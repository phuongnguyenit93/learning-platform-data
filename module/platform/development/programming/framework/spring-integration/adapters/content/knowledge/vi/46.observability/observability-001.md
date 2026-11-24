# Message history qua các endpoint trong Spring Integration

## 1. Bài toán: một message đã đi qua những endpoint nào?

Trong Spring Integration, một luồng xử lý thường bắt đầu từ **inbound adapter/gateway**, chuyển qua một hoặc nhiều **MessageChannel**, **filter**, **router**, **transformer**, **splitter**, **aggregator**, **service activator**, rồi kết thúc ở **outbound adapter/gateway**. Khi luồng có nhiều nhánh và xử lý bất đồng bộ, câu hỏi “Message này đã đi qua đâu trước khi lỗi?” không dễ trả lời chỉ bằng một dòng stack trace.

**Message history** là thông tin chẩn đoán được Spring Integration tích lũy trong **message header** để phản ánh các thành phần tích hợp mà message đã đi qua **khi cơ chế thu thập history được bật và header được giữ lại**. Nó giúp:

- Phân biệt message đi qua nhánh router nào, endpoint nào đã xử lý, endpoint nào chưa thấy.
- Điều tra vì sao một filter, transformer, handler hoặc gateway cho kết quả ngoài dự kiến.
- Đối chiếu đầu vào/đầu ra giữa các adapter file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu.
- Phối hợp với **correlation ID**, metrics, logs và tracing để chẩn đoán lỗi xuyên kênh.
- Xây dựng phép thử xác nhận đường đi của một message theo hợp đồng tích hợp.

Bài học thuộc chương **Observability** của module **SPRING_INTEGRATION_ADAPTERS**. Phạm vi học tập là cách kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel; thực hành luồng qua file, SFTP, HTTP, JMS, AMQP, Kafka, database; đồng thời theo dõi **hợp đồng message, lỗi và vòng đời kết nối**. Vì thế trọng tâm không phải tổng quan logging, mà là **hiểu và vận hành MessageHistory ở từng ranh giới endpoint**.

> **Giới hạn quan trọng:** Message history là metadata chẩn đoán trong một đường xử lý Spring Integration. Nó **không mặc nhiên** là distributed trace xuyên process/broker, không ghi lại thời gian thực thi từng hop, không bảo đảm tồn tại sau khi serialize sang giao thức bên ngoài và **không phải** audit log bất biến.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **history, message ID, correlation ID, log, metric và trace**.
2. Bật/tắt và đọc `MessageHistory` bằng cấu hình Spring Integration phù hợp.
3. Đọc đường đi của message qua endpoint, channel, router, splitter/aggregator, poller và gateway.
4. Xác định những nơi history **không xuất hiện hoặc bị mất** do mapping/serialization/new message.
5. Viết phép thử và dashboard hỗ trợ chẩn đoán mà không để lộ dữ liệu nhạy cảm hoặc làm tăng header vô hạn.

## 2. Nhắc lại mô hình Message, Header, Channel và Endpoint

Một message trong Spring Messaging có thể hiểu là:

~~~text
Message<T>
├── payload: T
└── headers: MessageHeaders
    ├── id
    ├── timestamp
    ├── correlationId / sequenceNumber / sequenceSize (nếu có)
    ├── application headers (nếu có)
    └── history (khi MessageHistory được bật và truyền qua)
~~~

**Payload** là dữ liệu nghiệp vụ: nội dung file, DTO, byte[], record Kafka, câu lệnh/request hoặc kết quả xử lý. **Header** mang metadata hỗ trợ định tuyến và xử lý. **MessageChannel** là đường chuyển message; **endpoint** nối một adapter, handler hoặc message source vào channel. Ví dụ:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **Inbound channel adapter** | Nhận/poll dữ liệu từ bên ngoài, đưa thành message vào flow | File inbound, SFTP inbound, JMS listener |
| **Inbound gateway** | Nhận request và cung cấp đường reply | HTTP inbound gateway |
| **MessageChannel** | Vận chuyển message giữa các endpoint | DirectChannel, QueueChannel, ExecutorChannel |
| **Filter** | Chấp nhận hoặc loại message theo điều kiện | Loại file sai đuôi, message không hợp lệ |
| **Router** | Chọn kênh/nhánh xử lý | Chuyển theo loại đơn hàng |
| **Transformer** | Chuyển payload/hình thức biểu diễn | File → DTO, JSON → domain object |
| **Service activator** | Thực thi xử lý nghiệp vụ | Lưu lệnh vào database |
| **Splitter / Aggregator** | Tách một message thành nhiều phần / gom nhóm | Batch item, fan-out/fan-in |
| **Outbound adapter** | Gửi ra bên ngoài, thường là one-way | Gửi file/SFTP, publish Kafka |
| **Outbound gateway** | Request/reply với hệ thống ngoài | HTTP call, database request/reply |
| **Poller** | Kích hoạt nguồn hoặc consumer theo chu kỳ | Đọc thư mục, bảng DB, QueueChannel |

**Điểm cần nhớ:** history mô tả **những thành phần được instrument và thực sự được đi qua**, không phải một sơ đồ tĩnh của tất cả node đã cấu hình. Nếu router chọn nhánh A, history của message đó không chứng minh nhánh B có được gọi.

## 3. MessageHistory là gì?

Spring Integration có cơ chế **message history** và API `org.springframework.integration.history.MessageHistory`. Khi được kích hoạt, thông tin thành phần được tích lũy trong header có tên do `MessageHistory.HEADER_NAME` định nghĩa (thường là `history`).

Một phần tử history thường có thông tin tương đương:

- **`name`:** tên/ID của thành phần tích hợp được ghi nhận.
- **`type`:** loại thành phần tích hợp được ghi nhận.

Bạn có thể đọc history qua API `MessageHistory.read(message)` và duyệt các mục theo thứ tự được lưu. Tùy **phiên bản, kiểu endpoint và cấu hình**, danh sách thành phần cụ thể có thể khác nhau. Vì vậy hãy xác nhận bằng một phép thử với phiên bản Spring Integration đang sử dụng thay vì hardcode hình dạng history vào hợp đồng nghiệp vụ.

### 3.1. Message history không phải message log

