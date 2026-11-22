# Chẩn đoán không nhận được thông điệp theo từng chặng

Khi một message “không đến nơi”, câu hỏi đầu tiên là: không đến nơi nào? Producer có thể đã tạo message nhưng chưa gửi; transport có thể đã nhận request nhưng chưa chuyển tới handler; handler có thể đã chạy nhưng chưa phát kết quả; reply có thể đã tới client nhưng bị decode, filter hoặc cancellation loại bỏ. Cụm từ “không nhận được” chỉ mô tả triệu chứng ở một điểm quan sát, không xác định được tầng gây lỗi.

Cách chẩn đoán hiệu quả là chia luồng messaging thành các chặng có tên, ghi nhận bằng chứng ở ranh giới mỗi chặng và dùng cùng một correlation ID để nối các sự kiện. Khi biết sự kiện cuối cùng đã xuất hiện ở đâu, ta có thể thu hẹp lỗi vào đoạn kế tiếp mà không phải bật log toàn bộ payload hoặc suy đoán từ một timeout.

Bài học tập trung vào Spring Messaging và RSocket, đồng thời chỉ ra cách áp dụng cùng tư duy cho Spring Integration channel.

## 1. Vẽ đường đi của một message

Một luồng RSocket request/response điển hình có các chặng sau:

~~~text
Producer / API caller
       |
       v
Tạo request + correlation ID
       |
       v
RSocketRequester: route + encode + subscribe
       |
       v
Connection / transport / RSocket protocol
       |
       v
RSocketMessageHandler: decode + route mapping
       |
       v
@MessageMapping handler
       |
       v
Business service / downstream channel
       |
       v
Handler tạo Mono/Flux response
       |
       v
Encode + transport trả response
       |
       v
RSocketRequester decode + caller consume
~~~

Với Spring Integration, giữa handler và business service có thể có thêm MessageChannel, router, filter, transformer, splitter, aggregator hoặc outbound adapter. Mỗi channel và endpoint là một ranh giới cần quan sát riêng. Không gom tất cả thành một bước “Spring đã nhận message”.

Trước khi điều tra, ghi rõ:

- Message được tạo ở đâu và ai là producer?
- “Đã gửi” được xác định bằng sự kiện nào?
- Thành phần nào được kỳ vọng nhận message tiếp theo?
- Message có phải request/response, stream, fire-and-forget hay channel?
- Bằng chứng nào chứng minh một chặng đã hoàn thành?

Một lệnh send hoàn tất, một publisher được subscribe, một transport nhận frame và một business handler commit dữ liệu là bốn sự kiện khác nhau. Không dùng chúng thay thế cho nhau.

## 2. Gắn định danh xuyên suốt

Mỗi thao tác nghiệp vụ nên có một correlation ID ổn định qua các chặng. Với mỗi lần retry, có thể bổ sung attempt number hoặc request ID riêng để phân biệt lần gửi. Message ID định danh một instance message; nó có thể thay đổi khi framework tạo message mới, vì vậy không dùng nó làm correlation key xuyên suốt.

Trong Spring Integration, IntegrationMessageHeaderAccessor.CORRELATION_ID liên kết các message trong cùng một nhóm; SEQUENCE_NUMBER và SEQUENCE_SIZE hỗ trợ splitter/aggregator. Trong RSocket, correlation ID có thể nằm trong payload envelope hoặc metadata ứng dụng đã được cấu hình ở cả hai phía. Đừng giả định metadata tự động được chuyển thành một header Spring nếu chưa cấu hình MetadataExtractor.

Một log sự kiện nên có các trường:

| Trường | Mục đích |
|---|---|
| timestamp | So sánh thứ tự sự kiện; dùng đồng bộ thời gian giữa các host |
| event | Tên chặng: created, send, accepted, handler-start, reply, consumed... |
| correlationId | Nối các log của cùng một thao tác |
| messageId | Định danh instance message tại chặng hiện tại |
| route / destination | Xác định endpoint đích |
| interaction | Request-Response, Request-Stream, Fire-and-Forget hoặc Request-Channel |
| node / service | Xác định instance xử lý |
| attempt | Phân biệt retry |
| payloadType / size | Kiểm tra codec và kích thước mà không log nội dung nhạy cảm |
| outcome / error | Ghi nhận thành công, timeout, cancel hoặc lỗi |
| durationMs | Đo thời gian xử lý tại chặng |

