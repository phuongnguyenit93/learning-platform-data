# Xác thực là gì và giải quyết vấn đề nhận diện chủ thể như thế nào?

> **Phạm vi:** Khái niệm xác thực (authentication) và cách Spring Security nhận biết chủ thể gửi yêu cầu trong ứng dụng web Servlet. Bài học dùng username/password để minh họa; cùng nguyên tắc tin cậy cũng áp dụng cho session, token và danh tính dịch vụ.

## 1. Từ một HTTP request, hệ thống biết ai đang gọi bằng cách nào?

Một request như `GET /api/orders/501` tự nó không nói ai là người gửi. HTTP truyền URL, method, header và body; tất cả trường do client tùy ý cung cấp, chẳng hạn `?userId=42` hoặc `X-User-Id: 42`, chỉ là **lời khai**. Nếu máy chủ tin ngay lời khai này, người A có thể sửa thành ID của người B rồi giả danh B.

**Xác thực (authentication)** là quá trình kiểm tra bằng chứng để quyết định liệu yêu cầu có thể được gắn với một **chủ thể (principal)** mà hệ thống tin cậy hay không. Chủ thể có thể là tài khoản người dùng, tài khoản dịch vụ hoặc một workload. Với đăng nhập bằng mật khẩu, hệ thống kiểm tra người gọi có biết mật khẩu phù hợp với tài khoản được khai hay không; với khóa hoặc token, hệ thống kiểm tra loại bằng chứng tương ứng. Chỉ khi kiểm tra thành công mới coi danh tính ấy là đã xác thực.

Điểm giới hạn cần nhớ: xác thực chứng minh người gọi đáp ứng **cơ chế kiểm chứng đã chọn**, không tự chứng minh họ là ai ngoài đời thực và không bảo đảm bí mật/thiết bị chưa từng bị đánh cắp. Độ tin cậy của kết quả phụ thuộc vào cách cấp, lưu, kiểm tra và bảo vệ credential.

Ví dụ: client gửi `username=an` và `password=...`. Trước khi kiểm tra, `an` chỉ là danh tính được tuyên bố. Sau khi đối chiếu mật khẩu hợp lệ, server có thể tạo một `Authentication` đại diện cho tài khoản `an`. Ở request tiếp theo, ứng dụng cần cơ chế để kiểm tra lại bằng chứng hoặc khôi phục phiên hợp lệ; không thể mặc định mọi request tiếp theo đều đến từ `an`.

### Các thuật ngữ dễ nhầm

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Identity / danh tính** | Hồ sơ hoặc mã định danh mà hệ thống quản lý | User ID `u-42` |
| **Claimed identity / danh tính tự khai** | Giá trị do người gọi đưa ra trước kiểm chứng | Username `an` trong form |
| **Credential / bằng chứng xác thực** | Thông tin hoặc vật sở hữu được dùng để chứng minh quyền sử dụng danh tính | Mật khẩu, khóa riêng, session cookie, bearer token |
| **Principal / chủ thể** | Danh tính mà framework biểu diễn sau khi xử lý cơ chế xác thực; kiểu dữ liệu tùy cơ chế | `UserDetails`, tên người dùng, `Jwt` |
| **Authentication / kết quả xác thực** | Trạng thái/đối tượng mô tả ai đang được coi là chủ thể, bằng chứng và quyền liên quan | `Authentication` trong Spring Security |
| **Authorization / phân quyền** | Kiểm tra chủ thể đã nhận diện có được thực hiện hành động cụ thể hay không | `an` có được đọc đơn hàng 501? |
| **Authority / quyền** | Thuộc tính được dùng khi ra quyết định phân quyền | `ROLE_USER`, `SCOPE_orders.read` |

Tên hiển thị, email, username và mã định danh ổn định không nhất thiết là một. Email có thể thay đổi hoặc chưa được xác minh; trong nghiệp vụ thường nên ánh xạ principal tin cậy về **ID nội bộ ổn định**, thay vì dùng giá trị do client cung cấp làm chủ sở hữu tài nguyên.

## 2. Authentication và authorization giải quyết hai câu hỏi khác nhau

- **Authentication:** "Ai đang gọi và bằng chứng cho danh tính đó đã được kiểm chứng chưa?"
- **Authorization:** "Với danh tính và ngữ cảnh này, họ được phép làm gì đối với tài nguyên cụ thể?"

