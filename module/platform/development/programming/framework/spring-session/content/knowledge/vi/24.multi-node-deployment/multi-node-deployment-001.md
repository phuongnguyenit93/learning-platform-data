# Chia sẻ kho phiên giữa các bản chạy ứng dụng

Khi một ứng dụng Spring được triển khai thành nhiều instance phía sau load balancer, mỗi request có thể được chuyển đến một instance khác nhau. Nếu session chỉ nằm trong bộ nhớ của servlet container, instance nhận request tiếp theo có thể không tìm thấy trạng thái đăng nhập hoặc dữ liệu phiên đã tạo ở instance trước. Spring Session giải quyết vấn đề này bằng cách lưu session trong một kho dùng chung như Redis hoặc JDBC để mọi instance cùng đọc và cập nhật.

Mục tiêu là để session có vòng đời độc lập với một tiến trình ứng dụng. Instance A có thể tạo session, instance B có thể đọc session đó, và instance C có thể xử lý request tiếp theo mà vẫn nhận được cùng trạng thái. Điều này giúp scale ngang, rolling deployment và thay thế instance khi có lỗi mà không buộc người dùng đăng nhập lại chỉ vì request chuyển sang máy khác.

## 1. Vì sao nhiều instance cần kho session dùng chung?

Trong triển khai một instance, servlet container thường giữ session trong bộ nhớ của chính tiến trình. Cách này đơn giản nhưng tạo ra sự phụ thuộc vào instance:

- Người dùng đăng nhập qua instance A và session được lưu trong RAM của A.
- Load balancer chuyển request tiếp theo đến instance B.
- B không có session trong bộ nhớ riêng nên không khôi phục được trạng thái đăng nhập.
- Người dùng có thể bị xem như chưa đăng nhập hoặc nhận trạng thái ứng dụng không nhất quán.

Có thể cấu hình sticky session để load balancer cố gắng gửi một người dùng về cùng instance. Tuy nhiên, sticky routing không giải quyết đầy đủ lỗi instance, restart, rolling deployment hoặc nhu cầu truy cập session từ tác vụ chạy ở instance khác.

Với Spring Session, ứng dụng sử dụng SessionRepository thay cho bộ nhớ session cục bộ. Các instance cùng kết nối đến một repository bên ngoài. Session ID vẫn được gửi từ client, thường qua cookie; dữ liệu session được tải từ kho dùng chung.

## 2. Kiến trúc tổng thể

Một triển khai điển hình có load balancer, nhiều instance Spring và một kho session chung:

~~~mermaid
flowchart TD
    C["Browser / API client"] --> LB["Load balancer"]
    LB --> A["Spring instance A"]
    LB --> B["Spring instance B"]
    LB --> D["Spring instance C"]
    A --> F["SessionRepositoryFilter"]
    B --> G["SessionRepositoryFilter"]
    D --> H["SessionRepositoryFilter"]
    F --> R[("Shared SessionRepository<br/>Redis hoặc JDBC")]
    G --> R
    H --> R
    R --> A
    R --> B
    R --> D
~~~

Luồng xử lý:

1. Client gửi cookie hoặc header có session ID đến load balancer.
2. Load balancer chuyển request đến một instance bất kỳ.
3. SessionRepositoryFilter đọc session ID qua HttpSessionIdResolver.
4. Filter dùng SessionRepository để tải session từ kho dùng chung.
5. Controller, service và Spring Security làm việc với HttpSession như thông thường.
6. Khi request kết thúc, filter lưu các thay đổi cần thiết vào repository và cập nhật định danh ở response nếu có thay đổi.
7. Request sau có thể đến instance khác và tải cùng session từ kho chung.

Spring Session giữ API HttpSession quen thuộc cho ứng dụng Servlet. Phần lưu trữ được thay đổi phía dưới; controller không cần tự gọi Redis hoặc SQL để quản lý từng thuộc tính session.

## 3. Các điều kiện để mọi instance dùng cùng một session

Chỉ cấu hình cùng loại backend là chưa đủ. Tất cả instance phải thống nhất những thông tin quyết định cách tìm, đọc, giải mã và cập nhật session:

- Cùng Redis deployment hoặc cùng database/schema.
- Cùng namespace hoặc tên bảng session.
- Cùng cookie name, Path, Domain và chính sách SameSite nếu dùng cookie.
- Cùng header name nếu dùng HeaderHttpSessionIdResolver.
- Cùng timeout và cách áp dụng expiration.
- Cùng serializer hoặc định dạng dữ liệu tương thích.
- Cùng cấu hình principal index nếu cần tra cứu session theo người dùng.
- Cùng cách xử lý session fixation, logout và security context.
- Cùng phiên bản Spring Session tương thích trong giai đoạn triển khai.

