# Mô hình KDF, thuật toán, tham số dẫn xuất và nhà cung cấp mật mã

## 1. Vì sao cần Key Derivation Function?

Một ứng dụng thường phải tạo nhiều khóa cho các mục đích khác nhau: mã hóa dữ liệu, xác thực thông điệp, bảo vệ kênh trao đổi, hoặc tách khóa theo phiên và theo giao thức. Nếu dùng một bí mật gốc cho nhiều chức năng, việc quản lý vòng đời và phạm vi sử dụng trở nên khó kiểm soát. Nếu tự ghép chuỗi, hash hoặc cắt byte để tạo khóa, ứng dụng có thể vô tình tạo ra khóa yếu, trùng lặp hoặc không tách biệt đúng mục đích.

**Key Derivation Function (KDF)** là thuật toán dẫn xuất vật liệu khóa mới từ *input keying material* (IKM) cùng các tham số bổ sung. KDF được thiết kế để biến đầu vào mật mã thành một hoặc nhiều giá trị đầu ra có cấu trúc và có thể tái tạo khi các bên dùng cùng thuật toán, đầu vào và tham số.

Java 25 bổ sung API chuẩn **Key Derivation Function API** theo **JEP 510**. API nằm trong package `javax.crypto`, cung cấp lớp `KDF`, giao diện tham số `HKDFParameterSpec` và cơ chế provider theo kiến trúc Java Cryptography Architecture (JCA). JEP 510 là bản hoàn thiện của API từng được preview ở Java 24; trong Java 25, API đã final và không cần `--enable-preview`. [JEP 510](https://openjdk.org/jeps/510)

Bài này thuộc chương **API dẫn xuất khóa** của module `JAVA_VERSION_JAVA25`. Trọng tâm là **mô hình KDF, thuật toán, tham số dẫn xuất và nhà cung cấp mật mã**; chỉ trình bày API và thực hành còn áp dụng trên Java hiện đại.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt KDF với hash thông thường, mã hóa, key agreement và password hashing.
2. Giải thích IKM, salt, PRK, info và hai bước HKDF-Extract/HKDF-Expand.
3. Sử dụng `KDF.getInstance`, `deriveKey`, `deriveData` và `HKDFParameterSpec` trên Java 25.
4. Chọn độ dài khóa và thuật toán đầu ra theo giao thức, không tự ý cắt hoặc ghép byte.
5. Hiểu cách provider cung cấp thuật toán, kiểm tra khả năng hỗ trợ và xử lý việc lựa chọn provider.
6. Thiết kế domain separation, vòng đời khóa, kiểm thử bằng test vectors và vận hành an toàn.
7. Nhận biết trường hợp không nên dùng HKDF, đặc biệt là dẫn xuất trực tiếp từ mật khẩu người dùng.

## 2. Trạng thái chính thức của KDF API trong Java 25

| Mốc | JEP | Trạng thái |
| --- | --- | --- |
| Java 24 | JEP 478 | Preview |
| **Java 25** | **JEP 510** | **Final / permanent** |

Các kiểu chính của API Java 25:

| Kiểu | Package | Vai trò |
| --- | --- | --- |
| `KDF` | `javax.crypto` | Tạo instance KDF và thực hiện dẫn xuất |
| `KDFParameters` | `javax.crypto` | Tham số khởi tạo riêng của thuật toán/provider nếu cần |
| `KDFSpi` | `javax.crypto` | SPI cho nhà cung cấp triển khai KDF |
| `HKDFParameterSpec` | `javax.crypto.spec` | Tham số cho HKDF Extract, Expand hoặc Extract-then-Expand |
| `SecretKey` | `javax.crypto` | Đại diện khóa bí mật đầu ra hoặc đầu vào |
| `AlgorithmParameterSpec` | `java.security.spec` | Kiểu tham số thuật toán được truyền cho thao tác dẫn xuất |

Trong JDK 25, các tên thuật toán HKDF chuẩn gồm:

- `HKDF-SHA256`
- `HKDF-SHA384`
- `HKDF-SHA512`

Đây là các biến thể HKDF dùng HMAC với hàm băm tương ứng, được định nghĩa trong RFC 5869. Provider `SunJCE` của JDK tham chiếu cung cấp các biến thể này. Provider khác có thể hỗ trợ tập thuật toán khác; ứng dụng phải kiểm tra provider thực tế đang triển khai. [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html) · [JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html)

**Lưu ý về phạm vi:** API KDF không tự động triển khai mọi KDF đang tồn tại. Việc Java 25 có lớp `KDF` không có nghĩa JDK mặc định cung cấp Argon2id, scrypt hoặc mọi thuật toán password-based. Danh sách thuật toán phải được kiểm tra theo đặc tả và provider.

## 3. KDF giải quyết bài toán nào?

Một KDF hữu ích khi ứng dụng đã có **vật liệu khóa đầu vào có entropy phù hợp** và cần dẫn xuất khóa cho một mục đích cụ thể.

Ví dụ các nguồn IKM:

- Shared secret sau một phép key agreement như ECDH hoặc X25519.
- Shared secret thu được từ một cơ chế KEM.
- Khóa gốc do KMS/HSM quản lý, nếu provider và KDF hỗ trợ xử lý loại key đó.
- Vật liệu khóa được cấp bởi một giao thức hoặc hệ thống mật mã đã xác định.

~~~mermaid
flowchart TD
    A["Nguồn IKM có entropy"] --> B["KDF / HKDF"]
    S["Salt (nếu giao thức dùng)"] --> B
    I["Info: context và mục đích"] --> B
    B --> K1["Khóa AES cho encryption"]
    B --> K2["Khóa HMAC cho authentication"]
    B --> K3["Khóa theo phiên / giao thức khác"]
~~~

Mỗi khóa đầu ra phải có **mục đích, thuật toán, độ dài và vòng đời rõ ràng**. Không sử dụng cùng một khóa cho nhiều primitive chỉ vì nó có đủ byte.

### KDF không thay thế các primitive khác

| Cơ chế | Nhiệm vụ |
| --- | --- |
| KDF | Dẫn xuất key material từ IKM và tham số |
| Hash | Tạo digest từ dữ liệu; không mặc nhiên tạo khóa bí mật |
| KeyGenerator | Sinh khóa mới bằng nguồn ngẫu nhiên phù hợp |
| KeyAgreement | Hai bên tạo shared secret qua giao thức trao đổi khóa |
| KEM | Encapsulation/decapsulation tạo shared secret và ciphertext encapsulation |
| Cipher | Mã hóa/giải mã bằng khóa và tham số phù hợp |
| MAC | Tạo/xác minh mã xác thực thông điệp |
| Password KDF | Làm chậm/giảm hiệu quả dò mật khẩu và dẫn xuất vật liệu từ mật khẩu có entropy thấp |

Không dùng `SHA-256(password)` rồi coi kết quả là khóa an toàn. Hash thông thường không tự cung cấp cơ chế chống dò mật khẩu offline, và không nên tự thiết kế một KDF bằng cách lặp hash hoặc nối chuỗi.

## 4. Mô hình HKDF: Extract và Expand

Java 25 có triển khai HKDF theo **RFC 5869**. HKDF gồm hai giai đoạn logic:

~~~text
Input Keying Material (IKM)
          |
          v
   HKDF-Extract(salt, IKM)
          |
          v
   Pseudorandom Key (PRK)
          |
          v
   HKDF-Expand(PRK, info, L)
          |
          v
   Output Keying Material (OKM)
~~~

### 4.1. Extract

`HKDF-Extract` nhận IKM và salt, tạo ra một pseudorandom key (PRK). Có thể hiểu đây là bước chuẩn hóa vật liệu đầu vào thành một khóa giả ngẫu nhiên phù hợp cho bước mở rộng.

Trong RFC 5869, salt là đầu vào không nhất thiết bí mật. Khi không cung cấp salt, HKDF sử dụng giá trị mặc định theo quy định của RFC. Nếu giao thức có salt riêng, phải dùng đúng cách tạo, truyền và xác thực salt theo giao thức đó.

### 4.2. Expand

`HKDF-Expand` nhận PRK, thông tin context `info` và độ dài đầu ra `L`, rồi tạo output keying material (OKM). `info` ràng buộc khóa dẫn xuất với ứng dụng hoặc ngữ cảnh, chẳng hạn:

- Tên giao thức và phiên bản.
- Mục đích sử dụng: encryption hay authentication.
- Vai trò client/server hoặc chiều gửi/nhận.
- Thuật toán và định danh suite.
- Định danh phiên hoặc context đã được chuẩn hóa theo giao thức.

Bằng cách thay đổi `info`, cùng một IKM có thể dẫn xuất các khóa khác nhau cho những mục đích khác nhau. Đây là kỹ thuật **domain separation**: ngăn việc vô tình dùng một khóa đầu ra ở nhầm giao thức hoặc nhầm vai trò.

### 4.3. Extract-then-Expand

Đây là đường sử dụng phổ biến khi có IKM ban đầu và muốn tạo khóa đầu ra:

\[
PRK = HKDF\text{-}Extract(salt, IKM)
\]

\[
OKM = HKDF\text{-}Expand(PRK, info, L)
\]

Trong đó `L` là số byte đầu ra. RFC 5869 giới hạn độ dài Expand tối đa là `255 × HashLen`, với `HashLen` là kích thước output của HMAC hash tương ứng. Provider phải từ chối tham số vượt giới hạn.

**Không tự nối nhiều lần output để vượt giới hạn** hoặc thay đổi cấu trúc RFC. Nếu giao thức cần nhiều khóa, hãy xác định các label/context riêng và dẫn xuất theo đúng đặc tả.

## 5. Hiểu đúng IKM, salt, info và độ dài đầu ra

| Tham số | Ý nghĩa | Yêu cầu thiết kế |
| --- | --- | --- |
| IKM | Input keying material, đầu vào bí mật hoặc vật liệu khóa có entropy | Phải có nguồn tin cậy và entropy phù hợp; không dùng chuỗi tùy ý |
| Salt | Tham số Extract, không nhất thiết bí mật | Theo giao thức; có thể là ngẫu nhiên hoặc giá trị công khai đã xác định |
| PRK | Kết quả của Extract | Vật liệu khóa trung gian, phải bảo vệ như bí mật |
| Info | Context/application-specific information của Expand | Dùng label rõ ràng, mã hóa không nhập nhằng, tách biệt mục đích |
| L | Độ dài OKM theo byte | Phải đúng yêu cầu thuật toán đích và giới hạn HKDF |

### IKM không phải lúc nào cũng là password

IKM thường là shared secret hoặc key material có entropy đủ cao. Một password do người dùng tự chọn có thể có entropy thấp và dễ bị dò; HKDF không được thiết kế để tự tăng entropy của một password yếu.

### Salt không phải khóa bí mật

Salt thường có thể được truyền cùng dữ liệu giao thức. Vai trò của nó là làm đầu vào cho Extract theo quy tắc HKDF, không phải thay thế secret hoặc làm mật khẩu khó đoán hơn nếu password yếu.

### Info không phải chỗ chứa secret

`info` dùng để ràng buộc context. Không đưa access token, password, private key hay payload bí mật vào info. Nếu context có định danh, phải chuẩn hóa cách encode và bảo đảm hai bên dùng cùng bytes.

### Độ dài đầu ra phải gắn với thuật toán đích

Ví dụ:

| Đầu ra | Độ dài phổ biến |
| --- | ---: |
| AES-128 key | 16 byte |
| AES-192 key | 24 byte |
| AES-256 key | 32 byte |
| HMAC key | Theo protocol và chính sách mật mã |

Các con số trên là độ dài biểu diễn khóa, không phải quy tắc chọn tùy ý. Dùng chính xác độ dài do protocol hoặc security design yêu cầu. Không cắt một output ngẫu nhiên cho vừa API đích mà không xem lại thiết kế.

## 6. API Java 25: KDF và HKDFParameterSpec

### 6.1. Tạo KDF instance

~~~java
KDF kdf = KDF.getInstance("HKDF-SHA256");
~~~

`getInstance` yêu cầu provider có triển khai thuật toán. Nếu không có, phương thức có thể ném `NoSuchAlgorithmException`. Các overload cho phép chỉ định tên hoặc object `Provider`; chỉ chỉ định provider khi hệ thống có yêu cầu rõ về implementation.

### 6.2. Tạo tham số Extract-then-Expand

~~~java
AlgorithmParameterSpec params =
        HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, 32);
