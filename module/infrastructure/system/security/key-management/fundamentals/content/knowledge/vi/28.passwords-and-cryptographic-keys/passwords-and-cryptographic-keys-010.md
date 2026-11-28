# Tách password policy và key policy

**Password policy** và **key policy** đều là chính sách bảo mật bí mật, nhưng chúng quản lý hai loại tài sản khác nhau. Password policy quy định cách tổ chức tạo, tiếp nhận, xác minh, bảo vệ và khôi phục mật khẩu dùng để xác thực người hoặc tài khoản. Key policy quy định cách tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi, sao lưu và hủy khóa mật mã.

Hai chính sách cần phối hợp khi mật khẩu được dùng để mở khóa dữ liệu hoặc bảo vệ một khóa dữ liệu. Tuy nhiên, không nên áp cùng một quy tắc cho cả hai. Mật khẩu thường do con người chọn và có entropy thấp; khóa mật mã nên được sinh ngẫu nhiên bằng nguồn mật mã an toàn. Mật khẩu có thể được thay đổi theo quy trình tài khoản, còn khóa cần được xoay vòng theo cryptoperiod, mục đích sử dụng, mức độ phơi lộ và sự kiện vận hành.

Trong module quản lý khóa mật mã, việc tách hai chính sách giúp xác định rõ chủ sở hữu, biện pháp kiểm soát và bằng chứng kiểm toán cho từng loại bí mật. Nó cũng tránh tình trạng đổi mật khẩu đăng nhập làm gián đoạn dữ liệu mã hóa, hoặc giữ một khóa mật mã vô thời hạn chỉ vì tài khoản người dùng vẫn hoạt động.

## 1. Hai chính sách quản lý hai loại tài sản

### Password policy

Password policy là tập hợp quy tắc dành cho mật khẩu hoặc passphrase mà người dùng nhập để chứng minh quyền truy cập. Chính sách thường áp dụng cho tài khoản nhân viên, quản trị viên, khách hàng và một số tài khoản dịch vụ nếu hệ thống vẫn dùng mật khẩu.

Các câu hỏi password policy cần trả lời:

- Mật khẩu tối thiểu dài bao nhiêu và có cho phép passphrase dài hay không?
- Hệ thống có chặn mật khẩu phổ biến, dễ đoán hoặc đã bị lộ không?
- Mật khẩu được truyền, xác minh và lưu dưới dạng nào?
- Có dùng MFA, rate limiting và phát hiện đăng nhập bất thường không?
- Khi quên mật khẩu, nghi ngờ bị lộ hoặc nhân viên nghỉ việc thì xử lý thế nào?
- Khi nào cần yêu cầu đổi mật khẩu và làm sao bảo vệ quy trình đặt lại?

Mục tiêu chính là giảm khả năng kẻ khác đoán, đánh cắp, tái sử dụng hoặc chiếm quyền tài khoản thông qua mật khẩu.

### Key policy

Key policy là tập hợp quy tắc dành cho khóa mật mã như khóa AES dùng mã hóa dữ liệu, khóa RSA/EC dùng ký số, khóa TLS, Data Encryption Key (DEK) và Key Encryption Key (KEK). Chính sách áp dụng cho khóa do ứng dụng, KMS, HSM, thiết bị hoặc nhà cung cấp dịch vụ tạo và quản lý.

Các câu hỏi key policy cần trả lời:

- Thuật toán, kích thước và tham số nào được phép?
- Khóa được sinh ở đâu, bằng nguồn ngẫu nhiên nào và ai sở hữu?
- Khóa có được phép xuất khỏi HSM/KMS hay phải không thể xuất?
- Danh tính nào được phép dùng khóa để mã hóa, giải mã, ký hoặc xác minh?
- Khóa được lưu, sao lưu, khôi phục và kiểm toán ra sao?
- Cryptoperiod là bao lâu, sự kiện nào buộc phải xoay vòng hoặc thu hồi?
- Khi khóa bị lộ hoặc hết nhu cầu, việc thu hồi và hủy được thực hiện thế nào?