Giả sử An đăng nhập thành công. Điều đó chỉ cho biết request đang được gắn với tài khoản An theo cơ chế xác thực của hệ thống. Nó **không** chứng minh An có quyền đọc đơn hàng của Bình. Để trả đơn hàng 501, server còn phải kiểm tra quyền đối với đơn hàng đó, chẳng hạn `order.ownerId == authenticatedUserId` hoặc chính sách nghiệp vụ tương đương.

Một lỗi phổ biến là lấy `ownerId` từ query/body rồi so với `order.ownerId`. Kẻ tấn công kiểm soát cả giá trị tự khai ấy, nên kiểm tra trở nên vô nghĩa. Cách đúng là lấy ID chủ thể từ **kết quả xác thực đã được server tin cậy**, sau đó thực hiện kiểm tra phân quyền riêng.

| Tình huống | Câu hỏi xác thực | Câu hỏi phân quyền |
| --- | --- | --- |
| Người chưa đăng nhập đọc trang công khai | Không cần danh tính đăng nhập | Route có cho `permitAll` không? |
| An gửi mật khẩu đúng | Bằng chứng cho tài khoản An có hợp lệ không? | An được truy cập endpoint nào? |
| An đọc đơn hàng của Bình | An đã xác thực, nhưng không phải Bình | An có quyền với **đơn hàng này** không? |
| API service gọi API khác bằng token | Token có đáng tin và còn hiệu lực không? | Service có scope/quyền phù hợp không? |

## 3. Chuỗi xử lý để biến lời khai thành danh tính tin cậy

Ở mức khái niệm, một lượt xác thực có sáu bước. Chi tiết triển khai khác nhau giữa HTTP Basic, form login, session cookie, JWT và OAuth2/OIDC.

1. **Thu thập bằng chứng:** client gửi credential theo giao thức được hỗ trợ. Ví dụ, HTTP Basic mang username/password trong header `Authorization`; form login nhận dữ liệu đăng nhập; API có thể nhận bearer token. Dữ liệu này luôn là **không đáng tin** cho tới khi xác minh.
2. **Xác minh:** thành phần xác thực kiểm tra bằng chứng theo đúng quy tắc. Mật khẩu được so với hash bằng `PasswordEncoder.matches(...)`; token phải được xác minh chữ ký/nguồn cấp, điều kiện thời gian và các claim bắt buộc theo cấu hình; session ID phải ánh xạ đến phiên hợp lệ do server quản lý.
3. **Xác định principal:** khi bằng chứng hợp lệ, hệ thống liên kết nó với tài khoản hoặc service tương ứng; có thể tải thêm thông tin người dùng và các authority.
4. **Tạo kết quả đáng tin:** framework tạo/trả về `Authentication` đã xác thực, mang `principal`, `authorities` và thông tin phù hợp. Không tự đánh dấu "đã xác thực" cho đối tượng được tạo trực tiếp từ dữ liệu client.
5. **Gắn vào ngữ cảnh request:** cơ chế tích hợp đặt kết quả vào `SecurityContext` để các bước xử lý tiếp theo có thể biết principal. Việc lưu để dùng ở request sau tùy chiến lược session/token; không phải cứ có `SecurityContextHolder` là tồn tại đăng nhập vĩnh viễn.
6. **Phân quyền rồi xử lý nghiệp vụ:** Security Filter Chain và/hoặc tầng method/service kiểm tra quyền; controller/service đọc principal đáng tin và chỉ tiếp tục khi chính sách truy cập cho phép.

Minh họa tuyến xử lý thường gặp với username/password:

```text
HTTP request (credential từ client, chưa tin cậy)
    |
    v
Spring Security Filter Chain
    |
    v
Authentication filter
    |  tạo token yêu cầu xác thực
    v
AuthenticationManager (thường là ProviderManager)
    |
    v
AuthenticationProvider (ví dụ DaoAuthenticationProvider)
    |-- UserDetailsService: tìm tài khoản
    |-- PasswordEncoder: kiểm tra mật khẩu với hash
    |
    +-- Sai --> từ chối xác thực / kích hoạt cơ chế phản hồi lỗi
    |
    +-- Đúng --> Authentication đã được xác thực
                         |
                         v
                  SecurityContext
                         |
                         v
                Quyết định phân quyền
                         |
                         v
                  Controller / Service
```

