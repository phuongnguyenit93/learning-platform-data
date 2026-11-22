# Conditions, AudienceRestriction và thời hạn assertion trong SAML 2.0

Một **SAML 2.0 Assertion** là tập hợp phát biểu do Identity Provider (IdP) đưa ra về một chủ thể, nhưng **assertion có chữ ký hợp lệ không có nghĩa mọi Service Provider (SP) được phép dùng nó vào mọi thời điểm**. Bên nhận phải xác minh ranh giới sử dụng: assertion có hiệu lực **từ khi nào đến trước khi nào**, **dành cho SP nào**, và **chứng minh chủ thể theo cách nào**.

Nhóm kiểm tra trung tâm của bài này là `<saml:Conditions>`, `<saml:AudienceRestriction>`, các thuộc tính `NotBefore`/`NotOnOrAfter`. Với SAML Web Browser SSO, phải hiểu thêm thời hạn ở **`SubjectConfirmationData`**: đó là một giới hạn độc lập, có thể khiến assertion không thể dùng ngay cả khi `Conditions` còn hiệu lực.

## 1. Định vị các trường trong assertion

~~~text
samlp:Response
├── @ID, @IssueInstant, @Destination, @InResponseTo
├── saml:Issuer
└── saml:Assertion  (được bảo vệ bằng chữ ký theo binding/profile)
    ├── @ID, @IssueInstant
    ├── saml:Issuer
    ├── saml:Subject
    │   └── saml:SubjectConfirmation Method="...:bearer"
    │       └── saml:SubjectConfirmationData
    │           ├── @Recipient
    │           ├── @InResponseTo
    │           └── @NotOnOrAfter
    ├── saml:Conditions
    │   ├── @NotBefore
    │   ├── @NotOnOrAfter
    │   └── saml:AudienceRestriction
    │       └── saml:Audience
    └── saml:AuthnStatement
        ├── @AuthnInstant
        └── @SessionNotOnOrAfter (nếu có)
~~~

Các vị trí trên là sơ đồ khái niệm; một số phần tử có thể vắng mặt hoặc xuất hiện nhiều lần theo schema/profile. Khi xác thực **Web SSO**, không được chỉ nhìn `Conditions` mà bỏ qua `Issuer`, `Destination`, `SubjectConfirmation`, chữ ký, giao dịch `InResponseTo` và chống phát lại.

| Thuộc tính / phần tử | Ý nghĩa | Không nên hiểu nhầm thành |
| --- | --- | --- |
| `Assertion@IssueInstant` | Thời điểm IdP phát hành assertion. | Không tự là hạn hết hiệu lực. |
| `Conditions@NotBefore` | Thời điểm sớm nhất assertion được phép dùng theo điều kiện. | Không phải thời điểm đăng nhập của người dùng. |
| `Conditions@NotOnOrAfter` | Mốc kết thúc **loại trừ** của khoảng hiệu lực assertion. | Không phải ngày hết hạn của tài khoản hay phiên HTTP. |
| `AudienceRestriction/Audience` | Danh sách relying party/SP được phép dùng assertion theo các điều kiện audience. | Không phải danh sách role, nhóm hoặc OAuth scope. |
| `SubjectConfirmationData@NotOnOrAfter` | Hạn độc lập cho cách xác nhận chủ thể, thường là bearer SSO. | Không phải bản sao tùy chọn có thể bỏ qua của `Conditions`. |
| `AuthnStatement@AuthnInstant` | Thời điểm IdP xác thực người dùng. | Không quyết định một mình assertion còn hợp lệ. |
| `AuthnStatement@SessionNotOnOrAfter` | Hạn phiên xác thực do IdP công bố nếu có, theo ngữ nghĩa SAML. | Không tự đặt TTL cho cookie phiên ứng dụng. |

## 2. Cách diễn giải `NotBefore` và `NotOnOrAfter`

Giả sử IdP phát hành:

