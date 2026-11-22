# SSL, xác thực và giới hạn quyền truy cập Redis

## 1. Vì sao một ứng dụng Spring Boot cần bảo vệ Redis?

Trong hệ thống Spring Boot Integration, Redis thường lưu cache từ HTTP client, trạng thái tạm thời giữa các adapter, khóa chống xử lý trùng webhook, bộ đếm rate limit hoặc phiên đăng nhập. Những thành phần đó có thể chạy trên nhiều instance, pod hoặc máy chủ. Redis có tốc độ cao nhưng một kết nối mạng thành công không có nghĩa kết nối ấy an toàn.

Ví dụ, dịch vụ `order-integration` lưu cache tại các khóa:

~~~text
integration:orders:tenant-42:ORD-1001
integration:orders:tenant-42:ORD-1002
integration:dedup:partner-a:evt-198
~~~

Nếu kết nối không mã hóa, dữ liệu và thông tin xác thực có thể bị thu thập trên đường truyền. Nếu mọi dịch vụ dùng cùng một tài khoản toàn quyền, lỗi trong một service có thể xóa hoặc đọc dữ liệu của service khác. Nếu cổng Redis được mở ra Internet, ngay cả một mật khẩu mạnh cũng không thay thế được kiểm soát truy cập mạng.

Mục tiêu bài học là xây dựng mô hình an toàn theo bốn câu hỏi: **ai có thể kết nối, client có xác minh đúng server không, đăng nhập bằng danh tính nào, và danh tính ấy được phép làm gì trên những key hoặc channel nào?** Ví dụ sử dụng Redis hỗ trợ ACL (Redis 6+), Spring Boot 3.x, Spring Data Redis/Lettuce; khi dùng phiên bản khác cần đối chiếu property và tính năng thực tế.

## 2. Phân biệt TLS, authentication, authorization và giới hạn mạng

| Lớp bảo vệ | Câu hỏi giải quyết | Cơ chế | Không tự bảo đảm |
| --- | --- | --- | --- |
| **Network access** | Client nào mở được TCP tới Redis? | Private subnet, firewall, security group, Kubernetes NetworkPolicy, bind/port | Tài khoản Redis có quyền tối thiểu |
| **TLS/SSL** | Kênh truyền có được mã hóa và server được xác minh? | TLS certificate, CA trust, hostname validation, mTLS nếu cần | Command/key được phép |
| **Authentication** | Client là user Redis nào? | `AUTH`, ACL username/password | User ấy được đọc/ghi key nào |
| **Authorization** | User được chạy command, dùng key/channel nào? | Redis ACL command/category/key/channel rules | Quyền tenant của người dùng cuối, transaction liên hệ thống |

~~~mermaid
flowchart LR
    A["Spring Boot / Lettuce"] --> B{"Mạng cho phép?"}
    B -->|Không| X["TCP bị từ chối"]
    B -->|Có| C{"TLS và certificate hợp lệ?"}
    C -->|Không| Y["TLS handshake thất bại"]
    C -->|Có| D{"Redis AUTH hợp lệ?"}
    D -->|Không| Z["NOAUTH / WRONGPASS"]
    D -->|Có| E{"Redis ACL cho phép lệnh/key?"}
    E -->|Có| F["GET/SET thành công"]
    E -->|Không| G["NOPERM"]
~~~

TLS bảo vệ đường truyền, ACL kiểm soát hành động, còn firewall ngăn những nguồn không được phép bắt đầu kết nối. Cần kết hợp cả ba. Một client dùng TLS nhưng có quyền `+@all` vẫn có thể xóa mọi dữ liệu; ngược lại, ACL chặt mà kết nối plaintext vẫn có nguy cơ lộ credential.

## 3. SSL/TLS ở Redis Server

### 3.1. Mã hóa kết nối và xác minh máy chủ

