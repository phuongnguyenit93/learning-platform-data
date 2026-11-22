# Phân quyền ACL theo người dùng, nhóm lệnh và mẫu khóa trong Spring Data Redis

Redis thường phục vụ nhiều chức năng trong cùng một hệ thống: cache, session, Redis Streams, Pub/Sub, rate limiting, lock và dữ liệu tạm. Nếu tất cả microservice dùng chung một tài khoản có quyền `+@all ~*`, lỗi lập trình hoặc lộ credential ở một service có thể cho phép đọc dữ liệu của service khác, xóa key hoặc chạy lệnh quản trị nguy hiểm.

**Redis Access Control List (ACL)** cho phép cấp quyền theo **người dùng Redis**, **lệnh hoặc nhóm lệnh**, **mẫu key** và, từ Redis 6.2, **mẫu kênh Pub/Sub**. Trong Spring Data Redis, các quyền được thực thi tại **Redis server** đối với mọi command phát ra từ `StringRedisTemplate`, `RedisTemplate`, `ReactiveRedisTemplate`, cache, repository hoặc listener. Annotation Java và method name không tự quyết định Redis ACL.

Bài này triển khai chính sách **least privilege**: mỗi thành phần chỉ nhận những command và namespace thật sự cần. Chúng ta sẽ phân biệt xác thực với phân quyền; thiết lập Redis ACL; thử nghiệm `NOPERM`; giải thích Redis 7 key permissions/selectors; áp dụng cho Spring Boot, Redis Cache, Repository, Streams, Pub/Sub; kiểm soát secret, Cluster/Sentinel và kiểm thử bằng Testcontainers.

> **Lưu ý:** Những lệnh `ACL SETUSER` là ví dụ cho **Redis Open Source trong lab**. Redis Cloud/Redis Software có thể yêu cầu quản lý user qua giao diện hoặc API riêng và không hỗ trợ một số ACL subcommands. Password, hostname và namespace minh họa không được dùng nguyên văn trong production.

## 1. ACL hoạt động ở đâu?

```text
HTTP/API request
      |
      v
Spring service / repository
      |
      v
RedisConnectionFactory (username, password, TLS)
      |
      v
Redis server
      |
      +-- Authentication: user có hợp lệ?
      |
      +-- Authorization:
               1. Command được phép?
               2. Key được đọc/ghi đúng pattern?
               3. Nếu Pub/Sub, channel được phép?
      |
      +-- Đúng quyền: thực hiện command
      +-- Sai quyền: NOPERM
```

Ví dụ:

```redis
SET app:orders:913:state PAID
```

Để lệnh này được xét thực thi, connection cần user còn hiệu lực, quyền `+set` và quyền ghi trên `app:orders:913:state`. Thiếu một điều kiện, Redis có thể từ chối. Một lệnh được **cho phép** vẫn có thể lỗi vì `WRONGTYPE`, `CROSSSLOT`, hết RAM hay network timeout; ACL chỉ là một tầng kiểm tra.

### 1.1. Authentication khác authorization

| Khái niệm | Câu hỏi | Lỗi thường gặp |
|---|---|---|
| Authentication | Client là Redis user nào, password hợp lệ không? | `NOAUTH` / `WRONGPASS` |
| Command permission | User có quyền `GET`/`SET`/`XACK` không? | `NOPERM` |
| Key permission | User có quyền trên key được nêu không? | `NOPERM` |
| Channel permission | User có quyền nghe/phát channel không? | `NOPERM` |
| Business authorization | Người dùng HTTP có được truy cập đơn hàng này không? | Do ứng dụng quyết định |

Một Redis user được cấp `~tenant:*` không phân biệt được người gọi HTTP thuộc tenant nào nếu mọi request dùng **cùng connection credential**. ACL là lớp **defense-in-depth**, không thay thế xác thực/ủy quyền API.

### 1.2. ACL không tự mã hóa dữ liệu

ACL hạn chế thao tác. TLS bảo vệ username/password và dữ liệu trên network; firewall, private networking và security groups kiểm soát điểm kết nối. Secret manager quản lý password. Với dữ liệu nhạy cảm, cả bốn lớp vẫn cần được thiết kế; không đặt Redis public Internet rồi coi ACL là biện pháp duy nhất.

## 2. Các thành phần của một Redis ACL user

Một policy diễn đạt ý tưởng:

```text
user svc_orders on #<password-hash> ~app:orders:* resetchannels -@all +ping +get +set +del
```

| Rule | Ý nghĩa |
|---|---|
| `svc_orders` | Tên tài khoản Redis riêng cho service |
| `on` / `off` | Cho phép hoặc vô hiệu hóa đăng nhập mới |
| `>password` | Thêm password qua `ACL SETUSER` |
| `#<hash>` | Biểu diễn password hash trong ACL file/output |
| `reset` | Đưa user về trạng thái không quyền, không password, off |
| `~app:orders:*` | Cho truy cập các key khớp pattern, có cả R/W nếu command tương ứng được phép |
| `resetchannels` | Xóa danh sách channel patterns |
| `&app:events:*` | Cho phép channel khớp mẫu |
| `-@all` | Không cấp command nào |
| `+get` / `+set` | Cấp quyền command cụ thể |
| `+@read` | Cấp nhóm command đọc |
| `-@dangerous` | Thu hồi những command trong nhóm dangerous |

Redis xử lý ACL rules **từ trái qua phải**. Vì vậy nếu sau `-@dangerous` lại có `+@all`, lệnh nguy hiểm có thể được cấp lại.

### 2.1. Những mốc phiên bản cần nhớ

| Version | Khả năng |
|---|---|
| Redis 6.0+ | ACL user, password, command categories, key pattern `~...` |
| Redis 6.2+ | Channel patterns `&...` và `resetchannels` |
| Redis 7.0+ | Key read/write permissions `%R~...` / `%W~...`, selectors, `ACL DRYRUN` |
| Phiên bản sau | Command/categories và driver handshake có thể thay đổi |

Redis Enterprise/Cloud có khả năng hỗ trợ và cú pháp quản trị khác Redis Open Source; xác nhận ở dịch vụ thực tế.

## 3. Tạo user theo nguyên tắc deny-by-default

Ví dụ **trong interactive redis-cli của môi trường lab**, dùng tài khoản quản trị:

```redis
ACL SETUSER svc_orders reset on >LAB_ONLY_PASSWORD resetchannels ~app:orders:* +ping +get +mget +set +del +expire +ttl +pttl
```

Diễn giải:

