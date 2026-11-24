# Health báo DOWN ngoài dự kiến trong Spring Boot

## 1. Mục tiêu và bối cảnh

Ứng dụng vẫn nhận request nhưng `/actuator/health` trả `DOWN` hoặc HTTP 503. Kubernetes có thể đánh dấu Pod không sẵn sàng, load balancer ngừng gửi traffic hoặc liveness probe khởi động lại container. Triệu chứng này thường xuất hiện khi một health contributor phụ thuộc ngoài gặp lỗi, status aggregation thay đổi kết quả tổng thể, hoặc custom indicator diễn giải sai trạng thái.

Health endpoint phản ánh chính xác những contributors được đưa vào group đang truy vấn và quy tắc tổng hợp status của chúng. `DOWN` không nhất thiết có nghĩa JVM đã chết hoặc mọi chức năng nghiệp vụ đều ngừng hoạt động. Cần xác định component nào báo lỗi, group nào đang được kiểm tra và consumer dùng kết quả đó để làm gì.

Bài thuộc chương **Chẩn đoán sự cố** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể:
1. Đọc aggregate status và component details của Actuator health.
2. Tìm contributor khiến health group chuyển sang DOWN.
3. Phân biệt overall health, liveness và readiness.
4. Kiểm tra status aggregation, order và HTTP mapping.
5. Chẩn đoán custom HealthIndicator, timeout và dependency failure.
6. Tránh probe phụ thuộc ngoài làm restart loop.
7. Viết test tái hiện trạng thái DOWN và xác minh cách khôi phục.

**Baseline:** Spring Boot 3.5.x, Java 17+, Spring Boot Actuator. Health contributors và property cụ thể phụ thuộc dependencies, application configuration và version.

## 2. Xác định endpoint và consumer đang báo lỗi

Trước tiên xác định URL được gọi và ai đang gọi nó:

| Endpoint | Consumer thường gặp | Ý nghĩa |
| --- | --- | --- |
| `/actuator/health` | Operator, dashboard, load balancer | Aggregate health của group mặc định |
| `/actuator/health/readiness` | Kubernetes readiness probe | Instance có nên nhận traffic không |
| `/actuator/health/liveness` | Kubernetes liveness probe | Process có cần được restart không |
| `/actuator/health/{group}` | Monitoring hoặc operator | Aggregate của group tùy chỉnh |

Không suy luận từ một HTTP 503 rằng toàn bộ ứng dụng không hoạt động. Ghi nhận endpoint cụ thể, timestamp, Pod/instance, profile và probe type. Một group readiness có thể DOWN trong khi liveness vẫn UP; đó có thể là hành vi mong muốn khi dependency chưa sẵn sàng.

## 3. Đọc aggregate status và component details

Khi được phép hiển thị details, gọi endpoint:

```bash
curl -i http://localhost:8080/actuator/health
```

Ví dụ response:

```json
{
  "status": "DOWN",
  "components": {
    "db": {
      "status": "DOWN",
      "details": {
        "error": "Connection refused"
      }
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

Ví dụ minh họa. Component names và detail fields phụ thuộc contributor. Ở đây `db` là manh mối đầu tiên: disk và process ping vẫn UP nhưng database health check không kết nối được.

Nếu response chỉ có `{"status":"DOWN"}`, details có thể đang bị ẩn bởi policy. Không nên bật hiển thị công khai để debug. Dùng principal vận hành được ủy quyền hoặc kiểm tra log/metrics nội bộ.

## 4. Hiểu cách aggregate status

Actuator thu thập status từ các contributors trong group rồi dùng `StatusAggregator` để tạo kết quả tổng thể. Theo mặc định, status nghiêm trọng hơn có thể chi phối aggregate. Vì vậy một contributor DOWN có thể làm toàn bộ group DOWN dù các component khác UP.

Các status phổ biến:

| Status | Ý nghĩa khái quát |
| --- | --- |
| `UP` | Contributor hoạt động bình thường |
| `DOWN` | Contributor không hoạt động theo health check |
| `OUT_OF_SERVICE` | Thành phần không nên phục vụ traffic |
| `UNKNOWN` | Không xác định được trạng thái |

Ứng dụng có thể định nghĩa custom status. Nếu custom status không nằm trong `status.order`, thứ tự ưu tiên có thể không như mong đợi. Kiểm tra status thực tế và aggregator config thay vì giả định DOWN là status duy nhất có thể làm aggregate fail.

Ví dụ cấu hình thứ tự:

```yaml
management:
  endpoint:
    health:
      status:
        order: DOWN, OUT_OF_SERVICE, UNKNOWN, UP
