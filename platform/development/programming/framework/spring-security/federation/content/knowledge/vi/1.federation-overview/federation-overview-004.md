# Phân biệt xác thực tập trung, phân quyền và cấp phát tài khoản

Trong một hệ thống *federation*, nhiều ứng dụng có thể tin cậy cùng một nhà cung cấp danh tính (Identity Provider, IdP). Tuy vậy, **đăng nhập thành công**, **được phép thực hiện thao tác** và **có tài khoản đang hoạt động trong ứng dụng** là ba vấn đề khác nhau. Một thiết kế an toàn cần giải quyết cả ba, đồng thời chỉ rõ hệ thống nào chịu trách nhiệm cho từng quyết định.

## 1. Ba câu hỏi cốt lõi

| Khái niệm | Câu hỏi cần trả lời | Trách nhiệm chính | Kết quả điển hình |
| --- | --- | --- | --- |
| **Xác thực tập trung** (*centralized authentication*) | **Người dùng là ai?** Họ đã chứng minh danh tính với ai? | IdP xác minh thông tin đăng nhập, MFA và các chính sách đăng nhập; ứng dụng xác minh phản hồi IdP. | Danh tính đã xác thực, thông tin phiên đăng nhập hoặc các token hợp lệ. |
| **Phân quyền** (*authorization*) | **Danh tính đó được làm gì, với tài nguyên nào, trong ngữ cảnh nào?** | Ứng dụng/API bảo vệ tài nguyên quyết định theo chính sách nghiệp vụ; có thể tham khảo vai trò/nhóm do IdP cấp. | Cho phép hoặc từ chối thao tác cụ thể. |
| **Cấp phát tài khoản** (*provisioning*) | **Tài khoản, hồ sơ, nhóm và trạng thái hoạt động trong ứng dụng được tạo, cập nhật, thu hồi ra sao?** | Hệ thống quản lý vòng đời danh tính, ứng dụng đích hoặc cả hai theo hợp đồng tích hợp. | Bản ghi tài khoản/nhóm/quyền được đồng bộ, kích hoạt hoặc vô hiệu hóa. |

Ba cơ chế có thể cùng tham gia một lần truy cập nhưng **không thay thế nhau**:

- Một người đăng nhập SSO thành công vẫn có thể nhận **403 Forbidden** vì không được xem báo cáo tài chính.
- Một người có tài khoản ứng dụng đã được SCIM tạo trước vẫn phải xác thực khi truy cập.
- Một người bị vô hiệu hóa tại IdP có thể vẫn còn phiên ứng dụng hoặc access token chưa hết hạn, nếu hệ thống chưa xử lý thu hồi tương ứng.

## 2. Xác thực tập trung: tin cậy danh tính qua federation

**Mục tiêu:** người dùng xác thực tại IdP (chẳng hạn hệ thống danh tính của tổ chức), rồi nhiều ứng dụng có thể sử dụng kết quả xác thực đó theo quan hệ tin cậy đã cấu hình. Ứng dụng thường không phải lưu hoặc kiểm tra mật khẩu của nhân viên.

**Các thành phần:**

- **Người dùng / trình duyệt:** khởi tạo truy cập.
- **IdP / OpenID Provider:** thực hiện đăng nhập, MFA, chính sách rủi ro; phát hành thông tin xác thực phù hợp.
- **Ứng dụng tin cậy (Relying Party/OIDC Client hoặc Service Provider/SAML):** xác minh kết quả do IdP phát hành, xác định danh tính người dùng và tạo phiên riêng nếu cần.
- **Ứng dụng/API tài nguyên (Resource Server):** xác minh access token phù hợp cho API của mình.

Với **OpenID Connect (OIDC)**, ứng dụng web thường dùng luồng *Authorization Code* qua IdP. IdP trả về mã ủy quyền; ứng dụng đổi mã theo giao thức và xác minh **ID token** dành cho client đó. ID token mô tả sự kiện/danh tính xác thực; nó **không phải** vé truy cập chung cho mọi API. Với **SAML 2.0**, Service Provider kiểm tra assertion theo quan hệ tin cậy đã cấu hình.

Trước khi tin phản hồi OIDC, client phải sử dụng cơ chế xác minh của thư viện: chữ ký và khóa tin cậy, issuer (`iss`), audience/client ID (`aud`), thời hạn (`exp`), trạng thái yêu cầu (`state`), `nonce` khi áp dụng, và các ràng buộc giao thức. Đừng tự giải mã JWT rồi coi các claim chưa xác minh là danh tính thật.

