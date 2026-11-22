# Ranh giới tin cậy với proxy và ngăn client tự giả mạo header (Spring Security pre-authentication)

## 1. Mục tiêu và cảnh báo quan trọng

**Tiền xác thực (pre-authentication)** là mô hình trong đó hệ thống đứng trước ứng dụng (identity-aware proxy, SSO gateway, reverse proxy tích hợp xác thực, servlet container...) đã xác minh người dùng. Spring Security nhận một danh tính được chuyển giao, ánh xạ danh tính đó sang tài khoản/quyền của ứng dụng và áp dụng phân quyền.

Trong mô hình chuyển danh tính bằng HTTP header, **header tự nó không phải bằng chứng xác thực**. Mọi HTTP client đều có thể gửi một header giống hệt header do proxy tạo. Vì vậy:

> Chỉ tin header chứa danh tính khi đã bảo đảm nó được phát hành hoặc ghi đè bởi một proxy đã xác thực người dùng, và backend chỉ nhận traffic qua đường tin cậy đó.

Spring Security nói rõ `RequestHeaderAuthenticationFilter` **không xác thực người dùng bằng mật khẩu/token**; filter chỉ đọc principal từ header. Nếu request đến backend mang header giả mạo nhưng không đi qua hàng rào tin cậy, ứng dụng có thể xem kẻ gửi là bất kỳ người dùng nào.

Sau bài này, bạn cần giải thích và triển khai được: ranh giới tin cậy ở từng hop; cơ chế giả mạo header; trách nhiệm của proxy so với backend; cấu hình Spring Security pre-auth; biện pháp chống truy cập trực tiếp backend, trùng/lệch tên header và lỗi trong chuỗi proxy; cùng bộ test chứng minh không thể mạo danh.

## 2. Ranh giới tin cậy là gì?

**Trust boundary** là ranh giới giữa nơi có thể nhận dữ liệu do bên ngoài tự khai và nơi dữ liệu đã được kiểm tra theo một cơ chế cụ thể. Với pre-auth header, ranh giới nằm tại **điểm thực hiện xác thực và tái tạo header**, thường là một identity gateway hoặc reverse proxy.

~~~text
       VÙNG KHÔNG TIN CẬY                 VÙNG ĐƯỢC KIỂM SOÁT
┌──────────────────────────┐      ┌──────────────────────────────┐
│ Browser, mobile, curl    │      │ Identity-aware proxy / SSO   │
│ Có thể tự gửi:           │      │ 1. Xác thực credential       │
│ X-Verified-User: admin   ├─────>│ 2. Loại bỏ header từ client   │
│ X-Verified-Roles: root   │ HTTPS│ 3. Ghi lại user đã xác minh  │
└──────────────────────────┘      └──────────────┬───────────────┘
                                                │ Đường nội bộ có kiểm soát:
                                                │ ACL + TLS/mTLS nếu có thể
                                                v
                                   ┌──────────────────────────────┐
                                   │ Spring Boot / Spring Security│
                                   │ Đọc X-Verified-User          │
                                   │ Nạp quyền của chính app      │
                                   │ Kiểm tra authorization       │
                                   └──────────────────────────────┘
~~~

**Phân chia trách nhiệm:**

| Thành phần | Việc phải làm | Việc không được mặc định |
|---|---|---|
| Client | Gửi credential tới gateway, sử dụng ứng dụng | Được tự khẳng định danh tính bằng `X-Verified-User` |
| Gateway/SSO proxy | Xác thực, loại bỏ header giả, tạo header chuẩn, chặn request chưa xác thực | Tin `X-Verified-User` do client gửi |
| Hạ tầng mạng | Giới hạn backend chỉ nhận kết nối từ gateway đã duyệt, mã hóa và xác minh kết nối nội bộ theo yêu cầu | Coi mọi máy trong VPC/Kubernetes cluster đều đáng tin |
| Backend Spring Security | Đọc danh tính **đã đi qua gateway**, ánh xạ user/authorities, phân quyền từng request | Tự cho rằng header hoặc `X-Forwarded-For` chứng minh danh tính |
| Identity store | Xác định tài khoản, trạng thái và nhóm/quyền theo chính sách | Tin vào một trường `role=ADMIN` do client điều khiển |

### “Tin proxy” phải có căn cứ

