# Poller gửi lỗi đến error-channel trong Spring Integration

## 1. Bài toán: ai nhận exception khi poller chạy theo lịch?

Trong module **SPRING_INTEGRATION_ADAPTERS**, Spring Integration kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và MessageChannel. Một số nguồn, như thư mục File, SFTP hoặc truy vấn JDBC, thường được đọc bằng **polling consumer/source**: scheduler định kỳ đánh thức một endpoint để lấy message rồi chuyển qua các bước xử lý.

Giả sử ứng dụng quét thư mục mỗi ba giây:

1. File inbound adapter phát hiện một file CSV mới.
2. Poller nhận file dưới dạng Spring Message.
3. Message đi qua transformer, service activator và JDBC outbound handler.
4. Database tạm không khả dụng; handler ném exception.

Ở đây không có một HTTP caller đang chờ trên cùng call stack để nhận exception. Nếu tác vụ được scheduler kích hoạt và không có error strategy thích hợp, lỗi có thể chỉ xuất hiện ở logging của scheduler hoặc gây tác động ngoài dự kiến. Spring Integration cung cấp cơ chế **bắt exception trong vòng poll và publish một ErrorMessage đến error channel**.

**Poller gửi lỗi đến error-channel** có nghĩa: khi một polling task được cấu hình với cơ chế error publishing và gặp exception trong phạm vi mà cơ chế đó xử lý, exception được biểu diễn thành **ErrorMessage** rồi gửi đến **MessageChannel dành cho lỗi**, thay vì phải được trả về caller đồng bộ ban đầu.

Điều cần lưu ý ngay:

- **Exception không tự biến thành ErrorMessage trong mọi flow.** Cần có poller/error handler thực sự bắt và publish lỗi.
- **errorChannel toàn cục không phải retry queue.** Nó là nơi vận chuyển message lỗi; recovery cần thiết kế riêng.
- **ErrorMessage thành công không chứng minh message nguồn đã được xử lý lại hoặc rollback.** File filter, DB transaction, broker acknowledgment và các side effect có vòng đời riêng.
- **Một lỗi trước khi tạo Message** (ví dụ SFTP không kết nối được) có thể không có failedMessage hay file payload.
- **Kênh lỗi chuyên dụng** cho một poller có thể phù hợp hơn global errorChannel khi cần quarantine, alert, retry hoặc SLA riêng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **polling source**, **polling consumer** và **message-driven endpoint**.
2. Giải thích exception nào đi qua poller error handler và vai trò của **MessagePublishingErrorHandler**.
3. Cấu hình Java DSL để poller gửi ErrorMessage đến một kênh lỗi riêng.
4. Sử dụng **ErrorMessage**, **MessagingException**, **failedMessage**, **originalMessage** và correlation ID an toàn.
5. Phân biệt lỗi trong **receive/poll**, **transform/handle** và **send/outbound**.
6. Thiết kế retry, backoff, quarantine, idempotency và transaction theo adapter.
7. Viết integration test, quan sát metrics và xử lý khi chính error flow thất bại.

## 2. Poller là gì và nằm ở đâu trong flow?

Spring Integration có các endpoint chủ động lấy dữ liệu theo chu kỳ hoặc tiêu thụ message từ một channel có khả năng lưu trữ. Ví dụ:

- **File inbound adapter:** tìm file trong một thư mục theo lịch.
- **SFTP inbound adapter:** dò/tải file từ máy chủ bên ngoài.
- **JDBC polling inbound adapter:** truy vấn các bản ghi đang chờ.
- **QueueChannel + polling consumer:** nhận message đã nằm trong channel và xử lý theo lịch.
- **Nguồn tùy biến:** MessageSource tự viết gọi một API hoặc đọc dữ liệu theo lịch.

### 2.1. Hai mô hình thường gặp

~~~mermaid
flowchart LR
    subgraph SourcePolling["Polling inbound source"]
        T1["Scheduler"] --> P1["Source poller"]
        P1 --> SRC["File / SFTP / JDBC MessageSource"]
        SRC --> CH1["MessageChannel"]
        CH1 --> H1["Handler"]
    end
    subgraph ConsumerPolling["Polling consumer"]
        PROD["Producer"] --> Q["QueueChannel"]
        T2["Scheduler"] --> P2["Consumer poller"]
        P2 --> Q
        Q --> H2["Service activator"]
    end
~~~

**Source poller** chủ động gọi MessageSource để nhận dữ liệu. **Consumer poller** chủ động đọc từ một PollableChannel. Cả hai có thể xử lý message ngoài call stack ban đầu của producer.

### 2.2. Poller không phải mọi adapter inbound

HTTP inbound gateway thường xử lý request khi client kết nối, không cần poller định kỳ. JMS/AMQP message-driven inbound adapter và Kafka message-driven inbound adapter thường dùng **listener/container** có cơ chế exception/acknowledgment riêng. Kafka consumer thực chất dùng poll ở giao thức client, nhưng điều đó **không đồng nghĩa** ứng dụng đang dùng Spring Integration PollerSpec.

Do đó, khi nói **poller gửi lỗi tới error-channel**, bài học chủ yếu nói về **polling endpoint của Spring Integration**, không phải mọi listener của JMS, AMQP hay Kafka.

### 2.3. Một chu kỳ poll

~~~text
Scheduler đánh thức tác vụ
   |
   v
Poller gọi receive() trên MessageSource / PollableChannel
   |
   +-- Không có message --> kết thúc lần poll bình thường
   |
   +-- Có message --> gửi tới output channel / handler
                         |
                         +-- Thành công: tiếp tục theo poll policy
                         |
                         +-- Exception: error strategy của tác vụ xử lý
                                              |
                                  ErrorMessage (nếu được publish)
                                              |
                                         error-channel
~~~

Việc một chu kỳ tiếp tục lấy message khác sau khi xảy ra exception phụ thuộc poller configuration, error handler, advice và triển khai của endpoint. Đừng dựa vào giả định “một file lỗi chỉ ảnh hưởng file đó” khi chưa kiểm thử.

## 3. Ngoại lệ đi từ poller sang ErrorMessage thế nào?

### 3.1. Những thành phần đóng vai trò

| Thành phần | Vai trò trong đường lỗi |
|---|---|
| TaskScheduler hoặc tác vụ định kỳ | Đánh thức polling endpoint |
| Polling consumer / source poller | Receive message và kích hoạt xử lý |
| Error handler của tác vụ | Nhận exception nếu lỗi nằm trong phạm vi được bao |
| MessagePublishingErrorHandler | Một cơ chế Spring Integration publish exception thành ErrorMessage |
| ErrorMessageStrategy | Dựng ErrorMessage từ Throwable và context được cung cấp |
| errorChannel / dedicated error channel | MessageChannel chuyển lỗi tới subscriber |
| Service Activator / LoggingHandler | Quan sát, phân loại, tạo nhiệm vụ recovery |

Hành vi cụ thể có thể thay đổi theo **phiên bản Spring Integration**, task scheduler tùy biến, executor, poller advice và cấu hình endpoint. Không phải task scheduler tùy ý nào của Spring Framework cũng mặc định biết global errorChannel.

### 3.2. Sơ đồ logic đường lỗi

~~~mermaid
flowchart TD
    SCH["TaskScheduler"] --> POLL["Spring Integration poller"]
    POLL --> RECEIVE["receive()"]
    RECEIVE --> HANDLE["send/transform/handle"]
    RECEIVE -. "Exception nhận dữ liệu" .-> EH["Poller error handler"]
    HANDLE -. "Exception trong phạm vi poller" .-> EH
    EH --> BUILDER["ErrorMessageStrategy"]
    BUILDER --> EMSG["ErrorMessage: payload Throwable"]
    EMSG --> DEST{"Error destination?"}
    DEST -->|"Poller-specific"| LOCAL["filePollErrors"]
    DEST -->|"Global fallback"| GLOBAL["errorChannel"]
    LOCAL --> OWN["Application error handler"]
    GLOBAL --> LOG["Logging/monitoring subscribers"]
~~~

Sơ đồ là mô hình khái niệm, không khẳng định cả hai trường hợp đều có đầy đủ originalMessage/failedMessage hay adapter luôn dùng đúng error handler đó.

### 3.3. Những loại lỗi có thể được bắt

- **Receive-time:** File/SFTP/JDBC source ném exception khi quét, truy vấn, lấy session, đọc file hoặc tạo Message.
- **Process-time:** transformer hoặc service activator ném exception trong lời gọi đang thuộc poll task.
- **Send-time:** việc gửi message tới channel/handler thất bại, ví dụ không có subscriber hoặc outbound endpoint ném exception đồng bộ.
- **Advice-time:** retry/transaction advice ném exception cuối cùng hoặc recovery callback ném lỗi; phải kiểm tra thứ tự và trách nhiệm các advice.

**Ranh giới thread rất quan trọng.** Nếu handler bàn giao việc sang ExecutorChannel, outbound async client, scheduler khác hoặc broker, lỗi xuất hiện về sau có thể nằm ngoài stack poller ban đầu. Poller error-channel **không thể tự nhận mọi lỗi của tác vụ đã tách thread**.

## 4. errorChannel mặc định và kênh riêng của poller

### 4.1. Kênh toàn cục

Spring Integration có tên chuẩn **errorChannel** cho kênh lỗi toàn cục trong cấu hình mặc định. Trong cấu hình framework thông dụng, kênh đó là **PublishSubscribeChannel** kèm LoggingHandler. Khi một error publisher không có destination riêng, nó có thể gửi ErrorMessage tới kênh này.

Nhưng **global errorChannel là điểm quan sát tổng quát**; nó không nên mặc định thực hiện hành động sửa dữ liệu chuyên biệt cho mọi luồng trong ứng dụng.

### 4.2. Kênh riêng theo poller

Trong Java DSL, có thể đặt **errorChannel("filePollErrors")** trên poller specification để điều hướng những exception poller chuyển thành ErrorMessage tới một MessageChannel cụ thể. Kênh riêng thuận tiện để:

- Phân biệt lỗi import file với lỗi poller JDBC;
- Gắn business owner và SLA khác nhau;
- Cách ly file lỗi, phân loại SFTP timeout, tạo retry ticket;
- Tránh subscriber chung áp dụng nhầm recovery policy;
- Kiểm thử đường lỗi một cách độc lập.

### 4.3. Cấu hình kênh nào thì kênh đó nhận lỗi?

