# Chuyển hướng, URL quay lại sau đăng nhập và rủi ro chuyển hướng không an toàn

Mai mở `/reports/42` nhưng chưa đăng nhập. Ứng dụng chuyển Mai đến `/login`; sau khi Mai xác thực thành công, ứng dụng đưa cô trở lại `/reports/42` thay vì bắt đầu từ trang chủ. Đây là một trải nghiệm rất thường gặp trong ứng dụng web có Spring Security.

Tuy nhiên, câu hỏi quan trọng là: **ai quyết định URL đích sau khi đăng nhập?** Nếu ứng dụng lấy nguyên giá trị `returnUrl`, `next` hoặc `redirect` do người dùng gửi rồi đặt vào header `Location`, một người có ý đồ xấu có thể khiến đường dẫn trên website đáng tin chuyển người truy cập sang website giả mạo. Đó là **chuyển hướng mở (open redirect)**, còn gọi là **chuyển hướng chưa được kiểm tra (unvalidated redirect)**.

Bài này giải thích từ nền tảng HTTP đến cơ chế ghi nhớ yêu cầu ban đầu của Spring Security, cách kiểm soát URL trở về và cách tránh biến đăng nhập thành điểm trung chuyển tới địa chỉ không đáng tin.

## 1. Chuyển hướng là gì? Browser thực sự làm gì?

Trong HTTP, redirect là một **response có mã trạng thái chuyển hướng và thường có header `Location`**. Máy khách nhận response rồi có thể gửi một request **mới** tới địa chỉ được chỉ định. Redirect khác với việc máy chủ lấy dữ liệu rồi trả về trực tiếp: đường đi trong trình duyệt có thể đổi, và request sau là một lượt HTTP riêng.

Ví dụ:

~~~http
GET /reports/42 HTTP/1.1
Host: learning.example
~~~

~~~http
HTTP/1.1 302 Found
Location: /login
Cache-Control: no-store
~~~

Trình duyệt xử lý response, sau đó gửi một request mới:

~~~http
GET /login HTTP/1.1
Host: learning.example
~~~

Mấu chốt ở đây là **`Location` xác định đích chuyển hướng**; status code cho biết cách xử lý chuyển hướng. `/login` là đường dẫn tương đối theo origin hiện tại, còn một URL đầy đủ như `https://other.example/login` có thể đưa người dùng sang origin khác.

### Các status code thường gặp

| Mã | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `301 Moved Permanently` | Chuyển vĩnh viễn | Có thể bị cache; xử lý phương thức sau redirect có khác biệt lịch sử đối với request không phải GET |
| `302 Found` | Chuyển tạm thời | Thường xuất hiện ở luồng đăng nhập/form; browser có thể đổi POST thành GET theo thực tế triển khai |
| `303 See Other` | Chuyển tới tài nguyên để GET | Sau POST, yêu cầu tiếp theo dùng GET; phù hợp mẫu Post/Redirect/Get |
| `307 Temporary Redirect` | Chuyển tạm thời nhưng giữ phương thức | **Giữ nguyên method và body** của request khi chuyển tới đích |
| `308 Permanent Redirect` | Chuyển vĩnh viễn và giữ phương thức | **Giữ nguyên method và body**, lại có ý nghĩa vĩnh viễn |

Ví dụ sau khi nhận POST của biểu mẫu, nếu muốn hiển thị trang kết quả mà không thực hiện lại POST khi tải lại, `303` là lựa chọn rõ nghĩa. Đặc biệt thận trọng khi dùng `307` hoặc `308` trên request chứa mật khẩu hay dữ liệu nhạy cảm: chúng yêu cầu client gửi lại cùng method và body tới đích chuyển hướng. Không dùng URL đích chưa tin cậy cho những trường hợp này.

**Redirect không xác nhận danh tính hoặc cấp quyền.** Việc browser đến `/reports/42` sau login chỉ là thao tác điều hướng; server vẫn phải xác thực và phân quyền khi xử lý request mới.

## 2. Tại sao cần URL quay lại sau đăng nhập?

Một người có thể đi tới trang cần xác thực bằng bookmark, đường dẫn từ email hoặc từ một menu nội bộ. Nếu chưa đăng nhập, ứng dụng thường muốn:

1. Ghi nhớ trang hoặc hành động **đang yêu cầu xác thực**.
2. Chuyển đến màn hình đăng nhập phù hợp.
3. Kiểm tra credentials khi người dùng gửi biểu mẫu đăng nhập.
4. Sau khi xác thực thành công, đưa người dùng trở lại tài nguyên mà họ định mở.
5. Đánh giá quyền truy cập vào **tài nguyên đích** theo danh tính đã xác thực.

Ví dụ:

~~~text
Mai muốn xem /reports/42
           |
           v
GET /reports/42  -> chưa xác thực
           |
           v
Lưu yêu cầu gốc theo cơ chế RequestCache (nếu được bật)
           |
           v
HTTP 302 Location: /login
           |
           v
Mai đăng nhập thành công
           |
           v
HTTP redirect đến /reports/42
           |
           v
GET /reports/42 (request mới)
           |
           v
Kiểm tra quyền thực sự trên báo cáo 42
           |
    +------+------+
    |             |
Cho phép      Từ chối (ví dụ 403)
~~~

Đây là hành vi phù hợp khi người dùng được phép xem tài nguyên. Nếu Mai đăng nhập thành công nhưng **không có quyền xem báo cáo 42**, ứng dụng vẫn phải từ chối ở bước cuối. “Được chuyển về đường dẫn ban đầu” hoàn toàn khác “được cấp quyền vào đường dẫn đó”.

Một tình huống khác là Mai chủ động mở `/login` từ trang chủ khi chưa có yêu cầu được ghi nhớ. Sau login, ứng dụng cần một **đích mặc định** hợp lý, chẳng hạn `/dashboard`.

## 3. Spring Security ghi nhớ request ban đầu ra sao?

Trong ứng dụng **servlet** có xác thực dựa trên trang đăng nhập, Spring Security có các thành phần đáng chú ý:

- **`ExceptionTranslationFilter`**: nhận diện tình huống request tới tài nguyên cần xác thực hoặc bị từ chối, phối hợp với `AuthenticationEntryPoint` và cơ chế lưu request.
- **`AuthenticationEntryPoint`**: đưa người dùng chưa xác thực vào quy trình đăng nhập; với form login thường dẫn đến chuyển hướng tới trang login.
- **`RequestCache`**: trừu tượng để lưu/đọc yêu cầu cần quay lại, chẳng hạn `HttpSessionRequestCache` lưu thông tin vào HTTP session.
- **`SavedRequest`/`DefaultSavedRequest`**: biểu diễn yêu cầu đã lưu, gồm thông tin giúp khôi phục điểm đến.
- **`AuthenticationSuccessHandler`**: xử lý sau xác thực thành công, có thể chuyển hướng đến đích đã được chọn.
- **`SavedRequestAwareAuthenticationSuccessHandler`**: một success handler hỗ trợ lấy URL từ SavedRequest để quay lại nơi người dùng định đến.

Cơ chế request cache phụ thuộc **cấu hình thực tế**. Không phải mọi request chưa đăng nhập đều được lưu; một ứng dụng API stateless có thể không dùng session/request cache, hoặc trả `401 Unauthorized` thay vì redirect tới trang HTML. Những thứ trên mô tả luồng servlet phổ biến, không phải một cam kết cho mọi cách xác thực.

### RequestCache không đơn giản là một chuỗi `next` trong URL

Với `HttpSessionRequestCache`, ứng dụng có thể lưu yêu cầu ban đầu ở phía server gắn với session, rồi sử dụng lại sau login. Điều này khác việc đặt `?next=https://... ` do client tự quyết định và tin ngay giá trị ấy.

Ví dụ mô phỏng:

~~~text
GET /private/report/42 (chưa đăng nhập)
    -> ExceptionTranslationFilter phát hiện cần xác thực
    -> RequestCache lưu URL yêu cầu gốc
    -> redirect /login

POST /login (xác thực thành công)
    -> AuthenticationSuccessHandler tìm SavedRequest
    -> redirect /private/report/42

GET /private/report/42 (đã đăng nhập)
    -> Spring Security kiểm tra Authentication và quyền
    -> thành công hoặc từ chối tùy chính sách
~~~

Một URL được ghi nhớ có thể chứa đường dẫn và query string của request gốc; vì thế không đặt mật khẩu, mã xác thực hay bí mật khác vào URL. Dữ liệu trong query có thể xuất hiện ở lịch sử, nhật ký, công cụ giám sát hoặc header tham chiếu trong một số hoàn cảnh.

