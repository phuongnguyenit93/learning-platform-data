# Memorystore và các lựa chọn công cụ bộ nhớ đệm

Một dịch vụ Java `catalog-api` trên Cloud Run đọc sản phẩm từ Cloud SQL PostgreSQL. Khi chiến dịch bán hàng tăng lưu lượng gấp nhiều lần, hầu hết request chỉ đọc cùng vài nghìn sản phẩm. Nếu mọi request đều vào database, độ trễ, số kết nối và chi phí tăng dù dữ liệu không đổi. **Cache** lưu tạm kết quả đã tính/đọc để giảm tải nguồn dữ liệu chính.

Trên Google Cloud, cần chọn đúng **vị trí cache**: trong bộ nhớ ứng dụng (Caffeine), cache dùng chung qua **Memorystore for Valkey/Redis**, hoặc cache HTTP tại biên (**Cloud CDN**). **Memorystore** là dịch vụ quản lý bộ nhớ dữ liệu tốc độ cao, nhưng không tự bảo đảm cache luôn đúng, không tự giải quyết giao dịch đặt hàng và không phải bản sao lưu thay cho database.

Bài thuộc chương **Bigtable và Memorystore** của mô-đun `CLOUD_PROVIDERS_GCP`: từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run và cơ sở dữ liệu, người học cần lựa chọn dịch vụ, bảo vệ tài nguyên, phát hành an toàn và theo dõi độ tin cậy/chi phí. Ví dụ dùng Java 21, Valkey tương thích Redis và một nguồn dữ liệu giả lập để tránh đụng đến production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt cache **L1 trong process**, cache **L2 dùng chung**, cache **HTTP/CDN** và nguồn dữ liệu chuẩn.
2. Chọn giữa Memorystore for **Valkey**, **Redis Cluster**, **Redis** và cách xử lý hệ thống Memcached cũ.
3. Giải thích **cache-aside**, hit/miss, TTL, eviction, invalidation và consistency.
4. Viết ví dụ Java dùng **Lettuce** với cache-aside, TTL, xóa cache sau khi cập nhật và fallback khi cache lỗi.
5. Nhận diện **cache stampede**, hot key, dữ liệu nhạy cảm, lỗi kết nối và failover.
6. Thiết kế mạng riêng, IAM/TLS và client phù hợp cluster/non-cluster.
7. Đo hit ratio, latency, bộ nhớ, cost và xác định có nên dùng cache hay không.

## 1. Cache đặt ở đâu trong kiến trúc?

~~~mermaid
flowchart LR
    U["Web/mobile client"] --> CDN["Cloud CDN<br/>HTTP responses/assets"]
    CDN --> API["catalog-api<br/>Cloud Run/GKE"]
    API --> L1["L1: Caffeine<br/>mỗi process"]
    L1 -. "miss" .-> L2["L2: Memorystore<br/>Valkey/Redis"]
    L2 -. "miss" .-> DB[("Cloud SQL/Firestore/Bigtable<br/>nguồn dữ liệu chuẩn")]
    DB -->|"fill cache"| L2
~~~

| Lớp | Chia sẻ giữa replicas? | Phù hợp | Giới hạn |
| --- | --- | --- | --- |
| **In-process**: Caffeine, Map có TTL | **Không** | Dữ liệu rất nóng, nhỏ, chịu được trễ cập nhật vài giây | Mỗi Pod/instance có bản riêng; mất khi restart |
| **Distributed**: Memorystore | **Có**, giữa clients kết nối hợp lệ | Catalog, feature flags, kết quả query, rate-limit counters có điều kiện | Có network hop, phí bộ nhớ và rủi ro dữ liệu cũ |
| **HTTP edge**: Cloud CDN | Dùng chung theo điểm cache ở biên | Ảnh, CSS/JS, trang/response HTTP được phép cache | Không phù hợp dữ liệu riêng tư khi cache key/headers sai |
| **Nguồn dữ liệu chuẩn**: Cloud SQL/Firestore/Bigtable | Theo semantics riêng của DB | Tồn kho, đơn hàng, thanh toán, dữ liệu cần bền vững | Thường đắt/chậm hơn một cache hit |

**Nguyên tắc:** chỉ lưu vào cache dữ liệu **có thể tái tạo hoặc mất mà không làm sai nghiệp vụ**. Nếu cache rỗng sau restart, ứng dụng phải có đường đọc nguồn chuẩn và phục hồi an toàn.

## 2. Memorystore đang có những lựa chọn nào?

Google Cloud hiện có bốn dòng Memorystore. **Valkey** là lựa chọn đáng xem xét cho hệ thống mới cần cache tương thích Redis và khả năng scale theo shards.

