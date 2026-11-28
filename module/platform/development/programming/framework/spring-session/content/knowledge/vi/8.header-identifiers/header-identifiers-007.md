# CORS, header được phép gửi và header phản hồi cần được công bố

Khi frontend và ứng dụng Spring chạy ở các origin khác nhau, trình duyệt áp dụng Cross-Origin Resource Sharing (CORS) để quyết định JavaScript có được phép đọc phản hồi từ ứng dụng hay không. CORS đặc biệt quan trọng khi Spring Session dùng cookie để nhận diện phiên: frontend có thể cần gửi cookie trong request cross-origin, đồng thời API có thể cần nhận các header tùy chỉnh hoặc cho phép JavaScript đọc một số header phản hồi.

CORS gồm hai nhóm header thường bị nhầm lẫn. Access-Control-Allow-Headers cho biết request có thể gửi những header nào; Access-Control-Expose-Headers cho biết JavaScript có thể đọc những header phản hồi nào. Cả hai đều khác với Access-Control-Allow-Credentials, vốn cho phép trình duyệt chia sẻ phản hồi của request có thông tin xác thực như cookie.

## 1. Origin và lý do cần CORS

Origin được xác định bởi bộ ba scheme, host và port. Ví dụ:

- https://app.example.com là một origin.
- https://api.example.com là origin khác vì host khác.
- http://app.example.com khác origin với HTTPS vì scheme khác.
- https://app.example.com:8443 khác origin với cổng HTTPS mặc định.

Giả sử giao diện chạy tại https://app.example.com và Spring API chạy tại https://api.example.com. Khi JavaScript gọi API, đây là request cross-origin. Trình duyệt gửi request theo các quy tắc CORS và kiểm tra header CORS trong response trước khi cho JavaScript đọc nội dung.

CORS là cơ chế do trình duyệt thực thi. Nó không phải cơ chế xác thực người dùng, không ngăn mọi client gọi API và không thay thế phân quyền ở backend. Một chương trình như curl hoặc một server khác có thể gửi request dù response không có header CORS; điều bị chặn là việc JavaScript trong origin không được phép đọc response theo chính sách trình duyệt.

## 2. Hai nhóm header: request được gửi và response được đọc

Khi cấu hình CORS, cần trả lời hai câu hỏi riêng:

1. Frontend được phép gửi những header nào đến API?
2. Sau khi API trả response, frontend được phép đọc những header nào bằng JavaScript?

| Header CORS | Hướng áp dụng | Ý nghĩa |
| --- | --- | --- |
| Access-Control-Allow-Headers | Request | Cho phép các header mà frontend muốn gửi |
| Access-Control-Allow-Methods | Request | Cho phép các HTTP method |
| Access-Control-Allow-Origin | Response | Chỉ ra origin được phép truy cập response |
| Access-Control-Allow-Credentials | Response | Cho phép request cross-origin có credentials |
| Access-Control-Expose-Headers | Response | Công bố thêm response header cho JavaScript |
| Access-Control-Max-Age | Response preflight | Thời gian trình duyệt có thể cache kết quả preflight |

Access-Control-Allow-Headers không làm cho response header xuất hiện trong JavaScript. Ngược lại, Access-Control-Expose-Headers không cho phép frontend tự gửi một request header mới. Cấu hình nhầm hai loại này thường dẫn đến lỗi preflight hoặc frontend không đọc được metadata cần thiết.

## 3. Preflight và Access-Control-Allow-Headers

Một số cross-origin request cần được trình duyệt gửi kiểm tra trước bằng phương thức OPTIONS. Request này được gọi là preflight. Trình duyệt thường cần preflight khi request dùng method không thuộc nhóm đơn giản, có header tùy chỉnh hoặc dùng một số kiểu Content-Type như application/json.

Ví dụ frontend muốn gửi request có Content-Type: application/json, X-Request-Id và Authorization:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type, x-request-id
~~~

Header Access-Control-Request-Headers do trình duyệt tạo để liệt kê các request header mà request thật dự định gửi. Server cần phản hồi với các header cho phép phù hợp:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin
~~~

