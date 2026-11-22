# AuthnStatement, AuthnContext và thời điểm xác thực trong SAML 2.0

**AuthnStatement** là thành phần của SAML 2.0 Assertion mô tả *một sự kiện xác thực danh tính*: bên cung cấp danh tính (Identity Provider, IdP) đã xác thực chủ thể vào **thời điểm nào** và trong **ngữ cảnh xác thực** nào. Hai thông tin cốt lõi là **AuthnInstant** (thời điểm xác thực thực tế) và **AuthnContext** (bối cảnh/phương thức xác thực do IdP công bố).

Trong bài toán **Spring Security – federation**, ứng dụng đóng vai trò **Service Provider/Relying Party (SP/RP)**. SP xác minh SAML Response/Assertion từ IdP và có thể dùng AuthnStatement để hiểu mức độ mới của sự kiện xác thực, yêu cầu phương thức xác thực phù hợp và thiết kế các thao tác nhạy cảm cần xác thực lại. Một AuthnStatement hợp lệ **không tự đồng nghĩa** mọi quyền truy cập đều được cấp, một phiên ứng dụng phải tồn tại đến thời điểm nào, hoặc người dùng vừa nhập mật khẩu ngay lúc Response được gửi đến.

## 1. AuthnStatement nằm ở đâu trong mô hình SAML 2.0?

Luồng Web Browser SSO thông thường:

~~~text
Người dùng  --->  Spring Security SP/RP
                       |
                       | 1. SAML AuthnRequest
                       v
                  IdP xác thực
                       |
                       | 2. SAML Response chứa Assertion
                       v
               SP kiểm chứng Response/Assertion
                       |
                       | 3. Đọc thông tin xác thực đáng tin cậy
                       v
               Principal + phiên ứng dụng + authorization
~~~

SAML 2.0 Assertion có thể chứa các loại statement khác nhau:

- **AuthnStatement:** xác thực danh tính khi nào và theo ngữ cảnh nào.
- **AttributeStatement:** thông tin về chủ thể như email, bộ phận, nhóm; **không** thay thế AuthnStatement.
- **AuthzDecisionStatement:** phát biểu về quyết định ủy quyền trong một ngữ cảnh cụ thể; ứng dụng vẫn chịu trách nhiệm áp dụng chính sách hiện hành của mình.

Trong Web Browser SSO, SP thường nhận SAML Response qua **Assertion Consumer Service (ACS)**, kiểm tra nguồn phát hành, chữ ký, audience, recipient, thời hạn và các ràng buộc với yêu cầu đăng nhập. Chỉ **sau khi đã kiểm chứng tính hợp lệ và ngữ cảnh tin cậy của assertion**, ứng dụng mới có thể dựa vào các trường bên trong AuthnStatement để đưa ra quyết định.

**Điểm phân biệt:** SAML Response và Assertion là các lớp bao; AuthnStatement là một phần bên trong Assertion. Có thể có nhiều AuthnStatement tùy nội dung/protocol, nên nếu nghiệp vụ dựa vào độ mới hoặc phương thức xác thực, phải xác định rõ statement nào được chấp nhận theo chính sách.

## 2. Cấu trúc của AuthnStatement

Một đoạn XML minh họa **riêng thành phần AuthnStatement**:

~~~xml
<saml:AuthnStatement
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    AuthnInstant="2026-11-07T08:00:00Z"
    SessionIndex="_idp-session-123"
    SessionNotOnOrAfter="2026-11-07T16:00:00Z">

    <saml:AuthnContext>
        <saml:AuthnContextClassRef>
            urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
    </saml:AuthnContext>
</saml:AuthnStatement>
~~~

Đây là **mảnh minh họa cấu trúc**, không phải SAML Assertion/Response đầy đủ và không có chữ ký số. Không dùng mảnh XML này làm bằng chứng đăng nhập thực tế. Giá trị URI trong AuthnContextClassRef phải tuân theo cách biểu diễn chính xác mà IdP hỗ trợ; XML ở ví dụ được xuống dòng để dễ đọc.

Theo **SAML 2.0 Core**, thành phần có các phần chính:

| Thành phần | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| **AuthnInstant** | Có | Mốc thời gian tại đó sự kiện xác thực diễn ra, định dạng thời gian XML Schema, mã hóa theo UTC trong SAML |
| **AuthnContext** | Có | Thông tin ngữ cảnh mà IdP dùng để xác thực chủ thể |
| **SessionIndex** | Không | Định danh/chỉ mục một phiên giữa subject và authentication authority; thường hữu ích cho việc tham chiếu phiên, ví dụ Single Logout |
| **SessionNotOnOrAfter** | Không | Thời điểm phiên xác thực giữa subject và SAML authority phải được coi là kết thúc |
| **SubjectLocality** | Không | Thông tin như địa chỉ IP hoặc DNS name của thiết bị nơi sự kiện xác thực được cho là diễn ra; không nên mặc nhiên coi là nguồn xác định địa lý đáng tin |

Trong **AuthnContext**, chuẩn hỗ trợ thông tin như **AuthnContextClassRef**, **AuthnContextDecl**, **AuthnContextDeclRef** và **AuthenticatingAuthority** theo cấu trúc cho phép. Ngữ cảnh có thể được biểu diễn bằng class reference, một declaration chi tiết, declaration reference hoặc kết hợp hợp lệ của chúng. Không phải IdP nào cũng phát đầy đủ những phần tùy chọn này.

### Trường dữ liệu quan trọng cần ghi nhớ

- **AuthnInstant** là thuộc tính của chính **AuthnStatement**, không phải thời gian hiện tại của trình duyệt.
- **SessionIndex** là định danh theo ngữ cảnh IdP/SAML authority. Không tự lấy nó thay cho session ID của HttpSession trong Spring.
- **SessionNotOnOrAfter** nói về **phiên với SAML authority**; không có quan hệ bắt buộc với **Conditions.NotOnOrAfter** của assertion.
- **AuthnContext** mô tả *đã xác thực như thế nào*; nó không chứa mặc định toàn bộ quyền nghiệp vụ của người dùng.

## 3. AuthnInstant chính xác là thời điểm nào?

**AuthnInstant** bắt buộc trên mỗi AuthnStatement và thể hiện **thời điểm xác thực đã diễn ra ở hệ thống cung cấp danh tính**. Đây là thuộc tính quan trọng nếu ứng dụng muốn biết xác thực có đủ mới cho một hành động nhạy cảm không.

Ví dụ về dòng thời gian theo UTC:

| Mốc thời gian | Sự kiện | Thuộc tính/đối tượng |
| --- | --- | --- |
| 08:00:00Z | Người dùng đăng nhập vào IdP; IdP xác thực thành công | **AuthnInstant = 08:00:00Z** |
| 09:10:00Z | Người dùng mở Portal; IdP tái dùng phiên SSO đang tồn tại và phát SAML assertion mới | **Assertion.IssueInstant = 09:10:00Z** |
| 09:15:00Z | Assertion hết hạn sử dụng theo Conditions | **Conditions.NotOnOrAfter = 09:15:00Z** |
| 16:00:00Z | Phiên giữa subject và IdP phải được coi là kết thúc theo statement | **SessionNotOnOrAfter = 16:00:00Z** |

**Hệ quả:** ở **09:12Z**, assertion có thể vẫn nằm trong khoảng hiệu lực và được SP chấp nhận để đăng nhập, nhưng **sự kiện xác thực gốc đã xảy ra 72 phút trước**. Nếu thao tác duyệt chuyển khoản yêu cầu người dùng vừa xác thực trong **10 phút gần nhất**, dùng **IssueInstant = 09:10** để kết luận “mới 2 phút” là **sai**. Phải xem **AuthnInstant = 08:00**, áp dụng chính sách độ mới và yêu cầu xác thực lại nếu cần.

Một IdP có thể xác thực lại thực sự và phát statement mới với AuthnInstant mới. Nhưng việc phát **Response mới**, gia hạn **SP session** hoặc có **trình duyệt được redirect qua IdP** không đủ chứng minh IdP đã thực hiện một sự kiện xác thực mới.

## 4. Phân biệt mọi mốc thời gian thường xuất hiện trong SAML

