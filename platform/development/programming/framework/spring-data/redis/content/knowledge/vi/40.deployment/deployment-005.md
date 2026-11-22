# Tương thích dịch vụ Redis được quản lý và các lệnh bị hạn chế

## 1. Khi ứng dụng chạy tốt với Redis local nhưng lỗi trên môi trường cloud

Một ứng dụng Spring Boot sử dụng Spring Data Redis có thể hoạt động ổn định với Redis chạy bằng Docker ở máy phát triển:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Ứng dụng đọc/ghi cache:

```java
stringRedisTemplate.opsForValue()
        .set("cache:product:42", "READY");
```

Mọi thứ đều bình thường. Nhưng khi chuyển sang một **dịch vụ Redis được quản lý** (*managed Redis service*), đội triển khai có thể gặp các tình huống:

- Kết nối TCP thành công nhưng server trả `NOPERM` với `INFO`, `CONFIG` hoặc `FLUSHDB`.
- Dịch vụ chỉ cung cấp một endpoint TLS, còn code vẫn dùng kết nối plaintext.
- Dịch vụ có Redis Cluster, nhưng ứng dụng cấu hình như một Redis standalone.
- Seed endpoint kết nối được, nhưng Lettuce không truy cập được các node mà Cluster công bố.
- Health check cố chạy lệnh quản trị không được phép nên đánh dấu ứng dụng unhealthy.
- `@CacheEvict(allEntries = true)` gọi `KEYS`/`DEL` và không chạy được dưới tài khoản hạn chế.
- Script `EVALSHA` hoạt động lúc đầu nhưng sau một lần thay node trả `NOSCRIPT`; fallback sang `EVAL` lại bị ACL từ chối.
- Một lệnh hoặc module có trong Redis tự vận hành không có trong gói dịch vụ hiện tại.
- Tài khoản có quyền đọc/ghi dữ liệu ứng dụng nhưng không có quyền thay đổi `maxmemory`, backup, failover hoặc ACL trực tiếp.
- Redis data plane hoạt động, nhưng các tính năng backup/restore hoặc điều chỉnh cấu hình phải dùng **control plane** của nhà cung cấp.

Các lỗi này không nhất thiết có nghĩa Spring Data Redis hoặc Lettuce bị hỏng. Chúng thường xảy ra vì ứng dụng đang giả định rằng:

> Có thể kết nối bằng giao thức Redis thì có thể dùng mọi lệnh, mọi quyền, mọi kiểu topology và mọi tính năng giống Redis tự vận hành.

Giả định đó không an toàn. **Tương thích giao thức không đồng nghĩa tương thích hoàn toàn về lệnh, quyền, tính năng, phiên bản, topology hoặc vận hành.**

Bài học thuộc chương **Triển khai** của **Spring Data Redis**. Mục tiêu là xây dựng một quy trình xác minh tương thích trước khi chuyển ứng dụng sang dịch vụ được quản lý và xử lý đúng các lệnh bị hạn chế mà không phá vỡ bảo mật hoặc tính đúng đắn của dữ liệu.

## 2. Managed Redis là gì?

Trong mô hình tự vận hành, nhóm ứng dụng hoặc nhóm hạ tầng chịu trách nhiệm phần lớn những việc:

```text
Cài Redis
    |
Chọn phiên bản
    |
Cấu hình bảo mật, persistence, maxmemory
    |
Quản lý replication/failover
    |
Backup và restore
    |
Nâng cấp, giám sát, khắc phục sự cố
```

Với Redis được quản lý, nhà cung cấp thường vận hành một phần hoặc phần lớn hạ tầng Redis:

```text
                     Nhà cung cấp
              +---------------------------+
              | Nodes / replication       |
              | Failover / patching       |
              | Backup / restore          |
              | Tài nguyên và cấu hình    |
              | Metrics / control plane   |
              +---------------------------+
                           |
                      Redis endpoint
                           |
                           v
                    Spring Boot app
                    Spring Data Redis
                           |
                    GET / SET / HGET...
```

Tuy nhiên, mỗi sản phẩm có phạm vi quản lý và tính năng khác nhau. Một số nền tảng cung cấp Redis OSS hoặc Valkey dưới dạng managed service; một số có engine tương thích Redis với tập lệnh, giới hạn hoặc các extension riêng.

Có thể gặp các nhóm dịch vụ như:

- Amazon ElastiCache cho Redis OSS hoặc Valkey, tùy engine/gói triển khai.
- Amazon MemoryDB và các sản phẩm tương thích Redis với mô hình durability khác.
- Google Cloud Memorystore với các chế độ Redis/Redis Cluster/Valkey được cung cấp.
- Microsoft Azure Managed Redis hoặc những dịch vụ Redis được cung cấp trong hệ sinh thái Azure.
- Redis Cloud và các dịch vụ Redis từ nhà cung cấp khác.
- Các nền tảng serverless hoặc proxy sử dụng một tập con của giao thức Redis.

**Không nên suy luận rằng một nhà cung cấp luôn cấm hay luôn hỗ trợ một lệnh trong mọi region, tier, engine và phiên bản.** Những thông tin đó có thể thay đổi. Phải xác nhận trên **dịch vụ cụ thể mà dự án mua và triển khai**.

### 2.1. Data plane và control plane

Đây là sự khác biệt quan trọng nhất.

**Data plane** là nơi ứng dụng gửi các lệnh dữ liệu:

```redis
GET cache:product:42
SET cache:product:42 "READY" EX 600
HGETALL profile:42
XADD events:orders * status PAID
```

**Control plane** là nơi nhà cung cấp cho phép thay đổi hạ tầng:

```text
Tăng dung lượng / đổi node type
Đổi engine version
Bật backup, tạo snapshot
Thiết lập retention
Cấu hình replication/failover
Thay các parameter được hỗ trợ
Quản lý endpoint hoặc mạng
```

Một thao tác tương đương với `CONFIG SET` hoặc `BGSAVE` ở Redis tự vận hành có thể phải thực hiện qua API/console/IaC của nhà cung cấp thay vì gửi Redis command từ Spring Boot.

Đó thường là **ranh giới quản trị có chủ đích**, không phải một lỗi cần tìm cách vượt qua.

## 3. Sáu chiều tương thích phải kiểm tra

Không nên hỏi chung chung “dịch vụ này có hỗ trợ Redis không?”. Cần chia thành những câu hỏi độc lập.

| Chiều | Câu hỏi cần trả lời |
|---|---|
| Giao thức và kết nối | TCP Redis/RESP, TLS, xác thực, proxy, timeout có tương thích với driver không? |
| Engine và phiên bản | Hỗ trợ Redis/Valkey phiên bản nào, RESP2/RESP3 và tập lệnh nào? |
| Quyền thực thi | Redis user được phép gọi những command/subcommand nào và trên những key nào? |
| Topology | Standalone, primary/replica, Sentinel, Cluster hay endpoint được nhà cung cấp trừu tượng hóa? |
| Ngữ nghĩa dữ liệu | TTL, eviction, persistence, replication, scripting và consistency có đáp ứng yêu cầu không? |
| Vận hành | Metrics, backup, restore, failover, nâng cấp, cấu hình thực hiện qua đường nào? |

Ví dụ, một dịch vụ có thể:

```text
GET / SET / EXPIRE            -> hỗ trợ
TLS                          -> bắt buộc
Redis Cluster routing        -> hỗ trợ
CONFIG SET                   -> không cấp cho app
FLUSHALL                     -> bị chặn
EVAL                         -> chỉ được phép với role riêng
RDB snapshot                 -> thao tác qua provider API
INFO memory                  -> chỉ cung cấp qua metrics service
```

Đây là **một mô hình minh họa**, không phải mô tả chính thức của một nhà cung cấp cụ thể.

Nếu dự án phụ thuộc một tính năng cụ thể, chẳng hạn `XAUTOCLAIM`, Redis Functions, RedisJSON, pub/sub hoặc các lệnh mới, phải xác định rõ **mức độ hỗ trợ của engine đang chạy** thay vì dựa trên tên thương mại của dịch vụ.

## 4. Tạo compatibility contract trước khi triển khai

Một tài liệu tương thích nên gắn với **môi trường cụ thể**, không chỉ gắn với tên provider.

Ví dụ:

```text
Environment:        production
Provider/product:   managed-redis-product
Service tier:       chosen-tier
Engine:             Redis-compatible engine
Engine version:     exact-version
Topology:           Redis Cluster
Region/network:     private endpoint
Authentication:     ACL username/password
TLS:                required
Spring Boot:        pinned version
Spring Data Redis:  pinned version
Driver:             Lettuce, pinned version
Database selection: DB 0 only
Scripting:          approved scripts only
Admin commands:     not available to application user
Observability:      provider metrics + application metrics
Backup:             provider control plane
```

Tiếp theo, liệt kê **tập command ứng dụng thật sự cần**:

| Chức năng | Ví dụ command | Có cần trong production? |
|---|---|---|
| String cache | `GET`, `SET`, `DEL`, `EXPIRE` | Có, theo code |
| Hash repository | `HGETALL`, `HSET`, `HDEL`, các lệnh index phụ | Tùy mapping |
| TTL | `TTL`, `PTTL`, `PEXPIRE` | Tùy API |
| Spring Cache clear | `KEYS`/`SCAN`, `DEL`/`UNLINK` | Chỉ nếu thật sự có region clear |
| Distributed lock | `SET NX`, script compare-and-delete | Tùy thiết kế |
| Redis Streams | `XADD`, `XREADGROUP`, `XACK`, `XAUTOCLAIM` | Tùy consumer |
| Pub/Sub | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | Tùy listener |
| Scripts | `EVALSHA`, `EVAL`, `SCRIPT LOAD` | Tùy thực thi |
| Metrics từ Redis | `INFO`, `SLOWLOG`, `MEMORY STATS` | Có thể chuyển sang provider |
| Quản trị | `CONFIG SET`, `ACL SETUSER`, `BGSAVE`, `FLUSHALL` | Thường không thuộc app |

**Nguồn xác nhận** nên gồm tài liệu provider cho đúng tier/engine/version, cấu hình quyền thực tế và integration tests trên môi trường staging tương đương production.

Không sử dụng một phép thử `PING` thành công làm bằng chứng mọi command đều tương thích.

## 5. Những nhóm lệnh thường bị hạn chế trên dịch vụ được quản lý

Tên lệnh và phạm vi hạn chế dưới đây là các **nhóm cần xác minh**, không phải danh sách cấm áp dụng cho mọi managed Redis.

### 5.1. Thay đổi cấu hình server

```redis
CONFIG GET maxmemory
CONFIG SET maxmemory-policy allkeys-lru
CONFIG REWRITE
```

Một nhà cung cấp có thể không cho client thực hiện `CONFIG SET`, vì tham số Redis được quản lý qua parameter group, service API hoặc một control plane tương ứng.

Nếu application startup tự gọi `CONFIG SET notify-keyspace-events Ex`, ứng dụng có thể hoạt động local nhưng không khởi động thành công trên managed service.

**Thay thế:** cấu hình thông qua cơ chế được nhà cung cấp hỗ trợ. Không tự retry `CONFIG SET` hàng trăm lần hoặc cấp tài khoản admin vào application để vượt hạn chế.

### 5.2. Quản lý người dùng và ACL

```redis
ACL SETUSER ...
ACL DELUSER ...
ACL LOAD
ACL SAVE
```

Một số dịch vụ quản lý user và role qua hệ thống riêng, hoặc chỉ hỗ trợ một tập con lệnh ACL. Ngay cả khi `ACL GETUSER` được phép, việc sửa ACL có thể bị chặn.

**Thay thế:** tạo và gán người dùng/role theo cơ chế của provider. Test với thông tin xác thực đúng của application.

### 5.3. Lệnh xóa diện rộng

```redis
FLUSHDB
FLUSHALL
```