~~~xml
<saml:Conditions
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    NotBefore="2026-11-07T03:00:00Z"
    NotOnOrAfter="2026-11-07T03:05:00Z">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

Khoảng thời gian hiệu lực là:

~~~text
2026-11-07T03:00:00Z <= thời điểm kiểm tra
                       < 2026-11-07T03:05:00Z
~~~

Nghĩa là **bao gồm** `NotBefore` và **không bao gồm** `NotOnOrAfter`. Nếu không tính dung sai lệch đồng hồ, tại đúng `03:00:00Z` có thể hợp lệ về thời gian; tại đúng `03:05:00Z` đã hết hạn. Thời điểm hiện tại phải được lấy từ đồng hồ đáng tin và so sánh theo cùng mốc UTC/instant, không so sánh chuỗi ngày hay dùng sai múi giờ.

| Thời điểm SP kiểm tra (UTC) | Kết quả chỉ xét `Conditions` về thời gian |
| --- | --- |
| `02:59:59Z` | Không hợp lệ: trước `NotBefore`. |
| `03:00:00Z` | Hợp lệ tại biên đầu. |
| `03:04:59Z` | Còn trong khoảng. |
| `03:05:00Z` | Không hợp lệ: đã chạm `NotOnOrAfter`. |
| `03:10:00Z` | Không hợp lệ: quá hạn. |

**Nếu thiếu mốc:** `NotBefore` và `NotOnOrAfter` là thuộc tính tùy chọn trong schema của `Conditions`; việc thiếu một mốc không tự tạo mốc mặc định. Tuy nhiên, Web SSO profile, cấu hình SP và chính sách bảo mật có thể đòi giới hạn thời gian ngắn; không được suy ra “không có mốc thì assertion dùng vô hạn” vì vẫn còn các giới hạn khác và quy tắc profile.

**`NotOnOrAfter` là mốc thời gian tuyệt đối**, không phải số phút TTL. Đừng tự cộng thêm 5 phút từ `IssueInstant` nếu IdP đã cấp mốc hết hạn cụ thể. Không coi timestamp `IssueInstant` hoặc `AuthnInstant` là phép thay thế kiểm tra Conditions.

### 2.1. Dung sai lệch đồng hồ (*clock skew*)

IdP và SP có thể chênh nhau vài giây. Validator có thể cho phép một khoảng dung sai nhỏ, có cấu hình, để tránh từ chối hợp lệ do đồng hồ không đồng bộ. Nhưng mỗi giây nới biên thời gian cũng mở rộng khoảng có thể chấp nhận assertion.

Cần thực hiện đồng thời:

- Đồng bộ đồng hồ máy chủ bằng NTP hoặc nguồn thời gian đáng tin; ưu tiên sửa đồng hồ sai thay vì tăng clock skew quá rộng.
- Chọn dung sai vừa đủ theo môi trường triển khai, ghi nhận các trường hợp lệch thời gian.
- Giữ thời hạn assertion/SubjectConfirmationData ngắn phù hợp Web SSO, không đổi thành thời gian tồn tại dài để “chống lỗi đăng nhập”.
- Nhớ rằng dung sai ở **`Conditions`** không được làm mất đi bước kiểm tra **SubjectConfirmationData** và các yếu tố replay.

Ví dụ dung sai 60 giây là **quyết định cấu hình minh họa**, không phải giá trị chuẩn bắt buộc của SAML hay khuyến nghị áp dụng cho mọi hệ thống.

## 3. `AudienceRestriction`: assertion dành cho SP nào?

IdP có thể tin cậy nhiều SP nhưng assertion dùng để đăng nhập vào **SP báo cáo** không được đem sang **SP nhân sự**. `AudienceRestriction` ràng buộc bên được phép sử dụng assertion.

Mỗi phần tử `<saml:Audience>` thường chứa **entity ID của SP/Relying Party**. Đó là định danh được khai báo trong cấu hình/metadata SAML; entity ID có thể trông như URL hoặc URN nhưng **không bắt buộc là URL truy cập được**. Nó cũng **không đồng nghĩa** với ACS callback URL.