Nếu request thật dùng credentials như cookie session, response preflight cũng cần cho phép credentials. Sau khi preflight thành công, trình duyệt mới gửi request thật. Nếu server không cho phép một header trong danh sách, request thật có thể không được gửi. Tên header không phân biệt chữ hoa chữ thường; danh sách nên phản ánh chính xác nhu cầu của frontend.

Các header thường cần cho API:

- Content-Type: mô tả định dạng nội dung request, thường cần khi gửi JSON.
- Authorization: dùng khi frontend gửi bearer token trong header.
- X-Request-Id: mã tương quan để theo dõi request qua log và dịch vụ.
- X-CSRF-TOKEN hoặc header CSRF tương ứng: dùng nếu ứng dụng gửi token CSRF trong custom header.
- Các header nghiệp vụ riêng: chỉ thêm khi endpoint thực sự cần.

Không nên dùng danh sách header rộng chỉ để tránh xử lý lỗi cấu hình. Chỉ cho phép các header ứng dụng cần và rà soát lại khi API thay đổi.

### Preflight không nên bị yêu cầu đăng nhập

Preflight là request kiểm tra do trình duyệt gửi trước request thật. Nó thường không mang cookie session như request thật. Nếu Spring Security yêu cầu xác thực cho OPTIONS preflight trước khi CORS được xử lý, server có thể trả 401 hoặc 403, khiến trình duyệt không gửi request thật.

Khi dùng Spring Security, phải bật CORS tích hợp và cung cấp cấu hình CORS để bộ lọc CORS xử lý preflight trước các bước xác thực phù hợp. Không mở tất cả endpoint cho người dùng ẩn danh chỉ để khắc phục preflight; hãy cho phép việc kiểm tra CORS cần thiết và vẫn áp dụng xác thực, phân quyền cho request thật.

## 4. Access-Control-Expose-Headers

Theo mặc định, JavaScript chỉ được đọc một tập response header được xem là safelisted. Những header ứng dụng tự tạo hoặc một số header điều khiển thường không hiển thị qua response.headers.get() trong fetch nếu server chưa công bố chúng.

Ví dụ API trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
X-Request-Id: req-7f92
X-RateLimit-Remaining: 42
Content-Type: application/json
~~~

Frontend có thể đọc hai header đã được công bố:

~~~javascript
const response = await fetch("https://api.example.com/api/profile", {
  credentials: "include"
});

const requestId = response.headers.get("X-Request-Id");
const remaining = response.headers.get("X-RateLimit-Remaining");
const profile = await response.json();
~~~

Nếu thiếu Access-Control-Expose-Headers, các header tùy chỉnh vẫn có thể xuất hiện trong Network tab của Developer Tools, nhưng JavaScript không nhất thiết đọc được chúng. Đây không có nghĩa server chưa gửi header; đó là giới hạn truy cập response header do CORS áp dụng.

Chỉ công bố header mà frontend có lý do sử dụng, chẳng hạn mã request để hỗ trợ người dùng báo lỗi, thông tin phân trang hoặc hạn mức. Tránh công bố thông tin nội bộ, header debug, dữ liệu hạ tầng hoặc metadata có thể tiết lộ cấu trúc hệ thống.

## 5. Vì sao không thể đọc Set-Cookie từ JavaScript?

Set-Cookie là forbidden response-header name đối với API trình duyệt. JavaScript không được đọc header này thông qua fetch hoặc XMLHttpRequest, kể cả khi server thêm Set-Cookie vào Access-Control-Expose-Headers.

Đây là chủ đích bảo vệ cookie. Trình duyệt tự xử lý Set-Cookie, lưu cookie nếu các thuộc tính và chính sách cho phép, rồi gửi cookie trong những request tiếp theo. Frontend không cần đọc session ID để quản lý phiên.

Với Spring Session:

- Backend phát hành cookie session qua response.
- Trình duyệt lưu cookie và gửi lại tự động khi request phù hợp.
- Spring Session đọc session ID từ request và tìm dữ liệu trong repository.
- JavaScript không đọc session ID từ Set-Cookie và không nên lưu session ID vào localStorage hoặc sessionStorage.

Nếu frontend cần biết trạng thái đăng nhập, cung cấp endpoint như /api/me hoặc /api/session-status trả về thông tin nghiệp vụ tối thiểu, ví dụ authenticated: true và thông tin người dùng được phép hiển thị. Không tạo endpoint trả session ID hoặc dữ liệu nội bộ của repository.

## 6. CORS có credentials khi dùng cookie session

Khi frontend và API khác origin, cookie session không phải lúc nào cũng được gửi tự động. Với Fetch API, frontend cần bật credentials: "include":

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

Frontend không tự đặt header Cookie bằng JavaScript; Cookie là forbidden request header. Khi bật credentials, trình duyệt tự chọn cookie phù hợp theo Domain, Path, Secure, SameSite và các chính sách riêng tư của trình duyệt.

Với Axios, cấu hình tương ứng là:

~~~javascript
import axios from "axios";

const api = axios.create({
  baseURL: "https://api.example.com",
  withCredentials: true
});
~~~

Server phải trả các header phù hợp:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Khi cho phép credentials, Access-Control-Allow-Origin không được là *. Server phải trả một origin cụ thể, được kiểm tra từ danh sách tin cậy. Access-Control-Allow-Credentials phải có giá trị true chính xác. Nếu response dùng wildcard origin cùng credentials, trình duyệt sẽ chặn việc JavaScript đọc response.

Không phản chiếu mọi giá trị Origin mà client gửi lên. Nếu backend sao chép tùy tiện Origin vào Access-Control-Allow-Origin, bất kỳ website nào cũng có thể được cho phép truy cập response có credentials. Hãy định nghĩa allowlist rõ ràng, chỉ gồm origin frontend được tin cậy.

### CORS và cookie là hai lớp kiểm tra khác nhau

Ngay cả khi CORS cho phép credentials, trình duyệt vẫn áp dụng chính sách cookie:

- Cookie phải khớp host/domain và Path.
- Cookie Secure chỉ được gửi qua kết nối bảo mật.
- Cookie phải còn hạn.
- SameSite phải phù hợp với ngữ cảnh request.
- Chính sách chặn third-party cookie của trình duyệt hoặc người dùng vẫn có thể ngăn cookie được lưu/gửi.

Origin và site không giống nhau. https://app.example.com và https://api.example.com là hai origin khác nhau vì host khác, nhưng có thể được xem là cùng site khi cùng scheme và cùng registrable domain. Trong trường hợp này cookie host/domain, Path và CORS vẫn cần cấu hình đúng; việc cross-origin không đồng nghĩa chắc chắn là cross-site.

Nếu frontend thực sự gọi API từ một site khác, cookie thường cần SameSite=None; Secure để được gửi trong ngữ cảnh cross-site. Tuy nhiên, một số trình duyệt hoặc thiết lập quyền riêng tư có thể chặn third-party cookie ngay cả khi thuộc tính này đúng. Cần kiểm thử trong trình duyệt mục tiêu và cân nhắc triển khai frontend/API cùng site hoặc dùng kiến trúc xác thực phù hợp hơn.

## 7. Cấu hình CORS với Spring Security

Với ứng dụng Spring Boot có Spring Security, nên cấu hình CORS tại security filter chain thông qua CorsConfigurationSource. Cấu hình này giúp preflight được xử lý trước các quyết định xác thực và áp dụng thống nhất cho các request.

Ví dụ cho frontend tại https://app.example.com gọi API session-cookie:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
        );
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-Request-Id", "X-CSRF-TOKEN")
        );
        config.setExposedHeaders(
            List.of("X-Request-Id", "X-RateLimit-Remaining")
        );
        config.setAllowCredentials(true);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            );
        return http.build();
    }
}
~~~