TLS mã hóa luồng trao đổi và cho phép client xác minh certificate server do một CA tin cậy cấp, có tên DNS/SAN phù hợp với endpoint thực tế. Redis OSS phải được build/cung cấp với hỗ trợ TLS. Việc bật TLS **không tự tắt cổng TCP plaintext**; người vận hành phải kiểm tra cấu hình và các cổng đang lắng nghe.

Ví dụ một phần `redis.conf` cho hệ thống tự quản lý:

~~~conf
# Chỉ bind vào private interface thực tế của server.
bind 10.10.1.12
protected-mode yes

# Tắt cổng TCP không mã hóa; mở TLS trên cổng ví dụ 6380.
port 0
tls-port 6380
tls-cert-file /etc/redis/tls/server.crt
tls-key-file /etc/redis/tls/server.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# TLS một chiều: server gửi certificate để client xác minh.
# Không bắt buộc client certificate; AUTH/ACL cấu hình riêng.
tls-auth-clients no
~~~

`10.10.1.12` và `6380` là giá trị minh họa, không phải IP/cổng mặc định bắt buộc; Redis managed service có thể dùng endpoint và cổng khác. Firewall/NetworkPolicy phải giới hạn nguồn truy cập thực tế. `protected-mode` là lớp dự phòng, không thay thế chính sách mạng.

**Cấu hình TLS trên chưa tự bật Redis authentication.** Một Redis mới có thể vẫn cho user `default` đăng nhập không cần mật khẩu với quyền rộng. Phải cấu hình user ACL riêng như phần sau, tạo và kiểm thử tài khoản quản trị dự phòng, rồi giới hạn/vô hiệu hóa user `default` theo kế hoạch; persist ACL bằng cơ chế được triển khai hỗ trợ. Nếu bỏ qua bước này, client không có credential vẫn có thể được quyền truy cập dù cổng đang dùng TLS.

Nếu dùng **mutual TLS (mTLS)**, Redis server có thể cấu hình `tls-auth-clients yes` và phía client phải cung cấp certificate + private key được CA chấp nhận. mTLS là xác thực ở lớp TLS; ứng dụng vẫn cần chính sách `AUTH`/ACL tương ứng. Không đưa private key TLS vào repository hay Docker image công khai; nên mount qua hệ thống secret, đặt quyền file hạn chế và quản lý thay chứng chỉ.

Nếu Redis dùng Cluster/replication qua TLS, còn phải kiểm tra `tls-cluster yes`, `tls-replication yes`, đường truyền nội bộ và certificate ở các endpoint tương ứng. Bảo vệ riêng kết nối Spring Boot → Redis không mặc nhiên bảo vệ các đường giữa các node.

### 3.2. Kiểm tra bằng Redis CLI

Khi mạng đã cho phép và `redis-cli` hỗ trợ TLS:

~~~bash
redis-cli --tls \
  -h redis.internal.example \
  -p 6380 \
  --cacert /run/secrets/redis/ca.crt \
  --user order-cache \
  --askpass
~~~

`--askpass` yêu cầu nhập mật khẩu tương tác; cách này tránh đưa mật khẩu trực tiếp vào đối số dòng lệnh. Nếu server yêu cầu mTLS, thêm `--cert /run/secrets/redis/client.crt --key /run/secrets/redis/client.key`. Không bỏ xác minh CA hoặc hostname chỉ để “cho kết nối chạy được”: điều đó làm mất khả năng phát hiện máy chủ giả mạo.

Sau khi đăng nhập, có thể thử `PING` và lệnh dữ liệu đã được ACL cho phép. Cần phân biệt:

- `Connection refused` hoặc timeout: DNS, network route, firewall, service/port hoặc Redis chưa sẵn sàng.
- TLS handshake/certificate verify failed: CA không đúng, chain thiếu, certificate hết hạn, hostname không khớp hoặc thiếu client certificate khi có mTLS.
- `WRONGPASS`/`NOAUTH`: Redis yêu cầu đăng nhập hoặc username/password không hợp lệ.
- `NOPERM`: đã xác thực nhưng bị ACL từ chối command, key hoặc channel.

