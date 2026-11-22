# Kết nối Redis an toàn từ ứng dụng Java

Một API Java dùng Azure SQL Database làm nguồn dữ liệu có thể phải đọc cùng một danh mục sản phẩm hàng nghìn lần mỗi phút. Redis giúp lưu bản sao dữ liệu tạm thời để giảm độ trễ và số lần truy vấn database. Nhưng nếu kết nối Redis không mã hóa, cấu hình xác thực sai, rò rỉ mật khẩu, dùng cache key không phân biệt tenant hoặc retry không giới hạn khi Redis lỗi, một giải pháp nhằm tăng tốc có thể trở thành điểm yếu bảo mật và nguồn gây sự cố dây chuyền.

**Kết nối Redis an toàn từ ứng dụng Java** bao gồm nhiều lớp: chọn đúng dịch vụ Redis trên Azure; xác định endpoint và cổng TLS; xác minh chứng chỉ server; chọn Microsoft Entra ID hoặc credentials theo khả năng dịch vụ; bảo vệ secret; cấu hình mạng riêng; quản lý vòng đời Lettuce/Spring Redis client; giới hạn timeout, retry, concurrency; và bảo đảm dữ liệu cache không làm sai nghiệp vụ.

Bài học thuộc chương **Cache và giao tiếp thời gian thực** của mô-đun **CLOUD_PROVIDERS_AZURE**. Trong lộ trình Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu, kỹ năng này gắn liền với triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng.

> **Lưu ý:** Azure hiện có **Azure Managed Redis** và những triển khai **Azure Cache for Redis** kế thừa. Sản phẩm, tier, hostname, cổng TLS, Redis protocol mode và xác thực có thể khác nhau. Azure Cache for Redis có lộ trình chuyển đổi/ngừng hỗ trợ theo SKU; khi xây dựng hệ thống mới cần kiểm tra tài liệu và thông báo hiện hành. Không hard-code một cấu hình kết nối chung cho mọi dịch vụ Redis của Azure.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt Redis cache với nguồn dữ liệu chính và với cache trong JVM.
2. Xác định đúng Redis endpoint, TLS port, authentication mode và topology.
3. Sử dụng **TLS và certificate/hostname verification** trong Java Lettuce.
4. Hiểu Microsoft Entra ID/managed identity, Redis ACL/password và quản lý access keys.
5. Viết code Lettuce đọc/ghi key có TTL trong một môi trường lab an toàn.
6. Cấu hình Spring Boot và Spring Data Redis, quản lý Redis client dài hạn.
7. Thiết kế **cache-aside**, TTL, cache key đa tenant và invalidation.
8. Cấu hình timeout, retry, backoff, pooling và fallback để Redis outage không kéo sập database.
9. Chẩn đoán DNS, Private Endpoint, TLS, AUTH, cluster routing và capacity.
10. Thiết kế logging, metrics, kiểm thử và checklist production cho Java workloads trên Azure.

## 1. Redis đứng ở đâu trong kiến trúc?

~~~text
Browser / Mobile
       |
       v
Java API (AKS / App Service / Container Apps)
       |
       v
Redis cache trên Azure
   | HIT              | MISS
   v                  v
Trả giá trị      Azure SQL / Cosmos DB
                      |
                      v
                SET Redis có TTL
                      |
                      v
                  Trả response
~~~

Trong kiến trúc **cache-aside**, Redis giữ dữ liệu có thể lấy lại từ backend; Azure SQL/Cosmos DB vẫn là **source of truth**. Khi cache bị xóa, hết TTL hoặc gặp failover, ứng dụng phải biết cách lấy dữ liệu từ nguồn chính hoặc degrade theo chính sách.

Redis không tự thay thế phân quyền người dùng, không tạo transaction nguyên tử với Azure SQL, không bảo đảm mọi cache hit là dữ liệu mới nhất và không cung cấp semantics của Azure Service Bus đối với hàng đợi công việc quan trọng.

## 2. Azure Managed Redis và Azure Cache for Redis

| Tiêu chí | Azure Managed Redis | Azure Cache for Redis kế thừa |
|---|---|---|
| Mục đích | Dịch vụ Redis được Azure quản lý cho các kiến trúc hiện hành | Cache Redis được nhiều hệ thống Azure đã triển khai |
| Endpoint | FQDN/cổng do resource cung cấp | FQDN/cổng do resource cung cấp |
| Cổng TLS thường gặp | **10000** ở nhiều cấu hình | **6380** ở nhiều cấu hình |
| Authentication | Entra ID/ACL/access key tùy cấu hình, tier và hỗ trợ | Access keys/Entra ID theo SKU và khả năng |
| Network | Private networking và giới hạn truy cập theo dịch vụ/tier | Private Endpoint/VNet integration theo tier |
| Cluster/HA | Theo deployment mode, shard/replica và SKU | Theo tier/replica/clustering |
| Lifecycle | Đánh giá cho kiến trúc mới | Kiểm tra thông báo chuyển đổi và mốc hỗ trợ |

**Không suy ra cổng thật chỉ từ tên sản phẩm**. Một Java application phải nhận **REDIS_HOST, REDIS_PORT, auth mode** từ cấu hình environment được xác minh với đúng Azure resource.

### Preflight trước khi viết code

1. Resource thuộc Azure Managed Redis hay Azure Cache for Redis?
2. Hostname và **TLS port** nào được cung cấp trong hướng dẫn kết nối?
3. Dịch vụ dùng **Entra token**, Redis ACL username/password hay access key?
4. Workload Java kết nối qua private endpoint hay một public endpoint có firewall?
5. Client cần **RedisClient** thông thường hay **Redis Cluster-aware client** theo topology?

Một Redis deployment được gọi là “managed” không đồng nghĩa mọi client và mọi Redis command đều được hỗ trợ như một Redis OSS instance cài trên máy cục bộ.

## 3. Cache nội bộ JVM khác gì Redis?

| Đặc điểm | Caffeine/JVM local cache | Redis |
|---|---|---|
| Nơi lưu | Heap của từng Java process | Cache service ngoài process |
| Network | Không cần | Có TCP/TLS/network latency |
| Chia sẻ giữa các replicas | Không tự động | Có thể dùng chung |
| Pod restart | Mất dữ liệu local | Redis có vòng đời riêng |
| Chi phí | JVM RAM/CPU | Redis SKU, network, ops, monitoring |
| Invalidation | Phải đồng bộ từng instance | Dùng shared key, vẫn cần TTL/invalidation |

Hai tầng cache có thể cùng tồn tại. Nhưng cập nhật một Redis key **không tự xóa** bản Caffeine đang nằm trong hàng chục Java pods. Mỗi tầng bổ sung một bài toán về độ mới dữ liệu.

## 4. Cache-aside và TTL

~~~text
GET product 123
     |
     v
GET Redis key
     |
     +-- HIT -> trả dữ liệu có thể chấp nhận
     |
     +-- MISS -> đọc DB -> SET Redis TTL -> trả dữ liệu
~~~

**TTL (time to live)** là thời hạn tồn tại của cache entry. Chọn TTL theo yêu cầu nghiệp vụ, không phải theo một hằng số áp dụng toàn bộ hệ thống.

| Dữ liệu | Có nên cache? | Thời gian stale cần lưu ý |
|---|---|---|
| Danh mục quốc gia | Thường phù hợp | Có thể chấp nhận dài |
| Danh mục sản phẩm công khai | Phù hợp nếu có invalidation | Giá/tồn kho cần kiểm tra lại |
| Dashboard tổng hợp | Tùy freshness SLO | Có thể hiển thị tuổi dữ liệu |
| Số dư hoặc trạng thái thanh toán | Không cache tùy tiện | Cần nguồn chính/transaction |
| Token/password | Chỉ trong giải pháp bảo mật chuyên biệt | Rò rỉ bí mật và vòng đời thu hồi |