Nếu một instance dùng namespace Redis khác, instance đó sẽ không tìm thấy session dù kết nối đến cùng Redis server. Nếu cookie name hoặc Domain khác nhau, client có thể gửi định danh không giống nhau đến các instance. Nếu serializer khác nhau, instance này có thể ghi dữ liệu mà instance kia không đọc được.

Hãy quản lý các giá trị này bằng cấu hình dùng chung, biến môi trường hoặc hệ thống quản lý cấu hình. Tránh để mỗi replica có file cấu hình độc lập được chỉnh thủ công.

## 4. Cấu hình Spring Session với Redis

Redis thường phù hợp khi cần truy cập session nhanh và có thể vận hành một dịch vụ dữ liệu phân tán riêng. Ứng dụng cần dependency Spring Session Data Redis và Redis client tương thích với phiên bản Spring Boot/Spring Session.

Ví dụ cấu hình:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 30m
    redis:
      namespace: shop:session
      flush-mode: on-save
      save-mode: on-set-attribute
  data:
    redis:
      host: redis.internal
      port: 6379
      ssl:
        enabled: true
~~~

Các tên property và cấu trúc TLS có thể khác theo phiên bản Spring Boot; hãy dùng cấu hình được tài liệu của phiên bản dự án hỗ trợ. Không đưa password hoặc secret vào file cấu hình được commit. Lấy thông tin xác thực từ secret manager hoặc biến môi trường được bảo vệ.

Trong nhiều ứng dụng Spring Boot, auto-configuration tạo Redis-backed SessionRepository khi dependency và cấu hình phù hợp có mặt. Với cấu hình thủ công, Spring Session cung cấp annotation như EnableRedisHttpSession. Chọn một cách cấu hình rõ ràng và tránh đồng thời tạo nhiều repository hoặc filter cạnh tranh.

Namespace tách dữ liệu session của ứng dụng khỏi ứng dụng khác dùng chung Redis. Mọi instance của cùng ứng dụng phải dùng cùng namespace. Các ứng dụng khác nên dùng namespace riêng để tránh xung đột key, cấu hình expiration và kiểu dữ liệu.

### Redis deployment và HA

Kho Redis cần được triển khai với độ sẵn sàng phù hợp. Tùy yêu cầu, hệ thống có thể dùng managed Redis, Sentinel hoặc Redis Cluster. Cần kiểm tra Spring Data Redis client và Spring Session version có tương thích với topology đó hay không.

Redis replica hoặc cluster không tự động bảo đảm mọi loại lỗi đều không mất dữ liệu. Hãy hiểu chính sách replication, failover, persistence, backup và consistency của dịch vụ đang dùng. Nếu Redis mất dữ liệu session, người dùng có thể phải đăng nhập lại; không có cấu hình sticky session nào khôi phục được dữ liệu đã mất khỏi kho chung.

## 5. Cấu hình Spring Session với JDBC

JDBC phù hợp khi tổ chức muốn lưu session trong database quan hệ hiện có hoặc cần quản lý schema và backup theo quy trình database. Ứng dụng cần dependency Spring Session JDBC và một DataSource được cấu hình.

Ví dụ:

~~~yaml
spring:
  session:
    store-type: jdbc
    timeout: 30m
    jdbc:
      initialize-schema: never
      table-name: SPRING_SESSION
  datasource:
    url: jdbc:postgresql://db.internal:5432/app
    username: app_session
    password: <secret-from-environment>
~~~

Trong production, nên quản lý schema bằng Flyway, Liquibase hoặc quy trình migration của tổ chức. Dùng schema mẫu phù hợp với phiên bản Spring Session; khi đổi tên bảng, phải cập nhật đầy đủ các bảng và cấu trúc liên quan. Tài khoản runtime chỉ nên có quyền cần thiết để đọc/ghi/xóa session.

Mọi instance phải dùng cùng database, schema và tên bảng. Nếu một node trỏ sang database replica chỉ đọc, database khác hoặc schema riêng, session sẽ không được chia sẻ đúng cách.

JDBC cung cấp transaction và độ bền theo khả năng database, nhưng session read/write vẫn tạo truy vấn. Cần đo connection pool, số lần ghi, thời gian truy vấn, index và tác vụ cleanup trước khi chọn JDBC cho lưu lượng lớn.

