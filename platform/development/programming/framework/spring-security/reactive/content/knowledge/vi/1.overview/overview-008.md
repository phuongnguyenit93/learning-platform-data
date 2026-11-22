# Kiến thức đầu vào và trình tự học: từ yêu cầu HTTP đến bảo mật nghiệp vụ trong Spring Security Reactive

> **Phạm vi:** Bài này xây dựng bản đồ kiến thức và thứ tự thực hành cho ứng dụng **Spring WebFlux + Spring Security Reactive**. Mục tiêu là hiểu một yêu cầu HTTP được nhận diện, xác thực và cấp quyền như thế nào, sau đó tiếp tục kiểm tra quyền đối với **hành động và dữ liệu nghiệp vụ**. Các ví dụ dùng Java và cơ chế JWT Bearer cho API; chúng là một nhánh thực hành cụ thể, không phải cơ chế đăng nhập duy nhất của Spring Security.

## 1. Đích đến của lộ trình

Sau bài này, người học cần trả lời được bốn câu hỏi theo đúng thứ tự:

1. **Yêu cầu gì đang đến?** Phương thức HTTP, đường dẫn, header, cookie/body, giao thức HTTPS và dữ liệu nào không đáng tin cậy.
2. **Ai đang gọi?** Ứng dụng có kiểm chứng được danh tính/thông tin xác thực của người gọi không? Cơ chế đó tạo ra đối tượng Authentication như thế nào?
3. **Người đó có thể gọi chức năng nào?** Quy tắc ở đường dẫn và ở method/service cho phép thao tác nào theo role, authority hoặc scope?
4. **Người đó có được tác động đến đối tượng cụ thể này không?** Ví dụ cùng có quyền xem đơn hàng nhưng chỉ được xem đơn của mình hoặc của tenant được phân quyền.

**Xác thực (authentication)** trả lời “ai đang gọi?”. **Phân quyền (authorization)** trả lời “được làm gì với tài nguyên nào?”. **Bảo mật nghiệp vụ** còn xét trạng thái, chủ sở hữu, tenant, quan hệ thành viên và điều kiện riêng của nghiệp vụ. Có JWT hợp lệ hoặc vai trò USER chưa đủ để được phép truy cập mọi bản ghi.

Một kết quả học tập đạt yêu cầu phải thể hiện bằng hành vi quan sát được: yêu cầu thiếu danh tính bị chặn; yêu cầu có danh tính nhưng thiếu quyền bị từ chối; yêu cầu đủ quyền chức năng nhưng sai chủ sở hữu/tenant không lấy được dữ liệu; yêu cầu hợp lệ mới hoàn thành.

## 2. Kiến thức đầu vào cần có

### 2.1. Java, Spring và giao thức HTTP

- **Java 17+**: class/interface/record, generic, exception, lambda, dependency injection và cách chạy test JUnit.
- **Spring Boot**: component, bean, configuration, Controller/Service/Repository, cấu hình theo môi trường và dependency.
- **HTTP**: method GET/POST/PUT/PATCH/DELETE, URL/path/query, headers (đặc biệt Authorization), cookie, body, status, HTTPS/TLS. Không đồng nhất trạng thái HTTP với phiên đăng nhập: giao thức HTTP không tự lưu phiên, nhưng ứng dụng có thể dùng session/cookie.
- **Mã trạng thái thường gặp**: 200/201 khi thành công; 400 khi yêu cầu sai; **401** khi cần xác thực hoặc thông tin xác thực không hợp lệ; **403** khi đã xác thực nhưng không được phép; **404** khi không tồn tại hoặc API chủ ý không tiết lộ sự tồn tại của tài nguyên. Quy tắc xử lý thực tế còn phụ thuộc entry point, exception handler và chính sách sản phẩm.

**Bài kiểm tra đầu vào:** dùng một HTTP client gửi GET /api/orders/42, chỉ ra method, path, header Authorization và phân biệt rõ việc máy chủ có biết “ai gọi” với việc có cho xem đơn 42 hay không.