| Tình huống | Kết quả cần mong đợi và kiểm tra |
|---|---|
| Poller có error channel riêng và có publisher phù hợp | ErrorMessage tới kênh riêng |
| Poller dùng global fallback | ErrorMessage tới errorChannel toàn cục |
| Request message mang header errorChannel | Một số error publisher có thể ưu tiên header theo cơ chế của chúng; cần test với poller |
| Exception trong DirectChannel đồng bộ ngoài task poller | Thường throw về sender, không tự động publish |
| Lỗi async sau khi poller đã giao message | Thuộc error strategy của executor/async flow, không mặc nhiên về poller |
| Listener JMS/AMQP/Kafka không dùng PollerSpec | Đường lỗi chịu adapter/container policy |

**Chính sách chọn error channel không phải một quy luật ưu tiên áp dụng giống nhau cho mọi adapter.** Nếu application cần routing bảo đảm, hãy cấu hình rõ endpoint, rồi viết test để xác minh error destination.

### 4.4. Vì sao thêm Service Activator trên errorChannel chưa đủ?

Đăng ký subscriber chỉ giúp **nhận những ErrorMessage đã được publish**. Nếu source poller sử dụng một task scheduler tùy biến không có error publishing, hoặc exception đã được retry advice bắt và phục hồi, có thể không có ErrorMessage tương ứng. Hãy kiểm tra **nơi exception được bắt và có publish hay không**.

## 5. ErrorMessage, failedMessage và originalMessage của poller

### 5.1. Cấu trúc dữ liệu

**ErrorMessage** là Spring Message có payload kiểu Throwable. Payload có thể là **MessagingException**, **MessageHandlingException**, **MessageDeliveryException** hoặc Throwable khác. Nếu là MessagingException, **getFailedMessage()** có thể trả Message ở điểm xảy ra lỗi; giá trị có thể null.

ErrorMessage cũng có **getOriginalMessage()**, nhưng chỉ tồn tại nếu ErrorMessageStrategy/constructor được cấp input message. Không nên giả định mọi lỗi đều có message gốc.

~~~text
ErrorMessage
  payload: Throwable
    (có thể là MessagingException)
        failedMessage: Message<?> hoặc null
        cause: Throwable hoặc null
  originalMessage: Message<?> hoặc null
  headers: id, timestamp, ... của error message
~~~

### 5.2. Lỗi trước khi nhận message

Ví dụ SFTP inbound source không mở được session và ném exception **trước khi có một File Message**. Khi đó:

- Có thể publish ErrorMessage với Throwable từ lỗi kết nối;
- failedMessage hoặc originalMessage có thể null;
- Không nên cố cast failedMessage.payload thành File;
- Dùng endpoint ID, remote directory, source ID và safe connection metadata để tìm nguyên nhân;
- Phục hồi theo connection/backoff, không phải quarantine một file chưa xác định.

### 5.3. Lỗi sau khi đã nhận message

Ví dụ FileReadingMessageSource đã tạo message với File payload, handler đọc CSV rồi ném exception:

- MessagingException có thể chứa failedMessage với File hoặc payload đã transform;
- originalMessage có thể chứa input được cung cấp cho error strategy;
- Correlation ID có thể tìm từ failedMessage, originalMessage hoặc state store;
- Cần lưu file reference trước khi retry vì message trong bộ nhớ không phải kho dữ liệu bền vững.

### 5.4. Header errorChannel

**MessageHeaders.ERROR_CHANNEL** là header điều khiển chọn kênh lỗi khi thành phần error publishing hỗ trợ. Nó không phải payload Throwable và không tự sinh ErrorMessage. Không nên lấy một header chỉ định kênh nội bộ từ file/HTTP client bên ngoài mà không kiểm soát, vì có thể gây định tuyến lỗi sai hoặc lộ dữ liệu.

## 6. Java DSL: cấu hình File poller gửi lỗi tới kênh riêng

### 6.1. Phạm vi ví dụ

Ví dụ minh họa dùng **Spring Integration Java DSL** trong một ứng dụng Spring có các dependency core và file adapter thích hợp. Ứng dụng có thư mục data/inbox chứa CSV; cứ hai giây poller tìm file và gọi handler. Handler **cố tình ném exception** để kiểm tra đường lỗi.

Các class dùng API Java DSL thông dụng của những phiên bản Spring Integration hiện đại; trước khi dùng trong dự án thật cần đối chiếu overload và kiểu cấu hình với dependency đã chọn. Dự án sử dụng Java phiên bản đủ mới để hỗ trợ các cú pháp mẫu.

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

@Configuration
@EnableIntegration
public class FilePollErrorConfiguration {

    @Bean
    public MessageChannel filePollErrors() {
        return new PublishSubscribeChannel();
    }

    @Bean
    public IntegrationFlow csvImportFlow() {
        return IntegrationFlow
                .from(Files.inboundAdapter(new File("data/inbox"))
                                .autoCreateDirectory(true)
                                .patternFilter("*.csv"),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(2))
                                        .maxMessagesPerPoll(1)
                                        .errorChannel("filePollErrors")))
                .handle(message -> {
                    File file = (File) message.getPayload();
                    // Chỉ dùng để chứng minh poller error handling.
                    throw new IllegalStateException(
                            "Demo parse failure: " + file.getName());
                })
                .get();
    }

    @ServiceActivator(inputChannel = "filePollErrors")
    public void handleFileError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        System.err.println("File poll failure: "
                + failure.getClass().getSimpleName());
    }
}
~~~

Đây là ví dụ học thuật **cố tình ném lỗi**. Trong production dùng logger có cấu trúc thay cho System.err, không in toàn bộ file hoặc payload nhạy cảm, và đưa file sai vào quarantine theo trạng thái nghiệp vụ.

### 6.2. Đọc từng phần cấu hình

1. **Files.inboundAdapter:** tạo nguồn nhận File từ thư mục.
2. **endpoint.poller:** cấu hình polling endpoint chạy theo khoảng thời gian.
3. **maxMessagesPerPoll(1):** giới hạn số message nhận trong một lần poll theo cấu hình tương ứng; không thay số lần retry.
4. **errorChannel("filePollErrors"):** chỉ định destination cho ErrorMessage do error handling của poller publish.
5. **filePollErrors bean:** channel tồn tại trong Spring context.
6. **@ServiceActivator:** subscriber nhận ErrorMessage từ kênh chuyên dụng.

Nếu có file và poller chạy, exception từ handler trong phạm vi đồng bộ của polling task sẽ được error strategy xử lý theo cấu hình. Trong thực tế, kiểm tra integration test và log để xác minh message tới kênh đúng.

### 6.3. Nếu bỏ errorChannel ở PollerSpec?

Khi poller dùng cơ chế **MessagePublishingErrorHandler với fallback toàn cục**, exception có thể được publish tới **errorChannel** mặc định. Cấu hình subscribe:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class GlobalErrorObserver {

    @ServiceActivator(inputChannel = "errorChannel")
    public void observe(ErrorMessage error) {
        System.err.println("Global integration failure: "
                + error.getPayload().getClass().getSimpleName());
    }
}
~~~

Chú ý: Global errorChannel thường có **LoggingHandler mặc định**. Một subscriber khác có thể làm log cùng lỗi hai lần. Và nếu đã cấu hình filePollErrors chuyên dụng, không mặc định global observer cũng sẽ nhận bản sao lỗi từ flow đó.

### 6.4. Có cần tự khai báo bean errorChannel không?

Không cần để chỉ lắng nghe lỗi trên global channel đã được framework cung cấp. Tự định nghĩa bean cùng tên có thể thay đổi topology, subscriber và cách xử lý. Khi cần chính sách riêng, ưu tiên tạo **filePollErrors** hoặc channel có tên nghiệp vụ rõ ràng.

### 6.5. Hướng thay cho annotation hoặc XML

Trong hệ thống dùng annotation-based inbound adapter, có thể gắn **@Poller** tại endpoint để định nghĩa lịch, max messages và error channel theo API của phiên bản đó. Với XML namespace của Spring Integration, element poller có thể hỗ trợ thuộc tính **error-channel**. Nguyên tắc vẫn giống Java DSL: **error destination thuộc polling endpoint/error handler, không chỉ thuộc message producer bên ngoài**.

Nếu application vừa khai báo poller global mặc định vừa khai báo poller ở endpoint, cần biết endpoint sẽ nhận cấu hình nào. Đọc cấu hình thực và thử ném exception; đừng cho rằng mọi endpoint dùng chung một error policy.

## 7. Viết handler đọc ErrorMessage an toàn

### 7.1. Không giả định exception luôn là MessagingException

Một Throwable từ lỗi source SFTP có thể không được wrap cùng failedMessage. Handler nên kiểm tra kiểu và fallback sang originalMessage khi có.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class PollingErrorLogger {

    private static final Logger log =
            LoggerFactory.getLogger(PollingErrorLogger.class);

    @ServiceActivator(inputChannel = "filePollErrors")
    public void log(ErrorMessage error) {
        Throwable throwable = error.getPayload();

        Message<?> failed = null;
        if (throwable instanceof MessagingException messageException) {
            failed = messageException.getFailedMessage();
        }

        Message<?> original = error.getOriginalMessage();
        Message<?> context = failed != null ? failed : original;

        Object correlation = context == null
                ? null
                : context.getHeaders().get("correlationId");

        log.error(
                "poller failure type={}, hasFailed={}, hasOriginal={}, correlation={}",
                throwable.getClass().getSimpleName(),
                failed != null,
                original != null,
                correlation,
                throwable);
    }
}
~~~

Trong production, đánh giá việc logging Throwable có thể lộ exception message chứa SQL, URL có token hoặc thông tin cá nhân. Khi cần giảm rủi ro, chỉ log exception class, error category, safe code và correlation; stack trace lưu vào hệ thống log hạn chế quyền đọc.

### 7.2. Truy dấu bằng endpoint/flow ID

Đôi khi cả failed và original đều không có correlation. Nên có:

- **Endpoint ID / flow ID:** định danh nguồn poller trong cấu hình;
- **Business key:** mã đơn, mã batch, tên file được giảm nhạy cảm;
- **Poll attempt:** thời điểm, phiên worker, số lần thử;
- **Source reference:** đường dẫn file đã chuẩn hóa, bảng/record, remote file ID;
- **Error classification:** lỗi dữ liệu, permission, network, DB timeout hay unknown.

Không tự suy business key từ tên file nếu dữ liệu nghiệp vụ có thể bị trùng hoặc nguồn chưa đáng tin. Dùng key bền vững được chuẩn hóa trong ingest pipeline.

### 7.3. Subscriber không nên tự retry vô hạn

Một handler trên errorChannel có thể ghi log hoặc **tạo yêu cầu retry**. Nhưng gọi lại ngay toàn bộ input flow bên trong handler có thể gây:

- Vòng lặp error → retry → error với cùng dữ liệu sai;
- Đọc trùng file đã được filter nhận;
- Side effect trùng ở HTTP/JDBC;
- Scheduler/consumer bị nghẽn do xử lý lỗi quá lâu.

Thay vì vậy, phân loại lỗi và tạo recovery request có **attempt limit**, business key, thời điểm retry, owner và idempotency. Nếu source cần replay, dựa vào file/row/queue state thực thay vì chỉ giữ ErrorMessage trong bộ nhớ.

## 8. Poller lỗi ở receive() khác lỗi ở handler

### 8.1. Lỗi trước khi có message

Ví dụ:

~~~text
Poller tick
  -> SFTP session factory connect()
  -> Authentication failed
  -> Throwable được error strategy nhận
  -> ErrorMessage (không bảo đảm có failedMessage)
  -> sftpPollErrors
~~~

Hành động đúng thường là alert credential/permission và dừng retry dồn dập. Không thể quarantine file chưa hề tải được chỉ vì có ErrorMessage.

### 8.2. Lỗi sau khi có message

~~~text
Poller tick
  -> FileReadingMessageSource.receive() -> Message<File>
  -> transformer parse CSV
  -> Validation failed
  -> ErrorMessage chứa Throwable
     -> có thể chứa failedMessage = File hoặc payload đã transform
  -> filePollErrors
~~~

Tại đây có thể cách ly file; nhưng phải biết **filter đã đánh dấu file, file đã được move/delete hay chưa**. Error channel không làm các thao tác đó tự động.

### 8.3. Lỗi khi gửi tới channel không có subscriber

Một endpoint poller đã nhận message nhưng channel đích hoặc dispatcher từ chối nhận. Lỗi có thể là MessageDeliveryException hoặc exception tương tự. Dù có failedMessage, policy chủ yếu là sửa wiring/availability hoặc bảo tồn input, không phải sửa nội dung CSV.

### 8.4. Bảng phân loại theo giai đoạn

| Giai đoạn | Ví dụ | Context có thể có | Recovery thường phù hợp |
|---|---|---|---|
| RECEIVE | SFTP session timeout | Flow/source ID, chưa chắc có Message | Reconnect, backoff, alert |
| QUERY | JDBC query lỗi | Query ID, DB exception; có thể không có row Message | Retry có kiểm soát hoặc sửa SQL |
| DELIVER | Output channel không có subscriber | Message đã nhận, target channel | Sửa cấu hình, ngăn mất input |
| TRANSFORM | CSV sai schema | failedMessage/File context | Quarantine, phản hồi dữ liệu lỗi |
| HANDLE | DB ghi lỗi | Business key, input đã chuẩn hóa | Kiểm tra commit, idempotent retry |
| OUTBOUND | HTTP timeout | Request ID, endpoint, trạng thái chưa rõ | Tra cứu trạng thái/idempotency |
| ERROR_HANDLER | Subscriber lỗi | ErrorMessage và lỗi thứ cấp | Cơ chế fallback, không để loop |

### 8.5. Không nên coi receive()==null là lỗi

Khi poller không tìm thấy file hoặc QueueChannel rỗng, MessageSource/PollableChannel có thể trả **null**; đây là tình huống bình thường và không nhất thiết phát ErrorMessage. Nếu doanh nghiệp mong mỗi giờ phải có file nhưng không có dữ liệu, cần **monitor last successful poll/last input**, không trông chờ error-channel tự cảnh báo.

## 9. Retry advice và error-channel: lớp nào chịu trách nhiệm?

### 9.1. Hai giai đoạn khác nhau

Trong nhiều flow, retry advice được áp dụng quanh handler để thử lại một hoạt động trước khi ngoại lệ cuối cùng thoát ra. Error publisher có thể chỉ nhận **lỗi sau khi retry exhausted**. Điều này tùy vị trí advice và recovery callback.

~~~text
Poller receives Message
   -> Handler with retry advice
      -> attempt 1: fails
      -> attempt 2: fails
      -> attempt 3: fails
      -> exhausted: throw/recover
   -> Poller error strategy
      -> ErrorMessage nếu exception được propagate/publish
~~~

Nếu recovery callback **đã xử lý exception và trả về giá trị được coi là success**, poller có thể không nhận thêm exception để publish. Ngược lại, một callback có thể tự gửi ErrorMessage tới kênh recovery. Cần kiểm thử để tránh **hai nơi cùng gửi lỗi hoặc hai nơi cùng retry**.

### 9.2. Khi nào retry?

| Nhóm lỗi | Quyết định thường phù hợp |
|---|---|
| Network timeout tạm thời | Retry với exponential backoff, giới hạn |
| DB transient connection | Retry có điều kiện và idempotency |
| HTTP 429/503 | Xem Retry-After, retry theo time budget |
| CSV sai schema | Không retry y nguyên vô hạn; quarantine |
| Credential/permission bị từ chối | Alert và sửa cấu hình; tránh thử dồn dập |
| HTTP timeout sau khi POST | Query trạng thái hoặc dùng idempotency key |
| Message bị consumer khác xử lý trùng | Dedupe/kiểm tra state, không lặp side effect |

### 9.3. Tổng số lần thử có thể bị nhân lên

Nếu HTTP client retry 3 lần, handler advice retry 3 lần, poller lại đọc file sau restart và broker bên ngoài cũng redeliver, số request thực tế có thể lớn hơn nhiều so với “retry 3 lần”. Cần có **global attempt budget theo business key** hoặc một nơi chịu trách nhiệm chính cho retry của từng bước.

### 9.4. Không giả định ErrorMessage đồng nghĩa đã lưu dữ liệu để retry

PublishSubscribeChannel và nhiều MessageChannel khác hoạt động trong bộ nhớ. Nếu process crash, chỉ có error message trong channel chưa chắc có thể phục hồi. Với yêu cầu at-least-once cần durable input, state store/outbox, transaction và replay logic phù hợp.

### 9.5. Thứ tự của advice chain quan trọng

Nếu một advice dùng transaction và một advice khác retry, thứ tự bao quanh handler có thể thay đổi ranh giới rollback và số lần thử trên cùng transaction. Không áp dụng một công thức cố định khi chưa xét loại resource, transaction manager và cấu hình endpoint thực; dùng test giả lập lỗi từng bước để xác định semantics.

## 10. Poller nhận nhiều message và hành vi khi một message lỗi

### 10.1. Vai trò của maxMessagesPerPoll

**maxMessagesPerPoll** giới hạn số message được poller lấy trong một lần kích hoạt theo cấu hình. Nó **không** phải số lần retry. Một lỗi xảy ra ở message thứ hai có thể làm dừng xử lý của lượt poll hoặc ảnh hưởng các message còn lại tùy cách poller/error strategy vận hành.

### 10.2. Lỗi đơn lẻ không nên làm mất cả batch

Với file CSV, một file có thể chứa nhiều dòng. Nếu ứng dụng import theo từng row nhưng transaction và file filter được thiết kế không rõ, một row lỗi có thể khiến:

- Các row trước đã commit vẫn tồn tại;
- Row lỗi phải được sửa hoặc cách ly;
- Những row sau chưa được xử lý;
- File bị filter đánh dấu là đã nhận;
- Khi replay file, các row trước bị xử lý lại.

Vì vậy cần định nghĩa **đơn vị xử lý và acknowledgment**: theo file, theo batch hay theo từng record. Nếu toàn file là một transaction, cần cân nhắc nguồn dữ liệu ngoài DB và tác động outbound.

### 10.3. Tránh starvation

Một file poison luôn gây exception có thể chiếm lượt poll, làm các file tốt không được xử lý. Cần quarantine, skip policy có kiểm soát, idempotent state và alert, thay vì tiếp tục quét lại cùng dữ liệu lỗi vô hạn.

### 10.4. Backpressure và concurrency

Tăng poller frequency hoặc thêm taskExecutor có thể làm throughput cao hơn nhưng cũng làm tăng:

- Số kết nối SFTP/DB đồng thời;
- Rủi ro hai worker nhận cùng file/record;
- Tỷ lệ lỗi network do overload;
- Khó truy vết lỗi khi tác vụ async đã tách thread;
- Backlog trên error channel hoặc recovery queue.

Cần phối hợp **task executor, lock/claim source, idempotency, receiveTimeout và capacity** của channel. Không chỉ tăng thread count để xử lý lỗi nhiều hơn.

## 11. File polling: quản lý filter, trạng thái file và quarantine

### 11.1. Vì sao lỗi đã vào error channel vẫn có thể mất file?

FileReadingMessageSource thường kết hợp các bộ lọc để chọn file. Khi một file đã được lựa chọn, **filter và metadata store** có thể ghi nhận file đã được tiếp nhận trước khi handler nghiệp vụ hoàn tất. Nếu handler ném exception sau đó, một subscriber errorChannel chỉ ghi log không tự hoàn tác trạng thái lọc.

Ví dụ:

~~~text
09:00:00  Poller thấy invoice-274.csv
09:00:00  Filter nhận file và ghi trạng thái "seen"
09:00:01  Handler JDBC lỗi
09:00:01  ErrorMessage được gửi tới filePollErrors
09:00:01  Error handler ghi log rồi kết thúc
09:00:03  Poller chạy lại, file không được chọn do filter
~~~

Trong trường hợp này, dữ liệu nghiệp vụ chưa xử lý thành công nhưng file có thể không được đọc lại. Hành vi cụ thể phụ thuộc **filter, persistent metadata store, cách cấu hình accept-once, việc di chuyển/xóa file và restart**.

### 11.2. State machine cho file import

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED
    DETECTED --> CLAIMED: Poller nhận file
    CLAIMED --> VALIDATING: Đọc và kiểm tra schema
    VALIDATING --> PROCESSING: Dữ liệu hợp lệ
    VALIDATING --> QUARANTINED: Dữ liệu sai
    PROCESSING --> PROCESSED: Ghi nghiệp vụ thành công
    PROCESSING --> RETRY_WAIT: Lỗi tạm thời
    RETRY_WAIT --> PROCESSING: Đến hạn retry
    RETRY_WAIT --> MANUAL_REVIEW: Hết giới hạn
    PROCESSED --> ARCHIVED: Lưu theo chính sách
    QUARANTINED --> [*]
    ARCHIVED --> [*]
~~~

Sơ đồ là mô hình nghiệp vụ đề xuất, không phải các state mặc định của FileReadingMessageSource. Nên lưu trạng thái trong kho bền vững hoặc theo quy trình file move/rename có khả năng kiểm chứng.

### 11.3. Phân biệt error recovery và file replay