1. `reset` bỏ toàn bộ quyền và password cũ.
2. `on` bật tài khoản.
3. `>LAB_ONLY_PASSWORD` thêm một password thử nghiệm.
4. `resetchannels` không cho channel nào.
5. `~app:orders:*` giới hạn namespace key.
6. Danh sách `+...` cấp đúng các command cần cho ví dụ.

**Không paste password production vào shell history, ticket hay log.** Ký tự `>` có thể bị shell diễn giải như redirect; khi tự động hóa phải truyền rule thành argument đúng cách qua client/secret mechanism. Password trên chỉ dành cho lab.

### 3.1. Vì sao cần reset khi định nghĩa lại toàn bộ?

`ACL SETUSER` cho **user đã tồn tại** thường chỉ sửa/bổ sung rule:

```redis
ACL SETUSER svc_orders +get
ACL SETUSER svc_orders +set
```

Sau lời gọi thứ hai, user vẫn giữ `+get`. Nếu policy mới dự kiến chỉ có `SET`, quyền đọc cũ có thể tồn dư. Một hệ thống IaC nên biết policy đầy đủ và reconcile chính xác. Nhưng `reset` trên user thật có thể gián đoạn ứng dụng: nên tạo user mới hoặc dùng một kế hoạch thay đổi/rollback có kiểm thử.

### 3.2. Đọc rule từ tài khoản admin

```redis
ACL USERS
ACL GETUSER svc_orders
ACL LIST
ACL CAT
ACL CAT read
ACL CAT write
ACL CAT stream
```

| Lệnh | Tác dụng |
|---|---|
| `ACL USERS` | Liệt kê Redis ACL users |
| `ACL GETUSER name` | Xem flags, password hashes, commands, keys, channels, selectors |
| `ACL LIST` | Xem toàn bộ rules theo dạng ACL file |
| `ACL CAT` | Liệt kê các command categories |
| `ACL CAT read` | Các command thuộc category `read` |
| `ACL WHOAMI` | Tên Redis user hiện tại nếu connection được cấp quyền command đó |

Output có thể chứa quyền chi tiết và password hashes; không in toàn bộ vào log chia sẻ. Không cấp các lệnh quản trị ACL cho application chỉ để “tự xem quyền”.

## 4. Phân quyền theo lệnh và nhóm lệnh

### 4.1. Cho phép lệnh riêng lẻ

```text
+get           Cho phép GET
+mget          Cho phép MGET
+set           Cho phép SET
+del           Cho phép DEL
-del           Tước quyền DEL
+xreadgroup    Cho phép XREADGROUP
+xack          Cho phép XACK
```

Một service chỉ cần GET/SET nên được cấp danh sách lệnh nhỏ thay vì toàn bộ Redis. Danh sách cần tính cả command mà connection driver và framework thực sự gửi khi startup, health, cache evict hoặc reconnect.

### 4.2. Cấp theo category

```text
+@read       Các command thuộc nhóm đọc
+@write      Các command thuộc nhóm ghi
+@string     Các command làm việc với String
+@hash       Các command làm việc với Hash
+@set        Các command làm việc với Set
+@sortedset  Các command làm việc với Sorted Set
+@stream     Các command làm việc với Stream
+@pubsub     Các command Pub/Sub
+@connection Các command liên quan kết nối
-@dangerous  Bỏ những command bị gắn dangerous
```

Một command có thể thuộc **nhiều category**; ví dụ `SET` thuộc các nhóm liên quan String và write. Thành phần từng nhóm có thể thay đổi khi nâng Redis. Đối với Redis modules, các nhóm chuẩn như `@read`/`@write` không tự bao gồm mọi module command; `+@all` rộng hơn và có thể cấp cả module commands.

### 4.3. Vì sao `+@all -@dangerous` vẫn quá rộng?

`+@all` cấp mọi command, kể cả những lệnh mới hoặc module commands; `-@dangerous` chỉ gỡ một danh mục, không có nghĩa user chỉ được thực hiện đúng các thao tác business cần. Mỗi command mới được cấp là một bề mặt rủi ro.

Mẫu ưu tiên:

```text
reset on >password ~app:orders:* -@all +ping +get +set
```

Rule có `reset` vốn đã không cấp command nào; `-@all` ở dòng minh họa nhấn mạnh ý định **deny-by-default**. Với hệ thống thật, ghi rõ allowlist tại nguồn cấu hình và kiểm tra sau triển khai.

### 4.4. Quyền subcommand

Redis có lệnh chứa subcommand như `CONFIG GET` hoặc `XGROUP CREATE`. ACL có cú pháp:

```text
+config|get
-config|set
+xgroup|create
+client|setinfo
```

Cấp `+config|get` không đồng nghĩa cấp mọi thao tác `CONFIG`. Các kiểu subcommand ACL phụ thuộc Redis version và cần được thử trên server mục tiêu. Không cấp `CONFIG GET` rộng nếu service không cần biết cấu hình vận hành.

## 5. Mẫu khóa: `~pattern` không phải regex

Redis ACL sử dụng **glob-style pattern** trên **tên key thực tế**. Ví dụ:

```text
~app:orders:*         Mọi key bắt đầu bằng app:orders:
~app:cache:*          Mọi key bắt đầu bằng app:cache:
~tenant42:*           Namespace tenant42
~app:orders:{42}:*    Tên key có chuỗi {42} đúng vị trí đó
~*                    Tất cả key, rất rộng
```

Với `~app:orders:*`:

| Key | Được phép theo key pattern? |
|---|---|
| `app:orders:913` | Có |
| `app:orders:913:state` | Có |
| `app:orders:` | Có |
| `app:order:913` | Không |
| `app:billing:913` | Không |
| `other:orders:913` | Không |

`*` có thể khớp cả dấu hai chấm; nó không hiểu “cấp thư mục” hay các ranh giới tenant. `~app:*` có thể bao gồm nhiều namespace bạn không định mở.

### 5.1. Nhiều key patterns

```redis
ACL SETUSER svc_billing reset on >LAB_ONLY_PASSWORD resetchannels ~app:orders:* ~app:billing:* +ping +get +set +del
```

User được truy cập key khớp **một trong hai** patterns, trong phạm vi command được cấp.

### 5.2. Reset và mở tất cả key

```text
resetkeys   Xóa danh sách key patterns
allkeys     Tương đương ~*
~foo:*      Bổ sung quyền cho key foo:*
```

Không dùng `allkeys` cho user cần cô lập tenant. Nếu phải thay phạm vi key, thay đổi này cần test negative cases và kiểm tra connection đang hoạt động.

