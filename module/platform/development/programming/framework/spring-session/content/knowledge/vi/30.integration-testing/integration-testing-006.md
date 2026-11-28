# Kiểm thử idle timeout, cookie hết hạn và tác vụ cleanup độc lập

Spring Session quản lý thời gian sống của session ở phía server và có thể lưu dữ liệu trong Redis hoặc JDBC. Trình duyệt đồng thời quản lý cookie chứa session ID. Hai vòng đời này liên quan nhưng độc lập: cookie có thể hết hạn trong browser trong khi session vẫn còn ở kho; ngược lại, cookie vẫn được gửi nhưng session phía server đã hết inactivity timeout.

Kiểm thử đúng cần tách ba hành vi: **idle timeout** quyết định session không còn hợp lệ sau một khoảng không hoạt động; **cookie expiration** quyết định browser còn gửi session ID hay không; **cleanup** thu hồi dữ liệu hết hạn khỏi kho theo cơ chế nền. Cleanup không được phụ thuộc vào việc người dùng gửi request tiếp theo. Bài này trình bày cách kiểm thử ba hành vi với Servlet Spring Session, Redis và JDBC, đồng thời phân biệt hết hạn logic với xóa vật lý.

## 1. Ba đồng hồ khác nhau

### 1.1. Idle timeout ở phía server

Spring Session lưu `maxInactiveInterval` và thời điểm truy cập gần nhất (`lastAccessedTime`). Khi session không được sử dụng trong khoảng thời gian cấu hình, nó trở thành expired. Request gửi session ID cũ không được khôi phục trạng thái xác thực hoặc thuộc tính của phiên đã hết hạn.

Ví dụ cấu hình timeout 30 phút:

```yaml
spring:
  session:
    timeout: 30m
```

Hoặc cấu hình repository trực tiếp bằng annotation, tùy loại kho và phiên bản:

```java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
public class RedisSessionConfiguration {
}
```

Idle timeout là thời gian không hoạt động, không phải thời gian tuyệt đối tính từ lúc đăng nhập. Một request hợp lệ có thể cập nhật `lastAccessedTime` và làm mới thời hạn theo semantics của repository.

### 1.2. Cookie expiration ở phía browser

Cookie chứa session ID có thể là session cookie hoặc persistent cookie:

- Cookie không có `Max-Age`/`Expires` thường được browser quản lý như session cookie.
- Cookie có `Max-Age` hoặc `Expires` được browser giữ đến thời điểm hết hạn được chỉ định, trừ khi bị xóa sớm.

`DefaultCookieSerializer` có thể cấu hình `cookieMaxAge`. Ví dụ:

```java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setCookiePath("/");
    serializer.setCookieMaxAge(3600);
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
```

Trong ví dụ, cookie được cấu hình với tuổi thọ browser một giờ. Điều đó không làm session ở Redis/JDBC sống một giờ nếu idle timeout phía server ngắn hơn. Ngược lại, cookie hết hạn sau một giờ cũng không có nghĩa repository đã xóa session đúng vào thời điểm đó.

Không giả định cookie `Max-Age` tự động trượt theo mỗi request. Hành vi phát lại cookie phụ thuộc resolver, việc session ID có thay đổi và cấu hình serializer. Hãy kiểm tra header `Set-Cookie` thực tế của ứng dụng.

### 1.3. Cleanup vật lý trong kho

Khi session hết hạn logic, dữ liệu có thể vẫn còn trong kho một thời gian:

- Redis quản lý TTL và expiration event; Spring Session có thể cần xử lý event để dọn key/index liên quan.
- JDBC giữ row session/attributes cho tới khi tác vụ cleanup xóa chúng.

Vì vậy, ba mốc sau không nhất thiết trùng nhau:

1. Thời điểm server bắt đầu xem session là expired.
2. Thời điểm browser ngừng gửi cookie.
3. Thời điểm key/row được xóa vật lý khỏi Redis/JDBC.

