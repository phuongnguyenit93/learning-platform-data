# Giới hạn tạo phiên để tránh làm cạn bộ nhớ hoặc dung lượng kho

Spring Session cho phép nhiều instance ứng dụng lưu `HttpSession` vào Redis hoặc JDBC dùng chung. Khi lượng đăng nhập tăng đột biến, bot liên tục tạo session hoặc ứng dụng vô tình tạo session cho mọi request, kho session có thể tăng nhanh về số lượng key/row và tổng dung lượng. Hậu quả có thể là Redis chạm `maxmemory`, database đầy dung lượng hoặc connection pool quá tải, làm ảnh hưởng cả những người dùng đang đăng nhập bình thường.

Giới hạn tạo session cần được thiết kế ở nhiều lớp: chỉ tạo session khi thực sự cần, giới hạn số phiên trên mỗi tài khoản, kiểm soát tốc độ tạo session từ client, đặt timeout hợp lý, giới hạn kích thước thuộc tính và bảo vệ năng lực của Redis/JDBC. Spring Session cung cấp repository và vòng đời session; chính sách quota toàn hệ thống hoặc theo tenant thường cần được ứng dụng bổ sung.

## 1. Vì sao session có thể làm cạn tài nguyên?

### 1.1. Tăng số lượng session

Một session thường được tạo khi ứng dụng cần lưu trạng thái giữa nhiều request, ví dụ sau đăng nhập, khi lưu CSRF token, khi bắt đầu OAuth2 authorization flow hoặc khi ứng dụng gọi `request.getSession()`. Nếu một endpoint công khai vô tình tạo session cho mỗi request, crawler hoặc bot có thể tạo hàng trăm nghìn session mà không cần đăng nhập.

Số session tăng bởi nhiều nguồn:

- Người dùng thật đăng nhập trên nhiều thiết bị/trình duyệt.
- Session anonymous được tạo trước login hoặc trong quy trình giỏ hàng.
- Bot gọi endpoint làm phát sinh session.
- Client không giữ cookie nên mỗi request tạo một session mới.
- Session timeout quá dài hoặc cleanup không chạy.
- Ứng dụng tạo session sớm trong filter/controller dù request không cần trạng thái.

### 1.2. Tăng kích thước từng session

Số session không phải yếu tố duy nhất. Một session có thể chứa nhiều object hoặc object graph lớn:

- Danh sách sản phẩm hoặc kết quả tìm kiếm đầy đủ.
- JPA entity và quan hệ đã tải.
- DTO chứa ảnh, nội dung lớn hoặc dữ liệu lặp.
- `SecurityContext` với custom principal quá nặng.
- Nhiều bản snapshot không còn được dùng.

Kích thước session tăng làm tăng bộ nhớ Redis, dung lượng database, băng thông mạng và thời gian serialize/deserialize. Một request tưởng như đơn giản có thể ghi lại nhiều byte hơn dự kiến.

### 1.3. Tác động tới Redis và JDBC

| Kho session | Tài nguyên có thể cạn | Biểu hiện thường gặp |
|---|---|---|
| Redis | `maxmemory`, RAM dành cho key/index, replication buffer, network và connection | Lệnh ghi lỗi khi hết bộ nhớ, eviction làm mất session, latency tăng |
| JDBC | Disk, transaction log/WAL, index, connection pool, IOPS | Insert/update chậm, cleanup kéo dài, lock contention, hết connection |
| Cả hai | CPU serialize/deserialize, mạng và số lượng session đồng thời | p95/p99 tăng, request timeout, người dùng bị yêu cầu đăng nhập lại |

Spring Session không tự đặt một quota tổng thể cho toàn bộ Redis hoặc database. Cần kết hợp giới hạn ở ứng dụng với capacity planning và giới hạn tài nguyên ở tầng lưu trữ.

## 2. Chỉ tạo session khi thực sự cần

### 2.1. Tránh gọi `getSession()` vô điều kiện

Trong Servlet API:

- `request.getSession()` tạo session mới nếu request chưa có session.
- `request.getSession(true)` có hành vi tương tự.
- `request.getSession(false)` chỉ lấy session hiện có; nếu không có thì trả `null`.

Ở endpoint chỉ cần đọc trạng thái đăng nhập hoặc kiểm tra session tồn tại, dùng `getSession(false)` thay vì vô tình tạo session mới.

