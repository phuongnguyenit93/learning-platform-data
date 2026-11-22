# Phân biệt xác thực, phân quyền và quản lý vòng đời tài khoản

Khi thiết kế hệ thống đăng nhập, ba trách nhiệm thường xuất hiện cùng một luồng nhưng giải quyết ba câu hỏi khác nhau:

- **Xác thực (authentication):** Ai đang gửi yêu cầu và bằng chứng nào cho phép tin vào danh tính đó?
- **Phân quyền (authorization):** Danh tính đã được xác thực có được thực hiện hành động này trên tài nguyên cụ thể hay không?
- **Quản lý vòng đời tài khoản (account lifecycle management):** Tài khoản được tạo, kích hoạt, thay đổi, khóa, khôi phục và kết thúc sử dụng theo chính sách nào?

Trong phạm vi Spring Security, hiểu rõ ranh giới này giúp tránh lỗi “đã đăng nhập thì được làm mọi thứ”, tránh trộn xử lý tài khoản vào bộ lọc bảo mật, và biết phải vô hiệu hóa phiên hoặc token thế nào khi tài khoản đổi trạng thái.

## 1. So sánh ba trách nhiệm

| Khía cạnh | Xác thực (AuthN) | Phân quyền (AuthZ) | Vòng đời tài khoản |
|---|---|---|---|
| Câu hỏi chính | “Bạn là ai?” | “Bạn được làm gì, đối với cái gì?” | “Tài khoản này có đang hợp lệ và được quản trị đúng trạng thái không?” |
| Đầu vào điển hình | Tên đăng nhập, mật khẩu, MFA, chứng chỉ, session cookie, bearer token | Principal đã xác thực, quyền/role, tài nguyên, hành động, chủ sở hữu và ngữ cảnh | Hồ sơ tài khoản, email xác minh, trạng thái, lịch sử bảo mật, yêu cầu đổi/khóa/xóa |
| Kết quả | Thiết lập hoặc từ chối danh tính cho yêu cầu/phiên | Cho phép hoặc từ chối một thao tác | Chuyển trạng thái, cập nhật thông tin/credential, thu hồi quyền truy cập theo chính sách |
| Thời điểm | Đăng nhập hoặc khi xác minh credential/token trong từng request | Mỗi lần truy cập chức năng/tài nguyên được bảo vệ | Trước, trong và sau thời gian tài khoản tồn tại |
| Trách nhiệm điển hình trong Spring | `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, `SecurityContext` | `AuthorizationManager`, `authorizeHttpRequests`, `@PreAuthorize` | Service/domain, kho tài khoản, quy trình xác minh/khôi phục; tích hợp với cơ chế của Spring Security |
| Ví dụ thất bại | Mật khẩu sai, token hết hạn | Đã đăng nhập nhưng thiếu quyền đọc đơn hàng | Tài khoản chưa xác minh, bị đình chỉ hoặc phải thu hồi phiên sau khi nghỉ việc |

**Điểm cốt lõi:** Xác thực thành công **không** hàm ý có quyền với mọi tài nguyên. Một tài khoản còn trong cơ sở dữ liệu **không** hàm ý được phép đăng nhập. Việc đã khóa tài khoản **không** tự động đảm bảo mọi access token phát hành trước đó lập tức hết hiệu lực.

Ví dụ cửa hàng trực tuyến: Linh nhập đúng mật khẩu và MFA để đăng nhập (AuthN); Linh được xem các đơn hàng thuộc về mình nhưng không được sửa đơn của khách khác (AuthZ); khi Linh đổi mật khẩu hoặc bị đình chỉ tài khoản, hệ thống phải áp dụng quy trình đổi credential, thu hồi phiên/token và ghi nhận sự kiện (vòng đời).

## 2. Xác thực: thiết lập danh tính đáng tin cậy

### 2.1. Danh tính, bằng chứng và phiên là các đối tượng khác nhau

- **Identity/principal** là chủ thể mà hệ thống nhận diện, chẳng hạn user ID nội bộ, username hoặc service account ID. Không nên lấy một tham số `userId` do client gửi làm bằng chứng cho danh tính.
- **Credential** là bằng chứng dùng để xác thực: mật khẩu, mã/thiết bị MFA, khóa riêng, token có chữ ký hoặc session credential. Mật khẩu là một loại credential, không phải toàn bộ khái niệm authentication.
- **Authentication result** chứa principal và dữ liệu bảo mật có liên quan sau khi cơ chế xác thực kiểm tra bằng chứng. Một request được xác thực với token hợp lệ không nhất thiết vừa đi qua màn hình đăng nhập.
- **Session/token** giúp duy trì hoặc chuyển tiếp trạng thái xác thực giữa các request. Chúng có thời hạn và chính sách thu hồi riêng với trạng thái hồ sơ tài khoản.

Ba yếu tố xác thực thường được phân theo “điều người dùng biết” (mật khẩu/PIN), “điều người dùng sở hữu” (thiết bị, khóa bảo mật) và “đặc tính của người dùng” (sinh trắc). MFA kết hợp các yếu tố độc lập để giảm rủi ro credential bị đánh cắp. Email đã được xác minh là bằng chứng kiểm soát hộp thư tại thời điểm xác minh; nó không đương nhiên chứng minh danh tính pháp lý của một người.

### 2.2. Spring Security biểu diễn xác thực ra sao?

Ở mức khái niệm, request đi qua `SecurityFilterChain`. Tùy phương thức đăng nhập, một cơ chế như HTTP Basic, form login hoặc OAuth2 Resource Server đọc bằng chứng. `AuthenticationManager` giao việc cho `AuthenticationProvider` thích hợp; nếu thành công, `Authentication` được gắn với `SecurityContext` của request để bước phân quyền và code ứng dụng sử dụng.

~~~text
HTTP request
  -> SecurityFilterChain
  -> Cơ chế xác thực phù hợp (Basic / form / bearer ...)
  -> Kiểm tra credential, token, chữ ký, hạn dùng và chính sách liên quan
  -> Authentication / SecurityContext (principal, authorities)
  -> Kiểm tra quyền URL hoặc method
  -> Controller / Service nếu được cho phép
~~~

Đây là sơ đồ khái niệm: bộ lọc và thứ tự thực tế tùy cấu hình. Với username/password nội bộ, `UserDetailsService` có thể tải tài khoản, `PasswordEncoder` kiểm tra hash mật khẩu, và provider kiểm tra trạng thái như enabled/locked/expired. Với bearer JWT, ứng dụng có thể kiểm tra chữ ký, issuer, audience, thời hạn và chuyển claims thành authorities; không nhất thiết gọi `UserDetailsService` ở mọi request.

**Lưu ý về anonymous:** Spring Security có thể đặt một `AnonymousAuthenticationToken` trong context ngay cả khi người dùng chưa đăng nhập. Vì thế, chỉ kiểm tra `SecurityContextHolder.getContext().getAuthentication() != null` hoặc chỉ gọi `isAuthenticated()` trên một token bất kỳ không phải tiêu chí đủ để kết luận đã có người dùng thật. Hãy dùng các quy tắc `authenticated()`/`permitAll()` của Spring Security hoặc cơ chế nhận diện anonymous thích hợp.

### 2.3. Bảo vệ credential

Mật khẩu cần được lưu dưới dạng hash một chiều có salt với thuật toán thích hợp như bcrypt, scrypt hoặc Argon2 qua `PasswordEncoder`; không lưu plaintext hay dùng hash nhanh như SHA-256 đơn thuần để lưu mật khẩu. Cần giới hạn thử đăng nhập, có chính sách MFA phù hợp, bảo vệ kênh truyền bằng HTTPS và không ghi mật khẩu/token thô vào log. HTTP Basic trong ví dụ bên dưới chỉ nhằm minh họa, phải dùng qua HTTPS và không phải thiết kế đăng nhập đầy đủ cho môi trường sản xuất.

Khi xác thực từ Identity Provider (IdP), ứng dụng vẫn phải xác minh token/response đúng giao thức; nhận một chuỗi “đã đăng nhập” từ frontend không phải xác thực.

## 3. Phân quyền: quyết định có được thực hiện thao tác hay không

Giả sử request đã được xác thực thành principal `reader`. Khi thực hiện `GET /orders/42`, hệ thống cần trả lời ít nhất ba câu hỏi: principal có quyền đọc đơn hàng không, đơn số 42 có thuộc phạm vi được truy cập không, và có quy tắc bổ sung nào (tenant, trạng thái đơn, thời điểm, chính sách tổ chức) không?

Một số cách biểu diễn quyền:

| Cách | Ý tưởng | Ví dụ |
|---|---|---|
| Role-based (RBAC) | Gán nhóm trách nhiệm, ánh xạ thành quyền | `ROLE_ADMIN`, `ROLE_SUPPORT` |
| Permission/authority | Quyền theo hành động/chức năng | `orders:read`, `orders:refund` |
| Object/attribute-based | Xét tài nguyên và ngữ cảnh của request | Chỉ chủ đơn hàng hoặc người hỗ trợ được ủy quyền mới xem được đơn |
| Tenant/scope-based | Giới hạn dữ liệu trong tổ chức/phạm vi token | Nhân viên tenant A không đọc dữ liệu tenant B |

Trong Spring Security, `GrantedAuthority` là dạng dữ liệu thường được dùng cho kiểm tra quyền. `hasAuthority("orders:read")` khớp chính xác chuỗi authority. `hasRole("ADMIN")` theo quy ước mặc định tìm authority `ROLE_ADMIN` (có tiền tố `ROLE_`). Role là cách nhóm quyền; bản thân role không giải quyết được việc “đơn hàng này thuộc ai”.

Có thể đặt quy tắc ở hai tầng bổ sung nhau:

1. **Tầng HTTP:** `authorizeHttpRequests` bảo vệ nhóm URL, chặn người chưa xác thực hoặc không có quyền sơ bộ.
2. **Tầng method/nghiệp vụ:** `@PreAuthorize` hoặc kiểm tra trong service bảo vệ thao tác thực và đối tượng cụ thể. Nếu API có `GET /orders/{id}`, chỉ kiểm tra `orders:read` là chưa đủ để chống lỗi IDOR: còn phải kiểm tra người gọi được truy cập đúng đơn hàng `id` đó.

Đừng dựa vào ẩn/hiện nút trên giao diện, tự gửi `role=admin` từ client, hoặc việc đã lọc danh sách trước đó để thay cho phân quyền tại server. Một tài nguyên có thể bị gọi qua URL trực tiếp, API khác hoặc job nền. Nên áp dụng “deny by default” cho đường đi chưa được định nghĩa và “least privilege” cho các quyền được cấp.

### 3.1. Phân biệt HTTP 401 và 403

| Tình huống | Phản hồi thường dùng với REST API |
|---|---|
| Không có credential hợp lệ cho tài nguyên cần xác thực | **401 Unauthorized**: cần xác thực hoặc xác thực lại |
| Đã xác thực nhưng không đủ quyền | **403 Forbidden**: không được thực hiện thao tác |
| Endpoint cho phép truy cập công khai | **200** hoặc mã phù hợp với nghiệp vụ |
| Không muốn tiết lộ tài nguyên có tồn tại cho người không được phép | Có thể dùng **404** theo chính sách chống lộ dữ liệu |

Các mã này phụ thuộc cách cấu hình `AuthenticationEntryPoint`, `AccessDeniedHandler` và loại ứng dụng. Với form login trên web, người chưa đăng nhập thường được **302 redirect** tới trang login thay vì trả 401 trực tiếp. “Unauthorized” trong tên mã 401 không có nghĩa đã phân quyền thất bại; về mặt luồng HTTP đây là trường hợp cần thông tin xác thực hợp lệ.

## 4. Quản lý vòng đời tài khoản: chính sách xuyên suốt thời gian sử dụng

Xác thực và phân quyền xử lý một request; vòng đời tài khoản quản lý sự tồn tại và trạng thái của principal theo thời gian. Các hệ thống thường có các trạng thái và chuyển đổi như sau, nhưng đây là **ví dụ thiết kế nghiệp vụ**, không phải enum bắt buộc của Spring Security:

| Trạng thái | Ý nghĩa | Quy tắc thường gặp |
|---|---|---|
| `PENDING_VERIFICATION` | Đã đăng ký/được mời, còn chờ xác minh | Chưa cấp quyền truy cập thông thường; token xác minh ngắn hạn và dùng một lần |
| `ACTIVE` | Đã hoàn tất điều kiện kích hoạt | Có thể xác thực; vẫn phải được phân quyền trên từng request |
| `LOCKED` | Bị khóa tạm do rủi ro hoặc sai mật khẩu nhiều lần | Không chấp nhận đăng nhập mới; chỉ mở khóa sau bước xác minh/quy trình định trước |
| `SUSPENDED` | Bị quản trị viên hoặc chính sách đình chỉ | Ngăn sử dụng, thu hồi phiên/token theo mức độ rủi ro |
| `CLOSED` / `DELETED` | Không còn được dùng | Vô hiệu hóa truy cập, xử lý dữ liệu và audit theo chính sách lưu giữ |

Một quy trình đầy đủ thường bao gồm:

1. **Tạo/được mời:** Kiểm tra trùng danh tính, dữ liệu đầu vào, điều kiện mời và quyền cấp tài khoản. Không cấp role đặc quyền chỉ vì client yêu cầu.
2. **Xác minh/kích hoạt:** Xác minh email hoặc phương thức sở hữu phù hợp; token kích hoạt có hạn, một lần dùng; chuyển trạng thái có kiểm tra tính hợp lệ.
3. **Sử dụng:** Đăng nhập, MFA, cập nhật hồ sơ, đổi mật khẩu, gắn/bỏ thiết bị, điều chỉnh vai trò và quyền theo thẩm quyền.
4. **Khôi phục:** Quên mật khẩu/MFA hoặc nghi tài khoản bị chiếm đoạt. Yêu cầu token khôi phục có hạn, giới hạn thử, xác nhận đúng chủ thể và vô hiệu hóa credential/phiên cũ theo chính sách.
5. **Khóa/đình chỉ:** Ngăn xác thực mới, cân nhắc thu hồi access token, refresh token, session và các quyền truy cập dịch vụ liên quan; ghi log sự kiện quản trị.
6. **Đóng/xóa:** Thu hồi vai trò/quyền, token, khóa API, kết nối bên thứ ba; thực thi yêu cầu xóa/ẩn danh hoặc lưu giữ dữ liệu theo chính sách và luật áp dụng.

**Trạng thái tài khoản khác trạng thái phiên.** Một tài khoản `SUSPENDED` không tự làm session cookie đang lưu ở server bị hủy. Một JWT tự chứa, hợp lệ về chữ ký và thời hạn có thể vẫn được resource server chấp nhận nếu server chỉ kiểm tra token và không kiểm tra trạng thái hiện tại hoặc cơ chế thu hồi. Vì vậy, quy trình khóa cần nêu rõ thời điểm và cách chặn truy cập đang tồn tại.

Ví dụ lựa chọn kỹ thuật: session phía server có thể bị xóa/vô hiệu hóa; refresh token có thể thu hồi ở kho cấp phát; access token tồn tại ngắn, dùng introspection hoặc danh sách thu hồi khi cần phản ứng tức thời; thay đổi credential đôi khi cần tăng “security version” và kiểm tra phiên/token với phiên bản đó. Mỗi lựa chọn có chi phí, độ trễ đồng bộ và đánh đổi riêng.

### 4.1. Spring Security hỗ trợ gì, ứng dụng phải tự làm gì?

Với mô hình username/password dùng `UserDetails`, các thuộc tính `isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()` và `isCredentialsNonExpired()` hỗ trợ từ chối xác thực khi provider phù hợp kiểm tra trạng thái. Điều này hữu ích để chặn **lần đăng nhập mới**. Nhưng Spring Security không tự thiết kế bảng tài khoản, luồng đăng ký, email xác minh, reset password, phê duyệt quyền, lịch sử trạng thái hay quy tắc xóa dữ liệu cho ứng dụng.

Ứng dụng thường cần `AccountService`, kho dữ liệu, giao dịch nhất quán, audit, cơ chế phát/thu hồi token hoặc quản lý session. Với OAuth2/OIDC, IdP có thể giữ nhiều trách nhiệm vòng đời, nhưng resource server vẫn chịu trách nhiệm xác thực token được nhận và thực thi quyền trên tài nguyên mà nó quản lý. Không giả định IdP khóa người dùng thì mọi access token đã phát hành sẽ bị từ chối tức khắc.

Cần phân biệt **lockout do nhiều lần đăng nhập sai** với **suspension do nghiệp vụ**: lý do, người có quyền xử lý, thời hạn, quy trình mở lại và mức độ thu hồi truy cập có thể rất khác nhau.

## 5. Luồng điển hình từ đăng ký đến truy cập và đình chỉ

Giả sử một ứng dụng có endpoint `POST /accounts`, `POST /auth/login` và `GET /orders/{id}`:

1. Người dùng đăng ký. `AccountService` tạo bản ghi `PENDING_VERIFICATION` và gửi liên kết xác minh có token sử dụng một lần.
2. Sau khi xác minh hợp lệ, account chuyển sang `ACTIVE`. Chưa có request đọc đơn hàng nào được phép chỉ vì tài khoản đã active.
3. Người dùng đăng nhập. Cơ chế AuthN kiểm tra credential, MFA khi áp dụng và trạng thái tài khoản; kết quả xác thực thiết lập principal.
4. Người dùng gọi `GET /orders/42`. AuthN xử lý cookie/token trên request. AuthZ kiểm tra quyền `orders:read`, tenant và chủ sở hữu của đơn 42. Chỉ khi toàn bộ điều kiện đều thỏa thì controller/service trả dữ liệu.
5. Quản trị viên đình chỉ tài khoản. Dịch vụ tài khoản ghi `SUSPENDED`, audit, thu hồi phiên/refresh token và triển khai chính sách xử lý access token còn hạn.
6. Request sau đình chỉ bị từ chối theo chính sách. Cần kiểm thử cả login mới **và** phiên/token đã phát trước khi đình chỉ.

Trong thiết kế này, `POST /accounts` không phải bộ lọc xác thực; `GET /orders/42` không nên tự xử lý mật khẩu; và thao tác đình chỉ không nên chỉ đổi cờ database rồi bỏ mặc các token còn hiệu lực.

## 6. Ví dụ Spring Boot 3.x / Java 17+: một request đi qua AuthN rồi AuthZ

Ví dụ tối thiểu dưới đây dùng HTTP Basic và hai tài khoản trong bộ nhớ để thấy rõ ba kết quả 401, 403 và 200. Nó minh họa AuthN/AuthZ; quy trình quản lý vòng đời nêu ở trên cần persistence và service riêng trong hệ thống thật.

Tạo dự án Gradle có `settings.gradle`:

~~~groovy
rootProject.name = 'authn-authz-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.7'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Tạo đúng một tệp `src/main/java/example/authdemo/DemoApplication.java`:

~~~java
package example.authdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/public/status").permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("change-me"))
            .authorities("orders:read")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("change-me"))
            .authorities("profile:read")
            .build();

        return new InMemoryUserDetailsManager(reader, viewer);
    }
}

@RestController
class DemoController {
    @GetMapping("/public/status")
    String status() {
        return "OK";
    }

    @GetMapping("/orders/{id}")
    @PreAuthorize("hasAuthority('orders:read')")
    OrderView getOrder(@PathVariable String id) {
        return new OrderView(id, "READABLE");
    }
}

record OrderView(String id, String status) {}
~~~

**Giải thích theo đúng ranh giới trách nhiệm:**

- `httpBasic()` bật cơ chế đọc HTTP Basic credential và xác thực người dùng. `UserDetailsService` cung cấp hai principal; `PasswordEncoder` lưu/kiểm tra mật khẩu dạng bcrypt. `reader` và `viewer` đều có thể xác thực bằng mật khẩu mẫu.
- `requestMatchers(HttpMethod.GET, "/orders/**").authenticated()` yêu cầu có danh tính được xác thực trước khi vào API; `/public/status` được phép truy cập không đăng nhập; các đường còn lại mặc định bị từ chối.
- `@EnableMethodSecurity` kích hoạt kiểm tra ở method; `@PreAuthorize("hasAuthority('orders:read')")` quyết định quyền của người gọi. `viewer` đã xác thực nhưng thiếu authority nên bị từ chối.
- `DemoController` không tự so sánh mật khẩu hay đọc role do client gửi. Ví dụ chưa kiểm tra chủ sở hữu đơn hàng: ứng dụng thực tế phải bổ sung chính sách object-level trong service/repository để tránh IDOR.
- Hai user trong `InMemoryUserDetailsManager` chỉ là fixture. Chúng không cung cấp luồng đăng ký, xác minh email, khóa, khôi phục hay thu hồi token. Password `change-me` chỉ dùng trong máy thử nghiệm. CSRF mặc định của Spring Security không bị tắt trong ví dụ; các thao tác ghi bằng cookie/session cần chính sách CSRF phù hợp.

Chạy với Gradle Wrapper của dự án (nếu đã tạo wrapper), hoặc dùng bản Gradle tương thích:

~~~bash
./gradlew bootRun
~~~

Mở terminal khác và chạy lệnh sau trong shell có `curl` (mỗi lệnh in riêng HTTP status code):

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/status
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/orders/42
curl -s -o /dev/null -w '%{http_code}\n' -u viewer:change-me http://localhost:8080/orders/42
curl -s -o /dev/null -w '%{http_code}\n' -u reader:change-me http://localhost:8080/orders/42
~~~

Kết quả mong đợi, theo thứ tự, với cấu hình trên:

~~~text
200
401
403
200
~~~

Có thể gọi `curl -s -u reader:change-me http://localhost:8080/orders/42` để nhận JSON có `id` là `42` và `status` là `READABLE`. Mã 401 đến từ request chưa xác thực; 403 đến từ một principal đã xác thực nhưng thiếu authority; 200 đến từ principal có quyền. Không dùng mật khẩu mẫu hoặc HTTP Basic qua HTTP không mã hóa trên mạng thật.

