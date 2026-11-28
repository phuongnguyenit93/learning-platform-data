# Tạo, đọc, lưu, xóa và thay đổi định danh trên Redis

## Mục tiêu bài học

Redis là kho dữ liệu key-value trong bộ nhớ, thường được dùng làm repository chia sẻ cho session khi ứng dụng Spring chạy trên nhiều instance. Để vận hành Spring Session với Redis, cần hiểu các thao tác cơ bản trên Redis và cách Spring Session ánh xạ vòng đời của một phiên vào repository.

Sau bài học, bạn có thể:

- Giải thích cách Redis tổ chức key, value, hash và TTL.
- Phân biệt thao tác Redis trực tiếp với thao tác session qua Spring Session.
- Mô tả cách tạo, đọc, cập nhật, lưu và xóa session trong Redis.
- Hiểu vì sao dữ liệu session có thể được ghi ở cuối request hoặc ngay khi thay đổi.
- Thay đổi Session ID an toàn qua Servlet API.
- Kiểm tra key, kiểu dữ liệu và TTL bằng redis-cli mà không làm hỏng dữ liệu phiên.
- Nhận diện rủi ro khi tự sửa hoặc xóa key nội bộ của Spring Session.

## 1. Redis lưu dữ liệu theo key

Redis là một data store dạng key-value. Mỗi giá trị được truy cập thông qua một key. Key có thể đại diện cho string, hash, list, set, sorted set hoặc kiểu dữ liệu khác được Redis hỗ trợ.

Một số lệnh cơ bản:

| Lệnh | Tác dụng |
|---|---|
| `SET key value` | Tạo hoặc ghi đè giá trị kiểu string |
| `GET key` | Đọc giá trị kiểu string |
| `DEL key` | Xóa một hoặc nhiều key |
| `EXPIRE key seconds` | Đặt thời hạn tồn tại tính bằng giây |
| `TTL key` | Xem số giây còn lại trước khi key hết hạn |
| `PTTL key` | Xem thời gian còn lại theo mili giây |
| `TYPE key` | Xem kiểu dữ liệu của key |
| `HSET key field value` | Ghi một field vào hash |
| `HGET key field` | Đọc một field trong hash |
| `HGETALL key` | Đọc các field và value của hash |

Ví dụ tạo một key độc lập cho dữ liệu ứng dụng:

~~~text
SET demo:cart:42 "cart-2026"
GET demo:cart:42
EXPIRE demo:cart:42 1800
TTL demo:cart:42
DEL demo:cart:42
~~~

Ví dụ trên minh họa các thao tác Redis cơ bản. Key `demo:cart:42` là dữ liệu ứng dụng do ví dụ tạo ra, không phải key nội bộ của Spring Session.

### Key namespace

Key nên có namespace để phân biệt ứng dụng, môi trường và loại dữ liệu. Ví dụ:

- `shop:dev:cart:42`
- `shop:prod:cache:product:1001`
- `shop:session:sessions:<session-id>`

Spring Session có namespace riêng. Namespace mặc định thường bắt đầu bằng `spring:session`; có thể cấu hình namespace khác theo môi trường và phiên bản Spring Boot.

Không nên để nhiều ứng dụng dùng chung một namespace nếu chúng có cấu trúc dữ liệu hoặc chính sách session khác nhau. Namespace giúp tránh trùng key, nhưng không thay thế quyền truy cập Redis và phân tách dữ liệu giữa các ứng dụng.

## 2. Redis hash và TTL

Spring Session Redis thường lưu dữ liệu session dưới dạng hash hoặc cấu trúc key phụ trợ do repository quản lý. Một hash có thể chứa nhiều field, ví dụ thời điểm tạo, lần truy cập gần nhất, thời hạn không hoạt động và các thuộc tính session đã serialize.

Ví dụ hash độc lập để minh họa Redis:

~~~text
HSET demo:profile:42 name "An" locale "vi"
HGET demo:profile:42 name
HGETALL demo:profile:42
TYPE demo:profile:42
~~~

Kết quả của `HGETALL` phụ thuộc dữ liệu đã lưu. Với session thật, một số giá trị có thể được serialize thành byte array hoặc định dạng mà redis-cli không hiển thị thành văn bản dễ đọc.

