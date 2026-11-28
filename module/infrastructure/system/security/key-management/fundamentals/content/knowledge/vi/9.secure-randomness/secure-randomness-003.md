# Entropy (Độ bất định trong mật mã)

## 1. Entropy là gì và vì sao liên quan trực tiếp đến khóa?

**Entropy** mô tả mức độ bất định của một nguồn dữ liệu hoặc biến ngẫu nhiên. Trong mật mã, câu hỏi quan trọng là: **kẻ tấn công có thể dự đoán hoặc thu hẹp không gian những giá trị bí mật mà hệ thống tạo ra đến mức nào?**

Ví dụ, khi tạo khóa AES-256, hệ thống cần một giá trị bí mật gồm 256 bit được sinh từ nguồn ngẫu nhiên thích hợp. Nếu một chương trình lấy giờ hiện tại rồi băm SHA-256 thành 256 bit, đầu ra vẫn dài 256 bit nhưng người đoán được khoảng thời gian sinh khóa có thể thử rất ít ứng viên. **Độ dài 256 bit không đồng nghĩa 256 bit entropy.**

Trong chương **Secure randomness** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, entropy là một trong những điều kiện ban đầu để toàn bộ vòng đời khóa an toàn: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Các cơ chế như AES-GCM, RSA/ECDSA/Ed25519, HMAC, KDF, KMS/HSM hay envelope encryption đều có thể thất bại nếu vật liệu khóa ban đầu dễ đoán.

~~~text
Nguồn bất định vật lý / hệ điều hành
                  |
                  v
        Thu thập và đánh giá entropy
                  |
                  v
     Seed / trạng thái CSPRNG hoặc DRBG
                  |
                  v
       Sinh key, nonce, token, secret
                  |
                  v
      Phân quyền, sử dụng và quản lý
~~~

**Entropy không phải tên của một thuật toán mã hóa.** Đây là thuộc tính của nguồn và phân bố xác suất. CSPRNG/DRBG sử dụng entropy để tạo chuỗi byte phù hợp cho các thao tác mật mã, còn KMS/HSM cung cấp môi trường quản lý và bảo vệ khóa theo chính sách.

## 2. Phân biệt entropy, randomness và unpredictability

| Thuật ngữ | Ý nghĩa | Liên hệ trong bảo mật |
|---|---|---|
| **Randomness** (tính ngẫu nhiên) | Tính chất thống kê/phân bố của giá trị hoặc quá trình | Một chuỗi trông ngẫu nhiên chưa chắc khó dự đoán |
| **Entropy** | Định lượng bất định của phân bố | Cho biết mức bất định cần đánh giá ở nguồn/secret |
| **Unpredictability** (khó dự đoán) | Đối thủ không thể suy ra giá trị trước khi nó được tạo/tiết lộ với khả năng đáng kể | Thuộc tính thiết yếu khi sinh private key, secret và token |
| **CSPRNG** | Bộ sinh số giả ngẫu nhiên được thiết kế cho mật mã | Tạo đầu ra khó phân biệt với ngẫu nhiên khi trạng thái, seed và triển khai an toàn |
| **DRBG** | Deterministic Random Bit Generator: bộ sinh bit xác định từ trạng thái bí mật | Sau khởi tạo an toàn, có thể sinh nhiều bit từ entropy đầu vào |
| **Entropy source** | Nguồn cung cấp bất định từ hiện tượng hoặc thành phần được đánh giá | Dùng để khởi tạo và tái cấp entropy cho bộ sinh |
| **Seed** | Dữ liệu đầu vào khởi tạo trạng thái bộ sinh | Seed có đủ entropy và được bảo vệ hay không ảnh hưởng toàn chuỗi đầu ra |

Một **PRNG thông thường** có thể vượt qua nhiều phép kiểm tra thống kê nhưng vẫn dự đoán được nếu biết seed hoặc trạng thái. Ví dụ, một bộ sinh lập trình dùng hạt giống cố định tạo đúng chuỗi byte sau mỗi lần chạy; nhìn riêng một vài byte có vẻ hỗn loạn nhưng không phù hợp để tạo secret.

Một **CSPRNG** cũng là bộ sinh **xác định theo trạng thái**. Sự bảo mật đến từ việc trạng thái đã được khởi tạo bằng entropy phù hợp, thuật toán và triển khai đủ mạnh, việc giới hạn tiết lộ trạng thái và quy trình reseed đúng. CSPRNG **không tạo thêm entropy độc lập từ một seed vốn dễ đoán**.

## 3. Định lượng entropy: Shannon entropy và min-entropy

### 3.1. Shannon entropy

Với biến ngẫu nhiên X có những khả năng x_i với xác suất p_i, **Shannon entropy** là:

\[
H(X)=-\sum_i p_i\log_2 p_i
\]

Nó biểu thị **mức thông tin trung bình** của phân bố, tính bằng bit. Nếu có 256 kết quả **đều xác suất**, Shannon entropy bằng 8 bit; nếu một giá trị có xác suất rất lớn, entropy nhỏ hơn.

### 3.2. Min-entropy

Trong đánh giá nguồn bí mật, **min-entropy** thường hữu ích vì nó tập trung vào kết quả dễ đoán nhất:

\[
H_{\infty}(X)=-\log_2\left(\max_x \Pr[X=x]\right)
\]

Nếu một giá trị có xác suất 1/2 thì min-entropy của X chỉ là **1 bit**, dù phân bố có thể chứa rất nhiều giá trị hiếm gặp.

| Phân bố | Shannon entropy | Min-entropy | Ý nghĩa |
|---|---:|---:|---|
| Đồng xu công bằng (2 kết quả đều xác suất) | 1 bit | 1 bit | Không có mặt nào dễ đoán hơn |
| 1 byte đều ngẫu nhiên (256 giá trị) | 8 bit | 8 bit | Mỗi giá trị có xác suất 1/256 |
| 4 giá trị: 1/2, 1/4, 1/8, 1/8 | 1,75 bit | 1 bit | Giá trị đầu tiên có xác suất 1/2 |
| Một biến luôn bằng 0 | 0 bit | 0 bit | Hoàn toàn dự đoán được |