Danh sách trong ví dụ cần được điều chỉnh theo API thực tế. Nếu frontend gửi bearer token, thêm Authorization vào allowedHeaders. Nếu frontend gửi CSRF token trong header, thêm đúng tên header mà Spring Security đang cấu hình. Không thêm Authorization chỉ vì có thể cần trong tương lai.

Khi bật allowCredentials(true), phải dùng allowedOrigins cụ thể. Nếu có nhiều origin, liệt kê từng origin. Với các origin động theo môi trường, có thể đọc allowlist từ cấu hình triển khai và xác thực chặt chẽ; không dùng mẫu phản chiếu mọi origin.

setExposedHeaders() chỉ công bố response header cho JavaScript. Ví dụ trên không thêm Set-Cookie vì trình duyệt không cho JavaScript đọc header này. Cookie session vẫn được browser xử lý tự động.

### Cấu hình CORS ở Spring MVC

Nếu ứng dụng không dùng Spring Security hoặc muốn cấu hình tại tầng MVC, có thể dùng WebMvcConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders("Content-Type", "X-Request-Id", "X-CSRF-TOKEN")
            .exposedHeaders("X-Request-Id", "X-RateLimit-Remaining")
            .allowCredentials(true)
            .maxAge(600);
    }
}
~~~

Không nên cấu hình nhiều tầng CORS với các chính sách mâu thuẫn. Khi dùng Spring Security, ưu tiên cấu hình CORS được Security sử dụng để preflight không bị chặn trước khi đến MVC. Nếu có reverse proxy hoặc API gateway cũng thêm CORS header, cần xác định một nơi chịu trách nhiệm chính để tránh response có header trùng hoặc giá trị không nhất quán.

## 8. Kết hợp CORS với Spring Session và CSRF

Cookie session thường được trình duyệt tự động gửi. Đây là đặc điểm thuận tiện nhưng cũng tạo ra rủi ro CSRF: một website khác có thể khiến trình duyệt của người dùng gửi request đến ứng dụng đã đăng nhập. CORS chủ yếu kiểm soát việc JavaScript đọc response và một phần việc gửi preflight; CORS không phải biện pháp CSRF.

Khi dùng session cookie để xác thực:

1. Giữ CSRF protection của Spring Security cho các request thay đổi trạng thái như POST, PUT, PATCH và DELETE, trừ khi đã có thiết kế bảo vệ tương đương được đánh giá đầy đủ.
2. Cấu hình frontend lấy CSRF token theo cơ chế ứng dụng hỗ trợ và gửi token trong header được cho phép bởi CORS.
3. Chỉ cho phép origin frontend tin cậy và chỉ cho phép các method/header cần thiết.
4. Dùng cookie HttpOnly, Secure và SameSite phù hợp.
5. Không xem Access-Control-Allow-Credentials: true là dấu hiệu request đã được xác thực; backend vẫn phải kiểm tra session và quyền truy cập.

Nếu dùng Spring Security với CSRF token trong cookie có thể đọc từ JavaScript, hãy cân nhắc kỹ thiết kế cookie token và cookie session. Cookie session nên tiếp tục là HttpOnly. CSRF token không phải session ID và không được dùng thay cho xác thực.

## 9. Ví dụ request thật và response

Sau khi preflight thành công, request thật có thể trông như sau:

~~~http
POST /api/cart/items HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=opaque-session-value
Content-Type: application/json
X-Request-Id: req-7f92
X-CSRF-TOKEN: csrf-token-value

{"productId":"P100","quantity":1}
~~~

Response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-Id
Vary: Origin
X-Request-Id: req-7f92
Content-Type: application/json

{"cartItems":1}
~~~

Trình duyệt gửi cookie nếu frontend dùng chế độ credentials phù hợp và cookie vượt qua các quy tắc Domain, Path, Secure, SameSite. Spring Session dùng cookie ID để tìm session. JavaScript đọc được X-Request-Id vì header này được expose, nhưng không đọc được Set-Cookie hoặc giá trị cookie session.

## 10. Kiểm thử và chẩn đoán CORS