| Dịch vụ | Kiến trúc | Khi phù hợp | Điểm cần tránh hiểu nhầm |
| --- | --- | --- | --- |
| **Memorystore for Valkey** | Hỗ trợ **Cluster Mode Enabled** (nhiều shards) và **Disabled** (một shard) | Cache mới; lựa chọn giữa single-shard và scale-out; IAM authentication/TLS theo cấu hình | Mode được chọn khi tạo instance, không chuyển trực tiếp qua lại |
| **Memorystore for Redis Cluster** | Redis cluster nhiều shards, có thể thêm replicas | Workload đã dùng Redis Cluster semantics, cần scale ngang | Client phải hỗ trợ cluster topology và chuyển hướng `MOVED` |
| **Memorystore for Redis** | Một primary, **Basic** hoặc **Standard** tier | Ứng dụng Redis standalone hiện có, dung lượng/throughput phù hợp | **Basic không HA**; Standard có replication và automatic failover; không đổi Basic ↔ Standard tại chỗ |
| **Memorystore for Memcached** | Memcached managed, key/value đơn giản | **Chủ yếu duy trì workload cũ trong giai đoạn chuyển đổi** | **Đã deprecated**; không khuyến nghị chọn mới |

**Mốc vòng đời Memcached (tính đến 19/11/2026):** từ **20/01/2026** không còn là dịch vụ được khuyến nghị; sau **01/02/2027**, project mới không thể tạo instance nếu chưa từng có instance; **31/01/2029** là ngày chấm dứt dịch vụ. Google khuyến nghị chuyển sang **Memorystore for Valkey**. Khi chuyển cần thử tương thích client, key types, eviction, TTL và hoạt động vận hành; **không giả định copy mọi command từ Memcached sang Valkey đều giống nhau**.

### 2.1. Khi nào không cần Memorystore?

- Cache chỉ vài trăm bản ghi, mỗi Cloud Run instance đọc rất nhanh, invalidation không nghiêm ngặt: cân nhắc **Caffeine với TTL ngắn**.
- Dữ liệu là response công khai/asset tĩnh từ Cloud Storage hoặc backend HTTP: cân nhắc **Cloud CDN**, `Cache-Control` và cache key đúng.
- Cần ghi giao dịch ACID/giữ tồn kho không âm: dùng **Cloud SQL, Spanner hoặc Firestore transaction** làm nguồn chuẩn.
- Cần key-value/time series rất lớn, dữ liệu **bền vững**: đánh giá **Bigtable**; Bigtable là database, **không phải bộ nhớ đệm thay thế trực tiếp cho Valkey**.

## 3. Cluster mode, replication và tính bền vững

Với **Memorystore for Valkey**:

- **Cluster Mode Enabled**: keyspace được chia theo hash slots, có thể scale ngang bằng nhiều shards; nên dùng **cluster-aware client**. Multi-key commands, scripts hoặc transactions thường phải dùng keys nằm **cùng hash slot**.
- **Cluster Mode Disabled**: một shard, đơn giản hơn cho ứng dụng đang dùng Redis/Valkey standalone và multi-key commands; không scale số shards ngang như mode Enabled.
- Có thể cấu hình **replicas** để tăng khả dụng/đọc theo khả năng hỗ trợ. Failover vẫn có thể **ngắt kết nối**, client phải reconnect/backoff.
- **Persistence** như AOF hoặc RDB là tính năng tùy cấu hình, có chi phí và giới hạn riêng; **replication không thay backup/nguồn dữ liệu chuẩn**.

Với **Memorystore for Redis** standalone, Basic tier phù hợp cache chịu mất dữ liệu; Standard tier có replica và automatic failover. HA giảm rủi ro gián đoạn, **không bảo đảm 0 giây downtime hoặc tuyệt đối không mất dữ liệu cache**.

| Vấn đề | Cách nghĩ đúng |
| --- | --- |
| Cache hit nhanh | Có thể giảm truy cập DB và p95 nhưng vẫn có network hop |
| Failover | Pool connections có thể lỗi; SDK phải reconnect |
| Mất key do TTL/eviction | Là hành vi bình thường, app phải xử lý miss |
| Mất toàn bộ cache | Có thể gây **thundering herd** vào DB nếu không giảm tốc fill |
| AOF/RDB | Hữu ích cho một số workload nhưng không làm cache trở thành database transaction mặc định |

## 4. Cache-aside: mẫu phổ biến cho ứng dụng Java

**Cache-aside** (*lazy loading*): ứng dụng hỏi cache trước. Nếu miss, đọc nguồn chuẩn, rồi ghi vào cache với **TTL**.

~~~mermaid
flowchart TD
    R["GET product(sku-01)"] --> C{"Cache có key?"}
    C -->|"Hit"| H["Trả giá trị cached"]
    C -->|"Miss"| DB["Đọc Cloud SQL/Firestore"]
    DB --> V{"Có dữ liệu?"}
    V -->|Có| SET["SET key EX TTL"]
    SET --> RETURN["Trả kết quả"]
    V -->|Không| N["Trả not found; negative-cache ngắn khi phù hợp"]
    C -. "Redis tạm lỗi" .-> FALL["Fallback nguồn chuẩn + cảnh báo"]
    FALL --> DB
~~~

- **Cache hit**: dữ liệu đã có, không gọi DB.
- **Cache miss**: thiếu/hết hạn/đã bị eviction, cần DB.
- **TTL**: thời gian sống tối đa của một bản ghi cache nếu không được refresh.
- **Eviction**: key bị đuổi khi bộ nhớ không đủ theo `maxmemory-policy`, có thể **trước khi TTL hết**.

Ví dụ key được quản lý theo namespace/version:

~~~text
catalog:v1:product:sku-01
catalog:v1:product:sku-02
catalog:v1:tenant:tenant-7:sku-03
~~~

Không dùng raw user input làm key chưa qua validate, không gộp dữ liệu của các tenants. Nếu API thay đổi schema cached value, **đổi key namespace/version** để tránh đọc nhầm serialization cũ.

## 5. TTL, invalidation và dữ liệu cũ

Chọn TTL theo **mức chịu dữ liệu cũ (staleness budget)**, không theo một số mặc định cho mọi business field.

| Dữ liệu | Gợi ý chính sách | Lý do |
| --- | --- | --- |
| Ảnh/asset gắn version | TTL dài / CDN | URL immutable, dễ cache |
| Catalog tên/mô tả | TTL vài chục giây/phút + invalidate khi sửa | Chấp nhận stale ngắn |
| Giá khuyến mãi | TTL ngắn + version, kiểm tra lại lúc checkout | Giá có thể đổi |
| Số tồn kho và tiền thanh toán | DB/transaction là nguồn quyết định | Cache không giữ invariant giao dịch |
| Kết quả 404 | **Negative cache** TTL rất ngắn khi phù hợp | Tránh miss dồn dập; tránh ẩn dữ liệu mới |
| Token, PII, secrets | Tránh hoặc có threat model, TLS, encryption, TTL và phân quyền | Cache không là vùng dữ liệu tự động an toàn |

### 5.1. Cập nhật database trước, xóa cache sau

~~~text
BEGIN / UPDATE DB / COMMIT
              |
              v
          DEL cache-key
              |
              v
  Request kế tiếp miss → đọc DB mới → fill cache
~~~

**Luôn commit nguồn chuẩn trước khi invalidate cache.** Nếu xóa cache trước rồi DB transaction rollback, cache có thể được fill dữ liệu cũ hoặc không cần thiết.

**Cảnh báo race:** cache-aside + `DEL` sau commit **không bảo đảm nhất quán tức thời**. Request A có thể đang đọc dữ liệu cũ từ DB, request B cập nhật DB và xóa key, rồi A lại fill cache bằng giá trị cũ. Với yêu cầu freshness cao, dùng **versioned keys, event-based invalidation có kiểm chứng, optimistic versions hoặc bỏ cache cho truy vấn quyết định**. TTL chỉ chặn thời gian stale tối đa trong điều kiện bình thường; không thay kiểm soát dữ liệu đúng.

### 5.2. Chống key đồng loạt hết hạn

Cho nhiều keys TTL hơi khác nhau (TTL + **jitter**, ví dụ 60–75 giây) để tránh hết hạn cùng lúc. Không đặt TTL ngẫu nhiên vô hạn; bám theo thời gian stale chấp nhận được. Các thay đổi bảo mật/quyền truy cập thường cần invalidation chủ động thay vì chờ TTL.

## 6. Java với Lettuce: cache-aside và fallback

Mẫu dưới đây dùng **Valkey standalone local** tương thích Redis protocol. Phần SOURCE giả lập Cloud SQL; production thay bằng repository thật, không dùng `ConcurrentHashMap` làm nguồn chuẩn. **Đây không phải client cấu hình sẵn cho Memorystore for Valkey Cluster Mode Enabled**; khi dùng cluster cần cluster-aware client, discovery endpoint và TLS/auth theo thiết lập instance.

### 6.1. Maven project

Cấu trúc:

~~~text
cache-lab/
├── pom.xml
└── src/main/java/lab/cache/CacheAsideDemo.java
~~~

`pom.xml` tối thiểu cho Java 21:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.cache</groupId>
  <artifactId>cache-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.lettuce</groupId>
      <artifactId>lettuce-core</artifactId>
      <version>6.6.0.RELEASE</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.4</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Phiên bản dependency chỉ phục vụ ví dụ: trước production hãy dùng bản mới nhất **đã kiểm duyệt** và quét lỗ hổng. Không nhúng Redis password/IAM token vào URI trong source.

### 6.2. CacheAsideDemo.java

~~~java
package lab.cache;

import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class CacheAsideDemo {
    // DEMO: Map đóng vai database nguồn. Production dùng repository/Cloud SQL.
    private static final Map<String, String> SOURCE = new ConcurrentHashMap<>();

    static String getProduct(String sku, RedisCommands<String, String> cache) {
        String key = "catalog:v1:product:" + sku;
        if (cache != null) {
            try {
                String hit = cache.get(key);
                if (hit != null) {
                    System.out.println("HIT " + sku);
                    return hit;
                }
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_READ_FAILED; use source");
            }
        }

        System.out.println("MISS " + sku);
        String fromSource = SOURCE.get(sku);
        if (fromSource != null && cache != null) {
            try {
                cache.setex(key, 30, fromSource); // TTL 30 giây.
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_FILL_FAILED; source value returned");
            }
        }
        return fromSource;
    }

    static void updateProduct(String sku, String value,
            RedisCommands<String, String> cache) {
        SOURCE.put(sku, value); // DEMO: production phải DB COMMIT trước.
        if (cache != null) {
            try {
                cache.del("catalog:v1:product:" + sku);
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_INVALIDATION_FAILED; stale until TTL");
            }
        }
    }

    public static void main(String[] args) {
        SOURCE.put("sku-01", "Laptop 16GB");
        RedisClient client = RedisClient.create("redis://127.0.0.1:6379");
        StatefulRedisConnection<String, String> connection = null;
        try {
            try {
                connection = client.connect();
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_UNAVAILABLE; source-only mode");
            }
            RedisCommands<String, String> cache =
                connection == null ? null : connection.sync();

            System.out.println(getProduct("sku-01", cache)); // MISS lần đầu.
            System.out.println(getProduct("sku-01", cache)); // HIT nếu cache khỏe.
            updateProduct("sku-01", "Laptop 32GB", cache);
            System.out.println(getProduct("sku-01", cache)); // Giá trị mới.
        } finally {
            if (connection != null) {
                connection.close();
            }
            client.shutdown();
        }
    }
}
~~~