### Invalidation khi dữ liệu thay đổi

~~~text
PUT product 123
    |
    v
Commit thay đổi trong database
    |
    v
DEL Redis key product 123
    |
    v
Lượt đọc sau -> MISS -> nạp dữ liệu mới
~~~

Nếu xóa cache lỗi sau khi database commit, giá trị cũ có thể còn cho đến hết TTL. **Tối ưu latency không được đánh đổi vô điều kiện lấy dữ liệu sai nghiệp vụ.**

## 5. TLS bảo vệ đường truyền Redis

TLS giúp mã hóa dữ liệu và xác minh server:

~~~text
Java client                     Redis server
     |                              |
     | ClientHello + SNI FQDN       |
     +----------------------------->|
     | Server certificate           |
     |<-----------------------------+
     | Validate CA + hostname       |
     | AUTH theo mode hỗ trợ        |
     +----------------------------->|
     | GET/SET trên kênh mã hóa      |
     +=============================>|
~~~

**Bắt buộc kiểm tra bốn điểm:**

1. Kết nối tới **TLS port** của đúng resource.
2. Client bật SSL/TLS.
3. Xác minh certificate chain và hostname; không dùng **trust-all**.
4. Kết nối theo FQDN chính thức, không thay bằng IP để né DNS.

**Private Endpoint không thay thế TLS**. Private Endpoint giới hạn đường mạng; TLS bảo vệ nội dung và danh tính của peer.

### Lỗi nguy hiểm cần tránh

- Bỏ **verifyPeer** để né lỗi PKIX.
- Kết nối Redis qua cổng không mã hóa chỉ vì ở VNet riêng.
- Dùng hostname của môi trường dev cho production.
- Dùng IP riêng trực tiếp khiến SNI/hostname verification không còn đúng.
- Log Redis URL chứa password/token.

Lỗi **SSLHandshakeException** hoặc **PKIX path building failed** phải được xử lý bằng kiểm tra CA/truststore/DNS/certificate, không bằng cách tắt xác minh server.

## 6. Hostname, SNI và Java truststore

Một cấu hình lab nên tách:

~~~text
REDIS_HOST=<FQDN được Azure cung cấp>
REDIS_PORT=<TLS port đúng>
REDIS_USERNAME=<username nếu auth mode yêu cầu>
REDIS_PASSWORD=<bí mật, chỉ cấp ở runtime>
~~~

Java sử dụng truststore JDK (hoặc cấu hình được quản trị) để xác minh chuỗi chứng chỉ. Một Java container loại bỏ hệ thống CA hoặc dùng JDK quá cũ có thể không tin certificate dù trình duyệt trên laptop vẫn tin.

### Những điều nên kiểm tra

- Phiên bản JDK còn được cập nhật bảo mật.
- Hostname mà Lettuce kết nối phải khớp certificate.
- DNS trả đường đi phù hợp với Private Endpoint nếu sử dụng.
- Không thiết lập custom trust manager **chấp nhận mọi certificate**.
- Không import CA/certificate chưa xác thực nguồn gốc.

Nếu một tổ chức dùng TLS inspection, thay đổi truststore cần được bộ phận an ninh đánh giá; không tự cho phép một CA lạ chỉ để kết nối thành công.

## 7. Authentication và quyền Redis

| Cơ chế | Cách hiểu | Lưu ý |
|---|---|---|
| **Microsoft Entra ID** | Redis data access qua token/danh tính khi dịch vụ hỗ trợ | Token có hạn, cần refresh/re-auth |
| **Redis ACL username/password** | Xác thực user và giới hạn lệnh/key theo quyền | Cần ACL phù hợp và rotation |
| **Access key/password** | Bí mật tĩnh do dịch vụ cung cấp | Phải giữ kín và rotate |
| **Azure RBAC management plane** | Quản lý Redis resource trong subscription | Không đồng nghĩa quyền GET/SET qua Redis protocol |
| **Application authorization** | Người dùng cuối được truy cập dữ liệu nào | Không được bỏ qua chỉ vì cache hit |

### Ưu tiên danh tính thay secret dài hạn

Với Java workload chạy trên Azure, **managed identity** hoặc **AKS Workload Identity** là hướng nên đánh giá để kết nối bằng Microsoft Entra ID nếu dịch vụ Redis/tier và SDK integration hỗ trợ.

Quy trình khái niệm:

~~~text
Java app với managed identity
       |
       v
Entra ID cấp access token đúng audience
       |
       v
Redis client AUTH theo format dịch vụ
       |
       v
Redis data-plane authorization
       |
       v
GET/SET theo quyền đã cấp
~~~

**Token không phải password vĩnh viễn**. Nếu client chỉ AUTH một lần bằng token lúc startup rồi không refresh/re-auth, nó có thể lỗi sau khi token hết hạn hoặc reconnect. Chọn thư viện/tích hợp Java hỗ trợ **token renewal** đúng với Azure Redis product đang dùng.

## 8. Ba lớp quyền không được nhầm

1. **Management plane:** ai được tạo/xóa/thay cấu hình Redis trong Azure.
2. **Redis data plane:** ai có thể AUTH, GET, SET, DEL hay thực hiện những Redis commands khác.
3. **Application layer:** user hoặc tenant nào được xem dữ liệu nghiệp vụ.

Ví dụ một Java service có Redis GET trên mọi key vẫn phải kiểm tra **user A không thể yêu cầu xem cart của user B**. Prefix key giúp tổ chức dữ liệu nhưng không tự là authorization.

### Least privilege

- Runtime identity chỉ có commands/key patterns cần thiết nếu ACL hỗ trợ.
- Không dùng admin credential cho mọi Java pods.
- Phân tách dev, staging và production.
- Bảo vệ quyền xem Key Vault secrets và attach managed identities.
- Có quy trình thu hồi quyền và rotation.
- Không cấp Owner trên toàn subscription để sửa lỗi Redis AUTH.

## 9. Quản lý credentials với Key Vault

Khi resource dùng access key/password, không đặt secret trong:

- Source Java, test source hoặc repository.
- Build script Maven/Gradle.
- Dockerfile, container image, Kubernetes ConfigMap.
- URL/command line có thể bị log.
- CI pipeline output, exception traces hoặc application diagnostics.

Một hướng an toàn hơn:

~~~text
AKS Workload Identity / App Service Managed Identity
           |
           v
Azure Key Vault
           |
           | secret read theo scope hẹp
           v
Java app nhận secret tại runtime
           |
           v
Lettuce / Spring Data Redis -> TLS -> Redis
~~~

Key Vault reference, Kubernetes Secrets Store CSI Driver hoặc cơ chế secret injection của nền tảng có thể dùng tùy kiến trúc. **Biến môi trường không phải kho bí mật tuyệt đối**: người có quyền xem process/container hoặc dump có thể truy cập.

### Credential rotation

1. Xem Redis service có hỗ trợ access keys song song hoặc rotation workflow nào.
2. Cấp secret mới theo quy trình phê duyệt.
3. Đảm bảo ứng dụng reload và reconnect/re-auth theo secret mới.
4. Xác minh kết nối/commands/metrics.
5. Thu hồi secret cũ khi không còn client phụ thuộc.
6. Có rollback plan nếu Redis AUTH bị gián đoạn.

**Không reset access key production để kiểm tra bài lab.**

