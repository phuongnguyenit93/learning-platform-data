# Luồng inbound đưa dữ liệu vào MessageChannel

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích đường đi của dữ liệu từ hệ thống ngoài, qua inbound channel adapter, thành một Spring Integration Message và vào MessageChannel.
- Phân biệt inbound adapter sử dụng poller với inbound adapter dựa trên sự kiện, đồng thời xác định khi nào cần inbound gateway.
- Nhận diện ảnh hưởng của DirectChannel, QueueChannel và ExecutorChannel đối với xử lý đồng bộ, độ trễ và khả năng chịu tải.
- Xây dựng luồng đọc tệp CSV vào MessageChannel bằng Spring Integration Java DSL và kiểm tra dữ liệu đến subscriber.
- Thiết kế hợp đồng payload/headers, xử lý lỗi, chống trùng lặp và quản lý vòng đời kết nối ở đầu vào.

## 1. Bối cảnh: từ nguồn ngoài đến mô hình message nội bộ

Một hệ thống tích hợp thường phải tiếp nhận dữ liệu theo nhiều cách: file được đặt vào thư mục, tệp trên SFTP, yêu cầu HTTP, thông điệp trong JMS/AMQP, bản ghi Kafka hoặc hàng dữ liệu mới trong cơ sở dữ liệu. Mỗi nguồn có cách kết nối, nhịp nhận, xác nhận và biểu diễn dữ liệu khác nhau. Nếu mọi xử lý nghiệp vụ đều trực tiếp sử dụng API của từng nguồn, việc đổi giao thức hoặc bổ sung nguồn mới sẽ kéo theo thay đổi ở nhiều nơi.

Trong **Spring Integration**, inbound channel adapter là điểm kết nối **từ hệ thống bên ngoài đi vào luồng messaging của ứng dụng**. Nó nhận hoặc truy xuất dữ liệu từ nguồn, tạo message theo hợp đồng đã cấu hình và gửi message đến một **MessageChannel**. Các thành phần phía sau channel có thể kiểm tra dữ liệu, chuyển đổi, định tuyến, lưu trữ hoặc gửi dữ liệu đi mà không phải trực tiếp mở kết nối đến nguồn ban đầu.

Thông điệp của Spring Integration gồm hai phần chính:

- **Payload:** dữ liệu mà bước tiếp theo cần xử lý, chẳng hạn đối tượng File, chuỗi JSON, mảng byte hoặc một DTO.
- **Headers:** thông tin đi kèm message, chẳng hạn mã định danh, thời điểm tạo, khóa tương quan và metadata đặc thù của adapter.

Điểm cần nhớ: **inbound adapter nhận dữ liệu, MessageChannel chuyển giao message, còn handler xử lý nội dung**. Ba vai trò có thể được cấu hình trong cùng một IntegrationFlow nhưng vẫn là những trách nhiệm khác nhau.

~~~mermaid
flowchart LR
    S["Hệ thống ngoài<br/>File / SFTP / JMS / Kafka / DB"] --> A["Inbound channel adapter"]
    P["Poller hoặc listener"] -. "Kích hoạt nhận" .-> A
    A --> M["Spring Message<br/>payload + headers"]
    M --> C["MessageChannel"]
    C --> H["Transformer / Filter / Handler"]
    H --> N["Luồng xử lý tiếp theo"]
~~~

Với nguồn HTTP, tùy mục đích có thể sử dụng inbound channel adapter hoặc inbound gateway. Khi caller cần phản hồi nghiệp vụ từ flow để tạo HTTP response, gateway là lựa chọn phù hợp hơn. Hướng **inbound** luôn tính từ bên ngoài **vào ứng dụng Spring Integration**.

## 2. Một thông điệp inbound được đưa vào channel như thế nào?

Có thể phân tích quá trình thành sáu giai đoạn:

| Giai đoạn | Thành phần thực hiện | Điều diễn ra |
| --- | --- | --- |
| 1. Nguồn có dữ liệu | File system, SFTP server, queue, topic, HTTP client, database | Dữ liệu mới hoặc sự kiện sẵn sàng để tiếp nhận |
| 2. Kích hoạt nhận | Poller hoặc listener/consumer | Poller chạy theo lịch; listener được đánh thức bởi sự kiện hoặc cơ chế consumer của giao thức |
| 3. Nhận dữ liệu | Inbound adapter, message source hoặc client tích hợp | Đọc file, nhận message từ broker, tiếp nhận request hoặc truy vấn nguồn |
| 4. Tạo message | Adapter và các converter được cấu hình | Xác định payload và headers; có thể chuyển đổi biểu diễn của dữ liệu |
| 5. Gửi vào channel | Inbound endpoint | Chuyển message qua MessageChannel theo ngữ nghĩa channel |
| 6. Tiêu thụ message | Subscriber hoặc polling consumer phía sau channel | Chạy transformer, filter, service activator hoặc một flow khác |