**Các giới hạn có chủ đích:**

- Đây là **demo đồng bộ và một process**, chưa có pool/reconnect topology, metrics, tracing, jitter TTL hoặc coordination cho concurrent misses.
- `SOURCE` là Map; nếu cache chết, ví dụ vẫn đọc Map. Trong production, fallback là **database nguồn** và phải bảo vệ nó bằng timeouts, connection pool, backpressure.
- `updateProduct` minh họa **commit rồi DEL** nhưng không bảo đảm read-your-writes trong cuộc đua như mục 5.1.
- Lỗi khi cache hỏng không nên làm sai giao dịch ghi vào DB; với bộ đếm dùng cho **security/rate limit**, không được mặc định “fail-open”.

## 7. Lab local không tạo Memorystore tính phí

Cần Docker, Java 21, Maven và cổng local 6379 chưa được sử dụng. Chạy một **Valkey standalone** để học protocol:

~~~bash
# Chỉ mở cổng loopback trên máy lab, không public mạng.
docker run -d --name memorystore-cache-lab \
  -p 127.0.0.1:6379:6379 \
  valkey/valkey:8.1

docker exec memorystore-cache-lab valkey-cli ping
# Kỳ vọng: PONG
~~~

Tạo Maven project và file Java ở mục 6, rồi chạy:

~~~bash
mvn -B -ntp compile
mvn -q exec:java \
  -Dexec.mainClass=lab.cache.CacheAsideDemo

docker exec memorystore-cache-lab valkey-cli \
  TTL catalog:v1:product:sku-01

docker exec memorystore-cache-lab valkey-cli \
  GET catalog:v1:product:sku-01
~~~

Dữ liệu có thể hết hạn sau 30 giây, vì vậy kết quả `TTL = -2` hoặc `GET = nil` sau thời gian đó là bình thường. Không dùng các lệnh `FLUSHALL`/`FLUSHDB` trên instance production hoặc instance dùng chung.

**Thử lỗi an toàn trong lab:** dừng container local trước khi chạy Java, quan sát `CACHE_UNAVAILABLE` và vẫn lấy dữ liệu từ SOURCE; không dừng managed instance production để thử fallback. Dọn container:

~~~bash
docker stop memorystore-cache-lab
docker rm memorystore-cache-lab
~~~

Lab này chứng minh `GET → MISS → SETEX → HIT → DEL`. Không thể từ lab local suy ra đã kiểm thử Memorystore HA, PSC, IAM auth, TLS hoặc sharding thật.

## 8. Xem Memorystore hiện có bằng gcloud (chỉ đọc)

Phạm vi: project `PROJECT_ID`, region `asia-southeast1`. Cần quyền xem Memorystore; **chưa tạo hay đổi tài nguyên**:

~~~bash
gcloud auth list
gcloud config get-value project

# Valkey và phiên bản Memorystore quản lý bằng API mới:
gcloud memorystore instances list \
  --location=asia-southeast1 --project=PROJECT_ID

# Redis Basic/Standard tier:
gcloud redis instances list \
  --region=asia-southeast1 --project=PROJECT_ID

# Khi có một ID đã được xác minh:
gcloud memorystore instances describe INSTANCE_ID \
  --location=asia-southeast1 --project=PROJECT_ID

gcloud redis instances describe REDIS_INSTANCE_ID \
  --region=asia-southeast1 --project=PROJECT_ID
~~~

Không dùng `gcloud redis instances ...` để quản lý **Valkey**, hoặc dùng `gcloud memorystore instances ...` để kết luận đã liệt kê đầy đủ **Redis Basic/Standard**. **Redis Cluster** có nhóm CLI riêng (`gcloud redis clusters ...`); xác minh sản phẩm trước khi viết automation.

Để **tạo** Memorystore for Valkey trong lab cloud, phải chuẩn bị **VPC, Private Service Connect service connection policy**, vị trí/zone, node type, shard count, replica count, mode, IAM/TLS và Billing. Tránh copy một lệnh create thiếu PSC prerequisites rồi nghĩ là lỗi Redis/Java. **Node type shared-core-nano dành cho dev/test và không có SLA**; production cần sizing và HA thích hợp.

## 9. Bảo mật và kết nối từ Cloud Run/GKE/Compute Engine