## 6. Cookie và định danh session phải nhất quán

Trong mô hình cookie, browser gửi session ID theo domain, path và các thuộc tính cookie. Spring Session thường dùng cookie resolver để đọc/ghi ID. Tất cả instance phục vụ cùng ứng dụng phải hiểu cùng một cookie.

Ví dụ cấu hình cookie dùng chung:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
class SharedSessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
~~~

Ví dụ này giả định ứng dụng được truy cập qua HTTPS và cookie cần dùng trong cùng site. Với frontend cross-site, cần đánh giá SameSite=None cùng Secure, CORS credentials và CSRF protection. Không bật một chính sách cookie khác nhau trên từng instance.

Nếu dùng HeaderHttpSessionIdResolver cho API client, mọi instance cũng phải dùng cùng tên header và cùng quy tắc ghi/xóa định danh. Client phải gửi header trong mọi request cần session và phải xóa ID khi nhận tín hiệu logout/expiration.

Không dùng đồng thời cookie resolver và header resolver theo cách không có quy tắc ưu tiên rõ ràng. Một request đi đến node A có thể được hiểu khác với request đến node B nếu hai node chọn nguồn session ID khác nhau.

## 7. Load balancing và sticky session

Khi session đã được lưu trong repository dùng chung, request có thể được chuyển đến bất kỳ instance tương thích nào. Sticky session không còn là yêu cầu để giữ tính đúng đắn của HttpSession.

Sticky session vẫn có thể được dùng như một tối ưu nhằm giảm số lần đọc repository hoặc giữ một số trạng thái kết nối cục bộ. Tuy nhiên:

- Không được dựa vào sticky routing để thay thế shared repository.
- Khi instance bị restart hoặc mất kết nối, request vẫn phải được xử lý bởi node khác.
- Không lưu trạng thái xác thực quan trọng chỉ trong RAM của một instance.
- Nếu dùng cache session cục bộ, phải hiểu invalidation và consistency giữa các node.

Với load balancer, cần bật hỗ trợ WebSocket nếu ứng dụng có WebSocket endpoint và cấu hình timeout phù hợp. Cũng cần kiểm tra forwarded headers, HTTPS termination và cookie Domain/Path khi ứng dụng chạy sau reverse proxy.

## 8. Vòng đời request và lưu session giữa các node

SessionRepositoryFilter là thành phần kết nối Servlet API với repository. Filter cần được đăng ký đúng thứ tự trước các filter bảo mật và filter ứng dụng cần dùng HttpSession. Spring Boot và Spring Session thường quản lý thứ tự đăng ký khi dùng auto-configuration phù hợp.

Trong một request:

1. Filter đọc session ID từ cookie/header.
2. Repository tải session nếu ID hợp lệ và chưa hết hạn.
3. Ứng dụng đọc hoặc cập nhật thuộc tính qua HttpSession.
4. Filter lưu thay đổi theo flush/save mode và hợp đồng của repository.
5. Resolver cập nhật cookie/header nếu session mới được tạo, ID được đổi hoặc session bị invalidate.

Không cần tự gọi Redis hoặc SQL trong controller để lưu mỗi thuộc tính session. Việc ghi thủ công có thể tạo dữ liệu không đồng nhất với repository và bỏ qua cơ chế lifecycle của Spring Session.

Nếu request chỉ đọc session, số lần ghi có thể khác với request cập nhật thuộc tính. FlushMode và SaveMode ảnh hưởng thời điểm và phạm vi ghi; cấu hình cần được thống nhất trên mọi instance.

## 9. Timeout và expiration trong kho dùng chung

Session thường có idle timeout. Khi không được truy cập trong khoảng thời gian đó, session hết hạn và không còn được xem là hợp lệ. Spring Session ghi nhận thời gian truy cập và phối hợp với backend để thực thi expiration.

Với Redis, repository quản lý TTL và các key phụ trợ theo implementation. Với JDBC, repository kiểm tra thời hạn và có thể dọn các bản ghi hết hạn bằng tác vụ cleanup. Không tự đặt TTL ở tầng Redis hoặc job SQL ngắn hơn timeout session của ứng dụng.

Các instance phải dùng timeout thống nhất. Nếu node A đặt timeout 30 phút còn node B đặt 10 phút, việc một request đi qua từng node có thể làm kết quả khó dự đoán. Cấu hình timeout theo môi trường nên được quản lý tập trung.

Phân biệt:

- Idle timeout: thời gian tối đa session không được truy cập.
- Absolute lifetime: tổng thời gian tối đa từ lúc đăng nhập, bất kể có hoạt động hay không.
- Cookie Max-Age/Expires: thời gian browser giữ cookie.
- Backend TTL/cleanup: thời gian dữ liệu được giữ hoặc dọn trong Redis/JDBC.

Nếu cần absolute lifetime, lưu mốc xác thực riêng và kiểm tra ở tầng bảo mật. Không dùng idle timeout làm giới hạn tuyệt đối.

## 10. Cập nhật session đồng thời từ nhiều instance

Khi nhiều request cùng dùng một session, chúng có thể được xử lý đồng thời trên các node khác nhau. Ví dụ hai tab cùng đọc giá trị cart, mỗi tab thêm một sản phẩm rồi ghi lại. Nếu cả hai cùng cập nhật từ một trạng thái cũ, thay đổi của request ghi sau có thể ghi đè thay đổi của request kia.

Shared repository không tự động biến mọi thao tác trên thuộc tính session thành transaction nghiệp vụ nguyên tử. FlushMode và SaveMode quyết định thời điểm/phạm vi lưu, nhưng không thay thế cơ chế khóa hoặc cập nhật nguyên tử cho dữ liệu có tranh chấp.

Nguyên tắc:

- Chỉ lưu dữ liệu nhỏ, tạm thời và ít tranh chấp trong session.
- Không dùng session làm bộ đếm tiền, số lượng tồn kho hoặc trạng thái đơn hàng cần tính đúng khi cập nhật đồng thời.
- Dữ liệu nghiệp vụ quan trọng nên nằm trong database/service có transaction hoặc optimistic locking.
- Với object mutable trong session, cập nhật rõ ràng và đặt lại attribute khi SaveMode yêu cầu.
- Kiểm thử hai request đồng thời trên hai instance để phát hiện lost update.

Nếu cần giới hạn số session cho một principal, tra cứu index rồi tạo session mới có thể phát sinh race khi hai lần đăng nhập cùng lúc. Cần cơ chế điều phối hoặc kiểm tra lại sau khi tạo; không giả định một lần đọc index rồi ghi session là thao tác nguyên tử.

## 11. Session fixation, đăng nhập và logout trên nhiều node

Sau khi đăng nhập, Spring Security có thể đổi session ID theo chiến lược chống session fixation. Session ID mới phải được lưu và dùng chung qua repository để request tiếp theo ở node khác vẫn hợp lệ.

Logout qua Spring Security hoặc HttpSession.invalidate() phải xóa session ở kho chung. Khi một node thu hồi session, request tiếp theo đến node khác phải bị từ chối vì repository không còn phiên hợp lệ.

Đối với logout mọi thiết bị, cần tra cứu session theo principal và thu hồi từng phiên bằng repository API. Nếu cần ngăn cả phiên mới được tạo đồng thời, có thể dùng authentication version/session generation hoặc trạng thái thu hồi ở cấp tài khoản.

Không chỉ xóa cookie ở browser. Cookie bị xóa không làm session phía server biến mất. Ngược lại, xóa session trong repository không thể xóa ngay cookie đang nằm trên thiết bị khác; thiết bị đó cần nhận response hoặc phát hiện ID cũ không còn hợp lệ ở request tiếp theo.

## 12. Rolling deployment và tương thích dữ liệu

Trong rolling deployment, phiên bản ứng dụng cũ và mới có thể cùng truy cập repository trong một khoảng thời gian. Vì vậy, session được ghi bởi phiên bản này có thể được đọc bởi phiên bản kia.

Rủi ro thường gặp:

- Class hoặc DTO lưu trong session đổi package, tên hoặc cấu trúc.
- Serializer mới không đọc được dữ liệu đã ghi theo định dạng cũ.
- Enum hoặc kiểu thuộc tính thay đổi.
- Một node dùng SaveMode/FlushMode khác node còn lại.
- Cookie name, namespace hoặc principal resolver thay đổi giữa các bản phát hành.

Hãy lưu DTO nhỏ và ổn định, tránh lưu trực tiếp entity ORM hoặc object graph phụ thuộc nhiều class nội bộ. Khi cần thay đổi định dạng session, thiết kế tương thích ngược trong giai đoạn rollout, chờ session cũ hết hạn hoặc dùng migration/namespace mới theo kế hoạch.

