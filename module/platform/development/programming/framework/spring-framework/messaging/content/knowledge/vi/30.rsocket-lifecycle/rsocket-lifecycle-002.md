# Keepalive và phát hiện transport mất kết nối

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao một kết nối TCP hoặc WebSocket có thể trông như vẫn mở dù đường truyền đã hỏng.
- Mô tả vai trò của frame **KEEPALIVE** trong vòng đời một kết nối RSocket.
- Phân biệt **keepAlive interval**, **maxLifetime** và timeout của một request.
- Cấu hình keepalive qua **RSocketRequester** trong Spring và theo dõi sự kiện đóng kết nối.
- Chọn tham số phù hợp và xử lý lỗi mà không retry một cách mù quáng.

## 1. Vì sao cần phát hiện mất kết nối?

RSocket duy trì một kết nối transport để mang nhiều stream đồng thời. Một kết nối có thể đang rảnh vì ứng dụng chưa gửi request, nhưng điều đó không có nghĩa là kết nối đã chết. Ngược lại, hệ điều hành có thể vẫn xem socket là đang mở dù một đầu đã mất điện, thiết bị đổi mạng, router loại bỏ trạng thái NAT hoặc đường truyền bị black-hole.

Có hai tình huống cần phân biệt:

1. **Đóng kết nối được báo rõ ràng:** TCP nhận FIN/RST hoặc WebSocket phát tín hiệu đóng/lỗi. Transport có thể thông báo ngay cho ứng dụng.
2. **Kết nối nửa mở hoặc đường truyền im lặng:** không có tín hiệu đóng rõ ràng. Ứng dụng gửi dữ liệu nhưng không nhận được phản hồi; nếu không có traffic, việc phát hiện có thể bị trì hoãn rất lâu.

Nếu một kết nối RSocket bị mất, nhiều stream đang dùng chung kết nối đó có thể cùng thất bại. Vì vậy, ứng dụng cần biết thời điểm kết nối không còn sử dụng được để giải phóng tài nguyên, cập nhật trạng thái client và quyết định có kết nối lại hay không.

## 2. Keepalive hoạt động như thế nào trong RSocket?

Keepalive là cơ chế heartbeat ở **cấp kết nối** của giao thức RSocket. Nó tạo ra các frame điều khiển định kỳ ngay cả khi không có request nghiệp vụ. Mục đích là xác nhận đầu bên kia vẫn có thể trao đổi frame qua kết nối.

Các tham số được khai báo trong frame **SETUP**:

- **Time Between KEEPALIVE Frames:** khoảng thời gian client dự định gửi các frame **KEEPALIVE**.
- **Max Lifetime:** khoảng thời gian client cho phép không nhận được phản hồi keepalive từ server trước khi xem server là đã mất kết nối.

Một chu trình thông thường diễn ra như sau:

1. Client mở transport và gửi frame **SETUP**, trong đó có interval và max lifetime.
2. Sau khi kết nối được thiết lập, client gửi frame **KEEPALIVE** theo chu kỳ đã cấu hình.
3. Frame do client gửi có cờ **RESPOND** bật để yêu cầu đầu bên kia phản hồi.
4. Server nhận frame và gửi lại một frame **KEEPALIVE** với cờ **RESPOND** tắt. Phần data của frame được echo lại.
5. Client tiếp tục theo dõi thời gian nhận frame từ server. Nếu vượt quá **maxLifetime** mà không nhận được keepalive hợp lệ, client xem kết nối là đã chết.

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant S as RSocket server
    C->>S: SETUP(interval, maxLifetime)
    loop Theo chu kỳ interval
        C->>S: KEEPALIVE (RESPOND = true)
        S-->>C: KEEPALIVE (RESPOND = false, echo data)
    end
    Note over C: Không nhận keepalive trong maxLifetime
    Note over C: Xem peer là mất kết nối
~~~

Một số chi tiết quan trọng của frame:

- **KEEPALIVE** luôn dùng **Stream ID = 0**, vì nó liên quan đến toàn bộ connection chứ không thuộc một request stream cụ thể.
- Cờ **RESPOND** cho biết frame có yêu cầu phản hồi hay không. Khi nhận frame có cờ này, peer phải trả về một frame có cờ **RESPOND** tắt và echo data.
- Trường **Last Received Position** phục vụ cơ chế resumption. Khi không dùng resumption, trường này được đặt bằng 0.
- Client là bên gửi keepalive định kỳ theo giao thức. Server cũng có thể chủ động gửi keepalive trong một số trường hợp do ứng dụng yêu cầu.

