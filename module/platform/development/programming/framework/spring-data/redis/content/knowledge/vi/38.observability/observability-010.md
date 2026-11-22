# Thiết kế cảnh báo theo tác động nghiệp vụ trong Spring Data Redis

Một hệ thống Redis có thể ghi nhận CPU 95%, hàng nghìn connection hoặc một đợt failover mà người dùng vẫn thao tác bình thường. Ngược lại, một Redis chỉ dùng vài phần trăm CPU vẫn có thể khiến chức năng thanh toán ngừng hoạt động nếu `SET NX` dùng để chống xử lý trùng liên tục timeout. Vì vậy, **cảnh báo tốt không chỉ mô tả Redis đang bất thường, mà phải nói rõ bất thường đó gây tác động gì cho nghiệp vụ, ai cần xử lý và cần hành động ra sao**.

Trong Spring Data Redis, ứng dụng có thể dùng Redis với nhiều vai trò: lớp cache tối ưu hiệu năng, session store, token hoặc rate limit, distributed lock, bộ đếm, Redis Streams, Pub/Sub, Spring Cache hoặc Redis Repository. Cùng một chỉ số như `connected_clients`, `evicted_keys`, replication lag hay `RedisCommandTimeoutException` sẽ có mức nghiêm trọng khác nhau tùy vai trò đó.

Bài học hướng dẫn thiết kế hệ thống cảnh báo từ mục tiêu kinh doanh xuống các dấu hiệu kỹ thuật: xác định **user journey**, định nghĩa **SLI/SLO**, đo lỗi tại ứng dụng Spring Data Redis, phân lớp cảnh báo theo **mức ảnh hưởng**, kết hợp Redis metrics với downstream metrics, viết ví dụ Prometheus/Alertmanager, tổ chức runbook và kiểm thử quy tắc cảnh báo. Các ngưỡng số chỉ là ví dụ minh họa; production cần hiệu chỉnh bằng SLO, tải và kiến trúc thực tế.

## 1. Nguyên tắc đầu tiên: bắt đầu từ người dùng, không bắt đầu từ Redis

Giả sử một ứng dụng thương mại điện tử dùng Redis như sau:

```text
                Khách hàng
                    |
     +--------------+--------------+
     |              |              |
  Xem sản phẩm    Đăng nhập      Đặt hàng
     |              |              |
     v              v              v
 Redis cache     Redis session   Redis idempotency/lock
     |              |              |
     v              v              v
 PostgreSQL      Session state   Order database
     |
     +------ Redis Streams cho event hậu xử lý
```

Nếu cache sản phẩm lỗi nhưng database vẫn đủ năng lực, khách hàng có thể chỉ thấy trang tải chậm hơn. Nếu Redis session không đọc được, hàng loạt người dùng có thể bị đăng xuất hoặc không truy cập được. Nếu Redis idempotency key mất và code chấp nhận xử lý lại yêu cầu thanh toán, vấn đề không còn là latency mà có thể là **sai lệch giao dịch**.

Do đó, câu hỏi cảnh báo đầu tiên không phải:

> Redis có `used_memory` bao nhiêu?

mà là:

> Khi Redis bị lỗi, chức năng nghiệp vụ nào bị ảnh hưởng, ảnh hưởng ở mức nào, và hệ thống còn đáp ứng cam kết với người dùng không?

### 1.1. Chuyển từ triệu chứng kỹ thuật sang tác động

| Triệu chứng | Tác động nghiệp vụ có thể có | Cách kiểm chứng tác động |
|---|---|---|
| Redis `GET` timeout | Trang sản phẩm chậm do fallback DB | p95/p99 endpoint, DB load, tỷ lệ request lỗi |
| Redis session read thất bại | Người dùng không đăng nhập được | Login/auth success ratio, số session lỗi |
| `SET NX` lock timeout | Đơn hàng kẹt hoặc thao tác duplicate | Số đơn hàng hoàn tất, lock acquisition và duplicate guard |
| Stream pending tăng | Giao hàng/email/xử lý đơn hàng chậm | Tuổi event chưa hoàn tất, backlog và business completion lag |
| Pub/Sub listener mất kết nối | Cache nội bộ không được invalidate | Độ cũ dữ liệu, version mismatch, số consumer disconnected |
| Redis primary failover | Một số thao tác tạm lỗi | SLI thành công end-to-end và thời gian phục hồi |
| `evicted_keys` tăng | Cache hit rate giảm hoặc dữ liệu quan trọng bị loại | Cache miss, session eviction, request errors |
| AOF rewrite kéo dài | Latency tăng, memory pressure | p99 Redis command, API latency, cgroup memory |
| `rejected_connections` tăng | Một số ứng dụng không kết nối được | Client connection failures và error rate theo service |

Mỗi hàng cần một **định nghĩa impact** thay vì một kết luận chung “Redis có vấn đề”.

## 2. Redis đang là cache hay thành phần thiết yếu?

Nên phân loại từng Redis usage trong kiến trúc.

### 2.1. Redis chỉ là cache có thể tái tạo

Ví dụ: `@Cacheable` lưu thông tin sản phẩm có nguồn sự thật ở PostgreSQL.

```text
Redis available:
  GET cache -> trả nhanh

Redis unavailable:
  GET lỗi -> service truy vấn DB -> vẫn trả đúng dữ liệu
```

Nếu fallback DB hoạt động và request thành công, đây có thể là **suy giảm hiệu năng** thay vì outage ngay lập tức. Nhưng DB có thể không chịu được toàn bộ traffic khi Redis lỗi, nên phải đo **khả năng fallback**, không chỉ HTTP 2xx.

### 2.2. Redis giữ dữ liệu cần cho request thành công

Ví dụ:

- Session state không có nguồn thay thế.
- Rate limit state mà hệ thống chọn policy fail-closed.
- Token/nonce chống replay.
- Khóa điều phối công việc.
- Idempotency record.
- Stream được dùng như hàng đợi công việc có SLA hoàn thành.

Trong nhóm này, Redis error có thể chặn trực tiếp nghiệp vụ hoặc tạo rủi ro toàn vẹn dữ liệu. Cần ưu tiên cảnh báo thành công/thất bại của **thao tác nghiệp vụ**, không chỉ service health.

### 2.3. Ma trận phụ thuộc

| Vai trò Redis | Khi Redis lỗi | Độ ưu tiên đo chính |
|---|---|---|
| Product cache | Fallback về nguồn dữ liệu | Latency + DB saturation + cache read error |
| Session store | Đăng nhập/session có thể thất bại | Auth availability |
| Feature flag cache | Có thể dùng default hoặc fail-closed tùy tính năng | Đúng policy và tỷ lệ fallback |
| Rate limiter | Có thể fail-open/fail-closed | Abuse risk, tỷ lệ request bị chặn sai |
| Distributed lock | Không được phép tiếp tục mù quáng | Job success, lock wait và ownership correctness |
| Idempotency store | Không được nhận duplicate nguy hiểm | Duplicate prevention, payment/order correctness |
| Redis Streams | Event có thể backlog hoặc pending | Processing delay + completion ratio |
| Pub/Sub | Thông báo có thể mất khi offline | Listener health + reconciliation/data freshness |
| Counter analytics | Có thể chấp nhận dữ liệu trễ hoặc thiếu có giới hạn | Data freshness, error budget |
| Redis Repository làm data store | Có thể mất trực tiếp dữ liệu/CRUD | Read/write availability và durability |

**Một Redis instance có thể phục vụ nhiều vai trò.** Cùng một Redis outage có thể là P3 cho product cache nhưng P1 cho session hoặc idempotency. Cảnh báo phải dựa vào thành phần nghiệp vụ đang bị ảnh hưởng.

## 3. Chọn User Journey làm đơn vị thiết kế cảnh báo

Một user journey là luồng mà người dùng hoặc hệ thống kỳ vọng hoàn tất:

1. Xem trang sản phẩm.
2. Đăng nhập và duy trì phiên.
3. Tạo đơn hàng.
4. Thanh toán một lần duy nhất.
5. Nhận xác nhận đơn hàng.
6. Đồng bộ kho.
7. Truy vấn lịch sử giao dịch.

Với mỗi journey, xác định:

- **Kết quả thành công:** điều kiện rõ ràng, có thể đo.
- **Cửa sổ thời gian:** ví dụ “xác nhận đơn trong 30 giây” hoặc “event xử lý trong 2 phút”.
- **Phụ thuộc Redis:** cache, key, Stream, lock hay session.
- **Fallback:** có hay không, có chịu tải không, có làm sai nghiệp vụ không.
- **Owner:** đội nào có quyền sửa.
- **Mức nghiêm trọng:** tính từ tác động thực tế, không từ tên metric.

Ví dụ bảng thiết kế:

| Journey | SLI chính | Phụ thuộc Redis | Dấu hiệu Redis để chẩn đoán |
|---|---|---|---|
| Xem sản phẩm | Tỷ lệ trả dữ liệu đúng trong 500 ms | Cache | GET error, cache hit, DB load |
| Đăng nhập | Tỷ lệ đăng nhập thành công | Session | Redis session error, latency |
| Đặt hàng | Tỷ lệ đặt hàng hoàn tất | Idempotency/lock | Lock failure, duplicate check |
| Gửi xác nhận | Tỷ lệ event được xử lý trong 60 s | Stream | Oldest pending age, lag, consumer errors |
| Đồng bộ tồn kho | Độ trễ giữa thay đổi và trạng thái đọc | Pub/Sub/Stream | Listener disconnect, reconcile mismatch |

Bảng này trở thành **hợp đồng quan sát** giữa nhóm ứng dụng, SRE và chủ sở hữu sản phẩm.

## 4. SLI, SLO, SLA và error budget

### 4.1. SLI là gì?

**Service Level Indicator (SLI)** là một phép đo về mức độ dịch vụ đáp ứng kỳ vọng.

Ví dụ availability SLI:

\[
SLI_{availability}=
\frac{\text{số request hợp lệ thành công}}
{\text{tổng request hợp lệ}}
\]

Hoặc SLI latency:

\[
SLI_{latency}=
\frac{\text{request hợp lệ hoàn tất dưới ngưỡng}}
{\text{tổng request hợp lệ}}
\]