Correlation ID nên nằm trong log hoặc trace, không nên làm tag metric vì mỗi request có thể tạo một giá trị riêng và khiến cardinality tăng không giới hạn. Metric chỉ nên dùng các chiều có tập giá trị nhỏ như route, interaction, outcome và service.

Không ghi toàn bộ payload, token, dữ liệu cá nhân hoặc thông tin bí mật vào log. Nếu cần đối chiếu payload, ghi loại dữ liệu, kích thước hoặc một digest có chính sách bảo mật rõ ràng.

## 3. Chẩn đoán theo sự kiện cuối cùng đã nhìn thấy

Dùng bảng này như một decision tree. Bắt đầu từ producer, tìm sự kiện cuối cùng có cùng correlation ID, rồi kiểm tra chặng ngay sau nó.

| Bằng chứng cuối cùng | Chặng cần kiểm tra tiếp | Nguyên nhân thường gặp |
|---|---|---|
| Không có event created | Producer / trigger | Trigger không chạy, validation dừng, transaction rollback trước khi publish |
| Có created nhưng không có send | Outbound publisher | Filter loại message, branch không được subscribe, code return publisher nhưng không subscribe |
| Có send nhưng không có transport/connection evidence | Client connection và transport | Chưa kết nối, setup lỗi, connection đóng, DNS/TLS/network hoặc sai địa chỉ |
| Có connection nhưng không có handler entry | Route và responder mapping | Sai route, route metadata không được encode, sai interaction model, responder không đăng ký |
| Có handler entry nhưng không có processing-start | Handler/reactive pipeline | Publisher không được subscribe, điều kiện rẽ nhánh, lỗi đồng bộ trước khi gọi service |
| Có processing-start nhưng không có processing-complete | Business service/downstream | Call treo, queue đầy, dependency chậm, exception, deadlock hoặc cancellation |
| Có processing-complete nhưng không có reply | Handler output/encoding | Handler trả Mono.empty/Mono<Void>, lỗi khi encode, response type không phù hợp |
| Có reply ở server nhưng client không thấy | Response transport/client decode | Connection đã đóng, codec/MIME type sai, response bị cancel hoặc client timeout |
| Client nhận reply nhưng caller không thấy | Consumer cuối | Filter/drop, mapping lỗi, subscriber đã cancel, kết quả không được lưu hoặc hiển thị |

Không có log ở một chặng chưa đủ chứng minh chặng đó không chạy: log có thể bị sampling, bị filter, mất do collector hoặc chưa flush. Hãy đối chiếu thêm metric, trace, queue depth, broker offset và một test tái hiện nhỏ.

## 4. Phân biệt send, delivery và business completion

Các hệ thống messaging thường có nhiều mức xác nhận:

- Created: ứng dụng đã tạo message.
- Published/sent: publisher đã gọi API gửi hoặc publisher hoàn tất theo hợp đồng của nó.
- Accepted: broker/transport xác nhận nhận dữ liệu theo giao thức.
- Delivered: consumer đã nhận message.
- Processed: handler đã thực thi xong logic.
- Committed: side effect đã được lưu bền vững.
- Replied/acknowledged: response hoặc acknowledgement đã được gửi.

RSocket Fire-and-Forget không cung cấp business response. Việc requester.send() hoàn tất không chứng minh handler đã commit. Nếu cần xác nhận xử lý nghiệp vụ, dùng Request-Response, một event completion riêng hoặc truy vấn trạng thái độc lập.

Với Spring Integration, MessageChannel.send() trả về khi channel chấp nhận message theo semantics của channel. Với ExecutorChannel, message có thể chỉ được đưa vào executor queue; handler chạy sau đó. Một send thành công không có nghĩa endpoint downstream đã hoàn tất. Hãy instrument cả channel boundary lẫn service/handler.

Với broker có acknowledgement, phân biệt delivery tag/offset và thời điểm ack. Consumer có thể đã nhận nhưng chưa commit; message có thể được redeliver. Thiết kế consumer idempotent và ghi nhận duplicate thay vì giả định mỗi message chỉ tới đúng một lần.

## 5. Instrument Spring Integration channel