Khi đánh giá đầu vào cho hệ thống sinh khóa, **không được lấy số bit của vùng nhớ rồi tự coi đó là số bit entropy**. Một thiết bị trả 256 byte không đồng nghĩa nó đã đóng góp 2048 bit entropy nếu đầu ra có thiên lệch hoặc tương quan mạnh.

### 3.3. Entropy của một mật khẩu

Một PIN gồm 6 chữ số **được chọn đều ngẫu nhiên** có entropy:

\[
\log_2(10^6)\approx19{,}93\ \text{bit}.
\]

Nhưng PIN hoặc mật khẩu **do con người chọn** không nhất thiết tuân theo phân bố đều: các giá trị phổ biến, ngày sinh và mẫu bàn phím có thể được thử trước. Vì thế không thể đánh giá entropy chỉ bằng cách đếm ký tự hoặc nhân số ký tự với số khả năng trong bảng chữ cái.

Một khóa **256 bit được sinh đều bởi CSPRNG an toàn** có không gian tìm kiếm khác hoàn toàn với chuỗi 256 bit được tạo bằng SHA-256 từ mật khẩu yếu.

## 4. Ví dụ: dữ liệu dài 256 bit nhưng chỉ có khoảng 20 bit bất định

Giả sử ứng dụng tạo khóa như sau:

~~~text
seed = số nguyên ngẫu nhiên đồng đều từ 0 đến 1.000.000 - 1
key  = SHA256(UTF8(seed))
~~~

Dù SHA-256 tạo 256 bit, chỉ có **1.000.000 seed khả dĩ**, tương đương gần **2^20** ứng viên. Kẻ tấn công có thể hash tất cả ứng viên rồi kiểm tra dữ liệu để xác định khóa. Một hàm băm **không thể tự biến nguồn 20 bit entropy thành một khóa có 256 bit bảo đảm chống đoán**.

Nếu seed lấy từ **thời gian hệ thống trong một khoảng ngắn**, số khả năng có thể còn ít hơn. Tương tự, UUID, request ID, địa chỉ IP, PID hoặc số lượng chu kỳ CPU đo được không phải bằng chứng đủ entropy cho private key.

**Nguyên tắc:** Chiều dài khóa là tham số của thuật toán; **entropy của nguồn sinh khóa** là yếu tố ảnh hưởng đến khả năng đối thủ đoán được giá trị khóa thực sự.

## 5. Nguồn entropy có thể đến từ đâu?

Các hệ thống hiện đại thường sử dụng nguồn entropy được tích hợp trong hệ điều hành hoặc phần cứng:

| Nguồn/cơ chế | Vai trò | Vấn đề cần đánh giá |
|---|---|---|
| **Entropy collection của OS** | Thu thập nhiễu/biến thiên từ những nguồn mà hệ điều hành hỗ trợ | Khởi tạo sớm, phiên bản OS, môi trường container/VM, trạng thái seed |
| **Hardware random generator / TRNG** | Khai thác hiện tượng vật lý hoặc phần cứng để sinh bất định | Chất lượng, kiểm tra sức khỏe, driver, trust vào thiết bị |
| **CPU RNG instruction** | Có thể góp phần lấy ngẫu nhiên từ phần cứng theo thiết kế nền tảng | Không mặc định mọi CPU/API có cùng cách vận hành và tiêu chuẩn |
| **OS CSPRNG** | Mở rộng trạng thái đã khởi tạo để cấp random bytes cho ứng dụng | Cần hệ điều hành đã khởi tạo tốt và API an toàn |
| **HSM entropy source** | Phục vụ sinh khóa và các phép toán trong thiết bị an toàn | Cần đánh giá chứng nhận, cấu hình, sự cố và quyền dùng khóa |

**Không nên tự ghép các biến thời gian, tên máy, PID hay địa chỉ bộ nhớ** để làm "nguồn ngẫu nhiên mật mã". Các dữ kiện đó có thể bị biết hoặc đoán được. Tốt nhất, ứng dụng sử dụng **API CSPRNG của hệ điều hành hoặc thư viện mật mã được kiểm chứng**.

Trong một số môi trường nhúng, thiết bị mới khởi động, VM clone hoặc hệ thống không có nguồn entropy đáng tin, quá trình sinh secret cần được thiết kế thận trọng. Một CSPRNG chạy với trạng thái khởi tạo sai có thể lặp đầu ra sau reboot hoặc snapshot.

## 6. CSPRNG và DRBG biến entropy thành random bytes như thế nào?

Một thiết kế thường gặp gồm những bước:

1. **Thu thập entropy** từ nguồn đã được đánh giá.
2. **Conditioning/extraction** để xử lý nguồn thô và tạo vật liệu seed phù hợp, theo cơ chế chuẩn.
3. **Instantiate** DRBG/CSPRNG với seed và thông tin khởi tạo cần thiết.
4. **Generate** bytes cho các thao tác mật mã bằng cách cập nhật trạng thái bên trong.
5. **Reseed** hoặc làm mới trạng thái khi chính sách/giới hạn của bộ sinh yêu cầu, có thể sau sự kiện khởi tạo, số lượt sinh nhất định hoặc nhu cầu bảo mật.
6. **Kiểm tra lỗi** và thực hiện quy trình an toàn nếu nguồn entropy hoặc bộ sinh không hoạt động đúng.

~~~mermaid
flowchart TD
    E["Entropy sources đã đánh giá"] --> C["Conditioning / Seed material"]
    C --> I["Khởi tạo DRBG"]
    I --> G["Generate random bytes"]
    G --> U["Khóa / token / nonce"]
    G --> P{"Cần reseed theo chính sách?"}
    P -->|Có| R["Lấy entropy bổ sung"]
    R --> I
    P -->|Không| G
    F["Health tests / trạng thái lỗi"] --> A["Fail-safe: ngừng cấp secret nếu RNG không đạt"]
