# Liên kết danh tính (Identity Federation) là gì và giải quyết vấn đề nào?

**Liên kết danh tính (identity federation)** là mô hình trong đó một ứng dụng hoặc dịch vụ tin cậy kết quả xác thực do một **nhà cung cấp danh tính (Identity Provider – IdP)** đưa ra, thay vì tự kiểm tra mật khẩu, passkey hoặc yếu tố xác thực của người dùng. IdP và ứng dụng có quan hệ tin cậy được thiết lập trước; kết quả đăng nhập được chuyển qua một giao thức liên kết tiêu chuẩn, rồi ứng dụng kiểm tra tính hợp lệ và tạo phiên làm việc của riêng mình.

**Ý chính:** Người dùng chứng minh danh tính với IdP; ứng dụng nhận và kiểm chứng bằng chứng xác thực để biết *ai đang đăng nhập*, sau đó **tự quyết định người đó được làm gì**. Federation giúp nhiều hệ thống có thể dùng chung một nguồn danh tính mà không cần chia sẻ mật khẩu giữa các hệ thống.

## 1. Vì sao cần identity federation?

Giả sử một doanh nghiệp dùng ba ứng dụng độc lập: cổng nhân sự, hệ thống hỗ trợ khách hàng và ứng dụng quản lý dự án. Nếu mỗi ứng dụng tự lưu tài khoản và mật khẩu thì cùng một nhân viên phải có nhiều danh tính đăng nhập. Khi doanh nghiệp hợp tác với đối tác bên ngoài, việc cấp thêm tài khoản ở từng ứng dụng còn phức tạp hơn.

Mô hình đăng nhập riêng lẻ thường gây ra những vấn đề sau:

1. **Phân mảnh danh tính:** cùng một người được biểu diễn bằng nhiều tài khoản, mật khẩu, thuộc tính và quy trình khôi phục khác nhau; dễ nhầm lẫn khi đối chiếu người dùng giữa các hệ thống.
2. **Chi phí quản trị cao:** cấp mới, khóa và thu hồi quyền truy cập phải phối hợp qua nhiều ứng dụng; dễ sót tài khoản khi nhân viên nghỉ việc hoặc đối tác kết thúc hợp đồng.
3. **Chính sách xác thực không đồng đều:** một ứng dụng bắt buộc MFA, ứng dụng khác vẫn dùng mật khẩu yếu; mỗi nhóm phát triển phải tự vận hành luồng đăng nhập và các biện pháp bảo vệ.
4. **Trải nghiệm rời rạc:** người dùng phải đăng nhập nhiều lần và nhớ nhiều thông tin, làm tăng yêu cầu hỗ trợ đăng nhập.
5. **Khó cộng tác giữa tổ chức:** ứng dụng của doanh nghiệp A khó tin cậy tài khoản được doanh nghiệp B xác thực nếu không có cơ chế liên kết tiêu chuẩn.

Federation xử lý phần lõi của các vấn đề này bằng cách **tách vai trò xác thực danh tính khỏi vai trò cung cấp chức năng nghiệp vụ**. Ứng dụng tập trung vào nghiệp vụ và phân quyền; IdP tập trung vào tài khoản, quy trình xác thực và thông tin danh tính cần chia sẻ.

## 2. Các thành phần và quan hệ tin cậy

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **User / Subject** | Người cần truy cập dịch vụ và chứng minh danh tính | Nhân viên, khách hàng, đối tác |
| **Identity Provider (IdP)** | Xác thực người dùng, phát hành thông tin hoặc bằng chứng về sự kiện xác thực | Hệ thống danh tính doanh nghiệp |
| **Relying Party (RP) / Service Provider (SP)** | Ứng dụng dựa vào bằng chứng từ IdP, kiểm chứng và phục vụ người dùng | Cổng nhân sự, ứng dụng Spring Boot |
| **Assertion / Identity token** | Thông điệp có thể kiểm chứng về người dùng và ngữ cảnh xác thực | SAML assertion hoặc OIDC ID token |
| **Trust configuration** | Cấu hình xác định IdP nào được tin, khóa/chứng thư dùng để kiểm tra, bên nhận hợp lệ và điểm kết nối | Issuer, client registration, metadata, chứng thư ký |

