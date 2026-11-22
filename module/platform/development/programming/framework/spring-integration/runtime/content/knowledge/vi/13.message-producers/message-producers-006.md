# Error channel của message producer

Trong Spring Integration Runtime, message producer thường là một inbound channel adapter nhận dữ liệu từ hệ thống bên ngoài rồi phát Spring Message vào output channel. Khi việc tạo hoặc chuyển message vào flow gặp lỗi, error channel cho phép endpoint chuyển lỗi thành một ErrorMessage để một nhánh xử lý riêng có thể ghi log, phân loại, cảnh báo, lưu lỗi hoặc định tuyến sang nơi phục hồi.

Error channel không phải là cơ chế tự retry và cũng không bảo đảm message nguồn sẽ được xác nhận hay phát lại. Kết quả đó còn phụ thuộc loại producer, transaction, acknowledgement và cách error flow kết thúc.

## Message producer phát lỗi ở đâu?

Một message producer như message-driven channel adapter nhận dữ liệu từ broker hoặc transport, chuyển đổi thành Spring Message rồi gửi đến output channel. Lỗi có thể xảy ra khi chuyển đổi dữ liệu, tạo message, gửi message vào channel hoặc khi một handler phía sau ném exception trong một đường truyền đồng bộ.

~~~mermaid
flowchart LR
    S["Broker / external source"] --> P["Message producer"]
    P --> O["Output channel"]
    O --> F["Integration flow"]
    P -. "exception" .-> E["ErrorMessage"]
    E --> EC["Producer error channel"]
    EC --> H["Error handler / recovery flow"]
~~~

Các endpoint dựa trên MessageProducerSupport cung cấp thuộc tính error channel. Có thể cấu hình bằng đối tượng MessageChannel hoặc tên bean. Nếu không cấu hình error channel, endpoint sẽ truyền exception trở lại message-driven source để transport/container xử lý theo chính sách của nó. Đặt nullChannel làm error channel sẽ loại bỏ lỗi khỏi luồng xử lý; chỉ dùng khi việc bỏ qua lỗi là chủ đích.

## ErrorMessage chứa gì?

Spring Integration biểu diễn lỗi dưới dạng ErrorMessage. Payload của ErrorMessage là một Throwable, thường là exception đã xảy ra. ErrorMessage còn có thể mang originalMessage để truy vết message đã gây lỗi, cùng các headers liên quan.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

void inspect(ErrorMessage errorMessage) {
    Throwable cause = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    // cause: exception cần phân loại hoặc ghi nhận
    // original: message đầu vào nếu có thể xác định
}
~~~

Không phải lỗi nào cũng có originalMessage. Ví dụ, lỗi xảy ra trước khi Spring Message được tạo hoàn chỉnh có thể không có message gốc. Khi xử lý lỗi, hãy luôn kiểm tra giá trị này trước khi đọc payload hoặc header. Tránh ghi toàn bộ payload vào log nếu message có dữ liệu cá nhân, bí mật hoặc thông tin xác thực.

## Cấu hình error channel riêng cho producer

Ví dụ dùng JMS message-driven channel adapter. Error channel được gắn trực tiếp vào producer endpoint:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageChannel;
import jakarta.jms.ConnectionFactory;

@Bean
MessageChannel producerErrorChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow ordersInbound(ConnectionFactory connectionFactory) {
    return IntegrationFlow.from(
                    Jms.messageDrivenChannelAdapter(connectionFactory)
                            .destination("orders")
                            .errorChannel("producerErrorChannel"))
            .channel("orders.input")
            .get();
}
~~~

Với XML namespace, adapter có thuộc tính error-channel tương ứng:

~~~xml
<int-jms:message-driven-channel-adapter
        id="ordersInbound"
        destination="orders"
        channel="orders.input"
        error-channel="producerErrorChannel"/>
~~~

Các transport adapter khác có thể cung cấp cấu hình tương đương thông qua DSL, namespace hoặc endpoint bean. Ở tầng API, MessageProducerSupport có các phương thức setErrorChannel và setErrorChannelName. Hãy kiểm tra API của adapter cụ thể và phiên bản Spring Integration đang dùng vì không phải mọi loại inbound source đều có cùng thuộc tính cấu hình.

Tạo consumer cho channel lỗi để ErrorMessage không bị bỏ lại mà không xử lý:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
class ProducerErrorHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ProducerErrorHandler.class);

    @ServiceActivator(inputChannel = "producerErrorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        Message<?> original = errorMessage.getOriginalMessage();

        log.error("Inbound producer failed; original message: {}",
                original, cause);

        // Phân loại lỗi, phát metric hoặc chuyển đến recovery flow.
    }
}
~~~

Nếu muốn tách các loại lỗi, consumer có thể chuyển tiếp ErrorMessage đến router hoặc các channel riêng, ví dụ lỗi dữ liệu không hợp lệ, lỗi kết nối tạm thời và lỗi không thể phục hồi. Hãy giữ lại thông tin exception và định danh message khi định tuyến để có thể đối chiếu với log của transport.

## Phân biệt ba cơ chế định tuyến lỗi