### TTL là gì?

TTL (time to live) là thời gian còn lại trước khi key hết hạn. Redis có thể tự loại bỏ key khi TTL kết thúc.

Ví dụ:

~~~text
SET demo:temporary "value"
EXPIRE demo:temporary 60
TTL demo:temporary
~~~

Một số kết quả thường gặp của `TTL`:

- Số dương: key còn tồn tại và còn số giây tương ứng.
- `-1`: key tồn tại nhưng không có thời hạn hết hạn.
- `-2`: key không tồn tại.

Đối với session, thời hạn không hoạt động được cấu hình ở Spring Session. Repository chuyển chính sách này thành thời hạn lưu trữ trên Redis. Việc key vật lý bị xóa và thời điểm repository phát hiện session hết hạn có thể có chi tiết riêng theo implementation.

Không nên tự đặt TTL tùy tiện cho từng key nội bộ của Spring Session. Nếu TTL không còn khớp với metadata của session, repository có thể đọc, xóa hoặc phát sự kiện vòng đời không như mong đợi.

## 3. Spring Session ánh xạ session vào Redis như thế nào?

Trong ứng dụng Servlet, controller thường thao tác qua `HttpSession`. Spring Session tích hợp vào Servlet filter chain và chuyển các thao tác session sang repository Redis.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `HttpSession` | API Servlet mà controller và filter sử dụng |
| `SessionRepositoryFilter` | Bọc request/response và thay cách quản lý session |
| `RedisIndexedSessionRepository` | Repository Redis phổ biến có hỗ trợ index session |
| `RedisConnectionFactory` | Cung cấp kết nối đến Redis |
| `CookieHttpSessionIdResolver` | Đọc và gửi Session ID qua cookie |
| Session ID | Định danh để repository tìm đúng dữ liệu phiên |

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as SessionRepositoryFilter
    participant R as Redis Session Repository
    participant D as Redis

    B->>F: Request + Cookie SESSION
    F->>R: findById(sessionId)
    R->>D: Đọc dữ liệu session
    D-->>R: Hash và metadata
    R-->>F: Session
    F->>F: Bọc request thành HttpSession
    F-->>B: Response
    F->>R: Lưu thay đổi session
    R->>D: Ghi dữ liệu và thời hạn
~~~

Redis là nơi lưu trạng thái chia sẻ. Mỗi instance ứng dụng có thể đọc cùng session nếu dùng cùng Redis endpoint, namespace, serializer và cấu hình tương thích.

Spring Session quản lý key và dữ liệu nội bộ. Ứng dụng không nên tự đoán toàn bộ schema Redis rồi ghi hoặc xóa trực tiếp những key đó.

## 4. Tạo session trên Redis

Thông thường, session được tạo khi ứng dụng hoặc framework yêu cầu session mới. Với Servlet API:

- `request.getSession()` trả session hiện có hoặc tạo mới nếu chưa có.
- `request.getSession(false)` chỉ trả session hiện có; nếu không có thì trả `null`.

Ví dụ controller tạo session khi thêm một mặt hàng:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CartController {

    @PostMapping("/cart")
    public String createOrUpdateCart(
            HttpServletRequest request,
            @RequestParam String cartId) {

        HttpSession session = request.getSession();

        session.setAttribute("cartId", cartId);
        return "Cart stored in session";
    }
}
~~~

Nếu request chưa có session, Spring Session tạo session thông qua repository. Khi response được hoàn tất theo luồng filter, repository lưu dữ liệu và resolver gửi Session ID về client, thường qua cookie.

Tùy cấu hình flush, một số thay đổi có thể được đẩy xuống Redis ngay trong quá trình xử lý. Với chế độ lưu ở cuối request, repository ghi các thay đổi khi request kết thúc.

Không nên tạo session cho mọi endpoint nếu endpoint không cần trạng thái. Dùng `getSession(false)` để kiểm tra phiên hiện có mà không vô tình tạo session mới.

## 5. Đọc session từ Redis

Client gửi lại Session ID trong cookie hoặc header theo resolver đã cấu hình. Spring Session dùng ID đó để tra cứu session trong Redis repository.

Ví dụ đọc thuộc tính mà không tạo session mới:

~~~java
@GetMapping("/cart")
public String readCart(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session == null) {
        return "No active session";
    }

    String cartId = (String) session.getAttribute("cartId");

    return cartId == null ? "Cart not found" : "Cart: " + cartId;
}
~~~

Quy trình đọc:

1. Client gửi cookie chứa Session ID.
2. `SessionRepositoryFilter` đọc ID qua resolver.
3. Repository tìm session trong Redis.
4. Nếu tìm thấy, session được gắn vào request wrapper.
5. Controller đọc thuộc tính qua `getAttribute`.

Nếu Redis không có session tương ứng, session đã hết hạn hoặc ID không hợp lệ, `getSession(false)` trả `null`. Nếu controller gọi `getSession()`, một session mới có thể được tạo.

### Kiểm tra dữ liệu bằng redis-cli

Có thể dùng `SCAN` để tìm key theo namespace:

~~~text
SCAN 0 MATCH spring:session:* COUNT 100
~~~

Lệnh `SCAN` trả cursor và một nhóm key. Tiếp tục gọi `SCAN` với cursor mới cho đến khi cursor bằng `0`. Kết quả có thể thay đổi khi dữ liệu đang được thêm hoặc xóa.

Khi đã có key cụ thể, có thể kiểm tra:

~~~text
TYPE <key>
TTL <key>
PTTL <key>
HGETALL <key>
~~~

Cấu trúc key và field nội bộ phụ thuộc repository và phiên bản Spring Session. Hãy xem các lệnh trên là công cụ quan sát. Không giả định mọi key session đều là hash hoặc mọi thuộc tính đều đọc được thành văn bản.

Trong môi trường production, tránh dùng `KEYS` với pattern rộng vì lệnh này có thể chặn Redis khi số lượng key lớn. `SCAN` phù hợp hơn cho việc duyệt key theo từng đợt.

## 6. Cập nhật và lưu thay đổi session

Khi controller gọi `setAttribute`, Spring Session đánh dấu thuộc tính được cập nhật theo cơ chế lưu của repository.

Ví dụ:

~~~java
HttpSession session = request.getSession();
session.setAttribute("cartId", "cart-100");
session.setAttribute("locale", "vi");
~~~

Có hai khái niệm cần phân biệt:

- `SaveMode` xác định nhóm thuộc tính nào cần được lưu khi session được ghi.
- `FlushMode` xác định thời điểm thay đổi được đẩy xuống repository.

Các chế độ cụ thể và giá trị mặc định phụ thuộc phiên bản Spring Session và repository. Với cấu hình phổ biến:

| Chế độ | Hành vi khái quát |
|---|---|
| `SaveMode.ON_SET_ATTRIBUTE` | Lưu các thuộc tính được đặt hoặc đánh dấu thay đổi |
| `SaveMode.ON_GET_ATTRIBUTE` | Bao gồm cả thuộc tính được đọc trong tập cần lưu |
| `SaveMode.ALWAYS` | Lưu tất cả thuộc tính khi session được lưu |
| `FlushMode.ON_SAVE` | Gom thay đổi và ghi khi session được lưu, thường cuối request |
| `FlushMode.IMMEDIATE` | Ghi thay đổi sớm ngay khi có thể sau thao tác cập nhật |

Ví dụ cấu hình qua properties:

~~~properties
spring.session.redis.namespace=shop:session
spring.session.redis.flush-mode=on-save
spring.session.redis.save-mode=on-set-attribute
spring.session.timeout=30m
~~~

Hãy kiểm tra tên property và giá trị được hỗ trợ trong đúng phiên bản Spring Boot/Spring Session của dự án. Khi đã có auto-configuration, không nên thêm cấu hình thủ công chồng lấn.

### Thay đổi object khả biến

Nếu session chứa một `List`, `Map` hoặc object có thể thay đổi, việc sửa object tại chỗ có thể không được dirty tracking nhận biết theo cách bạn mong muốn.

Ví dụ:

~~~java
@SuppressWarnings("unchecked")
List<String> items =
        (List<String>) session.getAttribute("items");

items.add("BOOK-01");

// Đặt lại để biểu đạt rõ thuộc tính đã thay đổi.
session.setAttribute("items", items);
~~~