~~~

Sơ đồ mô tả quan hệ **khái niệm**, không phải yêu cầu mọi runtime triển khai đúng những thành phần hay bước gọi API như nhau. Hệ điều hành và provider Java có thể quản lý seed/reseed nội bộ.

### 6.1. Reseed có tăng độ an toàn khi seed ban đầu yếu?

**Không thể coi reseed là biện pháp bù trừ chắc chắn cho việc đã cấp những khóa yếu trước đó.** Reseed bằng entropy tốt có thể cải thiện trạng thái và bảo vệ đầu ra tương lai theo thiết kế DRBG, nhưng các khóa đã được cấp từ trạng thái dễ đoán vẫn cần được **thay thế và đánh giá sự cố**.

Không tự xây cơ chế reseed bằng cách gọi hash(timestamp) rồi trộn vào một RNG riêng. Quy tắc trộn entropy, cập nhật trạng thái và xử lý lỗi thuộc về thiết kế CSPRNG/DRBG đáng tin.

### 6.2. Backtracking resistance và prediction resistance

Hai khái niệm thường gặp trong tài liệu DRBG:

- **Backtracking resistance:** nếu một trạng thái nội bộ bị lộ tại thời điểm hiện tại, việc suy ngược những byte đã sinh **trước thời điểm ấy** vẫn khó theo thiết kế.
- **Prediction resistance:** hệ thống được thiết kế và cấp entropy bổ sung theo cách làm giảm khả năng đối thủ dự đoán **đầu ra tương lai** ngay cả khi từng chiếm được trạng thái trong điều kiện được mô hình bảo vệ.

Không phải mọi CSPRNG hay lời gọi API đều cam kết các thuộc tính này ở cùng mức. Quy định **nguồn, tần suất reseed, mô hình lộ trạng thái và trạng thái lỗi** phải được kiểm tra theo provider và tiêu chuẩn sử dụng.

## 7. Entropy được dùng vào những đối tượng nào?

| Đối tượng | Cần gì từ nguồn ngẫu nhiên? | Lưu ý thiết kế |
|---|---|---|
| **AES DEK / KEK** | Vật liệu khóa bí mật, khó đoán, đủ độ dài | Sinh bằng CSPRNG/HSM; tách mục đích, quản lý KMS |
| **HMAC key** | Secret đối xứng có entropy phù hợp | Không dùng mật khẩu yếu hay static string làm secret |
| **RSA key pair** | Randomness cho các giá trị riêng của thuật toán sinh khóa | Dùng thư viện, provider và tham số được chấp nhận |
| **ECDSA private key** | Số vô hướng bí mật trong miền giá trị hợp lệ | CSPRNG/thuật toán sinh khóa an toàn; chú ý nonce bí mật khi ký |
| **Ed25519 private seed** | Seed bí mật sinh an toàn theo thuật toán | Không suy từ timestamp hoặc mã định danh |
| **Session secret / token** | Byte khó đoán, độc lập phù hợp mô hình | CSPRNG, thời hạn, scope, phân quyền và bảo vệ token |
| **Password salt** | Salt ngẫu nhiên, thông thường duy nhất từng bản ghi | Salt không cần bí mật, nhưng không dùng chung cố định |
| **AES-GCM nonce** | **Tính duy nhất với cùng khóa** | Có thể dùng counter an toàn hoặc random với giới hạn; không phải lúc nào cần entropy bí mật |
| **ECDSA nonce k** | Bí mật, phù hợp cho từng chữ ký | Lộ hoặc tái sử dụng sai k có thể làm lộ private key |
| **Recovery key** | Secret đủ mạnh cho khôi phục | Cần bảo vệ, tách quyền, backup và quy trình kích hoạt rõ ràng |

Điểm rất quan trọng là **"giá trị cần random" không đồng nghĩa "giá trị phải giữ bí mật"**. Một salt password có thể được lưu công khai, trong khi AES key phải bí mật. Một nonce AES-GCM cần **không trùng theo khóa**; bộ đếm có thể đáp ứng tính duy nhất nếu thiết kế chính xác, dù bộ đếm hoàn toàn dự đoán được.

Ngược lại, **ECDSA k** phải là giá trị bí mật phù hợp cho mỗi chữ ký hoặc được dẫn xuất xác định theo cơ chế chuẩn như RFC 6979; không thể đối xử với k giống nonce công khai của GCM.

## 8. Java: dùng SecureRandom để sinh secret

Trong Java, **java.security.SecureRandom** cung cấp API lấy byte ngẫu nhiên phù hợp cho các mục đích mật mã theo provider được chọn. Java **Random** và các cơ chế PRNG thông thường không được thiết kế để bảo vệ secret mật mã.

Ví dụ Java 17+:

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class EntropyAndSecureRandomExample {
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    public static void main(String[] args) throws Exception {
        // 1. Sinh secret 32 byte cho token ngẫu nhiên.
        byte[] tokenBytes = new byte[32];
        SECURE_RANDOM.nextBytes(tokenBytes);

        // Mã hóa biểu diễn, không phải mã hóa giữ bí mật.
        String bearerToken = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(tokenBytes);

        // 2. Sinh một AES-256 key bằng KeyGenerator.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, SECURE_RANDOM);
        SecretKey dataKey = generator.generateKey();

        // 3. Minh họa sinh một nonce 96 bit cho một lần AES-GCM encrypt.
        // Ở hệ thống lớn phải kiểm soát uniqueness toàn vòng đời key.
        byte[] gcmNonce = new byte[12];
        SECURE_RANDOM.nextBytes(gcmNonce);

        if (dataKey == null || bearerToken.isEmpty()) {
            throw new IllegalStateException("Random generation failed");
        }
        System.out.println("Generated token, AES key and GCM nonce");

        // Giảm thời gian tồn tại của mảng byte chứa secret.
        Arrays.fill(tokenBytes, (byte) 0);

        // Chỉ demo: không log token, AES key, nonce hoặc dump state RNG.
    }
}
~~~