## 7. Những trường hợp dễ nhầm

**“Đăng nhập rồi thì xem được đơn hàng nào cũng được.”** Sai: authenticated chỉ chứng minh principal; phân quyền phải xét hành động và tài nguyên. `orders:read` không đồng nghĩa sở hữu mọi đơn.

**“Có role ADMIN trong JWT nghĩa là backend phải tin ngay.”** Backend phải xác minh token (chữ ký/issuer/audience/hạn dùng theo cấu hình) và ánh xạ claim thành authority theo chính sách. Role do frontend tự truyền không đáng tin.

**“Đổi mật khẩu là mọi thiết bị lập tức đăng xuất.”** Không tự động. Đổi hash mật khẩu thường ảnh hưởng lần xác thực bằng mật khẩu tiếp theo; session và access token đang tồn tại cần chính sách riêng để thu hồi/hết hạn.

**“Đặt account.enabled=false thì JWT đã phát lập tức vô hiệu.”** Chỉ đúng nếu đường kiểm tra request có kiểm tra trạng thái hoặc cơ chế thu hồi phù hợp. Với JWT tự chứa được xác minh offline, việc đổi cờ DB không tự sửa token.

**“Phải dùng 403 cho mọi lỗi đăng nhập.”** Credential thiếu/sai thường đi qua authentication entry point, trả 401 cho API (hoặc redirect khi form login); 403 thường là đã xác thực nhưng thiếu quyền. Không để mã lỗi tiết lộ tài khoản có tồn tại khi đăng nhập/khôi phục.