Nhiều tổ chức chủ động chặn những lệnh này với application account; một số dịch vụ có thể vô hiệu hóa ở cấp engine/service.

**Thay thế:** cleanup chính xác theo key, namespace versioning hoặc maintenance job được kiểm soát. Nếu mục đích là xóa toàn deployment, sử dụng quy trình quản trị dữ liệu đã được phê duyệt, không tìm cách giả lập `FLUSHALL` bằng script tự do.

### 5.4. Thao tác hệ thống và tiến trình

Ví dụ:

```redis
SHUTDOWN
DEBUG ...
MODULE LOAD ...
CLIENT KILL ...
MONITOR
```

Các lệnh này có thể dừng dịch vụ, ảnh hưởng kết nối, tải module tùy ý hoặc bộc lộ dữ liệu.

**Thay thế:** provider operations, observability/diagnostics có kiểm soát, hoặc không sử dụng trong application path.

### 5.5. Persistence và backup

```redis
SAVE
BGSAVE
BGREWRITEAOF
LASTSAVE
```

Managed service có thể không cho ứng dụng chủ động tạo snapshot hoặc thao tác file persistence bằng Redis command. Một số product không có các khái niệm tệp RDB/AOF được expose cho tenant.

**Thay thế:** dùng backup/snapshot/restore API của provider, xác định retention, quyền truy cập và kiểm thử restore.

### 5.6. Lệnh quan sát và duyệt keyspace

```redis
INFO
SLOWLOG GET 10
MEMORY STATS
CLIENT LIST
KEYS *
SCAN 0 MATCH app:cache:*
```

Một số có thể được cho phép với tài khoản có quyền; số khác bị chặn. `KEYS *` đặc biệt không nên dùng trên dataset lớn do chi phí quét keyspace.

**Thay thế:** metrics do provider xuất, telemetry tại ứng dụng hoặc một tác vụ scan giới hạn trong môi trường được cho phép. Nếu `SCAN` bị chặn, **không fallback sang `KEYS`** để lách cơ chế kiểm soát.

### 5.7. Scripting và functions

```redis
EVAL ...
EVALSHA ...
SCRIPT LOAD ...
SCRIPT FLUSH
FUNCTION LOAD ...
FCALL ...
```

Tập quyền được hỗ trợ có thể khác nhau theo engine/version/user; một số nền tảng hạn chế scripting hoặc các thao tác quản lý function libraries.

**Thay thế:** dùng command nguyên tử tương đương nếu có, thiết kế lại atomic boundary hoặc sử dụng cơ chế được provider hỗ trợ. Không chuyển logic không nguyên tử thành hai lệnh độc lập rồi tuyên bố vẫn có cùng bảo đảm.

## 6. Bảng phân biệt “không hỗ trợ” và “không có quyền”

Một lệnh có thể không chạy vì những nguyên nhân rất khác nhau.

| Triệu chứng | Nguyên nhân cần xét | Hành động phù hợp |
|---|---|---|
| `NOPERM` | ACL/user không có quyền command hoặc key | Kiểm tra role và contract, không retry vô hạn |
| `NOAUTH` / lỗi xác thực | Client chưa xác thực hoặc credential sai | Kiểm tra secret, cơ chế auth, kết nối |
| `ERR unknown command` | Lệnh bị ẩn, không hỗ trợ hoặc không có trong engine | Kiểm tra phiên bản/tài liệu/gói dịch vụ |
| `ERR unknown subcommand` | Subcommand không có ở phiên bản đó | Kiểm tra cú pháp và version |
| `READONLY` | Đang gửi lệnh ghi tới replica hoặc node không còn writable | Kiểm tra topology/failover |
| `MOVED` | Cluster yêu cầu định tuyến lại slot | Dùng cluster-aware client/topology refresh |
| `ASK` | Chuyển hướng tạm khi resharding | Để cluster-aware driver xử lý đúng |
| `CROSSSLOT` | Multi-key command không thỏa yêu cầu cùng slot | Đổi thiết kế key/atomic operation |
| `NOSCRIPT` | Script chưa có trong cache của node hiện tại | Kiểm tra cơ chế load/fallback/quyền |
| `OOM command not allowed` | Memory policy hoặc giới hạn bộ nhớ | Quan sát memory/quota, không coi là ACL |
| Command timeout | Mạng, queue, server, tải hoặc chuyển node | Đo client/server metrics và thời gian |
| TLS handshake error | Trust chain, hostname, TLS version, cấu hình | Sửa TLS/certificate, không tắt xác minh |

Không nên viết:

```java
if (exception.getMessage().contains("NOPERM")) {
    return null;
}
```

rồi xem như cache miss. Lỗi quyền là lỗi cấu hình/bảo mật; nếu bị che, ứng dụng có thể gây cache stampede hoặc hành vi nghiệp vụ sai.

Tên exception Java cụ thể có thể khác theo Lettuce, Spring Data Redis và cách dịch vụ trả lỗi. Trong code, ưu tiên phân loại theo type và nguyên nhân có cấu trúc; khi buộc phải nhận diện mã lỗi từ response, cô lập logic đó trong một adapter và kiểm thử với phiên bản thực tế.

## 7. Chọn kiểu kết nối đúng với topology mà nhà cung cấp expose

Một dịch vụ managed Redis có thể cung cấp:

1. **Một endpoint data plane** giống standalone hoặc được proxy.
2. **Primary endpoint và read endpoint** cho topology primary/replica.
3. **Cluster configuration/seed endpoint** để client khám phá các node và hash slots.
4. **Địa chỉ Sentinel** trong những deployment thực sự dùng Sentinel.
5. **REST/HTTP API** tương thích một tập thao tác Redis nhưng không phải TCP Redis/RESP.

Không mặc định rằng một managed service có replica sẽ cho ứng dụng kết nối qua Sentinel. Nhà cung cấp có thể thực hiện failover và duy trì endpoint theo cơ chế riêng.

### 7.1. Một endpoint dữ liệu

Ví dụ Spring Boot 3.x:

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

Ở đây `REDIS_*` là biến cấu hình/secret được cung cấp từ môi trường, **không commit giá trị thật vào repository**.

Trường `ssl.enabled` là ví dụ cho endpoint yêu cầu TLS. Nếu nhà cung cấp dùng endpoint/proxy khác, cần cấu hình phù hợp với yêu cầu thật.

### 7.2. Redis Cluster

Nếu nhà cung cấp cung cấp **Redis Cluster thật** với hash slots:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - ${REDIS_CLUSTER_NODE_1}
          - ${REDIS_CLUSTER_NODE_2}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 2s
```

Ví dụ biến:

```text
REDIS_CLUSTER_NODE_1=redis-seed-a.internal:6379
REDIS_CLUSTER_NODE_2=redis-seed-b.internal:6379
```

Đây là **seed nodes**, không phải danh sách cố định mọi primary/replica. Driver cluster-aware khám phá topology và tiếp tục kết nối đến node sở hữu slot.

Điều cần thử:

- DNS và TLS certificate của các node được công bố.
- Ứng dụng có thể truy cập mọi địa chỉ node mà Cluster trả về.
- Redis cluster bus/đường nội bộ được cấu hình đúng ở hạ tầng.
- Redis Cluster slots đều được phân bổ.
- Lettuce topology refresh theo được reshard/failover.
- Connection authentication có hiệu lực trên các node liên quan.

Nếu dịch vụ chỉ expose một proxy endpoint và tự định tuyến ở phía server, cấu hình client có thể khác; **không ép cấu hình cluster seed chỉ vì tài liệu bán hàng dùng từ “cluster”**.

### 7.3. Redis Sentinel

Chỉ cấu hình Sentinel khi nhà cung cấp thực sự cung cấp Sentinel endpoints:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

Các cấu hình xác thực riêng dành cho Sentinel có thể cần thêm tùy Spring Boot/driver/Redis topology. Ví dụ trên chỉ cho thấy cấu trúc, không thay thế contract bảo mật của dịch vụ cụ thể.

**Không dùng Sentinel config để kết nối một managed service chỉ cấp primary/reader endpoint mà không cung cấp Sentinel.**

### 7.4. HTTP API khác với Redis TCP protocol

Một số sản phẩm serverless dùng HTTP endpoints và API riêng. Nếu chỉ có HTTP API mà không có Redis RESP endpoint tương thích, `LettuceConnectionFactory` không thể tự biến thành HTTP Redis client.

Cần kiểm tra:

```text
Provider exposes RESP over TCP/TLS? -> Dùng Lettuce/Jedis khi hỗ trợ.
Provider exposes proprietary HTTP?  -> Dùng SDK/API tương ứng.
```

Không suy đoán rằng mọi dịch vụ có chữ “Redis” đều chạy được Spring Data Redis TCP connection factory.

## 8. TLS và chứng chỉ khi triển khai Spring Data Redis

Trên managed service, TLS có thể là yêu cầu bắt buộc. Sự khác nhau giữa development và production thường nằm ở:

```text
Local:
  redis://localhost:6379
Managed:
  rediss://private-host:6379
```

Với Spring Boot:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
```

Những điều cần xác minh:

- Trust store của JVM có tin CA/chain của provider không?
- Hostname Redis endpoint có khớp tên trong certificate không?
- Có TLS proxy hoặc private DNS không?
- Có yêu cầu TLS tối thiểu hoặc mutual TLS không?
- Cert rotation có làm connection pool cũ lỗi khi reconnect không?
- `connect-timeout` và `timeout` có đủ ngân sách cho handshake và operation không?
- Client có đang dùng endpoint nội bộ đúng VPC/VNet không?

### 8.1. Không bỏ qua hostname verification

Một cách “sửa nhanh” không an toàn là cấu hình trust-all hoặc tắt xác minh certificate trên production. Điều đó làm yếu bảo mật truyền tải và có thể che việc kết nối nhầm endpoint.

Nếu TLS thất bại, cần sửa chain tin cậy/hostname/network theo cấu hình provider, không tắt xác minh chỉ để bài test pass.

### 8.2. Không log Redis URI có credential

Ví dụ một URI:

```text
rediss://user:secret@redis-host:6379
```

có chứa thông tin nhạy cảm. Một exception hoặc log debug có thể vô tình phơi bày URI, tên key hoặc command arguments.

Ghi log dạng an toàn:

```text
component=redis
endpointAlias=product-cache-prod
operation=cache_read
failureCategory=TLS_HANDSHAKE
```

Không log password, access token, dữ liệu cache hoặc full command.

## 9. ACL username/password và cơ chế xác thực động

Managed Redis có thể dùng:

- Username/password theo Redis ACL.
- Password-only trong cấu hình được provider hỗ trợ.
- Secret do hệ thống quản lý danh tính của provider cấp hoặc xoay vòng.
- Token xác thực tạm thời (ví dụ integration dựa trên IAM), tùy dịch vụ và engine.
- TLS client certificate trong những kiến trúc có hỗ trợ.

Không nên coi chúng là các cơ chế thay thế lẫn nhau mà không kiểm tra contract.

### 9.1. Spring Boot dùng credentials tĩnh từ secret manager

Ví dụ:

```yaml
spring:
  data:
    redis:
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

Một deployment nên đảm bảo:

- Secret chỉ được cung cấp cho workload cần thiết.
- Không ghi secret trong source code, log, crash dump hoặc lệnh command-line.
- Có kế hoạch rotation.
- Các node mới sau failover cũng nhận đúng cơ chế xác thực.
- Người dùng Redis chỉ có tập command và key prefix cần thiết.

### 9.2. Token ngắn hạn cần cơ chế làm mới đúng

Nếu dịch vụ yêu cầu authentication token có thời hạn, ứng dụng không thể luôn lấy token tại startup rồi dùng mãi. Cần xét:

- Thời hạn token.
- Cách tạo token mới.
- Kết nối mới sử dụng token nào.
- Kết nối cũ có cần được tái xác thực/reconnect không.
- Lettuce/client version có hỗ trợ cơ chế cung cấp credential động theo service không.
- Pool và topology refresh có dùng token mới không.
- Failover/reconnect trong thời điểm token đổi.

**Không tự viết mã “refresh token sau mỗi GET”** nếu provider đã cung cấp driver integration đúng. Ngược lại, nếu client không hỗ trợ token rotation, phải thiết kế lại kết nối hoặc sử dụng SDK/connector được hỗ trợ.

### 9.3. Redis ACL vẫn cần least privilege

Dịch vụ có thể hỗ trợ user/role, nhưng **managed không có nghĩa tự an toàn cho mọi application user**.

Một product-read API thường không cần quyền:

```text
FLUSHALL
CONFIG SET
ACL SETUSER
SCRIPT FLUSH
MODULE LOAD
```

Nếu code sử dụng `GET`, `MGET`, `TTL`, chỉ cấp các command cần thiết và namespace được phép, theo khả năng của provider.

Với lệnh bị từ chối, **không tự nâng quyền tài khoản ứng dụng lên admin** để “sửa production nhanh”.

## 10. Spring Data Redis connection factory và trách nhiệm cấu hình

`RedisConnectionFactory` là ranh giới quan trọng giữa Spring Data Redis và driver.

```text
Spring service
      |
      v
RedisTemplate / RedisCacheManager
      |
      v
RedisConnectionFactory
      |
      v
Lettuce / Jedis
      |
      v
Managed Redis endpoint
```

Nếu application đã tự tạo `LettuceConnectionFactory`, một phần Redis properties mà Spring Boot auto-configuration thường xử lý có thể **không được áp dụng** như bạn mong đợi.

Cần kiểm tra:

1. Có bao nhiêu `RedisConnectionFactory` beans?
2. Bean nào được Spring Cache và `RedisTemplate` sử dụng?
3. Có `@Primary` và `@Qualifier` rõ ràng không?
4. TLS, username/password, timeout và topology đặt ở đâu?
5. `LettuceClientConfigurationBuilderCustomizer` có thực sự được áp dụng không?
6. Có một service dùng connection factory cũ trỏ nhầm Redis development không?
7. Health indicators có dùng cùng endpoint và credential đúng không?

### 10.1. Không trộn mode

Sai về ý tưởng:

```text
Provider exposes Cluster seed endpoint
App configures standalone host/port
App works for some keys
App fails on redirect or reshard
```

Hoặc:

```text
Provider manages failover via stable endpoint
App invents Sentinel addresses
App fails to discover primary
```

Chọn cấu hình theo **mô hình mà provider thực tế expose**, không dựa vào giả định của môi trường local.

## 11. Redis Cluster: hash slots và giới hạn lệnh nhiều key

Trong Redis Cluster, key được ánh xạ tới **16.384 hash slots**.

Ví dụ:

```text
cart:42
cart:43
```

có thể thuộc các slot khác nhau. Một số lệnh nhiều key và các Lua scripts cần mọi key liên quan nằm cùng hash slot.

### 11.1. Dùng hash tag cho dữ liệu liên quan

Ví dụ:

```text
cart:{42}:header
cart:{42}:items
```

Hai key chia sẻ hash tag `{42}` nên được ánh xạ cùng slot.

Có thể xác nhận trong môi trường Cluster cho phép:

```redis
CLUSTER KEYSLOT cart:{42}:header
CLUSTER KEYSLOT cart:{42}:items
```

Điều này giúp một số thao tác nhiều key có thể chạy đúng giới hạn Cluster.

**Không dùng một hash tag cố định cho mọi key toàn hệ thống**, vì có thể dồn toàn bộ tải vào một slot.

### 11.2. CROSSSLOT không phải lỗi transient

Nếu script hoặc lệnh nhiều key cần cùng slot nhưng được gọi với keys khác slot:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Retry vô hạn không làm hai key chuyển về cùng slot. Đây là lỗi thiết kế key/operation hoặc lỗi trong migration namespace.

### 11.3. SELECT và logical database

Redis Cluster sử dụng database 0. Không giả định có thể chọn `SELECT 1`, `SELECT 2` trên Cluster giống Redis standalone.

Thay vì dùng nhiều logical databases để phân chia nghiệp vụ, có thể dùng namespace key:

```text
app:cache:products:*
app:sessions:*
```

Nhưng namespace **không phải cơ chế cách ly bảo mật và tài nguyên hoàn chỉnh**. Nếu cần memory policy/quota/bảo mật độc lập, cân nhắc các Redis databases/deployments hoặc service instances riêng theo khả năng provider.

## 12. Redis phiên bản và tập lệnh: đừng dựa vào tài liệu “latest” một cách mù quáng

Spring Data Redis và Redis server có vòng đời version riêng:

```text
Spring Boot version
  |
  +--> Spring Data Redis version
  |
  +--> Lettuce/Jedis version
  |
Managed Redis engine/version/tier
```

Một API trong thư viện Java có thể tồn tại ngay cả khi Redis server chưa hỗ trợ lệnh tương ứng.

Ví dụ các tính năng cần kiểm tra đúng phiên bản:

- Redis Streams và consumer groups.
- `XAUTOCLAIM`.
- Một số lệnh/option Redis Streams về xử lý ACK và deletion mới hơn.
- Redis Functions (`FCALL`, `FUNCTION ...`).
- ACL, ACL key/channel patterns, `ACL DRYRUN`.
- `GETEX`, `SET` options, expiration options.
- Redis modules hoặc module-like data types.
- RESP3, client tracking và những tính năng protocol liên quan.

### 12.1. Spring API có sẵn không có nghĩa server hỗ trợ

Ví dụ:

```java
streamOperations.autoClaim(...);
```

nếu Spring Data Redis version cung cấp API, nhưng engine đang chạy không hỗ trợ command, server vẫn có thể trả lỗi.

Do đó, trước khi dùng tính năng mới:

1. Xác định lệnh Redis cần thiết.
2. Xác định engine version/tier của provider.
3. Kiểm tra quyền của application user.
4. Kiểm thử với service thật trong staging.
5. Thiết kế fallback phù hợp **nếu ngữ nghĩa cho phép**.

Không thay một lệnh nguyên tử bằng chuỗi lệnh rời rạc chỉ vì muốn bỏ qua lỗi “unknown command”.

### 12.2. Redis-compatible không mặc nhiên giống Redis OSS

Một số engine hoặc proxy tương thích Redis chỉ triển khai một tập con của command set, hoặc có khác biệt về persistence, pub/sub, script, blocking commands và concurrency.

Các câu hỏi cần hỏi:

```text
Dùng được Redis RESP TCP hay không?
Có hỗ trợ pipeline và transaction không?
Lua scripting có cùng giới hạn hay không?
Redis Streams có consumer groups/PEL đầy đủ không?
Có hỗ trợ blocking reads không?
Pub/Sub có kết nối dài hạn không?
TTL/eviction có cùng ngữ nghĩa không?
Có module/RedisJSON/RediSearch tương đương không?
Có quota theo request, memory hoặc connection không?
```

Không chỉ dùng một benchmark `SET/GET` để tuyên bố “hoàn toàn tương thích”.

## 13. Lệnh quản trị bị chặn: sửa workflow, không tìm cách lách

Giả sử startup code gọi:

```redis
CONFIG SET notify-keyspace-events Ex
```

Trong Redis local có quyền admin, lệnh thành công. Trên managed service, tài khoản ứng dụng có thể bị từ chối.

Sai về hướng xử lý:

```text
CONFIG SET bị chặn
       |
       v
Thử một script EVAL gọi CONFIG SET
       |
       v
Mở quyền EVAL hoặc ACL admin cho app
```

Đúng hơn:

```text
CONFIG SET bị chặn
       |
       v
Kiểm tra provider có hỗ trợ setting không?
       |
       +-- Có -> cấu hình qua control plane/parameter group
       |
       +-- Không -> thay đổi thiết kế dựa trên event/TTL/logic khác
```

Nếu tính năng hoàn toàn không hỗ trợ, cần sửa kiến trúc hoặc chọn gói dịch vụ khác. **Tìm cách vượt ACL là sai ranh giới bảo mật.**

### 13.1. Bảng command bị chặn và phương án thay thế

| Command/nhóm | Tại sao có thể bị hạn chế | Phương án hợp lệ |
|---|---|---|
| `CONFIG SET` | Provider kiểm soát tham số | Service config/control plane/IaC |
| `CONFIG REWRITE` | Không cho sửa file server | Quản trị cấu hình theo provider |
| `ACL SETUSER` | User/roles do provider quản lý | Identity/ACL management API |
| `BGSAVE` | Backup do nền tảng điều phối | Snapshot/backup API |
| `SHUTDOWN` | Provider quản lý lifecycle | Maintenance/failover API có kiểm soát |
| `MONITOR` | Hiệu năng và lộ payload | Exported metrics, tracing được phép |
| `FLUSHALL` | Rủi ro xóa diện rộng | Namespace/version hoặc purge qua maintenance |
| `KEYS` | Quét keyspace lớn | `SCAN` nếu được cấp; hoặc data index riêng |
| `EVAL` | Code động và rủi ro tải | Script đã duyệt nếu hỗ trợ; atomic command khác |
| `FUNCTION LOAD` | Quản trị code server-side | Quy trình deploy function do provider hỗ trợ |
| `MODULE LOAD` | Security/engine integrity | Module/tính năng được provider cung cấp |
| `SELECT` (Cluster) | Cluster chỉ dùng DB 0 | Namespace/cách ly instance |
| `DUMP`/`RESTORE` | Có thể giới hạn export/import | Công cụ migration/backup được hỗ trợ |

Không phải dòng nào trong bảng cũng bị chặn trên mọi provider. Đây là **danh sách điểm kiểm tra**.

## 14. Redis Cache và rủi ro xóa cả cache region

Spring Data Redis có thể được dùng qua Spring Cache:

```java
@Cacheable(cacheNames = "products", key = "#id")
public Product findById(long id) {
    return repository.findById(id).orElse(null);
}
```

Và invalidation một entry:

```java
@CacheEvict(cacheNames = "products", key = "#id")
public void updateProduct(long id) {
    // Cập nhật dữ liệu có thẩm quyền.
}
```

Nhưng cũng có:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearAllProducts() {
}
```

`allEntries = true` là thao tác **clear cả cache region**, có thể phải duyệt/xóa rất nhiều Redis keys.

### 14.1. Vì sao managed service có thể làm clear thất bại?

Tùy phiên bản/cấu hình, `RedisCacheWriter` có thể sử dụng chiến lược dựa trên `KEYS` và `DEL` để clear cache. Nếu Redis user không được phép gọi `KEYS`, quá trình clear bị từ chối.

Đây có thể là tác dụng đúng của một ACL được thiết kế chặt chẽ. Không nên mở `KEYS` cho toàn bộ application chỉ vì một endpoint ít dùng cần clear region.

### 14.2. Dùng SCAN batch strategy khi được hỗ trợ

Ví dụ Spring Data Redis:

```java
package com.example.redis.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheManagerConfiguration {

    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheWriter writer =
                RedisCacheWriter.nonLockingRedisCacheWriter(
                        connectionFactory,
                        BatchStrategies.scan(500)
                );

        return RedisCacheManager
                .builder(writer)
                .build();
    }
}
```

Điều này cho phép writer dùng batch scanning cho thao tác được hỗ trợ, tránh những vấn đề của `KEYS` trên keyspace lớn.

Nhưng cần hiểu:

- `SCAN` vẫn cần quyền phù hợp.
- `SCAN` có thể trả key lặp hoặc dữ liệu thay đổi.
- Một clear region vẫn có thể xóa hàng triệu key.
- Redis Cluster có giới hạn scan/route theo driver và phiên bản.
- `SCAN` không tự trở thành một transaction xóa toàn region.
- Phải kiểm tra phiên bản Lettuce/Jedis, Spring Data Redis và khả năng của provider.