### 5.3. Serializer quyết định key bytes

Ví dụ:

```java
StringRedisTemplate strings = ...;
strings.opsForValue().set("app:orders:913", "READY");
```

`StringRedisTemplate` mã hóa key String theo UTF-8, phù hợp prefix trực quan. Nhưng `RedisTemplate` dùng `JdkSerializationRedisSerializer` cho key có thể gửi bytes khác hoàn toàn so với chuỗi `app:orders:913`. Redis coi đó là **key vật lý khác** và pattern `~app:orders:*` có thể không khớp.

Hãy cấu hình key serializer rõ ràng, thường là `StringRedisSerializer` khi dùng ACL theo tên key, và kiểm thử key bytes sau khi đổi version/serializer.

### 5.4. Redis Cluster hash tag khác với ACL pattern

```text
app:orders:{913}:state
app:orders:{913}:total
```

Hash tag `{913}` ảnh hưởng **slot placement** trong Redis Cluster. ACL pattern `~app:orders:*` xét **tên key**. Hai key cùng slot không tự động cùng quyền; hai key cùng ACL prefix không nhất thiết cùng slot.

## 6. Cảnh báo: key patterns không chặn command toàn server

ACL key patterns kiểm tra các lệnh có **key arguments** cụ thể. Các lệnh thay đổi toàn bộ database/server như:

```redis
FLUSHALL
FLUSHDB
SWAPDB
```

không nêu từng key để kiểm tra `~tenant42:*`. Một user có `~tenant42:* +@all` vẫn có thể được phép chạy `FLUSHALL`, xóa dữ liệu ngoài tenant của nó.

Vì vậy tài khoản ứng dụng cần **allowlist command**, không chỉ thêm key pattern. Không cấp `FLUSHALL`, `FLUSHDB`, `SWAPDB`, các lệnh quản trị/debug/replication hay config nếu không có nhu cầu vận hành được kiểm soát.

### 6.1. KEYs/SCAN và lộ metadata

`KEYS pattern` và `SCAN` duyệt keyspace. Pattern `MATCH` của `SCAN` không phải một key cần đọc/ghi. Không giả định `~tenant42:*` sẽ tự lọc mọi tên key có thể bị khám phá khi cho client quyền scan.

Với multi-tenant có yêu cầu bí mật về tên/sự tồn tại key, tránh cấp `KEYS`/`SCAN` cho tenant client. Nếu cần cleanup, dùng worker riêng, lệnh phù hợp và giới hạn lượng công việc.

### 6.2. ACL không lọc từng field trong Redis Hash

Một key:

```text
tenant:42:customer:913
  publicName: "An"
  personalId: "..."
  accessToken: "..."
```

Nếu user được `HGETALL` trên key đó, Redis ACL tiêu chuẩn không tự lọc field `accessToken` theo “quyền user”. Với dữ liệu có mức nhạy cảm khác nhau, tách key hoặc dùng database/kiến trúc có field-level authorization thích hợp.

## 7. Redis 7: key chỉ đọc và chỉ ghi

Từ Redis 7.0, ACL hỗ trợ:

```text
%R~app:reports:*        Cho phép đọc key phù hợp
%W~app:reports:out:*    Cho phép ghi key phù hợp
%RW~app:reports:*       Cho cả đọc và ghi, tương đương ~...
```

Ví dụ user đọc nguồn báo cáo nhưng chỉ ghi ra namespace output:

```redis
ACL SETUSER svc_reports reset on >LAB_ONLY_PASSWORD resetchannels %R~app:reports:* %W~app:reports:out:* +ping +get +set
```

| Lệnh | Kỳ vọng |
|---|---|
| `GET app:reports:913:source` | Được phép |
| `SET app:reports:out:913 READY` | Được phép |
| `SET app:reports:913:source BAD` | Bị chặn |
| `GET app:secrets:token` | Bị chặn |

**Quyền R/W do key specifications của command quyết định**, không thể suy ra đơn giản từ tên. Chẳng hạn một thao tác vừa thay đổi key vừa trả dữ liệu cũ có thể cần cả đọc và ghi; lệnh chỉ trả metadata về độ dài có thể chỉ yêu cầu quyền kiểu khác. Kiểm thử trên Redis version thực.

### 7.1. Nhiều key trong một command

`COPY source destination` đọc key nguồn và ghi key đích; user cần quyền tương ứng cho **cả hai**. Đối với Redis Cluster còn có quy tắc hash slot. `MGET` trên một key hợp lệ và một key không được phép có thể khiến **toàn command** bị từ chối; không mặc định Redis chỉ bỏ qua key bị cấm.

## 8. Redis 7 selectors: nhiều bộ quyền độc lập

Một selector là nhóm rule trong dấu ngoặc đơn. Redis chấp nhận command nếu **root rule hoặc một selector** đáp ứng điều kiện.

```redis
ACL SETUSER svc_reports reset on >LAB_ONLY_PASSWORD resetchannels +get ~app:reports:* (+set ~app:reports:out:*)
```

Ở đây root cho phép `GET app:reports:*`, selector cho phép `SET app:reports:out:*`. Selector không phải cơ chế thu hẹp quyền đã cấp bởi root.

Sai:

```text
Root:     +@all ~*
Selector: (+get ~app:reports:*)
```

Root đã cho phép mọi command/key; selector hẹp hơn **không có tác dụng hạn chế** root.

Khi một command cần quyền trên nhiều key, một bộ rule/selector cần đáp ứng **toàn bộ command**, không tự ghép một nửa quyền từ root với phần còn lại từ selector theo ý ứng dụng. Selectors cũng không tạo “role” có thể gán cho nhiều Redis users; chúng thuộc user cụ thể.

## 9. Redis Pub/Sub: channel patterns là lớp riêng

Redis Pub/Sub dùng channel, không phải Redis key. Rule `~app:events:*` **không** tự cấp quyền subscribe/publish lên channel cùng tên.

Từ Redis 6.2, dùng:

```text
resetchannels
&app:events:*
+subscribe
+psubscribe
+publish
```

Ví dụ **listener chỉ nghe**:

```redis
ACL SETUSER svc_events_sub reset on >LAB_ONLY_PASSWORD resetchannels &app:events:* +ping +subscribe +psubscribe
```

Ví dụ **publisher chỉ phát**:

```redis
ACL SETUSER svc_events_pub reset on >LAB_ONLY_PASSWORD resetchannels &app:events:* +ping +publish
```

