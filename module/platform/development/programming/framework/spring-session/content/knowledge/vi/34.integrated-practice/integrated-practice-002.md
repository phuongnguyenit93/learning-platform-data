# Chuyển từ phiên trong bộ nhớ sang Redis và kiểm chứng qua hai nút

Trong một ứng dụng Spring chạy trên một máy chủ, session trong bộ nhớ có thể đáp ứng nhu cầu ban đầu. Khi triển khai nhiều instance, mỗi instance có bộ nhớ riêng. Nếu request đầu tạo session ở node A nhưng request sau đến node B, B không biết trạng thái mà A đã lưu. Sticky session có thể giảm hiện tượng này, nhưng không chia sẻ dữ liệu và không bảo vệ tốt khi node restart.

Spring Session tách API session khỏi nơi lưu trữ. Khi chuyển sang Redis, nhiều instance có thể đọc và ghi cùng repository. Bài thực hành này chuyển cấu hình in-memory sang Redis, chạy hai node từ cùng một ứng dụng, rồi xác minh một cookie có thể dùng qua lại giữa hai node. Sau đó kiểm tra restart, logout, TTL, lỗi cấu hình và cutover.

## 1. Mục tiêu và kiến trúc đích

- Node A và node B chạy cùng phiên bản ứng dụng.
- Cả hai kết nối cùng Redis deployment và namespace.
- Cả hai dùng cùng cookie name, path, domain, serializer và chính sách session.
- Session tạo ở A được đọc và cập nhật ở B.
- Session vẫn tồn tại khi node tạo session restart, miễn Redis còn dữ liệu hợp lệ.
- Invalidate ở một node có hiệu lực khi request tiếp theo tới node còn lại.
- Không phụ thuộc sticky session.

~~~mermaid
flowchart LR
    C[Browser / HTTP client]
    LB[Load balancer]
    A[Spring node A]
    B[Spring node B]
    R[(Shared Redis)]
    C --> LB
    LB --> A
    LB --> B
    A <--> R
    B <--> R
~~~

Cookie chỉ mang session ID. Trạng thái session nằm trong Redis. Node A và B không cần chia sẻ heap; chúng cần thống nhất cách diễn giải ID và dữ liệu đã serialize.

## 2. Phân biệt session trong bộ nhớ và Spring Session Redis

| Kiểu lưu | Nơi giữ trạng thái | Hành vi khi request sang node khác |
|---|---|---|
| HttpSession mặc định của Servlet container | Bộ nhớ của container/node | Node khác thường không tìm thấy session |
| Spring Session với MapSessionRepository | Map trong bộ nhớ của ứng dụng | Mỗi instance có map riêng nếu không chia sẻ implementation |
| Spring Session với Redis | Redis dùng chung | Mọi node có cùng cấu hình có thể tìm session |
| Spring Session với JDBC | Database dùng chung | Mọi node có cùng schema/repository có thể tìm session |

MapSessionRepository hữu ích cho test hoặc ứng dụng đơn giản, nhưng không phải kho phân tán chỉ vì nó triển khai SessionRepository. Một Map trong JVM vẫn thuộc về một tiến trình.

Trong bài này, mục tiêu là ứng dụng Servlet dùng Spring Session Redis. Nếu ứng dụng dùng WebFlux, phải dùng WebSession và reactive Redis repository tương ứng; không áp dụng filter Servlet hoặc HttpSession trực tiếp cho WebFlux.

## 3. Kiểm kê trước khi chuyển đổi

Ghi nhận:

- Spring Boot, Spring Framework, Spring Security và Spring Session version.
- Cách tạo và cấu hình HttpSession hiện tại.
- Cookie name, path, domain, Secure, HttpOnly, SameSite và thời hạn cookie.
- Session timeout và absolute lifetime nếu có.
- Các attribute: tên, kiểu dữ liệu, kích thước gần đúng và mức độ nhạy cảm.
- Object Java tùy chỉnh, entity JPA, proxy hoặc dữ liệu lớn được lưu trong session.
- Code phụ thuộc JSESSIONID, session ID hoặc API riêng của container.
- Security configuration và các secret mà mọi node phải dùng chung.

