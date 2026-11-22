# Xử lý kết nối hỏng, Redis khởi động lại và thay đổi máy chủ

Redis thường nằm trên đường xử lý của các chức năng cần phản hồi nhanh: cache, session, bộ đếm, khóa phân tán, hàng đợi hoặc thông tin tạm thời. Trong thực tế, kết nối Redis có thể bị ngắt dù mã Java không thay đổi: server khởi động lại, node bị thay thế, địa chỉ IP đổi, Sentinel bầu primary mới, Redis Cluster chuyển hash slot, thiết bị mạng chặn một kết nối lâu không hoạt động hoặc pool giữ một kết nối đã chết.

Với **Spring Data Redis**, cần phân biệt ba câu hỏi:

1. **Kết nối hiện tại có còn dùng được không?** Driver phải phát hiện lỗi, đóng hoặc tái tạo connection phù hợp.
2. **Đích Redis mới là ở đâu?** Topology và cơ chế khám phá node phải cập nhật đúng máy chủ phục vụ lệnh.
3. **Lệnh vừa gửi có thực sự được thực thi không?** Retry phải tôn trọng tính chất nghiệp vụ, nhất là các lệnh ghi có tác dụng phụ.

Bài học thuộc chủ đề **Kết nối và pool** nên tập trung vào vòng đời kết nối, Lettuce/Jedis, quản lý pool, timeout, reconnect, failover và cách ứng dụng khôi phục hành vi chính xác khi Redis gặp sự cố.

## 1. Kết nối Redis đi qua những lớp nào?

Một ứng dụng Spring Boot thường có đường gọi sau:

~~~text
HTTP request / Scheduled job / Message consumer
                    |
                    v
       Service của ứng dụng
                    |
                    v
 RedisTemplate / StringRedisTemplate
 hoặc ReactiveRedisTemplate
                    |
                    v
        RedisConnectionFactory
          /                  \
 LettuceConnectionFactory   JedisConnectionFactory
          \                  /
           Driver / connection / pool
                    |
               TCP hoặc TLS
                    |
       Standalone / Sentinel / Cluster
~~~

Mỗi lớp chịu trách nhiệm khác nhau:

| Lớp | Vai trò khi có lỗi |
|---|---|
| Service | Quyết định có retry, fallback, báo lỗi hay từ chối thao tác nghiệp vụ |
| Spring Data Redis | Chuyển ngoại lệ driver sang nhóm ngoại lệ truy cập dữ liệu; cung cấp abstraction thao tác Redis |
| Connection factory | Tạo hoặc cung cấp kết nối tương ứng với driver và topology |
| Driver Lettuce/Jedis | Duy trì transport, phát hiện disconnect, reconnect hoặc tạo connection mới |
| Connection pool (nếu dùng) | Cho mượn/trả connection; loại connection hỏng; giới hạn số lượng connection |
| Redis topology | Xác định primary, replica, các node sở hữu hash slot hoặc endpoint dịch vụ |
| Mạng/DNS/TLS | Quyết định endpoint có thể phân giải, xác thực và truy cập hay không |

**Driver tự reconnect không đồng nghĩa với lệnh nghiệp vụ tự thành công.** Nếu Redis mất kết nối trong lúc service đang gửi lệnh, việc driver kết nối lại chỉ giúp các lệnh tiếp theo có cơ hội chạy. Ứng dụng vẫn phải xử lý ngoại lệ và trạng thái chưa biết của lệnh cũ.

## 2. Những dạng lỗi kết nối cần phân biệt

Không phải cứ thấy lỗi Redis là phải retry. Trước khi viết chính sách xử lý, hãy xác định lỗi thuộc nhóm nào.

| Tình huống | Dấu hiệu thường gặp | Ảnh hưởng | Cách tiếp cận |
|---|---|---|---|
| Không kết nối được từ đầu | Connection refused, DNS failure, TLS handshake failure | Chưa thiết lập session mạng | Kiểm tra địa chỉ, port, mạng, TLS, xác thực; retry có giới hạn nếu lỗi tạm thời |
| Socket đang dùng bị đóng | Connection reset, broken pipe, connection closed | Lệnh đang chạy có thể thất bại | Driver reconnect/đổi connection; service xử lý kết quả không chắc chắn |
| Lệnh vượt timeout | Command timeout | Client chưa nhận phản hồi đúng hạn | Kiểm tra latency; phân biệt retry an toàn với tác vụ ghi |
| Redis đang restart | Connection refused rồi kết nối lại được | Có khoảng ngắt kết nối; cache có thể lạnh | Chấp nhận outage ngắn, backoff, không flood server khi vừa lên |
| Primary thay đổi | Lệnh ghi từ chối, client còn trỏ node cũ | Sai đường đến primary | Dùng Sentinel/Cluster discovery hoặc endpoint ổn định |
| Redis Cluster di chuyển slot | `MOVED`, `ASK`, timeout trên node cũ | Cần route đến node mới | Client hiểu Cluster; cập nhật topology, kiểm tra địa chỉ node được công bố |
| Pool trả connection chết | Lỗi ngay sau lúc borrow, tăng lỗi sau khoảng idle | Một số request thất bại theo đợt | Loại connection lỗi, kiểm tra chính sách validation/eviction phù hợp |
| Pool hết connection | Chờ pool, timeout khi mượn connection | Request chậm dù Redis vẫn chạy | Kiểm tra active/idle/waiters, thời gian giữ connection |
| Redis từ chối lệnh do quyền hoặc kiểu dữ liệu | NOAUTH, NOPERM, WRONGTYPE | Thường là lỗi cấu hình hoặc dữ liệu | Sửa cấu hình/quyền/lệnh; retry liên tục không giúp ích |