| Câu hỏi | Message history giải đáp được? | Cần công cụ bổ sung |
|---|---|---|
| Message đã đi qua những thành phần nào? | Có, trong phạm vi history được ghi và giữ | Log để kiểm tra bản ghi thực thi |
| Filter có loại message không? | Có thể suy từ đường đi và checkpoint; không phải luôn có lý do reject | Counter discard, log quyết định filter |
| Handler chạy bao lâu? | Không phải chức năng cốt lõi | Micrometer timers, observation spans |
| Vì sao HTTP trả 500? | Chỉ cung cấp ngữ cảnh đi tới endpoint | HTTP logs, exception, trace |
| Một Kafka record có bị redeliver? | Không đủ; mỗi lần xử lý có thể mang history khác | Offset/partition, consumer logs, delivery metrics |
| Message đi qua những service nào? | Không bảo đảm xuyên process | Distributed tracing, propagation có chủ đích |
| Đó có phải bằng chứng kiểm toán vĩnh viễn? | Không | Audit events được lưu an toàn, retention |
| Endpoint nào đang nghẽn? | Không có dữ liệu tốc độ hoặc độ sâu queue | Channel/handler metrics, queue depth, tracing |

### 3.2. Sơ đồ một luồng có history

~~~mermaid
flowchart LR
    EXT[File / SFTP / Broker] --> IN[Inbound Adapter]
    IN --> C1[rawChannel]
    C1 --> F[Validate Filter]
    F --> C2[validChannel]
    C2 --> T[Normalize Transformer]
    T --> R[Type Router]
    R -->|A| H1[Handler A]
    R -->|B| H2[Handler B]
    H1 --> OUT[Outbound Adapter]
    H2 --> OUT
    IN -. history .-> MH[History Header]
    F -. history .-> MH
    T -. history .-> MH
    R -. history .-> MH
    H1 -. history .-> MH
    H2 -. history .-> MH
~~~

Đường chấm chỉ mang ý nghĩa **metadata có thể được ghi khi message đi qua**. Nó không có nghĩa một header được gửi về node tập trung tên “History Header”, cũng không bảo đảm tất cả node trong hình đều luôn xuất hiện trong danh sách.

## 4. Bật message history bằng Java Configuration

Trong các phiên bản Spring Integration hỗ trợ annotation, có thể kích hoạt thu thập history bằng `@EnableMessageHistory` trên một cấu hình ứng dụng.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;

@Configuration
@EnableIntegration
@EnableMessageHistory
public class IntegrationHistoryConfiguration {
    // Bean cấu hình bổ sung nếu ứng dụng cần.
}
~~~

Khi tích hợp Spring Boot, phần enablement cơ bản có thể đã được Boot tự cấu hình; việc bật `@EnableMessageHistory` không nên nhầm với việc bật mọi metric/tracing. Hãy kiểm tra dependency, phiên bản và cấu hình thực tế của ứng dụng.

### 4.1. Cách bật bằng XML trong hệ thống legacy

Với Spring Integration XML namespace, cấu hình tương đương có thể sử dụng:

~~~xml
<int:message-history/>
~~~

Ở đây tiền tố `int` là namespace Spring Integration đã được khai báo trong file XML. Ví dụ này minh họa **phần tử enablement**, không phải một file cấu hình XML hoàn chỉnh. Không dùng cả hai phương thức một cách tùy tiện nếu ứng dụng đang có nhiều context cấu hình chồng lắp.

### 4.2. Bật ở môi trường nào?

- **Local/test:** hữu ích khi nghiên cứu một luồng, so sánh đường filter/router và kiểm thử các nhánh.
- **Staging:** thuận tiện để kiểm chứng behavior sau khi đổi topology, adapter và channel.
- **Production:** cần đánh giá tần suất message, kích thước header, lưu lượng liên service, PII và overhead trước khi bật rộng.

Message history thường tăng metadata theo số thành phần đi qua. Với flow dài, splitter fan-out lớn hoặc retry nhiều lần, header có thể lớn đáng kể. Không nên biến nó thành một tùy chọn “bật mãi cho mọi message” mà không đo lường overhead.

## 5. Đọc MessageHistory an toàn

Để inspect tại một điểm trong flow, dùng API đọc thay vì truy cập trực tiếp bằng chuỗi tên header.

~~~java
import java.util.Properties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;

public final class HistoryInspector {
    private static final Logger log =
            LoggerFactory.getLogger(HistoryInspector.class);

    private HistoryInspector() {}

    public static void inspect(Message<?> message) {
        MessageHistory history = MessageHistory.read(message);
        if (history == null || history.isEmpty()) {
            log.debug("No Spring Integration message history available");
            return;
        }

        for (Properties component : history) {
            String name = component.getProperty("name", "unknown");
            String type = component.getProperty("type", "unknown");
            log.debug("SI history component: name={}, type={}", name, type);
        }
    }
}
~~~

**Lưu ý về tính tương thích:** API và hình dạng record có thể thay đổi theo thế hệ thư viện; khi nâng version cần kiểm tra signature `MessageHistory.read(...)` và nội dung phần tử ở bản đang dùng. Ví dụ chỉ đọc metadata thành phần, **không in payload** hay các header chứa credential.

### 5.1. Vì sao phải kiểm tra null/rỗng?

Một số trường hợp thông thường:

1. History chưa được bật ở context tương ứng.
2. Message được đọc trước khi đi qua endpoint được theo dõi.
3. Message mới được tạo thủ công mà không giữ header.
4. Header bị loại bởi filter/header mapper tại ranh giới giao thức.
5. Message được nhận từ broker hoặc service khác mà history không được truyền qua.
6. Adapter/endpoint hoặc phiên bản framework không đóng góp mục lịch sử như người lập trình kỳ vọng.

Do đó, logic nghiệp vụ **không nên yêu cầu history tồn tại** để quyết định chấp nhận thanh toán, xóa dữ liệu hay cấp quyền. Đây là thông tin quan sát, không phải input tin cậy của domain.

## 6. Demo: một flow với transformer và điểm kiểm tra history

Ví dụ Java DSL tối giản: tiếp nhận tên file, chuẩn hóa và chuyển tới kênh quan sát. Dùng `@EnableMessageHistory` như ở mục 4.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class SimpleHistoryFlow {
    @Bean
    IntegrationFlow filenameFlow() {
        return IntegrationFlow.from("incomingFilename")
                .transform(String.class, String::trim,
                        endpoint -> endpoint.id("normalizeFilename"))
                .channel("historySink")
                .get();
    }

    @Bean
    @ServiceActivator(inputChannel = "historySink")
    MessageHandler historyConsumer() {
        return HistoryInspector::inspect;
    }
}
~~~