### Thứ tự chọn đích trong SavedRequestAwareAuthenticationSuccessHandler

Với hành vi được tài liệu hóa của `SavedRequestAwareAuthenticationSuccessHandler` (khi dùng cấu hình mặc định tương ứng), việc chọn đích có các nhánh chính:

| Điều kiện | Đích được chọn |
| --- | --- |
| `alwaysUseDefaultTargetUrl=true` | Luôn dùng `defaultTargetUrl`; SavedRequest đã lưu được loại bỏ |
| Có cấu hình `targetUrlParameter` và request gửi giá trị tham số hợp lệ theo điều kiện handler | Dùng giá trị tham số làm đích; SavedRequest được loại bỏ |
| Không thuộc hai trường hợp trên và có SavedRequest | Quay lại URL của SavedRequest |
| Không có SavedRequest phù hợp | Dùng hành vi của lớp cơ sở, thường là `defaultTargetUrl` |

Thứ tự này hữu ích khi chẩn đoán “đăng nhập xong không quay lại trang vừa mở”. Chẳng hạn, `alwaysUseDefaultTargetUrl=true` sẽ chủ ý bỏ qua request đã lưu; custom success handler cũng có thể thay đổi hoàn toàn hành vi mặc định.

**Lưu ý bảo mật:** nếu bật cơ chế lấy đích từ một tham số trên request, tuyệt đối không mặc định rằng tham số do client cung cấp đã an toàn chỉ vì nó nằm trong flow Spring Security. Đích điều hướng cần có chính sách xác thực nguồn gốc rõ ràng. Cách đơn giản nhất là để máy chủ tự chọn từ các đích được định nghĩa sẵn.

## 4. Cấu hình Spring Security servlet cho trang mặc định

Ví dụ sau minh họa một `SecurityFilterChain` trong ứng dụng Spring Boot có Spring Security. Đây là đoạn mã thuộc ứng dụng Spring; để chạy cần cấu hình web, người dùng/provider và các dependency phù hợp.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/dashboard", false)
                .permitAll()
            );

        return http.build();
    }
}
~~~

Giải thích:

- `/login` và tài nguyên tĩnh được phép truy cập khi chưa đăng nhập. Khi chọn `loginPage("/login")`, ứng dụng chịu trách nhiệm cung cấp trang GET `/login` và form phù hợp.
- `/admin/**` yêu cầu role `ADMIN`; redirect đến URL này không tự cấp quyền quản trị.
- `defaultSuccessUrl("/dashboard", false)` đặt đích mặc định nhưng **không bắt buộc bỏ qua SavedRequest**. Nếu có yêu cầu gốc phù hợp được lưu, flow mặc định có thể quay lại đó.
- Đổi thành `defaultSuccessUrl("/dashboard", true)` nghĩa là **luôn điều hướng** đến `/dashboard` sau thành công, kể cả có request gốc được lưu.
- `permitAll()` trên form login giúp các endpoint phục vụ quá trình login được dùng khi chưa xác thực; nó không mở toàn bộ tài nguyên riêng tư.

`false` trong phương thức trên là lựa chọn cho trải nghiệm quay lại trang ban đầu. Ứng dụng muốn một màn hình cố định sau mỗi lần đăng nhập có thể dùng `true`. Hãy chủ động chọn theo nghiệp vụ thay vì ngạc nhiên vì behavior mặc định.

### Custom success handler thay đổi hành vi

Một `AuthenticationSuccessHandler` tùy biến có thể tự quyết định `Location` sau khi xác thực. Nó cũng có thể **bỏ qua logic SavedRequest** nếu không gọi hoặc không triển khai lại việc sử dụng request cache. Vì vậy khi debug, cần tìm handler thực sự được cấu hình cho cơ chế đăng nhập.

Không viết kiểu sau trong ứng dụng thật:

~~~java
// VÍ DỤ KHÔNG AN TOÀN: trả nguyên URL do client chỉ định.
String target = request.getParameter("next");
response.sendRedirect(target);
~~~

Giá trị `next` đến từ người dùng hoặc một đường dẫn do người khác tạo ra. Nếu không kiểm tra, đoạn này có thể redirect ra domain không đáng tin. Vấn đề không nằm ở riêng `sendRedirect`: việc đặt giá trị ấy vào response header `Location` qua bất kỳ cách nào cũng gây rủi ro tương tự.