## 4. Redis ACL: tạo user có quyền tối thiểu

### 4.1. Redis ACL khác gì requirepass?

Với Redis 6+, **Access Control Lists (ACL)** cho phép nhiều user độc lập, mỗi user có mật khẩu, trạng thái `on/off`, quyền command và mẫu key/channel. Cơ chế `requirepass` truyền thống tương ứng cách bảo vệ user `default` và không tạo sự tách biệt theo từng dịch vụ.

Ví dụ quyền đề xuất:

| User Redis | Vai trò | Key namespace | Quyền dữ liệu |
| --- | --- | --- | --- |
| `order-cache` | Cache trạng thái đơn | `integration:orders:*` | `GET`, `SET`, một số lệnh TTL thực sự dùng |
| `order-dedup` | Chống trùng webhook tạm thời | `integration:dedup:*` | `SET NX EX`, lệnh đọc/TTL khi cần |
| `order-reader` | Dịch vụ chỉ đọc | `integration:orders:*` | `GET`, `MGET` |
| `redis-admin` | Quản trị Redis | Theo chính sách vận hành | Được cấp riêng, không dùng làm runtime user |

Đăng nhập bằng tài khoản quản trị Redis, rồi chạy trong **phiên redis-cli tương tác**:

~~~redis
ACL SETUSER order-cache reset on >REPLACE_WITH_LONG_RANDOM_SECRET ~integration:orders:* +get +set +del +pttl +ping +hello
~~~

Ý nghĩa:

- `reset` xóa quyền/mật khẩu/pattern cũ của user rồi thiết lập lại; chỉ dùng khi chủ động tái cấu hình vì nó có thể ảnh hưởng client đang chạy.
- `on` bật user; `>...` thêm mật khẩu. Mật khẩu mẫu bắt buộc thay bằng secret đủ dài, ngẫu nhiên.
- `~integration:orders:*` giới hạn các key được thao tác.
- `+get +set +del +pttl` cấp lệnh dữ liệu; `+ping +hello` là ví dụ lệnh phục vụ kết nối. Các lệnh còn lại không được cấp sau `reset`.

Ký tự `>` trong cú pháp Redis ACL có thể bị shell hiểu là toán tử chuyển hướng nếu gõ nguyên lệnh vào terminal hệ điều hành. Dùng phiên Redis CLI tương tác, file ACL được quản lý an toàn hoặc công cụ provisioning thích hợp; tránh ghi mật khẩu vào command history, CI log hoặc Git.

Danh sách lệnh trên là **điểm bắt đầu** cho adapter dùng GET/SET; nó chưa chắc đủ cho mọi phiên bản Lettuce, health check, `RedisCacheManager` hay cluster client. Một số client thực hiện thêm `CLIENT SETNAME`/`CLIENT SETINFO`, `SELECT` hoặc `INFO`. Khi gặp `NOPERM`, xác minh command thực tế và chỉ cấp quyền tối thiểu cần thiết, không cấp `+@all` như một cách sửa lỗi mặc định.

Tài khoản chỉ đọc có thể bắt đầu với:

~~~redis
ACL SETUSER order-reader reset on >REPLACE_WITH_ANOTHER_SECRET ~integration:orders:* +get +mget +pttl +ping +hello
~~~

Nếu tài khoản không có quyền `SET`/`DEL`, Redis sẽ từ chối các lệnh ghi ấy. Với các command khác, hành vi được quyết định bởi ACL cụ thể; không suy luận “read-only” từ tên user.

### 4.2. Key pattern, command và Pub/Sub channel