| Yêu cầu | Quyền cần |
|---|---|
| `SUBSCRIBE app:events:orders` | `+subscribe` và channel pattern khớp |
| `PUBLISH app:events:orders msg` | `+publish` và channel pattern khớp |
| `PSUBSCRIBE app:events:*` | `+psubscribe` và ACL channel pattern tương ứng |
| `PUBLISH other:secret msg` | Bị chặn nếu chỉ cấp `&app:events:*` |

### 9.1. PSUBSCRIBE có cách kiểm tra pattern đặc biệt

Đối với `SUBSCRIBE` và `PUBLISH`, Redis kiểm tra channel được nêu có phù hợp ACL channel patterns. Với `PSUBSCRIBE`, **pattern đăng ký** cần khớp chính xác pattern ACL đã cấp, không chỉ là pattern rộng hơn:

```text
ACL: &app:events:*

PSUBSCRIBE app:events:*   -> phù hợp khi có +psubscribe
PSUBSCRIBE app:*          -> không được phép chỉ vì ACL trên
```

### 9.2. Spring listener không tự bypass ACL

`RedisMessageListenerContainer` và `ReactiveRedisMessageListenerContainer` sử dụng connection với Redis ACL user đã cấu hình. Nếu thiếu channel pattern hoặc `SUBSCRIBE` permission, listener có thể lỗi khi đăng ký hoặc reconnect. Pub/Sub không giữ lịch sử để replay mặc định; lỗi quyền trong lúc listener offline có thể dẫn đến **mất event**. Nếu cần replay/ACK, cân nhắc Redis Streams.

## 10. Mô hình user cho từng service

```text
                         Redis
                           |
        +------------------+------------------+
        |                  |                  |
   Catalog API         Order worker      Event listener
   read catalog        read/write        subscribe only
        |                  |                  |
  svc_catalog_ro      svc_orders_rw     svc_events_sub

           Operations / backup / admin
                       |
                 ops_redis_admin
              (credential đặc quyền riêng)
```

| Redis user | Key/channel scope | Lệnh ví dụ |
|---|---|---|
| `svc_catalog_ro` | `~app:catalog:*` | `GET`, `MGET`, `PING` |
| `svc_orders_rw` | `~app:orders:*` | `GET`, `SET`, `DEL`, `EXPIRE` theo nhu cầu |
| `svc_events_sub` | `&app:events:*` | `SUBSCRIBE`/`PSUBSCRIBE` |
| `svc_stream_worker` | `~app:streams:orders` | `XREADGROUP`/`XACK`/`XPENDING` |
| `ops_redis_admin` | Quản trị theo runbook | ACL/config/backup commands cần thiết |

Redis Open Source **không có generic roles/groups** để thêm một user làm thành viên nhóm. Có thể quản lý policy templates ở IaC, nhưng Redis lưu ACL rules trên từng user.

### 10.1. Một ACL user không thay thế authorization HTTP

Giả sử mọi request tenant42 và tenant43 dùng một `RedisTemplate` có credential `svc_shared` với `~tenant:*`. Redis chỉ thấy **svc_shared**, không biết khách hàng HTTP nào gửi request.

Phải xác định tenant từ security context, kiểm tra ownership trong business logic và tạo key theo ID đáng tin. Nếu yêu cầu cách ly chặt, cấp ACL user riêng theo tenant hoặc tách Redis deployment; không lấy tenantId tùy ý từ query parameter rồi coi `~tenant:*` là bảo vệ dữ liệu.

## 11. Kết nối ACL từ Spring Boot

Dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Spring Boot 3.x `application.yml`:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      timeout: 3s
      ssl:
        enabled: true
```

Credential được cấp qua environment/secret manager. Cần cấu hình TLS và hostname theo Redis deployment thật. Nếu dùng `spring.data.redis.url`, host/port/username/password có thể bị URL ghi đè theo quy tắc auto-config của Boot.

### 11.1. Connection factory quyết định Redis ACL identity

```text
RedisConnectionFactory
    username = svc_orders_rw
           |
           +--> StringRedisTemplate
           +--> RedisTemplate
           +--> RedisCacheManager
           +--> Stream listener (nếu dùng factory này)
```

Mọi command trên cùng connection factory dùng cùng Redis ACL user. Java class/method annotation không tự thay Redis user. Nếu hai service trong cùng JVM cần quyền khác nhau, có thể tạo **hai connection factories** và các template tương ứng, không tái sử dụng credential đặc quyền cho mọi module.

### 11.2. Ví dụ factory riêng cho service chỉ đọc

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class CatalogRedisConfig {

    @Bean("catalogRedisFactory")
    public LettuceConnectionFactory catalogRedisFactory(
            CatalogRedisProperties props) {

        RedisStandaloneConfiguration config =
                new RedisStandaloneConfiguration(
                        props.host(), props.port());
        config.setUsername(props.username());
        config.setPassword(RedisPassword.of(props.password()));

        // Với TLS, cấu hình thêm LettuceClientConfiguration.
        return new LettuceConnectionFactory(config);
    }

    @Bean("catalogRedisTemplate")
    public StringRedisTemplate catalogRedisTemplate(
            @Qualifier("catalogRedisFactory")
            LettuceConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
```

`CatalogRedisProperties` là kiểu properties do ứng dụng tự định nghĩa. Nếu nhiều connection factories cùng loại, dùng `@Qualifier`/bean name rõ và định nghĩa bean `@Primary` khi cần cho auto-configuration. Không tạo một factory mới cho mỗi request.

### 11.3. Driver và health check có lệnh phụ trợ

Lettuce/Jedis có thể gửi thêm `PING`, `HELLO`, `CLIENT SETINFO`, `SELECT` hoặc commands phục vụ connection/health, phụ thuộc phiên bản. Nếu application lỗi `NOPERM` khi startup dù `GET` đã được cấp:

1. Xem command nào thực sự bị từ chối trong log/`ACL LOG`.
2. Kiểm tra redis-server và driver version.
3. Cấp **command phụ trợ tối thiểu**, ví dụ `+ping` hoặc `+client|setinfo` khi thực sự cần.
4. Test startup, reconnect và health endpoint.

Không cấp `+@all` hoặc `+@connection` rộng một cách mù quáng. Redis ACL là nguồn bảo vệ, và driver handshake có thể thay đổi khi nâng Spring Boot/Lettuce.

### 11.4. Reactive Redis

`ReactiveStringRedisTemplate`/`ReactiveRedisTemplate` vẫn thực thi ACL khi Publisher được subscribe. Một `NOPERM` trở thành lỗi reactive (`onError`), không phải lý do để tự `subscribe()` thêm hoặc retry vô hạn. Lỗi quyền không tự hết khi gửi cùng command bằng cùng user lần nữa.

