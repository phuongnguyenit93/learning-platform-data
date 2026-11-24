# Broker health trong Spring Boot

Trong chương **Health và readiness** của module **SPRING_BOOT_OBSERVABILITY**, broker health là trạng thái sức khỏe của message broker mà ứng dụng phụ thuộc để gửi hoặc nhận message. Với Spring Boot dùng JMS, broker có thể là ActiveMQ Artemis, IBM MQ hoặc một provider tương thích JMS khác. Kiểm tra broker health giúp phát hiện sớm tình trạng mất kết nối, xác thực thất bại hoặc broker không đáp ứng trước khi producer/consumer phát sinh lỗi hàng loạt.

Broker health không chỉ là “socket có mở hay không”. Một broker có thể reachable nhưng credentials không hợp lệ, destination không tồn tại, quyền publish/consume bị thiếu hoặc queue backlog tăng tới mức không đáp ứng SLA. Cần chọn health signals phù hợp với vai trò của ứng dụng, đồng thời tránh để health probe tạo thêm tải hoặc làm một dependency chập chờn khiến toàn bộ service liên tục bị restart.

Trong **SPRING_BOOT_OBSERVABILITY**, broker health cần được đọc cùng metrics, logs và distributed tracing. Health endpoint trả trạng thái tổng quát để orchestration/monitoring ra quyết định; broker metrics và traces giúp điều tra nguyên nhân. Bài này tập trung vào Spring Boot Actuator HealthIndicator, kết nối broker, readiness/liveness, queue signals, timeout/cache và kiểm thử thực tế.

## 1. Broker health gồm những khía cạnh nào?

Một message broker cung cấp nhiều khả năng: nhận kết nối, xác thực client, quản lý destination, lưu message, giao message cho consumer và xác nhận xử lý. Mỗi khả năng có thể gặp lỗi độc lập.

| Khía cạnh | Ví dụ tín hiệu | Câu hỏi vận hành |
| --- | --- | --- |
| Connectivity | Kết nối TCP/JMS có thể được thiết lập | Ứng dụng có liên lạc được broker không? |
| Authentication | JMS connection/session được tạo thành công | Credentials còn hợp lệ không? |
| Authorization | Producer/consumer được phép truy cập destination | Quyền publish/consume có đúng không? |
| Destination availability | Queue/topic tồn tại và có thể truy cập | Ứng dụng có gửi/nhận đúng destination không? |
| Broker capacity | Disk, memory, connection limits | Broker có đủ tài nguyên không? |
| Queue backlog | Queue depth, oldest message age | Consumer có theo kịp producer không? |
| Consumer availability | Consumer count, delivery rate | Có consumer hoạt động không? |
| Processing reliability | Redelivery, DLQ rate | Message có bị lỗi lặp lại không? |

Không phải tất cả signals đều nên được kiểm tra đồng bộ trong mỗi HTTP health request. Một probe nên ngắn, có giới hạn thời gian và chỉ kiểm tra những điều kiện cần thiết để service nhận traffic hoặc thực hiện nhiệm vụ.

## 2. Phân biệt broker health với application health

Broker có thể healthy trong khi ứng dụng không xử lý được message do lỗi code, schema mismatch hoặc database downstream. Ngược lại, broker có thể mất kết nối trong thời gian ngắn nhưng service vẫn phục vụ HTTP requests khác và có thể retry publish sau.

Phân biệt các góc nhìn:

- **Broker health:** trạng thái của broker/provider và tài nguyên broker.
- **Application dependency health:** ứng dụng hiện có thể thực hiện thao tác cần thiết với broker không.
- **Messaging flow health:** producer rate, consumer processing rate, backlog, redelivery và DLQ.
- **Business health:** workflow nghiệp vụ có hoàn thành trong SLA không.

Actuator HealthIndicator thường thể hiện trạng thái dependency ở góc nhìn ứng dụng. Queue depth, oldest message age và broker disk usage thường cần broker management metrics/exporter. Không suy ra broker healthy chỉ từ một UP do connection factory đã khởi tạo.

## 3. Spring Boot Actuator và HealthIndicator

Spring Boot Actuator cung cấp health endpoint và cơ chế đóng góp trạng thái qua HealthIndicator hoặc reactive health contributor. Một custom indicator có thể kiểm tra dependency mà ứng dụng cần.

Ví dụ indicator đơn giản cho JMS ConnectionFactory:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("jmsBroker")
class JmsBrokerHealthIndicator implements HealthIndicator {
    private final ConnectionFactory connectionFactory;

