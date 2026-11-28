# Password verification

**Password verification** là quá trình kiểm tra mật khẩu người dùng vừa nhập có khớp với thông tin xác minh đã lưu hay không. Hệ thống an toàn không lưu mật khẩu gốc để so sánh trực tiếp. Thay vào đó, hệ thống lưu kết quả của một thuật toán password hashing chuyên dụng cùng salt và các tham số cần thiết. Khi đăng nhập, hệ thống tính lại giá trị từ mật khẩu được nhập rồi so sánh với giá trị đã lưu.

Mật khẩu và khóa mật mã có vai trò khác nhau. Mật khẩu do con người ghi nhớ, thường có entropy thấp và dễ bị đoán; khóa mật mã nên được sinh từ nguồn ngẫu nhiên mật mã và có độ mạnh phù hợp với thuật toán. Vì vậy, cơ chế lưu mật khẩu đăng nhập cần chống dò ngoại tuyến, còn khóa dùng để mã hóa, ký hoặc xác thực dữ liệu cần được quản lý trong KeyStore, KMS hoặc HSM theo vòng đời riêng.

Trong Java, có thể dùng **SecretKeyFactory** và **PBEKeySpec** để triển khai PBKDF2. Với hệ thống mới, nên cân nhắc Argon2id hoặc thuật toán password hashing hiện đại khác theo chính sách triển khai; PBKDF2 phù hợp khi cần hỗ trợ rộng hoặc đáp ứng yêu cầu môi trường được kiểm soát.

## 1. Vì sao không lưu mật khẩu gốc?

Nếu cơ sở dữ liệu lưu mật khẩu dạng rõ, bất kỳ ai đọc được bản sao dữ liệu đều có thể đăng nhập bằng tài khoản bị lộ. Mã hóa mật khẩu bằng một khóa dùng chung cũng tạo ra rủi ro lớn: nếu kẻ tấn công lấy được cả cơ sở dữ liệu và khóa giải mã, toàn bộ mật khẩu có thể bị khôi phục.

Password verification cần một cách lưu trữ cho phép kiểm tra mật khẩu nhưng không cung cấp phép đảo ngược để lấy lại mật khẩu gốc. Password hashing thực hiện mục tiêu này bằng hàm dẫn xuất có chủ đích chậm hoặc tốn bộ nhớ.

Luồng cơ bản:

1. Khi đăng ký hoặc đổi mật khẩu, hệ thống tạo salt ngẫu nhiên riêng cho tài khoản.
2. Hệ thống chạy thuật toán password hashing với mật khẩu, salt và tham số chi phí.
3. Hệ thống lưu tên thuật toán, phiên bản, tham số, salt và kết quả băm.
4. Khi đăng nhập, hệ thống lấy bản ghi xác minh, chạy lại thuật toán với mật khẩu được nhập và cùng tham số.
5. Hệ thống so sánh kết quả mới với kết quả đã lưu bằng phép so sánh phù hợp.

Cơ sở dữ liệu chỉ lưu thông tin cần thiết để kiểm tra mật khẩu. Không có bước giải mã ngược để khôi phục mật khẩu người dùng.

## 2. Password hashing khác hash thông thường thế nào?

Một hàm băm mật mã tổng quát như SHA-256 được thiết kế để tính nhanh. Tốc độ cao hữu ích cho kiểm tra toàn vẹn dữ liệu và các giao thức mật mã, nhưng lại có lợi cho kẻ tấn công khi họ thử hàng tỷ mật khẩu phỏng đoán trên bản sao cơ sở dữ liệu bị đánh cắp.

Password hashing dùng thuật toán dẫn xuất có chủ đích tốn tài nguyên. Một số thuật toán còn tiêu thụ nhiều bộ nhớ nhằm làm cho việc mở rộng tấn công bằng GPU hoặc phần cứng chuyên dụng đắt đỏ hơn.

| Cơ chế | Mục đích | Có phù hợp để lưu mật khẩu đăng nhập? |
|---|---|---|
| SHA-256 hoặc SHA-512 đơn lẻ | Hash tổng quát, kiểm tra toàn vẹn | Không |
| SHA-256(password + salt) | Hash nhanh có salt | Không đủ mạnh cho password storage |
| PBKDF2 | KDF dựa trên HMAC với số vòng lặp cấu hình | Có, khi cấu hình đủ mạnh và phù hợp chính sách |
| bcrypt | Password hashing với cost factor | Có |
| scrypt | KDF/password hashing tiêu thụ bộ nhớ | Có |
| Argon2id | Password hashing memory-hard, cân bằng bảo vệ trước nhiều kiểu tấn công | Thường là lựa chọn ưu tiên cho hệ thống mới |