## 12. Spring Cache: prefix, lệnh đọc/ghi và clear

Ví dụ Redis CacheManager tạo key:

```text
catalogDetails::p-100
catalogDetails::p-101
inventory::p-100
```

User chỉ cache catalog có thể cần key scope `~catalogDetails::*`. Nhưng RedisCacheManager có **serializer và key prefix riêng**: phải test tên key vật lý thật, không đoán từ key biểu diễn trong Java.

Một cache flow có thể dùng:

| Thao tác | Commands có thể dùng |
|---|---|
| Cache hit | `GET` |
| Cache miss rồi lưu | `SET` cùng TTL/expiration |
| Evict key | `DEL` hoặc `UNLINK` |
| Clear cache | Có thể dùng `KEYS`/`SCAN` và xóa hàng loạt, tùy cache writer |

### 12.1. Cẩn trọng với cache clear

`Cache.clear()` có thể enumerate tên key theo prefix. Không cấp `KEYS`/`SCAN` toàn Redis cho user API chỉ vì nó cần xóa cache thỉnh thoảng. Có thể tách admin cache worker, thiết kế TTL/prefix version, hoặc triển khai chính sách clear riêng có kiểm soát.

```text
app:v4:catalogDetails::p-100
app:v5:catalogDetails::p-100
```

Versioned prefix tạo namespace mới mà không bắt API có quyền quét/xóa mọi key cũ; cleanup nền chỉ xóa key khi đã xác định owner và retention.

## 13. Redis Repository: entity và index có nhiều key

Với Redis Repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;
    private String name;
}
```

Spring Data Redis có thể lưu entity dưới dạng Hash cùng một số Set/index/metadata key phụ trợ. Một `repository.save(...)` có thể phát nhiều lệnh lên nhiều key, và **không phải mọi key phụ đều khớp một pattern** do developer đoán trước.

Quy trình đúng:

1. Chạy integration test trên Redis test, lấy tên key thực và command thực.
2. Phân loại entity key, id index, secondary index và TTL/cleanup.
3. Cấp patterns cho đúng các key thật sự do repository dùng.
4. Cấp từng command cần cho `save/find/delete/query`.
5. Test sau khi bật `@Indexed`, expiration hoặc nâng version mapping.

Không sửa `NOPERM` của Repository bằng cách cấp `+@all ~*`, vì đó là loại bỏ hoàn toàn ranh giới ACL.

## 14. Redis Streams: consumer group khác Redis user

```text
Stream key:      app:streams:orders
Consumer group:  billing-workers
Consumer name:   billing-instance-1
ACL user:        svc_stream_worker
```

Đây là **bốn định danh khác nhau**. Redis ACL kiểm tra `svc_stream_worker` của connection. Consumer group và consumer name không tạo tài khoản Redis và không tự cấp lệnh.

| Vai trò | Các command cần cân nhắc |
|---|---|
| Producer | `XADD` |
| Consumer | `XREADGROUP`, `XACK` |
| Pending diagnostics | `XPENDING` |
| Recovery | `XAUTOCLAIM`, `XCLAIM` |
| Group provisioning | `XGROUP CREATE` |
| Trimming | `XTRIM`, `XDEL` |

Ví dụ worker chỉ đọc, ACK và reclaim:

```redis
ACL SETUSER svc_stream_worker reset on >LAB_ONLY_PASSWORD resetchannels ~app:streams:orders +ping +xreadgroup +xack +xpending +xautoclaim
```

Không cấp `XGROUP CREATE` cho runtime nếu group được tạo bởi provisioning job. Nếu ứng dụng thực sự tự tạo group, kiểm tra và cấp `+xgroup|create` theo command/subcommand mà version Redis dùng.

Với retry/DLQ stream riêng, user phải có key pattern tương ứng và quyền `XADD` khi ghi DLQ. Một key pattern quá rộng cho mọi stream có thể làm worker can thiệp nhầm message của service khác. Redis Cluster vẫn áp đặt hash-slot constraints độc lập với ACL.

## 15. Lua, Redis Functions, pipeline và transaction

### 15.1. Lua không phải cách vượt ACL

Ví dụ script release lock:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Khi gọi bằng `EVAL`/`EVALSHA` qua Spring Data Redis, Redis user cần quyền scripting command và **các command mà script thực hiện** (như `GET`/`DEL`), cùng key permissions tương ứng. Không giả định `+eval` cho phép script đọc/xóa mọi key. Hạn chế script runtime và tránh dynamic key names không được khai báo/kiểm soát.

### 15.2. Pipeline vẫn xét từng command

Pipeline là cách gửi nhiều command với ít round trips, **không bỏ ACL**. Một command trong pipeline bị NOPERM có thể làm kết quả pipeline chứa lỗi hoặc framework phát exception. Không mặc định toàn batch thành công chỉ vì vài lệnh trước đã chạy.

### 15.3. Multi-key và MULTI/EXEC

`MGET`/`MSET` cần command permission và key permissions cho **tất cả các key**. Redis transaction cần những lệnh quản lý `MULTI`/`EXEC`/`DISCARD`/`WATCH` nếu được sử dụng; các command bên trong vẫn bị ACL kiểm tra. Trong Redis Cluster còn có ràng buộc các key thuộc cùng hash slot cho những multi-key operations. ACL success không tạo cross-shard transaction.

## 16. Redis Cluster và Sentinel: tránh lệch quyền giữa node

### 16.1. Redis Cluster

Redis ACL là cấu hình của **Redis server/node**. Không mặc định một lệnh `ACL SETUSER` gửi tới Master A được tự động nhân bản sang tất cả master/replica trong Cluster.

```text
Spring cluster-aware driver
      |
      +-- Master A: svc_orders_rw có quyền
      +-- Master B: svc_orders_rw chưa được tạo
      +-- Master C: svc_orders_rw khác password/pattern
```

Hậu quả: ứng dụng chạy được với key thuộc slot A nhưng gặp auth/NOPERM khi truy cập slot B, hoặc khi failover lên replica chưa có ACL config.

Quy trình:

- Phân phối ACL qua IaC/control plane tới **mọi node cần phục vụ client**.
- So sánh policy version và `ACL GETUSER` từng node.
- Kiểm thử key ở nhiều hash slot, không chỉ một key test.
- Theo dõi drift sau resharding, add node, failover.
- Không fallback sang default superuser khi quyền riêng gặp lỗi.

Redis Cloud/Enterprise có thể quản lý ACL tập trung; tuân theo giao diện hỗ trợ thay vì gửi `ACL SETUSER` thủ công.

### 16.2. Redis Sentinel

Spring client có thể cần credential để **nói chuyện với Sentinel** tìm master, và credential khác để **nói chuyện với Redis data node**:

```text
Spring client --(Sentinel identity)--> Sentinel nodes
             --(Redis ACL user)-----> Redis master/replica
