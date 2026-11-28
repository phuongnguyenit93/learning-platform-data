# Phân biệt idle timeout với giới hạn tuổi thọ tuyệt đối

Trong Spring Session, một phiên có thể được lưu ở Redis hoặc JDBC để nhiều instance của ứng dụng cùng sử dụng. Việc lưu session ở kho dữ liệu dùng chung giải quyết vấn đề chia sẻ trạng thái, nhưng ứng dụng vẫn phải quyết định phiên được phép tồn tại trong bao lâu. Hai chính sách thời gian thường gặp là **idle timeout** và **absolute timeout**.

Idle timeout giới hạn khoảng thời gian phiên không có request được ghi nhận. Absolute timeout giới hạn tổng tuổi của phiên hoặc thời gian kể từ lúc người dùng xác thực, kể cả khi người dùng liên tục hoạt động. Hai chính sách giải quyết hai rủi ro khác nhau và thường được áp dụng đồng thời.

## 1. Idle timeout là gì?

Idle timeout, còn gọi là inactivity timeout, là khoảng thời gian tối đa một phiên được phép không hoạt động. Khi có request hợp lệ gắn với session, mốc truy cập cuối được cập nhật và khoảng chờ được tính lại.

Giả sử ứng dụng đặt idle timeout là 30 phút:

- Người dùng gửi request lúc 09:00. Phiên có thể hết hạn nếu không có request tiếp theo trước 09:30.
- Người dùng gửi request tiếp theo lúc 09:20. Mốc truy cập cuối được làm mới; thời hạn inactivity tiếp theo được tính từ lần truy cập này.
- Nếu request tiếp theo đến lúc 09:55, phiên đã vượt quá khoảng không hoạt động 30 phút và không còn hợp lệ.

Về mặt khái niệm:

```text
idleDuration = now - lastAccessedTime
idleExpired  = idleDuration >= idleTimeout
```

`lastAccessedTime` là thời điểm request gần nhất được hệ thống ghi nhận gắn với session. Nó không nhất thiết là thời điểm người dùng bấm chuột hoặc gõ phím. Một request AJAX, polling hoặc heartbeat gửi kèm cookie phiên có thể làm session tiếp tục hoạt động dù người dùng không tương tác trực tiếp.

Trong Servlet API, `HttpSession.getMaxInactiveInterval()` trả về số giây không hoạt động tối đa; `setMaxInactiveInterval(int)` thay đổi giá trị này cho phiên. Spring Session cung cấp API tương ứng trên `Session` với kiểu `Duration`. Giá trị không dương trong API Servlet biểu thị không áp dụng timeout do inactivity; cần tránh vô tình cấu hình `0` khi mong muốn phiên hết hạn nhanh.

## 2. Absolute timeout là gì?

Absolute timeout là giới hạn tuổi thọ tối đa của phiên. Khi đạt giới hạn này, phiên phải hết hiệu lực dù người dùng vừa gửi request cách đây vài giây.

Ví dụ, một ứng dụng đặt absolute timeout tám giờ kể từ lúc đăng nhập. Người dùng có thể gửi request đều đặn và không bao giờ chạm idle timeout 30 phút, nhưng sau tám giờ họ vẫn phải xác thực lại.

Nếu dùng thời điểm xác thực thành công làm mốc, có thể biểu diễn:

```text
sessionAge       = now - authenticatedAt
absoluteExpired  = sessionAge >= absoluteTimeout
```

Trong một số chính sách, absolute timeout được tính từ `creationTime` của session. Trong chính sách khác, nó được tính từ lúc người dùng xác thực thành công. Hai mốc này không nhất thiết giống nhau: ứng dụng có thể tạo session ẩn danh trước khi đăng nhập, hoặc thay đổi session ID trong quá trình chống session fixation. Nếu yêu cầu là “tám giờ kể từ lúc đăng nhập”, hãy lưu một timestamp xác thực riêng như `authenticatedAt`, thay vì mặc định coi `creationTime` luôn là thời điểm đăng nhập.

