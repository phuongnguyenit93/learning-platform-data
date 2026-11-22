# TaskScheduler, heart-beat và giới hạn kích thước thông điệp

Khi dùng `WebSocketStompClient` của Spring, `TaskScheduler` đảm nhiệm các tác vụ định kỳ của STOMP client, nổi bật là gửi heartbeat và theo dõi thời hạn RECEIPT. Cùng lúc đó, client có giới hạn bộ đệm cho STOMP message nhận vào để ghép một message có thể được chia thành nhiều WebSocket message. Cần hiểu các giới hạn này theo từng chiều truyền dữ liệu, vì cấu hình ở client, cấu hình WebSocket server và giới hạn của container là những lớp khác nhau.

Bài này tập trung vào STOMP client Java của Spring Framework 6.1. API bổ sung trong Spring 6.2 được đánh dấu riêng khi có khác biệt.

## 1. Vị trí của TaskScheduler trong STOMP client

`WebSocketStompClient` là adapter đưa giao thức STOMP lên một `WebSocketClient`. Nó quản lý việc kết nối, mã hóa và giải mã STOMP frame, chuyển đổi payload và tạo `StompSession` để ứng dụng gửi, subscribe hoặc xử lý message.

Một STOMP client thường thực hiện các công việc sau:

- Mở kết nối WebSocket tới endpoint của server.
- Gửi frame `CONNECT` và nhận frame `CONNECTED`.
- Gửi `SUBSCRIBE`, `SEND`, `UNSUBSCRIBE` và các frame STOMP khác.
- Nhận `MESSAGE`, `ERROR`, `RECEIPT` và xử lý payload.
- Duy trì heartbeat khi kết nối không có lưu lượng.
- Theo dõi những receipt đã yêu cầu để biết frame đã được server xử lý hay chưa.

`TaskScheduler` cung cấp bộ lập lịch cho các tác vụ cần chạy theo thời gian. Trong `WebSocketStompClient`, scheduler được dùng cho heartbeat và receipt tracking. Nó không phải thread pool xử lý payload trong callback, không thay thế `TaskExecutor` và cũng không phải scheduler của simple broker phía server.

Sự phân biệt này quan trọng khi một ứng dụng vừa chạy STOMP client để kết nối tới hệ thống khác, vừa bật STOMP server để phục vụ client bên ngoài. Scheduler truyền cho `WebSocketStompClient` thuộc phía client; scheduler cấu hình trong `MessageBrokerRegistry` thuộc broker phía server. Hai thành phần có vòng đời và trách nhiệm riêng.

## 2. Khai báo TaskScheduler cho WebSocketStompClient

Có thể dùng `ThreadPoolTaskScheduler` làm một Spring bean. Bean này được container quản lý vòng đời và được inject vào `WebSocketStompClient`:

~~~java
package com.example.messaging.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.converter.StringMessageConverter;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

@Configuration
public class StompClientConfiguration {