Không tự tạo thuật toán bằng cách lặp SHA-256 nhiều lần hoặc ghép chuỗi khóa vào hash. Hãy dùng một thuật toán password hashing/KDF đã được phân tích công khai và thư viện triển khai được duy trì.

## 3. Salt, pepper và tham số chi phí

### 3.1. Salt

Salt là dữ liệu ngẫu nhiên riêng cho mỗi mật khẩu được băm. Salt không cần giữ bí mật và thường được lưu cùng bản ghi password hash.

Salt có ba vai trò:

- Làm cho cùng một mật khẩu tạo ra các kết quả khác nhau giữa các tài khoản hoặc các lần đổi mật khẩu.
- Ngăn kẻ tấn công dùng một bảng tra cứu hash dựng sẵn cho tất cả tài khoản.
- Buộc kẻ tấn công phải tính toán riêng cho từng salt khi thử mật khẩu.

Salt phải được sinh từ SecureRandom hoặc nguồn ngẫu nhiên mật mã tương đương. Không dùng username, email, ngày sinh hoặc giá trị cố định làm salt. Salt nên có độ dài đủ lớn; 16 byte ngẫu nhiên là lựa chọn phổ biến.

### 3.2. Pepper

Pepper là bí mật bổ sung dùng chung cho một phạm vi ứng dụng hoặc hệ thống. Không giống salt, pepper phải được giữ bí mật và lưu tách khỏi cơ sở dữ liệu chứa password hash, ví dụ trong KMS, HSM hoặc secret manager.

Pepper có thể làm giảm khả năng tấn công nếu chỉ cơ sở dữ liệu bị lộ. Tuy nhiên, nó làm tăng độ phức tạp vận hành: nếu pepper mất, hệ thống có thể không xác minh được các bản ghi cũ; nếu pepper bị lộ cùng cơ sở dữ liệu, lợi ích bảo vệ giảm đáng kể.

Nếu dùng pepper, cần có phiên bản pepper, quy trình xoay vòng và cách xác minh bản ghi cũ trong giai đoạn chuyển tiếp. Không ghi pepper vào log, mã nguồn, biến cấu hình công khai hoặc cùng bảng password hash.

### 3.3. Tham số chi phí

Thuật toán password hashing thường có tham số điều khiển chi phí:

- **PBKDF2:** số vòng lặp (iteration count).
- **bcrypt:** cost factor, ảnh hưởng số vòng tính toán.
- **scrypt:** các tham số N, r, p, điều khiển chi phí CPU và bộ nhớ.
- **Argon2id:** memory cost, time cost và parallelism.

Chi phí cần đủ cao để làm chậm tấn công ngoại tuyến, nhưng vẫn đáp ứng độ trễ đăng nhập và năng lực máy chủ. Hãy benchmark trên phần cứng thật, dự trù tải đồng thời và giới hạn tốc độ đăng nhập để tránh tạo điểm nghẽn hoặc DoS.

Tham số cần được lưu cùng kết quả hash. Khi chính sách tăng chi phí theo thời gian, hệ thống có thể xác minh bản ghi cũ bằng tham số đã lưu rồi nâng cấp bản ghi sau lần đăng nhập thành công.

## 4. Chọn thuật toán password hashing

**Argon2id** thường là lựa chọn ưu tiên cho hệ thống mới nếu nền tảng và chính sách cho phép. Đây là biến thể kết hợp khả năng chống tấn công side-channel của Argon2i và đặc tính chống dò của Argon2d. Nó cho phép cấu hình bộ nhớ, thời gian và mức song song.

**scrypt** cũng là một lựa chọn memory-hard đã được sử dụng rộng rãi. **bcrypt** phù hợp với nhiều hệ thống hiện hữu, nhưng cần chú ý giới hạn độ dài đầu vào theo cách triển khai và phiên bản thư viện.