## 10. Lettuce là gì?

**Lettuce** là Redis client Java dựa trên Netty, hỗ trợ synchronous, asynchronous và reactive operations. Nó thường được Spring Data Redis dùng trong Spring Boot.

### Khi nào dùng Lettuce trực tiếp?

- Ứng dụng Java không dùng Spring.
- Muốn kiểm soát rõ connection lifecycle, RedisURI/TLS và error handling.
- Có các luồng async/reactive cần thiết.
- Muốn viết một chương trình lab kết nối đơn giản.

### Dependency Maven

~~~xml
<dependency>
  <groupId>io.lettuce</groupId>
  <artifactId>lettuce-core</artifactId>
  <version>APPROVED_VERSION</version>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    implementation("io.lettuce:lettuce-core:APPROVED_VERSION")
}
~~~

**APPROVED_VERSION** là placeholder; phải dùng phiên bản được dự án phê duyệt và đã kiểm tra tương thích/bảo mật. Nếu sử dụng Spring Boot, thường nên để **Spring Boot dependency BOM** quản lý version.

## 11. Java Lettuce: ví dụ kết nối TLS an toàn

Đây là ví dụ **Java lab có thao tác SET/GET/DEL** trên Redis thử nghiệm. Nó áp dụng khi endpoint hỗ trợ **username/password ACL-style auth**. Nếu dùng Microsoft Entra ID, cần integration có refresh token riêng; không dùng mật khẩu tĩnh giả mạo token.

~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import java.time.Duration;
import java.util.UUID;

public final class RedisTlsLab {
    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String host = required("REDIS_HOST");
        int port = Integer.parseInt(required("REDIS_PORT"));
        String username = required("REDIS_USERNAME");
        String password = required("REDIS_PASSWORD");

        RedisURI uri = RedisURI.Builder.redis(host, port)
            .withAuthentication(username, password.toCharArray())
            .withSsl(true)
            .withVerifyPeer(true)
            .withTimeout(Duration.ofSeconds(3))
            .build();

        RedisClient client = RedisClient.create(uri);
        try {
            try (StatefulRedisConnection<String, String> conn =
                    client.connect()) {
                RedisCommands<String, String> redis = conn.sync();
                String key = "lab:java:tls:" + UUID.randomUUID();

                redis.setex(key, 30, "connected");
                String value = redis.get(key);
                if (!"connected".equals(value)) {
                    throw new IllegalStateException(
                        "Redis lab value mismatch");
                }
                System.out.println("Redis TLS/auth lab: PASS");
                redis.del(key);
            }
        } finally {
            client.shutdown();
        }
    }
}
~~~

### Những gì ví dụ bảo đảm và không bảo đảm

- Bật TLS, verify peer và dùng host/port từ config.
- Không ghi mật khẩu trong source hoặc stdout.
- TTL 30 giây giúp key lab không tồn tại vô hạn nếu client lỗi trước DEL.
- Code dùng RedisClient một endpoint logic; topology Redis Cluster khác có thể cần cluster-aware client.
- **Không được chạy trên production**: đây là write/delete test.
- Không phải production-ready về pool, retries, token refresh hay metrics.
- Java String chứa password vẫn có giới hạn về khả năng xóa khỏi memory; production cần secret management đúng quy trình.

### Nếu endpoint dùng password-only

Thay phần xác thực bằng API Lettuce cho password-only sau khi xác minh resource:

~~~java
RedisURI uri = RedisURI.Builder.redis(host, port)
    .withPassword(password.toCharArray())
    .withSsl(true)
    .withVerifyPeer(true)
    .withTimeout(Duration.ofSeconds(3))
    .build();
~~~

Không tự thêm username **default** nếu auth mode của resource không hướng dẫn như vậy.

## 12. Spring Boot và Spring Data Redis

Spring Data Redis cung cấp **RedisConnectionFactory**, **RedisTemplate** và **StringRedisTemplate**, cùng cache abstraction qua **@Cacheable** nếu dự án bật Spring caching.

### Dependency Spring Boot

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

### application.yml cho Spring Boot 3.x

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      client-type: lettuce
      connect-timeout: 3s
      timeout: 2s
      ssl:
        enabled: true
~~~

**Điều kiện:**

- Prefix **spring.data.redis** áp dụng với các phiên bản Spring Boot hiện đại như 3.x; kiểm tra phiên bản thật vì config namespace có thể khác.
- Với auth password-only, username có thể không cần thiết.
- Với Entra authentication, cấu hình username/password tĩnh này **không đủ**: dùng client integration có token refresh.
- **3s/2s** chỉ là ví dụ minh họa, cần đo theo SLO.
- Không hard-code hostname/port production trong code; Redis TLS port phải đúng resource.

## 13. Spring Java: thao tác GET, SET TTL, DEL

Ví dụ service dùng **StringRedisTemplate** để lưu JSON của một sản phẩm **công khai**:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public final class CatalogCache {
    private final StringRedisTemplate redis;

    public CatalogCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String read(String productId) {
        return redis.opsForValue().get(key(productId));
    }

    public void write(String productId, String publicJson) {
        redis.opsForValue().set(
            key(productId), publicJson, Duration.ofSeconds(60));
    }

    public void invalidate(String productId) {
        redis.delete(key(productId));
    }

    private String key(String productId) {
        return "public:catalog:product:" + productId + ":v1";
    }
}
~~~

Đoạn code giả định **productId đã được API validate**, **publicJson** thực sự không chứa dữ liệu riêng tư, và dự án có cấu hình RedisConnectionFactory/TLS hợp lệ. Đây là cache storage helper, không phải luồng cache-aside đầy đủ với database, circuit breaker và monitoring.

### Lưu ý về serializer

Nếu ứng dụng khác lưu cùng key dưới định dạng nhị phân khác, Spring StringRedisTemplate không tự hiểu schema đó. Nên dùng data format/version đã thỏa thuận và không tùy tiện bật Java native serialization trên dữ liệu không tin cậy.

## 14. Cache keys và tách tenant

Một key có thể có cấu trúc:

~~~text
<environment>:<service>:<entity>:<tenant>:<identifier>:<schema-version>

Ví dụ:
lab:catalog:product:public:123:v2
prod:catalog:product:tenant-A:123:v2
prod:catalog:product:tenant-B:123:v2
~~~

**Key prefix không thay thế authorization.** Ứng dụng vẫn phải xác thực caller và đảm bảo tenant ID dùng tạo key đến từ một nguồn tin cậy, không lấy header client chưa kiểm tra.

### Những thông tin không nên nằm trong key

- Password, Redis access keys, Entra tokens.
- Email/phone/id cá nhân không cần thiết.
- Tài liệu hoặc payload có tính bảo mật.
- URL chứa SAS token.
- Full SQL queries có tham số nhạy cảm.

Key dài cũng tốn bộ nhớ; cần cân bằng khả năng debug với kích thước key.

## 15. Cache-aside có race condition

Một tình huống:

~~~text
Thread A: GET Redis -> MISS
Thread A: đọc DB -> product v1

Thread B: UPDATE DB -> product v2
Thread B: DEL Redis key

Thread A: SET Redis -> product v1 với TTL
~~~

Sau đó, cache có thể trả v1 dù database đã có v2. Cache-aside **không bảo đảm atomicity** giữa Redis và Azure SQL/Cosmos DB.

Giải pháp tùy độ nhạy dữ liệu:

- TTL đủ ngắn.
- Version key hoặc ETag.
- Conditional population nếu có cơ chế version.
- Invalidation đáng tin sau transaction.
- Không sử dụng cache để xác nhận giá cuối cùng hoặc số dư.
- Có freshness tests theo nghiệp vụ.

