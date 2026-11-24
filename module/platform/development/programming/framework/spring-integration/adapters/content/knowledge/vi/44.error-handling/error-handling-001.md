# errorChannel mặc định trong Spring Integration

## 1. Vì sao cần errorChannel?

**Spring Integration** tổ chức việc tích hợp các hệ thống bằng **Message**, **MessageChannel** và các endpoint như inbound/outbound adapter, gateway, transformer, filter, router, service activator. Message có **payload** và **headers**; channel chuyển message giữa các thành phần. Mỗi thành phần có thể thất bại vì dữ liệu sai định dạng, file bị khóa, dịch vụ HTTP không phản hồi, broker mất kết nối, transaction thất bại hoặc lỗi xử lý nghiệp vụ.

Trong một lời gọi hàm đồng bộ thông thường, ngoại lệ có thể được ném ngược cho caller. Tuy nhiên, khi xử lý message bằng **poller** hoặc các ranh giới **bất đồng bộ**, caller ban đầu không còn ở cùng ngăn xếp gọi để nhận exception. Vì vậy, Spring Integration có cơ chế **chuyển lỗi thành message** và định tuyến nó tới một kênh lỗi.

**errorChannel mặc định** là tên kênh lỗi toàn cục mà Spring Integration cung cấp trong cấu hình tích hợp thông thường. Khi một cơ chế xử lý lỗi có khả năng **publish ErrorMessage** mà không chọn kênh lỗi riêng, kênh mang tên **errorChannel** là điểm nhận mặc định. Trong cấu hình tiêu chuẩn của framework, kênh này thường là **PublishSubscribeChannel**, đồng thời có **LoggingHandler** đăng ký để ghi lỗi. Cấu hình thực tế có thể khác nếu ứng dụng tự định nghĩa/thay thế bean, bổ sung subscriber hoặc tích hợp với thành phần bên ngoài.

Điểm cốt lõi là **không phải mọi exception trong mọi flow đều tự động đi tới errorChannel**. Cần phân biệt rõ:

- **Exception được ném trực tiếp** trong luồng đồng bộ;
- **Exception được bắt và chuyển thành ErrorMessage** tại poller, listener hoặc một thành phần có chính sách error publishing;
- **Lỗi ở tài nguyên bên ngoài** do file system, SFTP server, HTTP client/server, JMS/AMQP/Kafka broker hoặc database tự quản lý;
- **Quyết định retry, rollback, reject, dead-letter hoặc trả response** do adapter/transaction/container và chính sách của ứng dụng.

Tên kênh errorChannel **không biến nó thành “bộ xử lý retry toàn cục” hay một dead-letter queue**. Nó trước hết là **đường vận chuyển thông tin lỗi dưới dạng message**.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích cách errorChannel mặc định được dùng trong Spring Integration.
2. Phân biệt exception đồng bộ với ErrorMessage bất đồng bộ hoặc do poller tạo ra.
3. Đọc payload của ErrorMessage và truy dấu message gây lỗi.
4. Đăng ký handler cho errorChannel và quyết định khi nào cần kênh lỗi riêng.
5. Tích hợp error flow với File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC mà không hiểu nhầm cơ chế commit/retry.
6. Thiết kế các lựa chọn **log, alert, retry có giới hạn, cách ly, dead-letter, compensation** và quan sát vận hành.
7. Viết thử nghiệm xác minh đường lỗi, tránh mất message và lỗi bị nuốt.

## 2. Đặt errorChannel vào kiến trúc message

Một luồng tích hợp có thể mô tả:

~~~mermaid
flowchart LR
    SRC["Hệ thống ngoài: file / SFTP / HTTP / broker"]
    IN["Inbound adapter hoặc gateway"]
    CH["MessageChannel"]
    HANDLER["Transformer / Handler / Outbound adapter"]
    TARGET["Hệ thống đích"]
    PUB["Thành phần bắt lỗi và publish ErrorMessage"]
    ERR["errorChannel (global)"]
    LOG["LoggingHandler mặc định"]
    OPS["Custom error handler / alert / recovery"]
    SRC --> IN --> CH --> HANDLER --> TARGET
    IN -. "Lỗi trong poller/listener có hỗ trợ" .-> PUB
    HANDLER -. "Lỗi được error strategy bắt" .-> PUB
    PUB --> ERR
    ERR --> LOG
    ERR --> OPS
~~~

Sơ đồ là **mô hình logic**, không ngụ ý mọi adapter tự động phát ErrorMessage hoặc luôn tiếp tục chạy sau ngoại lệ. Hành vi thực tế phụ thuộc endpoint, cách gọi, cấu hình executor, transaction, advice và adapter cụ thể.

### 2.1. Những thành phần liên quan

| Thành phần | Chức năng | Liên quan đến lỗi |
|---|---|---|
| Message | Payload và headers của một đơn vị xử lý | Giúp truy vết dữ liệu và correlation ID |
| MessageChannel | Nơi gửi và nhận message | Có thể là DirectChannel, QueueChannel, ExecutorChannel, PublishSubscribeChannel... |
| errorChannel | Tên kênh lỗi toàn cục | Điểm đến mặc định cho lỗi đã được publish |
| ErrorMessage | Một Message có payload kiểu Throwable | Mang exception và có thể kèm original message |
| MessagingException | Ngoại lệ của hệ thống messaging | Thường có failedMessage để xác định message bị lỗi |
| ErrorMessagePublisher / MessagePublishingErrorHandler | Thành phần công bố ErrorMessage khi được sử dụng | Có thể chọn errorChannel từ header hoặc fallback |
| LoggingHandler | Endpoint ghi thông tin lỗi | Có thể là subscriber mặc định của errorChannel |
| Poller / task executor / listener | Khởi động xử lý ngoài caller đồng bộ | Thường cần error handling strategy riêng |

### 2.2. errorChannel mặc định là channel, không phải exception class

Tên **errorChannel** thường được xác định bởi bean/channel trong Spring context. Các thành phần framework biết tên chuẩn này và có thể định tuyến lỗi tới nó. Không nên nhầm:

- **errorChannel**: một message channel;
- **ErrorMessage**: object chứa ngoại lệ;
- **MessagingException**: một loại exception có thể mang failed message;
- **error-channel configuration**: cách chỉ định kênh riêng ở gateway, poller hoặc endpoint;
- **dead-letter queue (DLQ)**: hàng đợi lưu thông điệp không xử lý được, cần cơ chế và chính sách riêng.

## 3. ErrorMessage chứa gì?

Trong Spring Framework, **ErrorMessage** là một message có **payload là Throwable**. Nội dung có thể là MessagingException, MessageHandlingException, MessageDeliveryException hoặc một exception khác, tùy nơi lỗi được bắt và tạo message.

Đối với các MessagingException, thuộc tính **failedMessage** thường chứa message liên quan tới lỗi. Một ErrorMessage cũng có thể giữ **originalMessage** nếu thành phần tạo lỗi cung cấp. Tuy nhiên, không nên khẳng định mọi lỗi đều có đầy đủ failedMessage hoặc originalMessage: một ngoại lệ phát sinh trước khi tạo Spring Message, hoặc một thành phần chỉ chuyển Throwable, có thể thiếu bối cảnh.

### 3.1. Ví dụ nội dung logic

~~~text
ErrorMessage
  payload:
    MessageHandlingException
      message: "Failed to handle message"
      failedMessage:
        payload: order-274.csv
        headers:
          id: ...
          correlationId: import-2026-001
          file_name: order-274.csv
  originalMessage: ...  (có thể có hoặc không)
  headers:
    id: ...
    timestamp: ...
~~~

Lưu ý: đây là minh họa cấu trúc, **không phải bản dump chính xác cho mọi phiên bản hoặc adapter**. Không suy rằng mọi header ở source đều được bảo toàn qua biến đổi message, bridge hoặc gateway.

### 3.2. Đọc exception và failedMessage an toàn

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class GlobalIntegrationErrorLogger {

    @ServiceActivator(inputChannel = "errorChannel")
    public void onError(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();
        System.err.println("Integration error: " + failure.getClass().getSimpleName());

        if (failure instanceof MessagingException messagingException) {
            Message<?> failed = messagingException.getFailedMessage();
            if (failed != null) {
                Object correlation = failed.getHeaders().get("correlationId");
                System.err.println("Correlation: " + correlation);
                // Chỉ ghi metadata an toàn; tránh in payload nhạy cảm.
            }
        }
    }
}
~~~

Ví dụ dùng Java hỗ trợ pattern matching cho instanceof; nếu dự án dùng phiên bản Java thấp hơn, có thể cast theo cú pháp cũ. Trong production nên dùng SLF4J/structured logging thay vì System.err, che dữ liệu cá nhân và tránh ghi toàn bộ payload, token, password hoặc key.

**Quan trọng:** vì errorChannel mặc định thường theo cơ chế publish-subscribe, nhiều subscriber có thể cùng nhận một ErrorMessage. Đăng ký handler không mặc nhiên loại bỏ subscriber ghi log đang có; hãy kiểm tra cấu hình thực tế nếu muốn tránh ghi trùng hoặc xử lý side effect nhiều lần.

