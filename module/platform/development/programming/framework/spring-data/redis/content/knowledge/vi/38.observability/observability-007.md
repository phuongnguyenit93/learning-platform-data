# Phân biệt health check, readiness và khả năng chịu tải

Trong ứng dụng **Spring Data Redis**, việc Redis trả `PONG` khi gọi `PING` là một tín hiệu hữu ích, nhưng **không đồng nghĩa** ứng dụng đang sẵn sàng nhận request, tất cả thao tác Redis đều thành công hoặc hệ thống còn đủ năng lực phục vụ giờ cao điểm.

Một Redis server có thể trả `PING` trong vài mili giây nhưng đã chạm `maxmemory` và từ chối `SET`. Một application pod có thể chạy bình thường nhưng Redis Cluster thiếu slot hoặc client giữ topology cũ. Một service phụ thuộc Redis chỉ để cache có thể vẫn phục vụ bằng database dù Redis bị ngắt. Trong khi đó, một service dùng Redis làm nơi duy nhất giữ session hoặc hàng đợi tác vụ có thể không còn đáp ứng hợp đồng nghiệp vụ nếu Redis mất kết nối.

Muốn quan sát đúng, cần phân biệt ba câu hỏi:

1. **Health check:** thành phần hoặc thao tác cụ thể có đang hoạt động tại thời điểm kiểm tra không?
2. **Readiness:** instance ứng dụng này có nên được nhận **traffic mới** cho chức năng nó chịu trách nhiệm không?
3. **Khả năng chịu tải (*capacity/load tolerance*):** hệ thống còn **headroom** để duy trì throughput, độ trễ, tỷ lệ lỗi và giới hạn tài nguyên khi lưu lượng tăng không?

Ba câu hỏi có liên quan nhưng không thay thế được nhau. Bài học này triển khai cách thiết kế các phép kiểm tra và hệ thống giám sát bằng **Spring Boot Actuator, Spring Data Redis, Lettuce, Redis server metrics và Kubernetes probes**, đồng thời hướng dẫn cách đánh giá khi Redis là cache tùy chọn hoặc dependency bắt buộc.

## 1. Bản đồ tư duy: “sống”, “sẵn sàng” và “chịu tải”

```text
                      Ứng dụng Spring Boot
                               |
                  +------------+-------------+
                  |            |             |
                  v            v             v
               Liveness    Readiness      Capacity / SLO
                  |            |             |
             Process còn   Có phục vụ    Phục vụ BAO NHIÊU
             vận hành      request mới   request với p99,
             được không?   được không?   error rate, memory?
                  |            |             |
             Lỗi deadlock  Tùy Redis là   Redis CPU, clients,
             nghiêm trọng  critical hay  command latency,
             cần restart   optional      queue, pool, GC
```

**Liveness** hỏi “instance có đang ở trạng thái mà restart có cơ hội khôi phục không?”. **Readiness** hỏi “instance này có thể nhận thêm request mới ngay lúc này không?”. **Capacity** hỏi “tải hiện tại và tải dự kiến có vượt khả năng phục vụ đúng SLO không?”.

Ví dụ:

| Tình huống | Liveness app | Readiness app | Khả năng chịu tải |
|---|---|---|---|
| App hoạt động, Redis/cache bình thường, tải thấp | Tốt | Tốt | Còn headroom |
| Redis mất mạng, cache có fallback sang DB | Có thể tốt | Có thể vẫn ready | Có thể suy giảm vì DB phải gánh cache miss |
| Redis mất mạng, app không thể xác thực session | Có thể tốt | Có thể not ready tùy kiến trúc | Capacity chức năng có thể bằng 0 |
| Redis trả PING nhưng `SET` lỗi OOM | Tốt | Tùy write có bắt buộc không | Dưới yêu cầu cho workload ghi |
| Redis vẫn hoạt động, p99 tăng mạnh do hot key | Tốt | Có thể vẫn ready | Đang thiếu headroom/SLO vi phạm |
| App đang startup, chưa hoàn tất khởi tạo | Có thể chưa sẵn sàng | Not ready | Chưa đánh giá được |
| Application deadlock thật sự, không xử lý được yêu cầu | Có thể failed | Not ready | Không có khả năng phục vụ |
| Một Redis replica chậm nhưng primary vẫn phục vụ ghi | Tốt | Tùy read routing | Read capacity và độ mới dữ liệu có thể suy giảm |

Không nên biến mọi metric xấu thành `DOWN`. Nếu readiness nhấp nháy liên tục theo từng đợt latency tăng, load balancer có thể loại dần các pod, dồn thêm tải vào các pod còn lại và làm sự cố nặng hơn.

## 2. Phân biệt các thuật ngữ trước khi cấu hình

| Thuật ngữ | Nội dung kiểm tra | Hành động thường gắn với nó |
|---|---|---|
| **Component health** | Redis endpoint trả lời, một lệnh đơn chạy được | Cảnh báo/chẩn đoán |
| **Application liveness** | Tiến trình ứng dụng có thể tiếp tục hoạt động | Kubernetes có thể restart container |
| **Application readiness** | Có thể gửi traffic mới đến instance này | Kubernetes có thể loại/tái đưa pod vào Service endpoints |
| **Startup probe** | Ứng dụng đã có đủ thời gian để khởi động xong chưa | Trì hoãn quyết định liveness/readiness trong startup |
| **Capacity** | Công suất phục vụ, độ trễ, sử dụng tài nguyên, backlog | Scale, giới hạn tải, tối ưu |
| **SLO/SLI** | Kết quả user-facing được đo theo mục tiêu dịch vụ | Cảnh báo SLO/budget, ưu tiên khắc phục |
| **Durability/consistency** | Ghi có bền vững, đọc có đủ mới không | Kiểm soát dữ liệu, replication, fallback |

Một Redis health indicator thường kiểm tra một tập điều kiện **hẹp**. Nó không phải chứng nhận về tính nhất quán, khả năng failover, bảo mật của tất cả ACL commands hoặc năng lực phục vụ dưới tải.

## 3. “Redis PING thành công” thực sự chứng minh điều gì?

Ví dụ:

```bash
redis-cli -h redis.internal -p 6379 --user app_reader --askpass PING
```

Phản hồi mong đợi:

```text
PONG
```

Một lần `PING` thành công thường cho thấy:

- Client đã kết nối đến **endpoint cụ thể**.
- Giao thức Redis đang trả lời lệnh PING.
- Trên đường kết nối đó, những bước xác thực cần thiết để chạy PING đã được đáp ứng.
- Redis server có thể xử lý **một lệnh nhẹ tại thời điểm ấy**.

Nó **không** chứng minh:

- User có quyền `GET`/`SET`/`XACK`/`EVAL` trên key namespace nghiệp vụ.
- Redis còn đủ bộ nhớ để ghi thêm.
- Tất cả primary/slot của Redis Cluster đều truy cập được.
- Replica vừa nhận đủ dữ liệu để đọc đúng kết quả mới nhất.
- Lần ghi trước timeout có hay chưa được thực thi.
- Một Redis Stream consumer group có tồn tại và có thể ACK.
- Ứng dụng đạt 10.000 requests/giây với p99 dưới 50 ms.
- Redis không bị hot key/gián đoạn failover trong vài giây tiếp theo.

**PING là một probe connectivity rất nhỏ, không phải load test hay kiểm chứng end-to-end nghiệp vụ.**

## 4. Một health check nên có phạm vi rõ ràng

Thay vì một nhãn chung “Redis healthy”, hãy mô tả probe:

```text
Tên: redis-connectivity
Mục tiêu: Redis endpoint có phản hồi lệnh nhẹ?
Đường gọi: RedisConnectionFactory -> Redis PING
Giới hạn thời gian: ví dụ 500 ms hoặc theo hạ tầng
Đơn vị kết quả: UP / DOWN / UNKNOWN
Không kiểm tra: write permissions, maxmemory, multi-key, capacity
```

Một probe khác có thể có hợp đồng khác:

```text
Tên: redis-critical-write-path
Mục tiêu: User của service có thực hiện SET với TTL vào namespace lab được phép?
Đường gọi: StringRedisTemplate -> SET key value EX
Giới hạn: thời gian nhỏ, key riêng, TTL nhỏ
Không kiểm tra: throughput tối đa hoặc tính nhất quán SQL/Redis
```

Những phép kiểm tra **ghi dữ liệu** đắt và có side effect hơn PING. Không nên chạy chúng với tần suất quá cao hoặc nhúng vào liveness chỉ để “chắc ăn”.

## 5. Health check của Spring Boot Actuator với Redis

Trong ứng dụng Spring Boot có `spring-boot-starter-actuator` và Spring Data Redis, Actuator có thể cung cấp Redis health contributor/indicator khi các điều kiện auto-configuration phù hợp.