Thông báo cụ thể phụ thuộc phiên bản driver, bản Redis, TLS và lớp Spring Data Redis. Đừng xây hệ thống chỉ dựa vào chuỗi văn bản ngoại lệ; khi có thể, xử lý theo loại exception và ngữ cảnh thao tác.

### 2.1. Ba thời điểm quan trọng của một lỗi

~~~text
A. Trước khi gửi lệnh:
   Client --X--> Redis
   Có thể biết chắc lệnh chưa được gửi qua kết nối đó.

B. Đã gửi, chưa nhận phản hồi:
   Client ---- lệnh ----> Redis
   Client <--X-- phản hồi
   Không biết chắc server đã áp dụng lệnh hay chưa.

C. Đã nhận phản hồi thành công:
   Client ---- lệnh ----> Redis
   Client <--- kết quả --- Redis
   Client biết server đã trả kết quả cho lệnh.
~~~

Trường hợp **B** thường khó nhất. Ví dụ, ứng dụng gửi `INCR payment:attempts`, Redis tăng bộ đếm nhưng socket rớt trước khi phản hồi đến client. Retry một lần có thể khiến bộ đếm tăng **hai lần**. Việc kết nối lại thành công không giải quyết được sự mơ hồ này.

Với nghiệp vụ có tác động quan trọng, cần thiết kế idempotency hoặc cơ chế hòa giải trạng thái dựa trên nguồn dữ liệu đáng tin cậy. Không coi timeout là bằng chứng Redis chưa xử lý lệnh.

## 3. Điều gì xảy ra khi Redis khởi động lại?

Trong một lần restart, có thể xảy ra chuỗi sự kiện:

~~~text
T0  Ứng dụng đang giữ connection tới Redis
T1  Redis ngừng nhận lệnh / đóng socket
T2  Request đang chạy nhận lỗi hoặc timeout
T3  Driver phát hiện connection không còn hợp lệ
T4  Redis khởi động và bắt đầu nhận kết nối mới
T5  Driver reconnect hoặc pool tạo connection mới
T6  Request mới hoạt động; request thất bại trước đó
    chỉ được thực thi lại nếu service có chính sách phù hợp
~~~

**Không có bảo đảm mọi request đang bay qua mạng sẽ được thực thi lại.** Một số request thất bại là hành vi bình thường trong khoảng restart. Ứng dụng cần giới hạn ảnh hưởng thay vì giả định kết nối luôn tồn tại.

### 3.1. Redis sống lại nhưng dữ liệu có thể khác trước

Kết nối mạng đã phục hồi không đồng nghĩa toàn bộ dữ liệu đã phục hồi đúng như trước khi restart. Trạng thái phụ thuộc vào:

- **Persistence:** Redis có cấu hình RDB, AOF hoặc cả hai không; lần lưu bền vững gần nhất là khi nào?
- **Replication:** node vừa trở lại là primary hay replica, đã đồng bộ đủ dữ liệu chưa?
- **Cache:** nếu Redis được dùng như cache không bắt buộc giữ dữ liệu, dữ liệu bị xóa/evict có thể phải nạp lại từ nguồn chính.
- **TTL:** các khóa có hạn sử dụng vẫn có thể hết hạn trong thời gian Redis dừng.
- **Ứng dụng:** có dùng khóa Redis để đại diện cho trạng thái nghiệp vụ quan trọng hay không?

Ví dụ, sau restart, `GET cache:product:42` trả về null có thể là cache miss hợp lệ. Service nên đọc từ database nguồn chính rồi tái tạo cache theo nhu cầu nếu Redis chỉ đóng vai trò cache. Nhưng nếu Redis là nguồn lưu duy nhất của một trạng thái quan trọng, yêu cầu phục hồi dữ liệu và persistence nghiêm ngặt hơn nhiều.

### 3.2. Tránh “bão reconnect” khi server vừa lên lại

Nếu nhiều instance cùng bị mất kết nối, mọi instance có thể retry liên tục trong cùng một thời điểm. Khi Redis vừa hoạt động trở lại, số kết nối và lượng request dồn vào có thể làm server tiếp tục quá tải.

Biện pháp thường dùng:

1. Đặt **connect timeout** và **command timeout** hữu hạn.
2. Retry có **giới hạn số lần**, **backoff** tăng dần và một khoảng **jitter** ngẫu nhiên.
3. Bảo đảm ngân sách retry của service nằm trong thời hạn request HTTP/job.
4. Có giới hạn số thao tác đồng thời hoặc circuit breaker khi Redis không sẵn sàng kéo dài.
5. Với cache, có fallback về nguồn chính và cân nhắc ngăn cache stampede khi nhiều request cùng cần nạp lại một key.

Retry không nên diễn ra vô hạn chỉ vì Redis là dịch vụ hạ tầng.

## 4. Lettuce: tự nối lại kết nối và giới hạn cần hiểu

**Lettuce** dựa trên Netty và hỗ trợ imperative, asynchronous và reactive. Lettuce có cơ chế **automatic reconnection** cho kết nối bị mất khi được bật; trong cách sử dụng phổ biến, auto-reconnect là hành vi mặc định của driver.

Một chuỗi cơ bản:

~~~text
Spring service --> Lettuce native connection --> Redis
                          |
                    mất transport
                          |
              driver phát hiện mất kết nối
                          |
                 thử kết nối lại
                          |
               kết nối mới được thiết lập
                          |
                 lệnh mới tiếp tục
~~~

Các điểm cần nắm:

- Lettuce có thể chia sẻ một native connection phù hợp giữa nhiều thao tác/luồng. Vì thế, một native connection hỏng có thể ảnh hưởng nhiều request đồng thời trước khi reconnect.
- **Auto-reconnect phục hồi transport**, không bảo đảm mọi command đã gửi được xử lý đúng một lần, cũng không thay thế chính sách retry nghiệp vụ.
- Có sự khác biệt giữa việc client tạm thời xếp hàng lệnh khi mất kết nối và kết quả các lệnh đã gửi trước đó. Cấu hình request queue, timeout và auto-reconnect thay đổi hành vi tùy phiên bản.
- Những hoạt động cần connection độc lập hoặc quản lý trạng thái riêng, chẳng hạn một số tình huống blocking/pipeline/transaction, phải được xem xét tách biệt.
- Trong topology Cluster, reconnect tới **đúng node mới** còn phụ thuộc khả năng khám phá topology, không chỉ việc mở lại TCP tới IP cũ.

### 4.1. LettuceConnectionFactory trong Spring Data Redis

`LettuceConnectionFactory` giúp Spring Data Redis cung cấp connection cho template. Factory có thể quản lý một native connection được chia sẻ cho các thao tác thông thường và có tùy chọn quản lý connection riêng khi cần.

Với `RedisTemplate`, lệnh vẫn là **imperative/blocking** dù driver bên dưới là Lettuce. Với `ReactiveRedisTemplate`, lệnh đi qua reactive connection; việc phục hồi kết nối không đồng nghĩa tự động phát lại toàn bộ subscription và tác vụ nghiệp vụ đã thất bại.

Ví dụ, một publisher Reactor kết thúc bằng `onError` do Redis không kết nối được sẽ không “tự hồi sinh” chỉ vì Redis đã lên lại. Cần quyết định có subscription lại, retry publisher hoặc trả kết quả fallback tại tầng reactive.

### 4.2. Khi nào cần pool với Lettuce?

Pool không phải yêu cầu bắt buộc cho mọi thao tác Lettuce. Một số lý do hợp lý để dùng pool hoặc connection riêng gồm quản lý số kết nối dành cho tác vụ đặc thù, cô lập các luồng công việc và giới hạn tài nguyên.

Nếu bật pool, cần theo dõi connection đang được mượn, idle, thời gian chờ borrow, giới hạn tối đa và xử lý connection hỏng. Không tăng pool size chỉ để che giấu timeout gây ra bởi Redis quá tải hoặc mạng lỗi.

## 5. Jedis: quản lý connection lỗi qua pool

**Jedis** trong Spring Data Redis chủ yếu phục vụ API imperative. Một instance connection Jedis trực tiếp không nên được nhiều luồng gọi lệnh đồng thời khi không có cơ chế bảo vệ phù hợp.

Ứng dụng đa luồng thường sử dụng pooling để mỗi request mượn connection và trả về sau khi thao tác kết thúc:

~~~text
Request A --> borrow --> Jedis connection 1 --> Redis
Request B --> borrow --> Jedis connection 2 --> Redis
Request C --> wait for free connection (nếu pool hết)
                   |
                 return
                   |
              connection pool
~~~

Khi Redis restart:

1. Những connection đang mở có thể bị ngắt.
2. Request dùng chúng nhận ngoại lệ.
3. Connection hỏng cần được loại ra, không phát lại cho request kế tiếp như connection khỏe.
4. Các lần borrow tiếp theo có thể sử dụng connection còn hợp lệ hoặc tạo connection mới tới Redis.
5. Nếu server vẫn đang ngừng hoạt động, cả việc mở connection mới cũng thất bại.

Pool không làm Redis sẵn sàng hơn. Nó chỉ là cơ chế quản lý tài nguyên phía client.

### 5.1. Connection “stale” trong pool

Một connection có thể bị Redis hoặc thiết bị mạng đóng trong lúc nằm idle. Pool chưa phát hiện ngay và trả connection đó cho request mới. Request đầu tiên sau khoảng thời gian rảnh có thể lỗi dù Redis hiện đã hoạt động.

Các chính sách thường được xem xét:

- Kiểm tra connection lúc borrow (**test on borrow**) nếu chi phí kiểm tra chấp nhận được.
- Kiểm tra hoặc loại bỏ các idle connection theo chu kỳ và ngưỡng thời gian.
- Không giữ connection quá lâu khi thiết bị mạng có idle timeout thấp.
- Loại connection đã xác nhận hỏng; tuyệt đối không trả nó về pool như một connection tốt.
- Đặt `max-wait` hữu hạn để pool cạn không làm request chờ vô hạn.

Kiểm tra connection qua một lần `PING` chỉ chứng minh trạng thái ở **thời điểm kiểm tra**. Socket vẫn có thể chết ngay sau đó, vì vậy ứng dụng vẫn cần xử lý lỗi lúc gửi lệnh.

### 5.2. Phân biệt connection timeout và pool wait timeout

| Khái niệm | Ý nghĩa | Ví dụ sự cố |
|---|---|---|
| Connect timeout | Thời gian tối đa để thiết lập kết nối mạng | Redis tắt, firewall drop gói tin |
| Command/read timeout | Thời gian đợi phản hồi lệnh | Redis bị nghẽn, mạng trễ hoặc mất reply |
| Pool max-wait | Thời gian đợi mượn được một connection từ pool | Mọi connection đang được giữ bởi request khác |
| Idle eviction/validation | Chính sách dọn và kiểm tra connection nhàn rỗi | Pool giữ connection chết sau restart |

Cả ba loại timeout đều có thể xuất hiện trong một outage. Nếu chỉ thấy “Redis timeout” mà không biết loại nào, rất dễ tăng sai thông số.

## 6. Cấu hình Spring Boot để giới hạn tác động khi mất kết nối

Ví dụ sau minh họa cấu hình Spring Boot 3.x sử dụng Lettuce với Redis Standalone:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: redis.internal.example
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