Tìm các nơi đọc session ID trực tiếp, ghi cookie thủ công hoặc truy vấn session container-specific. Khi dùng Spring Session, repository và filter quản lý vòng đời session; code ứng dụng nên làm việc qua HttpSession.

### 3.1. Kiểm tra attribute có thể serialize

Redis cần lưu dữ liệu đã serialize. Tránh đưa vào session:

- Connection, stream, thread, request/response object.
- Entity graph có proxy lazy hoặc vòng tham chiếu.
- Object không tương thích giữa phiên bản node.
- File hoặc byte array lớn.
- Cache hoặc danh sách nghiệp vụ không giới hạn.

Ưu tiên lưu ID tham chiếu như cartId, orderId hoặc workflowId. Giữ payload session nhỏ để giảm RAM, mạng và chi phí serialize mỗi request.

## 4. Chuẩn bị Redis dùng riêng cho thực hành

Chạy Redis riêng cho môi trường phát triển/test, không dùng Redis production hoặc instance đang chứa dữ liệu của ứng dụng khác:

~~~bash
docker run --name spring-session-practice-redis -p 6379:6379 -d redis:7
~~~

Xác minh Redis sẵn sàng:

~~~bash
docker exec spring-session-practice-redis redis-cli PING
~~~

Kết quả mong đợi là PONG. Nếu môi trường không dùng Docker, có thể dùng Redis cài sẵn hoặc dịch vụ Redis test được cấp riêng. Ghi lại host, port, credentials, TLS và database/namespace được phép dùng.

Không mở Redis test ra Internet. Trong môi trường chia sẻ, dùng authentication/ACL và network policy; không đặt mật khẩu thật trong file cấu hình được commit.

## 5. Thêm dependency Spring Session Redis

Với Spring Boot, dùng dependency management/BOM của dự án để giữ phiên bản tương thích. Các dependency thường cần:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
~~~

Ứng dụng Servlet cũng cần web starter tương ứng. Không tự chỉ định phiên bản Spring Session khác với dòng Spring Boot đang quản lý nếu chưa kiểm tra compatibility matrix. Nếu dự án dùng starter tích hợp Spring Session Redis riêng của phiên bản Boot đang chạy, theo đúng cách dependency management của dự án; tránh thêm đồng thời dependency gây cấu hình trùng.

Sau khi thêm dependency, xác nhận ứng dụng khởi động được và có RedisConnectionFactory. Chỉ có Redis client dependency chưa đủ để chứng minh request đang dùng Spring Session Redis; cần bật cấu hình Spring Session hoặc auto-configuration đúng cách.

## 6. Bật Spring Session Redis cho Servlet

Có hai hướng phổ biến: để Spring Boot auto-configuration tạo repository, hoặc cấu hình tường minh bằng annotation. Chọn một hướng làm nguồn cấu hình chính; không bật hai cấu hình repository khác nhau cùng lúc.

### 6.1. Ví dụ dùng Spring Boot properties

Trong application.yml:

~~~yaml
server:
  port: 8080
  servlet:
    session:
      cookie:
        name: SESSION
        http-only: true
        secure: false
        same-site: lax
spring:
  session:
    timeout: 30m
    redis:
      namespace: spring:session:practice
      flush-mode: on-save
      save-mode: on-set-attribute
  data:
    redis:
      host: localhost
      port: 6379
~~~

Các thuộc tính có thể thay đổi theo phiên bản Spring Boot. Kiểm tra metadata/configuration properties của đúng phiên bản đang dùng, đặc biệt tên prefix cho Redis và cookie. Với ứng dụng có reverse proxy HTTPS, đặt Secure=true và cấu hình forwarded headers đúng để ứng dụng nhận biết request gốc dùng HTTPS.