Ví dụ:

~~~xml
<saml:AudienceRestriction
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Audience>urn:example:sp:reports</saml:Audience>
  <saml:Audience>urn:example:sp:reports-backup</saml:Audience>
</saml:AudienceRestriction>
~~~

Nếu SP hiện tại có entity ID `urn:example:sp:reports`, condition phía trên cho phép về audience. SP `urn:example:sp:payroll` phải từ chối dù assertion còn hạn và chữ ký hợp lệ.

### 3.1. Quy tắc OR trong một restriction, AND giữa các restriction

Đây là điểm dễ bị diễn giải sai trong SAML Core, được làm rõ trong OASIS Errata 05:

- **Trong một `AudienceRestriction`**, nhiều `Audience` kết hợp theo **OR**: SP chỉ cần khớp ít nhất một audience của restriction đó.
- **Nếu có nhiều `AudienceRestriction`**, mỗi restriction phải hợp lệ, kết hợp theo **AND**. SP phải xuất hiện trong ít nhất một audience ở **mỗi** restriction.

Ví dụ **hợp lệ** với SP `reports`:

~~~xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
    <saml:Audience>urn:example:sp:archive</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

Ví dụ **không hợp lệ** với SP `reports`:

~~~xml
<saml:Conditions xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:reports</saml:Audience>
  </saml:AudienceRestriction>
  <saml:AudienceRestriction>
    <saml:Audience>urn:example:sp:payroll</saml:Audience>
  </saml:AudienceRestriction>
</saml:Conditions>
~~~

Restriction thứ nhất hợp lệ cho `reports`, nhưng restriction thứ hai không khớp: kết quả tổng thể **không hợp lệ**. Không được gộp tất cả `Audience` của nhiều restriction thành một danh sách duy nhất rồi chỉ cần khớp một giá trị.

**Trong Web Browser SSO:** SAML Web SSO profile yêu cầu assertion dành cho requester có `AudienceRestriction` tham chiếu SP. Nếu không tìm thấy audience cần thiết, hãy từ chối theo quy tắc profile/chính sách; đừng coi “không bị hạn chế trong Conditions” là đủ cho SSO.

### 3.2. Audience không thay thế authorization

Audience nói **ứng dụng nào được nhận assertion**, không nói user có được xem hóa đơn số 42 hay không. Sau khi xác thực SAML, API/ứng dụng vẫn phải tự kiểm tra role, tenant, ownership và quyền nghiệp vụ. Cũng không thể tin audience lấy từ request do người dùng tự gửi; SP phải so sánh với **entity ID đã cấu hình đáng tin cậy** của registration đang được xử lý.

## 4. `SubjectConfirmationData` đặt giới hạn độc lập

Với bearer SAML Web SSO, IdP thường đưa thêm dữ liệu xác nhận chủ thể:

~~~xml
<saml:SubjectConfirmation
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
  <saml:SubjectConfirmationData
      InResponseTo="_req-456"
      Recipient="https://sp.example.org/login/saml2/sso/corporate"
      NotOnOrAfter="2026-11-07T03:04:00Z"/>
</saml:SubjectConfirmation>
~~~

Các thuộc tính có ý nghĩa khác `Conditions`:

- **`Recipient`**: endpoint nhận assertion/điểm Assertion Consumer Service hợp lệ. So sánh với URL ACS mong đợi theo cấu hình; đây là URL điểm nhận, **không phải entity ID trong AudienceRestriction**.
- **`InResponseTo`**: liên kết phản hồi với `AuthnRequest` do SP tạo trước đó. Trong SP-initiated SSO, SP phải xác minh ID yêu cầu thực sự còn chờ và được gắn với phiên trình duyệt khởi tạo.
- **`NotOnOrAfter` ở SubjectConfirmationData**: hạn được phép dùng cách chứng minh chủ thể bearer này, **độc lập** với hạn Conditions.
- **`Address`** (nếu có): một điều kiện bổ sung trong dữ liệu xác nhận chủ thể; cách xử lý phải theo profile/chính sách, không tự coi IP là biện pháp duy nhất để ngăn replay.

