# Kiến thức nền, lộ trình đọc và cách quan sát một yêu cầu được bảo vệ trong Spring Security Servlet

Spring Security trong ứng dụng Servlet bảo vệ HTTP request **trước khi request đi vào controller**. Khi học một dự án Spring MVC, điều đầu tiên cần làm là nhận diện đường đi của request, nơi danh tính được xác thực và nơi quyết định quyền truy cập được đưa ra. Bài này xây dựng mô hình nền, hướng dẫn thứ tự đọc cấu hình và trình diễn cách quan sát một request công khai, một request cần đăng nhập và một request bị từ chối quyền.

Sau bài học, bạn có thể:
- Phân biệt **authentication** (xác thực danh tính) với **authorization** (kiểm tra quyền).
- Giải thích vai trò của Servlet Filter, `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain` và `SecurityContext`.
- Đọc một cấu hình bảo vệ URL từ `requestMatchers` tới `anyRequest`, rồi nối nó với controller tương ứng.
- Gửi HTTP request có/không có thông tin đăng nhập, đối chiếu kết quả 200, 401, 403 và lần theo log để tìm nguyên nhân.

## 1. Kiến thức HTTP và Servlet cần nắm trước

Một HTTP request gồm **method** (GET, POST...), **đường dẫn**, **headers**, đôi khi có **body**. Server trả về **status**, headers và body. Thông tin danh tính có thể đi qua header `Authorization`, cookie phiên đăng nhập hoặc cơ chế khác. Đường dẫn và method là hai chiều độc lập: GET và POST cùng một URL không nhất thiết chịu cùng một chính sách.

Trong Servlet stack, container (ví dụ Tomcat) nhận request, chuyển qua chuỗi Servlet Filter rồi mới đến `DispatcherServlet` của Spring MVC và controller. Spring Security khai thác điểm chặn ở **filter chain**: vì vậy một request có thể nhận 401 hoặc 403 **trước khi phương thức controller chạy**. Việc bảo vệ ở tầng HTTP có thể cùng tồn tại với kiểm tra quyền ở tầng method; bài này tập trung vào đường HTTP.

Phân biệt các khái niệm:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Authentication | Người gọi là ai? Bằng chứng danh tính có hợp lệ? | Đối chiếu username/password khi dùng HTTP Basic. |
| Authorization | Danh tính hiện tại có quyền làm thao tác này? | Chỉ người có quyền `ROLE_ADMIN` được vào `/api/admin`. |
| Principal | Đại diện danh tính của người gọi sau xác thực | Username `reader`. |
| Authority/Role | Quyền gắn với danh tính | `ROLE_READER`, `ROLE_ADMIN`. |
| SecurityContext | Nơi giữ đối tượng `Authentication` của xử lý bảo mật hiện tại | Controller có thể đọc principal nếu request đã được xác thực. |
| Session/Cookie | Cơ chế giữ trạng thái giữa các request khi được cấu hình sử dụng | Trình duyệt gửi lại cookie phiên; cookie tự nó không phải một quyền. |
| CSRF | Rủi ro trình duyệt bị lợi dụng gửi request thay người dùng đã đăng nhập | Với phương thức làm thay đổi trạng thái, cơ chế CSRF có thể từ chối request thiếu token. |

**HTTP không tự nhớ người dùng giữa các request.** Nếu ứng dụng dùng session, cookie giúp server nhận diện phiên; nếu dùng Basic, client thường gửi lại header `Authorization` trên mỗi request. Không suy luận ứng dụng hoàn toàn stateless chỉ vì nó dùng Basic: trạng thái phiên còn phụ thuộc cấu hình `SessionCreationPolicy` và những thành phần liên quan.

Các status cần đọc theo tình huống:

- **200 OK**: request đã đi tới điểm xử lý và thành công; đây không phải bằng chứng rằng endpoint không có bảo vệ.
- **401 Unauthorized**: không có hoặc không xác thực được thông tin đăng nhập cần thiết. Với HTTP Basic thường có header `WWW-Authenticate` yêu cầu client cung cấp credentials.
- **403 Forbidden**: request bị từ chối truy cập. Thường do đã xác thực nhưng thiếu quyền; cũng có thể do CSRF, nên phải đọc log và cấu hình trước khi kết luận.
- **302 Found**: một cơ chế đăng nhập dựa trên chuyển hướng có thể đưa người dùng tới trang login, tùy cấu hình; không nên mặc định mọi request chưa đăng nhập đều trả 401.
- **404/405**: sau khi vượt qua các filter, URL hoặc method không khớp handler. Cần phân biệt với lỗi bảo mật.

