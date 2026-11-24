# Polling Consumer Pattern trong Spring Integration Adapters

> **Chương:** Design patterns  
> **Chủ đề:** Polling consumer pattern  
> **Phạm vi module:** Kết nối hệ thống ngoài với **Spring Integration** bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; minh họa với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Trọng tâm là **cách chủ động lấy dữ liệu theo nhịp**, hợp đồng message, xử lý lỗi, điều tiết tải và vòng đời kết nối.

## 1. Mục tiêu bài học

Sau bài này, người học có thể:

1. Giải thích **Polling Consumer** là gì, khi nào dùng polling thay vì cơ chế đẩy sự kiện (*message-driven/push*).
2. Phân biệt chính xác **`PollingConsumer` đọc `PollableChannel`** và **`SourcePollingChannelAdapter` đọc `MessageSource`** trong Spring Integration.
3. Thiết lập poller bằng Java DSL hoặc annotation, hiểu tác dụng của `fixedDelay`, `fixedRate`, cron, `maxMessagesPerPoll` và thời gian chờ nhận message.
4. Thiết kế luồng đọc file/SFTP/JDBC và xác định trách nhiệm của inbound adapter, `MessageChannel`, handler và outbound adapter.
5. Quản lý dữ liệu trùng, message đang ghi dở, retry, giao dịch, acknowledgment, lỗi tạm thời và backpressure.
6. Chọn chiến lược triển khai nhiều instance mà không tự giả định “poll mỗi bản ghi đúng một lần”.
7. Đọc chỉ số, viết kiểm thử và giải thích giới hạn của một thiết kế polling trước khi đưa vào production.

**Câu hỏi xuyên suốt:** *Khi nguồn dữ liệu không chủ động gửi message đến ứng dụng, làm sao lấy đúng dữ liệu vào đúng lúc, không lấy trùng ngoài ý muốn, không bỏ sót và không làm quá tải hệ thống?*

## 2. Polling Consumer là gì?

**Polling Consumer** là mẫu tích hợp trong đó bên nhận **chủ động kiểm tra** nguồn hoặc hàng đợi theo lịch hoặc tín hiệu kích hoạt, rồi nhận tối đa một hoặc nhiều message khả dụng. Nó đối lập với cơ chế **Event-Driven Consumer**, trong đó phía nguồn, broker hoặc runtime chủ động thông báo/đẩy dữ liệu khi có.

Ví dụ một hệ thống đối tác chỉ tải tệp CSV lên thư mục SFTP mỗi vài phút. Đối tác không cung cấp webhook; ứng dụng cần định kỳ liệt kê thư mục và tải các tệp mới:

~~~text
09:00:00  Poll SFTP: chưa có file
09:00:05  Poll SFTP: chưa có file
09:00:10  Poll SFTP: có orders-001.csv
09:00:10  Adapter tạo Message<File> / nội dung file
09:00:10  Channel chuyển tới handler kiểm tra và xử lý
09:00:15  Poll tiếp: không xử lý lại file cũ nếu bộ lọc/metadata hoạt động
~~~

Polling không nhất thiết “bận chờ liên tục”. Với lịch cố định, scheduler chỉ kích hoạt vào các mốc hoặc sau một khoảng chờ. Mỗi lượt poll phải quyết định **có dữ liệu không**, **lấy tối đa bao nhiêu**, **nếu lỗi thì làm gì**, và **khi nào lượt sau được phép chạy**.

### 2.1. Khi nào nên chọn polling?

| Bối cảnh | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Thư mục file local có tệp được đẩy định kỳ | File inbound adapter + poller hoặc cơ chế theo dõi được hỗ trợ | File system không cung cấp hàng đợi thông điệp chuẩn với ack |
| SFTP đối tác chỉ cho liệt kê/tải file | SFTP inbound/streaming adapter + poller | Bên nhận phải chủ động kết nối và tìm file |
| Bảng database chứa bản ghi chờ xử lý | JDBC/message source polling với cơ chế claim | Không có broker; trạng thái nằm ở DB |
| API HTTP chỉ có `GET /changes` | Poll HTTP có cursor/ETag/rate limit | Không có webhook, SSE hoặc stream |
| JMS/AMQP broker hỗ trợ listener | Thường xem xét message-driven adapter | Broker có cơ chế nhận/ack; polling không luôn là lựa chọn tối ưu |
| Kafka topic có consumer group | Thường sử dụng Kafka listener/message-driven adapter | Client Kafka vẫn dùng poll bên trong, nhưng Spring Integration có abstraction listener riêng |
| Một `QueueChannel` nội bộ cần tiêu thụ theo lịch | `PollingConsumer` | Kênh hỗ trợ `receive()`; handler được kích hoạt theo poller |

**Không suy ra:** vì client Kafka có phương thức `poll()` nên mọi luồng Kafka trong Spring Integration là `PollingConsumer` endpoint. Phải phân biệt cơ chế poll nội bộ của client/broker với **kiểu endpoint Spring Integration** do ứng dụng cấu hình.

### 2.2. Điểm mạnh và chi phí

**Ưu điểm:**

- Kiểm soát được nhịp đọc, số lượng message mỗi lượt và cửa sổ vận hành.
- Có thể tích hợp hệ thống chỉ hỗ trợ đọc chủ động, không có cơ chế push.
- Có nơi để tổ chức timeout, retry, giao dịch và điều tiết khi đích xử lý chậm.
- Có thể điều chỉnh mức tiêu thụ mà không phải thay đổi hệ thống nguồn.

**Đánh đổi:**

- Có độ trễ phát hiện dữ liệu, thường phụ thuộc khoảng giữa các lượt poll.
- Poll rỗng quá dày gây I/O, kết nối và tải không cần thiết.
- Một lượt poll lâu hoặc xử lý chậm có thể gây backlog, lệch lịch hoặc chồng lấn nếu cấu hình concurrency không phù hợp.
- Không tự có bảo đảm *exactly-once end-to-end*; xử lý trùng/mất cần thiết kế nguồn, acknowledgment, giao dịch và idempotency.
- Nhiều instance đồng thời có thể cùng thấy một dữ liệu nếu không có lock/claim/metadata dùng chung.

## 3. Vị trí của Polling Consumer trong Enterprise Integration Patterns

~~~mermaid
flowchart LR
    A["Nguồn ngoài: File / SFTP / DB / HTTP"] -->|Có dữ liệu khi được hỏi| SRC["MessageSource"]
    TR["Scheduler + Trigger + Poller"] --> SPA["SourcePollingChannelAdapter"]
    SRC --> SPA
    SPA --> CH["MessageChannel"]
    CH --> HANDLER["Filter / Transformer / Service Activator"]
    HANDLER --> OUT["Outbound Adapter / Gateway"]
    OUT --> DEST["Hệ đích"]
~~~

Ở cấp độ khái niệm, bên tiêu thụ có một lịch kích hoạt và một thao tác nhận. Nhưng **Spring Integration dùng hai loại polling endpoint đáng phân biệt**.

### 3.1. Hai trường hợp khác nhau trong Spring Integration

| Trường hợp | Nguồn được poll | Endpoint Spring Integration | Ví dụ |
| --- | --- | --- | --- |
| **Poll dữ liệu ngoài** | `MessageSource.receive()` | **`SourcePollingChannelAdapter`** | Đọc file, tìm bản ghi DB, lấy dữ liệu từ nguồn remote |
| **Poll message đã ở trong channel** | `PollableChannel.receive(timeout)` | **`PollingConsumer`** | `QueueChannel` → service activator theo lịch |

Hai endpoint cùng dùng cơ chế **poller/trigger**; chúng giải quyết hai điểm nhận dữ liệu khác nhau. Nếu gọi mọi inbound adapter poll là lớp `PollingConsumer`, việc đọc log, cấu hình và chẩn đoán sẽ dễ sai.

~~~mermaid
flowchart TB
    subgraph ExternalSource["Nhánh A: poll nguồn ngoài"]
        FS["File / SFTP / JDBC MessageSource"] --> SPA["SourcePollingChannelAdapter"]
        SPA --> DC["DirectChannel / QueueChannel"]
    end
    subgraph ChannelConsume["Nhánh B: poll channel"]
        PRODUCER["Producer / Flow trước"] --> Q["QueueChannel (PollableChannel)"]
        Q --> PC["PollingConsumer"]
        PC --> H["MessageHandler"]
    end
    SCHED["TaskScheduler + Poller"] -.-> SPA
    SCHED -.-> PC
    DC --> DOWN["Luồng xử lý tiếp"]
~~~

### 3.2. `PollableChannel` và `SubscribableChannel`

| Kiểu channel | Cách tiêu thụ | Ví dụ Spring Integration | Ghi chú |
| --- | --- | --- | --- |
| **`PollableChannel`** | Consumer gọi `receive()` để lấy message | `QueueChannel`, `PriorityChannel` | Message có thể chờ trong channel; cần poller cho endpoint tiêu thụ |
| **`SubscribableChannel`** | Handler được đăng ký để nhận message khi channel được gửi đến | `DirectChannel`, `PublishSubscribeChannel` | Không dùng `PollingConsumer` để gọi `receive()` trên `DirectChannel` |
| **Channel có dispatch bất đồng bộ** | Subscriber được dispatch qua executor | `ExecutorChannel` | Bất đồng bộ không đồng nghĩa channel trở thành pollable |

`QueueChannel` chứa message và hỗ trợ nhận theo thao tác pull. `DirectChannel` thường chuyển message trực tiếp tới handler trong luồng gọi gửi. Dùng `QueueChannel` để đệm có thể giúp tách tốc độ producer và consumer, nhưng cần **giới hạn dung lượng** và hiểu hành vi khi đầy; bản thân kênh này không mặc định là một kho hàng đợi bền vững sau khi process chết.

### 3.3. Adapter, gateway và handler khác nhau