Absolute timeout ngăn việc kéo dài vô hạn một phiên chỉ bằng cách gửi request định kỳ. Nó đặc biệt hữu ích cho tài khoản có quyền cao, hệ thống tài chính, trang quản trị và môi trường có yêu cầu xác thực lại theo chu kỳ.

## 3. So sánh hai chính sách

| Tiêu chí | Idle timeout | Absolute timeout |
|---|---|---|
| Mốc bắt đầu tính | Lần truy cập cuối được ghi nhận | Thời điểm tạo phiên hoặc thời điểm xác thực thành công theo chính sách |
| Điều kiện hết hạn | Không có request trong một khoảng thời gian | Tổng tuổi phiên đạt giới hạn |
| Request mới có làm mới thời hạn? | Có, nếu request được gắn với session | Không |
| Mục đích | Thu hồi phiên bị bỏ quên hoặc không còn sử dụng | Giới hạn thời gian một phiên có thể được sử dụng liên tục |
| Ví dụ | 30 phút không hoạt động | Tối đa 8 giờ sau đăng nhập |

Hai chính sách bổ sung cho nhau. Idle timeout giảm thời gian một phiên bị bỏ quên có thể bị chiếm dụng; absolute timeout giới hạn thời gian tồn tại của credential phiên ngay cả khi nó vẫn đang hoạt động.

## 4. Kết hợp idle timeout và absolute timeout

Khi cả hai chính sách được bật, phiên phải hết hiệu lực ngay khi một trong hai giới hạn bị vượt qua:

```text
expired = idleExpired OR absoluteExpired
```

Ví dụ cấu hình:

- Idle timeout: 30 phút.
- Absolute timeout: 8 giờ kể từ lúc xác thực.
- Người dùng xác thực lúc 08:00.
- Nếu không gửi request sau 08:10, phiên hết hạn do inactivity lúc khoảng 08:40.
- Nếu người dùng hoạt động liên tục, phiên vẫn phải hết hạn do absolute timeout lúc 16:00.

Thời điểm hết hạn hiệu lực có thể được mô tả là mốc sớm hơn giữa hai deadline:

```text
idleDeadline     = lastAccessedTime + idleTimeout
absoluteDeadline = authenticatedAt + absoluteTimeout
effectiveDeadline = min(idleDeadline, absoluteDeadline)
```

Đây là mô hình chính sách. Thời điểm xóa dữ liệu vật lý khỏi Redis hoặc JDBC có thể khác thời điểm ứng dụng từ chối phiên. Điều quan trọng là mọi request được bảo vệ phải kiểm tra chính sách hiệu lực trước khi cho phép tiếp tục.

## 5. Cấu hình idle timeout trong Spring Session

Với Spring Boot và Spring Session, có thể đặt timeout mặc định trong cấu hình ứng dụng. Ví dụ với Redis:

```yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: storefront:sessions
```

Timeout mặc định áp dụng cho session được quản lý bởi cấu hình Spring Session tương ứng. Tên namespace giúp phân tách dữ liệu giữa ứng dụng hoặc môi trường dùng chung Redis. Hãy kiểm tra cấu hình thực tế và phiên bản Spring Boot/Spring Session của ứng dụng vì cơ chế auto-configuration và thuộc tính được hỗ trợ có thể khác nhau giữa các phiên bản.

Có thể đặt idle timeout riêng cho một session bằng API Servlet:

```java
import jakarta.servlet.http.HttpSession;

void configureIdleTimeout(HttpSession session) {
    session.setMaxInactiveInterval(30 * 60); // 30 phút, đơn vị giây
}
```

Hoặc dùng API Spring Session trực tiếp:

```java
import java.time.Duration;
import org.springframework.session.Session;

void configureIdleTimeout(Session session) {
    session.setMaxInactiveInterval(Duration.ofMinutes(30));
}
```

