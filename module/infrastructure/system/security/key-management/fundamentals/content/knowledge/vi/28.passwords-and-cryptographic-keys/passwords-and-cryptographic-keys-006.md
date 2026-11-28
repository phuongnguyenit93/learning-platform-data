# Key derivation từ passphrase

Key derivation từ passphrase là quá trình dùng một mật khẩu hoặc cụm từ bí mật do con người ghi nhớ làm đầu vào cho Key Derivation Function (KDF), từ đó tạo ra khóa mật mã có độ dài và định dạng phù hợp. KDF được thiết kế để làm cho mỗi lần thử đoán passphrase tốn tài nguyên hơn so với một phép băm thông thường. Quá trình này thường dùng khi mã hóa tệp, sao lưu, dữ liệu cục bộ hoặc khi cần tạo password verifier để xác minh thông tin đăng nhập.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, chủ đề này kết nối việc tạo khóa với lưu trữ, sử dụng, sao lưu, khôi phục và xoay vòng. Passphrase dễ ghi nhớ nhưng thường có entropy thấp hơn khóa được sinh ngẫu nhiên. Vì vậy, thiết kế phải kết hợp passphrase đủ mạnh, salt ngẫu nhiên, KDF phù hợp, tham số chi phí được hiệu chỉnh và quy trình bảo vệ dữ liệu dẫn xuất.

## 1. Vì sao cần dẫn xuất khóa từ passphrase?

Một khóa AES 256 bit được sinh ngẫu nhiên có không gian khóa rất lớn. Con người khó ghi nhớ và nhập chính xác một chuỗi ngẫu nhiên dài như vậy. Ngược lại, passphrase như một câu dễ nhớ có thể được nhập lại, nhưng người dùng thường chọn cụm từ ngắn, quen thuộc hoặc có quy luật. Kẻ tấn công có thể dùng từ điển, thông tin cá nhân bị lộ và các mẫu phổ biến để đoán.

KDF giải quyết hai nhu cầu:

- Chuyển đầu vào dạng passphrase thành vật liệu khóa có độ dài xác định để dùng trong thuật toán mật mã.
- Làm chậm hoặc làm tốn tài nguyên cho mỗi lần thử passphrase, khiến tấn công đoán ngoại tuyến đắt đỏ hơn.

KDF không biến một passphrase yếu thành bí mật có entropy cao. Nếu passphrase nằm trong danh sách phổ biến hoặc dễ đoán, kẻ tấn công vẫn có thể thử đủ nhanh để tìm ra nó. Vì thế, chất lượng passphrase và chi phí KDF đều quan trọng.

## 2. Passphrase, password và entropy

Passphrase thường là một chuỗi gồm nhiều từ hoặc một câu dài. Độ dài giúp tăng khả năng chống đoán khi các thành phần được chọn ngẫu nhiên từ một tập đủ lớn. Một câu trích dẫn nổi tiếng, lời bài hát, ngày sinh hoặc câu có cấu trúc quen thuộc không nhất thiết có entropy cao chỉ vì nó dài.

Entropy phản ánh mức độ khó đoán của bí mật. Nếu người dùng chọn từng ký tự hoặc từ theo thói quen, không thể tính entropy chỉ bằng cách đếm độ dài. Passphrase được tạo từ một quy trình ngẫu nhiên, chẳng hạn chọn nhiều từ độc lập bằng bộ sinh ngẫu nhiên mật mã, có thể cung cấp entropy dễ đánh giá hơn.

Thực hành tốt:

- Khuyến khích passphrase dài, duy nhất cho từng ứng dụng hoặc bản sao lưu.
- Ưu tiên các từ được chọn ngẫu nhiên thay vì câu quen thuộc hoặc mẫu thay ký tự như a thành @.
- Không tái sử dụng passphrase đã dùng ở dịch vụ khác.
- Không đưa tên, ngày sinh, tên công ty hoặc dữ liệu công khai vào passphrase.
- Có phương án khôi phục được kiểm soát vì mất passphrase có thể đồng nghĩa mất dữ liệu đã mã hóa.

