# Namespace và cách tách khóa phiên giữa các ứng dụng, môi trường

Spring Session có thể lưu session của nhiều instance ứng dụng trong cùng một Redis. Điều đó giúp các instance của cùng ứng dụng chia sẻ trạng thái phiên, nhưng cũng đặt ra một yêu cầu: khóa Redis của ứng dụng này phải được tách khỏi khóa của ứng dụng khác và khỏi dữ liệu ở môi trường khác.

Spring Session dùng một namespace làm tiền tố cho key session trong Redis. Nếu không cấu hình riêng, namespace mặc định thường là spring:session. Khi nhiều ứng dụng cùng dùng một Redis, dùng namespace mặc định cho tất cả có thể dẫn tới va chạm key, đọc nhầm dữ liệu hoặc xóa nhầm session. Cần đặt namespace rõ ràng theo ứng dụng và môi trường, rồi giữ cấu hình đó nhất quán trên mọi instance.

Bài này giải thích namespace hoạt động ra sao, cách chọn quy ước đặt tên, cách cấu hình Spring Session, cách phối hợp namespace với Redis database, ACL và cookie, cùng quy trình migration và kiểm tra khi vận hành.

## 1. Namespace trong Spring Session là gì?

Namespace là chuỗi tiền tố được Spring Session dùng để nhóm các key mà repository tạo ra trong Redis. Nó tạo ranh giới tên giữa các tập dữ liệu session trong cùng một Redis server hoặc cluster.

Ví dụ, nếu namespace là:

~~~text
acme:commerce:checkout:prod:spring-session
~~~

các key nội bộ có thể có dạng:

~~~text
acme:commerce:checkout:prod:spring-session:sessions:<session-id>
acme:commerce:checkout:prod:spring-session:expirations:<time-bucket>
acme:commerce:checkout:prod:spring-session:index:...
~~~

Đây là ví dụ minh họa về cách tiền tố được áp dụng; cấu trúc chi tiết và các loại key phụ thuộc repository, phiên bản Spring Session và các tính năng được bật. Ứng dụng nên thao tác qua SessionRepository và API Spring Session thay vì phụ thuộc vào tên key nội bộ.

Namespace không phải session ID, cookie name hay tên database Redis. Nó là tiền tố ở phía kho lưu trữ. Một trình duyệt có thể gửi cùng một cookie session ID đến một ứng dụng, nhưng repository của ứng dụng đó chỉ tìm kiếm trong keyspace namespace mà ứng dụng được cấu hình.

### Namespace giải quyết vấn đề gì?

Giả sử ứng dụng checkout và ứng dụng admin cùng kết nối tới một Redis. Nếu cả hai dùng namespace mặc định, các cấu trúc key có thể trùng tên. Khi một ứng dụng lưu hoặc xóa session, ứng dụng kia có nguy cơ quan sát nhầm dữ liệu hoặc bị ảnh hưởng bởi thao tác cleanup.

Khi tách namespace:

| Ứng dụng | Namespace |
|---|---|
| Checkout | acme:commerce:checkout:prod:spring-session |
| Admin | acme:commerce:admin:prod:spring-session |
| Customer portal | acme:commerce:portal:prod:spring-session |

Mỗi repository thao tác trên nhóm key riêng. Các instance checkout dùng chung một namespace để nhìn thấy cùng session; ứng dụng admin dùng namespace khác để có keyspace độc lập.

Namespace giúp tránh va chạm tên key. Nó không mã hóa dữ liệu, không phân quyền truy cập Redis và không thay thế ACL hoặc tách hạ tầng.

## 2. Thiết kế quy ước namespace

Một quy ước tốt phải dễ đọc, ổn định, không chứa dữ liệu nhạy cảm và có thể áp dụng thống nhất cho mọi instance.

Một cấu trúc thường dùng:

~~~text
<organization>:<domain>:<application>:<environment>:spring-session
~~~

Ví dụ:

| Thành phần | Giá trị mẫu | Ý nghĩa |
|---|---|---|
| organization | acme | Nhóm sở hữu hệ thống |
| domain | commerce | Miền nghiệp vụ |
| application | checkout | Ứng dụng cụ thể |
| environment | prod | Môi trường triển khai |
| suffix | spring-session | Nhận diện nhóm key của Spring Session |

Một namespace hoàn chỉnh:

~~~text
acme:commerce:checkout:prod:spring-session
~~~

Một số nguyên tắc:

- **Đặt tên theo ứng dụng và môi trường.** Hai ứng dụng độc lập hoặc hai môi trường độc lập nên có namespace khác nhau nếu dùng chung Redis.
- **Dùng ký tự ổn định.** Chữ thường, số, dấu gạch ngang và dấu hai chấm giúp tên dễ đọc và dễ lọc bằng công cụ Redis.
- **Không dùng tên pod hoặc hostname.** Các instance của cùng ứng dụng phải chia sẻ namespace; nếu thêm tên pod, mỗi instance sẽ nhìn thấy một keyspace khác và mất khả năng chia sẻ session.
- **Không đưa bí mật vào namespace.** Không dùng token, mật khẩu, email, tên người dùng hoặc dữ liệu cá nhân làm thành phần của prefix.
- **Giữ namespace ngắn và có ý nghĩa.** Prefix dài làm key dài hơn và khó thao tác; không cần lặp lại mọi tên nhóm hạ tầng.
- **Không thay đổi tùy tiện giữa các lần triển khai.** Namespace mới thường làm các session ở namespace cũ trở nên không nhìn thấy với ứng dụng mới.

Có thể thêm region hoặc cluster khi một ứng dụng thật sự cần nhiều keyspace độc lập theo khu vực. Tuy nhiên, nếu các region cùng phục vụ một tập session chia sẻ, phải có thiết kế đồng bộ dữ liệu phù hợp; chỉ dùng cùng tên namespace không làm dữ liệu Redis tự động được sao chép giữa các cluster.

## 3. Cấu hình namespace trong Spring Session

Với ứng dụng cấu hình Java và Redis, có thể đặt namespace trong annotation:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(
    redisNamespace = "acme:commerce:checkout:prod:spring-session",
    maxInactiveIntervalInSeconds = 1800
)
public class SessionConfig {
}
~~~

Với repository indexed, annotation tương ứng cũng cho phép chỉ định namespace:

~~~java
@Configuration
@EnableRedisIndexedHttpSession(
    redisNamespace = "acme:commerce:checkout:prod:spring-session",
    maxInactiveIntervalInSeconds = 1800
)
public class IndexedSessionConfig {
}
~~~

Nếu dùng Spring Boot auto-configuration, có thể cấu hình namespace bằng property trong application.yml:

~~~yaml
spring:
  session:
    redis:
      namespace: acme:commerce:checkout:prod:spring-session
~~~

Tên property và cách chọn repository cần được đối chiếu với phiên bản Spring Boot/Spring Session của dự án. Khi đã dùng auto-configuration, tránh khai báo thêm một cấu hình annotation khác để tạo repository thứ hai cho cùng ứng dụng.

### Tất cả instance phải dùng cùng namespace

Trong một cụm nhiều instance, cấu hình namespace phải giống nhau trên tất cả node:

~~~text
checkout-1 -> acme:commerce:checkout:prod:spring-session
checkout-2 -> acme:commerce:checkout:prod:spring-session
checkout-3 -> acme:commerce:checkout:prod:spring-session
~~~

Nếu một instance dùng namespace khác:

~~~text
checkout-1 -> acme:commerce:checkout:prod:spring-session
checkout-2 -> acme:commerce:checkout:prod:spring-session-v2
~~~

một request có thể tạo session ở namespace thứ nhất, nhưng request kế tiếp đi tới instance thứ hai lại không tìm thấy session đó. Người dùng có thể bị yêu cầu đăng nhập lại ngẫu nhiên hoặc liên tục nhận cookie mới.