**Hành vi minh họa:** message đi vào `incomingFilename`, được transformer `normalizeFilename` xử lý rồi tới consumer ở `historySink`. History đọc ở consumer cho biết những thành phần framework đã ghi nhận cho message đó. **Đừng phụ thuộc vào đúng số mục hoặc thứ tự chi tiết** của một đoạn code ví dụ nếu chưa chạy trên phiên bản thư viện đang dùng.

### 6.1. Đặt ID endpoint có chủ đích

Đặt tên rõ ràng, ổn định cho endpoint như `normalizeFilename`, `validateOrder`, `routeBySource` hoặc `sendToBilling` giúp phân tích history hơn so với những ID sinh tự động. Đặt tên theo **vai trò logic** thay vì tên máy chủ, mật khẩu, người dùng hoặc một giá trị runtime thay đổi liên tục.

### 6.2. History là thông tin phát sinh trong flow

Một message được dựng ngoài Spring Integration rồi gửi vào channel có thể chưa có history. Sau khi đi qua các thành phần tích hợp được ghi nhận, các mục mới được bổ sung. Đọc message **trước** hoặc **sau** một endpoint có thể cho kết quả khác nhau; cần chọn checkpoint cố định để so sánh.

## 7. Theo dõi filter, router và transformer

### 7.1. Filter: khi message bị loại

Giả sử flow từ file:

~~~text
fileInbound -> validateFormat -> normalize -> outboundKafka
                     |
                     +-- discardChannel -> rejectAudit
~~~

Nếu file không hợp lệ và bị filter loại, message **không tới transformer hoặc outbound Kafka**. History chỉ phản ánh nhánh đã thật sự đi qua và còn có thể đọc được. Muốn biết **lý do bị loại**, nên có discard channel/counter/log có kiểm soát và mã lỗi nghiệp vụ:

~~~text
event = FILE_REJECTED
reason_code = UNSUPPORTED_EXTENSION
source_adapter = fileInbound
endpoint = validateFormat
message_ref = order-batch-2026-11
~~~

Không mong `history` tự chứa kết quả predicate, payload bị loại, exception hoặc thời điểm xử lý.

### 7.2. Router: một message chọn một hoặc nhiều nhánh

Router có thể điều hướng sang `priorityChannel` hoặc `standardChannel`; một số loại router cấu hình gửi nhiều nơi. History của **từng message ở từng nhánh** chỉ phản ánh đường của nhánh đó khi header được bảo toàn.

**Sai lầm thường gặp:** thấy tên router trong history rồi kết luận “mọi nhánh đã xử lý”. Muốn biết nhánh nào được chọn, ghi thêm routing decision event/tag với số lượng nhánh và mã kết quả; không tạo tag có cardinality vô hạn.

### 7.3. Transformer: khi payload thay hình dạng

Transformer có thể trả payload mới hoặc xây `Message<?>` mới. Framework thường xử lý/lan truyền các header phù hợp tùy loại transformer; nhưng **custom code tự tạo message** có thể vô tình bỏ header history, correlation hoặc reply channel.

~~~java
// Khi chủ động tạo Message mới và muốn giữ các header phù hợp
Message<String> normalized =
        MessageBuilder.withPayload(normalizedText)
                .copyHeaders(incomingMessage.getHeaders())
                .build();
~~~

Đoạn trên cần import `org.springframework.integration.support.MessageBuilder` hoặc builder phù hợp với version đang dùng. Đây là ví dụ **trong cùng ứng dụng**. Khi qua HTTP/JMS/AMQP/Kafka, không nên copy toàn bộ header không chọn lọc, vì một số header là runtime object, chứa thông tin nội bộ hoặc không serialize được.

## 8. MessageChannel: Direct, Queue, Executor và Publish-Subscribe

### 8.1. DirectChannel

Với `DirectChannel`, downstream handler thường chạy đồng bộ trên thread gọi, theo mô hình dispatch của channel. Header history có thể tiếp tục qua flow nếu không bị thay thế. Đừng suy ra **thời gian từng endpoint** chỉ vì list history có thứ tự.

### 8.2. QueueChannel

`QueueChannel` giữ message để một consumer/poller lấy ra sau. Độ trễ trong queue cần đo bằng queue depth, thời điểm enqueue/dequeue hoặc metric tương ứng; **history không ghi thời lượng chờ mặc định**. Nếu message bị khởi tạo lại trước khi đưa vào queue, có thể mất header.

### 8.3. ExecutorChannel

`ExecutorChannel` xử lý qua executor, tạo ranh giới thread. Message headers có thể vẫn nằm trong message, nhưng **MDC và tracing context là thread-local hoặc context-specific** nên không tự động bảo đảm được chuyển sang thread mới. Cần instrumentation/context propagation phù hợp với version, Spring Boot/Micrometer và executor đang dùng.

### 8.4. PublishSubscribeChannel

Một message được phát tới nhiều subscriber tạo các đường xử lý khác nhau. Khi nhiều subscriber cùng xử lý, cần chú ý **thứ tự, async dispatch và bất biến message/header**, không giả định một list history duy nhất biểu diễn đầy đủ mọi nhánh theo thứ tự toàn cục.

| Kênh | Câu hỏi chẩn đoán quan trọng | Dữ liệu ngoài history |
|---|---|---|
| DirectChannel | Handler nào nhận message ngay trên call path? | Exception, handler timer |
| QueueChannel | Message đang đợi hay consumer không lấy? | Queue depth, poll count, oldest age |
| ExecutorChannel | Task có được schedule/thực thi? | Executor queue, active threads, trace propagation |
| PublishSubscribeChannel | Subscriber nào thành công/thất bại? | Subscriber counters, per-branch logs, error policy |

## 9. Splitter, Aggregator và Resequencer

Đây là nhóm endpoint dễ làm người học suy luận sai về history vì **một message có thể trở thành nhiều message**, hoặc nhiều message được gom thành một.

### 9.1. Splitter

Giả sử payload là danh sách 100 bản ghi. Splitter tạo các message con, thường gắn metadata phục vụ correlation/sequence theo cấu hình. Mỗi message con có thể mang các header phù hợp từ message cha và tiếp tục tích lũy history theo đường xử lý riêng.

~~~mermaid
flowchart TD
    B[Batch Message] --> S[Splitter]
    S --> M1[Item 1 - headers riêng]
    S --> M2[Item 2 - headers riêng]
    S --> MN[Item N - headers riêng]
    M1 --> V[Validate]
    M2 --> V
    MN --> V
    V --> AGG[Aggregator]
    AGG --> RES[Grouped Result]
~~~

Không nên diễn giải một history của item 7 như bằng chứng 99 item còn lại đã chạy. Muốn tổng hợp kết quả cần **correlation ID, sequence/aggregation metadata, item status và metric**.