**Không đổi chiến lược KEYS sang SCAN rồi coi như đã cấp quyền cho endpoint public clear cả cache.** Xóa diện rộng nên thuộc maintenance workflow riêng.

### 14.3. Nếu SCAN cũng không được phép

Một số ứng dụng có thể không cần clear region tại runtime. Có thể:

- Chỉ invalidation theo ID mà ứng dụng biết.
- Dùng namespace versioning khi cần làm lạnh một thế hệ cache.
- Để key cũ hết TTL theo chính sách.
- Xây danh sách key/ID ở nguồn authoritative nếu nghiệp vụ cho phép.
- Dùng maintenance API chính thức của provider.
- Tách cache sang instance riêng để quản trị vòng đời dễ hơn.

Không fallback sang `KEYS *` hoặc `FLUSHALL` vì `SCAN` không được cấp.

## 15. Namespace versioning thay cho xóa hàng loạt

Giả sử cache v1:

```text
catalog:product:v1:42
catalog:product:v1:43
```

Khi schema hoặc dữ liệu cần invalidation rộng, ứng dụng mới chuyển sang:

```text
catalog:product:v2:42
catalog:product:v2:43
```

Ưu điểm:

- Không cần duyệt xóa toàn bộ keyspace ngay.
- Giảm phụ thuộc quyền `KEYS`, `SCAN`, `FLUSHALL`.
- Cho phép rolling deployment có kiểm soát.
- Key cũ có thể tự hết TTL.

Đánh đổi:

- Dữ liệu v1 vẫn chiếm memory tới lúc hết hạn/xóa.
- Tỷ lệ cache hit giảm trong giai đoạn cache mới còn lạnh.
- Database có thể nhận tải cao nếu không warm cache.
- Phải bảo đảm không còn writer cũ làm lệch dữ liệu cần truy cập.
- Nếu Redis lưu dữ liệu authoritative, **đổi namespace mà không migration là không đủ**.

Namespace versioning là chiến lược quản trị **cache có thể tái tạo**, không phải lời giải cho mọi loại dữ liệu.

## 16. Lua scripting trên managed service: không chỉ kiểm tra EVAL

Spring Data Redis hỗ trợ server-side Lua scripts để thực hiện thao tác nguyên tử, ví dụ release lock theo owner.

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Trong một Redis server bình thường, script xử lý `GET` và `DEL` theo một atomic execution boundary.

Nhưng để chạy được trên managed service, phải kiểm tra ít nhất:

- Engine có hỗ trợ Lua scripting không?
- `EVAL`, `EVALSHA` và cơ chế script cache được phép ra sao?
- Application user có quyền gọi script và những lệnh nội bộ không?
- Script có truy cập những key thuộc key patterns được cấp không?
- Nếu dùng Redis Cluster, các key có cùng slot không?
- Có giới hạn thời gian/số lượng lệnh/tài nguyên cho script không?
- Cơ chế reconnect, restart, failover xử lý script cache thế nào?

### 16.1. EVALSHA và NOSCRIPT

Một chuỗi thực thi có thể là:

```text
Application
    |
    | EVALSHA <sha> ...
    v
Redis node
    |
    +-- Script có trong cache -> execute
    |
    +-- Script không có        -> NOSCRIPT
                                    |
                                    v
                             Client fallback EVAL?
```

Các phiên bản Spring Data Redis phổ biến có cơ chế thử `EVALSHA` và fallback sang `EVAL` khi cần, tùy API/connection. Nếu application user chỉ được phép `EVALSHA` nhưng không có đường load/script tương ứng, lần chạy đầu trên node mới có thể lỗi.

**Không mặc định script SHA sẽ tồn tại trên mọi node, mọi failover và mọi lúc.** Với Redis Cluster, script cache/connection có thể gắn với node.

### 16.2. Script cố định trong source

Ví dụ:

```java
package com.example.redis.script;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class LeaseReleaseService {

    private static final String RELEASE_LUA = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public LeaseReleaseService(StringRedisTemplate redis) {
        this.redis = redis;
        this.script = new DefaultRedisScript<>();
        this.script.setScriptText(RELEASE_LUA);
        this.script.setResultType(Long.class);
    }

    public boolean release(String resourceId, String owner) {
        if (resourceId == null
                || !resourceId.matches("[a-zA-Z0-9._-]{1,80}")) {
            throw new IllegalArgumentException("Invalid resourceId");
        }

        String key = "app:lock:{" + resourceId + "}";

        Long deleted = redis.execute(
                script,
                List.of(key),
                owner
        );

        return Long.valueOf(1L).equals(deleted);
    }
}
```

Ví dụ này thể hiện script cố định được tham số hóa bằng `KEYS`/`ARGV`. Nó vẫn cần authorization ở tầng nghiệp vụ và Redis ACL thích hợp.

**Cần xem lại riêng:** nếu provider không hỗ trợ `EVAL`, không thể đơn giản đổi thành `GET` rồi `DEL` hai lệnh rời rạc mà giữ nguyên bảo đảm compare-and-delete. Phải tìm primitive được hỗ trợ hoặc thay thiết kế lock/ownership.

### 16.3. Script không vượt quyền ACL

Không nên dùng `EVAL` như một cách vượt qua `NOPERM`. Các lệnh trong script vẫn phải thỏa quy tắc quyền tương ứng. Đồng thời, nếu cấp scripting và command permissions quá rộng, ứng dụng có thể thực hiện nhiều tác dụng phụ hơn dự kiến.

Với hệ thống yêu cầu chỉ gọi một script đã được phê duyệt, cần thiết kế quyền/entry point và quy trình review; `EVALSHA` không tự là ACL allowlist per-SHA.

### 16.4. Redis Functions

Redis Functions có lifecycle khác với Lua script cache. Việc gọi function (`FCALL`, `FCALL_RO`) và quản trị thư viện function (`FUNCTION LOAD`, `FUNCTION DELETE`, `FUNCTION FLUSH`) là những quyền riêng cần đánh giá.

Nếu provider hỗ trợ gọi function nhưng không cho application deploy library, nhóm hạ tầng có thể phải thực hiện deployment qua quy trình riêng.

## 17. Kiểm thử script sau failover và engine upgrade

Một script có thể hoạt động trên node cũ nhưng lỗi sau:

- Redis restart.
- Primary/replica failover.
- Cluster reshard.
- Engine upgrade.
- Xoay vòng user/ACL.
- Thay đổi script/function deployment.

Test case:

1. Khởi tạo dữ liệu test và xác nhận script chạy được.
2. Kiểm tra Redis user có đúng command/key permissions.
3. Trong staging, thực hiện failover có kiểm soát.
4. Gọi lại script qua chính `RedisTemplate` mà production dùng.
5. Xác nhận behavior khi `NOSCRIPT`, `NOPERM` và timeout.
6. Kiểm tra dữ liệu không bị ghi hai lần hoặc giải phóng lock nhầm owner.
7. Nếu không có capability scripting, test phải xác nhận ứng dụng **không bật feature phụ thuộc script**.

Đối với timeout sau script ghi, không mặc định script chưa chạy; cần idempotency hoặc đọc lại trạng thái bằng cách an toàn theo nghiệp vụ.

## 18. Dịch vụ được quản lý và Redis Pub/Sub, Streams

Không phải mọi dịch vụ có giao thức Redis giống nhau đều có đầy đủ khả năng nhắn tin.

### 18.1. Pub/Sub

Redis Pub/Sub thông thường dùng kết nối dài hạn:

```redis
SUBSCRIBE events:product
PUBLISH events:product "{\"id\":42}"
```

Nếu ứng dụng dùng `RedisMessageListenerContainer`, phải xác minh:

- Dịch vụ hỗ trợ Pub/Sub với TCP connection theo mô hình client không?
- Dịch vụ có giới hạn kết nối/subscription không?
- Reconnect sau failover có hoạt động không?
- Channel ACL có cho phép subscribe/publish không?
- Trong Cluster có yêu cầu subscribe những node nào cho loại notification đang dùng không?

**Pub/Sub không có replay/ACK mặc định.** Managed failover không biến nó thành một message queue bền vững. Thông điệp phát trong lúc subscriber offline có thể bị mất.

### 18.2. Redis Streams

Nếu ứng dụng dùng:

```redis
XADD orders:events * type CREATED id 42
XREADGROUP GROUP billing consumer-1 STREAMS orders:events >
XACK orders:events billing <entry-id>
```

cần xác minh:

- Redis engine version có đầy đủ các lệnh Streams đang sử dụng.
- `XGROUP`/`XREADGROUP`/`XPENDING`/`XAUTOCLAIM` được hỗ trợ.
- Blocking reads được provider/proxy cho phép và có timeout thích hợp.
- Consumer group state sống sót qua recovery theo hợp đồng durability.
- Retention không xóa payload trước khi consumer xử lý.
- App có idempotency để xử lý retry/pending reclaim.

Nếu một Redis-compatible HTTP API không hỗ trợ blocking group reads, không thể chỉ thay endpoint mà giữ nguyên `StreamMessageListenerContainer` và mong mọi thứ hoạt động.

### 18.3. Keyspace notifications

Một số ứng dụng dùng expired-key events:

```text
__keyevent@0__:expired
```

Tính năng này phụ thuộc `notify-keyspace-events`. Trên managed service, ứng dụng có thể không được phép chạy:

```redis
CONFIG SET notify-keyspace-events Ex
```

Nếu provider không hỗ trợ cấu hình sự kiện, nên thiết kế thay thế: database expiration policy, scheduled reconciliation, explicit event hoặc cơ chế được quản lý phù hợp.

**Không dựa vào keyspace Pub/Sub notifications như một nguồn sự kiện không thể mất**, vì subscriber offline có thể bỏ lỡ thông báo.

## 19. Redis Repositories và các lệnh “ẩn” sau API tiện lợi

Spring Data Redis Repository có thể dùng nhiều loại cấu trúc Redis:

```java
@RedisHash("profiles")
public class Profile {
    @Id
    private String id;

    @Indexed
    private String email;
}
```

Một lời gọi:

```java
profileRepository.save(profile);
```

có thể không tương đương với một `SET` đơn giản. Tùy mapping và tính năng sử dụng, repository có thể ghi:

- Redis Hash.
- ID sets.
- Secondary index sets.
- TTL hoặc expire metadata.
- Các key phụ liên quan sự kiện hết hạn.

Nếu tạo Redis user chỉ có:

```text
+get +set
```

Repository có thể báo `NOPERM` vì cần `HSET`, `SADD`, `EXPIRE` hoặc lệnh khác.

**Cấp quyền theo tập command mà feature thực sự phát**, bao gồm các thao tác phụ của Spring Data Redis.

### 19.1. Không mở `+@all` khi repository thất bại

Quy trình hợp lý:

1. Xác định chức năng Java đang thất bại.
2. Phân loại exception và Redis command bị từ chối qua nguồn được phép.
3. Kiểm tra chính sách ACL và tài liệu feature.
4. Bổ sung đúng command/key permissions nếu có lý do.
5. Chạy regression integration tests.
6. Không dùng tài khoản admin cho mọi repository chỉ để tránh cấu hình ACL.

### 19.2. Secondary indexes và Cluster

Redis Repository có thể có những thao tác liên quan nhiều key. Trong Redis Cluster, hash slots, cách framework thực thi và các giới hạn cross-slot có thể tạo khác biệt.

Nếu ứng dụng dùng repository indexes hoặc transaction/multi-key writes, cần integration test với **managed Cluster thực** và layout key thực, không chỉ test một Redis standalone container.

## 20. Health checks: không biến lệnh bị cấm thành dấu hiệu ứng dụng chết

Một service Spring Boot thường có:

```text
/actuator/health
/actuator/health/readiness
```

Redis health contributor có thể sử dụng những Redis commands để kiểm tra dependency, tùy phiên bản Spring Boot và driver.

Nếu một health probe cần `INFO` nhưng application user không có quyền, readiness có thể bị đánh dấu DOWN dù `GET`/`SET` nghiệp vụ vẫn hoạt động.