Keepalive không cần route, payload nghiệp vụ hay một phương thức **@MessageMapping**. Nó là frame giao thức được xử lý ở tầng RSocket.

## 3. Phân biệt interval và maxLifetime

Hai tham số này giải quyết hai vấn đề khác nhau:

| Tham số | Ý nghĩa | Khi đặt quá thấp | Khi đặt quá cao |
| --- | --- | --- | --- |
| **interval** | Tần suất client gửi keepalive | Tăng frame điều khiển, CPU và mức tiêu thụ pin | Có thể không tạo traffic đủ thường xuyên để vượt qua idle timeout của mạng trung gian |
| **maxLifetime** | Thời gian chờ keepalive từ peer trước khi xem kết nối là chết | Dễ kết luận nhầm khi mạng trễ, JVM pause hoặc thiết bị tạm thời mất sóng | Phát hiện kết nối hỏng chậm, giữ tài nguyên và stream lỗi lâu hơn |

RSocket Java đặt mặc định **interval = 20 giây** và **maxLifetime = 90 giây**. Đây là giá trị mặc định của thư viện, không phải cấu hình tối ưu cho mọi môi trường. API khuyến nghị max lifetime đủ rộng để bỏ lỡ được nhiều heartbeat trước khi kết luận kết nối đã chết.

Khi lựa chọn giá trị, hãy xem xét:

- Độ trễ mạng bình thường và độ trễ tăng đột biến.
- Thời gian JVM có thể dừng do garbage collection hoặc CPU bị quá tải.
- Idle timeout của load balancer, proxy, firewall và NAT.
- Loại client: server-to-server thường có thể gửi heartbeat thường xuyên; thiết bị di động cần cân bằng giữa phát hiện nhanh và pin. Đặc tả RSocket nêu 500 ms như một khoảng hợp lý cho server-to-server và thường lớn hơn 30 giây cho mobile-to-server; đây là ví dụ định hướng, không phải quy tắc bắt buộc.
- Chi phí của việc giữ một kết nối đã chết và hậu quả của việc đóng nhầm một kết nối còn hoạt động.

Thông thường, interval phải ngắn hơn idle timeout của hạ tầng trung gian nếu mục tiêu là giữ kết nối không bị loại bỏ do im lặng. Max lifetime nên dài hơn interval đủ để chịu được nhiều lần heartbeat bị trễ hoặc thất lạc. Không nên chọn hai giá trị chỉ theo cảm tính; hãy đo trên môi trường triển khai thật.

## 4. Cấu hình keepalive trong Spring Framework

Spring cung cấp **RSocketRequester** để gửi request ở mức đối tượng. Builder cho phép cấu hình trực tiếp **io.rsocket.core.RSocketConnector** thông qua callback **rsocketConnector**.

Ví dụ dưới đây cấu hình client TCP gửi keepalive mỗi 20 giây và xem peer là mất kết nối nếu không nhận được keepalive trong 90 giây:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
class RSocketClientConfiguration {

    @Bean
    RSocketRequester rSocketRequester() {
        return RSocketRequester.builder()
                .rsocketConnector(connector ->
                        connector.keepAlive(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(90)))
                .tcp("localhost", 7000);
    }
}
~~~

Giải thích:

- **rsocketConnector(...)** cho phép tùy chỉnh connector cấp thấp của RSocket Java.
- **keepAlive(interval, maxLifeTime)** thiết lập tần suất phát frame và thời gian chờ frame từ peer.
- **tcp("localhost", 7000)** chọn transport TCP. Spring cũng hỗ trợ kết nối WebSocket bằng builder tương ứng; cấu hình keepalive vẫn thuộc connector RSocket.
- Việc gọi **tcp(...)** tạo một requester dùng chung. Kết nối thường được thiết lập khi ứng dụng bắt đầu gửi request, không nhất thiết ngay tại thời điểm tạo bean.

Nếu không cần tùy chỉnh, có thể dùng giá trị mặc định của RSocket Java. Hãy cấu hình tường minh khi cần đồng bộ timeout với hạ tầng mạng hoặc có yêu cầu rõ ràng về thời gian phát hiện mất kết nối.

## 5. Theo dõi thời điểm kết nối đóng

Cấu hình heartbeat chỉ giúp phát hiện peer không còn phản hồi. Ứng dụng vẫn cần quan sát vòng đời kết nối để ghi log, cập nhật registry hoặc kích hoạt quy trình khôi phục.

### Theo dõi kết nối đến server bằng @ConnectMapping