Trong OpenID Connect (OIDC), ứng dụng thường gọi là **Relying Party**; trong SAML 2.0, thường gọi là **Service Provider**. Ở cả hai, ứng dụng **không được tin một lời tuyên bố chỉ vì nó có vẻ là token hoặc đến từ trình duyệt**: phải kiểm chứng bằng chứng theo giao thức và cấu hình tin cậy.

Quan hệ tin cậy có thể trải qua ranh giới tổ chức: doanh nghiệp A chấp nhận kết quả xác thực từ IdP của đối tác B. Một RP cũng có thể tin nhiều IdP, nhưng cần quy tắc rõ ràng để nhận diện và ánh xạ đúng từng người.

## 3. Luồng đăng nhập liên kết hoạt động như thế nào?

Ví dụ người dùng muốn vào một ứng dụng Spring Boot dùng IdP doanh nghiệp:

~~~text
Người dùng ──(1) truy cập──> Ứng dụng / RP
                                |
                                | (2) yêu cầu đăng nhập liên kết
                                v
                           IdP đã cấu hình
                                |
                         (3) xác thực người dùng
                         (mật khẩu/MFA/passkey...)
                                |
                                v
                        Kết quả qua giao thức
                                |
                                v
Ứng dụng / RP <──(4) nhận và kiểm chứng bằng chứng
       |
       +──(5) xác định tài khoản, kiểm tra quyền
       |
       +──(6) tạo phiên ứng dụng và trả nội dung
~~~

1. **Bắt đầu tại RP:** người dùng truy cập tài nguyên yêu cầu đăng nhập. RP biết IdP được phép dùng và thông số đăng ký ứng dụng.
2. **Chuyển đến IdP:** RP khởi động luồng liên kết. Trình duyệt có thể chuyển hướng tới IdP; yêu cầu bao gồm dữ liệu dùng để liên hệ đúng lần đăng nhập và đúng ứng dụng.
3. **IdP xác thực:** IdP kiểm tra yếu tố xác thực theo chính sách của mình. Nếu người dùng đã có phiên hợp lệ tại IdP, bước này có thể không cần nhập lại mật khẩu.
4. **Trao kết quả:** với **OIDC Authorization Code Flow**, trình duyệt quay về RP cùng authorization code; RP đổi code qua kết nối máy chủ đến IdP để lấy token, trong đó có **ID token**. Với **SAML 2.0 Web Browser SSO**, RP nhận và xử lý **SAML response/assertion** theo binding đã cấu hình. Hai giao thức có hình thức trao đổi khác nhau.
5. **RP kiểm chứng:** kiểm tra chữ ký, issuer, đối tượng nhận (audience/recipient), hiệu lực thời gian, tính gắn kết với yêu cầu ban đầu và các điều kiện chống giả mạo/phát lại tương ứng từng giao thức. RP xác định người dùng từ định danh đã xác thực, rồi áp dụng quy tắc tài khoản và phân quyền nội bộ.
6. **RP tạo phiên:** sau khi đăng nhập thành công, RP quản lý phiên hoặc ngữ cảnh bảo mật của chính ứng dụng. Phiên tại IdP và phiên tại RP là hai đối tượng khác nhau.

**Điểm dễ nhầm:** IdP xác thực người dùng, nhưng ứng dụng không đơn giản “nhận mọi token rồi cho vào”. Không có bước kiểm chứng và ánh xạ danh tính đúng thì federation không an toàn.

## 4. Identity federation giải quyết được những bài toán cụ thể nào?

| Bài toán | Federation giúp gì? | Ranh giới cần hiểu |
| --- | --- | --- |
| Mỗi ứng dụng có tài khoản/mật khẩu riêng | Ứng dụng tin kết quả xác thực từ một hoặc nhiều IdP được cấu hình | Ứng dụng vẫn có thể cần hồ sơ người dùng nội bộ |
| Người dùng phải đăng nhập lặp lại | Có thể tạo trải nghiệm **Single Sign-On (SSO)** qua phiên hiện có tại IdP | Federation không tự bảo đảm SSO nếu chính sách IdP yêu cầu xác thực lại |
| Chính sách đăng nhập thiếu thống nhất | Cho phép tập trung MFA, chính sách xác thực, quy trình khôi phục tại IdP | RP phải chọn IdP phù hợp và có thể cần kiểm tra mức bảo đảm xác thực |
| Đối tác cần dùng ứng dụng của doanh nghiệp | Thiết lập tin cậy với IdP phía đối tác thay vì phát hành mật khẩu riêng cho mọi người | Vẫn cần quản lý hợp đồng, phạm vi tin cậy và quyền vào ứng dụng |
| Tích hợp người dùng từ nhiều hệ thống | Chuẩn hóa cách nhận định danh và thuộc tính cần thiết | Không tự đồng bộ hồ sơ, nhóm hoặc vòng đời tài khoản |
| Mỗi nhóm phát triển tự viết luồng đăng nhập | Có thể dùng thư viện/protocol phổ biến với cơ chế kiểm chứng được chuẩn hóa | Phải cấu hình đúng issuer, keys, redirect, session và phân quyền |