## 4. Đồng bộ và bất đồng bộ: khác biệt quyết định đường lỗi

### 4.1. Luồng đồng bộ với DirectChannel

~~~text
caller --> DirectChannel --> serviceActivator --> outboundAdapter
                         |
                         +-- throw exception --> caller / upstream
~~~

**DirectChannel** thường gọi subscriber trong cùng luồng của người gửi. Nếu handler ném exception và không có lớp advice/catch đặc biệt, ngoại lệ thường **lan ngược đến sender**. Nó không tự động trở thành ErrorMessage chỉ vì Spring context có bean errorChannel.

Ví dụ một HTTP inbound gateway xử lý đồng bộ: caller chờ HTTP response. Exception có thể dẫn đến response lỗi theo cơ chế gateway/web layer hoặc cấu hình error flow. Nếu chỉ tin vào subscriber của errorChannel, ứng dụng có thể không xử lý đúng HTTP status/body.

### 4.2. Poller: không có caller đồng bộ để trả exception

Inbound File/SFTP/JDBC poller thường chạy do scheduler kích hoạt. Nếu poller đang nhận hoặc xử lý message mà lỗi xảy ra, cơ chế error handler được cấu hình cho poller có thể **publish ErrorMessage** đến kênh được chọn. Khi không có kênh riêng và sử dụng global fallback, đó thường là **errorChannel**.

~~~text
Scheduler --> Poller --> MessageChannel --> Handler
                 |                               |
                 +------ exception được bắt -----+
                              |
                       ErrorMessagePublisher
                              |
                         errorChannel
~~~

Từng loại poller/adapter có chính sách nhận message, acknowledgment và transaction khác nhau. Gửi ErrorMessage **không tự chứng minh** input đã được retry hoặc chưa bị đánh dấu là đã xử lý.

### 4.3. Ranh giới bất đồng bộ khác

ExecutorChannel, QueueChannel có consumer poller, message-driven inbound adapter hoặc một task executor có thể khiến exception không còn đường ném trực tiếp về caller ban đầu. Tuy nhiên, **việc chuyển thành ErrorMessage còn phụ thuộc error handler thực tế ở điểm xử lý**. Một message được gửi vào QueueChannel mà không có consumer không tự sinh lỗi; một executor không được cấu hình error publisher có thể chỉ báo lỗi qua cơ chế của executor.

### 4.4. Bảng hành vi tham khảo

| Luồng | Khi handler lỗi | Điều cần cấu hình/kiểm tra |
|---|---|---|
| DirectChannel đồng bộ | Thường ném ngược cho sender | Advice, gateway response, exception mapping |
| Polling inbound adapter | Poller error strategy có thể publish ErrorMessage | errorChannel của poller, retry, file/DB acknowledgment |
| QueueChannel với consumer poller | Consumer/poller xử lý lỗi ngoài sender gốc | Poller và error handler tại consumer |
| ExecutorChannel | Lỗi xảy ra trên thread khác | Cơ chế error publishing và executor behavior |
| HTTP inbound gateway | Caller chờ response | HTTP error mapping, status, timeouts, error flow |
| JMS/AMQP/Kafka message-driven | Listener/container tham gia xử lý lỗi | Ack, transaction, redelivery, broker/container error handler |

**Quy tắc kiểm thử:** Không suy diễn đường lỗi chỉ dựa vào loại channel. Viết integration test cố tình ném exception tại điểm xử lý và xác minh cả errorChannel lẫn trạng thái nguồn message/response.

## 5. errorChannel toàn cục và kênh lỗi có scope riêng

### 5.1. Ưu tiên của kênh lỗi

Một số thành phần dùng **MessagePublishingErrorHandler** có thể tìm kênh lỗi bằng **header errorChannel** của failed message, sau đó dùng kênh fallback/toàn cục nếu không có lựa chọn phù hợp. Trong những endpoint khác, người dùng cấu hình trực tiếp error-channel riêng. Quy tắc và điểm áp dụng cụ thể **phụ thuộc thành phần**, không phải mọi Message<?> đều được định tuyến tự động theo header.

Vì vậy có ba kiểu thực tế:

1. **Global:** route ErrorMessage tới errorChannel, nơi có logging và handler chung;
2. **Per-flow/per-endpoint:** poller hoặc gateway chỉ định fileErrors, sftpErrors, apiErrors...;
3. **Per-message:** dùng header errorChannel khi endpoint/error handler có hỗ trợ phân giải theo header.

### 5.2. Khi nào dùng global?

Global errorChannel phù hợp để:

- Ghi nhận lỗi không có kênh cụ thể;
- Cảnh báo một số lỗi không được xử lý ở flow riêng;
- Theo dõi tỷ lệ lỗi chung, correlation/trace và phân loại;
- Đặt bước xử lý cuối cho những failure đã được publish.

Không nên đẩy mọi hành động recovery, retry, email cảnh báo và gửi DLQ vào một handler toàn cục không phân loại. Một lỗi file SFTP cần rollback file, một lỗi HTTP 503 cần retry có giới hạn, còn lỗi dữ liệu sai schema cần cách ly — chúng có logic khác nhau.

### 5.3. Khi nào dùng dedicated error channel?

Một luồng nên dùng kênh riêng khi có **SLA, độ tin cậy, retry, transaction hoặc thông tin nghiệp vụ khác biệt**. Ví dụ:

| Kênh | Nguồn lỗi | Chính sách gợi ý |
|---|---|---|
| fileErrors | Poller đọc/parse file | Cách ly file lỗi, ghi nguyên nhân, tránh đọc lặp |
| sftpErrors | Session/transfer SFTP | Phân biệt lỗi mạng và file không hợp lệ; backoff |
| httpClientErrors | Outbound HTTP | Phân loại HTTP status/timeout; retry có giới hạn |
| brokerErrors | JMS/AMQP/Kafka | Phối hợp container, ack/tx, redelivery/DLQ |
| databaseErrors | JDBC query/write | Kiểm tra transaction, idempotency và retry constraint |

Các tên trên chỉ là ví dụ. Kênh riêng có thể là DirectChannel, PublishSubscribeChannel hoặc loại channel khác tùy topology; lựa chọn loại channel ảnh hưởng concurrency, backpressure và ai nhận một ErrorMessage.

## 6. Cấu hình nhận lỗi từ errorChannel mặc định

### 6.1. Tối thiểu: thêm một Service Activator

Nếu Spring Integration đã được kích hoạt và sử dụng **default errorChannel**, có thể đăng ký một subscriber bằng annotation mà không cần tự khai báo một channel bean mới:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationErrorObserver {

    private static final Logger log =
            LoggerFactory.getLogger(IntegrationErrorObserver.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void observe(ErrorMessage error) {
        Throwable cause = error.getPayload();
        String failedMessageId = "unknown";

        if (cause instanceof MessagingException exception
                && exception.getFailedMessage() != null) {
            failedMessageId = exception.getFailedMessage()
                    .getHeaders().getId().toString();
        }

        log.error("Spring Integration failure, failedMessageId={}, type={}",
                failedMessageId, cause.getClass().getSimpleName(), cause);
    }
}
~~~

Lớp trên giả định ứng dụng có dependency Spring Integration, SLF4J, component scanning và cấu hình integration tương ứng. Có thể bổ sung **@EnableIntegration** trong lớp cấu hình nếu dự án chưa kích hoạt hạ tầng annotation; với Spring Boot, cần kiểm tra auto-configuration đang dùng. **Không khai báo một bean trùng tên errorChannel chỉ vì muốn lắng nghe lỗi**: khai báo trùng tên có thể làm thay đổi cơ chế mặc định và subscriber logging sẵn có.

Ví dụ chỉ cho thấy **handler nhận những ErrorMessage đã được publish đến global channel**. Nó không bắt mọi exception đồng bộ trong DirectChannel. Cũng không tự tạo retry hay bảo đảm rằng hệ thống nguồn sẽ gửi lại dữ liệu.

### 6.2. Tại sao không nên ném exception vô hạn từ error handler?

Khi error handler lại thất bại, lỗi có thể bị ghi lại, được ném cho cơ chế gọi handler hoặc dẫn đến retry ngoài dự kiến tùy channel/error strategy. Nếu handler gửi notification hoặc ghi DB cũng bị lỗi, không nên tạo vòng gửi lỗi về chính errorChannel một cách vô hạn.

Một error handler thực tế nên:

- Có logic nhỏ, xác định rõ kết quả; tránh chặn luồng bằng thao tác network chậm;
- Phân biệt lỗi nguồn với lỗi của chính error handler;
- Không ghi toàn bộ payload nhạy cảm;
- Có giới hạn số lần gửi thông báo hoặc chuyển lỗi sang hàng đợi xử lý bền vững khi cần;
- Được kiểm thử khi log server, DB hoặc notification provider không khả dụng.

### 6.3. Hiểu subscriber của PublishSubscribeChannel

Trong cấu hình mặc định thường gặp, global errorChannel dùng **PublishSubscribeChannel**, có thể chuyển một ErrorMessage tới nhiều subscriber:

~~~text
                  +--> LoggingHandler
ErrorMessage --> errorChannel
                  +--> ErrorObserver
                  +--> Metrics/alerting handler
~~~

Vì thế một handler ghi log bổ sung có thể khiến cùng lỗi được ghi **hai lần**. Muốn dùng một pipeline xử lý recovery duy nhất, có thể cấu hình kênh riêng cho flow hoặc thiết kế subscriber phân loại lỗi. Không nhầm với QueueChannel, nơi một message có thể được một consumer lấy ra theo cơ chế queue.

### 6.4. Tự định nghĩa global errorChannel có an toàn không?

Framework cho phép tùy biến cấu hình channel/error handler trong những bối cảnh nhất định, nhưng **cách thay thế bean errorChannel và mặc định LoggingHandler phụ thuộc cấu hình cùng phiên bản Spring Integration**. Trước khi khai báo bean cùng tên, cần kiểm tra ứng dụng có auto-config hay explicit integration configuration, và hậu quả với các endpoint đang dùng fallback. Với một bài thực hành nhập môn, ưu tiên **subscribe vào kênh hiện có** thay vì thay thế nó.

## 7. Ví dụ: poller đọc file và định tuyến lỗi

Inbound File adapter thường sử dụng poller để dò file mới. Khác với gateway HTTP đồng bộ, nó không có một caller đang đợi exception. Một ví dụ minh họa bằng **Spring Integration Java DSL**:

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

@Configuration
public class FileImportFlow {

    @Bean
    public MessageChannel fileErrors() {
        return new PublishSubscribeChannel();
    }

    @Bean
    public IntegrationFlow inboundFileFlow() {
        return IntegrationFlow
                .from(
                        Files.inboundAdapter(new File("data/inbox"))
                                .autoCreateDirectory(true),
                        spec -> spec.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(3))
                                        .maxMessagesPerPoll(1)
                                        .errorChannel("fileErrors")))
                .handle(message -> {
                    File file = (File) message.getPayload();
                    throw new IllegalStateException(
                            "Demo failure while importing: " + file.getName());
                })
                .get();
    }

    @ServiceActivator(inputChannel = "fileErrors")
    public void onFileFailure(ErrorMessage message) {
        System.err.println("File poller failure: "
                + message.getPayload().getClass().getSimpleName());
    }
}
~~~

