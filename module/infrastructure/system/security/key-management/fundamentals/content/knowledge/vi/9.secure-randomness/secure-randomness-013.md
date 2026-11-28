# Nguồn random của nền tảng

## 1. Vì sao cần hiểu nguồn random của nền tảng?

**Nguồn random của nền tảng** là những cơ chế mà **hệ điều hành, runtime, phần cứng hoặc dịch vụ mật mã** cung cấp để tạo số/byte ngẫu nhiên. Với hệ thống bảo mật, điều quan trọng không chỉ là API có tên Random mà là **đường đi từ entropy đáng tin đến bộ sinh số ngẫu nhiên phục vụ mật mã (CSPRNG/DRBG)**.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nguồn random của nền tảng là nền móng của vòng đời khóa:

- Khi **tạo khóa**, nó cung cấp tính khó đoán cho AES DEK/KEK, HMAC key và private key.
- Khi **cấp phát**, hệ thống phải tránh rò vật liệu khóa và phân biệt nơi tạo khóa với nơi dùng khóa.
- Khi **sử dụng**, các thuật toán như AES-GCM và ECDSA có những yêu cầu khác nhau về nonce và bí mật tạm thời.
- Khi **xoay vòng**, phải tạo vật liệu khóa mới thực sự độc lập, không chỉ đổi alias.
- Khi **thu hồi/hủy**, nếu nguồn random từng lỗi, cần xác định những khóa và token có thể bị ảnh hưởng.
- Khi dùng **KMS/HSM, envelope encryption, IAM và kiểm toán**, phải hiểu ranh giới trách nhiệm giữa OS, JVM, ứng dụng và dịch vụ quản lý khóa.

**Tình huống:** Hai instance Java vô tình được khởi tạo bằng một PRNG tự chế với cùng seed. Chúng có thể sinh cùng DEK hoặc bearer token dù mọi phần còn lại của ứng dụng dùng AES-256 và HTTPS đúng. **Mật mã mạnh không thể sửa được secret dễ đoán hoặc bị trùng.**

~~~text
Nguồn entropy từ nền tảng
          |
          v
Thu thập / kiểm tra / conditioning
          |
          v
OS CSPRNG, runtime DRBG hoặc RNG trong HSM
          |
          v
API an toàn: SecureRandom / KeyGenerator / KMS / HSM
          |
          v
Key, token, nonce tùy yêu cầu của từng thuật toán
          |
          v
Key lifecycle + IAM + audit + ứng phó sự cố
~~~

## 2. Phân biệt entropy source, TRNG, CSPRNG và API

Các tầng dưới đây không đồng nghĩa:

| Thành phần | Bản chất | Trách nhiệm | Ví dụ |
|---|---|---|---|
| **Entropy source** | Nguồn bất định từ môi trường/phần cứng | Cung cấp entropy để khởi tạo hoặc làm mới trạng thái | Nhiễu phần cứng và các nguồn OS được đánh giá |
| **TRNG / hardware RNG** | Cơ chế lấy tín hiệu ngẫu nhiên từ hiện tượng vật lý | Tạo entropy hoặc bit ngẫu nhiên theo khả năng thiết bị | RNG tích hợp HSM/TPM hoặc thiết bị phần cứng |
| **Conditioning mechanism** | Thành phần xử lý nguyên liệu entropy thô | Giảm thiên lệch, kết hợp và chuẩn hóa dữ liệu theo thiết kế | Bộ xử lý entropy do OS/thiết bị quản lý |
| **CSPRNG / DRBG** | Bộ sinh bit giả ngẫu nhiên phục vụ mật mã | Mở rộng trạng thái bí mật đã được seed đúng thành các byte khó dự đoán | Kernel RNG, DRBG của provider |
| **System crypto API** | Giao diện để ứng dụng lấy byte phù hợp | Che giấu chi tiết hệ thống, xử lý trạng thái và lỗi | getrandom, BCryptGenRandom, SecRandomCopyBytes |
| **Runtime API** | Giao diện của ngôn ngữ hoặc thư viện | Chọn provider và sử dụng nguồn bên dưới | java.security.SecureRandom |
| **KMS/HSM API** | Giao diện quản lý/sử dụng khóa tập trung | Sinh/giữ vật liệu khóa, quản lý quyền và kiểm toán | GenerateKey, GenerateDataKey, HSM GenerateRandom |

Một bộ sinh **xác định** không nhất thiết không an toàn: DRBG được thiết kế để tạo đầu ra khó dự đoán từ **trạng thái bí mật đã được seed an toàn**. Điều đáng lo là seed có entropy thấp, thuật toán không dành cho mật mã, lộ trạng thái hoặc lỗi triển khai.

Ngược lại, dữ liệu **trông ngẫu nhiên** không chứng minh độ an toàn. Bộ đếm hoặc PRNG có seed công khai vẫn có thể tạo chuỗi byte qua được nhiều kiểm tra phân bố nhưng bị đối thủ dự đoán.

## 3. Entropy đến từ đâu?

**Entropy** đo mức độ bất định của nguồn, không phải số bit được in ra. Một đầu ra 256 bit tạo từ timestamp chỉ có độ khó đoán tương ứng với **khoảng thời gian thực sự chưa biết**, không tự có 256 bit entropy.

Các hệ điều hành và thiết bị mật mã có thể thu thập entropy từ nhiều tín hiệu:

- Nhiễu phần cứng hoặc hiện tượng vật lý được bộ sinh ngẫu nhiên hỗ trợ.
- Nguồn do kernel nhận biết và quản lý theo nền tảng.
- Tín hiệu từ phần cứng bảo mật hoặc thiết bị chuyên dụng khi được tích hợp đúng.
- Những nguồn bổ sung được thu thập và trộn theo cơ chế đã được thiết kế, kiểm tra và đánh giá.

Không nên giả định mọi hệ điều hành đều dùng đúng một danh sách nguồn hay thuật toán. **Cấu hình kernel, thiết bị và phiên bản nền tảng có thể thay đổi**, trong khi hợp đồng API dành cho ứng dụng mới là điểm cần dựa vào.

### 3.1. Hai thuộc tính quan trọng của entropy

- **Shannon entropy** mô tả bất định trung bình của phân bố.
- **Min-entropy** phụ thuộc vào xác suất của kết quả dễ đoán nhất và thường hữu ích khi đánh giá nguồn bí mật theo hướng bảo thủ.