## 16. Java client lifecycle và pooling

Một lỗi thường gặp là tạo RedisClient trong từng HTTP request:

~~~text
Request 1 -> Create client -> TCP/TLS -> GET -> Close
Request 2 -> Create client -> TCP/TLS -> GET -> Close
...
~~~

Cách này làm tăng TLS handshake, sockets, CPU và latency. **RedisClient/Lettuce ConnectionFactory nên được tạo dài hạn** theo lifecycle application.

| Trường hợp | Hướng quản lý connection |
|---|---|
| GET/SET thường xuyên | Reuse client và connection theo contract thread-safety |
| Blocking Redis commands | Dùng connection chuyên biệt phù hợp |
| Pub/Sub subscription | Connection/subscription riêng |
| Transaction/stateful commands | Kiểm soát connection ownership và scope |
| Nhiều Java pods | Giới hạn tổng kết nối theo cache capacity |

Lettuce **StatefulRedisConnection** hỗ trợ những thao tác đồng thời theo contract client, nhưng một số commands có trạng thái/blocking không thích hợp chia chung. **Pooling không luôn làm nhanh hơn**: quá nhiều connections chỉ tăng áp lực tài nguyên.

### Phép tính ngân sách connections

~~~text
25 pods x 40 connections/pod
= 1.000 connections tiềm năng
~~~

Đó chưa tính monitoring clients, rollout hai phiên bản đồng thời và reconnect storm. Hãy đo **active, idle, pending, reconnect count** và Redis limits trước khi tăng pool.

## 17. Timeout phải nằm trong ngân sách API

| Timeout | Mục đích |
|---|---|
| **Connect** | Giới hạn thời gian tạo TCP connection |
| **TLS handshake** | Giới hạn thời gian thiết lập kênh an toàn |
| **Command** | Giới hạn thời gian GET/SET chờ phản hồi |
| **Pool acquisition** | Giới hạn chờ connection khi pool hết |
| **HTTP request** | Giới hạn toàn bộ thời gian xử lý nghiệp vụ |

Ví dụ API có SLO p95 **300 ms**, trong đó Redis chỉ nên chiếm một phần ngắn. Nếu Redis command timeout đặt 10 giây, ứng dụng có thể vượt SLO dù nguồn SQL tốt.

Không có một timeout cố định đúng cho mọi workload; cần đo TLS handshake, mạng vùng, p95/p99, failover và Redis load. **Timeout quá ngắn** cũng gây lỗi giả và tăng retry load.

## 18. Retry phải an toàn

Các lỗi kết nối tạm thời có thể phát sinh khi failover, network jitter, DNS chuyển đổi, server busy hoặc client reconnect. Dùng:

1. Retry hữu hạn.
2. Exponential backoff + jitter.
3. Deadline tổng cho request.
4. Circuit breaker khi Redis unavailable.
5. Giới hạn concurrency để không gây retry storm.
6. Fallback theo loại dữ liệu.

### Lệnh Redis không giống nhau về khả năng retry

| Command | Retry sau timeout? | Lý do |
|---|---|---|
| **GET** | Thường tương đối an toàn | Không tạo side effect |
| **SET** cùng value | Tùy TTL/version semantics | Retry có thể làm mới TTL |
| **INCR** | Không retry mù | Có thể tăng hai lần |
| **LPUSH** | Không retry mù | Có thể thêm hai lần |
| **PUBLISH** | Không retry mù | Có thể phát lại tín hiệu |
| **DEL** | Thường có thể lặp, nhưng xem nghiệp vụ | Key có thể được tái tạo giữa hai lần DEL |

Client timeout **không chứng minh command chưa được Redis thực thi**. Các ghi có ý nghĩa nghiệp vụ cần idempotency hoặc một nguồn dữ liệu bền vững để đối chiếu.

## 19. Fallback an toàn khi Redis lỗi

~~~text
GET /catalog
      |
      v
GET Redis (short timeout)
    | HIT            | MISS / cache unavailable
    v                v
Return cache       Read Azure SQL
                        |
                        v
                     Return data
~~~

Cache outage không nên làm mất đơn hàng. Nhưng nếu tất cả requests cùng fallback xuống database, **DB stampede** có thể làm sự cố lan rộng.

Biện pháp:

- Circuit breaker.
- Bounded DB concurrency và rate limit.
- Single-flight theo key.
- Local cache ngắn cho dữ liệu public nếu phù hợp.
- Serve stale **chỉ khi nghiệp vụ cho phép**.
- Fail closed cho chức năng bảo mật thay vì cho phép vô điều kiện.

**Redis dùng làm rate-limiter hoặc distributed lock không nên được bỏ qua theo cùng logic fallback của public catalog.**

## 20. Cache stampede, hot key và TTL jitter

Khi một key phổ biến hết TTL, hàng nghìn requests có thể đồng thời miss và gọi database:

~~~text
Key public:catalog:123 hết hạn
     |
     +-- Request A -> DB
     +-- Request B -> DB
     +-- Request C -> DB
     ...
~~~

Hướng giảm tải:

- Single-flight/coalescing cho cùng key.
- Cache warm-up cho key phổ biến.
- TTL jitter trong khoảng stale được chấp nhận.
- Negative caching với TTL rất ngắn nếu hợp đồng cho phép.
- Bounded concurrency và backend rate limiting.
- Theo dõi key distribution để phát hiện **hot keys**.

Ví dụ TTL danh nghĩa 300 giây cộng jitter 0–30 giây chỉ phù hợp khi dữ liệu cho phép stale thêm tối đa 30 giây. Không dùng jitter tùy ý cho dữ liệu phải hết hạn chính xác vì yêu cầu bảo mật.

## 21. Serialization và schema version

Redis lưu values ở dạng bytes/strings theo Redis protocol. Java objects cần được chuyển đổi với serializer phù hợp. Những lựa chọn phổ biến gồm JSON, MessagePack hoặc định dạng nhị phân có schema rõ ràng.

### Rủi ro khi thay đổi Java model

~~~text
Deployment v1 ghi cache:
  {"schemaVersion":1,"productId":"123","price":100000}

Deployment v2 đổi contract:
  {"schemaVersion":2,"productId":"123","priceMinor":100000}

Nếu v2 đọc key cũ mà không migration:
  Deserialize/logic giá có thể thất bại hoặc sai.
~~~

Nên:

- Đặt **schemaVersion** trong payload và/hoặc key suffix.
- Kiểm soát kích thước item; không đưa object graph quá lớn vào cache.
- Tránh deserialization kiểu Java native không giới hạn với dữ liệu không tin cậy.
- Tạo tests tương thích giữa các phiên bản trong thời gian rolling deploy.
- Không cho client tùy ý điều khiển class name/deserializer type.
- Có chiến lược xóa/đổi version key khi schema thay đổi.

Ví dụ JSON dữ liệu public:

~~~json
{
  "schemaVersion": 2,
  "productId": "123",
  "name": "Lab Product",
  "priceDisplay": "100000 VND",
  "cachedAt": "2026-11-20T08:00:00Z"
}
~~~

Trường **cachedAt** giúp debug, nhưng **không thay thế TTL và điều kiện freshness** từ nghiệp vụ.

## 22. Đa tenant và nguy cơ rò rỉ dữ liệu

Trong SaaS, một key chỉ dựa vào productId có thể sai nếu hai tenant có giá riêng.

~~~text
KHÔNG ĐỦ với response theo tenant:
  catalog:product:123