**Lưu ý khả năng tương thích:** ví dụ mô tả một cấu hình Java DSL phổ biến; tên overload/kiểu spec và các lựa chọn poller có thể thay đổi giữa các phiên bản Spring Integration. Khi triển khai, cần đối chiếu Java DSL đúng phiên bản dependency trong dự án. Code trên **cố ý ném lỗi** để minh họa luồng, không phải handler xử lý file production.

Trong ví dụ:

1. File inbound adapter nhận file khi poller chạy;
2. Message đi tới handler xử lý;
3. Handler ném exception;
4. **Error handler của poller**, nếu được thiết lập như trên và áp dụng với lỗi đó, publish ErrorMessage tới fileErrors;
5. Service Activator trên fileErrors nhận thông tin lỗi.

Nếu bỏ cấu hình kênh riêng ở poller, cơ chế mặc định có thể gửi lỗi tới **errorChannel** toàn cục khi error publisher sử dụng global fallback. Điều này cần được kiểm thử trên flow cụ thể.

**Cảnh báo về file nguồn:** việc publish ErrorMessage không tự chuyển file vào thư mục quarantine, không tự bảo đảm file sẽ được đọc lại và không mặc nhiên rollback dấu đánh dấu file đã nhận. Những điều này phụ thuộc FileListFilter, AcceptOnceFileListFilter, cách di chuyển/xóa file, idempotency và chiến lược xử lý file sau lỗi.

### 7.1. Vì sao không nên gửi message lỗi chứa toàn bộ file?

Một file import có thể chứa dữ liệu cá nhân hoặc hàng triệu dòng. Nếu error handler ghi toàn bộ payload, log sẽ phình to và có thể rò rỉ dữ liệu. Nên lấy **tên file, checksum, attempt count, correlation ID, exception type** và vị trí an toàn, rồi chuyển file vào quarantine theo workflow có phân quyền.

### 7.2. Thiết kế kết quả cuối của file

| Kết quả xử lý | Hành động gợi ý |
|---|---|
| Parse thành công | Chuyển file sang processed hoặc ghi state thành công |
| Lỗi tạm thời DB/HTTP | Retry có backoff và giới hạn, dùng idempotency |
| File sai schema không sửa được | Quarantine, ghi lý do và yêu cầu người xử lý |
| File bị khóa/chưa ghi xong | Chờ file ổn định, tránh ingest khi chưa hoàn chỉnh |
| Lỗi permission/path | Alert vận hành, không retry dồn dập |

Một lỗi có thể xảy ra **trước khi Spring Message tồn tại** (ví dụ tạo thư mục hoặc kết nối file system). Khi đó failedMessage có thể rỗng hoặc bối cảnh khác. Cần chú ý log của poller/adapter và không giả định ErrorMessage luôn chứa File payload.

## 8. Chọn errorChannel theo endpoint hoặc message

### 8.1. Kênh toàn cục và kênh riêng

Nếu tất cả lỗi đều rơi về errorChannel toàn cục, handler cần phân loại theo flow, source và exception. Trong hệ thống nhiều adapter, một chính sách cụ thể theo endpoint thường dễ bảo trì hơn:

~~~mermaid
flowchart TD
    FILE["File poller"] --> F["fileErrors"]
    SFTP["SFTP poller"] --> S["sftpErrors"]
    HTTP["HTTP outbound flow"] --> H["httpErrors / advice"]
    BROKER["JMS / AMQP / Kafka listener"] --> B["Broker/container error policy"]
    F --> Q["Quarantine hoặc retry có giới hạn"]
    S --> A["Reconnect/backoff và cảnh báo"]
    H --> R["HTTP retry/compensation"]
    B --> D["Broker redelivery / DLQ / DLT nếu cấu hình"]
    OTHER["Error publisher không chọn kênh riêng"] --> G["errorChannel global"]
    G --> L["Logging / monitoring / triage"]
~~~

Đây là kiến trúc minh họa, không khẳng định HTTP flow hoặc broker tự động có channel tên httpErrors/brokerErrors. Những channel đó cần được cấu hình ở điểm thích hợp hoặc thông qua advice/flow riêng.

### 8.2. Header errorChannel

Spring Messaging định nghĩa header chuẩn **MessageHeaders.ERROR_CHANNEL**, thường có giá trị tên header là errorChannel. Khi một cơ chế error publisher hỗ trợ phân giải header này, message có thể chỉ định kênh trả lỗi. Ví dụ minh họa cách gắn header:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> request = MessageBuilder.withPayload("order-274")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "orderErrors")
        .setHeader("correlationId", "import-2026-001")
        .build();
~~~

**Gắn header không tự tạo error handler.** Phải có kênh orderErrors phù hợp và endpoint/error publishing strategy thực sự sử dụng header đó. Một synchronous DirectChannel vẫn có thể ném exception ngược sender mà không gửi tới orderErrors. Cũng không nên cho caller không đáng tin tự chỉ định kênh lỗi nội bộ tùy ý, vì có thể làm rò rỉ dữ liệu hoặc định tuyến sai.

### 8.3. Original message và correlation

Với pipeline biến đổi payload qua nhiều bước, cần duy trì một **correlation ID** xuyên suốt và ghi nhận tên adapter/flow tại thời điểm lỗi. Không giả định mọi lỗi đều có originalMessage của message ban đầu; có trường hợp chỉ có failedMessage ngay trước endpoint lỗi.

Một error event tối thiểu:

~~~json
{
  "flow": "sftp-order-import",
  "adapter": "sftp-inbound",
  "correlationId": "import-2026-001",
  "messageId": "8c8b...example",
  "exceptionType": "MessageHandlingException",
  "stage": "parse-csv",
  "attempt": 2,
  "outcome": "quarantined"
}
~~~

Giá trị chỉ minh họa; không lấy exception message có chứa mật khẩu, URL secret hoặc dữ liệu khách hàng rồi ghi nguyên văn nếu không có cơ chế lọc.

## 9. Lỗi đến từ đâu trong từng loại adapter?

| Adapter / gateway | Lỗi thường gặp | Điểm cần xem trước errorChannel |
|---|---|---|
| File inbound | I/O, quyền file, parse dữ liệu, file chưa ổn định | Poller, file filter, move/delete policy |
| SFTP inbound/outbound | Timeout, authentication, permission, network, file rename | Session factory/caching, poller, remote synchronization |
| HTTP inbound gateway | Request validation, payload conversion, handler exception | HTTP status/response mapping, timeout |
| HTTP outbound gateway/adapter | DNS, connection timeout, HTTP 4xx/5xx, response conversion | Client error handler, sync exception/advice |
| JMS inbound/outbound | Broker down, conversion, listener exception, transaction | Listener container, acknowledgment, redelivery/DLQ |
| AMQP/RabbitMQ | Publish failure, consumer exception, reject/nack | Broker ack, retry/requeue, DLX/DLQ |
| Kafka | Deserialize, poll, listener error, offset/commit | Listener container, CommonErrorHandler/recovery strategy |
| JDBC inbound/outbound | SQL syntax, constraint, deadlock, timeout | Transaction boundary, query/update semantics |

