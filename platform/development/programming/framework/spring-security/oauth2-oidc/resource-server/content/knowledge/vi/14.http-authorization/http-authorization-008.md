# Đường đi không thuộc chuỗi bảo mật và cách kiểm tra độ bao phủ

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, API thường được bảo vệ bằng một hoặc nhiều **SecurityFilterChain**. Mỗi chain có bộ lọc xác thực và các quy tắc phân quyền như **hasAuthority("SCOPE_orders.read")**, **authenticated()**, **permitAll()** hoặc **denyAll()**.

Một sai lầm nguy hiểm là tưởng rằng chỉ cần khai báo **anyRequest().authenticated()** trong một chain thì mọi URL của ứng dụng đều đã được bảo vệ. Thực tế, **FilterChainProxy chỉ chạy các security filters của SecurityFilterChain đầu tiên khớp request**. Nếu không chain nào khớp, các filter và authorization rule của những chain đó **không được áp dụng** cho request.

Một endpoint vẫn có thể bị chặn ở API Gateway, firewall hoặc lớp bảo mật khác. Tuy nhiên, nếu đang dựa vào Spring Security để bảo vệ Resource Server, cần coi **request không thuộc chuỗi bảo mật** là một khoảng trống phải xử lý, đặc biệt khi vẫn có controller/servlet phục vụ request đó.

Bài này giải thích cách Spring Security chọn chain, phân biệt **securityMatcher** với **requestMatchers**, thiết kế fallback, kiểm tra độ bao phủ bằng endpoint có thật, và những điểm dễ bị bỏ qua như HTTP method, servlet path, reverse proxy, Actuator và dispatcher type.

## 1. Ba trạng thái rất khác nhau của một đường dẫn

| Trạng thái | Có SecurityFilterChain được chọn? | Authorization rule có được thực thi? | Ý nghĩa |
|---|---|---|---|
| **Được permitAll() trong chain** | Có | Có; policy cho phép request không cần xác thực | Public endpoint **có chủ đích** |
| **Được authenticated()/hasAuthority trong chain** | Có | Có; policy kiểm token và quyền theo cấu hình | Endpoint có kiểm soát bảo mật |
| **Không khớp bất kỳ chain nào** | Không | Không; Spring Security chain không xử lý request | Có thể thành **vùng mù** nếu endpoint vẫn truy cập được |

Một trường hợp khác là **web.ignoring()**: Spring Security được hướng dẫn bỏ qua request thuộc một số matcher. Đây không phải **permitAll()** và không nên được dùng tùy tiện cho API nghiệp vụ.

### 1.1. Ví dụ một đường đi bị bỏ lọt

Ứng dụng có controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InternalReportController {
    @GetMapping("/internal/reports")
    String reports() {
        return "internal data";
    }
}
~~~

Nhưng chỉ có một SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );
    return http.build();
}
~~~