Dependency Gradle minh họa:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Nếu ứng dụng dùng WebFlux, thay `spring-boot-starter-web` bằng `spring-boot-starter-webflux` theo kiến trúc đã lựa chọn. Redis driver phổ biến trong starter là Lettuce.

Một cấu hình Redis local:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: never
```

Phần `prometheus` chỉ hoạt động khi ứng dụng có registry/auto-configuration phù hợp (ví dụ Micrometer Prometheus registry); không nên coi khai báo expose endpoint là đã có dữ liệu Prometheus.

Khi Actuator health endpoint được bật, đường cơ bản thường là:

```text
GET /actuator/health
```

Một response có thể giống:

```json
{
  "status": "UP"
}
```

Nếu được cấu hình để hiển thị components/details cho caller có quyền, có thể thấy contributor Redis. Đừng đưa thông tin endpoint, lỗi xác thực hoặc topology nhạy cảm ra Internet công khai chỉ để debug.

### 5.1. RedisHealthIndicator có nghĩa gì?

Redis health contributor được thiết kế để kiểm tra khả năng Redis connection trả lời theo hợp đồng indicator của phiên bản Spring Boot/Spring Data Redis. Với một số cấu hình, nó có thể lấy thông tin Redis hoặc thực hiện command nhẹ thay vì tự thực hiện cả chuỗi workflow nghiệp vụ.

Vì vậy không nên tuyên bố rằng nó kiểm tra được mọi key, mọi Redis Cluster node hay mọi loại operation. Hãy xác định behavior chính xác theo dependency/version ứng dụng và **gắn tên metric/health indicator với phạm vi thật**.

### 5.2. Reactive health indicator

Khi ứng dụng dùng `ReactiveRedisConnectionFactory`/WebFlux, Spring Boot có thể cấu hình reactive Redis health indicator phù hợp. Dù là imperative hay reactive, ý nghĩa health check vẫn hẹp hơn readiness/capacity.

Không tự gọi `block()` trong Netty event-loop của ứng dụng để xây health check reactive; nếu cần custom probe, dùng API và scheduler phù hợp với runtime. Nếu health check cần I/O nhiều bước, nên tách khỏi request user-facing và hạn chế tần suất.

## 6. Liveness không nên phụ thuộc Redis từ xa

Liveness thường dùng để quyết định **restart instance**. Nếu Redis đang lỗi nhưng tiến trình Java vẫn chạy được, restart ứng dụng thường **không sửa được Redis server**, chỉ tạo thêm tác động:

- Kết nối Redis mới đồng loạt tăng.
- Cache nội bộ/memory của ứng dụng bị mất.
- Các request đang xử lý có thể bị ngắt.
- Startup phải tải lại class/JVM/connection pool.
- Nhiều pod đồng loạt restart trong cùng một outage, gây thêm tải.
- Redis phục hồi có thể phải đối mặt “thundering herd” kết nối/retry.

Ví dụ nguy hiểm:

```text
Redis outage
    |
    +--> 40 application pods: liveness gọi Redis PING
    |
    +--> PING fail
    |
    +--> Kubernetes restart 40 pods
    |
    +--> pods reconnect/retry cùng lúc
    |
    +--> Redis outage kéo dài và application unavailable hơn
```

Một **liveness probe tốt** thường phản ánh tình trạng mà restart tiến trình có thể khắc phục, ví dụ application runtime mắc kẹt nghiêm trọng hoặc bộ phận nội bộ không thể tiếp tục hoạt động.

Nếu một service bắt buộc phụ thuộc Redis, Redis outage có thể làm service **not ready**, nhưng vẫn không phải lý do mặc định làm nó **not live**.

## 7. Readiness trả lời câu hỏi về traffic mới

Kubernetes readiness có thể được dùng để loại một pod khỏi các endpoint được dùng phục vụ traffic khi nó không sẵn sàng. Điều này khác liveness.

Một readiness probe có thể xét:

- Application đã khởi động và hoàn tất phần khởi tạo tối thiểu.
- Các thành phần nội bộ phục vụ request đã sẵn sàng.
- Một dependency **bắt buộc** đối với hầu hết workload không thể dùng.
- Instance đang graceful shutdown và không nên nhận request mới.
- App tạm thời không nhận thêm traffic do state riêng của instance.

Nhưng readiness **không nên** phụ thuộc máy móc vào **mọi dịch vụ bên ngoài**. Nếu Redis mất trên toàn hệ thống, tất cả pods bị đánh dấu not ready có thể khiến load balancer không còn endpoint nào, kể cả khi ứng dụng vẫn có thể chạy ở chế độ degraded hợp lệ.

**Quy tắc thiết kế:** readiness là một **quyết định định tuyến traffic**, không phải một dashboard tổng hợp tất cả lỗi Redis/DB/queue.

## 8. Spring Boot Actuator liveness và readiness probes

Spring Boot Actuator hỗ trợ health groups phục vụ Kubernetes probes khi được bật.

Cấu hình minh họa:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
```

Các đường health group thường là:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Trong những phiên bản Spring Boot hỗ trợ cấu hình `add-additional-paths`, ứng dụng có thể expose các đường bổ sung như:

```text
GET /livez
GET /readyz
```

trên **cổng HTTP chính của ứng dụng**, giúp tránh một số “false healthy” khi management server vẫn phục vụ nhưng cổng traffic chính không hoạt động. Cần xác nhận đường thực tế và cấu hình theo version Spring Boot.

Thông thường, hai groups dựa trên:

- `livenessState`: ApplicationAvailability/liveness state.
- `readinessState`: ApplicationAvailability/readiness state.

Các indicator bên ngoài như Redis **không nhất thiết được đưa vào readiness group mặc định**. Đây là một chủ ý hợp lý để tránh khi dependency từ xa gặp lỗi khiến mọi pod cùng bị loại.

### Các status và HTTP code

Actuator có các trạng thái như `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN`, cùng HTTP mapping tùy cấu hình. Các status `DOWN`/`OUT_OF_SERVICE` thường được ánh xạ sang HTTP 503 theo mặc định.

Kubernetes probe thường đánh giá HTTP code trong phạm vi thành công, không “hiểu” toàn bộ JSON status. Vì vậy cần đảm bảo **health HTTP mapping** phù hợp với probe và không tùy tiện cấu hình mọi trạng thái trả 200.

## 9. Kubernetes probes có mục đích khác nhau

Một deployment minh họa:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: api
          image: orders-api:example
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
```

Các thông số chỉ để minh họa; cần phù hợp thời gian startup, networking, HTTP stack và SLO thực tế. Không dùng image tag `example` như image production.

Ý nghĩa:

- **startupProbe:** cho phép ứng dụng có đủ thời gian khởi động trước khi liveness/readiness chịu logic kiểm tra thường xuyên. Nếu startup probe liên tục thất bại vượt ngưỡng, container có thể bị restart.
- **livenessProbe:** thất bại đủ lần có thể khiến kubelet restart container.
- **readinessProbe:** thất bại khiến pod không được dùng làm endpoint sẵn sàng; bản thân readiness failure không mặc định restart container.
- **failureThreshold/periodSeconds:** giúp tránh phản ứng quá nhạy với một lần trễ nhẹ.
- **timeoutSeconds:** cần tính cả chi phí network/runtime của probe.

**Không đặt readiness và liveness cùng gọi một custom Redis PING endpoint** trừ khi đã cân nhắc rõ lý do và hậu quả khác nhau của hai hành động.

## 10. Khi Redis chỉ là cache tùy chọn

Ví dụ service đọc sản phẩm từ PostgreSQL, cache trong Redis theo cache-aside:

```text
GET /products/42
      |
      v
Redis GET product:42
      |
      +--> HIT: trả cache
      |
      +--> MISS: PostgreSQL SELECT -> Redis SET -> trả
      |
      +--> Redis error: PostgreSQL SELECT -> trả (degraded mode)
```

Trong trường hợp này, Redis outage không nhất thiết làm endpoint không thể phục vụ. Readiness có thể vẫn `UP` nếu database còn đáp ứng SLO và policy cho phép fallback.

Tuy nhiên:

- Cache miss rate tăng có thể làm PostgreSQL quá tải.
- Latency có thể tăng mạnh.
- Redis write/eviction lỗi cần được ghi nhận.
- Không phải tất cả endpoints đều có thể fallback an toàn.
- Số lượng concurrent DB queries cần được giới hạn.

Vì vậy Redis **component health = DOWN** nhưng **application readiness có thể vẫn UP**; đồng thời **capacity phải được giảm ước lượng** hoặc áp dụng load shedding.

Không nên coi fallback là không tốn chi phí. Một ứng dụng chỉ chịu 500 RPS khi không có cache nhưng bình thường chịu 5.000 RPS có thể vẫn ready ở tải thấp, song không còn khả năng chịu tải như trước.

## 11. Khi Redis là dependency bắt buộc

Redis có thể giữ dữ liệu hoặc khả năng thiết yếu cho request:

- Session state không có nguồn dự phòng.
- Rate limiter mà thiếu nó phải fail-closed.
- Hàng đợi chính để ghi nhận commands/events khi không có durable fallback.
- Distributed coordination/lock cần thiết trước khi xử lý.
- Trạng thái nghiệp vụ mà Redis là nguồn dữ liệu có thẩm quyền.
- Một endpoint phụ thuộc Redis Streams để nhận và xử lý công việc.

Nếu không thể thực hiện hoạt động quan trọng nhất khi Redis không dùng được, ứng dụng có thể cần báo **not ready** hoặc chủ động từ chối những request tương ứng.

Ví dụ:

```text
Checkout API
   |
   +--> Redis required for session validation
   |
   +--> Redis unavailable
           |
           +--> trả lỗi có kiểm soát / fail-closed
           |
           +--> readiness decision theo policy