**Không có một chiến lược errorChannel mặc định có thể xử lý đúng mọi lỗi giao thức.** File cần biết file có bị đọc lại không; HTTP cần trả status tương ứng; JMS/Kafka phải cân nhắc acknowledgment và transaction; JDBC phải biết rollback. Đường ErrorMessage chỉ là một phần của bức tranh.

## 10. File và SFTP: từ ErrorMessage đến xử lý lại an toàn

### 10.1. File inbound

Với FileReadingMessageSource, poller lấy file theo filter. Một file có thể được đánh dấu là đã được chấp nhận trước khi business handler hoàn tất; phụ thuộc filter và cách lưu metadata. Nếu handler thất bại mà không chuyển file/chỉnh trạng thái, file có thể:

- Không được đọc lại vì filter đã đánh dấu;
- Bị đọc lại sau restart và gây trùng nghiệp vụ;
- Bị pipeline khác đọc song song;
- Bị xóa/di chuyển bởi một bước không gắn với commit nghiệp vụ.

Giải pháp không chỉ là nghe errorChannel; phải thiết kế **idempotent processing**, file locking/ready checks, quarantine, record trạng thái và khả năng replay có kiểm soát. Nếu dùng persistent filter, cần biết lúc nào metadata được cập nhật và cơ chế reset.

### 10.2. SFTP inbound

SFTP inbound có thể đồng bộ file từ server ngoài về local hoặc xử lý trực tiếp tùy cấu hình. Lỗi có thể phát sinh khi kết nối, list remote directory, tải file, rename hoặc parse nội dung. Cần phân loại:

- **Transient:** kết nối/timeout — retry với backoff, giới hạn concurrency và alert nếu kéo dài;
- **Permanent:** sai mật khẩu/quyền truy cập — cần can thiệp cấu hình, không thử dồn dập;
- **Data failure:** file sai định dạng — cách ly file, thông báo đối tác cung cấp dữ liệu;
- **Partial transfer:** file tải dở — không đưa file chưa hoàn chỉnh vào downstream processing.

**Remote delete/rename phải gắn với chính sách thành công thực tế**, không mặc định publish ErrorMessage là đã xử lý thỏa đáng. Cần kiểm soát khi hai pollers cùng xử lý một remote file.

### 10.3. Error channel cho SFTP chưa đủ để bảo đảm “at-least-once”

Để thực hiện ít nhất một lần, cần thiết kế cách nhận lại input, retry với số lần, acknowledgment/delete phù hợp, durable state và khả năng xử lý trùng. Để đạt hiệu ứng “exactly-once” ở mức nghiệp vụ trong môi trường phân tán thường cần idempotency key và giao dịch/đối soát; không thể suy ra từ một ErrorMessage.

## 11. HTTP inbound/outbound: errorChannel không thay HTTP response

### 11.1. HTTP inbound gateway

HTTP inbound gateway thường nhận một request từ client và cần trả **HTTP response** trong thời gian chờ. Ví dụ POST /orders đi qua transformer và service activator:

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant G as HTTP inbound gateway
    participant F as Integration flow
    participant E as Error handling / mapping
    C->>G: POST /orders
    G->>F: Message request
    F-->>E: Validation/business failure
    E-->>G: Kết quả lỗi đã ánh xạ
    G-->>C: HTTP 4xx/5xx + response phù hợp
~~~

Đối với request đồng bộ, exception có thể lan ngược lên gateway. Ứng dụng phải quyết định **mã trạng thái, nội dung trả về, timeout và correlation ID**; không thể chỉ thêm một Service Activator trên global errorChannel rồi giả định client sẽ tự nhận HTTP 400 hoặc 503 đúng nghiệp vụ.

Ví dụ phân loại:

| Lỗi | HTTP response có thể phù hợp | Điều cần lưu ý |
|---|---|---|
| Request sai schema/thiếu field | 400 Bad Request | Không retry dữ liệu lỗi |
| Chưa xác thực | 401 Unauthorized | Phân biệt với quyền bị từ chối |
| Đã xác thực nhưng thiếu quyền | 403 Forbidden | Không lộ thông tin tài nguyên khác |
| Xung đột trạng thái nghiệp vụ | 409 Conflict | Chỉ dùng khi đúng ngữ nghĩa |
| Downstream tạm không khả dụng | 503 Service Unavailable | Có thể cân nhắc Retry-After |
| Lỗi không dự kiến | 500 Internal Server Error | Log server-side, không lộ stacktrace |

Đây là gợi ý mapping, không phải luật bắt buộc; ứng dụng phải tuân theo contract HTTP cụ thể.

### 11.2. HTTP outbound gateway/adapter

Một HTTP outbound endpoint có thể thất bại khi DNS/network không khả dụng, kết nối bị reset, response không hợp lệ hoặc phía đích trả 4xx/5xx. Tùy HTTP client và error handler, những trạng thái có thể được chuyển thành exception hoặc thông điệp response; **không mặc định mọi 4xx/5xx đều được publish tới errorChannel**.

Chiến lược cần phân biệt:

- **4xx do request sai:** thường không retry cùng request, chuyển sang sửa dữ liệu hoặc quy trình nghiệp vụ;
- **429/503:** có thể retry với backoff và xem xét Retry-After nếu được cung cấp;
- **Timeout:** có thể không biết server đích đã xử lý request hay chưa; retry ghi dữ liệu cần idempotency key;
- **5xx:** đánh giá tính tạm thời và khả năng chịu lỗi của đích;
- **Conversion exception:** kiểm tra hợp đồng payload/headers và content type.

### 11.3. Lỗi nằm ở gateway hay flow?

Với luồng đồng bộ, có thể xử lý bằng advice, error mapping, hoặc trả một response biểu diễn lỗi. Với luồng bất đồng bộ (chẳng hạn HTTP nhận request rồi gửi job vào queue), gateway có thể trả 202 Accepted trước; lỗi trong worker sẽ đi qua error path khác, không còn liên hệ trực tiếp tới HTTP caller ban đầu. Khi đó cần **job status**, callback hoặc event thông báo lỗi cho client, không cố trả HTTP response ở một thread đã kết thúc.

## 12. JMS và AMQP: errorChannel không thay broker acknowledgment

### 12.1. Hai loại vòng đời

Trong broker messaging, cần phân biệt:

1. **Spring Integration flow** đã xử lý message thành công hay chưa?
2. **Broker đã acknowledge/commit/reject/redeliver message nguồn hay chưa?**

Một ErrorMessage gửi thành công tới errorChannel **không tự định nghĩa kết quả ack/rollback**. Kết quả phụ thuộc listener container, transaction, acknowledgment mode và cấu hình error handling/retry của adapter.

### 12.2. JMS inbound

Trong JMS, session transaction hoặc acknowledge mode có thể quyết định broker gửi lại message khi listener không thành công. Nếu exception được bắt và chỉ ghi log ở một endpoint mà transaction nhìn thấy là “thành công”, broker có thể không redeliver như mong đợi. Ngược lại, throw exception có thể kích hoạt rollback/redelivery, dẫn tới lặp vô hạn nếu message bị poison và không có giới hạn xử lý.

Điểm cần thiết kế:

- Transaction boundary bao quanh nhận message và xử lý nghiệp vụ tới đâu;
- Lỗi có được ném lại để container biết xử lý thất bại không;
- Chính sách broker redelivery, delay, số lần và DLQ;
- Idempotency khi nhận lại cùng business message;
- Phân biệt lỗi payload vĩnh viễn với lỗi hạ tầng tạm thời;
- Chỉ đánh dấu đã xử lý khi hành động nghiệp vụ thực sự thành công.

### 12.3. AMQP/RabbitMQ

Với AMQP, consumer có thể ack, reject/nack, requeue hoặc cấu hình dead-letter exchange (DLX) và dead-letter queue (DLQ). Spring Integration AMQP adapters làm việc cùng RabbitMQ listener/container; cách retry, recover/reject phải tương thích với cấu hình đó.

| Tình huống | Hướng xử lý | Rủi ro cần tránh |
|---|---|---|
| DB đích tạm lỗi | Retry với giới hạn/backoff | Redelivery dồn dập làm nghẽn hệ thống |
| Payload không thể parse | Reject/quarantine/DLQ theo policy | Poison message lặp mãi |
| Downstream đã ghi DB nhưng chưa ack | Idempotency/dedupe khi redelivery | Ghi trùng |
| Credential broker sai | Alert/circuit/khôi phục cấu hình | Retry vô hạn không giải quyết được |
| Broker offline | Reconnect và giám sát | Không mất message chưa được xử lý |

Một handler subscriber errorChannel có thể phục vụ observability hoặc recovery, nhưng **không thay cấu hình DLX, acknowledgment hay broker retry**.

### 12.4. Khi nào dùng errorChannel ở broker flow?

Nếu adapter/container publish ErrorMessage theo cấu hình, một subscriber có thể ghi exception và context. Nhưng cần xác minh **việc gửi ErrorMessage có được coi là đã xử lý exception hay không** đối với listener container. Cần integration test kiểm tra cùng lúc:

- errorChannel hoặc custom channel có nhận được lỗi?
- Broker ack/nack/rollback/commit ra sao?
- Message có redelivery không, bao nhiêu lần?
- Sau khi vượt retry limit có vào DLQ đúng không?
- Có tạo side effect trùng không?

Không kết luận “at-least-once” hay “exactly-once” chỉ từ tên channel.

## 13. Kafka: errorChannel và cơ chế lỗi của Kafka container

Kafka thêm một chiều quan trọng: **offset**. Consumer poll records, ứng dụng xử lý, rồi offset commit dựa trên ack/transaction/configuration. Một ErrorMessage không tự làm offset quay lại hoặc gửi record sang dead-letter topic.

### 13.1. Các nơi có thể lỗi

| Giai đoạn | Lỗi ví dụ | Công cụ/cấu hình thường liên quan |
|---|---|---|
| Deserialization | Bytes không chuyển được thành object | Deserializer/error-handling deserializer, container |
| Poll/consume | Broker, authentication, rebalance | Kafka consumer/container |
| Spring Message conversion | Header, mapping, payload conversion | Adapter/converter |
| Flow handler | Validation, business exception | Error flow, retry advice |
| Outbound producer | Serialization, send failure, timeout | Producer callback/error handling, transaction |
| Offset commit | Commit thất bại, consumer fencing | Container/consumer configuration |

Trong các cấu hình dùng Spring for Apache Kafka, **CommonErrorHandler**, **DefaultErrorHandler** hoặc các recovery/publishing strategies là những cơ chế chuyên biệt để quản lý retry, offset và dead-letter topic. Khi Spring Integration Kafka adapters tham gia, cần hiểu **mối liên kết cụ thể giữa adapter và listener container**, thay vì giả định global errorChannel bao trọn mọi failure.

### 13.2. Retry một record không đồng nghĩa retry nguyên flow

Giả sử record K được đưa vào một handler Spring Integration, sau đó handler ném exception. Các khả năng khác nhau:

- Error handler của container xử lý retry record theo offset;
- Exception được publish thành ErrorMessage cho một flow lỗi;
- Một recovery component gửi record đến dead-letter topic;
- Offset được commit hoặc không tùy cấu hình và trạng thái transaction;
- Record được xử lý lặp, sinh side effect trùng nếu không idempotent.

Vì vậy phải kiểm thử đường đi end-to-end. Với dữ liệu order, nên có business key để chống cập nhật trùng khi redelivery.

### 13.3. Dead-letter topic và errorChannel

**DLT (dead-letter topic)** là một topic Kafka được tạo/quản trị theo chính sách để nhận record không xử lý được. **errorChannel** là một Spring MessageChannel; hai khái niệm khác nhau. Một error handler có thể gửi thông tin lỗi hoặc record sang DLT bằng cơ chế chuyên biệt, nhưng **không tự động có DLT chỉ vì đã có errorChannel**.

### 13.4. Test offset và side effect

Khi viết test cho Kafka:

1. Gửi một record hợp lệ và xác minh handler xử lý một lần theo test setup;
2. Gửi một record gây lỗi tạm thời, quan sát retry và số lần xử lý;
3. Gửi poison record, kiểm tra nó vào DLT/được cách ly theo chính sách;
4. Xác minh offset/commit không khiến record bị mất hoặc xử lý vô hạn;
5. Xác minh errorChannel subscriber chỉ nhận lỗi mà adapter/container được thiết kế publish;
6. Kiểm tra việc restart consumer và xử lý lặp qua idempotency key.

## 14. JDBC, transaction và lỗi ở adapter cơ sở dữ liệu

### 14.1. Polling inbound database

Một JDBC inbound adapter có thể dùng poller lấy các bản ghi còn chờ xử lý. Nếu query thành công nhưng xử lý downstream lỗi, điều gì xảy ra với row nguồn? Câu trả lời phụ thuộc cách SQL đánh dấu trạng thái, transaction và cơ chế cập nhật sau xử lý.

Ví dụ:

~~~text
pending_order table
  id=274, status=NEW

poller SELECT status=NEW
  --> handler gửi HTTP tới đối tác
  --> cập nhật status=PROCESSED nếu thành công
~~~

Nếu gửi HTTP thành công nhưng DB update thất bại, lần poll tiếp theo có thể gửi lại. Nếu DB đánh dấu PROCESSED trước rồi HTTP thất bại, message có thể bị bỏ qua trong các lần poll sau. **errorChannel không sửa được thứ tự và atomicity của hai hệ thống**.

### 14.2. Transaction boundary

Trong một DB transaction, lỗi có thể gây rollback nếu exception được chuyển đúng tới transaction manager. Nhưng request HTTP hoặc gửi broker khác không tự nằm trong cùng local transaction. Vì vậy cần:

- Thiết kế outbox/inbox hoặc trạng thái workflow để bảo đảm có thể phục hồi;
- Retry có điều kiện và idempotency key;
- Phân biệt lỗi deadlock/timeout tạm thời với schema/constraint không thể tự sửa;
- Không ghi “processed” trước khi quyết định commit phù hợp;
- Đối soát khi thao tác bên ngoài đã thực hiện nhưng ack/DB commit chưa hoàn tất.

### 14.3. SQL exception được publish ở đâu?

Trong flow đồng bộ, JdbcMessageHandler/JDBC outbound adapter có thể ném exception lên caller/poller. Lỗi chỉ tới errorChannel khi có cơ chế error publisher được cấu hình và áp dụng. Không tự giả định mọi DataAccessException đều trở thành ErrorMessage. Nếu transaction cần rollback, phải kiểm tra việc bắt exception trong handler có làm thay đổi kết quả transaction không.

## 15. Thiết kế retry, backoff, circuit breaker và recovery

### 15.1. ErrorMessage không tự retry

Một error handler ghi log rồi kết thúc **không tự phát lại message**. Retry phải được cấu hình ở đúng lớp:

- Advice quanh handler/outbound endpoint, ví dụ retry advice của Spring Integration;
- Poller/scheduler hoặc logic đọc lại file có trạng thái;
- HTTP client hoặc job retry queue;
- JMS/AMQP broker redelivery;
- Kafka container retry/error handler;
- Database transaction/retry coordination.

Không nên đặt retry ở mọi lớp cùng lúc mà không tính số lần tổng. Ví dụ HTTP client retry 3 lần, handler advice retry 3 lần và broker redeliver 5 lần có thể tạo hàng chục request tới cùng downstream.

### 15.2. Phân loại transient và permanent

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Transient infrastructure | Network timeout, broker temporarily unavailable | Retry có giới hạn, exponential backoff + jitter |
| Overload/rate limit | HTTP 429, dịch vụ quá tải | Tôn trọng giới hạn, Retry-After khi phù hợp |
| Permanent data | JSON/CSV sai schema, enum không hỗ trợ | Quarantine hoặc báo producer sửa dữ liệu |
| Authorization/config | Credential hết hạn, sai permission | Alert và sửa cấu hình; tránh retry dồn dập |
| Concurrency conflict | DB deadlock hoặc optimistic lock | Retry có điều kiện và idempotency |
| Business rejection | Order không hợp lệ, bị từ chối theo policy | Ghi trạng thái nghiệp vụ; thường không retry y nguyên |

### 15.3. Giới hạn retry

Một chính sách retry tốt nêu rõ:

1. **Điều kiện retry:** exception class/status code nào được phép;
2. **Số lần tối đa:** tránh vòng lặp vô hạn;
3. **Backoff:** delay và jitter để không tạo retry storm;
4. **Idempotency:** tránh tạo side effect trùng;
5. **Time budget:** timeout tổng và hủy khi request không còn ý nghĩa;
6. **Kết thúc:** chuyển quarantine/DLQ/DLT, đánh dấu failure, alert hoặc compensation;
7. **Bằng chứng:** attempt number, last error và người chịu trách nhiệm.

### 15.4. Circuit breaker và rate limit

Khi dịch vụ ngoài liên tục thất bại, circuit breaker có thể giảm áp lực bằng cách ngừng gửi request mới trong một khoảng thời gian. Nhưng khi breaker mở, error handling vẫn cần ghi được trạng thái nghiệp vụ và đặt lịch phục hồi; không mặc định “đã gửi ErrorMessage” nghĩa là message đã được bảo quản bền vững.

### 15.5. Recovery không giống catch-and-ignore

Nếu một error handler bắt exception, log WARN rồi trả về success, upstream có thể tin xử lý đã hoàn tất dù dữ liệu chưa được ghi. Cần chính sách rõ:

- Chỉ **swallow** khi nghiệp vụ thực sự chấp nhận bỏ message;
- Ném lại khi transaction/ack cần rollback;
- Gửi vào kho durable recovery nếu định xử lý sau;
- Trả kết quả lỗi cho gateway đồng bộ theo contract;
- Ghi reason và correlation để người vận hành có thể replay đúng.

## 16. Hợp đồng lỗi: xử lý ErrorMessage như sự kiện nghiệp vụ