| Lỗi | Xử lý tại error channel | Xử lý nguồn file |
|---|---|---|
| CSV sai cấu trúc | Ghi INVALID_INPUT, cảnh báo producer | Quarantine file, không poll lại vô hạn |
| JDBC không khả dụng | Ghi TRANSIENT, tạo retry task | Giữ bản sao input an toàn, replay idempotent |
| File chưa được ghi xong | Ghi hoặc giám sát source state | Chờ file ổn định trước khi ingest |
| File bị khóa hoặc permission denied | Alert vận hành | Sửa quyền/lock, tránh retry dồn dập |
| File đã xử lý một phần | Ghi PARTIAL/UNKNOWN | Đối soát từng record hoặc transaction batch |

### 11.4. Quarantine phải có owner và quy tắc replay

Một file bị cách ly không nên chỉ được copy vào thư mục errors vô thời hạn. Cần biết ai xử lý, lý do lỗi, batch/business key, hash hoặc checksum phù hợp, version parser, retention, và cách replay sau khi dữ liệu sửa. **Không tự sửa/sao chép file từ ErrorMessage nếu file đã bị tiến trình khác thay đổi**.

### 11.5. File outbound phát sinh lỗi trong poller

Một inbound File poller có thể gọi FileWritingMessageHandler để xuất file. Nếu handler xuất lỗi đồng bộ trong cùng polling task, exception có thể được error handler của poller publish. Nhưng nếu file đã được ghi một phần, ErrorMessage không xóa file dở. Nên ghi vào temporary path và rename atomically theo khả năng filesystem, kiểm tra kết quả trước khi đánh dấu xử lý thành công.

## 12. SFTP poller: session, đồng bộ tệp và retry phù hợp

### 12.1. Hai nhóm lỗi khác nhau

SFTP inbound có thể gặp lỗi **ở mức remote session** trước khi có Message hoặc lỗi **ở local downstream handler** sau khi đã đồng bộ được file.

~~~mermaid
flowchart TD
    P["SFTP poller"] --> CONN["Mở session/list remote directory"]
    CONN -->|"Không thành công"| NET["Connection/auth/permission error"]
    CONN -->|"Thành công"| TRANS["Download hoặc nhận remote file"]
    TRANS -->|"Thành công"| MSG["Message<File> hoặc dạng được cấu hình"]
    TRANS -->|"Partial transfer"| PART["Incomplete file state"]
    MSG --> PARSE["Parse/validate/business handler"]
    PARSE -->|"Lỗi"| DATA["Data processing error"]
    NET --> E["Error publisher nếu được cấu hình"]
    PART --> E
    DATA --> E
    E --> EC["sftpPollErrors"]
~~~

Nếu session fail trước khi Message hình thành, handler không được giả định có failedMessage. Trong khi đó lỗi parse sau khi download có thể gắn với local file; **remote file không tự được phục hồi** theo thông tin của ErrorMessage.

### 12.2. Chiến lược phục hồi SFTP

| Tình huống | Hành động |
|---|---|
| Timeout hoặc mất mạng tạm thời | Backoff, kết nối lại có giới hạn |
| Authentication thất bại | Alert, sửa secret/credential; không thử dồn dập |
| Remote permission denied | Xác minh ACL và đường dẫn |
| Remote file đang upload dở | Chờ rename/marker hoặc kiểm tra ổn định theo contract |
| Download một phần | Không đưa local partial file vào parser |
| CSV đã tải nhưng sai schema | Quarantine bản local, thông báo đối tác |
| Upload outbound thành công nhưng mất response | Xác minh checksum/remote path trước khi gửi lại |

### 12.3. Ranh giới remote/local

Một hệ thống SFTP inbound thường có remote filter và local filter hoặc một cơ chế metadata store để nhận diện file. Có thể xảy ra:

- Server đã đánh dấu remote file là đã chuyển nhưng local processing thất bại;
- Local file đã tồn tại nhưng message chưa tới handler;
- Remote file được đối tác ghi lại với cùng tên;
- Hai poller từ nhiều instance cùng nhìn thấy một file;
- Tên file giống nhau nhưng nội dung khác nhau.

Do đó, recovery cần **remote file identity/version, metadata store, local ready state và idempotency theo business key**. Chỉ đặt .errorChannel("sftpPollErrors") không đủ bảo đảm không mất hoặc trùng file.

### 12.4. Lỗi outbound SFTP khi poller đang xử lý

Một polling consumer có thể đọc công việc từ QueueChannel rồi upload file ra SFTP. Nếu session factory/remote write ném exception đồng bộ, poller có thể publish ErrorMessage. Nhưng nếu command đã bị lấy khỏi QueueChannel, cần biết nó còn tồn tại ở đâu để thử lại. Với workflow quan trọng nên dùng **durable task store/queue** hoặc cơ chế transaction/ack phù hợp.

### 12.5. Không để đường xử lý lỗi làm hỏng session quản trị

Error handler nên tránh cố mở kết nối SFTP lặp ngay trong cùng thread với failed poll khi server đang lỗi. Việc gửi email cảnh báo hay gọi API kiểm tra có thể block scheduler. Có thể phân loại nhanh, lưu recovery task rồi xử lý độc lập qua worker có giới hạn tài nguyên.

## 13. JDBC poller: query fail, row state và transaction

### 13.1. Poller nhận bản ghi từ DB

JDBC inbound polling có thể truy vấn các record pending theo chu kỳ:

~~~sql
SELECT id, tenant_id, order_id, payload_ref
FROM integration_work
WHERE state = 'PENDING'
ORDER BY created_at;
~~~

Đây là ví dụ truy vấn khái niệm. Khi triển khai cần giới hạn số row, lựa chọn index, transaction/locking và tránh nhiều instance claim trùng; không chạy SELECT không giới hạn trên bảng lớn.

### 13.2. Lỗi ở lúc query

Nếu DB unavailable hoặc SQL sai, source có thể ném exception **trước khi tạo Message chứa row**. ErrorMessage có thể chứa DataAccessException hoặc MessagingException nhưng failedMessage có thể null. Lúc này không thể biết chắc row nào đang bị xử lý chỉ từ exception, vì lỗi xảy ra trước receive thành công.

Hướng vận hành:

- Đánh dấu source/DB unavailable và retry có backoff;
- Theo dõi last-successful-query, số record pending và lag;
- Alert khi SQL/permission/config sai liên tục;
- Không đánh dấu hàng loạt record đã xử lý do một event lỗi nguồn.

### 13.3. Lỗi sau khi đã lấy row

Giả sử JDBC inbound poller đã lấy record order-274, outbound HTTP handler gửi POST thành công nhưng JDBC update state=PROCESSED thất bại. Lần poll sau có thể đọc lại order-274:

~~~text
PENDING row order-274
    |
    +--> poller reads
    +--> HTTP POST succeeds
    +--> status update fails
    |
PENDING row order-274 remains
    |
next poll may send HTTP POST again
~~~

Đây là ví dụ **at-least-once processing với nguy cơ side effect trùng**. ErrorMessage cho biết failure nhưng không đảm bảo lời gọi HTTP trước đó chưa thành công.

### 13.4. Claim trạng thái bền vững

Một cách quản lý công việc là sử dụng trạng thái **PENDING → CLAIMED → SUCCEEDED/RETRY/FAILED** với lease, worker ID, attempt và version. Có thể dùng câu lệnh update có điều kiện:

~~~sql
UPDATE integration_work
SET state = 'CLAIMED',
    worker_id = :workerId,
    attempt = attempt + 1
WHERE id = :workId
  AND state = 'PENDING';
~~~

Chỉ xem claim thành công nếu số row update đúng một. Đây là ví dụ logic; với nhiều worker cần thiết kế thêm cơ chế chọn công việc, isolation level, lease expiry và bảo vệ trường hợp worker crash. **Error channel không tự sửa claim đã bị kẹt**.

### 13.5. Transaction trong polling endpoint

Một poller có thể được cấu hình transaction advice để bao một phạm vi xử lý. Nhưng:

- Transaction của DB chỉ bao các thao tác được transaction manager quản lý;
- HTTP/SFTP không tự tham gia local DB transaction;
- Một exception bị error handler **swallow** có thể ảnh hưởng quyết định rollback;
- Lỗi sau DB commit không thể rollback bằng việc phát ErrorMessage;
- Phải kiểm tra behavior của poller, advice chain, source và JDBC handler theo cấu hình.

Muốn đồng bộ giữa DB state và publish command/event, cân nhắc **transactional outbox/inbox** hoặc state machine bền vững. Nếu nhận lại record, phải có idempotency.

## 14. QueueChannel polling consumer: message đã rời queue rồi thì sao?

### 14.1. Điểm khác biệt với inbound file

QueueChannel là một **PollableChannel**. Một producer có thể gửi Message vào QueueChannel; polling consumer nhận nó khi scheduler đánh thức. Khi receive đã lấy message ra khỏi queue, handler thất bại **không mặc nhiên đưa message trở lại queue**.

Điều này đặc biệt quan trọng với **in-memory QueueChannel**: khi process restart, những message chưa xử lý có thể không còn. Nếu yêu cầu durable recovery, cần sử dụng một cơ chế persistence hoặc broker/queue bền vững phù hợp.

### 14.2. Cấu hình Java DSL minh họa

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;

@Configuration
public class QueuedOrderPollingFlow {

    @Bean
    public QueueChannel pendingOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public MessageChannel orderPollErrors() {
        return new PublishSubscribeChannel();
    }

    @Bean
    public IntegrationFlow orderWorker() {
        return IntegrationFlow
                .from(pendingOrders(),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(1))
                                        .maxMessagesPerPoll(5)
                                        .errorChannel("orderPollErrors")))
                .handle(message -> {
                    // Mô phỏng lỗi xử lý OrderCommand.
                    throw new IllegalStateException("Order service unavailable");
                })
                .get();
    }
}
~~~

Kênh orderPollErrors cần có subscriber (ví dụ Service Activator) để nhận ErrorMessage. Mẫu cấu hình phụ thuộc DSL version; mục tiêu chính là thấy **poller gắn với consumer của PollableChannel**, chứ không chỉ với File MessageSource.

### 14.3. Recovery cho queue

Nếu Message đã được lấy khỏi QueueChannel và handler lỗi, không nên chỉ gửi lại cùng Message vào channel từ error handler mà không kiểm soát. Cần:

1. Định nghĩa business key hoặc command ID;
2. Ghi trạng thái đang xử lý trước/đúng thời điểm cần bảo đảm;
3. Khi lỗi, phân loại transient/permanent;
4. Lưu retry command hoặc chuyển message sang durable recovery store;
5. Chỉ phát lại với retry limit, timeout và idempotency;
6. Xác minh side effect trước khi đánh dấu success.