ChannelInterceptor quan sát các MessageChannel mà nó được đăng ký. preSend chạy trước khi channel gửi message; postSend quan sát kết quả gửi; afterSendCompletion chạy sau khi send hoàn tất hoặc lỗi. Với channel bất đồng bộ, các callback này không thay thế log tại handler vì send có thể kết thúc trước khi consumer xử lý.

Ví dụ interceptor đơn giản dùng System.Logger:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public final class DiagnosticChannelInterceptor
        implements ChannelInterceptor {

    private static final System.Logger LOG =
            System.getLogger(DiagnosticChannelInterceptor.class.getName());

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        Object correlationId = message.getHeaders().get("correlationId");
        LOG.log(System.Logger.Level.INFO,
                "event=channel-pre-send channel=" + channel
                        + " correlationId=" + correlationId
                        + " messageId=" + message.getHeaders().getId());
        return message;
    }

    @Override
    public void postSend(
            Message<?> message, MessageChannel channel, boolean sent) {
        LOG.log(System.Logger.Level.INFO,
                "event=channel-post-send sent=" + sent
                        + " correlationId="
                        + message.getHeaders().get("correlationId"));
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {
        if (ex != null) {
            LOG.log(System.Logger.Level.ERROR,
                    "event=channel-send-error correlationId="
                            + message.getHeaders().get("correlationId"),
                    ex);
        }
    }
}
~~~

Đăng ký interceptor trên channel cần quan sát, ví dụ channel hỗ trợ ChannelInterceptor hoặc thông qua cấu hình channel của ứng dụng. Không đăng ký interceptor ở một channel rồi kết luận nó bao phủ mọi transport hoặc mọi channel khác.

Với Spring Integration, wireTap có thể chuyển bản sao message sang một channel chẩn đoán. MessageHistory có thể lưu dấu các component mà message đã đi qua khi tính năng history được bật. Đây là bằng chứng hữu ích cho tuyến xử lý nội bộ, nhưng không thay thế tracing giữa các process hoặc log tại broker/transport.

## 6. Instrument RSocket requester và handler

RSocketRequester trả về các publisher lazy. Nếu publisher không được subscribe, request không được gửi. Đặt hook trên publisher để quan sát lúc subscription, response, error và terminal signal:

~~~java
Mono<OrderReply> reply = requester.route("orders.lookup")
        .data(request)
        .retrieveMono(OrderReply.class)
        .doOnSubscribe(ignored -> log.info(
                "event=rsocket-client-send correlationId={}", correlationId))
        .doOnNext(value -> log.info(
                "event=rsocket-client-reply correlationId={}", correlationId))
        .doOnError(error -> log.error(
                "event=rsocket-client-error correlationId={}", correlationId, error))
        .doFinally(signal -> log.info(
                "event=rsocket-client-terminal correlationId={} signal={}",
                correlationId, signal));
~~~

doOnSubscribe chứng minh publisher đã được subscribe; nó không chứng minh server đã nhận request. doOnNext chứng minh client đã decode và nhận response. Nếu không có doOnNext, cần đối chiếu server-side log và connection/transport events.

Ở responder, ghi nhận lúc handler được gọi và lúc reactive pipeline thực sự subscribe/terminal:

~~~java
@MessageMapping("orders.lookup")
public Mono<OrderReply> lookup(@Payload OrderRequest request) {
    String correlationId = request.correlationId();
    log.info("event=rsocket-handler-invoked correlationId={}", correlationId);

    return Mono.defer(() -> {
        log.info("event=business-start correlationId={}", correlationId);
        return orderService.lookup(request.orderId())
                .doOnNext(value -> log.info(
                        "event=business-complete correlationId={}", correlationId))
                .doOnError(error -> log.error(
                        "event=business-error correlationId={}", correlationId, error))
                .doFinally(signal -> log.info(
                        "event=handler-terminal correlationId={} signal={}",
                        correlationId, signal));
    });
}
~~~

Ví dụ giả định OrderRequest có correlationId trong payload. Ứng dụng có thể truyền ID qua metadata thay thế, nhưng phải cấu hình MIME type và MetadataExtractor ở responder để lấy giá trị đúng. Không dùng ThreadLocal để truyền correlation qua Reactor pipeline nếu không bật cơ chế context propagation; các callback có thể chạy trên thread khác. Khi cần context, dùng Reactor Context hoặc Micrometer Observation/Tracing integration phù hợp với phiên bản ứng dụng.