Phân vùng rõ ràng hơn:
  catalog:tenant-A:product:123:v2
  catalog:tenant-B:product:123:v2
~~~

Tuy nhiên **key prefix không tự là access control**. Java API phải:

1. Xác thực user/tenant từ nguồn tin cậy.
2. Xác minh quyền trước khi trả dữ liệu kể cả khi Redis hit.
3. Lấy tenant ID từ identity đã được kiểm tra, không dùng header tự khai báo.
4. Không cache user profile dưới key dùng chung.
5. Bảo vệ bí mật/tokens/PII theo data classification.
6. Phân tách Redis workloads hoặc ACL khi yêu cầu cô lập mạnh hơn.

**TLS chỉ bảo vệ đường truyền**, không ngăn Java bug trả cache tenant A cho tenant B.

## 23. Redis không thay database bền vững

Cache entries có thể biến mất do TTL, eviction khi memory thiếu, maintenance, failover hoặc thao tác vận hành. Redis persistence, replication và durability (nếu tier hỗ trợ) phải được đánh giá độc lập.

Không dùng Redis như nguồn sự thật cho:

- Số dư và giao dịch thanh toán.
- Đơn hàng đã xác nhận.
- Inventory nếu không có cơ chế điều phối và ghi bền vững.
- Log kiểm toán phải giữ theo yêu cầu pháp lý.

Một cache có thể mất toàn bộ keys mà hệ thống **vẫn phải tái tạo được từ nguồn chính**, hoặc ứng dụng phải degrade có chủ đích.

### Redis Pub/Sub khác Azure Service Bus

Redis Pub/Sub phù hợp các tín hiệu tạm thời giữa các subscribers đang online; subscriber offline có thể bỏ lỡ message. Nó không cung cấp settlement, DLQ và cách giao lại như Service Bus Peek-Lock.

~~~text
Java Publisher
      |
      v
Redis Pub/Sub channel
      |
      +-- Subscriber A online -> nhận
      +-- Subscriber B online -> nhận
      +-- Subscriber C offline -> có thể bỏ lỡ
~~~

Nếu hệ thống phải đảm bảo công việc cuối cùng được xử lý và có điều tra lỗi, cân nhắc **Azure Service Bus** hoặc luồng bền vững được thiết kế phù hợp, thay vì gọi Redis Pub/Sub là durable queue.

## 24. VNet, Private Endpoint và DNS

Một kiến trúc an toàn:

~~~text
Public Internet
       |
       v
API ingress / gateway
       |
       v
Java application trong VNet
       |
       | DNS resolves Redis FQDN to private route
       v
Redis Private Endpoint
       |
       v
Azure Redis service
~~~

Tính năng Private Endpoint/VNet integration phụ thuộc **sản phẩm và tier**. Không mặc định mọi Redis deployment đều cấu hình giống nhau.

### Checklist network

- Java workload có VNet integration/đường route tới endpoint?
- DNS tại **pod/VM/process thật** trả địa chỉ phù hợp Private Endpoint?
- Private Endpoint connection ở trạng thái được duyệt?
- NSG, UDR, Azure Firewall và egress rules cho phép **cổng TLS đúng**?
- Firewall và public network access được hạn chế phù hợp?
- Java vẫn dùng **FQDN chính thức** để TLS verify hostname?
- Redis data-plane authentication có hoạt động qua đường mạng đó?

### Lỗi DNS phổ biến

Một người quản trị đã tạo Private Endpoint nhưng Java pod vẫn resolve hostname về IP công cộng do thiếu private DNS zone link hoặc custom resolver forwarding. Không nên sửa bằng cách hard-code private IP trong Java: việc đó có thể gây lỗi TLS/SNI, khó vận hành khi IP thay đổi.

## 25. Đọc lỗi Redis theo từng lớp

| Lớp | Dấu hiệu | Kiểm tra |
|---|---|---|
| **DNS** | UnknownHostException | FQDN, private DNS zone và resolver |
| **TCP** | Connect timeout/refused | Port TLS, NSG/UDR, firewall, endpoint approval |
| **TLS** | SSLHandshakeException/PKIX | Certificate chain, truststore, SNI/hostname |
| **AUTH** | NOAUTH, WRONGPASS hoặc token error | Đúng auth mode, Redis ACL, token expiry và rights |
| **Topology** | MOVED/ASK hoặc redirect errors | Cluster-aware client, topology và networking |
| **Server** | OOM/command latency, evictions | Memory, CPU, Redis maxmemory policy, hot keys |
| **Client** | Pool timeout, reconnect loop | Connection lifecycle, pool size, threads |
| **Application** | Cache sai tenant, stale data | Key schema, auth, TTL, invalidation |

### Thứ tự xử lý

1. Xác định service type/hostname/port/auth mode.
2. Phân giải DNS từ nơi Java thực sự chạy.
3. Kiểm tra TCP tới TLS port.
4. Kiểm tra TLS/certificate/hostname.
5. Kiểm tra AUTH theo cơ chế đúng.
6. Kiểm tra PING hoặc GET nhỏ trong lab.
7. Đo latency, reconnects và resource usage.

**Không thay đổi tất cả cài đặt cùng lúc.** Nếu lỗi ở DNS, rotate password không giúp gì; nếu lỗi ở TLS, cấp Owner subscription cũng không giúp gì.

## 26. Kiểm tra DNS/TLS bằng công cụ chẩn đoán

Các lệnh dưới đây kiểm tra kết nối ở môi trường được phép; không xóa hoặc cấu hình Redis resources.

### Kiểm tra DNS

~~~bash
nslookup "$REDIS_HOST"
~~~

### Kiểm tra certificate qua TLS

~~~bash
openssl s_client \
  -connect "$REDIS_HOST:$REDIS_PORT" \
  -servername "$REDIS_HOST" \
  -verify_return_error < /dev/null
~~~

Lệnh này giúp kiểm tra TLS certificate chain và SNI, **không tự chứng minh Redis AUTH thành công**.

### Kiểm tra redis-cli mà không đưa password vào arguments

~~~bash
# Chỉ dùng với endpoint/credentials lab hợp lệ.
redis-cli \
  -h "$REDIS_HOST" \
  -p "$REDIS_PORT" \
  --tls \
  --user "$REDIS_USERNAME" \
  --askpass \
  PING
~~~

**Chú ý:** cần redis-cli hỗ trợ TLS; nếu auth password-only hãy điều chỉnh theo tài liệu. Với Entra token auth, lệnh trên không tự cung cấp cơ chế refresh token. Tránh **-a password** trên command line vì có thể lộ qua process listing/history.

### Những lệnh không dùng để chẩn đoán production

- **FLUSHALL/FLUSHDB**: có nguy cơ xóa toàn bộ dữ liệu.
- **KEYS \***: có thể gây tải nặng trên keyspace lớn.
- **CONFIG SET**: thay hành vi Redis, có thể không được hỗ trợ.
- **MONITOR** kéo dài: tốn tài nguyên và có thể lộ dữ liệu.

Đối với inventory key, dùng telemetry hoặc công cụ quan sát do vận hành phê duyệt; nếu cần quét keyspace hãy dùng phương pháp có giới hạn trên lab.

## 27. Redis Cluster và client mode

Redis trên Azure có thể được triển khai qua một endpoint logic hoặc nhiều shards/Redis Cluster protocol tùy loại dịch vụ/tier. Không phải cứ instance lớn là bạn phải tạo **RedisClusterClient**, cũng không phải mọi deployment đều chấp nhận **RedisClient** đơn node.

### MOVED/ASK