### 9.2. Aggregator

Aggregator có thể tạo message kết quả từ một tập messages đầu vào. History cuối cùng phụ thuộc cách framework/chính sách chọn message gốc, header merge và cách tạo output. **Không giả định aggregator hợp nhất toàn bộ history của mọi input**.

Nếu cần audit “mỗi item đi qua endpoint nào”, hãy lưu **một event riêng cho từng item**, hoặc một bảng kết quả item với correlation ID, chứ không mong header của result chứa mọi hành trình.

### 9.3. Resequencer và retry

Việc đổi thứ tự hoặc xử lý lại message khiến **thứ tự business event** khác thứ tự thực thi/tiếp nhận. History là dấu vết đường đi cục bộ, không phải bằng chứng về exactly-once processing, FIFO của broker hay quan hệ nhân quả xuyên mọi thread.

## 10. Poller và inbound adapter: history bắt đầu từ đâu?

Với **polling inbound adapter**, poller kích hoạt đọc nguồn theo lịch (thư mục file, remote SFTP, database hoặc nguồn khác), rồi adapter tạo message nếu có dữ liệu.

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant SRC as File / SFTP / DB
    participant A as Inbound Adapter
    participant C as MessageChannel
    participant H as Handler
    P->>A: Kích hoạt poll
    A->>SRC: Đọc/scan nguồn
    alt Có dữ liệu
        SRC-->>A: File / record
        A->>C: Message với payload + headers
        C->>H: Dispatch
        H->>H: Read MessageHistory
    else Không có dữ liệu
        SRC-->>A: Empty
        Note over A,H: Không có Message để xem history
    end
~~~

### 10.1. “Không có message” không có nghĩa poller không chạy

Nếu không có bản ghi nguồn, poller có thể chạy đúng mà **không phát bất kỳ message nào**; dĩ nhiên không có history để đọc. Ngược lại, poller có thể ngừng hoạt động vì scheduler/executor lỗi, cũng không có history. Phân biệt hai tình huống bằng:

- Poll tick count và thời điểm poll cuối.
- Số kết quả poll rỗng/không rỗng, số record phát.
- Lỗi kết nối, authentication, timeout, remote listing/read.
- Trạng thái scheduler, executor saturation và lock.
- Tuổi bản ghi/file cũ nhất chưa được xử lý.

### 10.2. Vòng đời resource/connection

File và SFTP có lỗi khác nhau: không thấy file, file đang được ghi dở, permission denied, remote session timeout, trùng tên hoặc khóa kết nối. History chỉ có giá trị với message thực sự đi vào flow; để biết **tại sao inbound adapter chưa tạo message**, phải theo dõi lifecycle của nguồn, session factory, poller, remote directory và filter.

## 11. Bảng đối chiếu theo loại adapter/gateway

| Adapter/gateway | History có ích ở đâu? | Điều không tự chứng minh | Dữ liệu cần bổ sung |
|---|---|---|---|
| **File inbound/outbound** | Đường từ file được poll đến transformer và output handler | File đã thực sự được ghi hoàn chỉnh/durable hay chưa | File path được rút gọn, size, checksum, write result |
| **SFTP inbound/outbound** | Hành trình sau khi remote file được tạo thành message | Kết nối SFTP đã tồn tại suốt thời gian hoặc upload đã commit | Remote session, transfer status, retry, remote file identity |
| **HTTP inbound gateway** | Endpoint xử lý request trong Spring Integration | Client đã nhận response hay mạng không đứt | HTTP status, request ID, server/client logs |
| **HTTP outbound gateway** | Path tới handler gọi HTTP và response processing trong app | Remote service đã commit giao dịch nếu timeout | HTTP status/latency, idempotency key, trace/span |
| **JMS inbound/outbound** | Flow trong từng ứng dụng tiêu thụ/phát JMS message | Broker ack, transaction commit, redelivery count | Message ID, correlation, consumer stats, DLQ |
| **AMQP/RabbitMQ** | Flow quanh producer/consumer của adapter | Publish confirm, consumer ack, retry hay DLQ outcome | Broker delivery tag, routing key, confirm/ack metrics |
| **Kafka inbound/outbound** | Những handler nội bộ xử lý record đến/từ Kafka | Offset commit, transactional boundary hoặc exactly-once | Topic/partition/offset, consumer group, lag, producer outcome |
| **JDBC/DB adapters** | Đường xử lý record/event được poll hoặc truy vấn | Transaction DB đã commit nếu thiếu transaction trace | Query/update result, transaction, lock, poll watermark |

### 11.1. Điểm kết thúc của history nội bộ

Khi một **outbound adapter** gửi message ra Kafka/JMS/AMQP/HTTP, history nằm trong message nội bộ. Dịch vụ tiêu thụ có thể dựng **message mới** từ payload và headers được mapped/serialized theo giao thức. Vì vậy **không được giả định** header history của process A sẽ tự trở thành history hợp lệ trong process B.

### 11.2. Điểm bắt đầu của history phía consumer

Một inbound adapter của process B có thể tạo Spring Message mới và bắt đầu tích lũy history **cục bộ tại B**. Để nối A và B, truyền **correlation/trace context** theo hợp đồng tích hợp được phê duyệt, không truyền nguyên xi mọi header nội bộ.

## 12. Header propagation và nguy cơ mất history

### 12.1. Các ranh giới cần xem

1. **Transformer/custom handler** tạo `Message<?>` mới.
2. **HeaderFilter** loại bỏ hoặc đổi tên header.
3. **Gateway** biến payload/header thành tham số request rồi dựng reply message.
4. **Adapter giao thức** chỉ map một tập header được hỗ trợ hoặc chọn qua header mapper.
5. **Serializer/converter** chuyển message sang JSON, Avro, byte[] hoặc native broker record.
6. **Aggregator/splitter** tạo messages con/kết quả với chính sách header riêng.
7. **Error flow** phát `ErrorMessage` và có thể chứa original message để điều tra.
8. **Process boundary** khi service khác nhận message và tạo Spring Message mới.

### 12.2. Trường hợp tạo message mới

~~~java
// Dễ làm mất correlation/history nếu tự tạo message từ payload:
Message<String> withoutOriginalHeaders =
        MessageBuilder.withPayload(normalized).build();

// Giữ header nội bộ khi chủ động tạo message mới trong cùng flow:
Message<String> withOriginalHeaders =
        MessageBuilder.withPayload(normalized)
                .copyHeaders(source.getHeaders())
                .build();
~~~