## 7. Dùng metrics và tracing để thu hẹp vị trí lỗi

Log giúp xem một request cụ thể; metrics cho biết lỗi có phổ biến hay không; trace cho biết thời gian bị tiêu tốn ở đâu.

Metrics hữu ích:

- Số request gửi đi và số response nhận được theo route/interaction.
- Tỷ lệ error, timeout, cancellation và request không có response.
- Thời gian xử lý tại handler và downstream dependency.
- Queue depth, consumer lag, số message đang chờ và số retry.
- Số connection đang hoạt động, số connection setup/error.
- Kích thước MessageGroupStore hoặc số group đang chờ nếu dùng aggregator.

Không tự giả định tên metric giống nhau giữa mọi phiên bản Spring, RSocket transport và registry. Liệt kê metric đang được exporter công bố rồi xác định metric phù hợp với phiên bản triển khai. Dùng tag có cardinality thấp; correlation ID, user ID hoặc message ID không nên trở thành tag.

Tracing giúp nối các span qua service. Một trace hữu ích có span cho producer, outbound messaging, transport/server, handler và downstream dependency. Nếu trace dừng ở producer, kiểm tra context propagation và instrumentation của outbound client. Nếu server span không nối vào client span, kiểm tra propagation qua transport và cấu hình tracing. RSocket metadata chỉ mang trace context nếu client/server đã cấu hình tương ứng; không giả định mọi RSocket connection tự động truyền W3C trace headers.

Đồng bộ thời gian giữa host bằng NTP hoặc cơ chế tương đương. Khi so sánh duration trong cùng process, dùng đồng hồ monotonic như System.nanoTime() thay vì trừ hai wall-clock timestamp có thể bị điều chỉnh.

## 8. Kiểm tra route, codec và metadata

Khi server có connection nhưng không thấy handler entry, kiểm tra các điểm sau:

- Route trong requester có khớp chính xác với @MessageMapping không?
- Requester có gửi routing metadata và đúng composite metadata MIME type không?
- Data MIME type hai phía có tương thích không?
- Encoder/Decoder có hỗ trợ kiểu payload thực tế không?
- MetadataExtractor có đăng ký MIME type và chuyển metadata thành header mong muốn không?
- Interaction model có phù hợp với chữ ký handler không?
- Handler có được đăng ký trong RSocketMessageHandler hoặc Spring ApplicationContext không?

Test với String mặc định không chứng minh custom JSON/CBOR codec hoạt động. Gửi object thực tế, metadata thực tế và assert giá trị ở handler. Khi debug, log route, MIME type, payload class và metadata keys; tránh log token hoặc raw metadata có chứa bí mật.

## 9. Phân biệt lỗi do reactive lifecycle

Một lỗi thường gặp là tạo Mono/Flux nhưng không subscribe. Publisher của Reactor lazy: đoạn code trong map/defer chỉ chạy khi có subscription. Với RSocketRequester, việc tạo request publisher chưa có nghĩa request đã được gửi.

Các dấu hiệu cần phân biệt:

- Không có doOnSubscribe: publisher chưa được subscribe hoặc code không đi tới nhánh tạo publisher.
- Có doOnSubscribe nhưng không có response/error: request có thể đang chờ, server không phản hồi, connection bị treo hoặc timeout chưa được cấu hình.
- Có doOnError: phân loại lỗi transport, route, codec hay business từ cause và server logs.
- Có doFinally signal=CANCEL: subscriber đã hủy hoặc timeout/operator upstream đã cancel.
- Có handler-invoked nhưng không có handler-terminal: handler publisher có thể không hoàn tất hoặc bị giữ bởi dependency.
- Có server complete nhưng client không nhận: kiểm tra response encoding, connection và client cancellation.

Dùng timeout có giới hạn và xử lý cancellation rõ ràng. Không dùng block() trong event-loop hoặc reactive handler vì có thể gây deadlock hoặc làm nghẽn thread phục vụ transport. Trong test, dùng StepVerifier.verify(Duration) để tránh chờ vô hạn.

## 10. Quy trình điều tra một sự cố thực tế