```

Chỉ thay đổi thứ tự khi semantics của status đã được thống nhất. Nếu đặt một custom status ở mức ưu tiên thấp hơn UP, health có thể báo UP trong khi contributor đang báo trạng thái cần ngừng traffic.

## 5. Xác định contributor gây DOWN

Đi theo thứ tự:

1. Lấy component details qua endpoint/group có quyền xem.
2. Ghi tên contributor, status, exception class và timestamp.
3. Đối chiếu logs của đúng instance cùng thời điểm.
4. Kiểm tra dependency tương ứng bằng health/metrics độc lập.
5. Xác nhận contributor có nằm trong group đang bị probe hay không.
6. Kiểm tra contributor được auto-configure từ dependency hay do ứng dụng tự đăng ký.

Các contributors thường gặp:

| Contributor | Nguyên nhân DOWN thường gặp | Kiểm tra |
| --- | --- | --- |
| `db` | DB unavailable, sai credentials, pool cạn, network lỗi | DB connectivity, pool active/pending/timeouts, secrets/config |
| `diskSpace` | Dung lượng dưới threshold | Filesystem, volume mount, threshold |
| `redis`/cache | Cache server không kết nối được | DNS, auth, timeout, server health |
| `mongo`/search | Dependency unavailable | Connection string, TLS, server status |
| `rabbit`/messaging | Broker không reachable hoặc credentials sai | Broker health, network, credentials |
| Custom indicator | Logic/exception/timeout trong code | Source, timeout, logs và unit tests |

Không phải mọi ứng dụng đều có tất cả contributors này. Chúng thường xuất hiện khi dependency tương ứng và auto-configuration có mặt.

## 6. Database health báo DOWN

Database indicator có thể thực hiện một thao tác kiểm tra qua datasource. DOWN có thể do:
- Database server dừng hoặc đang failover.
- DNS, routing, firewall hoặc TLS handshake thất bại.
- Username/password/secret sai hoặc vừa rotate.
- Connection pool hết connection hoặc không tạo connection mới được.
- Database giới hạn số connections.
- Health query bị chặn bởi lock hoặc database quá tải.
- Health check timeout quá ngắn so với môi trường.

Kiểm tra cùng lúc:

```text
Application:
  hikaricp active / idle / max / pending / timeout
  JDBC connection errors
  datasource health duration

Database:
  server availability
  active sessions / max connections
  lock waits / deadlocks
  CPU / disk / replication state
```

Nếu business queries vẫn thành công nhưng health query thất bại, xem lại health indicator, query validation, datasource routing và credentials mà indicator sử dụng. Không tắt health check chỉ để làm status xanh khi dependency thật sự không ổn định.

## 7. DiskSpace health báo DOWN

Disk space contributor thường so sánh dung lượng trống của filesystem với threshold. Nó có thể báo DOWN khi:
- Container writable layer gần đầy.
- Log files tăng không giới hạn.
- Temporary files hoặc heap dump chiếm dung lượng.
- Persistent volume gần hết.
- Indicator kiểm tra filesystem khác với volume chứa dữ liệu quan trọng.

Kiểm tra filesystem từ đúng container/Pod và so sánh với path mà indicator sử dụng. Không tăng threshold tùy tiện để che dấu nguy cơ hết đĩa. Xử lý nguyên nhân: log rotation, retention, temporary-file cleanup hoặc mở rộng volume theo capacity policy.

## 8. Health group và readiness/liveness

Overall health có thể chứa nhiều contributors hơn readiness/liveness. Kiểm tra cấu hình group:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
```

Ví dụ này đưa database vào readiness và chỉ dùng liveness state cho liveness. Quyết định đưa DB vào readiness phải dựa trên việc service có thể xử lý traffic có ý nghĩa nếu DB không hoạt động hay không.

**Liveness** nên phản ánh process có khả năng tiếp tục chạy và tự phục hồi hay không. Không đưa database, remote API hoặc broker vào liveness theo mặc định. Nếu dependency chung bị down, mọi Pod có thể bị restart đồng loạt và tạo restart storm.

**Readiness** quyết định instance có nhận traffic không. Nếu dependency bắt buộc đang unavailable, readiness có thể DOWN để ngừng route traffic tới instance. Nhưng nếu một dependency tùy chọn hỏng, không nhất thiết phải đánh dấu toàn service NOT_READY.

Kiểm tra cấu hình Kubernetes probe: path, port, initial delay, period, timeout và failure threshold. Probe quá gắt có thể biến một spike ngắn thành trạng thái không ổn định.

## 9. Custom HealthIndicator luôn DOWN