Điểm quan trọng: định nghĩa **request hợp lệ** và **thành công** dựa trên hành vi nghiệp vụ, không chỉ HTTP status. Một endpoint trả `200` nhưng lại dùng giá trị mặc định sai có thể không phải một thành công thật.

### 4.2. SLO là gì?

**Service Level Objective (SLO)** là mục tiêu cho SLI trong một khoảng thời gian.

Ví dụ giả định:

```text
Product page:
  99.9% request hợp lệ trả kết quả đúng trong <= 500 ms
  đo theo cửa sổ rolling 30 ngày

Login:
  99.95% yêu cầu hợp lệ có kết quả thành công
  đo theo cửa sổ rolling 30 ngày

Order processing:
  99.9% event cần xử lý hoàn thành trong <= 60 giây
```

Các giá trị trên chỉ nhằm minh họa. Không có “Redis SLO chuẩn” áp dụng cho mọi hệ thống.

### 4.3. SLA khác SLO

- **SLO:** mục tiêu kỹ thuật/vận hành nội bộ.
- **SLA:** cam kết dịch vụ với khách hàng, có thể gắn với điều khoản thương mại.
- **SLI:** phép đo.
- **Error budget:** phần không đạt mục tiêu cho phép trong cửa sổ đánh giá.

Nếu SLO availability là 99.9%, error budget về tỷ lệ là:

\[
1-0.999=0.001=0.1\%
\]

Một Redis incident khiến request errors tăng sẽ tiêu hao ngân sách này. Cảnh báo theo tốc độ tiêu hao budget thường hữu ích hơn một ngưỡng cố định như “Redis CPU > 80%”.

### 4.4. Từ business SLO xuống Redis alert

Sơ đồ:

```text
Business SLO: tạo đơn thành công
         |
         v
SLI: order creation errors / valid requests
         |
         v
Alert: error-budget burn nhanh
         |
         +-- Redis idempotency GET/SET timeout?
         +-- DB transaction errors?
         +-- payment gateway errors?
         +-- traffic spike?
```

**Business alert phát hiện tác động**, còn Redis metrics giúp xác định nguyên nhân. Không nên tự động gọi mọi sự cố order là Redis incident chỉ vì order service có dùng Redis.

## 5. Phân biệt leading indicator và impact indicator

Có hai nhóm dấu hiệu:

### 5.1. Impact indicator: người dùng đã bị ảnh hưởng

- Login success rate giảm.
- Order creation failure tăng.
- Request p99 vượt ngưỡng.
- Event processing age vượt SLA.
- Dữ liệu cache trả sai/stale vượt giới hạn cho phép.
- Duplicate payment được phát hiện.

Nhóm này thường là cơ sở cho **page** vì tác động đã xảy ra.

### 5.2. Leading indicator: có rủi ro sắp xảy ra

- Redis memory headroom giảm.
- Replication lag tăng.
- AOF fsync delayed tăng.
- Pool waiters tăng.
- Stream pending tăng nhưng chưa vượt deadline.
- Redis disk gần đầy.
- Redis latency có xu hướng xấu.
- Sentinel quorum giảm nhưng primary vẫn chạy.

Nhóm này phù hợp với **cảnh báo dự báo rủi ro/ticket** hoặc page nếu nguy cơ rất gần và hậu quả rất nghiêm trọng. Không dùng chung một mức severity cho tất cả.

### 5.3. Kết hợp hai nhóm

Một thiết kế tốt có thể có:

```text
Impact:
  Checkout SLO burn rate cao -> PAGE

Context:
  Redis command timeouts tăng
  Redis server slowlog cho EVAL
  Redis pool waiters tăng
  DB khỏe mạnh

=> Incident response có dữ liệu để khoanh vùng
```

Thay vì:

```text
Redis CPU > 70% -> PAGE
Redis memory > 70% -> PAGE
Redis client count > 100 -> PAGE
```

mà chưa chứng minh user journey nào đang thất bại.

## 6. Chọn mức nghiêm trọng từ tác động nghiệp vụ

Một bảng mức độ minh họa:

| Mức | Điều kiện điển hình | Kênh xử lý |
|---|---|---|
| **P1 / Critical** | Thanh toán bị xử lý trùng, mất dữ liệu nghiệp vụ, login/checkout ngừng trên diện rộng | Page ngay, incident commander, phối hợp owner |
| **P2 / High** | Journey trọng yếu vượt SLO đáng kể, stream xử lý trễ gây vi phạm SLA | Page cho on-call liên quan |
| **P3 / Medium** | Cache fallback còn hoạt động nhưng DB gần saturation; disk/memory có nguy cơ | Ticket/working-hours hoặc page tùy headroom |
| **P4 / Informational** | Một failover thành công không ảnh hưởng SLO, một node đã recovery | Dashboard/event log |

Đây là ma trận minh họa. Severity phải dựa trên chính sách sự cố của tổ chức, thị trường, thời điểm, quy mô người dùng và tính an toàn dữ liệu.

### 6.1. Sự cố tính đúng đắn có thể cần page dù error rate thấp

Nếu một số ít giao dịch thanh toán bị thực thi hai lần, tỷ lệ HTTP error có thể vẫn gần 0. Nhưng **invariant bị vi phạm** rất nghiêm trọng.

Cần có alert riêng cho:

- Idempotency duplicate được xác nhận.
- Lock ownership violation.
- Phát hiện mismatch dữ liệu không thể chấp nhận.
- Trường hợp charge/refund bất thường.
- Những thao tác Redis mà fallback policy cho phép tiến hành không an toàn.

Một hệ thống chỉ dùng HTTP 5xx SLO sẽ bỏ sót các sai lệch nghiệp vụ này.

## 7. Đo tại đúng lớp: controller, service và Redis client

Nên có ít nhất ba lớp quan sát.

```text
[Business journey / HTTP]
        |
        | request result, response duration, business invariant
        v
[Spring service]
        |
        | cache hit/miss/fallback, Redis operation outcome
        v
[Spring Data Redis / client]
        |
        | command latency, connection timeout, pool wait
        v
[Redis server/topology]
        |
        | memory, CPU, replication, persistence, clients
```

### 7.1. Vì sao chỉ đo Redis health là chưa đủ?

Redis `PING` trả `PONG` nhưng:

- Lua script quan trọng có thể lỗi `WRONGTYPE`.
- Một `SET` có thể bị `OOM command not allowed`.
- Redis Cluster có thể thiếu slot hoặc gặp `CROSSSLOT`.
- Session serializer không đọc được dữ liệu sau rolling upgrade.
- Cache fallback vẫn tạo quá tải database.
- Redis Stream đã giao entry nhưng handler chưa hoàn thành.

Health check chỉ nói về một lớp, không đo end-to-end business success.

### 7.2. Vì sao chỉ đo HTTP 5xx cũng chưa đủ?

Trong fail-open cache:

```text
Redis unavailable
    |
    v
Application fallback to DB
    |
    v
HTTP 200, nhưng latency tăng và DB sắp quá tải
```

Lúc đầu HTTP 5xx có thể không tăng. Nếu không có leading metrics như cache error, DB pool usage và fallback rate, đội vận hành chỉ được page khi database đã sụp.

Giải pháp: **business impact + dependency risk**, với severity riêng và threshold đủ chống nhiễu.

## 8. Định nghĩa metric có cấu trúc cho Spring Data Redis

Không phải mọi metric đều có sẵn từ Spring Boot. Với nghiệp vụ quan trọng, ứng dụng nên instrument kết quả Redis-related operations.

Ví dụ danh sách metric do ứng dụng tự định nghĩa:

| Tên metric ví dụ | Kiểu | Labels nên có | Ý nghĩa |
|---|---|---|---|
| `app_business_requests_total` | Counter | journey, outcome | Kết quả nghiệp vụ |
| `app_business_request_duration_seconds` | Histogram/Timer | journey, outcome | Latency journey |
| `app_redis_operations_total` | Counter | role, operation, result | Redis operation success/error |
| `app_redis_operation_duration_seconds` | Timer | role, operation, result | Redis call latency |
| `app_cache_access_total` | Counter | cache, outcome | Hit, miss, fallback, error |
| `app_cache_fallback_total` | Counter | cache, reason | Số lần dùng nguồn dự phòng |
| `app_stream_events_total` | Counter | stream_group, result | Xử lý stream success/failure |
| `app_stream_processing_delay_seconds` | Histogram | stream_group | Độ trễ từ event đến completion |
| `app_lock_acquire_total` | Counter | workflow, result | Thành công, timeout, denied |
| `app_idempotency_conflicts_total` | Counter | workflow, result | Nhận diện replay/duplicate |
| `app_dependency_fallback_total` | Counter | dependency, outcome | Fallback thành công/thất bại |

Đây là **tên do bài học đề xuất**, không khẳng định Spring Boot tự xuất những series này. Nếu dự án đã có chuẩn metric riêng, nên tuân theo chuẩn đó.

### 8.1. Quy tắc cardinality

Labels có thể dùng:

```text
service="checkout"
environment="production"
journey="create_order"
operation="get"
role="idempotency"
result="timeout"
```

Không nên dùng:

```text
customer_id="123456789"
order_id="order-123"
redis_key="session:customer:123456789"
request_id="f3a2..."
```

Mỗi giá trị khác nhau của label có thể sinh một time series riêng, làm Prometheus và hệ thống observability tăng tải nghiêm trọng. Các ID riêng lẻ nên nằm trong log/tracing có quyền truy cập phù hợp, không nằm trong label metric.

### 8.2. Tách những trạng thái khác nhau

Với Redis cache, tối thiểu phân biệt:

```text
HIT
MISS
REDIS_ERROR
FALLBACK_SUCCESS
FALLBACK_FAILURE
```

Không ghi lỗi kết nối thành `MISS`, vì làm mất khả năng phát hiện dependency outage.

Với `SET NX` idempotency:

```text
CREATED
EXISTS / CONFLICT
REDIS_ERROR / UNKNOWN
```

`EXISTS` thường không phải lỗi hạ tầng; nó có thể phản ánh request trùng được xử lý theo thiết kế.

## 9. Ví dụ instrument cache trong Spring Data Redis

Ví dụ service đọc product cache rồi fallback tới repository khi key chưa có. Redis chỉ là lớp tối ưu; lỗi cache được ghi riêng.

