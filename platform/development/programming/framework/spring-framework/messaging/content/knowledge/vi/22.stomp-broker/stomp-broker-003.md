# TaskScheduler và heart-beat của simple broker

Trong Spring WebSocket/STOMP, simple broker có thể trao đổi heartbeat với từng STOMP client để nhận biết phiên kết nối còn hoạt động và phát hiện client đã ngừng gửi dữ liệu. Để làm việc đó, broker cần một `TaskScheduler` chạy định kỳ. Khi cấu hình `TaskScheduler` cho `enableSimpleBroker(...)`, Spring bật khả năng heartbeat; ứng dụng cũng có thể đặt rõ hai khoảng thời gian bằng `setHeartbeatValue(...)`.

Heartbeat giúp phát hiện kết nối bị treo hoặc bị ngắt mà không có frame thông báo. Nó không phải message nghiệp vụ, không thay thế ACK/RECEIPT và không biến simple broker thành message broker có lưu trữ bền vững.

## 1. Simple broker và vai trò của heartbeat

Simple broker là message broker tích hợp trong Spring Messaging. Nó nhận các yêu cầu subscribe, lưu thông tin subscription trong bộ nhớ và chuyển message tới những client có subscription khớp destination. Cấu hình thường gặp:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Client gửi message tới application destination như `/app/chat`; controller xử lý message rồi có thể gửi kết quả tới broker destination như `/topic/chat`. Simple broker giữ subscription của các phiên đang kết nối để phân phối message.

Một kết nối WebSocket có thể mất vì thiết bị ngủ, mạng chuyển đổi, proxy đóng kết nối nhàn rỗi, tiến trình client bị dừng hoặc đường truyền bị lỗi. Đôi khi ứng dụng không nhận được sự kiện đóng socket ngay lập tức. Nếu không có hoạt động nào khác, broker có thể tiếp tục giữ subscription của một phiên không còn sử dụng được.

Heartbeat là tín hiệu định kỳ ở tầng STOMP giúp hai đầu nhận biết hoạt động của nhau. Khi không có STOMP frame thông thường để gửi, đầu gửi phát một dòng kết thúc (EOL, thường là ký tự xuống dòng LF). Khi có dữ liệu STOMP khác đi qua kết nối, dữ liệu đó cũng được xem là hoạt động và có thể thay thế heartbeat riêng trong khoảng thời gian tương ứng.

Trong Spring simple broker, heartbeat có hai chiều:

- Server gửi heartbeat tới client khi server không gửi message nào khác trong khoảng đã thương lượng.
- Server theo dõi dữ liệu client gửi về. Nếu client không gửi dữ liệu trong khoảng được yêu cầu, simple broker thực hiện xử lý disconnect và dọn subscription của phiên đó.

Heartbeat không chứa destination, payload nghiệp vụ hoặc nội dung chat. Client không nhận nó như một message `MESSAGE` thông thường trong subscription.

## 2. TaskScheduler làm gì?

`TaskScheduler` là abstraction của Spring để lên lịch chạy tác vụ theo thời gian. Với simple broker, scheduler cung cấp bộ lập lịch cho tác vụ heartbeat. Tác vụ định kỳ kiểm tra trạng thái đọc/ghi của các session:

- Nếu session đã quá hạn nhận dữ liệu từ client theo khoảng heartbeat đã thương lượng, broker xử lý session như một kết nối đã disconnect.
- Nếu session đã quá hạn gửi dữ liệu từ server, broker phát heartbeat rỗng xuống client.
- Nếu message thông thường đã được trao đổi, thời điểm hoạt động tương ứng được cập nhật và heartbeat riêng không cần phát thêm ngay lúc đó.

Scheduler vì thế hỗ trợ cả việc gửi heartbeat lẫn kiểm tra hoạt động của client. Nó không tự động gửi message tới một destination và cũng không thay thế scheduler nghiệp vụ của ứng dụng.

### Mặc định khi chưa cấu hình

Theo API của `SimpleBrokerRegistration` và `SimpleBrokerMessageHandler`:

- Nếu không có `TaskScheduler`, mặc định heartbeat là `[0, 0]`, nghĩa là không gửi và không yêu cầu heartbeat.
- Khi đặt `TaskScheduler` mà chưa đặt giá trị riêng, Spring mặc định heartbeat thành `[10000, 10000]` (mili giây).
- Nếu đặt giá trị heartbeat khác 0 nhưng không cung cấp scheduler, simple broker không thể chạy tác vụ định kỳ; cấu hình như vậy không hợp lệ và broker sẽ báo lỗi khi khởi động.

