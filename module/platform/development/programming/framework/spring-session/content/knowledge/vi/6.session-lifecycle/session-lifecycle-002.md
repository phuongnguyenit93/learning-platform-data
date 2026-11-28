# Cập nhật lần truy cập cuối và thời gian không hoạt động

Trong Spring Session, một phiên có thể hết hạn sau một khoảng thời gian người dùng không gửi request gắn với phiên đó. Cơ chế này dựa trên hai giá trị: **lần truy cập cuối** (`lastAccessedTime`) và **thời gian không hoạt động tối đa** (`maxInactiveInterval`). Khi request hợp lệ tiếp tục sử dụng phiên, mốc truy cập cuối được cập nhật và thời điểm hết hạn được đẩy về phía trước. Khi không còn hoạt động đủ lâu, repository coi phiên đã hết hạn và không trả phiên đó cho ứng dụng.

Đây là cơ chế timeout trượt (sliding inactivity timeout). Nó phù hợp với đăng nhập web, giỏ hàng và trạng thái quy trình ngắn hạn. Để vận hành đúng trong nhiều instance, cần hiểu cách Spring Session cập nhật mốc thời gian, cách repository thực thi TTL, sự khác nhau giữa hết hạn logic và dọn dữ liệu vật lý, cũng như cách kiểm thử request đồng thời.

## 1. Hai mốc thời gian quyết định thời hạn phiên

### 1.1. `lastAccessedTime`

`lastAccessedTime` là thời điểm gần nhất client gửi request được liên kết với phiên. Nó cho biết phiên đã được sử dụng gần đây đến đâu. Trong API Spring Session, giá trị này được biểu diễn bằng `java.time.Instant`:

```java
Instant lastAccessed = session.getLastAccessedTime();
session.setLastAccessedTime(Instant.now());
```

Trong ứng dụng Servlet, `HttpSession.getLastAccessedTime()` trả về số mili giây tính từ epoch; `HttpSession.getMaxInactiveInterval()` trả về số giây. Spring Session ánh xạ khái niệm này sang API `Session` có kiểu `Instant` và `Duration`.

Không nên nhầm `lastAccessedTime` với thời điểm tạo phiên (`creationTime`), thời điểm đăng nhập, thời điểm cập nhật thuộc tính cuối cùng hay thời điểm phản hồi HTTP được gửi xong. Đây là mốc theo dõi lần request gắn với phiên được sử dụng.

### 1.2. `maxInactiveInterval`

`maxInactiveInterval` là khoảng thời gian tối đa một phiên được phép không hoạt động trước khi bị vô hiệu hóa. Trong Spring Session, kiểu dữ liệu là `Duration`:

```java
session.setMaxInactiveInterval(Duration.ofMinutes(30));
Duration allowedIdleTime = session.getMaxInactiveInterval();
```

Nếu thời gian không hoạt động là 30 phút, phiên có thể được dùng tiếp khi request hợp lệ đến trước hạn. Một khoảng thời gian mới được tính từ lần truy cập đó. Nếu không có hoạt động mới, phiên sẽ hết hạn khi vượt qua giới hạn.

API `Session` quy định khoảng thời gian âm có nghĩa phiên không bao giờ hết hạn do inactivity timeout. Đây là lựa chọn cần cân nhắc rất kỹ trong ứng dụng đăng nhập vì phiên có thể tồn tại lâu hơn dự kiến. Với `HttpSession`, `setMaxInactiveInterval(int)` nhận đơn vị giây; giá trị âm cũng biểu thị không timeout. Một số annotation cấu hình repository JDBC yêu cầu số giây không âm, vì vậy cần dùng đúng API và kiểm tra ràng buộc của phiên bản đang sử dụng.

### 1.3. Công thức thời điểm hết hạn

Có thể tính thời điểm hết hạn logic như sau:

\[
T_{expire} = T_{lastAccess} + I_{maxInactive}
\]

Trong đó:

- `T_lastAccess` là `lastAccessedTime`.
- `I_maxInactive` là `maxInactiveInterval`.
- `T_expire` là thời điểm phiên không còn hợp lệ do không hoạt động.