**Điều cần hiểu:**

1. **new SecureRandom()** chọn triển khai/provider theo môi trường Java. Các chi tiết về nguồn entropy, khi nào khởi tạo seed và reseed có thể khác giữa provider/hệ điều hành.
2. **nextBytes** cấp random bytes cho token hoặc các mục đích được phép. Một token 32 byte đều ngẫu nhiên có **256 bit độ dài và entropy lý tưởng** nếu CSPRNG được khởi tạo đúng và không bị lộ.
3. **KeyGenerator** sinh AES key với các ràng buộc của provider, thuận tiện hơn việc tự chuyển một chuỗi ký tự hoặc hash mật khẩu thành SecretKey.
4. **Nonce GCM 12 byte** trong ví dụ được sinh ngẫu nhiên. Cách này **không chứng minh chắc chắn không va chạm** khi số lần mã hóa dưới cùng khóa tăng nhiều; phải chọn chiến lược nonce và giới hạn sử dụng phù hợp.
5. **Bearer token** là bí mật truy cập; tuyệt đối không log hoặc hard-code. Base64url chỉ chuyển byte sang text để truyền, không làm dữ liệu được mã hóa bí mật.
6. Việc xóa **tokenBytes** chỉ xử lý một bản sao trong bộ nhớ; biến **bearerToken** và các bản sao JVM/provider vẫn có thể tồn tại. Cần hạn chế phơi lộ secret, quyền truy cập, thời hạn và scope.

**Không gọi SecureRandom.setSeed(System.currentTimeMillis()) như cách "cải thiện entropy".** Một seed do ứng dụng tự chọn từ timestamp rất dễ đoán; cách xử lý setSeed và trộn seed còn phụ thuộc provider. Tốt nhất để provider/OS thực hiện seeding theo thiết kế hoặc dùng API được nhà cung cấp tài liệu hóa cho yêu cầu cụ thể.

### 8.1. Khi nào dùng getInstanceStrong?

Java có **SecureRandom.getInstanceStrong()** để chọn một thuật toán theo cấu hình strong của hệ thống. Nó **có thể block** hoặc có đặc tính độ trễ khác tùy provider và môi trường. Không suy rằng gọi getInstanceStrong luôn cần thiết hay luôn tốt hơn new SecureRandom() cho mọi request web.

Đối với ứng dụng thông thường, cần chọn provider theo chính sách bảo mật và đánh giá vận hành. Đối với HSM, môi trường yêu cầu chứng nhận hoặc ứng dụng khóa đặc biệt nhạy cảm, có thể cần một nguồn RNG/provider cụ thể theo quy trình quản lý rủi ro.

### 8.2. CSPRNG không phải bộ sinh số cho mô phỏng ngẫu nhiên

- **java.util.Random**, **ThreadLocalRandom** thường hữu ích cho mô phỏng, chọn mẫu hoặc cân bằng tải, nhưng không phù hợp để sinh private key, session token hay secret.
- **SecureRandom** phù hợp cho ngẫu nhiên phục vụ mật mã theo cấu hình đúng.
- **SplittableRandom** được thiết kế cho các công việc thống kê song song, không phải mặc định cho bảo mật.

Không dựa vào việc một lớp có tên Random hoặc sinh được byte khó đọc để kết luận nó là CSPRNG.

## 9. Sinh khóa mật mã khác gì dẫn xuất khóa từ mật khẩu?

Nếu một hệ thống cần AES key ngẫu nhiên, nguồn đầu vào nên là **CSPRNG/KMS/HSM**. Nếu một hệ thống chỉ có mật khẩu người dùng, phải sử dụng **password-based KDF** phù hợp như Argon2id, scrypt hoặc PBKDF2 theo chính sách, không băm một lần rồi coi output có entropy đầy đủ.

| Nguồn đầu vào | Phương án | Điều không được suy diễn |
|---|---|---|
| Secret được lấy đều ngẫu nhiên từ CSPRNG | Dùng làm key khi đúng thuật toán/độ dài | Không bảo đảm an toàn nếu key bị log hoặc IAM bị lạm dụng |
| Mật khẩu yếu | Dùng password KDF để tăng chi phí thử đoán | KDF không tạo entropy vốn không có trong password |
| Bí mật chia sẻ có entropy cao | Dùng HKDF và ngữ cảnh để dẫn xuất nhiều subkeys | HKDF không được dùng thay password hashing cho mật khẩu yếu |
| Các giá trị nhận dạng như user ID/timestamp | Không dùng làm key source | Hash đến 256 bit không biến chúng thành bí mật mạnh |

### 9.1. Salt không phải nguồn entropy cho mật khẩu yếu

**Salt** của password hashing được tạo ngẫu nhiên để hạn chế việc dùng chung kết quả và bảng tra cứu sẵn; nó được lưu công khai với verifier. Khi kẻ tấn công đã có salt và verifier, họ vẫn có thể thử password. Salt không bù được mật khẩu quá dễ đoán.

### 9.2. Pepper là bí mật riêng

Một **pepper** bổ sung trong một số kiến trúc được giữ ngoài cơ sở dữ liệu mật khẩu, có thể trong secret store/KMS/HSM. Pepper phải thực sự được sinh ngẫu nhiên và bảo vệ vòng đời. Nó **không thay cho salt hay password KDF**, và việc mất pepper có thể ảnh hưởng khả năng xác minh password cũ.

## 10. Entropy, nonce uniqueness và xác thực AEAD

Các khái niệm gần nhau nhưng có yêu cầu khác nhau:

| Thành phần | Yêu cầu thiết yếu |
|---|---|
| **AES key/DEK** | Secret khó đoán, đúng độ dài, phân quyền và vòng đời |
| **AES-GCM nonce** | Không tái sử dụng cùng nonce với **cùng key** trên các lần mã hóa |
| **AES-GCM AAD** | Đúng dữ liệu ngữ cảnh cần xác thực và không bị tráo đổi |
| **AES-GCM tag** | Được kiểm tra khi giải mã; sai tag phải từ chối |
| **HMAC key** | Secret có entropy và mục đích thích hợp |
| **ECDSA k** | Bí mật theo lần ký, không lộ hoặc tái sử dụng sai |

Một ứng dụng có thể dùng **DEK ngẫu nhiên rất mạnh** nhưng vẫn mất bảo mật nếu mỗi lần AES-GCM encrypt dùng lại nonce bằng 0. Đó là lỗi **nonce uniqueness**, không phải lỗi độ dài DEK.

Ngược lại, dùng nonce ngẫu nhiên 96 bit từ SecureRandom tạo khả năng va chạm rất nhỏ ở lưu lượng giới hạn, nhưng không bảo đảm tuyệt đối. Ở quy mô lớn hoặc đa instance, cần chiến lược phù hợp như **counter/partition có cấp phát duy nhất bền vững**, hoặc tách DEK theo phạm vi và đặt giới hạn số lần mã hóa.

### 10.1. Entropy không thay thế tính duy nhất

**Random ≠ unique.** Một giá trị ngẫu nhiên có thể trùng với giá trị đã dùng. Bộ đếm được cấp phát an toàn có thể bảo đảm không trùng nhưng dự đoán được. Với AES-GCM, điều cần thiết là **duy nhất theo khóa**; với token truy cập, điều cần thiết còn là **khó đoán**.

Nếu hai worker cùng dùng một DEK, chúng cũng chia sẻ không gian nonce. Chỉ gán hai key ID khác nhau trong metadata không giúp gì nếu vật liệu DEK thực tế giống nhau.

## 11. Entropy trong KMS, HSM và envelope encryption

Trong **envelope encryption**, dữ liệu được mã hóa bằng **DEK**, còn **KEK** bảo vệ DEK. KMS/HSM có thể cung cấp chức năng tạo và sử dụng các khóa này trong miền tin cậy:

~~~mermaid
flowchart TD
    R["OS RNG / HSM entropy + CSPRNG"] --> K["Tạo DEK ngẫu nhiên"]
    K --> E["AES-GCM mã hóa dữ liệu"]
    D["Dữ liệu gốc"] --> E
    E --> C["Ciphertext + nonce + tag"]
    W["KMS/HSM bảo vệ KEK"] --> WR["Wrap DEK"]
    K --> WR
    WR --> WK["Encrypted DEK"]
    C --> S["Lưu bản mã + metadata"]
    WK --> S
    ID["Key ID/version, AAD context"] --> S
~~~

**Vai trò của entropy:**

- **Sinh KEK/DEK:** vật liệu khóa phải khó đoán; không lấy timestamp, request ID hay hash một mật khẩu yếu làm DEK.
- **Sinh private signing key:** các thuật toán ECC/RSA cần cách tạo riêng được hỗ trợ bởi thư viện hoặc HSM.
- **Sinh token/credential:** các secret để gọi KMS hay truy cập API phải khó đoán và có vòng đời.
- **Sinh salt:** salt có thể công khai nhưng nên được tạo ngẫu nhiên, thường duy nhất từng bản ghi.
- **Sinh nonce AES-GCM:** chọn cách đáp ứng uniqueness, không tự đồng nhất với seeding HSM.

**KMS/HSM không phải bảo đảm tuyệt đối rằng mọi đầu ra đều an toàn trong mọi điều kiện**. Cần kiểm tra cam kết API, loại key, thuật toán, quy trình sinh, chính sách export, chứng nhận nếu có và quản trị quyền. Nếu API cho phép caller nhập một khóa yếu để import, việc lưu khóa yếu đó vào HSM **không tự nâng entropy** của vật liệu ban đầu.

### 11.1. Khi ứng dụng tự sinh DEK

Một mô hình sử dụng KMS có thể yêu cầu ứng dụng gọi API tạo DEK, dùng DEK dạng rõ trong RAM ngắn hạn, rồi lưu encrypted DEK bên cạnh bản mã. Nếu ứng dụng tự sinh DEK bằng SecureRandom rồi wrap qua KMS, trách nhiệm đảm bảo **nguồn random an toàn** thuộc cả thiết kế ứng dụng.

Trong cả hai mô hình cần:

1. Giới hạn ai được tạo/sử dụng DEK và unwrap qua IAM.
2. Giữ DEK dạng rõ trong RAM **chỉ khi cần** và không log.
3. Lưu **key ID/version, encrypted DEK, nonce/tag và ngữ cảnh cần thiết**.
4. Có kế hoạch rotate/revoke KEK/DEK riêng.
5. Kiểm toán các lời gọi KMS đáng ngờ mà không để lộ vật liệu khóa.

## 12. Thiếu entropy khi khởi động và sự cố snapshot/clone

Một lỗi khó phát hiện là **nhiều instance tạo cùng chuỗi bí mật** do trạng thái sinh ngẫu nhiên bị lặp:

~~~text
VM A: snapshot chứa CSPRNG state tại thời điểm T
     |
     +--> VM A1 phục hồi và sinh token X, key K
     |
     +--> VM A2 phục hồi cùng trạng thái và sinh token X, key K
          (nếu RNG không có bảo vệ chống clone/reseed thích hợp)
~~~

Điều này không có nghĩa mọi VM clone đều chắc chắn lặp đầu ra. Hệ điều hành và DRBG hiện đại có thể có cơ chế phòng vệ riêng. Nhưng **thiết kế phải đánh giá** khả năng snapshot/rollback, clone image, máy mới boot và nguồn entropy của môi trường thực tế.

