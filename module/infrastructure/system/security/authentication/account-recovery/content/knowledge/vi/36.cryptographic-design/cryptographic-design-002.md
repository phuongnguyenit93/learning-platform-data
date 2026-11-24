# Hash algorithm selection — Chọn thuật toán băm cho bí mật khôi phục

## 1. Bắt đầu từ bí mật cần bảo vệ

Không có một lựa chọn thuật toán duy nhất phù hợp với mọi giá trị được gọi là “recovery token”. Một liên kết chứa 32 byte ngẫu nhiên, một mã sáu chữ số và một cụm từ do người dùng tự chọn có đặc tính rất khác nhau.

**Hash algorithm selection** trong khôi phục tài khoản là quyết định dùng cơ chế nào để lưu và kiểm chứng bí mật, dựa trên:

- Cách bí mật được tạo và không gian đoán thực tế.
- Khả năng kẻ tấn công đọc dữ liệu lưu trữ.
- Khả năng tách và bảo vệ khóa nếu dùng cơ chế có khóa.
- Chi phí xác minh mà dịch vụ có thể chịu.
- Cách quản lý phiên bản, thời hạn, thu hồi và sử dụng một lần.

Mục tiêu thường là lưu **verifier**, tức giá trị giúp máy chủ kiểm chứng một bí mật, thay vì lưu token gốc trong bản ghi xác minh.

OWASP yêu cầu token đặt lại mật khẩu được tạo bằng nguồn ngẫu nhiên mật mã, đủ mạnh trước việc đoán, lưu an toàn, có thời hạn và dùng một lần. Chọn thuật toán băm chỉ giải quyết một phần của thiết kế đó. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Một lựa chọn đúng phải đi kèm giả định rõ ràng. Câu “dùng SHA-256” chưa đủ nếu không biết đầu vào là một bí mật ngẫu nhiên mạnh hay một mã ngắn dễ liệt kê.

## 2. Phân biệt ba cơ chế

| Cơ chế | Đầu vào chính | Mục tiêu liên quan đến khôi phục |
| --- | --- | --- |
| Hash mật mã không khóa | Bí mật và dữ liệu được mã hóa theo quy tắc | Tạo verifier một chiều cho bí mật phù hợp |
| MAC có khóa, chẳng hạn HMAC | Khóa bí mật cùng thông điệp | Kiểm chứng dựa trên khóa mà bên chỉ đọc database không có |
| Hàm băm mật khẩu hoặc password KDF | Bí mật, salt và tham số chi phí | Làm việc đoán offline tốn tài nguyên hơn |

SHA-256 và HMAC-SHA-256 không phải hai tên của cùng một thao tác. SHA-256 không có khóa; HMAC-SHA-256 cần khóa để tính và kiểm chứng.

Argon2id cũng không đơn giản là “SHA-256 với output dài hơn”. Nó được thiết kế với chi phí bộ nhớ và tính toán phù hợp cho những bí mật có nguy cơ bị đoán.

Cần phân biệt thêm với:

- **Mã hóa:** có thể khôi phục plaintext nếu có khóa; phù hợp với nhu cầu cần lấy lại dữ liệu, không tự thay cho verifier.
- **Encoding:** Base64URL hoặc hex chỉ biểu diễn byte thành ký tự; không tăng tính bí mật.
- **Chữ ký số:** thuộc một cơ chế xác minh khác; một digest không phải chữ ký.
- **Hàm hash của ngôn ngữ:** `String.hashCode()` không phải cơ chế lưu bí mật khôi phục.

Nếu dịch vụ cần giữ token để thử gửi lại, phần lưu có thể giải mã phục vụ chuyển phát cần được thiết kế riêng. Không chọn mã hóa cho toàn bộ verifier chỉ vì một worker gửi email cần truy cập token trong thời gian ngắn.

## 3. Entropy quan trọng hơn độ dài chuỗi hash