Tin cậy là **thuộc tính của toàn bộ đường đi** chứ không phải thuộc tính của tên header. Header `X-Verified-User` trên Internet và cùng header trên kết nối được giới hạn tới proxy đáng tin có cú pháp giống nhau nhưng ý nghĩa bảo mật khác nhau.

Nếu backend vẫn công khai cổng `8080`, một người dùng có thể bỏ qua gateway và gửi thẳng:

~~~http
GET /me HTTP/1.1
Host: backend.example.test:8080
X-Verified-User: alice
~~~

Nếu Spring chỉ dùng filter đọc header, request đó có thể xác thực thành `alice` dù client chưa từng vượt qua cơ chế đăng nhập ở gateway. Đó là **authentication bypass / header spoofing**.

## 3. Cơ chế của Spring Security pre-auth

Ở Servlet stack, các thành phần phổ biến là:

1. `RequestHeaderAuthenticationFilter` lấy username từ một request header (mặc định là `SM_USER`, có thể đổi thành `X-Verified-User`).
2. Filter tạo `PreAuthenticatedAuthenticationToken` và gửi đến `AuthenticationManager`.
3. `PreAuthenticatedAuthenticationProvider` nhận token và dùng `AuthenticationUserDetailsService` (hoặc `UserDetailsByNameServiceWrapper`) để nạp tài khoản/trạng thái và quyền trong ứng dụng.
4. `SecurityContext` chứa `Authentication`, còn `authorizeHttpRequests` quyết định request có được vào endpoint không.

~~~text
Trusted header → RequestHeaderAuthenticationFilter
              → PreAuthenticatedAuthenticationToken
              → PreAuthenticatedAuthenticationProvider
              → UserDetails / GrantedAuthority
              → SecurityContext
              → AuthorizationFilter
~~~

**Điều không xảy ra:** Spring Security không tự liên hệ gateway để chứng minh người dùng thật sự là `alice` khi chỉ cấu hình `RequestHeaderAuthenticationFilter`. Việc nạp `UserDetails("alice")` cũng không kiểm chứng ai đã gửi header. Ứng dụng có thể kiểm tra rằng username tồn tại, nhưng **không chứng minh người gửi HTTP có quyền sử dụng username đó**.

Phải phân biệt **authentication** (gateway chứng thực danh tính) và **authorization** (Spring kiểm tra user/role/permission đối với tài nguyên). Đây là hai bước khác nhau; app vẫn phải phân quyền độc lập.

## 4. Các con đường giả mạo và cấu hình sai thường gặp

### 4.1. Proxy chuyển tiếp nguyên header từ client

Ví dụ cấu hình nguy hiểm:

~~~nginx
# SAI: chỉ chuyển thẳng upstream mà không tái tạo danh tính.
location / {
    proxy_pass http://internal_app;
}
~~~

Nếu backend tin `X-Verified-User`, request từ Internet có thể cung cấp header đó và được chuyển tiếp nguyên. **Chỉ thêm `RequestHeaderAuthenticationFilter` không tạo bảo vệ.**

Một biến thể khác cũng nguy hiểm:

~~~nginx
# SAI: lấy "danh tính đã xác thực" trực tiếp từ client.
proxy_set_header X-Verified-User $http_x_verified_user;
~~~

Biến `$http_x_verified_user` là giá trị header từ request client; không chứng minh proxy đã xác thực nó. Giá trị phải đến từ kết quả xác thực của gateway (`$remote_user` sau khi NGINX Basic authentication thành công, claim từ SSO đã kiểm chứng, hoặc một cơ chế danh tính an toàn tương đương).

### 4.2. Bỏ qua proxy và vào backend trực tiếp

Các đường phổ biến: public IP/port, node port, load balancer khác, Kubernetes Service nội bộ nhưng pod trong cluster bất kỳ có thể gọi, debug/management port, port-forward cấu hình không kiểm soát, đường từ VPN hoặc mạng nội bộ có quyền rộng.

Với header-based pre-auth, **network isolation là điều kiện cần**: không có đường từ client hoặc workload không được phép đến backend. Nếu có nhiều ingress/gateway, **mọi đường** phải áp dụng cùng chính sách. `ClusterIP` riêng không tự động là chính sách phân quyền mạng; cần firewall/security group/Kubernetes NetworkPolicy/service mesh có hiệu lực.

