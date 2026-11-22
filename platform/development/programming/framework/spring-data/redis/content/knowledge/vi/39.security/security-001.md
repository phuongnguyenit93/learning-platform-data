# Giới hạn truy cập mạng và bảo vệ Redis khỏi Internet công cộng

**Redis không nên được đặt trực tiếp trên Internet công cộng.** Trong ứng dụng Spring Data Redis, Redis có thể chứa cache, phiên đăng nhập, token tạm, rate-limit counters, hàng đợi, trạng thái nghiệp vụ và dữ liệu được nhiều dịch vụ cùng sử dụng. Một cổng Redis lộ ra ngoài không chỉ khiến dữ liệu có nguy cơ bị đọc trái phép, mà còn tạo cơ hội cho hành vi ghi/xóa dữ liệu hoặc làm gián đoạn hệ thống nếu các lớp bảo vệ không đầy đủ.

Bảo vệ Redis cần bắt đầu từ **ranh giới mạng**: chỉ những ứng dụng, worker và công cụ quản trị được phép mới có đường mạng tới Redis. Sau đó mới đến **TLS để bảo vệ đường truyền**, **Redis ACL để giới hạn danh tính và lệnh**, **quản lý secret**, và **giám sát/kiểm thử khả năng truy cập**.

Trong hệ sinh thái **Spring Data Redis**, cấu hình kết nối bằng `LettuceConnectionFactory`, `RedisTemplate` hoặc `ReactiveRedisTemplate` chỉ là tầng client. Không thể làm Redis an toàn bằng một annotation Java nếu hạ tầng vẫn công khai cổng Redis cho mọi địa chỉ IP.

Mục tiêu của bài học là thiết kế một mô hình bảo vệ theo nhiều lớp, nhận diện các lỗi triển khai phổ biến và có một quy trình xác minh cụ thể trước khi vận hành.

## 1. Vì sao Redis có rủi ro cao khi mở ra Internet?

Redis là hệ thống dữ liệu hiệu năng cao, thường được ứng dụng truy cập trực tiếp bằng giao thức Redis. Redis không phải một HTTP application gateway có cơ chế kiểm soát truy cập theo người dùng cuối được thiết kế sẵn cho mọi nghiệp vụ.

Nếu endpoint Redis bị lộ ra mạng công cộng, các hậu quả có thể bao gồm:

- Đọc các key chứa dữ liệu cache, session hoặc thông tin nội bộ nếu quyền truy cập không được giới hạn.
- Ghi đè hoặc xóa dữ liệu, phá hoại cache, session và trạng thái được dùng bởi ứng dụng.
- Gây áp lực CPU, RAM, network hoặc connection count dẫn tới từ chối dịch vụ.
- Thực thi các lệnh quản trị nguy hiểm nếu tài khoản được cấp quyền quá rộng.
- Khai thác cấu hình sai về authentication, ACL, TLS, replication hoặc module.
- Dùng quyền truy cập dữ liệu đã chiếm được để làm ảnh hưởng tới các dịch vụ phụ thuộc Redis.

Điều này vẫn quan trọng nếu Redis “chỉ để cache”. Một cache không phải nguồn sự thật có thể bị đầu độc bằng giá trị sai, làm ứng dụng phục vụ dữ liệu giả hoặc dồn toàn bộ tải về database khi bị xóa hàng loạt.

**Không mở cổng Redis cho Internet chỉ vì đã thiết lập password.** Password giúp nhận diện client, nhưng không thay thế firewall, network segmentation, TLS và least privilege.

## 2. Kiến trúc bảo vệ nhiều lớp

Một triển khai phù hợp nên có ít nhất những ranh giới sau:

```text
                   Internet công cộng
                           |
                           v
                    Load Balancer/WAF
                           |
                      HTTPS (443)
                           |
                           v
                  Spring Boot API tier
                           |
                   Private networking
                           |
                  Chỉ source được phép
                           |
                           v
                 Firewall/Security Group
                           |
                       TLS + ACL
                           |
                           v
                    Redis private
                           |
                      Replica(s)
                  (chỉ mạng nội bộ)
```

Trong mô hình này:

1. Browser chỉ có thể truy cập HTTP/API gateway theo chính sách.
2. Redis không có địa chỉ hoặc endpoint công khai được định tuyến trực tiếp từ Internet.
3. Firewall chỉ cho phép ứng dụng được chỉ định truy cập cổng Redis.
4. Redis xác thực client, giới hạn key và lệnh theo vai trò.
5. TLS giúp bảo mật dữ liệu và thông tin xác thực khi truyền qua mạng.
6. Redis primary/replica, Sentinel hoặc Cluster dùng các kênh nội bộ riêng và có quyền cần thiết.
7. Hệ thống có log/metric để phát hiện truy cập bất thường và sai cấu hình.

Một hệ thống bảo vệ tốt phải chịu được việc **một lớp gặp lỗi** mà không lập tức công khai dữ liệu. Ví dụ, nếu một rule firewall được cấu hình quá rộng, ACL và TLS vẫn là lớp bảo vệ bổ sung; nhưng không được dùng chúng làm lý do duy trì rule firewall sai.

## 3. Phân biệt các lớp bảo mật

| Lớp | Câu hỏi được trả lời | Không thể thay thế |
|---|---|---|
| **Mạng riêng/VPC** | Client có đường mạng tới Redis không? | Không xác thực lệnh và người dùng |
| **Firewall/Security Group** | Source nào được kết nối tới cổng nào? | Không kiểm tra nội dung thao tác Redis |
| **Redis bind** | Redis lắng nghe trên interface nào? | Không tự tạo policy theo từng client |
| **Protected mode** | Giúp ngăn một số cấu hình Redis không an toàn | Không thay thế firewall, ACL hoặc TLS |
| **TLS** | Đường truyền có được mã hóa và xác minh server không? | Không tự phân quyền Redis command |
| **Redis ACL** | User có thể truy cập key và command nào? | Không ngăn việc endpoint bị quét/DoS ở tầng mạng |
| **Spring Security** | Người dùng HTTP nào được gọi API? | Không thay thế Redis ACL và network boundary |
| **Secret management** | Password/certificate được lưu, cấp và xoay vòng ra sao? | Không sửa được cổng Redis công khai |
| **Monitoring/Audit** | Có dấu hiệu truy cập sai hoặc thay đổi bất thường không? | Không ngăn sự cố nếu chỉ quan sát |

Các lớp bảo vệ nên được thiết kế độc lập nhưng nhất quán. Một user được phép gọi `GET /products/42` trên API không có nghĩa client đó được quyền kết nối trực tiếp tới Redis.

## 4. Mô hình đe dọa trước khi viết cấu hình

Trước khi quyết định firewall và ACL, xác định các nhóm client:

- Spring Boot API instance.
- Background worker hoặc scheduled job.
- Công cụ migration/maintenance có quyền hạn cao hơn.
- Monitoring/health-check component.
- Redis primary và replica.
- Sentinel hoặc Cluster nodes.
- Người quản trị có quyền truy cập theo quy trình.
- Những hệ thống **không được phép** kết nối, gồm người dùng Internet, container không liên quan và môi trường thử nghiệm khác.

Ví dụ ma trận:

| Nguồn | Redis data port | Lệnh/khóa cần dùng | Chính sách |
|---|---|---|---|
| Catalog API private subnet | Cho phép | GET/SET/DEL trong `cache:catalog:*` | User ACL hạn chế |
| Order worker private subnet | Cho phép | Một tập command/namespace khác | User ACL riêng |
| CI runner công cộng | Mặc định từ chối | Không truy cập production | Dùng môi trường test riêng |
| Bastion/admin host | Chỉ theo phiên/quy trình được duyệt | Vận hành có audit | Quyền tách biệt ứng dụng |
| Internet `0.0.0.0/0` và `::/0` | Từ chối | Không có | Không route trực tiếp tới Redis |
| Redis replica/Cluster node | Cho phép trong mạng nội bộ | Replication/cluster protocols | Hạn chế tới node được biết |

**Danh sách cho phép phải xuất phát từ vai trò và danh tính hạ tầng**, không phải một dải IP rất rộng được chọn chỉ để “kết nối cho tiện”.

## 5. Nguyên tắc số một: đặt Redis trong mạng riêng

Đối với hạ tầng cloud, Redis nên nằm trong:

- Private subnet/VPC hoặc mạng riêng tương đương.
- Endpoint private do dịch vụ managed Redis cung cấp.
- Kubernetes Service nội bộ, không public LoadBalancer.
- Docker network dành riêng cho ứng dụng liên quan, không publish cổng lên host công cộng.
- Mạng on-premises có firewall giữa application tier và data tier.

```text
Sai:
Browser/Internet ---- TCP 6379 ----> Redis public IP

Đúng hơn:
Browser/Internet ---- HTTPS 443 ----> API
                                      |
                                 Private route
                                      |
                                      v
                                Redis private IP
```

Ứng dụng chạy ở vùng mạng khác cần kết nối riêng có kiểm soát, chẳng hạn VPN/site-to-site, VPC peering, private networking hoặc một cơ chế private endpoint phù hợp. Không dùng việc mở Redis ra Internet như giải pháp mặc định cho kết nối giữa hai môi trường.

### 5.1. Private IP là điều kiện cần, chưa phải điều kiện đủ

Việc Redis có địa chỉ RFC 1918 không tự xác nhận rằng nó được bảo vệ:

- Có thể có VPN hoặc network peering kết nối quá nhiều mạng.
- Một subnet có thể chứa nhiều workload không đáng tin.
- Reverse proxy/tunnel hoặc port-forward có thể vô tình mở Redis ra ngoài.
- Docker/Kubernetes ingress/Service có thể publish traffic tới Redis.
- Một container bị chiếm quyền trong cùng mạng có thể thử kết nối tới Redis.

Vì vậy, ngoài private IP còn cần **firewall allowlist theo nguồn** và Redis ACL.

### 5.2. Cần kiểm tra cả IPv4 và IPv6

Một firewall chỉ chặn `0.0.0.0/0` nhưng để mở `::/0` có thể vẫn làm endpoint lộ qua IPv6. Redis có thể lắng nghe IPv4, IPv6 hoặc cả hai tùy cấu hình bind và hệ điều hành.

Khi rà soát:

- Kiểm tra public IPv4 và public IPv6.
- Kiểm tra IPv6 inbound rules.
- Kiểm tra Kubernetes/Load Balancer dual-stack nếu có.
- Không suy luận rằng một cổng không truy cập được bằng IPv4 thì chắc chắn không truy cập được từ Internet.

## 6. Firewall và Security Group: chỉ mở nguồn thật sự cần

Giả sử API chạy trong private subnet và Redis lắng nghe ở cổng 6379. Chính sách nên có dạng:

```text
Destination: Redis private endpoint
Protocol: TCP
Destination port: 6379
Allowed source: API security group / workload identity
Everything else: deny
```

Trên cloud hỗ trợ security group reference, thường nên cho phép **source security group của ứng dụng** thay vì một dải CIDR rộng như toàn VPC. Cách này bám sát membership của workload khi instance được tăng/giảm.

Ví dụ chính sách logic:

| Rule | Source | Destination | Port | Hành động |
|---|---|---|---:|---|
| Inbound Redis | Catalog API group | Redis endpoint | TCP 6379 | Allow |
| Inbound Redis | Order worker group | Redis endpoint | TCP 6379 | Allow nếu cần |
| Inbound Redis | Admin/bastion đã kiểm soát | Redis endpoint | TCP 6379 | Allow theo quy trình |
| Inbound Redis | Internet và mạng khác | Redis endpoint | TCP 6379 | Deny |
| HTTP public | Internet | API load balancer | TCP 443 | Allow theo WAF/API policy |

Đối với firewall stateful, response traffic của kết nối đã được cho phép thường được xử lý theo state. Với Network ACL stateless, cần xét cả chiều đi/về và ephemeral ports. Không đơn giản sao chép rule của security group sang một loại firewall khác mà bỏ qua statefulness.

### 6.1. Chỉ mở cổng thực tế cần dùng

Cổng Redis mặc định thường là `6379`, nhưng dịch vụ managed Redis, TLS endpoint hoặc triển khai tùy chỉnh có thể dùng cổng khác. Không suy luận mọi Redis TLS đều dùng `6380`; phải kiểm tra endpoint của môi trường thực.

Các port liên quan trong kiến trúc lớn hơn:

| Thành phần | Cổng thường gặp | Nguyên tắc |
|---|---:|---|
| Redis data service | 6379 mặc định | Chỉ application/worker được phép |
| Redis TLS data service | Do cấu hình quyết định | Chỉ mạng riêng; cần TLS thật |
| Redis Sentinel | 26379 mặc định | Chỉ client Sentinel/Redis nodes được phép |
| Redis Cluster bus | Thường data port + 10000 | Chỉ giữa các Cluster nodes |
| Redis admin/metrics sidecars | Tùy deployment | Không publish công khai; cần auth và phân quyền |

**Không mở Cluster bus port hoặc Sentinel port ra Internet.** Những giao thức này phục vụ phối hợp hạ tầng, không dành cho browser hoặc client không đáng tin.

## 7. Redis bind và protected-mode: hiểu đúng phạm vi

Trong Redis server configuration, hai thiết lập thường gặp là:

- `bind`: chọn địa chỉ/interface mà Redis lắng nghe.
- `protected-mode yes`: bổ sung cơ chế bảo vệ trước một số kiểu cấu hình không an toàn.

Ví dụ Redis chỉ dùng trong một máy cho môi trường phát triển:

```conf
bind 127.0.0.1 -::1
protected-mode yes
port 6379
```

Khi chỉ bind loopback, client ở máy khác không thể kết nối trực tiếp qua IP private/public của host.

Nếu Redis phục vụ ứng dụng từ máy khác, cần bind tới **interface private phù hợp**, đồng thời dùng firewall, ACL và TLS:

```conf
# Ví dụ host có IP private thực sự được gán cho máy.
bind 10.20.30.15
protected-mode yes
port 6379
```

Địa chỉ `10.20.30.15` chỉ minh họa, phải thay bằng địa chỉ có thật ở host. Và **cấu hình này chỉ nói về interface, chưa bật TLS và ACL**; nếu dùng trong production, cần các lớp bảo vệ ở mục tiếp theo.

### 7.1. Vì sao 0.0.0.0 cần thận trọng?

```conf
bind 0.0.0.0
```

có nghĩa Redis lắng nghe trên tất cả IPv4 interfaces có liên quan trong network namespace. Nếu host/container có interface được truy cập từ Internet và firewall mở, cổng có thể bị lộ.

Trong Kubernetes, Redis pod đôi khi phải bind `0.0.0.0` **bên trong pod** để Service và những pod khác truy cập. Khi đó lớp bảo vệ phải nằm ở **ClusterIP/private network, NetworkPolicy, firewall và Redis ACL/TLS**. Không coi `0.0.0.0` trong container luôn tương đương public exposure, nhưng cũng không được xem nó là an toàn chỉ vì chạy trong container.

### 7.2. Protected mode không phải firewall

Redis protected mode có thể ngăn một số kết nối từ xa khi server thiếu cấu hình bảo vệ phù hợp, nhưng hành vi phụ thuộc bản Redis và cấu hình bind/auth thực tế. Không dùng `protected-mode yes` như lý do để:

- Mở inbound `6379` cho mọi địa chỉ IP.
- Bỏ Redis ACL/password.
- Bỏ TLS.
- Coi một Redis đang lắng nghe public interface là an toàn.
- Tắt tất cả NetworkPolicy và security groups.

**Hạn chế đường mạng là lớp bảo vệ đầu tiên; protected mode chỉ là lớp bổ sung.**

## 8. TLS: bảo vệ dữ liệu và thông tin xác thực khi truyền

Redis password hoặc ACL credential nếu truyền trên kết nối không mã hóa có thể bị lộ cho đối tượng có khả năng quan sát traffic. Redis có thể lưu dữ liệu nhạy cảm như session ID hoặc token, vì vậy đường truyền giữa app và Redis cần được bảo vệ theo threat model.

**TLS** giúp mã hóa dữ liệu trên đường truyền và, khi cấu hình đúng, cho phép client xác minh server qua certificate chain và hostname.

```text
Spring Boot / Lettuce
      |
      | TLS handshake + server certificate validation
      |
      v
Redis TLS endpoint (private network)
      |
      v
Redis ACL/commands
```

TLS **không thay thế ACL**, vì một client xác thực TLS thành công vẫn cần bị giới hạn các command/key được sử dụng.

### 8.1. Ví dụ Redis TLS-only

Ví dụ Redis server có thể được cấu hình:

```conf
# Không lắng nghe plain TCP data port.
port 0

# Cổng TLS được cấu hình rõ.
tls-port 6379

tls-cert-file /etc/redis/tls/server.crt
tls-key-file /etc/redis/tls/server.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# Ví dụ này chỉ yêu cầu client xác thực server;
# Redis ACL vẫn xác thực application user.
tls-auth-clients no

protected-mode yes
```

Đây là cấu hình minh họa phía server, chưa phải toàn bộ cấu hình triển khai. Cần:

- Bind interface phù hợp hoặc firewall giới hạn nguồn.
- Cấp phát certificate với SAN tương ứng tên host mà client kết nối.
- Bảo vệ private key và file permission.
- Định kỳ thay certificate và thử reconnect.
- Chỉ cho phép giao thức/cipher TLS đáp ứng chính sách của tổ chức.
- Bật Redis ACL cho mọi application client.

Nếu muốn **mutual TLS (mTLS)**, có thể yêu cầu client certificate bằng `tls-auth-clients yes`, đồng thời cấu hình certificate/key phía Lettuce client và trust chain tương ứng. Đừng bật mTLS trên server rồi chỉ bật `spring.data.redis.ssl.enabled` ở client mà kỳ vọng client tự có certificate.

### 8.2. Không tắt kiểm tra chứng chỉ để “sửa” kết nối

Nếu client lỗi vì certificate không khớp hostname hoặc CA chưa được trust, hãy sửa certificate/SAN, trust store hoặc endpoint. Không đưa vào production cấu hình tùy tiện bỏ certificate validation hay hostname verification.

TLS chỉ bảo vệ khỏi nhiều kiểu nghe lén/giả mạo khi client **thực sự xác minh được peer**, không phải chỉ khi socket có biểu tượng “mã hóa”.

## 9. Redis ACL: tách danh tính của ứng dụng khỏi quản trị viên

Kể từ Redis 6, ACL cho phép định nghĩa user, password, tập key pattern và command được dùng.

Một ứng dụng chỉ cần đọc catalog cache không nên có quyền:

- Xóa toàn bộ database Redis.
- Chạy lệnh cấu hình hoặc quản trị Cluster.
- Đổi ACL của Redis.
- Truy cập session hoặc key của dịch vụ khác.
- Chạy những lệnh scripting/module không có trong yêu cầu nghiệp vụ.

Ví dụ nguyên tắc cấp quyền:

```text
User: catalog-reader
Key scope: cache:catalog:*
Commands: GET, EXISTS, TTL, PTTL, PING

User: catalog-writer
Key scope: cache:catalog:*
Commands: GET, SET, DEL, EXPIRE, ...
 
User: redis-operator
Phân quyền quản trị riêng, không dùng trong API instance
```

Tên user và tập command chỉ là ví dụ. Với `RedisCacheManager`, Spring Session, Spring Data Redis Streams hoặc các cấu trúc Hash/Set/ZSet, danh sách command cần thiết có thể khác; phải quan sát **lệnh thực sự mà ứng dụng sử dụng** trước khi tạo ACL tối thiểu.

### 9.1. Ví dụ ACL minh họa

Trong Redis CLI quản trị trên môi trường kiểm soát, cú pháp rule có thể như sau:

```redis
ACL SETUSER catalog_reader on >CHANGE_TO_A_STRONG_SECRET ~cache:catalog:* +get +exists +ttl +pttl +ping
```

Ý nghĩa:

- `on`: bật user.
- `>...`: đặt password cho user.
- `~cache:catalog:*`: giới hạn các key có pattern tương ứng.
- `+get +exists +ttl +pttl +ping`: chỉ cho phép command cần thiết trong ví dụ đọc.

**Không dùng chuỗi `CHANGE_TO_A_STRONG_SECRET` như password thật** và không đưa secret thật vào shell history, source repository hoặc ticket/log. Trong hệ thống thực, password nên được tạo, phân phối và xoay vòng qua cơ chế secret management an toàn; cấu hình ACL cần được triển khai theo phương thức quản trị được chấp nhận.

Rule trên là **quyền đọc rất hẹp**, không phải ACL đủ cho mọi Spring Data Redis application. Các thao tác connection negotiation, ping, pub/sub, script, cache lock, session hoặc cluster có thể cần quyền khác theo driver/phiên bản.

### 9.2. Không tiếp tục để default user không giới hạn

Nếu hệ thống tạo các user ACL riêng nhưng vẫn để default user được truy cập không giới hạn và không cần mật khẩu, lớp ACL có thể không đạt mục tiêu.

Hãy quản lý default user theo chính sách, kiểm tra từng client đã chuyển sang user riêng trước khi tắt/giới hạn default user để tránh outage. Không nên đột ngột thay ACL trên production khi chưa thống kê ứng dụng, worker, monitoring, replication và công cụ admin đang kết nối.

### 9.3. Authentication và authorization khác nhau

- **AUTH/ACL user:** xác định client đăng nhập với danh tính Redis nào.
- **ACL key patterns:** giới hạn key mà user có thể thao tác.
- **ACL command rules:** giới hạn loại lệnh user được chạy.
- **Network policy:** giới hạn vị trí nào có thể kết nối.
- **Spring Security:** giới hạn người dùng HTTP gọi tính năng nào.

Một user ACL có password mạnh nhưng được `+@all` và `~*` trên mọi key vẫn là tài khoản rất rộng. Nếu password đó lộ từ một service, ảnh hưởng có thể lan sang toàn bộ Redis.

## 10. Spring Boot/Spring Data Redis cấu hình kết nối an toàn

Với Spring Boot dùng Spring Data Redis và Lettuce, cấu hình có thể sử dụng các thuộc tính:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 2s
```

Ví dụ này giả định:

- `REDIS_HOST` trỏ tới **private DNS name** của Redis.
- Redis server **đã bật TLS** trên port tương ứng.
- `REDIS_USERNAME` là Redis ACL user có quyền hạn tối thiểu.
- Password được cấp từ secret manager hoặc cơ chế cấu hình an toàn.
- JVM/Lettuce đã trust CA phù hợp và xác minh certificate server.
- Firewall chỉ cho phép ứng dụng được kết nối tới Redis.

Nếu Redis server không bật TLS, chỉ đặt `ssl.enabled: true` sẽ làm client không thể handshake. Ngược lại, nếu server yêu cầu TLS mà client dùng plain connection thì cũng lỗi; phải cấu hình hai phía đồng bộ.

### 10.1. Cẩn thận với URI chứa secret

Một số cấu hình dùng URI:

```text
rediss://user:password@private-redis.example.internal:6379
```

`rediss://` thường chỉ định TLS khi dùng URI phù hợp với driver. Nhưng **đặt password trong URI** có thể gây rò rỉ qua log, exception, monitoring, command line hoặc hệ thống cấu hình. Không hardcode URI có credential trong repository; nên dùng secret injection và cơ chế masking của platform.

### 10.2. Không log secret hoặc toàn bộ Redis URL

Tránh:

```java
log.info("Redis connection {}", redisUrlWithPassword);
```

Thay vào đó, log metadata đã làm sạch, ví dụ:

```text
Redis connection target:
    environment=production
    service=catalog-cache
    tls=true
    endpointClass=private
```

Không log password, token, session ID, private key hoặc dữ liệu payload nhạy cảm.

### 10.3. Dùng LettuceConnectionFactory thay vì tự tạo socket tùy ý

Spring Boot thường tự cấu hình `LettuceConnectionFactory` khi Spring Data Redis starter và cấu hình phù hợp. Các `RedisTemplate`, `StringRedisTemplate` và `ReactiveRedisTemplate` nên nhận connection factory được cấu hình bảo mật, thay vì mỗi service tự mở Redis connection bằng IP/user/password riêng.

Điều này giúp thống nhất:

- TLS và trust store.
- ACL user được dùng.
- Timeout, reconnect và topology.
- Secret rotation strategy.
- Observability và cấu hình môi trường.

Không tự tạo connection mới với password hardcode chỉ để một job “khỏi cần phụ thuộc cấu hình Spring”.

## 11. Ví dụ Java: sử dụng RedisTemplate và giới hạn đường API

Một service đọc cache catalog:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogCacheReader {

    private final StringRedisTemplate redis;

    public CatalogCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String findCachedProduct(String productId) {
        String key = "cache:catalog:product:" + productId;
        return redis.opsForValue().get(key);
    }
}
```

Code này không tự quyết định Redis có private hay TLS hay không; những bảo đảm đó thuộc **connection factory và hạ tầng triển khai**.

Với một API controller:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final CatalogCacheReader cache;

    public CatalogController(CatalogCacheReader cache) {
        this.cache = cache;
    }

    @PreAuthorize("hasAuthority('catalog:read')")
    @GetMapping("/{id}/cached")
    public String cached(@PathVariable String id) {
        return cache.findCachedProduct(id);
    }
}
```