~~~

Các thành phần:

- `HKDFParameterSpec.ofExtract()` tạo builder cho HKDF Extract.
- `addIKM(...)` cung cấp input keying material.
- `addSalt(...)` cung cấp salt.
- `thenExpand(info, 32)` hoàn tất tham số Extract-then-Expand với info và output length 32 byte.

`HKDFParameterSpec` có các dạng tham số cho Extract, Expand và Extract-then-Expand. Builder có thể nhận IKM/salt dưới dạng `byte[]` hoặc `SecretKey`; nhiều thành phần có thể được thêm lần lượt theo thứ tự. Điều này hữu ích khi một phần key material nằm trong thiết bị mật mã và không thể export thành byte array. [HKDFParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html) · [Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.Builder.html)

### 6.3. Dẫn xuất thành SecretKey

~~~java
SecretKey key = kdf.deriveKey("AES", params);
~~~

`deriveKey` trả về `SecretKey` có thuật toán được yêu cầu, ví dụ `AES`. Ưu tiên dạng key object khi cần truyền trực tiếp cho các API mật mã khác; tránh chuyển key sang chuỗi hoặc log byte của key.

### 6.4. Dẫn xuất raw data

~~~java
byte[] material = kdf.deriveData(params);
~~~

`deriveData` trả về byte array raw. Nó hữu ích khi giao thức thật sự cần raw key material hoặc khi kết quả không thể biểu diễn bằng một `SecretKey` theo cách provider hỗ trợ.