```java
@GetMapping("/health/ping")
public String ping(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    return session == null ? "no-session" : "session-present";
}
```

Không gọi `getSession()` trong filter chung cho mọi request chỉ để ghi log hoặc đo thời gian. Việc đó có thể biến traffic tĩnh như CSS, ảnh, favicon và health check thành một nguồn tạo session lớn.

### 2.2. Đặt chính sách tạo session của Spring Security

`SessionCreationPolicy` kiểm soát cách Spring Security sử dụng `HttpSession`:

| Chính sách | Hành vi của Spring Security | Khi phù hợp |
|---|---|---|
| `ALWAYS` | Luôn tạo session | Ứng dụng thực sự cần session cho mọi request; cần đánh giá kỹ chi phí |
| `IF_REQUIRED` | Chỉ tạo khi chức năng Security cần | Ứng dụng web truyền thống dùng form login, request cache hoặc CSRF trong session |
| `NEVER` | Không chủ động tạo session nhưng có thể dùng session đã tồn tại | Ứng dụng muốn tránh Security tự tạo session nhưng vẫn chấp nhận session do thành phần khác tạo |
| `STATELESS` | Security không tạo session và không dùng session để lấy SecurityContext | API xác thực bằng bearer token, không dựa vào `HttpSession` |

Ví dụ cho API stateless:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
```

Ví dụ này dành cho API dùng bearer JWT; không áp dụng máy móc cho giao diện web dùng cookie/session. `STATELESS` chỉ điều khiển cách Spring Security lưu trạng thái xác thực. Code ứng dụng hoặc thư viện khác vẫn có thể gọi `request.getSession()` và tạo session nếu không được kiểm soát.

### 2.3. Phân tách security chain cho API và web

Một ứng dụng có thể có cả trang web dùng session và API stateless. Nên tách `SecurityFilterChain` theo matcher và đặt thứ tự rõ ràng. API không cần session không nên vô tình dùng cấu hình form login, request cache hoặc CSRF token repository dựa trên session của web.

Không tắt CSRF một cách tổng quát để giảm session. Với ứng dụng xác thực bằng cookie, CSRF vẫn cần được xử lý đúng. Với API bearer token không tự động gửi bởi browser, có thể chọn chính sách CSRF phù hợp dựa trên cách credential được truyền.

### 2.4. Những thành phần có thể tạo session ngoài ý muốn

Rà soát các điểm sau:

- `HttpSessionRequestCache` lưu request ban đầu để chuyển về sau login.
- `HttpSessionCsrfTokenRepository` lưu CSRF token trong session.
- OAuth2/OIDC authorization request repository lưu state trong session.
- Form login và session authentication strategy.
- Controller hoặc service gọi `getSession()`.
- Filter ghi flash message hoặc thông tin điều hướng.
- Thư viện bên thứ ba dùng `HttpSession`.

Không phải thành phần nào tạo session cũng là lỗi. Hãy xác định route nào cần session và tránh tạo nó trên các route công khai không cần trạng thái.

## 3. Đặt timeout và dọn session hết hạn

### 3.1. Chọn `maxInactiveInterval` phù hợp

Spring Session sử dụng inactivity timeout: session hết hạn khi không có request hoạt động trong khoảng thời gian cấu hình. Timeout càng dài thì số session đồng thời còn tồn tại càng lớn.

Ví dụ cấu hình 30 phút:

```yaml
spring:
  session:
    timeout: 30m