Memorystore for Valkey sử dụng **Private Service Connect (PSC)**, không phơi endpoint ra Internet. Các sản phẩm Redis đời trước dùng mô hình network/authorized VPC khác; chọn đúng tài liệu của sản phẩm.

| Nguồn ứng dụng | Kiểm tra kết nối |
| --- | --- |
| **Cloud Run** | Dùng **Direct VPC egress** (khuyến nghị) hoặc Serverless VPC Access; subnet, route, firewall/network tags và PSC endpoint |
| **GKE** | Node/Pod egress tới VPC/PSC, NetworkPolicy, firewall, DNS và khả năng kết nối đa zone |
| **Compute Engine** | VM cùng mạng định tuyến được tới private endpoint; firewall/port và service account |
| **Local developer** | Không mở Redis public; dùng đường truy cập riêng được tổ chức chấp thuận hoặc emulator/local Valkey |
| **Shared VPC/cross-project** | Kiểm tra PSC project/network policy, quyền thiết lập endpoint và ingress/egress constraints |

### 9.1. Phân biệt IAM quản trị và IAM xác thực dữ liệu

- **Control plane IAM**: ai được create/describe/delete instances.
- **Data plane authentication**: ai có thể gửi lệnh `GET/SET` tới cache. **Không tự có** chỉ vì caller có IAM Viewer.
- **Valkey IAM authentication**: có thể dùng `roles/memorystore.dbConnectionUser` và access token qua `AUTH` khi được bật. Token ngắn hạn cần **refresh khi tạo kết nối mới**; không hard-code.
- **TLS in-transit**: phải **bật và cấu hình client**; IAM AUTH không tự đồng nghĩa mọi đường truyền đã mã hóa. Valkey hỗ trợ cả token auth/ACL theo cấu hình và tính năng được hỗ trợ.
- **Redis Basic/Standard**: cơ chế AUTH/TLS theo khả năng sản phẩm; không áp cơ chế Valkey IAM auth một cách máy móc.

Không lưu password, access tokens, session cookies, dữ liệu khách hàng nhạy cảm trong CLI history hoặc logs. VPC private endpoint **không thay thế authorization trong ứng dụng**.

### 9.2. Cluster-aware client và key slots

Với **Valkey Cluster Mode Enabled/Redis Cluster**, dùng client Redis/Valkey có hỗ trợ cluster discovery, xử lý `MOVED`, `ASK` và topology refresh. Kết nối vào discovery endpoint bằng client standalone có thể lỗi `MOVED` khi key nằm ở shard khác.

Ví dụ nhóm các keys phải thao tác cùng hash slot:

~~~text
cart:{user-123}:items
cart:{user-123}:totals
~~~

`{user-123}` là **hash tag** giúp các key trên cùng slot, nhưng tạo hot slot nếu một tenant chiếm phần lớn lưu lượng. Multi-key atomic operations chỉ trong **cùng slot** theo cluster semantics; đừng thiết kế cross-shard transaction chỉ bằng một lệnh `MULTI/EXEC`.

## 10. Những mô hình cache và bất biến dữ liệu

| Mô hình | Cách hoạt động | Khi dùng |
| --- | --- | --- |
| **Cache-aside** | Ứng dụng đọc cache, miss thì đọc DB và fill | Lựa chọn mặc định cho catalog/read-heavy |
| **Read-through** | Lớp cache/library tự gọi nguồn khi miss | Có framework/provider tương thích, đơn giản hóa ứng dụng |
| **Write-through** | Ghi đi qua cache/lớp phối hợp tới nguồn | Khi adapter có semantics rõ; đánh giá lỗi giữa hai writes |
| **Write-behind** | Ghi cache rồi đẩy DB bất đồng bộ | Chỉ khi chấp nhận rủi ro mất/chậm bền vững, có queue/replay |
| **L1 + L2** | Caffeine tại process và Valkey dùng chung | Lưu lượng đọc cực lớn; cần TTL/invalidation hai tầng |
| **Stale-while-revalidate** | Tạm trả bản cũ và refresh nền | Catalog/HTTP cache chấp nhận stale có giới hạn |

**Đừng gọi write-behind là giao dịch an toàn** cho đơn hàng/thanh toán: nếu cache mất dữ liệu trước khi đẩy DB, doanh nghiệp có thể mất giao dịch. Với dữ liệu quan trọng, **database là nguồn chuẩn**, còn cache chỉ tối ưu tốc độ.

## 11. Cache stampede, hot key và bảo vệ nguồn dữ liệu

**Cache stampede**: key nóng vừa hết TTL, hàng nghìn requests đồng thời miss rồi tất cả gọi DB.

Các cơ chế giảm rủi ro:

1. **TTL + jitter**: tránh hết hạn đồng loạt.
2. **Request coalescing / single-flight**: với cùng key, chỉ một request thực hiện fill ở mỗi instance.
3. **Distributed lock ngắn hạn** khi thật cần: `SET key value NX PX timeout` để một worker fill, nhưng cần ownership token và giải phóng an toàn; không dùng `DEL` vô điều kiện cho lock do worker khác nắm.
4. **Stale-while-revalidate** với các dữ liệu chịu stale, giới hạn tối đa.
5. **Negative caching** ngắn cho key không tồn tại (đừng cache kết quả permission-denied).
6. **Rate limit/backpressure/circuit breaker** khi cache không sẵn sàng, để database không sập bởi fallback bão hòa.

