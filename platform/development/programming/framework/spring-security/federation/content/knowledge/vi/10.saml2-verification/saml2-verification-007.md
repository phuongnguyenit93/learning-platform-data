# Kiểm tra NotBefore, NotOnOrAfter và độ lệch đồng hồ cho phép trong SAML 2.0

Trong SAML 2.0 federation, Service Provider (SP, hay Relying Party) không được chấp nhận một Assertion chỉ vì nó có chữ ký hợp lệ. Assertion còn phải **được sử dụng đúng thời điểm**. Hai thuộc tính `NotBefore` và `NotOnOrAfter` quy định **khoảng hiệu lực**; cấu hình **clock skew** cho phép một sai số nhỏ do đồng hồ Identity Provider (IdP) và SP lệch nhau. Sai số này là một khoản dung sai có giới hạn, **không phải cách tắt kiểm tra thời gian**.

Bài học tập trung vào kiểm chứng SAML2 trong ứng dụng Java/Spring Security: hiểu ngữ nghĩa chính xác của mốc đầu/cuối, phân biệt thời gian của `<Conditions>` với `<SubjectConfirmationData>`, kiểm tra đơn vị/UTC và đồng hồ, cấu hình `OpenSaml5AuthenticationProvider.AssertionValidator`, xây dựng bài test biên bằng Java 17 và chẩn đoán sự cố với IdP.

**Kết luận nền tảng:** tại thời điểm hiện tại `now`, một khoảng hợp lệ thường được hiểu là **`NotBefore <= now < NotOnOrAfter`**. Khi có độ lệch cho phép `skew`, hai phía được nới có kiểm soát nhưng vẫn phải kiểm mọi điều kiện còn lại: chữ ký, issuer, audience, recipient, request correlation và chống phát lại.

## 1. Vì sao xác thực SAML phải kiểm thời gian?

Một SAML Assertion là một tuyên bố về danh tính, sự kiện xác thực và/hoặc thuộc tính do IdP phát hành cho bên tiếp nhận. Ngay cả khi chữ ký được ký bằng khóa đáng tin cậy, message vẫn có thể không an toàn nếu:

- Assertion được **sử dụng trước thời điểm IdP cho phép**.
- Assertion đã **hết hạn** nhưng bị gửi lại.
- Đồng hồ hệ thống SP bị sai, khiến Assertion tốt bị từ chối hoặc Assertion hết hạn được nhận.
- Kẻ tấn công tái sử dụng một Response đã thu thập được trong khoảng thời gian chấp nhận.
- Bộ kiểm chỉ xem `<Conditions>` mà bỏ qua thời hạn `<SubjectConfirmationData>`.
- Một custom validator lấy thời điểm từ header/client thay vì từ đồng hồ đáng tin của server.

Ví dụ: IdP B phát Assertion chỉ có hiệu lực từ `10:00Z` tới trước `10:05Z`. Nếu SP nhận nó lúc `10:07Z` mà không kiểm `NotOnOrAfter`, chữ ký có thể vẫn đúng nhưng yêu cầu xác thực **không còn hợp lệ về thời gian**.

**Authentication khác authorization:** qua thời gian và chữ ký là điều kiện để chấp nhận principal; còn vai trò, dữ liệu tenant và quyền tài nguyên vẫn phải được kiểm ở ứng dụng.

## 2. Vị trí của NotBefore và NotOnOrAfter trong SAML XML

Hai thuộc tính xuất hiện ở nhiều cấu trúc, nhưng cần phân biệt ít nhất hai ngữ cảnh:

| Cấu trúc | Mục đích | Cách đọc |
| --- | --- | --- |
| `Assertion/Conditions@NotBefore` | Thời điểm sớm nhất Assertion được dùng theo các conditions | Chưa tới mốc này thì chưa được dùng, tùy skew |
| `Assertion/Conditions@NotOnOrAfter` | Thời điểm các conditions hết hiệu lực | Đến mốc này thì hết hiệu lực, tùy skew |
| `Subject/SubjectConfirmation/SubjectConfirmationData@NotBefore` | Thời điểm sớm nhất cho việc xác nhận subject theo phương thức confirmation, nếu có | Bổ sung giới hạn; **không thay** Conditions |
| `Subject/SubjectConfirmation/SubjectConfirmationData@NotOnOrAfter` | Hạn cuối của bearer subject confirmation | Phải kiểm riêng cho confirmation được sử dụng |
| `Response@IssueInstant` | Thời điểm IdP tạo Response | Không tương đương hạn hết hiệu lực của Assertion |
| `Assertion@IssueInstant` | Thời điểm IdP phát Assertion | Không thay thế NotBefore/NotOnOrAfter |
| `AuthnStatement@AuthnInstant` | Thời điểm user thực sự được IdP xác thực | Có thể xảy ra trước lúc phát Assertion |
| `AuthnStatement@SessionNotOnOrAfter` | Giới hạn phiên liên quan đến authentication statement, khi được cung cấp | **Không** là bản sao thời hạn Assertion |
| `Metadata@validUntil` | Thời hạn của metadata SAML được công bố | Phục vụ quản lý metadata trust, không phải login Assertion |

**Không đánh đồng các trường chỉ vì đều chứa ngày giờ.** Ví dụ user đăng nhập IdP lúc 09:40, IdP phát Assertion lúc 10:00, bearer confirmation hết hạn lúc 10:03, Conditions hết hạn lúc 10:10. SP phải xử lý hạn của từng cấu trúc, không dùng `AuthnInstant = 09:40` để kết luận Response hiện tại đã hết hạn.

### Ví dụ XML có hai khoảng hiệu lực

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-example"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:00Z">

    <saml:Issuer>https://idp.example.com/saml</saml:Issuer>

    <saml:Subject>
        <saml:NameID>employee-123</saml:NameID>
        <saml:SubjectConfirmation
            Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
            <saml:SubjectConfirmationData
                InResponseTo="_request-123"
                Recipient="https://sp.example.com/login/saml2/sso/corp"
                NotOnOrAfter="2026-11-07T10:03:00Z"/>
        </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-11-07T09:59:00Z"
        NotOnOrAfter="2026-11-07T10:10:00Z">
        <saml:AudienceRestriction>
            <saml:Audience>https://sp.example.com/sp/corp</saml:Audience>
        </saml:AudienceRestriction>
    </saml:Conditions>