```

Hoặc cấu hình trực tiếp với Redis Servlet repository:

```java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
public class SessionConfiguration {
}
```

Giá trị timeout phải dựa trên nhu cầu nghiệp vụ và rủi ro bảo mật. Ứng dụng ngân hàng hoặc quản trị có thể cần timeout ngắn hơn; một luồng nhập liệu dài có thể cần cơ chế lưu nháp bền vững thay vì kéo dài session vô hạn.

### 3.2. Timeout server-side khác thời hạn cookie

Cookie session có thể là cookie phiên của trình duyệt, trong khi repository có `maxInactiveInterval` riêng. Xóa cookie khi đóng browser không bảo đảm server đã xóa session ngay; ngược lại, cookie vẫn còn cũng không làm session đã hết hạn trở nên hợp lệ.

Không dựa vào `Max-Age` của cookie làm cơ chế dọn kho. Repository mới là nơi xác định session còn hợp lệ hay không. Khi kiểm tra dung lượng, phải tính cả session hết hạn nhưng đang chờ tác vụ dọn vật lý.

### 3.3. Redis expiration và cleanup

Spring Session Redis đặt TTL trên các key liên quan đến session. Với repository indexed, có thể có key expiration và hash session được giữ thêm một khoảng đệm để xử lý event/index cleanup. Vì vậy, số key quan sát tại một thời điểm có thể cao hơn số session còn hợp lệ.

Theo dõi:

- Số session đang hoạt động theo repository/index.
- Số key session và key expiration trong namespace.
- TTL/expiration lag.
- Redis memory used, fragmentation và eviction count.
- Tốc độ tạo/xóa session.

Không tự xóa key nội bộ của Spring Session bằng pattern scan trong request path. Nếu cần dọn dữ liệu bất thường, dùng repository API hoặc quy trình bảo trì đã kiểm thử.

### 3.4. JDBC cleanup

Với `JdbcIndexedSessionRepository`, `EXPIRY_TIME` xác định thời điểm hết hạn. Tác vụ cleanup xóa các hàng hết hạn khỏi `SPRING_SESSION`; khóa ngoại có thể xóa các thuộc tính tương ứng ở `SPRING_SESSION_ATTRIBUTES`.

Nếu cleanup bị tắt, lỗi hoặc chạy chậm, hàng hết hạn vẫn chiếm disk và index. Theo dõi số hàng hết hạn, thời gian cleanup, số hàng xóa mỗi lần và query plan trên `EXPIRY_TIME`. Với bảng lớn, có thể cần batch cleanup hoặc job riêng theo khả năng database.

## 4. Giới hạn số phiên trên mỗi tài khoản

### 4.1. Dùng Spring Security concurrent-session control

Spring Security có thể giới hạn số session đồng thời theo principal. Khi dùng Spring Session trong nhiều instance, nên dùng `SpringSessionBackedSessionRegistry` với repository hỗ trợ `FindByIndexNameSessionRepository` để registry tra cứu session từ kho dùng chung.

Ví dụ giới hạn tối đa ba phiên cho một tài khoản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.security.SpringSessionBackedSessionRegistry;

@Configuration
public class ConcurrentSessionConfiguration {

    @Bean
    SessionRegistry sessionRegistry(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        return new SpringSessionBackedSessionRegistry<>(repository);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SessionRegistry sessionRegistry) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .formLogin(form -> form.permitAll())
            .sessionManagement(session -> session
                .maximumSessions(3)
                .sessionRegistry(sessionRegistry))
            .build();
    }
}
```

Khi vượt giới hạn, cấu hình mặc định có thể đánh dấu session cũ hết hạn để request tiếp theo bị `ConcurrentSessionFilter` xử lý. Nếu muốn từ chối đăng nhập mới thay vì thu hồi session cũ, có thể dùng `maxSessionsPreventsLogin(true)` trong các phiên bản Spring Security hỗ trợ.

### 4.2. Điều kiện để principal index hoạt động

Repository phải lưu principal name vào session. `PrincipalNameIndexResolver` có thể lấy tên từ `SecurityContext` hoặc thuộc tính principal index. Nếu ứng dụng dùng authentication tùy chỉnh, cần xác minh `findByPrincipalName(username)` trả đủ các session.

Không dùng `SessionRegistryImpl` cục bộ cho giới hạn toàn cụm nếu mỗi instance có thể nhận login khác nhau. Registry local có thể đếm thiếu session được tạo ở node khác.

### 4.3. Giới hạn theo tài khoản không phải quota toàn hệ thống

`maximumSessions(3)` giới hạn số phiên của một principal. Nó không giới hạn tổng số session anonymous, tổng số tài khoản đang đăng nhập hoặc tổng byte trong Redis/JDBC. Một bot có thể tạo rất nhiều anonymous session trước khi xác thực nếu ứng dụng cho phép.

Vì vậy, cần phối hợp quota per-principal với rate limit theo IP/device, giới hạn tạo session anonymous và capacity guard toàn hệ thống nếu workload đòi hỏi.

## 5. Admission control và quota tạo session

### 5.1. Các lớp giới hạn

Một thiết kế thường kết hợp:

| Lớp | Khóa quota | Mục tiêu |
|---|---|---|
| Edge/WAF/API gateway | IP, subnet, route, client identity | Chặn bot và burst trước khi request vào ứng dụng |
| Ứng dụng trước khi tạo session | IP, device token hoặc anonymous flow | Ngăn endpoint công khai tạo session vô hạn |
| Spring Security | Principal/account | Giới hạn session đã xác thực trên mỗi tài khoản |
| Admission control phân tán | Tenant, toàn ứng dụng hoặc nhóm người dùng | Giữ số session trong giới hạn capacity đã tính |
| Redis/JDBC | Bộ nhớ, disk, connection, query capacity | Bảo vệ hạ tầng lưu trữ khi quota ứng dụng bị vượt hoặc lỗi |

Không có một giới hạn duy nhất thay thế được tất cả lớp. Ví dụ rate limit IP không ngăn được một người dùng tạo nhiều session từ nhiều IP; giới hạn per-principal không ngăn anonymous session flood.

### 5.2. Đặt quota toàn cục và theo tenant

Giả sử hệ thống có ngân sách tối đa 200.000 session active. Có thể đặt quota vận hành thấp hơn, ví dụ 150.000, để giữ headroom cho tăng trưởng, rolling deployment và key phụ. Tenant lớn có thể có quota riêng nhưng tổng quota tenant không được vượt ngân sách toàn hệ thống.

Một bảng quota có thể biểu diễn:

| Phạm vi | Ví dụ quota | Khi vượt |
|---|---:|---|
| Toàn ứng dụng | 150.000 session | Từ chối tạo session mới không thiết yếu, phát cảnh báo |
| Một tenant | 20.000 session | Trả lỗi quota riêng cho tenant đó |
| Một principal | 3 session đã xác thực | Áp dụng concurrent-session policy |
| Một IP | 30 lần tạo/login trong 5 phút | Rate limit hoặc yêu cầu challenge |

Các con số chỉ minh họa. Quota thực tế phải dựa trên đo đạc payload, RAM/disk, số key/row và tải đỉnh.

### 5.3. Admission check phải nằm trước thao tác tạo/lưu session

Nếu kiểm tra quota sau khi đã gọi `request.getSession()` hoặc sau khi repository đã lưu session, hệ thống đã tiêu tốn tài nguyên trước khi từ chối. Hãy đặt admission gate trước bước tạo session trong luồng login hoặc trước endpoint tạo anonymous session.

Với xác thực Servlet, có thể tích hợp kiểm tra per-principal vào chiến lược xác thực session hoặc một thành phần điều phối login. Với anonymous session, đặt filter/handler ở trước code gọi `getSession()` và chỉ áp dụng cho route thực sự cần tạo session. Cần bảo đảm các đường tạo session khác cũng được kiểm soát.

### 5.4. Tránh check-then-act không nguyên tử

Mẫu sau không an toàn dưới tải đồng thời:

```text
if (countSessions() < limit) {
    createSession();
}
```

Hai node có thể cùng đọc thấy còn một slot rồi cùng tạo session, làm quota bị vượt. Đây là race condition giữa kiểm tra và ghi.

Thay vào đó, cần thao tác reserve slot có tính nguyên tử ở kho dùng chung, ví dụ Redis Lua script, transaction/row lock ở JDBC hoặc một quota service chuyên dụng. Chỉ tạo session sau khi reserve thành công. Nếu tạo session thất bại, phải release reservation; nếu tiến trình chết giữa reserve và create, reservation cần lease/TTL để tự hết hạn.

### 5.5. Mô hình reservation có lease

Một admission service có thể cung cấp API:

```java
public interface SessionAdmissionService {

    Reservation reserve(String scope, String requestId);

    void confirm(Reservation reservation, String sessionId);

    void release(Reservation reservation);
}
```

Luồng xử lý:

1. `reserve` atomically kiểm tra quota và cấp reservation có TTL ngắn.
2. Ứng dụng tạo và lưu session trong Spring Session repository.
3. `confirm` liên kết reservation với session ID hoặc tăng bộ đếm đã xác nhận.
4. Nếu lưu session lỗi, `release` reservation.
5. Job đối soát loại reservation hết lease và so sánh quota với session thực tế.

`requestId` giúp thao tác retry có tính idempotent. Không giữ reservation vô thời hạn nếu request bị hủy hoặc node crash.

### 5.6. Redis Lua minh họa quota nguyên tử