**Hot key** khác stampede: một key luôn được truy cập quá nhiều, dù không miss; có thể cần L1, sharding read load, copy immutable data hoặc xem lại client distribution.

### 11.1. Eviction và memory policy

Redis/Valkey có thể dùng chính sách như `allkeys-lru`, `volatile-ttl` hoặc `noeviction` tùy sản phẩm/instance. Nếu chọn `noeviction` và chạm giới hạn memory, writes mới có thể thất bại; nếu eviction được bật, keys có thể biến mất **trước TTL**. Theo dõi **evicted keys, hit/miss ratio, max memory** và dùng alerts. Không đặt cache như kho dữ liệu duy nhất nếu eviction/mất dữ liệu là không chấp nhận được.

## 12. Chọn cache cho từng tình huống

| Bài toán | Phương án nên thử trước | Lý do |
| --- | --- | --- |
| Static JS/CSS/images công khai | **Cloud CDN + Cache-Control** | Cache tại edge, giảm load ứng dụng |
| Catalog sản phẩm cho nhiều Cloud Run instances | **Memorystore for Valkey** cache-aside | Shared cache, TTL và invalidation |
| Cấu hình ít, thay đổi hiếm, mỗi Pod dùng | **Caffeine** | Không có network hop/phí instance managed |
| Session web | Valkey/Redis nếu cần shared state, **TTL và auth** | Không phụ thuộc memory một instance; tránh PII nhạy cảm |
| Rate limiting toàn dịch vụ | Valkey/Redis **atomic command/script** theo key slot | Cần thống nhất giữa replicas; thiết kế fail-open/closed theo rủi ro |
| Tồn kho/đặt hàng/thanh toán | **Cloud SQL/Spanner/Firestore transaction** | Giữ business invariant, không quyết định qua cache |
| Time-series/key-value bền vững quy mô lớn | **Bigtable** | Database throughput lớn, không phải bộ nhớ đệm |
| Hệ thống Memcached cũ | **Lập kế hoạch chuyển sang Valkey** | Memcached đang deprecated |

Với CDN, chỉ cache những response được phép chia sẻ; cấu hình `Cache-Control: private, no-store` cho dữ liệu tài khoản/giỏ hàng nếu không có thiết kế cache key và kiểm soát chặt. `Cache-Control`, `CDN-Cache-Control` và chế độ cache của backend quyết định hành vi; không nghĩ “thêm Cloud CDN” sẽ tự cache mọi API.

## 13. Quan sát hiệu quả, độ tin cậy và chi phí

Theo dõi cả **cache và DB**, vì cache có thể “khỏe” nhưng không tiết kiệm gì nếu mọi request vẫn đi DB.

| Nhóm | Số liệu | Câu hỏi vận hành |
| --- | --- | --- |
| **Hiệu quả** | Cache hit/miss count, hit ratio | Có thật giảm database reads? |
| **Latency** | p50/p95/p99 cache GET, end-to-end API | L2 có nhanh hơn fallback DB đủ đáng kể? |
| **Capacity** | Memory utilization, evictions, fragmentation, hot shards | Có thiếu RAM hoặc phân tải lệch? |
| **Connections** | Active/new connections, reconnect, timeout | Có connection storm sau deploy/failover? |
| **Reliability** | Failed requests, failover, errors, cache down duration | App có fallback an toàn và giới hạn tải? |
| **DB** | QPS, connections, CPU, p95 query latency | Cache hit có giảm áp lực thật? |
| **Cost** | Provisioned nodes/replicas, PSC network, logging, egress | Lợi ích > tổng chi phí cache? |

Ví dụ 8.000 hits và 2.000 misses trên tổng 10.000 lookups:

~~~text
Hit ratio = 8.000 / (8.000 + 2.000) = 80%

Chỉ số cần đo tiếp: DB QPS giảm bao nhiêu?
p95 API giảm bao nhiêu? Có stale-data incidents không?
~~~

Memorystore có metrics Cloud Monitoring về keyspace hits/misses, CPU, memory và connections theo sản phẩm. Với Valkey nhiều shards, xem **maximum utilization/hot node**, không chỉ average.

**Chi phí:** Memorystore là dịch vụ **provisioned capacity**: instance có thể bị tính tiền **ngay khi tạo dù không có request**. Valkey tính theo node type, số shards/replicas, region, persistence và các khoản networking/backup tương ứng. Redis Basic/Standard có mô hình dung lượng/giờ riêng. Thêm standby, nhiều replicas hoặc VPC connector có thể làm tổng phí tăng. Dùng Cloud Billing Reports và budget alerts; **budget thông báo không phải hard spending cap**.

## 14. Troubleshooting thường gặp