Với một không gian gồm 1.000.000 seed **đều xác suất**, độ bất định lý tưởng chỉ gần:

\[
\log_2(1.000.000) \approx 19{,}93\ \text{bit}.
\]

Dù gọi SHA-256 trên mỗi seed để tạo ra 256 bit, đối thủ vẫn có thể thử toàn bộ khoảng một triệu ứng viên. **Hàm hash không bổ sung entropy độc lập.**

### 3.2. Nguồn entropy cần được kiểm tra, không tự đánh giá bằng mắt

Một nguồn TRNG có thể bị thiên lệch, lỗi phần cứng, thay đổi theo nhiệt độ hoặc môi trường. Các thiết bị và hệ thống cần **health test**, xử lý lỗi và kiểm chứng thiết kế theo tiêu chuẩn phù hợp.

**Kiểm tra thống kê đơn lẻ không chứng nhận một bộ sinh phù hợp cho mật mã**: một PRNG xác định biết trước seed vẫn có thể vượt qua nhiều phép kiểm tra tần suất bit. Đánh giá đúng phải kết hợp tính chất nguồn entropy, thuật toán DRBG, trạng thái seed/reseed, triển khai và threat model.

## 4. Nguồn random ở các hệ điều hành

### 4.1. Linux: kernel RNG, getrandom và thiết bị ngẫu nhiên

Trong Linux, các ứng dụng thường sử dụng **kernel cryptographic RNG** thông qua API hệ điều hành hoặc runtime.

| Giao diện | Mục đích/đặc điểm | Hướng sử dụng |
|---|---|---|
| **getrandom(2)** | API lấy byte từ bộ sinh của kernel; hành vi chờ và cờ phụ thuộc trạng thái khởi tạo/loại yêu cầu | Thường phù hợp làm nền cho thư viện mật mã hiện đại |
| **/dev/urandom** | Thiết bị cấp byte từ cơ chế RNG của kernel; dùng rộng rãi cho ứng dụng mật mã sau khi kernel RNG khởi tạo đúng | Thường thích hợp qua API/thư viện hệ thống |
| **/dev/random** | Giao diện lịch sử có ngữ nghĩa về blocking/entropy khác theo phiên bản kernel | Không mặc định an toàn hơn /dev/urandom cho ứng dụng thông thường |
| **getentropy(3)** nếu có | API thư viện trả một lượng byte ngẫu nhiên mỗi lần gọi theo hợp đồng của nền tảng | Dùng qua thư viện chuẩn được hỗ trợ thay vì tự đọc tùy tiện |

**Điểm mấu chốt:** đối với ứng dụng, **trạng thái khởi tạo an toàn của kernel RNG** quan trọng hơn suy nghĩ rằng một tên thiết bị ngẫu nhiên luôn tốt hơn tên khác. Trên những Linux hiện đại, lấy ngẫu nhiên mật mã qua giao diện chuẩn của OS là lựa chọn phù hợp; không cần xây một "entropy collector" riêng từ PID, thời gian hoặc lịch sử I/O.

Về **early boot**, nhiều cơ chế có cách chờ đến khi RNG kernel được khởi tạo phù hợp. Không được bỏ qua lỗi hoặc sử dụng timestamp làm fallback nếu API báo chưa sẵn sàng.

### 4.2. Windows: hệ mật mã CNG

Trên Windows hiện đại, ứng dụng native có thể yêu cầu byte ngẫu nhiên phục vụ mật mã qua **Cryptography Next Generation (CNG)**, chẳng hạn API **BCryptGenRandom** trong cấu hình thích hợp. Hệ thống và thư viện mật mã quản lý cơ chế sinh bit bên dưới.

Ứng dụng Java thường nên sử dụng **SecureRandom của provider được cấu hình** thay vì tự gọi CNG bằng native code. Không mặc định rằng một tên thuật toán SecureRandom nhất định luôn ánh xạ chính xác đến một API Windows trên mọi bản JDK.

### 4.3. macOS và hệ sinh thái Apple

Các nền tảng Apple cung cấp các giao diện random được hỗ trợ, ví dụ **SecRandomCopyBytes** trong Security framework. Một số API hệ thống khác có thể được cung cấp tùy phiên bản và môi trường.

Tương tự Linux và Windows, ứng dụng nên sử dụng **API mật mã được hỗ trợ** hoặc thư viện/runtime dựa vào chúng. Không lấy số mili giây hệ thống, PID hoặc đầu ra PRNG thống kê để thay thế nguồn bí mật.

### 4.4. Android và môi trường di động

Android có **SecureRandom** qua runtime Java/Android và các provider phù hợp; nền tảng dựa vào cơ chế an toàn của hệ điều hành và thư viện mật mã ở phiên bản được hỗ trợ.

Lưu ý:

- Không dùng **java.util.Random** tạo khóa, token hoặc secret.
- Tránh tự seed một PRNG bằng thông tin thiết bị hoặc timestamp.
- Khi yêu cầu private key **khó xuất khỏi thiết bị**, cân nhắc API quản lý khóa của nền tảng (ví dụ Android Keystore) với khả năng bảo vệ tùy thiết bị.
- Không mặc định mọi thiết bị Android có mức bảo vệ hardware-backed giống nhau; xem khả năng và thuộc tính thực tế.

Các API Apple cho keychain/secure enclave và Android Keystore có vai trò **bảo vệ và sử dụng khóa**; điều này bổ sung cho nguồn random, không đồng nghĩa mọi khóa đều được lưu trong phần cứng.

### 4.5. Bảng đối chiếu nền tảng

| Nền tảng | Ví dụ giao diện crypto-random native | Lời khuyên cho ứng dụng Java |
|---|---|---|
| **Linux** | getrandom, /dev/urandom sau khởi tạo thích hợp | Dùng SecureRandom/provider hỗ trợ OS |
| **Windows** | BCryptGenRandom / CNG | Dùng SecureRandom/provider được phê duyệt |
| **macOS/iOS** | SecRandomCopyBytes và API hệ thống được hỗ trợ | Dùng provider/runtime đã được đánh giá cho nền tảng |
| **Android** | SecureRandom và cơ chế mật mã của Android | Dùng SecureRandom, Android Keystore nếu cần bảo vệ khóa |
| **HSM chuyên dụng** | API RNG/key generation theo PKCS#11 hoặc nhà cung cấp | Chỉ định provider/connector và chính sách được chứng nhận nếu cần |