Nếu key material không extractable, `deriveData` có thể ném `UnsupportedOperationException`. Đừng gọi `getEncoded()` trên `SecretKey` rồi mặc định kết quả luôn khác null; hardware-backed/non-extractable keys có thể không cho phép export.

## 7. Ví dụ đầy đủ: dẫn xuất AES-256 key từ IKM

Ví dụ sau dùng dữ liệu giả lập để minh họa API. Trong ứng dụng thật, `ikm` phải đến từ một nguồn mật mã đã được thiết kế và kiểm chứng, không phải một hằng số hard-code.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

public final class HkdfKeyDerivation {

    private HkdfKeyDerivation() {
    }

    public static SecretKey deriveAes256Key(
            byte[] ikm,
            byte[] salt,
            String purpose) throws GeneralSecurityException {

        byte[] info = (
                "com.example.orders/v1/aes-256/" + purpose
        ).getBytes(StandardCharsets.UTF_8);

        KDF hkdf = KDF.getInstance("HKDF-SHA256");

        var parameters = HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, 32);

        return hkdf.deriveKey("AES", parameters);
    }
}
~~~

Phân tích:

1. `KDF.getInstance("HKDF-SHA256")` chọn thuật toán HKDF dùng HMAC-SHA-256.
2. `ikm` cung cấp key material; `salt` là salt theo thiết kế giao thức.
3. `info` gắn khóa với ứng dụng, phiên bản và mục đích.
4. `thenExpand(info, 32)` yêu cầu 32 byte output, phù hợp độ dài AES-256.
5. `deriveKey("AES", parameters)` trả về một `SecretKey` thuật toán AES.

### Những điều ví dụ chưa làm

- Chưa tạo hoặc trao đổi IKM; ví dụ giả định đầu vào đã có nguồn tin cậy.
- Chưa quản lý salt persistence hoặc protocol transcript.
- Chưa lưu khóa vào KMS/HSM.
- Chưa mã hóa dữ liệu hoặc quản lý nonce.
- Chưa xử lý rotation, key identifier, revocation và audit.
- Chưa kiểm tra compliance/provider policy của môi trường triển khai.