```java
package com.example.product;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;
    private final ProductRepository repository;
    private final MeterRegistry registry;
    private final Timer redisReadTimer;

    public ProductCacheReader(
            StringRedisTemplate redis,
            ProductRepository repository,
            MeterRegistry registry
    ) {
        this.redis = redis;
        this.repository = repository;
        this.registry = registry;

        this.redisReadTimer =
                Timer.builder("app.redis.operation.duration")
                    .description("Redis read duration from application")
                    .tag("role", "product_cache")
                    .tag("operation", "get")
                    .register(registry);
    }

    public ProductDto find(String productId) {
        String key = "cache:product:v1:" + productId;

        String cached = null;

        try {
            cached = redisReadTimer.record(
                () -> redis.opsForValue().get(key)
            );

            if (cached != null) {
                count("app.cache.access", "hit");
                return deserialize(cached);
            }

            count("app.cache.access", "miss");
        } catch (org.springframework.dao.DataAccessException ex) {
            count("app.cache.access", "redis_error");
            // Log/trace lỗi với mức dữ liệu an toàn.
            // Fallback chỉ khi policy cho phép.
        }

        count("app.cache.fallback", "attempt");
        ProductDto product = repository.find(productId);

        if (product == null) {
            count("app.cache.fallback", "not_found");
            return null;
        }

        count("app.cache.fallback", "success");

        try {
            redis.opsForValue().set(
                key,
                serialize(product),
                Duration.ofMinutes(5)
            );
        } catch (org.springframework.dao.DataAccessException ex) {
            count("app.cache.write", "redis_error");
            // Cache write là best-effort trong thiết kế này.
        }

        return product;
    }

    private void count(String metric, String outcome) {
        Counter.builder(metric)
                .tag("cache", "products")
                .tag("outcome", outcome)
                .register(registry)
                .increment();
    }

    // Những phương thức ứng dụng phải triển khai theo DTO/schema thật.
    private ProductDto deserialize(String value) {
        return ProductJsonCodec.decode(value);
    }

    private String serialize(ProductDto product) {
        return ProductJsonCodec.encode(product);
    }
}
```

`ProductRepository`, `ProductDto` và `ProductJsonCodec` là các abstraction của ứng dụng, không phải API có sẵn của Spring Data Redis.

### 9.1. Các ranh giới của ví dụ

- Đo thời gian `GET` bằng `Timer` nhưng chưa tách borrow wait và server execution.
- Chỉ fallback với `DataAccessException` của Redis; lỗi deserialize JSON có thể cần chính sách riêng như invalidate corrupted cache và phát cảnh báo.
- `repository.find(...)` vẫn có thể lỗi; không được coi repository exception là cache miss.
- Fallback liên tục có thể làm database quá tải; phải quan sát DB latency, connections và error rate.
- `register(...)` thường tái sử dụng cùng meter identity; trong code production nên xây dựng/tag metrics ổn định và hạn chế overhead trên hot path.
- Trong Prometheus exposition, Micrometer Timer thường tạo series với hậu tố `_seconds_count`, `_seconds_sum` và bucket khi histogram được bật; phải xem cấu hình registry thực tế.

### 9.2. Lỗi fallback có thể nghiêm trọng hơn lỗi cache

Giả sử Redis GET error tăng từ 0 lên 100%, nhưng DB fallback vẫn đáp ứng được. Chỉ số cache Redis error rất xấu nhưng người dùng có thể ít bị ảnh hưởng. Nếu DB cũng bắt đầu timeout, **đây mới là thời điểm user journey gặp rủi ro nghiêm trọng**.

Vì vậy cần ít nhất hai nhóm alert:

```text
Redis cache degraded + DB healthy:
    cảnh báo sớm / triage

Product page SLO burn cao:
    page theo tác động nghiệp vụ
```

Không nên tắt hoàn toàn alert Redis cache error chỉ vì có fallback; fallback có thể đang ăn hết headroom dự phòng.

## 10. ReactiveRedisTemplate: quan sát publisher đúng thời điểm

Trong WebFlux, thao tác Redis trả `Mono` hoặc `Flux`. Nếu chỉ đếm metric lúc **tạo** publisher mà chưa có subscription, metric có thể ghi nhận lệnh chưa hề chạy.

Ví dụ minh họa:

```java
public Mono<String> getCachedValue(String key) {
    return reactiveRedis.opsForValue()
        .get(key)
        .doOnNext(value -> metrics.cacheHit())
        .switchIfEmpty(Mono.defer(() -> {
            metrics.cacheMiss();
            return Mono.empty();
        }))
        .doOnError(error -> metrics.redisError(error));
}
```

Lưu ý: ví dụ này chỉ gắn metric cho lần read thành công có value, empty và error. Trong production còn cần:

- `doFinally`/Micrometer Observation để đo duration đầy đủ.
- Không đếm error thành miss.
- Xác định behavior khi cancellation hoặc timeout.
- Không dùng `.block()` trên WebFlux event-loop chỉ để ghi metric.
- Giữ metric label ổn định.

### 10.1. Một lỗi quan sát phổ biến: nuốt error rồi vẫn báo thành công

```java
redisRead()
    .onErrorResume(ex -> Mono.just("DEFAULT"))
```

Nếu code chỉ đo downstream `onNext`, dashboard sẽ thấy “GET thành công” dù Redis đã lỗi. Nên ghi **Redis dependency error** trước `onErrorResume`, đồng thời đo xem fallback có giúp user journey thành công hay không.

Đây là lý do phải có metric ở **cả dependency boundary và business boundary**.

## 11. Thiết kế alert cho Spring Cache

Với `@Cacheable`, `@CachePut`, `@CacheEvict`, ứng dụng cần quan sát ít nhất:

- Cache hit ratio.
- Cache miss ratio.
- Cache read/write errors.
- Độ trễ truy vấn nguồn sau miss.
- TTL hoặc tình trạng thundering herd khi nhiều key hết hạn.
- Invalidation success/error.
- Staleness nếu business không chấp nhận dữ liệu cũ.
- Tình trạng Redis cache clear trên Cluster nếu có.

### 11.1. Cache hit ratio thấp có luôn là sự cố?

Không. Cache miss tăng có thể vì:

- Deploy phiên bản mới đổi key prefix.
- Cache được chủ động làm mới.
- Working set thay đổi.
- TTL được điều chỉnh có chủ đích.
- Traffic từ tập người dùng mới.
- Redis bị eviction.
- Redis connection error bị code nhầm thành miss.

Vì thế, **cache miss rate cao không nên tự động là P1**.

Một rule tốt hơn có thể là:

```text
Cache hit ratio giảm mạnh
AND database utilization vượt ngưỡng an toàn
AND product endpoint latency đang xấu
```

hoặc tạo một warning riêng cho hit ratio giảm, rồi page khi SLO người dùng thực sự bị đe dọa.

### 11.2. Cache invalidation failure

Nếu Redis cache chỉ làm tăng tốc, ghi cache thất bại có thể không nghiêm trọng. Nhưng nếu `@CacheEvict` thất bại sau khi DB đã cập nhật, ứng dụng có thể trả dữ liệu cũ cho người dùng.

Cần đo khác nhau:

```text
cache_write_error
cache_invalidation_error
cache_read_error
```

Với dữ liệu có yêu cầu freshness cao, invalidation error có thể nghiêm trọng hơn write error. Có thể bổ sung TTL tối đa, versioned key hoặc cơ chế đối chiếu nguồn dữ liệu.

## 12. Session: cảnh báo theo khả năng đăng nhập và giữ phiên

Nếu Spring Session dùng Redis, các tín hiệu nghiệp vụ quan trọng gồm:

- Login thành công theo nhóm endpoint.
- Request đã xác thực nhưng session lookup thất bại.
- Người dùng bị yêu cầu đăng nhập lại bất thường.
- Số lỗi ghi/đọc session store.
- Session data không deserialize được sau triển khai.
- TTL session không phù hợp policy.
- Redis eviction đụng tới session.

Tình huống:

```text
Redis node còn trả PONG
Nhưng session serializer thay đổi không tương thích
    |
    v
Session lookup lỗi
    |
    v
Authenticated requests thất bại
```

Cảnh báo **login/auth SLI** sẽ phát hiện tác động, còn Redis session decode error giúp chẩn đoán.

### 12.1. Không dùng một endpoint healthcheck để thay login SLI

Một `GET healthcheck` thành công không chứng minh Redis đang đọc được session payload thực tế. Nên có integration test về session serialization, rolling upgrade và TTL; production metric đo lỗi session ở abstraction phù hợp.

### 12.2. Phân biệt expired session đúng policy và hạ tầng lỗi

User đăng nhập lại vì session đã hết TTL bình thường không phải incident. Nếu tỷ lệ session failure tăng đột biến sau failover, deployment hoặc eviction, cần phân biệt:

```text
normal_expiration
explicit_logout
missing_session_unexpected
deserialize_error
redis_unavailable
```

Không cộng mọi trường hợp thành một “Redis session errors” duy nhất rồi page.

## 13. Lock và idempotency: ưu tiên invariant nghiệp vụ

Khi dùng Redis lock hoặc idempotency key, lỗi không chỉ là độ trễ.

Ví dụ:

```text
POST /payments
    |
    v
Check/claim idempotency key bằng Redis
    |
    +-- claimed     -> xử lý thanh toán
    +-- exists      -> trả kết quả trước / báo duplicate
    +-- Redis error -> quyết định fail-closed/fail-open
```

Nếu Redis lỗi nhưng ứng dụng chọn **fail-open**, nó có thể tiến hành thanh toán mà không chống trùng. HTTP 2xx có thể tăng trong khi hệ thống trở nên không an toàn.

### 13.1. Các SLI riêng

- Tỷ lệ idempotency check/claim thành công theo workflow.
- Số request có trạng thái idempotency **unknown**.
- Số lần phát hiện duplicate request.
- Số duplicate side effects được xác nhận sau đối chiếu.
- Tỷ lệ lock acquire timeout.
- Thời gian chờ lock.
- Số lock ownership violation nếu có cơ chế phát hiện.
- Số giao dịch phải compensation.

### 13.2. Cảnh báo bất biến là cảnh báo cấp cao

Ví dụ:

```text
ConfirmedDuplicateCharge > 0
```

