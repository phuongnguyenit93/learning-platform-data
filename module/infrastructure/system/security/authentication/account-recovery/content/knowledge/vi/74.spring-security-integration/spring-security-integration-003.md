# PasswordEncoder integration — Tích hợp lưu mật khẩu trong luồng khôi phục tài khoản

## 1. Đặt PasswordEncoder đúng chỗ trong account recovery

Trong module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, một người dùng có thể mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mỗi tình huống đòi hỏi bằng chứng và phạm vi thao tác khác nhau. PasswordEncoder chỉ tham gia khi hệ thống thực sự cần lưu hoặc kiểm tra một mật khẩu.

Nó không xác minh quyền khôi phục tài khoản, không phát token dùng một lần, không quyết định ai được xóa MFA và không tự thu hồi session. Chẳng hạn, một recovery grant chỉ cho phép đăng ký lại thiết bị xác thực không mặc nhiên cho phép đặt mật khẩu mới.

Bài học này tập trung vào việc nối ba thành phần:

- Recovery service quyết định một chủ thể có được thay mật khẩu của tài khoản cụ thể hay không.
- PasswordEncoder tạo biểu diễn mật khẩu phù hợp để lưu trữ và kiểm tra.
- Kho credential và cơ chế đăng nhập cùng hiểu biểu diễn ấy, kể cả khi hệ thống đang chuyển đổi thuật toán.

Các ví dụ dùng Java 17 trở lên và API Spring Security Servlet dòng 6.5 làm mốc tham chiếu. Đây là lựa chọn để làm rõ API, không phải khẳng định phiên bản dependency của ứng dụng đang triển khai. Các lớp miền, repository và policy trong ví dụ là hợp đồng cần được ứng dụng hiện thực.

## 2. Phân biệt mật khẩu, hash và bằng chứng recovery

Một request hoàn tất khôi phục có thể mang cả recovery token và mật khẩu mới, nhưng hai giá trị có vai trò khác nhau:

| Giá trị | Câu hỏi cần giải quyết | Cách xử lý ở ranh giới ứng dụng |
|---|---|---|
| Recovery token hoặc grant | Người gọi có quyền thực hiện thao tác nào, cho tài khoản nào? | Verifier, policy và trạng thái dùng một lần có thẩm quyền |
| Mật khẩu mới dạng người dùng nhập | Giá trị này có đáp ứng policy đặt mật khẩu không? | Kiểm tra đầu vào rồi chuyển cho PasswordEncoder |
| Mật khẩu đã encode | Đăng nhập bằng mật khẩu nào có thể được kiểm tra? | Lưu nguyên biểu diễn, chỉ dùng ở thành phần được cấp quyền |
| Password credential version | Một thay đổi mới hơn có xảy ra không? | Kiểm tra cạnh tranh khi cập nhật và khi nâng cấp hash |
| Authentication/session | Người dùng đang có quyền truy cập nào? | Cơ chế đăng nhập và kiểm soát session riêng |

Không dùng PasswordEncoder thay cho toàn bộ kho recovery token. Một token ngẫu nhiên có entropy cao, mã OTP ngắn và mật khẩu do con người chọn có mô hình tấn công khác nhau; chi phí kiểm tra và cách chống đoán phải được thiết kế theo từng loại. Bài này không quy định thuật toán lưu token.

Đối với mật khẩu, việc lưu biểu diễn một chiều giúp giảm hậu quả khi dữ liệu credential bị lộ. Tuy nhiên, cơ sở dữ liệu chứa hash vẫn là dữ liệu nhạy cảm: kẻ có bản sao có thể thử đoán ngoại tuyến. Vì vậy, không đưa hash vào DTO công khai, log nghiệp vụ hoặc email thông báo recovery.

## 3. Ba phương thức cần hiểu chính xác

Theo hợp đồng [PasswordEncoder](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/password/PasswordEncoder.html), có ba thao tác đáng chú ý:

~~~java
String encode(CharSequence rawPassword);

boolean matches(CharSequence rawPassword, String encodedPassword);

boolean upgradeEncoding(String encodedPassword);
~~~

encode nhận mật khẩu chưa encode. matches nhận mật khẩu người dùng đưa ở đối số thứ nhất và biểu diễn đã lưu ở đối số thứ hai. upgradeEncoding cho biết biểu diễn có nên được nâng cấp theo encoder hiện tại hay không; phương thức này không tự ghi cơ sở dữ liệu.

### 3.1. Không so sánh bằng cách encode lại rồi dùng equals

Sai lầm phổ biến:

~~~java
// Sai: không dùng cách này để xác minh mật khẩu.
boolean accepted = encoder.encode(candidate).equals(storedPassword);
~~~

Một encoder sử dụng salt ngẫu nhiên có thể tạo nhiều biểu diễn khác nhau cho cùng một mật khẩu. Cách tích hợp đúng là:

~~~java
boolean accepted = encoder.matches(candidate, storedPassword);
~~~

Salt và tham số cần thiết thường nằm trong biểu diễn mà implementation tạo ra. Ứng dụng không tự nối username làm salt, không cắt bỏ một phần hash và không tìm cách giải mã mật khẩu để so sánh.

### 3.2. Không encode biểu diễn đã encode

Nếu repository nhận một chuỗi đã encode từ service rồi tiếp tục gọi encode, dữ liệu sẽ trở thành một lớp hash khác. Sau đó, mật khẩu gốc không còn khớp theo đường đăng nhập thông thường.

Hợp đồng nên thể hiện rõ mỗi điểm nhận loại dữ liệu nào:

~~~text
Controller → recovery service: mật khẩu mới dạng người dùng nhập
Recovery service → PasswordEncoder: mật khẩu chưa encode
Recovery service → credential repository: biểu diễn đã encode
UserDetailsService → authentication provider: biểu diễn đã lưu
~~~

Tên biến như rawPassword và encodedPassword có ích, nhưng chưa phải cơ chế bảo vệ. Không để mapper, entity listener hoặc setter tự động encode thêm một lần mà người gọi không biết.

