# Forward nội bộ và các request được thực thi lại

## 1. Một URL được phép chưa phải là toàn bộ vòng đời của request

Khi học Spring Security trên nền Servlet, ta thường hình dung một HTTP request đi qua chuỗi filter, được phân quyền một lần rồi tới controller. Thực tế một **HTTP request có thể trải qua nhiều lượt dispatch nội bộ**: controller chuyển tiếp sang view bằng `forward`, container dispatch sang trang lỗi, hoặc ứng dụng khởi động xử lý bất đồng bộ rồi dispatch lại kết quả. Mỗi lượt có thể có **đường dẫn đích, `DispatcherType` và điểm vào xử lý khác với lần đầu**.

Vì thế, hai câu hỏi phải được trả lời độc lập:

1. **Request lần đầu có được vào endpoint ban đầu không?**
2. **Nếu cùng request được chuyển tiếp/dispatch lại, đích mới có được thực thi đúng chính sách không?**

Giả sử user truy cập `GET /app/orders`. HTTP rule cho người đăng nhập xem trang danh sách; controller sau đó trả tên view, và view resolver thực hiện forward sang `/WEB-INF/views/orders.jsp`. Nếu phân quyền lại ở lượt `FORWARD`, một quy tắc chỉ cho phép `/app/orders` có thể khiến trang JSP nhận 403. Nhưng nếu sửa bằng cách mở **mọi forward**, một forward tới handler nhạy cảm có thể trở thành lối đi ngoài chính sách nếu không có bảo vệ ở tầng nghiệp vụ.

Đó là bài toán trung tâm: **phân biệt internal dispatch phục vụ hiển thị với đường dẫn thực hiện hành động cần quyền; bảo vệ cả hai mà không nhầm “request cũ” thành “đã được phép làm mọi thứ”.**

### Minh họa vòng đời

```text
Client
  |
  | GET /app/orders
  v
Servlet container: DispatcherType.REQUEST
  |
  v
Spring Security filter chain
  |  kiểm tra quyền vào /app/orders
  v
Spring MVC controller
  |  return "orders"
  v
View resolver / RequestDispatcher.forward(...)
  |
  v
Servlet container: DispatcherType.FORWARD
  |  đường đích /WEB-INF/views/orders.jsp
  |  vẫn trong request logic ban đầu
  |  nhưng là lượt dispatch khác
  v
Các filter phù hợp dispatcher type có thể chạy lại
  |
  v
View render và trả response
```

Nếu controller ném exception hoặc gọi `sendError(...)`, server có thể tạo lượt `ERROR` hướng đến trang lỗi. Nếu request xử lý bất đồng bộ và được dispatch lại, lượt sau có thể mang `ASYNC`. **Không phải mọi thành phần đều chạy ở mọi lượt**: còn phụ thuộc đăng ký filter theo dispatcher type, thứ tự filter, chính sách `OncePerRequestFilter` và cấu hình servlet/container.

## 2. Năm DispatcherType của Servlet

Jakarta Servlet định nghĩa năm loại dispatch. Spring Security Servlet cần được hiểu trong nền tảng đó.

| `DispatcherType` | Phát sinh khi nào? | Điểm cần lưu ý |
| --- | --- | --- |
| `REQUEST` | Request đầu vào thông thường từ client | Bắt đầu chuỗi xử lý HTTP |
| `FORWARD` | Một servlet/controller chuyển việc xử lý tới tài nguyên khác bằng `RequestDispatcher.forward(...)` | Đường đích và tham số có thể được điều chỉnh; ban đầu đã có một lượt request |
| `INCLUDE` | Một tài nguyên nhúng nội dung tài nguyên khác bằng `RequestDispatcher.include(...)` | Không phải trang đích được thay thế hoàn toàn; phản hồi bị giới hạn về status/header |
| `ERROR` | Container đưa request tới cơ chế/trang xử lý lỗi | Có thể là lần dispatch bổ sung sau exception hoặc mã lỗi |
| `ASYNC` | Request được dispatch lại qua `AsyncContext.dispatch(...)` | Có thể tiếp tục xử lý trên luồng khác; cần hiểu security context |

Mỗi `HttpServletRequest` có thể cung cấp:

```java
DispatcherType type = request.getDispatcherType();
```

Trong đó `DispatcherType` là `jakarta.servlet.DispatcherType`. Một filter có thể được container gọi cho loại dispatch này nhưng không cho loại khác, tùy cách đăng ký. **Bản thân `getDispatcherType()` không quyết định cấp quyền**; nó là dữ kiện để chọn chính sách và hiểu vòng đời.

### 2.1. `REQUEST` không phải “tất cả các lượt”

Lượt đầu tiên là `REQUEST`. Nhưng nếu controller trả về một view dùng forward, hoặc container hiển thị trang lỗi, một phần xử lý có thể được gọi thêm. Vì thế:

- Đừng khẳng định “filter chắc chắn chỉ chạy một lần trong toàn bộ HTTP request”.
- Đừng khẳng định “cứ có một lượt khác thì user đã gửi HTTP request mới”.
- Đừng cho rằng authorization ở lượt đầu đương nhiên đã bao trùm hành động của mọi đích nội bộ.

### 2.2. Forward khác redirect

| Tiêu chí | Forward nội bộ | Redirect |
| --- | --- | --- |
| Ai điều khiển? | Servlet container/server | Server trả mã 3xx và `Location` để client gửi request tiếp |
| Số request từ client | Thường vẫn một request client | Thường tạo request HTTP tiếp theo từ client |
| `DispatcherType` ở đích | `FORWARD` | Request mới thường bắt đầu bằng `REQUEST` |
| URL hiển thị ở browser | Thường giữ nguyên URL ban đầu | Thường chuyển sang URL mới |
| Request attributes | Có thể mang theo trong cùng request logic | Không tự chuyển sang request HTTP mới |
| Security context | Thường liên tục trong request forward, phụ thuộc filter/ngữ cảnh | Cần xác thực/khôi phục theo cơ chế của request mới |
| Điều cần bảo vệ | Cả endpoint đầu và đích được forward tới | Cả endpoint đầu và endpoint mới |

Ví dụ Spring MVC:

```java
@GetMapping("/old-page")
public String forward() {
    return "forward:/new-page";
}

@GetMapping("/moved-page")
public String redirect() {
    return "redirect:/new-page";
}
```

Đây là **đoạn mã minh họa trong controller**, không phải chương trình độc lập. `forward:` yêu cầu chuyển tiếp nội bộ; `redirect:` tạo phản hồi hướng client chuyển sang đường đích. Cơ chế router và view resolver cụ thể vẫn cần kiểm tra theo cấu hình MVC.

