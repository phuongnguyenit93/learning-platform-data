# Cấu hình maximumSessions và chính sách từ chối hoặc hết hạn phiên cũ

Spring Security có thể giới hạn số phiên đăng nhập đồng thời của một principal. Ví dụ, tài khoản chỉ được duy trì tối đa hai phiên. Khi người dùng đăng nhập trên thiết bị thứ ba, ứng dụng có thể từ chối lần đăng nhập mới hoặc chấp nhận phiên mới và đánh dấu một phiên cũ hết hạn. Spring Session giúp chính sách này hoạt động trên nhiều instance bằng cách lưu session trong kho dùng chung như Redis hoặc JDBC.

Để giới hạn phiên chính xác trên toàn cụm, Spring Security cần một SessionRegistry nhìn thấy session từ mọi node. Registry chỉ lưu trong bộ nhớ của từng JVM không đủ cho hệ thống phân tán: node A có thể không biết người dùng đã đăng nhập ở node B. Với Spring Session, thường dùng SpringSessionBackedSessionRegistry cùng repository hỗ trợ tìm session theo principal.

## 1. maximumSessions kiểm soát điều gì?

Trong cấu hình Spring Security, maximumSessions(n) đặt số phiên tối đa mà một principal có thể giữ. Giới hạn được áp dụng theo principal name mà SessionRegistry nhận diện, không phải theo địa chỉ IP, trình duyệt hay session ID riêng lẻ.

Ví dụ:

- maximumSessions(1) cho phép một phiên hoạt động cho mỗi principal.
- maximumSessions(2) cho phép hai phiên.

Giới hạn này khác với giới hạn số request đồng thời. Một session có thể gửi nhiều request song song mà vẫn chỉ được tính là một phiên đăng nhập. Ngược lại, cùng một tài khoản có thể có nhiều session ID từ các trình duyệt hoặc thiết bị khác nhau.

Chính sách maximum sessions thường được thực thi trong luồng xác thực Servlet khi một Authentication mới thành công. Vì vậy, cần kiểm tra filter chain và Authentication mechanism thực tế. Một endpoint tùy chỉnh tự tạo Authentication nhưng bỏ qua các strategy của Spring Security có thể không kích hoạt kiểm soát concurrent session như mong đợi.

## 2. Hai chính sách khi vượt giới hạn

Spring Security cung cấp hai lựa chọn chính qua maxSessionsPreventsLogin:

| Cấu hình | Khi số phiên đã đạt giới hạn | Kết quả |
|---|---|---|
| maxSessionsPreventsLogin(true) | Có lần đăng nhập mới | Từ chối phiên mới; các phiên đang hoạt động được giữ |
| maxSessionsPreventsLogin(false) | Có lần đăng nhập mới | Chấp nhận phiên mới và đánh dấu một hoặc nhiều phiên cũ hết hạn để đưa tổng số về giới hạn |

Mặc định thường là false: hệ thống cho phép đăng nhập mới và hết hạn phiên cũ. Có thể cấu hình rõ ràng để tránh hiểu nhầm chính sách.

### 2.1. Từ chối lần đăng nhập mới

Khi đặt maxSessionsPreventsLogin(true), nếu principal đã có đủ số phiên thì authentication mới bị từ chối. Người dùng tiếp tục sử dụng các phiên cũ. Ứng dụng có thể hiển thị thông báo như “Tài khoản đang đăng nhập trên thiết bị khác; hãy đăng xuất thiết bị đó trước khi tiếp tục”.

Chính sách này phù hợp khi tổ chức muốn giữ phiên hiện tại ổn định, ví dụ tài khoản nội bộ chỉ được dùng trên một thiết bị quản trị. Người dùng cần biết cách khôi phục quyền đăng nhập nếu thiết bị cũ bị mất hoặc không thể truy cập.

### 2.2. Hết hạn phiên cũ để chấp nhận phiên mới

Khi đặt maxSessionsPreventsLogin(false), Spring Security cho phép đăng nhập mới. Nếu vượt giới hạn, chiến lược concurrent session sẽ chọn session cũ để đánh dấu hết hạn. Thông thường, phiên có lần request gần nhất cũ nhất được chọn trước.