| Cú pháp ACL | Ví dụ | Mục đích |
| --- | --- | --- |
| Key pattern | `~integration:orders:*` | Giới hạn tên key |
| Command cụ thể | `+get +set` | Chỉ cấp command cần dùng |
| Command category | `+@read`, `+@write` | Cấp nhóm command; có thể rộng hơn cần thiết |
| Channel pattern | `&integration:events:*` | Giới hạn channel khi dùng Pub/Sub |
| Lệnh quản trị | `FLUSHALL`, `FLUSHDB`, `CONFIG`, `ACL` | Không cấp cho user ứng dụng thông thường |

`~...` giới hạn **key**, không tự hạn chế **Pub/Sub channel**. Khi dùng `PUBLISH`/`SUBSCRIBE` cần đánh giá thêm quyền command và mẫu channel `&...`. Redis phiên bản hỗ trợ có thể phân biệt key pattern chỉ đọc/chỉ ghi bằng cú pháp như `%R~` và `%W~`; kiểm tra version server trước khi triển khai.

Nếu ứng dụng sử dụng Redis Streams, Lua script, RedisJSON, Redis Search hoặc Spring Cache với cơ chế xóa theo pattern, tập command cần thiết khác GET/SET đơn giản. Thiết kế ACL dựa trên các thao tác thực tế, rồi kiểm thử với cùng client mà Spring Boot sử dụng.

**Redis ACL không phải authorization cho người dùng cuối.** Một API nhận `tenantId` từ query string rồi tạo key `integration:orders:<tenantId>:...` vẫn có thể truy cập nhầm tenant khác trong cùng pattern. Lấy tenant từ security context đã xác thực, kiểm tra quyền nghiệp vụ và chuẩn hóa key; không cấp Redis credential trực tiếp cho browser/mobile client.

## 5. Cấu hình Spring Boot và truy cập Redis an toàn

### 5.1. Spring Data Redis với Lettuce

~~~kotlin
// build.gradle.kts — ví dụ Spring Boot 3.x
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Spring Boot 3.x thường sử dụng Lettuce làm Redis client mặc định. Với máy chủ có certificate được CA mặc định tin cậy:

~~~yaml
# application.yml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 3s
      timeout: 2s
~~~

Các placeholder `${REDIS_USERNAME}` và `${REDIS_PASSWORD}` yêu cầu Spring lấy username/password từ biến môi trường tương ứng. Không lưu mật khẩu cố định trong file cấu hình được commit hoặc trong URL xuất hiện ở log.

Với **CA riêng**, Spring Boot 3.1+ hỗ trợ SSL bundles; cách cấu hình cần đối chiếu với phiên bản Boot đang dùng:

~~~yaml
# Cấu hình thay thế ví dụ phía trên khi cần CA riêng
spring:
  ssl:
    bundle:
      pem:
        redis-client:
          truststore:
            certificate: file:/run/secrets/redis/ca.crt
  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
        bundle: redis-client
~~~

Certificate CA phải có trong môi trường runtime đúng đường dẫn và trust chain. Với mTLS, SSL bundle cần bổ sung client certificate/private key theo cơ chế hỗ trợ của phiên bản. Nếu tự tạo `LettuceConnectionFactory`, Spring Boot properties có thể không tự áp vào factory đó; phải cấu hình và xác minh client thực tế. Tương tự, nếu dùng URL `rediss://...`, kiểm tra quy tắc ưu tiên cấu hình và tránh ghi mật khẩu trong URI.

Không tạo custom trust manager “tin mọi certificate” để vượt qua lỗi handshake. Cấu hình đó vô hiệu hóa xác minh danh tính server, dù traffic vẫn mang định dạng TLS.

### 5.2. Ví dụ adapter chỉ dùng GET/SET trên namespace được cấp