## 2. Bản đồ thành phần của một request được bảo vệ

Khi tích hợp Spring Security vào ứng dụng Servlet, container gọi `DelegatingFilterProxy`, proxy này chuyển tiếp tới bean Spring có tên `springSecurityFilterChain` (thường là `FilterChainProxy`). `FilterChainProxy` chọn **SecurityFilterChain đầu tiên có matcher khớp** request. Chain đó gồm các security filter phù hợp cấu hình; không nên giả định mọi dự án có cùng số filter hoặc thứ tự tuyệt đối.

~~~text
HTTP client
   |
   v
Servlet container (Tomcat...)
   |
   v
DelegatingFilterProxy -> FilterChainProxy
   |
   v
Chọn SecurityFilterChain khớp request
   |
   +--> Tạo/nạp SecurityContext phù hợp cấu hình
   +--> Đọc credentials và xác thực nếu có bộ lọc phù hợp
   +--> Xác định người gọi (đã xác thực hoặc anonymous)
   +--> Kiểm tra chính sách authorization
                |
                +--> Được phép -> DispatcherServlet -> controller -> response
                |
                +--> Bị chặn  -> entry point/denied handler -> 401/403/... 
~~~

Các mắt xích cần nhận diện khi xem log hoặc source:

1. **`SecurityFilterChain`** là tập filter dùng cho nhóm request; một ứng dụng có thể khai báo nhiều chain, với thứ tự matcher quyết định chain nào được chọn.
2. **`SecurityContextHolderFilter`** hỗ trợ đưa SecurityContext vào phạm vi xử lý request; cách lưu/persist context phụ thuộc repository và cấu hình.
3. **Filter xác thực** phụ thuộc cơ chế: HTTP Basic thường có `BasicAuthenticationFilter`; form login hoặc bearer token sử dụng thành phần khác. Filter không tự hiểu mọi loại credentials.
4. **`AuthenticationManager` và `AuthenticationProvider`** điều phối/kiểm chứng thông tin đăng nhập. `UserDetailsService` thường được dùng để tải thông tin người dùng trong xác thực username/password; nó không phải lớp cấp quyền cho URL.
5. **`AnonymousAuthenticationFilter`** có thể đặt một authentication đại diện anonymous vào context; điều đó không biến khách chưa đăng nhập thành người dùng đã xác thực.
6. **`AuthorizationFilter`** thực thi chính sách khai báo qua `authorizeHttpRequests`. `ExceptionTranslationFilter` có thể chuyển lỗi xác thực/truy cập thành phản hồi thông qua entry point hoặc access-denied handler. Riêng filter xác thực như `BasicAuthenticationFilter` cũng có thể trực tiếp kích hoạt entry point khi credentials sai.

**Tách ba câu hỏi khi quan sát:** chain nào được chọn? Authentication hiện tại là ai? Quy tắc authorization nào chấp nhận hoặc từ chối request? Câu trả lời cho cả ba mới giải thích được status.

## 3. Lộ trình đọc một dự án Servlet Security

Đọc từ **biên HTTP vào bên trong**, không bắt đầu bằng việc mở ngẫu nhiên một class về user hay role.

| Thứ tự | Đọc ở đâu | Kết quả cần rút ra |
| --- | --- | --- |
| 1 | Dependencies và cấu hình ứng dụng | Có Spring Web/Spring Security Servlet? Đang dùng Basic, form login, session, JWT resource server hay phối hợp nhiều cách? |
| 2 | Các bean `SecurityFilterChain`, `@Order`, `securityMatcher` | Có bao nhiêu chain? Request cụ thể khớp chain nào? |
| 3 | `authorizeHttpRequests`, `requestMatchers`, `anyRequest` | Method/path này public, chỉ yêu cầu đăng nhập hay cần authority nào? |
| 4 | Filter xác thực, `AuthenticationProvider`, `UserDetailsService`, password encoder | Credentials đến từ đâu và được kiểm chứng bằng cách nào? |
| 5 | Session, `SecurityContextRepository`, CSRF, exception handling | Danh tính tồn tại trong phạm vi nào? Tại sao request bị chặn hoặc bị redirect? |
| 6 | `@RequestMapping`/`@GetMapping`, method security nếu có, log và tests | Request hợp lệ sẽ vào handler nào và có thêm kiểm tra quyền nào? |

