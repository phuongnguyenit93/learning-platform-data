# Checklist đối chiếu cấu hình, lệnh và topology trước khi kết luận lỗi

Trong ứng dụng **Spring Data Redis**, một triệu chứng như “không đọc được key”, “Redis mất dữ liệu”, “thỉnh thoảng timeout” hoặc “consumer không nhận message” có thể xuất phát từ nhiều tầng khác nhau:

- Ứng dụng đang dùng **profile, endpoint hoặc credential khác** với môi trường dự kiến.
- Spring Boot tạo connection factory hoặc template bằng cấu hình không như người triển khai nghĩ.
- DNS, firewall, TLS, ACL hoặc network routing khiến một số kết nối thất bại.
- Serializer, namespace hoặc Redis key type khác nhau giữa nơi ghi và nơi đọc.
- Redis trả **nil, số 0, collection rỗng hoặc lỗi command** theo ngữ nghĩa hợp lệ nhưng ứng dụng diễn giải sai.
- Key thật sự hết TTL, bị eviction, bị xóa hoặc được đọc từ replica chưa cập nhật.
- Redis Cluster chuyển hash slot, một node không sẵn sàng hoặc client topology chưa kịp refresh.
- Redis Streams consumer đã đọc message nhưng chưa ACK, còn pending ở group hoặc consumer khác.
- Spring Cache, Caffeine L1 hoặc một lớp repository trung gian khiến kết quả không phản ánh trực tiếp Redis.

Bài học này trình bày một **checklist chẩn đoán có thứ tự**, giúp đối chiếu từ cấu hình tới lệnh và topology trước khi kết luận Redis, Spring Data Redis hoặc dữ liệu có lỗi.

Mục tiêu không phải chạy thật nhiều lệnh kiểm tra. Mục tiêu là thu thập **đúng bằng chứng**, hiểu phạm vi của từng bằng chứng và phân loại được: **lỗi cấu hình**, **lỗi truy cập**, **ngữ nghĩa command hợp lệ**, **dữ liệu/serialization sai**, **sự cố topology** hay **lỗi trong ứng dụng**.

## 1. Nguyên tắc điều tra: triệu chứng không phải nguyên nhân

Những phát biểu sau chưa đủ để kết luận root cause:

> “API trả 404 nên Redis đã mất key.”

> “`PING` trả `PONG` nên Redis chắc chắn khỏe.”

> “Cùng một key mà máy A đọc thấy, máy B không đọc thấy; chắc Redis lỗi.”

> “Consumer group lag bằng 0 nên tất cả message đã xử lý xong.”

> “`SET` timeout nên Redis chắc chắn chưa ghi dữ liệu.”

Mỗi câu bỏ qua một ranh giới kỹ thuật:

| Quan sát | Điều thực sự chứng minh | Điều **chưa** chứng minh |
|---|---|---|
| HTTP `404` | API đã trả kết quả not-found | Redis key thật sự không tồn tại ở node authoritative |
| Redis `PING` thành công | Endpoint đó đã phản hồi lệnh PING | GET/SET/ACL/serialization/Cluster slots đều đúng |
| `GET` trả nil | Key được hỏi không có String value theo semantics lệnh tại nơi đọc | Database không có đối tượng; mọi replica đều không có key |
| `EXISTS` trả 1 | Key tồn tại lúc lệnh chạy | Key còn ở lần đọc tiếp theo; value đúng type |
| `TTL` trả -2 | Key không tồn tại ở thời điểm TTL tại node được đọc | Vì sao key biến mất; có từng tồn tại không |
| `XINFO GROUPS` lag 0 | Theo định nghĩa lag khả dụng, group không còn entry mới chờ phân phối | PEL không còn message chưa ACK |
| Client timeout sau `INCR` | Client không nhận kết quả trong deadline | `INCR` chưa được Redis thực thi |
| Một Cluster node UP | Node đang được kiểm tra phản hồi | Mọi slot và mọi node đều phục vụ bình thường |

**Quy tắc chẩn đoán:** mỗi kết luận cần chỉ rõ *đã quan sát ở tầng nào, thời điểm nào, từ client nào, tới node nào, bằng lệnh nào và với dữ liệu nào*.

## 2. Checklist 60 giây đầu trước khi chạy bất kỳ lệnh nào

Trước khi thay cấu hình hoặc dọn cache, ghi lại:

- [ ] **Triệu chứng chính xác:** HTTP status, loại exception, command, dữ liệu mong đợi và kết quả thực.
- [ ] **Mốc thời gian:** bắt đầu lúc nào, liên tục hay ngắt quãng, có trùng deploy/failover/scale-up không.
- [ ] **Phạm vi ảnh hưởng:** một endpoint, một key, một tenant, một pod, một Redis node hay toàn bộ hệ thống.
- [ ] **Môi trường:** dev/staging/prod, namespace, region/AZ, application version, active Spring profiles.
- [ ] **Redis deployment:** Standalone, Sentinel, Redis Cluster hay managed service tương đương.
- [ ] **Đường truy cập:** địa chỉ private endpoint, data port, TLS mode, ACL user **không ghi password**.
- [ ] **Thao tác:** `GET`, `HGET`, `MGET`, `SET`, `XREADGROUP`, Lua, Spring Cache hay API nào.
- [ ] **Vị trí xảy ra:** trước khi gửi lệnh, lúc kết nối, khi Redis thực thi hay khi deserialize kết quả.
- [ ] **Nguồn sự thật:** Redis là database chính, cache, session store, queue hay trạng thái phối hợp?
- [ ] **Ảnh hưởng bảo mật:** có nguy cơ đọc stale permission/session, nhầm missing với Redis outage hay không.

Không bắt đầu bằng `FLUSHALL`, xóa namespace, recreate consumer group hoặc restart toàn bộ Redis. Những thao tác đó vừa có thể phá bằng chứng vừa tạo ra sự cố mới.

### 2.1. Ghi nhận một ca lỗi dưới dạng dữ liệu

Ví dụ báo cáo ban đầu:

```text
Environment: staging
App version: 2.8.4
Active profiles: staging,redis
Observed at: 2026-11-13T03:14:20Z
HTTP endpoint: GET /api/products/p-42
HTTP response: 404
Expected behavior: product p-42 tồn tại trong database
App pod: catalog-7d4f... (đã rút gọn)
Redis operation: GET cache:catalog:v3:p-42
Spring result: null, không ném exception
Redis mode: Cluster, 3 primary
Recent change: v3 đổi prefix từ v2 sang v3
```

Ngay cả khi không có thông tin root cause, báo cáo này chỉ ra những hướng kiểm tra hợp lý: prefix, serializer, key ở node đúng slot và cache-aside fallback. Không phải mọi HTTP `404` đều do Redis lỗi.

### 2.2. Không tiết lộ secret khi điều tra

Ghi nhận **tên ACL user**, endpoint đã được phép công bố, loại command và namespace; tránh ghi:

- Redis password, token, client certificate private key.
- Session ID, OAuth2 token, idempotency secret.
- Toàn bộ Redis URI có username/password.
- Dữ liệu PII, JWT, payload nghiệp vụ nhạy cảm.
- Raw network capture chưa được khử dữ liệu nhạy cảm.

Không đưa key thực chứa session ID vào log chẩn đoán công khai. Nếu cần correlation, dùng request ID hoặc hash/identifier đã được xử lý theo chính sách bảo mật.

## 3. Xác định Redis đóng vai trò gì trước khi chọn cách xử lý

Một lệnh lỗi ở **cache tùy chọn** có mức nghiêm trọng khác với cùng lỗi ở **session store**.

| Vai trò Redis | Khi GET trả nil | Khi Redis không truy cập được |
|---|---|---|
| Cache sản phẩm có database nguồn | Cache miss; đọc database | Có thể fallback sang nguồn với giới hạn tải |
| Spring Session | Session không có/hết hạn theo repository semantics | Không cấp quyền chỉ vì không kiểm tra được session |
| Redis Streams | Không có entry mới ở offset đó, hoặc đọc sai offset | Không tự ACK; kiểm tra PEL và phục hồi |
| Rate limiter | Key/bộ đếm chưa khởi tạo theo policy | Chọn fail-closed hoặc biện pháp bảo vệ thay thế |
| Distributed lock | Lock có thể chưa tồn tại | Không coi timeout là lock đang trống |
| Idempotency key | Chưa có dấu hoàn tất theo protocol | Không retry mutation nếu outcome chưa rõ |
| Temporary notes có TTL | Tài nguyên đã hết hạn/không tồn tại | Trả lỗi lưu trữ, không tự tạo giá trị giả |
| Cache L1/L2 | L2 miss còn có nguồn | Kiểm tra L1 stale hoặc fallback storm |

Do đó, **một checklist kỹ thuật cần đi kèm hợp đồng nghiệp vụ**: nguồn nào có thẩm quyền tuyên bố “dữ liệu không tồn tại” và nguồn nào được phép lỗi mà request vẫn tiếp tục?

## 4. Tầng thứ nhất: đối chiếu cấu hình Spring Boot thực tế

Ứng dụng có thể đọc cấu hình từ:

- `application.yml`, `application-{profile}.yml`.
- Biến môi trường.
- Command-line arguments.
- Kubernetes ConfigMap/Secret.
- Spring Cloud Config hoặc configuration provider khác.
- Custom `@Bean` cấu hình `RedisConnectionFactory`.
- Custom Redis client do một thư viện hoặc module tự tạo.

Một file YAML đúng trong Git **không chứng minh** instance đang chạy đã nhận đúng giá trị.

### 4.1. Đối chiếu những mục tối thiểu