    @Bean
    public ThreadPoolTaskScheduler stompClientTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("stomp-client-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }

    @Bean
    public WebSocketStompClient webSocketStompClient(
            TaskScheduler stompClientTaskScheduler) {

        WebSocketStompClient client =
                new WebSocketStompClient(new StandardWebSocketClient());

        client.setMessageConverter(new StringMessageConverter());
        client.setTaskScheduler(stompClientTaskScheduler);
        client.setDefaultHeartbeat(new long[] {10_000, 10_000});
        client.setReceiptTimeLimit(15_000);
        client.setInboundMessageSizeLimit(128 * 1024);

        return client;
    }
}
~~~

Ví dụ đặt pool size bằng 2 để minh họa; số thread phù hợp phụ thuộc số session, tần suất tác vụ và tải thực tế. Nếu ứng dụng có nhiều bean cùng kiểu `TaskScheduler`, hãy dùng `@Qualifier("stompClientTaskScheduler")` ở tham số inject để chọn đúng bean.

Một số điểm cần lưu ý:

- `setTaskScheduler(...)` bật scheduler cho heartbeat và receipt tracking.
- `setDefaultHeartbeat(...)` đặt hai giá trị heartbeat mặc định được client gửi trong frame `CONNECT`.
- `setReceiptTimeLimit(...)` đặt thời gian tối đa chờ receipt trước khi receipt được xem là hết hạn. Mặc định là 15.000 ms.
- `setInboundMessageSizeLimit(...)` đặt dung lượng bộ đệm tối đa cho một STOMP message nhận vào. Ví dụ dùng 128 KiB.
- `setMessageConverter(...)` chọn cách chuyển đổi payload. Ví dụ dùng `StringMessageConverter` cho payload văn bản; nếu truyền DTO/JSON, cần converter JSON phù hợp.

Không tạo scheduler mới cho từng message. Với một client có nhiều session, scheduler được chia sẻ để chạy các tác vụ định kỳ của client đó.

### Mặc định đặc biệt của WebSocketStompClient

Lớp nền `StompClientSupport` có heartbeat mặc định `10000,10000`, nhưng constructor của `WebSocketStompClient` đặt mặc định thành `0,0`. Khi gọi `setTaskScheduler(...)`, nếu heartbeat vẫn là `0,0`, client tự chuyển về giá trị khuyến nghị `10000,10000`.

Vì vậy, nếu muốn tùy chỉnh heartbeat, hãy cấu hình scheduler trước rồi gọi `setDefaultHeartbeat(...)` với giá trị mong muốn. Điều này giúp tránh nhầm lẫn giữa mặc định của lớp nền và mặc định riêng của `WebSocketStompClient`.

Một số transport có hỗ trợ heartbeat riêng và không cần scheduler chỉ để gửi/nhận heartbeat. Tuy nhiên, nếu ứng dụng cần theo dõi RECEIPT, `TaskScheduler` vẫn cần được cấu hình.

## 3. Heartbeat phía client

Heartbeat là tín hiệu STOMP định kỳ giúp hai đầu phát hiện kết nối không còn hoạt động. Nó được trao đổi khi không có message STOMP thông thường nào được gửi trong khoảng thời gian tương ứng. Nếu client vừa gửi `SEND` hoặc server vừa gửi `MESSAGE`, dữ liệu đó cũng thể hiện hoạt động trên kết nối; heartbeat rỗng không cần phát thêm ngay lúc đó.

Trong STOMP, header `heart-beat` có hai số, đơn vị mili giây. Ở frame `CONNECT` của client:

- Số thứ nhất biểu thị khoảng client có thể gửi heartbeat.
- Số thứ hai biểu thị khoảng client muốn nhận heartbeat từ server.
- Giá trị `0` nghĩa là client không hỗ trợ gửi hoặc không yêu cầu nhận heartbeat ở chiều tương ứng.

Client Spring đặt hai giá trị này bằng:

~~~java
client.setDefaultHeartbeat(new long[] {10_000, 15_000});
~~~

Ở ví dụ trên, client có thể gửi heartbeat tối thiểu mỗi 10 giây và mong server gửi heartbeat trong khoảng 15 giây, trước khi thương lượng với khả năng của server.

### Thương lượng hai chiều

Server trả về cặp `heart-beat` trong frame `CONNECTED`. Gọi:

- Client khai báo `cx, cy`.
- Server khai báo `sx, sy`.

Khoảng heartbeat được thương lượng độc lập cho từng chiều:

~~~text
Client -> Server:
  Không có heartbeat nếu cx = 0 hoặc sy = 0
  Nếu cả hai khác 0: khoảng = max(cx, sy)

Server -> Client:
  Không có heartbeat nếu sx = 0 hoặc cy = 0
  Nếu cả hai khác 0: khoảng = max(sx, cy)
~~~

Ví dụ client khai báo `10000,15000`, server trả `5000,20000`:

- Client → server: `max(10000, 20000) = 20000` ms, tức 20 giây.
- Server → client: `max(5000, 15000) = 15000` ms, tức 15 giây.

Giá trị trong `setDefaultHeartbeat(...)` chỉ là đề xuất phía client. Khoảng thực tế phụ thuộc cả hai đầu. Nếu client không gửi header heartbeat hoặc một trong hai đầu đặt giá trị cần thiết bằng 0, chiều tương ứng sẽ không có heartbeat được thương lượng.

### Theo dõi inactivity và phát hiện mất kết nối

Khi scheduler được cấu hình, client có thể:

1. Theo dõi thời điểm gửi dữ liệu cuối cùng để quyết định khi nào cần gửi heartbeat.
2. Theo dõi thời điểm nhận dữ liệu cuối cùng từ server.
3. Phát hiện server không gửi dữ liệu trong thời gian đã thương lượng.
4. Chuyển lỗi kết nối tới `StompSessionHandler` thông qua callback xử lý lỗi vận chuyển.

Heartbeat chỉ giúp phát hiện hoạt động của kết nối theo quy tắc giao thức. Nó không xác nhận một message đã được lưu vào database hoặc xử lý xong trong nghiệp vụ. Nếu cần biết server đã xử lý một frame `SEND` hoặc `SUBSCRIBE`, hãy dùng RECEIPT.

## 4. TaskScheduler và STOMP RECEIPT

STOMP RECEIPT là cơ chế xác nhận server đã xử lý một frame mà client gửi kèm header `receipt`. Nó khác heartbeat:

- Heartbeat kiểm tra hoạt động của kết nối.
- RECEIPT xác nhận việc xử lý một frame cụ thể.
- ACK/NACK liên quan tới xác nhận tiêu thụ message ở phía client, tùy subscription acknowledgment mode.

Trong Spring, `TaskScheduler` cũng theo dõi thời hạn chờ RECEIPT. `StompClientSupport` mặc định đặt receipt time limit là 15 giây; có thể thay đổi bằng `setReceiptTimeLimit(...)`.

Với `StompSession`, có thể bật tự động thêm receipt cho các thao tác gửi và subscribe:

~~~java
session.setAutoReceipt(true);
~~~

Các thao tác `send` và `subscribe` trả về `Receiptable`, cho phép đăng ký callback khi receipt đến hoặc khi thao tác hết hạn. Ví dụ:

~~~java
Receiptable receipt = session.send("/app/orders", orderPayload);

receipt.addReceiptTask(() ->
        System.out.println("Server đã xác nhận frame"));
receipt.addReceiptLostTask(() ->
        System.out.println("Không nhận được RECEIPT trong thời hạn"));
~~~

Để các tác vụ hết hạn được theo dõi, client cần có `TaskScheduler`. Nếu không cấu hình scheduler, không nên bật auto receipt và kỳ vọng client tự theo dõi thời hạn xác nhận.

Receipt chỉ chứng minh server đã xử lý frame theo quy tắc STOMP. Nó không mặc nhiên chứng minh logic nghiệp vụ đã commit transaction hoặc dữ liệu đã được ghi bền vững. Nếu ứng dụng cần xác nhận nghiệp vụ, hãy trả kết quả nghiệp vụ riêng sau khi hoàn tất xử lý.

## 5. Giới hạn kích thước STOMP message nhận vào ở client

`WebSocketStompClient` có thuộc tính `inboundMessageSizeLimit`, được cấu hình bằng:

~~~java
client.setInboundMessageSizeLimit(128 * 1024);
~~~

Giá trị tính bằng byte. Mặc định là `64 * 1024` byte, tức 64 KiB. Đây là giới hạn bộ đệm cho một STOMP message đi vào client.

Một STOMP message có thể được vận chuyển qua nhiều WebSocket message. Khi đó client phải ghép các phần lại để giải mã được toàn bộ STOMP frame. `inboundMessageSizeLimit` giới hạn tổng kích thước được phép buffer cho một message sau khi ghép; nó không đơn thuần là giới hạn của một WebSocket frame riêng lẻ.

Nếu STOMP message nhận vào vượt giới hạn, quá trình giải mã/chuyển đổi thất bại, thường được báo dưới dạng `StompConversionException`. Việc tăng giới hạn cho phép nhận message lớn hơn nhưng cũng làm tăng lượng bộ nhớ có thể cần cho mỗi message đang được buffer.

Ví dụ:

~~~java
WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());

