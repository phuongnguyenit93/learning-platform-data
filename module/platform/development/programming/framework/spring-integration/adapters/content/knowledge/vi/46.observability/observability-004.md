# Metrics cho adapter và channel trong Spring Integration

## 1. Vì sao phải đo metrics tại adapter và MessageChannel?

Một ứng dụng Spring Integration có thể nhận dữ liệu từ **file/SFTP**, **HTTP**, **JMS**, **AMQP**, **Kafka** hay **database**, sau đó dùng **MessageChannel**, filter, router, transformer và handler để gửi tới hệ thống đích. Luồng hoạt động đúng về mặt code nhưng vẫn có thể gây sự cố: poller không lấy file, queue đầy, consumer tụt lag, outbound HTTP timeout, broker redeliver, database commit chậm hoặc connector cứ retry cùng một bản ghi.

**Metrics** biến những hiện tượng đó thành tín hiệu định lượng có thể theo dõi theo thời gian: **tốc độ, độ trễ, tỷ lệ lỗi, mức tồn đọng, kết quả retry và khả năng kết nối**. Trong chương **Observability** của module **SPRING_INTEGRATION_ADAPTERS**, mục tiêu là quan sát luồng tích hợp qua inbound/outbound adapter, gateway, poller và MessageChannel, đồng thời kiểm soát **hợp đồng message, lỗi và vòng đời kết nối**.

Ví dụ, một dashboard chỉ hiển thị “đã gửi 2.000 messages” chưa trả lời được:

- Có bao nhiêu message **được xử lý thành công** và bao nhiêu message bị filter/reject?
- Số lần gửi là **attempts**, hay số business event duy nhất?
- Có record đang **chờ** trong QueueChannel hoặc broker không?
- Một HTTP outbound gateway nhận **2xx từ remote** hay chỉ thực hiện send tại channel?
- Thời gian trễ tính **từ file xuất hiện tới khi xác nhận xử lý xong**, hay chỉ thời gian ở một handler?
- Nếu Kafka consumer xử lý lỗi rồi retry, counter tăng thêm bao nhiêu lần?

### Mục tiêu sau bài học

1. Phân biệt metrics của **channel, endpoint/handler, adapter, poller** và hệ thống ngoài.
2. Dùng **Micrometer**, Spring Boot Actuator và khả năng quản lý/quan sát của Spring Integration một cách phù hợp với phiên bản thư viện.
3. Đặt tên endpoint/metric và chọn **tag có cardinality thấp**, tránh đưa message ID hoặc tên file vào nhãn.
4. Thiết kế **SLI/SLO** đo việc xử lý message thành công, độ trễ và backlog thay vì chỉ xem CPU hay HTTP 200.
5. Xây dashboard, cảnh báo và runbook cho File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC/database.
6. Kiểm thử metric, phân tích metric bị thiếu/sai và kết hợp metrics với log, trace, message history.

> **Giới hạn:** Tên meter, tag và tùy chọn instrumentation tích hợp sẵn của Spring Integration thay đổi theo phiên bản và cấu hình quản lý/observation. Các metric ứng dụng trong bài có prefix `app.integration.*` là **quy ước minh họa do ta chủ động tạo**, không phải cam kết chúng luôn được Spring Integration xuất tự động.

## 2. Metrics đứng ở đâu trong bộ ba observability?

| Loại tín hiệu | Trả lời | Ví dụ trong integration flow |
|---|---|---|
| **Metrics** | Bao nhiêu? Bao lâu? Tần suất lỗi? | Messages/s, p95 handler latency, queue depth, redelivery rate |
| **Structured logs** | Sự kiện cụ thể nào đã xảy ra? | `event=HTTP_TIMEOUT`, `correlation_ref=...`, status code, target |
| **Distributed traces** | Request/message đi qua service nào và từng span tốn bao lâu? | HTTP → IntegrationFlow → Kafka producer → consumer service |
| **Message history** | Message đi qua những thành phần Spring Integration nào khi history được bật? | Transformer, router, service activator, adapter |
| **Audit/business events** | Hệ thống đã thực sự chấp nhận hoặc thay đổi nghiệp vụ nào? | Order accepted/paid, file processed, transaction committed |

Metrics cho biết **mẫu hình theo thời gian**, không nhất thiết cho biết message cụ thể bị lỗi ở đâu. Vì thế nên kết hợp:

- **Counter/gauge/timer** để phát hiện sự cố sớm.
- **Correlation ID và trace context** để tìm message/transaction bị ảnh hưởng.
- **MessageHistory** để xem đường đi trong một process, nếu history đang bật.
- **Source/target audit và broker metadata** để xác nhận tác dụng thực sự tại hệ thống ngoài.

Một histogram p99 tăng bất thường có thể cho biết luồng xử lý chậm, nhưng không chứng minh nguyên nhân ở SFTP, CPU, broker hay database. Cần drill down bằng các tín hiệu khác.

## 3. Kiến trúc đo lường luồng adapter–channel

~~~mermaid
flowchart LR
    SRC[File / SFTP / HTTP / JMS / AMQP / Kafka / DB] --> IN[Inbound Adapter hoặc Gateway]
    IN --> CH1[Input MessageChannel]
    CH1 --> PROC[Filter / Router / Transformer / Handler]
    PROC --> CH2[Output MessageChannel]
    CH2 --> OUT[Outbound Adapter hoặc Gateway]
    OUT --> DST[Remote System]
    IN -. polling / input metrics .-> REG[Micrometer MeterRegistry]
    CH1 -. channel metrics .-> REG
    PROC -. handler metrics .-> REG
    CH2 -. send / queue metrics .-> REG
    OUT -. outbound attempts .-> REG
    SRC -. source / broker telemetry .-> REG
    DST -. acknowledgement / outcome .-> REG
    REG --> EXP[Actuator / Metrics Exporter]
    EXP --> OBS[Prometheus / Monitoring Backend]
    OBS --> DASH[Dashboard / Alert / On-call]
~~~

Sơ đồ minh họa **nguồn dữ liệu đo**, không có nghĩa Spring Integration tự thu mọi metric ở broker hoặc remote service. Telemetry của Kafka, RabbitMQ, JMS provider, database, SFTP server và HTTP target thường cần **instrumentation/client metrics hoặc exporter riêng**.

### 3.1. Bốn ranh giới cần phân biệt

1. **Inbound acceptance:** adapter đã lấy hoặc nhận message vào ứng dụng chưa?
2. **Channel delivery:** channel đã chấp nhận dispatch/enqueue message cho downstream chưa?
3. **Processing outcome:** handler đã xử lý theo đúng hợp đồng nghiệp vụ chưa?
4. **External confirmation:** hệ thống đích đã ack/commit/ghi file/HTTP trả response thành công chưa?

Nếu trộn bốn điểm đo thành một counter `success`, dashboard dễ báo xanh ngay cả khi message đã bị mất sau một gateway timeout hoặc broker publish chưa được confirm.

## 4. Từ vựng metrics: Counter, Timer, Gauge, Distribution

| Loại meter | Phù hợp cho | Điểm cần lưu ý |
|---|---|---|
| **Counter** | Số message nhận, số attempt, số retry, số reject/error | Giá trị tích lũy tăng; muốn biết tốc độ thì tính rate theo cửa sổ thời gian |
| **Timer** | Thời gian handler, HTTP call, DB processing hoặc toàn flow | Cần xác định rõ **bắt đầu/kết thúc**; thường cung cấp count và tổng thời gian, histogram nếu cấu hình |
| **Gauge** | Queue depth, in-flight requests, connection pool active, oldest backlog age | Giá trị tại lúc lấy mẫu; một gauge không phải lịch sử mọi lần thay đổi |
| **Distribution summary** | Kích thước file, số byte message, batch size | Không thay thế timer; phân phối và bucket cần cấu hình phù hợp |
| **Long task timer** | Tác vụ kéo dài cần quan sát khi chưa kết thúc | Cân nhắc nếu polling/transfer/job có vòng đời dài |

### 4.1. Một cái tên “success” phải có hợp đồng

Ví dụ định nghĩa:

- `received_total`: inbound adapter tạo một Spring Message từ nguồn.
- `accepted_total`: message qua validation/filter và được handler chấp nhận.
- `delivery_attempt_total`: số lần gọi outbound (bao gồm retry).
- `delivery_confirmed_total`: target đã xác nhận theo semantics tương ứng.
- `failed_total`: lỗi kết thúc sau policy retry và đưa DLQ/failed state.
- `inflight`: số message đang xử lý ở một ranh giới đã xác định.

**Không đồng nhất** một send attempt với một business event duy nhất: cùng message có thể được gửi lại nhiều lần sau timeout hoặc redelivery.

### 4.2. Đơn vị đo và timestamp

Timer trong Micrometer được chuyển đổi đơn vị khi xuất ở backend; với Prometheus, tên thường được chuẩn hóa và thời gian hay xuất theo giây. Khi hiển thị, cần thống nhất **ms/s** trên panel. Không so trực tiếp một gauge tính milliseconds với histogram tính seconds rồi suy p95.

