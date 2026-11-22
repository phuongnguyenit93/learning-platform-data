# Readiness của ứng dụng khi broker hoặc transport chưa sẵn sàng

## 1. Readiness là gì?

Readiness mô tả một instance hiện có đủ điều kiện nhận thêm công việc hay chưa. Với ứng dụng Spring Messaging, điều này phụ thuộc vào khả năng thực hiện workload mà instance được giao: nhận HTTP request tạo message, publish tới broker, tiêu thụ queue, hoặc gọi một peer qua RSocket.

Một tiến trình có thể vẫn chạy bình thường nhưng chưa thể phục vụ workload. Ví dụ:

- Spring ApplicationContext đã khởi tạo, HTTP server đang lắng nghe, nhưng JMS broker chưa khởi động.
- Ứng dụng đã tạo được `JmsTemplate`, nhưng lần gửi đầu tiên thất bại vì broker chưa nhận kết nối.
- `@JmsListener` đã được đăng ký trong Spring, nhưng listener container chưa kết nối được tới destination.
- Ứng dụng đã tạo một `RSocketRequester`, nhưng peer ở xa không thể truy cập.
- Broker đã phục hồi, nhưng consumer chưa đăng ký lại subscription hoặc chưa hoàn tất bước khởi tạo cần thiết.

Readiness giúp nền tảng triển khai biết instance nào có thể nhận traffic hoặc workload mới. Nó là tín hiệu vận hành, không phải cơ chế tự sửa kết nối. Spring JMS, JMS provider, RSocket client và chính sách retry vẫn chịu trách nhiệm phục hồi giao tiếp.

Cần phân biệt ba khái niệm:

- **Liveness:** tiến trình còn hoạt động và có khả năng tự tiếp tục hay không. Nếu liveness thất bại, Kubernetes có thể khởi động lại container.
- **Readiness:** instance có nên được nhận thêm traffic/workload hay không. Nếu readiness thất bại, Kubernetes loại instance khỏi các endpoint sẵn sàng.
- **Startup probe:** ứng dụng đã qua giai đoạn khởi động ban đầu hay chưa. Probe này giúp tránh việc Kubernetes kết luận instance chết khi startup vốn mất nhiều thời gian.

Một broker tạm thời không khả dụng thường là vấn đề readiness hoặc degraded state. Không nên biến mọi lỗi kết nối bên ngoài thành liveness failure, vì restart hàng loạt instance có thể tạo thêm áp lực lên broker vừa gặp sự cố.

## 2. Xác định broker hoặc transport có bắt buộc không

Trước khi đưa một dependency vào readiness, cần xác định nó có thiết yếu với chức năng instance đang cung cấp hay không.

| Tình huống | Readiness nên phản ánh |
|---|---|
| Ứng dụng nhận command HTTP rồi bắt buộc publish JMS để hoàn tất request | Chưa sẵn sàng nếu không thể publish theo cam kết API |
| Ứng dụng chỉ tiêu thụ một queue bắt buộc để thực hiện chức năng chính | Chưa sẵn sàng nếu broker hoặc consumer subscription chưa hoạt động |
| Ứng dụng gửi email qua queue tùy chọn, có thể ghi outbox và xử lý sau | Có thể vẫn sẵn sàng; hiển thị trạng thái degraded và theo dõi backlog |
| RSocket peer là dependency bắt buộc cho mọi request | Chưa sẵn sàng nếu không thể thực hiện lời gọi cần thiết tới peer |
| RSocket chỉ phục vụ một tính năng phụ có fallback | Có thể vẫn sẵn sàng; chỉ tính năng đó trả degraded/fallback |
| Broker dùng chung cho tất cả replica và đang mất kết nối | Cần cân nhắc việc rút tất cả replica khỏi traffic; có thể xử lý lỗi ở tầng gọi nếu ứng dụng có fallback |

Không phải cứ broker ngừng hoạt động là toàn bộ ứng dụng phải ngừng nhận HTTP traffic. Nếu ứng dụng vẫn có thể xử lý truy vấn, ghi nhận yêu cầu vào outbox hoặc cung cấp fallback hợp lệ, readiness có thể vẫn là accepting traffic. Điều quan trọng là response của ứng dụng phải trung thực với cam kết nghiệp vụ: không trả thành công cho một thao tác mà hệ thống chưa lưu hoặc chưa tiếp nhận an toàn.