Quyết định xác thực phải dựa trên session còn hợp lệ hay không, không dựa vào việc dữ liệu đã biến mất vật lý khỏi kho.

## 2. Luồng kiểm tra idle timeout

### 2.1. Tạo session và lưu cookie

Một endpoint kiểm thử có thể tạo session rõ ràng:

```java
@RestController
@RequestMapping("/test-session")
public class SessionProbeController {

    @PostMapping("/start")
    public Map<String, String> start(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("probe", "created");
        return Map.of("state", "created");
    }

    @GetMapping("/current")
    public ResponseEntity<Map<String, String>> current(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }
        return ResponseEntity.ok(Map.of(
            "state", String.valueOf(session.getAttribute("probe"))));
    }
}
```

Endpoint `/current` dùng `getSession(false)` để không tạo một session mới khi cookie không hợp lệ hoặc session đã hết hạn. Nếu dùng `getSession()` ở đây, request kiểm tra có thể tự tạo session khác và làm test hiểu nhầm rằng session cũ vẫn còn.

### 2.2. Gửi lại cookie để chứng minh session còn hoạt động

Quy trình test:

1. Gửi POST `/test-session/start`.
2. Lấy cookie `SESSION` từ response `Set-Cookie`.
3. Gửi GET `/test-session/current` với cookie vừa lấy.
4. Xác minh thuộc tính `probe=created` được khôi phục.
5. Chờ quá idle timeout mà không gửi request nào với cookie đó.
6. Gửi lại cookie cũ và xác minh session không còn được khôi phục.

Nếu trong thời gian chờ có health check hoặc background client vô tình gửi cookie cũ tới endpoint làm mới session, thời gian idle sẽ được kéo dài. Test phải bảo đảm không có request sử dụng session trong khoảng quan sát.

### 2.3. Không nhầm inactivity timeout với absolute timeout

Nếu người dùng gửi request đều đặn, idle timeout có thể không bao giờ xảy ra. Một số ứng dụng cần thêm absolute session lifetime, ví dụ bắt buộc đăng nhập lại sau 12 giờ dù có hoạt động liên tục. Đây là chính sách khác, cần lưu thời điểm tạo session hoặc thời điểm xác thực gần nhất và kiểm tra riêng.

Không mô tả `maxInactiveInterval` như giới hạn tổng thời gian đăng nhập. Nếu yêu cầu có cả idle timeout và absolute timeout, phải có hai assertion riêng trong test.

## 3. Kiểm thử idle timeout bằng MockMvc

### 3.1. Dùng repository thật trong integration test

`MockMvc` có thể gửi request qua Spring MVC filter chain trong application context. Để kiểm thử Spring Session, test context phải đăng ký đúng `SessionRepositoryFilter` và dùng repository test thật hoặc container Redis/JDBC riêng.

Ví dụ dưới đây minh họa cách lấy cookie từ response đầu và gửi lại:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SessionIdleTimeoutIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void restoresSessionBeforeIdleTimeout() throws Exception {
        MvcResult created = this.mockMvc.perform(post("/test-session/start"))
            .andExpect(status().isOk())
            .andReturn();

        Cookie sessionCookie = created.getResponse().getCookie("SESSION");
        assertNotNull(sessionCookie);

        this.mockMvc.perform(get("/test-session/current").cookie(sessionCookie))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state", is("created")));
    }
}
```

Test này kiểm tra khôi phục trước timeout. Để kiểm tra timeout thực tế, cấu hình TTL ngắn trong test profile hoặc test configuration, rồi chờ trạng thái expired bằng một điều kiện có giới hạn thời gian.

### 3.2. Chờ điều kiện thay vì ngủ đúng một khoảng cố định

Để tránh request kiểm tra làm mới `lastAccessedTime`, hãy chờ bằng một thao tác đọc repository không tạo hoạt động HTTP mới:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .until(() -> sessionRepository.findById(sessionId) == null);
```