### 16.1. Phân loại lỗi để quyết định hành động

Không nên dựa hoàn toàn vào class name của exception để quyết định retry. Cùng một IllegalStateException có thể thể hiện lỗi lập trình, dữ liệu không hợp lệ hoặc hệ thống chưa sẵn sàng. Bổ sung **stage**, **adapter**, **business key**, **response status**, **attempt number** và **khả năng phục hồi**.

| Loại logic | Ví dụ | Hướng xử lý |
|---|---|---|
| INVALID_INPUT | CSV thiếu field bắt buộc | Quarantine và yêu cầu sửa dữ liệu |
| TEMPORARY_UNAVAILABLE | SFTP timeout, HTTP 503 | Retry có backoff và giới hạn |
| PERMISSION_DENIED | HTTP 403, SFTP auth fail | Alert, kiểm tra credential/policy |
| DUPLICATE | orderId đã được xử lý | Idempotent success hoặc nghiệp vụ từ chối |
| CONFLICT | Optimistic locking, HTTP 409 | Reload state, retry có điều kiện |
| POISON_MESSAGE | Message luôn làm parser lỗi | DLQ/DLT hoặc quarantine |
| UNKNOWN | Exception chưa phân loại | Ghi metadata an toàn, điều tra |

Global errorChannel nên giữ vai trò ghi nhận và phân tuyến lỗi chung. Những quy tắc recovery đặc thù cho từng adapter nên nằm gần flow tương ứng để tránh một handler toàn cục có quá nhiều nhánh và side effect không kiểm soát.

### 16.2. Error event nghiệp vụ

~~~json
{
  "eventType": "integration.processing.failed",
  "flowId": "sftp-orders-import",
  "adapterType": "SFTP_INBOUND",
  "stage": "persist-order",
  "correlationId": "order-import-274",
  "businessKey": "order-274",
  "classification": "TEMPORARY_UNAVAILABLE",
  "exceptionType": "DataAccessResourceFailureException",
  "attempt": 3,
  "maxAttempts": 3,
  "disposition": "REQUIRES_RETRY_WORKER",
  "occurredAt": "2026-11-23T08:00:00Z"
}
~~~

Đây là **mô hình event do ứng dụng tự định nghĩa**, không phải cấu trúc mặc định của ErrorMessage. Một handler có thể chuyển từ ErrorMessage thành event như trên để gửi vào kho recovery bền vững theo thiết kế. Nếu event không được lưu thành công, không được khẳng định dữ liệu đã được bảo quản để xử lý sau.

### 16.3. Bảo toàn message contract qua các bước

Một flow có thể biến đổi payload từ File sang String rồi OrderCommand. Cần thỏa thuận:

- Business key nào dùng nhận diện và chống trùng?
- Correlation ID tạo ở inbound hay nhận từ đối tác?
- Những header nào cần bảo toàn qua transform/router/gateway?
- Payload nào được phép lưu trong log hoặc event recovery?
- Replay từ file gốc, message chuẩn hóa hay business command?
- Error event phải có reference và version nào để tránh xử lý lại dữ liệu cũ?

**Không gửi ErrorMessage ngược vào kênh input chứa OrderCommand**: payload của ErrorMessage là Throwable. Replay phải tạo lại message đúng hợp đồng và kiểm soát idempotency, không retry vô hạn vì thiếu phân loại lỗi.

## 17. Observability cho errorChannel

### 17.1. Log có cấu trúc

Thông tin nên có: tên flow và adapter, correlation ID, message ID, business key đã giảm nhạy cảm, exception class, stage (receive/transform/send/ack/commit), attempt, kết quả recovery và thời điểm. Không ghi nguyên văn token, password, private key, toàn bộ file chứa dữ liệu cá nhân hoặc HTTP body nhạy cảm.

### 17.2. Metrics cần theo dõi

| Metric | Mục tiêu |
|---|---|
| integration_errors_total theo flow và type | Đếm lỗi, phát hiện tỷ lệ lỗi tăng |
| integration_retries_total | Theo dõi chi phí retry |
| retries_exhausted_total | Biết thông điệp không tự phục hồi |
| quarantine_items hoặc DLQ depth | Đo backlog cần xử lý |
| message_processing_latency | Nhận biết độ trễ/timeout |
| last_successful_poll_timestamp | Phát hiện poller im lặng |
| consumer_lag/unacked_count | Theo dõi backlog broker khi phù hợp |
| error_handler_failure_total | Phát hiện chính error handler đang lỗi |

Không đặt messageId hoặc businessKey duy nhất làm metric label vì sẽ gây high cardinality; sử dụng log/trace để truy vấn theo correlation ID.

### 17.3. Trace xuyên adapter

Một message đi qua SFTP, Spring Integration, JDBC và HTTP có thể qua nhiều thread hoặc service. Trace context chỉ được bảo toàn khi hạ tầng và code thực sự truyền đúng headers/context. Không giả định ErrorMessage luôn có đủ span context, đặc biệt khi message đã được biến đổi nhiều lần.

### 17.4. Không có lỗi cũng có thể là sự cố

Poller dừng lấy file mà không ném exception; số ErrorMessage bằng 0 nhưng dữ liệu bị trễ. Ngoài alert theo tỷ lệ lỗi, cần alert **không có successful poll**, tuổi backlog vượt SLA, queue depth, last-successful-send, retry exhausted và permission failures. Một lỗi timeout đơn lẻ retry thành công thường không nên gửi alert như sự cố nghiêm trọng.

## 18. Case study: SFTP → CSV → JDBC → HTTP → Kafka

### 18.1. Bối cảnh

Ứng dụng theo dõi thư mục SFTP do nhà phân phối gửi file đơn hàng. Mỗi file chứa nhiều dòng. Hệ thống tải file, parse CSV, kiểm tra dữ liệu, lưu đơn hàng vào DB, gọi HTTP outbound gateway để xác nhận và phát sự kiện Kafka khi hoàn tất.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound poller"]
    CSV["CSV parser và validator"]
    DB["JDBC persistence"]
    HTTP["HTTP outbound"]
    KAFKA["Kafka outbound"]
    GLOBAL["errorChannel mặc định"]
    LOCAL["Kênh lỗi riêng / advice / container strategy"]
    OPS["Logging, metrics, triage"]
    SFTP --> CSV --> DB --> HTTP --> KAFKA
    SFTP -. "Lỗi poller nếu publish global" .-> GLOBAL
    CSV -. "Lỗi được cơ chế bắt và publish" .-> LOCAL
    DB -. "SQLException" .-> LOCAL
    HTTP -. "HTTP failure" .-> LOCAL
    KAFKA -. "Producer failure" .-> LOCAL
    GLOBAL --> OPS
    LOCAL --> OPS
~~~

Sơ đồ không mô tả một giao dịch phân tán bao trùm SFTP, JDBC, HTTP và Kafka; **mỗi hệ thống có cơ chế trạng thái riêng**.

### 18.2. Tình huống A — SFTP timeout trước khi tải file

Poller kết nối thất bại. Chưa chắc đã có Message đại diện file, do đó failedMessage có thể null. Error strategy của poller có thể publish ErrorMessage với exception kết nối. Cần:

1. Ghi adapter, host định danh an toàn, stage = connect/list và loại exception;
2. Retry có backoff, không mở vô hạn session mới;
3. Giám sát thời gian không nhận file và cảnh báo nếu vượt ngưỡng;
4. Tránh đưa file tải dở vào parser;
5. Khi kết nối lại, đối soát remote/local file và trạng thái filter.

### 18.3. Tình huống B — CSV sai schema

File đã tải nhưng một dòng thiếu mã đơn hàng. Handler ném lỗi validation. Nếu error strategy publish ErrorMessage, có thể lấy failedMessage để xác định file/dòng lỗi, tuy nhiên nội dung payload tùy stage.

**Không retry vô hạn** một file có lỗi dữ liệu vĩnh viễn. Nên quarantine file, ghi reason và correlation ID, yêu cầu bên gửi sửa, rồi replay có kiểm soát từ input đúng schema. Khi file đã được file filter đánh dấu, phải kiểm tra cách reset hoặc xử lý metadata để tránh vừa mất file vừa đọc trùng.

### 18.4. Tình huống C — DB lỗi giữa chừng

Một số dòng đã commit trước khi DB trở nên unavailable. Retry toàn file có thể tạo order trùng. Cần transaction phù hợp trong DB, business key/unique constraint và idempotent write. ErrorMessage không rollback được những row đã commit. Khi chưa biết chắc phần nào đã ghi, đối soát bằng business key trước khi replay.

### 18.5. Tình huống D — HTTP timeout sau khi downstream đã xử lý

Ứng dụng gửi POST xác nhận đơn hàng. Phía đối tác xử lý thành công nhưng response bị mất trên mạng. Retry không kiểm soát có thể xác nhận hai lần. Nên dùng idempotency key nếu API hỗ trợ, hoặc truy vấn trạng thái trước khi retry. Nếu kết quả không xác định, đánh dấu **needs reconciliation** thay vì mặc định request thất bại hoàn toàn.

### 18.6. Tình huống E — Kafka producer báo lỗi

