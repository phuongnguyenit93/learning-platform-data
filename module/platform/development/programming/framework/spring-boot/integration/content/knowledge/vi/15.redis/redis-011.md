# Lỗi mạng, chuyển đổi nút và chính sách khi Redis không sẵn sàng

Redis thường xuất hiện trong hệ thống Spring Boot như bộ nhớ đệm, nơi lưu phiên, bộ đếm giới hạn tốc độ, khoá phân tán, nơi chống xử lý trùng lặp hoặc thành phần trung gian chuyển thông điệp. Mỗi vai trò kéo theo một yêu cầu khác nhau khi Redis gặp sự cố. Một ứng dụng có thể tiếp tục phục vụ khi mất cache, nhưng không thể mặc nhiên bỏ qua lỗi của hệ thống giữ khoá thanh toán hay kiểm soát truy cập.

Bài học thuộc chương **Redis** của học phần **SPRING_BOOT_INTEGRATION**: tổ chức tích hợp hệ thống Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration; chú trọng cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát luồng tích hợp thực tế.

## 1. Mục tiêu và phạm vi

Sau bài này, người học có thể:

1. Phân biệt lỗi kết nối, timeout, lỗi điều hướng Cluster, gián đoạn chuyển primary và lỗi dữ liệu/cấu hình.
2. Giải thích hành vi của ứng dụng khi Redis Sentinel hoặc Redis Cluster chuyển nút, kể cả cửa sổ mất ghi và nguy cơ mất bản ghi vừa được xác nhận.
3. Chọn chính sách **fail-open**, **fail-closed**, **fallback**, **degrade** theo hợp đồng nghiệp vụ của từng chức năng.
4. Cấu hình Redis client trong Spring Boot, cô lập lớp tích hợp Redis, đặt thời gian chờ và giới hạn retry để tránh lỗi lan sang cơ sở dữ liệu.
5. Kiểm thử kịch bản mất kết nối, chuyển nút và phục hồi; quan sát được tác động tới độ trễ, lỗi nghiệp vụ và tải của dịch vụ phụ thuộc.

**Phạm vi ví dụ:** Spring Boot 3.x, Spring Data Redis, Lettuce và cơ sở dữ liệu quan hệ làm nguồn dữ liệu chuẩn cho ví dụ cache giá hiển thị. Những tên thuộc tính cấu hình và API cụ thể cần được đối chiếu với phiên bản Spring Boot đang triển khai.

## 2. Sự cố Redis tác động đến luồng tích hợp thế nào?

Một lời gọi Redis đi qua nhiều lớp: service nghiệp vụ, Redis adapter, client, kết nối TCP/TLS, proxy hoặc load balancer, rồi mới đến nút Redis. Lỗi ở bất kỳ lớp nào đều có thể bộc lộ dưới dạng timeout; ngược lại, timeout ở phía client không chứng minh Redis chưa thực thi lệnh.

~~~mermaid
flowchart TD
    HTTP["HTTP request / message consumer"] --> APP["Spring Boot business service"]
    APP --> POLICY{"Vai trò của Redis?"}
    POLICY -->|Cache có DB nguồn| CACHE["Redis cache adapter"]
    POLICY -->|Khoá / idempotency / bảo mật| CRITICAL["Redis coordination adapter"]
    CACHE --> REDIS[("Redis primary / Cluster")]
    CRITICAL --> REDIS
    CACHE -->|Miss hoặc lỗi được phép fallback| DB[("Database nguồn chuẩn")]
    CRITICAL -->|Không xác định được trạng thái| STOP["Từ chối / hoãn / dùng cơ chế dự phòng đủ mạnh"]
    DB --> RESPONSE["Phản hồi theo hợp đồng nghiệp vụ"]
    REDIS --> RESPONSE
~~~

Có bốn nhóm hiện tượng cần tách riêng:

| Hiện tượng | Dấu hiệu thường gặp | Ý nghĩa đối với ứng dụng |
|---|---|---|
| Không thiết lập được kết nối | DNS lỗi, TCP refused/reset, TLS hoặc xác thực thất bại, connection timeout | Có thể chưa gửi lệnh; lỗi xác thực và sai cấu hình thường không tự hết nhờ retry. |
| Gửi lệnh nhưng hết thời gian chờ | Command timeout, kết nối bị cắt giữa lúc chờ phản hồi | **Kết quả không xác định**: lệnh có thể đã chạy, chưa chạy hoặc đã chạy nhưng phản hồi bị mất. |
| Redis đang chuyển vai trò hoặc cấu trúc | Replica được nâng lên primary, nút cũ mất kết nối; MOVED, ASK, TRYAGAIN, CLUSTERDOWN trong Cluster | Client cần khám phá đúng đích và có thể phải kết nối lại; một số thao tác đang bay sẽ thất bại. |
| Redis trả lỗi hợp lệ | Sai kiểu dữ liệu (WRONGTYPE), hết bộ nhớ theo chính sách, lỗi ACL, CROSSSLOT | Đây là lỗi hợp đồng/cấu hình/dữ liệu hoặc điều kiện tài nguyên; không nên che giấu như cache miss thông thường. |

Các exception Spring Data Redis có thể gặp gồm **RedisConnectionFailureException**, **QueryTimeoutException** và **RedisSystemException**; ngoại lệ từ Lettuce thường được Spring dịch sang họ **DataAccessException**. Không nên gắn chính sách nghiệp vụ với đúng một tên exception: cần kiểm tra nguyên nhân gốc và phân biệt sự cố hạ tầng với lỗi lập trình, dữ liệu hoặc quyền truy cập.