**Ví dụ trước và sau:**

- *Trước:* Nhân viên đăng nhập ba ứng dụng bằng ba tài khoản. Khi nhân viên nghỉ việc, bộ phận vận hành phải vô hiệu hóa từng tài khoản, dễ bỏ sót.
- *Sau:* Cả ba ứng dụng dựa trên IdP doanh nghiệp. Khóa khả năng đăng nhập tại IdP giúp ngăn các lần đăng nhập liên kết mới theo chính sách IdP; các ứng dụng vẫn cần cơ chế quản lý **phiên đã cấp**, quyền nội bộ và quy trình thu hồi/provisioning thích hợp.

Federation làm giảm việc nhân bản xác thực. Nó **không đồng nghĩa với việc mọi phiên và mọi quyền truy cập biến mất tức thì** khi một tài khoản bị khóa.

## 5. Phân biệt các khái niệm liên quan

### Federation khác Single Sign-On (SSO)

- **Federation** là cơ chế và quan hệ tin cậy để một hệ thống chấp nhận bằng chứng xác thực từ hệ thống danh tính khác.
- **SSO** là trải nghiệm đăng nhập một lần rồi truy cập nhiều ứng dụng mà không phải xác thực lại ở mỗi ứng dụng, khi các phiên và chính sách cho phép.

Federation thường được dùng để hiện thực SSO giữa nhiều ứng dụng hoặc tổ chức. Tuy nhiên, SSO cũng có thể tồn tại trong một hệ thống cùng miền quản trị, và một luồng federation vẫn có thể yêu cầu MFA hoặc đăng nhập lại.

### Authentication khác Authorization

- **Authentication (xác thực):** người dùng là ai và bằng chứng đăng nhập có hợp lệ không?
- **Authorization (phân quyền):** người dùng được đọc, sửa, phê duyệt hay quản trị tài nguyên nào?

Ví dụ IdP chứng minh người dùng có định danh hợp lệ. Ứng dụng Spring Boot vẫn phải xác định người đó có quyền duyệt đơn hàng hay chỉ được xem. Claim hoặc nhóm từ IdP **không tự động trở thành quyền cao trong ứng dụng**; cần ánh xạ và kiểm soát theo chính sách.

### Federation khác OAuth 2.0, OpenID Connect và SAML 2.0

| Khái niệm | Mục đích trọng tâm | Liên hệ với federation |
| --- | --- | --- |
| **OAuth 2.0** | Ủy quyền cho client truy cập tài nguyên/API theo phạm vi cho phép | Bản thân OAuth 2.0 không phải giao thức chứng minh danh tính người dùng |
| **OpenID Connect (OIDC)** | Lớp xác thực dựa trên OAuth 2.0, có **ID token** và các quy tắc nhận diện người dùng | Thường dùng cho federation và đăng nhập ứng dụng web/mobile |
| **SAML 2.0** | Trao đổi assertion về xác thực/thuộc tính, thường dùng XML và chữ ký số | Phổ biến trong SSO và federation doanh nghiệp |
| **Identity federation** | Mô hình tin cậy danh tính giữa các bên | Có thể triển khai bằng OIDC, SAML hoặc cơ chế phù hợp khác |

**ID token** của OIDC được thiết kế để RP xác minh kết quả xác thực. **Access token** chủ yếu phục vụ truy cập tài nguyên được ủy quyền; không được dùng như một ID token tùy tiện. Một số nhà cung cấp hỗ trợ “social login” theo OAuth 2.0 kết hợp truy xuất thông tin người dùng, nhưng cách đó không biến mọi access token thành bằng chứng đăng nhập theo chuẩn OIDC.

