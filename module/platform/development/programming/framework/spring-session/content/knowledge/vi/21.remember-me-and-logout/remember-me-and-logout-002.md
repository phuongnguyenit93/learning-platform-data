# SpringSessionRememberMeServices và điều chỉnh vòng đời phiên

Spring Session quản lý dữ liệu phiên ở một kho dùng chung như Redis hoặc JDBC. Khi kết hợp với Spring Security, ứng dụng có thể cung cấp lựa chọn “Ghi nhớ đăng nhập” để kéo dài thời gian không hoạt động của phiên sau khi người dùng xác thực thành công. SpringSessionRememberMeServices là thành phần tích hợp cho cách làm này: nó điều chỉnh maxInactiveInterval của HttpSession khi lựa chọn remember-me được gửi trong quá trình đăng nhập.

Điểm quan trọng là cơ chế này tận dụng chính session đã được Spring Session lưu trữ. Nó không đồng nghĩa với việc phát hành một remember-me token độc lập có thể tự đăng nhập lại sau khi session bị xóa. Vì vậy, cần hiểu rõ khác biệt giữa thời hạn session phía server, thời hạn cookie phía trình duyệt và cơ chế remember-me dựa trên token của Spring Security.

## 1. Remember-me trong ứng dụng Spring Session

Thông thường, một session có thời hạn không hoạt động tối đa. Nếu người dùng không gửi request trong khoảng thời gian này, session hết hạn và request sau đó phải tạo phiên mới hoặc yêu cầu đăng nhập lại.

Khi người dùng chọn “Ghi nhớ đăng nhập”, ứng dụng có thể muốn giữ phiên lâu hơn. SpringSessionRememberMeServices tích hợp với Spring Security để điều chỉnh maxInactiveInterval của session sau khi đăng nhập thành công và remember-me được yêu cầu.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Người dùng gửi form đăng nhập"] --> B["Spring Security xác thực"]
    B --> C{"Remember-me được chọn?"}
    C -->|Không| D["Giữ timeout session thông thường"]
    C -->|Có| E["SpringSessionRememberMeServices"]
    E --> F["Điều chỉnh maxInactiveInterval"]
    D --> G["Spring Session lưu HttpSession"]
    F --> G
    G --> H["Redis hoặc JDBC repository"]
    H --> I["Trình duyệt tiếp tục gửi cookie session"]
~~~

Với Spring Session, HttpSession là API Servlet mà ứng dụng và Spring Security sử dụng. Session thực tế được lưu ngoài tiến trình ứng dụng; do đó một instance khác vẫn có thể tải session khi request tiếp theo được chuyển đến instance đó.

## 2. SpringSessionRememberMeServices làm gì?

SpringSessionRememberMeServices triển khai hợp đồng RememberMeServices của Spring Security. Khi đăng nhập thành công và lựa chọn remember-me được gửi, thành phần này điều chỉnh thời gian không hoạt động tối đa của session để phiên có thể tồn tại lâu hơn timeout thông thường.

Các điểm cần hiểu:

- Nó tác động đến thời hạn của session hiện tại.
- Nó không phải user database và không thay thế quá trình xác thực.
- Nó không tự cấp một session ID tùy ý cho client.
- Nó không làm cho session còn hợp lệ sau khi repository đã xóa dữ liệu hoặc quản trị viên đã thu hồi phiên.
- Thời hạn thực tế còn phụ thuộc repository, TTL, chính sách cookie và cấu hình hạ tầng.

Trong Spring Session, timeout của session được lưu cùng trạng thái phiên. Khi session được cập nhật, repository có thể cập nhật thời hạn tương ứng ở kho dữ liệu. Với Redis, điều này liên quan đến TTL của dữ liệu session; với JDBC, repository kiểm tra thời hạn và dọn các bản ghi hết hạn theo cơ chế của nó.

Không suy luận rằng “remember me” đồng nghĩa với đăng nhập vĩnh viễn. Người dùng vẫn có thể bị yêu cầu đăng nhập lại khi session bị logout, bị thu hồi, mất dữ liệu, bị xóa bởi chính sách vận hành hoặc không còn được trình duyệt gửi cookie.