Vì vậy, để bật heartbeat, cần cấu hình cả scheduler và hai giá trị mong muốn, hoặc cấu hình scheduler rồi chấp nhận mặc định 10 giây cho mỗi chiều.

## 3. Cấu hình heartbeat cho simple broker

Spring cho phép dùng scheduler đã được khai báo trong cấu hình WebSocket tích hợp sẵn. Khi inject scheduler này vào `WebSocketMessageBrokerConfigurer`, dùng `@Lazy` để tránh vòng phụ thuộc giữa cấu hình WebSocket nội bộ và lớp cấu hình của ứng dụng.

Ví dụ sau yêu cầu server gửi heartbeat tối thiểu mỗi 10 giây và mong client gửi dữ liệu mỗi 20 giây:

~~~java
package com.example.messaging;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private TaskScheduler messageBrokerTaskScheduler;

    @Autowired
    public void setMessageBrokerTaskScheduler(
            @Lazy TaskScheduler taskScheduler) {
        this.messageBrokerTaskScheduler = taskScheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableSimpleBroker("/topic/", "/queue/")
                .setHeartbeatValue(new long[] {10_000, 20_000})
                .setTaskScheduler(this.messageBrokerTaskScheduler);
    }
}
~~~

Các điểm cần hiểu trong ví dụ:

- `enableSimpleBroker("/topic/", "/queue/")` bật simple broker cho các destination có tiền tố tương ứng.
- `setHeartbeatValue(new long[] {10_000, 20_000})` đặt khoảng server gửi và khoảng server mong client gửi, đơn vị là mili giây.
- `setTaskScheduler(...)` cung cấp bộ lập lịch để simple broker thực hiện tác vụ heartbeat.
- `@Lazy` trì hoãn việc phân giải scheduler được cấu hình sẵn cho tới khi cần, tránh vòng phụ thuộc trong cấu hình WebSocket.

Nếu không cần tùy chỉnh khoảng thời gian, có thể bỏ `setHeartbeatValue(...)`; khi có scheduler, mặc định của simple broker là 10.000 ms cho cả hai giá trị.

### Dùng scheduler do ứng dụng tự khai báo

Ứng dụng cũng có thể tự tạo một bean `ThreadPoolTaskScheduler`, nhất là khi muốn kiểm soát số thread, tên thread hoặc các thiết lập vận hành. Ví dụ:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
public class MessagingSchedulerConfig {