Ví dụ, phiên có lần truy cập cuối lúc 10:00 và thời gian không hoạt động tối đa 30 phút thì hạn logic là 10:30. Nếu người dùng gửi request hợp lệ lúc 10:20, mốc truy cập cuối được cập nhật thành 10:20 và hạn mới là 10:50. Nếu không có request mới trước 10:50, phiên hết hạn.

```mermaid
timeline
    title Timeout trượt 30 phút
    10:00 : Request gắn với session
          : lastAccessedTime = 10:00
          : Hạn dự kiến = 10:30
    10:20 : Request tiếp theo
          : lastAccessedTime = 10:20
          : Hạn mới = 10:50
    10:50 : Không có hoạt động mới
          : Session hết hạn logic
```

Điều này khác với thời hạn tuyệt đối. Nếu yêu cầu bảo mật là “bắt đăng nhập lại sau 8 giờ kể từ lúc đăng nhập dù người dùng vẫn hoạt động”, chỉ đặt `maxInactiveInterval` là chưa đủ. Cần thêm giới hạn tuổi tối đa dựa trên `creationTime`, thời điểm xác thực gần nhất hoặc chính sách của hệ thống định danh.

## 2. Spring Session cập nhật lần truy cập cuối như thế nào?

### 2.1. Khi dùng `HttpSession` trong Servlet

Trong ứng dụng Servlet, Spring Session thay phần triển khai `HttpSession` bằng một implementation dựa trên repository thông qua `SessionRepositoryFilter`. Filter này phải chạy trước các thành phần khác truy cập `HttpSession`, để controller và Spring Security nhìn thấy cùng một phiên do Spring Session quản lý.

Luồng tổng quát:

1. Trình duyệt gửi cookie chứa session ID (hoặc resolver được cấu hình cung cấp ID qua header).
2. `SessionRepositoryFilter` dùng ID để tìm phiên trong repository.
3. Nếu phiên tồn tại và chưa hết hạn, request có thể sử dụng phiên thông qua API `HttpSession`.
4. Trong quá trình xử lý và lưu phiên, Spring Session cập nhật thời điểm truy cập cuối.
5. Repository lưu lại trạng thái phiên và cập nhật thời hạn tương ứng.

Phần lớn ứng dụng không cần tự gọi `setLastAccessedTime()` trong controller. Việc quản lý vòng đời được thực hiện bởi filter và repository. Hãy dùng `HttpSession` theo API Servlet bình thường, đặt timeout phù hợp và để Spring Session quản lý mốc truy cập.

### 2.2. Khi thao tác trực tiếp với `SessionRepository`

Trong code dùng trực tiếp repository, Spring Session tự cập nhật `lastAccessedTime` khi gọi `SessionRepository.save(session)`. Tài liệu API cũng nêu rằng `findById` trả về `null` nếu phiên đã hết hạn. Vì vậy, không nên tự đặt mốc truy cập bằng `Instant.now()` trong mọi service rồi mới lưu, trừ khi đang xây dựng một repository hoặc quy trình đặc biệt có quy tắc riêng.

Ví dụ:

```java
import java.time.Duration;
import java.time.Instant;
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import org.springframework.stereotype.Service;

@Service
public class SessionActivityService<S extends Session> {

    private final SessionRepository<S> repository;

    public SessionActivityService(SessionRepository<S> repository) {
        this.repository = repository;
    }

    public String createSession() {
        S session = this.repository.createSession();
        session.setMaxInactiveInterval(Duration.ofMinutes(30));
        session.setAttribute("purpose", "checkout");
        this.repository.save(session);
        return session.getId();
    }

    public Instant lastActivity(String sessionId) {
        S session = this.repository.findById(sessionId);
        return session == null ? null : session.getLastAccessedTime();
    }
}
```

Trong ví dụ, repository quản lý mốc truy cập khi lưu. Phương thức `lastActivity` trả về `null` nếu ID không tìm thấy hoặc phiên đã hết hạn theo repository. Trong ứng dụng web, nên ưu tiên thao tác gián tiếp qua `HttpSession` thay vì để service nghiệp vụ tự quản lý repository.