## 5. Metrics ở MessageChannel: cùng tên nhưng semantics khác nhau

### 5.1. DirectChannel

`DirectChannel` thường dispatch đồng bộ trong thread của sender đến subscriber. Thời gian thực hiện `send` có thể bao gồm phần xử lý downstream tùy loại channel/handler và instrumentation. Vì vậy **không gán nhãn “network latency”** cho timer send của DirectChannel.

Nên quan sát:

- Số send attempts và failures.
- Thời gian dispatch/send theo định nghĩa meter thực tế.
- Handler latency riêng tại các endpoint tốn tài nguyên.
- Exception/rejection, kể cả không có subscriber.

### 5.2. ExecutorChannel

`ExecutorChannel` chuyển dispatch qua executor. Một phép send có thể được chấp nhận rất nhanh nhưng task **đợi trong executor queue** lâu trước khi handler chạy. Do đó:

- Channel send latency thấp **không bảo đảm** xử lý end-to-end nhanh.
- Cần executor queue size, active threads, rejection count, task wait time.
- Đếm in-flight ở đúng thời điểm; nếu handler thất bại bất đồng bộ, đừng coi send thành công là business success.
- Kiểm thử propagation của tracing context và MDC vì thread thay đổi.

### 5.3. QueueChannel

`QueueChannel` lưu message để consumer/poller lấy sau; có thể cần đo:

| Metric | Ý nghĩa |
|---|---|
| **Queue depth** | Số message còn trong queue tại thời điểm lấy mẫu |
| **Oldest age** | Message cũ nhất đã chờ bao lâu |
| **Enqueue rate** | Tốc độ đưa message vào queue |
| **Dequeue/consumption rate** | Tốc độ lấy và xử lý tiếp |
| **Capacity usage** | Mức sử dụng so với dung lượng cấu hình |
| **Rejected/blocked sends** | Send timeout/capacity exhausted tùy loại channel |

Queue depth **có thể bằng 0** khi consumer xử lý nhanh nhưng remote outbound đang chậm; hoặc queue rất lớn vì downstream bị nghẽn. Để chẩn đoán nguyên nhân phải so ingress, egress, in-flight và lỗi.

### 5.4. PublishSubscribeChannel

Một message có thể fan-out tới nhiều subscriber; metric số send ở channel thường khác tổng số deliveries tới từng subscriber. Nếu một subscriber lỗi và một subscriber thành công, cần theo dõi **per-branch outcome** và cấu hình error handling. Không kết luận một business event đã hoàn tất mọi nhánh chỉ vì channel chấp nhận gửi.

### 5.5. Bảng so sánh

| Channel | Tín hiệu nên ưu tiên | Điều không được suy ra |
|---|---|---|
| Direct | Dispatch/send count, latency, handler timer | Remote network ACK |
| Executor | Executor wait/queue, handler timer, task rejection | Send được accept = handler đã chạy |
| Queue | Depth, oldest age, enqueue/dequeue, capacity | Depth 0 = business completed |
| Publish-subscribe | Per-subscriber outcome, fan-out failures | Một send = mọi subscriber thành công |

## 6. Metrics tại endpoint và message handler

Endpoint/handler là nơi thực hiện hành động như validate, transform, route, lưu database hoặc gọi HTTP. Những chỉ số quan trọng:

1. **Handler invocation/attempt count:** số lần xử lý được bắt đầu.
2. **Processing duration:** thời gian thực thi logic trong handler.
3. **Success/failure count:** kết quả theo policy; phân biệt exception được retry với lỗi cuối cùng.
4. **Discard/reject count:** filter bỏ message có lý do gì, chuyển đến discard channel hay không.
5. **Payload/batch size:** kích thước hoặc số phần tử được xử lý.
6. **Concurrency/in-flight:** có bao nhiêu handler executions đang hoạt động.
7. **Timeout/retry:** task bị timeout, retry do lỗi mạng hoặc từ chối bởi target.

### 6.1. Handler time khác flow time

Nếu message chờ trong `QueueChannel` 30 giây và handler chạy 20 ms, dashboard handler timer sẽ rất tốt nhưng người dùng vẫn gặp **latency 30 giây**. Cần SLI end-to-end đo từ mốc **accepted/received** tới mốc **completed/confirmed** theo hợp đồng.

### 6.2. Filter, router và aggregator

- **Filter:** counters `accepted`, `rejected` và các nhóm `reason_code` có số giá trị hữu hạn; không log raw payload.
- **Router:** counters cho destination dạng nhóm cố định, đo nhánh không có mapping và lỗi router.
- **Splitter:** số batch đầu vào, số item đầu ra, batch size distribution, item failures.
- **Aggregator:** group count, outstanding groups, completion latency, timeout/expiry, group storage capacity.
- **Resequencer:** số nhóm đang đợi, độ trễ hoàn thiện thứ tự, message bị timeout.

**Lưu ý cardinality:** đừng dùng `correlationId` hoặc `batchId` làm metric tag cho aggregator; đó là nhãn giá trị gần như vô hạn. Dùng log/trace cho ID cụ thể, metrics chỉ theo flow, handler và result.

## 7. Metrics cho poller và inbound channel adapter

Poller có thể **chạy thành công nhưng không thấy dữ liệu**. Nếu chỉ đếm số message, bạn không biết đang “không có gì để làm” hay scheduler đã dừng.

### 7.1. Bốn trạng thái poll cần tách

| Trạng thái | Ý nghĩa | Quan sát phù hợp |
|---|---|---|
| **Poll executed, empty** | Poller chạy, source không có item mới hoặc bị filter | Poll count, empty count, source scan result |
| **Poll executed, received** | Poller tạo được message | Poll count, received count và handler flow |
| **Poll executed, failed** | Lỗi connect/read/filter/conversion | Error count, exception class giới hạn, latency |
| **Poll did not execute** | Scheduler bị ngừng, lock, executor nghẽn hoặc app down | Last successful tick, expected cadence, scheduler health |

### 7.2. Những mốc thời gian hữu ích

- `last_poll_at`: lần poll được kích hoạt gần nhất (nếu thu thập bằng thiết kế ứng dụng).
- `last_nonempty_poll_at`: lần cuối có dữ liệu thực sự.
- `source_oldest_item_age`: tuổi file/record chưa được lấy.
- `processing_lag`: khoảng chênh từ source event time tới lúc được chấp nhận hoặc hoàn tất.
- `poll_duration`: thời gian đọc/scan của poll.

Một cảnh báo “không có message 10 phút” có thể sai trong hệ thống nhận file mỗi đêm. Phải so **lịch nguồn phát, poll cadence, SLA của dữ liệu và business calendar**.

### 7.3. Throttling, maxMessagesPerPoll và backpressure

Poller có thể được cấu hình số lượng message tối đa trên mỗi chu kỳ, lịch chạy và transaction. Khi nguồn tạo dữ liệu nhanh hơn tốc độ poll/handle, backlog sẽ tăng dù không có exception. Cần đo **tốc độ vào, tốc độ ra, queue age và capacity** thay vì chỉ tăng tần suất poll vô hạn, vì làm vậy có thể quá tải target.

## 8. Metrics cho outbound adapter và gateway

Outbound adapter/gateway là ranh giới từ Spring Integration sang hệ thống ngoài. Phải phân biệt:

- **Attempt:** ứng dụng bắt đầu gửi/call.
- **Transport accepted:** thư viện client/adapter chấp nhận hoặc queue request.
- **Remote ACK/response:** đối tác/broker phản hồi theo protocol.
- **Business committed:** hành động nghiệp vụ đã bền vững ở target theo hợp đồng.

Ví dụ với Kafka, callback producer có thể xác nhận broker nhận record theo cấu hình `acks`; điều đó **không** có nghĩa downstream consumer đã xử lý xong. Với HTTP, response 200 có thể là “accepted async” chứ không chứng minh nghiệp vụ cuối cùng đã commit.

### 8.1. Adapter one-way

One-way outbound thường không trả một reply business trực tiếp cho flow. Số message được dispatch vào adapter không đủ để biết kết quả publish/upload thật sự. Cần thu thập **callback/confirm/error channel** hoặc telemetry từ client/broker khi khả dụng.

### 8.2. Outbound gateway request/reply

Nên đo:

| Metric | Ý nghĩa |
|---|---|
| Request attempts | Số lần gửi thực sự, gồm retry |
| Request duration | Thời gian chờ reply/timeout theo client |
| Response class | 2xx/4xx/5xx, hoặc status domain |
| Timeouts | Số call không có kết quả chắc chắn |
| Retry attempts | Lần thử bổ sung, theo nhóm nguyên nhân |
| Circuit breaker state | Trạng thái open/half-open/closed nếu được dùng |
| Confirmed business outcome | Kết quả thật theo hợp đồng, khi có thể kiểm tra |