**Ranh giới số 5 rất quan trọng.** Message đã được channel chấp nhận không nhất thiết đồng nghĩa với nghiệp vụ đã hoàn thành hoặc hệ thống đích đã ghi dữ liệu. Với DirectChannel đồng bộ, việc gửi thường gọi handler ngay trên cùng luồng thực thi. Với channel bất đồng bộ hoặc channel lưu hàng đợi, bước gửi có thể kết thúc trước khi nghiệp vụ phía sau xử lý xong.

### 2.1. Polling inbound: ứng dụng chủ động hỏi nguồn

Một số nguồn không chủ động thông báo mỗi khi có dữ liệu. Khi đó Spring Integration dùng một **MessageSource** kết hợp **poller**. Trong mỗi lần kích hoạt, poller gọi cơ chế nhận của message source; nếu có dữ liệu thì tạo/gửi message vào channel, nếu chưa có thì chờ chu kỳ kế tiếp.

Ví dụ: mỗi 5 giây quét thư mục nhận file, chọn tối đa 5 tệp CSV hợp lệ theo bộ lọc, rồi chuyển từng đối tượng File vào channel. Cần phân biệt:

- **fixedDelay:** khoảng chờ giữa các lần chạy theo cách lập lịch fixed delay của poller, không phải cam kết thời gian giao nhận chính xác đến từng mili giây.
- **maxMessagesPerPoll:** giới hạn số message mà poller lấy trong một lần thực thi; không phải giới hạn tổng số message của ứng dụng.
- **Bộ lọc nguồn:** quyết định dữ liệu nào được coi là ứng viên nhận, chẳng hạn tên file hoặc trạng thái đã từng được chọn.
- **Consumer phía sau:** quyết định khả năng xử lý thực tế; tăng tốc polling mà không cải thiện downstream có thể làm tăng nghẽn tải.

Một file mới được nhìn thấy chưa chắc đã được hệ thống đối tác ghi xong. Trong môi trường thực tế, nên có quy ước ghi file tạm rồi đổi tên nguyên tử, tín hiệu hoàn tất, bộ lọc theo tuổi file hoặc cơ chế tương đương.

### 2.2. Event-driven inbound: nguồn hoặc client phát sự kiện

Với các nguồn hỗ trợ listener/consumer, adapter nhận sự kiện khi cơ chế lắng nghe của giao thức kích hoạt. Ví dụ, một JMS listener nhận message từ queue, một AMQP listener nhận delivery từ broker, hoặc một Kafka consumer nhận các record được broker cung cấp qua cơ chế poll của Kafka client.

**Không đồng nhất “Kafka consumer có poll nội bộ” với “Spring Integration poller cho MessageSource”.** Adapter message-driven của Kafka tự quản lý vòng đời consumer theo hạ tầng Kafka; người lập trình thường không cấu hình một Spring Integration Poller cho endpoint này.

| Tiêu chí | Polling inbound | Event-driven/message-driven inbound |
| --- | --- | --- |
| Cách kích hoạt | Lịch của Spring Integration poller | Listener, container hoặc consumer của giao thức |
| Ví dụ | Đọc thư mục, quét SFTP, truy vấn database | JMS, AMQP, Kafka, HTTP request |
| Điều chỉnh tải | Chu kỳ poll, batch và maxMessagesPerPoll | Concurrency, prefetch, batch, consumer settings và cơ chế acknowledgment |
| Rủi ro chính | Trễ giữa hai lần quét, nhận lại dữ liệu, đọc nguồn chưa hoàn chỉnh | Giao lại message, mất kết nối, quá tải listener, xử lý ack/offset không đúng |
| Vấn đề cần thiết kế | Lọc, thứ tự nhận, trạng thái sau restart | Điểm xác nhận, xử lý lỗi, restart và cân bằng tải |