Phiên cũ không nhất thiết bị xóa khỏi Redis/JDBC ngay tại thời điểm đăng nhập mới. Nó được đánh dấu hết hạn trong trạng thái session. Khi request tiếp theo mang session ID cũ đi qua ConcurrentSessionFilter, filter phát hiện trạng thái expired, thực hiện logout/invalidate và gọi chiến lược phản hồi hết hạn. Do đó, client đang dùng phiên cũ có thể chỉ thấy bị đăng xuất ở request kế tiếp.

Đây là điểm khác nhau giữa đánh dấu hết hạn, từ chối request và xóa vật lý dữ liệu session. Việc cleanup dữ liệu trong repository có thể diễn ra theo vòng đời session hoặc cơ chế hết hạn riêng.

## 3. Luồng xử lý concurrent session

Khi một người dùng đăng nhập:

1. Authentication filter xác thực credentials.
2. Concurrent session strategy lấy các session hiện có của principal từ SessionRegistry.
3. Nếu số session còn dưới giới hạn, lần đăng nhập được phép tiếp tục.
4. Nếu đã đạt giới hạn, strategy áp dụng chính sách từ chối hoặc đánh dấu session cũ hết hạn.
5. Khi phiên mới được lưu, session ID và principal được ghi vào repository/index.
6. Với chính sách hết hạn phiên cũ, request kế tiếp của phiên bị đánh dấu sẽ bị ConcurrentSessionFilter xử lý.

~~~mermaid
flowchart TD
    A[Đăng nhập thành công về credentials] --> B[Tra SessionRegistry theo principal]
    B --> C{Đã đạt maximumSessions?}
    C -->|Chưa| D[Cho phép đăng nhập]
    C -->|Rồi, preventsLogin=true| E[Từ chối lần đăng nhập mới]
    C -->|Rồi, preventsLogin=false| F[Đánh dấu phiên cũ hết hạn]
    F --> G[Cho phép phiên mới]
    G --> H[Request kế tiếp dùng session cũ]
    H --> I[ConcurrentSessionFilter phát hiện expired]
    I --> J[Logout/invalidate phiên cũ]
~~~

Khi dùng Spring Session, SessionRegistry phải tra cứu dữ liệu chia sẻ. Nếu registry chỉ có dữ liệu local, sơ đồ trên chỉ phản ánh một node và giới hạn có thể bị vượt khi request được phân phối giữa các instance.

## 4. Cấu hình maximumSessions với Spring Security

Ví dụ cấu hình Servlet với giới hạn một phiên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.core.session.SessionRegistry;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SessionRegistry sessionRegistry) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .sessionManagement(session -> session
                .maximumSessions(1)
                .maxSessionsPreventsLogin(false)
                .expiredUrl("/login?expired")
                .sessionRegistry(sessionRegistry)
            );

        return http.build();
    }
}
~~~

Trong ví dụ, mỗi principal có tối đa một phiên. Khi có lần đăng nhập mới, phiên cũ được đánh dấu hết hạn và lần đăng nhập mới được chấp nhận. Request tiếp theo từ phiên cũ được chuyển đến URL hết hạn.

Nếu muốn từ chối đăng nhập mới, đổi maxSessionsPreventsLogin thành true. Khi chọn chính sách từ chối, hãy cấu hình authentication failure handling để thông báo rõ nguyên nhân. Tùy cơ chế đăng nhập, exception do concurrent-session control có thể đi qua AuthenticationFailureHandler hoặc cơ chế xử lý lỗi của filter tương ứng. Cần xác minh hành vi thực tế và nội dung thông báo trong ứng dụng.

Các phương thức DSL có thể thay đổi chi tiết giữa các phiên bản Spring Security. Hãy dùng API của phiên bản dependency trong dự án và tránh trộn ví dụ từ thế hệ cũ với cấu hình hiện đại.

## 5. Vì sao SessionRegistry mặc định không đủ cho nhiều instance?