`connect-timeout` điều chỉnh thời gian chờ kết nối. `timeout` liên quan tới giới hạn thời gian thao tác Redis trong cấu hình của Spring Boot. Giá trị thực tế phải xuất phát từ mục tiêu độ trễ và đặc điểm mạng/Redis; 2 và 3 giây ở đây chỉ là minh họa.

Nếu endpoint dùng TLS, cần cấu hình SSL phù hợp:

~~~yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
~~~

TLS cần đi kèm endpoint và chứng chỉ tin cậy. Lỗi chứng chỉ hoặc ACL sẽ không biến mất chỉ bằng cách retry nhiều lần.

### 6.1. Ví dụ Jedis với pool

Spring Data Redis có thể sử dụng Jedis thay cho Lettuce khi thêm dependency Jedis và chọn client tương ứng:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      host: redis.internal.example
      port: 6379
      connect-timeout: 2s
      timeout: 3s
      jedis:
        pool:
          max-active: 24
          max-idle: 12
          min-idle: 2
          max-wait: 1500ms
~~~

Cấu hình pool cần thư viện pooling tương ứng có mặt trên classpath và phải phù hợp phiên bản Spring Boot đang dùng. Những con số này là ví dụ, không phải giá trị khuyến nghị cố định.

Với Lettuce, Spring Boot cũng có nhóm cấu hình `spring.data.redis.lettuce.pool` khi sử dụng pooling. Đừng bật pool cho toàn bộ service khi không có nhu cầu cụ thể: một pool nhiều connection cũng đồng nghĩa có nhiều connection có thể bị ảnh hưởng bởi lần restart.

### 6.2. Vì sao một địa chỉ hostname ổn định hữu ích?

Khi Redis thay máy chủ, điều lý tưởng là client kết nối qua endpoint có thể theo dõi node mới:

~~~text
Ứng dụng
   |
   v
redis.service.internal  (DNS / Service / Managed endpoint)
   |
   +----> Redis node cũ  [được thay thế]
   |
   +----> Redis node mới [được đưa vào hoạt động]
~~~

Tuy nhiên, **DNS không phải cơ chế failover thần kỳ**. Driver có thể đang giữ socket tới IP cũ; JVM, resolver, proxy hoặc tầng mạng có thể cache kết quả phân giải tên. Cần kết nối lại và có chiến lược refresh phù hợp để lấy đích mới. Nếu endpoint quản lý qua load balancer/proxy, cần hiểu proxy hỗ trợ giao thức Redis và xử lý chuyển primary như thế nào.

Ứng dụng không nên hard-code địa chỉ IP của một Redis primary tạm thời khi hạ tầng có khả năng thay node.

## 7. Redis khởi động lại trên cùng máy chủ

Đây là tình huống phổ biến nhất khi môi trường đang dùng Standalone hoặc đang kiểm thử cục bộ.

### 7.1. Trước khi restart

- Các connection cũ đang tồn tại và có thể có lệnh chờ phản hồi.
- Các transaction, blocking read, Pub/Sub subscription hoặc consumer có thể đang hoạt động.
- Redis có thể lưu dữ liệu theo cấu hình persistence hoặc chỉ giữ cache.

### 7.2. Trong lúc restart

- Driver báo mất kết nối hoặc timeout.
- Request HTTP phụ thuộc Redis có thể thất bại.
- Nếu dùng cache tùy chọn, service có thể đọc từ database thay thế.
- Nếu Redis là thành phần bắt buộc cho tính đúng đắn, service nên trả lỗi có kiểm soát thay vì giả lập kết quả thành công.

### 7.3. Sau khi restart

- Driver/client phải tạo lại kết nối, hoặc pool phải cung cấp connection mới.
- Redis có thể đang tải dữ liệu khi startup; mở được TCP chưa chắc đã bảo đảm thao tác mong muốn đã sẵn sàng.
- Các khóa cache không còn tồn tại có thể được nạp lại khi cần.
- Những luồng nghiệp vụ đã thất bại phải được retry hoặc phục hồi theo chính sách riêng.

Nếu ứng dụng đăng ký Pub/Sub, không nên giả định các message phát trong lúc subscriber bị ngắt vẫn có thể truy hồi: **Redis Pub/Sub không giữ backlog cho subscriber offline**. Nếu cần đọc lại, cân nhắc Stream và checkpoint xử lý, kèm cơ chế khôi phục consumer group phù hợp.

## 8. Redis đổi sang máy chủ khác: ba mô hình vận hành

### 8.1. Standalone và thay đổi trực tiếp endpoint

Ví dụ, máy chủ cũ là `redis-old.internal:6379`, còn máy mới là `redis-new.internal:6379`. Nếu service chỉ biết địa chỉ cũ và không có cơ chế discovery, reconnect sẽ tiếp tục hướng tới máy cũ.

Các cách xử lý:

1. Cập nhật cấu hình endpoint và triển khai/cập nhật application context theo quy trình ứng dụng.
2. Sử dụng DNS hoặc tên service ổn định nếu hạ tầng có thể thay backend dưới một endpoint.
3. Xác minh các socket cũ đã được thay hoặc client buộc reconnect khi cần.
4. Kiểm tra dữ liệu ở máy mới có đúng phạm vi cần thiết; đổi endpoint có thể đổi **cả dữ liệu** chứ không chỉ địa chỉ mạng.

Tự động thay `host` trong file cấu hình không đồng nghĩa bean `RedisConnectionFactory` đã tự đọc lại giá trị lúc runtime. Với ứng dụng Spring Boot thông thường, nhiều thuộc tính được bind khi bean khởi tạo. Cần cơ chế refresh cấu hình được thiết kế rõ ràng, hoặc triển khai lại/restart ứng dụng.

