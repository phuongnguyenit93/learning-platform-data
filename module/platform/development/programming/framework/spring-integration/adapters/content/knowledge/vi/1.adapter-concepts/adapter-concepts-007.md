# Vòng đời endpoint và trạng thái hoạt động

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả các giai đoạn **khởi tạo, khởi động, đang chạy, dừng và khởi động lại** của một endpoint trong Spring Integration.
- Phân biệt trạng thái **endpoint đang chạy** với trạng thái **kết nối sẵn sàng**, **channel có người nhận** và **message được xử lý thành công**.
- Sử dụng đúng các khái niệm **Lifecycle**, **SmartLifecycle**, **autoStartup**, **phase**, **start()**, **stop()** và **isRunning()**.
- Giải thích sự khác biệt khi vận hành inbound polling adapter, message-driven adapter, outbound adapter và gateway.
- Cấu hình Java DSL để một file inbound endpoint không tự khởi động, sau đó bật/tắt endpoint bằng mã quản trị.
- Thiết kế trình tự khởi động/dừng an toàn, theo dõi backlog, xử lý message đang chạy và khôi phục sau sự cố.

## 1. Vì sao vòng đời endpoint quan trọng?

Một IntegrationFlow có thể kết nối hệ thống ngoài qua file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu. Để luồng hoạt động, chỉ tạo bean và khai báo MessageChannel là chưa đủ: có những endpoint cần **bắt đầu lịch poller**, **đăng ký listener**, **khởi tạo consumer**, hoặc **mở/thuê kết nối** trước khi có thể trao đổi message.

Ví dụ, ứng dụng nhận CSV từ đối tác qua SFTP, chuẩn hóa thành Order rồi phát Kafka event. Nếu Kafka producer hoặc consumer downstream chưa sẵn sàng mà inbound SFTP đã quét và chuyển dữ liệu, hệ thống có thể gặp lỗi gửi hoặc backlog. Khi triển khai lại, nếu dừng nguồn nhận quá muộn, các message mới có thể tiếp tục đến trong lúc bước xử lý hoặc gửi ra ngoài đã dừng.

Spring Integration cung cấp cơ chế quản lý **vòng đời endpoint** để ứng dụng có thể chủ động:

- **Khởi động** nguồn nhận hoặc consumer khi điều kiện hoạt động đã đáp ứng.
- **Tạm ngừng tiếp nhận** một nguồn mà không nhất thiết dừng toàn bộ ứng dụng.
- **Dừng có thứ tự** để giảm rủi ro message còn đang xử lý.
- **Khởi động lại** endpoint sau sự cố hoặc khi cửa sổ bảo trì kết thúc.
- **Quan sát trạng thái** để phân biệt endpoint chưa chạy với endpoint đang chạy nhưng không có dữ liệu.

Đây là một phần của việc quản lý luồng kết nối và độ tin cậy của messaging, không chỉ là thao tác bật/tắt một bean Java.

## 2. Endpoint, channel và tài nguyên bên ngoài có vòng đời khác nhau

Một luồng có thể có nhiều thành phần cùng tồn tại:

~~~mermaid
flowchart LR
    SRC["Nguồn bên ngoài<br/>File / SFTP / JMS / Kafka"]
    EP["Inbound endpoint<br/>poller hoặc listener"]
    CH["MessageChannel"]
    H["Transformer / Service activator"]
    OUT["Outbound endpoint"]
    DST["Hệ thống đích"]
    SRC --> EP --> CH --> H --> OUT --> DST
    SCH["TaskScheduler / Listener container"] -. "Điều phối" .-> EP
    CON["Connection factory / Session / Client"] -. "Cấp kết nối" .-> EP
    CON -. "Có thể được dùng riêng" .-> OUT
~~~

**Endpoint** là thành phần kết nối message producer/consumer với channel. **MessageChannel** là đường chuyển giao message. **Connection factory, session, scheduler hoặc client** là tài nguyên được endpoint sử dụng. Mỗi lớp có trách nhiệm vận hành riêng.