**/internal/reports không thuộc phạm vi /api/**. Nếu không còn chain nào khác khớp, **anyRequest().authenticated()** trong **apiChain** không bảo vệ endpoint đó. Một request không Bearer token có thể đi tiếp đến controller, nếu không có cơ chế bảo vệ khác.

**Nguyên tắc:** **anyRequest** chỉ bao phủ những request đã được lựa chọn vào **chính chain đó**. Nó không phải một lệnh phủ tất cả servlet hay tất cả HTTP port trong hệ thống.

## 2. Cách FilterChainProxy chọn SecurityFilterChain

Trong ứng dụng **Servlet**, Spring Security thường đăng ký bộ lọc thông qua **DelegatingFilterProxy**, ủy thác cho bean **springSecurityFilterChain**. Bean này thường là một **FilterChainProxy** giữ danh sách **SecurityFilterChain** có thứ tự.

Mỗi SecurityFilterChain có:

1. **RequestMatcher** xác định request nào thuộc chain.
2. Danh sách security filters được chạy cho request được chọn.
3. Một vị trí trong danh sách so với các chain khác.

**Chain đầu tiên có matcher khớp sẽ được chọn.** Spring Security không tự chạy mọi chain phù hợp rồi cộng dồn tất cả policy.

~~~mermaid
flowchart TD
    R[HTTP request] --> P[DelegatingFilterProxy / FilterChainProxy]
    P --> C1{Chain 1 matches?}
    C1 -->|Có| F1[Chạy filters chain 1]
    C1 -->|Không| C2{Chain 2 matches?}
    C2 -->|Có| F2[Chạy filters chain 2]
    C2 -->|Không| C3{Fallback chain matches?}
    C3 -->|Có| F3[Chạy filters fallback]
    C3 -->|Không| U[Không có security chain phù hợp]
    F1 --> A[Authentication và authorization tương ứng]
    F2 --> A
    F3 --> A
    U --> H[Request tiếp tục theo các lớp còn lại]
~~~

### 2.1. First match wins

Giả sử các chain được đăng ký:

~~~text
@Order(1): securityMatcher("/api/admin/**")
@Order(2): securityMatcher("/api/**")
@Order(3): matcher mặc định cho mọi request còn lại
~~~

Thứ tự chọn:

| Request | Chain được chọn |
|---|---|
| **GET /api/admin/reports** | Chain 1 |
| **GET /api/orders/42** | Chain 2 |
| **GET /health/live** | Chain 3 |
| **GET /internal/reports** | Chain 3 |

**/api/admin/reports** đồng thời có thể khớp **/api/**, nhưng chain thứ hai không được chạy vì chain thứ nhất đã khớp.

Nếu chain quản trị đầu tiên chỉ dùng **authenticated()**, còn chain API thứ hai có rule **hasAuthority("SCOPE_admin.read")**, rule của chain thứ hai **không tự được cộng thêm** cho request admin. Phải đặt toàn bộ policy cần thiết vào chain được chọn đầu tiên.

### 2.2. Đừng dựa vào Boot tự tạo fallback

Spring Boot có security auto-configuration khi ứng dụng không tự cấu hình security. Khi ứng dụng khai báo **SecurityFilterChain** riêng, cấu hình chain mặc định do Boot cung cấp thường lùi lại.

Vì thế, nếu chỉ khai báo một chain giới hạn **/api/** thì **không được giả định** Spring Boot sẽ luôn thêm một chain bảo vệ các endpoint ngoài **/api/**. Một thư viện khác có thể có thêm chain, nhưng phải xác nhận tại runtime, không suy luận từ một file Java.

## 3. securityMatcher khác requestMatchers ở đâu?

Có hai cấp matcher thường bị lẫn.

### 3.1. securityMatcher: phạm vi của cả chain

~~~java
http.securityMatcher("/api/**");
~~~

Dòng này quyết định **chain hiện tại có được chọn hay không** cho một request. Nếu URL không khớp, Spring Security tiếp tục tìm chain khác. Các rule bên trong chain hiện tại **không được đánh giá**.

### 3.2. requestMatchers trong authorizeHttpRequests: chọn rule trong chain

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest()
        .authenticated()
);
~~~

Những rule này được xét **sau khi request đã vào chain**.

Kết hợp hai cấp:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

Kết quả:

- **/api/admin/reports**: vào chain và cần **ROLE_ADMIN**.
- **/api/orders/42**: vào chain và cần authentication.
- **/internal/reports**: **không vào chain này**, nên không chịu **anyRequest** của nó.

~~~mermaid
flowchart TD
    R[Request] --> S{securityMatcher của chain khớp?}
    S -->|Không| N[Thử SecurityFilterChain kế tiếp]
    S -->|Có| M[Đánh giá authorizeHttpRequests]
    M --> C[requestMatchers cụ thể]
    M --> A[anyRequest trong chain]
    C --> Q[Kiểm policy tương ứng]
    A --> Q
~~~

**securityMatcher chọn chain; requestMatchers chọn rule bên trong chain.**

## 4. Một cấu hình an toàn hơn với fallback chain

Giả sử ứng dụng Orders API cần:

- Các request **/api/** đi qua JWT Resource Server.
- **GET /api/public/** cho phép public có chủ đích.
- **GET /api/orders/** yêu cầu scope **orders.read**.
- API khác ít nhất phải xác thực.
- **GET /health/live** là endpoint health public.
- Những đường đi còn lại bị từ chối mặc định.

Ví dụ **Spring Security Servlet**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http
            // Không giới hạn securityMatcher: dùng matcher mặc định.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health/live")
                    .permitAll()
                .anyRequest()
                    .denyAll()
            );

        return http.build();
    }
}
~~~

Ý nghĩa:

1. **@Order(1)** bảo đảm API chain được xem trước.
2. Request thuộc **/api/** dùng cơ chế Bearer JWT do chain đó cấu hình.
3. **/api/public/** được phép truy cập không token nhưng vẫn thuộc chain API.
4. **@Order(2)** là fallback không giới hạn matcher, bao phủ những request chưa được chain trước chọn.
5. Fallback chỉ cho **GET /health/live** đi qua; các route khác bị **denyAll()**.
6. Thêm mới **/internal/export** mà chưa khai báo policy sẽ không âm thầm thành endpoint public nếu request thật sự đi qua FilterChainProxy.

**Đây là cấu hình minh họa**, chưa bao gồm đầy đủ các đường dẫn và HTTP method của mọi ứng dụng. Có thể cần cấu hình CORS, Actuator, trang lỗi, static assets, request DELETE/PUT, CSRF theo mô hình client và các endpoint nghiệp vụ khác. Mỗi ngoại lệ phải có chủ đích và được kiểm thử.

### 4.1. Khi nào fallback dùng authenticated thay vì denyAll?