### 2.3. Request có cookie chưa chắc là hoạt động nghiệp vụ

Một request có thể mang cookie session ID nhưng không nhất thiết thực hiện hành động nghiệp vụ có ý nghĩa. Ví dụ, một endpoint heartbeat có thể được gọi định kỳ chỉ để kéo dài thời gian đăng nhập. Nếu ứng dụng coi mọi heartbeat là hoạt động người dùng, một tab bị bỏ quên có thể giữ phiên tồn tại rất lâu.

Hãy quyết định rõ loại hoạt động nào được phép làm mới inactivity timeout. Trong ứng dụng dùng HTTP session tiêu chuẩn, mốc truy cập được quản lý theo request gắn với session bởi tích hợp Servlet. Nếu yêu cầu nghiệp vụ cần phân biệt “người dùng thực sự hoạt động” với request nền, hãy lưu thêm mốc hoạt động nghiệp vụ riêng và áp dụng chính sách đó ở tầng ứng dụng.

WebSocket cũng cần được xem xét riêng: sau handshake, dữ liệu có thể tiếp tục trao đổi qua kết nối WebSocket mà không tạo thêm HTTP request thông thường. Không nên mặc định rằng mỗi frame WebSocket sẽ làm mới HTTP session timeout. Nếu kết nối dài cần có thời hạn hoặc cần xác thực lại, hãy thiết kế heartbeat, thời hạn kết nối và kiểm tra quyền riêng cho WebSocket.

## 3. Cấu hình thời gian không hoạt động

### 3.1. Spring Boot

Với ứng dụng Servlet dùng Spring Boot và Spring Session, có thể cấu hình thời gian không hoạt động bằng `spring.session.timeout`:

```yaml
spring:
  session:
    timeout: 30m
```

Nếu `spring.session.timeout` không được đặt trong ứng dụng Servlet, auto-configuration của Spring Boot sử dụng `server.servlet.session.timeout` làm giá trị dự phòng. Cần kiểm tra cấu hình hiệu lực để tránh đặt hai giá trị khác nhau rồi khó xác định timeout thực tế.

Ví dụ dùng cấu hình Servlet container:

```yaml
server:
  servlet:
    session:
      timeout: 20m
```

Khi Spring Session được auto-configure, ưu tiên dùng `spring.session.timeout` để thể hiện rõ timeout của Spring Session. Với ứng dụng không dùng Spring Session, `server.servlet.session.timeout` là cấu hình session của Servlet container.

### 3.2. Annotation cấu hình Spring Session

Nếu tự cấu hình Spring Session JDBC, có thể đặt timeout bằng `maxInactiveIntervalInSeconds`:

```java
@Configuration
@EnableJdbcHttpSession(maxInactiveIntervalInSeconds = 1800)
public class JdbcSessionConfiguration {
}
```

Với Redis:

```java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
public class RedisSessionConfiguration {
}
```

Hai ví dụ dùng 1.800 giây, tương đương 30 phút. Khi dùng Spring Boot starter, có thể để auto-configuration tạo repository và dùng property thay vì khai báo annotation thủ công. Nếu chuyển sang cấu hình thủ công, kiểm tra cơ chế auto-configuration back-off và bảo đảm chỉ có một repository/filter được kích hoạt.

### 3.3. Timeout theo từng session

Một số luồng có thể cần timeout khác nhau. Ví dụ, session dành cho quy trình thanh toán có thể ngắn hơn session duyệt danh mục. Với `HttpSession`, có thể đặt timeout cho phiên hiện tại bằng số giây:

```java
@PostMapping("/checkout/start")
public String startCheckout(HttpSession session) {
    session.setMaxInactiveInterval(10 * 60); // 10 phút
    session.setAttribute("checkoutStarted", true);
    return "checkout-started";
}
```

Giá trị này chỉ áp dụng cho session tương ứng. Không nhầm nó với timeout mặc định dùng khi tạo session mới. Nếu session có timeout riêng, cần kiểm tra repository và cách cập nhật phiên để chắc chắn giá trị đó được lưu cùng session.

