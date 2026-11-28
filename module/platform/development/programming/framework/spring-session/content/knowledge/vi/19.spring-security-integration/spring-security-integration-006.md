# Chống session fixation bằng đổi định danh sau xác thực

## Mục tiêu bài học

Session fixation là kiểu tấn công trong đó kẻ tấn công biết hoặc kiểm soát trước Session ID của nạn nhân, sau đó tìm cách khiến nạn nhân đăng nhập và tiếp tục sử dụng chính định danh đó. Nếu ứng dụng giữ nguyên Session ID sau khi xác thực, kẻ tấn công có thể dùng ID đã biết để truy cập phiên đã được xác thực.

Spring Security cung cấp cơ chế session fixation protection để thay đổi định danh phiên khi xác thực thành công. Khi kết hợp Spring Session với Redis hoặc JDBC, việc đổi ID phải được thực hiện qua Servlet API và repository tích hợp, để ID cũ không còn đại diện cho phiên đã xác thực và các instance khác cũng nhìn thấy trạng thái mới.

Sau bài học, bạn có thể:

- Giải thích cách session fixation xảy ra trước và sau khi người dùng đăng nhập.
- Mô tả thời điểm Spring Security áp dụng session fixation protection.
- Cấu hình chiến lược `changeSessionId`, `migrateSession`, `newSession` hoặc `none`.
- Hiểu cách Spring Session phối hợp với `HttpServletRequest.changeSessionId()`.
- Phân biệt đổi Session ID với tạo session mới, logout và hủy phiên.
- Giữ lại hoặc loại bỏ thuộc tính session theo chính sách bảo mật.
- Kiểm thử ID cũ, ID mới và trạng thái xác thực trên Redis/JDBC.
- Xử lý đúng các trường hợp nhiều instance và custom authentication filter.

## 1. Session fixation là gì?

Trong ứng dụng web dùng session, client thường giữ một Session ID trong cookie. Máy chủ dùng ID đó để tìm trạng thái phiên ở repository.

Session fixation xảy ra khi kẻ tấn công biết một Session ID trước khi nạn nhân đăng nhập, rồi khiến nạn nhân xác thực trong khi ứng dụng vẫn giữ nguyên ID đó.

Một tình huống điển hình:

1. Kẻ tấn công tạo hoặc lấy được một session chưa xác thực, có ID là `S1`.
2. Kẻ tấn công tìm cách khiến trình duyệt nạn nhân sử dụng ID `S1`, ví dụ qua một điểm yếu cho phép cài đặt session identifier hoặc một luồng chia sẻ session không an toàn.
3. Nạn nhân đăng nhập thành công.
4. Ứng dụng giữ nguyên `S1` và gắn trạng thái xác thực vào session đó.
5. Kẻ tấn công gửi lại `S1` và có thể tiếp tục phiên đã được xác thực.

Sơ đồ trước khi có bảo vệ:

~~~text
Attacker biết Session ID S1
          |
          v
Victim nhận / sử dụng S1
          |
          v
Victim đăng nhập thành công
          |
          v
Server giữ nguyên S1 và gắn Authentication
          |
          v
Attacker gửi lại S1
          |
          v
Nguy cơ truy cập phiên đã xác thực
~~~

Vấn đề cốt lõi là định danh trước xác thực vẫn được dùng sau xác thực. Ứng dụng cần thay ID tại ranh giới tin cậy này.

Session fixation khác với session hijacking theo cách thường mô tả: hijacking thường là kẻ tấn công lấy cắp một ID đang đại diện cho phiên hợp lệ; fixation là kẻ tấn công cố định hoặc biết ID từ trước và chờ nạn nhân đăng nhập trên chính ID đó. Cả hai đều có thể dẫn đến chiếm quyền phiên.

## 2. Đổi Session ID sau xác thực giải quyết điều gì?

Sau khi xác thực thành công, ứng dụng cần tạo một định danh mới mà kẻ tấn công chưa biết. Session ID cũ không được tiếp tục truy cập trạng thái đã xác thực.

Luồng sau khi bật bảo vệ:

~~~text
Request trước đăng nhập
Cookie: SESSION=S1
          |
          v