Khi request tiếp theo sử dụng session, `lastAccessedTime` được cập nhật theo vòng đời request và repository thực hiện lưu/điều chỉnh thời hạn theo backend. Với Redis, TTL hỗ trợ loại bỏ dữ liệu hết hạn; với JDBC, Spring Session quản lý thời điểm hết hạn và cơ chế dọn dẹp theo repository. Không tự sửa Redis key hoặc cột thời hạn trong SQL để thay đổi timeout, vì việc đó có thể làm lệch metadata và quy trình quản lý phiên.

## 6. Thiết kế absolute timeout

`maxInactiveInterval` chỉ biểu diễn idle timeout. Nó không tự giới hạn tuổi đời tuyệt đối của một phiên có request liên tục. Vì vậy, ứng dụng cần lưu mốc tuyệt đối và kiểm tra nó trong luồng request được bảo vệ.

### 6.1. Lưu thời điểm xác thực thành công

Sau khi xác thực thành công, lưu timestamp vào session. Ví dụ dưới đây là thao tác có thể gọi từ authentication success handler của ứng dụng:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.time.Instant;

final class AuthenticationSessionMetadata {

    static final String AUTHENTICATED_AT = "security.authenticatedAt";

    void markAuthenticated(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute(AUTHENTICATED_AT, Instant.now().toEpochMilli());
        session.setMaxInactiveInterval(30 * 60);
    }
}
```

Hãy gọi thao tác này sau khi đăng nhập thành công và sau khi Spring Security áp dụng chiến lược bảo vệ session fixation. Cách này giúp timestamp xác thực được gắn với session đang tiếp tục sử dụng. Khi ứng dụng dùng cơ chế xác thực stateless, không nên tạo session chỉ để lưu timestamp này.

Nếu chính sách tính từ lúc session được tạo, có thể dùng `HttpSession.getCreationTime()` thay vì thuộc tính riêng. Tuy nhiên, cần xác định rõ hành vi mong muốn khi session ẩn danh được tạo trước đăng nhập, khi session ID được thay đổi, hoặc khi session được migrate. Mốc xác thực riêng thường diễn đạt chính xác hơn chính sách “tối đa N giờ sau đăng nhập”.

### 6.2. Kiểm tra absolute timeout trên request

Một filter có thể kiểm tra mốc xác thực trước khi request tới tài nguyên được bảo vệ. Ví dụ dưới đây giả định filter chạy sau `SessionRepositoryFilter` và sau bước nạp `SecurityContext`, nhưng trước bước phân quyền cho request:

```java
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class AbsoluteSessionTimeoutFilter extends OncePerRequestFilter {

    private static final String AUTHENTICATED_AT =
            "security.authenticatedAt";

    private final Duration absoluteTimeout = Duration.ofHours(8);

    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {

        HttpSession session = request.getSession(false);
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        boolean authenticated = authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);

        if (authenticated && session != null) {
            Object value = session.getAttribute(AUTHENTICATED_AT);

            // Phiên đã xác thực nhưng thiếu mốc thời gian: yêu cầu đăng nhập lại.
            if (!(value instanceof Long)) {
                expireSession(session, response);
                return;
            }

            Instant authenticatedAt = Instant.ofEpochMilli((Long) value);
            Instant absoluteDeadline = authenticatedAt.plus(absoluteTimeout);

            if (!Instant.now().isBefore(absoluteDeadline)) {
                expireSession(session, response);
                return;
            }
        }

        filterChain.doFilter(request, response);
    }

    private void expireSession(HttpSession session,
            HttpServletResponse response) throws IOException {
        SecurityContextHolder.clearContext();
        session.invalidate();
        response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
                "Session expired; authenticate again");
    }
}
```

Đây là ví dụ minh họa cho Servlet và Spring Security; trong ứng dụng thực tế, hãy đưa timeout vào cấu hình có thể thay đổi theo môi trường, xử lý redirect/JSON response theo loại client và đăng ký filter ở vị trí phù hợp trong security filter chain. Với Spring Security hiện đại, có thể thêm filter trước `AuthorizationFilter` để bảo đảm `SecurityContext` đã được nạp và kiểm tra trước khi quyết định quyền truy cập. Filter phải chạy sau `SessionRepositoryFilter` để `getSession(false)` đọc đúng session được chia sẻ.

Chính sách thiếu timestamp cần được xác định rõ. Ví dụ trên chọn cách từ chối phiên đã xác thực nhưng không có mốc `authenticatedAt`, nhằm tránh các session cũ vượt qua absolute timeout. Khi triển khai lần đầu trên hệ thống đang có session hoạt động, cần có kế hoạch chuyển đổi: yêu cầu người dùng đăng nhập lại, hoặc gán mốc thời gian theo một quy tắc migration được phê duyệt. Không tự động coi mọi session thiếu timestamp là mới nếu điều đó làm vô hiệu hóa chính sách tuổi thọ tuyệt đối.

Khi absolute timeout xảy ra, `invalidate()` làm phiên không còn hợp lệ và Spring Session xóa phiên qua repository theo vòng đời filter. Cookie session cần được hết hạn để trình duyệt ngừng gửi ID cũ. Đối với API, có thể trả `401 Unauthorized`; đối với ứng dụng web, có thể chuyển hướng đến trang đăng nhập theo thiết kế bảo mật.

## 7. Chọn mốc thời gian đúng cho chính sách

Không phải mọi ứng dụng đều định nghĩa tuổi phiên theo cùng một mốc. Cần viết rõ chính sách trước khi triển khai:

| Mốc thời gian | Cách lấy | Phù hợp khi |
|---|---|---|
| Tạo session | `HttpSession.getCreationTime()` hoặc `Session.getCreationTime()` | Giới hạn tổng tuổi của session kể từ khi repository tạo nó |
| Xác thực thành công | Thuộc tính session `authenticatedAt` được ghi trong authentication success flow | Giới hạn thời gian đăng nhập của người dùng |
| Bắt đầu một nghiệp vụ nhạy cảm | Timestamp riêng của luồng nghiệp vụ | Giới hạn thời gian của một bước phê duyệt hoặc giao dịch cụ thể |

Ví dụ, một người dùng mở trang chủ lúc 08:00 và nhận session ẩn danh. Họ đăng nhập lúc 08:15. Nếu absolute timeout là tám giờ sau đăng nhập, deadline phải là 16:15, không phải 16:00. Lưu `authenticatedAt` giúp biểu diễn chính xác yêu cầu đó.

Nếu người dùng đăng nhập lại hoặc thực hiện xác thực tăng cường, quyết định có đặt lại absolute deadline hay không phải theo chính sách bảo mật. Một lần refresh token, một request AJAX hoặc một thao tác đọc session không nên tự động kéo dài absolute timeout. Nếu muốn xác thực lại tạo một phiên mới, hãy thực hiện qua luồng xác thực và ghi mốc mới có chủ đích.

## 8. Session ID rotation và xác thực lại

Spring Security có thể thay đổi session ID sau đăng nhập để giảm nguy cơ session fixation. Việc thay ID không nên được hiểu là người dùng đã đăng nhập lại và nhận thêm toàn bộ thời gian absolute mới. Nếu chính sách tính từ thời điểm xác thực ban đầu, giữ nguyên `authenticatedAt` qua quá trình đổi ID.

Khi người dùng thực hiện xác thực lại đầy đủ, ứng dụng có thể đặt lại `authenticatedAt` nếu chính sách cho phép. Khi chỉ làm mới cookie, gia hạn idle timeout hoặc gửi heartbeat, không đặt lại timestamp này. Điều đó giữ cho hai bộ đếm có ý nghĩa riêng biệt.

Đối với “remember me” hoặc cơ chế tự động đăng nhập, cần xác định phiên mới có được tính là một lần xác thực mới hay chỉ là phiên được khôi phục từ credential dài hạn. Absolute timeout của session không tự động giới hạn tuổi của remember-me token hoặc refresh token; những credential đó cần chính sách hết hạn và thu hồi riêng.

## 9. Tác động của Redis, JDBC và nhiều instance

Với Spring Session, `lastAccessedTime`, `maxInactiveInterval` và các thuộc tính session được lưu qua repository dùng chung. Redis có thể dùng TTL để tự động dọn dữ liệu hết hạn; JDBC lưu metadata và thời điểm hết hạn để repository xác định session không còn hợp lệ và dọn bản ghi theo cơ chế tương ứng.

Absolute timeout thường được kiểm tra ở tầng ứng dụng dựa trên timestamp lưu trong session. Vì vậy:

- Tất cả instance phải dùng cùng repository, namespace Redis hoặc schema JDBC và cùng cách tuần tự hóa thuộc tính.
- Tất cả instance phải thực hiện cùng chính sách absolute timeout; không để mỗi node có một giá trị khác nhau.
- Đồng hồ hệ thống cần được đồng bộ. Nếu instance A và B lệch giờ, một request có thể được chấp nhận ở node này nhưng bị từ chối ở node khác.
- Việc session bị từ chối ở absolute deadline không có nghĩa Redis key hoặc JDBC row nhất thiết biến mất đúng thời điểm đó. Dữ liệu có thể được dọn khi TTL inactivity hết hạn hoặc khi cơ chế cleanup chạy.
- Mỗi request phải kiểm tra session hợp lệ ở phía máy chủ. Không dựa vào việc cookie còn tồn tại ở trình duyệt để kết luận phiên vẫn được phép sử dụng.

Nếu yêu cầu vận hành đòi hỏi dữ liệu phải bị xóa vật lý ngay tại absolute deadline dù không có request mới, cần thêm cơ chế cleanup có kiểm soát hoặc thiết kế TTL riêng phù hợp với backend. Không sửa trực tiếp key hay row nội bộ của Spring Session để giả lập chính sách đó; hãy dùng API repository hoặc một cơ chế lưu trữ được hỗ trợ.

## 10. Các tình huống dễ gây hiểu nhầm

### Request nền giữ phiên luôn hoạt động

Một ứng dụng có thể gửi heartbeat mỗi năm phút để giữ kết nối hoặc cập nhật dữ liệu. Nếu heartbeat mang cookie phiên, nó có thể làm mới idle timeout. Người vận hành nhìn thấy người dùng “không thao tác” nhưng session vẫn còn hiệu lực. Hãy xem xét liệu heartbeat có thực sự cần kéo dài phiên đăng nhập hay nên dùng một endpoint không tạo/không làm mới session.

### Idle timeout dài hơn absolute timeout

Nếu idle timeout là 12 giờ nhưng absolute timeout là 8 giờ, absolute timeout phải thắng. Nếu chỉ cấu hình `maxInactiveInterval`, session có thể tiếp tục tồn tại quá giới hạn tuyệt đối khi vẫn có request. Cần kiểm tra absolute deadline ở tầng ứng dụng.

### Absolute timeout bị đặt lại ở mọi request

Nếu code cập nhật `authenticatedAt = now` ở mỗi request, chính sách absolute timeout biến thành idle timeout thứ hai. Chỉ đặt mốc này ở sự kiện xác thực thành công hoặc một sự kiện tái xác thực được cho phép.

### Phiên bị xóa nhưng token vẫn dùng được

Xóa `HttpSession` không tự thu hồi JWT hoặc access token stateless đã phát hành. Nếu hệ thống dùng nhiều loại credential, phải áp dụng expiration, revocation hoặc token introspection phù hợp cho từng loại.

### Thời gian hết hạn vật lý khác thời gian hết hạn logic

Repository có thể giữ lại dữ liệu hết hạn một khoảng ngắn để cleanup. Điều đó không có nghĩa ứng dụng được phép chấp nhận session. Quyết định truy cập phải dựa trên trạng thái hết hạn và chính sách, không dựa vào việc key/row còn nhìn thấy trong kho dữ liệu.

## 11. Kiểm thử cả hai timeout

Kiểm thử cần xác minh hai bộ đếm độc lập. Một số kịch bản quan trọng:

1. **Idle timeout:** tạo session với timeout ngắn, không gửi request trong khoảng vượt ngưỡng, sau đó xác nhận session không còn được chấp nhận.
2. **Idle được làm mới:** gửi request trước khi idle timeout đạt ngưỡng, xác nhận session tiếp tục hợp lệ và mốc truy cập cuối được cập nhật.
3. **Absolute timeout:** đặt `authenticatedAt` lùi quá absolute timeout nhưng gửi request gần đây; xác nhận filter vẫn từ chối session.
4. **Request đều đặn:** gửi request thường xuyên để giữ idle timeout chưa hết, rồi xác nhận absolute timeout vẫn kết thúc phiên.
5. **Session thiếu mốc xác thực:** xác nhận chính sách migration hoặc từ chối phiên được thực hiện nhất quán.
6. **Session ID rotation:** đăng nhập qua Spring Security, xác nhận session ID có thể thay đổi nhưng `authenticatedAt` vẫn được giữ nguyên.
7. **Xác thực lại:** xác nhận timestamp chỉ được đặt lại khi luồng xác thực lại được chính sách cho phép.
8. **Nhiều instance:** tạo phiên ở instance A, gửi request qua instance B và xác nhận cả idle lẫn absolute timeout được áp dụng như nhau.
9. **Credential khác:** nếu có JWT hoặc remember-me token, kiểm thử riêng thời hạn của chúng thay vì giả định session timeout đã thu hồi chúng.

Để kiểm thử thời gian ổn định, nên tiêm `Clock` vào thành phần kiểm tra absolute timeout thay vì gọi trực tiếp `Instant.now()` ở mọi nơi. Bài kiểm thử có thể dùng clock cố định hoặc clock điều khiển được để tiến thời gian mà không phải chờ lâu bằng `Thread.sleep()`. Với Redis/JDBC, cần có kiểm thử tích hợp để xác nhận TTL, lưu thuộc tính và hành vi repository thực tế.

Ví dụ dùng `Clock`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

final class AbsoluteDeadlinePolicy {
    private final Clock clock;
    private final Duration maximumAge;

    AbsoluteDeadlinePolicy(Clock clock, Duration maximumAge) {
        this.clock = clock;
        this.maximumAge = maximumAge;
    }

    boolean isExpired(Instant authenticatedAt) {
        Instant deadline = authenticatedAt.plus(maximumAge);
        return !clock.instant().isBefore(deadline);
    }
}
```