## 4. Thời hạn session và TTL của kho dữ liệu

### 4.1. Hạn logic và thời điểm xóa vật lý

Hết hạn logic có nghĩa repository không còn chấp nhận phiên. Dữ liệu vật lý có thể còn tồn tại thêm một khoảng thời gian trước khi bị dọn. Điều này đặc biệt quan trọng khi điều tra Redis hoặc JDBC: nhìn thấy một key hay một row chưa chắc phiên vẫn hợp lệ.

Repository cần kiểm tra `lastAccessedTime` và `maxInactiveInterval` khi tìm phiên. API `SessionRepository.findById` được thiết kế để không trả về session đã hết hạn. Vì vậy, tầng ứng dụng nên dựa vào kết quả repository thay vì chỉ nhìn thấy dữ liệu còn nằm trong kho.

### 4.2. Redis

Spring Session Redis lưu thông tin như `creationTime`, `lastAccessedTime`, `maxInactiveInterval` và các thuộc tính phiên. TTL của khóa được thiết lập dựa trên `maxInactiveInterval`.

Với `RedisIndexedSessionRepository`, khóa chứa dữ liệu session có thể được đặt TTL dài hơn hạn logic khoảng năm phút. Khoảng đệm này giúp Spring Session còn cơ hội đọc dữ liệu phiên khi xử lý sự kiện hết hạn và dọn tài nguyên liên quan. Một khóa riêng theo dõi thời điểm hết hạn có TTL bằng thời gian không hoạt động. Vì thế, khi dùng `redis-cli TTL`, không nên suy ra hạn đăng nhập chính xác chỉ từ TTL của hash chứa session.

Spring Session dùng Redis keyspace notifications và cơ chế theo dõi expiration để phát hiện phiên hết hạn, phục vụ sự kiện như `SessionExpiredEvent` và dọn tài nguyên liên quan. Thời điểm Redis phát sự kiện có thể không chính xác tuyệt đối theo giây; repository vẫn phải từ chối phiên hết hạn khi đọc. Sự kiện là cơ chế thông báo và dọn dẹp, không phải điều kiện duy nhất quyết định phiên có hợp lệ hay không.

`RedisSessionRepository` cơ bản và `RedisIndexedSessionRepository` có khác biệt về khả năng phát sự kiện. Nếu ứng dụng phụ thuộc vào session destroyed/expired events, hãy chọn repository có hỗ trợ và cấu hình Redis keyspace notifications theo yêu cầu môi trường. Với Redis được quản trị chặt, ứng dụng có thể không được phép tự thay đổi cấu hình `notify-keyspace-events`; khi đó cần phối hợp với quản trị hạ tầng.

### 4.3. JDBC

Spring Session JDBC lưu các thông tin liên quan đến thời hạn trong bảng session, bao gồm:

- `LAST_ACCESS_TIME`: thời điểm truy cập cuối.
- `MAX_INACTIVE_INTERVAL`: khoảng không hoạt động tối đa.
- `EXPIRY_TIME`: thời điểm hết hạn được tính từ hai giá trị trên.

Repository dùng `EXPIRY_TIME` để lọc hoặc dọn phiên đã hết hạn. Spring Session JDBC chạy tác vụ dọn các phiên hết hạn theo lịch, mặc định mỗi phút. Do đó, row của phiên đã hết hạn có thể còn trong bảng cho tới lần chạy dọn tiếp theo. Sự tồn tại của row không đồng nghĩa request tiếp theo được phép dùng session đó.

Có thể thay lịch dọn qua `cleanupCron` của `@EnableJdbcHttpSession` hoặc property `spring.session.jdbc.cleanup-cron` trong Spring Boot. Không nên giảm chu kỳ quá mức nếu bảng lớn hoặc cơ sở dữ liệu đang chịu tải; hãy theo dõi thời gian truy vấn, chỉ mục `EXPIRY_TIME` và số lượng row tồn đọng.

### 4.4. Map hoặc repository tự triển khai