có thể là một event đủ để khởi động điều tra nghiêm trọng, tùy chính sách sản phẩm. Không cần chờ error ratio 5%.

Nhưng cần nguồn phát hiện **đáng tin cậy**: đếm số request bị từ chối vì duplicate không đồng nghĩa đã có duplicate charge. Tên metric phải phân biệt `duplicate_attempt_prevented` và `duplicate_side_effect_confirmed`.

### 13.3. Lock acquisition timeout chưa chắc là sự cố Redis

Đôi khi lock được giữ bởi một worker hợp lệ vì công việc mất nhiều thời gian. Tỷ lệ acquire timeout tăng có thể do business contention, worker kẹt hoặc Redis latency.

Cần tương quan:

```text
lock_wait_duration
lock_acquire_result
worker_processing_duration
Redis command latency
business completion ratio
```

Đừng mặc định tăng TTL lock hoặc số connection pool sẽ sửa được mọi lock timeout.

## 14. Redis Streams: cảnh báo theo thời gian hoàn tất công việc

Với Redis Streams consumer group, số entry trong stream và pending count chỉ là **dấu hiệu**, không phải SLI nghiệp vụ hoàn chỉnh.

Luồng:

```text
Producer XADD
     |
     v
Redis Stream
     |
     v
XREADGROUP / ReadOffset.lastConsumed()
     |
     v
Business handler
     |
     v
Commit side effect
     |
     v
XACK
```

Một message có thể đã được giao nhưng vẫn nằm trong Pending Entries List (PEL) nếu handler chưa hoàn tất/ACK.

### 14.1. Cảnh báo quan trọng nhất: tuổi công việc chưa hoàn thành

Ví dụ yêu cầu:

```text
99.9% order-confirmation events hoàn thành trong 60 giây.
```

Số message pending = 100 chưa đủ kết luận vi phạm SLA nếu workload đang xử lý 10.000 event/s trong vài giây. Ngược lại, chỉ 1 message pending **30 phút** cũng có thể làm một đơn hàng bị kẹt.

Nên đo:

- `processing_delay_seconds` từ thời điểm event được tạo tới side effect hoàn thành.
- Oldest uncompleted business event age.
- Số event chưa hoàn tất theo loại.
- Successful completions/sec so với arrivals/sec.
- Retry/claim count.
- Handler failure ratio.
- Pending entries và consumer lag.

### 14.2. `XINFO GROUPS` lag không phải số event failed

Một group có thể có `lag=0` nhưng vẫn còn pending entries chưa ACK. Đó là trường hợp entry đã được giao hết nhưng xử lý chưa hoàn tất.

Ngược lại, pending count = 0 không chứng minh mọi event được xử lý nếu code **ACK quá sớm**, group được tạo từ `$` hoặc entry đã bị trim.

Đối với SLA công việc, cần một **business completion metric**, không dùng mỗi Redis group lag.

### 14.3. Các cảnh báo theo tầng

| Tầng | Dấu hiệu | Mức xử lý |
|---|---|---|
| Early warning | Backlog tăng nhanh, consumer rate thấp hơn producer rate | Warning, xem capacity |
| SLO risk | Oldest unprocessed age tiến gần deadline | Page nếu dự báo sẽ vi phạm cam kết |
| Impact | Event vượt SLA hoặc completion ratio không đạt SLO | Page |
| Recovery failure | Pending age lớn, claim không hiệu quả | Escalate tới stream/worker owner |
| Data loss suspicion | Event ID nguồn không tồn tại trong stream/hoàn tất record | Điều tra dữ liệu, không chỉ tăng consumers |

### 14.4. Không dùng timestamp của Stream ID làm nguồn thời gian duy nhất

Redis Stream ID có dạng `milliseconds-sequence`, nhưng nó không nhất thiết là thời gian **nghiệp vụ tạo event** trong mọi kiến trúc. Nếu event được ghi muộn, imported, hoặc có quy tắc ID riêng, tính `now - streamIdTimestamp` có thể sai.

Tốt hơn là ghi `eventCreatedAt` từ nguồn đáng tin cậy vào payload/metadata và đo:

```text
business event created -> handler committed
```

Cần đồng bộ clock và xử lý clock skew khi thu metric.

## 15. Pub/Sub: connection up không chứng minh nhận đủ sự kiện

Redis Pub/Sub không có durable backlog cho subscriber đã offline. Một `RedisMessageListenerContainer` có thể reconnect thành công sau failover nhưng **các message trong khoảng gián đoạn không được replay**.

Các chỉ số:

- Listener subscription state.
- Số lần disconnect/reconnect.
- Message publish count ở producer.
- Message received count ở subscriber.
- Handler processing error.
- Business freshness/version mismatch.
- Thời điểm reconciliation cuối cùng thành công.

### 15.1. “Published - received” có luôn là số message mất?

Không đơn giản. Với Pub/Sub:

- Một publish có thể tới nhiều subscriber.
- Một subscriber có thể subscribe nhiều pattern chồng lấp.
- Có thể có nhiều replicas/instances tiêu thụ.
- Metric producer/subscriber có thể ở các phạm vi/clock khác nhau.
- Message filtering, race lúc subscribe, restart hoặc scale làm số đếm khác nhau.

Muốn đo loss chính xác hơn, cần **event ID, expected recipients và đối chiếu** theo contract nghiệp vụ. Nếu chỉ cần invalidation notification, có thể đo **độ cũ dữ liệu** và dùng periodic reconciliation thay vì yêu cầu khớp mọi số đếm Pub/Sub.

### 15.2. Alert theo correctness, không chỉ disconnect

Một Pub/Sub listener disconnect trong 3 giây có thể không đáng page nếu có TTL/reconciliation, nhưng 3 giây đó có thể khiến giá trị quyền truy cập không được invalidate trong một workflow bảo mật.

Mức severity phải theo **dữ liệu mà notification quản lý** và khả năng tự phục hồi.

## 16. Redis server metrics: dùng làm ngữ cảnh và cảnh báo rủi ro

Redis `INFO` cung cấp nhiều chỉ số qua các phần như:

```redis
INFO stats
INFO clients
INFO memory
INFO commandstats
INFO persistence
INFO replication
INFO cpu
```

Một số công cụ như Redis exporter có thể chuyển các trường này thành Prometheus metrics, nhưng **tên series tùy exporter và phiên bản**. Không được viết alert giả định `redis_memory_used_bytes` hay `redis_connected_clients` luôn tồn tại nguyên dạng trên mọi cluster.

### 16.1. Memory pressure

Theo dõi:

- `used_memory` và `maxmemory`.
- `used_memory_rss`.
- `used_memory_peak`.
- `mem_fragmentation_ratio` trong bối cảnh phù hợp.
- `evicted_keys` tăng theo thời gian.
- `mem_not_counted_for_evict` nếu có.
- Cgroup/container memory và OOM events.
- Free disk nếu AOF/RDB bật.

Một cảnh báo memory tốt phân biệt:

```text
Cache instance:
  eviction tăng có thể chấp nhận trong một mức
  nhưng hit rate giảm và DB overload mới gây impact

Session / critical state:
  eviction không mong muốn có thể gây mất phiên/dữ liệu
  cần cảnh báo sớm hơn
```

### 16.2. Client connections

Theo dõi:

```redis
INFO clients
INFO stats
CONFIG GET maxclients
```

Các tín hiệu:

- `connected_clients`.
- `blocked_clients`.
- `rejected_connections`.
- Pool active/idle/waiters ở ứng dụng.
- Command timeout và connection error.

`blocked_clients` trên Redis không đồng nghĩa số Java threads đang chờ borrow pool. Một hệ thống có thể có pool hết connections nhưng Redis server vẫn thấy ít clients.

### 16.3. Command latency

Đo từ application và Redis:

- Lettuce/Jedis command latency nếu instrumentation bật.
- Micrometer Timer cho thao tác nghiệp vụ.
- `SLOWLOG`/Redis latency monitor.
- CPU và network RTT.
- Lua script duration nếu có.

`SLOWLOG` không đo toàn bộ thời gian client đợi pool hoặc network, vì vậy không có slowlog entry chưa chứng minh dependency không gây latency.

## 17. Persistence: cảnh báo theo rủi ro độ bền dữ liệu

Nếu Redis là cache có thể tái tạo, snapshot/AOF failure có thể ít nghiêm trọng hơn khi Redis là nơi giữ state không thể mất.

Các tín hiệu cần xem từ `INFO persistence`:

| Trường | Ý nghĩa |
|---|---|
| `rdb_last_bgsave_status` | Kết quả snapshot gần nhất |
| `rdb_last_save_time` | Lần snapshot thành công gần nhất |
| `rdb_bgsave_in_progress` | Snapshot nền đang chạy |
| `rdb_last_cow_size` | COW của RDB job gần đây khi có |
| `aof_enabled` | AOF bật/tắt |
| `aof_last_bgrewrite_status` | Trạng thái rewrite gần đây |
| `aof_rewrite_in_progress` | Rewrite đang chạy |
| `aof_delayed_fsync` | Dấu hiệu fsync bị trễ |
| `aof_current_size` | Kích thước AOF theo Redis |
| `aof_last_cow_size` | COW của rewrite khi có |

Cần đặt ngưỡng trên:

- Thời gian từ lần snapshot thành công gần nhất, nếu RDB là cơ chế durability quan trọng.
- AOF write/fsync failures.
- Disk space/inodes.
- Duration của background jobs.
- Memory headroom cho fork/COW.
- RPO quan sát qua drill hoặc hệ thống đối chiếu.

**Không nên đồng nhất `BGSAVE in progress` với incident.** Đó có thể là hoạt động bình thường, chỉ đáng cảnh báo khi duration/latency/memory vượt ngân sách.

### 17.1. Một lỗi AOF có thể chưa làm HTTP lỗi ngay

Redis vẫn có thể đang phục vụ read trong khi khả năng ghi bền vững bị suy giảm. Nếu đợi đến khi checkout trả lỗi, đội vận hành có thể đã mất cơ hội xử lý storage.

Đây là ví dụ phù hợp cho cảnh báo **leading risk có severity cao**, đặc biệt khi Redis giữ state quan trọng.

## 18. Replication, Sentinel và Cluster: phân biệt health với impact

### 18.1. Replication lag