Tên errorChannel xuất hiện ở nhiều lớp của Spring Integration, nhưng phạm vi áp dụng khác nhau.

| Cơ chế | Khi nào được dùng | Nơi nhận lỗi |
|---|---|---|
| Thuộc tính errorChannel của message producer | Producer endpoint phát lỗi khi tạo hoặc gửi message vào flow | Channel được cấu hình trên endpoint; nếu không có, exception được truyền về message-driven source |
| Header MessageHeaders.ERROR_CHANNEL | Một message được xử lý trong task bất đồng bộ và task đó phát sinh exception | Channel trong header của message lỗi; nếu không có thì dùng global errorChannel |
| errorChannel của poller | Task được scheduler kích hoạt để poll source hoặc chạy poller bị lỗi | Channel cấu hình cho poller; nếu không cấu hình thì dùng cơ chế error handler của scheduler, thường là global errorChannel |

### Lỗi trong flow đồng bộ

Với DirectChannel mặc định, handler chạy trên cùng thread gọi send. Nếu handler ném exception, exception có thể truyền ngược trên call stack đến sender. Đây là hành vi đồng bộ thông thường của Java. Một message-driven producer có error channel riêng có thể bắt lỗi trong thao tác gửi message và phát ErrorMessage đến channel đã cấu hình. Tuy nhiên, không nên giả định mọi exception trong mọi flow đồng bộ đều tự động được chuyển đến global errorChannel.

### Lỗi trong flow bất đồng bộ

Với ExecutorChannel hoặc một task chạy trong TaskExecutor, sender có thể đã kết thúc trước khi handler phát sinh exception. Framework dùng cơ chế MessagePublishingErrorHandler để phát ErrorMessage. Cơ chế này ưu tiên header errorChannel của message đang được xử lý; nếu không có header thì gửi đến channel toàn cục có tên errorChannel.

Có thể gắn channel riêng vào message trước khi đưa nó qua ranh giới bất đồng bộ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder.withPayload("order-123")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "ordersAsyncErrors")
        .build();
~~~

Header này điều khiển định tuyến lỗi của task bất đồng bộ xử lý message đó. Nó không thay thế thuộc tính errorChannel được cấu hình trực tiếp trên một MessageProducerSupport endpoint.

### Lỗi trong poller

Với inbound channel adapter dùng poller, lỗi có thể xảy ra khi gọi source, chuyển đổi dữ liệu hoặc gửi message vào output channel. Có thể cấu hình error channel trên poller:

~~~java
@InboundChannelAdapter(
        value = "polledInput",
        poller = @Poller(
                fixedDelay = "1000",
                errorChannel = "pollerErrors"
        )
)
public String pollSource() {
    return readNextRecord();
}
~~~

Lỗi của scheduled poller được đóng gói thành ErrorMessage bởi MessagePublishingErrorHandler. Nếu tự khai báo taskScheduler, cần bảo đảm scheduler có error handler phù hợp nếu muốn tiếp tục định tuyến lỗi qua message flow.

## Global errorChannel

Spring Integration tạo một bean mặc định tên errorChannel. Mặc định đây là PublishSubscribeChannel có LoggingHandler đăng ký để ghi lỗi ở mức ERROR. Các task bất đồng bộ không có header errorChannel riêng thường gửi lỗi về channel này.

Có thể đăng ký endpoint xử lý lỗi toàn cục:

~~~java
@Component
class GlobalErrorHandler {

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        Message<?> original = errorMessage.getOriginalMessage();

        // Ghi log có cấu trúc, phát metric hoặc định tuyến lỗi.
    }
}
~~~

Khi cần kiểm soát cách phân phối, có thể định nghĩa bean errorChannel riêng, chẳng hạn PublishSubscribeChannel để nhiều subscriber nhận cùng lỗi hoặc QueueChannel để tách thời điểm phát và tiêu thụ lỗi. Chọn loại channel theo yêu cầu về đồng bộ, buffering và back-pressure.

Từ Spring Integration 5.4.3, global errorChannel mặc định được cấu hình requireSubscribers=true. Vì vậy, khi không còn subscriber để nhận ErrorMessage, việc dispatch có thể phát sinh MessageDispatchingException. Điều này giúp phát hiện lỗi không có consumer thay vì âm thầm bỏ qua. Nếu thay thế channel mặc định hoặc dừng ứng dụng, hãy kiểm tra subscriber và hành vi khi endpoint ngừng hoạt động.

## Error flow và transaction của nguồn

Error channel chỉ định nơi xử lý exception dưới dạng message. Việc error flow kết thúc bình thường thường có nghĩa lỗi đã được xử lý ở tầng messaging; nó không tự động yêu cầu broker gửi lại message.

Với nguồn hỗ trợ transaction hoặc acknowledgement, cần quyết định rõ hành vi sau khi lỗi được chuyển sang error channel:

- Nếu error flow ghi nhận lỗi và kết thúc bình thường, adapter/container có thể xem callback đã xử lý xong. Với nguồn có transaction, transaction có thể commit và message không được phát lại.
- Nếu muốn rollback hoặc yêu cầu redelivery, error flow có thể cần ném lại exception để lỗi truyền về listener container. Cách làm chính xác phụ thuộc transport, transaction manager và acknowledgement mode.
- Nếu lỗi là dữ liệu độc hại hoặc không thể sửa bằng retry, hãy chuyển message đến dead-letter queue hoặc kho lỗi có khả năng tra cứu để tránh lặp vô hạn.
- Nếu lỗi tạm thời, dùng retry có giới hạn, backoff và chính sách phục hồi. Error channel tự nó không thực hiện retry.

Với JMS message-driven adapter, tài liệu Spring Integration nêu rõ rằng khi lỗi chuyển đổi được đưa vào error channel, muốn rollback transaction thì error flow phải ném lại exception (hoặc exception khác). Nếu error flow kết thúc bình thường, transaction có thể commit và message được loại khỏi nguồn. Hãy xác minh chính sách container thực tế trước khi dựa vào hành vi redelivery.

## Thiết kế consumer cho lỗi

Một error handler tốt cần giữ được ngữ cảnh, tránh làm lỗi thứ cấp che mất lỗi gốc và có hành động cuối cùng rõ ràng.

1. Lấy exception từ payload của ErrorMessage và xác định originalMessage nếu có.
2. Ghi nhận mã correlation, message ID, nguồn, endpoint và loại exception. Không log dữ liệu nhạy cảm.
3. Phân loại lỗi tạm thời và lỗi không thể phục hồi. Chỉ retry nhóm lỗi có khả năng thành công ở lần sau.
4. Giới hạn số lần retry, dùng backoff và bảo đảm thao tác xử lý có tính idempotent để tránh tác dụng phụ lặp lại.
5. Với lỗi không thể phục hồi, lưu message cùng thông tin exception vào nơi có thể tra cứu hoặc chuyển sang dead-letter flow.
6. Quyết định có cần ném lại exception để yêu cầu nguồn rollback/redelivery hay không; quyết định này phải khớp với transaction và acknowledgement của transport.

Đừng chỉ log rồi trả về nếu hệ thống cần bảo đảm không mất dữ liệu. Cũng đừng ném lại mọi lỗi một cách vô điều kiện: lỗi dữ liệu cố định có thể khiến broker phát lại cùng message mãi mãi.

## Chẩn đoán khi ErrorMessage không đến nơi

| Triệu chứng | Điểm cần kiểm tra |
|---|---|
| Exception xuất hiện ở log của broker/container | Producer đã cấu hình errorChannel chưa; adapter có đang truyền exception về source không |
| Lỗi bất đồng bộ chỉ xuất hiện ở global errorChannel | Message có header MessageHeaders.ERROR_CHANNEL không; header có trỏ đúng channel không |
| Lỗi từ DirectChannel đi ngược về sender | Đây có thể là hành vi đồng bộ bình thường; kiểm tra endpoint producer có errorChannel riêng không |
| ErrorMessage được phát nhưng không có consumer | Tên bean, subscriber của channel và vòng đời endpoint |
| Message nguồn không được redeliver | Error flow có kết thúc bình thường không; transaction manager và acknowledgement mode đang dùng là gì |
| Không thấy originalMessage | Lỗi xảy ra trước khi message được tạo đầy đủ hay ErrorMessageStrategy có giữ request message không |
| Lỗi xuất hiện lặp lại | Retry ở adapter, container hoặc broker; giới hạn retry và dead-letter policy |

Khi quan sát runtime, nên theo dõi số ErrorMessage theo producer và loại exception, tốc độ tiêu thụ error channel, số lần retry, số message chuyển vào dead-letter flow và thời gian tồn tại của lỗi chưa xử lý. Nếu error channel là QueueChannel, theo dõi cả độ sâu hàng đợi để phát hiện error handler không theo kịp tốc độ phát lỗi.

## Chọn cơ chế theo nguồn phát

| Tình huống | Cấu hình nên xem xét |
|---|---|
| Message-driven inbound adapter cần nhánh xử lý lỗi riêng | Thuộc tính errorChannel của producer endpoint |
| Nhiều flow bất đồng bộ cần nơi nhận lỗi mặc định | Global errorChannel |
| Mỗi message cần định tuyến lỗi đến một nơi khác nhau | Header MessageHeaders.ERROR_CHANNEL |
| Inbound adapter đọc source theo lịch | errorChannel trên poller |
| Cần broker redelivery khi xử lý thất bại | Transaction/acknowledgement và việc truyền exception về source |
| Cần lưu lỗi để xử lý thủ công | Error flow đến kho lỗi hoặc dead-letter channel |

Hãy cấu hình error channel theo đúng nơi exception được phát sinh, giữ lại thông tin message để truy vết và thiết kế rõ quyết định commit, rollback, retry hoặc dead-letter. Khi hiểu ranh giới giữa producer endpoint, task bất đồng bộ và poller, việc chẩn đoán lỗi trong Spring Integration Runtime sẽ chính xác hơn.

## Tài liệu tham khảo

- [Spring Integration - Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration - JMS Support](https://docs.spring.io/spring-integration/reference/jms.html)
- [MessageProducerSupport API](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/MessageProducerSupport.html)