Những điều cần xem xét:

- **First boot / early boot:** hệ thống đã khởi tạo nguồn ngẫu nhiên của OS đến mức cần thiết trước khi cấp private key chưa?
- **Container:** nhiều container có dùng cùng hạ tầng OS RNG như dự kiến? Có code nào tự seed từ giá trị container ID hoặc timestamp không?
- **Virtual machine snapshot:** trạng thái RNG có bị clone và phát lại? OS/runtime có cơ chế reseed hoặc phòng chống duplicate state?
- **Restore backup:** sau restore có tái sử dụng secret/token hoặc nonce counter đã phát hành trước đó không?
- **Process fork / preloading:** thư viện mật mã có bảo đảm trạng thái ngẫu nhiên riêng hoặc cập nhật sau fork theo nền tảng sử dụng không?
- **Embedded/IoT:** nguồn entropy vật lý có được đo, khởi tạo, health-test và giám sát theo thiết kế không?

**Không tự tin rằng chạy trên cloud hoặc dùng HSM sẽ loại bỏ hoàn toàn lỗi cấu hình entropy.** Cần kiểm tra cách ứng dụng tạo khóa thực sự, trạng thái khi khởi động, phiên bản phần mềm và hợp đồng của provider.

## 13. Bảo vệ entropy source và seed qua vòng đời hệ thống

Mục tiêu của key management bao gồm cả những thành phần tạo ra khóa:

| Giai đoạn | Cần kiểm soát |
|---|---|
| **Thiết kế** | Chọn OS CSPRNG/HSM hoặc thư viện theo thuật toán và yêu cầu tuân thủ |
| **Khởi tạo** | Đảm bảo nguồn entropy đã sẵn sàng trước khi sinh secret |
| **Generation** | Sinh đúng key length/type; không nhập seed yếu hoặc sử dụng PRNG thông thường |
| **Provisioning** | Cấp secret qua kênh và IAM được xác thực; không chia sẻ seed/DRBG state |
| **Storage** | Bảo vệ private key/DEK/seed nếu seed được lưu theo thiết kế |
| **Usage** | Hạn chế ai được GenerateKey, GenerateDataKey, Sign, Decrypt, Wrap |
| **Rotation** | Sinh **vật liệu khóa mới độc lập**, không chỉ đổi alias; đánh giá nguồn randomness |
| **Revocation** | Khi RNG bị nghi lỗi, khoanh vùng các khóa có thể được tạo từ seed yếu |
| **Destruction** | Hủy vật liệu khóa và bản sao sau khi đánh giá phụ thuộc dữ liệu, audit |

### 13.1. Reseed và rotation là hai việc khác nhau

**Reseed** làm mới trạng thái của bộ sinh theo quy tắc DRBG. **Rotation** là thay vật liệu khóa hoặc phiên bản được sử dụng cho phép toán mật mã. Reseed hôm nay **không biến một private key yếu được tạo hôm qua thành private key mạnh**; phải tạo khóa mới và chuyển phụ thuộc.

**Revocation** là rút quyền sử dụng hoặc niềm tin đối với khóa có rủi ro. Khi nghi ngờ một RNG từng sinh key yếu, cần xác định giai đoạn/thành phần bị ảnh hưởng, chặn việc cấp key mới từ nguồn đó, thay khóa, cập nhật dữ liệu/chữ ký và đánh giá thông tin đã lộ.

## 14. Khi nào cần kiểm thử nguồn entropy?

Các **kiểm tra thống kê** như tần suất bit 0/1, chuỗi lặp, phân bố byte có thể phát hiện lỗi nghiêm trọng trong nguồn thô, nhưng **không chứng minh một CSPRNG an toàn trước đối thủ mật mã**. Một bộ sinh xác định với seed công khai cũng có thể tạo dữ liệu vượt qua nhiều kiểm tra thống kê.

Do đó phân biệt:

- **Entropy source validation:** đánh giá nguồn thô, phương pháp ước lượng entropy, điều kiện hoạt động và **health test** theo tiêu chuẩn thích hợp.
- **CSPRNG/DRBG validation:** kiểm tra thuật toán, cách khởi tạo/reseed, trạng thái lỗi, triển khai và các cam kết bảo mật.
- **Application tests:** xác minh ứng dụng thực sự sử dụng SecureRandom/KMS đúng nơi, không rò secret và xử lý lỗi an toàn.
- **Operational monitoring:** theo dõi sự cố RNG/OS/HSM, chính sách nguồn seed, hành vi tạo khóa và những đợt deployment liên quan.

### 14.1. Những điều kiểm thử có thể xác nhận

| Tình huống | Kết quả cần có |
|---|---|
| Đường tạo DEK | Dùng CSPRNG/KMS/HSM được phê duyệt, không dùng seed tự chế |
| Sinh token đăng nhập | Token khó đoán, đúng độ dài và không bị log hoặc lộ trong URL không phù hợp |
| Khởi động khi OS RNG chưa sẵn sàng | Hệ thống tuân theo hành vi an toàn của nền tảng; không tự fallback sang thời gian |
| Clone/restore thử nghiệm | Có cơ chế xử lý trạng thái RNG và nonce counters, không sử dụng lại secret ngoài dự kiến |
| KMS/DRBG báo lỗi | Không tự cấp khóa bằng RNG yếu làm fallback |
| Provider thay đổi sau nâng cấp | Đánh giá lại cấu hình, thuật toán và cam kết nguồn randomness |
| Sinh DEK bằng API | Key được quản lý đúng version, quyền và audit; không đưa key ra log |
| Tạo nonce GCM | Đảm bảo uniqueness theo khóa trong giới hạn thiết kế, kể cả nhiều writer |
| Đổi tên key/alias | Không tự đánh dấu đã rotation nếu vật liệu khóa chưa đổi |
| Dữ liệu đầu vào entropy có dấu hiệu lỗi | Health test/giám sát hoặc cơ chế an toàn xử lý theo thiết kế |