SessionRegistry mặc định của Spring Security thường giữ thông tin session trong bộ nhớ tiến trình. Trong một ứng dụng đơn node, cách này có thể hoạt động tốt. Nhưng trong cụm nhiều instance:

- Người dùng đăng nhập ở node A; registry của A ghi nhận session.
- Người dùng đăng nhập lần nữa ở node B; registry của B có thể không thấy session của A.
- Cả hai node đều cho phép đăng nhập vì mỗi registry nghĩ rằng số phiên còn dưới giới hạn.
- Tổng số phiên trên toàn cụm vượt maximumSessions.

Sticky session ở load balancer không giải quyết triệt để vấn đề. Node có thể restart, failover hoặc thay đổi phân phối request. Dữ liệu kiểm soát phiên cần được chia sẻ qua repository.

Với Spring Session, dùng SpringSessionBackedSessionRegistry để tra cứu session từ FindByIndexNameSessionRepository:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.security.SpringSessionBackedSessionRegistry;
import org.springframework.security.core.session.SessionRegistry;

@Configuration
public class ConcurrentSessionConfiguration {

    @Bean
    SessionRegistry sessionRegistry(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        return new SpringSessionBackedSessionRegistry<>(repository);
    }
}
~~~

Bean này thay SessionRegistry local bằng registry đọc dữ liệu từ Spring Session repository. Repository được inject phải hỗ trợ tìm session theo principal. Không dùng một repository chỉ có khả năng tìm theo ID nếu nó không cung cấp API index mà registry cần.

## 6. Điều kiện để SpringSessionBackedSessionRegistry hoạt động

SpringSessionBackedSessionRegistry dựa trên FindByIndexNameSessionRepository. Nó cần biết principal name của từng session để tìm tất cả phiên của một người dùng.

Các điều kiện cần bảo đảm:

- Repository thực tế triển khai FindByIndexNameSessionRepository.
- Session được index theo principal name sau khi người dùng xác thực.
- Mọi node dùng cùng repository, namespace, database và cấu hình index.
- Principal name ổn định giữa các lần đăng nhập và các node.
- Các phiên bản Spring Session và Spring Security tương thích.

Với Redis, cần dùng repository/index resolver hỗ trợ principal lookup; trong một số cấu hình cần bật indexed session repository thay vì repository không cung cấp index. Với JDBC, xác minh implementation được dùng có hỗ trợ tìm theo principal và schema chứa dữ liệu index tương ứng.

Nếu ứng dụng dùng principal tùy chỉnh, cần xác định quy tắc lấy tên principal. Hai node không được dùng hai biểu diễn khác nhau, ví dụ node A index theo username viết thường còn node B index theo email. Nếu khác nhau, registry có thể coi cùng một người là hai principal và không áp dụng giới hạn chính xác.

### 6.1. Kiểm tra index principal

Một cách kiểm tra qua API repository:

~~~java
Map<String, ? extends Session> sessions =
    repository.findByIndexNameAndIndexValue(
        FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
        principalName
    );
~~~

Kết quả cần chứa các session đang gắn với principal name tương ứng. Nếu luôn rỗng dù người dùng đã đăng nhập, kiểm tra cách repository xác định principal, thuộc tính SecurityContext và cấu hình index. Không nên tự ghi index thô bằng Redis command hoặc SQL nếu repository đã có API quản lý.

## 7. Chọn phiên cũ nào để hết hạn?

Khi chính sách cho phép đăng nhập mới, Spring Security cần chọn một hoặc nhiều phiên hiện tại để đưa tổng số về giới hạn. Strategy concurrent session thường dựa trên thời điểm request gần nhất của SessionInformation.

Ví dụ người dùng có ba phiên nhưng giới hạn là hai:

| Session | Lần truy cập gần nhất | Kết quả minh họa |
|---|---|---|
| Máy tính văn phòng | 08:10 | Có thể bị chọn hết hạn trước |
| Điện thoại | 09:45 | Giữ |
| Máy tính cá nhân | 10:20 | Giữ |