Với quota đơn giản, có thể dùng một Redis counter và script để kiểm tra rồi tăng trong một thao tác nguyên tử:

```lua
-- KEYS[1]: quota counter key
-- ARGV[1]: maximum allowed reservations
-- ARGV[2]: reservation TTL in seconds
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local maximum = tonumber(ARGV[1])

if current >= maximum then
    return 0
end

local nextValue = redis.call('INCR', KEYS[1])
if nextValue == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
return 1
```

Đây chỉ là ví dụ minh họa reservation counter có TTL, không phải một quota service production hoàn chỉnh. TTL trên toàn counter có thể reset quota không đúng nếu reservation có vòng đời khác nhau; release cũng phải idempotent và tránh giảm counter hai lần. Với quota production, thường cần lưu từng reservation ID trong Redis Set/Hash hoặc dùng Lua script quản lý reservation và lease riêng, đồng thời có reconciliation job.

Redis Cluster yêu cầu các key mà một Lua script thao tác cùng nằm trong hash slot. Thiết kế key theo tenant/scope và hash tag phù hợp; kiểm thử script trên topology thực tế.

## 6. Giới hạn tốc độ tạo session và chống session flood

### 6.1. Rate limit ở edge

WAF hoặc API gateway có thể giới hạn request theo IP, route và client fingerprint trước khi request vào ứng dụng. Đặt giới hạn chặt hơn cho các endpoint dễ tạo session như login, cart initialization, OAuth2 authorization start hoặc endpoint cấp CSRF token.

Không dùng IP làm định danh duy nhất cho người dùng vì NAT/VPN có thể gom nhiều người thật vào cùng IP. Có thể kết hợp IP, account, device cookie không nhạy cảm và hành vi request; cần tránh fingerprinting quá mức hoặc lưu dữ liệu nhận dạng không cần thiết.

### 6.2. Rate limit ở ứng dụng

Nếu ứng dụng cần rate limit theo trạng thái đăng nhập, dùng bucket phân tán như Redis token bucket hoặc sliding window. Bộ đếm phải dùng chung giữa các node; `ConcurrentHashMap` trong mỗi instance không bảo vệ được quota toàn cụm.

Rate limit nên trả `429 Too Many Requests` cùng `Retry-After` khi phù hợp. Không tạo session chỉ để lưu bộ đếm rate limit; nếu làm vậy, chính cơ chế chống flood lại tạo thêm session.

### 6.3. Chống client không giữ cookie

Một client có thể bỏ cookie sau mỗi response, khiến server không nhận lại session ID cũ và tạo session mới trên request tiếp theo. Theo dõi tỷ lệ session mới trên số client/request và số cookie bị thiếu. Với browser hợp lệ, kiểm tra Domain, Path, Secure, SameSite, reverse proxy và CORS trước khi kết luận client cố tình bỏ cookie.

Không bật session creation cho mọi request như cách sửa lỗi cookie. Điều đó có thể khuếch đại session flood.

## 7. Giới hạn kích thước session

### 7.1. Lưu dữ liệu tối thiểu

Session nên chứa dữ liệu nhỏ, cần thiết để nối trạng thái giữa request. Thay vì lưu toàn bộ đơn hàng hoặc entity graph, lưu ID rồi truy vấn nguồn dữ liệu bền vững khi cần.

Ví dụ:

```java
// Không nên: lưu toàn bộ entity graph hoặc danh sách kết quả lớn.
session.setAttribute("order", orderEntity);

// Nên: lưu tham chiếu nhỏ và truy vấn dữ liệu khi cần.
session.setAttribute("currentOrderId", orderId);
```

Không lưu `HttpServletRequest`, `DataSource`, service, repository, stream, file handle hoặc object có vòng đời gắn với một node. Những object này vừa khó serialize vừa làm payload lớn hoặc không tương thích giữa các phiên bản.

### 7.2. Đặt ngân sách byte cho session

Ứng dụng có thể định nghĩa ngân sách, ví dụ session thông thường dưới 16 KB và session có workflow đặc biệt dưới 64 KB. Đây là chính sách ứng dụng, không phải giới hạn mặc định của Spring Session. Cần đo kích thước serialized payload trong test và production bằng metric an toàn.

Tránh serialize toàn bộ session để đo kích thước trên mỗi request vì chính phép đo có thể tăng CPU và memory. Có thể đo tại điểm save, sample một tỷ lệ request hoặc dùng serializer wrapper có thống kê số byte.