Nếu timeout xảy ra **sau khi remote commit**, retry không có idempotency có thể tạo bản ghi trùng. Metrics retry là cảnh báo, không thay thế **idempotency key, trạng thái remote và reconciliation**.

## 9. Micrometer trong hệ sinh thái Spring Integration

**Micrometer** cung cấp `MeterRegistry` và các loại meter như `Counter`, `Timer`, `Gauge`. Spring Boot Actuator có thể cho phép quan sát meter và xuất dữ liệu qua registry phù hợp. Spring Integration có các cơ chế quản lý/metrics/observation dành cho channel và handler, nhưng cách kích hoạt và bộ metric thực tế phụ thuộc version.

### 9.1. Thành phần cần phân biệt

| Thành phần | Vai trò |
|---|---|
| `MeterRegistry` | Nơi đăng ký/ghi meter của ứng dụng |
| `Counter`, `Timer`, `Gauge` | Các phép đo |
| Spring Integration management/instrumentation | Tạo hoặc đăng ký đo lường cho channel, handler, poller tùy tính năng/version |
| `ObservationRegistry` | Ngữ cảnh cho Micrometer Observation, có thể kết nối metrics và tracing |
| Spring Boot Actuator | Endpoint quản trị/quan sát như `/actuator/metrics` |
| Registry/exporter | Prometheus hoặc backend tương ứng |
| Logging/tracing | Bổ sung ngữ cảnh điều tra từng request/message |

**Quan trọng:** thêm Micrometer registry **không bảo đảm** mọi adapter File/SFTP/JMS/Kafka/JDBC tự có cùng bộ meter, tag và thời gian đo. Một số metric tới từ client hoặc connector, một số phải xây riêng theo nhu cầu nghiệp vụ.

### 9.2. Quản lý Spring Integration

Ở những phiên bản Spring Integration hỗ trợ, cơ chế quản lý có thể được kích hoạt/cấu hình qua `@EnableIntegrationManagement` hoặc cấu hình management tương ứng; các thuộc tính/cơ chế Observation cần kiểm tra theo thế hệ thư viện.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationManagement;

@Configuration
@EnableIntegration
@EnableIntegrationManagement
public class IntegrationManagementConfig {
    // Kiểm tra meter/observation thực tế với version đang sử dụng.
}
~~~

Đây là **ví dụ về hướng enablement**, không phải bảo đảm đầy đủ meter trong mọi Spring Boot application. Trước khi cấu hình production, kiểm tra ứng dụng đã có integration-management bean do auto-configuration chưa, tránh tạo cấu hình chồng hoặc hiểu sai default.

### 9.3. Không hardcode meter name theo trí nhớ

Tùy phiên bản, channel/handler metrics có thể được xuất với những tên và tags khác nhau hoặc theo cơ chế metrics/observations. Cách an toàn:

1. Bật management/observation phù hợp.
2. Chạy một integration flow đại diện.
3. Liệt kê meter thực sự có trong registry/Actuator.
4. Ghi lại **meter name, base unit, type, tags và điều kiện tăng**.
5. Dựa trên danh sách đã xác minh để xây dashboard/alert và lock vào integration test.

Không kết luận rằng một meter có tên `spring.integration.*` nhất định sẽ luôn tồn tại sau mọi lần nâng dependency.

## 10. Ví dụ Spring Boot: dependency và Actuator

Với một ứng dụng Spring Boot có Spring Integration, bạn có thể bổ sung Actuator và registry theo lựa chọn. Ví dụ phần dependency Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Quản lý version bằng BOM/parent tương thích với Spring Boot đang sử dụng; không tự chọn version riêng ngẫu nhiên cho Micrometer/Spring Integration.

### 10.1. Ví dụ cấu hình Actuator

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: integration-adapters-demo
~~~

**Cảnh báo bảo mật:** `/actuator/metrics` và `/actuator/prometheus` có thể tiết lộ chi tiết vận hành. Chỉ mở endpoint cho hệ thống monitoring qua phân quyền và network control thích hợp; không triển khai ví dụ exposure này lên Internet công khai.

### 10.2. Khám phá meter thực tế

Trong môi trường dev được phép truy cập:

~~~bash
# Kiểm tra endpoint metrics đã được bật và bảo vệ:
curl -s http://localhost:8080/actuator/metrics

# Chọn một meter name thực sự có trong kết quả:
curl -s http://localhost:8080/actuator/metrics/METER_NAME

# Với registry Prometheus đã cấu hình:
curl -s http://localhost:8080/actuator/prometheus
~~~

`METER_NAME` là placeholder, **không phải tên meter mặc định**. Hãy kích hoạt vài lần gửi nhận message trước khi khám phá; nhiều meter chỉ xuất hiện sau khi thành phần thực sự được sử dụng hoặc khi registry được cấu hình.

## 11. Ví dụ Java DSL: đặt tên endpoint và quan sát luồng

Các ID ổn định giúp kiểm tra metrics và trace theo thành phần, tránh lẫn các endpoint tự sinh tên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderFlowConfig {

    @Bean
    IntegrationFlow ordersFlow() {
        return IntegrationFlow.from("ordersInput")
                .filter(String.class,
                        text -> !text.isBlank(),
                        endpoint -> endpoint.id("validateOrderText"))
                .transform(String.class,
                        String::trim,
                        endpoint -> endpoint.id("normalizeOrderText"))
                .channel("ordersValidated")
                .handle(message -> {
                    // Xử lý message đã chuẩn hóa.
                }, endpoint -> endpoint.id("ordersSink"))
                .get();
    }
}
~~~

Điểm học tập: `validateOrderText`, `normalizeOrderText`, `ordersSink` và các channel có tên rõ ràng giúp quan sát. **Không suy ra tên meter chính xác** chỉ từ ID này: chúng là identity logic cho flow, còn meter naming do instrumentation và phiên bản quyết định.

### 11.1. Kiểm chứng meter theo sự kiện cụ thể

Thử gửi một message hợp lệ rồi một message rỗng qua input:

- Message hợp lệ đi qua filter → transform → handler.
- Message rỗng bị filter reject → không tới handler.
- Đọc meter/filter counters hoặc custom counters (nếu đã được tạo) để xác minh sự khác biệt.
- Kiểm tra **số message hợp lệ** và **số attempts**, không chỉ “có meter”.

Không biến một test gửi message qua channel thành bằng chứng remote Kafka/JMS/HTTP đã hoàn tất vì luồng này chưa có outbound protocol.

## 12. Chủ động thêm metric nghiệp vụ bằng MeterRegistry

Built-in metrics giúp xem framework components; nhiều dự án vẫn cần những metric mang ý nghĩa riêng như “order đã được target xác nhận” hoặc “batch bị loại vì schema”. Có thể dùng Micrometer trực tiếp.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderFlowMetrics {
    private final MeterRegistry registry;
    private final Timer processingTimer;

    public OrderFlowMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.processingTimer = Timer.builder(
                "app.integration.processing.duration")
                .description("Duration of order processing logic")
                .tag("flow", "orders")
                .register(registry);
    }

    public void recordProcessing(Runnable action) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";
        try {
            action.run();
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(processingTimer);
            Counter.builder("app.integration.events")
                    .tag("flow", "orders")
                    .tag("outcome", outcome)
                    .register(registry)
                    .increment();
        }
    }
}
~~~

### 12.1. Đọc chính xác semantics của ví dụ

- `processing.duration` đo **đoạn code được truyền vào action**, không đo thời gian chờ trong QueueChannel hay độ trễ đầu vào tới đầu ra.
- `events` đếm **một lần gọi recordProcessing**, không tự đếm unique business message.
- Nếu `action.run()` có retry bên trong hoặc handler được redeliver, counter có thể tăng nhiều lần cho cùng business event.
- `outcome=success` ở đây nghĩa là **action không ném RuntimeException**; không chứng minh target đã bền vững commit nếu action chỉ queue dữ liệu.
- Ví dụ bắt `RuntimeException`, vì thế không tự định nghĩa đầy đủ semantics cho mọi `Error` hoặc xử lý bất đồng bộ; cần điều chỉnh theo mô hình ứng dụng.

### 12.2. Vì sao tag phải cố định?

Ví dụ chỉ dùng `flow=orders` và `outcome=success|failure`. Không dùng:

~~~text
Không nên:
tag("orderId", orderId)
tag("filename", filename)
tag("userId", userId)
tag("correlationId", correlationId)
tag("exceptionMessage", exception.getMessage())
~~~

Những giá trị này gần như vô hạn theo thời gian, gây **high cardinality**, tăng memory/chi phí monitoring và có thể lộ PII. Đưa chúng vào **structured logs/traces đã được bảo vệ** thay vì labels metric.

## 13. Thiết kế metric contract cho một integration flow

### 13.1. Các mốc trạng thái có thể audit