Trong Redis Cluster protocol, phản hồi **MOVED/ASK** hướng client tới node/slot khác. Nếu thấy lỗi:

1. Xác minh Redis instance đang dùng cluster protocol hay một endpoint Enterprise-managed routing.
2. Dùng client mode/version hỗ trợ topology thật.
3. Kiểm tra SSL và khả năng truy cập DNS/ports của các node được khám phá.
4. Không sửa bằng cách kết nối vào IP shard rồi tắt TLS.

### Không dựa vào Redis logical DB index để cô lập tenant

Redis Cluster có giới hạn liên quan lệnh **SELECT** và logical databases. Dùng tenant key prefixes, Redis ACL, phân tách tài nguyên và authorization ở ứng dụng theo yêu cầu; **SELECT 1 không phải biện pháp bảo mật tenant**.

## 28. Metrics cần theo dõi

| Nhóm | Metric/telemetry | Ý nghĩa |
|---|---|---|
| Cache | Hit rate, miss rate | Hiệu quả giảm tải database |
| Latency | GET/SET p50/p95/p99 | Cache response có đáp ứng API SLO? |
| Connections | Active/idle, reconnect, handshake errors | Chẩn đoán pool/connection storm |
| Security | AUTH errors, token refresh failures | Credential/identity đã hoạt động? |
| Memory | Used memory, fragmentation, evictions | Phát hiện thiếu RAM/eviction |
| Capacity | CPU/server load, bandwidth/operations | Nhìn giới hạn theo tier |
| Data freshness | Cache age, stale responses | Kiểm tra đúng nghiệp vụ |
| Backend | SQL/Cosmos DB calls khi cache miss | Phát hiện cache outage cascade |
| Cost | Redis SKU, data transfer, logs, backend savings | Đo ROI thật |

Không phải tất cả là metric Azure Monitor có sẵn cùng tên. Những giá trị như Redis command p99 theo method, business cache hit rate hoặc token refresh failures thường cần **Micrometer/OpenTelemetry/client instrumentation**.

### Log an toàn

~~~json
{
  "service": "catalog-api",
  "operation": "GET",
  "cache": "publicCatalog",
  "result": "HIT",
  "durationMs": 8,
  "environment": "lab",
  "correlationId": "req-lab-42"
}
~~~

Không log access keys, Entra tokens, Redis URI chứa secret, raw customer data hoặc full keys có PII.

## 29. Observability: hit rate chưa đủ

Ví dụ:

~~~text
100.000 requests/ngày
Cache hit rate = 80% (giả định)

Backend fetches lý thuyết:
  100.000 x (1 - 0,80) = 20.000/ngày

Backend reads tránh được:
  80.000/ngày
~~~

Đây chỉ là mô hình sơ bộ. Cache warm-up, retries, eviction, multi-key requests và database reads bị nhân bởi thundering herd làm số thực tế khác.

**Một cache trả dữ liệu sai tenant hoặc sai giá thanh toán vẫn là thất bại** dù hit rate 99%. Kết hợp metrics hiệu năng và tests tính đúng đắn.

### Alert nên có

- TLS/AUTH/connect errors tăng.
- Redis command p99 vượt ngân sách latency.
- Cache hit rate giảm đột ngột sau deployment.
- Memory/evictions tăng.
- Redis outage tạo spike trên SQL/Cosmos DB.
- Secret/token rotation thất bại.
- Private DNS/endpoint bị thay đổi ngoài quy trình.
- Chi phí cache tăng nhưng số backend reads không giảm.

## 30. Spring Cache abstraction và @Cacheable

Spring Boot có thể dùng **RedisCacheManager** và các annotations:

- **@Cacheable**: lấy từ cache hoặc gọi method để nạp.
- **@CacheEvict**: loại entry theo điều kiện.
- **@CachePut**: cập nhật cache theo kết quả method.

Ví dụ ý tưởng, chỉ dành cho catalog public:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public final class PublicCatalogService {
    private final CatalogRepository repository;

    public PublicCatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "publicCatalog",
        key = "#productId"
    )
    public ProductDto getPublicProduct(String productId) {
        return repository.loadPublicProduct(productId);
    }
}
~~~

**CatalogRepository** và **ProductDto** chưa được định nghĩa; snippet chỉ minh họa annotation. Production cần cấu hình RedisCacheManager, serializer, TTL, key prefix, validation, auth, metrics, fallback và invalidation.

### Các bẫy thường gặp

- Spring proxy-based caching có thể không áp dụng khi **self-invocation** trong cùng bean.
- CacheManager mặc định có thể không đặt TTL như yêu cầu nghiệp vụ.
- Một cacheName/key không phân biệt tenant có thể lộ dữ liệu.
- Không có cache error handler phù hợp có thể khiến Redis outage làm cả API fail.
- Đổi serializer giữa deployments làm key cũ không tương thích.

## 31. Microsoft Entra ID từ Java: token refresh

Nếu Redis instance hỗ trợ Entra auth, một kết nối an toàn nên có:

~~~text
Java app trên Azure
        |
        | Managed Identity / Workload Identity
        v
Microsoft Entra ID
        |
        | Access token đúng audience/resource
        v
Redis client AUTH theo format dịch vụ hỗ trợ
        |
        v
Redis data-plane permissions
        |
        v
Commands qua TLS
~~~

### Những bước triển khai

1. Xác minh Redis resource hỗ trợ Entra auth và account/user permission tương ứng.
2. Cấp quyền data-plane tối thiểu cho managed identity.
3. Dùng Azure Identity SDK để lấy token theo resource scope mà dịch vụ Redis yêu cầu.
4. Dùng Lettuce/Jedis integration đã hỗ trợ **AUTH, token renewal, reconnect/re-auth**.
5. Kiểm thử khi token sắp hết hạn và khi Redis failover.
6. Không in token và không đưa token vào URL/command line.
7. Thu hồi access keys cũ theo kế hoạch migration khi không cần nữa.

### Vì sao không minh họa một lệnh AUTH với token hard-code?

Một access token được lấy lúc khởi động có thời hạn. Khi nó hết hạn, client có thể không mở được kết nối mới hoặc bị yêu cầu xác thực lại. **Quản lý vòng đời token là một phần bắt buộc của kết nối an toàn**, không phải chi tiết có thể bỏ qua. Ngoài ra username mapping, audience và thư viện hỗ trợ khác nhau theo Azure Redis product/tier.

Vì thế, hãy dùng thư viện/ứng dụng tích hợp Java được tài liệu **của đúng Redis service** khuyến nghị, thay vì sao chép một token vào password rồi để kết nối chạy vô thời hạn.

## 32. Managed identity theo nền tảng Java

| Compute | Danh tính gợi ý | Cần kiểm tra |
|---|---|---|
| App Service | System/user-assigned managed identity | Identity, Redis permissions, VNet integration |
| AKS | Microsoft Entra Workload ID | ServiceAccount federation, OIDC issuer, network policy |
| Azure Container Apps | Managed identity | Identity attachment, VNet ingress/egress |
| Azure VM | Managed identity | VM identity, NSG/UDR, endpoint |
| Local developer | Developer identity được cấp quyền | Tenant/subscription đúng, không dùng production privileges |

Managed identity **không tự cấp Redis permissions**, không mở firewall, không sửa DNS và không tự cài integration token refresh. Phải kiểm tra từng lớp.

## 33. Xử lý secret rotation không gián đoạn

~~~text
Ứng dụng dùng credential A
            |
            v
Cấp credential B theo cách resource hỗ trợ
            |
            v
Cập nhật Key Vault/secret store
            |
            v
Rollout Java instances -> reconnect/auth bằng B
            |
            v