Redis replication thường bất đồng bộ. Lag tăng có thể mở rộng rủi ro mất các write gần nhất khi primary failover, dù request hiện tại vẫn trả thành công.

Cần đo:

- Replica link status.
- Replication offset/lag theo node.
- Số replica healthy.
- Mức mất dữ liệu chấp nhận (RPO).
- Redis persistence condition.
- Business writes được ACK và khả năng đối chiếu.

Alert có thể chia:

```text
Risk:
  replica lag lớn hơn mục tiêu + failover protection giảm

Impact:
  primary failover xảy ra, confirmed data mismatch/loss
```

Không kết luận `offset difference / commands per second` luôn bằng thời gian lag chính xác. Replication offset là vị trí trong byte stream, không phải số lệnh nghiệp vụ.

### 18.2. Sentinel quorum

Một Redis primary vẫn hoạt động nhưng Sentinel còn không đủ quorum/đa số để tự failover có thể là **nguy cơ HA**, chưa phải outage hiện tại.

Nếu đồng thời primary mất liên lạc và không thể promote replica, impact trở nên trực tiếp.

Cần route cảnh báo mất quorum tới đội hạ tầng sớm, nhưng page ngay hay tạo ticket phụ thuộc mức availability yêu cầu.

### 18.3. Redis Cluster

Theo dõi:

- Slot coverage của 16.384 slots.
- Trạng thái `cluster_state`.
- Primary/replica availability.
- `MOVED`, `ASK`, `TRYAGAIN`, `CLUSTERDOWN`/connection errors.
- Hot slots, mất cân bằng CPU/memory.
- Application errors cho multi-key `CROSSSLOT`.

Một `MOVED` trong resharding được client xử lý thành công có thể là hiện tượng bình thường. `CROSSSLOT` thường là lỗi tập key/lệnh, không phải sự cố Redis CPU. Đừng page chỉ vì có redirect nếu SLI vẫn tốt và topology thay đổi theo kế hoạch.

## 19. Alert theo error-budget burn rate

Một hướng đáng tin cậy là page khi service đang tiêu hao error budget quá nhanh.

Giả sử SLO availability là 99.9% trong 30 ngày, tỷ lệ lỗi cho phép:

\[
e = 1-0.999 = 0.001
\]

Burn rate:

\[
B = \frac{\text{observed error ratio}}{e}
\]

Nếu observed error ratio là 1.44%:

\[
B = \frac{0.0144}{0.001}=14.4
\]

Nghĩa là đang tiêu hao budget nhanh hơn **14.4 lần** tốc độ trung bình cho phép, nếu xu hướng kéo dài.

### 19.1. Vì sao kết hợp cửa sổ ngắn và dài?

- Cửa sổ ngắn phản ánh sự cố vừa xuất hiện.
- Cửa sổ dài lọc nhiễu và đánh giá tác động đáng kể.
- Dùng **cả hai** có thể phát hiện outage thực sự mà tránh page chỉ vì vài request lỗi trong vài giây.

Ví dụ một chính sách thường được cân nhắc cho SLO 30 ngày:

```text
Fast burn:
  burn rate > 14.4 trong cửa sổ 1 giờ
  VÀ burn rate > 14.4 trong cửa sổ 5 phút

Slow burn:
  burn rate > 6 trong cửa sổ 6 giờ
  VÀ burn rate > 6 trong cửa sổ 30 phút
```

Đây chỉ là **ví dụ về mẫu multiwindow burn-rate alert**, không phải thiết lập mặc định cho mọi dịch vụ. SLO, traffic và error classification của ứng dụng cần quyết định những thông số thực tế.

### 19.2. Tách lỗi nghiệp vụ hợp lệ khỏi lỗi hệ thống

Nếu khách hàng nhập sai mật khẩu, API trả `401` có thể là kết quả **hợp lệ** của login journey, không phải failure của dịch vụ. Nếu `401` xuất hiện do Redis session không đọc được và code chuyển lỗi thành unauthenticated, đó có thể là lỗi dịch vụ.

SLI phải đo **valid requests** và phân loại kết quả theo contract nghiệp vụ, không chỉ lấy tổng `status >= 400`.

## 20. Ví dụ Prometheus recording rules cho business SLI

Giả sử ứng dụng đã chủ động xuất metric counter:

```text
app_business_requests_total{
  service="checkout",
  journey="create_order",
  result="success|failure"
}
```

Trong Prometheus, `_total` là một counter tăng dần. Ta tính error ratio của một journey theo các cửa sổ 5 phút và 1 giờ.

File rules minh họa:

```yaml
groups:
  - name: business-sli
    interval: 30s
    rules:
      - record: business:journey_requests:rate5m
        expr: |
          sum by (service, journey) (
            rate(app_business_requests_total[5m])
          )

      - record: business:journey_errors:rate5m
        expr: |
          sum by (service, journey) (
            rate(app_business_requests_total{result="failure"}[5m])
          )

      - record: business:journey_error_ratio:5m
        expr: |
          business:journey_errors:rate5m
          /
          clamp_min(business:journey_requests:rate5m, 1e-9)

      - record: business:journey_error_ratio:1h
        expr: |
          sum by (service, journey) (
            rate(app_business_requests_total{result="failure"}[1h])
          )
          /
          clamp_min(
            sum by (service, journey) (
              rate(app_business_requests_total[1h])
            ),
            1e-9
          )
```

Nếu metric còn labels như `environment`, `cluster` hoặc `tenant_tier`, recording rule phải giữ những labels dùng để phân vùng SLO/route alert phù hợp. Không tự gộp production và staging vào cùng ratio.

### 20.1. Cần xử lý cửa sổ rất ít traffic

Một tỷ lệ lỗi là:

```text
1 failure / 1 request = 100%
```

dù tác động tuyệt đối có thể nhỏ. Với hệ thống ít request, burn-rate alert có thể quá nhạy hoặc độ tin cậy thống kê thấp. Có thể kết hợp với:

- Số lượng request tối thiểu trong cửa sổ.
- Synthetic probes.
- Dead-man/absence alert.
- Ngưỡng đếm tuyệt đối cho journey có traffic thấp.
- Chỉ số kết quả business theo batch/event.

`clamp_min(..., 1e-9)` chỉ tránh chia cho 0; **không thay thế điều kiện traffic tối thiểu** hoặc phân biệt “không có request” với “100% request thành công”.

### 20.2. Tên metric là ví dụ, không phải series có sẵn

Micrometer có thể chuyển dấu chấm trong tên Java sang dấu gạch dưới cho Prometheus. Hình thức cuối cùng phụ thuộc registry và cấu hình. Trước khi dùng PromQL, phải kiểm tra exporter đang thực sự xuất tên/labels nào.

## 21. Ví dụ alert rule cho tác động business

Giả sử recording rules ở trên đang có dữ liệu cho journey `create_order`, SLO 99.9%.

```yaml
groups:
  - name: business-impact-alerts
    rules:
      - alert: OrderCreationFastErrorBudgetBurn
        expr: |
          (
            business:journey_error_ratio:5m{
              service="checkout",
              journey="create_order"
            } > 0.0144
          )
          and on (service, journey)
          (
            business:journey_error_ratio:1h{
              service="checkout",
              journey="create_order"
            } > 0.0144
          )
          and on (service, journey)
          (
            business:journey_requests:rate5m{
              service="checkout",
              journey="create_order"
            } > 0.1
          )
        for: 2m
        labels:
          severity: critical
          owning_team: checkout
          signal: business_impact
        annotations:
          summary: "Order creation đang tiêu hao error budget nhanh"
          description: |
            Tỷ lệ lỗi journey create_order vượt ngưỡng fast-burn
            trong cửa sổ ngắn và dài. Kiểm tra checkout endpoint,
            idempotency Redis, database và payment dependencies.
          runbook: "https://runbooks.example.internal/checkout/create-order"
```

`runbooks.example.internal` là URL **giữ chỗ minh họa**, không phải địa chỉ có thật được xác nhận.

### 21.1. Ý nghĩa ngưỡng traffic

Biểu thức:

```promql
business:journey_requests:rate5m > 0.1
```

yêu cầu trên khoảng 0.1 request/s, tức xấp xỉ 30 request trong 5 phút. Ngưỡng này chỉ để minh họa việc lọc cửa sổ quá ít traffic; nên chọn từ mức traffic thực tế và độ quan trọng của journey.

Với một hệ thống xử lý thanh toán giá trị lớn, một sự cố tính đúng đắn duy nhất vẫn có thể nghiêm trọng, nên **phải có alert invariant riêng**, không dựa hoàn toàn vào traffic gate.

### 21.2. Tránh duplicate pages

Nếu nhiều Redis-backed endpoints cùng lỗi, alert theo từng endpoint có thể tạo hàng chục pages. Cần grouping và routing theo service/journey, đồng thời link tới dashboard triệu chứng Redis để điều tra.

Không nên tắt business alerts chỉ vì một Redis infrastructure alert đã nổ; các alert nghiệp vụ cho biết thực sự đã ảnh hưởng đến đâu.

## 22. Ví dụ alert về Redis cache fallback

Giả sử ứng dụng xuất counter:

```text
app_cache_access_total{
  cache="products",
  outcome="hit|miss|redis_error"
}
```

Có thể phát hiện tỷ lệ Redis read error tăng:

```promql
sum(rate(app_cache_access_total{
  cache="products",
  outcome="redis_error"
}[5m]))
/
clamp_min(
  sum(rate(app_cache_access_total{
    cache="products"
  }[5m])),
  1e-9
)
> 0.05
```

Nếu metric `app_cache_access_total` chỉ ghi hit/miss/error **một lần cho mỗi attempted read**, ratio có ý nghĩa. Nếu code ghi nhiều outcomes cho một request, mẫu số cần đổi để tránh đếm trùng.

Khi tỷ lệ lỗi Redis tăng nhưng fallback DB còn chịu tải, đây có thể là warning. Page nếu:

- Product page latency SLO burn cao.
- DB pool gần hết với tỷ lệ fallback tăng.
- Error rate của business journey tăng.
- Cache invalidation failures gây dữ liệu stale vượt giới hạn.

Không đặt rule “Redis cache error > 5% = critical” cho mọi service mà không xét tác động và fallback.

## 23. Cảnh báo latency theo phân phối, không theo một request chậm