```

Dù vậy cần phân biệt **global dependency outage** với **local instance outage**. Nếu Redis mất trên toàn vùng, đánh dấu tất cả pods not ready không tự khôi phục Redis. Trong một số thiết kế, readiness vẫn có thể giữ app ở trạng thái ready để trả lỗi có kiểm soát thay vì không còn endpoint nào. Quyết định phụ thuộc routing, fallback, error budget và đặc điểm của các endpoints.

## 12. Không nên nhét mọi dependency vào readiness group

Một ứng dụng có:

```text
GET /catalog            -> Redis cache optional
POST /orders            -> SQL required
GET /sessions/me        -> Redis session critical
POST /email/notifications -> Kafka/Stream async
```

Nếu một readiness group thêm tất cả dependencies (Redis, SQL, Kafka, search), chỉ cần một thành phần hỏng là **toàn pod bị loại** dù một số chức năng vẫn phục vụ được.

Cần cân nhắc:

1. Một ứng dụng có thể chia thành các deployment/service theo dependency profile không?
2. Có thể graceful degrade từng endpoint thay vì loại toàn pod không?
3. Có endpoint thực sự không thể phục vụ nếu dependency hỏng?
4. Load balancer có khả năng route theo chức năng hay chỉ theo pod?
5. Khi một dependency toàn vùng hỏng, việc loại mọi pod có làm downtime tệ hơn?
6. Có cần một **operational health dashboard** tách rời traffic readiness không?

Actuator health contributors giúp quan sát dependency; **không bắt buộc** tất cả contributor đều phải quyết định Kubernetes readiness.

## 13. Thêm Redis vào readiness có chủ đích

Nếu Redis là dependency bắt buộc và readiness thực sự nên phụ thuộc nó, có thể chỉ định health group.

Ví dụ Spring Boot YAML:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,redis
```

Cấu hình trên là minh họa cho một ứng dụng có contributor tên `redis`. Cần xác nhận **ID thực tế** của health contributor qua Actuator/auto-configuration, nhất là khi nhiều Redis factories hoặc custom indicators.

Phần `readinessState` giữ trạng thái application availability, còn `redis` đưa Redis health contributor vào quyết định group. Nếu Redis indicator `DOWN`, readiness group có thể trả HTTP 503 theo aggregation.

**Không áp dụng cấu hình này một cách mặc định cho mọi service dùng Redis.** Với Redis cache optional, cách làm này có thể làm traffic ngừng hoàn toàn ngay lúc Redis lỗi, dù service có thể dùng database để phục vụ.

### Thay đổi health group không đồng nghĩa thay đổi code nghiệp vụ

Ngay cả khi readiness `UP`, một lệnh `XADD` có thể bị `NOPERM` hoặc `SET` bị `OOM`. Health group không thay cho xử lý lỗi trong service, retry, idempotency và nghiệp vụ degraded mode.

## 14. Tách dashboard dependency health khỏi traffic readiness

Một thiết kế dễ quan sát:

```text
/actuator/health/liveness
    -> livenessState, kiểm tra nội bộ tối thiểu

/actuator/health/readiness
    -> readinessState và dependency thực sự quyết định traffic

/actuator/health
    -> trạng thái tổng hợp, dành cho vận hành theo quyền truy cập

Metrics + traces + logs
    -> Redis latency, errors, memory, saturation, cache efficiency
```

Đừng cho external load balancer tự lấy endpoint `/actuator/health` tổng hợp rồi suy luận rằng bất kỳ contributor nào `DOWN` đều phải restart ứng dụng.

Nếu cần các health groups riêng như `redisDependency` hoặc `criticalWritePath`, có thể cấu hình trong Actuator để theo dõi độc lập với readiness. Dù thiết kế nhóm nào, cần giới hạn quyền truy cập và không lộ Redis server/ACL details công khai.

## 15. Health check dạng read-only và write synthetic khác nhau

Một Redis `PING` kiểm tra rất ít. Một phép thử nghiệp vụ có thể kiểm tra thêm quyền ghi hoặc trạng thái keyspace bằng cách ghi một key synthetic.

### Read-only probe

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Component;

@Component("redisConnectivityProbe")
public class RedisConnectivityProbe implements HealthIndicator {

    private final RedisConnectionFactory factory;

