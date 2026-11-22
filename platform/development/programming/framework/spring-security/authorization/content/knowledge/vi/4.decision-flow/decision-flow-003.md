# AuthorizationManager và đối tượng được bảo vệ trong Spring Security

Trong Spring Security, **phân quyền** là một quyết định về **người gọi có được phép thực hiện thao tác hiện tại trên đối tượng đang được bảo vệ hay không**. Giao diện `AuthorizationManager<T>` là hợp đồng chung để đưa ra quyết định đó. Chữ `T` rất quan trọng: framework không chỉ cung cấp danh tính người dùng, mà còn cung cấp **đối tượng/ngữ cảnh của hoạt động cần được kiểm soát** (*secure object*).

Ví dụ: cùng một nhân viên có quyền `ORDER_READ`, nhưng chỉ được xem đơn trong cửa hàng được giao. Khi kiểm tra ở tầng HTTP, đối tượng bảo vệ có thể là yêu cầu web; ở tầng service, đối tượng bảo vệ có thể là một lời gọi phương thức và các tham số. **Đơn hàng thật trong cơ sở dữ liệu không tự xuất hiện trong đối tượng ấy**: ứng dụng phải tải và đối chiếu nó nếu quy tắc phụ thuộc vào owner, tenant, trạng thái hoặc hạn mức.

Bài này giải thích hợp đồng `AuthorizationManager`, luồng kiểm tra, kiểu đối tượng bảo vệ, các hook HTTP/method security, cách xây policy và kiểm thử quyết định. Ví dụ framework tập trung vào **Spring Security 6.x trên Servlet stack**, với ghi chú cụ thể cho API 6.4–6.5. Ví dụ Java độc lập chạy trên **JDK 17+**.

## 1. `AuthorizationManager<T>` đóng vai trò gì?

`AuthorizationManager<T>` là giao diện cho một thành phần quyết định truy cập. Nó nhận hai đầu vào chính:

1. **`Supplier<Authentication>`**: cách lấy `Authentication` của người gọi khi thật sự cần. `Authentication` chứa principal, authorities và trạng thái xác thực; supplier giúp trì hoãn chi phí lấy thông tin.
2. **`T secureObject`**: đối tượng/ngữ cảnh đang được kiểm soát. Có thể là HTTP request, `RequestAuthorizationContext`, `MethodInvocation` hoặc ngữ cảnh kết quả của lời gọi phương thức.

Hình dung quyết định dưới dạng:

~~~text
AuthorizationManager<T>
  input : Supplier<Authentication> + T secureObject
  output: AuthorizationResult / AuthorizationDecision
          granted = true  -> cho phép đi tiếp ở điểm chặn tương ứng
          granted = false -> từ chối ở điểm chặn tương ứng
          null             -> không đưa ra quyết định (abstain; cần xử lý an toàn)
~~~

Mối liên hệ không phải “role → endpoint” một cách cố định. Manager có thể kiểm tra authority, đường dẫn, HTTP method, tham số phương thức, kết quả trả về hoặc dữ liệu nghiệp vụ đã được tra cứu. **Cùng một người gọi** có thể được phép với tài nguyên A nhưng bị từ chối với tài nguyên B.

Trong Spring Security hiện đại, `AuthorizationManager` thay thế mô hình cấp quyền truyền thống dựa trên `AccessDecisionManager` và `AccessDecisionVoter` cho các phần tích hợp mới. Ứng dụng thường dùng manager có sẵn, hoặc tạo manager riêng khi chính sách không thể diễn đạt đầy đủ bằng `authenticated()`, `hasRole()`, `hasAuthority()`.

### API cần phân biệt theo phiên bản

Ở **Spring Security 6.5**, các phương thức liên quan là:

~~~java
// Chữ ký rút gọn để học API (không phải định nghĩa interface đầy đủ).
AuthorizationResult authorize(Supplier<Authentication> authentication, T object);
AuthorizationDecision check(Supplier<Authentication> authentication, T object);
void verify(Supplier<Authentication> authentication, T object);
~~~

- `authorize(...)` được thêm từ **6.4**, trả `AuthorizationResult` (có thể `null` nếu manager không đưa ra quyết định). Khi **gọi manager từ mã ứng dụng** ở 6.4+, nên ưu tiên `authorize`.
- `check(...)` là giao diện quyết định lâu đời, trả `AuthorizationDecision`; **được đánh dấu deprecated trong 6.5** để khuyến khích người gọi dùng `authorize`. Trong API 6.5, `check` vẫn là phương thức trừu tượng của giao diện chức năng, nên **lambda `(authentication, object) -> new AuthorizationDecision(...)` vẫn là cách khai báo manager hợp lệ**. Ứng dụng Spring Security 6.3 chưa có `authorize` mới.
- `verify(...)` phục vụ tình huống muốn áp dụng quyết định bằng ngoại lệ: với quyết định **từ chối**, nó ném `AccessDeniedException`; không nên đồng nhất `verify` với hàm trả `boolean`.
- `AuthorizationDecision(boolean granted)` là một hiện thực của `AuthorizationResult`. Kiểm tra `isGranted()` khi cần biết ALLOW hay DENY.

