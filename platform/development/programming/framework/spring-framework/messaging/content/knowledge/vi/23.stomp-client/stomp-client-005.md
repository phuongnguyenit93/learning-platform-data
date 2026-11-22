# StompFrameHandler và chuyển đổi payload nhận được

## Mục tiêu

Khi một ứng dụng Java dùng Spring làm STOMP client, client không nhận trực tiếp một object Java từ server. Nó nhận một STOMP frame có header và phần body dạng byte. Spring cung cấp `StompFrameHandler` để xử lý frame nhận được và `MessageConverter` để chuyển body thành kiểu dữ liệu mà ứng dụng mong muốn.

Hai phương thức cốt lõi của `StompFrameHandler` là:

- `getPayloadType(StompHeaders headers)`: khai báo kiểu dữ liệu đích mà payload cần được chuyển đổi thành.
- `handleFrame(StompHeaders headers, Object payload)`: xử lý payload sau khi converter đã chuyển đổi thành công.

Bài này sử dụng `WebSocketStompClient` để minh họa client Java nhận một JSON message và chuyển nó thành DTO. Các khái niệm về frame handler và message converter cũng áp dụng khi dùng một STOMP transport client khác của Spring.

## 1. Luồng nhận một STOMP frame

Khi client đã kết nối STOMP và subscribe một destination, broker có thể gửi frame `MESSAGE` về client. Frame thường có dạng:

~~~text
MESSAGE
destination:/topic/prices
subscription:sub-0
message-id:msg-42
content-type:application/json

{"symbol":"ACME","price":125.50,"observedAtEpochMillis":1794033000000}
^@
~~~

Một frame gồm command, header và body. Với ví dụ trên:

- `MESSAGE` cho biết broker đang chuyển một message tới subscription.
- `destination` là destination của message.
- `subscription` xác định subscription đã nhận message.
- `message-id` là định danh message do broker cung cấp.
- `content-type` mô tả định dạng body.
- Phần JSON sau dòng trống là body của message.

Spring xử lý frame theo luồng sau:

1. `WebSocketStompClient` nhận frame từ WebSocket transport.
2. Spring phân tích command và STOMP headers thành `StompHeaders`.
3. Spring tìm handler gắn với subscription tương ứng.
4. Spring gọi `getPayloadType(headers)` để hỏi handler muốn nhận kiểu nào.
5. `MessageConverter` được cấu hình trên client chuyển body từ byte[] sang kiểu đích, dựa trên kiểu được yêu cầu và thông tin như `content-type`.
6. Spring gọi `handleFrame(headers, payload)` với object đã chuyển đổi.

Vì vậy, `handleFrame` thường không cần tự đọc byte[] hoặc gọi Jackson để parse JSON. Việc chuyển đổi đã được thực hiện trước callback nếu client có converter phù hợp.

## 2. Vai trò của StompFrameHandler

`StompFrameHandler` thuộc package `org.springframework.messaging.simp.stomp`. Đây là contract xử lý một STOMP frame được chuyển tới subscription.

~~~java
import java.lang.reflect.Type;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;

public class MyFrameHandler implements StompFrameHandler {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        return String.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        String text = (String) payload;
        System.out.println(text);
    }
}
~~~

`getPayloadType` được gọi trước `handleFrame`. Kiểu trả về là `java.lang.reflect.Type`, cho phép khai báo một kiểu class cụ thể. Với trường hợp thông thường, trả về `String.class`, `byte[].class` hoặc DTO class.

`handleFrame` nhận hai tham số:

- `headers`: metadata của STOMP frame dưới dạng `StompHeaders`.
- `payload`: object đã được converter chuyển đổi sang kiểu mà `getPayloadType` yêu cầu. Nếu frame không có body, payload có thể là `null`.

Một handler nên kiểm tra null nếu giao thức ứng dụng cho phép message rỗng. Nếu payload có thể đến từ nhiều nguồn hoặc nhiều phiên bản schema, hãy kiểm tra kiểu và dữ liệu trước khi sử dụng.

