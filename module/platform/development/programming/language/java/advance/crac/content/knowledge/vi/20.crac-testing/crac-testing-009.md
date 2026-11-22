# Kiểm thử dịch vụ phụ thuộc chậm, mất kết nối hoặc chưa sẵn sàng

Ứng dụng Java thường phụ thuộc vào database, message broker, HTTP API, DNS/service discovery, secret manager, filesystem hoặc một dịch vụ nội bộ khác. Khi dùng CRaC, ứng dụng có thể được checkpoint rồi restore sau một khoảng thời gian. Trong khoảng đó, các dịch vụ bên ngoài vẫn tiếp tục hoạt động và thay đổi độc lập: service có thể khởi động chậm, endpoint có thể đổi, connection có thể bị đóng, credential có thể hết hạn hoặc một dependency có thể tạm thời không truy cập được.

Một lần restore thành công ở cấp JVM vì thế chưa chứng minh ứng dụng có thể phục vụ request. Cần kiểm thử các tình huống dependency phản hồi chậm, kết nối bị ngắt và dependency chưa sẵn sàng; xác nhận callback CRaC có giới hạn thời gian; kiểm tra ứng dụng chuyển readiness đúng trạng thái; và bảo đảm request không đi qua tài nguyên cũ hoặc dữ liệu không còn hợp lệ.

## 1. Phân biệt các dạng lỗi dependency

Không nên gom mọi sự cố thành “service down”. Các kiểu lỗi khác nhau cần cách tạo lỗi và tiêu chí kiểm thử riêng.

| Tình huống | Biểu hiện | Ví dụ | Điều cần xác nhận |
| --- | --- | --- | --- |
| Phản hồi chậm | Kết nối thành công nhưng phản hồi sau thời gian dài | HTTP API xử lý chậm, database query bị lock | Request timeout và callback deadline được áp dụng đúng. |
| Kết nối bị từ chối | Không thiết lập được TCP connection | Service chưa listen hoặc port sai | Client phân loại lỗi connect và retry có giới hạn. |
| Kết nối bị reset/đóng | Socket đang dùng bị peer hoặc network đóng | Pod bị thay thế, database failover, broker channel đóng | Pool loại bỏ connection hỏng và tạo connection mới. |
| Mất gói hoặc mạng bị gián đoạn | Kết nối có thể treo hoặc timeout thay vì báo lỗi ngay | Network partition, route thay đổi | Client có timeout cho từng tầng, không chờ vô hạn. |
| DNS/service discovery lỗi | Hostname không phân giải được hoặc trả endpoint cũ | DNS record đổi, resolver tạm thời không truy cập | Cache và endpoint được refresh theo policy. |
| Dependency chưa sẵn sàng | Process đã chạy nhưng service chưa nhận request | Database đang recovery, broker chưa elect leader | Readiness vẫn từ chối traffic cho tới khi probe thành công. |
| Authentication thất bại | Server phản hồi unauthorized/forbidden | Credential hết hạn hoặc bị rotation | Refresh credential đúng cách; không retry vô hạn với secret cũ. |
| Quá tải hoặc giới hạn tài nguyên | 429, 503, connection pool cạn, queue đầy | Rate limit hoặc service saturation | Backoff, bulkhead và load shedding hoạt động. |
| Phản hồi không hợp lệ | Có kết nối nhưng payload/schema không đúng | API trả lỗi định dạng hoặc version không tương thích | Không phân loại lỗi dữ liệu vĩnh viễn thành lỗi mạng để retry vô hạn. |

Phân biệt lỗi tạm thời và lỗi không thể tự phục hồi. Timeout, reset và 503 có thể tạm thời; 401 có thể cần refresh token; 403 thường là vấn đề quyền; schema mismatch hoặc dữ liệu đầu vào sai thường cần sửa cấu hình/code. Retry chỉ hữu ích khi nguyên nhân có khả năng thay đổi trong thời gian retry.

## 2. Vì sao cần kiểm thử riêng cho CRaC?

Khi checkpoint, trạng thái trong heap có thể chứa client, connection pool, cache, DNS result, token, scheduler và trạng thái circuit breaker. Các object này vẫn có thể tồn tại sau restore, nhưng dependency bên ngoài có thể đã thay đổi.

Ví dụ một connection pool được tạo trước checkpoint có thể chứa:

- Socket đã bị server đóng trong thời gian process tạm dừng.
- Connection tới IP cũ sau khi DNS hoặc service discovery thay đổi.
- Session database đã hết timeout hoặc bị failover.
- TLS session/certificate state không còn phù hợp.
- Credential cũ được dùng để mở connection mới.

Tương tự, một scheduler có thể giữ lịch refresh đã quá hạn; circuit breaker có thể giữ trạng thái `OPEN` dù dependency đã hồi phục, hoặc `CLOSED` dù service hiện đã lỗi. Một cache trong heap có thể vẫn trả dữ liệu cũ dù nguồn đã thay đổi.

Do đó, test CRaC cần xác nhận cả ba lớp:

1. **Process:** JVM có restore và chạy callback thành công không?
2. **Resource:** client, pool, socket, scheduler và credential có được làm mới hoặc kiểm tra đúng không?
3. **Service behavior:** readiness, request, message processing và dữ liệu nghiệp vụ có hoạt động đúng khi dependency chậm hoặc lỗi không?