Nếu tự viết policy cho một ứng dụng cố định ở Spring Security 6.5, bạn có thể dùng class/lambda tương thích `check` và gọi `authorize` ở nơi sử dụng. Đừng sao chép đoạn `authorize` từ tài liệu mới vào dự án Spring Security cũ mà không kiểm tra phiên bản API.

**Quan trọng:** `null` là “abstain/không có quyết định”, **không phải DENY rõ ràng**. Việc một điểm chặn xử lý `null` thế nào phụ thuộc bộ gọi và cách ghép các manager. Với thao tác nhạy cảm, hãy trả **`new AuthorizationDecision(false)`** khi thiếu thông tin hoặc không có điều kiện cho phép; không dựa vào `null` để mong chặn truy cập.

## 2. `T secureObject` có phải bản ghi nghiệp vụ cần bảo vệ không?

**Không nhất thiết.** Tên *secure object* chỉ **đơn vị mà bộ chặn đang kiểm soát ở thời điểm đó**. Kiểu `T` cho biết manager có thể nhìn thấy thông tin gì.

| Điểm chặn | Kiểu manager tiêu biểu | Đối tượng/ngữ cảnh được truyền | Kiểm tra được gì? |
| --- | --- | --- | --- |
| Servlet request ở `AuthorizationFilter` | `AuthorizationManager<HttpServletRequest>` | `HttpServletRequest` | URL, HTTP method, thông tin request và `Authentication`. |
| Quy tắc `.access(...)` trong `authorizeHttpRequests` | `AuthorizationManager<RequestAuthorizationContext>` | `RequestAuthorizationContext` | `getRequest()` và biến đường dẫn từ matcher qua `getVariables()`. |
| Trước lời gọi method | `AuthorizationManager<MethodInvocation>` | `MethodInvocation` của AOP Alliance | Method, đối tượng đích, tham số; có thể kiểm tra trước khi method chạy. |
| Sau lời gọi method | `AuthorizationManager<MethodInvocationResult>` | Lời gọi method **và kết quả đã trả về** | Có thể quyết định người gọi có được nhận kết quả hay không. |
| Policy do ứng dụng tự tổ chức | Kiểu `T` do ứng dụng chọn | DTO, command hoặc domain context | Thông tin do ứng dụng đưa vào để quyết định theo nghiệp vụ. |

**Sự khác biệt mấu chốt:** `RequestAuthorizationContext` không phải `Order`; `MethodInvocation` không phải `Customer`. Một route `GET /api/orders/42` chỉ cung cấp **ID “42”**, không chứng minh đơn 42 thuộc ai hoặc trạng thái hiện tại của nó. Manager nào cần dữ liệu đó phải tải hoặc được cấp **dữ liệu tin cậy từ server**.

Ví dụ cụ thể:

~~~text
HTTP GET /api/orders/42
  secure object ở filter: HttpServletRequest
  secure object ở DSL .access: RequestAuthorizationContext
     request: GET /api/orders/42
     variables: {orderId: "42"} (nếu matcher trích xuất được)
  domain resource trong DB:
     Order(id=42, tenantId="shop-a", ownerId="alice", status="PAID")
~~~

`getVariables()` chỉ có giá trị đúng khi request matcher cung cấp biến đã trích xuất. Không mặc định rằng mọi mẫu URL đều tạo được cùng một map. Cũng không dùng `orderId` như bằng chứng truy cập: phải xác minh người gọi so với **bản ghi thực**.

Ở tầng method security, `MethodInvocation` có thể chứa ID, object DTO, hoặc tham số số tiền. Nếu cần kiểm tra điều kiện trên trạng thái bản ghi vừa thay đổi, service phải lấy dữ liệu thực tế phù hợp; lời gọi method chỉ cung cấp các argument đã được truyền vào.

## 3. Luồng quyết định ở tầng HTTP Servlet

Với `authorizeHttpRequests`, Spring Security dùng `AuthorizationFilter` để kiểm soát request. Luồng khái quát:

~~~mermaid
flowchart TD
  A[HTTP request] --> B[Security filter chain]
  B --> C[Authentication đã được thiết lập nếu cần]
  C --> D[AuthorizationFilter]
  D --> E[Supplier Authentication + HttpServletRequest]
  E --> F[AuthorizationManager định tuyến theo RequestMatcher]
  F --> G[Manager của quy tắc phù hợp]
  G --> H{AuthorizationResult}
  H -->|ALLOW| I[Tiếp tục FilterChain tới controller]
  H -->|DENY| J[AccessDeniedException]
  J --> K[ExceptionTranslationFilter và phản hồi phù hợp]