client.setInboundMessageSizeLimit(256 * 1024);
~~~

Cấu hình này cho phép bộ đệm một STOMP message nhận vào tối đa 256 KiB ở phía client. Giá trị nên dựa trên kích thước message hợp lệ lớn nhất mà ứng dụng thực sự cần, cộng thêm biên phù hợp cho header và payload.

### Đây là giới hạn ở chiều nào?

`WebSocketStompClient.setInboundMessageSizeLimit(...)` áp dụng cho message đi từ server tới client STOMP này. Nó không giới hạn message mà client gửi lên server.

Nếu client gửi một message lớn tới server, giới hạn nhận vào của server và giới hạn của WebSocket container phía server mới là những điểm cần kiểm tra. Không thể tăng giới hạn nhận vào của client để sửa lỗi server từ chối message client gửi đi.

## 6. Giới hạn kích thước ở server và WebSocket container

Ở phía server, Spring cung cấp `WebSocketTransportRegistration.setMessageSizeLimit(...)` trong `configureWebSocketTransport(...)` để giới hạn kích thước của inbound sub-protocol message, chẳng hạn một STOMP frame được ghép từ nhiều WebSocket message.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketServerConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {
        registration.setMessageSizeLimit(128 * 1024);
    }
}
~~~

Giá trị mặc định của giới hạn STOMP message phía server là 64 KiB. Cấu hình `128 * 1024` cho phép server buffer một STOMP message đến 128 KiB trước khi xử lý.