Ví dụ này nhấn mạnh **sự khác biệt về header**. Không copy mù toàn bộ header sang hệ thống khác. `replyChannel`, `errorChannel` hoặc header chứa Java object có thể không serialize được, còn `history` có thể tiết lộ topology nội bộ. Khi qua external adapter, dùng **allowlist và mapping được xác định rõ**.

### 12.3. Header history có thể dài

Nếu mỗi lần retry hoặc vòng lặp định tuyến làm history tăng, header lớn có thể:

- Tăng số byte trong heap, queue hoặc payload mapping.
- Vượt giới hạn header của HTTP/broker hoặc không được converter chấp nhận.
- Gây nhiều log và chi phí telemetry nếu in toàn bộ.
- Rò rỉ tên endpoint, tên hệ thống và chi tiết topology tới đối tác.

Hãy chỉ giữ history trong phạm vi chẩn đoán cần thiết; ở network boundary, thường nên truyền **ID tương quan và trace context**, không truyền toàn bộ lịch sử nội bộ.

## 13. Message ID, Correlation ID và Business ID

Các ID giải quyết những bài toán khác nhau:

| ID | Ý nghĩa | Có thể dùng để nối toàn bộ flow không? |
|---|---|---|
| **MessageHeaders.ID** | Định danh của một instance Spring Message | Không chắc; khi tạo message mới có thể có ID khác |
| **Business ID** | Mã đơn hàng, hợp đồng, batch theo domain | Có ý nghĩa xuyên hệ thống nếu thiết kế ổn định, không thay thế idempotency |
| **Correlation ID** | Nhóm request/reply, splitter/aggregator hoặc transaction logic | Có, khi được propagate nhất quán theo hợp đồng |
| **Trace ID / Span ID** | Mối quan hệ thực thi giữa các operation được instrument | Có, nếu tracing context được propagate đúng |
| **Broker message/record identity** | JMSMessageID, Kafka topic-partition-offset… | Gắn với transport và delivery, không phải business identity |
| **Message history** | Danh sách component path trong Spring Integration | Không phải ID và không đủ làm khóa tương quan |

### 13.1. Thiết kế ID xuyên adapter

Giả sử một đơn hàng đi từ HTTP → Spring Integration → Kafka → service B → JDBC:

~~~text
businessOrderId = ORD-1042
correlationId   = integration-request-79
traceId         = tracing-context-id
messageId(A)    = Spring Message UUID cục bộ A
kafkaIdentity   = topic / partition / offset
messageId(B)    = Spring Message UUID cục bộ B
history(A)      = Các component đi qua ở A
history(B)      = Các component đi qua ở B
~~~

Khi debug, dùng correlation/trace/business ID phù hợp để tìm **hai đoạn history riêng**. Không gán một Message ID của A làm khóa duy nhất cho các message B, C, D nếu không có hợp đồng rõ ràng.

### 13.2. Redelivery và idempotency

Một Kafka/JMS/AMQP message có thể được giao lại. Có thể có nhiều lần xử lý với **cùng business ID** nhưng khác trace/span/Message instance. History không cho biết bản ghi đã commit vào database hay chưa; thiết kế adapter cần **idempotent receiver, transaction/ack phù hợp, deduplication key và retry policy**.

## 14. Request/reply qua gateway và history ở hai chiều

### 14.1. Inbound gateway

Một HTTP inbound gateway thường tạo request message, đi qua business flow và trả reply cho HTTP caller. History của **request** không mặc nhiên cho biết caller đã nhận reply; cần thêm response status/latency và network telemetry.

### 14.2. Outbound gateway

Outbound gateway gửi request tới hệ thống ngoài và có thể nhận reply/exception. Nếu timeout, history tới gateway chỉ chứng minh luồng đã đến điểm gọi, **không chứng minh remote chưa xử lý**. Retry có thể tạo giao dịch lặp nếu không có idempotency key.

### 14.3. Header khác nhau giữa request và reply

Reply message có thể được framework tạo mới, header được copy/mapped theo contract hoặc mất một số trường. Vì vậy nên kiểm tra **cả message trước gateway và reply sau gateway** thay vì kỳ vọng một history duy nhất ghi trọn mọi hoạt động bên ngoài.

~~~mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant G as Inbound Gateway A
    participant Flow as Flow A
    participant B as Service B
    Client->>G: Request + correlation
    G->>Flow: Spring Message request
    Flow->>B: Outbound HTTP request
    Note over G,Flow: History A tích lũy tại các endpoint nội bộ
    B-->>Flow: HTTP response
    Flow-->>G: Reply Message
    G-->>Client: HTTP response
    Note over Flow,B: Cần HTTP logs / trace để biết call và xử lý ở B
~~~

## 15. Điều tra lỗi bằng ErrorMessage và original message

Một endpoint có thể ném exception; tùy cấu hình dispatch, gateway, error channel, error handling và transaction, lỗi có thể được chuyển thành `ErrorMessage`. Khi có original message, history của nó có thể cho biết đường đi **trước khi lỗi**.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.integration.history.MessageHistory;

public void inspectError(Message<?> inbound) {
    if (inbound instanceof ErrorMessage error) {
        Message<?> original = error.getOriginalMessage();
        if (original != null) {
            MessageHistory history = MessageHistory.read(original);
            // Ghi component IDs an toàn, không dump cả payload/headers.
        }
        Throwable failure = error.getPayload();
        // Ghi exception type, error code và correlation ID theo policy.
    }
}
~~~

**Lưu ý:** không phải mọi lỗi đều tạo ErrorMessage, và `originalMessage` có thể vắng mặt. Một lỗi trước khi có Spring Message (ví dụ kết nối SFTP không mở được, HTTP request bị chặn trước gateway) sẽ không có history của message chưa từng được tạo.

### 15.1. Checklist triage lỗi

1. Xác định **vị trí exception**: poller/source, adapter, channel dispatch, transformer, handler, outbound request, broker acknowledgment.
2. Lấy exception type, error code và correlation ID; tránh in credentials trong exception message.
3. Đọc history của **original message khi có**; đối chiếu endpoint cuối với cấu hình flow.
4. Xem hành động của error flow: discard, retry, dead-letter, rollback hay reply lỗi.
5. Kiểm tra **tác dụng phụ đã xảy ra chưa** (file move, HTTP call, DB update, Kafka publish).
6. Nếu retry, kiểm tra idempotency key, version, transaction, ack và cấu hình backoff.
7. Ghi trạng thái **UNKNOWN/RETRYABLE/FAILED/VERIFIED** theo chính sách; không đánh dấu “chưa xử lý” chỉ vì timeout.

