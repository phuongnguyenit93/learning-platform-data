# Thực nghiệm interceptor, chuyển đổi payload và lỗi thời gian chạy

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định interceptor chạy ở thời điểm nào trong vòng đời gửi và nhận message.
- Phân biệt ChannelInterceptor với ExecutorChannelInterceptor.
- Dùng MessageConverter và codec để chuyển payload giữa object, JSON, chuỗi và byte.
- Cấu hình chuyển đổi payload cho STOMP/WebSocket và RSocket.
- Phân loại lỗi lúc gửi, chuyển đổi, định tuyến và xử lý message.
- Viết unit test và integration test để tái hiện lỗi thời gian chạy, xác nhận kết quả và tránh làm hỏng connection không liên quan.

## 1. Nhìn message pipeline như các ranh giới có thể quan sát

Một message trong Spring Messaging thường đi qua chuỗi bước:

1. Producer tạo payload và metadata.
2. MessageChannel nhận message.
3. Interceptor có thể kiểm tra, bổ sung header, ghi nhận thời gian hoặc từ chối message.
4. Adapter/transport chuyển message thành frame hoặc dữ liệu trên wire.
5. Phía nhận giải mã và chuyển payload về kiểu dữ liệu mà handler yêu cầu.
6. Message được định tuyến đến handler.
7. Handler thực hiện nghiệp vụ và trả kết quả hoặc phát lỗi.

Một lỗi có thể xuất hiện ở bất kỳ bước nào. Ví dụ:

- Producer gửi message nhưng channel từ chối.
- Interceptor phát hiện header bắt buộc bị thiếu.
- Payload không thể chuyển từ JSON sang DTO.
- Route không có handler tương ứng.
- Handler ném exception khi truy cập database.
- Transport đóng khi response đang được gửi.

Khi thực nghiệm, hãy quan sát từng ranh giới. Nếu chỉ nhìn exception cuối cùng, bạn có thể nhầm lỗi chuyển đổi payload với lỗi nghiệp vụ hoặc lỗi transport.

## 2. ChannelInterceptor: quan sát và điều chỉnh message trên channel

ChannelInterceptor là hook ở tầng MessageChannel. Nó cho phép quan sát hoặc điều chỉnh message khi channel gửi/nhận dữ liệu. Những phương thức thường dùng:

| Callback | Thời điểm | Mục đích |
| --- | --- | --- |
| preSend | Trước khi channel gửi message | Kiểm tra, bổ sung header, thay message hoặc từ chối |
| postSend | Sau khi channel thực hiện send | Ghi nhận kết quả gửi thành công hay thất bại |
| afterSendCompletion | Sau khi toàn bộ quá trình send kết thúc | Cleanup và ghi nhận exception nếu có |
| preReceive | Trước khi polling channel nhận message | Cho phép hoặc ngăn lần receive |
| postReceive | Sau khi receive có message | Quan sát hoặc thay đổi message vừa nhận |
| afterReceiveCompletion | Sau khi quá trình receive kết thúc | Cleanup sau receive |

