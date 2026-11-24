# Remember me treatment — Xử lý remember-me khi khôi phục tài khoản

## 1. Vì sao recovery phải xử lý remember-me?

Một người dùng vừa đặt lại mật khẩu sau khi nghi ngờ tài khoản bị chiếm đoạt. Hệ thống thông báo khôi phục thành công và đóng phiên đang sử dụng. Tuy nhiên, trình duyệt của kẻ tấn công vẫn giữ một remember-me cookie hợp lệ. Ở lần truy cập tiếp theo, cookie đó tạo lại một phiên đăng nhập mà không yêu cầu nhập mật khẩu mới.

Trong tình huống này, cập nhật mật khẩu đã thành công nhưng việc loại bỏ đường quay lại tài khoản chưa hoàn tất. Remember-me là một dạng credential có tuổi thọ riêng và có thể tồn tại ngoài vòng đời của session hiện tại.

Đối với `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, xử lý remember-me cần gắn với các luồng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là cho phép chủ tài khoản khôi phục quyền truy cập trong khi hạn chế credential cũ tiếp tục được dùng để chiếm lại tài khoản.

Một thiết kế đầy đủ phải trả lời bốn câu hỏi:

- Có cho phép remember-me tham gia nhận diện người đang yêu cầu recovery không?
- Khi nào credential remember-me của tài khoản đích bị thu hồi?
- Những session đã được tạo trước đó được xử lý thế nào?
- Sau khôi phục, điều kiện nào cho phép phát hành remember-me mới?

Bài học sử dụng Spring Security Servlet với các API `SecurityFilterChain` và `jakarta.servlet`. Những chi tiết implementation được đối chiếu với mã nguồn nhánh Spring Security `7.0.x`; khi áp dụng vào dự án cần kiểm tra phiên bản dependency thực tế. Các đường dẫn, thời hạn, account ID, epoch và tên sự kiện trong ví dụ là thiết kế minh họa, không phải cấu hình mặc định hoặc bằng chứng về hệ thống đang chạy.

## 2. Phân biệt các loại trạng thái xác thực

Không dùng từ “token” chung cho mọi đối tượng. Khả năng thu hồi và nơi kiểm tra của mỗi loại khác nhau.

| Đối tượng | Vai trò | Điều cần lưu ý khi recovery |
| --- | --- | --- |
| Recovery token hoặc recovery grant | Cho phép thực hiện một hành động khôi phục cụ thể sau các kiểm tra cần thiết | Cần ràng buộc tài khoản, mục đích, thời hạn và điều kiện sử dụng một lần |
| Remember-me cookie | Cho phép tự động khôi phục trạng thái đăng nhập | Phải đánh giá thu hồi riêng; không coi là bằng chứng xác minh mới |
| Session cookie | Tham chiếu một session đã được tạo | Có thể tiếp tục dùng dù remember-me token gốc đã bị thu hồi |
| Persistent login record | Trạng thái phía máy chủ cho remember-me dạng persistent | Cần xóa hoặc vô hiệu theo tài khoản và phạm vi chính xác |
| Refresh token | Cấp lại access token trong cơ chế token tương ứng | Không tự bị thu hồi chỉ vì xóa bảng remember-me |
| Dấu tin cậy thiết bị | Ghi nhận một thiết bị được hưởng chính sách đặc biệt | Có thể là cơ chế riêng của sản phẩm, không đồng nhất với remember-me |
| Credential MFA hoặc passkey | Authenticator để chứng minh quyền truy cập | Việc thay hoặc gỡ credential không tự định nghĩa cách xử lý cookie khác |

Ví dụ, một session bắt đầu từ remember-me có thể đã được lưu vào session store. Nếu chỉ xóa persistent login record, các lần tự đăng nhập mới bằng record đó bị chặn, nhưng session đã được tạo còn có thể hoạt động theo chính sách session của ứng dụng.

Ngược lại, chỉ gọi `session.invalidate()` ở trình duyệt hiện tại có thể để nguyên remember-me cookie. Cookie còn hiệu lực có thể tạo ra session mới sau khi session cũ bị đóng.

Vì vậy, nên mô hình hóa ba việc riêng biệt: **thu hồi credential remember-me phía máy chủ, vô hiệu các session thuộc phạm vi cần bảo vệ và dọn cookie ở trình duyệt hiện tại**.

## 3. Hai implementation remember-me của Spring Security

Spring Security cung cấp cách remember-me dựa trên dữ liệu được ký và cách dựa trên persistent token repository. Cả hai đều tích hợp qua `RememberMeServices` và cần `UserDetailsService`. Luồng tự đăng nhập sử dụng `RememberMeAuthenticationFilter`. Xem [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html).

### 3.1. TokenBasedRememberMeServices

Implementation này kiểm tra cookie bằng dữ liệu gồm định danh người dùng, hạn sử dụng, giá trị password từ `UserDetails` và key của dịch vụ. Password không được gửi nguyên giá trị vào cookie.

Khi giá trị password mà `UserDetailsService` cung cấp thay đổi, cookie được tạo từ giá trị cũ không còn khớp. Điều đó có thể hỗ trợ thu hồi sau đặt lại mật khẩu, nhưng chỉ khi các node thực sự đọc được dữ liệu mới và không tiếp tục chấp nhận giá trị cũ từ cache hoặc một đường xác minh khác. Xem [mã nguồn TokenBasedRememberMeServices](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/rememberme/TokenBasedRememberMeServices.java).

Không suy diễn rằng khôi phục MFA hoặc passkey cũng có hiệu ứng tương tự. Nếu luồng đó không thay đổi giá trị password, điều kiện ràng buộc password của cookie không tự thay đổi.

Với yêu cầu thu hồi từng tài khoản mà không đổi password, thiết kế có thể cần cơ chế version bảo mật được kiểm tra có chủ đích, denylist hoặc một implementation khác. Chỉ thêm cột `security_epoch` vào database không làm implementation mặc định tự đọc cột đó.

### 3.2. PersistentTokenBasedRememberMeServices

Implementation persistent sử dụng cookie chứa dữ liệu series/token và một repository phía máy chủ. Khi kiểm tra thành công, token có thể được thay mới trong cùng series. Việc quản lý password, trạng thái user và persistent token phải được phối hợp ở cấp ứng dụng. Xem [Javadoc PersistentTokenBasedRememberMeServices](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html).

**Đổi password không tự xóa persistent login record.** Luồng recovery cần thực hiện việc thu hồi phù hợp, chẳng hạn gọi `PersistentTokenRepository.removeUserTokens(...)` với principal của đúng tài khoản đã được xác minh.

Đừng coi rotation token là bằng chứng người dùng đã thực hiện xác minh mới. Trình duyệt chỉ trình một credential đã có từ trước; việc credential đó được xoay sau khi dùng không biến nó thành MFA hoặc một lần đăng nhập tương tác mới.

### 3.3. Vai trò của key không giống nhau ở hai cách

Với token-based, key tham gia kiểm tra giá trị cookie. Với persistent, cookie được kiểm tra theo dữ liệu repository; key còn được dùng để phối hợp `RememberMeAuthenticationToken` với provider trong quá trình xác thực nội bộ.

Nếu đổi key đồng thời ở service và provider của persistent implementation nhưng giữ record hợp lệ trong repository, không được kết luận cookie cũ đã bị thu hồi. Nhận định này được suy ra từ đường kiểm tra repository của persistent service và cách provider kiểm tra key của đối tượng authentication. Xem [RememberMeAuthenticationProvider](https://github.com/spring-projects/spring-security/blob/7.0.x/core/src/main/java/org/springframework/security/authentication/RememberMeAuthenticationProvider.java) và [PersistentTokenBasedRememberMeServices](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.java).

Key rotation toàn hệ thống cũng không thay việc vô hiệu session đã được tạo. Phải xác định chính xác cơ chế đang dùng và mục tiêu thu hồi, thay vì áp dụng một thao tác giống nhau cho mọi loại token.

## 4. Remember-me không phải bằng chứng đủ để khôi phục tài khoản

Cookie remember-me có thể giúp gợi ý một tài khoản hoặc hỗ trợ đánh giá rủi ro. Nó không tự chứng minh rằng người đang cầm trình duyệt là chủ tài khoản tại thời điểm yêu cầu thay authenticator.

Trong thiết kế recovery, nên phân biệt:

- **Nhận diện ứng viên:** tìm tài khoản có thể liên quan đến yêu cầu.
- **Xác minh quyền thực hiện:** kiểm tra bằng chứng phù hợp với hành động khôi phục.
- **Cấp quyền có giới hạn:** cho phép đúng thao tác, với thời hạn và số lần sử dụng đã quy định.

Ví dụ, remember-me xác định được tài khoản A không có nghĩa trình duyệt đó được tự gỡ MFA của A. Nếu cookie bị đánh cắp, việc cho phép đổi MFA chỉ với cookie sẽ biến một sự cố credential thành chiếm đoạt tài khoản lâu dài.

Đặc biệt, một recovery request có thể nhắm tới tài khoản B trong khi trình duyệt đang có session hoặc cookie của tài khoản A. Tài khoản đích phải được xác định từ recovery request/grant đã được kiểm chứng, không từ `Authentication.getName()` của trình duyệt hiện tại và không từ một username tự do trong request body.

### Ba mức cần tách khi phân quyền

| Trạng thái | Có thể cho phép theo thiết kế sản phẩm | Cần bổ sung trước thao tác recovery nhạy cảm |
| --- | --- | --- |
| Chưa đăng nhập | Bắt đầu yêu cầu, xem màn hình hướng dẫn | Bằng chứng độc lập và recovery grant hợp lệ |
| Được nhận diện bằng remember-me | Trải nghiệm thông thường có rủi ro thấp | Xác minh mới hoặc recovery policy phù hợp |
| Đã đăng nhập bằng cơ chế tương tác | Thao tác theo quyền tài khoản | Kiểm tra độ mới, yếu tố bắt buộc, trạng thái bảo mật và mục đích thao tác |

“Đã authenticated” không có nghĩa “đã hoàn thành mọi điều kiện của recovery”. Cũng không phải mọi authentication không thuộc remember-me đều có MFA hoặc còn đủ mới cho việc gỡ authenticator.

## 5. Thời điểm thu hồi: tránh biến recovery thành công cụ gây gián đoạn

Không xóa mọi remember-me token chỉ vì một người nhập email vào màn hình “quên mật khẩu”. Điểm bắt đầu này thường công khai; nếu dùng nó làm tín hiệu thu hồi toàn bộ, kẻ tấn công có thể gửi hàng loạt yêu cầu để liên tục làm gián đoạn người dùng hợp lệ.

Một chính sách minh họa:

| Giai đoạn hoặc tình huống | Cách xử lý minh họa |
| --- | --- |
| Chỉ yêu cầu gửi liên kết reset | Giữ credential hiện có; áp dụng chống lạm dụng và phản hồi phù hợp |
| Đã xác minh một bước nhưng chưa đủ quyền recovery | Giữ trạng thái theo policy; không cấp quyền quản trị credential chỉ từ remember-me |
| Đặt lại mật khẩu thành công | Thu hồi remember-me của tài khoản đích theo phạm vi đã quyết định; xử lý session riêng |
| Khôi phục MFA/passkey sau mất thiết bị | Đánh giá thu hồi credential cũ kể cả khi password không đổi |
| Có bằng chứng đáng tin về tài khoản bị xâm phạm | Có thể áp dụng biện pháp chặn sớm theo quy trình sự cố được phép |
| Recovery bị từ chối hoặc hết hạn | Không mặc định xóa token của một tài khoản chưa xác minh được quyền tác động |

Các lựa chọn phụ thuộc mô hình rủi ro. Một cảnh báo xâm phạm đã xác thực khác với một yêu cầu công khai chưa xác minh. Điều kiện kích hoạt biện pháp chặn cần được định nghĩa và kiểm chứng, không dựa vào một cờ do client tự gửi như `compromised=true`.

Đối với recovery sau mất MFA hoặc thiết bị, cần đặc biệt xem xét “trusted device” hoặc dấu bỏ qua MFA nếu sản phẩm có cơ chế đó. Chúng có thể nằm ở bảng hoặc dịch vụ khác với persistent remember-me token.

## 6. Cấu hình remember-me persistent theo cách dễ quản lý

Ví dụ sau thể hiện wiring cơ bản cho một ứng dụng Servlet dùng form login. Ví dụ yêu cầu dự án đã có `DataSource` và `UserDetailsService` phù hợp. Bảng persistent login được tạo bằng migration, không tạo tự động mỗi lần khởi động.

`security.remember-me.key` phải được cung cấp từ cấu hình bí mật của môi trường. Không đưa key thật vào mã nguồn hoặc tài liệu. Thời hạn bảy ngày bên dưới chỉ dùng minh họa.

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
@EnableWebSecurity
public class RememberMeSecurityConfig {
    @Bean
    PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        return repository;
    }

    @Bean
    PersistentTokenBasedRememberMeServices rememberMeServices(
            @Value("${security.remember-me.key}") String key,
            UserDetailsService users,
            PersistentTokenRepository repository) {

        PersistentTokenBasedRememberMeServices services =
                new PersistentTokenBasedRememberMeServices(key, users, repository);
        services.setCookieName("remember-me");
        services.setParameter("remember-me");
        services.setAlwaysRemember(false);
        services.setUseSecureCookie(true);
        services.setTokenValiditySeconds(7 * 24 * 60 * 60);
        services.setCookieCustomizer(cookie -> cookie.setAttribute("SameSite", "Lax"));
        return services;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            PersistentTokenBasedRememberMeServices rememberMeServices,
            SecurityContextRepository contextRepository) throws Exception {

        http
            .securityContext(context ->
                    context.securityContextRepository(contextRepository))
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .requestMatchers("/recovery/**").permitAll()
                    .requestMatchers("/account/security/**").fullyAuthenticated()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                    .key(rememberMeServices.getKey())
                    .rememberMeServices(rememberMeServices))
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là cấu hình nền cho ví dụ, chưa phải một hệ thống recovery hoàn chỉnh. Các endpoint `/recovery/**` phải tự kiểm tra grant, bằng chứng, mục đích, quyền đối với tài khoản đích và chống lạm dụng tại tầng nghiệp vụ. Một ứng dụng có quản trị recovery cần matcher và quyền riêng cho các endpoint quản trị, không đặt chúng dưới một vùng public chung rồi dựa vào tên đường dẫn.

`permitAll()` không bỏ qua toàn bộ filter chain. Authentication filter và các cơ chế bảo vệ vẫn có thể chạy trước khi quyết định cho phép request. Xem [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html). Vì thế, tầng nghiệp vụ phải xử lý đúng cả trường hợp request recovery công khai mang theo cookie đăng nhập cũ.

`fullyAuthenticated()` giúp loại remember-me khỏi một nhóm endpoint, nhưng không tự kiểm tra lần xác minh gần nhất, MFA hay recovery epoch. Tầng xử lý thay đổi credential vẫn cần policy về xác minh mới và quyền thực hiện đúng hành động.

Ví dụ không tắt CSRF. Trong ứng dụng dựa trên cookie, các request thay đổi trạng thái cần cơ chế chống CSRF phù hợp; `permitAll()` không đồng nghĩa với bỏ kiểm tra CSRF. Xem [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html). Nếu thiết kế một luồng khác có cơ chế bảo vệ chuyên biệt, phải đánh giá theo luồng đó thay vì tắt CSRF cho toàn ứng dụng.

Việc đăng ký `RememberMeServices` và provider phải nhất quán. Khi truyền một service tùy chỉnh, cấu hình các thuộc tính trực tiếp trên service đó; đừng giả định mọi setter khác trên DSL đều sẽ cấu hình lại instance đã cung cấp. Cơ chế lựa chọn service và key được thể hiện trong [RememberMeConfigurer](https://github.com/spring-projects/spring-security/blob/7.0.x/config/src/main/java/org/springframework/security/config/annotation/web/configurers/RememberMeConfigurer.java).

## 7. Thu hồi token phía máy chủ của đúng tài khoản

`PersistentTokenRepository` cung cấp thao tác `removeUserTokens(String username)` để loại các persistent login thuộc principal tương ứng. Đây là API theo username của repository, không phải theo session của request hiện tại. Xem [PersistentTokenRepository](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.java).

Một lời gọi ở vị trí đã xác minh đúng tài khoản có thể là:

```java
// target được nạp từ recovery request/grant đã xác minh ở phía máy chủ.
// rememberMePrincipal phải khớp định danh mà UserDetailsService/repository sử dụng.
persistentTokenRepository.removeUserTokens(target.rememberMePrincipal());
```

Đây là trích đoạn tích hợp, không phải endpoint hoàn chỉnh. `target` phải là kết quả nạp và kiểm chứng trong nghiệp vụ; không để client trực tiếp chọn principal cần xóa.

Trong ứng dụng nhiều tenant, cùng một tên đăng nhập có thể xuất hiện ở nhiều tenant. Repository mặc định không tự biết domain model tenant của sản phẩm. Cần dùng principal duy nhất toàn phạm vi repository hoặc repository tùy chỉnh có ràng buộc tenant/account rõ ràng.

`JdbcTokenRepositoryImpl` sử dụng câu xóa theo cột `username`. Nó không tự thêm điều kiện tenant hoặc tự ánh xạ email thành account ID. Xem [mã nguồn JdbcTokenRepositoryImpl](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/rememberme/JdbcTokenRepositoryImpl.java).

Nên có quy tắc ổn định cho principal. Nếu email có thể đổi, một mapping không nhất quán có thể để lại token dưới định danh cũ. Trong thiết kế tùy chỉnh, có thể ưu tiên account ID ổn định và mapping được quản lý rõ ràng, nhưng phải bảo đảm mọi thao tác phát hành, tra cứu và thu hồi dùng cùng hợp đồng.

### Phối hợp với transaction recovery

Nếu cập nhật credential, tiêu thụ recovery grant và xóa persistent token cùng dùng một database, có thể đưa chúng vào một transaction phù hợp. Điều này tránh việc trả thành công sau khi chỉ cập nhật được một phần trạng thái.

Mã giả sau mô tả thứ tự nghiệp vụ; các tên hàm là abstraction của sản phẩm, không phải API có sẵn của Spring Security:

```text
completeRecovery(command):
    bắt đầu transaction
    nạp và khóa recovery request theo grant đã kiểm chứng
    kiểm tra mục đích, hạn, subject, tenant, bằng chứng và trạng thái chưa dùng
    nạp và khóa tài khoản đích
    áp dụng thay đổi credential đã được phép
    tăng security epoch nếu policy yêu cầu thu hồi trạng thái trước recovery
    xóa persistent remember-me token của tài khoản đích
    đánh dấu grant đã tiêu thụ
    ghi sự kiện outbox cho cleanup session/cache liên quan
    commit

    dọn cookie và context của trình duyệt hiện tại theo policy
    trả kết quả hoàn tất
```

Nếu repository hoặc dịch vụ token dùng nguồn dữ liệu khác, một annotation transaction cục bộ không tạo transaction phân tán. Cần cơ chế phối hợp có khả năng retry, theo dõi trạng thái và chặn credential cũ trong khoảng cleanup chưa hoàn tất.

Không trả “đã đăng xuất mọi thiết bị” chỉ vì đã ghi một sự kiện dự định xóa. Sự kiện outbox bảo đảm công việc được ghi nhận cùng transaction khi được triển khai đúng; nó không tự chứng minh mọi nơi đã thực thi thu hồi.

## 8. Dọn remember-me cookie và context ở trình duyệt hiện tại

Xóa trạng thái phía máy chủ là quyết định bảo mật. Dọn cookie giúp trình duyệt ngừng gửi credential không còn hợp lệ và giảm vòng tự đăng nhập/lỗi lặp lại. Hai việc bổ sung cho nhau.

Không thể xóa trực tiếp cookie trong trình duyệt khác bằng response của trình duyệt hiện tại. Các bản sao cookie đã bị đánh cắp phải mất hiệu lực nhờ kiểm tra phía máy chủ, chứ không nhờ kỳ vọng client nhận lệnh xóa.

### 8.1. Dùng đúng instance và phạm vi cookie

Cookie cần được xử lý theo tên, domain và path khớp với cookie đã phát hành. Khi đổi tên hoặc phạm vi cookie qua các phiên bản, cần kế hoạch dọn cả các biến thể cũ đã được sử dụng.

Trong mã nguồn nhánh được đối chiếu, `AbstractRememberMeServices.logout(...)` thực hiện hủy cookie theo cấu hình service. Nhánh tạo cookie dùng cookie customizer, còn nhánh hủy không gọi cùng customizer đó. Vì vậy, không tùy ý thay path/domain chỉ trong customizer rồi mặc định thao tác hủy sẽ có cùng phạm vi. Xem [AbstractRememberMeServices](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.java).

Ví dụ cấu hình ở trên chỉ dùng customizer cho `SameSite`, không đổi tên, domain hoặc path qua customizer. Trong production cần kiểm chứng header `Set-Cookie` thực tế, cả khi chạy sau proxy hoặc dưới context path khác `/`.

### 8.2. Không nhầm tài khoản trong trình duyệt với tài khoản được recovery

Persistent service mặc định có thể xóa token theo `authentication.getName()` khi logout được truyền một authentication khác null. Do đó, không dùng một authentication tình cờ có trong request để thay cho tài khoản đích đã được recovery. Hành vi này được thể hiện trong [PersistentTokenBasedRememberMeServices.logout](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.java).

Sau khi nghiệp vụ đã thu hồi token của tài khoản đích một cách tường minh, có thể tách phần dọn trình duyệt như sau:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.context.SecurityContextRepository;

public final class RecoveryBrowserCleanup {
    private final PersistentTokenBasedRememberMeServices rememberMeServices;
    private final SecurityContextLogoutHandler contextLogout;

    public RecoveryBrowserCleanup(
            PersistentTokenBasedRememberMeServices rememberMeServices,
            SecurityContextRepository contextRepository) {
        this.rememberMeServices = rememberMeServices;
        this.contextLogout = new SecurityContextLogoutHandler();
        this.contextLogout.setSecurityContextRepository(contextRepository);
    }

    public void clearCurrentBrowser(
            HttpServletRequest request, HttpServletResponse response) {
        // null: chỉ yêu cầu service này dọn cookie trong response;
        // việc thu hồi token của tài khoản đích đã được xử lý riêng.
        this.rememberMeServices.logout(request, response, null);

        // Dọn context/session hiện tại qua cùng repository đã cấu hình.
        this.contextLogout.logout(request, response, null);
    }
}
```

Đăng ký lớp này trong ứng dụng với chính `rememberMeServices` và `SecurityContextRepository` đang được filter chain sử dụng. Chỉ gọi sau điểm nghiệp vụ recovery được phép hoàn tất; đây không phải hàm xác minh grant hoặc hàm thu hồi toàn bộ session.

Trong policy minh họa, thao tác này đóng session của trình duyệt đang thực hiện recovery, kể cả nếu trình duyệt trước đó đăng nhập một tài khoản khác. Đây phải là hành vi được lựa chọn và giải thích ở sản phẩm; không vô tình coi tài khoản trong trình duyệt là tài khoản cần thu hồi toàn hệ thống.

`SecurityContextLogoutHandler` vô hiệu session hiện tại, xóa context và lưu context rỗng qua repository đã cấu hình. Nó không tự tìm mọi session ở các node khác. Xem [SecurityContextLogoutHandler](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.java).

Nếu sản phẩm muốn xóa thêm cookie session khỏi trình duyệt, cần dùng tên/phạm vi thực tế của session cookie. Không hardcode `JSESSIONID` trong mọi ứng dụng vì một triển khai dùng Spring Session hoặc cấu hình riêng có thể dùng tên khác. Dù header xóa cookie không đến được client, session phía máy chủ đã vô hiệu vẫn phải không được chấp nhận.

### 8.3. Phân biệt custom recovery cleanup với logout chuẩn

Logout chuẩn của Spring Security phối hợp nhiều handler, có thể gồm context, remember-me và CSRF. Một custom controller tự gọi hai thành phần ở trên không mặc định tái tạo toàn bộ chuỗi logout, sự kiện và success handler của cấu hình ứng dụng. Xem [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html).

Vì vậy, cần xác định recovery cleanup muốn đạt điều gì và phối hợp các handler phù hợp. Nếu muốn tái sử dụng quy trình logout đầy đủ, phải kiểm tra đúng tài khoản, đúng phạm vi và những side effect của từng handler; không đơn giản gọi một URL logout thay cho nghiệp vụ recovery.

## 9. Chặn session cũ tiếp tục dùng sau recovery

Thu hồi persistent token chặn một đường xác thực trong tương lai. Session được tạo trước đó là trạng thái khác và cần chính sách riêng.

Các cách thường được thiết kế ở cấp ứng dụng gồm xóa session theo account trong session store, đánh dấu session hết hiệu lực hoặc dùng security epoch để từ chối session có thế hệ cũ. Nếu dùng một session registry cục bộ, phải hiểu giới hạn của nó trong cụm nhiều node và cách các filter thực thi trạng thái hết hiệu lực.

`SecurityContextHolder.clearContext()` chỉ tác động context đang được quản lý trong lần xử lý hiện tại. Trạng thái lưu cho các request tiếp theo nằm ở `SecurityContextRepository`/session store tương ứng. Cơ chế persistence được giải thích trong [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html).

Không đánh đồng các hành động sau:

```text
xóa context hiện tại
    khác với xóa context đã lưu trong một session
    khác với vô hiệu mọi session của một tài khoản
    khác với thu hồi remember-me credential
```

Một recovery flow sau nghi ngờ bị chiếm tài khoản có thể yêu cầu xử lý cả bốn. Một flow khác có thể có phạm vi hẹp hơn theo policy, nhưng phải ghi rõ loại trạng thái nào còn hiệu lực và trong bao lâu.

Nếu ứng dụng dùng refresh token hoặc access token ngoài session web, cần đi qua cơ chế thu hồi riêng của chúng. Không tuyên bố xóa persistent login record đã chặn được mọi API token.

## 10. Race condition: token cũ có thể tạo session trong lúc thu hồi

Chỉ kiểm tra “bảng persistent login đã trống” chưa đủ để chứng minh một yêu cầu tự đăng nhập đang chạy không thể hoàn tất.

Xét lịch thực thi giả định:

```text
T1: Auto-login đọc một persistent token hợp lệ của tài khoản A.
T2: Recovery của A commit: đổi credential và xóa persistent token.
T1: Tiếp tục xử lý dữ liệu đã đọc, có thể tạo Authentication/session.
```

Một transaction bao quanh các thay đổi ở T2 không tự khóa mọi đường xử lý của T1. Cần đánh giá thứ tự đọc, khóa, isolation, cache và thời điểm session được phép sử dụng.

Mã nguồn persistent service và JDBC repository được đối chiếu có bước đọc token rồi cập nhật, tải user và tạo authentication ở các thành phần liên quan. API cập nhật repository không mang sẵn hợp đồng compare-and-set theo security epoch của ứng dụng. Vì vậy, không suy ra tính an toàn đồng thời chỉ từ tên `PersistentTokenRepository`; phải thiết kế và kiểm thử cơ chế thu hồi của hệ thống.

### 10.1. Security epoch là một thiết kế bổ sung

Một thiết kế tùy chỉnh có thể gắn một thế hệ bảo mật vào credential và session:

```text
Tài khoản A: security_epoch = 8

Remember-me record R:
    account_id = A
    issued_epoch = 8

Session S tạo từ R:
    account_id = A
    authenticated_epoch = 8

Recovery hoàn tất:
    security_epoch của A tăng lên 9

Khi tiếp tục dùng R hoặc S:
    epoch của credential/session không khớp tài khoản -> từ chối
```

`issued_epoch` phải đi cùng credential đã được xác minh từ nguồn có thẩm quyền. Không lấy cookie cũ, đọc epoch hiện tại là 9 rồi gắn 9 vào session mới. Cách đó làm credential cũ được “đổi nhãn” thành trạng thái mới và phá mục đích thu hồi.

Một cơ chế đúng cần bảo đảm:

- Credential được phát hành dưới epoch nào phải được kiểm tra theo epoch đó.
- Session kế thừa đúng epoch của lần xác thực, không tự nâng epoch khi chỉ đọc lại user.
- Việc tăng epoch được commit cùng thay đổi recovery cần bảo vệ.
- Điểm xác thực và điểm cho phép thao tác nhạy cảm đối chiếu trạng thái tài khoản đủ mới.
- Cache và các node có hợp đồng về độ trễ hoặc cơ chế chặn khi không thể xác định trạng thái hiện hành.

Đây là thiết kế mở rộng của sản phẩm. Schema và `PersistentRememberMeToken` mặc định không tự có những trường epoch nói trên; muốn áp dụng cần repository/services, session metadata và enforcement phù hợp. Không chỉ thêm một filter đọc user hiện tại rồi tuyên bố đã giải quyết mọi race condition.

### 10.2. Giới hạn khi request đã bắt đầu chạy

Ngay cả khi mọi request mới đều kiểm tra epoch, một request đã được cấp quyền và đang tạo side effect có thể cần kiểm tra lại tại điểm commit nhạy cảm. Không thể mô tả mọi side effect đang chạy là bị “hủy ngay” chỉ bằng cách tăng một số trong tài khoản.

Đối với thay đổi credential hoặc dữ liệu nhạy cảm, cần ràng buộc quyết định cuối với trạng thái bảo mật phù hợp, chẳng hạn kiểm tra version khi cập nhật hoặc cơ chế đồng bộ đã được thiết kế. Cam kết thu hồi nên được mô tả theo ranh giới thực thi có thể chứng minh.

## 11. Kiểm tra mức tin cậy và yêu cầu xác minh mới

`Authentication.isAuthenticated()` không đủ để xác định một request vừa nhập lại mật khẩu hoặc vừa hoàn tất MFA. Remember-me authentication có thể là authentication hợp lệ nhưng vẫn không đạt yêu cầu cho thao tác nhạy cảm.

Spring Security cung cấp `AuthenticationTrustResolver` để phân biệt anonymous, remember-me và fully authenticated theo mô hình trust tương ứng. Ví dụ dùng implementation mặc định:

```java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;

public final class RememberMeTrustGate {
    private final AuthenticationTrustResolver trustResolver =
            new AuthenticationTrustResolverImpl();

    public boolean isInteractiveCandidate(Authentication authentication) {
        return this.trustResolver.isFullyAuthenticated(authentication);
    }
}
```

Tên `isInteractiveCandidate` nhấn mạnh đây chỉ là một điều kiện đầu vào cho policy. Theo định nghĩa API, fully authenticated loại anonymous và remember-me; nó không tự biểu diễn độ mới, MFA hoặc subject được phép recovery. Xem [AuthenticationTrustResolver](https://github.com/spring-projects/spring-security/blob/7.0.x/core/src/main/java/org/springframework/security/authentication/AuthenticationTrustResolver.java).

Nếu ứng dụng dùng loại authentication tùy chỉnh hoặc cơ chế nâng mức bảo đảm riêng, phải kiểm tra trust resolver và authorization logic thực tế. Việc thay một `RememberMeAuthenticationToken` bằng token “fully authenticated” tự tạo trong controller không phải quá trình xác minh.

Một policy cho việc gỡ MFA có thể cần đồng thời: subject khớp tài khoản đích, bằng chứng thuộc phương thức được phép, thời điểm xác minh đủ mới, mục đích được ràng buộc, trạng thái tài khoản hiện hành và grant chưa bị dùng. Phần đó thuộc nghiệp vụ recovery và cơ chế step-up của sản phẩm.

### Không suy ra xác minh mới chỉ từ tên authentication event

Trong nhánh mã nguồn được đối chiếu, `RememberMeAuthenticationFilter` có thể phát `InteractiveAuthenticationSuccessEvent` sau auto-login thành công. Vì vậy, một listener nghe tên event này rồi ghi `lastFreshAuthenticationAt = now` cho mọi trường hợp có thể vô tình coi remember-me là xác minh mới. Xem [RememberMeAuthenticationFilter](https://github.com/spring-projects/spring-security/blob/7.0.x/web/src/main/java/org/springframework/security/web/authentication/rememberme/RememberMeAuthenticationFilter.java).

Khi ghi mức bảo đảm hoặc thời điểm xác minh, cần xét loại authentication, nguồn xác thực và bằng chứng đã hoàn tất. Event là tín hiệu tích hợp; ý nghĩa bảo mật phải được định nghĩa cụ thể.

## 12. Sau recovery có nên tự đăng nhập hoặc phát cookie mới?

Một lựa chọn dễ kiểm soát là kết thúc recovery bằng việc dọn trạng thái trình duyệt, hướng dẫn người dùng đăng nhập lại qua quy trình bình thường, rồi chỉ cấp remember-me sau khi thỏa điều kiện phát hành.

Nếu sản phẩm cho phép tiếp tục trong một session recovery có giới hạn, session đó cần thể hiện đúng quyền đã cấp. Ví dụ, một grant cho phép đăng ký passkey mới không tự cho phép dùng mọi API tài khoản hoặc tạo credential đăng nhập lâu dài.

Không gọi `rememberMeServices.loginSuccess(...)` trực tiếp từ một endpoint reset chỉ vì endpoint đã đổi password. Trước khi cấp remember-me mới, phải xác định chính xác flow nào đã hoàn tất, những yếu tố nào đã được xác minh và người dùng đã chọn lưu đăng nhập hay chưa.

Trong ứng dụng MFA, cần kiểm tra thời điểm hook phát hành cookie được gọi. Nếu form login coi kiểm tra password là thành công và cấp remember-me trước khi hoàn tất yếu tố tiếp theo, cookie có thể được phát hành quá sớm so với policy của sản phẩm. Luồng xác thực nhiều bước cần phối hợp việc phát hành với mốc hoàn tất thực tế.

Điều kiện phát hành minh họa:

```text
Được phát hành remember-me mới khi:
    đã hoàn tất luồng xác thực mà policy cho phép
    + các yếu tố bắt buộc đã được kiểm chứng
    + account/security epoch còn hợp lệ
    + không đang trong trạng thái recovery bị hạn chế
    + có lựa chọn lưu đăng nhập theo thiết kế sản phẩm
```

Dấu cộng biểu thị tập điều kiện phải thỏa, không phải phép cộng điểm rủi ro. Các nguồn bằng chứng và thời điểm ghi nhận phải ở phía máy chủ, không chỉ dựa trên checkbox hoặc cờ frontend.

Sau khi người dùng đăng nhập lại, những session hay token đã bị thu hồi trước đó không được khôi phục để “đồng bộ trải nghiệm”. Cần phát hành trạng thái mới theo chính sách hiện hành.

## 13. Hệ thống nhiều node, lỗi repository và retry

### 13.1. Nguồn trạng thái dùng chung

Trong cụm nhiều node, persistent token repository và nguồn trạng thái bảo mật phải có hợp đồng nhất quán phù hợp. Dùng một kho in-memory riêng trên mỗi node không tạo cơ chế thu hồi toàn cụm.

Một node đọc cache cũ của user hoặc token có thể tiếp tục chấp nhận credential đã bị thu hồi nếu cơ chế kiểm tra không có biện pháp bảo vệ. Vì vậy, cần thiết kế cả đường cache invalidation, kiểm tra version và hành vi khi nguồn trạng thái không sẵn sàng.

### 13.2. Không có fallback làm sống lại cookie cũ

Khi repository không truy cập được, không chuyển sang “tin cookie vì cookie chưa hết hạn” nếu điều đó bỏ qua điều kiện bảo mật đã được thiết kế. Một lỗi vận hành không được tự tạo đường auto-login yếu hơn.

Người dùng có thể được hướng dẫn đăng nhập qua phương thức còn hoạt động, thử lại sau hoặc liên hệ hỗ trợ theo policy. Nội dung thông báo cần tránh làm lộ thông tin tài khoản hoặc chi tiết credential.

### 13.3. Retry phải giữ nguyên mục tiêu thu hồi

Các công việc cleanup có thể dùng event ID, account ID ổn định và version đích để xử lý lặp an toàn. Tuy nhiên, cần phân biệt “lặp lại xóa mọi token” với “thu hồi token thuộc thế hệ cũ”.

Ví dụ, recovery ở epoch 8 đã tăng tài khoản lên epoch 9. Người dùng sau đó đăng nhập hợp lệ và có remember-me mới ở epoch 9. Một consumer retry chậm gọi `removeUserTokens(username)` không phân biệt thế hệ có thể xóa cả token mới này.

Nếu yêu cầu sản phẩm cần giữ credential mới, cần thao tác thu hồi có điều kiện theo thế hệ hoặc thời điểm phát hành đáng tin, và có cơ chế đồng bộ chống race phù hợp. API repository chuẩn chỉ có xóa theo user; khả năng thu hồi theo epoch là phần mở rộng phải triển khai rõ ràng.

Một lựa chọn khác là trì hoãn cấp remember-me mới đến khi cleanup đã đạt trạng thái cần thiết. Đây là quyết định trải nghiệm và khả dụng phải được diễn đạt trong policy.

### 13.4. Trạng thái hoàn tất phải phản ánh thực tế

Phân biệt ít nhất các mốc: credential đã cập nhật, grant đã tiêu thụ, ràng buộc vô hiệu credential cũ đã có hiệu lực và công việc dọn dữ liệu đã hoàn tất. Nếu có độ trễ, sự kiện, dashboard và thông báo phải dùng ngữ nghĩa phù hợp với mốc đã đạt.

## 14. Các tình huống kiểm thử cần có

Kiểm thử remember-me trong recovery phải kiểm tra hành vi xác thực thực tế, không chỉ kiểm tra đã gọi một hàm xóa token.

| Tình huống | Kết quả cần chứng minh theo policy |
| --- | --- |
| Remember-me được dùng trước recovery | Endpoint thông thường hoạt động theo mức quyền được phép |
| Remember-me truy cập thao tác gỡ MFA | Không được dùng cookie làm bằng chứng duy nhất để hoàn tất |
| Gửi yêu cầu quên password công khai | Không tự thu hồi mọi credential của tài khoản chưa xác minh |
| Recovery password thành công | Credential cũ bị từ chối theo cơ chế đang sử dụng |
| Recovery MFA/passkey không đổi password | Token cũ vẫn bị thu hồi theo policy; không dựa vào password hash thay đổi |
| Token-based sau cập nhật password | Mọi node không tiếp tục chấp nhận giá trị password cũ |
| Persistent token sau đổi password | Luồng nghiệp vụ thực sự thu hồi record theo tài khoản đích |
| Xóa persistent token nhưng giữ session đã có | Kiểm tra và xử lý riêng session còn sống |
| Trình duyệt A đang đăng nhập, recovery nhắm B | Không xóa nhầm credential toàn hệ thống của A thay cho B |
| Username giống nhau ở hai tenant | Chỉ tác động đúng phạm vi account/tenant |
| Cookie có path hoặc tên cũ | Response dọn đúng biến thể cookie cần xử lý |
| Response dọn cookie bị mất | Cookie cũ vẫn không xác thực được nhờ server-side revocation |
| Auto-login đồng thời với recovery | Không tạo quyền sử dụng vượt ranh giới thu hồi đã cam kết |
| Cleanup event được gửi trùng hoặc đến muộn | Không làm sống lại credential cũ hoặc thu hồi nhầm credential mới |
| Repository lỗi trong recovery | Không báo thành công thu hồi khi chưa đạt điều kiện hoàn tất |
| Đăng nhập lại sau recovery | Chỉ cấp remember-me mới ở mốc được policy cho phép |

### 14.1. Đừng để mock che mất đường auto-login

`@WithMockUser` hoặc request post-processor `user(...)` tạo sẵn một authentication cho kiểm thử. Chúng hữu ích cho một số kiểm tra phân quyền nhưng không chứng minh remember-me cookie đã được giải mã, tra repository và xử lý đúng. Spring hỗ trợ truyền authentication tùy chỉnh khi cần kiểm tra một mức trust cụ thể. Xem [Spring Security — Testing Authentication in MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html).

Để kiểm thử auto-login, cần một request mới không có session/authentication đã nạp sẵn, mang cookie thực tế do flow kiểm thử phát hành hoặc một fixture hợp lệ phù hợp implementation. Chạy qua filter chain của ứng dụng, sau đó kiểm tra kết quả và trạng thái repository/session.

Nếu request mang session authenticated sẵn, filter có thể không đi qua nhánh remember-me. Một test vẫn thành công trong trường hợp đó không chứng minh cookie đã bị chấp nhận hoặc từ chối.

### 14.2. Kiểm thử đồng thời cần điều khiển lịch thực thi

Không chỉ chạy hai thread ngẫu nhiên rồi kỳ vọng gặp race. Có thể dùng synchronization trong test để giữ auto-login sau bước đọc token, thực hiện commit recovery rồi cho auto-login tiếp tục. Kết quả cần kiểm tra là credential/session cũ không có quyền tạo side effect vượt policy thu hồi.

Với thiết kế epoch, phải thử cả trường hợp session bị gắn nhầm epoch hiện tại, cache còn epoch cũ và consumer cleanup tới sau lần đăng nhập mới. Đây là các ranh giới thường bị bỏ qua khi chỉ kiểm tra số record đã xóa.

## 15. Audit và quan sát vận hành

Audit nên mô tả quyết định và kết quả thu hồi mà không ghi token hoặc cookie. Dữ liệu có thể gồm recovery request reference, account reference được bảo vệ phù hợp, scope, policy revision, epoch trước/sau và kết quả từng nhóm công việc.

Ví dụ sự kiện miền do sản phẩm tự định nghĩa:

```json
{
  "eventId": "REC-REVOCATION-0045",
  "eventType": "RECOVERY_CREDENTIAL_REVOCATION_COMMITTED",
  "recoveryRequestRef": "RECOVERY-REQUEST-0045",
  "subjectRef": "ACCOUNT-0045",
  "scopeRef": "TENANT-SCOPE-A",
  "policyRevision": "recovery-policy-r12",
  "rememberMeAction": "REVOKE_PREVIOUS_CREDENTIALS",
  "securityEpochBefore": 8,
  "securityEpochAfter": 9,
  "sessionCleanup": "OUTBOX_PENDING",
  "occurredAt": "2030-04-10T09:30:00Z"
}
```

Ví dụ này chỉ phù hợp nếu sản phẩm thực sự có cơ chế epoch và đã commit việc thu hồi tương ứng. Không phát sự kiện mang ngữ nghĩa đó chỉ vì đã gọi một API từ controller.

Không ghi giá trị `remember-me` cookie, recovery token, OTP, password hoặc nguyên header `Cookie`/`Set-Cookie`. Các định danh tương quan cũng cần quyền truy cập phù hợp vì có thể liên kết tới hồ sơ người dùng.

Những tín hiệu nên quan sát theo thiết kế gồm lỗi repository, auto-login bị từ chối sau recovery, độ trễ cleanup, request mang epoch cũ, tỷ lệ phát hành remember-me mới trước khi đủ điều kiện và sai lệch giữa các node.

Một lần token mismatch cần được xử lý theo implementation và quy trình sự cố, nhưng không vội kết luận mọi mismatch đều chứng minh cookie đã bị đánh cắp. Các request đồng thời, tab cũ hoặc lỗi phân phối trạng thái có thể cần được điều tra. Thông báo và cảnh báo phải phân biệt sự kiện kỹ thuật quan sát được với kết luận về nguyên nhân.

## 16. Những lỗi tích hợp cần tránh

| Cách làm | Vấn đề | Hướng thiết kế phù hợp |
| --- | --- | --- |
| Chỉ đổi password | Không bảo đảm persistent token đã bị thu hồi | Quản lý credential remember-me theo implementation và policy |
| Chỉ xóa cookie ở trình duyệt hiện tại | Bản sao ở thiết bị khác vẫn có thể được trình lại | Bắt buộc có kiểm tra thu hồi phía máy chủ |
| Chỉ xóa persistent login record | Session đã được tạo có thể còn hiệu lực | Xử lý session và token khác theo phạm vi recovery |
| Dùng principal hiện tại để xác định tài khoản recovery | Có thể nhầm tài khoản trong trình duyệt với subject của grant | Nạp tài khoản đích từ recovery request đã kiểm chứng |
| Đổi key của persistent service để thu hồi một user | Không phải cơ chế xóa persistent record của user | Dùng thao tác thu hồi có chủ đích |
| Dùng `authenticated()` như xác minh mới | Remember-me có thể đáp ứng trạng thái authenticated | Tách trust, freshness, yếu tố và quyền thao tác |
| Tự nâng authentication sau reset | Có thể cấp quyền đầy đủ khi chưa đủ bằng chứng | Dùng flow xác thực hoặc grant giới hạn đúng policy |
| Xóa token ngay khi ai đó yêu cầu gửi email reset | Tạo đường gây gián đoạn tài khoản chưa xác minh | Định nghĩa đúng mốc thu hồi và chống lạm dụng |
| Tin rằng `@Transactional` chặn mọi auto-login đang chạy | Các đường xác thực có thể không tham gia cùng cơ chế đồng bộ | Thiết kế ranh giới thu hồi và kiểm chứng race |
| Retry xóa mọi token không xét thế hệ | Có thể xóa credential hợp lệ mới phát hành | Thu hồi có phạm vi hoặc phối hợp mốc cấp mới |

Remember-me cần được xem như một credential đăng nhập có vòng đời riêng. Khi recovery thay đổi nền tảng tin cậy của tài khoản, hệ thống phải quyết định rõ credential nào mất hiệu lực, session nào bị hạn chế và điều kiện phát hành trạng thái mới. Spring Security cung cấp các điểm tích hợp; tính đúng đắn của toàn luồng phụ thuộc vào việc phối hợp chúng với bằng chứng recovery, định danh tài khoản và cơ chế thu hồi của sản phẩm.