~~~

Bản chất từng bước:

1. `AuthorizationFilter` tạo một `Supplier<Authentication>` lấy danh tính hiện hành từ `SecurityContextHolder` khi cần.
2. Manager ở tầng request xét mẫu đường dẫn, HTTP method và quy tắc được khai báo. Với `authorizeHttpRequests`, **matcher phù hợp đầu tiên** xác định quy tắc được áp dụng.
3. Quy tắc có thể dùng manager dựng sẵn (`permitAll`, `denyAll`, `authenticated`, `hasAuthority`) hoặc manager tùy biến được truyền qua `.access(...)`.
4. Nếu bị từ chối, Spring phát sinh ngoại lệ kiểm soát truy cập; `ExceptionTranslationFilter` phối hợp `AuthenticationEntryPoint` / `AccessDeniedHandler` để xử lý. REST API thường trả 401 cho người chưa xác thực cần đăng nhập, 403 cho người đã xác thực nhưng thiếu quyền; login form có thể chuyển hướng.
5. Nếu được cho phép, request **tiếp tục qua filter chain**. Điều này **không tự động chứng minh** controller/service sẽ được phép thao tác lên từng bản ghi; các chính sách khác ở method/service vẫn có thể từ chối.

Spring Security còn có cơ chế phát sự kiện kết quả phân quyền (`AuthorizationDeniedEvent`, `AuthorizationGrantedEvent`); việc thực sự ghi nhận/công bố thành công tùy `AuthorizationEventPublisher` và cấu hình, nên không giả định mọi kết quả ALLOW đều thành một log sự kiện.

Lưu ý `AuthorizationFilter` được đặt gần cuối security filter chain theo cấu hình mặc định và có thể kiểm tra cả các lần dispatch như `REQUEST`, `FORWARD`, `ERROR`. Cấu hình matcher phải tính đến những luồng thực tế của ứng dụng. Nếu tự thêm filter phía sau `AuthorizationFilter`, đừng mặc định chúng đã được chặn theo cùng cách.

## 4. Ghép RequestMatcher với manager phù hợp

Ví dụ cấu hình ngắn trong Spring Boot 3 + Spring Security 6:

~~~java
@Configuration
class WebSecurityConfig {
    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
            .requestMatchers("/api/admin/**").hasAuthority("ADMIN_PANEL")
            .requestMatchers("/api/orders/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Đoạn trên là **cấu hình để đặt trong dự án Spring**, cần các import của Spring Framework/Spring Security và một phương thức xác thực phù hợp. Nó không phải Java độc lập chạy bằng `javac` khi thiếu thư viện.

Mỗi nhánh dẫn tới một cơ chế phân quyền: `permitAll` không cần đọc `Authentication`, `hasAuthority` kiểm tra authority trong `Authentication`, `authenticated` yêu cầu người dùng đã xác thực và `denyAll` chặn mặc định. `/api/orders/**` chỉ yêu cầu đăng nhập, **chưa kiểm tra đơn của ai**.

Ở tầng HTTP, `RequestMatcherDelegatingAuthorizationManager` là hiện thực tiêu biểu của `AuthorizationManager<HttpServletRequest>`: nó chọn delegate dựa trên `RequestMatcher`. Khi dùng API cấu hình `.access(...)`, manager được ứng dụng cung cấp thường nhận **`RequestAuthorizationContext`**. Đây là lý do cùng luồng HTTP xuất hiện hai kiểu generic khác nhau, không có mâu thuẫn về thiết kế.

### Manager tùy biến đọc ID từ đường dẫn

Một ví dụ tối giản chỉ cho phép xem đơn khi policy nghiệp vụ xác minh có quyền trên **đúng đơn hàng**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
class OrderSecurityConfig {

    @Bean
    SecurityFilterChain orderChain(HttpSecurity http,
                                   OrderReadPolicy policy) throws Exception {
        AuthorizationManager<RequestAuthorizationContext> canReadOrder =
                (authentication, context) -> {
                    String orderId = context.getVariables().get("orderId");
                    if (orderId == null || orderId.isBlank()) {
                        return new AuthorizationDecision(false);
                    }
                    // policy phải xác minh cả danh tính, quyền, tenant/owner
                    // và dữ liệu Order trên server; không tin chỉ mỗi ID.
                    Authentication actor = authentication.get();
                    return new AuthorizationDecision(
                            policy.canRead(actor, orderId));
                };

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/{orderId}")
                .access(canReadOrder)
            .anyRequest().denyAll()
        );
        return http.build();
    }

    interface OrderReadPolicy {
        boolean canRead(Authentication authentication, String orderId);
    }
}
~~~

Đây là **một đoạn cấu hình Spring có thể đặt vào dự án đã cài dependencies tương ứng**, không phải file Java độc lập với JDK thuần. `OrderReadPolicy` chỉ khai báo hợp đồng; **ứng dụng phải viết hiện thực thật** lấy user/tenant từ security context đáng tin cậy, tra Order bằng ID, so permission và owner/tenant, rồi trả `false` nếu thiếu điều kiện. Ví dụ sử dụng API `check` thông qua lambda tương thích Spring Security 6.x; trên 6.5 đây là interface chức năng có `check` trừu tượng và `authorize` mặc định.

Điểm cần đọc kỹ: `context.getVariables().get("orderId")` là **tham số định tuyến**, không phải đối tượng nghiệp vụ. Phép `.access(canReadOrder)` gọi manager cho request khớp; nếu matcher không trích được `orderId`, ví dụ từ chối. Giá trị `actor` do supplier lấy có thể biểu diễn người chưa xác thực/anonymous; policy cần kiểm tra đúng, **không chỉ tin `isAuthenticated()`** vì cách biểu diễn anonymous trong Spring Security có thể dùng `Authentication` có cờ authenticated.

Dùng database trong request manager có thể tốn query; khi controller/service sau đó lại tải cùng đơn, dễ sinh **hai lần truy vấn** và cửa sổ thay đổi dữ liệu. Với thao tác sửa trạng thái nhạy cảm, nên giữ kiểm tra bất biến gần cập nhật trong service, bằng transaction và cách chống cập nhật đồng thời phù hợp. Ví dụ request manager minh họa cách dùng *secure object*, không yêu cầu mọi phép kiểm tra sở hữu đều phải nằm trong filter.

## 5. Luồng quyết định ở tầng method

Tại tầng service, đối tượng bảo vệ thường là **`MethodInvocation`**, chứ không phải HTTP request. Spring Security dùng AOP proxy và các interceptor như:

- `AuthorizationManagerBeforeMethodInterceptor` kết hợp `PreAuthorizeAuthorizationManager` để kiểm tra **trước** khi method chạy.
- `AuthorizationManagerAfterMethodInterceptor` kết hợp `PostAuthorizeAuthorizationManager` để kiểm tra **sau** khi method trả kết quả.
- `@EnableMethodSecurity` bật các cơ chế như `@PreAuthorize`, `@PostAuthorize`; Spring Boot Starter Security **không tự bật method security**.

Đoạn minh họa trong Spring-managed service:

~~~java
@Service
class OrderService {
    @PreAuthorize("hasAuthority('ORDER_READ')")
    public OrderDto loadOrder(String orderId) {
        // Tải Order thật và áp dụng policy theo tenant/owner.
        // Chỉ sau khi qua đủ điều kiện mới chuyển thành OrderDto.
        return serviceLogicForAuthorizedOrder(orderId);
    }
}
~~~

`OrderDto` và `serviceLogicForAuthorizedOrder` là thành phần ứng dụng giả định; đoạn trên **không chạy độc lập**. Khi proxy gặp lời gọi `loadOrder("42")`, `MethodInvocation` có thể cung cấp tên method và tham số `"42"`. `PreAuthorizeAuthorizationManager` kiểm tra biểu thức dựa trên `Authentication` cùng ngữ cảnh lời gọi; ví dụ kiểm tra `ORDER_READ` **không tự kiểm tra owner của Order 42**. Logic bên trong method hoặc một policy bean cần thực hiện phần đó.

Ví dụ bảo vệ cả dữ liệu sau khi phương thức trả về:

~~~java
@PreAuthorize("hasAuthority('ORDER_READ')")
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public OrderDto findOrder(String id) {
    return repositoryAndMapper.loadOrderDto(id);
}
~~~

`@PostAuthorize` có thể dựa trên **đối tượng trả về** để từ chối tiết lộ kết quả nếu owner không khớp. Thực hiện method trước rồi kiểm tra sau có thể phù hợp cho **truy vấn không gây tác dụng phụ**; không dùng kiểm tra sau như “phanh an toàn” cho thao tác đã chuyển tiền, đã gửi email hoặc ghi dữ liệu. Với ghi/cập nhật, cần kiểm tra **trước hành động** và bảo vệ điều kiện ở transaction.

`MethodInvocationResult` bao gồm lời gọi method và giá trị đã trả, giúp manager hậu kiểm nhìn thấy nhiều thông tin hơn manager tiền kiểm. Lưu ý `@PostAuthorize` chỉ hoạt động với kết quả và lời gọi đi qua interceptor phù hợp; không tự thay thế kiểm soát truy vấn/tài nguyên.

**Giới hạn proxy:** lời gọi một method sang method khác trên **cùng instance** có thể không đi qua AOP proxy nên không kích hoạt method security như kỳ vọng. Nếu thao tác nghiệp vụ bắt buộc phải giữ bất biến, hãy bảo vệ ở tầng service/policy dùng chung và kiểm thử cả những entry point ngoài controller.

## 6. “Được bảo vệ” có hai lớp khác nhau

Một sai lầm thường gặp là đánh đồng **đối tượng mà Spring chặn** với **dữ liệu nghiệp vụ cuối cùng**.

| Câu hỏi | Ở tầng filter | Ở tầng service |
| --- | --- | --- |
| Framework đang bảo vệ điều gì? | Một request phù hợp matcher. | Một method invocation / kết quả method. |
| Có ID tài nguyên chưa? | Có thể có trong path/query. | Có thể có trong tham số. |
| Đã biết owner, tenant, trạng thái bản ghi chưa? | Thường **chưa**, nếu không tra cứu thêm. | **Chỉ khi** service/policy đã tải dữ liệu đó. |
| Quyết định nào đủ để cho qua tầng này? | Phù hợp các điều kiện HTTP. | Phù hợp điều kiện gọi method và dữ liệu nghiệp vụ. |
| Sau khi qua tầng này đã an toàn tuyệt đối chưa? | Chưa; service vẫn cần giới hạn dữ liệu. | Cần bảo đảm cả logic cập nhật và bất biến đồng thời. |

Ví dụ **BOLA/IDOR**: cả `GET /api/orders/42` và `GET /api/orders/43` đều vượt qua `authenticated()`. Nhưng Order 42 thuộc Alice, Order 43 thuộc Bob. Nếu Alice thay ID trong URL, request-level manager kiểm tra “đã đăng nhập” vẫn cho qua, còn service phải từ chối Order 43 trừ khi Alice có quyền hợp lệ để xem nó.

Ngược lại, để chặn API backoffice nội bộ, chỉ cần rule HTTP yêu cầu authority có thể đã là một lớp kiểm tra hữu ích. **Nơi thực thi phụ thuộc vào thông tin mà quyết định cần biết.** Không ép mọi luật thành một biểu thức URL, cũng không bỏ qua request authorization chỉ vì service có policy.

Đối với dữ liệu đa tenant, các truy vấn đọc danh sách nên lọc theo tenant/authorization ngay ở tầng dữ liệu nếu phù hợp. Lấy tất cả bản ghi rồi lọc sau có thể làm lộ metadata, số lượng kết quả, phân trang hoặc chi phí xử lý không cần thiết. Với phương thức cập nhật, cần xét dữ liệu mới nhất, giao dịch và cơ chế kiểm soát cập nhật cạnh tranh.

## 7. Vì sao đầu vào `Authentication` là một `Supplier`?

`Supplier<Authentication>` giúp manager **chỉ đọc danh tính khi quy tắc cần đến**. Ví dụ `permitAll` quyết định cho phép endpoint công khai mà không cần tải authentication từ session. Điều này giảm công việc không cần thiết và giúp quy tắc có cấu trúc rõ.

~~~text
GET /api/catalog          -> permitAll -> ALLOW, không cần đọc Authentication
GET /api/orders/42        -> hasAuthority / custom policy
                           -> cần Authentication để xét quyền
GET /api/internal/secret  -> denyAll -> DENY, không cần đọc Authentication
~~~

Trong custom manager, nếu kiểm tra ban đầu đã xác định request không hợp lệ, có thể trả DENY trước khi gọi `authentication.get()`. Nhưng đừng kéo dài thời gian lưu trữ một `Supplier` ngoài vòng đời request hoặc tự giả định nó là một principal bất biến suốt các luồng bất đồng bộ.

Trên Spring Security servlet, `Authentication` thường lấy từ `SecurityContextHolder`. `Authentication` **không phải** `AuthorizationResult`: nó mô tả danh tính/trạng thái và authorities; manager dùng các thông tin đó cùng secure object để đưa ra quyết định. **Đăng nhập thành công không đồng nghĩa được truy cập mọi đối tượng**.

## 8. Ví dụ Java 17 chạy độc lập: quyền phụ thuộc người gọi và đối tượng

Chương trình sau dùng **`Supplier<Actor>`** và một object **`ProtectedAction`** để mô phỏng đúng dạng hai đầu vào của một policy. Nó **không dùng thư viện Spring**, không cố giả lập mọi API Spring Security, mà giúp quan sát quyết định và tính trì hoãn của supplier.

Chính sách ví dụ:

- Tài liệu công khai được phép đọc mà không cần tra danh tính.
- Tài liệu riêng cần đã xác thực, đúng tenant, có `DOC_READ`.
- Chủ tài liệu được đọc; người có thêm `DOC_READ_ALL` được đọc các tài liệu khác **trong cùng tenant**.
- Mọi thao tác ngoài `READ` bị từ chối theo chính sách minh họa.

Lưu đúng tên tệp **ProtectedObjectDecisionDemo.java**:

~~~java
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class ProtectedObjectDecisionDemo {
    enum Operation { READ, EDIT }

    record Actor(String userId, String tenantId,
                 Set<String> permissions, boolean authenticated) {}

    record Document(String tenantId, String ownerId, boolean publiclyReadable) {}

    record ProtectedAction(Operation operation, Document document) {}

    record Decision(boolean granted) {}

    static Decision decide(Supplier<Actor> currentActor,
                           ProtectedAction secured) {
        Document document = secured.document();
        if (secured.operation() == Operation.READ && document.publiclyReadable()) {
            return new Decision(true);
        }
        Actor actor = currentActor.get();
        if (actor == null || !actor.authenticated()) {
            return new Decision(false);
        }
        if (secured.operation() != Operation.READ
                || !actor.tenantId().equals(document.tenantId())
                || !actor.permissions().contains("DOC_READ")) {
            return new Decision(false);
        }
        boolean owner = actor.userId().equals(document.ownerId());
        boolean allInTenant = actor.permissions().contains("DOC_READ_ALL");
        return new Decision(owner || allInTenant);
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "shop-a", Set.of("DOC_READ"), true);
        Actor manager = new Actor("mary", "shop-a",
                Set.of("DOC_READ", "DOC_READ_ALL"), true);
        Actor noPermission = new Actor("alice", "shop-a", Set.of(), true);
        Actor anonymous = new Actor("guest", "shop-a",
                Set.of("DOC_READ", "DOC_READ_ALL"), false);
        Document publicDoc = new Document("shop-a", "alice", true);
        Document ownDoc = new Document("shop-a", "alice", false);
        Document otherDoc = new Document("shop-a", "bob", false);
        Document foreignDoc = new Document("shop-b", "bob", false);

        AtomicInteger lookups = new AtomicInteger();
        Supplier<Actor> suppliedAlice = () -> {
            lookups.incrementAndGet();
            return alice;
        };

        System.out.println("Public read: " + decide(suppliedAlice,
                new ProtectedAction(Operation.READ, publicDoc)).granted());
        System.out.println("Authentication lookups for public: " + lookups.get());
        System.out.println("Owner read: " + decide(() -> alice,
                new ProtectedAction(Operation.READ, ownDoc)).granted());
        System.out.println("Different owner: " + decide(() -> alice,
                new ProtectedAction(Operation.READ, otherDoc)).granted());
        System.out.println("Manager same tenant: " + decide(() -> manager,
                new ProtectedAction(Operation.READ, otherDoc)).granted());
        System.out.println("Manager other tenant: " + decide(() -> manager,
                new ProtectedAction(Operation.READ, foreignDoc)).granted());
        System.out.println("Missing permission: " + decide(() -> noPermission,
                new ProtectedAction(Operation.READ, ownDoc)).granted());
        System.out.println("Anonymous: " + decide(() -> anonymous,
                new ProtectedAction(Operation.READ, ownDoc)).granted());
        System.out.println("Unsupported edit: " + decide(() -> manager,
                new ProtectedAction(Operation.EDIT, ownDoc)).granted());
    }
}
~~~

