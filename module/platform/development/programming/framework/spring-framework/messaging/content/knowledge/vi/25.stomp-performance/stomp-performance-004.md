# setPreserveReceiveOrder và thứ tự nhận theo phiên bản hỗ trợ

Trong ứng dụng Spring WebSocket/STOMP, message client gửi lên server đi qua `clientInboundChannel`. Channel này thường được xử lý bằng thread pool, vì vậy các message đã được nhận theo thứ tự trên cùng một kết nối vẫn có thể được xử lý song song và hoàn tất theo thứ tự khác. Từ Spring Framework 6.1, có thể bật `StompEndpointRegistry.setPreserveReceiveOrder(true)` để Spring đưa message của cùng một STOMP session vào `clientInboundChannel` lần lượt theo thứ tự nhận.

Đây là thiết lập cho chiều client → server. Nó khác với `MessageBrokerRegistry.setPreservePublishOrder(true)`, vốn kiểm soát thứ tự server gửi message tới client và đã có từ Spring Framework 5.1.

## 1. Vì sao thứ tự nhận có thể bị thay đổi?

Một kết nối WebSocket duy trì thứ tự dữ liệu trên cùng một connection. Tuy nhiên, sau khi Spring giải mã STOMP frame, message được gửi vào `clientInboundChannel` để tiếp tục xử lý. Channel mặc định được hỗ trợ bởi `ThreadPoolExecutor`; các task có thể chạy trên những thread khác nhau.

Ví dụ một client gửi ba lệnh liên tiếp trên cùng session:

~~~text
M1: tăng số lượng sản phẩm lên 1
M2: đổi giá trị giỏ hàng thành 200
M3: xác nhận giỏ hàng
~~~

Transport nhận M1, rồi M2, rồi M3. Nếu ba task được xử lý song song, M2 hoặc M3 có thể được xử lý trước M1. Khi đó trạng thái nghiệp vụ có thể khác với ý định của client.

Điều này đặc biệt đáng chú ý khi handler:

- Cập nhật cùng một bản ghi hoặc aggregate.
- Thay đổi trạng thái theo từng bước.
- Xử lý lệnh nối tiếp như tạo đơn hàng rồi xác nhận đơn hàng.
- Dựa vào trạng thái mà message trước vừa cập nhật.
- Ghi lịch sử hoặc sequence event cần giữ thứ tự.

Mặc định, Spring ưu tiên khả năng xử lý song song của channel. Nếu thứ tự message từ một session là yêu cầu nghiệp vụ, cần bật cơ chế giữ thứ tự tương ứng.

## 2. Bật setPreserveReceiveOrder từ Spring Framework 6.1

API `setPreserveReceiveOrder(boolean)` được bổ sung từ Spring Framework 6.1. Cấu hình thông qua `StompEndpointRegistry` trong phương thức `registerStompEndpoints`:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.setPreserveReceiveOrder(true);
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Khi đặt `true`, Spring gửi các message thuộc cùng một session tới `clientInboundChannel` từng message một theo đúng thứ tự chúng được nhận. Những session khác vẫn có thể được xử lý song song.

Nếu không gọi phương thức này hoặc đặt `false`, Spring giữ hành vi mặc định: message trên `clientInboundChannel` có thể được xử lý đồng thời và thứ tự xử lý có thể khác thứ tự nhận.

`setPreserveReceiveOrder` là cấu hình ở cấp `StompEndpointRegistry`, không phải annotation trên từng `@MessageMapping`. Nó được áp dụng cho cơ chế xử lý STOMP endpoint được đăng ký trong registry đó.

## 3. Phạm vi bảo đảm: theo từng session

Giả sử có hai client session A và B:

~~~text
Session A nhận: A1 -> A2 -> A3
Session B nhận: B1 -> B2 -> B3
~~~

Khi `setPreserveReceiveOrder(true)` được bật, Spring giữ thứ tự A1 → A2 → A3 trong session A và B1 → B2 → B3 trong session B. Hai session vẫn có thể tiến hành đồng thời; Spring không tạo một hàng đợi toàn cục buộc mọi client phải chờ nhau.

Vì vậy, phạm vi bảo đảm là:

- Giữ thứ tự nhận giữa các message trong cùng một STOMP session.
- Không thiết lập thứ tự toàn cục giữa các session khác nhau.
- Không gom nhiều session của cùng một người dùng thành một luồng tuần tự.
- Không sắp xếp lại message theo timestamp do client tự gửi.
- Không thay thế sequence number hoặc cơ chế đồng bộ nghiệp vụ khi nhiều client cùng cập nhật một tài nguyên.