Bảng trên **không phải cam kết nội bộ** của mọi phiên bản JVM hoặc hệ điều hành. Đường đi từ Java tới nguồn random bên dưới phụ thuộc **JDK, provider, cấu hình bảo mật và môi trường triển khai**.

## 5. SecureRandom trong Java: API, provider và nguồn bên dưới

**java.security.SecureRandom** là giao diện lấy byte ngẫu nhiên phục vụ mật mã trong **Java Cryptography Architecture (JCA)**.

~~~java
import java.security.SecureRandom;

SecureRandom rng = new SecureRandom();
byte[] secret = new byte[32];      // 256 bit độ dài
rng.nextBytes(secret);
~~~

Điều Java bảo đảm ở mức API là ứng dụng làm việc với một đối tượng SecureRandom do một **security provider** cung cấp. Những chi tiết như **thuật toán, seed, reseed, nguồn entropy, tính chặn và yêu cầu chứng nhận** phụ thuộc provider.

### 5.1. Các cách khởi tạo phổ biến

| Cách gọi | Ý nghĩa | Cảnh báo |
|---|---|---|
| **new SecureRandom()** | Chọn một triển khai SecureRandom từ provider được đăng ký/cấu hình | Không mặc định provider và thuật toán giống nhau trên mọi host |
| **SecureRandom.getInstance("DRBG")** | Yêu cầu dịch vụ SecureRandom mang tên DRBG nếu provider hỗ trợ | Có thể không khả dụng hoặc có khác biệt cấu hình giữa JDK |
| **SecureRandom.getInstanceStrong()** | Chọn thuật toán theo cấu hình strong của Java security properties | Có thể có đặc tính block/độ trễ khác; không bắt buộc cho mọi request |
| **rng.nextBytes(bytes)** | Sinh byte ngẫu nhiên theo provider | Cần cân nhắc độ dài, số lần gọi và vòng đời secret |
| **rng.generateSeed(n)** | Yêu cầu seed bytes theo cơ chế được provider hỗ trợ | Không phải thao tác cần gọi trước mỗi lần nextBytes; có thể chậm/chặn tùy provider |
| **rng.setSeed(seed)** | Cung cấp seed bổ sung theo ngữ nghĩa của provider | Không dùng timestamp/chuỗi cố định làm chiến lược khởi tạo entropy |

**Không tự cho rằng cần gọi setSeed(System.currentTimeMillis()) để SecureRandom tốt hơn.** Cách xử lý seed do provider quyết định; một giá trị dễ đoán không tạo entropy hữu ích. Để provider/OS quản lý seed theo cơ chế được hỗ trợ, trừ khi chính sách có hướng dẫn cụ thể và được đánh giá.

### 5.2. Đừng "khóa cứng" provider khi không cần thiết

Có thể gặp các thuật toán/provider như **NativePRNG, DRBG, Windows-PRNG** hoặc những tên khác tùy môi trường. Việc chỉ định cứng một tên không phổ biến có thể khiến ứng dụng không chạy khi chuyển nền tảng.

Có hai nhu cầu khác nhau:

- **Ứng dụng đa nền tảng thông thường:** dùng API SecureRandom được hỗ trợ, kiểm tra môi trường và lựa chọn provider khi triển khai.
- **Ứng dụng tuân thủ yêu cầu cụ thể** như nhà cung cấp đã được thẩm định, thuật toán DRBG hoặc HSM: cấu hình provider và policy rõ ràng; kiểm tra khi start-up để fail-closed nếu provider không phù hợp.

Không nên chỉ in tên thuật toán rồi tuyên bố hệ thống đã có **256 bit entropy**. Metadata provider giúp vận hành, nhưng không thay kết quả đánh giá thiết kế nguồn random.

## 6. Ví dụ Java đầy đủ: lấy random từ nền tảng và sinh khóa AES

Đoạn mã dưới đây mô tả **một chương trình Java 17+** sử dụng SecureRandom và KeyGenerator. Chương trình chỉ báo metadata về provider, **không in khóa hay token**.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class PlatformRandomnessExample {
    private static final SecureRandom RNG = new SecureRandom();

    public static void main(String[] args) throws Exception {
        // 1. Quan sát provider để hỗ trợ kiểm tra môi trường.
        //    Provider metadata không chứng minh mức entropy cụ thể.
        System.out.println("RNG algorithm: " + RNG.getAlgorithm());
        System.out.println("RNG provider: " + RNG.getProvider().getName());

        // 2. Sinh 32 byte ngẫu nhiên cho token/secret.
        byte[] tokenSecret = new byte[32];
        RNG.nextBytes(tokenSecret);

        // 3. Sinh AES-256 key; provider thực hiện key generation.
        KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
        aesGenerator.init(256, RNG);
        SecretKey dataEncryptionKey = aesGenerator.generateKey();

        // 4. Sinh một EC key pair P-256 cho chữ ký ECDSA.
        KeyPairGenerator ecGenerator = KeyPairGenerator.getInstance("EC");
        ecGenerator.initialize(
            new ECGenParameterSpec("secp256r1"), RNG
        );
        KeyPair signingKeys = ecGenerator.generateKeyPair();

        // 5. Sinh nonce 96 bit cho một lần AES-GCM encryption.
        //    Không dùng nonce này lại với cùng AES key ở lần encrypt khác.
        byte[] gcmNonce = new byte[12];
        RNG.nextBytes(gcmNonce);

        if (dataEncryptionKey == null ||
                signingKeys.getPrivate() == null) {
            throw new IllegalStateException("Key generation failed");
        }

        System.out.println("Generated secrets without printing them");

        // Chỉ giảm phơi lộ một mảng có thể kiểm soát.
        Arrays.fill(tokenSecret, (byte) 0);
    }
}
~~~

**Phân tích:**