### 15.2. History không thay exception stack

History giúp biết **đường đi**, còn stack trace/error classification giải thích **lỗi gì**. Cần ghép hai nguồn, vì endpoint cuối có trong history không nhất thiết chính là nơi code ném exception; có thể là downstream call hoặc asynchronous failure.

## 16. Message history so với Micrometer metrics và tracing

Đây là ba lớp quan sát **bổ sung** chứ không thay thế nhau.

| Tín hiệu | Đại diện cho | Dùng để |
|---|---|---|
| **Message history** | Metadata thành phần trong một Spring Message | Debug đường đi cục bộ qua endpoint |
| **Structured logs** | Sự kiện có timestamp, severity, code, correlation | Tìm hoạt động cụ thể, phân tích lỗi |
| **Metrics** | Counters/timers/gauges đã tổng hợp | Error rate, throughput, queue depth, latency/SLO |
| **Distributed tracing** | Span và trace context của các operation | Phân tích call path, độ trễ xuyên service |
| **Audit events** | Thay đổi/truy cập được ghi có quy tắc retention | Đối soát trách nhiệm, nghiệp vụ và tuân thủ |

### 16.1. Spring Integration management và Micrometer

Spring Integration có khả năng instrument các thành phần tích hợp; tùy version và cấu hình, **Micrometer metrics/Observations** có thể thu thập hoạt động của channel/handler và được xuất sang hệ quan sát như Prometheus/tracing backend. **Không giả định chỉ thêm annotation message history là sẽ tự xuất đầy đủ metrics/traces**.

Khi triển khai, cần xác nhận:

- Dependency/instrumentation được hỗ trợ bởi phiên bản Spring Boot/Spring Integration hiện tại.
- Registry/observation và exporter đã cấu hình đúng.
- Các channel/handler/adapter nào thực sự có metric; không suy rằng mọi adapter đều mặc định có một counter tương đương.
- Sampling và tracing propagation qua HTTP/broker/executor.
- Tag cardinality và quyền truy cập dữ liệu telemetry.

### 16.2. Những metric hữu ích theo đường đi

| Vấn đề | Tín hiệu nên theo dõi |
|---|---|
| Poller chạy nhưng không nhận file | Poll success/empty/error, file age, remote listing count |
| Filter loại nhiều message | Accepted/rejected count theo loại/nguồn hạn chế |
| QueueChannel nghẽn | Queue depth, oldest message age, consumer throughput |
| ExecutorChannel quá tải | Executor active threads, queue size, rejection |
| Outbound HTTP timeout | Request count, latency distribution, status/error rate |
| Kafka consumer tụt lại | Consumer lag, offset processing, rebalance, DLQ count |
| JMS/AMQP redelivery | Redelivery count, ack/nack/requeue và DLQ metrics |
| SFTP thường xuyên mất kết nối | Session open failures, transfer retry, remote latency |
| JDBC poll trùng lặp | Poll watermark, rows selected/processed, transaction failures |

History chỉ giúp đặt câu hỏi “nó đi tới handler nào?”; metrics/tracing giúp trả lời “đi mất bao lâu?” và “hỏng ở tỷ lệ bao nhiêu?”.

## 17. Thiết kế log an toàn với history

### 17.1. Logging structured thay vì in toàn bộ Message

Một log dễ phân tích nên có:

~~~json
{
  "event": "INTEGRATION_MESSAGE_CHECKPOINT",
  "flow": "sftp-orders-to-kafka",
  "endpoint": "normalizeOrder",
  "correlation_ref": "corr-2048",
  "business_ref": "order-batch-71",
  "message_ref": "local-message-id",
  "history_component_count": 4,
  "history_last_component": "normalizeOrder",
  "outcome": "PROCESSED"
}
~~~

Đây là **cấu trúc log minh họa do ứng dụng tự tạo**, không phải output tự động hoặc tên field mặc định của Spring Integration. Ưu tiên **mã tham chiếu không nhạy cảm** và chỉ các thành phần cần thiết; không log payload đơn hàng, URL có token hoặc toàn bộ MessageHeaders.

### 17.2. Những dữ liệu không nên đưa vào log/history xuất ngoài

- Password, API key, OAuth tokens, private key, Authorization header, cookie.
- PII trong payload, body HTTP hoặc tên file nhạy cảm.
- Full remote path chứa username/tenant bí mật hoặc network topology.
- Nội dung raw SAML assertion/JWT, secret manager path nhạy cảm.
- Query database chứa dữ liệu cá nhân, dữ liệu khách hàng hoặc thông tin thanh toán.

### 17.3. Correlation trong log và MDC

MDC có thể gắn `correlationId`/`traceId` vào log của một thread, nhưng ở `ExecutorChannel`, reactive bridge hoặc polling task, MDC **không tự đồng bộ sang mọi thread**. Dùng context-propagation được hỗ trợ và kiểm thử. Message header là metadata trong message; MDC là ngữ cảnh thread/logging: hai cơ chế không giống nhau.

## 18. Kiểm thử MessageHistory có chủ đích

### 18.1. Test mục tiêu

Một bài test tốt phải xác minh:

1. Message đi qua flow thành công thì history được đọc được tại checkpoint đã định.
2. Tên endpoint được chỉ định tường minh có thể được tìm thấy khi endpoint đó hỗ trợ ghi history trong version test.
3. Nhánh filter bị loại **không tới** outbound handler không phù hợp.
4. Router chọn đúng destination; không suy mọi nhánh đều chạy.
5. Khi custom transformer tạo message mới, các header được chủ đích giữ hoặc loại.
6. Với asynchronous boundary, correlation header vẫn đúng và log context được propagate nếu đã thiết kế.
7. Khi lỗi, original message hoặc checkpoint trước lỗi còn đủ metadata để điều tra.
8. Khi qua broker/HTTP, chỉ các header **được allowlist** và trace context được gửi theo contract.

### 18.2. Phương pháp test trong môi trường nhỏ

~~~text
Given: @EnableMessageHistory và flow có endpoint id "normalizeFilename"
When : Gửi message "  invoice.csv  " vào input channel
Then : Consumer nhận payload "invoice.csv"
And  : MessageHistory.read(message) tồn tại tại checkpoint cuối
And  : Có dấu hiệu đi qua normalizeFilename theo version đang chạy
And  : Không có credential/payload nhạy cảm được ghi log
~~~