## 3. Cấu hình với Spring Security

Trong ứng dụng Servlet dùng Spring Security, tạo bean SpringSessionRememberMeServices và đăng ký nó qua cấu hình remember-me:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.RememberMeServices;
import org.springframework.session.security.SpringSessionRememberMeServices;

@Configuration
class SecurityConfiguration {

    @Bean
    RememberMeServices rememberMeServices() {
        SpringSessionRememberMeServices services =
            new SpringSessionRememberMeServices();
        services.setAlwaysRemember(false);
        return services;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RememberMeServices rememberMeServices) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .rememberMe(rememberMe -> rememberMe
                .rememberMeServices(rememberMeServices)
            );

        return http.build();
    }
}
~~~

Ví dụ đặt alwaysRemember thành false, vì vậy ứng dụng chỉ áp dụng remember-me khi request đăng nhập có lựa chọn tương ứng. Đây là lựa chọn phù hợp khi giao diện cho phép người dùng chủ động chọn trên từng lần đăng nhập.

API và package phải khớp với phiên bản Spring Session/Spring Security trong dự án. Dùng dependency management/BOM tương thích để tránh trộn các phiên bản không tương thích. Nếu ứng dụng không dùng Spring Security, SpringSessionRememberMeServices không tự tạo một cơ chế đăng nhập hoàn chỉnh.

## 4. Lựa chọn remember-me trên form đăng nhập

Theo cấu hình mặc định phổ biến của Spring Security, tham số checkbox remember-me có tên remember-me. Form đăng nhập có thể gửi giá trị này khi người dùng chọn:

~~~html
<form method="post" action="/login">
  <label>
    <input type="checkbox" name="remember-me" value="true">
    Ghi nhớ đăng nhập trên thiết bị này
  </label>
  <button type="submit">Đăng nhập</button>
</form>
~~~

Form thực tế cần có các trường username/password theo cấu hình đăng nhập và CSRF token nếu CSRF protection được bật. Không bỏ CSRF chỉ để làm cho form ví dụ hoạt động.

Khi alwaysRemember là false, dịch vụ dựa vào lựa chọn remember-me trong request. Nếu giao diện dùng tên tham số khác với mặc định của Spring Security, cấu hình tên tham số tương ứng trong remember-me DSL hoặc API được phiên bản hỗ trợ. Đảm bảo form và backend dùng cùng tên.

## 5. alwaysRemember và lựa chọn của người dùng

setAlwaysRemember(true) yêu cầu dịch vụ áp dụng remember-me cho mọi lần đăng nhập thành công mà dịch vụ xử lý, kể cả khi form không gửi checkbox. Điều này có thể phù hợp với một thiết bị chuyên dụng hoặc ứng dụng có chính sách ghi nhớ thống nhất, nhưng thường không phù hợp với hệ thống có thiết bị dùng chung.

| Cấu hình | Hành vi | Khi cân nhắc |
| --- | --- | --- |
| alwaysRemember=false | Chỉ kéo dài phiên khi request có lựa chọn remember-me | Ứng dụng có checkbox và người dùng tự chọn |
| alwaysRemember=true | Áp dụng remember-me cho mọi lần đăng nhập thành công | Thiết bị/kiosk được quản lý hoặc chính sách cố định đã được đánh giá |

Không bật alwaysRemember chỉ để giảm số lần đăng nhập lại. Người dùng có thể đăng nhập trên máy dùng chung, máy công cộng hoặc thiết bị không được bảo vệ. Kéo dài mọi session làm tăng thời gian một session bị lộ có thể bị sử dụng.

## 6. Điều chỉnh vòng đời session và maxInactiveInterval

Servlet HttpSession có phương thức setMaxInactiveInterval(int seconds). Giá trị này biểu diễn số giây không hoạt động tối đa trước khi session hết hạn. Spring Session ánh xạ trạng thái này vào repository thay vì chỉ giữ trong bộ nhớ servlet container.