Đây là ví dụ theo nguyên tắc chọn phiên ít hoạt động gần đây nhất; kết quả chính xác phụ thuộc thời điểm registry ghi nhận và thứ tự xử lý. Không coi thứ tự này là một hợp đồng nghiệp vụ để quyết định thiết bị nào phải được giữ nếu ứng dụng có yêu cầu ưu tiên thiết bị.

Nếu cần chính sách đặc biệt như luôn giữ thiết bị tin cậy hoặc ưu tiên phiên quản trị, phải thiết kế một strategy riêng dựa trên metadata được quản lý rõ ràng. Không suy đoán thiết bị từ user-agent hoặc IP rồi sửa trực tiếp trạng thái SessionRegistry.

## 8. ConcurrentSessionFilter và trải nghiệm của phiên bị hết hạn

ConcurrentSessionFilter kiểm tra session hiện tại với SessionRegistry trong mỗi request. Nếu SessionInformation cho biết phiên đã hết hạn, filter:

1. Thực hiện logout cho request hiện tại.
2. Vô hiệu hóa session theo cơ chế tương ứng.
3. Gọi SessionInformationExpiredStrategy để tạo phản hồi.

Với ứng dụng web truyền thống, có thể dùng expiredUrl("/login?expired"). Với REST API, nên dùng strategy trả JSON và status phù hợp, ví dụ thông báo mã SESSION_EXPIRED_BY_CONCURRENT_LOGIN, thay vì redirect HTML.

Client nên xử lý trạng thái hết hạn bằng cách xóa session ID local/cookie theo response và đưa người dùng về luồng đăng nhập. Không tiếp tục retry request với session ID cũ.

### 8.1. Không phải lúc nào phiên cũ cũng bị xóa ngay

Chính sách “expire old session” thường đánh dấu session hết hạn để filter xử lý ở request tiếp theo. Nó khác với thao tác xóa toàn bộ key hoặc dòng session ngay tại thời điểm đăng nhập mới. Dữ liệu có thể còn trong repository trong một khoảng thời gian ngắn, nhưng request qua filter chain phải bị từ chối theo trạng thái expired.

Với client không gửi request tiếp theo, session cũ có thể còn tồn tại cho tới khi timeout hoặc cleanup. Đây là lý do nên cấu hình idle timeout hợp lý và có cơ chế thu hồi phiên phù hợp.

## 9. Xử lý đăng nhập đồng thời và race condition

maximumSessions kiểm soát các lần xác thực mới, nhưng hai lần đăng nhập gần như đồng thời có thể cùng đọc trạng thái trước khi session mới của lần còn lại được ghi/index. Trong hệ thống có tải cao, việc kiểm tra rồi ghi không nhất thiết là một thao tác nguyên tử trên toàn cụm.

Ví dụ với giới hạn một:

1. Node A xác thực người dùng và tra registry, chưa thấy phiên.
2. Node B gần như đồng thời xác thực cùng người dùng và cũng chưa thấy phiên.
3. Cả hai tiếp tục tạo session.
4. Hai phiên được lưu vào repository.

Kết quả có thể vượt giới hạn trong một khoảng thời gian nếu thao tác không được điều phối nguyên tử. SpringSessionBackedSessionRegistry cung cấp registry dựa trên session store, nhưng không nên mặc định nó biến toàn bộ quá trình authentication thành một giao dịch distributed atomic.

Nếu giới hạn là yêu cầu nghiêm ngặt, cần đánh giá thêm cơ chế đồng bộ ở tầng ứng dụng hoặc store:

- Distributed lock theo principal với thời gian giữ ngắn và xử lý timeout rõ ràng.
- Một dịch vụ quản lý phiên trung tâm có thao tác atomic check-and-register.
- Constraint/record quản lý slot phiên trong database nghiệp vụ nếu mô hình phù hợp.
- Retry có giới hạn sau khi đọc lại trạng thái, tránh giữ lock quá lâu.

Thiết kế bổ sung phải tránh deadlock và phải xử lý được node chết giữa lúc giữ lock. Không khóa toàn bộ Redis hoặc database cho mỗi lần đăng nhập.