**Inbound channel adapter** đưa dữ liệu từ hệ thống ngoài thành Spring `Message` rồi gửi vào channel. **Outbound channel adapter** nhận message trong flow và thực hiện side effect bên ngoài; thông thường không mong đợi reply. **Gateway** mô hình hóa giao tiếp request/reply và có thể đợi kết quả. **Service activator** gọi nghiệp vụ khi nhận message. **Poller** là cơ chế kích hoạt một endpoint đọc dữ liệu, không phải kênh hoặc giao thức vận chuyển mới.

## 4. Thành phần cấu hình poller

Một lượt poll bao gồm: **trigger → lấy tối đa N message → chuyển/xử lý → ghi nhận kết quả hoặc lỗi → chờ lượt tiếp theo**. Có thể cấu hình poller bằng Java DSL, annotation, XML hay bean tùy phong cách dự án.

| Tham số/khái niệm | Tác dụng | Điều cần kiểm tra |
| --- | --- | --- |
| **fixedDelay** | Đặt khoảng chờ giữa các lần kích hoạt sau khi lượt trước kết thúc theo cơ chế scheduler | Không tạo vòng hỏi liên tục khi nguồn rỗng; có độ trễ khi dữ liệu đến |
| **fixedRate** | Lập lịch theo nhịp thời gian tương đối đều | Nếu công việc dài hơn chu kỳ, cần hiểu scheduler/executor và nguy cơ chồng lấn |
| **cron** | Poll theo cửa sổ lịch, ví dụ giờ làm việc hoặc batch ban đêm | Múi giờ, DST nếu có, missed execution khi service dừng |
| **maxMessagesPerPoll** | Giới hạn số message nhận/xử lý trong một lượt poll | Kích thước batch, mức tải, thời gian chiếm scheduler |
| **receiveTimeout** | Thời gian chờ khi poll từ một `PollableChannel` có hỗ trợ đợi | Không nhầm với timeout mạng SFTP/HTTP hoặc timeout xử lý handler |
| **TaskScheduler** | Kích hoạt công việc theo trigger | Pool size, chạy đồng thời, shutdown, xử lý lỗi |
| **TaskExecutor** | Có thể tách lịch kích hoạt khỏi công việc tùy cấu hình | Threading, thứ tự message, giao dịch và thread-bound context |
| **Transaction advice** | Bao các thao tác phù hợp trong giao dịch nếu source/handler hỗ trợ | Biên giao dịch không mặc định bao trùm nhiều hệ ngoài |
| **Advice/error handling** | Retry, quan sát, xử lý lỗi tại poll/handler | Phân biệt lỗi tạm thời và lỗi dữ liệu, tránh retry vô hạn |

### 4.1. Fixed delay và fixed rate

Giả sử xử lý một lượt poll mất 4 giây:

~~~text
fixedDelay = 5 giây
  Poll 1 bắt đầu t=0, kết thúc t=4
  Poll 2 có thể bắt đầu khoảng t=9 (sau khi chờ 5 giây)

fixedRate = 5 giây
  Mốc dự kiến t=0, t=5, t=10...
  Lịch thực thi phụ thuộc scheduler và thời gian chạy;
  không được mặc định mọi lần luôn bắt đầu đúng mốc hay luôn chạy song song.
~~~

Với việc tải file hoặc gọi API chậm, `fixedDelay` thường dễ dự đoán mức tải hơn. `fixedRate` hữu ích khi cần nhịp đều nhưng phải đánh giá việc kéo dài công việc và cấu hình executor. Không coi cron là biện pháp bảo đảm message không trùng hoặc không bị bỏ sót.

### 4.2. `maxMessagesPerPoll` không phải kích thước message

Nếu poller đặt `maxMessagesPerPoll(10)`, có thể lấy tối đa 10 message trong một lượt kích hoạt, nhưng không có nghĩa:

- Mọi lượt đều có đủ 10 message.
- Mỗi message là một bản ghi nghiệp vụ (một file có thể chứa hàng nghìn bản ghi).
- Source hỗ trợ nhận 10 bản ghi trong một truy vấn mạng.
- Có 10 message thì sẽ chạy song song 10 handler.

**Đơn vị batch thực tế** phụ thuộc adapter: file, hàng DB, một trang HTTP, một message trong channel hoặc một record/event. Nếu nguồn rỗng, `receive()` có thể trả `null` và lượt poll kết thúc.

### 4.3. `receiveTimeout` khác timeout kết nối

Với `QueueChannel`, `receive(timeout)` có thể đợi đến khi message xuất hiện hoặc hết thời gian. Nhưng khi poll file/SFTP/HTTP, adapter còn có các timeout **kết nối**, **đọc socket**, **session**, **response** riêng. Điều chỉnh `receiveTimeout` của consumer không tự sửa lỗi SFTP connect timeout.

### 4.4. Lập kế hoạch dung lượng sơ bộ

Gọi `R` là số message nhận mỗi lượt, `P` là số lượt poll hoàn tất trung bình trong một giây và `T` là thông lượng xử lý thực tế. Khi có tải:

~~~text
T <= R × P
T <= năng lực xử lý của handler và hệ đích
~~~

Đây là **giới hạn lý thuyết minh họa**, chưa tính poll rỗng, timeout, lỗi, lock, xử lý song song hay ràng buộc broker. Nếu nguồn tạo 200 message/giây nhưng flow thực tế chỉ xử lý 100 message/giây, backlog tăng dù tăng số lần poll có vẻ làm flow hoạt động nhiều hơn. Cần đo end-to-end và xử lý nguyên nhân nghẽn.

## 5. Message contract và đường đi dữ liệu

Spring Integration truyền dữ liệu qua `org.springframework.messaging.Message<T>`, gồm **payload** và **headers**. Payload có thể là `File`, `String`, `byte[]`, DTO, record từ database hoặc đối tượng của adapter; headers mang metadata như ID, timestamp, thông tin file, correlation hoặc trace.

### 5.1. Checklist hợp đồng message

- [ ] Định nghĩa rõ kiểu payload trước/sau transformation, encoding, schema và trường bắt buộc.
- [ ] Xác định các header từ adapter là đáng tin đến mức nào; dữ liệu ngoài không được dùng làm quyền truy cập nội bộ nếu chưa xác minh.
- [ ] Có **business key/idempotency key** ổn định ngoài message ID được runtime tự sinh.
- [ ] Biết message tương ứng một file, một hàng dữ liệu hay cả batch; giữ correlation ID khi tách/gộp.
- [ ] Có cách phân loại lỗi chuyển đổi dữ liệu, lỗi nguồn và lỗi hệ đích.
- [ ] Tách metadata cần cho kiểm toán khỏi credential như access token hoặc mật khẩu.
- [ ] Có hợp đồng cho trạng thái thành công: đã nhận, đã parse, đã ghi DB hay đã gửi ra đích?

### 5.2. Ví dụ các bước xử lý file

~~~mermaid
sequenceDiagram
    participant S as Scheduler/Poller
    participant F as File MessageSource
    participant A as Inbound Adapter
    participant C as MessageChannel
    participant H as Handler
    participant DB as Database
    S->>A: Kích hoạt lượt poll
    A->>F: receive()
    F-->>A: File mới hoặc null
    A->>C: send(Message<File>)
    C->>H: Chuyển message
    H->>H: Validate, parse, idempotency
    H->>DB: Lưu kết quả
    DB-->>H: Commit/ACK phù hợp
    H-->>A: Hoàn tất hoặc ném lỗi
~~~

Tùy channel, việc gọi handler có thể đồng bộ hoặc bất đồng bộ. Vì vậy **“send thành công” không luôn bằng “nghiệp vụ đã commit”**. Chọn điểm ghi nhận hoàn tất thích hợp, đặc biệt trước khi di chuyển/xóa file nguồn hoặc xác nhận message cho broker.

## 6. Ví dụ Spring Integration Java DSL: poll file

Ví dụ sau minh họa một **inbound channel adapter** đọc những file CSV trong thư mục và chuyển message vào handler. Đây là nhánh **poll MessageSource**, tức runtime sử dụng `SourcePollingChannelAdapter`. Mã minh họa phong cách Spring Integration 6.x; khi áp dụng, kiểm tra API đúng với phiên bản Spring Boot/Spring Integration đang dùng.

### 6.1. Cấu hình đơn giản

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class FilePollingFlow {

    @Bean
    public IntegrationFlow readCsvFiles() {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(new File("./lab/in"))
                         .autoCreateDirectory(true)
                         .patternFilter("*.csv"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofSeconds(3))
                               .maxMessagesPerPoll(5)
                    )
                )
                .handle((MessageHandler) message -> {
                    File file = (File) message.getPayload();
                    System.out.println("Found file: " + file.getName());
                    // Trong dự án thật: validate, parse, idempotency,
                    // ghi nhận kết quả và quản lý trạng thái file.
                })
                .get();
    }
}
~~~

Ý nghĩa:

1. `Files.inboundAdapter(...)` mô tả nguồn file được đọc; bản thân nó không tự biến thành một scheduler riêng do ứng dụng tự viết.
2. `endpoint.poller(...)` tạo lịch poll cho **source polling endpoint**.
3. `fixedDelay(Duration.ofSeconds(3))` lên lịch giữa các lượt kích hoạt.
4. `maxMessagesPerPoll(5)` giới hạn số lần nhận message trong một lượt poll.
5. Handler ở ví dụ chỉ in tên file; **in ra console không đồng nghĩa file đã xử lý bền vững**.

**Quan trọng về file filter:** file đã đọc có bị nhận lại không phụ thuộc cấu hình file inbound source/filter và khả năng lưu metadata. Khi yêu cầu tránh xử lý lại qua restart, hãy sử dụng **bộ lọc accept-once có trạng thái bền vững** và/hoặc idempotency ở nghiệp vụ; không giả định bộ lọc trong bộ nhớ bảo vệ được sau khi ứng dụng chết.

### 6.2. Vì sao cần quy ước file đã ghi xong?