Giả sử mã được chọn đều từ N giá trị. Số bit thông tin tương ứng là:

~~~text
H = log2(N)
~~~

Ví dụ:

| Bí mật được tạo đúng giả định | Không gian | Xấp xỉ số bit |
| --- | --- | --- |
| Mã sáu chữ số, kể cả số 0 ở đầu | 1.000.000 | 19,93 |
| Mã tám chữ số, kể cả số 0 ở đầu | 100.000.000 | 26,58 |
| 32 byte ngẫu nhiên độc lập | 2^256 | 256 |

SHA-256 biến cả ba đầu vào thành digest 256 bit. Điều đó không biến mã sáu chữ số thành bí mật có 256 bit entropy.

Nếu kẻ tấn công có một verifier không khóa của mã sáu chữ số, họ có thể tính verifier cho các ứng viên trong không gian một triệu mã. Không cần “đảo ngược SHA-256” theo nghĩa giải một bài toán trên toàn bộ không gian 256 bit.

Tương tự, Base64URL của timestamp, account ID hoặc một bộ đếm có thể trông dài và khó đọc nhưng vẫn dự đoán được. Băm một dữ liệu dự đoán được không tự làm nguồn tạo bí mật trở nên an toàn.

Với token ngẫu nhiên mạnh, phần ngẫu nhiên phải thật sự đến từ nguồn ngẫu nhiên mật mã. Độ dài của một UUID, chuỗi hex hoặc kết quả hash không tự chứng minh điều đó.

## 4. Khi hash nhanh phù hợp với token ngẫu nhiên mạnh

Với giả định phần bí mật S gồm 32 byte ngẫu nhiên mật mã, một thiết kế verifier có thể là:

~~~text
stored_verifier = SHA-256(S)
~~~

Khi người dùng nộp C:

~~~text
candidate_verifier = SHA-256(C)
matches = secure_compare(stored_verifier, candidate_verifier)
~~~

Lý do hash nhanh có thể phù hợp ở đây là bí mật gốc có không gian đoán rất lớn. Mục tiêu không phải làm một mật khẩu dễ đoán trở nên đắt để thử, mà là tránh lưu trực tiếp một bearer secret vốn đã mạnh.

Thiết kế minh họa này có các giả định:

- S được sinh đúng bằng CSPRNG và không bị rút ngắn thành một không gian nhỏ.
- API chỉ chấp nhận bí mật gốc, không chấp nhận digest đã lưu như một token thay thế.
- Kẻ chỉ đọc database không đồng thời lấy được token ở log, email hoặc kho chuyển phát.
- Quyền ghi database và các trạng thái cấp quyền được bảo vệ riêng.
- Verifier được gắn với đúng tài khoản, mục đích và luồng trong dữ liệu máy chủ.

Có thể dùng selector không bí mật để định vị bản ghi trước khi tính và so verifier. Selector không được tính vào số bit bí mật nếu nó đã xuất hiện công khai cùng token.

Không cần mặc định chạy một hàm băm mật khẩu tốn bộ nhớ cho mọi token ngẫu nhiên mạnh. Chi phí đó cần có mục tiêu cụ thể; nó có thể làm endpoint khôi phục chịu tải lớn hơn mà không xử lý điểm yếu thật sự của hệ thống.

Đây không phải lý do dùng SHA-256 trực tiếp cho mật khẩu do người dùng chọn. Hai loại đầu vào có mô hình đoán khác nhau.

## 5. Khi nên xét HMAC và bảo vệ khóa

Một phương án khác là:

~~~text
stored_verifier =
    HMAC-SHA-256(K, encode(context, S))
~~~

K là khóa phía máy chủ. Context có thể gồm tên giao thức, phiên bản, tenant, account, purpose, flow và selector theo thiết kế.

HMAC là cơ chế xác thực thông điệp dựa trên hash và khóa bí mật, được mô tả trong [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104.html). Việc bài này chọn HMAC-SHA-256 là lựa chọn cụ thể cho ví dụ, không phải dùng lại các thuật toán lịch sử được nêu trong RFC.