1. **RNG.getAlgorithm()** và **getProvider()** cho biết runtime đã chọn provider gì. Chúng không phải phép kiểm định entropy, nhưng giúp phát hiện sai cấu hình deployment.
2. **KeyGenerator("AES")** giúp tạo AES key đúng kích thước bằng cơ chế nhà cung cấp; không biến một password yếu thành AES key.
3. **KeyPairGenerator("EC")** chọn generator cho cặp khóa elliptic; **secp256r1** chọn curve P-256. Private key không nên được xuất hoặc log trong sản xuất.
4. **Token secret 32 byte** có độ dài 256 bit; mức khó đoán thực tế phụ thuộc SecureRandom/provider được seed đúng, và còn phải giữ bí mật token.
5. **GCM nonce 12 byte** là giá trị cho một lần mã hóa; sinh ngẫu nhiên không chứng minh không thể va chạm. Trong hệ thống nhiều request phải xét giới hạn tổng lượt mã hóa dưới cùng DEK và chiến lược uniqueness.
6. **Arrays.fill** không xóa được mọi bản sao của secret trong JVM hoặc provider. Với key material cần bảo vệ dài hạn, ưu tiên KMS/HSM hoặc kho khóa thích hợp.

### 6.1. Vì sao không dùng java.util.Random?

Đoạn sau chỉ để chỉ ra một lỗi thiết kế:

~~~java
// KHÔNG AN TOÀN để sinh key, session token hoặc HMAC secret.
java.util.Random random =
    new java.util.Random(System.currentTimeMillis());
byte[] key = new byte[32];
random.nextBytes(key);
~~~

Giá trị thời gian dễ đoán và PRNG này không được thiết kế cho bảo mật. Một attacker biết thời gian tạo khóa gần đúng có thể tìm kiếm seed hoặc dự đoán chuỗi đầu ra. **Hash mảng key sau đó cũng không khắc phục thiếu entropy.**

### 6.2. Tránh phát tán secret ở tầng ứng dụng

Cũng cần tránh:

- In byte khóa, DRBG state, seed hoặc token ra log để debug.
- Trả private key trong exception, telemetry hoặc endpoint chẩn đoán.
- Lưu khóa cố định trong source code, image hoặc cấu hình không được bảo vệ.
- Giữ key material dạng rõ trong RAM lâu hơn yêu cầu.
- Dùng cùng bí mật cho nhiều mục đích mà không tách khóa theo chính sách.

## 7. Hardware RNG: CPU, TPM và HSM

**Hardware RNG** có thể cung cấp entropy hoặc byte ngẫu nhiên dựa trên cơ chế phần cứng. Tuy nhiên, tồn tại nhiều loại và không thể đánh đồng chúng.

| Nguồn/thiết bị | Vai trò | Lưu ý |
|---|---|---|
| **CPU RNG instructions** | Cung cấp random/seed data theo cơ chế của CPU | Chất lượng, trạng thái lỗi và cách OS trộn/tiếp nhận tùy nền tảng |
| **TPM (Trusted Platform Module)** | Có thể hỗ trợ RNG và bảo vệ một số khóa/các phép đo trạng thái nền tảng | Không thay cho thiết kế KMS/HSM hoặc quản trị IAM |
| **HSM** | Có thể sinh khóa và random trong miền thiết bị bảo mật | Cần đánh giá entropy, thiết bị, chứng nhận, key policy và audit |
| **Hardware TRNG chuyên dụng** | Tạo entropy từ hiện tượng vật lý | Cần health tests, conditioning và xử lý lỗi |
| **OS RNG** | Tập hợp và cung cấp CSPRNG chuẩn cho tiến trình | Thường là lựa chọn mặc định tốt cho ứng dụng |

Ví dụ, những CPU hỗ trợ các lệnh như **RDRAND/RDSEED** có thể đóng góp vào hệ thống nguồn ngẫu nhiên, nhưng ứng dụng **không nên tự phụ thuộc hoàn toàn vào một lời gọi lệnh CPU** mà bỏ qua hợp đồng của OS/provider và xử lý lỗi. Không phải mọi CPU cung cấp cùng tính chất hay khả năng.

Trong thiết kế nhiều lớp, OS có thể kết hợp nhiều nguồn theo quy trình của kernel; HSM lại có cơ chế seed và kiểm tra riêng. **Số lượng nguồn không tự chứng minh tổng entropy** nếu các nguồn tương quan, bị lỗi hoặc cùng phụ thuộc một thành phần.

## 8. KMS và dịch vụ cloud: ai chịu trách nhiệm sinh khóa?

Một nền tảng cloud có thể cung cấp **KMS**, **HSM chuyên dụng**, **API tạo random bytes**, **API tạo khóa** hoặc **API tạo data key**. Các tên API cụ thể khác nhau theo nhà cung cấp.

| Hoạt động | Ý nghĩa | Câu hỏi cần hỏi |
|---|---|---|
| **GenerateKey** | Tạo một key được dịch vụ quản lý | Thuật toán, key usage, key origin, export policy và quyền |
| **GenerateDataKey** | Tạo DEK và thường trả dạng bảo vệ cùng tùy chọn plaintext cho ứng dụng, tùy API | Plaintext DEK có bị log/cache và được xóa giảm thiểu không? |
| **GenerateRandom** | Yêu cầu dịch vụ trả random bytes theo API hỗ trợ | Nguồn, giới hạn kích thước, kiểm soát quyền và độ sẵn sàng? |
| **Sign / Verify** | Thực hiện chữ ký số bằng khóa phù hợp | Private key có non-exportable? Ai được Sign và audit như thế nào? |
| **Wrap / Unwrap** | Bảo vệ/giải bọc DEK bằng KEK | Thuật toán wrap, key ID/version, AAD/context và quyền? |

**KMS không tự làm mạnh một khóa yếu được ứng dụng import.** Nếu ứng dụng tạo DEK từ password dễ đoán rồi import vào HSM, vật liệu khóa ấy vẫn dễ đoán. Chính sách cần phân biệt **key generated inside trusted boundary** với **key imported by caller**.

### 8.1. Đường đi của DEK trong envelope encryption

~~~mermaid
flowchart TD
    R["OS CSPRNG hoặc KMS/HSM RNG"] --> D["DEK bí mật"]
    D --> A["AES-GCM encrypt dữ liệu"]
    P["Plaintext"] --> A
    A --> C["Ciphertext + nonce + tag"]
    K["KMS giữ KEK"] --> W["Wrap DEK"]
    D --> W
    W --> E["Encrypted DEK"]
    C --> S["Lưu ciphertext & metadata"]
    E --> S
    M["Key ID/version + AAD/context"] --> S
~~~