Khi dùng repository trong bộ nhớ như `MapSessionRepository`, việc kiểm tra `isExpired()` có thể diễn ra khi tìm session, nhưng cơ chế dọn dữ liệu khỏi map là trách nhiệm của triển khai. Với `@EnableSpringHttpSession` và repository tự cung cấp, Spring Session không tự cấu hình một cơ chế dọn hết hạn chung cho mọi loại kho. Nếu map giữ các phiên hết hạn vô thời hạn, bộ nhớ sẽ tăng dần dù các phiên không còn được trả về cho ứng dụng.

Repository tự triển khai cần định nghĩa rõ:

1. Khi nào kiểm tra `isExpired()`.
2. Có xóa session hết hạn ngay khi đọc hay dùng tác vụ nền.
3. Cách tránh tác vụ dọn dữ liệu xóa nhầm session vừa được gia hạn.
4. Cách giữ hành vi nhất quán khi nhiều instance cùng truy cập kho.

## 5. Cookie, timeout và thời hạn tuyệt đối

Cookie thường chứa session ID. Thời hạn cookie điều khiển thời gian trình duyệt giữ và gửi ID; `maxInactiveInterval` điều khiển thời gian máy chủ chấp nhận phiên khi không hoạt động. Hai giá trị liên quan nhưng không thay thế nhau.

| Thành phần | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| `maxInactiveInterval` | Thời gian không hoạt động tối đa của session ở phía máy chủ | 30 phút kể từ lần truy cập cuối |
| Cookie `Max-Age`/`Expires` | Thời gian trình duyệt lưu cookie session ID | Cookie bị xóa sau 8 giờ |
| Thời hạn tuyệt đối | Tuổi tối đa của phiên tính từ thời điểm tạo hoặc xác thực | Bắt đăng nhập lại sau 8 giờ |
| TTL kho dữ liệu | Thời gian key/row tồn tại vật lý theo cơ chế repository | Redis key hoặc JDBC cleanup |

Nếu cookie hết hạn trước session, trình duyệt có thể mất ID trong khi dữ liệu phiên vẫn còn ở kho. Nếu cookie còn lâu hơn session, trình duyệt vẫn gửi ID nhưng repository từ chối vì phiên đã hết hạn. Nếu cần thời hạn tuyệt đối, hãy lưu `creationTime` hoặc thời điểm xác thực và kiểm tra riêng; việc request tiếp tục cập nhật `lastAccessedTime` không được phép kéo dài tuổi tối đa đó.

## 6. Nhiều instance và đồng hồ hệ thống

Với Redis hoặc JDBC dùng chung, mọi instance có thể đọc cùng `lastAccessedTime` và `maxInactiveInterval`. Điều này giúp phiên tiếp tục hoạt động khi load balancer chuyển request từ instance A sang instance B.

Các instance cần đồng bộ đồng hồ hệ thống. Nếu một máy chủ nhanh hơn hoặc chậm hơn đáng kể, việc tính `Instant.now()` và so sánh với thời điểm truy cập cuối có thể làm session hết hạn sớm hoặc muộn. Nên đồng bộ thời gian qua NTP, dùng UTC/`Instant` cho mốc thời gian và theo dõi clock drift.

Request đồng thời có thể tạo ra các cập nhật gần nhau cho cùng session. Ví dụ, hai request cùng đọc session tại thời điểm gần như đồng thời, một request cập nhật giỏ hàng và request kia cập nhật locale. Nếu repository ghi toàn bộ trạng thái cũ, request hoàn tất sau có thể ghi đè dữ liệu request trước. Một số repository tối ưu bằng cách chỉ ghi những thuộc tính thay đổi, nhưng không nên coi đó là bảo đảm transaction cho mọi cập nhật nghiệp vụ.

Để giảm rủi ro:

- Giữ dữ liệu session nhỏ và phân chia thuộc tính theo trách nhiệm.
- Tránh dùng session làm nơi lưu trạng thái nghiệp vụ cần tính nhất quán cao.
- Kiểm thử request song song cùng session, bao gồm cập nhật thuộc tính và refresh timeout.
- Với dữ liệu quan trọng, dùng transaction, optimistic locking hoặc cơ chế đồng bộ phù hợp ở tầng dữ liệu nghiệp vụ.
- Đảm bảo tất cả instance dùng cùng timeout mặc định, phiên bản tương thích và cấu hình repository.