| Mục | Bằng chứng cần thu | Lỗi điển hình |
|---|---|---|
| Active profiles | Profile thật của pod/JVM | Prod đang đọc file staging |
| Redis host/port | Endpoint runtime đã được khử thông tin nhạy cảm | Trỏ nhầm Redis khác |
| Standalone/Sentinel/Cluster | Loại connection factory/topology thực dùng | Client Standalone tới Cluster node |
| TLS enabled | Client/server TLS mode trùng nhau | SSL handshake failure hoặc plain-text mismatch |
| Username/ACL | User name và quyền yêu cầu | `NOAUTH` / `NOPERM` |
| Redis logical database | Index được cấu hình nếu mode cho phép | Đọc DB 0 trong khi app ghi DB 1 |
| Cache key prefix | Prefix hiện tại, version, tenant | Đọc v3 nhưng dữ liệu ở v2 |
| Serializers | Key/value/hash serializers | Java String giống nhau nhưng bytes khác |
| Read preference | Primary hay replica reads | Replica trả dữ liệu cũ |
| Timeouts | Connect và command timeout | Fail chậm, gây retry storm |
| Client pool/resources | Connection config, thread load | Connection starvation |
| CacheManager | Provider và cache names | Đọc Caffeine thay vì Redis |
| Multiple factory beans | Factory nào được inject vào component | Hai service dùng hai Redis deployments |

### 4.2. Ví dụ cấu hình Redis theo Spring Boot

Ở những dòng Spring Boot hiện đại, cấu hình thường có dạng:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD:}
      connect-timeout: 2s
      timeout: 2s
```

Với Redis có TLS:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
```

Tên property thay đổi theo dòng Spring Boot; ví dụ cũ có thể dùng prefix `spring.redis.*`. **Đối chiếu configuration metadata của phiên bản đang chạy**. Một property sai tên có thể bị bỏ qua, trong khi ứng dụng vẫn khởi động bằng default khác.

Không in toàn bộ `Environment` hoặc `/actuator/env` ra log công khai. Nếu cần so sánh runtime, chỉ công bố những key đã được lọc và mask secret.

### 4.3. Có bao nhiêu RedisConnectionFactory?

Spring Boot thường auto-configure một connection factory khi chưa có custom bean phù hợp. Nhưng dự án có thể tự tạo nhiều factory:

```text
catalogRedisConnectionFactory -> Redis A
sessionRedisConnectionFactory -> Redis B
reactiveConnectionFactory     -> Redis C
```

Nếu `StringRedisTemplate` đọc Redis A còn cache writer dùng Redis B, người điều tra có thể quan sát “cùng Java key” nhưng không bao giờ thấy dữ liệu.

Kiểm tra:

- Bean type/name được inject vào service.
- `@Qualifier`/`@Primary`.
- `RedisTemplate` và `CacheManager` thực sự dùng factory nào.
- Spring Session repository sử dụng Redis connection nào.
- Reactive và synchronous clients có được cấu hình giống nhau không.

Không đổi thành một connection factory duy nhất nếu việc tách Redis là chủ đích; mục tiêu chẩn đoán là xác minh **consumer và producer có cùng hợp đồng hạ tầng**.

## 5. Tầng thứ hai: DNS, network route và cổng

Khi gặp `RedisConnectionFailureException`, connection refused hoặc timeout, kiểm tra theo thứ tự:

1. Hostname có resolve đúng private IP không?
2. Client và Redis nằm trên các mạng có route được phép không?
3. Firewall/security group/NetworkPolicy có cho source thực kết nối không?
4. Redis server có đang listen trên interface/port đó không?
5. Client có cần TLS nhưng đang mở plain connection, hoặc ngược lại không?
6. Redis Cluster/Sentinel có quảng bá node address mà client không thể truy cập không?
7. Kết nối bị từ chối ngay, bị timeout khi bắt tay hay timeout khi chạy lệnh?

Không coi **DNS resolve thành công** là đủ. Địa chỉ đúng nhưng bị firewall chặn vẫn không sử dụng được.

### 5.1. Phân biệt lỗi kết nối

| Triệu chứng | Giả thuyết ưu tiên | Bằng chứng tiếp theo |
|---|---|---|
| DNS lookup failure | Sai hostname/DNS search/zone | So sánh DNS từ **chính pod** xảy ra lỗi |
| Connection refused | Không listen, port sai, proxy chủ động từ chối | Kiểm tra listen socket và target port |
| Connection timeout | Route, firewall, packet loss hoặc node quá tải | Đối chiếu network policy, TCP connection metrics |
| TLS handshake failure | Certificate/CA/SAN/protocol mismatch | Log TLS đã khử secret, trust chain |
| `NOAUTH` / `WRONGPASS` | Sai credential hoặc không AUTH | Kiểm tra user/secret version |
| `NOPERM` | Kết nối và AUTH có thể đã thành công nhưng thiếu quyền | Xác định command/key/channel bị từ chối |
| Command timeout sau connect | Redis chậm, network, queue/pool, blocking command | Metrics server + client latency |
| Kết nối chỉ lỗi khi failover | DNS/discovery/advertised endpoints hoặc stale topology | Sentinel/Cluster state, reconnect logs |

**Kiểm tra từ cùng network namespace** với ứng dụng nếu có thể. Một lệnh `redis-cli PING` từ laptop quản trị có thể thành công trong khi application pod bị chặn bởi NetworkPolicy.

### 5.2. Docker và Kubernetes có ranh giới khác nhau

- `localhost` bên trong container thường chỉ container đó, không phải host hoặc container Redis khác.
- Docker Compose service name thường được resolve trong network tương ứng.
- Redis container có `ports: "6379:6379"` có thể publish port ra host, nhưng ứng dụng cùng Docker network thường không cần publish.
- Kubernetes `ClusterIP` cho truy cập nội bộ, nhưng vẫn cần NetworkPolicy khi muốn giới hạn namespace/pod.
- Kết nối application→Redis có thể cần cả egress allow phía app và ingress allow phía Redis.
- Với managed Redis, private endpoint, VPC peering và security group phải phù hợp hạ tầng thật.

Không sửa lỗi kết nối bằng cách mở Redis ra `0.0.0.0/0` hoặc `::/0`. Cần xác định source hợp lệ rồi chỉ mở đúng đường cần thiết.

## 6. Tầng thứ ba: TLS, ACL và xác thực

`PING` có thể thành công với một account nhưng `GET`/`SET` vẫn thất bại do ACL.

Checklist:

- [ ] Redis server và client cùng sử dụng TLS/plain mode.
- [ ] Client xác minh certificate chain, hostname và CA đúng.
- [ ] Redis ACL user được cấu hình đúng environment.
- [ ] Credential được cấp từ secret source hiện hành, không phải bản đã rotate.
- [ ] User có quyền command cần thiết, ví dụ `GET`, `SET`, `DEL`, `HGET`.
- [ ] Key pattern ACL bao phủ namespace thực sau serializer/prefix.
- [ ] Với Pub/Sub, user có quyền channel phù hợp.
- [ ] Với Redis Streams, user có quyền các lệnh group/read/ack/claim cần thiết.
- [ ] Với Cluster/Sentinel, client có thể khám phá và kết nối tới các endpoint trả về.
- [ ] Không có lỗi auth khác chỉ xảy ra sau reconnect/credential rotation.

### 6.1. Ví dụ kiểm tra read-only trong môi trường được phép

```bash
# Kiểm tra bằng endpoint private và account có quyền phù hợp.
# Password được lấy từ secret manager/prompt, không ghi trực tiếp.
redis-cli \
  -h private-redis.example.internal \
  -p 6379 \
  --user catalog_reader \
  PING

# Nếu Redis yêu cầu TLS, bổ sung cấu hình --tls và CA tương ứng.
```

`PONG` không kiểm chứng mọi quyền. Nếu application cần `GET`, kiểm tra một key an toàn thuộc namespace test bằng account đó.

Không dùng thử `CONFIG SET`, `FLUSHALL` hay thao tác nguy hiểm để “xem tài khoản có đủ quyền không”. Quyền quản trị cần được đánh giá qua ACL policy đã cấp hoặc bài kiểm thử chuyên biệt trong môi trường test.

### 6.2. Một ACL NOPERM không phải Redis miss

Nếu `GET cache:catalog:v3:p-42` trả lỗi `NOPERM`, ứng dụng **không có bằng chứng key có hay không**. Một đoạn code:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ignored) {
    return null;
}
```

đã chuyển lỗi truy cập thành kết quả “không tồn tại” giả. Đây là lỗi xử lý trong ứng dụng, không phải ngữ nghĩa Redis.

## 7. Tầng thứ tư: xác định key vật lý thực sự được truy vấn

Một nguyên nhân thường gặp của “ghi được nhưng đọc không được” là **nơi ghi và nơi đọc dùng hai key khác nhau**, dù giá trị Java trông tương tự.

### 7.1. Đối chiếu các thành phần của key

```text
Prefix        Module       Version     Tenant       ID
   |             |            |          |          |
   v             v            v          v          v
cache:catalog:product:v3:tenant-7:p-42
```

Checklist:

- Prefix Redis từ cache manager hay service code?
- Có namespace môi trường, tenant, region hoặc locale không?
- Có version trong key không?
- Dấu phân tách và chữ hoa/thường có nhất quán không?
- Producer và consumer dùng cùng canonical ID không?
- Có ký tự Unicode, space hoặc escape khác không?
- Redis Cluster hash tag `{...}` có làm thay đổi slot không?
- Key được serialize thành bytes thế nào?
- Có một lớp Spring Cache tự thêm prefix khác không?
- Có viết vào logical database khác không (nếu mode Redis hỗ trợ)?

### 7.2. Serializer key khiến một Java String thành byte key khác

Ví dụ cả hai component gọi:

```java
redisTemplate.opsForValue().get("product:42");
```

Nhưng:

- Template A dùng `StringRedisSerializer` cho key.
- Template B dùng serializer khác, ví dụ JDK serializer.

Redis lưu **byte key**, không lưu “Java String object”. Hai template có thể truy vấn hai chuỗi byte khác nhau.

Giải pháp chẩn đoán không phải đổi serializer ngay giữa production. Hãy xác định serializer thực tế ở cả writer/reader rồi so sánh key bytes/namespace trong môi trường test hoặc công cụ read-only được cấp phép.

### 7.3. Phân biệt GET nil với lỗi mapping

Nếu `GET` trả bytes nhưng JSON không giải mã được thành DTO, Redis **không báo key thiếu**. Đó có thể là lỗi schema, Jackson configuration, class version hoặc payload bị ghi sai.

```text
Redis GET -> value bytes
     |
     v