Đây là **luồng khái niệm**, không phải một thứ tự filter cố định cho mọi cấu hình. Từng cơ chế có filter/provider riêng; có trường hợp framework khôi phục `SecurityContext` từ repository mà không yêu cầu nhập lại mật khẩu ở mỗi request.

### Vì sao "chỉ biết username" không đủ?

Username, email hay user ID thường có thể đoán được. Nếu chỉ cần biết ID đã truy cập được dữ liệu, ứng dụng đã biến giá trị định danh công khai thành credential giả. **Định danh trả lời "muốn là ai"; xác thực kiểm tra "có bằng chứng gì để được coi là chủ thể ấy".**

## 4. Những thành phần Spring Security cần nắm

### `SecurityFilterChain`

Trong ứng dụng Spring MVC/Servlet, Spring Security đặt các filter vào đường đi của HTTP request. Filter đọc bằng chứng theo cơ chế cấu hình, quản lý ngữ cảnh bảo mật, xử lý lỗi liên quan và đưa ra/điều phối quyết định truy cập trước khi request tới controller. Các filter cụ thể và thứ tự phụ thuộc phiên bản, cơ chế và cấu hình; không nên tự suy ra rằng một tên filter xuất hiện trong mọi ứng dụng.

### `Authentication`

Đây là interface trung tâm biểu diễn kết quả hoặc yêu cầu xác thực:

- `getPrincipal()`: thông tin chủ thể; không mặc định luôn là `String` hay entity trong database.
- `getCredentials()`: credential liên quan; sau xác thực có thể đã bị xóa khỏi bộ nhớ để giảm rủi ro lộ bí mật.
- `getAuthorities()`: tập các `GrantedAuthority` được cấp cho chủ thể.
- `isAuthenticated()`: một cờ trạng thái trên token; **không đủ một mình để kết luận đây là người dùng đăng nhập thực sự**, vì Spring Security còn có token anonymous. Hãy để cơ chế authorization của framework, chẳng hạn `authenticated()`, xác định yêu cầu.
- `getName()`: tên đại diện của principal; có thể là username hoặc giá trị khác tùy implementation.

`UsernamePasswordAuthenticationToken` trước khi được kiểm tra có thể chứa username/password nhưng chưa đáng tin; sau khi provider xác minh thành công, framework trả một token xác thực hợp lệ. Tránh tạo token từ dữ liệu request rồi tự đặt cờ xác thực thành `true`.

### `AuthenticationManager` và `AuthenticationProvider`

`AuthenticationManager` định nghĩa thao tác `authenticate(...)`; `ProviderManager` là implementation phổ biến, điều phối các `AuthenticationProvider`. Mỗi provider hỗ trợ một kiểu chứng thực nhất định và có thể xác thực thành công, từ chối, hoặc nhường cho provider phù hợp khác. Một application có thể dùng nhiều provider mà không đồng nghĩa mọi provider đều kiểm tra cùng một loại credential.

Ví dụ `DaoAuthenticationProvider` dành cho username/password dựa trên `UserDetailsService` và `PasswordEncoder`. `UserDetailsService` **tải thông tin người dùng**, không tự kiểm tra mật khẩu; trách nhiệm kiểm tra do provider và encoder thực hiện.

### `SecurityContext` và `SecurityContextHolder`

`SecurityContext` chứa `Authentication` đang được sử dụng. Trong mô hình Servlet đồng bộ, `SecurityContextHolder` thường dùng chiến lược gắn ngữ cảnh với thread hiện hành; framework thiết lập và dọn ngữ cảnh quanh request. Không lưu principal vào biến static chung, không mặc định thread nền/async tự kế thừa ngữ cảnh, và không lấy `SecurityContextHolder` của request khác.

`SecurityContextRepository` quyết định khả năng đọc/lưu ngữ cảnh giữa các request, thường gắn với HTTP session hoặc chiến lược không lưu trạng thái. **Xác thực ở request hiện tại** và **duy trì đăng nhập qua nhiều request** là hai vấn đề liên quan nhưng khác nhau.