## 3. KDF hoạt động như thế nào?

KDF nhận passphrase và các tham số khác rồi thực hiện một lượng công việc được xác định để tạo đầu ra. Các tham số thường gặp:

- **Passphrase/password:** bí mật do người dùng cung cấp.
- **Salt:** giá trị ngẫu nhiên, thường công khai và riêng cho mỗi lần tạo verifier hoặc khóa.
- **Work factor:** tham số quy định chi phí tính toán, ví dụ số vòng lặp hoặc số vòng xử lý.
- **Memory cost:** lượng bộ nhớ cần dùng với các KDF memory-hard.
- **Parallelism:** mức độ xử lý song song được KDF cho phép.
- **Output length:** số bit hoặc byte cần dẫn xuất.

~~~mermaid
flowchart TD
    A[Passphrase] --> D[KDF]
    B[Salt ngẫu nhiên] --> D
    C[Tham số chi phí] --> D
    D --> E[Derived key hoặc password verifier]
    E --> F[Khóa mã hóa dữ liệu]
    E --> G[Giá trị dùng để xác minh đăng nhập]
~~~

Salt không cần giữ bí mật. Mục tiêu của salt là làm cho cùng một passphrase tạo ra kết quả khác nhau ở các bản ghi hoặc dữ liệu khác nhau, ngăn kẻ tấn công tái sử dụng bảng tính trước và làm lộ việc nhiều người dùng có cùng mật khẩu. Salt không làm tăng entropy của passphrase và không thay thế pepper.

Work factor càng cao thì mỗi lần dẫn xuất càng tốn tài nguyên. Tuy nhiên, chi phí quá cao có thể làm ứng dụng chậm, tăng tiêu thụ bộ nhớ hoặc tạo cơ hội từ chối dịch vụ nếu endpoint xác minh bị lạm dụng. Cần hiệu chỉnh theo thiết bị, tải thực tế và yêu cầu trải nghiệm.

## 4. Phân biệt KDF với hàm băm thông thường

Hàm băm mật mã như SHA-256 được thiết kế để tính nhanh. Điều đó phù hợp khi kiểm tra toàn vẹn dữ liệu lớn, nhưng không phù hợp để lưu password verifier: kẻ tấn công có thể thử hàng tỷ ứng viên nếu có phần cứng phù hợp.

KDF dành cho passphrase thêm chi phí có chủ đích:

| Cơ chế | Đặc điểm | Mục đích phù hợp |
|---|---|---|
| SHA-256 hoặc SHA-512 trực tiếp | Rất nhanh, không có salt/work factor theo mặc định | Hash dữ liệu, fingerprint; không dùng trực tiếp để lưu password verifier |
| PBKDF2 | Lặp hàm PRF như HMAC theo số vòng cấu hình | Dẫn xuất khóa và password verifier; tương thích rộng |
| scrypt | KDF memory-hard, yêu cầu bộ nhớ đáng kể | Password hashing và dẫn xuất từ bí mật có entropy thấp |
| Argon2id | KDF memory-hard, kết hợp khả năng chống tấn công qua kênh kề và GPU theo thiết kế | Lựa chọn mạnh cho password hashing khi thư viện hỗ trợ |
| bcrypt | Password hashing có cost factor, đầu ra và giới hạn đầu vào đặc thù | Xác minh mật khẩu; không phải lựa chọn tổng quát để tạo khóa tùy ý |

Không nên lặp SHA-256 thủ công để tự tạo password KDF. Dùng thuật toán chuẩn và thư viện được duy trì, với tham số được thiết lập theo khuyến nghị hiện hành của tổ chức.

## 5. Chọn KDF: PBKDF2, scrypt hay Argon2id?