Ngược lại, một `PING` thành công chỉ chứng minh kết nối và Redis trả lời lệnh đó, **không chứng minh** cache write, serializer, routing và ACL của lệnh thực sự hoạt động.

### 20.1. Liveness khác readiness

- **Liveness:** tiến trình Java có còn hoạt động và có khả năng tự tiếp tục?
- **Readiness:** tiến trình đã sẵn sàng nhận traffic theo dependency policy chưa?

Nếu Redis tạm lỗi và Kubernetes liên tục restart mọi pod vì liveness phụ thuộc Redis, ứng dụng có thể tạo thêm reconnect storm mà không giúp Redis phục hồi.

Cần thiết kế:

```text
Liveness -> chủ yếu phản ánh tình trạng ứng dụng.
Readiness -> phản ánh khả năng phục vụ theo hợp đồng.
```

Nếu Redis chỉ là cache với fallback database, readiness có thể khác với một service phụ thuộc Redis Streams như nguồn xử lý chính. Quyết định theo yêu cầu nghiệp vụ.

### 20.2. Smoke test quyền hạn đúng nghiệp vụ

Thay vì chỉ probe:

```redis
PING
```

trên một môi trường staging, kiểm tra một thao tác có phạm vi an toàn:

```text
SET it:<run-id>:probe <value> EX 60
GET it:<run-id>:probe
DEL it:<run-id>:probe
```

Với production, không nên buộc readiness ghi key liên tục ở tốc độ cao chỉ để xác nhận Redis; cần giới hạn tần suất và chọn health strategy phù hợp.

Nếu app chỉ là reader, probe phải dùng những lệnh thực sự được cấp; không yêu cầu quyền `SET` chỉ vì health checker chọn sai phép thử.

### 20.3. Tách vận hành và ứng dụng

Metrics exporter hoặc monitoring agent có thể dùng tài khoản riêng được cấp quyền read-only cho `INFO`, nếu dịch vụ cho phép. Web app không cần chia sẻ credentials metrics và không nên được cấp mọi lệnh giám sát chỉ để phục vụ dashboard.

## 21. Logging và observability khi lệnh bị từ chối

Tại tầng Spring Data Redis, lỗi có thể được ánh xạ sang `DataAccessException` và những exception khác. Thông điệp từ driver có thể chứa key, endpoint hoặc command.

Không nên log:

```java
log.error(
        "Redis command failed: key={}, value={}, error={}",
        key,
        value,
        ex.getMessage()
);
```

Một log có cấu trúc an toàn hơn:

```text
event=redis_operation_failed
environment=production
component=product-cache
operation=product_cache_read
failureCategory=ACL_DENIED
exceptionType=RedisCommandExecutionException
endpointAlias=managed-cache-prod
traceId=<internally-generated-id>
```

Tùy phiên bản, exception type thật có thể khác. Ghi nhóm lỗi và type đã được chuẩn hóa; không dùng message chưa kiểm soát làm metric label.

### 21.1. Metrics cần có

| Metric / dấu hiệu | Câu hỏi |
|---|---|
| Connection/auth failures | Credentials/TLS/endpoint có lỗi không? |
| Command permission denied | ACL có thiếu hoặc phát hiện lệnh ngoài thiết kế không? |
| Unknown command errors | Engine version/tier có thiếu tính năng không? |
| Redis timeout rate | Service có đang bị quá tải hoặc lỗi mạng? |
| Retry rate | Có nguy cơ retry storm không? |
| Cache hit/miss/error | Cache có hoạt động hữu ích không? |
| Redis memory/evictions | Có đang gần quota hoặc thiếu memory không? |
| Current connections | Client pools có vượt giới hạn không? |
| Failover events | Có liên quan tới lỗi/reconnect không? |
| Slot redirects/reconnects | Cluster topology có cập nhật đúng không? |
| Script errors/NOSCRIPT | Server-side code có được quản lý đúng không? |

Nếu các lệnh `INFO`, `SLOWLOG` hoặc `MONITOR` không được phép, ưu tiên **provider metrics** và ứng dụng metrics, không cấp admin cho mọi microservice.

### 21.2. Thông tin cần ghi mà không lộ dữ liệu

Nên ghi:

```text
service alias
operation alias from allowlist
error category
engine version / deployment version
time window
retry count
latency
correlation ID
```

Không nên ghi:

```text
Redis password
IAM auth token
full connection URL
entire Lua script arguments
raw cache value
session token
full Redis key nếu chứa dữ liệu nhạy cảm
```

Đặc biệt, `MONITOR` và một số diagnostic commands có thể bộc lộ command arguments. Chúng không thích hợp làm log nguồn mở dài hạn.

## 22. Cần hiểu giới hạn connection và throughput

Managed Redis thường có quota hoặc giới hạn theo tier:

- Số connection.
- Memory/dataset size.
- CPU/throughput hoặc network.
- Kích thước/loại lệnh.
- Số lệnh mỗi giây hoặc chi phí theo request.
- Số node/shard.
- Số database hoặc giới hạn topology.
- Thời gian timeout cho kết nối, script, blocking read.
- Số replica và tính năng read routing.

Những giá trị cụ thể thay đổi theo provider/tier, nên không đưa một con số cố định làm quy tắc chung.

### 22.1. Lettuce multiplexing không có nghĩa kết nối vô hạn

Lettuce hỗ trợ chia sẻ/multiplex nhiều command trên connection theo cách triển khai. Nhưng:

- Có thể vẫn cần connection chuyên dụng cho Pub/Sub hoặc blocking operations.
- Client pool nếu cấu hình sai có thể tạo nhiều connection hơn dự kiến.
- Mỗi application replica/pod đều tạo workload riêng.
- Deploy 100 pods có thể làm số connection tăng rất nhanh.
- Reconnect sau outage có thể tạo đột biến kết nối đồng thời.

Một kế hoạch capacity nên tính:

```text
Số application pods
x số kết nối trung bình/tối đa mỗi pod
+ maintenance/monitoring connections
+ dự phòng reconnect/failover
```

### 22.2. Pipelining và giới hạn lệnh

Pipelining giảm round trips nhưng không làm biến mất hạn mức memory, command size hay CPU. Một pipeline chứa hàng trăm nghìn lệnh có thể tạo queue/buffer lớn phía client hoặc server.

Nên:

- Đặt batch size hữu hạn.
- Giới hạn in-flight commands.
- Có timeout tổng và retry có kiểm soát.
- Tránh gửi bulk writes trong lúc managed service đang failover.
- Đo p95/p99 latency, không chỉ throughput trung bình.

## 23. Retry trên managed service: không được làm sai nghiệp vụ

Một timeout không chứng minh lệnh chưa chạy.

Ví dụ:

```text
Client                   Redis
   |                      |
   | INCR counter ------->|
   |                      | counter tăng một lần
   |     response lost     |
   |<--- timeout           |
   |                      |
   | Retry INCR ---------> | counter tăng lần thứ hai
```

Các lệnh cần đặc biệt thận trọng khi retry:

| Lệnh | Nguy cơ |
|---|---|
| `GET` | Thường không có side effect, nhưng tăng tải |
| `SET` cùng value | Có thể an toàn về value, nhưng TTL/version cần xét |
| `INCR` | Có thể tăng hai lần |
| `LPUSH` | Có thể tạo phần tử trùng |
| `XADD` | Có thể tạo entry trùng |
| `ZINCRBY` | Có thể cộng score hai lần |
| `EVAL` có tác dụng ghi | Tùy script, có thể không idempotent |
| Transaction Redis | Kết quả có thể mơ hồ nếu mất response sau `EXEC` |

Vì vậy, khi xử lý failover hoặc service throttling:

- Retry đọc theo ngân sách có thể phù hợp.
- Retry ghi cần operation ID/idempotency khi có side effect.
- `NOPERM`/unknown command/CROSSSLOT thường không thể giải quyết bằng retry cùng yêu cầu.
- Dùng backoff và jitter để tránh retry storm.
- Không tự gửi lại giao dịch nhiều lần chỉ vì client báo timeout.

## 24. Memory, maxmemory và eviction thuộc phạm vi nào?

Trong Redis tự vận hành, người quản trị có thể điều chỉnh:

```redis
CONFIG SET maxmemory ...
CONFIG SET maxmemory-policy ...
```

Trên managed service, việc chọn kích thước instance hoặc policy có thể phải thực hiện qua control plane.

### 24.1. Không coi `maxmemory` là toàn bộ dung lượng RAM

Redis còn cần bộ nhớ cho:

- Client/replication buffers.
- Allocator overhead và fragmentation.
- Persistence/fork/copy-on-write trong các cấu hình phù hợp.
- Metadata và hoạt động nội bộ.

Managed provider có thể dành một phần bộ nhớ cho hệ thống, hoặc áp dụng quota khác. Không tự lấy RAM công bố trừ payload size để kết luận có bao nhiêu dung lượng cache hữu ích.

### 24.2. Chính sách eviction ảnh hưởng tính đúng đắn

Nếu cùng Redis lưu:

```text
cache:product:...
idempotency:...
session:...
stream:orders
lock:...
fencing:sequence:...
```

mà policy cho phép eviction toàn bộ keys, key quan trọng có thể mất trước khi nghiệp vụ cho phép.

**Không mặc định managed Redis an toàn cho dữ liệu không được phép mất** chỉ vì có replication. Eviction/expiration và thao tác xóa hợp lệ có thể được lan truyền theo replication.

Tách workload hoặc chọn dịch vụ/độ bền phù hợp nếu business contract yêu cầu.

### 24.3. Số liệu từ provider có thể khác `INFO`

Một metric dashboard của provider có thể báo:

```text
Memory utilization %
Eviction count
CPU utilization
Connections
Network bytes
Replication lag
```

Định nghĩa metric và thời gian lấy mẫu có thể khác Redis raw counters.

Khi so sánh `used_memory`, `used_memory_rss`, maxmemory và cloud dashboard, cần đọc **định nghĩa metric**, không tự giả định chúng dùng cùng mẫu số.

## 25. Backup, persistence và restore trên managed service

Một dịch vụ managed có thể cung cấp backup tự động, snapshots, point-in-time restore hoặc những cơ chế durability khác tùy product.

Không tự suy rằng:

```text
Managed = mọi SET đều bền vững tuyệt đối
```

Cần làm rõ:

- Có RDB/AOF hoặc cơ chế persistence nào?
- Có lưu dữ liệu trên nhiều zone không?
- Mất điện/failover có thể mất những write nào?
- Backup diễn ra theo lịch nào?
- Retention bao lâu?
- Có restore vào instance mới hay khôi phục tại chỗ?
- Có thể export dữ liệu cho mục đích migration không?
- Restore có làm đổi endpoint, credentials hoặc engine version không?
- RTO/RPO phù hợp nghiệp vụ không?

### 25.1. Redis replication không đồng nghĩa zero data loss

Redis replication thông thường bất đồng bộ. Một primary có thể trả `OK` trước khi replica được promote nhận mọi write cuối cùng.

Các dịch vụ có kiến trúc durability khác nhau có thể cung cấp những cam kết khác, nhưng phải lấy **hợp đồng cụ thể của sản phẩm** làm căn cứ.

### 25.2. Backup API thay BGSAVE

Nếu `BGSAVE` bị từ chối, workflow:

```text
Spring app -> BGSAVE
```

không nên được sửa bằng việc tăng quyền application user.

Thay bằng:

```text
Backup scheduler / platform automation
          |
          v
Provider backup API
          |
          v
Managed snapshot/restore workflow
```

App chỉ cần biết trạng thái backup khi nghiệp vụ thật sự cần, không cần tự quản lý tiến trình Redis.

### 25.3. Test restore là một phần của compatibility

Một backup có tồn tại chưa đủ. Cần thử restore:

1. Sang môi trường cô lập.
2. Bằng đúng cơ chế provider hỗ trợ.
3. Xác nhận serializer và schema của Spring Data Redis.
4. Xác nhận TTL/keyspace/Stream state trong giới hạn contract.
5. Xác nhận kết nối và credentials mới.
6. Kiểm thử các thao tác nghiệp vụ quan trọng.

## 26. Di chuyển dữ liệu mà không có DUMP/RESTORE hoặc MIGRATE

Một số managed service hạn chế export/import, truy cập file nội bộ hoặc một số lệnh:

```redis
DUMP
RESTORE
MIGRATE
```

Nếu ứng dụng muốn đổi provider, namespace hoặc serializer, cần phân biệt:

- **Di chuyển bytes cùng định dạng** giữa Redis deployments.
- **Chuyển schema** như Java serialization sang JSON.
- **Chuyển Redis type** như String sang Hash.
- **Chuyển trạng thái xử lý** như Redis Streams consumer groups.
- **Chuyển dữ liệu authoritative** với concurrent writes.

Ngay cả khi `DUMP/RESTORE` được hỗ trợ, chúng không tự chuyển nội dung Java serialized value thành JSON model mới.

Một migration có thể dùng:

```text
Read source with old serializer
         |
         v
Convert to canonical business model
         |
         v
Write destination with new serializer
         |
         v
Verify revision + TTL + count + checks
```

### 26.1. Nếu SCAN bị hạn chế

Không chuyển sang `KEYS *` để cưỡng ép enumerate keyspace. Có thể:

- Dùng danh sách logical IDs từ database có thẩm quyền.
- Dùng event log/change stream của ứng dụng để backfill.
- Sử dụng provider migration/export service.
- Dùng cutover namespace cho cache tái tạo.
- Yêu cầu một maintenance role chỉ có quyền cần thiết khi provider cho phép.
- Chọn quy trình downtime có kiểm soát nếu dữ liệu không thể chuyển zero-downtime an toàn.

### 26.2. TTL và writes đồng thời

Migration phải tính:

```text
GET source
    |
    | Source bị cập nhật hoặc hết TTL
    v
SET destination
```

Không coi `GET + PTTL + SET` là atomic. Với dữ liệu có thẩm quyền, phải có revision/tombstone, catch-up, write freeze hoặc protocol đảm bảo không resurrect dữ liệu đã xóa.

## 27. Mẫu thiết kế feature fallback khi command không khả dụng

Không phải tất cả tính năng cần thiết đều có thể fallback mà giữ nguyên ngữ nghĩa.

Có thể chia thành ba nhóm.

### 27.1. Fallback tương đương về nghiệp vụ

Ví dụ, nếu app không được phép gọi `INFO`, có thể lấy metrics từ provider thay thế. Mục tiêu quan sát vẫn đạt được.

```text
INFO bị cấm
   |
   v
Provider metrics
```

### 27.2. Fallback chấp nhận thay đổi hành vi

Ví dụ, nếu region clear không được phép:

```text
Region clear bằng SCAN/DEL
          |
          v
Đổi namespace version + warm cache
```

Đây có thể là lựa chọn tốt cho cache disposable, nhưng sẽ làm cache lạnh và tăng memory trong một giai đoạn. Cần đánh giá effect.

### 27.3. Không có fallback an toàn mặc định

Ví dụ:

- Compare-and-delete lock Lua bị chặn.
- Một transaction/atomic operation không được hỗ trợ.
- `XREADGROUP` không có ở dịch vụ tương thích Redis.
- Fencing/idempotency state cần bền vững hơn service cung cấp.
- Dữ liệu authoritative cần bảo đảm mà engine không đáp ứng.

Không thể dùng hai command rời rạc thay một atomic operation mà không xem xét race condition.

Trong trường hợp này, **fail fast hoặc tắt feature**, thay đổi thiết kế hoặc chọn dịch vụ tương thích hơn. Một hệ thống “khởi động thành công nhưng làm sai dữ liệu” tệ hơn một deployment bị từ chối rõ ràng.

## 28. Thiết kế capability profile trong ứng dụng

Nếu cùng một codebase chạy trên nhiều môi trường, có thể biểu diễn những tính năng đã được xác minh bằng **configuration/capability profile**.

Ví dụ:

```yaml
app:
  redis:
    features:
      cache-region-clear: false
      scripts-enabled: true
      redis-streams-enabled: true
      keyspace-events-enabled: false
```

Các giá trị trên là **ví dụ cho một deployment đã được kiểm chứng**, không tự phát hiện server có hỗ trợ hay không.

Một lớp cấu hình:

```java
package com.example.redis.features;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.redis.features")
public record RedisFeatureProperties(
        boolean cacheRegionClear,
        boolean scriptsEnabled,
        boolean redisStreamsEnabled,
        boolean keyspaceEventsEnabled
) {
}
```

Đăng ký configuration properties bằng cơ chế Spring Boot tương ứng, ví dụ `@ConfigurationPropertiesScan` trên ứng dụng hoặc `@EnableConfigurationProperties(RedisFeatureProperties.class)`.

### 28.1. Không để capability flags trở thành cách vượt quyền

Nếu `scriptsEnabled=true` nhưng Redis user không có quyền, app vẫn lỗi. Flags cần được kiểm chứng với service staging và theo dõi khi triển khai.

Ngược lại, nếu `cacheRegionClear=false`, controller/maintenance workflow không nên có đường ẩn tự gọi `FLUSHDB` để thực hiện một hành vi tương tự.

### 28.2. Tách mandatory và optional features

Ví dụ:

```text
Mandatory:
  GET, SET, EXPIRE trên namespace cache
  Redis Cluster routing
  TLS + auth

Optional:
  INFO ở app user
  Cache region clear
  Keyspace notifications
  Specific script optimization
```

Nếu mandatory không hoạt động, deployment không đạt readiness/capability contract.

Nếu optional không hoạt động, app có thể tắt feature **theo chính sách** mà vẫn phục vụ được.

Không nên catch mọi lỗi Redis thành một feature flag tự bật/tắt ngẫu nhiên ở runtime; đó là hành vi khó dự đoán.

## 29. Không chạy thử lệnh phá hủy để “detect capability”

Một kiểu kiểm tra sai:

```text
Startup:
  FLUSHALL
  Nếu trả NOPERM -> kết luận an toàn
  Nếu trả OK     -> ...
```

Nếu lệnh thực sự được cho phép, nó đã xóa dữ liệu.

**Không bao giờ gọi lệnh destructive trên production chỉ để biết server có chặn hay không.**

Tương tự, không thử:

```text
SHUTDOWN
CONFIG SET ...
MODULE LOAD ...
FUNCTION FLUSH
```

như một phép kiểm tra tự động vô hại.

### 29.1. Capability discovery cần an toàn

Có thể dùng:

- Tài liệu và API provider theo service tier/version.
- Chính sách IAM/ACL do hạ tầng cấu hình.
- `COMMAND INFO`/`INFO`/`ACL DRYRUN` **chỉ khi được phép và phù hợp**, hiểu rằng chúng cũng có thể bị chặn.
- Integration tests trong managed staging với dữ liệu riêng.
- Negative tests bằng user ít quyền trên test environment.
- Capability profile được phê duyệt sau khi kiểm chứng.

**`ACL DRYRUN` kiểm tra quyền trên một command, không chứng minh toàn bộ ngữ nghĩa của lệnh hoặc mọi tác dụng bên trong Lua script.**

### 29.2. Startup probe an toàn

Một phép thử không phá dữ liệu trên keyspace riêng:

```java
package com.example.redis.health;

import java.time.Duration;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisCapabilityProbe {

    private final StringRedisTemplate redis;

    public RedisCapabilityProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean canReadAndWriteTestKey() {

        String key = "it:capability:" + UUID.randomUUID();
        String value = "ok";

        try {
            redis.opsForValue().set(
                    key,
                    value,
                    Duration.ofSeconds(30)
            );

            return value.equals(
                    redis.opsForValue().get(key)
            );

        } finally {
            try {
                redis.delete(key);
            } catch (RuntimeException ignored) {
                // TTL 30s là lớp dọn dẹp dự phòng cho key test.
                // Một ứng dụng thực nên ghi metric cleanup failure.
            }
        }
    }
}
```

Đoạn code minh họa **chỉ áp dụng khi ứng dụng có quyền SET/GET/DEL trên namespace probe**. Không chạy liên tục mỗi request và không để exception Redis bị âm thầm che trong application path.

Nếu muốn phân biệt lỗi auth/permission trong test, giữ original exception và báo loại lỗi. Với production health checks, cân nhắc probe phù hợp với quyền thực tế và tần suất thấp.

## 30. Integration test trên managed staging quan trọng hơn unit mock

Một Redis local container có thể không hạn chế `CONFIG`, `FLUSHALL` hoặc ACL như managed Redis. Vì thế:

```text
Unit test          -> logic Java
Redis container    -> Redis protocol/serializer basics
Managed staging    -> quyền, topology, TLS, tier, version
Fault injection    -> failover/reconnect/retry khi được phép
```

### 30.1. Contract test cần có

| Mã | Kiểm thử | Điều cần xác nhận |
|---|---|---|
| C1 | TLS handshake | JVM tin certificate và hostname đúng |
| C2 | Authentication | Đúng user/password hoặc token |
| C3 | Cache GET/SET/TTL | Các command cốt lõi hoạt động |
| C4 | Redis ACL/key patterns | App không đọc/ghi namespace trái quyền |
| C5 | Health check | Không yêu cầu admin commands không cần thiết |
| C6 | Cache clear | Chỉ hoạt động nếu policy cấp quyền |
| C7 | Lua script | `EVALSHA`/`EVAL`, ACL và script-cache behavior |
| C8 | Cluster routing | Key ở nhiều slots đều đọc/ghi đúng |
| C9 | Multi-key operations | Hash tags/slot constraints đúng |
| C10 | Redis Streams | Các lệnh producer/consumer cần thiết được hỗ trợ |
| C11 | Pub/Sub reconnect | Listener phục hồi nhưng không giả định replay |
| C12 | Failover | Client reconnect và phục hồi trong SLO |
| C13 | Error mapping | `NOPERM`, `NOSCRIPT`, `READONLY` không bị nuốt |
| C14 | Retry/idempotency | Timeout sau write không tạo side effect trùng |
| C15 | Metrics | Provider exporter và application metrics đủ quan sát |
| C16 | Backup/restore | Restore làm việc trong runbook |
| C17 | Rotation | Client dùng credential mới đúng lúc |
| C18 | Quota | Connection, memory và throughput đáp ứng tải |
| C19 | Engine upgrade | Command/serializer/feature không regress |
| C20 | Rollback | Có phương án nếu triển khai code mới không tương thích |

Các test destructive như failover hoặc xóa diện rộng chỉ thực hiện trên môi trường **cô lập và được phép điều khiển**. Không dùng production Redis để chạy canary `FLUSHALL` hoặc `SHUTDOWN`.

### 30.2. Negative ACL tests

Một bài test có giá trị không chỉ chứng minh `GET` thành công, mà còn chứng minh:

```text
App user:
  GET app:cache:product:* -> permitted
  GET security:tokens:*   -> denied
  FLUSHALL                -> denied
  CONFIG SET              -> denied
```

Nếu có `ACL DRYRUN` được provider cho phép, có thể kiểm tra command permissions mà không thực sự chạy lệnh. Nếu không, test negative phải được thiết kế an toàn trên staging với user ít quyền và tuyệt đối không để lệnh nguy hiểm có khả năng thành công trên dữ liệu thật.

### 30.3. Không chỉ kiểm tra startup

Một số lỗi chỉ xuất hiện sau:

- Rolling deployment làm thay bean/configuration.
- Primary failover.
- Scale-out tăng connection count.
- Replica promotion.
- Thay đổi network/DNS.
- Thay ACL/credential.
- Engine upgrade.
- Script cache bị reset.