**Một redirect không được coi là đã qua phân quyền chỉ vì endpoint nguồn từng cho phép.** Trình duyệt hoặc client có thể gọi thẳng URL đích mà không đi qua nguồn, và HTTP request mới cần chịu chính sách riêng.

### 2.3. Forward khác include

`RequestDispatcher.include(...)` nhúng đầu ra của tài nguyên khác vào response hiện tại. Trong include, thông tin path của request gốc được giữ theo ngữ nghĩa Servlet, và tài nguyên được include bị giới hạn quyền thay đổi status/header. Ngược lại, forward chuyển trách nhiệm tạo response sang tài nguyên đích, thường điều chỉnh đường dẫn/parameter được nhìn thấy và phải xảy ra **trước khi response đã được commit**.

Cả hai vẫn là cơ chế server-side. Việc include một fragment HTML hoặc JSP không khiến fragment đó được mặc định phép đọc dữ liệu nhạy cảm. Nếu fragment đọc dữ liệu, các service/repository liên quan vẫn phải tuân thủ quyền theo đối tượng.

## 3. Điều gì được giữ và điều gì thay đổi khi forward?

### 3.1. Request cùng vòng đời nhưng đích thay đổi

Servlet API bảo đảm cơ chế chuyển tiếp giữ request/response theo hợp đồng (hoặc các wrapper tương ứng). Với `RequestDispatcher` lấy bằng đường dẫn, thông tin path và parameter được điều chỉnh để phản ánh tài nguyên đích; vì vậy code ở đích có thể thấy những giá trị path khác lượt đầu.

Sau `forward(...)`:

- `request.getDispatcherType()` tại đích cho `FORWARD`.
- Đường hiện hành có thể chỉ tới tài nguyên đích.
- Request attributes do server thiết lập có thể tiếp tục tồn tại và được đọc ở đích.
- Các thuộc tính tiêu chuẩn dành cho forward giữ thông tin request ban đầu.
- Không tạo ra một principal mới chỉ vì chuyển tới view.
- Nếu response đã commit, gọi forward không hợp lệ và có thể gây `IllegalStateException`.

Điều này giải thích vì sao log chỉ ghi `requestURI` mà không ghi dispatcher type đôi khi khiến một request nhìn như “gọi hai endpoint”. Hai dòng log có thể thuộc **một request client với hai lượt xử lý nội bộ**.

### 3.2. Các request attribute chuẩn cho forward

Jakarta Servlet cung cấp các hằng tên attribute trong `jakarta.servlet.RequestDispatcher`:

```java
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;

Object originalUri = request.getAttribute(
    RequestDispatcher.FORWARD_REQUEST_URI
);
Object originalContextPath = request.getAttribute(
    RequestDispatcher.FORWARD_CONTEXT_PATH
);
Object originalServletPath = request.getAttribute(
    RequestDispatcher.FORWARD_SERVLET_PATH
);
Object originalQuery = request.getAttribute(
    RequestDispatcher.FORWARD_QUERY_STRING
);
```

Đây là **mã tích hợp Servlet**, giả định biến `request` đã tồn tại. Tên hằng tương ứng với các request attribute chuẩn mà container thiết lập khi forward. Thông tin ban đầu hữu ích để ghi log, dựng lại bối cảnh, debug route hoặc xử lý nghiệp vụ phù hợp.

**Không được dùng `FORWARD_REQUEST_URI` làm “vé cấp quyền”**: “request ban đầu tới URL công khai” không chứng minh “đích nhạy cảm hiện tại cũng được phép”. Đích hoặc service nhạy cảm cần chính sách riêng. Mặt khác, không nên tin một request attribute có tên tự đặt nếu nó được copy từ header/query chưa xác thực.

### 3.3. Security context có tiếp tục tồn tại không?

Trong trường hợp thông thường, `SecurityContext` đã thiết lập ở lượt `REQUEST` được giữ để các thành phần xử lý sau đó có thể sử dụng cùng danh tính. Spring Security cũng mô tả việc context mang qua các lượt dispatch. Tuy nhiên, việc **filter nào tham gia, có nạp/lưu context, và khi nào `SecurityContextHolder` được truy cập** phụ thuộc cấu hình.

Không suy ra rằng:

- Forward tự động làm mới JWT/role từ IdP.
- Một request attribute chứa username là bằng chứng xác thực.
- Chỉ cần principal có ở controller đầu, mọi lần dispatch khác đều được phép.
- Chuyển sang luồng async có thể mặc định dùng `ThreadLocal` context như lượt ban đầu.

Nếu quyết định phụ thuộc quyền vừa bị thu hồi, cần giải pháp TTL, session/token revocation hoặc policy lookup riêng. Forward chỉ di chuyển việc xử lý trong vòng đời request, không thay đổi cơ chế thu hồi quyền.

### 3.4. Request parameter có thể chịu ảnh hưởng của forward

Khi forward theo đường đích có query parameter, request đích có thể nhận các parameter được điều chỉnh theo hợp đồng Servlet. Vì thế không dùng `getParameter("role")` để xác định quyền hay `getParameter("tenant")` để cấp phạm vi: client và mã ứng dụng có thể ảnh hưởng những giá trị đó. Các quyết định quan trọng phải dựa vào `Authentication`, membership, dữ liệu máy chủ và chính sách.

## 4. Spring Security kiểm tra những lượt dispatch nào?

### 4.1. AuthorizationFilter có thể phân quyền nhiều lần

Trong cấu hình `authorizeHttpRequests` của Spring Security Servlet 6.x, tài liệu chính thức nêu `AuthorizationFilter` phân quyền không chỉ ở lượt `REQUEST` mà còn ở các lượt dispatch khác như `FORWARD`, `ERROR` và `INCLUDE` khi bộ lọc tham gia xử lý.

Ví dụ:

```text
REQUEST /app/orders
  -> hasAuthority("order:read")
  -> controller trả view
FORWARD /WEB-INF/views/orders.jsp
  -> AuthorizationFilter có thể đánh giá tiếp
  -> nếu không có rule phù hợp, denyAll có thể trả 403
```

Điều này không nhất thiết là lỗi trong xác thực của user. Có thể đơn giản là **request ở lượt forward được match theo đường mới** nhưng cấu hình chỉ có rule cho đường ban đầu.

**Điều kiện kỹ thuật cần nhớ:** chỉ có lượt kiểm tra bổ sung nếu `springSecurityFilterChain`/các filter liên quan được đăng ký và thực sự được gọi cho dispatcher type ấy. Cấu hình servlet/container và filter registration có thể thay đổi kết quả. Không kết luận “chắc chắn mỗi request luôn được authorize đúng N lần”.