Nếu Micrometer Timer xuất Prometheus histogram với bucket:

```text
app_business_request_duration_seconds_bucket
```

có thể tính latency quantile:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, journey) (
    rate(app_business_request_duration_seconds_bucket[5m])
  )
)
```

Nhưng cần thận trọng:

- Histogram phải thực sự được bật và bucket phù hợp với latency target.
- p99 từ histogram là một ước lượng theo bucket.
- p99 tại thời điểm traffic thấp dễ nhiễu.
- Một quantile vượt ngưỡng không tự nói **bao nhiêu request** đã vi phạm SLO.
- Với latency SLO, thường nên đo tỷ lệ request **trong/ngời ngưỡng** bằng bucket hoặc event classification, rồi tính error-budget burn.

Ví dụ nếu SLO quy định 99.9% request dưới 500 ms, có thể dùng bucket `le="0.5"` nếu histogram có boundary đó:

```promql
1 -
(
  sum(rate(app_business_request_duration_seconds_bucket{
    journey="view_product",
    le="0.5"
  }[5m]))
  /
  clamp_min(
    sum(rate(app_business_request_duration_seconds_count{
      journey="view_product"
    }[5m])),
    1e-9
  )
)
```

Đây là tỷ lệ request vượt 500 ms **trong phạm vi các series được chọn**, cần lọc đúng môi trường/service và xử lý semantics về failed requests nếu đo latency SLO kết hợp availability.

## 24. Cảnh báo Redis Streams từ deadline của event

Giả sử các event xác nhận đơn hàng phải hoàn tất trong 60 giây. Một số metric đề xuất:

```text
app_stream_processing_delay_seconds_bucket{
  group="order-confirmations"
}
app_stream_uncompleted_events{
  group="order-confirmations"
}
app_stream_oldest_uncompleted_age_seconds{
  group="order-confirmations"
}
```

Trong đó `oldest_uncompleted_age_seconds` là **gauge do application/reconciler tính** từ nguồn event nghiệp vụ, không khẳng định Redis exporter tự tạo nó.

Một cảnh báo rủi ro:

```yaml
- alert: OrderConfirmationDeadlineAtRisk
  expr: |
    app_stream_oldest_uncompleted_age_seconds{
      group="order-confirmations"
    } > 45
    and on (group)
    app_stream_uncompleted_events{
      group="order-confirmations"
    } > 0
  for: 2m
  labels:
    severity: warning
    owning_team: orders
  annotations:
    summary: "Event xác nhận đơn hàng gần vượt deadline 60 giây"
```

Nếu deadline thực tế là 60 giây, ngưỡng 45 giây giúp phát hiện sớm. Nhưng `for: 2m` có thể khiến cảnh báo kích hoạt **sau khi SLA đã bị vi phạm**; do đó phải chọn cửa sổ/threshold dựa trên tốc độ tăng backlog và mục tiêu phản ứng.

Với tác động đã xảy ra, có thể xây rule riêng:

```text
oldest_uncompleted_age > 60 seconds
OR overdue business events > 0
```

Nếu một event overdue luôn quan trọng, không nên chỉ dùng `for: 10m` vì sẽ làm trễ phản ứng.

### 24.1. Gauge phải chính xác theo tập event nào?

Một gauge “oldest pending age” được tính chỉ từ PEL có thể bỏ sót event **chưa từng được group giao**. Một gauge chỉ từ Redis group lag có thể bỏ sót pending đã giao nhưng chưa ACK.

Để đo deadline end-to-end, reconciler cần xem **tất cả event chưa hoàn tất theo business contract**, không chỉ một trạng thái Redis riêng lẻ. Điều này có thể yêu cầu sự kiện có ID, status store/outbox và cơ chế đối chiếu độc lập.

## 25. Phát hiện dữ liệu stale thay vì chỉ quan sát Pub/Sub disconnect

Giả sử app dùng Redis Pub/Sub để invalidate local cache giữa các nodes.

```text
Product updated
    |
    v
Publisher sends invalidation
    |
    +--> Service A listener -> evict local cache
    +--> Service B listener -> evict local cache
```

Nếu Service B offline vài giây, nó có thể bỏ lỡ thông báo, sau đó giữ local cache cũ.

Một cảnh báo có ý nghĩa hơn:

```text
Data freshness violations > budget
```

Cách xây:

1. Gắn `version` hoặc `updatedAt` vào data.
2. Có một luồng reconciliation kiểm tra sampled data hoặc các key quan trọng.
3. Đo tuổi dữ liệu trả về so với nguồn sự thật.
4. Chỉ page nếu vượt giới hạn nghiệp vụ.
5. Để subscription disconnect/reconnect làm context warning và căn cứ điều tra.

Không nên viết metric “PubSub lost messages” như thể Redis cung cấp một bộ đếm chắc chắn cho mọi subscriber và mọi thời điểm. Nếu cần delivery bền vững, xem Redis Streams hoặc broker khác thay vì cố làm cảnh báo thay thế semantics.

## 26. Phối hợp alert Redis với DB và API downstream

Khi Redis cache fail-open, tải có thể chuyển sang database:

```text
Redis error
    |
    v
Fallback to DB
    |
    +-- DB có headroom -> user vẫn ổn
    |
    +-- DB gần full pool -> latency tăng
    |
    +-- DB saturation -> user-visible errors
```

Đây là chuỗi **dependency failure propagation**.

Một bộ cảnh báo tốt có thể gồm:

- Redis cache error rate.
- Fallback-to-DB rate.
- DB connection pool active/waiters.
- DB query latency.
- Product endpoint success/latency SLI.
- Saturation của HTTP worker/event-loop.

Nếu Redis lỗi mà downstream hoàn toàn đủ headroom, tạo ticket để điều tra Redis là hợp lý. Nếu DB bắt đầu gần saturation, có thể cần page **trước khi** user errors tăng cao.

### 26.1. Không kết hợp tất cả điều kiện theo kiểu bắt buộc cùng xảy ra

Một alert quá chặt:

```text
Redis error high
AND DB CPU high
AND HTTP 5xx high
```

có thể bỏ sót sự cố quan trọng nếu metric DB bị mất, hoặc Redis không phải nguyên nhân. Business SLO alert nên **độc lập** với Redis metrics; các metric phụ thuộc dùng làm context và alert nguy cơ riêng.

## 27. Alert routing: ai cần nhận và xử lý?

Một cảnh báo tốt phải có owner rõ.

Ví dụ:

| Alert | Primary owner | Secondary owner |
|---|---|---|
| Checkout SLO burn | Checkout team | SRE + Payments |
| Session error spike | Identity team | Platform/Redis |
| Stream processing deadline | Event processor team | Redis platform |
| Redis disk nearly full | Infra/Redis platform | On-call service phụ thuộc |
| Cache fallback + DB saturation | Product API team | Database + Redis |
| Sentinel quorum loss | Redis platform | SRE |
| Confirmed duplicate side effect | Owning business service + incident lead | Data/Payments |
| Redis exporter missing | Monitoring/Platform | On-call theo service |

Không cần mọi cảnh báo Redis gửi đến mọi nhóm. Một Redis primary chung có thể gây ảnh hưởng nhiều dịch vụ, nhưng paging tất cả đồng thời tạo alert storm và mất người điều phối.

### 27.1. Route theo impact, không chỉ theo instance

Một nhãn:

```text
redis_instance="redis-01"
```

hữu ích khi điều tra, nhưng `redis-01` không nói journey nào bị ảnh hưởng.

Labels bổ sung:

```text
service="checkout"
journey="create_order"
owning_team="checkout"
severity="critical"
```

được dùng để route business alert. Với infrastructure alert, có thể route theo `cluster`/`redis_owner` và link đến service dependency map.

## 28. Ví dụ Alertmanager routing và grouping

File Alertmanager rút gọn, chỉ minh họa cấu trúc:

```yaml
route:
  receiver: platform-default
  group_by: ['alertname', 'environment', 'owning_team']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
        - owning_team="checkout"
      receiver: checkout-oncall

    - matchers:
        - severity="critical"
        - owning_team="identity"
      receiver: identity-oncall

    - matchers:
        - owning_team="redis-platform"
      receiver: redis-platform

receivers:
  - name: platform-default
    # Receiver integration cần cấu hình thật của tổ chức.
  - name: checkout-oncall
  - name: identity-oncall
  - name: redis-platform
```

Đây **không phải file hoàn chỉnh có thể gửi notification ngay**. Phải cấu hình Slack/PagerDuty/webhook/email integration hợp lệ, credentials qua secrets và kiểm tra syntax theo Alertmanager version.

### 28.1. Grouping không được che impact khác nhau

Nếu group theo mỗi `redis_instance`, nhiều journey quan trọng có thể bị gộp thành một alert khó nhìn tác động. Nếu group theo mọi Redis key, số notification có thể bùng nổ.

Một grouping hợp lý thường giữ:

```text
environment + owning_team + alertname/service
```

và bổ sung notification nội dung mô tả số lượng journey/instances ảnh hưởng.

## 29. Cảnh báo phải có runbook và hành động cụ thể

Một alert chỉ ghi:

```text
Redis connected clients high.
```

buộc người trực tự đoán vấn đề. Một alert tốt nên có:

- **Impact:** user journey nào, bao nhiêu request/event bị ảnh hưởng?
- **SLO:** đang vi phạm ngưỡng nào và trong cửa sổ nào?
- **Scope:** môi trường, service, Redis cluster/role liên quan.
- **Current symptoms:** tỷ lệ lỗi/latency/backlog.
- **Possible causes:** những hướng điều tra, không khẳng định khi chưa có bằng chứng.
- **Runbook:** lệnh/metrics/dashboard cần xem.
- **Owner/escalation:** ai nhận đầu tiên.
- **Safety guardrails:** thao tác nào không được làm tùy tiện.
- **Recovery criteria:** điều kiện xác định đã phục hồi.

Ví dụ nội dung một page:

```text
P2 — Order confirmation backlog vượt deadline

Impact:
  37 events chưa hoàn tất quá 60 giây.
  User journey: order confirmation.

Symptoms:
  Worker completion throughput giảm.
  Redis Stream pending age tăng.
  DB latency cũng tăng.