Trong production, có thể inject `Clock.systemUTC()`. Trong kiểm thử, dùng clock cố định hoặc clock giả có thể điều khiển để kiểm tra chính xác thời điểm trước, tại và sau deadline.

## 12. Nguyên tắc triển khai

- Dùng idle timeout để kết thúc phiên bị bỏ quên; cấu hình qua `maxInactiveInterval` hoặc timeout mặc định Spring Session.
- Dùng absolute timeout để giới hạn tổng tuổi phiên, kể cả khi request liên tục làm mới last access.
- Kết hợp hai chính sách bằng điều kiện hết hạn khi một trong hai deadline bị vượt qua.
- Nếu giới hạn tính từ lúc đăng nhập, lưu `authenticatedAt` sau xác thực thành công; không mặc định `creationTime` luôn là thời điểm đăng nhập.
- Không đặt lại `authenticatedAt` trong request thông thường, polling hoặc heartbeat.
- Kiểm tra absolute timeout trong filter hoặc thành phần bảo mật chạy trên mọi request được bảo vệ, sau khi session và security context đã được nạp.
- Dùng `invalidate()` để kết thúc session qua Spring Session; để repository quản lý việc xóa và cookie resolver xử lý session ID.
- Đồng bộ cấu hình và đồng hồ giữa các instance; kiểm thử với Redis/JDBC thực tế.
- Quản lý thời hạn và thu hồi JWT, remember-me token hoặc credential stateless bằng chính sách riêng.