</saml:Assertion>
~~~

Đây chỉ là **fragment XML minh họa ngữ nghĩa**; nó không có SAML Response envelope, `AuthnStatement` và chữ ký hợp lệ, nên **không thể dùng để đăng nhập**. Khi kiểm thực tế, phải xác minh XML signature theo đúng phần tử được ký, issuer và các ràng buộc khác trước khi tin nội dung thuộc tính.

Tại `10:04:00Z` và **không có skew**, `Conditions` vẫn đang trong khoảng 09:59–10:10, nhưng bearer `SubjectConfirmationData` đã hết hạn từ 10:03. Nếu không có SubjectConfirmation hợp lệ khác theo profile, SP phải **từ chối** dù Conditions còn hiệu lực.

## 3. NotBefore có nghĩa gì?

`NotBefore` quy định **mốc bắt đầu**. Nếu mốc là `2026-11-07T10:00:00Z`:

- `09:59:59.999Z`: chưa đủ điều kiện khi skew bằng 0.
- `10:00:00.000Z`: đã tới lúc hợp lệ.
- `10:01:00Z`: qua kiểm tra mốc bắt đầu, nhưng còn phải kiểm mốc kết thúc và các điều kiện khác.

Về toán học, với `b = NotBefore` và `n = now`:

~~~text
Không có clock skew:
n >= b    -> đạt điều kiện NotBefore
n <  b    -> chưa đạt NotBefore
~~~

Không thể lấy `Assertion.IssueInstant` làm mốc thay thế nếu `Conditions.NotBefore` có giá trị khác. Một IdP có thể phát Assertion ở `09:59:30Z` nhưng đặt `NotBefore = 10:00Z`; việc SP nhận sớm vài giây là một lỗi thời gian có thể cần skew **nhỏ, có chính sách**.

Với bộ kiểm tra riêng, điều kiện mốc bắt đầu phải được áp cho đúng `Conditions` hoặc `SubjectConfirmationData` và không bỏ qua các kiểm tra ràng buộc thời gian khác.

## 4. NotOnOrAfter có nghĩa gì? Vì sao không phải "đến hết giây đó"?

`NotOnOrAfter` là **mốc đã hết hiệu lực**. Điểm quan trọng là tính **loại trừ** (*exclusive*) của thời điểm kết thúc.

Giả sử `NotOnOrAfter = 2026-11-07T10:05:00Z` và skew bằng 0:

| `now` | Hợp lệ về mốc kết thúc? | Lý do |
| --- | --- | --- |
| `10:04:59.999Z` | Có | Chưa tới mốc kết thúc |
| `10:05:00.000Z` | **Không** | Đã đúng thời điểm hết hạn |
| `10:05:00.001Z` | Không | Đã quá hạn |
| `10:08:00Z` | Không | Đã hết hiệu lực từ lâu |

Công thức:

~~~text
Không có clock skew:
n < e     -> chưa hết hạn
n >= e    -> đã hết hạn
e = NotOnOrAfter
~~~

**Lỗi thường gặp:** viết `now <= NotOnOrAfter` khiến thời điểm đúng bằng expiry vẫn được chấp nhận. Trong Java, cho upper bound có tính exclusive, dùng `now.isBefore(expiresAt)`, không dùng `!now.isAfter(expiresAt)`.

Câu "hết hạn lúc 10:05" không có nghĩa được dùng tới `10:05:59`. Thời gian là một `Instant` chính xác, không phải một phút được làm tròn để so sánh.

## 5. Khoảng hợp lệ dạng nửa mở và điều kiện dữ liệu đầu vào

Khi cả hai thuộc tính đều tồn tại:

~~~text
[b, e)

b = NotBefore
e = NotOnOrAfter
Yêu cầu b < e
Hợp lệ khi b <= now < e
~~~

Đây là **khoảng nửa mở**: bao gồm đầu trái, loại trừ đầu phải.

Nếu `NotBefore >= NotOnOrAfter`, khoảng không hợp lệ; theo SAML Core, khi cùng xuất hiện, NotBefore phải **sớm hơn** NotOnOrAfter. Không được dùng clock skew để “cứu” một khoảng có thứ tự sai: nó có thể mở ra điều kiện khó dự đoán và che lỗi IdP.

**Có thể thiếu một thuộc tính không?** Trong cấu trúc `<Conditions>` của **SAML Core**, `NotBefore` và `NotOnOrAfter` đều được định nghĩa **optional**. Thiếu một mốc nghĩa là mốc đó không được chỉ rõ ở cấp Conditions. Tuy nhiên các **SAML profiles và chính sách tin cậy của SP có thể yêu cầu hạn cụ thể**. Trong Bearer Web Browser SSO, `SubjectConfirmationData@NotOnOrAfter` là một ràng buộc quan trọng của profile. Không mặc định "thiếu là luôn hợp lệ" cho toàn bộ Web SSO và cũng không khẳng định mọi `Conditions` thiếu một thuộc tính là XML sai.

**Quyết định an toàn:** xác định các thời hạn bắt buộc theo profile thực tế, không tự viết validator bỏ qua expiration khi thiếu trường và không suy ngầm vô hạn nếu doanh nghiệp yêu cầu TTL tối đa.

## 6. Clock skew là gì và có tác dụng nào?

Giả sử IdP B nhanh hơn SP A **90 giây**. IdP phát Assertion với `NotBefore=10:00:00Z` theo đồng hồ của mình, trong khi SP nhìn thấy `09:58:30Z`. Nếu không có dung sai, SP từ chối Assertion chưa tới hạn dù hai phía đang làm việc bình thường.

**Clock skew tolerance** là một khoảng `Duration` được cấu hình tại SP, ví dụ 120 giây, để chấp nhận sai số nhỏ **khi đánh giá timestamp**. Thông thường dung sai ảnh hưởng **cả mốc sớm và mốc muộn**:

- Ở đầu khoảng, cho phép `now` sớm hơn `NotBefore` một lượng tối đa `skew`.
- Ở cuối khoảng, cho phép `now` muộn hơn `NotOnOrAfter` một lượng tối đa `skew`.

Mô hình khái niệm với `δ = skew >= 0`:

~~~text
Gốc:       b <= now < e

Có skew:
             now + δ >= b
         AND now - δ <  e

Tương đương với:
          b - δ <= now < e + δ
~~~

Trong đó `b < e` vẫn phải hợp lệ trước khi áp dung sai.

Ví dụ:

~~~text
NotBefore     = 10:00Z
NotOnOrAfter  = 10:05Z
clock skew    = 2 phút

Khoảng gốc:                [10:00, 10:05)
Khoảng chấp nhận có skew:  [09:58, 10:07)

09:57:59 -> FAIL
09:58:00 -> đạt kiểm thời gian
10:04:59 -> đạt kiểm thời gian
10:05:00 -> đạt kiểm thời gian nhờ skew
10:06:59 -> đạt kiểm thời gian nhờ skew
10:07:00 -> FAIL
~~~

**Đây chỉ là mô hình toán học để học:** trình xác minh Spring Security/OpenSAML thực tế còn có nhiều validators, policy, resolution/precision và yêu cầu profile. Không được diễn giải một phép kiểm thời gian `true` thành chứng cứ authentication thành công.

### Tại sao không đặt skew một giờ cho dễ?

Nếu skew quá lớn, SP cho phép chấp nhận Assertion **sớm hoặc trễ** hơn phạm vi IdP dự định. Khoảng có thể bị kéo dài cả hai phía, giúp tăng khả năng bị phát lại hoặc làm giảm hiệu quả expiration. Skew **không phải** thời hạn session và không được dùng để thay thế cấu hình NTP.

Giá trị phù hợp phụ thuộc yêu cầu bảo mật và mức đồng bộ của hai phía; **không có một giá trị số duy nhất hợp lệ cho mọi tổ chức**. Một số tài liệu dùng ví dụ 10 phút để minh họa API, không có nghĩa production nên đặt 10 phút.

## 7. Chọn độ lệch cho phép như thế nào?

Đầu tiên cần phân biệt **độ lệch quan sát được** và **dung sai được phê duyệt**:

- `observed offset`: chênh lệch của đồng hồ server với nguồn thời gian chính xác, có thể đo bằng hạ tầng/NTP.
- `configured clock skew`: mức lệch mà bộ xác minh chấp nhận khi đánh giá SAML timestamp.
- `Assertion lifetime`: thời hạn do IdP phát (ví dụ 2–5 phút cho bearer confirmation trong một chính sách cụ thể).
- `Session lifetime`: thời hạn cookie/application session; không nhất thiết trùng Assertion lifetime.

Quy trình chọn:

1. Đo độ lệch giữa KDC/NTP/system time của máy IdP và SP tại nhiều thời điểm.
2. Kiểm chênh lệch giữa các node Spring phía sau load balancer, pod/container và host.
3. Đồng bộ đồng hồ bằng NTP/chrony/systemd-timesyncd/Windows Time theo hạ tầng.
4. Thỏa thuận với quản trị IdP về thời hạn SAML assertion, bearer confirmation và **dung sai tối đa**.
5. Chọn **skew nhỏ nhất đủ đáp ứng sai số hợp lệ và mạng** sau khi đồng hồ đã ổn; đừng tăng vô hạn để che lỗi hạ tầng.
6. Kiểm các mốc sát ranh giới và negative test với nhiều node thực.
7. Theo dõi lỗi theo thời gian, hiệu chỉnh NTP trước khi tăng skew.
8. Ghi rõ giá trị đã chọn, owner, lý do và ngày review.

**Đề xuất học tập:** có thể thử `Duration.ofSeconds(60)` hoặc `Duration.ofMinutes(2)` trong staging để thấy tác động, sau đó chỉ áp production khi đã đo offset và được phê duyệt. Đây là **ví dụ**, không phải mức mặc định bắt buộc của Spring Security hay chuẩn SAML.

## 8. Cách xử lý khi có cả Conditions và SubjectConfirmationData

SAML Web Browser SSO không chỉ nhìn một khoảng thời gian. Assertion thường có:

1. `Conditions@NotBefore/NotOnOrAfter` — giới hạn **khả năng sử dụng Assertion**.
2. `SubjectConfirmationData@NotOnOrAfter` — giới hạn **khả năng xác nhận bearer subject** tại recipient/ACS đúng.
3. `SubjectConfirmationData@NotBefore` — mốc bắt đầu **nếu profile/message có cung cấp**.
4. Các điều kiện khác như `AudienceRestriction` và `SubjectConfirmationData@Recipient/InResponseTo`.

Một Assertion chỉ được dùng nếu **Conditions hợp lệ** **và** có **SubjectConfirmation hợp lệ theo profile**, sau khi mọi kiểm chứng khác cũng thành công.

### Tại sao không lấy mốc hết hạn muộn nhất?

Giả sử:

~~~text
Conditions:              [09:59, 10:10)
SubjectConfirmationData: [10:00, 10:03)

Thời điểm SP nhận:       10:04
Skew:                    0 phút

Conditions:              PASS
SubjectConfirmationData: FAIL
Kết quả xác nhận bearer: FAIL
~~~

Nếu chọn `max(10:10, 10:03) = 10:10` làm hạn chung, ta đã **vô tình bỏ qua** giới hạn của bearer confirmation. Ngược lại, lấy “hạn sớm hơn” chỉ là cách nghĩ nhanh khi có hai khoảng cụ thể; trong sản phẩm phải xác minh **từng phần tử với đúng validator** vì SAML có thể có nhiều SubjectConfirmation và điều kiện bổ sung.

### Nếu có nhiều SubjectConfirmation?