Lệnh biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac ProtectedObjectDecisionDemo.java
java ProtectedObjectDecisionDemo
~~~

Kết quả chuẩn:

~~~text
Public read: true
Authentication lookups for public: 0
Owner read: true
Different owner: false
Manager same tenant: true
Manager other tenant: false
Missing permission: false
Anonymous: false
Unsupported edit: false
~~~

**Giải thích:** `ProtectedAction` chứa cả **hành động** và **Document**, nên policy có đủ dữ liệu để kiểm tra. Dù manager có quyền `DOC_READ_ALL`, tài liệu khác tenant vẫn bị từ chối. Với tài liệu công khai, nhánh ALLOW chạy **trước** `currentActor.get()`, nên bộ đếm supplier vẫn bằng 0. Nếu đổi `Operation.READ` thành `EDIT`, chính sách trả DENY vì không hề định nghĩa đường cho phép thao tác này.

Trong ứng dụng thật, `Document.publiclyReadable()`, owner, tenant và các thuộc tính bảo mật phải đến từ dữ liệu server được xác minh; caller không được tự gửi `publiclyReadable=true` để mở quyền. `Actor` phải đại diện dữ liệu đã xác thực, không phải thông tin client tùy ý khai báo.

## 9. Khi nào cần manager dựng sẵn, khi nào cần custom manager?

