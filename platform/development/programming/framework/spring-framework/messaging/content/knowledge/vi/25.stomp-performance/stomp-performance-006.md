# Giới hạn kích thước message, thời gian gửi và bộ đệm trong STOMP

## 1. Vì sao cần giới hạn tài nguyên?

Trong ứng dụng Spring hỗ trợ STOMP over WebSocket, message đi qua nhiều tầng: WebSocket transport, bộ xử lý STOMP, các channel nội bộ, message broker và kết nối tới từng client. Mỗi tầng có một loại giới hạn riêng.

Một message lớn có thể cần nhiều WebSocket frame để truyền. Một client có đường truyền chậm có thể tiêu thụ message chậm hơn tốc độ server phát ra. Khi đó, message chờ gửi tích tụ trong bộ đệm của session. Nếu không giới hạn kích thước và lượng dữ liệu chờ, một client chậm có thể chiếm bộ nhớ và tài nguyên gửi của server trong thời gian dài.

Spring cung cấp ba nhóm giới hạn quan trọng ở phía server:

- \`messageSizeLimit\`: giới hạn kích thước một message STOMP inbound sau khi ghép các WebSocket message liên quan.
- \`sendTimeLimit\`: giới hạn thời gian gửi tới một WebSocket session.
- \`sendBufferSizeLimit\`: giới hạn số byte được giữ trong bộ đệm gửi của một WebSocket session.

Ở phía STOMP client, \`WebSocketStompClient\` có giới hạn inbound riêng và tùy chọn chia nhỏ message outbound. Đây là cấu hình khác với các giới hạn gửi của server.

## 2. Phân biệt các loại kích thước message

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Nơi cấu hình |
| --- | --- | --- |
| WebSocket frame/message | Đơn vị dữ liệu mà transport WebSocket gửi và nhận | WebSocket server/container và WebSocket client |
| STOMP message/frame | Đơn vị giao thức gồm command, headers và body; có thể trải qua nhiều WebSocket message | Spring STOMP transport hoặc STOMP client |
| Payload nghiệp vụ | Nội dung ứng dụng sau khi MessageConverter giải mã, ví dụ JSON DTO | Hợp đồng API, converter và logic ứng dụng |

Giới hạn của Spring STOMP không đồng nghĩa với giới hạn của một WebSocket frame riêng lẻ. Một STOMP message có thể được chia thành nhiều WebSocket message rồi ghép lại trước khi Spring xử lý. Ngược lại, WebSocket container vẫn có giới hạn riêng đối với từng message/frame transport.

Vì vậy, khi gặp lỗi “message too large”, cần xác định giới hạn nào bị vượt: giới hạn của WebSocket container, giới hạn STOMP ở server, giới hạn inbound của STOMP client, hay giới hạn của một tầng trung gian như reverse proxy hoặc broker.

## 3. Giới hạn message inbound ở phía server

### 3.1. WebSocketTransportRegistration.setMessageSizeLimit

Phương thức \`setMessageSizeLimit(int)\` cấu hình kích thước tối đa của một inbound sub-protocol message, ví dụ một STOMP frame có thể được ghép từ nhiều WebSocket message.

Giá trị mặc định của Spring Framework là **64 KB (64 × 1024 bytes)**. Khi một STOMP message vượt giới hạn này, quá trình xử lý message bị từ chối và có thể phát sinh lỗi chuyển đổi giao thức.

Ví dụ cấu hình giới hạn 128 KB:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration.setMessageSizeLimit(128 * 1024);
    }
}
\`\`\`

Ở đây:

- \`128 * 1024\` là 131.072 bytes, tương đương 128 KiB.
- Giới hạn áp dụng cho một inbound STOMP sub-protocol message sau khi Spring ghép các phần cần thiết.
- Cấu hình này không thay thế giới hạn kích thước WebSocket message của Tomcat, Jetty, Undertow hoặc container đang chạy ứng dụng.

### 3.2. Vì sao STOMP message có thể bị chia nhỏ?

Một WebSocket server có thể áp dụng giới hạn cho mỗi WebSocket message. Ví dụ, tài liệu Spring nêu các cấu hình mặc định phổ biến là khoảng 8 KB trên Tomcat và 64 KB trên Jetty. Để truyền một STOMP message lớn hơn, client STOMP có thể chia dữ liệu thành nhiều WebSocket message.

Một số STOMP client JavaScript, chẳng hạn \`@stomp/stompjs\`, chia message lớn theo các đoạn khoảng 16 KB. Spring STOMP-over-WebSocket có thể ghép các phần này lại và cho phép cấu hình giới hạn ở cấp STOMP message. Spring cũng điều chỉnh kích thước WebSocket message khi cần để có thể mang các đoạn WebSocket tối thiểu 16 KB theo cách hỗ trợ của transport.

Không nên giả định mọi client, server và proxy đều có cùng cách phân mảnh. Hãy kiểm tra tài liệu của WebSocket container và client đang sử dụng, sau đó kiểm thử với message lớn thực tế.

## 4. Thời gian gửi và bộ đệm outbound ở phía server

### 4.1. Vì sao cần hai giới hạn này?

WebSocket server thường yêu cầu các message gửi tới cùng một session được ghi tuần tự từ một thread tại một thời điểm. Cấu hình \`@EnableWebSocketMessageBroker\` của Spring bảo đảm việc gửi tới một session được điều phối theo yêu cầu đó.

Nếu client nhận message chậm hơn tốc độ server phát message, message tiếp theo phải chờ trong bộ đệm. Tình trạng này có thể xảy ra khi:

- Client dùng mạng di động yếu hoặc băng thông thấp.
- Client tạm ngừng đọc do tab trình duyệt bị treo hoặc thiết bị quá tải.
- Server broadcast nhiều message hoặc message có payload lớn.
- Client xử lý message chậm và socket send bị nghẽn.

\`sendTimeLimit\` giới hạn thời gian gửi, còn \`sendBufferSizeLimit\` giới hạn lượng dữ liệu chờ gửi. Hai giá trị phối hợp để ngăn một session chậm giữ bộ đệm vô hạn.

### 4.2. sendTimeLimit

\`WebSocketTransportRegistration.setSendTimeLimit(int)\` nhận thời gian tính bằng milliseconds. Giá trị mặc định của Spring Framework là **10 giây (10.000 ms)**.

Khi gửi tới một session chậm, các message tiếp theo được buffer. Nếu giới hạn thời gian hoặc giới hạn dung lượng buffer bị chạm, Spring xóa trạng thái gửi đang chờ của session và cố gắng đóng session đó.

Có một chi tiết quan trọng: Spring chỉ kiểm tra giới hạn thời gian khi có lần gửi bổ sung. Nếu chỉ có một message đang gửi và thao tác đó bị treo, giới hạn này chưa chắc đóng session ngay; việc kiểm tra có thể phải đợi một message khác được gửi hoặc timeout ở socket vật lý xảy ra. Vì vậy, \`sendTimeLimit\` không thay thế timeout của WebSocket server, HTTP connection hay hệ điều hành.

Giá trị phải lớn hơn 0; giá trị không dương được bỏ qua. Chọn giới hạn theo độ trễ chấp nhận được và tốc độ phát message, thay vì tăng thời gian chỉ để che giấu client chậm.

### 4.3. sendBufferSizeLimit

\`WebSocketTransportRegistration.setSendBufferSizeLimit(int)\` đặt số byte tối đa được buffer khi gửi tới một WebSocket session. Với SockJS fallback, giới hạn cũng áp dụng cho dữ liệu chờ ghi vào HTTP response.

Giá trị mặc định của Spring Framework là **512 KB (512 × 1024 bytes)** cho mỗi session.

Nếu giá trị nhỏ hơn hoặc bằng 0, buffering bị vô hiệu hóa về mặt hiệu lực. Khi message gửi chậm hơn tốc độ phát, buffer có thể đầy trước khi client tiêu thụ dữ liệu. Khi một trong hai giới hạn gửi bị vượt, Spring xóa trạng thái session và cố gắng đóng kết nối.

Đóng session ở tầng framework không bảo đảm socket vật lý luôn đóng tức thì. Với blocking I/O, thao tác đóng có thể bị treo hoặc không hoàn tất như mong đợi. Nên ưu tiên cấu hình connector I/O không blocking của WebSocket server nếu có thể.

### 4.4. Cấu hình đồng thời hai giới hạn

Ví dụ cấu hình send timeout 15 giây và buffer 512 KiB:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketPerformanceConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration
                .setSendTimeLimit(15 * 1000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
\`\`\`

Có thể kết hợp cả ba giới hạn trong một cấu hình:

\`\`\`java
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {

    registration
            .setMessageSizeLimit(128 * 1024)
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
\`\`\`

Không có một bộ giá trị đúng cho mọi ứng dụng. 128 KiB, 15 giây và 512 KiB chỉ là ví dụ để minh họa API. Cần hiệu chỉnh theo kích thước payload, tần suất broadcast, số kết nối đồng thời, băng thông và mức độ trễ mà sản phẩm chấp nhận.

## 5. Cấu hình ở phía WebSocketStompClient

Các thuộc tính của \`WebSocketStompClient\` điều khiển cách client Java xử lý message của chính nó. Chúng không thay thế cấu hình server ở các phần trước.

### 5.1. Inbound message size limit

\`setInboundMessageSizeLimit(int)\` đặt kích thước tối đa của một STOMP message inbound ở phía client. Vì một STOMP message có thể đến qua nhiều WebSocket message, client cần buffer để ghép các phần. Giá trị mặc định là **64 KiB**.

Nếu message inbound vượt giới hạn, client phát sinh \`StompConversionException\`.

### 5.2. Outbound message size limit

Từ Spring Framework 6.2, \`setOutboundMessageSizeLimit(Integer)\` cho phép đặt giới hạn cho STOMP message outbound của client. Nếu message lớn hơn giới hạn, client chia STOMP message thành nhiều WebSocket message để bên nhận ghép lại.

Mặc định thuộc tính này không được đặt, vì vậy client không tự chia nhỏ message outbound theo giới hạn này. Tính năng chia nhỏ yêu cầu bên nhận có khả năng ghép các phần message.

Ví dụ:

\`\`\`java
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setInboundMessageSizeLimit(128 * 1024);
stompClient.setOutboundMessageSizeLimit(128 * 1024);
\`\`\`

Cấu hình trên chỉ điều chỉnh client Java. Server vẫn phải cho phép nhận message tương ứng qua \`setMessageSizeLimit\` và giới hạn WebSocket container phù hợp. Ngược lại, tăng giới hạn server không tự động tăng giới hạn inbound của client.

### 5.3. Bảng so sánh cấu hình

| Thuộc tính | Phía áp dụng | Hướng message | Mặc định Spring Framework |
| --- | --- | --- | --- |
| \`WebSocketTransportRegistration.setMessageSizeLimit\` | Server | Inbound STOMP message | 64 KiB |
| \`WebSocketTransportRegistration.setSendTimeLimit\` | Server | Outbound gửi tới từng session | 10 giây |
| \`WebSocketTransportRegistration.setSendBufferSizeLimit\` | Server | Buffer outbound của từng session | 512 KiB |
| \`WebSocketStompClient.setInboundMessageSizeLimit\` | Client Java | Inbound STOMP message | 64 KiB |
| \`WebSocketStompClient.setOutboundMessageSizeLimit\` | Client Java | Outbound STOMP message | Không đặt; không chia nhỏ theo thuộc tính này |

Không cộng hoặc thay thế các giới hạn trên cho nhau. Chúng thuộc các tầng và hướng truyền khác nhau.

## 6. Ước lượng bộ nhớ khi có nhiều client chậm

Giới hạn buffer có phạm vi theo từng WebSocket session. Khi số lượng client tăng, tổng bộ nhớ tiềm năng dành cho message chờ gửi cũng tăng theo.

Ước lượng thô:

\`\`\`text
Tổng buffer tối đa
    ≈ số session chậm × sendBufferSizeLimit mỗi session
\`\`\`

Ví dụ với 5.000 session và giới hạn 512 KiB/session:

\`\`\`text
5.000 × 512 × 1.024
= 2.621.440.000 bytes
≈ 2,44 GiB
\`\`\`

Đây là phép tính biên trên giả định tất cả session cùng đạt giới hạn. Nó chưa tính object overhead, queue metadata, bản sao payload, bộ nhớ của broker và các vùng nhớ khác. Không phải mọi session đều dùng hết buffer, nhưng phép tính giúp thấy rằng một giới hạn “nhỏ” trên từng kết nối có thể trở thành khoản tiêu thụ lớn ở quy mô hàng nghìn kết nối.

Khi thiết kế, nên xác định ngân sách bộ nhớ dành cho outbound buffering, số session tối đa, tỷ lệ client chậm và kích thước message p95/p99. Nếu nhiều session thường xuyên chạm giới hạn, cần xử lý nguyên nhân ở tốc độ phát, payload hoặc khả năng tiêu thụ của client.

## 7. Backpressure ở tầng ứng dụng

Giới hạn transport bảo vệ bộ nhớ và vòng đời session. Chúng không tự làm cho ứng dụng có backpressure nghiệp vụ hoàn chỉnh. Nếu hệ thống liên tục phát nhiều message hơn khả năng client xử lý, việc đóng session chỉ là biện pháp bảo vệ cuối cùng.

Một số cách giảm tải:

- **Giảm payload:** chỉ gửi trường cần thiết, dùng DTO nhỏ và tránh gửi cả entity hoặc cây object lớn.
- **Phân trang hoặc tải theo nhu cầu:** dữ liệu lịch sử lớn nên lấy qua REST/API phân trang hoặc một cơ chế tải có giới hạn, sau đó dùng STOMP cho event thay đổi.
- **Gộp cập nhật:** nếu client chỉ cần trạng thái mới nhất, có thể gộp nhiều thay đổi liên tiếp thành một snapshot hoặc một event tổng hợp.
- **Giới hạn tần suất:** throttle hoặc debounce các event có tần suất cao nếu nghiệp vụ cho phép.
- **Loại bỏ dữ liệu cũ:** với dữ liệu realtime dạng giá trị hiện tại, có thể bỏ các bản cập nhật đã lỗi thời trước khi gửi.
- **Tách luồng quan trọng:** tránh để event quan trọng bị chặn bởi stream telemetry hoặc tiến trình ít ưu tiên; dùng destination/queue và chính sách xử lý phù hợp.
- **Điều chỉnh subscription:** client chỉ đăng ký destination và phạm vi dữ liệu mà màn hình đang cần.
- **Chuyển payload lớn ra storage:** gửi ID hoặc URL có thời hạn để client tải file lớn qua HTTP, thay vì broadcast toàn bộ binary qua STOMP.

Chỉ bỏ message khi hợp đồng nghiệp vụ cho phép. Với event tài chính, đơn hàng hoặc lệnh điều khiển, bỏ message có thể làm sai trạng thái; cần sequence, replay hoặc xác nhận nghiệp vụ thay vì coalesce tùy tiện.

## 8. Điều chỉnh thread pool và channel

Message trong Spring STOMP được xử lý bất đồng bộ qua các channel có thread pool, đặc biệt:

- \`clientInboundChannel\`: xử lý message từ client đi vào ứng dụng.
- \`clientOutboundChannel\`: gửi message từ ứng dụng/broker tới client.

Theo tài liệu Spring, mặc định thread pool của hai channel thường được cấu hình ở mức gấp đôi số processor khả dụng. Cần điều chỉnh dựa trên loại công việc:

- Nếu handler inbound chủ yếu dùng CPU, số thread gần số processor thường là điểm bắt đầu hợp lý.
- Nếu handler inbound thường chờ database hoặc dịch vụ ngoài, có thể cần tăng số thread để giảm thời gian chờ.
- Nếu outbound có nhiều client mạng chậm, thread gửi có thể bị chiếm lâu hơn và hàng đợi outbound tăng.

Một điểm dễ nhầm trong \`ThreadPoolExecutor\`: tăng max pool size không đồng nghĩa thread pool sẽ tự tăng tới mức đó. Nếu queue có capacity mặc định rất lớn, task mới thường được xếp hàng sau khi core pool đã bận, nên pool có thể không tăng vượt core size. Cần hiểu cả core size, max size và queue capacity trước khi chỉnh.

Ví dụ điều chỉnh channel:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompChannelConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }

    @Override
    public void configureClientOutboundChannel(
            ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }
}
\`\`\`

Đây là giá trị minh họa, không phải cấu hình khuyến nghị cho mọi tải. Khi thay đổi queue capacity, cần quyết định cách ứng dụng xử lý overload/rejection và bảo đảm không làm mất các message mà nghiệp vụ yêu cầu phải giao. Điều chỉnh thread pool không thay thế \`sendTimeLimit\` hoặc \`sendBufferSizeLimit\`.

## 9. Quan sát và chẩn đoán

Spring cung cấp \`WebSocketMessageBrokerStats\` để theo dõi hoạt động của STOMP/WebSocket. Các số liệu hữu ích gồm:

- Số lượng WebSocket session đang mở và số session đã đóng.
- Số frame CONNECT, CONNECTED, DISCONNECT.
- Kích thước và trạng thái thread pool của \`clientInboundChannel\`.
- Kích thước và trạng thái thread pool của \`clientOutboundChannel\`.
- Thống kê scheduler của SockJS khi được sử dụng.

Cách diễn giải:

| Dấu hiệu | Khả năng cần kiểm tra |
| --- | --- |
| Queue inbound tăng liên tục | Handler ứng dụng chậm, query DB/HTTP blocking hoặc inbound pool không đủ |
| Queue outbound tăng | Client tiêu thụ chậm, mạng yếu hoặc server broadcast quá nhanh |
| Session đóng tăng đột biến | Có thể chạm send timeout/buffer limit, heartbeat timeout hoặc lỗi transport |
| STOMP message bị từ chối | Message vượt \`messageSizeLimit\` hoặc lỗi giao thức/converter |
| Nhiều session cùng tăng buffer | Payload quá lớn, tần suất phát cao hoặc nhiều client không theo kịp |
| CPU cao nhưng queue thấp | Xử lý CPU-bound hoặc serialize/deserialize payload tốn kém |

Nên kết hợp số liệu broker, WebSocket container, JVM heap, GC, network throughput và application metrics. Chỉ nhìn số kết nối đang mở không đủ để đánh giá sức khỏe của hệ thống.

Không ghi toàn bộ payload hoặc headers nhạy cảm vào log. Khi cần truy vết, dùng correlation ID, session ID đã được xử lý phù hợp và thống kê kích thước message.

## 10. Kiểm thử giới hạn và client chậm

Một bài kiểm thử hiệu năng nên xác nhận cả hành vi đúng và hành vi bảo vệ khi vượt giới hạn.

1. **Message nhỏ hơn giới hạn:** gửi một STOMP message bình thường và xác nhận server/client nhận đúng payload.
2. **Message sát giới hạn:** kiểm tra kích thước ngay dưới và ngay tại ngưỡng đã cấu hình.
3. **Message vượt giới hạn:** xác nhận message bị từ chối theo đúng tầng và lỗi được quan sát rõ ràng.
4. **Phân mảnh WebSocket:** gửi một STOMP message lớn được chia thành nhiều WebSocket message và xác nhận Spring ghép lại thành công.
5. **Client nhận chậm:** tạo client đọc dữ liệu có chủ ý chậm hơn tốc độ server phát; quan sát buffer, send time và việc session được đóng khi chạm giới hạn.
6. **Burst traffic:** gửi nhiều message liên tục để kiểm tra buffer có tăng không giới hạn hay không.
7. **Nhiều client:** chạy nhiều session với các mức băng thông khác nhau để đánh giá tác động của một nhóm client chậm lên các session khác.
8. **Sau khi bị đóng:** xác nhận client có thể reconnect theo chính sách ứng dụng, tạo lại subscription và đồng bộ lại dữ liệu.
9. **So sánh cấu hình:** chạy cùng workload với các ngưỡng khác nhau; so sánh throughput, p95/p99 latency, heap, số session bị đóng và queue depth.

Không nên chỉ kiểm tra happy path với một client trên localhost. Tình huống cần kiểm chứng nhất của \`sendTimeLimit\` và \`sendBufferSizeLimit\` là khi client chậm hoặc không đọc message trong khi server vẫn tiếp tục gửi.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Message STOMP lớn bị lỗi dù đã tăng giới hạn WebSocket container | \`messageSizeLimit\` của Spring vẫn thấp | Tăng \`setMessageSizeLimit\` phù hợp và kiểm tra cả giới hạn client |
| Message bị cắt hoặc không ghép được | Client/server không hỗ trợ phân mảnh như mong đợi hoặc giới hạn transport không tương thích | Kiểm tra cách chia frame của STOMP client và cấu hình WebSocket container |
| Client Java nhận lỗi chuyển đổi với message lớn | \`inboundMessageSizeLimit\` phía client thấp | Tăng \`setInboundMessageSizeLimit\` sau khi xác định kích thước hợp lệ |
| Outbound client gửi một message rất lớn | Chưa đặt \`outboundMessageSizeLimit\` hoặc receiver không hỗ trợ ghép frame | Cấu hình giới hạn client và xác nhận receiver |
| Client chậm bị ngắt | Buffer hoặc send time vượt ngưỡng | Xem lại throughput, payload, tần suất và chính sách session |
| Heap tăng khi nhiều client chậm | Tổng buffer theo session quá lớn | Giảm buffer, giảm fan-out, coalesce event và đặt giới hạn số session |
| Tăng max pool size nhưng throughput không tăng | Queue lớn khiến task được xếp hàng thay vì tạo thêm thread | Đánh giá đồng thời core/max pool và queue capacity |
| Tăng sendTimeLimit nhưng vẫn có socket treo | Giới hạn được kiểm tra khi có lần gửi tiếp theo, không thay thế socket timeout | Cấu hình timeout ở container/transport và dùng I/O không blocking |

## 12. Quy trình chọn giới hạn

Có thể dùng quy trình sau để hiệu chỉnh:

1. Đo kích thước STOMP message thực tế, bao gồm phân phối p50/p95/p99 và kích thước cực đại hợp lệ.
2. Chọn \`messageSizeLimit\` đủ cho message hợp lệ lớn nhất với khoảng dự phòng hợp lý, đồng thời giữ trần chống payload bất thường.
3. Kiểm tra giới hạn từng WebSocket message của container, proxy và client để bảo đảm các phần STOMP được truyền/ghép đúng.
4. Đo tốc độ server gửi và tốc độ client tiêu thụ; xác định thời gian một client chậm có thể giữ backlog.
5. Chọn \`sendBufferSizeLimit\` theo ngân sách heap cho mỗi session và tổng số session đồng thời.
6. Chọn \`sendTimeLimit\` theo mức chờ chấp nhận được trước khi xem session là không theo kịp.
7. Dùng load test để kiểm tra hành vi khi đạt ngưỡng và theo dõi session bị đóng.
8. Khi phải tăng giới hạn liên tục để tránh disconnect, kiểm tra lại thiết kế payload, tần suất phát và cơ chế backpressure.

Mục tiêu là cho phép message hợp lệ đi qua, giới hạn tài nguyên bị giữ bởi client chậm và giữ độ trễ trong mức hệ thống có thể chấp nhận.

## Tài liệu tham khảo chính thức

- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): thread pool, send time, send buffer và giới hạn kích thước inbound STOMP.
- [WebSocketTransportRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html): hợp đồng, đơn vị và giá trị mặc định của \`setMessageSizeLimit\`, \`setSendTimeLimit\`, \`setSendBufferSizeLimit\`.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): giới hạn inbound/outbound của \`WebSocketStompClient\`, phân mảnh message và receipt.
- [WebSocketStompClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): API \`setInboundMessageSizeLimit\` và \`setOutboundMessageSizeLimit\`.
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html): thống kê session, STOMP frame và channel executor.

**Ghi nhớ:** \`messageSizeLimit\` bảo vệ kích thước STOMP message inbound; \`sendTimeLimit\` và \`sendBufferSizeLimit\` bảo vệ việc gửi tới từng WebSocket session chậm. Giới hạn client Java và giới hạn WebSocket container là các lớp độc lập, vì vậy phải cấu hình và kiểm thử đồng bộ ở tất cả tầng liên quan.