Không có lựa chọn nào mặc nhiên bảo đảm không mất dữ liệu hoặc không trùng lặp. Bảo đảm thực tế phụ thuộc nguồn, adapter, channel, transaction và logic nghiệp vụ.

## 3. MessageChannel quyết định cách thông điệp đến người xử lý

Inbound adapter đưa message vào channel nhưng không tự xác định toàn bộ cách chạy của các thành phần phía sau. **Loại MessageChannel** quyết định cách phân phối message và mức độ phụ thuộc giữa nguồn và consumer.

| MessageChannel | Cách chuyển giao | Lưu ý đối với inbound |
| --- | --- | --- |
| DirectChannel | Gọi subscriber đồng bộ trên luồng gửi | Handler chậm có thể giữ luồng poller/listener; exception có thể truyền ngược theo cùng chuỗi gọi |
| ExecutorChannel | Giao xử lý cho executor | Cần giới hạn thread, queue capacity và cách xử lý khi executor quá tải; không mặc định bảo toàn thứ tự |
| QueueChannel | Đưa message vào hàng đợi để một consumer chủ động nhận | Cần consumer hoặc poller phía nhận; khả năng lưu bền tùy backing store, không tự có khi dùng mặc định |
| PublishSubscribeChannel | Phát message đến các subscriber | Phù hợp nhiều nhánh cùng nhận sự kiện; không mặc định là cơ chế chia tải cho nhiều worker |

### 3.1. Vì sao chọn channel trước khi tối ưu poller?

Giả sử inbound adapter có thể lấy 100 file/giây nhưng service activator chỉ xử lý 10 file/giây:

- Với DirectChannel, lần gửi message có thể phải chờ xử lý xong; tốc độ lấy dữ liệu tự nhiên bị giới hạn bởi consumer đồng bộ.
- Với ExecutorChannel, đầu vào có thể tiếp tục lấy file trong khi worker xử lý, nhưng hàng đợi tác vụ có thể đầy nếu tốc độ đến luôn vượt tốc độ xử lý.
- Với QueueChannel, message có thể được đệm trước khi xử lý, nhưng cần quyết định rõ capacity, thời gian tồn tại và chính sách khi queue đầy.

Đổi channel không tự tăng năng lực xử lý nghiệp vụ. Cần xác định throughput khả thi, thời gian xử lý, backlog cho phép và ngữ nghĩa giao nhận trước khi tăng concurrency.

### 3.2. Thành công của send khác với thành công của nghiệp vụ

Một lần gửi message đến channel có thể hoàn tất trong khi xử lý nghiệp vụ vẫn đang diễn ra ở luồng khác. Vì vậy:

1. **Đã nhận từ nguồn** không nhất thiết là **đã gửi đến channel**.
2. **Đã gửi đến channel** không nhất thiết là **đã ghi thành công xuống database hoặc hệ thống đích**.
3. **Đã nhận phản hồi ở cấp giao thức** không nhất thiết là **đã hoàn tất nghiệp vụ**.

Đây là lý do thiết kế inbound phải xem xét thời điểm acknowledgment/commit, cơ chế retry và cách chống xử lý trùng từ đầu.

## 4. Ví dụ Java DSL: File inbound adapter đưa CSV vào DirectChannel

Bài thực hành tạo một nguồn polling: cứ 5 giây quét thư mục **./data/inbox**, chọn tối đa 5 file **.csv** mỗi lượt, rồi gửi message có payload kiểu **File** vào channel tên **incomingFiles**. Một flow thứ hai đăng ký nhận từ channel đó và ghi thông tin cơ bản ra console.

Ví dụ sử dụng Spring Integration Java DSL. Với Spring Boot, cần starter tích hợp Spring Integration và module **spring-integration-file** tương thích với phiên bản Spring Boot/Spring Integration đang dùng. Không cần thêm version riêng khi đã dùng dependency management của Spring Boot.

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
public class InboundFileConfiguration {

    @Bean
    public MessageChannel incomingFiles() {
        return new DirectChannel();
    }

    // Bên tạo message: nguồn file -> MessageChannel
    @Bean
    public IntegrationFlow fileIngressFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                spec -> spec.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))
            .channel("incomingFiles")
            .get();
    }

    // Bên tiêu thụ: MessageChannel -> xử lý
    @Bean
    public IntegrationFlow fileConsumerFlow() {
        return IntegrationFlow.from("incomingFiles")
            .handle(File.class, (file, headers) -> {
                System.out.println(
                    "Nhan CSV: " + file.getName()
                    + ", kich thuoc: " + file.length() + " bytes");
                return null; // Kết thúc flow một chiều
            })
            .get();
    }
}
~~~