Session chưa xác thực S1
          |
          v
Người dùng xác thực thành công
          |
          v
Spring Security gọi SessionAuthenticationStrategy
          |
          v
Đổi định danh S1 -> S2
          |
          v
Repository lưu session theo định danh mới
          |
          v
Response gửi cookie SESSION=S2
          |
          v
Request sau đăng nhập dùng S2
~~~

Sau khi đổi ID:

- Client nhận định danh mới trong response.
- Session đã xác thực được truy cập bằng ID mới.
- ID cũ không còn được chấp nhận như định danh của phiên đã xác thực.
- Những instance khác dùng chung repository phải nhìn thấy kết quả đổi ID.

Việc đổi ID thường giữ lại session hiện tại và các thuộc tính cần thiết. Nó không nhất thiết có nghĩa là người dùng bị logout rồi login lại. Mục tiêu là thay định danh của phiên tại thời điểm xác thực.

Đổi ID không thay thế việc xác thực, phân quyền, bảo vệ CSRF hoặc cấu hình cookie an toàn. Đây là một biện pháp cụ thể trong quản lý vòng đời session.

## 3. Spring Security áp dụng session fixation protection khi nào?

Trong ứng dụng Servlet, Spring Security quản lý quá trình xác thực qua các authentication filter và cơ chế session management. Sau khi authentication thành công, chiến lược `SessionAuthenticationStrategy` được gọi để thực hiện các hành động liên quan đến session.

Một trong các hành động đó là session fixation protection.

Với form login chuẩn của Spring Security, authentication filter tích hợp chiến lược session management. Các cơ chế xác thực do framework cung cấp cũng phối hợp với session strategy theo cấu hình.

Trình tự khái quát:

1. Authentication filter nhận thông tin đăng nhập.
2. `AuthenticationManager` xác thực thông tin.
3. Khi xác thực thành công, Spring Security gọi session authentication strategy.
4. Session fixation strategy đổi ID hoặc tạo session mới tùy cấu hình.
5. `SecurityContext` được lưu theo cơ chế cấu hình của ứng dụng.
6. Response được gửi về client với định danh phiên mới nếu session resolver sử dụng cookie hoặc header.

Điểm quan trọng là phải đổi ID sau khi xác thực thành công và trước khi tiếp tục sử dụng session đã xác thực. Nếu custom filter tự xác thực nhưng bỏ qua session strategy, cơ chế bảo vệ có thể không được thực hiện.

### Vai trò của SessionAuthenticationStrategy

`SessionAuthenticationStrategy` là abstraction để Spring Security thực hiện các hành động liên quan đến session khi một authentication thành công. Session fixation protection là một trong những chiến lược có thể được cấu hình thông qua session management.

Trong ứng dụng có thêm concurrent session control hoặc các chính sách session khác, Spring Security có thể kết hợp nhiều strategy. Không nên tự gọi một strategy riêng song song với cấu hình framework nếu chưa hiểu thứ tự và cách phối hợp, vì có thể đổi ID nhiều lần hoặc làm sai trạng thái session.

## 4. Các chiến lược session fixation protection

Spring Security cung cấp các lựa chọn phổ biến:

| Chiến lược | Hành vi | Khi cân nhắc |
|---|---|---|
| `changeSessionId` | Đổi ID của session hiện tại bằng Servlet API | Lựa chọn phù hợp với Servlet 3.1+ và thường là mặc định trên container hiện đại |
| `migrateSession` | Tạo session mới, chuyển các thuộc tính từ session cũ sang session mới | Khi cần tương thích với container cũ hoặc muốn tạo session object mới nhưng giữ thuộc tính |
| `newSession` | Tạo session sạch, không chuyển các thuộc tính ứng dụng cũ; các thuộc tính Spring Security cần thiết vẫn được duy trì | Khi không muốn mang dữ liệu session trước xác thực sang phiên đã xác thực |
| `none` | Không thực hiện session fixation protection | Chỉ dùng khi có lý do đặc biệt và rủi ro đã được đánh giá |

### changeSessionId