**PBKDF2-HMAC-SHA-256** có lợi thế tương thích rộng trong hệ sinh thái Java và các môi trường có yêu cầu tuân thủ nhất định. Khi sử dụng PBKDF2, phải chọn iteration count đủ cao theo chuẩn và chính sách hiện hành, đồng thời benchmark để bảo đảm máy chủ đáp ứng tải.

Không nên chọn thuật toán chỉ dựa vào tên hoặc giá trị mặc định của thư viện. Cần kiểm tra:

- Thuật toán có được duy trì và được chính sách bảo mật chấp thuận không?
- Thư viện có được cập nhật, kiểm thử và sử dụng rộng rãi không?
- Có thể lưu phiên bản thuật toán và tham số trong bản ghi không?
- Có thể nâng cấp tham số và di chuyển thuật toán mà không buộc toàn bộ người dùng đổi mật khẩu không?
- Môi trường có yêu cầu FIPS hoặc giới hạn provider hay không?

JCA không chuẩn hóa một dịch vụ password hashing Argon2id hoặc bcrypt như cách nhiều provider cung cấp PBKDF2. Nếu chọn Argon2id, bcrypt hoặc scrypt, hãy dùng thư viện Java chuyên dụng, đáng tin cậy và được cập nhật. Không tự cài đặt thuật toán.

## 5. Quy trình xác minh mật khẩu

Khi người dùng đăng nhập, hệ thống cần thực hiện các bước theo thứ tự:

1. Kiểm tra đầu vào theo chính sách mật khẩu đã công bố. Nếu hệ thống áp dụng chuẩn hóa Unicode, phải dùng cùng một quy tắc khi tạo và xác minh mật khẩu. Không âm thầm cắt ngắn mật khẩu.
2. Tìm bản ghi tài khoản và lấy thuật toán, tham số, salt, hash và phiên bản pepper nếu có.
3. Kiểm tra bản ghi có định dạng hợp lệ; giới hạn các tham số chi phí trong miền được chấp nhận để tránh một bản ghi bị sửa có thể ép máy chủ tiêu tốn tài nguyên quá mức.
4. Tính lại password hash từ mật khẩu người dùng nhập.
5. So sánh kết quả bằng phép so sánh phù hợp, không dùng so sánh chuỗi thông thường.
6. Nếu xác minh thành công và bản ghi dùng thuật toán hoặc tham số cũ, tính lại hash theo chính sách hiện tại và cập nhật bản ghi.
7. Ghi nhận kết quả xác thực ở mức cần thiết, không ghi mật khẩu, hash đầy đủ hoặc pepper vào log.

Nếu tài khoản không tồn tại, hệ thống có thể thực hiện một phép tính giả với tham số tương đương để giảm khác biệt thời gian giữa tài khoản tồn tại và không tồn tại. Thông báo lỗi bên ngoài nên chung chung, ví dụ “Tên đăng nhập hoặc mật khẩu không đúng”, để hạn chế dò tìm tài khoản.

## 6. Triển khai PBKDF2-HMAC-SHA-256 trong Java