### 4.2. Chọn SecurityFilterChain ở mỗi lượt có thể khác

`FilterChainProxy` chọn `SecurityFilterChain` khớp theo request hiện hành. Nếu filter proxy được gọi trên một forward, path và dispatcher type của lượt forward có thể khiến **một chain khác** được chọn so với lượt REQUEST ban đầu.

Ví dụ:

```text
SecurityFilterChain A:
  securityMatcher("/api/**")
SecurityFilterChain B:
  fallback (mọi đường khác)

REQUEST /api/report
  -> chain A

FORWARD /WEB-INF/views/report.jsp
  -> có thể chọn chain B khi proxy được gọi lại
```

Một `anyRequest().denyAll()` trong chain A **không bao phủ** `/WEB-INF/views/report.jsp` nếu lượt ấy không khớp chain A. Ngược lại, chain B có thể xử lý đích forward bằng quy tắc chặt hơn dự kiến. Phải kiểm tra cả **filter registration, securityMatcher, thứ tự chain** và rule trong chain thực sự được chọn.

Không dùng suy luận “đã qua chain A nên chain B không quan trọng” hoặc “mọi chain đều chạy cộng dồn”. Trong một lần gọi `FilterChainProxy`, chain khớp đầu tiên được chọn.

### 4.3. Điều kiện `dispatcherTypeMatchers(...)`

Spring Security DSL cho phép xét dispatcher type như một tiêu chí phân quyền:

```java
import static jakarta.servlet.DispatcherType.ERROR;
import static jakarta.servlet.DispatcherType.FORWARD;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(FORWARD, ERROR).permitAll()
    .requestMatchers("/app/orders").authenticated()
    .anyRequest().denyAll()
);
```

Đây là **đoạn cấu hình minh họa** đúng kiểu API Spring Security Servlet 6.x. Nó cho phép mọi lượt `FORWARD` và `ERROR` mà authorization matcher nhìn thấy, giúp nhiều ứng dụng MVC render view hoặc trang lỗi mà không bị deny ngoài ý muốn.

**Nhưng đây không phải lời khuyên dùng đại trà cho mọi hệ thống.** Rule `FORWARD` và `ERROR` rộng có thể cho phép một lượt chuyển tới handler nhạy cảm qua lớp request authorization. Nếu đích thực hiện dữ liệu nhạy cảm, phải có kiểm tra tại method/service/data và/hoặc thu hẹp rule đến những đích nội bộ đã được kiểm soát.

### 4.4. Một cấu hình thu hẹp theo đích forward

Ví dụ sau minh họa cách chỉ cho phép **forward tới một vùng view** và **error dispatch tới trang lỗi đơn giản**, trong khi mọi đường nghiệp vụ vẫn yêu cầu authority. Đây là **mã khung Spring Boot 3.x / Spring Security Servlet 6.x**, không chạy độc lập; cần cấu hình authentication, MVC mapping và view renderer tương ứng.