Đây là **ví dụ API**, không phải một protocol hoàn chỉnh để sao chép nguyên trạng vào production.

## 8. Extract-only và Expand-only

Trong một số giao thức, các bước Extract và Expand được thực hiện ở những nơi hoặc thời điểm khác nhau.

### Extract-only

`extractOnly()` tạo tham số cho giai đoạn Extract:

~~~java
var extractParameters = HKDFParameterSpec.ofExtract()
        .addIKM(ikm)
        .addSalt(salt)
        .extractOnly();
~~~

Sau đó có thể gọi `deriveData(extractParameters)` để nhận raw PRK khi quy trình cho phép export:

~~~java
byte[] prk = KDF.getInstance("HKDF-SHA256")
        .deriveData(extractParameters);
~~~

PRK là bí mật trung gian; không log, không gửi qua kênh không bảo vệ và không lưu lâu hơn cần thiết. Nếu dùng byte array, giới hạn phạm vi tồn tại và xem xét xóa sau khi sử dụng; việc ghi đè mảng trong Java không phải bảo đảm xóa vật lý tuyệt đối do runtime, copies và tối ưu hóa.

### Expand-only

Nếu đã có PRK dưới dạng `SecretKey`, có thể xây dựng tham số Expand:

~~~java
var expandParameters =
        HKDFParameterSpec.expandOnly(prk, info, 32);

SecretKey encryptionKey =
        KDF.getInstance("HKDF-SHA256")
                .deriveKey("AES", expandParameters);
~~~

Trong đó `prk` phải thực sự là PRK đúng theo HKDF và `info` phải giống chính xác context mà protocol quy định. Không dùng một key AES đang mã hóa dữ liệu làm PRK chỉ vì nó là `SecretKey`.

### Khi nào nên tách hai giai đoạn?

- Giao thức yêu cầu bên này thực hiện Extract và bên khác thực hiện Expand.
- Key material được giữ trong provider/HSM và cần tránh export.
- Một phiên cần dẫn xuất nhiều key với các label riêng từ cùng PRK.
- Protocol specification quy định rõ lifecycle của PRK.

Nếu ứng dụng chỉ cần một khóa từ một IKM, dạng `ofExtract().addIKM(...).addSalt(...).thenExpand(...)` thường dễ đọc và ít sai hơn.

## 9. Multi-part IKM và provider có key không export được

Builder của `HKDFParameterSpec` cho phép thêm IKM/salt nhiều lần:

~~~java
var params = HKDFParameterSpec.ofExtract()
        .addIKM(label)
        .addIKM(sharedSecretKey)
        .addSalt(protocolSalt)
        .thenExpand(info, 32);
~~~

HKDF định nghĩa cách kết hợp các thành phần input theo thứ tự. API cho phép một phần IKM là `SecretKey` thay vì bắt buộc mọi thành phần phải là byte array. Điều này hữu ích khi key material nằm trong HSM hoặc thiết bị mà ứng dụng không được phép đọc raw bytes.

**Thứ tự thành phần là một phần của protocol.** Hai phía phải thêm các phần IKM/salt theo cùng thứ tự và cùng encoding. Nếu đổi thứ tự, thay đổi label hoặc dùng bytes khác, output sẽ khác.

Không cố lấy `sharedSecretKey.getEncoded()` để nối byte khi key không export được. Truyền `SecretKey` trực tiếp vào builder nếu provider và KDF implementation hỗ trợ loại key đó.

## 10. KDF provider trong Java Cryptography Architecture

`KDF` sử dụng mô hình provider tương tự các engine class khác của JCA. Ứng dụng yêu cầu một thuật toán theo tên; provider được chọn sẽ thực thi thao tác.

### Vai trò của provider

- Cung cấp implementation cho tên thuật toán, ví dụ `HKDF-SHA256`.
- Xác định kiểu key material và tham số được hỗ trợ.
- Có thể tích hợp với key store, thiết bị phần cứng hoặc cơ chế bảo vệ khóa.
- Có thể cung cấp thêm thuật toán ngoài những implementation mặc định của JDK.
- Chịu trách nhiệm tuân thủ contract của JCA SPI.