Trước khi triển khai phiên bản mới, kiểm thử khả năng đọc dữ liệu do phiên bản cũ ghi. Nếu cần rolling back, kiểm tra chiều ngược lại: phiên bản cũ có đọc được dữ liệu mà phiên bản mới đã cập nhật hay không.

## 13. Xử lý lỗi instance và lỗi kho session

Shared session store giúp ứng dụng chịu được lỗi một instance web, nhưng kho session trở thành thành phần quan trọng của đường xử lý request.

| Sự cố | Hành vi mong đợi | Việc cần kiểm tra |
| --- | --- | --- |
| Instance A dừng | Load balancer chuyển request sang B; B tải session từ repository | Health check, kết nối B đến store và cookie |
| Instance restart | Session tiếp tục tồn tại nếu store còn khỏe | Không lưu trạng thái phiên quan trọng trong RAM |
| Redis/JDBC tạm mất kết nối | Request cần session có thể lỗi hoặc không xác thực được | Timeout, retry có giới hạn, circuit breaker và cảnh báo |
| Redis failover | Client kết nối lại endpoint hợp lệ; có thể có gián đoạn ngắn | Topology, reconnect, replication và durability |
| Database quá tải | Đọc/ghi session chậm hoặc timeout | Connection pool, query latency và tải cleanup |
| Một node cấu hình sai namespace | Node đó không tìm thấy session của các node khác | So sánh cấu hình runtime giữa replicas |

Với chức năng xác thực, không nên fail-open bằng cách coi lỗi repository là một session mới vô danh rồi tiếp tục cho phép thao tác được bảo vệ. Khi không thể xác minh session, ứng dụng nên từ chối request được bảo vệ hoặc trả lỗi có kiểm soát.

Không retry vô hạn các thao tác ghi session. Retry cần có giới hạn và phải hiểu khả năng lặp lại an toàn của thao tác. Theo dõi lỗi repository để phân biệt session không tồn tại với backend không truy cập được.

## 14. Bảo mật kho session dùng chung

Kho session chứa trạng thái xác thực và có thể chứa dữ liệu cá nhân. Mọi node có quyền truy cập repository đều có khả năng đọc hoặc sửa trạng thái phiên. Cần bảo vệ backend và đường truyền:

- Dùng TLS giữa ứng dụng và Redis/database khi hạ tầng hỗ trợ.
- Dùng authentication và ACL tối thiểu cho từng ứng dụng.
- Đặt Redis/database trong mạng riêng; không mở trực tiếp ra Internet.
- Tách namespace hoặc schema giữa các ứng dụng.
- Không ghi cookie, session ID hoặc toàn bộ session attributes vào log.
- Dùng cookie HttpOnly, Secure và SameSite phù hợp.
- Duy trì CSRF protection nếu browser xác thực bằng cookie.
- Hạn chế quyền truy cập kho session từ các công cụ quản trị và môi trường phát triển.
- Bảo vệ backup, snapshot và dump vì chúng có thể chứa dữ liệu session.

Không dùng namespace như một ranh giới bảo mật duy nhất. ACL và quyền database phải ngăn ứng dụng không liên quan đọc hoặc ghi dữ liệu session của ứng dụng khác.

## 15. Giám sát vận hành

Theo dõi cả ứng dụng và kho session:

- Số session đang hoạt động và tốc độ tạo/xóa session.
- Tỷ lệ request không tìm thấy session và số lần người dùng bị yêu cầu đăng nhập lại bất thường.
- Độ trễ đọc/ghi repository.
- Redis memory, evictions, connections, replication lag hoặc trạng thái cluster.
- JDBC connection pool, query latency, lock contention và kích thước bảng session.
- Số session hết hạn và thời gian cleanup.
- Lỗi serialization/deserialization.
- Sự khác biệt cấu hình giữa các replica.

Đặt cảnh báo cho repository unavailable, connection pool cạn, Redis memory pressure, replication/failover bất thường và tỷ lệ session miss tăng đột ngột. Không log session ID để điều tra; dùng request correlation ID và principal đã được bảo vệ.

## 16. Kiểm thử chia sẻ session giữa các instance

Kiểm thử quan trọng nhất là chứng minh session tạo ở một node có thể được đọc và cập nhật ở node khác.