SAML có thể có nhiều `<SubjectConfirmation>`. Theo profile/errata, **một SubjectConfirmation phù hợp** có thể đủ để xác nhận subject, nhưng mỗi entry phải được đánh giá với method, recipient, InResponseTo, time window và chính sách áp dụng. Không lấy `NotOnOrAfter` dài nhất trong nhiều entry rồi gắn ngầm cho tất cả; cũng không lấy một confirmation đã hết hạn làm hợp lệ chỉ vì một confirmation khác còn hiệu lực nếu hai entry khác method hoặc recipient.

## 9. Thời điểm nhận, thời điểm xác minh và đồng hồ server

Có ba thời điểm dễ bị nhầm:

- **`IssueInstant`:** timestamp do IdP đặt khi tạo Response/Assertion.
- **`receivedAt`:** thời điểm SP thực sự nhận HTTP POST tại ACS; được đo bằng đồng hồ server đáng tin.
- **`validatedAt`:** thời điểm bộ kiểm tra thực hiện phép so sánh; trong xử lý đồng bộ thường rất gần receivedAt.

Không lấy timestamp từ browser, `Date` header người dùng gửi, JavaScript frontend hoặc RelayState do client cung cấp làm `now` cho validation. Nếu ứng dụng phân tán qua queue hoặc xử lý bất đồng bộ, cần xác định policy đánh giá lúc nhận hay lúc xác minh theo thư viện/thiết kế và bảo vệ trước việc message bị trì hoãn lâu.

**Nên dùng `Instant` / `Clock`, không dùng local time không có timezone.** Ví dụ:

~~~text
2026-11-07T10:00:00Z
2026-11-07T17:00:00+07:00

Hai giá trị trên biểu diễn cùng một thời điểm.
~~~

Java `Instant.parse("2026-11-07T10:00:00Z")` mô tả UTC. Nếu nhận timestamp có offset, xử lý qua `OffsetDateTime.parse(...).toInstant()`. Không parse SAML time bằng `LocalDateTime` rồi ngầm áp múi giờ của máy chủ.

Lưu ý thay đổi timezone/ngày giờ mùa hè ở địa phương không được làm thay đổi `Instant`; SAML timestamp dùng chuẩn `xsd:dateTime` theo đặc tả, thường phát trong UTC `Z`.

## 10. Cấu hình clock skew trong Spring Security 7.x / OpenSAML 5

**Mốc phiên bản:** tài liệu chính thức Spring Security 7.1 cho biết luồng nhận SAMLResponse được xử lý bằng `Saml2AuthenticationTokenConverter` và `OpenSaml5AuthenticationProvider`. Để cấu hình sai số thời gian, Spring Security đưa ra API:

~~~java
OpenSaml5AuthenticationProvider provider =
        new OpenSaml5AuthenticationProvider();

OpenSaml5AuthenticationProvider.AssertionValidator validator =
        OpenSaml5AuthenticationProvider.AssertionValidator.builder()
                .clockSkew(Duration.ofMinutes(2))
                .build();

provider.setAssertionValidator(validator);
~~~

`Duration.ofMinutes(2)` ở đây **chỉ là policy mẫu**, không phải recommendation chung hay giá trị mặc định của framework.

### JavaConfig cho một ứng dụng Spring Security Servlet

File `SamlSkewSecurityConfiguration.java`:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider.AssertionValidator;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSkewSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        OpenSaml5AuthenticationProvider provider =
                new OpenSaml5AuthenticationProvider();

        AssertionValidator assertionValidator = AssertionValidator.builder()
                .clockSkew(Duration.ofMinutes(2))
                .build();

        provider.setAssertionValidator(assertionValidator);

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
~~~

Đây là **mã cấu hình trong dự án Spring**, không phải chương trình Java thuần biên dịch bằng `javac`. Cần đầy đủ dependency Spring Security SAML2, `RelyingPartyRegistrationRepository`, metadata/chứng thư IdP và cấu hình web hợp lệ. Nếu dự án có nhiều `SecurityFilterChain`, phải bảo đảm endpoint ACS đi qua chain dùng provider đã chỉnh.

Giải thích:

- `OpenSaml5AuthenticationProvider` thực hiện xác thực và áp các validator cần thiết cho SAML Response/Assertions.
- `AssertionValidator.builder().clockSkew(...)` điều chỉnh tolerance của các phép kiểm thời gian trong validation context của assertion theo API hiện hành.
- `setAssertionValidator(...)` cung cấp validator được cấu hình cho provider.
- `saml2Login(...authenticationManager(...))` đảm bảo filter SAML sử dụng `ProviderManager` chứa provider đã chỉnh, thay vì chỉ tạo bean không được gắn vào quá trình login.
- Việc sử dụng builder mặc định với `clockSkew` **không phải lệnh tắt** issuer, audience, signature hay subject confirmation validation.

**Quan trọng:** đây là cấu hình dành cho **Spring Security 7 / OpenSAML 5** hoặc nhánh đã xác nhận hỗ trợ chính xác API đó. Không copy tên class/method của 7.x sang một ứng dụng Spring Security 5/6 dùng provider OpenSAML khác mà chưa kiểm version. Đặc biệt, `clockSkew` của assertion validator **không được hiểu là tự động thay mọi giới hạn thời gian khác** như metadata validUntil, session TTL, logout timestamp, hoặc cookie expiration.

## 11. Khi dùng Spring Security 5.x hoặc 6.x phải làm gì?

Spring Security đã thay đổi các lớp provider theo thế hệ:

| Dòng | Provider/API liên quan | Cách tiếp cận |
| --- | --- | --- |
| **Spring Security 5.4/5.5 đời cũ** | `OpenSamlAuthenticationProvider` | Có `setResponseTimeValidationSkew(Duration)` đời cũ (deprecated), hoặc custom assertion validator dùng `ValidationContext` |
| **Spring Security 6.0–một số 6.x** | `OpenSaml4AuthenticationProvider` | Đối chiếu `createDefaultAssertionValidatorWithParameters` và `ValidationContext` của đúng patch |
| **Nhánh hỗ trợ OpenSAML 5** | `OpenSaml5AuthenticationProvider` | Dùng builder `AssertionValidator.builder().clockSkew(...)` khi Javadoc xác nhận |
| **Spring Security 7.x** | `OpenSaml5AuthenticationProvider` | Dùng documented `AssertionValidator` builder như phần trên |