Với một instance chạy nhiều chức năng, có thể tách readiness theo nhóm workload hoặc endpoint. Một dependency chỉ nên ảnh hưởng tới nhóm nào thực sự cần dependency đó.

## 3. Readiness trong vòng đời Spring Boot

Một vòng đời điển hình có các bước:

1. JVM và Spring ApplicationContext khởi động.
2. Bean, cấu hình, connection factory, listener container và transport được tạo.
3. Spring thực hiện các startup task cần thiết.
4. Ứng dụng chuyển từ `REFUSING_TRAFFIC` sang `ACCEPTING_TRAFFIC` khi đã hoàn tất startup.
5. Trong lúc chạy, broker/peer có thể mất kết nối. Instance đánh giá lại khả năng nhận workload.
6. Khi dependency thiết yếu phục hồi và các listener/transport cần thiết hoạt động trở lại, instance có thể nhận traffic.
7. Khi shutdown, instance chuyển sang refusing traffic trước khi dừng các listener và giải phóng resource.

Spring Boot quản lý trạng thái availability thông qua `ApplicationAvailability`. Các trạng thái readiness thường dùng là:

- `ReadinessState.REFUSING_TRAFFIC`
- `ReadinessState.ACCEPTING_TRAFFIC`

Actuator cung cấp `ReadinessStateHealthIndicator` để đưa trạng thái này vào health endpoint. Ứng dụng có thể cập nhật trạng thái bằng `AvailabilityChangeEvent`.

Lưu ý: việc ApplicationContext đã khởi tạo không tự chứng minh broker hoặc remote peer đã sẵn sàng. Startup readiness mặc định chủ yếu phản ánh vòng đời ứng dụng; dependency bên ngoài cần được đánh giá riêng.

## 4. Liveness và readiness không được dùng thay cho nhau

### 4.1. Liveness không phụ thuộc broker

Liveness nên kiểm tra khả năng tự vận hành của process: event loop hoặc web server có đáp ứng, thread quan trọng có bị treo, ứng dụng có rơi vào trạng thái không thể tự phục hồi hay không.

Nếu broker mất kết nối:

- Liveness thường vẫn là healthy.
- Listener container có thể tiếp tục thử kết nối lại.
- Publisher có thể ghi nhận lỗi hoặc lưu yêu cầu vào outbox.
- Readiness được quyết định theo việc broker có thiết yếu cho workload hay không.

Nếu đưa JMS health vào liveness, broker downtime có thể làm Kubernetes restart toàn bộ pod. Các pod vừa khởi động lại lại cùng kết nối tới broker đang quá tải hoặc chưa phục hồi, tạo ra vòng lặp restart và reconnect.

### 4.2. Readiness phản ánh khả năng nhận workload

Readiness có thể bao gồm trạng thái ứng dụng và một số dependency bắt buộc. Nếu broker là điều kiện để instance nhận request mới, readiness cần kiểm tra broker hoặc trạng thái kết nối tương đương.

Nếu dependency có fallback, circuit breaker hoặc outbox đủ bảo đảm, có thể giữ instance ready và trả lỗi/degraded cho chức năng bị ảnh hưởng.

### 4.3. Startup probe cho ứng dụng khởi động lâu

Nếu ứng dụng cần thời gian dài để tạo listener, khởi tạo schema, đăng ký subscription hoặc tải cấu hình, Kubernetes có thể dùng `startupProbe` để không đánh giá liveness quá sớm. Readiness vẫn phải từ chối traffic cho tới khi startup hoàn tất.

Startup probe không thay thế readiness. Nó chỉ điều chỉnh cách nền tảng quan sát giai đoạn khởi động.

## 5. Spring Boot Actuator và Kubernetes probes

### 5.1. Bật health probes

Khi dùng Spring Boot Actuator, các endpoint thường có dạng:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Spring Boot tự quản lý availability state và cung cấp health group tương ứng khi probes được bật. Có thể cấu hình rõ ràng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when-authorized
~~~

Mặc định, Spring Boot không tự thêm tất cả external health indicator vào readiness group. Nếu cần kiểm tra JMS broker, phải đưa indicator tương ứng vào group.

### 5.2. Đưa JMS health vào readiness

Spring Boot có JMS health indicator với ID `jms` khi cấu hình JMS và Actuator phù hợp. Indicator này kiểm tra khả năng kết nối tới broker qua `ConnectionFactory`. Nó không mặc định nằm trong readiness group.