### 2.1. Tình huống quan trọng: timeout không đồng nghĩa thất bại

Giả sử ứng dụng gửi lệnh tăng bộ đếm **INCR**. Redis thực thi lệnh, nhưng gói phản hồi bị mất do chuyển nút mạng. Ứng dụng thấy timeout và gửi lại **INCR**. Bộ đếm tăng hai lần, dù yêu cầu nghiệp vụ chỉ có một lần.

Tương tự, ghi nhận một khoá idempotency rồi timeout có thể khiến caller không biết khoá đã được tạo hay chưa. Với cache đọc thuần tuý, gọi lại thường có thể chấp nhận; với lệnh có tác dụng phụ, **không retry mù**. Cần idempotency key, điều kiện ghi có tính nguyên tử, trạng thái chuẩn trong DB hoặc bước đối soát dựa trên mã yêu cầu nghiệp vụ.

Một lệnh Lua chạy nguyên tử trên một primary ở thời điểm thực thi, nhưng việc client nhận timeout vẫn có thể để lại kết quả không rõ ràng; Lua cũng không biến replication bất đồng bộ thành giao dịch bền vững xuyên failover.

## 3. Cơ chế chuyển nút: Standalone, Sentinel và Cluster

| Mô hình | Chuyển nút | Điều cần chuẩn bị ở phía Spring Boot |
|---|---|---|
| Redis standalone | Không có tự động bầu primary từ riêng Redis standalone; việc đổi endpoint do hạ tầng bên ngoài xử lý nếu có | Phát hiện mất kết nối, chính sách fallback, endpoint ổn định và quy trình phục hồi. |
| Redis Sentinel | Sentinel quan sát primary/replica, xác nhận lỗi qua quorum và tổ chức chọn replica làm primary mới khi đạt điều kiện | Cấu hình tên primary logic và danh sách Sentinel; client phải khám phá primary mới và kết nối lại. |
| Redis Cluster | Dữ liệu chia theo 16.384 hash slot; mỗi primary giữ một nhóm slot, có thể có replica; cluster tự phát hiện failover khi đủ điều kiện | Client hiểu topology, tự xử lý MOVED/ASK, cập nhật slot mapping và không giả định mọi key nằm trên cùng nút. |
| Dịch vụ Redis được quản lý | Nhà cung cấp có thể đổi primary/endpoint/proxy hoặc thực hiện failover theo cơ chế riêng | Theo tài liệu nhà cung cấp về DNS, TLS, authentication, endpoint, failover và giới hạn kết nối. |

### 3.1. Sentinel: có bầu primary nhưng vẫn có khoảng gián đoạn

Ví dụ triển khai có một primary, hai replica và ba Sentinel ở các miền lỗi thích hợp:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot + Lettuce
    participant S as Sentinel quorum
    participant P as Primary cũ
    participant R as Replica
    App->>P: Ghi hoặc đọc
    P--xApp: Mất kết nối / không phản hồi
    S->>S: Xác nhận primary không sẵn sàng
    S->>R: Chọn và nâng replica thành primary
    App->>S: Hỏi primary hiện tại
    S-->>App: Địa chỉ primary mới
    App->>R: Kết nối lại và thực hiện lệnh mới
~~~

Cần phân biệt **quorum để đánh giá primary đã mất** với yêu cầu đủ đa số Sentinel cho việc cho phép tiến hành failover. Một Sentinel đơn lẻ không mang lại độ sẵn sàng cao cho toàn bộ quy trình.

Những yêu cầu đang xử lý trong lúc chuyển vai trò vẫn có thể timeout hoặc bị từ chối. Không có lời hứa rằng mọi lệnh được client gửi đều được tự động phát lại an toàn; ứng dụng phải biết lệnh nào có thể retry.

**Điểm nhất quán dữ liệu:** Redis replication phổ biến là bất đồng bộ. Primary cũ có thể trả thành công cho client trước khi replica nhận thay đổi. Nếu replica ấy được nâng lên, một ghi đã được xác nhận vẫn có nguy cơ không xuất hiện trên primary mới. Các cơ chế như AOF, yêu cầu số replica tối thiểu hay **WAIT** có thể giảm một số rủi ro trong điều kiện cụ thể, nhưng không tương đương với bảo đảm giao dịch đồng bộ, bền vững tuyệt đối sau mọi kiểu lỗi.

### 3.2. Cluster: thay đổi primary và thay đổi vị trí hash slot

Trong Cluster, một số phản hồi có ý nghĩa điều hướng:

- **MOVED**: slot đã được chuyển tới nút khác; client cần cập nhật địa chỉ đích/topology.
- **ASK**: điều hướng tạm thời trong quá trình di chuyển slot; client thực hiện thủ tục ASKING đối với đích theo giao thức.
- **TRYAGAIN**: thao tác tạm thời chưa thể đáp ứng, có thể xảy ra khi slot đang dịch chuyển.
- **CLUSTERDOWN**: cluster không thể phục vụ thao tác theo trạng thái hiện tại.
- **CROSSSLOT**: thao tác nhiều key đặt ở các slot khác nhau; đây là vấn đề thiết kế key, không phải lỗi mạng. Chỉ sử dụng hash tag như **order:{123}:state** và **order:{123}:lock** khi thật sự cần cùng slot và hiểu tác động phân phối tải.