~~~mermaid
stateDiagram-v2
    [*] --> SOURCE_AVAILABLE
    SOURCE_AVAILABLE --> RECEIVED: Inbound đọc thành công
    RECEIVED --> ACCEPTED: Validate pass
    RECEIVED --> REJECTED: Validate fail
    ACCEPTED --> IN_FLIGHT: Xử lý
    IN_FLIGHT --> DELIVERY_ATTEMPTED: Gọi outbound
    DELIVERY_ATTEMPTED --> CONFIRMED: Target xác nhận
    DELIVERY_ATTEMPTED --> RETRYABLE_FAILURE: Có thể retry
    RETRYABLE_FAILURE --> DELIVERY_ATTEMPTED: Retry hợp lệ
    RETRYABLE_FAILURE --> TERMINAL_FAILURE: Hết budget / DLQ
    CONFIRMED --> [*]
    REJECTED --> [*]
    TERMINAL_FAILURE --> [*]
~~~

Không phải hệ thống nào cũng có trạng thái `CONFIRMED` ngay lập tức. Một API HTTP trả 202 có thể chỉ chấp nhận công việc bất đồng bộ; nếu cần bảo đảm business completion, phải thu thập callback/status event hoặc reconciliation ở target.

### 13.2. Ví dụ định nghĩa meter ứng dụng

| Meter logic | Loại | Labels đề xuất | Ý nghĩa |
|---|---|---|---|
| `app.integration.events` | Counter | flow, stage, outcome | Số sự kiện qua một mốc được định nghĩa |
| `app.integration.processing.duration` | Timer | flow, handler | Thời gian xử lý đoạn logic |
| `app.integration.end_to_end.duration` | Timer | flow, outcome | Thời gian received → confirmed/failed |
| `app.integration.queue.depth` | Gauge | flow, queue | Độ sâu queue đã xác định |
| `app.integration.oldest_item.age` | Gauge | flow, source | Tuổi item cũ nhất chưa xử lý |
| `app.integration.poll.events` | Counter | source_type, outcome | Poll empty/nonempty/error |
| `app.integration.delivery.attempts` | Counter | target_type, outcome | Số lần gọi target và kết quả vận chuyển |
| `app.integration.dlq.events` | Counter | flow, reason_class | Message tới DLQ |
| `app.integration.connections.active` | Gauge | dependency, state | Trạng thái hoặc số kết nối từ client pool |

Các metric trên **phải được code/instrument tương ứng** nếu dự án muốn có chúng. Không tự đăng ký gauge giả luôn bằng 0 khi chưa biết nguồn trạng thái thực; cảnh báo trên dữ liệu giả sẽ gây hiểu lầm.

### 13.3. Quy tắc rõ nghĩa cho success và retry

Giả sử 100 business events đi vào, 95 hoàn tất ngay, 3 hoàn tất sau một lần retry và 2 hết retry → DLQ:

- **Received unique events:** 100.
- **Successfully confirmed unique events:** 98.
- **Terminal failures:** 2.
- **Delivery attempts:** ít nhất 103 nếu chỉ 3 event được retry đúng một lần; có thể cao hơn nếu 2 failed events cũng đã thử lại.
- **Success rate theo business events:** 98/100, không phải số successful attempts chia tổng attempts.

Nếu không có idempotency và business identity, việc tính unique events từ attempts có thể sai. Thống nhất SLI với domain owner.

## 14. SLI và SLO cho tích hợp: đo điều gì là đủ tốt?

**SLI (Service Level Indicator)** là phép đo định lượng phản ánh chất lượng dịch vụ; **SLO (Service Level Objective)** là mục tiêu cho SLI trong một cửa sổ. Metric chỉ hữu ích khi gắn được với kỳ vọng hệ thống.

### 14.1. SLI phổ biến

| SLI | Công thức khái niệm | Cần làm rõ |
|---|---|---|
| **Delivery success rate** | Unique events confirmed / eligible events | Eligible và confirmed dựa vào hệ thống nào? |
| **End-to-end latency** | Confirmed time − accepted/source time | Có bao gồm queue, remote API, consumer downstream không? |
| **Freshness** | Now − event time của item mới nhất được xử lý thành công | Đồng hồ/timezone và nguồn event time có tin cậy không? |
| **Backlog age** | Now − thời điểm item cũ nhất đang pending | Pending ở inbound source, in-memory queue hay broker? |
| **Processing error ratio** | Failed processing attempts / all processing attempts | Error retries hay lỗi cuối cùng? |
| **Availability of adapter path** | Khoảng có thể nhận và xử lý thành công theo probe | Probe có đại diện giao dịch thật không? |

### 14.2. Ví dụ giả lập về SLO

- 99,9% business events hợp lệ được target xác nhận trong cửa sổ đo của tổ chức.
- 95% file đầu vào được xử lý tới target trong khoảng thời gian quy định sau khi **file sẵn sàng đọc**, không tính khi upload chưa hoàn tất.
- Backlog age của luồng đơn hàng không vượt ngưỡng đã định trong giờ phục vụ.
- Với tích hợp batch cuối ngày, deadline quan trọng hơn số messages/s từng phút.

**Không dùng những giá trị trên làm SLA mặc định**; cần chốt với owner nghiệp vụ, throughput thực tế, batch window, khả năng hệ thống ngoài và sự kiện nào nằm trong tập được tính.

### 14.3. Bẫy ở inbound SLO

Nếu poller chỉ đọc từ SFTP mỗi 5 phút, tính latency từ **lúc poll** sẽ bỏ qua thời gian file đã nằm trên server. Muốn đo freshness, có thể cần timestamp khi remote file hoàn tất, metadata an toàn và đồng hồ đồng bộ. Không lấy local processing duration để suy “file đã vào hệ thống kịp thời”.

## 15. Thiết kế tên và labels không gây high cardinality

### 15.1. Naming

Một quy ước hợp lý:

~~~text
app.integration.<domain>.<signal>
Ví dụ:
app.integration.events
app.integration.processing.duration
app.integration.poll.events
app.integration.queue.depth
~~~

Tên metric nên biểu thị **đơn vị và semantics** nhất quán; đừng ghi `total` ở code nếu backend exporter đã thêm suffix counter theo convention, trừ khi đã hiểu cách xuất.

### 15.2. Labels nào phù hợp?

| Nhãn | Có nên dùng? | Lý do |
|---|---|---|
| `flow=orders` | Có | Tập flow xác định |
| `adapter_type=kafka` | Có | Danh sách protocol hữu hạn |
| `direction=inbound|outbound` | Có | Hữu hạn |
| `outcome=success|failure|timeout` | Có | Hữu hạn |
| `error_class=auth|network|schema` | Có nếu taxonomy ổn định | Hữu hạn, có ý nghĩa vận hành |
| `environment=prod` | Có nếu được quản lý | Nhóm môi trường hữu hạn |
| `host/instance` | Cân nhắc theo collector | Nhiều instance tăng series, nhưng đôi khi cần debug |
| `file_path` | Không | Cardinality/PII/path nhạy cảm |
| `message_id`, `order_id` | Không | Mỗi message một series |
| `kafka_partition` | Cân nhắc | Tăng theo số partition, dùng khi thật sự cần |
| `exception_message` | Không | Gần như vô hạn, có thể chứa secret |
| `http_url_full` | Không | Path động và query nhạy cảm |

### 15.3. Cardinality bùng nổ thế nào?

Nếu có 10 flow × 5 endpoint × 4 outcome × 50 tenant ID × 2.000 file names, số tổ hợp có thể lên tới **2 triệu series** trước khi tính instance và histogram buckets. Trong khi đó dùng flow/endpoint/outcome cố định thường chỉ tạo hàng trăm series. Đừng gắn tenant/file/message cụ thể vào metrics; ghi **opaque correlation reference** vào log/trace.

## 16. File adapter: throughput, file age và tính bền vững

### 16.1. Inbound File

Các vấn đề thường gặp:

- Poller chạy nhưng không tìm thấy file do file filter hoặc cấu hình thư mục.
- File xuất hiện nhưng writer bên ngoài chưa hoàn tất; đọc sớm gây parse error.
- File trùng được lấy lại do metadata store/filter idempotency sai.
- File tồn đọng lâu; message count thấp không biết vì không có dữ liệu hay do lỗi.

Nên đo:

| Metric | Nguồn | Ý nghĩa |
|---|---|---|
| File discovered/eligible count | Scanner/filter | Số file đủ điều kiện |
| File accepted count | Inbound adapter | Số file thành Spring Message |
| File size distribution | File metadata | Phân bố kích thước file |
| Oldest eligible file age | Directory/file inventory | SLA freshness |
| Parse/validation failure | Handler/error channel | Lỗi payload |
| Duplicate/ignored count | Accept-once filter/metadata store | File bị bỏ do policy |
| Successful downstream outcome | Target/biz audit | Đã hoàn tất xử lý, không chỉ đọc file |

### 16.2. Outbound File