    @Bean
    public ThreadPoolTaskScheduler messageBrokerTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
~~~

Sau đó inject bean theo tên bằng `@Qualifier("messageBrokerTaskScheduler")` và truyền vào `setTaskScheduler(...)` trong cấu hình broker. Khi scheduler là Spring bean, container quản lý vòng đời khởi tạo và dừng của nó. Không tạo một scheduler mới cho mỗi client hoặc mỗi message.

Nếu ứng dụng có nhiều bean cùng kiểu `TaskScheduler`, dùng `@Qualifier` để chọn đúng bean. Nếu dùng scheduler tích hợp sẵn của Spring, làm theo mẫu `@Lazy` ở phần trước.

## 4. Ý nghĩa của setHeartbeatValue

`setHeartbeatValue` nhận một mảng gồm đúng hai số không âm:

~~~java
.setHeartbeatValue(new long[] {10_000, 20_000})
~~~

Hai phần tử được hiểu theo góc nhìn của server:

| Phần tử | Ý nghĩa | Ví dụ |
|---|---|---|
| Phần tử thứ nhất | Khoảng tối thiểu server có thể gửi heartbeat đi | `10_000` ms = 10 giây |
| Phần tử thứ hai | Khoảng server mong muốn nhận dữ liệu/heartbeat từ client | `20_000` ms = 20 giây |

Giá trị `0` có nghĩa là tắt heartbeat theo chiều tương ứng. Ví dụ:

- `[10000, 10000]`: server có thể gửi mỗi 10 giây và mong client gửi mỗi 10 giây, trước khi xét kết quả thương lượng với client.
- `[10000, 0]`: server có thể gửi heartbeat; server không yêu cầu client gửi heartbeat.
- `[0, 20000]`: server không gửi heartbeat; server yêu cầu client gửi dữ liệu/heartbeat mỗi 20 giây.
- `[0, 0]`: tắt heartbeat cả hai chiều.

Các số này là mili giây, không phải giây. Ghi `10` có nghĩa là 10 mili giây, không phải 10 giây.

Mảng phải có đúng hai phần tử và mỗi phần tử phải không âm. Giá trị âm hoặc mảng sai kích thước là cấu hình không hợp lệ.

## 5. Thương lượng heartbeat theo giao thức STOMP

Cấu hình của Spring là khả năng và mong muốn ở phía server. Khoảng heartbeat thực tế còn phụ thuộc vào header mà client gửi khi kết nối. STOMP 1.1 trở lên dùng header `heart-beat` trong hai frame đầu phiên:

~~~text
CONNECT
accept-version:1.2
host:localhost
heart-beat:5000,10000

^@

CONNECTED
version:1.2
heart-beat:10000,20000

^@
~~~

Hai cặp số có ý nghĩa giống nhau ở cả client và server:

- Số thứ nhất: khoảng tối thiểu đầu gửi có thể bảo đảm để gửi heartbeat ra ngoài.
- Số thứ hai: khoảng đầu gửi muốn nhận heartbeat từ phía bên kia.
- `0`: đầu gửi không thể gửi heartbeat hoặc không yêu cầu nhận heartbeat, tùy vị trí của số đó.

Ký hiệu:

- Client khai báo `cx, cy` trong `CONNECT`.
- Server khai báo `sx, sy` trong `CONNECTED`.

Hai chiều được tính độc lập:

~~~text
Client -> Server:
  Không có heartbeat nếu cx = 0 hoặc sy = 0
  Nếu cả hai khác 0: khoảng thực tế = max(cx, sy)

Server -> Client:
  Không có heartbeat nếu sx = 0 hoặc cy = 0
  Nếu cả hai khác 0: khoảng thực tế = max(sx, cy)
~~~

Ví dụ client gửi `heart-beat:5000,10000`, server trả về `heart-beat:10000,20000`:

- Client → server: `max(5000, 20000) = 20000` ms, tức 20 giây.
- Server → client: `max(10000, 10000) = 10000` ms, tức 10 giây.

Do đó, `setHeartbeatValue([10000, 20000])` không bảo đảm mọi client đều nhận heartbeat đúng mỗi 10 giây và gửi đúng mỗi 20 giây. Đó là hai giá trị phía server đưa ra để thương lượng. Nếu client không hỗ trợ hoặc không yêu cầu một chiều heartbeat, chiều đó có thể bị tắt.

Nếu client không gửi header `heart-beat`, giao thức xem như `heart-beat:0,0`; khi đó không có heartbeat được thương lượng cho phiên đó.

## 6. Client cũng phải bật heartbeat

Chỉ cấu hình scheduler ở server chưa đủ để tạo heartbeat hai chiều. Client phải quảng bá khả năng gửi và nhu cầu nhận trong `CONNECT`. Với STOMP.js, có thể cấu hình các giá trị heartbeat khi tạo client:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  heartbeatIncoming: 10_000,
  heartbeatOutgoing: 10_000,
  reconnectDelay: 5_000
});

client.onConnect = () => {
  client.subscribe("/topic/notifications", message => {
    console.log(message.body);
  });
};

client.activate();
~~~

Trong STOMP.js:

- `heartbeatOutgoing` là khoảng client muốn gửi heartbeat ra server.
- `heartbeatIncoming` là khoảng client mong nhận heartbeat từ server.
- Các giá trị tính bằng mili giây.
- Heartbeat chỉ được trao đổi khi cả hai phía thương lượng một giá trị khác 0 cho chiều đó.

Nếu sử dụng `WebSocketStompClient` của Spring ở phía client, cấu hình `TaskScheduler` cho client và đặt `setDefaultHeartbeat(...)` khi cần điều chỉnh khoảng mặc định. Scheduler phía client và scheduler phía simple broker là hai cấu hình ở hai đầu kết nối; mỗi bên chịu trách nhiệm cho các tác vụ của chính mình.

## 7. Heartbeat thực sự làm gì trong một phiên?

Giả sử client và server đã thương lượng heartbeat 10 giây theo cả hai chiều.

1. Client gửi `CONNECT` với khả năng gửi và mong muốn nhận heartbeat.
2. Server trả `CONNECTED` với hai giá trị heartbeat của server.
3. Spring tính khoảng thực tế cho mỗi chiều theo quy tắc STOMP.
4. Simple broker lưu thông tin thời điểm nhận và gửi dữ liệu của session.
5. Tác vụ do `TaskScheduler` lập lịch định kỳ kiểm tra các session.
6. Nếu server không gửi message nào khác trong thời hạn ghi, broker gửi heartbeat rỗng.
7. Nếu server không nhận được dữ liệu client trong thời hạn đọc đã thương lượng, broker thực hiện xử lý disconnect và gỡ session khỏi trạng thái subscription.