SpringSessionRememberMeServices sử dụng cơ chế thời hạn của session để kéo dài phiên khi remember-me được chọn. Trong các phiên bản triển khai phổ biến, giá trị được đặt rất lớn (thường là Integer.MAX_VALUE giây), nên cần xem nó như một thời hạn dài chứ không phải cam kết vĩnh viễn. Kiểm tra JavaDoc/source của phiên bản đang dùng nếu ứng dụng cần dựa vào giá trị số cụ thể.

Thời hạn session ảnh hưởng đến:

- Thời điểm repository coi session không còn hợp lệ.
- TTL hoặc expiration metadata mà repository quản lý.
- Khả năng session được tải bởi request tiếp theo.
- Dung lượng dữ liệu session tích tụ trong Redis hoặc database.
- Thời gian một session bị lộ có thể tiếp tục được sử dụng nếu chưa bị thu hồi.

Không nhầm maxInactiveInterval với absolute lifetime. Idle timeout đo thời gian không hoạt động; absolute lifetime là giới hạn tổng thời gian từ lúc đăng nhập, bất kể người dùng có hoạt động hay không. Nếu nghiệp vụ cần cả hai, hãy lưu mốc xác thực riêng và kiểm tra absolute lifetime ở tầng bảo mật.

## 7. Phân biệt timeout session và thời hạn cookie

Remember-me qua SpringSessionRememberMeServices chủ yếu điều chỉnh thời hạn session phía server. Cookie là cơ chế để trình duyệt gửi session ID trong các request tiếp theo. Hai thời hạn này độc lập:

| Thành phần | Quyết định điều gì? | Ví dụ vấn đề |
| --- | --- | --- |
| HttpSession.maxInactiveInterval | Session còn hợp lệ bao lâu khi không hoạt động | Session hết hạn ở repository |
| Redis TTL/JDBC expiration | Kho dữ liệu giữ hoặc coi session hết hạn như thế nào | Key hết TTL hoặc bản ghi bị dọn |
| Cookie Max-Age/Expires | Trình duyệt giữ cookie đến khi nào | Browser không còn gửi session ID |
| Cookie Path/Domain/SameSite/Secure | Request nào được gửi kèm cookie | Cookie không được gửi trong một ngữ cảnh cụ thể |

Nếu cookie là session cookie, trình duyệt có thể xóa cookie khi phiên trình duyệt kết thúc, tùy chính sách và cơ chế khôi phục session của trình duyệt. Khi đó, session phía server có thể còn tồn tại nhưng người dùng không còn cookie để truy cập nó. Ngược lại, cookie còn trong browser không làm session phía server sống lại sau khi repository đã hết hạn hoặc xóa dữ liệu.

Vì vậy, không thay Cookie Max-Age rồi cho rằng session phía server cũng được kéo dài. Cũng không tăng session timeout rồi cho rằng trình duyệt chắc chắn sẽ giữ cookie sau khi đóng trình duyệt.

## 8. Kết hợp với Spring Session Redis

Với Redis, session được lưu trong các key do Spring Session quản lý và có TTL/expiration. Khi SpringSessionRememberMeServices điều chỉnh max inactive interval, repository phải lưu thay đổi này để Redis áp dụng thời hạn tương ứng.

Những điểm cần kiểm tra:

- Mọi instance dùng cùng Redis deployment và namespace.
- Các instance dùng cùng cấu hình serializer.
- TTL của key session không ngắn hơn timeout mà ứng dụng mong muốn.
- Cấu hình expiration/cleanup phụ trợ không xóa session hợp lệ.
- Khi request sử dụng session, last accessed time và expiration được cập nhật theo cơ chế repository.
- Khi logout hoặc thu hồi, dữ liệu session bị vô hiệu hóa dù trước đó đã được đặt timeout dài.

Không tự đặt TTL cố định cho map/key session bằng một giá trị ngắn hơn remember-me timeout. Nếu cấu hình Redis bên ngoài hoặc chính sách eviction làm dữ liệu bị xóa sớm, remember-me không thể khôi phục session đã mất.

## 9. Kết hợp với Spring Session JDBC

Với JDBC, JdbcIndexedSessionRepository lưu metadata và thuộc tính session trong các bảng quan hệ. Timeout session được ghi trong dữ liệu repository và được kiểm tra khi tải session. Các bản ghi hết hạn có thể được dọn bởi tác vụ cleanup định kỳ.