| Thành phần | Khi đang hoạt động | Khi dừng hoặc không sẵn sàng |
| --- | --- | --- |
| File inbound polling endpoint | Poller có thể quét nguồn theo lịch | Không phát sinh những lần poll mới từ endpoint đã dừng |
| JMS/AMQP/Kafka inbound message-driven endpoint | Listener/consumer được kích hoạt theo cơ chế giao thức | Không tiếp tục nhận theo listener đã dừng; tiến độ và message đang xử lý phụ thuộc container |
| Event-driven consumer của outbound adapter | Đăng ký nhận message từ channel và gọi handler | Có thể ngừng nhận từ channel dù bean adapter vẫn tồn tại |
| Polling consumer của outbound adapter | Lấy message từ PollableChannel theo lịch | Có thể còn message chờ trong channel |
| MessageChannel | Chuyển giao hoặc lưu message theo loại channel | Channel không nhất thiết là endpoint có cùng trạng thái start/stop |
| Connection/session/client | Cung cấp khả năng giao tiếp với hệ thống ngoài | Có thể mất kết nối hoặc hết hạn ngay cả khi endpoint báo đang chạy |

Đặc biệt, một **DirectChannel** không có nghĩa vụ tự mở kết nối mạng hay tự chạy scheduler. Ngược lại, một **QueueChannel** có thể giữ message trong bộ nhớ dù polling consumer đã tạm dừng. QueueChannel mặc định không bảo đảm lưu message bền vững khi ứng dụng chết.

## 3. Vòng đời ở mức Spring: Lifecycle và SmartLifecycle

Spring cung cấp hai giao diện nền tảng:

**Lifecycle** định nghĩa các thao tác và trạng thái:

~~~java
void start();
void stop();
boolean isRunning();
~~~

**SmartLifecycle** mở rộng cơ chế quản lý vòng đời, hỗ trợ **auto-startup** và **phase** để Spring ApplicationContext điều phối lúc khởi động/dừng. Nhiều endpoint của Spring Integration sử dụng cơ chế vòng đời này, thường thông qua endpoint/consumer triển khai tương ứng.

| Khái niệm | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **start()** | Yêu cầu thành phần bắt đầu hoạt động | Có thể kích hoạt scheduler, đăng ký subscriber hoặc chạy listener |
| **stop()** | Yêu cầu thành phần dừng hoạt động | Không bảo đảm mọi tác vụ đang chạy lập tức kết thúc hoặc được rollback |
| **isRunning()** | Cho biết trạng thái vòng đời mà thành phần báo cáo | Không chứng minh remote server đang khỏe hoặc message đã xử lý thành công |
| **autoStartup** | Có tự chạy khi ApplicationContext khởi động hay không | Có thể đặt false để chờ bật thủ công |
| **phase** | Hỗ trợ thứ tự khởi động/dừng của SmartLifecycle | Phase nhỏ thường start trước; khi shutdown, phase lớn dừng trước |

Trong quá trình khởi động ApplicationContext, cơ chế lifecycle processor của Spring khởi động các bean SmartLifecycle phù hợp theo phase và chế độ auto-startup. Khi đóng context, Spring điều phối dừng theo thứ tự ngược lại. **Thứ tự chính xác phải xét bean, endpoint và cấu hình hiện hành**; không nên giả định mọi adapter có cùng phase mặc định.

### 3.1. State machine để suy nghĩ, không phải enum chính thức

Có thể hình dung endpoint trải qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Initialized: Spring tạo và cấu hình bean
    Initialized --> Running: autoStartup hoặc start()
    Running --> Stopping: stop() hoặc đóng context
    Stopping --> Stopped: Hoàn tất dừng
    Stopped --> Running: start() khi context còn sống
    Initialized --> Stopped: Không tự khởi động
    Stopped --> [*]: Hủy context / tài nguyên
~~~

Các nhãn **Created**, **Initialized**, **Stopping** trong sơ đồ là cách diễn giải để thiết kế và vận hành; **không phải enum trạng thái thống nhất** mà mọi endpoint Spring Integration đều công khai. Phương thức thông dụng **isRunning()** chỉ trả về boolean, vì thế không đủ để phân biệt “đang khởi động”, “đã kết nối nhưng chưa nhận được dữ liệu”, hoặc “đang chờ xử lý hết message”.

### 3.2. autoStartup = false có ý nghĩa gì?

Khi đặt **autoStartup(false)** cho endpoint, Spring vẫn có thể tạo các bean và đăng ký flow, nhưng endpoint đó **không tự hoạt động khi context khởi động**. Một tác vụ quản trị hoặc một service khác có thể gọi start() sau khi các điều kiện sẵn sàng được đáp ứng.

Ví dụ phù hợp: đợi cấu hình đối tác được kích hoạt, tạm khóa luồng nhập khi đang chuyển đổi dữ liệu, hoặc tránh nhận thêm file trong thời gian bảo trì. Chỉ tắt autoStartup **không xóa dữ liệu nguồn** và **không tự bảo đảm thông điệp sẽ được xử lý đúng một lần** khi bật lại.