```

Đừng sửa lỗi data node `NOPERM` bằng cách mở quyền Sentinel. Kiểm tra các property `spring.data.redis.sentinel.*` đúng Spring Boot version và quản lý rotation cả hai loại credentials khi cần.

## 17. Lưu bền ACL và bảo vệ password

Redis Open Source hỗ trợ định nghĩa users trong cấu hình Redis hoặc qua file ACL (`aclfile`). Với ACL file, có thể dùng các command quản trị `ACL SAVE`/`ACL LOAD` theo quy trình phù hợp. Thay đổi runtime bằng `ACL SETUSER` có thể mất khi container restart hoặc bị configuration management ghi đè nếu chưa lưu theo nguồn sự thật.

Một mô hình vận hành cần:

1. Policy được lưu và versioned trong hạ tầng cấu hình.
2. Secret được cấp qua secret manager, không hardcode trong Git.
3. ACL file/metadata được bảo vệ bằng quyền filesystem.
4. Rule không phụ thuộc thay đổi thủ công trên một node.
5. Có audit trail ai đã đổi password, key patterns, commands.
6. Có kiểm tra định kỳ sự khác biệt giữa thực tế và policy.

### 17.1. Password rotation nhiều giai đoạn

Redis user có thể có nhiều password hợp lệ cùng lúc:

```text
Phase 1: thêm password mới vào cùng user
Phase 2: cập nhật secret cho application và rolling restart/reconnect
Phase 3: xác minh mọi instance hoạt động với password mới
Phase 4: xóa password cũ
Phase 5: lưu lại policy, giám sát authentication failures
```

Cú pháp:

```text
>NEW_PASSWORD    Thêm password mới
<OLD_PASSWORD    Gỡ password cũ
```

Không nhập password thật theo ví dụ vào shell history. Ký tự `<`, `>` là **Redis ACL rule syntax**, nhưng shell có thể hiểu là redirection. Dùng API/automation truyền argument an toàn và secrets bảo mật.

### 17.2. Thay password không luôn cắt existing connections

Một connection đã xác thực có thể tiếp tục hoạt động dù user bị chuyển `off` hoặc password cũ bị gỡ theo cách quản lý user. Khi cần thu hồi khẩn cấp, quản trị viên có thể cần `CLIENT KILL USER ...`, `ACL DELUSER` hoặc cách cô lập network phù hợp, nhưng các thao tác đó **có thể ngắt application**. Cần runbook incident response và xác minh thực tế.

### 17.3. Không dùng nopass trong production

Rule `nopass` cho phép user không cần password theo Redis semantics. Redis `default` user trên một số cấu hình mới có thể bắt đầu ở trạng thái permissive. Trong môi trường yêu cầu bảo mật, phải chủ động hạn chế/tắt `default` và tạo user riêng **sau khi** đã bảo đảm application dùng được credential mới. Thao tác sai thứ tự có thể gây outage.

## 18. ACL DRYRUN: kiểm tra quyền mà không thực thi command

Redis 7.0+ hỗ trợ:

```redis
ACL DRYRUN svc_orders GET app:orders:913:state
ACL DRYRUN svc_orders SET app:orders:913:state PAID
ACL DRYRUN svc_orders GET app:secrets:token
ACL DRYRUN svc_orders FLUSHALL
```

Lệnh được chạy bởi tài khoản quản trị để **mô phỏng quyền** của user mục tiêu mà không thực hiện side effect của command đích. Nó rất hữu ích để kiểm tra rằng `FLUSHALL` bị từ chối mà không phải thử xóa dữ liệu thật.

| Lệnh mô phỏng | Kỳ vọng với user chỉ có `~app:orders:* +get +set` |
|---|---|
| `GET app:orders:913` | Cho phép |
| `SET app:orders:913 PAID` | Cho phép |
| `GET app:billing:913` | Từ chối do key pattern |
| `DEL app:orders:913` | Từ chối do command permission |
| `FLUSHALL` | Từ chối do command permission |
| `PUBLISH app:events:orders hello` | Từ chối nếu thiếu channel/command |

**Giới hạn:** `ACL DRYRUN` không thực thi Redis command, không xác nhận key tồn tại, không kiểm tra `WRONGTYPE`/network/serializer, không thực thi các lệnh bên trong Lua và không bảo đảm Java application startup thành công. Cần integration test trên Redis thật để bổ sung.

## 19. Integration test ACL với Testcontainers

Test nên chứng minh cả trường hợp **được phép** và **bị từ chối**:

1. Spring kết nối đúng Redis user, không dùng default credential.
2. GET/SET với key trong namespace chạy thành công.
3. Cùng command trên key ngoài namespace bị từ chối.
4. Command không được cấp (ví dụ DEL) bị từ chối ngay cả trên key hợp lệ.
5. Driver/health/reconnect có đủ quyền cần thiết mà không mở wildcard.

### 19.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

### 19.2. Test mẫu

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

class RedisAclIntegrationTest {

    @Test
    void serviceUserRespectsCommandAndKeyPatterns() throws Exception {
        try (GenericContainer<?> redis = new GenericContainer<>(
                DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379)) {

            redis.start();

            var created = redis.execInContainer(
                    "redis-cli", "ACL", "SETUSER",
                    "svc_test", "reset", "on",
                    ">lab-only-password",
                    "resetchannels", "~it:acl:*",
                    "+ping", "+get", "+set");

            assertThat(created.getExitCode()).isZero();
            assertThat(created.getStdout()).contains("OK");

            RedisStandaloneConfiguration cfg =
                    new RedisStandaloneConfiguration(
                            redis.getHost(), redis.getMappedPort(6379));
            cfg.setUsername("svc_test");
            cfg.setPassword(
                    RedisPassword.of("lab-only-password"));

            LettuceConnectionFactory factory =
                    new LettuceConnectionFactory(cfg);
            factory.afterPropertiesSet();

            try {
                StringRedisTemplate limited =
                        new StringRedisTemplate(factory);

                limited.opsForValue().set("it:acl:allowed", "READY");

                assertThat(limited.opsForValue().get(
                        "it:acl:allowed")).isEqualTo("READY");

                assertThatThrownBy(() ->
                        limited.opsForValue().set(
                                "private:other", "DENIED"))
                        .isInstanceOf(RuntimeException.class);

                assertThatThrownBy(() ->
                        limited.delete("it:acl:allowed"))
                        .isInstanceOf(RuntimeException.class);
            } finally {
                factory.destroy();
            }
        }
    }
}
```