Mục tiêu chính là giữ bí mật key material, giới hạn đúng mục đích sử dụng, duy trì tính toàn vẹn và khả năng sẵn sàng, đồng thời kiểm soát rủi ro trong suốt vòng đời khóa.

## 2. So sánh password policy và key policy

| Tiêu chí | Password policy | Key policy |
|---|---|---|
| Đối tượng | Mật khẩu/passphrase của người hoặc tài khoản. | Khóa đối xứng, khóa công khai/riêng, DEK, KEK và khóa ký. |
| Nguồn tạo | Thường do người dùng chọn hoặc được hệ thống cấp. | Nên được sinh bằng CSPRNG, KeyGenerator, KeyPairGenerator hoặc KMS/HSM. |
| Đặc điểm entropy | Thường thấp, phụ thuộc thói quen và khả năng ghi nhớ của con người. | Có thể đạt entropy cao nếu sinh đúng bằng nguồn ngẫu nhiên mật mã. |
| Cách lưu | Lưu password hash cùng salt và tham số; không lưu mật khẩu dạng rõ. | Lưu trong KMS/HSM, keystore hoặc kho được kiểm soát; hạn chế xuất key material. |
| Cách xác minh/sử dụng | Xác minh phỏng đoán bằng password hashing scheme; kết quả quyết định quyền đăng nhập. | Thực hiện thao tác mật mã theo thuật toán, mục đích và quyền đã cấp. |
| Tham số chính | Độ dài, danh sách mật khẩu bị chặn, thuật toán hash, salt và cost. | Thuật toán, key size, usage, cryptoperiod, trạng thái, version và policy quyền. |
| Xoay vòng | Đặt lại khi bị lộ, có dấu hiệu xâm phạm hoặc theo quy định phù hợp. | Theo cryptoperiod, số lần sử dụng, thay đổi thuật toán, nghi ngờ lộ hoặc thay đổi hệ thống. |
| Khôi phục | Quy trình reset danh tính, xác minh người yêu cầu và thu hồi phiên. | Backup/restore có kiểm soát, recovery key, quorum hoặc quy trình phục hồi KMS/HSM. |
| Sự kiện kết thúc | Tài khoản bị khóa, vô hiệu hóa hoặc xóa theo vòng đời danh tính. | Khóa bị disable, revoke, destroy hoặc giữ ở trạng thái chỉ giải mã theo chính sách. |
| Bằng chứng kiểm toán | Thay đổi mật khẩu, reset, đăng nhập thất bại, MFA và thay đổi chính sách. | Tạo khóa, cấp quyền, sử dụng, export, rotate, disable, revoke, backup và destroy. |

Hai chính sách có thể cùng áp dụng cho một quy trình, nhưng kiểm soát cụ thể vẫn khác nhau. Ví dụ, mật khẩu quản trị dùng để đăng nhập vào KMS chịu password policy và chính sách MFA; khóa mã hóa do KMS quản lý chịu key policy. Việc người quản trị đổi mật khẩu không tự động thay đổi khóa dữ liệu trong KMS.

## 3. Vì sao không nên gộp hai chính sách?

Nếu dùng chung một bộ quy tắc, tổ chức có thể tạo ra các kiểm soát sai đối tượng:

**Áp quy tắc độ dài mật khẩu cho khóa.** Khóa AES không phải passphrase để người dùng ghi nhớ. Nó phải được sinh ngẫu nhiên theo kích thước được phê duyệt. Một chuỗi dễ nhớ có 32 ký tự không tương đương khóa AES-256 ngẫu nhiên.

**Áp lịch đổi mật khẩu cho mọi khóa.** Mật khẩu tài khoản và khóa mã hóa có mục đích, mức phơi lộ và tác động thay đổi khác nhau. Xoay vòng khóa dữ liệu có thể cần mã hóa lại dữ liệu hoặc rewrap DEK; reset mật khẩu đăng nhập thường chỉ cập nhật verifier và phiên xác thực.

