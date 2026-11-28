# Không lưu password plaintext

## 1. Nguyên tắc và phạm vi trong hệ thống IAM

Password plaintext là mật khẩu ở dạng có thể đọc hoặc sử dụng trực tiếp, chưa được bảo vệ bằng một cơ chế lưu mật khẩu thích hợp. Ví dụ, cột `password` chứa đúng chuỗi người dùng nhập là nơi lưu plaintext. Một file CSV xuất từ cột đó, một dòng log chụp request đăng nhập và một sự kiện chứa trường `rawPassword` cũng tạo ra các bản sao plaintext.

Trong hệ thống xác thực bằng mật khẩu, máy chủ cần trả lời câu hỏi: “Mật khẩu vừa được cung cấp có khớp với thông tin xác thực của tài khoản không?”. Máy chủ không cần chức năng đọc lại mật khẩu hiện tại của người dùng. Thiết kế lưu trữ vì thế phải phục vụ việc **xác minh**, thay vì phục vụ việc **khôi phục bí mật gốc**.

OWASP khuyến nghị bảo vệ mật khẩu bằng hàm băm chuyên dụng có salt, thay cho lưu bản rõ hoặc dùng mã hóa có thể đảo ngược cho mục đích xác minh đăng nhập thông thường. [Nguồn: OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#hashing-vs-encryption).

“Không lưu plaintext” không có nghĩa là mật khẩu không bao giờ xuất hiện trong bộ nhớ. Trong luồng xác thực bằng mật khẩu thông thường, người dùng nhập bí mật trên thiết bị và thành phần xác minh phải xử lý đầu vào đó. Mục tiêu là giảm nơi tiếp nhận, thời gian tồn tại và số bản sao, đồng thời ngăn bí mật bị ghi thành dữ liệu bền vững ngoài mục đích cần thiết.

Sau bài học, người học cần nhận diện được nơi mật khẩu bị sao chép, thiết kế ranh giới lưu trữ credential và giải thích cách chuyển đổi một hệ thống đang vi phạm nguyên tắc này.

## 2. Vì sao một cột plaintext gây hậu quả vượt khỏi database?

Xét một cổng nhân sự giả định. Ban đầu nhóm phát triển chỉ có một bảng tài khoản, nhưng sau một thời gian hệ thống có thêm backup, đồng bộ dữ liệu, công cụ hỗ trợ và nền tảng phân tích lỗi.

```text
Request đăng ký chứa mật khẩu
    ├── Bảng tài khoản
    │     ├── Replica
    │     ├── Backup
    │     └── Export hỗ trợ vận hành
    ├── Log request của ứng dụng
    └── Công cụ ghi nhận lỗi và trace
```

Nếu đầu vào được lưu nguyên dạng, mỗi nhánh trở thành một nơi phải bảo vệ như kho bí mật. Một tài khoản chỉ có quyền đọc log có thể vô tình có khả năng lấy mật khẩu, dù không được phép đọc bảng credential.

Hậu quả còn có thể lan sang dịch vụ khác nếu người dùng tái sử dụng mật khẩu. Một sự cố ở cổng nhân sự khi đó có thể cung cấp dữ liệu để thử đăng nhập vào email hoặc hệ thống bên ngoài. Hệ thống không có cách xác định chắc chắn người dùng đã dùng lại bí mật ở đâu.

Việc giới hạn quyền đọc database vẫn cần thiết, nhưng không giải quyết toàn bộ vấn đề. Lỗ hổng ứng dụng, backup bị chia sẻ sai, quyền hỗ trợ quá rộng hoặc tài khoản vận hành bị chiếm đều có thể đưa dữ liệu ra ngoài ranh giới dự kiến.

## 3. Những biện pháp dễ bị nhầm là đã thay thế plaintext

| Cách lưu hoặc bảo vệ | Điều nó thực sự làm | Đánh giá với mật khẩu đăng nhập |
| --- | --- | --- |
| Lưu nguyên chuỗi nhập | Giữ lại bí mật gốc | Không chấp nhận |
| Base64, hex hoặc đảo ngược chuỗi | Đổi cách biểu diễn | Có thể khôi phục dễ dàng; không tạo bảo vệ mật khẩu |
| Chia mật khẩu vào hai cột | Đổi cách bố trí dữ liệu | Người đọc được cả hai vẫn ghép lại được |
| Mã hóa có khóa giải mã | Cho phép khôi phục bằng khóa | Tạo thêm khả năng đọc lại mà luồng xác minh thông thường không cần |
| Mã hóa ổ đĩa hoặc database | Bảo vệ một số trường hợp truy cập lớp lưu trữ | Không ngăn ứng dụng được cấp quyền đọc ra plaintext |
| HTTPS/TLS | Bảo vệ dữ liệu trên kênh truyền khi cấu hình đúng | Không quyết định ứng dụng sẽ ghi gì vào database hoặc log |
| Hàm băm mật khẩu có salt và chi phí thích hợp | Tạo dữ liệu để xác minh, tăng chi phí đoán ngoại tuyến | Là cơ chế lưu verifier cần thiết cho luồng mật khẩu cục bộ |

Một lần SHA-256 của mật khẩu cũng chưa phải thiết kế lưu trữ phù hợp. Không nên thay chuỗi plaintext bằng một hash tính rất nhanh rồi tuyên bố đã giải quyết đầy đủ vấn đề. Password hashing cần thuật toán chuyên dụng và cấu hình được lựa chọn cho môi trường vận hành. [Nguồn: OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

NIST yêu cầu verifier lưu mật khẩu theo cách chống tấn công ngoại tuyến, sử dụng salt và cơ chế băm mật khẩu thích hợp; bản ghi cần đủ thông tin để xác minh và hỗ trợ thay đổi thuật toán hoặc chi phí. [Nguồn: NIST SP 800-63B-4, mục Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver).

Không có cơ chế nào trong bảng làm mất trách nhiệm bảo vệ ứng dụng đang chạy. Nếu đối thủ kiểm soát thành phần xác minh, họ có thể quan sát đầu vào ở thời điểm người dùng cung cấp mật khẩu. Băm dữ liệu lưu trữ chủ yếu hạn chế hậu quả của việc lộ verifier, không phải bảo đảm máy chủ đã bị chiếm vẫn an toàn.

## 4. Chỉ lưu dữ liệu đủ để xác minh

Mô hình dữ liệu khái niệm có thể tách thông tin tài khoản khỏi credential:

```text
account
  id
  login_name
  account_status

local_password_credential
  account_id
  encoded_verifier
  credential_version
  changed_at
```

`encoded_verifier` là bản ghi được thư viện tạo ra, chứa hoặc tham chiếu thông tin thuật toán, salt, tham số chi phí và kết quả băm. “Encoded” ở đây mô tả cách đóng gói verifier; nó không có nghĩa là Base64 của mật khẩu.

Không thêm các trường `original_password`, `password_backup`, `last_plain_password` hay `password_hint` chứa bí mật để phục vụ hỗ trợ. Nếu cần ngăn tái sử dụng mật khẩu trong một phạm vi chính sách cụ thể, thiết kế dữ liệu lịch sử credential theo mục đích đó; không lưu danh sách mật khẩu cũ ở bản rõ.

Salt không phải mật khẩu và thường được lưu cùng verifier. Nếu kiến trúc dùng thêm pepper hoặc khóa bí mật cho phép biến đổi credential, phải quản lý bí mật đó ở ranh giới riêng. Không coi việc giấu salt là điều kiện thay thế cho một thuật toán băm thích hợp.

Verifier cũng là dữ liệu nhạy cảm: người có bản sao có thể thử đoán ngoại tuyến. Không đưa verifier vào API trả hồ sơ, dashboard hỗ trợ, log hoặc tập dữ liệu phân tích chỉ vì nó không phải plaintext.

## 5. Luồng đăng ký và đăng nhập không cần đọc lại mật khẩu

### 5.1. Khi tạo hoặc đổi mật khẩu

```text
Nhận mật khẩu qua kênh được bảo vệ
    ↓
Xác minh quyền thực hiện thao tác và kiểm tra chính sách
    ↓
Tạo verifier bằng thư viện password hashing
    ↓
Lưu verifier vào kho credential
    ↓
Kết thúc xử lý đầu vào; không đưa mật khẩu sang sự kiện nghiệp vụ
```

Khi đổi mật khẩu, người thực hiện phải có quyền thay credential của đúng tài khoản. Việc một mật khẩu mới đáp ứng chính sách không chứng minh request đổi mật khẩu là hợp lệ.

### 5.2. Khi đăng nhập

Thành phần xác thực đọc verifier của tài khoản và dùng hàm xác minh của thư viện để đối chiếu mật khẩu ứng viên. Nó không giải mã verifier thành mật khẩu gốc. Cũng không tạo hash với salt ngẫu nhiên mới rồi so hai chuỗi kết quả, vì hai lần tạo verifier có thể dùng salt khác nhau.

Kết quả đối chiếu chỉ xác nhận một bằng chứng xác thực. Tài khoản còn phải đáp ứng các điều kiện như trạng thái hoạt động, yêu cầu MFA và chính sách rủi ro trước khi được cấp phiên. Quyền truy cập tài nguyên vẫn do cơ chế phân quyền quyết định.

Không giữ mật khẩu trong session để “đăng nhập lại tự động” ở mỗi request. Sau đăng nhập, ứng dụng sử dụng cơ chế phiên hoặc token theo thiết kế; các token đó cũng phải được bảo vệ như credential của chính chúng.

## 6. Ví dụ Java: giữ ranh giới giữa đầu vào và verifier

Spring Security cung cấp `PasswordEncoder` cho phép tạo giá trị lưu bằng `encode(...)` và đối chiếu bằng `matches(...)`. Encoder phải được cấu hình cho thuật toán lưu mật khẩu thực sự; tên interface không bảo đảm một cấu hình cụ thể là an toàn. [Nguồn: Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html).

Ví dụ sau chỉ minh họa thao tác với verifier, không phải một endpoint đăng ký hoặc đăng nhập hoàn chỉnh:

```java
import java.util.Objects;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class PasswordVerifierOperations {
    private final PasswordEncoder encoder;

    public PasswordVerifierOperations(PasswordEncoder encoder) {
        this.encoder = Objects.requireNonNull(encoder);
    }

    public String createVerifier(CharSequence suppliedPassword) {
        Objects.requireNonNull(suppliedPassword);
        return encoder.encode(suppliedPassword);
    }

    public boolean verify(CharSequence candidate, String savedVerifier) {
        Objects.requireNonNull(candidate);
        Objects.requireNonNull(savedVerifier);
        return encoder.matches(candidate, savedVerifier);
    }
}
```

Ở lớp gọi, chỉ giá trị trả về của `createVerifier(...)` được ghi vào kho credential. Đầu vào được kiểm tra chính sách và xử lý biểu diễn nhất quán trước khi dùng các thao tác này. Không cấu hình encoder không biến đổi mật khẩu, không chấp nhận định dạng lưu plaintext trong production và không bật cơ chế dự phòng coi dữ liệu không nhận diện được là mật khẩu thô.

Hàm `verify(...)` không xử lý tìm tài khoản, chống dò tài khoản, giới hạn tốc độ hay MFA. Các trách nhiệm đó phải có ở luồng xác thực đầy đủ; không dùng ví dụ để bỏ qua chúng.

Trong Java, `String` là bất biến và không cung cấp thao tác xóa nội dung tại chỗ. Dùng `char[]` có thể cho phép xóa mảng do ứng dụng sở hữu, nhưng không chứng minh framework, bộ giải mã request hay thư viện chưa tạo bản sao. Biện pháp thực tế là hạn chế phạm vi biến, tránh chuyển đổi và sao chép không cần thiết, không giữ bí mật trong cache, đồng thời quản lý quyền truy cập heap dump và công cụ chẩn đoán.

## 7. Ranh giới API: mật khẩu được nhận vào không được phản chiếu ra

Một lỗi thiết kế thường gặp là dùng chung đối tượng cho request đăng ký, entity database và response. Khi đó trường `password` có thể đi theo đối tượng sang cơ chế serialize, `toString()` hoặc mapper mà tác giả ban đầu không dự kiến.

Thiết kế hợp đồng riêng cho từng chiều dữ liệu:

| Đối tượng hoặc luồng | Dữ liệu cần thiết | Dữ liệu không được đưa theo |
| --- | --- | --- |
| Request tạo credential | Định danh thích hợp và mật khẩu mới | Dữ liệu ngoài mục đích của thao tác |
| Bản ghi credential | Account ID, verifier và metadata cần thiết | Mật khẩu gốc |
| Response hồ sơ tài khoản | Account ID, tên hiển thị và trường được phép công khai | Mật khẩu, verifier và khóa bí mật |
| Sự kiện `PasswordChanged` | Account ID, thời điểm, phiên bản credential | Mật khẩu mới hoặc cũ |
| Audit event | Chủ thể, thao tác, kết quả, correlation ID thích hợp | Request body chứa credential |

Response đăng ký không cần trả lại mật khẩu để chứng minh server đã nhận đúng. Tương tự, không đưa mật khẩu vào URL hoặc query string của thao tác đăng nhập, vì URL có thể xuất hiện ở nhiều lớp ghi nhận khác nhau.

Phía trình duyệt cần phân biệt việc người dùng chủ động lưu credential trong trình quản lý mật khẩu với việc ứng dụng tự chép mật khẩu vào `localStorage`, công cụ phân tích hành vi hoặc dữ liệu đồng bộ. Trong thiết kế của bài học, ứng dụng không tự giữ các bản sao này.

Nếu frontend gửi một hash cố định và backend chấp nhận hash đó như credential đăng nhập, hash có thể trở thành bí mật tương đương mật khẩu có thể phát lại. Việc biến đổi ở client không tự thay thế kênh truyền được bảo vệ hoặc cơ chế lưu verifier ở server.

## 8. Log và telemetry là nơi phải kiểm soát từ lúc thu thập

Việc không gọi trực tiếp `log.info(password)` chưa chứng minh mật khẩu không vào log. Nó có thể lọt qua request logger, bộ thu thập exception, proxy, WAF, APM hoặc cơ chế tự động chụp biến cục bộ.

OWASP liệt kê mật khẩu xác thực trong nhóm dữ liệu không nên ghi trực tiếp vào log. [Nguồn: OWASP Logging Cheat Sheet, Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

Với cổng nhân sự giả định, nhóm vận hành có thể đặt hợp đồng thu thập như sau:

| Nơi thu thập | Quyết định thiết kế |
| --- | --- |
| Endpoint đăng nhập, đăng ký, đổi mật khẩu | Không chụp request body |
| Trace của luồng xác thực | Chỉ ghi thuộc tính đã cho phép, như loại thao tác và kết quả |
| Exception khi kiểm tra đầu vào | Dùng mã lỗi không nhúng giá trị mật khẩu |
| Log SQL hoặc công cụ quan sát truy vấn | Không ghi tham số có thể chứa bí mật và hạn chế thu thập verifier |
| Dashboard hỗ trợ | Không có nút xem mật khẩu hiện tại hoặc tải verifier |
| Công cụ quay lại phiên trình duyệt | Không thu nội dung trường credential, kể cả khi người dùng bật hiển thị mật khẩu |

Che mật khẩu ở màn hình dashboard sau khi dữ liệu đã được chuyển đến nhà cung cấp telemetry vẫn để lại bản sao ở nơi thu thập. Cần loại bỏ hoặc lọc trước khi phát sự kiện, đồng thời kiểm tra cấu hình của từng lớp có khả năng ghi dữ liệu.

Không ghi vài ký tự đầu, vài ký tự cuối hoặc độ dài chính xác của mật khẩu để debug. Cũng không thay plaintext bằng hash nhanh của mật khẩu trong log: cách này tạo thêm tập dữ liệu để thử đoán hoặc đối chiếu không cần thiết. Để liên kết request, dùng mã tương quan độc lập với credential.

Một sự kiện minh họa đủ cho mục đích kiểm toán có thể là:

```json
{
  "eventType": "PASSWORD_CHANGED",
  "accountId": "u-104",
  "actorType": "ACCOUNT_OWNER",
  "outcome": "SUCCESS",
  "credentialVersion": 7,
  "correlationId": "req-demo-42"
}
```

Các giá trị trên là dữ liệu giả cho ví dụ. Quyền đọc log, thời gian lưu và các định danh được phép ghi vẫn cần phù hợp với mục đích vận hành.

## 9. Khôi phục tài khoản phải đặt bí mật mới

Một hệ thống lưu verifier đúng cách không có chức năng “gửi lại mật khẩu hiện tại”. Nếu bộ phận hỗ trợ có thể mở hồ sơ và đọc mật khẩu của người dùng, kiến trúc đã giữ lại khả năng khôi phục bí mật gốc ở đâu đó.

Quy trình quên mật khẩu cần xác minh bằng chứng khôi phục, cho phép người dùng đặt mật khẩu mới và lưu verifier mới. Token khôi phục phải có vòng đời thích hợp, được bảo vệ và mất hiệu lực sau sử dụng; email thông báo thay đổi không chứa mật khẩu mới. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Với luồng cấp phát tài khoản của cổng nhân sự, quản trị viên có thể gửi lời mời thiết lập credential thay vì chọn một mật khẩu lâu dài mà mình biết. Link lời mời là một bí mật trao quyền thiết lập; vì vậy không ghi nguyên link hoặc token vào log, ticket hỗ trợ hay hệ thống phân tích không cần nhận nó.

Sau một sự cố chiếm tài khoản, thay mật khẩu không tự thu hồi mọi phiên hoặc khôi phục cấu hình MFA đã bị thay đổi. Luồng phục hồi phải xem xét những khả năng truy cập còn lại của đối thủ và áp dụng chính sách phiên tương ứng.

## 10. Chuyển đổi hệ thống đang lưu plaintext

Phát hiện plaintext trong hệ thống cũ cần dẫn đến một kế hoạch xử lý có kiểm soát. Chỉ thêm cột hash cho tài khoản mới sẽ để lại nguyên rủi ro ở phần dữ liệu cũ.

### 10.1. Ngăn phát sinh bản sao mới

Trước hết cần xác định tất cả đường ghi credential: đăng ký, đổi mật khẩu, import nhân sự, công cụ quản trị và job nền. Đưa chúng về cùng cơ chế tạo verifier. Không dual-write cả plaintext và hash để “dễ rollback”; cách đó tiếp tục tạo dữ liệu mà đợt chuyển đổi muốn loại bỏ.

Song song, xử lý các nơi đang thu đầu vào như log request hoặc sự kiện chứa mật khẩu. Nếu chỉ chuyển đổi database nhưng request body vẫn bị ghi, hệ thống tiếp tục phát sinh bản sao mới ngay sau migration.

### 10.2. Xử lý credential đã tồn tại

Tùy phạm vi sự cố và độ tin cậy của dữ liệu, tổ chức có thể chọn bắt buộc đặt lại mật khẩu, hoặc chuyển đổi có kiểm soát từng bản ghi plaintext hiện có thành verifier. Trường hợp chuyển đổi cần môi trường cô lập phù hợp, quyền tối thiểu, theo dõi tiến độ bằng ID và không tạo file trung gian chứa mật khẩu.

Nếu người dùng đổi mật khẩu đồng thời với migration, không được để job ghi một verifier tạo từ mật khẩu cũ đè lên credential mới. Cần cơ chế cập nhật có điều kiện theo phiên bản hoặc một phương án phối hợp ghi đã được thiết kế trước.

Chuyển plaintext thành hash không làm một mật khẩu từng bị lộ trở lại bí mật. Nếu có dấu hiệu dữ liệu đã ra ngoài, quyết định đặt lại mật khẩu và xử lý phiên cần dựa trên sự cố đó, không chỉ dựa trên việc migration chạy thành công.

### 10.3. Xử lý backup, replica và đường khôi phục

Sau chuyển đổi, một snapshot cũ vẫn có thể chứa plaintext. Cần kiểm kê replica, bản dump, file export, dữ liệu CDC, môi trường thử nghiệm và tài liệu hỗ trợ đã từng nhận dữ liệu này.

Với bản sao lưu bất biến hoặc dữ liệu phải giữ để điều tra, không giả định có thể xóa chọn lọc ngay. Cần giới hạn truy cập, quản lý khóa, thời hạn lưu và quy trình xử lý theo chính sách áp dụng. Trước khi mở lại dịch vụ từ một backup cũ, phải bảo đảm dữ liệu và phần mềm được đưa về trạng thái đã chuyển đổi; nếu không, thao tác restore có thể tái đưa plaintext vào production.

Kế hoạch rollback cũng không nên phục hồi một phiên bản ứng dụng tiếp tục ghi mật khẩu thô. Khả năng quay lại an toàn phải được thiết kế trong giai đoạn chuyển đổi, thay vì dựa vào việc giữ bí mật gốc trong một cột dự phòng.

## 11. Ứng phó khi mật khẩu đã vào log hoặc bị xuất ra ngoài

Đây là sự cố lộ credential, không chỉ là lỗi định dạng dữ liệu. Người xử lý cần xác định dữ liệu nào đã được thu thập, khoảng thời gian, tài khoản bị ảnh hưởng, nơi nhận dữ liệu và ai có khả năng truy cập.

Các hành động cần phối hợp gồm chặn luồng tiếp tục ghi, hạn chế truy cập bản sao bị ảnh hưởng, bảo toàn chứng cứ theo quy trình, thay credential khi cần và đánh giá phiên đang hoạt động. Không sao chép mật khẩu vào ticket để chứng minh lỗi. Có thể ghi loại trường, phạm vi bản ghi và một dấu hiệu kiểm chứng không tiết lộ bí mật thật.

Nếu log có cả credential của dịch vụ hoặc tài khoản đặc quyền, phải xử lý riêng theo vòng đời của chúng. Mật khẩu người dùng, token phiên, khóa API và bí mật workload không nhất thiết có cùng cơ chế thu hồi.

Sau khi thay đổi cấu hình, cần xác nhận lỗi không còn ở cả đường thành công lẫn đường thất bại. Một request bị từ chối do validation vẫn có thể bị exception handler ghi toàn bộ payload.

## 12. Những tình huống dùng để kiểm chứng thiết kế

Các kiểm tra dưới đây sử dụng tài khoản thử và bí mật giả được tạo riêng cho đợt kiểm tra. Không dùng mật khẩu thật của người dùng làm dữ liệu dò tìm.

| Tình huống | Bằng chứng mong đợi |
| --- | --- |
| Đăng ký tài khoản thử thành công | Kho credential chỉ có verifier; response và sự kiện không chứa đầu vào mật khẩu |
| Đăng ký thất bại do validation hoặc lỗi lưu dữ liệu | Log và bản ghi lỗi không chứa mật khẩu của request |
| Đăng nhập đúng hoặc sai | Kết quả được ghi bằng metadata cần thiết, không kèm credential |
| Đổi và đặt lại mật khẩu | Verifier được thay; mật khẩu cũ và mới không xuất hiện trong log hoặc email |
| Serialize đối tượng tài khoản | Chỉ các trường response được cho phép xuất hiện |
| Gửi sự kiện nghiệp vụ | Payload không chứa plaintext hoặc verifier ngoài mục đích cần thiết |
| Khôi phục backup cũ ở môi trường cô lập | Có bước chuyển đổi và xác minh trước khi phục vụ truy cập |
| Bật mức log chẩn đoán | Cấu hình vẫn ngăn thu thập credential |

Một kết quả tìm kiếm không thấy chuỗi giả trong một file log chưa chứng minh toàn bộ hệ thống không lưu plaintext. Bằng chứng cần bao phủ các nơi dữ liệu thực sự đi qua: collector, hàng đợi, kho log tập trung, bản ghi exception và công cụ của bên thứ ba trong phạm vi thiết kế.

## 13. Gắn với danh tính, đặc quyền và ít quyền nhất

Trong mô hình SSO qua OIDC, ứng dụng dựa vào IdP thường không cần nhận hoặc lưu mật khẩu của người dùng. Nếu ứng dụng vẫn yêu cầu một bản sao mật khẩu để đồng bộ nội bộ, cần xem lại trách nhiệm của từng thành phần. Các tài khoản cục bộ dự phòng phải được quản lý như một đường xác thực riêng.

Đối với RBAC hoặc ABAC, phân quyền đọc hồ sơ không nên kéo theo quyền đọc verifier. Tách quyền quản trị danh tính, quyền thay credential và quyền truy cập dữ liệu xác thực giúp giảm phạm vi ảnh hưởng của từng vai trò. Nhân viên hỗ trợ có thể hỗ trợ quy trình đặt lại mật khẩu mà không cần biết mật khẩu hiện tại.

Một ứng dụng bắt buộc giữ bí mật để đăng nhập vào hệ thống cũ là bài toán quản lý secret riêng, cần khả năng khôi phục có kiểm soát và nên được xem xét thay bằng cơ chế ủy quyền hoặc liên kết danh tính khi khả thi. Không dùng trường hợp đó để hợp thức hóa việc lưu mật khẩu người dùng trong bảng hồ sơ hoặc file cấu hình.

Đối với workload, ưu tiên thiết kế credential và vòng đời phù hợp với danh tính máy, chẳng hạn credential ngắn hạn khi kiến trúc hỗ trợ. Nguyên tắc ít quyền nhất áp dụng cho cả quyền dùng bí mật, quyền đọc kho lưu và quyền truy cập công cụ chẩn đoán có thể quan sát bí mật trong bộ nhớ.

## 14. Bài tập vận dụng

Một cổng nhân sự đã băm mật khẩu trong database, nhưng APM đang ghi request đăng ký và công cụ hỗ trợ có nút tải toàn bộ entity tài khoản. Backup từ sáu tháng trước còn chứa cột plaintext.

Hãy đề xuất phương án trả lời bốn câu hỏi:

1. Những nơi nào đang giữ hoặc có thể xuất credential, và quyền nào cho phép truy cập chúng?
2. Cần thay đổi hợp đồng request, response, sự kiện và telemetry ra sao để ngăn phát sinh bản sao mới?
3. Phải xử lý credential bị ảnh hưởng và đường khôi phục backup như thế nào để không tái đưa plaintext vào vận hành?
4. Cần bằng chứng nào để xác nhận đường đăng ký, đăng nhập và đặt lại mật khẩu đều tuân thủ thiết kế?

Phương án cần chỉ rõ đường đi của bí mật và trách nhiệm của từng thành phần. Việc không còn cột `password_plaintext` là một điều kiện cần, nhưng hệ thống chỉ thực hiện được nguyên tắc khi những đường sao chép và sử dụng credential cũng được kiểm soát.