### 4.1. Diễn giải từng thành phần

1. **Files.inboundAdapter(...):** cấu hình file inbound adapter. Message source trả về đối tượng File đại diện cho tệp được chọn, không tự đọc và parse nội dung CSV thành đối tượng đơn hàng.
2. **autoCreateDirectory(true):** tạo thư mục đầu vào nếu chưa tồn tại theo cấu hình adapter; chỉ phù hợp khi ứng dụng có quyền thao tác trên vị trí đó.
3. **patternFilter("*.csv"):** chọn tệp phù hợp với mẫu tên. Bộ lọc theo đuôi file không kiểm tra CSV hợp lệ và không chứng minh file đã ghi xong.
4. **Pollers.fixedDelay(...):** thiết lập lịch gọi message source; **maxMessagesPerPoll(5)** giới hạn số message được lấy mỗi lượt.
5. **incomingFiles():** tạo DirectChannel. Adapter không gọi trực tiếp phương thức xử lý file; nó gửi message vào channel có tên này.
6. **IntegrationFlow.from("incomingFiles"):** flow tiêu thụ đăng ký nhận message trên channel và chạy handler với payload File.
7. **return null:** handler không sinh message trả về; luồng kết thúc sau khi xử lý. Ví dụ chỉ in metadata để minh họa việc chuyển giao, chưa thực hiện lưu đơn hàng hay di chuyển file.

Nếu muốn đọc nội dung CSV, hãy đặt một transformer hoặc service activator sau channel để chuyển payload từ File sang cấu trúc nghiệp vụ. Đối với file lớn, nên đọc dạng stream hoặc từng bản ghi thay vì nạp toàn bộ file vào bộ nhớ.

### 4.2. Thử nghiệm bằng tay

1. Khởi động ứng dụng có cấu hình trên; xác nhận thư mục **./data/inbox** được tạo hoặc tồn tại.
2. Tạo một file nhỏ **orders-001.csv** trong thư mục, chẳng hạn hai dòng **orderId,total** và **O-1001,150000**.
3. Quan sát console sau chu kỳ poller: tên file và kích thước xuất hiện khi handler nhận message.
4. Đặt thêm **readme.txt** để xác nhận bộ lọc không lựa chọn file ngoài mẫu.
5. Tắt và khởi động lại ứng dụng để quan sát chính sách nhận lại file. Muốn có hành vi ổn định qua restart cần thiết kế bộ lọc lưu trạng thái và quy trình chuyển/xóa file sau khi xử lý thành công.

**Giới hạn của ví dụ:** chỉ chứng minh luồng File → Message → DirectChannel → handler. Không xem log console là bằng chứng dữ liệu nghiệp vụ đã được lưu bền; không suy ra file tự bị xóa hay tự được chuyển vào thư mục archive.

## 5. Hợp đồng message tại ranh giới inbound

Để downstream xử lý được dữ liệu từ nhiều adapter, đội phát triển cần thống nhất **payload type**, các **headers quan trọng** và quy tắc chuyển đổi.

~~~text
Message<File>
├── payload: File("./data/inbox/orders-001.csv")
└── headers
    ├── id, timestamp
    └── metadata bổ sung (nếu adapter/converter cung cấp)

        |
        v
Transformer: đọc CSV, chuẩn hóa, kiểm tra định dạng
        |
        v
Message<OrderBatch> -> MessageChannel xử lý nghiệp vụ
~~~

Một số nguồn ngoài có thể mang thông tin như tên file từ xa, topic/partition/offset của Kafka, correlation ID hoặc headers của JMS/AMQP. Các giá trị cụ thể phụ thuộc adapter và cấu hình mapping. **Không giả định mọi message inbound đều có cùng tập headers**, hoặc headers chắc chắn được truyền nguyên vẹn sang giao thức đích.