~~~java
// OrderCacheAdapter.java
import java.time.Duration;
import java.util.regex.Pattern;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderCacheAdapter {
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private final StringRedisTemplate redis;

    public OrderCacheAdapter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStatus(String tenantId, String orderId, String status) {
        redis.opsForValue().set(key(tenantId, orderId),
                status, Duration.ofMinutes(10));
    }

    public String getStatus(String tenantId, String orderId) {
        return redis.opsForValue().get(key(tenantId, orderId));
    }

    private String key(String tenantId, String orderId) {
        if (!SAFE_ID.matcher(tenantId).matches()
                || !SAFE_ID.matcher(orderId).matches()) {
            throw new IllegalArgumentException("Invalid key component");
        }
        return "integration:orders:" + tenantId + ":" + orderId;
    }
}
~~~

`putStatus` sử dụng `SET` có TTL; `getStatus` dùng `GET`. Redis ACL mẫu cho phép cả hai trên `integration:orders:*`. Regex tránh thành phần key chứa ký tự phân cách không dự kiến; **nó không kiểm tra quyền tenant**. `tenantId` phải lấy từ danh tính/ngữ cảnh đã xác thực và đối chiếu chính sách nghiệp vụ.

Nếu Redis là cache, một `GET` trả `null` có thể chỉ ra key chưa tồn tại/hết hạn. Không được âm thầm coi `NOPERM`, TLS handshake lỗi hoặc timeout là “cache miss”: các lỗi ấy cần log, metric và fallback theo thiết kế.

Nếu Redis được dùng để chống trùng webhook, `SET key value NX EX seconds` giúp tạo marker có TTL một cách nguyên tử **trong Redis**. Tuy nhiên marker và việc commit database/ack broker không cùng một giao dịch; crash có thể để lại hiệu ứng nghiệp vụ thiếu hoặc trùng. Với yêu cầu đúng một hiệu ứng bền vững, cân nhắc inbox/unique constraint ở database và quy tắc replay rõ ràng.

## 6. Giới hạn truy cập mạng và topology Redis

### Standalone, Sentinel, Cluster và managed service

| Topology | Điểm cần kiểm tra về TLS và quyền |
| --- | --- |
| **Standalone** | Endpoint private, cổng TLS, user ACL, CA trust, firewall/NetworkPolicy |
| **Sentinel** | Client có thể kết nối tới Sentinel và Redis data node; xác thực và TLS của các endpoint này cần được xét riêng |
| **Redis Cluster** | Client nhận redirect đến các node khác; mọi node mà client truy cập phải có DNS/certificate/ACL/network hợp lệ |
| **Managed Redis** | Theo tài liệu nhà cung cấp về TLS endpoint, user/ACL, xoay vòng mật khẩu và cấu hình mạng; không mặc định cổng 6379 hay 6380 |

Với Redis Cluster, cho phép mạng từ Spring Boot đến seed node **chưa chắc đủ**. Sau khi nhận `MOVED`/`ASK`, client có thể mở kết nối mới đến node khác. Chứng chỉ phải hợp lệ cho endpoint mà client sử dụng, ACL phải được triển khai đồng nhất theo cơ chế quản trị cluster. Không “chữa” lỗi redirect bằng cách mở toàn bộ subnet rộng hơn cần thiết.

Trong Redis Sentinel, cấu hình xác thực Sentinel và Redis data server có thể khác nhau; chỉ khai báo một bộ mật khẩu trong Spring Boot khi topology thực sự dùng chung như vậy. Với multi-tenant, cân nhắc tách Redis user/prefix theo dịch vụ hoặc ranh giới dữ liệu, và kiểm tra quyền tenant tại backend.

### Secret management và xoay vòng

Một mật khẩu mạnh vẫn có thể bị lộ qua log, file cấu hình, history hoặc môi trường CI nếu quản lý sai. Vòng đời credential nên bao gồm:

1. Tạo user ACL và secret bằng pipeline/quy trình quản trị có quyền giới hạn; không gửi mật khẩu qua chat, ticket công khai hay source repository.
2. Phân tách credential cho development, staging, production; tách account vận hành và account runtime.
3. Cấp credential qua secret manager, volume được bảo vệ hoặc biến môi trường do nền tảng kiểm soát; che giá trị secret trong log.
4. Khi rotation, có thể bổ sung mật khẩu mới cho cùng user Redis ACL nếu server hỗ trợ, cập nhật client và connection pool, sau đó thu hồi mật khẩu cũ. Lập kế hoạch rollback nếu deployment không thể kết nối.
5. Theo dõi certificate hết hạn, thay CA/certificate, kết nối mới sau rotation và tỷ lệ `WRONGPASS`/`NOPERM`.

Không tắt user `default` trước khi đã có tài khoản quản trị được kiểm thử và đường khôi phục. Với Redis tự quản lý, các thay đổi qua `ACL SETUSER` cần được lưu bền vững đúng cơ chế cấu hình (ví dụ ACL file/`ACL SAVE` khi phù hợp); nếu không, restart có thể làm cấu hình quay về trạng thái trước. Không đặt tài khoản ứng dụng vào nhóm lệnh quản trị chỉ để nó tự quản lý credential.

`maxclients`, connection pool và timeout giúp giới hạn tài nguyên, **không phải authorization theo tenant**. Redis không nên là cổng truy cập trực tiếp từ trình duyệt/mobile client; backend giữ credential Redis và thực hiện kiểm soát quyền nghiệp vụ.

## 7. Kiểm tra ACL và TLS mà không tác động dữ liệu thật

### 7.1. Dùng ACL DRYRUN để kiểm tra quyền

Redis 7+ có `ACL DRYRUN` cho phép **tài khoản quản trị** đánh giá xem một user có quyền chạy command với tham số đã cho mà không thực thi command đó. Trong phiên quản trị Redis:

~~~redis
ACL DRYRUN order-cache GET integration:orders:tenant-42:ORD-1001
ACL DRYRUN order-cache SET integration:orders:tenant-42:ORD-1001 PAID
ACL DRYRUN order-cache GET private:payroll:employee-7
ACL DRYRUN order-cache FLUSHALL
~~~

Theo rule `order-cache` mẫu, hai trường hợp đầu được phép, hai trường hợp sau phải bị từ chối. **Không chạy `FLUSHALL` thật** để kiểm thử quyền. `ACL DRYRUN` kiểm tra ACL, không chứng minh server certificate hợp lệ, firewall đúng hay Spring Boot dùng đúng kết nối.

Các lệnh `ACL GETUSER`, `ACL LOG` có thể giúp người vận hành kiểm tra user và nguyên nhân bị từ chối; chỉ cấp quyền này cho tài khoản phù hợp. Sau khi nâng cấp Lettuce/Spring Data Redis, ACL log có thể cho biết client mới gọi thêm `CLIENT SETINFO`, `HELLO` hoặc command phục vụ health check. Hãy đánh giá lệnh mới trước khi bổ sung vào whitelist.

### 7.2. Ma trận kiểm thử tích hợp

| Tình huống thử nghiệm | Kết quả cần xác minh |
| --- | --- |
| Đúng CA, hostname, user và password | Spring Boot kết nối TLS, `GET`/`SET` trên prefix được phép thành công |
| CA không tin cậy hoặc DNS/SAN certificate không khớp | TLS handshake thất bại; không fallback sang plaintext |
| Username/password sai | Redis từ chối xác thực, không thực thi command dữ liệu |
| `order-reader` gọi `SET` | `NOPERM` cho command ghi |
| `order-cache` gọi `GET private:payroll:*` | `NOPERM` do key pattern |
| Kết nối từ IP/pod không thuộc allowlist | Không tạo phiên TCP đến Redis |
| Mật khẩu cũ bị thu hồi sau rotation | Connection mới với mật khẩu cũ không được chấp nhận |
| Failover sang Redis node khác | Kết nối TLS/ACL vẫn đúng trên endpoint mới |
| Redis client/Boot được nâng cấp | Không xuất hiện command `NOPERM` ngoài ý muốn; không mở rộng quyền quá mức |