Namespace là cấu hình ở cấp ứng dụng/môi trường, không phải cấu hình riêng cho từng máy chủ.

## 4. Namespace và Redis logical database

Redis hỗ trợ logical database được chọn bằng chỉ số, ví dụ database 0, 1 hoặc 2 trong một Redis server standalone. Có thể dùng database riêng để tách dữ liệu:

| Môi trường | Redis database | Namespace |
|---|---:|---|
| Development | 1 | acme:commerce:checkout:dev:spring-session |
| Staging | 2 | acme:commerce:checkout:staging:spring-session |
| Production | 3 | acme:commerce:checkout:prod:spring-session |

Logical database và namespace giải quyết hai mức tách biệt khác nhau:

- Logical database tách không gian key theo chỉ số database trong một Redis server hỗ trợ nhiều database.
- Namespace thêm tiền tố vào key, giúp tách ứng dụng ngay cả khi chúng dùng cùng database.

Không nên xem logical database là phương án tách biệt hạ tầng hoàn chỉnh. Các database logic vẫn dùng chung tiến trình Redis, bộ nhớ, CPU, cấu hình persistence, replication và giới hạn tài nguyên. Một sự cố hoặc áp lực bộ nhớ ở Redis server vẫn có thể ảnh hưởng tất cả database.

Redis Cluster chỉ hỗ trợ database 0. Không thể dựa vào SELECT để tách môi trường trong Redis Cluster. Với cluster, namespace/prefix và quyền truy cập ACL càng quan trọng; môi trường production và non-production có yêu cầu cô lập cao nên cân nhắc cluster hoặc instance riêng.

## 5. Namespace không thay thế ACL và phân quyền

Một prefix riêng giúp tránh va chạm key, nhưng bất kỳ client nào có quyền truy cập rộng vào Redis vẫn có thể đọc hoặc sửa key của namespace khác. Namespace tự nó không phải ranh giới bảo mật.

Nên kết hợp:

- **Redis ACL:** giới hạn user Redis chỉ được truy cập các key pattern cần thiết và các command cần dùng.
- **Credential riêng:** dùng tài khoản Redis riêng cho ứng dụng hoặc nhóm ứng dụng khi hạ tầng hỗ trợ.
- **TLS:** bảo vệ kết nối giữa ứng dụng và Redis khi đi qua mạng không tin cậy.
- **Mạng riêng:** giới hạn nguồn có thể kết nối tới Redis.
- **Tách instance/cluster:** dùng khi các môi trường hoặc nhóm ứng dụng cần mức cô lập tài nguyên và sự cố cao hơn.
- **Giám sát quyền:** kiểm tra quyền truy cập thực tế sau khi thay đổi namespace hoặc repository.

Redis ACL hỗ trợ giới hạn key theo pattern. Ví dụ pattern khái niệm cho namespace checkout:

~~~text
~acme:commerce:checkout:prod:spring-session:*
~~~

Đây chỉ là một phần của ACL policy. Ứng dụng còn cần các command và, với repository indexed, có thể cần quyền Pub/Sub phù hợp cho các channel notification. Không sao chép một ACL tối thiểu chưa được kiểm thử vào production; hãy xác định command/channel thực tế theo phiên bản Spring Session và cấu hình Redis.

Namespace không nên chứa thông tin nhận dạng người dùng hoặc tenant. Nếu cần phân quyền theo tenant, thực hiện kiểm tra ở tầng ứng dụng và thiết kế kho dữ liệu phù hợp. Không dùng một chuỗi prefix do client gửi lên để tự chọn keyspace.

## 6. Namespace và cookie session là hai cấu hình khác nhau

Namespace xác định keyspace phía Redis. Cookie name, Domain và Path quyết định trình duyệt gửi session ID đến ứng dụng nào.

Ví dụ:

| Thành phần | Checkout | Admin |
|---|---|---|
| Redis namespace | acme:commerce:checkout:prod:spring-session | acme:commerce:admin:prod:spring-session |
| Cookie name | CHECKOUT_SESSION | ADMIN_SESSION |
| Cookie path | /shop | /admin |
| Domain | Host-only hoặc theo chính sách triển khai | Host-only hoặc theo chính sách triển khai |