`@PreAuthorize` chỉ có hiệu lực khi method security được bật và quy trình xác thực/phân quyền Spring Security được cấu hình đúng; ví dụ này không bao gồm toàn bộ SecurityFilterChain.

Hai tầng quyền phải độc lập:

1. Spring Security cho phép/không cho phép **người dùng HTTP** đọc catalog.
2. Redis ACL cho phép **service identity** đọc key thuộc `cache:catalog:*`.

Ngay cả khi người dùng HTTP có thể gọi một endpoint, họ **không được nhận Redis credential** hoặc mở Redis socket trực tiếp từ browser.

### 11.1. Không cung cấp endpoint Redis command tùy ý

Một API kiểu:

```text
POST /admin/redis-command
body: {"command": "ANY", "key": "..."}
```

có thể biến server thành proxy thực thi lệnh Redis theo yêu cầu của người gọi. Không thiết kế endpoint như vậy cho người dùng cuối. Công cụ quản trị riêng nếu thật sự cần phải có quyền hẹp, audit, allowlist thao tác và quy trình truy cập đặc biệt.

Ưu tiên API nghiệp vụ có command cố định thay vì cho client chọn raw Redis command/key.

## 12. Docker: tránh publish Redis port ngoài host

Docker Compose rất tiện trong phát triển, nhưng cấu hình `ports` dễ làm Redis lộ ra host:

```yaml
services:
  redis:
    image: redis:7.4-alpine
    ports:
      - "6379:6379"
```

Khi publish theo dạng này, Docker có thể bind host port trên các interface, tùy cấu hình Docker và network. Nếu host có public IP và firewall mở, Redis có thể bị truy cập từ ngoài.

**Trong deployment container, ứng dụng cùng Docker network thường không cần publish Redis port lên host.**

### 12.1. Ví dụ không publish cổng Redis

```yaml
services:
  api:
    image: example/catalog-api:1.0
    environment:
      REDIS_HOST: redis
      REDIS_PORT: "6379"
    networks:
      - app-private

  redis:
    image: redis:7.4-alpine
    volumes:
      - ./redis.conf:/usr/local/etc/redis/redis.conf:ro
    command:
      - redis-server
      - /usr/local/etc/redis/redis.conf
    networks:
      - app-private
    # Không khai báo ports để publish Redis ra host.

networks:
  app-private:
    internal: true
```

Cấu hình minh họa **chỉ giải quyết một phần giới hạn mạng container**; vẫn cần Redis ACL, TLS khi thích hợp, secret provisioning và giới hạn quyền của những container cùng mạng.

`internal: true` có thể hạn chế kết nối ra ngoài mạng này; nếu API cần Internet hoặc database ở mạng khác, phải bố trí thêm network riêng và rules có kiểm soát. Không sao chép cấu hình internal network vào mọi ứng dụng mà không xét nhu cầu kết nối.

Một container khác được nối vào `app-private` vẫn có thể thử truy cập Redis. Docker network không phải thay thế cho ACL.

### 12.2. Phát triển local cần truy cập từ host

Khi cần công cụ Redis CLI từ máy phát triển, có thể publish chỉ trên loopback của máy:

```yaml
ports:
  - "127.0.0.1:6379:6379"
```

Điều này **hạn chế host binding trên IPv4 loopback** trong cấu hình hỗ trợ, phù hợp cho môi trường developer có kiểm soát. Không coi nó là bảo đảm tuyệt đối trên mọi phiên bản/nền tảng Docker và không dùng như mẫu production không cần thiết.

Trên máy có nhiều network adapter, VM, tunnel hoặc môi trường phát triển từ xa, vẫn phải xác minh exposure bằng công cụ kiểm tra kết nối thực tế.

### 12.3. EXPOSE và ports không cùng ý nghĩa

- `EXPOSE` trong Dockerfile hoặc `expose` trong Compose chủ yếu mô tả cổng container cho mạng nội bộ/metadata.
- `ports` publish cổng container lên host theo rule Docker.
- Không publish host port không tự ngăn container khác trong cùng network truy cập.
- `network_mode: host` thay đổi ranh giới namespace mạng; phải đánh giá riêng.

Đừng lấy việc Dockerfile không có `EXPOSE` làm bằng chứng Redis không thể bị truy cập.

## 13. Kubernetes: Redis nên dùng ClusterIP

Trong Kubernetes, Redis thường được cung cấp thông qua một `Service` nội bộ.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: data
spec:
  type: ClusterIP
  selector:
    app: redis
  ports:
    - name: redis-tls
      port: 6379
      targetPort: 6379
      protocol: TCP
```

`ClusterIP` tạo endpoint nội bộ trong cluster. Đây thường là lựa chọn phù hợp cho Redis khi ứng dụng cũng chạy trong Kubernetes.

Tránh tự tạo:

```yaml
spec:
  type: LoadBalancer
```

cho Redis nếu không có kiến trúc private load balancer và ràng buộc nguồn rõ ràng. Một số cloud tạo public LoadBalancer theo mặc định, có thể khiến Redis bị expose.

Tương tự, Kubernetes `NodePort` có thể làm một cổng truy cập qua node IP, ảnh hưởng exposure tùy network/firewall. Không dùng NodePort chỉ để “đỡ phải cấu hình DNS”.

### 13.1. ClusterIP chưa đủ

Nếu cluster có hàng trăm namespace, một ClusterIP Service có thể vẫn được nhiều pod trong cluster truy cập mặc định. Network segmentation cần tiếp tục tới **NetworkPolicy** và Redis ACL.

## 14. Kubernetes NetworkPolicy: chỉ cho pod được chỉ định truy cập

Ví dụ Redis pod có label `app: redis` trong namespace `data`; API pod có label `app: catalog-api` trong namespace `apps`.

NetworkPolicy cho Redis:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-only-catalog-api
  namespace: data
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: apps
          podSelector:
            matchLabels:
              app: catalog-api
      ports:
        - protocol: TCP
          port: 6379
```

Ý nghĩa:

- Chính sách áp dụng cho các pod Redis được chọn bởi `podSelector`.
- Ingress từ những pod `app: catalog-api` trong namespace `apps` được phép tới TCP 6379.
- Những nguồn khác không được cho phép bởi chính sách này sẽ bị chặn **nếu không có NetworkPolicy khác cho phép** và CNI thực thi NetworkPolicy đúng.
- `namespaceSelector` và `podSelector` trong **cùng một mục của `from`** kết hợp để chọn pod của namespace phù hợp.

### 14.1. NetworkPolicy chỉ có hiệu lực khi CNI hỗ trợ

Không phải mọi Kubernetes networking setup đều thực thi NetworkPolicy theo cùng cách. Phải kiểm tra CNI và network policy controller của cluster.

Ngoài ra, NetworkPolicy của Kubernetes thường có semantics **cộng dồn allow rules**. Nếu một policy khác đã cho phép mọi pod vào Redis, thêm policy hẹp ở trên có thể **không thu hồi quyền đã được policy khác cho phép**.

Do đó, cần rà soát **toàn bộ NetworkPolicy áp dụng lên Redis pods**, không chỉ file mới tạo.

### 14.2. Ingress và egress là hai chiều riêng

Policy trên giới hạn **ingress tới Redis**. Nếu namespace ứng dụng có egress default-deny, ứng dụng cũng cần egress policy cho phép kết nối tới Redis và DNS cần thiết.

Tương tự, Redis replication/Cluster/Sentinel có thể cần kết nối giữa các Redis pods. Nếu chỉ thêm một ingress policy cho API mà vô tình chặn inter-node traffic, Cluster có thể mất quorum hoặc failover không hoạt động.

Không sao chép một rule port 6379 rồi kết luận đã đủ cho Redis Cluster/Sentinel; cần dựng ma trận port và source/destination riêng cho topology thực tế.

## 15. Redis Cluster: bảo vệ cả data port và cluster bus

Redis Cluster chia keyspace thành hash slots, các primary/replica phối hợp với nhau. Các node có thể cần giao tiếp qua:

- **Data/client port** do triển khai cấu hình.
- **Cluster bus port**, thường mặc định bằng data port + 10000 trong cấu hình phổ biến.
- Đường replication và TLS cluster bus nếu được bật.
- Endpoint mà client Lettuce nhận được khi khám phá topology.

```text
                  Application private tier
                           |
                       TLS + ACL
                           |
                    Cluster data ports
                           |
             +-------------+-------------+
             |             |             |
          Primary A     Primary B     Primary C
             |             |             |
          Replica A     Replica B     Replica C
             \_____________|_____________/
                  Private cluster bus
                  (không public)
```

Một Redis Cluster có thể trả về địa chỉ node khi client khám phá topology. Nếu những địa chỉ đó là public IP hoặc hostname không thể truy cập từ private application network, client có thể bị lỗi redirect/routing hoặc bị dẫn tới đường không phù hợp với chính sách mạng.

Cần kiểm tra:

- Cluster announcement/advertised addresses là **địa chỉ private có thể truy cập** từ client hợp lệ.
- Không publish Redis Cluster bus ra Internet.
- Firewall cho phép node–node traffic đúng cổng cần thiết, không phải mọi cổng.
- Sự thay đổi slot/failover không làm client mất khả năng kết nối tới node mới.
- Certificate TLS hợp lệ với hostname mà client thực tế dùng.
- ACL command cần thiết cho ứng dụng; không cấp cluster-admin cho service.
- Các job `SCAN`/maintenance không bị biến thành công cụ quét mọi node từ bên ngoài.

### 15.1. TLS cho replication và Cluster

Khi dùng Redis TLS trên những triển khai có replication hoặc Cluster, có thể cần thiết lập như `tls-replication yes` hoặc `tls-cluster yes` theo phiên bản và mode. Phải đồng bộ certificate/trust, port và firewall giữa các node.

Chỉ bật TLS cho app→primary mà để đường primary→replica hoặc node→node không được bảo vệ **có thể chưa đạt yêu cầu bảo mật nội bộ**, tùy mô hình đe dọa.

## 16. Sentinel: kiểm soát riêng cổng discovery và failover

Redis Sentinel thường dùng cổng `26379` mặc định để client và các Sentinel nodes truy cập thông tin hạ tầng. Trong mô hình Sentinel:

```text
             Spring Data Redis / Lettuce
                      |
                  Sentinel nodes
                      |
                Primary discovery
                      |
                      v
                   Redis primary
                      |
                   Replica(s)
```

Nếu cho ứng dụng truy cập Sentinel nhưng không cho nó kết nối tới primary/replica được Sentinel trả về, client vẫn có thể không đọc/ghi được dữ liệu.

Vì vậy, firewall cần phản ánh đúng **luồng discovery và luồng data**:

1. Application → Sentinel endpoints, chỉ port cần thiết.
2. Application → Redis data endpoint hiện hành.
3. Redis primary ↔ replicas/replication traffic theo topology.
4. Sentinel ↔ Redis/Sentinel communication theo thiết kế.
5. Không có đường truy cập công khai trực tiếp vào những endpoint này.

Sentinel cũng cần authentication/TLS và quyền phù hợp. Không coi Sentinel là “chỉ metadata nên ai cũng kết nối được”.

## 17. Managed Redis: không dựa vào giả định dịch vụ tự an toàn

Với dịch vụ Redis do cloud quản lý, người dùng có thể không chỉnh trực tiếp `redis.conf` hoặc interface bind. Khi đó, các lớp bảo vệ được cung cấp qua:

- Private endpoint và network placement.
- Cloud security groups / firewall rules.
- Service-level authentication/ACL.
- TLS in transit và encryption at rest khi được hỗ trợ.
- IAM/role-based control cho API quản trị cloud.
- Audit logs, metrics và phương án failover.
- Chính sách backup, retention và key management.

Một số cloud có tùy chọn publicly accessible hoặc public endpoint, một số chỉ hỗ trợ private connectivity. Không suy luận tên dịch vụ có chữ “managed” thì chắc chắn không thể bị expose.

### 17.1. Checklist cloud networking

- Redis resource nằm trong VPC/private network nào?
- Có public IP/public DNS endpoint không?
- Security group inbound có `0.0.0.0/0` hoặc `::/0` không?
- Có kết nối chéo VPC/account/peering ngoài dự kiến không?
- Có public load balancer/tunnel/port-forward tới Redis không?
- Application identity nào được phép kết nối?
- Admin console/CLI được truy cập qua đường nào?
- Redis Cluster/Sentinel nodes quảng bá địa chỉ gì?
- TLS/ACL có được bật đúng không?
- Logging/alerting có thể phát hiện thay đổi policy mạng không?

Những câu hỏi này áp dụng cho AWS/Azure/GCP và các hạ tầng tương đương, dù tên sản phẩm và cấu hình cụ thể khác nhau.

## 18. Phân vùng theo môi trường và theo ứng dụng

Không nên sử dụng một Redis production chung cho:

```text
production API
staging API
developer laptops
CI tests
experimental background workers
```

khi tất cả cùng có credential/quyền ghi tương đương. Một lỗi test có thể xóa cache/session thật, còn secret trên laptop có thể làm tăng bề mặt tấn công vào production.

Ưu tiên:

- Tách Redis deployment hoặc ít nhất tách network/credentials theo môi trường.
- Prod không truy cập trực tiếp từ CI/test runner public.
- Tách application ACL user theo vai trò.
- Giới hạn key namespace; nhưng **namespace không thay thế ACL hoặc network segmentation**.
- Định nghĩa rõ ai có quyền migration hoặc lệnh quản trị.
- Không dùng `SELECT databaseIndex` làm ranh giới bảo mật: logical databases của Redis không phải tenant isolation và Redis Cluster có giới hạn riêng.

Một module dùng `cache:*` và một module dùng `session:*` trên cùng Redis không trở nên cô lập về bảo mật nếu cả hai dùng user có quyền `~*` và được nối từ cùng mọi mạng.

## 19. Least privilege cho Spring Cache, Spring Session và Streams

Spring Data Redis là thư viện rộng; quyền ACL thực tế phụ thuộc phần ứng dụng dùng.

| Workload | Dữ liệu | Quyền cần đánh giá |
|---|---|---|
| `StringRedisTemplate` GET/SET đơn giản | Catalog cache | GET/SET, TTL, DEL theo namespace |
| `RedisCacheManager` | Cache entries | Lệnh cache get/put/evict/clear phù hợp |
| Spring Session Redis | Session keys/index/expiry | Lệnh quản lý session, index, TTL và notification theo repository |
| Redis Streams consumer | Stream và consumer group | XREADGROUP, XACK, XPENDING, claim và những lệnh lifecycle cần thiết |
| Redis Pub/Sub listener | Channel | SUBSCRIBE/PSUBSCRIBE và channel pattern phù hợp |
| Rate limiter Lua | Bộ đếm/TTL | Quyền script/keys được dùng theo thiết kế |
| Health check | Kiểm tra kết nối | PING hoặc check được định nghĩa; không cần quyền toàn bộ Redis |

### 19.1. Redis ACL cũng hỗ trợ channel patterns

Với Pub/Sub, quyền key không đủ để mô tả kênh. Các phiên bản Redis ACL hỗ trợ giới hạn channel pattern riêng theo khả năng của Redis server. Cần kiểm tra cấu hình ACL cho `SUBSCRIBE`/`PUBLISH`, tránh cho dịch vụ nghe hoặc phát trên mọi channel khi không cần.

### 19.2. Đừng cấp quyền rộng để chữa lỗi NOPERM

Khi chuyển sang ACL hạn chế, có thể gặp lỗi `NOPERM` vì ứng dụng dùng thêm command ngoài dự đoán. Không sửa bằng cách cho mọi application user `+@all` và `~*`.

Quy trình tốt hơn:

1. Xác định command thật sự bị từ chối.
2. Xem use case có hợp lệ hay không.
3. Thêm đúng command/key/channel pattern nếu cần.
4. Kiểm thử luồng đọc/ghi, expiration, reconnect và failover.
5. Theo dõi lại ACL failures.

Một số công việc như session indexing, script evaluation hoặc cluster topology có thể cần quyền bổ sung; luôn chứng minh qua môi trường thử nghiệm.

## 20. Quản lý mật khẩu, chứng chỉ và secret rotation

Đặt credential trong source code:

```java
String password = "redis-production-password"; // Không làm.
```

hoặc trong file cấu hình được commit vào repository:

```yaml
spring:
  data:
    redis:
      password: "hardcoded-production-secret"
```