Nên kiểm thử qua **cùng `LettuceConnectionFactory` hoặc Spring Data Redis client** được dùng khi chạy production. `redis-cli` thành công chưa chứng minh Spring Boot đã lấy đúng SSL bundle, secrets, hostname hay các command tự động lúc khởi tạo kết nối.

Kiểm thử đơn vị việc xây key không thay thế kiểm thử TLS thực, xác thực và Redis ACL trên server. Có thể dùng môi trường tích hợp riêng hoặc Redis container được cấu hình TLS/ACL tương đương; tránh thực hiện kiểm thử lệnh xóa hoặc giả lập lộ credential trên production.

## 8. Gỡ lỗi lỗi kết nối, quyền và thay đổi sau nâng cấp

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
| --- | --- | --- |
| `Connection refused` hoặc timeout kết nối | Sai hostname/port, DNS, firewall, Redis chưa ready | Kiểm tra endpoint, mạng, service readiness; không mở Redis công khai |
| `SSLHandshakeException`, certificate verify failed | CA/chain/SAN không hợp lệ, hết hạn cert, client cert thiếu khi mTLS | Cập nhật CA/cert phù hợp; giữ xác minh TLS |
| `WRONGPASS invalid username-password pair` | Sai user/password, user `off`, rotation chưa đồng bộ | Kiểm tra secret và user ACL trên server |
| `NOAUTH Authentication required` | Client không gửi authentication hợp lệ | Xem property binding và connection factory thực tế |
| `NOPERM this user has no permissions to run command` | Command nằm ngoài whitelist (có thể là health check, cache clear, handshake) | Dùng `ACL LOG` để xác định command, cấp quyền tối thiểu |
| `NOPERM ... access one of the keys ...` | Key prefix không khớp hoặc tên key không đúng serializer/policy | Đối chiếu key thực tế và ACL pattern |
| Chạy được trên CLI, lỗi trong ứng dụng | CLI và Java client dùng CA/cert/endpoint/credential khác nhau | Kiểm tra Spring config, SSL bundle, factory được inject |
| Standalone chạy được nhưng Cluster lỗi | Redirect tới node chưa mở mạng hoặc certificate/ACL khác | Kiểm tra từng endpoint trong cluster |
| Từ khi nâng cấp client mới xuất hiện `NOPERM` | Lettuce hoặc Spring Data gọi thêm command | So sánh ACL log, release notes và command thực tế |
| Redis không thấy cache nhưng không báo lỗi | TTL, key prefix, database, serializer hoặc nhầm môi trường | Kiểm tra logic GET/SET, thời hạn và cấu hình client |

**Phân biệt nhanh:** `WRONGPASS`/`NOAUTH` liên quan authentication, `NOPERM` liên quan authorization, còn TLS handshake thất bại xảy ra trước Redis ACL. Không nên giải quyết lỗi chứng chỉ bằng cách thêm `+@all`, hoặc giải quyết lỗi ACL bằng cách tắt TLS.

Khi ghi log, chỉ lưu thông tin cần thiết như service, hostname không kèm secret, tên user theo chính sách nội bộ, command bị từ chối, latency, correlation ID và loại lỗi. Tránh in URL Redis có password, đầy đủ payload hoặc key chứa thông tin cá nhân. `/actuator/health` của Spring Boot cũng có thể cần command kiểm tra Redis; nếu ACL chặn health command, điều chỉnh health contributor hoặc cấp đúng quyền sau khi đánh giá.

## 9. Ghép các lớp bảo vệ vào luồng tích hợp đơn hàng

Giả sử Spring Boot nhận webhook thanh toán, ghi PostgreSQL và dùng Redis cache giúp truy vấn nhanh:

~~~text
Partner webhook
      |
      v