## 3. Xác định chính sách ứng dụng trước khi viết test

Không phải mọi dependency đều cần xử lý giống nhau. Trước khi fault injection, xác định dependency nào bắt buộc để ứng dụng sẵn sàng và dependency nào có thể hoạt động degraded.

| Loại dependency | Chính sách thường gặp | Readiness sau restore |
| --- | --- | --- |
| Database chứa dữ liệu nghiệp vụ bắt buộc | Phải kết nối và xác thực trước khi phục vụ thao tác cần DB | `NOT_READY` nếu không thể mở connection hoặc health query thất bại. |
| Message broker cho consumer bắt buộc | Tạo consumer/session mới, subscribe và xác nhận trạng thái group/queue | `NOT_READY` nếu ứng dụng không thể nhận hoặc xử lý message theo yêu cầu. |
| HTTP service bắt buộc trong mọi request | Kiểm tra connectivity hoặc dùng probe phù hợp | Có thể `NOT_READY` nếu không có chế độ fallback. |
| HTTP service chỉ dùng cho một tính năng tùy chọn | Dùng timeout, circuit breaker và fallback có giới hạn | Có thể `READY` nếu phần chức năng còn lại vẫn đáp ứng SLO. |
| Secret manager | Cần credential mới để tạo client hoặc kết nối database | `NOT_READY` nếu chưa lấy được secret hợp lệ. |
| Telemetry/metrics exporter | Có thể buffer hoặc bỏ telemetry trong thời gian ngắn | Thường không nên chặn readiness của nghiệp vụ chính. |
| Cache có thể nạp lại | Invalidate hoặc refresh theo policy | Phụ thuộc loại dữ liệu; cache quyền/credential cần kiểm tra trước khi dùng. |

Ghi rõ degraded mode nào được phép, trong bao lâu và với giới hạn nào. Không đánh dấu ứng dụng `READY` chỉ vì process còn sống nếu dependency bắt buộc chưa hoạt động.

## 4. Thiết kế test theo thời điểm trong chu kỳ checkpoint–restore

Nên kiểm thử dependency ở nhiều thời điểm, vì lỗi trước checkpoint khác lỗi xảy ra trong thời gian process bị dừng hoặc sau restore.

| Thời điểm tạo lỗi | Kịch bản | Kết quả cần kiểm tra |
| --- | --- | --- |
| Trước khi checkpoint | Dependency chậm hoặc mất kết nối trong khi request/transaction đang chạy | Ứng dụng drain công việc trong deadline; không checkpoint khi transaction còn ở trạng thái không an toàn. |
| Trong `beforeCheckpoint` | Connection pool không đóng được hoặc worker không hoàn tất | Callback timeout/fail đúng cách; không báo chuẩn bị thành công giả. |
| Sau khi checkpoint, trước restore | Dependency bị restart, DNS đổi, credential rotate, network policy thay đổi | Restore không dùng giả định rằng trạng thái bên ngoài còn nguyên. |
| Trong `afterRestore` | Dependency chưa listen hoặc secret manager chưa sẵn sàng | Retry có giới hạn; callback/readiness phản ánh trạng thái chưa sẵn sàng. |
| Ngay sau khi readiness mở | Dependency ngắt lại khi traffic bắt đầu | Request có timeout, retry an toàn và circuit breaker/bulkhead hoạt động. |
| Trong lúc ứng dụng đã ổn định | Dependency failover hoặc network partition | Ứng dụng phục hồi kết nối mà không cần process restart không cần thiết. |
| Checkpoint bị abort | Một số resource đã dừng nhưng checkpoint không hoàn tất | Coordinator rollback/resume hoặc giữ `NOT_READY` theo policy; không chờ `afterRestore` để rollback. |

Mỗi test nên ghi lại checkpoint attempt id, restore attempt id, dependency state và thời điểm fault được bật/tắt. Điều này giúp phân biệt lỗi do CRaC callback với lỗi do dependency chưa sẵn sàng.

## 5. Tạo lỗi có kiểm soát trong môi trường test

Fault injection cần tái lập được và chỉ tác động tới môi trường thử nghiệm. Có thể kết hợp fake dependency, mock server, proxy mạng và container thật.

| Công cụ/kỹ thuật | Phù hợp để kiểm thử | Giới hạn |
| --- | --- | --- |
| Fake/stub trong unit test | Timeout logic, retry, state transition, readiness và lỗi xác định | Không mô phỏng đầy đủ TCP, TLS, DNS hoặc behavior thật của driver. |
| WireMock hoặc mock HTTP server | HTTP 5xx, 429, response delay, malformed response, endpoint unavailable | Không thay thế kiểm thử protocol/database thật. |
| Toxiproxy | TCP latency, connection reset, timeout, bandwidth limit và network partition giữa client với service | Cần đặt proxy đúng trên đường kết nối và kiểm soát lifecycle của proxy. |
| Testcontainers | Database, broker và dependency thật trong container | Khởi động container không tự mô phỏng mọi failure; cần kết hợp proxy hoặc thao tác điều khiển service. |
| Docker Compose test environment | Thử dependency startup order, service restart và network topology | Kết quả phụ thuộc Docker/network setup và không đại diện hoàn toàn cho Kubernetes. |
| Kubernetes staging/chaos tooling | Pod restart, readiness delay, network policy, node disruption | Chỉ chạy trong namespace thử nghiệm và có giới hạn phạm vi rõ ràng. |