## 10. Logout, timeout và registry

SessionRegistry cần phản ánh vòng đời thực tế của session:

- Đăng nhập thành công: phiên mới được đăng ký hoặc xuất hiện trong repository/index.
- Logout: phiên bị invalidate và không còn được xem là hoạt động.
- Hết idle timeout: repository từ chối session và cleanup dữ liệu theo cơ chế lưu trữ.
- Concurrent-session expiration: phiên bị đánh dấu hết hạn và bị ConcurrentSessionFilter xử lý khi request tiếp theo đến.
- Tài khoản bị khóa hoặc thu hồi quyền: ứng dụng có thể cần chủ động xóa tất cả session theo principal.

Với SpringSessionBackedSessionRegistry, dữ liệu lấy từ repository dùng chung; không nên trông chờ listener local của một JVM là nguồn duy nhất. Kiểm thử logout và expiration phải xác nhận node khác cũng nhìn thấy trạng thái mới.

Nếu cần “đăng xuất khỏi tất cả thiết bị”, truy vấn session theo principal rồi xóa/invalidate từng session qua API được hỗ trợ. Không chỉ xóa session ID trong trình duyệt hiện tại.

## 11. Kết hợp maximumSessions với các chính sách session khác

Concurrent session control là một phần của session management. Nó cần phối hợp với:

| Thành phần | Quan hệ với maximumSessions |
|---|---|
| SessionCreationPolicy | Quyết định có dùng/tạo HttpSession để lưu xác thực hay không |
| Session fixation protection | Đổi session ID sau xác thực; registry phải theo dõi đúng ID mới |
| SecurityContextRepository | Lưu Authentication để request sau được nhận diện |
| SessionRegistry | Liệt kê và đánh dấu session theo principal |
| ConcurrentSessionFilter | Phát hiện phiên đã bị đánh dấu expired |
| Spring Session repository | Lưu session dùng chung để mọi node tra cứu |
| Logout handler | Invalidate session và xóa context |

Với ứng dụng stateful dùng Spring Session, SessionCreationPolicy.IF_REQUIRED thường phù hợp hơn STATELESS. Nếu cấu hình STATELESS, Spring Security không dùng HttpSession để duy trì SecurityContext và concurrent-session control dựa trên session sẽ không hoạt động như mong đợi.

Đừng bỏ session fixation protection khi thêm maximumSessions. Sau login, ID có thể được đổi; test cần dùng cookie/ID mới để request tiếp theo được nhận diện.

## 12. Ví dụ cấu hình đầy đủ cho nhiều instance

Ví dụ sau ghép registry dùng chung và giới hạn một phiên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.security.SpringSessionBackedSessionRegistry;

@Configuration
public class SessionSecurityConfiguration {

    @Bean
    SessionRegistry sessionRegistry(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        return new SpringSessionBackedSessionRegistry<>(repository);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SessionRegistry sessionRegistry) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/session-expired").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .sessionManagement(session -> session
                .maximumSessions(1)
                .maxSessionsPreventsLogin(false)
                .expiredUrl("/session-expired")
                .sessionRegistry(sessionRegistry)
            );

        return http.build();
    }
}
~~~

Để dùng ví dụ này:

1. Cấu hình Spring Session Redis hoặc JDBC cho ứng dụng Servlet.
2. Bảo đảm repository được tạo là loại hỗ trợ FindByIndexNameSessionRepository.
3. Cấu hình principal index hoạt động cho Authentication thực tế.
4. Mọi node dùng chung store và cùng cấu hình security.
5. Xác nhận custom authentication flow cũng đi qua concurrent-session strategy hoặc được tích hợp tương đương.

Không chỉ khai báo bean registry mà quên cấu hình indexed repository. Nếu không có principal index, registry có thể không tìm được các session hiện có và giới hạn không được áp dụng đúng.

## 13. Tùy chỉnh phản hồi khi đăng nhập bị từ chối hoặc phiên hết hạn

Hai chính sách tạo ra hai loại kết quả khác nhau:

| Tình huống | Điểm xử lý | Trải nghiệm gợi ý |
|---|---|---|
| Đăng nhập mới bị từ chối vì đã đạt giới hạn | Authentication failure handling | Thông báo đang có đủ phiên; hướng dẫn logout thiết bị khác |
| Phiên cũ bị đánh dấu hết hạn | ConcurrentSessionFilter và expired strategy | Thông báo phiên đã kết thúc do đăng nhập mới |

Không dùng cùng một thông báo cho hai trường hợp nếu người dùng cần biết họ phải làm gì tiếp theo. Với REST API, định nghĩa mã lỗi ổn định và không trả thông tin nhạy cảm về thiết bị khác. Với giao diện web, redirect URL phải cho phép truy cập công khai để tránh vòng lặp redirect.

Nếu dùng expiredUrl, kiểm tra URL đó không yêu cầu authentication, nếu không request của phiên expired có thể bị chuyển hướng lặp lại. Với SPA, có thể dùng SessionInformationExpiredStrategy tùy chỉnh để trả JSON.

## 14. Kiểm thử maximumSessions

Kiểm thử cần chạy qua authentication filter và session repository thật. Chỉ gọi trực tiếp method trên SessionRegistry không xác nhận toàn bộ flow.

Ma trận cơ bản với maximumSessions(1):

| Kịch bản | Cấu hình | Kết quả mong đợi |
|---|---|---|
| Đăng nhập lần đầu | Cả hai chính sách | Thành công, có session |
| Đăng nhập lần hai, từ chối mới | maxSessionsPreventsLogin(true) | Lần hai thất bại; session đầu vẫn dùng được |
| Đăng nhập lần hai, hết hạn cũ | maxSessionsPreventsLogin(false) | Lần hai thành công; request kế tiếp của phiên đầu bị từ chối |
| Logout phiên đầu | Bất kỳ chính sách | Slot phiên được giải phóng theo repository |
| Đăng nhập lại sau logout | Bất kỳ chính sách | Thành công nếu không còn phiên vượt giới hạn |
| Hai node | Registry dùng Spring Session | Node B thấy phiên do node A tạo |
| Principal khác nhau | Giới hạn một | Mỗi principal có thể có một phiên riêng |
| Hai lần login đồng thời | Nhiều node | Quan sát và đánh giá race condition |
| Hết idle timeout | Repository có TTL/cleanup | Session hết hạn không được tính là phiên hoạt động |
| Session fixation | Bật changeSessionId | Registry nhận diện ID sau xác thực |

### 14.1. Ví dụ kiểm thử với MockMvc

Ví dụ dưới đây minh họa kiểm tra chính sách từ chối đăng nhập mới. Endpoint, status và cách xác thực phải khớp cấu hình test của ứng dụng:

~~~java
MvcResult firstLogin = mockMvc.perform(formLogin()
        .user("alice")
        .password("password"))
    .andExpect(authenticated())
    .andReturn();

mockMvc.perform(formLogin()
        .user("alice")
        .password("password"))
    .andExpect(unauthenticated());

MockHttpSession firstSession =
    (MockHttpSession) firstLogin.getRequest().getSession(false);

mockMvc.perform(get("/profile").session(firstSession))
    .andExpect(authenticated());
~~~

Với chính sách hết hạn phiên cũ, test cần giữ session đầu, đăng nhập lần hai, sau đó gửi request bằng session đầu và xác nhận bị redirect hoặc nhận response expired. Với Spring Session thực tế, nên dùng Redis/JDBC integration test và hai application context/instance để chứng minh registry dùng chung.

## 15. Chẩn đoán khi maximumSessions không hoạt động

Khi người dùng đăng nhập nhiều lần vượt giới hạn, kiểm tra theo thứ tự:

1. SecurityFilterChain có cấu hình maximumSessions cho đúng request chain không?
2. Authentication flow có chạy qua concurrent session strategy không?
3. Bean SessionRegistry có phải SpringSessionBackedSessionRegistry không?
4. Repository có triển khai FindByIndexNameSessionRepository không?
5. Principal name có được index và có cùng giá trị trên mọi node không?
6. Session mới có được lưu và index trước lần đăng nhập tiếp theo không?
7. ConcurrentSessionFilter có được cài trong filter chain và chạy cho request cũ không?
8. Session fixation hoặc custom logout có làm registry nhìn thấy ID khác với ID thực tế không?
9. Các node có dùng cùng Redis/database, namespace và schema không?
10. Có race condition do hai lần đăng nhập đồng thời không?

Không kết luận lỗi chỉ từ số dòng session trong Redis/JDBC. Session có thể đã bị đánh dấu expired nhưng chưa bị xóa vật lý; cần kiểm tra trạng thái qua API repository/registry và hành vi request qua filter.

## 16. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đăng nhập vượt giới hạn trên nhiều node | SessionRegistry local memory | Dùng SpringSessionBackedSessionRegistry |
| Registry luôn trả danh sách rỗng | Repository không index principal hoặc principal mapping sai | Dùng indexed repository và xác minh index |
| Phiên cũ không bị đá ra | ConcurrentSessionFilter không chạy hoặc flow không qua strategy | Kiểm tra filter chain và custom authentication |
| Đăng nhập mới bị từ chối ngoài ý muốn | maxSessionsPreventsLogin(true) hoặc còn session cũ | Xác minh chính sách và trạng thái repository |
| Phiên cũ chỉ bị logout ở request sau | Hành vi đánh dấu expired rồi filter xử lý | Đây là luồng thông thường; tùy chỉnh expired strategy nếu cần |
| Logout rồi vẫn không đăng nhập được | Session cũ chưa được invalidate hoặc index chưa cập nhật | Kiểm tra logout handler và repository |
| Một principal bị xem thành hai người | Node index principal theo quy tắc khác nhau | Chuẩn hóa principal name/index resolver |
| Giới hạn bị vượt trong login đồng thời | Check-and-register không nguyên tử | Bổ sung điều phối atomic nếu yêu cầu nghiêm ngặt |
| URL expired redirect lặp | Endpoint expired yêu cầu authentication | Cho phép truy cập endpoint expired |
| Test pass với mock nhưng fail production | Mock không mô phỏng index, Redis/JDBC và nhiều node | Dùng integration test với store thật |

## 17. Nguyên tắc triển khai

- Chọn rõ maximumSessions(n) và quyết định giữ phiên cũ hay từ chối phiên mới.
- Dùng maxSessionsPreventsLogin(true) để từ chối login mới; dùng false để chấp nhận login mới và đánh dấu phiên cũ hết hạn.
- Dùng SpringSessionBackedSessionRegistry khi cần kiểm soát phiên trên nhiều instance.
- Bảo đảm repository triển khai FindByIndexNameSessionRepository và index principal hoạt động.
- Đồng bộ principal name, session repository, namespace và security configuration trên mọi node.
- Hiểu ConcurrentSessionFilter xử lý phiên expired ở request kế tiếp; đánh dấu expired không đồng nghĩa xóa vật lý ngay.
- Phối hợp maximumSessions với session creation policy, fixation protection, SecurityContextRepository và logout.
- Tùy chỉnh failure/expired response rõ ràng cho web hoặc REST API.
- Kiểm thử cả hai chính sách, chuyển node, logout, timeout, session fixation và hai lần login đồng thời.
- Nếu giới hạn là ràng buộc nghiêm ngặt dưới tải đồng thời, đánh giá cơ chế atomic coordination bổ sung.

maximumSessions đặt chính sách số phiên theo principal; maxSessionsPreventsLogin quyết định phiên mới bị từ chối hay phiên cũ bị hết hạn. Trong cụm Spring Session, SpringSessionBackedSessionRegistry và repository có principal index giúp các node cùng nhìn thấy phiên của người dùng. Khi cấu hình đồng bộ và kiểm thử qua nhiều instance, ứng dụng có thể áp dụng giới hạn đăng nhập nhất quán và thông báo đúng cho thiết bị bị từ chối hoặc bị kết thúc phiên.