## 5. Open redirect: một điểm đến không đáng tin lọt vào Location

Giả sử ứng dụng có endpoint:

~~~text
https://learning.example/login?next=/dashboard
~~~

Đích `/dashboard` là trang nội bộ. Nhưng nếu tham số `next` được nhận vô điều kiện, người xấu có thể chia sẻ một URL có domain khởi đầu rất giống website thật nhưng sau khi login lại dẫn sang website khác:

~~~text
https://learning.example/login?next=https%3A%2F%2Foutside.example%2Ffake-login
~~~

Sau khi người dùng thấy `learning.example` và tương tác, browser có thể nhận:

~~~http
HTTP/1.1 302 Found
Location: https://outside.example/fake-login
~~~

Trang tiếp theo thuộc `outside.example`, có thể giả giao diện để lừa nhập lại mật khẩu, mật khẩu dùng một lần hoặc thông tin cá nhân. Đây là tình huống phishing kinh điển qua open redirect.

**Đừng suy ra rằng cookie session của `learning.example` tự động được gửi sang `outside.example`.** Browser vẫn áp dụng phạm vi cookie/domain. Rủi ro trực tiếp của open redirect là điều hướng sang nơi không đáng tin; nó còn có thể là mắt xích của những lỗ hổng khác khi kết hợp với các luồng xác thực, callback hoặc token không được thiết kế chặt chẽ.

### Vì sao kiểm tra chuỗi đơn giản không đủ?

Giả sử ứng dụng chỉ kiểm tra:

~~~java
// VÍ DỤ SAI: startsWith không chứng minh host đáng tin.
if (next.startsWith("https://learning.example")) {
    response.sendRedirect(next);
}
~~~

Chuỗi `https://learning.example.outside.test/path` cũng có tiền tố `https://learning.example` nhưng **host thật là `learning.example.outside.test`**.

Các dạng input cần cảnh giác:

| Input từ người dùng | Vấn đề khi dùng làm đích điều hướng |
| --- | --- |
| `https://outside.example/login` | URL tuyệt đối ra ngoài |
| `//outside.example/login` | URL bắt đầu bằng hai dấu gạch chéo, có thể dùng host ngoài theo scheme hiện tại |
| `https://learning.example.outside.test/x` | Host khác dù có tiền tố giống host tin cậy |
| `https://learning.example@outside.example/x` | Phần trước `@` là user-info, host thực tế ở sau `@` |
| `/../admin` hoặc đường dẫn biến thể được mã hóa | Nguy cơ chuẩn hóa đường dẫn làm khác ý định kiểm tra; không thay thế phân quyền |
| Giá trị chứa dấu gạch ngược, ký tự điều khiển hoặc nhiều lớp percent-encoding | Có thể được client/framework/redirect handler diễn giải hoặc chuẩn hóa khác nhau |

Chỉ kiểm tra `startsWith("/")` cũng chưa đủ để khẳng định một đường dẫn là nội bộ vì trường hợp `//host`. Chỉ loại chuỗi `http` cũng thiếu vì URL scheme-relative và các biến thể. Không tự viết một chuỗi regex ngắn rồi kết luận đã xử lý toàn bộ cách browser phân tích URL.

Lỗ hổng open redirect còn liên quan đến việc dùng redirect như một **trang trung gian đáng tin**. Hệ thống khác có thể cho phép callback/return URI trỏ về domain của mình; nếu domain đó lại cho redirect ra ngoài vô điều kiện, nó có thể phá vỡ giả định an toàn của luồng tích hợp. Vì thế việc thiết kế OAuth/OIDC callback và redirect URI cần chặt chẽ, dù bài này chỉ đi sâu vào redirect sau login thông thường.

## 6. Nguyên tắc chọn URL trở về an toàn

Thứ tự ưu tiên trong thiết kế thực tế nên là:

1. **Không nhận URL tùy ý** nếu nghiệp vụ chỉ cần một số màn hình đã biết. Dùng mã đích (route key) như `orders`, `profile`, `dashboard` rồi ánh xạ phía server sang đường dẫn nội bộ.
2. Khi cần quay lại request trước login, dùng cơ chế **SavedRequest/RequestCache** phù hợp do ứng dụng kiểm soát, đồng thời bảo vệ cấu hình host, proxy và quá trình đưa URL vào hệ thống.
3. Nếu phải chấp nhận một URL do client đưa vào, dùng **parser chuẩn**, chính sách đích rõ ràng, chuẩn hóa tương thích với cách thành phần redirect/browser diễn giải, và chỉ sử dụng **giá trị đã được xác minh** để tạo response.
4. Với URL bên ngoài thực sự cần cho nghiệp vụ, dùng allowlist host/scheme/port và đường dẫn theo yêu cầu; cân nhắc trang trung gian cho người dùng biết họ sẽ rời website.
5. Nếu input sai/không hợp lệ/không được phép, **từ chối hoặc đưa về đích mặc định cố định**. Không tự sửa một chuỗi đáng ngờ rồi hy vọng trở thành an toàn.

Cần kiểm tra đồng thời:

- **Scheme**: chỉ `https` cho đích ngoài khi yêu cầu bảo mật đòi hỏi; không cho `javascript:`, `data:` hoặc scheme lạ.
- **Host**: so khớp chính xác host đã chuẩn hóa, không so sánh tiền tố hoặc hậu tố mơ hồ.
- **Port**: xét port hiệu lực theo chính sách, không coi mọi port trên host là ứng dụng của mình.
- **User info**: từ chối dạng `user@host` gây nhầm lẫn khi không có nhu cầu.
- **Đường dẫn**: giới hạn vào những route được phép; kiểm tra những biến thể do percent-encoding, slash/backslash và chuẩn hóa có thể ảnh hưởng.
- **Query/fragment**: không cho bí mật hoặc một “URL lồng bên trong” chạy vòng sang địa chỉ khác mà không kiểm tra.
- **Nguồn tin cậy của host**: không ghép `request.getHeader("Host")` hoặc `X-Forwarded-Host` chưa được reverse proxy xác minh để tạo URL quay về.

Một URL **nội bộ** chưa chắc là URL mà người dùng **có quyền mở**. Sau redirect, server vẫn phải thực hiện phân quyền như bình thường. Ví dụ một nhân viên không có role quản trị vẫn bị từ chối tại `/admin`, cho dù đích này có trong một danh sách đường dẫn nội bộ.

## 7. Ví dụ Java 17+ chạy độc lập: ánh xạ mã đích ở phía server

Ví dụ này **không triển khai cơ chế đăng nhập**; nó tách riêng quyết định chọn URL đích. Người dùng chỉ được gửi một *mã đích*, còn danh sách đường dẫn đích hợp lệ do ứng dụng định nghĩa. Mọi input khác được đưa về trang mặc định. Nhờ vậy, ứng dụng không bao giờ chèn trực tiếp URL từ query vào `Location`.

Tạo tệp `SafeReturnDestinationDemo.java`:

~~~java
import java.util.Map;

public class SafeReturnDestinationDemo {

    private static final Map<String, String> ROUTES = Map.of(
            "dashboard", "/app",
            "orders", "/app/orders",
            "profile", "/app/profile");

    static String destination(String routeKey) {
        if (routeKey == null) {
            return ROUTES.get("dashboard");
        }
        return ROUTES.getOrDefault(
                routeKey, ROUTES.get("dashboard"));
    }

    public static void main(String[] args) {
        String[] supplied = {
                "orders",
                "profile",
                "https://outside.example/fake-login",
                "//outside.example",
                "../admin"
        };

        for (String key : supplied) {
            System.out.println(key + " -> " + destination(key));
        }

        System.out.println("null -> " + destination(null));
    }
}
~~~

Với JDK 17 trở lên, đứng cùng thư mục với tệp vừa tạo rồi chạy:

~~~bash
javac SafeReturnDestinationDemo.java
java SafeReturnDestinationDemo
~~~

Đầu ra chính xác:

~~~text
orders -> /app/orders
profile -> /app/profile
https://outside.example/fake-login -> /app
//outside.example -> /app
../admin -> /app
null -> /app
~~~

Giải thích: `orders` và `profile` là các mã đích hợp lệ do máy chủ định nghĩa, nên chúng được ánh xạ đến đường dẫn tương ứng. Những giá trị còn lại không có trong `ROUTES` và đều trở về `/app`. Không có thao tác phân tích hay “làm sạch” URL bên ngoài vì ứng dụng **không cho phép nhập URL tự do ngay từ đầu**.