Nếu hai ứng dụng nằm trên cùng host và cùng path, trình duyệt có thể gửi cookie cùng tên tới cả hai. Dù namespace Redis khác nhau, ứng dụng vẫn có thể nhận một session ID do ứng dụng kia phát. Repository sẽ tìm ID trong keyspace riêng và không tìm thấy; sau đó ứng dụng có thể tạo session mới và ghi đè cookie của ứng dụng còn lại.

Vì vậy, khi nhiều ứng dụng dùng chung domain, hãy phối hợp cả namespace và cookie scope. Có thể chọn cookie name riêng cho từng ứng dụng, path riêng hoặc subdomain riêng tùy kiến trúc. Không dựa vào namespace để giải quyết cookie trùng tên ở trình duyệt.

## 7. Tách namespace theo môi trường và chiến lược triển khai

Development, staging và production nên có keyspace riêng:

~~~text
acme:commerce:checkout:dev:spring-session
acme:commerce:checkout:staging:spring-session
acme:commerce:checkout:prod:spring-session
~~~

Tách môi trường giúp:

- Tránh test hoặc thao tác thủ công xóa session production.
- Tránh ứng dụng staging đọc session của người dùng production.
- Cho phép đặt TTL, giới hạn tài nguyên và chính sách cleanup phù hợp từng môi trường.
- Dễ truy vết key thuộc ứng dụng/môi trường nào khi giám sát.

Tuy nhiên, chỉ khác namespace chưa đủ để ngăn một ứng dụng staging kết nối nhầm Redis production. Hãy cấu hình endpoint, credential và network policy theo môi trường. Với production, nên dùng hạ tầng riêng nếu yêu cầu bảo mật, độ sẵn sàng hoặc hiệu năng đòi hỏi cô lập mạnh.

Không dùng namespace khác nhau cho các instance cùng một môi trường chỉ để dễ nhận diện node. Nếu muốn theo dõi node ghi session, dùng metric/log đã được kiểm soát; không chia keyspace của cùng một ứng dụng.

### Tenant có nên có namespace riêng?

Thông thường, không nên tạo một Redis namespace cho từng người dùng hoặc từng tenant chỉ vì dữ liệu session có tenant ID. Số lượng tenant có thể lớn và thay đổi liên tục, gây khó quản lý ACL, cleanup, thống kê và vận hành.

Có thể lưu tenant ID như một thuộc tính session nếu ứng dụng cần ngữ cảnh tenant, nhưng mọi thao tác nghiệp vụ phải xác minh tenant hiện tại và quyền truy cập. Nếu yêu cầu cô lập dữ liệu tenant ở cấp hạ tầng, hãy thiết kế database/cluster/credential riêng hoặc một chiến lược phân vùng có quản lý, thay vì ghép trực tiếp dữ liệu client vào namespace.

## 8. Đổi namespace và migration session

Thay đổi namespace không phải thao tác đổi tên key đơn giản. Nếu ứng dụng chuyển từ:

~~~text
spring:session
~~~

sang:

~~~text
acme:commerce:checkout:prod:spring-session
~~~

repository mới sẽ tìm session trong keyspace mới. Những session còn tồn tại ở namespace cũ sẽ không tự xuất hiện trong namespace mới. Với người dùng, điều này thường giống như tất cả session cũ đã hết hạn và họ phải đăng nhập lại.

Trong rolling deployment, nếu node phiên bản cũ và mới dùng hai namespace khác nhau, cùng một cookie có thể được node cũ hiểu nhưng node mới không hiểu. Người dùng có thể bị đăng xuất tùy request được định tuyến tới node nào.

Trước khi đổi namespace, xác định mục tiêu:

- **Chỉ tách keyspace để tránh va chạm:** nếu có thể, hãy chọn namespace ổn định ngay từ đầu. Khi đổi, cần chấp nhận hoặc lập kế hoạch di chuyển session.
- **Chủ động thu hồi tất cả session:** đổi namespace có thể là một cách cắt sang keyspace mới, nhưng phải truyền thông và chuẩn bị luồng đăng nhập lại.
- **Di chuyển session đang hoạt động:** cần một migration có kiểm soát, tương thích serializer và định dạng key. Không sao chép key bằng lệnh Redis tùy tiện nếu không hiểu cấu trúc session, index, expiration và serialization.

Một kế hoạch đổi namespace có chủ đích:

1. Ghi nhận namespace cũ, namespace mới, repository và serializer đang dùng.
2. Quyết định session cũ được giữ, di chuyển hay bị thu hồi.
3. Nếu không di chuyển, thông báo khả năng người dùng phải đăng nhập lại và chọn thời điểm cutover.
4. Cập nhật cấu hình namespace đồng nhất trên mọi instance trước khi đưa phiên bản mới vào phục vụ.
5. Kiểm tra cookie vẫn phù hợp với ứng dụng và không bị chia sẻ nhầm giữa ứng dụng.
6. Theo dõi số session mới, tỷ lệ xác thực lại và lỗi lookup sau cutover.
7. Để keyspace cũ hết TTL hoặc dọn theo quy trình được kiểm soát sau khi chắc chắn không còn node nào cần đọc.
8. Không xóa wildcard key ngay lập tức nếu chưa xác minh phạm vi và tác động.

Nếu buộc phải hỗ trợ phiên bản cũ và mới cùng lúc, hãy thiết kế khả năng đọc tương thích hoặc một bước chuyển đổi có thời hạn. Tránh để các node phục vụ cùng một người dùng với namespace khác nhau trong thời gian rolling deployment.

## 9. Kiểm tra và quan sát namespace trong Redis

Có thể dùng redis-cli để tìm key theo prefix. Trong môi trường production, ưu tiên SCAN thay vì KEYS vì KEYS có thể quét toàn bộ keyspace và gây ảnh hưởng tới Redis khi dữ liệu lớn.

Ví dụ:

~~~bash
redis-cli --scan --pattern 'acme:commerce:checkout:prod:spring-session:*'
~~~

Lệnh trên minh họa việc liệt kê key theo namespace. Không đưa kết quả chứa session ID vào log chia sẻ hoặc tài liệu công khai. Với dữ liệu nhạy cảm, hãy chỉ kiểm tra số lượng hoặc nhóm key thay vì in toàn bộ key.

Nếu đã biết một key cụ thể trong môi trường test, có thể xem TTL:

~~~bash
redis-cli TTL 'acme:commerce:checkout:prod:spring-session:sessions:<session-id>'
~~~

Kết quả TTL phụ thuộc loại key và repository; key expiration phụ trợ có thể có thời hạn khác hash session. Không suy ra thời hạn toàn bộ session chỉ từ một key nội bộ. API repository và cấu hình maxInactiveInterval mới là nơi ứng dụng nên dựa vào.

### Các tín hiệu nên theo dõi

- Số session hiện hành theo ứng dụng/môi trường nếu repository hỗ trợ thống kê phù hợp.
- Số lượng key theo namespace và xu hướng tăng bộ nhớ.
- Tỷ lệ lookup không tìm thấy session.
- Lỗi kết nối, timeout và lỗi serialization.
- Số lần người dùng phải xác thực lại sau khi triển khai.
- Tình trạng TTL và cleanup.
- Redis memory usage, eviction, replication lag và cluster health.

Redis có thể dùng eviction policy khi bộ nhớ vượt giới hạn. Nếu key session bị eviction trước TTL, người dùng sẽ mất session sớm. Namespace không ngăn eviction và không tạo quota riêng cho từng ứng dụng. Cần cấu hình bộ nhớ, eviction policy, capacity và cảnh báo theo tải thực tế.

