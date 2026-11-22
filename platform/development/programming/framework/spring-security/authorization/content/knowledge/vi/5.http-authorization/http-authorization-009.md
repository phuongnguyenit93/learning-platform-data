# permitAll so với bỏ qua filter chain bằng ignoring

Trong Spring Security cho ứng dụng Servlet, hai đoạn cấu hình trông như cùng “cho phép tải nội dung công khai” có ý nghĩa bảo mật rất khác nhau:

- **`requestMatchers(...).permitAll()`**: request **vẫn đi qua Spring Security filter chain**, nhưng bước *phân quyền HTTP* cho phép truy cập mà không yêu cầu người gọi có role, authority hoặc đăng nhập.
- **`web.ignoring().requestMatchers(...)`**: request khớp matcher **bỏ qua các security filter do Spring Security quản lý** trong `FilterChainProxy`. Đây không phải một quyết định ALLOW của `AuthorizationFilter`, mà là **không đi qua cơ chế bảo mật đó**.

Với đa số trang công khai và static resources như CSS, JavaScript, ảnh, favicon, lựa chọn **nên dùng mặc định là `permitAll`**. Tài liệu Spring Security 6.x khuyến nghị như vậy vì các tài nguyên công khai vẫn có lợi từ HTTP security headers và những bộ lọc bảo vệ khác; trong Spring Security 6, `permitAll` cũng không cần lấy `Authentication` từ session để quyết định cấp quyền.

Bài viết giải thích chính xác request được xử lý thế nào, những khả năng nào còn hoặc mất, cách cấu hình Spring Boot 3 / Spring Security 6, các trường hợp ngoại lệ cần cân nhắc, cách kiểm thử và những lỗi dễ gây lỗ hổng.

## 1. Bối cảnh: request đi qua các tầng nào?

Một ứng dụng Spring MVC/Servlet thường có các tầng:

~~~text
Client
  |
  v
Servlet container filters (có thể do nhiều thư viện hoặc ứng dụng đăng ký)
  |
  v
DelegatingFilterProxy
  |
  v
FilterChainProxy của Spring Security
  |
  +-- Request khớp một SecurityFilterChain:
  |      SecurityContext / authentication filters / CSRF /
  |      exception handling / security headers / AuthorizationFilter ...
  |         |
  |         +-- requestMatchers(...).permitAll() -> ALLOW ở bước authorization
  |         |   (những filter Spring Security còn lại vẫn có thể hoạt động)
  |         v
  |      Controller / static resource handler
  |
  +-- Request thuộc web.ignoring():
         không thực thi các security filters Spring Security cho request đó
         |
         v
         Controller / static resource handler
~~~

`FilterChainProxy` là nơi phối hợp nhiều `SecurityFilterChain`. Bộ lọc nào thực tế có mặt phụ thuộc cấu hình của ứng dụng: dùng form login, HTTP Basic, resource server JWT hay các filter tùy biến sẽ tạo ra pipeline khác nhau. `permitAll` **không bảo đảm mọi filter đều xuất hiện**, nhưng nó **không chủ động loại bỏ toàn bộ chain**.

`ignoring` cũng **không có nghĩa** request vượt qua mọi middleware trong hệ thống: các Servlet filter nằm ngoài Spring Security, container, gateway, reverse proxy, ứng dụng web và chính trình duyệt vẫn có thể xử lý hoặc từ chối. Kết luận chính xác là **Spring Security không thực thi chuỗi filter của nó trên URL đã ignore**.

Hai thao tác đều **không tạo URL hay file**. Nếu `/assets/app.css` không tồn tại, dù đã `permitAll` hoặc `ignoring`, tầng static resource của ứng dụng vẫn có thể trả **404**.

## 2. So sánh từng thuộc tính, không chỉ “có truy cập được không?”

