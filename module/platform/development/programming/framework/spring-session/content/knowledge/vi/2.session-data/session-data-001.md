# Định danh phiên, thời điểm tạo, lần truy cập cuối và khoảng không hoạt động

Trong ứng dụng web, một request HTTP thường độc lập với request tiếp theo. Spring Session duy trì trạng thái giữa các request bằng một phiên (session) được lưu trong kho dữ liệu dùng chung, chẳng hạn Redis hoặc JDBC. Trình duyệt gửi định danh phiên qua cookie; Spring Session dùng định danh đó để tìm dữ liệu phiên và cung cấp lại qua API `HttpSession` quen thuộc của Servlet.

Khi vận hành nhiều instance ứng dụng, cần hiểu rõ bốn thông tin thường được dùng để theo dõi vòng đời phiên: **session ID**, **creation time**, **last accessed time** và **max inactive interval**. Chúng trả lời những câu hỏi khác nhau: phiên nào đang được tham chiếu, phiên được tạo khi nào, request gần nhất gắn với phiên được ghi nhận lúc nào, và phiên có thể không hoạt động trong bao lâu trước khi hết hạn.

## 1. Bốn thuộc tính mô tả vòng đời phiên

| Thuộc tính | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `id` | Chuỗi định danh phiên do hệ thống tạo | Tra cứu phiên trong repository và liên kết cookie với dữ liệu phiên |
| `creationTime` | Thời điểm phiên được tạo | Tính tuổi phiên và áp dụng giới hạn tuổi tuyệt đối |
| `lastAccessedTime` | Thời điểm request gần nhất gắn với phiên được ghi nhận | Ước tính thời gian phiên không hoạt động |
| `maxInactiveInterval` | Khoảng thời gian không hoạt động tối đa | Xác định ngưỡng hết hạn do inactivity |

### 1.1. Session ID — định danh phiên

Session ID là một định danh khó đoán, thường được sinh ngẫu nhiên. Nó đóng vai trò khóa để Spring Session tìm đúng bản ghi phiên trong Redis, JDBC hoặc repository khác. Cookie gửi từ trình duyệt thường chỉ mang định danh này; các thuộc tính và dữ liệu phiên nằm ở phía máy chủ.

Spring Session thường dùng cookie tên `SESSION` với cấu hình mặc định của cookie serializer. Tên cookie, domain, path và các thuộc tính bảo mật có thể được tùy chỉnh. Nếu ứng dụng vẫn dùng trực tiếp session của Servlet container mà không có Spring Session, tên cookie thường gặp là `JSESSIONID`.

Không dùng session ID làm mã người dùng, mã đơn hàng hoặc định danh nghiệp vụ. Một người dùng có thể có nhiều phiên trên các trình duyệt hoặc thiết bị khác nhau. ID cũng có thể thay đổi trong quá trình xác thực để chống session fixation, ví dụ khi ứng dụng gọi `HttpServletRequest.changeSessionId()` hoặc Spring Security thực hiện chính sách bảo vệ phiên. Vì vậy, không nên lưu ID như một định danh lâu dài.

Session ID tương đương một thông tin xác thực dạng bearer: người có ID hợp lệ có thể được máy chủ nhận diện là đang sở hữu phiên. Không ghi ID thô vào log, URL, hệ thống phân tích hoặc thông báo lỗi. Nếu cần đối chiếu log, hãy dùng một giá trị đã băm hoặc một mã tương quan riêng. Cookie phiên nên được cấu hình phù hợp với HTTPS, `HttpOnly`, `Secure` và `SameSite` theo mô hình triển khai.

### 1.2. Creation time — thời điểm tạo phiên

`creationTime` là mốc thời gian phiên được tạo lần đầu. Việc đọc hoặc cập nhật thuộc tính trong phiên không làm thay đổi mốc này. Khi phiên bị hủy và một phiên mới được tạo, phiên mới có ID và creation time mới.

Thời điểm tạo hữu ích để:

- Tính tuổi phiên: `sessionAge = now - creationTime`.
- Áp dụng giới hạn tuổi tuyệt đối, ví dụ yêu cầu người dùng xác thực lại sau tám giờ kể từ lúc đăng nhập.
- Điều tra phiên bất thường được tạo vào thời điểm nào.

Creation time không thể thay thế last accessed time. Một phiên được tạo từ sáng và vẫn có request đều đặn có thể đã tồn tại nhiều giờ nhưng chưa vượt quá idle timeout.

### 1.3. Last accessed time — lần truy cập cuối