Đếm số attempt ghi file khác số file đã hoàn tất và được target đọc. Nếu cần giao nhận an toàn, theo dõi **ghi tạm → rename/commit theo quy trình**, checksum/size và lỗi I/O; không kết luận durable write chỉ vì channel send thành công.

**Không dùng tên file đầy đủ làm metric label**. Nếu cần điều tra một file, dùng log tham chiếu hoặc audit file ID.

## 17. SFTP adapter: poll, remote session và transfer outcomes

SFTP có ít nhất ba phạm vi metrics:

1. **Remote connectivity:** session establishment, auth failure, timeout, stale connection.
2. **Remote discovery/transfer:** listing count, file eligible, bytes transferred, transfer duration, retry, partial transfer.
3. **Downstream processing:** parse, transform, publish, ACK/DB commit sau khi file đã được nhận.

| Triệu chứng | Metric cần xem | Chẩn đoán |
|---|---|---|
| Không có message mới | Poll count/last success, listing errors, remote file age | Poller dừng hay remote directory trống? |
| Lỗi chuyển file | SFTP transfer errors, retries, session opens | Auth/network/permission/remote disk? |
| Throughput giảm | Bytes/s, transfer latency, concurrent sessions | Băng thông, server throttling, file size? |
| File bị đọc lại | Filter metadata state, duplicate count | Accept-once/filter persistence hoặc rename? |
| File đã tải nhưng chưa xử lý | Local queue age, downstream errors | SFTP ổn nhưng flow bị nghẽn? |

**Vòng đời kết nối:** session pool metrics và trạng thái remote không mặc nhiên được Spring Integration xuất sẵn dưới một tên chuẩn; có thể cần metrics từ SSH/SFTP client, wrapper hoặc health probe. Không probe bằng cách mở session liên tục với tần suất quá cao gây rate-limit.

## 18. HTTP inbound/outbound gateway: request, status và latency

### 18.1. HTTP inbound

Ngoài handler/channel metrics, theo dõi:

- HTTP request rate, latency, response status, 4xx/5xx và timeout.
- Số request được adapter biến thành message và được business handler chấp nhận.
- In-flight requests, thread pool saturation và request body size theo bucket.
- **Client disconnect**/cancel và các trường hợp business processing vẫn tiếp tục sau khi caller timeout.

Nếu HTTP trả 202 sau khi enqueue vào QueueChannel, đó là **acceptance**, chưa chắc business event đã hoàn tất. Metric `2xx` không được dùng làm SLI confirmed outcome nếu hợp đồng là async.

### 18.2. HTTP outbound

Đo request attempt, connection pool, DNS/TLS errors, status class, response time, timeout, retry và circuit breaker nếu có. Nên tách:

- **Network/transport outcome:** kết nối/HTTP status.
- **Application outcome:** response body/code nghiệp vụ.
- **Business completion:** remote đã commit hay chỉ accepted async.

### 18.3. Labels HTTP an toàn

Không dùng URL đầy đủ như `/customers/7812/orders/934` hoặc query token làm tag. Dùng **route template/endpoint class** có số lượng hữu hạn, status class, client name cố định; đảm bảo framework HTTP metrics có cơ chế sanitize route.

## 19. JMS adapter: ack, transaction, consumer và DLQ

Với JMS, metrics của Spring Integration tại handler chỉ phản ánh **xử lý trong process**, không tự bảo đảm JMS session commit/ack.

### 19.1. Các tín hiệu broker/client

| Metric | Câu hỏi |
|---|---|
| Queue depth/oldest age | Message còn chờ bao lâu? |
| Consumer count/in-flight | Consumer có đang kết nối và xử lý? |
| Delivery/redelivery count | Có message bị giao lại sau rollback? |
| Acknowledge/transaction commit | Processing đã commit theo JMS semantics chưa? |
| DLQ size/ingress | Message lỗi cuối cùng đang nằm đâu? |
| Connection/session failures | Broker có mất kết nối hay auth lỗi? |

### 19.2. Tránh đếm hai lần

Nếu một message bị rollback và redeliver ba lần, **handler invocation count = 3** nhưng **unique business event = 1**. Định nghĩa metric `attempt` và `confirmed unique` riêng, theo ID nghiệp vụ/deduplication. Không dùng một bộ counter handler để tuyên bố exactly-once processing.

### 19.3. Transaction boundaries

Khi JMS consumer phối hợp database transaction, phải biết **ack và DB commit** có nằm chung transaction hay không, cơ chế redelivery và điều kiện DLQ. Một timer ngắn hoặc một handler success không chứng minh atomicity; cần kiểm thử failure/recovery.

## 20. AMQP/RabbitMQ: publish confirm và consumer ack

Các tầng nên quan sát:

1. **Producer:** số publish attempts, confirm ack/nack và returned messages nếu routing bắt buộc.
2. **Broker:** queue depth, ready/unacked messages, consumer count, ingress/deliver rates.
3. **Consumer:** processing attempts, ack/nack/requeue, errors, retries và DLQ.
4. **Connection/channel:** reconnect, heartbeat, auth failures, channel closures.

**Phân biệt:**

- Producer confirm cho biết broker xử lý publish theo chế độ confirm, **không chứng minh consumer đã xử lý**.
- Consumer ack phản ánh hành vi protocol, không tự chứng minh mọi side effect phía database đạt exactly-once.
- Requeue có thể tạo vòng lặp và làm tăng attempts; theo dõi **redelivery ratio và age of oldest message**, không chỉ số deliveries/s.

### 20.1. Cảnh báo “tốc độ cao nhưng không tiến triển”

Nếu `deliveries/s` cao cùng `nack/requeue` cao mà backlog không giảm, hệ thống có thể đang **poison-message loop**. Dashboard chỉ nhìn throughput sẽ cho kết luận sai. Cần status theo terminal success, DLQ và loại lỗi.

## 21. Kafka adapter: partition/offset, lag và commit

### 21.1. Inbound Kafka

Kafka consumer cần quan sát:

- Records polled/processed và failure attempts.
- **Consumer lag** theo group/topic/partition khi có dữ liệu.
- Rebalances, pauses, seek/retry, poll duration và processing latency.
- Offset commit failures, DLQ/retry topic backlog.
- Thời gian từ record timestamp tới processing/confirmation nếu timestamp phù hợp.

**Consumer lag không đồng nghĩa processing latency.** Một record có thể được poll và xử lý chậm dù lag nhìn nhỏ; ngược lại sau rebalance, lag cao nhưng consumer đang bắt kịp.

### 21.2. Outbound Kafka

Nên theo dõi client producer:

| Metric | Ý nghĩa |
|---|---|
| Publish/send attempts | Số record đưa vào producer API |
| Send callback success/failure | Kết quả broker publish theo producer semantics |
| Retry/buffer pressure | Producer bị nghẽn, backpressure |
| Batch/bytes/compression | Đặc tính throughput |
| Broker request latency | Độ trễ gửi và ack ở client/broker |
| Producer errors/timeouts | Lỗi transport hoặc khả năng kết quả chưa rõ |

**Không đồng nhất callback gửi thành công với downstream business processing.** Nếu hợp đồng yêu cầu consumer B đã lưu DB, cần event xác nhận/reconciliation ở B.

### 21.3. Topic, group và partition tags

Topic/consumer group thường có số lượng hữu hạn được quản lý; phân vùng tăng series theo số partition, nên chọn phù hợp với quy mô. Không dùng Kafka key hoặc payload làm metric label. Khi cần xem một record, dùng topic/partition/offset trong **log/trace được bảo vệ**.

### 21.4. Exactly-once và metric outcome

Kafka hỗ trợ các cơ chế transaction/offset và idempotent producer theo cấu hình, nhưng **end-to-end exactly-once** phụ thuộc cả side effects bên ngoài, DB và flow. Metric không tự xác nhận tính chất đó; kiểm thử trên failure/replay/rebalance.

## 22. JDBC/database adapter: polling watermark, transaction và data freshness

Các luồng JDBC phổ biến gồm inbound polling query, outbound update/insert hoặc gateway request/reply. Metric cần đáp ứng:

- Thời gian SQL/transaction, pool active/idle/wait, connection errors.
- Số rows selected, processed, updated/inserted theo outcome.
- **Watermark/cursor progress** và lag giữa record nguồn tới khi xử lý.
- Deadlocks, lock waits, serialization/constraint errors, retry.
- Số row bị chọn lại sau rollback/restart và tỷ lệ duplicate.

### 22.1. Không chỉ đo số rows được SELECT

Nếu inbound poller SELECT 1.000 rows nhưng chỉ xử lý/commit 100, counter selected tăng rất nhanh trong khi **backlog thực** không giảm. Phải phân biệt `selected`, `accepted`, `processed` và `committed`.

### 22.2. Giao dịch và idempotency