| Trường/khái niệm | Thuộc về | Trả lời câu hỏi |
| --- | --- | --- |
| **Response.IssueInstant** | SAML Response | Response này được phát hành khi nào? |
| **Assertion.IssueInstant** | SAML Assertion | Assertion này được phát hành khi nào? |
| **AuthnStatement.AuthnInstant** | Authentication statement | IdP xác thực người dùng vào thời điểm nào? |
| **Conditions.NotBefore** | Assertion conditions | Assertion chưa thể được sử dụng trước khi nào? |
| **Conditions.NotOnOrAfter** | Assertion conditions | Assertion phải bị coi là hết hiệu lực vào thời điểm nào? |
| **SubjectConfirmationData.NotOnOrAfter** | Subject confirmation | Bằng chứng xác nhận subject phải bị từ chối sau mốc nào trong ngữ cảnh xác nhận đó? |
| **AuthnStatement.SessionNotOnOrAfter** | Phiên subject–SAML authority | Phiên xác thực phía SAML authority kết thúc chậm nhất khi nào? |
| **Session timeout của ứng dụng Spring** | Phiên web tại SP | Phiên ứng dụng do SP quản lý hết hạn khi nào? |

Những thời điểm này **không hoán đổi cho nhau**:

1. **Assertion còn hiệu lực** chưa có nghĩa **lần xác thực đủ mới** cho step-up.
2. **AuthnInstant mới** chưa có nghĩa **assertion đang hợp lệ** nếu chữ ký, audience, recipient hoặc thời gian hiệu lực assertion sai.
3. **SessionNotOnOrAfter của IdP** không phải một chỉ thị tự động đặt thời hạn HttpSession của ứng dụng Spring.
4. **SessionIndex** có thể hỗ trợ tham chiếu phiên khi Single Logout được triển khai đúng, nhưng không có nghĩa logout tại IdP tự động kết thúc mọi phiên SP ngay lập tức.

SAML mô tả thời gian theo chuẩn UTC; ví dụ **Z** thể hiện UTC. Khi đọc hoặc so sánh ở Java, ưu tiên **Instant** thay vì LocalDateTime không kèm múi giờ. Cho phép độ lệch đồng hồ (**clock skew**) trong các kiểm tra do thư viện và chính sách bảo mật quy định; không tự bỏ toàn bộ kiểm tra thời gian vì máy chủ có thể lệch đồng hồ.

## 5. AuthnContext cho biết điều gì?

**AuthnContext** là mô tả **ngữ cảnh, phương thức hoặc mức bảo đảm của sự kiện xác thực** như IdP công bố. Một phần thường gặp là **AuthnContextClassRef** chứa URI tham chiếu đến lớp ngữ cảnh xác thực.

Ví dụ một số URI chuẩn SAML:

- **urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport**: bối cảnh xác thực bằng mật khẩu qua kênh truyền có bảo vệ.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:Password**: lớp ngữ cảnh xác thực bằng mật khẩu.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken**: lớp ngữ cảnh dựa trên token đồng bộ thời gian.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:SmartcardPKI**: lớp ngữ cảnh dùng smart card và PKI.
- **urn:oasis:names:tc:SAML:2.0:ac:classes:PreviousSession**: lớp ngữ cảnh liên quan việc dựa trên phiên xác thực trước đó.

**Không suy luận máy móc:** URI **PasswordProtectedTransport** không khẳng định người dùng đã hoàn thành MFA. URI **TimeSyncToken** không tự chứng minh ứng dụng đạt một mức NIST AAL cụ thể. Cũng không nên tự xếp tất cả class URI thành thang đo mạnh–yếu nếu IdP và SP chưa thống nhất ý nghĩa.

Một IdP có thể dùng **URI riêng** để biểu diễn chính sách MFA, passkey, phishing-resistant authentication hoặc assurance level. SP chỉ dựa vào URI đó khi đã có hợp đồng tin cậy với IdP: URI nghĩa là gì, phương thức thực tế nào đứng sau, có thể bị thay đổi khi nào, có cần bắt buộc tái xác thực không.

### AuthnContextClassRef, DeclRef và AuthenticatingAuthority