**SSO (Single Sign-On)** là trải nghiệm nhiều ứng dụng có thể tái sử dụng phiên đăng nhập tại IdP. Federation là quan hệ tin cậy/trao đổi danh tính giữa các bên; SSO là một kết quả sử dụng phổ biến, không đồng nghĩa với phân quyền hay đồng bộ tài khoản. Đăng xuất một ứng dụng cũng không mặc nhiên đăng xuất mọi phiên ở IdP và ứng dụng khác.

**Định danh ổn định:** liên kết tài khoản dựa trên cặp **(`iss`, `sub`)** trong OIDC, có xét tenant và chính sách liên kết tài khoản của ứng dụng. Email, tên hiển thị hoặc username có thể đổi hoặc được tái sử dụng, nên không nên là khóa danh tính duy nhất để tự động gộp người dùng từ các IdP khác nhau.

## 3. Phân quyền: quyền tại tài nguyên phải được kiểm tra riêng

**Authentication** cho biết ai đang gọi; **authorization** quyết định lời gọi đó có được phép hay không. Ví dụ, tài khoản `lan` đã đăng nhập qua IdP nhưng chỉ có quyền đọc hóa đơn thuộc công ty A. Yêu cầu sửa hóa đơn của công ty B phải bị từ chối dù token còn hiệu lực.

Các nguồn dữ liệu thường dùng để ra quyết định:

- **Role (RBAC):** `REPORT_VIEWER`, `ORDER_ADMIN`; vai trò phải có ý nghĩa và phạm vi rõ ràng.
- **Thuộc tính/ngữ cảnh (ABAC):** phòng ban, mức phân loại dữ liệu, giờ truy cập, tenant, trạng thái tài khoản.
- **Quan hệ/tài nguyên:** người tạo đơn hàng, thành viên dự án, quyền sở hữu bản ghi, ACL.
- **Scope OAuth 2.0:** phạm vi quyền mà access token được cấp, ví dụ `reports.read`. Scope không tự động chứng minh người dùng có quyền với **mọi** bản ghi hay tenant.

**Ai là nơi quyết định?** IdP có thể quản lý group hoặc phát hành claim, nhưng API/ứng dụng sở hữu tài nguyên vẫn phải định nghĩa và thực thi chính sách. Nếu dùng nhóm từ IdP để cấp role nội bộ, cần quy tắc ánh xạ minh bạch, giới hạn tenant, kiểm soát nguồn claim và thời điểm cập nhật. Spring Security không tự hiểu claim tùy ý như `groups` thành quyền nghiệp vụ.

**Phân biệt mã phản hồi:** API thường trả **401 Unauthorized** khi yêu cầu thiếu/chưa có xác thực hợp lệ và **403 Forbidden** khi danh tính đã xác thực nhưng thiếu quyền. Ứng dụng web có thể chuyển hướng đến IdP thay vì trả 401 trực tiếp.

Ví dụ hai cấp kiểm tra cho `GET /api/invoices/42`:

1. **Cấp endpoint:** có access token hợp lệ dành cho API này, có scope `invoices.read`.
2. **Cấp bản ghi:** hóa đơn 42 thuộc tenant mà người gọi được phép truy cập và người gọi có quan hệ/quyền xem phù hợp.

Chỉ làm bước 1 sẽ để lọt lỗi truy cập chéo tenant hoặc lỗi IDOR/BOLA.

## 4. Cấp phát tài khoản: quản lý vòng đời, không phải đăng nhập

**Provisioning** bao gồm khởi tạo tài khoản, hồ sơ, nhóm, trạng thái hiệu lực và các thay đổi trong suốt vòng đời người dùng. Tùy ứng dụng, nó còn gồm tạo chỗ làm việc, giấy phép hoặc quan hệ với tenant. Đây là luồng quản trị dữ liệu, có thể hoạt động **trước** khi người dùng từng đăng nhập.

Ba cách thường gặp:

| Cách thực hiện | Thời điểm | Ưu điểm | Giới hạn cần xử lý |
| --- | --- | --- | --- |
| **Quản trị thủ công / mời người dùng** | Quản trị viên chủ động tạo/gán quyền. | Dễ kiểm soát phê duyệt cho tổ chức nhỏ. | Dễ sót thay đổi và thu hồi khi số người dùng tăng. |
| **Just-in-Time (JIT) provisioning** | Tạo hoặc liên kết tài khoản khi lần đăng nhập hợp lệ đầu tiên diễn ra. | Giảm thao tác tạo trước, phù hợp onboarding đơn giản. | Không tự giải quyết đầy đủ đổi nhóm và offboarding nếu không xây thêm đồng bộ. |
| **Đồng bộ tự động, thường qua SCIM 2.0** | Hệ thống danh tính đẩy tạo/sửa/vô hiệu hóa theo sự kiện vòng đời. | Có thể chuẩn bị tài khoản trước đăng nhập, cập nhật và thu hồi tập trung hơn. | Phải thiết kế xác thực API SCIM, mapping, idempotency, đồng bộ lỗi và độ trễ. |

