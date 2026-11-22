# @SubscribeMapping và phản hồi trực tiếp khi đăng ký STOMP

## 1. Vấn đề mà annotation giải quyết

Trong Spring Framework, WebSocket cung cấp kết nối hai chiều, còn STOMP định nghĩa các frame trao đổi trên kết nối đó. Khi client gửi frame `SUBSCRIBE`, ứng dụng có thể cần trả ngay một ảnh chụp dữ liệu ban đầu để dựng giao diện. Sau đó, client tiếp tục nhận các sự kiện mới qua một destination do message broker quản lý.

`@SubscribeMapping` dành cho trường hợp đầu tiên: ánh xạ một frame STOMP `SUBSCRIBE` tới một phương thức trong `@Controller`. Nếu phương thức trả về một giá trị và không khai báo `@SendTo` hoặc `@SendToUser`, Spring gửi kết quả trực tiếp về đúng client đã đăng ký, qua `clientOutboundChannel`, không chuyển kết quả qua `brokerChannel`. Vì vậy, đây là một lần trao đổi request–reply gắn với thao tác đăng ký, phù hợp để lấy dữ liệu khởi tạo.

Điểm cần nhớ: `@SubscribeMapping` không tạo luồng phát sự kiện liên tục. Broker không lưu subscription ở destination ứng dụng này để dùng cho các lần broadcast sau. Nếu client cần cập nhật liên tục, nó phải đăng ký thêm một destination broker như `/topic/jobs`.

## 2. Phân biệt SUBSCRIBE, SEND và các annotation

| Tác nhân | Frame STOMP | Cách Spring xử lý thường dùng | Kết quả mặc định |
| --- | --- | --- | --- |
| Client muốn nhận snapshot ban đầu | `SUBSCRIBE` | `@SubscribeMapping` | Trả trực tiếp về client gửi frame |
| Client gửi lệnh hoặc dữ liệu | `SEND` | `@MessageMapping` | Giá trị trả về được gửi qua broker để phân phối tới subscriber |
| Client muốn nhận sự kiện liên tục | `SUBSCRIBE` | Message broker, ví dụ destination `/topic/**` | Broker lưu subscription và phân phối các MESSAGE phù hợp |
| Controller cần chọn destination đầu ra | Giá trị trả về từ handler | `@SendTo` | Gửi qua broker tới destination được chỉ định |
| Controller cần gửi tới destination riêng của user | Giá trị trả về từ handler | `@SendToUser` | Gửi qua broker theo user destination |

`@SubscribeMapping` là annotation ở cấp phương thức và chỉ dành cho STOMP over WebSocket. Nó có thể kết hợp với `@MessageMapping` ở cấp lớp để dùng chung tiền tố đường dẫn. Ví dụ:

- Cấu hình tiền tố ứng dụng là `/app`.
- Lớp controller có `@MessageMapping("/jobs")`.
- Phương thức có `@SubscribeMapping("/initial-state")`.
- Client gửi `SUBSCRIBE` tới `/app/jobs/initial-state`.

Spring bỏ tiền tố ứng dụng `/app` trước khi so khớp mapping. Phần còn lại `/jobs/initial-state` được ghép từ mapping cấp lớp và mapping cấp phương thức.

## 3. Cấu hình STOMP tối thiểu

Ví dụ dưới đây dùng endpoint WebSocket `/ws`, tiền tố dành cho controller là `/app`, còn broker đơn giản nhận các destination bắt đầu bằng `/topic` hoặc `/queue`.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Hai loại destination có vai trò khác nhau:

- `/app/**`: frame hướng tới ứng dụng. Các frame `SEND` có thể được xử lý bởi `@MessageMapping`; frame `SUBSCRIBE` có thể được xử lý bởi `@SubscribeMapping`.
- `/topic/**` và `/queue/**`: destination của broker trong ví dụ. Broker quản lý subscription để phân phối các thông điệp về sau.

Endpoint `/ws` là địa chỉ bắt tay WebSocket; nó không phải destination STOMP. Client kết nối WebSocket tới endpoint này, sau đó mới gửi các frame STOMP có destination riêng.