Trong multi-step flow DB → outbound API → DB update trạng thái, một HTTP timeout có thể xảy ra khi remote đã hoàn tất nhưng DB chưa cập nhật. Khi retry, records có thể bị xử lý lặp. Cần metric **reconciliation/unknown outcomes** và idempotency key, không suy ra hoàn tất bằng SQL query timer.

### 22.3. Độ nhạy dữ liệu

Không gắn SQL query có literal params, customer ID hoặc record key làm labels. Nếu cần phân nhóm endpoint, dùng **query name** cố định, loại SQL hoặc repository method có số lượng hữu hạn, với quyền truy cập metrics/logs phù hợp.

## 23. Luồng bất đồng bộ, backpressure và queue age

Một integration flow có thể không lỗi nhưng ngày càng chậm vì tốc độ vào lớn hơn tốc độ ra.

### 23.1. Quan hệ ingress, egress và backlog

Về trực giác:

~~~text
backlog(t+Δt) ≈ backlog(t) + arrivals(Δt) - completed(Δt)
~~~

Đẳng thức chỉ đúng khi hai bộ đếm cùng phạm vi và không có message duplicate, expiration, purge, retry/delayed queue ngoài tập đếm. Trong thực tế phải xác định **những trạng thái nào nằm trong backlog**.

### 23.2. Little's Law và giới hạn

Với một hệ ổn định và điều kiện áp dụng phù hợp, **Little's Law** diễn tả quan hệ giữa số work-in-progress trung bình, throughput trung bình và thời gian chờ trung bình:

\[
L = \lambda W
\]

Trong đó `L` là số item trung bình trong hệ, `λ` là tốc độ hoàn tất/đến trung bình theo điều kiện ổn định và `W` là thời gian trung bình ở hệ đó. Dùng để kiểm tra tính nhất quán giữa **in-flight/queue depth**, throughput và latency; không dùng để suy tức thời trong burst, outage hoặc hệ đang mất ổn định.

### 23.3. Dấu hiệu backpressure

| Tín hiệu | Khả năng |
|---|---|
| Queue age tăng, egress rate thấp | Downstream chậm hoặc bị lỗi |
| Executor queue tăng, thread active tối đa | Pool bão hòa |
| Producer buffer pressure tăng | Broker/remote chậm, throughput không đủ |
| HTTP outbound p99 tăng | Target/network/connection pool chậm |
| Poller error/timeout tăng | Source unavailable hoặc pool cạn |
| Retry attempts tăng cùng success không tăng | Poison message/remote lỗi kéo dài |

Tăng số worker mù quáng có thể làm database/broker quá tải. Cần **throttle, bounded queue, max in-flight, retry backoff, circuit breaker và capacity planning** phù hợp.

## 24. Error channel, retries và DLQ: đo lỗi mà không đếm sai

### 24.1. Ba kiểu lỗi cần phân biệt

1. **Transient failure:** timeout, network reset, rate-limit, broker temporarily unavailable. Có thể retry với backoff.
2. **Permanent failure:** payload schema sai, không có quyền hợp lệ, unsupported format. Retry y nguyên có thể không giải quyết.
3. **Unknown outcome:** request timeout nhưng remote có thể đã commit; cần readback/reconciliation trước khi retry.

### 24.2. Những counter nên tách

- `processing_attempts`: mọi lần handler được gọi.
- `retry_attempts`: mọi lần thử bổ sung.
- `recovered_after_retry`: unique event cuối cùng thành công sau retry.
- `terminal_failures`: unique event thất bại cuối cùng.
- `dlq_published`: event được publish tới DLQ theo protocol đã xác minh.
- `dlq_reprocessed`: event DLQ được xử lý lại theo quy trình.
- `unknown_outcomes`: event chưa biết kết quả đích.

### 24.3. ErrorMessage không đồng nghĩa “một lỗi cuối”

Spring Integration có các đường error channel/`ErrorMessage` tùy endpoint và cấu hình. Một exception có thể được bắt, retry, chuyển sang error channel, rollback hoặc được trả lại caller. Cần biết **error flow nào chịu trách nhiệm emit terminal outcome** để tránh tăng `terminal_failures` ngay ở lần retry đầu tiên.

**Không đếm 3 attempts lỗi là 3 business events thất bại** nếu đó chỉ là một event đang retry.

## 25. Metrics và message history, tracing: nối điểm đo với nguyên nhân

### 25.1. Một quy trình drill down điển hình

~~~mermaid
flowchart TD
    ALERT[Alert: end-to-end latency tăng] --> FLOW[Dashboard theo flow]
    FLOW --> STAGE[Stage: poller / queue / handler / outbound]
    STAGE --> METRIC[Metrics: age, timer, error, retry]
    METRIC --> TRACE[Trace/span theo correlation]
    TRACE --> LOG[Structured logs, error code, endpoint]
    LOG --> HISTORY[MessageHistory cục bộ nếu có]
    HISTORY --> TARGET[Đối soát ACK / broker / database]
    TARGET --> ACTION[Root cause, remediation, verification]
~~~

Không phải hệ nào cũng có đầy đủ một trace xuyên các adapter; cần instrument và propagate context phù hợp, đặc biệt qua QueueChannel, ExecutorChannel, broker và HTTP. `MessageHistory` chỉ lưu đường đi các thành phần Spring Integration được ghi nhận và được bảo toàn header, không chứa duration của từng hop.

### 25.2. Correlation ID không phải metric tag

Để điều tra một message cụ thể:

~~~text
Dashboard:
  flow=orders, target=kafka, outcome=timeout

Structured log/trace:
  correlation_ref=corr-82
  business_ref=order-opaque-ref
  endpoint=publishOrders
  error_code=BROKER_TIMEOUT

Spring Integration message history:
  validateOrder -> transformOrder -> publishOrders
~~~

Đưa `correlation_ref` vào trace/log, **không** đưa vào tag counter/timer. Điều này giữ metrics có cardinality thấp mà vẫn hỗ trợ điều tra chi tiết.

## 26. Dashboard vận hành theo luồng và phụ thuộc

Một dashboard hữu ích nên bắt đầu từ **service journey** thay vì liệt kê hàng trăm meter không rõ ý nghĩa.

### 26.1. Mẫu dashboard “orders-file-to-kafka”

| Hàng dashboard | Panels | Câu hỏi |
|---|---|---|
| **Business outcome** | Confirmed unique events, success %, end-to-end p95/p99 | Đơn hàng đã được chấp nhận đúng hạn chưa? |
| **Inbound** | Files eligible, file age, poll empty/error, bytes | File có xuất hiện và được đọc không? |
| **Processing** | Filter reject %, transform error %, handler timer | Payload/logic có lỗi không? |
| **Queue** | Depth, oldest age, enqueue/dequeue rate | Có backlog nội bộ không? |
| **Outbound Kafka** | Send attempts, confirmations, producer errors, retries | Producer/broker có xác nhận không? |
| **Downstream** | Consumer lag, DLQ, completion events | Consumer có xử lý được record không? |
| **Dependency health** | SFTP session failures, broker availability, DB pool | Hệ thống ngoài có bất thường không? |

### 26.2. Ba cấp độ nhìn

1. **Service overview:** SLO, freshness, end-to-end success, backlog tuổi lớn nhất.
2. **Component drill-down:** channel, handler, adapter, pool, retry, error classes.
3. **Case investigation:** trace/log và external target acknowledgement theo correlation/business reference.

Giới hạn dashboards hiển thị dữ liệu cá nhân; phân quyền viewer, retention và alert routing theo nhóm vận hành.

## 27. Truy vấn Prometheus minh họa

Các ví dụ dưới đây giả định bạn đã **tự tạo** counter `app.integration.events` và timer `app.integration.processing.duration` như mục 12, đã export qua Prometheus registry và kiểm tra tên series thực tế. Tên Prometheus thông thường sẽ được chuẩn hóa, nhưng **phải xác minh trên `/actuator/prometheus`** trước khi dùng.

### 27.1. Tốc độ sự kiện thành công

~~~promql
sum(
  rate(app_integration_events_total{
    flow="orders",outcome="success"
  }[5m])
)
~~~

Đây là tốc độ **thành công của `recordProcessing`** theo định nghĩa ứng dụng trong ví dụ, chưa phải số unique orders target confirmed.

### 27.2. Tỷ lệ lỗi attempt

~~~promql
sum(rate(app_integration_events_total{
  flow="orders",outcome="failure"
}[5m]))
/
clamp_min(
  sum(rate(app_integration_events_total{
    flow="orders"
  }[5m])),
  0.001
)
~~~

Khi lượng sự kiện ít, rate trên cửa sổ ngắn rất nhiễu; nên có **minimum traffic condition** hoặc burn-rate policy riêng, không cứ thấy error ratio 100% từ một event là page P0.

### 27.3. p95 processing duration

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_integration_processing_duration_seconds_bucket{
      flow="orders"
    }[5m])
  )
)
~~~