Custom indicator thường gây lỗi do:
- Dependency injection không đúng hoặc client chưa khởi tạo.
- Gọi remote service không có timeout.
- Catch exception rồi luôn trả `Health.down()`.
- Dùng điều kiện sai, ví dụ null/empty bị coi là unavailable.
- Dùng side effect hoặc business query nặng.
- Indicator chạy trên thread/event loop không phù hợp.

Ví dụ implementation có timeout và phân biệt trạng thái:

```java
@Component
class SearchHealthIndicator implements HealthIndicator {
    private final SearchClient client;

    SearchHealthIndicator(SearchClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.pingWithTimeout(Duration.ofSeconds(2));
            return Health.up().build();
        } catch (SearchUnavailableException ex) {
            return Health.down()
                    .withDetail("reason", "search unavailable")
                    .build();
        }
    }
}
```

Ví dụ dùng API `pingWithTimeout` giả định của ứng dụng; thay bằng client thực tế có timeout hữu hạn. Chỉ trả detail an toàn, không đưa exception message chứa host, credentials hoặc request data ra response.

Đừng catch mọi `Exception` rồi trả DOWN mà không log/metric nội bộ. Cần giữ exception class và nguyên nhân ở kênh được bảo vệ để phân biệt lỗi cấu hình, lỗi network và lỗi lập trình.

## 10. Timeout và health check bị treo

Health endpoint có thể bị chậm nếu contributor gọi dependency tuần tự hoặc chờ vô hạn. Khi nhiều probes đến đồng thời, health checks có thể tạo thêm tải lên dependency đang quá tải.

Kiểm tra:
- Timeout của HTTP/JDBC client mà indicator sử dụng.
- Số contributors chạy đồng thời và tổng thời gian response.
- Thread pool/executor hoặc event loop có bị block không.
- Health check có tạo connection/query mới ở mỗi lần gọi không.
- Có cache health result ngắn hạn phù hợp hay không.

Chỉ cache nếu semantics và freshness chấp nhận được; không cache DOWN/UP quá lâu khiến probe không phản ánh trạng thái phục hồi. Với reactive stack, dùng `ReactiveHealthIndicator` và non-blocking client; không block event loop.

## 11. Security làm details bị ẩn hoặc probe bị chặn

Health details có thể bị ẩn do:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
```

`when-authorized` chỉ hiển thị details cho caller được xác thực/ủy quyền theo Spring Security configuration. Nếu Kubernetes kubelet hoặc load balancer nhận 401/403, probe có thể thất bại dù component status đang UP.

Kiểm tra SecurityFilterChain hiện tại, request matcher, management port và identity của probe. Cho phép probe path theo policy network/identity phù hợp; không mở toàn bộ Actuator hoặc chuyển `show-details: always` để giải quyết 401.

## 12. Status mapping và HTTP 503

Aggregate status được ánh xạ sang HTTP status. Theo cấu hình mặc định thường gặp, UP trả 200, DOWN/OUT_OF_SERVICE trả 503. Status order và HTTP mapping có thể tùy chỉnh.

Ví dụ:

```yaml
management:
  endpoint:
    health:
      status:
        http-mapping:
          DOWN: 503
          OUT_OF_SERVICE: 503
          UP: 200