### 3.3. Hash không phải kiểm tra chất lượng mật khẩu

encode có thể tạo một hash hợp lệ cho một mật khẩu rất dễ đoán. Policy về độ dài, mật khẩu phổ biến hoặc đã bị lộ phải được thực thi trước khi lưu credential mới. Việc đăng nhập về sau chạy một checker nào đó không bảo đảm endpoint recovery cũng đã chạy checker ấy.

## 4. Dùng một hợp đồng định dạng cho đăng nhập và recovery

Theo [DelegatingPasswordEncoder](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/password/DelegatingPasswordEncoder.html), định dạng mặc định có dạng:

~~~text
{id}encodedPassword
~~~

id chọn implementation dùng để kiểm tra biểu diễn đã lưu. idForEncode chọn implementation cho lần encode mới. Hai quyết định này giúp ứng dụng ghi bằng profile hiện tại và vẫn đọc được profile cũ đã được hỗ trợ rõ ràng.

Một thiết kế minh họa:

~~~text
Ghi mới sau recovery:
    {argon2id-recovery-v1}<biểu diễn Argon2 do encoder tạo>

Đọc khi đăng nhập:
    argon2id-recovery-v1 → encoder Argon2 đã cấu hình
    bcrypt             → encoder BCrypt cho dữ liệu cũ đã kiểm kê
~~~

Chuỗi trong dấu ngoặc nhọn là khóa do ứng dụng chọn. Tên argon2id-recovery-v1 không phải một ID được Spring tự nhận diện khi thiếu mapping tương ứng.

Không nhận encodedPassword từ client rồi ghi thẳng vào cột password. Nếu người gọi tự chọn được prefix hoặc cost, họ có thể tác động tới định dạng credential mà máy chủ sẽ xử lý. Endpoint đặt mật khẩu nhận raw password và máy chủ tự chọn profile ghi.

### 4.1. Một bean minh họa với profile ghi rõ ràng

[Argon2PasswordEncoder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/crypto/argon2/Argon2PasswordEncoder.html) cung cấp constructor nhận độ dài salt, độ dài hash, parallelism, memory cost và iterations. Trong implementation tham chiếu, cần đáp ứng dependency Bouncy Castle tương ứng. Không suy rằng có spring-security-crypto là mọi provider mật mã bổ sung đều đã sẵn sàng.

Ví dụ dưới đây minh họa Argon2id với bộ tham số memory 19 MiB, iterations 2, parallelism 1. Đây là một bộ khởi điểm được nêu trong [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#argon2id); lựa chọn triển khai cần được đối chiếu yêu cầu hiện hành và đo trên hạ tầng thực tế.

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration(proxyBeanMethods = false)
public class PasswordEncodingConfiguration {

    @Bean
    PasswordEncoder accountPasswordEncoder() {
        String currentId = "argon2id-recovery-v1";

        PasswordEncoder current = new Argon2PasswordEncoder(
            16,       // saltLength: byte
            32,       // hashLength: byte
            1,        // parallelism
            19 * 1024, // memory: KiB
            2         // iterations
        );

        Map<String, PasswordEncoder> readers = Map.of(
            currentId, current,
            "bcrypt", new BCryptPasswordEncoder()
        );

        return new DelegatingPasswordEncoder(currentId, readers);
    }
}
~~~

Mapping bcrypt trong ví dụ chỉ phù hợp nếu dữ liệu cũ thực sự mang prefix bcrypt và có nguồn gốc hợp lệ. Nó không chuyển đổi dữ liệu cũ, không tự thêm prefix và không yêu cầu recovery ghi bcrypt.

Việc chọn thuật toán còn phụ thuộc khả năng vận hành và yêu cầu của môi trường. Nếu hệ thống có yêu cầu dùng module mật mã được thẩm định, lựa chọn tên thuật toán đơn thuần chưa chứng minh đã đáp ứng yêu cầu đó. Cần đánh giá cả implementation, provider và cấu hình.

### 4.2. Chia sẻ bean và tránh các encoder tự phát

Cả service recovery và authentication provider phải được nối với cùng hợp đồng đọc/ghi. Với ứng dụng có nhiều PasswordEncoder, dùng qualifier rõ ràng ở mọi nơi liên quan. Không tạo một encoder khác bằng new bên trong controller vì ví dụ đó tiện hơn.

Một instance dùng để ghi mới có thể chứa nhiều reader cho dữ liệu cũ. Điều cần nhất quán là profile ghi đã phê duyệt, tập định dạng được chấp nhận và cách xử lý dữ liệu không nhận diện được; không phải mọi lớp trong ứng dụng đều có quyền gọi encode.

## 5. Nối với cơ chế đăng nhập thật sự

Trong kiến trúc đăng nhập bằng username/password, [DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html) lấy UserDetails từ UserDetailsService rồi dùng PasswordEncoder kiểm tra mật khẩu. Vì vậy, file cấu hình recovery chưa đủ: đường đăng nhập phải đọc được hash mà recovery tạo.

Một bean provider cho API tham chiếu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration(proxyBeanMethods = false)
public class PasswordAuthenticationConfiguration {

    @Bean
    DaoAuthenticationProvider passwordAuthenticationProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder accountPasswordEncoder) {

        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);

        provider.setPasswordEncoder(accountPasswordEncoder);
        return provider;
    }
}
~~~

Constructor nhận UserDetailsService và setter của encoder có trong [API DaoAuthenticationProvider 6.5](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html). Nếu ứng dụng tự tạo AuthenticationManager hoặc có nhiều filter chain, cần đăng ký provider này vào đúng manager/chain sử dụng username/password. Chỉ khai báo bean chưa chứng minh request đăng nhập thực tế đã đi qua nó.

UserDetailsService phải trả nguyên biểu diễn đã lưu trong getPassword(). Nó không giải mã, encode lại hoặc loại prefix trước khi trả dữ liệu. Tenant và account phải được giải quyết theo mô hình identity của ứng dụng; username trùng giữa hai tenant không được dẫn tới đọc nhầm credential.