Truy vấn này **chỉ hoạt động khi histogram buckets thực sự được cấu hình và xuất** cho timer đó. Một timer không có percentile histogram sẽ không có series `_bucket` mong đợi; trong trường hợp đó phải cấu hình histogram/SLO buckets hoặc dùng phép đo khác.

### 27.4. Cảnh báo backlog age

Với custom gauge đã instrument:

~~~promql
max(app_integration_oldest_item_age_seconds{
  flow="orders"
}) > 300
~~~

Ngưỡng 300 giây chỉ minh họa. Cần xử lý **no data**, giờ nghỉ/không có batch, producer downtime và freshness business rule; một gauge bị biến mất có thể do exporter lỗi chứ không có nghĩa backlog bằng 0.

## 28. Alerting: tránh báo động sai và bỏ sót

### 28.1. Alert theo triệu chứng nghiệp vụ

Ưu tiên cảnh báo như:

- Tỷ lệ **confirmed end-to-end success** thấp hơn mục tiêu trong cửa sổ đo.
- **Oldest pending item age** vượt ngưỡng với nguồn đang có dữ liệu.
- **Queue backlog tăng liên tục** và tốc độ hoàn tất không đủ.
- **Consumer lag hoặc DLQ** tăng bất thường và kéo dài.
- **Remote publish confirmations** giảm cùng retry/timeouts tăng.
- **Poller không chạy** so với lịch kỳ vọng, dù không có dữ liệu gửi vào.

### 28.2. Alert theo nguyên nhân hỗ trợ

Các alert như connection errors, TLS/auth failures, thread pool saturation, DB pool wait, broker unavailable là **tín hiệu phụ trợ** rất cần nhưng không phải lúc nào cũng tương ứng trực tiếp với tác động người dùng.

### 28.3. Một bảng severity mẫu

| Mức tham khảo | Triệu chứng | Phản ứng |
|---|---|---|
| **Critical** | Dòng dữ liệu trọng yếu không hoàn tất và backlog vượt deadline | Page on-call, phối hợp owner nguồn/đích, containment và recovery |
| **High** | Delivery confirmations giảm mạnh, DLQ tăng, age liên tục cao | Điều tra connector/broker/handler, xử lý có ưu tiên |
| **Medium** | Một nguồn batch bị chậm nhưng còn trong cửa sổ phục hồi | Ticket và theo dõi sát |
| **Low** | Thay đổi metric nhỏ, chưa ảnh hưởng SLO | Review vào giờ làm việc |

Đây không phải ngưỡng chuẩn. **Không cảnh báo trên một số đếm tích lũy đơn lẻ** mà thiếu rate/window, baseline và volume. Luôn định nghĩa fallback cho monitoring pipeline mất dữ liệu.

## 29. Runbook MET-01 — Không thấy metric của channel/adapter

**Triệu chứng:** có messages chạy nhưng `/actuator/metrics` không có meter như kỳ vọng.

1. **Kiểm tra dependency:** Micrometer, Actuator và exporter có đúng phiên bản tương thích không?
2. **Kiểm tra enablement:** Spring Integration management/Observation đã được bật hoặc auto-config trong đúng ApplicationContext chưa?
3. **Kiểm tra luồng đã chạy:** meter có thể chưa được đăng ký trước khi channel/handler được sử dụng.
4. **Kiểm tra endpoint ID và bean:** channel/handler mà bạn đang xem có thực sự thuộc flow vừa chạy không?
5. **Kiểm tra registry:** có đúng `MeterRegistry` mà exporter đọc không, có MeterFilter loại meter không?
6. **Kiểm tra exposure/security:** metrics endpoint có đang bị tắt, hạn chế quyền hoặc chỉ expose nội bộ không?
7. **Kiểm tra tên/tag thực tế:** không hardcode tên từ ví dụ/version khác.
8. **Kiểm tra loại adapter:** metric đó thuộc client/broker, không tự do Spring Integration tạo?
9. **Kiểm tra số đo:** gửi một message/trigger poll đại diện, xem meter nào tăng thực sự.
10. **Viết test bảo vệ** naming/semantics quan trọng sau khi xác nhận version.

**Không sửa vội bằng cách tạo custom meter giả cùng tên** với built-in meter; dễ làm trùng/khác label semantics và che khuất lỗi cấu hình.

## 30. Runbook MET-02 — Metrics có nhưng báo sai kết quả

### 30.1. Throughput cao mà business outcome thấp

Kiểm tra: attempts vs unique events, retry/requeue loops, successful channel send vs outbound ACK, database commit vs handler return, filter rejects và DLQ.

### 30.2. p95 handler thấp nhưng end-to-end chậm

Kiểm tra: poll interval, source file age, QueueChannel/executor wait, broker lag, remote processing, response callbacks và clock skew.

### 30.3. Error rate đột ngột bằng 100%

Kiểm tra: cửa sổ tính chỉ có 1 request lỗi, service mới deploy chưa có traffic, exporter thiếu series success, label mapping khác, counter reset sau restart hoặc batch theo lịch.

### 30.4. “Backlog = 0” khi người dùng báo dữ liệu chưa tới

Kiểm tra: bạn đo queue nào? Message chưa được poll từ nguồn, đang nằm trong broker khác, bị DLQ, hay đã dequeue nhưng handler chưa confirm? Cần theo dõi **source pending + channel queue + broker/remote pending** trong phạm vi SLI.

### 30.5. Metric trùng hoặc tăng gấp đôi

Kiểm tra instrumentation chồng lớp, wrapper counter cộng thêm built-in counter, retry, redelivery, nhiều subscriber, duplicate scrape targets, multi-instance aggregation. Không tự chia cho 2 trước khi xác minh nguyên nhân.

## 31. Testing strategy cho metrics

Metrics là một phần **hợp đồng vận hành** nên phải được kiểm tra, nhưng test không nên ràng buộc quá chặt vào mọi tên meter nội bộ của thư viện.

### 31.1. Test custom meter bằng SimpleMeterRegistry

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderFlowMetricsTest {
    @Test
    void countsSuccessfulProcessing() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderFlowMetrics metrics = new OrderFlowMetrics(registry);
            metrics.recordProcessing(() -> {
                // Mô phỏng một lần xử lý thành công.
            });

            double count = registry.counter(
                    "app.integration.events",
                    "flow", "orders",
                    "outcome", "success")
                    .count();

            assertEquals(1.0d, count);
        }
    }
}
~~~

Ví dụ này kiểm thử **custom counter theo semantics `recordProcessing`**; không chứng minh tính đúng đắn end-to-end của một adapter cụ thể. Trong ứng dụng thật cần dependency JUnit tương thích và tách test code ra đúng môi trường; đây là đoạn mã hướng dẫn, không phải test đã được chạy.

### 31.2. Các test khác nên có

| Test | Input/sự cố mô phỏng | Kỳ vọng |
|---|---|---|
| Handler success | Message hợp lệ | Counter success tăng, timer có sample |
| Handler throws | Lỗi xử lý | Counter failure tăng, exception không bị nuốt |
| Filter reject | Message sai schema | Reject tăng, outbound không được gọi |
| Empty poll | Không có file/record | Poll count tăng nếu đo riêng, received không tăng |
| Source unavailable | SFTP/DB connect fail | Error tăng, alert theo policy |
| Queue saturation | Consumer chậm | Queue depth/age tăng, không gọi send success là business success |
| Retry/redelivery | Một event xử lý nhiều lần | Attempts tăng, unique outcome không đếm lặp |
| Broker timeout | Publish outcome unknown | Không tự tăng confirmed, cần callback/reconciliation |
| HTTP 202 async | Remote chấp nhận request | Accepted tăng, completed chỉ tăng khi confirmation về |
| Missing series | Monitoring scraper lỗi | Có missing-data alert, không coi no data là zero |
| High cardinality | Nhiều unique IDs | Không tạo series theo message/file/user ID |

### 31.3. Integration tests phụ thuộc phiên bản

Với built-in channel/handler metrics, tạo một flow nhỏ, gửi messages và kiểm tra **meter đã được xác minh trong chính version ứng dụng**. Nếu upgrade dependency, review tên meter/tag và tính tương thích dashboard; không chốt cứng toàn bộ bộ metric nội bộ nếu không thuộc hợp đồng cần duy trì.

## 32. Bảo mật, riêng tư và chi phí observability

### 32.1. Không để lộ payload/credential

Metrics labels không phải nơi chứa:

- JWT, OAuth access/refresh token, API key, SSH private key.
- Cookie, Authorization header, SFTP username/password.
- Tên người, email, customer ID, số đơn hàng có thể định danh cá nhân.
- Full file path, URL query hoặc SQL chứa literal dữ liệu.
- Stack trace/exception message thô.

### 32.2. Quyền truy cập và retention

Endpoints Actuator, exporter, dashboards và alerts phải có access control theo vai trò. Thiết lập retention theo quy định tổ chức; audit business nhạy cảm cần nơi lưu khác với metrics aggregate. Monitor về kết nối có thể tiết lộ topology/dịch vụ nội bộ.