Cần có regression suite và kiểm thử failure/recovery theo giai đoạn.

## 31. Quan sát lệnh mà Spring Data Redis thật sự phát

Khi tài khoản bị từ chối một lệnh, đừng mở mọi quyền ngay. Cần biết API framework đang sử dụng command nào.

Ví dụ:

```text
Java API:
  @CacheEvict(allEntries=true)

Redis commands có thể gồm:
  KEYS / SCAN
  DEL / UNLINK
```

Hoặc:

```text
Java API:
  repository.save(profile)

Redis commands có thể gồm:
  HSET
  SADD
  EXPIRE
  ...
```

Tùy phiên bản, serializer và mapping, tập command có thể khác nhau.

### 31.1. Cách điều tra an toàn

- Đọc contract của Spring Data Redis component liên quan.
- Dùng logging debug trong môi trường test nhưng **không đưa payload/credentials vào log**.
- Dùng Redis ACL denial logs nếu provider cho phép, có kiểm soát truy cập.
- Dùng integration tests với ACL giới hạn.
- Lưu operation alias và loại lệnh thay vì nguyên command arguments.
- Dùng command statistics/provider metrics để quan sát tải, không dùng `MONITOR` liên tục trên production.

### 31.2. Không tạm cấp admin cho web app để debug

Một đường debug không an toàn:

```text
App trả NOPERM
    |
    v
Thay REDIS_USERNAME thành admin
    |
    v
Redeploy web app
```

Điều này làm tăng blast radius đúng lúc hệ thống đang gặp sự cố. Nên dùng môi trường test hoặc maintenance user có quyền được kiểm soát; sửa cấu hình quyền nhỏ nhất cần thiết.

## 32. Multi-region, failover và read consistency

Một số managed Redis deployments có primary/replica, zone redundancy hoặc geo-replication. Nhưng **replica tồn tại không có nghĩa dữ liệu luôn nhất quán ngay lập tức**.

Ví dụ:

```text
t0: SET user:42:status ACTIVE -> primary
t1: primary trả OK
t2: GET qua replica -> có thể vẫn trả giá trị cũ
t3: replica bắt kịp
```

Nếu ứng dụng bật Lettuce `ReadFrom.REPLICA_PREFERRED`, cần hiểu dịch vụ có thực sự expose replica reads cho driver không và có cho client khám phá topology theo cách đó không.

Không áp dụng `ReadFrom.REPLICA_PREFERRED` toàn cục cho những đường đọc cần *read-your-writes* mà không đánh giá stale reads.

### 32.1. Endpoint đọc và chính sách của client

Một managed service có thể expose một **reader endpoint** mà client kết nối trực tiếp; một dịch vụ khác yêu cầu driver cluster-aware để chọn replica.

Hai cơ chế không giống nhau. Nếu driver đọc một endpoint là primary mà nhà cung cấp không expose replica topology, đặt `ReadFrom.REPLICA_PREFERRED` không tự sinh ra một replica để đọc.

### 32.2. Failover và kết quả write mơ hồ

Sau failover:

- Redis primary mới có thể chưa nhận một số thay đổi tùy cơ chế replication/durability.
- Một write có thể đã thực hiện nhưng response bị mất.
- DNS/endpoint và connection pool có thể cần thời gian cập nhật.
- Retry có thể tạo side effect trùng nếu command không idempotent.

Kiểm thử read/write recovery và RTO/RPO theo hợp đồng **sản phẩm cụ thể**.

## 33. Đừng nhầm Redis Cluster với nhiều logical databases

Một ứng dụng chạy Redis local có thể viết:

```java
lettuceConnectionFactory.setDatabase(2);
```

Nhưng khi chuyển sang Redis Cluster, không nên kỳ vọng `SELECT 2` hoạt động.

Redis Cluster chỉ sử dụng DB 0. Thay vào đó:

- Namespace keys để phân biệt domain.
- ACL key patterns khi hỗ trợ.
- Tách instances/deployments nếu cần chính sách/quota độc lập.
- Thiết kế multi-key operations với hash slots phù hợp.

**Namespace không bảo đảm isolation tuyệt đối**: một key prefix không tự ngăn memory pressure, eviction hay quyền admin ảnh hưởng các namespace khác trên cùng Redis deployment.

## 34. Một mẫu runbook khi triển khai bị lỗi vì restricted command

Giả sử sau deployment, application log có:

```text
event=redis_operation_failed
operation=cache_region_clear
category=ACL_DENIED
```

Một runbook có thể là:

### Bước 1 — Xác định phạm vi

- Những endpoint nào lỗi?
- Redis vẫn phục vụ `GET/SET` không?
- Có phải lỗi ở cache clear, health check, script hay Redis Repository?
- Tác động lên khách hàng hay chỉ một maintenance job?
- Các service khác cùng Redis có bị ảnh hưởng không?

### Bước 2 — Xác định nguồn lỗi

- App user nào đang dùng?
- Command nào bị từ chối theo telemetry an toàn?
- Provider tier/engine/version có hỗ trợ command không?
- Vừa đổi ACL, secret, engine hoặc code Spring Data Redis không?
- Node/Cluster route có thay đổi không?

### Bước 3 — Phân biệt sửa config hay sửa code

```text
Lệnh hợp lệ, thiếu permission
    -> Điều chỉnh least-privilege ACL qua quy trình được duyệt

Lệnh thuộc control plane
    -> Chuyển thao tác sang provider API/IaC

Lệnh không được engine hỗ trợ
    -> Đổi thiết kế hoặc service tier/engine

Lệnh destructive không nên thuộc app
    -> Tắt endpoint, chuyển sang maintenance workflow

Lỗi topology hoặc TLS
    -> Sửa client configuration/network, không nâng ACL
```

### Bước 4 — Giữ nguyên thông tin kỹ thuật an toàn

- Giữ original exception làm cause nếu bọc lỗi.
- Log category, operation alias, endpoint alias, deployment version.
- Không log raw password, key/value hoặc URI có credential.
- Ghi số lượng request lỗi và xu hướng latency.
- Nếu lỗi chỉ ở chức năng tùy chọn, có thể tạm tắt chức năng đó khi hợp đồng cho phép.

### Bước 5 — Sửa tại staging

- Cập nhật cấu hình đã được review.
- Chạy contract tests.
- Test failover/reconnect nếu phần thay đổi liên quan auth/topology.
- Canary deployment.
- Theo dõi `NOPERM`/unknown command và business metrics.
- Full rollout khi đạt điều kiện.

### Bước 6 — Ghi nhận bài học

- Cập nhật compatibility contract.
- Thêm negative ACL test.
- Giảm quyền dư thừa.
- Bổ sung runbook vào quy trình triển khai.
- Đánh giá lại nếu feature không có đường tương thích.

## 35. Các lỗi thường gặp

### Lỗi 1: Coi managed Redis là Redis local có host khác

Bỏ qua TLS, ACL, topology, engine version, quotas và provider control plane.

### Lỗi 2: Dùng tài khoản admin trong mọi microservice

Một lỗi code có thể làm ảnh hưởng toàn Redis deployment. Dùng credentials theo least privilege.

### Lỗi 3: Ứng dụng tự gọi CONFIG SET khi khởi động

Managed service có thể yêu cầu tham số được thiết lập qua control plane. Không retry hoặc nâng quyền vô tội vạ.

### Lỗi 4: Health check cần INFO nhưng app chỉ có quyền GET

Có thể làm readiness fail dù đường dữ liệu vẫn hoạt động. Thiết kế probe theo contract và đúng quyền.

### Lỗi 5: Dùng FLUSHALL để clear một cache region

Xóa rộng hơn phạm vi nghiệp vụ. Dùng invalidation theo ID, namespace versioning hoặc maintenance có kiểm soát.

### Lỗi 6: SCAN bị chặn nên fallback sang KEYS

Vừa không giải quyết vấn đề ACL vừa có nguy cơ tăng tải. Nếu không có quyền enumerate, chọn workflow khác.

### Lỗi 7: Coi EVALSHA tự đủ cho mọi thời điểm

Script có thể không tồn tại sau node change; fallback EVAL có thể cần quyền khác. Test script lifecycle.

### Lỗi 8: Thay atomic Lua bằng GET rồi DEL

Tạo race condition giữa kiểm tra và xóa. Không đánh đổi tính đúng đắn chỉ vì command hạn chế.

### Lỗi 9: Chỉ test GET/SET trên một key Cluster

Không phát hiện lỗi redirect, slot owner, multi-key hoặc DNS của các node khác.

### Lỗi 10: Bỏ qua CROSSSLOT bằng retry

CROSSSLOT là vấn đề key/operation design, không phải transient timeout.

### Lỗi 11: Cho rằng primary/reader endpoint giống Sentinel

Managed service có thể không expose Sentinel. Cấu hình đúng theo topology được cung cấp.

### Lỗi 12: Dùng RedisTemplate TCP cho HTTP-only product

Nếu provider không có RESP endpoint tương thích, phải dùng SDK/API phù hợp.

### Lỗi 13: Dùng cert trust-all để vượt lỗi TLS

Làm yếu bảo mật và che endpoint/network cấu hình sai.

### Lỗi 14: Hard-code password trong application.yml

Dễ lộ qua source control, log và artifact. Dùng secrets management.

### Lỗi 15: Không làm mới credentials ngắn hạn

App có thể hoạt động ban đầu nhưng lỗi sau token expiry hoặc khi reconnect.

### Lỗi 16: NOPERM bị nuốt thành cache miss

Che lỗi quyền và có thể làm database quá tải. Phân loại lỗi riêng.

### Lỗi 17: Retry lệnh write sau timeout mà thiếu idempotency

Một lệnh có thể đã chạy; retry `INCR` hoặc `XADD` có thể gây tác dụng phụ trùng.

### Lỗi 18: Gọi BGSAVE để kiểm tra backup managed

Backup có thể do control plane quản lý; lệnh có thể bị chặn. Kiểm tra snapshot/restore thật theo dịch vụ.

### Lỗi 19: Tưởng managed replication là zero data loss

Các sản phẩm có cam kết durability khác nhau; phải xác minh RPO/RTO thực.

### Lỗi 20: Tăng memory mà không xét eviction policy

Một Redis lưu cả cache và dữ liệu cần giữ có thể mất key quan trọng nếu policy không phù hợp.

### Lỗi 21: Chỉ theo dõi INFO và không có phương án khi INFO bị chặn

Provider metrics và application metrics cần đủ để quan sát production.

### Lỗi 22: Dùng MONITOR liên tục trên production

Có thể ảnh hưởng hiệu năng và làm lộ command arguments. Ưu tiên telemetry được kiểm soát.

### Lỗi 23: Tự phát hiện capability bằng lệnh phá dữ liệu

Không chạy FLUSHALL/SHUTDOWN/CONFIG SET chỉ để xem có bị chặn không. Dùng staging và tài liệu/quyền.

### Lỗi 24: Dùng Spring Redis Repository với ACL chỉ có GET/SET

Repository có thể cần Hash/Set/index/TTL commands. Kiểm tra command contract thực.

### Lỗi 25: Không test service version khi nâng cấp Spring Boot

Thư viện mới có thể dùng command hoặc serializer khác; regression tests phải chạy trên managed staging.

### Lỗi 26: Không xét access qua private network

DNS, firewall, VPC/VNet và hostname certificate có thể làm client lỗi dù service đang healthy.

### Lỗi 27: Giả định quota vô hạn vì server managed

Connection, request, memory và throughput vẫn có giới hạn; phải load test ở tier thật.

### Lỗi 28: Không có phương án khi provider không hỗ trợ lệnh thiết yếu

Nếu một lệnh tạo bảo đảm atomicity/durability bắt buộc không có, phải thay thiết kế hoặc dịch vụ, không silently degrade.

### Lỗi 29: Nâng quyền ứng dụng chỉ vì một tính năng maintenance

Tách maintenance workload/secret và quy trình approval; không đặt lệnh quản trị ở web app.