Ví dụ sau minh họa tạo salt, dẫn xuất verifier bằng PBKDF2 và lưu bản ghi theo định dạng có phiên bản. Số vòng lặp 600.000 chỉ là giá trị minh họa để giải thích cấu trúc; cần đo hiệu năng và điều chỉnh theo hướng dẫn hiện hành, chính sách tổ chức và môi trường triển khai.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordVerifier {
    private static final int SALT_BYTES = 16;
    private static final int HASH_BITS = 256;
    private static final int CURRENT_ITERATIONS = 600_000;
    private static final int MAX_ACCEPTED_ITERATIONS = 2_000_000;

    private static final SecureRandom RANDOM = new SecureRandom();

    private PasswordVerifier() {
    }

    private static byte[] derive(
            char[] password,
            byte[] salt,
            int iterations) throws GeneralSecurityException {

        PBEKeySpec spec =
            new PBEKeySpec(password, salt, iterations, HASH_BITS);

        try {
            SecretKeyFactory factory =
                SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");

            return factory.generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    public static String create(char[] password)
            throws GeneralSecurityException {

        byte[] salt = new byte[SALT_BYTES];
        RANDOM.nextBytes(salt);

        byte[] hash = derive(password, salt, CURRENT_ITERATIONS);

        return "pbkdf2-sha256:"
            + CURRENT_ITERATIONS + ":"
            + Base64.getEncoder().withoutPadding().encodeToString(salt) + ":"
            + Base64.getEncoder().withoutPadding().encodeToString(hash);
    }

    public static boolean verify(char[] password, String stored)
            throws GeneralSecurityException {

        if (stored == null) {
            return false;
        }

        String[] parts = stored.split(":", -1);
        if (parts.length != 4 || !"pbkdf2-sha256".equals(parts[0])) {
            return false;
        }

        final int iterations;
        try {
            iterations = Integer.parseInt(parts[1]);
        } catch (NumberFormatException ex) {
            return false;
        }

        if (iterations < 1 || iterations > MAX_ACCEPTED_ITERATIONS) {
            return false;
        }

        final byte[] salt;
        final byte[] expectedHash;

        try {
            salt = Base64.getDecoder().decode(parts[2]);
            expectedHash = Base64.getDecoder().decode(parts[3]);
        } catch (IllegalArgumentException ex) {
            return false;
        }

        if (salt.length != SALT_BYTES || expectedHash.length != HASH_BITS / 8) {
            return false;
        }

        byte[] actualHash = derive(password, salt, iterations);
        return MessageDigest.isEqual(expectedHash, actualHash);
    }
}
~~~

Trong ví dụ:

- **SecureRandom** tạo salt riêng cho mỗi bản ghi.
- **PBEKeySpec** giữ mật khẩu, salt, số vòng lặp và độ dài đầu ra.
- **SecretKeyFactory** thực hiện PBKDF2-HMAC-SHA-256.
- Bản ghi lưu thuật toán, iteration count, salt và hash dưới dạng Base64.
- Khi xác minh, ứng dụng đọc tham số đã lưu, kiểm tra giới hạn rồi dẫn xuất lại hash.
- **MessageDigest.isEqual** được dùng để so sánh hai mảng byte.

Ví dụ này minh họa cấu trúc xử lý; hệ thống sản xuất cần bổ sung quản lý phiên bản thuật toán, chính sách nâng cấp tham số, xử lý lỗi và giới hạn tài nguyên. MAX_ACCEPTED_ITERATIONS là hàng rào chống đầu vào tham số bất thường, cần được cấu hình theo chính sách. Khi bản ghi cũ dùng iteration count thấp hơn hiện tại, hệ thống vẫn có thể xác minh trong giới hạn cho phép rồi nâng cấp sau đăng nhập thành công.

PBEKeySpec.clearPassword() xóa bản sao mật khẩu mà đối tượng này quản lý. Mảng char[] do bên gọi cung cấp vẫn thuộc trách nhiệm của bên gọi; hãy xóa khi đã dùng xong nếu không còn cần thiết và bảo đảm không xóa khi thành phần khác còn sử dụng.

## 7. So sánh hash và xử lý sai lệch

Sau khi dẫn xuất hash, hệ thống cần so sánh với giá trị đã lưu. Không dùng String.equals, Arrays.equals hoặc vòng lặp dừng ngay khi gặp byte khác nhau cho dữ liệu xác thực bí mật nếu có thể tạo rò rỉ thời gian.

**MessageDigest.isEqual** cung cấp phép so sánh phù hợp cho mảng byte của digest hoặc password verifier. Hệ thống vẫn cần kiểm tra định dạng, độ dài và cấu trúc bản ghi trước khi so sánh.

Không trả về thông tin chi tiết như “mật khẩu sai ở ký tự thứ 4”, “hash không khớp” hoặc “tài khoản tồn tại nhưng mật khẩu sai”. Những thông tin đó hỗ trợ kẻ tấn công thu hẹp phạm vi dò.

Không ghi mật khẩu, hash, salt kèm thông tin tài khoản nhạy cảm hoặc pepper vào log theo cách làm tăng khả năng khai thác. Salt và hash phải được bảo vệ theo chính sách dữ liệu xác thực; pepper là bí mật cấp hệ thống và phải được quản lý riêng.

## 8. Nâng cấp thuật toán và tham số theo thời gian

Khả năng nâng cấp là một yêu cầu quan trọng vì phần cứng ngày càng mạnh và khuyến nghị mật mã thay đổi. Mỗi bản ghi nên có đủ thông tin để hệ thống biết cách xác minh:

- Tên thuật toán và phiên bản định dạng.
- Tham số chi phí như iteration count hoặc memory cost.
- Salt.
- Hash hoặc verifier.
- Phiên bản pepper nếu hệ thống sử dụng pepper.

Khi người dùng đăng nhập thành công:

1. Hệ thống xác minh bằng thuật toán và tham số được lưu trong bản ghi.
2. So sánh cấu hình đó với chính sách hiện tại.
3. Nếu bản ghi đã cũ, sinh salt mới và tính hash bằng thuật toán/tham số mới.
4. Cập nhật bản ghi một cách nguyên tử để tránh ghi đè thay đổi đồng thời.
5. Xóa dữ liệu trung gian nhạy cảm trong phạm vi có thể kiểm soát.

Không thể chuyển đổi một password hash cũ sang thuật toán mới nếu không có mật khẩu gốc. Hệ thống phải chờ lần đăng nhập tiếp theo để người dùng cung cấp mật khẩu, hoặc yêu cầu đặt lại mật khẩu nếu thuật toán cũ không còn được phép xác minh.

Với pepper, xoay vòng cần thiết kế riêng vì hash cũ phụ thuộc pepper cũ. Có thể duy trì nhiều phiên bản pepper trong giai đoạn chuyển tiếp, chỉ cho phép xác minh theo phiên bản đã gắn với bản ghi và chuyển sang pepper mới sau khi xác minh thành công. Nếu pepper bị mất mà không còn bản sao an toàn, có thể phải yêu cầu người dùng đặt lại mật khẩu.

## 9. Password verification không phải mã hóa mật khẩu

Mật khẩu đăng nhập và khóa mã hóa phục vụ hai mục tiêu khác nhau.

| Nhu cầu | Cơ chế phù hợp | Có cần khôi phục đầu vào gốc? |
|---|---|---|
| Xác minh người dùng đăng nhập | Password hashing như Argon2id, scrypt, bcrypt hoặc PBKDF2 | Không |
| Mã hóa dữ liệu để giải mã về sau | Mã hóa đối xứng hoặc AEAD với khóa được quản lý | Có, cần khóa phù hợp để giải mã |
| Dẫn xuất khóa từ mật khẩu để mã hóa dữ liệu | KDF/password-based encryption với salt và tham số được lưu | Có, cần cùng mật khẩu hoặc khóa dẫn xuất |
| Sinh khóa mật mã cho dịch vụ | KeyGenerator, KeyPairGenerator hoặc KMS/HSM | Không dùng mật khẩu người dùng làm nguồn ngẫu nhiên |

Nếu cần mã hóa dữ liệu bằng mật khẩu người dùng, phải dùng KDF phù hợp để dẫn xuất khóa, sau đó dùng AEAD hoặc cơ chế mã hóa đã được thiết kế an toàn. Không dùng trực tiếp mật khẩu làm AES key. Cũng không lấy password hash lưu trong cơ sở dữ liệu rồi dùng nó như khóa mã hóa: việc này trộn lẫn hai miền mục đích và có thể khiến một bản ghi xác minh bị lộ trở thành khóa truy cập dữ liệu.

Nếu một hệ thống vừa xác thực người dùng vừa cần khóa mã hóa riêng, hãy tách hai quy trình. Khóa dữ liệu nên được sinh ngẫu nhiên, quản lý bằng KMS/HSM hoặc envelope encryption; mật khẩu đăng nhập chỉ dùng cho xác thực người dùng.

## 10. Các biện pháp bảo vệ bổ sung

Password hashing bảo vệ dữ liệu khi cơ sở dữ liệu bị đánh cắp, nhưng không thay thế bảo vệ luồng đăng nhập. Hệ thống cần kết hợp:

- **Rate limiting:** giới hạn số lần thử theo tài khoản, IP, thiết bị hoặc tín hiệu rủi ro. Tránh khóa tài khoản cứng dễ bị lợi dụng để DoS.
- **MFA:** yêu cầu yếu tố bổ sung cho tài khoản và thao tác nhạy cảm.
- **TLS:** bảo vệ mật khẩu trong quá trình truyền giữa client và server.
- **Password reset an toàn:** dùng token ngẫu nhiên, thời hạn ngắn, chỉ dùng một lần và lưu verifier của token nếu cần.
- **Credential stuffing defense:** phát hiện việc thử các cặp email/mật khẩu bị rò rỉ từ dịch vụ khác.
- **Kiểm tra mật khẩu bị lộ:** đối chiếu với danh sách mật khẩu phổ biến hoặc dữ liệu rò rỉ theo phương pháp không gửi mật khẩu rõ tới bên thứ ba.
- **Giám sát:** ghi nhận sự kiện đăng nhập bất thường, thay đổi mật khẩu và reset; không ghi bí mật xác thực.

Thông báo lỗi nên nhất quán và không tiết lộ tài khoản có tồn tại hay không. Quy trình reset phải thu hồi hoặc vô hiệu hóa token cũ, thông báo cho chủ tài khoản và xem xét thu hồi session hiện tại theo chính sách.

## 11. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Lưu mật khẩu dạng rõ | Cơ sở dữ liệu bị lộ làm lộ trực tiếp thông tin đăng nhập | Chỉ lưu password hash cùng salt và tham số |
| Dùng SHA-256 đơn lẻ | Kẻ tấn công thử mật khẩu rất nhanh | Dùng password hashing chuyên dụng |
| Dùng một salt cố định cho mọi tài khoản | Cùng mật khẩu tạo cùng hash và hỗ trợ tấn công hàng loạt | Sinh salt ngẫu nhiên riêng cho mỗi bản ghi |
| Dùng username làm salt | Giá trị dễ đoán và có thể thay đổi | Dùng SecureRandom |
| Lưu pepper cùng cơ sở dữ liệu | Kẻ tấn công lấy được cả verifier và bí mật bổ sung | Lưu pepper riêng trong KMS/HSM/secret manager |
| Không lưu tham số thuật toán | Không thể xác minh hoặc nâng cấp bản ghi nhất quán | Lưu algorithm ID, version, cost, salt và hash |
| Chấp nhận cost không giới hạn từ bản ghi | Có thể gây tiêu tốn CPU/bộ nhớ và DoS | Kiểm tra định dạng và giới hạn tham số |
| So sánh hash bằng phép so sánh thông thường | Có thể rò rỉ thông tin qua thời gian xử lý | Dùng MessageDigest.isEqual |
| Dùng password hash làm khóa mã hóa | Trộn lẫn mục đích và tăng tác động khi lộ verifier | Dùng KDF và quản lý khóa riêng cho dữ liệu |
| Không nâng cấp tham số cũ | Bản ghi yếu tồn tại lâu dài | Rehash sau lần xác minh thành công |
| Trả lỗi đăng nhập quá chi tiết | Hỗ trợ dò tài khoản và thông tin xác thực | Dùng thông báo chung và giám sát ở phía server |

## 12. Nguyên tắc triển khai an toàn

- Ưu tiên Argon2id cho hệ thống mới khi thư viện và chính sách cho phép; cân nhắc scrypt hoặc bcrypt. Dùng PBKDF2-HMAC-SHA-256 khi cần tương thích hoặc đáp ứng yêu cầu môi trường.
- Sinh salt ngẫu nhiên riêng cho từng bản ghi bằng SecureRandom.
- Chọn tham số chi phí dựa trên benchmark và khuyến nghị hiện hành; lưu tham số cùng hash để có thể xác minh và nâng cấp.
- Dùng pepper nếu mô hình đe dọa và khả năng vận hành hỗ trợ; giữ pepper tách khỏi cơ sở dữ liệu.
- Kiểm tra định dạng và giới hạn tham số trước khi thực hiện phép tính tốn tài nguyên.
- Dùng phép so sánh phù hợp cho hash, thông báo lỗi chung và rate limiting.
- Nâng cấp hash sau khi xác minh thành công; không cố chuyển đổi hash cũ khi không có mật khẩu gốc.
- Không mã hóa mật khẩu đăng nhập để lưu trữ và không dùng password hash làm khóa mã hóa dữ liệu.
- Tách password verification khỏi quản lý khóa dữ liệu; dùng KeyStore, KMS hoặc HSM cho khóa mật mã.
- Bảo vệ đăng nhập bằng TLS, MFA, chống credential stuffing và quy trình reset mật khẩu an toàn.

Password verification an toàn dựa trên một bản ghi có salt riêng, thuật toán password hashing được thiết kế cho mật khẩu và tham số chi phí được quản lý theo thời gian. Khi tách biệt mật khẩu con người khỏi khóa mật mã ngẫu nhiên, ứng dụng có thể xác thực tài khoản mà vẫn giữ được ranh giới bảo vệ cần thiết cho dữ liệu và khóa của hệ thống.