Mọi frame STOMP thông thường được trao đổi trên kết nối đều thể hiện hoạt động của đầu gửi. Vì vậy, một phiên đang gửi message thường xuyên không cần thêm heartbeat rỗng ở mỗi chu kỳ. Heartbeat chủ yếu có ý nghĩa khi kết nối không có lưu lượng nghiệp vụ.

Ở mức wire protocol, heartbeat là một dòng EOL rỗng, thường là byte LF (`0x0A`). Nó không phải frame `MESSAGE`, không có header `destination` và không xuất hiện như một payload ứng dụng. Trong mã Spring, loại message nội bộ dùng để biểu diễn tín hiệu này là `SimpMessageType.HEARTBEAT`.

Khi client không gửi dữ liệu trong khoảng đã thương lượng, simple broker gọi xử lý disconnect cho session. Điều này cho phép broker loại subscription mồ côi khỏi registry. Việc phát hiện heartbeat không phải bằng chứng rằng nghiệp vụ trước đó đã được xử lý thành công; nó chỉ cho biết tình trạng hoạt động của đường truyền/session theo quy tắc giao thức.

## 8. Chọn khoảng thời gian và vận hành scheduler

Khoảng heartbeat quá ngắn làm tăng số lần đánh thức scheduler và lưu lượng điều khiển. Khoảng quá dài khiến ứng dụng phát hiện kết nối chết chậm hơn. Khi chọn giá trị, cần cân nhắc:

- Timeout nhàn rỗi của reverse proxy, load balancer, ingress hoặc firewall trên đường truyền.
- Độ trễ mạng và jitter thực tế của client.
- Thời gian thiết bị di động chuyển giữa Wi-Fi và mạng di động hoặc đi vào chế độ tiết kiệm pin.
- Số lượng kết nối đồng thời và khả năng xử lý của scheduler.
- Thời gian ứng dụng chấp nhận một session mất liên lạc trước khi dọn subscription.

Nếu proxy đóng kết nối sau 60 giây không có dữ liệu, khoảng heartbeat thực tế nên thấp hơn timeout đó và có đủ biên an toàn. Không chỉ nhìn vào giá trị cấu hình phía server: kết quả thương lượng với client mới quyết định khoảng trao đổi cuối cùng.

### Quản lý thread

Nếu dùng `ThreadPoolTaskScheduler` riêng, chọn pool size dựa trên tải và số tác vụ định kỳ của ứng dụng. Không chạy tác vụ nghiệp vụ dài hoặc blocking trên scheduler heartbeat. Một tác vụ bị nghẽn có thể làm heartbeat đến trễ và khiến các phiên khỏe mạnh bị đánh giá là mất kết nối.

Với simple broker, tác vụ heartbeat được dùng chung để kiểm tra các session đang hoạt động. Không cần tạo một thread hay scheduler riêng cho từng người dùng. Theo dõi log, số session đang kết nối, số lần disconnect và tình trạng thread khi vận hành thực tế.

Khi ứng dụng dừng, Spring quản lý vòng đời của scheduler bean. Nếu tự tạo scheduler ngoài Spring container, ứng dụng phải tự bảo đảm nó được khởi tạo và dừng đúng cách; cách đó thường không cần thiết trong cấu hình Spring thông thường.

## 9. Phân biệt heartbeat với các cơ chế khác

| Cơ chế | Mục đích | Có thay thế STOMP heartbeat không? |
|---|---|---|
| STOMP heartbeat | Kiểm tra hoạt động hai chiều ở tầng STOMP | Đây là cơ chế đang cấu hình |
| WebSocket Ping/Pong | Kiểm tra hoạt động ở tầng WebSocket transport | Không; tầng và cách quản lý khác nhau |
| TCP keepalive | Hệ điều hành kiểm tra kết nối TCP theo cấu hình socket | Không; thời gian thường dài và phụ thuộc hệ điều hành |
| STOMP RECEIPT | Xác nhận server đã xử lý một frame có yêu cầu receipt | Không; xác nhận xử lý frame, không phải kiểm tra kết nối định kỳ |
| STOMP ACK/NACK | Xác nhận client đã tiêu thụ hoặc từ chối một message | Không; liên quan đến xử lý message |
| Application event/ping | Kiểm tra logic nghiệp vụ hoặc trạng thái ứng dụng | Không; đây là thông điệp do ứng dụng tự định nghĩa |

Trong trình duyệt, JavaScript thường không trực tiếp tạo WebSocket Ping/Pong control frame. STOMP heartbeat là dữ liệu giao thức STOMP được gửi trên kết nối, vì vậy ứng dụng có thể cấu hình nó thông qua thư viện STOMP.