Test này chỉ dùng Redis container lab và một password **không dùng ở production**. Khi chạy thực, driver có thể yêu cầu thêm một command handshake theo phiên bản; cần điều tra và cho phép command tối thiểu đã xác nhận. Với negative assertions, bộ test production-grade phải xác minh root cause thực sự là **NOPERM**, không phải connection timeout hoặc container lỗi.

### 19.3. Ma trận test phải tách lỗi quyền

| Case | Lệnh | Key | Kỳ vọng |
|---|---|---|---|
| Positive | `SET` | `it:acl:ok` | Thành công |
| Positive | `GET` | `it:acl:ok` | Thành công |
| Negative command | `DEL` | `it:acl:ok` | NOPERM do thiếu `+del` |
| Negative key | `SET` | `private:other` | NOPERM do key pattern |
| Negative admin | `FLUSHALL` trong `ACL DRYRUN` | Không có key | Bị từ chối |

Thử `FLUSHALL` chỉ bằng `ACL DRYRUN`/policy test, **không thực thi** nó trên một Redis server có dữ liệu cần giữ.

## 20. Quan sát ACL và xử lý NOPERM

Redis quản trị có:

```redis
ACL LOG 10
ACL GETUSER svc_orders
ACL CAT
```

`ACL LOG` chứa các sự kiện authentication/authorization bị từ chối gần đây. Thông tin như user, command, key/channel hoặc lý do có thể giúp xác định sự cố; trường cụ thể phụ thuộc Redis version. Không in raw password hoặc nhạy cảm từ logs và chỉ cho người vận hành được phép xem.

### 20.1. Quy trình chẩn đoán

1. Xác định endpoint/server, Redis username và credentials mà connection đang dùng.
2. Xác định lỗi `NOAUTH`, `WRONGPASS` hay `NOPERM`.
3. Với NOPERM, tìm command bị từ chối và key/channel thực sự được gửi.
4. Kiểm tra namespace/prefix/serializer của Spring Cache hoặc Repository.
5. Kiểm tra driver handshake, transaction, Lua commands khi liên quan.
6. Với Redis Cluster, kiểm tra quyền trên **node đang sở hữu slot** và các node khác.
7. Nếu use case hợp lệ, bổ sung **quyền nhỏ nhất** vào policy/IaC.
8. Chạy lại positive/negative tests và theo dõi auth errors.

Không tự cấp `+@all ~*` để chữa NOPERM.

### 20.2. Những metric có ích

| Metric đề xuất | Ý nghĩa |
|---|---|
| `redis.auth.failure.count` | Số lần authentication lỗi |
| `redis.acl.noperm.count` | Số command/key/channel bị từ chối |
| `redis.acl.denied.command` | Phân bố theo command |
| `redis.acl.denied.namespace` | Namespace nào gây từ chối |
| `redis.acl.policy.version` | Phiên bản policy theo node |
| `redis.acl.rotation.progress` | Trạng thái đổi password |
| `redis.cluster.acl.drift` | Lệch quyền giữa nodes |

Đây là **gợi ý instrumentation**, không phải toàn bộ metric Redis/Spring tự động xuất sẵn.

## 21. Những lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Mọi service dùng default user toàn quyền | Blast radius lớn khi một service lỗi/lộ secret | Tài khoản riêng, least privilege |
| Có `~tenant:*` nhưng cấp `+@all` | `FLUSHALL` hoặc command keyless có thể thao tác ngoài pattern | Allowlist command |
| Dùng `+@read +@write` thay vì phân tích nhu cầu | Cấp nhiều lệnh không cần | `ACL CAT` và test |
| Không reset/reconcile user cũ | Quyền tồn dư sau thay đổi | Policy đầy đủ, triển khai có kế hoạch |
| Cho `~app:*` cho tất cả tenant | Ranh giới quá rộng | Prefix hẹp, authorization ở API |
| Coi key pattern là Pub/Sub channel rule | Listener/PUBLISH NOPERM | `&...` và command phù hợp |
| Cho `PSUBSCRIBE app:*` quá rộng | Listener có thể nghe event nhạy cảm | Pattern hẹp và test |
| Coi consumer group là Redis ACL identity | Không hạn chế được worker như mong đợi | User credential riêng |
| Thay key serializer không cập nhật ACL | Key bytes không khớp pattern | Kiểm thử bytes và key prefix |
| Cho `KEYS`/`SCAN` để debug | Tải server và rò tên key | Worker vận hành riêng |
| Dùng một Redis Hash cho field nhiều mức quyền | HGETALL có thể trả field nhạy cảm | Tách key/nguồn dữ liệu |
| Chỉ cập nhật ACL trên một node Cluster | Lỗi tùy slot/failover | Đồng bộ mọi node |
| Hardcode password vào repo/log | Lộ credential | Secret manager, rotation |
| Coi đổi password là kill session ngay | Existing connections có thể tiếp tục | Revoke/kết thúc connections đúng runbook |
| Chỉ chạy ACL DRYRUN, không integration test | Bỏ sót serializer/handshake/caches | Test với Redis thật |
| Dùng `EVAL` và nghĩ Lua bypass ACL | Hiểu sai giới hạn, có thể lỗi production | Test commands/key access trong script |

## 22. Bài thực hành trong Redis lab

### Bài 1 — Read-only theo prefix

1. Tạo user `svc_catalog_ro` có `~app:catalog:*`, `+get` và `+ping`.
2. Admin ghi sẵn `app:catalog:p-100`.
3. Login bằng `svc_catalog_ro`, `GET` key đó thành công.
4. `SET` key đó bị NOPERM do thiếu command.
5. `GET app:orders:913` bị NOPERM do key pattern.

### Bài 2 — Command và key là hai rào khác nhau

1. Tạo user `+get` nhưng chưa có key pattern.
2. Thử GET một key bất kỳ: bị từ chối.
3. Thêm `~app:catalog:*`; GET key hợp lệ.
4. Thu hồi `+get` nhưng giữ key pattern; GET bị chặn lại.
5. Giải thích vì sao chỉ một trong hai quyền là chưa đủ.

### Bài 3 — ACL DRYRUN Redis 7+