DB đã ghi đơn và HTTP đã chạy, nhưng Kafka outbound producer không phát được event. Không thể rollback HTTP từ ErrorMessage. Có thể dùng **transactional outbox** gắn DB commit với ý định phát event, sau đó publisher retry gửi Kafka và ghi trạng thái phát. Recovery cần đảm bảo không sinh sự kiện trùng ngoài ý muốn hoặc consumer phải xử lý idempotent.

### 18.7. Kết quả học được

Global errorChannel hữu ích để quan sát những exception đã được publish mà không có error destination riêng. Nhưng phục hồi an toàn phải xét **SFTP file state, JDBC transaction, HTTP idempotency, Kafka producer/offset và các hợp đồng dữ liệu**. Cùng một Throwable không thể quyết định được tính an toàn khi replay nếu không biết side effect nào đã xảy ra.

## 19. Kiểm thử errorChannel mặc định và kênh lỗi riêng

### 19.1. Kiểm thử DirectChannel đồng bộ

Tạo một flow DirectChannel có handler chủ động ném IllegalStateException. Gửi message từ test và xác minh:

- Exception lan về caller theo flow đồng bộ hoặc được advice/gateway xử lý theo cấu hình;
- Không tự mong đợi global errorChannel nhận ErrorMessage nếu không có cơ chế publish lỗi;
- Khi có gateway, response code/body phản ánh đúng contract;
- Không có side effect bị coi là thành công nếu handler chưa hoàn tất.

**Bài học:** một exception đồng bộ và một ErrorMessage được publish là hai sự kiện kỹ thuật khác nhau.

### 19.2. Kiểm thử poller

Tạo File inbound adapter hoặc QueueChannel consumer với poller; handler ném exception. Cấu hình error channel cho poller hoặc dùng fallback đã được kiểm chứng. Xác nhận:

1. Poller lấy message và handler được gọi;
2. ErrorMessage được gửi đúng channel;
3. ErrorMessage.payload là Throwable;
4. Nếu có failedMessage, message ID/correlation liên hệ input test;
5. Lỗi không bị xem là success ngoài ý muốn;
6. Retry, quarantine, rollback hoặc replay xảy ra đúng chính sách được thiết kế.

### 19.3. Dùng QueueChannel để nhận lỗi trong test

Với test, một QueueChannel riêng có thể giúp nhận ErrorMessage và assert kết quả một cách dễ kiểm soát. Ví dụ cấu hình bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;

@Configuration
class TestErrorChannelConfig {

    @Bean
    QueueChannel testErrors() {
        return new QueueChannel();
    }
}
~~~

Sau khi flow test đã được cấu hình **gửi ErrorMessage đến testErrors** và thực thi, có thể kiểm tra:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

// testErrors được lấy từ Spring context và đã được cấp trong flow test.
Message<?> received = testErrors.receive(5_000);

if (!(received instanceof ErrorMessage)) {
    throw new AssertionError("Expected ErrorMessage on testErrors");
}

Throwable problem = ((ErrorMessage) received).getPayload();
if (problem == null) {
    throw new AssertionError("Missing Throwable payload");
}
~~~

Đây là đoạn assert minh họa, không phải một class test độc lập có thể chạy nếu chưa dựng flow. Trong test thực tế, dùng JUnit/AssertJ, thời gian chờ hữu hạn và dọn trạng thái sau test. **Không thay global errorChannel production bằng QueueChannel chỉ để tiện assert**.

### 19.4. Kiểm thử không có subscriber hoặc error handler thất bại

Với custom error channel cần làm rõ:

- Điều gì xảy ra nếu không có subscriber hoặc channel từ chối gửi?
- QueueChannel có giới hạn capacity không, hành vi khi đầy ra sao?
- Error handler có ném exception nếu downstream alerting/DB lỗi không?
- Có sinh vòng lặp error-of-error hoặc gửi thông báo nhiều lần?
- Các failure có được đếm/alert ngay cả khi error handler riêng bị lỗi?

Hành vi phụ thuộc loại channel và các thuộc tính như send timeout/requireSubscribers. Cần kiểm thử trên cấu hình thực thay vì suy từ tên channel.

### 19.5. Ma trận test theo adapter

| Adapter | Kích hoạt lỗi | Tiêu chí kiểm tra |
|---|---|---|
| File | CSV sai format | Lỗi được quan sát, file cách ly, replay rõ |
| SFTP | Timeout hoặc permission denied | Backoff, không tải dở, cảnh báo |
| HTTP inbound | Request sai schema | Response 4xx, không trả stacktrace |
| HTTP outbound | Timeout/503 | Retry budget, idempotency và outcome |
| JMS | Handler throw | Transaction, redelivery và DLQ theo cấu hình |
| AMQP | Poison message | Reject/nack/requeue/DLQ đúng |
| Kafka | Record không deserialize được | Container error strategy, offset và DLT |
| JDBC | SQLException | Transaction rollback/row state và replay |

Không cần chạy mọi hệ thống ngoài để hiểu global errorChannel. Tuy nhiên, **không nên coi bài test unit cho ErrorMessage tương đương kiểm thử delivery semantics của broker và transaction thực tế**.

## 20. Runbook chẩn đoán lỗi trong Spring Integration

### Bước A — Xác định vị trí lỗi

1. Xác định tên flow, message source, endpoint/adapter và correlation ID;
2. Xem exception xuất hiện trong caller, poller, executor, container hay HTTP response;
3. Kiểm tra có ErrorMessage được publish hay không, ở channel nào;
4. Xác định failedMessage/originalMessage có tồn tại và có chứa thông tin hữu ích không;
5. Phân biệt lỗi nguồn, lỗi transform, lỗi handler, lỗi gửi outbound và lỗi ack/commit.

### Bước B — Đánh giá dữ liệu đã được xử lý đến đâu

1. File đã được tải, đánh dấu nhận, move/delete hay chưa?
2. DB đã commit dòng nào, có side effect nào không?
3. HTTP downstream đã nhận/thi hành request dù caller timeout chưa?
4. Broker đã ack/commit offset hay có redelivery?
5. API client/connector có đang lỗi cấu hình hoặc authentication không?
6. Một message có thể đang được xử lý song song và gây trùng không?

### Bước C — Chọn biện pháp

| Kết luận | Hành động |
|---|---|
| Transient và retry an toàn | Retry với backoff, giới hạn và idempotency |
| Dữ liệu vĩnh viễn sai | Quarantine/DLQ/DLT, phản hồi producer |
| Broker acknowledgment không đúng | Sửa listener/container transaction/ack config |
| DB partial commit | Đối soát transaction và business key |
| HTTP outcome không xác định | Truy vấn trạng thái hoặc reconciliation |
| Error handler làm mất thông tin | Bổ sung error event/context an toàn |
| Lỗi không sinh ErrorMessage | Kiểm tra nơi exception được ném và error strategy |

### Bước D — Kiểm chứng phục hồi

Xác nhận input không mất, không xử lý trùng trái ý muốn, quyền truy cập log được bảo vệ, retry không gây quá tải, DLQ/quarantine có owner và số liệu cảnh báo được cập nhật. Sau khi fix, kiểm thử **success path và failure path** để chắc rằng luồng không bị thay đổi ngoài mục đích.

### Bước E — Đóng sự cố bằng bằng chứng

Ghi nhận nguyên nhân gốc, điểm lỗi, phiên bản cấu hình, thời gian ảnh hưởng, số message lỗi, message đã replay, dữ liệu cần reconciliation và hành động phòng tránh lặp lại. Không chỉ ghi “đã xử lý ở errorChannel”; cần chứng minh **message nghiệp vụ cuối cùng đạt trạng thái nào**.

## 21. Sai lầm thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Tin mọi exception tự đi errorChannel | Bỏ sót lỗi đồng bộ | Phân tích điểm throw và error publisher |
| Chỉ lắng nghe global channel, bỏ qua per-flow handlers | Không theo dõi được lỗi ở flow chuyên biệt | Kiểm tra routing và cơ chế từng adapter |
| Coi LoggingHandler là cơ chế retry | Message thất bại bị bỏ lại hoặc mất | Thiết kế retry/recovery riêng |
| Catch exception rồi return success | Ack/commit dù nghiệp vụ thất bại | Bảo toàn failure semantics, transaction đúng |
| Retry mọi loại lỗi | Poison message và retry storm | Phân loại transient/permanent, giới hạn |
| Nhiều lớp retry không tính budget | Số lần gọi downstream tăng mạnh | Tính retry tổng và timeout |
| Không dùng idempotency | Replay gây order trùng | Business key, dedupe/outbox |
| Ghi toàn bộ payload lỗi vào log | Rò rỉ dữ liệu, log quá tải | Structured metadata, masking |
| Gửi ErrorMessage ngược vào business input | Consumer gặp Throwable sai contract | Replay đúng message gốc/command |
| Lầm errorChannel với JMS DLQ hoặc Kafka DLT | Hiểu sai delivery/offset semantics | Cấu hình container/broker riêng |
| Bỏ qua trạng thái file filter | File bị mất hoặc xử lý lại sai | Metadata store, quarantine, test restart |
| HTTP timeout coi chắc chắn chưa xử lý | Tạo side effect lặp | Idempotency key/reconciliation |
| Chỉ xem error count | Poller chết im lặng không được phát hiện | Monitor last poll, backlog, latency |
| Handler lỗi lại ném vào chính nó | Lặp error và trùng alert | Tách recovery, giới hạn side effect |
| Dùng PublishSubscribeChannel mà tưởng một consumer nhận | Nhiều handler cùng hành động | Phân tách trách nhiệm, idempotent notification |
| Không test transaction và ack | Record mất/trùng khi broker fail | Integration test container và offset/ack |