Đoạn này giả định idle timeout test ngắn hơn 10 giây và `findById` không làm mới last-access time. Sau khi điều kiện đạt, gửi đúng một request HTTP với cookie cũ để xác minh endpoint từ chối session. Không đặt timeout test sát đúng TTL; cần thêm biên cho scheduler, network và CI load. Không dùng `Thread.sleep(2000)` rồi khẳng định chắc chắn key đã được cleanup vật lý.

Lưu ý: mỗi lần gửi request kiểm tra trước khi hết TTL có thể cập nhật last-access time. Vì vậy, polling endpoint HTTP có thể vô tình giữ session sống mãi. Đối với kiểm thử idle timeout, ưu tiên kiểm tra repository bằng một quan sát không làm mới session hoặc chờ qua TTL rồi mới gửi đúng một request xác minh.

### 3.3. Kiểm tra trực tiếp repository

Trong test có thể lưu session ID từ cookie rồi dùng `SessionRepository.findById` để kiểm tra sau TTL:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .until(() -> sessionRepository.findById(sessionId) == null);
```

Ví dụ minh họa với Servlet `SessionRepository`. Một số repository có thể trả `null` khi session hết hạn logic trước khi dữ liệu được xóa vật lý. Đây là kiểm tra session không còn được nạp, không phải bằng chứng cleanup job đã xóa mọi key/row phụ.

## 4. Kiểm thử cookie hết hạn

### 4.1. Kiểm tra header `Set-Cookie`

Khi cấu hình cookie persistent, kiểm tra response đầu có `Max-Age` hoặc `Expires` theo yêu cầu:

```java
MvcResult result = mockMvc.perform(post("/test-session/start"))
    .andExpect(status().isOk())
    .andReturn();