### Lỗi 30: Không lưu compatibility contract

Sau vài tháng, khó biết vì sao ứng dụng không dùng một command hoặc vì sao health check đặc biệt. Lưu quyết định theo engine/tier/version và test evidence.

## 36. Bài tập thực hành

### Bài tập A: Lập bảng command requirements

Cho một ứng dụng có:

```java
@Cacheable("products")
@CacheEvict(cacheNames = "products", key = "#id")
RedisMessageListenerContainer
StreamMessageListenerContainer
```

Hãy liệt kê:

1. Những lệnh Redis có thể cần cho từng feature.
2. Những lệnh có thể thuộc read/write/scripting/pubsub.
3. Những lệnh quản trị không nên có trong application user.
4. Những command cần xác minh trên managed staging.
5. Các chức năng nên tắt khi provider không hỗ trợ.

Không dùng danh sách अनुमान từ code annotation làm chứng cứ cuối cùng; cần kiểm thử theo phiên bản cụ thể.

### Bài tập B: Chạy thử ACL least privilege

Trên một Redis test cô lập có hỗ trợ ACL, tạo user chỉ được phép thao tác namespace `it:cache:*`.

Kiểm tra:

```redis
GET it:cache:42
SET it:cache:42 "value"
```

Sau đó dùng `ACL DRYRUN` nếu được phép để đánh giá các lệnh quản trị:

```redis
ACL DRYRUN app_cache_user FLUSHALL
ACL DRYRUN app_cache_user CONFIG SET maxmemory 1000000
```

Mục tiêu là xác nhận các thao tác ngoài contract bị từ chối **mà không thực thi chúng**.

### Bài tập C: Test script lifecycle

Dùng một script compare-and-delete cho lock test:

1. Chạy qua `StringRedisTemplate`.
2. Quan sát hành vi khi script chưa được load.
3. Thử lại sau restart/failover trên môi trường staging cô lập.
4. Kiểm tra quyền `EVALSHA`/`EVAL` và lệnh nội bộ.
5. Xác nhận owner sai không thể xóa lock người khác.

### Bài tập D: Đổi RedisCacheWriter batch strategy

Trong môi trường có quyền `SCAN`:

1. Tạo một cache region test.
2. Cấu hình batch strategy `SCAN`.
3. Thực hiện clear region với user chuyên dụng.
4. Đo độ trễ và lượng key đã xóa.
5. Kiểm tra không xóa namespace khác.
6. Thử user thông thường và xác nhận clear bị chặn theo thiết kế.

### Bài tập E: Cluster contract test

Trên managed Cluster staging:

1. Dùng nhiều keys thuộc các hash slots khác nhau.
2. Xác nhận Spring client route và đọc/ghi đúng.
3. Thử multi-key command trên keys cùng hash tag.
4. Thử khác slot và phân loại `CROSSSLOT`.
5. Nếu được phép, kiểm thử reshard/failover bằng quy trình kiểm soát.

### Bài tập F: Thử compatibility sau engine upgrade

Trước khi nâng engine:

```text
Capture:
  engine version
  Spring Data Redis version
  Lettuce version
  required commands
  ACL policies
  TLS/auth mode
  cluster topology
```

Sau upgrade trên staging, chạy lại contract tests và so sánh behavior, không chỉ so latency của `PING`.

### Bài tập G: Thiết kế health policy

Một API chỉ dùng Redis làm cache và có database fallback. Hãy xác định:

- Redis lỗi có làm liveness DOWN không?
- Khi nào readiness phải DOWN?
- Probe cần command nào?
- Cách tránh cho health checks tạo quá nhiều write?
- Cách cảnh báo Redis outage dù API vẫn trả 200 nhờ fallback?

### Bài tập H: Runbook khi provider chặn INFO

Giả sử dashboard cũ phụ thuộc:

```redis
INFO stats
INFO memory
```

Nhưng tài khoản monitoring mới không được phép. Hãy tìm một thiết kế dùng provider metrics và Micrometer application counters để tiếp tục quan sát eviction, memory, cache hit/miss, timeout và application SLO mà không nâng app user lên admin.

## 37. Câu hỏi tự kiểm tra

**1. Managed Redis có bảo đảm mọi lệnh Redis OSS đều chạy được không?**

Không. Khả năng phụ thuộc engine, version, tier, topology và quyền được cấp.

**2. Redis data plane khác control plane ở đâu?**

Data plane xử lý command dữ liệu; control plane quản lý cấu hình, scaling, backup, failover và tài nguyên theo API/console của provider.

**3. Vì sao `CONFIG SET` hoạt động local nhưng bị từ chối ở cloud?**

Provider có thể quản lý cấu hình qua control plane hoặc không cấp quyền thay đổi trực tiếp cho Redis user.

**4. `NOPERM` khác unknown command thế nào?**

`NOPERM` biểu thị vấn đề quyền ACL; unknown command có thể do lệnh không được engine biết/hỗ trợ hoặc bị ẩn theo service. Cần điều tra theo phiên bản và cấu hình.

**5. Có nên mở `+@all` để sửa nhanh NOPERM không?**

Không. Chỉ cấp command/key permissions cần thiết và đúng phạm vi.

**6. RedisCacheManager có thể dùng KEYS khi clear region không?**

Có, tùy version/cấu hình RedisCacheWriter. Cần kiểm tra chiến lược thực tế và ACL.

**7. Đổi sang SCAN có làm thao tác clear region không còn nguy hiểm không?**

Không. Nó vẫn có thể xóa rất nhiều key; cần hạn chế quyền/phạm vi/batch và cân nhắc namespace versioning.

**8. Nếu EVAL không hỗ trợ, có thể thay atomic compare-and-delete bằng GET rồi DEL không?**

Không an toàn nếu cần bảo đảm không xóa lock của owner mới. Cần primitive hoặc thiết kế khác.

**9. `NOSCRIPT` sau failover có thể xảy ra không?**

Có. Không nên giả định script cache có sẵn trên mọi node. Cần test lifecycle và fallback.

**10. Redis Cluster có thể dùng SELECT 2 như standalone không?**

Không. Redis Cluster dùng DB 0; dùng namespace hoặc tách deployment khi cần.

**11. Một endpoint tên “cluster” có chắc cần Lettuce Cluster client không?**

Không. Một số provider expose proxy endpoint; phải xác nhận topology/data plane thật.

**12. Vì sao RESP TCP và HTTP API là hai trường hợp khác nhau?**

Lettuce/Spring Data Redis connection factory dùng Redis protocol; HTTP-only product có thể cần SDK/API riêng.

**13. Tại sao `PING` thành công chưa chứng minh readiness toàn bộ?**

Nó không xác nhận quyền SET/HSET/XREADGROUP, serializer, slot routing hoặc nghiệp vụ.

**14. Khi Redis server hỗ trợ lệnh nhưng application user bị từ chối, nên làm gì?**

Xác nhận lệnh thật sự cần, sửa ACL theo least privilege qua quy trình quản trị, không retry mù quáng hoặc nâng toàn quyền.

**15. Provider-managed backup có thể thay BGSAVE trực tiếp không?**

Có thể có workflow snapshot/restore riêng qua control plane; phải kiểm tra hợp đồng của sản phẩm.

**16. Redis replication luôn bảo đảm không mất write sau failover không?**

Không. Tùy cơ chế replication/durability, một số write có thể chưa tới node được promote.

**17. Lỗi CROSSSLOT có thể xử lý bằng exponential backoff không?**

Không. Cần sửa cách chọn key/hash slot hoặc thay atomic operation.

**18. Nếu dùng Redis Streams, cần test gì thêm ngoài GET/SET?**

Các lệnh Streams, consumer groups, pending/reclaim, blocking reads, ACK, retention, reconnect và idempotency.

**19. Vì sao keyspace notifications có thể không hoạt động dù Redis connection bình thường?**

Có thể cần server configuration mà provider không cho application thay, hoặc listener không subscribe đúng node/channel.

**20. Tại sao phải test credential rotation khi dùng token ngắn hạn?**

Một kết nối thành công lúc startup không chứng minh reconnect sau expiry sẽ còn được xác thực.

**21. Có nên log toàn bộ exception message của Redis khi bị NOPERM không?**

Không mặc định. Message/URI/key/command arguments có thể chứa thông tin nhạy cảm. Ghi loại lỗi và operation alias an toàn.

**22. Nếu tính năng bắt buộc không có ở provider, nên tự mô phỏng bằng nhiều lệnh không nguyên tử không?**

Không khi điều đó phá vỡ tính đúng đắn. Phải sửa kiến trúc hoặc chọn dịch vụ phù hợp.

**23. Tại sao managed staging là cần thiết?**

Redis local/mock không phản ánh đầy đủ ACL, TLS, topology, quotas, engine version và lệnh bị hạn chế của managed service.

**24. Redis Cluster đã có replication thì có cần test backup/restore không?**

Có. Replication và backup/restore giải quyết các tình huống khác nhau; xóa nhầm có thể được replication.

**25. Vì sao không gọi FLUSHALL để tự kiểm tra quyền trong production?**

Nếu lệnh được phép, dữ liệu sẽ bị xóa. Chỉ đánh giá qua tài liệu, chính sách, dry-run được hỗ trợ và môi trường cô lập.

## 38. Ghi nhớ

- **Tương thích Redis là một hợp đồng nhiều chiều**, gồm protocol, engine version, tập lệnh, ACL, topology, TLS, quotas, durability và control plane.
- **Managed service có thể giới hạn các lệnh quản trị** như `CONFIG`, `ACL`, `BGSAVE`, `SHUTDOWN`, `MONITOR`, `FLUSHALL`, cùng một số lệnh quan sát hoặc scripting.
- **Không nâng quyền application user để vượt restricted command.** Chuyển thao tác quản trị sang provider API/IaC hoặc thay đổi thiết kế.
- **Spring Data Redis abstractions có thể phát nhiều command ngầm**: RedisCacheWriter clear, Redis Repositories, Streams và Lua scripts phải được kiểm tra thực tế.
- **`KEYS`/`SCAN` và `@CacheEvict(allEntries = true)` cần thận trọng**; nếu không được phép enumerate, cân nhắc invalidation theo ID hoặc namespace versioning thay vì xóa toàn vùng.
- **Script và Functions phải phù hợp engine/ACL/version**; `EVALSHA` có thể gặp `NOSCRIPT` sau đổi node. Không thay atomic operation bằng lệnh rời rạc thiếu an toàn.
- **Kết nối phải đúng topology**: standalone/proxy, primary/reader, Sentinel, Cluster hoặc HTTP API là các mô hình khác nhau. Kiểm tra TLS, hostname, credential rotation và cluster-discovered endpoints.
- **Không coi timeout là chứng minh write chưa chạy**; retry lệnh có side effects cần idempotency.
- **Quan sát qua provider metrics và application metrics** khi `INFO`/`MONITOR` bị hạn chế; không cần cấp quyền admin cho web app.
- **Trước cutover phải có compatibility contract và integration tests trên managed staging**, bao gồm những lỗi `NOPERM`, unknown command, `NOSCRIPT`, `READONLY`, `MOVED`, `CROSSSLOT`, backup/restore và failover theo khả năng provider.
- **Không có fallback an toàn cho mọi tính năng**. Nếu thiếu một bảo đảm atomicity hoặc durability bắt buộc, hãy fail fast hoặc chọn kiến trúc/dịch vụ khác.

### Tài liệu tham khảo

- [Spring Data Redis — Redis configuration](https://docs.spring.io/spring-data/redis/reference/redis/redis-configuration.html).
- [Spring Data Redis — Connection modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Boot — Redis auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis).
- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/).
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/).
- [Redis — COMMAND INFO](https://redis.io/docs/latest/commands/command-info/).
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/).
- [Redis — Redis Functions](https://redis.io/docs/latest/develop/programmability/functions-intro/).
- [Redis — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/).
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