Cách dễ kiểm soát hơn là tạo object mới rồi gọi `setAttribute`. Điều này đặc biệt hữu ích với repository dùng chung và nhiều request.

Không nên xem `FlushMode.IMMEDIATE` là cơ chế transaction. Nó điều khiển thời điểm ghi, không tự giải quyết lost update khi nhiều request cùng sửa một thuộc tính.

## 7. Xóa session trên Redis

Khi người dùng đăng xuất hoặc ứng dụng cần hủy phiên, có thể gọi `invalidate()`:

~~~java
@PostMapping("/logout")
public String logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session != null) {
        session.invalidate();
    }

    return "Logged out";
}
~~~

Spring Session xử lý việc xóa session qua repository. Resolver cũng có thể gửi chỉ thị để client xóa cookie hoặc ngừng gửi Session ID.

Các bước khái quát:

1. Ứng dụng lấy session hiện có.
2. Ứng dụng gọi `invalidate()`.
3. Spring Session đánh dấu phiên đã kết thúc.
4. Repository xóa dữ liệu phiên và cập nhật các cấu trúc phụ trợ cần thiết.
5. Resolver gửi response expire cookie hoặc định danh theo cơ chế đang dùng.

Không nên dùng `DEL` trực tiếp lên một key session trong Redis để thay cho `invalidate()`. Một session có thể liên quan đến nhiều key, index hoặc metadata. Xóa một key bằng tay có thể để lại dữ liệu phụ hoặc làm mất event cần thiết.

Nếu cần thao tác quản trị xóa một phiên cụ thể, hãy dùng API repository hoặc chức năng quản trị được ứng dụng cung cấp, không tự sửa cấu trúc Redis nội bộ.

### Xóa một key Redis độc lập

Với dữ liệu ứng dụng do chính bạn quản lý, có thể dùng `StringRedisTemplate`:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TemporaryValueService {

    private final StringRedisTemplate redis;

    public TemporaryValueService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String key, String value) {
        redis.opsForValue().set(key, value);
    }

    public String read(String key) {
        return redis.opsForValue().get(key);
    }

    public Boolean delete(String key) {
        return redis.delete(key);
    }
}
~~~

Đây là thao tác với key nghiệp vụ riêng. Không dùng service này để ghi trực tiếp key nội bộ mà Spring Session quản lý.

## 8. Thay đổi Session ID

Session ID là định danh được client gửi lại trong request. Khi người dùng đăng nhập hoặc thay đổi mức đặc quyền, ứng dụng nên thay ID để phòng chống session fixation.

Trong Servlet API, có thể dùng:

~~~java
request.changeSessionId();
~~~

Spring Session tích hợp với request wrapper để thay ID và cập nhật repository. Resolver gửi định danh mới về client.

Ví dụ minh họa:

~~~java
@PostMapping("/login/complete")
public String completeLogin(HttpServletRequest request) {
    HttpSession session = request.getSession();

    // Thực tế phải xác thực người dùng trước thao tác này.
    request.changeSessionId();

    session.setAttribute("authenticated", true);
    return "Login completed";
}
~~~

Ví dụ trên chỉ mô tả thời điểm đổi ID. Không đặt thuộc tính xác thực dựa trên input client. Trong ứng dụng dùng Spring Security, nên dùng session fixation protection có sẵn của framework và tránh triển khai cơ chế đổi ID thủ công chồng lấn.

### Điều gì thay đổi trong Redis?

Khi Session ID thay đổi, repository cần làm cho định danh mới trỏ đến trạng thái phiên hiện tại và bảo đảm ID cũ không còn được dùng như phiên hợp lệ theo luồng đổi ID. Chi tiết thao tác key, index và thứ tự lưu phụ thuộc repository.

Không nên tự thực hiện:

~~~text
RENAME spring:session:sessions:old-id spring:session:sessions:new-id
~~~

Lệnh này chỉ đổi tên một key. Nó không cập nhật toàn bộ index, metadata, expiration key hoặc trạng thái mà Spring Session quản lý. Dùng `request.changeSessionId()` hoặc cơ chế Spring Security là cách an toàn hơn.

### Phân biệt thay ID và tạo session mới