Ví dụ interceptor ghi nhận loại message và bổ sung một header nội bộ:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class AuditChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        Object contentType = message.getHeaders()
                .get("contentType");

        return MessageBuilder.fromMessage(message)
                .setHeader("audit.channel", channel.toString())
                .setHeader("audit.hasContentType", contentType != null)
                .build();
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {
        System.out.println("sent=" + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {

        if (ex != null) {
            System.err.println("send failed: " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Các điểm cần nhớ:

- **preSend** có thể trả về một Message mới để thay message sắp gửi.
- Trả về **null** có nghĩa là dừng việc gửi message đó. Đây là hành vi có chủ đích, vì vậy đừng trả null do một lỗi lập trình không được xử lý.
- MessageHeaders là immutable. Dùng MessageBuilder.fromMessage(...) để tạo message mới thay vì sửa trực tiếp map header.
- **postSend** cho biết kết quả của lần gửi ở channel; nó không chứng minh consumer đã hoàn tất nghiệp vụ hoặc dữ liệu đã commit.
- **afterSendCompletion** phù hợp để cleanup và ghi nhận lỗi của quá trình send. Không dùng callback này để thực hiện side effect nghiệp vụ lần nữa.

### Đăng ký interceptor

Với channel hỗ trợ InterceptableChannel, có thể đăng ký interceptor qua API addInterceptor. Ví dụ dưới đây dùng DirectChannel của Spring Integration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
class ChannelConfiguration {

    @Bean
    MessageChannel ordersChannel(AuditChannelInterceptor interceptor) {
        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(interceptor);
        return channel;
    }
}
~~~

Nếu ứng dụng dùng channel do framework hoặc adapter tạo, hãy cấu hình interceptor tại abstraction được hỗ trợ thay vì thay thế channel đang được container quản lý.

### Interceptor cho xử lý bất đồng bộ

ChannelInterceptor quan sát hoạt động của channel. Với channel dispatch đến subscriber qua executor, **ExecutorChannelInterceptor** cung cấp thêm callback quanh việc gọi handler:

- **beforeHandle:** chạy ngay trước khi handler nhận message trên thread thực thi.
- **afterMessageHandled:** chạy sau khi handler hoàn tất hoặc ném exception.

Đây là vị trí phù hợp để đo thời gian xử lý handler hoặc gắn context cho phần thực thi. Không nên dùng nó thay thế việc truyền trace context đúng cách qua executor; context propagation cần được cấu hình riêng.

Không chặn event loop hoặc thread gửi message bằng công việc blocking trong interceptor. Interceptor nằm trên đường đi của message, vì vậy một thao tác chậm trong đó có thể làm tăng latency cho nhiều request.

## 3. Thực nghiệm interceptor: kiểm tra, bổ sung và từ chối

Một interceptor thường có ba nhiệm vụ kỹ thuật:

1. Kiểm tra metadata cần thiết, ví dụ correlation ID hoặc content type.
2. Bổ sung metadata phục vụ quan sát, ví dụ timestamp tiếp nhận hoặc tên logical channel.
3. Từ chối message không đáp ứng điều kiện ở tầng channel nếu đó là chính sách kỹ thuật của channel.

Ví dụ interceptor yêu cầu correlation ID:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public class CorrelationIdInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        Object correlationId =
                message.getHeaders().get("correlationId");

        if (correlationId == null ||
                correlationId.toString().isBlank()) {
            throw new IllegalArgumentException(
                    "Missing correlationId");
        }

        return message;
    }
}
~~~

Trong ứng dụng thực tế, hãy quyết định rõ thiếu correlation ID sẽ bị từ chối, được sinh mới hay được chuyển thành một lỗi có cấu trúc. Nếu interceptor ném exception, producer có thể nhận lỗi ngay trong thao tác send tùy loại channel và cách dispatch. Với xử lý bất đồng bộ, lỗi phát sinh ở thread consumer có thể đi theo error handling path khác.

Không đưa toàn bộ validation nghiệp vụ vào interceptor. Ví dụ kiểm tra số lượng đặt hàng, quyền truy cập hoặc trạng thái đơn hàng nên nằm ở handler/domain service, nơi có đủ context và có thể trả lỗi nghiệp vụ rõ ràng.

## 4. MessageConverter: chuyển đổi payload và content type

Spring Messaging tách payload khỏi metadata. **MessageConverter** chuyển đổi payload giữa object Java và dạng dữ liệu phù hợp với message/transport.

Các converter thường gặp:

- **StringMessageConverter:** chuyển payload dạng String.
- **ByteArrayMessageConverter:** làm việc với byte[].
- **MappingJackson2MessageConverter:** chuyển object và JSON khi ứng dụng dùng Jackson 2.
- **CompositeMessageConverter:** thử một danh sách converter theo cấu hình.

Việc chọn converter thường dựa trên content type và kiểu payload/kiểu đích. Ví dụ:

| Content type | Payload wire | Kiểu Java mong muốn |
| --- | --- | --- |
| text/plain | Chuỗi UTF-8 | String |
| application/json | JSON | DTO/record |
| application/octet-stream | Bytes | byte[] |
| application/cbor | CBOR | DTO nếu có codec phù hợp |

Content type không chỉ là nhãn trang trí. Nếu producer gửi JSON nhưng khai báo text/plain, converter có thể chọn sai cách giải mã. Nếu consumer yêu cầu một DTO nhưng không có converter phù hợp, message có thể thất bại trước khi handler chạy.

### Thử round-trip với JSON converter

Ví dụ sau minh họa chuyển DTO thành message JSON và giải mã lại. Mẫu dùng MappingJackson2MessageConverter trong ứng dụng đang sử dụng Jackson 2; với phiên bản Spring/Jackson khác, chọn converter tương thích mà dự án đang quản lý.

~~~java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.util.MimeTypeUtils;

public class PayloadConversionDemo {

    record CreateOrder(String customerId, int quantity) {}

    public static void main(String[] args) {
        MappingJackson2MessageConverter converter =
                new MappingJackson2MessageConverter();

        CreateOrder input = new CreateOrder("C-17", 2);

        MessageHeaders headers = new MessageHeaders(Map.of(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON));

        Message<?> message = converter.toMessage(input, headers);

        CreateOrder output = (CreateOrder) converter.fromMessage(
                message, CreateOrder.class);

        if (!input.equals(output)) {
            throw new AssertionError("JSON round-trip failed");
        }

        System.out.println("contentType=" +
                message.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("payloadType=" +
                message.getPayload().getClass().getSimpleName());
        System.out.println("order=" + output);
    }
}
~~~

Kết quả minh họa:

~~~text
contentType=application/json
payloadType=byte[]
order=CreateOrder[customerId=C-17, quantity=2]
~~~

Kiểu payload trung gian phụ thuộc converter và cấu hình. Với MappingJackson2MessageConverter, dữ liệu JSON được biểu diễn thành byte[] trong message ở ví dụ này; handler nhận message ở phía khác sẽ được converter giải mã về kiểu đích.

Nếu test trong dự án, hãy dùng cùng phiên bản Jackson và cấu hình ObjectMapper như ứng dụng thật. Các cấu hình date/time, naming strategy, polymorphic type và module tùy chỉnh có thể làm kết quả khác nhau.

## 5. Chuyển đổi payload trong STOMP/WebSocket

Với STOMP, frame có command, native headers và body. Spring chuyển body thành đối số của phương thức @MessageMapping thông qua các MessageConverter được cấu hình.

Ví dụ handler nhận DTO:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
class OrderMessageController {

    @MessageMapping("/orders.create")
    public OrderResult create(@Payload CreateOrder command) {
        return new OrderResult("accepted", command.customerId());
    }
}
~~~

Khi client gửi JSON, frame cần khai báo content type phù hợp, thường là application/json. Spring dùng converter tương ứng để tạo CreateOrder trước khi gọi handler. Nếu chuyển đổi thất bại, handler có thể chưa được thực thi.

Cấu hình converter tùy chỉnh trong WebSocketMessageBrokerConfigurer:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.converter.MessageConverter;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompMessageConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public boolean configureMessageConverters(
            List<MessageConverter> converters) {

        converters.add(new MappingJackson2MessageConverter());

        // false: cho phép Spring đăng ký thêm các converter mặc định.
        return false;
    }
}
~~~

Nếu chỉ muốn dùng đúng các converter tự khai báo, trả về true và bảo đảm danh sách đã có đủ converter cần thiết cho String, byte[] và JSON. Trong ứng dụng Spring Boot, hãy kiểm tra cấu hình auto-configuration trước khi đăng ký thêm converter để tránh duplicate hoặc thay đổi hành vi mặc định ngoài ý muốn.

Khi test STOMP, kiểm tra cả:
- Header content type trên frame.
- Payload JSON thực tế.
- DTO mà handler nhận được.
- Kết quả trả về hoặc ERROR frame khi JSON sai.

Không chỉ test gọi trực tiếp controller với DTO, vì cách đó bỏ qua bước giải mã mà bài thực nghiệm cần kiểm tra.

## 6. Chuyển đổi payload trong RSocket

RSocket tách data và metadata. Spring dùng **RSocketStrategies** để cấu hình encoder/decoder và các thành phần chuyển đổi. Data MIME type giúp hai đầu thống nhất cách diễn giải payload.

Ví dụ cấu hình strategies với Jackson 2 codec khi ứng dụng cần bổ sung codec tương ứng:

~~~java
import org.springframework.core.codec.Decoder;
import org.springframework.core.codec.Encoder;
import org.springframework.core.codec.Jackson2JsonDecoder;
import org.springframework.core.codec.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();
~~~

Nếu strategies mặc định đã có JSON codec phù hợp, không thêm bản sao. Khi cấu hình codec tùy chỉnh, hãy xác nhận thứ tự codec và MIME type tương ứng.

Có thể dùng strategies và JSON MIME type khi tạo requester:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
~~~

Phía server cũng cần cấu hình RSocketStrategies tương thích. Hai đầu phải thống nhất data MIME type, codec và kiểu dữ liệu. Nếu client gửi CBOR trong khi server giải mã JSON, lỗi xảy ra trước khi handler xử lý payload.

Đừng nhầm data MIME type với route metadata. Route cho biết message được định tuyến đến handler nào; data MIME type cho biết cách giải mã phần data. Metadata có thể chứa route và các thông tin giao thức khác.

## 7. Lỗi thời gian chạy: phân loại trước khi xử lý

Một số lỗi thường gặp trong message pipeline:

| Nhóm | Ví dụ | Nơi thường phát hiện |
| --- | --- | --- |
| Gửi/dispatch | Channel không gửi được, subscriber không còn hoạt động | Producer/channel |
| Interceptor | Header thiếu hoặc policy từ chối message | preSend/beforeHandle |
| Chuyển đổi | JSON sai cú pháp, content type không hỗ trợ, DTO không tương thích | MessageConverter/codec |
| Định tuyến | Không có handler cho destination/route | Dispatcher |
| Validation | Field thiếu, sai miền giá trị | Handler/validation layer |
| Nghiệp vụ | Database lỗi, trạng thái không hợp lệ | Service/domain |
| Transport | Socket đóng, timeout, peer reset | Transport/client |
| Quá tải | Executor đầy, buffer overflow, request vượt giới hạn | Channel/executor/runtime |

Các exception quan trọng trong Spring Messaging gồm:

- **MessageConversionException:** payload không thể chuyển đổi theo converter.
- **MessageDeliveryException:** lỗi trong quá trình gửi message đến channel/consumer.
- **MessageHandlingException:** lỗi khi xử lý message tại handler.
- **MessagingException:** lớp cơ sở mang thông tin lỗi messaging; trong nhiều trường hợp có thể truy cập failedMessage.

Không bắt mọi exception rồi trả về một response thành công. Hãy giữ nguyên phân loại lỗi và chuyển nó thành kết quả phù hợp với giao thức.

## 8. Xử lý lỗi ở các tầng Spring Messaging

### Lỗi trong @MessageMapping

Với controller messaging, có thể dùng @MessageExceptionHandler để ánh xạ exception từ handler sang response lỗi có cấu trúc:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
class OrderErrorController {

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendTo("/topic/order-errors")
    public ErrorResponse handleInvalidMessage(
            IllegalArgumentException error) {

        return new ErrorResponse(
                "INVALID_MESSAGE",
                "Thông điệp không hợp lệ");
    }
}
~~~

Đây là mẫu minh họa cho messaging controller; destination và cách gửi lỗi cụ thể cần phù hợp với STOMP hoặc RSocket endpoint đang dùng. Không trả stack trace, SQL, hostname nội bộ hoặc dữ liệu nhạy cảm cho client.

### Lỗi trong Spring Integration flow

Nếu ứng dụng dùng Spring Integration, message flow có thể gửi lỗi vào error channel. ErrorMessage mang Throwable và có thể mang failed message thông qua MessagingException. Có thể đăng ký handler cho error channel để ghi nhận, phân loại hoặc chuyển lỗi đến nơi xử lý phù hợp.

Không giả định mọi Spring MessageChannel thuần đều tự động có error channel. Error channel là một phần của cơ chế messaging flow trong Spring Integration và cần được cấu hình theo kiến trúc đó.

### Lỗi trong RSocket/Reactor

Với RSocket controller trả về Mono hoặc Flux, lỗi có thể được phát như terminal signal của publisher. Có thể dùng onErrorMap để ánh xạ exception nội bộ sang exception giao thức/ứng dụng phù hợp, hoặc xử lý tại exception handler được hỗ trợ bởi controller infrastructure.

Không dùng onErrorResume để biến mọi lỗi thành empty publisher. Làm vậy có thể khiến client tưởng request thành công nhưng không có dữ liệu. Nếu nghiệp vụ có kết quả rỗng hợp lệ, hãy phân biệt rõ với lỗi.

### Lỗi transport

Khi transport bị đóng, request đang chờ có thể kết thúc bằng lỗi. Đây không phải lỗi chuyển đổi payload. Xử lý reconnect hoặc retry ở tầng client với giới hạn và backoff; không retry vô hạn trong interceptor hoặc handler. Với operation có side effect, cần idempotency để tránh thực hiện lặp nếu response bị mất sau khi server đã commit.

## 9. Thực nghiệm end-to-end

Có thể thực hiện lab theo các bước sau:

1. Tạo channel và đăng ký AuditChannelInterceptor.
2. Gửi một message có correlation ID và content type hợp lệ.
3. Xác nhận interceptor nhìn thấy message, header bổ sung xuất hiện và handler nhận đúng payload.
4. Gửi message thiếu correlation ID; xác nhận message bị từ chối theo policy.
5. Gửi JSON hợp lệ với content type application/json; xác nhận DTO được tạo đúng.
6. Gửi JSON sai cú pháp hoặc content type không được hỗ trợ; xác nhận lỗi conversion và handler không chạy.
7. Gửi message có route không tồn tại; xác nhận lỗi routing riêng với lỗi conversion.
8. Cho handler ném exception nghiệp vụ; xác nhận error mapping trả lỗi an toàn.
9. Đóng transport trong khi request đang chờ; xác nhận lỗi connection được quan sát riêng.
10. Gửi lại một request hợp lệ sau lỗi; xác nhận hệ thống vẫn tiếp tục hoạt động.

Với mỗi bước, ghi lại:
- Input headers và content type.
- Kiểu payload trước và sau conversion.
- Interceptor callback nào đã chạy.
- Handler có được gọi hay không.
- Exception class và tầng phát sinh.
- Response/error signal quan sát được.
- Connection có còn hoạt động sau lỗi hay không.

## 10. Kiểm thử tự động

### Unit test cho interceptor

Có thể gọi trực tiếp preSend để xác nhận header được thêm và message không bị thay payload:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class AuditChannelInterceptorTest {

    @Test
    void addsAuditHeadersWithoutChangingPayload() {
        AuditChannelInterceptor interceptor =
                new AuditChannelInterceptor();

        Message<String> input = MessageBuilder
                .withPayload("order-created")
                .setHeader("contentType", "application/json")
                .build();

        Message<?> output = interceptor.preSend(input, message -> true);

        assertNotNull(output);
        assertEquals("order-created", output.getPayload());
        assertEquals(
                true,
                output.getHeaders().get("audit.hasContentType"));
    }
}
~~~

Unit test này kiểm tra logic của interceptor. Nó không chứng minh interceptor đã được đăng ký vào channel thực tế hoặc được gọi trong transport.

### Unit test cho conversion

Dùng converter thực tế để kiểm tra round-trip DTO/JSON. Bổ sung test cho:
- Content type không tương thích.
- JSON sai cú pháp.
- Field thiếu hoặc sai kiểu.
- DTO có generic/nested object.
- Date/time và custom serializer nếu ứng dụng dùng.
- Payload byte[] lớn hơn giới hạn cấu hình.

Assert cả exception type và việc handler/service không bị gọi nếu conversion thất bại.

### Integration test cho STOMP/RSocket

Khởi động endpoint thật trên cổng ngẫu nhiên và dùng client test của giao thức. Gửi frame/message qua network để kiểm tra serialization, header mapping, routing và error path. Test trực tiếp method controller không thay thế được integration test này.

Với RSocket, dùng StepVerifier để kiểm tra terminal signal và timeout hữu hạn. Với STOMP, xác nhận native header, content type, response destination và hành vi đóng session khi protocol error xảy ra.

Không dùng Thread.sleep để chờ message. Dùng latch, Awaitility hoặc StepVerifier với timeout để test ổn định trong CI.

## 11. Chẩn đoán lỗi trong production

Khi message thất bại, thu thập đủ thông tin để xác định ranh giới:

- Message ID hoặc correlation ID đã được xác thực/chuẩn hóa.
- Destination/route hoặc tên channel.
- Content type và kiểu payload, không nhất thiết log toàn bộ payload.
- Tên interceptor và callback đã chạy.
- Exception class, cause chain và failed message metadata nếu an toàn.
- Trace ID/span ID nếu tracing đã được cấu hình.
- Thời điểm gửi, thời điểm handler bắt đầu và kết thúc.
- Số task đang chạy, queue depth và trạng thái connection.

Tránh log raw payload, access token, session cookie, dữ liệu cá nhân hoặc toàn bộ header chưa lọc. Dùng allowlist cho các header được phép ghi log.

Metric nên có cardinality thấp: channel, operation, converter type, error category. Không dùng message ID, customer ID hoặc trace ID làm metric tag.

Một dashboard hữu ích có thể theo dõi:
- Tỷ lệ send thất bại.
- Tỷ lệ conversion error.
- Tỷ lệ handler error.
- Message processing latency.
- Executor queue depth và rejected task count.
- Connection close/reset count.
- Số message retry/redelivery.

## 12. Lỗi thực nghiệm thường gặp

- **Nhầm postSend với xử lý nghiệp vụ hoàn tất:** postSend chỉ phản ánh kết quả gửi ở channel.
- **Sửa MessageHeaders trực tiếp:** header bất biến; tạo message mới bằng MessageBuilder.
- **Dùng interceptor làm nơi chứa toàn bộ business validation:** làm logic khó kiểm thử và khó phân biệt lỗi kỹ thuật với lỗi nghiệp vụ.
- **Quên content type:** converter có thể không chọn đúng cách giải mã.
- **Chỉ test converter bằng object có sẵn:** bỏ qua serialization bytes và header trên wire.
- **Đăng ký converter tùy chỉnh nhưng loại bỏ converter mặc định:** String hoặc byte[] có thể không còn hoạt động.
- **Thêm codec trùng vào RSocketStrategies:** có thể tạo lựa chọn không mong muốn hoặc thứ tự giải mã khó đoán.
- **Nuốt exception bằng empty publisher:** client không phân biệt kết quả rỗng với lỗi.
- **Retry trong interceptor:** dễ tạo vòng lặp, duplicate side effect và tăng tải.
- **Log payload đầy đủ:** có nguy cơ lộ dữ liệu và làm log phình to.
- **Dùng mock để kết luận transport đúng:** chỉ integration test qua network mới kiểm tra được framing, serialization và connection lifecycle.

## 13. Checklist hoàn thành

- [ ] Đã xác định rõ thứ tự interceptor và phạm vi callback của channel.
- [ ] Đã phân biệt ChannelInterceptor và ExecutorChannelInterceptor.
- [ ] Đã xác nhận preSend có thể thay message hoặc từ chối message.
- [ ] MessageHeaders được tạo mới thay vì sửa trực tiếp.
- [ ] Converter được chọn theo content type và kiểu đích.
- [ ] Đã kiểm tra JSON hợp lệ, JSON sai và content type không hỗ trợ.
- [ ] STOMP native headers và body được kiểm tra trên frame thực.
- [ ] RSocket data MIME type và codec hai đầu tương thích.
- [ ] Lỗi conversion, routing, handler và transport được phân loại riêng.
- [ ] Exception được ánh xạ thành response an toàn, không lộ nội bộ.
- [ ] Unit test và integration test đều có timeout hữu hạn.
- [ ] Log/metric đủ chẩn đoán nhưng không chứa payload nhạy cảm hoặc high-cardinality tag.

## Tài liệu tham khảo

- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Framework API — ChannelInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Framework API — MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketStrategies](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