**PBKDF2** dùng một hàm giả ngẫu nhiên, thường là HMAC-SHA-256, lặp theo số vòng được cấu hình. PBKDF2 có mặt rộng rãi trong JCA/JCE và nhiều nền tảng, phù hợp khi cần tương thích hoặc môi trường có yêu cầu tiêu chuẩn cụ thể. PBKDF2 chủ yếu làm tăng chi phí CPU, không phải KDF memory-hard.

**scrypt** yêu cầu bộ nhớ theo tham số N, r và p. Điều này làm cho việc chạy số lượng lớn phép đoán song song tốn bộ nhớ hơn, tăng chi phí của các cuộc tấn công bằng GPU hoặc phần cứng chuyên dụng.

**Argon2id** cho phép cấu hình memory cost, time cost và parallelism. Đây là biến thể thường được khuyến nghị cho lưu trữ password verifier khi có thư viện đáng tin cậy. Cần chọn tham số dựa trên ngân sách CPU/bộ nhớ và giới hạn của môi trường.

| Tiêu chí | PBKDF2 | scrypt | Argon2id |
|---|---|---|---|
| Chi phí CPU | Có, điều chỉnh qua iteration count | Có | Có |
| Chi phí bộ nhớ | Thấp | Cao, cấu hình được | Cao, cấu hình được |
| Hỗ trợ JCA mặc định | Thường có PBKDF2 qua SecretKeyFactory | Phụ thuộc provider/thư viện | Phụ thuộc provider/thư viện |
| Tính tương thích | Rộng | Cần thư viện hỗ trợ | Cần thư viện hỗ trợ |
| Trường hợp thường chọn | Tương thích, chuẩn hóa hoặc dẫn xuất khóa | Cần KDF memory-hard | Lưu password verifier mới khi có triển khai phù hợp |

Không có một bộ tham số phù hợp cho mọi hệ thống. Với password verifier, cần theo khuyến nghị bảo mật đang áp dụng và đo thời gian trên cấu hình production. Với khóa mã hóa dữ liệu, phải cân bằng khả năng mở khóa trên các thiết bị được hỗ trợ trong suốt thời gian lưu trữ dữ liệu.

## 6. Salt, pepper và tham số phải lưu

### Salt

Salt nên được tạo ngẫu nhiên bằng SecureRandom, thường tối thiểu 16 byte cho các thiết kế mới. Salt có thể lưu cùng ciphertext hoặc password verifier. Không dùng một salt cố định cho mọi người dùng, không dùng tên đăng nhập làm salt và không tái sử dụng salt chỉ vì tiện cấu hình.

~~~java
import java.security.SecureRandom;

byte[] salt = new byte[16];
new SecureRandom().nextBytes(salt);
~~~

Đoạn mã trên minh họa việc tạo salt; trong ứng dụng thực tế có thể dùng SecureRandom mặc định do JCA cung cấp nếu provider và cấu hình đã được tin cậy. Điều quan trọng là dùng nguồn ngẫu nhiên mật mã phù hợp, không dùng java.util.Random.

### Pepper

Pepper là bí mật bổ sung được giữ tách biệt khỏi cơ sở dữ liệu hoặc ciphertext. Với password verifier, pepper có thể được bảo vệ trong secret manager hoặc HSM/KMS. Nếu dữ liệu verifier bị đánh cắp nhưng pepper không bị lộ, kẻ tấn công gặp thêm một rào cản.

Pepper phải có quy trình phân phối, xoay vòng và khôi phục. Mất pepper có thể khiến không thể xác minh mật khẩu cũ hoặc giải mã dữ liệu phụ thuộc nó. Không đặt pepper trong cùng file hoặc cùng cơ sở dữ liệu với salt và verifier rồi xem nó như một bí mật độc lập.

### Metadata

Để có thể xác minh hoặc dẫn xuất lại, cần lưu tối thiểu:

- Tên KDF và phiên bản/định danh thuật toán.
- Salt.
- Work factor và các tham số liên quan như memory cost, parallelism.
- Output length.
- Với mã hóa dữ liệu: thuật toán mã hóa, nonce/IV, tag và thông tin phiên bản định dạng.