Đây là một kỹ thuật tránh open redirect tại điểm chọn đích, **không phải một hệ thống phân quyền**: người dùng vẫn phải được kiểm tra quyền khi truy cập `/app/orders` hoặc `/app/profile`. Nếu route có thêm ID tài nguyên, `documentId` của tài liệu hay `tenantId` cũng phải qua kiểm tra quyền riêng; không thể đưa mọi URL tùy ý vào `ROUTES` rồi coi là đủ an toàn.

## 8. Tích hợp route key vào success handler khi thật sự cần

Đối với một website chỉ cần ba trang đích đã định nghĩa, có thể chọn route key sau login trong success handler tùy biến. Mảnh mã dưới đây được đặt **bên trong phần cấu hình `formLogin` của một ứng dụng Spring Security servlet**, không phải chương trình Java độc lập:

~~~java
.formLogin(form -> form
    .successHandler((request, response, authentication) -> {
        String key = request.getParameter("destination");

        String path = switch (key == null ? "" : key) {
            case "orders" -> "/app/orders";
            case "profile" -> "/app/profile";
            default -> "/app";
        };

        response.sendRedirect(request.getContextPath() + path);
    })
)
~~~

Các đích trong `switch` là hằng số do server kiểm soát. Người dùng không thể dùng `destination=https://outside.example` để khiến code chọn host ngoài. Trong mã production, cần bảo vệ nguồn dữ liệu, áp dụng URL/context path và chính sách ghi log phù hợp.

**Đổi lấy điều gì?** Handler tùy biến như trên **không tự động khôi phục SavedRequest**. Người dùng truy cập một trang riêng tư trước login sẽ không được quay về trang đó nếu handler chỉ xét route key. Nếu ứng dụng muốn cả hai chức năng, cần thiết kế rõ thứ tự ưu tiên: chẳng hạn SavedRequest hợp lệ do server lưu trước, sau đó route key đã xác minh, cuối cùng là đích mặc định. Đừng trộn tùy tiện những nguồn đích không có cùng mức tin cậy.

### Tại sao không dùng mỗi Referer làm URL quay về?

Header `Referer` có thể vắng mặt, bị giới hạn bởi `Referrer-Policy`, hoặc đến từ ngữ cảnh mà ứng dụng không thể tin là nguồn quyết định quyền. Nếu dùng `Referer` như một tín hiệu trải nghiệm, nó vẫn phải qua cùng chính sách kiểm tra đích. **Không dùng nguyên `Referer` làm URL chuyển hướng chỉ vì nó có mặt trong request.**

### Login bằng OAuth2/OIDC có khác gì?

Các cơ chế OAuth2/OIDC còn có redirect URI giữa ứng dụng và nhà cung cấp danh tính. `redirect_uri` trong giao thức cần được đăng ký/kiểm tra theo quy tắc provider và ứng dụng. URL **đưa người dùng về trang nội bộ sau khi đã hoàn tất login** là một quyết định khác với URL callback của giao thức.

Không sử dụng `next` tùy ý để sửa callback URI, và không gửi authorization code, access token, ID token hoặc session credential tới URL do người dùng chỉ định. Phân biệt hai loại đích giúp tránh những lỗi kết hợp open redirect với luồng đăng nhập liên kết.

## 9. Những điểm dễ nhầm khi kiểm tra đăng nhập

### 9.1. Đến trang login bằng URL trực tiếp khác với bị chặn ở trang riêng tư

- Người dùng mở `/reports/42` khi chưa login: RequestCache có thể nhớ yêu cầu đó; sau thành công quay về `/reports/42`.
- Người dùng vào `/login` trực tiếp: có thể không tồn tại SavedRequest; handler dùng đích mặc định.
- Nếu vẫn bị đưa tới trang cũ dù vừa bấm login từ trang chủ, cần kiểm tra SavedRequest của session và chính sách xóa/đổi phiên.
- Nếu `alwaysUseDefaultTargetUrl=true`, SavedRequest có thể bị bỏ qua có chủ ý.

### 9.2. Request POST trước login không đồng nghĩa được gửi lại tự động