## 3. Chọn MessageConverter phù hợp

`WebSocketStompClient` có một `MessageConverter` để chuyển payload giữa object Java và byte[] khi gửi hoặc nhận. Nếu không cấu hình converter, client dùng converter mặc định của Spring; converter mặc định không tự biến JSON bất kỳ thành DTO tùy ý.

Một số lựa chọn thường gặp:

| Loại payload | Converter | Kiểu trả về từ `getPayloadType` |
|---|---|---|
| Văn bản thuần | `StringMessageConverter` | `String.class` |
| Mảng byte | `ByteArrayMessageConverter` | `byte[].class` |
| JSON thành DTO | `JacksonJsonMessageConverter` trên Spring 7 | DTO class |
| JSON thành DTO trên Spring 6.x | `MappingJackson2MessageConverter` | DTO class |

Spring Framework 7 dùng `JacksonJsonMessageConverter` dựa trên Jackson 3. Trong Spring Framework 6.x, ứng dụng thường dùng `MappingJackson2MessageConverter` dựa trên Jackson 2. `MappingJackson2MessageConverter` được đánh dấu deprecated từ Spring 7.0 để chuyển sang converter mới.

Ví dụ cấu hình cho Spring Framework 7:

~~~java
import org.springframework.messaging.converter.JacksonJsonMessageConverter;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setMessageConverter(new JacksonJsonMessageConverter());
~~~

Với Spring Framework 6.x, thay dòng cấu hình converter bằng:

~~~java
import org.springframework.messaging.converter.MappingJackson2MessageConverter;

stompClient.setMessageConverter(new MappingJackson2MessageConverter());
~~~

Ứng dụng phải có dependency Jackson tương ứng với phiên bản Spring đang dùng. Converter JSON cũng cần nhận được STOMP `content-type` phù hợp, thường là `application/json`. Cấu hình converter phía client và định dạng message phía server/broker phải thống nhất.

## 4. Chuyển JSON thành DTO

Giả sử server phát dữ liệu giá cổ phiếu với body JSON:

~~~json
{
  "symbol": "ACME",
  "price": 125.50,
  "observedAtEpochMillis": 1794033000000
}
~~~

Tạo DTO Java 17:

~~~java
import java.math.BigDecimal;

public record PriceUpdate(
        String symbol,
        BigDecimal price,
        long observedAtEpochMillis
) {
}
~~~

Handler khai báo DTO là kiểu payload đích:

~~~java
import java.lang.reflect.Type;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;

public class PriceUpdateFrameHandler implements StompFrameHandler {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        return PriceUpdate.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        if (payload == null) {
            System.out.println("Received an empty price update");
            return;
        }

        PriceUpdate update = (PriceUpdate) payload;

        System.out.println("Destination: " + headers.getDestination());
        System.out.println("Symbol: " + update.symbol());
        System.out.println("Price: " + update.price());
    }
}
~~~

Khi frame có `content-type:application/json`, Spring dùng converter JSON để tạo `PriceUpdate` trước khi gọi `handleFrame`. Bên trong handler, payload đã là object Java nên có thể truy cập trực tiếp các accessor của record.

Ví dụ này dùng epoch milliseconds để tránh yêu cầu thêm cấu hình module ngày giờ cho Jackson. Nếu DTO dùng `Instant`, `LocalDateTime` hoặc kiểu Java Time khác, hãy bảo đảm Jackson Java Time module tương ứng đã được cài và đăng ký với mapper.

## 5. Đăng ký handler khi subscribe

Handler được truyền vào `StompSession.subscribe`. Nên subscribe sau khi STOMP session đã kết nối thành công, thường trong callback `afterConnected`:

~~~java
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;

public class PriceClientSessionHandler extends StompSessionHandlerAdapter {

    @Override
    public void afterConnected(
            StompSession session,
            org.springframework.messaging.simp.stomp.StompHeaders connectedHeaders) {

        session.subscribe(
                "/topic/prices",
                new PriceUpdateFrameHandler()
        );
    }
}
~~~