`lastAccessedTime` là mốc request gần nhất được hệ thống ghi nhận là gắn với phiên. Nó phục vụ việc tính thời gian không hoạt động. Đây không phải thời điểm cuối cùng người dùng thao tác trên giao diện, cũng không nhất thiết là thời điểm cuối cùng một thuộc tính session được đọc hoặc ghi.

Ví dụ, một trang có thể gửi request AJAX định kỳ kèm cookie phiên. Những request này có thể làm phiên tiếp tục được xem là hoạt động dù người dùng không tương tác trực tiếp. Ngược lại, một tác vụ chạy nền trên máy chủ không mang ngữ cảnh `HttpSession` sẽ không tự động cập nhật last accessed time của phiên người dùng.

Thời điểm chính xác mà ứng dụng quan sát được phụ thuộc vòng đời request và thời điểm Spring Session lưu phiên. Khi một request đã được gắn với phiên, chính request đang dùng để kiểm tra metadata cũng có thể được tính là một lần truy cập. Do đó, endpoint chẩn đoán đọc `lastAccessedTime` có thể thấy giá trị rất gần thời điểm hiện tại. Nếu cần đo khoảng idle trước request hiện tại, phải ghi nhận mốc đó trước khi phiên được làm mới trong vòng đời request hoặc đọc snapshot đã lưu trước đó.

### 1.4. Max inactive interval — khoảng không hoạt động tối đa

`maxInactiveInterval` là khoảng thời gian phiên được phép không có request gắn với nó trước khi bị xem là hết hạn. Đây là idle timeout, không phải tuổi thọ tối đa tính từ lúc tạo.

Với:

- `lastAccessedTime`: thời điểm truy cập cuối được ghi nhận;
- `maxInactiveInterval`: khoảng không hoạt động tối đa;
- `now`: thời điểm hiện tại;

ta có thể ước tính:

```text
idleDuration = now - lastAccessedTime
expiresAt    = lastAccessedTime + maxInactiveInterval
expired      = idleDuration >= maxInactiveInterval
```

Giả sử idle timeout là 30 phút. Nếu request tiếp theo gắn với phiên đến sau 20 phút, thời điểm truy cập cuối được cập nhật và đồng hồ inactivity bắt đầu lại. Người dùng có thể duy trì cùng một phiên lâu hơn 30 phút, miễn là có request phù hợp trước khi phiên hết hạn. Muốn giới hạn cả tuổi đời phiên, ứng dụng phải bổ sung chính sách absolute timeout dựa trên `creationTime`.

Trong API Servlet, `HttpSession.getMaxInactiveInterval()` trả về số giây. Giá trị không dương biểu thị không áp dụng timeout do inactivity theo hợp đồng Servlet. API `Session` của Spring Session biểu diễn khoảng này bằng `java.time.Duration`. Hãy kiểm tra đơn vị khi chuyển đổi giữa hai API để tránh lỗi nhân hoặc chia 1.000 lần.

## 2. Đọc metadata qua API Spring Session và Servlet

Spring Session bọc API `HttpSession`, vì vậy phần lớn mã ứng dụng có thể tiếp tục dùng `HttpServletRequest` và `HttpSession` mà không phụ thuộc trực tiếp vào Redis hay JDBC.

| Thông tin | `HttpSession` | `org.springframework.session.Session` |
|---|---|---|
| Định danh | `getId()` | `getId()` |
| Thời điểm tạo | `getCreationTime()` — epoch milliseconds | `getCreationTime()` — `Instant` |
| Truy cập cuối | `getLastAccessedTime()` — epoch milliseconds | `getLastAccessedTime()` — `Instant` |
| Idle timeout | `getMaxInactiveInterval()` — giây | `getMaxInactiveInterval()` — `Duration` |
| Thay đổi idle timeout | `setMaxInactiveInterval(int)` — giây | `setMaxInactiveInterval(Duration)` |
| Kiểm tra hết hạn | Do Servlet container/Spring Session quản lý | `isExpired()` |

Ví dụ dưới đây trả về metadata cơ bản cho một request. `getSession(false)` lấy phiên hiện có nếu request mang phiên hợp lệ; nó không tạo phiên mới khi không tìm thấy phiên. Điều này phù hợp với endpoint chẩn đoán vì một request kiểm tra trạng thái không nên tự tạo session rỗng.