Một người dùng mở hai tab trình duyệt thường có hai STOMP session khác nhau. Nếu cả hai tab gửi lệnh tới cùng một đơn hàng, `setPreserveReceiveOrder(true)` không xác định lệnh từ tab nào phải chạy trước. Ứng dụng cần quy tắc đồng bộ ở tầng nghiệp vụ cho tình huống nhiều session cùng ghi.

## 4. Phân biệt thứ tự nhận và thứ tự publish

Spring có hai tùy chọn dễ nhầm tên nhưng điều khiển hai hướng khác nhau:

| Tùy chọn | Vị trí cấu hình | Chiều message | Phiên bản hỗ trợ |
|---|---|---|---|
| `setPreserveReceiveOrder(true)` | `StompEndpointRegistry` trong `registerStompEndpoints` | Client → server, qua `clientInboundChannel` | Từ Spring Framework 6.1 |
| `setPreservePublishOrder(true)` | `MessageBrokerRegistry` trong `configureMessageBroker` | Server → client, qua `clientOutboundChannel` | Từ Spring Framework 5.1 |

### Thứ tự nhận từ client

`setPreserveReceiveOrder` xử lý tình huống server nhận M1, M2, M3 từ cùng một client session. Spring đưa chúng vào `clientInboundChannel` lần lượt để quá trình xử lý phía server giữ thứ tự nhận.

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}
~~~

### Thứ tự gửi tới client

`setPreservePublishOrder` xử lý tình huống broker phát nhiều message tới cùng một client session. Vì `clientOutboundChannel` cũng dùng thread pool, message được publish có thể tới WebSocket session theo thứ tự khác nhau. Bật tùy chọn này để Spring gửi message trong cùng session lần lượt:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

Hai tùy chọn độc lập. Nếu ứng dụng cần giữ thứ tự cả khi nhận lệnh từ client và khi gửi kết quả về client, có thể bật cả hai:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

Bật một tùy chọn không tự động bật tùy chọn còn lại. Cũng không nên bật `setPreservePublishOrder` để cố sửa thứ tự message client gửi vào; nó chỉ áp dụng cho chiều outbound.

## 5. Khác biệt theo phiên bản Spring Framework

`setPreserveReceiveOrder` có từ Spring Framework 6.1. Javadoc của `StompEndpointRegistry` ghi rõ API này được bổ sung trong phiên bản 6.1; tính năng cũng được nêu trong ghi chú phát hành Spring Framework 6.1.

| Phiên bản Spring Framework | `setPreserveReceiveOrder` | `setPreservePublishOrder` |
|---|---|---|
| 5.0 trở xuống | Chưa có | Chưa có |
| 5.1 đến 6.0.x | Chưa có | Có |
| 6.1 trở lên | Có | Có |

Nếu dự án dùng Spring Framework 6.0 hoặc thấp hơn, gọi `registry.setPreserveReceiveOrder(true)` sẽ không biên dịch vì phương thức chưa tồn tại trong API đó. `setPreservePublishOrder` đã có từ 5.1 nhưng không thay thế được chức năng nhận tuần tự.

Khi dự án dùng Spring Boot, hãy kiểm tra phiên bản Spring Framework thực tế được resolve bởi dependency management, thay vì chỉ suy luận từ phiên bản Boot hoặc một dòng version khai báo trong file build. Với Gradle có thể kiểm tra:

~~~bash
./gradlew dependencyInsight --dependency spring-websocket --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-websocket
~~~

Cần kiểm tra module `spring-websocket` đang chạy thực tế. Nếu ứng dụng bị ép một phiên bản Spring Framework cũ hơn BOM, API có thể không tồn tại dù các module khác đã được nâng cấp.

### Nếu chưa thể nâng cấp lên 6.1

Trong Spring 5.x hoặc 6.0, không có `setPreserveReceiveOrder` trong `StompEndpointRegistry`. Có thể xử lý thứ tự ở tầng ứng dụng bằng một hàng đợi tuần tự theo session, một executor tuần tự cho từng khóa/session, hoặc sequence number để phát hiện và xử lý message đến sai thứ tự.

Không nên tùy tiện đặt một executor duy nhất cho toàn bộ `clientInboundChannel` chỉ để giữ thứ tự cho từng client. Cách đó có thể tuần tự hóa mọi client trên toàn ứng dụng, tạo nút thắt cổ chai và làm giảm khả năng mở rộng. Nếu cần fallback, hãy thiết kế hàng đợi theo session hoặc theo aggregate cần bảo vệ.

## 6. Tác động hiệu năng

Giữ thứ tự đồng nghĩa các message trong cùng session không còn được xử lý song song trên `clientInboundChannel`. Điều đó giúp tránh đảo thứ tự nhưng giới hạn mức song song của một session.