Giả sử `Conditions@NotOnOrAfter` bằng `03:05Z`, còn `SubjectConfirmationData@NotOnOrAfter` bằng `03:04Z`. Tại `03:04:30Z`, điều kiện thời gian assertion vẫn có thể đúng, nhưng bearer confirmation **đã hết hạn**: đăng nhập phải bị từ chối. Không thể “chọn mốc hết hạn muộn hơn” để kéo dài quyền sử dụng.

Một assertion có thể có nhiều `SubjectConfirmation`. Validator cần tìm đường chứng minh chủ thể đáp ứng **đúng profile/binding**, và đồng thời yêu cầu các điều kiện toàn cục của assertion đều hợp lệ. Không được tùy tiện chọn một nhánh rồi bỏ qua issuer, chữ ký hoặc audience.

## 5. Các hạn thời gian không được đánh đồng

| Mốc | Nó mô tả gì? | Kiểm tra / hậu quả |
| --- | --- | --- |
| `Response@IssueInstant` | Lúc IdP tạo response. | Có thể là dữ kiện kiểm tra độ mới theo profile/policy; không thay thế thời hạn assertion. |
| `Assertion@IssueInstant` | Lúc assertion được tạo. | Không tự biến assertion thành hợp lệ cho tới “hết phiên”. |
| `Conditions@NotBefore` | Chưa đến lúc được phép dùng. | Từ chối nếu còn quá sớm ngoài dung sai cấu hình. |
| `Conditions@NotOnOrAfter` | Mốc kết thúc hiệu lực assertion. | Từ chối khi hết hạn. |
| `SubjectConfirmationData@NotOnOrAfter` | Mốc kết thúc bearer confirmation. | Từ chối nếu confirmation đã hết hạn dù Conditions vẫn còn hạn. |
| `AuthnStatement@AuthnInstant` | Thời điểm người dùng xác thực tại IdP. | Có thể dùng cho yêu cầu “đăng nhập lại gần đây”, không thay thế Conditions. |
| `AuthnStatement@SessionNotOnOrAfter` | Giới hạn phiên xác thực liên quan nếu có. | Cần xử lý theo giao thức/chính sách; không tự đồng bộ TTL của cookie phiên SP. |
| HTTP session cookie của SP | Phiên ứng dụng sau khi SAML login thành công. | Có idle/absolute timeout, logout và chính sách vòng đời **riêng**. |

Ví dụ SP thiết lập cookie phiên sống 30 phút sau khi chấp nhận assertion, trong khi assertion chỉ có hiệu lực để **trao đổi đăng nhập** trong vài phút. Assertion hết hạn lúc `03:05Z` không đồng nghĩa phiên ứng dụng đã phát phải logout ngay đúng `03:05Z`, trừ khi chính sách ứng dụng quy định như vậy. Ngược lại, assertion chưa hết hạn cũng **không được phép tái dùng vô hạn**; callback phải kiểm tra transaction và chống replay.

## 6. Luồng xác minh bên nhận — điều kiện cần kết hợp

Một SP triển khai SAML an toàn nên dùng **thư viện SAML/OpenSAML được tích hợp chuẩn**, kiểm tra đúng dữ liệu được bảo vệ bởi chữ ký XML. Một chuỗi kiểm tra có thể được trình bày về mặt khái niệm như sau:

1. **Nạp registration đáng tin:** xác định IdP và SP entity ID từ cấu hình/metadata đã tin cậy; không chấp nhận entity ID hoặc chứng thư ký tùy ý từ HTTP request.
2. **Kiểm tra response/binding:** phân tích XML an toàn, xác minh chữ ký của response/assertion theo profile và bảo đảm assertion đem sử dụng được bảo vệ bởi chữ ký đã xác minh; kiểm tra issuer và `Destination`.
3. **Kiểm tra tương quan:** với SP-initiated, `InResponseTo` phải khớp `AuthnRequest` đang chờ của chính giao dịch/phiên trình duyệt. Kiểm tra `Recipient` của bearer confirmation.
4. **Kiểm tra Conditions:** áp dụng `NotBefore`, `NotOnOrAfter`, mọi `AudienceRestriction`, và các condition bổ sung như `OneTimeUse`/`ProxyRestriction` nếu có theo quy tắc được hỗ trợ. Điều kiện không hiểu/không thể đánh giá an toàn thì không được mặc nhiên bỏ qua.
5. **Kiểm tra subject confirmation:** có phương thức chứng minh chủ thể hợp lệ, đúng người nhận, đúng giao dịch và còn trong hạn sử dụng của confirmation.
6. **Chống replay:** response/assertion và transaction đã dùng không được chấp nhận lặp lại; cache chống replay cần tồn tại đủ lâu theo thời hạn và dung sai đã chấp nhận. Hãy tiêu thụ transaction theo cách an toàn trước callback đồng thời.
7. **Phát hành phiên ứng dụng:** chỉ sau khi mọi điều kiện đạt, tạo Spring Security `Authentication` và phiên SP; tiếp tục kiểm tra authorization nghiệp vụ độc lập.

Điểm cốt lõi là **các giới hạn phải được đáp ứng cùng nhau**. Chữ ký đúng + audience đúng + Conditions còn hiệu lực **vẫn chưa đủ** nếu bearer confirmation đã hết hạn hoặc `InResponseTo` không khớp.

### 6.1. Ví dụ “điều kiện đúng nhưng đăng nhập vẫn thất bại”

Giả sử:

- SP có `entityID = urn:example:sp:reports`, `ACS = https://sp.example.org/login/saml2/sso/corporate`.
- Assertion có `Conditions = [03:00Z, 03:05Z)`; `AudienceRestriction` chứa đúng entity ID.
- Bearer `SubjectConfirmationData@NotOnOrAfter = 03:04Z`, `Recipient` là ACS trên.
- `InResponseTo = _req-456` thuộc request còn chờ của đúng phiên.

| Trường hợp | Phân tích | Kết quả |
| --- | --- | --- |
| Nhận lúc `03:03Z`, tất cả điều kiện khác đều đúng. | Conditions, audience và bearer confirmation hợp lệ. | Có thể chấp nhận sau khi xác minh đầy đủ chữ ký, issuer, replay, v.v. |
| Nhận lúc `03:04:30Z`. | Conditions còn hạn nhưng bearer confirmation đã quá hạn. | **Từ chối.** |
| Nhận lúc `03:05Z`. | Chạm `Conditions@NotOnOrAfter`. | **Từ chối** (nếu không xét dung sai đồng hồ). |
| Nhận lúc `03:03Z`, audience chỉ có `urn:example:sp:payroll`. | Assertion dành SP khác. | **Từ chối.** |
| Nhận lúc `03:03Z`, `InResponseTo` không khớp yêu cầu đang chờ. | Không gắn được callback với giao dịch trước. | **Từ chối.** |
| Nhận lại response đã dùng một lần. | Phát lại assertion hoặc transaction. | **Từ chối.** |

## 7. Java 17: minh họa biên thời gian và logic audience

Chương trình dưới đây là **mô hình học tập cho hai điều kiện**, không phải SAML validator thực tế. Nó chưa kiểm tra chữ ký XML, issuer, recipient, subject confirmation, clock skew, các loại condition khác hoặc replay. Trong production, sử dụng thư viện xác thực SAML.

Tệp `SamlConditionsDemo.java`:

~~~java
import java.time.Instant;
import java.util.List;

public class SamlConditionsDemo {
    static boolean validWindow(Instant now, Instant notBefore,
                               Instant notOnOrAfter) {
        return !now.isBefore(notBefore)
                && now.isBefore(notOnOrAfter);
    }