`changeSessionId` gọi `HttpServletRequest.changeSessionId()` để thay định danh của session hiện tại. Session object và các thuộc tính vẫn được giữ; chỉ ID được thay đổi.

Đây là chiến lược mặc định của Spring Security trên Servlet 3.1 trở lên trong các cấu hình hiện đại. Nó phù hợp với Spring Session vì request đã được Spring Session bọc để thao tác đổi ID được chuyển tới repository.

### migrateSession

`migrateSession` tạo một session mới và sao chép các thuộc tính từ session cũ sang session mới. Session cũ bị invalidate theo chiến lược này.

Chiến lược này hữu ích khi cần tương thích với container Servlet cũ hoặc muốn bảo đảm session object mới được tạo sau xác thực nhưng vẫn giữ dữ liệu trước đó.

Cần lưu ý rằng mọi thuộc tính được sao chép có thể mang theo dữ liệu không còn phù hợp sau đăng nhập. Hãy rà soát những gì đang được lưu trong session.

### newSession

`newSession` tạo một session mới mà không chuyển các thuộc tính ứng dụng từ session cũ. Các thuộc tính liên quan đến Spring Security cần thiết cho quá trình xác thực vẫn được duy trì theo hành vi của framework.

Chiến lược này phù hợp khi session trước xác thực có thể chứa dữ liệu không đáng tin cậy hoặc không nên được giữ sau đăng nhập. Tuy nhiên, giỏ hàng tạm, ngôn ngữ hoặc trạng thái quy trình có thể bị mất nếu chúng nằm trong session cũ.

### none

`none` không thay đổi định danh. Nó loại bỏ lớp bảo vệ session fixation do Spring Security cung cấp. Không chọn tùy tiện chỉ để giữ Session ID hoặc tránh thay đổi cookie.

Nếu một hệ thống chọn `none`, cần có lý do kiến trúc rõ ràng, đánh giá rủi ro và biện pháp bảo vệ thay thế. Với ứng dụng dùng session xác thực, thông thường nên bật một chiến lược đổi ID.

## 5. Cấu hình changeSessionId trong Spring Security