JSON/JDK deserialization
     |
   +---+---+
   |       |
  OK      Fail
   |       |
   v       v
Value   Invalid payload
```

Không chuyển `SerializationException`/Jackson exception thành `Optional.empty()` một cách vô điều kiện.

## 8. Tầng thứ năm: kiểm tra đúng ngữ nghĩa command

Không có một quy tắc “Redis key không tồn tại luôn trả null”. Mỗi command có contract khác nhau.

| Command | Trường hợp key/field thiếu | Điều cần nhớ |
|---|---|---|
| `GET k` | Nil | Sai kiểu Redis thường gây `WRONGTYPE` |
| `HGET k f` | Nil | Hash thiếu **hoặc** field thiếu |
| `MGET k1 k2` | Vị trí nil | Nil cũng có thể do key chứa kiểu không phải String |
| `EXISTS k` | 0 | Chỉ phản ánh thời điểm command chạy |
| `TTL k` | -2 | -1 là key có tồn tại nhưng không có expiry |
| `PTTL k` | -2 | Đơn vị millisecond |
| `TYPE k` | `none` | Có ích để phân biệt String/Hash/Set/ZSet/Stream |
| `SCARD k` | 0 | Với Set thiếu theo semantics Redis |
| `SMEMBERS k` | Tập rỗng | Empty collection không phải access error |
| `LLEN k` | 0 | Không phân biệt nguồn dữ liệu đã từng tồn tại |
| `XREADGROUP ... >` | Có thể không có entry mới | Không có nghĩa PEL đã sạch |
| `XPENDING stream group` | Count pending | Không nói message nào đã commit nghiệp vụ |
| `XACK stream group id` | Số pending được xác nhận | Không xóa payload khỏi stream |
| `SET ... NX` | Không ghi khi key đã tồn tại | Không đồng nghĩa lỗi kết nối |
| `HSET` | Số field mới được thêm | Ghi đè field có thể trả số 0, không phải failure |

### 8.1. Ví dụ GET với key không tồn tại và sai kiểu

Trên Redis test riêng:

```bash
redis-cli DEL demo:diag:string
redis-cli GET demo:diag:string

redis-cli SET demo:diag:string "READY"
redis-cli GET demo:diag:string

redis-cli DEL demo:diag:set
redis-cli SADD demo:diag:set one
redis-cli GET demo:diag:set
```

Kết quả kỳ vọng:

- GET key thiếu trả nil.
- GET key String trả value.
- GET key Set trả `WRONGTYPE`.

Nếu ứng dụng bắt cả ba nhánh bằng `catch (Exception) { return null; }`, log sẽ mất dấu lỗi sai kiểu.

### 8.2. TTL không tự nói vì sao dữ liệu biến mất

```bash
redis-cli TTL demo:diag:string
redis-cli EXISTS demo:diag:string
redis-cli TYPE demo:diag:string
```

Một `TTL=-2` cho thấy key không tồn tại tại thời điểm kiểm tra, nhưng chưa chỉ ra nguyên nhân:

- Key chưa từng được tạo.
- Đã hết TTL.
- Bị `DEL` hoặc `UNLINK`.
- Bị cache eviction do memory pressure.
- Đã bị ghi/xóa bởi service khác.
- Đang đọc nhầm namespace/Redis deployment.
- Replica chưa nhận ghi hoặc đã xảy ra failover mất ghi.

**Một snapshot không thay thế timeline**. Để tìm nguyên nhân phải kết hợp logs, metrics, deploy history và đường ghi của ứng dụng.

### 8.3. EXISTS rồi GET vẫn có race

```text
T0: Client A EXISTS key -> 1
T1: Client B DEL key
T2: Client A GET key -> nil
```

Đây là tình huống hợp lệ, không tự là bằng chứng Redis “không nhất quán”. Hai command không nguyên tử như một transaction.

Nếu nghiệp vụ cần “chỉ tạo khi chưa có”, dùng `SET ... NX` hoặc một thao tác atomic phù hợp, thay vì check-then-act bằng hai command.

## 9. Cẩn thận với giá trị null trong Spring Data Redis

Trong ngữ cảnh **một lệnh GET thông thường, không queue trong transaction hoặc pipeline**, `StringRedisTemplate.opsForValue().get(key)` có thể trả Java `null` khi Redis trả nil.

Nhưng Spring Data Redis cũng có những trường hợp return value **chưa phải reply thực tế**:

- Lệnh đang được queue trong Redis transaction `MULTI`.
- Lệnh đang được queue trong pipelined execution.
- Một callback nhận `null` tạm thời vì kết quả sẽ được tập hợp sau.

```text
StringRedisTemplate GET bình thường:
    null có thể là Redis nil -> miss

GET trong pipeline/transaction callback:
    null có thể chỉ là placeholder -> chưa có reply
```

Ví dụ conceptual:

```java
List<Object> results = redisTemplate.executePipelined(
        (RedisCallback<Object>) connection -> {
            connection.stringCommands().get(rawKey);
            return null;
        });

// Kết quả lệnh nằm trong results sau khi pipeline hoàn tất,
// không nằm ở return value tức thời của command trong callback.
```

Đây là mẫu minh họa ngữ nghĩa `executePipelined`; `rawKey` phải là bytes đã encode bằng serializer phù hợp và callback cần theo hợp đồng của phiên bản Spring Data Redis sử dụng.

**Không viết nhánh tạo dữ liệu mới ngay khi callback command trong pipeline trả null.** Đó có thể là chưa nhận reply chứ không phải key thiếu.

## 10. Đối chiếu Spring Cache và tầng local cache

Khi code dùng `@Cacheable`, giá trị trả về có thể đi qua:

```text
Controller
    |
    v
@Cacheable AOP
    |
    +--> Caffeine L1 (nếu cấu hình)
    |
    +--> RedisCacheManager (nếu cấu hình)
    |
    +--> Method / database (nếu miss)
```

Không nên kết luận Redis có dữ liệu sai nếu API trả một value cũ mà không chứng minh API thực sự gọi Redis.

Checklist:

- [ ] Cache manager nào được chọn?
- [ ] Có nhiều `CacheManager`/`CacheResolver` không?
- [ ] Cache name và key expression là gì?
- [ ] Caffeine/L1 có được bật trong instance đó không?
- [ ] TTL L1 và TTL Redis L2 bao lâu?
- [ ] `@CacheEvict` chỉ xóa local cache hay tất cả instance?
- [ ] Có negative-cache entry không?
- [ ] Redis cache có lưu null dưới sentinel không?
- [ ] Serializer của Spring Cache có trùng với `StringRedisTemplate` không?
- [ ] Có AOP self-invocation khiến annotation cache không chạy như mong đợi không?

### 10.1. Spring Cache null khác Redis GET nil

Với Spring Cache:

```java
Cache cache = cacheManager.getCache("products");
Cache.ValueWrapper wrapper = cache.get("p-42");
```

Nếu cache tồn tại:

- `wrapper == null`: không có entry theo contract `Cache.get`.
- `wrapper != null && wrapper.get() == null`: có thể là **cached null** nếu provider được cấu hình hỗ trợ.
- `wrapper != null && wrapper.get() != null`: có value.

Đừng nhầm wrapper không có với một cached-null entry. Cũng đừng lấy một method `@Cacheable` trả `null` làm bằng chứng Redis key không có: method có thể đã trả cached null mà không gọi database.

### 10.2. Cache invalidation có thể đến muộn hoặc bị bỏ lỡ

Nếu ứng dụng có Caffeine L1 ở nhiều JVM và dùng Redis Pub/Sub để invalidate:

```text
DB cập nhật version 8
    |
    v
Redis L2 đổi version 8
    |
    v
Pub/Sub invalidation
    |
    +--> App A nhận, xóa L1
    +--> App B offline, bỏ lỡ message
    |
    v
App B vẫn trả version 7 từ L1 tới khi TTL/reconcile
```

Đây là giới hạn của Pub/Sub và cache topology, không phải Redis GET trả value sai. Nếu yêu cầu độ mới chặt, cần version/authoritative reads hoặc cơ chế invalidation bền.

## 11. Tầng thứ sáu: xác định Redis topology thực tế

Cùng một Redis endpoint có thể đại diện cho:

- Một Redis Standalone instance.
- Primary có replica nhưng không có Sentinel.
- Sentinel-managed primary/replicas.
- Redis Cluster với nhiều primary và hash slots.
- Managed Redis service với proxy/private endpoint và failover riêng.

Không dùng checklist Cluster cho Standalone một cách máy móc, cũng không dùng một lần `PING` của Standalone để kết luận Cluster khỏe.

### Bảng đối chiếu mode

| Mode | Nguồn routing | Bằng chứng cần xem |
|---|---|---|
| Standalone | Host/port đã cấu hình | Endpoint, role, DB index, INFO replication |
| Sentinel | Sentinel nodes và master name | Sentinel discovery, primary hiện tại, replica state |
| Cluster | Slot map và advertised node addresses | `CLUSTER INFO`, `CLUSTER SLOTS`/`SHARDS`, `CLUSTER KEYSLOT` |
| Managed proxy | Endpoint proxy của provider | Provider topology/status, route và failover events |
| Replication read | Client read preference | Primary vs replica, replication lag |

### 11.1. Mô hình Standalone

Nếu app cấu hình:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      database: 0
```

thì trước tiên kiểm tra đúng host/port/database và Redis role. Trên Standalone, logical DB có thể khiến hai process dùng `database: 0` và `database: 1` nhìn thấy hai tập key khác nhau.