| Kịch bản | Thực hiện | Kết quả cần xác nhận |
| --- | --- | --- |
| Đăng nhập ở A, đọc ở B | Gửi request login đến A, giữ cookie rồi gửi request đến B | B nhận đúng principal và thuộc tính session |
| Cập nhật ở B, đọc ở A | B thay đổi một attribute; A đọc ở request sau | Thay đổi được lưu theo repository |
| Logout ở A, request đến B | Invalidate session ở A rồi gửi cookie cũ đến B | B không chấp nhận session cũ |
| Không sticky session | Luân phiên request qua A, B, C | Người dùng giữ trạng thái trong suốt chuỗi request |
| Instance crash | Dừng node đang xử lý sau khi session đã lưu | Node còn lại tiếp tục đọc session |
| Backend outage | Ngắt Redis/database trong test | Request bảo vệ được xử lý fail-closed và có lỗi quan sát được |
| Timeout | Chờ quá idle timeout | Session hết hạn trên mọi instance |
| Concurrent update | Hai node cập nhật cùng session | Phát hiện và xử lý lost update theo thiết kế |
| Rolling deployment | Phiên bản cũ và mới cùng đọc session | Serializer và cấu hình tương thích |
| Cookie/header mismatch | Cố ý cấu hình resolver khác nhau trong test | Test phát hiện node không đọc được định danh |

Nên dùng Testcontainers hoặc môi trường integration có Redis/database thật. Mock SessionRepository chỉ kiểm tra logic ứng dụng, không chứng minh serializer, TTL, failover hoặc chia sẻ dữ liệu hoạt động.

## 17. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Người dùng bị đăng xuất khi request đổi node | Các instance dùng repository hoặc namespace khác nhau | Đồng bộ store, namespace và cấu hình |
| Chỉ một số node đọc được session | Một node dùng sai cookie resolver, serializer hoặc database schema | So sánh cấu hình runtime giữa các replica |
| Session mất khi restart web instance | Ứng dụng vẫn dùng local in-memory session | Xác nhận Spring Session repository và filter đã được kích hoạt |
| Logout ở node A nhưng node B vẫn chấp nhận session | Xóa không đến shared store hoặc node B dùng store khác | Kiểm tra repository endpoint, namespace và cache cục bộ |
| Session hết hạn không đồng nhất | Timeout hoặc TTL khác nhau giữa các node | Quản lý timeout tập trung và kiểm thử backend expiration |
| Thuộc tính bị mất khi hai request chạy song song | Lost update do cả hai ghi từ trạng thái cũ | Đưa dữ liệu tranh chấp vào kho có transaction/locking |
| Lỗi deserialize sau rollout | Các phiên bản không tương thích class/serializer | Giữ định dạng tương thích và triển khai migration |
| Tăng độ trễ sau khi bỏ sticky routing | Tải repository tăng hoặc pool chưa đủ | Đo latency, tối ưu store và connection pool |

Khi chẩn đoán, ghi nhận request đã đến node nào, node đó dùng repository nào, namespace/schema nào và resolver nào. So sánh các giá trị cấu hình đã được bind trong runtime thay vì chỉ nhìn file cấu hình nguồn.

## 18. Checklist triển khai nhiều instance

- [ ] Chọn Redis hoặc JDBC theo yêu cầu độ trễ, durability, vận hành và tải.
- [ ] Dùng dependency Spring Session tương thích với Spring Boot/Spring Security.
- [ ] Bảo đảm mọi instance sử dụng cùng repository, namespace/schema và serializer.
- [ ] Đồng bộ cookie name, Path, Domain, Secure, HttpOnly, SameSite hoặc header resolver.
- [ ] Đặt timeout và expiration nhất quán.
- [ ] Xác nhận SessionRepositoryFilter được đăng ký đúng thứ tự.
- [ ] Không dựa vào sticky session để giữ tính đúng đắn của session.
- [ ] Kiểm tra logout, session fixation và thu hồi session từ xa.
- [ ] Kiểm thử cập nhật đồng thời và tương thích dữ liệu khi rolling deployment.
- [ ] Thiết kế HA, backup, network security và quyền truy cập cho Redis/database.
- [ ] Đặt cảnh báo cho lỗi repository, độ trễ, memory/connection pool và session expiration.
- [ ] Kiểm thử failover của node ứng dụng và backend trước khi đưa vào production.

Chia sẻ kho phiên giúp các instance Spring hoạt động như một nhóm xử lý request có thể thay thế lẫn nhau. Điều kiện cốt lõi là mọi instance cùng đọc và ghi một repository với cấu hình cookie/header, namespace, timeout và serialization tương thích. Khi kết hợp kiểm thử không sticky session, xử lý cập nhật đồng thời, triển khai tương thích dữ liệu và giám sát backend, Spring Session giúp duy trì trạng thái người dùng ổn định trong môi trường scale ngang.