Nếu KMS tạo cả DEK và encrypted DEK, ứng dụng cần hiểu chính xác **KMS có xuất DEK dạng rõ cho ứng dụng hay không** và trách nhiệm giảm thời gian tồn tại của bản rõ. Nếu ứng dụng tự dùng DEK trong AES-GCM, nó vẫn phải đảm bảo **nonce uniqueness** theo DEK.

Chuyển KEK sang phiên bản mới và **rewrap** DEK thường không đòi hỏi mã hóa lại toàn bộ dữ liệu khi KEK chưa bị lộ; nhưng **nếu DEK bị lộ hoặc AES-GCM nonce reuse**, cần đánh giá việc sinh DEK mới và mã hóa lại dữ liệu liên quan.

### 8.2. Tính sẵn sàng và fail-safe

Gọi KMS/HSM tạo khóa có thể gặp lỗi mạng, quota, quyền, thiết bị hoặc timeout. **Không tạo một khóa bằng java.util.Random chỉ để không làm gián đoạn dịch vụ.**

Tùy threat model, ứng dụng có thể:
- Từ chối thao tác cần secret nếu không có nguồn random hợp lệ.
- Dùng một CSPRNG cục bộ đã được phê duyệt làm đường dự phòng **chỉ nếu kiến trúc cho phép** và vòng đời khóa được kiểm soát.
- Xếp hàng hoặc thử lại theo chính sách mà không lặp nonce, key material hoặc ghi log bí mật.

Fail-safe là quyết định kiến trúc cần thử nghiệm trước, không phải đoạn catch lỗi sinh khóa tùy tiện.

## 9. Nguồn random trong container, VM và Kubernetes

**Container không đồng nghĩa có một entropy source riêng**. Nhiều container thường chia sẻ cơ chế RNG của kernel host hoặc cơ chế được nền tảng ảo hóa cung cấp. Nhưng ứng dụng Java trong container vẫn có thể mắc lỗi nếu **tự quản lý seed hoặc snapshot trạng thái bộ sinh**.

Các tình huống cần phân tích:

| Sự kiện | Nguy cơ |
|---|---|
| **Clone image** | Secret bị hard-code trong image sẽ giống nhau ở mọi bản sao |
| **Fork/preload process** | Trạng thái PRNG tự chế có thể bị sao chép nếu không có cơ chế an toàn |
| **VM snapshot/restore** | DRBG hoặc counter có thể quay về trạng thái cũ tùy nền tảng |
| **Autoscaling nhiều pod** | Nếu mỗi pod tự khởi tạo từ cùng seed cố định, secret/nonce có thể lặp |
| **Cold start/early boot** | OS RNG có thể chưa sẵn sàng tùy môi trường |
| **Failover/restore DB** | Bộ đếm nonce AES-GCM có thể bị khôi phục về giá trị đã dùng |
| **Đổi node/provider** | Thuật toán SecureRandom hoặc chính sách FIPS có thể thay đổi |

### 9.1. Ví dụ nguy hiểm với snapshot

~~~text
VM A được snapshot khi PRNG tự chế ở trạng thái S
             |
          Restore
           /    \
          v      v
      VM A1      VM A2
      state S    state S
          |      |
    token T1    token T1 (trùng nếu không có bảo vệ)
~~~

Không khẳng định **mọi bản clone VM sẽ trùng token**. OS CSPRNG hiện đại có thể có biện pháp reseed/fork safety; cần kiểm tra hành vi cụ thể của hypervisor, kernel, JDK và provider.

Đối với **nonce counter**, dù CSPRNG đã an toàn, restore một cơ sở dữ liệu lưu high-water mark cũ vẫn có thể làm cấp lại nonce dưới cùng AES key. Đó là lỗi **quản lý trạng thái nonce**, phải xử lý độc lập với RNG.

### 9.2. Thiết kế phòng ngừa

- Dựa vào OS CSPRNG/provider được phê duyệt, không tự seed từ pod name, hostname hoặc PID.
- Không bake **key, token, seed** vào image hoặc snapshot có thể nhân bản.
- Với DRBG tùy biến được phép, sử dụng cơ chế **fork/restore/reseed** đã được tài liệu hóa; không tự chế.
- Nếu phát hiện restore khiến trạng thái nonce không còn tin cậy, **ngừng encrypt bằng DEK liên quan và chuyển khóa** theo kế hoạch.
- Giám sát nguồn RNG và quản lý version/provider khi migrate node, JDK hoặc cấu hình HSM.

## 10. Nonce, salt, token và key: yêu cầu random khác nhau

Một lỗi thiết kế phổ biến là gọi chung mọi đầu vào là "random" mà không quan tâm mục đích:

| Đối tượng | Cần khó đoán? | Cần duy nhất? | Cần bí mật? |
|---|---|---|---|
| **AES DEK / KEK** | **Có** | Khóa độc lập theo yêu cầu thiết kế | **Có** |
| **Private signing key** | **Có** | Phù hợp quy trình tạo và phạm vi khóa | **Có** |
| **HMAC secret** | **Có** | Phân tách theo mục đích/ngữ cảnh | **Có** |
| **Bearer token** | **Có** | Tránh trùng/đụng định danh token theo thiết kế | **Có** |
| **Password salt** | Không nhất thiết khó đoán sau khi công bố | Nên ngẫu nhiên, thường riêng từng bản ghi | **Không** |
| **AES-GCM nonce** | Không nhất thiết | **Bắt buộc không trùng với cùng key** | Không |
| **ECDSA per-signature k** | Phải bí mật/khó khai thác, hoặc dẫn xuất xác định an toàn | Không tái sử dụng sai giữa các chữ ký | **Có** |
| **Request ID chống replay** | Tùy giao thức và mô hình đe dọa | Cần không trùng trong miền áp dụng | Không nhất thiết |
| **HKDF salt/info** | Tùy thiết kế chuẩn | Tùy giao thức; không thay input entropy | Không nhất thiết |

**Quan trọng:** AES-GCM nonce được sinh từ CSPRNG chỉ đạt **tính duy nhất theo xác suất**. Nếu hệ thống có lượng encrypt lớn với cùng DEK, cần tính giới hạn theo thuật toán hoặc dùng chiến lược cấp phát nonce xác định đã được chứng minh không trùng.

Nếu cùng một nonce được dùng dưới **hai DEK độc lập thực sự**, điều đó không tự vi phạm GCM; phạm vi uniqueness theo key material. Nhưng hai key alias trỏ **cùng vật liệu khóa** không tạo hai phạm vi độc lập.