Ví dụ cấu hình WireMock có thể làm HTTP API phản hồi chậm hoặc lỗi:

```java
stubFor(get(urlEqualTo("/catalog"))
    .willReturn(aResponse()
        .withStatus(503)
        .withFixedDelay(3000)
        .withBody("temporarily unavailable")));
```

Ví dụ minh họa một response chậm 3 giây và trả 503. Cú pháp import/helper tùy phiên bản WireMock đang dùng. Có thể thay status, delay hoặc body để kiểm thử từng nhánh phân loại lỗi.

Toxiproxy phù hợp khi cần kiểm tra connection reset hoặc latency ở tầng TCP. Hãy cấu hình proxy giữa ứng dụng và dependency, sau đó bật/tắt toxic theo từng test. Nếu muốn kiểm tra DNS, cần điều khiển resolver hoặc hostname test riêng; thêm latency TCP không mô phỏng được lỗi phân giải tên.

Không nên dùng một test duy nhất với tất cả fault cùng lúc. Bắt đầu bằng một lỗi có thể lặp lại, xác nhận ứng dụng phản ứng đúng, rồi mới kết hợp nhiều lỗi để mô phỏng sự cố phức tạp.

## 6. Kiểm thử dependency khởi động chậm hoặc chưa sẵn sàng

Một dependency có thể mất vài giây hoặc vài phút để phục hồi sau deploy/failover. Test cần mô phỏng trường hợp JVM restore xong trước khi dependency listen hoặc chấp nhận request.

Kịch bản cơ bản:

1. Khởi động ứng dụng và tạo checkpoint hợp lệ.
2. Dừng dependency hoặc cấu hình nó chờ trước khi listen.
3. Restore ứng dụng.
4. Xác nhận ứng dụng không mở readiness ngay khi JVM tiếp tục chạy.
5. Xác nhận reconnect có deadline và retry/backoff.
6. Khởi động dependency sau một khoảng delay nằm trong retry window.
7. Xác nhận ứng dụng kết nối thành công, health check đạt và readiness chuyển sang accepting traffic.
8. Lặp lại với delay dài hơn retry window để xác nhận ứng dụng fail theo policy và không chờ vô hạn.

Không nên kiểm thử bằng cách chỉ sleep một khoảng thời gian cố định rồi hy vọng service đã sẵn sàng. Hãy chờ một điều kiện cụ thể như port listen, health endpoint trả trạng thái healthy hoặc một truy vấn read-only thành công; vẫn cần giới hạn thời gian chờ.

### Readiness, liveness và startup probe

Ba loại probe trả lời các câu hỏi khác nhau:

- **Readiness:** instance có nên nhận traffic ngay lúc này không?
- **Liveness:** process có còn sống và có khả năng tự tiếp tục không, hay cần restart?
- **Startup probe:** ứng dụng đã hoàn tất giai đoạn khởi tạo/restore dài hay chưa?

Dependency tạm thời chưa sẵn sàng thường nên làm readiness fail, không nhất thiết làm liveness fail. Nếu liveness phụ thuộc trực tiếp vào database hoặc broker, một outage bên ngoài có thể khiến Kubernetes restart liên tục mọi instance, làm sự cố nặng hơn. Chọn policy theo khả năng tự phục hồi của ứng dụng và yêu cầu vận hành.

Trong Spring Boot, có thể dùng Availability API để giữ trạng thái từ chối traffic trong lúc reconnect:

```java
AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.REFUSING_TRAFFIC);

// Refresh credentials, reconnect dependencies, validate clients...

AvailabilityChangeEvent.publish(
    applicationContext,
    ReadinessState.ACCEPTING_TRAFFIC);
```

Đây là ví dụ minh họa; chỉ publish `ACCEPTING_TRAFFIC` sau khi mọi dependency bắt buộc đã đạt health criteria. Với ứng dụng không dùng Spring Boot, triển khai readiness gate tương đương ở HTTP health endpoint hoặc service registry.

## 7. Kiểm thử response chậm và timeout ở từng tầng

Một request tới dependency có thể chờ ở nhiều nơi:

1. Lấy connection từ pool.
2. Phân giải DNS.
3. Thiết lập TCP connection.
4. TLS handshake.
5. Gửi request và chờ response.
6. Thực thi query hoặc xử lý ở server.
7. Đọc body/response.
8. Retry sau lỗi.

Chỉ cấu hình một `readTimeout` không có nghĩa toàn bộ request có giới hạn thời gian. Ví dụ connection pool có thể chờ lấy connection vô hạn; DNS có thể chậm; retry có thể kéo dài tổng thời gian vượt xa timeout của từng lần gọi.

Nên có deadline tổng và timeout ở tầng tương ứng:

| Tầng | Timeout cần xem xét |
| --- | --- |
| Connection pool | Thời gian tối đa chờ lấy connection. |
| DNS | Timeout resolver hoặc giới hạn thời gian lookup nếu client hỗ trợ. |
| TCP | Connect timeout. |
| TLS | Handshake timeout hoặc timeout tổng bao quanh kết nối nếu thư viện không có riêng. |
| HTTP | Response/read timeout và call timeout tổng. |
| JDBC | Connection timeout, query timeout, socket/network timeout theo driver. |
| Broker | Timeout khi connect, poll, publish, ack/commit và heartbeat/session policy. |
| Retry | Tổng retry budget nằm trong deadline của request/callback. |