Nếu kiến trúc yêu cầu các endpoint ngoài **/api/** cũng nhận Bearer token và hoạt động, có thể sử dụng chain bao phủ tương ứng với authentication/authorization đúng. **denyAll** là lựa chọn fail-closed mạnh khi không có route ngoài nhóm được phép.

Không nên tự động đặt **anyRequest().authenticated()** và coi đã an toàn cho tất cả hành động: **authenticated** chỉ yêu cầu đã xác thực, không đòi scope **orders.write** hay quyền export. Với endpoint nhạy cảm, cần policy cụ thể và quyền theo tài nguyên.

### 4.2. Đừng đặt chain catch-all trước

Ví dụ nguy hiểm:

~~~text
@Order(1): matcher /**            -> permitAll()
@Order(2): matcher /api/**        -> OAuth2 JWT Resource Server
~~~

Chain đầu tiên khớp mọi request, nên chain API phía sau có thể không bao giờ được chọn. Request có thể được cho qua mà không qua JWT authentication mà developer kỳ vọng.

Ngược lại, **denyAll** catch-all đặt trước có thể chặn mọi API dù chain JWT được cấu hình đúng ở phía sau.

**Chain chuyên biệt đặt trước; fallback matcher rộng đặt cuối.**

## 5. permitAll không có nghĩa bỏ qua Spring Security

Một endpoint có rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
~~~

vẫn có thể đi qua các Spring Security filters của chain đã được chọn. Chính sách **permitAll** chỉ nói rằng bước authorization không yêu cầu principal đã xác thực cho request phù hợp.

| Khía cạnh | **permitAll()** | **Không khớp chain nào** |
|---|---|---|
| FilterChainProxy chọn chain | Có | Không |
| Authorization rule hiện diện | Có | Không |
| Security filters của chain có thể xử lý request | Có | Không |
| Các security headers/chính sách chain có thể áp dụng | Có | Không được bảo đảm |
| Endpoint được public có chủ đích | Có | Không thể suy ra |
| Thường phù hợp để làm public path | Có | Không |

**Một chi tiết quan trọng:** nếu endpoint **permitAll** vẫn nằm trong JWT chain và client gửi **Bearer token không hợp lệ**, bộ lọc authentication có thể xử lý token đó và trả lỗi trước khi rule permitAll cho phép. Vì vậy, endpoint public không token trả 200 nhưng gửi token sai trả 401 **không có nghĩa** securityMatcher đã sai.

### 5.1. web.ignoring là một cơ chế khác

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
~~~

**web.ignoring()** cấu hình Spring Security bỏ qua các request phù hợp matcher ở cấp web security. Với những tài nguyên tĩnh, một dự án có thể từng sử dụng cách này, nhưng với phần lớn public endpoints nên ưu tiên **permitAll trong SecurityFilterChain**, tránh mất những filter/chính sách security khác.

Một cấu hình như:

~~~java
web.ignoring().requestMatchers("/api/**");
~~~

có thể vô tình loại toàn bộ API khỏi cơ chế bảo vệ Spring Security. Không dùng ignoring để “sửa lỗi 401/403” cho endpoint nghiệp vụ.

## 6. Vì sao một chuỗi không bao phủ URL dù anyRequest được khai báo?

Xét:

~~~java
http
    .securityMatcher("/api/private/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
~~~

Những request khác nhau:

| URL | Thuộc chain này không? | anyRequest trong chain có được xét không? |
|---|---|---|
| **/api/private/orders** | Có nếu matcher khớp | Có |
| **/api/public/ping** | Không | Không |
| **/internal/reports** | Không | Không |
| **/health/live** | Không | Không |
| **/actuator/health** | Tùy path/port thực tế; không thuộc pattern trên | Không theo chain này |

Đây không phải lỗi trong Spring Security. Đó là kết quả đúng của cách đặt **securityMatcher**. Lỗi thiết kế là **không có chain khác** bảo vệ các đường đi còn lại hoặc không biết các đường đi ấy tồn tại.

Khi một nhóm phát triển mới thêm controller, Spring Boot có thể tự đăng ký endpoint theo route của controller, trong khi chain giới hạn từ trước vẫn không đổi. Vì vậy fallback có tác dụng giảm nguy cơ route mới trở thành public mặc định.

## 7. Độ bao phủ có hai lớp: chain và rule

Chỉ biết một request **có SecurityFilterChain** vẫn chưa đủ. Còn phải biết **quy tắc phân quyền nào áp dụng trong chain đó**.

Ví dụ:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest()
            .authenticated()
    );
~~~

Nếu controller có:

~~~text
GET    /api/orders/42    -> đọc đơn
PUT    /api/orders/42    -> sửa đơn
DELETE /api/orders/42    -> xóa đơn
~~~

thì:

- **GET** cần **SCOPE_orders.read**.
- **PUT** và **DELETE** đi vào **anyRequest().authenticated()** nếu không có rule khác.
- Một token hợp lệ **không có scope write/delete** có thể vượt qua yêu cầu authentication của rule mặc định.

Cả ba method đều thuộc API chain nhưng **authorization-policy coverage vẫn thiếu**.

| Lớp kiểm | Câu hỏi |
|---|---|
| **Filter-chain coverage** | Request có đi vào một chain Spring Security phù hợp không? |
| **Authorization-rule coverage** | Trong chain đó, rule cho đúng path/method có yêu cầu đủ quyền không? |
| **Domain/resource authorization** | Principal có được thao tác lên bản ghi, tenant hoặc trạng thái dữ liệu này không? |

Một bảo mật tốt cần cả ba.