Lettuce có khả năng xử lý redirection và làm mới topology, nhưng vẫn cần giới hạn số redirect, thời gian chờ và cấu hình refresh phù hợp với môi trường. Việc có replica không bảo đảm một vùng mạng bị cô lập vẫn ghi được: Cluster cần điều kiện đồng thuận/bầu chọn và phần lớn primary phù hợp; tính sẵn sàng phụ thuộc mô hình phân vùng và kết nối thực tế.

**Đọc từ replica** có thể trả dữ liệu cũ do độ trễ replication. Không sử dụng replica read như một cách sửa lỗi kết nối nếu yêu cầu nghiệp vụ đòi đọc thấy ngay ghi vừa thực hiện.

## 4. Quyết định chính sách khi Redis không sẵn sàng

Không thể áp dụng cùng một quy tắc cho mọi ứng dụng. Câu hỏi đầu tiên là: **Redis đang lưu bản sao phục vụ tốc độ, hay đang giữ một điều kiện đúng/sai mà nghiệp vụ phụ thuộc?**

| Vai trò Redis | Khi Redis lỗi | Chính sách điển hình | Cảnh báo chính |
|---|---|---|---|
| Cache-aside cho danh mục/giá hiển thị | Bỏ qua cache, đọc từ DB nguồn chuẩn, trả kết quả; ghi lại cache theo kiểu best effort | **Fail-open đối với cache**, với giới hạn tải DB | Giá có thể cũ trong TTL; phải xác nhận lại ở bước thanh toán. |
| Cache để tăng tốc truy vấn nhưng DB chịu tải giới hạn | Đọc DB qua bulkhead/rate limit; khi vượt sức chứa, trả 429/503 hoặc dữ liệu stale đã được cho phép | **Degrade có kiểm soát** | Fallback vô hạn có thể làm sập DB. |
| Trạng thái thu hồi token/quyền truy cập | Chuyển sang nguồn xác thực thay thế đáng tin cậy hoặc từ chối thao tác nhạy cảm | **Fail-closed** khi không xác minh được quyền | Không coi lỗi Redis là “token hợp lệ” hay “chưa bị thu hồi”. |
| Rate limiting bảo vệ đăng nhập/API nhạy cảm | Dùng tầng kiểm soát dự phòng đủ mạnh hoặc từ chối có kiểm soát | Thường **fail-closed** | Fail-open cho phép lạm dụng khi bộ đếm mất tác dụng. |
| Rate limiting tiện ích cho API ít rủi ro | Có thể cho qua trong giới hạn với local limiter tạm thời | Có thể **fail-open/degrade** theo SLO | Local limiter không có tầm nhìn toàn cụm. |
| Khoá phân tán bảo vệ cập nhật quan trọng | Dừng thao tác hoặc chuyển qua ràng buộc giao dịch/khóa DB | **Fail-closed** | Mất Redis không đồng nghĩa lấy được khóa. |
| Idempotency chống tạo đơn/thanh toán trùng | Dùng unique constraint hoặc bảng idempotency bền vững; nếu không có, từ chối/hoãn | **Fail-closed** nếu không chứng minh an toàn | Timeout và failover có thể gây xử lý trùng. |
| Redis Pub/Sub chuyển sự kiện | Phân biệt sự kiện có thể mất với sự kiện bắt buộc giao | Với sự kiện quan trọng, chuyển sang outbox + broker bền vững | Pub/Sub không lưu lại thông điệp cho subscriber đang offline. |

**Fail-open** nghĩa là chấp nhận tiếp tục một hành vi dù một bước kiểm tra hoặc tối ưu không hoạt động. **Fail-closed** nghĩa là không cho phép hành vi phụ thuộc vào trạng thái chưa xác minh. **Fallback** là đường xử lý thay thế có hợp đồng rõ ràng; **degrade** là hạ chất lượng có chủ đích, ví dụ trả giá tham khảo hoặc giới hạn tính năng.

Các lựa chọn trên là ví dụ, phải được quyết định theo mức độ quan trọng của dữ liệu, nguồn sự thật, yêu cầu pháp lý/bảo mật và SLO. Mỗi endpoint nên chỉ rõ mã lỗi, khả năng retry, trạng thái giao dịch và thông điệp trả caller khi không thể tiếp tục.

## 5. Cấu hình client Spring Boot để phát hiện lỗi có giới hạn

Các ví dụ sau dùng thuộc tính của Spring Boot 3.x. Mỗi môi trường chọn **một** cách khai báo kết nối phù hợp: standalone, Sentinel hoặc Cluster.

### 5.1. Kết nối đơn / endpoint của dịch vụ quản lý

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: redis.internal
      port: 6379
      connect-timeout: 300ms
      timeout: 700ms
~~~

- **connect-timeout**: giới hạn thời gian thiết lập kết nối. Nó không thay thế thời gian chờ cho lệnh.
- **timeout**: ngưỡng thời gian cho thao tác Redis trong cấu hình Spring Boot. Giá trị phải đặt trong ngân sách độ trễ của toàn bộ request.
- **Lettuce**: client mạng bất đồng bộ bên dưới, được Spring Data Redis dùng để tự quản lý kết nối, reconnect và các thao tác liên quan đến topology khi được cấu hình thích hợp.

Các số 300 ms và 700 ms chỉ để minh hoạ. Chọn từ độ trễ đo thực tế, khoảng cách vùng mạng và yêu cầu đầu cuối; timeout quá ngắn tạo lỗi giả, timeout quá dài làm cạn worker/thread và lan sự cố.