### 32.3. Chi phí instrumentation

Mỗi timer có phân phối histogram và labels sẽ tạo nhiều series. Trước khi bật histogram tất cả handler/endpoint:

1. Xác định SLI thật sự cần percentile.
2. Chọn buckets hợp lý với dải latency.
3. Đo số series, storage và scrape cost.
4. Tránh label có giá trị không giới hạn.
5. Có sampling/tracing để drill down mà không mở rộng metrics quá mức.

### 32.4. Metrics pipeline cũng có thể lỗi

Prometheus exporter, scrape network, registry hoặc monitoring backend có thể không khả dụng. Phân biệt **không có dữ liệu đo** với **dịch vụ đang tốt**. Alert missing data/telemetry pipeline health là một phần của observability.

## 33. Tình huống thực hành có hướng giải

### Tình huống A — File poller không tạo message

Trên dashboard không có `received` trong 15 phút. File vẫn xuất hiện trên thư mục nguồn.

**Hướng xử lý:** kiểm tra poll tick, last successful poll, file eligibility, file filter, quyền đọc, scheduler và age của file cũ nhất. Nếu poller không chạy, không thể kết luận “không có dữ liệu” từ received count bằng 0.

### Tình huống B — QueueChannel depth tăng, handler timer vẫn tốt

Số message chờ tăng liên tục. Handler p95 chỉ 10 ms nhưng customer thấy trễ một phút.

**Hướng xử lý:** kiểm tra enqueue/dequeue rate, consumer concurrency, poller schedule, age và end-to-end latency. Thời gian chờ queue không nằm trong handler timer; xử lý backpressure và capacity đúng nguồn.

### Tình huống C — SFTP transfer count tăng nhưng Kafka không có record

Inbound SFTP tải được file và transformer thành công; downstream Kafka chưa thấy record.

**Hướng xử lý:** phân biệt SFTP inbound success, handler success, outbound send attempts và Kafka producer confirmations. Kiểm tra serializer/topic/permission/callback/DLQ, không dùng metric inbound làm bằng chứng broker publish thành công.

### Tình huống D — HTTP 202 nhưng người dùng không thấy kết quả

Inbound gateway trả 202 ngay sau khi enqueue message, nhưng consumer phía sau chậm.

**Hướng xử lý:** xem HTTP acceptance riêng, QueueChannel depth/age, downstream completion events và business success SLI. Đừng dùng tỷ lệ 2xx làm success rate của quy trình bất đồng bộ.

### Tình huống E — JMS redelivery làm error count tăng mạnh

Một message bị rollback và nhận lại nhiều lần; dashboard báo 200 lỗi dù chỉ 20 business events.

**Hướng xử lý:** kiểm tra attempt/redelivery/unique-event counters, transaction ACK và DLQ. Tách terminal failures khỏi retry attempts, dùng dedup/idempotency và xác minh outcome.

### Tình huống F — RabbitMQ throughput rất cao nhưng queue không giảm

Consumer liên tục nhận message rồi nack/requeue do schema lỗi.

**Hướng xử lý:** đo redelivery ratio, nack/requeue, DLQ và backlog oldest age. Giới hạn retry, phân loại permanent errors và xử lý poison-message loop; không tăng consumer vô hạn.

### Tình huống G — Kafka consumer lag thấp nhưng DB update chậm

Kafka poll/ack nhìn bình thường, song dữ liệu chưa được lưu kịp.

**Hướng xử lý:** kiểm tra offset commit semantics, DB pool wait/transaction latency, async queue/in-flight, end-to-end confirmation. Lag thấp không chứng minh DB đã commit thành công.

### Tình huống H — Gauge bằng 0 vì exporter mất kết nối

Dashboard hiển thị queue depth bằng 0 sau khi monitoring exporter bị lỗi.

**Hướng xử lý:** kiểm tra series missing, `up`/scrape health và ứng dụng thực. Cảnh báo thiếu dữ liệu; không mặc định null hoặc missing bằng 0.

### Tình huống I — Metrics backend quá tải bởi labels

Developer thêm `filename` và `orderId` vào tags, số series tăng đột biến.

**Hướng xử lý:** loại labels có giá trị thay đổi theo message, giữ flow/adapter/outcome hữu hạn, chuyển ID sang structured log/trace. Đo chi phí histogram × tags trước khi mở lại.

### Tình huống J — Error ratio tăng sau retry rollout

Sau khi thêm retry, counter handler failure tăng nhưng terminal DLQ giảm.

**Hướng xử lý:** đây có thể là sự thay đổi **attempt semantics**, không nhất thiết tình trạng xấu hơn. So retry attempts, recovered-after-retry, terminal failures, remote confirmed và end-to-end latency.

### Tình huống K — JDBC polling xử lý cùng row hai lần

Poller SELECT row chưa xử lý; một HTTP timeout xảy ra sau khi remote đã commit, DB status chưa cập nhật.

**Hướng xử lý:** phân biệt selected, attempt và confirmed outcome; dùng idempotency key, remote reconciliation, transaction/watermark và duplicate count. Không suy sự thành công từ SQL query timer.

### Tình huống L — DirectChannel send latency p99 tăng

Dashboard kênh đồng bộ báo send chậm, còn adapter output nằm cuối flow.

**Hướng xử lý:** kiểm tra handler/downstream call cùng thread, CPU, external HTTP/DB latency và queue/circuit breaker. Send timer của DirectChannel có thể bao trùm xử lý downstream, không nhất thiết do chính channel “chậm”.

## 34. Checklist triển khai metrics cho adapter và channel

### 34.1. Thiết kế trước khi code

- [ ] Xác định success/error/attempt/confirmed theo **hợp đồng nghiệp vụ**.
- [ ] Vẽ ranh giới inbound → channel → handler → outbound → remote ACK.
- [ ] Đặt tên ổn định cho endpoint/channel, biết nào là sync/async.
- [ ] Thống nhất SLI: success rate, end-to-end latency, queue age/freshness.
- [ ] Có nguồn đo cho poll tick và source backlog, không chỉ message count.
- [ ] Xác định adapter-specific telemetry cho File/SFTP/HTTP/JMS/AMQP/Kafka/DB.
- [ ] Chọn labels low cardinality; không đưa business IDs/PII vào tags.

### 34.2. Cấu hình và kiểm thử

- [ ] Micrometer/Actuator/registry tương thích version đã dùng.
- [ ] Spring Integration management/observation được cấu hình đúng context.
- [ ] Có quyền truy cập an toàn tới metrics exporter; không expose công khai.
- [ ] Liệt kê và xác minh meter names/tags/types thực tế.
- [ ] Custom counters/timers có test happy/failure/retry.
- [ ] End-to-end confirmation được đo tại đúng target/ACK.
- [ ] Retry/redelivery không bị đếm thành unique success/failure.
- [ ] Histogram/percentile được cấu hình trước khi dùng query bucket.
- [ ] Có alert missing data và kiểm tra series cardinality.

### 34.3. Vận hành và hậu kiểm

- [ ] Dashboard bắt đầu từ business SLO, drill down tới adapter/channel.
- [ ] Queue depth và **age** được theo dõi phù hợp.
- [ ] Có SFTP/File poller last tick/last item age.
- [ ] Broker ACK, DLQ, consumer lag và commit semantics được hiểu đúng.
- [ ] HTTP 2xx/202 và business completion không bị đánh đồng.
- [ ] Database SELECT/processed/committed có ranh giới rõ.
- [ ] Alerts có cửa sổ, traffic floor, owner, escalation và runbook.
- [ ] Logs/traces/message history hỗ trợ truy nguyên nhưng không rò dữ liệu.
- [ ] Sau thay đổi adapter/registry, metric contract và dashboard được kiểm tra lại.

## 35. Kết luận

**Metrics cho adapter và channel** không chỉ là “đếm số message chạy qua Spring Integration”. Một hệ thống tích hợp đáng tin cậy cần thấy rõ **inbound nhận gì, MessageChannel chuyển gì, handler xử lý thế nào, outbound đã thử bao nhiêu lần và target xác nhận điều gì**. Chỉ số queue age, poll cadence, retries, connection health và business freshness giúp phát hiện những trường hợp throughput nhìn đẹp nhưng dữ liệu thực tế vẫn bị trễ hoặc mất.

Trong **Spring Integration Adapters**, Micrometer và Spring Boot Actuator là nền tảng thuận tiện để thu thập/xuất metrics; instrumentation của channel/handler cần được xác nhận theo version, còn telemetry cho File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC phải gắn với semantics của từng giao thức. Kết hợp **metrics có hợp đồng rõ ràng, dashboard SLI/SLO, log/trace/message history và kiểm chứng tại hệ thống đích**, đồng thời giữ nhãn hữu hạn và bảo vệ dữ liệu nhạy cảm, giúp đội vận hành phân biệt chính xác **đã gửi – đã nhận – đã xử lý – đã xác nhận hoàn tất**.
