# 2.4 Phân biệt API bắt buộc của Java SE với thuật toán do một JDK cung cấp

## Mục tiêu

Khi viết ứng dụng mật mã bằng Java, cần trả lời **ba câu hỏi khác nhau**:

1. **Java SE quy định API nào?** Ví dụ `MessageDigest`, `Signature`, `SecureRandom` trong `java.security`, hoặc `Cipher`, `Mac` trong `javax.crypto` là các API chuẩn mà mã ứng dụng có thể lập trình dựa vào.
2. **Java SE yêu cầu triển khai những thuật toán nào?** Đây là tập tối thiểu được nêu riêng trong mục **Security Algorithm Implementation Requirements** của đặc tả tương ứng với *phiên bản Java SE*.
3. **JDK/runtime đang chạy thực tế cung cấp những gì?** Các provider có sẵn hoặc được cài thêm quyết định danh sách thuật toán, transformation, định dạng keystore và một số đặc tính triển khai thực tế.

Ba câu hỏi có liên hệ nhưng không đồng nghĩa. **Có lớp API** không bảo đảm **mọi tên thuật toán** đều dùng được; **tên thuật toán được chuẩn hóa** cũng không có nghĩa Java SE yêu cầu mọi implementation hỗ trợ tên đó.

> Trong bài này, các ví dụ về tập bắt buộc lấy **Java SE 17** làm mốc để kiểm chứng cụ thể. Với Java SE 21, 25 hoặc phiên bản khác, phải kiểm tra *đúng phiên bản đặc tả* trước khi kết luận. Một bản JDK là sản phẩm triển khai Java SE kèm các công cụ; những provider và thuật toán mở rộng có thể khác nhau giữa bản phân phối, hệ điều hành, cấu hình và phiên bản cập nhật.

## 1. Bốn tầng cần phân biệt

| Tầng | Ý nghĩa | Ví dụ | Suy luận hợp lệ |
| --- | --- | --- | --- |
| **API/engine của Java SE** | Lớp, phương thức và hợp đồng lập trình chuẩn | `MessageDigest.getInstance(String)`, `Cipher.getInstance(String)`, `Security.getProviders()` | Có thể biên dịch mã sử dụng API trên phiên bản Java SE đã định, miễn dùng module/API phù hợp. |
| **Standard algorithm name** | Tên chuẩn để yêu cầu một loại dịch vụ | `SHA-256`, `SHA3-256`, `ChaCha20-Poly1305`, `RSASSA-PSS`, `PKCS12` | Nếu implementation cung cấp dịch vụ ấy, nên dùng tên chuẩn. **Chưa chứng minh dịch vụ bắt buộc phải có.** |
| **Java SE required implementation** | Những dịch vụ/thuật toán và kích thước khóa tối thiểu mà *mỗi implementation tuân thủ phiên bản Java SE đó* phải hỗ trợ | Java SE 17 yêu cầu `MessageDigest`/`SHA-256` và `Cipher`/`AES/GCM/NoPadding` với khóa AES 128 bit | Có cơ sở kỳ vọng tính khả chuyển giữa các implementation **tuân thủ Java SE 17** trong cấu hình bình thường. |
| **Provider capability tại runtime** | Thuật toán thực tế do provider đang đăng ký cung cấp; có thể nhiều hơn mức tối thiểu | Provider `SUN` hỗ trợ `SHA3-256`; `SunJCE` hỗ trợ `ChaCha20-Poly1305` trong Oracle JDK 17 | Khả dụng trong runtime/provider tương ứng; phải kiểm tra khi triển khai sang môi trường khác. |

**Chú ý về từ “bắt buộc”:** Đặc tả yêu cầu *toàn bộ implementation Java SE* cung cấp dịch vụ tối thiểu; không yêu cầu **từng provider riêng lẻ** đều cung cấp mọi dịch vụ đó. Một provider có thể chỉ triển khai `Signature`, provider khác chỉ triển khai `Cipher`.