Redis Cluster thông thường chỉ hỗ trợ **database 0**, nên lỗi `SELECT` hoặc giả định logical DB 1 trong Cluster có thể là lỗi cấu hình mode.

### 11.2. Replication không chia nhỏ dữ liệu

Một primary và hai replica thường giữ bản sao của cùng keyspace. Nếu một key vừa được ghi lên primary mà replica chưa bắt kịp, đọc replica có thể thấy value cũ hoặc nil.

Vì vậy, khi App A thấy value mới còn App B thấy value cũ, đối chiếu **read preference** và node thực đọc trước khi quy kết dữ liệu hỏng.

## 12. Redis Sentinel: master discovery và failover

Trong Sentinel mode, client có thể kết nối tới Sentinel rồi được hướng dẫn địa chỉ Redis primary hiện tại.

```text
Spring Boot / Lettuce
       |
       v
Sentinel endpoints
       |
       v
Master name -> current primary
       |
       +--> Primary A
                 |
                 +--> Replica B
                 +--> Replica C
```

Checklist:

- [ ] Sentinel master name trong ứng dụng đúng với cấu hình Sentinel.
- [ ] Ứng dụng truy cập được các Sentinel endpoints đã khai báo.
- [ ] Redis primary/replica được Sentinel trả về có private address phù hợp.
- [ ] ACL/TLS cho Sentinel và Redis data endpoint được cấu hình đúng.
- [ ] Client không ghim IP primary cũ sau failover.
- [ ] Khi failover, Lettuce reconnect/discovery có hoạt động trong timeout budget?
- [ ] Có ghi vừa thành công trên old primary nhưng chưa replicate sang new primary không?
- [ ] Replica mới promoted đã đủ điều kiện phục vụ write chưa?

Các lệnh quan sát Sentinel phải dùng qua endpoint có quyền:

```bash
redis-cli -h sentinel.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster

redis-cli -h sentinel.internal -p 26379 \
  SENTINEL masters
```

Tên/host chỉ minh họa. Trong môi trường cần TLS/ACL, dùng cấu hình CLI tương ứng và tránh ghi credential vào command line.

Một `PING` tới Sentinel trả `PONG` chỉ chứng minh Sentinel endpoint phản hồi; không chứng minh Redis primary do Sentinel giới thiệu đang tiếp nhận `SET`.

### 12.1. READONLY sau failover

Một client có thể vẫn kết nối tới node đã trở thành replica. Lệnh ghi có thể bị từ chối bằng lỗi như `READONLY`.

Đây là tín hiệu cần xem **role và routing**, không phải khẳng định key không tồn tại:

- Kiểm tra Redis node role.
- Kiểm tra Sentinel/Cluster topology mà client giữ.
- Kiểm tra reconnect/redirect behavior của Lettuce.
- Xem thời điểm failover so với request.
- Không dùng retry vô hạn trên stale primary address.

## 13. Redis Cluster: hash slot, redirect và địa chỉ node

Redis Cluster chia keyspace thành **16.384 hash slots**, mỗi slot thuộc về một primary. Client như Lettuce cần biết slot map để định tuyến key.

```text
              Spring Data Redis
                     |
              Lettuce Cluster
                     |
               Slot của key
                     |
         +-----------+-----------+
         |           |           |
         v           v           v
      Primary A   Primary B   Primary C
       slots ...   slots ...   slots ...
         |           |           |
      Replica A   Replica B   Replica C
```

Những lỗi thường bị chẩn đoán sai:

| Triệu chứng | Giả thuyết cần kiểm |
|---|---|
| `MOVED` | Slot owner thay đổi; client topology/redirect cần xử lý |
| `ASK` | Slot đang chuyển, redirect tạm thời trong quá trình migration |
| `CROSSSLOT` | Lệnh nhiều key không đáp ứng cùng-slot constraint |
| `CLUSTERDOWN` | Cluster không thể phục vụ theo trạng thái/slot coverage |
| Một số key timeout, key khác bình thường | Lỗi node/slot, hot slot hoặc routing |
| `SCAN` “thiếu key” | Lệnh chỉ scan node được hỏi, không phải toàn Cluster |
| TLS handshake chỉ lỗi với một vài key | Client được route sang node khác với certificate/address sai |
| App khởi động được nhưng GET fail sau redirect | Seed node tới được, advertised node không tới được |

### 13.1. Dùng CLUSTER KEYSLOT để đối chiếu key

Trên endpoint Cluster được cấp quyền:

```bash
redis-cli -c -h redis-cluster.internal -p 6379 \
  CLUSTER KEYSLOT 'cache:product:{42}:details'

redis-cli -c -h redis-cluster.internal -p 6379 \
  CLUSTER KEYSLOT 'cache:product:{42}:price'
```

Nếu hai key có cùng hash tag `{42}`, chúng cùng hash slot. Nếu tên key bị serializer thay đổi thành bytes khác, hãy bảo đảm giá trị CLI đang hỏi thực sự tương ứng với key vật lý của app.

### 13.2. Multi-key operations và CROSSSLOT

```text
cart:{user-42}:items
cart:{user-42}:total
```

Những key trên cùng slot, phù hợp hơn nếu cần Lua hoặc transaction multi-key tại một shard.

Ngược lại:

```text
cart:user-42:items
stock:sku-9:available
```

có thể ở các slot khác nhau. Redis có thể từ chối một command yêu cầu same-slot bằng `CROSSSLOT`.

Không sửa lỗi bằng cách dồn toàn bộ key của hệ thống vào hash tag `{global}`: làm vậy tạo **hot slot** và đánh mất lợi ích phân mảnh.

Một số high-level Spring Data Redis/driver operations có thể hỗ trợ xử lý nhiều node bằng các command tách biệt. Điều đó **không tạo transaction nguyên tử xuyên Cluster**; cần xác minh semantics của từng API.

### 13.3. MOVED và ASK không phải cùng ý nghĩa

- `MOVED` thường chỉ ra slot owner lâu dài đã chuyển.
- `ASK` thường xuất hiện trong quá trình slot migration và là chuyển hướng tạm.
- Cluster-aware client thường xử lý redirect theo khả năng và cấu hình.
- Nếu app tự dùng raw client không hỗ trợ Cluster, redirect có thể nổi lên như lỗi thường xuyên.
- Nếu địa chỉ được quảng bá là public/unreachable, redirect đúng về mặt Redis nhưng client vẫn timeout.

Kiểm tra thông số topology refresh và max redirects, nhưng không chỉ tăng max redirects để che sai network/Cluster state.

### 13.4. Một PONG không đại diện 16.384 slots

Redis Cluster có thể có node A đang hoạt động trong khi node B nắm một nhóm slot không sẵn sàng. Một `PING` tới A thành công không có nghĩa mọi key có thể đọc/ghi.

Các bằng chứng phù hợp hơn:

```bash
redis-cli -c -h redis-cluster.internal -p 6379 CLUSTER INFO

redis-cli -c -h redis-cluster.internal -p 6379 CLUSTER SLOTS

redis-cli -c -h redis-cluster.internal -p 6379 CLUSTER NODES
```

`CLUSTER SHARDS` cũng có thể có trên các phiên bản Redis hỗ trợ và cho cái nhìn cấu trúc theo shard. Các lệnh cần quyền phù hợp; ở managed service có thể phải dựa vào provider metrics thay vì raw Cluster commands.

## 14. SCAN trong Redis Cluster không tự quét toàn cụm

Một báo cáo “Redis chỉ còn 30% số key” đôi khi xuất phát từ việc chỉ quét **một primary**.

```text
redis-cli --scan --pattern 'cache:product:*'
         |
         v
Chỉ node Redis đang kết nối
         |
         v
Không chứng minh số key của mọi primary
```

Trong Redis Cluster, cần quét từng primary có trách nhiệm khi thực hiện inventory phân tán, hoặc dùng API cluster-aware tương ứng. Không dùng `KEYS *` trên production lớn vì có thể gây tải và latency không mong muốn.

Khi quét:

- Sử dụng `SCAN` theo lô, giới hạn thời gian/tốc độ.
- Biết node nào được quét và phạm vi slot.
- Chấp nhận rằng `SCAN` không cung cấp snapshot nguyên tử của keyspace đang thay đổi.
- Không suy luận “không tìm thấy trong một lần scan” là bằng chứng tuyệt đối key chưa từng tồn tại.
- Tránh log raw keys chứa session ID hoặc dữ liệu nhạy cảm.

## 15. Replica read: quan sát nào là authoritative?

Một client có thể ghi lên primary rồi đọc từ replica. Replication Redis thông thường là bất đồng bộ.

```text
T0: Primary nhận SET user:42:role ADMIN
T1: Primary trả OK
T2: Replica chưa replicate
T3: App B đọc replica và thấy role cũ
T4: Replica bắt kịp
```

Kết quả `GET` ở T3 có thể là một reply hợp lệ từ replica, **không phải bảo đảm dữ liệu mới nhất trên primary**.

Checklist:

- [ ] Lettuce read preference là gì: primary, replica preferred, replica only?
- [ ] Request gây lỗi đọc từ node role nào?
- [ ] Replication lag hiện tại và tại thời điểm sự cố?
- [ ] Có failover hoặc replica promotion gần thời điểm đó?
- [ ] Key đã được ghi rồi ngay lập tức đọc lại qua một client khác không?
- [ ] Có version trong dữ liệu để phát hiện stale?
- [ ] Nghiệp vụ có cho phép eventual consistency không?
- [ ] Session/permission/nonce/lock có bị đọc từ replica stale không?

Không bật replica reads cho một quyết định bảo mật chỉ để giảm primary QPS mà chưa có consistency policy. Khi chẩn đoán, hãy thử đường đọc primary có kiểm soát để tách replication lag khỏi lỗi serialization.

### 15.1. WAIT không phải bằng chứng durability tuyệt đối

Redis `WAIT` có thể được dùng để chờ một số replica xác nhận replication theo điều kiện nhất định, nhưng không biến một hệ thống bất đồng bộ thành giao dịch bền tuyệt đối qua mọi failover/persistence failure.