**Nếu sử dụng QueueChannel với MessageStore bền vững hoặc transaction synchronization**, behavior có thể khác mẫu trong bộ nhớ; phải kiểm thử commit/rollback/receive cụ thể.

## 15. Poller và các adapter HTTP, JMS, AMQP, Kafka

### 15.1. HTTP outbound được gọi từ một polling flow

Một File hoặc JDBC poller có thể đưa message tới HTTP outbound gateway. Nếu lời gọi HTTP ném exception **đồng bộ trong cùng stack xử lý của poller**, lỗi có thể tới errorChannel được cấu hình cho poller. Nhưng:

- HTTP status 4xx/5xx được ném exception hay trả response tùy client/gateway configuration;
- Một HTTP timeout không chứng minh đối tác chưa xử lý request;
- Nếu gateway dùng async execution, callback lỗi có thể nằm ngoài stack poller;
- Inbound HTTP gateway thường xử lý request chứ không dùng poller này.

Retry các thao tác HTTP ghi dữ liệu nên có **Idempotency-Key** theo contract của đối tác hoặc tra cứu trạng thái để tránh trùng.

### 15.2. JMS và AMQP outbound từ poller

Nếu một polling consumer xử lý command rồi gửi JMS/AMQP qua outbound adapter, lỗi gửi đồng bộ có thể được báo về poller error handling. Tuy nhiên:

- Broker có thể đã chấp nhận message nhưng response/ack phía producer chưa xác định;
- JMS transaction hoặc RabbitMQ publisher confirm có cách xử lý riêng;
- Không thể coi việc publish ErrorMessage là bằng chứng source đã rollback;
- Consumer downstream đã xử lý thì không thể đơn giản “unsend” message.

Với **JMS/AMQP message-driven inbound**, lỗi thường được quản lý bởi **listener container**, ack/nack, requeue, transaction và DLQ. Không nên coi các listener này là PollerSpec chỉ vì chúng liên tục nhận message.

### 15.3. Kafka outbound từ poller

Kafka producer có thể gửi bất đồng bộ. Poller hoàn tất handler trước khi producer callback báo lỗi; khi đó failure **không nhất thiết quay về poller-specific error channel**. Phải cấu hình callback/error handling của Kafka outbound adapter và xác định producer transaction, acknowledgment, retries và DLT/recovery theo contract.

Với **Kafka inbound message-driven adapter**, Kafka listener container và offset handling thuộc cơ chế chuyên biệt, không dùng errorChannel của File poller làm thay thế.

### 15.4. Bảng phân biệt adapter

| Mô hình | Poller-specific error channel có vai trò nào? | Cần kiểm tra thêm |
|---|---|---|
| File poller → HTTP outbound đồng bộ | Có thể bắt exception trong stack poller | HTTP status, timeout, idempotency |
| SFTP poller → JDBC handler | Bắt lỗi receive/handler trong phạm vi poller | Remote file state, DB commit |
| QueueChannel poller → JMS send | Quan sát lỗi xử lý/gửi đồng bộ | Source queue durability, broker accept/tx |
| JDBC poller → Kafka producer async | Không tự bắt callback xuất hiện sau | Producer callback, outbox, ack |
| JMS/AMQP listener → IntegrationFlow | Không mặc nhiên là Spring Integration poller | Ack/nack, listener error handler, DLQ |
| Kafka listener → IntegrationFlow | Không mặc nhiên dùng PollerSpec | Offset, retry, container error handler, DLT |
| HTTP inbound gateway | Không phải periodic poller | HTTP error status/response mapping |

### 15.5. Hệ thống ngoài có thể đã tạo side effect

Khi một handler ném exception, phải hỏi:

- DB đã commit chưa?
- HTTP server đích đã tạo order chưa?
- JMS/AMQP broker đã nhận message chưa?
- Kafka event đã có trên topic chưa?
- File SFTP đã được rename/move/delete chưa?

ErrorMessage không trả lời chắc chắn tất cả câu hỏi đó. Nếu result unknown, hãy **reconcile** trước khi retry hoặc compensate để tránh gây thêm tác động.

## 16. Thiết kế hợp đồng lỗi cho poller

### 16.1. Một ErrorMessage chưa đủ cho hệ thống vận hành

ErrorMessage là kiểu message nội bộ của Spring với Throwable payload. Nó phù hợp để error handler đọc nguyên nhân, nhưng không nên dùng như **định dạng bền vững duy nhất cho replay hoặc sự kiện gửi ra ngoài**.

Một lỗi cần được phân loại theo:

- **flowId/endpointId:** poller nào chạy, thuộc business service nào;
- **stage:** RECEIVE, TRANSFORM, VALIDATE, PERSIST, OUTBOUND_SEND hay ACK;
- **source reference:** file path/remote path/record ID hoặc queue message ID;
- **correlationId:** liên kết nhiều message cùng batch/giao dịch;
- **business key:** khóa chống xử lý trùng;
- **error class và category:** Throwable, TRANSIENT, INVALID_INPUT, CONFIGURATION, PERMISSION hoặc UNKNOWN;
- **attempt/budget:** số lần retry đã dùng;
- **disposition:** RETRY_PENDING, QUARANTINED, NEEDS_RECONCILIATION hoặc TERMINAL;
- **observed outcome:** thành công/không thành công/chưa rõ ở từng hệ thống đích;
- **owner và deadline:** ai giải quyết nếu không tự khôi phục.

### 16.2. Ví dụ error event được chuẩn hóa

~~~json
{
  "eventType": "integration.poll.failed",
  "eventVersion": 1,
  "flowId": "sftp-orders-import",
  "endpointId": "sftpInbound",
  "stage": "PERSIST",
  "sourceReference": "incoming/orders-274.csv",
  "businessKey": "order-274",
  "correlationId": "batch-2026-274",
  "exceptionClass": "MessageHandlingException",
  "rootCauseClass": "DataAccessResourceFailureException",
  "category": "TRANSIENT",
  "attempt": 2,
  "maxAttempts": 4,
  "disposition": "RETRY_PENDING",
  "nextAttemptAt": "2026-11-23T09:05:00Z"
}
~~~

Đây là **schema do ứng dụng tự định nghĩa**, không phải nội dung mặc định của ErrorMessage. Source reference chỉ mang giá trị đã giảm nhạy cảm; không nhúng file chứa dữ liệu cá nhân, mật khẩu JDBC, bearer token, access key hoặc toàn bộ stacktrace vào event.

### 16.3. Lỗi không có message context

Nếu SFTP session thất bại trước khi có Message, event có thể chỉ có endpointId, remote host alias, stage=RECEIVE, exception type và timestamp. Đừng tạo businessKey/orderId giả rồi cố replay dữ liệu chưa đọc được.

### 16.4. Không lưu Throwable trực tiếp như hợp đồng bên ngoài

Java Throwable có graph cause, stacktrace, lớp runtime đặc thù và khả năng chứa thông tin nhạy cảm; không nên serialize tùy ý qua Kafka/JMS hoặc database lâu dài. Nếu cần recovery qua restart, lưu **command/data reference hợp lệ** và thông tin lỗi chuẩn hóa.

### 16.5. Phân biệt triage với recovery

Một subscriber nhận ErrorMessage có thể ghi metrics và tạo incident. Một recovery coordinator khác sẽ quyết định retry/quarantine/reconcile theo state. Trong trường hợp cần bảo đảm không mất nhiệm vụ recovery, việc ghi **durable task** phải được thiết kế đúng ranh giới transaction/ack; không thể chỉ gửi một message trong bộ nhớ và tuyên bố đã lưu.

## 17. Observability: phát hiện lỗi và cả sự im lặng của poller

### 17.1. Log có cấu trúc

Log nên có thời gian, endpoint, flow, adapter, correlation, exception type, stage và outcome. Ví dụ:

~~~text
level=ERROR
flow=sftp-orders-import
poller=sftpInbound
stage=RECEIVE
exceptionType=SftpException
errorCategory=TEMPORARY_UNAVAILABLE
attempt=2
outcome=RETRY_SCHEDULED
~~~

Không log nguyên failedMessage.toString() nếu có thể chứa payload tài chính, file nhạy cảm, token hoặc thông tin người dùng. Với lỗi phát sinh tại source, dùng safe source ID thay vì in nguyên connection URI có credentials.

### 17.2. Metrics

| Metric đề xuất | Ý nghĩa |
|---|---|
| poll_attempt_total | Số lượt scheduler kích hoạt poll |
| poll_messages_received_total | Số message source thực sự trả về |
| poll_errors_published_total | Số ErrorMessage do poller/error publisher phát |
| processing_failures_total | Lỗi handler theo stage/category |
| poll_retry_total | Số lần retry theo flow |
| retry_exhausted_total | Message hết retry budget |
| quarantine_backlog | Số file/record cần sửa |
| last_successful_poll_timestamp | Thời gian một lần poll hoàn thành thành công theo định nghĩa |
| last_nonempty_poll_timestamp | Lần gần nhất thật sự nhận được input |
| oldest_pending_item_age | Tuổi công việc đang chờ |
| error_handler_failure_total | Lỗi của chính subscriber error flow |

Các tên trên là **metric do ứng dụng có thể định nghĩa**. Không suy rằng Spring Integration tự phát tất cả chúng. Theo dõi nhãn flow, stage, adapter với cardinality thấp; không dùng mỗi file path/message ID làm metric label.

### 17.3. Nhận biết poller chạy nhưng không có dữ liệu

Hệ thống yêu cầu mỗi 10 phút có file mới; poller vẫn chạy nhưng không thấy file suốt 2 giờ. Không có exception và **errorChannel im lặng**. Cần cảnh báo theo **last_nonempty_poll**, số file dự kiến, heartbeat từ đối tác hoặc backlog ở nguồn, không chỉ số lỗi.

### 17.4. Nhận biết poller dừng hẳn

Một cấu hình scheduler không kích hoạt endpoint, bean bị stopped hoặc thread pool cạn có thể làm poller không chạy. Kiểm tra:

- Endpoint lifecycle/running state;
- Thời điểm kích hoạt poll gần nhất;
- Scheduler pool usage, thread exhaustion;
- Receive timeout và channel capacity;
- Logging của executor/scheduler;
- Cấu hình start/stop và deployment version.

Lỗi im lặng không được giải quyết bằng cách gắn thêm một @ServiceActivator trên errorChannel nếu nguồn vấn đề là task không chạy.

### 17.5. Distributed tracing