Không mặc định rằng một biểu mẫu POST bị chặn sẽ được phát lại nguyên body sau khi xác thực. Luồng redirect trình duyệt còn phụ thuộc status code, request cache, loại request và thiết kế nghiệp vụ. Với thao tác ghi dữ liệu, nên xử lý rõ việc xác thực trước, lưu bản nháp hợp lệ khi cần, kiểm soát CSRF và thực hiện hành động ghi sau khi đủ quyền. **Không yêu cầu người dùng đăng nhập rồi tự replay một thao tác gây tác dụng phụ khi chưa xác minh.**

### 9.3. API thường cần phản hồi khác trang HTML

Một browser đang điều hướng tới trang HTML có thể hiểu 302 sang `/login`. Nhưng REST API/SPA có thể cần `401` hoặc `403` theo trạng thái và hợp đồng API, để client chủ động hiện màn hình đăng nhập. Nếu API tự redirect HTML, client có thể nhận trang login thay vì JSON, dẫn đến lỗi phân tích response. Lựa chọn `AuthenticationEntryPoint` và success handler cần phù hợp loại client.

### 9.4. Đường dẫn sai, vòng lặp và session hết hạn

Khi `/login` cũng bị yêu cầu đăng nhập, cấu hình có thể tạo redirect loop. Khi SavedRequest trỏ đến URL không còn tồn tại, browser có thể nhận 404 sau login. Khi session dùng để giữ SavedRequest đã mất, ứng dụng không còn thông tin quay về và thường dùng đích mặc định. Khi cơ chế cấu hình thay đổi context path/reverse proxy, URL đích có thể có scheme, host, port hoặc path không mong đợi.

Những lỗi này phải được kiểm tra từng bước qua Network, không sửa bằng cách tin một tham số `next` từ client vô điều kiện.

## 10. Quy trình kiểm thử trên trình duyệt và HTTP

Có thể dùng DevTools → Network (bật Preserve log nếu muốn xem chuỗi 302) để theo dõi flow. Kiểm tra **status**, **`Location`**, cookie/session và request mới; đừng chỉ nhìn trang cuối.

Bộ thử nghiệm nên gồm:

| Tình huống | Điều kỳ vọng |
| --- | --- |
| Chưa đăng nhập mở `/reports/42` | Chuyển vào flow xác thực khi cần; request ban đầu có thể được lưu |
| Đăng nhập thành công, còn SavedRequest hợp lệ | Quay về `/reports/42` nếu chính sách cho phép |
| Mở `/login` trực tiếp và đăng nhập thành công | Đi tới trang mặc định phù hợp |
| Cấu hình `defaultSuccessUrl("/dashboard", true)` | Luôn quay về `/dashboard` theo cấu hình |
| Người dùng đã login nhưng không có quyền với `/reports/42` | Vẫn bị từ chối khi request mới được xử lý |
| `destination=orders` với route key cho phép | Chỉ chuyển tới `/app/orders` |
| `destination=https://outside.example` | Từ chối/fallback; không redirect tới host ngoài |
| `destination=//outside.example` | Từ chối/fallback; không coi `//` là đường dẫn nội bộ |
| `destination=https://learning.example.outside.test` | Từ chối/fallback; không dùng kiểm tra tiền tố hostname |
| Đích yêu cầu quyền quản trị nhưng người dùng thường đăng nhập | Redirect không nâng quyền; target phải từ chối |
| Không còn SavedRequest do session hết hạn | Dùng đích mặc định; không dựa vào trạng thái cũ |
| Browser/URL có query chứa token nhạy cảm | Không để token lộ vào history, log hoặc Location ngoài |

Nếu có cấu hình proxy, kiểm tra cả request với `Host` và forwarded headers theo cách môi trường triển khai cho phép. URL được tạo bởi server phải dựa trên origin đáng tin cậy, không từ header tùy ý không được xác minh. Khi có tích hợp OAuth2/OIDC, kiểm tra riêng redirect URI callback với danh sách URI đã đăng ký.

## 11. Sai lầm thường gặp