Ví dụ, một callback có ngân sách 20 giây không nên gọi ba dependency tuần tự, mỗi dependency có retry tối đa 20 giây. Các thao tác con phải dùng phần thời gian còn lại của deadline tổng.

## 8. Kiểm thử retry, backoff và jitter

Retry giúp phục hồi lỗi tạm thời, nhưng retry quá nhanh hoặc đồng loạt có thể làm dependency đang hồi phục bị quá tải. Test cần xác nhận:

- Chỉ retry loại lỗi có thể tạm thời.
- Có số lần retry hoặc deadline tổng.
- Khoảng chờ tăng dần theo exponential backoff và có giới hạn tối đa.
- Có jitter để nhiều instance không retry cùng thời điểm.
- Không giữ lock trong lúc ngủ/chờ retry.
- Không retry thao tác không idempotent nếu chưa có idempotency key hoặc cơ chế deduplication.
- Sau khi hết ngân sách, component vẫn `NOT_READY` hoặc trả lỗi rõ ràng.

Ví dụ helper retry đơn giản với deadline:

```java
public void connectWithRetry(Duration totalBudget) throws Exception {
    long deadline = System.nanoTime() + totalBudget.toNanos();
    long delayMillis = 100;
    Exception lastFailure = null;

    while (System.nanoTime() - deadline < 0) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Reconnect interrupted");
        }

        try {
            dependency.connectAndValidate();
            return;
        } catch (TransientDependencyException e) {
            lastFailure = e;
        }

        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            break;
        }

        long jitteredMillis = addJitter(delayMillis);
        long sleepNanos = Math.min(
                TimeUnit.MILLISECONDS.toNanos(jitteredMillis),
                remainingNanos);
        TimeUnit.NANOSECONDS.sleep(sleepNanos);
        delayMillis = Math.min(delayMillis * 2, 2000);
    }

    throw new DependencyUnavailableException(
            "Dependency did not become ready before deadline", lastFailure);
}
```

`dependency`, `TransientDependencyException`, `DependencyUnavailableException` và `addJitter()` là thành phần minh họa của ứng dụng. Trong production, cần phân loại exception theo client cụ thể, tránh retry lỗi authentication/quyền/schema như lỗi tạm thời, xử lý overflow duration và dành một phần deadline cho health check cuối. Nếu callback bị interrupt, không nuốt interruption.

Trong unit test, inject clock/sleeper hoặc retry policy để kiểm tra số lần thử và khoảng chờ mà không phải sleep thật. Integration test mới kiểm tra timeout thực tế của network client.

## 9. Kiểm thử circuit breaker và bulkhead

Circuit breaker giúp ngừng gọi dependency khi tỷ lệ lỗi vượt ngưỡng; sau một khoảng chờ, nó cho phép một số request thử lại ở trạng thái half-open. Bulkhead giới hạn số request đồng thời để một dependency chậm không chiếm hết thread hoặc connection của ứng dụng.

Với CRaC, cần kiểm tra trạng thái breaker được khôi phục có còn phù hợp không:

- Breaker `OPEN` trước checkpoint có thể vẫn mở sau restore dù dependency đã hồi phục.
- Breaker `CLOSED` trong ảnh có thể không phản ánh outage bắt đầu khi process tạm dừng.
- Half-open probe đang chờ trước checkpoint không nên được coi là vẫn đang chạy sau restore.
- Semaphore/permit trong heap có thể giữ số lượng đang sử dụng cũ nếu request bị ngắt ở thời điểm checkpoint.

Sau restore, tùy thư viện và policy, có thể reset breaker, chuyển về trạng thái cần probe hoặc để breaker tự kiểm tra lại. Không reset mù quáng nếu breaker được dùng để bảo vệ dependency đang quá tải; cần có probe giới hạn và jitter để tránh mọi instance cùng mở traffic.

Test nên tạo outage đủ dài để breaker mở, checkpoint, phục hồi dependency và restore; xác nhận hệ thống không tạo một đợt request dồn dập. Test thêm trường hợp dependency vẫn lỗi sau restore để bảo đảm breaker tiếp tục bảo vệ ứng dụng.

## 10. Kiểm thử connection pool và stale connection

Connection pool là một trong các resource dễ phát sinh lỗi sau restore. Connection có thể bị server đóng, firewall idle timeout, failover hoặc credential rotation trong khi ứng dụng tạm dừng.

Các kịch bản nên kiểm tra:

- Server đóng toàn bộ connection trong lúc process checkpoint.
- Pool chứa connection idle đã stale trước khi checkpoint.
- Connection đang được borrow khi `beforeCheckpoint` bắt đầu.
- Pool đóng thành công nhưng checkpoint bị abort.
- Pool mới được tạo sau restore nhưng database chưa sẵn sàng.
- Database sẵn sàng nhưng credential cũ bị từ chối.
- Pool validation query chậm hoặc timeout.

Kiểm tra rằng:

- Ứng dụng dừng nhận database work mới trước khi drain.
- Connection đang mượn được trả hoặc transaction được rollback trong deadline.
- Pool/client cũ được đóng bằng API phù hợp.
- Sau restore, pool mới dùng endpoint và credential hiện hành.
- Validation thất bại thì pool không được công bố là sẵn sàng.
- Pool cũ không bị dùng đồng thời sau khi pool mới được publish.