### 2.2. Reactive WebFlux và Project Reactor

- **Mono<T>** biểu diễn luồng bất đồng bộ có tối đa một giá trị; **Flux<T>** có thể có nhiều giá trị. Phần lớn công việc trong chuỗi reactive diễn ra khi có subscription, không phải chỉ vì đã tạo Mono/Flux.
- **map** biến đổi giá trị đồng bộ; **flatMap** kết hợp một thao tác bất đồng bộ trả Publisher; **filter** loại giá trị không thỏa điều kiện; **switchIfEmpty** xử lý kết quả trống; **onErrorResume** xử lý lỗi theo chính sách phù hợp.
- **Không chặn luồng sự kiện** bằng block(), Thread.sleep(), JDBC đồng bộ hoặc gọi HTTP đồng bộ trên event-loop. Nếu có thư viện blocking chưa thể thay thế, cần ranh giới thực thi riêng và kế hoạch chuyển đổi rõ ràng.
- **Reactor Context** gắn dữ liệu với subscription và truyền qua chuỗi reactive; khác ThreadLocal vì xử lý có thể chuyển luồng. Trong Spring Security Reactive, thông tin SecurityContext được truy cập qua ReactiveSecurityContextHolder trong pipeline.
- **WebFlux** dùng WebFilter, ServerWebExchange và SecurityWebFilterChain; không bê nguyên OncePerRequestFilter, HttpSecurity hay SecurityFilterChain dành cho Servlet/MVC sang cấu hình Reactive.

**Bài kiểm tra đầu vào:** giải thích vì sao lấy user từ ThreadLocal ở một đoạn xử lý reactive có thể sai và vì sao gọi block() trong controller WebFlux là rủi ro.

### 2.3. Khái niệm security nền tảng

- **Principal**: danh tính đã xác thực; **credentials**: dữ liệu dùng để chứng minh danh tính; **authorities**: quyền được gắn cho Authentication. Role thường được biểu diễn bằng authority có tiền tố ROLE_; scope của JWT Resource Server thường được ánh xạ thành SCOPE_… theo cấu hình mặc định.
- **Session/cookie và Bearer token** là hai cách mang trạng thái xác thực khác nhau. Đối với Bearer JWT, máy chủ cần kiểm chứng chữ ký, thời hạn, issuer và các ràng buộc cần thiết như audience; không coi việc chỉ giải mã payload là xác thực.
- **OAuth 2.0** chủ yếu giải quyết ủy quyền truy cập; **OpenID Connect** bổ sung lớp nhận diện người dùng. API đóng vai Resource Server thường nhận và kiểm chứng access token, không tự phát token chỉ vì đã khai báo Resource Server.
- **Least privilege, deny by default, defense in depth**: chỉ mở những quyền cần thiết; điểm vào HTTP và tầng nghiệp vụ cùng phải bảo vệ vùng trách nhiệm của mình.
- **CSRF** và **CORS** khác nhau: CORS quản lý truy cập liên nguồn do trình duyệt thực thi; CSRF liên quan việc trình duyệt tự động gửi thông tin đăng nhập (điển hình là cookie). Không tắt CSRF chỉ vì “API dùng JSON” nếu ứng dụng còn xác thực dựa trên cookie.

## 3. Bản đồ một yêu cầu bảo mật

Ví dụ xét GET /api/orders/42 với API dùng Bearer token:

~~~mermaid
flowchart TD
    A["Client gửi HTTP request"] --> B["WebFlux + SecurityWebFilterChain"]
    B --> C{"Thông tin xác thực hợp lệ?"}
    C -->|"Không"| D["401 / authentication entry point"]
    C -->|"Có"| E{"Quyền truy cập route?"}
    E -->|"Không"| F["403 / access denied"]
    E -->|"Có"| G["Controller / Handler"]
    G --> H{"Quyền gọi service / hành động?"}
    H -->|"Không"| F
    H -->|"Có"| I{"Được truy cập đơn 42 trong tenant này?"}
    I -->|"Không"| J["403 hoặc 404 theo chính sách"]
    I -->|"Có"| K["Reactive Repository"]
    K --> L["Trả dữ liệu được phép"]