- **AuthnContextClassRef:** URI nhận diện *lớp* ngữ cảnh xác thực. Đây là cách mô tả cô đọng và thường gặp.
- **AuthnContextDecl / AuthnContextDeclRef:** khai báo chi tiết hoặc URI tham chiếu tới khai báo về ngữ cảnh xác thực; giúp diễn đạt chính sách, quy trình kỹ thuật sâu hơn một class name.
- **AuthenticatingAuthority:** có thể chỉ ra một hoặc nhiều authority tham gia xác thực; hữu ích khi có ủy thác xác thực theo nhiều tầng, nhưng bản thân tên authority không thay bước kiểm chứng tin cậy.

Điều cần làm ở SP là **đối chiếu ngữ cảnh được báo với chính sách ứng dụng**, không tự coi mọi AuthnContext đều tương đương.

## 6. RequestedAuthnContext và ForceAuthn: yêu cầu trước, xác minh sau

Có sự khác biệt giữa điều ứng dụng **yêu cầu IdP làm** và điều assertion **thực sự cho biết IdP đã làm**.

### RequestedAuthnContext

Trong SAML **AuthnRequest**, SP có thể gửi **RequestedAuthnContext** để yêu cầu một hoặc nhiều class/declaration ngữ cảnh xác thực. Thuộc tính **Comparison** có các giá trị theo SAML 2.0:

| Comparison | Ý nghĩa ở mức giao thức |
| --- | --- |
| **exact** | Kết quả phải khớp chính xác với ít nhất một ngữ cảnh được yêu cầu; đây là mặc định |
| **minimum** | Ngữ cảnh được IdP đánh giá ít nhất mạnh tương đương một trong các yêu cầu |
| **better** | Ngữ cảnh được IdP đánh giá mạnh hơn yêu cầu theo quy tắc của nó |
| **maximum** | Ngữ cảnh được IdP đánh giá mạnh nhất có thể nhưng không vượt quá giới hạn yêu cầu |

Định nghĩa “mạnh hơn” trong các so sánh không phải quy tắc sắp xếp URI bằng chuỗi; nó dựa trên ngữ nghĩa/mô hình so sánh của bên đáp ứng. Vì vậy trong tích hợp thực tế, **exact** với một ngữ cảnh đã thống nhất thường dễ kiểm thử hơn; một số IdP còn chỉ hỗ trợ tập con của các phép so sánh.

Mảnh XML minh họa một yêu cầu ngữ cảnh trong AuthnRequest:

~~~xml
<samlp:RequestedAuthnContext
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Comparison="exact">
    <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:SmartcardPKI
    </saml:AuthnContextClassRef>
</samlp:RequestedAuthnContext>
~~~

Đây chỉ là **đoạn con minh họa**, không phải một AuthnRequest hoàn chỉnh. Thông số class reference chỉ có giá trị khi IdP thực sự hỗ trợ lớp ngữ cảnh đó và chính sách tổ chức thống nhất cách diễn giải.

### ForceAuthn

Một **AuthnRequest** có thuộc tính **ForceAuthn="true"** yêu cầu IdP **xác thực trực tiếp người dùng** thay vì chỉ dựa vào ngữ cảnh bảo mật trước đó; mặc định khi không gửi là **false**. Điều này giúp yêu cầu xác thực mới khi người dùng thực hiện thao tác có độ rủi ro cao.

**ForceAuthn không đồng nghĩa bắt buộc MFA.** Muốn yêu cầu MFA hoặc một mức assurance cụ thể, cần chính sách IdP và ngữ cảnh yêu cầu phù hợp; SP vẫn phải xác minh AuthnContext và AuthnInstant trong assertion đã kiểm chứng. Một số IdP có hạn chế triển khai, vì vậy cần thử nghiệm liên thông thay vì giả định mọi thuộc tính request đều được hỗ trợ như nhau.

**Nếu IdP không thể đáp ứng ngữ cảnh yêu cầu**, giao thức có lỗi như **NoAuthnContext**. SP phải xử lý thất bại/không đạt yêu cầu một cách rõ ràng, không âm thầm hạ yêu cầu để cho qua giao dịch nhạy cảm.

## 7. Khi nào cần kiểm tra authentication freshness?

Ứng dụng có thể chấp nhận SSO thông thường cho việc xem dashboard nhưng yêu cầu **recent authentication** cho thao tác nhạy cảm:

- Thay đổi email khôi phục, mật khẩu hoặc cấu hình MFA.
- Phê duyệt chuyển tiền, xuất dữ liệu nhạy cảm hoặc cấp quyền admin.
- Thực hiện thao tác pháp lý, ký lệnh hoặc thay đổi chính sách bảo mật.
- Bật phiên quản trị đặc quyền trong thời gian ngắn.

Ví dụ chính sách:

> “Để duyệt khoản thanh toán, sự kiện xác thực gần nhất phải trong vòng **10 phút**, đồng thời AuthnContext phải thuộc danh sách ngữ cảnh xác thực mạnh mà doanh nghiệp đã phê duyệt.”

Hệ thống cần kiểm tra **đồng thời**:

1. Response/Assertion đã qua xác minh đầy đủ: IdP đáng tin, chữ ký hợp lệ, đúng audience, recipient, InResponseTo khi cần, đúng khoảng thời gian và không replay.
2. **AuthnInstant** hiện tại đủ mới so với đồng hồ máy chủ và độ lệch cho phép.
3. **AuthnContext** thể hiện chính sách/chất lượng xác thực đã thống nhất, không chỉ là tên URI.
4. Tài khoản có quyền nghiệp vụ thực hiện giao dịch, không chỉ đăng nhập thành công.
5. Nếu chưa đáp ứng, điều hướng tới flow **step-up / fresh authentication** rồi kiểm tra lại kết quả trước khi cho phép thao tác.

**Rủi ro:** đọc AuthnInstant từ XML mà chưa xác minh chữ ký và các điều kiện SAML có thể khiến kẻ tấn công tự gắn thời gian mới hoặc AuthnContext “mạnh”. Dữ liệu này chỉ có ý nghĩa sau khi thuộc **assertion được xác thực hợp lệ**.

## 8. Ví dụ Java 17: kiểm tra khoảng thời gian từ AuthnInstant

Ví dụ sau **độc lập, biên dịch và chạy được bằng Java 17+**. Nó minh họa tính tuổi của một sự kiện xác thực đã được IdP kiểm chứng; **không phải thư viện xác minh chữ ký SAML**.

Tạo tệp **AuthnFreshnessDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;

public class AuthnFreshnessDemo {