## 4. Trạng thái chạy khác với trạng thái sẵn sàng

Một lỗi vận hành phổ biến là nhìn thấy **isRunning() == true** rồi kết luận hệ thống tích hợp đang khỏe. Trên thực tế, trạng thái vòng đời có thể không phản ánh kết nối mạng hoặc năng lực xử lý.

| Quan sát | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Endpoint báo isRunning = true | Endpoint đang ở trạng thái chạy theo vòng đời của nó | SFTP/JMS/Kafka/HTTP/DB luôn kết nối thành công |
| Poller tiếp tục được kích hoạt | Nhiệm vụ theo lịch đang chạy | Nguồn có dữ liệu mới hoặc dữ liệu nhận được hợp lệ |
| JMS/Kafka listener đang chạy | Container/consumer được phép nhận theo cơ chế cấu hình | Mọi partition/queue đều có dữ liệu, không có consumer lag |
| Message đã vào DirectChannel | Lượt gửi được thực hiện theo ngữ nghĩa channel | Side effect tại hệ thống đích đã hoàn tất |
| Message đã vào QueueChannel | Message đã được chấp nhận để chờ lấy | Message lưu bền sau restart hoặc đã được consumer xử lý |
| Broker xác nhận nhận event | Đã đạt mốc xác nhận theo producer/broker | Consumer cuối đã hoàn thành nghiệp vụ |

Nên phân biệt ít nhất bốn khía cạnh: **lifecycle state**, **connection health**, **message throughput/backlog** và **business outcome**. Một endpoint “đang chạy nhưng poll trống” có thể hoàn toàn bình thường, trong khi endpoint “đang chạy nhưng mỗi lần poll đều lỗi xác thực” là tình trạng cần cảnh báo.

## 5. Polling inbound adapter bắt đầu và dừng như thế nào?

Với file, SFTP hoặc JDBC inbound adapter dạng polling, một **MessageSource** kết hợp **SourcePollingChannelAdapter** và **poller**. Khi endpoint hoạt động, scheduler kích hoạt việc gọi source theo lịch; message nhận được được gửi vào channel để xử lý.

~~~mermaid
sequenceDiagram
    participant C as ApplicationContext
    participant E as Polling inbound endpoint
    participant S as TaskScheduler / Poller
    participant F as File/SFTP/DB source
    participant M as MessageChannel
    C->>E: start()
    E->>S: Đăng ký lịch poll
    loop Mỗi lần poll khi endpoint hoạt động
      S->>F: receive() theo nguồn
      F-->>S: Message hoặc không có dữ liệu
      opt Có Message
        S->>M: send(message)
      end
    end
    C->>E: stop()
    E->>S: Ngừng lịch nhận mới
~~~

Khi gọi **stop()**:

- Lịch poll của endpoint bị dừng/hủy theo cơ chế quản lý endpoint.
- Không nên hiểu là mọi công việc **đã bắt đầu** đều bị cắt ngay lập tức; việc kết thúc tác vụ phụ thuộc luồng xử lý, scheduler và cấu hình.
- File chưa nhận vẫn có thể nằm nguyên tại nguồn. File đã được nhận nhưng xử lý lỗi có được chọn lại hay không phụ thuộc bộ lọc, trạng thái, cơ chế retry và khôi phục.
- Việc stop một endpoint dùng chung **TaskScheduler** không có nghĩa ứng dụng phải tắt scheduler cho tất cả endpoint khác.

### 5.1. Trường hợp poller không có dữ liệu

Không có file mới hoặc SQL query trả về tập rỗng **không có nghĩa endpoint đã dừng**. Poller có thể tiếp tục chạy đúng lịch và không phát message nào. Để giám sát, cần tách số lần poll thành công, lần poll trống và lần poll lỗi.

### 5.2. Restart và lọc file nhận một lần

File inbound adapter thường có bộ lọc tránh chọn lặp các file đã được nhận trong cùng trạng thái theo dõi. Tuy nhiên bộ lọc hoặc metadata lưu **trong bộ nhớ** có thể mất trạng thái khi ứng dụng restart. Cũng cần phân biệt “đã chọn tệp để gửi vào channel” với “nghiệp vụ đã hoàn tất”.

Nếu cần an toàn sau restart, hãy thiết kế rõ:

1. Bộ lọc hoặc metadata store có trạng thái bền vững phù hợp.
2. Quy trình tiếp nhận file đã được ghi hoàn tất.
3. Cách chuyển/đánh dấu file sau khi xử lý.
4. Khóa idempotency của nghiệp vụ, ví dụ **partnerId + orderId**, để tránh tác động trùng.

## 6. Message-driven endpoint: listener và consumer có vòng đời riêng

Các nguồn JMS, AMQP và Kafka thường dùng **listener container** hoặc consumer do client giao thức quản lý. Khi inbound endpoint start, framework kích hoạt hoặc tiếp tục cơ chế nhận theo cấu hình; khi stop, hoạt động tiếp nhận được yêu cầu dừng.

| Nguồn | Khi start | Khi stop cần chú ý |
| --- | --- | --- |
| **JMS** | Khởi động message listener container để nhận từ destination | Giao dịch/ack của message đang xử lý, khả năng redelivery, timeout shutdown |
| **AMQP** | Bật container lắng nghe queue hoặc cơ chế consumer | ACK/NACK, requeue, prefetch và message chưa xác nhận |
| **Kafka** | Khởi động listener/consumer, tham gia group theo client | Offset đã commit, record đang xử lý, rebalance, khả năng nhận lại |
| **HTTP inbound gateway** | Endpoint web được đăng ký và có thể tiếp nhận request trong hạ tầng server | Dừng endpoint không đồng nghĩa tự tắt toàn bộ HTTP server hoặc kết thúc mọi request đang chờ |

Đối với Kafka, consumer client tự có vòng poll nội bộ; không nên suy ra mọi Kafka inbound endpoint cần một **Spring Integration poller**. Tương tự, JMS/AMQP acknowledgment không phải response nghiệp vụ của gateway.

Điểm quan trọng: **stop() không phải lệnh xóa message khỏi broker**. Message còn ở queue/topic, đang in-flight hoặc đã được acknowledge/commit sẽ có hành vi tiếp theo theo cơ chế của từng giao thức, nhóm consumer, transaction và cấu hình.

### 6.1. Tránh nhầm restart endpoint với restart ứng dụng

Gọi **stop()/start()** trên một endpoint trong ApplicationContext còn sống khác với khởi động lại cả tiến trình:

- Một số bean/client/scheduler vẫn được giữ lại khi chỉ dừng endpoint.
- Các message trong queue nội bộ có thể tiếp tục tồn tại trong cùng tiến trình.
- Restart ứng dụng có thể tạo bean mới, reset trạng thái bộ nhớ hoặc thiết lập lại consumer group/session.
- Shutdown ApplicationContext thường đóng tài nguyên chia sẻ; không nên kỳ vọng gọi start() trên bean sau khi context đã bị đóng.

## 7. Outbound adapter và gateway cũng có trạng thái chạy

Lifecycle không chỉ liên quan inbound adapter. **Consumer endpoint** của outbound adapter nhận message từ channel; nó cũng phải được đăng ký và hoạt động để xử lý dữ liệu.

**Event-driven consumer** thường đăng ký một subscriber với **SubscribableChannel** như DirectChannel. Khi endpoint dừng, subscriber đó có thể bị ngừng đăng ký; producer vẫn gửi vào DirectChannel có thể gặp lỗi nếu không còn subscriber nhận message.

**Polling consumer** lấy message từ **PollableChannel** như QueueChannel. Khi endpoint dừng, những message đang chờ có thể tiếp tục nằm trong queue (tùy cấu hình và khả năng lưu trữ). Việc resume có thể làm consumer bắt đầu lấy backlog.

**Outbound gateway** cần xét thêm message reply. Nếu dừng endpoint hoặc kết nối bị đóng giữa request–reply, caller có thể không nhận kết quả trong thời gian cho phép. **Timeout không chứng minh tác vụ bên ngoài chưa thực hiện**; retry cần idempotency và đối soát.

~~~mermaid
flowchart LR
    P["Producer"] --> Q["QueueChannel"]
    Q --> PC["Polling consumer<br/>có lifecycle"]
    PC --> OA["Outbound adapter"]
    OA --> EXT["Broker / File / API"]
    CTRL["Bật/tắt endpoint"] -.-> PC
    NOTE["Message có thể chờ trong queue"] -.-> Q
~~~