Với Spring Security hiện đại sử dụng `SecurityFilterChain`, có thể cấu hình rõ chiến lược `changeSessionId`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/login", "/assets/**").permitAll()
                        .anyRequest().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation
                                .changeSessionId()
                        )
                )
                .build();
    }
}
~~~

Cấu hình trên:

- Cho phép truy cập trang login và tài nguyên tĩnh.
- Yêu cầu xác thực cho các request còn lại.
- Bật form login mặc định.
- Yêu cầu đổi Session ID sau khi xác thực thành công.

Với Servlet 3.1+ và Spring Security hiện đại, `changeSessionId` thường là mặc định. Khai báo tường minh vẫn hữu ích để người đọc cấu hình hiểu rõ chính sách bảo mật mà ứng dụng mong muốn.

Cú pháp DSL có thể khác giữa các major version Spring Security. Khi dự án dùng API cũ, đối chiếu tài liệu của đúng version thay vì sao chép nguyên cấu hình của phiên bản mới.

### Chọn migrateSession hoặc newSession

Nếu muốn chuyển thuộc tính ứng dụng sang session mới:

~~~java
.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.migrateSession())
)
~~~

Nếu muốn tạo session sạch và bỏ các thuộc tính ứng dụng cũ:

~~~java
.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.newSession())
)
~~~

Không nên cấu hình `none()` trong ứng dụng session-based nếu không có đánh giá bảo mật riêng.

## 6. Spring Session phối hợp với Servlet API như thế nào?

Servlet API cung cấp phương thức:

~~~java
request.changeSessionId();
~~~

Phương thức này đổi định danh của session hiện tại mà không cần tạo một session object mới.

Khi Spring Session được tích hợp, `SessionRepositoryFilter` bọc request và response. Request wrapper cung cấp triển khai phù hợp cho `HttpSession` và thao tác đổi ID. Khi Spring Security gọi `request.changeSessionId()`, thao tác được chuyển đến session do Spring Session quản lý.

Luồng tích hợp:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security
    participant F as SessionRepositoryFilter
    participant R as Spring Session Repository
    participant D as Redis or JDBC

    C->>F: Request với Session ID cũ
    F->>S: Request đã được bọc
    S->>S: Xác thực thành công
    S->>F: request.changeSessionId()
    F->>R: Đổi định danh session
    R->>D: Cập nhật dữ liệu / index
    D-->>R: Thành công
    R-->>F: Session ID mới
    F-->>C: Response với cookie hoặc ID mới
~~~

Spring Session xử lý các chi tiết lưu trữ tùy repository. Ứng dụng không cần và không nên tự sửa key Redis hoặc hàng JDBC để đổi Session ID.

### Thứ tự filter rất quan trọng

`SessionRepositoryFilter` cần chạy trước các filter trong Spring Security có thể truy cập `HttpSession`. Khi đó Spring Security thao tác trên session wrapper của Spring Session thay vì session cục bộ của Servlet container.

Spring Boot và Spring Session auto-configuration thường đăng ký filter với thứ tự phù hợp. Nếu ứng dụng tự đăng ký filter, cần kiểm tra thứ tự thực tế trong Servlet filter chain.

Nếu Spring Security chạy trước Spring Session filter, việc đổi ID hoặc đọc session có thể không tác động đến repository dùng chung như dự kiến.

## 7. Đổi ID khi dùng Redis hoặc JDBC

Spring Session tách API Servlet khỏi nơi lưu trữ. Vì vậy, Spring Security có thể dùng cùng chiến lược `changeSessionId` dù repository là Redis hay JDBC.

### Với Redis

Repository Redis lưu session theo định danh và có thể duy trì các cấu trúc phụ trợ như index, expiration metadata hoặc thông tin phục vụ tìm kiếm session.

Khi ID đổi, Spring Session chịu trách nhiệm cập nhật trạng thái repository để ID mới trỏ đến session hiện tại và ID cũ không còn được dùng để tải phiên đã xác thực.

Không tự dùng `RENAME` hoặc `DEL` trên key Redis nội bộ để đổi ID. Một session có thể liên quan đến nhiều key. Đổi tên một key đơn lẻ không bảo đảm index, TTL và metadata được cập nhật nhất quán.

### Với JDBC

Repository JDBC lưu thông tin session và các thuộc tính trong các bảng Spring Session. Khi ID đổi, repository cập nhật dữ liệu theo mô hình lưu trữ của nó.

Không tự chạy SQL cập nhật cột Session ID hoặc xóa hàng cũ trong controller. Việc này có thể phá quan hệ giữa bảng session và bảng thuộc tính, bỏ qua transaction hoặc bỏ qua cơ chế cập nhật của repository.

### Điều kiện để nhiều instance cùng thấy ID mới

Tất cả instance cần dùng:

- Cùng Redis deployment hoặc cùng database.
- Cùng namespace/schema và cấu hình repository.
- Cùng cách serialize thuộc tính.
- Cùng cookie/header resolver và tên định danh.
- Các phiên bản Spring Session tương thích trong giai đoạn rolling deployment.

Nếu instance A đổi ID nhưng instance B dùng repository khác hoặc namespace khác, B có thể không tìm được phiên mới. Đây là lỗi cấu hình chia sẻ session, không phải lý do để giữ nguyên ID cũ.

## 8. Bảo toàn dữ liệu session khi đổi ID

Khi người dùng truy cập ứng dụng trước đăng nhập, session có thể chứa một số dữ liệu hợp lệ:

- Giỏ hàng tạm.
- Ngôn ngữ giao diện.
- Lựa chọn sản phẩm.
- Trạng thái quy trình nhiều bước.
- CSRF token hoặc thuộc tính kỹ thuật do framework quản lý.

Sau đăng nhập, ứng dụng cần quyết định dữ liệu nào được giữ lại. Không phải mọi thuộc tính trước xác thực đều đáng tin cậy.

### Chọn chiến lược theo dữ liệu

| Dữ liệu trước xác thực | Cách xử lý thường phù hợp |
|---|---|
| Giỏ hàng ẩn danh | Có thể chuyển sang tài khoản sau khi xác minh và hợp nhất |
| Ngôn ngữ giao diện | Thường có thể giữ |
| Trạng thái điều hướng | Có thể giữ nếu không chứa quyền |
| Vai trò hoặc quyền do client gửi | Không tin cậy; phải tải lại từ nguồn xác thực |
| Cờ authenticated do client đặt | Không được dùng làm bằng chứng xác thực |
| Token hoặc credential cũ | Không sao chép tùy tiện; cần chính sách riêng |
| Dữ liệu workflow nhạy cảm | Xác minh chủ sở hữu và quyền trước khi giữ |

`changeSessionId` giữ các thuộc tính hiện tại. Vì vậy, nếu ứng dụng lưu dữ liệu trước xác thực, cần kiểm tra những thuộc tính đó không thể làm tăng quyền sau đăng nhập.

`migrateSession` cũng chuyển thuộc tính cũ. `newSession` loại bỏ thuộc tính ứng dụng cũ, phù hợp hơn khi không muốn mang dữ liệu trước xác thực sang phiên đã xác thực.

### Hợp nhất giỏ hàng là nghiệp vụ riêng

Nếu cần chuyển giỏ hàng ẩn danh sang tài khoản, không nên chỉ giữ nguyên thuộc tính session rồi tin rằng dữ liệu đã thuộc về user đã đăng nhập.

Hãy:

1. Đọc giỏ hàng ẩn danh.
2. Xác minh dữ liệu và giới hạn sản phẩm/số lượng.
3. Tải giỏ hàng hiện tại của tài khoản.
4. Hợp nhất theo quy tắc nghiệp vụ.
5. Ghi giỏ hàng dưới danh tính tài khoản.
6. Xóa dữ liệu tạm nếu đã chuyển thành công.

Đổi Session ID và hợp nhất dữ liệu nghiệp vụ là hai thao tác liên quan nhưng khác trách nhiệm.

## 9. Cookie và header sau khi đổi định danh

Với cookie resolver, response sau xác thực cần gửi cookie chứa Session ID mới. Trình duyệt phải lưu và gửi lại cookie mới ở các request tiếp theo.

Cookie session nên có các thuộc tính phù hợp:

- `Secure`: chỉ gửi qua HTTPS.
- `HttpOnly`: JavaScript không đọc cookie qua API cookie thông thường.
- `SameSite`: giảm gửi cookie trong một số ngữ cảnh cross-site.
- `Path` và `Domain`: giới hạn phạm vi cookie cần thiết.

Spring Session có thể dùng cookie resolver mặc định hoặc cấu hình cookie serializer riêng. Khi đổi ID, resolver phải cập nhật cookie theo cùng tên và phạm vi cookie đã cấu hình.

Với client dùng header resolver, client phải đọc định danh mới trong response header và gửi lại ID mới ở request tiếp theo. Client không nên tiếp tục gửi ID cũ sau khi authentication thành công.

Nếu ứng dụng hỗ trợ cả cookie và header, phải quy định nguồn định danh có hiệu lực. Không để request đồng thời gửi ID cũ trong cookie và ID mới trong header mà server không có chính sách ưu tiên rõ ràng.

## 10. Tích hợp với custom authentication filter

Form login chuẩn của Spring Security tích hợp session authentication strategy. Tuy nhiên, ứng dụng có thể có custom filter để xử lý đăng nhập bằng JSON, OTP, SSO callback hoặc cơ chế xác thực riêng.

Nếu custom filter tự xác thực và tự lưu `SecurityContext` mà bỏ qua `SessionAuthenticationStrategy`, session fixation protection có thể không được áp dụng.

Một luồng custom authentication cần:

1. Xác thực credential bằng `AuthenticationManager` hoặc cơ chế tương đương.
2. Khi authentication thành công, gọi session authentication strategy đã được cấu hình.
3. Lưu SecurityContext theo SecurityContextRepository phù hợp.
4. Trả response để session resolver gửi định danh mới.
5. Xử lý lỗi mà không để lại session ở trạng thái xác thực dở dang.

Không tự tạo một `SessionFixationProtectionStrategy` riêng nếu Spring Security đã quản lý strategy qua cấu hình `HttpSecurity`. Hãy tích hợp với strategy được framework cấu hình để tránh bỏ qua concurrent session control hoặc các chính sách session khác.

Với Spring Security 6, cách cấu hình và kết nối strategy cho custom filter phụ thuộc loại filter và authentication flow. Đối chiếu API đúng phiên bản và viết integration test chứng minh ID được đổi sau khi xác thực.

## 11. Session fixation và session creation policy

Session fixation protection có ý nghĩa khi ứng dụng sử dụng session để lưu trạng thái xác thực.

Một số chính sách tạo session:

| Chính sách | Ý nghĩa tổng quát |
|---|---|
| `ALWAYS` | Luôn tạo session |
| `IF_REQUIRED` | Tạo session khi cần |
| `NEVER` | Không chủ động tạo session nhưng có thể dùng session hiện có |
| `STATELESS` | Không dùng HttpSession để lưu SecurityContext |

Nếu ứng dụng dùng `STATELESS` và xác thực bằng token stateless, session fixation protection cho HttpSession thường không phải cơ chế chính. Tuy nhiên, nếu một phần khác của ứng dụng vẫn dùng session, cần xem xét riêng ranh giới đó.

Không bật `STATELESS` chỉ để tránh xử lý session fixation nếu ứng dụng đang dựa vào session để giữ SecurityContext. Điều đó có thể làm trạng thái xác thực không được lưu như mong muốn.

## 12. Kiểm thử session fixation protection

Một bài test đúng cần xác minh cả ID và trạng thái xác thực. Chỉ kiểm tra response login thành công chưa chứng minh session ID đã được đổi.

### Các điều cần kiểm tra

1. Tạo session chưa xác thực và lấy Session ID cũ.
2. Lưu một thuộc tính vô hại trước đăng nhập nếu muốn kiểm tra hành vi giữ dữ liệu.
3. Gửi thông tin đăng nhập kèm ID cũ.
4. Xác minh authentication thành công.
5. Lấy Session ID mới từ response.
6. Xác minh ID mới khác ID cũ.
7. Gửi request đã xác thực với ID mới và xác minh truy cập được.
8. Gửi request với ID cũ và xác minh không còn được xem là phiên đã xác thực.
9. Kiểm tra thuộc tính ứng dụng được giữ hay bị loại bỏ theo chiến lược đã chọn.
10. Kiểm tra logout làm phiên mới không còn hợp lệ.

### Ví dụ khung MockMvc

Ví dụ dưới đây giả định cookie Spring Session có tên `SESSION`, endpoint login dùng form login và dự án có Spring Security Test để cung cấp CSRF request post processor.

~~~java
MvcResult beforeLogin = mockMvc.perform(get("/test/session"))
        .andExpect(status().isOk())
        .andReturn();

Cookie oldCookie = beforeLogin.getResponse().getCookie("SESSION");

MvcResult loginResult = mockMvc.perform(post("/login")
        .cookie(oldCookie)
        .with(csrf())
        .param("username", "alice")
        .param("password", "correct-password"))
        .andReturn();

Cookie newCookie = loginResult.getResponse().getCookie("SESSION");

assertThat(newCookie).isNotNull();
assertThat(newCookie.getValue()).isNotEqualTo(oldCookie.getValue());
~~~

Đây là khung minh họa. Endpoint test tạo session, cookie name, login URL và cơ chế xác thực cần khớp ứng dụng. Nếu response không phát cookie mới vì resolver hoặc session policy khác, hãy kiểm tra cấu hình thực tế thay vì giả định cookie mặc định.

Tiếp theo cần gửi request đã xác thực bằng `newCookie` và xác minh request dùng `oldCookie` không truy cập được dữ liệu đã bảo vệ.

### Kiểm thử repository thật

Mock session trong bộ nhớ không đủ để chứng minh Spring Session Redis/JDBC cập nhật định danh trong repository.

Nên chạy integration test với:

- Redis test instance hoặc Testcontainers khi dùng Redis.
- Database cùng hệ quản trị production hoặc Testcontainers khi dùng JDBC.
- Cấu hình Spring Session giống production.
- Filter chain và authentication flow thật.
- Cookie/header resolver thật.

Kiểm tra repository không còn trả session xác thực bằng ID cũ và session ID mới có thể được tải bởi instance khác.

## 13. Kiểm thử nhiều instance và request đồng thời

Trong hệ thống nhiều instance, load balancer có thể chuyển request đăng nhập đến A rồi chuyển request tiếp theo đến B.

Một kịch bản kiểm thử:

1. Request đầu tiên tạo session ở App A, ID là S1.
2. Request đăng nhập được xử lý ở App A.
3. Spring Security yêu cầu đổi ID thành S2.
4. Repository dùng chung cập nhật session.
5. Response trả cookie S2.
6. Request tiếp theo đến App B với S2.
7. App B tải được SecurityContext và session attributes theo chính sách.
8. Request đến App B với S1 không thể truy cập phiên đã xác thực.

### Request đồng thời dùng ID cũ

Có thể có request khác đang chạy khi ID được đổi. Ví dụ một tab trình duyệt gửi request song song bằng cookie cũ ngay lúc đăng nhập hoàn tất.

Ứng dụng cần chấp nhận rằng request đến với ID cũ có thể không còn tải được phiên đã xác thực. Client nên cập nhật cookie từ response đăng nhập và gửi ID mới cho request sau.

Không nên khôi phục ID cũ chỉ để các request đang chạy tiếp tục truy cập phiên xác thực. Nếu cần xử lý các request đang diễn ra, hãy thiết kế luồng điều hướng hoặc retry sau authentication theo trạng thái an toàn.

Với dữ liệu nghiệp vụ được cập nhật đồng thời trong session, session fixation protection không tự giải quyết lost update. Cần dùng cơ chế đồng bộ hoặc lưu dữ liệu nghiệp vụ có version/transaction riêng.

## 14. Những lỗi thường gặp

**Đăng nhập thành công nhưng Session ID không đổi.**  
Kiểm tra session management DSL, Servlet version, authentication filter có gọi session strategy không và Spring Session filter có đứng trước Spring Security không.

**ID đổi nhưng người dùng bị mất giỏ hàng.**  
Có thể ứng dụng dùng `newSession`, hoặc logic migration không giữ thuộc tính mong muốn. Chọn chiến lược phù hợp và hợp nhất dữ liệu nghiệp vụ có kiểm tra.

**ID cũ vẫn truy cập được phiên đã xác thực.**  
Kiểm tra repository, filter order, resolver và các instance có dùng chung store/namespace không. Không tự xóa key bằng SQL hoặc Redis command để vá.

**App A thấy phiên mới nhưng App B không thấy.**  
Kiểm tra cả hai instance dùng cùng repository, namespace, serializer và phiên bản tương thích.

**Custom authentication filter không đổi ID.**  
Xác minh filter đã gọi `SessionAuthenticationStrategy` sau authentication thành công và trước khi tiếp tục xử lý SecurityContext.

**Cookie vẫn chứa ID cũ.**  
Kiểm tra response Set-Cookie, cookie name/path/domain, reverse proxy và việc client có lưu cookie mới không.

**Session fixation protection bị tắt do STATELESS.**  
Xác định ứng dụng có thật sự không dùng HttpSession hay không. Nếu vẫn lưu trạng thái xác thực trong session, chọn policy phù hợp.

**Đổi ID thủ công bằng cách xóa key Redis.**  
Thao tác này bỏ qua repository, index và TTL. Dùng `request.changeSessionId()` qua Spring Security/Spring Session.

**Cho rằng đổi ID thay thế CSRF protection.**  
Session fixation và CSRF là hai rủi ro khác nhau. Ứng dụng cookie-based vẫn cần CSRF protection phù hợp.

## 15. Checklist triển khai

Trước khi đưa cấu hình session fixation protection lên production, xác nhận:

- Ứng dụng dùng Servlet stack và Spring Security session management phù hợp.
- Session ID được đổi sau authentication thành công.
- Chiến lược `changeSessionId`, `migrateSession` hoặc `newSession` phù hợp dữ liệu session.
- Custom authentication filter có gọi session authentication strategy.
- `SessionRepositoryFilter` chạy trước Spring Security filter chain.
- Redis/JDBC repository được chia sẻ giữa mọi instance.
- Resolver gửi ID mới về client.
- Cookie có Secure, HttpOnly, SameSite và phạm vi path/domain phù hợp.
- ID cũ không còn tải được phiên đã xác thực.
- ID mới tải được SecurityContext và thuộc tính cần giữ.
- Có integration test với repository thật.
- Có test nhiều instance và request đồng thời.
- Logout vẫn invalidate phiên mới theo đúng chính sách.

## 16. Tự kiểm tra

1. Session fixation xảy ra trong tình huống nào?
2. Vì sao đổi Session ID sau authentication giúp giảm nguy cơ fixation?
3. `SessionAuthenticationStrategy` được gọi ở thời điểm nào?
4. `changeSessionId` khác `migrateSession` như thế nào?
5. Khi nào `newSession` phù hợp?
6. Vì sao `none` thường không nên dùng?
7. Spring Session phối hợp với `HttpServletRequest.changeSessionId()` ra sao?
8. Vì sao `SessionRepositoryFilter` cần chạy trước Spring Security filter chain?
9. Custom authentication filter cần làm gì để không bỏ qua session fixation protection?
10. Vì sao không nên đổi Session ID bằng lệnh Redis hoặc SQL trực tiếp?
11. Cần kiểm tra những gì để xác nhận ID cũ không còn truy cập phiên đã xác thực?
12. Vì sao session fixation protection không thay thế CSRF protection?

### Gợi ý trả lời

1. Kẻ tấn công biết hoặc cố định Session ID trước khi nạn nhân đăng nhập, rồi dùng lại ID sau khi nạn nhân xác thực.
2. ID mới không được chia sẻ với kẻ tấn công; ID cũ không còn đại diện cho phiên đã xác thực.
3. Sau khi authentication thành công, trong quá trình xử lý session authentication trước khi hoàn tất response.
4. `changeSessionId` đổi ID của session hiện tại; `migrateSession` tạo session mới và chuyển thuộc tính cũ.
5. Khi muốn session sạch, không mang thuộc tính ứng dụng trước xác thực sang phiên mới.
6. Vì nó không đổi định danh, bỏ qua lớp bảo vệ fixation.
7. Request wrapper của Spring Session chuyển thao tác đổi ID sang repository và resolver.
8. Để Spring Security thao tác trên session được Spring Session quản lý, không phải session local của container.
9. Gọi session authentication strategy đã cấu hình sau xác thực thành công.
10. Vì repository có thể quản lý index, TTL, metadata và quan hệ dữ liệu ngoài một key/hàng đơn lẻ.
11. Dùng ID mới xác minh truy cập được; dùng ID cũ xác minh không còn tải được phiên đã xác thực; kiểm tra qua repository thật và instance khác.
12. Fixation là vấn đề định danh phiên; CSRF là vấn đề request giả mạo được trình duyệt gửi kèm credential tự động.

## Kết luận

Session fixation xảy ra khi một định danh phiên mà kẻ tấn công biết từ trước vẫn được dùng sau khi nạn nhân xác thực. Spring Security giảm nguy cơ này bằng cách áp dụng `SessionAuthenticationStrategy` sau authentication thành công và đổi Session ID theo chiến lược đã chọn. Trên Servlet hiện đại, `changeSessionId` thường là lựa chọn mặc định; `migrateSession` và `newSession` phù hợp với những yêu cầu khác nhau về việc giữ thuộc tính cũ.

Khi dùng Spring Session Redis hoặc JDBC, `SessionRepositoryFilter` phải bọc request trước Spring Security để thao tác `HttpServletRequest.changeSessionId()` cập nhật repository và resolver đúng cách. Không sửa key Redis hoặc hàng JDBC bằng tay. Hãy kiểm thử ID cũ, ID mới, dữ liệu session được giữ, logout và khả năng tải phiên qua nhiều instance. Đổi định danh là một lớp bảo vệ quan trọng, nhưng vẫn cần authentication, authorization, CSRF protection và cookie policy phù hợp.