Kiểm chứng Redis commands, logs và error metrics
            |
            v
Vô hiệu hóa A theo change plan
~~~

Không phải mọi Redis deployment đều có **hai active keys** hay cùng quy trình rotation. Phải kiểm tra tính năng thực của resource, tránh reset key cũ trước khi app mới được cấu hình và reconnect.

Các lỗi đáng theo dõi:

- Key Vault đã đổi nhưng process vẫn giữ secret cũ.
- Rolling deploy tạo nhiều connections cùng lúc.
- Entra token mới có audience/ACL không đúng.
- Container instance mới không có Workload Identity federation.
- Secret bị ghi vào deployment diff hoặc CI logs.

## 34. Redis cache và distributed lock

Redis có thể hỗ trợ phối hợp tác vụ, nhưng dùng một lock key có TTL không bảo đảm business exclusivity tuyệt đối:

~~~text
Worker A nhận lock -> làm việc lâu
        |
        v
Lock TTL hết hạn
        |
        +--> Worker B nhận lock mới
        |
        v
Worker A vẫn có thể ghi side effect
~~~

Những bài toán quan trọng cần đánh giá **lock ownership token, lease renewal, fencing token, conditional writes, idempotency** và nguồn dữ liệu chính. Redis cache không thay SQL transaction hay optimistic concurrency của Cosmos DB chỉ nhờ một lệnh SET NX.

## 35. Redis trong kiến trúc realtime Azure

| Nhu cầu | Dịch vụ/khả năng nên cân nhắc |
|---|---|
| Cache catalog/product lookup | Redis |
| Tín hiệu tạm thời giữa process online | Redis Pub/Sub tùy yêu cầu |
| Job phải ACK, retry và có DLQ | Azure Service Bus |
| Telemetry stream, partition và replay | Azure Event Hubs |
| Routing BlobCreated/resource events | Azure Event Grid |
| Browser WebSocket realtime | Azure Web PubSub/Azure SignalR Service |

Không đưa các giao dịch thanh toán vào Redis Pub/Sub rồi giả định người nhận offline sẽ được giao lại. Redis có thể hỗ trợ realtime, nhưng tính bền vững, ordering và recovery phải được thiết kế đúng theo service.

## 36. Chi phí Redis phải so với lợi ích

Các yếu tố chi phí:

- Redis SKU/tier, memory/compute và availability.
- Network/Private Endpoint/data transfer.
- Monitoring và Log Analytics.
- Connections, TLS handshakes và client CPU.
- Dung lượng dữ liệu/cấu trúc, serialization overhead và eviction.
- Azure SQL/Cosmos DB reads tránh được nhờ cache.
- Thời gian vận hành, incident response và migration.

### Bài toán lựa chọn cache size

Đừng chỉ cộng bytes của JSON values. Redis còn dùng memory cho **keys, metadata, allocator overhead, internal structures** và fragmentation. Một cache đạt 95% RAM chưa chắc còn đủ headroom cho writes, failover hoặc spike.

Tăng Redis capacity có thể giúp, nhưng phải kiểm tra cache key cardinality, big keys, eviction policy và TTL trước. Không lấy cache size theo một số GB “ước lượng cho chắc” rồi bỏ qua metrics.

## 37. Quy trình lab an toàn: Java kết nối Redis trên Azure

**Mục tiêu:** xác minh TLS, AUTH và SET/GET key lab có TTL trong môi trường được cấp phép.

### Chuẩn bị

1. Có Redis instance lab và xác định đúng product/tier.
2. Có FQDN/TLS port/auth mode thật của instance.
3. Java runtime có đường network hợp lệ.
4. Có credentials lab hoặc tích hợp Entra được kiểm chứng.
5. Có Lettuce dependency tương thích; không chạy lệnh Gradle của repository bài học này.
6. Có quyền xem logs/metrics theo scope.

### Các bước

1. Ghi lại FQDN/cổng/auth mode, không ghi password vào tài liệu.
2. Kiểm tra DNS từ nơi Java process sẽ chạy.
3. Kiểm tra TLS certificate/hostname.
4. Cấp credentials theo secret store/identity.
5. Chạy Java Lettuce lab ở mục 11 hoặc nhánh password-only nếu đúng auth mode.
6. Xác minh SET/GET trả giá trị expected, key có TTL.
7. Xác minh client không in secret, đóng connection.
8. Kiểm tra Redis command latency và connect/auth errors.
9. Thử Redis unavailable **chỉ trong lab** để xác minh timeout và fallback.
10. Xóa key lab nếu còn hoặc để TTL hết; không xóa resource production.

### Bảng nghiệm thu

| Kiểm tra | Kết quả đạt |
|---|---|
| Host/port | Đúng Redis instance và TLS port |
| DNS/private route | FQDN phân giải/định tuyến theo kiến trúc |
| TLS | Certificate chain/hostname được verify |
| AUTH | Đúng Redis data-plane permission |
| SET/GET | Giá trị lab đúng, TTL được áp |
| Cleanup | Key lab hết hạn hoặc được xóa, client đóng an toàn |
| Failure | Timeout hữu hạn; không treo HTTP vô hạn |
| Logging | Không lộ token/password/PII |
| Monitoring | Có connect/command latency và error counters |

Một lần PASS **không chứng minh** token refresh, failover, cluster topology, high concurrency hoặc multi-region routing. Những chủ đề đó cần test riêng.

## 38. Case study: catalog API Java chạy trên AKS

Một doanh nghiệp triển khai **catalog-api** gồm 20 Java pods trên AKS:

- Azure SQL Database lưu sản phẩm và giá.
- Redis cache dữ liệu catalog công khai, không là nguồn giá checkout.
- Lưu lượng GET cao hơn hàng chục lần số lần UPDATE.
- Redis có Private Endpoint và chỉ cho phép TLS.
- Mong muốn dùng Workload Identity/Entra nếu resource hỗ trợ.
- API SLO p95 là 200 ms.
- Yêu cầu Redis outage không làm sập Azure SQL.
- Dữ liệu catalog có một phần biến đổi theo tenant.

### Nhiệm vụ

1. Vẽ request path từ ingress đến Java, Redis, SQL.
2. Chỉ ra nơi áp TLS, DNS và Private Endpoint.
3. Giải thích cách kiểm tra đúng Redis TLS port.
4. Chọn auth mode và mô tả token renewal nếu dùng Entra.
5. Nêu cách cấp quyền Redis data plane cho AKS Workload Identity.
6. Tính số connections tiềm năng nếu mỗi pod có pool tối đa 40.
7. Đề xuất TTL và cách invalidation khi giá thay đổi.
8. Vì sao checkout phải xác nhận giá từ nguồn chính?
9. Thiết kế key phân biệt tenant và schemaVersion.
10. Chọn timeout Redis phù hợp API p95 200 ms.
11. Thiết kế circuit breaker và giới hạn DB fallback.
12. Nêu năm metrics/alerts có ý nghĩa.
13. Mô tả rotation credentials không gây outage.
14. Nếu có realtime notifications, vì sao Redis Pub/Sub chưa chắc phù hợp để gửi công việc thanh toán?

### Hướng giải

**Network và security:** AKS pod → private DNS → Redis FQDN/Private Endpoint → TLS verify hostname → AUTH theo managed identity token đã refresh hoặc secret store được cấp quyền.

**Cache:** cache-aside cho public catalog, TTL ngắn có kiểm chứng, invalidation sau DB commit; tenant-specific values dùng namespace/authorization, checkout đọc dữ liệu chuẩn.