Trong các API cũ, tham số dạng `SAML2AssertionValidationParameters.CLOCK_SKEW` của OpenSAML `ValidationContext` được tính theo **milliseconds**. Không truyền `120` và tưởng là 120 giây khi API mong **mili giây**: đó chỉ là 0,12 giây. Dòng API mới nhận `java.time.Duration`, tránh nhầm đơn vị.

**Không đoán provider chỉ từ Spring Boot major.** Kiểm dependency graph runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
~~~

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Chọn tài liệu/Javadoc của **exact artifact version**. Một bản nâng Spring Security cũng có thể thay OpenSAML, Servlet `javax` → `jakarta` hoặc chữ ký method. Không chỉ override riêng `spring-security-saml2-service-provider` để lấy một API mà bỏ qua bộ module khác.

### Có nên thay assertion validator hoàn toàn?

Không nếu chỉ cần chỉnh dung sai. Một custom validator viết tay có thể vô ý làm mất `AudienceRestrictionValidator`, `BearerSubjectConfirmationValidator`, hoặc các kiểm tra conditions khác. Tài liệu Spring Security nêu rõ các phương án giữ default validator rồi nối additional validation; **đừng thay toàn bộ mặc định** nếu chưa chứng minh mọi kiểm tra profile còn nguyên.

Đặc biệt, **không** sửa lỗi time bằng cách loại bỏ toàn bộ condition validators, tắt chữ ký hoặc bỏ `InResponseTo`. Việc lấy login thành công bằng cách xóa các ràng buộc an toàn là một thất bại thiết kế.

## 12. Java 17 chạy độc lập: kiểm đúng biên và clock skew

Ví dụ sau không dùng Spring Security, OpenSAML hoặc XML. Nó **mô hình hóa phép so sánh khoảng nửa mở** để bạn tự kiểm dấu bằng/không bằng, cách nới skew và việc có **hai** cửa sổ kiểm tra `Conditions` và `SubjectConfirmationData`.