là rủi ro vận hành lớn.

Thay vào đó:

- Dùng cloud secret manager, vault hoặc cơ chế secret injection của platform.
- Giới hạn quyền đọc secret của workload và nhân viên.
- Tách credential production/staging/dev.
- Không in secret trong logs, stacktrace, CI output hoặc connection URI.
- Quản lý rotation và thời gian tồn tại credential.
- Thu hồi credential cũ sau khi xác nhận application đã chuyển.
- Đảm bảo pod/container có thể reload/reconnect khi secret thay đổi.

### 20.1. Rotation mà không gây outage

Một chiến lược có thể gồm:

```text
Tạo credential mới có quyền tương đương, giới hạn
            |
            v
Phân phối tới application instances
            |
            v
Canary reconnect và verify GET/SET
            |
            v
Rollout phần còn lại
            |
            v
Xác minh không còn session dùng credential cũ
            |
            v
Thu hồi credential cũ
```

Redis ACL có thể hỗ trợ cấu hình user/password theo cơ chế phiên bản cụ thể, nhưng thứ tự rotation và khả năng giữ nhiều credential cần được thiết kế theo hệ thống triển khai. Không xóa ngay credential cũ trước khi các connection đã chuyển, nếu không có kế hoạch downtime.

### 20.2. Certificate rotation

Khi thay TLS certificate:

- Certificate mới phải đúng hostname.
- Client trust chain phải được cập nhật.
- Các connection cũ và mới có thể có hành vi khác nhau trong giai đoạn rollout.
- Kiểm tra khả năng reconnect/failover.
- Không “khắc phục” bằng việc tắt hostname verification.

Bảo vệ private key server và client nếu dùng mTLS; không mount file certificate/private key với permission quá rộng.

## 21. Phát hiện Redis đã bị expose ra ngoài

Không thể xác nhận Redis an toàn chỉ bằng việc file cấu hình trông hợp lý. Cần **kiểm chứng đường mạng thực tế** từ cả nguồn được phép và nguồn không được phép trong phạm vi hạ tầng mình quản lý.

### 21.1. Kiểm tra cấu hình lắng nghe

Trong môi trường có quyền quản trị, xác định:

- Redis đang listen trên IP/port nào?
- Có cả IPv4 và IPv6 không?
- Có plain TCP listener không mong muốn không?
- Docker có publish host port không?
- Kubernetes Service có thuộc loại LoadBalancer/NodePort không?
- Security group/firewall có allow từ nguồn rộng không?
- Có load balancer, proxy hoặc tunnel nào forward tới Redis không?

Các công cụ quan sát thường gặp:

```bash
# Trên máy Linux quản trị Redis được cấp quyền:
ss -lnt

# Trong môi trường Docker:
docker ps

# Trong Kubernetes:
kubectl get svc -A
kubectl get networkpolicy -A
```

Đây là các lệnh khảo sát cấu hình tại những môi trường được quyền quản lý. `ss -lnt` cho biết socket listen trên máy được hỏi, không chứng minh rằng traffic từ Internet có thể đi xuyên firewall. `kubectl get svc` cho biết Service, nhưng không thay thế việc kiểm tra cloud load balancer và security group.

### 21.2. Kiểm tra kết nối từ nguồn cho phép

Từ một application instance hoặc pod test được phép:

```bash
redis-cli --tls \
  --host private-redis.example.internal \
  --port 6379 \
  --user catalog_reader \
  PING
```

Lệnh minh họa chưa cung cấp password; trong môi trường test, dùng cơ chế an toàn như secret environment hoặc credential prompt theo cách Redis CLI và platform hỗ trợ. Không đưa password thật trực tiếp vào command line hiển thị trong process list hoặc shell history.

Kết quả `PONG` xác nhận ít nhất một lệnh Redis đã hoàn tất, nhưng **không chứng minh**:

- Client chỉ có quyền ACL phù hợp.
- Server certificate đã được xác minh theo chính sách thật.
- Tất cả lệnh ứng dụng cần đều thành công.
- Địa chỉ Redis không truy cập được từ nguồn không tin cậy.
- Replication/Cluster/Sentinel và failover hoạt động an toàn.

### 21.3. Kiểm tra nguồn không được phép

Từ một network test mà người quản trị sở hữu và có quyền kiểm tra, kết nối trực tiếp tới Redis private endpoint **phải bị từ chối/timeout theo firewall policy** nếu nguồn không nằm trong allowlist.

Cần phân biệt:

- DNS không resolve private name từ ngoài có thể là một lớp hỗ trợ, không phải chứng cứ cuối.
- Nếu public endpoint tồn tại, một DNS private record không ngăn địa chỉ public còn truy cập được.
- Không có phản hồi `PING` có thể do TLS/auth fail, nhưng socket vẫn có thể đã được mở từ Internet.
- Mục tiêu là **không có đường mạng không được phép tới Redis**, không chỉ “không AUTH được”.

Không quét hay thử kết nối vào hệ thống của bên thứ ba không được ủy quyền; phạm vi kiểm thử chỉ là tài nguyên/mạng thuộc quyền quản trị.

## 22. Kiểm thử quyền ACL và phân biệt lỗi

Một test bảo mật cần xác minh cả hai hướng:

### Quyền hợp lệ

- API user đọc được key thuộc namespace được cấp.
- API writer ghi/evict được key được phép.
- Spring Session/Streams hoạt động với user riêng có quyền đúng.
- Reconnect sau failover vẫn dùng ACL đúng.
- TLS handshake và hostname validation thành công với certificate hợp lệ.

### Quyền không hợp lệ

- API user **không** đọc được key thuộc namespace session của dịch vụ khác.
- API user **không** chạy được lệnh quản trị nguy hiểm.
- User read-only không ghi được.
- Client không được cho phép không kết nối được qua network policy.
- Credential sai bị từ chối rõ ràng.
- Certificate không tin cậy hoặc hostname sai khiến kết nối TLS bị từ chối.

Trong Spring Data Redis, các lỗi như connection timeout, `NOAUTH`/`NOPERM`, certificate failure hay lỗi cấu hình có thể biểu diễn qua exception của driver/Spring Data Access. Không biến những lỗi đó thành cache miss bằng `catch (Exception) { return null; }`.

### 22.1. Fail closed với dữ liệu nhạy cảm

Khi Redis chỉ giữ catalog cache có database làm nguồn, lỗi Redis có thể được phép fallback có giới hạn. Nhưng với:

- Session authentication.
- Anti-replay token.
- Rate limit bảo vệ endpoint nhạy cảm.
- Lock dùng cho một bất biến quan trọng.
- Revocation state.

không được mặc định coi Redis access error như “key không tồn tại” rồi cho phép request. Chính sách fail-open hay fail-closed phải dựa trên threat model và nguồn sự thật, không phải do một catch block tiện tay.

## 23. Bảo vệ chống bão tải và từ chối dịch vụ ở lớp ứng dụng

Ngay cả Redis chỉ có private endpoint vẫn có thể bị quá tải từ chính client nội bộ nếu ứng dụng có bug hoặc traffic burst.

Các biện pháp:

- Giới hạn timeout cho lệnh Redis.
- Dùng connection/pool/concurrency policy phù hợp workload.
- Không tạo hàng nghìn blocking requests lên Redis từ event loop.
- Giới hạn retry, tránh retry storm khi Redis không sẵn sàng.
- Không cho client HTTP điều khiển trực tiếp lệnh quét lớn.
- Dùng bulkhead/rate limit cho fallback database khi Redis outage.
- Giới hạn kích thước value, lệnh collection tốn thời gian và script dài.
- Cảnh báo khi connected clients, CPU, memory, command latency tăng bất thường.

Redis Cluster/replica không phải lá chắn tự động trước DoS: một hot key vẫn có thể tập trung vào một shard, còn lệnh Lua dài có thể chiếm thời gian xử lý của primary.

### 23.1. Không chạy lệnh quản trị trong request người dùng

Tránh các endpoint chạy `KEYS *`, `FLUSHALL`, `CONFIG SET` hoặc những thao tác quản trị tương đương theo input client. Nếu phải có maintenance job, chạy qua kênh có kiểm soát, hạn chế quyền, số lượng key, tốc độ và audit.

## 24. Observability và audit khi bảo vệ Redis

Các metric nên theo dõi:

| Metric/log | Câu hỏi |
|---|---|
| Redis connections theo nguồn/network | Có client bất thường đang kết nối? |
| Authentication failure count | Có credential sai hoặc hành vi dò xác thực? |
| ACL denied commands/key/channel | Ứng dụng thiếu quyền hay có thao tác bất thường? |
| Redis command QPS/latency | Có thay đổi bất thường sau deploy? |
| Connected clients | Có connection leak/burst? |
| Redis memory/evictions | Có áp lực tài nguyên hoặc dữ liệu bị evict? |
| TLS handshake/certificate errors | Có lỗi trust/expiry/SAN? |
| Firewall/security group change logs | Có rule mở rộng bất thường? |
| Public endpoint inventory | Có tài nguyên Redis mới bị publish? |
| Cluster/Sentinel failover events | Có thay đổi node/kết nối ngoài dự đoán? |
| Slowlog/commandstats | Có lệnh quá chậm hoặc workload mới? |
| Secret access/rotation logs | Ai truy cập/đổi credential? |

Redis cung cấp một số công cụ quan sát:

```bash
redis-cli INFO clients
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli ACL LOG 10
redis-cli SLOWLOG GET 10
```

Một số lệnh như `ACL LOG` có thể đòi hỏi quyền quản trị, không nên cấp cho service API thường. Khi thu thập log, tránh ghi dữ liệu nhạy cảm hoặc địa chỉ nội bộ vào hệ thống công khai.

### 24.1. Cảnh báo phù hợp

Ví dụ nên cảnh báo khi:

- Security group inbound Redis xuất hiện `0.0.0.0/0` hoặc `::/0`.
- Kubernetes Service Redis đổi từ `ClusterIP` sang `LoadBalancer` không được duyệt.
- Có port publish mới trên Docker/host.
- Redis bắt đầu listen trên public interface ngoài dự kiến.
- `ACL LOG` có nhiều `NOPERM`/auth failures bất thường.
- TLS certificate sắp hết hạn hoặc hostname verification bắt đầu lỗi.
- Replica/Cluster bus endpoint mở ở mạng rộng.
- Redis connection count và command latency đột ngột tăng.

Không chỉ cảnh báo khi Redis CPU cao: nhiều lỗi bảo mật về network exposure xảy ra trước khi có tải hoặc request đáng ngờ.

## 25. Phân biệt bảo vệ đường client và đường nội bộ Redis

Trong Redis có replication/Cluster, hai nhóm traffic:

1. **Client → Redis:** GET/SET/EVAL/Streams/PubSub từ ứng dụng.
2. **Redis node ↔ Redis node:** replication, Cluster bus, Sentinel coordination theo kiến trúc.

Nếu chỉ kiểm soát lớp client mà không bảo vệ đường liên-node, một attacker có đường mạng vào hạ tầng nội bộ có thể tác động lên thành phần replication/coordination khi quyền và giao thức cho phép.

Cần:

- Tách rule client và inter-node.
- Hạn chế node source tới đúng danh sách node Redis.
- Dùng TLS và authentication phù hợp với replication/Cluster/Sentinel.
- Kiểm tra đổi node/replica khi failover.
- Kiểm tra CIDR của node autoscaling và private DNS.
- Không đặt management endpoint hoặc metrics exporter chưa bảo vệ trên public interface.

Đặc biệt, một deployment có Redis data port dùng TLS nhưng Cluster bus không được giới hạn mạng **vẫn cần được đánh giá lại**.

## 26. Vận hành truy cập quản trị an toàn

Người vận hành đôi khi cần dùng Redis CLI để điều tra key hoặc kiểm tra Redis health. Truy cập trực tiếp từ laptop qua cổng public không nên là đường mặc định.

Các phương án phù hợp hơn:

- Bastion/private jump host đã có xác thực mạnh và audit.
- VPN được quản lý với phân quyền theo nhóm và thời gian.
- Privileged administration job trong mạng private với quyền tối thiểu.
- Port-forward tạm thời qua kênh được bảo vệ, gắn với quyền và phiên truy cập có kiểm soát.
- Managed provider console/connection tool nếu hỗ trợ private network và audit.

Quy trình quản trị nên:

1. Xác định mục đích và thời gian truy cập.
2. Dùng user ACL admin riêng, không mượn credential ứng dụng.
3. Hạn chế nguồn mạng và thời gian mở.
4. Không lưu secret trong shell history và logs.
5. Ghi lại thay đổi trên hạ tầng theo change management.
6. Thu hồi quyền/tunnel tạm khi hoàn tất.

Không tạo ngoại lệ firewall “tạm thời mở toàn Internet” rồi để lại như cấu hình vĩnh viễn.

## 27. Kịch bản sự cố: Redis bị phát hiện có cổng public

Giả sử một Redis production được phát hiện có endpoint public hoặc inbound rule quá rộng. Quy trình ứng phó cần ưu tiên **cô lập và bảo toàn khả năng điều tra**, không chỉ đổi password rồi coi như xong.

### 27.1. Cô lập ngay đường không cần thiết

- Chặn public inbound tới Redis bằng security group/firewall/network policy.
- Đánh giá port-forward/load balancer/tunnel nào có thể mở đường thay thế.
- Đảm bảo ứng dụng hợp lệ vẫn có private route, tránh tự gây outage không cần thiết.
- Nếu có nghi ngờ compromise, dùng quy trình incident response của tổ chức và giữ bằng chứng/log thích hợp.

### 27.2. Đánh giá phạm vi ảnh hưởng

- Redis đã lộ từ khi nào?
- Credential có đang bật và đủ mạnh không?
- ACL default user và các application user có quyền gì?
- Có dấu hiệu truy cập, lệnh bất thường, thay đổi ACL/CONFIG không?
- Những loại dữ liệu nào đang lưu: cache, session, token, PII hay state nghiệp vụ?
- Có replica/backup nào có thể đã bị ảnh hưởng?
- Có cần revoke session/token hoặc đối soát nghiệp vụ không?

### 27.3. Khắc phục và phục hồi

- Xoay vòng credential/secret và certificate khi cần.
- Thu hồi quyền quá rộng; tách user theo workload.
- Kiểm tra integrity dữ liệu và đối soát với nguồn authoritative.
- Nếu cần, khôi phục từ backup có độ tin cậy và thời điểm phù hợp.
- Revoke session/token nếu có nguy cơ lộ.
- Rà soát host/container và đường truy cập quản trị.
- Kiểm tra lại private connectivity, firewall và TLS từ nguồn được phép/không được phép.
- Tạo cơ chế ngăn tái phát qua IaC, policy-as-code và cảnh báo thay đổi.

**Không mặc định rằng đổi Redis password sẽ sửa được dữ liệu đã bị ghi đè hoặc token đã bị lộ.** Phải xem xét cả trạng thái nghiệp vụ và các hệ thống đã dùng dữ liệu Redis.

## 28. Kiểm thử bảo mật theo từng môi trường

Một quy trình test nên có những nhóm sau:

### 28.1. Network

- Redis không có public-facing endpoint không được duyệt.
- IPv4/IPv6 firewall không cho Internet vào data/Sentinel/Cluster ports.
- Application private subnet kết nối được tới Redis.
- Một workload ở namespace/mạng không được phép **không** kết nối được.
- Load balancer, Docker port publish, Kubernetes Service không vô tình mở public.
- Redis Cluster/Sentinel internal nodes vẫn kết nối đúng sau khi áp policy.

### 28.2. TLS

- Client xác thực được certificate Redis hợp lệ.
- TLS certificate sai hostname bị từ chối.
- CA không tin cậy bị từ chối.
- Không có đường plain TCP không mong muốn.
- Rotation certificate không làm ứng dụng mất kết nối kéo dài.
- Replication/Cluster traffic được bảo vệ theo chính sách.

### 28.3. ACL

- User reader chỉ GET key được phép.
- User reader không SET/DEL được.
- User ứng dụng không chạy được lệnh admin.
- User không truy cập key namespace khác.
- Credentials sai bị từ chối.
- Các lệnh Spring Cache/Session/Streams thực tế vẫn hoạt động với quyền tối thiểu.

### 28.4. Failover và rollout

- Khi primary đổi, client kết nối qua private route tới primary mới.
- Redis Cluster redirect không yêu cầu mở public IP.
- Sentinel discovery trả endpoint app thực sự tới được.
- Secret rotation và TLS renewal vẫn giữ ứng dụng hoạt động theo SLO.
- Một Redis outage không khiến API bypass session/rate-limit/authorization.

### 28.5. Logging