```java
import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
@EnableMethodSecurity
public class DispatchAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Chỉ là minh họa cho ứng dụng có servlet path như bên dưới.
        // Thực tế cần kiểm tra mapping của view resolver/container.
        RequestMatcher internalViewForward = request ->
            request.getDispatcherType() == DispatcherType.FORWARD
                && request.getServletPath()
                    .startsWith("/WEB-INF/views/");

        RequestMatcher errorPageDispatch = request ->
            request.getDispatcherType() == DispatcherType.ERROR
                && "/error".equals(request.getServletPath());

        http.authorizeHttpRequests(auth -> auth
            // Bảo vệ hành động nghiệp vụ trên mọi lượt dispatch
            // mà Spring Security thực sự xử lý.
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.POST, "/api/documents/**")
                .hasAuthority("document:write")
            .requestMatchers(HttpMethod.GET, "/admin/**")
                .hasAuthority("admin:read")

            // Chỉ mở phạm vi render view và trang lỗi đã kiểm soát.
            .requestMatchers(internalViewForward).permitAll()
            .requestMatchers(errorPageDispatch).permitAll()

            .requestMatchers(HttpMethod.GET, "/app/home")
                .authenticated()
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Các điểm cần hiểu:

1. Route `/api/documents/**` và `/admin/**` được khai báo trước những nhánh ngoại lệ. Nếu có forward tới một route nghiệp vụ thuộc các matcher đó, authority tương ứng vẫn được kiểm tra.
2. `internalViewForward` yêu cầu đồng thời **dispatcher type là FORWARD** và đường đích nằm trong vùng view đã định. Request trực tiếp kiểu `REQUEST` đến đường ấy không được nhánh này cho phép.
3. `errorPageDispatch` chỉ chọn `ERROR` tới `/error`. Nó không cho mọi request bên ngoài tới `/error` bằng cùng quy tắc.
4. `anyRequest().denyAll()` đóng những trường hợp chưa được phân loại.
5. Ví dụ dựa vào `getServletPath()` cho view; nếu servlet mapping khác, giá trị này có thể khác. Phải kiểm thử bằng request thực. Việc cấp quyền cho vùng view chỉ hợp lý nếu view **không tự thực thi hành động nghiệp vụ nhạy cảm**.
6. Nếu trong ứng dụng có nhiều `SecurityFilterChain`, quy tắc này phải được đặt vào chain thực sự bao phủ lượt forward/error, hoặc có fallback bảo vệ. Nó không sửa được thiếu coverage ở cấp `FilterChainProxy`.

**Giới hạn:** chỉ sử dụng `getServletPath().startsWith(...)` trong snippet như một minh họa rõ về ý định; trong ứng dụng thực hãy kiểm tra path normalization, encoded URL, servlet mapping và loại view. Ưu tiên matcher tương thích router/container. Không cho phép nội dung nghiệp vụ nhạy cảm được thực thi chỉ vì một tài nguyên được đặt dưới thư mục tên `views`.

### 4.5. Vì sao rule quá rộng có thể nguy hiểm?

Giả sử:

```text
FORWARD /any-path -> permitAll
REQUEST /admin/delete -> hasRole(ADMIN)
```

Nếu tồn tại một controller công khai có thể điều khiển đích forward và nó forward tới handler `/admin/delete`, lượt FORWARD có thể đi qua rule `permitAll`, trong khi tác vụ nhạy cảm cần admin. Khi dùng broad forward permit, chỉ an toàn khi **không có đường điều khiển đích tùy ý** và **service/data vẫn áp chính sách độc lập**, cùng những ranh giới khác.

Không giả định endpoint nội bộ không thể bị gọi chỉ vì client không nhìn thấy đường forward. Kiểm tra quyền phải dựa vào danh tính và hành động, không dựa vào việc đường gọi là “nội bộ”.

## 5. `OncePerRequestFilter` và việc tránh xử lý trùng lặp

Tên `OncePerRequestFilter` dễ tạo ngộ nhận rằng filter này chỉ chạy đúng một lần trong mọi hoàn cảnh. Thực tế, đây là lớp cơ sở trong Spring Framework thiết kế để kiểm soát việc thực thi filter trong một lượt xử lý request, với cơ chế marker attribute; hành vi ở các dispatcher khác còn chịu ảnh hưởng của đăng ký filter và các phương thức cấu hình.

Các điểm cần nhớ:

- Filter có thể được container gọi theo `REQUEST`, `FORWARD`, `ERROR`, `ASYNC` tùy đăng ký dispatcher type.
- Với một lần xử lý đang diễn ra, cơ chế “already filtered” tránh thực thi logic `doFilterInternal` trùng trong cùng điều kiện mà lớp cơ sở bảo vệ.
- `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()` giúp điều chỉnh filter có bỏ qua các lượt async/error hay không. Mặc định thông dụng là bỏ qua.
- Không suy ra việc đăng ký filter với nhiều dispatcher type sẽ khiến filter tự xử lý hết; hai lớp điều kiện (registration và logic filter) đều có tác dụng.
- Không dùng tên “OncePerRequest” để kết luận authorization manager hoặc một filter khác cũng chỉ được đánh giá đúng một lần.

Đặc biệt, **`AuthorizationFilter` không thể được đánh đồng với `OncePerRequestFilter`**. Spring Security có thể đánh giá quyền cho nhiều lượt dispatch khi nó tham gia chúng, còn một custom filter kế thừa `OncePerRequestFilter` có hành vi riêng.

### 5.1. Mã minh họa filter có điều kiện async/error

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.web.filter.OncePerRequestFilter;

public class CorrelationFilter extends OncePerRequestFilter {
    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        try {
            // Đọc/tạo request correlation ID đã được kiểm soát
            // và thiết lập ngữ cảnh log phù hợp.
            chain.doFilter(request, response);
        } finally {
            // Dọn ngữ cảnh trên luồng đang xử lý.
        }
    }
}
```

Đây chỉ là **khung mã tích hợp**: chưa đăng ký filter và chưa triển khai logger/correlation ID. Trả `false` không đủ để buộc filter chạy nếu container không đăng ký nó cho dispatcher type tương ứng. Đừng biến filter quan sát thành điểm cấp quyền dựa trên header thô. Khi chạy bất đồng bộ, phải xử lý đúng cleanup ở từng thread và tránh ghi đè/dùng nhầm ngữ cảnh log.

### 5.2. Cảnh báo logic chạy nhiều lần

Một filter quan sát hoặc một handler bị chạy thêm do dispatch có thể:

- Tăng counter hoặc ghi log nhiều lần cho một HTTP request client.
- Ghi audit “đã xử lý” nhiều lần khi chỉ thực sự có một quyết định nghiệp vụ.
- Thêm header nhiều lần hoặc tạo correlation ID mới khiến trace bị đứt.
- Gọi logic nghiệp vụ không idempotent nếu cấu hình sai (điều này cần đặc biệt tránh).

Không giải quyết bằng một biến static `alreadyProcessed` toàn cục; biến đó có thể làm các request hợp lệ khác ảnh hưởng lẫn nhau. Cần xác định **cấp nào đang đếm**: một lượt dispatch, một HTTP request client, một giao dịch nghiệp vụ hay một lệnh có idempotency key.

## 6. Async: “request được dispatch lại” khác với “job chạy thread khác”

### 6.1. Async Servlet dispatch

Trong Servlet async, một request có thể gọi `startAsync()`, tạm nhả thread ban đầu, tiếp tục công việc và dispatch lại qua `AsyncContext.dispatch(...)`. Lượt được dispatch lại có `DispatcherType.ASYNC`. Các filter được đăng ký cho async có thể tham gia một lần xử lý khác.

Việc thread đổi khiến `SecurityContextHolder` quan trọng: chiến lược mặc định trong Servlet thường dùng `ThreadLocal`, nên không tự tin rằng security context sẽ hiện diện trong mọi callback/thread tùy ý. Spring Security có cơ chế tích hợp với Spring MVC async và các wrapper truyền security context, nhưng vẫn cần hiểu đúng phiên bản, cách sử dụng và các điểm kiểm tra quyền.

### 6.2. Không đồng nhất ba kiểu xử lý

| Tình huống | Bản chất | Có phải `ASYNC` redispatch không? |
| --- | --- | --- |
| Servlet `AsyncContext.dispatch()` | Lượt dispatch lại trong vòng đời một HTTP request | Có |
| Spring MVC async `Callable`/`DeferredResult` | Xử lý HTTP bất đồng bộ, có tích hợp Servlet/framework | Có thể dẫn đến async dispatch theo cơ chế framework |
| `@Async`, executor, `CompletableFuture` hoặc queue job độc lập | Công việc chạy trên thread/worker khác | Không mặc định là Servlet ASYNC dispatch |
| Client gửi request HTTP tiếp theo | Một request mới | Không |

Điểm này rất quan trọng với authorization: **message consumer hoặc scheduled job không tự đi qua Spring Security HTTP filter**, và thường không có cùng principal với request đã kích hoạt công việc. Tác vụ nền phải có danh tính dịch vụ hoặc mô hình ủy quyền rõ, kiểm tra quyền tại service/data và quản lý thời hạn/thu hồi phù hợp.

### 6.3. Thời điểm kiểm tra quyền cho tác vụ kéo dài

Giả sử người dùng được phép yêu cầu xuất báo cáo lúc 10:00, nhưng công việc export chạy lúc 10:15 sau khi quyền bị thu hồi. Phải xác định chính sách: quyền được chụp tại lúc tạo job hay cần kiểm tra lại trước khi đọc dữ liệu và trước khi tải file? Không có câu trả lời mặc định của Servlet; đây là quyết định nghiệp vụ/an ninh của hệ thống.

Một thiết kế thường gồm:

1. Kiểm tra quyền tạo tác vụ.
2. Gắn task với principal/tenant và phạm vi đã xác minh, không tin payload thô.
3. Kiểm tra lại điều kiện cần thiết ở giai đoạn thực thi dựa trên quy định thời hạn/thu hồi.
4. Khi công việc tạo file, kiểm soát quyền truy cập file thành phẩm.
5. Ghi audit cho job và bảo đảm không dùng chéo tenant.

Supplier của `Authentication` trong authorization không tự đồng bộ quyền mới hoặc lan truyền context tới background thread.

## 7. ERROR dispatch: vì sao trang lỗi có thể bị 403?

Khi một controller ném exception, container có thể tạo một lượt `ERROR` để hiển thị error page, ví dụ `/error`. Nếu `AuthorizationFilter` được áp dụng ở lượt đó, rule `anyRequest().denyAll()` có thể từ chối `/error`. Người dùng sẽ thấy một kết quả HTTP khó hiểu, và log có thể chứa cả exception gốc lẫn một lỗi phân quyền tại trang lỗi.

Tài liệu Spring Security chỉ rõ đây là tình huống thường gặp. Có thể cho phép các error dispatch cần thiết, nhưng phải hiểu phạm vi:

- Một error handler chỉ trả mã lỗi hoặc trang tĩnh không bí mật thường có thể được cho phép.
- Error handler có hiển thị dữ liệu nghiệp vụ hoặc truy vấn tài nguyên người dùng vẫn cần bảo vệ dữ liệu.
- Không dùng error dispatch như cách đưa nội dung tài nguyên bị cấm vào body lỗi.
- Không trả thông tin stack trace, session token, SQL hoặc dữ liệu định danh nhạy cảm tới client.

Các Servlet request attribute chuẩn như `RequestDispatcher.ERROR_STATUS_CODE`, `ERROR_REQUEST_URI` và `ERROR_EXCEPTION` có thể giúp xác định lỗi gốc; cần xử lý và log phù hợp, không lộ ra response. Nếu error page lại phát sinh exception, cần tránh vòng xử lý lỗi khó chẩn đoán.

### 7.1. `FORWARD` và `ERROR` được phép rộng có thể phù hợp khi nào?

Trong một ứng dụng MVC chỉ forward tới view template không có thao tác dữ liệu nhạy cảm, hoặc error handler luôn xuất trang lỗi an toàn, cấu hình `dispatcherTypeMatchers(FORWARD, ERROR).permitAll()` có thể đơn giản và phù hợp. Tuy nhiên, điều kiện quyết định phải được kiểm chứng:

- Có forward theo URL đích do người dùng ảnh hưởng không?
- Đích có thể là controller thực hiện thao tác nhạy cảm không?
- Method security và object policy có chặn được hành động không?
- Filter chain registration có áp dụng tới loại dispatch ấy không?
- Có thể điều chỉnh rule cho đúng đường view/error thay vì mở tất cả không?

**Bảo vệ theo dispatcher type không thay thế bảo vệ ở tầng nghiệp vụ.**

## 8. Chương trình Java 17 độc lập: mô phỏng những lượt dispatch và quyền

Ví dụ sau giúp trực quan hóa **lượt REQUEST được phép không có nghĩa lượt FORWARD tới tài nguyên nhạy cảm cũng được phép**. Nó là mô hình Java thuần, không triển khai filter container và không giả vờ mô phỏng chính xác mọi nội bộ Spring Security.

Lưu file `ServletRedispatchAuthorizationDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class ServletRedispatchAuthorizationDemo {
    enum Kind { REQUEST, FORWARD, INCLUDE, ERROR, ASYNC }

    record Principal(long id, long tenantId, Set<String> authorities) {}
    record Document(long id, long tenantId, long ownerId) {}
    record Dispatch(Kind kind, String method, String path) {}

    static boolean allowed(
            Dispatch dispatch,
            Principal principal,
            Document document) {

        if (dispatch == null || dispatch.kind() == null
                || dispatch.method() == null
                || dispatch.path() == null) {
            return false;
        }

        // Chỉ mở forward vào vùng view do server quản lý.
        if (dispatch.kind() == Kind.FORWARD
                && dispatch.path().startsWith("/WEB-INF/views/")) {
            return true; // Chỉ render, không thực thi nghiệp vụ.
        }

        // Chỉ mở error dispatch vào trang lỗi không có dữ liệu kín.
        if (dispatch.kind() == Kind.ERROR
                && "/error".equals(dispatch.path())) {
            return true;
        }

        // Endpoint trang bình thường cần user đã xác thực.
        if (dispatch.kind() == Kind.REQUEST
                && "GET".equals(dispatch.method())
                && "/app/home".equals(dispatch.path())) {
            return principal != null;
        }

        // Mọi dispatch tới API này đều phải thỏa quyền tài nguyên.
        if ("GET".equals(dispatch.method())
                && dispatch.path().matches("/api/docs/[0-9]+")) {
            return principal != null
                && principal.authorities() != null
                && principal.authorities().contains("doc:read")
                && document != null
                && principal.tenantId() == document.tenantId()
                && principal.id() == document.ownerId();
        }
        return false;
    }

    static void show(
            String label,
            Dispatch dispatch,
            Principal principal,
            Document document) {
        System.out.println(label + ": "
            + allowed(dispatch, principal, document));
    }

    public static void main(String[] args) {
        Principal owner =
            new Principal(10, 1, Set.of("doc:read"));
        Principal stranger =
            new Principal(20, 1, Set.of("doc:read"));
        Document doc = new Document(7, 1, 10);

        show("initial home request",
            new Dispatch(Kind.REQUEST, "GET", "/app/home"),
            owner, null);

        show("forward to safe view",
            new Dispatch(
                Kind.FORWARD, "GET", "/WEB-INF/views/home.jsp"),
            null, null);

        show("forward to private api anonymous",
            new Dispatch(Kind.FORWARD, "GET", "/api/docs/7"),
            null, doc);

        show("direct private api owner",
            new Dispatch(Kind.REQUEST, "GET", "/api/docs/7"),
            owner, doc);

        show("forward to private api owner",
            new Dispatch(Kind.FORWARD, "GET", "/api/docs/7"),
            owner, doc);

        show("forward to private api stranger",
            new Dispatch(Kind.FORWARD, "GET", "/api/docs/7"),
            stranger, doc);

        show("error page dispatch",
            new Dispatch(Kind.ERROR, "GET", "/error"),
            null, null);

        show("error into private api",
            new Dispatch(Kind.ERROR, "GET", "/api/docs/7"),
            null, doc);

        show("async resume owner",
            new Dispatch(Kind.ASYNC, "GET", "/api/docs/7"),
            owner, doc);

        show("async resume without context",
            new Dispatch(Kind.ASYNC, "GET", "/api/docs/7"),
            null, doc);

        show("include private api anonymous",
            new Dispatch(Kind.INCLUDE, "GET", "/api/docs/7"),
            null, doc);

        // Chỉ mô phỏng idempotency trong bộ nhớ, không phải DB thật.
        Set<String> processed = new HashSet<>();
        System.out.println("first operation: "
            + processed.add("operation-1"));
        System.out.println("repeated operation: "
            + processed.add("operation-1"));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac ServletRedispatchAuthorizationDemo.java
java ServletRedispatchAuthorizationDemo
```

Kết quả stdout dự kiến:

```text
initial home request: true
forward to safe view: true
forward to private api anonymous: false
direct private api owner: true
forward to private api owner: true
forward to private api stranger: false
error page dispatch: true
error into private api: false
async resume owner: true
async resume without context: false
include private api anonymous: false
first operation: true
repeated operation: false
```

Diễn giải:

1. Trang home hợp lệ cho người đã đăng nhập.
2. Lượt `FORWARD` tới view được cho phép nhờ **đích đã định**, không phải nhờ loại dispatch nói chung.
3. Forward tới API tài liệu với principal thiếu hoặc không phải owner đều bị từ chối. Owner được phép ở cả `REQUEST` và `FORWARD` vì mọi điều kiện tài nguyên đều đúng.
4. `ERROR /error` được phép để hiển thị lỗi không nhạy cảm; lỗi được dispatch tới API tài liệu không vì vậy được quyền đọc tài liệu.
5. Lượt `ASYNC` chỉ được vào tài liệu nếu còn danh tính và quyền phù hợp trong bối cảnh mà policy đang đánh giá; điều này không bảo đảm framework thật tự truyền context.
6. Set bảo đảm cùng key không được thêm hai lần **trong chương trình này**. Trong hệ thống thật, một `HashSet` không phải cơ chế idempotency bền vững qua nhiều process hay transaction. Phải dùng khóa nghiệp vụ/unique constraint hoặc cơ chế xử lý lặp thích hợp.

Không lấy số lần in log trong demo làm số lượt authorization bắt buộc của Spring Security. Số lượt filter thực tế phụ thuộc dispatcher mapping/container.

## 9. “Request được thực thi lại” còn có thể là client retry hoặc replay

Cụm “request được thực thi lại” có thể ám chỉ hai hiện tượng khác nhau:

**A. Redispatch trong cùng request:** `FORWARD`, `ERROR`, `ASYNC`, `INCLUDE` là các lượt xử lý trong vòng đời Servlet request theo cơ chế của container.

**B. Request mới hoặc retry:** client gửi lại `POST /api/payments` sau timeout; trình duyệt reload, proxy retry, người dùng bấm nút hai lần; message queue gửi lại tác vụ. Đây thường là **yêu cầu hoặc sự kiện độc lập**, không phải một lượt `DispatcherType.FORWARD`. Nó phải được **xác thực và phân quyền lại** theo cơ chế áp dụng, và phải chống thực hiện giao dịch hai lần.

### 9.1. Idempotency khác với forward permission

Với API nhạy cảm như thanh toán, hủy đơn hoặc tạo tài khoản:

- Quyền của caller phải được kiểm tra ở mỗi request thực thi, kể cả request retry.
- Trùng lặp phải được phát hiện theo **idempotency key** hoặc khóa nghiệp vụ được thiết kế rõ (kèm principal/tenant, nội dung request và thời hạn thích hợp).
- Cơ sở dữ liệu cần constraint/transaction để hai request đến đồng thời không cùng ghi side effect.
- Trạng thái và version của tài nguyên phải được kiểm tra tại lúc thực thi.
- Với hệ thống bên ngoài (cổng thanh toán, email), cân nhắc outbox, idempotent downstream API hoặc đối soát; DB transaction không tự hoàn tác được tác động bên ngoài.

Đừng chỉ dùng request attribute “processed=true” để chống retry qua hai HTTP request khác nhau: mỗi request mới có đối tượng và vòng đời khác. Cũng đừng cho rằng một filter chạy “once per request” ngăn thao tác nghiệp vụ bị gửi lại.

### 9.2. TOCTOU khi quyền hoặc tài nguyên đổi giữa các lượt

Nếu một handler kiểm tra quyền rồi chờ bất đồng bộ, dữ liệu có thể đổi trước khi ghi. Ví dụ tài liệu đang DRAFT lúc bắt đầu nhưng được phê duyệt trong thời gian chờ; khi resume, thao tác sửa DRAFT phải được kiểm tra lại hoặc thực thi bằng cập nhật có điều kiện.

Tùy rủi ro, dùng version/optimistic locking, khóa bi quan, điều kiện `UPDATE ... WHERE status = 'DRAFT'`, transaction và kiểm tra số dòng tác động. Không coi việc “đã authorize ở REQUEST” là bằng chứng trạng thái dữ liệu vẫn hợp lệ sau một khoảng chờ.

## 10. Thiết kế và kiểm thử theo ma trận dispatch

### 10.1. Ma trận bắt buộc

| Tình huống | Dispatcher type / cơ chế | Kỳ vọng bảo vệ |
| --- | --- | --- |
| Người hợp lệ truy cập trang | `REQUEST` | Cho vào route nếu đủ quyền |
| MVC forward sang view tĩnh | `FORWARD` | Render nếu đích view được phép |
| Request trực tiếp vào `/WEB-INF/views/...` | `REQUEST` | Không vì rule forward mà được truy cập |
| Forward sang API nhạy cảm | `FORWARD` | Không vượt qua method/object policy |
| Trang lỗi của endpoint thông thường | `ERROR` | Có thể hiển thị lỗi đã kiểm soát |
| ERROR dispatch tới handler nhạy cảm | `ERROR` | Không coi ERROR là quyền truy cập tài nguyên |
| Include fragment hiển thị | `INCLUDE` | Không lộ dữ liệu nhạy cảm từ fragment |
| Async resume với principal đúng | `ASYNC` | Theo quyền và dữ liệu còn hợp lệ |
| Async callback không có context | Luồng/background | Không mặc định cho phép |
| Redirect tới trang admin | Request HTTP mới | Phải xác thực/phân quyền đích |
| Client retry cùng POST | Request HTTP mới | Kiểm tra quyền và idempotency |
| Proxy tự retry khi timeout | Request mới/replayed | Không tạo tác động lặp |
| Session/JWT hết hiệu lực giữa các request | Request tiếp theo | Quyền mới/thu hồi theo chính sách |
| Hai request đồng thời | Hai luồng/giao dịch | Constraint và transaction nhất quán |

Kết quả 403 không tự chứng minh “đúng dispatch đã bị chặn”: có thể thiếu CSRF, sai `SecurityFilterChain` hoặc thiếu authentication. Phải cô lập điều kiện cần kiểm thử.

### 10.2. Test riêng Spring Security rule

Với Spring Security Test và Spring MVC `MockMvc`, test đầu tiên cần kiểm tra:

1. Người thiếu quyền vào `/api/documents/7` bị chặn.
2. Người đủ authority nhưng không phải owner bị từ chối tại service/repository.
3. Route được phép render view không bị lỗi forward do rule chưa khai báo.
4. Direct request tới đường view/đường lỗi không vô tình có quyền như internal dispatch.
5. Thay đổi dispatcher type, path và principal dẫn tới quyết định dự kiến.
6. Endpoint error không làm lộ chi tiết exception/secret.

Ví dụ **đoạn code đặt trong lớp test đã có `MockMvc`, controller và fixture**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Fixture: /api/documents/7 được bảo vệ bằng document:read.
mockMvc.perform(get("/api/documents/7")
        .with(user("viewer").authorities(
            new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().is2xxSuccessful());
```

Cần import `org.springframework.security.core.authority.SimpleGrantedAuthority`. Đoạn này **không phải file biên dịch độc lập** và 2xx chỉ đúng nếu user có quyền trên document 7 theo fixture thực tế. Không dùng test này để khẳng định filter re-run ở lượt `FORWARD` hoặc `ASYNC`; một số hành vi Servlet container không được mô phỏng đầy đủ bằng test MVC đơn thuần.

### 10.3. Kiểm thử dispatcher type bằng MockHttpServletRequest

Để **unit test riêng một matcher** dựa trên `DispatcherType`, có thể tạo request giả:

```java
import jakarta.servlet.DispatcherType;
import org.springframework.mock.web.MockHttpServletRequest;

MockHttpServletRequest req =
    new MockHttpServletRequest("GET", "/WEB-INF/views/home.jsp");

req.setServletPath("/WEB-INF/views/home.jsp");
req.setDispatcherType(DispatcherType.FORWARD);

boolean internalView = req.getDispatcherType()
        == DispatcherType.FORWARD
    && req.getServletPath().startsWith("/WEB-INF/views/");

// internalView == true với dữ liệu mock này.
```

Điều này chứng minh **logic matcher** trên dữ liệu request giả. Nó không chứng minh container thực sự gọi `springSecurityFilterChain` ở forward, không chứng minh SecurityContext được truyền đúng, và không chứng minh view không gây side effect.

Cần thêm test tích hợp bằng embedded servlet container hoặc cấu hình dispatch thật khi muốn chứng minh vòng đời filter/dispatch. Với Spring Security, xác minh bean filter được đăng ký cho các `DispatcherType` cần thiết và quan sát các lượt thực thi thực tế.

### 10.4. Test filter đăng ký và log

Trong môi trường test/staging có logging bảo mật phù hợp, quan sát tối thiểu:

- Correlation ID của request client.
- `DispatcherType` của từng lượt.
- Method và path ở lượt hiện hành, nếu cần cả original URI trong attribute chuẩn.
- Chain và rule được chọn (tránh log dữ liệu mật).
- Principal đã xác minh/authority ở mức tối thiểu, quyết định ALLOW/DENY.
- Một giao dịch nghiệp vụ có thực hiện side effect hay không.

Nếu một request client tạo hai dòng log authorization, đó có thể là hành vi đúng. Nếu một hành động nghiệp vụ làm hai khoản thanh toán, đó thường là lỗi nghiêm trọng. Không thể suy ra tình trạng dữ liệu chỉ từ số lượng log filter.

### 10.5. Test response commit và lỗi lồng nhau

Kiểm tra rằng forward diễn ra trước khi response commit. Khi handler đã flush response, việc forward có thể không hợp lệ. Test trang lỗi xuất hiện khi handler ném exception hoặc gửi mã lỗi, và đảm bảo error handler không lại gọi endpoint cần quyền hoặc rơi vào vòng lỗi liên tục.

Nếu dùng AJAX/API trả JSON, có thể không cần forward tới view; một error response đúng cấu trúc thường dễ quản lý hơn. Phải thiết kế riêng quyền/error handling cho API và web view, thay vì dùng cùng rule rộng cho mọi kiểu client.

## 11. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tưởng `REQUEST` là toàn bộ vòng đời | Bỏ qua `FORWARD/ERROR/ASYNC` | Vẽ luồng theo dispatcher type |
| Chặn toàn bộ forward vô tình | MVC view render 403 | Định nghĩa chính sách cho view đích và kiểm thử |
| `permitAll()` mọi FORWARD | Có thể bypass HTTP authorization của đích nhạy cảm | Thu hẹp đích hoặc giữ chốt nghiệp vụ đáng tin |
| `permitAll()` ERROR trên handler có dữ liệu kín | Lộ dữ liệu hoặc trạng thái không mong muốn | Chỉ mở error view an toàn |
| Cho rằng filter luôn được gọi ở mọi dispatch | Kỳ vọng kiểm tra không tồn tại | Xác minh dispatcher registration và filter behavior |
| Cho rằng `OncePerRequestFilter` nghĩa chính xác một lần mãi mãi | Bỏ qua async/error và double invocation | Hiểu marker và các phương thức shouldNotFilter |
| Đặt quyền trên request attribute tự khai | Fake tenant/user qua header | Dùng Authentication và membership đã xác minh |
| Dùng `FORWARD_REQUEST_URI` để cho phép đích | Client tác động URL nguồn rồi forward vào đích khác | Quyền theo đích và tài nguyên thực |
| Quên fallback SecurityFilterChain | Forward/error chọn đường ngoài chain | Bao phủ mọi route và dispatch phù hợp |
| Giữ `SecurityContextHolder` trong thread async tùy ý | Mất hoặc dùng nhầm principal | Truyền context có kiểm soát, thiết kế task identity |
| Ghi side effect trong view/filter | Một dispatch thêm có thể ghi lặp | Tách nghiệp vụ khỏi render/filter |
| Cho rằng retry là FORWARD | Không chặn duplicate POST | Idempotency và transaction bền vững |
| Test chỉ response 403 | Không biết chặn bởi CSRF hay authorization | Cô lập nguyên nhân, kiểm dữ liệu sau request |
| Ghi log mỗi dispatch như mỗi giao dịch | Sai số audit/metric | Tách request ID, dispatch ID, business operation ID |
| Gọi forward sau response commit | IllegalStateException hoặc lỗi trả response | Chuyển tiếp trước khi flush/commit |
| Chỉ check trạng thái ở REQUEST, ghi sau async | TOCTOU trên trạng thái/permission | Recheck/conditional write/version |

## 12. Bài tập thực hành

### Bài 1 — Vẽ đường đi của trang MVC

Với `GET /app/orders` trả view JSP `orders`, vẽ hai lượt `REQUEST` và `FORWARD`. Ghi rõ method, path, dispatcher type, SecurityFilterChain nào có thể khớp, lúc nào controller chạy và view nào render. Giải thích vì sao không nên ghi một sự kiện “đã duyệt đơn hàng” bên trong mã render view.

### Bài 2 — Sửa 403 ở forward

Một ứng dụng có `anyRequest().denyAll()`, chỉ cho phép `GET /app/orders`. View resolver forward tới `/WEB-INF/views/orders.jsp` và nhận 403. Đề xuất rule chỉ cho phép forward tới vùng view đã kiểm soát. Viết test đảm bảo request client trực tiếp vào vùng view không được cấp quyền theo rule đó.

### Bài 3 — Bảo vệ đích nhạy cảm

Một controller công khai nhận parameter `target` và forward tới đường do user nhập. Giải thích rủi ro khi dùng broad `FORWARD.permitAll()`. Thiết kế lại bằng whitelist đích cố định, method security và kiểm tra tenant ở service. Chứng minh forward vào API nhạy cảm không vượt được quyền.

### Bài 4 — Chạy Java 17

Chạy `ServletRedispatchAuthorizationDemo.java`. Đổi forward sang `/api/docs/7` bằng user khác tenant, thêm trường hợp forward sang `/WEB-INF/views/home.jsp` với dispatcher `REQUEST` và một redirect được mô hình hóa thành request mới. Dự đoán stdout rồi xác minh.

### Bài 5 — Async và security context

Tạo một endpoint trả `Callable` hoặc `DeferredResult`, ghi log có kiểm soát dispatcher type và principal. Xác minh security context trên các luồng liên quan trong cấu hình thực, sau đó kiểm tra quyền tại service. Thử quyền bị thu hồi khi job còn đang chờ để xác định policy hiệu lực.

### Bài 6 — Retry và idempotency

Giả lập client gửi `POST /api/payments` hai lần với cùng operation key. Dùng kho dữ liệu có ràng buộc duy nhất và trạng thái xử lý, chứng minh không thực hiện side effect hai lần. So sánh với việc chỉ dùng request attribute hoặc `HashSet` cục bộ và giải thích tại sao cách sau không đủ trong hệ thống nhiều instance.

## 13. Checklist triển khai

- [ ] Biết chính xác các dispatcher type mà Servlet filter và Spring Security filter tham gia.
- [ ] Đã phân biệt `REQUEST/FORWARD/INCLUDE/ERROR/ASYNC` với redirect và HTTP retry.
- [ ] Các đường đích forward phục vụ render không thực hiện hành động nghiệp vụ nhạy cảm.
- [ ] Các handler nhạy cảm có kiểm tra authority và quyền đối tượng ở service/data.
- [ ] `dispatcherTypeMatchers(...)` được dùng theo phạm vi đã review, không mở rộng tùy tiện.
- [ ] Các `SecurityFilterChain` bao phủ cả path/dispatch đích cần bảo vệ.
- [ ] `OncePerRequestFilter` được cấu hình phù hợp async/error và filter registration.
- [ ] Không dùng original URI, request attribute hoặc header thô để cấp quyền.
- [ ] Async/background work có mô hình principal/context/tenant rõ ràng.
- [ ] Các thao tác không idempotent có cơ chế chống replay/retry ở tầng dữ liệu.
- [ ] Test đầy đủ original request, forward, error, async và đường trực tiếp vào view/handler.
- [ ] Log có correlation ID cho request, dispatch và nghiệp vụ; không lộ secret.
- [ ] Có kiểm soát trạng thái/phiên bản tại lúc thực thi sau chờ bất đồng bộ.

## 14. Tự kiểm tra cuối bài

1. **Forward có tạo HTTP request mới từ browser không?** Thông thường không; nó là chuyển tiếp server-side trong vòng đời request hiện tại.
2. **Redirect khác forward ở đâu?** Redirect trả 3xx yêu cầu client gửi request mới; forward là dispatch nội bộ với `DispatcherType.FORWARD`.
3. **Tại sao view JSP có thể nhận 403 sau controller được phép?** Vì lượt FORWARD có thể được `AuthorizationFilter` đánh giá với đường đích mới và thiếu rule phù hợp.
4. **Spring Security tự kiểm tra mọi dispatch trong mọi cấu hình container không?** Không thể khẳng định tuyệt đối; còn cần filter proxy được đăng ký/thực sự chạy cho dispatcher type ấy.
5. **Có nên mặc định cho phép mọi FORWARD?** Chỉ khi mô hình forward và lớp nghiệp vụ bảo đảm an toàn; nếu có handler nhạy cảm, cần rule hẹp và kiểm tra riêng.
6. **`FORWARD_REQUEST_URI` có phải bằng chứng được phép truy cập đích không?** Không. Đó là thông tin request gốc để tham khảo/debug.
7. **OncePerRequestFilter có đảm bảo không bao giờ chạy lại trong async/error không?** Không suy đoán từ tên; cần xem dispatcher registration và các phương thức shouldNotFilter.
8. **ASYNC dispatch có giống `@Async` background job không?** Không. Một bên là lượt dispatch của Servlet request, bên kia là tác vụ trên thread riêng có thể không còn request context.
9. **Client retry POST có `DispatcherType.FORWARD` không?** Không; đây thường là request HTTP mới, phải phân quyền và xử lý idempotency riêng.
10. **Vì sao không dùng request attribute `processed=true` để chặn thanh toán trùng giữa hai request?** Vì các request có vòng đời độc lập và có thể chạy nhiều instance; cần ràng buộc bền vững ở tầng dữ liệu/nghiệp vụ.
11. **Nếu service đã check quyền trước khi chờ async, có cần xét lại khi thực thi không?** Tùy chính sách, thời hạn và rủi ro, nhưng dữ liệu/phiên bản thay đổi phải được bảo vệ tại lúc thực thi.
12. **Có `admin:read` thì được xem tài liệu tenant khác qua forward không?** Không mặc định; object policy phải xét tenant/owner và phạm vi quyền thực tế.

**Ghi nhớ:** forward và redispatch cho thấy **một HTTP request không nhất thiết là một lượt xử lý duy nhất**. Bảo vệ đúng phải nhận ra dispatcher type, đích hiện hành, nguồn principal đáng tin, filter nào thực sự chạy và chính sách nghiệp vụ còn hiệu lực. Cho phép render view hoặc error page không đồng nghĩa cho phép thực hiện hành động nhạy cảm; còn retry từ client là một request mới cần kiểm soát quyền và idempotency riêng.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Authorize HTTP Requests / All Dispatches Are Authorized](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet Architecture và FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Framework – Servlet Filters / OncePerRequestFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Jakarta Servlet – RequestDispatcher](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/RequestDispatcher.html)
- [Jakarta Servlet – ServletRequest.getDispatcherType()](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/ServletRequest.html)