Ở phía server, **@ConnectMapping** xử lý frame **SETUP**. Từ **RSocketRequester** nhận được trong handler, có thể lấy RSocket đang hoạt động và đăng ký listener qua **onClose()**.

~~~java
import io.rsocket.RSocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.ConnectMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Controller;

@Controller
class RSocketConnectionObserver {

    private static final Logger log =
            LoggerFactory.getLogger(RSocketConnectionObserver.class);

    @ConnectMapping
    void onConnect(RSocketRequester requester) {
        RSocket socket = requester.rsocket();

        if (socket == null) {
            log.warn("Không lấy được RSocket đang hoạt động để theo dõi");
            return;
        }

        socket.onClose()
                .doOnError(error ->
                        log.warn("Kết nối RSocket đóng do lỗi", error))
                .doFinally(signal ->
                        log.info("Vòng đời kết nối RSocket kết thúc: {}", signal))
                .subscribe();
    }
}
~~~

**onClose()** trả về một **Mono<Void>** kết thúc khi RSocket bị đóng. Nếu kết thúc do lỗi, lỗi được phát qua **onError**; nếu đóng bình thường, publisher hoàn tất. **doFinally** chạy khi publisher kết thúc bằng complete, error hoặc cancel.

Trong ứng dụng client tạo requester bằng builder hiện đại, **requester.rsocket()** có thể trả về **null** vì requester giữ một **RSocketClient** thay vì một RSocket trực tiếp. Khi cần quan sát vòng đời client đó, dùng:

~~~java
requester.rsocketClient().onClose()
        .doOnError(error ->
                log.warn("RSocket client connection closed with error", error))
        .doFinally(signal ->
                log.info("RSocket client connection terminated: {}", signal))
        .subscribe();
~~~

Hãy đăng ký listener trong thành phần quản lý vòng đời phù hợp và bảo đảm subscription được quản lý khi ứng dụng shutdown. Không tạo một subscription mới mỗi lần gửi request.

## 6. Keepalive, request timeout và resumption không giống nhau

| Cơ chế | Câu hỏi được trả lời | Phạm vi |
| --- | --- | --- |
| Keepalive / max lifetime | Peer còn phản hồi qua kết nối RSocket không? | Toàn bộ connection |
| Request timeout | Request nghiệp vụ này có trả kết quả đúng hạn không? | Một request hoặc stream |
| Transport close/error | TCP hoặc WebSocket đã báo đóng/lỗi chưa? | Transport connection |
| Session resumption | Có thể tiếp tục session/stream sau khi transport bị ngắt không? | Session và trạng thái resume |
| Reconnect | Có thể mở một connection mới sau khi connection cũ mất không? | Connection mới |

Một keepalive thành công không chứng minh request nghiệp vụ sẽ thành công. Peer có thể vẫn trả lời frame điều khiển trong khi handler, database hoặc dịch vụ phụ thuộc đang chậm. Vì vậy, request vẫn cần timeout và xử lý lỗi riêng.

Ngược lại, một request stream thất bại không nhất thiết có nghĩa toàn bộ connection đã chết. RSocket có lỗi ở cấp stream và lỗi ở cấp connection. **RSocket.onClose()** quan sát lỗi cấp connection (Stream ID 0); lỗi nghiệp vụ trên một stream cần được xử lý tại publisher của request đó.

Keepalive cũng không tự gửi lại request hoặc khôi phục stream. Reconnect tạo một connection mới theo chính sách được cấu hình. Resumption là cơ chế riêng, cần hai đầu hỗ trợ và duy trì trạng thái phiên cần thiết. Nếu retry một request sau khi mất kết nối, hãy cân nhắc trường hợp server đã xử lý xong nhưng phản hồi bị mất; request có side effect cần idempotency key hoặc thiết kế idempotent để tránh thực hiện lặp.

## 7. Quy trình chẩn đoán khi connection bị timeout

Khi thấy lỗi keepalive hoặc connection bị đóng, kiểm tra theo thứ tự:

1. **Xác định phạm vi lỗi:** lỗi chỉ xảy ra trên một stream hay listener cấp connection **onClose()** cũng kết thúc?
2. **Đọc nguyên nhân đóng:** phân biệt lỗi transport, lỗi protocol, timeout keepalive và đóng chủ động khi shutdown.
3. **Đối chiếu thời gian:** so sánh interval, max lifetime, request timeout và idle timeout của proxy/load balancer/firewall.
4. **Kiểm tra độ trễ của tiến trình:** xem JVM pause, CPU saturation, event-loop bị block hoặc scheduler không được cấp thời gian chạy.
5. **Kiểm tra mạng:** tìm dấu hiệu đổi mạng, NAT timeout, packet loss, reset hoặc kết nối WebSocket bị proxy đóng.
6. **Quan sát frame:** khi cần phân tích sâu, bật log frame của RSocket Java ở mức DEBUG (logger **io.rsocket.FrameLogger**) trong môi trường kiểm thử có kiểm soát.
7. **Đánh giá khôi phục:** quyết định dùng reconnect, resumption hay yêu cầu client tạo session mới. Kiểm tra tính an toàn của retry đối với request có side effect.

Không nên tăng **maxLifetime** ngay khi gặp timeout mà chưa xác định nguyên nhân. Giá trị lớn có thể che giấu một đường truyền lỗi và kéo dài thời gian giữ tài nguyên. Cũng không nên giảm interval quá mạnh để bù cho một event loop đang bị block; heartbeat vẫn cần scheduler và transport hoạt động bình thường.

## 8. Các lỗi hiểu nhầm thường gặp

- **Nghĩ rằng TCP đang connected đồng nghĩa peer còn sống:** TCP có thể ở trạng thái half-open sau khi đường truyền bị đứt im lặng.
- **Nghĩ rằng có request timeout thì không cần keepalive:** request timeout chỉ phát hiện một thao tác chậm; nó không duy trì và kiểm tra một kết nối rảnh.
- **Dùng max lifetime làm timeout nghiệp vụ:** hai loại timeout có phạm vi và mục đích khác nhau.
- **Đặt max lifetime gần bằng interval:** một lần trễ hoặc thất lạc heartbeat có thể gây false positive. Cần cho phép nhiều chu kỳ bị bỏ lỡ.
- **Cho rằng keepalive tự reconnect:** keepalive phát hiện trạng thái peer; reconnect và resumption phải được cấu hình và xử lý riêng.
- **Cho rằng keepalive chứng minh toàn bộ ứng dụng khỏe:** nó xác nhận khả năng phản hồi ở tầng giao thức, không kiểm tra database, queue hay logic nghiệp vụ.
- **Retry mọi request sau khi connection đóng:** phản hồi có thể đã bị mất sau khi server thực hiện side effect. Cần idempotency hoặc cơ chế đối soát.

## 9. Tình huống minh họa

Giả sử client cấu hình interval 20 giây và max lifetime 90 giây:

- Khi kết nối ổn định, client gửi keepalive định kỳ và server phản hồi. Connection có thể vẫn được giám sát dù không có request nghiệp vụ.
- Khi router âm thầm loại bỏ đường truyền, client vẫn có thể nghĩ socket đang mở. Các frame keepalive tiếp theo không nhận được phản hồi.
- Khi vượt quá max lifetime, client kết luận peer không còn phản hồi và connection bị đánh dấu đã kết thúc theo hành vi của implementation.
- Các request/stream đang phụ thuộc connection có thể phát lỗi. Ứng dụng ghi nhận sự kiện đóng, giải phóng tài nguyên và áp dụng chính sách reconnect/resume phù hợp.
- Nếu chỉ một request vượt quá timeout trong khi **onClose()** chưa kết thúc, hãy xử lý lỗi request đó trước; đừng mặc định toàn bộ connection đã mất.

## 10. Checklist triển khai

- [ ] Đã chọn interval dựa trên loại client và idle timeout của hạ tầng.
- [ ] Max lifetime cho phép bỏ lỡ nhiều heartbeat và phù hợp với độ trễ thực tế.
- [ ] Đã kiểm tra cấu hình keepalive được gửi trong **SETUP**.
- [ ] Đã theo dõi connection close/error bằng **onClose()** ở đúng phía.
- [ ] Request nghiệp vụ vẫn có timeout riêng.
- [ ] Retry được giới hạn và an toàn với side effect; resumption được cấu hình riêng nếu cần.
- [ ] Đã thử nghiệm trường hợp đóng transport rõ ràng và trường hợp mất mạng im lặng.
- [ ] Log/metrics đủ để phân biệt stream error, connection error và timeout.

## Tài liệu tham khảo

- [RSocket Protocol — SETUP và KEEPALIVE frames](https://github.com/rsocket/rsocket/blob/master/Protocol.md#frame-setup)
- [RSocket Protocol — KEEPALIVE frame và xử lý transport chết](https://github.com/rsocket/rsocket/blob/master/Protocol.md#keepalive-frame-0x03)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [RSocket Java API — RSocketConnector.keepAlive](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