String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);
assertNotNull(setCookie);
assertTrue(setCookie.contains("Max-Age=3600"));
assertTrue(setCookie.contains("HttpOnly"));
```

Header có thể được định dạng hoặc sắp xếp thuộc tính khác nhau theo framework/container. Assertion nên tập trung vào thuộc tính cần kiểm tra thay vì so sánh toàn bộ chuỗi cứng.

### 4.2. MockMvc không tự mô phỏng browser cookie jar

MockMvc không tự đợi `Max-Age` trôi qua rồi xóa cookie như browser. Nếu test gọi `.cookie(sessionCookie)` sau thời điểm hết hạn, test vẫn gửi cookie vì chính test đang chủ động gắn nó vào request.

Do đó cần tách hai loại test:

- **Server-side test:** gửi lại cookie cũ sau idle timeout và xác minh repository từ chối session.
- **Browser cookie test:** dùng browser automation để xác minh browser ngừng gửi cookie sau `Max-Age`/`Expires`.

Không dùng việc browser bỏ cookie làm bằng chứng session đã bị xóa khỏi Redis/JDBC.

### 4.3. Kiểm thử xóa cookie khi logout

Logout thường phát một `Set-Cookie` cùng tên/path/domain với giá trị rỗng hoặc chỉ thị hết hạn. Kiểm tra cookie bị hết hạn ở response logout và kiểm tra session ID cũ không còn khôi phục được ở server.

Nếu cấu hình cookie name/path/domain tùy chỉnh, cookie xóa phải khớp các thuộc tính định danh của cookie ban đầu. Nếu path hoặc domain không khớp, browser có thể giữ cookie cũ.

### 4.4. Cookie hết hạn trước server session

Giả sử browser cookie có `Max-Age=15 phút`, còn server idle timeout là 30 phút. Sau 15 phút, browser không gửi cookie nữa; server có thể vẫn giữ session tới khi idle timeout kết thúc và cleanup xử lý.

Đây có thể tạo session mồ côi trong kho một khoảng thời gian. Nếu cần giới hạn dung lượng, không đặt cookie max-age dài hơn nhiều so với chính sách session mà không có lý do. Nhưng cookie max-age ngắn cũng không thay thế server-side cleanup.

### 4.5. Server session hết hạn trước cookie

Nếu cookie sống 8 giờ nhưng server idle timeout là 20 phút, browser có thể tiếp tục gửi cookie cũ sau 20 phút. Server phải từ chối session ID đó. Response có thể phát cookie hết hạn hoặc một identifier mới nếu request chủ động tạo session khác.

## 5. Cleanup trong Spring Session JDBC

### 5.1. Hết hạn logic và xóa row

`JdbcIndexedSessionRepository` lưu session trong bảng `SPRING_SESSION` và các thuộc tính trong `SPRING_SESSION_ATTRIBUTES`. Cột `EXPIRY_TIME` cho biết thời điểm session hết hạn. Khi session đã hết hạn, repository không được xem nó là session hợp lệ, kể cả khi row chưa được cleanup.

Tác vụ cleanup xóa row hết hạn khỏi bảng session; schema và cơ chế cascade/cleanup tương ứng xử lý attributes. Nếu cleanup không chạy, các row hết hạn vẫn chiếm disk và index.

### 5.2. Cấu hình lịch cleanup

`@EnableJdbcHttpSession` hỗ trợ cấu hình lịch cleanup qua `cleanupCron` ở các phiên bản tương ứng. Ví dụ trong test profile, chạy mỗi 5 giây:

```java
@Configuration
@EnableJdbcHttpSession(
    maxInactiveIntervalInSeconds = 2,
    cleanupCron = "*/5 * * * * *"
)
public class JdbcSessionTestConfiguration {
}
```

Cron sáu trường của Spring có trường giây ở đầu. Giá trị production nên được chọn theo tải database và độ trễ cleanup chấp nhận được; không nhất thiết chạy mỗi vài giây. Kiểm tra API annotation và cơ chế scheduling theo đúng phiên bản Spring Session của dự án.

Nếu dùng Spring Boot auto-configuration, cấu hình cleanup cron qua property được phiên bản đó hỗ trợ hoặc cấu hình annotation tương ứng. Tránh bật hai job cleanup độc lập cùng chạy trên một bảng nếu không cần thiết.

### 5.3. Cleanup phải chạy khi không có request

Đây là thuộc tính quan trọng của cleanup job. Sau khi tạo session và để nó hết hạn, test không gửi request nào tới ứng dụng trong thời gian chờ. Job nền vẫn phải xóa row hết hạn.

Có thể kiểm tra số row bằng SQL:

```sql
SELECT COUNT(*)
FROM SPRING_SESSION
WHERE SESSION_ID = ?;
```

Và kiểm tra attributes theo primary key của session:

```sql
SELECT COUNT(*)
FROM SPRING_SESSION_ATTRIBUTES
WHERE SESSION_PRIMARY_ID = ?;
```

Lấy `SESSION_PRIMARY_ID` từ row session trước khi cleanup hoặc truy vấn bằng join. Khi cleanup hoàn tất, cả session row và các attribute row liên quan phải được xóa theo schema/repository đang dùng.

### 5.4. Kiểm thử scheduled cleanup độc lập

Một test tích hợp nên:

1. Tạo session với idle timeout rất ngắn.
2. Lấy session ID và xác nhận row xuất hiện trong `SPRING_SESSION`.
3. Không gửi thêm request sử dụng session.
4. Chờ qua idle timeout.
5. Chờ lịch cleanup chạy thêm ít nhất một chu kỳ.
6. Xác minh session row không còn.
7. Xác minh attribute row liên quan cũng không còn.
8. Xác minh request gửi cookie cũ bị từ chối.

Điều kiện 3 chứng minh cleanup không phụ thuộc traffic. Điều kiện 8 kiểm tra semantics hết hạn, còn điều kiện 6–7 kiểm tra xóa vật lý. Hai nhóm assertion trả lời hai câu hỏi khác nhau.

### 5.5. Tải cleanup và batch

Trên bảng lớn, cleanup quá thường xuyên hoặc xóa quá nhiều row trong một transaction có thể tạo lock, WAL/transaction log lớn và cạnh tranh I/O với request. Theo dõi số row xóa mỗi lần, thời gian chạy, số row hết hạn còn tồn và query plan trên `EXPIRY_TIME`.

Nếu cần batch cleanup tùy chỉnh, giữ nguyên semantics của repository và schema, kiểm tra foreign key/attributes, dùng index phù hợp và commit theo batch. Không tự viết lệnh xóa chỉ dựa vào tên bảng mà bỏ qua dữ liệu liên quan.

## 6. Expiration và cleanup trong Spring Session Redis

### 6.1. Redis TTL không đồng nghĩa mọi key biến mất cùng lúc

Redis hỗ trợ TTL và expiration cho key. Spring Session Redis có thể dùng các key session, key expiration và index phụ để hỗ trợ truy vấn hoặc phát sự kiện. Vì vậy, số key quan sát trong Redis không nhất thiết bằng số session còn hoạt động.

Session có thể đã expired theo `lastAccessedTime`/`maxInactiveInterval` trong khi một số key phụ vẫn còn chờ expiration event hoặc cleanup. Không dùng `SCAN` thấy key còn tồn tại làm bằng chứng session vẫn hợp lệ.

### 6.2. Keyspace notifications

Spring Session Redis sử dụng Redis expiration events cho một số thao tác lifecycle và cleanup index. Redis keyspace notifications cần được cấu hình theo yêu cầu của phiên bản Spring Session và môi trường Redis. Một số dịch vụ Redis managed hạn chế lệnh `CONFIG`; trong trường hợp đó, cấu hình notification ở tầng dịch vụ và dùng `ConfigureRedisAction.NO_OP` nếu tài liệu Spring Session yêu cầu.

Không bật hoặc thay đổi `notify-keyspace-events` tùy tiện trên Redis dùng chung nhiều ứng dụng. Xác minh tác động tới toàn cluster và bảo đảm cấu hình có đủ event flags mà repository cần.

### 6.3. Kiểm tra session hết hạn qua repository

Để kiểm tra semantics, lấy session ID từ cookie rồi gọi `SessionRepository.findById(sessionId)` sau idle timeout. Repository phải không trả một session hợp lệ. Việc key vật lý biến mất có thể xảy ra sau đó tùy TTL, event và cấu trúc key.

Với Redis, kiểm thử integration nên xác minh:

- Session mới được ghi vào namespace mong đợi.
- TTL của key phù hợp với inactivity interval và cơ chế expiration của repository.
- Request cũ không khôi phục session sau expiry.
- Expiration event và index cleanup hoạt động khi notifications được cấu hình.
- Không để lại dữ liệu phụ tăng vô hạn khi listener bị ngắt hoặc event bị bỏ lỡ.

### 6.4. Không tự xóa key nội bộ bằng wildcard trong ứng dụng

Không dùng `KEYS spring:session:*` trong production hoặc xóa key bằng pattern trong request path. Việc đó có thể block Redis hoặc xóa session của ứng dụng khác nếu namespace không tách. Dùng repository API, TTL và quy trình bảo trì có giới hạn, được kiểm thử.

## 7. Kiểm thử Redis idle timeout và expiration event

### 7.1. Test với Redis container

Khởi chạy Redis riêng bằng Testcontainers và cấu hình `@EnableRedisHttpSession` với timeout ngắn trong test context. Tạo session, lấy cookie, xác minh session được đọc trước TTL, rồi chờ qua TTL và xác minh cookie cũ không còn nạp session.

Ví dụ cấu hình test:

```java
@Configuration
@EnableRedisHttpSession(
    maxInactiveIntervalInSeconds = 3,
    redisNamespace = "test:idle-session"
)
class RedisIdleSessionTestConfiguration {
}
```

Test phải dùng Redis container cô lập và namespace riêng. Không chạy TTL ngắn trên Redis development/production dùng chung.

### 7.2. Kiểm tra expiration event riêng

Nếu ứng dụng dựa vào `SessionExpiredEvent`, hãy kiểm tra event listener nhận event khi Redis key expiration được phát và listener đang hoạt động. Event có thể phụ thuộc keyspace notification và độ trễ Redis; không viết test yêu cầu event đến chính xác tại mili giây TTL.

Dùng Awaitility để chờ event với timeout hợp lý. Test cũng nên kiểm tra hành vi khi notification bị tắt hoặc listener mất kết nối: session vẫn phải bị xem là expired khi đọc, dù cleanup phụ trợ có thể chậm.

### 7.3. Phân biệt event với cleanup

`SessionExpiredEvent` là tín hiệu vòng đời, không phải bằng chứng rằng mọi key phụ đã biến mất. Nếu yêu cầu là dọn index, test phải kiểm tra index/secondary data liên quan sau khi event được xử lý. Nếu yêu cầu là session không thể dùng lại, kiểm tra `findById`/HTTP request.

## 8. Kiểm thử browser cookie expiration

### 8.1. Vì sao cần browser thật?

MockMvc và WebTestClient cho phép gắn cookie vào request theo ý test. Chúng không tự thực thi đầy đủ quy tắc browser về `Max-Age`, `Expires`, cookie session, Secure, SameSite, domain và path.

Để xác minh cookie thực sự hết hạn ở client, dùng browser automation như Playwright hoặc Selenium:

1. Mở ứng dụng qua HTTPS test.
2. Gọi endpoint tạo session.
3. Đọc cookie từ browser context và xác minh thuộc tính `expires`/`maxAge` tương ứng.
4. Chờ qua thời hạn cookie hoặc dùng browser context/clock test phù hợp.
5. Gọi endpoint tiếp theo và xác minh cookie không còn được gửi.
6. Đồng thời kiểm tra server session có thể vẫn còn cho tới idle timeout.

Không dùng JavaScript `document.cookie` để xác minh cookie `HttpOnly`, vì cookie này cố ý không hiển thị qua API đó. Dùng browser automation cookie API hoặc network request inspection.

### 8.2. Cookie session không có Max-Age

Cookie session thường không có thời hạn persistent. Browser thường xóa khi session browser kết thúc, nhưng session restore có thể khôi phục cookie tùy browser. Vì vậy, “đóng tab” không phải cách kiểm thử cookie session expiration; đóng tab thường không kết thúc browser session.

Kiểm thử browser session cookie cần kiểm soát vòng đời browser context và không suy ra server cleanup từ hành vi client.

## 9. Kiểm thử cleanup độc lập với traffic

### 9.1. Mục tiêu

Một cleanup job tốt phải xóa dữ liệu đã hết hạn dù không có request mới. Nếu cleanup chỉ chạy khi có request, session mồ côi có thể chiếm dung lượng lâu dài trong một ứng dụng ít traffic hoặc một tenant đã ngừng hoạt động.

### 9.2. Kịch bản test

| Giai đoạn | Hành động | Assertion |
|---|---|---|
| Tạo | Tạo session và ghi attribute | Repository/DB có session |
| Hoạt động | Gửi request với cookie trước TTL | Attribute được khôi phục |
| Ngừng hoạt động | Dừng mọi request dùng session | Không có hoạt động làm mới last access |
| Hết hạn | Chờ idle timeout | Repository từ chối session cũ |
| Cleanup | Không gửi request, chờ job/event | Row/key và dữ liệu phụ được dọn theo cơ chế kho |
| Sau cleanup | Gửi cookie cũ | Không khôi phục được session |

### 9.3. Không dùng chính request kiểm tra để giữ session sống

Một lỗi phổ biến là test cứ mỗi giây gọi endpoint `/current` để kiểm tra session đã hết hạn chưa. Nếu request đó được xem là hoạt động hợp lệ, nó làm mới idle timeout và test không bao giờ đạt điều kiện. Hãy dùng repository/DB quan sát không làm mới session hoặc chỉ gửi request kiểm tra sau khi đã chờ qua TTL.

### 9.4. Kiểm tra job chạy khi không có traffic

Với JDBC, dùng `cleanupCron` ngắn trong test và không gửi request sau khi session hết hạn. Với Redis, kiểm tra expiration event/key TTL và các key phụ theo cấu hình repository. Nếu dùng job tùy chỉnh, test job trực tiếp và test scheduler riêng; không gộp hai cơ chế thành một assertion mơ hồ.

## 10. Đồng hồ, thời gian và tính ổn định của test

### 10.1. Tránh kiểm thử sát ranh giới thời gian

TTL phụ thuộc đồng hồ, scheduler, network, container và độ trễ CI. Nếu timeout là 3 giây, không assert tại đúng 3.000 giây. Chờ một khoảng an toàn hoặc dùng eventual assertion có deadline.

### 10.2. Clock skew giữa các node

Trong cụm nhiều instance, nếu logic expiration dựa vào timestamp do node ghi, đồng hồ giữa các node cần được đồng bộ. Sai lệch lớn có thể khiến node đánh giá session hết hạn sớm hoặc muộn. Dùng NTP/clock sync và giám sát drift.

### 10.3. Thời gian logic khác thời gian cleanup

Repository có thể từ chối session ngay khi hết hạn logic, trong khi tác vụ cleanup chạy mỗi phút hoặc Redis event đến trễ. Test nên đặt hai mốc riêng:

- `logicalExpiryDeadline`: từ thời điểm session hết inactivity timeout.
- `physicalCleanupDeadline`: từ thời điểm cleanup có cơ hội chạy và hoàn tất.

Đừng dùng cùng một deadline cho cả hai nếu cleanup là eventual.

## 11. Ví dụ truy vấn và quan sát JDBC

### 11.1. Kiểm tra expiry time

Có thể kiểm tra thời điểm hết hạn dự kiến:

```sql
SELECT SESSION_ID,
       LAST_ACCESS_TIME,
       MAX_INACTIVE_INTERVAL,
       EXPIRY_TIME