Một lợi ích cần đánh giá: nếu chỉ database bị đọc còn K vẫn an toàn, kẻ tấn công không thể tự tính cùng verifier cho mỗi ứng viên mà không có khóa hoặc một đường gọi dịch vụ tính MAC.

Điều này đặc biệt đáng chú ý với mã có không gian nhỏ. Tuy nhiên:

- HMAC không làm mã sáu chữ số có nhiều giá trị hơn.
- Người gọi endpoint xác minh vẫn có thể thử mã online nếu thiếu giới hạn.
- Nếu dịch vụ tính MAC bị biến thành oracle không giới hạn, ranh giới bảo vệ bị suy yếu.
- Nếu cả khóa lẫn dữ liệu bị lấy, kẻ tấn công lại có thể thử offline theo cơ chế tương ứng.
- Một khóa dùng chung quá rộng có thể làm phạm vi sự cố lớn hơn.

K cần được quản lý ngoài bản ghi token và giới hạn quyền sử dụng theo nhiệm vụ. Cất K trong một cột bên cạnh verifier không tạo ra cách ly trước việc đọc cả bảng.

Không tự thay HMAC bằng công thức ghép chuỗi như `SHA-256(key || message)`. Cấu trúc có khóa cần được dùng theo cơ chế đã được thiết kế và triển khai phù hợp, thay vì tự xây một MAC từ hash.

## 6. Khi cần hàm băm mật khẩu có chi phí

Nếu bí mật do người dùng chọn có đặc tính giống mật khẩu, cần cơ chế dành cho tình huống đó: salt riêng, tham số chi phí và thư viện verify phù hợp.