### 5.2. Sentinel

~~~yaml
spring:
  data:
    redis:
      sentinel:
        master: redis-primary
        nodes:
          - "sentinel-1.internal:26379"
          - "sentinel-2.internal:26379"
          - "sentinel-3.internal:26379"
      connect-timeout: 300ms
      timeout: 700ms
~~~

**redis-primary** là tên master logic do Sentinel quản lý, không phải tên host tuỳ ý của Spring. Các địa chỉ Sentinel phải truy cập được từ ứng dụng, kể cả sau chuyển nút. Cấu hình ACL, mật khẩu, TLS cho Redis và Sentinel cần đối chiếu với mô hình triển khai; không ghi bí mật trực tiếp vào repository.

### 5.3. Cluster

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - "redis-node-1.internal:6379"
          - "redis-node-2.internal:6379"
          - "redis-node-3.internal:6379"
        max-redirects: 5
      connect-timeout: 300ms
      timeout: 700ms
~~~

Các node trên là **seed** để client khám phá topology; chúng không phải toàn bộ danh sách primary bắt buộc. Với hệ thống thường xuyên reshard hoặc chuyển nút, cân nhắc cơ chế **adaptive topology refresh** và **periodic refresh** của Lettuce Cluster. Chọn khoảng refresh theo nhịp chuyển đổi và chi phí truy vấn topology; giới hạn redirect giúp tránh lặp điều hướng không kết thúc.

Kiểm tra tên host mà Cluster công bố cho client: kết nối seed thành công nhưng các địa chỉ nút nội bộ không định tuyến được từ Kubernetes hoặc VPC khác vẫn gây lỗi sau MOVED/failover.

### 5.4. Ngân sách thời gian theo luồng

Ví dụ một HTTP endpoint có hạn mức 1.500 ms:

| Thành phần | Ví dụ ngân sách |
|---|---:|
| Redis cache lookup | Tối đa 200–400 ms |
| Truy vấn DB fallback | Tối đa 700–900 ms |
| Xử lý hợp đồng, network HTTP, serialization | Phần thời gian còn lại |
| Retry | Chỉ trong tổng hạn mức, không cộng thời gian chờ vô hạn |

Đây là mô hình phân bổ, không phải công thức cấu hình cố định. Nếu còn 200 ms cho cả request, không nên bắt đầu một retry Redis có timeout 700 ms. Có thể truyền deadline từ request vào tầng xử lý hoặc để timeout/bulkhead bảo đảm tổng thời gian chờ không vượt SLO.

## 6. Mẫu cache-aside: cô lập Redis khỏi nghiệp vụ

Giả sử một trang sản phẩm cần **giá hiển thị**. DB là nguồn chuẩn; Redis chỉ giữ chuỗi giá đã tính để giảm tải. Khi Redis lỗi, trang vẫn được phục vụ bằng DB nếu DB còn đủ năng lực. Giá dùng để thanh toán phải được kiểm tra từ dữ liệu chuẩn tại bước xác nhận đơn.

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DisplayPriceService {
    private static final Logger log =
            LoggerFactory.getLogger(DisplayPriceService.class);

    private final StringRedisTemplate redis;
    private final PriceRepository prices;
    private final Counter readFailures;
    private final Counter writeFailures;

    public DisplayPriceService(
            StringRedisTemplate redis,
            PriceRepository prices,
            MeterRegistry meterRegistry) {
        this.redis = redis;
        this.prices = prices;
        this.readFailures = Counter.builder("integration.redis.failures")
                .tag("operation", "read")
                .register(meterRegistry);
        this.writeFailures = Counter.builder("integration.redis.failures")
                .tag("operation", "write")
                .register(meterRegistry);
    }

    public BigDecimal findDisplayPrice(String sku) {
        String key = "display-price:" + sku;

        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                try {
                    return new BigDecimal(cached);
                } catch (NumberFormatException invalidCacheValue) {
                    log.warn("Giá trị cache sai định dạng, key={}", key);
                }
            }
        } catch (DataAccessException redisError) {
            readFailures.increment();
            log.warn("Không đọc được Redis, key={}, cause={}",
                    key, redisError.getClass().getSimpleName());
        }

        // Không bắt lỗi DB thành lỗi Redis: DB là nguồn dữ liệu chuẩn.
        BigDecimal price = prices.findDisplayPrice(sku)
                .orElseThrow(() -> new NoSuchElementException("SKU not found"));

        try {
            // TTL phân tán để giảm nhiều key đồng thời hết hạn.
            long ttlSeconds = ThreadLocalRandom.current().nextLong(50, 71);
            redis.opsForValue().set(
                    key, price.toPlainString(), Duration.ofSeconds(ttlSeconds));
        } catch (DataAccessException redisError) {
            writeFailures.increment();
            log.warn("Không ghi được cache, key={}, cause={}",
                    key, redisError.getClass().getSimpleName());
        }

        return price;
    }
}

// Adapter DB do ứng dụng cung cấp, ví dụ triển khai qua Spring Data JPA.
interface PriceRepository {
    Optional<BigDecimal> findDisplayPrice(String sku);
}
~~~

Trong ví dụ:

1. Cache hit trả nhanh. Cache miss hoặc lỗi đọc Redis chuyển sang nguồn chuẩn.
2. Lỗi chuyển đổi dữ liệu cache không được coi là giá hợp lệ.
3. Lỗi DB vẫn được truyền lên tầng xử lý HTTP, vì không còn nguồn chuẩn để trả lời.
4. Lỗi ghi cache không đảo ngược kết quả đọc DB; chỉ ghi nhận metric/log.
5. TTL có độ lệch giảm đồng loạt hết hạn nhưng **không** tự giải quyết cache stampede, dữ liệu cũ hoặc giới hạn tải DB.

**Giới hạn quan trọng:** ví dụ phù hợp với cache chỉ để tăng tốc. Không sao chép catch-and-continue này sang bước ghi khoá phân tán, xác thực hoặc chống trùng thanh toán. Với traffic lớn, nên đặt bulkhead/concurrency limit cho đường DB fallback, đồng thời bảo đảm việc invalidate cache sau khi thay đổi DB. Nếu invalidation thất bại, dữ liệu cũ có thể tồn tại đến khi TTL hết hạn; yêu cầu chặt hơn cần chiến lược version, event/outbox hoặc đọc từ nguồn chuẩn tại điểm quyết định.

### 6.1. Circuit breaker, bulkhead và retry ngắn

Khi Redis không sẵn sàng, mỗi request có thể cùng mất 700 ms rồi đồng loạt dồn xuống DB. Một chiến lược vận hành thường gồm:

- **Timeout hữu hạn** để request không chờ vô hạn.
- **Circuit breaker** bao quanh adapter Redis để tạm ngừng gọi tới dependency đang lỗi, sau khoảng cooldown cho phép một số request thăm dò. Cache miss bình thường không phải lỗi; lỗi DB ở đường fallback không nên được tính thành lỗi của Redis.
- **Bulkhead** giới hạn request đồng thời đi qua DB fallback, bảo vệ connection pool và giữ năng lực phục vụ cho thao tác quan trọng.
- **Retry có giới hạn** cho thao tác an toàn, với exponential backoff và jitter; dừng khi deadline request không còn đủ. Một số lỗi như sai mật khẩu, CROSSSLOT, WRONGTYPE cần sửa nguyên nhân thay vì retry.
- **Load shedding** khi không còn năng lực: phản hồi 429/503 theo hợp đồng và hướng dẫn caller retry, thay vì giữ request chờ đến hết tài nguyên.

Có thể dùng Resilience4j ở lớp Redis gateway; phải cấu hình breaker riêng cho cache read và các thao tác có tác dụng phụ. Không áp một annotation retry rộng lên cả service, vì nó có thể làm lặp cả phần ghi DB hoặc xuất bản thông điệp.

### 6.2. Tại sao fallback có thể tạo sự cố thứ cấp?

Giả sử trạng thái bình thường 90% truy vấn được cache hit, còn DB phục vụ 10%. Khi Redis ngừng hoạt động, DB đột ngột nhận gần 100% lưu lượng truy vấn — khoảng gấp mười lần trước đó, chưa tính retry và các key nóng. Sự cố cache vì thế có thể lan thành timeout DB và HTTP 5xx.

Những biện pháp nên phối hợp:

- Giới hạn đồng thời, connection pool và tốc độ request tới DB; ưu tiên thao tác quan trọng.
- Có thể dùng local cache TTL rất ngắn hoặc trả dữ liệu stale **chỉ khi hợp đồng cho phép**; nêu rõ tuổi dữ liệu.
- Làm ấm cache có chọn lọc sau phục hồi, phân tán TTL và tránh mọi node cùng tải lại key nóng.
- Đo tỷ lệ fallback, tải DB, p95/p99 và tỷ lệ bị từ chối để biết khi nào cần hạ chất lượng dịch vụ.

## 7. Những thao tác Redis tuyệt đối không retry tùy tiện

Bảng sau xét tình huống **không nhận được phản hồi**:

| Thao tác | Retry khi timeout? | Điều kiện an toàn |
|---|---|---|
| GET, EXISTS (đọc thuần) | Thường có thể retry ngắn | Không vượt deadline, chấp nhận dữ liệu có thể thay đổi giữa hai lần đọc. |
| SET ghi đè cùng giá trị | Có thể an toàn trong một số hợp đồng | Xem xét TTL bị gia hạn, thứ tự cập nhật và cạnh tranh với writer khác; không mặc nhiên coi mọi SET đều idempotent. |
| INCR, DECR, LPUSH, XADD | Không retry mù | Cần định danh yêu cầu, deduplication hoặc đối soát kết quả. |
| SET NX để tạo khoá/idempotency marker | Cần xử lý trạng thái chưa rõ | Kiểm tra ownership/token và hợp đồng hết hạn, không giả định thất bại nghĩa là chưa tạo khoá. |
| Lua script thay đổi nhiều key | Không retry mù | Atomic trong một lần thực thi nhưng phản hồi vẫn có thể mất; cần mã yêu cầu chống lặp. |
| XACK, xử lý Redis Stream | Phân biệt ACK với xử lý nghiệp vụ | Consumer phải idempotent; chỉ ACK sau khi side effect quan trọng đã được commit. |

Trong tích hợp HTTP hoặc message broker, một retry từ tầng gateway/consumer có thể xảy ra dù ứng dụng không tự viết retry Redis. Vì vậy cần thiết kế idempotency ở **ranh giới nghiệp vụ**, thí dụ unique constraint theo request ID trong DB, thay vì chỉ dựa vào Redis TTL key.

### 7.1. Khoá phân tán và fencing token