Dùng manager dựng sẵn khi chính sách đơn giản và ổn định:

| Mong muốn | Cơ chế thường dùng | Ranh giới |
| --- | --- | --- |
| Tài nguyên thật sự công khai | `permitAll` | Không cần truy xuất Authentication. |
| Chặn mặc định | `denyAll` | Không có đường truy cập được phép. |
| Người dùng phải đăng nhập | `authenticated` | Chưa quyết định trên từng tài nguyên. |
| Yêu cầu authority chính xác | `hasAuthority("ORDER_READ")` | Không biết owner/tenant của từng đơn. |
| Yêu cầu role theo quy ước | `hasRole("ADMIN")` | Mặc định đối chiếu authority `ROLE_ADMIN`. |
| Chọn rule theo URL và HTTP method | `authorizeHttpRequests` + `requestMatchers` | Quy tắc khớp đầu tiên được áp dụng. |
| Quyết định theo request/method + dữ liệu động | `.access(customManager)` hoặc policy service | Phải chủ động lấy dữ liệu tin cậy và xác định kết quả. |

Spring Security cũng có các manager chuyên biệt như `AuthorityAuthorizationManager`, `AuthenticatedAuthorizationManager`, `RequestMatcherDelegatingAuthorizationManager`, `PreAuthorizeAuthorizationManager`, `PostAuthorizeAuthorizationManager`. Các thành phần này **phục vụ những kiểu đối tượng/ngữ cảnh khác nhau**, vì vậy không tự ý ép `AuthorizationManager<MethodInvocation>` vào chỗ cần `AuthorizationManager<RequestAuthorizationContext>`.