OWASP ưu tiên các hàm băm mật khẩu hiện đại như Argon2id cho lưu mật khẩu và giải thích vì sao hash nhanh không phù hợp với dữ liệu dễ bị đoán. [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

Argon2 là một hàm memory-hard được mô tả trong [RFC 9106 — Argon2](https://www.rfc-editor.org/rfc/rfc9106.html). Khi lựa chọn Argon2id, cần quản lý cả biến thể, phiên bản, salt và tham số tài nguyên; chỉ ghi tên “Argon2” trong một ghi chú không đủ xác định verifier.

Một số phân biệt thực tế:

| Loại bí mật | Cách suy nghĩ khi chọn verifier |
| --- | --- |
| Token URL ngẫu nhiên mạnh | Có thể xét hash nhanh hoặc HMAC theo mô hình đe dọa |
| Mã ngẫu nhiên đủ dài để nhập tay | Đánh giá entropy thực; không phân loại chỉ vì người dùng gõ bằng tay |
| Mã số ngắn | Không gian nhỏ; cần chiến lược lưu trữ phù hợp, giới hạn thử và thời hạn |
| Cụm từ khôi phục do người dùng tự đặt | Có nguy cơ đoán như mật khẩu; xét password hashing |
| Câu trả lời cá nhân dễ tìm | Không thể sửa vấn đề bằng cách chỉ chọn output hash dài hơn |

Một hàm chậm có thể tăng chi phí đoán mã ngắn, nhưng không làm không gian hữu hạn đó biến mất. Không nên chỉ tăng chi phí đến mức endpoint dễ bị cạn CPU hoặc bộ nhớ rồi coi đó là toàn bộ bảo vệ.

Nếu dùng password KDF, tham số cần xuất phát từ yêu cầu an ninh, tài nguyên triển khai và hướng dẫn phù hợp tại thời điểm triển khai. Trong nội dung thiết kế, nên lưu được bộ tham số đã chọn và lý do lựa chọn.

Không tự viết vòng lặp hash nhiều lần để thay một password KDF đã được thiết kế cho mục tiêu đó.

## 7. Salt, khóa và bí mật token không có cùng chức năng

### Salt

Salt thường là dữ liệu ngẫu nhiên công khai đi cùng verifier. Nó giúp các bản ghi không dùng chung một kết quả và làm giảm lợi ích của việc tính trước hoặc chia sẻ công việc giữa nhiều bản ghi.

Salt không phải khóa. Người lấy được database thường cũng có salt. Họ vẫn có thể thử hết không gian của một mã ngắn cho từng bản ghi.

Với token ngẫu nhiên mạnh, mỗi bí mật vốn đã độc lập và khó đoán. Có thể thêm salt theo định dạng đã chọn, nhưng không nên cho rằng thiếu một salt riêng tự làm ví dụ SHA-256 trên token 256 bit trở thành giống lưu mật khẩu yếu.

### Khóa hoặc pepper

Khóa cần bí mật và được quản lý ngoài dữ liệu verifier trong mô hình muốn chống lộ database riêng lẻ. Nó bổ sung một ranh giới tin cậy khác với salt.

Mất khóa có thể làm các verifier dùng khóa đó không còn kiểm chứng được. Lộ khóa có thể ảnh hưởng mọi bản ghi liên quan. Vì vậy, lựa chọn HMAC phải đi cùng quản lý vòng đời khóa.

### Token gốc

Token gốc là bằng chứng người dùng nộp. Nó không được thay bằng salt, key ID hoặc verifier.

~~~text
salt công khai ≠ khóa bí mật
key_id ≠ khóa
verifier ≠ token gốc
output 256 bit ≠ đầu vào có entropy 256 bit
~~~

Những phân biệt này giúp tránh lựa chọn thuật toán đúng tên nhưng sai chức năng.

## 8. Chống collision không phải toàn bộ bài toán đoán token

Hai khái niệm cần phân biệt:

- **Preimage:** từ một giá trị hash đã biết, tìm một đầu vào khớp.
- **Collision:** tìm hai đầu vào khác nhau có cùng hash.

Trong tình huống verifier của token ngẫu nhiên đã được cấp, mục tiêu của kẻ tấn công thường liên quan đến tìm bí mật khớp hoặc một đầu vào được chấp nhận cho bản ghi đó. Điều này không giống việc tự chọn hai thông điệp bất kỳ có cùng hash.

Vì vậy, không nên giải thích mọi quyết định bằng một câu “có collision nên có thể đọc lại mọi token”. Cũng không nên dựa vào sự phân biệt này để tiếp tục chọn thuật toán cũ ngoài danh mục an ninh được chấp nhận.

Một lựa chọn thuật toán cần đáp ứng mục tiêu bảo mật của thiết kế và có triển khai đáng tin. Sự phổ biến hoặc việc runtime vẫn hỗ trợ một tên thuật toán không tự làm nó phù hợp cho một thiết kế khôi phục mới.

Đặc biệt, đừng cắt digest hoặc MAC xuống vài ký tự để tiết kiệm cột database mà không đánh giá lại xác suất chấp nhận sai và số lượt thử. Độ dài verifier là một tham số an ninh, không chỉ là định dạng hiển thị.

## 9. Quy tắc byte, context và biểu diễn phải nhất quán

Một thuật toán đúng vẫn có thể được dùng sai nếu hai phía xử lý khác nhau.

Ví dụ, nếu S là 32 byte ngẫu nhiên và được gửi dưới dạng Base64URL không padding:

~~~text
Phát hành:
    tạo S là 32 byte
    gửi Base64URL(S)
    lưu SHA-256(S)

Xác minh:
    kiểm tra định dạng chuỗi
    giải mã về đúng 32 byte C
    tính SHA-256(C)
    so với verifier đã lưu
~~~

Không bên nào băm chuỗi Base64URL trong khi bên kia băm byte đã giải mã. Nếu thiết kế chọn băm biểu diễn văn bản, quy tắc đó phải được xác định và giữ nhất quán; không tự chuyển qua lại giữa hai hợp đồng.

Không tự đổi hoa/thường, cắt tiền tố hoặc bỏ ký tự của một bí mật máy sinh. Với mã nhập tay cho phép dấu nhóm, quy tắc chuẩn hóa phải là một phần của giao thức ngay từ đầu.

Khi HMAC chứa context, cần tránh nối chuỗi nhập nhằng:

~~~text
encode("ab", "c") phải phân biệt với encode("a", "bc")
~~~

Có thể dùng định dạng xác định hoặc từng trường có tiền tố độ dài. Tên giao thức và phiên bản giúp tách mục đích sử dụng. Context kỳ vọng phải được dựng từ dữ liệu tin cậy ở máy chủ, không chỉ lấy lại các claim do client tự khai.

Nếu MAC ràng buộc một trường, việc thay trường đó phải tuân theo giao thức cập nhật tương ứng. Nó không bảo vệ các trường không được đưa vào MAC và không tự chống phát lại một bản ghi hợp lệ cũ.

## 10. Ví dụ Java cho hai nhánh verifier

Ví dụ sau chỉ minh họa tính verifier cho phần bí mật ngẫu nhiên 32 byte. Nó không sinh endpoint hoàn chỉnh, không xử lý mã ngắn và chưa thực hiện giới hạn thử, kiểm tra trạng thái hay tiêu thụ token.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class RecoveryVerifier {
    private static final int SECRET_BYTES = 32;
    private static final int SHA256_BYTES = 32;

    private RecoveryVerifier() {
    }

    public static byte[] hashRandomSecret(byte[] secret)
            throws GeneralSecurityException {
        requireRandomSecretLength(secret);
        return MessageDigest.getInstance("SHA-256").digest(secret);
    }

    public static boolean matchesRandomSecret(
            byte[] candidateSecret,
            byte[] storedVerifier
    ) throws GeneralSecurityException {
        if (storedVerifier == null
                || storedVerifier.length != SHA256_BYTES) {
            throw new IllegalArgumentException("Invalid verifier record");
        }
        if (candidateSecret == null
                || candidateSecret.length != SECRET_BYTES) {
            return false;
        }

        byte[] candidateVerifier = hashRandomSecret(candidateSecret);
        return MessageDigest.isEqual(storedVerifier, candidateVerifier);
    }

    public static byte[] macEncodedContextAndSecret(
            SecretKey key,
            byte[] encodedContextAndSecret
    ) throws GeneralSecurityException {
        if (key == null || encodedContextAndSecret == null) {
            throw new IllegalArgumentException("Missing MAC input");
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(key);
        return mac.doFinal(encodedContextAndSecret);
    }

    private static void requireRandomSecretLength(byte[] secret) {
        if (secret == null || secret.length != SECRET_BYTES) {
            throw new IllegalArgumentException("Invalid secret length");
        }
    }
}
~~~

`MessageDigest` cung cấp phép tính digest, còn `MessageDigest.isEqual` dành cho so sánh digest. Với ví dụ này, hai verifier có độ dài cố định. [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)

`Mac` là API cho MAC; tên chuẩn dùng ở đây là `HmacSHA256`. [Java SE 21 — Mac](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)

Những giới hạn của ví dụ cần được giữ rõ:

- `hashRandomSecret` không chứng minh đầu vào được sinh ngẫu nhiên; đó là trách nhiệm của đường phát hành.
- `storedVerifier` phải đến từ bản ghi đáng tin, không phải giá trị kỳ vọng do client cung cấp.
- Hàm MAC giả định caller đã tạo `encodedContextAndSecret` theo hợp đồng không nhập nhằng; nó không tự xác minh cấu trúc đó.
- Khóa không được hardcode trong mã nguồn hoặc lưu cùng verifier theo cách phá giả định cách ly.
- Lỗi khởi tạo thuật toán hoặc khóa phải làm thao tác kiểm chứng thất bại, không kích hoạt đường cho qua.

Không đưa mật khẩu hoặc một mã sáu chữ số vào `hashRandomSecret` rồi coi việc đủ 32 byte sau một phép tiền xử lý là đã đáp ứng giả định entropy. Padding hoặc hash trước không biến một bí mật dễ đoán thành token ngẫu nhiên mạnh.

## 11. Lưu phiên bản thuật toán và quản lý thay đổi

Bản ghi cần đủ dữ liệu để xác định cách kiểm chứng:

~~~yaml
verifier_scheme: HMAC_SHA256_CONTEXT_V1
key_version: recovery-key-7
verifier: "<32-byte-MAC-duoc-luu-theo-dinh-dang-da-quy-dinh>"
context_version: 1
token_generation: 4
state: ACTIVE
~~~

Với password KDF, định dạng còn cần salt và tham số chi phí phù hợp. Một số thư viện mã hóa các tham số này trong chuỗi verifier; cần dùng hàm verify đúng định dạng.

Máy chủ chọn scheme dựa trên dữ liệu và chính sách được kiểm soát. Không cho client tùy ý gửi `alg=...` rồi kích hoạt mọi thuật toán mà runtime biết.

Những quy tắc quan trọng:

- Scheme không nhận diện được là chưa kiểm chứng được.
- Không tìm thấy khóa phù hợp thì không chuyển sang hash không khóa.
- Một lỗi MAC không được thử tiếp bằng nhiều công thức cũ cho đến khi có công thức khớp.
- Chỉ hỗ trợ những phiên bản còn được chính sách cho phép.
- Không để một key ID từ đầu vào kích hoạt tải khóa từ đích tùy ý.

Nếu chỉ có `SHA-256(S)`, không thể tính `HMAC(K, S)` bằng cách băm lại digest cũ và gọi đó là migration tương đương. Công thức mới có đầu vào khác.

Với token có thời hạn ngắn, một phương án thay đổi là cấp theo scheme mới và cho bản cũ hết hạn hoặc bị thu hồi theo chính sách chuyển đổi. Nếu reissue, phải xử lý hiệu lực token cũ và điều kiện cấp mới rõ ràng.

Việc người dùng vừa nộp S hợp lệ có thể tạo cơ hội chuyển định dạng trong một số thiết kế. Tuy nhiên, token dùng một lần có thể được tiêu thụ ngay; không nhất thiết cần lưu một verifier nâng cấp cho token đã mất quyền.

## 12. Chi phí, khả năng vận hành và lỗi dịch vụ

Thuật toán phải được đặt vào endpoint có thể bị gọi bởi người chưa đăng nhập.

Với hash nhanh hoặc HMAC, chi phí mỗi lần tính thấp nhưng không được bỏ giới hạn lưu lượng. Hàng triệu yêu cầu vẫn có thể gây tải database, dịch vụ khóa hoặc hệ thống gửi thông báo.

Với password KDF tốn bộ nhớ, cần quản lý cả số phép tính đồng thời. Một tham số hợp lý cho một lần verify có thể vẫn gây cạn tài nguyên nếu endpoint cho phép số lượng không giới hạn.

Các lớp điều khiển cần được thiết kế trước bước tốn chi phí:

- Giới hạn kích thước và định dạng đầu vào.
- Giới hạn yêu cầu theo nguồn, mục tiêu và luồng phù hợp.
- Giới hạn số lần thử được chấp nhận ở máy chủ.
- Giới hạn số tác vụ tính toán hoặc gọi kho khóa đồng thời.
- Giữ phản hồi công khai không tiết lộ chi tiết bí mật hoặc tài khoản.

Không chỉ dựa vào thời hạn ngắn để bảo vệ một verifier yếu. Sau khi dữ liệu bị lấy, đối phương có thể tính offline mà không hỏi máy chủ. Thời hạn giới hạn cơ hội sử dụng token nếu máy chủ thực thi đúng; nó không làm phép đoán offline tự chậm lại.

Khi kho khóa không khả dụng, dịch vụ cần xử lý lỗi theo tuyến đã thiết kế. Không bỏ HMAC, không dùng một khóa mặc định công khai và không cấp quyền để tránh gián đoạn.

Tương tự, không ghi raw token, verifier hoặc khóa vào trace để “debug thuật toán”. Dữ liệu vận hành hữu ích thường là token ID không bí mật, scheme, key version, kết quả theo nhóm và correlation ID.

## 13. Kết quả băm khớp chưa đủ cho phép khôi phục

Dù dùng SHA-256, HMAC hay password KDF, kết quả khớp chỉ chứng minh điều kiện về bí mật theo cơ chế đã chọn.

Quyết định tiếp tục vẫn cần:

~~~text
bí mật khớp
and đúng tenant, account, flow và purpose
and token còn hiện hành
and chưa hết hạn
and chưa bị thu hồi hoặc tiêu thụ
and các ràng buộc bổ sung còn đạt
and thao tác tiêu thụ nguyên tử thành công
~~~

Hash không làm token tự hết hạn. HMAC không làm token tự dùng một lần. Password KDF không ngăn hai node đồng thời cấp quyền từ cùng trạng thái chưa dùng.

Trong luồng khôi phục MFA hoặc passkey, một token đã kiểm chứng qua email vẫn chỉ có mức bằng chứng mà tuyến đó được phép cung cấp. Việc chọn thuật toán mạnh hơn không tự cho phép bỏ yếu tố xác thực còn lại hoặc nâng một session hạn chế thành session đăng nhập đầy đủ.

Các điều kiện trạng thái và phạm vi phải được kiểm tra lại tại điểm chốt quyền, phối hợp với thay thế và thu hồi. Không lấy kết quả hash đã khớp trên snapshot cũ làm quyền sử dụng vĩnh viễn.

## 14. Những quyết định cần giải thích được

| Tình huống | Quyết định có cơ sở |
| --- | --- |
| Token URL có 32 byte ngẫu nhiên mật mã | Có thể xét SHA-256 làm verifier theo các giả định đã nêu |
| Muốn bảo vệ thêm khi chỉ database bị đọc | Xét HMAC với khóa tách biệt và vòng đời khóa rõ ràng |
| Mã sáu chữ số được băm SHA-256 | Không coi output 256 bit là bằng chứng chống liệt kê offline |
| Bí mật do người dùng tự chọn | Xét password hashing như Argon2id với salt và tham số phù hợp |
| Muốn tái sử dụng verifier của mật khẩu cho mọi token | Phân loại lại đầu vào và mục tiêu chi phí trước |
| Thêm salt vào mã ngắn | Có lợi ích theo từng bản ghi, nhưng không tạo thêm entropy cho mã |
| Chỉ có digest cũ nhưng muốn đổi sang HMAC của secret | Không thể tính công thức mới tương đương nếu thiếu secret |
| Key version không còn khả dụng | Không kiểm chứng được; không fallback sang cơ chế yếu hơn |
| Hai verifier khớp nhưng token đã dùng | Không cấp quyền lần nữa |
| Token có chữ ký hoặc mã hóa | Dùng cơ chế kiểm chứng đúng giao thức; digest đơn thuần không thay thế |
| Hệ thống bị lộ cả khóa và database | Đánh giá lại giả định, thu hồi và thay khóa theo phạm vi sự cố |
| Một scheme đúng tên nhưng log giữ raw token | Bí mật vẫn có thể bị sử dụng từ đường rò khác |

Lựa chọn thuật toán tốt bắt đầu từ loại bí mật và khả năng của đối phương, rồi mới đến tên hàm băm. Với khôi phục tài khoản, cần giữ liên hệ đó xuyên suốt: entropy của đầu vào, verifier được lưu, khóa nếu có, chi phí kiểm chứng và trạng thái cho phép sử dụng token.