## 8. Context path, servlet path và cơ chế match URL

Một URL công khai không nhất thiết là chuỗi mà **RequestMatcher** nhìn thấy bên trong ứng dụng.

Các yếu tố thường ảnh hưởng:

| Yếu tố | Ví dụ | Nguy cơ hiểu sai |
|---|---|---|
| **Context path** | /shop | URL ngoài có prefix khác đường dẫn servlet để match |
| **Servlet path** | /api | Ứng dụng có nhiều servlet mapping hoặc DispatcherServlet riêng |
| **Request URI/path info** | /orders/42 | Matcher đánh giá một phần đường dẫn theo quy tắc cụ thể |
| **Reverse proxy rewrite** | /v1/orders → /api/orders | SecurityMatcher backend nhìn route backend, không nhất thiết route public |
| **Trailing slash** | /api, /api/ | Có thể khác nhau tùy matcher/version |
| **Path encoding** | Encoded slash, nhiều dấu slash | Container, firewall và matcher có thể chuẩn hóa khác nhau |
| **HTTP method** | GET, POST, OPTIONS | Rule method-specific không áp dụng cho mọi method |

Spring Security có các loại **RequestMatcher** và cơ chế integration với Spring MVC/PathPattern. Hành vi cụ thể phụ thuộc phiên bản Spring Security, cấu hình servlet và cách matcher được tạo.

### 8.1. Đừng chỉ kiểm /api/orders/42 mà quên /api và /api/

Nếu cấu hình **securityMatcher("/api/**")**, cần kiểm trên ứng dụng thực tế:

~~~text
GET /api
GET /api/
GET /api/orders
GET /api/orders/42
POST /api/orders
OPTIONS /api/orders
~~~

Không nên tự khẳng định pattern **/api/** chắc chắn khớp hoặc không khớp **/api** ở mọi loại RequestMatcher và mọi phiên bản. Hãy xác nhận bằng request trong context thực tế.

### 8.2. Nhiều servlet có thể cần matcher khác nhau

Spring Boot MVC thông thường có một DispatcherServlet, nhưng ứng dụng có thể đăng ký servlet khác hoặc thiết lập servlet mapping không mặc định. Lúc đó, một request matcher được viết theo giả định servlet path **/** có thể không đúng.

Khi có nhiều servlet, cần:

- Xác định contextPath, servletPath, pathInfo thực tế.
- Chọn đúng cơ chế matching được phiên bản Spring Security hỗ trợ.
- Test route trên từng servlet/registration, không chỉ qua một MockMvc request thiếu servlet path.
- Không giả định chain của DispatcherServlet chính bao phủ mọi servlet được triển khai trong container.

## 9. Filter registration cũng là một ranh giới

Một **SecurityFilterChain** có matcher catch-all vẫn không bảo vệ request nếu **Servlet filter proxy không được đăng ký/chạy cho request đó**.

Trong Spring Boot Servlet thông thường, Spring Security được đăng ký tự động. Nhưng những hệ thống deploy thủ công, nhiều web context hoặc customize filter registrations cần xác minh:

- Bean **springSecurityFilterChain** có tồn tại và được đăng ký không?
- URL pattern của Servlet filter registration có phù hợp không?
- Dispatcher types nào được filter xử lý?
- Có servlet hoặc context khác mà request không chạy qua filter proxy không?
- Có profile/conditional bean làm SecurityFilterChain bị tắt ngoài ý muốn không?
- Một test có vô tình tắt các filters không?

**Không sửa một lỗi filter registration bằng cách chỉ thêm requestMatchers trong chain không bao giờ được gọi.**

### 9.1. DispatcherType: REQUEST, FORWARD, ERROR, ASYNC

Servlet sử dụng dispatcher types như:

- **REQUEST** cho request thông thường.
- **FORWARD** khi container chuyển tiếp nội bộ.
- **ERROR** cho error dispatch.
- **ASYNC** cho xử lý bất đồng bộ.
- **INCLUDE** cho thao tác include.

Filter registration và authorization có thể được áp dụng khác nhau tùy dispatcher type. Spring Boot có thuộc tính cấu hình dispatcher types cho security filter theo phiên bản, chẳng hạn **spring.security.filter.dispatcher-types**.

Cần xác minh:

1. Request loại **REQUEST** có được bảo vệ như kỳ vọng?
2. Một **FORWARD** nội bộ đến endpoint nhạy cảm có đổi đường xử lý filter/authorization không?
3. Một **ERROR** dispatch tới **/error** có bị fallback chặn làm thay đổi response gốc không?
4. Xử lý **ASYNC** có tạo dispatch mới cần security context và filter tương ứng không?

Không phải mọi FORWARD/ERROR là lỗ hổng. Nhiều ứng dụng cần permit một số dispatch có chủ đích để hiển thị lỗi đúng, nhưng phải kiểm soát ranh giới route và không mở controller nghiệp vụ do rule quá rộng.

### 9.2. /error có thể bị denyAll chặn