Nếu broker là dependency bắt buộc, có thể cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,jms
      show-details: when-authorized
~~~

Khi broker không thể truy cập, `jms` có thể báo `DOWN`, làm readiness group không đạt trạng thái healthy. Khi broker phục hồi và kiểm tra thành công, group có thể trở lại healthy.

Tên package của JMS health indicator thay đổi theo major version Spring Boot. Hãy dùng API thuộc đúng phiên bản dự án; Boot 3.x và Boot 4.x có package khác nhau.

**JMS health không chứng minh toàn bộ message flow hoạt động.** Kết nối tới broker thành công chưa chắc destination tồn tại, user có quyền publish/consume, listener đã subscribe, selector đúng hoặc consumer xử lý message được. Nếu các điều kiện đó là yêu cầu bắt buộc, cần bổ sung kiểm tra riêng phù hợp với workload.

### 5.3. Kubernetes probe

Ví dụ cấu hình rút gọn:

~~~yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2

startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30
~~~

Các con số chỉ là ví dụ; cần điều chỉnh theo thời gian khởi động, timeout, chu kỳ reconnect và SLA. Probe phải trả lời nhanh và không tạo thêm tải lớn cho broker.

Nếu management endpoint chạy trên port riêng, probe có thể kiểm tra management server thành công trong khi main server không nhận kết nối được. Có thể bật additional paths trên main server port:

~~~yaml
management:
  endpoint:
    health:
      probes:
        add-additional-paths: true
~~~

Khi đó Spring Boot cung cấp các đường dẫn bổ sung như `/livez` và `/readyz` trên main port. Bảo đảm probe dùng đúng port và path thực tế của ứng dụng.

## 6. Quản lý availability state bằng Spring Boot

Khi ứng dụng có một bộ theo dõi kết nối hoặc lifecycle coordinator, có thể phát `AvailabilityChangeEvent` để thay đổi readiness:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;

@Component
public class MessagingAvailability {

    private final ApplicationEventPublisher publisher;