**“Phân quyền một lần ở controller là đủ.”** Không chắc: service có thể được gọi từ endpoint khác, message consumer hoặc tác vụ nền; chính sách nhạy cảm, nhất là ownership và tenant boundary, cần được kiểm tra tại điểm nghiệp vụ thích hợp.

**“Quản lý tài khoản chỉ là bảng users.”** Chưa đủ: cần luồng trạng thái, reset/verify, phân quyền thay đổi trạng thái, audit, thu hồi credential và dữ liệu theo chính sách.

## 8. Checklist thiết kế và kiểm thử

Dùng ma trận tình huống thay vì chỉ thử một tài khoản admin hoạt động bình thường:

| Tình huống kiểm thử | Điều cần xác minh |
|---|---|
| Anonymous truy cập endpoint yêu cầu đăng nhập | Bị yêu cầu xác thực; không rò dữ liệu |
| Đã đăng nhập nhưng thiếu authority | Bị từ chối đúng tại URL/method |
| Có authority nhưng truy cập đơn của người khác/tenant khác | Bị từ chối tại lớp kiểm tra đối tượng |
| Tài khoản bị khóa/chưa xác minh đăng nhập mới | Cơ chế AuthN từ chối theo chính sách |
| Tài khoản bị đình chỉ sau khi đã đăng nhập | Session, refresh token và access token cũ được xử lý đúng cam kết |
| Đổi mật khẩu, reset MFA, cấp/thu hồi role | Credential cũ và quyền cũ không tiếp tục có tác dụng ngoài thời hạn/chính sách cho phép |
| Gọi lại token kích hoạt/reset hoặc token đã hết hạn | Không dùng được lần hai và không kéo dài hiệu lực |
| Gọi API trực tiếp bỏ qua UI | Backend vẫn xác thực và phân quyền |