Mã hóa TLS giữa proxy và backend giảm nguy cơ bị nghe lén/sửa header trên đường truyền. **mTLS với kiểm tra client certificate** còn giúp backend nhận diện đúng proxy. Chỉ bật HTTPS mà không kiểm tra peer được phép vẫn chưa chứng minh người gửi là gateway.

### 4.3. Trùng hoặc biến thể tên header

HTTP header name không phân biệt chữ hoa/chữ thường. Cần xét các biến thể như:

~~~http
X-Verified-User: alice
x-verified-user: admin
X_Verified_User: admin
~~~

Các proxy, framework, servlet container có thể xử lý trùng tên, gạch dưới, dấu gạch ngang, khoảng trắng và cách gộp header khác nhau; `request.getHeader(...)` có thể trả một giá trị theo quy tắc của container. Có nguy cơ **gateway kiểm tra một biến thể, backend lại đọc biến thể khác**.

Biện pháp: tại edge, loại bỏ header chứa danh tính/role được gửi từ bên ngoài theo một chính sách chuẩn hóa thống nhất; từ chối duplicate/ambiguous headers; gateway tự sinh **một tên header duy nhất**; kiểm thử trọn đường đi qua đúng proxy/container đang triển khai. Không chỉ dựa vào việc đổi tên header thành tên khó đoán.

### 4.4. Tự khai vai trò hoặc IP

Không tin vào các header như `X-Role: ADMIN`, `X-User-Groups: superuser`, `X-Is-Admin: true` nếu gateway chưa bảo đảm nguồn và app chưa kiểm chứng/mapping. Ngay cả username hợp lệ, **quyền vẫn phải được kiểm tra** bằng dữ liệu đáng tin cậy.

`X-Forwarded-For`, `Forwarded`, `X-Real-IP` chủ yếu mang thông tin đường đi của request, **không phải chứng chỉ danh tính**. Header IP có thể do client tự chèn nếu edge không làm sạch. Không dùng riêng `X-Forwarded-For` hay `request.getRemoteAddr()` sau khi rewrite proxy headers để chứng minh người dùng đã đăng nhập.

### 4.5. Sai chính sách lỗi và phiên đăng nhập

- Identity service/gateway bị timeout mà reverse proxy cho request đi tiếp (`fail open`) là lỗi nghiêm trọng; yêu cầu fail closed.
- Backend có form login, Basic hoặc endpoint bypass do `securityMatcher`/route cấu hình sai có thể mở thêm đường không qua mô hình pre-auth.
- Ứng dụng có session lưu `Authentication` cũ trong khi proxy thay đổi user/logout: cần thiết kế đồng bộ phiên, phát hiện principal change và invalidation. Với API chỉ cần pre-auth mỗi request, cấu hình stateless thường dễ kiểm soát hơn.
- Không coi CORS là hàng rào chống spoof: `curl`, script server-to-server và direct HTTP client không chịu sự giới hạn của browser CORS.

## 5. Kiến trúc phòng thủ nhiều lớp

Thực hiện theo thứ tự, không dựa vào một cơ chế duy nhất:

1. **Xác thực ở edge:** gateway bắt buộc xác thực mọi request tới đường cần bảo vệ; kiểm tra session/token/IdP, thời gian hết hạn và trạng thái account; nếu xác thực thất bại, không chuyển request vào backend.
2. **Xóa rồi tạo lại:** loại bỏ/ghi đè tất cả inbound identity headers và role headers, kể cả bản trùng/lệch cách viết; chỉ điền `X-Verified-User` từ kết quả xác thực thành công. Không copy từ `$http_...` của client.
3. **Khóa đường tới backend:** firewall, security group, NetworkPolicy hoặc mesh policy chỉ cho gateway được xác minh kết nối tới cổng ứng dụng; chặn direct path và alternate ingress.
4. **Bảo vệ từng hop:** HTTPS client→gateway, TLS hoặc mTLS gateway→backend tùy mức độ rủi ro; quản lý certificate, trust roots, DNS và danh tính peer đúng cách.
5. **Fail closed trong app:** thiếu header, user không tồn tại, account disabled hoặc thiếu authority phải bị từ chối; không fallback sang anonymous có quyền hoặc role mặc định nâng cao.
6. **Quyền do app kiểm soát:** nạp roles/permissions từ nguồn được quản lý; ánh xạ external subject sang internal user có định danh ổn định; không cấp admin chỉ vì client gửi `X-Role`.
7. **Kiểm thử đường đi thật:** test trực tiếp cổng backend, request giả mạo tới edge, header trùng/alias, auth outage, multi-hop và thay đổi session; audit định kỳ khi thay đổi ingress/service mesh.