Nếu ứng dụng dùng `WAIT`, cần xem số replica thực tế đã đáp ứng và timeout, không chỉ xem command đã được gọi.

## 16. TTL, eviction, expiration và “dữ liệu tự biến mất”

Khi key biến mất sau một khoảng thời gian, checklist:

- [ ] `SET` ban đầu có kèm TTL không?
- [ ] Có `EXPIRE`/`PEXPIRE` sau đó không?
- [ ] Có ghi đè key bằng một command làm thay đổi TTL không?
- [ ] `TTL` từng trả `-1` (không expire) hay số dương?
- [ ] Có application `DEL`/`UNLINK`, `@CacheEvict`, invalidation event không?
- [ ] Redis `maxmemory-policy` có cho eviction khi memory đầy không?
- [ ] Eviction count có tăng cùng thời điểm không?
- [ ] Dữ liệu được đọc từ node/DB/namespace nào?
- [ ] Có failover làm mất write vừa được primary xác nhận chưa replicate không?
- [ ] Có migration/flush trên đúng namespace mà nhiều ứng dụng chia sẻ không?

Các lệnh quan sát:

```bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO persistence
redis-cli INFO replication
```

Trong Redis `INFO stats` thường có số liệu về expired/evicted keys. Tên trường và cách metric được provider hiển thị có thể khác theo version/deployment.

**Expiration và eviction là hai cơ chế khác nhau.** Key hết TTL là hành vi đã cấu hình; eviction có thể loại key trước TTL khi memory policy cho phép. Cần xác định cơ chế nào xảy ra, không gộp cả hai thành “Redis rớt dữ liệu”.

## 17. Error taxonomy: lỗi nào đáng retry?

| Error hoặc tín hiệu | Nhóm nguyên nhân | Hướng xử lý |
|---|---|---|
| Redis nil | Kết quả lệnh đọc hợp lệ theo semantics | Xử lý miss theo domain |
| `WRONGTYPE` | Key đang có kiểu không phù hợp | Kiểm tra namespace/schema, không retry mạng mù |
| `NOAUTH` / `WRONGPASS` | Thiếu/sai xác thực | Kiểm tra credential/ACL user |
| `NOPERM` | Không có quyền command/key/channel | Sửa least privilege có chủ đích |
| `READONLY` | Đang ghi vào replica hoặc routing sai | Kiểm tra node role và failover |
| `MOVED` / `ASK` | Cluster redirect hoặc migration | Kiểm tra cluster-aware client/topology |
| `CROSSSLOT` | Multi-key không cùng hash slot | Đổi thiết kế key/operation |
| `CLUSTERDOWN` | Cluster không phục vụ đầy đủ | Kiểm tra slot coverage/node health |
| `NOSCRIPT` | Script SHA không có ở node đang thực thi | Tải script lại hoặc dùng chiến lược EVAL phù hợp |
| `BUSYGROUP` | Consumer group đã tồn tại | Khởi tạo idempotent, không xóa group |
| OOM/maxmemory write rejection | Redis thiếu memory và policy chặn write | Capacity/eviction, không giả như miss |
| Connect timeout | Network, endpoint, node không đáp ứng | Kiểm tra DNS/firewall/latency |
| Command timeout | Server/network/client queue, command chậm | Đối chiếu client/server timing |
| Serialization error | Payload/serializer/schema không tương thích | Sửa data/schema, không đổi thành miss |
| Spring `Mono.empty()` từ GET | Missing value bình thường | `switchIfEmpty` cho miss |
| Spring `Mono.error()` | Thất bại của publisher | Phân loại lỗi, không mặc định 404 |

Lưu ý: exception cụ thể của Spring Data Redis có thể thay đổi theo driver, phiên bản và cách exception translation xử lý. Đừng viết logic production dựa vào việc parse nguyên văn một thông báo lỗi không ổn định; phân loại theo exception type, Redis response và operation context khi có thể.

### 17.1. Timeout của lệnh ghi có thể có outcome chưa biết

```text
Client gửi INCR counter
       |
       v
Redis tăng counter thành công
       |
       v
Response bị mất
       |
       v
Client nhận timeout
```

Trong trường hợp này, retry `INCR` có thể làm tăng hai lần. Không kết luận “chưa ghi” chỉ vì client nhận exception.

Cần phân biệt:

- **Retry GET:** thường an toàn về side effect, nhưng vẫn phải giới hạn backoff/deadline.
- **Retry SET cùng value/key:** có thể phù hợp trong một số trường hợp, nhưng ảnh hưởng TTL và race.
- **Retry INCR/XADD/Lua mutation:** cần idempotency hoặc đối soát để tránh tác dụng trùng.
- **Retry XACK:** ACK một pending ID theo group thường cho kết quả 1 lần đầu, 0 sau đó; số 0 không có nghĩa handler chưa chạy.

## 18. Pipeline, MULTI/EXEC và Lua script: xem đúng ranh giới

Một số lỗi được gán cho Redis nhưng nguyên nhân là giả định sai về atomicity.

### 18.1. Pipeline chỉ gom lệnh

Pipelining giúp giảm round-trip bằng cách gửi nhiều command mà không chờ reply từng lệnh. Nó **không tạo transaction** cho toàn batch.

Nếu giữa batch có lỗi, có thể một số lệnh đã chạy thành công. Với Spring Data Redis, cần lấy kết quả sau khi `executePipelined` hoàn tất.

### 18.2. MULTI/EXEC không bao giao dịch database

Redis `MULTI/EXEC` thực thi một chuỗi lệnh theo semantics transaction của Redis; nó không tạo một transaction phân tán giữa Redis và PostgreSQL/MySQL hoặc external API.

Ngoài ra, runtime error trong một command của `EXEC` không nhất thiết rollback các command Redis khác đã thực thi. Cần hiểu command-specific failure.

### 18.3. Lua script không rollback write đã chạy trước lỗi runtime

Một Lua script có thể thực hiện một số write rồi gặp runtime error. Redis không tự khôi phục mọi write đã thực hiện trước đó như database transaction có rollback.

Đừng chẩn đoán “Lua error nên chắc Redis không thay đổi gì” nếu script có side effect trước điểm lỗi. Với Cluster, script thao tác nhiều key còn phải tuân thủ slot constraint.

### 18.4. Đối chiếu đúng command thật sự đã chạy

Một high-level API có thể phát nhiều lệnh:

- Spring Cache `put`/`evict`.
- Spring Session write + TTL/index management.
- Redis Streams consumer group startup.
- RedisTemplate execute callback.
- Lua script invocation qua script executor.

Không suy luận từ **tên method Java** rằng Redis chỉ nhận một command. Khi cần, dùng command metrics, tracing hoặc môi trường test để quan sát lệnh thực, tránh bật `MONITOR` kéo dài trên production.

## 19. Redis Streams: group offset, pending và ACK

Với Redis Streams, “message không tới consumer” có thể do:

1. Consumer group được tạo từ `$` nên bỏ qua lịch sử trước thời điểm tạo.
2. Message đã được giao cho consumer A và đang pending, không còn là message mới cho consumer B dùng `>`.
3. Handler lỗi và không ACK.
4. Pending thuộc consumer đã chết nhưng chưa được claim.
5. Entry bị trim/xóa nên payload không còn để recovery.
6. Consumer chỉ dùng `ReadOffset.latest()` và bỏ lỡ message giữa những lần poll trong một số mô hình.
7. Redis ACL/network/Cluster khiến consumer không thể đọc.
8. Listener container không thực sự đang chạy hoặc subscriber đã bị cancel.

### 19.1. Ba nhóm bằng chứng khác nhau

| Lệnh | Điều cần xem | Không được suy ra |
|---|---|---|
| `XINFO STREAM` | Độ dài stream, ID đầu/cuối | Số event xử lý thành công |
| `XINFO GROUPS` | Last-delivered, consumers, pending, lag khi khả dụng | Lag 0 nghĩa pending 0 |
| `XPENDING` | Entry đã giao chưa ACK, owner, idle, delivery count | Business transaction đã commit hay chưa |
| `XRANGE` | Payload còn lưu trong stream | Entry đang pending với group nào |
| `XINFO CONSUMERS` | Pending per consumer, idle | Consumer process chắc còn khỏe |

Ví dụ read-only:

```bash
redis-cli XINFO STREAM stream:orders:v1

redis-cli XINFO GROUPS stream:orders:v1

redis-cli XPENDING stream:orders:v1 order-workers

redis-cli XPENDING stream:orders:v1 order-workers - + 20

redis-cli XINFO CONSUMERS stream:orders:v1 order-workers
```

Không nên chạy lệnh `XGROUP DESTROY`/`XGROUP SETID` trên production chỉ để “giải quyết lag” khi chưa rõ PEL, offset và yêu cầu replay.

### 19.2. XREADGROUP > không lấy lại pending của consumer khác

```text
XREADGROUP GROUP order-workers worker-a STREAMS stream:orders:v1 >
    -> worker-a nhận e1, PEL chứa e1

worker-a crash trước XACK

XREADGROUP GROUP order-workers worker-b STREAMS stream:orders:v1 >
    -> không tự lấy lại e1 đang pending ở worker-a
```

Recovery cần `XCLAIM` hoặc `XAUTOCLAIM` theo idle threshold và policy phù hợp. Nếu worker A restart cùng consumer name, nó có thể đọc pending của chính nó theo offset pending tương ứng.

**Không coi claim là ACK**. Claim đổi owner của pending; chỉ sau business success mới gọi `XACK`.

### 19.3. Retention có thể làm mất payload đang pending

Stream entry có thể bị `XTRIM` hoặc `XDEL` dù group có pending. PEL không phải một kho payload độc lập có thể tái tạo nội dung đã xóa.

Khi chẩn đoán “pending còn nhưng không xử lý được”, kiểm tra stream retention/trim policy, entry ID và payload có còn hay không. Nếu event bắt buộc không được mất, thiết kế retention theo nhóm consumer chậm nhất, không theo nhóm nhanh nhất.