Cách đọc một rule cụ thể: tìm **matcher chính xác**, kiểm tra **thứ tự rule**, xác định **chain chứa rule**, rồi mới mở controller. `permitAll()` có nghĩa chính sách URL cho phép truy cập, **không có nghĩa bỏ qua toàn bộ filter chain**. `authenticated()` yêu cầu danh tính được xác thực; `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` (Spring Security thêm tiền tố `ROLE_` theo quy ước mặc định), còn `hasAuthority("REPORT_READ")` kiểm tra đúng chuỗi authority.

Nên học sâu lần lượt: HTTP/Servlet Filter → chain selection → authentication & SecurityContext → authorization → 401/403/entry point → session/CSRF → method security và testing. JWT/OAuth2 có thể học sau khi đã vững luồng này: chúng thay đổi cách xác thực credentials, nhưng vẫn phải giải thích chain được chọn và quyền được kiểm tra.

## 4. Ví dụ chạy được: ba endpoint, một người dùng

Tạo ứng dụng **Java 17+**, **Spring Boot 3.x** với dependencies **Spring Web** và **Spring Security** (Gradle hoặc Maven đều được). Trong source root đặt đúng tệp `src/main/java/example/security/SecurityLessonApplication.java` với nội dung sau. Các class bổ sung là package-private, cùng nằm trong tệp Java này để ví dụ độc lập ở tầng source.

~~~java
package example.security;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
public class SecurityLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLessonApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(reader);
    }
}

@RestController
class ExampleController {
    @GetMapping("/health")
    String health() {
        return "OK";
    }

    @GetMapping("/api/notes")
    String notes(Principal principal) {
        return "Private notes for " + principal.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "Admin only";
    }
}
~~~

**Đọc cấu hình trước khi chạy:**

- `/health` được phép dù chưa có credentials; request vẫn đi qua security chain.
- `/api/admin` cần role ADMIN, tức authority `ROLE_ADMIN`. User mẫu chỉ có `ROLE_READER` nên đăng nhập đúng vẫn không đủ quyền.
- Các URL khác, bao gồm `/api/notes`, cần người dùng đã được xác thực.
- `httpBasic(...)` bật HTTP Basic; không cấu hình form login nên trường hợp chưa đăng nhập trong ví dụ sẽ dùng challenge Basic thay vì trang login.
- `InMemoryUserDetailsManager` cung cấp user mẫu; `BCryptPasswordEncoder` mã hóa mật khẩu lưu trong bộ nhớ. Thông tin `reader/demo-pass` chỉ dùng để thử nghiệm cục bộ.
- Ví dụ không chủ động tắt CSRF. Chỉ dùng GET nên không phải cung cấp CSRF token; khi mở rộng sang POST/PUT/DELETE, phải xét chính sách CSRF riêng.

Khởi động bằng wrapper của dự án (thư mục chứa `build.gradle` hoặc `build.gradle.kts`):

~~~bash
./gradlew bootRun
~~~

Trên Windows có thể chạy `gradlew.bat bootRun`. Nếu dùng Maven, chạy bằng wrapper `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`). Lệnh `javac` đơn lẻ không đủ vì ví dụ cần thư viện Spring và classpath từ công cụ build.

Trong terminal khác, gửi các request sau. `curl -i` hiển thị cả status và response headers; `-u` tạo header HTTP Basic:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/notes
curl -i -u reader:wrong http://localhost:8080/api/notes
curl -i -u reader:demo-pass http://localhost:8080/api/notes
curl -i -u reader:demo-pass http://localhost:8080/api/admin
~~~

Kết quả cần đối chiếu (các header phụ thuộc phiên bản và môi trường, vì vậy chỉ khẳng định status/body chính):

| Request | Kết quả dự kiến | Giải thích |
| --- | --- | --- |
| GET `/health`, không credentials | **200**, body `OK` | `permitAll()` cho phép truy cập. |
| GET `/api/notes`, không credentials | **401**, thường kèm `WWW-Authenticate: Basic ...` | Không có danh tính hợp lệ để thỏa `authenticated()`. |
| GET `/api/notes`, mật khẩu sai | **401** | HTTP Basic nhận credentials nhưng xác thực thất bại. |
| GET `/api/notes`, `reader/demo-pass` | **200**, body `Private notes for reader` | Xác thực thành công rồi controller dùng `Principal`. |
| GET `/api/admin`, `reader/demo-pass` | **403** | Đã xác thực, nhưng thiếu `ROLE_ADMIN`. |