Nếu ứng dụng xác thực tại một identity provider bên ngoài, thay hash ở một bảng local chưa chắc thay được mật khẩu đăng nhập. Recovery phải gọi đúng hệ thống đang có thẩm quyền với credential, thay vì tạo một mật khẩu local mà đường đăng nhập không sử dụng.

## 6. Policy đầu vào phải nhất quán ở các luồng đặt mật khẩu

Đăng ký, đổi mật khẩu và recovery có thể khác nhau về bằng chứng cho phép thao tác, nhưng cần thống nhất quy tắc xử lý mật khẩu mới. Một giá trị được endpoint recovery chấp nhận phải có thể được đường đăng nhập kiểm tra đúng.

### 6.1. Không âm thầm biến đổi mật khẩu

Không tự trim, lowercase hoặc bỏ ký tự ở một luồng riêng. Nếu recovery encode một giá trị đã bị trim nhưng login kiểm tra nguyên giá trị người dùng nhập, người dùng có thể bị khóa ngay sau khi khôi phục.

Unicode làm vấn đề rõ hơn: số đơn vị UTF-16 của String.length(), số code point và số byte UTF-8 không phải cùng một đại lượng. Chính sách giới hạn phải nói rõ đang đếm gì. Nếu sản phẩm chọn chuẩn hóa Unicode, phải định nghĩa và áp dụng nhất quán ở mọi đường tạo và kiểm tra mật khẩu, đồng thời có kế hoạch tương thích dữ liệu cũ.

Không chuyển sang một quy tắc chuẩn hóa mới chỉ bằng cách sửa frontend. Backend, client khác và credential cũ vẫn tồn tại.

### 6.2. Giới hạn đầu vào trước thao tác tốn tài nguyên

Giới hạn kích thước HTTP body và độ dài trường trước khi gọi encoder. Sau đó áp dụng policy mật khẩu mới và kiểm tra mật khẩu đã bị lộ theo cơ chế của sản phẩm. Nếu checker cần dịch vụ bên ngoài, không gửi nguyên mật khẩu qua một API tự phát và không đưa raw password vào hàng đợi retry.