Ở đây, `/topic/prices` là destination mà client muốn nhận. Handler được gắn với subscription này sẽ xử lý các message broker chuyển tới subscription.

`subscribe` trả về `StompSession.Subscription`. Có thể giữ handle này để hủy subscription khi không cần nhận nữa:

~~~java
StompSession.Subscription subscription =
        session.subscribe("/topic/prices", new PriceUpdateFrameHandler());

// Khi cần ngừng nhận:
subscription.unsubscribe();
~~~

Nếu subscribe nhiều destination, có thể tạo một handler riêng cho từng kiểu payload. Cách này làm rõ schema của từng luồng và tránh một handler phải đoán kiểu object trong nhiều trường hợp.

## 6. Ví dụ client hoàn chỉnh theo các thành phần chính

Ví dụ dưới đây minh họa cấu hình client, kết nối và đăng ký handler. Nó giả định server đã mở STOMP endpoint tại `/ws` và có thể phát JSON tới `/topic/prices`.

~~~java
import org.springframework.messaging.converter.JacksonJsonMessageConverter;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public class PriceClient {

    public static void main(String[] args) {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-client-");
        scheduler.initialize();

        WebSocketStompClient client =
                new WebSocketStompClient(new StandardWebSocketClient());

        client.setMessageConverter(new JacksonJsonMessageConverter());
        client.setTaskScheduler(scheduler);

        StompSessionHandlerAdapter sessionHandler =
                new StompSessionHandlerAdapter() {

            @Override
            public void afterConnected(
                    StompSession session,
                    org.springframework.messaging.simp.stomp.StompHeaders headers) {

                session.subscribe(
                        "/topic/prices",
                        new PriceUpdateFrameHandler()
                );
                System.out.println("Subscribed to /topic/prices");
            }

            @Override
            public void handleTransportError(
                    StompSession session,
                    Throwable exception) {
                System.err.println("STOMP transport error: " + exception.getMessage());
            }
        };

        client.connectAsync("ws://localhost:8080/ws", sessionHandler);
    }
}
~~~

Trong một ứng dụng Spring thực tế, nên khai báo `WebSocketStompClient` và `TaskScheduler` thành bean rồi inject vào component quản lý kết nối. Ví dụ trên tập trung vào cách kết nối và đăng ký handler; vòng đời ứng dụng cần quản lý việc đóng session, dừng client và shutdown scheduler khi ứng dụng kết thúc.

`StandardWebSocketClient` sử dụng một WebSocket implementation tương thích với Jakarta WebSocket. Nếu runtime chưa cung cấp implementation, cần thêm implementation phù hợp vào classpath. Có thể thay transport bằng SockJS client khi server endpoint được cấu hình hỗ trợ SockJS.

## 7. Đọc STOMP headers trong handleFrame

Ngoài payload, handler có thể đọc metadata để ghi log, kiểm tra routing hoặc xử lý header nghiệp vụ:

~~~java
@Override
public void handleFrame(StompHeaders headers, Object payload) {
    String destination = headers.getDestination();
    String messageId = headers.getMessageId();
    var contentType = headers.getContentType();

    System.out.println("Destination: " + destination);
    System.out.println("Message ID: " + messageId);
    System.out.println("Content type: " + contentType);

    PriceUpdate update = (PriceUpdate) payload;
    System.out.println(update);
}
~~~

Một số thông tin thường dùng:

- `getDestination()`: destination của frame.
- `getMessageId()`: message identifier nếu broker cung cấp.
- `getSubscription()`: subscription identifier liên quan đến frame.
- `getContentType()`: MIME type của payload.
- `getFirstNativeHeader(name)`: đọc native STOMP header do ứng dụng bổ sung.

Không nên dùng custom header do client gửi làm bằng chứng xác thực hoặc quyền truy cập. Danh tính và quyền phải được xác minh ở server thông qua cơ chế authentication/authorization.

## 8. Chọn kiểu payload theo header

Một subscription thường nhận một schema thống nhất, vì vậy trả về một DTO cố định từ `getPayloadType` là lựa chọn dễ bảo trì nhất.