Ngoài test trả về 200/401/403, cần kiểm tra **dữ liệu thực tế** được trả về, thử thao tác ở cả hai phía của ranh giới tenant/ownership, audit các hành động nhạy cảm mà không ghi credential bí mật, và mô phỏng đồng thời thay đổi quyền/trạng thái tài khoản trong lúc token còn hạn.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Một người dùng nhập đúng mật khẩu nhưng gọi API của quản trị viên và bị 403. Thành phần nào đã thành công, thành phần nào từ chối?  
**Đáp án:** AuthN thành công; AuthZ từ chối thao tác vì không đủ quyền.

**Câu 2.** Người dùng bị đình chỉ trong database nhưng JWT cũ vẫn gọi API được. Đó là lỗi ở đâu?  
**Đáp án:** Quy trình vòng đời và chiến lược thực thi trạng thái/thu hồi token chưa kết nối đúng với đường xác thực/phân quyền request hiện tại. Cần làm rõ hợp đồng hiệu lực và cách từ chối token đã cấp.

**Câu 3.** Hai người cùng có `orders:read`; người A có được xem đơn của người B không?  
**Đáp án:** Không thể kết luận chỉ từ authority. Phải kiểm tra ownership, tenant hoặc chính sách chia sẻ cụ thể.

**Câu 4.** Đổi mật khẩu và đổi role có cùng trách nhiệm không?  
**Đáp án:** Đổi mật khẩu là quản lý credential/vòng đời tài khoản; đổi role là quản trị quyền trong vòng đời danh tính và ảnh hưởng kết quả AuthZ. Cả hai cần cơ chế cập nhật tác dụng lên session/token khi chính sách yêu cầu.

## 10. Ghi nhớ để áp dụng

- **AuthN xác định principal từ bằng chứng đáng tin.** Spring Security cung cấp filter chain, providers, authentication context và các tích hợp xác thực.
- **AuthZ quyết định hành động trên tài nguyên trong ngữ cảnh.** Dùng URL/method security làm lớp chặn, bổ sung kiểm tra đối tượng/tenant trong nghiệp vụ.
- **Account lifecycle quyết định khi nào tài khoản tồn tại, được dùng và phải bị thu hồi.** Thiết kế state machine, self-service/admin workflow, audit và chính sách session/token riêng.
- **Thay đổi trạng thái tài khoản phải có hiệu lực đã định nghĩa rõ với credential và token cũ.** Kiểm thử cả request mới lẫn request dùng bằng chứng đã phát từ trước.

Ba trách nhiệm phối hợp để bảo vệ cùng một hệ thống, nhưng mỗi trách nhiệm có dữ liệu đầu vào, điểm kiểm soát và điều kiện kiểm thử riêng.