## 4. Ví dụ: trả snapshot khi client đăng ký

Giả sử giao diện cần tải danh sách công việc ngay khi mở màn hình. Ta tạo một phương thức `@SubscribeMapping` trả snapshot của người dùng hiện tại.

Các DTO dùng record của Java 17. Đặt mỗi `public record` trong tệp riêng, hoặc khai báo chúng dưới dạng kiểu lồng trong controller.

```java
import java.util.List;

public record JobView(
        String id,
        String name,
        String status
) {}

public record JobSnapshot(
        long version,
        List<JobView> jobs
) {}
```

Controller:

```java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SubscribeMapping;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/jobs")
public class JobController {

    private final JobService jobService;

    public JobController(JobService jobService) {
        this.jobService = jobService;
    }

    @SubscribeMapping("/initial-state")
    public JobSnapshot initialState(Principal principal) {
        return jobService.snapshotFor(principal.getName());
    }
}
```

`JobService` là service do ứng dụng cung cấp và được Spring inject. Phương thức `snapshotFor` nên trả một DTO rõ ràng, chứa đúng dữ liệu mà client được phép xem. Đây là ví dụ thành phần Spring, không phải một chương trình độc lập có thể chạy chỉ bằng `javac`: nó cần Spring Messaging/WebSocket, cấu hình STOMP, một bean `JobService` và cấu hình chuyển đổi message của ứng dụng.

Khi client đăng ký `/app/jobs/initial-state`:

1. Client đã kết nối STOMP qua WebSocket `/ws`.
2. Client gửi frame `SUBSCRIBE` với destination `/app/jobs/initial-state`.
3. Spring nhận frame trên `clientInboundChannel`, nhận diện tiền tố ứng dụng `/app`, rồi tìm handler theo đường dẫn `/jobs/initial-state`.
4. Spring gọi `initialState`. Đối số `Principal` đại diện cho người dùng đã được xác thực gắn với phiên WebSocket.
5. Giá trị `JobSnapshot` được chuyển thành payload qua `MessageConverter` thích hợp, ví dụ JSON converter nếu ứng dụng đã cấu hình.
6. Spring gửi message phản hồi qua `clientOutboundChannel` về kết nối của client vừa đăng ký. Kết quả không đi qua broker để broadcast cho các client khác.

Nếu phương thức trả `void` hoặc không tạo giá trị phản hồi, client không nhận được payload snapshot từ phương thức đó.

## 5. Client STOMP nhận phản hồi

Ví dụ dùng thư viện JavaScript `@stomp/stompjs`. Đoạn mã giả định server đã bật endpoint `/ws` và trả payload JSON.

```javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
  brokerURL: 'ws://localhost:8080/ws'
});

client.onConnect = () => {
  client.subscribe('/app/jobs/initial-state', frame => {
    const snapshot = JSON.parse(frame.body);
    renderSnapshot(snapshot);
  });
};

client.activate();
```

Callback của subscription nhận frame `MESSAGE`; phần `frame.body` là payload được server gửi về. Nếu ứng dụng dùng SockJS thay cho WebSocket thuần, cấu hình client bằng `webSocketFactory` theo endpoint SockJS đã đăng ký.

Tên destination phía client phải khớp chính xác với cấu hình tiền tố và mapping phía server. Với ví dụ trên, đăng ký `/jobs/initial-state` mà thiếu `/app`, hoặc đăng ký `/app/initial-state` mà thiếu phần `/jobs`, sẽ không khớp handler đã khai báo.

## 6. Kết hợp snapshot ban đầu với cập nhật liên tục

Một màn hình thường cần cả hai loại dữ liệu:

- Snapshot hiện tại khi mở màn hình: `@SubscribeMapping` trên destination ứng dụng.
- Các thay đổi phát sinh sau đó: subscription tới destination broker như `/topic/jobs`.

Khai báo DTO cho lệnh và sự kiện:

```java
public record JobCommand(String name) {}

public record JobEvent(
        long version,
        String type,
        String jobId
) {}
```