Khi dùng remember-me:

- Kiểm tra cột thời hạn/expiration được cập nhật đúng sau đăng nhập.
- Đảm bảo các instance dùng cùng schema và cấu hình repository.
- Kiểm tra cleanup job không xóa session còn hợp lệ.
- Theo dõi số bản ghi session tăng do thời hạn dài.
- Có chính sách dọn dữ liệu và giới hạn dung lượng phù hợp.

Session có thời hạn dài có thể khiến dữ liệu JDBC tồn tại lâu hơn, làm bảng lớn và tăng chi phí index, backup, cleanup. Hãy theo dõi số session đang hoạt động, dung lượng bảng và thời gian truy vấn.

## 10. Khác biệt với remember-me dựa trên token của Spring Security

Spring Security còn có các cơ chế remember-me dựa trên cookie/token, ví dụ TokenBasedRememberMeServices hoặc PersistentTokenBasedRememberMeServices. Những cơ chế đó có mục tiêu và vòng đời khác với SpringSessionRememberMeServices.

| Tiêu chí | SpringSessionRememberMeServices | Remember-me token của Spring Security |
| --- | --- | --- |
| Trạng thái được kéo dài | Session hiện tại | Có thể xác thực lại bằng remember-me cookie/token |
| Phụ thuộc session còn tồn tại | Có | Có thể tạo phiên mới sau khi token được xác thực |
| Dữ liệu chính | Session trong Spring Session repository | Cookie/token và có thể có persistent token repository |
| Khi session bị xóa | Người dùng cần đăng nhập lại nếu không còn cơ chế khác | Token hợp lệ có thể tạo một authentication/session mới |
| Thu hồi | Invalidate/xóa session | Cần xóa/thu hồi token và xử lý session hiện tại |

Không cấu hình hai cơ chế remember-me cùng lúc nếu chưa xác định rõ cơ chế nào chịu trách nhiệm xác thực lại và cơ chế nào chỉ kéo dài session. Hai cơ chế có thể tạo cookie, xử lý logout và timeout khác nhau.

Nếu yêu cầu là “giữ session hiện tại lâu hơn”, SpringSessionRememberMeServices là hướng tích hợp phù hợp. Nếu yêu cầu là “sau khi session mất hoặc trình duyệt khởi động lại, người dùng có thể được xác thực lại từ token”, cần đánh giá remember-me token của Spring Security với chính sách bảo mật, rotation và revocation tương ứng.

## 11. Session fixation và thay đổi session ID khi đăng nhập

Kéo dài thời hạn session không được làm suy yếu cơ chế chống session fixation. Khi người dùng đăng nhập thành công, Spring Security có thể áp dụng chiến lược session fixation protection để thay đổi session ID hoặc tạo session mới theo cấu hình.

Remember-me chỉ nên quyết định thời hạn sau khi xác thực thành công. Không dùng session ID trước đăng nhập như một token đăng nhập lâu dài và không tự sao chép ID cũ sang cookie remember-me.

Kiểm thử cần xác nhận:

- Session ID được xử lý theo chiến lược session fixation của Spring Security.
- Trạng thái cần giữ qua đăng nhập được migrate theo cơ chế bảo mật.
- Remember-me timeout được áp dụng cho session sau xác thực.
- Session ID cũ không còn dùng được nếu chiến lược yêu cầu đổi ID.

Không gọi thủ công changeSessionId hoặc tạo session mới trong nhiều nơi mà không phối hợp với Spring Security; điều đó có thể tạo hai lần đổi ID hoặc làm mất trạng thái xác thực.

## 12. Logout phải thu hồi cả session dài hạn

Khi người dùng chọn remember-me, session có thể sống lâu hơn đáng kể. Vì vậy logout phải vô hiệu hóa session phía server, không chỉ xóa cookie trên trình duyệt.

Với Spring Security Servlet, cấu hình logout tiêu chuẩn có thể xử lý việc xóa SecurityContext và invalidate session:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class LogoutSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            );
        return http.build();
    }
}
~~~