**Resilience:** Redis command deadline ngắn, bounded retry, circuit breaker, single-flight và giới hạn DB fallback concurrency.

**Operations:** quan sát hit rate, p99 Redis, evictions, auth/connect failures, DB CPU/IO trong cache outage và monthly cost.

## 39. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| UnknownHostException | Sai FQDN/private DNS | Resolve từ pod/VM đúng VNet |
| Connect timeout | Sai port, firewall, NSG/UDR, endpoint | Kiểm tra TCP route/TLS port |
| SSLHandshakeException | CA/truststore/hostname/SNI | Verify chain, không tắt TLS |
| NOAUTH/WRONGPASS | Sai credential hoặc Entra token/ACL | Xác định auth mode và quyền |
| Lúc đầu chạy rồi lỗi AUTH | Token hết hạn/không refresh hoặc secret rotation | Kiểm tra lifecycle và reconnection |
| MOVED/ASK liên tục | Client mode/topology không phù hợp | Xác định Redis Cluster protocol |
| Too many connections | Mỗi request tạo client hoặc pool quá lớn | Đo tổng pods x connections |
| Redis timeout khiến API 5xx | Không có fallback/circuit breaker | Timeout budget, degrade hợp lý |
| Cache hit thấp | TTL ngắn, keys phân mảnh, invalidation liên tục | Đo hit rate theo cache group |
| Cache trả dữ liệu tenant khác | Key không tách tenant hoặc thiếu authorization | Điều tra bảo mật, sửa key/auth |
| Database spike khi Redis lỗi | Cache stampede/fallback không giới hạn | Single-flight, DB concurrency cap |
| Evictions/OOM | Memory pressure, quá nhiều keys/big values | Xem TTL, sizing, Redis metrics |
| Key cũ không deserialize | Schema/serializer thay đổi | Key version và migration strategy |
| Token nằm trong logs | Logging quá chi tiết | Redaction, incident response và rotate |

### Chẩn đoán sáu bước

1. **Resource:** xác định đúng Azure Redis product/tier, FQDN, port.
2. **Network:** DNS, Private Endpoint, VNet, NSG/UDR/firewall.
3. **TLS:** certificate/SNI/hostname/JDK truststore.
4. **AUTH:** data-plane role, access key/ACL hoặc token renewal.
5. **Client:** Lettuce/Spring version, topology, connection pool, timeout, reconnect.
6. **Business:** cache key, TTL, consistency, fallback, dữ liệu theo tenant.

Không thay đổi production firewall hoặc dùng trust-all trước khi xác định lỗi ở lớp nào.

## 40. Checklist production

| Nhóm | Tiêu chí PASS |
|---|---|
| Product lifecycle | Đúng loại Redis, SKU và chính sách support/migration |
| Endpoint | FQDN/cổng TLS từ instance, không hard-code IP |
| Encryption | TLS bật, verify chain và hostname/SNI |
| Identity | Entra auth nếu hỗ trợ, hoặc secret được quản lý chặt |
| Token lifecycle | Refresh/re-auth/reconnect đã được thử |
| ACL | Data-plane least privilege, admin/runtime tách biệt |
| Secret handling | Key Vault/secret injection và rotation/rollback |
| Networking | Private Endpoint/VNet/DNS/firewall được kiểm chứng |
| Java runtime | JDK/Lettuce/Spring versions được hỗ trợ |
| Client lifecycle | Reuse, bounded pool và connection budget |
| Resilience | Timeout, bounded retry/backoff, circuit breaker |
| Fallback | Tránh DB stampede, fail-open/closed đúng nghiệp vụ |
| Cache model | Cache-aside/TTL/invalidation rõ ràng |
| Data isolation | Tenant key schema, authorization, no PII logging |
| Serialization | Schema version, input validation, no unsafe deserialization |
| Monitoring | Hits/misses, latency, connection errors, memory/evictions |
| Cost | Redis size/tier/network/monitoring so với backend savings |
| Drills | Đã thử cache outage, reconnect, secret rotation, failover |
| Runbook | Có owner, lịch kiểm tra và cách purge key đúng phạm vi |

## 41. Câu hỏi tự kiểm tra

1. Vì sao Redis cache không nên là nguồn chính cho đơn hàng và số dư?
2. Redis local JVM cache khác shared Redis như thế nào?
3. Azure Managed Redis và Azure Cache for Redis có dùng cùng TLS port trong mọi trường hợp không?
4. Vì sao cần dùng FQDN thay IP và giữ SNI/hostname verification?
5. Private Endpoint có thay TLS không?
6. Lỗi PKIX nên được xử lý bằng cách nào?
7. Managed identity có tự cho phép thực hiện Redis GET/SET không?
8. Entra token có thể dùng như password tĩnh vô thời hạn không?
9. Redis ACL khác ứng dụng kiểm tra quyền user cuối ở điểm nào?
10. Vì sao không đặt password trong application.yml commit Git?
11. RedisClient nên tạo mỗi request hay reuse?
12. Khi nào cần connection riêng cho blocking/transaction/PubSub?
13. Connect timeout và command timeout khác nhau ra sao?
14. Vì sao retry INCR có thể gây sai dữ liệu?
15. Cache-aside có race condition khi update DB và invalidate không?
16. TTL có thay thế cache invalidation không?
17. Key schema cần phân biệt tenant và version khi nào?
18. Vì sao không dùng key prefix làm authorization?
19. Cache stampede là gì?
20. TTL jitter có rủi ro với loại dữ liệu nào?
21. Vì sao Redis outage có thể gây database outage?
22. Redis Cluster MOVED/ASK báo hiệu vấn đề gì?
23. Vì sao không dùng SELECT DB index làm ranh giới bảo mật?
24. Một hệ thống 20 pods, 40 connections/pod có bao nhiêu connections tiềm năng?
25. Cache hit rate cao có chứng minh dữ liệu đúng không?
26. Redis Pub/Sub khác Azure Service Bus như thế nào?
27. Java serialization có rủi ro gì khi dữ liệu từ Redis không tin cậy?
28. Vì sao Spring @Cacheable không tự giải quyết TTL/invalidation theo nghiệp vụ?
29. Cần quan sát những metrics nào khi sau deploy có lỗi Redis timeout?
30. Ba kiểm thử quan trọng nhất trước production là gì?

## Tài liệu tham khảo

- Microsoft Learn — *Azure Managed Redis*: https://learn.microsoft.com/azure/redis/
- Microsoft Learn — *Azure Cache for Redis*: https://learn.microsoft.com/azure/azure-cache-for-redis/
- Microsoft Learn — *Best practices for Azure Cache for Redis connections*: https://learn.microsoft.com/azure/azure-cache-for-redis/cache-best-practices-connection
- Microsoft Learn — *Microsoft Entra ID authentication for Azure Cache for Redis*: https://learn.microsoft.com/azure/azure-cache-for-redis/cache-azure-active-directory-for-authentication
- Microsoft Learn — *Azure Private Endpoint overview*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
- Microsoft Learn — *Azure Key Vault overview*: https://learn.microsoft.com/azure/key-vault/general/overview
- Microsoft Learn — *Microsoft Entra Workload ID on AKS*: https://learn.microsoft.com/azure/aks/workload-identity-overview
- Lettuce documentation: https://redis.github.io/lettuce/
- Spring Data Redis reference: https://docs.spring.io/spring-data/redis/reference/
- Spring Boot Redis configuration: https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis
- Redis documentation — *Security*: https://redis.io/docs/latest/operate/oss_and_stack/management/security/
- Redis documentation — *Caching*: https://redis.io/docs/latest/develop/use-cases/caching/