    public MessagingAvailability(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
            publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Gọi `refuseTraffic()` khi một dependency bắt buộc hoặc một phần chức năng cốt lõi không thể phục vụ workload. Chỉ gọi `acceptTraffic()` sau khi toàn bộ điều kiện cần thiết đã phục hồi.

**Không để từng dependency tự phát ACCEPTING_TRAFFIC một cách độc lập.** Ví dụ broker đã phục hồi nhưng database vẫn down; nếu JMS monitor phát accepting ngay, nó có thể ghi đè trạng thái từ chối do database. Trong ứng dụng có nhiều dependency, nên có một readiness coordinator tổng hợp trạng thái của tất cả thành phần bắt buộc.

Coordinator cũng nên có debounce hoặc hysteresis: chỉ chuyển trạng thái sau một số lần kiểm tra/thời gian xác nhận phù hợp, tránh readiness liên tục bật/tắt khi mạng chập chờn.

Nếu đã dùng health group gồm `readinessState` và `jms`, không nhất thiết phải phát availability event cho mọi lần broker lỗi. Có thể để health indicator phản ánh trạng thái dependency trực tiếp; dùng availability event khi ứng dụng cần điều phối trạng thái toàn cục hoặc các điều kiện không thể biểu diễn bằng một indicator đơn lẻ.

## 7. JMS: startup, listener recovery và gửi message

### 7.1. ConnectionFactory và JmsTemplate

`JmsTemplate` cần một `ConnectionFactory`. Việc tạo bean template không có nghĩa kết nối broker đã được kiểm tra. Lệnh gửi thực tế mới sử dụng resource để tạo connection/session/producer theo cách triển khai của provider và connection factory.

Ví dụ:

~~~java
jmsTemplate.convertAndSend("orders.commands", command);
~~~

Nếu broker không sẵn sàng, thao tác có thể ném lỗi JMS đã được Spring chuyển thành exception unchecked. Ứng dụng cần quyết định có trả lỗi cho caller, lưu vào outbox hay retry theo chính sách. Không nên giữ HTTP request hoặc thread xử lý trong vòng retry vô hạn.

Với command/event quan trọng, transactional outbox thường phù hợp hơn việc retry publish đồng bộ trong thời gian dài: ghi business state và outbox row trong cùng database transaction, rồi relay gửi lại khi broker phục hồi.

### 7.2. @JmsListener và DefaultMessageListenerContainer

Spring dùng listener container để kết nối consumer với JMS provider, đăng ký nhận message và quản lý threading/resource. Trong các trường hợp phổ biến, `DefaultMessageListenerContainer` là lựa chọn mặc định phù hợp.

Container này có khả năng phục hồi khi broker ngừng hoạt động. Theo tài liệu Spring Framework, backoff mặc định thử lại sau mỗi 5 giây; ứng dụng có thể cấu hình `BackOff` riêng để kiểm soát chu kỳ phục hồi.

Điều này có nghĩa listener có thể vẫn đang trong quá trình reconnect khi broker chưa sẵn sàng. Không nên chỉ dựa vào việc bean listener tồn tại để kết luận consumer có thể nhận message.

Cần phân biệt:

- Listener endpoint đã được đăng ký trong Spring.
- Listener container đang chạy theo lifecycle.
- JMS connection đã được thiết lập.
- Consumer đã subscribe thành công destination.
- Message thực tế có thể được nhận và xử lý.

Các trạng thái trên không đồng nghĩa với nhau. Nếu workload yêu cầu consumer subscription sẵn sàng trước khi pod nhận traffic, readiness phải phản ánh điều kiện subscription thực tế hoặc một health check tương ứng.

### 7.3. Kiểm tra listener container

`JmsListenerEndpointRegistry` cho phép truy cập các listener container được tạo bởi `@JmsListener`. Có thể kiểm tra trạng thái lifecycle để phục vụ diagnostics hoặc một readiness coordinator:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ListenerStatus {

    private final JmsListenerEndpointRegistry registry;

    public ListenerStatus(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean requiredListenerRunning(String id) {
        MessageListenerContainer container =
            registry.getListenerContainer(id);

        return container != null && container.isRunning();
    }
}
~~~

Khai báo listener cần kiểm tra với một ID tường minh, ví dụ `ordersListener`, rồi truyền ID đó vào `requiredListenerRunning`.

Đây là kiểm tra lifecycle. `isRunning()` không đảm bảo broker đang nhận kết nối hoặc subscription vẫn hoạt động ở thời điểm hiện tại. Với `DefaultMessageListenerContainer`, container có thể đang chạy và tiếp tục thử reconnect trong khi broker down.

Vì vậy, kết hợp trạng thái container với broker health hoặc trạng thái subscription do provider/container cung cấp. Đừng coi một boolean lifecycle là phép thử end-to-end.

### 7.4. Recovery và backoff

Backoff quyết định tần suất thử kết nối lại. Một chính sách tốt cần:

- Tăng khoảng chờ khi lỗi kéo dài.
- Có giới hạn trên để vẫn thử lại định kỳ.
- Thêm jitter nếu nhiều replica có thể reconnect đồng thời.
- Không tạo một vòng reconnect thứ hai cạnh tranh với cơ chế recovery của listener container.
- Ghi log có giới hạn để tránh log storm.
- Phân biệt lỗi cấu hình cố định như sai credential với lỗi mạng tạm thời.

`DefaultMessageListenerContainer` hỗ trợ custom `BackOff`. Hãy đọc tài liệu provider và phiên bản Spring để chọn cách cấu hình phù hợp. Với broker down ngắn hạn, cơ chế recovery sẵn có thường đã đủ; chỉ tùy chỉnh khi có yêu cầu vận hành cụ thể.

### 7.5. Xử lý khi broker phục hồi

Khi broker trở lại, không nên lập tức đánh dấu toàn bộ ứng dụng ready chỉ vì TCP port mở. Hãy chờ:

1. ConnectionFactory có thể tạo kết nối hợp lệ.
2. Authentication và quyền truy cập được xác nhận.
3. Listener container kết nối lại.
4. Consumer đăng ký destination/subscription cần thiết.
5. Các bước khởi tạo cục bộ của ứng dụng đã hoàn tất.

Sau đó coordinator mới chuyển readiness sang accepting nếu các dependency bắt buộc khác cũng sẵn sàng.

Nếu message được redeliver sau reconnect, handler phải idempotent và có chiến lược xử lý duplicate. Recovery connection không đảm bảo message chỉ được xử lý một lần.

## 8. RSocket và transport kết nối tới peer từ xa

### 8.1. Tạo RSocketRequester không đồng nghĩa đã kết nối

Spring `RSocketRequester` cung cấp API fluent để gửi request qua RSocket. Một requester có thể được tạo như sau:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
~~~

Theo tài liệu Spring, lời gọi `tcp` hoặc `webSocket` ở ví dụ này chưa kết nối ngay. Kết nối dùng chung được thiết lập khi ứng dụng bắt đầu gửi request.

Vì vậy, việc ApplicationContext tạo được bean `RSocketRequester` không chứng minh peer đang hoạt động. Readiness cho một dependency RSocket bắt buộc cần kiểm tra khả năng thực hiện một interaction thực tế hoặc theo dõi trạng thái kết nối từ client/transport.

### 8.2. Dùng route kiểm tra không gây side effect

Có thể định nghĩa một route nhẹ, chỉ trả thông tin trạng thái:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class PeerReadinessController {

    @MessageMapping("system.readiness")
    public Mono<Boolean> readiness() {
        return Mono.just(true);
    }
}
~~~

Phía client có thể gọi route đó với timeout hữu hạn:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<Boolean> peerReady = requester
    .route("system.readiness")
    .retrieveMono(Boolean.class)
    .timeout(Duration.ofSeconds(2))
    .onErrorReturn(false);
~~~

Đây là ví dụ probe ở mức ứng dụng. Route phải tồn tại ở peer và chỉ xác nhận các điều kiện mà nó cam kết. Nếu peer chỉ trả `true` khi process sống, điều đó chưa chứng minh các dependency phía sau peer cũng sẵn sàng.

Không nên gửi một probe nặng ở mỗi lần Kubernetes gọi readiness. Có thể thực hiện probe định kỳ với timeout, lưu trạng thái gần nhất và để readiness đọc trạng thái đã được cập nhật. Chu kỳ probe cần đủ ngắn để phát hiện sự cố nhưng không tạo thêm tải lên peer.

### 8.3. Phân biệt inbound server và outbound client

- **RSocket server inbound:** readiness phản ánh transport đã bind và responder có thể nhận request, cùng các dependency cần thiết của handler.
- **RSocket client outbound:** readiness có thể phụ thuộc peer từ xa, nếu peer là điều kiện bắt buộc cho workload.
- **Peer tùy chọn:** giữ instance ready nếu fallback hoặc chức năng còn lại vẫn đáp ứng cam kết; ghi nhận trạng thái degraded riêng.

Nếu chỉ có một requester bean mà chưa có request nào được gửi, chưa thể kết luận remote connection đã được thiết lập. Ngược lại, một lần probe thành công cũng không bảo đảm kết nối sẽ còn tồn tại mãi; cần xử lý timeout và lỗi ở từng request.

## 9. Retry, timeout, circuit breaker và outbox

Readiness chỉ điều khiển việc nhận thêm workload. Các request đang chạy vẫn có thể gặp lỗi, nên cần chính sách phục hồi ở tầng giao tiếp.

### 9.1. Timeout

Đặt timeout hữu hạn cho các thao tác kết nối, gửi và request-response. Timeout phải phù hợp với SLA và timeout của tầng gọi phía trên.

Nếu timeout quá dài, thread hoặc connection có thể bị giữ trong thời gian broker/peer down. Nếu quá ngắn, ứng dụng có thể từ chối thao tác hợp lệ khi hệ thống đang chậm tạm thời.

### 9.2. Retry có giới hạn

Retry chỉ phù hợp với lỗi có khả năng phục hồi. Dùng exponential backoff và jitter để tránh tất cả replica thử lại cùng lúc. Giới hạn số lần hoặc tổng thời gian retry; sau đó trả lỗi rõ ràng, lưu outbox hoặc chuyển message vào cơ chế xử lý lỗi phù hợp.

Không retry mù quáng các lỗi không thể phục hồi như sai credential, schema không hợp lệ hoặc permission bị từ chối.

### 9.3. Circuit breaker

Circuit breaker giúp ngăn các request tiếp tục gọi một dependency đang lỗi. Khi breaker open, caller có thể fail fast hoặc dùng fallback. Điều này có thể cho phép ứng dụng vẫn ready nếu dependency đó không thiết yếu cho toàn bộ workload.

Circuit breaker không tự phục hồi JMS listener container và không thay thế readiness probe. Hai cơ chế giải quyết các lớp vấn đề khác nhau.

### 9.4. Outbox và message bền vững

Nếu request cần được tiếp nhận ngay cả khi broker tạm thời down, ứng dụng có thể ghi command/event vào outbox cùng transaction nghiệp vụ. Worker relay publish lại khi broker phục hồi.

Trong mô hình này, readiness có thể vẫn accepting nếu database/outbox là nơi tiếp nhận bền vững và hệ thống cam kết xử lý bất đồng bộ. Cần theo dõi backlog, tuổi message cũ nhất và dung lượng outbox; nếu backlog vượt ngưỡng hoặc database không thể ghi, readiness có thể phải chuyển trạng thái.

Không trả thành công nếu message chỉ nằm trong bộ nhớ và có thể mất khi process restart.

## 10. Graceful shutdown khi đang dùng messaging

Khi nhận tín hiệu shutdown, instance nên:

1. Chuyển readiness sang `REFUSING_TRAFFIC` để ngừng nhận workload mới.
2. Ngừng nhận request mới ở tầng ứng dụng hoặc route cần thiết.
3. Dừng hoặc pause listener container theo chính sách drain của ứng dụng.
4. Cho phép message đang xử lý hoàn tất trong thời gian grace period.
5. Commit transaction/ack theo đúng semantics của consumer.
6. Giải phóng connection và transport.
7. Để broker redeliver các message chưa được xác nhận theo chính sách của provider.

Graceful shutdown HTTP của Spring Boot không tự đảm bảo mọi JMS listener đã drain an toàn. Cần cấu hình lifecycle và thời gian shutdown phù hợp với container, transaction, broker và độ dài xử lý message.

Không xác nhận message trước khi công việc quan trọng đã được commit. Nếu consumer chết giữa xử lý và ack, message có thể được redeliver; handler phải xử lý duplicate an toàn.

## 11. Quan sát trạng thái messaging

Readiness endpoint chỉ là một phần của vận hành. Cần quan sát thêm:

**JMS/broker**

- Số lần kết nối thất bại và reconnect.
- Thời gian broker không sẵn sàng.
- Listener container state và số consumer hoạt động.
- Queue depth, consumer lag và tuổi message cũ nhất.
- Publish failure, redelivery, rollback và dead-letter count.
- Outbox backlog và thời gian chờ publish.

**RSocket/transport**

- Connection count và connection failure.
- Keepalive timeout hoặc disconnect.
- Request latency, timeout và error rate theo route.
- Số lần reconnect/resume nếu ứng dụng cấu hình các cơ chế đó.
- Tỷ lệ probe thành công và tuổi của lần probe gần nhất.

**Application**

- Readiness state chuyển đổi bao nhiêu lần.
- Thời gian từ broker phục hồi tới lúc ứng dụng ready.
- Số request bị từ chối vì dependency.
- Số lần circuit breaker open/half-open.
- Thời gian shutdown và số message còn in-flight.

Log nên có correlation ID, destination/route, message ID và loại lỗi. Không ghi credential, token hoặc toàn bộ payload nhạy cảm vào log. Health details cũng cần giới hạn quyền truy cập.

## 12. Kiểm thử tình huống broker hoặc transport không sẵn sàng

Một bài test readiness có giá trị phải mô phỏng lỗi ở dependency thật hoặc test double tương đương, thay vì chỉ gọi health endpoint khi mọi thứ đều đang chạy.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Khởi động app khi broker down | Process không bị liveness restart liên tục; readiness từ chối nếu JMS là dependency bắt buộc |
| Broker khởi động sau app | Listener reconnect; readiness chỉ accepting sau khi điều kiện cần thiết được đáp ứng |
| Broker mất kết nối khi app đang chạy | Liveness vẫn healthy; readiness thay đổi theo chính sách dependency |
| Sai credential hoặc thiếu quyền destination | Không retry vô hạn; lỗi được quan sát và readiness phản ánh đúng chức năng bị ảnh hưởng |
| Broker phục hồi sau thời gian dài | Listener hoạt động lại, message được xử lý, duplicate không gây side effect lặp |
| Queue backlog tăng cao | Alert theo lag/age; readiness chỉ chuyển refusing khi đạt ngưỡng đã định |
| RSocket peer down trước request đầu tiên | Probe phát hiện peer unavailable; không coi requester bean tồn tại là connected |
| RSocket peer mất kết nối giữa hai request | Request có timeout/error rõ ràng; probe cập nhật trạng thái theo chính sách |
| Dependency phụ down | Instance vẫn ready nếu fallback thực sự đáp ứng contract |
| Shutdown khi message đang xử lý | Instance ngừng nhận workload mới, drain hoặc redeliver message đúng semantics |

Với Kubernetes, xác nhận readiness probe loại instance khỏi endpoints khi refusing traffic và đưa instance trở lại khi healthy. Kiểm tra cả trường hợp tất cả replica cùng unready để hiểu cách Service/Ingress/load balancer phản ứng trong môi trường triển khai thực tế.

## 13. Lỗi thường gặp

1. **Đưa broker vào liveness.** Broker down làm pod restart hàng loạt và gây reconnect storm. Giữ liveness độc lập với dependency bên ngoài.
2. **Cho rằng readiness mặc định kiểm tra JMS.** Spring Boot không tự đưa mọi external health indicator vào readiness group; phải include rõ ràng.
3. **Cho rằng có JmsTemplate là broker đã kết nối.** Bean tồn tại không chứng minh lần gửi thật sẽ thành công.
4. **Cho rằng @JmsListener tồn tại là consumer đã subscribe.** Cần xem lifecycle container, connection và subscription.
5. **Cho rằng requester bean là RSocket connection.** Spring RSocketRequester kết nối lazy khi request được gửi.
6. **Probe thực hiện nghiệp vụ thật.** Probe có thể tạo đơn hàng, gửi email hoặc làm thay đổi trạng thái. Dùng route/operation chỉ đọc, nhẹ và có giới hạn.
7. **Retry vô hạn trong request thread.** Gây cạn thread, tăng latency và khuếch đại sự cố. Dùng timeout, backoff, outbox hoặc fail fast.
8. **Mỗi dependency tự đặt readiness accepting.** Một dependency phục hồi có thể ghi đè trạng thái từ chối do dependency khác. Dùng coordinator tổng hợp.
9. **Readiness flap liên tục.** Mạng chập chờn làm instance liên tục bị thêm/bớt khỏi load balancer. Dùng debounce/hysteresis.
10. **Không drain listener khi shutdown.** Message có thể mất hoặc xử lý lặp nếu ack/transaction không đúng. Thiết kế shutdown và idempotency.

## 14. Checklist thiết kế

- [ ] Xác định broker/transport nào bắt buộc cho từng workload.
- [ ] Phân biệt liveness, readiness và startup probe.
- [ ] Không đưa lỗi external dependency vào liveness nếu ứng dụng có thể tự phục hồi.
- [ ] Cấu hình Actuator readiness group với đúng dependency thiết yếu.
- [ ] Không giả định JMS health chứng minh listener đã subscribe hoặc message flow hoàn chỉnh.
- [ ] Không giả định RSocketRequester bean đồng nghĩa với remote connection.
- [ ] Probe có timeout, chi phí thấp và không gây side effect.
- [ ] Có một coordinator khi nhiều dependency cùng quyết định readiness.
- [ ] Có backoff/reconnect phù hợp và không tạo retry storm.
- [ ] Có outbox hoặc cơ chế tiếp nhận bền vững nếu cần chịu broker downtime.
- [ ] Theo dõi queue depth, lag, reconnect, DLQ và thời gian phục hồi.
- [ ] Có graceful shutdown và xử lý message in-flight.
- [ ] Fault-injection test cho broker down, recovery, permission failure và peer disconnect.

## 15. Tài liệu tham khảo

- [Spring Boot Reference — Actuator Endpoints: Health and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health groups, liveness/readiness state, probe paths và cách đánh giá external dependency.
- [Spring Boot API — ApplicationAvailability](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ApplicationAvailability.html): truy vấn availability state hiện tại của ứng dụng.
- [Spring Boot API — AvailabilityChangeEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html): phát sự kiện cập nhật readiness/liveness state.
- [Spring Boot API — JmsHealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jms/health/JmsHealthIndicator.html): health indicator kiểm tra JMS ConnectionFactory và broker.
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, ConnectionFactory, listener containers và recovery của DefaultMessageListenerContainer.
- [Spring Framework Reference — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html): tạo requester, kết nối lazy, request/response và transport TCP/WebSocket.