Khoá Redis có thời gian thuê (lease) có thể hết hạn trong lúc holder bị pause hoặc mất kết nối. Holder cũ vẫn có thể chạy tiếp sau khi holder mới đã nhận khoá. Failover còn có thể làm mất trạng thái khoá chưa replicate. Do đó:

- Mọi thao tác quan trọng phải kiểm tra quyền sở hữu khoá trước khi unlock; không xoá khoá của holder khác.
- Với tài nguyên yêu cầu loại trừ mạnh, dùng **fencing token** tăng đơn điệu được hệ thống ghi nhận ở nơi cập nhật dữ liệu, hoặc dùng locking/transaction tại DB nguồn chuẩn.
- Nếu không chứng minh được quyền sở hữu hợp lệ, từ chối hoặc hoãn thao tác. Không “tạm bỏ khoá” khi Redis chết.
- **RedisLockRegistry** của Spring Integration hữu ích cho một số kịch bản điều phối, nhưng không tự thay thế thiết kế nhất quán hay fencing ở hệ thống đích.

### 7.2. Xác thực, phiên và rate limiting

Nếu Redis giữ danh sách token đã bị thu hồi, mất Redis không được hiểu thành “không có token nào bị thu hồi”. Hệ thống cần một nguồn xác minh độc lập hoặc trả lỗi có kiểm soát cho hành động nhạy cảm. Nếu Redis chỉ lưu phiên có thể phục hồi bằng cơ chế đăng nhập lại, chính sách degrade có thể là yêu cầu người dùng xác thực lại; đó là quyết định sản phẩm và bảo mật.

Rate limiter chống brute-force nên có phòng tuyến ở API gateway/WAF hoặc trạng thái khác đủ tin cậy. Local in-memory limiter trên mỗi pod chỉ áp giới hạn cục bộ, không thể cam kết giới hạn toàn bộ số request qua nhiều pod.

### 7.3. Redis Pub/Sub, Streams và Spring Integration

**Redis Pub/Sub** truyền cho subscriber đang kết nối; nếu adapter bị disconnect trong failover, những publish xảy ra lúc ấy có thể không đến ứng dụng. Tái kết nối không tạo lại lịch sử thông điệp đã mất.

**Redis Streams** hỗ trợ lưu bản ghi, consumer group, pending entry và cơ chế claim/ack; nhưng vẫn cần cấu hình persistence, xem xét replication/failover và xử lý lặp. Không đánh đồng ACK của broker với transaction DB.

Đối với sự kiện bắt buộc giao sau commit DB (chẳng hạn đơn hàng được xác nhận), một mẫu an toàn hơn là:

~~~mermaid
flowchart LR
    REQ["HTTP command"] --> TX["DB transaction"]
    TX --> ORDER[("Business row")]
    TX --> OUTBOX[("Outbox row")]
    OUTBOX --> PUBLISH["Outbox publisher"]
    PUBLISH --> BROKER["Durable broker / event stream"]
    BROKER --> CONS["Idempotent consumer"]
    CONS --> INVALIDATE["Invalidate / update Redis cache"]
    INVALIDATE -. "Lỗi cache: retry invalidation, quan sát" .-> CONS
~~~

Transactional outbox đảm bảo bản ghi nghiệp vụ và ý định phát sự kiện được lưu trong cùng transaction DB; publisher/consumer vẫn phải chịu lặp và tự idempotent. Redis có thể là bộ nhớ đệm bị cập nhật từ sự kiện, nhưng không nên là nơi duy nhất chứng minh sự kiện nghiệp vụ quan trọng đã xảy ra.

Với Spring Integration, cần quan sát lỗi ở adapter/channel và **errorChannel** thích hợp, đồng thời quy định retry, ACK, dead-letter và idempotency theo loại message. Error channel giúp định tuyến lỗi, không tự phục hồi các bản tin Pub/Sub đã mất.

## 8. Nhất quán dữ liệu trong failover

Cần phân biệt bốn cấp độ:

1. **Đã gửi yêu cầu**: client đưa lệnh tới socket; chưa đủ bằng chứng lệnh tới Redis.
2. **Redis đã thực thi trên primary**: dữ liệu có thể hiện hữu trên primary hiện tại.
3. **Client nhận thành công**: ứng dụng thấy phản hồi, nhưng dữ liệu có thể chưa đến replica hoặc thiết bị lưu trữ bền vững.
4. **Dữ liệu sống sót sau lỗi**: phụ thuộc replication, persistence, thời điểm fsync, bầu primary và kiểu lỗi thực tế.

Trong khoảng chuyển nút, hai client có thể quan sát thứ tự hoặc phiên bản dữ liệu khác nhau, nhất là nếu một client đọc replica. Đọc lại sau timeout cũng không luôn chứng minh một thao tác có tác dụng phụ đã hoặc chưa chạy, bởi một writer khác có thể cập nhật trạng thái.

**Các quy tắc thiết kế:**

- Xác định rõ nguồn dữ liệu chuẩn. Với đơn hàng, tiền, quyền truy cập và điều kiện chống trùng, ưu tiên ràng buộc bền vững của DB/ledger thay vì chỉ dựa vào cache.
- Cache key có TTL, version hoặc cơ chế invalidate gắn với thay đổi dữ liệu chuẩn; không giả định invalidation luôn thành công.
- Chấp nhận rằng hoạt động trước/sau failover có thể bị lặp ở lớp request hoặc message. Khóa duy nhất nghiệp vụ và xử lý idempotent phải chịu được việc phát lại.
- Nếu một thao tác không thể bảo đảm kết quả, biểu diễn trạng thái **unknown/pending reconciliation** và có quy trình đối soát; không biến trạng thái chưa rõ thành “thành công” hoặc “chưa thực hiện”.
- Không nhầm **WAIT** (chờ ACK replication) với commit giao dịch nhiều nút hoặc đảm bảo bản ghi đã được fsync an toàn trên mọi node.