**Không kiểm thử bằng cách chỉ tạo 100 khóa và kết luận an toàn vì chúng khác nhau.** Kết quả khác nhau không chứng minh entropy đủ; ngược lại, khả năng trùng của một giá trị ngẫu nhiên hữu hạn phụ thuộc mô hình xác suất và số lượng mẫu.

## 15. Rủi ro khi quản lý entropy sai

| Sai lầm | Hậu quả có thể xảy ra | Cách phòng tránh |
|---|---|---|
| Dùng timestamp để seed PRNG sinh AES key | Kẻ tấn công thử được không gian seed nhỏ | Dùng CSPRNG của OS hoặc dịch vụ key generation đã đánh giá |
| Dùng java.util.Random hoặc ThreadLocalRandom cho secret | Chuỗi có thể dự đoán theo trạng thái/seed | SecureRandom hoặc API KMS/HSM |
| Lấy hash của password làm khóa "256-bit mạnh" | Entropy thực chỉ giới hạn bởi password | CSPRNG cho key; password KDF nếu bắt buộc dựa trên password |
| Đếm số byte output rồi coi đó là entropy | Đánh giá sai sức mạnh của key | Đánh giá nguồn và phân bố theo phương pháp phù hợp |
| Đọc source RNG không sẵn sàng khi boot rồi tự fallback | Có thể tạo khóa từ seed dễ đoán | Fail-safe, chờ API OS sẵn sàng theo hợp đồng hệ thống |
| Clone VM kèm trạng thái DRBG yếu | Nhiều instance có thể lặp key/token | Giải pháp chống snapshot/fork và reseed theo provider |
| Log seed, state, private key hoặc token | Kẻ tấn công dự đoán/đánh cắp secret | Redaction và kiểm soát quyền log |
| Tự trộn nhiều nguồn yếu không đánh giá | Không có bảo đảm tổng entropy đủ | Sử dụng bộ thu thập/conditioning tiêu chuẩn |
| Nhầm AES-GCM nonce với key ngẫu nhiên | Tái sử dụng nonce phá AEAD dù key mạnh | Thiết kế duy nhất nonce theo mỗi key |
| Sinh ECDSA k bằng RNG lỗi | Có thể lộ private signing key từ chữ ký | Provider/HSM đã kiểm chứng và quy trình nonce chuẩn |
| Khóa sinh từ RNG bị nghi lỗi nhưng chỉ reseed | Khóa cũ vẫn có thể dễ đoán | Xác định phạm vi và rotate/revoke các khóa bị ảnh hưởng |
| Nhập key yếu vào HSM rồi coi đã an toàn | HSM không thay entropy đã thiếu | Sinh trong miền tin cậy hoặc kiểm chứng nguồn import |
| Chỉ kiểm tra phân bố bit rồi chứng nhận RNG an toàn | Bỏ qua khả năng đối thủ suy ra trạng thái | Đánh giá thuật toán, seed, entropy source, provider, threat model |

## 16. Tình huống thực hành: hai máy chủ sinh trùng khóa sau restore

Giả sử một dịch vụ Java triển khai trong môi trường thử nghiệm có đoạn khởi tạo:

~~~java
// CỐ TÌNH SAI: không sử dụng để tạo secret.
java.util.Random random =
    new java.util.Random(System.currentTimeMillis());
byte[] keyBytes = new byte[32];
random.nextBytes(keyBytes);
~~~

Hai máy khởi động vào khoảng thời gian gần nhau có thể có seed dễ đoán hoặc trùng nhau. Khi đó private key/DEK tạo ra không đáp ứng yêu cầu bí mật, dù mảng đầu ra dài 32 byte.

**Phân tích sự cố:**

1. Tìm tất cả đường sinh khóa, token hoặc secret có sử dụng **Random, seed từ timestamp, snapshot trạng thái hoặc nguồn giả ngẫu nhiên không dành cho mật mã**.
2. Xác định giai đoạn code lỗi đã chạy và **danh sách key ID/version, DEK, token hoặc signing key** có thể bị ảnh hưởng.
3. Chặn code cũ sinh secret mới; chuyển sang **SecureRandom/KeyGenerator/KMS** phù hợp.
4. **Thay khóa nghi yếu** thay vì chỉ đổi tên key ID. Với DEK có thể cần mã hóa lại dữ liệu; với signing key cần thay private/public key và cập nhật verifier.
5. Kiểm soát những bản mã, chứng từ hoặc session đã phát hành bằng khóa nghi yếu. Không kết luận dữ liệu đã an toàn chỉ vì RNG đã được sửa.
6. Kiểm tra lại quá trình deploy, restore và monitoring; thêm kiểm tra mã nguồn hoặc review API để ngăn tái diễn.
7. Ghi audit về phạm vi tác động, quyền sử dụng khóa, rotation/revocation và kết quả chuyển đổi.

**Cách đúng trong mã Java:**

~~~java
import java.security.SecureRandom;

SecureRandom rng = new SecureRandom();
byte[] secret = new byte[32];
rng.nextBytes(secret);
~~~

Mã tốt ở trên còn cần **xác nhận lựa chọn provider/môi trường**, vòng đời secret và quyền truy cập. Nếu secret là AES key, có thể dùng **KeyGenerator** để cho provider tạo khóa đúng thuật toán.

## 17. Câu hỏi tự kiểm tra

**Câu 1. Entropy có nghĩa là một chuỗi phải trông lộn xộn không?**

**Trả lời:** Không. Entropy là đặc tính của phân bố và khả năng dự đoán. Một chuỗi nhìn ngẫu nhiên vẫn có thể được tạo từ seed cố định.