**Dùng password hash thay cho khóa mã hóa.** Password hash phục vụ xác minh mật khẩu, không phải kho khóa và không tự cung cấp quy trình bảo vệ, phân quyền hay xoay vòng khóa. Nếu cần dẫn xuất khóa từ mật khẩu, phải dùng KDF và thiết kế riêng cho mục đích đó.

**Coi việc đổi mật khẩu là xử lý xong khi khóa bị lộ.** Nếu key material bị xâm phạm, đổi mật khẩu đăng nhập không làm khóa cũ mất hiệu lực. Cần thu hồi hoặc thay khóa, đánh giá dữ liệu bị ảnh hưởng và xử lý mọi bản sao.

**Dùng một cơ chế khôi phục cho cả hai.** Reset mật khẩu dựa trên xác minh danh tính người dùng; phục hồi khóa phải bảo đảm dữ liệu vẫn giải mã được nhưng không mở thêm quyền trái phép. Khôi phục khóa có thể cần HSM dự phòng, quorum hoặc quy trình dual control.

## 4. Nội dung nên có trong password policy

Một password policy thực tế cần bao phủ vòng đời tài khoản:

### Tạo và chọn mật khẩu

- Cho phép mật khẩu dài và passphrase; quy định độ dài tối thiểu theo chuẩn áp dụng và rủi ro hệ thống.
- Chặn mật khẩu phổ biến, dễ đoán, theo mẫu phổ biến hoặc xuất hiện trong danh sách mật khẩu đã bị lộ.
- Không buộc người dùng theo các quy tắc thành phần ký tự phức tạp đến mức khuyến khích ghi mật khẩu ra giấy hoặc tái sử dụng mẫu dễ đoán.
- Không cắt cụt mật khẩu âm thầm; giới hạn tối đa phải đủ lớn để hỗ trợ passphrase và tránh xử lý đầu vào quá mức.
- Xác định rõ quy tắc Unicode, khoảng trắng và chuẩn hóa để đăng ký, đăng nhập và reset dùng cùng một cách.

### Lưu và xác minh

- Dùng password hashing scheme chuyên dụng như Argon2id, scrypt, bcrypt hoặc PBKDF2 theo yêu cầu môi trường.
- Sinh salt ngẫu nhiên riêng cho từng bản ghi; lưu thuật toán, phiên bản và tham số chi phí cùng hash.
- Benchmark tham số trên hạ tầng thật và kiểm soát giới hạn đầu vào để tránh cạn kiệt CPU/bộ nhớ.
- So sánh kết quả bằng cơ chế phù hợp cho dữ liệu mật mã; không ghi mật khẩu hoặc giá trị nhạy cảm vào log.
- Nếu dùng pepper, lưu pepper ngoài cơ sở dữ liệu password hash, quản lý phiên bản và có kế hoạch phục hồi/di trú.

### Xác thực và khôi phục tài khoản

- Dùng TLS để bảo vệ mật khẩu khi truyền.
- Bật MFA hoặc passkey cho tài khoản nhạy cảm, đặc biệt là quản trị viên và người vận hành KMS/HSM.
- Áp dụng rate limiting, phát hiện credential stuffing và giám sát đăng nhập bất thường.
- Thiết kế reset password có xác minh danh tính, thời hạn token ngắn, token dùng một lần và thu hồi phiên theo chính sách.
- Không bắt buộc đổi mật khẩu định kỳ chỉ vì đến ngày nếu không có căn cứ rủi ro hoặc yêu cầu quản trị cụ thể; yêu cầu đổi khi có dấu hiệu lộ, chiếm quyền hoặc khi chính sách sự cố quy định.
- Khi nhân viên nghỉ việc hoặc đổi vai trò, vô hiệu hóa tài khoản và thu hồi quyền truy cập; không chỉ yêu cầu đổi mật khẩu.

## 5. Nội dung nên có trong key policy