### 19.4. XACK không đồng nghĩa xóa message

`XACK` loại message khỏi PEL của **một group**; nó không mặc định `XDEL` entry trong stream. Một message vẫn có thể cần được group khác đọc. Không dùng `XLEN` để suy ra số entry chưa xử lý.

## 20. Redis Pub/Sub: không có pending hoặc replay bền

Redis Pub/Sub không hoạt động như Redis Streams:

```text
Publisher -- PUBLISH --> Channel
                             |
                      Subscribers online
                             |
                        Nhận message
```

Nếu subscriber offline lúc publish, thông điệp đó có thể mất đối với subscriber. Không có PEL/ACK để claim lại như Streams consumer group.

Checklist cho Pub/Sub:

- [ ] Subscriber đang kết nối **trước** lúc publish?
- [ ] Đúng channel hoặc pattern?
- [ ] Redis ACL có quyền subscribe channel đó?
- [ ] Có dùng Cluster sharded Pub/Sub hay Pub/Sub thông thường?
- [ ] Listener container đã startup và không bị stop/cancel?
- [ ] Publisher/consumer có trỏ cùng Redis deployment và channel?
- [ ] Có proxy/network path làm mất kết nối dài hạn?
- [ ] Ứng dụng có yêu cầu replay nhưng lại dùng Pub/Sub không?

`PUBLISH` có thể trả số subscription nhận được ở thời điểm phát, nhưng không phải ACK xác nhận business handler đã xử lý thành công. Không chuyển một kịch bản mất notification Pub/Sub thành cáo buộc Redis Streams bị mất message.

## 21. Reactor/WebFlux: Mono.empty khác Mono.error

Trong Spring Data Redis Reactive:

```java
Mono<String> value =
        reactiveStringRedisTemplate.opsForValue().get(key);
```

Với `GET` thông thường:

- Value tồn tại → `onNext(value)` rồi `onComplete`.
- Key không tồn tại → `onComplete` mà không có `onNext`, tức `Mono.empty()`.
- Redis lỗi → `onError(exception)`.

Mẫu đúng khi muốn phân biệt:

```java
return reactiveStringRedisTemplate.opsForValue()
        .get(key)
        .switchIfEmpty(Mono.error(
                new CacheKeyMissingException(key)));
```

`CacheKeyMissingException` là một exception ứng dụng giả định để diễn đạt key thiếu. Nó **không** tự bắt lỗi kết nối Redis.

Mẫu che lỗi:

```java
return reactiveStringRedisTemplate.opsForValue()
        .get(key)
        .onErrorResume(error -> Mono.empty())
        .switchIfEmpty(Mono.error(
                new CacheKeyMissingException(key)));
```

Ở đây lỗi Redis bị đổi thành kết quả empty rồi bị tuyên bố key thiếu. Đây là một lỗi ở reactive composition, không phải bằng chứng Redis đã xóa key.

### 21.1. subscribe() và block() làm thay đổi hành vi quan sát

- `subscribe()` trong controller tạo side effect bất đồng bộ không gắn đúng response lifecycle; HTTP có thể trả thành công trước khi Redis write xong.
- `block()` trong WebFlux request handler có thể chặn event loop.
- `flatMap` có concurrency cao có thể khiến nhiều lệnh hoàn thành khác thứ tự.
- `retryWhen` không giới hạn có thể gây bão request tới Redis.
- Cancellation không chứng minh Redis command chưa được server thực thi.

Khi một issue chỉ xảy ra ở WebFlux mà không xảy ra trong `StringRedisTemplate` test đồng bộ, cần so sánh **client configuration, connection factory, scheduler, operator chain và error handling** trước khi quy về Redis.

## 22. Redis Session và khóa xác thực

Khi Redis lưu session, token marker hoặc revocation state, lỗi của repository có thể xuất hiện như “người dùng bị logout” hoặc “quyền không cập nhật”.

Checklist:

- Session namespace có nhất quán giữa các app instances?
- Spring Session serializer có tương thích sau rolling deploy?
- Cookie name/domain/path/secure/same-site có đúng browser flow?
- Session ID được gửi lên server hay browser đã không gửi cookie?
- Redis TTL/expiry của session có theo chính sách?
- Có đọc từ replica stale sau logout/revoke?
- Có ACL error khi Spring Session cập nhật index hoặc expiration metadata?
- Spring Security `SecurityContext` có được lưu/khôi phục theo cấu hình?
- Redis outage có bị chuyển thành “session absent” thay vì error không?

Không chỉnh trực tiếp những key nội bộ của Spring Session để “sửa timeout” nếu chưa hiểu repository contract. Session key layout, index và expiration mechanics có thể khác theo phiên bản Spring Session.

Đối với endpoint cần bảo mật, khi không kiểm tra được session, phải có chính sách fail-closed hoặc xác thực dự phòng đã được thiết kế; **Redis unavailable không phải lý do cho phép truy cập**.

## 23. Quan sát hiệu năng: chậm ở client hay server?

Khi thấy Spring Redis command timeout, cần tách thời gian:

```text
HTTP request enters application
       |
       +--> Chờ thread / reactive scheduling
       |
       +--> Chờ connection/pool
       |
       +--> DNS/TCP/TLS
       |
       +--> Network RTT
       |
       +--> Redis command execution
       |
       +--> Network response
       |
       +--> Deserialize / map
       |
       +--> Other business processing
       |
       v
HTTP response
```

`SLOWLOG` chủ yếu ghi nhận những command có thời gian thực thi server vượt ngưỡng; nó không bao trùm toàn bộ thời gian chờ connection, network hoặc xử lý ứng dụng.

Checklist:

- [ ] HTTP p50/p95/p99 và Redis command p50/p95/p99 cùng tăng?
- [ ] `SLOWLOG` có command liên quan ở thời điểm lỗi không?
- [ ] Redis CPU và event loop latency tăng không?
- [ ] Có big key hoặc script Lua dài?
- [ ] Network RTT/loss/connection resets tăng không?
- [ ] Lettuce pool hoặc Netty threads bị nghẽn?
- [ ] Có Java GC pause dài hoặc blocking trên WebFlux event loop?
- [ ] Redis Cluster node nào có CPU/latency cao?
- [ ] Có hot key hoặc slot skew?
- [ ] Redis đang persistence fork/replication catch-up/failover?
- [ ] Retry làm tổng lệnh/s tăng nhanh hơn request/s không?

### 23.1. Lệnh quan sát hợp lý

```bash
redis-cli INFO clients
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli INFO replication
redis-cli SLOWLOG GET 10
```

Các lệnh yêu cầu quyền phù hợp; provider managed Redis có thể giới hạn. Không bật `MONITOR` liên tục trên production lớn nếu chưa đánh giá chi phí và nguy cơ log payload nhạy cảm.

### 23.2. Pool exhaustion khác Redis CPU overload

Nếu Redis CPU thấp nhưng app liên tục chờ connection, vấn đề có thể ở connection pool hoặc cách ứng dụng giữ connection, không phải Redis xử lý lệnh chậm.

Ngược lại, nếu Redis CPU cao và có nhiều command chậm, tăng pool Java có thể làm Redis càng bão hòa. Cần đo cả hai phía trước khi thay pool size.

## 24. Các bước đọc an toàn bằng redis-cli

Không dùng CLI như một công cụ “sửa dữ liệu nhanh” trước khi có root cause. Trên môi trường được cấp quyền, một phiên điều tra **read-only** có thể theo mẫu:

### Bước 1: xác định endpoint và role

```bash
redis-cli -h redis.internal -p 6379 PING
redis-cli -h redis.internal -p 6379 INFO replication
```

Nếu endpoint dùng TLS, cần thêm `--tls` và cấu hình CA/ACL an toàn. Nếu endpoint là Sentinel, phải dùng đúng cổng Sentinel để hỏi discovery; nếu Cluster, xem thêm slot/topology.

### Bước 2: hỏi một key cụ thể

```bash
redis-cli -h redis.internal -p 6379 \
  TYPE 'cache:catalog:v3:p-42'

redis-cli -h redis.internal -p 6379 \
  EXISTS 'cache:catalog:v3:p-42'

redis-cli -h redis.internal -p 6379 \
  TTL 'cache:catalog:v3:p-42'
```

Nếu type là `string` và dữ liệu không nhạy cảm, mới cân nhắc `GET`. Không dump session/JWT/customer payload chỉ để chứng minh key tồn tại.

### Bước 3: đối chiếu cùng key từ app

Ghi nhận:

```text
Application instance: catalog-pod-a
Redis template: StringRedisTemplate
Factory: catalogRedisConnectionFactory
Endpoint: redis.internal
DB/index: 0 (nếu mode cho phép)
Key prefix: cache:catalog:v3:
Serializer: StringRedisSerializer
Command: GET
Result: null
```

Nếu CLI thấy key có nhưng app GET nil, kiểm tra namespace, database, serializer, node role, TLS proxy và client factory.

### Bước 4: kiểm tra thời điểm và topology

Nếu lỗi chỉ thỉnh thoảng xảy ra, đối chiếu:

- Timeline failover/reshard.
- Redis eviction/expiration metrics.
- Ghi log request ID và command type đã ẩn key nhạy cảm.
- Replication lag/read preference.
- Application deployments và cache version changes.

Đọc tại hai thời điểm khác nhau không đảm bảo cùng trạng thái dữ liệu. Điều tra cần giữ timestamp của từng quan sát.

## 25. Ví dụ Spring Data Redis diagnostic helper

Một helper read-only có thể giúp đối chiếu key tồn tại, type và TTL khi chạy **trên môi trường test hoặc bằng công cụ vận hành được cấp quyền**.