    public RedisConnectivityProbe(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    @Override
    public Health health() {
        try (var connection = factory.getConnection()) {
            String reply = connection.ping();
            return "PONG".equalsIgnoreCase(reply)
                    ? Health.up().build()
                    : Health.down().withDetail("reason", "Unexpected PING").build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("type", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
```

Ví dụ này chỉ kiểm tra connectivity của một connection theo API Spring Data Redis tương ứng. Không đặt tên “capacity healthy” cho nó.

Tùy cấu hình/driver, factory có thể cung cấp connection wrapper với cơ chế lifecycle riêng; khi áp dụng vào production cần tuân theo contract của version Spring Data Redis đang dùng. Nên tái sử dụng contributor có sẵn khi nó đáp ứng yêu cầu, tránh nhân đôi PING.

### Write synthetic probe

Một custom probe có thể dùng một Redis key riêng:

```java
import java.time.Duration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component("redisWriteProbe")
public class RedisWriteProbe implements HealthIndicator {

    private static final String KEY = "health:app:write-probe";

    private final StringRedisTemplate redis;

    public RedisWriteProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public Health health() {
        try {
            Boolean result = redis.opsForValue().set(
                    KEY, "ok", Duration.ofSeconds(15));

            return Boolean.TRUE.equals(result)
                    ? Health.up().build()
                    : Health.down()
                        .withDetail("reason", "Write not acknowledged")
                        .build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("type", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
```

Đây là **một probe có side effect**. Nếu đưa vào health group và Kubernetes gọi rất thường xuyên, nó sẽ phát sinh Redis writes liên tục từ mọi pod. Hãy cân nhắc:

- Dùng key namespace riêng và ACL theo least privilege.
- Đặt TTL để không tạo key sống mãi.
- Đặt tần suất/thời hạn nhỏ và giới hạn tài nguyên.
- Không đặt key chứa thông tin nhạy cảm.
- Nếu nhiều pods dùng chung key, chúng có thể cùng ghi một value; điều này không chứng minh độc lập tính đúng của mỗi business key.
- Một `SET` thành công không chứng minh mọi script, stream group, slot hay command khác có quyền.
- Redis Cluster: một probe key chỉ nằm trên **một slot**, không kiểm tra mọi primary.
- Không đặt probe ghi dữ liệu vào liveness.
- Thường nên gọi write synthetic **thưa hơn** readiness probe, chẳng hạn qua một scheduled diagnostics task có cache kết quả, nếu kiến trúc thực sự cần.

## 16. Chọn phép thử theo workflow, không theo tên công nghệ

Nếu một service chỉ gọi `GET`, `PING` có thể hữu ích nhưng không xác nhận key serializer, prefix hay quyền `GET`. Nếu service tạo Redis Stream events, `PING` càng không chứng minh `XADD` được phép.

Một ma trận probe:

| Workload | Phép kiểm tra hẹp | Phép kiểm tra sâu hơn | Rủi ro cần lưu ý |
|---|---|---|---|
| Cache đọc | PING/connectivity | GET key synthetic đã tạo sẵn | Cache miss không phải lỗi hạ tầng |
| Cache ghi | PING | SET TTL key riêng | OOM/ACL có thể chặn write |
| Session Redis | Connectivity | Đọc/ghi session synthetic theo schema | Không ghi đè session thật |
| Counter/rate limiter | Connectivity | INCR synthetic có TTL/giới hạn | Side effect, TTL và retry |
| Redis Streams producer | Connectivity | XADD vào stream lab riêng | Tăng stream length, retention |
| Stream consumer | Connectivity | Kiểm tra group/ACK path ở môi trường kiểm soát | Không ACK message thật của người dùng |
| Redis Cluster | Seed reachable | Thử các slots/node endpoints theo scope | Probe một key không bao phủ cluster |
| Lua logic | Connectivity | Script synthetic trên key riêng | ACL EVAL và side effect |

Probe sâu nên phục vụ **chẩn đoán hoặc kiểm tra định kỳ có kiểm soát**, không mặc nhiên chèn toàn bộ vào endpoint bị Kubernetes gọi mỗi vài giây.

## 17. Redis trả PING nhưng thao tác ghi có thể lỗi OOM

Redis có thể trả:

```text
PONG
```

nhưng khi ứng dụng gọi:

```bash
redis-cli SET cache:product:42 some-value
```

server lại trả:

```text
OOM command not allowed when used memory > 'maxmemory'.
```

Nguyên nhân thường liên quan `maxmemory`, `maxmemory-policy`, key expiration/eviction hoặc phần dữ liệu không thể giải phóng.

Hệ quả:

- Health connectivity vẫn `UP`.
- Readiness có thể không đổi nếu Redis chỉ là cache optional.
- Một service bắt buộc ghi Redis có thể không còn đáp ứng workflow.
- Write capacity có thể giảm về gần 0 cho những command cần thêm memory.
- `GET` có thể vẫn hoạt động, khiến kết quả đọc và ghi khác nhau.
- Redis Streams `XADD` có thể thất bại trong khi consumer vẫn đọc được message đã tồn tại.

**Một health check chỉ gọi `PING` không thể thay thế metrics về memory và kiểm tra success/error của lệnh thực tế.**

## 18. Dữ liệu Redis server cần quan sát

Một Redis admin/operator có thể dùng:

```bash
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO memory
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO stats
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO clients
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO commandstats
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO replication
```

Các command có thể bị giới hạn bởi Redis ACL hoặc managed service. Không cấp quyền admin cho application chỉ để health check đọc thêm thông tin.

Các chỉ số điển hình:

| Chỉ số/nhóm chỉ số | Điều cần hiểu |
|---|---|
| `used_memory` / `maxmemory` | Redis còn headroom bộ nhớ theo policy không? |
| `used_memory_rss` | Resident memory có vượt ngân sách container/host không? |
| `mem_fragmentation_ratio` | Có overhead/fragmentation đáng kể không? |
| `evicted_keys` | Redis đang loại key vì áp lực memory hay không? |
| `expired_keys` | Key TTL được hết hạn theo thời gian |
| `rejected_connections` | Client mới bị từ chối do giới hạn hay lỗi liên quan |
| `connected_clients` | Số kết nối hiện tại, so với giới hạn vận hành |
| `blocked_clients` | Clients đang chờ các blocking operations |
| `instantaneous_ops_per_sec` | Tốc độ command gần đây, không phải throughput nghiệp vụ |
| `commandstats` | Chi phí và tần suất theo Redis command |
| `total_error_replies` | Số phản hồi lỗi tích lũy, cần xem rate và phân loại |
| `role` và replication offset/lag | Primary/replica state và rủi ro đọc dữ liệu stale |
| CPU / network / disk | Redis process và hạ tầng đang nghẽn ở đâu |
| Latency diagnostics | Dấu hiệu các command hoặc server event có độ trễ cao |

Tên chỉ số/exporter và sự sẵn có khác nhau giữa Redis versions/managed service. Các counters tích lũy nên được theo dõi **tốc độ thay đổi**, không chỉ giá trị tổng từ lúc server khởi động.

## 19. Khả năng chịu tải không có một ngưỡng PING

Capacity nên được đánh giá theo khả năng giữ **SLO** ở workload mong đợi.

Ví dụ service đặt:

```text
Mục tiêu:
  2.000 HTTP requests/giây

Bất biến:
  p99 end-to-end latency <= 150 ms
  error rate <= 0,5%
  không bỏ sót nghiệp vụ quan trọng
  JVM heap / Redis memory không tăng không giới hạn
  backlog có thể phục hồi sau đợt tải cao
```

Khi thử tải:

- 500 RPS: p99 40 ms, lỗi 0%.
- 1.500 RPS: p99 95 ms, lỗi 0,1%.
- 2.000 RPS: p99 230 ms, lỗi 1,2%.
- 2.500 RPS: Redis command timeout và hàng đợi tăng.

Trong ví dụ này, Redis `PING` có thể vẫn ổn ở 2.500 RPS, nhưng **ứng dụng đã không đạt SLO ở 2.000 RPS**. “Redis healthy” theo PING không thể phủ nhận điều đó.

**Capacity phải gắn với workload và SLO cụ thể**, không phải một số “Redis có thể xử lý N operations/s” lấy từ môi trường khác.

## 20. Throughput và tail latency cần được đo cùng nhau

Một tối ưu như tăng pipelining hoặc batch size có thể cải thiện throughput nhưng làm p99 tăng do:

1. Batch formation wait.
2. Connection queueing.
3. Reply buffer/serialization.
4. Head-of-line blocking.
5. Redis CPU-bound commands hoặc Lua script dài.
6. Client event-loop saturation.
7. Garbage collection của JVM.
8. Retry bùng phát khi Redis timeout.

Nếu chỉ đo số Redis commands/giây, ta có thể bỏ qua trải nghiệm người dùng.

Một mô hình đơn giản:

```text
HTTP request latency
    =
    App queue wait
    + Business processing
    + Redis command wait/network/server
    + Deserialize
    + Fallback or retry
    + Response serialization
```

Cần đo **end-to-end p50/p95/p99** và tách từng bước để tìm bottleneck. Một Redis `GET` p99 = 20 ms không giải thích được HTTP request p99 = 500 ms nếu đang có lock contention, DB fallback hoặc downstream queue.

## 21. Little's Law: tải tăng có thể làm hàng chờ tăng

Trong trạng thái tương đối ổn định, Little's Law:

\[
L = \lambda W
\]

Trong đó:

- `L`: số công việc trung bình đang ở trong hệ thống.
- `λ`: tốc độ công việc đến/hoàn thành trung bình.
- `W`: thời gian trung bình một công việc ở trong hệ thống.

Ví dụ 5.000 ops/giây và mỗi operation ở trong hệ thống 40 ms:

\[
L = 5\,000 \times 0.04 = 200
\]

Nếu Redis chậm khiến thời gian tăng từ 40 ms lên 200 ms mà tốc độ đến chưa giảm, lượng công việc in-flight có thể lên gần 1.000 operations. Khi ấy:

- Futures/replies/buffers tăng.
- Thread pool/connection pool có thể bão hòa.
- Timeouts tăng và client retry thêm.
- Memory có thể tăng dù Redis `PING` vẫn trả lời.

Little's Law giúp giải thích nhu cầu buffer và saturation, **không phải phép dự đoán chính xác khi traffic burst hoặc hệ thống chưa ổn định**.

## 22. Những nguồn nghẽn cần phân biệt

| Nguồn nghẽn | Triệu chứng | Hướng đo |
|---|---|---|
| Redis CPU | Command latency tăng, throughput plateau | Redis CPU, commandstats, slowlog/latency |
| Redis memory | Eviction/OOM, RSS tăng | INFO memory, maxmemory, memory pressure |
| Network | RTT tăng, timeout, retransmission | Network latency, bandwidth, connection errors |
| Connection limits | Connection refused/rejected | Connected/rejected clients, pool |
| Lettuce client | Event-loop chậm, pending commands | Client metrics/traces, command latency |
| JVM heap/GC | p99 spikes, OOM Java | Heap usage, GC pauses |
| Thread pool | Queue sâu, active threads tối đa | Executor gauges |
| Redis Cluster hot slot | Một primary bận, node khác rảnh | Slot/key distribution, per-node metrics |
| Read replica lag | Read không thấy write vừa commit | Replication lag, source version |
| Cache miss storm | Database tăng QPS sau Redis failure | Cache hit/miss, DB pool, fallback rate |
| Stream consumer lag | Pending tăng, ACK throughput giảm | XINFO GROUPS, XPENDING, consumer processing |
| Long Lua/MULTI | Các command khác bị chậm | Command latency, slowlog, tracing |

Đôi khi một Redis dependency health indicator `UP` trong khi **kết nối của một application pod khác** bị lỗi DNS/TLS. Cần quan sát theo application instance và theo Redis node, không lấy một phép kiểm tra từ laptop vận hành làm đại diện cho mọi pod.

## 23. Redis Cluster cần health theo node và slot

Redis Cluster có nhiều primary và replica. Một `PING` tới seed node không chứng minh **mọi hash slot** đều có đường truy cập hợp lệ.

```text
Cluster:
  Primary A -> slots 0..5000        UP
  Primary B -> slots 5001..10000    node/endpoint unreachable
  Primary C -> slots 10001..16383   UP

App PING Primary A -> PONG
App GET key thuộc B -> timeout / redirection failure
```

Khi chẩn đoán, dùng các lệnh quản trị có quyền:

```bash
redis-cli -c -h redis-a -p 7000 CLUSTER INFO
redis-cli -c -h redis-a -p 7000 CLUSTER SHARDS
redis-cli -c -h redis-a -p 7000 CLUSTER NODES
```

Những lệnh này giúp quan sát topology/slot coverage nhưng cũng không phải load test.

Một hệ thống giám sát Cluster nên xem:

- `cluster_state` và slot coverage.
- Primary/replica roles, failover events.
- Endpoint quảng bá có truy cập được từ network ứng dụng không.
- Redis memory/CPU/latency **theo từng primary**.
- Hot keys/hot slots, key distribution.
- Số lần Lettuce gặp MOVED/ASK hoặc topology refresh failures.
- Tỷ lệ lỗi theo hash-slot range hoặc logical key namespace khi có thể.
- Replication lag nếu có đọc replica.

Một service có thể có latency xấu chỉ với một nhóm users vì key của họ thuộc slot ở node bận. Một dashboard Redis aggregate có thể che giấu điều này.

## 24. Redis Sentinel và health trong thời gian failover

Với Redis Sentinel, một primary có thể được thay bằng replica được promote. Trong thời gian failover:

- Endpoint primary cũ có thể offline hoặc trở thành replica.
- Một số commands ghi có thể timeout hoặc trả `READONLY`.
- Lettuce/Sentinel-aware connection cần tìm primary mới.
- Redis có thể phục hồi nhanh nhưng application connection pool chưa ổn định ngay.
- Một số writes gần thời điểm failover có thể chịu rủi ro theo replication/durability semantics.

Liveness của application **thường không nên chuyển DOWN chỉ vì một Redis failover ngắn**. Readiness phụ thuộc mức độ thiết yếu của Redis và khả năng degrade; metric/alert phải theo dõi thời gian phục hồi và các writes không rõ kết quả.

Một health probe quá nhạy (timeout 200 ms, failureThreshold 1) có thể đánh dấu pod not ready trong những nhiễu mạng ngắn, gây traffic shifting liên tục. Ngược lại, timeout quá dài làm phát hiện sự cố chậm. Cần cân bằng theo SLO và độ biến động môi trường.

## 25. Replica read có thể khỏe nhưng dữ liệu không đủ mới

Một replica có thể trả `PING` và `GET` bình thường, nhưng vẫn chậm sao chép dữ liệu từ primary.

Ví dụ:

```text
T1: app SET token:revoked:42 = true trên primary
T2: app đọc từ replica chưa nhận update
T3: replica GET token:revoked:42 -> nil
```

Ở đây:

- Node **healthy** về kết nối.
- Có thể vẫn **ready** cho các truy vấn chấp nhận eventual consistency.
- Nhưng kết quả không phù hợp cho nghiệp vụ kiểm tra quyền đã thu hồi cần trạng thái mới nhất.

Vì vậy cần tách **health** khỏi **freshness/consistency SLO**. Nếu độ mới có yêu cầu rõ ràng, hãy theo dõi replication lag và/hoặc version so với nguồn, thay vì coi `GET` thành công là bằng chứng dữ liệu đúng.

## 26. Đọc/ghi khác nhau dù cùng Redis instance

Một Redis server có thể:

- Cho phép `GET` nhưng `SET` lỗi `NOPERM` do ACL.
- Trả `PING` nhưng `SET` lỗi `OOM` do maxmemory.
- Cho phép đọc từ replica nhưng ghi bị `READONLY`.
- Có Stream entry nhưng `XREADGROUP` lỗi `NOGROUP`.
- Cho phép `XREADGROUP` nhưng `XACK` lỗi quyền.
- Cho phép lệnh đơn key nhưng `MGET` nhiều slot lỗi `CROSSSLOT`.

Do đó health check cần phân biệt **capability theo lệnh**.

Ví dụ một luồng đăng ký đơn hàng dùng Redis Streams:

```text
POST /orders
    -> SQL COMMIT
    -> XADD orders:events
```

Nếu `PING` thành công nhưng `XADD` bị `NOPERM` hoặc `OOM`, sự kiện có thể không được ghi. Nếu SQL đã commit, cần outbox/retry đáng tin cậy; health indicator không tự khôi phục một sự kiện bị thiếu.

## 27. Đừng dùng PING làm performance benchmark

Một lệnh `PING` có payload nhỏ, không đo được:

- Kích thước value lớn của `MGET`.
- CPU của `ZREVRANGE` trên ZSet lớn.
- Độ trễ của Lua script chạy nhiều thao tác.
- Serialization JSON/JDK của Spring Data Redis.
- Redis transaction `MULTI/EXEC` gồm hàng trăm commands.
- Redis Streams consumer ACK/recovery throughput.
- Hot key được gọi hàng nghìn lần/giây.
- Lượng pending command trong Lettuce.
- Thời gian chờ của downstream database khi cache miss.

Một performance test có ý nghĩa phải dùng **command mix và distribution giống workload**, không chỉ một vòng lặp PING.

### Redis benchmark vs application benchmark

Các công cụ benchmark Redis có thể đo khả năng xử lý raw commands, nhưng ứng dụng Spring còn có HTTP, security, serialization, Reactor/thread pool, cache miss/fallback và SQL. Nên đo cả:

1. Redis server command capacity trong môi trường lab.
2. Spring Data Redis operations latency.
3. HTTP end-to-end throughput và SLO.
4. Workload degraded khi Redis lỗi.
5. Recovery time sau failover/restart.

## 28. SLI và SLO nên gắn với chức năng cụ thể

Một số Service Level Indicators:

| SLI | Định nghĩa có ý nghĩa |
|---|---|
| HTTP success rate | Tỷ lệ request thực sự hoàn thành đúng hợp đồng |
| HTTP p95/p99 latency | Thời gian end-to-end theo loại endpoint |
| Redis command success rate | Thành công theo GET, SET, XADD, XACK, Lua... |
| Redis command latency | p50/p95/p99 theo command và topology |
| Cache hit ratio | Hit/(hit+miss) cho use case cache |
| Redis fallback rate | Tỷ lệ request phải bỏ cache và đọc DB |
| DB pressure after fallback | DB QPS/pool wait khi Redis không khả dụng |
| Memory headroom | Khoảng cách tới maxmemory/container limits |
| Error rate by type | Timeout, NOPERM, OOM, READONLY, MOVED/CROSSSLOT... |
| Stream pending age | Tuổi lớn nhất của message pending |
| Event processing lag | Từ XADD tới nghiệp vụ hoàn tất/ACK |
| Replica freshness | Độ trễ hoặc version lag so với primary/source |

Ví dụ mục tiêu SLO phải có điều kiện:

```text
Catalog API, khi cache healthy:
  p99 <= 150 ms
  99,9% successful requests trong 30 ngày

Catalog API, khi Redis unavailable:
  vẫn trả dữ liệu nguồn với error rate <= 1%
  và throughput tối thiểu phù hợp với fallback capacity

Order event consumer:
  99,9% events được xử lý trong <= 60 giây
  pending age không vượt 5 phút trong điều kiện bình thường
```

Mục tiêu chỉ là ví dụ; cần dựa trên yêu cầu sản phẩm/khả năng hạ tầng thực tế. Đừng dùng một SLO Redis chung rồi coi mọi endpoint đều có cùng mức độ phụ thuộc.

## 29. Các metric phía Spring và Lettuce

Trong ứng dụng Spring Boot/Micrometer, có thể thu thập:

- HTTP server request duration, status codes.
- JVM memory, garbage collection pauses.
- Executor active threads/queue depth.
- Connection pool gauges nếu dùng.
- Lettuce Redis command latency/metrics nếu instrumentation được bật.
- Cache hit/miss, cache operations, fallback counts.
- Circuit breaker state/rejections.
- Retry attempts theo loại exception.
- Application-specific event processing rate/lag.
- Redis dependency state qua health indicator.

Tên metric phụ thuộc phiên bản Spring Boot, Micrometer, Redis client và registry. Ví dụ không nên hard-code một chuỗi tên metric rồi khẳng định sẽ có trong mọi ứng dụng.

### Metric cardinality

Không gắn Redis key chứa user ID vào metric label:

```text
Không nên:
  redis_operation_latency{key="user:42:session"}
  redis_operation_latency{key="user:43:session"}
  ... hàng triệu series

Nên:
  redis_operation_latency{operation="GET",namespace="session"}
```

Cardinality cao có thể làm Prometheus/metrics backend quá tải. Key nhạy cảm còn có nguy cơ lộ thông tin qua telemetry.

## 30. Dashboard quan sát theo nhiều lớp

Một dashboard hữu ích có thể chia thành các vùng:

```text
[APPLICATION]
  HTTP throughput, p95/p99 latency, error %
  readiness/liveness trends, active instances
  JVM heap, GC, thread pools

[REDIS CLIENT / LETTUCE]
  GET/SET/XADD/XACK latency
  timeout/error rate, reconnects, pending commands
  retry and fallback counts

[REDIS SERVER / CLUSTER]
  per-primary CPU/memory, maxmemory headroom
  evictions/OOM, connected/rejected clients
  replication lag, Cluster slots/topology

[BUSINESS]
  cache hit/miss, DB fallback saturation
  Stream lag / pending age / ACK throughput
  missed events, duplicate suppression
```

**Cảnh báo quan trọng:** một readiness endpoint `UP` không làm các biểu đồ capacity trở nên không cần thiết. Ngược lại, một lệnh Redis PING fail trong vài giây không nhất thiết yêu cầu restart application.

## 31. Cảnh báo health và capacity nên khác nhau

Ví dụ nguyên tắc alert:

| Mức | Tín hiệu | Phản ứng |
|---|---|---|
| Sự cố kết nối Redis | Redis command errors tăng liên tục | Điều tra Redis/network/ACL |
| Readiness nhiều pods chuyển DOWN | Service mất traffic capacity | Xem policy readiness và dependency scope |
| Liveness restart tăng | Crash loop, stuck application, cấu hình probes | Điều tra app process, không chỉ Redis |
| Redis memory > ngưỡng cảnh báo | Headroom thấp | Capacity planning, TTL/eviction, cleanup hợp lệ |
| Redis OOM errors > 0 | Write capability bị ảnh hưởng | Ưu tiên bảo vệ dữ liệu/producer |
| Redis command p99 vượt SLO | Latency degradation | Xem CPU, hotkeys, network, client queue |
| Cache hit ratio giảm mạnh | DB có thể bị tăng tải | Bảo vệ DB, kiểm tra invalidation/TTL |
| Stream PEL oldest idle tăng | Recovery/consumer chậm hoặc lỗi | Kiểm tra ACK, reclaim, poison messages |
| Replica lag tăng | Rủi ro stale reads | Điều chỉnh read routing/consistency |
| Redis Cluster primary mất | Slot coverage/failover | Theo dõi failover và reconnect |

Nên tránh alert dựa trên một điểm đo đơn lẻ khi hệ thống có dao động ngắn, nhưng cũng đừng chỉ lấy trung bình 30 phút khiến một outage vài phút bị làm mờ. Dùng ngưỡng thời gian, burn-rate, severity phù hợp với tác động nghiệp vụ.

## 32. Kịch bản lỗi: Redis cache mất trên toàn vùng

Giả sử 20 application pods cùng dùng Redis cache, PostgreSQL là nguồn dữ liệu chuẩn.

```text
T0 Redis unavailable
T1 GET cache errors tăng
T2 Các pods fallback về PostgreSQL
T3 Database CPU/pool wait tăng
T4 p99 HTTP tăng
T5 Database có nguy cơ quá tải
```

Nếu readiness được thiết kế “Redis PING fail = not ready” cho mọi pod, tất cả 20 pods có thể bị loại cùng lúc và users mất toàn bộ khả năng phục vụ.

Một thiết kế resilience có thể gồm:

- Readiness không phụ thuộc Redis khi cache optional.
- Fallback có timeout rõ ràng và tránh retry Redis vô hạn.
- Circuit breaker giảm việc liên tục thử Redis đang lỗi.
- Rate limit/bounded concurrency để bảo vệ PostgreSQL.
- Cache stale tạm thời nếu nghiệp vụ cho phép và có cơ chế kiểm soát độ cũ.
- Alert Redis outage, DB fallback rate, DB pool và HTTP SLO.
- Khi Redis phục hồi, warm-up có giới hạn để tránh stampede.

**Kết luận:** health Redis có thể DOWN, readiness vẫn UP, nhưng capacity giảm mạnh. Nếu không đo capacity, service có thể chuyển từ một outage Redis thành outage database thứ hai.

## 33. Kịch bản lỗi: Redis là session store bắt buộc

Một web application không có cách xác thực session nếu Redis session store mất.

```text
Redis unavailable
    |
    +--> Session GET/SET fails
    |
    +--> Authentication workflow unavailable
    |
    +--> Endpoints requiring session cannot succeed
```

Trong trường hợp này, service phải trả lỗi hợp đồng rõ ràng hoặc chuyển readiness theo policy phù hợp. Nhưng lưu ý:

- Nếu Redis mất toàn vùng, mọi pod cũng có thể đồng thời not ready.
- Việc restart từng pod không khắc phục Redis session store.
- Nếu có một số endpoints public không cần session, có thể cân nhắc tách deployment/routing.
- Phải có bảo vệ khỏi retry storms trong lúc Redis phục hồi.
- Kiểm tra Redis connection `PING` không chứng minh session read/write ACL và serialization vẫn đúng.

Các alert nên theo dõi **session operation failure rate** và HTTP authentication success rate, không chỉ Redis PING.

## 34. Kịch bản lỗi: Redis còn PING nhưng maxmemory hết

Giả sử Redis dùng `maxmemory-policy noeviction` và dữ liệu tiếp tục tăng.

```text
PING -> PONG
GET  -> OK
SET  -> OOM
XADD -> OOM
```

Các lớp quan sát cần phản ứng khác nhau:

- **Connectivity:** UP.
- **Write capability:** FAILED.
- **Readiness:** phụ thuộc vai trò của write với service.
- **Capacity:** không còn headroom cho những write cần thêm memory.
- **Alerting:** memory threshold, OOM reply rate, evictions.
- **Recovery:** điều chỉnh TTL/retention/capacity có kiểm soát, không `FLUSHALL` vội vàng.

Nếu Redis là cache có thể bỏ qua SET lỗi và vẫn trả dữ liệu từ database, read service có thể tiếp tục. Nhưng nếu Redis Streams là nơi duy nhất chứa event phát sinh, `XADD` lỗi là một vấn đề dữ liệu rất nghiêm trọng và cần durable fallback/outbox.

## 35. Kịch bản lỗi: Redis Cluster có một primary chậm

```text
Primary A: p99 GET 3 ms
Primary B: p99 GET 120 ms, CPU gần bão hòa
Primary C: p99 GET 4 ms
```

Health PING của tất cả nodes có thể `UP`. App readiness vẫn `UP`. Tuy nhiên users có key thuộc B có trải nghiệm xấu.

Phải xem:

- Key/slot nào nằm ở B.
- Có hot key/ZSet/stream ở một slot không.
- Có Lua script hoặc multi-key command nặng không.
- Replica routing có làm stale dữ liệu không.
- p99 theo endpoint/user cohort có lệch nhau không.
- Cân bằng slot/reshard có phù hợp và an toàn không.

Không kết luận Redis Cluster đủ capacity chỉ vì trung bình CPU toàn cluster thấp; một hot primary có thể là điểm nghẽn làm SLO thất bại.

## 36. Kịch bản lỗi: Redis Streams PING ổn nhưng backlog tăng

Ví dụ:

```text
Producer XADD: 2.000 events/s
Consumer ACK:   800 events/s
Backlog tăng:  1.200 events/s
```

Redis vẫn trả PING. Application consumer pods vẫn live. Thậm chí readiness có thể UP nếu chúng nhận/ACK được message, nhưng **khả năng xử lý tải đã nhỏ hơn tốc độ đến**.

Cần đo:

- `XINFO GROUPS` lag và các giới hạn của ý nghĩa chỉ số lag.
- `XPENDING` tổng pending và tuổi pending lớn nhất.
- Event age từ XADD đến xử lý xong.
- Consumer success/failure/ACK rate.
- Retry/reclaim count và poison messages.
- Tốc độ producer, áp lực downstream DB/API.
- Stream length và retention; `XACK` không tự xóa entry vật lý.

Việc tăng `batchSize` của listener có thể giúp giảm polling overhead nhưng không giải quyết một business handler xử lý chậm hoặc database bottleneck. Nếu backlog tăng đều, cần capacity planning, scale consumers và/hoặc giảm tải upstream.

## 37. Readiness không phải công cụ auto-scaling tốt nhất

Đánh dấu pod not ready khi CPU tăng nhẹ có thể làm traffic dồn lên các pod còn lại. Nếu tất cả pods đều cao tải, loại bớt endpoints chỉ làm tình hình xấu hơn.

Thông thường:

- **Readiness:** instance có nên nhận traffic không.
- **Horizontal scaling:** tăng số instances theo demand/metrics.
- **Backpressure/load shedding:** giới hạn số công việc mà instance nhận.
- **Circuit breaker:** ngăn phụ thuộc đang lỗi gây cascade.
- **Capacity alerting:** báo trước khi SLO vi phạm.
- **Liveness:** phát hiện tình trạng restart có thể phục hồi.

Redis Cluster cũng không tự tăng capacity chỉ vì tăng số application pods. Nếu một primary Redis là bottleneck, scale ứng dụng có thể làm pressure lên Redis lớn hơn. Phải xác định điểm nghẽn trước khi chọn hướng mở rộng.

## 38. Chọn khoảng thời gian và ngưỡng probe

Một probe có các biến:

| Tham số | Ý nghĩa |
|---|---|
| `periodSeconds` | Khoảng cách các lần kiểm tra của kubelet |
| `timeoutSeconds` | Giới hạn một lần probe |
| `failureThreshold` | Số lần thất bại liên tiếp trước khi coi probe fail |
| `successThreshold` | Số lần thành công để coi là hồi phục, theo ràng buộc từng probe |
| HTTP path/port | Đường traffic hoặc management endpoint được kiểm tra |
| Health group membership | Các thành phần nào ảnh hưởng kết quả |
| Redis/client timeout | Command/probe có thể chờ tối đa bao lâu |
| Startup grace | Startup probe hoặc initial delay phù hợp |

Không được tùy tiện đặt Redis command timeout dài hơn HTTP probe timeout rồi giả định có phản hồi đầy đủ. Khi probe request bị timeout nhưng Redis command còn chạy ở tầng client, hàng chờ có thể tích tụ nếu không quản lý cancel/lifecycle tốt.

Tương tự, liveness probe failure threshold quá nhỏ trong JVM có GC pause tạm thời có thể gây restart không cần thiết. Cần cân bằng độ nhạy và khả năng chống nhiễu ngắn hạn.

## 39. Graceful startup và shutdown

Một service chưa sẵn sàng khi khởi động có thể:

1. Tạo Spring context.
2. Khởi tạo Redis connection factory.
3. Chạy migration/configuration cần thiết.
4. Đăng ký consumer/khởi động listener nếu có.
5. Chuẩn bị state/config nội bộ.
6. Chuyển readiness sang nhận traffic.

Không cần chặn liveness suốt startup nếu có startupProbe hợp lý.

Khi shutdown:

```text
Pod bắt đầu termination
    |
    +--> readiness chuyển trạng thái không nhận traffic mới
    |
    +--> HTTP requests đang xử lý hoàn tất trong grace period
    |
    +--> Redis Stream consumers dừng nhận thêm message
    |
    +--> Tasks đã xử lý thành công ACK
    |
    +--> Connections/executors đóng đúng lifecycle
```

Nếu worker đang xử lý Redis Streams, việc dừng pod không tự đảm bảo pending messages được xử lý hết. Phải có consumer recovery/claim/idempotency phù hợp.

## 40. Kiểm thử probes trong integration test

Không nên chỉ mock một `HealthIndicator` và kết luận wiring Kubernetes đã đúng. Cần một số integration tests dùng Spring Boot/Redis test instance.

Ma trận kiểm thử:

| Test | Setup | Kỳ vọng |
|---|---|---|
| LIVE-01 | App chạy bình thường | Liveness UP |
| LIVE-02 | Redis mất, app còn sống | Liveness vẫn phản ánh app, không restart chỉ vì Redis |
| READY-01 | Startup chưa hoàn tất | Readiness chưa nhận traffic |
| READY-02 | Redis cache optional mất | Readiness theo policy, có thể vẫn UP |
| READY-03 | Redis critical mất | Readiness/endpoint failure theo hợp đồng |
| READY-04 | Graceful shutdown | Pod không nhận request mới |
| HEALTH-01 | PING thành công | Redis connectivity contributor UP |
| HEALTH-02 | User thiếu quyền SET | Write synthetic probe phát hiện, PING có thể vẫn UP |
| HEALTH-03 | Redis maxmemory noeviction | SET có thể OOM dù PING UP |
| HEALTH-04 | Endpoint Redis replica | Write probe thất bại READONLY |
| HEALTH-05 | Một Redis Cluster primary lỗi | Một seed PING không đại diện toàn cluster |
| CAP-01 | Load tăng dần | Xác định điểm SLO vi phạm dù probes UP |
| CAP-02 | Redis timeout/fallback | Đo DB load và service capacity suy giảm |
| CAP-03 | Stream producer nhanh hơn consumer | Lag/PEL tăng được phát hiện |

Với Kubernetes, có thể chạy test triển khai trên cluster thử nghiệm để xác nhận **endpoint paths/ports, HTTP codes, startupProbe và readiness service membership**. Test đơn thuần ở cấp `HealthIndicator.health()` không kiểm chứng kubelet/service routing.

## 41. Test fault injection nên theo giả thuyết rõ ràng

Trong Redis lab hoặc môi trường staging độc lập, có thể mô phỏng:

- Redis server tạm dừng hoặc connection bị cắt.
- Redis trả `NOPERM` cho `SET` nhưng cho `PING`.
- Redis giới hạn `maxmemory` để tạo OOM có kiểm soát.
- App Redis client trỏ nhầm replica, gặp `READONLY`.
- Redis Cluster thay primary/slot ownership.
- Latency mạng tăng theo ngưỡng thử nghiệm.
- Redis Stream consumer chậm/stop ACK.
- Cache miss storm sau Redis outage.

Mỗi test cần trả lời:

1. Probe nào thay đổi trạng thái?
2. Traffic vẫn được đưa tới pod hay không?
3. Application có trả lỗi đúng hợp đồng?
4. Client retry có làm thêm tải hay tạo duplicate side effect?
5. Metrics/alerts có phát hiện capacity suy giảm?
6. Khi dependency phục hồi, app có tự phục hồi mà không bị restart không cần thiết?
7. Có giữ đúng dữ liệu nghiệp vụ và pending recovery không?

**Không thực hiện failover, maxmemory reduction hoặc ACL denial trên Redis production chỉ để thử probes**. Có thể dùng Testcontainers, Redis lab và proxy tạo lỗi trong staging.

## 42. Đọc hiểu tình huống: readiness và health báo khác nhau

### Tình huống A

```text
/actuator/health        -> DOWN (redis contributor DOWN)
/actuator/health/liveness -> UP
/actuator/health/readiness -> UP
HTTP catalog requests   -> 200, latency tăng
```

Đây **không nhất thiết là cấu hình sai**. Nếu Redis chỉ là cache optional và source DB còn hoạt động, application có thể vẫn ready trong khi health tổng hợp báo một dependency hỏng.

Cần giám sát DB pressure, fallback rate và p99.

### Tình huống B

```text
/actuator/health/liveness -> UP
/actuator/health/readiness -> DOWN
Redis session unavailable
```

Có thể phù hợp nếu Redis session là dependency bắt buộc theo policy và instance không nên nhận traffic. Restart pod theo liveness là không cần thiết.

### Tình huống C

```text
PING Redis -> PONG
Readiness app -> UP
HTTP p99 -> 700 ms
Redis command p99 -> 100 ms
Redis CPU -> 98%
```

Hệ thống có vấn đề capacity/performance dù probes khỏe. Cần tối ưu workload, backpressure, hot key analysis hoặc scale Redis đúng điểm nghẽn.

### Tình huống D

```text
PING Redis -> PONG
GET -> OK
SET -> OOM
Redis maxmemory gần ngưỡng
```

Read-only use case còn dùng được; write path có thể thất bại. Phải xem loại workflow, memory policy và quyền/fallback.

## 43. Các sai lầm phổ biến

**“Redis trả PONG nghĩa là toàn hệ thống khỏe.”**  
Sai. PING chỉ phản ánh khả năng xử lý lệnh nhẹ ở một điểm; không kiểm chứng command permissions, memory, all slots hoặc capacity.

**“Redis DOWN thì liveness cũng phải DOWN.”**  
Thường sai. Dependency outage không được sửa bằng restart pod; có nguy cơ restart storm.

**“Readiness phải kiểm tra tất cả database, cache, broker và API bên ngoài.”**  
Không mặc định. Một dependency hỏng có thể không làm mọi endpoint mất khả năng phục vụ, và loại toàn bộ pods có thể khuếch đại outage.

**“Có health endpoint UP thì không cần load test.”**  
Sai. Health không chứng minh throughput hoặc p99 ở giờ cao điểm.

**“Nếu cache lỗi thì cứ fallback sang DB vô hạn.”**  
Sai. Fallback có thể làm database bão hòa, cần concurrency limits/circuit breaker.

**“Redis Cluster PING một node đủ để kiểm tra mọi hash slot.”**  
Sai. Một primary có thể khỏe khi node khác unreachable hoặc hot.

**“Tăng số pod luôn làm tăng Redis throughput.”**  
Sai. Nếu Redis primary là bottleneck, thêm pods còn có thể làm áp lực tăng.

**“Redis Stream XREADGROUP được là consumer khỏe.”**  
Chưa đủ. Cần đo xử lý nghiệp vụ, ACK success, pending age và khả năng reclaim.

**“Đưa synthetic SET vào liveness sẽ an toàn hơn.”**  
Thường ngược lại. Probe ghi tạo side effect, có thể lỗi OOM/ACL và kéo theo restart không sửa được nguyên nhân.

**“Readiness DOWN nghĩa là Kubernetes sẽ restart pod.”**  
Không. Readiness failure ảnh hưởng nhận traffic; liveness/startup failure mới có thể dẫn đến restart theo cấu hình.

## 44. Checklist triển khai quan sát Redis

- [ ] Xác định Redis là **cache optional** hay **critical dependency** của từng workflow.
- [ ] Liveness chỉ xét tình trạng tiến trình/cơ chế nội bộ mà restart có khả năng khắc phục.
- [ ] Readiness được thiết kế để quyết định traffic mới, không phải bản sao health tổng hợp.
- [ ] Startup probe đủ thời gian cho application khởi động thực tế.
- [ ] Redis health indicator có tên và phạm vi rõ: PING, read hay synthetic write.
- [ ] Probe có timeout/threshold, không thực hiện lệnh Redis nặng hoặc quét toàn keyspace.
- [ ] Synthetic writes dùng key riêng, TTL và ACL least privilege; không dùng business keys.
- [ ] Không lộ error details/Redis endpoints/credentials qua public Actuator.
- [ ] Đo p50/p95/p99 end-to-end theo endpoint và Redis command.
- [ ] Đo Redis memory, maxmemory headroom, OOM, eviction, CPU, connections.
- [ ] Đo cache hit/miss, Redis fallback rate và downstream DB saturation.
- [ ] Redis Cluster có per-primary metrics/slot visibility, không chỉ một seed probe.
- [ ] Có cảnh báo Stream lag, pending age và ACK throughput nếu dùng Streams.
- [ ] Có load test xác định headroom thực sự dưới traffic production-like.
- [ ] Có kiểm thử Redis outage và failover trong môi trường cô lập.
- [ ] Có circuit breaker/backpressure/rate limit bảo vệ downstream khi cache lỗi.
- [ ] Khi dependency phục hồi, service tự kết nối/khôi phục mà không gây retry storm.
- [ ] Readiness/liveness paths thực sự hoạt động trên port Kubernetes gọi.
- [ ] Metrics/tags tránh user ID, token và key cardinality cao.
- [ ] Runbook phân biệt connectivity failure, read/write permission, memory và capacity.

## 45. Câu hỏi tự kiểm tra kiến thức

**1. Redis PING thành công chứng minh điều gì?**  
Chủ yếu chứng minh một kết nối đến Redis endpoint cụ thể có thể thực hiện lệnh PING tại thời điểm kiểm tra. Không chứng minh write capacity, ACL mọi lệnh hay all Cluster slots.

**2. Tại sao không nên đưa Redis outage trực tiếp vào liveness?**  
Vì restart ứng dụng thường không sửa được Redis, có thể gây đồng loạt reconnect/retry và làm outage nặng hơn.

**3. Readiness khác liveness ở hành động Kubernetes nào?**  
Readiness điều khiển pod có được nhận traffic mới qua Service endpoints hay không; liveness failure đủ ngưỡng có thể khiến kubelet restart container.

**4. Redis cache optional bị mất, app có nhất thiết not ready không?**  
Không. Nếu dữ liệu nguồn còn phục vụ được theo hợp đồng, app có thể vẫn ready nhưng capacity và p99 có thể suy giảm.

**5. Redis là session store bắt buộc bị mất, cần xem xét điều gì?**  
Khả năng endpoint còn phục vụ đúng hợp đồng, policy fail-closed, readiness, và hậu quả nếu mọi pod cùng not ready; không chỉ nhìn PING.

**6. Redis PONG nhưng SET OOM là mâu thuẫn không?**  
Không. Lệnh PING nhẹ và write cần thêm bộ nhớ chịu giới hạn maxmemory/policy khác nhau.

**7. Làm sao kiểm tra Redis Cluster không chỉ một node?**  
Theo dõi cluster slot coverage, node roles, endpoints, per-primary metrics và thử đường lệnh theo scope phù hợp; một seed PING không đủ.

**8. Có nên chạy XADD synthetic mỗi 1 giây trong liveness không?**  
Thông thường không. Nó có side effect, làm stream phình ra và có thể tạo restart do lỗi dependency, cần dùng phép kiểm tra phù hợp hơn.

**9. Nếu GET hoạt động nhưng SET bị NOPERM, health PING có phát hiện không?**  
Không nhất thiết. Cần kiểm tra quyền/write path theo use case với synthetic probe có kiểm soát.

**10. p99 HTTP tăng cao mà readiness vẫn UP có thể là trạng thái hợp lệ không?**  
Có. Readiness và capacity là tín hiệu khác nhau; phải dùng SLO/metrics và phương án scale/backpressure.

**11. Khi Redis cache mất, vì sao database có thể là nguồn nghẽn mới?**  
Vì mọi cache miss hoặc Redis error đều chuyển sang đọc dữ liệu nguồn, tăng DB QPS/pool wait và p99.

**12. Redis Stream lag tăng nhưng PING vẫn tốt nghĩa là gì?**  
Hạ tầng còn trả lời lệnh nhẹ nhưng consumer processing/ACK capacity có thể thấp hơn tốc độ producer.

**13. Vì sao một key synthetic không chứng minh tất cả Redis Cluster slots khỏe?**  
Vì mỗi key thuộc một hash slot/node cụ thể, không bao phủ tất cả primary.

**14. Những chỉ số tối thiểu để đánh giá khả năng chịu tải là gì?**  
Throughput, p95/p99 latency, error rate, memory/CPU, pending commands/queue depth và tác động tới downstream.

**15. Khi nào có thể cân nhắc not ready vì Redis?**  
Khi Redis thực sự là dependency cần thiết để app phục vụ phần traffic mà readiness đại diện, và đã cân nhắc hệ quả loại pod trong outage toàn vùng.

## 46. Tổng kết

Ba thuật ngữ dễ bị trộn lẫn nhưng cần được vận hành riêng:

- **Health check** đánh giá một thành phần hoặc operation cụ thể, ví dụ Redis connectivity qua `PING` hoặc khả năng synthetic `SET` với TTL.
- **Liveness** đánh giá tiến trình còn có thể hoạt động hay cần restart; **không mặc định phụ thuộc Redis bên ngoài**.
- **Readiness** quyết định instance có nên nhận traffic mới, phụ thuộc vai trò thực sự của Redis trong nghiệp vụ và chiến lược degraded mode.
- **Capacity** đo khả năng đạt throughput, latency p95/p99, error rate và giới hạn tài nguyên khi tải tăng; Redis `PONG` không phải bằng chứng capacity.

Trong Spring Data Redis, thực hành tốt là dùng **Spring Boot Actuator** cho liveness/readiness rõ ràng; quan sát Redis connectivity, ACL, OOM, role/failover và Cluster topology theo từng phạm vi; đồng thời dùng **Micrometer/Redis metrics, benchmark và fault injection** để đánh giá năng lực phục vụ thực tế.

Khi Redis chỉ là cache, service có thể vẫn ready trong lúc Redis unhealthy — nhưng cần kiểm soát tải đổ về database. Khi Redis là dependency bắt buộc, readiness cần có chính sách tương xứng nhưng không gây restart storm. Khi Redis PING vẫn tốt mà p99 và error rate tăng, vấn đề nằm ở **khả năng chịu tải**, không phải điều kiện “còn sống” của server.

Một hệ thống quan sát trưởng thành phải trả lời được bốn câu: **“Redis còn phản hồi không?”, “ứng dụng có phục vụ traffic này không?”, “dưới bao nhiêu tải thì còn đạt SLO?” và “nếu dependency hỏng, hệ thống sẽ suy giảm và phục hồi như thế nào?”**

## Tài liệu tham khảo

- [Spring Boot Actuator — Production-ready Features](https://docs.spring.io/spring-boot/reference/actuator/index.html): health endpoints, monitoring và health groups.
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness, startup và bổ sung đường health trên port chính.
- [Spring Boot — Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health): health indicators, groups và HTTP status mappings.
- [Spring Data Redis — Redis Connection](https://docs.spring.io/spring-data/redis/reference/redis.html): RedisConnectionFactory và thao tác Redis.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): template, serializers và error handling.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache manager, TTL và fallback considerations.
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): cluster nodes, slot routing và topology.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Streams listeners, groups, ACK và pending.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): semantics và cấu hình probes.
- [Redis — PING](https://redis.io/docs/latest/commands/ping/): ý nghĩa và phản hồi PING.
- [Redis — INFO](https://redis.io/docs/latest/commands/info/): memory, clients, stats, replication và commandstats.
- [Redis — Key Eviction](https://redis.io/docs/latest/develop/reference/eviction/): maxmemory, eviction và OOM.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, failover và cluster behavior.
- [Redis — XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/): metrics của Redis Streams consumer groups.
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/): quan sát pending message.
- [Micrometer — Reference](https://docs.micrometer.io/micrometer/reference/): timers, metrics, histograms và registries.