Hai trường hợp 401 có thể đi tới entry point qua những nhánh khác nhau (không có credentials so với Basic credentials không hợp lệ). Vì vậy status giống nhau **không có nghĩa** đường đi qua mọi filter giống hệt.

## 5. Quan sát một request từ log tới controller

### Bước 1: bật log bảo mật có giới hạn ở môi trường học

Thêm vào `src/main/resources/application.properties`:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Khởi động lại ứng dụng và gửi từng lệnh `curl` riêng. Tùy phiên bản, log có thể cho thấy request đang được bảo vệ, chain/filter đang được gọi, kết quả authentication hoặc authorization và nhánh exception handling. **Không dựa vào chuỗi log cố định**: tên message và danh sách filter thay đổi theo phiên bản/cấu hình. Chỉ bật TRACE để thử nghiệm, vì log rất nhiều và có thể chứa thông tin nhạy cảm về request.

### Bước 2: truy dấu theo ba trục

Với mỗi request, ghi lại:

1. **Request đầu vào:** method, path, có hay không header `Authorization` hoặc cookie phù hợp.
2. **Security chain & identity:** request khớp chain nào; filter nào xử lý credentials; trước/sau xác thực, `Authentication` và authorities là gì.
3. **Authorization & response:** rule nào được áp dụng; request tới controller hay dừng ở filter; ai tạo status/redirect/challenge.

Ví dụ với `GET /api/notes` và credentials đúng: container gọi security chain → filter Basic kiểm chứng password qua provider/user store → context chứa danh tính `reader` và `ROLE_READER` → rule `authenticated()` thành công → controller nhận `Principal` và trả `Private notes for reader`. Với cùng credentials nhưng `GET /api/admin`, authentication vẫn thành công; điểm rẽ nằm ở rule `hasRole("ADMIN")`. Đây là khác biệt cốt lõi giữa **đã đăng nhập** và **được phép thao tác**.

Với request không credentials, anonymous có thể xuất hiện trong context. **Anonymous authentication không đồng nghĩa với người dùng đã đăng nhập.** Với credentials sai, filter xác thực có thể kích hoạt HTTP Basic entry point ngay; đừng kết luận rằng request sai mật khẩu đã chạy tới controller.

### Bước 3: dùng breakpoint khi log chưa đủ

Khi debug dự án Servlet thực tế, có thể đặt breakpoint tại các vị trí tương ứng với cấu hình:

- `FilterChainProxy`: kiểm tra chain nào khớp method/path.
- Filter xác thực đang dùng, ví dụ `BasicAuthenticationFilter`: xác định credentials được đọc thế nào và nhánh success/failure.
- `AuthorizationFilter` hoặc authorization manager được cấu hình: tìm rule và authorities dẫn đến quyết định.
- Controller: kiểm tra request thực sự đã tới handler chưa; đọc `Principal` hoặc `SecurityContextHolder.getContext().getAuthentication()` nếu cần quan sát danh tính.

Không đặt kỳ vọng breakpoint ở filter **không được cấu hình** (ví dụ filter Bearer trong ví dụ Basic). Khi xử lý bất đồng bộ hoặc chạy luồng khác, SecurityContext không tự động được truyền sang mọi thread; cần xem đúng cơ chế propagation của ứng dụng.

### Bước 4: phân tích response trước khi sửa cấu hình

Một quy trình chẩn đoán nhanh:

| Dấu hiệu | Kiểm tra đầu tiên |
| --- | --- |
| 401 khi gọi endpoint cần đăng nhập | Credentials có được gửi? Bộ lọc xác thực có chạy? Provider có chấp nhận? Có `WWW-Authenticate`? |
| 403 với credentials đúng | Authentication có authorities gì? `hasRole` có cần tiền tố `ROLE_`? Có CSRF denial? |
| 302 tới trang login | Có `formLogin`/entry point chuyển hướng không? Client gửi cookie phiên chưa? |
| 404/405 | Sau khi qua security, controller mapping có đúng path và method không? |
| Endpoint public vẫn bị chặn | Request có khớp đúng chain/rule `permitAll` không? Có matcher ưu tiên phía trước hoặc CSRF không? |

**Đừng sửa bằng cách thêm `permitAll` thật rộng chỉ để làm biến mất 401/403.** Trước hết xác định nguyên nhân là authentication, authorization, CSRF hay route mismatch; sau đó sửa đúng lớp chịu trách nhiệm.

## 6. Những nhầm lẫn phổ biến cần tránh