1. Thu thập một correlation ID và khoảng thời gian hẹp. Ghi route, interaction model, service/instance và attempt.
2. Tìm event đầu tiên ở producer. Xác định message có được tạo và có đi tới lệnh gửi hay không.
3. Tìm event ở client requester: subscribe, send, error, terminal. Nếu không có subscribe, điều tra code tạo publisher và nhánh thực thi.
4. Kiểm tra connection/transport, setup và broker/queue nếu có. Đối chiếu connection logs, active connections, queue depth và consumer lag.
5. Tìm event handler-invoked trên responder. Nếu không có, kiểm tra route, responder mapping, MIME type và codec.
6. Nếu handler đã chạy, theo dõi từng downstream dependency, channel, filter, router và transaction.
7. Nếu business xử lý xong nhưng không có response, kiểm tra kiểu trả về Mono/Flux, empty completion, error mapping và encode.
8. Nếu server phát reply, kiểm tra client response/error/terminal hooks, timeout, cancellation và decode.
9. Tái hiện bằng LocalTransport integration test để cô lập mapping/codec/protocol; sau đó chạy TCP/WebSocket test nếu nghi ngờ transport thật.
10. Ghi lại chặng cuối cùng có bằng chứng, nguyên nhân đã xác nhận, và metric/log/test nào sẽ giúp phát hiện sớm lần sau.

Khi message đi qua broker, thêm các bước kiểm tra broker publish acknowledgement, routing key/topic, subscription/binding, consumer group/offset, retry queue, dead-letter queue và acknowledgement. Không giả định RSocket transport và broker có cùng semantics delivery.

## 11. Test tái hiện với LocalTransport

LocalTransport cho phép nối RSocketRequester và RSocketMessageHandler qua protocol stack trong cùng tiến trình. Dùng tên transport duy nhất cho mỗi test. Test này chứng minh route, payload và handler thực sự trao đổi được, đồng thời tạo các điểm log có correlation ID.

### 11.1. Maven dependencies