## 22. Checklist trước khi đưa error flow vào production

### A. Hiểu đường lỗi

- [ ] Xác định channel/endpoint nào đồng bộ, poller hoặc message-driven.
- [ ] Biết exception nào truyền ngược caller và exception nào được publish.
- [ ] Có thể truy vết ErrorMessage tới message hoặc business key khi dữ liệu sẵn có.
- [ ] Biết rõ global errorChannel có subscriber nào, có ghi log trùng không.
- [ ] Những flow cần recovery riêng có kênh lỗi/advice/container policy riêng.

### B. Hợp đồng message và bảo mật

- [ ] Payload, headers và correlation ID được định nghĩa.
- [ ] Có taxonomy lỗi và stage đủ để phân loại retry.
- [ ] Log và error event không để lộ password, token, private key hoặc dữ liệu nhạy cảm.
- [ ] Không cho header errorChannel từ caller không đáng tin điều hướng nội bộ tùy ý.
- [ ] Replay dùng message đúng schema, có idempotency.

### C. Delivery và transaction

- [ ] File/SFTP có kiểm soát file ready, filter, move/quarantine và replay.
- [ ] HTTP có timeout, status mapping, idempotency key và time budget.
- [ ] JMS/AMQP có ack/tx, redelivery, retry limit và DLQ khi cần.
- [ ] Kafka có container recovery, offset/commit và DLT khi cần.
- [ ] JDBC có transaction/outbox hoặc cơ chế chống partial commit phù hợp.
- [ ] Retry chỉ áp dụng với failure có thể phục hồi, có backoff và giới hạn.

### D. Vận hành

- [ ] Có metrics theo flow, stage, retry exhausted, backlog và error handler failure.
- [ ] Có alert khi poller không xử lý thành công trong thời gian kỳ vọng.
- [ ] Có owner cho quarantine/DLQ/DLT và quy trình replay.
- [ ] Test cả direct synchronous exception lẫn poller-published ErrorMessage.
- [ ] Test một message poison, một timeout transient, một transaction failure và restart.
- [ ] Kết quả lỗi được xác minh end-to-end, không chỉ thấy log.

## 23. Câu hỏi tự kiểm tra

**Câu 1. errorChannel mặc định có chức năng chính là gì?**

**Trả lời:** Là một MessageChannel toàn cục nhận **ErrorMessage được publish** bởi các cơ chế error handling có sử dụng fallback này. Nó không tự bắt mọi exception và không tự retry, rollback hay đẩy dữ liệu vào DLQ.

**Câu 2. Vì sao handler trên DirectChannel ném exception mà subscriber của errorChannel không thấy lỗi?**

**Trả lời:** DirectChannel thường xử lý đồng bộ; exception có thể lan ngược tới sender. Chỉ khi một lớp xử lý được thiết kế bắt rồi publish ErrorMessage thì kênh lỗi mới nhận được.

**Câu 3. Payload của ErrorMessage là gì?**

**Trả lời:** Một Throwable. Nó có thể là MessagingException chứa failedMessage. Original message cũng có thể tồn tại nếu được cung cấp, nhưng không nên dựa vào việc hai trường này luôn có dữ liệu.

**Câu 4. Đăng ký @ServiceActivator(inputChannel = "errorChannel") có thay thế LoggingHandler mặc định không?**

**Trả lời:** Không nhất thiết. Khi errorChannel là PublishSubscribeChannel, nhiều subscriber có thể nhận cùng message, bao gồm logging subscriber hiện có. Cần kiểm tra context để tránh log/side effect trùng.

**Câu 5. File inbound poller ném exception và errorChannel ghi log. File đã được xử lý lại chưa?**

**Trả lời:** Chưa thể kết luận. Phải xem file filter, metadata, chính sách move/delete, transaction nếu có và workflow retry. Ghi log không bảo đảm retry.

**Câu 6. HTTP inbound gateway lỗi validation. Có nên chỉ đưa ErrorMessage tới global errorChannel?**

**Trả lời:** Không đủ. Caller HTTP cần status/body phù hợp và timeout rõ ràng. Cần exception/response mapping tại gateway/web layer hoặc error flow được thiết kế riêng.

**Câu 7. Trong JMS, ErrorMessage có thể thay cho broker rollback không?**

**Trả lời:** Không. Acknowledgment, rollback, redelivery và DLQ chịu ảnh hưởng của listener container, session transaction và broker policy. Phải kiểm thử cùng error flow.

**Câu 8. Kafka đã có errorChannel thì có sẵn dead-letter topic chưa?**

**Trả lời:** Không. Kafka DLT/offset/recovery phải được cấu hình riêng theo adapter và Kafka listener/container. Một Spring MessageChannel không phải Kafka topic.

**Câu 9. HTTP POST timeout có nghĩa server chưa xử lý request phải không?**

**Trả lời:** Không. Server có thể đã commit thao tác nhưng response bị mất. Retry ghi dữ liệu cần idempotency key hoặc kiểm tra trạng thái để tránh tác động trùng.

**Câu 10. Vì sao cần ghi correlation ID thay vì log toàn bộ payload?**

**Trả lời:** Correlation ID giúp lần theo dữ liệu giữa các bước mà không cần xuất lộ thông tin nhạy cảm. Payload có thể chứa dữ liệu cá nhân, secret hoặc rất lớn, gây rủi ro bảo mật và vận hành.

**Câu 11. Handler nhận ErrorMessage có thể gửi lại chính ErrorMessage vào input channel để replay không?**

**Trả lời:** Không nên. Input business thường chờ một schema khác, còn ErrorMessage có payload Throwable. Replay phải tái tạo lệnh/message đúng contract, kiểm tra trạng thái side effect và dùng idempotency.

**Câu 12. Tại sao phải monitor poller ngay cả khi errorChannel không có lỗi?**

**Trả lời:** Poller có thể ngừng chạy hoặc không lấy dữ liệu do cấu hình mà không phát ErrorMessage. Cần last-successful-poll, backlog, age of oldest item và health signals.

**Câu 13. Khi nào nên tách fileErrors riêng khỏi errorChannel?**

**Trả lời:** Khi flow file cần xử lý riêng như quarantine, retry hoặc SLA khác với HTTP/broker. Kênh riêng giúp tách recovery policy và owner, còn global channel có thể giữ monitoring tổng quan.

**Câu 14. Một retry tại handler và một retry tại broker có thể gây ra vấn đề gì?**

**Trả lời:** Tổng số lần thực hiện có thể nhân lên, gây quá tải hoặc side effect trùng. Cần tính retry budget theo end-to-end, backoff và xử lý trùng dữ liệu.

**Câu 15. Chứng cứ nào cho thấy error handling thành công?**

**Trả lời:** Không chỉ là sự xuất hiện của log. Phải chứng minh input đã thành công, được retry có kết quả, đưa vào quarantine/DLQ hoặc ở trạng thái lỗi có owner; đồng thời trạng thái file/DB/HTTP/broker và acknowledgment phù hợp.

## 24. Kết luận

Trong **Spring Integration Adapters**, **errorChannel mặc định** là cơ chế quan trọng để **tiếp nhận lỗi đã được chuyển thành ErrorMessage**, nhất là các tình huống poller và luồng không có caller đồng bộ nhận exception. Thông thường kênh toàn cục có subscriber ghi log; ứng dụng có thể thêm Service Activator để quan sát hoặc phân loại. Tuy nhiên, **đường lỗi thực tế phụ thuộc endpoint, channel, error strategy, advice và adapter**, nên không thể đồng nhất “throw exception” với “đã vào errorChannel”.

Thiết kế đáng tin cậy cần kết hợp **message contract, correlation ID, phân loại lỗi, retry có giới hạn, idempotency, acknowledgment, transaction và recovery có chủ sở hữu**. Với File/SFTP, phải quản lý file state và replay; với HTTP, phải xử lý response và timeout; với JMS/AMQP/Kafka, phải hiểu broker/container acknowledgment và dead-letter; với JDBC, phải xác minh commit và các side effect. Global errorChannel giúp nhìn thấy sự cố, nhưng **chính sách từng hệ thống** mới quyết định thông điệp có được xử lý lại, từ chối hay cách ly đúng cách.

Điều cần ghi nhớ: **bắt được lỗi chưa phải đã phục hồi được luồng tích hợp**. Chỉ khi có kiểm chứng end-to-end rằng thông điệp nghiệp vụ đạt trạng thái mong muốn hoặc được lưu để xử lý sau một cách an toàn, hệ thống mới có thể coi tình huống lỗi đã được xử lý đầy đủ.