Namespace phải giống nhau trên cả hai node. Nếu dùng Redis cho nhiều ứng dụng, đặt namespace riêng để tránh key collision. Không dùng namespace mặc định chung cho các hệ thống không liên quan.

### 6.2. Ví dụ cấu hình annotation

Nếu ứng dụng quản lý Spring Session bằng Java configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FlushMode;
import org.springframework.session.SaveMode;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    redisNamespace = "spring:session:practice",
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
public class RedisSessionConfiguration {
}
~~~

Ví dụ dành cho Servlet. Nếu dùng cấu hình annotation này, không cấu hình một repository khác song song với auto-configuration. Đảm bảo RedisConnectionFactory đã được tạo.

ON_SAVE gom các thay đổi và flush khi repository lưu session; ON_SET_ATTRIBUTE phù hợp khi ứng dụng gọi setAttribute/removeAttribute rõ ràng. Nếu code sửa object mutable tại chỗ, hãy kiểm thử SaveMode; thay đổi bên trong collection có thể không được phát hiện theo cách mong muốn. Không đổi sang ALWAYS một cách máy móc vì có thể làm tăng serialization và write load.

## 7. Cookie phải giống nhau trên hai node

Cookie là cách trình duyệt mang session ID qua các request. Để hai node dùng cùng phiên, cần thống nhất:

- Cookie name, ví dụ SESSION.
- Path và Domain.
- Secure, HttpOnly và SameSite.
- Cách encode/decode session ID.
- Chính sách cookie hết hạn.

Cookie không gắn với port. Khi hai node chạy trên localhost ở port 8081 và 8082, HTTP client có thể gửi cùng cookie đến cả hai port nếu host/path phù hợp. Khi triển khai sau load balancer, trình duyệt thường chỉ thấy một hostname chung.

Không để node A phát cookie tên SESSION còn node B chờ JSESSIONID. Không cấu hình domain khác nhau giữa node. Nếu chạy HTTPS phía proxy, kiểm tra Set-Cookie có Secure đúng như mong muốn.

Session ID là bearer credential. Không log Cookie hoặc Set-Cookie, không đưa ID vào URL, metric label, exception message hoặc ảnh chụp màn hình hỗ trợ.

## 8. Chuẩn bị hai node từ cùng một artifact

Build một artifact duy nhất, ví dụ app.jar, rồi chạy hai tiến trình với cấu hình giống nhau. Chỉ khác node identifier và port:

~~~bash
java -jar app.jar --server.port=8081 --spring.data.redis.host=localhost --spring.data.redis.port=6379 --spring.session.redis.namespace=spring:session:practice
~~~

~~~bash
java -jar app.jar --server.port=8082 --spring.data.redis.host=localhost --spring.data.redis.port=6379 --spring.session.redis.namespace=spring:session:practice
~~~

Nếu cấu hình bằng annotation, namespace và timeout nằm trong Java configuration; không kỳ vọng command-line property ghi đè thuộc tính annotation. Đặt cấu hình node/port qua biến môi trường hoặc property riêng. Cả hai node phải dùng cùng Redis, namespace, cookie policy, serializer và session timeout.

Không dùng hai namespace khác nhau để tách node. Làm vậy sẽ tạo hai kho session riêng và bài kiểm chứng chéo node thất bại đúng như thiết kế.

## 9. Tạo endpoint thực hành để quan sát session

Trong profile thực hành/test, tạo controller đơn giản để tăng bộ đếm session, đọc trạng thái và invalidate. Không đưa endpoint này vào production nếu không có lý do nghiệp vụ và bảo vệ phù hợp.