## 6. Ba tình huống thực tế

**Tình huống A – SSO nội bộ:** Công ty có HR, Jira-like tracker và cổng báo cáo, cùng tin IdP của công ty. Nhân viên được yêu cầu MFA ở IdP, sau đó vào các ứng dụng theo phiên và chính sách tương ứng. Mỗi ứng dụng vẫn có role khác nhau.

**Tình huống B – Đối tác B2B:** Công ty cung cấp một cổng giao dịch cho đối tác. Thay vì giữ mật khẩu của nhân viên đối tác, cổng cho phép đăng nhập qua IdP của đối tác đã ký kết quan hệ tin cậy. Ứng dụng kiểm tra issuer và điều kiện nhận, ánh xạ người dùng vào đúng tổ chức đối tác, rồi áp dụng quyền dành cho tổ chức đó.

**Tình huống C – Nhiều IdP:** Một sản phẩm hỗ trợ nhân viên đăng nhập bằng IdP doanh nghiệp và khách hàng đăng nhập bằng IdP khách hàng. Hai người có cùng email hiển thị chưa chắc là một danh tính. Tài khoản liên kết phải dựa trên định danh bền vững có ngữ cảnh IdP (chẳng hạn cặp **issuer + subject** với OIDC) và quy trình linking được xác minh.

Các tình huống này cho thấy giá trị của federation nằm ở **việc chuyển trách nhiệm xác thực theo ranh giới tin cậy rõ ràng**; dữ liệu nghiệp vụ và quyết định phân quyền vẫn ở phía ứng dụng.

## 7. Identity federation liên quan thế nào tới Spring Security?

Trong ứng dụng Java/Spring Boot, Spring Security cung cấp các thành phần để ứng dụng hành động như bên nhận kết quả xác thực:

- **OIDC/OAuth2 Login:** tính năng **oauth2Login** của Spring Security giúp ứng dụng servlet đăng nhập qua nhà cung cấp OIDC hoặc nhà cung cấp OAuth 2.0 có luồng đăng nhập được hỗ trợ. Với OIDC, ứng dụng thường là **Relying Party** và cấu hình **ClientRegistration**, issuer, client credentials, redirect URI.
- **SAML 2.0 Login:** tính năng **saml2Login** cho phép ứng dụng servlet đóng vai trò **Service Provider/Relying Party**, dựa vào assertion của SAML IdP/Asserting Party, với cấu hình registration, metadata và thông tin xác minh chữ ký.
- **OAuth2 Resource Server:** dùng khi API kiểm chứng **access token** từ một authorization server để bảo vệ tài nguyên. Đây là vai trò API nhận token, **khác** với luồng trình duyệt đăng nhập người dùng của **oauth2Login**.
- **Authorization trong ứng dụng:** Spring Security có thể dựa vào principal/authorities sau đăng nhập để bảo vệ URL và method. Cần thiết kế ánh xạ claims/groups sang authorities theo quyền nghiệp vụ thực tế.

Ví dụ tối thiểu về *phần cấu hình bảo vệ URL và bật OIDC login* trong một ứng dụng **Spring Boot servlet** có Spring Security và dependency **spring-boot-starter-oauth2-client**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **một class cấu hình trong dự án Spring Boot**, không phải chương trình Java độc lập chạy bằng lệnh **javac/java** và không có stdout cố định. Để đăng nhập hoạt động, dự án còn cần ít nhất một đăng ký OIDC client hợp lệ với IdP (issuer, client ID, thông tin bí mật khi cần, callback/redirect khớp đăng ký). Thông tin bí mật phải được quản lý an toàn thay vì nhúng vào mã nguồn. Khi người dùng vào URL được bảo vệ, Spring Security khởi động luồng đăng nhập và xử lý callback theo cấu hình.

**Vì sao ví dụ này thể hiện federation?** Class không triển khai hàm kiểm tra mật khẩu người dùng. Công việc xác thực được giao cho IdP; Spring Security xử lý giao thức và tạo ngữ cảnh xác thực cho ứng dụng. Quyền truy cập ứng dụng vẫn được cấu hình riêng bằng các quy tắc authorization.

## 8. Điều kiện tin cậy và giới hạn an toàn

Federation giúp tập trung xác thực nhưng cũng tạo phụ thuộc vào IdP và cấu hình tin cậy. Một thiết kế đúng cần chú ý:

1. **Xác minh bằng chứng thật sự:** chỉ chấp nhận issuer được phép, kiểm tra chữ ký bằng khóa/chứng thư tin cậy, đối tượng nhận và thời gian hiệu lực. Với OIDC cần quan tâm **state**, **nonce** (khi áp dụng), PKCE và luồng code; với SAML kiểm tra các điều kiện như **Destination**, **Recipient**, **InResponseTo** và chống phát lại theo profile/binding tương ứng. Không tự viết logic bỏ qua các kiểm tra của thư viện.
2. **Bảo vệ kênh và cấu hình callback:** dùng HTTPS, đăng ký redirect URI chính xác, bảo vệ phiên/cookie và không tiết lộ token hoặc client secret trong log.
3. **Định danh bền vững:** ưu tiên cặp **issuer + subject** hoặc định danh federation theo chính sách; không tự ghép tài khoản chỉ vì địa chỉ email giống nhau hoặc có thể thay đổi. Tránh nhận token từ tenant/issuer ngoài danh sách tin cậy.
4. **Phân quyền tối thiểu:** người dùng đăng nhập thành công chưa đồng nghĩa được làm quản trị viên. Role và nhóm từ IdP chỉ có ý nghĩa khi được kiểm chứng và ánh xạ có chủ đích trong ứng dụng.
5. **Quản lý vòng đời:** provisioning/deprovisioning tài khoản, cập nhật thuộc tính, thu hồi phiên, logout một ứng dụng và Single Logout là các vấn đề riêng. Federation không tự giải quyết tất cả.
6. **Phụ thuộc và giới hạn tin cậy:** IdP gặp sự cố có thể chặn đăng nhập mới; IdP bị xâm nhập có thể ảnh hưởng nhiều RP. Cần đánh giá độ tin cậy, vận hành khóa ký/xoay khóa và kế hoạch xử lý sự cố.
7. **Quyền riêng tư:** chỉ yêu cầu và lưu các thuộc tính danh tính cần cho mục đích nghiệp vụ; xác định trách nhiệm chia sẻ dữ liệu giữa các tổ chức.

**Lỗi phổ biến:** coi “đăng nhập được qua IdP” là “có mọi quyền”; nhầm access token với ID token; tin email làm khóa định danh duy nhất; chấp nhận issuer không đúng; bỏ kiểm tra audience/chữ ký; nghĩ rằng khóa tài khoản ở IdP luôn chấm dứt tức thì mọi phiên đang mở tại RP.

## 9. Cách kiểm tra xem đã hiểu đúng

- **Câu hỏi 1:** Ứng dụng A chấp nhận ID token hợp lệ từ IdP B. Ai đã kiểm chứng mật khẩu hoặc passkey của người dùng? **IdP B**; A kiểm chứng bằng chứng và quyết định cấp phiên.
- **Câu hỏi 2:** Đăng nhập thành công vào ứng dụng A bằng IdP chung có tự cấp quyền quản trị ứng dụng A không? **Không**; A phải kiểm tra authorization của chính mình.
- **Câu hỏi 3:** Dùng chung IdP có bảo đảm khi khóa tài khoản thì mọi phiên của các ứng dụng biến mất ngay không? **Không**; cần cơ chế quản lý và thu hồi phiên phù hợp.
- **Câu hỏi 4:** OAuth 2.0 access token có mặc nhiên là chứng cứ xác thực chuẩn OIDC không? **Không**; OIDC quy định ID token và các bước kiểm chứng riêng.

## 10. Ghi nhớ và đọc thêm

Identity federation trả lời câu hỏi: **“Làm sao ứng dụng tin được danh tính đã được một bên khác xác thực, theo một giao thức và quan hệ tin cậy kiểm chứng được?”** Nó giúp giảm tài khoản và luồng xác thực phân tán, hỗ trợ SSO và cộng tác giữa tổ chức, nhưng không thay thế phân quyền, quản lý vòng đời tài khoản hoặc bảo mật phiên ứng dụng.

Tài liệu tham khảo chính thức:

- NIST SP 800-63C-4 – Federation and Assertions: https://pages.nist.gov/800-63-4/sp800-63c.html
- Spring Security – OAuth2 Login (servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security – SAML 2.0 Login (servlet): https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html