| Triệu chứng | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| Cloud Run timeout tới cache | Direct VPC egress/subnet/PSC/firewall thiếu | Network routes, endpoint, service connection policy |
| `MOVED` hoặc `CROSSSLOT` | Dùng standalone client hay keys khác slots với cluster | Cluster client/topology/hash tags |
| `NOAUTH`/`WRONGPASS` | AUTH token, IAM principal, TLS/config sai | Data-plane auth, token refresh, TLS handshake |
| `READONLY` sau failover | Client còn nối replica hoặc endpoint sai | Reconnect/refresh topology, backoff |
| `OOM` hoặc writes rejected | Memory đầy, `noeviction` hoặc key sizes lớn | Memory/evictions, maxmemory-policy, sizing |
| Hit ratio thấp | TTL quá ngắn, key version không thống nhất, cardinality cao | Key naming, TTL, sampling hits/misses |
| Giá trị cũ kéo dài | Race cache-aside, DEL lỗi, TTL dài | Invalidation logs, versioning, freshness budget |
| DB bị quá tải khi cache fail | Fallback đồng thời không giới hạn | Circuit breaker, coalescing, backpressure |
| Cache latency tăng dù CPU trung bình thấp | Một shard/hot key, connection pool nghẽn | Max per-node metrics, load test |
| Hóa đơn tăng khi traffic thấp | Instance/replicas provisioned, network connector | Billing SKU, instance sizing, cleanup |

**Không sửa kết nối bằng cách mở cổng Redis ra Internet**; ưu tiên VPC/PSC/TLS và quyền tối thiểu. Cũng không ghi `AUTH` token vào logs để chẩn đoán.

## 15. Tình huống tổng hợp: tối ưu Catalog API

**Giả định:** Java `catalog-api` trên Cloud Run có 20.000 request/phút, 90% là GET product, nguồn chuẩn là Cloud SQL PostgreSQL. Nhóm muốn giảm p95 từ 250 ms nhưng không cho phép cache quyết định tồn kho khi checkout.

Thiết kế:

~~~mermaid
flowchart TD
    API["GET /products/:sku"] --> L1{"Caffeine (L1)"}
    L1 -->|"miss"| L2{"Valkey (L2)"}
    L2 -->|"miss"| DB["Cloud SQL SELECT"]
    DB -->|"fill L2 + L1"| OUT["Response"]
    L1 -->|"hit"| OUT
    L2 -->|"hit + fill L1"| OUT
    CHANGE["Admin updates product"] --> COMMIT["Cloud SQL COMMIT"]
    COMMIT --> INVALIDATE["Invalidate L2 + gửi event invalidate L1"]
~~~

**Kế hoạch triển khai:**

1. Đo baseline DB QPS, p95 API, query latency và chi phí.
2. Cache **mô tả/ảnh/thông tin công khai**, TTL ngắn có jitter; không cache số lượng tồn kho làm điều kiện checkout.
3. Thêm L2 Valkey với cache-aside; L1 chỉ dùng khi thực sự có lợi và chấp nhận stale thêm.
4. Commit DB rồi invalidate; theo dõi race, key version và lost invalidation.
5. Tạo dashboard hit/miss, memory, evictions, cache errors và DB traffic; giả lập cache down ở staging.
6. Giới hạn fallback bằng pool/circuit breaker, giữ SLO và rollback nếu có stale dữ liệu hoặc p95 không cải thiện.
7. Tính tổng chi phí Valkey nodes/replicas/PSC, Cloud Run egress và Cloud SQL giảm tải.

**Tiêu chí thành công:** hit ratio/latency đáp ứng SLO, DB QPS giảm, cache failure không làm hệ thống mất giao dịch và chi phí tổng không vượt ngân sách. Không kết luận chỉ dựa vào “GET Redis rất nhanh”.

## 16. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Cache-aside local.** Chạy lab mục 7, quan sát MISS → HIT → update → MISS. Sau 30 giây, kiểm tra TTL/GET.

*Đạt:* dữ liệu lấy từ SOURCE khi miss, TTL có hiệu lực và giá trị mới sau invalidation.

**Bài 2 — Cache down.** Dừng Valkey local trước khi chạy Java.

*Đạt:* nguồn giả lập vẫn trả dữ liệu; production cần timeout và giới hạn fallback.

**Bài 3 — TTL và độ tươi.** Giá sản phẩm đổi sau 10 giây, TTL đang là 5 phút. Điều gì sai?

*Đáp án:* Có thể stale 5 phút nếu invalidation bị mất; giảm TTL, invalidate chủ động, versioning, kiểm tra giá tại checkout.

**Bài 4 — Stampede.** 10.000 requests cùng miss một key, DB chịu tải lớn. Nêu hai biện pháp.

*Đáp án:* Single-flight/coalescing; TTL jitter và stale-while-revalidate khi cho phép; thêm bounded fallback.

**Câu 5.** Basic tier Redis có automatic failover không?

*Đáp án:* Không. Standard tier có replication/automatic failover.

**Câu 6.** Valkey Cluster Mode Enabled có thể dùng standalone client để truy cập mọi shard không?

*Đáp án:* Không đáng tin cậy; phải dùng cluster-aware client/slot routing.

**Câu 7.** Cache và database có nhất quán tức thời sau `COMMIT → DEL` không?

*Đáp án:* Không bảo đảm; race fill cache vẫn có thể tạo dữ liệu cũ.