```java
import java.time.Instant;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionMetadataController {

    record SessionMetadata(
            Instant createdAt,
            Instant lastAccessedAt,
            int maxInactiveIntervalSeconds) {
    }

    @GetMapping("/internal/session/metadata")
    ResponseEntity<SessionMetadata> metadata(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.noContent().build();
        }

        SessionMetadata metadata = new SessionMetadata(
                Instant.ofEpochMilli(session.getCreationTime()),
                Instant.ofEpochMilli(session.getLastAccessedTime()),
                session.getMaxInactiveInterval());

        return ResponseEntity.ok(metadata);
    }
}
```

Endpoint này chỉ là ví dụ cho công cụ nội bộ. Không đưa session ID, thuộc tính xác thực hoặc dữ liệu cá nhân vào response chẩn đoán. Hãy giới hạn quyền truy cập endpoint và tránh bật nó công khai trong môi trường production nếu không có nhu cầu vận hành rõ ràng.

Nếu cần tính idle duration từ một snapshot đã lưu, có thể dùng `Duration`:

```java
Instant now = Instant.now();
Instant lastAccessedAt = Instant.ofEpochMilli(session.getLastAccessedTime());
Duration idleDuration = Duration.between(lastAccessedAt, now);

int timeoutSeconds = session.getMaxInactiveInterval();
boolean idleTimeoutDisabled = timeoutSeconds <= 0;
boolean idleTimeoutReached = !idleTimeoutDisabled
        && idleDuration.compareTo(Duration.ofSeconds(timeoutSeconds)) >= 0;
```

Đoạn tính toán trên minh họa quy tắc. Nếu chạy bên trong request đã làm mới `lastAccessedTime`, `idleDuration` có thể rất nhỏ. Với phép đo trước request, hãy ghi nhận timestamp trước bước cập nhật phiên hoặc lấy snapshot đã lưu trước đó. Đồng hồ giữa các instance cũng cần được đồng bộ; nếu lệch giờ, phép tính dựa trên timestamp của instance khác có thể sai.

## 3. Cấu hình idle timeout

Trong ứng dụng Spring Boot dùng Spring Session, có thể đặt timeout mặc định trong cấu hình. Ví dụ với Redis:

```yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: storefront:sessions
  data:
    redis:
      host: localhost
      port: 6379
```

`spring.session.timeout` đặt idle timeout mặc định cho phiên. Namespace giúp các ứng dụng hoặc môi trường dùng chung Redis tránh đụng tên dữ liệu phiên. Cấu hình kết nối Redis phải trỏ đến cùng kho dữ liệu mà tất cả instance ứng dụng cần chia sẻ.

Có thể đặt timeout riêng cho một phiên thông qua API Servlet:

```java
HttpSession session = request.getSession();
session.setMaxInactiveInterval(15 * 60); // 15 phút, đơn vị giây
```

Hoặc khi thao tác trực tiếp với API Spring Session:

```java
session.setMaxInactiveInterval(Duration.ofMinutes(15));
```

Giá trị được đặt trên phiên có thể ghi đè timeout mặc định của ứng dụng cho phiên đó. Chỉ thay đổi timeout khi có chính sách nghiệp vụ cụ thể; nếu mỗi request đều đặt lại một giá trị khác nhau, hành vi hết hạn sẽ khó dự đoán và khó điều tra.

Đối với JDBC, Spring Session lưu metadata phiên trong bảng `SPRING_SESSION` và các thuộc tính trong bảng liên quan `SPRING_SESSION_ATTRIBUTES`. Những cột thường dùng để kiểm tra vòng đời gồm `SESSION_ID`, `CREATION_TIME`, `LAST_ACCESS_TIME`, `MAX_INACTIVE_INTERVAL` và `EXPIRY_TIME`. Schema phải được tạo theo phiên bản Spring Session đang dùng; trong production nên quản lý schema bằng quy trình migration của ứng dụng.

Không cập nhật trực tiếp các cột metadata hoặc Redis key để kéo dài/hủy phiên. Hãy dùng `HttpSession.invalidate()`, `SessionRepository` hoặc API quản lý phiên tương ứng để Spring Session thực hiện đúng quy trình lưu, xóa và phát sự kiện.

## 4. Idle timeout và absolute timeout là hai chính sách khác nhau

Idle timeout chỉ giới hạn khoảng thời gian không có request. Nó không giới hạn tổng tuổi đời của phiên. Nếu người dùng liên tục gửi request, phiên có thể tiếp tục tồn tại rất lâu.

Absolute timeout giới hạn thời gian kể từ `creationTime`, bất kể phiên có hoạt động hay không. Ví dụ, một hệ thống có thể đặt idle timeout 30 phút và absolute timeout tám giờ. Khi request đến, ứng dụng kiểm tra cả hai điều kiện:

```text
idleDuration = now - lastAccessedTime
sessionAge   = now - creationTime

hết hạn nếu:
    idleDuration >= idleTimeout
    hoặc sessionAge >= absoluteTimeout
```

Với chính sách absolute timeout, ứng dụng cần tự triển khai kiểm tra ở một điểm chung của request, chẳng hạn filter bảo mật hoặc thành phần quản lý xác thực. Khi vượt ngưỡng, hủy phiên bằng `invalidate()` và yêu cầu xác thực lại. Không thay `creationTime` để làm mới tuổi phiên; nếu người dùng xác thực lại và chính sách yêu cầu một phiên mới, hãy tạo phiên mới theo luồng xác thực.

## 5. Điều gì xảy ra khi ứng dụng chạy nhiều instance?

Với Spring Session, `SessionRepositoryFilter` bọc request/response và kết nối API `HttpSession` với `SessionRepository`. Khi request có cookie phiên đến một instance, filter tìm phiên trong repository dùng chung. Những thay đổi trong request được lưu lại theo cơ chế của repository và cấu hình flush/save mode. Instance tiếp theo có thể đọc cùng phiên vì dữ liệu không chỉ nằm trong bộ nhớ của instance đầu tiên.

Để hành vi nhất quán, các instance cần dùng chung cấu hình repository, Redis namespace hoặc JDBC schema, cách tuần tự hóa dữ liệu và cấu hình cookie. Nếu hai instance trỏ đến hai Redis database hoặc namespace khác nhau, cùng một cookie có thể được hiểu là phiên không tồn tại ở một trong hai instance. Khi đó ứng dụng có thể tạo phiên mới và người dùng bị đăng xuất ngẫu nhiên sau khi load balancer chuyển request.

Một số điểm cần lưu ý khi vận hành:

- **TTL và thời điểm hết hạn:** repository có thể dùng TTL hoặc cơ chế dọn dẹp để loại bỏ dữ liệu hết hạn. Bản ghi/key còn nhìn thấy trong kho dữ liệu không phải bằng chứng rằng phiên vẫn hợp lệ; hãy để Spring Session kiểm tra trạng thái hết hạn.
- **Độ trễ dọn dẹp:** việc xóa dữ liệu vật lý có thể diễn ra sau thời điểm phiên được xem là hết hạn. Không dùng thời điểm key biến mất làm căn cứ duy nhất cho logic xác thực.
- **Request đồng thời:** hai request cùng dùng một session ID có thể đọc và ghi phiên gần như đồng thời. Metadata `lastAccessedTime` là thông tin vận hành, không phải nhật ký thứ tự tuyệt đối. Những cập nhật thuộc tính đồng thời cũng cần được thiết kế để tránh ghi đè dữ liệu nghiệp vụ.
- **Đồng hồ hệ thống:** các instance nên đồng bộ thời gian. Chênh lệch đồng hồ có thể làm timestamp tạo/truy cập và phép tính idle duration lệch nhau.
- **Sự kiện phiên:** Spring Session có các sự kiện như `SessionDeletedEvent` và `SessionExpiredEvent` để ứng dụng phản ứng khi phiên bị xóa hoặc hết hạn. Với Redis, việc nhận sự kiện hết hạn phụ thuộc cấu hình thông báo keyspace và cơ chế backend. Hãy thiết kế listener có tính idempotent và không coi sự kiện là một nhật ký giao dịch bảo đảm đúng một lần.

Ví dụ listener có thể dùng để thu thập số liệu hoặc dọn tài nguyên phụ trợ:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.session.events.SessionDeletedEvent;
import org.springframework.session.events.SessionExpiredEvent;

@Component
class SessionLifecycleListener {

    @EventListener
    void onExpired(SessionExpiredEvent event) {
        // Ghi metric hoặc thực hiện công việc dọn dẹp có tính idempotent.
    }