Khi poller lấy Message rồi gọi HTTP/Kafka, correlation/trace context cần được propagate qua headers, executor và adapter theo cơ chế phù hợp. Một Throwable hoặc ErrorMessage chỉ có một phần ngữ cảnh không bảo đảm đầy đủ distributed trace; kiểm tra propagation và giữ business key ở state store.

## 18. Case study: SFTP poller nhập đơn, JDBC và HTTP

### 18.1. Nhu cầu kinh doanh

Công ty A nhận file CSV từ đối tác B qua SFTP mỗi 5 phút. Các record hợp lệ được lưu vào database, sau đó hệ thống gọi HTTP của đối tác logistics C để đăng ký vận chuyển. Yêu cầu nghiệp vụ:

1. File không được xử lý hai lần không kiểm soát.
2. Dữ liệu sai schema phải được cách ly để sửa.
3. Lỗi SFTP network phải retry với backoff, không xoá file nguồn.
4. Database lỗi sau khi đã lưu một phần phải có cơ chế đối soát/transaction.
5. HTTP timeout không được tạo shipment trùng.
6. Error handler phải có đủ thông tin để người vận hành biết lỗi xảy ra ở đâu.

### 18.2. Kiến trúc giải pháp

~~~mermaid
flowchart TD
    SFTP["SFTP Server B"] --> POLL["SFTP inbound poller"]
    POLL --> FILE["Local file / durable reference"]
    FILE --> PARSE["CSV validation"]
    PARSE --> DB["JDBC persist order"]
    DB --> HTTP["HTTP register shipment C"]
    HTTP --> OK["Processed + archived"]
    POLL -. "Receive exception" .-> ERR["sftpPollErrors"]
    PARSE -. "Handler exception trong poller scope" .-> ERR
    DB -. "Handler exception trong poller scope" .-> ERR
    HTTP -. "Synchronous exception trong poller scope" .-> ERR
    ERR --> CLASSIFY["Classify + read safe context"]
    CLASSIFY --> DEC{"Category?"}
    DEC -->|"Network transient"| RETRY["Backoff / retry task"]
    DEC -->|"Invalid CSV"| QUAR["Quarantine file"]
    DEC -->|"Unknown outcome"| RECON["Reconciliation"]
    DEC -->|"Security/config"| ALERT["Alert / manual fix"]
~~~

Đường lỗi phụ thuộc cấu hình: nếu một endpoint đã đổi thread, callback HTTP/Kafka phát lỗi sau này có thể đi qua error strategy khác. Sơ đồ cũng không thể hiện đầy đủ commit/ack; chúng phải được kiểm thử.

### 18.3. Kịch bản A — SFTP không mở được session

Poller bị timeout trước khi tải file; nhận ErrorMessage từ error strategy nếu được cấu hình. failedMessage có thể null. Error handler:

- Gắn flow=sftp-orders-import, stage=RECEIVE;
- Phân loại lỗi mạng transient;
- Chờ và retry với backoff, giới hạn session mở mới;
- Alert nếu quá thời gian cho phép;
- Không chuyển một file giả vào quarantine và không đánh dấu file đã xử lý.

### 18.4. Kịch bản B — CSV sai schema

File đã tải về an toàn, transformer nhận File Message và gặp trường bắt buộc bị thiếu. Handler ném exception; ErrorMessage có thể chứa failedMessage. Error handler:

- Lấy safe file reference và correlation;
- Đánh dấu invalid batch/record;
- Chuyển file đến quarantine theo policy;
- Lưu lý do lỗi đã masking để B sửa;
- Ngăn file poison chiếm mọi lượt poll.

Không tự retry cùng CSV sai schema cho đến khi hết tài nguyên. Nếu file filter đã nhận file, phải kiểm soát re-ingest sau khi sửa.

### 18.5. Kịch bản C — JDBC down khi xử lý batch

File hợp lệ nhưng DB timeout giữa batch. Nếu một số row đã commit, lần poll sau có thể nhập trùng. Cần:

- Đối soát row đã commit bằng business key;
- Sử dụng transaction/unique constraints theo đơn vị batch phù hợp;
- Lưu retry task an toàn và idempotent;
- Không đánh dấu file PROCESSED chỉ vì error message đã được ghi log.

### 18.6. Kịch bản D — HTTP tạo shipment nhưng timeout

Một Order đã lưu DB, HTTP POST CreateShipment bị timeout. C có thể đã tạo shipment dù A không nhận response. Không thực hiện lại bằng request ID mới một cách mù quáng. Cần:

- Đánh dấu RESULT_UNKNOWN;
- Tra cứu shipment theo key ổn định/idempotency key;
- Nếu đã tạo, lưu shipment ID và hoàn tất bước phù hợp;
- Nếu chưa tạo và có bằng chứng tin cậy, retry trong budget;
- Nếu không xác định, chuyển manual reconciliation.

### 18.7. Kịch bản E — Poller nhận được ErrorMessage nhưng file không được đọc lại

Đội vận hành thấy lỗi trên sftpPollErrors và nghĩ poller tự retry. Thực tế local filter đã đánh dấu file accepted; trong lần poll sau file không còn được chọn. Đây là nguyên nhân **missing processing** dù alert đã hoạt động.

Giải pháp: bổ sung durable file state/metadata, quarantine hoặc retry worker có tham chiếu file và business key, đặt rõ điều kiện khi nào reset filter hoặc requeue. Không sửa bằng cách tắt hết filter để tránh mất file, vì có thể tạo hàng loạt duplicate.

### 18.8. Kịch bản F — Bị ngắt nguồn trong lúc xử lý lỗi

Error handler đang gửi email/đẩy ticket thì logging service chậm 30 giây. Nếu chạy đồng bộ trong poller error path, task scheduler có thể bị block làm các file khác chậm trễ. Nên giới hạn thời gian ở error observer, đưa thông báo quan trọng vào durable task và tách worker gửi alert khỏi poller.

### 18.9. Bảng tiêu chí hoàn tất

| Bước | Bằng chứng cần có |
|---|---|
| Receive | Remote/local file reference, trạng thái chuyển file |
| Parse | Schema/version và kết quả từng record hoặc batch |
| Persist | DB commit và business key |
| HTTP outbound | Request ID, kết quả hoặc trạng thái unknown |
| Error notification | ErrorMessage được nhận bởi channel đúng |
| Retry/quarantine | Durable record, attempt, owner |
| Final disposition | PROCESSED, QUARANTINED hoặc MANUAL_REVIEW có căn cứ |

### 18.10. Bài học

**Định tuyến lỗi đúng channel** là một bước cần thiết, nhưng chất lượng tích hợp phụ thuộc **source state, transaction boundary, timeout semantics và khả năng replay có kiểm chứng**. Một hệ thống không mất message phải biết message đang ở đâu sau khi error handler chạy xong.

## 19. Kiểm thử đường lỗi poller với QueueChannel

### 19.1. Vì sao nên test bằng QueueChannel trước?

QueueChannel làm giảm phụ thuộc vào filesystem hoặc SFTP trong bài test đầu tiên. Có thể gửi một Message vào input queue, cho consumer poller nhận rồi cố tình ném exception; test đọc ErrorMessage từ một **test error channel** khác.

Điều này xác minh:

- Poller thực sự đang chạy;
- Handler được gọi;
- Exception được publish vào error destination đã cấu hình;
- ErrorMessage.payload là Throwable;
- Correlation có thể tìm từ context nếu được cung cấp.

Nó chưa kiểm chứng file filtering, remote transfer hay broker acknowledgment.

### 19.2. Mẫu JUnit/Spring integration test

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PollerErrorFlowTest.Config.class)
class PollerErrorFlowTest {

    @Autowired
    QueueChannel testInputs;

    @Autowired
    QueueChannel testErrors;

    @Test
    void publishesFailureToDedicatedErrorChannel() {
        testInputs.send(MessageBuilder
                .withPayload("invalid-order")
                .setHeader("correlationId", "test-batch-1")
                .build());

        Message<?> received = testErrors.receive(5_000);
        assertNotNull(received, "Expected an ErrorMessage");
        ErrorMessage error = assertInstanceOf(ErrorMessage.class, received);
        assertNotNull(error.getPayload());
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        QueueChannel testInputs() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel testErrors() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow failingPoller() {
            return IntegrationFlow.from(testInputs(),
                    spec -> spec.poller(
                            Pollers.fixedDelay(Duration.ofMillis(100))
                                    .maxMessagesPerPoll(1)
                                    .errorChannel("testErrors")))
                    .handle(message -> {
                        throw new IllegalArgumentException("demo failure");
                    })
                    .get();
        }
    }
}
~~~

Test dùng Spring Integration Java DSL, Spring Test và JUnit Jupiter. Nó giả định dependency đúng phiên bản và task scheduler chạy trong Spring context. Phần chính cần quan sát là **lỗi từ polling consumer được nhận tại testErrors**, không phải listener toàn cục. Nếu overload Java DSL thay đổi theo phiên bản, điều chỉnh cú pháp phù hợp mà vẫn giữ hành vi.

### 19.3. Xác minh context có thể null

Thêm test giả lập lỗi source trước khi tạo Message. ErrorMessage được tạo ra có thể chỉ có Throwable mà không có failedMessage. Handler và test phải hỗ trợ null, không yêu cầu luôn truy ra một File.

### 19.4. Xác minh global fallback

Thiết lập một flow thử nghiệm khác không chỉ định error-channel riêng, bảo đảm error publisher phù hợp được bật, rồi đăng ký observer trên global errorChannel. Tạo lỗi và xác minh nơi nhận. Tránh đăng ký một subscriber có side effect thật trong test, vì default LoggingHandler cũng có thể hoạt động.

### 19.5. Xác minh không có ErrorMessage khi không có message

Chạy QueueChannel rỗng hoặc File adapter không tìm thấy file; poller vẫn tick nhưng không phải lỗi. Test không nên yêu cầu sinh ErrorMessage cho trường hợp receive trả null. Nếu nhu cầu nghiệp vụ đòi hỏi dữ liệu đúng giờ, viết **separate freshness/heartbeat test**.

### 19.6. Test lỗi ngoài stack poller

Thêm ExecutorChannel hoặc outbound async component rồi phát sinh lỗi sau khi polling task trả về. Kiểm tra xem lỗi đi tới error strategy của executor/adapter chứ không giả định về testErrors. Đây là ca rất hữu ích khi ứng dụng vừa tăng concurrency và bắt đầu mất dấu exception.

### 19.7. Test xử lý trùng và restart

Với bài test tích hợp File/SFTP/JDBC, cần xác minh cả:

1. Message đã được nhận có được đọc lại không?
2. Input đã lưu bền vững chưa?
3. Khi worker crash, retry task có được tiếp tục sau restart?
4. Business key có chặn duplicate side effect không?
5. Quarantine file sai schema có làm các file tốt được xử lý tiếp không?
6. Lỗi cố định có gây retry loop vô hạn không?

## 20. Runbook: điều tra khi poller không gửi lỗi tới kênh mong đợi

### Bước A — Xác minh poller thật sự chạy

1. Kiểm tra bean/endpoint có đang **running** trong Spring context không.
2. Kiểm tra scheduler có task được đăng ký và còn thread để chạy.
3. Xem log lần poll gần nhất, successful poll, non-empty poll và backlog.
4. Xác minh MessageSource hoặc PollableChannel có dữ liệu.
5. Xác minh maxMessagesPerPoll, fixed-delay/fixed-rate/cron và receive timeout phù hợp.

Nếu poller không chạy, không nên bắt đầu bằng việc sửa @ServiceActivator trên errorChannel. Không có tác vụ thực thi thì chưa có exception do tác vụ đó publish.

### Bước B — Xác định vị trí exception

**Trong lời gọi poller?** Lỗi receive hoặc handler đồng bộ có thể được error handler của poller xử lý.

**Trong executor/async callback?** Có thể lỗi nằm ở thread khác, cần error strategy riêng.

**Trong inbound listener/container?** Nếu nguồn là JMS, AMQP hoặc Kafka message-driven, cần xem error handler/ack/offset của container.

**Trong HTTP inbound gateway?** Request có thể được ánh xạ thành HTTP response, không phải lỗi của polling task.

### Bước C — Kiểm tra đích lỗi

1. Poller có cấu hình .errorChannel("...") hoặc equivalent không?
2. Bean channel được định nghĩa trong context chưa?
3. Có subscriber trên channel đúng tên không?
4. Global errorChannel có đang được framework tạo và có logging subscriber không?
5. Message có header errorChannel và error publisher có đọc header đó không?
6. Có endpoint khác tạo error flow riêng không?
7. Có retry advice hoặc recovery callback đã xử lý exception trước khi nó tới poller không?

**Nếu channel riêng đã nhận lỗi**, global errorChannel có thể không nhận thêm bản sao. Đó là kết quả của routing, không tự động là mất lỗi.

### Bước D — Kiểm tra error message contract

1. ErrorMessage.payload phải là Throwable.
2. Nếu Throwable thuộc MessagingException, có thể đọc failedMessage; phải null-check.
3. originalMessage cũng có thể null.
4. failedMessage.payload có thể không còn là input ban đầu do transformer.
5. Lưu safe correlation/flow/stage để truy vết.
6. Không log cả payload chứa PII/secret.

### Bước E — Kiểm tra tài nguyên nguồn

| Nguồn | Câu hỏi kiểm tra |
|---|---|
| File | Filter đã đánh dấu file? File bị move/delete/quarantine? |
| SFTP | Session fail trước download? Partial file? Remote metadata? |
| JDBC | Query có trả row? Row đã CLAIMED/PROCESSED? Transaction đã commit? |
| QueueChannel | Message đã bị receive xóa khỏi queue? Có durable store không? |
| HTTP outbound | Server đã nhận POST mặc dù caller timeout? |
| Broker outbound | Publish đã được broker chấp nhận? Callback lỗi xảy ra ở thread nào? |

### Bước F — Khôi phục an toàn

- Nếu lỗi dữ liệu vĩnh viễn: cách ly, sửa dữ liệu và replay đúng version.
- Nếu lỗi hạ tầng tạm thời: retry có backoff, time budget và idempotency.
- Nếu kết quả outbound chưa rõ: đối soát trước retry.
- Nếu poller mất heartbeat: xử lý scheduler/lifecycle/availability.
- Nếu error handler thất bại: ghi nhận lỗi thứ cấp, sử dụng fallback/recovery store.
- Nếu quá SLA: mở incident, nêu owner và tác động business.

### Bước G — Đóng sự cố

Không chỉ ghi “đã thấy ErrorMessage”. Cần chứng minh input đã đạt trạng thái **PROCESSED**, **QUARANTINED**, **RETRY_PENDING có durable reference** hoặc **MANUAL_REVIEW có owner**. Với tích hợp quan trọng, đối soát kết quả database, file, HTTP và broker.

## 21. Chống vòng lặp lỗi: khi error handler cũng gặp lỗi

### 21.1. Error-of-error

Một Service Activator lắng nghe filePollErrors có thể gọi Slack/email, ghi DB hoặc đưa event sang queue. Nếu các hệ thống phụ đó bị lỗi, error handler có thể ném exception mới. Tùy channel và dispatcher, lỗi thứ cấp có thể lan ngược tới error publisher, bị log hoặc gây tác động ngoài ý muốn.

**Không giả định một ErrorMessage thứ hai sẽ tự đến đúng chỗ và không mất dữ liệu.** Cần có fallback và phương thức kiểm tra thực tế.

### 21.2. Thiết kế tốt hơn

- Handler tuyến đầu nhẹ, giới hạn thời gian và tài nguyên;
- Phân loại lỗi, giảm dữ liệu nhạy cảm;
- Lưu durable incident/recovery request khi nghiệp vụ cần;
- Gửi notification qua worker độc lập, có retry limit;
- Không dùng chính channel nguồn làm đích mặc định của error handler;
- Chống notification trùng theo failure ID/correlation;
- Quan sát backlog và thất bại của error handler;
- Bảo đảm xử lý nguồn/ack được thiết kế tương thích với việc lưu recovery state.

### 21.3. PublishSubscribeChannel và side effect trùng

Kênh dạng publish-subscribe có thể chuyển ErrorMessage tới nhiều subscriber. Nếu hai subscriber đều thực hiện một compensation như “release inventory”, thao tác có thể xảy ra hai lần. Nên phân chia rõ:

| Subscriber | Trách nhiệm |
|---|---|
| Logging observer | Ghi structured log |
| Metrics observer | Tăng counters theo flow/category |
| Recovery coordinator | Là nơi duy nhất về mặt logic quyết định retry/quarantine/compensation |
| Alerting worker | Gửi thông báo qua durable task, giới hạn tần suất |

Không dùng subscriber order như cơ chế giao dịch tin cậy để đảm bảo trình tự bù. Nếu recovery có dependency, hãy quản lý nó trong coordinator/state store.

### 21.4. Kênh không có subscriber

Với dedicated error channel, khi không có subscriber hoặc channel từ chối gửi, hành vi có thể là MessageDeliveryException, bị log hoặc kết thúc theo cấu hình. Một số cấu hình PublishSubscribeChannel có **requireSubscribers**, nhưng cách bật và giá trị mặc định tùy phiên bản/cách tạo bean. Cần test khi subscriber bị stop, bị tháo hoặc error channel bị quá tải.

## 22. Anti-pattern thường gặp với polling error flow

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ mọi exception đều tới global errorChannel | Bỏ sót exception đồng bộ hoặc async | Xác định scope thực tế của error publisher |
| Chỉ khai báo @ServiceActivator mà không cấu hình poller/error strategy | Handler không nhận được lỗi mong đợi | Kiểm tra endpoint, channel, publisher |
| Đặt tên errorChannel sai hoặc thiếu bean riêng | Message lỗi không được định tuyến đúng | Xác nhận bean và subscriber |
| Đọc failedMessage không null-check | NullPointerException với lỗi SFTP/JDBC trước receive | Xử lý ngữ cảnh không có Message |
| Cast mọi failedMessage.payload thành File | ClassCastException sau transformer | Kiểm tra runtime type và message stage |
| Ghi toàn bộ payload lỗi vào log | Lộ PII, token hoặc file lớn | Structured log/masking |
| Coi ErrorMessage là retry tự động | File/row không được xử lý lại | Durable retry logic, file state |
| Tắt filter để “sửa” mất file | Xử lý trùng mọi file cũ | Persistent state + controlled replay |
| Retry file poison vô hạn | Starvation, nghẽn scheduler | Quarantine và limit |
| Bắt lỗi rồi return success trước khi lưu recovery | Ack/commit dù chưa xử lý nghiệp vụ | Durable recovery và error semantics phù hợp |
| Coi global error channel là DLQ | Message lỗi có thể mất khi restart | Durable queue/store và broker policy |
| Suy maxMessagesPerPoll là retry count | Sai lưu lượng và số lần xử lý | Phân biệt receive limit và retry |
| Gửi lại ErrorMessage vào kênh business | Throwable không đúng schema | Replay message/command nghiệp vụ |
| Bỏ qua HTTP timeout outcome unknown | Trùng booking/order | Idempotency và reconciliation |
| Cho rằng Kafka async callback về poller errorChannel | Bỏ sót lỗi producer muộn | Adapter/callback error strategy |
| Dùng retry ở mọi lớp không có budget | Retry storm | Một chính sách retry tổng |
| Poller schedule quá dày so với backend | Quá tải SFTP/DB/HTTP | Rate limiting, backpressure, pool sizing |
| Không test scheduler đã chạy | Error channel im lặng không được phát hiện | Heartbeat/last poll metrics |
| Nhiều error subscribers cùng bù | Double side effect | Một recovery coordinator, idempotency |
| Không kiểm tra app state sau lỗi | Dashboard báo lỗi nhưng dữ liệu bị mất/trùng | End-to-end validation và reconciliation |

## 23. Checklist triển khai poller gửi lỗi đến error-channel

### A. Xác định poller và lỗi

- [ ] Xác định endpoint là source poller, consumer poller hay message-driven listener.
- [ ] Biết thread/scheduler/executor nào chạy và nơi exception có thể xuất hiện.
- [ ] Phân biệt receive-time, handler-time và async callback failure.
- [ ] Có test khi không có Message (receive trả null) và khi receive ném exception.
- [ ] Biết maxMessagesPerPoll, lịch poll, receive timeout và concurrency.

### B. Cấu hình error destination

- [ ] Poller có error strategy/error-channel phù hợp theo phiên bản đang dùng.
- [ ] Bean kênh lỗi riêng tồn tại và có subscriber hoạt động.
- [ ] Global errorChannel còn logging/monitoring đúng nhu cầu.
- [ ] Không giả định global và local cùng nhận một lỗi.
- [ ] Khi header errorChannel được sử dụng, nó do nguồn đáng tin cậy kiểm soát.
- [ ] Error handler xử lý null failedMessage/originalMessage và không ép kiểu bừa.

### C. An toàn dữ liệu và retry