POM tối thiểu cho Java 17, Spring Framework 7.0.8, RSocket Java 1.1.5, Reactor Test và JUnit 5:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>rsocket-missing-message-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <rsocket.version>1.1.5</rsocket.version>
    <junit.version>5.12.2</junit.version>
    <reactor.version>3.8.7</reactor.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-messaging</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-core</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-transport-local</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>${reactor.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Nếu ứng dụng dùng Spring Boot, ưu tiên dependency management của Boot thay vì cố định các phiên bản độc lập như ví dụ này.

### 11.2. Test hoàn chỉnh

Lưu thành src/test/java/example/MissingMessageDiagnosticTest.java:

~~~java
package example;

import java.time.Duration;
import java.util.List;

import io.rsocket.core.RSocketServer;
import io.rsocket.transport.local.LocalClientTransport;
import io.rsocket.transport.local.LocalServerTransport;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class MissingMessageDiagnosticTest {

    static final class DiagnosticHandler {
        private static final System.Logger LOG =
                System.getLogger(DiagnosticHandler.class.getName());

        @MessageMapping("orders.lookup")
        public Mono<String> lookup(@Payload String envelope) {
            String[] parts = envelope.split("\\|", 2);
            if (parts.length != 2) {
                return Mono.error(new IllegalArgumentException(
                        "Expected correlationId|orderId"));
            }

            String correlationId = parts[0];
            String orderId = parts[1];
            LOG.log(System.Logger.Level.INFO,
                    "hop=server-handler-invoked correlationId=" + correlationId);

            return Mono.defer(() -> {
                LOG.log(System.Logger.Level.INFO,
                        "hop=server-processing-start correlationId=" + correlationId);
                return Mono.just("found:" + orderId)
                        .doOnNext(value -> LOG.log(System.Logger.Level.INFO,
                                "hop=server-processing-complete correlationId="
                                        + correlationId))
                        .doFinally(signal -> LOG.log(System.Logger.Level.INFO,
                                "hop=server-handler-terminal correlationId="
                                        + correlationId + " signal=" + signal));
            });
        }
    }

    @Test
    void logsCorrelationAtClientAndHandlerAndReturnsReply() {
        String transportName = "missing-message-row396";
        String correlationId = "corr-396";
        RSocketStrategies strategies = RSocketStrategies.create();

        RSocketMessageHandler messageHandler = new RSocketMessageHandler();
        messageHandler.setRSocketStrategies(strategies);
        messageHandler.setHandlers(List.of(new DiagnosticHandler()));
        messageHandler.afterPropertiesSet();

        Disposable server = RSocketServer.create(messageHandler.responder())
                .bind(LocalServerTransport.create(transportName))
                .block(Duration.ofSeconds(5));
        assertNotNull(server);

        RSocketRequester requester = RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .transport(LocalClientTransport.create(transportName));

        System.Logger log = System.getLogger(
                MissingMessageDiagnosticTest.class.getName());
        try {
            Mono<String> reply = requester.route("orders.lookup")
                    .data(correlationId + "|order-42")
                    .retrieveMono(String.class)
                    .doOnSubscribe(ignored -> log.log(System.Logger.Level.INFO,
                            "hop=client-send correlationId=" + correlationId))
                    .doOnNext(value -> log.log(System.Logger.Level.INFO,
                            "hop=client-reply correlationId=" + correlationId))
                    .doOnError(error -> log.log(System.Logger.Level.ERROR,
                            "hop=client-error correlationId=" + correlationId, error))
                    .doFinally(signal -> log.log(System.Logger.Level.INFO,
                            "hop=client-terminal correlationId=" + correlationId
                                    + " signal=" + signal));

            StepVerifier.create(reply)
                    .expectNext("found:order-42")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        }
        finally {
            requester.dispose();
            server.dispose();
        }
    }
}
~~~

Test dùng payload envelope dạng correlationId|orderId để giữ ví dụ gọn. Trong ứng dụng thật, dùng DTO có kiểu hoặc metadata MIME type đã đăng ký. Kết quả mong đợi là client gửi, server vào handler, business processing hoàn tất, client nhận reply và cả hai publisher hoàn tất. Log có cùng correlationId giúp ghép các chặng.

Chạy:

~~~bash
mvn test
~~~

Kết quả Surefire:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

LocalTransport không kiểm tra port, TLS, WebSocket upgrade hoặc network failure. Dùng test này để thu hẹp lỗi vào protocol/requester/handler trước khi chạy test transport thật.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước xác minh |
|---|---|---|
| Producer log có nhưng requester không gửi | Publisher chưa subscribe hoặc bị filter | Kiểm tra subscription, doFinally và nhánh code |
| Client có send nhưng server không có handler | Connection, route hoặc responder mapping | Kiểm tra setup/transport, route và MIME metadata |
| Handler chạy nhưng service không chạy | Reactive pipeline chưa subscribe hoặc điều kiện rẽ nhánh | Log tại Mono.defer và trước khi gọi service |
| Service hoàn tất nhưng client chờ | Handler trả empty, encode lỗi hoặc response không được gửi | Kiểm tra terminal signal và server-side error |
| Server reply nhưng client không nhận | Connection đóng, timeout, cancellation hoặc decode | Đối chiếu client hooks, codec và connection logs |
| Chỉ lỗi dưới tải | Queue đầy, consumer lag, scheduler nghẽn, timeout | Kiểm tra latency, backlog, thread và retry |
| Message biến mất sau filter | Filter chủ động loại bỏ | Ghi metric/log cho nhánh discard |
| Một message xuất hiện nhiều lần | Redelivery, retry hoặc duplicate publish | Dùng idempotency key và log delivery/attempt |
| Trace không nối qua hai service | Context không được propagate | Kiểm tra Reactor Context, tracing instrumentation và transport metadata |

## 13. Checklist vận hành

- Mỗi thao tác có correlation ID xuyên suốt; retry có attempt riêng.
- Log phân biệt created, subscribed, sent, handler-invoked, processed, replied và consumed.
- Log chứa route, interaction, service/instance, outcome và duration.
- Metrics dùng tag cardinality thấp; không gắn correlation ID vào metric tag.
- Có trace nối producer, messaging transport, handler và downstream dependency.
- Có log cho filter/discard, retry, timeout và dead-letter.
- Payload nhạy cảm, token và metadata bí mật không xuất hiện trong log.
- Test LocalTransport xác nhận requester, route, handler và codec.
- Test TCP/WebSocket riêng xác nhận cấu hình transport production.
- Mọi test có timeout hữu hạn và cleanup requester/server.
- Runbook ghi rõ chặng cuối có bằng chứng và thao tác tiếp theo.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — Messaging](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Framework API — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html)
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