| Câu hỏi | Ví dụ quyết định |
| --- | --- |
| Dữ liệu đầu vào là kiểu nào? | File, byte array, String, Map, DTO hoặc record của client |
| Nội dung đã được decode chưa? | Adapter chỉ nhận bytes hay converter đã chuyển JSON thành DTO? |
| Header nào phục vụ xử lý? | Source ID, correlation ID, loại sự kiện, tên file, khóa idempotency |
| Khóa nhận diện bản ghi là gì? | orderId, eventId, message ID do đối tác cam kết ổn định |
| Khi đổi nguồn thì hợp đồng đổi ra sao? | File → Kafka có thể đổi kiểu payload, metadata và thời điểm ack |
| Ai chịu trách nhiệm kiểm tra hợp lệ? | Converter/transformer kiểm tra cú pháp; handler hoặc validator kiểm tra nghiệp vụ |

Một cách thiết kế thuận lợi là chuẩn hóa dữ liệu gần ranh giới inbound: **source-specific payload → domain message ổn định**. Ví dụ File và SFTP cùng đi qua bước parse để tạo **OrderBatch** trước khi vào channel xử lý đơn hàng. Cách này giúp handler nghiệp vụ ít phụ thuộc vào chi tiết giao thức mà vẫn giữ metadata quan trọng để truy vết.

## 6. Các nguồn inbound thường gặp trong Spring Integration

Mặc dù đều đưa dữ liệu vào MessageChannel, adapter cho từng hệ thống có những điều kiện xử lý khác nhau:

| Nguồn | Kiểu inbound phổ biến | Điều cần cân nhắc |
| --- | --- | --- |
| File cục bộ | Polling file inbound adapter | File đã ghi xong chưa, bộ lọc nhận một lần, trạng thái qua restart |
| SFTP | Polling/đồng bộ file từ xa tùy cấu hình | Kết nối, phiên đăng nhập, file từ xa chưa hoàn tất, metadata và idempotency |
| HTTP | Inbound adapter hoặc inbound gateway | Phân biệt nhận một chiều với hợp đồng request–reply, status và timeout |
| JMS | Message-driven inbound adapter | Acknowledgment, transaction, redelivery, listener concurrency |
| AMQP | Message-driven inbound adapter | Ack/nack, prefetch, queue binding, requeue hoặc dead-letter |
| Kafka | Message-driven inbound adapter | Consumer group, partition/order, offset commit, retry và deserialization |
| Database | JDBC inbound adapter/polling query | Watermark, bản ghi mới, transaction, concurrency và chống đọc lại |

Ví dụ một đối tác trước đây đẩy CSV qua SFTP rồi chuyển sang Kafka: bước parsing có thể tái sử dụng **nếu hợp đồng domain giữ nguyên**, nhưng tầng inbound bắt buộc phải rà soát converter, metadata, nhịp tiêu thụ và cách xác nhận bản ghi. Kafka không có cơ chế “file đã hoàn tất” như SFTP; ngược lại, hệ thống phải quan tâm đến offset, consumer group và khả năng nhận lại record.

## 7. Xử lý lỗi trong luồng inbound

Lỗi có thể xảy ra **trước khi tạo message**, **khi gửi vào channel**, hoặc **khi subscriber xử lý**. Cần biết lỗi nằm ở ranh giới nào để chọn phương án phục hồi.

~~~mermaid
flowchart TD
    A["Nguồn ngoài"] --> B["Inbound adapter"]
    B --> C{"Nhận/đọc thành công?"}
    C -- "Không" --> E1["Log + retry/reconnect theo nguồn"]
    C -- "Có" --> D["MessageChannel"]
    D --> F{"Consumer xử lý thành công?"}
    F -- "Không" --> E2["Error flow / retry / cách ly message lỗi"]
    F -- "Có" --> G["Xác nhận tiến độ theo chính sách"]
    E1 -. "Nhận lại nếu phù hợp" .-> A
    E2 -. "Phục hồi có kiểm soát" .-> F
~~~

### 7.1. Lỗi đồng bộ và bất đồng bộ

Với **DirectChannel**, handler thường chạy trên cùng luồng gửi; exception của subscriber có thể truyền ngược đến phía inbound/poller và ảnh hưởng đến lần nhận hiện tại. Với **ExecutorChannel** hoặc luồng qua queue, lỗi có thể xuất hiện sau khi bước đưa vào channel đã kết thúc. Vì vậy, không thể dùng duy nhất kết quả send để kết luận nghiệp vụ thành công trên mọi cấu hình.