```java
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisKeyInspector {

    private final StringRedisTemplate redis;

    public RedisKeyInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public KeySnapshot inspect(String key) {
        Boolean exists = redis.hasKey(key);
        DataType type = redis.type(key);
        Long ttlSeconds =
                redis.getExpire(key, TimeUnit.SECONDS);

        return new KeySnapshot(
                Boolean.TRUE.equals(exists),
                type == null ? "unknown" : type.code(),
                ttlSeconds);
    }

    public record KeySnapshot(
            boolean observedExisting,
            String observedType,
            Long observedTtlSeconds) {
    }
}
```

**Giới hạn quan trọng của ví dụ:**

- `hasKey`, `type` và `getExpire` là **ba lệnh khác nhau**; key có thể đổi giữa chúng.
- Snapshot này không nguyên tử và không dùng làm kiểm tra–sau đó–ghi.
- Nếu Redis access error, để exception đi theo đường lỗi; đừng đổi thành `observedExisting=false`.
- Không nên công bố một HTTP endpoint nhận raw Redis key tùy ý và trả snapshot cho người dùng cuối.
- `StringRedisTemplate` phải sử dụng cùng factory/key serializer với component đang cần chẩn đoán nếu muốn so sánh chính xác.

### 25.1. Ghi log có cấu trúc thay vì dump value

Ví dụ log khuyến nghị:

```text
event=redis_lookup
operation=GET
cacheName=catalog
namespaceVersion=v3
result=MISS
redisMode=cluster
nodeRole=primary
durationMs=4
requestId=...
```

Khi lỗi:

```text
event=redis_lookup
operation=GET
result=ERROR
errorCategory=TIMEOUT
durationMs=2000
requestId=...
```

Không gộp `ERROR` vào `MISS`, và không dùng raw key/session ID làm metric label có cardinality cao.

## 26. Case study A: API trả 404 dù database có sản phẩm

### Triệu chứng

```text
GET /products/p-42 -> 404
DB có p-42
Redis GET -> null
```

### Không nên kết luận ngay

“Redis bị mất dữ liệu” chưa được chứng minh. Các khả năng:

- Redis là cache, cache miss vốn bình thường.
- API mapping xử lý miss sai, không hỏi database.
- Key prefix đổi sau deploy.
- Writer và reader dùng serializer khác.
- API đọc cache ở Redis deployment/DB khác.
- Key TTL hết hạn hoặc bị evict.
- Query được gửi tới replica đang lag.
- Cached-null/negative-cache ở Spring Cache/L1.

### Checklist phân biệt

1. Đọc flow cache-aside: miss có dẫn tới database không?
2. So sánh cache name/key prefix trước và sau deploy.
3. Xác định connection factory/template của writer và reader.
4. Xem `TYPE`/`TTL`/`EXISTS` một key an toàn ở endpoint được dùng.
5. So sánh read preference và node role.
6. Kiểm tra L1 local cache hoặc negative cache.
7. Nếu Redis trả nil hợp lệ, phân loại là **MISS**; lỗi HTTP 404 có thể nằm ở business service.

**Kết luận phù hợp có thể là**: “Service đổi key prefix v2→v3, Redis miss bình thường nhưng controller trả 404 thay vì hỏi DB”; không phải “Redis làm mất bản ghi”.

## 27. Case study B: PING thành công nhưng SET luôn lỗi

### Triệu chứng

```text
PING -> PONG
SET cache:catalog:v3:p-42 ... -> NOPERM
```

### Đối chiếu

- Kết nối và basic command đã hoạt động.
- ACL có thể cho `PING` nhưng không cho `SET`, hoặc key pattern không khớp.
- Spring Boot có thể đang dùng user read-only thay vì writer user.
- ACL vừa được rotate hoặc namespace vừa đổi.
- Một service khác có user writer và vẫn ghi bình thường.

### Hành động phù hợp

Kiểm tra policy ACL, application role, key pattern và command set. Không mở tất cả quyền `+@all ~*` chỉ để lệnh chạy. Không coi lỗi SET là cache miss.

Một biến thể khác là `READONLY`: khi đó phải kiểm tra node role/routing/failover chứ không sửa ACL.

## 28. Case study C: Redis Cluster chỉ lỗi một phần key

### Triệu chứng

```text
GET product:1 -> thành công
GET product:2 -> timeout
GET product:3 -> MOVED
GET product:4 -> thành công
```

### Giả thuyết

Các key có slot khác nhau, được gửi tới những primary khác nhau. Một node có thể:

- Không truy cập được từ pod.
- Đang failover/reshard.
- Quảng bá hostname sai.
- Có TLS certificate không khớp.
- Bị quá tải/hot key.
- Nằm trong slot map cũ của client.

### Checklist

1. `CLUSTER KEYSLOT` cho các key mẫu.
2. `CLUSTER INFO` và slot coverage.
3. Slot→primary mapping và Redis node addresses.
4. Client topology refresh/reconnect logs.
5. Network từ application pod tới **từng node được quảng bá**.
6. Command latency theo node.
7. Redis driver/Cluster-aware mode đang cấu hình.
8. Có dùng multi-key script cross-slot không?

Không kết luận “Redis lúc được lúc không” như một mô tả root cause; cần chỉ ra shard/slot hoặc giai đoạn thay đổi topology liên quan.

## 29. Case study D: Consumer vẫn chạy nhưng event không được xử lý

### Triệu chứng

```text
XINFO GROUPS:
    lag = 0
    pending = 500

Application:
    Không thấy event mới
    business projection chậm
```

### Giải thích có thể đúng

Group đã phân phối mọi event mới nhưng 500 entry vẫn đang pending chưa ACK. Nếu worker chỉ gọi `XREADGROUP ... >`, nó sẽ không lấy lại pending của consumer đã chết.

### Checklist

- `XPENDING` tổng và chi tiết theo owner/idle time.
- `XINFO CONSUMERS`.
- Có worker crash giữa commit và ACK không?
- Có recovery bằng `XCLAIM`/`XAUTOCLAIM` không?
- Payload của pending ID còn trong stream không?
- Handler có poison message hoặc idempotency failure không?
- ACK đã được gọi sau commit hay trước?
- Retention có trim entry khi còn pending không?

Nếu PEL chứa entry thuộc worker đã chết, hướng khắc phục là pending recovery có kiểm soát, không xóa group để “reset lag”.

## 30. Case study E: “SET thành công nhưng sau failover bị mất”

### Triệu chứng

Ứng dụng ghi dữ liệu rồi một thời gian ngắn sau failover không đọc thấy key.

### Các giả thuyết cần kiểm

- Redis replication bất đồng bộ chưa chuyển write tới replica được promote.
- App đọc nhầm replica hoặc endpoint cũ.
- Redis maxmemory eviction hoặc TTL.
- Persistence settings và quy trình failover.
- Có write timeout nhưng ứng dụng đã log “thành công” sai?
- Hai node không cùng deployment/namespace?
- Có listener/job xóa key sau write?

### Cách ghi kết luận

Trước khi kết luận mất write do replication, cần đối chiếu thời điểm primary xác nhận `SET`, replication offset/lag khi sự cố, node được promote, ứng dụng đọc node nào và các thao tác xóa/expiry. Trong một số hạ tầng, dữ liệu đã được xác nhận ở primary có thể không còn sau failover; nhưng một triệu chứng đơn lẻ không chứng minh đó là nguyên nhân.

Không thử tái tạo bằng cách failover production tùy tiện. Dùng môi trường test có topology tương ứng và kịch bản được duyệt.

## 31. Case study F: Redis chậm sau khi bật reactive

### Triệu chứng

Ứng dụng chuyển sang WebFlux + `ReactiveRedisTemplate` nhưng p99 HTTP tăng, có timeout Redis.

### Checklist

- Có `block()` trên Reactor Netty event loop không?
- Có dùng `StringRedisTemplate` synchronous trong handler reactive không?
- Có `flatMap` concurrency vô hạn không?
- Có `collectList()` trên Flux lớn không?
- Redis command thực có chậm trên server hay chỉ chờ client/network?
- Connection factory có cùng endpoint/TLS/timeouts với trước?
- Serializer mới có encode payload lớn không?
- Có nhiều `subscribe()` tự tạo gây uncontrolled parallelism?
- Có retry không giới hạn khi Redis lỗi?
- CPU/GC/Netty event-loop delay của app có tăng không?

**Reactive không tự giảm chi phí Redis server**. Nếu ứng dụng gửi nhiều lệnh cùng lúc hơn khả năng Redis xử lý, hệ thống có thể chậm hơn dù không block request threads.

## 32. Bảng quyết định nhanh theo triệu chứng

| Triệu chứng chính | Kiểm tra đầu tiên | Chưa nên làm |
|---|---|---|
| Không kết nối Redis | Host, DNS, port, firewall, TLS | Mở cổng công khai |
| PING OK, GET NOPERM | ACL user, key pattern, command | Tăng quyền toàn bộ |
| GET nil | Endpoint, DB, prefix, serializer, TTL, node role | Khẳng định Redis lỗi |
| WRONGTYPE | `TYPE`, writer/reader, namespace | Retry liên tục |
| Dữ liệu chỉ sai sau deploy | Profile, schema, serializer, cache version | FLUSHALL |
| Đọc stale trên một số pod | L1, replica read preference, invalidation | Chỉ tăng TTL |
| READONLY | Primary/replica role, failover routing | Đổi password |
| CROSSSLOT | Hash tags và key slot | Gom mọi key vào một slot |
| MOVED/ASK | Cluster topology, redirect reachability | Hardcode một primary |
| Chỉ một vài key timeout | Node/slot/hot key/Cluster mapping | Restart tất cả Redis |
| SET timeout | Redis outcome chưa chắc chắn | Retry mutation vô điều kiện |
| TTL = -2 | Expiry, DEL, eviction, key/endpoint | Kết luận mất dữ liệu do crash |
| Stream lag 0 nhưng pending cao | XPENDING, worker owner, recovery | Xóa group |
| Pub/Sub bỏ lỡ message | Subscriber online, network, Pub/Sub semantics | Kỳ vọng replay tự động |
| HTTP 404 khi Redis outage | Exception→null/empty mapping | Gán 404 cho mọi Redis failure |
| Actuator Redis UP, API Redis lỗi | ACL/command/serializer/slot/business flow | Tin PING đủ chứng minh mọi thứ |