Key policy phải mô tả cả thuộc tính mật mã lẫn quyền và trạng thái vòng đời.

### Thuật toán và tham số

- Danh sách thuật toán, mode, padding, key size và đường cong được phép.
- Mức security strength tối thiểu và thời gian dữ liệu cần được bảo vệ.
- Yêu cầu riêng cho mã hóa dữ liệu, ký số, trao đổi khóa, MAC và TLS.
- Quy tắc cấm thuật toán hoặc tham số lỗi thời, cùng lộ trình di trú.
- Kiểm tra khả năng tương thích của JDK, provider, KMS/HSM và hệ thống đối tác.

### Tạo, lưu trữ và quyền sử dụng

- Tạo khóa bằng CSPRNG hoặc bên trong KMS/HSM theo chính sách.
- Gán chủ sở hữu, mục đích, môi trường, thuật toán, phiên bản và thời điểm tạo.
- Phân tách khóa theo mục đích; không tái sử dụng một khóa cho mã hóa, ký và MAC nếu thiết kế không cho phép.
- Quy định khóa có được export hay phải không thể xuất; bảo vệ bản sao và kênh phân phối.
- Áp dụng least privilege, tách nhiệm vụ, dual control hoặc quorum cho thao tác nhạy cảm.
- Giới hạn thao tác theo vai trò, ứng dụng, tenant, môi trường và trạng thái khóa.

### Cryptoperiod, xoay vòng và thu hồi

Cryptoperiod là khoảng thời gian một khóa được phép dùng cho một mục đích nhất định. Thời hạn này phụ thuộc thuật toán, loại khóa, mức an toàn, số lượng thao tác, quy định và mô hình đe dọa. Key policy cần quy định:

- Khi nào khóa được dùng để tạo bản mã/chữ ký mới.
- Khi nào khóa chuyển sang trạng thái chỉ giải mã hoặc chỉ xác minh.
- Khi nào phải rotate, disable, revoke hoặc destroy.
- Cách xử lý khóa bị nghi ngờ lộ, mất quyền kiểm soát hoặc dùng sai mục đích.
- Cách duy trì khả năng đọc dữ liệu cũ và xác minh chữ ký lịch sử theo yêu cầu.

### Sao lưu, phục hồi và hủy

- Xác định khóa nào được phép backup và ai được phê duyệt.
- Mã hóa bản sao lưu, phân tách quyền truy cập và lưu trữ ở vị trí độc lập.
- Thử nghiệm restore định kỳ để chứng minh khả năng phục hồi.
- Quy định cách xử lý replica, cache, snapshot, bản sao CI/CD và thiết bị dự phòng.
- Khi destroy, lưu bằng chứng về khóa, thời điểm, người phê duyệt và phạm vi bản sao đã xử lý.

## 6. Mối quan hệ giữa mật khẩu, password hash và khóa mật mã

Ba khái niệm này thường bị nhầm:

| Thành phần | Đầu vào/nguồn | Đầu ra | Mục đích |
|---|---|---|---|
| Password | Người dùng chọn hoặc nhập. | Chuỗi ký tự. | Chứng minh quyền truy cập. |
| Password hash | Password, salt và tham số KDF/hash. | Giá trị verifier không dùng để khôi phục password. | Xác minh đăng nhập. |
| Password-derived key | Password, salt, KDF và tham số riêng cho mục đích mã hóa. | Khóa dẫn xuất có độ dài xác định. | Có thể dùng làm KEK để mở gói khóa dữ liệu nếu thiết kế hỗ trợ. |
| Cryptographic key | Sinh ngẫu nhiên hoặc được KMS/HSM cấp. | Key material hoặc handle khóa. | Mã hóa, giải mã, ký, xác minh hoặc MAC. |

Password hash dùng cho đăng nhập không nên được tái sử dụng làm khóa mã hóa. Nếu cần khóa từ mật khẩu, hãy dùng password-based KDF với salt và tham số riêng cho mục đích mã hóa. Có thể dùng PBKDF2, scrypt hoặc Argon2 theo yêu cầu, nhưng cần kiểm tra định dạng, tham số và thư viện.