## 5. Ví dụ Spring Boot: phân biệt client tự khai và principal đã xác thực

Ví dụ dưới đây là ứng dụng Servlet dùng **HTTP Basic** và một tài khoản in-memory để quan sát luồng. Yêu cầu: Java 17+, dự án Spring Boot có Spring Web (MVC) và Spring Security, dùng Gradle hoặc Maven do Spring Initializr tạo. Đây là demo học tập; mật khẩu mẫu không dùng cho môi trường thật.

Tạo file `src/main/java/com/example/authdemo/AuthDemoApplication.java`:

```java
package com.example.authdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails an = User.withUsername("an")
                .password(passwordEncoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(an);
    }
}

@RestController
class IdentityController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }
}
```

**Cách chạy:** sử dụng wrapper có sẵn trong dự án Spring Boot:

```bash
./gradlew bootRun
```

Trên Windows PowerShell có thể dùng `.\gradlew.bat bootRun`; nếu dự án dùng Maven thì chạy `./mvnw spring-boot:run` (Windows: `.\mvnw.cmd spring-boot:run`). Không gọi `javac` trực tiếp cho file trên vì các import Spring cần dependency từ build tool.

Mở terminal khác và chạy:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
curl -i http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
```

Hai lệnh đầu trả về **body lần lượt là** `pong` và `principal=an`. Hai lệnh sau, trong cấu hình Basic này, nhận **HTTP 401** vì không có hoặc có credential sai. Dùng `curl.exe` thay cho `curl` nếu PowerShell ánh xạ tên `curl` sang lệnh khác. Header và body lỗi có thể khác tùy phiên bản/cấu hình; không dựa vào chuỗi lỗi cụ thể để xác định kết quả.

**Giải thích:** `/public/ping` được `permitAll()` nên không cần một principal đã đăng nhập. `/me` yêu cầu `authenticated()`. Khi nhận Basic credential, Spring Security kiểm tra tài khoản `an` bằng `UserDetailsService` và so khớp password với hash BCrypt; nếu hợp lệ, controller nhận một `Authentication` và dùng `getName()`. Dù client thử thêm `?userId=admin` vào URL, đoạn controller vẫn lấy tên từ kết quả xác thực, không tin tham số tự khai.

**Điều demo chứng minh và chưa chứng minh:** Nó chứng minh đường đi xác thực và principal đã được kiểm tra. Nó chưa có endpoint kiểm tra chủ sở hữu tài nguyên, phân quyền role riêng, MFA, persistence người dùng thực, rate limit hay cơ chế chống brute force. HTTP Basic gửi thông tin đăng nhập được mã hóa Base64 (không phải mã hóa bí mật); triển khai thực tế **phải dùng HTTPS**.

## 6. Nhận diện chủ thể qua các cơ chế khác nhau

| Cơ chế | Bằng chứng được kiểm tra | Danh tính tin cậy hình thành như thế nào? | Lưu ý |
| --- | --- | --- | --- |
| **Form login + session** | Username/password lúc đăng nhập; session ID hợp lệ ở các request sau | Server xác thực lúc login rồi khôi phục ngữ cảnh từ session/repository khi phù hợp | Cookie phải được bảo vệ; cần quản lý CSRF, session fixation, hết hạn, logout |
| **HTTP Basic** | Username/password gửi trong header cho request | Provider xác minh mỗi lần cần xử lý Basic credential | Base64 không thay thế TLS; trình duyệt/client có thể lưu lại credential |
| **Bearer JWT** | Token được kiểm tra chữ ký và các điều kiện như issuer, audience, thời hạn theo cấu hình | Resource server tạo `Authentication` từ token **đã được xác minh** | Chỉ thấy header `Bearer` hoặc giải mã payload không phải xác thực |
| **Opaque access token** | Token được tra cứu/introspect tại nguồn tin cậy theo cấu hình | Principal/authority suy ra từ kết quả xác minh token | Cần xét hiệu lực, hủy token, lỗi kết nối nguồn xác minh |
| **OIDC login** | Luồng đăng nhập với Identity Provider và kết quả giao thức được kiểm tra | Ứng dụng tin cậy subject do nhà cung cấp danh tính đã cấu hình xác thực | Phân biệt ID token, access token và session cục bộ; kiểm tra issuer/subject |

Không có cách nào chỉ cần "nhận một chuỗi giống token" là đủ. Mỗi loại bằng chứng có quy tắc kiểm tra và phạm vi tin cậy riêng. Với service-to-service, principal có thể là **client/service identity**, không nhất thiết là người dùng cuối; mọi authorization phía sau phải hiểu đúng loại chủ thể đó.

## 7. Điều xảy ra khi xác thực thất bại hoặc thiếu quyền

- **Chưa có bằng chứng hoặc bằng chứng sai:** request cần xác thực sẽ được đưa vào luồng yêu cầu đăng nhập/challenge. Với REST dùng HTTP Basic trong demo, kết quả điển hình là `401 Unauthorized` cùng challenge phù hợp. Với form login, phản hồi có thể là chuyển hướng tới trang đăng nhập hoặc báo lỗi form.
- **Đã xác thực nhưng không được quyền:** một endpoint hoặc service có thể trả `403 Forbidden`. Ví dụ tài khoản An đăng nhập đúng nhưng endpoint quản trị yêu cầu quyền khác.
- **Tài nguyên công khai:** route `permitAll` có thể hoạt động mà không cần tài khoản đăng nhập.
- **Request có anonymous token:** Spring Security có thể đặt `AnonymousAuthenticationToken` vào context cho mục đích nội bộ; sự hiện diện của `Authentication` hoặc cờ `isAuthenticated()` trên token **không tự chứng minh người thật đã đăng nhập**. Spring Security dùng cơ chế phân biệt anonymous khi áp dụng `authenticated()`.

Bảng phân biệt sau giả sử endpoint bảo vệ có cấu hình thích hợp; nó không ngụ ý mọi hệ thống luôn trả đúng cùng mã HTTP:

| Người gọi | Endpoint | Kết quả điển hình |
| --- | --- | --- |
| Anonymous | Công khai | Cho phép |
| Anonymous hoặc credential không hợp lệ | Yêu cầu đăng nhập | 401 hoặc bắt đầu luồng login |
| Đã xác thực, đủ quyền | Tài nguyên cho phép | Tiếp tục xử lý; thường 2xx nếu nghiệp vụ thành công |
| Đã xác thực, thiếu quyền | Tài nguyên hạn chế | 403 hoặc quyết định từ chối tương ứng |

## 8. Những sai lầm làm hệ thống nhận diện sai chủ thể

1. **Tin user ID/email/header do client gửi.** Những giá trị này có thể mô tả danh tính mong muốn nhưng không phải chứng cứ. Chỉ tin identity từ cơ chế xác thực đã được cấu hình và bảo vệ; nếu dùng header từ reverse proxy, cần thiết lập ranh giới tin cậy và ngăn client gọi thẳng backend hoặc tự giả mạo header.
2. **Lấy được user trong database rồi coi như login thành công.** `findByUsername` chỉ tìm hồ sơ; có tài khoản không đồng nghĩa người gọi sở hữu tài khoản. Kiểm tra credential vẫn bắt buộc.
3. **Kiểm tra `isAuthenticated()` đơn lẻ.** Anonymous token là ngoại lệ dễ gây hiểu nhầm. Dùng quy tắc `authenticated()`, `hasAuthority(...)` hoặc cơ chế authorization chính thức.
4. **Đồng nhất xác thực với quyền truy cập mọi bản ghi.** Endpoint yêu cầu đăng nhập vẫn có thể bị lộ dữ liệu nếu không kiểm tra sở hữu đơn hàng, tenant, role hoặc scope phù hợp.
5. **Dùng mật khẩu thô, `{noop}` hoặc tự so sánh hash sai cách.** Lưu mật khẩu bằng encoder thích hợp như BCrypt/Argon2 với tham số được quản trị; khi login dùng phương thức kiểm tra của encoder, không so sánh trực tiếp plaintext với chuỗi hash.
6. **Chấp nhận JWT vì nó giải mã được.** Base64URL chỉ là encoding; phải xác minh chữ ký, issuer, audience, thời hạn và những điều kiện giao thức/cấu hình cần thiết. Một token đúng chữ ký nhưng cấp cho API khác vẫn có thể không hợp lệ tại API này.
7. **Bỏ qua vòng đời credential và session.** Cookie bị lộ, token bị đánh cắp hoặc password bị phishing khiến kẻ xấu có thể đóng vai chủ thể hợp lệ theo cơ chế kiểm tra. Cần HTTPS, bảo vệ secret, chính sách hết hạn/thu hồi, MFA khi phù hợp, giám sát và chống đoán mật khẩu. Với xác thực dựa cookie tự động gửi bởi browser, cần đánh giá bảo vệ CSRF.
8. **Ghi credential vào log hoặc chuyển context sai thread.** Không log plaintext password, bearer token, session cookie. Context gắn với request/thread phải được framework quản lý; tác vụ bất đồng bộ cần truyền ngữ cảnh một cách có chủ đích.

Một điểm tinh tế: `Authentication.getName()` thường là username, nhưng nhiều hệ thống cần **ID người dùng bất biến** để kiểm tra chủ sở hữu. Thiết kế principal/custom user object sao cho service lấy được ID đáng tin cậy; không lấy ID từ tham số HTTP chỉ vì controller không có sẵn ID.

## 9. Cách kiểm chứng một hệ thống có thật sự nhận diện đúng người gọi

Thử lần lượt các tình huống sau trong môi trường học tập:

1. Gửi request tới endpoint công khai khi chưa đăng nhập: được cho phép.
2. Gửi request tới endpoint bảo vệ khi không có credential: bị yêu cầu xác thực.
3. Gửi mật khẩu sai: bị từ chối, không tạo danh tính đã xác thực cho tài khoản đó.
4. Gửi credential đúng: controller quan sát được principal tương ứng.
5. Giữ nguyên credential của A nhưng đổi tham số `userId` hoặc header `X-User-Id` thành B: principal phía server **vẫn phải là A**.
6. Cho A đọc tài nguyên sở hữu bởi B: chỉ được phép khi **quy tắc phân quyền nghiệp vụ** cho phép; đăng nhập thành công của A không thay thế bước này.
7. Quan sát log ở mức cần thiết: biết kết quả xác thực và quyết định truy cập, nhưng không hiển thị password, token hay cookie.

Khi chẩn đoán lỗi, hỏi theo thứ tự: **client đã cung cấp loại bằng chứng nào? filter phù hợp có chạy không? provider/validator xác minh ra sao? principal/authority được tạo từ đâu? context có được đặt/khôi phục cho request hiện tại không? cuối cùng authorization dựa vào cái gì?** Câu hỏi này giúp phân biệt lỗi xác thực, lỗi duy trì phiên và lỗi phân quyền.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Client gửi `X-User-Id: 42`. Server có được khẳng định người gọi là tài khoản 42 không?  
**Đáp án:** Không. Header do client tự đặt là lời khai; chỉ một cơ chế xác thực tin cậy mới cung cấp bằng chứng phù hợp.

**Câu 2.** `UserDetailsService.loadUserByUsername("an")` trả về một tài khoản. Chức năng đăng nhập đã hoàn thành chưa?  
**Đáp án:** Chưa. Đây mới là bước tải dữ liệu; password/token vẫn cần được xác minh bằng provider/validator thích hợp.

**Câu 3.** An đăng nhập đúng nhưng truy cập đơn hàng riêng của Bình bị chặn. Xác thực có "sai" không?  
**Đáp án:** Không nhất thiết. Authentication có thể đã thành công; authorization đối với tài nguyên cụ thể từ chối.

**Câu 4.** Vì sao `Authentication` có mặt trong `SecurityContextHolder` chưa đủ để nói có người dùng đã đăng nhập?  
**Đáp án:** Context có thể chứa anonymous authentication; cần cơ chế phân biệt/trust resolver hoặc authorization policy của Spring Security.

## Ghi nhớ cốt lõi

**Nhận diện đáng tin cậy = danh tính được khai + bằng chứng được xác minh + kết quả được gắn đúng vào request.** Spring Security cung cấp các thành phần để làm điều đó nhất quán: filter xử lý cơ chế đăng nhập, manager/provider kiểm tra bằng chứng, `Authentication` biểu diễn principal và `SecurityContext` đưa principal đến tầng xử lý. **Xác thực trả lời "ai"; phân quyền phải trả lời tiếp "được làm gì với tài nguyên này".**

### Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)