Không chỉ gọi `DataSource.getConnection()` một lần để chứng minh pool khỏe. Nên chạy một truy vấn read-only phù hợp và xác nhận connection thực sự hoạt động. Với test nghiệp vụ, dùng transaction/dữ liệu test có thể rollback hoặc cleanup rõ ràng.

## 11. Kiểm thử DNS, service discovery và endpoint đổi

Dependency có thể chuyển IP hoặc instance sau checkpoint. Test cần tách lỗi DNS khỏi lỗi TCP:

1. Cấu hình hostname test trỏ tới server A.
2. Chạy ứng dụng, xác nhận client kết nối A và tạo checkpoint.
3. Thay bản ghi DNS/service registry để hostname trỏ tới server B.
4. Dừng hoặc chặn A.
5. Restore ứng dụng.
6. Xác nhận client phân giải lại hostname theo cache policy và tạo connection mới tới B.
7. Xác nhận request thực tế tới B, không chỉ xác nhận lookup trả IP mới.

Thêm các trường hợp DNS tạm thời không phân giải được, trả nhiều IP, negative cache, resolver chậm và endpoint B chưa healthy. Nếu client có DNS cache riêng, phải kiểm tra cache đó thay vì chỉ dùng `dig` từ shell.

## 12. Kiểm thử message broker và consumer

Consumer có thể mất session/group membership trong thời gian checkpoint. Broker vẫn tiếp tục quản lý message, offset, acknowledgement và visibility timeout.

Các kịch bản cần có:

- Broker chưa sẵn sàng khi `afterRestore` chạy.
- Connection/channel/session cũ bị đóng trong thời gian checkpoint.
- Kafka consumer phải rejoin group và nhận partition assignment mới.
- RabbitMQ delivery chưa ack được redeliver sau khi channel đóng.
- SQS visibility timeout hết và message được giao lại.
- Handler bị ngắt sau database commit nhưng trước ack.
- Ack/offset commit đã hoàn tất trước khi process checkpoint.

Kiểm tra ứng dụng dừng nhận message mới, drain handler và chỉ ack/commit sau khi business side effect bền vững. Dùng inbox/idempotency để message redelivery không lặp nghiệp vụ. Sau restore, tạo consumer/session/channel mới; không tái sử dụng delivery tag, receipt handle hoặc assignment cũ.

## 13. Kiểm thử secret manager và credential refresh

Secret manager có thể chậm hoặc unavailable đúng lúc `afterRestore` cần lấy credential mới. Token trong heap có thể đã hết hạn trong thời gian checkpoint.

Test nên bao gồm:

- Secret manager phản hồi chậm hơn connect/read timeout.
- Secret manager trả 503 rồi hồi phục trong retry window.
- IAM/workload identity bị từ chối.
- Secret version đã đổi; credential cũ bị thu hồi.
- Token mới lấy được nhưng sắp hết hạn.
- Secret provider cache version cũ.
- TLS certificate/trust store của secret endpoint đã đổi.

Ứng dụng chỉ tạo/công bố pool mới sau khi có credential hợp lệ và connection validation thành công. Nếu không thể lấy secret trong deadline, giữ readiness ở `NOT_READY`; không fallback sang credential đã bị thu hồi. Không ghi giá trị secret vào log hoặc test output.

## 14. Kiểm thử lỗi trong callback `beforeCheckpoint` và `afterRestore`

Hai callback có trách nhiệm khác nhau:

| Callback | Mục tiêu | Lỗi cần mô phỏng |
| --- | --- | --- |
| `beforeCheckpoint` | Quiesce, drain và đưa resource về trạng thái có thể checkpoint | Worker không dừng, transaction không hoàn tất, pool không đóng, dependency chậm khi flush. |
| `afterRestore` | Tạo lại/kiểm tra resource và phục hồi hoạt động | DNS/secret/database/broker chưa sẵn sàng, connect timeout, TLS/authentication fail. |

`beforeCheckpoint` cần báo lỗi nếu không thể đưa resource về trạng thái an toàn trong deadline. Không tiếp tục checkpoint với transaction hoặc tài nguyên đang ở trạng thái không xác định chỉ để tiết kiệm thời gian.

`afterRestore` cần xử lý dependency chưa sẵn sàng theo policy. Có thể retry trong cửa sổ cho phép; nếu vẫn thất bại, báo callback failure hoặc giữ ứng dụng `NOT_READY` để orchestration xử lý. Không publish readiness thành công trước khi resource bắt buộc hoạt động.

Nếu checkpoint bị abort sau khi callback đã dừng resource, process ban đầu có thể tiếp tục mà không chạy `afterRestore`. Cần test rollback/resume riêng cho đường checkpoint failure. Không dùng `afterRestore` như callback rollback.

## 15. Ví dụ Resource kiểm tra dependency sau restore

Ví dụ dưới đây dùng abstraction để minh họa readiness gate, retry có giới hạn và health validation:

```java
import org.crac.Context;
import org.crac.Resource;

import java.time.Duration;

public final class DependencyResource implements Resource {
    private final DependencyClient client;
    private final ReadinessGate readiness;

    public DependencyResource(
            DependencyClient client,
            ReadinessGate readiness) {
        this.client = client;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        client.stopAcceptingWork();
        client.awaitInFlightWithTimeout(Duration.ofSeconds(15));
        client.closeConnections();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        client.reconnectWithRetry(Duration.ofSeconds(30));
        client.validateHealth();
        readiness.acceptTraffic();
    }
}
```