```

Nếu UI báo DOWN nhưng HTTP trả 200, kiểm tra custom mapping. Nếu contributor UP nhưng endpoint trả 503, kiểm tra aggregate contributors/group và custom status mapping. Không đổi HTTP mapping để che lỗi: orchestrator có thể tiếp tục route traffic vào instance không sẵn sàng.

## 13. Quy trình điều tra nhanh

1. Xác định endpoint chính xác: overall, readiness, liveness hay custom group.
2. Ghi instance/Pod, timestamp, profile và HTTP status.
3. Lấy component details qua quyền vận hành được phép.
4. Xác định contributor đầu tiên có status khác UP.
5. Kiểm tra logs, exception class và dependency metrics của contributor đó.
6. Xác minh health group include/exclude và auto-configured contributors.
7. Kiểm tra timeout, status order, custom status và HTTP mapping.
8. Đối chiếu Kubernetes probe path/port/threshold.
9. Sửa nguyên nhân và xác nhận contributor trở lại UP.
10. Kiểm tra readiness/liveness và traffic routing phục hồi đúng; theo dõi để chắc không tái diễn.

## 14. Kiểm thử tái hiện DOWN ngoài dự kiến

### 14.1. Unit test custom indicator

Mock dependency để kiểm tra các nhánh:
- Dependency healthy → UP.
- Dependency unavailable → DOWN hoặc OUT_OF_SERVICE theo policy.
- Timeout → status đã định nghĩa, không treo test.
- Unexpected exception → được ghi nhận và không làm lộ dữ liệu nhạy cảm.

### 14.2. Integration test health endpoint

```java
mockMvc.perform(get("/actuator/health"))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.status").value("DOWN"));
```

Test trên giả định health contributor test đang DOWN và HTTP mapping mặc định/được cấu hình trả 503. Cần cấu hình fixture rõ ràng; không phụ thuộc database hoặc network thật trong unit test.

### 14.3. Test groups và probes

- Database DOWN không làm liveness DOWN nếu DB không thuộc liveness group.
- Database DOWN làm readiness DOWN chỉ khi đó là dependency bắt buộc và được include.
- Contributor ngoài group không ảnh hưởng group result.
- Caller không đủ quyền không nhìn thấy details.
- Probe path/port trong Kubernetes khớp management/server configuration.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Overall health DOWN nhưng readiness UP | Contributor phụ trong overall group bị DOWN | Xem component details và group membership |
| Readiness DOWN, liveness UP | Dependency bắt buộc chưa sẵn sàng | Kiểm tra dependency; tránh restart process nếu vẫn sống |
| Mọi Pod restart khi DB down | DB nằm trong liveness group | Chuyển dependency check sang readiness nếu phù hợp |
| DB component DOWN nhưng query nghiệp vụ vẫn chạy | Health query/credential/route khác business datasource | Kiểm tra indicator và datasource thực tế |
| DiskSpace DOWN | Filesystem path dưới threshold | Kiểm tra đúng mount, logs, temp files và volume |
| Custom indicator luôn DOWN | Logic/exception/timeout sai | Unit test các nhánh và đặt timeout |
| Health endpoint treo | Contributor I/O không timeout hoặc block thread | Timeout hữu hạn, non-blocking client và giảm probe cost |
| HTTP 503 nhưng components UP | Custom status/aggregator hoặc group mismatch | Kiểm tra status order và contributors thực sự được query |
| HTTP 200 dù status custom degraded | HTTP mapping hoặc status order không phù hợp | Xác minh consumer semantics và mapping |
| Kubernetes probe 401/403 | Security matcher chặn kubelet | Điều chỉnh access cho probe path theo policy |
| Details không xuất hiện | show-details/show-components ẩn | Dùng operator identity được authorize |
| Status dao động UP/DOWN | Dependency chập chờn hoặc probe quá thường xuyên | Xem latency/error timeline, timeout và threshold |
| Probe fail sau deployment | Startup chưa hoàn tất hoặc initial delay quá ngắn | Kiểm tra startup/readiness state và probe timing |

## 16. Checklist production

- [ ] Biết endpoint/group nào được load balancer và orchestrator gọi.
- [ ] Có thể xác định contributor gây DOWN qua details hoặc log nội bộ.
- [ ] StatusAggregator order và HTTP mapping được hiểu rõ.
- [ ] Liveness chỉ kiểm tra khả năng process tự phục hồi.
- [ ] Readiness chỉ gồm dependencies cần thiết để nhận traffic.
- [ ] Custom indicators nhanh, có timeout và không có side effects.
- [ ] Database/disk/network checks được kiểm tra từ đúng runtime environment.
- [ ] Health details được bảo vệ bằng authorization.
- [ ] Probe path, port, timeout, period và thresholds đã được test.
- [ ] Có tests cho UP, DOWN, timeout, group membership và recovery.
- [ ] Alert phân biệt health degradation với process liveness failure.

## 17. Câu hỏi tự luyện

1. Vì sao một contributor DOWN có thể làm aggregate health DOWN?
2. Component details giúp khoanh vùng nguyên nhân thế nào?
3. Overall health khác readiness/liveness ở đâu?
4. Vì sao database outage không nên mặc định làm liveness fail?
5. Health group include/exclude ảnh hưởng aggregate ra sao?
6. StatusAggregator order và HTTP mapping giải quyết hai việc gì?
7. Những nguyên nhân nào làm DB indicator DOWN dù query nghiệp vụ vẫn chạy?
8. Vì sao custom HealthIndicator cần timeout hữu hạn?
9. Khi nào readiness nên phụ thuộc remote service?
10. Làm thế nào phân biệt probe 401/403 với component DOWN?
11. Vì sao không nên đổi mapping để che trạng thái DOWN?
12. Cần test những trường hợp nào trước khi triển khai Kubernetes probes?

## Tài liệu tham khảo

- [Spring Boot 3.5 — Health Endpoint](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot 3.5 — Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)