1. **Nhầm 401 với 403.** 401 thiên về thiếu/sai xác thực; 403 thiên về từ chối quyền hoặc cơ chế bảo vệ khác như CSRF. Trong ứng dụng form login, một request thiếu đăng nhập còn có thể bị chuyển hướng 302.
2. **Nhầm rule với chain.** `securityMatcher` quyết định chain áp dụng, còn `requestMatchers` trong `authorizeHttpRequests` quyết định quyền truy cập **bên trong chain đã được chọn**. Khi có nhiều chain, hãy xét thứ tự ưu tiên trước khi đọc rule.
3. **Đặt matcher tổng quát trước matcher cụ thể.** Hãy đọc thứ tự rule: một rule bắt mọi request có thể khiến rule phía sau không được xét. Quy tắc `anyRequest()` thường đặt cuối.
4. **Dùng sai role/authority.** `roles("READER")` tạo `ROLE_READER`; `hasRole("READER")` kiểm tra authority đó, trong khi `hasAuthority("READER")` là kiểm tra chuỗi `READER` khác.
5. **Cho rằng `permitAll` bỏ qua Spring Security.** Public endpoint vẫn có thể chạy qua security filters. `web.ignoring` là chuyện khác và không nên dùng tùy tiện.
6. **Cho rằng Basic luôn đồng nghĩa stateless.** Header `Authorization` được gửi trên request, nhưng chính sách tạo/lưu session và SecurityContext là cấu hình riêng; quan sát `Set-Cookie` và các rule session trước khi kết luận.
7. **Tắt CSRF để xử lý 403 mà chưa điều tra.** Với trình duyệt sử dụng cookie/session, CSRF có ý nghĩa khác với client gửi token độc lập. GET đơn thuần không phải phép thử đầy đủ cho POST/PUT/DELETE.
8. **Cho rằng mọi lỗi được tạo ở controller.** Security filters có thể trả status ngay trước MVC; ngược lại, request có thể qua bảo mật rồi mới gặp 404/405 trong MVC.
9. **Dùng log làm chân lý tuyệt đối.** TRACE hỗ trợ tìm đường đi, nhưng quyết định cuối cùng cần đối chiếu cấu hình, danh tính và HTTP response thực tế.

## 7. Bài tập quan sát và tiêu chí tự kiểm tra

Thực hiện bài tập nhỏ theo thứ tự để bảo đảm bạn hiểu dòng request, không chỉ nhớ câu lệnh:

1. Gọi `/api/notes` khi chưa đăng nhập; giải thích tại sao controller không trả chuỗi `Private notes ...`.
2. Gọi lại bằng `reader/demo-pass`; chỉ ra tại sao cùng URL đổi từ 401 sang 200, và controller lấy username từ đâu.
3. Gọi `/api/admin` bằng user đó; giải thích tại sao **xác thực thành công** vẫn trả 403. Xác định authority đang có và authority đang đòi hỏi.
4. Tạm thay rule `/health` từ `permitAll()` thành `authenticated()` trong môi trường thử nghiệm, khởi động lại và dự đoán status trước/sau khi thêm credentials. Ghi nhận sự thay đổi ở **authorization**, không nhầm với thay đổi controller.
5. Bật TRACE rồi tự điền bảng ba trục *chain → authentication → authorization → response* cho mỗi request. Chỉ ghi điều thực sự quan sát được; nếu log không thể hiện đủ, kiểm chứng thêm bằng breakpoint hoặc test.

Tự trả lời được các câu hỏi sau là đạt nền tảng cho bài tiếp theo:

- Request nào được chọn vào `SecurityFilterChain` nào, và làm sao biết?
- Credentials được đọc ở filter nào? Thành phần nào kiểm chứng? `Authentication` sau đó chứa những gì?
- `authenticated()`, `hasRole()` và `permitAll()` khác nhau ở bước nào?
- Vì sao 401, 403, 302, 404 có thể xuất hiện trong các tình huống khác nhau?
- Nếu đổi từ Basic sang form login hoặc bearer token, phần nào của luồng thay đổi và phần nào vẫn phải kiểm tra?

**Mạch tư duy cần giữ:** xác định **request** → chọn **filter chain** → thiết lập **danh tính** → đánh giá **quyền truy cập** → quan sát **HTTP response/controller**. Khi năm bước này rõ ràng, các chủ đề sâu hơn như session, CSRF, method security hoặc OAuth2 sẽ có chỗ đứng trong cùng một mô hình thay vì trở thành các cấu hình rời rạc.