## 11. Quy trình chọn nguồn random khi thiết kế hệ thống Java

Có thể dùng bảng quyết định sau:

| Nhu cầu | Lựa chọn phù hợp thường gặp | Kiểm soát bổ sung |
|---|---|---|
| **Token API/session** | SecureRandom từ provider được phê duyệt | Độ dài, scope, TTL, không log/token leakage |
| **AES DEK tạo trong ứng dụng** | KeyGenerator với SecureRandom hoặc API được hỗ trợ | KMS wrapping, key version, hạn chế plaintext |
| **AES KEK dùng chung** | Key generation và lưu trong KMS/HSM | IAM, rotation, audit, non-exportable nếu phù hợp |
| **ECDSA/Ed25519 signing key** | KeyPairGenerator/provider hoặc HSM | Tham số thuật toán, key usage, kiểm soát Sign |
| **HMAC secret** | CSPRNG/KMS được phê duyệt | Phân tách purpose, key rotation, chính sách Verify |
| **Password verifier** | Salt từ CSPRNG; Argon2id/scrypt hoặc KDF phù hợp | Work factor, chống DoS, MFA, rate limiting |
| **Nonce AES-GCM** | CSPRNG 96 bit trong giới hạn hoặc counter duy nhất | Không trùng theo DEK, xử lý restart/multiwriter |
| **Khóa trong môi trường tuân thủ** | Provider/HSM/KMS được phép theo policy | Đánh giá cấu hình, thuật toán, chứng nhận, audit |

### 11.1. Câu hỏi cần chốt trước khi phát hành

1. **Ứng dụng tạo key ở đâu?** OS/JVM hay KMS/HSM?
2. **Runtime dùng provider nào?** Có bị thay sau nâng cấp JDK/node không?
3. **Entropy được đảm bảo theo cam kết nào?** OS/provider/thiết bị có tài liệu đánh giá không?
4. **Lỗi nguồn random được xử lý ra sao?** Có fallback không an toàn không?
5. **Secret bị xuất ở những nơi nào?** RAM, log, backup, image, secret store và API?
6. **Khi rotate, vật liệu khóa có thực sự đổi?** Alias/version có khớp key material không?
7. **Nonce và token có quy tắc riêng?** Duy nhất, khó đoán và thời gian tồn tại được áp dụng đúng chưa?
8. **Có kịch bản clone/restore/restart không?** Trạng thái RNG, nonce counter và phiên cũ được xử lý thế nào?

## 12. Quản lý vòng đời khóa gắn với nguồn random

~~~mermaid
flowchart LR
    A["Nguồn entropy / CSPRNG được phê duyệt"] --> B["Generate key material"]
    B --> C["Cấp phát / lưu trong KMS-HSM"]
    C --> D["Dùng key theo IAM + key usage"]
    D --> E["Giám sát và audit"]
    E --> F["Rotate: tạo vật liệu mới"]
    F --> D
    D --> G["Revoke / disable khi rủi ro"]
    G --> H["Migrate dữ liệu/niềm tin"]
    H --> I["Hủy sau khi xử lý phụ thuộc"]
~~~

| Giai đoạn | Kiểm tra liên quan nguồn random |
|---|---|
| **Generation** | Có dùng CSPRNG/KMS/HSM phù hợp, entropy và tham số thuật toán đủ mạnh? |
| **Provisioning** | Secret truyền qua kênh xác thực, không lộ vào CI/log/image? |
| **Storage** | Private key/DEK/KEK và bản sao lưu được bảo vệ; seed/state không bị phơi lộ? |
| **Usage** | Token/nonce/k của thuật toán được tạo hoặc dẫn xuất đúng cách? |
| **Rotation** | Sinh key mới thực sự, không chỉ đổi tên/version; kiểm tra RNG đang khỏe? |
| **Revocation** | Nếu RNG từng lỗi, xác định các key và hiện vật bị ảnh hưởng? |
| **Destruction** | Hủy key và bản sao theo chính sách mà không làm mất dữ liệu hợp lệ ngoài ý muốn? |

**Reseed khác rotation.** Reseed cập nhật trạng thái bộ sinh, không biến những khóa yếu đã phát hành thành khóa mạnh. Nếu phát hiện một thời kỳ RNG không đáng tin, phải xem xét thay key và xử lý dữ liệu/chữ ký/token đã sử dụng các key đó.

## 13. Kiểm toán, giám sát và kiểm thử nguồn random

### 13.1. Nên quan sát những gì?

- Provider/algorithm và phiên bản runtime được cấu hình (metadata vận hành).
- Những thay đổi policy, key origin, tạo khóa mới, import khóa và rotation.
- Sự kiện lỗi của OS RNG, HSM hoặc API KMS khi có dữ liệu quan sát đáng tin.
- Đường thực thi phải từ chối tạo secret nếu không có nguồn được phê duyệt.
- Sự kiện clone/restore/rollback và các ảnh hưởng đến counter/secret.
- Lưu lượng GenerateKey/GenerateDataKey, danh tính caller, key ID/version và kết quả.
- Bất thường trong cấp phát token, sự kiện đăng nhập, sign hoặc decrypt.

**Không log raw entropy, seed, CSPRNG/DRBG state, private key, DEK plaintext, token hay secret HMAC.** Việc đưa những dữ liệu đó vào telemetry có thể làm mất chính tính bí mật mà nguồn random đang bảo vệ.

### 13.2. Ma trận kiểm thử gợi ý

| Trường hợp | Kỳ vọng |
|---|---|
| Tạo DEK trong ứng dụng | Dùng CSPRNG/provider được phê duyệt, không dùng Random |
| Sinh token | Token dài đúng chính sách, không lộ trong log hoặc response sai chỗ |
| Provider không đáp ứng policy | Ứng dụng fail-closed, không dùng PRNG yếu |
| Chuyển node/JDK | Kiểm tra provider và thuộc tính RNG thực tế |
| Early boot OS RNG chưa sẵn sàng | Không phát hành secret từ fallback dễ đoán |
| Cấp quyền KMS không hợp lệ | GenerateKey/GenerateDataKey bị từ chối, có audit |
| Restore/clone | Kiểm tra thiết kế không lặp token/nonce do state bị khôi phục |
| Nhiều worker dùng một DEK | Kiểm tra nonce uniqueness trên tổng lưu lượng |
| KMS timeout | Không tự dùng java.util.Random hoặc hash(timestamp) làm key |
| RNG báo lỗi vận hành | Dừng cấp secret mới theo fail-safe policy |
| Rotation sau sự cố RNG | Sinh key mới từ nguồn an toàn, chuyển đúng dữ liệu/niềm tin |
| Audit | Truy vết key ID và caller, không có key material hay DRBG state |