Tạo file **`SamlTimeWindowDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;

public class SamlTimeWindowDemo {

    record Window(Instant notBefore, Instant notOnOrAfter) {}

    static boolean validAt(
            Instant now, Window window, Duration skew) {
        if (skew.isNegative()) {
            throw new IllegalArgumentException("negative skew");
        }
        if (!window.notBefore().isBefore(window.notOnOrAfter())) {
            return false;
        }
        return !now.plus(skew).isBefore(window.notBefore())
                && now.minus(skew).isBefore(window.notOnOrAfter());
    }

    static boolean bothValid(
            Instant now, Window conditions,
            Window subjectConfirmation, Duration skew) {
        return validAt(now, conditions, skew)
                && validAt(now, subjectConfirmation, skew);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Duration none = Duration.ZERO;
        Duration threeMinutes = Duration.ofMinutes(3);

        Window normal = new Window(
                now.minusSeconds(60), now.plusSeconds(300));

        Window future = new Window(
                now.plusSeconds(120), now.plusSeconds(300));

        Window endingNow = new Window(
                now.minusSeconds(300), now);

        Window expiredFiveMinutesAgo = new Window(
                now.minusSeconds(900), now.minusSeconds(300));

        Window subjectExpiredOneSecondAgo = new Window(
                now.minusSeconds(60), now.minusSeconds(1));

        Window invalid = new Window(
                now.plusSeconds(60), now.minusSeconds(60));

        System.out.println("Inside: "
                + validAt(now, normal, none));
        System.out.println("End exclusive: "
                + validAt(now, endingNow, none));
        System.out.println("Future without skew: "
                + validAt(now, future, none));
        System.out.println("Future with 3m skew: "
                + validAt(now, future, threeMinutes));
        System.out.println("Expired 5m, skew 3m: "
                + validAt(now, expiredFiveMinutesAgo, threeMinutes));
        System.out.println("Subject expires first: "
                + bothValid(now, normal, subjectExpiredOneSecondAgo, none));
        System.out.println("Invalid interval: "
                + validAt(now, invalid, threeMinutes));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac SamlTimeWindowDemo.java
java SamlTimeWindowDemo
~~~

**Stdout chính xác:**

~~~text
Inside: true
End exclusive: false
Future without skew: false
Future with 3m skew: true
Expired 5m, skew 3m: false
Subject expires first: false
Invalid interval: false
~~~

Vì sao từng kết quả đúng?

- `Inside: true` — now nằm trong khoảng [-1 phút, +5 phút].
- `End exclusive: false` — expiry đúng bằng now thì **hết hạn**.
- `Future without skew: false` — Assertion chưa tới NotBefore (+2 phút).
- `Future with 3m skew: true` — dung sai +3 phút cho phép lệch +2 phút.
- `Expired 5m, skew 3m: false` — đã quá hạn nhiều hơn dung sai cho phép.
- `Subject expires first: false` — Conditions còn thời gian nhưng bearer confirmation đã hết hạn.
- `Invalid interval: false` — `NotBefore` sau `NotOnOrAfter` phải bị từ chối trước khi xét skew.

**Giới hạn quan trọng:** `Window` bắt buộc cả hai mốc để dễ học; SAML Core cho phép `Conditions` thiếu một mốc, và Web Browser bearer profile có yêu cầu khác. Chương trình không thể mô phỏng đầy đủ quy tắc missing-field, signature, issuer, recipient, multiple confirmations, DateTime precision, replay cache hoặc policy của Spring Security. Không dùng `validAt` thay cho `OpenSaml5AuthenticationProvider`.

## 13. Bảng test biên để tránh lỗi so sánh

Dùng một Assertion mẫu với:

~~~text
NotBefore     = 2026-11-07T10:00:00Z
NotOnOrAfter  = 2026-11-07T10:05:00Z
Skew          = 0 hoặc 2 phút
~~~

| Thời điểm kiểm `now` | Skew = 0 | Skew = 2 phút | Diễn giải |
| --- | --- | --- | --- |
| 09:57:59Z | FAIL | FAIL | Trước cả ngưỡng nới |
| 09:58:00Z | FAIL | PASS về time | Đúng đầu nới |
| 09:59:59Z | FAIL | PASS về time | Sớm dưới 2 phút |
| 10:00:00Z | PASS | PASS | Đúng NotBefore, inclusive |
| 10:04:59Z | PASS | PASS | Trước expiry |
| 10:05:00Z | **FAIL** | PASS về time | Đúng expiry, exclusive khi không skew |
| 10:06:59Z | FAIL | PASS về time | Muộn dưới 2 phút |
| 10:07:00Z | FAIL | **FAIL** | Đúng cuối ngưỡng nới, exclusive |
| 10:07:01Z | FAIL | FAIL | Quá ngưỡng nới |

Ký hiệu **PASS về time** chỉ có nghĩa bài toán thời gian minh họa thỏa công thức; **không đủ** để xác thực SAML Response.

Thêm các ca bắt buộc:

- NotBefore **bằng** NotOnOrAfter → FAIL vì khoảng không có độ dài.
- NotBefore **sau** NotOnOrAfter → FAIL dù skew lớn.
- Conditions còn hạn nhưng SubjectConfirmationData hết hạn → FAIL nếu không có confirmation khác hợp lệ.
- Conditions hết hạn nhưng SubjectConfirmationData còn hạn → FAIL; cả hai đều là ràng buộc cần kiểm.
- SAML timestamp có `Z` và có `+07:00` mô tả cùng Instant → kết quả không được khác.
- IdP ký một assertion trong tương lai quá nhiều so với skew → FAIL.
- Assertion hợp lệ về thời gian nhưng issuer/audience/recipient sai → FAIL.
- Assertion hợp lệ về thời gian nhưng signature sai → FAIL.
- Assertion hợp lệ về thời gian nhưng `InResponseTo` không khớp request → FAIL theo SP-initiated policy.
- Replay Response cũ trong khoảng dung sai → phải bị chống phát lại theo policy.

## 14. Vì sao thời gian hợp lệ không chống được replay?

Một attacker giữ bản sao của một Assertion có chữ ký hợp lệ chưa chắc đã sửa được nội dung. Tuy nhiên nếu gửi lại trong thời gian SP vẫn chấp nhận, chỉ kiểm NotBefore/NotOnOrAfter có thể **không đủ** để phát hiện hành vi tái sử dụng.

Các lớp bảo vệ cần kết hợp:

1. **Mốc thời gian ngắn** cho bearer confirmation và Conditions theo hợp đồng IdP.
2. **Recipient/Destination** khớp chính xác ACS được phép.
3. **AudienceRestriction** khớp SP Entity ID của application.
4. **Issuer + signature** đúng IdP đã đăng ký.
5. **InResponseTo** gắn với AuthnRequest của browser/session khi dùng SP-initiated SSO.
6. **Replay detection** theo Message/Assertion ID khi threat model/profile yêu cầu.
7. **Session management** bảo vệ login fixation, cookie và timeout.
8. **Role/object authorization** độc lập để không mở rộng đặc quyền chỉ nhờ SAML.

Nếu skew tăng từ 2 phút lên 15 phút, biên kiểm thời gian nới theo cả hai hướng; **khả năng chấp nhận lại các message cũ tăng lên** trong mô hình đơn giản. Chỉ tăng skew không giải quyết NTP sai, và không thể thay cho anti-replay.

Đối với `OneTimeUse` trong SAML Conditions, cần biết framework/profile có thực sự kiểm điều kiện này hay không. Theo tài liệu Spring Security 7.x, có thể thêm `OneTimeUseConditionValidator` vào assertion validator bằng builder khi policy yêu cầu; không giả định một check NotOnOrAfter tự thực hiện OneTimeUse.

## 15. Xử lý sai lệch đồng hồ trong hạ tầng thực

Nguồn lỗi có thể ở bất kỳ phía nào:

| Tầng | Rủi ro | Việc cần kiểm |
| --- | --- | --- |
| **IdP** | Đồng hồ máy IdP/cluster lệch hoặc đổi theo failover | Thời gian chính xác trên các node và nguồn NTP |
| **SP** | JVM/container dùng đồng hồ host không chuẩn | Giám sát host time, NTP, image/OS, nhiều pods |
| **Mạng** | Request tới IdP rồi quay lại chậm, proxy/buffering | Round-trip, latency P95/P99, timeouts, queue |
| **Load balancer** | Node A đúng giờ, node B lệch | Kiểm cùng lúc toàn bộ node |
| **Clock configuration** | Phân biệt lệch Instant với timezone hiển thị | So UTC timestamp và offset thật |
| **Parser** | Phân tích `xsd:dateTime` sai timezone, làm tròn giây | Dùng thư viện SAML/XML và `Instant` chính xác |
| **IdP policy** | Bearer lifetime quá ngắn so với luồng user | Phối hợp IdP về TTL hợp lệ thay vì tự tăng skew rất lớn |
| **SP policy** | Custom validator bỏ Conditions/bearer expiration | Khôi phục validators chuẩn, thêm regression tests |

Đối với Linux có systemd, kiểm hệ thống (tùy bản phân phối):

~~~bash
date -u
timedatectl status
~~~

Nếu có chrony:

~~~bash
chronyc tracking
chronyc sources -v
~~~

Trên Windows Domain Controller hoặc Windows host:

~~~powershell
w32tm /query /status
w32tm /query /source
~~~

**Không có stdout chung** cho các lệnh trên. Kiểm hiện trạng thực, độ lệch ước tính, nguồn thời gian, reachability và sức khỏe synchronization. Không đổi đồng hồ production thủ công chỉ để đi qua một SAML login failure: tác động có thể lan sang TLS, log ordering, database, cache, scheduler và các giao thức xác thực khác.

Trong Kubernetes, phần lớn container chia sẻ clock của host; đừng cho rằng thay `TZ` của container sẽ làm lệch UTC Instant. `TZ` chủ yếu ảnh hưởng cách hiển thị local time. Vấn đề có thể là host NTP hoặc clock provider trong môi trường ảo hóa.

## 16. Chẩn đoán lỗi trước khi tăng clockSkew

Khi nhận log như "assertion not yet valid", "assertion expired", "subject confirmation has expired", hãy xác định:

1. Assertion bị từ chối tại **Conditions** hay **SubjectConfirmationData**?
2. `NotBefore` / `NotOnOrAfter` chính xác trong message sau khi **đã được xác minh chữ ký** là gì?
3. SP nhận request lúc nào theo đồng hồ UTC đáng tin? IdP có đang nhanh/chậm không?
4. Có `IssueInstant` hoặc `AuthnInstant` bị nhầm với expiry không?
5. Có mất thời gian do IdP MFA, cross-domain redirects, browser delay, proxy queue hoặc network không?
6. Có mất session/`InResponseTo` hoặc sai audience/recipient nhưng log bị gom thành "SAML invalid" không?
7. Validator nào thực sự đang chạy: mặc định hay custom `AssertionValidator`?
8. Skew cấu hình được áp vào provider thực thi hay chỉ nằm ở một bean không được dùng?

**Thứ tự sửa ưu tiên:**

- Đầu tiên đồng bộ **đồng hồ IdP/SP** và kiểm Internet/NTP/firewall trong môi trường.
- Tiếp đến đánh giá đúng **thời hạn IdP phát** và SAML round-trip.
- Rồi kiểm **clock skew policy** đủ nhỏ và đúng nơi cấu hình.
- Cuối cùng mới thay một thành phần phức tạp của SAML validation nếu có bằng chứng API/config bị lỗi.

Nếu một request cụ thể chỉ hỏng khi đi qua node B, hãy nghi ngờ **clock skew theo node** trước khi chỉnh toàn bộ bean của ứng dụng.

## 17. Vấn đề liên quan tới session, logout và hiệu lực sau login

Assertion validity áp dụng khi **đang chấp nhận SAML Assertion** tại ACS. Sau khi Spring Security tạo `Authentication` và ứng dụng có session cookie riêng, **phiên ứng dụng không tự động hết hạn ngay khi NotOnOrAfter qua**. Đây là hai tầng thời gian khác nhau.

Ví dụ:

~~~text
10:00 IdP phát Assertion (Conditions hết hạn 10:10)
10:02 SP xác minh hợp lệ và tạo session ứng dụng
10:10 Conditions của Assertion hết hạn
10:30 Session ứng dụng còn hoạt động (nếu app cấu hình vậy)
~~~

Tình huống này không tự mâu thuẫn: SAML Assertion phục vụ **việc thiết lập danh tính ở thời điểm login**; ứng dụng phải quản lý session TTL, `SessionNotOnOrAfter` nếu áp dụng theo profile, logout, role refresh và deprovisioning theo policy.

Vì vậy đừng sửa session timeout bằng cách tăng/giảm `clockSkew`, cũng đừng coi `NotOnOrAfter` là lúc phải lập tức xóa mọi cookie. Nếu chính sách SAML session yêu cầu SP tôn trọng `SessionNotOnOrAfter`, phải đảm bảo ứng dụng thực thi thông qua cơ chế quản lý phiên và kiểm thử riêng.

## 18. Dấu thời gian khác trong SAML không được xử lý chung một cách mù quáng

Ngoài Assertion Conditions, có những mốc khác:

- `SAML Response IssueInstant`: phát sinh message; không phải Assertion expiration.
- `Assertion IssueInstant`: phát hành Assertion; có thể có giới hạn “độ cũ” riêng theo chính sách nhưng không thay `Conditions`.
- `SubjectConfirmationData NotOnOrAfter`: hết hạn bearer confirmation, thường chặt hơn `Conditions`.
- `AuthnStatement AuthnInstant`: xác thực người dùng đã diễn ra khi nào; có thể dùng trong đánh giá `max authentication age`, MFA freshness.
- `AuthnStatement SessionNotOnOrAfter`: time cap của phiên theo statement, nếu có.
- `SAML Metadata validUntil`: thời gian metadata còn hiệu lực; cần quy trình reload/refresh và signature verification.
- `LogoutRequest NotOnOrAfter`: giới hạn message logout, không phải login assertion.

Đừng áp `clockSkew` cho mọi timestamp theo một custom helper duy nhất nếu profile/thư viện không làm vậy. Ví dụ thời hạn của metadata hoặc logout có thể do component khác xử lý; phải kiểm bằng test theo từng thành phần và Javadoc phiên bản được resolve.

## 19. Bài tập tình huống

### Tình huống A: chênh 90 giây

IdP phát `NotBefore=10:00:00Z`, `NotOnOrAfter=10:05:00Z`. SP nhận tại `09:58:30Z`.

- Skew = 0: **FAIL** vì chưa đến NotBefore.
- Skew = 2 phút: **PASS về mốc thời gian minh họa** vì now + 2 phút = 10:00:30Z.
- Nếu issuer/signature/audience sai: vẫn **FAIL toàn bộ** dù timestamp hợp lệ.

**Hướng vận hành:** kiểm NTP/SP offset trước; nếu có sai số ổn định nhỏ mà chính sách cho phép thì cấu hình skew hẹp và ghi nhận.

### Tình huống B: Conditions còn hiệu lực nhưng SubjectConfirmation hết hạn

`Conditions` có expiry 10:10, `SubjectConfirmationData` có expiry 10:03; SP nhận lúc 10:04; skew=0.

**Kết quả:** bearer confirmation hết hạn, phải từ chối nếu không có confirmation hợp lệ khác. Không dùng 10:10 làm expiry thay cho cả hai.

### Tình huống C: đúng bằng NotOnOrAfter

`NotOnOrAfter=10:05:00Z`, SP kiểm `10:05:00Z`, skew=0.

**Kết quả:** **FAIL**. Vì NotOnOrAfter là exclusive; viết `now <= e` là lỗi so sánh.

### Tình huống D: tăng skew 30 phút để chống login timeout

Một đội muốn tăng skew lên 30 phút vì user đăng nhập IdP cần MFA lâu.

**Phân tích:** 30 phút kéo rộng cửa sổ chấp nhận của SAML assertion, có thể làm tăng rủi ro replay. Phải xem **thời điểm IdP phát assertion**: nếu IdP phát sau MFA, thời gian user thao tác trước đó không nhất thiết là thời gian tuổi Assertion. Kiểm round-trip thực, NTP và lifetime của bearer confirmation; chỉ tăng dung sai ở mức đã đo/phê duyệt.

### Tình huống E: nhiều node lệch giờ

Node A trả login thành công; Node B thất bại `NotBefore` với cùng IdP, traffic qua load balancer.

**Phân tích:** so `date -u` / NTP offset của host A/B, kiểm source NTP, time drift, session propagation và reverse proxy. Không mặc định sửa SAML issuer/audience nếu cùng cấu hình chỉ khác node.

### Tình huống F: Java parse local time

IdP phát `2026-11-07T10:00:00Z`, developer parse thành local `10:00` ở múi giờ Asia/Ho_Chi_Minh rồi so với UTC của server.

**Sai ở đâu?** Thời gian `10:00Z` thực tế là `17:00+07:00`. Cần chuyển mọi thời điểm về `Instant`, không trộn local time và UTC; thay timezone hiển thị không sửa được clock drift.

## 20. Checklist kiểm thử và vận hành

- [ ] Đã xác định provider thực tế của Spring Security/OpenSAML theo dependency graph.
- [ ] `RelyingPartyRegistration` tin đúng IdP, certificate và ACS.
- [ ] Kiểm `Conditions@NotBefore` inclusive và `Conditions@NotOnOrAfter` exclusive.
- [ ] Kiểm riêng `SubjectConfirmationData@NotOnOrAfter`, `Recipient` và `InResponseTo`.
- [ ] Phép kiểm với `NotBefore >= NotOnOrAfter` phải từ chối.
- [ ] Mọi timestamp được chuẩn hóa thành UTC/`Instant`; không làm tròn phút.
- [ ] Clock skew được đo/phê duyệt nhỏ, không đoán mặc định.
- [ ] JavaConfig gắn assertion validator vào authentication provider **đang thực thi**.
- [ ] Giữ tất cả default validation về signature, issuer, audience, subject confirmation và conditions.
- [ ] Test ngay trước/đúng/sau từng biên có và không có skew.
- [ ] Test Conditions còn hiệu lực nhưng bearer confirmation hết hạn, và ngược lại.
- [ ] Kiểm IdP-initiated theo policy riêng, không bỏ request correlation bừa bãi.
- [ ] Có replay prevention và session cookie security phù hợp.
- [ ] Các node SP/IdP và host container đồng bộ nguồn thời gian đáng tin.
- [ ] Negative tests không biến thành PASS chỉ vì tăng skew.
- [ ] Không lưu SAML Assertion thô, private keys hoặc dữ liệu cá nhân trong log production.
- [ ] Theo dõi metrics lỗi time validation để phát hiện clock drift hoặc IdP thay lifetime.
- [ ] Kiểm session TTL/`SessionNotOnOrAfter` riêng với Assertion expiration.
- [ ] Khi tăng/giảm skew, ghi quyết định, thử trên staging và có rollback.

## 21. Tài liệu gốc để đối chiếu

Tài liệu và phiên bản API Spring Security thay đổi; hãy mở đúng dòng đang chạy trong ứng dụng:

1. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): hướng dẫn **Setting a Clock Skew** với `OpenSaml5AuthenticationProvider.AssertionValidator.builder().clockSkew(Duration)` và cách gắn `AuthenticationManager`.
2. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): luồng SP/IdP, ACS và vai trò của `Saml2WebSsoAuthenticationFilter`.
3. [Spring Security — SAML 2.0 Migrations](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html): khác biệt OpenSAML 4/5 và các phiên bản provider khi nâng cấp.
4. [Spring Security 6.0 — OpenSaml4AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.0.x/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): tham số `ValidationContext` và cách thêm validator theo API cũ.
5. [Spring Security 5.4 — OpenSamlAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/5.4.2/api/org/springframework/security/saml2/provider/service/authentication/OpenSamlAuthenticationProvider.html): API cũ `setResponseTimeValidationSkew` và ghi chú deprecated.
6. [OASIS SAML 2.0 Core, `2.5.1.2`](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): ngữ nghĩa `NotBefore`, `NotOnOrAfter`, mốc optional của Conditions và yêu cầu `NotBefore < NotOnOrAfter` khi cùng xuất hiện.
7. [OASIS SAML 2.0 Approved Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0-cd-02.html): kiểm bearer SubjectConfirmationData NotOnOrAfter, Recipient, InResponseTo và thời hạn SessionNotOnOrAfter.
8. [RFC 7522 — SAML2 Profile for OAuth2](https://www.rfc-editor.org/rfc/rfc7522.html): tài liệu **profile khác Web Browser SSO** nhưng minh họa yêu cầu kiểm expiry và clock skew cho SAML bearer assertions. Không lấy RFC này thay cho các điều kiện Web SSO của OASIS.
9. [Microsoft Learn — SAML Protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol): ví dụ thực tế của `Conditions` và `SubjectConfirmationData` và các thời hạn khác nhau.

**Ghi nhớ cuối cùng:** `NotBefore` là **đầu khoảng có tính bao gồm**, `NotOnOrAfter` là **đầu thời điểm hết hiệu lực có tính loại trừ**, và `clockSkew` chỉ là dung sai nhỏ để bù chênh đồng hồ. SP phải kiểm độc lập **Conditions**, **SubjectConfirmation**, chữ ký, issuer, audience, recipient, request correlation và chống phát lại. Sửa hạ tầng đồng hồ trước, chỉnh clock skew có chính sách sau; không dùng skew lớn để bỏ qua các ranh giới bảo mật của SAML2.