Không dùng lệnh FLUSHDB hoặc FLUSHALL để dọn một namespace. Các lệnh này có thể xóa dữ liệu của ứng dụng khác cùng database hoặc toàn bộ Redis. Nếu cần dọn key của một namespace, phải dùng quy trình có phạm vi rõ ràng, kiểm tra trước danh sách key và ưu tiên API repository khi có thể.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Người dùng bị đăng xuất sau khi thêm instance | Instance mới dùng namespace khác | Đồng bộ namespace trên mọi node |
| Hai ứng dụng ghi đè hoặc không tìm thấy session | Dùng chung namespace mặc định | Đặt namespace riêng cho từng ứng dụng |
| Staging nhìn thấy session production | Dùng chung Redis, namespace hoặc credential quá rộng | Tách endpoint/credential và namespace |
| Đổi namespace làm mọi session cũ biến mất | Repository mới tìm keyspace khác | Lập kế hoạch migration hoặc chấp nhận xác thực lại |
| Chỉ một số request bị mất session | Một số node có cấu hình namespace/cookie khác | So sánh cấu hình runtime giữa node |
| Cookie được gửi nhưng repository không tìm thấy ID | Cookie name/path dùng chung giữa ứng dụng hoặc ID thuộc namespace khác | Phối hợp cookie scope và namespace |
| ACL từ chối lệnh Redis | Policy thiếu key pattern, command hoặc Pub/Sub channel cần thiết | Kiểm tra log Redis và quyền theo repository |
| Dữ liệu session mất trước TTL | Redis eviction hoặc thao tác cleanup rộng | Kiểm tra memory pressure, eviction và lệnh xóa |
| Key không xuất hiện trong SCAN | Đang chọn sai database, prefix hoặc Redis endpoint | Kiểm tra connection factory, cluster và namespace runtime |

## 11. Checklist trước khi đưa namespace vào production

Trước khi triển khai, hãy xác nhận:

- Namespace có tên riêng cho từng ứng dụng và môi trường dùng chung Redis.
- Mọi instance của cùng ứng dụng trong một môi trường dùng đúng một namespace.
- Namespace không chứa session ID, email, token hoặc thông tin cá nhân.
- Redis endpoint, credential, TLS và network policy phù hợp với môi trường.
- Redis ACL cho phép đúng key pattern, command và channel cần thiết.
- Cookie name, Domain và Path không gây xung đột giữa các ứng dụng trên cùng host.
- Logical database chỉ được dùng khi Redis deployment hỗ trợ; Redis Cluster chỉ dùng database 0.
- TTL, eviction policy, capacity và cleanup đã được kiểm thử.
- Kế hoạch migration nêu rõ session cũ được giữ, di chuyển hay thu hồi.
- Không dùng KEYS, FLUSHDB hoặc FLUSHALL như cách dọn namespace thông thường.
- Có metric và cảnh báo cho lookup miss, lỗi Redis, serialization và xác thực lại.

Luồng định tuyến key có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Request mang cookie session ID] --> B[Instance ứng dụng]
    B --> C[SessionRepository của ứng dụng]
    C --> D[Namespace được cấu hình]
    D --> E[Redis keyspace riêng]
    E --> F{Key session hợp lệ?}
    F -->|Có| G[Đọc hoặc cập nhật session]
    F -->|Không| H[Request không có session hợp lệ]
    G --> I[Response]
    H --> I
~~~

Trong Spring Session, namespace là ranh giới tên key giúp nhiều ứng dụng và môi trường cùng sử dụng Redis mà không va chạm dữ liệu phiên. Hãy chọn namespace ổn định theo ứng dụng/môi trường, dùng cùng giá trị trên mọi instance, kết hợp ACL và hạ tầng phù hợp, đồng thời quản lý cookie riêng theo phạm vi trình duyệt. Khi đổi namespace, xem đó là một thay đổi vòng đời session có ảnh hưởng tới người dùng và cần kế hoạch migration rõ ràng.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — RedisIndexedSessionRepository Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisIndexedSessionRepository.html)
- [Spring Boot — Spring Session properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Redis — Keyspace](https://redis.io/docs/latest/develop/use/keyspace/)
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)