### 7.3. Giới hạn số thuộc tính và collection

Không cho client gửi một mảng không giới hạn rồi lưu trực tiếp vào session. Validate số phần tử, chiều dài chuỗi, số nested object và độ sâu graph. Với dữ liệu lớn, dùng database/object storage và chỉ lưu reference trong session.

## 8. Bảo vệ Redis khỏi cạn bộ nhớ

### 8.1. Capacity planning

Ước lượng bộ nhớ theo:

\[
M_{sessions} \approx N_{active} \times (S_{payload}+S_{key/index}+S_{overhead})
\]

Trong đó:

- `N_active`: số session còn tồn tại, bao gồm phần session hết hạn nhưng đang chờ cleanup.
- `S_payload`: kích thước serialized attributes trung bình.
- `S_key/index`: key session, expiration key và index phụ nếu có.
- `S_overhead`: metadata Redis, allocator, fragmentation và overhead cấu trúc dữ liệu.

Ví dụ, 100.000 session với payload trung bình 8 KB đã tương đương khoảng 800 MB chỉ tính payload thô. Bộ nhớ thực tế cao hơn do key, object overhead, fragmentation, replication và buffer. Hãy đo bằng workload đại diện thay vì chỉ nhân kích thước JSON.

### 8.2. Chọn `maxmemory` và eviction policy có chủ đích

Redis có `maxmemory` và các eviction policy. Với session là trạng thái xác thực quan trọng, policy tự động evict key session có thể làm người dùng bị logout ngẫu nhiên. Cần đánh giá chính sách theo kiến trúc:

- Dùng Redis chuyên cho session giúp tránh cache nghiệp vụ chiếm hết quota session.
- `noeviction` khiến thao tác ghi mới lỗi khi chạm giới hạn thay vì âm thầm xóa key; ứng dụng phải giám sát và xử lý lỗi ghi.
- Các policy `allkeys-*` có thể evict cả key không TTL; `volatile-*` chỉ chọn trong nhóm key có expiration nhưng vẫn có thể xóa session có TTL.
- Không coi eviction là cơ chế cleanup session đúng nghiệp vụ.

Chọn policy phù hợp với yêu cầu availability và bảo mật; cấu hình phải được kiểm thử khi Redis đạt ngưỡng `maxmemory`. Cần cảnh báo trước khi chạm giới hạn, không chờ đến khi lệnh ghi thất bại.

### 8.3. Tách Redis session khỏi cache không quan trọng

Nếu cache có thể tái tạo và session không thể tự phục hồi, nên tách chúng ra instance/cluster hoặc ít nhất tách resource budget và policy. Dùng chung một Redis với eviction policy cho cache có thể làm key session bị xóa theo áp lực bộ nhớ.

### 8.4. Theo dõi memory và eviction

Theo dõi `used_memory`, `used_memory_peak`, `maxmemory`, `mem_fragmentation_ratio`, `evicted_keys`, `expired_keys`, rejected writes, connected clients và latency. Các tên metric có thể khác theo exporter. Cảnh báo theo xu hướng tăng và thời gian còn lại trước khi đạt capacity.

## 9. Bảo vệ JDBC khỏi tăng trưởng không giới hạn

### 9.1. Dọn session hết hạn

JDBC repository lưu session và attributes trong hai bảng. Mỗi thuộc tính session thường là một row trong bảng attributes. Nếu ứng dụng tạo nhiều session hoặc lưu nhiều thuộc tính, bảng `SPRING_SESSION_ATTRIBUTES` có thể tăng nhanh hơn bảng session.

Đảm bảo cleanup job chạy, index `EXPIRY_TIME` tồn tại và database có đủ dung lượng cho bảng, index, transaction log/WAL và backup. Theo dõi số row hết hạn và độ trễ cleanup.

### 9.2. Batch cleanup và tải database

Một lệnh xóa quá nhiều session trong một transaction có thể tạo lock, WAL lớn và ảnh hưởng request bình thường. Khi dữ liệu lớn, cân nhắc job batch theo phạm vi expiry và commit từng batch. Nếu thay query cleanup mặc định, phải bảo đảm giữ đúng semantics, cascade attributes và hỗ trợ vendor database đang dùng.

### 9.3. Connection pool khi scale out