Giả sử request ban đầu gây lỗi 500, container dispatch đến **/error**. Nếu fallback denyAll chặn request lỗi, client có thể thấy 403 hoặc phản hồi khác khiến điều tra sự cố khó khăn.

Cách xử lý có thể gồm cấu hình dispatcher-specific rule hoặc route lỗi phù hợp, tùy phiên bản và kiến trúc. Tuy nhiên, **không vì muốn hiển thị lỗi mà bỏ qua toàn bộ security cho mọi đường dẫn**. Phải test riêng error dispatch và không tiết lộ dữ liệu nhạy cảm.

## 10. Reverse proxy và đường dẫn bên ngoài ứng dụng

Giả sử request:

~~~text
Client:
  https://api.example.com/v1/orders/42

Gateway:
  /v1/orders/42  ->  orders-service:8080/api/orders/42

Spring MVC backend:
  GET /api/orders/42
~~~

Nếu backend cấu hình **securityMatcher("/api/**")**, cần xác minh matcher thấy path thực tế nào sau proxy, context path và servlet mapping. Không thể dựa hoàn toàn vào URL mà browser hiển thị.

Các tình huống đáng kiểm:

- Proxy rewrite path trước khi request vào Servlet container.
- Một route ingress khác không rewrite giống route chính.
- Backend có thể được gọi trực tiếp bằng một port nội bộ.
- Header forwarded-prefix hoặc host do client tự khai được tin sai.
- Application có context path khác trong staging/production.
- Một alias route cho cùng controller được thêm sau khi cấu hình chain.

Sơ đồ phân tích:

~~~text
Public URL
    -> Ingress/Gateway route
    -> Rewrite/forwarded headers
    -> Container context path
    -> Servlet path + pathInfo
    -> SecurityFilterChain đầu tiên khớp
    -> Authorization rule
    -> Controller
~~~

Vì vậy, test bảo mật nên có **request qua URL public thực tế** trong môi trường kiểm thử triển khai, ngoài các test MockMvc tại backend.

## 11. Actuator và management port không được quên

Ứng dụng Spring Boot có thể dùng Actuator, ví dụ những endpoint như:

~~~text
/actuator/health
/actuator/info
/actuator/metrics
/actuator/env
/actuator/heapdump
~~~

Endpoint nào thực sự bật hoặc được expose phụ thuộc cấu hình Actuator. Một số endpoint chứa thông tin nhạy cảm và cần biện pháp bảo vệ nghiêm ngặt.

Có hai mô hình thường gặp:

**Actuator cùng port/context ứng dụng:** các đường đi management cần được bao phủ bởi security configuration trong context tương ứng. Đừng giả định **securityMatcher("/api/**")** bảo vệ **/actuator/**.

**Actuator trên management port/context riêng:** có thể có một web server/context và policy khác. Không thể dùng fallback chain của application port làm bằng chứng management port đã được bảo vệ.

Cần kiểm:

- Management port có tách riêng không?
- Actuator endpoints nào được expose?
- Endpoint health/liveness có public có chủ đích không?
- Metrics, env, heapdump hoặc logfile có giới hạn mạng và quyền đúng không?
- Có ingress management riêng không?
- Kịch bản không token, token sai và người dùng thiếu quyền có kết quả gì trên **cổng thực tế**?

## 12. OPTIONS và CORS preflight

Browser có thể gửi:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Một response **200/204** cho OPTIONS có thể là kết quả đúng cho CORS preflight. Nhưng nó **không chứng minh POST /api/orders đã được bảo vệ hoặc được cho phép**.

CORS kiểm quyền truy cập từ browser origin, không thay thế JWT signature verification, Bearer authentication hay authorization.

Các request cần kiểm riêng:

- **OPTIONS /api/orders** với header preflight thích hợp.
- **POST /api/orders** không token.
- **POST /api/orders** với JWT sai signature hoặc audience.
- **POST /api/orders** với token hợp lệ thiếu quyền write.
- **POST /api/orders** với token có quyền write và domain policy đạt.

Không bỏ qua OPTIONS trong bản đồ HTTP, nhưng cũng không dùng kết quả OPTIONS làm phép thử duy nhất cho endpoint.

## 13. Bảng kiểm độ bao phủ route và method

Để kiểm một ứng dụng thực tế, nên tạo ma trận:

| Endpoint | Port/context | Chain mong muốn | Rule mong muốn | Không token |
|---|---|---|---|---|
| **GET /api/public/ping** | API port | API chain | permitAll | Cho phép |
| **GET /api/orders/42** | API port | API chain | SCOPE_orders.read | Thường 401 |
| **POST /api/orders** | API port | API chain | SCOPE_orders.write | Thường 401 |
| **GET /api/admin/reports** | API port | API/admin chain | Role/scope admin | Thường 401 |
| **GET /internal/coverage-probe** | API port | Fallback | denyAll | Bị từ chối |
| **GET /health/live** | API port | Fallback | permitAll | Cho phép |
| **GET /actuator/health** | Management port thực tế | Management policy | Theo thiết kế | Theo thiết kế |
| **GET /actuator/env** | Management port thực tế | Management policy | Chặn truy cập ngoài ý muốn | Theo thiết kế |

Đây là **bảng yêu cầu**, không phải kết quả test. Với cấu hình ví dụ ở mục 4, **POST /api/orders** mới chỉ thuộc **anyRequest().authenticated()**, nên **chưa đáp ứng yêu cầu SCOPE_orders.write** trong bảng. Phải bổ sung rule có chủ đích.

Chính sự đối chiếu giữa **policy mong muốn** và **rule đã viết** giúp tìm lỗi không chỉ ở cấp chain mà còn trong các method/path cụ thể.

### 13.1. Không có handler cũng có thể trả 404

Nếu gọi **GET /secret/not-found** mà ứng dụng không có controller tương ứng, response 404 chỉ cho biết không tìm thấy route. Nó **không chứng minh Spring Security đã chặn truy cập**.

Muốn kiểm coverage, hãy dùng:

- Route có handler thật và có hành vi rõ nếu không bị chặn; hoặc
- Một controller/test probe được tạo riêng trong test context.

Như vậy, khi request bị từ chối, ta biết nguyên nhân đến từ security policy chứ không phải đơn giản do không có handler.

## 14. MockMvc phải chạy với Spring Security filters

Một lỗi kiểm thử là dùng MockMvc nhưng không đưa security filter chain vào request pipeline.

### 14.1. standaloneSetup không tự tương đương production

Ví dụ:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .standaloneSetup(new OrderController(...))
    .build();
~~~

Cách này phù hợp với controller tests nhưng **không tự động đồng nghĩa đã chạy springSecurityFilterChain thật**.

Tương tự:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

có thể tắt việc thêm Servlet filters vào MockMvc. Nếu dùng kiểu test này để xác định một URL có bị JwtDecoder bảo vệ hay không, kết luận có thể hoàn toàn sai.

### 14.2. Kiểm private endpoint với context gần production

Một hướng phù hợp trong Spring Boot Servlet:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityCoverageTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersEndpointRequiresToken() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Ví dụ giả định đã import JUnit và Spring Boot Test/MockMvc. Cần chạy với **SecurityFilterChain và controller mapping thực tế**. Với JWT Resource Server mặc định, endpoint private không Bearer token thường trả **401**.

Nếu route không có handler và trả 404, không thể dùng 404 làm bằng chứng security. Các test nên xác nhận handler tồn tại, cùng việc filters đã được gắn vào context.

### 14.3. Tạo test-only probe ngoài chain chuyên biệt

Để chứng minh fallback thực sự chặn đường dẫn ngoài **/api/**, có thể thêm controller **chỉ trong test**:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CoverageProbeController {

    @GetMapping("/internal/coverage-probe")
    ResponseEntity<Void> probe() {
        return ResponseEntity.noContent().build();
    }
}
~~~

Nếu không có security, handler này có thể trả **204 No Content**. Với fallback **denyAll**, request nên bị chặn trước khi đến handler:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Import(CoverageProbeController.class)
class CoverageProbeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void pathOutsideApiChainIsDenied() throws Exception {
        mockMvc.perform(get("/internal/coverage-probe"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là ví dụ test rút gọn; các imports, bean registration và response code cụ thể phụ thuộc app config. Nếu fallback dùng authentication entry point khác, có thể trả một mã **4xx** khác. Điều cốt lõi là **handler tồn tại** và request không được phép đi đến đó khi không có quyền.

Không vô tình deploy test-only probe như production endpoint.

### 14.4. Nếu dựng MockMvc thủ công từ WebApplicationContext

Spring Security Test cung cấp cấu hình **springSecurity()** cho MockMvc:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Nhớ dùng imports của Spring Security Test và kiểm filters thực sự được đăng ký. **@WebMvcTest** là slice test hữu ích nhưng có thể dùng tập bean khác full application context; không nên là bằng chứng duy nhất về độ bao phủ trong production.

## 15. Kiểm tra runtime chain được chọn

### 15.1. Bật log FilterChainProxy trong môi trường kiểm thử

Có thể tạm bật log:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Tùy phiên bản Spring Security, log có thể cung cấp thông tin request và filter chain đang xử lý. Không dựa độc nhất vào log: kết hợp với request tests và review danh sách SecurityFilterChain.

**Không ghi nguyên Bearer token, Authorization header, cookie, secret hoặc payload nhạy cảm vào log.** Logging chi tiết chỉ dùng ở môi trường thích hợp và trong thời gian cần thiết.

### 15.2. Xem danh sách SecurityFilterChain

Trong Servlet Spring Security, **FilterChainProxy** quản lý các chain và có API để lấy danh sách chúng trong ngữ cảnh phù hợp. Một test cấu hình có thể inspect:

- Số lượng chain.
- Matcher và thứ tự mỗi chain.
- Chain nào có BearerTokenAuthenticationFilter.
- Có fallback matcher rộng cuối cùng không.
- Những path nào được intentionally ignored.
- Chain nào khớp **đầu tiên** với từng request.

**Đừng chỉ kiểm “có ít nhất một chain khớp”** nếu chain đầu tiên là **permitAll** quá rộng. Ví dụ:

~~~text
Chain 1 (first):  /**             -> permitAll
Chain 2:          /api/admin/**   -> hasRole("ADMIN")
~~~

Request **/api/admin/reports** sẽ bị chain 1 “nuốt” trước, nên sự tồn tại của chain 2 không có tác dụng bảo vệ request.