Tùy endpoint và cấu hình, Spring Integration có thể đưa lỗi vào **errorChannel** dưới dạng **ErrorMessage**. Với luồng polling, cần cấu hình và kiểm tra đường lỗi của poller; với JMS/AMQP/Kafka, cần phối hợp error handler của listener container, retry và chính sách ack tương ứng. Một errorChannel mặc định không thay cho chính sách retry hay dead-letter được thiết kế rõ ràng.

### 7.2. Retry, redelivery và idempotency

**Retry** giúp phục hồi lỗi tạm thời, ví dụ kết nối SFTP bị ngắt hoặc database quá tải. Nhưng nếu lỗi xảy ra sau khi đơn hàng đã được ghi mà trước khi nguồn ghi nhận thành công, dữ liệu có thể được nhận lại.

**Idempotency** ngăn việc xử lý lại cùng một sự kiện gây tác động nghiệp vụ trùng lặp. Các cách triển khai thường dùng:

- Tạo khóa xử lý ổn định, chẳng hạn **partnerId + orderId** hoặc event ID được đối tác bảo đảm duy nhất.
- Lưu kết quả xử lý/khóa đã nhận vào nơi lưu bền phù hợp với yêu cầu nghiệp vụ.
- Chỉ xác nhận hoặc commit tiến độ của nguồn tại điểm phù hợp với mức bảo đảm mong muốn.
- Với file, phối hợp bộ lọc bền vững, quy trình chuyển file sau khi xử lý và khả năng chạy lại an toàn.
- Với queue/broker, hiểu cách ack, nack, requeue và commit offset hoạt động khi handler lỗi.

Không nên tuyên bố **exactly-once end-to-end** chỉ vì sử dụng một adapter hay một loại channel. File system, broker và database có thể thuộc các giao dịch khác nhau. Nếu cần tính nhất quán, hãy cân nhắc idempotent consumer, outbox/inbox, transaction được hỗ trợ hoặc thao tác bù trừ.

## 8. Vòng đời inbound adapter, tải và khả năng quan sát

Inbound adapter thường gắn với tài nguyên có vòng đời riêng: scheduler, socket, SFTP session, JMS listener container, Kafka consumer hoặc connection pool. Khi ứng dụng khởi động, endpoint cần được đăng ký và bắt đầu nhận dữ liệu; khi dừng, các tác vụ và tài nguyên phải được đóng hoặc bàn giao theo chính sách đã định.

Tính sẵn sàng của kết nối không đồng nhất với tính sẵn sàng xử lý. Ví dụ, poller có thể chạy đúng lịch nhưng không đọc được file do quyền truy cập, hoặc Kafka consumer vẫn kết nối được nhưng downstream đã hết capacity.

| Khía cạnh vận hành | Cần theo dõi hoặc cấu hình |
| --- | --- |
| Khả năng nhận | Số message nhận, số lần poll trống, lần nhận cuối, trạng thái listener |
| Độ trễ | Thời gian từ khi sự kiện xuất hiện đến lúc được nhận và xử lý |
| Backlog | Số file chờ, queue depth, lag của Kafka consumer, hàng dữ liệu chưa xử lý |
| Lỗi | Lỗi kết nối, chuyển đổi dữ liệu, gửi channel, xử lý nghiệp vụ, retry hết lần |
| Thông lượng | Số message/giây và thời gian xử lý của downstream |
| An toàn dữ liệu | Số sự kiện trùng, số lần giao lại, số message bị cách ly, tính bền vững của checkpoint |

Đặc biệt, tăng **maxMessagesPerPoll**, số listener hoặc số worker cần đi kèm đánh giá capacity. Nếu nguồn cung cấp nhanh hơn khả năng xử lý liên tục, hệ thống phải áp dụng giới hạn đầu vào, backpressure, bộ đệm có kiểm soát hoặc chính sách phục hồi backlog.

Về bảo mật, cấu hình endpoint bằng credential/secret thích hợp; không in dữ liệu nhạy cảm nguyên văn trong log. Khi cần truy vết, ưu tiên correlation ID, event ID và thông tin trạng thái thay vì ghi toàn bộ payload.

## 9. Tình huống thiết kế: nhận đơn hàng từ đối tác

Một ứng dụng bán hàng nhận dữ liệu đơn hàng qua tệp CSV. Yêu cầu là mỗi đơn hàng hợp lệ chỉ được tạo một lần, kể cả khi đối tác truyền lại file hoặc ứng dụng khởi động lại.