## 33. Mẫu báo cáo kết luận kỹ thuật

Sau khi có đủ bằng chứng, một báo cáo sự cố nên có cấu trúc:

```text
1. Triệu chứng
   - User-visible impact
   - Thời điểm bắt đầu/kết thúc
   - Tỷ lệ request ảnh hưởng

2. Phạm vi
   - App versions, pods, profiles
   - Redis mode, nodes/slots/region
   - Command, key namespace, tenant scope

3. Bằng chứng
   - App logs/traces theo request ID
   - Redis CLI/INFO metrics có timestamp
   - Topology / ACL / DNS / TLS configuration
   - Dữ liệu thực tế ở nguồn authoritative

4. Giả thuyết đã loại
   - Vì sao không phải TTL/serializer/ACL/replica/...
   - Bằng chứng cụ thể để loại

5. Root cause được hỗ trợ
   - Sự kiện và thay đổi cấu hình/code gây lỗi
   - Cơ chế kỹ thuật từ nguyên nhân đến triệu chứng

6. Khắc phục
   - Biện pháp khôi phục
   - Kết quả sau thay đổi
   - Rủi ro còn lại

7. Phòng ngừa
   - Test, metric, alert, rollout, documentation
```

### 33.1. Không bỏ qua điều chưa chắc chắn

Nếu chỉ có bằng chứng “Redis GET trả nil tại 10:05” nhưng không có logs hoặc TTL timeline, báo cáo đúng có thể là:

> “Key không tồn tại ở thời điểm 10:05 trên node được kiểm tra; chưa xác định nó hết TTL, bị xóa hay chưa từng được ghi.”

Đây là một kết luận có trách nhiệm hơn việc đoán chắc Redis đã mất dữ liệu.

### 33.2. Phân biệt workaround và root cause fix

Ví dụ tăng Redis timeout từ 2 giây lên 10 giây có thể giảm lỗi tạm thời nhưng không sửa hot key, network congestion hoặc long-running Lua script.

Hãy ghi:

- **Mitigation:** giảm tác động ngay.
- **Root cause:** cơ chế tạo sự cố.
- **Fix:** thay đổi ngăn lỗi tái diễn.
- **Verification:** bằng chứng sau fix và kịch bản regression test.

## 34. Checklist trước khi tuyên bố sự cố được xử lý

- [ ] Đã xác định đúng endpoint, profile, factory, serializer và namespace.
- [ ] Kết quả từng Redis command được diễn giải theo contract, không dựa vào phỏng đoán.
- [ ] Đã phân biệt nil/empty/false với exception và payload invalid.
- [ ] Đã đối chiếu primary/replica read preference và lag nếu có replication.
- [ ] Đã kiểm tra Cluster slot/node reachability khi lỗi phụ thuộc key.
- [ ] Đã kiểm tra Sentinel discovery/primary role khi lỗi phụ thuộc failover.
- [ ] Đã xem TTL/eviction/DEL và timeline nếu key biến mất.
- [ ] Đã xem PEL/ACK/claim nếu lỗi liên quan Streams.
- [ ] Đã xem Pub/Sub subscription/replay semantics nếu notification mất.
- [ ] Đã xem Spring Cache/L1/negative cache nếu HTTP khác Redis CLI.
- [ ] Đã xác nhận retry mutation không gây tác dụng trùng.
- [ ] Đã kiểm tra lỗi Redis không bị đổi thành HTTP 404 giả hoặc bypass bảo mật.
- [ ] Đã có kết quả thử lại với workload/cấu hình liên quan.
- [ ] Đã ghi lại phạm vi hệ thống còn chưa chắc chắn.
- [ ] Đã có test/metric/alert giúp phát hiện lại cùng lớp lỗi.

Checklist này là công cụ điều tra **sau khi có sự cố**, không phải lý do để chạy các command thay đổi dữ liệu ngay trong production.

## 35. Quy trình điều tra từ biểu hiện tới nguyên nhân

```text
              Có triệu chứng Redis/Spring
                         |
                         v
              Ghi timestamp + phạm vi
                         |
                         v
              Redis là cache, session,
              queue, lock hay nguồn chính?
                         |
                         v
              Lệnh nào + endpoint nào?
                         |
                +--------+---------+
                |                  |
            Exception         Kết quả có reply
                |                  |
                v                  v
         Network / TLS / ACL   Hiểu đúng contract
         driver / timeout      GET/HGET/TTL/Streams
                |                  |
                v                  v
         Đối chiếu factory     Nil hay value?
         và actual topology     |          |
                |              Nil       Value
                |               |          |
                v               v          v
         Sentinel/Cluster   Prefix/TTL   Type/schema/
         role/slot/route    replica/L1   deserialize
                |               |          |
                +---------------+----------+
                                |
                                v
                       Tách Redis result
                       khỏi business result
                                |
                                v
                     Kiểm tra timeline
                     deploy/failover/evict
                                |
                                v
                     Root cause có bằng chứng?
                         /           \
                       Có            Chưa
                        |              |
                        v              v
                  Mitigate/fix     Giữ giả thuyết,
                  test lại        thu thêm evidence
                        |              |
                        +------+-------+
                               |
                               v
                     Báo cáo và phòng ngừa
```

## 36. Những sai lầm chẩn đoán dễ tái diễn

| Sai lầm | Hậu quả | Cách làm tốt hơn |
|---|---|---|
| Chỉ dựa vào một ảnh chụp `PING` | Bỏ sót ACL, slot, payload hoặc worker lỗi | Đối chiếu command và topology thật |
| Đọc application.yml nhưng không xem profile runtime | Nhầm endpoint hoặc database | Xác minh effective config đã mask secret |
| Chỉ hỏi CLI từ laptop | Không phản ánh network của app pod | Kiểm tra từ cùng source/network boundary |
| GET nil bị gộp với timeout | Trả 404 sai, che Redis outage | Phân loại MISS và ERROR |
| MGET nil được coi chắc chắn là key thiếu | Bỏ qua key sai type | Hiểu ngữ nghĩa MGET |
| Null trong pipeline bị coi là miss | Xử lý khi chưa có reply | Đọc kết quả sau pipeline |
| Chỉ kiểm tra logical key Java | Bỏ qua serializer/prefix | Đối chiếu physical key bytes |
| Đổi serializer nóng trên production | Session/cache cũ không đọc được | Migration và schema compatibility |
| Dùng `KEYS *` để inventory Cluster | Tạo tải, vẫn có thể thiếu node | Bounded SCAN theo từng primary |
| Restart Redis khi thấy MOVED | Che lỗi topology, gây gián đoạn | Kiểm tra Cluster routing/redirect |
| Tăng retry mọi lỗi | Bão tải, mutation trùng | Classify transient, backoff/idempotency |
| Coi replica stale là primary mất key | Root cause sai | So sánh read preference và replication lag |
| Coi lag group 0 là đã xử lý xong | Bỏ quên pending | Xem XPENDING và ACK |
| Xóa consumer group để “giải quyết” pending | Mất tiến độ/recovery | Claim và xử lý idempotent |
| Tin Pub/Sub replay message khi reconnect | Mất event không được phát hiện | Streams/event store cho yêu cầu bền |
| Coi Spring Cache null là Redis nil | Nhầm cached-null và missing entry | Kiểm tra ValueWrapper/provider |
| Bật MONITOR dài hạn | Gây tải và rủi ro lộ payload | Metrics/tracing được kiểm soát |
| Sửa ACL bằng `+@all ~*` | Mở rộng ảnh hưởng khi credential lộ | Least privilege theo lệnh/key |
| Mở Redis public để kiểm tra mạng | Tăng bề mặt tấn công | Private route và firewall allowlist |
| Khẳng định root cause khi chưa có timeline | Fix sai, lỗi quay lại | Ghi rõ bằng chứng và phần chưa chắc chắn |

## 37. Tổng kết

Khi chẩn đoán sự cố **Spring Data Redis**, điểm khó thường không nằm ở việc nhớ thêm một lệnh Redis, mà ở **việc đối chiếu đúng những lớp độc lập**:

1. **Cấu hình thật:** Spring profiles, environment overrides, connection factory, serializer, namespace và cache manager.
2. **Kết nối:** DNS, network, TLS, ACL, client timeouts và quyền command.
3. **Ngữ nghĩa lệnh:** GET nil khác exception; TTL -2 khác -1; MGET/HGET/pipeline có contract riêng.
4. **Dữ liệu:** physical key bytes, type, TTL, eviction, JSON/schema và nguồn authoritative.
5. **Topology:** Standalone, Sentinel, Cluster slots, redirects, primary/replica và replication lag.
6. **Mô hình tiêu thụ:** Streams group/PEL/ACK khác Pub/Sub không replay; group lag không phải số message đã commit.
7. **Ranh giới nghiệp vụ:** Redis có thể chỉ là cache; kết quả cache miss chưa quyết định HTTP 404 nếu database là nguồn sự thật.
8. **Lỗi và retry:** timeout sau mutation có thể có outcome chưa biết; phải dùng idempotency và đối soát khi cần.
9. **Quan sát:** timestamp, tracing, metric theo command/node, deploy và failover history quan trọng hơn một lần PING đơn lẻ.
10. **An toàn:** không flush, reset group, mở public port hoặc lộ secret chỉ để tìm lỗi nhanh.

**Quy tắc cốt lõi:** Trước khi kết luận “Redis lỗi”, hãy chỉ ra **ứng dụng đã thực sự dùng cấu hình nào, gửi lệnh gì, tới node/slot nào, nhận reply hay exception gì, và kết quả ấy có đúng theo contract của Redis và Spring Data Redis hay không**. Khi các lớp đó được xác nhận bằng bằng chứng, root cause mới có thể được phân định và khắc phục mà không tạo thêm rủi ro cho hệ thống.