**Câu 8.** Memorystore for Memcached còn được khuyến nghị cho hệ thống mới năm 2026?

*Đáp án:* Không; đã deprecated 20/01/2026, cần kế hoạch migrate sang Valkey hoặc dịch vụ phù hợp.

**Câu 9.** Cloud Run scale về 0 có nghĩa Memorystore tự dừng tính phí không?

*Đáp án:* Không. Memorystore tính phí capacity đã provision ngay cả khi idle.

**Câu 10.** IAM Viewer trên project có tự cấp quyền gửi `GET` vào Valkey instance không?

*Đáp án:* Không. IAM quản trị khác data-plane authentication; Valkey IAM auth phải bật và cấp quyền connect thích hợp.

**Câu 11.** Khi cache chứa số tồn kho, có thể dùng `DECR` để đảm bảo đặt hàng không vượt tồn kho trong Cloud SQL?

*Đáp án:* Không. Nguồn chuẩn và transaction nghiệp vụ phải giữ invariant; cache counter không tự atomic với DB.

**Câu 12.** Một response có thông tin cá nhân có nên cache bằng `Cache-Control: public` không?

*Đáp án:* Không. Có nguy cơ lộ dữ liệu qua shared cache/CDN; dùng private/no-store hoặc thiết kế riêng đã được kiểm duyệt.

**Câu 13.** Khi key miss nhiều, có nên chỉ tăng số replicas Redis mà không xem nguyên nhân?

*Đáp án:* Không. Kiểm tra TTL, key naming, eviction, traffic distribution, upstream DB và cost.

**Câu 14.** HA Valkey/Redis có giữ nguyên TCP connection khi failover?

*Đáp án:* Không bảo đảm; client phải reconnect, refresh topology và bounded retry.

## 17. Checklist production và kết luận

- [ ] Phân loại dữ liệu được cache theo **freshness, bảo mật và nguồn chuẩn**.
- [ ] Chọn L1/Caffeine, L2/Memorystore, CDN hoặc DB theo workload thay vì một giải pháp cho mọi thứ.
- [ ] Chọn đúng dòng Memorystore, mode cluster, shard/replica, HA và roadmap Memcached.
- [ ] Mỗi key có namespace/version, TTL và invalidation được thiết kế.
- [ ] Không cache dữ liệu giao dịch làm nguồn quyết định duy nhất.
- [ ] Có chống stampede, hot key, fallback với timeouts/backpressure.
- [ ] Redis/Valkey cluster dùng cluster-aware client và xử lý topology changes.
- [ ] Cloud Run/GKE/VM có VPC/PSC path hợp lệ, TLS và data-plane auth theo sản phẩm.
- [ ] Không lưu password/PII/tokens trong cache hoặc logs mà thiếu threat model.
- [ ] Có load test: hits/misses, p95/p99, DB QPS, key eviction và failover.
- [ ] Có dashboards CPU/memory/connection/evictions, alerts và quy trình rollback.
- [ ] Đã tính chi phí provisioned nodes/replicas/network và dự kiến dọn lab đúng quyền.

**Kết luận:** Cache giúp giảm latency và tải database, nhưng **chỉ là bản sao có thể hết hạn, bị đuổi hoặc mất khi sự cố**. Với ứng dụng Java trên Google Cloud, lựa chọn hợp lý thường bắt đầu từ **cache-aside + TTL + invalidation + nguồn dữ liệu chuẩn**, rồi thêm Caffeine, Memorystore for Valkey hoặc Cloud CDN khi benchmark chứng minh lợi ích. Tính đúng dữ liệu, khả năng fallback, bảo mật kết nối và chi phí phải được kiểm chứng cùng hiệu năng.

## Tài liệu tham khảo chính thức

- [Memorystore overview](https://cloud.google.com/memorystore/docs)
- [Memorystore for Valkey overview](https://cloud.google.com/memorystore/docs/valkey/product-overview)
- [Valkey: Cluster Mode Enabled vs Disabled](https://cloud.google.com/memorystore/docs/valkey/cluster-mode-enabled-and-disabled)
- [Valkey: Networking](https://cloud.google.com/memorystore/docs/valkey/networking)
- [Valkey: IAM authentication](https://cloud.google.com/memorystore/docs/valkey/about-iam-auth)
- [Valkey: Persistence](https://cloud.google.com/memorystore/docs/valkey/persistence-overview)
- [Memorystore for Redis Cluster overview](https://cloud.google.com/memorystore/docs/cluster/memorystore-for-redis-cluster-overview)
- [Memorystore for Redis: Basic vs Standard tiers](https://cloud.google.com/memorystore/docs/redis/redis-tiers)
- [Memorystore for Memcached deprecation timeline](https://cloud.google.com/memorystore/docs/memcached/deprecation/memcached)
- [Connect Memorystore Redis from Cloud Run](https://cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/connecting-vpc)
- [Cloud CDN caching overview](https://cloud.google.com/cdn/docs/caching)
- [Memorystore for Valkey pricing](https://cloud.google.com/memorystore/valkey/pricing)
- [Memorystore for Redis pricing](https://cloud.google.com/memorystore/docs/redis/pricing)