Đây là cấu hình khung minh họa. Nếu ứng dụng đã có SecurityFilterChain, hãy bổ sung logout vào chain hiện tại thay vì khai báo một chain cạnh tranh. Giữ CSRF protection và dùng POST cho thao tác logout theo chính sách Spring Security.

Nếu ứng dụng tự triển khai logout handler, cần bảo đảm:

1. Session trong repository bị invalidate hoặc delete.
2. SecurityContext được xóa.
3. Cookie session bị hết hạn với đúng tên, Path và Domain.
4. Các phiên khác của cùng principal chỉ bị thu hồi nếu người dùng chọn “đăng xuất khỏi mọi thiết bị” hoặc chính sách yêu cầu.
5. Audit event không chứa session ID hoặc cookie thô.

Vì SpringSessionRememberMeServices kéo dài session hiện tại thay vì cấp một token độc lập, xóa session đúng cách sẽ kết thúc cơ chế remember-me đó. Nếu ứng dụng đồng thời dùng token remember-me khác, logout cần thu hồi token đó theo cơ chế riêng.

## 13. Đăng xuất khỏi một thiết bị và mọi thiết bị

Ứng dụng nhiều phiên có thể cung cấp hai hành động:

- Đăng xuất thiết bị hiện tại: invalidate session gắn với cookie request hiện tại.
- Đăng xuất khỏi mọi thiết bị: tìm các session theo principal đã xác thực rồi thu hồi từng phiên theo repository API.

Không dùng getAllPrincipals() để thực hiện logout mọi thiết bị. Principal đã biết từ Authentication; dùng findByPrincipalName(principal) để lấy các phiên liên quan. Phải kiểm tra quyền và xử lý trường hợp một session mới được tạo đồng thời với thao tác thu hồi.

Nếu yêu cầu “logout mọi nơi” phải ngăn cả request đăng nhập đồng thời hoặc token cũ được tái sử dụng, cần thêm cơ chế thu hồi cấp tài khoản như authentication version, account session generation hoặc token revocation. Việc xóa snapshot các session hiện có không tự động ngăn một phiên mới được tạo ngay sau đó.

## 14. Rủi ro bảo mật của session được ghi nhớ lâu

Session tồn tại lâu làm tăng khoảng thời gian một cookie bị đánh cắp có thể được sử dụng. Một số biện pháp:

- Chỉ cho phép remember-me trên thiết bị cá nhân đáng tin cậy.
- Cung cấp lựa chọn rõ ràng; không bật alwaysRemember nếu không có lý do.
- Dùng cookie Secure, HttpOnly và SameSite phù hợp.
- Bắt buộc HTTPS.
- Duy trì CSRF protection khi xác thực bằng cookie.
- Có khả năng xem và thu hồi session theo thiết bị.
- Thu hồi session khi đổi mật khẩu, khóa tài khoản hoặc phát hiện rủi ro theo chính sách.
- Cân nhắc xác thực lại cho thao tác nhạy cảm, kể cả khi session còn hợp lệ.
- Không lưu session ID hoặc token trong localStorage, URL hay log.

Remember-me không nên được hiểu là miễn xác thực cho mọi thao tác. Một session dài hạn có thể cho phép truy cập ứng dụng thường xuyên, nhưng thao tác đổi mật khẩu, thay thông tin thanh toán hoặc thay đổi quyền vẫn có thể yêu cầu xác thực gần đây hoặc bước xác minh bổ sung.

## 15. Kiểm thử vòng đời remember-me

Kiểm thử nên dùng repository thật hoặc môi trường tích hợp gần production, đồng thời xác nhận cả session timeout và cookie:

| Kịch bản | Thao tác | Điều cần xác nhận |
| --- | --- | --- |
| Không chọn remember-me | Đăng nhập không gửi checkbox | Timeout thông thường được giữ |
| Chọn remember-me | Đăng nhập có checkbox | Session được đặt thời hạn dài theo service |
| alwaysRemember=true | Đăng nhập không gửi checkbox | Service vẫn áp dụng remember-me |
| Request tiếp theo | Gửi lại cookie session | Repository tìm được session và cập nhật truy cập |
| Redis/JDBC expiration | Chờ theo timeout test | Session hết hạn theo chính sách thực tế |
| Cookie hết hạn hoặc mất | Không gửi cookie | Session phía server không tự khôi phục quyền truy cập |
| Logout | Gửi POST logout | Session bị invalidate và cookie bị xóa |
| Logout mọi thiết bị | Thu hồi session theo principal | Các phiên đã tìm được không còn hợp lệ |
| Session fixation | Đăng nhập với session trước đó | Session ID được thay đổi theo chiến lược bảo mật |
| Nhiều instance | Đăng nhập ở A, truy cập ở B | Cả hai instance thấy cùng timeout và trạng thái |
| Rolling deployment | Phiên bản mới và cũ cùng đọc session | Serializer và cấu hình timeout tương thích |

Không dùng sleep ngắn rồi giả định session hết hạn chính xác. TTL, cleanup và scheduler có thể có độ trễ. Trong test, đặt timeout nhỏ ở repository test, chờ điều kiện có giới hạn và xác nhận trạng thái qua API session.

## 16. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Checkbox được chọn nhưng timeout không đổi | RememberMeServices chưa được đăng ký hoặc tên tham số không khớp | Kiểm tra SecurityFilterChain và form |
| Mọi người dùng đều được ghi nhớ | alwaysRemember=true | Đặt false nếu cần lựa chọn từng lần đăng nhập |
| Session vẫn hết hạn sớm | Repository TTL hoặc cấu hình khác ghi đè timeout | Kiểm tra session metadata và TTL thực tế |
| Cookie biến mất sau khi đóng browser | Cookie là session cookie hoặc chính sách browser | Xác định yêu cầu lưu cookie riêng với timeout server |
| Cookie còn nhưng session không tồn tại | Repository đã hết hạn/xóa session | Yêu cầu đăng nhập lại; không tin cookie một mình |
| Logout không kết thúc phiên | Chỉ xóa cookie, chưa invalidate repository session | Dùng logout handler và kiểm tra repository |
| Một instance nhớ, instance khác không | Cấu hình timeout, serializer hoặc repository khác nhau | Đồng bộ cấu hình toàn cụm |
| Dữ liệu session tích tụ | Timeout remember-me quá dài và cleanup không phù hợp | Theo dõi dung lượng và điều chỉnh chính sách |

Khi điều tra, kiểm tra theo thứ tự: remember-me parameter trong request, RememberMeServices thực tế được Spring Security sử dụng, maxInactiveInterval sau đăng nhập, dữ liệu repository, TTL/expiration của backend và thuộc tính cookie trên response.

## 17. Nguyên tắc triển khai

- Dùng SpringSessionRememberMeServices khi mục tiêu là kéo dài session do Spring Session quản lý.
- Đăng ký service trong Spring Security remember-me DSL.
- Giữ alwaysRemember=false nếu người dùng cần lựa chọn trên form.
- Phân biệt idle timeout của session với thời hạn cookie và absolute lifetime.
- Kiểm tra Redis/JDBC repository thực sự lưu thời hạn mới.
- Không coi remember-me là session vĩnh viễn hoặc cơ chế khôi phục sau khi session bị xóa.
- Giữ session fixation protection, CSRF và cookie security.
- Logout phải invalidate session phía server và xóa cookie phù hợp.
- Nếu dùng token-based remember-me cùng lúc, thiết kế rõ việc phát hành, xác thực và thu hồi từng loại credential.
- Kiểm thử nhiều instance, timeout, logout, cookie và rolling deployment.

SpringSessionRememberMeServices cho phép Spring Security điều chỉnh vòng đời HttpSession do Spring Session quản lý khi người dùng chọn ghi nhớ đăng nhập. Nó kéo dài thời gian không hoạt động của phiên hiện tại, trong khi repository và cookie vẫn quyết định khả năng truy cập thực tế. Muốn triển khai an toàn, cần đồng bộ timeout, TTL, cookie, logout và chính sách thu hồi; đồng thời phân biệt rõ cơ chế này với remember-me token có khả năng xác thực lại sau khi session cũ không còn tồn tại.