    static boolean audienceAllowed(
            String expectedEntityId, List<List<String>> restrictions) {
        // Với Web SSO demo này: yêu cầu ít nhất một restriction.
        // OR trong mỗi danh sách; AND giữa các danh sách.
        return !restrictions.isEmpty()
                && restrictions.stream().allMatch(
                    audiences -> audiences.contains(expectedEntityId));
    }

    public static void main(String[] args) {
        Instant from = Instant.parse("2026-11-07T03:00:00Z");
        Instant until = Instant.parse("2026-11-07T03:05:00Z");
        String sp = "urn:example:sp:reports";

        System.out.println(validWindow(from, from, until));
        System.out.println(validWindow(until, from, until));

        System.out.println(audienceAllowed(sp, List.of(
                List.of(sp, "urn:example:sp:archive"))));

        System.out.println(audienceAllowed(sp, List.of(
                List.of(sp),
                List.of("urn:example:sp:payroll"))));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac SamlConditionsDemo.java
java SamlConditionsDemo
~~~

Kết quả chính xác:

~~~text
true
false
true
false
~~~

Hai dòng đầu xác nhận khoảng **[NotBefore, NotOnOrAfter)**. Hai dòng sau xác nhận audience **OR trong một restriction** và **AND giữa nhiều restriction**. Phần mềm thật phải dùng parser/validator SAML đáng tin cậy và đối chiếu entity ID từ registration đã cấu hình.

## 8. Cấu hình trong Spring Security SAML 2.0 Login

Với Spring Boot Servlet có dependency `spring-boot-starter-security` và `spring-security-saml2-service-provider` (thêm kho thư viện phù hợp với phiên bản dự án), sử dụng cấu hình SAML Login và metadata của IdP thay vì tự parse XML trong controller.

Ví dụ cấu hình `SecurityFilterChain` trong một dự án Spring Boot:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là mã cấu hình trong dự án, **không biên dịch độc lập** chỉ bằng `javac`. Ngoài đoạn mã trên, phải có `RelyingPartyRegistration` hợp lệ: SP entity ID, ACS, IdP entity ID/metadata, chứng thư xác minh chữ ký, thuật toán/binding và cấu hình khóa theo nhu cầu. Cấu hình sai entity ID khiến audience hợp lệ bị từ chối; “sửa” bằng cách tắt AudienceRestriction validation sẽ phá ranh giới tin cậy.

Spring Security sử dụng OpenSAML để xác thực SAML response và assertion, với các validator cho signature, issuer/destination, Conditions, audience, subject confirmation theo phiên bản/provider được cấu hình. Những thành phần như `OpenSaml4AuthenticationProvider`, `OpenSaml5AuthenticationProvider` và API tùy biến validator khác nhau giữa các đời; **đối chiếu tài liệu đúng bản Spring Security mà dự án đang chạy**.

Khi cần dung sai đồng hồ hoặc xác minh condition bổ sung, cấu hình ở lớp validator được hỗ trợ và **giữ lại các validator mặc định**. Không thay toàn bộ validator bằng một hàm chỉ kiểm tra timestamp hoặc chỉ kiểm tra chữ ký. Không dùng việc “parse được XML” làm bằng chứng assertion đã xác thực.

### 8.1. Debug an toàn khi SAML login bị từ chối

Nếu người dùng báo lỗi “SAML token expired” hoặc “invalid audience”, kiểm tra theo thứ tự có căn cứ:

1. So sánh thời gian UTC của IdP và SP, `NotBefore`, `NotOnOrAfter` của **Conditions** và **SubjectConfirmationData**; kiểm tra dung sai clock skew đã cấu hình.
2. Lấy **SP entity ID dự kiến trong RelyingPartyRegistration**, so với từng `AudienceRestriction`, không so theo URL thanh địa chỉ trình duyệt.
3. Kiểm tra ACS/Recipient/Destination qua HTTPS, reverse proxy và public base URL; đây là vấn đề khác với audience.
4. Kiểm tra `InResponseTo`, transaction còn chờ, session cookie và replay, nhất là khi IdP → SP dùng cross-site POST.
5. Kiểm tra issuer, metadata và chứng thư ký đúng IdP; tránh thay metadata/khóa tin cậy theo giá trị người dùng gửi.
6. Ghi log **loại lỗi, thời điểm, registration ID và ID giao dịch đã xử lý an toàn**. Tránh đưa nguyên assertion, NameID, thuộc tính cá nhân, cookie hoặc XML nhạy cảm vào log/ticket.

## 9. Các nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Chữ ký hợp lệ nên assertion được dùng mãi.” | Chữ ký chứng minh tính toàn vẹn/nguồn ký; thời gian, audience, subject confirmation và replay vẫn phải kiểm tra. |
| “`NotOnOrAfter` bao gồm đúng giây kết thúc.” | Khoảng hiệu lực có biên phải **loại trừ**, trước khi áp dụng dung sai đồng hồ đã kiểm soát. |
| “`IssueInstant` = hạn hết hiệu lực.” | Là thời điểm phát hành, không thay `ConditionsNotOnOrAfter`. |
| “Một `Audience` khớp ở bất kỳ `AudienceRestriction` nào là đủ.” | Mỗi restriction phải được đáp ứng độc lập: **AND giữa restriction**, **OR trong restriction**. |
| “Audience chính là URL ACS.” | Audience thường là **SP entity ID**; ACS là URL nhận response/Recipient. |
| “Conditions còn hạn nên có thể bỏ qua SubjectConfirmationData.” | Bearer confirmation có hạn và yêu cầu recipient/giao dịch độc lập. |
| “Hết hạn assertion là phải xóa tức thì cookie session.” | TTL phiên ứng dụng do SP quản lý riêng; cần thiết kế session/logout theo chính sách. |
| “Một assertion hết hạn có thể chấp nhận khi tăng clock skew thật lớn.” | Đồng bộ thời gian và dùng dung sai nhỏ, có giới hạn; không nới để che lỗi cấu hình. |
| “IdP-initiated và SP-initiated có cùng InResponseTo.” | IdP-initiated thường không có request gốc; cần chính sách riêng, không dùng làm fallback tùy tiện. |
| “Spring Security tự quyết định quyền vào mọi tài nguyên.” | SAML login cung cấp danh tính; authorization theo nghiệp vụ/tenant vẫn phải triển khai. |

## 10. Tự kiểm tra hiểu biết

1. Assertion có `NotBefore=03:00Z` và `NotOnOrAfter=03:05Z`. Tại `03:05:00Z` có hợp lệ không? **Không**, khi chưa tính dung sai đồng hồ.
2. Assertion có `AudienceRestriction` chứa `reports` và `archive`, SP là `reports`. Có qua điều kiện audience không? **Có**, nếu các điều kiện khác hợp lệ.
3. Assertion có **hai** `AudienceRestriction`: cái đầu chứa `reports`, cái sau chỉ chứa `payroll`. SP `reports` có qua không? **Không**, vì restriction thứ hai không hợp lệ.
4. Conditions còn hạn đến `03:05Z`, bearer confirmation hết hạn `03:04Z`. Đến `03:04:30Z` dùng được không? **Không**, do bearer confirmation hết hạn.
5. Audience, signature, thời hạn đều hợp lệ nhưng `InResponseTo` thuộc phiên khác. SP-initiated login chấp nhận không? **Không**, vì không thuộc giao dịch yêu cầu ban đầu.
6. Khi SAML login thành công, ứng dụng có thể bỏ kiểm tra quyền bản ghi không? **Không**, xác thực và authorization là hai bước khác nhau.

## Tài liệu tham khảo

- [OASIS SAML V2.0 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Errata 05 — AudienceRestriction AND/OR](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML 2.0 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Producing SAML 2.0 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