Nếu một destination cố ý truyền nhiều loại event, có thể dùng một header nghiệp vụ để chọn kiểu:

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    String eventType = headers.getFirstNativeHeader("event-type");

    if ("PRICE_UPDATED".equals(eventType)) {
        return PriceUpdate.class;
    }

    return String.class;
}
~~~

Handler cần xử lý từng kiểu tương ứng:

~~~java
@Override
public void handleFrame(StompHeaders headers, Object payload) {
    String eventType = headers.getFirstNativeHeader("event-type");

    if ("PRICE_UPDATED".equals(eventType) && payload instanceof PriceUpdate update) {
        handlePriceUpdate(update);
        return;
    }

    if (payload instanceof String text) {
        handleTextEvent(text);
        return;
    }

    throw new IllegalArgumentException("Unsupported event payload");
}
~~~

Cả server và client phải thống nhất tên header, giá trị event type, content type và schema. Không chọn class tùy ý chỉ dựa trên dữ liệu không đáng tin cậy. Với nhiều event type, một DTO envelope chung có trường `type` và `data` thường dễ mở rộng hơn việc thay đổi kiểu đích liên tục.

## 9. Xử lý payload dạng String, byte[] và JSON

**Văn bản thuần**

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    return String.class;
}
~~~

Cấu hình `StringMessageConverter` để nhận text body:

~~~java
stompClient.setMessageConverter(new StringMessageConverter());
~~~

**Payload nhị phân**

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    return byte[].class;
}
~~~

Cấu hình `ByteArrayMessageConverter` nếu cần xử lý raw bytes. Ứng dụng tự giải mã định dạng nhị phân sau khi nhận payload.

**JSON DTO**

~~~java
@Override
public Type getPayloadType(StompHeaders headers) {
    return PriceUpdate.class;
}
~~~

Dùng converter Jackson phù hợp với phiên bản Spring. Đây thường là cách thuận tiện nhất cho ứng dụng nghiệp vụ vì DTO có kiểu rõ ràng và dễ kiểm tra.

Không nên parse JSON hai lần. Nếu converter đã trả về `PriceUpdate`, không chuyển object đó ngược thành String để parse lại bằng ObjectMapper.

## 10. Lỗi chuyển đổi payload và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `handleFrame` không nhận được DTO | Client chưa cấu hình JSON converter | Cấu hình converter tương ứng với phiên bản Spring |
| Không tìm được converter phù hợp | STOMP `content-type` không khớp hoặc payload type không được hỗ trợ | Kiểm tra header `content-type` và `getPayloadType` |
| Jackson báo lỗi parse | JSON sai cú pháp hoặc không khớp cấu trúc DTO | Kiểm tra body thực tế, tên field, kiểu dữ liệu và constructor/record |
| Ép kiểu bị lỗi | `getPayloadType` trả về kiểu khác với kiểu handler đang cast | Dùng một kiểu đích nhất quán và kiểm tra bằng `instanceof` |
| Payload là null | Frame không có body | Xử lý trường hợp rỗng trước khi cast |
| Không nhận được frame | Client chưa CONNECTED, chưa subscribe hoặc destination sai | Kiểm tra callback `afterConnected`, SUBSCRIBE và broker destination |
| Message lớn bị từ chối | Vượt giới hạn buffer inbound | Kiểm tra `setInboundMessageSizeLimit` và giới hạn transport/server |

Khi xảy ra exception trong quá trình xử lý frame hoặc chuyển đổi, session handler có thể nhận thông tin qua `handleException`. Lỗi kết nối hoặc transport được báo qua `handleTransportError`. Nên ghi log đủ destination, content type và loại lỗi; tránh log token, mật khẩu hoặc dữ liệu nhạy cảm trong payload.

Ví dụ bổ sung callback lỗi:

~~~java
@Override
public void handleException(
        StompSession session,
        StompCommand command,
        StompHeaders headers,
        byte[] payload,
        Throwable exception) {

    System.err.println("STOMP handling error: " + exception.getMessage());
}