Check:
  - Worker error logs + event IDs
  - XPENDING / XINFO GROUPS
  - Handler duration / DB pool usage
  - Consumer group ACK/reclaim state

Do not:
  - XACK toàn bộ pending chỉ để dọn dashboard
  - XTRIM stream chưa xử lý
  - Retry side effect không idempotent

Recovery:
  Overdue events giảm về mức cho phép.
  Completion success ratio trở lại SLO.
```

## 30. Runbook theo nhóm sự cố Spring Data Redis

### 30.1. Redis connection timeout

Kiểm tra:

```redis
INFO clients
INFO stats
INFO commandstats
SLOWLOG GET 20
```

Đồng thời xem:

- Client command timeout và connect timeout.
- Pool borrow waiters, active/idle.
- Reconnect count.
- Redis CPU, memory, network.
- Redis Sentinel/Cluster topology.
- DNS/TLS/authentication issues.
- Request error ratio và business impact.

Không chỉ tăng `max-active` hoặc timeout mà chưa xác định bottleneck.

### 30.2. Redis memory/eviction

Kiểm tra:

```redis
INFO memory
INFO stats
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Xác định Redis là cache hay chứa state quan trọng. Với cache, eviction có thể chấp nhận; với session/idempotency, eviction có thể vi phạm yêu cầu dữ liệu.

Không thay `maxmemory-policy` trên production trong lúc incident nếu chưa đánh giá dữ liệu nào sẽ bị loại.

### 30.3. Stream pending backlog

Kiểm tra:

```redis
XINFO STREAM stream:orders
XINFO GROUPS stream:orders
XINFO CONSUMERS stream:orders order-workers
XPENDING stream:orders order-workers
```

Đối chiếu:

- Producer traffic.
- Handler success/error.
- Last-delivered ID, lag, pending.
- Oldest uncompleted business events.
- Claim/retry policy.
- Downstream DB/API latency.

Không ACK những message chưa xử lý thành công chỉ để pending count về 0.

### 30.4. Persistence failure

Kiểm tra:

```redis
INFO persistence
INFO memory
```

và metrics disk bytes/inodes, fsync latency, container OOM, fork/COW. Nếu RDB/AOF failure đang đe dọa durability, phải theo runbook backup/incident response; không tự tắt persistence hoặc xóa AOF active files.

## 31. Tránh alert fatigue và alert storm

Nếu mỗi Redis instance có 20 cảnh báo metric và cụm 30 instances gặp sự cố mạng, hệ thống có thể tạo hàng trăm pages cùng lúc.

Một số cách giảm nhiễu:

1. **Page theo business impact hoặc rủi ro cao có hành động rõ**.
2. Dùng Redis infrastructure alerts như context, warning hoặc ticket khi chưa có impact.
3. Group alert theo nguyên nhân/phạm vi hợp lý.
4. Dùng inhibition khi một nguyên nhân rộng đã xác nhận làm những symptoms phụ không cần page riêng.
5. Dùng `for` để lọc spike ngắn với những metric phù hợp.
6. Đặt điều kiện `absent()` hoặc source-health riêng để biết khi metric không còn được thu.
7. Không dùng dynamic labels tạo alert mới cho mỗi user/key.
8. Tạm mute có thời hạn trong maintenance đã phê duyệt.
9. Định kỳ xem alert nào **không dẫn tới hành động** và điều chỉnh.

### 31.1. Vì sao inhibition phải thận trọng?

Nếu Redis Cluster down, có thể muốn suppress 50 warnings `RedisCommandTimeout`. Nhưng không nên tự động suppress mọi **business SLO alert**, vì các team vẫn cần biết người dùng đang bị ảnh hưởng và recovery đã hoàn tất chưa.

Inhibition nên giảm thông báo trùng về triệu chứng, **không che sự cố tính đúng đắn hoặc user impact**.

### 31.2. Chọn `for` theo semantics

Các loại sự cố khác nhau cần thời gian chờ khác nhau:

- Redis CPU spike ngắn: có thể dùng `for` dài hơn để tránh nhiễu.
- Một lần mất quorum khi primary vẫn khỏe: cảnh báo rủi ro có thể chờ điều kiện ổn định.
- Duplicate payment được xác nhận: không hợp lý chờ thêm 15 phút chỉ để đủ `for`.
- Stream event đã vượt deadline: `for` quá dài có thể làm trễ vi phạm SLA.
- Fast error-budget burn: thường dùng cặp cửa sổ và có thể `for` rất ngắn.

Không áp cùng một `for: 5m` cho tất cả cảnh báo chỉ vì template YAML dùng như vậy.

## 32. Alert khi thiếu metric hoặc scrape thất bại

Một vấn đề nguy hiểm: khi Redis hoặc exporter mất kết nối, các series có thể **biến mất**, khiến một biểu thức như:

```promql
redis_connected_clients > 1000
```

không còn trả dữ liệu. Không có alert **không đồng nghĩa system đã khỏe**.

Nên có alert cho:

- Prometheus target `up == 0` đối với ứng dụng/exporter quan trọng.
- Số samples/scrape giảm bất thường.
- Một metric nghiệp vụ bắt buộc biến mất ngoài thời gian maintenance.
- Synthetic probe không chạy hoặc không báo kết quả.
- Alertmanager notification pipeline không hoạt động.
- Recording rules thất bại hoặc trả dữ liệu rỗng.

Ví dụ:

```promql
up{job="redis-exporter",environment="production"} == 0
```

Trong thực tế, cần biết sự khác nhau giữa:

```text
up == 0: target tồn tại nhưng scrape thất bại
absent(up{...}): không có time series target phù hợp
```

Một service bị xóa khỏi service discovery có thể không tạo `up == 0`; nên có quy tắc absence phù hợp với danh sách targets/desired replicas.

## 33. Dashboard theo business journey và dependency

Một dashboard dễ dùng trong incident nên đi từ trên xuống:

```text
BUSINESS:
  Login SLO, Checkout SLO, Product latency,
  Event completion delay, confirmed correctness violations

DEPENDENCY:
  Cache miss/error/fallback,
  Lock/idempotency outcome,
  Stream pending/lag/processing age,
  Pub/Sub listener state

REDIS:
  command latency, clients, CPU, memory,
  eviction, replication, persistence,
  Sentinel/Cluster topology

PLATFORM:
  DB connection pool, network RTT,
  container OOM, disk latency, JVM GC
```

Không đặt 100 biểu đồ Redis `INFO` lên một trang rồi yêu cầu on-call tự tìm thứ liên quan tới người dùng.

### 33.1. Chỉ số “đang khỏe” và “đang nguy hiểm”

Ví dụ bảng tóm tắt:

| Business capability | Availability/quality | Redis symptom | Recovery status |
|---|---|---|---|
| Product reads | SLO đạt / không đạt | Cache errors, fallback | DB headroom |
| Login | SLO đạt / không đạt | Session errors | Session store health |
| Checkout | SLO đạt / không đạt | Lock/idempotency errors | Duplicate risk |
| Order notifications | Deadline đạt / không đạt | Stream backlog | Oldest pending/claim |
| Data freshness | Stale ratio | Pub/Sub/reconcile | Last successful sync |

Đây là cách đưa metrics về **quyết định vận hành**, thay vì chỉ làm đẹp dashboard.

## 34. Đặt ngưỡng dựa trên baseline và ngân sách rủi ro

Một số ngưỡng Redis truyền thống:

```text
CPU > 80%
Memory > 80%
Pool active > 90%
Replication lag > 100 MB
```

không tự nói chúng có nguy hiểm không. Một hệ thống có CPU Redis 85% ổn định nhưng p99 tốt có thể đang được sử dụng hiệu quả. Một hệ thống chỉ 20% CPU nhưng single-thread blocking script gây tail latency lại đáng lo.

Phương pháp định ngưỡng:

1. Xác định SLO nghiệp vụ và giới hạn dữ liệu.
2. Ghi baseline ở traffic bình thường và peak.
3. Chạy stress test để tìm điểm saturation.
4. Xác định những signals thay đổi **trước** SLO vi phạm.
5. Chọn ngưỡng có đủ lead time để phản ứng.
6. Đo false positives và false negatives.
7. Điều chỉnh ngưỡng sau incident/drill.
8. Ghi rõ các trường hợp maintenance, planned failover và traffic seasonality.

### 34.1. Dự báo thời gian hết headroom

Nếu disk còn 20 GiB và AOF đang tăng 10 GiB/giờ, cảnh báo theo `% disk used` có thể đến quá muộn.

Có thể ước lượng:

```text
time-to-exhaustion
    = free_capacity / recent_positive_growth_rate
```

Đây là mô hình đơn giản, phải xử lý growth rate thay đổi, rewrite giảm size, storage reservation và việc metric bị thiếu. Nhưng nó thể hiện đúng ý tưởng: **cảnh báo khi thời gian xử lý còn ít hơn thời gian hệ thống cần để phản ứng**, không chỉ khi một con số vượt ngưỡng tùy ý.

## 35. Kịch bản kiểm thử alert bằng Testcontainers và fault injection

Một rule chưa được thử có thể là “cảnh báo trên giấy”. Nên kiểm thử cả **metric emitted**, **rule evaluation**, **routing** và **runbook**.

### 35.1. Cache Redis unavailable

Trên môi trường test cô lập:

1. Khởi động Spring Boot và Redis bằng Testcontainers.
2. Gửi request có cache hit/miss baseline.
3. Ngắt kết nối Redis bằng proxy hoặc điều khiển container.
4. Kiểm tra `app_cache_access_total{outcome="redis_error"}` tăng.
5. Kiểm tra fallback DB được gọi và có metric riêng.
6. Nếu business SLO còn đạt, không phát cảnh báo P1 sai.
7. Nếu DB bị bão hòa, alert business impact phải được kích hoạt.
8. Khôi phục Redis, kiểm tra metric/alert kết thúc theo điều kiện rõ.

### 35.2. Session store lỗi

1. Dùng session store thật và login test users.
2. Tạo Redis unavailable hoặc serializer incompatibility theo kịch bản.
3. Kiểm tra tỷ lệ authenticated requests thất bại.
4. Xác nhận alert route tới Identity on-call.
5. Đảm bảo hành vi lỗi không bị ghi nhầm là logout hợp lệ.

### 35.3. Stream consumer bị dừng