Thêm phương thức sau vào cùng lớp `JobController` ở phần trên:

```java
@MessageMapping("/publish")
@SendTo("/topic/jobs")
public JobEvent publish(JobCommand command, Principal principal) {
    return jobService.publish(principal.getName(), command);
}
```

Client gửi lệnh bằng frame `SEND` tới `/app/jobs/publish`; broker phân phối kết quả tới các client đang đăng ký `/topic/jobs`:

```javascript
client.subscribe('/topic/jobs', frame => {
  const event = JSON.parse(frame.body);
  renderEvent(event);
});

client.publish({
  destination: '/app/jobs/publish',
  body: JSON.stringify({ name: 'Backup' })
});
```

Phương thức `publish` là phần bổ sung cho lớp `JobController`; khi ghép mã, giữ một khai báo `@MessageMapping("/jobs")` ở cấp lớp và đặt các phương thức bên trong lớp đó. `@SendTo("/topic/jobs")` yêu cầu broker xử lý message đầu ra. Nếu bỏ `@SendTo` khỏi phương thức `@SubscribeMapping`, hành vi mặc định vẫn là trả trực tiếp cho client.

Khi client cần tránh khoảng trống giữa snapshot và luồng sự kiện, phải thiết kế thứ tự đồng bộ có chủ đích. Với broker hỗ trợ STOMP receipt, client có thể đợi receipt xác nhận subscription tới `/topic/jobs` đã được broker lưu rồi mới yêu cầu snapshot. Broker đơn giản tích hợp sẵn của Spring không hỗ trợ receipt. Trong trường hợp đó, nên dùng version/sequence trong snapshot và event, hoặc cơ chế replay/catch-up ở tầng ứng dụng, để phát hiện và bù các sự kiện bị bỏ lỡ. Chỉ gọi `subscribe()` trước `SUBSCRIBE` snapshot không tự nó tạo ra bảo đảm đồng bộ.

## 7. Tham số phương thức và dữ liệu trả về

`@SubscribeMapping` hỗ trợ cùng nhóm đối số như `@MessageMapping`. Các đối số thường hữu ích:

| Đối số | Công dụng |
| --- | --- |
| `Principal` | Lấy danh tính đã xác thực của phiên WebSocket |
| `@DestinationVariable` | Lấy biến được trích từ destination |
| `@Header("...")` | Đọc một header cụ thể |
| `@Headers` | Nhận toàn bộ headers trong một tham số kiểu `Map` |
| `Message` hoặc `MessageHeaders` | Truy cập message và headers đầy đủ |
| `SimpMessageHeaderAccessor` hoặc `StompHeaderAccessor` | Đọc headers qua API accessor có kiểu |
| `@Payload` | Đọc payload đã được MessageConverter chuyển đổi |

Ví dụ lấy snapshot cho một phòng cụ thể:

```java
@SubscribeMapping("/rooms/{roomId}/snapshot")
public RoomSnapshot roomSnapshot(
        @DestinationVariable UUID roomId,
        Principal principal) {
    return roomService.snapshotFor(roomId, principal.getName());
}
```

Client đăng ký `/app/rooms/42/snapshot`; Spring chuyển phần `42` thành giá trị `roomId` theo kiểu tham số. Mapping hỗ trợ mẫu đường dẫn và biến destination. Nếu lớp có `@MessageMapping("/jobs")`, tiền tố lớp cũng được ghép vào đường dẫn phương thức.

Frame `SUBSCRIBE` thường không có body. Vì vậy, không nên thiết kế snapshot dựa vào một JSON payload gửi kèm SUBSCRIBE. Hãy lấy dữ liệu cần thiết từ destination, headers được kiểm soát hoặc `Principal`; nếu cần gửi một lệnh có body, dùng frame `SEND` và `@MessageMapping`.

Giá trị trả về phải được chuyển đổi bởi một `MessageConverter` phù hợp. DTO là lựa chọn tốt vì nó tạo hợp đồng dữ liệu ổn định, dễ kiểm tra và tránh vô tình phát ra entity nội bộ. Nếu cần định tuyến qua broker thay vì trả trực tiếp, có thể gắn `@SendTo` hoặc `@SendToUser`; hai annotation này thay đổi đường đi mặc định của kết quả.