- Thay ID giữ ngữ cảnh phiên hiện tại nhưng đổi định danh mà client sử dụng.
- Tạo session mới có thể bắt đầu một ngữ cảnh mới và không nhất thiết giữ toàn bộ thuộc tính phiên cũ.
- Invalidate hủy phiên hiện tại và khiến ID cũ không còn tải được phiên đó.

Chọn đúng thao tác theo mục tiêu nghiệp vụ. Sau khi đổi ID, kiểm thử rằng ID mới tải được session và ID cũ không còn được chấp nhận.

## 9. TTL và thời hạn session

Spring Session thường cấu hình thời gian không hoạt động tối đa của phiên. Ví dụ:

~~~properties
spring.session.timeout=30m
~~~

Thời hạn này thường được ánh xạ sang TTL trong Redis repository. Khi session được truy cập, thời điểm truy cập gần nhất và thời hạn có thể được cập nhật theo cấu hình.

Cần phân biệt:

- **Session timeout**: chính sách thời gian không hoạt động của phiên.
- **Redis key TTL**: thời gian còn lại của key vật lý.
- **Cookie Max-Age**: thời gian trình duyệt giữ cookie.
- **Thời điểm phát event hết hạn**: có thể phụ thuộc Redis notification và cách repository phát hiện expiration.

Các giá trị có liên quan nhưng không đồng nhất. Một cookie còn tồn tại không bảo đảm repository còn session. Một key hết hạn cũng không có nghĩa listener được gọi đúng mili giây timeout.

Khi kiểm tra TTL, hãy dùng `TTL` hoặc `PTTL` trên key cụ thể và hiểu key đó thuộc cấu trúc nào. Không tự gia hạn key nội bộ bằng `EXPIRE` để kéo dài phiên; hãy cập nhật thời hạn qua cấu hình hoặc API session phù hợp.

## 10. Namespace và kiểm tra Redis trong môi trường nhiều instance

Các instance của ứng dụng cần thống nhất:

- Redis endpoint hoặc cluster.
- Namespace của Spring Session.
- Cấu hình serialization.
- Chính sách timeout, save mode và flush mode.
- Cấu hình resolver và cookie/header.
- Phiên bản tương thích trong quá trình rolling deployment.

Ví dụ hai instance cùng cấu hình:

~~~properties
spring.data.redis.host=redis.internal
spring.data.redis.port=6379
spring.session.redis.namespace=shop:session
spring.session.timeout=30m
~~~

Nếu App A ghi session vào namespace `shop:session`, còn App B đọc namespace khác, App B sẽ không tìm thấy phiên dù cùng kết nối một Redis server.

### Các lệnh quan sát hữu ích

Với namespace đã cấu hình, có thể dùng:

~~~text
SCAN 0 MATCH shop:session:* COUNT 100
INFO keyspace
DBSIZE
~~~

Các lệnh này giúp quan sát key và thống kê Redis. `DBSIZE` đếm key trong database hiện tại, không chỉ riêng session. `INFO keyspace` cung cấp số liệu theo database. Không dùng kết quả tổng này để kết luận chính xác số phiên nếu Redis còn chứa dữ liệu khác.

Không nên chạy `FLUSHDB` hoặc `FLUSHALL` để dọn session trong môi trường dùng chung. Các lệnh này có thể xóa dữ liệu của nhiều ứng dụng và gây gián đoạn diện rộng.

## 11. Serialization và tương thích dữ liệu

Redis lưu byte hoặc chuỗi; object Java phải được serialize trước khi lưu. Spring Session sử dụng serializer theo cấu hình của repository và phiên bản thư viện.

Khi lưu thuộc tính session:

- Object phải tương thích với serializer.
- Các instance cần dùng serializer tương thích.
- Không nên lưu object phụ thuộc request, connection, thread hoặc persistence context.
- DTO trong session nên có cấu trúc ổn định.
- Rolling deployment cần xem xét khả năng instance cũ đọc dữ liệu do instance mới ghi.

Nếu một instance không deserialize được thuộc tính, request có thể lỗi dù Redis vẫn còn key. Hãy xem log serialization, kiểm tra phiên bản class và serializer trước khi xóa dữ liệu.