Một outbound adapter có thể dùng HTTP client, Kafka producer, JMS connection factory hoặc SFTP session từ bean chia sẻ. Dừng consumer endpoint không có nghĩa tự động đóng mọi tài nguyên dùng chung hay làm đích bên ngoài ngừng hoạt động.

## 8. Thực hành Java DSL: bật/tắt file inbound endpoint

Mục tiêu: tạo một file inbound polling adapter đọc **./data/inbox**, gửi payload kiểu File vào MessageChannel **incomingFiles**, rồi một consumer in tên file. Endpoint được đặt **autoStartup(false)** để không quét ngay khi ứng dụng khởi động. Ta bật/tắt endpoint qua **SmartLifecycle**.

Với Spring Boot, cần module Spring Integration core (thường từ **spring-boot-starter-integration**) và **spring-integration-file** tương ứng với phiên bản Boot quản lý.

### 8.1. Cấu hình hai flow độc lập

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class FileEndpointConfiguration {

    @Bean
    public MessageChannel incomingFiles() {
        return new DirectChannel();
    }

    // Chỉ inbound endpoint này không tự khởi động.
    @Bean
    public IntegrationFlow fileInboundFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                endpoint -> endpoint
                    .id("ordersFileInbound")
                    .autoStartup(false)
                    .poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))
            .channel("incomingFiles")
            .get();
    }

    // Consumer flow sẽ được tự khởi động theo mặc định.
    @Bean
    public IntegrationFlow inspectInboundFiles() {
        return IntegrationFlow.from("incomingFiles")
            .handle(File.class, (file, headers) -> {
                System.out.println("Da nhan: " + file.getName());
                return null;
            })
            .get();
    }
}
~~~

Trong cấu hình:

1. **Files.inboundAdapter(...)** tạo nguồn polling trả về File, không tự parse CSV.
2. **id("ordersFileInbound")** tạo định danh endpoint để có thể tham chiếu bean quản lý vòng đời.
3. **autoStartup(false)** ngăn inbound endpoint tự đăng ký lịch poll lúc context khởi động.
4. **Pollers.fixedDelay(...)** xác định nhịp quét khi endpoint được bật; **maxMessagesPerPoll(5)** giới hạn số message nhận mỗi lượt.
5. **incomingFiles** là DirectChannel đưa message đến consumer; flow consumer có lifecycle riêng và không bị tắt chỉ vì inbound endpoint tạm dừng.

### 8.2. Service điều khiển start/stop

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Service;

@Service
public class InboundEndpointControl {

    private final SmartLifecycle inboundEndpoint;

    public InboundEndpointControl(
            @Qualifier("ordersFileInbound")
            SmartLifecycle inboundEndpoint) {
        this.inboundEndpoint = inboundEndpoint;
    }

    public void resume() {
        if (!inboundEndpoint.isRunning()) {
            inboundEndpoint.start();
        }
    }

    public void pause() {
        if (inboundEndpoint.isRunning()) {
            inboundEndpoint.stop();
        }
    }

    public boolean isRunning() {
        return inboundEndpoint.isRunning();
    }
}
~~~

**Đặt hai class vào các file Java phù hợp.** Service điều khiển nhận bean theo ID của inbound endpoint. Khi gọi **resume()**, poller bắt đầu quét; khi gọi **pause()**, endpoint ngừng khởi tạo các lượt nhận mới theo cơ chế vòng đời. **isRunning()** phục vụ kiểm tra trạng thái của endpoint trong tiến trình này, không phải health check của filesystem hoặc toàn bộ hệ thống.

Đây là API quản trị nội bộ. Nếu expose các thao tác bật/tắt qua HTTP hoặc control bus, cần quản lý quyền gọi và khả năng ghi audit vì thao tác có thể ảnh hưởng tới nguồn dữ liệu đang nhận.

### 8.3. Cách thử và kết quả mong đợi

1. Khởi động ứng dụng; kiểm tra **InboundEndpointControl.isRunning()** ban đầu là **false**.
2. Đặt file **orders-001.csv** vào **./data/inbox**. Trong lúc endpoint tạm dừng, file chưa được polling endpoint này chọn.
3. Gọi **resume()**. Khi lịch poll chạy, consumer sẽ in tên file được nhận.
4. Gọi **pause()**, sau đó đặt **orders-002.csv** vào thư mục. Endpoint đã tạm dừng sẽ không chủ động tạo lượt poll mới để chọn file.
5. Gọi **resume()** lần nữa và quan sát file chờ được chọn theo chính sách bộ lọc.
6. Thử file **notes.txt** để xác nhận **patternFilter("*.csv")** không chọn file ngoài mẫu.