FROM SPRING_SESSION
WHERE SESSION_ID = ?;
```

`EXPIRY_TIME` giúp chẩn đoán row nào đã tới hạn. Không dùng truy vấn này thay cho repository API để quyết định Authentication; repository áp dụng semantics và mapping session của Spring Session.

### 11.2. Kiểm tra backlog hết hạn

```sql
SELECT COUNT(*)
FROM SPRING_SESSION
WHERE EXPIRY_TIME < CURRENT_TIMESTAMP;
```

Theo dõi backlog theo thời gian. Nếu số row hết hạn tăng liên tục, kiểm tra cleanup schedule, index, lock, transaction timeout và quyền delete của database user.

### 11.3. Kiểm tra attributes

```sql
SELECT COUNT(*)
FROM SPRING_SESSION_ATTRIBUTES a
JOIN SPRING_SESSION s ON s.PRIMARY_ID = a.SESSION_PRIMARY_ID
WHERE s.SESSION_ID = ?;
```

Sau cleanup, không còn session row nên không còn attributes gắn với session đó theo schema đã áp dụng. Nếu database schema tùy chỉnh, xác minh tên cột và cascade behavior.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cookie còn nhưng request bị logout | Server idle timeout đã hết | Kiểm tra repository `findById`, không chỉ cookie |
| Browser xóa cookie nhưng Redis vẫn còn session | Cookie Max-Age ngắn hơn server TTL hoặc browser session kết thúc | Đợi server expiry/cleanup; không xem cookie deletion là server deletion |
| MockMvc vẫn gửi cookie sau Max-Age | Test tự gắn cookie, không có browser cookie jar | Dùng browser automation cho client expiry |
| Session hết hạn nhưng JDBC row vẫn còn | Cleanup cron chưa chạy hoặc bị lỗi | Kiểm tra `cleanupCron`, job log, index và backlog |
| JDBC attributes còn lại sau cleanup | Schema/cascade hoặc cleanup tùy chỉnh sai | Kiểm tra foreign key và bảng attributes |
| Redis key vẫn thấy sau idle timeout | Key phụ/expiration event cleanup trễ | Kiểm tra repository semantics và event notification |
| `SessionExpiredEvent` không tới | Keyspace notifications chưa bật hoặc listener không hoạt động | Kiểm tra Redis event flags và listener container |
| Test timeout không bao giờ kết thúc | Request polling liên tục refresh last access | Quan sát repository không làm mới hoặc chờ rồi mới gửi request |
| Cleanup chỉ chạy khi có traffic | Job bị cấu hình sai hoặc cleanup phụ thuộc request path | Kiểm tra scheduler độc lập và chạy test không traffic |
| Cleanup làm database chậm | Batch quá lớn, thiếu index hoặc cron quá thường xuyên | Tối ưu `EXPIRY_TIME`, batch và cadence |
| Session hết hạn sớm trên một node | Clock skew hoặc cấu hình timeout không đồng nhất | Đồng bộ clock và cấu hình repository giữa node |
| Cookie không được browser gửi | Secure/SameSite/Domain/Path hoặc HTTPS sai | Kiểm tra browser DevTools và reverse proxy |

## 13. Checklist kiểm thử

Trước khi hoàn tất integration test, xác minh:

1. Test dùng đúng Spring Session repository và filter của ứng dụng.
2. Idle timeout được đặt ngắn trong test profile, không thay đổi cấu hình production.
3. Request đầu tạo session và test lấy cookie session ID từ response.
4. Request trước TTL khôi phục được attribute.
5. Không có request nào refresh session trong khoảng idle được đo.
6. Request sau TTL không khôi phục session cũ.
7. Cookie `Max-Age`/`Expires` được kiểm tra riêng với server timeout.
8. Browser expiration được kiểm tra bằng browser automation nếu là yêu cầu sản phẩm.
9. JDBC cleanup job được kiểm tra khi không có traffic.
10. Redis expiration event/key cleanup được kiểm tra với keyspace notification phù hợp.
11. Test phân biệt logical expiration và physical deletion.
12. Attribute row/key phụ được dọn theo repository semantics.
13. Eventual assertion có deadline và khoảng an toàn, không phụ thuộc sleep sát ngưỡng.
14. Không log raw session ID hoặc cookie.

## 14. Quy trình thực hành

1. Cấu hình Spring Session Redis/JDBC với idle timeout ngắn trong test profile.
2. Tạo endpoint test tạo session và endpoint đọc bằng `getSession(false)`.
3. Gửi request đầu, lấy cookie và xác minh request tiếp theo khôi phục attribute.
4. Để session không hoạt động quá TTL mà không gửi request làm mới.
5. Kiểm tra repository từ chối session ID cũ.
6. Cấu hình cookie `Max-Age` riêng và kiểm tra `Set-Cookie` header.
7. Dùng browser automation để xác minh browser ngừng gửi cookie khi cookie hết hạn.
8. Với JDBC, cấu hình `cleanupCron` test ngắn và xác minh row/attribute bị xóa khi không có traffic.
9. Với Redis, kiểm tra TTL, keyspace notification và cleanup index/event.
10. Đo backlog, cleanup duration và lỗi scheduler trong test/monitoring.

Idle timeout quyết định khi nào Spring Session không còn chấp nhận phiên; cookie expiration quyết định khi nào client ngừng gửi session ID; cleanup quyết định khi nào dữ liệu hết hạn được dọn vật lý khỏi kho. Kiểm thử phải tách ba hành vi này. Hãy xác minh session cũ bị từ chối sau idle timeout, kiểm tra browser cookie bằng browser thật khi cần, và chứng minh cleanup JDBC/Redis vẫn chạy khi không có request mới.

## Tài liệu tham khảo

- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — Redis Configuration and Expiration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration and Cleanup](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session API — JdbcIndexedSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html)
- [Spring Session API — DefaultCookieSerializer](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/DefaultCookieSerializer.html)
- [Spring Framework — Testing with MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Awaitility — Usage](https://github.com/awaitility/awaitility/wiki/Usage)
- [Redis — Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