## 2. Cơ chế JCA: API ổn định, thuật toán được chọn qua provider

Ứng dụng gọi một **engine API** như `MessageDigest`, `Signature` hoặc `Cipher`; JCA tìm provider có triển khai phù hợp và ủy quyền thao tác cho phần hiện thực phía sau API (Service Provider Interface, thường gọi là **SPI**).

```text
Mã ứng dụng
    |
    | MessageDigest.getInstance("SHA-256")
    v
Engine API chuẩn Java SE (MessageDigest)
    |
    | tìm dịch vụ MessageDigest/SHA-256
    v
JCA provider selection
    |
    +---- Provider A: không cung cấp dịch vụ
    |
    +---- Provider B: cung cấp SHA-256 --> implementation/SPI
    |
    +---- Provider C: có thể cũng cung cấp SHA-256
```

- Không chỉ định provider: `MessageDigest.getInstance("SHA-256")` để framework tìm implementation trong các provider đã đăng ký theo quy tắc lựa chọn của runtime.
- Chỉ định provider: `MessageDigest.getInstance("SHA-256", "SomeProvider")` chỉ chấp nhận provider được nêu; nếu provider vắng mặt hoặc không cung cấp đúng dịch vụ thì thao tác thất bại, dù provider khác có thể hỗ trợ.
- `Security.getProviders()` cho biết các provider được đăng ký; `getProvider()` trên đối tượng engine cho biết provider thực tế được chọn. Provider như `SUN`, `SunJCE`, `SunRsaSign`, `SunEC` là tên triển khai cụ thể của một số bản JDK, **không phải tên provider bắt buộc của Java SE**.
- Provider có thể đi kèm JDK, là thư viện bên thứ ba, hoặc tích hợp hệ điều hành/HSM. “JDK hỗ trợ” không nhất thiết có nghĩa chính JDK tự viết mọi thuật toán đó.

Cần phân biệt thêm hai nguồn tài liệu: **Java Security Standard Algorithm Names** chuẩn hóa tên và liệt kê yêu cầu tối thiểu; **JDK Providers Documentation** mô tả dịch vụ được các provider của *một JDK cụ thể* triển khai.

## 3. Java SE 17 thực sự yêu cầu những gì?

Một số trường hợp điển hình trích theo mục **Security Algorithm Implementation Requirements** của Java SE 17:

| Engine/service | Mức tối thiểu được Java SE 17 yêu cầu | Phạm vi cần hiểu đúng |
| --- | --- | --- |
| `MessageDigest` | `SHA-1`, `SHA-256` | `SHA3-256` và `SHA-512` là các tên chuẩn, nhưng không có trong **danh sách tối thiểu** của engine này ở Java SE 17. |
| `Cipher` | `AES/GCM/NoPadding`, `AES/CBC/PKCS5Padding`, `AES/CBC/NoPadding`, `AES/ECB/NoPadding`, `AES/ECB/PKCS5Padding` với AES **128 bit**, cùng một số transformation DESede và RSA được liệt kê cụ thể | Yêu cầu AES-128 **không đồng nghĩa** mọi tổ hợp mode/padding hoặc mọi cỡ khóa AES đều bắt buộc. AES/ECB thuộc tập tương thích, không phải khuyến nghị bảo mật cho dữ liệu nhiều khối. |
| `Signature` | `SHA1withDSA`, `SHA256withDSA`, `SHA1withRSA`, `SHA256withRSA` | `RSASSA-PSS` có tên chuẩn và được nhiều JDK hỗ trợ, nhưng không nằm trong tập tối thiểu Java SE 17 ở đây. |
| `Mac` | `HmacSHA1`, `HmacSHA256` | Một tên HMAC khác xuất hiện trong danh mục standard names chưa chắc là bắt buộc. |
| `KeyGenerator` | `AES` (khóa 128 bit), `DESede` (168 bit), `HmacSHA1`, `HmacSHA256` | Không thể suy ra mọi cỡ khóa hoặc mọi thuật toán sinh khóa đều được bảo đảm. |
| `KeyStore` | `PKCS12` | `JKS`, `JCEKS` được biết đến và có thể có trong JDK cụ thể nhưng không phải định dạng tối thiểu được yêu cầu cho engine này. |
| `SecureRandom` | Phải có mặc định do implementation cung cấp; **không có tên thuật toán cụ thể nào bắt buộc** trong bảng yêu cầu | Không giả định mọi Java SE 17 đều có `SHA1PRNG`, `NativePRNG` hay `DRBG` chỉ từ việc lớp `SecureRandom` tồn tại. |