## 9. Health check và quan sát vận hành

Một ứng dụng dùng Redis chỉ làm cache có thể vẫn sẵn sàng xử lý request khi Redis mất; một ứng dụng dùng Redis làm thành phần bắt buộc để xác thực có thể không còn sẵn sàng. Trạng thái readiness nên thể hiện **khả năng phục vụ hợp đồng nghiệp vụ**, không chỉ phản ánh một lệnh PING.

Ví dụ khi DB là bắt buộc nhưng Redis cache là tùy chọn:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Ở ví dụ này, readiness không bao gồm health contributor **redis**; health tổng hợp ở endpoint khác vẫn có thể phản ánh Redis đang lỗi. Nếu Redis thực sự bắt buộc cho mọi thao tác của service, cần tính Redis vào readiness hoặc tạo health indicator nghiệp vụ phù hợp. Liveness nên tập trung vào khả năng tiến trình tự hoạt động, tránh restart mọi pod chỉ vì lỗi của một dependency bên ngoài.

Theo dõi ít nhất:

| Nhóm | Metric/sự kiện cần quan sát | Câu hỏi vận hành |
|---|---|---|
| Client | Timeout, connection failure, reconnect, thời gian thực hiện lệnh, pool saturation nếu dùng pool | Redis đang chậm, bị đứt mạng hay hết kết nối? |
| Failover | Số lần đổi primary, thời gian phát hiện/phục hồi, topology refresh/redirection | Mất bao lâu để ứng dụng nối tới primary mới? |
| Dữ liệu Redis | Replication lag, memory, evictions, rejected commands, persistence errors | Có rủi ro dữ liệu/khả năng đáp ứng nào đang tăng? |
| Chính sách ứng dụng | Cache hit/miss, fallback count, breaker state, retry count, số request bị từ chối | Ứng dụng thực sự có degrade đúng chính sách không? |
| Downstream | QPS DB, connection pool, query latency, HTTP 429/503/5xx, consumer lag | Redis lỗi có đang kéo sập thành phần khác không? |

Dùng Micrometer/Actuator để phát metric từ lớp Redis adapter; log có request/correlation ID, loại thao tác, duration, trạng thái retry và loại exception. Không đưa password, token, giá trị session hoặc payload nhạy cảm vào log. Hạn chế key chứa định danh cá nhân hoặc cardinality cao khi đặt metric label: dùng tên nhóm key/operation thay cho full key.

Cảnh báo nên dựa trên **tỷ lệ lỗi và tác động tới nghiệp vụ**: nhiều cache miss có thể bình thường, còn thất bại khi kiểm tra revocation hoặc tăng tỷ lệ giao dịch chưa xác định phải được ưu tiên cao.

## 10. Kiểm thử khả năng chịu lỗi

Kiểm thử happy path với Redis đang chạy là chưa đủ. Nên có unit test cho ma trận chính sách, integration test với Redis thực, và fault-injection test ở môi trường kiểm thử có topology giống production khi cần xác thực failover.

| Kịch bản gây lỗi | Cách mô phỏng trong môi trường thử nghiệm | Kết quả cần chứng minh |
|---|---|---|
| Redis không khởi động / endpoint sai | Tắt Redis của test environment hoặc dùng địa chỉ không kết nối | Cache read fallback về DB trong deadline; thao tác critical từ chối đúng hợp đồng. |
| Tăng latency / packet loss | Network proxy như Toxiproxy giữa Spring Boot và Redis | Timeout hữu hạn, không bùng retry, circuit breaker mở khi đúng ngưỡng. |
| Cắt kết nối sau khi lệnh ghi được gửi | Đóng kết nối/proxy vào thời điểm kiểm soát | Không tăng bộ đếm, thanh toán hay tạo message lần hai do retry mù. |
| Sentinel đổi primary | Dùng test topology có nhiều Redis và Sentinel, kích hoạt failover | Client khám phá primary mới, có khoảng lỗi được đo, không hứa không mất ghi. |
| Cluster reshard / failover | Dùng Redis Cluster test, chuyển slot hoặc tắt primary | Client xử lý MOVED/ASK, refresh topology và timeout theo giới hạn. |
| Redis phục hồi nhưng cache trống | Xoá dữ liệu cache trong môi trường thử nghiệm rồi khôi phục traffic | Không gây cache stampede làm quá tải DB; TTL phân tán và bulkhead có hiệu lực. |
| DB đồng thời quá tải khi cache lỗi | Giới hạn DB pool hoặc tải truy vấn trong test | Hệ thống load shed/degrade, không tạo hàng đợi vô hạn hay treo request. |
| Consumer reconnect sau gián đoạn | Ngắt Pub/Sub/Streams adapter rồi nối lại | Hợp đồng mất/nhận lại message được kiểm chứng; consumer idempotent, ACK đúng thời điểm. |