**SCIM 2.0** (RFC 7643/7644) chuẩn hóa lược đồ `User`, `Group` và giao diện HTTP như `/Users`, `/Groups`, với các thao tác `POST`, `GET`, `PUT`, `PATCH`, `DELETE`. Ví dụ, hệ thống nguồn có thể gửi cập nhật `active: false` để ứng dụng đích vô hiệu hóa tài khoản; ngữ nghĩa thu hồi, xóa hay bảo lưu dữ liệu phải được thống nhất giữa hai bên và tuân thủ hỗ trợ thực tế của nhà cung cấp.

Đừng đánh đồng ba thứ:

- **Provisioned account:** có bản ghi người dùng trong ứng dụng.
- **Authenticated session:** người dùng đã xác thực cho một phiên hiện tại.
- **Authorized access:** phiên hoặc yêu cầu đó vượt qua chính sách của đúng tài nguyên.

Tài khoản đã được tạo không tự đăng nhập; đăng nhập thành công không tự có quyền quản trị; một quyền đã tồn tại trong database không cho phép bỏ qua kiểm tra phiên và trạng thái tài khoản.

## 5. Luồng phối hợp từ onboarding đến truy cập

~~~text
Hệ thống nhân sự/Directory
        |
        | người mới / chuyển nhóm / nghỉ việc
        v
Hệ thống quản lý danh tính + IdP -----------+
        |                                   |
        | SCIM (tạo/sửa/disable)            | OIDC/SAML (đăng nhập)
        v                                   v
Cơ sở dữ liệu tài khoản ứng dụng <---> Ứng dụng web / API
         (trạng thái, tenant, role)          |
                                            | kiểm tra quyền
                                            v
                                     Tài nguyên nghiệp vụ
~~~

Các mũi tên biểu diễn **những kênh có mục đích khác nhau**. SCIM cập nhật dữ liệu danh tính/vòng đời; OIDC/SAML chuyển bằng chứng xác thực; lớp authorization kiểm tra thao tác trên tài nguyên. Không bắt buộc mọi hệ thống có SCIM, nhưng thiếu SCIM thì vẫn phải có phương án vòng đời tương đương.

**Tình huống cụ thể:** Lan mới vào công ty và cần xem báo cáo của dự án Alpha.

1. **Onboarding:** bộ phận nhân sự kích hoạt nhân sự; hệ thống danh tính tạo user ở IdP. Nếu tích hợp SCIM, ứng dụng nhận sự kiện tạo/liên kết tài khoản, gán tenant và quyền tối thiểu ban đầu. Nếu dùng JIT, ứng dụng tạo user ở lần đăng nhập đầu tiên **sau** khi xác minh danh tính và kiểm tra chính sách cho phép tự cấp phát.
2. **Đăng nhập:** Lan mở ứng dụng; `oauth2Login` chuyển đến IdP. IdP xác thực (có thể yêu cầu MFA); ứng dụng xác minh ID token và ánh xạ `iss + sub` đến tài khoản nội bộ. Kết quả là Lan có phiên đăng nhập, chưa có nghĩa Lan được xem mọi báo cáo.
3. **Truy cập:** Lan gọi API báo cáo. API kiểm tra access token đúng issuer/audience/hạn dùng và kiểm tra chính sách `reports.read` **cùng** tenant/dự án. Nếu Lan không thuộc Alpha thì từ chối dù đã SSO.
4. **Chuyển bộ phận:** hệ thống nguồn cập nhật group/role qua SCIM, đồng bộ hoặc cơ chế phê duyệt. Chính sách phân quyền trong ứng dụng cần phản ánh thay đổi; claim trong token cũ có thể còn giá trị cũ cho đến khi token được thay mới.
5. **Nghỉ việc:** IdP chặn đăng nhập mới; luồng provisioning vô hiệu hóa tài khoản ứng dụng; hệ thống cần xử lý phiên đang hoạt động, refresh/access token, quyền nền và các tích hợp khác theo yêu cầu thu hồi. Chỉ vô hiệu hóa tại một nơi chưa chắc cắt ngay mọi truy cập đã cấp trước đó.