`DependencyClient` và `ReadinessGate` là abstraction của ứng dụng. Các method drain, reconnect và health check phải có timeout; retry cần phân loại lỗi và deadline tổng. Nếu dependency này chỉ phục vụ một tính năng tùy chọn, readiness policy có thể cho phép degraded mode thay vì chặn toàn bộ instance.

Trong production, nên có coordinator quản lý nhiều dependency theo thứ tự: refresh DNS/secret, tạo network/database client, kết nối broker, start consumer/scheduler và cuối cùng mới mở traffic. Không giữ application lock trong lúc gọi network hoặc chờ retry.

## 16. Unit test cho retry và readiness

Unit test có thể dùng fake dependency để kiểm tra trạng thái mà không cần network thật:

```java
class FakeDependency implements DependencyClient {
    private int attempts;
    private final int failAttempts;

    FakeDependency(int failAttempts) {
        this.failAttempts = failAttempts;
    }

    @Override
    public void connectAndValidate() throws TransientDependencyException {
        attempts++;
        if (attempts <= failAttempts) {
            throw new TransientDependencyException("not ready yet");
        }
    }

    int attempts() {
        return attempts;
    }
}
```

Ví dụ JUnit 5 ở mức khái niệm:

```java
@Test
void becomesReadyWhenDependencyRecoversWithinBudget() {
    FakeDependency dependency = new FakeDependency(2);
    FakeReadinessGate readiness = new FakeReadinessGate();

    DependencyRecovery recovery = new DependencyRecovery(
            dependency,
            readiness,
            testRetryPolicy());

    recovery.reconnect();

    assertEquals(3, dependency.attempts());
    assertTrue(readiness.isAcceptingTraffic());
}

@Test
void remainsNotReadyWhenDependencyNeverRecovers() {
    FakeDependency dependency = new FakeDependency(Integer.MAX_VALUE);
    FakeReadinessGate readiness = new FakeReadinessGate();

    assertThrows(DependencyUnavailableException.class,
            () -> new DependencyRecovery(
                    dependency, readiness, shortTestRetryPolicy())
                    .reconnect());

    assertFalse(readiness.isAcceptingTraffic());
}
```

Tên class và helper trong ví dụ là thành phần test minh họa. Nên inject `Clock`, retry policy và sleeper để unit test không phải chờ thời gian thật. Unit test xác nhận logic; nó không thay thế test socket, driver, broker hoặc CRaC runtime thật.

## 17. Component test bằng mock server và proxy

Với HTTP client, dùng WireMock hoặc mock server để tạo:

- Response 200 nhanh.
- Response 503/429.
- Response delay lớn hơn read timeout.
- Connection close trước khi response hoàn tất.
- Body lỗi schema hoặc content type không hợp lệ.
- Endpoint chỉ bắt đầu trả 200 sau một thời gian chờ.

Với TCP dependency như database/broker, dùng Toxiproxy để:

- Thêm latency và jitter.
- Ngắt kết nối đang mở.
- Tạo timeout hoặc bandwidth thấp.
- Bật lại đường mạng sau một khoảng thời gian.

Test nên điều khiển fault theo tín hiệu thay vì sleep tùy tiện. Ví dụ test bật proxy toxic, xác nhận request thất bại trong deadline, bỏ toxic, rồi xác nhận client reconnect thành công. Với connection pool, xác nhận pool loại bỏ connection hỏng và không tiếp tục trả connection stale.

## 18. Integration test với dependency thật

Testcontainers có thể chạy database và broker thật để kiểm tra driver, pool và protocol. Một bài test tích hợp có thể:

1. Start database/broker container.
2. Start ứng dụng với CRaC-compatible JDK và cấu hình checkpoint riêng.
3. Chạy health check và một nghiệp vụ test.
4. Tạo checkpoint theo quy trình của runtime.
5. Restart dependency hoặc chặn kết nối trong lúc ứng dụng ở trạng thái checkpoint.
6. Restore ứng dụng.
7. Xác nhận callback reconnect và readiness behavior.
8. Bật lại dependency và kiểm tra ứng dụng tự phục hồi trong retry window.
9. Xác nhận dữ liệu nghiệp vụ, transaction và message không bị duplicate/mất.

Nếu Testcontainers quản lý vòng đời dependency, test có thể stop/start container theo API của phiên bản thư viện. Khi muốn mô phỏng network partition mà không stop server, đặt Toxiproxy giữa ứng dụng và container. Không dùng một database container dùng chung cho nhiều test song song nếu test có thể làm thay đổi trạng thái hoặc dữ liệu lẫn nhau.

## 19. Kiểm thử end-to-end với CRaC thật

Unit test gọi trực tiếp `beforeCheckpoint()` và `afterRestore()` hữu ích để kiểm tra logic callback, nhưng không xác nhận CRIU/JVM có tạo hoặc khôi phục được process image. Cần ít nhất một bộ integration test dùng đúng JDK CRaC, kernel, container runtime và filesystem dự kiến.

Quy trình tổng thể:

1. Khởi chạy dependency trong trạng thái healthy.
2. Khởi chạy ứng dụng và xác nhận readiness.
3. Gửi workload đại diện, sau đó yêu cầu checkpoint.
4. Xác nhận `beforeCheckpoint` đã drain và đóng tài nguyên.
5. Trong khi process được checkpoint, làm dependency chậm, stop/restart, đổi endpoint hoặc rotate credential.
6. Restore ứng dụng từ checkpoint.
7. Xác nhận process restore, callback sau restore và resource reconnect.
8. Đo thời gian từ restore tới readiness.
9. Gửi request/message và xác nhận kết quả nghiệp vụ.
10. Xác nhận log/metric cho biết timeout, retry, dependency recovery và readiness transition.

Chạy từng failure scenario độc lập trước. Sau đó mới kết hợp, ví dụ DNS đổi đồng thời database chậm và secret manager tạm thời unavailable. Nếu test kết hợp thất bại, cần đủ telemetry để biết dependency nào gây lỗi đầu tiên.

## 20. Ma trận test tham khảo

| ID | Dependency/fault | Thời điểm | Kết quả mong đợi |
| --- | --- | --- | --- |
| DEP-01 | HTTP response chậm hơn read timeout | Sau restore | Request timeout trong budget; readiness theo policy. |
| DEP-02 | HTTP 503 rồi hồi phục | `afterRestore` | Retry có backoff; readiness mở khi health check thành công. |
| DEP-03 | TCP reset khi connection đang mở | Trong checkpoint | Pool/client không dùng socket cũ; tạo kết nối mới sau restore. |
| DEP-04 | Database chưa listen | Sau restore | Callback/recovery chờ có giới hạn; instance không nhận traffic sớm. |
| DEP-05 | Database failover và endpoint đổi | Trong checkpoint | DNS/service discovery refresh; pool mới kết nối endpoint hiện hành. |
| DEP-06 | Broker chưa sẵn sàng | Sau restore | Consumer chưa start/nhận message cho tới khi broker và group/queue sẵn sàng. |
| DEP-07 | Message handler không drain | `beforeCheckpoint` | Checkpoint bị từ chối/timeout theo policy; không ack message chưa hoàn tất. |
| DEP-08 | Secret manager timeout | `afterRestore` | Retry bounded; không dùng credential cũ đã hết hạn. |
| DEP-09 | Credential bị thu hồi | Trong checkpoint | Pool mới dùng secret version hiện hành; readiness chỉ mở sau validation. |
| DEP-10 | DNS tạm thời NXDOMAIN | Sau restore | Negative cache policy không giữ lỗi quá lâu; retry theo deadline. |
| DEP-11 | Connection pool cạn | Trước checkpoint và sau restore | Pool acquisition timeout; bulkhead ngăn thread exhaustion. |
| DEP-12 | Circuit breaker còn OPEN | Sau restore | Probe/half-open theo policy; không tạo request storm. |
| DEP-13 | Dependency không bao giờ hồi phục | Sau restore | Hết retry budget; instance giữ `NOT_READY` hoặc fail theo policy. |
| DEP-14 | Checkpoint abort sau khi resource đã stop | Trong checkpoint | Coordinator rollback/resume hoặc giữ `NOT_READY`; không chờ `afterRestore`. |
| DEP-15 | Dependency lỗi lại ngay sau readiness | Sau restore | Circuit breaker, timeout và readiness phản ánh degradation đúng. |

Ma trận nên được điều chỉnh theo dependency thực tế. Không cần chạy tất cả test trên mọi commit; có thể chia unit/component test chạy thường xuyên và CRaC end-to-end test chạy trên pipeline/runtime tương thích.

## 21. Đo lường kết quả test

Để xác định ứng dụng phản ứng đúng, thu thập các mốc thời gian và số liệu:

- Thời gian từ yêu cầu restore đến khi callback `afterRestore` bắt đầu/kết thúc.
- Thời gian lấy secret, phân giải DNS, mở connection và health check.
- Số lần retry, loại exception, backoff và thời gian chờ.
- Connection pool active/idle/pending, số connection bị loại bỏ và lỗi acquisition.
- Consumer state, partition assignment, queue depth và số message đang xử lý.
- Circuit breaker state, bulkhead saturation và số request bị từ chối.
- Readiness/liveness/startup probe result và thời điểm chuyển trạng thái.
- Latency p50/p95/p99, error rate và throughput sau khi traffic mở.
- Thời điểm dependency được bật lại và thời điểm ứng dụng phục hồi.

Gắn các log với checkpoint attempt id và restore attempt id. Không log password, token, private key hoặc payload nhạy cảm. Với metric, dùng label có cardinality thấp; message id, user id và request id nên nằm trong trace/log thay vì label metric.

## 22. Tiêu chí pass/fail

Một test dependency fault chỉ nên pass khi hành vi đáp ứng policy đã định trước. Ví dụ:

**Pass** khi:

- Không có thao tác chờ vô hạn; timeout nằm trong budget.
- Không mở readiness khi dependency bắt buộc chưa healthy.
- Khi dependency hồi phục trong retry window, ứng dụng reconnect và phục vụ được request.
- Khi dependency không hồi phục, ứng dụng giữ `NOT_READY` hoặc fail theo policy mà không tạo restart/retry storm.
- Không dùng stale socket, credential, DNS endpoint hoặc session không hợp lệ.
- Không mất hoặc nhân đôi nghiệp vụ/message trong các cửa sổ commit/ack đã kiểm thử.
- Resource và scheduler không bị start/stop lặp sai khi checkpoint/restore hoặc checkpoint abort.