Cần phân biệt ba lớp:

| Lớp giới hạn | API/vị trí cấu hình | Chiều áp dụng |
|---|---|---|
| STOMP message buffer của client | `WebSocketStompClient.setInboundMessageSizeLimit(...)` | Server → client |
| STOMP message buffer của Spring server | `configureWebSocketTransport(...).setMessageSizeLimit(...)` | Client → server |
| Kích thước một WebSocket message/frame tại transport container | Cấu hình WebSocket client/server container | Tùy chiều và transport |

Một STOMP message có thể được chia thành nhiều WebSocket message. Spring hỗ trợ ghép các phần đó; tài liệu hiệu năng của Spring lưu ý các STOMP client phổ biến có thể chia message lớn ở ranh giới 16 KiB. Vì vậy, giới hạn của một WebSocket message đơn lẻ trong container phải tương thích với cách client phân mảnh. Spring có điều chỉnh giới hạn WebSocket message để hỗ trợ các phần 16 KiB tối thiểu trong cấu hình STOMP-over-WebSocket.

Giới hạn container vẫn cần xem riêng. Ví dụ tài liệu Spring nêu Tomcat có thể mặc định giới hạn nhỏ hơn Jetty; giá trị thực tế còn phụ thuộc phiên bản và cấu hình container. Khi gặp lỗi frame quá lớn, hãy kiểm tra cả cấu hình container và giới hạn STOMP message của Spring.

## 7. Phân biệt message size với send buffer và send time

Spring server có thêm hai cấu hình cho tình huống gửi tới client chậm:

- `setSendBufferSizeLimit(...)`: giới hạn lượng dữ liệu được buffer khi gửi tới một WebSocket session.
- `setSendTimeLimit(...)`: giới hạn thời gian cho một lần gửi tới session.

Đây là các giới hạn phục vụ outbound flow của server. Khi một client đọc chậm hơn tốc độ server gửi, các message tiếp theo có thể phải chờ trong buffer. Khi vượt giới hạn thời gian hoặc dung lượng buffer, Spring dọn trạng thái session và cố gắng đóng kết nối.

Ví dụ:

~~~java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {
    registration
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setMessageSizeLimit(128 * 1024);
}
~~~

Ba giá trị có mục đích khác nhau:

- `sendTimeLimit`: tối đa 15 giây cho việc gửi.
- `sendBufferSizeLimit`: tối đa 512 KiB dữ liệu đang chờ gửi tới một session.
- `messageSizeLimit`: tối đa 128 KiB cho một inbound STOMP message ở server.