Nếu pause xảy ra đúng lúc một lần poll hoặc handler đang thực thi, một số xử lý đang diễn ra có thể còn hoàn tất sau lời gọi dừng. Vì vậy kết quả kiểm thử nên xem thời điểm tác vụ bắt đầu, log của handler và trạng thái thực tế thay vì kỳ vọng dừng đồng bộ tuyệt đối trong mọi trường hợp.

**Giới hạn ví dụ:** chỉ in tên file. Chưa bảo đảm file được ghi hoàn tất trước khi nhận, chưa xử lý nội dung CSV, chưa có persistent filter hoặc idempotency qua restart. Việc bật lại endpoint không khôi phục tự động trạng thái nghiệp vụ nếu đã xảy ra lỗi giữa chừng.

## 9. Thứ tự start và stop với SmartLifecycle phase

Khi hệ thống gồm nhiều endpoint và tài nguyên, thứ tự hoạt động ảnh hưởng trực tiếp đến khả năng nhận/gửi message.

Spring SmartLifecycle sử dụng **phase**:

- Thành phần có **phase thấp hơn** thường **khởi động trước** thành phần có phase cao hơn.
- Khi đóng context, thành phần có **phase cao hơn** thường **dừng trước** thành phần có phase thấp hơn.
- Một endpoint có thể có **autoStartup(false)** nên không tự khởi động dù phase được đặt.

~~~mermaid
flowchart TD
    A["1. Chuẩn bị tài nguyên<br/>connection / scheduler / consumer"] --> B["2. Bật downstream handler<br/>và outbound endpoint"]
    B --> C["3. Bật inbound listener<br/>hoặc polling source"]
    C --> R["RUNNING"]
    R --> D["4. Yêu cầu inbound dừng nhận mới"]
    D --> E["5. Cho xử lý đang chạy hoàn tất<br/>hoặc lưu checkpoint"]
    E --> F["6. Dừng downstream và tài nguyên"]
~~~

Nguyên tắc vận hành thường là **chuẩn bị đầu tiêu thụ trước khi cho nguồn phát dữ liệu**, và **dừng nguồn nhận trước khi tắt đầu tiêu thụ**. Có thể sử dụng phase và dependency phù hợp để hỗ trợ điều phối, nhưng không suy diễn rằng các default phase đã luôn đáp ứng thứ tự mong muốn cho mọi luồng.

### 9.1. Ví dụ về rủi ro thứ tự sai

Nếu inbound file endpoint đang chạy và gửi tới DirectChannel nhưng outbound consumer đã dừng hoặc chưa đăng ký, lần gửi có thể gặp lỗi **không có subscriber**. Nếu nguồn là message broker, lỗi này ảnh hưởng đến thời điểm ACK/redelivery. Nếu flow có ExecutorChannel, producer có thể tưởng đã gửi xong dù tác vụ downstream sau đó bị từ chối vì executor đang dừng.

Do đó thứ tự dừng phải xét **channel thực tế**, khả năng nhận message đang chạy, transaction, queue capacity và vị trí lưu checkpoint.

## 10. Graceful shutdown: dừng nhận, xả hàng, đóng kết nối

Một lần shutdown an toàn cần phân biệt **ngừng nhận thêm** với **đã xử lý xong mọi message**.

### 10.1. Quy trình tham khảo

1. **Ngăn tạo công việc mới:** yêu cầu inbound adapter/listener dừng nhận theo cơ chế của từng nguồn.
2. **Theo dõi message đang xử lý:** xem active handlers, pending replies, queue depth và các transaction đang chạy.
3. **Chờ hoặc ghi trạng thái an toàn:** cho các tác vụ hoàn tất trong giới hạn vận hành; nếu chưa xong, bảo đảm cơ chế phục hồi hoặc redelivery.
4. **Dừng consumer và đầu ra:** sau khi giảm backlog, dừng outbound endpoints, worker và các thành phần dùng chung theo thứ tự phù hợp.
5. **Đóng tài nguyên:** giải phóng connection/session/executor qua lifecycle của Spring và các client.
6. **Khởi động lại:** dựa vào checkpoint/offset/metadata store bền vững và khóa nghiệp vụ để tránh bỏ sót hoặc xử lý trùng.

Không nên tuyên bố **stop() = drain thành công**. API vòng đời có thể yêu cầu dừng nhưng không bao hàm một transaction xuyên file, database, broker và HTTP. Khả năng chờ tác vụ đang chạy, hủy hoặc redelivery là đặc điểm của từng endpoint và client.