Một inbound adapter có thể thấy file **ngay khi bên ngoài bắt đầu ghi**. Nếu đọc tệp chưa hoàn tất, parse CSV có thể lỗi hoặc tạo dữ liệu thiếu.

Quy ước giao file gợi ý:

~~~text
Đối tác ghi tạm:
  orders-2026-11-23.csv.uploading

Khi hoàn thành:
  đổi tên nguyên tử (nếu cùng filesystem và được hỗ trợ)
  orders-2026-11-23.csv

Poller chỉ chọn *.csv
  → nhận file đã công bố hoàn tất
~~~

Không phải mọi remote filesystem hoặc SFTP server đều bảo đảm thao tác rename nguyên tử theo cách bạn cần. Có thể kết hợp thư mục staging, manifest/marker file, kiểm tra kích thước ổn định hoặc last-modified age. Cần thỏa thuận **hợp đồng producer/consumer** rõ ràng, không chỉ dựa vào `patternFilter("*.csv")`.

### 6.3. Xử lý file đã nhận thành công

Một chiến lược thường dùng:

~~~mermaid
flowchart TD
    POLL["Poll chọn file mới"] --> READY{"File hoàn tất và chưa xử lý?"}
    READY -->|Không| SKIP["Bỏ qua tới lượt khác"]
    READY -->|Có| CLAIM["Claim/đánh dấu đang xử lý nếu hỗ trợ"]
    CLAIM --> PARSE["Đọc + validate + parse"]
    PARSE --> SAVE["Ghi nghiệp vụ có idempotency"]
    SAVE --> SUCCESS{"Commit thành công?"}
    SUCCESS -->|Có| ARCH["Move/mark processed, lưu audit"]
    SUCCESS -->|Không| RETRY["Giữ có kiểm soát để retry hoặc quarantine"]
~~~

**Đừng xóa/di chuyển file ngay khi nhận message** nếu nghiệp vụ phía sau chưa commit. Với các flow có nhiều bước bất đồng bộ, cần có trạng thái bền vững hoặc điểm ack/mark riêng; chỉ xử lý tên file không đủ để chứng minh file đã được nhập thành công.

### 6.4. Cách tổ chức luồng khi handler chậm

Ban đầu nên dùng một luồng đơn giản **source → channel → handler** để đo. Nếu xử lý quá chậm, có thể đặt một `QueueChannel` giới hạn dung lượng giữa producer và consumer rồi cấu hình **một polling consumer khác** để rút dữ liệu ra. Khi đó sẽ có **hai lớp polling**:

- **Poller A** lấy dữ liệu từ file `MessageSource` và gửi vào queue.
- **Poller B** gọi `receive()` từ `QueueChannel` để chạy handler.

Thiết kế này giúp tách nhịp phát hiện file với nhịp xử lý, nhưng không tự tạo tính bền vững. Phải kiểm soát dung lượng queue và hành vi khi channel đầy, tránh producer poll file liên tục rồi làm tăng memory.

## 7. Ví dụ Spring Integration: PollingConsumer đọc QueueChannel

Ở đây message **đã nằm trong ứng dụng**, trong một `QueueChannel`. Ta dùng endpoint service handler có poller. Đây mới là trường hợp ứng với lớp **`PollingConsumer`** theo tên gọi Spring Integration.

### 7.1. Java DSL

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class QueuePollingFlow {

    @Bean
    public QueueChannel auditWorkQueue() {
        // Dung lượng giới hạn thay vì queue trong bộ nhớ không giới hạn.
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow drainAuditQueue(QueueChannel auditWorkQueue) {
        return IntegrationFlow.from(
                    auditWorkQueue,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(500))
                               .maxMessagesPerPoll(10)
                    )
                )
                .handle((MessageHandler) message -> {
                    System.out.println("Consume: " + message.getPayload());
                    // Xử lý ở đây; một queue trong bộ nhớ không thay thế
                    // durable broker hoặc giao dịch nghiệp vụ.
                })
                .get();
    }
}
~~~

**Luồng gửi message** từ producer khác có thể lấy bean `auditWorkQueue` như một `MessageChannel` và gọi `send(message)`. Consumer nhận theo nhịp của poller. Nếu không có message, `receive()` trả null hoặc đợi theo timeout, không bắt buộc handler được gọi.

### 7.2. Java annotation: gắn poller ở consumer