Không dùng `sendBufferSizeLimit` để thay thế `messageSizeLimit`. Một message nhỏ có thể tích lũy thành buffer outbound lớn nếu client đọc chậm; ngược lại, một message inbound lớn có thể vượt `messageSizeLimit` ngay cả khi outbound buffer đang trống.

## 8. Giới hạn outbound của WebSocketStompClient trong Spring 6.1

Trong Spring Framework 6.1, `WebSocketStompClient` có `setInboundMessageSizeLimit(...)` nhưng chưa có API `setOutboundMessageSizeLimit(...)`. Do đó, không viết cấu hình dùng phương thức outbound này nếu dự án đang dùng Spring 6.1.

Với message client gửi đi trong Spring 6.1:

- Kiểm tra giới hạn kích thước message của WebSocket client và transport container đang dùng.
- Kiểm tra giới hạn inbound STOMP message của server nhận.
- Nếu payload nghiệp vụ rất lớn, cân nhắc chia nhỏ dữ liệu ở tầng ứng dụng, dùng upload/download riêng hoặc truyền tham chiếu tới dữ liệu thay vì gửi toàn bộ nội dung trong một STOMP message.
- Kiểm tra cả giới hạn của proxy, gateway và broker bên ngoài nếu có.

Từ Spring Framework 6.2, `WebSocketStompClient` bổ sung `setOutboundMessageSizeLimit(...)`. Khi STOMP message vượt giới hạn cấu hình, client chia nó thành nhiều phần/frame để phía nhận ghép lại. Đây là API mới của 6.2, không phải API có sẵn trong 6.1.

## 9. Chọn giá trị giới hạn phù hợp

Không nên tăng tất cả giới hạn lên một con số rất lớn để tránh lỗi. Mỗi kết nối có thể có nhiều message đang được buffer; số lượng client đồng thời làm tổng bộ nhớ tăng nhanh.

Khi chọn giới hạn:

1. Đo kích thước thực tế của payload lớn nhất trong các use case hợp lệ.
2. Tính thêm header STOMP và phần dữ liệu chuyển đổi cần thiết.
3. Đặt giới hạn ở client và server phù hợp với hướng truyền dữ liệu.
4. Kiểm tra giới hạn WebSocket container, proxy và broker trên toàn tuyến.
5. Ước lượng bộ nhớ có thể bị giữ khi nhiều client cùng nhận message lớn.
6. Kiểm tra tác động của slow client và tốc độ tiêu thụ outbound message.
7. Từ chối payload không hợp lệ bằng validation hoặc giới hạn nghiệp vụ ở tầng ứng dụng.

Đối với payload JSON, kích thước chuỗi ký tự không luôn bằng kích thước byte truyền qua mạng. UTF-8 có thể dùng nhiều byte cho một ký tự; ngoài ra STOMP header và framing cũng chiếm dung lượng. Hãy đo byte thực tế của dữ liệu được mã hóa thay vì chỉ đếm số ký tự Java.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Client nhận message lớn bị StompConversionException | Vượt inboundMessageSizeLimit | Kiểm tra kích thước STOMP message nhận vào và tăng giới hạn có kiểm soát. |
| Client gửi message lớn nhưng server từ chối | Giới hạn inbound STOMP phía server hoặc giới hạn WebSocket container quá nhỏ | Kiểm tra setMessageSizeLimit phía server và giới hạn container. |
| Cấu hình setOutboundMessageSizeLimit không biên dịch | Dự án đang dùng Spring Framework 6.1 | API này có từ 6.2; với 6.1 hãy kiểm soát kích thước ở ứng dụng và transport. |
| Heartbeat không chạy dù đã đặt khoảng thời gian | WebSocketStompClient chưa có scheduler và heartbeat mặc định đang là 0,0 | Gọi setTaskScheduler(...), sau đó đặt setDefaultHeartbeat(...) nếu cần. |
| Client phát hiện server mất kết nối quá sớm | Heartbeat interval ngắn, mạng có jitter hoặc scheduler bị nghẽn | Đối chiếu heart-beat trong CONNECT/CONNECTED và tình trạng scheduler. |
| Không nhận được callback RECEIPT | Frame không yêu cầu receipt, server không gửi receipt hoặc client không có scheduler để theo dõi timeout | Kiểm tra header receipt, callback và TaskScheduler. |
| Client chậm làm bộ nhớ tăng | Nhiều message đang chờ được đọc hoặc buffer vượt khả năng tiêu thụ | Kiểm tra tốc độ outbound, số session và sendBufferSizeLimit phía server. |
| Tăng giới hạn làm ứng dụng tốn bộ nhớ | Quá nhiều message lớn được buffer đồng thời | Đặt giới hạn sát nhu cầu, theo dõi tải và chia nhỏ payload ở tầng ứng dụng. |
| Client chỉ heartbeat một chiều | Khả năng gửi/nhận hai bên không giao nhau trong thương lượng | Tính riêng hai chiều bằng max và kiểm tra cả hai cặp giá trị. |
| Dùng scheduler chung nhưng receipt timeout sai | Receipt time limit không phù hợp độ trễ hệ thống | Điều chỉnh setReceiptTimeLimit(...) dựa trên thời gian phản hồi thực tế. |