Các metadata này thường không phải bí mật, nhưng phải được kiểm tra giới hạn trước khi sử dụng. Nếu attacker có thể sửa metadata, họ có thể thử hạ thấp work factor để giảm chi phí đoán hoặc gây tiêu thụ tài nguyên quá mức. Với dữ liệu AEAD, nên ràng buộc metadata vào Additional Authenticated Data (AAD) hoặc cơ chế xác thực định dạng tương đương.

## 7. Dẫn xuất khóa bằng PBKDF2 trong Java

JCA cung cấp PBKDF2 qua SecretKeyFactory. Tên thuật toán thường dùng là PBKDF2WithHmacSHA256. Ví dụ sau dẫn xuất khóa AES 256 bit từ passphrase và salt:

~~~java
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

public final class PassphraseKdf {
    // Các ngưỡng minh họa; cần hiệu chỉnh theo policy và benchmark của hệ thống.
    private static final int MIN_ITERATIONS = 600_000;
    private static final int MAX_ITERATIONS = 2_000_000;

    private PassphraseKdf() {
    }

    public static SecretKey deriveAesKey(
            char[] passphrase,
            byte[] salt,
            int iterations) throws GeneralSecurityException {

        if (passphrase == null || passphrase.length == 0) {
            throw new IllegalArgumentException("Passphrase is required");
        }
        if (salt == null || salt.length < 16) {
            throw new IllegalArgumentException("Salt must be at least 16 bytes");
        }
        if (iterations < MIN_ITERATIONS || iterations > MAX_ITERATIONS) {
            throw new IllegalArgumentException("Iteration count is outside policy bounds");
        }

        PBEKeySpec spec = new PBEKeySpec(
                passphrase,
                salt,
                iterations,
                256);
        byte[] keyBytes = null;
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance(
                    "PBKDF2WithHmacSHA256");
            keyBytes = factory.generateSecret(spec).getEncoded();
            return new SecretKeySpec(keyBytes, "AES");
        } finally {
            spec.clearPassword();
            if (keyBytes != null) {
                Arrays.fill(keyBytes, (byte) 0);
            }
        }
    }
}
~~~

Mã minh họa kiểm tra passphrase, salt và iteration count trước khi dẫn xuất. Hai ngưỡng trong ví dụ chỉ là giá trị chính sách minh họa, không phải con số cố định cho mọi thiết bị hoặc mọi thời điểm. Trong production, cần benchmark và hiệu chỉnh giới hạn trên/dưới, không nhận một giá trị tùy ý từ request. Khi đọc metadata cũ, phải áp dụng giới hạn trước khi chạy KDF để tránh tấn công tiêu thụ tài nguyên.

PBEKeySpec giữ bản sao của passphrase; gọi clearPassword giúp xóa bản sao do spec quản lý sau khi dùng. Ứng dụng vẫn cần xóa mảng char[] gốc trong finally sau khi không còn cần, đồng thời hạn chế chuyển passphrase thành String vì String bất biến và khó chủ động xóa khỏi bộ nhớ. Việc ghi đè mảng không bảo đảm mọi bản sao trong JVM đã biến mất.

### Chọn iteration count

Ví dụ không cố định một con số cho mọi môi trường. Hãy benchmark trên phần cứng production và chọn chi phí sao cho một lần dẫn xuất đủ chậm để làm tốn kém đoán ngoại tuyến nhưng vẫn đáp ứng độ trễ và tải hợp lệ. Ghi lại iteration count cùng verifier/ciphertext để sau này có thể nâng cấp.

Khi chính sách yêu cầu mức chi phí mới cao hơn, có thể dẫn xuất lại sau khi người dùng xác thực thành công, rồi cập nhật verifier với salt và tham số mới. Với dữ liệu đã mã hóa, cần giải mã bằng khóa dẫn xuất cũ và mã hóa lại bằng khóa mới; không chỉ sửa metadata.