~~~

Sơ đồ mô tả **một đường đi điển hình của endpoint cần đăng nhập**. Route công khai có thể bỏ qua yêu cầu danh tính; các lỗi do dữ liệu hoặc hệ thống không nhất thiết là lỗi authorization. JWT được kiểm tra ở ranh giới security, kết quả được chuyển thành Authentication; controller không tự kiểm tra chuỗi chữ ký trong mỗi method.

| Tầng | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| HTTP/transport | Request có đi qua HTTPS và tuân thủ hợp đồng API? | Method, path, header, body, TLS |
| Authentication | Token/session có hợp lệ và thuộc ai? | JWT được xác thực, principal là subject |
| Request authorization | Endpoint này cần authority nào? | GET /api/orders/** cần SCOPE_orders:read |
| Method/action authorization | Caller có thể thực hiện nghiệp vụ này? | Service đọc đơn chỉ chấp nhận orders:read |
| Object/tenant authorization | Caller có quyền trên đơn cụ thể? | ownerId hoặc tenantId phù hợp |
| Data/output boundary | Kết quả chỉ chứa dữ liệu được phép? | Query đã lọc tenant; DTO tránh lộ trường nhạy cảm |

**Nguyên tắc nối tầng:** Quyền gọi đường dẫn không tự cấp quyền trên mọi bản ghi. Một ID do client cung cấp không thể được tin là “thuộc về người gọi”.

## 4. Trình tự học khuyến nghị và điều kiện qua từng chặng

Đi theo thứ tự dưới đây để mỗi chặng có một kết quả kiểm chứng trước khi mở rộng:

| Chặng | Học gì và vì sao | Thực hành tối thiểu | Dấu hiệu đã hiểu |
| --- | --- | --- | --- |
| **0 — HTTP** | Request/response, HTTPS, cookie, header, 401/403/404 | Gửi cùng một URL với/không có Authorization | Phân loại chính xác từng trường hợp |
| **1 — Reactive** | Mono/Flux, subscription, lỗi, Reactor Context | Viết pipeline lấy dữ liệu không dùng block() | Mô tả được khi nào dữ liệu chạy và lỗi đi đâu |
| **2 — WebFlux routing** | Controller/functional route, WebFilter, ServerWebExchange | Tạo GET /health và GET /api/orders/{id} | Phân biệt routing với security |
| **3 — Security chain** | SecurityWebFilterChain, ServerHttpSecurity, thứ tự matcher | Mở /health, chặn mặc định phần còn lại | Route lạ không vô tình thành công khai |
| **4 — Authentication** | Authentication, SecurityContext, Resource Server, JWT | Cấu hình issuer thật trong môi trường test | Token thiếu/sai/hết hạn bị từ chối |
| **5 — Quyền theo route** | authenticated, permitAll, hasAuthority, denyAll | Yêu cầu SCOPE_orders:read cho GET đơn hàng | Token đúng nhưng thiếu scope bị chặn |
| **6 — Quyền theo method** | @EnableReactiveMethodSecurity, @PreAuthorize | Chặn service đọc đơn khi thiếu scope | Gọi service qua Spring bean vẫn có policy |
| **7 — Quyền đối tượng** | owner, tenant, trạng thái đơn, truy vấn lọc | Ngăn Alice đọc đơn của Bob | Cùng scope nhưng khác chủ không lộ dữ liệu |
| **8 — Kiểm thử và vận hành** | WebTestClient, mockJwt, mã lỗi, log/audit an toàn | Test ma trận danh tính × quyền × dữ liệu | Có bằng chứng cho các nhánh allow/deny |

**Cách học cho hiệu quả:** sau mỗi chặng, chỉ chuyển tiếp khi có thể viết một ví dụ dương tính và một ví dụ âm tính. Nếu kết quả 401/403/404 chưa giải thích được, quay về chặng tương ứng thay vì sửa ngẫu nhiên matcher hoặc bỏ kiểm tra.

## 5. Cấu hình minh họa: cửa kiểm soát HTTP

Đoạn Java sau đặt trong một ứng dụng Spring Boot dùng WebFlux, Spring Security và hỗ trợ OAuth2 Resource Server/JWT. Đây là **một lớp cấu hình trong dự án**, không phải chương trình Java chạy độc lập. Cần cung cấp issuer/decoder thật và các bean nghiệp vụ để toàn bộ ứng dụng chạy.

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

**Giải thích theo thứ tự xử lý:**

1. **@EnableWebFluxSecurity** kích hoạt mô hình security cho WebFlux; **SecurityWebFilterChain** mô tả chính sách HTTP.
2. **/health** được mở riêng. **GET /api/orders/** chỉ cho principal có authority phù hợp; các API còn lại yêu cầu xác thực; những đường dẫn khác bị từ chối mặc định.
3. **oauth2ResourceServer(...jwt(...))** cho phép xử lý Bearer JWT với bộ giải mã/xác thực được cấu hình. Khi sử dụng Spring Boot, có thể khai báo ví dụ cấu trúc cấu hình sau:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
~~~

Địa chỉ trên chỉ **minh họa cú pháp**, phải thay bằng issuer thực tế và bảo đảm tài liệu khám phá/khóa ký tồn tại. Tùy hợp đồng API, cần cấu hình thêm kiểm tra **audience**, ánh xạ claim quyền và xử lý token không hợp lệ; mặc định xác thực JWT không đồng nghĩa token được cấp cho đúng API này.

4. **@EnableReactiveMethodSecurity** chuẩn bị kiểm soát quyền ở các method reactive được Spring quản lý. Chính sách URL không tự bảo vệ khi một nghiệp vụ được gọi từ điểm vào khác.
5. **csrf(...disable)** chỉ phù hợp với ví dụ API thực sự stateless, nhận Bearer token do client chủ động gửi và không dựa vào cookie để xác thực. Với đăng nhập trình duyệt dựa trên cookie/session, hãy đánh giá CSRF và giữ bảo vệ phù hợp. CORS cần chính sách riêng theo origin/method/header được phép.

**Thứ tự matcher có ý nghĩa:** quy tắc cụ thể phải đứng trước quy tắc bao quát. Khi có nhiều SecurityWebFilterChain, cần xét cả securityMatcher và thứ tự chain; tránh để một chain chung vô tình bắt mọi request trước chain chuyên biệt.

## 6. Đi sâu từ quyền chức năng tới quyền nghiệp vụ

Giả sử hệ thống có hai người dùng Alice và Bob. Cả hai đều sở hữu authority SCOPE_orders:read, nhưng đơn 42 thuộc Bob. Nếu chỉ có quy tắc GET /api/orders/** cần scope, Alice có thể thử GET /api/orders/42 và khai thác lỗ hổng **IDOR/BOLA** (truy cập đối tượng dựa trên ID mà không kiểm tra quyền đối tượng).

Tầng nghiệp vụ phải kiểm tra **chính đối tượng đang được đọc hoặc thay đổi**. Ví dụ Java dưới đây mô tả hợp đồng Order/OrderRepository và logic Service. Nó là trích đoạn cần được tích hợp vào ứng dụng có triển khai OrderRepository; không phải một ứng dụng Spring Boot độc lập.

~~~java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

record Order(String id, String ownerId, String description) {}

interface OrderRepository {
    Mono<Order> findById(String id);
}

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public Mono<Order> findVisibleOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(currentUserId ->
                orders.findById(orderId)
                    .filter(order -> order.ownerId().equals(currentUserId))
                    .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)
                    ))
            );
    }
}
~~~

- **@PreAuthorize** kiểm tra scope ở cửa vào service; **filter** kiểm tra owner của từng bản ghi. Thiếu bản ghi hoặc owner không khớp đều cho 404 theo chính sách tránh lộ sự tồn tại của đơn. Một ứng dụng có thể chọn 403 cho trường hợp sai quyền nếu chính sách công khai sự tồn tại cho phép; phải nhất quán và có test.
- Trong ví dụ, **Authentication.getName() được giả định là ID nội bộ trùng với ownerId**. Với JWT thật, getName() thường xuất phát từ claim subject và có thể **khác** ID nội bộ. Hãy ánh xạ từ danh tính đã xác thực sang ID nghiệp vụ bằng quy tắc tin cậy, không so sánh tùy tiện username/email với tenantId.
- **Chặn ở service vẫn phải bảo vệ các caller khác**, không chỉ HTTP. Method security dùng Spring AOP: lời gọi nội bộ trong cùng object (self-invocation) có thể không đi qua proxy bảo vệ. Nếu nghiệp vụ đi từ message consumer hoặc batch job, xác định danh tính/chính sách của tác vụ rõ ràng.
- Với dữ liệu nhiều tenant, chỉ so ownerId là chưa đủ. Nên truyền tenant đã xác thực tới query (ví dụ findByIdAndTenantId), kiểm tra quyền thành viên/role theo tenant và áp dụng kiểm soát tại lúc cập nhật. Các thay đổi trạng thái, chuyển tiền hoặc hành động nhạy cảm có thể cần kiểm tra điều kiện **sau khi tải dữ liệu và tại thời điểm ghi** để tránh lỗi tranh chấp/race.
- **Không cấp quyền dựa trên ownerId hoặc role trong JSON body do client gửi.** Những thuộc tính đó phải được xác minh từ token đã kiểm chứng và dữ liệu phía máy chủ.

## 7. Ma trận kết quả cần quan sát

Xét GET /api/orders/42 khi route yêu cầu SCOPE_orders:read:

| Tình huống | Kiểm tra nào quyết định? | Kết quả kỳ vọng |
| --- | --- | --- |
| Không có Bearer token | Authentication tại HTTP | **401** |
| Token sai chữ ký/hết hạn/issuer không hợp lệ | JWT validation | **401** |
| Token hợp lệ nhưng không có SCOPE_orders:read | Request authorization hoặc @PreAuthorize | **403** |
| Token hợp lệ, có scope, chủ đơn là người khác | Business/object authorization | **404** theo policy ví dụ |
| Token hợp lệ, có scope, đúng chủ đơn | Toàn bộ các tầng | **200** và chỉ dữ liệu được phép |
| Token hợp lệ nhưng tenant khác dù ID bản ghi đúng | Tenant/data authorization | **403/404** theo policy, không lộ dữ liệu |
| Đường dẫn ngoài API được công khai | Route mặc định | Bị từ chối theo cấu hình; không tự động public |

**Lưu ý về 401 và 403:** 401 báo cần xác thực, 403 báo đã biết danh tính nhưng không đủ quyền; chi tiết response headers và body phụ thuộc cấu hình Spring Security/exception handling. Không tự khẳng định mọi lỗi authentication đều luôn ra cùng một định dạng JSON. Đối với chính sách che giấu tài nguyên bằng 404, test phải khẳng định không tiết lộ owner/tenant/tên đối tượng trong body hoặc log gửi cho client.

## 8. Kiểm thử theo từng tầng, không chỉ kiểm thử đường đi thành công

### 8.1. Quy trình kiểm thử

1. **Web layer:** dùng WebTestClient cho request thiếu token, token không có quyền và token có quyền; thư viện spring-security-test cung cấp mockJwt() để tạo principal trong test, không phải để kiểm chứng chữ ký JWT thật.
2. **Service layer:** kiểm thử @PreAuthorize qua **Spring bean được proxied** và trường hợp owner đúng/sai. Một unit test gọi trực tiếp đối tượng mới khởi tạo bằng new không tự kiểm thử cơ chế AOP.
3. **Repository/data layer:** bảo đảm query đã lọc owner/tenant chính xác; với cập nhật cần xác minh affected rows và điều kiện thay đổi trạng thái.
4. **Tích hợp xác thực thật:** kiểm thử decoder/issuer/audience/expiry và ánh xạ claim với token test phù hợp. mockJwt() không thay thế lớp kiểm thử này.
5. **Negative tests:** thử ID của người khác, tenant khác, thiếu scope, scope sai, user bị vô hiệu hóa hoặc bị rút quyền, request không đúng method, đường dẫn không khai báo; kiểm thử kết quả và dữ liệu trả về.

Ví dụ cấu trúc kiểm thử WebTestClient khi client đã được cấu hình với hỗ trợ Spring Security test:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Minh họa bên trong một method @Test;
// client là WebTestClient đã được cấu hình, bản ghi 42 phải được seed phù hợp.
client
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ trên **chỉ kiểm tra được nhánh thành công** khi môi trường test có đơn 42 thuộc principal được tạo bởi mockJwt(); cần chủ động đặt subject và dữ liệu owner tương ứng. Thêm test tương tự cho missing scope và mismatched owner; không suy luận rằng một request 200 đủ chứng minh hệ thống an toàn.

### 8.2. Truy vết và xử lý sự cố

Khi nhận kết quả bất ngờ, lần lượt kiểm tra **request → chain được chọn → authentication → authorities đã ánh xạ → route matcher → method security → owner/tenant query → exception handler**. Có thể bật logging phù hợp trong môi trường test, nhưng không in access token, mật khẩu, session ID, dữ liệu nhạy cảm hay toàn bộ claims ra log. Audit nên ghi hành động, mã tài nguyên phù hợp, principal đã chuẩn hóa, quyết định allow/deny và correlation ID theo chính sách bảo vệ dữ liệu.

## 9. Những nhầm lẫn hay gặp khi chuyển từ HTTP sang nghiệp vụ

1. **“JWT giải mã được thì đã đăng nhập.”** Giải mã Base64 không xác thực chữ ký, thời hạn, issuer hoặc audience. Cần dùng decoder/validator đúng và bảo vệ đường truyền.
2. **“Có ROLE_ADMIN hoặc scope đọc là xem được mọi dữ liệu.”** Role/scope thường cấp quyền chức năng; owner/tenant/trạng thái nghiệp vụ vẫn phải kiểm soát riêng, trừ khi có chính sách toàn cục được phê duyệt.
3. **“Chặn đường dẫn là đủ.”** Nghiệp vụ có thể được gọi qua luồng khác; route security không thay thế method và data authorization.
4. **“Ứng dụng reactive lấy SecurityContextHolder như MVC.”** Authentication reactive đi theo Reactor Context; ThreadLocal và việc chuyển thread có thể làm mất/méo ngữ cảnh.
5. **“Thêm block() để lấy current user cho nhanh.”** block() phá mô hình non-blocking ở event-loop và có thể gây nghẽn hoặc deadlock; giữ luồng Mono/Flux và ghép bằng flatMap.
6. **“@PreAuthorize luôn chạy với mọi lời gọi.”** Spring method security cần bean/proxy hợp lệ; self-invocation và các object tự new có thể bỏ qua interception.
7. **“CORS thay cho CSRF” hoặc “stateless nghĩa là luôn tắt CSRF”.** Hai cơ chế có mục đích khác nhau; quyết định CSRF phụ thuộc cách browser mang credential.
8. **“Request body có tenantId đúng nên được tin.”** Chọn tenant theo nguồn tin cậy, kiểm tra membership và giới hạn query/ghi theo tenant phía server.
9. **“Trả 404 đã ngăn rò rỉ.”** Nếu query đọc dữ liệu trái phép trước khi quyết định, cache, log, side effect hoặc thông báo lỗi vẫn có thể lộ thông tin; kiểm tra quyền trước khi xuất dữ liệu/tạo tác dụng phụ.
10. **“Test mockJwt() đã chứng minh cấu hình JWT production hợp lệ.”** mockJwt kiểm tra logic authorization; decoder, chữ ký và issuer cần test tích hợp riêng.

## 10. Bài thực hành tích lũy và tiêu chí hoàn thành

**Bối cảnh:** tạo API đọc và hủy đơn hàng cho hai người dùng Alice/Bob thuộc các tenant khác nhau. Định nghĩa sẵn rule chức năng: đọc đơn cần SCOPE_orders:read; hủy đơn cần SCOPE_orders:cancel; chỉ chủ đơn hoặc vai trò quản lý tenant được hủy, và chỉ khi đơn còn ở trạng thái được phép hủy.

**Thứ tự làm:**

1. Xây một endpoint /health public và một endpoint /api/orders/{id} trong WebFlux; xác minh request/response không có security.
2. Thêm SecurityWebFilterChain với deny-by-default; yêu cầu authentication cho API; giải thích 401 ở request không có token.
3. Cấu hình JWT Resource Server bằng issuer test thực; viết test token hợp lệ/không hợp lệ và kiểm tra ánh xạ SCOPE_orders:read.
4. Áp đặt quyền GET theo route rồi đưa policy đọc vào service bằng @PreAuthorize; giải thích vì sao cần cả hai tầng.
5. Giới hạn truy vấn theo owner/tenant đáng tin cậy, xây kịch bản Alice thử ID đơn Bob; dự kiến 404 hoặc 403 theo chính sách đã chọn.
6. Thêm thao tác hủy đơn: kiểm tra scope, quan hệ owner/manager, tenant và trạng thái trước khi cập nhật; thiết kế thao tác ghi bảo đảm điều kiện trạng thái còn đúng khi lưu.
7. Viết ma trận test tích cực/tiêu cực cho mọi ranh giới. Chứng minh người dùng không đọc/hủy được đơn người khác và không lộ dữ liệu nhạy cảm trong response.

**Definition of Done cho phần học:** người học vẽ lại đường đi của request, phân biệt 401/403/404, cho thấy nơi tạo Authentication và nơi lấy nó trong Reactor Context, giải thích sự khác nhau giữa quyền route/method/object, và cung cấp test cho ít nhất bốn trường hợp: không token, thiếu scope, sai owner/tenant, đúng toàn bộ quyền. Phải trả lời được: **Nếu Alice biết chính xác ID đơn của Bob, lớp nào ngăn Alice truy cập và bài test nào chứng minh điều đó?**

## 11. Tự kiểm tra nhanh

- Nếu GET /health được phép truy cập nhưng GET /api/orders/42 thiếu token nhận 401, quy tắc nào chịu trách nhiệm cho mỗi kết quả?
- Vì sao Bearer token hợp lệ vẫn có thể nhận 403 ở route? Khi nào kiểm tra owner có thể trả 404?
- Nếu cùng service được gọi từ HTTP controller và message consumer, chỉ dựa vào pathMatchers có đủ không?
- Vì sao subject của JWT không mặc nhiên bằng mã người dùng nội bộ? Nên giải quyết việc ánh xạ danh tính ở đâu?
- Vì sao cần kiểm soát tenant ở truy vấn dữ liệu và trong cập nhật, kể cả khi @PreAuthorize đã PASS?
- mockJwt() kiểm tra được điều gì và **không** kiểm tra được điều gì?
- Khi đổi từ Servlet MVC sang WebFlux, những API/khái niệm bảo mật nào phải chuyển từ ThreadLocal và filter Servlet sang Reactive Context và WebFilter?

Nếu chưa giải thích được một câu, quay lại chặng tương ứng ở mục 4 và bổ sung test nhỏ trước khi tiếp tục.

## 12. Tài liệu tham khảo chính thức

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): SecurityWebFilterChain, ServerHttpSecurity và nhiều chain.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): @EnableReactiveMethodSecurity, @PreAuthorize và Reactor Context.
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): kiểm chứng JWT và cấu hình issuer/JWK.
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): mockJwt() và kiểm thử quyền.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, operators và Context.

**Thông điệp kết nối toàn bài:** security không dừng ở việc biến một Bearer token thành Authentication. Hành trình hoàn chỉnh đi từ **HTTP → xác thực → quyền vào chức năng → quyền thực hiện nghiệp vụ → quyền trên dữ liệu cụ thể → kết quả chỉ chứa dữ liệu được phép**.