Nếu có 10 instance, mỗi instance mở pool tối đa 30 connection, tổng tiềm năng có thể lên tới 300 connection chưa kể job, admin và dịch vụ khác. Tính tổng connection theo toàn cụm và giới hạn pool từng node. Khi database chậm, pool cạn có thể làm request timeout và tạo retry storm.

## 10. Quản lý session anonymous và login flow

### 10.1. Anonymous session không nên tồn tại vô hạn

Một số ứng dụng cần giỏ hàng trước login hoặc lưu OAuth2 state. Đặt timeout ngắn hơn cho flow anonymous nếu kiến trúc hỗ trợ, giới hạn số lượng theo IP/device và chuyển dữ liệu giỏ hàng sang storage phù hợp nếu cần tồn tại lâu.

Không dùng một session anonymous mới cho mỗi page view. Tái sử dụng cookie session hợp lệ và chỉ tạo khi flow thực sự cần.

### 10.2. Hợp nhất anonymous session sau login

Sau login, ứng dụng có thể chuyển giỏ hàng anonymous sang tài khoản. Hãy xác minh quyền sở hữu dữ liệu, xoay session ID theo session fixation protection và xóa hoặc đánh dấu dữ liệu anonymous cũ đã được hợp nhất. Tránh giữ hai bản session lớn không cần thiết.

### 10.3. Không để login retry tạo nhiều reservation/session

Client có thể retry login khi timeout. Dùng request correlation/idempotency cho admission reservation và xử lý xác thực để retry không tạo nhiều slot quota hoặc session trùng. Xóa reservation nếu authentication thất bại hoặc session save lỗi.

## 11. Kiểm thử giới hạn và áp lực tải

### 11.1. Kiểm thử không tạo session ngoài ý muốn

Gửi nhiều request tới health check, static resource, public read-only endpoint và API stateless. Xác minh repository không tăng session count. Kiểm tra `getSession(false)` và cấu hình `SessionCreationPolicy` của từng security chain.

### 11.2. Kiểm thử per-principal quota

1. Cấu hình `maximumSessions(3)`.
2. Đăng nhập cùng tài khoản trên ba browser/client.
3. Thử đăng nhập client thứ tư.
4. Xác minh chính sách được áp dụng: đánh dấu phiên cũ hoặc từ chối login mới.
5. Lặp lại khi login được xử lý ở các instance khác nhau.

### 11.3. Kiểm thử global admission quota

Chạy nhiều node đồng thời gửi yêu cầu tạo session khi quota chỉ còn một slot. Chỉ một request được reserve thành công. Kiểm tra release khi session creation thất bại, lease hết hạn khi node crash và retry cùng request ID không tăng quota hai lần.

### 11.4. Kiểm thử session flood

Dùng load test tạo anonymous session với nhiều IP/client, client không giữ cookie và burst login. Theo dõi số session mới/giây, số session active, memory/disk, cleanup lag, eviction và latency. Xác minh rate limit trả `429` hoặc response phù hợp mà không tạo session bổ sung.

### 11.5. Kiểm thử payload lớn

Tạo session với DTO ở kích thước bình thường và vượt ngân sách. Xác minh ứng dụng từ chối hoặc rút gọn dữ liệu trước khi lưu. Đo serialization time, bytes written và repository latency.

### 11.6. Kiểm thử storage saturation

Trong môi trường test cô lập, mô phỏng Redis gần `maxmemory` hoặc database gần giới hạn disk/pool. Xác minh cảnh báo phát trước ngưỡng, lệnh ghi lỗi được xử lý an toàn, không fallback sang local session và người dùng hiện hữu không bị cấp quyền dựa trên trạng thái mặc định.

## 12. Giám sát và cảnh báo

| Chỉ số | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| Session create rate | Tốc độ tạo session mới | Tăng đột biến so với baseline |
| Active session count | Số session còn tồn tại | Tiến gần quota hoặc tăng liên tục |
| Average/max payload bytes | Kích thước session | Tăng sau release hoặc vượt ngân sách |
| Session save failures | Lỗi ghi repository | Có lỗi OOM, timeout hoặc serialization |
| Redis memory/headroom | Dung lượng còn lại | Dưới ngưỡng vận hành đã đặt |
| Redis evicted keys | Số key bị eviction | Bất kỳ eviction không mong muốn nào trong store session |
| JDBC expired row backlog | Hàng hết hạn chờ cleanup | Backlog tăng hoặc cleanup lag vượt ngưỡng |
| JDBC pool active/pending | Áp lực connection | Pending tăng, pool gần cạn |
| Admission rejected | Số yêu cầu bị quota từ chối | Tăng đột biến hoặc tenant vượt mức thường lệ |
| Session lookup miss | ID không còn session | Tăng bất thường sau deploy hoặc failover |