Khi đổi cấu trúc DTO, nên duy trì tương thích trong giai đoạn các phiên bản cùng chạy hoặc dùng versioning để chuyển đổi dữ liệu. Tránh dựa vào việc xóa toàn bộ session để che giấu lỗi không tương thích nếu điều đó làm mất trạng thái người dùng ngoài ý muốn.

## 12. Các thao tác Redis trực tiếp cần tránh

Redis cho phép thao tác trực tiếp lên key, nhưng key nội bộ Spring Session là một phần của cấu trúc repository.

Tránh:

- Dùng `SET` để ghi đè key session hash bằng chuỗi.
- Dùng `DEL` một key mà không biết các key phụ trợ liên quan.
- Dùng `RENAME` để tự đổi Session ID.
- Dùng `EXPIRE` để kéo dài TTL mà không cập nhật metadata session.
- Dùng `KEYS *` trên Redis production có nhiều key.
- Dùng `FLUSHDB` hoặc `FLUSHALL` để đăng xuất người dùng.
- Đọc hoặc ghi toàn bộ session attributes vào log.

Nên:

- Dùng `HttpSession` trong controller hoặc service web.
- Dùng Spring Session repository API cho thao tác quản trị được hỗ trợ.
- Dùng RedisTemplate cho key nghiệp vụ do ứng dụng sở hữu.
- Dùng `SCAN`, `TYPE`, `TTL`, `PTTL` để quan sát dữ liệu.
- Dùng metric và log đã che dữ liệu nhạy cảm để vận hành.
- Kiểm thử thao tác xóa, expire và đổi ID trên repository tích hợp.

## 13. Kiểm thử vòng đời session trên Redis

Kiểm thử nên xác minh session có thể được tạo, tải, cập nhật, xóa và đổi ID qua nhiều request.

Một quy trình integration test:

1. Khởi động Redis test instance hoặc Testcontainers.
2. Khởi động Spring application context có Spring Session Redis.
3. Gửi request tạo session và lưu thuộc tính.
4. Lấy cookie hoặc header chứa Session ID từ response.
5. Gửi request tiếp theo với cùng định danh và xác minh thuộc tính được khôi phục.
6. Cập nhật thuộc tính rồi gửi request mới để xác minh dữ liệu đã lưu.
7. Đổi Session ID và xác minh ID mới tải được phiên.
8. Gửi request với ID cũ và xác minh không còn khôi phục được phiên.
9. Invalidate session và xác minh repository không còn trả phiên.
10. Kiểm tra TTL theo cấu hình và xác minh hết hạn trong điều kiện test được kiểm soát.

### Ví dụ kiểm thử qua MockMvc

~~~java
MvcResult created = mockMvc.perform(post("/cart")
        .param("cartId", "cart-100"))
    .andExpect(status().isOk())
    .andReturn();

Cookie cookie = created.getResponse().getCookie("SESSION");

mockMvc.perform(get("/cart")
        .cookie(cookie))
    .andExpect(status().isOk());
~~~

Ví dụ chỉ minh họa việc giữ cookie giữa hai request. Tên cookie phải khớp cấu hình serializer. Để xác minh Redis thật, test cần chạy repository Redis thực tế; mock session trong bộ nhớ không kiểm tra serialization, TTL hoặc keyspace.

### Kiểm thử TTL

Không nên phụ thuộc vào một lần `Thread.sleep` cố định rồi giả định event hoặc key expiration xuất hiện đúng thời điểm. Nên dùng timeout ngắn, polling có giới hạn và kiểm tra trạng thái repository. Redis expiration được xử lý theo cơ chế của server nên thời điểm quan sát có thể lệch so với con số TTL ban đầu.

### Kiểm thử nhiều instance

Khởi động hai application context dùng cùng Redis, namespace và serializer. Tạo session ở App A, lấy ID, gửi request đến App B và xác minh thuộc tính. Sau đó cập nhật ở B và đọc lại ở A. Test này chứng minh session được chia sẻ qua Redis thay vì chỉ nằm trong bộ nhớ một tiến trình.

## 14. Những lỗi thường gặp

**Tạo session nhưng không thấy key trong Redis.**  
Kiểm tra Redis connection, repository auto-configuration, namespace, filter và việc request có thực sự gọi `getSession()` hay không. Với chế độ flush cuối request, kiểm tra sau khi response đã hoàn tất.