@Override
public void handleTransportError(
        StompSession session,
        Throwable exception) {

    System.err.println("Transport error: " + exception.getMessage());
}
~~~

## 11. Heartbeat, receipt và kích thước message

**Heartbeat** giúp phát hiện kết nối không còn hoạt động. `WebSocketStompClient` có thể dùng `TaskScheduler` để lên lịch heartbeat. Khi cấu hình scheduler, client sử dụng heartbeat mặc định phù hợp thay vì tắt heartbeat mặc định của client. Scheduler cũng cần thiết cho receipt tracking.

**Receipt** xác nhận broker đã xử lý một thao tác STOMP như SEND hoặc SUBSCRIBE. Có thể bật tự động:

~~~java
session.setAutoReceipt(true);

session.subscribe("/topic/prices", new PriceUpdateFrameHandler())
        .addReceiptTask(() -> System.out.println("SUBSCRIBE processed"));
~~~

Receipt xác nhận broker xử lý frame, không chứng minh logic trong `handleFrame` đã hoàn tất hoặc người dùng đã nhìn thấy thông tin.

**Kích thước message**: giới hạn inbound message mặc định của `WebSocketStompClient` là 64 KB. Có thể tăng hoặc giảm theo nhu cầu:

~~~java
stompClient.setInboundMessageSizeLimit(128 * 1024);
~~~

Giới hạn này cần được phối hợp với giới hạn WebSocket container, reverse proxy và broker. Không nên tăng giới hạn một cách tùy tiện; payload lớn làm tăng bộ nhớ và chi phí xử lý cho mỗi kết nối.

## 12. Kiểm thử handler và converter

Có hai cấp độ kiểm thử:

1. **Unit test handler**: truyền trực tiếp DTO và headers vào `handleFrame` để kiểm tra logic xử lý. Cách này không xác minh quá trình deserialize JSON.
2. **Integration test**: chạy STOMP client và server/broker thật hoặc test broker phù hợp, gửi frame JSON có `content-type:application/json`, rồi xác nhận callback nhận được đúng DTO.

Các tình huống nên kiểm tra:

- JSON hợp lệ được chuyển thành đúng DTO.
- Body sai định dạng tạo lỗi chuyển đổi có thể quan sát qua session handler.
- Body rỗng được xử lý theo quy tắc ứng dụng.
- Header content type không hỗ trợ được phát hiện.
- Subscribe đúng destination nhận được message.
- Unsubscribe ngăn handler nhận message tiếp theo.
- Kết nối mất được báo qua `handleTransportError`.

Một unit test gọi trực tiếp `handleFrame` không thể chứng minh `MessageConverter` đã được cấu hình đúng. Để kiểm tra conversion, cần test qua pipeline nhận frame của STOMP client.

## Ghi nhớ

- `StompFrameHandler` xử lý frame được gửi tới một subscription.
- `getPayloadType` khai báo kiểu đích và được gọi trước `handleFrame`.
- `MessageConverter` chuyển body từ byte[] sang object Java dựa trên kiểu đích và header như `content-type`.
- `handleFrame` nhận payload đã chuyển đổi; payload có thể null nếu body rỗng.
- Dùng `StringMessageConverter` cho text, `ByteArrayMessageConverter` cho bytes và converter Jackson cho JSON DTO.
- Spring 7 dùng `JacksonJsonMessageConverter` (Jackson 3); Spring 6.x thường dùng `MappingJackson2MessageConverter` (Jackson 2).
- Đăng ký subscription sau khi STOMP CONNECTED, thường trong `afterConnected`.
- Dùng `handleException` và `handleTransportError` để quan sát lỗi xử lý và lỗi transport.
- Receipt xác nhận broker xử lý frame, không xác nhận nghiệp vụ đã hoàn tất.

## Tài liệu tham khảo

- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/client.html)
- [StompFrameHandler API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/stomp/StompFrameHandler.html)
- [StompSession API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html)
- [WebSocketStompClient API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [JacksonJsonMessageConverter API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/converter/JacksonJsonMessageConverter.html)