### 8.2. Redis Sentinel thay primary

Sentinel giám sát một nhóm primary–replica và cung cấp thông tin primary hiện hành. Khi primary hỏng, Sentinel có thể bầu/promote replica để thay thế, tùy điều kiện quorum và cơ chế failover.

~~~text
Ứng dụng
   |
   +--> Sentinel A
   +--> Sentinel B  ---> tra cứu primary hiện tại
   +--> Sentinel C
                     |
                Redis primary P1
                     |
                 Redis replica R1

Khi failover: R1 được nâng thành primary mới.
~~~

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
      connect-timeout: 2s
      timeout: 3s
~~~

Những điều bắt buộc phải hiểu:

- **Tên master** (`mymaster`) là tên cấu hình Sentinel, không phải hostname của Redis node.
- Endpoint Sentinel dùng cho **discovery**; endpoint Redis primary mới là nơi thực thi lệnh dữ liệu.
- Redis node do Sentinel trả về phải truy cập được từ mạng ứng dụng; khi chạy container, NAT hoặc nhiều VPC, địa chỉ được công bố có thể không đúng với phía client.
- Redis auth và Sentinel auth có thể cần được cấu hình riêng.
- Trong khi failover diễn ra, các lệnh có thể lỗi; driver cần tìm primary mới và service vẫn cần xử lý request chưa thành công.
- Replica có thể trễ dữ liệu. Một số thao tác đã ghi vào primary cũ có nguy cơ không xuất hiện trên primary mới trong các tình huống failover; replication không đồng nghĩa commit đồng bộ tuyệt đối.

Một endpoint primary cố định không giải quyết được failover Sentinel. Muốn tự nhận primary mới, phải sử dụng cách kết nối hiểu Sentinel hoặc hạ tầng proxy phù hợp.

### 8.3. Redis Cluster chuyển node và hash slot

Redis Cluster chia keyspace thành **16.384 hash slot**. Khi node hỏng hoặc cụm được cân bằng lại, topology sở hữu slot có thể thay đổi.

~~~text
Spring Data Redis
       |
       v
Lettuce/Jedis Cluster-aware client
       |
       +----> Node A: slot nhóm A
       +----> Node B: slot nhóm B
       +----> Node C: slot nhóm C
                   |
             MOVED / ASK
                   |
            Cập nhật định tuyến
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-a.internal:6379
          - redis-b.internal:6379
          - redis-c.internal:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
~~~

Danh sách `nodes` là các node khởi tạo để khám phá cụm, **không phải bản đồ cố định** mà ứng dụng tự chia key.

Hai phản hồi quan trọng:

- **MOVED:** node báo slot hiện do một node khác sở hữu; client cluster-aware cần chuyển hướng và có thể cập nhật topology.
- **ASK:** chuyển hướng tạm thời, thường xuất hiện trong quá trình dịch chuyển slot; client phải tuân theo giao thức chuyển hướng tương ứng.

Lettuce hỗ trợ làm mới topology cụm; có các lựa chọn refresh theo chu kỳ hoặc theo sự kiện. Thiết lập cần phù hợp với phiên bản driver và môi trường thực tế. Đừng coi `max-redirects` là giải pháp cho một cụm luôn công bố IP không thể truy cập từ ứng dụng.

**Không chuyển sang host/port mới bằng cách bỏ qua hash slot.** Với Cluster, ứng dụng phải tiếp tục dùng client hiểu slot routing; các thao tác đa khóa còn bị giới hạn bởi điều kiện cùng slot.

## 9. Retry an toàn: đọc, ghi, và trạng thái không chắc chắn

### 9.1. Phân loại theo hiệu ứng nghiệp vụ

| Hoạt động | Retry khi lỗi kết nối/timeout? | Lý do |
|---|---|---|
| `GET key`, `HGET key field` | Thường có thể retry có giới hạn | Đọc không đổi dữ liệu Redis |
| `EXISTS key`, `TTL key` | Thường có thể retry có giới hạn | Đọc trạng thái hiện tại |
| `SET key sameValue` | Có thể idempotent về giá trị, nhưng phải xem TTL/ghi đè | Ghi lặp có thể làm mới TTL hoặc ghi đè thay đổi mới |
| `INCR`, `LPUSH`, `XADD` | Không retry mù | Lệnh có thể đã chạy trước khi reply mất |
| Trừ tồn kho/thanh toán/ghi đơn | Cần idempotency và nguồn xác nhận riêng | Phải tránh áp dụng hiệu ứng nghiệp vụ nhiều lần |
| Giao dịch nhiều lệnh | Không thể tự động coi cả chuỗi là một thao tác retry an toàn | Một phần hoặc toàn bộ công việc có thể đã thực hiện |

Lệnh retry phải được đánh giá theo cả **hiệu ứng trên Redis** và **ý nghĩa nghiệp vụ**. Ví dụ, `SET key value` lặp lại có thể không đổi giá trị cuối, nhưng nếu đặt TTL mới hoặc xen giữa có người ghi giá trị khác, kết quả vẫn có thể sai.

### 9.2. Mẫu imperative: đọc cache với retry có giới hạn

Ví dụ chỉ phù hợp khi Redis **là cache tùy chọn** và ứng dụng có nguồn dữ liệu chính để đọc tiếp nếu trả về `Optional.empty()`:

~~~java
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {
    private static final Logger log =
            LoggerFactory.getLogger(ProductCacheReader.class);

    private final StringRedisTemplate redis;

    public ProductCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Optional<String> getCachedName(String productId) {
        String key = "product:" + productId + ":name";

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                return Optional.ofNullable(redis.opsForValue().get(key));
            } catch (RedisConnectionFailureException | QueryTimeoutException ex) {
                if (attempt == 2) {
                    log.warn("Redis unavailable for cache key {}", key, ex);
                    return Optional.empty();
                }

                // Imperative code only: retry sau khoảng chờ ngắn có jitter.
                try {
                    Thread.sleep(
                        ThreadLocalRandom.current().nextLong(30, 81));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return Optional.empty();
                }
            }
        }

        return Optional.empty();
    }
}
~~~

Điểm cần hiểu:

- `GET` là lệnh đọc nên retry ít rủi ro hơn thao tác ghi có tác dụng phụ.
- Retry chỉ xảy ra với hai nhóm ngoại lệ minh họa, không bắt và giấu mọi lỗi `DataAccessException` như `WRONGTYPE` hoặc lỗi cấu hình.
- Trả `Optional.empty()` làm cache miss và cache outage trông giống nhau đối với caller; đây là **chủ ý của cache best-effort**, cần log/metric riêng để không làm mất khả năng quan sát.
- `Thread.sleep` chặn thread và **không phù hợp trên Reactor event loop**. Khi dùng reactive, hãy sử dụng retry/backoff trong Reactor.
- Số lần retry phải tính vào thời gian còn lại của HTTP request. Nếu Redis là thành phần bắt buộc cho nghiệp vụ, trả empty như cache miss là sai; hãy truyền lỗi có kiểm soát.

### 9.3. Mẫu reactive: fallback cho lệnh đọc cache

Với `ReactiveStringRedisTemplate`, mô hình xử lý có thể là:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCacheReader {
    private static final Logger log =
            LoggerFactory.getLogger(ReactiveProductCacheReader.class);

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductCacheReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> getCachedName(String productId) {
        return redis.opsForValue()
            .get("product:" + productId + ":name")
            .onErrorResume(RedisConnectionFailureException.class, ex -> {
                log.warn("Redis cache temporarily unavailable", ex);
                return Mono.empty();
            });
    }
}
~~~

Ở đây `Mono.empty()` biểu thị cache không có kết quả. Với lỗi timeout hoặc chính sách retry có backoff, thêm xử lý tương ứng theo loại ngoại lệ thực tế và dùng các toán tử Reactor thích hợp. Không gọi `.block()` để “đợi Redis lên lại” trong request pipeline reactive.

### 9.4. Idempotency cho thao tác ghi quan trọng

Giả sử service nhận yêu cầu tạo đơn hàng có `requestId`. Một mẫu thiết kế là ghi nhận `requestId` bằng cơ chế bền vững và bảo đảm trạng thái xử lý chỉ chuyển một lần. Redis có thể hỗ trợ dedup tạm bằng `SET NX`:

~~~redis
SET idempotency:order:req-123 "processing" NX EX 600
~~~

Lệnh chỉ tạo khóa nếu khóa chưa tồn tại. Nhưng **chỉ riêng SET NX không bảo đảm exactly-once**: service có thể tạo khóa rồi crash trước khi lưu đơn, TTL có thể hết trước lúc retry muộn, hoặc hai hệ thống có thể tranh chấp trạng thái. Với thanh toán/đơn hàng, cần một trạng thái idempotency có thể kiểm chứng, cơ chế hoàn tất/khôi phục và một nguồn lưu trữ nghiệp vụ đáng tin cậy.

## 10. Readiness, liveness và degraded mode

Khi Redis hỏng, ứng dụng cần quyết định liệu nó còn có thể phục vụ request hay không.

| Redis dùng để làm gì? | Chiến lược thường phù hợp |
|---|---|
| Cache tùy chọn, dữ liệu gốc trong database | Tiếp tục chạy; cache miss/fallback; log và metric Redis outage |
| Session bắt buộc cho đăng nhập | Có thể từ chối các request cần session; quyết định readiness theo kiến trúc |
| Khóa điều phối hoặc kiểm soát tính đúng đắn | Fail-closed cho thao tác phụ thuộc khóa khi Redis không chắc chắn |
| Hàng đợi/sự kiện Redis là nguồn xử lý quan trọng | Dừng/giảm consumer thích hợp, dùng checkpoint và cơ chế phục hồi |
| Dữ liệu có thể tái dựng | Tái nạp có kiểm soát sau restart, tránh stampede |

**Liveness** phản ánh tiến trình ứng dụng còn hoạt động; một Redis outage không nhất thiết có nghĩa nên restart JVM liên tục. **Readiness** phản ánh instance có nên nhận lưu lượng hay không, tùy các phụ thuộc bắt buộc. Nếu Redis chỉ là cache tùy chọn, buộc readiness thất bại mỗi khi Redis mất kết nối có thể rút toàn bộ instance khỏi load balancer và khuếch đại sự cố.

Spring Boot Actuator có health indicator Redis trong các cấu hình thích hợp. Cần quyết định Redis health nên tham gia health group nào theo mức độ phụ thuộc của service, thay vì mặc định dùng một phản hồi `DOWN` để điều khiển cả liveness và readiness.

### 10.1. Circuit breaker và bulkhead

Nếu Redis không sẵn sàng kéo dài, retry liên tục trên mọi request có thể làm tăng độ trễ và tiêu thụ thread. Circuit breaker giúp tạm ngừng gọi Redis sau một ngưỡng lỗi và thử lại có kiểm soát khi cho phép.

Bulkhead hoặc giới hạn đồng thời giúp ngăn các request chờ Redis lấy hết tài nguyên của service.

Cần có chiến lược riêng cho loại nghiệp vụ: **fallback đúng với cache** có thể **nguy hiểm với khóa phân tán** nếu service tiếp tục công việc như thể khóa đã được lấy thành công.

## 11. Duy trì trạng thái đúng sau reconnect