## 8. Phân biệt phản hồi ứng dụng và STOMP receipt

Đây là hai loại thông điệp khác nhau:

- Phản hồi từ `@SubscribeMapping` là payload nghiệp vụ, thường được gửi dưới dạng frame `MESSAGE`, ví dụ snapshot JSON.
- STOMP receipt là xác nhận ở cấp giao thức rằng broker đã xử lý frame có yêu cầu receipt. Nó không chứa snapshot nghiệp vụ và không thay thế kết quả của controller.

Nếu yêu cầu là “đã có dữ liệu ban đầu”, hãy kiểm tra payload `MESSAGE`. Nếu yêu cầu là “broker đã lưu subscription và sẵn sàng phân phối broadcast”, hãy dùng receipt khi broker hỗ trợ hoặc cơ chế xác nhận tương đương. Đừng dùng việc nhận snapshot để suy ra rằng subscription broker cho một destination khác đã sẵn sàng.

Không ánh xạ controller và broker vào cùng một tiền tố destination nếu không chủ ý để cả hai cùng xử lý. Nếu cùng xử lý một subscription, hai bên nhận message độc lập và song song; không có bảo đảm bên nào chạy trước. Điều này có thể tạo ra hành vi khó đoán khi vừa mong controller trả snapshot, vừa mong broker lưu cùng subscription để broadcast.

## 9. Bảo mật và độ tin cậy

- Xác thực kết nối WebSocket và dùng `Principal` do server cung cấp để xác định người dùng. Không tin một `userId` do client tự gửi trong header hoặc destination nếu chưa kiểm tra quyền.
- Cấu hình authorization cho các frame inbound, đặc biệt quyền `SUBSCRIBE` tới destination `/app/**` và các destination broker như `/topic/**`. Phản hồi trực tiếp của `@SubscribeMapping` không phải lý do để bỏ kiểm tra quyền truy cập.
- Kiểm tra quyền đọc trên từng tài nguyên. Ví dụ, người dùng chỉ được yêu cầu snapshot của phòng mà họ là thành viên.
- Chỉ trả DTO chứa trường cần thiết; không trả entity hoặc dữ liệu nội bộ có thể làm lộ thông tin.
- Xử lý lỗi nghiệp vụ rõ ràng. Có thể dùng `@MessageExceptionHandler` trong controller hoặc `@ControllerAdvice` cho phạm vi rộng hơn để chuẩn hóa lỗi message.
- Mỗi frame SUBSCRIBE mới có thể gọi handler thêm một lần, bao gồm khi client reconnect hoặc tạo subscription mới. Tránh giả định phương thức chỉ chạy một lần trong vòng đời người dùng; cân nhắc cache, giới hạn tần suất và chi phí truy vấn.
- Nếu snapshot và event có thể thay đổi đồng thời, đưa version/sequence vào payload để client phát hiện dữ liệu cũ, trùng hoặc thiếu.

## 10. Kiểm thử đúng hành vi

Unit test gọi trực tiếp phương thức Java chỉ kiểm tra logic bên trong, không chứng minh Spring đã ánh xạ đúng frame STOMP hoặc gửi phản hồi đúng đường. Nên có kiểm thử ở tầng messaging hoặc end-to-end:

1. Kết nối client tới endpoint WebSocket và hoàn tất STOMP CONNECT.
2. Gửi `SUBSCRIBE` tới `/app/jobs/initial-state`; xác nhận handler được gọi và client nhận đúng snapshot.
3. Mở một phiên client thứ hai; xác nhận snapshot trực tiếp của phiên thứ nhất không bị broadcast sang phiên thứ hai.
4. Đăng ký `/topic/jobs`, gửi `SEND` tới `/app/jobs/publish`, rồi xác nhận broker phân phối event tới các subscriber phù hợp.
5. Kiểm tra trường hợp chưa đăng nhập hoặc không có quyền đọc tài nguyên.
6. Ngắt kết nối rồi kết nối lại; xác nhận client có thể yêu cầu snapshot mới và xử lý version/sequence đúng.
7. Nếu dùng receipt, kiểm thử với đúng loại broker đang chạy; không giả định simple broker hỗ trợ receipt.