Cần cân nhắc:

- Một handler chạy lâu sẽ khiến các message tiếp theo của cùng session phải chờ.
- Nếu một session gửi message với tốc độ cao hơn khả năng xử lý, hàng đợi có thể tăng độ trễ.
- Các session khác vẫn có thể dùng các thread còn lại của inbound channel.
- Tăng thread pool không làm một session được xử lý song song trở lại khi preserve receive order đang bật.
- Handler nên tránh blocking I/O kéo dài; dùng timeout, xử lý bất đồng bộ có kiểm soát hoặc đưa công việc dài sang một pipeline phù hợp.

Trong cấu hình STOMP, `clientInboundChannel` được thực thi bằng thread pool. Kích thước pool, queue capacity và loại công việc của handler vẫn quan trọng. Với workload CPU-bound, số thread nên gần số CPU khả dụng. Với workload I/O-bound có chờ database hoặc dịch vụ ngoài, cần đo và điều chỉnh phù hợp.

Đừng tăng pool size để giải quyết một handler chậm trong cùng session khi đã bật giữ thứ tự. Message của session đó vẫn phải chờ message trước hoàn thành phần xử lý đồng bộ trên channel.

## 7. Giới hạn khi xử lý bất đồng bộ và nhiều nguồn ghi

`setPreserveReceiveOrder` kiểm soát thứ tự message được đưa qua `clientInboundChannel`. Nó không tạo một transaction chung cho các handler và cũng không điều khiển mọi tác vụ bất đồng bộ mà handler khởi chạy.

Ví dụ handler nhận lệnh rồi gửi tác vụ sang executor khác:

~~~java
@MessageMapping("/orders/{orderId}/commands")
public void handle(
        @DestinationVariable String orderId,
        @Payload OrderCommand command) {

    asyncExecutor.execute(() -> orderService.apply(orderId, command));
}
~~~

Spring có thể nhận và chuyển lệnh theo thứ tự, nhưng các task trong `asyncExecutor` vẫn có thể hoàn thành theo thứ tự khác nếu executor cho phép chạy song song. Tương tự, các lời gọi HTTP bất đồng bộ, `CompletableFuture`, reactive pipeline hoặc xử lý event ngoài luồng có thể hoàn tất khác thứ tự nhận ban đầu.

Nếu thứ tự hoàn tất nghiệp vụ là yêu cầu bắt buộc, cần bảo vệ ở tầng thực thi nghiệp vụ, ví dụ:

- Dùng một hàng đợi tuần tự theo `orderId` hoặc aggregate key.
- Gắn sequence number tăng dần cho từng luồng lệnh và từ chối hoặc buffer lệnh đến sai thứ tự.
- Dùng optimistic locking/version để phát hiện cập nhật cũ.
- Dùng transaction và cơ chế khóa phù hợp khi nhiều session cùng ghi một tài nguyên.
- Thiết kế handler idempotent để message retry không gây áp dụng lặp.

Tính năng này cũng không cung cấp thứ tự giữa các server instance. Nếu nhiều node nhận message từ những session khác nhau hoặc một user kết nối tới nhiều node, cần thiết kế thứ tự và đồng bộ phân tán riêng.

## 8. Ví dụ kiểm thử thứ tự nhận

Có thể kiểm tra tính năng bằng một client STOMP gửi các lệnh đánh số tăng dần. Controller ghi lại thứ tự xử lý:

~~~java
@Controller
public class SequenceController {

    private final List<Integer> received =
            new CopyOnWriteArrayList<>();

    @MessageMapping("/sequence")
    public void receive(@Payload Integer sequence) {
        received.add(sequence);
    }

    public List<Integer> receivedMessages() {
        return List.copyOf(received);
    }
}
~~~

Client gửi liên tiếp:

~~~java
for (int sequence = 1; sequence <= 5; sequence++) {
    session.send("/app/sequence", sequence);
}
~~~

Trong integration test, đợi đủ năm message được xử lý rồi so sánh danh sách nhận với:

~~~text
[1, 2, 3, 4, 5]
~~~

Để kiểm tra đúng phạm vi:

1. Dùng một session gửi nhiều message liên tiếp và xác nhận thứ tự xử lý.
2. Chạy test khi `setPreserveReceiveOrder(false)` để hiểu rằng thread pool có thể xử lý song song; không yêu cầu mọi lần chạy đều phải đảo thứ tự vì đây là khả năng, không phải kết quả bắt buộc.
3. Bật `true` và xác nhận các message của cùng session được xử lý lần lượt.
4. Mở hai session và xác nhận chúng vẫn có thể tiến hành đồng thời.
5. Thử handler đồng bộ chậm để quan sát message sau trong cùng session phải chờ.
6. Thử handler offload công việc sang executor khác để thấy việc hoàn tất tác vụ bất đồng bộ không được tự động tuần tự hóa.
7. Nếu cần thứ tự server publish, kiểm tra riêng `setPreservePublishOrder(true)`.