~~~java
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionPracticeController {

    @GetMapping("/practice/session")
    Map<String, Object> read(HttpSession session) {
        Integer count = (Integer) session.getAttribute("count");
        return Map.of("count", count == null ? 0 : count);
    }

    @PostMapping("/practice/session/increment")
    Map<String, Integer> increment(HttpSession session) {
        Integer previous = (Integer) session.getAttribute("count");
        int next = previous == null ? 1 : previous + 1;
        session.setAttribute("count", next);
        return Map.of("count", next);
    }

    @PostMapping("/practice/session/logout")
    ResponseEntity<Void> logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

Ví dụ dùng Jakarta Servlet API cho Spring Boot 3+/Spring Framework 6+. Với dòng Spring cũ dùng javax.servlet thay cho jakarta.servlet. Endpoint increment dùng POST vì nó thay đổi trạng thái. Nếu Spring Security bật CSRF, test HTTP phải gửi CSRF token hợp lệ; không tắt CSRF trong production chỉ để đơn giản hóa bài thực hành.

Bộ đếm này chỉ để kiểm chứng tuần tự giữa hai node. Hai request increment đồng thời có thể đọc cùng giá trị và ghi đè nhau. Không dùng session attribute làm bộ đếm nghiệp vụ hoặc rate limit cần tính nguyên tử.

## 10. Kiểm chứng từng bước qua hai node

Dùng cùng một cookie jar cho cả hai node. Ví dụ với curl:

~~~bash
# Tạo hoặc cập nhật session ở node A
curl -i -c session-cookie.txt -b session-cookie.txt -X POST http://localhost:8081/practice/session/increment

# Đọc cùng session ở node B
curl -i -c session-cookie.txt -b session-cookie.txt http://localhost:8082/practice/session
~~~

Kết quả mong đợi: node B đọc được count: 1. Tiếp tục:

~~~bash
# Tăng bộ đếm tại node B
curl -i -c session-cookie.txt -b session-cookie.txt -X POST http://localhost:8082/practice/session/increment

# Đọc lại ở node A
curl -i -c session-cookie.txt -b session-cookie.txt http://localhost:8081/practice/session
~~~

Kết quả mong đợi: node A đọc được count: 2. Cookie jar giữ cookie từ response và gửi lại trong request. Nếu ứng dụng bật CSRF, lấy token theo cấu hình Spring Security và gửi token đó trong POST; các lệnh rút gọn trên giả định endpoint thực hành không yêu cầu token hoặc test client đã bổ sung token hợp lệ.

Để kiểm tra cookie được phát, xem header Set-Cookie nhưng không sao chép giá trị session ID vào tài liệu hoặc log. Có thể xác minh tên cookie và thuộc tính Secure/HttpOnly/SameSite mà không tiết lộ giá trị.

### 10.1. Không dùng sticky session trong phép thử

Gọi trực tiếp port 8081 và 8082 để chắc chắn request đi qua hai tiến trình khác nhau. Nếu chỉ gọi một URL load balancer có sticky routing, mọi request có thể luôn về node A và test không chứng minh được shared repository.

## 11. Kiểm chứng node restart

Sau khi tạo session ở node A và đọc được ở B:

1. Giữ nguyên cookie jar.
2. Dừng node A.
3. Gửi request với cookie cũ tới node B.
4. Xác nhận B vẫn đọc được count đã lưu.
5. Khởi động lại node A với cùng cấu hình Redis.
6. Gửi request tới A và xác nhận session vẫn được khôi phục.

Nếu session biến mất sau khi A restart, kiểm tra xem ứng dụng còn dùng session local, namespace có khác, Redis có bị restart/flush, hoặc cookie có bị thay đổi hay không. Với Redis không bật persistence, việc Redis restart có thể làm mất dữ liệu; khả năng sống sót của session phụ thuộc cấu hình persistence/HA của Redis.

## 12. Kiểm chứng logout/invalidate xuyên node

Với cookie jar đã tạo:

~~~bash
# Invalidate session qua node B
curl -i -c session-cookie.txt -b session-cookie.txt -X POST http://localhost:8082/practice/session/logout

# Gửi lại cookie jar tới node A
curl -i -c session-cookie.txt -b session-cookie.txt http://localhost:8081/practice/session
~~~

Kết quả mong đợi: session cũ không còn được khôi phục; request tới A tạo session mới hoặc trả trạng thái theo chính sách ứng dụng. Cookie jar có thể được cập nhật nếu response logout phát Set-Cookie xóa cookie. Để kiểm tra ID cũ bị từ chối, có thể lưu cookie cũ riêng trong biến test trước logout và gửi lại; không in giá trị đó ra output.

Logout qua Spring Security có thể xóa SecurityContext, invalidate session và xóa cookie theo cấu hình. Test endpoint trên chỉ kiểm tra Servlet session invalidation; cần một test riêng qua logout flow thực nếu muốn chứng minh toàn bộ Spring Security integration.

## 13. Kiểm chứng TTL và idle timeout

Cấu hình timeout 30 phút trong ví dụ là max inactive interval. Với test, nên dùng timeout ngắn hơn trong profile riêng, ví dụ 30 giây:

1. Tạo session qua node A.
2. Gửi request qua B trước khi hết hạn và xác nhận state còn.
3. Chờ vượt idle timeout mà không gửi request.
4. Gửi lại cookie cũ tới A hoặc B.
5. Xác nhận session cũ không còn được khôi phục.

Phân biệt hết hạn logic với xóa vật lý. Repository có thể từ chối session đã hết hạn trước khi Redis key hoặc index được cleanup hoàn toàn. Không yêu cầu cleanup xảy ra chính xác cùng thời điểm với timeout.

Không dùng sleep dài trong test suite nếu có thể dùng polling có deadline. Với TTL Redis thực, virtual time của Reactor không điều khiển đồng hồ Redis. Tách test logic timeout khỏi test cleanup vật lý.

## 14. Xác nhận Redis thực sự đang giữ session

Có thể dùng Redis CLI trong môi trường thực hành để kiểm tra namespace và số key, nhưng tránh in session ID hoặc payload. Ví dụ:

~~~powershell
redis-cli --scan --pattern 'spring:session:practice:*' | Measure-Object
~~~

Lệnh trên minh họa cách đếm kết quả trong PowerShell khi redis-cli nằm trong PATH. Với bash, có thể pipe sang wc -l. Không dùng KEYS * trên Redis production; lệnh này có thể chặn server khi keyspace lớn. SCAN vẫn cần giới hạn phạm vi, sampling hoặc chạy ngoài đường request.

Không dùng GET/HGETALL để dump toàn bộ session vào terminal. Payload có thể chứa SecurityContext, thông tin người dùng hoặc token. Nếu cần xác minh dữ liệu, dùng test repository API hoặc thống kê tổng hợp đã làm sạch.

## 15. Chuyển đổi từ session local: cutover và người dùng hiện tại

Việc bật Spring Session Redis không tự động chuyển các session đang nằm trong bộ nhớ của Servlet container hoặc MapSessionRepository sang Redis. Hai repository không tự chia sẻ dữ liệu.

Một cutover đơn giản và an toàn thường chấp nhận người dùng đăng nhập lại:

1. Triển khai phiên bản ứng dụng có Spring Session Redis.
2. Dùng cookie name mới hoặc chủ động hết hạn cookie cũ.
3. Session cũ không được tìm thấy trong Redis nên không được khôi phục.
4. Người dùng xác thực lại và nhận session ID mới.
5. Tất cả node mới dùng Redis repository chung.

Nếu giữ nguyên cookie name, session ID cũ có thể được gửi tới Spring Session nhưng không tồn tại trong Redis; ứng dụng thường tạo session mới theo chính sách. Tuy vậy, đổi cookie name hoặc hết hạn cookie cũ làm ranh giới cutover rõ ràng hơn, đặc biệt nếu có nhiều ứng dụng cùng domain.

Nếu nghiệp vụ bắt buộc giữ phiên đăng nhập, cần thiết kế một cơ chế migration riêng: đọc session cũ từ nơi có thẩm quyền, kiểm tra danh tính, chuyển dữ liệu được cho phép và phát ID mới. Không thể chỉ copy một session ID local sang Redis nếu dữ liệu session không được chuyển. Cơ chế bridge phải có thời hạn, chống replay và không giữ lại credential cũ ngoài chính sách.

## 16. Đồng bộ cấu hình bảo mật giữa các node

Hai node dùng chung session store nhưng vẫn cần tương thích về:

- Spring Boot/Spring Session/Spring Security versions.
- Serialization format và class definitions.
- SecurityContext và authentication principal representation.
- Cookie serializer/resolver.
- Session timeout và policy rotation.
- Các secret dùng để ký hoặc mã hóa dữ liệu ứng dụng nếu session attributes chứa dữ liệu phụ thuộc secret đó.
- CSRF/session fixation/logout configuration.

Không nên triển khai node A và B với hai phiên bản class không tương thích trong khi cùng đọc/ghi object session phức tạp. Rolling deployment cần bảo đảm phiên bản mới đọc được session do phiên bản cũ tạo, và ngược lại trong thời gian hai phiên bản cùng chạy nếu node cũ vẫn nhận traffic.

Nếu serializer là Java serialization, thay đổi class có thể làm session cũ không deserialize được. Dùng DTO ổn định, version hóa dữ liệu và có kế hoạch hết hạn/di trú session khi thay schema.

## 17. Kiểm thử tự động bằng hai application instance

Một integration test đầy đủ có thể khởi động Redis test container và hai application context/instance:

1. Redis container được tạo một lần cho test class hoặc suite.
2. Node A và B dùng cùng host/port, namespace test và cookie policy.
3. Mỗi node có server port riêng.
4. Web client gửi request tới A, lấy Set-Cookie.
5. Cùng cookie được gửi tới B.
6. B cập nhật session; A đọc lại kết quả.
7. Test invalidate qua B và xác nhận A không còn truy cập session cũ.
8. Dọn namespace test khi kết thúc.

Nếu dùng hai SpringApplication context trong cùng JVM, phải đặt tên bean/context riêng và đóng cả hai sau test. Nếu dùng hai tiến trình, dùng cùng artifact và cùng biến môi trường; ghi log theo node ID nhưng không ghi session ID.

Một test đơn node với Redis thật chỉ chứng minh repository kết nối được Redis. Nó chưa chứng minh hai node có cùng namespace/cookie/serializer. Bài test chéo node là điều kiện bắt buộc cho mục tiêu thực hành này.

## 18. Kiểm thử lỗi cấu hình và sự cố

| Thử nghiệm | Cách tạo tình huống | Kết quả mong đợi |
|---|---|---|
| Node dùng namespace khác | Đổi namespace ở B | B không tìm thấy session A; test phải phát hiện mismatch |
| Node dùng Redis khác | Đổi host hoặc database ở B | Session không chia sẻ; cấu hình phải được kiểm tra |
| Cookie name khác | Đổi tên cookie ở B | B không nhận cookie của A |
| Serializer không tương thích | Dùng class/config khác có kiểm soát | Lỗi đọc được phát hiện, không cấp quyền mặc định |
| Redis unavailable | Dừng Redis test | Request cần session fail theo chính sách; không xác thực giả |
| Node A restart | Dừng và khởi động lại A | B vẫn đọc được session nếu Redis còn dữ liệu |
| Redis restart không persistence | Restart Redis test | Có thể mất session; test chứng minh phụ thuộc persistence |
| Session hết hạn | Chờ quá idle timeout | Cookie cũ không khôi phục session hết hạn |
| Logout tại node khác | Invalidate qua B | A không khôi phục session cũ |

Không chạy các thử nghiệm phá hoại trên Redis dùng chung. Mỗi tình huống phải dùng instance, namespace và dữ liệu test riêng.

## 19. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Node A đọc được, B tạo session mới | Namespace hoặc Redis endpoint khác | So sánh cấu hình runtime của hai node |
| Mỗi node có bộ đếm riêng | Ứng dụng vẫn dùng session local/in-memory | Xác minh Spring Session filter/repository thực sự được kích hoạt |
| Cookie liên tục đổi | Cookie policy, proxy hoặc resolver không thống nhất | Đồng bộ cookie name/path/domain và forwarded headers |
| Node B lỗi deserialize | Class hoặc serializer không tương thích | Đồng bộ artifact và serialization schema |
| Session mất sau restart node | Dữ liệu chỉ nằm trong heap hoặc Redis bị mất dữ liệu | Xác minh repository và Redis persistence/HA |
| Logout ở B nhưng A vẫn đọc session | Hai node không dùng cùng store/namespace hoặc request cũ ghi lại | Kiểm tra config, stale save và cơ chế invalidate |
| Redis RAM tăng nhanh | Payload lớn, TTL dài hoặc nhiều session | Giảm payload, đặt timeout và theo dõi memory |
| Redis ghi lỗi khi đầy bộ nhớ | maxmemory policy hoặc capacity không phù hợp | Tăng headroom, cảnh báo và xử lý lỗi ghi |
| POST test trả 403 | CSRF token thiếu hoặc security chain chặn | Gửi CSRF token hợp lệ và xác thực theo cấu hình |
| Test pass nhưng production fail | Chỉ test mock/local hoặc sticky routing | Test hai instance và Redis thật, bỏ sticky routing |

## 20. Checklist trước khi triển khai

- [ ] Xác nhận ứng dụng đang dùng Servlet HttpSession hay WebFlux WebSession.
- [ ] Chọn đúng Spring Session Redis module và version tương thích.
- [ ] Chỉ có một cấu hình repository rõ ràng.
- [ ] Redis host, credentials, TLS và namespace giống nhau giữa các node.
- [ ] Cookie name/path/domain/Secure/HttpOnly/SameSite tương thích.
- [ ] Session timeout và serializer tương thích.
- [ ] Attribute session nhỏ, serializable và không chứa resource đang mở.
- [ ] Cả hai node chạy cùng artifact hoặc phiên bản tương thích đã được kiểm chứng.
- [ ] Tạo session ở A, đọc và cập nhật ở B, đọc lại ở A.
- [ ] Restart A và xác minh B vẫn đọc được session.
- [ ] Invalidate ở B và xác minh A từ chối session cũ.
- [ ] Kiểm thử TTL, Redis unavailable và serialization failure.
- [ ] Không phụ thuộc sticky session cho trạng thái.
- [ ] Không log cookie, session ID hoặc payload nhạy cảm.
- [ ] Có kế hoạch cutover cho session local và người dùng cần đăng nhập lại.

## 21. Kết quả cần ghi nhận

Sau khi hoàn thành, lưu kết quả kiểm thử ở dạng không chứa bí mật:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Redis PING | PONG |
| Node A tạo session | Thành công |
| Node B đọc session A | Đọc được cùng state |
| Node B cập nhật session | Thành công |
| Node A đọc lại | Nhận state mới |
| Node A restart | Session còn nếu Redis giữ dữ liệu |
| Logout tại B | Cookie cũ không truy cập state cũ ở A |
| TTL | Session hết hạn theo idle timeout |
| Namespace mismatch test | Phát hiện không chia sẻ |
| Security/cookie | Thuộc tính đúng, không lộ ID |

Không đưa session ID, cookie value, Redis password hoặc payload vào báo cáo. Chỉ ghi phiên bản ứng dụng, namespace test đã làm sạch, node/port, thời điểm và pass/fail.

Chuyển từ session trong bộ nhớ sang Redis là thay đổi về nơi lưu trạng thái và cách vận hành vòng đời phiên. Kết quả chỉ được xác nhận khi cùng một cookie hoạt động qua hai tiến trình độc lập, thay đổi ở node này được node kia đọc thấy, và invalidate/expiration có hiệu lực xuyên node. Cấu hình Redis đúng nhưng chỉ kiểm thử một node chưa chứng minh được mục tiêu chia sẻ session của Spring Session.