Đây là **test specification**, không phải đoạn mã JUnit đã được chạy. Để tránh assertion mong manh, tập trung vào endpoint được đặt ID rõ ràng và behavior nghiệp vụ, không khóa cứng mọi entry history sinh tự động bởi framework.

### 18.3. Ma trận các nhánh cần kiểm tra

| Case | Input | Kết quả mong đợi | Quan sát |
|---|---|---|---|
| Happy path | Payload hợp lệ | Đến outbound adapter | History checkpoint và success metric |
| Filter reject | Sai schema/định dạng | Không gửi downstream | Discard counter + reason |
| Router branch A | Loại A | Chỉ handler A | Path/branch log |
| Router branch B | Loại B | Chỉ handler B | Path/branch log |
| Handler throws | Lỗi do xử lý | Error flow theo config | ErrorMessage/original + exception |
| Gateway timeout | Remote không reply | Timeout/retry theo policy | History tới gateway + outbound latency |
| Async | Nhiều message đồng thời | Không trộn correlation | Trace/MDC propagation + per-message history |
| Split/aggregate | Batch nhiều item | Gom nhóm đúng | Per-item correlation, không suy từ result history |
| Broker redelivery | Cùng record giao lại | Idempotency đúng | Offset/delivery attempts và audit |

## 19. Quy trình chẩn đoán khi history bị trống hoặc thiếu endpoint

### SOP-HIST-01

**Tín hiệu:** một message đến service activator nhưng không có `history`, danh sách bị cụt hoặc không thấy endpoint kỳ vọng.

1. **Xác minh cấu hình:** annotation hoặc XML message history có thực sự được load trong đúng ApplicationContext?
2. **Xác định checkpoint:** đọc message trước hay sau endpoint, có handler nào đã nhận được message chưa?
3. **Kiểm tra flow path:** filter/router có thực sự chọn nhánh cần quan sát không?
4. **Soát custom Message creation:** dùng `MessageBuilder.withPayload(...)` mà không copy header?
5. **Soát header mapper/filter:** adapter HTTP/JMS/AMQP/Kafka hoặc converter có loại header không?
6. **Kiểm tra process boundary:** message đến từ broker được tạo mới; history local của producer có được truyền hay cố ý loại?
7. **Kiểm tra endpoint ID:** tên được sinh tự động có khác dự kiến khi build/refactor không?
8. **Kiểm tra async/race:** log của các worker có bị ghép sai correlation hay đang đọc message khác không?
9. **Xác minh version/capability:** endpoint/adapter có thực sự bổ sung history trong phiên bản đó?
10. **Thử lại trên một flow tối giản** với history bật, endpoint ID tường minh và một consumer đọc `MessageHistory.read`.

**Không sửa nhanh bằng cách tự nhét một header tên `history` chứa chuỗi bất kỳ**, vì có thể làm sai định dạng framework và tạo phụ thuộc nghiệp vụ không kiểm soát.

### 19.1. Khi history dài nhưng không biết lỗi

History không chứa exception nguyên nhân. Chuyển sang error flow, stack trace, business error code, broker offsets, HTTP status/latency hoặc database transaction logs. Đừng đọc đường đi dài rồi gán nguyên nhân cho “endpoint cuối cùng” nếu chưa kiểm chứng.

## 20. Hiệu năng, kích thước header và tính sẵn sàng

### 20.1. Chi phí vận hành có thể phát sinh

- **CPU/GC:** thêm metadata ở mỗi hop trong luồng có throughput cao.
- **Memory:** history dài hơn khi message đi qua nhiều endpoint; fan-out tạo nhiều bản message có header.
- **Serialization:** header lớn và Java-specific type không thích hợp khi chuyển qua mạng.
- **Logging:** in full history ở mọi message tạo số lượng log lớn và phí lưu trữ cao.
- **Rủi ro chính sách:** topology, identifier nội bộ có thể lọt ra ngoài qua mapping thiếu kiểm soát.

Không có một con số overhead cố định; cần đo trong workload thật hoặc load test đại diện.

### 20.2. Cách giữ chi phí phù hợp

1. Bật history có chủ đích cho môi trường/lưu lượng cần điều tra; đánh giá trước khi mở production diện rộng.
2. Dùng endpoint IDs ngắn, ổn định; không gắn payload hay thông tin định danh riêng vào component name.
3. Tránh dump full `Message<?>` hoặc toàn bộ history trong hot path.
4. Ở gateway/adapter ra ngoài, chỉ propagate header allowlist.
5. Lưu metrics/trace sampled và business audit ở hệ chuyên dụng, không thay chúng bằng header history ngày càng dài.
6. Theo dõi memory, queue depth, broker header limit, latency và error rate trước/sau khi bật.
7. Với retry/DLQ, áp chính sách về retention, max attempts, correlation và không giữ mãi các dữ liệu không cần thiết.
8. Khi tắt history ở production, giữ đường chẩn đoán thay thế bằng correlation ID + structured log + metrics/tracing.

## 21. Bảo mật và tính tin cậy của history

### 21.1. Header history là dữ liệu chẩn đoán, không phải quyền

Không sử dụng tên endpoint trong history để **xác thực người dùng, chấp nhận message, quyết định thanh toán hay cho phép truy cập**. Một message đến từ hệ thống khác có thể mang header do phía gửi kiểm soát; nếu bạn tin header đó như audit bằng chứng, đối tác hoặc tác nhân bên ngoài có thể giả mạo “đã đi qua validatePayment”.

**Các quyết định nghiệp vụ cần dựa vào dữ liệu đã xác minh, policy, authz và state lưu trữ**, không dựa vào header path không được xác thực.

### 21.2. Không xuất toàn bộ topology nội bộ

History có thể tiết lộ tên handler, môi trường, hệ thống, nhánh xử lý hoặc thư viện. Trước khi gửi HTTP response/broker record hoặc log ra hệ ngoài, xác định rõ những header được phép xuất. Không copy `history` chỉ để “dễ debug” nếu chưa có yêu cầu hợp đồng và bảo vệ phù hợp.

### 21.3. Privacy by design

- Đặt retention cho logs/trace theo chính sách.
- Giới hạn người đọc telemetry và evidence.
- Hash hoặc dùng opaque reference cho business ID nhạy cảm khi cần.
- Không lưu raw token/credential; kiểm tra exception serializer có log body/payload vô tình không.
- Phân biệt logs phục vụ hỗ trợ với audit evidence cần lưu và bảo vệ độc lập.

## 22. Tình huống thực hành tổng hợp

### Tình huống A — File inbound thành công nhưng Kafka chưa nhận record