- [ ] Có business key/correlation ID và safe source reference.
- [ ] File/SFTP filter, move, delete, quarantine và replay đã được thiết kế.
- [ ] JDBC polling có transaction/claim/idempotency theo trạng thái nghiệp vụ.
- [ ] QueueChannel source không bị xem nhầm là durable nếu chỉ in-memory.
- [ ] HTTP retry có idempotency/tra cứu khi outcome không rõ.
- [ ] JMS/AMQP ack/tx và Kafka callback/offset xử lý theo container.
- [ ] Retry có loại lỗi phù hợp, giới hạn, backoff và final disposition.
- [ ] Recovery task có lưu bền vững khi cần tiếp tục sau restart.

### D. Kiểm thử và vận hành

- [ ] Test DirectChannel đồng bộ không mặc định publish lỗi.
- [ ] Test polling source và consumer publish tới kênh lỗi đã chọn.
- [ ] Test không có context Message, lỗi trước receive, handler failure.
- [ ] Test error handler thất bại, channel không subscriber, quá tải.
- [ ] Test restart, replay, duplicate và message poison.
- [ ] Có metric polling activity, last success, error rate, backlog và retry exhausted.
- [ ] Có owner và runbook cho quarantine/reconciliation/manual recovery.
- [ ] Kết quả được xác minh trên tài nguyên nguồn và đích, không chỉ thấy error log.

## 24. Câu hỏi tự kiểm tra

**Câu 1. Vì sao poller cần một error strategy riêng thay vì chỉ ném exception lên caller?**

**Trả lời:** Poller thường do scheduler kích hoạt, không có business caller đang đợi trên cùng call stack. Một error publishing strategy có thể chuyển Throwable thành ErrorMessage và gửi tới error channel để xử lý/quan sát.

**Câu 2. ErrorMessage có payload là dữ liệu file bị lỗi không?**

**Trả lời:** Không. Payload của ErrorMessage là Throwable. File hoặc business data có thể nằm trong failedMessage/originalMessage nếu context được cung cấp, hoặc trong một durable source reference.

**Câu 3. Poller SFTP lỗi kết nối trước khi tạo Message. Có thể đọc getFailedMessage().getPayload() không?**

**Trả lời:** Không nên. Throwable có thể không phải MessagingException hoặc failedMessage có thể null. Handler phải kiểm tra kiểu và fallback sang source/endpoint metadata.

**Câu 4. Khi đặt .errorChannel("filePollErrors") trên poller, global errorChannel có luôn nhận thêm một bản sao không?**

**Trả lời:** Không. Kênh được chọn phụ thuộc error publisher/routing. Khi đã chọn filePollErrors, không mặc định toàn cục cũng nhận; cần test cấu hình thực tế.

**Câu 5. Bổ sung @ServiceActivator(inputChannel="errorChannel") có làm mọi exception đồng bộ đi vào kênh không?**

**Trả lời:** Không. DirectChannel đồng bộ thường ném exception ngược sender. Subscriber chỉ nhận ErrorMessage đã được publisher gửi tới channel đó.

**Câu 6. maxMessagesPerPoll(5) nghĩa là retry tối đa năm lần?**

**Trả lời:** Không. Nó giới hạn số message mà poller lấy trong một lần kích hoạt theo policy. Retry có cấu hình riêng về số lần, loại lỗi và backoff.

**Câu 7. Tại sao file CSV đã ghi log lỗi ở error channel lại không xuất hiện trong lượt poll tiếp theo?**

**Trả lời:** File filter/metadata có thể đã đánh dấu nó là accepted. ErrorMessage không tự reset filter. Cần durable state và cơ chế quarantine/replay có kiểm soát.

**Câu 8. JDBC polling đọc row, gửi HTTP POST thành công nhưng update DB thất bại. Retry row ngay có an toàn không?**

**Trả lời:** Chưa chắc. Có thể gây POST trùng. Cần business key, idempotency key, trạng thái ở HTTP đích hoặc reconciliation trước khi gửi lại.

**Câu 9. Message lấy từ QueueChannel rồi handler ném exception có tự quay về queue không?**

**Trả lời:** Không nên mặc định. Đặc biệt QueueChannel in-memory không bảo đảm rollback/durable replay. Cần kiểm tra channel implementation, transaction và state recovery.

**Câu 10. Kafka inbound adapter message-driven có dùng errorChannel của File poller để quản lý offset không?**

**Trả lời:** Không. Listener container/Kafka error handler quản lý retry, offset và DLT. Poller-specific error channel không thay thế chính sách đó.

**Câu 11. Nếu retry advice đã bắt và phục hồi exception, poller có luôn publish ErrorMessage nữa không?**

**Trả lời:** Không. Nếu exception không được propagate, poller có thể không thấy failure để publish. Một recovery callback có thể tự gửi lỗi theo thiết kế, nên cần test tránh gửi hai lần.

**Câu 12. Error handler ghi log và trả về bình thường; có thể khẳng định file đã được nhập thành công không?**

**Trả lời:** Không. Ghi log là quan sát lỗi, không chứng minh DB/HTTP hoàn tất hoặc file đã vào retry/quarantine. Cần xác minh trạng thái nghiệp vụ và nguồn/đích.

**Câu 13. Vì sao log toàn bộ failedMessage có thể nguy hiểm?**

**Trả lời:** Payload/headers có thể chứa PII, thông tin tài chính, bearer token, secret, đường dẫn nhạy cảm hoặc file lớn. Nên log safe metadata và correlation ID.

**Câu 14. Khi nào nên dùng kênh filePollErrors riêng thay vì chỉ global errorChannel?**

**Trả lời:** Khi file processing có cách retry, quarantine, owner hoặc SLA khác với SFTP/JDBC/HTTP, hoặc cần test/monitor lỗi theo flow độc lập.

**Câu 15. Vì sao poller không phát ErrorMessage mà hệ thống vẫn có thể bị lỗi?**

**Trả lời:** Poller có thể ngừng chạy, không nhận dữ liệu, bị scheduler starvation hoặc nguồn không gửi file. Không có exception thì không có ErrorMessage; cần heartbeat, last successful poll và backlog metrics.

**Câu 16. Một file lỗi liên tục làm các file tốt không được xử lý. Nên làm gì?**

**Trả lời:** Đánh dấu file poison, quarantine/recovery riêng, giới hạn retry và giữ cơ chế nhận các file còn lại. Đừng disable mọi filter hoặc retry vô hạn cùng file.

**Câu 17. Nếu error handler cũng ném exception, nên làm gì?**

**Trả lời:** Tách observer nhẹ với durable recovery worker, có fallback/alert cho error-of-error, hạn chế thời gian block scheduler và test behavior khi channel không có subscriber.

**Câu 18. Một source poller nhận file, sau đó chuyển sang ExecutorChannel để gọi HTTP bất đồng bộ. HTTP lỗi có chắc trở về filePollErrors không?**

**Trả lời:** Không. Lỗi phát sinh sau ranh giới thread có thể thuộc error strategy của executor/HTTP adapter. Cần xác định đường lỗi bằng integration test.

**Câu 19. Có thể coi global errorChannel là dead-letter queue bền vững không?**

**Trả lời:** Không. Nó là Spring MessageChannel; việc lưu bền vững, retry sau restart, acknowledgment và DLQ/DLT cần cấu hình riêng ở workflow/broker thích hợp.

**Câu 20. Điều gì chứng minh poller error handling đã hoạt động đúng?**

**Trả lời:** Có test cho exception được gửi đúng ErrorMessage destination, handler đọc context an toàn, nguồn và hệ thống đích có trạng thái đúng, retry/quarantine được bảo đảm khi cần và các trường hợp lỗi chưa xử lý đều có owner.

## 25. Kết luận và tài liệu tham khảo

### 25.1. Điều cần ghi nhớ

Trong **Spring Integration**, poller chủ động nhận Message từ **MessageSource hoặc PollableChannel**. Khi polling task gặp exception trong phạm vi error handler được cấu hình, cơ chế như **MessagePublishingErrorHandler** có thể dựng **ErrorMessage** và gửi tới **error-channel**, mặc định là **errorChannel** toàn cục hoặc một channel riêng do poller chỉ định.

**Cấu hình đúng error destination là bước đầu tiên, không phải bước cuối cùng.** Cần hiểu rõ:

- **Bắt exception:** xảy ra trong scheduler/poller hay đã ra ngoài thread đó?
- **Định tuyến lỗi:** global hay dedicated error-channel; có subscriber và publisher chưa?
- **Bối cảnh lỗi:** Throwable, failedMessage, originalMessage, business key và stage có tồn tại không?
- **Nguồn dữ liệu:** file filter, SFTP remote metadata, JDBC row state hoặc QueueChannel có giữ message không?
- **Side effect:** DB đã commit, HTTP đã xử lý, broker đã nhận message chưa?
- **Phục hồi:** retry, backoff, idempotency, quarantine, compensation hoặc manual reconciliation;
- **Kiểm chứng:** message đã đạt trạng thái cuối mong muốn hay mới chỉ có một dòng log lỗi?

### 25.2. Sơ đồ tổng kết

~~~mermaid
flowchart LR
    SRC["File / SFTP / JDBC / QueueChannel"] --> P["Poller"]
    P --> H["Message processing"]
    P -. "Lỗi receive" .-> E["Error publisher"]
    H -. "Lỗi trong phạm vi poller" .-> E
    E --> EC["errorChannel hoặc kênh riêng"]
    EC --> O["Observe + classify"]
    O --> Q{"Kết quả cần xử lý?"}
    Q -->|"Transient"| R["Durable retry + backoff"]
    Q -->|"Permanent data"| C["Quarantine"]
    Q -->|"Unknown"| U["Reconciliation"]
    Q -->|"Fatal/config"| M["Alert / manual intervention"]
    R --> V["Verify source & target"]
    C --> V
    U --> V
    M --> V
~~~

### 25.3. Tài liệu chính thức nên đối chiếu

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): cơ chế errorChannel, ErrorMessage, MessagePublishingErrorHandler và lỗi đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): polling endpoint, PollerSpec, lịch poll, task executor và advice.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): cách cấu hình IntegrationFlow, channel và polling endpoint.
- [Spring Integration Reference — File Support](https://docs.spring.io/spring-integration/reference/file.html): file source, filter và xử lý file.
- [Spring Integration Reference — SFTP Support](https://docs.spring.io/spring-integration/reference/sftp.html): polling/remote synchronization và file transfer.
- [Spring Framework — ErrorMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html): Throwable payload, originalMessage và constructors.

Các đoạn Java/JSON/SQL và Mermaid trong bài là **ví dụ học tập**. Hãy kiểm tra phiên bản Spring Integration, Spring Boot, Java, adapter và dependency của dự án, rồi chạy integration tests cho scheduler, thread boundary, retry, transaction và message state trước khi dùng trong production.