**Bất biến quan trọng:** khi xử lý một yêu cầu, hệ thống phải kiểm tra cả **danh tính đáng tin cậy + trạng thái tài khoản hợp lệ + quyền đối với tài nguyên thực tế**; đường đi chính xác phụ thuộc ứng dụng sử dụng session, bearer token và mô hình policy nào.

## 6. Đặt đúng trách nhiệm trong Spring Security

Spring Security cung cấp cơ chế xác thực tích hợp OIDC/OAuth 2.0, xác minh token và thực thi authorization. Việc quản lý user nội bộ, SCIM, quy trình phê duyệt và đồng bộ vòng đời là phần ứng dụng/hệ thống danh tính phải triển khai theo thiết kế; không tự xuất hiện chỉ vì bật `oauth2Login`.

### 6.1. Ứng dụng web Servlet đăng nhập bằng OIDC

Ví dụ cấu hình tối thiểu cho một ứng dụng Spring Boot có dependency `spring-boot-starter-security` và `spring-boot-starter-oauth2-client`. Đây là cấu hình ứng dụng, **không phải chương trình Java độc lập** dùng `javac` ngoài dự án Spring Boot.

Tệp `src/main/java/example/federation/FederationSecurityConfig.java`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class FederationSecurityConfig {
    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Tệp `src/main/resources/application.yml` (endpoint và client là **ví dụ cấu hình**, thay bằng thông số của IdP thực tế):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          corporate:
            issuer-uri: https://idp.example.org/realms/corporate
~~~

Với cấu hình này, yêu cầu chưa có phiên đến đường dẫn bảo vệ sẽ khởi động đăng nhập qua IdP. Sau khi người dùng được xác thực, lớp web vẫn phải kiểm tra quyền từng thao tác, ví dụ qua `authorizeHttpRequests`, `@PreAuthorize` và một service kiểm tra quyền trên bản ghi. `@EnableMethodSecurity` bật method-level authorization; quyền từ nhóm/role doanh nghiệp cần được **ánh xạ có chủ đích** vào Spring `GrantedAuthority`, không mặc nhiên có sẵn chỉ vì ID token chứa group.

### 6.2. API riêng nhận JWT bearer access token

Với một ứng dụng **Resource Server** riêng, dùng `spring-boot-starter-oauth2-resource-server` và cấu hình ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/corporate
          audiences: https://reports-api.example.org
~~~

Spring Security Resource Server sẽ xác minh chữ ký JWT và những claim thời gian/issuer theo cấu hình; audience phải phù hợp API nhận token. Trong ứng dụng API này, khi mapping scope mặc định được dùng, scope `reports.read` trở thành authority `SCOPE_reports.read`. Một điều kiện minh họa:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportDto getReport(String reportId) {
    return reportService.loadIfAllowedForCurrentUser(reportId);
}
~~~

Đoạn method trên là **mã minh họa trong service**, không thể biên dịch độc lập vì phụ thuộc `ReportDto`, `reportService` và chính sách ứng dụng. `loadIfAllowedForCurrentUser` phải kiểm tra quyền trên **reportId, tenant và người gọi**, tránh hiểu nhầm rằng có scope là được xem tất cả báo cáo. Khi sử dụng cả login bằng session và bearer token trong cùng một ứng dụng, cần cấu hình chain, matcher và chính sách phù hợp với từng loại request; hai ví dụ trên đại diện cho hai kiểu ứng dụng khác nhau.

### 6.3. Phần provisioning và authorization nghiệp vụ nằm ở đâu?

- **OIDC login:** cấu hình `oauth2Login`; ánh xạ danh tính ngoài (`issuer + subject`) đến user nội bộ; từ chối nếu user bị khóa hoặc không thỏa chính sách cấp phát.
- **JWT API:** cấu hình `oauth2ResourceServer`; xác minh issuer, audience, chữ ký, thời hạn; ánh xạ scope/claim đáng tin vào authority.
- **Authorization nghiệp vụ:** triển khai ở tầng API/service/repository, kiểm tra tenant, ownership, quyền thao tác, trạng thái nghiệp vụ, áp dụng nguyên tắc *deny by default* và *least privilege*.
- **Provisioning:** tích hợp SCIM client/server, webhook, đồng bộ directory hoặc JIT theo nhu cầu; xử lý tạo/cập nhật/disable có idempotency, audit, giới hạn quyền API và đối soát khi mất đồng bộ.

Nếu hệ thống dùng group claim để cấp vai trò nội bộ, cần quy định rõ bên nào là nguồn dữ liệu có thẩm quyền, quan hệ group → role → resource, độ trễ đồng bộ và cách thu hồi. Đừng nhận role chỉ từ request body, query parameter hay JWT của issuer chưa được tin cậy.

## 7. Những nhầm lẫn dễ gây lỗ hổng

| Nhầm lẫn | Vì sao sai / cách làm đúng |
| --- | --- |
| “Đã SSO nghĩa là có quyền admin.” | SSO chỉ xác thực danh tính. Admin là quyền cần được cấp và kiểm tra riêng. |
| “OAuth 2.0 luôn là chuẩn xác thực người dùng.” | OAuth 2.0 chủ yếu là khung ủy quyền truy cập; dùng OIDC cho xác thực người dùng với ID token và quy trình xác minh chuẩn. |
| “ID token dùng gọi mọi API.” | ID token dành cho client; API yêu cầu access token dành đúng resource/audience. |
| “Có scope `read` là được xem mọi bản ghi.” | Phải kiểm tra quyền theo owner, tenant, project và đối tượng cụ thể. |
| “Mỗi lần login đều tự tạo tài khoản và cấp role mặc định rộng.” | JIT cần kiểm tra điều kiện cho phép, tạo quyền tối thiểu và ghi audit; có thể yêu cầu duyệt. |
| “SCIM đã tạo tài khoản thì không cần đăng nhập.” | SCIM xử lý vòng đời; yêu cầu truy cập vẫn cần xác thực/authorization. |
| “Xóa người dùng ở IdP sẽ lập tức chặn mọi phiên cũ.” | Phải xử lý trạng thái app, phiên, refresh/access token, TTL và cơ chế thu hồi tương ứng. |
| “Có thể dùng email làm ID duy nhất cho federation.” | Email có thể đổi hoặc trùng giữa tenant/IdP; ưu tiên `iss + sub` và mapping rõ ràng. |
| “Group claim tự trở thành Spring role.” | Cần cấu hình chuyển đổi claim → authority và xác định phạm vi/nguồn tin cậy. |
| “403 và 401 là một.” | 401 thường là thiếu xác thực hợp lệ; 403 là đã xác thực nhưng không được phép. |

## 8. Kiểm tra thiết kế bằng tình huống

**Tình huống A — User đăng nhập đúng nhưng chưa có tài khoản ứng dụng:** Nếu cho phép JIT, tạo/liên kết tài khoản sau khi xác minh IdP và kiểm tra policy, với quyền tối thiểu; nếu yêu cầu provisioning trước/duyệt trước thì từ chối truy cập cho đến khi tài khoản hợp lệ. **Không tự suy ra quyền từ việc đăng nhập.**

**Tình huống B — Nhân viên chuyển từ nhóm A sang B:** IdP/directory hoặc SCIM cập nhật thuộc tính/nhóm; ứng dụng tính lại quyền và giải quyết độ trễ của token/phiên. Role A không nên tồn tại vô hạn nếu đã bị thu hồi tại nguồn quản trị.

**Tình huống C — JWT hợp lệ nhưng gọi report của tenant khác:** Resource Server xác minh token thành công, nhưng tầng authorization nghiệp vụ phải từ chối truy cập vì sai tenant. Xác minh chữ ký chỉ là điều kiện cần.

**Tình huống D — Nhân viên nghỉ việc, access token còn 20 phút:** Thiết kế phải xác định mức thu hồi mong muốn: kiểm tra trạng thái tài khoản trên các request nhạy cảm, TTL ngắn, thu hồi phiên/refresh token, cơ chế introspection/revocation hoặc event cập nhật khi phù hợp. Không hứa hẹn “logout toàn hệ thống ngay” nếu chưa có cơ chế thực tế.

### Tự kiểm cuối bài

1. **Ai xác nhận “Lan là ai”?** IdP và ứng dụng tin cậy xác minh kết quả giao thức.
2. **Ai quyết định “Lan được sửa hóa đơn số 42 không”?** Ứng dụng/API sở hữu hóa đơn, theo policy và ngữ cảnh thật.
3. **Ai tạo hoặc vô hiệu hóa hồ sơ Lan trong ứng dụng?** Luồng provisioning đã chọn (SCIM/JIT/quản trị/đồng bộ), độc lập với việc Lan có đang đăng nhập hay không.
4. **Vì sao ba cơ chế cần phối hợp?** Vì danh tính hợp lệ không suy ra quyền tài nguyên và không bảo đảm trạng thái vòng đời đã được đồng bộ.

## Tài liệu tham khảo

- [Spring Security: OAuth 2.0 Client, Login, Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Spring Security: JWT Resource Server và xác minh token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 7643 — SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643)
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644)