**Đừng kết luận RNG đủ mạnh chỉ vì một triệu byte trông đều hoặc một nghìn khóa không trùng.** Các kiểm tra thống kê có thể phát hiện lỗi triển khai, nhưng sự an toàn mật mã cần bằng chứng về entropy source, DRBG, cấu hình, cập nhật và threat model.

## 14. Các sai lầm phổ biến

| Sai lầm | Hệ quả | Phòng tránh |
|---|---|---|
| Dùng java.util.Random cho secret | Đầu ra có thể bị dự đoán | Dùng SecureRandom hoặc KMS/HSM |
| Tự seed SecureRandom bằng timestamp và coi là tăng bảo mật | Nhầm lẫn về entropy, cấu hình không được kiểm chứng | Để provider/OS quản lý seed hoặc theo policy đã đánh giá |
| Chỉ chọn /dev/random vì nghĩ luôn "mạnh hơn" | Có thể tăng độ trễ/không giải quyết đúng vấn đề | Hiểu hợp đồng RNG của OS và chọn API phù hợp |
| Coi source RNG 256 byte = 2048 bit entropy | Đánh giá quá cao độ khó đoán | Dựa vào đánh giá nguồn, không đếm byte |
| Hash(password) làm DEK rồi gọi nó là AES-256 | Key có thể bị đoán qua mật khẩu | Dùng CSPRNG cho DEK; password KDF nếu buộc dựa mật khẩu |
| Lưu seed trong Docker image và nhân bản | Mọi bản triển khai có thể lặp chuỗi | Không gắn seed/secret vào image hoặc snapshot |
| Bỏ qua VM snapshot/fork | DRBG tự chế hoặc counter bị lặp | Dùng RNG được hỗ trợ và xử lý restore an toàn |
| Nhầm entropy với uniqueness | Nonce AES-GCM bị trùng dù nguồn random mạnh | Thiết kế uniqueness theo key, giới hạn lưu lượng |
| Cho rằng HSM làm mạnh key import yếu | Giữ nguyên vật liệu khóa dễ đoán trong miền an toàn | Sinh key trong miền đáng tin hoặc đánh giá nguồn import |
| Chỉ kiểm tra tên provider rồi kết luận đạt chứng nhận | Không phản ánh cấu hình hoặc phạm vi chứng nhận | Xác minh tài liệu/đánh giá và chế độ hoạt động |
| Log seed để hỗ trợ debug | Lộ trạng thái và secret | Chỉ log metadata an toàn, sử dụng test seed giả trong test |
| Reseed sau sự cố rồi giữ khóa yếu cũ | Dữ liệu/chữ ký vẫn có nguy cơ | Rotate/revoke các key bị ảnh hưởng và đánh giá lại hiện vật |
| Fail-open khi KMS/RNG lỗi | Tạo secret không an toàn | Thiết kế fail-safe và đường dự phòng được phê duyệt |

## 15. Tình huống thực hành: Java service trên Kubernetes tạo DEK

Một dịch vụ **Document Service** lưu hồ sơ của nhiều khách hàng. Mỗi bản ghi được mã hóa bằng **AES-GCM**, DEK được wrap dưới KEK của KMS.

### Thiết kế sai

~~~java
// Không sử dụng trong hệ thống bảo mật.
java.util.Random rng = new java.util.Random(
    System.currentTimeMillis()
);
byte[] dek = new byte[32];
rng.nextBytes(dek);
~~~

Hệ thống chạy nhiều pod; thời gian khởi động gần nhau và trạng thái PRNG có thể dự đoán được. Dù có **KMS wrap DEK**, attacker đoán được DEK vẫn có thể giải mã bản mã đã thu thập. KMS chỉ bảo vệ **một vật liệu khóa vốn không mạnh**.

### Thiết kế cải tiến

1. **Sinh DEK ngẫu nhiên qua KMS** có key generation phù hợp hoặc dùng **KeyGenerator + SecureRandom** đã được kiểm chứng và được policy cho phép.
2. Tách DEK theo đối tượng/tenant hoặc phạm vi phù hợp; gắn **key ID/version** với ciphertext.
3. Với AES-GCM, thiết kế nonce 96 bit theo chiến lược **không trùng dưới cùng DEK**, bao gồm pod restart, failover và restore.
4. Hạn chế DEK plaintext trong RAM; không log; dùng KMS wrap/unwrap cùng IAM theo tenant và audit.
5. Giám sát sự kiện GenerateDataKey và mọi thay đổi key policy; không coi việc wrap thành công là bằng chứng DEK có entropy tốt nếu DEK được import tự tạo.
6. Khi phát hiện lỗi RNG, khoanh vùng **những DEK sinh từ code lỗi**, ngừng dùng chúng cho encrypt mới, tạo DEK an toàn và đánh giá re-encrypt dữ liệu.
7. Kiểm thử rollback snapshot, cold start và thay node/JDK; không dùng PRNG yếu làm fallback nếu KMS không khả dụng.

### Sơ đồ trách nhiệm

~~~text
Java / Kubernetes:
  xác thực workload + chọn đúng DEK, tenant, nonce
                  |
                  +--> KMS: generate / wrap / unwrap
                  |
                  +--> AES-GCM ở ứng dụng (nếu DEK dạng rõ trong RAM)
                  |
                  +--> Audit: caller, key version, result

KMS/HSM:
  bảo vệ KEK và key-generation theo hợp đồng dịch vụ

OS/JVM:
  cung cấp SecureRandom nếu ứng dụng tự tạo secret

Verifier / dịch vụ khác:
  kiểm tra quyền, metadata và tính xác thực dữ liệu
~~~

**Bài học:** nguồn random an toàn là một **phần** của kiến trúc. Các lớp còn lại gồm **chính sách KMS/HSM, bảo vệ key material, nonce uniqueness, IAM, kiểm toán và phương án ứng phó sự cố**.

## 16. Câu hỏi tự kiểm tra