## 11. Checklist kiểm thử

Khi cấu hình `WebSocketStompClient`, nên kiểm tra bằng một server STOMP có thể điều khiển:

1. Khởi tạo client với scheduler và xác nhận frame `CONNECT` có header heartbeat mong muốn.
2. Xác nhận frame `CONNECTED` và tính khoảng heartbeat thực tế cho hai chiều.
3. Để kết nối nhàn rỗi để quan sát heartbeat; sau đó gửi message thường xuyên để xác nhận hoạt động dữ liệu cũng được tính.
4. Ngắt hoặc làm chậm phản hồi server trong môi trường kiểm thử để xác nhận callback lỗi vận chuyển được gọi.
5. Bật auto receipt, gửi frame có yêu cầu receipt và xác nhận callback thành công.
6. Tạo tình huống không có receipt để kiểm tra timeout theo `setReceiptTimeLimit(...)`.
7. Gửi STOMP message nhỏ hơn giới hạn và xác nhận client giải mã thành công.
8. Gửi message lớn hơn `inboundMessageSizeLimit` và xác nhận lỗi được phát hiện.
9. Gửi message qua nhiều WebSocket message để xác nhận client ghép đủ dữ liệu.
10. Kiểm tra server inbound limit và WebSocket container limit riêng với client inbound limit.
11. Thử client đọc chậm để quan sát outbound buffer và send time limit ở server.
12. Kiểm tra số lượng session đồng thời để đánh giá tác động của heartbeat task và bộ đệm message.

Không coi một bài kiểm thử heartbeat thành công là bằng chứng cho giới hạn kích thước đã đúng. Đây là hai cơ chế độc lập; cần kiểm tra riêng heartbeat, receipt, inbound message buffer và outbound backpressure.

## Tài liệu tham khảo

- [Spring Framework 6.1 — STOMP Client](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/client.html): tạo WebSocketStompClient, cấu hình TaskScheduler, heartbeat và RECEIPT.
- [Spring Framework 6.1 — Performance](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/configuration-performance.html): cấu hình giới hạn STOMP message, send buffer, send time và cách Spring ghép WebSocket message.
- [Spring Framework 6.1.8 Javadoc — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): setTaskScheduler, setInboundMessageSizeLimit và giá trị mặc định 64 KiB.
- [Spring Framework 6.1.8 Javadoc — StompClientSupport](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/messaging/simp/stomp/StompClientSupport.html): setDefaultHeartbeat, setReceiptTimeLimit và vai trò scheduler.
- [Spring Framework 6.1.8 Javadoc — WebSocketTransportRegistration](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html): giới hạn inbound STOMP message và buffer/time khi gửi tới client.
- [Spring Framework 6.2 Javadoc — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): API setOutboundMessageSizeLimit được bổ sung từ 6.2.
- [STOMP 1.2 Specification — Heart-beating](https://stomp.github.io/stomp-specification-1.2.html#Heart-beating): định dạng header heartbeat và quy tắc thương lượng hai chiều.