## 8. Dùng khóa dẫn xuất để mã hóa dữ liệu

Một ứng dụng có thể dùng passphrase để tạo khóa AES-GCM, sau đó mã hóa dữ liệu. Mỗi lần tạo dữ liệu mã hóa mới cần salt mới và nonce/IV mới. Salt và nonce có thể lưu cạnh ciphertext vì chúng không phải bí mật.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

char[] passphrase = obtainPassphrase();
byte[] salt = new byte[16];
byte[] nonce = new byte[12];
SecureRandom random = new SecureRandom();
random.nextBytes(salt);
random.nextBytes(nonce);

try {
    SecretKey key = PassphraseKdf.deriveAesKey(
            passphrase,
            salt,
            configuredIterations);

    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(128, nonce));

    byte[] ciphertext = cipher.doFinal(
            plaintext.getBytes(StandardCharsets.UTF_8));
    // Lưu version, KDF, salt, iterations, nonce và ciphertext.
} finally {
    java.util.Arrays.fill(passphrase, '\0');
}
~~~

Đây là ví dụ minh họa luồng mã hóa; obtainPassphrase, plaintext, configuredIterations và nơi lưu metadata cần được ứng dụng cung cấp. Nếu dùng AAD, phải gọi updateAAD trước doFinal và cung cấp lại đúng AAD khi giải mã. Nên ràng buộc version định dạng, thuật toán KDF và tham số KDF vào AAD để phát hiện việc sửa metadata.

AES-GCM yêu cầu nonce duy nhất dưới cùng một khóa. Dùng nonce 12 byte là lựa chọn phổ biến; không tái sử dụng nonce khi cùng passphrase và salt tạo ra cùng khóa. Nếu mã hóa nhiều bản ghi bằng cùng một khóa, cần thiết kế bộ đếm hoặc cơ chế cấp nonce đảm bảo không trùng. Với mỗi đối tượng mã hóa mới, salt mới thường tạo ra khóa mới, nhưng nonce vẫn phải tuân theo quy tắc của GCM.

Khi giải mã, dùng đúng KDF, salt, iteration count, nonce và AAD đã lưu. Nếu passphrase sai hoặc ciphertext/metadata bị sửa, xác minh tag GCM sẽ thất bại. Không trả plaintext trước khi xác minh tag hoàn tất.

## 9. Dẫn xuất khóa khác với lưu password verifier

Hai tình huống có mục tiêu khác nhau:

| Tình huống | Dữ liệu lưu | Mục đích |
|---|---|---|
| Mã hóa tệp bằng passphrase | KDF name, salt, tham số, nonce/IV, ciphertext và tag | Dẫn xuất lại đúng khóa khi người dùng cần giải mã |
| Xác minh mật khẩu đăng nhập | KDF name, salt, tham số và password verifier | So sánh kết quả dẫn xuất khi người dùng nhập mật khẩu |

Với password verifier, không cần lưu khóa AES và không cần giải mã mật khẩu. Khi đăng nhập, hệ thống chạy KDF với passphrase vừa nhập và salt/tham số đã lưu, rồi so sánh kết quả với verifier đã lưu bằng phép so sánh phù hợp cho dữ liệu mật mã, chẳng hạn MessageDigest.isEqual.

Với dữ liệu mã hóa bằng passphrase, hệ thống phải có khả năng dẫn xuất lại khóa để giải mã. Vì vậy, mất passphrase có thể khiến dữ liệu không thể khôi phục. Không có cách khôi phục an toàn nếu không còn passphrase hoặc một cơ chế recovery key đã được thiết kế trước.

## 10. Dẫn xuất nhiều khóa và phân tách mục đích

Nếu ứng dụng cần nhiều khóa từ cùng một passphrase, không nên dùng cùng một mảng byte cho mọi mục đích. Có thể dẫn xuất một khóa gốc bằng KDF chống đoán, rồi dùng KDF thứ cấp như HKDF để tạo các khóa riêng theo context:

~~~text
passphrase + salt + work factor
              |
              v
         PBKDF2 / Argon2id
              |
              v
         root key material
              |
              v
          HKDF-Expand
          /          \
         v            v
    encryption key  authentication key
    context=A       context=B
~~~

HKDF phù hợp để mở rộng và phân tách vật liệu khóa đã có entropy đủ tốt; HKDF không thay thế KDF chậm dành cho passphrase yếu. Không dùng HKDF trực tiếp với passphrase con người rồi cho rằng đã chống được tấn công đoán ngoại tuyến.

Context phải được định nghĩa ổn định và không trùng giữa mục đích, phiên bản giao thức hoặc hướng truyền. Cần dùng thư viện/provider có triển khai HKDF chuẩn nếu Java runtime không cung cấp API phù hợp.

## 11. Unicode, encoding và khả năng tương thích

Hai passphrase hiển thị giống nhau có thể có biểu diễn Unicode khác nhau. Ví dụ một ký tự có thể được mã hóa bằng một code point dựng sẵn hoặc bằng ký tự cơ sở kết hợp dấu. Nếu các hệ thống xử lý khác nhau, chúng có thể dẫn xuất khóa khác nhau dù người dùng nhìn thấy cùng một cụm từ.

Với ứng dụng đa nền tảng, cần quy định rõ:

- Quy tắc chuẩn hóa Unicode, chẳng hạn NFC, nếu ứng dụng quyết định chuẩn hóa.
- Cách chuyển passphrase thành byte theo chuẩn KDF và hành vi của thư viện/provider.
- Quy tắc xử lý khoảng trắng đầu/cuối, xuống dòng và ký tự không hợp lệ.
- Phiên bản định dạng metadata để thay đổi quy tắc trong tương lai.

Không tự ý trim hoặc đổi chữ hoa/chữ thường nếu giao thức không quy định. Việc chuẩn hóa hoặc biến đổi passphrase phải nhất quán khi tạo và khi xác minh/giải mã. Nếu dùng PBEKeySpec, cần xác nhận provider và các nền tảng liên quan có cùng cách diễn giải đầu vào để bảo đảm tương thích.

## 12. Thay đổi passphrase, nâng cấp KDF và khôi phục

### Đổi passphrase cho dữ liệu mã hóa

Để đổi passphrase, ứng dụng cần giải mã dữ liệu bằng passphrase cũ, xác minh tag thành công, sau đó tạo salt và nonce mới, dẫn xuất khóa từ passphrase mới và mã hóa lại. Không thể chỉ thay salt hoặc tham số KDF trong header vì khóa mới sẽ khác khóa đã dùng để mã hóa.

### Nâng cấp tham số KDF

Khi work factor hiện tại không còn đủ cao, có thể nâng cấp theo hai cách:

- **Password verifier:** sau lần xác thực thành công, tạo salt mới và verifier mới với tham số mạnh hơn, rồi cập nhật bản ghi.
- **Dữ liệu mã hóa:** giải mã bằng tham số cũ và mã hóa lại bằng tham số mới; lưu metadata mới cùng ciphertext mới.

Phải duy trì khả năng đọc định dạng cũ trong giai đoạn chuyển đổi và có kế hoạch loại bỏ phiên bản yếu theo thời hạn. Không được hạ tham số chỉ để hỗ trợ một thiết bị cũ mà không đánh giá rủi ro.

### Recovery

Nếu dữ liệu quan trọng được mã hóa bằng passphrase, cân nhắc recovery key hoặc cơ chế escrow có kiểm soát. Recovery key phải có entropy cao, được lưu riêng, phân quyền và kiểm toán. Thiết kế recovery cần bảo đảm người vận hành không thể tùy tiện giải mã dữ liệu ngoài quy trình phê duyệt.