Nếu còn hỗ trợ BCrypt, phải hiểu giới hạn đầu vào của implementation; giới hạn thường được nhắc tới là 72 byte, không phải 72 ký tự. Không tự cắt một mật khẩu dài để vừa giới hạn, vì hai chuỗi khác nhau có thể trở thành cùng đầu vào. Tài liệu [OWASP về giới hạn BCrypt](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#input-limits-of-bcrypt) là điểm tham chiếu cho việc thiết kế policy và kiểm thử tương thích.

### 6.3. Khôi phục mật khẩu khác với buộc chứng minh mật khẩu cũ

Người quên mật khẩu không thể đáp ứng yêu cầu nhập mật khẩu cũ chỉ để được recovery. Quyền thay đổi phải đến từ bằng chứng recovery đã được policy chấp nhận.

Sản phẩm có thể cấm dùng lại một số mật khẩu gần nhất. Khi đó, so sánh với lịch sử hash là một policy riêng, tốn tài nguyên và cần được giới hạn. Nó không biến thành yêu cầu người dùng phải chứng minh mật khẩu cũ. Không lưu plaintext để xây lịch sử và không so sánh hash mới bằng equals để phát hiện việc dùng lại.

## 7. Thứ tự hoàn tất recovery: kiểm tra quyền, encode, rồi commit có điều kiện

Hash mật khẩu có chủ ý tiêu tốn tài nguyên. Giữ khóa cơ sở dữ liệu trong suốt thời gian encode có thể làm tăng tranh chấp; ngược lại, encode trước khi kiểm tra bất kỳ bằng chứng nào tạo cơ hội lạm dụng tài nguyên.

Một thiết kế có thể chia công việc thành hai giai đoạn:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Recovery service
    participant E as PasswordEncoder
    participant D as Kho trạng thái có thẩm quyền
    C->>R: Token recovery và mật khẩu mới
    R->>R: Giới hạn đầu vào và admission control
    R->>D: Xác minh sơ bộ grant, subject, tenant, purpose
    D-->>R: Snapshot đã xác minh và credential version
    R->>R: Kiểm tra policy mật khẩu mới
    R->>E: encode(rawPassword)
    E-->>R: encodedPassword
    R->>D: Commit có điều kiện trong transaction
    Note over D: Kiểm tra lại grant, expiry, policy và version<br/>Đổi hash, tiêu thụ grant, ghi event cùng transaction
    D-->>R: Commit thành công hoặc từ chối
    R-->>C: Kết quả công khai theo policy
~~~

Snapshot đã xác minh chỉ giúp chuẩn bị công việc. Nó không giữ cho grant còn hợp lệ trong lúc encode. Grant có thể hết hạn, bị hủy hoặc mất hiệu lực khi một lần đổi credential khác thành công.

### 7.1. Một service minh họa ranh giới trách nhiệm

Đoạn Java sau là cấu trúc điều phối, không phải verifier hoặc implementation transaction hoàn chỉnh. Các kiểu được sử dụng là hợp đồng của ứng dụng, không phải API có sẵn trong Spring Security.

~~~java
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class PasswordRecoveryCompletionService {

    private final RecoveryAdmission admission;
    private final RecoveryGrantVerifier grantVerifier;
    private final NewPasswordPolicy passwordPolicy;
    private final PasswordEncoder passwordEncoder;
    private final AtomicPasswordRecoveryWriter writer;

    public PasswordRecoveryCompletionService(
            RecoveryAdmission admission,
            RecoveryGrantVerifier grantVerifier,
            NewPasswordPolicy passwordPolicy,
            PasswordEncoder passwordEncoder,
            AtomicPasswordRecoveryWriter writer) {
        this.admission = admission;
        this.grantVerifier = grantVerifier;
        this.passwordPolicy = passwordPolicy;
        this.passwordEncoder = passwordEncoder;
        this.writer = writer;
    }

    public CompletionReceipt complete(PasswordRecoveryInput input) {
        admission.check(input.trustedRequestContext());
        passwordPolicy.validateInputBounds(input.newPassword());

        VerifiedPasswordGrant grant =
            grantVerifier.verifyForPasswordReplacement(
                input.trustedTenant(),
                input.recoveryToken()
            );

        passwordPolicy.validateNewPassword(
            grant.subject(),
            input.newPassword()
        );

        String encodedPassword =
            passwordEncoder.encode(input.newPassword());

        return writer.commitIfStillAuthorized(
            grant,
            encodedPassword
        );
    }
}
~~~

Các hợp đồng quan trọng trong ví dụ:

| Thành phần | Điều implementation phải bảo đảm |
|---|---|
| PasswordRecoveryInput | Không tự ghi secret qua toString, log hoặc serialization phản hồi |
| trustedTenant và trustedRequestContext | Do server giải quyết theo nguồn tin cậy, không chỉ đổi tên dữ liệu do client gửi |
| RecoveryAdmission | Kiểm soát số request và số phép tính hash được nhận xử lý |
| RecoveryGrantVerifier | Xác minh bằng chứng, tenant, subject, purpose và trạng thái trước khi encode |
| NewPasswordPolicy | Kiểm tra raw password, không âm thầm biến đổi nó |
| AtomicPasswordRecoveryWriter | Đọc lại trạng thái có thẩm quyền và ghi các thay đổi cần nguyên tử |
| CompletionReceipt | Chỉ mang kết quả phù hợp, không chứa raw password, hash hoặc token |

Một record chứa secret cần được xem xét cẩn thận: toString mặc định có thể đưa giá trị trường vào log. Override toString hoặc dùng loại dữ liệu phù hợp chỉ đóng được một đường rò rỉ; body logging và APM vẫn cần cấu hình riêng.

### 7.2. Những điều phải kiểm tra lại khi ghi

AtomicPasswordRecoveryWriter không được hiểu grant snapshot là một lệnh cập nhật đã được duyệt vĩnh viễn. Tại thời điểm commit, nó cần kiểm tra tối thiểu:

1. Grant vẫn thuộc đúng tenant và subject.
2. Mục đích và scope vẫn cho phép thay mật khẩu.
3. Grant chưa hết hạn theo thời gian có thẩm quyền, chưa bị dùng và chưa bị hủy.
4. Trạng thái account vẫn cho phép recovery; không có lệnh quản trị hoặc policy mới đã vô hiệu hóa grant.
5. Credential version hoặc security state được ràng buộc với grant chưa bị một thao tác khác thay đổi.
6. Các điều kiện bổ sung của quyết định rủi ro vẫn thỏa mãn theo policy sản phẩm.

Nếu quy tắc mật khẩu hoặc profile encoder có thể thay đổi ngay giữa một request, hệ thống cần quy định version policy được chấp nhận khi commit. Không âm thầm chấp nhận một snapshot cũ sau một thay đổi khẩn cấp mà policy yêu cầu áp dụng ngay.

### 7.3. Transaction cần bao gồm đúng các thay đổi cốt lõi

Một transaction trong cùng kho trạng thái có thể thực hiện:

~~~text
BEGIN
    Khóa/đọc grant và credential theo thứ tự khóa thống nhất.
    Đọc lại trạng thái account và thời gian có thẩm quyền.
    Kiểm tra tenant, subject, purpose, expiry, state, version.

    Cập nhật encoded password với điều kiện credential version cũ còn đúng.
    Tăng credential version và trạng thái bảo mật cần thiết.
    Chuyển grant ACTIVE → CONSUMED bằng cập nhật có điều kiện.
    Hoàn tất attempt và ghi sự kiện outbox không chứa secret.

    Nếu bất kỳ cập nhật bắt buộc nào không tác động đúng một bản ghi:
        ROLLBACK toàn bộ.
    Ngược lại:
        COMMIT.
END
~~~

Tất cả cập nhật có điều kiện phải được kiểm tra số bản ghi thực sự thay đổi. Không đổi mật khẩu xong mới phát hiện thao tác consume token trả về 0 rồi vẫn commit.

Nếu dùng Spring transaction, đặt ranh giới transaction ở implementation writer được gọi qua Spring proxy phù hợp. Không giả định gọi một method có @Transactional từ chính cùng object sẽ luôn mở transaction. Kiểu exception và cấu hình rollback cũng phải làm cho mọi lỗi của chuỗi cập nhật bắt buộc được rollback như mong đợi.

Nếu password authority và grant store ở hai hệ thống không có transaction chung, sơ đồ trên không còn là một bảo đảm nguyên tử tự động. Cần thiết kế orchestration, trạng thái pending, idempotency và reconciliation cho hệ thống đó. Chỉ thêm @Transactional ở một service local không tạo transaction phân tán.

### 7.4. Hai request cùng sử dụng một grant

Hai request có thể cùng vượt qua bước xác minh sơ bộ và cùng encode. Điều đó chưa vi phạm tính dùng một lần nếu chỉ một transaction được phép commit thay đổi.

~~~text
Request A: đọc version 41 → encode password A → commit version 42
Request B: đọc version 41 → encode password B → bị từ chối khi commit
~~~

Request B phải thất bại do grant đã bị consume hoặc version không còn đúng. Nó không được ghi password B đè lên password A rồi báo token đã dùng. Cũng không được tự cấp một grant mới để tiếp tục retry.

Nếu kết nối bị mất sau commit nhưng trước response, client có thể không biết kết quả. Chính sách retry cần dựa trên kết quả bền vững và cơ chế ràng buộc người gọi đã thiết kế, không đơn giản cho phép dùng lại mọi token đã consumed. Không ghi raw password vào bảng idempotency hoặc queue để giải quyết tình huống này.

## 8. Phân biệt thay mật khẩu với nâng cấp hash

Có hai sự kiện rất dễ bị gộp nhầm:

| Tình huống | Giá trị bí mật do người dùng sử dụng | Điều thay đổi trong kho |
|---|---|---|
| Hoàn tất password recovery | Một mật khẩu mới được policy chấp nhận | Credential được thay đổi theo quyền recovery |
| Rehash sau đăng nhập thành công | Mật khẩu đang dùng được xác minh thành công | Biểu diễn lưu trữ được nâng cấp |

Ở recovery, gọi encode mật khẩu mới bằng profile ghi hiện tại. Không cần chờ upgradeEncoding của hash cũ trả true; dù hash cũ đang mạnh, yêu cầu đã được cấp quyền vẫn là thay mật khẩu.

Ở rehash, ứng dụng thường cần có raw password vừa được xác minh để tạo biểu diễn mới. Không thể nâng cấp mọi hash bằng cách lấy hash cũ làm raw password rồi encode tiếp, và không thể khôi phục raw password từ hash để chạy một batch migration.

### 8.1. UserDetailsPasswordService nhận mật khẩu đã encode

Spring có điểm nối [UserDetailsPasswordService.updatePassword](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/userdetails/UserDetailsPasswordService.html). Theo hợp đồng API, đối số newPassword của method này là mật khẩu đã được encoder cấu hình encode.

~~~java
// Đăng ký thêm nếu ứng dụng triển khai cơ chế nâng cấp hash khi login.
provider.setUserDetailsPasswordService(userDetailsPasswordService);
~~~

Implementation của userDetailsPasswordService lưu nguyên biểu diễn được truyền vào, đồng thời xử lý identity và cạnh tranh cập nhật theo mô hình dữ liệu của ứng dụng. Không encode lại đối số chỉ vì tên method có chữ Password.

Điểm nối này không tự cấp quyền recovery và không phải API công khai cho controller đổi mật khẩu theo account ID. Nó phục vụ một luồng có điều kiện gọi và ngữ cảnh xác thực cụ thể.

### 8.2. Cuộc đua giữa login rehash và recovery

Một lỗi nguy hiểm có thể xảy ra như sau:

~~~text
T1  Login đọc hash H_old ở credential version 41.
T2  Login xác minh đúng mật khẩu cũ và bắt đầu tạo H_upgraded.
T3  Recovery đặt mật khẩu mới, ghi H_new ở version 42.
T4  Login ghi H_upgraded không kiểm tra version.
~~~

Ở T4, mật khẩu cũ đã quay trở lại nếu update chỉ dựa trên account ID. Cách phòng tránh là gắn rehash với snapshot được xác minh và cập nhật có điều kiện, chẳng hạn:

~~~sql
UPDATE password_credential
SET encoded_password = :upgraded_password,
    credential_version = credential_version + 1
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND credential_version = :version_observed_during_authentication;
~~~

Câu SQL minh họa một cơ chế optimistic concurrency. Các placeholder là bind parameter. Không log bound value của upgraded_password. Mọi đường cập nhật credential phải tuân thủ quy tắc version thì điều kiện mới có ý nghĩa.

Nếu update trả về 0, không đọc version mới rồi ghi lại hash được tạo từ mật khẩu cũ. Phải xử lý xung đột theo policy. UserDetailsPasswordService không bắt buộc mang version trong interface, nên ứng dụng có thể cần một UserDetails tùy biến hoặc ngữ cảnh nội bộ thích hợp để giữ snapshot; không suy từ username rằng dữ liệu chưa thay đổi.

Ngăn việc ghi đè hash cũng chưa ngăn một request đăng nhập đang chạy tạo session từ snapshot cũ. Nếu policy yêu cầu recovery vô hiệu hóa cả những đăng nhập cạnh tranh, bước cấp session/token phải được ràng buộc với trạng thái bảo mật hiện hành, và các request dùng session phải chịu kiểm tra thu hồi đã thiết kế.

### 8.3. Tách ý nghĩa version để tránh hiệu ứng phụ

Có thể dùng credential_version cho tính nhất quán khi thay đổi biểu diễn lưu trữ và một auth_epoch/security_version riêng cho việc vô hiệu hóa quyền truy cập.

Rehash cùng một mật khẩu không nhất thiết phải đăng xuất toàn bộ người dùng. Thay mật khẩu qua recovery lại có thể yêu cầu thu hồi session theo policy. Nếu chỉ dùng một counter cho mọi mục đích, đội triển khai cần hiểu rõ mỗi lần tăng sẽ tác động tới đăng nhập, token, cache và grant như thế nào.

## 9. Dữ liệu cũ và migration định dạng

### 9.1. Thiếu prefix không phải tín hiệu cho phép fallback

DelegatingPasswordEncoder mặc định có thể ném IllegalArgumentException khi ID không có mapping, kể cả trường hợp không tìm thấy ID. Không chữa lỗi này bằng cách mặc định mọi dữ liệu không nhận diện được là plaintext hoặc cho mọi encoder lần lượt thử đến khi có một kết quả true.

Nếu dữ liệu lịch sử là BCrypt không có prefix, một migration có kiểm kê có thể thêm đúng prefix mà không thay hash bên trong. Điều đó chỉ hợp lệ sau khi đã xác định chính xác nguồn dữ liệu và định dạng. Không thêm bcrypt vào mọi chuỗi chỉ vì chúng có vẻ dài tương tự.

Migration prefix là một thao tác dữ liệu được kiểm soát riêng. Endpoint recovery vẫn nhận raw password và ghi định dạng hiện tại; nó không cố sửa toàn bộ bảng credential trong mỗi request.

### 9.2. Không mở reader plaintext cho tiện kiểm thử

Chỉ đưa những định dạng legacy cần thiết vào mapping. Việc hỗ trợ đọc một profile cũ làm rộng tập dữ liệu mà ứng dụng chấp nhận; nó phải có lý do, theo dõi số bản ghi còn lại và kế hoạch loại bỏ.

Không thêm NoOpPasswordEncoder vào production chỉ để vượt qua lỗi dữ liệu kiểm thử. Với dữ liệu không biết nguồn gốc hoặc có dấu hiệu hỏng, từ chối xác thực và báo lỗi vận hành phù hợp; không coi exception của encoder là đăng nhập thành công.

### 9.3. Triển khai reader trước writer

Trong rolling deployment, một node mới có thể ghi prefix mà node cũ chưa nhận diện. Sau recovery, đăng nhập thành công hay thất bại sẽ phụ thuộc request rơi vào node nào.

Một trình tự triển khai có kiểm soát:

1. Bổ sung reader cho profile mới ở mọi node và đường đăng nhập liên quan.
2. Xác minh chúng đọc được các test vector phù hợp, kể cả dependency mật mã.
3. Chuyển profile ghi mới của đăng ký, đổi mật khẩu, recovery và rehash.
4. Theo dõi phân bố profile và xử lý credential cũ theo kế hoạch.
5. Chỉ gỡ reader cũ sau khi đã đáp ứng điều kiện migration và rollback.

Không đổi mapping của một ID đang tồn tại sang một định dạng không tương thích. Khi đổi thuật toán, pepper scheme hoặc cấu trúc biểu diễn, một ID mới thường giúp nhận diện chính sách rõ hơn. Với tham số đã nằm trong biểu diễn, cách đặt ID còn cần phù hợp với implementation và kế hoạch nâng cấp của sản phẩm.

## 10. Lưu trữ và bí mật: bảo toàn cả biểu diễn

### 10.1. Cột credential phải chứa được dữ liệu hiện tại và kế tiếp

Một schema vừa đủ cho chuỗi BCrypt trần có thể không chứa được prefix và biểu diễn của thuật toán khác. Nếu cột hoặc mapper cắt ngắn dữ liệu, recovery có thể báo thành công nhưng mật khẩu mới không thể đăng nhập.

Lựa chọn kiểu và kích thước cột theo tập profile thực tế, rồi kiểm tra round trip qua repository. Không xem một độ dài hardcode trong bài học là đủ cho mọi encoder trong tương lai. Truncation phải là lỗi được phát hiện, không phải hành vi chấp nhận ngầm.

Không dựa vào collation không phân biệt hoa thường để so khớp biểu diễn hoặc thực hiện optimistic update. Với version số, điều kiện cạnh tranh rõ ràng hơn việc dùng so sánh chuỗi theo collation mặc định; việc kiểm tra mật khẩu vẫn do encoder thực hiện.

### 10.2. Salt khác pepper

Salt là dữ liệu riêng cho mỗi lần hash, thông thường được giữ cùng biểu diễn. Pepper là bí mật bổ sung nếu thiết kế lựa chọn sử dụng, cần được quản lý bên ngoài kho credential theo một kế hoạch riêng.

Một encoder bean thông thường không chứng minh ứng dụng đã có pepper. Không tự nối một secret vào password ở riêng recovery rồi giữ login như cũ. Nếu bổ sung pepper, phải thống nhất cách biến đổi, version/key identifier, quyền truy cập secret và kế hoạch khi secret bị lộ hoặc bị mất.

Không thể giả định đổi pepper chỉ bằng cách sửa biến môi trường là mọi hash cũ vẫn kiểm tra được. Trong nhiều thiết kế, tái tạo hash với pepper mới cần mật khẩu gốc được cung cấp lại hoặc một luồng recovery phù hợp.

### 10.3. Giảm thời gian sống của raw password

Raw password chỉ nên đi qua những thành phần cần nó trong request đang xử lý. Không đặt nó trong sự kiện domain, outbox, tracing span, analytics hoặc exception message.

Java String không cho phép ứng dụng xóa nội dung tại chỗ một cách đáng tin cậy. Dùng char[] ở một lớp chưa bảo đảm các lớp JSON, framework và encoder không tạo bản sao. Mục tiêu thực tế là giảm số bản sao và thời gian giữ tham chiếu, đồng thời kiểm soát heap dump, crash report và debugger trong môi trường nhạy cảm.

## 11. Chi phí hash là một phần của chống lạm dụng recovery

[Spring Security Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html) nhấn mạnh đặc điểm tốn tài nguyên có chủ ý của các hàm password hashing thích ứng. Đối với recovery, đây vừa là bảo vệ credential vừa là chi phí mà kẻ gửi request có thể tìm cách khuếch đại.

### 11.1. Đo trong điều kiện triển khai thực tế

Đừng chọn cost chỉ bằng thời gian encode trên máy phát triển. Đo cả encode và matches trên loại instance, CPU quota, memory limit và runtime thực tế. Xem độ trễ ở tải đồng thời, không chỉ giá trị trung bình khi chạy một request.

Ví dụ giả định mỗi phép tính dùng khoảng 19 MiB bộ nhớ làm việc cho phần thuật toán và ứng dụng cho phép 50 phép chạy đồng thời. Chỉ phép nhân này đã tương ứng khoảng 950 MiB, chưa kể heap khác, cấu trúc phụ, thread stack và phần bộ nhớ của runtime. Đây là phép ước lượng để thấy quan hệ tải, không phải dự đoán chính xác RSS của implementation.

Thay đổi cost cũng tác động tới đăng nhập, đổi mật khẩu, recovery và tác vụ nâng cấp hash. Không tối ưu một endpoint riêng rồi để các endpoint khác dùng profile yếu hơn ngoài ý muốn.

### 11.2. Giới hạn lượng công việc trước khi encode

Có thể phối hợp:

- Giới hạn request ở biên, kích thước body và độ dài trường.
- Rate limit theo những chiều thích hợp như tenant, attempt, account đã giải quyết và nguồn request.
- Giới hạn số phép encode/matches chạy đồng thời trong mỗi instance và trong hệ thống.
- Queue có giới hạn nếu dùng hàng đợi nội bộ; không giữ raw password trong hàng đợi bền vững.
- Từ chối hoặc yêu cầu thử lại có kiểm soát khi hết khả năng phục vụ.

Chỉ giới hạn theo IP có thể ảnh hưởng người dùng chung NAT và vẫn bị né bởi nhiều nguồn. Chỉ giới hạn theo account có thể bị lạm dụng để gây từ chối dịch vụ cho nạn nhân. Quy tắc cần bám vào mô hình rủi ro của sản phẩm và được áp dụng trước công việc đắt tiền khi có thể.

Không phản hồi khác biệt về tài khoản tồn tại chỉ vì một nhánh chạy encode còn nhánh kia kết thúc ngay. Tuy nhiên, cố thêm nhiều phép hash đắt tiền cho mọi request không hợp lệ cũng có thể làm tăng khả năng bị DoS. Hãy thiết kế phản hồi và giới hạn công việc cùng nhau; không xem một phép dummy hash là giải pháp đầy đủ cho enumeration.

### 11.3. Lỗi tài nguyên không phải lý do ghi plaintext

Nếu encoder thiếu dependency, không thể khởi tạo provider mật mã hoặc không đủ tài nguyên, endpoint phải đi theo nhánh thất bại phù hợp. Không fallback sang plaintext, SHA-256 trực tiếp hoặc một encoder yếu hơn chỉ để người dùng hoàn tất form.

Khi encode chưa thành công, không consume grant và không thay credential. Khi lỗi xảy ra trong transaction ghi, phải rollback chuỗi thay đổi bắt buộc. Cơ chế retry không được làm token hết hạn được coi như mới phát hành.

## 12. Sau khi lưu hash: session, MFA, passkey và thông báo

### 12.1. Hash mới không tự làm mất session cũ

Một session có thể được kiểm tra bằng session ID, còn access token có thể được chấp nhận mà không đọc lại password hash. Vì vậy, đổi encoded_password không chứng minh người đang giữ session cũ đã bị loại khỏi tài khoản.

Recovery phải gọi hoặc kích hoạt cơ chế thu hồi đã được thiết kế: session store, refresh-token family, auth epoch, denylist hoặc kiểm tra trạng thái tương đương. Chỉ gọi SecurityContextHolder.clearContext() ở request hiện tại không thu hồi session trên mọi thiết bị và mọi node.

Nếu thu hồi dựa trên event bất đồng bộ, cần biết khoảng thời gian trước khi consumer xử lý event. Nếu policy yêu cầu hiệu lực ngay tại thời điểm commit, điểm chấp nhận request phải kiểm tra một trạng thái đã được cập nhật đủ sớm; chỉ có outbox chưa bảo đảm mọi session đã mất hiệu lực tức thì.

### 12.2. Giữ scope của recovery qua mọi lời gọi service

Một grant đặt lại mật khẩu không mặc nhiên cho phép:

- Xóa mọi factor MFA.
- Đăng ký passkey mới.
- Đổi email hoặc số điện thoại nhận thông báo.
- Gỡ khóa tài khoản do một quyết định quản trị riêng.
- Bỏ qua bước MFA còn được policy yêu cầu khi đăng nhập lại.

Các thay đổi đó cần scope và bằng chứng thích hợp. Hash mạnh không bù được việc một grant giới hạn bị diễn giải thành quyền quản trị mọi authenticator.

Với tài khoản chỉ dùng passkey hoặc đăng nhập liên kết, việc có một bảng password nullable không có nghĩa recovery được tự tạo thêm phương thức password login. Đó là thay đổi phương thức xác thực và phải được policy cấp quyền rõ ràng.

### 12.3. Phát thông báo theo kết quả đã commit

Một sự kiện outbox sau khi transaction thành công có thể mang tenant ID, subject ID nội bộ, loại thay đổi, event ID, timestamp và dữ liệu tối thiểu phục vụ xử lý. Không đưa mật khẩu, hash hoặc recovery token vào event.

Notification consumer cần idempotent để retry không gây gửi hàng loạt. Thông báo không được nói mật khẩu đã đổi nếu transaction còn có thể rollback. Ngược lại, lỗi gửi email sau commit không có nghĩa mật khẩu chưa đổi và không phải lý do phục hồi lại credential cũ.

Theo policy sản phẩm, người dùng có thể được yêu cầu đăng nhập lại qua cơ chế thông thường. Nếu có trải nghiệm tiếp tục sau recovery, quyền được cấp phải được thiết kế riêng; không tự tạo Authentication đầy đủ chỉ vì encode và update trả về thành công.

## 13. Các tình huống kiểm thử có ý nghĩa với tích hợp

Các đoạn và bảng dưới đây là hướng dẫn xây kiểm thử cho ứng dụng hiện thực bài học. Chúng không phải tuyên bố rằng một project cụ thể đã được chạy test.

### 13.1. Hợp đồng encoder

Ví dụ JUnit 5 dùng cùng cấu hình ở mục 4, đặt test trong package truy cập được method bean của ví dụ và bảo đảm dependency Argon2 đã sẵn sàng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordEncodingContractTest {

    private final PasswordEncoder encoder =
        new PasswordEncodingConfiguration().accountPasswordEncoder();

    @Test
    void aNewEncodingCanBeVerifiedByTheConfiguredReader() {
        String raw = "Vi-du-kiem-thu-rieng-cho-bai-hoc-2026!";

        String encoded = encoder.encode(raw);

        assertTrue(encoded.startsWith("{argon2id-recovery-v1}"));
        assertTrue(encoder.matches(raw, encoded));
        assertFalse(encoder.matches("Mot-gia-tri-khac!", encoded));
    }
}
~~~

Giá trị raw trong test là dữ liệu giả, không phải mật khẩu mẫu để cấp cho người dùng. Không khẳng định hash phải bằng một chuỗi snapshot cố định khi salt được sinh ngẫu nhiên. Test ở trên kiểm tra hợp đồng encode/matches và prefix ghi mới; nó chưa kiểm tra database, wiring Spring hoặc authorization của recovery.

### 13.2. Round trip qua đúng đường credential

Một kiểm thử tích hợp nên đi qua đường ghi credential và đọc UserDetails thật của ứng dụng:

~~~text
Tạo account test và recovery grant đúng tenant, đúng scope.
Gọi service hoàn tất recovery với mật khẩu mới.
Đọc credential vừa lưu bằng repository thật trong môi trường test.
Đọc UserDetails bằng đường mà login thực sự sử dụng.
Kiểm tra encoder của authentication provider matches mật khẩu mới.
Kiểm tra mật khẩu cũ không còn được chấp nhận theo policy.
Kiểm tra không có secret trong response hoặc event đã phát.
~~~

Kiểm tra này có thể phát hiện thiếu prefix, cắt ngắn cột, encode hai lần và UserDetailsService đọc nhầm nguồn credential. Một test chỉ mock repository rồi xác nhận save được gọi không phát hiện được những lỗi đó.

### 13.3. Biên authorization và cạnh tranh cập nhật

| Tình huống | Kết quả cần quan sát |
|---|---|
| Grant đúng nhưng chỉ có scope MFA reset | Không đổi password credential |
| Token thuộc tenant khác | Không đọc/ghi nhầm tài khoản, không lộ dữ liệu tenant khác |
| Grant hết hạn trong lúc encode | Commit bị từ chối, credential và trạng thái grant không bị cập nhật một phần |
| Hai request dùng cùng grant | Chỉ một thay đổi được commit; request còn lại không ghi đè |
| Account bị khóa bởi quản trị trước commit | Áp dụng policy mới từ trạng thái có thẩm quyền |
| Recovery đồng thời với login rehash | Rehash từ snapshot cũ không phục hồi mật khẩu cũ |
| Encoder ném lỗi trước commit | Không consume grant hoặc lưu raw password |
| Transaction lỗi sau bước cập nhật hash | Rollback cả thay đổi hash và consume grant |
| Response mất sau commit | Retry không tạo thêm một lần đổi credential trái policy |
| Node cũ đọc profile mới | Tương thích đã được kiểm tra trước khi bật writer mới |

Kiểm thử concurrency cần chủ động điều khiển điểm dừng giữa các bước bằng barrier hoặc cơ chế tương đương trong môi trường test. Chỉ chạy nhiều request ngẫu nhiên rồi không thấy lỗi chưa chứng minh cuộc đua đã được xử lý.

### 13.4. Session và đầu vào đa ngôn ngữ

Kiểm tra session tồn tại trước recovery trên ít nhất những đường truy cập mà policy yêu cầu thu hồi; đừng chỉ kiểm tra session của browser đang chạy form recovery.

Với mật khẩu, đưa vào bộ test các ký tự tiếng Việt, ký tự ngoài BMP, dấu cách ở đầu/cuối và giới hạn byte nếu encoder có giới hạn đó. Kỳ vọng phải theo policy đã công bố; không sửa kỳ vọng bằng cách trim dữ liệu test cho test chạy qua.

## 14. Dấu hiệu lỗi và hướng kiểm tra

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Recovery thành công nhưng mật khẩu mới luôn sai | Encode hai lần, mapper sửa dữ liệu, cột bị cắt, login đọc sai kho |
| Login báo không có encoder cho ID | Prefix thiếu/sai, reader chưa triển khai, mapping khác giữa các node |
| Login lúc được lúc không sau deploy | Rolling deployment chưa tương thích, cache hoặc replica credential cũ |
| Mật khẩu cũ dùng lại được sau recovery | Rehash ghi đè, cache chưa vô hiệu hóa, login in-flight dùng snapshot cũ |
| Mật khẩu mới đúng nhưng session cũ vẫn hoạt động | Cơ chế thu hồi session chưa được gọi hoặc chưa có hiệu lực |
| Recovery làm tăng CPU/RAM đột biến | Concurrency hash không giới hạn, cost chưa đo, encode trước admission |
| MFA bị mất sau password recovery | Lỗi scope/policy ở service thay authenticator, không phải lỗi encoder |
| Mật khẩu có dấu hoặc emoji không nhất quán | Chuẩn hóa khác nhau, giới hạn ký tự/byte bị nhầm, frontend cắt dữ liệu |

Để điều tra, dùng correlation ID, event ID và các mã lỗi hữu hạn. Có thể đo encode latency, số lần xung đột version, lỗi định dạng và độ trễ thu hồi session. Không dùng password, hash hoặc token làm metric label, log field hay dữ liệu tìm kiếm.

Các ví dụ quan sát được chỉ là điểm bắt đầu điều tra. Kết luận nguyên nhân cần dựa trên wiring, dữ liệu và thứ tự sự kiện thực tế; không bỏ prefix hoặc hạ cost chỉ vì muốn loại bỏ triệu chứng nhanh.

## 15. Một kịch bản xuyên suốt

Giả sử tài khoản ở tenant T có password credential version 41, một session cũ và một yếu tố MFA vẫn còn hoạt động. Người dùng được cấp grant chỉ cho phép PASSWORD_REPLACE sau khi hoàn tất quy trình recovery.

Service xác minh grant và kiểm tra mật khẩu mới. Encoder chung tạo biểu diễn mang profile hiện tại. Trong lúc encode, một request login khác có thể đang kiểm tra mật khẩu cũ; chưa thành phần nào được suy rằng account đã hoàn tất recovery.

Transaction hoàn tất recovery đọc lại grant, account và version. Nếu còn hợp lệ, nó ghi hash mới, tăng version, consume grant và cập nhật trạng thái phục vụ thu hồi theo policy. Event không chứa secret được commit cùng dữ liệu.

Nếu request login cũ cố ghi một hash nâng cấp dựa trên version 41, cập nhật có điều kiện phải thất bại. Nếu login đó cố tạo session, cơ chế cấp và kiểm tra quyền truy cập phải xử lý trạng thái bảo mật mới theo policy đã thiết kế.

Lần đăng nhập tiếp theo sử dụng mật khẩu mới được provider kiểm tra bằng encoder tương thích. Yếu tố MFA còn hoạt động tiếp tục được yêu cầu nếu policy nói như vậy. Thông báo đổi mật khẩu được gửi theo event đã commit; nó không chứa mật khẩu và không cấp quyền reset MFA.

Kịch bản này cho thấy tích hợp PasswordEncoder thành công không chỉ là gọi encode trước save. Kết quả cần đạt là biểu diễn credential đọc được bởi đường đăng nhập, được ghi bởi một thao tác recovery hợp lệ, chịu kiểm soát cạnh tranh và phối hợp đúng với trạng thái quyền truy cập của tài khoản.