### 15.3. Request thật quan trọng hơn việc so chuỗi pattern

Một test tự tạo MockHttpServletRequest thiếu contextPath/servletPath phù hợp có thể cho kết quả matcher khác request thực. Vì vậy, introspection chain là công cụ hỗ trợ phân tích, còn **integration request qua ứng dụng thật** là cơ sở quan trọng để chứng minh độ bao phủ.

## 16. Kiểm qua HTTP thật, gateway và management port

MockMvc không đi qua toàn bộ gateway, reverse proxy, TLS, ingress và cấu hình container thực tế. Với hệ thống có nhiều tầng, nên kiểm cả:

1. **Public URL** mà client thật sử dụng.
2. **Backend direct URL/port** nếu có thể kết nối theo kiến trúc.
3. **Management port** nếu tách biệt.
4. Đường dẫn có prefix/rewrite khác nhau.
5. HTTP methods **GET, POST, PUT, DELETE, OPTIONS** cần thiết.
6. Token thiếu, giả chữ ký, sai issuer/audience, hết hạn.
7. Token hợp lệ nhưng thiếu scope hoặc quyền tenant.
8. FORWARD/ERROR/ASYNC dispatch ở những luồng có sử dụng.

Ví dụ request kiểm riêng tư:

~~~bash
curl -i https://api.example.com/api/orders/42
~~~

Với JWT Resource Server thông thường, private endpoint không token thường trả **401 Unauthorized** và có thể có **WWW-Authenticate: Bearer**.

Kiểm endpoint ngoài **/api/**:

~~~bash
curl -i https://api.example.com/internal/coverage-probe
~~~

Nếu handler test tồn tại và fallback denyAll có hiệu lực, request phải bị từ chối. **Không suy luận từ 404 của URL chưa được map**.

Khi cần test token có quyền, sử dụng token phát hành cho môi trường test, thời hạn ngắn, issuer/JWKS test đáng tin và cơ chế giữ bí mật. Không đưa token production vào log hay ticket.

## 17. Ba kiểu thiếu bảo vệ thường bị nhầm là một

| Nhóm lỗi | Ví dụ | Cách khắc phục |
|---|---|---|
| **Không có SecurityFilterChain phù hợp** | Chỉ securityMatcher("/api/**") nhưng có controller /internal/export | Thêm/điều chỉnh chain hoặc fallback |
| **Có chain nhưng rule quá rộng** | PUT/DELETE chỉ cần authenticated() thay vì scope write/delete | Sửa requestMatchers và domain authorization |
| **Có rule nhưng Authentication không đáng tin** | Custom filter tự lấy role từ JWT JSON chưa verify | Dùng JwtDecoder/introspection tin cậy, sửa trust boundary |
| **Có bean chain nhưng request không đi qua FilterChainProxy** | Filter registration/dispatcher/context khác hoặc test tắt filters | Sửa filter wiring, deployment/test setup |

Phân biệt đúng nhóm giúp tránh việc chỉ thêm các matcher mà không sửa căn nguyên.

### 17.1. Những anti-pattern cần tìm khi review

- **securityMatcher** giới hạn hẹp nhưng không có fallback.
- **anyRequest().permitAll()** xuất hiện trong chain đầu có matcher rộng.
- **web.ignoring("/api/**")** hoặc bỏ qua cả nhóm endpoint nghiệp vụ.
- Rule **authenticated()** cho method vốn cần scope/role cụ thể.
- Một SecurityFilterChain có thứ tự cao che khuất chain chuyên biệt phía sau.
- MockMvc dùng **standaloneSetup** hoặc **addFilters=false** làm test security.
- Test assert 404 trên route không tồn tại và coi đó là bằng chứng bảo mật.
- Reverse proxy rewrite URL khác phạm vi matcher backend.
- Management endpoints trên port khác mà không có review security.
- Custom servlet/filter registration không bao phủ mọi dispatcher/path cần thiết.
- Bật một profile production làm mất SecurityFilterChain hoặc mở permitAll ngoài ý muốn.

## 18. Quy trình kiểm tra độ bao phủ có thể áp dụng

### Bước 1 — Lập danh sách route thực tế

Thu thập tất cả HTTP endpoints từ controller mapping, tài liệu API, actuator mappings nếu phù hợp, servlet registrations, gateway routes và cổng management. Ghi rõ **HTTP method, public path, backend path, port và context**.

Không chỉ lấy những endpoint bắt đầu bằng **/api/**.

### Bước 2 — Liệt kê chain và thứ tự

Ví dụ:

~~~text
@Order(1): /api/admin/**     -> admin JWT policy
@Order(2): /api/**           -> general JWT API policy
@Order(3): any request       -> fallback deny/public exceptions
~~~

Cần xác định chain nào có matcher rộng, chain nào yêu cầu Bearer token và chain nào là fallback.

### Bước 3 — Đối chiếu mỗi route với chain đầu tiên khớp

Với từng request:

~~~text
HTTP method + actual servlet path
  -> SecurityFilterChain đầu tiên match
  -> authorizeHttpRequests rule được chọn
  -> yêu cầu authentication/scope/role
  -> domain resource policy
~~~

Nếu không chain nào khớp, phải xác định đó là chủ đích hay lỗ hổng. Nếu chain khớp nhưng rule không đủ quyền, vẫn phải sửa.

### Bước 4 — Thiết kế fail-closed

Nếu quy trình triển khai yêu cầu endpoint mới phải được review bảo mật trước, fallback **denyAll** hoặc policy fail-closed tương đương là lựa chọn phù hợp. Định nghĩa các exception public rõ ràng, không dùng permitAll toàn cục cho tiện.

### Bước 5 — Test trường hợp không token

Với endpoint private **có handler thật**, request không token phải bị từ chối xác thực theo chính sách, thường là **401** đối với Bearer Resource Server. Với fallback denyAll, test endpoint có thật ngoài API chain để tránh bẫy 404.

### Bước 6 — Test token hợp lệ và không hợp lệ

Kiểm token sai chữ ký, issuer/audience, hết hạn; token hợp lệ thiếu scope; token đủ scope nhưng không thuộc tenant; token đủ quyền hợp lệ. Các lớp authentication, request authorization và domain policy phải được test độc lập.

### Bước 7 — Test đường đi deployment

Kiểm proxy rewrite, Servlet context, management port, HTTP methods/path variants và dispatcher type có liên quan. Phát hiện sự khác nhau giữa local MockMvc và request thật trước khi production.

### Bước 8 — Gắn review coverage vào quá trình thêm endpoint

Khi thêm controller hoặc dependency tự đăng ký endpoint:

- Ghi route vào bảng coverage.
- Xác định chain và policy được chọn.
- Thêm negative tests.
- Review thay đổi của **@Order**, **securityMatcher**, **web.ignoring** và fallback.
- Chỉ deploy khi endpoint nhạy cảm có cơ chế bảo vệ rõ ràng.

## 19. Bài tập tự kiểm tra

**Câu 1.** Một chain có **securityMatcher("/api/**")** và **anyRequest().authenticated()**. Controller **/admin/export** có được rule anyRequest đó bảo vệ không?