Trong JDK tham chiếu Java 25, `SunJCE` cung cấp `HKDF-SHA256`, `HKDF-SHA384` và `HKDF-SHA512`. Điều này không có nghĩa mọi JDK vendor hoặc mọi provider bên thứ ba phải hỗ trợ cùng tập thuật toán. [SunJCE provider algorithm list](https://docs.oracle.com/en/java/javase/25/security/security-developer-guide.pdf)

### Kiểm tra khả năng hỗ trợ

Có thể truy vấn provider đã đăng ký:

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.KDF;

public class KdfProviderCheck {
    public static void main(String[] args) throws Exception {
        KDF kdf = KDF.getInstance("HKDF-SHA256");

        System.out.println("Algorithm: " + kdf.getAlgorithm());

        for (Provider provider : Security.getProviders()) {
            Provider.Service service =
                    provider.getService("KDF", "HKDF-SHA256");

            if (service != null) {
                System.out.println(
                        provider.getName() + " -> " + service.getAlgorithm());
            }
        }
    }
}
~~~

Đoạn kiểm tra service hữu ích để kiểm kê provider đã đăng ký. Tuy nhiên, việc provider có khai báo thuật toán **chưa chứng minh** nó hỗ trợ mọi dạng tham số hoặc loại key cụ thể. Hãy chạy phép dẫn xuất thử với key material và parameter spec thực tế trong môi trường kiểm thử.

### Chỉ định provider tường minh

Nếu chính sách ứng dụng bắt buộc provider cụ thể, có thể yêu cầu theo tên hoặc object:

~~~java
KDF hkdf = KDF.getInstance("HKDF-SHA256", "SunJCE");
~~~

Tên provider phải tồn tại và hỗ trợ thuật toán. Hard-code provider có thể làm ứng dụng phụ thuộc implementation, khiến deployment trên vendor khác hoặc HSM khác thất bại. Chỉ chỉ định provider khi yêu cầu compliance, vận hành hoặc key custody đòi hỏi; nếu không, dùng cơ chế lựa chọn provider của JCA và kiểm tra kết quả.

## 11. Delayed provider selection và khả năng dùng key phần cứng

Một đặc điểm quan trọng của `KDF` là **delayed provider selection** khi gọi `getInstance` mà không chỉ định provider. Provider có thể được chọn trễ cho đến lúc `deriveKey` hoặc `deriveData` nhận được key material thực tế.

Lý do: provider cần biết loại IKM/SecretKey để chọn implementation có thể xử lý nó. Ví dụ, một `SecretKey` nằm trong thiết bị phần cứng có thể không export được; không phải provider nào cũng sử dụng được key đó.

Quy trình khái quát:

~~~mermaid
flowchart TD
    A["KDF.getInstance(algorithm)"] --> B["KDF instance"]
    B --> C["deriveKey / deriveData với parameters"]
    C --> D["Xem thuật toán, params và key material"]
    D --> E["Chọn provider hỗ trợ"]
    E --> F["Thực hiện dẫn xuất"]
~~~

Một lưu ý API: nếu gọi các phương thức như `getProviderName` hoặc `getParameters` trước khi thực hiện derivation, provider đầu tiên hỗ trợ algorithm/initial parameters có thể được chọn sớm. Provider này chưa chắc xử lý được key material thực tế được truyền sau đó. Khi dùng key không export được, tránh ép lựa chọn provider sớm mà chưa hiểu hệ quả.

**Kết luận vận hành:** provider selection là một phần của thiết kế key custody. Nếu ứng dụng yêu cầu HSM/PKCS#11, hãy test bằng provider và thiết bị thật, không chỉ kiểm tra thuật toán trên máy developer.

## 12. Thread safety và vòng đời KDF object

API Java SE quy định các method của `KDF` **không thread-safe**, trừ khi implementation có tài liệu riêng nói khác. Không chia sẻ một instance `KDF` cho nhiều thread chạy đồng thời mà không có cơ chế đồng bộ.

Một cách đơn giản là tạo instance riêng cho từng thao tác:

~~~java
SecretKey deriveKey(byte[] ikm, byte[] salt, byte[] info)
        throws Exception {

    KDF kdf = KDF.getInstance("HKDF-SHA256");

    var params = HKDFParameterSpec.ofExtract()
            .addIKM(ikm)
            .addSalt(salt)
            .thenExpand(info, 32);

    return kdf.deriveKey("AES", params);
}
~~~

Nếu muốn tái sử dụng object để giảm chi phí tạo instance, cần đánh giá provider implementation và bảo đảm đồng bộ theo contract. Đừng giả định object có tên API immutable thì toàn bộ engine object cũng an toàn khi dùng đồng thời.

Cũng cần xem `HKDFParameterSpec.Builder` là builder không thread-safe. Tạo builder riêng cho từng lần dựng tham số, không dùng chung giữa các request.

## 13. Dùng key dẫn xuất với AES-GCM

Một ví dụ tiếp theo cho thấy `SecretKey` dẫn xuất có thể truyền vào Cipher. GCM cần nonce duy nhất cho mỗi lần mã hóa với cùng key; ví dụ dùng nonce ngẫu nhiên 12 byte và tag 128 bit:

~~~java
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmExample {

    private static final SecureRandom RANDOM = new SecureRandom();

    public static byte[] encrypt(
            SecretKey key, byte[] plaintext) throws Exception {

        byte[] nonce = new byte[12];
        RANDOM.nextBytes(nonce);

        GCMParameterSpec parameters =
                new GCMParameterSpec(128, nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, parameters);

        byte[] ciphertext = cipher.doFinal(plaintext);

        // Protocol phải lưu/truyền nonce cùng ciphertext.
        return concatenate(nonce, ciphertext);
    }

    private static byte[] concatenate(byte[] first, byte[] second) {
        byte[] result = new byte[first.length + second.length];
        System.arraycopy(first, 0, result, 0, first.length);
        System.arraycopy(second, 0, result, first.length, second.length);
        return result;
    }
}
~~~

Đây là ví dụ minh họa cho cách dùng key, chưa phải format lưu trữ production. Nonce ngẫu nhiên 96-bit chỉ cho xác suất va chạm thấp chứ không bảo đảm duy nhất tuyệt đối; hệ thống mã hóa nhiều bản ghi dưới cùng một key phải giới hạn số lần dùng và chọn cơ chế cấp nonce phù hợp với protocol (chẳng hạn bộ đếm duy nhất được quản lý bền vững). Khi triển khai:

- Không bao giờ tái sử dụng cùng nonce với cùng AES-GCM key.
- Dùng nguồn random phù hợp và thiết kế nonce theo protocol để tránh collision.
- Bảo đảm nonce được truyền cùng ciphertext và được xác thực theo cách giao thức yêu cầu.
- Khi giải mã, dùng đúng nonce và tag; bắt lỗi authentication failure.
- Có key version/key identifier để chọn đúng khóa khi decrypt dữ liệu cũ.
- Không dùng cùng một key đầu ra cho encryption và HMAC; dẫn xuất các key riêng với `info` khác nhau.

Trong code production, cũng nên xem xét API lưu/đóng gói dữ liệu chuẩn thay vì tự nối byte không có version/length framing.

## 14. HKDF không phải password hashing

Đây là phân biệt bảo mật quan trọng.

**HKDF** phù hợp khi IKM đã có entropy đủ cao, chẳng hạn shared secret từ key agreement. Nó được tối ưu để trích xuất và mở rộng key material, không phải để làm việc dò password trở nên tốn kém.

Mật khẩu người dùng thường có entropy thấp và có thể đoán được. Nếu dùng HKDF-SHA256 trực tiếp với password, attacker có thể thử từ điển nhanh; salt không tự biến một password yếu thành secret mạnh.

| Nhu cầu | Hướng phù hợp |
| --- | --- |
| Dẫn xuất nhiều khóa từ ECDH/shared secret | HKDF theo protocol |
| Tách encryption/authentication key từ PRK | HKDF với info/domain separation khác nhau |
| Lưu password người dùng | Password hashing/KDF chuyên dụng như Argon2id hoặc scrypt; PBKDF2 khi tiêu chuẩn/chính sách yêu cầu |
| Sinh khóa mới ngẫu nhiên độc lập | `KeyGenerator` hoặc hệ thống KMS/HSM |
| Trao đổi/thiết lập shared secret | KeyAgreement hoặc KEM, sau đó dùng KDF nếu protocol quy định |

JDK 25 KDF API và provider mặc định có hỗ trợ HKDF; **không được suy ra** API đó tự cung cấp Argon2id/scrypt. Nếu ứng dụng cần password hashing, chọn implementation được duy trì và kiểm toán, cấu hình work factor theo threat model và phần cứng hiện tại, lưu salt/parameters theo format đã chuẩn hóa.

Không dùng các mẫu cũ như hash một lần bằng MD5/SHA-1 hoặc tự lặp digest để thay thế password hashing hiện đại.

## 15. Kiểm thử: test vectors, tính xác định và tính tương thích

KDF có tính xác định: cùng thuật toán, IKM, salt, info và output length phải cho cùng output theo specification. Vì vậy, **test vectors chuẩn** là nền tảng để kiểm tra implementation và tương thích giữa provider.

### Các lớp kiểm thử cần có

1. **RFC test vectors:** dùng các test vector HKDF từ RFC 5869 cho SHA-256/SHA-384/SHA-512 phù hợp implementation.
2. **Parameter validation:** input rỗng, salt không có, info không có, output length bằng 0, length vượt giới hạn.
3. **Algorithm support:** xác nhận provider hỗ trợ tên HKDF cần thiết.
4. **Cross-provider compatibility:** cùng test vectors trên các provider được phép sử dụng.
5. **Context separation:** thay đổi `info` theo purpose phải tạo output khác nhau.
6. **Key use:** key dẫn xuất có algorithm/length đúng và hoạt động với Cipher/MAC tương ứng.
7. **Non-extractable key:** nếu dùng HSM, test với key thật và xác nhận không cần export.
8. **Failure behavior:** không hỗ trợ algorithm/provider hoặc tham số sai phải được xử lý rõ ràng.

### Ví dụ kiểm thử cấu trúc đầu ra

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import javax.crypto.SecretKey;
import org.junit.jupiter.api.Test;

class HkdfKeyDerivationTest {

    @Test
    void derivesAes256Key() throws Exception {
        byte[] ikm = new byte[32];
        byte[] salt = new byte[16];

        SecretKey key = HkdfKeyDerivation.deriveAes256Key(
                ikm, salt, "encryption");

        assertNotNull(key);
        assertEquals("AES", key.getAlgorithm());
        assertEquals(32, key.getEncoded().length);
    }
}
~~~

Đây là kiểm tra smoke với dữ liệu giả và provider trả key extractable. Nó **không thay thế RFC 5869 test vector** và không được dùng để chứng minh tính đúng đắn mật mã. Với HSM hoặc key không export được, không kiểm tra bằng `getEncoded().length`; hãy xác minh bằng phép sử dụng key trong thao tác mật mã được phép.

### Không tự viết expected output từ chính implementation

Nếu test lấy output lần đầu rồi hard-code lại làm expected, nó chỉ kiểm tra tính lặp lại của code hiện tại, không xác nhận RFC. Dùng vector độc lập có nguồn tin cậy và kiểm tra cả hai phía nếu giao thức đa ngôn ngữ.

## 16. Quản lý khóa và triển khai production

Một API chuẩn làm giảm code tự viết, nhưng không thay thế kiến trúc quản lý khóa.

### Nguồn IKM và lưu trữ

- Ưu tiên shared secret/key material từ KMS, HSM hoặc giao thức trao đổi khóa đã được review.
- Không hard-code IKM trong source, Docker image hoặc file cấu hình công khai.
- Hạn chế export key bytes; truyền `SecretKey` qua provider nếu implementation hỗ trợ.
- Tách quyền sử dụng key khỏi quyền quản trị/rotation.
- Xác định key identifier, version, owner và ngày hết hạn/rotation.
- Không ghi IKM, PRK, OKM hoặc `SecretKey.getEncoded()` vào logs.

### Salt và info

- Chuẩn hóa encoding của `info`, ví dụ UTF-8 với label và version được xác định rõ.
- Đưa protocol, purpose, direction và version vào domain separation khi phù hợp.
- Salt phải được lưu/truyền cùng context nếu protocol cần tái tạo khóa; salt không cần bảo mật nhưng phải giữ đúng.
- Không lấy một chuỗi tùy ý từ request làm `info` nếu hai bên không có quy tắc canonicalization giống nhau.
- Không tự thêm/bớt prefix khi protocol đã định nghĩa chính xác bytes.

### Rotation và khả năng giải mã dữ liệu cũ

Khi dẫn xuất key từ root key, thay root key sẽ tạo output mới. Dữ liệu đã mã hóa cần metadata để biết dùng key version nào khi giải mã:

~~~text
EncryptedRecord
├── formatVersion
├── keyId / keyVersion
├── salt (nếu protocol dùng)
├── nonce
├── ciphertext
└── authenticationTag (nếu format tách riêng)
~~~

Đây là cấu trúc logic minh họa, không phải định dạng chuẩn. Khi rotation, giữ cơ chế decrypt dữ liệu cũ trong thời gian được phép, chuyển mã hóa mới sang key version mới, rồi loại bỏ key cũ theo policy. Không xóa root key trước khi chắc dữ liệu cần giữ không còn phụ thuộc vào nó.

### Bảo vệ dữ liệu trong bộ nhớ

Java không cung cấp bảo đảm xóa tuyệt đối mọi bản sao secret do runtime, provider, garbage collector và tối ưu hóa có thể tạo copies. Vì vậy:

- Giảm thời gian tồn tại của byte arrays chứa bí mật.
- Không giữ secret trong object singleton hoặc cache không có policy.
- Nếu API/provider hỗ trợ key không export được, ưu tiên giữ key trong provider.
- Có thể ghi đè mảng byte sau khi dùng trong phạm vi ứng dụng kiểm soát, nhưng không tuyên bố đây là secure zeroization tuyệt đối.
- Hạn chế heap dump, core dump và quyền truy cập process trong môi trường xử lý khóa.

## 17. Các lỗi thường gặp và cách xử lý

| Lỗi/hiểu nhầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng HKDF trực tiếp với password | Dễ bị brute-force nhanh | Dùng password hashing/KDF chuyên dụng |
| Dùng SHA-256 rồi cắt 32 byte | Không có HKDF extract/expand/domain separation | Dùng API KDF và protocol parameters |
| Bỏ qua `info` | Các key purpose có thể không được tách biệt rõ | Đặt label/context theo giao thức |
| Dùng cùng output cho AES và HMAC | Vi phạm key separation | Dẫn xuất key riêng với info riêng |
| Tự chọn output length | Key không khớp thuật toán/protocol | Dùng đúng length đã được chuẩn hóa |
| Nhầm salt là secret | Lưu trữ/trao đổi không cần thiết phức tạp | Hiểu salt không cần bí mật; vẫn phải giữ đúng giá trị |
| Gọi `getEncoded()` rồi log key | Lộ bí mật | Không log key; dùng `SecretKey` trực tiếp |
| Giả định mọi provider có HKDF | `NoSuchAlgorithmException` hoặc lỗi deploy | Kiểm tra provider trên runtime mục tiêu |
| Chỉ kiểm tra tên provider | Có thể không hỗ trợ key/parameters cụ thể | Test derivation với key thực tế |
| Chia sẻ một KDF instance giữa threads | Race/concurrency behavior không được đảm bảo | Tạo instance riêng hoặc đồng bộ |
| Dùng `deriveData` với non-extractable key | Có thể ném `UnsupportedOperationException` | Dùng `deriveKey`/provider phù hợp |
| Tự nối nhiều output vượt giới hạn HKDF | Không còn đúng RFC | Thiết kế số key/label/length đúng protocol |
| Hard-code IKM trong ứng dụng | Khó rotation, lộ secret | Dùng KMS/HSM/secret management |

### Những API/thuật toán không nên lấy làm mẫu mới

Không dùng ví dụ hash yếu hoặc PBE legacy để “minh họa KDF” trong code mới. Không tự triển khai HKDF bằng HMAC thủ công khi Java 25 có API chuẩn và provider đã hỗ trợ; chỉ viết implementation riêng khi có yêu cầu provider/protocol rõ ràng, kiểm toán và test vectors đầy đủ. Không dùng một algorithm name không có trong Standard Algorithm Names rồi giả định mọi JDK đều hỗ trợ.

## 18. Bài thực hành: tách khóa encryption và authentication

### Bối cảnh

Một dịch vụ trao đổi dữ liệu đã có shared secret `IKM` từ một cơ chế key agreement được giao thức chấp thuận. Cần tạo:

- Khóa AES-256 cho mã hóa dữ liệu.
- Khóa HMAC-SHA-256 cho xác thực một kênh/format riêng, nếu giao thức yêu cầu hai primitive độc lập.

Không được sử dụng cùng một key object cho cả hai mục đích.

### Nhiệm vụ

1. Tạo `byte[] ikm` và `byte[] salt` giả lập cho môi trường test.
2. Xây dựng `info` riêng cho encryption, ví dụ label chứa protocol name, version và direction.
3. Dùng `KDF.getInstance("HKDF-SHA256")` cùng `HKDFParameterSpec` để derive 32-byte AES key.
4. Tạo một `info` khác cho authentication và derive một key riêng theo độ dài giao thức yêu cầu.
5. Xác nhận cùng IKM/salt nhưng info khác nhau cho output khác nhau.
6. Dùng AES-GCM để mã hóa dữ liệu giả; đảm bảo nonce không lặp với cùng key.
7. Viết test kiểm tra algorithm, độ dài key, test vector và provider.
8. Thử thay provider hoặc chạy trên runtime khác; ghi nhận thuật toán nào được hỗ trợ.
9. Nếu có môi trường HSM, thử dùng `SecretKey` không export được làm IKM và xác minh provider selection.
10. Viết một trang thiết kế ngắn mô tả key version, salt, info, rotation, retention và xử lý khi không còn provider tương thích.

### Câu hỏi tự đánh giá

- IKM, PRK và OKM khác nhau thế nào?
- Vì sao salt không nhất thiết bí mật nhưng vẫn phải được giữ đúng?
- `info` giúp domain separation như thế nào?
- Khi nào nên dùng `deriveKey` thay vì `deriveData`?
- Tại sao HKDF không phù hợp làm password hashing?
- Vì sao provider có thể được chọn trễ cho đến khi có key material?
- Điều gì xảy ra nếu dùng `getProviderName` trước khi đưa non-extractable key vào?
- Vì sao không nên chia sẻ `KDF` instance giữa nhiều thread?
- Giới hạn output của HKDF được tính theo gì?
- Nếu thay root IKM, dữ liệu cũ được giải mã bằng cách nào?
- Làm sao chứng minh implementation tuân thủ RFC 5869 thay vì chỉ cho output lặp lại?

## 19. Checklist review trước khi dùng KDF trong production

- [ ] Xác định nguồn IKM và chứng minh entropy/nguồn tin cậy phù hợp.
- [ ] Thuật toán KDF và hash/HMAC đã được giao thức hoặc security review chấp thuận.
- [ ] Tên thuật toán được provider mục tiêu hỗ trợ trên runtime thực tế.
- [ ] Salt được tạo, truyền và lưu theo protocol; không nhầm salt với secret.
- [ ] Info có encoding canonical và label tách biệt purpose/version/direction.
- [ ] Output length phù hợp key algorithm và nằm trong giới hạn HKDF.
- [ ] Khóa đầu ra được tách biệt cho encryption/authentication/other uses.
- [ ] Không dùng HKDF để dẫn xuất trực tiếp từ password yếu.
- [ ] Ưu tiên `deriveKey` và `SecretKey`; không export key nếu không cần.
- [ ] Provider selection và non-extractable key đã được test nếu dùng HSM.
- [ ] Không chia sẻ KDF/Builder instance giữa threads khi chưa có bảo đảm.
- [ ] RFC test vectors và cross-provider tests đạt.
- [ ] Có key ID/version, rotation và khả năng xử lý dữ liệu cũ.
- [ ] Không log IKM, PRK, OKM, password hoặc encoded secret key.
- [ ] Đã xác định retention, quyền truy cập, heap/core dump và xử lý secret trong memory.
- [ ] Có quy trình fallback/incident khi provider hoặc thuật toán không khả dụng.

**Tiêu chí hoàn thành:** người học hiểu KDF là bước dẫn xuất key material theo một thuật toán và bộ tham số đã định nghĩa; có thể dùng **Java 25 KDF API** để thực hiện HKDF Extract/Expand, giải thích IKM/salt/info/output length, chọn provider phù hợp và kiểm tra bằng test vectors. Quan trọng nhất, việc dẫn xuất khóa phải tuân thủ protocol, domain separation, key lifecycle và security review; API chuẩn không thay thế thiết kế mật mã an toàn.

## 20. Tài liệu chính thức và tiêu chuẩn tham khảo

- [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510): trạng thái final trong Java 25 và mục tiêu API.
- [Java SE 25 — KDF API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html): `getInstance`, `deriveKey`, `deriveData`, delayed provider selection và thread-safety.
- [Java SE 25 — HKDFParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html): Extract, Expand, Extract-then-Expand.
- [Java SE 25 — HKDFParameterSpec.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.Builder.html): thêm IKM/salt, tạo tham số và giới hạn Expand.
- [Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html): mô hình KDF, HKDF và provider.
- [Java Security Standard Algorithm Names — Java 25](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html): tên chuẩn `HKDF-SHA256`, `HKDF-SHA384` và `HKDF-SHA512`.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869): thuật toán Extract/Expand, salt, info, output length và test vectors.

Khi nâng JDK hoặc thay vendor/provider, hãy kiểm tra tài liệu và danh sách thuật toán của **runtime mục tiêu**. Không giả định mọi provider có cùng implementation, cùng hỗ trợ hardware key hoặc cùng chính sách mật mã. KDF API là tính năng chuẩn của Java 25, nhưng tính đúng đắn của hệ thống vẫn phụ thuộc nguồn IKM, tham số, protocol và quản lý khóa.