1. Tạo event có `eventId` và thời điểm tạo.
2. Dừng consumer nhưng giữ producer.
3. Xác nhận backlog/uncompleted age tăng.
4. Kiểm tra warning trước deadline và critical sau khi breach.
5. Khởi động consumer/reclaim, xác nhận side effect xử lý idempotent.
6. Kiểm tra alert phục hồi khi overdue count giảm theo contract.

### 35.4. Redis failover

Với topology Sentinel/Cluster trong staging:

1. Dừng đúng primary thử nghiệm hoặc dùng planned failover.
2. Theo dõi reconnect và Redis command errors.
3. Đo business journey success/latency.
4. Xác nhận infra events được ghi lại.
5. Kiểm tra page nếu SLO burn cao, không page nếu failover thành công không gây impact vượt chính sách.
6. Kiểm tra recovery và rủi ro acknowledged-write loss theo nghiệp vụ.

Không thực hiện fault injection gây mất dữ liệu trên Redis production dùng chung khi chưa được phê duyệt và có kế hoạch khôi phục.

## 36. Kiểm thử Prometheus rules trước triển khai

Các rule YAML có thể đúng cú pháp nhưng sai nhãn hoặc trả series rỗng. Một quy trình:

- Lấy tên metric thật từ `/actuator/prometheus` hoặc endpoint exporter tương ứng.
- Kiểm tra labels và counter semantics.
- Dùng `promtool check rules` cho rule files.
- Dùng `promtool test rules` với test fixtures để xác nhận firing/recovery.
- Chạy trong staging có traffic hoặc synthetic samples.
- Kiểm tra Alertmanager receiver, grouping và inhibition.
- Test một trường hợp metric mất hoàn toàn.
- Xem có cảnh báo quá nhiều khi một sự cố lan ra nhiều pods không.
- Đảm bảo cảnh báo tự kết thúc khi SLI phục hồi, không bị giữ do recording rule sai.

Ví dụ test cases quan trọng:

```text
Case 1: 0 lỗi, traffic đủ      -> không fire
Case 2: lỗi ngắn trong 1 phút -> không page giả
Case 3: outage kéo dài        -> fire đúng severity
Case 4: không có traffic      -> không coi là 100% success
Case 5: exporter down         -> observability missing alert
Case 6: service rollout       -> không tạo 100 alerts trùng
Case 7: dữ liệu metric thiếu  -> không âm thầm coi là khỏe
```

Với low-traffic workflows, có thể cần synthetic test hoặc batch completion metrics thay vì chỉ rate trên request counter.

## 37. Thử nghiệm cảnh báo theo kịch bản kinh doanh

Một số ví dụ mang tính quyết định:

### 37.1. Product cache lỗi nhưng người dùng còn truy cập được

```text
Redis GET errors:            95%
Fallback success:            99.9%
Product page SLO:            vẫn đạt
Database connection usage:   55%
```

Hướng xử lý: cảnh báo Redis cache degraded, ưu tiên điều tra và theo dõi downstream capacity. Không nhất thiết đánh thức mọi nhóm bằng P1.

### 37.2. Cache lỗi làm database quá tải

```text
Redis GET errors:            95%
Fallback requests:           tăng 20 lần
Database connections:        98%
Product page p99:            vượt SLO
Product 5xx:                 tăng mạnh
```

Hướng xử lý: page theo Product business SLO, kèm Redis cache và DB saturation context. Đây là user-impacting incident.

### 37.3. Stream có ít pending nhưng event quan trọng bị kẹt

```text
Pending count:               1
Oldest uncompleted age:      25 phút
Business deadline:           2 phút
```

Hướng xử lý: cảnh báo theo overdue event dù pending count rất thấp. Điều tra handler, ownership/ACK/reclaim.

### 37.4. Redis CPU cao nhưng không ảnh hưởng

```text
Redis CPU:                   88%
GET p99:                     tốt
Business SLO:                đạt
Memory/disk headroom:        tốt
```

Hướng xử lý: theo dõi capacity/trend, có thể tạo ticket tối ưu. Không tự động P1 chỉ vì CPU 88%.

### 37.5. Một duplicate thanh toán được xác nhận

```text
HTTP 5xx:                    0%
Redis healthcheck:           UP
Confirmed duplicate charge:  1
```

Hướng xử lý: cảnh báo tính đúng đắn cấp cao theo chính sách, điều tra idempotency và database/payment invariants. Đây là ví dụ chứng minh **HTTP availability không bao phủ integrity**.

## 38. Review alert sau incident

Sau mỗi incident liên quan Redis, nên hỏi:

1. Cảnh báo đầu tiên là business SLI hay noise từ Redis metrics?
2. Cảnh báo có đến đủ sớm để giảm tác động không?
3. Có ai bị page sai, hoặc đội chịu trách nhiệm không được gọi?
4. Dashboard có phân biệt Redis error, cache miss và fallback không?
5. Có phát hiện duplicate/stale data không?
6. Redis exporter/metrics có bị mất đúng lúc sự cố không?
7. Có alert nào firing nhưng không dẫn đến hành động không?
8. Runbook có chỉ dẫn nguy hiểm như ACK hàng loạt, `FLUSHDB`, xóa AOF hoặc tăng retry vô hạn không?
9. Có cần thêm một SLI mới đại diện tốt hơn cho user journey không?
10. Có cần sửa ngưỡng/`for`/grouping hay quy trình rollback/deployment không?

Mục tiêu của review không phải chỉ làm “ít alert hơn”, mà là **ít thông báo vô ích hơn và phát hiện đúng sự cố quan trọng nhanh hơn**.

## 39. Bộ checklist triển khai

### 39.1. Business/SLO

- [ ] Mỗi Redis usage có owner và business journey liên quan.
- [ ] Các journey quan trọng có SLI/SLO rõ ràng.
- [ ] Có phân biệt availability, latency, freshness và correctness.
- [ ] Có alert invariant riêng cho duplicate/lock/data integrity.
- [ ] Có định nghĩa valid request và expected business outcome.
- [ ] Đã xác định RTO/RPO nếu Redis giữ state cần bền vững.

### 39.2. Application metrics

- [ ] Redis cache hit/miss/error/fallback là trạng thái riêng.
- [ ] Redis client timeout và command error có metric theo role/operation.
- [ ] Session read/write/deserialize errors có thể quan sát.
- [ ] Lock/idempotency outcomes được phân loại.
- [ ] Streams có processing delay và completion metric.
- [ ] Pub/Sub có listener health và freshness/reconciliation nếu cần.
- [ ] Metrics không chứa user ID, raw key hoặc order ID làm labels.

### 39.3. Redis/dependency metrics

- [ ] Thu Redis INFO clients/stats/memory/persistence/replication.
- [ ] Theo dõi Redis CPU/network/command latency.
- [ ] Theo dõi pool active/waiters và timeout ở phía Spring app.
- [ ] Có DB/downstream saturation metrics khi Redis là cache.
- [ ] Có trạng thái Sentinel/Cluster nếu dùng HA/sharding.
- [ ] Có cảnh báo observability missing khi exporter/scrape lỗi.

### 39.4. Alert policy

- [ ] Severity tính theo business impact hoặc risk có hành động.
- [ ] Fast-burn/slow-burn cho journey phù hợp.
- [ ] Có traffic gate hoặc synthetic signals cho low-traffic.
- [ ] `for` không làm trễ cảnh báo integrity hay deadline.
- [ ] Grouping/inhibition giảm noise nhưng không che business impact.
- [ ] Có owner, escalation, runbook và recovery criteria.
- [ ] Maintenance silence có thời hạn và quản trị rõ.

### 39.5. Testing/operations

- [ ] PromQL đã được kiểm tra với metric names thực.
- [ ] Rules được test về firing, recovery và missing-data.
- [ ] Receiver và routing được kiểm thử.
- [ ] Có fault injection test trong môi trường cô lập.
- [ ] Có kiểm thử Redis failover/reconnect nếu production dùng.
- [ ] Runbook tránh thao tác có thể mất dữ liệu.
- [ ] Có post-incident review để cải tiến SLI/alert.

## 40. Kết luận

**Thiết kế cảnh báo theo tác động nghiệp vụ** trong Spring Data Redis bắt đầu từ câu hỏi “người dùng hoặc luồng nghiệp vụ nào bị ảnh hưởng?” thay vì chỉ hỏi “Redis metric nào vượt ngưỡng?”.

Các nguyên tắc cốt lõi:

1. **Định nghĩa user journey, SLI và SLO trước**; sau đó ánh xạ Redis dependency và metrics kỹ thuật vào hành trình ấy.
2. **Phân biệt Redis dùng làm cache với Redis giữ state quan trọng**; cùng một timeout có thể mang mức severity rất khác nhau.
3. **Đo ba lớp:** business outcome, hành vi Spring Data Redis và trạng thái Redis server/topology.
4. **Dùng error-budget burn rate cho những SLO phù hợp**, thay vì chỉ page theo CPU/memory cố định.
5. **Theo dõi cả correctness và freshness**: duplicate payments, idempotency, lock ownership, cache stale và overdue Stream events có thể nghiêm trọng ngay cả khi HTTP 5xx thấp.
6. **Phân biệt cache miss với dependency error**; đo fallback và áp lực lên database.
7. **Dùng Redis metrics để chẩn đoán và dự báo rủi ro**: replication lag, AOF/RDB failure, memory headroom, pool waiters, blocked clients và Cluster/Sentinel health.
8. **Tránh alert fatigue** bằng severity rõ, grouping, inhibition thận trọng, labels ổn định và runbook có hành động cụ thể.
9. **Kiểm thử cả alert rules và incident scenarios**, kể cả trường hợp metrics biến mất, không traffic hoặc Redis failover không ảnh hưởng người dùng.
10. **Cải tiến sau mỗi incident** để cảnh báo đến đúng đội, đúng thời điểm và thể hiện đúng mức độ ảnh hưởng.

Hệ thống cảnh báo thành công không phải hệ thống có nhiều biểu đồ Redis nhất, mà là hệ thống giúp đội vận hành **nhận biết sớm những vi phạm hoặc nguy cơ nghiệp vụ thực sự**, xử lý an toàn và xác nhận sự phục hồi dựa trên trải nghiệm người dùng cùng tính đúng đắn của dữ liệu.