### 10.2. Trường hợp hệ thống ngắt đột ngột

Không phải lần dừng nào cũng chạy được quy trình graceful shutdown. Mất điện hoặc kill tiến trình có thể khiến message đang chờ trong bộ nhớ bị mất, kết nối bị đóng mà chưa ACK, hoặc file đã ghi nhưng checkpoint chưa cập nhật.

Với nghiệp vụ quan trọng, cần lựa chọn lưu trữ bền vững, transactional outbox/inbox, idempotent consumer và quy trình đối soát để có thể phục hồi sau sự cố. **QueueChannel mặc định trong bộ nhớ** không tự cung cấp bảo đảm này.

## 11. Giám sát trạng thái endpoint và chất lượng tích hợp

Nên kết hợp tín hiệu vòng đời với tình trạng kết nối, lưu lượng và kết quả xử lý:

| Nhóm chỉ số | Ví dụ cần quan sát | Ý nghĩa |
| --- | --- | --- |
| **Lifecycle** | Endpoint ID, isRunning, thời điểm start/stop | Biết thành phần đã được bật hay chưa |
| **Kết nối** | Trạng thái session SFTP, broker connectivity, DB pool, HTTP client | Phát hiện endpoint đang chạy nhưng không giao tiếp được |
| **Polling** | Số lượt poll, lần poll rỗng, lỗi poll, thời điểm nhận mới nhất | Phân biệt nguồn không có dữ liệu với nguồn lỗi |
| **Listener** | Kafka consumer lag, JMS/AMQP queue depth, redelivery count | Phát hiện ùn tắc hoặc giao nhận lặp |
| **Xử lý** | Throughput, handler latency, active tasks, queue depth | Biết downstream có đáp ứng tốc độ nguồn hay không |
| **Lỗi** | ErrorMessage, retry, dead-letter, timeout, exception | Tìm vị trí lỗi và cách phục hồi |
| **Nghiệp vụ** | Đơn hàng hoàn tất, khóa trùng, số lượng cần đối soát | Đánh giá outcome, không chỉ mốc gửi message |

Có thể tích hợp log, Micrometer/Actuator và các công cụ quản trị phù hợp với phiên bản/cấu hình của ứng dụng. Đừng giả định mọi endpoint đều tự xuất metric hoặc được quản lý qua HTTP mà không bật tính năng và phụ thuộc cần thiết.

Khi log, dùng endpoint ID, event ID hoặc correlation ID; tránh in credential, payload nhạy cảm và dữ liệu đối tác không cần thiết. Nếu quản trị endpoint theo ID, tên phải ổn định và dễ hiểu để log/metric có thể theo dõi qua các lần triển khai.

## 12. Các tình huống cần quyết định vòng đời

| Tình huống | Cách suy nghĩ phù hợp |
| --- | --- |
| Đối tác SFTP bảo trì | Pause inbound SFTP endpoint, theo dõi trạng thái file và resume theo chính sách |
| Database migration | Tạm dừng nguồn tạo công việc mới trước khi thay schema; xem xét transaction đang xử lý |
| Kafka consumer lag tăng | Đo throughput, concurrency, downstream latency; chỉ tăng consumer phù hợp với partition và năng lực xử lý |
| JMS listener bị mất kết nối | Kiểm tra container, broker, reconnect, redelivery và thời điểm ACK |
| File inbound báo running nhưng không có file | Kiểm tra nguồn có file mới không, pattern filter, quyền đọc, lần poll rỗng và exception |
| Outbound consumer dừng nhưng QueueChannel còn message | Kiểm tra backlog, dung lượng/bền vững của queue, resume có kiểm soát |
| HTTP gateway đang có request chờ khi shutdown | Quy định timeout, trạng thái phản hồi và xử lý request đã có side effect |
| Ứng dụng khởi động sau crash | Đối soát checkpoint, dữ liệu đã gửi, idempotency và trạng thái nguồn/đích |

### 12.1. Trường hợp đặc biệt: “running” nhưng không có subscriber

Giả sử File inbound adapter chạy bình thường và gửi message tới DirectChannel. Flow downstream có thể chưa được khởi động hoặc đã dừng để bảo trì. Lúc này lỗi không nhất thiết nằm ở nguồn file, mà ở việc channel không có consumer phù hợp. Cần kiểm tra **cả endpoint gửi và endpoint nhận** chứ không chỉ một giá trị isRunning.