Trong test thực tế, nên dùng latch hoặc điều kiện chờ có timeout thay vì `Thread.sleep` cố định. Điều đó giúp test ổn định hơn khi CI hoặc máy chạy có tải khác nhau.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Không biên dịch được `setPreserveReceiveOrder` | Đang dùng Spring Framework trước 6.1 | Kiểm tra dependency `spring-websocket`; nâng cấp lên 6.1+ hoặc dùng giải pháp tuần tự ở ứng dụng. |
| Đã bật `setPreservePublishOrder` nhưng message inbound vẫn đảo thứ tự | Đang cấu hình chiều server → client | Dùng `StompEndpointRegistry.setPreserveReceiveOrder(true)` cho client → server. |
| Message trong cùng session xử lý đúng nhưng giữa hai tab vẫn xung đột | Mỗi tab là một STOMP session riêng | Dùng khóa, version hoặc sequence theo aggregate ở tầng nghiệp vụ. |
| Handler nhận đúng thứ tự nhưng database commit khác thứ tự | Handler offload hoặc thực thi bất đồng bộ | Tuần tự hóa tại executor/service hoặc dùng transaction/version phù hợp. |
| Bật giữ thứ tự làm session có độ trễ cao | Handler đồng bộ chậm chặn message tiếp theo của session | Giảm thời gian handler, giới hạn I/O và tách công việc dài sang pipeline có thứ tự riêng. |
| Tăng thread pool nhưng một session vẫn xử lý tuần tự | Đây là hành vi chủ ý của preserve receive order | Đánh giá throughput của từng session và chỉ bật khi nghiệp vụ cần. |
| Nghĩ rằng mọi session đều chạy tuần tự toàn cục | Nhầm phạm vi per-session | Kiểm tra lại: session khác nhau vẫn có thể xử lý đồng thời. |
| Dựa vào timestamp client để suy ra thứ tự | Đồng hồ client có thể lệch và request có thể đến khác thứ tự | Dùng sequence number hoặc thứ tự nhận thực tế của cùng session. |

## 10. Checklist lựa chọn cấu hình

Trước khi bật `setPreserveReceiveOrder(true)`, hãy trả lời:

1. Nghiệp vụ có phụ thuộc vào thứ tự message từ cùng một session không?
2. Các handler có thực hiện cập nhật trạng thái nối tiếp không?
3. Có handler nào blocking hoặc giữ thread lâu không?
4. Có tác vụ bất đồng bộ được offload ra executor khác không?
5. Yêu cầu thứ tự là theo session, theo user hay theo aggregate? API này chỉ giải quyết theo session.
6. Phiên bản `spring-websocket` thực tế có phải 6.1 trở lên không?
7. Có cần giữ thứ tự publish server → client riêng bằng `setPreservePublishOrder` không?
8. Có test bao phủ cùng session, nhiều session và xử lý bất đồng bộ không?

Chỉ bật khi có yêu cầu rõ ràng. Nếu hệ thống cần tính đúng đắn giữa nhiều client cùng sửa một tài nguyên, hãy kết hợp kiểm soát thứ tự per-session với cơ chế đồng bộ và kiểm tra version ở tầng nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework Reference — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html): giải thích vì sao inbound/outbound channel có thể xử lý khác thứ tự và cách cấu hình hai tùy chọn.
- [Spring Framework 6.1.11 Javadoc — StompEndpointRegistry](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html): `setPreserveReceiveOrder(boolean)` và phạm vi giữ thứ tự theo cùng session.
- [Spring Framework 6.1.11 Javadoc — WebMvcStompEndpointRegistry](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/socket/config/annotation/WebMvcStompEndpointRegistry.html): triển khai registry của STOMP endpoint và API receive order.
- [Spring Framework 6.1 — Performance](https://docs.spring.io/spring-framework/reference/6.1/web/websocket/stomp/configuration-performance.html): thread pool của `clientInboundChannel`/`clientOutboundChannel` và ảnh hưởng hiệu năng.
- [Spring Framework 6.x — What's New](https://github.com/spring-projects/spring-framework/wiki/What's-New-in-Spring-Framework-6.x): ghi nhận tính năng `preserveReceiveOrder` được bổ sung trong Spring Framework 6.1.
