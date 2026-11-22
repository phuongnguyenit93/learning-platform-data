# Tài khoản mặc định, mật khẩu sinh tự động và giới hạn sử dụng khi phát triển

## 1. Vì sao vừa cài Spring Security thì API đã đòi đăng nhập?

Một ứng dụng Spring Boot có Controller GET /hello thường có thể được gọi ngay khi chưa bổ sung bảo mật. Khi thêm **spring-boot-starter-security**, cùng request có thể nhận **401 Unauthorized** trong curl hoặc bị chuyển hướng đến trang login khi truy cập bằng trình duyệt. Log khởi động xuất hiện dòng **Using generated security password: ...**.

Đây là hành vi **auto-configuration** của Spring Boot: ứng dụng web có bảo vệ HTTP mặc định và thường có một tài khoản thử để developer quan sát quá trình đăng nhập. Điều này hữu ích cho bước khởi tạo nhưng **không phải hệ thống quản lý người dùng hay cấu hình production**.

Bài này giải thích tài khoản được tạo ra như thế nào, password xuất hiện ở đâu, khi nào mật khẩu đổi, cách dùng khi học, cách thay đổi bằng properties, các trường hợp auto-configuration rút lui và giới hạn của việc dùng tài khoản thử.

**Phạm vi:** Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet. Phiên bản Boot/Security khác có thể thay đổi cấu hình và cách ghi log; hãy đọc tài liệu của phiên bản thực tế. WebFlux có cơ chế cấu hình reactive riêng.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Xác định nguồn username/password và trạng thái lưu trữ của tài khoản mặc định.
2. Tìm password được sinh từ log của lần khởi động đang chạy.
3. Giải thích vì sao browser có thể hiện login page còn curl nhận HTTP 401.
4. Phân biệt thay **SecurityFilterChain** với thay **UserDetailsService**.
5. Sử dụng **spring.security.user.name/password/roles** đúng phạm vi.
6. Phân tích trường hợp Boot không còn tạo user mặc định do bean riêng hoặc dependency mới.
7. Thử chính sách /public, /private, /admin và giải thích 200, 401, 403, 404.
8. Biết những thay đổi cần thiết trước khi triển khai cho người dùng thật.

## 2. Có hai cơ chế mặc định cần phân biệt

Nhiều người tưởng chỉ có một “cấu hình security mặc định”. Với Spring Boot 3.3 Servlet, cần phân biệt:

| Nhóm | Auto-configuration liên quan | Trách nhiệm |
| --- | --- | --- |
| **Bảo vệ HTTP** | SecurityAutoConfiguration và SpringBootWebSecurityConfiguration | Tạo chính sách bảo vệ web khi chưa có SecurityFilterChain riêng |
| **Nguồn người dùng thử** | UserDetailsServiceAutoConfiguration | Tạo UserDetailsService/in-memory user nếu chưa có nguồn xác thực thay thế |
| **Sự kiện xác thực** | DefaultAuthenticationEventPublisher | Phát sự kiện xác thực theo tích hợp mặc định |

Nhóm thứ nhất quyết định **endpoint nào cần đăng nhập**, nhóm thứ hai cung cấp **tài khoản để kiểm tra credentials**. Chúng được tự động cấu hình theo những điều kiện khác nhau.

Vì vậy:

- Khai báo một **SecurityFilterChain** bean riêng sẽ làm cấu hình **web security mặc định** của Boot rút lui, nhưng **không tự động xóa user mặc định**.
- Khai báo một **UserDetailsService** bean riêng làm Boot dừng tạo UserDetailsService mặc định, nhưng **không tự động biến endpoint thành public**.
- AuthenticationProvider hoặc AuthenticationManager bean riêng cũng có thể làm UserDetailsService auto-configuration rút lui.
- Một số module OAuth2/SAML2 trên classpath cũng ảnh hưởng việc Boot tạo user mặc định.

Đây là mối quan hệ quan trọng nhất của bài: **policy HTTP** và **nguồn authentication** là hai thành phần độc lập, dù chúng phối hợp trong một request.

## 3. Tài khoản mặc định của Spring Boot 3.3

Khi Spring Security có trên classpath, ứng dụng web chưa thay thế các bean liên quan và các điều kiện khác được thỏa, Boot có thể tạo một tài khoản duy nhất:

| Thuộc tính | Giá trị hoặc cơ chế mặc định |
| --- | --- |
| Username | **user** |
| Password | **Chuỗi ngẫu nhiên được sinh khi khởi động ứng dụng** |
| Kho lưu trữ | **InMemoryUserDetailsManager** trong bộ nhớ tiến trình |
| Role mặc định | **USER**, tương ứng authority thông dụng ROLE_USER |
| Đăng nhập | Form login hoặc HTTP Basic tùy request/cấu hình |
| Tồn tại trong database? | **Không**; đây không phải tài khoản trong bảng users nghiệp vụ |

Tài khoản này không tự có email, số điện thoại, MFA, khả năng reset password, quản lý nhiều user hoặc quyền quản trị nghiệp vụ. Vai trò mặc định thường là USER, **không phải ADMIN**. Không suy ra một URL tên /admin được bảo vệ bởi ADMIN chỉ vì tên đường dẫn đó.

### 3.1. Password được in như thế nào?

Ở Spring Boot 3.3, khi mật khẩu tự sinh, log khởi động có thể chứa thông điệp mức **WARN**:

~~~text
Using generated security password: 78fa095d-3f4c-48b1-ad50-e24c31d5cf35

This generated password is for development use only. Your security configuration must be updated before running your application in production.
~~~

Đây là **ví dụ định dạng log**, không phải password dùng chung cho mọi ứng dụng. Mật khẩu thật phải lấy từ **đúng lần khởi động của đúng instance**.

Nếu log không hiển thị, không được vội kết luận security đã bị tắt. Có thể password đã được chỉ định trong properties, UserDetailsService mặc định đã rút lui hoặc logging không cho thấy cảnh báo từ **org.springframework.boot.autoconfigure.security**. Trong Spring Boot 3.3, nếu điều chỉnh logging, cần cho phép thông điệp WARN ở nhóm này mới thấy password được sinh.

### 3.2. Password có thay đổi sau restart?

Khi Boot tự sinh, một lần tạo ApplicationContext mới **thường sinh password khác**. Do đó password của lần chạy hôm qua không phải credential ổn định cho phiên hôm nay. Tài khoản nằm trong bộ nhớ của từng process; nhiều replica có thể có mật khẩu tự sinh khác nhau.

Password ngẫu nhiên này:

- Không phải mật khẩu tài khoản root/admin của database.
- Không phải signing key của JWT.
- Không phải API key cấp cho client ứng dụng.
- Không phải password của khách hàng thật.
- Không phải bí mật được phân phối nhất quán giữa các server.

### 3.3. Vì sao việc in password trong log là rủi ro?

Password trong log là **credential thật của ứng dụng đang chạy**, dù được tạo ngẫu nhiên. Log có thể bị thu thập bởi terminal, công cụ CI, Docker/container runtime, agent quan sát hay hệ thống tập trung. Ai đọc được log phù hợp và truy cập được ứng dụng có thể thử sử dụng password đó.

Không chia sẻ công khai screenshot chứa generated password; không đẩy nó vào issue/ticket hoặc tài liệu vận hành. Cảnh báo “for development use only” nhấn mạnh rằng cơ chế này được thiết kế cho **thử nghiệm cục bộ**, không dành cho tài khoản thực ngoài Internet.

## 4. Bảo vệ HTTP mặc định có hành vi gì?

Với ứng dụng Servlet web có Spring Security nhưng không khai báo SecurityFilterChain thay thế, Spring Boot thường yêu cầu xác thực cho các endpoint ứng dụng, bao gồm **/error**. Nó cung cấp lựa chọn **HTTP Basic** hoặc **form login** theo content negotiation.

Một số tình huống:

- **curl** gửi request không có credentials và yêu cầu JSON thường nhận **HTTP 401**.
- **Browser** gửi Accept ưu tiên HTML có thể được chuyển hướng **302** tới trang login.
- Đăng nhập đúng nhưng URL không có Controller có thể nhận **404**.
- Nếu có policy role riêng, user đã xác thực nhưng thiếu quyền có thể nhận **403**.
- Một request thay đổi trạng thái không có CSRF token thích hợp có thể bị **403**, dù username/password đúng.

**Authentication** xác định người gửi request có credentials hợp lệ hay không. **Authorization** quyết định người đó được làm gì. Mặc định của Boot là điểm khởi đầu bảo vệ web; không tự xác định ai là chủ sở hữu từng bản ghi.