Không dùng heartbeat để chứng minh message đã được ghi vào database, đã được consumer xử lý hoặc sẽ được gửi lại sau khi reconnect. Những yêu cầu đó cần cơ chế ACK, persistence, retry hoặc broker phù hợp.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Không thấy heartbeat từ server | Chưa gắn `TaskScheduler`, giá trị heartbeat bằng 0 hoặc client không yêu cầu nhận | Kiểm tra scheduler, `setHeartbeatValue` và header `heart-beat` trong `CONNECTED`. |
| Broker lỗi khi khởi động | Đã đặt heartbeat khác 0 nhưng không có scheduler | Truyền `TaskScheduler` vào `setTaskScheduler`. |
| Client bị disconnect dù mạng vẫn hoạt động | Scheduler bị nghẽn, khoảng thương lượng quá ngắn hoặc client bị pause | Kiểm tra log, tải scheduler, thời gian pause và giá trị thực tế hai chiều. |
| Kết nối bị proxy đóng khi nhàn rỗi | Heartbeat thực tế dài hơn idle timeout của proxy | Giảm khoảng thương lượng và kiểm tra dữ liệu heartbeat thực sự đi qua proxy. |
| Server có scheduler nhưng client không gửi heartbeat | Client không quảng bá khả năng gửi hoặc server không yêu cầu nhận | Kiểm tra `heart-beat` trong CONNECT/CONNECTED và cấu hình client. |
| Ghi `10000` nhưng tưởng là 10 mili giây | Nhầm đơn vị | Giá trị là mili giây: 10.000 ms = 10 giây. |
| Nhầm heartbeat với message trong subscription | Heartbeat là EOL rỗng ở tầng STOMP | Không tìm heartbeat như một body của destination `/topic`. |
| Dùng heartbeat để xác nhận message đã xử lý | Nhầm tín hiệu sống của kết nối với ACK/RECEIPT | Dùng cơ chế xác nhận phù hợp cho message và nghiệp vụ. |
| Dùng nhiều TaskScheduler nhưng inject sai bean | Có nhiều bean cùng kiểu | Dùng `@Qualifier` hoặc dùng scheduler tích hợp với `@Lazy`. |

## 11. Checklist kiểm thử

Khi bật heartbeat cho simple broker, kiểm tra qua một STOMP client thật hoặc integration test:

1. Xác nhận ứng dụng khởi động với scheduler được inject thành công.
2. Kết nối bằng client có header `heart-beat` khác 0 và xác nhận server trả về giá trị trong `CONNECTED`.
3. Tính khoảng heartbeat thực tế cho cả hai chiều bằng phép `max` theo STOMP.
4. Để kết nối nhàn rỗi và quan sát heartbeat rỗng trên transport hoặc log frame ở phía client.
5. Gửi message thường xuyên để xác nhận dữ liệu STOMP thực tế cũng giữ cho kết nối được xem là đang hoạt động.
6. Ngừng gửi dữ liệu từ client trong môi trường kiểm thử có kiểm soát và xác nhận simple broker thực hiện xử lý disconnect sau thời hạn phù hợp.
7. Dừng scheduler hoặc dùng cấu hình không hợp lệ trong test cấu hình để nhận biết lỗi thiếu scheduler.
8. Kiểm tra qua proxy hoặc load balancer thật nếu môi trường triển khai có idle timeout.
9. Xác nhận reconnect tạo session và subscription mới theo logic của ứng dụng; không giả định heartbeat tự khôi phục subscription cũ.

Nên kiểm thử cả hai chiều. Một client có thể nhận heartbeat đều nhưng không gửi heartbeat; trường hợp đó chỉ chứng minh chiều server → client đang hoạt động. Tương tự, client gửi đều nhưng không nhận được phản hồi không chứng minh chiều server → client khỏe mạnh.

## Tài liệu tham khảo

- [Spring Framework Reference — Simple Broker](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/handle-simple-broker.html): vai trò simple broker, cấu hình `TaskScheduler` và ví dụ bật heartbeat.
- [Spring Framework 6.1.11 Javadoc — SimpleBrokerRegistration](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/simp/config/SimpleBrokerRegistration.html): `setHeartbeatValue`, `setTaskScheduler` và giá trị mặc định.
- [Spring Framework 6.1.11 Javadoc — SimpleBrokerMessageHandler](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/simp/broker/SimpleBrokerMessageHandler.html): cấu hình scheduler và heartbeat ở broker handler.
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/client.html): cấu hình heartbeat phía `WebSocketStompClient`.
- [STOMP 1.2 Specification — Heart-beating](https://stomp.github.io/stomp-specification-1.2.html#Heart-beating): header `heart-beat`, quy tắc thương lượng hai chiều và tín hiệu EOL.