Nếu kiến trúc không bảo đảm được **proxy là nguồn duy nhất** của identity header, cân nhắc backend tự xác thực một bằng chứng có mật mã như **JWT/OIDC access token** với kiểm tra chữ ký, issuer, audience, expiration, scopes và ràng buộc transport theo yêu cầu. Cách đó chuyển từ “tin header username thuần” sang “xác thực một token”; không được nhầm một chuỗi username với một JWT đã được kiểm chứng.

## 6. Ví dụ NGINX: proxy thực sự xác thực và ghi đè username

Ví dụ dưới đây dùng **NGINX HTTP Basic authentication** để làm rõ nơi danh tính được xác minh. Trong doanh nghiệp có thể dùng SSO/OIDC gateway thay cho Basic; nguyên tắc lọc inbound header, tạo từ verified identity và khóa backend là như nhau.

Giả định:
- Public hostname: `app.example.test`.
- Backend chỉ lắng nghe trên mạng nội bộ: `10.30.0.15:8080` và firewall chỉ cho phép NGINX gọi.
- NGINX có TLS certificate hợp lệ, file password của gateway đã được cấu hình an toàn.
- Spring backend sẽ đọc đúng `X-Verified-User`.

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        # Xác thực trước khi cho request đi tới backend.
        auth_basic "Application Gateway";
        auth_basic_user_file /etc/nginx/auth/users.htpasswd;

        # Tạo danh tính TỪ KẾT QUẢ XÁC THỰC của NGINX.
        # Không lấy từ $http_x_verified_user của client.
        proxy_set_header X-Verified-User $remote_user;

        # Loại bỏ các header khác có thể bị app dùng nhầm làm role/user.
        proxy_set_header X-Verified-Roles "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header Authorization "";

        # Tái tạo forwarding metadata tại trust boundary.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;

        proxy_pass http://10.30.0.15:8080;
    }
}
~~~

**Vì sao đây là một ví dụ có ranh giới rõ ràng?**

- NGINX chỉ tạo `$remote_user` khi Basic authentication đã chấp nhận credential. `proxy_set_header X-Verified-User $remote_user` **thay giá trị từ client** bằng kết quả đã xác thực.
- `proxy_set_header ... ""` khiến NGINX không chuyển header đó tới upstream; việc xóa `Authorization` giúp không vô tình chuyển Basic credential tới backend.
- `X-Forwarded-For $remote_addr` ở đây đặt giá trị theo peer NGINX thấy, tránh giữ chuỗi do bên ngoài tự chèn. Nếu phía trước còn load balancer hợp lệ, cần lập cấu hình trusted upstream/real IP riêng và kiểm tra đúng trust chain; không sao chép mù quáng.
- **NGINX snippet chỉ là một phần**, không thiết lập firewall, mTLS, quản lý mật khẩu, giám sát hoặc phát hiện mọi header alias. Những điều đó phải cấu hình trong hệ thống triển khai thực tế.

**Giới hạn:** NGINX Basic authentication không thay thế một thiết kế SSO hiện đại, MFA hay quản trị phiên doanh nghiệp. Với `auth_request`/OIDC, identity phải đến từ **response của hệ thống xác thực đã được xác nhận**, không phải từ request header client. Luồng thiếu user hoặc auth service lỗi phải bị chặn. Dù có proxy đáng tin, dùng các kênh TLS/mTLS phù hợp trên đường proxy→backend.

## 7. Ví dụ Spring Boot 3.x / Spring Security 6.x / Java 17+

Ví dụ ứng dụng Servlet dưới đây dùng đúng API pre-auth. Nó minh họa rằng Spring **tin username nhận ở header** và chỉ nạp quyền cho một user được biết tới. Cấu hình chỉ an toàn khi kết hợp với ranh giới mạng và proxy trong phần trước; **khởi động app riêng lẻ trên cổng public rồi gửi header bằng tay là không an toàn**.

### 7.1. Dependency

Trong ứng dụng Maven Spring Boot 3.x đã có `spring-boot-starter-parent` hoặc Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
~~~

Dùng Java 17+ và project Spring Boot 3.x với source đặt dưới `src/main/java/com/example/preauth/`.