**Không.** /admin/export không thuộc phạm vi chain; cần chain khác hoặc fallback.

**Câu 2.** Một chain dùng **permitAll("/api/public/**")** có nghĩa request không qua security filters không?

**Không.** permitAll là authorization decision trong chain; những security filters có thể vẫn xử lý request.

**Câu 3.** Hai chain cùng khớp **/api/admin/reports** thì các rule có được cộng dồn không?

**Không.** Chain khớp đầu tiên theo thứ tự được chọn.

**Câu 4.** Request **GET /secret/unknown** trả 404 có chứng minh endpoint /secret/** đã được bảo vệ không?

**Không.** Có thể chỉ vì không có handler. Cần test route có thật hoặc test-only probe.

**Câu 5.** Có fallback denyAll trên application port thì Actuator management port riêng chắc chắn đã được bảo vệ chưa?

**Không thể kết luận.** Phải kiểm context và policy của management port thực tế.

**Câu 6.** Có SecurityFilterChain khớp request thì endpoint đã an toàn chưa?

**Chưa chắc.** Rule trong chain có thể quá rộng, không yêu cầu đúng scope hoặc bỏ qua quyền tenant/ownership.

**Câu 7.** Vì sao MockMvc có thể cho kết luận sai?

Vì có thể dựng MockMvc không gắn Spring Security filters hoặc chỉ tải một test slice khác production.

## Kết luận

Độ bao phủ của Spring Security phải được đánh giá ở **hai cấp**: request có thuộc một **SecurityFilterChain phù hợp** hay không, và rule bên trong chain có yêu cầu **đúng quyền** cho path/method đó hay không. **FilterChainProxy chọn chain đầu tiên khớp**, và **anyRequest** bên trong một chain bị giới hạn **securityMatcher** không tự mở rộng ra toàn ứng dụng.

Để tránh endpoint bị bỏ lọt, nên cấu hình chain theo thứ tự rõ ràng, dùng một **fallback có chính sách phù hợp**, ưu tiên **permitAll trong chain** thay vì bỏ qua security và kiểm request tới **handler thật** với security filters đã được bật.

Khi đánh giá độ bao phủ thực tế, đừng quên **HTTP method, path/context/servlet mapping, proxy rewrite, dispatcher types, Actuator/management port và profiles triển khai**. Một phản hồi 404, một test MockMvc không chạy filter hoặc một dòng anyRequest trong code đều không đủ để kết luận API đã an toàn.

### Tài liệu tham khảo

- [Spring Security — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security API — FilterChainProxy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security API — SecurityFilterChain](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html)
- [Spring Security — Testing Spring MVC](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Boot — Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Actuator Endpoint Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.security)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