**Câu 1. Vì sao không nên dùng java.util.Random để tạo AES key?**

**Trả lời:** Nó không được thiết kế như CSPRNG; trạng thái và seed có thể bị dự đoán. Dùng SecureRandom, KeyGenerator với provider phù hợp hoặc KMS/HSM.

**Câu 2. CSPRNG khác entropy source thế nào?**

**Trả lời:** Entropy source cung cấp bất định; CSPRNG/DRBG dùng trạng thái bí mật đã được seed an toàn để sinh nhiều byte khó dự đoán theo thuật toán.

**Câu 3. SHA-256(timestamp) có tạo khóa 256 bit entropy không?**

**Trả lời:** Không. Đầu ra dài 256 bit nhưng entropy không vượt quá bất định thực sự của timestamp.

**Câu 4. Linux /dev/random có luôn an toàn hơn /dev/urandom không?**

**Trả lời:** Không nên kết luận như vậy. Cần hiểu kernel RNG, trạng thái khởi tạo và hành vi API theo phiên bản Linux; với ứng dụng thông thường, giao diện CSPRNG chuẩn của OS thường thích hợp.

**Câu 5. Java SecureRandom luôn dùng cùng thuật toán trên mọi OS/JDK chứ?**

**Trả lời:** Không. Provider, cấu hình và runtime quyết định thuật toán, nguồn seed và hành vi cụ thể.

**Câu 6. getInstanceStrong có bắt buộc dùng cho mọi token không?**

**Trả lời:** Không. Nó chọn thuật toán theo strong configuration và có thể ảnh hưởng latency; lựa chọn phải dựa trên policy/provider và yêu cầu ứng dụng.

**Câu 7. Nonce AES-GCM có bắt buộc bí mật và không đoán trước được không?**

**Trả lời:** Không nhất thiết. Điều cốt yếu là **không dùng lại nonce với cùng khóa**; có thể dùng counter được cấp phát đúng.

**Câu 8. Private signing key trong HSM có còn rủi ro không?**

**Trả lời:** Có. IAM quá rộng cho phép lạm dụng Sign; hoặc key import ban đầu có entropy kém. HSM không thay việc quản lý quyền và nguồn khóa.

**Câu 9. Nếu KMS lỗi, có được fallback sang java.util.Random để giữ dịch vụ chạy không?**

**Trả lời:** Không. Cần từ chối an toàn hoặc một đường dự phòng đã được đánh giá và phê duyệt.

**Câu 10. Clone VM có luôn khiến hệ thống RNG lặp output không?**

**Trả lời:** Không. Điều này phụ thuộc thiết kế OS/DRBG/hypervisor, nhưng phải đánh giá khi snapshot/restore hoặc dùng PRNG tự chế.

**Câu 11. Reseed hôm nay có chữa được một DEK yếu tạo hôm qua không?**

**Trả lời:** Không. DEK cũ vẫn có thể đoán được; cần xác định phạm vi, rotate/revoke và xử lý dữ liệu bị ảnh hưởng.

**Câu 12. Vì sao KeyGenerator tốt hơn tự hash một chuỗi làm AES key?**

**Trả lời:** KeyGenerator dùng cơ chế tạo khóa của provider với yêu cầu thuật toán và SecureRandom phù hợp; hash một chuỗi dễ đoán không tạo entropy bí mật.

**Câu 13. Salt password có cần bí mật như HMAC key không?**

**Trả lời:** Không. Salt thường công khai và dùng để phân tách phép password hashing; HMAC key là bí mật phải được bảo vệ.

**Câu 14. Nếu token tạo ra đều khác nhau, đã chắc nguồn random an toàn chưa?**

**Trả lời:** Chưa. Một bộ đếm cũng tạo các giá trị khác nhau nhưng dễ dự đoán; token cần khó đoán và được giữ bí mật.

**Câu 15. Vì sao khi đổi key alias vẫn cần kiểm tra vật liệu khóa thực sự?**

**Trả lời:** Đổi alias không nhất thiết tạo key mới. Nếu khóa cũ yếu hoặc lộ, alias mới không khắc phục nguy cơ.

## 17. Checklist vận hành và ghi nhớ

Trước khi triển khai dịch vụ tạo secret, cần xác định:

- **Nền tảng:** đang chạy Linux/Windows/macOS/Android, JDK và provider phiên bản nào?
- **Nguồn:** Java SecureRandom dựa vào cơ chế nào theo tài liệu/cấu hình đã được phê duyệt?
- **Khởi tạo:** có đảm bảo OS RNG sẵn sàng trước khi sinh private key/token không?
- **Tính độc lập:** các bản clone, pod, VM restore hoặc quy trình fork có thể lặp trạng thái bộ sinh hay nonce không?
- **API:** có đang dùng Random, timestamp, UUID, PID hay password hash ở vị trí cần CSPRNG không?
- **Khóa:** DEK/KEK/private key được sinh bằng provider/KMS/HSM thích hợp, đúng algorithm, key usage, version và cryptoperiod chưa?
- **Nonce/salt:** có phân biệt uniqueness, unpredictability và confidentiality đúng theo từng cơ chế mật mã không?
- **IAM:** ai được GenerateKey, GenerateDataKey, Sign, Decrypt, Wrap/Unwrap hoặc thay policy?
- **Audit:** có log provider metadata, key ID/version, caller, kết quả mà không tiết lộ seed/secret không?
- **Sự cố:** nếu RNG/KMS/provider lỗi, hệ thống fail-safe và có kế hoạch xác định, rotate/revoke các key bị ảnh hưởng không?
- **Vận hành:** có đánh giá lại khi nâng JDK/OS, thay provider, thay phần cứng hoặc chuyển cloud không?

**Ghi nhớ:** **Nguồn random của nền tảng** là chuỗi tin cậy từ **entropy source → OS/runtime CSPRNG hoặc DRBG → API tạo khóa/secret**. Ứng dụng Java nên dùng **SecureRandom/KeyGenerator** hoặc dịch vụ **KMS/HSM** được đánh giá và tuân thủ hợp đồng API của nền tảng; không tự tạo "random bảo mật" từ timestamp, PRNG thông thường hoặc một vòng hash mật khẩu. Kiểm soát nguồn random phải luôn đi cùng **quản lý DEK/KEK, AES-GCM nonce, chữ ký số, IAM, kiểm toán, rotation, revocation và hủy khóa**.