Spring hỗ trợ kiểm thử handler bằng cách gửi message vào `clientInboundChannel` với cấu hình Spring thực tế hoặc dựng `SimpAnnotationMethodMessageHandler` tối thiểu. Kiểm thử end-to-end có thể chạy server WebSocket nhúng và kết nối một STOMP client. Hai cách kiểm thử bổ sung cho nhau: kiểm thử server-side nhanh và tập trung; kiểm thử end-to-end xác nhận cả giao thức, cấu hình endpoint, mapping và đường gửi message.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Handler không được gọi | Client dùng sai destination hoặc thiếu tiền tố `/app`/mapping cấp lớp | Đối chiếu `setApplicationDestinationPrefixes`, `@MessageMapping` cấp lớp và `@SubscribeMapping` cấp phương thức |
| Handler không chạy khi client gửi SEND | `@SubscribeMapping` chỉ nhận SUBSCRIBE | Dùng `@MessageMapping` cho frame SEND |
| Client không nhận snapshot | Handler trả `void`, lỗi xảy ra khi truy vấn, hoặc MessageConverter không chuyển đổi được DTO | Kiểm tra log handler, exception handler và converter |
| Client khác cũng nhận dữ liệu khởi tạo | Kết quả bị gửi qua broker do có `@SendTo`/`@SendToUser`, hoặc destination bị cấu hình chồng lấn | Kiểm tra annotation đầu ra và các tiền tố broker/controller |
| Không nhận được event sau snapshot | Client chỉ đăng ký destination `/app/**`, nơi không lưu subscription broadcast | Đăng ký thêm destination broker như `/topic/jobs` |
| Có lúc mất event giữa snapshot và live update | Chưa đồng bộ thời điểm broker lưu subscription với lúc lấy snapshot | Dùng receipt nếu broker hỗ trợ; nếu không, dùng version/sequence và catch-up |
| Snapshot trả dữ liệu của người khác | Tin danh tính từ dữ liệu client gửi hoặc thiếu kiểm tra quyền tài nguyên | Dùng Principal đã xác thực và kiểm tra quyền ở service |

## 12. Quy trình chọn đúng cơ chế

- Chỉ cần trả một snapshot ngay khi client đăng ký: dùng `@SubscribeMapping`.
- Client gửi lệnh hoặc dữ liệu để server xử lý: dùng `@MessageMapping`.
- Server cần phát sự kiện tới nhiều client hoặc các subscriber của một destination: dùng broker destination và `@SendTo` hoặc `SimpMessagingTemplate`.
- Server cần gửi tới một user cụ thể: dùng user destination, thường kết hợp `@SendToUser` hoặc `SimpMessagingTemplate.convertAndSendToUser`.
- Cần xác nhận broker đã lưu subscription: dùng STOMP receipt nếu broker hỗ trợ; đây không phải nhiệm vụ của `@SubscribeMapping`.

## Tài liệu tham khảo chính thức

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): mapping, đối số, giá trị trả về, hành vi riêng của `@SubscribeMapping`, receipt và xử lý exception.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): vai trò của `clientInboundChannel`, `clientOutboundChannel`, `brokerChannel`, tiền tố ứng dụng và luồng broker.
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html): kiểm soát quyền đối với message STOMP.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): kiểm thử handler ở server-side và kiểm thử end-to-end.
- [SubscribeMapping Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/annotation/SubscribeMapping.html): phạm vi annotation và hợp đồng API.

**Ghi nhớ:** `@SubscribeMapping` xử lý một frame SUBSCRIBE và mặc định trả snapshot trực tiếp về client đã gửi frame đó. Broker chỉ tham gia khi ta chủ động định tuyến kết quả qua `@SendTo`/`@SendToUser`, hoặc khi client đăng ký một destination broker riêng để nhận các cập nhật tiếp theo.