    JmsBrokerHealthIndicator(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    @Override
    public Health health() {
        try (Connection connection = connectionFactory.createConnection()) {
            connection.start();
            return Health.up()
                    .withDetail("broker", "connection-established")
                    .build();
        } catch (Exception ex) {
            return Health.down(ex)
                    .withDetail("broker", "connection-failed")
                    .build();
        }
    }
}
```

Đây là ví dụ minh họa API JMS cổ điển. Với Jakarta JMS, package jakarta.jms phù hợp các thế hệ Spring Boot mới; project cũ có thể dùng javax.jms. Cách tạo connection mỗi lần probe có thể tốn tài nguyên hoặc tạo tải lên broker, vì vậy không nên sao chép nguyên mẫu này vào production mà không thiết kế timeout, cache và tần suất kiểm tra.

Nếu connection factory dùng pool/caching layer, việc tạo connection có thể chỉ lấy connection đã tồn tại từ pool và không chứng minh broker đang đáp ứng một thao tác mới. Cần hiểu semantics của provider và wrapper trước khi xem probe là bằng chứng connectivity.

## 4. HealthIndicator nên kiểm tra gì?

| Check | Có thể xác nhận | Giới hạn |
| --- | --- | --- |
| ConnectionFactory bean tồn tại | Spring đã cấu hình bean | Không chứng minh broker reachable |
| Tạo JMS connection | Network và provider handshake cơ bản | Có thể chưa xác minh destination permission |
| Tạo session | Connection có thể mở session | Không chứng minh publish/consume được |
| Publish probe message | Producer có thể gửi tới destination test | Có side effect và cần cleanup/consumer |
| Consume probe message | Consumer có thể nhận message test | Cần destination và protocol test riêng |
| Broker management API | Có thể đọc broker state/capacity | Cần credential/quyền quản trị riêng |
| Queue depth/oldest age | Backlog và tuổi message | Thường lấy từ broker metrics, không phải connection probe |

Không nên publish message giả vào queue nghiệp vụ chỉ để health check. Nếu cần end-to-end probe, dùng destination riêng, correlation ID cố định theo probe run, TTL ngắn và consumer kiểm tra riêng; đảm bảo probe không bị xử lý như business event.

## 5. Readiness và liveness không giống nhau

Kubernetes và các nền tảng orchestration thường phân biệt hai câu hỏi:

- **Liveness:** process còn sống và có khả năng tiếp tục chạy không? Nếu fail liên tục, orchestrator có thể restart container.
- **Readiness:** instance hiện có nên nhận traffic/công việc mới không? Nếu fail, instance có thể bị loại khỏi service endpoints mà không restart.

Một broker dependency mất kết nối không nhất thiết có nghĩa JVM process bị treo. Nếu đưa broker health vào liveness, một sự cố broker có thể khiến mọi replica restart cùng lúc, tạo reconnect storm và làm broker phục hồi khó hơn.

Nếu ứng dụng không thể thực hiện nhiệm vụ cốt lõi khi broker unavailable, có thể đưa broker dependency vào readiness. Nếu service vẫn phục vụ HTTP và chỉ tạm thời buffer/retry message, quyết định readiness cần dựa trên khả năng thực tế và SLA. Không có một quy tắc chung cho mọi kiến trúc.

Ví dụ cấu hình health groups:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,jmsBroker
        liveness:
          include: livenessState
```

Property group và cách đặt tên health contributors phụ thuộc Spring Boot version. Kiểm tra output endpoint readiness/liveness thực tế. Nếu broker không phải dependency bắt buộc để nhận traffic, không thêm nó vào readiness một cách máy móc.

## 6. Khi nào broker nên ảnh hưởng readiness?

Đặt broker trong readiness khi instance không thể đảm nhận công việc chính nếu broker không khả dụng. Ví dụ:

- Consumer service chỉ làm nhiệm vụ nhận và xử lý message; không kết nối broker thì không thể hoàn thành nhiệm vụ.
- Producer API cam kết publish đồng bộ và không có outbox/buffer fallback; broker unavailable khiến request không thể đáp ứng contract.
- Service cần consumer subscription active để hoàn thành workflow bắt buộc trước khi nhận traffic.

Không nhất thiết đưa broker vào readiness nếu:

- HTTP API vẫn phục vụ các chức năng độc lập.
- Producer dùng transactional outbox và có thể lưu event vào database để publish lại.
- Client có retry/buffer bounded và hệ thống chấp nhận độ trễ message tạm thời.
- Broker là dependency tùy chọn cho một phần tính năng, không phải toàn bộ service.

Nếu một dependency chỉ ảnh hưởng một feature, có thể thể hiện health component riêng và để readiness tổng thể dựa trên yêu cầu phục vụ traffic. Tránh biến mọi dependency warning thành trạng thái DOWN toàn service.

## 7. Queue depth và backlog không đồng nghĩa connection health

Một broker có thể nhận kết nối bình thường nhưng queue backlog vẫn tăng. Ví dụ producer gửi 1.000 messages/phút trong khi consumer chỉ xử lý 700 messages/phút. Connection health có thể UP, nhưng messaging flow đang không đáp ứng throughput.

Các broker signals cần theo dõi:

- Queue depth hoặc pending message count.
- Oldest message age.
- Enqueue/dequeue rate.
- Active consumer count.
- Redelivery count/rate.
- Dead-letter queue depth/rate.
- Broker memory/disk usage và connection count.

HealthIndicator không nên query management API nặng cho từng HTTP request. Thu thập các signals này bằng broker exporter/management integration, rồi dùng metrics dashboard và alert để quan sát xu hướng. Nếu backlog vượt SLA, có thể phản ánh trạng thái degraded/readiness theo policy cụ thể.

## 8. Timeout, cache và tần suất health check

Health probe được gọi thường xuyên bởi orchestrator và monitoring system. Nếu mỗi lần gọi tạo connection mới, hệ thống có thể sinh nhiều connection attempts cùng lúc khi broker đang chậm.

Thiết kế probe cần:

1. **Timeout hữu hạn:** connection check không được treo lâu hơn ngân sách health endpoint.
2. **Bounded concurrency:** tránh hàng loạt probe đồng thời tạo tải lên broker.
3. **Cache ngắn hạn:** có thể dùng kết quả kiểm tra gần nhất để tránh reconnect liên tục, tùy yêu cầu freshness.
4. **Failure semantics rõ:** phân biệt timeout, authentication, authorization và destination errors khi log/metric.
5. **No sensitive details:** không trả broker URL, username, password hoặc stack trace cho caller không được phép.

Cache có trade-off: kết quả UP vừa cache có thể không phản ánh broker vừa mất kết nối; kết quả DOWN cache quá lâu có thể trì hoãn phục hồi readiness. Chọn TTL theo probe interval, broker recovery time và yêu cầu vận hành. Có thể dùng background checker cập nhật trạng thái gần nhất thay vì kiểm tra broker đồng bộ trên mỗi health request.

## 9. Không để health probe gây reconnect storm

Giả sử 30 replica cùng bị broker mất kết nối. Nếu mỗi replica có readiness/liveness probe mỗi giây và mỗi probe tạo một JMS connection, có thể xuất hiện hàng chục lần reconnect mỗi giây. Khi broker vừa phục hồi, health checks cạnh tranh connection với producer/consumer thực tế.

Các biện pháp:

- Reuse connection hoặc dùng provider-native health check có chi phí thấp nếu semantics phù hợp.
- Đặt timeout và backoff cho connection attempts.
- Cache kết quả probe với TTL ngắn và có jitter nếu có background checker.
- Giới hạn concurrency và tần suất management API calls.
- Tách liveness khỏi dependency checks để tránh restart loop.
- Theo dõi health probe duration/error rate như một tín hiệu riêng.

Health endpoint phải phản ánh trạng thái, không trở thành workload mới làm suy giảm dependency.

## 10. Graceful degradation và recovery

Khi broker unavailable, hành vi ứng dụng phụ thuộc vai trò:

**Producer:** có thể trả lỗi cho caller, ghi event vào outbox, hoặc buffer bounded trong memory/disk theo contract. Không giữ request thread vô hạn để chờ broker. Nếu dùng outbox, database commit và publish worker cần được quan sát riêng.

**Consumer:** có thể tạm dừng listener, reconnect theo backoff, để broker giữ message hoặc tiếp tục các chức năng độc lập. Tránh polling lỗi liên tục làm tăng log noise.

**Recovery:** sau khi broker phục hồi, kiểm tra consumer count, queue drain rate, oldest message age, redelivery và DLQ. Broker connection UP không có nghĩa backlog đã được xử lý xong.

Nếu queue backlog vượt SLA, service có thể vẫn healthy ở mức process nhưng degraded ở mức business flow. Dashboard nên thể hiện hai trạng thái thay vì ép mọi vấn đề vào một boolean UP/DOWN.

## 11. Logs và metrics cho broker health

| Signal | Ví dụ | Mục đích |
| --- | --- | --- |
| Health check status | UP/DOWN/UNKNOWN | Trạng thái dependency tổng quát |
| Probe duration | p95 health check duration | Phát hiện check chậm |
| Connection failures | Count theo error type hữu hạn | Phân biệt network/auth/provider |
| Reconnect attempts | Rate và retry count | Quan sát recovery behavior |
| Queue depth | Messages pending | Phát hiện backlog |
| Oldest message age | Seconds | Theo dõi SLA chờ xử lý |
| Consumer count | Active consumers | Phát hiện listener mất hoạt động |
| Redelivery/DLQ | Rate/count | Phát hiện message poison/failure |

Không dùng broker URL đầy đủ, message ID, queue name động theo request hoặc exception message làm metric tags. Queue/destination names nên ổn định và thuộc tập được quản lý.

Log event nên chứa service, broker alias đã chuẩn hóa, check type, outcome và error class. Không ghi credentials, connection string có secret hoặc raw message payload.

## 12. Cấu hình và vận hành theo môi trường

Một ứng dụng có thể chỉ expose health và Prometheus, đồng thời giới hạn chi tiết health:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
```

Nếu dùng readiness group riêng, include component broker theo vai trò của service và kiểm tra group endpoint. Không expose toàn bộ health component details ra public network.

Với môi trường test, có thể dùng embedded/test broker hoặc Testcontainers provider phù hợp để xác minh connection failures, credentials và listener behavior. Production readiness phải được kiểm tra bằng đúng broker provider, network path và security identity mà ứng dụng sử dụng.

## 13. Kiểm thử broker health

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Broker reachable, credentials đúng | Indicator UP theo semantics đã chọn |
| Broker không reachable | Indicator DOWN/OUT_OF_SERVICE theo policy, timeout hữu hạn |
| Credentials sai | Failure được phân loại, không lộ secret |
| User không có quyền destination | Authorization failure được phân biệt với connectivity |
| Broker chậm | Probe duration bị giới hạn, không treo health endpoint |
| Queue backlog lớn | Queue metrics/alert phản ánh degraded flow; không nhầm với TCP health |
| Consumer count bằng 0 | Consumer availability được phát hiện nếu role yêu cầu |
| Broker restart | Recovery/reconnect diễn ra có backoff, không tạo storm |
| Management API unavailable | Broker health check không bị nhầm với management exporter failure |
| Health caller anonymous | Không thấy details nhạy cảm |

Test không nên phụ thuộc vào hostname production hoặc broker dùng chung của team. Dùng broker test cô lập và kiểm soát trạng thái để có kết quả lặp lại.

## 14. Bài tập tình huống

Một hệ thống có 20 replica của payment-consumer. Broker bị restart trong 45 giây. Liveness probe hiện gọi custom HealthIndicator, và indicator tạo JMS connection mới mỗi lần. Sau khi broker phục hồi, số connection attempts tăng mạnh; một số pod liên tục restart. Queue depth vẫn tăng vì consumer chưa bắt kịp producer.

**Câu hỏi:**

1. Vì sao đưa broker connectivity vào liveness có thể làm sự cố nặng hơn?
2. Nên tách liveness và readiness như thế nào cho consumer-only service?
3. Vì sao broker connection UP chưa chứng minh messaging flow đã phục hồi?
4. Những metrics nào cần theo dõi trong giai đoạn recovery?
5. HealthIndicator nên được thiết kế lại ra sao để giảm tải?

**Gợi ý phân tích:**

- Liveness failure có thể restart tất cả pod cùng lúc, tạo reconnect storm và làm broker vừa phục hồi phải xử lý thêm connection attempts.
- Liveness nên tập trung vào process; readiness có thể phụ thuộc broker nếu consumer không thể đảm nhận nhiệm vụ khi broker unavailable.
- Connection chỉ chứng minh một phần connectivity/authentication; queue backlog và consumer throughput còn có thể chưa đạt SLA.
- Theo dõi consumer count, processing rate, queue depth, oldest message age, redelivery, DLQ, reconnect attempts và health probe duration.
- Dùng timeout hữu hạn, bounded concurrency, backoff và cache/background status checker phù hợp; không tạo connection mới trên mọi probe tick.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Broker health dimensions | Connectivity, auth, authorization, destination và capacity |
| HealthIndicator | Tạo custom dependency check có timeout |
| Readiness/liveness | Không dùng dependency outage làm restart trigger tùy tiện |
| Queue signals | Phân biệt connectivity với backlog/throughput |
| Timeout/cache | Giới hạn tần suất và tải health check |
| Recovery | Dùng backoff, tránh reconnect storm và theo dõi drain backlog |
| Metrics/logs | Quan sát probe, reconnect, queue age, redelivery và DLQ |
| Security | Không trả credentials hoặc broker details nhạy cảm |
| Testing | Kiểm tra broker down, auth failure, slow broker và recovery |

**Ghi nhớ:** Broker health cần phản ánh khả năng ứng dụng sử dụng broker theo vai trò thực tế, đồng thời phân biệt connectivity với queue backlog và consumer processing. Dùng Actuator HealthIndicator có timeout hữu hạn, bảo vệ health details và cân nhắc kỹ việc đưa broker vào readiness; tránh đưa dependency chập chờn vào liveness gây restart/reconnect storm. Theo dõi queue depth, oldest message age, consumer count, redelivery và DLQ bằng broker metrics; kết hợp logs/traces để điều tra. Khi broker phục hồi, connection UP mới chỉ là bước đầu, cần xác nhận consumer throughput và backlog đã trở lại SLA.