Kết nối mới chỉ khôi phục đường truyền. Một số loại tác vụ cần khôi phục trạng thái ở tầng ứng dụng:

### 11.1. Redis Pub/Sub

Pub/Sub phân phối message tới các subscriber đang kết nối. Sau disconnect, cần bảo đảm subscriber đã subscribe lại và hiểu rằng message phát trong khoảng offline có thể mất.

Nếu ứng dụng đòi hỏi khả năng đọc lại, dùng cơ chế lưu sự kiện như Redis Streams thay vì dựa vào Pub/Sub thuần túy.

### 11.2. Redis Streams và consumer group

Sau restart/reconnect, consumer có thể tiếp tục đọc các entry đã lưu nếu Redis đã duy trì dữ liệu. Cần quản lý `XREADGROUP`, `XACK` và các pending entry khi consumer chết hoặc đổi instance.

Consumer reconnect không tự quyết định liệu một entry đã được xử lý nghiệp vụ trước khi lỗi hay chưa. Nên thiết kế xử lý lặp an toàn và cơ chế nhận lại pending khi cần.

### 11.3. Transaction, pipeline và lệnh blocking

- **Transaction:** kết nối hỏng trong quá trình transaction khiến ứng dụng phải xác định transaction đã được thực thi tới đâu; không tự kết luận lỗi mạng đồng nghĩa mọi lệnh chưa chạy.
- **Pipeline:** mất phản hồi của nhiều command có thể khiến không biết rõ từng command đã chạy hay chưa; không replay toàn bộ pipeline ghi tùy tiện.
- **Blocking command:** lệnh chờ dữ liệu như blocking pop/read có thể kết thúc bằng ngoại lệ khi kết nối mất; consumer cần khởi động lại vòng đọc theo chính sách.
- **Khóa phân tán:** sau một lần đứt mạng, client có thể không biết khóa đã được cấp hay chưa hoặc đã hết TTL hay chưa. Không tiếp tục thao tác độc quyền nếu không chắc quyền sở hữu khóa còn hợp lệ.

## 12. Quan sát và chẩn đoán khi mất kết nối

Một lỗi Redis cần đủ dữ liệu để xác định nguyên nhân gốc mà không phải ghi lộ password hoặc payload nhạy cảm.

| Thông tin quan sát | Mục đích |
|---|---|
| Số lượng lỗi kết nối theo thời gian | Phát hiện đợt outage và tần suất reconnect |
| Command timeout / connect timeout / pool wait timeout | Tách nhóm lỗi |
| Redis command latency | Xác định server chậm hay chỉ riêng network |
| Pool active, idle, waiters, borrow timeout | Phát hiện pool cạn hoặc connection bị giữ quá lâu |
| Số Redis clients, rejected connections | Phát hiện áp lực connection phía server |
| Redis memory, CPU, eviction, blocked clients | Phát hiện server quá tải |
| Replication lag và vai trò node | Xác định read staleness và failover |
| Redis Cluster slot coverage / node state | Xác định lỗi routing/topology |
| DNS resolution, socket reset, TLS error | Xác định lỗi hạ tầng và thay endpoint |
| Mốc restart/failover/deployment | Đối chiếu nguyên nhân với thời điểm bắt đầu lỗi |

Để phân biệt lỗi mạng và lỗi pool, cần nhìn **hai phía**: service có thể báo pool wait timeout trong khi Redis vẫn khỏe, hoặc service có nhiều connection mới nhưng Redis đang từ chối kết nối vì vượt giới hạn clients.

### 12.1. Một quy trình chẩn đoán theo thứ tự

1. **Xác định phạm vi:** mọi instance lỗi hay chỉ một máy/availability zone?
2. **Xác định loại lỗi:** DNS, connect, TLS, command timeout, borrow timeout hay `MOVED`/`ASK`?
3. **Kiểm tra Redis có sẵn sàng không:** quá trình restart đã xong, primary/replica và cluster có trạng thái đúng?
4. **Kiểm tra endpoint hiện tại:** hostname/IP/port và địa chỉ do Sentinel/Cluster công bố có truy cập được từ ứng dụng?
5. **Kiểm tra tài nguyên và pool:** pool cạn, connection idle chết, Redis client limit, CPU và network latency.
6. **Kiểm tra tính đúng đắn nghiệp vụ:** những lệnh ghi có kết quả không chắc chắn phải được xác minh trước khi replay.
7. **Khôi phục có kiểm soát:** để driver reconnect/đổi endpoint, hoặc khởi tạo lại ứng dụng khi cấu hình/factory chỉ cập nhật lúc startup.
8. **Quan sát sau phục hồi:** tỷ lệ lỗi giảm, latency trở lại bình thường và dữ liệu quan trọng được xác nhận.

Trong quá trình chẩn đoán, không ghi nguyên password, access token hay dữ liệu người dùng vào log.

## 13. Các kịch bản thực hành để hiểu cơ chế phục hồi

Có thể tự tạo tình huống hỏng trong môi trường phát triển hoặc staging để quan sát behavior. Các ví dụ sau là **kịch bản học tập**, không phải lệnh đã được thực thi trong bài.

### Kịch bản A: Redis Standalone restart

1. Khởi chạy service có thao tác đọc cache định kỳ.
2. Ghi nhận trước restart: số Redis connections, latency và kết quả đọc.
3. Dừng Redis tạm thời.
4. Quan sát exception/timeout, số retry và fallback.
5. Khởi động Redis lại.
6. Quan sát thời gian driver có thể chạy lệnh mới, cache miss và tác động của dữ liệu sau restart.

Điểm cần rút ra: **Redis lên lại không làm các lời gọi đã lỗi tự thành công**.

### Kịch bản B: Stale Jedis connection trong pool