**Fail** khi:

- Callback treo quá deadline hoặc thread pool bị cạn do blocking.
- Readiness mở trước khi dependency bắt buộc hoạt động.
- Ứng dụng báo healthy chỉ vì process sống.
- Retry vô hạn hoặc retry đồng loạt gây quá tải.
- Dữ liệu/side effect bị mất hoặc duplicate do xử lý transaction/ack sai thứ tự.
- Restore tiếp tục dùng client/session/credential cũ mà không validation.
- Checkpoint abort để lại ứng dụng dừng một phần nhưng vẫn nhận traffic.

Tiêu chí thời gian cụ thể cần dựa trên SLO và môi trường. Không dùng một con số chung cho mọi database, broker hoặc API.

## 23. Các lỗi kiểm thử thường gặp

| Vấn đề trong test | Vì sao kết quả không đáng tin | Cách cải thiện |
| --- | --- | --- |
| Dùng `Thread.sleep()` cố định để chờ dependency | Test phụ thuộc tốc độ máy và dễ flaky | Chờ condition/health check có deadline. |
| Chỉ mock exception trong unit test | Không kiểm tra socket, DNS, TLS, driver hoặc pool behavior | Bổ sung proxy và integration test. |
| Test chỉ kiểm tra JVM restore | Không chứng minh dependency reconnect hoặc readiness đúng | Gửi request/message thật sau restore và kiểm tra side effect. |
| Chỉ kiểm tra readiness endpoint trả 200 | Endpoint có thể không kiểm tra dependency bắt buộc | Thiết kế health indicator theo policy dependency. |
| Liveness phụ thuộc trực tiếp vào database | Database outage có thể tạo restart storm | Phân biệt liveness với readiness và startup probe. |
| Retry không giới hạn trong callback | Restore có thể bị treo vô thời hạn | Deadline tổng, retry cap và fail behavior rõ ràng. |
| Dùng cùng test database cho nhiều test song song | Trạng thái và dữ liệu test ảnh hưởng lẫn nhau | Isolate container/schema/test data. |
| Không kiểm tra lỗi sau business commit trước ack | Không phát hiện duplicate khi broker redelivery | Kiểm thử inbox/idempotency và broker state. |
| Tắt proxy nhưng không xác nhận dependency healthy | Test có thể pass do timing hoặc client dùng cache cũ | Kiểm tra kết nối thật và endpoint/instance nhận request. |
| Không test checkpoint abort | Resource có thể đã stop nhưng process không restore | Tạo failure injection ở giai đoạn preparation/dump và kiểm tra rollback. |

## 24. Checklist kiểm thử

- [ ] Liệt kê dependency bắt buộc và dependency có thể degraded.
- [ ] Phân loại lỗi chậm, refused, reset, timeout, DNS, authentication và overload.
- [ ] Có test trước checkpoint, trong preparation, trong khoảng checkpoint và sau restore.
- [ ] Có fake/stub cho unit test và fault injection ở network layer.
- [ ] Dùng WireMock/mock server cho HTTP delay, 5xx và malformed response.
- [ ] Dùng Toxiproxy hoặc công cụ tương đương cho TCP latency/reset/partition.
- [ ] Dùng Testcontainers hoặc môi trường tương đương cho database/broker thật.
- [ ] Kiểm tra connection pool, stale socket, credential và endpoint refresh.
- [ ] Kiểm tra retry/backoff/jitter, deadline tổng và cancellation.
- [ ] Kiểm tra circuit breaker, bulkhead và connection pool exhaustion.
- [ ] Readiness fail khi dependency bắt buộc chưa sẵn sàng; liveness không gây restart storm.
- [ ] Kiểm tra consumer drain, ack/offset và idempotency nếu có message broker.
- [ ] Kiểm tra checkpoint abort và rollback/resume resource.
- [ ] Chạy ít nhất một CRaC integration test trên runtime/container/kernel mục tiêu.
- [ ] Đo thời gian restore-to-ready, retry, latency và error rate.
- [ ] Không ghi secret hoặc dữ liệu nhạy cảm vào log/test output.

## 25. Kết luận

Dependency chậm, mất kết nối hoặc chưa sẵn sàng là tình huống bình thường trong hệ thống phân tán, đặc biệt khi ứng dụng được restore từ một process image cũ. CRaC không bảo đảm database, broker, DNS, secret manager hay HTTP service giữ nguyên trạng thái trong thời gian checkpoint. Vì vậy, kiểm thử phải bao phủ cả callback, resource và hành vi nghiệp vụ sau restore.

Hãy tạo lỗi có kiểm soát bằng fake, mock server, proxy mạng và dependency thật; kiểm tra timeout ở từng tầng, retry có deadline, circuit breaker, pool/client recreation và readiness. Drain công việc trước checkpoint, không mở traffic trước khi dependency bắt buộc khỏe, và kiểm thử cả trường hợp dependency hồi phục lẫn không hồi phục. Kết hợp unit, component, integration và CRaC end-to-end test sẽ cho thấy ứng dụng có thể phục hồi an toàn khi dịch vụ phụ thuộc chậm hoặc gián đoạn.