Bảng trên chỉ chọn những engine quan trọng để so sánh; đặc tả còn nêu yêu cầu với `KeyFactory`, `KeyPairGenerator`, `KeyAgreement`, `CertificateFactory`, `SSLContext` và các loại dịch vụ khác. Ví dụ: `KeyStore/PKCS12` và `Signature/SHA256withRSA` thuộc mức tối thiểu, trong khi provider được chọn để hiện thực chúng vẫn tùy runtime.

**Hai giới hạn quan trọng:**

1. “Bắt buộc hỗ trợ” là yêu cầu **khả năng tương thích**, không phải đánh giá thuật toán **an toàn cho dự án mới**. Các thuật toán cũ như SHA-1 hoặc DESede có thể xuất hiện trong danh sách bắt buộc để phục vụ tương thích; không vì thế mà nên chọn chúng cho thiết kế mật mã mới.
2. Có engine instance mới chỉ xác nhận tìm được implementation. Việc `init`, tạo khóa, ký, giải mã còn phụ thuộc kích thước/loại khóa, tham số, policy bảo mật, trạng thái token/HSM và các ràng buộc runtime.

## 4. Những gì một JDK có thể cung cấp thêm

Theo tài liệu **JDK Providers Documentation** của Oracle JDK 17:

- Provider `SUN` liệt kê nhiều `MessageDigest` như `SHA-224`, `SHA-384`, `SHA-512` và `SHA3-256`, ngoài `SHA-1`/`SHA-256` tối thiểu. Việc chúng có tên chuẩn hoặc có trong Oracle JDK 17 **không nâng chúng thành yêu cầu tối thiểu của mọi Java SE 17**.
- Provider `SunJCE` có các transformation `ChaCha20-Poly1305`, nhiều biến thể AES và các dịch vụ `Mac`, `KeyGenerator`, `SecretKeyFactory` khác. `ChaCha20-Poly1305` là ví dụ rõ: tên đã được chuẩn hóa, Oracle JDK 17 hỗ trợ, nhưng không có trong bảng `Cipher` tối thiểu Java SE 17.
- Provider `SunRsaSign` có `RSASSA-PSS` và các thuật toán chữ ký RSA khác. Tính sẵn có của `RSASSA-PSS` trong bản phân phối đang chạy cần kiểm tra riêng.
- `SUN` có `KeyStore/JKS`; `SunJCE` có `KeyStore/JCEKS`. Tên/định dạng này có trong hệ sinh thái JDK nhưng không thay thế hợp đồng `PKCS12` tối thiểu.

Dù cùng tên thuật toán, provider vẫn có thể khác nhau về tham số chấp nhận, hiệu năng, hỗ trợ phần cứng và cấu hình. Mở rộng của một JDK/provider chỉ trở thành **phụ thuộc của ứng dụng** nếu ta chủ động yêu cầu hoặc kiểm tra nó.

## 5. Thực hành: hỏi runtime thay vì đoán

Tạo file **`JcaAvailability.java`** với nội dung Java 17+ sau. Chương trình kiểm tra ba dịch vụ tối thiểu của Java SE 17, in provider thực sự được chọn và thử một digest có tên chuẩn nhưng không bắt buộc là `SHA3-256`.

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Signature;
import javax.crypto.Cipher;