**Key tồn tại nhưng controller không đọc được session.**  
Kiểm tra Session ID client gửi, cookie/header resolver, namespace, serializer và TTL.

**TTL là -1.**  
Key có thể không có expiration. Kiểm tra key đó có phải key session hay dữ liệu khác, rồi kiểm tra cấu hình timeout và repository. Không tự áp TTL bằng tay lên key nội bộ.

**Đổi ID nhưng ID cũ vẫn tải được.**  
Kiểm tra luồng `request.changeSessionId()`, Spring Security session fixation configuration và repository. Không tự rename key Redis để sửa.

**Xóa một key nhưng session vẫn tồn tại.**  
Session có thể dùng nhiều key và index. Hãy invalidate hoặc xóa qua repository API thay vì chỉ xóa một key.

**App A thấy session nhưng App B không thấy.**  
Kiểm tra endpoint Redis, namespace, serializer, cookie name, cấu hình resolver và phiên bản ứng dụng.

**Session mất dữ liệu sau rolling deployment.**  
Kiểm tra thay đổi class DTO, serializer và khả năng đọc dữ liệu giữa các phiên bản. Giữ định dạng session tương thích trong giai đoạn chuyển tiếp.

## 15. Tự kiểm tra

1. Redis key và value có vai trò gì?
2. `TTL` trả về những giá trị đặc biệt nào khi key không tồn tại hoặc không có expiration?
3. Spring Session sử dụng `HttpSession` và Redis repository thông qua thành phần nào?
4. Vì sao không nên dùng `DEL` trực tiếp để logout một session?
5. `SaveMode` khác `FlushMode` ở điểm nào?
6. Vì sao thay đổi Session ID nên dùng `request.changeSessionId()`?
7. Session timeout, Redis TTL và cookie Max-Age có giống nhau không?
8. Vì sao hai instance cần dùng cùng namespace và serializer?
9. Khi nào nên dùng `SCAN` thay cho `KEYS`?
10. Cần kiểm thử những gì để xác minh session được chia sẻ qua Redis giữa hai instance?

### Gợi ý trả lời

1. Key là định danh dùng để truy cập dữ liệu; value là dữ liệu được lưu dưới key.
2. `TTL` trả `-1` khi key tồn tại nhưng không có expiration và `-2` khi key không tồn tại.
3. `SessionRepositoryFilter` bọc request và chuyển thao tác session đến repository.
4. Vì một session có thể có nhiều key, index và metadata; `DEL` một key có thể để lại dữ liệu phụ không nhất quán.
5. `SaveMode` chọn thuộc tính được lưu; `FlushMode` chọn thời điểm ghi xuống repository.
6. Vì Spring Session tích hợp với Servlet request và repository để cập nhật định danh cùng dữ liệu liên quan.
7. Không. Timeout là chính sách session phía server, TTL là thời hạn key Redis, Max-Age là thời hạn cookie ở client.
8. Nếu namespace hoặc serializer khác nhau, instance có thể không tìm thấy hoặc không đọc được session.
9. `SCAN` duyệt key theo từng đợt và tránh thao tác chặn lớn như `KEYS` trên production.
10. Tạo session ở A, gửi cùng ID đến B, xác minh thuộc tính, cập nhật ở B và đọc lại ở A.

## Kết luận

Redis cung cấp các thao tác key-value, hash và TTL để lưu dữ liệu có thời hạn. Spring Session sử dụng repository Redis để tạo, tìm, cập nhật và xóa session, trong khi ứng dụng Servlet tiếp tục thao tác qua `HttpSession`. Session ID được truyền qua cookie hoặc header; khi thay ID, ứng dụng nên dùng `request.changeSessionId()` để repository và resolver phối hợp cập nhật đúng.

Các key nội bộ Spring Session có thể gồm dữ liệu phiên, index và metadata expiration. Vì vậy, nên quan sát Redis bằng `SCAN`, `TYPE`, `TTL` và `PTTL`, còn thao tác vòng đời phải đi qua Spring Session API. Khi nhiều instance cùng dùng Redis, namespace, serializer, timeout và resolver cần tương thích; integration test phải xác minh cả tạo, đọc, lưu, xóa và thay đổi định danh.