Trong hệ thống lớn, có thể ghép các manager với phép AND/OR hoặc dùng policy engine riêng. Khi làm vậy, phải xác định rõ xử lý kết quả **ALLOW, DENY và abstain**; một nhánh role được cho phép không được vô tình bỏ qua tenant/owner hay trạng thái. Với các luật nghiệp vụ phức tạp, một hàm policy có đầu vào và các test rõ ràng thường dễ kiểm toán hơn một chuỗi biểu thức dài.

## 10. Phòng tránh nhầm lẫn về “đối tượng được bảo vệ”

1. **Cho rằng `T` luôn là entity.** Thực tế nó thường là request/method invocation. → Xác định đúng kiểu `T` ở mỗi điểm chặn, chỉ đọc được dữ liệu mà đối tượng đó thật sự chứa.
2. **Nhầm path ID với quyền sở hữu.** `/orders/42` chỉ có ID. → Tra owner/tenant thực từ server và so với người gọi đáng tin.
3. **Chỉ có `authenticated()` rồi tin rằng mọi bản ghi được bảo vệ.** → Thêm kiểm soát theo dữ liệu tại service/domain.
4. **Dùng `AuthorizationManager<MethodInvocation>` cho `.access` HTTP.** → Dùng `AuthorizationManager<RequestAuthorizationContext>` ở DSL HTTP; method security có kiểu ngữ cảnh riêng.
5. **Gọi `authentication.get()` trong mọi nhánh.** → Quy tắc `permitAll`/`denyAll` có thể không cần đọc Authentication; tối ưu có điều kiện, không phá tính đúng.
6. **Trả `null` khi thiếu dữ liệu rồi mong fail closed.** → Trả DENY tường minh ở các trường hợp rủi ro hoặc thiếu điều kiện bắt buộc.
7. **Dựa vào `@PostAuthorize` để ngăn hành động đã có side effect.** → Kiểm tra trước khi ghi và dùng transaction/concurrency guard khi cần.
8. **Tin dữ liệu do client gửi làm tài nguyên bảo mật.** → Dùng record/current state ở server và xác minh claims/authorities.
9. **Đặt policy chỉ ở một controller.** → Các đường gọi service khác, job và message consumer phải giữ cùng bất biến.
10. **Không thống nhất phiên bản API.** → Kiểm tra `check`/`authorize` theo Spring Security đang chạy; đừng mặc định mọi snippet mới biên dịch trên 6.3.
11. **Bỏ qua request dispatch và thứ tự matcher.** → Kiểm thử FORWARD/ERROR khi liên quan và bảo đảm rule cụ thể nằm trước rule bao quát.
12. **Chỉ test đường ALLOW.** → Test DENY khi thiếu authority, đổi ID, đổi tenant, status và trạng thái xác thực.

## 11. Bảng test cho manager và đối tượng đang bảo vệ

Test manager có giá trị nhất khi giữ cùng authentication nhưng **thay đối tượng bảo vệ**:

| Đầu vào | Đối tượng/ngữ cảnh | Kết quả cần có |
| --- | --- | --- |
| Người không đăng nhập | Request tới API riêng tư | DENY, REST thường 401 nếu cần xác thực. |
| Người có `ORDER_READ` | Request xem đơn hợp lệ cùng tenant/owner | ALLOW nếu policy đầy đủ thỏa. |
| Cùng người, cùng authority | Request xem đơn của người khác không thuộc phạm vi | DENY. |
| Cùng người, cùng authority | Request có order ID không tồn tại | DENY hoặc 404 theo quy ước API, không rò dữ liệu. |
| Người thuộc tenant A | Request có order ID thuộc tenant B | DENY/404 nhất quán, không rò tenant khác. |
| Người có role hợp lệ nhưng thiếu permission | Request tới action cần permission | DENY. |
| Đối tượng công khai | `permitAll` | ALLOW mà không cần lấy Authentication. |
| Không có matcher hợp lệ | `anyRequest().denyAll()` | DENY. |
| Method có tham số hợp lệ | `MethodInvocation` phù hợp policy | Cho lời gọi đi tiếp. |
| Cùng method với ID khác | `MethodInvocation` có ID ngoài phạm vi | Bị từ chối trước khi xử lý nhạy cảm. |
| Method trả bản ghi không được tiết lộ | Ngữ cảnh hậu kiểm `MethodInvocationResult` | Từ chối trả dữ liệu theo chính sách phù hợp. |
| Hai yêu cầu ghi cạnh tranh | Cùng tài nguyên, trạng thái thay đổi | Chỉ cập nhật hợp lệ qua điều kiện transaction/locking. |

Với Spring Security Test, có thể dùng MockMvc để kiểm tra request-level authorization, `@WithMockUser` hoặc SecurityContext test rõ authority và role, rồi bổ sung test service/policy cho từng tổ hợp owner/tenant/status. Khi test manager tùy biến, kiểm tra đúng biến được `RequestMatcher` trích xuất và xác minh `Authentication` đưa vào có authorities khớp nguồn thực tế.

Nếu chỉ test rằng `GET /api/orders/42` trả 200 cho Alice, bạn chưa chứng minh được phân quyền theo đối tượng. Test quan trọng là **cùng Alice gọi `/api/orders/43`**, thuộc người khác, phải bị chặn.

## 12. Quy trình thiết kế một `AuthorizationManager` cho chức năng mới

Khi có yêu cầu “Nhân viên được xuất báo cáo khách hàng”, hãy thực hiện tuần tự:

1. **Định nghĩa thao tác và tài nguyên:** xuất báo cáo nào, tổ chức nào, bộ lọc dữ liệu nào.
2. **Xác định người gọi và authority cần thiết:** ví dụ `CUSTOMER_REPORT_EXPORT`, không suy từ việc đã đăng nhập.
3. **Xác định các điều kiện dữ liệu:** tenant/chi nhánh, phạm vi khách hàng được phép, trạng thái tài khoản, giới hạn dữ liệu.
4. **Chọn điểm chặn và kiểu `T`:** request HTTP cần chặn truy cập endpoint; service cần chặn thao tác thực/giới hạn dữ liệu; có thể dùng cả hai.
5. **Chọn manager có sẵn hay tự viết:** đơn giản thì `hasAuthority`; phức tạp thì policy service hoặc `AuthorizationManager<T>` phù hợp điểm chặn.
6. **Định nghĩa DENY rõ ràng:** thiếu context, ID sai, khác tenant hoặc không xác thực thì không tạo đường ALLOW ngầm.
7. **Kiểm soát cập nhật và dữ liệu đầu ra:** không dùng hậu kiểm để biện minh cho side effect; lọc dữ liệu từ truy vấn và bảo vệ các thao tác ghi.
8. **Viết test cho cả hai đầu vào:** giữ principal và đổi đối tượng; giữ đối tượng và đổi principal/authority; bổ sung ca chưa xác thực và cạnh tranh.
9. **Quan sát và vận hành:** ghi audit cần thiết cho quyết định nhạy cảm, không để lộ token hoặc dữ liệu cá nhân; theo dõi lỗi 403 do mapper/permission hay do policy đối tượng.

**Điểm cần nhớ:** `AuthorizationManager<T>` trả lời câu hỏi truy cập bằng cách kết hợp **ai đang yêu cầu** (`Supplier<Authentication>`) với **điều gì đang được bảo vệ** (`T`). Ở HTTP, `T` thường là request/ngữ cảnh request; ở method security, `T` thường là invocation hoặc kết quả invocation. Đó là đầu mối để đưa ra quyết định, nhưng **bản ghi nghiệp vụ và điều kiện kiểm soát của nó phải được xác minh riêng khi cần**. Quyết định ALLOW ở một lớp không loại bỏ trách nhiệm bảo vệ dữ liệu ở các lớp sau.

### Tài liệu tham khảo

- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — RequestAuthorizationContext API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/intercept/RequestAuthorizationContext.html)