### 7.2. Điểm khởi động

File `DemoApplication.java`:

~~~java
package com.example.preauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityFilterChain và pre-auth provider

File `SecurityConfiguration.java`:

~~~java
package com.example.preauth;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    UserDetailsService users() {
        return username -> {
            // Ví dụ demo: nạp user/role từ allowlist.
            // Production phải tích hợp nguồn danh tính/quyền nội bộ.
            if (!"alice".equals(username)) {
                throw new UsernameNotFoundException("Unknown internal user");
            }
            // Password không được sử dụng bởi pre-authentication provider.
            return new User(
                    "alice",
                    "",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, UserDetailsService users) throws Exception {

        var provider = new PreAuthenticatedAuthenticationProvider();

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
                detailsService = new UserDetailsByNameServiceWrapper<>(users);

        provider.setPreAuthenticatedUserDetailsService(detailsService);

        var preAuth = new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(new ProviderManager(provider));

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(
                                new Http403ForbiddenEntryPoint()))
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .addFilterBefore(
                        preAuth, UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

**Giải thích các quyết định quan trọng:**

- `PreAuthenticatedAuthenticationProvider` không kiểm tra password. `UserDetailsByNameServiceWrapper` lấy tên trong `PreAuthenticatedAuthenticationToken` để tìm `UserDetails`; ở production, phải dùng directory/database/identity mapping đáng tin cậy thay vì allowlist `alice`.
- `RequestHeaderAuthenticationFilter` đặt `principalRequestHeader` rõ ràng; không mặc định tin mọi header tên tương tự hoặc một trường role tự khai.
- `setExceptionIfHeaderMissing(false)` cho phép request đi tiếp khi thiếu principal; **`anyRequest().authenticated()` vẫn từ chối** request chưa được xác thực. `Http403ForbiddenEntryPoint` trả HTTP 403 thay vì chuyển sang login form. Không nhầm “filter tiếp tục” với “được cấp quyền”.
- `SessionCreationPolicy.STATELESS` tránh dùng phiên Spring lưu danh tính cũ giữa các request trong ví dụ. Nếu ứng dụng dùng session, cần thiết kế riêng chuyện logout, principal change, invalidation và phối hợp cookie của gateway.
- `httpBasic` và `formLogin` bị tắt để không tạo cơ chế đăng nhập cạnh tranh không nằm trong mô hình pre-auth. Tùy hệ thống, cơ chế khác có thể hợp lệ nhưng phải có thiết kế chứng minh rõ ràng.
- **Không đăng ký `preAuth` làm `@Bean Filter` độc lập** nếu đã tự thêm vào `SecurityFilterChain`: Spring Boot có thể tự đăng ký Servlet `Filter` bean và làm filter chạy hai lần ở hai chain khác nhau. Ở đây filter được tạo cục bộ rồi gắn đúng một chỗ.
- Ví dụ **không tắt CSRF mặc định**. Với trình duyệt có cookie/credential tự gửi, CSRF vẫn phải được đánh giá cho thao tác thay đổi trạng thái; việc đặt stateless không tự tạo miễn nhiễm CSRF.
- Password để chuỗi rỗng là giá trị kỹ thuật trong `UserDetails` demo; pre-auth không đọc hay so sánh nó. Không dùng ví dụ này làm cơ chế lưu mật khẩu trong production.

### 7.4. Endpoint kiểm tra principal

File `IdentityController.java`:

~~~java
package com.example.preauth;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/me")
    Map<String, Object> me(Authentication auth) {
        List<String> roles = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList();
        return Map.of(
                "username", auth.getName(),
                "authorities", roles);
    }
}
~~~

Khi request đi **qua gateway đã xác thực `alice`**, phản hồi có hai trường sau (thứ tự key JSON không được bảo đảm):

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
~~~

Để chạy trong một dự án Maven Spring Boot 3.x đầy đủ, sử dụng `mvn spring-boot:run` hoặc build bằng `mvn package` rồi chạy JAR với `java -jar target/<ten-jar>.jar`. Đây là mã nguồn trong **ba file Java của ứng dụng Spring Boot**, không phải một file độc lập chạy bằng `javac` trần; nó cần dependency và gateway đã cấu hình.

**Chú ý về thử nghiệm nội bộ:** Nếu gọi thẳng backend với `X-Verified-User: alice`, ứng dụng ví dụ sẽ có khả năng trả nội dung `alice`. Đó là minh chứng vì sao việc **chặn kết nối trực tiếp bằng mạng** là bắt buộc; không nên coi nó là bài test đã chống spoof thành công.

## 8. Chứng minh an toàn bằng request thực tế

Với NGINX cấu hình đúng, `alice` có trong file Basic-auth của gateway, và backend chỉ cho phép truy cập từ NGINX:

### 8.1. Client chưa đăng nhập nhưng tự nhận là admin

~~~bash
curl -i -H 'X-Verified-User: admin' https://app.example.test/me
~~~

**Kỳ vọng:** HTTP 401 do gateway chưa nhận Basic credential; backend không được thấy identity header `admin`. Không để client chỉ cần thay `X-Verified-User` là vượt qua gateway.

### 8.2. Client là alice nhưng cố gửi header mạo danh người khác

~~~bash
curl -i --user alice \
  -H 'X-Verified-User: admin' \
  https://app.example.test/me
~~~

`curl` yêu cầu nhập password nếu chưa được cung cấp. Khi credential `alice` hợp lệ, **gateway phải ghi đè** header thành `alice`; backend chỉ nhận `X-Verified-User: alice`. Kết quả `/me` phải là `alice`, không phải `admin`. Nếu gateway từ chối request trùng header, cũng là hành vi an toàn; hành vi cụ thể phải được định nghĩa và test.

### 8.3. Bypass gateway để gửi header hợp lệ đến backend

~~~bash
curl -i -H 'X-Verified-User: alice' \
  http://10.30.0.15:8080/me
~~~

**Kỳ vọng từ một máy client/unauthorized workload:** kết nối bị firewall/NetworkPolicy/mTLS access policy chặn. Chỉ nhận HTTP 403 từ app chưa đủ chứng minh an toàn vì header `alice` là user hợp lệ; nếu kết nối lọt qua, Spring có thể xem request là `alice`.

### 8.4. Thiếu header hoặc user không được ứng dụng nhận biết

Khi gọi từ một proxy hợp lệ nhưng không cung cấp identity header, hoặc cung cấp username không tồn tại: ứng dụng không tạo principal có quyền và trả từ chối (trong cấu hình minh họa: HTTP 403). Nếu auth service không sẵn sàng, gateway trả lỗi/fail closed; không được đưa request chưa xác thực vào backend.

### 8.5. Kịch bản trùng/lệch header

Đặt test qua **đúng NGINX/Ingress/CDN/servlet container production**:

~~~bash
curl -i --user alice \
  -H 'X-Verified-User: admin' \
  -H 'x-verified-user: bob' \
  -H 'X_Verified_User: carol' \
  https://app.example.test/me
~~~

Không có giá trị do client tự khai nào được trở thành principal. Có thể từ chối ngay ở edge, hoặc chuẩn hóa sạch và tạo lại **một** identity `alice`. Các hành vi xử lý header phải được kiểm tra thực nghiệm vì phụ thuộc proxy và container.

### 8.6. Bảng test bắt buộc

| Trường hợp | Kết quả mong đợi | Lớp cần kiểm tra |
|---|---|---|
| Không đăng nhập nhưng gửi `X-Verified-User` | Gateway từ chối, không vào app | Gateway |
| Đã đăng nhập alice nhưng gửi header admin | App nhận alice hoặc gateway từ chối | Header sanitize + gateway |
| Kết nối thẳng cổng backend và gửi header alice | Kết nối bị chặn ở hạ tầng | NetworkPolicy / firewall / mTLS |
| Thiếu identity header từ proxy | Không có authenticated principal | Spring Security |
| Username không tồn tại trong source nội bộ | Không được cấp quyền | UserDetails service |
| Header role `ADMIN` từ client | Không có quyền admin được cấp | Gateway + authorization |
| Hai header cùng tên khác chữ hoa/thường | Reject hoặc xử lý chính tắc an toàn | Proxy + servlet container |
| Header dấu gạch dưới/alias | Reject hoặc loại bỏ hoàn toàn | Gateway parser/normalizer |
| Auth service mất kết nối | Request không lọt vào backend | Gateway fail closed |
| Logout hoặc đổi user khi giữ kết nối cũ | Không giữ `Authentication` sai người | Gateway + session strategy |
| Multi-hop: client tự gửi `X-Forwarded-For` | Không đổi trust decision | Proxy chain |
| Route phụ như `/actuator`, WebSocket, gRPC, admin | Áp cùng chính sách hoặc có cơ chế độc lập | Ingress/port routing |
| Cookie + request POST qua trình duyệt | Bảo vệ CSRF phù hợp mô hình phiên | Spring Security |

## 9. `Forwarded` và `X-Forwarded-*` không phải identity header

Nhiều hệ thống Spring Boot chạy sau proxy bật:

~~~properties
server.forward-headers-strategy=native
~~~

Hoặc chọn `framework` để Spring xử lý `ForwardedHeaderFilter`. Mục đích chính là khôi phục scheme, host, port, địa chỉ client và prefix để tạo redirect/link đúng khi đi qua reverse proxy.

Nhưng `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` đều có thể bị **client tự khai** nếu edge không xóa/ghi đè. Tài liệu Spring Framework khuyến cáo proxy ở trust boundary phải loại bỏ `Forwarded` và `X-Forwarded-*` từ bên ngoài trước khi tự tạo giá trị hợp lệ.

**Điểm dễ nhầm:**
- `ForwardedHeaderFilter` không biến `X-Verified-User` thành một bằng chứng xác thực.
- `server.forward-headers-strategy` không thay thế một auth gateway.
- Cấu hình NGINX `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` có thể bảo toàn chuỗi IP do client khai nếu chưa có quy tắc trust chain; xác định chính xác proxy nào được phép thêm hop.
- Nếu dùng IP allowlist, phải áp dụng tại mạng/transport hoặc thiết bị nhận diện đúng trusted hops, không đọc bừa một header IP do client truyền.

Không dựa vào `request.getRemoteAddr()` đã được `ForwardedHeaderFilter`/container xử lý từ header chưa được vệ sinh để kết luận kết nối đến từ trusted gateway.

## 10. Tình huống nhiều proxy và Kubernetes

### Chuỗi nhiều hop

~~~text
Client → CDN → Load Balancer → Auth Gateway → Service Mesh → Spring Boot
             ^           ^             ^              ^
             Mỗi hop phải biết chính xác mình tin ai và ghi/đọc header gì.
~~~

Có thể có nhiều điểm thêm `X-Forwarded-*`, nhưng **phải có một ranh giới rõ ràng** chịu trách nhiệm xác thực user, loại bỏ identity header từ các hop trước và phát hành identity header cho backend. Nếu một proxy trung gian có thể bị gọi trực tiếp hoặc có thể thêm `X-Verified-User` tùy ý, mô hình vẫn bị phá vỡ.

Trong Kubernetes:
- Public Ingress phải nằm trước xác thực; tránh các Ingress khác đi vòng qua gateway vào cùng Service.
- `ClusterIP` không giới hạn Pod khác trong cluster theo danh tính; dùng NetworkPolicy mặc định deny ingress rồi allow duy nhất các pod/namespace gateway được phép.
- Nếu dùng service mesh, chính sách peer authentication/mTLS và authorization phải match đúng workload identity; không dựa vào địa chỉ IP Pod thay đổi.
- Chú ý `/actuator`/management port, probe, admin port và route nội bộ; phân định rõ endpoint nào cần pre-auth, endpoint nào có policy riêng.
- Không chỉ bảo vệ một hostname nếu backend cũng xuất hiện dưới một hostname/port khác.

## 11. Lỗi thường gặp và cách xử lý

1. **Chỉ cấu hình filter và tin rằng header là bảo mật:** dựng/kiểm chứng gateway thực sự xác thực, strip và overwrite header, đồng thời chặn backend trực tiếp.
2. **Dùng `$http_x_verified_user` trong NGINX:** đó là giá trị từ client; chuyển sang `$remote_user` sau xác thực hợp lệ hoặc identity do SSO gateway xác minh.
3. **Dựa vào “tên header bí mật”:** client có thể đoán, dò, nhìn request hoặc tài liệu; bảo mật phải nằm ở nguồn tạo và kênh truyền.
4. **Gắn role trực tiếp từ header:** client có thể tự đặt `ROLE_ADMIN`; chỉ nạp quyền từ nguồn nội bộ hoặc claim đã được kiểm chứng và map theo policy.
5. **Filter bị gọi hai lần:** tránh đăng ký `Filter` dưới dạng `@Bean` cho servlet container đồng thời `addFilterBefore` vào Spring Security chain mà không quản lý thứ tự/đăng ký.
6. **Thêm fallback login không kiểm soát:** `formLogin`/Basic/JWT khác có thể vô tình tạo cơ chế bypass gateway; thiết kế tách route/chain rõ, kiểm thử đầy đủ.
7. **App trả 200 cho direct spoof:** phải sửa network access/mTLS và proxy chain. Chỉ sửa controller để kiểm tra username tồn tại không giải quyết việc mạo danh user hợp lệ.
8. **Nhầm client IP với proxy identity:** `X-Forwarded-For` có thể là dữ liệu không tin cậy, NAT cũng làm nhiều người dùng chung IP; không dùng thay cho user authentication.
9. **Header thiếu nhưng vẫn đi tiếp có quyền:** đặt `anyRequest().authenticated()`, không cấp role cho anonymous, kiểm tra policy và custom filters.
10. **Quên logout/đổi principal khi dùng session:** cân nhắc stateless hoặc phát hiện thay đổi principal và hủy phiên phù hợp.
11. **Cho phép header trùng/khác parser:** test gateway/container thực tế, loại bỏ hoặc reject giá trị mơ hồ và có thể bị request smuggling.
12. **Tin mọi workload nội bộ:** tách quyền mạng và identity giữa các dịch vụ; một Pod bị chiếm quyền không được tự giả là gateway.

## 12. Checklist review và vận hành

- [ ] Có sơ đồ mọi đường client→backend, bao gồm ingress phụ, port quản trị và multi-hop.
- [ ] Mọi request vào endpoint bảo vệ được gateway xác thực **trước** khi chuyển tiếp.
- [ ] Edge loại bỏ/ghi đè header danh tính, quyền và forwarded metadata do client tự khai.
- [ ] Backend chỉ nhận kết nối từ gateway/workload được phép; có test negative cho đường bypass.
- [ ] TLS/mTLS và kiểm tra peer identity được triển khai theo rủi ro và chính sách mạng.
- [ ] UserDetails/authorities được nạp, ánh xạ theo nguồn đáng tin; unknown/disabled users bị từ chối.
- [ ] Spring Security bảo vệ đủ route và HTTP methods; không có login fallback mở ngoài chủ đích.
- [ ] Proxy/header parser reject hoặc xử lý an toàn duplicate, casing, underscore và các alias.
- [ ] Auth service timeout/error fail closed; log và alert đủ để phát hiện sự cố.
- [ ] Session/logout/CSRF được kiểm tra theo cách dùng cookie, SPA, API hay browser.
- [ ] Integration test dùng đường đi production, bao gồm case giả mạo qua curl và direct-backend attempt.
- [ ] Không log access token, Basic password hoặc credential; log danh tính đã xác minh cùng request ID và hop provenance.

## 13. Ghi nhớ

**Không phải “header này tên gì?”, mà là “ai được quyền tạo header này, và backend kiểm chứng đường đi bằng gì?”**

`RequestHeaderAuthenticationFilter` là bộ chuyển danh tính vào `SecurityContext`, **không phải bộ chống giả mạo header**. Hệ thống an toàn cần cả ba điều kiện: **gateway xác thực và viết lại header**, **backend chỉ nhận traffic từ gateway được kiểm soát**, **Spring Security tiếp tục kiểm soát user/authorities và quyền truy cập**. Thiếu một trong ba, một username trong header vẫn có thể là lời tự khai của attacker.

## Tài liệu tham khảo

- [Spring Security — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): bản chất pre-auth và giới hạn của request-header authentication.
- [Spring Security API — RequestHeaderAuthenticationFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): `principalRequestHeader`, `exceptionIfHeaderMissing` và cảnh báo header forgery.
- [Spring Security API — AbstractPreAuthenticatedProcessingFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): xử lý principal, `SecurityContext` và failure behavior.
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): thứ tự `SecurityFilterChain` và cách gắn authentication filter.
- [Spring Framework — Forwarded Headers, Security Considerations](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): sanitization `Forwarded` và `X-Forwarded-*` tại edge.
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`.
- [NGINX — proxy_set_header](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header): ghi đè và loại bỏ request headers chuyển tới upstream.
- [NGINX — auth_request](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html): ủy quyền/auth upstream, `auth_request_set` và quy tắc chấp nhận/từ chối subrequest.
