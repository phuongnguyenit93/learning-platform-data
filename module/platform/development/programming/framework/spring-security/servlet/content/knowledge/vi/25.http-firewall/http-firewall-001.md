# HttpFirewall trong FilterChainProxy và vai trò chuẩn hóa yêu cầu (Spring Security Servlet)

## 1. Bối cảnh: vì sao cần kiểm tra đường dẫn trước khi phân quyền?

Ứng dụng web thường kiểm tra quyền theo URL, ví dụ: /public/** được truy cập công khai, còn /admin/** chỉ dành cho quản trị viên. Cơ chế này chỉ đáng tin khi **reverse proxy, servlet container, Spring Security và Spring MVC hiểu cùng một đường dẫn**. Trong thực tế, chuỗi URL mà client gửi có thể chứa ký tự mã hóa phần trăm (percent encoding), dấu chấm, dấu gạch chéo lặp, dấu chấm phẩy, dấu gạch chéo ngược hoặc các biến thể khiến mỗi tầng diễn giải khác nhau.

Hãy hình dung một đường dẫn chứa các thành phần bất thường như:

~~~text
/admin/../public/ping
/public//ping
/public;v=1/ping
/admin%2Freport
~~~

Bốn ví dụ trên không mặc nhiên tương đương với một URL thông thường. Một proxy có thể sửa đường dẫn trước khi chuyển tiếp; container có thể giải mã hoặc loại bỏ path parameter; Spring MVC có quy tắc route riêng; một request matcher bảo mật có thể dựa trên servletPath và pathInfo. Nếu bước **chọn security filter chain** hoặc **kiểm tra quyền** thấy đường dẫn khác bước **xử lý thực tế**, một URL có thể bị phân loại sai.

**HttpFirewall** là cơ chế Spring Security đặt trước việc chọn các bộ lọc bảo mật. Nó kiểm tra yêu cầu HTTP Servlet, từ chối những dạng request không được chấp nhận và cung cấp request wrapper theo hợp đồng để cơ chế matching làm việc nhất quán hơn.

Ở Spring Security 6.x Servlet, triển khai được dùng mặc định là **StrictHttpFirewall**. Điểm quan trọng nhất: StrictHttpFirewall thường **từ chối** đường dẫn bất thường; nó không phải bộ công cụ có nhiệm vụ âm thầm “làm sạch rồi cho qua” mọi URL. Việc URL có bị chặn từ proxy/container trước khi tới Spring Security vẫn phụ thuộc hạ tầng.

Sau bài này, người học có thể:

- Xác định vị trí HttpFirewall trong DelegatingFilterProxy → FilterChainProxy → SecurityFilterChain.
- Phân biệt **kiểm tra/từ chối**, **chuẩn hóa để matching**, **định tuyến MVC** và **phân quyền**.
- Hiểu các rủi ro từ path traversal, dấu chấm phẩy, slash mã hóa, đường dẫn không chuẩn và HTTP method.
- Cấu hình StrictHttpFirewall có chủ đích; tránh nới lỏng chính sách chỉ để hết HTTP 400.
- Kiểm thử firewall độc lập và kiểm thử đường đi thực tế qua container, proxy và các security filter chain.

Phạm vi bài: **Spring Security cho Servlet stack** (Spring MVC, Spring Boot 3.x, Spring Security 6.x, Java 17+). WebFlux có kiến trúc xử lý request khác; không áp dụng trực tiếp bean/filter ở bài này cho Reactive stack.

## 2. HttpFirewall nằm ở đâu trong đường đi của request?

Sơ đồ khái quát:

~~~text
Client
  |
  v
Reverse proxy / API gateway (nếu có)
  |
  v
Servlet container (Tomcat, Jetty, ...)
  |
  v
DelegatingFilterProxy: "springSecurityFilterChain"
  |
  v
FilterChainProxy
  |
  +--> HttpFirewall
  |       |
  |       +--> Kiểm tra request (method, URL/path, ...)
  |       +--> Nếu vi phạm: RequestRejectedException
  |       +--> Nếu hợp lệ: FirewalledRequest/response wrapper
  |
  +--> Chọn SecurityFilterChain phù hợp (theo matcher)
  |       |
  |       +--> Các security filters trong chain
  |               +--> Authentication / CSRF / Authorization / ...
  |
  v
Servlet filter chain còn lại
  |
  v
DispatcherServlet -> HandlerMapping -> Controller
~~~

**DelegatingFilterProxy** là cầu nối từ servlet filter registration vào bean Spring Security mang tên springSecurityFilterChain. Bean này thường là **FilterChainProxy**, quản lý danh sách các **SecurityFilterChain**. Mỗi SecurityFilterChain có request matcher và tập security filters riêng.

Trong FilterChainProxy, HttpFirewall xử lý request **trước khi FilterChainProxy quyết định chain nào phù hợp**. Nhờ vậy một URL không hợp lệ có thể bị từ chối ngay, không phải để từng AuthenticationFilter hoặc AuthorizationFilter tự giải mã đường dẫn theo cách riêng.

Hợp đồng chính của giao diện HttpFirewall gồm hai thao tác:

~~~java
FirewalledRequest getFirewalledRequest(HttpServletRequest request);
HttpServletResponse getFirewalledResponse(HttpServletResponse response);
~~~

Đoạn trên là **chữ ký minh họa** của giao diện, không phải một chương trình Java chạy độc lập. FirewalledRequest mở rộng HttpServletRequestWrapper và có thao tác reset() dùng trong vòng đời FilterChainProxy. Các wrapper giúp kiểm soát cách request/response được xử lý khi thực thi chuỗi filter. Cụ thể một triển khai firewall có thể kiểm tra giá trị ngay khi wrap hoặc khi getter được gọi.

**Thứ tự thực tế rất quan trọng:** firewall diễn ra trước bước chọn SecurityFilterChain và trước các logic xác thực/phân quyền bên trong chain. Một RequestRejectedException vì URL vi phạm không nên được chẩn đoán là “mật khẩu sai”, “thiếu role” hoặc “CSRF bị chặn”.

## 3. Vai trò “chuẩn hóa” cần hiểu chính xác

Trong tài liệu Spring Security, HttpFirewall thường được mô tả như lớp bảo đảm URL được xử lý nhất quán để request matching an toàn. Nhưng từ **chuẩn hóa** không có nghĩa các triển khai đều biến URL nguy hiểm thành một đường dẫn đẹp hơn.

Cần tách ba khái niệm:

1. **Validation / rejection:** nhận diện request bất thường hoặc không được phép và từ chối. StrictHttpFirewall ưu tiên cách này đối với các biến thể path nguy hiểm.
2. **Consistent matching view:** cung cấp yêu cầu qua firewall wrapper, bảo đảm quá trình chọn SecurityFilterChain và thực thi security filters dựa trên cách nhìn request được firewall cho phép. Các triển khai có thể xử lý path parameters khác nhau.
3. **Application routing:** sau các bộ lọc bảo mật, DispatcherServlet và HandlerMapping tìm controller. HttpFirewall không thay thế Spring MVC routing, cũng không quyết định request có quyền gọi endpoint nào.

Ví dụ minh họa sự khác biệt:

~~~text
Request gốc:  /admin/../public/ping

Cách nhìn A (trước xử lý): /admin/../public/ping
Cách nhìn B (sau chuẩn hóa): /public/ping

Nếu một lớp phân quyền dùng A và lớp xử lý dùng B,
quy tắc bảo mật có nguy cơ đánh giá sai đích thực tế.
~~~

Với StrictHttpFirewall, các đường dẫn không được coi là normalized thường bị **từ chối** thay vì chuẩn hóa rồi tiếp tục. Điều đó thu hẹp khoảng cách giữa các cách diễn giải và tránh việc phân quyền dựa trên chuỗi dễ gây nhầm lẫn.

**Không được suy luận** rằng sau khi đi qua firewall thì mọi chuỗi URL hoặc query string đã an toàn để dùng trực tiếp trong SQL, shell command, đường dẫn tệp, HTML hay template. Firewall không thay thế kiểm tra đầu vào và output encoding.

## 4. StrictHttpFirewall: mặc định chặt chẽ của Spring Security Servlet

**StrictHttpFirewall** kiểm tra nhiều đặc điểm của request và mặc định từ chối một số dạng không bình thường. Các nhóm thường cần biết gồm:

| Nhóm | Ví dụ | Vì sao cần cẩn trọng |
| --- | --- | --- |
| Đường dẫn chưa normalized | /a/../b, /a//b, /a/./b | Có thể bị các tầng chuẩn hóa khác nhau. |
| Dấu chấm phẩy trong đường dẫn | /products;v=1/42 | Matrix variables/path parameters có thể bị container hoặc matcher xử lý khác nhau. |
| Dấu phân cách đường dẫn đã mã hóa | /admin%2Freport, /a%5Cb | Decode một lần hoặc nhiều lần có thể làm thay đổi các path segment. |
| Ký tự mã hóa và điều khiển đáng ngờ | Một số dạng percent encoding, NUL, CR/LF, ký tự điều khiển | Có thể gây mơ hồ đường dẫn hoặc phá vỡ ranh giới xử lý request. |
| HTTP method không nằm trong danh sách cho phép | TRACE, CONNECT, method tự đặt | Giảm những phương thức ngoài tập thao tác ứng dụng mong đợi. |
| Một số giá trị header hoặc parameter vi phạm quy tắc ký tự | Ví dụ control character trong tên header | Giảm dữ liệu request không hợp lệ truyền tiếp vào hệ thống. |

Bảng trên trình bày các **nhóm kiểm tra**, không phải danh sách byte-level đầy đủ cho mọi phiên bản. Quy tắc cụ thể phụ thuộc phiên bản Spring Security và cả container/proxy. Cùng một HTTP request thô có thể bị reverse proxy hoặc servlet container chặn trước khi HttpFirewall quan sát nó.

Danh sách HTTP method được StrictHttpFirewall chấp nhận mặc định thường gồm **GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS**. Các method khác có thể bị từ chối tại firewall. Điều này khác với authorization: một method được firewall chấp nhận **vẫn có thể** bị controller từ chối 405, security filter từ chối 401/403, hoặc bị giới hạn bởi quy tắc API.

Một request bình thường, ví dụ GET /public/ping, không tự nhiên trở thành “được phép” chỉ vì firewall chấp nhận. Nó vẫn phải phù hợp với SecurityFilterChain và thỏa authentication, authorization và những kiểm tra khác.

### Vì sao dấu chấm phẩy bị chặn theo mặc định?

Một số framework hoặc servlet container xem **;** trong URL là path parameter. Ví dụ:

~~~text
/orders;region=eu/42
~~~

Nếu một tầng dùng /orders/42 nhưng tầng khác xét nguyên chuỗi /orders;region=eu/42, quy tắc đường dẫn và dữ liệu route có thể lệch nhau. Spring MVC có tính năng matrix variables cho một số nhu cầu hợp lệ, nhưng việc bật toàn hệ thống phải đi kèm chính sách rõ ràng.

StrictHttpFirewall **không cho phép semicolon theo mặc định**. Nếu ứng dụng thật sự cần matrix variables, có thể cấu hình setAllowSemicolon(true) sau khi đã đánh giá đầy đủ proxy, container, matcher, authorization và mọi URL liên quan. Nới lỏng này mở rộng bề mặt request được chấp nhận, không phải “sửa lỗi Spring Security”.

### Vì sao encoded slash đáng chú ý?

Chuỗi **%2F** thể hiện dấu **/** nếu được percent-decode. Tùy hạ tầng:

- Proxy có thể giữ nguyên %2F.
- Container có thể từ chối, giải mã hoặc chuyển theo thiết lập.
- Framework phía sau có thể diễn giải dấu phân cách path segment khác trước.

Nếu một endpoint kỳ vọng /resource/{id} và id chứa dấu /, thiết kế route có thể gây nhầm lẫn. Thường nên chọn ID URL-safe cho path segment hoặc truyền dữ liệu phức tạp qua vị trí khác được xác thực rõ ràng. Đừng bật setAllowUrlEncodedSlash(true) chỉ để một URL cụ thể hết bị chặn khi chưa kiểm tra toàn bộ đường xử lý.

## 5. HttpFirewall và các matcher: một sự khác biệt có thể nguy hiểm

Một ứng dụng có thể chứa các chain theo phạm vi, ví dụ:

~~~text
Chain 1: /api/admin/**  -> yêu cầu authentication + role ADMIN
Chain 2: /api/**        -> yêu cầu authentication
Chain 3: /**            -> quy tắc mặc định
~~~

FilterChainProxy chọn **SecurityFilterChain đầu tiên** có matcher phù hợp. Với request thông thường, việc này rõ ràng. Nhưng nếu đường dẫn chứa slash lặp, path parameter hoặc encoded separator và các tầng hiểu khác nhau, rất khó đảm bảo request thật sự đi vào chain mong muốn.

HttpFirewall giúp **từ chối ngay các dạng URL bị cấm trước khi chọn chain**. Nó không tự sửa thiết kế chain:

- Nếu chain rộng hoặc cho phép truy cập công khai quá nhiều, firewall không thay thế authorization.
- Nếu thiếu chain mặc định hoặc xếp sai thứ tự, request có thể nhận tập filter không đúng ý thiết kế.
- Nếu endpoint được map ở MVC khác matcher bảo mật do context path, servlet path hoặc version matcher, vẫn cần sửa quy tắc matching.
- Nếu reverse proxy ghi lại path trước khi tới ứng dụng, firewall chỉ kiểm tra request mà ứng dụng nhận được; nó không thể biết chính xác URL gốc nếu proxy đã thay đổi hoặc từ chối.

**Thực hành tốt:** kiểm tra request matcher và controller mapping cùng với behavior thực tế của container; giữ quy tắc fallback rõ ràng như anyRequest().authenticated() hoặc denyAll() tùy chính sách, thay vì hy vọng firewall sẽ chặn mọi lỗi authorization.

### FilterChainProxy có khôi phục thông tin request không?

Mục đích của firewall wrapper là phục vụ bước matching và luồng filter trong ranh giới Spring Security. Ở một số triển khai, phần path đã được xử lý để matching cần được **reset** khi bàn giao request ra servlet chain gốc; FilterChainProxy có cơ chế dùng FirewalledRequest.reset() cho vòng đời đó.

Không nên thiết kế ứng dụng dựa trên giả định rằng firewall sẽ thay đổi vĩnh viễn getRequestURI(), getServletPath() hoặc getPathInfo() theo một định dạng cụ thể. Quy tắc được bảo đảm tùy thuộc firewall implementation. Với StrictHttpFirewall, ý chính là **từ chối biến thể đường dẫn không được cho phép** và kiểm soát request wrapper, chứ không phải cam kết viết lại URL thành một dạng canonical ở mọi tầng.

## 6. Cấu hình Spring Security 6.x với StrictHttpFirewall

Trong Spring Boot 3.x dùng spring-boot-starter-web và spring-boot-starter-security, Spring Security thông thường đã dùng StrictHttpFirewall mặc định. Ví dụ dưới khai báo tường minh để người học nhận ra nơi policy được gắn vào **WebSecurity / FilterChainProxy**.

File src/main/java/demo/firewall/FirewallDemoApplication.java:

~~~java
package demo.firewall;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class FirewallDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FirewallDemoApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

File src/main/java/demo/firewall/SecurityConfig.java:

~~~java
package demo.firewall;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    HttpFirewall httpFirewall() {
        return new StrictHttpFirewall();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(HttpFirewall firewall) {
        return web -> web.httpFirewall(firewall);
    }
}
~~~

Các điểm chính của cấu hình:

1. **SecurityFilterChain** định nghĩa authentication và authorization cho các request hợp lệ. GET /public/ping có thể truy cập không cần đăng nhập; các URL khác cần người dùng xác thực.
2. **HttpFirewall** là một bean độc lập; tại đây triển khai StrictHttpFirewall giữ nguyên chính sách mặc định.
3. **WebSecurityCustomizer** gán firewall vào WebSecurity để FilterChainProxy sử dụng nó trước khi chọn chain. Đây là vị trí đúng để điều chỉnh chính sách firewall.
4. Không có lý do phải tạo một **GenericFilterBean** hoặc dùng http.addFilterBefore(...) để thêm HttpFirewall như một security filter bình thường: firewall là thành phần của FilterChainProxy, không nằm trong danh sách filter của một SecurityFilterChain riêng.
5. Việc đặt HttpFirewall bean không có nghĩa bỏ qua security headers, CSRF, session management hoặc các yêu cầu bảo vệ khác. Các tính năng của Spring Security vẫn do HttpSecurity và từng chain điều khiển.

Ví dụ sử dụng **Java 17+** và Spring Boot 3.x. Để chạy thực tế, tạo dự án Spring Boot có Spring Web, Spring Security; đưa hai file vào đúng package demo.firewall. Lệnh chạy ứng dụng (nếu dùng Gradle Boot plugin và repository đã có Gradle wrapper):

~~~bash
./gradlew bootRun
~~~

Sau khi server khởi động ở cổng 8080 mặc định, kiểm tra endpoint bình thường:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Khi ứng dụng chỉ có controller và cấu hình trên, response hợp lệ sẽ có status HTTP 200 và nội dung **pong**. Không dùng kết quả status của một URL bất thường để khẳng định ngay lớp nào từ chối request: proxy hoặc servlet container có thể chặn trước firewall.

## 7. Nếu buộc phải cho phép semicolon hoặc method đặc biệt

Đây là điểm thường phát sinh khi ứng dụng dùng Spring MVC matrix variables hoặc giao thức client cũ.

### 7.1. Chấp nhận semicolon có điều kiện

Ví dụ chính sách thay thế phần body của bean httpFirewall():

~~~java
@Bean
HttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowSemicolon(true);
    return firewall;
}
~~~

Đoạn trên **chỉ thay đổi chính sách dấu chấm phẩy**. Những kiểm tra còn lại của StrictHttpFirewall vẫn có hiệu lực theo default. Tuy vậy, việc cho phép semicolon có thể khiến URL mà security matcher xét và URL mà MVC map khác nhau, đặc biệt khi container cắt bỏ hoặc giữ path parameters theo cấu hình riêng.

Trước khi bật, hãy xác minh:

- Matrix variables có thực sự là tính năng cần thiết trên endpoint cụ thể, hay có thể thay bằng query parameter hoặc request body?
- Proxy, servlet container, Spring MVC và Spring Security matchers diễn giải path có semicolon như thế nào?
- Mọi URL mang thông tin authorization đều được kiểm thử với và không có path parameter?
- Các chain riêng cho /admin/**, /api/** và đường dẫn công khai có tiếp tục kiểm tra quyền chính xác?

Không nên bật tất cả cờ setAllow... hoặc thay StrictHttpFirewall bằng firewall khác chỉ để “đỡ 400” khi chưa hiểu biến thể URL cụ thể bị từ chối.

### 7.2. Cấu hình danh sách HTTP method (chỉ khi có lý do rõ ràng)

Nếu giao thức của ứng dụng thực sự cần phạm vi HTTP method khác, StrictHttpFirewall có API setAllowedHttpMethods(...). Ví dụ minh họa cách **giới hạn**, không phải khuyến nghị cho mọi dự án:

~~~java
@Bean
HttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowedHttpMethods(
        java.util.List.of("GET", "HEAD", "POST", "OPTIONS")
    );
    return firewall;
}
~~~

Đoạn này là lựa chọn **thay thế** bean httpFirewall() trong ví dụ trước, không định nghĩa trùng nhiều bean cùng kiểu. Với chính sách trên, PUT, PATCH và DELETE bị firewall từ chối ngay cả nếu controller có mapping tương ứng. Cần kiểm thử CORS preflight (OPTIONS), HEAD, các API method và client thực tế trước khi siết danh sách.

**Method allowlist của firewall khác với quyền truy cập endpoint.** Cho phép DELETE tại firewall không có nghĩa mọi người dùng đều được xóa dữ liệu; authorization, CSRF và business validation vẫn áp dụng. Ngược lại, method bị firewall từ chối không bao giờ tới controller dù có role hợp lệ.

### 7.3. Có nên dùng DefaultHttpFirewall?

Spring Security còn có **DefaultHttpFirewall** với chính sách khác, thường được xem là lựa chọn ít nghiêm ngặt hơn ở một số khía cạnh tương thích URL. Không lấy việc chuyển sang DefaultHttpFirewall làm giải pháp mặc định cho lỗi routing hoặc URL encoding: hãy xác định đúng yêu cầu nghiệp vụ, quy tắc hạ tầng, matcher và exception cần thiết.

Nếu cần nới lỏng, ưu tiên điều chỉnh **một hành vi có kiểm soát** của StrictHttpFirewall, lập test và kiểm toán rủi ro. Điều chỉnh firewall ảnh hưởng tới việc diễn giải request của **toàn bộ SecurityFilterChain** gắn với FilterChainProxy, không chỉ một controller.

## 8. RequestRejectedException và cách chẩn đoán mã lỗi

Khi firewall phát hiện yêu cầu vi phạm, nó ném **RequestRejectedException**. Exception này xảy ra sớm, trước khi các security filter xử lý thông thường. Ứng dụng có thể cấu hình RequestRejectedHandler để quyết định cách phản hồi; nhiều cấu hình Spring Security hiện đại chuyển trường hợp này thành **HTTP 400 Bad Request**, nhưng cách xử lý/logging cần kiểm tra theo phiên bản và cấu hình thực tế.

Phân biệt:

| Triệu chứng | Nguyên nhân có thể | Lớp cần kiểm tra |
| --- | --- | --- |
| 400 cho đường dẫn chứa ; hoặc %2F | Firewall hoặc container/proxy từ chối URL | Access log proxy/container, Spring Security firewall logging |
| 400 cho URL bình thường | Input/parser/validation của MVC, firewall khác hoặc proxy | Kiểm tra response, exception và log để xác định nguồn |
| 401 hoặc chuyển trang đăng nhập | Thiếu authentication trong chain đã chọn | AuthenticationEntryPoint, session, HTTP Basic |
| 403 | Authorization, CSRF hoặc một policy khác từ chối | AuthorizationFilter, CsrfFilter, access denied handler |
| 404 | Không có mapping phù hợp hoặc request không tới route dự kiến | DispatcherServlet/HandlerMapping, proxy rewrites |
| 405 | Route tồn tại nhưng không chấp nhận method | Spring MVC method mapping |

**Không phải mọi 400 đều do StrictHttpFirewall.** Với encoded slash, container có thể từ chối trước khi FilterChainProxy chạy. Với request body không hợp lệ, controller layer cũng có thể trả 400. Phải xác định request đã tới Spring Security hay chưa.

**RequestRejectedException không phải AccessDeniedException.** Không mong đợi @ControllerAdvice của MVC hoặc AccessDeniedHandler xử lý mọi request bị firewall từ chối vì thời điểm phát sinh có thể nằm ngoài chuỗi handler/authorization thường lệ.

Khi vận hành, ghi nhận lý do bị từ chối, method, request ID và route liên quan ở mức log phù hợp; tránh đưa raw token, session cookie, thông tin nhạy cảm hoặc toàn bộ request độc hại vào log. Nếu một client hợp lệ bị chặn, ưu tiên sửa đường dẫn client, encoding và proxy trước khi nới firewall.

## 9. Test đơn vị StrictHttpFirewall bằng Spring Mock Servlet

Test trực tiếp firewall giúp tách chính sách lọc URL khỏi hành vi container hoặc Spring MVC. Cần spring-security-web, spring-test và JUnit 5 (thường đến từ spring-boot-starter-security và spring-boot-starter-test).

File src/test/java/demo/firewall/StrictHttpFirewallTest.java:

~~~java
package demo.firewall;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StrictHttpFirewallTest {

    private final StrictHttpFirewall firewall = new StrictHttpFirewall();

    private static MockHttpServletRequest request(String method, String path) {
        MockHttpServletRequest req =
            new MockHttpServletRequest(method, path);
        req.setServletPath(path);
        return req;
    }

    @Test
    void normalGetIsAccepted() {
        assertDoesNotThrow(() ->
            firewall.getFirewalledRequest(
                request("GET", "/public/ping")));
    }

    @Test
    void semicolonIsRejectedByDefault() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("GET", "/public;v=1/ping")));
    }

    @Test
    void encodedSlashIsRejectedByDefault() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("GET", "/admin%2Freport")));
    }

    @Test
    void unsupportedMethodIsRejected() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("TRACE", "/public/ping")));
    }

    @Test
    void semicolonCanBeAllowedExplicitly() {
        StrictHttpFirewall custom = new StrictHttpFirewall();
        custom.setAllowSemicolon(true);

        assertDoesNotThrow(() ->
            custom.getFirewalledRequest(
                request("GET", "/public;v=1/ping")));
    }
}
~~~

Các method trong test gọi trực tiếp getFirewalledRequest() với **MockHttpServletRequest**, nên kiểm tra chính sách StrictHttpFirewall trên các path được truyền vào. Test đầu xác nhận URL thường được firewall chấp nhận; những test tiếp theo xác nhận semicolon, encoded slash và TRACE bị từ chối theo default; test cuối xác nhận ngoại lệ cho semicolon khi cấu hình rõ ràng.

**Giới hạn của test:** MockHttpServletRequest không mô phỏng mọi cách decode, canonicalize và normalize URL của Tomcat, Jetty, ingress hoặc API gateway. Một đường dẫn có %2F có thể bị container từ chối trước firewall trong HTTP request thật; kết quả kiểm thử đơn vị không bảo đảm HTTP status cuối cùng của môi trường production.

Chạy test với wrapper Gradle của dự án nếu dự án đã cấu hình test trên JUnit Platform:

~~~bash
./gradlew test
~~~

Không cần xuất stdout giả định: kết quả Gradle phụ thuộc dependencies, plugin và các test khác trong dự án. Khi test chạy thành công, năm test trên sẽ pass; nếu thất bại, xem assertion và phiên bản Spring Security thực tế thay vì thay firewall để làm test “xanh”.

## 10. Test tích hợp toàn tuyến: proxy, container, filter và controller

Sau test đơn vị, cần phép thử HTTP thật từ bên ngoài đường ingress mà production dùng. Một số request có thể bị từ chối tại nhiều tầng; ghi lại **tầng nào trả response** và đường dẫn ứng dụng thực nhận.

Ví dụ lệnh curl để khảo sát ở localhost:

~~~bash
curl -i 'http://localhost:8080/public/ping'
curl -i --path-as-is 'http://localhost:8080/public;v=1/ping'
curl -i --path-as-is 'http://localhost:8080/public//ping'
curl -i --path-as-is 'http://localhost:8080/admin%2Freport'
~~~

Cờ **--path-as-is** giúp tránh việc curl tự xử lý một số dấu chấm/segment trước khi gửi, nhưng reverse proxy hoặc servlet container vẫn có thể biến đổi request tiếp theo. Đừng coi mã 400 là kết quả bắt buộc cho mọi ví dụ: container, proxy hoặc ứng dụng có thể từ chối sớm bằng mã khác hoặc không chuyển request vào Spring Security.

Kiểm tra theo trình tự:

1. URL hợp lệ vào được đúng route, nhận status và response body dự kiến.
2. URL bất thường đã biết bị chặn **trước controller**; không gây side effect hay truy cập nhầm route.
3. Access log và Spring Security log cho thấy tầng từ chối chính xác.
4. Rule /public/** và /admin/** không thể bị chuyển từ protected sang public bằng path parameter, repeated slash hoặc encoded delimiter.
5. Mỗi servlet container, ingress và CDN trong môi trường đích đều được thử ở mức phù hợp.
6. Cấu hình được phép cho phép semicolon hoặc method đặc biệt phải có test cho cả URL hợp lệ và URL bị lợi dụng để đi nhầm security matcher.

Nếu cần quan sát Spring Security ở môi trường phát triển:

~~~properties
logging.level.org.springframework.security.web.firewall=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

Tên logger và lượng thông tin thực tế tùy phiên bản. Chỉ bật log chi tiết khi có mục đích chẩn đoán; cần kiểm soát dung lượng log và dữ liệu request nhạy cảm. Một server có HTTP status 400 từ proxy không nhất thiết phát ra log từ Spring Security.

### Kiểm thử riêng từng security chain

Với ứng dụng đa chain, viết các trường hợp đại diện cho mọi nhóm URL và method. Ví dụ:

| Request | Kỳ vọng nghiệp vụ | Cần xác minh |
| --- | --- | --- |
| GET /public/ping | Public endpoint | Firewall chấp nhận; matcher cho phép; controller trả pong |
| GET /admin/report | Chỉ người dùng có quyền | Firewall chấp nhận; rơi vào chain/phân quyền bảo vệ |
| GET /public;v=1/ping | Bị reject theo default StrictHttpFirewall | Không có controller side effect |
| GET /admin%2Freport | Bị reject theo default nếu tới firewall ở dạng đó | Không bị chuyển thành public route |
| TRACE /public/ping | Bị reject theo default | Không lọt vào route GET/HEAD bằng nhầm lẫn method |

Các dòng nêu **kỳ vọng kiểm thử**, không khẳng định mã status duy nhất trong mọi môi trường. Dùng response, log và tracing để xác định tầng từ chối.

## 11. Những nhầm lẫn thiết kế dễ gặp

### 11.1. Nghĩ HttpFirewall chính là AuthorizationFilter

HttpFirewall xác định **request có được phép đi tiếp dưới dạng HTTP request hợp lệ hay không**; AuthorizationFilter xác định **principal có quyền truy cập tài nguyên hay không**. Cả hai đều quan trọng nhưng giải quyết vấn đề khác nhau.

Cho phép một URL tại HttpFirewall không đồng nghĩa cho phép truy cập endpoint. Ngược lại, authorization chặt không bảo đảm an toàn khi cơ chế chọn security chain và router nhìn đường dẫn không thống nhất.

### 11.2. Nghĩ HttpFirewall hoạt động giống Web Application Firewall

Tên “firewall” có thể gây nhầm. HttpFirewall trong Spring Security không cung cấp bộ rule phát hiện SQL injection, XSS, bot, DDoS, payload malware, API abuse hoặc toàn bộ OWASP Top 10 như một WAF chuyên dụng. Nó chủ yếu kiểm soát **tính hợp lệ/diễn giải HTTP request ở ranh giới FilterChainProxy**.

Ứng dụng vẫn phải xác thực dữ liệu, mã hóa đầu ra, phân quyền, chống CSRF theo mô hình session, đặt giới hạn tài nguyên và cập nhật dependencies.

### 11.3. Vội bật setAllowUrlEncodedSlash(true)

Khi có 400 ở URL chứa %2F, giải pháp đúng thường là xem lại thiết kế identifier và đường đi request. Nếu một ID có dấu slash, dùng cách biểu diễn URL-safe hoặc một vị trí truyền dữ liệu khác. Nới một cấu hình firewall có thể tạo bất đồng giữa proxy, container và matcher, đặc biệt nếu từng tầng decode khác nhau.

### 11.4. Không phân biệt server nhận gì với client gửi gì

Trình duyệt gửi đường dẫn có thể khác requestURI, servletPath và pathInfo ở ứng dụng khi qua proxy/container. Hãy log/tracing có kiểm soát cả raw path tại ingress và path tại backend khi debug, rồi kiểm tra source of truth cho từng bước. Đừng giả định firewall thấy được byte của HTTP request nguyên thủy.

### 11.5. Chọn chain sai thứ tự

Trong FilterChainProxy, chain có matcher phù hợp đầu tiên được chọn. Firewall chặn một số URL bất thường nhưng không sửa thứ tự chain. Đặt chain chuyên biệt trước chain tổng quát, có fallback phù hợp và test endpoint thật.

### 11.6. Bỏ qua method hoặc đổi case bất thường

Một phương thức như TRACE có thể bị chặn ở firewall trước controller. HTTP method allowlist không phải là security policy cho business operations; cần kiểm tra các phương thức API và CORS preflight riêng. Đừng thêm method tùy biến toàn cục chỉ vì một client thử nghiệm dùng sai giao thức.

### 11.7. Bật cấu hình nới lỏng trên nhiều ứng dụng mà không đánh giá phạm vi

Firewall được gắn ở cấp FilterChainProxy và có thể áp dụng trước mọi SecurityFilterChain trong ứng dụng. Cho phép semicolon để phục vụ một route có thể ảnh hưởng tất cả route. Cần kiểm tra bảo mật của toàn app và mọi endpoint sharing host/servlet context.

### 11.8. Chỉ test MockMvc và bỏ qua request thực

MockMvc không tái hiện hoàn toàn các biến đổi URL ở proxy, container hoặc gateway. Một cấu hình có thể pass MockMvc nhưng thất bại ở production do slash encoding hoặc semicolon bị xử lý khác. Test tích hợp trên hạ tầng triển khai là bước cần thiết.

## 12. Quy trình xử lý sự cố 400 nghi do HttpFirewall

Khi client báo một endpoint hợp lệ bỗng trả 400, làm lần lượt:

1. **Chụp lại request tối thiểu**: method, hostname, raw path và status, tránh sao chép cookie/token vào ticket.
2. **Xác nhận request đã tới backend**: xem access log của reverse proxy/container trước; nếu bị từ chối ở ingress thì sửa ở ingress, không đoán lỗi Spring Security.
3. **Nếu request tới FilterChainProxy**, kiểm tra RequestRejectedException và thông điệp nguyên nhân phù hợp với phiên bản đang chạy.
4. **So sánh URL với endpoint chuẩn**: tìm semicolon, slash lặp, dot segments, encoded slash/backslash, encoded percent và method không mặc định.
5. **Đánh giá thiết kế URL**: client có encode sai không? Có thể biểu diễn ID bằng URL-safe character hoặc dùng query/body hay không?
6. **Xác minh matcher**: sau khi sửa URL, request có đi vào đúng SecurityFilterChain và authorization rule không?
7. **Chỉ nếu cần exception thật sự**, cấu hình chính xác một cờ StrictHttpFirewall, rồi tạo test regression cho cả request hợp lệ và những biến thể có thể bypass.
8. **Thử lại toàn tuyến**, bao gồm proxy/container và ứng dụng; theo dõi response side effect, không chỉ HTTP status.

Không đặt quy tắc “bất kỳ 400 nào cũng đổi thành 200/redirect” ở reverse proxy để làm êm lỗi: điều đó có thể che dấu request bị firewall chặn và biến đường đi bảo mật thành khó quan sát hơn.

## 13. Tổng hợp lựa chọn kỹ thuật

| Quyết định | Khuyến nghị | Điều kiện kiểm tra |
| --- | --- | --- |
| Firewall mặc định | Giữ StrictHttpFirewall khi không có yêu cầu đặc biệt | Test route hợp lệ, method, auth và ingress |
| URL chứa slash/encoded slash trong ID | Ưu tiên thiết kế ID URL-safe hoặc đổi cách truyền | Không lệch path matching giữa các tầng |
| Ứng dụng cần matrix variables | Cân nhắc setAllowSemicolon(true) một cách có chủ đích | Kiểm toán cả proxy, container, MVC, all security chains |
| Có nhiều SecurityFilterChain | Xếp chain chuyên biệt trước chain tổng quát | Test kết quả chọn chain và authorization |
| Có phản hồi 400 bất thường | Xác định tầng từ chối trước khi sửa | Logs, request mapping, firewall exception, container |
| Thử nghiệm firewall | Unit test trực tiếp + integration HTTP thật | Mock request khác HTTP request raw qua proxy |

## 14. Checklist kiến thức để tự đánh giá

- [ ] Giải thích được vì sao URL bất thường có thể gây khác biệt giữa security matcher và MVC/controller routing.
- [ ] Vẽ được thứ tự DelegatingFilterProxy → FilterChainProxy → HttpFirewall → chọn SecurityFilterChain → security filters.
- [ ] Phân biệt StrictHttpFirewall **từ chối** URL không hợp lệ với việc **viết lại** mọi URL thành canonical form.
- [ ] Biết default StrictHttpFirewall chặn semicolon, một số encoded slash/path bất thường và các method không được phép.
- [ ] Biết cách gắn HttpFirewall qua WebSecurityCustomizer mà không giả làm một HttpSecurity filter.
- [ ] Phân biệt RequestRejectedException với lỗi authentication/authorization/CSRF và lỗi từ reverse proxy/container.
- [ ] Viết được test trực tiếp trên MockHttpServletRequest và test HTTP thật trên đường ingress.
- [ ] Chỉ nới firewall sau khi chứng minh nhu cầu nghiệp vụ, đánh giá phạm vi và bổ sung regression tests.
- [ ] Duy trì authorization và validation riêng: firewall không thay thế WAF, security matcher hoặc input validation.

**Kết luận kỹ thuật:** HttpFirewall là chốt kiểm tra nằm **bên trong FilterChainProxy nhưng trước khi chọn SecurityFilterChain**. Nó làm cho quá trình matching tránh phụ thuộc vào các biến thể URL mơ hồ; với StrictHttpFirewall, phần lớn trường hợp bất thường sẽ bị **reject** thay vì được “tự động sửa cho qua”. Hiểu đúng vị trí và giới hạn này giúp vừa giữ quyền truy cập đúng, vừa xử lý những phản hồi 400 do URL không hợp lệ một cách có bằng chứng.