1. Mở một số connection rồi cho idle.
2. Làm Redis restart hoặc ngắt các socket cũ.
3. Gửi request mới sử dụng pool.
4. Quan sát connection nào lỗi ngay lần borrow/command đầu tiên.
5. Đối chiếu chính sách validation và eviction; kiểm tra pool có phục hồi được không.

Điểm cần rút ra: pool giữ connection không có nghĩa chúng luôn khỏe; validation cũng không thay thế xử lý lỗi lúc gửi lệnh.

### Kịch bản C: Thay endpoint Standalone

1. Cấu hình ứng dụng trỏ tới một hostname logic.
2. Thay backend Redis hoặc bản ghi DNS tại hạ tầng thử nghiệm.
3. Xác định khi nào application thực sự mở socket tới máy mới.
4. Nếu vẫn kết nối tới máy cũ, kiểm tra connection đang được giữ, DNS cache và cơ chế refresh cấu hình.
5. Xác nhận dữ liệu ở đích mới đáp ứng yêu cầu nghiệp vụ.

Điểm cần rút ra: đổi IP và đổi Redis topology là hai việc khác nhau; endpoint ổn định giúp vận hành nhưng không thay thế connection lifecycle.

### Kịch bản D: Sentinel failover

1. Dùng môi trường Redis primary–replica có Sentinel.
2. Cho primary gặp sự cố theo cơ chế thử nghiệm của môi trường.
3. Quan sát Sentinel chọn primary mới và client tìm lại primary.
4. Kiểm tra ứng dụng có ghi được vào primary mới và có gặp replica lag hay không.
5. Xem lại các thao tác ghi xảy ra sát mốc failover.

Điểm cần rút ra: **failover thành công ở hạ tầng không tự bảo đảm mọi ghi trước failover đã được nhân bản**.

### Kịch bản E: Redis Cluster chuyển slot

1. Kết nối bằng client cluster-aware.
2. Di chuyển một số hash slot trong cụm thử nghiệm.
3. Quan sát phản hồi chuyển hướng và quá trình client cập nhật topology.
4. Xác minh các lệnh truy cập key sau migration vẫn tới đúng node.
5. Kiểm tra ứng dụng có phụ thuộc thao tác multi-key không hợp lệ trên nhiều slot hay không.

Điểm cần rút ra: reconnect ở Cluster cần đi kèm **routing và topology refresh**, không chỉ TCP mới.

## 14. Ví dụ tổng hợp: chọn chính sách khôi phục theo vai trò Redis

Giả sử một ứng dụng bán hàng dùng Redis ở ba vị trí:

~~~text
ProductController
   |
   +--> ProductService --> Database chính
   |                          |
   |                        Redis cache
   |
OrderService
   |
   +--> Database giao dịch
   +--> Redis dedup tạm / rate-limit
   |
EventConsumer
   |
   +--> Redis Stream
~~~

Khi Redis restart:

| Thành phần | Cách phản ứng hợp lý |
|---|---|
| Cache sản phẩm | Đọc từ database chính, hạn chế retry, tải lại cache theo nhu cầu |
| Tạo đơn hàng | Không lặp lại giao dịch chỉ vì Redis timeout; kiểm tra trạng thái đơn và request ID |
| Rate limit | Quyết định fail-open hay fail-closed theo yêu cầu bảo mật/tải; không giả định mọi hệ thống giống nhau |
| Redis Stream consumer | Kết nối lại, tiếp tục đọc, xử lý pending và tránh áp dụng hiệu ứng trùng |
| Health của service | Cân nhắc readiness theo chức năng bắt buộc; liveness chỉ phản ánh tiến trình |

Một chiến lược kết nối duy nhất không thể áp dụng nguyên xi cho mọi nghiệp vụ. **Tính đúng đắn của thao tác ghi phải được thiết kế ở tầng nghiệp vụ; quản lý connection và pool chỉ giải quyết tầng transport.**

## 15. Những nguyên tắc cần ghi nhớ

- **Kết nối bị hỏng là một trạng thái dự kiến trong hệ thống phân tán.** Cần timeout hữu hạn, observability và hành vi phục hồi rõ ràng.
- **Lettuce có khả năng auto-reconnect**, còn **Jedis thường dựa vào vòng đời connection và pool** trong ứng dụng imperative. Cả hai không tự bảo đảm retry đúng một lần.
- **Redis restart có thể làm mất cả connection lẫn một phần dữ liệu**, tùy persistence, replication và mục đích sử dụng Redis.
- **Đổi máy chủ đòi hỏi discovery hoặc endpoint đúng:** Standalone có thể cần cập nhật endpoint; Sentinel cần master discovery; Cluster cần slot routing và topology refresh.
- **Pool có thể chứa connection đã chết** hoặc bị cạn. Validation, eviction và max-wait giúp quản lý tài nguyên, nhưng vẫn phải xử lý lỗi khi thao tác.
- **Retry phải có giới hạn và xét tính idempotent.** Lệnh ghi đã gửi nhưng chưa nhận reply có thể đã thực thi.
- **Ứng dụng cần phân biệt cache tùy chọn với dữ liệu bắt buộc.** Fallback cache có thể hợp lý, còn giả định thành công với khóa phân tán hoặc thanh toán có thể gây lỗi nghiệp vụ.
- **Phục hồi phải được xác minh bằng hành vi và dữ liệu:** kết nối mới mở được là điều kiện cần, chưa đủ để kết luận service đã phục hồi hoàn toàn.

Nắm được các điểm này giúp ứng dụng Spring Data Redis xử lý được Redis restart, kết nối chết trong pool và thay đổi máy chủ mà vẫn giữ độ ổn định và tính đúng đắn của nghiệp vụ.