Một phong cách khác là khai báo `QueueChannel` và phương thức service activator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class AnnotatedQueueConsumer {

    @Bean
    public QueueChannel workQueue() {
        return new QueueChannel(50);
    }

    @ServiceActivator(
        inputChannel = "workQueue",
        poller = @Poller(fixedDelay = "1000", maxMessagesPerPoll = "5")
    )
    public void process(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

Ở đây annotation `@Poller` thuộc **service activator tiêu thụ queue**, không phải một lịch quét thư mục. Khi chọn kiểu cấu hình, hãy bảo đảm `inputChannel` là channel phù hợp để poll; `DirectChannel` không hỗ trợ `receive()`.

### 7.3. So sánh hai ví dụ để tránh nhầm

| Câu hỏi | File inbound flow | Queue consumer flow |
| --- | --- | --- |
| Nguồn nhận | Thư mục file ngoài ứng dụng | Message đã gửi vào QueueChannel |
| Thao tác nhận | `MessageSource.receive()` | `PollableChannel.receive(timeout)` |
| Endpoint điển hình | `SourcePollingChannelAdapter` | `PollingConsumer` |
| Khi không có dữ liệu | File source không tìm thấy file đủ điều kiện | Queue rỗng |
| Độ bền | Filter/metadata/file store quyết định | QueueChannel trong bộ nhớ không mặc định durable |
| Lỗi phổ biến | File chưa ghi xong, duplicate sau restart | Queue đầy, handler chậm, mất message khi crash |
| Cách kiểm tra | File nào đã chọn, đã parse/commit chưa | Queue depth, dequeue, handler result |

## 8. Áp dụng polling theo từng adapter và giao thức

Cùng một pattern nhưng **đơn vị dữ liệu, acknowledgment, timeout và cơ chế tránh trùng** thay đổi theo hệ thống ngoài.

### 8.1. File và SFTP

**File:** đọc danh sách file đủ điều kiện trong thư mục. Cần kiểm soát pattern, thư mục staging, file viết dở, thứ tự, độ lớn file, memory, archive và metadata processed. File lớn không nhất thiết đọc hết vào RAM; có thể truyền `File` hoặc stream rồi xử lý theo chunk.

**SFTP:** kết nối phiên từ xa, liệt kê file, tải/copy hoặc stream. Cần cân nhắc:

- Thư mục remote và local; file nào đã nhận, file nào đã xử lý?
- Session factory, giới hạn kết nối, timeout, xác minh server host key, secret management.
- Remote file filter và metadata store **bền vững/dùng chung** nếu chạy nhiều instance.
- File đang upload, rename/marker, reconnect, resume hoặc retry khi đường truyền đứt.
- Tránh xoá file remote sớm nếu chưa xác nhận xử lý downstream.
- Quan sát số file tồn đọng, tuổi file và thời gian tải.

Trong Spring Integration SFTP có các dạng inbound adapter tải về local hoặc **inbound streaming adapter** đọc stream. Chọn loại dựa trên kích thước file, cách retry và yêu cầu lưu trữ. Không giả định “stream xong” nghĩa là dữ liệu nghiệp vụ đã commit; tài nguyên stream/session cần được đóng đúng cách.

### 8.2. JDBC và database polling

Một bài toán điển hình là bảng `integration_outbox` hoặc `pending_task` chứa các hàng cần chuyển:

~~~sql
-- Câu truy vấn minh họa kiểu SQL, không phải cấu hình JDBC adapter hoàn chỉnh.
SELECT id, business_key, payload
FROM integration_outbox
WHERE status = 'READY'
ORDER BY created_at, id;
~~~

Nếu hai instance cùng truy vấn các hàng READY, **cả hai có thể lấy cùng bản ghi**. Cần cơ chế **claim/lease/row lock hoặc thay trạng thái bằng update có điều kiện** trong transaction; cú pháp như `FOR UPDATE SKIP LOCKED` chỉ dùng khi DB hỗ trợ và transaction phù hợp. Một `SELECT` đơn thuần không phải hàng đợi exactly-once.

Mẫu trạng thái:

~~~text
READY
  → CLAIMED (owner, leaseUntil, attempt)
  → PROCESSED khi sink xác nhận kết quả
  → RETRYABLE/FAILED nếu lỗi
  → READY trở lại khi lease hết và được phục hồi hợp lệ
~~~

Nếu DB là **nguồn của transaction nghiệp vụ**, có thể cân nhắc **transactional outbox** để tránh tình huống commit dữ liệu nhưng không có sự kiện, rồi dùng poller đọc outbox và phát message. Tuy nhiên, việc phát sang broker hoặc HTTP đích vẫn cần idempotency và xử lý khoảng trống lỗi giữa “gửi thành công” với “mark processed”.

### 8.3. HTTP polling

Khi đối tác chỉ có API đọc thay đổi:

~~~http
GET /api/changes?cursor=cursor-017&limit=100 HTTP/1.1
Authorization: Bearer <REDACTED>
If-None-Match: "<known-etag>"
~~~

Đây là request minh họa; ETag, cursor và endpoint phụ thuộc API thực tế. Thiết kế cần:

1. Lưu cursor/ETag hoặc watermark trong kho bền vững.
2. Phân biệt **không có dữ liệu** với timeout, 429 và 5xx.
3. Tôn trọng rate limit và `Retry-After` nếu API cung cấp.
4. Không đẩy cursor tiến lên trước khi dữ liệu của trang đó được xử lý theo điều kiện đã định.
5. Xử lý pagination, bản ghi sửa lại, timestamp lệch và cửa sổ dữ liệu trùng.
6. Đảm bảo credential không được ghi lộ trong request log/headers.

Với HTTP, polling thường là một **scheduled flow gọi outbound gateway** hoặc message source tự thiết kế, tùy hướng tương tác; không nên gọi mọi HTTP outbound gateway là inbound polling adapter.

### 8.4. JMS và AMQP

JMS/AMQP có mô hình broker và consumer listener, acknowledgment, redelivery, dead-letter, prefetch và giao dịch theo từng sản phẩm. Thường nên cân nhắc **message-driven inbound adapter/listener container** thay vì thêm một lớp lịch hỏi riêng nếu broker đã hỗ trợ cơ chế nhận dữ liệu phù hợp.

Nếu thật sự dùng polling (ví dụ qua `MessageSource` hoặc luồng tiêu thụ `PollableChannel`), phải biết:

- Ai giữ message trước khi consumer nhận, và khi nào broker coi message đã được acknowledge?
- Nếu handler ném exception, broker redeliver hay message đã mất?
- Giao dịch broker có bao trùm việc ghi DB hoặc gọi HTTP đích không?
- Prefetch, batch, lock và concurrency ảnh hưởng thứ tự/duplicate ra sao?
- Poison message đi vào đâu sau số lần retry có giới hạn?

Không gán đảm bảo delivery của broker cho `QueueChannel` trong bộ nhớ. Khi cần hàng đợi bền vững và tái giao hàng, phải chọn cơ chế lưu/ack có đặc tính tương ứng.

### 8.5. Kafka

Kafka consumer client dùng vòng gọi `poll()` để lấy record, nhưng Spring Integration thường tích hợp Kafka qua **listener/message-driven inbound channel adapter** được quản lý bởi Kafka listener container; một luồng như vậy **không đồng nhất** với endpoint Spring Integration `PollingConsumer` đọc `QueueChannel`.

Khi sử dụng Kafka, các câu hỏi cốt lõi là:

- Offset được commit khi nào so với nghiệp vụ xử lý thành công?
- Consumer group, partition assignment, rebalance tác động thứ tự và retry thế nào?
- Một record lỗi có bị đọc lại nhiều lần không? Dead-letter/retry topic có được định nghĩa không?
- Concurrency có phù hợp số partition và yêu cầu giữ thứ tự theo key không?
- Nếu chủ động poll qua một `MessageSource` được hỗ trợ, nguồn đó quản lý offset/ack ra sao?

**Kết luận:** chọn adapter/lối tiêu thụ theo **ngữ nghĩa giao thức** trước; sau đó mới chọn nhịp poll, channel và cách điều tiết. Không cố áp mẫu file polling cho Kafka hay JMS chỉ để các cấu hình trông giống nhau.

### 8.6. Bảng lựa chọn nhanh

| Nguồn | Có thể chủ động poll? | Điều phải thiết kế trước khi chạy |
| --- | --- | --- |
| File local | Có | Filter, file hoàn tất, metadata đã nhận, archive/retry |
| SFTP | Có | Session, remote/local filter, tải/stream, reconnect |
| Database | Có | Claim/lock, transaction, lease, idempotency |
| HTTP changes API | Có | Cursor/ETag, rate limit, pagination, watermark |
| JMS | Có thể, nhưng thường có listener | Ack, transaction, redelivery, ordering |
| AMQP | Có thể, nhưng thường có listener | Ack/nack, prefetch, DLQ, concurrency |
| Kafka | Consumer client poll nội bộ; SI thường có listener | Offset, group, partition, rebalance, retry |
| QueueChannel nội bộ | Có | Dung lượng, receiveTimeout, poller, độ bền |

## 9. Delivery semantics: polling không tự bảo đảm exactly-once

Một trong những lỗi thiết kế lớn nhất là xem **“mỗi nguồn chỉ được poll một lần”** tương đương **“mỗi nghiệp vụ chỉ xử lý một lần”**. Hệ thống thực tế có nhiều cửa sổ lỗi:

~~~text
T1. Poller nhận record từ nguồn.
T2. Handler bắt đầu xử lý.
T3. Handler ghi kết quả vào database đích và commit.
T4. Process chết trước khi đánh dấu nguồn đã xử lý.
T5. Khi khởi động lại, poller có thể lấy lại record ở T1.
~~~

Nếu handler **không idempotent**, bước T5 có thể tạo hóa đơn, gửi email hoặc ghi dữ liệu hai lần. Ngược lại, nếu đánh dấu nguồn “đã xử lý” **trước T3**, process chết có thể khiến dữ liệu bị bỏ sót.

### 9.1. So sánh ba cách xử lý delivery

| Kiểu mục tiêu | Ý nghĩa | Cách thường đạt | Giới hạn |
| --- | --- | --- | --- |
| **At-most-once** | Không xử lý lại sau một lần nhận, có thể mất dữ liệu khi lỗi | Bỏ/ack sớm, không redelivery | Không phù hợp với nghiệp vụ không được mất |
| **At-least-once** | Cố gắng xử lý cho tới khi thành công; có thể trùng | Retry/redelivery, ghi nhận sau xử lý | Handler phải chịu được duplicate |
| **Effectively-once** | Tác động nghiệp vụ quan sát được chỉ xảy ra một lần dù message được nhận lại | Business idempotency key, unique constraint, giao dịch và reconciliation | Không có nghĩa toàn bộ mạng/hệ thống chỉ chuyển message một lần |

Một số nền tảng có đảm bảo xử lý mạnh trong một phạm vi giao dịch/stream xác định, nhưng **không tự mở rộng** sang file, SFTP, HTTP và nhiều cơ sở dữ liệu độc lập. Với polling consumer tích hợp nhiều hệ, **at-least-once + idempotent business operation** thường là điểm xuất phát thực tế hơn lời hứa exactly-once tổng quát.

### 9.2. Idempotency ở nhiều lớp

1. **Source filter:** ngăn chọn lại file/record đã thấy; cần lưu bền vững nếu muốn tồn tại qua restart.
2. **Message idempotent filter:** dùng stable message/business key thay vì chỉ dựa `MessageHeaders.ID`.
3. **Business idempotency:** lưu unique key khi tạo kết quả để duplicate không làm lặp side effect.
4. **Downstream API:** gửi `Idempotency-Key` hoặc cơ chế dedupe theo hợp đồng API nếu có.
5. **Reconciliation:** đối chiếu trạng thái cuối khi ACK bị mất nhưng thao tác có thể đã thành công.

Ví dụ với một file được đặt tên lại hoặc tải lại bằng tên khác, **file path** có thể không phải khóa nghiệp vụ tốt nhất. Có thể cần `partnerId + documentId + version` hoặc content checksum theo hợp đồng dữ liệu. Content checksum cũng cần cân nhắc: hai tài liệu khác nhau có nội dung giống nhau có thể vẫn phải xử lý độc lập.

### 9.3. Bảng dedupe trong DB

Ví dụ cấu trúc lưu business key:

~~~sql
CREATE TABLE processed_event (
    source_name VARCHAR(100) NOT NULL,
    business_key VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (source_name, business_key)
);
~~~

Một chiến lược là ghi hàng `processed_event` **trong cùng giao dịch** với thay đổi nghiệp vụ ở DB đích. Nếu xảy ra xung đột unique key, xử lý như duplicate đã biết hoặc kiểm tra trạng thái nghiệp vụ trước khi bỏ qua. Không đặt dấu dedupe “thành công” trước khi side effect không thể rollback hoàn tất, nếu như thế có thể làm mất dữ liệu.

**Cảnh báo:** Nếu handler gọi một HTTP API không tham gia transaction DB, việc ghi dedupe + commit DB vẫn không tạo một giao dịch xuyên mạng. Cần cơ chế outbox, idempotency ở API đích hoặc reconciliation theo yêu cầu.

## 10. Transaction, acknowledgment và xử lý lỗi poller

### 10.1. Biên giao dịch nằm ở đâu?

~~~mermaid
flowchart LR
    POLL["Poll nguồn"] --> CHANNEL["MessageChannel"]
    CHANNEL --> PROCESS["Handler: xử lý"]
    PROCESS --> DB["DB commit"]
    PROCESS --> API["HTTP / SFTP / Broker đích"]
    DB --> MARK["Mark source processed"]
    API --> MARK
    NOTE["Chỉ những thành phần tham gia cùng transaction mới có thể atomic với nhau"] -.-> DB
    NOTE -.-> API
~~~

Trong Spring Integration, có thể cấu hình **transaction advice** cho polling endpoint phù hợp. Nhưng cần biết:

- Transaction được áp lên thread và phạm vi nào?
- `MessageSource` hoặc `PollableChannel` có hỗ trợ transaction/rollback hay không?
- Handler có chạy đồng bộ trong cùng thread không, hay qua `ExecutorChannel`/executor khác?
- Broker/DB có dùng cùng transaction manager hoặc một cơ chế phối hợp được hỗ trợ không?
- Khi handler lỗi, source có thể đưa message trở lại, để retry, hay chỉ log?

Không suy ra rằng đặt `@Transactional` cho một method sẽ khiến file, SFTP, Kafka, DB và HTTP cùng rollback. File rename hoặc request HTTP đã gửi không thể rollback bằng giao dịch JDBC thông thường.

### 10.2. Phân loại lỗi để chọn chính sách

| Lỗi | Ví dụ | Cách xử lý thường phù hợp |
| --- | --- | --- |
| **Nguồn tạm thời** | SFTP mất kết nối, HTTP 503, DB timeout | Retry với backoff, reconnect và cảnh báo theo ngưỡng |
| **Rate limit** | HTTP 429, throttling từ API | Tôn trọng Retry-After, giảm nhịp poll |
| **Dữ liệu không hợp lệ** | CSV thiếu cột bắt buộc, JSON sai schema | Quarantine/reject có bằng chứng; không retry vô hạn |
| **Dữ liệu hợp lệ nhưng nghiệp vụ từ chối** | Order không có customer hợp lệ | Ghi trạng thái nghiệp vụ, chuyển xử lý theo quy định |
| **Đích tạm thời** | DB đích offline, broker gián đoạn | Không mark source processed sớm; retry idempotent |
| **Bug cấu hình** | Sai credentials, host key SFTP, sai role DB | Dừng lặp retry nhanh, alert owner, khắc phục cấu hình |
| **Poison message** | Một message gây exception lặp lại | Hạn retry, đưa vào hàng/quarantine riêng và theo dõi |

### 10.3. Error channel và lỗi bên trong poll

Spring Integration có cơ chế `ErrorMessage`, error channel, advice và error handler. Tuy nhiên **đường đi của exception phụ thuộc endpoint, channel, scheduler và cách flow thực thi**:

- Lỗi đồng bộ từ handler có thể lan ngược tới polling endpoint khi handler cùng luồng gọi.
- Lỗi từ handler bất đồng bộ có thể được chuyển qua một đường xử lý lỗi khác, không còn nằm trong transaction của poll ban đầu.
- Lỗi xảy ra lúc source `receive()` cần log, cảnh báo và xử lý riêng so với lỗi parse ở handler.
- Error handler chỉ **ghi log và nuốt exception** có thể làm thay đổi cách nguồn quyết định retry; phải hiểu semantics của adapter.

Khi xây error flow, lưu **original message hoặc business key, source, attempt, exception class, trace ID và owner** ở mức cần thiết; không ghi credential hoặc payload nhạy cảm nguyên văn tràn lan.

### 10.4. Retry có backoff thay vì poll dồn dập

Giả sử SFTP tạm ngừng 10 phút. Nếu mỗi poll thất bại lại thử ngay lập tức, ứng dụng vừa làm tăng tải vừa ngập log.

Một chính sách minh họa:

~~~text
Lần đầu:   thử theo lịch thông thường.
Lỗi 1:     trì hoãn ngắn, có jitter nếu nhiều instance.
Lỗi 2:     tăng thời gian chờ.
Lỗi N:     đạt ngưỡng → cảnh báo, circuit breaker hoặc tạm ngừng.
Khôi phục: kiểm tra kết nối, đọc lại metadata, tiếp tục an toàn.
~~~

Không áp dụng cùng một retry policy cho lỗi schema và lỗi mạng. File dữ liệu xấu thường cần **quarantine**, trong khi kết nối gián đoạn có thể retry sau khi endpoint phục hồi. Retry count và thời gian chờ cần có mục tiêu vận hành, không phải giá trị tùy tiện.

### 10.5. Poison message phải đi đâu?

~~~mermaid
flowchart TD
    M["Nhận message"] --> V{"Dữ liệu hợp lệ?"}
    V -->|Không| Q["Quarantine + reason + owner"]
    V -->|Có| P["Xử lý"]
    P --> R{"Thành công?"}
    R -->|Có| A["Ack/mark processed theo contract"]
    R -->|Lỗi tạm thời| RETRY["Retry có giới hạn + backoff"]
    RETRY --> P
    R -->|Lỗi không thể khắc phục tự động| DLQ["Error store / DLQ / manual review"]
~~~

**DLQ** là một pattern cần có **nơi lưu, owner, khả năng replay và bảo vệ dữ liệu**, không phải một thao tác `log.error(...)` rồi bỏ qua. Với file/SFTP có thể dùng thư mục quarantine cùng metadata; với JMS/AMQP/Kafka có thể dùng dead-letter destination theo broker/adapter.

## 11. Backpressure, batch size và điều tiết tải

Polling consumer tạo một **nhịp cung ứng work** cho handler. Định cấu hình tốt phải cân bằng **độ trễ**, **thông lượng** và **tải nguồn/đích**.

### 11.1. Ba biến cần đo

| Biến | Ý nghĩa | Cách quan sát |
| --- | --- | --- |
| **Arrival rate** | Dữ liệu mới xuất hiện ở nguồn bao nhiêu mỗi giây/phút | Broker lag, bản ghi READY, số file mới, HTTP change count |
| **Service rate** | Handler hoàn tất nghiệp vụ bao nhiêu mỗi giây/phút | Processed success/second và thời gian xử lý |
| **Backlog** | Dữ liệu đến nhưng chưa xử lý thành công | Queue depth, file age, rows pending, consumer lag |

Ví dụ, nguồn tạo **120 file/phút** nhưng handler hoàn tất **80 file/phút**. Backlog tăng khoảng **40 file/phút** nếu điều kiện ổn định, không có xử lý song song bổ sung. Chỉ giảm `fixedDelay` không giải quyết được nếu handler hoặc DB là nút thắt cổ chai.

### 11.2. Tăng throughput theo thứ tự thận trọng

1. Đo latency của từng bước: poll source, chuyển message, parse, validate, ghi đích.
2. Điều chỉnh `maxMessagesPerPoll` nếu scheduler thường kết thúc quá sớm dù nguồn còn dữ liệu.
3. Giảm I/O polling rỗng: tăng delay, dùng adaptive backoff hoặc chuyển event-driven nếu nguồn hỗ trợ.
4. Giảm chi phí connection bằng pooling phù hợp, nhưng tránh giữ session lỗi quá lâu.
5. Tối ưu handler/DB, batch operation hoặc xử lý không đồng bộ khi ranh giới giao dịch cho phép.
6. Chỉ tăng concurrency hoặc số instance sau khi có cơ chế **claim/lock, idempotency và ordering**.
7. Theo dõi hệ quả: backlog, memory, số kết nối, độ trễ và tỷ lệ retry.

### 11.3. `QueueChannel` không giới hạn có thể gây OOM

Nếu producer đọc file nhanh, đẩy mọi message vào queue trong bộ nhớ mà consumer xử lý chậm, heap tăng. Nên:

- Đặt **capacity** có chủ ý.
- Quy định hành vi khi `send()` không thành công hoặc phải chờ.
- Giảm nhịp nguồn, tạm ngừng endpoint hoặc dùng cơ chế durable queue khi cần.
- Đo queue depth và thời gian chờ; tránh chỉ đo số message nhận.
- Hiểu rằng `QueueChannel` có thể mất dữ liệu chưa xử lý khi JVM dừng nếu không có kho lưu bền vững phù hợp.

### 11.4. Concurrency khác “mỗi poll lấy nhiều message”

`maxMessagesPerPoll(20)` **không đồng nghĩa** 20 thread xử lý song song. Threading phụ thuộc scheduler, executor, channel, handler và adapter. Một `DirectChannel` thường gọi handler trên thread gửi; một `ExecutorChannel` có thể chuyển qua executor; `QueueChannel` đệm message rồi consumer rút ra.

Nếu yêu cầu giữ thứ tự theo đơn hàng hoặc customer, cần quy tắc **partition theo key, serial processing hoặc kiểm soát phiên bản**. Bật nhiều thread có thể cải thiện throughput nhưng làm thứ tự hoàn thành khác thứ tự nguồn.

## 12. Chạy nhiều instance và xử lý trùng trong hệ phân tán

Một poller chạy một instance đã có thể tạo duplicate khi restart. Khi triển khai **hai hoặc nhiều replica**, vấn đề trở nên rõ hơn: cả hai ứng dụng có thể cùng thấy file SFTP hoặc hàng database chưa xử lý.

### 12.1. Ba mô hình triển khai phổ biến

| Mô hình | Cách hoạt động | Ưu điểm | Điều kiện an toàn |
| --- | --- | --- | --- |
| **Single active poller** | Chỉ một instance thực hiện poll; instance khác dự phòng | Đơn giản, dễ giữ thứ tự | Cơ chế leader election/failover đáng tin, phát hiện leader chết |
| **Multi-poller với shared claim** | Nhiều instance poll, mỗi dữ liệu được claim có điều kiện | Tăng throughput | Shared lock/lease/metadata, xử lý lease hết hạn và retry |
| **Partitioned polling** | Mỗi instance sở hữu một phần dữ liệu theo key/range | Dễ quy định thứ tự trong partition | Điều phối assignment, xử lý rebalance và chuyển quyền sở hữu |

Không có mô hình “đúng cho mọi hệ”. Một thư mục SFTP vài file/ngày có thể không cần nhiều poller; một bảng outbox lớn có thể cần nhiều worker, claim có điều kiện và đo backlog.

### 12.2. Vì sao filter accept-once trong bộ nhớ chưa đủ?

~~~text
Replica A                         Replica B
  list SFTP: report-01.csv          list SFTP: report-01.csv
  in-memory filter: unseen         in-memory filter: unseen
  tải file                          tải cùng file
  xử lý                             xử lý trùng
~~~

Hai JVM có **bộ nhớ độc lập**. Không thể dựa vào một set filename cục bộ để đồng bộ cluster. Tùy adapter, hãy cân nhắc **persistent/shared metadata store** và cơ chế lock/claim phù hợp; ví dụ trong hệ sinh thái Spring Integration có các lựa chọn metadata store và lock registry cho từng nguồn.

Nhưng ngay cả shared metadata cũng cần xem xét thời điểm lưu trạng thái. Nếu đánh dấu “đã nhận” trước xử lý và process chết, có nguy cơ bỏ sót; nếu đánh dấu muộn, có thể nhận lại. Cơ chế idempotency ở nghiệp vụ vẫn quan trọng.

### 12.3. Lease và reclaim khi worker chết

Trong database polling, một hàng có thể mang `ownerId`, `claimedAt`, `leaseUntil` và `attempt`. Worker claim bằng **cập nhật có điều kiện** trong transaction; nếu worker chết, lease hết hạn để worker khác xử lý lại.

~~~text
READY --claim atomically--> IN_PROGRESS(owner=A, leaseUntil=t1)
IN_PROGRESS --completed--> PROCESSED
IN_PROGRESS --lease expired--> READY/RETRY
~~~

Cần giải quyết trường hợp worker A **vẫn còn chạy nhưng lease đã hết** trong khi worker B nhận lại. Có thể cần heartbeat/lease renewal, fencing token hoặc kiểm tra version khi commit. Lease chỉ là một phần của chiến lược không trùng và bảo toàn tác động.

### 12.4. Thứ tự và lịch sử dữ liệu

Một poller lấy file theo tên hoặc timestamp chưa chắc có **thứ tự nghiệp vụ**. Khi hai file `order-2.csv` và `order-1.csv` đến sai thứ tự, áp dụng cập nhật mù quáng có thể làm trạng thái cũ ghi đè trạng thái mới.

Hãy thiết kế:

- Business sequence/version nếu nguồn có.
- Quy tắc xử lý theo key hoặc partition.
- Cơ chế kiểm tra stale event trước khi thay đổi trạng thái.
- Quy trình xử lý trường hợp thiếu hoặc nhận lại một phiên bản.

Không dựa chỉ vào `File.lastModified()` như một cam kết thứ tự sự kiện nghiệp vụ, nhất là khi đồng hồ nhiều hệ khác nhau hoặc file được copy lại.

## 13. Vòng đời endpoint, kết nối và scheduler

Polling là một **công việc có vòng đời**. Khi ứng dụng khởi động, nó phải biết có nên poll ngay không; khi shutdown, nó phải dừng nhận công việc mới và xử lý các message đang chạy theo chính sách.

### 13.1. Startup

- [ ] Kiểm tra nguồn file/SFTP/DB/API đã sẵn sàng; nếu chưa, xác định retry/backoff và health.
- [ ] Khởi tạo metadata store, mapping và idempotency key trước lượt poll đầu tiên.
- [ ] Không mở nhiều poller trên cùng partition nếu chưa có shared coordination.
- [ ] Có cấu hình khác nhau cho môi trường dev/test/prod; không vô tình dùng thư mục hoặc credential production trong lab.
- [ ] Kiểm tra endpoint có auto-startup phù hợp và biết cách tạm ngừng theo runbook.

### 13.2. Shutdown và deploy rolling

- [ ] Ngăn lượt poll mới trước hoặc trong quá trình dừng dịch vụ theo lifecycle.
- [ ] Đảm bảo handler đang chạy có cơ hội kết thúc/rollback theo giới hạn thời gian shutdown.
- [ ] Không mark data processed khi business transaction chưa commit.
- [ ] Nếu message còn trong `QueueChannel` memory, đã tính cách không làm mất khi process dừng?
- [ ] Shared lock/lease được giải phóng hoặc có TTL để instance mới phục hồi.
- [ ] Không để nhiều phiên bản app cùng áp schema event khác nhau mà không có kế hoạch tương thích.

Trong Spring Integration, endpoint thường tham gia lifecycle của Spring application context và có thể được quản lý tạm dừng/khởi động theo khả năng cấu hình. Tên bean, control bus hoặc cơ chế quản lý runtime cần được xác minh cho phiên bản áp dụng; không tự giả định dừng endpoint tức thời làm mọi handler đang chạy hủy một cách an toàn.

### 13.3. Kết nối và resource

| Nguồn | Tài nguyên phải quản lý | Biểu hiện lỗi |
| --- | --- | --- |
| Local file | File handle, disk IO, archive directory | File bị giữ khóa, disk đầy, tệp dở |
| SFTP | Session, TCP connection, pool, remote server key | Timeout, session stale, server từ chối |
| JDBC | Connection pool, transaction, cursor, lock | Connection leak, deadlock, hết pool |
| HTTP | HTTP client pool, TLS, rate limit | 429, reset, timeout, cursor mất đồng bộ |
| JMS/AMQP | Connection, consumer channel/session, ack | Disconnect, redelivery, consumer bị dừng |
| Kafka | Consumer group, offset, partition assignment | Rebalance, lag tăng, record không được xử lý |

Đừng xử lý lỗi kết nối bằng vòng tạo session vô hạn không có giới hạn. Cấu hình timeout, connection validation, retry/backoff và metrics theo nguồn.

## 14. Observability: biết poller có thực sự tiến triển không

“Ứng dụng đang chạy” chưa chứng minh poller đang lấy và xử lý đúng dữ liệu. Cần theo dõi **hoạt động polling** và **tiến triển nghiệp vụ**.

### 14.1. Các chỉ số quan trọng

| Chỉ số | Cách hiểu | Khi nào cần cảnh báo? |
| --- | --- | --- |
| **poll attempts** | Số lượt scheduler kích hoạt poll | Giảm về 0 bất ngờ khi nguồn vẫn có dữ liệu |
| **empty poll ratio** | Tỷ lệ lượt poll không có message | Quá cao có thể poll quá dày; nhưng có thể bình thường theo tải |
| **poll duration** | Thời gian một lượt nhận và xử lý theo phạm vi đo | Tăng kéo dài làm lệch lịch |
| **messages received** | Số message lấy từ nguồn/kênh | Phân biệt với processed success |
| **processed successes** | Số tác vụ nghiệp vụ hoàn tất hợp lệ | Không tăng dù incoming tăng |
| **processing failures** | Số lỗi theo source/handler/target | Tăng đột biến hoặc lặp lại cùng business key |
| **retry attempts** | Số lần thử lại, nguyên nhân | Vòng lỗi không có tiến triển |
| **backlog depth/age** | Số lượng và tuổi dữ liệu chưa được xử lý | Vượt ngưỡng phụ thuộc SLA |
| **duplicate detected** | Số message đã thấy business key cũ | Tăng sau restart/rebalance/timeout |
| **last successful commit** | Lúc gần nhất lưu nghiệp vụ thành công | Quá lâu với nguồn có phát sinh dữ liệu |
| **connection errors** | SFTP/HTTP/DB/broker không kết nối được | Theo nguồn, môi trường, phân loại mã lỗi |

Định nghĩa chỉ số theo **source, flow, endpoint, target và môi trường**; tránh nhúng payload hoặc thông tin cá nhân nhạy cảm vào nhãn metric gây cardinality cực cao và rò rỉ.

### 14.2. Logging và tracing

Một bản ghi gợi ý:

~~~json
{
  "flow": "sftp-orders-inbound",
  "pollId": "poll-2026-11-23-00031",
  "source": "partner-A",
  "businessKey": "ORDERS-000387",
  "messageType": "ORDER_FILE",
  "attempt": 2,
  "stage": "VALIDATE_AND_STORE",
  "result": "RETRYABLE_ERROR",
  "durationMs": 142,
  "traceId": "trace-lab-531",
  "target": "order-db"
}
~~~

Mẫu JSON chỉ để minh họa; không phải format mặc định của Spring Integration. Khi nguồn chứa PII, không đưa nguyên nội dung file, password, token hoặc khóa riêng vào log. Dùng key tham chiếu an toàn và chính sách phân quyền truy cập log.

### 14.3. Ba cảnh báo có ích hơn chỉ báo “process alive”

1. **No progress:** nguồn có dữ liệu đang chờ nhưng `lastSuccessfulCommit` không thay đổi.
2. **Backlog age:** tệp/bản ghi lâu nhất chưa xử lý vượt thời hạn mà nghiệp vụ chịu được.
3. **Repeated failure:** cùng lỗi kết nối hoặc cùng business key retry quá ngưỡng.

Một poller rỗng khi nguồn thật sự không có dữ liệu là bình thường. Cảnh báo cần kết hợp tín hiệu nguồn và lịch phát sinh dữ liệu, tránh báo động mỗi khi polling trả `null`.

### 14.4. Chẩn đoán từ triệu chứng

| Triệu chứng | Giả thuyết ưu tiên | Bằng chứng nên tìm |
| --- | --- | --- |
| Không có message dù source có file | Filter quá chặt, endpoint chưa start, sai thư mục | Endpoint state, folder listing, filter logs |
| Poll rất thường xuyên nhưng không có tiến triển | File chưa hoàn tất, lỗi parse, empty polls, retry loop | Poll duration, rejects, staging |
| Chỉ thấy lỗi sau restart | Filter chỉ ở bộ nhớ, metadata không bền, lock chưa giải phóng | Duplicate keys, metadata store, startup sequence |
| Càng tăng poll càng chậm | DB/HTTP đích nghẽn, connection pool đầy, contention | Sink latency, queue depth, pool metrics |
| Hai replica xử lý cùng file | Không có shared claim/metadata hoặc fencing | Instance ID, lock logs, dedupe violation |
| Một message liên tục làm flow dừng | Poison data, retry vô hạn, không quarantine | Business key, error flow, attempt |
| Message đã dequeue nhưng dữ liệu không thấy | Ack/mark quá sớm, handler async, transaction lỗi | Handler completion, DB commit, channel semantics |

## 15. Thiết kế kiểm thử cho Polling Consumer

Vì polling chịu ảnh hưởng của **thời gian, scheduler và I/O**, kiểm thử cần phân biệt **logic xử lý** với **tác động của lịch poll thực tế**.

### 15.1. Ba lớp kiểm thử

1. **Unit test:** thử parser, idempotency key, state transition, retry classification bằng dữ liệu thuần, không cần chạy scheduler.
2. **Integration test trong JVM:** tạo `MessageSource`/channel giả hoặc thư mục tạm, khởi chạy Spring context, đợi message xuất hiện và kiểm tra handler.
3. **End-to-end/contract test:** kết nối SFTP/DB/broker giả lập hoặc được cấp phép, kiểm tra mapping, giao dịch, retry, ack/offset và readback ở hệ đích.

Thay vì dùng `Thread.sleep(5000)` tùy tiện rồi hy vọng poll đã chạy, có thể dùng cơ chế **eventual assertion với timeout** trong test, giữ thời gian chờ có giới hạn và thu thập log khi lỗi. Test schedule nên điều chỉnh đủ nhanh trong môi trường kiểm thử nhưng không thay đổi ý nghĩa giao thức.

### 15.2. Ma trận kiểm thử cốt lõi

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **PC-01** | Thư mục file rỗng, poll được kích hoạt | Không gọi handler, không exception vô ích |
| **PC-02** | Thêm một file CSV hoàn chỉnh | Tạo đúng một message trong một lần nhận hợp lệ |
| **PC-03** | Thêm file `*.tmp` không khớp filter | Không được xử lý trước khi công bố |
| **PC-04** | File đang được ghi, chưa đổi đuôi | Chưa xử lý file chưa hoàn tất |
| **PC-05** | Có 12 file, `maxMessagesPerPoll=5` | Một lượt không nhận quá 5 message; các lượt sau tiếp tục |
| **PC-06** | Nguồn trả `null` | Không tạo message rỗng hoặc gọi handler với payload null |
| **PC-07** | Hai lượt poll đều thấy cùng file | Filter/idempotency theo hợp đồng ngăn tác động nghiệp vụ trùng |
| **PC-08** | Restart app sau một file đã xử lý | Metadata/idempotency bền vững ngăn side effect bị lặp |
| **PC-09** | Handler lỗi trước commit | Nguồn/message được giữ để retry hoặc chuyển quarantine đúng policy |
| **PC-10** | Handler commit thành công nhưng ACK bị mất | Retry không tạo side effect trùng |
| **PC-11** | CSV sai schema | Tách quarantine, không retry vô hạn |
| **PC-12** | SFTP hoặc HTTP timeout tạm thời | Retry/backoff, alert theo ngưỡng, không busy loop |
| **PC-13** | HTTP trả 429 có Retry-After | Giảm nhịp phù hợp với hợp đồng API |
| **PC-14** | QueueChannel đầy | Producer được xử lý theo chính sách send timeout/backpressure |
| **PC-15** | Handler chậm hơn chu kỳ poll | Không vô tình làm backlog/OOM không kiểm soát |
| **PC-16** | Hai instance cùng thấy một file/hàng DB | Shared claim/lock và idempotency ngăn tác động trùng |
| **PC-17** | Một worker chết sau khi claim | Lease/khôi phục cho phép xử lý lại an toàn |
| **PC-18** | Event đến sai thứ tự | Version/business rule chặn trạng thái cũ ghi đè |
| **PC-19** | Dừng endpoint khi đang có backlog | Không nhận thêm việc trái chính sách; xử lý hoặc phục hồi phần đang dở |
| **PC-20** | Handler hoàn tất nhưng source metadata chưa cập nhật | Reconciliation phát hiện, retry không gây trùng |
| **PC-21** | Database không có bản ghi READY | Poll kết thúc bình thường, không full-table scan quá mức |
| **PC-22** | Mất kết nối SFTP và phục hồi | Reconnect an toàn, không dùng session cũ hỏng |
| **PC-23** | Lỗi transform trước khi outbound call | Error flow ghi đúng source và business key |
| **PC-24** | Kafka/JMS message-driven endpoint (nếu dùng) | Không nhầm lẫn consumer listener với PollingConsumer của QueueChannel |

### 15.3. Một phép kiểm thử mà nhiều người bỏ sót

**Tình huống:** poller đọc file, parser tạo một đơn hàng trong DB đích, rồi process chết **trước khi ghi nhận file đã xử lý**.

**Sai:** test chỉ xác nhận lần chạy đầu tạo một bản ghi; không kiểm tra restart.

**Đúng:** khởi động lại, cho poller thấy file lần nữa, xác minh **chỉ còn một đơn hàng** nhờ unique business key/transaction phù hợp, đồng thời metadata/trạng thái nguồn được khôi phục hoặc xử lý lại an toàn.

### 15.4. Test `QueueChannel` khác test `MessageSource`

Với `QueueChannel`, test phải xác minh khi có message thì consumer có thể nhận bằng `receive()`, và khi queue rỗng thì không phát sinh xử lý. Kiểm tra dung lượng, blocking timeout và shutdown.

Với `MessageSource`, test phải xác minh **nguồn ngoài được quét/đọc đúng**: file pattern, SFTP path, DB claim hoặc HTTP cursor. Không dùng test queue nội bộ làm bằng chứng rằng adapter SFTP đã quản lý duplicate và reconnect an toàn.

## 16. Bài lab tổng hợp: từ file CSV vào database

**Mục tiêu:** dùng polling để nhập các file đơn hàng giả vào một kho dữ liệu giả lập hoặc database test, có cơ chế tránh trùng, phân loại file lỗi và quan sát backlog. Không cần broker hoặc tài khoản SFTP thật để bắt đầu.

### 16.1. Bối cảnh

Đối tác DemoPartner đặt file CSV theo mẫu:

~~~csv
document_id,order_id,customer_id,amount
FILE-LAB-001,ORD-LAB-001,CUST-LAB-01,125000
FILE-LAB-001,ORD-LAB-002,CUST-LAB-02,82000
~~~

Giả định:

- Mỗi file có `document_id` ổn định do producer cấp.
- Mỗi order có `order_id` là business key duy nhất trong phạm vi đối tác.
- Producer chỉ đổi tên file sang `*.csv` khi đã ghi xong.
- Consumer kiểm tra schema, không tin số tiền hoặc tên file một cách mù quáng.
- Kết quả được ghi vào DB test với unique key phù hợp.

### 16.2. Cấu trúc thư mục đề xuất trong môi trường lab cá nhân

~~~text
lab/
  in/             # Producer công bố file hoàn chỉnh
  processing/     # File được claim (nếu triển khai)
  archive/        # File đã được xử lý và xác minh
  quarantine/     # File lỗi dữ liệu hoặc cần xem xét
  evidence/       # Báo cáo test/log không chứa secret
~~~

Đây là cấu trúc **gợi ý cho người thực hành**, không phải yêu cầu tạo thư mục trong repository của bài học.

### 16.3. Các bước thực hiện

**Bước 1 — Khởi tạo nguồn.** Dùng adapter đọc file định kỳ, filter theo `*.csv`; cấu hình fixed delay và `maxMessagesPerPoll` có giới hạn.

**Bước 2 — Công bố file.** Producer viết `*.uploading`, kiểm tra ghi xong rồi rename sang `*.csv`. Không để consumer đọc file đang ghi dở.

**Bước 3 — Tạo message contract.** Mỗi message có file path/stream và metadata `partnerId`, `documentId`, `traceId`; transformer parse thành DTO đã validate. `documentId` trong payload phải được xác minh theo hợp đồng, không tin filename là khóa duy nhất.

**Bước 4 — Ghi nghiệp vụ.** Xử lý từng dòng vào DB với business key. Với duplicate hợp lệ, không tạo bản ghi trùng; với lỗi dữ liệu, ghi trạng thái/quarantine.

**Bước 5 — Đánh dấu hoàn tất.** Chỉ chuyển file đến archive hoặc mark processed sau khi điều kiện commit được thỏa. Nếu một file có nhiều record và lỗi ở giữa, chọn policy **all-or-nothing**, partial recovery hoặc line-level quarantine; ghi rõ lựa chọn.

**Bước 6 — Gây lỗi.** Cho DB tạm thời trả timeout sau khi xử lý một phần; khởi động lại app và xác minh kết quả không trùng.

**Bước 7 — Tăng tải.** Thêm 100 file giả, đo số lượt poll, processing time và backlog age; điều chỉnh delay/batch có kiểm chứng.

**Bước 8 — Mô phỏng hai instance.** Nếu thêm replica, triển khai shared metadata/claim hoặc partition. Cho cả hai nhìn cùng file rồi xác minh side effect chỉ xuất hiện đúng một lần theo business key.

**Bước 9 — Bàn giao.** Viết runbook “SFTP unavailable”, “CSV malformed”, “DB timeout”, “duplicate after restart” và “backlog age quá hạn”.

### 16.4. Sơ đồ lab

~~~mermaid
flowchart LR
    P["Producer\n*.uploading → *.csv"] --> IN["File inbound adapter\nSource poller"]
    IN --> CH["MessageChannel"]
    CH --> VAL["Validate + Transform"]
    VAL --> IDEMP["Idempotent check"]
    IDEMP --> DB["Database test"]
    DB --> DONE["Archive + Evidence"]
    VAL -->|Sai schema| BAD["Quarantine"]
    DB -->|Lỗi tạm thời| RETRY["Retry có kiểm soát"]
    RETRY --> DB
~~~

### 16.5. Điều kiện nghiệm thu

- [ ] Chỉ file hoàn chỉnh đúng pattern được xử lý.
- [ ] Poll rỗng không tạo lỗi không cần thiết.
- [ ] Một file hợp lệ được transform đúng schema và kiểm tra dữ liệu.
- [ ] Dữ liệu sai không làm retry vô hạn; có quarantine và người chịu trách nhiệm.
- [ ] Cùng business key đến nhiều lần không tạo side effect trùng ngoài thiết kế.
- [ ] Process chết giữa xử lý có thể khôi phục hoặc retry theo policy.
- [ ] Không đánh dấu source processed trước khi đạt điều kiện commit.
- [ ] Backlog và thời gian xử lý có thể đo, có ngưỡng cảnh báo.
- [ ] Khi tăng poll rate, ứng dụng không làm nghẽn hoặc mất kiểm soát memory.
- [ ] Đã ghi rõ giới hạn: metadata bền vững, multi-instance, session và transaction.

### 16.6. Bài tập nâng cao

1. Đổi nguồn local file thành **SFTP test server**, kiểm tra host key và remote file filter.
2. Đổi nguồn thành **JDBC outbox**, thử hai worker claim cùng bản ghi và crash/reclaim.
3. Đổi thành API HTTP changes có cursor; gây lỗi ngay sau khi xử lý trang nhưng trước khi lưu cursor.
4. Tách handler chậm qua `QueueChannel` và đo queue depth; so với `DirectChannel`.
5. Thêm source error flow và business error flow tách biệt; thống kê retry theo nguyên nhân.
6. Đối chiếu với luồng **JMS/AMQP/Kafka listener**, giải thích thứ tự/ack/delivery có gì khác poll file.

## 17. Anti-patterns và sai lầm thiết kế thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| **Poll mỗi vài mili giây không có lý do** | Empty poll gây tải I/O và log | Đo latency cần thiết, chọn delay/adaptive backoff |
| **Bật maxMessagesPerPoll cực lớn** | Một lượt chiếm scheduler lâu, dồn bộ nhớ và tải đích | Giới hạn batch, đo duration và throughput |
| **Dùng DirectChannel rồi tìm cách receive()** | DirectChannel là subscribable, không pollable | Dùng QueueChannel khi cần consumer kéo message |
| **Nhầm PollingConsumer với SourcePollingChannelAdapter** | Cấu hình, đo đạc và lỗi nằm sai chỗ | Xác định rõ poll từ source hay từ channel |
| **Đặt QueueChannel vô hạn để tăng tốc** | Producer nhanh hơn consumer làm tăng heap | Bound queue, backpressure hoặc durable broker |
| **Tin filter in-memory là exactly-once** | Restart hoặc multi-instance gây duplicate | Persistent/shared metadata + business idempotency |
| **Mark file processed trước khi DB commit** | Crash làm mất dữ liệu | Gắn mark với trạng thái commit, recovery phù hợp |
| **Mark nguồn quá muộn nhưng không dedupe** | Retry tạo side effect trùng | Stable business key, unique constraint, idempotent sink |
| **Tăng concurrency không có claim** | Nhiều worker lấy cùng row/file | Lock/lease/partition và reconciliation |
| **Retry mãi CSV sai schema** | Poison message chặn flow, tốn tài nguyên | Quarantine + reason + replay được quản trị |
| **Ẩn lỗi bằng catch-log-and-continue** | Source có thể nghĩ message đã xử lý thành công | Phân loại lỗi, điều khiển ack/transaction đúng |
| **Dựa hoàn toàn vào lastModified** | File copy/clock skew làm sai thứ tự/độ mới | Business ID, manifest/marker, stable contract |
| **Xóa file ngay sau khi poll** | Handler downstream có thể thất bại | Chỉ archive/delete theo điều kiện hoàn tất |
| **Lẫn token vào Message headers/log** | Rò rỉ credential | Secret manager, redaction, không log raw token |
| **Coi poll thành công là business success** | Source đọc được nhưng đích chưa commit | Đo riêng receive, process, commit, readback |
| **Không tách lỗi nguồn và lỗi handler** | Retry/alert sai nơi | Error flow có phân loại và owner |

### 17.1. Khi không nên dùng Polling Consumer

Không nên chọn polling chỉ vì dễ hình dung nếu hệ thống nguồn có **listener/webhook/stream** đáng tin với semantics phù hợp. Chẳng hạn một JMS listener hoặc Kafka consumer container thường xử lý tốt việc nhận thông điệp theo cơ chế broker, trong khi tự tạo timer gọi API/broker nhiều lần có thể tăng độ trễ và gánh nặng vận hành.

Ngược lại, **webhook** không mặc nhiên tốt hơn polling: cần xử lý xác thực nguồn, retry từ producer, downtime, duplicate và ordering. Chọn pattern dựa trên **hợp đồng tích hợp và khả năng vận hành**, không theo sở thích công nghệ.

## 18. Checklist ra quyết định trước khi đưa polling lên production

### 18.1. Checklist về lựa chọn pattern

- [ ] Nguồn **không có hoặc không phù hợp** cơ chế push/listener theo nhu cầu, nên polling có lý do rõ ràng.
- [ ] Đã phân biệt poll **external MessageSource** với poll **PollableChannel** trong Spring Integration.
- [ ] Đã xác định thông lượng dự kiến, độ trễ chấp nhận được và giới hạn của nguồn.
- [ ] Có hợp đồng về đơn vị message, schema, encoding, stable business key và cách biết dữ liệu hoàn tất.
- [ ] Poller được cấu hình fixed delay/rate/cron có chủ ý và có timezone khi cần.
- [ ] `maxMessagesPerPoll`, receive timeout và network timeout được hiểu và kiểm thử riêng.
- [ ] Đã xác định khi nào dùng DirectChannel, QueueChannel, ExecutorChannel hoặc durable broker.

### 18.2. Checklist về tính đúng và an toàn

- [ ] Có chiến lược chống duplicate qua retry/restart và, nếu áp dụng, multi-instance.
- [ ] Đã mô tả biên transaction, ack/mark processed và tác động downstream không thể rollback.
- [ ] Không xóa hoặc archive dữ liệu nguồn trước khi đạt điều kiện hoàn tất được định nghĩa.
- [ ] Có cách xử lý poison message, quarantine/DLQ và replay được quản trị.
- [ ] Concurrency và ordering có hợp đồng; không để phiên bản cũ ghi đè trạng thái mới.
- [ ] Metadata store, lock/lease hoặc cơ chế claim phù hợp với nguồn và topology.
- [ ] Credential kết nối được bảo vệ, không ghi vào logs hay payload không cần thiết.
- [ ] App có quyền truy cập file/DB/broker tối thiểu; không dùng credential quản trị rộng ngoài nhu cầu.

### 18.3. Checklist vận hành và phục hồi

- [ ] Có metrics về poll attempts, empty polls, processing success, retry, backlog age và last successful commit.
- [ ] Có cảnh báo **no progress** khi nguồn còn work nhưng consumer không xử lý được.
- [ ] Có runbook cho source unavailable, malformed data, target timeout và retry sau crash.
- [ ] Startup, graceful shutdown và rolling deployment được thử.
- [ ] Nếu có nhiều replica, đã mô phỏng duplicate/lease expiration/failover.
- [ ] Có bằng chứng kiểm thử âm tính và fault injection trong môi trường được phép.
- [ ] Người trực có thể phân biệt lỗi poll source với lỗi parser, handler hoặc outbound adapter.

### 18.4. Cây quyết định ngắn

~~~mermaid
flowchart TD
    START{"Nguồn có cách push/listener phù hợp?"}
    START -->|Có| PUSH["Đánh giá event-driven\nAck, retry, ordering"]
    START -->|Không / không phù hợp| POLL{"Dữ liệu đang nằm ở đâu?"}
    POLL -->|File/SFTP/DB/HTTP| SOURCE["Source polling endpoint\nMessageSource + Poller"]
    POLL -->|QueueChannel nội bộ| CHANNEL["PollingConsumer\nPollableChannel + Poller"]
    SOURCE --> CONTRACT["Data contract + ready/claim"]
    CHANNEL --> CONTRACT
    PUSH --> CONTRACT
    CONTRACT --> SAFE["Idempotency + transaction/ack + error flow"]
    SAFE --> OPS["Backpressure + observability + recovery"]
    OPS --> PROD["Kiểm thử lại trước production"]
~~~

Nếu bạn không trả lời được **“dữ liệu được coi là đã nhận thành công ở thời điểm nào?”**, chưa nên tối ưu `fixedDelay` hoặc tăng concurrency. Hãy làm rõ ngữ nghĩa thành công và khả năng khôi phục trước.

## 19. Câu hỏi tự kiểm tra và tổng kết

### 19.1. Tự trả lời

1. **Polling Consumer** khác **Event-Driven Consumer** ở hành động nào quyết định thời điểm nhận message?
2. Một inbound file adapter dùng `MessageSource` sẽ tạo kiểu polling endpoint nào trong Spring Integration?
3. Vì sao service activator nhận từ `QueueChannel` cần poller, còn handler nhận từ `DirectChannel` thường không?
4. `maxMessagesPerPoll(10)` có nghĩa 10 thread song song hay 10 file luôn được xử lý thành công không?
5. Nếu `receiveTimeout` tăng, điều đó có tự sửa được timeout TCP ở SFTP không?
6. Vì sao file accept-once filter trong bộ nhớ không đủ ngăn duplicate sau restart?
7. Khi DB ghi thành công rồi process chết trước khi mark file processed, cần kiểm soát nào?
8. Khi hai replica cùng poll bảng outbox, vì sao `SELECT status='READY'` chưa đủ?
9. Một Kafka client dùng `poll()` có tự động đồng nghĩa Spring Integration `PollingConsumer` không?
10. Metric nào giúp phát hiện một poller vẫn sống nhưng dữ liệu ở nguồn ngày càng tồn đọng?

**Gợi ý đối chiếu:** (1) pull theo lịch so với được thông báo/đẩy; (2) `SourcePollingChannelAdapter`; (3) `QueueChannel` là `PollableChannel`, `DirectChannel` là `SubscribableChannel`; (4) không; (5) không; (6) metadata không bền/chia sẻ; (7) idempotency và khôi phục an toàn; (8) cần claim/lock/transaction; (9) không; (10) backlog age cùng last successful commit.

### 19.2. Ghi nhớ

**Polling Consumer Pattern** giúp ứng dụng chủ động lấy message từ nguồn hoặc kênh không tự đẩy dữ liệu. Trong **Spring Integration** có hai hình thức trọng tâm:

- **`SourcePollingChannelAdapter`** poll một **`MessageSource`**: phù hợp file, SFTP, JDBC hay nguồn ngoài có thể đọc theo lịch.
- **`PollingConsumer`** poll một **`PollableChannel`** như **`QueueChannel`** rồi gọi handler.

Poller điều phối **khi nào thử nhận** và **thử nhận bao nhiêu**, không quyết định một mình việc **khi nào nghiệp vụ thật sự hoàn tất**. Khi ghép inbound/outbound adapter, gateway và `MessageChannel` để đi qua file, SFTP, HTTP, JMS, AMQP, Kafka hoặc database, luôn xác định **message contract, ack/transaction, quyền sở hữu dữ liệu, retry, idempotency, backpressure, lifecycle kết nối và kiểm toán** theo semantics của từng hệ thống.

**Quy tắc cuối cùng:** *Đừng chỉ kiểm tra poller đã nhận message; hãy chứng minh message đã được xử lý đúng, không tạo tác động trùng ngoài ý muốn và có thể phục hồi khi bất kỳ bước nào thất bại.*