### 12.2. Trường hợp đặc biệt: đích đã xử lý nhưng ứng dụng timeout

Outbound HTTP gateway hoặc broker producer có thể gặp timeout sau khi hệ thống đích đã nhận request. Dừng và start lại endpoint không tự sửa được trạng thái không rõ này. Phải có khóa idempotency ổn định, hợp đồng xác nhận và công cụ đối soát với đích.

## 13. Sai lầm thường gặp

**“Bean đã khởi tạo tức là endpoint đang nhận dữ liệu.”** Endpoint có thể cấu hình autoStartup(false), chưa start hoặc đã stop.

**“isRunning() = true tức là kết nối và nghiệp vụ đều khỏe.”** Đây chỉ là tín hiệu vòng đời do thành phần báo cáo; cần theo dõi kết nối, lỗi, lưu lượng và kết quả nghiệp vụ.

**“Stop inbound đồng nghĩa tất cả message cũ đã xử lý xong.”** Message có thể đang trong handler, executor, queue hoặc hệ thống đích.

**“Dừng endpoint là dừng luôn scheduler và connection factory dùng chung.”** Các tài nguyên chia sẻ có vòng đời riêng; dừng một endpoint không nên làm hỏng endpoint khác đang dùng chung tài nguyên.

**“Resume sẽ luôn lấy đúng các message chưa xử lý, không trùng.”** Hành vi phụ thuộc file filter, offset, ACK, checkpoint, transaction và chính sách retry.

**“Tăng concurrency giải quyết được lỗi không nhận dữ liệu.”** Nếu nguyên nhân là xác thực SFTP sai, broker không kết nối hoặc dữ liệu bị lọc, tăng worker không giúp ích.

**“Gateway timeout đồng nghĩa đích chưa làm gì.”** Hệ thống đích có thể đã thực hiện side effect rồi mới mất reply; cần đối soát trước khi retry.

**“Phase không quan trọng vì Spring tự xử lý tất cả.”** Phase và dependency có thể quyết định đầu nào start trước, đầu nào stop trước. Cần kiểm tra kiến trúc thực tế.

## 14. Câu hỏi tự kiểm tra

1. Lifecycle và SmartLifecycle khác nhau ở những điểm nào? **autoStartup** và **phase** được dùng để làm gì?
2. Vì sao **isRunning()** không đủ để kết luận SFTP server hoặc Kafka broker đang khả dụng?
3. Khi inbound polling endpoint bị stop, điều gì có thể xảy ra với một lần poll đã bắt đầu trước đó?
4. Nếu inbound adapter gửi vào DirectChannel trong khi consumer endpoint đã stop, có thể gặp lỗi gì?
5. Một QueueChannel có message đang chờ nhưng outbound polling consumer đang dừng. Khi resume, cần kiểm tra những gì?
6. Trong ví dụ Java DSL, vì sao file đầu vào chưa được xử lý trước khi gọi **resume()**?
7. Tại sao nên start downstream trước inbound, và stop inbound trước downstream trong nhiều hệ thống?
8. Vì sao Kafka offset commit, JMS ACK và bộ lọc file có thể làm thay đổi khả năng khôi phục sau restart?
9. Một endpoint đang running nhưng liên tục poll rỗng. Bạn cần những chỉ số nào để xác định đây là hoạt động bình thường hay lỗi?
10. Khi HTTP gateway timeout đúng lúc ứng dụng dừng, vì sao gửi lại request phải cân nhắc idempotency?

## Tổng kết

**Vòng đời endpoint** là cơ chế điều khiển khi các adapter, listener và consumer bắt đầu hoặc ngừng chuyển giao message trong Spring Integration. **Lifecycle/SmartLifecycle** cung cấp start, stop, isRunning, autoStartup và phase để phối hợp quá trình khởi động/dừng. Tuy nhiên, **đang chạy** khác với **kết nối sẵn sàng** và **nghiệp vụ hoàn tất**. Với file, SFTP, HTTP, JMS, AMQP, Kafka hay database, cần quan sát đồng thời trạng thái endpoint, poller/listener, MessageChannel, backlog, xác nhận giao nhận và tài nguyên kết nối. Một thiết kế an toàn sẽ bật downstream trước khi nhận dữ liệu, dừng nguồn nhận trước khi đóng phần xử lý, đồng thời sử dụng checkpoint, retry và idempotency phù hợp để phục hồi sau sự cố.