    @EventListener
    void onDeleted(SessionDeletedEvent event) {
        // Xử lý khi phiên được ứng dụng chủ động xóa.
    }
}
```

Không dùng listener hết hạn làm cơ chế duy nhất để thu hồi quyền truy cập. Mỗi request vẫn phải đi qua kiểm tra phiên hợp lệ và quyền truy cập ở phía máy chủ.

## 6. Kiểm thử metadata và hết hạn phiên

Kiểm thử nên xác nhận cả giá trị metadata lẫn hành vi khi idle timeout xảy ra.

1. **Phiên mới:** tạo phiên và xác nhận ID tồn tại, creation time được thiết lập, last accessed time có giá trị và timeout bằng cấu hình mặc định.
2. **Phiên đã tồn tại:** gửi request tiếp theo cùng cookie và xác nhận ứng dụng tiếp tục đọc đúng phiên trong repository.
3. **Cập nhật timeout:** đặt timeout riêng cho một phiên, lưu phiên và xác nhận giá trị được đọc lại đúng đơn vị.
4. **Hết hạn do inactivity:** tạo phiên với timeout ngắn, đặt `lastAccessedTime` lùi quá ngưỡng trong bài kiểm thử repository, rồi xác nhận phiên không còn được xem là hợp lệ.
5. **Absolute timeout:** giữ cho phiên có request đều đặn nhưng vượt quá tuổi tối đa; xác nhận chính sách ứng dụng vẫn yêu cầu xác thực lại.
6. **Nhiều instance:** gửi các request luân phiên qua ít nhất hai instance dùng cùng Redis hoặc JDBC repository; xác nhận phiên và thuộc tính được chia sẻ.

Có thể dùng `MockHttpSession` cho kiểm thử đơn vị/controller để kiểm tra cách controller đọc metadata. Tuy nhiên, mock không xác minh TTL, tuần tự hóa hoặc cơ chế lưu của Redis/JDBC. Với các hành vi đó, cần kiểm thử tích hợp bằng repository thực tế, ví dụ Redis trong Testcontainers hoặc cơ sở dữ liệu kiểm thử có schema Spring Session. Tránh phụ thuộc vào `Thread.sleep()` dài trong kiểm thử; có thể điều khiển timestamp trong đối tượng session hoặc dùng cấu hình timeout ngắn kết hợp kiểm thử tích hợp có giới hạn thời gian rõ ràng.

## 7. Lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Người dùng bị đăng xuất dù vẫn thao tác | Request nền không gửi cookie, timeout quá ngắn hoặc instance dùng repository khác | Kiểm tra cookie trên request, timeout hiệu lực, namespace và kết nối kho dữ liệu |
| Phiên tồn tại lâu hơn dự kiến | Request polling/AJAX liên tục làm mới last access hoặc chưa có absolute timeout | Kiểm tra tần suất request gắn với cookie và chính sách tuổi tối đa |
| Idle duration luôn gần 0 | Endpoint đo đã truy cập phiên và cập nhật last access trong request hiện tại | Đo snapshot trước khi cập nhật hoặc tách thời điểm hoạt động nghiệp vụ khỏi session metadata |
| Thời gian tạo/truy cập lệch giữa instance | Đồng hồ máy chủ không đồng bộ hoặc timestamp bị chuyển đổi sai đơn vị | Đồng bộ thời gian, kiểm tra epoch milliseconds, seconds và `Instant` |
| Cùng cookie nhưng có lúc mất phiên | Các instance không dùng chung repository, namespace, schema hoặc serializer | So sánh cấu hình giữa các instance và kiểm tra log repository |
| Redis/JDBC còn dữ liệu sau thời điểm hết hạn | Cơ chế dọn dẹp vật lý có độ trễ | Kiểm tra trạng thái hết hạn qua Spring Session thay vì chỉ nhìn sự tồn tại của key/bản ghi |

Khi ghi log phục vụ điều tra, ưu tiên các trường không nhạy cảm như thời điểm tạo, thời điểm truy cập cuối, timeout, tên instance và mã tương quan request. Nếu phải liên kết nhiều log theo phiên, dùng fingerprint của session ID đã băm và giới hạn quyền truy cập log.

## 8. Nguyên tắc cần nhớ

- `id` xác định bản ghi phiên; nó không phải định danh người dùng và cần được bảo vệ như thông tin xác thực.
- `creationTime` dùng để tính tuổi phiên; `lastAccessedTime` dùng để tính khoảng không hoạt động.
- `maxInactiveInterval` xác định idle timeout. Mốc hết hạn được tính từ lần truy cập cuối, không phải từ lúc tạo phiên.
- Idle timeout không thay thế absolute timeout. Nếu cần giới hạn tổng tuổi phiên, hãy áp dụng chính sách riêng dựa trên creation time.
- `getSession(false)` giúp kiểm tra phiên mà không tạo phiên mới, nhưng request hiện tại vẫn có thể được tính là một lần truy cập.
- Trong môi trường nhiều instance, mọi instance phải chia sẻ cùng session repository và cấu hình liên quan; hãy kiểm thử bằng kho dữ liệu thực tế.
- Metadata phiên phục vụ vận hành và bảo mật. Không dùng `lastAccessedTime` như nhật ký kiểm toán chính xác cho hành động nghiệp vụ.