    public static void main(String[] args) {
        Instant authnInstant =
                Instant.parse("2026-11-07T08:00:00Z");
        Instant now =
                Instant.parse("2026-11-07T09:12:00Z");

        Duration age = Duration.between(authnInstant, now);
        Duration maxAge = Duration.ofMinutes(10);

        boolean freshEnough =
                !age.isNegative()
                && age.compareTo(maxAge) <= 0;

        System.out.println("Authn age (minutes): " + age.toMinutes());
        System.out.println("Fresh enough: " + freshEnough);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AuthnFreshnessDemo.java
java AuthnFreshnessDemo
~~~

Stdout **chính xác**:

~~~text
Authn age (minutes): 72
Fresh enough: false
~~~

Giải thích:

- 09:12Z trừ 08:00Z bằng **72 phút**.
- Chính sách tối đa 10 phút nên **freshEnough = false**.
- Ví dụ dùng thời gian cố định để có output có thể lặp lại. Trong hệ thống thật, nhận **AuthnInstant từ assertion đã được SP xác minh**, dùng thời gian máy chủ từ **Clock** đáng tin cậy và thêm quy tắc dung sai clock skew có giới hạn.
- Không dùng phép tính này để thay thế kiểm tra **Conditions.NotOnOrAfter**, **SubjectConfirmationData**, **chữ ký**, **audience**, **AuthnContext** hoặc phân quyền ứng dụng.
- Nếu AuthnInstant ở “tương lai” do đồng hồ lệch, ví dụ cố ý trả **false** vì không cho phép age âm. Hệ thống thật cần chính sách clock skew cẩn thận nhưng không bỏ kiểm tra độ mới.

**Thử suy luận:** Nếu IdP phát assertion mới tại 09:11Z, nhưng không xác thực lại và giữ AuthnInstant = 08:00Z, stdout **vẫn là 72 phút**. Nếu IdP xác thực lại thực sự lúc 09:11Z, AuthnInstant mới có thể là 09:11Z và age còn 1 phút, nhưng quyền thao tác vẫn phụ thuộc AuthnContext và authorization.

## 9. Spring Security dùng AuthnStatement như thế nào?

Với Spring Security trên Spring Boot servlet, mô-đun **SAML 2.0 Login** nhận SAML Response qua endpoint ACS và xử lý nó bằng provider dựa trên OpenSAML. Sau khi quá trình đăng nhập thành công, ứng dụng có **Authentication**, **principal** và có thể tạo phiên Spring Security tương ứng.

Một cấu hình đăng nhập đơn giản cho **Spring Boot 3 / Spring Security 6** (cần các dependency Spring Web, Spring Security và **spring-security-saml2-service-provider**, cùng cấu hình **RelyingPartyRegistration** hợp lệ với IdP):

Tệp **src/main/java/com/example/security/SamlSecurityConfig.java**:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là **class cấu hình thuộc dự án Spring Boot**, không phải chương trình độc lập chỉ cần lệnh **javac/java**; không có stdout cố định. Ngoài mã trên, phải cấu hình IdP issuer/entity ID, metadata/chứng thư ký, ACS và SP identity phù hợp. Spring Security SAML Login tự quản lý nhiều bước kiểm chứng giao thức của Web SSO, nhưng **không có nghĩa ứng dụng tự động có chính sách “xác thực lại trong 10 phút và đạt MFA”**.

### Khi ứng dụng cần dùng AuthnInstant hoặc AuthnContext

1. **Bước thứ nhất:** hoàn tất xác minh SAML Response/Assertion bằng thành phần phù hợp của Spring Security/OpenSAML, không dùng XML từ request trực tiếp làm nguồn tin.
2. **Bước thứ hai:** từ SAML Response đã được xác minh, truy cập **AuthnStatement** và **AuthnContext** qua API OpenSAML/phần mở rộng converter/provider tương ứng **phiên bản Spring Security đang dùng**. Không giả định các trường này được ánh xạ sẵn thành thuộc tính principal hoặc GrantedAuthority mặc định.
3. **Bước thứ ba:** diễn giải AuthnContextClassRef theo hợp đồng đã thỏa thuận với IdP; kiểm tra AuthnInstant với chính sách độ mới, xét trường hợp nhiều statement hoặc thiếu dữ liệu phù hợp.
4. **Bước thứ tư:** lưu kết quả **đã thẩm định** vào ngữ cảnh phiên/tập thông tin ứng dụng cần cho chính sách step-up, với thời hạn và cơ chế cập nhật khi xác thực lại.
5. **Bước thứ năm:** kiểm tra phân quyền nghiệp vụ tại controller/service/method security; nếu thông tin xác thực không đủ mới hoặc không đủ mạnh thì kích hoạt flow được hỗ trợ để yêu cầu IdP xác thực lại.

**Lưu ý phiên bản:** các API OpenSAML provider, converter và assertion accessor có thể thay đổi giữa các phiên bản Spring Security. Kiểm tra tài liệu API của phiên bản thực tế khi viết mã trích xuất AuthnStatement. Tránh viết parser XML thủ công để đọc từ **HTTP SAMLResponse chưa qua kiểm chứng**, đặc biệt tránh tự vô hiệu hóa kiểm tra chữ ký, audience hoặc subject confirmation.

### Không được hiểu sai phiên Spring Security

- **HttpSession/SecurityContext** của SP có vòng đời theo cấu hình ứng dụng.
- **SessionIndex/SessionNotOnOrAfter** nói về phiên IdP trong giao thức SAML.
- **AuthnInstant** nói về **sự kiện xác thực**, không phải thời điểm HttpSession mới được tạo.
- **AuthnContextClassRef** không tự biến thành quyền **ROLE_ADMIN** trong Spring Security.
- Khi triển khai **Single Logout**, cần thiết kế tương tác giữa IdP/SP và SessionIndex theo giao thức, không tự giả định logout một bên luôn kết thúc tức thì toàn bộ phiên bên kia.

## 10. Tình huống nghiệp vụ: xem dashboard và duyệt thanh toán

**Bối cảnh:** Một nhân viên đăng nhập IdP lúc 08:00Z bằng phương thức mật khẩu. Lúc 09:10Z, người đó mở Portal với SSO; IdP phát assertion mới có **AuthnInstant 08:00Z** và **AuthnContext PasswordProtectedTransport**.

**Hành động A — xem dashboard lúc 09:12Z:** Có thể cho phép nếu SAML assertion đã được kiểm chứng, phiên SP còn hợp lệ và người dùng đủ quyền xem. Chính sách xem dashboard không đòi hỏi sự kiện xác thực trong 10 phút gần nhất.

**Hành động B — duyệt thanh toán lúc 09:12Z:** Chính sách yêu cầu xác thực trong 10 phút và ngữ cảnh đã được doanh nghiệp đánh giá là MFA phù hợp. AuthnInstant 08:00Z đã quá cũ và PasswordProtectedTransport không chứng minh MFA. Portal phải **từ chối hành động tạm thời** và bắt đầu cơ chế **step-up/fresh authentication** đã thỏa thuận.

**Sau step-up:** IdP hoàn thành xác thực mới và trả assertion hợp lệ với AuthnInstant khoảng 09:13Z, AuthnContext thuộc giá trị đã được cho phép. Portal xác minh lại response, chính sách thời gian và ngữ cảnh; sau đó mới kiểm tra quyền duyệt thanh toán của nhân viên trên đơn hàng cụ thể.

**Nếu IdP chỉ phát assertion mới nhưng AuthnInstant không đổi:** Portal vẫn phải từ chối hành động B theo chính sách độ mới. Không suy đoán rằng có redirect SSO đồng nghĩa với MFA/reauthentication.

## 11. Các lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng **IssueInstant** thay cho **AuthnInstant** | Kết luận nhầm rằng người dùng vừa xác thực | Tính freshness từ AuthnStatement.AuthnInstant |
| Coi **Conditions.NotOnOrAfter** là thời điểm IdP session kết thúc | Đánh đồng tuổi assertion và vòng đời session | Xem đúng SessionNotOnOrAfter và policy phiên SP |
| Coi **SessionNotOnOrAfter** là thời gian tự kết thúc HttpSession | Dẫn đến thiết kế logout/session sai | Quản lý SP session độc lập, xử lý SAML logout theo cấu hình |
| Gắn **PasswordProtectedTransport** tương đương MFA | Cho qua hoạt động đòi assurance cao | Thống nhất mapping ngữ cảnh với IdP, thử nghiệm chính sách thực tế |
| Chỉ gửi **ForceAuthn=true** và không kiểm tra assertion trả về | Đơn vị tích hợp có thể không phát hiện kết quả không phù hợp | Xác minh AuthnInstant và AuthnContext đã ký/được xác thực sau response |
| Đọc AuthnStatement từ XML chưa xác thực | Dễ bị giả mạo thời gian hoặc lớp xác thực | Chỉ dùng dữ liệu sau khi kiểm chứng SAML đầy đủ |
| Bỏ qua lệch đồng hồ hoặc dùng LocalDateTime sai timezone | Từ chối sai hoặc chấp nhận sai độ mới | Dùng Instant/UTC và mức clock skew được kiểm soát |
| Tự coi **SessionIndex** là ID người dùng cố định | Tạo sai logic linking và rò rỉ liên kết phiên | Dùng định danh subject đã kiểm chứng theo chính sách; không dùng SessionIndex làm user ID |
| Tự gán quyền admin dựa trên AuthnContext | Nhầm xác thực mạnh với có quyền nghiệp vụ | Kết hợp role/permission và kiểm tra đối tượng cụ thể |
| SAML assertion chứa nhiều AuthnStatement nhưng chỉ chọn đại phần tử đầu | Có thể áp dụng sai độ mới hoặc ngữ cảnh | Đặt quy tắc chọn statement và từ chối dữ liệu mơ hồ khi yêu cầu đảm bảo cao |

## 12. Câu hỏi tự kiểm tra

**Câu 1:** SAML Assertion được phát lúc 11:00, nhưng AuthnInstant là 09:00. Thời điểm nào phản ánh việc người dùng được xác thực?  
**Đáp án:** **09:00**. IssueInstant 11:00 là thời điểm phát hành assertion, không tự có nghĩa xác thực mới lúc 11:00.

**Câu 2:** Assertion có Conditions.NotOnOrAfter lúc 11:05. Có đủ để khẳng định người dùng đã xác thực trong 5 phút trước 11:04 không?  
**Đáp án:** **Không**. Conditions xác định tính hiệu lực của assertion, còn độ mới xác thực dựa trên AuthnInstant.

**Câu 3:** AuthnContextClassRef là PasswordProtectedTransport. Có thể kết luận người dùng đã hoàn thành MFA không?  
**Đáp án:** **Không**. URI đó tự nó không chứng minh hai yếu tố xác thực; cần hợp đồng ánh xạ/đảm bảo với IdP.

**Câu 4:** SessionIndex có phải là ID của Spring HttpSession không?  
**Đáp án:** **Không**. Nó gắn với phiên của IdP/SAML authority, có thể phục vụ cơ chế SAML logout khi triển khai.

**Câu 5:** Gửi ForceAuthn=true có bảo đảm IdP đã xác thực mới và đạt đúng ngữ cảnh nghiệp vụ yêu cầu?  
**Đáp án:** Nó là **yêu cầu theo SAML**, nhưng SP vẫn phải kiểm tra response đã được xác minh, AuthnInstant, AuthnContext và tương thích thực tế với IdP.

**Câu 6:** Nếu AuthnInstant đủ mới, có thể bỏ kiểm tra chữ ký SAML hoặc quyền duyệt giao dịch không?  
**Đáp án:** **Không**. Freshness là một điều kiện bổ sung, không thay thế xác thực assertion hoặc authorization.

## 13. Checklist khi triển khai

- [ ] Xác định rõ IdP và SP; cấu hình issuer/entity ID, metadata, ACS, chứng thư và chữ ký tin cậy.
- [ ] Cho thư viện Spring Security/OpenSAML kiểm chứng SAML Response/Assertion **trước khi** tin AuthnStatement.
- [ ] Hiểu **AuthnInstant**, **IssueInstant**, **Conditions.NotOnOrAfter**, **SubjectConfirmationData.NotOnOrAfter** và **SessionNotOnOrAfter** là các thời điểm khác nhau.
- [ ] Chính sách freshness dùng AuthnInstant ở UTC/Instant, dung sai clock skew có giới hạn, không dùng local time không timezone.
- [ ] Ánh xạ AuthnContext từ IdP vào chính sách xác thực đã phê duyệt; không suy ra MFA chỉ từ URI bất kỳ.
- [ ] Nếu cần xác thực lại, sử dụng yêu cầu SAML phù hợp (ForceAuthn và/hoặc RequestedAuthnContext được IdP hỗ trợ), rồi kiểm chứng kết quả thực tế.
- [ ] Không đồng nhất SessionIndex với user ID hoặc Spring HttpSession ID.
- [ ] Có quy tắc rõ ràng với nhiều AuthnStatement, trường tùy chọn thiếu hoặc kết quả không thỏa chính sách.
- [ ] Bảo vệ dữ liệu nhạy cảm; không log toàn bộ assertion có thể chứa thông tin cá nhân và dấu vết phiên.
- [ ] Authorization theo role, tenant và tài nguyên nghiệp vụ vẫn được kiểm tra độc lập.

## 14. Ghi nhớ

**AuthnStatement trả lời “người dùng được xác thực khi nào và theo ngữ cảnh nào?”, không trả lời toàn bộ “người dùng được làm gì?”.** Trường **AuthnInstant** ghi nhận sự kiện xác thực thực tế, còn **AuthnContext** mô tả bối cảnh xác thực mà IdP công bố. **IssueInstant** và thời hạn của assertion/phiên là các dữ kiện riêng. Trong Spring Security, hãy kiểm chứng SAML trước, rồi nếu nghiệp vụ cần thì đánh giá độ mới và ngữ cảnh xác thực bằng chính sách riêng; cuối cùng vẫn kiểm tra quyền truy cập.

### Tài liệu chính thức

- **OASIS SAML 2.0 Core** — phần 2.7.2 Authentication Statement và phần 3.4 Authentication Request Protocol: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **OASIS SAML 2.0 Authentication Context** — định nghĩa các lớp/ngữ cảnh xác thực: https://docs.oasis-open.org/security/saml/v2.0/saml-authn-context-2.0-os.pdf
- **Spring Security — SAML 2.0 Login Overview**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security — Authenticating SAML Responses**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