## 7. Kiểm thử lần truy cập cuối và inactivity timeout

### 7.1. Kiểm thử `Session` trực tiếp

Có thể kiểm tra `MapSession` độc lập bằng cách đặt một thời điểm truy cập cũ và thời hạn ngắn:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.session.MapSession;

class SessionExpirationTest {

    @Test
    void expiresAfterMaximumInactiveInterval() {
        MapSession session = new MapSession();
        session.setMaxInactiveInterval(Duration.ofMinutes(10));
        session.setLastAccessedTime(Instant.now().minus(Duration.ofMinutes(11)));

        assertTrue(session.isExpired());
    }

    @Test
    void remainsValidWhenLastAccessWasRecent() {
        MapSession session = new MapSession();
        session.setMaxInactiveInterval(Duration.ofMinutes(10));
        session.setLastAccessedTime(Instant.now().minus(Duration.ofMinutes(2)));

        assertFalse(session.isExpired());
    }
}
```

Kiểm thử này xác minh quy tắc tính hết hạn của đối tượng session. Nó không chứng minh repository đang lưu TTL đúng hoặc filter Servlet cập nhật `lastAccessedTime` đúng trong một HTTP request.

### 7.2. Kiểm thử repository

Khi dùng `SessionRepository`, cần kiểm tra:

1. Tạo session và đặt `maxInactiveInterval`.
2. Lưu session rồi đọc lại bằng ID.
3. Xác minh `lastAccessedTime` được cập nhật khi `save`.
4. Đặt hoặc mô phỏng thời điểm truy cập cũ vượt timeout.
5. Xác minh `findById` không trả session đã hết hạn.
6. Kiểm tra thao tác xóa và dọn dữ liệu vật lý theo triển khai.

Không dùng `Thread.sleep` dài trong mọi unit test nếu có thể kiểm tra trực tiếp `Instant` hoặc `isExpired()`. Với kiểm thử tích hợp HTTP, timeout ngắn vài giây có thể hữu ích nhưng nên tách rõ thời gian chờ từ trình duyệt, network và scheduler dọn dữ liệu.

### 7.3. Kiểm thử HTTP qua nhiều instance

Một kịch bản tích hợp hữu ích:

| Bước | Thực hiện | Điều cần xác minh |
|---|---|---|
| 1 | Đăng nhập qua instance A và nhận cookie | Session được tạo, timeout đúng |
| 2 | Gửi request hợp lệ qua instance B với cookie đó | B đọc cùng session từ kho dùng chung |
| 3 | Đọc mốc truy cập cuối sau request | `lastAccessedTime` đã tiến lên |
| 4 | Chờ gần hết timeout, rồi gửi request mới qua A | Session được gia hạn theo chính sách |
| 5 | Không gửi request vượt quá timeout | Request tiếp theo bị xem là chưa xác thực hoặc cần đăng nhập lại |
| 6 | Kiểm tra Redis/JDBC sau đó | Dữ liệu vật lý được dọn theo cơ chế của repository |

Nên bổ sung tình huống hai request đồng thời cùng dùng cookie, một request chỉ đọc và một request cập nhật thuộc tính; request tới endpoint không cần session; request heartbeat; WebSocket mở lâu; và kho dữ liệu tạm thời mất kết nối.

## 8. Theo dõi và xử lý lỗi khi vận hành

Theo dõi số lượng session đang hoạt động, session hết hạn, session bị xóa, số lần người dùng bị yêu cầu đăng nhập lại, độ trễ đọc/ghi repository và lỗi kết nối kho dữ liệu. Với Redis, theo dõi TTL, memory, keyspace notifications, replication và latency. Với JDBC, theo dõi row hết hạn tồn đọng, lịch cleanup, thời gian truy vấn, connection pool và chỉ mục `EXPIRY_TIME`.

Một số dấu hiệu và nguyên nhân thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Người dùng bị đăng xuất sớm | Timeout hiệu lực thấp hơn dự kiến, request không được liên kết với session, cookie không được gửi hoặc đồng hồ instance lệch | Kiểm tra `spring.session.timeout`, `server.servlet.session.timeout`, cookie, filter và clock drift |
| Session tồn tại trong Redis/JDBC nhưng không dùng được | Dữ liệu vật lý chưa được dọn sau khi hết hạn logic | Kiểm tra `lastAccessedTime`, `maxInactiveInterval`, `EXPIRY_TIME` và kết quả `findById` |
| Session không bao giờ hết hạn | Timeout âm, endpoint heartbeat liên tục làm mới session hoặc repository không kiểm tra hết hạn | Kiểm tra timeout, luồng request nền và logic repository |
| JDBC có nhiều row hết hạn | Cleanup job không chạy, thiếu quyền xóa, query chậm hoặc chỉ mục không phù hợp | Kiểm tra scheduler, log, `cleanupCron`, SQL và index |
| Redis phát sự kiện hết hạn chậm | Redis keyspace notification hoặc cơ chế quét expiration chưa hoạt động như kỳ vọng | Kiểm tra `notify-keyspace-events`, listener và tác vụ truy cập key hết hạn |
| Hai request ghi đè dữ liệu phiên | Cập nhật đồng thời và ngữ nghĩa save của repository | Kiểm tra SaveMode, thay đổi thuộc tính và dữ liệu nghiệp vụ nên chuyển khỏi session |
| Các instance cho kết quả khác nhau | Cấu hình timeout, version, serializer hoặc đồng hồ không đồng nhất | So sánh cấu hình và log giữa các instance |

Không nên dùng việc xóa cookie ở trình duyệt làm cách xử lý duy nhất cho session bị xâm phạm hoặc cần đăng xuất từ xa. Muốn vô hiệu hóa phiên, cần xóa hoặc invalidate session ở repository dùng chung để các instance đều từ chối ID cũ.

## 9. Quy trình thiết kế timeout

Khi thiết kế inactivity timeout cho Spring Session, hãy thực hiện theo các bước:

1. Xác định khoảng không hoạt động tối đa theo mức độ nhạy cảm của chức năng.
2. Phân biệt inactivity timeout với tuổi tối đa của phiên và thời hạn cookie.
3. Cấu hình một giá trị rõ ràng qua Spring Boot property hoặc annotation phù hợp.
4. Để Spring Session/Servlet integration quản lý `lastAccessedTime`; tránh tự cập nhật ở nhiều tầng.
5. Xác minh repository thực thi hết hạn logic và có cơ chế dọn dữ liệu vật lý phù hợp.
6. Đồng bộ đồng hồ giữa các instance và kiểm thử request chuyển máy chủ.
7. Kiểm thử request đồng thời, heartbeat, WebSocket và sự cố kho dữ liệu.
8. Theo dõi session hết hạn, row/key tồn đọng và tỷ lệ đăng nhập lại trong môi trường thật.

`lastAccessedTime` cho biết lần request gần nhất gắn với session; `maxInactiveInterval` xác định thời gian được phép không hoạt động. Khi hai giá trị được cập nhật và kiểm tra nhất quán, Spring Session có thể duy trì timeout trượt trên nhiều instance. Thiết kế tốt cần đồng thời tính đến thời hạn cookie, tuổi tuyệt đối, cơ chế dọn dữ liệu của Redis/JDBC và hành vi khi nhiều request cùng cập nhật một phiên.

## Tài liệu tham khảo

- [Spring Session API — Session và thời hạn không hoạt động](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/Session.html)
- [Spring Session API — cập nhật last accessed time khi save](https://docs.spring.io/spring-session/reference/api.html)
- [Spring Session Redis — lưu session và expiration TTL](https://docs.spring.io/spring-session/reference/api.html#_using_redisindexedsessionrepository)
- [Spring Session JDBC — schema, expiry time và cleanup job](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Boot — Spring Session và session timeout](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