Không ghi raw session ID, cookie, access token hoặc toàn bộ session attributes vào log/metric. Dùng tenant ID đã chuẩn hóa hoặc bucket, request ID và outcome; tránh metric label có cardinality cao.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Redis tăng key liên tục dù ít user login | Endpoint công khai tạo session mỗi request hoặc client không giữ cookie | Kiểm tra `getSession()`, cookie và session create rate |
| Anonymous session flood | Bot gọi route tạo session trước xác thực | Rate limit ở WAF/gateway và admission filter trước session creation |
| Redis OOM khi traffic tăng | Quota không có, payload lớn hoặc TTL dài | Capacity planning, quota, giảm payload và timeout hợp lý |
| Người dùng logout ngẫu nhiên khi Redis đầy | Eviction policy xóa session hoặc write/expiration behavior không được giám sát | Dùng policy có chủ đích, tách Redis và cảnh báo eviction |
| JDBC table tăng mãi | Cleanup job tắt/lỗi hoặc query không dùng index | Kiểm tra cron, `EXPIRY_TIME`, query plan và batch cleanup |
| Một principal vượt giới hạn session | Registry local hoặc race condition khi login đồng thời | Dùng `SpringSessionBackedSessionRegistry` và kiểm thử đa node |
| Global quota vẫn bị vượt | Check-then-act không nguyên tử | Atomic reservation bằng Redis script/DB transaction |
| Quota bị kẹt sau node crash | Reservation không có lease hoặc không release | Dùng TTL lease, idempotency và reconciliation |
| `STATELESS` nhưng vẫn phát sinh session | Code ứng dụng hoặc thư viện gọi `getSession()` | Tìm mọi call site và kiểm tra filter chain |
| Session payload tăng sau release | Thêm object graph hoặc principal lớn | Đo bytes, lưu ID thay vì entity và đặt budget |
| Login retry tạo nhiều session | Retry không idempotent | Correlation/idempotency key và reservation có trạng thái |

## 14. Quy trình triển khai giới hạn tạo session

1. Đo baseline: session create rate, active count, payload size, TTL và storage headroom.
2. Xác định route nào thật sự cần session; dùng `getSession(false)` cho thao tác chỉ đọc.
3. Tách API stateless khỏi web session bằng `SessionCreationPolicy` phù hợp.
4. Rà soát request cache, CSRF, OAuth2 và filter có thể tạo session.
5. Đặt `maxInactiveInterval` phù hợp và xác minh Redis TTL/JDBC cleanup hoạt động.
6. Dùng `maximumSessions` với `SpringSessionBackedSessionRegistry` để giới hạn per-principal.
7. Đặt rate limit theo IP/route và admission gate cho anonymous/session creation.
8. Nếu cần global/tenant quota, dùng reservation nguyên tử, lease, idempotency và reconciliation.
9. Giới hạn kích thước session và số thuộc tính; lưu ID thay vì object graph lớn.
10. Capacity plan Redis/JDBC, connection pool, index, eviction policy và cleanup.
11. Kiểm thử burst, client không giữ cookie, login đồng thời, node crash và storage saturation.
12. Theo dõi quota, session create rate, payload bytes, eviction, cleanup lag và lỗi ghi.

Giới hạn tạo session hiệu quả bắt đầu bằng việc không tạo session khi không cần, sau đó giới hạn phiên theo principal và kiểm soát tốc độ ở edge. Khi hệ thống cần quota toàn cục hoặc theo tenant, phải dùng admission reservation có tính nguyên tử và có thể phục hồi sau crash. Kết hợp timeout, payload budget, Redis/JDBC capacity planning và giám sát giúp Spring Session phục vụ nhiều instance mà không để session flood hoặc dữ liệu phình to làm cạn kho dùng chung.

## Tài liệu tham khảo

- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — Redis Configuration and Expiration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration and Cleanup](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Session API — FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Data Redis — RedisTemplate, Serialization and Connection](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Redis — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis — Memory optimization](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/)