1. `ACL DRYRUN svc_catalog_ro GET app:catalog:p-100`.
2. `ACL DRYRUN svc_catalog_ro SET app:catalog:p-100 x`.
3. `ACL DRYRUN svc_catalog_ro GET app:secrets:token`.
4. `ACL DRYRUN svc_catalog_ro FLUSHALL`.
5. Lập bảng ALLOW/DENY và không chạy command phá hủy thật.

### Bài 4 — Read/write patterns và selector

1. Tạo `svc_reports` với `%R~app:reports:*` và `%W~app:reports:out:*`.
2. Cho `+get +set`.
3. Xác nhận đọc source được nhưng không sửa source.
4. Xác nhận ghi output được.
5. Dùng selector `(+set ~app:reports:out:*)`, so sánh mô hình cấp quyền.

### Bài 5 — Pub/Sub

1. Tạo user publisher với `+publish &app:events:*`.
2. Tạo listener với `+subscribe +psubscribe &app:events:*`.
3. Thử subscribe/publish `app:events:orders`.
4. Thử channel `other:secret`: bị chặn.
5. So sánh `PSUBSCRIBE app:events:*` với `PSUBSCRIBE app:*`.

### Bài 6 — Spring Boot và Testcontainers

1. Tạo Redis container riêng.
2. Tạo ACL user `svc_test` theo prefix `~it:acl:*`.
3. Cấu hình `StringRedisTemplate` kết nối bằng user đó.
4. Test SET/GET thành công trong prefix.
5. Test SET ngoài prefix và DEL không được cấp.
6. Xác nhận lỗi là NOPERM, không phải connection failure.

### Bài 7 — Spring Cache và Redis Streams

1. Tạo cache entry qua `@Cacheable`, xem key prefix thật.
2. Cấp quyền cache read/write tối thiểu.
3. Test eviction, clear và xác định command phụ trợ.
4. Tạo stream/group bằng admin user.
5. Consumer user chỉ có `XREADGROUP`/`XACK` trên đúng stream.
6. Thử `XGROUP DESTROY` hoặc `XADD` khi chưa được cấp để thấy ACL bảo vệ.

### Bài 8 — Redis Cluster

1. Tạo Cluster test với nhiều master.
2. Lấy key thuộc nhiều slot.
3. So sánh `ACL GETUSER` trên từng node.
4. Mô phỏng drift chính sách ở test, quan sát lỗi theo slot.
5. Reconcile rule và test sau failover/resharding trong lab.

## 23. Checklist triển khai production

**Người dùng và commands**

1. Mỗi service/function có Redis user phù hợp?
2. Policy deny-by-default, có allowlist commands cụ thể?
3. Đã loại lệnh admin/keyless nguy hiểm, không dựa chỉ vào key pattern?
4. Đã xem `ACL CAT` theo Redis server version hiện tại?
5. Có kiểm tra lệnh phụ của Lettuce/Jedis, Spring Cache/Repository/Stream?

**Key và channel**

6. Prefix key có hẹp theo module/tenant?
7. Key bytes/serializer có khớp ACL patterns?
8. Redis 7 read/write patterns và selectors có dùng đúng semantics?
9. Không trộn dữ liệu field khác quyền trong cùng Hash?
10. Pub/Sub có `resetchannels` và `&channel-pattern`?
11. Consumer group được phân biệt rõ với Redis ACL user?
12. Multi-key/script vừa thỏa ACL vừa thỏa Cluster slot?

**Secrets và vận hành**

13. Credentials lưu qua secret manager, không ở repository/log?
14. TLS/network restriction đúng?
15. Có chiến lược password rotation và revoke existing connection?
16. ACL policy lưu bền và tự reconcile?
17. Cluster mọi node có quyền đồng nhất?
18. Sentinel và Redis data nodes dùng đúng credentials?
19. Có alert auth/NOPERM và ACL drift?

**Kiểm thử**

20. Có `ACL DRYRUN` matrix với cả commands nguy hiểm?
21. Có integration test positive/negative trên Redis thật?
22. Có tách NOPERM command, NOPERM key và lỗi network?
23. Có test Spring Cache, Repository, Streams, Pub/Sub khi sử dụng?
24. Có kiểm tra lại sau nâng Redis/Spring/Lettuce hoặc đổi serializer?
25. Có kế hoạch rollback policy khi triển khai không thành công?

## 24. Tổng kết

Redis ACL phân quyền theo **user**, **commands/categories**, **key patterns** và **Pub/Sub channels**. Một user có `+get` chưa chắc được đọc mọi key; một user có `~app:orders:*` chưa chắc được gọi `SET`. Từ Redis 7, `%R~...`, `%W~...` và selectors diễn đạt chính sách đọc/ghi tinh vi hơn.

Tuy nhiên, key pattern không bảo vệ các lệnh **toàn server không có key arguments**, không phân quyền từng field trong Hash và không tự xác thực tenant của HTTP request. Vì thế phải ưu tiên **deny-by-default**, tách credential theo chức năng và giữ logic business authorization trong ứng dụng.

Với Spring Data Redis, hãy kiểm tra **key bytes** và prefix thực do serializer/Cache/Repository tạo ra, các command do driver gửi và policy trên toàn Redis Cluster. Sử dụng `ACL DRYRUN`, integration test với Redis thật và `ACL LOG` để xác nhận quyền; quản lý TLS, secrets, rotation và cấu hình bền vững. **Không chữa lỗi NOPERM bằng cách mở `+@all ~*`** nếu chưa xác định yêu cầu thực sự của ứng dụng.

## Tài liệu tham khảo

- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): user, nhóm lệnh, key patterns, selectors và channels.
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/): quy tắc tạo/sửa Redis ACL user.
- [Redis — ACL CAT](https://redis.io/docs/latest/commands/acl-cat/): phân loại lệnh Redis.
- [Redis — ACL GETUSER](https://redis.io/docs/latest/commands/acl-getuser/): xem quyền của user.
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/): kiểm tra quyền không thực thi command.
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/): log auth/permission bị từ chối.
- [Redis — ACL SAVE](https://redis.io/docs/latest/commands/acl-save/): lưu ACL file theo cấu hình.
- [Redis — Redis Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/): bảo vệ network, authentication và TLS.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): channels và subscriptions.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slot và routing của Redis Cluster.
- [Spring Boot — Working with NoSQL/Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html): cấu hình Redis username/password.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): templates, serializers và operations.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): Redis CacheManager, prefix và cache writer.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): consumer groups, XREADGROUP và XACK.
- [Spring Data Redis — Redis Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): listener và publisher.