## 13. Rủi ro và lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng SHA-256 trực tiếp với passphrase | Tấn công đoán ngoại tuyến rất nhanh | Dùng PBKDF2, scrypt hoặc Argon2id với salt và chi phí phù hợp |
| Dùng passphrase phổ biến | KDF không ngăn được đoán đúng một bí mật yếu | Yêu cầu passphrase dài, duy nhất và khó đoán |
| Dùng salt cố định hoặc dùng chung | Cho phép tái sử dụng bảng tính trước và phát hiện trùng passphrase | Tạo salt ngẫu nhiên riêng cho mỗi đối tượng |
| Đặt pepper cạnh verifier/ciphertext | Pepper không còn là bí mật độc lập | Lưu pepper trong secret manager hoặc HSM/KMS |
| Chọn work factor quá thấp | Mỗi lần đoán có chi phí nhỏ | Benchmark và nâng cấp tham số định kỳ |
| Chọn work factor quá cao | Tăng độ trễ hoặc tạo nguy cơ từ chối dịch vụ | Giới hạn tham số đầu vào và hiệu chỉnh theo tải |
| Không lưu KDF metadata | Không thể tái tạo khóa hoặc xác minh verifier | Lưu thuật toán, salt, tham số và phiên bản định dạng |
| Sửa metadata không có xác thực | Có thể hạ work factor hoặc làm sai khóa | Ràng buộc metadata bằng AAD/chữ ký hoặc định dạng được xác thực |
| Tái sử dụng nonce AES-GCM | Có thể làm lộ thông tin và phá vỡ bảo mật AEAD | Bảo đảm nonce duy nhất dưới cùng khóa |
| Thay passphrase nhưng không mã hóa lại | Không thể giải mã bằng passphrase mới | Giải mã và mã hóa lại với salt/nonce mới |
| Mất passphrase và không có recovery | Dữ liệu có thể mất vĩnh viễn | Thiết kế backup/recovery trước khi mã hóa dữ liệu quan trọng |

## 14. Checklist triển khai

- [ ] Dùng passphrase dài, duy nhất và có entropy tốt.
- [ ] Chọn KDF phù hợp: Argon2id hoặc scrypt khi có triển khai tin cậy; PBKDF2 khi cần tương thích hoặc theo chính sách.
- [ ] Tạo salt ngẫu nhiên riêng, thường tối thiểu 16 byte cho thiết kế mới.
- [ ] Hiệu chỉnh work factor/memory cost trên phần cứng production và cập nhật theo vòng đời.
- [ ] Lưu KDF name, salt, tham số, output length và version cùng dữ liệu cần xác minh/giải mã.
- [ ] Kiểm tra giới hạn metadata trước khi chạy KDF để tránh lạm dụng CPU/bộ nhớ.
- [ ] Giữ pepper tách biệt trong secret manager hoặc HSM/KMS nếu sử dụng.
- [ ] Dùng khóa dẫn xuất với AEAD như AES-GCM và quản lý nonce đúng quy tắc.
- [ ] Xác thực metadata bằng AAD hoặc cơ chế toàn vẹn tương đương.
- [ ] Không dùng KDF chậm để thay thế việc tạo khóa ngẫu nhiên cho hệ thống không cần passphrase.
- [ ] Có quy trình đổi passphrase, nâng cấp tham số và recovery được kiểm thử.
- [ ] Xóa bản sao passphrase và key material khỏi bộ nhớ khi không còn cần theo khả năng runtime.

Key derivation từ passphrase giúp tạo khóa có thể tái tạo từ bí mật người dùng mà không lưu trực tiếp khóa trong bộ nhớ lâu dài. Mức an toàn phụ thuộc entropy passphrase, KDF, salt, chi phí tính toán/bộ nhớ, tính toàn vẹn metadata và quy trình khôi phục. KDF làm tăng chi phí đoán; nó không thể bù cho passphrase dễ đoán hoặc thay thế việc quản lý khóa đúng vòng đời.