1. **“Đăng nhập thành công đồng nghĩa được vào URL quay lại.”** Sai: target request vẫn phải phân quyền.
2. **“`returnUrl` là tham số của ứng dụng mình nên luôn đáng tin.”** Sai: người ngoài có thể chỉnh query, form hoặc URL được chia sẻ.
3. **“URL bắt đầu bằng tên miền mình là an toàn.”** Sai: `learning.example.outside.test` có host khác.
4. **“Chuỗi bắt đầu bằng `/` chắc chắn nội bộ.”** Sai: `//outside.example` là một dạng URL có host ngoài.
5. **“Chỉ cần chặn `http://`.”** Sai: còn `https://`, `//`, các scheme và những biến thể định dạng khác.
6. **“SavedRequest có nghĩa Spring Security cấp phép cho target.”** Sai: SavedRequest ghi nhớ yêu cầu; authorization vẫn chạy trên request mới.
7. **“Đặt `defaultSuccessUrl` là luôn bỏ qua SavedRequest.”** Chưa đúng: đối số `alwaysUse` quyết định chuyện này.
8. **“Chuyển bằng 307 sau POST login giống 303.”** Sai: 307 giữ phương thức và body; 303 yêu cầu GET.
9. **“Open redirect chắc chắn làm lộ cookie session sang host khác.”** Sai về mặt cơ chế cookie mặc định; rủi ro chính là chuyển hướng ngoài ý muốn và các chuỗi tấn công liên quan.
10. **“Frontend ẩn link ngoài là đủ.”** Sai: server vẫn phải kiểm soát `Location`.
11. **“Cho phép redirect đến `/admin` tức người dùng có quyền admin.”** Sai: quyền phải được kiểm tra ở endpoint đích.
12. **“Không thấy redirect trong code controller nghĩa là không có.”** Chưa chắc: security filter, authentication entry point và success handler cũng có thể tạo redirect.

## 12. Tự kiểm tra tư duy

**Câu 1.** Mai mở `/reports/42` khi chưa login. Sau login, browser lại mở `/reports/42`. Spring Security có thể đã dùng những thành phần nào?

*Trả lời:* Trong flow servlet phù hợp, `ExceptionTranslationFilter` phối hợp `AuthenticationEntryPoint` và `RequestCache` lưu yêu cầu; sau thành công `SavedRequestAwareAuthenticationSuccessHandler` chọn URL từ SavedRequest. Request mới vẫn phải qua authorization.

**Câu 2.** Tại sao `defaultSuccessUrl("/dashboard", false)` có thể không đưa người dùng về `/dashboard`?

*Trả lời:* Vì vẫn có thể tồn tại SavedRequest hợp lệ; khi đó handler dùng URL gốc. Với `true`, đích mặc định được chọn dù có request đã lưu.

**Câu 3.** Một URL tham số là `//outside.example/path`. Vì sao không nên cho qua bằng điều kiện `startsWith("/")`?

*Trả lời:* Hai dấu `//` có thể biểu thị authority/host của URL scheme-relative; browser có thể đi đến website khác.

**Câu 4.** Làm thế nào để một hệ thống chỉ có ba trang đích sau login tránh xử lý URL tự do?

*Trả lời:* Cho client gửi một route key được định nghĩa, server ánh xạ key sang một trong ba đường dẫn cố định và fallback về trang mặc định. Target vẫn phải được phân quyền.

**Câu 5.** Một người dùng đã đăng nhập được redirect tới `/admin` nhưng nhận `403`. Đây có phải lỗi redirect?

*Trả lời:* Không nhất thiết. Redirect đã đưa browser tới đúng URL; chính sách phân quyền ở `/admin` tiếp tục từ chối vì thiếu quyền.

**Câu 6.** Vì sao dùng `307` để chuyển POST login sang URL ngoài đáng ngờ nguy hiểm hơn một redirect GET thông thường?

*Trả lời:* `307` bảo client giữ nguyên method và body; dữ liệu POST có thể được gửi tới đích mới. Không dùng đích chưa tin cậy, đặc biệt với request chứa credentials.

**Câu 7.** Có thể lấy nguyên `Referer` của request login rồi dùng làm `Location` sau thành công không?

*Trả lời:* Không nên. Referer có thể thiếu hoặc không đáng tin và phải được kiểm tra bằng chính sách đích giống mọi dữ liệu không tin cậy khác.

Khi xây dựng flow đăng nhập, hãy tách ba quyết định: **(1) người dùng có được xác thực không, (2) URL nào được phép dùng làm đích sau xác thực, (3) người dùng có quyền truy cập tài nguyên ở đích đó không.** Việc xác thực thành công không tự trả lời thay hai câu hỏi sau.

### Tài liệu tham khảo

- [Spring Security — SavedRequestAwareAuthenticationSuccessHandler](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security — RequestCache](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [MDN — Redirections in HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Redirections)
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)