Không dùng trực tiếp mật khẩu làm khóa AES bằng cách chuyển chuỗi thành byte rồi cắt hoặc đệm cho đủ độ dài. Cách làm đó không tạo ra khóa có entropy phù hợp và có thể khiến cùng mật khẩu tạo ra cùng khóa ở nhiều hệ thống.

## 7. Khi mật khẩu được dùng để bảo vệ khóa dữ liệu

Một trường hợp phối hợp hai chính sách là ứng dụng mã hóa dữ liệu cá nhân bằng DEK, rồi dùng khóa dẫn xuất từ mật khẩu để bảo vệ DEK:

~~~text
Password người dùng
        |
        v
Password-based KDF + salt + parameters
        |
        v
Password-derived KEK
        |
        v
Wrap / unwrap DEK
        |
        v
DEK mã hóa / giải mã dữ liệu bằng AEAD
~~~

Trong Java, có thể dùng **SecretKeyFactory** để dẫn xuất khóa AES từ mật khẩu và salt riêng cho tác vụ bảo vệ DEK:

~~~java
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;

private static final int MAX_KDF_ITERATIONS = 2_000_000;

public static SecretKey deriveWrappingKey(
        char[] password,
        byte[] salt,
        int iterations) throws GeneralSecurityException {

    if (password == null || salt == null || salt.length < 16
            || iterations < 1 || iterations > MAX_KDF_ITERATIONS) {
        throw new IllegalArgumentException("Tham số KDF không hợp lệ");
    }

    PBEKeySpec spec = new PBEKeySpec(
            password, salt, iterations, 256);
    try {
        SecretKeyFactory factory =
                SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
        byte[] derived = factory.generateSecret(spec).getEncoded();
        try {
            return new SecretKeySpec(derived, "AES");
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    } finally {
        spec.clearPassword();
    }
}
~~~

Đoạn mã chỉ minh họa việc dẫn xuất KEK. Giá trị MAX_KDF_ITERATIONS là giới hạn đầu vào ví dụ, không phải tham số khuyến nghị dùng chung; cần benchmark, đặt ngưỡng tối đa theo năng lực hệ thống và lưu số vòng để có thể dẫn xuất lại. Salt phải được tạo ngẫu nhiên, lưu cùng metadata và dùng riêng cho mục đích này. Mảng password thuộc quyền quản lý của bên gọi và cần được xóa sau khi hoàn tất. SecretKeySpec tạo bản sao key material trong bộ nhớ JVM, nên ứng dụng có trách nhiệm giới hạn vòng đời và quyền truy cập của đối tượng khóa. Với yêu cầu bảo vệ cao, cân nhắc KMS/HSM hoặc cơ chế bảo vệ khóa nền tảng để giảm việc giữ khóa rõ trong heap.

Trong mô hình này:

- Password policy quản lý cách người dùng chọn, thay đổi và xác minh mật khẩu, cũng như cách bảo vệ tài khoản.
- Key policy quản lý DEK, KEK, thuật toán wrapping, phiên bản, quyền sử dụng, sao lưu và hủy.
- KDF có chính sách tham số riêng cho mục đích dẫn xuất KEK. Tham số này không nhất thiết giống password hashing scheme dùng để xác minh đăng nhập.
- Salt của KDF có thể được lưu cùng metadata của bản mã; nó không phải bí mật.

### Đổi mật khẩu đăng nhập

Nếu mật khẩu chỉ dùng để đăng nhập, thay đổi mật khẩu thường chỉ yêu cầu tạo password hash mới, cập nhật verifier và xử lý phiên/token theo password policy. Khóa dữ liệu được quản lý bởi key policy vẫn giữ nguyên.

### Đổi mật khẩu dùng để mở khóa dữ liệu

Nếu mật khẩu cũ được dùng để dẫn xuất KEK bảo vệ DEK, quy trình đổi mật khẩu phải xử lý cả lớp wrapping:

1. Xác minh người dùng bằng password verifier.
2. Dùng mật khẩu cũ và tham số KDF cũ để dẫn xuất KEK cũ.
3. Dùng KEK cũ mở gói DEK trong bộ nhớ hoặc trong ranh giới bảo vệ phù hợp.
4. Tạo salt và tham số KDF mới, dẫn xuất KEK mới từ mật khẩu mới.
5. Dùng KEK mới đóng gói lại DEK.
6. Cập nhật metadata và verifier một cách nhất quán; kiểm tra có thể mở gói DEK bằng cấu hình mới.
7. Xóa các buffer nhạy cảm mà ứng dụng kiểm soát và xử lý bản sao tạm theo chính sách.

Nếu chỉ thay password hash đăng nhập mà quên rewrap DEK, người dùng có thể đăng nhập bằng mật khẩu mới nhưng không mở được dữ liệu đã mã hóa. Ngược lại, nếu thay KEK mà không cập nhật verifier hoặc metadata liên quan, quá trình xác minh và giải mã có thể mất đồng bộ.

Nếu người dùng quên mật khẩu cũ, hệ thống không thể suy ra KEK cũ chỉ từ password hash. Cần có cơ chế recovery đã thiết kế trước, chẳng hạn recovery key, khóa phục hồi do tổ chức kiểm soát hoặc bản sao DEK được bảo vệ bằng KEK phục hồi. Cơ chế đó phải được key policy phê duyệt, giới hạn người có quyền và kiểm toán mỗi lần sử dụng.

## 8. Ví dụ ma trận kiểm soát trong một tổ chức

Giả sử một doanh nghiệp có cổng nhân viên, dịch vụ mã hóa hồ sơ và KMS:

| Tình huống | Password policy | Key policy |
|---|---|---|
| Nhân viên đăng nhập cổng nội bộ | Mật khẩu/passkey, MFA, rate limit, reset và thu hồi phiên. | Không áp dụng trực tiếp cho khóa dữ liệu của dịch vụ. |
| Quản trị viên đăng nhập KMS | Tài khoản định danh mạnh, MFA chống phishing nếu khả thi, quy trình cấp lại thông tin xác thực. | Quyền tạo, rotate, disable, grant và destroy khóa được tách vai trò, có phê duyệt. |
| Dịch vụ mã hóa hồ sơ | Tài khoản dịch vụ dùng workload identity hoặc bí mật máy được quản lý; tránh mật khẩu tĩnh nếu có thể. | DEK/KEK, AES-GCM, key version, quyền decrypt và giới hạn export. |
| Nhân viên đổi mật khẩu | Xác minh người dùng, cập nhật verifier và thu hồi phiên theo chính sách. | Chỉ thay đổi khóa nếu mật khẩu còn tham gia mở gói DEK hoặc có yêu cầu độc lập. |
| Khóa mã hóa bị lộ | Reset mật khẩu chỉ khi thông tin xác thực cũng bị ảnh hưởng. | Disable/revoke khóa, tạo khóa mới, đánh giá dữ liệu và bản sao, re-encrypt hoặc rewrap theo tình huống. |
| Nhân viên nghỉ việc | Vô hiệu hóa tài khoản, token, phiên và thông tin xác thực liên quan. | Rà soát quyền của danh tính đó, thay đổi quyền truy cập khóa và xử lý khóa cá nhân nếu cần. |

Ma trận giúp đội vận hành xác định hành động cần thực hiện mà không đánh đồng sự cố tài khoản với sự cố key material.

## 9. Phân công trách nhiệm và kiểm toán

Hai chính sách có thể do các nhóm khác nhau quản lý, nhưng phải có cơ chế phối hợp:

| Vai trò | Trách nhiệm với password policy | Trách nhiệm với key policy |
|---|---|---|
| IAM/Identity team | Quản lý đăng nhập, MFA, reset, vòng đời tài khoản và password verifier. | Cấp danh tính dịch vụ và nhóm quyền truy cập KMS/HSM. |
| Security/Cryptography team | Định nghĩa yêu cầu xác thực và đánh giá rủi ro mật khẩu. | Phê duyệt thuật toán, key size, cryptoperiod, quy trình rotate/revoke/destroy. |
| Platform/Operations | Vận hành endpoint đăng nhập, giám sát và phục hồi tài khoản. | Vận hành KMS/HSM, backup, restore, phân phối và giám sát khóa. |
| Application owner | Bảo vệ luồng nhập mật khẩu và xử lý phiên. | Xác định mục đích khóa, tích hợp API và kiểm thử dữ liệu mã hóa. |
| Auditor/Compliance | Kiểm tra tuân thủ chính sách xác thực. | Kiểm tra quyền, lịch sử sử dụng khóa và bằng chứng vòng đời. |

Nhật ký password nên tập trung vào sự kiện xác thực và thay đổi tài khoản, không ghi giá trị mật khẩu hoặc password hash vào log ứng dụng thông thường. Nhật ký khóa cần ghi nhận mã định danh khóa, thao tác, danh tính gọi, kết quả, thời điểm và phê duyệt liên quan; không ghi key material.

Các thao tác nhạy cảm như export, disable, rotate, revoke và destroy nên được kiểm toán độc lập. Với thao tác có tác động lớn, cân nhắc dual control hoặc quorum để một cá nhân không thể tự ý thực hiện toàn bộ quy trình.

## 10. Xử lý sự cố theo đúng chính sách

| Sự cố | Hành động theo password policy | Hành động theo key policy |
|---|---|---|
| Mật khẩu người dùng bị lộ | Reset mật khẩu, thu hồi phiên/token, kiểm tra MFA và hoạt động bất thường. | Đánh giá xem tài khoản có quyền dùng khóa hay không; thu hồi quyền nếu cần. Chỉ rotate khóa khi có dấu hiệu key material bị ảnh hưởng hoặc chính sách yêu cầu. |
| Cơ sở dữ liệu password hash bị lộ | Đánh giá thuật toán/cost/pepper, buộc reset khi cần, theo dõi credential stuffing và mật khẩu tái sử dụng. | Kiểm tra pepper/KMS secret có bị lộ cùng không; thay bí mật liên quan nếu bị xâm phạm. |
| Khóa riêng bị lộ | Reset tài khoản chỉ khi thông tin đăng nhập cũng bị ảnh hưởng. | Revoke chứng thư hoặc khóa, tạo cặp mới, cập nhật bên tin cậy, điều tra bản sao và xử lý dữ liệu liên quan. |
| Quản trị viên nghỉ việc | Vô hiệu hóa tài khoản, token, MFA và phiên. | Rà soát quyền IAM/KMS, thay đổi phê duyệt hoặc bí mật chung mà người đó có thể đã biết. |
| Mất mật khẩu dùng để mở dữ liệu | Xác minh danh tính và thực hiện quy trình recovery/reset. | Dùng recovery key hoặc cơ chế escrow đã phê duyệt để phục hồi DEK; nếu không có bản sao phục hồi phù hợp, dữ liệu có thể không khôi phục được. |
| KMS/HSM không khả dụng | Không tự động yêu cầu người dùng đổi mật khẩu. | Kích hoạt quy trình dự phòng, khôi phục dịch vụ và kiểm tra tính toàn vẹn của bản sao khóa. |

Điều tra sự cố phải xác định bí mật nào thực sự bị ảnh hưởng: mật khẩu, verifier, pepper, KEK, DEK, khóa riêng hay quyền gọi KMS. Sau đó mới chọn hành động tương ứng. Đổi đồng loạt mọi mật khẩu và mọi khóa mà không phân tích phạm vi có thể gây gián đoạn và làm tăng rủi ro thao tác.

## 11. Ví dụ cấu trúc hai chính sách

Hai chính sách nên có mã định danh, chủ sở hữu, phạm vi, ngày hiệu lực, lịch rà soát và quy trình ngoại lệ riêng. Mẫu dưới đây chỉ minh họa cách tách trách nhiệm:

~~~yaml
password_policy:
  owner: identity_security
  scope:
    - human_user_accounts
    - privileged_accounts
  controls:
    password_storage: adaptive_password_hash
    unique_salt_per_password: true
    block_compromised_passwords: true
    mfa_required_for_privileged_accounts: true
    rate_limit_authentication: true
    reset_requires_identity_verification: true
    rotate_on_compromise: true

key_policy:
  owner: cryptography_security
  scope:
    - data_encryption_keys
    - key_encryption_keys
    - signing_keys
    - tls_private_keys
  controls:
    approved_algorithms: centrally_managed
    key_generation: approved_csprng_or_kms_hsm
    purpose_separation: true
    least_privilege: true
    non_exportable_where_required: true
    cryptoperiod: defined_per_key_class
    backup_and_recovery: controlled_and_tested
    rotation_and_revocation: event_and_period_based
    destruction: verified_and_audited
~~~

Không sao chép mẫu này thành cấu hình sản xuất mà chưa điền thuật toán, tham số, thời hạn, vai trò và quy trình cụ thể. Chính sách cần được chuyển thành cấu hình kỹ thuật, quy trình vận hành và bằng chứng kiểm toán có thể kiểm tra.

## 12. Checklist thiết kế và rà soát

**Password policy**

- [ ] Phạm vi tài khoản và loại mật khẩu được xác định.
- [ ] Có yêu cầu về độ dài, passphrase và chặn mật khẩu phổ biến/bị lộ.
- [ ] Password verifier dùng password hashing scheme, salt riêng và cost phù hợp.
- [ ] Có MFA, rate limiting, giám sát đăng nhập và reset an toàn.
- [ ] Có quy trình xử lý tài khoản bị chiếm quyền và người dùng rời tổ chức.

**Key policy**

- [ ] Mỗi loại khóa có mục đích, chủ sở hữu, thuật toán và tham số được phê duyệt.
- [ ] Khóa được sinh và lưu trong ranh giới bảo vệ phù hợp; quyền export được kiểm soát.
- [ ] Quyền dùng khóa được giới hạn theo danh tính và thao tác.
- [ ] Có cryptoperiod, điều kiện rotate/revoke/disable/destroy và cách xử lý dữ liệu cũ.
- [ ] Backup, restore, recovery và destruction được kiểm thử, phê duyệt và kiểm toán.

**Điểm giao giữa hai chính sách**

- [ ] Xác định rõ mật khẩu chỉ xác thực tài khoản hay còn dùng để mở gói khóa dữ liệu.
- [ ] Nếu dẫn xuất KEK từ mật khẩu, dùng KDF riêng cho mục đích đó và lưu tham số/metadata.
- [ ] Có quy trình rewrap DEK khi đổi mật khẩu bảo vệ dữ liệu.
- [ ] Có recovery key hoặc cơ chế phục hồi được phê duyệt nếu người dùng quên mật khẩu mở dữ liệu.
- [ ] Sự cố mật khẩu và sự cố key material được phân loại, điều tra và xử lý theo đúng phạm vi.

Password policy bảo vệ danh tính và khả năng xác thực của người dùng; key policy bảo vệ tài sản mật mã và các thao tác sử dụng khóa. Tách chúng giúp mỗi loại bí mật có quy tắc phù hợp, trong khi vẫn phối hợp rõ ràng tại những điểm giao như password-derived key, recovery và quyền truy cập KMS. Khi hai chính sách có chủ sở hữu, vòng đời và bằng chứng kiểm toán riêng, tổ chức có thể thay đổi mật khẩu mà không làm mất dữ liệu mã hóa, đồng thời xoay vòng khóa mà không nhầm lẫn với quy trình tài khoản.