**Câu 2. SHA-256(timestamp) tạo ra chuỗi 256 bit có nghĩa là khóa ấy có 256 bit entropy?**

**Trả lời:** Không. Entropy bị giới hạn bởi bất định thực sự của timestamp; hash không bổ sung entropy độc lập.

**Câu 3. Min-entropy khác Shannon entropy ở đâu?**

**Trả lời:** Shannon entropy biểu thị bất định trung bình; min-entropy tập trung vào xác suất của kết quả dễ đoán nhất, phù hợp với đánh giá bảo thủ cho bí mật.

**Câu 4. SecureRandom có thực sự tạo byte ngẫu nhiên vô điều kiện không?**

**Trả lời:** Nó cung cấp API CSPRNG theo provider. An toàn phụ thuộc thuật toán, trạng thái, nguồn seed và môi trường; không tự bảo đảm tuyệt đối trong mọi cấu hình.

**Câu 5. Một AES key 256 bit từ mật khẩu "123456" có mạnh không?**

**Trả lời:** Không. Kể cả dùng SHA-256 tạo 256 bit, người có thể đoán mật khẩu sẽ tìm được khóa; password KDF chỉ làm tăng chi phí thử đoán, không làm password có entropy bằng khóa ngẫu nhiên.

**Câu 6. AES-GCM nonce có bắt buộc bí mật và không dự đoán được không?**

**Trả lời:** Không nhất thiết. AES-GCM yêu cầu nonce **không trùng dưới cùng khóa**; bộ đếm được quản lý an toàn có thể phù hợp.

**Câu 7. Nonce k trong ECDSA có thể công khai như nonce AES-GCM không?**

**Trả lời:** Không. k ECDSA phải giữ bí mật theo cơ chế ký; lộ hoặc tái sử dụng sai có thể làm lộ private key.

**Câu 8. Nếu hai key alias khác nhau trỏ cùng key material, có hai phạm vi nonce độc lập không?**

**Trả lời:** Không. Với AES-GCM, phạm vi uniqueness gắn với vật liệu key thực tế.

**Câu 9. Reseed CSPRNG có làm các khóa yếu đã sinh trước đây trở nên an toàn không?**

**Trả lời:** Không. Phải đánh giá và thay các khóa có thể được sinh từ trạng thái RNG yếu.

**Câu 10. Tạo 1000 token đều khác nhau có chứng minh RNG có entropy cao không?**

**Trả lời:** Không. Một bộ đếm dự đoán được cũng tạo 1000 giá trị khác nhau.

**Câu 11. HSM có tự nâng entropy của một khóa yếu được import vào nó không?**

**Trả lời:** Không. HSM có thể bảo vệ và sử dụng key material, nhưng không làm vật liệu nhập vào vốn dễ đoán trở thành ngẫu nhiên mạnh.

**Câu 12. Khi secret của DRBG bị lộ, có thể chỉ thay quyền IAM không?**

**Trả lời:** Cần đánh giá trạng thái và các secret liên quan, khả năng dự đoán đầu ra, thay khóa và reseed/khởi tạo lại theo thiết kế; chỉ thay IAM chưa chắc đủ.

**Câu 13. Salt trong password KDF có cần 256 bit entropy vì SHA-256 dài 256 bit không?**

**Trả lời:** Không có sự tương ứng trực tiếp như vậy. Salt cần đáp ứng tính ngẫu nhiên/duy nhất theo cơ chế và tiêu chuẩn password hashing; không phải secret key.

**Câu 14. Vì sao entropy và IAM đều quan trọng trong KMS?**

**Trả lời:** Entropy giúp sinh key khó đoán; IAM ngăn dùng key trái phép. Có key mạnh mà cấp quyền decrypt/sign quá rộng vẫn có thể gây lộ dữ liệu hoặc giả mạo.

## 18. Checklist khi thiết kế hệ thống sinh khóa

Trước khi đưa hệ thống vào sản xuất, hãy xác định:

- **Nguồn:** OS CSPRNG, provider/HSM và cơ chế seed/reseed nào đang được dùng?
- **Entropy:** nguồn entropy và cách ước lượng mức bất định có đáng tin, phù hợp môi trường hay không?
- **Khởi động:** việc tạo khóa có xảy ra trước khi RNG sẵn sàng, sau VM clone, restore hoặc fork không?
- **Thuật toán:** đang dùng SecureRandom/KeyGenerator hay vô tình dùng java.util.Random, timestamp hoặc hàm băm mật khẩu?
- **Loại bí mật:** key, token, salt, nonce và ECDSA k có yêu cầu khác nhau thế nào?
- **Phân tách:** mỗi môi trường/tenant/mục đích có ranh giới key phù hợp và key version rõ ràng chưa?
- **Giới hạn:** AES-GCM nonce uniqueness có được bảo vệ xuyên restart, failover và nhiều writer không?
- **KMS/HSM:** nguồn sinh khóa, chính sách export, IAM, audit, vòng đời và việc nhập key có được quản lý không?
- **Sự cố:** nếu phát hiện lỗi RNG, có cách xác định khóa ảnh hưởng, rotate/revoke, re-encrypt/re-sign và xử lý dữ liệu lịch sử không?
- **Kiểm chứng:** những khẳng định về nguồn entropy/DRBG có được hỗ trợ bằng tài liệu provider, tiêu chuẩn và kiểm tra cần thiết không?

**Ghi nhớ:** **Entropy là mức bất định của nguồn, không phải số bit hiển thị ở đầu ra.** CSPRNG/DRBG an toàn sử dụng entropy thích hợp để sinh khóa và secret khó đoán; chúng không biến một seed dễ đoán thành bí mật mạnh bằng cách kéo dài chuỗi bit. Trong quản lý khóa, entropy phải được xem xét cùng **nguồn sinh, KMS/HSM, vòng đời DEK/KEK, chữ ký số, AES-GCM nonce, phân quyền, kiểm toán và ứng phó sự cố**.