### 4.1. Actuator không phải ngoại lệ có thể bỏ qua

Nếu dùng Spring Boot Actuator, việc **expose endpoint** và **bảo vệ endpoint** là hai điều kiện riêng. Endpoint health thường có chính sách truy cập riêng, trong khi endpoint management nhạy cảm cần bảo vệ phù hợp.

Khi tự khai báo SecurityFilterChain, bạn chịu trách nhiệm cả chính sách HTTP của ứng dụng và các endpoint Actuator liên quan. Không dựa vào việc Boot trước đó từng bảo vệ management endpoint rồi giả định một chain mới sẽ tự giữ mọi rule cũ.

## 5. Thực hành A: một ứng dụng chỉ có cấu hình Security mặc định

### 5.1. Tạo project

Sử dụng Spring Initializr tạo dự án Java 17+ với Spring Boot 3.3.x, Gradle Groovy DSL và Spring Web/Spring Security. Nếu đang có project Boot và Gradle Wrapper, chỉ cần hai dependency sau trong build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đây là phần dependencies của dự án Boot đã thiết lập plugin và build tool, không phải toàn bộ build.gradle độc lập.

### 5.2. File Java đầy đủ

Tạo file **src/main/java/com/example/defaultsecurity/DefaultSecurityApplication.java**:

~~~java
package com.example.defaultsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DefaultSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(DefaultSecurityApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint() {
        return "private OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Public class cùng tên file chứa Spring Boot entry point. Controller là class package-private trong cùng package, nên được Spring Boot component scan phát hiện. **Ở bước A, chưa tạo bean SecurityFilterChain hoặc UserDetailsService riêng.**

### 5.3. Chạy project và tìm password

Trong thư mục có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell dùng **.\gradlew.bat bootRun**. Tìm dòng Using generated security password trong console khởi động và dùng password của **lần chạy hiện tại**. HTTP Basic gửi credentials dưới dạng Base64, không phải mã hóa an toàn; ví dụ dùng localhost để học, còn hệ thống thật phải dùng HTTPS.

Thử bằng curl:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/public
curl -i -u user http://localhost:8080/public
curl -i -u user http://localhost:8080/private
curl -i -u user http://localhost:8080/admin
~~~

Tham số **-u user** khiến curl hỏi password qua terminal nếu không chỉ định sẵn password. Nhập giá trị sinh trong log. Trên Windows PowerShell, dùng **curl.exe** nếu lệnh curl là alias.

**Bảng kết quả kỳ vọng ở bước A:**

| Request | HTTP status | Ý nghĩa |
| --- | --- | --- |
| /public, không credentials, Accept: application/json | **401** | Mặc định Boot vẫn bảo vệ endpoint tên public |
| /public, có credentials đúng | **200**, public OK | Xác thực thành công |
| /private, có credentials đúng | **200**, private OK | Xác thực thành công |
| /admin, có credentials đúng | **200**, admin OK | Chưa có rule yêu cầu role ADMIN cho URL /admin |
| URL chưa có mapping, credentials đúng | Có thể **404** | Authentication thành công nhưng Controller không tồn tại |

Tên đường dẫn **/admin** không tự tạo rule **hasRole("ADMIN")**. Vì vậy kết quả 200 ở bước A không chứng minh tài khoản user mặc định là admin nghiệp vụ.

Kết quả trên **được suy ra từ cấu hình demo**; không phải log chạy thực tế trong tài liệu này. Nếu môi trường có proxy, cấu hình khác hoặc dependency khác, cần thử lại trên đúng app.

### 5.4. Vì sao browser có thể hiện form login?

Spring Security chọn cơ chế authentication entry point tùy request và content negotiation. Browser gửi Accept ưu tiên HTML thường được chuyển hướng đến form login; client muốn JSON thường nhận HTTP Basic challenge. Hai response này có thể cùng đúng đối với một endpoint được bảo vệ.

## 6. Tùy chỉnh user bằng properties

Spring Boot có ba thuộc tính thường dùng:

| Property | Tác dụng |
| --- | --- |
| **spring.security.user.name** | Username của user mặc định |
| **spring.security.user.password** | Password xác định, thay cho password Boot tự sinh |
| **spring.security.user.roles** | Các role gán cho user mặc định |

Ví dụ trong **src/main/resources/application-local.properties**:

~~~properties
spring.security.user.name=devuser
spring.security.user.roles=USER
~~~

Ví dụ trên không ghi password vào file. Khi chạy profile local, có thể cung cấp password từ biến môi trường **SPRING_SECURITY_USER_PASSWORD** mà Spring Boot ánh xạ sang spring.security.user.password.

Trên Windows PowerShell:

~~~powershell
$env:SPRING_SECURITY_USER_PASSWORD = 'local-demo-pass-123'
.\gradlew.bat bootRun --args='--spring.profiles.active=local'
~~~

Trên Linux/macOS với bash:

~~~bash
SPRING_SECURITY_USER_PASSWORD='local-demo-pass-123' \
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Password trong lệnh chỉ để học tập local; không dùng lại trong hệ thống thật. Shell history và environment có thể lưu dấu thông tin, do đó production cần cơ chế quản lý secret và quy trình triển khai an toàn.

Sau khi cấu hình:

1. Username được Boot tạo là **devuser**, không phải user gốc.
2. Password đến từ biến môi trường, nên không còn cần một generated password ngẫu nhiên cho tài khoản này.
3. Role USER tương ứng với ROLE_USER trong cách cấu hình thông dụng.
4. Vẫn chỉ là **một tài khoản in-memory đơn giản**, không trở thành database user hay SSO.

Thử đăng nhập bằng **curl -i -u devuser http://localhost:8080/private** rồi nhập password local khi được hỏi.

### 6.1. Có đặt password trực tiếp trong application.properties được không?

Về mặt kỹ thuật có thể dùng spring.security.user.password trong file. Nhưng password thật lưu trong source, container image hoặc config chia sẻ dễ bị lộ. Với bài học local, một mật khẩu không nhạy cảm có thể được dùng để nhìn cơ chế, nhưng trước production phải chuyển sang nguồn credentials hoặc identity provider được quản trị.

### 6.2. Có thể thêm nhiều user bằng spring.security.user.* không?

Các property này dùng cho **user mặc định đơn giản**, không phải quản lý một danh sách tài khoản nhiều người. Để tạo nhiều user, thiết kế UserDetailsService riêng, kho user hoặc tích hợp hệ thống danh tính. Không mở rộng bằng các password hard-code rải rác và coi đó là cơ chế quản trị người dùng.

## 7. Khi nào auto-configuration tài khoản rút lui?

Boot 3.3 xét điều kiện tạo **UserDetailsService mặc định** riêng với điều kiện tạo **SecurityFilterChain mặc định**.

| Thay đổi trong ứng dụng | Web security mặc định của Boot | User mặc định |
| --- | --- | --- |
| Chỉ thêm starter-security | Được tạo khi đủ điều kiện | Thường được tạo trong memory |
| Tự tạo **SecurityFilterChain** bean | **Rút lui**, dùng chain do ứng dụng khai báo | **Có thể vẫn tồn tại** |
| Tự tạo **UserDetailsService** bean | Có thể vẫn còn nếu chưa tự tạo chain | **Không tạo nữa** |
| Tự tạo **AuthenticationProvider** bean | Có thể vẫn còn nếu chưa tự tạo chain | **Không tạo nữa** |
| Tự tạo **AuthenticationManager** bean | Có thể vẫn còn nếu chưa tự tạo chain | **Không tạo nữa** |
| Tạo cả chain và nguồn user riêng | Do ứng dụng quy định | Do ứng dụng quy định |
| Có OAuth2 Client/Resource Server/SAML2 module trên classpath | Phụ thuộc cấu hình chain thực tế | UserDetailsService auto-configuration có thể rút lui |

Các module trong nhóm cuối gồm **spring-security-oauth2-client**, **spring-security-oauth2-resource-server** và **spring-security-saml2-service-provider**. Boot 3.3 có điều kiện classpath riêng cho nhóm này; nếu vẫn cần in-memory username/password cùng OAuth2, phải cung cấp UserDetailsService riêng.

**Kết luận về cơ chế:** khai báo SecurityFilterChain không đồng nghĩa đã loại bỏ generated password. Ngược lại, khai báo UserDetailsService không đồng nghĩa đã bỏ bảo vệ URL. Luôn xác định rõ cả hai.

## 8. Thực hành B: thay policy URL, vẫn dùng tài khoản Boot

Giữ nguyên DefaultSecurityApplication.java ở bước A. Tạo thêm file **src/main/java/com/example/defaultsecurity/SecurityRules.java**:

~~~java
package com.example.defaultsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityRules {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

Đây là **file Java thứ hai cùng project và package**, không phải đoạn mã độc lập để chạy một mình. Với @Configuration và @Bean, Spring Boot nhận được SecurityFilterChain do ứng dụng định nghĩa. Khi đó:

- /public được phép truy cập khi chưa đăng nhập.
- /private chỉ yêu cầu đã xác thực.
- /admin yêu cầu role ADMIN.
- Mọi URL khác bị denyAll trong ví dụ.
- HTTP Basic được bật; form login bị tắt cho bài test dễ quan sát 401.

**Chỉ thay chain không xóa UserDetailsService mặc định** nếu không có điều kiện nào khác làm nó rút lui. Khi chưa cấu hình password cố định, ứng dụng có thể vẫn sinh password cho user lúc khởi động.

### 8.1. Kết quả ở bước B

Khởi động lại và đọc password của lượt chạy nếu đang dùng mật khẩu sinh. Thử:

~~~bash
curl -i http://localhost:8080/public
curl -i -H "Accept: application/json" http://localhost:8080/private
curl -i -u user http://localhost:8080/private
curl -i -u user http://localhost:8080/admin
~~~

| Request | HTTP status kỳ vọng | Giải thích |
| --- | --- | --- |
| /public, anonymous | **200**, public OK | permitAll |
| /private, anonymous | **401** | HTTP Basic yêu cầu xác thực |
| /private, user/password đúng | **200**, private OK | authenticated() được đáp ứng |
| /admin, user/password đúng | **403** | User mặc định không có ROLE_ADMIN |

Ở bước A, user mặc định có thể vào URL /admin vì policy chỉ yêu cầu authentication. Ở bước B, user đó bị 403 vì chúng ta đã thêm rule authorization cụ thể. **Điều thay đổi là policy**, không phải mật khẩu.

### 8.2. Đừng nhầm 404 với 401/403

Request tới URL không có Controller có thể trả 404 sau khi vượt qua security filter. Nhưng với **anyRequest().denyAll()**, URL chưa được liệt kê có thể bị từ chối ngay bởi policy trước khi DispatcherServlet tìm handler. Cần đọc cả trạng thái authentication, rule và mapping, không suy đoán từ status đơn lẻ.

## 9. Thực hành C: thay nguồn user bằng UserDetailsService riêng

Để thấy tài khoản sinh tự động biến mất khi có nguồn user riêng, tạo file thứ ba **src/main/java/com/example/defaultsecurity/LocalUsers.java** cùng package:

~~~java
package com.example.defaultsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration(proxyBeanMethods = false)
public class LocalUsers {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-local-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-local-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Đoạn này có hai tài khoản thử hard-code **chỉ dành cho môi trường học tập cách ly**. Không lưu credentials thật trong source, không dùng password này cho production, không triển khai InMemoryUserDetailsManager như hệ thống user doanh nghiệp.

Khi UserDetailsService bean này xuất hiện:

1. Boot không tạo UserDetailsService mặc định có username user nữa.
2. Tài khoản sinh tự động và password sinh tự động không còn là nguồn đăng nhập của ứng dụng.
3. Alice có ROLE_USER; admin có ROLE_ADMIN.
4. SecurityRules vẫn được giữ, nên URL policy không thay đổi.

Thử:

~~~bash
curl -i -u alice http://localhost:8080/private
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
~~~

Nhập password tương ứng khi được hỏi. Kết quả kỳ vọng lần lượt **200**, **403**, **200**. Điều này làm rõ: thay UserDetailsService chuyển **nguồn authentication**, còn SecurityFilterChain quyết định **authorization**.

## 10. Giới hạn của tài khoản mặc định trong development và production

### 10.1. Một tài khoản thử không phải quản lý người dùng

In-memory default user không có quy trình tạo/xóa nhiều tài khoản, xác minh danh tính, reset mật khẩu, vô hiệu hóa tài khoản, MFA, cấp quyền phức tạp hoặc audit quản trị. Nó không phục vụ nhu cầu đăng nhập của khách hàng thật.

### 10.2. Random password trong log vẫn là secret

Mặc dù ngẫu nhiên, password là credential thực sự. Log tập trung, pipeline CI hoặc người có quyền xem log có thể vô tình hoặc cố ý dùng nó. Không để generated password làm cơ chế truy cập production.

### 10.3. Vòng đời không ổn định

Password có thể đổi qua restart. Nhiều instance có thể sinh khác nhau. Bộ nhớ process không thay thế database hoặc identity provider; nó không cung cấp quản lý đồng bộ và thu hồi credentials trên nhiều máy.

### 10.4. Default security không hiểu quyền nghiệp vụ

Boot không tự biết USER A chỉ được đọc đơn hàng của A, hay nhân viên chỉ được duyệt hóa đơn trong hạn mức. Khi triển khai thật, authorization phải dựa vào role/permission và dữ liệu sở hữu, không chỉ yêu cầu authenticated().

### 10.5. Bảo vệ HTTP còn nhiều trách nhiệm

Cần chọn HTTPS/TLS, cookie và session policy, CSRF theo kiểu client, cấu hình CORS, secret management, rate limiting, chống brute-force, quản lý log, cập nhật dependencies, vận hành backup/restore và giám sát. Starter-security hỗ trợ nhiều lớp bảo vệ nhưng **không tự hoàn thành mọi kiểm soát vận hành**.

**Lưu ý:** HTTP Basic gửi password trong header dạng Base64; phải dùng HTTPS nếu chạy trên mạng. Trong browser, các request thay đổi trạng thái có thể cần CSRF token do Spring Security bật CSRF protection mặc định ở Servlet. Không tắt CSRF chỉ để làm POST trả 200 mà chưa phân tích mô hình credentials.

### 10.6. Một chain custom có thể làm thay đổi Actuator

Khi SecurityFilterChain do ứng dụng khai báo, không còn mặc định giả định Boot đang bảo vệ Actuator giúp bạn như trước. Hãy kiểm tra **endpoint exposure** và **access rule**, kể cả những endpoint phục vụ vận hành.

## 11. Các lỗi dễ gặp khi bắt đầu học

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra / hướng xử lý |
| --- | --- | --- |
| Không thấy generated password | Password được cấu hình sẵn, user auto-config rút lui, logging WARN bị ẩn | Kiểm tra beans, classpath, config và log startup đúng instance |
| Thêm SecurityFilterChain nhưng vẫn thấy password | Chỉ thay web policy, chưa thay UserDetailsService mặc định | Xem hai nhóm auto-configuration độc lập |
| Thêm UserDetailsService nhưng URL vẫn bắt login | Nguồn user thay đổi, web policy vẫn bảo vệ endpoint | Đọc SecurityFilterChain đang hoạt động |
| curl nhận 401, browser thấy login page | HTTP Basic và form login theo content negotiation | Xem Accept, entry point, custom handlers |
| Đăng nhập đúng nhưng /admin trả 403 | Thiếu ROLE_ADMIN, hoặc policy khác từ chối | Kiểm tra role/authority và request matchers |
| GET với credential đúng trả 404 | Không có Controller/mapping | Kiểm tra path, method, context path |
| POST có credential đúng trả 403 | Có thể thiếu CSRF token hoặc thiếu quyền | Kiểm tra CSRF và authorization, không disable mù quáng |
| Sau restart password cũ không dùng được | Generated password được tạo mới | Đọc log mới hoặc cấu hình user source rõ ràng |
| Biến spring.security.user.password không có tác dụng | Đã thay nguồn user mặc định bằng bean khác | Kiểm tra UserDetailsService, Provider, Manager |
| Docker replica dùng password khác nhau | Mỗi instance có vòng đời tạo user/password riêng | Dùng identity provider hoặc nguồn danh tính chung |
| User mặc định vào được /admin ở bước A | Tên URL không tự kích hoạt role ADMIN | Tạo rule hasRole theo yêu cầu thật |
| Chọn permitAll cho mọi endpoint để hết lỗi | Bỏ qua bảo vệ thay vì sửa nguồn lỗi | Xác định lỗi authentication hay authorization |

### 11.1. Phân biệt bốn loại response

- **200**: Request được xác thực/phân quyền nếu cần, Controller xử lý thành công.
- **401**: Trong mô hình HTTP Basic, thường thiếu hoặc sai credentials khi tài nguyên yêu cầu authentication.
- **403**: Thường đã đăng nhập nhưng thiếu quyền, hoặc bị từ chối bởi một cơ chế như CSRF.
- **404**: Chưa có tài nguyên/handler tương ứng sau khi request vượt được những bước xử lý trước đó.

Browser có thể trả **302** tới login page thay vì 401 vì cách chọn entry point. Không dựa vào một status đơn lẻ để kết luận auto-configuration hoạt động thế nào.

## 12. Từ cấu hình học tập sang ứng dụng thật

Trước khi đưa ứng dụng ra môi trường có người dùng thật:

1. **Chọn nguồn danh tính thật:** database users được quản lý, LDAP, OIDC/identity provider hoặc cơ chế tổ chức đã chấp nhận.
2. **Bảo vệ credential:** băm mật khẩu bằng PasswordEncoder phù hợp, bảo vệ secret và token, hỗ trợ thu hồi/đổi mật khẩu và MFA khi cần.
3. **Thiết kế chính sách HTTP tường minh:** public/private/admin, method-specific matchers, deny by default và các chain cần thiết.
4. **Kiểm tra quyền trên dữ liệu:** USER A không đọc/sửa được record của USER B dù cả hai đều đăng nhập.
5. **Cấu hình bảo vệ web:** HTTPS, session/cookie, CSRF, CORS, proxy headers và security headers đúng topology.
6. **Rà soát Actuator:** exposure và quyền truy cập endpoint vận hành.
7. **Giám sát và audit:** log sự kiện phù hợp, không log raw password, cảnh báo lạm dụng, rate limiting, kiểm thử bảo mật.
8. **Kiểm tra triển khai:** không còn user thử/password sinh ngoài ý muốn, không có secrets trong log/source, các profile đúng môi trường.
9. **Kiểm thử nhánh thất bại:** anonymous, mật khẩu sai, user bị khóa, thiếu role, truy cập chéo dữ liệu, token hết hạn.
10. **Vận hành dài hạn:** cập nhật dependency, backup, khôi phục, rotation, tài liệu phản ứng sự cố.

Lộ trình này đi từ cơ chế học tập đơn giản tới hệ thống có chính sách cụ thể; không phải tất cả tính năng đều tự xuất hiện chỉ vì đã thêm starter-security.

## 13. Câu hỏi tự kiểm tra

**Câu 1:** Chỉ tạo SecurityFilterChain có tự bỏ tài khoản mặc định của Boot không?  
**Đáp:** Không. UserDetailsService auto-configuration là phần riêng; user mặc định có thể còn được tạo.

**Câu 2:** Vì sao Spring Boot in generated password ở startup?  
**Đáp:** Để developer dùng tài khoản thử cho việc đăng nhập khi bắt đầu học; đó không phải credential production.

**Câu 3:** Password được sinh ngẫu nhiên có phải JWT secret hoặc password database không?  
**Đáp:** Không. Nó là password của user in-memory mặc định.

**Câu 4:** User mặc định có tự có ROLE_ADMIN vì URL tên /admin không?  
**Đáp:** Không. Nếu chưa có policy role riêng, URL có thể chỉ yêu cầu authentication; cần rule authorization.

**Câu 5:** Tại sao UserDetailsService riêng xuất hiện nhưng request vẫn trả 401?  
**Đáp:** Chính sách web vẫn có thể yêu cầu đăng nhập; credentials phải đúng với user store mới và filter chain.

**Câu 6:** POST có Basic credentials đúng nhưng trả 403, có nên tắt CSRF ngay không?  
**Đáp:** Không. Cần kiểm tra CSRF token, session/cookie và chính sách quyền; tắt CSRF không phải cách sửa chung.

**Câu 7:** Một ứng dụng có ba replica, mỗi replica khởi động riêng; có nên dùng generated password để automation không?  
**Đáp:** Không. Password có thể khác nhau, không có nguồn user tập trung và không phù hợp vận hành.

**Câu 8:** Làm sao xác minh ứng dụng không còn user thử ngoài ý muốn trước khi lên production?  
**Đáp:** Kiểm tra dependency, bean UserDetailsService/Provider/Manager, config profiles, security chains và log khởi động đúng deployment.

## 14. Tài liệu chính thức

- Spring Boot 3.3 — Spring Security, tài khoản mặc định, generated password và quy tắc back-off: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Boot 3.3 — Security how-to: https://docs.spring.io/spring-boot/3.3/how-to/security.html
- Spring Security — Getting Started (Servlet): https://docs.spring.io/spring-security/reference/servlet/getting-started.html
- Spring Security — Servlet Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- Spring Security — HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot 3.3 — Externalized configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