Luồng `fileInbound → validate → transform → kafkaOutbound`. Message tới transform, nhưng downstream consumer chưa thấy event.

**Hướng điều tra:** đọc history ở checkpoint sau transform, xác minh đã tới outbound handler chưa. Kiểm tra Kafka producer callback, broker ack, partition/topic, serialization, retry và DLQ. History tới `kafkaOutbound` **không chứng minh broker đã nhận và commit**. Dùng producer metrics/log với correlation và business ID.

### Tình huống B — SFTP poller im lặng

Dashboard cho thấy không có message history trong 20 phút, trong khi remote directory có file mới.

**Hướng điều tra:** không kết luận history bị hỏng. Kiểm tra poller schedule, session factory, remote listing, authentication, file filter, quyền đọc và lỗi tạo message. Nếu adapter chưa phát message thì không có history. Theo dõi poll success/error và tuổi file.

### Tình huống C — Router chuyển dữ liệu sang nhánh sai

Order loại ưu tiên đi sang `normalHandler` thay vì `priorityHandler`. History thấy router và handler normal.

**Hướng điều tra:** history hỗ trợ xác nhận **đường thực tế**. Đọc routing key/headers và rule mapping bằng log an toàn, kiểm tra transform có đổi thuộc tính không; không sửa handler B nếu root cause là router expression.

### Tình huống D — HTTP outbound timeout rồi tạo giao dịch trùng

Outbound gateway gọi service thanh toán; request timeout. Retry khiến hai giao dịch.

**Hướng điều tra:** history chỉ cho thấy flow tới gateway, không biết remote đã commit chưa. Đối chiếu traceId, idempotency key, remote audit, response/timeout, DB transaction. Thiết kế retry idempotent và reconciliation theo business ID.

### Tình huống E — JMS redelivery nhưng history không nối được hai lần

JMS consumer xử lý message, rollback, broker giao lại. History ở lần hai không giống lần một.

**Hướng điều tra:** đây có thể là message Java mới từ cùng broker delivery logic. Dùng JMS headers, correlation, redelivery count, transaction và DLQ; không dựa vào history list để suy exactly-once.

### Tình huống F — Splitter xử lý 100 item, aggregator thiếu một item

Result history ở aggregator không cho biết item nào lỗi.

**Hướng điều tra:** theo correlation/sequence item ID, per-item success/failure, completion strategy, timeout và discard/error channels. Không kỳ vọng một history cuối chứa đủ 100 item paths.

### Tình huống G — ExecutorChannel mất MDC nhưng history vẫn có

Log downstream mất correlation ID, trong khi `MessageHistory.read` vẫn đọc được component path.

**Hướng điều tra:** header trong message được chuyển, nhưng MDC là thread-local. Kiểm tra context propagation của executor và logging instrumentation; không thêm cơ chế đọc history làm giải pháp thay thế tracing.

### Tình huống H — Message tạo mới làm mất history

Custom transformer dựng `MessageBuilder.withPayload(newPayload).build()`; service activator không thấy history dù upstream đã bật.

**Hướng điều tra:** sửa chính sách header propagation trong same-process flow, dùng copy headers phù hợp và bổ sung test. Qua network boundary, không copy toàn bộ mà chọn header công khai/correlation đã duyệt.

### Tình huống I — Kafka consumer thiếu dấu vết service upstream

Service A publish Kafka, service B xử lý. History của B bắt đầu từ inbound adapter B, không chứa transformer A.

**Hướng điều tra:** đây không nhất thiết là bug. Dùng trace context/opaque correlation ID qua header mapper, mở trace/log hai service để nối tuyến. History A và B là **hai đoạn cục bộ**, không yêu cầu sao chép nguyên `history` qua broker.

### Tình huống J — Header history bị xuất ra HTTP response

Một gateway cấu hình copy toàn bộ header khiến client ngoài nhận chuỗi tên endpoint nội bộ.

**Hướng xử lý:** điều chỉnh allowlist/response header mapping, không xuất topology hoặc runtime headers ra ngoài; rà nơi log/tài liệu chứa thông tin đã xuất, thêm test contract và security check.

## 23. Checklist triển khai và vận hành

| Giai đoạn | Câu hỏi nghiệm thu |
|---|---|
| **Enablement** | `@EnableMessageHistory` hoặc XML đã được load đúng context? |
| **Endpoint naming** | Các endpoint quan trọng có ID ổn định và dễ hiểu? |
| **Checkpoint** | Đã chọn chỗ đọc `MessageHistory.read` trước/sau endpoint đúng? |
| **Flow coverage** | Có test happy path, filter reject, router branch và error flow? |
| **Async** | Queue/executor/pub-sub có correlation, metric và trace propagation phù hợp? |
| **Poller** | Có phân biệt poll rỗng, poll fail và message processing failure? |
| **Gateway** | Có kiểm tra request/reply và remote outcome riêng với history? |
| **Broker** | Có offset/ack/redelivery/DLQ/idempotency, không dựa vào history để xác nhận commit? |
| **Header mapping** | Có allowlist khi gửi HTTP/JMS/AMQP/Kafka, tránh leak history nội bộ? |
| **Exception** | Có error logs và original message khi framework cung cấp? |
| **Performance** | Header size, heap/GC, latency và log volume đã được đánh giá? |
| **Security** | Không log token/payload nhạy cảm, không dùng history làm authorization/audit proof? |
| **Operations** | Có correlation ID, metrics, tracing và runbook hỗ trợ khi history tắt? |

## 24. Kết luận

**Message history qua các endpoint** là một công cụ chẩn đoán hữu ích trong Spring Integration: khi được bật, metadata tích lũy giúp người vận hành biết message đã đi qua những thành phần được ghi nhận, nhất là trong flow có filter, router, transformer, splitter/aggregator và nhiều loại adapter. Tên endpoint ổn định, checkpoint phù hợp và kiểm thử các nhánh thực tế là chìa khóa để history mang giá trị.

Tuy nhiên, history **không thay thế** metrics đo throughput/latency, distributed tracing nối các service, log ghi lỗi, cơ chế idempotency/transaction của broker hay audit nghiệp vụ. Các ranh giới mới tạo message, gateway, serialization và xử lý bất đồng bộ có thể thay đổi hoặc loại bỏ header. Trong module **Spring Integration Adapters**, cách làm bền vững là kết hợp **MessageHistory cục bộ + correlation/trace context xuyên hệ thống + log/metrics/kiểm chứng kết quả tại đích**, đồng thời bảo vệ dữ liệu, giới hạn header và xử lý rõ vòng đời kết nối, retry và lỗi của từng adapter.