public final class JcaAvailability {
    public static void main(String[] args) throws Exception {
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        Cipher aesGcm = Cipher.getInstance("AES/GCM/NoPadding");
        Signature rsa = Signature.getInstance("SHA256withRSA");

        System.out.println("Java SE 17 minimum: OK");
        System.out.println("SHA-256 provider: " + sha256.getProvider().getName());
        System.out.println("AES/GCM provider: " + aesGcm.getProvider().getName());
        System.out.println("SHA256withRSA provider: " + rsa.getProvider().getName());

        try {
            MessageDigest sha3 = MessageDigest.getInstance("SHA3-256");
            System.out.println("Optional SHA3-256: PRESENT (" +
                    sha3.getProvider().getName() + ")");
        } catch (NoSuchAlgorithmException e) {
            System.out.println("Optional SHA3-256: ABSENT");
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên):

```bash
javac --release 17 JcaAvailability.java
java JcaAvailability
```

**Ví dụ kết quả** trên Oracle JDK 17 với các provider mặc định (tên provider và dòng optional **có thể khác** trên runtime khác):

```text
Java SE 17 minimum: OK
SHA-256 provider: SUN
AES/GCM provider: SunJCE
SHA256withRSA provider: SunRsaSign
Optional SHA3-256: PRESENT (SUN)
```

**Cách diễn giải kết quả:**

- Nếu ba dòng bắt buộc được khởi tạo thành công, runtime hiện tại đáp ứng *những trường hợp vừa kiểm tra*. Chúng không phải một bài kiểm thử tuân thủ toàn bộ Java SE 17.
- Nếu `SHA3-256` báo `ABSENT`, **không được kết luận Java SE 17 bị thiếu API hoặc không tuân thủ đặc tả**; thuật toán này không thuộc mức tối thiểu Java SE 17.
- Nếu `getInstance` ném exception cho một dịch vụ vốn thuộc tập tối thiểu, cần xem lại bản JDK, provider đăng ký, cấu hình/policy và môi trường triển khai. Không nên tự động suy luận toàn bộ API Java SE đã biến mất.
- Ví dụ mới chỉ lấy **đối tượng engine**, chưa mã hóa hoặc ký dữ liệu. Đối với AES-GCM thật, phải dùng khóa hợp lệ, nonce/IV duy nhất phù hợp với khóa và xử lý authentication tag đúng cách; không tái sử dụng nonce với cùng khóa.

Để xem các provider đã cài và dịch vụ mà từng provider công bố, có thể dùng đoạn mã **minh họa đặt bên trong một phương thức**:

```java
for (java.security.Provider provider : java.security.Security.getProviders()) {
    System.out.println(provider.getName());
    for (java.security.Provider.Service service : provider.getServices()) {
        if (service.getType().equals("MessageDigest")) {
            System.out.println("  MessageDigest: " + service.getAlgorithm());
        }
    }
}
```

`Security.getAlgorithms("MessageDigest")` cũng liệt kê các tên digest được đăng ký trong runtime. Tuy nhiên, khi kiểm tra một **Cipher transformation** đầy đủ (algorithm/mode/padding), hãy thử `Cipher.getInstance("...")` thay vì chỉ so khớp chuỗi trong danh sách dịch vụ: provider có thể công bố tên cipher cơ sở và các mode/padding được hỗ trợ qua thuộc tính thay vì mọi transformation dưới dạng một entry độc lập.

## 6. Cách chọn API, tên thuật toán và provider trong ứng dụng

### Trường hợp A: cần chạy trên mọi implementation Java SE 17 tuân thủ chuẩn

Dùng **API công khai** và một thuật toán nằm trong **danh sách tối thiểu** của đúng Java SE 17. Ví dụ:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
Signature signature = Signature.getInstance("SHA256withRSA");
```

Đây là các **lời gọi minh họa**; chúng cần được đặt trong phương thức có xử lý exception, và `Cipher`/`Signature` phải `init` với khóa, tham số phù hợp trước khi xử lý dữ liệu. Không chỉ định tên provider nếu ứng dụng không có yêu cầu riêng về provider.

### Trường hợp B: muốn dùng thuật toán hiện đại/khả năng mở rộng ngoài tập tối thiểu

Ví dụ ứng dụng chọn `ChaCha20-Poly1305`, `SHA3-256` hoặc `RSASSA-PSS` vì yêu cầu giao thức hoặc thiết kế. Có thể dùng **cùng engine API chuẩn**, nhưng cần:

1. Ghi rõ **tên dịch vụ, tên thuật toán, tham số và phiên bản runtime/provider tối thiểu** mà ứng dụng yêu cầu.
2. Kiểm tra hỗ trợ trên **mọi môi trường đích**, tốt nhất lúc khởi động và trong kiểm thử tích hợp; thông báo cấu hình thiếu hỗ trợ một cách rõ ràng.
3. Khi có fallback, chỉ dùng fallback **được giao thức và chính sách bảo mật cho phép**. Không tự động “hạ cấp” sang thuật toán yếu hơn để tránh lỗi.
4. Kiểm thử cả `init`/thao tác thực tế, không dừng ở bước `getInstance`.

Nếu môi trường yêu cầu HSM, provider đã kiểm định hoặc tích hợp native cụ thể, việc chỉ định provider có thể là chủ ý hợp lý; lúc đó tên provider và quy trình cài/đăng ký là một phần của hợp đồng triển khai. Khi không có yêu cầu này, hard-code `"SUN"`, `"SunJCE"` hay `"SunRsaSign"` làm giảm khả chuyển.

### Trường hợp C: muốn bảo đảm transformation và tham số rõ ràng

Với `Cipher`, tên chỉ gồm thuật toán, ví dụ `Cipher.getInstance("AES")`, để provider quyết định mode/padding mặc định. Một số provider dùng ECB theo mặc định, dễ tạo thiết kế không an toàn cho dữ liệu nhiều khối. Hãy chọn **transformation đầy đủ** như `AES/GCM/NoPadding` và xử lý đúng nonce, tag và khóa. Sự tồn tại của tên chuẩn `AES` không bảo đảm mọi transformation hay mặc định an toàn như nhau.

## 7. Lỗi phổ biến và cách phân loại khi chẩn đoán

| Biểu hiện/nhận định | Vấn đề thật sự | Cách xử lý |
| --- | --- | --- |
| “`Cipher` là API Java SE nên mọi cipher đều chạy.” | Nhầm **engine API** với tập thuật toán bắt buộc. | Tra bảng yêu cầu tối thiểu theo phiên bản; nếu ngoài bảng, kiểm tra provider/runtime. |
| “Có trong **Standard Names** thì mọi JDK phải hỗ trợ.” | Nhầm **tên đã chuẩn hóa** với **implementation bắt buộc**. | Tìm tiếp mục **Security Algorithm Implementation Requirements**. |
| `NoSuchAlgorithmException` | Không tìm được implementation phù hợp cho yêu cầu hiện tại, hoặc yêu cầu thuật toán/provider không có. | Kiểm tra spelling/tên chuẩn, version, provider đã đăng ký và dịch vụ được hỗ trợ. |
| `NoSuchPaddingException` khi lấy `Cipher` | Padding được yêu cầu không được hỗ trợ cho transformation/provider đang chọn. | Dùng transformation chính xác, có hỗ trợ và phù hợp thiết kế. |
| `NoSuchProviderException` khi gọi overload có tên provider | Provider được chỉ định không được đăng ký. | Kiểm tra cấu hình cài provider hoặc bỏ ràng buộc provider nếu không cần. |
| `InvalidKeyException` hoặc `InvalidAlgorithmParameterException` khi `init` | Thuật toán có thể đã được tìm thấy, nhưng khóa/tham số không hợp lệ. | Xem cỡ khóa, loại khóa, IV/nonce, policy, HSM và yêu cầu của provider. |
| “Đã bắt buộc hỗ trợ SHA-1/DESede thì nên dùng trong dự án mới.” | Nhầm mục tiêu tương thích với đánh giá an toàn. | Chọn thuật toán/độ dài khóa theo tiêu chuẩn bảo mật hiện hành của hệ thống. |
| “`SHA-256` chạy với provider mặc định thì chắc chạy với `SunJCE`.” | Một provider riêng **không phải** toàn bộ tập provider của Java SE. | Dùng overload không chỉ định provider, trừ khi có yêu cầu thực sự. |

Một tình huống đặc biệt: chính sách như `jdk.tls.disabledAlgorithms` hoặc chính sách kiểm tra certificate có thể **hạn chế cách một thuật toán được sử dụng trong TLS/chứng chỉ** mà không có nghĩa engine đó đã bị xóa khỏi JCA. Vì vậy cần phân biệt *service availability*, *khả năng khởi tạo bằng key/tham số* và *quy tắc cho từng giao thức*.

## 8. Quy trình ra quyết định nhanh

1. **Xác định Java SE baseline** của ứng dụng, chẳng hạn Java SE 17; phân biệt phiên bản biên dịch (`--release 17`) với JDK/runtime thực sự khi chạy.
2. **Chọn engine API chuẩn** theo tác vụ (`MessageDigest`, `Cipher`, `Signature`, `Mac`, `KeyStore`...).
3. **Tra Standard Algorithm Names** để dùng tên đúng; sau đó **tra bảng Implementation Requirements** xem thuật toán/transformation/cỡ khóa đó có thuộc mức tối thiểu hay không.
4. **Nếu ngoài mức tối thiểu**, đọc tài liệu provider của bản JDK mục tiêu, dùng `getInstance` để kiểm tra trên runtime thực và kiểm thử thao tác với khóa/tham số thật.
5. **Ghi rõ dependency và chính sách xử lý khi thiếu**; không gắn cứng tên provider hoặc chọn fallback yếu chỉ vì tiện.
6. **Kiểm tra nhiều môi trường** nếu ứng dụng triển khai trên nhiều vendor JDK, OS, container, cấu hình provider hoặc HSM.

**Tự kiểm tra kiến thức:**

- Java SE 17 có API `MessageDigest`; liệu `SHA3-256` bắt buộc? **Không**. Tên chuẩn có tồn tại và Oracle JDK 17 có thể cung cấp, nhưng bảng tối thiểu chỉ nêu `SHA-1` và `SHA-256` cho `MessageDigest`.
- Java SE 17 yêu cầu `AES/GCM/NoPadding` với khóa 128 bit; liệu suy ra tất cả JDK phải hỗ trợ mọi cỡ khóa AES và mọi mode? **Không**.
- `KeyStore.getInstance("PKCS12")` và `KeyStore.getInstance("JKS")` có cùng tính khả chuyển theo Java SE 17? **Không**. `PKCS12` thuộc yêu cầu tối thiểu; `JKS` là một định dạng/triển khai thường có trong các JDK cụ thể.
- Một thuật toán có trong `SunJCE` có được dùng từ API `Cipher` chuẩn? **Có**, khi provider đã đăng ký và cung cấp transformation đó; việc dùng API chuẩn không biến thuật toán bổ sung thành bảo đảm của mọi implementation Java SE.

## Tài liệu gốc để đối chiếu

- [Java SE 17 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): đối chiếu phần **Standard Names** với **Security Algorithm Implementation Requirements**.
- [Java SE 17 — Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): engine API, SPI, provider selection và cách yêu cầu implementation.
- [Oracle JDK 17 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): danh sách provider, thuật toán và transformation của bản JDK được mô tả.
- [Java SE 17 — Signature API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): ví dụ API document nêu rõ những signature algorithm Java SE yêu cầu.