Luồng đề xuất:

~~~mermaid
flowchart LR
    F["Thư mục nhận CSV"] --> I["File inbound adapter + poller"]
    I --> C1["rawFiles"]
    C1 --> T["Parse CSV"]
    T --> V["Kiểm tra nghiệp vụ"]
    V --> C2["validOrders"]
    C2 --> K["Kiểm tra idempotency key"]
    K --> DB[("Database")]
    V -. "Dữ liệu lỗi" .-> ER["Lưu thông tin lỗi để xử lý"]
~~~

Ở đây, **rawFiles** mang payload File, còn **validOrders** mang dữ liệu đã chuẩn hóa. Handler ghi database không cần biết file được lấy từ ổ đĩa hay SFTP. Tuy nhiên, việc bảo đảm mỗi đơn hàng chỉ được tạo một lần nên dựa vào khóa nghiệp vụ và ràng buộc ghi dữ liệu, thay vì chỉ dựa vào trạng thái bộ lọc file.

Nếu sau này nhận dữ liệu qua HTTP hoặc Kafka, có thể thay điểm inbound và bước chuyển đổi để tiếp tục phát message **validOrders** với cùng hợp đồng nghiệp vụ. Lúc đó vẫn phải thiết kế riêng thời điểm trả HTTP response hoặc commit Kafka offset sao cho phản ánh đúng mức hoàn tất được hệ thống cam kết.

## 10. Lỗi thiết kế thường gặp

**Cho rằng inbound adapter tự xử lý nghiệp vụ.** Adapter chủ yếu mang dữ liệu vào messaging flow; bước xác thực, parse và quy tắc nghiệp vụ cần được định vị rõ trong các endpoint phía sau.

**Đồng nhất MessageChannel với hàng đợi lưu bền.** DirectChannel chuyển đồng bộ; QueueChannel mặc định không tự bảo đảm lưu message qua restart. Phải chọn channel theo nhu cầu và cấu hình persistence nếu cần.

**Dùng poller cho mọi nguồn.** HTTP request, JMS/AMQP listener hay Kafka message-driven adapter có cơ chế nhận riêng. Spring Integration poller phù hợp với các nguồn cần chủ động truy vấn theo lịch.

**Đánh đồng được nhận với được xử lý thành công.** Thời điểm ack/commit cần phù hợp với đường lỗi, channel, handler và thao tác ghi hệ thống đích.

**Đọc file ngay khi nhìn thấy tên file.** File có thể chưa ghi xong; cần thống nhất giao thức bàn giao file với đối tác.

**Tăng tốc inbound không xét downstream.** Poller hoặc listener nhanh hơn handler có thể gây backlog, đầy queue hoặc tăng bộ nhớ và độ trễ.

## 11. Câu hỏi tự kiểm tra

1. Inbound channel adapter khác MessageChannel ở chỗ nào? Hãy mô tả một message đi qua hai thành phần này.
2. Khi một File inbound adapter được poller kích hoạt mà thư mục không có file phù hợp, chuyện gì xảy ra với chu kỳ nhận tiếp theo?
3. Vì sao dùng DirectChannel có thể khiến handler chậm ảnh hưởng trực tiếp đến tốc độ nhận message?
4. Nếu một broker giao lại message sau khi handler đã ghi đơn hàng thành công, hệ thống cần cơ chế nào để tránh tạo hai đơn hàng?
5. Nếu API HTTP yêu cầu trả về kết quả xử lý đơn hàng trong cùng request, nên cân nhắc inbound adapter hay inbound gateway? Vì sao?
6. Khi chuyển nguồn file sang Kafka, những phần nào của hợp đồng payload, headers và acknowledgment cần được kiểm tra lại?

## Tổng kết

**Luồng inbound** là đường đi có kiểm soát từ hệ thống ngoài đến **MessageChannel**: nguồn phát sinh dữ liệu, inbound adapter nhận dữ liệu, xây dựng message, channel chuyển giao cho consumer và các endpoint phía sau xử lý nghiệp vụ. Hiểu rõ từng ranh giới giúp chọn đúng poller hoặc listener, quản lý payload/headers nhất quán, tránh nghẽn tải và phục hồi an toàn khi kết nối hay xử lý gặp lỗi. Những nguyên tắc này áp dụng khi tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, dù cơ chế xác nhận và vòng đời của từng giao thức khác nhau.