| Tiêu chí | `permitAll` trong `authorizeHttpRequests` | `web.ignoring()` |
| --- | --- | --- |
| Request đi qua `FilterChainProxy`? | Có; chọn chain phù hợp và chạy các security filter của chain. | URL đã ignore không được chuỗi security filter xử lý. |
| `AuthorizationFilter` có được áp dụng? | Có trong chain dùng `authorizeHttpRequests`; rule công khai trả ALLOW. | Không chạy `AuthorizationFilter` của Spring Security cho URL đó. |
| Có yêu cầu đăng nhập tại **rule HTTP này** không? | Không. | Không có rule HTTP Spring Security để xét. |
| Security response headers của Spring Security? | Được áp dụng nếu chain cấu hình header writer tương ứng. | Spring Security **không thêm** headers qua chain đã bị bỏ qua. |
| CSRF filter? | Vẫn có thể áp dụng cho request thay đổi trạng thái khi CSRF bật. | Không được Spring Security áp dụng cho URL bị ignore. |
| Authentication filters? | Vẫn thuộc pipeline; có thể xử lý credentials được gửi. | Không được Spring Security xử lý trên URL này. |
| CORS do Spring Security tích hợp? | Có thể áp dụng nếu `http.cors(...)` được cấu hình. | Spring Security CORS filter trong chain không chạy. |
| Filter logging/audit/exception handling tùy biến trong security chain? | Có thể chạy theo vị trí và cấu hình. | Không chạy nếu chỉ tồn tại trong Spring Security chain. |
| `SecurityContext` do Spring Security cung cấp? | Có thể được thiết lập theo pipeline. | Không nên dựa vào việc Spring Security thiết lập cho request này. |
| Phạm vi tác động | Rule phân quyền bên trong **chain đã được chọn**. | Bỏ qua Spring Security ở **vùng URL đã ignore**, không chỉ một rule. |
| Mục tiêu sử dụng | Endpoint công khai, trang login, static assets, health endpoint public có chủ đích. | Ngoại lệ kỹ thuật đã được đánh giá đặc biệt, không phải cách mở public endpoint thông thường. |

Lưu ý về cột security headers: **không có bảo đảm mọi header luôn hiện diện**. Ví dụ Spring Security mặc định cung cấp các header phổ biến như `X-Content-Type-Options: nosniff`, `X-Frame-Options`, cache-control và HSTS **trên HTTPS** (theo điều kiện/cấu hình). Header `Content-Security-Policy` (**CSP**) **không được thêm mặc định** và phải được cấu hình nếu ứng dụng cần. Header cũng có thể được đặt hoặc ghi đè bởi server/gateway khác. Câu “`ignoring` làm mất security headers” ở đây nghĩa là **mất cơ chế ghi headers của Spring Security**, không phải chắc chắn response trên mạng không còn header nào.

## 3. Ví dụ cấu hình khuyến nghị: cho phép static resources với permitAll

Giả sử ứng dụng bán hàng có:

- Các file `/assets/**` và `/favicon.ico` tải không cần đăng nhập.
- `GET /public/**` là nội dung công khai; `POST /public/contact` cho khách gửi biểu mẫu.
- `/api/admin/**` cần `ROLE_ADMIN`.
- Mọi endpoint còn lại cần đăng nhập.

