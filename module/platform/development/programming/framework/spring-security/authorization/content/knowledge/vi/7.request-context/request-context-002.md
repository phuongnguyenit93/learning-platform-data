# Endpoint lỗi và tránh vòng lặp từ chối khi chuyển sang /error

Trong ứng dụng Spring Boot dùng Spring Security, một lỗi `404` hoặc `500` đôi khi lại xuất hiện dưới dạng `401`/`403`, trình duyệt bị chuyển đến màn hình login, hoặc log ghi thêm một lần `AccessDeniedException` ở `/error`. Người phát triển có thể nghĩ rằng exception ban đầu gây lỗi authorization; thực tế, **request đầu tiên đã gặp lỗi, rồi quá trình hiển thị lỗi bị phân quyền lại và bị từ chối lần nữa**.

Vấn đề cốt lõi là **`DispatcherType.ERROR` và `DispatcherType.REQUEST` không đồng nhất**, dù cùng liên quan đến một lần người dùng gọi HTTP. Spring Security sử dụng `AuthorizationFilter` để kiểm tra quyền theo dispatch, còn Spring Boot Servlet thường dùng `/error` để hiển thị thông tin lỗi. Nếu `/error` hoặc `ERROR` dispatch bị một quy tắc `anyRequest().denyAll()`, `authenticated()` hay role-check khác chặn, người dùng có thể thấy kết quả sai và nhóm phát triển rơi vào vòng chẩn đoán sai hoặc chuỗi điều hướng lỗi.

Mục tiêu bài học: phân biệt **lỗi gốc** và **lỗi khi render trang lỗi**; biết khi nào nên cho phép `ERROR` dispatch, cấu hình sao cho `/error` không biến thành cửa sau, xử lý cả nhiều `SecurityFilterChain`, tránh custom error handler tự gây lỗi lại, và kiểm thử mã trạng thái/luồng dispatch một cách có chứng cứ. Ví dụ sử dụng **Spring Boot 3 / Spring Security 6 trên Servlet stack** (Java 17+), không áp dụng nguyên xi cho WebFlux reactive.

## 1. `/error` của Spring Boot là gì?

Trong ứng dụng **Spring MVC/Servlet** với error auto-configuration, Spring Boot cung cấp endpoint lỗi mặc định tại **`/error`** (thường qua `BasicErrorController`), đồng thời đăng ký đường xử lý lỗi cho Servlet container. Khi một request gây exception chưa được xử lý hoặc container cần hiển thị trang lỗi theo trạng thái, container có thể thực hiện **ERROR dispatch** tới endpoint này.

Ví dụ:

~~~text
GET /public/boom           DispatcherType.REQUEST
  |
  +-- Spring Security cho qua rule /public/**
  +-- Controller ném IllegalStateException
  |
  +-- Servlet container / Spring Boot error handling
       |
       v
       /error              DispatcherType.ERROR
          |
          +-- Spring Security có thể kiểm tra lại authorization
          +-- BasicErrorController tạo response lỗi phù hợp
~~~

Một số điểm cần hiểu chính xác:

- `/error` là **đường dẫn đích xử lý lỗi**, không tự động là bằng chứng rằng một client đã chủ động gọi `GET /error`.
- **`DispatcherType.ERROR`** biểu thị lượt dispatch nội bộ xử lý lỗi của Servlet container. Một request thường bắt đầu bằng **`DispatcherType.REQUEST`**.
- Request ERROR có thể mang những thuộc tính lỗi như `jakarta.servlet.error.status_code`, `jakarta.servlet.error.request_uri`, `jakarta.servlet.error.exception` và `jakarta.servlet.error.message`; các hằng tương ứng nằm trong `jakarta.servlet.RequestDispatcher`.
- Kết quả của `/error` có thể là JSON đối với API hoặc HTML đối với trình duyệt, phụ thuộc content negotiation và cấu hình, **không phải cứ là trang HTML**.
- Đường mặc định có thể đổi qua `server.error.path`. Một custom `ErrorController` hoặc `@ControllerAdvice` có thể thay đổi đường xử lý; không có nghĩa mọi exception đều phải qua cùng `/error`.
- Trong **Spring Boot 3**, Servlet API thuộc namespace **`jakarta.servlet`**, không phải `javax.servlet` của nhiều ứng dụng cũ.

Cần phân biệt **Spring Security `AccessDeniedHandler`** với **Spring Boot `BasicErrorController`**: một bên xử lý từ chối truy cập, bên kia là cách ứng dụng/trình chứa hiển thị lỗi. Hai cơ chế có thể nối tiếp nhau, nhưng không đồng nghĩa mọi câu trả lời 403 đều được điều hướng tới `/error`.

## 2. Vì sao một request có thể bị phân quyền nhiều lần?

Theo cơ chế `authorizeHttpRequests`, **`AuthorizationFilter`** có thể được gọi cho các lượt dispatch như `REQUEST`, `ERROR`, `FORWARD` (và những kiểu dispatch được cấu hình khác). Spring Security kiểm tra request hiện tại theo `RequestMatcher`/authority của chính lần dispatch đó. Nếu chính sách chỉ nghĩ tới URL gốc mà quên đường xử lý lỗi, request có thể trải qua hai quyết định khác nhau.

Ví dụ chính sách ban đầu:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

Giả sử `GET /public/boom` là endpoint public, nhưng controller ném exception chưa được xử lý:

~~~text
1. REQUEST /public/boom
   -> /public/** permitAll -> ALLOW, controller chạy
   -> controller ném exception

2. ERROR /error
   -> không match /public/**
   -> không match /api/admin/**
   -> anyRequest().authenticated()
   -> có thể DENY nếu ngữ cảnh lúc này không có Authentication hợp lệ

3. Client nhận kết quả từ lỗi thứ hai thay vì trang lỗi của exception gốc;
   log có thể cho thấy thêm lần AccessDeniedException/entry point.
~~~

Với `anyRequest().denyAll()`, lượt `ERROR /error` bị chặn **dù có Authentication** nếu không có rule đặc biệt. Với `authenticated()`, kết quả phụ thuộc trạng thái security context ở lần dispatch mới; không nên mặc định luôn được giữ nguyên một cách phù hợp trong mọi setup, custom filter hay cơ chế token.

**Quan trọng:** “bị từ chối hai lần” chưa chắc là một **vòng lặp vô hạn**. Servlet container, response đã committed, cách `sendError`/forward, error page mapping và exception handling có thể giới hạn hoặc thay đổi số lượt dispatch. Biểu hiện thực tế có thể là 401/403 che 404/500, redirect đến login, log dài lặp lại hoặc một vòng redirect do custom error flow. Cần đo **`DispatcherType`** và đường dẫn ở từng bước, không tự khẳng định có recursion vô hạn chỉ dựa vào nhiều dòng log.

## 3. Quy tắc được Spring Security khuyến nghị: cho phép `ERROR` dispatch

Trong một ứng dụng Spring Boot 3 / Spring Security 6 với một `SecurityFilterChain`, cách thường dùng để cho **container hiển thị lỗi** mà không mở toàn bộ đường dẫn thường là đặt rule dispatcher trước các rule chung:

~~~java
import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ErrorDispatchSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **mã cấu hình Spring**; cần `spring-boot-starter-security`, cơ chế authentication/user store và endpoint MVC tương ứng để sử dụng thực tế. Nó không phải chương trình Java độc lập chạy bằng `javac` với mỗi JDK.

**Ý nghĩa của dòng đầu tiên trong DSL:**

- `dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` kiểm tra **kiểu dispatch**, không dựa vào chuỗi `"/error"`. Nó cho phép lượt `ERROR` đi tiếp ở lớp **request authorization**.
- Một client HTTP thông thường gửi `GET /error` là `DispatcherType.REQUEST`, **không biến thành ERROR dispatch** chỉ vì URL chứa chữ `error`. Request trực tiếp vẫn phải theo các rule còn lại.
- Rule `/api/admin/**` vẫn yêu cầu `ROLE_ADMIN` đối với **REQUEST ban đầu**. Cho phép ERROR dispatch **không cho phép một người không có quyền truy cập controller quản trị** bằng cách đổi path.
- `anyRequest().authenticated()` tiếp tục bảo vệ các endpoint còn lại trong chain. Nếu muốn chính sách allowlist chặt, có thể dùng `anyRequest().denyAll()` rồi khai báo các URL được phép; nhưng cần cân nhắc hành vi 404 của URL chưa đăng ký.

**Dòng `dispatcherTypeMatchers` phải được đặt trước** các rule bao quát, đặc biệt `anyRequest()`. Các matcher được đánh giá theo thứ tự: rule phù hợp đầu tiên quyết định. Đặt `anyRequest().authenticated()` hoặc `anyRequest().denyAll()` trước rule ERROR sẽ khiến rule ERROR không còn cơ hội áp dụng.

### Có cần permit `DispatcherType.FORWARD` luôn không?

Tài liệu Spring Security cũng đưa ví dụ cho phép cả `FORWARD` lẫn `ERROR`, vì một MVC view hoặc JSP có thể được render bằng forward và gặp kiểm tra authorization lần thứ hai.

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Đây là **phương án mở rộng có điều kiện**, không phải yêu cầu bắt buộc cho mọi hệ thống. Nếu ứng dụng không cần FORWARD, **chỉ permit ERROR** giúp phạm vi ngoại lệ hẹp hơn. Cho phép tất cả FORWARD nghĩa là các chuyển tiếp nội bộ được bỏ qua kiểm tra authorization ở lớp HTTP theo kiểu dispatch; không dùng nó nếu chính sách dựa vào việc kiểm tra quyền tại đích forward hoặc có nhiều Servlet nhạy cảm. Trong môi trường dùng template/view, có thể chỉ permit một đường view/error có matcher phù hợp thay vì mở tất cả FORWARD.

Lưu ý `@ControllerAdvice` có thể trả response lỗi trực tiếp mà **không** thực hiện ERROR dispatch của container; trong trường hợp đó rule ERROR không được dùng. Cần hiểu thực tế request đi qua cơ chế xử lý lỗi nào.

## 4. `dispatcherTypeMatchers(ERROR)` khác `requestMatchers("/error")` như thế nào?

Có hai cách thường thấy để đảm bảo trang lỗi không bị block:

~~~java
// Hướng A: cho phép những lượt dispatch do container đánh dấu ERROR.
.dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
~~~

và

~~~java
// Hướng B: cho phép mọi request khớp URL /error,
// kể cả REQUEST trực tiếp từ client khi matcher khớp.
.requestMatchers("/error").permitAll()
~~~

Chúng **không tương đương**:

| Tình huống | Hướng A: dispatcher ERROR | Hướng B: URL `/error` |
| --- | --- | --- |
| `ERROR /error` do container chuyển tới | ALLOW ở authorization | ALLOW nếu path match. |
| `REQUEST /error` do browser chủ động gửi | Phải theo rule còn lại | Được cho phép tại rule `/error`. |
| ERROR dispatch tới đường lỗi tùy chỉnh như `/system/error-page` | Có thể ALLOW theo dispatcher type | Không match `/error` nếu không đổi rule. |
| FORWARD tới `/error` | Không được miễn bởi rule chỉ ERROR | Có thể ALLOW vì URL match, dù dispatcher là FORWARD. |
| Đích lỗi đổi bởi `server.error.path` | Không phụ thuộc tên `/error` | Cần cập nhật matcher theo đường mới. |
| Mức độ giới hạn theo path | Cho phép mọi ERROR dispatch trong chain | Cho phép path `/error` bất kể dispatcher nếu khớp. |

**Khuyến nghị mặc định:** dùng **rule theo `DispatcherType.ERROR`** để giải quyết chính xác vấn đề redispatch khi bị từ chối trang lỗi, vì nó không tự công khai truy cập `/error` qua REQUEST thông thường. Tuy nhiên, đây **không phải một quy tắc tuyệt đối**: trong hệ thống có nhiều servlet, error path đặc biệt hoặc điều kiện bảo mật nội bộ cho error dispatch, cần xem mục tiêu trước khi mở rộng.

Việc cho phép **lớp authorization** không có nghĩa không cần kiểm soát **dữ liệu mà error page hiển thị**. Trang lỗi phải được thiết kế không lộ stack trace, token, request headers nhạy cảm hay thông tin của người dùng khác. Chính sách API đối với những endpoint bình thường vẫn áp dụng đầy đủ.

Nếu muốn cho phép chính xác **chỉ ERROR dispatch tới `/error`**, có thể dùng `RequestMatcher` kết hợp dispatcher type và path tại DSL; đổi lại bạn phải xác định đúng matcher path, context/servlet path và các tuyến lỗi phụ. Độ hẹp không phải lúc nào cũng an toàn hơn nếu matcher bỏ sót trang lỗi thật và lại dẫn tới masked status.

## 5. `/error` và lỗi 401/403/404/500: nguồn gốc khác nhau

Những kết quả HTTP xuất hiện gần nhau nhưng cần phân biệt:

| Tình huống | Cơ chế quyết định ban đầu | Kết quả thường thấy |
| --- | --- | --- |
| Người chưa xác thực gọi API cần đăng nhập | `AuthenticationEntryPoint` khi cần xác thực. | Với HTTP Basic/JWT thường **401**; form login có thể **302 redirect**. |
| Người đã xác thực thiếu authority | `AccessDeniedHandler` xử lý quyền bị từ chối. | Thường **403**. |
| Người có quyền gọi URL không có controller | Spring MVC / Servlet container không tìm thấy handler. | Thường **404** nếu request đã vượt qua security. |
| Controller ném exception không được xử lý | Container / Spring Boot error handling. | Thường **500** nếu không có handler biến đổi sang status khác. |
| `ERROR /error` lại bị rule bảo mật từ chối | Authorization trong lượt dispatch lỗi. | Có thể che status gốc bằng 401/403/redirect hoặc lỗi thứ cấp. |
| `@ControllerAdvice` bắt và trả response | MVC exception resolver. | Theo `ResponseEntity` hoặc `@ResponseStatus` của handler; có thể không qua /error. |

Đừng vội xem một response `403` là bằng chứng `@PreAuthorize` hoặc `hasRole` của request gốc hoạt động đúng. Nếu log cho thấy controller đã ném exception hoặc route không tồn tại rồi **`DispatcherType.ERROR` tới `/error`**, 403 có thể đến từ **trang lỗi bị chặn**, không phải permission của thao tác ban đầu.

Ngược lại, khi request bị từ chối từ `AuthorizationFilter` trong một luồng bình thường, `ExceptionTranslationFilter` có thể chuyển `AccessDeniedException` sang entry point hoặc access-denied handler. Handler có thể ghi status, `sendError`, forward đến trang khác hoặc trả JSON tùy cấu hình; **không phải mọi 401/403 đều chạy qua Boot `/error`**. Cần trace một request cụ thể thay vì suy từ con số.

### Vì sao lỗi 404 đôi khi được hiển thị như 401?

Giả sử người dùng anonymous gọi một đường public chưa có controller:

~~~text
GET /public/missing                  REQUEST
  `/public/**` permitAll -> vào MVC
  MVC không thấy mapping -> cần render 404
  Servlet container chuyển tới /error  ERROR
  `anyRequest().authenticated()` -> anonymous không đủ điều kiện
  AuthenticationEntryPoint -> phản hồi 401/redirect
~~~

Sau khi thêm `dispatcherTypeMatchers(ERROR).permitAll()`, `ERROR /error` có thể chạy đến error controller và trả **404 đúng với lỗi gốc**, miễn các filter khác, error controller và exception handler không can thiệp. **Không nên thay mọi response 404 bằng 401/403**; sẽ làm frontend, client và monitoring khó nhận biết nguồn lỗi.

Cũng cần hiểu chiều ngược lại: với chính sách `anyRequest().denyAll()`, một **REQUEST tới URL chưa có rule** có thể bị **403 ở bước security trước cả khi MVC kiểm tra có controller hay không**. Cho phép `ERROR` chỉ sửa việc hiển thị lỗi sau khi lỗi đã được hình thành; không biến các URL bị `denyAll` thành 404.

## 6. Các ranh giới bảo mật cần giữ khi cho phép ERROR

Cho phép `DispatcherType.ERROR` là **ngoại lệ phân quyền request**, không phải giấy phép bỏ toàn bộ hệ thống bảo vệ. Những ràng buộc cần giữ:

- **Không dùng `web.ignoring("/error")` như phản xạ.** `ignoring` bỏ qua Spring Security filter chain, bao gồm security headers và các filter bảo vệ được cấu hình; `permitAll` chỉ cho phép ở bước request authorization trong chain.
- **Không dùng `permitAll("/**")` để che lỗi 403.** Một thay đổi như vậy có thể công khai các API nghiệp vụ.
- **Không đưa xử lý nghiệp vụ nhạy cảm vào error controller.** Error handler nên tạo response lỗi, không thực hiện thao tác quản trị, gửi tiền, sửa trạng thái hoặc truy xuất dữ liệu tenant khác.
- **Không tin request-supplied error attributes.** Không hiển thị trực tiếp stack trace, cookie, token, query chứa PII hoặc exception message không được kiểm soát. Những thuộc tính lỗi của container nên được dùng để trả mã/trang thông báo an toàn, không để phân quyền nghiệp vụ.
- **Giữ các filter khác hoạt động** theo thiết kế: `permitAll(ERROR)` không tự tắt CSRF, authentication filters, JWT token validation, rate limit hoặc custom filters. Với custom filter, phải quyết định có xử lý `ERROR` dispatch hay không, không tự yêu cầu role trên endpoint lỗi.
- **Audit và observability:** phân biệt lỗi gốc với lỗi từ redispatch để tránh đếm đôi hoặc ghi sai thống kê. Với một user request gây 500, các log có thể ghi nhiều dispatch; correlating theo request ID và dispatcher type rất hữu ích.
- **Không xem status hoàn chỉnh là chắc chắn nguyên vẹn.** Nếu response gốc đã committed hoặc custom handler gửi body/status khác, việc cho phép ERROR không tự khôi phục nội dung đã ghi.

Trong Spring Boot có thể quản lý việc lộ chi tiết lỗi qua các cấu hình `server.error.include-message`, `server.error.include-stacktrace`, `server.error.include-binding-errors` và cơ chế error attribute tùy biến. Khi triển khai công khai, ưu tiên chỉ trả thông tin an toàn cho client, còn chi tiết kỹ thuật lưu log server có kiểm soát.

## 7. Nhiều `SecurityFilterChain`: rule ERROR phải nằm trong chain thật sự nhận /error

Một tình huống dễ đánh lừa: ứng dụng chia chain API và chain web:

~~~text
Chain @Order(1): securityMatcher("/api/**")
     -> JWT authentication / API authorization
Chain @Order(2): match mọi URL còn lại
     -> form login hoặc fallback authorization
~~~

Client gọi `GET /api/orders/42`; controller sinh lỗi. Nếu Servlet container thực hiện ERROR dispatch tới **`/error`**, path của lượt mới có thể **không còn thuộc `/api/**`**. Khi `FilterChainProxy` chọn chain cho `/error`, **fallback chain** sẽ là nơi áp dụng quy tắc; một `dispatcherTypeMatchers(ERROR).permitAll()` đặt **chỉ trong API chain** chưa chắc có tác dụng cho /error.

Ví dụ cấu hình hai chain theo hướng an toàn (minh họa cho Spring Security 6 + Servlet):

~~~java
import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainErrorSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

**Phạm vi ví dụ:** hai bean chain minh họa **selection và authorization**, chưa khai báo provider JWT, form login hay nguồn identity phù hợp; không dùng nguyên như ứng dụng production. API chain `securityMatcher("/api/**")`, fallback chain không có `securityMatcher` nên bao phủ request khác, trong đó có ERROR tới `/error`.

- `REQUEST /api/admin/users` → API chain, role ADMIN vẫn bắt buộc.
- `ERROR /error` sau lỗi API → thường vào fallback chain → rule `DispatcherType.ERROR` cho render lỗi.
- `REQUEST /error` do người ngoài gọi → fallback chain → `anyRequest().denyAll()`, không được công khai bởi ngoại lệ ERROR.
- `REQUEST /public/status` → fallback chain → public.
- `REQUEST /unknown` → fallback chain → DENY theo chính sách, dù MVC có thể không có handler.

Đặc biệt, **thứ tự chain (`@Order`) và thứ tự rule trong chain là hai tầng khác nhau**. `dispatcherTypeMatchers(ERROR)` chỉ áp dụng nếu chain chứa nó thực sự được chọn. Khi debug, xác định chain và filter nào đã chạy ở lượt ERROR, thay vì chỉ nhìn bean API ban đầu.

Nếu app dùng `server.error.path=/problem`, custom `ErrorController`, context path hoặc servlet prefix khác, hãy thử đúng path của error dispatch thực tế. Không tự động hard-code `/error` cho mọi deployment.

### Không dùng securityMatcher quá hẹp mà bỏ hẳn fallback

Nếu chỉ đăng ký API chain cho `/api/**` rồi không có fallback, `/error` có thể **không khớp chain nào**. Khi ấy lỗi có thể được render, nhưng request không đi qua Spring Security filter chain, làm mất security headers hoặc các cơ chế lọc tùy biến. **Đó không phải cách sửa khuyến nghị**. Nên thiết kế fallback chain bao phủ ứng dụng và cho phép ERROR dispatch ở mức cần thiết.

## 8. FORWARD tới trang lỗi tùy biến khác ERROR dispatch

Trong ứng dụng MVC, có thể có hai đường xử lý bị gộp nhầm:

~~~text
A. Container error:
   REQUEST /private/boom -> controller/servlet lỗi
   ERROR   /error         -> Boot error controller

B. AccessDeniedHandler chuyển tiếp đến trang truy cập bị từ chối:
   REQUEST /private/data  -> AccessDeniedException
   FORWARD /access-denied  -> view/controller do ứng dụng cấu hình
~~~

Với `AccessDeniedHandlerImpl` được cấu hình dùng error page, cơ chế có thể là **forward**, không phải ERROR dispatch đến Boot `/error`. Nếu bạn chỉ cho phép `ERROR`, trường hợp B có thể vẫn gặp một lần từ chối nữa ở `FORWARD`.

Chọn chiến lược dựa trên cách thiết kế error flow:

~~~java
// Phương án 1: cho phép cả hai kiểu dispatcher,
// chỉ sau khi kiểm tra FORWARD không dùng để né chính sách.
.dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
    .permitAll()
~~~

hoặc dùng matcher đủ cụ thể cho trang đích và kiểu dispatch:

~~~java
import org.springframework.security.web.util.matcher.DispatcherTypeRequestMatcher;
import jakarta.servlet.DispatcherType;

// Trong authorizeHttpRequests:
.requestMatchers(
    new DispatcherTypeRequestMatcher(DispatcherType.FORWARD, "/access-denied")
).permitAll()
~~~

Đoạn thứ hai minh họa **matcher cho dispatcher type + HTTP path**. Kiểm tra signature constructor, servlet-path handling và phiên bản cụ thể khi tích hợp vào project; không sao chép qua các thế hệ Spring mà không chạy test. Cũng có thể dùng `requestMatchers("/access-denied").permitAll()` nếu muốn trang lỗi công khai qua `REQUEST` nữa.

Với hầu hết ứng dụng API JSON, không nhất thiết phải forward đến view: một `AccessDeniedHandler` có thể trả status và JSON an toàn trực tiếp, không tạo đường thứ hai phải authorized. Với ứng dụng MVC server-side render, cần bảo đảm đúng đường tới template và static assets của trang lỗi.

## 9. Tránh vòng lặp thực do custom error handler

Một vấn đề khác với việc `AuthorizationFilter` chặn ERROR là **custom error controller / error view tự kích hoạt thêm lỗi**. Ví dụ:

- `/error` ném exception khi cố truy database chưa sẵn sàng.
- Trang lỗi phụ thuộc session/user profile nhưng request anonymous hoặc authentication context không còn phù hợp.
- Error handler gọi lại controller gốc hoặc dùng `return "forward:/error"`, tạo thêm lượt dispatch vào chính mình.
- Exception handler tái ném exception không được chuyển đổi và error mapping lại gọi đúng handler đó.
- Error page tải JS/CSS đang cần đăng nhập hoặc trỏ sai context path, làm màn hình lỗi không render đúng.
- Custom security filter cho mọi request (kể cả ERROR) gọi một service khiến chính nó ném lỗi; khi server điều hướng tới /error, filter lại ném lỗi.

Hạn chế rủi ro bằng cách thiết kế **trang lỗi tối giản và độc lập**:

1. **Trả response an toàn trực tiếp** (status, code, message được kiểm soát), không điều hướng tới chính `/error`.
2. **Không phụ thuộc business DB/cache/network** chỉ để render một lỗi không liên quan. Dùng fallback thông điệp chung khi dữ liệu không sẵn.
3. **Không yêu cầu đăng nhập tại ERROR dispatcher** cho việc hiển thị một lỗi chung, trừ khi có lý do đặc biệt và cơ chế fallback độc lập.
4. **Không hiển thị exception message/stacktrace không lọc**. Log server có correlation ID để tìm nguyên nhân.
5. **Dùng static assets tối thiểu** hoặc CSS inline an toàn nếu trang error phải hoạt động trong trạng thái ứng dụng suy giảm; không tạo truy cập vòng lặp qua asset private.
6. **Dừng sớm khi response đã committed** hoặc khi custom handler không còn khả năng xử lý status theo giao thức.
7. **Kiểm thử error handler khi mọi dependency phụ trợ không khả dụng**, nhất là service xác thực hoặc database.

Một custom error handler có nhiệm vụ **kết thúc chuỗi lỗi**, không được tự coi mình là nơi “thử lại” action nghiệp vụ. Nếu cần logic retry, hãy đặt trong cơ chế riêng có giới hạn số lần và bảo đảm idempotency, không tự forward lỗi vô hạn.

## 10. Khác biệt giữa `permitAll(ERROR)`, bỏ filter chain và tắt kiểm tra dispatcher

Có ba kiểu thay đổi dễ bị nhầm:

| Cách làm | Điều được thay đổi | Rủi ro/cần cân nhắc |
| --- | --- | --- |
| `dispatcherTypeMatchers(ERROR).permitAll()` | Chỉ bỏ yêu cầu authorization ở lượt ERROR trong chain đã chọn. | Các filter Spring Security khác vẫn có thể chạy; nên ưu tiên để sửa lỗi render. |
| `web.ignoring().requestMatchers("/error")` | Bỏ Spring Security filter chain cho URL ignore. | Mất headers và các filter Spring Security khác; cũng có thể áp dụng với REQUEST trực tiếp. |
| Thay đăng ký filter dispatcher types để **không chạy security filter chain** trên ERROR | Bỏ qua cả chuỗi Spring Security ở ERROR dispatch. | Phạm vi thay đổi rộng, ảnh hưởng headers/security context/filters; chỉ làm khi có phân tích kiến trúc rõ. |

**Không dùng việc tắt toàn bộ security chain trên ERROR để chữa một rule authorization thiếu.** Cách tối thiểu thường là đặt rule dispatcher phù hợp ở chain đúng. Tuy nhiên, `permitAll(ERROR)` **không tự miễn các filter khác**. Ví dụ một JWT authentication filter tùy chỉnh có thể cố bắt buộc token trên mọi dispatcher và trả 401 trước AuthorizationFilter; khi đó phải sửa phạm vi của *filter đó* hoặc cách nó xử lý ERROR, thay vì mở tất cả endpoint.

Với security headers, không thể mặc định mọi header có mặt trong mọi chain. `permitAll` giữ cơ hội chạy các header writer đã cấu hình; `ignoring` thì loại chúng khỏi luồng Spring Security. Header từ reverse proxy/gateway vẫn có thể tồn tại dù Spring Security bị bypass; cần test trên response thực.

## 11. Minh họa Java 17 độc lập: một ERROR dispatch không cấp quyền admin

Ví dụ sau **không dùng thư viện Spring**. Nó mô phỏng quyết định authorization đối với `REQUEST` và `ERROR`. Chính sách:

- `/api/admin/**` chỉ được truy cập nếu đã xác thực và có `ROLE_ADMIN`.
- `/public/status` luôn công khai.
- Đường còn lại yêu cầu người gọi đã xác thực.
- Nếu bật ngoại lệ `permitErrorDispatch`, bất kỳ `Dispatch.ERROR` nào được **cho đi tiếp tới error renderer** theo mô hình; **REQUEST ban đầu vẫn áp dụng đầy đủ rule bình thường**.

Lưu đúng tên tệp **`ErrorDispatchAuthorizationDemo.java`**:

~~~java
import java.util.Set;

public class ErrorDispatchAuthorizationDemo {
    enum Dispatch { REQUEST, ERROR, FORWARD }
    record Call(Dispatch dispatch, String path, boolean authenticated,
                Set<String> authorities) {}

    static boolean authorized(Call call, boolean permitErrorDispatch) {
        if (permitErrorDispatch && call.dispatch() == Dispatch.ERROR) {
            return true;
        }
        if (call.path().equals("/public/status")) {
            return true;
        }
        if (call.path().startsWith("/api/admin/")) {
            return call.authenticated()
                    && call.authorities().contains("ROLE_ADMIN");
        }
        return call.authenticated();
    }

    public static void main(String[] args) {
        Call anonymousAdmin = new Call(Dispatch.REQUEST, "/api/admin/users",
                false, Set.of());
        Call regularAdmin = new Call(Dispatch.REQUEST, "/api/admin/users",
                true, Set.of("ROLE_USER"));
        Call admin = new Call(Dispatch.REQUEST, "/api/admin/users",
                true, Set.of("ROLE_ADMIN"));
        Call errorPage = new Call(Dispatch.ERROR, "/error", false, Set.of());
        Call directErrorUrl = new Call(Dispatch.REQUEST, "/error", false, Set.of());
        Call publicPage = new Call(Dispatch.REQUEST, "/public/status",
                false, Set.of());

        System.out.println("Anonymous original admin: "
                + authorized(anonymousAdmin, true));
        System.out.println("User original admin: "
                + authorized(regularAdmin, true));
        System.out.println("Admin original admin: "
                + authorized(admin, true));
        System.out.println("ERROR /error before exception: "
                + authorized(errorPage, false));
        System.out.println("ERROR /error with exception: "
                + authorized(errorPage, true));
        System.out.println("REQUEST /error remains private: "
                + authorized(directErrorUrl, true));
        System.out.println("Public status: "
                + authorized(publicPage, true));
        System.out.println("Error exception cannot grant admin: "
                + authorized(regularAdmin, true));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 ErrorDispatchAuthorizationDemo.java
java ErrorDispatchAuthorizationDemo
~~~

Kết quả chuẩn:

~~~text
Anonymous original admin: false
User original admin: false
Admin original admin: true
ERROR /error before exception: false
ERROR /error with exception: true
REQUEST /error remains private: false
Public status: true
Error exception cannot grant admin: false
~~~

**Cách đọc kết quả:** Người dùng thường vẫn không có quyền admin, dù `permitErrorDispatch=true`; request truy cập `/api/admin/users` vẫn bị từ chối. Trong lượt ERROR đã xác định rõ dispatcher type, policy chỉ cho đi tiếp để hiển thị lỗi, không chuyển kết quả của request gốc thành thành công. `GET /error` trực tiếp là `REQUEST`, nên không được ưu ái theo exception ERROR.

`startsWith("/api/admin/")` trong chương trình là **mô hình minh họa với input đã biết**, không được sao chép làm `RequestMatcher` bảo mật trong production; Spring MVC/Servlet có quy tắc path, URL encoding và firewall riêng. Chương trình không thực thi Servlet error dispatch thật, không mô phỏng body/HTTP status của `BasicErrorController` và không thể thay thế integration test Spring.

## 12. Kiểm thử luồng lỗi thực, không chỉ assert `/error` trả 200

Một kiểm thử chỉ gọi `GET /error` từ MockMvc thường bắt đầu bằng dispatcher **`REQUEST`**, nên **không** kiểm tra tình huống container đã dispatch **`ERROR`**. Và khi app không có handler ở một đường khác, một test trả 401/403 chưa chắc chứng minh rule cho endpoint gốc đúng; có thể response bị mask.

Hãy chia kiểm thử thành ba lớp:

### A. Kiểm tra logic matcher theo dispatcher type

Trong unit/integration test có `spring-security-test`, dựng request với **`DispatcherType.ERROR`** được thiết lập rõ, không dựa vào tên URL:

~~~java
// Trích đoạn nằm trong test Spring MVC/Security có MockMvc,
// MockMvcRequestBuilders.get và jakarta.servlet.DispatcherType.
mvc.perform(get("/error")
        .with(request -> {
            request.setDispatcherType(DispatcherType.ERROR);
            request.setAttribute(
                RequestDispatcher.ERROR_STATUS_CODE, 500);
            request.setAttribute(
                RequestDispatcher.ERROR_REQUEST_URI, "/public/boom");
            return request;
        }));
// Sau đó assert dispatcher rule/response theo cấu hình thực tế.
// get("/error") đơn thuần sẽ là REQUEST, không phải ERROR.
~~~

Đoạn này cần Spring MVC test dependencies, `RequestDispatcher`, `MockMvc`, static imports, bean security chain và error controller thích hợp. **Đừng khẳng định kết quả HTTP cụ thể từ snippet một mình**: controller, error attributes và cấu hình response có thể khác. Để kiểm tra việc lỗi gốc được giữ, dùng tiếp kiểm thử container thật.

### B. Kiểm thử end-to-end với container nhúng

Tạo endpoint test công khai **ném một exception được kiểm soát**:

~~~java
@RestController
class ErrorFixtureController {
    @GetMapping("/public/boom")
    String boom() {
        throw new IllegalStateException("Synthetic error for test");
    }
}
~~~

Đây là **fixture dành riêng cho test**, không phải endpoint nên tồn tại trong production. Với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client thực (ví dụ `TestRestTemplate`), gọi `GET /public/boom`. Trong môi trường dùng Boot error handling mặc định và không có exception resolver tùy chỉnh, kỳ vọng status cuối thường **500**; không phải 401/403 phát sinh từ việc `/error` bị chặn. Đồng thời thử một **đường public không tồn tại** và xác minh **404** nếu MVC nhận request đó.

Ngoài HTTP status, có thể dùng test filter ghi nhận **`getDispatcherType()` và `getRequestURI()`** để chứng minh có lượt `REQUEST` rồi `ERROR`. Không yêu cầu test fixture ghi thông tin nhạy cảm. Với proxy, cần thêm integration test tại entry point thực tế nếu deployment làm biến đổi path.

### C. Kiểm thử request bảo vệ vẫn DENY

Dù error dispatch được permit, những ca sau phải giữ nguyên:

| Ca thử | Kỳ vọng |
| --- | --- |
| Anonymous `REQUEST /api/admin/users` | Không được chạy controller admin; HTTP Basic/JWT thường 401, form login có thể redirect. |
| User thường `REQUEST /api/admin/users` | 403 hoặc cách xử lý quyền thiếu đã thiết kế. |
| Admin hợp lệ `REQUEST /api/admin/users` | Được qua authorization (controller còn có thể sinh lỗi nghiệp vụ). |
| Anonymous `ERROR /error` | Được qua **rule dispatcher ERROR** để render lỗi. |
| Anonymous `REQUEST /error` | **Không tự động** được permit bởi rule chỉ ERROR. |
| Anonymous `FORWARD /access-denied` | Theo chính sách FORWARD riêng, không suy từ ERROR. |
| ERROR từ API nhưng target không còn là `/api/**` | Chain nhận target error phải cho phép ERROR nếu muốn render. |
| Endpoint public ném exception | Status gốc (thường 500) được hiển thị đúng, không bị từ chối lần thứ hai. |
| Đường public không có handler | 404 nếu request được MVC tiếp nhận và error mapping hoạt động. |
| Custom error handler lại ném exception | Có fallback an toàn, không redirect/forward vô hạn. |

Để xác định **test nào chứng minh gì**, tách riêng quy tắc authorization ban đầu với quy tắc render lỗi. Một status 500 từ endpoint public không cho biết endpoint admin đã an toàn; một status 403 từ admin không cho biết `/error` không bị mask. Cần cả hai nhóm test.

## 13. Chẩn đoán 401/403 bất thường ở /error bằng log chính xác

Khi gặp triệu chứng “route không tồn tại nhưng trả 401” hoặc “response lỗi 500 bỗng thành 403”, dùng một quy trình ngắn:

1. **Xác định lỗi ở REQUEST đầu tiên:** path nào, method nào, HTTP status dự kiến, controller hoặc filter nào chạy đến đâu?
2. **Tìm lượt dispatch sau đó:** log `DispatcherType.REQUEST`, `DispatcherType.ERROR` hoặc `FORWARD`; path hiện tại có phải `/error` hay đường được cấu hình ở `server.error.path`?
3. **Xác định chain nào nhận lượt đó:** một chain toàn app hay API chain + fallback? `securityMatcher` và `@Order` có làm `/error` rơi vào chain khác không?
4. **Xác định matcher phân quyền nào thắng:** có `dispatcherTypeMatchers(ERROR).permitAll()` **trước** `anyRequest()` trong chain phù hợp không?
5. **Xác định filter gây từ chối:** `AuthorizationFilter`, CSRF, authentication filter tùy biến hay một exception handler khác? `permitAll` không tự bypass tất cả.
6. **Kiểm tra error controller không tự ném lỗi:** có truy vấn database, cần user profile, forward trở lại /error, hoặc trang lỗi bị bảo vệ role không?
7. **Kiểm tra status và header cuối:** không ngẫu nhiên biến lỗi gốc thành 200, 302, 401, 403 hay HTML chứa stack trace; phù hợp client API hoặc browser.
8. **Chỉ sửa đúng nơi bị lỗi** rồi kiểm thử lại cả request gốc và ERROR dispatch, tránh thay `anyRequest().denyAll()` thành `permitAll()` trên toàn app.

Có thể bật DEBUG mức có kiểm soát cho `org.springframework.security` và log filter chain trong môi trường test. Ghi **request ID/correlation ID**, dispatcher type, URI đã được normalize và rule/chain được chọn nếu framework hỗ trợ quan sát. Không log Authorization bearer token, cookie, session ID, stack trace nhạy cảm vào response công khai hoặc hệ thống log không được bảo vệ.

**Cảnh báo về `OncePerRequestFilter`:** các filter của Spring Security và filter tùy chỉnh không nhất thiết chạy giống nhau ở các dispatcher. Một số filter chỉ chạy REQUEST hoặc bỏ qua ERROR theo cơ chế nội bộ; `AuthorizationFilter` có cách xử lý dispatch riêng. Vì vậy log “filter X chạy một lần nhưng `AuthorizationFilter` chạy hai lần” có thể phản ánh pipeline hợp lệ. Đừng viết giả định rằng toàn bộ filter chain trong ERROR phải có cùng side effect như REQUEST.

## 14. Checklist trước khi đưa cấu hình lên production

- [ ] Biết `/error` mặc định hay đường lỗi tùy chỉnh (`server.error.path`); xác minh có Boot error controller hoặc custom implementation.
- [ ] Phân biệt **REQUEST**, **ERROR** và **FORWARD**, không suy dispatcher type từ URL.
- [ ] Có rule theo `DispatcherType.ERROR` nếu container error dispatch cần được render mà không yêu cầu xác thực, và đặt nó **trước** các rule khác.
- [ ] Với nhiều chain, chain thực sự match ERROR target có xử lý rule đúng; fallback chain bao phủ URL ngoài API.
- [ ] Các endpoint quản trị và API private vẫn có rule role/authority và policy dữ liệu trên **REQUEST ban đầu**.
- [ ] `permitAll(ERROR)` không thay cho tắt CSRF, JWT authentication hay sửa custom filter; kiểm chứng filter nào thực sự chặn.
- [ ] Không bỏ Spring Security cho toàn bộ `/error` bằng `web.ignoring` nếu chỉ muốn hiển thị lỗi.
- [ ] Custom error controller không gọi lại `/error`, không phụ thuộc database để render, không trả dữ liệu nhạy cảm.
- [ ] Nếu dùng access-denied page theo `FORWARD`, kiểm tra riêng rule FORWARD và trang đích.
- [ ] Test container nhúng cho endpoint public ném lỗi 500, public URL thiếu handler 404 và protected endpoint vẫn từ chối.
- [ ] Kiểm tra status/body cho cả API JSON và browser HTML, kể cả trường hợp session/token không tồn tại.
- [ ] Log có correlation ID, dispatcher type và path, không lộ token hoặc PII.

**Kết luận:** Khi Spring Security xử lý **nhiều lượt dispatch cho một request**, endpoint `/error` có thể bị phân quyền lại và che mất lỗi gốc. Giải pháp thường phù hợp là **cho phép `DispatcherType.ERROR` ở đúng `SecurityFilterChain`**, giữ nguyên chính sách cho REQUEST/FORWARD như nghiệp vụ cần, và làm error handler tối giản, không tự phát sinh lỗi. Một ngoại lệ cho ERROR dispatch là cách **cho phép render lỗi**, **không phải cấp quyền** để người dùng vượt qua API được bảo vệ.

### Tài liệu tham khảo

- [Spring Security — Authorize HttpServletRequests: All Dispatches Are Authorized / Matching by Dispatcher Type](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Architecture and Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter)
- [Spring Boot 3.5 — Servlet Web Applications, Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Common Application Properties: server.error.path](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