Spring Boot (validate input, authenticate tenant, transaction)
      |
      +---> PostgreSQL: nguồn dữ liệu đơn hàng
      |
      +---> Redis TLS endpoint: redis.internal.example:6380
                |
                +-- ACL user: order-cache
                +-- Key prefix: integration:orders:*
                +-- GET/SET theo policy, TTL 10 phút
                +-- Kết nối từ private application network
~~~

Các quyết định vận hành:

1. **Network:** Redis chỉ lắng nghe private interface và cổng TLS; firewall chỉ cho phép các workload cần thiết.
2. **TLS:** client xác minh certificate server qua CA; nếu dùng mTLS thì client có certificate/key hợp lệ.
3. **Authentication/ACL:** `order-cache` có credential riêng cho môi trường và chỉ thao tác trên `integration:orders:*` bằng các lệnh đã kiểm thử.
4. **App authorization:** `tenantId` được lấy từ ngữ cảnh đã xác thực; không dùng giá trị tenant từ request tùy ý để đọc cache của tenant khác.
5. **Data consistency:** PostgreSQL là nguồn chân lý; lỗi ghi/invalidate Redis sau DB commit được xử lý bằng fallback/invalidation/retry có kiểm soát. TLS/ACL không biến Redis + PostgreSQL thành một transaction nguyên tử.
6. **Observability:** theo dõi timeout, latency, lỗi TLS, `WRONGPASS`, `NOPERM`, certificate expiry và các lỗi phát sinh sau nâng cấp.

Nếu Redis dùng làm nơi đánh dấu idempotency cho thông điệp HTTP/Kafka/RabbitMQ, cần xem thêm cửa sổ TTL và khôi phục sau crash. ACL bảo vệ marker khỏi những user ngoài quyền, nhưng không tự bảo đảm exactly-once xuyên broker, database và Redis.

## 10. Câu hỏi tự kiểm tra

**1. Đã có Redis password thì tại sao cần TLS?** Password xác thực client, còn TLS mã hóa đường truyền và xác minh server; hai mục tiêu khác nhau.

**2. `spring.data.redis.ssl.enabled=true` có giới hạn được lệnh Redis không?** Không. Phải cấu hình Redis ACL riêng.

**3. Redis ACL `~integration:orders:*` có thay thế kiểm tra quyền tenant không?** Không. Nó chỉ giới hạn key theo user Redis, không biết ai là người dùng HTTP cuối cùng.

**4. Mật khẩu đúng nhưng `SET` trả `NOPERM`, nguyên nhân là gì?** User đã đăng nhập nhưng ACL không cho phép `SET` hoặc không cho phép key tương ứng.

**5. Tại sao không nên cấp `+@all` khi nâng cấp client làm xuất hiện `NOPERM`?** Vì tạo quyền vượt nhu cầu; nên tìm command thật, đánh giá và chỉ mở quyền tối thiểu.

**6. Nếu Redis Cluster chuyển client sang node khác, có cần certificate/ACL trên node đó không?** Có. Client phải tiếp tục kết nối an toàn tới những node có thể được truy cập.

**7. Có thể đặt mật khẩu thẳng trong `application.yml` rồi cho rằng TLS đã bảo vệ đủ không?** Không. TLS bảo vệ trên đường truyền; bí mật trong Git, artifact hoặc log vẫn có thể bị lộ.

**8. Cache Redis đã ghi thành công có bảo đảm transaction PostgreSQL thành công không?** Không; chúng có ranh giới commit khác nhau, cần chiến lược cập nhật/invalidate phù hợp.

Một kết nối Redis an toàn trong Spring Boot Integration phải đồng thời thỏa **mạng giới hạn, TLS có xác minh danh tính, authentication bằng user riêng và ACL chỉ cho phép command/key/channel cần dùng**. Những bảo đảm đó cần được kiểm chứng bằng hành vi thực tế của ứng dụng và theo dõi liên tục khi Redis hoặc thư viện client thay đổi.