- Không lộ Redis password, Redis URI có credential hay session ID trong log.
- Không dùng dữ liệu nhạy cảm làm metric label.
- Thay đổi firewall/ACL được audit.
- Có cảnh báo công khai cổng và auth failures.

Những test này nên chạy trong môi trường được kiểm soát và đúng phạm vi hạ tầng sở hữu. Không cần thực hiện hành vi tấn công hoặc thao tác phá hoại trên production để xác minh việc cổng Redis đã được giới hạn.

## 29. Bảng lỗi cấu hình phổ biến

| Sai lầm | Nguy cơ | Cách khắc phục |
|---|---|---|
| Redis listen `0.0.0.0` trên host có public IP và port mở | Internet truy cập Redis | Private bind/firewall, không public endpoint |
| Security group inbound `0.0.0.0/0` hoặc `::/0` | Bề mặt tấn công rộng | Chỉ allow application identity/private source |
| Tin `protected-mode yes` là đủ | Cấu hình khác vẫn có thể expose | Defense in depth |
| Dùng password nhưng không TLS | Credential/data có thể bị quan sát trên mạng | TLS và xác minh certificate |
| Tắt certificate validation để kết nối nhanh | Nguy cơ giả mạo endpoint | Sửa CA/SAN/trust store |
| Redis ACL user `+@all ~*` cho API | Quyền quá rộng khi app/secret bị lộ | Least privilege theo command/key/channel |
| Default user vẫn không giới hạn | Vô hiệu hiệu quả phân quyền ACL | Kiểm tra và quản lý default user |
| Password đặt trong Git/URI/log | Rò rỉ credential | Secret manager và rotation |
| Docker Compose publish `6379:6379` | Host port có thể công khai | Không publish; private network |
| Kubernetes Redis Service `LoadBalancer` công khai | Internet có đường vào Redis | ClusterIP và NetworkPolicy |
| Chỉ tin ClusterIP mà không có NetworkPolicy | Nhiều pod nội bộ truy cập được | Ingress/egress allowlist, CNI enforcement |
| NetworkPolicy có rule quá rộng khác | Policy hẹp không tự chặn rule cũ | Kiểm tra toàn bộ policies cộng dồn |
| Mở Cluster bus/Sentinel public | Lộ giao thức hạ tầng | Inter-node private rules |
| Cluster announce địa chỉ public | Client routing không an toàn/không ổn định | Private advertised addresses |
| Mọi môi trường dùng chung Redis prod | Test/dev có thể tác động dữ liệu thật | Tách deployment và user |
| Dùng database index làm tenant security | Không có isolation đủ mạnh | ACL/network/namespace theo boundary |
| Dùng lỗi Redis như cache miss bảo mật | Có thể bỏ qua điều kiện bảo vệ | Phân loại lỗi, fail closed khi cần |
| Mở public port tạm rồi quên đóng | Exposure kéo dài | IaC policy, alert và change control |
| Không giám sát auth/ACL/network change | Không phát hiện sai cấu hình | Audit, metrics và cảnh báo |

## 30. Cây quyết định triển khai Redis riêng tư

```text
Ứng dụng Spring Data Redis cần Redis?
                  |
                  v
         Redis có public endpoint?
              /          \
            Có           Không rõ / Không
             |                 |
             v                 v
       Loại public       Xác minh routing,
       exposure         IPv4/IPv6, firewall
             |                 |
             +--------+--------+
                      |
                      v
            Chỉ app/worker được phép
            có private route tới Redis?
                  /          \
                Không        Có
                  |           |
                  v           v
        Sửa firewall/SG    Bật Redis ACL
        NetworkPolicy      theo role/key
                  |           |
                  +-----+-----+
                        |
                        v
                    Có TLS?
                  /       \
                Không      Có
                  |         |
                  v         v
              Bật TLS     Xác minh cert,
              server/app  hostname/trust
                  |         |
                  +----+----+
                       |
                       v
           Có Sentinel/Cluster/replica?
                   /         \
                 Có          Không
                  |            |
                  v            |
       Bảo vệ inter-node ports |
       và private discovery     |
                  |            |
                  +-----+------+
                        |
                        v
         Test allowed/denied connections,
         ACL, TLS, failover và logs
                        |
                        v
             Đưa policy vào IaC,
             monitor drift và rotate
             credential định kỳ
```

## 31. Quy trình triển khai theo giai đoạn

### Giai đoạn 1: kiểm kê

- Liệt kê tất cả Redis deployments, endpoint và môi trường.
- Xác định dữ liệu đang lưu, user/client hiện tại và quyền cần thiết.
- Xác định Redis Standalone, Sentinel hay Cluster.
- Kiểm tra public endpoints, firewall, Docker/Kubernetes exposure.
- Thu metric kết nối và các nhóm command để chuẩn bị ACL.

### Giai đoạn 2: đóng đường công khai

- Đưa Redis vào private network hoặc private endpoint.
- Chặn inbound từ Internet, gồm IPv4/IPv6.
- Chỉ allow những workloads được duyệt.
- Bảo vệ Cluster/Sentinel/inter-node ports.
- Xác minh ứng dụng vẫn kết nối được qua private route.

### Giai đoạn 3: bảo vệ kết nối và danh tính

- Cấu hình TLS, CA, hostname và client trust.
- Tạo Redis ACL user theo dịch vụ/role.
- Phân phối secret qua secret manager.
- Kiểm thử quyền GET/SET/Streams/Session theo use case.
- Hạn chế default user và quyền quản trị.

### Giai đoạn 4: thử lỗi và rollout

- Thử denied network, credentials sai, TLS sai.
- Thử failover/reshard để kiểm tra private connectivity.
- Kiểm tra Redis outage không khiến ứng dụng bypass bảo mật.
- Rollout canary, theo dõi timeout và auth failures.
- Thu hồi credential cũ sau khi xác nhận chuyển đổi.

### Giai đoạn 5: duy trì

- Quản lý firewall/Service/NetworkPolicy bằng IaC.
- Phát hiện drift và cảnh báo rule công khai.
- Xoay vòng secret và certificate.
- Rà soát quyền ACL sau mỗi thay đổi feature.
- Diễn tập incident response và kiểm tra các endpoint mới.

## 32. Tổng kết

**Giới hạn truy cập mạng là yêu cầu đầu tiên để bảo vệ Redis khỏi Internet công cộng.** Trong kiến trúc Spring Data Redis, browser và client không tin cậy nên chỉ tương tác với API có xác thực, còn Redis phải nằm trong mạng riêng và chỉ chấp nhận kết nối từ những workloads được phép.

Những nguyên tắc cần ghi nhớ:

1. **Không publish Redis trực tiếp ra Internet.** Kiểm tra public IPv4/IPv6, firewall, Docker ports, Kubernetes Service và cloud endpoints.
2. **Private network + allowlist là lớp nền.** Chỉ cho API/worker và những thành phần quản trị được chỉ định tiếp cận data port.
3. **Redis bind và protected mode không thay thế firewall.** Chúng phải được đặt trong cùng mô hình defense in depth.
4. **TLS bảo vệ đường truyền; ACL giới hạn quyền.** Cả hai cần được cấu hình đồng bộ với Spring Data Redis/Lettuce.
5. **Credential phải được quản lý và xoay vòng.** Không hardcode password hoặc để lộ trong URI/log.
6. **Redis Cluster/Sentinel có nhiều cổng và đường kết nối.** Bảo vệ cả data path, discovery, replication và cluster bus; dùng private node addresses.
7. **Môi trường phải được cô lập.** Test/dev không sử dụng credential/quyền tương đương production.
8. **Kiểm tra bằng đường mạng thực tế.** Kết nối từ nguồn cho phép phải thành công; nguồn không được phép phải không có đường vào Redis.
9. **Giám sát drift và sự cố.** ACL failures, TLS errors, public port changes và network policy changes là những tín hiệu vận hành quan trọng.
10. **Ứng dụng vẫn phải xử lý lỗi an toàn.** Redis timeout không được trở thành lý do bỏ qua authentication, rate-limit hoặc điều kiện bảo mật.

**Quy tắc cốt lõi:** Redis chỉ nên nhìn thấy những client được quyền truy cập trong mạng được kiểm soát; mỗi client chỉ nên làm được những thao tác thực sự cần thiết. Chặn truy cập công cộng, bảo vệ đường truyền, phân quyền tối thiểu và liên tục xác minh cấu hình là những thành phần không thể thiếu của một hệ thống Spring Data Redis an toàn.