Trong Spring Boot 3.x / Spring Security 6.x, có thể tạo lớp cấu hình sau. File **`WebSecurityConfig.java`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/assets/**", "/favicon.ico")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/public/**")
                .permitAll()
            .requestMatchers(HttpMethod.POST, "/public/contact")
                .permitAll()
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .anyRequest()
                .authenticated()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **mã cấu hình cần thư viện Spring Boot/Spring Security và cơ chế tài khoản hợp lệ**, không phải chương trình Java chạy độc lập với JDK thuần. Các ví dụ dùng cấu hình Spring Security 6; API cụ thể cần khớp phiên bản mà ứng dụng thực sự đang chạy.

Ở ví dụ này:

1. `GET /assets/site.css` match rule đầu nên **được thông qua bước phân quyền**, nhưng vẫn vào security chain, nơi có các header writer và filter khác đã bật.
2. `GET /api/admin/users` match rule admin: `hasRole("ADMIN")` mặc định cần authority `ROLE_ADMIN`. Việc route admin xuất hiện **sau** rule asset không nguy hiểm nếu matcher asset thực sự chỉ match asset.
3. `POST /public/contact` không cần đăng nhập tại bước HTTP authorization. **Tuy nhiên CSRF mặc định vẫn bật**; request POST từ trình duyệt dùng cookie/session thường phải gửi CSRF token hợp lệ. Nếu thiếu token, kết quả có thể là **403** dù đã `permitAll`.
4. `GET /api/orders/42` yêu cầu có đăng nhập, nhưng chưa kiểm tra sở hữu Order 42. Đó là chính sách cấp tài nguyên phải thực thi ở tầng service/repository.
5. `anyRequest().authenticated()` áp dụng cho các request còn lại trong chain. Nếu cần mặc định **deny by default** chặt hơn, dùng `anyRequest().denyAll()` và khai báo từng endpoint được phép một cách tường minh.

Dùng `permitAll` **không biến** những URL đó thành “không chịu security”. Nó chỉ nói rằng **không cần điều kiện phân quyền ở lớp HTTP cho URL tương ứng**. Khi ứng dụng có `@PreAuthorize`, policy nghiệp vụ, rate limiting ở gateway, validation hoặc cơ chế kiểm tra khác, các điều kiện đó không tự biến mất.

### Dùng PathRequest của Spring Boot khi phù hợp

Spring Boot có helper dành cho các đường dẫn static resource ở vị trí mặc định. Nếu ứng dụng dùng cấu trúc static chuẩn của Boot, có thể sử dụng trong `authorizeHttpRequests`:

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Đặt bên trong authorizeHttpRequests(auth -> auth ...):
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
~~~

Đây là **trích đoạn DSL**, không phải file độc lập. `PathRequest` thuộc **Spring Boot**, không phải API lõi của Spring Security. Đường dẫn `/assets/**` tự đặt có thể **không thuộc** những common locations; nếu ứng dụng dùng custom assets, phải có matcher riêng. Luôn kiểm tra URL thực tế được MVC cung cấp và chỉ permit đúng tài nguyên muốn công khai.

## 4. Cấu hình ignoring: nó thực sự làm gì?

Cơ chế bỏ qua security filter chain thường được cấu hình bằng `WebSecurityCustomizer`. Đây là cách biểu diễn để **nhận biết và đánh giá cấu hình cũ hoặc ngoại lệ kỹ thuật**, **không phải mẫu khuyến nghị mặc định** cho static resources.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Configuration
public class IgnoredPathsConfig {

    @Bean
    WebSecurityCustomizer webSecurityCustomizer() {
        return web -> web.ignoring().requestMatchers("/assets/**");
    }
}
~~~

Khi request khớp `/assets/**`, `FilterChainProxy` **không chạy các security filter Spring** cho request đó. Nó không chỉ bỏ qua `AuthorizationFilter`; các thành phần như security header writer, authentication filter, CSRF filter, security context handling và filter tùy biến thuộc chain cũng không được thực thi theo luồng Spring Security thông thường.

**Rủi ro thường bị che khuất:** có thể tải `app.css` thành công trong cả hai cấu hình, nên kiểm thử chỉ nhìn status 200 không phát hiện được việc resource công khai mất header bảo mật hoặc mất filter thống kê/an ninh. Chưa kể sau này nhóm phát triển có thể đưa nhầm API nghiệp vụ vào cùng vùng `/assets/**` và vô tình bỏ qua toàn bộ Spring Security.

Nếu một tổ chức buộc phải dùng `ignoring` vì yêu cầu kiến trúc/hiệu năng đã đo đạc, vùng bỏ qua phải **hẹp, cố định, không chứa dữ liệu cá nhân, không có thao tác thay đổi trạng thái và không được biến thành vùng API tùy ý**. Đồng thời phải xác định rõ lớp khác nào cung cấp header và biện pháp an toàn cần thiết. Không sử dụng `ignoring("/**")`, `ignoring("/api/**")` hoặc ignore nguyên vùng chỉ để xử lý nhanh một lỗi 401/403.

Lựa chọn thay thế tốt hơn khi chỉ muốn bỏ qua **một cơ chế cụ thể** là cấu hình chính **cơ chế đó**, ví dụ điều chỉnh CSRF matcher hoặc authentication mechanism theo đúng endpoint, chứ không loại toàn bộ security chain.

## 5. Điểm quan trọng nhất: permitAll không tắt các filter khác

Thử ba request:

~~~text
GET /assets/site.css       (anonymous)
POST /public/contact       (anonymous, thiếu CSRF token)
GET /public/info           (gửi kèm Bearer token không hợp lệ)
~~~

Với một `SecurityFilterChain` đang hoạt động, `permitAll` chỉ trả lời câu hỏi “**AuthorizationFilter có yêu cầu danh tính/quyền không?**”:

- **GET asset công khai:** thường được cho đi tiếp, response có cơ hội được security header writer xử lý. Asset không tồn tại vẫn có thể trả 404.
- **POST public nhưng thiếu CSRF:** có thể bị `CsrfFilter` từ chối bằng 403 nếu request thuộc phạm vi cần CSRF và không có token hợp lệ. Cho phép phân quyền không đồng nghĩa vô hiệu hóa chống CSRF.
- **GET public có Bearer token sai:** nếu resource server authentication filter được bật và xử lý `Authorization: Bearer ...`, request có thể bị từ chối **trước khi** `permitAll` có cơ hội cho phép. “Public” nghĩa không bắt buộc credential, **không có nghĩa credential sai luôn bị bỏ qua**.

Cách giải quyết tình huống đó không phải đổi sang `ignoring` một cách máy móc, vì như vậy làm mất các bảo vệ khác. Hãy xem chuỗi filter thực tế và thiết kế authentication cho URL public khi cần.

### CSRF: tắt chọn lọc khác hoàn toàn ignoring

Giả sử có webhook chỉ dùng chữ ký số độc lập, không dùng browser cookie và không cần CSRF token. Có thể **chỉ bỏ qua CSRF cho endpoint đó** nhưng vẫn giữ các security filters khác. Ví dụ cấu hình **minh họa**:

~~~java
http
    .csrf(csrf -> csrf
        .ignoringRequestMatchers("/webhooks/partner/**"))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/webhooks/partner/**")
            .permitAll()
        .anyRequest().authenticated()
    );
~~~

`csrf.ignoringRequestMatchers(...)` **không phải** `web.ignoring()`: nó chỉ điều chỉnh phạm vi của **CSRF protection**, request vẫn được Spring Security filter chain xử lý. Webhook còn phải xác minh chữ ký, thời hạn, nonce/chống phát lại, nguồn khóa và hạn mức ở thành phần nghiệp vụ; **`permitAll` không phải bảo mật webhook**. Không áp dụng ví dụ bỏ CSRF cho endpoint dùng cookie/Basic trong trình duyệt mà chưa phân tích rủi ro.

### CORS khác với authorization

CORS là quy tắc trình duyệt áp dụng cho yêu cầu cross-origin. Nếu ứng dụng cấu hình `http.cors(...)`, CORS filter được tích hợp với Spring Security chain. Khi `ignoring`, phần tích hợp CORS bên trong Spring Security cũng bị bỏ qua; có thể vẫn có CORS ở MVC hoặc gateway, nhưng đó là một cơ chế khác. Đừng dùng `ignoring` để giải quyết preflight OPTIONS bị 401/403; cần cấu hình CORS và matcher đúng cho đường dẫn thật.

## 6. Security headers: lý do chính Spring Security khuyến nghị permitAll

Spring Security hỗ trợ ghi các header như:

| Header hoặc chính sách | Ý nghĩa thực tiễn | Ghi chú |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Giảm rủi ro trình duyệt suy đoán MIME type không phù hợp. | Có trong default headers của Spring Security Servlet. |
| `X-Frame-Options` | Kiểm soát khả năng nhúng trang vào frame. | Mặc định `DENY` trong nhiều cấu hình chuẩn. |
| `Strict-Transport-Security` | Yêu cầu trình duyệt dùng HTTPS trong tương lai. | Chỉ được thêm trong những điều kiện HTTPS/cấu hình phù hợp. |
| `Cache-Control` / `Pragma` / `Expires` | Mặc định chống cache nhầm nội dung nhạy cảm. | Có thể điều chỉnh cho asset tĩnh cần cache lâu. |
| `Content-Security-Policy` | Hạn chế nguồn script/style và các hành vi trình duyệt. | **Không mặc định được bật**; ứng dụng phải cấu hình. |
| Các header tùy chỉnh | Chính sách nội bộ áp dụng cho toàn bộ response. | Chỉ có nếu ứng dụng/gateway đã thiết lập. |

Với `permitAll`, security header writer trong chain vẫn có thể gắn các header được cấu hình cho response công khai. Với `ignoring`, Spring Security không chạy bộ ghi header đó. Ngay cả một file JavaScript hay HTML công khai cũng có thể cần `nosniff`, CSP theo thiết kế, hoặc header bảo vệ khác.

**Hiệu năng và cache:** các static assets có fingerprint như `app.8fa12.js` thường nên được cache. Default `Cache-Control: no-store` trong Spring Security có thể không phù hợp; giải pháp là **cấu hình cache headers riêng cho static resources** bằng Spring MVC/response hoặc cơ chế CDN phù hợp, không phải tự động bỏ qua security filter chain. Spring Security có thể tôn trọng header cache do ứng dụng đã thiết lập; cần kiểm thử header thực tế thay vì giả định.

Trên nền tảng có reverse proxy/CDN gửi các security headers ở lớp ngoài, các header đó có thể vẫn tồn tại dù request bị ignore ở ứng dụng. Tuy nhiên, quyết định bỏ qua security filter chain vẫn phải được xem xét với **CSRF, Authentication, SecurityContext, CORS và các filter tùy biến** chứ không chỉ với headers.

## 7. Hiệu năng: permitAll có bắt buộc truy cập session không?

**Không phải trong Spring Security 6.x.** Với cơ chế `authorizeHttpRequests` hiện đại, `permitAll` (và `denyAll`) có thể quyết định mà **không cần lấy `Authentication` từ session** ở bước request authorization. Đó là một trong các lý do tài liệu Spring Security khuyến nghị `permitAll` thay vì ignore static assets.

Nhưng câu “`permitAll` không đọc Authentication để phân quyền” **không có nghĩa** toàn bộ security chain không bao giờ đọc session hoặc làm công việc nào: một authentication filter, security context repository, custom filter hay cơ chế khác vẫn có thể xử lý request tùy cấu hình.

Khi muốn tối ưu tài nguyên tĩnh:

1. Đầu tiên dùng `permitAll`, rule URL/method hẹp, và đo latency/CPU/khả năng cache.
2. Xem nguyên nhân tốn kém có phải custom authentication filter luôn truy database hay không.
3. Nếu vấn đề nằm ở filter tùy biến, sửa matcher/logic của **filter đó** hoặc dùng cấu trúc chain riêng phù hợp, không loại toàn bộ Spring Security.
4. Nếu các asset đã được CDN phục vụ ngoài ứng dụng, cân nhắc tách đường đi từ kiến trúc cấp hạ tầng; phân tích trách nhiệm security headers và truy cập tại CDN.
5. Chỉ cân nhắc `ignoring` khi có bằng chứng hiệu năng đủ lớn, biết rõ tất cả biện pháp bảo vệ bị mất, có test định kỳ và chấp thuận rủi ro phù hợp.

Không phải mọi request static đều nhỏ hoặc không nhạy cảm. File upload, tài liệu hóa đơn, avatar riêng tư, export CSV và object storage proxy có thể nhìn như “file” nhưng chứa dữ liệu cần quyền; **không ignore chỉ vì URL có phần mở rộng tệp**.

## 8. Phân biệt ignoring, permitAll, securityMatcher và không có chain khớp

Đây là bốn khái niệm thường bị gộp thành một:

| Trường hợp | Tác động | Cần hiểu |
| --- | --- | --- |
| `authorizeHttpRequests(...permitAll())` | Cho phép tại **một quy tắc phân quyền HTTP**. | Các filter của chain vẫn có thể hoạt động. |
| `web.ignoring().requestMatchers(...)` | Request bỏ qua **Spring Security filter chain**. | Không phải chỉ “không cần login”. |
| `http.securityMatcher("/api/**")` | Giới hạn những request mà **một SecurityFilterChain** bảo vệ. | Request ngoài `/api/**` có thể thuộc chain khác. |
| Không có `SecurityFilterChain` nào khớp | Request nằm **ngoài bảo vệ Spring Security**. | Đây thường là lỗ hổng khi thiếu fallback chain. |

Sơ đồ quyết định:

~~~text
FilterChainProxy
  |
  +-- URL thuộc global ignoring?
  |       YES -> bỏ qua Spring Security filters
  |
  +-- chọn SecurityFilterChain đầu tiên khớp request
          |
          +-- nếu không có chain -> không được Spring Security bảo vệ
          |
          +-- nếu có chain -> chạy filters của chain
                              |
                              +-- AuthorizationFilter đọc rules
                                    |
                                    +-- permitAll -> cho qua authorization
                                    +-- authenticated/hasRole/... -> xét điều kiện
                                    +-- denyAll -> chặn authorization
~~~

Nếu có nhiều chain, `@Order` quyết định thứ tự kiểm tra các chain; chain đầu tiên match request thắng. Bên trong chain đó, `authorizeHttpRequests` dùng rule `requestMatchers` đầu tiên khớp. **Tự đặt `anyRequest().permitAll()` ở đầu hoặc `web.ignoring("/**")` có thể mở rộng phạm vi công khai không mong muốn.**

### Trường hợp cấu hình nhiều chain

Ví dụ tách API riêng và website:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/assets/**", "/login").permitAll()
        .anyRequest().authenticated());
    return http.build();
}
~~~

Đây là **mảnh cấu hình đặt trong class `@Configuration`**, cần import `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, và cơ chế đăng nhập phù hợp. Không thể chạy độc lập với JDK. Chain website không có `securityMatcher` nên là fallback; `/assets/**` được permit trong web chain và **vẫn đi qua security filters của web chain**. Nếu `/assets/**` bị đưa vào `web.ignoring`, cả hai chain của Spring Security không còn được dùng để xử lý vùng đó.

**Một lỗi nguy hiểm** là cấu hình API chain chỉ match `/api/**`, nhưng không có fallback cho `/admin/**`; request `/admin/users` khi đó có thể nằm ngoài Spring Security. Đó là lỗ hổng **thiếu chain**, không phải `permitAll`, nhưng hậu quả “không được security filters bảo vệ” tương tự về bản chất.

## 9. Nên dùng gì cho các nhóm URL phổ biến?

| Nhóm URL | Khuyến nghị | Vì sao |
| --- | --- | --- |
| `/css/**`, `/js/**`, `/images/**`, `/favicon.ico` public | **`permitAll`** | Công khai nhưng vẫn giữ security headers/filter chain. |
| `/`, trang giới thiệu, tài liệu public | **`permitAll`** | Có thể chứa HTML/script nên header bảo mật đặc biệt có giá trị. |
| `GET /products/**` công khai | **`permitAll`** | Authorization không đòi đăng nhập, nhưng service vẫn kiểm soát dữ liệu công khai và các filter khác vẫn chạy. |
| Form login GET/POST | Cho phép truy cập theo cấu hình `formLogin` và URL tương ứng | Login vẫn cần các authentication và CSRF filter. |
| `POST /public/contact` | **`permitAll` + CSRF/rate limit/validation** theo mô hình | Không cần đăng nhập không có nghĩa bỏ mọi bảo vệ. |
| `POST /webhooks/partner` | Authorization có thể `permitAll`; thiết kế xác thực chữ ký riêng | Chỉ bỏ CSRF có điều kiện nếu phù hợp; **không ignore cả chain**. |
| `GET /actuator/health` public có kiểm soát | `permitAll` **đúng endpoint** nếu được phê duyệt | Không mặc định công khai cả `/actuator/**`, đặc biệt env, heapdump, config. |
| File tải xuống riêng tư, hóa đơn, báo cáo | **Yêu cầu phân quyền + kiểm tra tài nguyên** | Đường dẫn trông như static không đồng nghĩa public. |
| JavaScript/HTML được CDN phục vụ bên ngoài ứng dụng | Policy tại CDN/gateway | Không phải case `WebSecurityCustomizer` trong app nếu request không đến app. |

Đừng dùng matcher theo phần mở rộng như `/**/*.pdf` để mặc định cho qua: PDF có thể là hợp đồng cá nhân; CSV có thể chứa dữ liệu khách hàng. Hãy thiết kế **từ phân loại dữ liệu và hành động**, không từ đuôi URL.

## 10. Một chương trình Java 17+ chạy độc lập để quan sát hai cơ chế

Chương trình sau là **mô phỏng có chủ đích**, không phải code Spring Security. Nó biểu diễn ba ý chính: `permitAll` cho phép request ở **bước authorization** trong khi các filter vẫn chạy; `ignoring` đưa request đi thẳng sang ứng dụng **không qua security filters**; và request POST công khai có thể bị CSRF chặn khi protection vẫn bật.

Mô hình đặt `securityHeaders=true` cho request đi qua chain để đại diện cho một cấu hình Spring Security **đang bật header writer**. Trong ứng dụng thật, header có mặt hay không phụ thuộc cấu hình, HTTPS, MVC, gateway và header writer cụ thể. `forwarded=true` ở đây chỉ là “được chuyển tới handler”, **không phải cam kết HTTP 200**.

Lưu chương trình với đúng tên **`PermitAllVsIgnoringDemo.java`**:

~~~java
public class PermitAllVsIgnoringDemo {
    record Request(String method, String path,
                   boolean authenticated, boolean csrfValid) {}

    record Outcome(boolean filtersRan, boolean forwarded,
                   boolean securityHeaders, String result) {}

    static Outcome handle(Request request, boolean ignoreAssets) {
        boolean asset = request.path().startsWith("/assets/");
        if (ignoreAssets && asset) {
            return new Outcome(false, true, false, "BYPASS");
        }

        boolean stateChanging = !request.method().equals("GET")
                && !request.method().equals("HEAD")
                && !request.method().equals("OPTIONS")
                && !request.method().equals("TRACE");

        if (stateChanging && !request.csrfValid()) {
            return new Outcome(true, false, true, "CSRF_DENIED");
        }

        boolean publicPath = asset || request.path().startsWith("/public/");
        if (publicPath || request.authenticated()) {
            return new Outcome(true, true, true, "ALLOW");
        }
        return new Outcome(true, false, true, "AUTH_REQUIRED");
    }

    static String describe(Outcome outcome) {
        return "filters=" + outcome.filtersRan()
                + ", forwarded=" + outcome.forwarded()
                + ", headers=" + outcome.securityHeaders()
                + ", result=" + outcome.result();
    }

    public static void main(String[] args) {
        Request staticGet = new Request("GET", "/assets/app.css", false, false);
        Request privateGet = new Request("GET", "/api/profile", false, false);
        Request publicPost = new Request("POST", "/public/contact", false, false);
        Request postWithCsrf = new Request("POST", "/public/contact", false, true);

        System.out.println("Asset permitAll: "
                + describe(handle(staticGet, false)));
        System.out.println("Asset ignoring: "
                + describe(handle(staticGet, true)));
        System.out.println("Private anonymous: "
                + describe(handle(privateGet, false)));
        System.out.println("Public POST without CSRF: "
                + describe(handle(publicPost, false)));
        System.out.println("Public POST with CSRF: "
                + describe(handle(postWithCsrf, false)));
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 PermitAllVsIgnoringDemo.java
java PermitAllVsIgnoringDemo
~~~

Kết quả chính xác:

~~~text
Asset permitAll: filters=true, forwarded=true, headers=true, result=ALLOW
Asset ignoring: filters=false, forwarded=true, headers=false, result=BYPASS
Private anonymous: filters=true, forwarded=false, headers=true, result=AUTH_REQUIRED
Public POST without CSRF: filters=true, forwarded=false, headers=true, result=CSRF_DENIED
Public POST with CSRF: filters=true, forwarded=true, headers=true, result=ALLOW
~~~

**Đọc kết quả:** hai tình huống asset đều được chuyển tới handler, nhưng cơ chế khác hẳn. Với `permitAll`, request đi qua chain và có thể được ghi headers; với `ignoring`, request bypass chain. Request private anonymous bị chặn; `POST /public/contact` thiếu CSRF bị từ chối **trước khi** phép kiểm tra công khai hoàn thành. Đây là mô hình học logic, không thay thế integration test với Spring MVC và cấu hình filter thật.

## 11. Kiểm thử thực tế: không được chỉ xem mã trạng thái 200

Để phân biệt hai cấu hình, cần test **cả pipeline** chứ không chỉ endpoint có mở được không. Với Spring Boot và `spring-security-test`, `MockMvc` có thể chạy qua Spring Security filter chain nếu test được cấu hình đúng.

Đối với `permitAll`, kiểm tra ít nhất:

- Request anonymous đến asset công khai **không bị yêu cầu login** tại AuthorizationFilter, và các default headers mà bạn bật thực sự có mặt.
- Private endpoint vẫn bị từ chối khi anonymous (401 với HTTP Basic, hoặc redirect tùy cơ chế), tránh rule `permitAll` quá rộng.
- POST công khai nhưng CSRF bật không tự động thành công khi thiếu CSRF token.
- Request gửi credentials sai được authentication filters xử lý đúng theo cấu hình, không giả định “public” đồng nghĩa bỏ qua mọi xác thực.
- Khi đổi tên hoặc đường dẫn tài nguyên, matcher còn phù hợp, không để asset mới vô tình bị chặn hoặc private resource bị công khai.

Ví dụ các assertion **minh họa trong Spring Boot integration test** (phải có `MockMvc`, static imports và các endpoint/resource thật):

~~~java
// Cấu hình security headers mặc định đang bật:
mvc.perform(get("/assets/app.css"))
    .andExpect(header().string("X-Content-Type-Options", "nosniff"));

// POST đã permitAll nhưng CSRF protection vẫn áp dụng:
mvc.perform(post("/public/contact"))
    .andExpect(status().isForbidden());

// Với CSRF token, request có thể đi đến controller:
mvc.perform(post("/public/contact").with(csrf()));
// Sau bước này còn phụ thuộc controller và validation.
~~~

Nếu asset không tồn tại, `get("/assets/app.css")` có thể trả 404, nhưng header assertion vẫn hữu ích để quan sát việc request đi qua header writer. Để tránh nhầm, trong test môi trường thật nên tạo một file asset có thật rồi kiểm tra cả body/content type, không chỉ header.

Khi thử `ignoring`, **đừng tự động assert “không có bất kỳ security header nào”**; reverse proxy hoặc Servlet filter khác có thể gắn header. Hãy kiểm chứng rằng **Spring Security filter chain không được gọi** bằng integration test/quan sát phù hợp, và xác định những header nào thực sự do ứng dụng/gateway bảo đảm.

### Test ma trận cần có

| Trường hợp | `permitAll` với chain mặc định hợp lệ | `ignoring` |
| --- | --- | --- |
| GET asset công khai | Cho qua authorization và vẫn chạy security filters | Bỏ qua security filters |
| GET asset kèm credential sai | Có thể bị authentication filter chặn | Authentication filter của Spring Security không chạy |
| GET private anonymous | Bị chặn bởi rule cần login | Không nằm trong phạm vi ignore nếu cấu hình hẹp |
| POST public, CSRF thiếu | Có thể 403 do `CsrfFilter` | Nếu URL bị ignore thì không bị Spring CSRF kiểm tra |
| HTTP response headers | Security header writer có thể thêm các header cấu hình | Header writer của Spring Security không chạy |
| URL public sau này chuyển thành private | Sửa rule `permitAll` tương ứng | Nếu vẫn ignore, Spring Security vẫn bị bypass |
| Endpoint không tồn tại | Có thể 404 sau khi qua security | Cũng có thể 404 tại handler |

Tất cả kỳ vọng về 401/403/redirect/header cụ thể phải dựa trên cấu hình thực, không chỉ vào tên `permitAll` hay `ignoring`.

## 12. Những lỗi và cách xử lý đúng

1. **“CSS công khai nên ignore cho nhanh.”** → Thử `requestMatchers("/css/**").permitAll()` trước; dùng profiler để chứng minh cần ngoại lệ, vì Spring Security 6 không cần lấy Authentication cho `permitAll` tại bước authorization.
2. **“PermitAll làm Spring Security không chạy.”** → Sai: chỉ nới lỏng rule phân quyền. Security headers, CSRF, authentication và các filter khác có thể vẫn chạy.
3. **“POST công khai bị 403, vậy phải đổi sang ignoring.”** → Tìm xem CSRF có yêu cầu token hay không; sửa quy tắc CSRF theo mô hình xác thực nếu phù hợp, không bypass cả chain.
4. **“Dùng ignoring cho /api/** để giải quyết lỗi CORS.”** → Đây là lỗ hổng nghiêm trọng. Cấu hình CORS và preflight một cách hẹp, vẫn kiểm tra quyền request thật.
5. **“Static resources không cần security headers.”** → Ngay cả HTML/JS/CSS công khai cũng có lợi từ `nosniff` và headers được cấu hình. Đừng bỏ hệ thống header writer nếu không có phương án thay thế.
6. **“Có CDN gửi headers rồi thì ignore luôn.”** → CDN không thay thế authentication/CSRF/security context/filter tùy biến của ứng dụng; phải kiểm toán toàn bộ trách nhiệm.
7. **“`securityMatcher` và ignoring là một.”** → `securityMatcher` chọn một chain; ignoring loại request khỏi các security filters. Khi không chain nào match cũng cần nhận diện là lỗ hổng.
8. **“`permitAll` có nghĩa không cần dữ liệu nghiệp vụ an toàn.”** → Endpoint công khai vẫn cần validation, rate limit, chống lạm dụng, và không được lộ dữ liệu private qua ID.
9. **“Chỉ test 200 OK là đủ.”** → Test headers, CSRF, authentication, private routes, ranh giới match và những filter phải hoạt động.
10. **“Đổi role/permission bằng bỏ chain.”** → Nếu có 403 vì mapping authority sai, hãy sửa authentication/authorization đúng nguồn; không dùng ignoring làm đường tắt.
11. **“Bật CSP mặc định rồi.”** → Spring Security không tự thêm CSP; muốn có CSP cần khai báo policy phù hợp và kiểm tra response.
12. **“Không chain match thì chắc có denyAll.”** → Không đúng. `anyRequest().denyAll()` chỉ có hiệu lực trong chain đã chọn. Nếu không chain nào match, Spring Security không bảo vệ request đó.

## 13. Checklist trước khi quyết định công khai một đường dẫn

Trước khi đặt `/assets/**`, `/public/**` hay `/health` ra ngoài đăng nhập, cần trả lời:

1. **Có thật sự public không?** Mọi nội dung của vùng URL, kể cả các file mới và các method khác, có được phép cho anonymous không?
2. **Đường dẫn có match đúng không?** Kiểm tra cả MVC mapping, URL prefix, `securityMatcher`, `requestMatchers` và thứ tự các rule.
3. **Bảo vệ nào vẫn cần?** Security headers, CSRF, CORS, authentication nếu có token, rate limiting, request validation, audit và policy domain.
4. **Có thể công khai bằng `permitAll` không?** Trong đa số trường hợp là **có**; ưu tiên cách này thay vì bỏ security filters.
5. **Nếu có ngoại lệ ignoring, vì sao?** Phải có lý do rõ ràng và kiểm chứng được, phạm vi tối thiểu, chính sách thay thế và ca test bảo đảm không mở rộng ngoài ý muốn.
6. **Khi quyền thay đổi, ai kiểm thử?** Một endpoint public sau này thành private phải được loại khỏi `permitAll` hoặc vùng ignoring và có test phủ trường hợp anonymous.
7. **Phản hồi có những headers gì?** Kiểm tra trên HTTP và HTTPS đúng môi trường; không coi CSP, cache-control hay HSTS là luôn có cùng giá trị.
8. **Các đường dẫn không match chain thì sao?** Định nghĩa fallback chain hoặc chính sách bao phủ được kiểm tra, tránh vùng không được Spring Security bảo vệ.

**Kết luận:** `permitAll` và `ignoring` **không tương đương**. `permitAll` cho phép truy cập ở **bước authorization của một chain vẫn hoạt động**. `ignoring` làm request **không đi qua các security filters của Spring Security**. Với static resources và endpoint công khai, **`permitAll` là lựa chọn được Spring Security 6.x khuyến nghị**; chỉ dùng ignoring trong ngoại lệ đã đánh giá toàn bộ tác động đến headers, authentication, CSRF và các thành phần bảo vệ khác.

### Tài liệu tham khảo

- [Spring Security 6.5 – Authorize HttpServletRequests: Favor permitAll over ignoring](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 – Java Configuration, RequestMatcher và filter chains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