Nên kiểm thử bằng trình duyệt vì trình duyệt mới thực thi chính sách CORS. Kiểm tra hai bước:

**Preflight**

~~~bash
curl -i -X OPTIONS https://api.example.com/api/cart/items \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-request-id,x-csrf-token"
~~~

Xác nhận response có Access-Control-Allow-Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers và các header credentials phù hợp. Curl giúp kiểm tra response của server, nhưng không tự thực thi chính sách CORS của trình duyệt.

**Request thật trong trình duyệt**

- Mở Developer Tools, chọn Network.
- Kiểm tra request OPTIONS và response preflight.
- Kiểm tra request thật có được gửi hay không.
- Xác nhận cookie session có được gửi trong request thật nếu thiết kế yêu cầu.
- Kiểm tra response có Access-Control-Allow-Origin và Access-Control-Allow-Credentials đúng hay không.
- Thử đọc một header đã expose trong JavaScript và một header chưa expose để xác nhận hành vi.
- Kiểm tra cookie trong Application/Storage để xem Domain, Path, Secure, HttpOnly và SameSite.

Các lỗi thường gặp:

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Preflight trả 401 hoặc 403 | Security chặn OPTIONS trước CORS | Bật CORS trong Security và kiểm tra thứ tự filter |
| Preflight không cho phép header | Thiếu header trong allowedHeaders | Thêm đúng header frontend thực sự gửi |
| Request thật được gửi nhưng JavaScript không đọc được response | Origin/credentials không khớp hoặc response thiếu CORS header | Kiểm tra origin cụ thể và Access-Control-Allow-Credentials |
| Cookie session không được gửi | Frontend thiếu credentials hoặc cookie không khớp Domain/Path/SameSite/Secure | Kiểm tra fetch/Axios và thuộc tính cookie |
| JavaScript không đọc được X-Request-Id | Header chưa nằm trong Access-Control-Expose-Headers | Công bố header cần đọc |
| JavaScript không đọc được Set-Cookie | Header bị trình duyệt cấm truy cập từ script | Không expose; để trình duyệt quản lý cookie |
| CORS hoạt động ở dev nhưng lỗi production | Origin, HTTPS, proxy hoặc cấu hình môi trường khác nhau | Kiểm thử bằng URL production và kiểm tra response thực tế |

Nếu response có nhiều Access-Control-Allow-Origin hoặc header CORS được thêm hai lần, kiểm tra cấu hình ở Spring, reverse proxy và gateway. CORS header không nên có các giá trị mâu thuẫn hoặc nhiều origin trong cùng một giá trị header.

## 11. Nguyên tắc cấu hình an toàn

- Phân biệt Access-Control-Allow-Headers với Access-Control-Expose-Headers.
- Chỉ cho phép origin frontend cụ thể; không phản chiếu Origin tùy ý.
- Khi dùng cookie session cross-origin, bật credentials ở frontend và allowCredentials ở server.
- Không kết hợp wildcard origin với credentialed request.
- Chỉ cho phép method và request header API cần dùng.
- Chỉ expose response header thật sự cần thiết cho frontend.
- Không cố expose Set-Cookie; JavaScript không được đọc header này.
- Để Spring Session quản lý session ID qua cookie và không lưu session ID trong web storage.
- Giữ CSRF protection khi xác thực bằng cookie và kiểm tra quyền ở backend.
- Kiểm thử preflight, request thật, cookie và response header trên trình duyệt mục tiêu.

Trong ứng dụng Spring Session, CORS cần được cấu hình cùng với cơ chế cookie và bảo mật của Spring Security. Access-Control-Allow-Headers quyết định frontend có thể gửi header nào; Access-Control-Expose-Headers quyết định JavaScript đọc được response header nào. Khi session cookie được dùng cross-origin, phải cấu hình credentials, origin tin cậy, thuộc tính cookie và CSRF đồng bộ để trình duyệt gửi đúng cookie và chỉ cho frontend được phép đọc dữ liệu cần thiết.