Một test cho cache-aside nên kiểm tra ba nhánh tách biệt: **cache hit**, **cache miss**, **Redis exception**. Nhánh exception cần assert DB được gọi, kết quả trả caller đúng và lỗi cache được ghi metric; test riêng chứng minh lỗi DB không bị nuốt. Với thao tác khoá và idempotency, assert Redis unavailable khiến lệnh bị từ chối hoặc dùng cơ chế dự phòng đúng, không lặng lẽ đi tiếp.

Khi đo, ghi nhận **thời gian phát hiện lỗi**, **thời gian failover**, **thời gian khôi phục tỷ lệ thành công**, **số request ở trạng thái unknown**, **mức tăng tải DB**, **số bản ghi trùng**. Kiểm thử bằng container Redis đơn lẻ không thể chứng minh hành vi Sentinel/Cluster: để kết luận về chuyển nút cần topology tương ứng.

## 11. Runbook khi Redis bị gián đoạn

1. **Xác định ảnh hưởng:** Redis đang giữ cache hay điều kiện bắt buộc? Xem tỷ lệ 5xx, request bị từ chối, số giao dịch unknown và mức tải DB; xác nhận vùng dịch vụ bị ảnh hưởng.
2. **Khoanh vùng nguyên nhân:** phân biệt DNS/TLS/ACL, network partition, Redis quá tải, chuyển primary, địa chỉ node Cluster không reachable, hay lỗi ứng dụng (WRONGTYPE/CROSSSLOT).
3. **Giữ an toàn nghiệp vụ:** bảo vệ thao tác thanh toán/khoá/idempotency bằng fail-closed hoặc nguồn chuẩn; bật degrade/fallback đã kiểm thử cho cache, giới hạn lượng truy vấn DB và retry.
4. **Quan sát quá trình khôi phục:** kiểm tra primary hiện tại, replication lag, client reconnect và topology refresh; đánh giá command error cùng latency, không dựa vào PING đơn lẻ.
5. **Khôi phục có kiểm soát:** cho phép breaker thử lại, tăng dần lưu lượng cache, tránh cùng lúc tải lại mọi key; đối soát các yêu cầu có kết quả không xác định và xử lý sự kiện chưa ACK/đang pending.
6. **Đóng sự cố bằng bằng chứng:** so sánh SLO, số request bị ảnh hưởng, dữ liệu mất/trùng (nếu có), log/metric/trace theo request ID; cập nhật ngưỡng và kịch bản fault injection.

Không thao tác xóa toàn bộ key hoặc chuyển primary thủ công trong môi trường thực chỉ dựa trên việc client bị timeout. Cần xác minh nguyên nhân và quy trình vận hành của Redis/Sentinel/Cluster hoặc nhà cung cấp trước khi can thiệp.

## 12. Checklist trước khi đưa vào production

- [ ] Mọi cách dùng Redis có **vai trò**, **nguồn dữ liệu chuẩn** và **chính sách mất Redis** bằng văn bản.
- [ ] Đã phân biệt cache miss với hỏng Redis và lỗi dữ liệu/cấu hình; không nuốt lỗi nghiệp vụ.
- [ ] Connect timeout, command timeout, deadline request, retry và circuit breaker có giới hạn phù hợp SLO.
- [ ] Không retry mù lệnh có tác dụng phụ; đã có idempotency, unique constraint hoặc đối soát khi kết quả unknown.
- [ ] Topology Sentinel/Cluster, địa chỉ client truy cập, TLS/ACL, chuyển nút và replication được kiểm thử thực tế.
- [ ] Cache fallback được bảo vệ bằng bulkhead/load shedding; có kế hoạch xử lý cache lạnh sau failover.
- [ ] Readiness/liveness phản ánh tính thiết yếu của Redis theo hợp đồng nghiệp vụ.
- [ ] Có metric, cảnh báo, trace, runbook và fault-injection test cho mất kết nối, failover, phục hồi.
- [ ] Với Spring Integration hoặc message consumer, đã xác định rõ semantic delivery, ACK, retry, DLQ và xử lý trùng.

## 13. Tình huống tổng hợp

Một dịch vụ bán hàng có ba đường xử lý dùng cùng Redis Cluster:

1. **GET /catalog/{sku}:** Redis cache sản phẩm lỗi trong lúc Cluster đổi primary. Service chuyển tới DB với bulkhead, trả dữ liệu hiển thị và ghi metric fallback. Nếu DB đã quá tải, service trả 503 theo SLA thay vì mở hàng nghìn kết nối DB.
2. **POST /orders:** Redis giữ marker chống gửi trùng, nhưng nhận timeout sau thao tác ghi marker. Service không suy đoán marker đã hay chưa tồn tại. Request ID được đối chiếu với unique constraint trong DB và bản ghi trạng thái đơn; caller được trả kết quả đơn hiện tại hoặc trạng thái cần tra cứu.
3. **POST /admin/revoke-token:** Redis chứa cache trạng thái thu hồi token. Redis không truy cập được và không có nguồn xác minh khả dụng. Dịch vụ từ chối hành động phụ thuộc xác minh quyền và ghi nhận lỗi, thay vì mặc định token được phép.

Cùng một sự cố mạng nhưng dẫn tới ba cách xử lý khác nhau vì **hợp đồng nghiệp vụ khác nhau**. Đây là nguyên tắc cốt lõi khi đưa Redis vào Spring Boot: có topology HA là cần thiết, nhưng **chính sách lỗi tại adapter, idempotency, nguồn sự thật và giám sát** mới quyết định hệ thống có tiếp tục hoạt động đúng khi Redis không sẵn sàng hay không.
