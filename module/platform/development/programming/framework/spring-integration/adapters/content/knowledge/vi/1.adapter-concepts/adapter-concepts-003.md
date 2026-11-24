# Luồng outbound gửi message đến hệ thống ngoài

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả đường đi của message từ **MessageChannel**, qua **outbound channel adapter**, đến hệ thống bên ngoài.
- Phân biệt outbound adapter một chiều với outbound gateway theo nhu cầu phản hồi nghiệp vụ.
- Xác định trách nhiệm của channel, handler, converter, payload, headers và kết nối trong một lần gửi.
- Xây dựng luồng Java DSL xuất CSV ra file bằng outbound adapter và kiểm chứng kết quả.
- Phân tích retry, gửi trùng, thời điểm xác nhận, giao dịch, tốc độ gửi và vòng đời kết nối.

## 1. Outbound nằm ở đâu trong kiến trúc messaging?

Sau khi nhận và xử lý dữ liệu, ứng dụng thường cần đưa kết quả sang hệ thống khác: xuất tệp CSV cho đối tác, đẩy sự kiện lên Kafka, gửi message qua JMS/AMQP, gọi HTTP API, tải tệp lên SFTP hoặc cập nhật cơ sở dữ liệu. Mỗi đích có giao thức, định dạng, chính sách xác nhận và giới hạn tài nguyên riêng. Nếu logic nghiệp vụ trực tiếp quản lý từng client, việc thay đổi hệ thống đích sẽ kéo theo nhiều sửa đổi không cần thiết.

Trong **Spring Integration**, các endpoint trao đổi đối tượng **Message** thông qua **MessageChannel**. **Outbound channel adapter** là endpoint ở biên ra: nó nhận message từ một channel rồi thực hiện thao tác ghi/gửi đến hệ thống ngoài. Bộ xử lý nghiệp vụ có thể tạo dữ liệu chuẩn mà không phải biết chi tiết kết nối file, SFTP, HTTP, JMS, AMQP, Kafka hay database.

Ví dụ, service xử lý đơn hàng tạo một message mô tả đơn hàng đã duyệt. Message đi qua channel đến outbound adapter ghi CSV vào thư mục trao đổi với đối tác. Nếu đích chuyển sang Kafka, có thể giữ phần xử lý nghiệp vụ phía trước và điều chỉnh bước chuẩn hóa dữ liệu, adapter cùng hợp đồng giao nhận của đích mới.

~~~mermaid
flowchart LR
    A["Nghiệp vụ / Transformer<br/>tạo message"] --> C["MessageChannel<br/>outboundOrders"]
    C --> O["Outbound channel adapter<br/>Message handler"]
    O --> X["Hệ thống ngoài<br/>File / SFTP / HTTP / JMS<br/>AMQP / Kafka / Database"]
    O -. "Lỗi hoặc xác nhận ở cấp giao thức" .-> E["Error handling<br/>Retry / Observability"]
~~~

**Outbound được xác định từ góc nhìn của ứng dụng Spring Integration.** Message có thể do inbound adapter, transformer, service activator hoặc một service Java tạo ra. Endpoint được gọi là outbound adapter vì nó **tiêu thụ message để tác động lên một hệ thống ngoài**.

## 2. Đường đi từ MessageChannel đến hệ thống đích

Một lượt gửi có thể chia thành bảy giai đoạn:

| Giai đoạn | Thành phần | Trách nhiệm |
| --- | --- | --- |
| 1. Chuẩn bị | Handler, transformer hoặc ứng dụng | Tạo payload đúng định dạng và thêm headers cần thiết |
| 2. Gửi nội bộ | Producer | Gửi Message đến MessageChannel |
| 3. Phân phối | MessageChannel | Gọi subscriber hoặc lưu message để consumer lấy sau |
| 4. Tiêu thụ | Outbound endpoint | Nhận message, đọc payload và headers |
| 5. Ánh xạ | Adapter/converter | Tạo file, HTTP request, record broker hoặc lệnh ghi |
| 6. I/O | Client, session hoặc connection | Thực hiện thao tác với hệ thống bên ngoài |
| 7. Kết quả | Adapter và xử lý lỗi | Ghi nhận kết quả theo giao thức hoặc phát hiện lỗi |

Cần phân biệt ba thời điểm:

1. **Message đã được channel chấp nhận:** chưa chắc hệ thống ngoài đã nhận dữ liệu.
2. **Adapter đã thực hiện thao tác gửi:** mức xác nhận phụ thuộc giao thức, client và cấu hình.
3. **Nghiệp vụ của hệ thống đích đã hoàn thành:** có thể diễn ra muộn hơn hoặc chỉ được biết qua luồng phản hồi riêng.

Ví dụ, Kafka producer được broker xác nhận đã lưu record không có nghĩa consumer cuối đã xử lý record đó. Một HTTP API trả 202 Accepted có thể mới tiếp nhận công việc bất đồng bộ. Ghi file thành công cũng không chứng minh đối tác đã đọc file.

## 3. Outbound adapter và outbound gateway khác nhau thế nào?

**Outbound channel adapter** có mô hình **one-way**: nhận message, tạo tác động ra bên ngoài và không đưa một message phản hồi nghiệp vụ trở lại flow. **Outbound gateway** phục vụ **request–reply**: gửi request, nhận response và phát response thành message để flow tiếp tục xử lý.

| Nhu cầu | Thành phần nên cân nhắc | Ví dụ |
| --- | --- | --- |
| Gửi dữ liệu, flow không cần body trả về | Outbound channel adapter | Ghi file, phát event Kafka, gửi JMS message |
| Phải sử dụng phản hồi để quyết định bước sau | Outbound gateway | HTTP API trả mã giao dịch hoặc thông tin khách hàng |
| Nhận dữ liệu từ nguồn ngoài vào channel | Inbound adapter | Quét file từ thư mục |
| Nguồn bên ngoài gọi vào và chờ kết quả | Inbound gateway | HTTP POST trả response theo kết quả xử lý |

~~~mermaid
flowchart TB
    subgraph A["Adapter: one-way"]
      A1["MessageChannel"] --> A2["Outbound adapter"] --> A3["Hệ thống đích"]
    end
    subgraph B["Gateway: request-reply"]
      B1["Request channel"] --> B2["Outbound gateway"] --> B3["Hệ thống đích"]
      B3 --> B2
      B2 --> B4["Reply channel"]
    end
~~~

**One-way không đồng nghĩa với không có lỗi hay hoàn toàn bất đồng bộ.** Adapter vẫn có thể chờ ghi file, nhận xác nhận ở mức client hoặc ném exception. Điểm phân biệt nằm ở **hợp đồng phản hồi nghiệp vụ trong messaging flow**.

Khi phân tích yêu cầu, hãy hỏi: *Bước tiếp theo có cần dữ liệu phản hồi của hệ thống đích hay không?* Nếu có, gateway hoặc một cơ chế phản hồi bất đồng bộ có correlation ID sẽ phù hợp hơn. Nếu chỉ cần gửi/ghi và quản lý thành bại theo cơ chế của client, outbound adapter thường đủ.

## 4. Hợp đồng message tại biên outbound

Message gồm **payload** và **headers**. Adapter phải có khả năng biến các thông tin này thành thao tác mà hệ thống đích hiểu được.

~~~text
Message
├── payload: String / byte[] / File / DTO / ...
└── headers
    ├── id, timestamp
    ├── correlationId hoặc traceId (nếu có)
    └── metadata dành cho adapter đích (nếu cấu hình)
                 |
                 v
          Outbound adapter
                 |
                 v
       File / HTTP / JMS / Kafka / SFTP / DB
~~~

Ví dụ về hợp đồng:

- **File:** nội dung file và tên file, chế độ xử lý trùng tên, thư mục đích.
- **HTTP:** URL, method, body, Content-Type và các HTTP header được ánh xạ.
- **JMS/AMQP:** payload được convert theo hợp đồng message của broker, destination hoặc routing key, các thuộc tính giao nhận.
- **Kafka:** topic, key, value, serializer; metadata broker không tự tương đương headers nội bộ.
- **Database:** dữ liệu/câu lệnh cập nhật, khóa bản ghi, ranh giới giao dịch và chính sách xung đột.

| Quyết định | Câu hỏi cần trả lời |
| --- | --- |
| Kiểu payload | Adapter hỗ trợ trực tiếp hay cần transformer/converter? |
| Định dạng | CSV, JSON, XML, byte hoặc record theo schema/version nào? |
| Đích gửi | Tên file, topic, queue, URL hay bảng được xác định ở đâu? |
| Metadata | Header nào được ánh xạ sang giao thức ngoài, header nào chỉ dùng nội bộ? |
| Định danh nghiệp vụ | Event ID/order ID nào giữ ổn định giữa các lần retry? |
| An toàn dữ liệu | Có lộ credential hoặc thông tin nhạy cảm trong log, URL, tên file không? |
| Thay đổi hợp đồng | Đối tác xử lý version mới và lỗi định dạng như thế nào? |

Nên chuẩn hóa dữ liệu **trước** adapter. Ví dụ, handler tạo đối tượng OrderExport; transformer chuyển thành CSV khi xuất file hoặc JSON khi phát Kafka. Cách này hạn chế việc mã nghiệp vụ phải phụ thuộc vào định dạng giao tiếp.

## 5. Ví dụ Java DSL: gửi CSV từ MessageChannel ra file

Ví dụ sau tạo một **DirectChannel** tên exportChannel. Một service gửi message chứa nội dung CSV và header tên file. Outbound adapter tiêu thụ message rồi ghi ra thư mục **./data/export**.

Với Spring Boot, sử dụng các dependency của Spring Integration (thường qua spring-boot-starter-integration) và **spring-integration-file** tương thích với phiên bản Spring Boot. Ví dụ minh họa đường gửi một chiều, không thực hiện nghiệp vụ xuất đơn hàng hoàn chỉnh.

### 5.1. Định nghĩa channel và adapter

~~~java
import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OutboundFileConfiguration {

    @Bean
    public MessageChannel exportChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow exportFileFlow() {
        return IntegrationFlow.from("exportChannel")
            .handle(Files.outboundAdapter(new File("./data/export"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(FileHeaders.FILENAME))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }
}
~~~

**Giải thích các cấu hình:**

1. **exportChannel():** channel nhận message từ producer.
2. **IntegrationFlow.from("exportChannel"):** kết nối flow với channel; outbound adapter là subscriber.
3. **Files.outboundAdapter(...):** tạo endpoint để ghi dữ liệu ra file đích.
4. **autoCreateDirectory(true):** cho phép tạo thư mục đích nếu chưa tồn tại và ứng dụng có quyền ghi.
5. **fileNameGenerator(...):** lấy tên file từ header FileHeaders.FILENAME. Producer phải cung cấp tên file hợp lệ.
6. **fileExistsMode(FileExistsMode.FAIL):** báo lỗi nếu file đã tồn tại, giúp không vô tình ghi đè trong ví dụ.
7. **handle(...):** thực hiện side effect một chiều. Flow không tiếp tục bằng response nghiệp vụ từ file adapter.

### 5.2. Service gửi message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderExportService {

    private final MessageChannel exportChannel;

    public OrderExportService(
            @Qualifier("exportChannel") MessageChannel exportChannel) {
        this.exportChannel = exportChannel;
    }

    public void export(String orderId, long total) {
        // Thực tế phải kiểm tra orderId trước khi dùng làm tên file.
        String csv = "orderId,total\n" + orderId + "," + total + "\n";

        Message<String> message = MessageBuilder.withPayload(csv)
            .setHeader(FileHeaders.FILENAME, "order-" + orderId + ".csv")
            .build();

        boolean accepted = exportChannel.send(message);
        if (!accepted) {
            throw new IllegalStateException("Không gửi được message");
        }
    }
}
~~~

Khi gọi service với order ID **O-1001** và tổng tiền **150000**, adapter sẽ cố ghi file **./data/export/order-O-1001.csv**:

~~~csv
orderId,total
O-1001,150000
~~~

Với DirectChannel, handler thường chạy đồng bộ trên luồng gọi gửi. Nếu thao tác ghi file ném exception, lỗi có thể lan ngược về caller; không phải lúc nào phương thức send cũng chỉ trả về false. Khi thay channel bằng loại bất đồng bộ hoặc queue, giá trị trả về từ send **không còn đủ để suy ra file đã được ghi**.

**Giới hạn ví dụ:** chưa xử lý CSV escaping khi dữ liệu chứa dấu phẩy hoặc xuống dòng, chưa kiểm tra tên file trước nguy cơ đi ra ngoài thư mục, chưa có cơ chế retry/đối soát và chưa có quy ước công bố file hoàn tất. Với môi trường thật cần dùng CSV encoder, xác thực tên file, quyết định chính sách trùng tên và bàn giao file an toàn.

### 5.3. Bài thực hành kiểm chứng

1. Khởi động ứng dụng có hai class trên.
2. Gọi phương thức export của OrderExportService với ID **O-1001** và tổng **150000**, từ một test tích hợp hoặc một điểm gọi thích hợp.
3. Kiểm tra file xuất hiện trong thư mục **./data/export**, chứa hai dòng CSV như ví dụ.
4. Gọi lại cùng ID: chính sách **FileExistsMode.FAIL** sẽ từ chối ghi đè lên file đã tồn tại.
5. Gửi một ID khác để thấy adapter tiếp tục xuất file mới.

Không nên coi kiểm tra bước gọi send là xác nhận đối tác đã nhận dữ liệu. Với file phải kiểm tra file đích; với broker cần xét producer acknowledgment; với nghiệp vụ cần chứng cứ riêng về việc đối tác xử lý.

## 6. Vai trò của MessageChannel đối với tốc độ và thời điểm gửi

Adapter tiêu thụ message nhưng **channel đứng trước nó** quyết định cách message tới handler:

| Loại channel | Cách phân phối | Hệ quả ở outbound |
| --- | --- | --- |
| **DirectChannel** | Subscriber thường chạy ngay trên luồng gửi | I/O chậm có thể giữ luồng producer; lỗi đồng bộ dễ lan ngược |
| **ExecutorChannel** | Giao việc cho executor | Producer có thể tiếp tục sớm; cần kiểm soát thread pool, queue và lỗi bất đồng bộ |
| **QueueChannel** | Đệm message, consumer chủ động lấy | Cần polling consumer; phải chọn capacity và cách xử lý khi queue đầy |
| **PublishSubscribeChannel** | Phát tới nhiều subscriber | Có thể gửi ra nhiều đích; cần xét thất bại từng nhánh và xử lý thành công một phần |

### 6.1. Outbound có cần poller không?

Với DirectChannel hoặc ExecutorChannel, endpoint thường được kích hoạt khi message đến. **Không cần poller chỉ vì đây là outbound adapter.** Nhưng nếu adapter lấy message từ một **PollableChannel** như QueueChannel, một polling consumer cần chủ động lấy message khỏi queue.

~~~mermaid
flowchart LR
    P["Producer"] --> Q["QueueChannel<br/>message chờ"]
    T["Poller của consumer<br/>quy định nhịp lấy"] -.-> Q
    Q --> O["Outbound adapter"]
    O --> D["Hệ thống ngoài"]
~~~

Poller ở sơ đồ này điều phối **lấy message từ channel nội bộ để gửi**, khác với poller của inbound file/SFTP/database adapter vốn chủ động hỏi **nguồn ngoài để nhận**.

QueueChannel mặc định sử dụng bộ nhớ. Nếu ứng dụng dừng đột ngột, message trong queue chưa chắc còn tồn tại. Khi cần lưu bền và khôi phục message chờ gửi, phải thiết kế backing store thích hợp hoặc dùng outbox/hàng đợi bền vững.

### 6.2. Backpressure và nghẽn tải

Nếu upstream tạo 1.000 message/giây nhưng hệ thống đích chỉ chịu 100 message/giây, backlog sẽ tăng. Chuyển từ DirectChannel sang ExecutorChannel không tự tạo thêm năng lực ở đích; nó có thể chỉ chuyển điểm nghẽn thành hàng đợi tác vụ. Cần giới hạn số request đồng thời, dung lượng hàng đợi, nhịp gửi, thời gian chờ và chính sách retry phù hợp.

## 7. Khi gửi sang từng loại hệ thống ngoài

Vai trò chung là giống nhau, nhưng điểm xác nhận và ràng buộc I/O phụ thuộc công nghệ:

| Đích | Thao tác thường gặp | Điều cần cân nhắc |
| --- | --- | --- |
| **File** | Ghi payload ra ổ đĩa | Tên file, trùng tên, quyền ghi, trạng thái file hoàn tất |
| **SFTP** | Tải file lên thư mục từ xa | Session, xác thực, timeout, reconnect, tên tạm và rename |
| **HTTP** | Gửi request đến API | URL, method, headers, status, timeout; cần response trong flow thì dùng gateway |
| **JMS** | Gửi message tới destination | Converter, transaction, producer config và chính sách broker |
| **AMQP** | Publish qua exchange/routing key | Publisher confirm/return khi cần, routing và requeue/dlq ở hệ thống nhận |
| **Kafka** | Publish record topic/key/value | Serializer, partition ordering, producer acknowledgment, retry và transaction |
| **Database** | Ghi/cập nhật dữ liệu qua JDBC | Câu lệnh cập nhật, khóa duy nhất, deadlock và ranh giới transaction |

**Với file/SFTP:** nếu đối tác liên tục quét thư mục, họ có thể nhìn thấy file trước khi ghi xong. Thường cần quy ước **ghi tên tạm → ghi hoàn tất → đổi tên/công bố**. Tính nguyên tử của thao tác rename phụ thuộc filesystem hoặc SFTP server; cần kiểm tra thực tế.

**Với HTTP:** nhận mã 2xx có thể chỉ chứng minh API tiếp nhận request. Đặc biệt HTTP 202 Accepted thường biểu thị công việc sẽ xử lý tiếp. Nếu cần sử dụng response body cho bước sau, outbound gateway phù hợp hơn outbound adapter.

**Với JMS/AMQP/Kafka:** xác nhận của producer/broker khác với xác nhận consumer đã thực hiện nghiệp vụ. Khi kết nối bị mất ngay sau khi gửi, trạng thái có thể không rõ; retry có nguy cơ tạo thêm bản sao. Cần khóa idempotency ở hệ thống nhận và chính sách xác nhận phù hợp.

**Với database:** thành công của một câu lệnh cập nhật thường thuộc transaction của cơ sở dữ liệu đó. Không mặc định transaction này bao phủ cả HTTP/SFTP/Kafka được gọi tiếp theo.

## 8. Lỗi outbound xuất hiện ở đâu?

Một luồng gửi có thể thất bại trước khi chuyển đổi payload, khi kết nối, trong lúc gửi hoặc sau khi đích đã chấp nhận nhưng chưa trả xác nhận.

~~~mermaid
flowchart TD
    M["Message từ channel"] --> V{"Hợp đồng message hợp lệ?"}
    V -- "Không" --> B["Cách ly dữ liệu hoặc sửa hợp đồng"]
    V -- "Có" --> S["Outbound adapter gửi"]
    S --> R{"Kết quả theo client"}
    R -- "Thành công" --> OK["Ghi nhận tiến độ theo chính sách"]
    R -- "Lỗi tạm thời" --> RET["Retry có giới hạn và backoff"]
    R -- "Không rõ trạng thái" --> UN["Đối soát + idempotency"]
    R -- "Lỗi không phục hồi" --> DL["Cách ly / cảnh báo"]
    RET --> S
~~~

Các lỗi điển hình:

- **Hợp đồng sai:** payload không được hỗ trợ, JSON serialize lỗi, tên file trống hoặc topic không hợp lệ.
- **Kết nối:** timeout, DNS, SFTP session bị đóng, broker không sẵn sàng.
- **Đích từ chối:** HTTP 4xx/5xx, thiếu quyền ghi, database constraint violation hoặc routing sai.
- **Trạng thái không rõ:** request đã rời client nhưng mất kết nối trước khi nhận acknowledgment.
- **Quá tải:** pool kết nối cạn, executor queue đầy, hệ thống đích giới hạn request.

### 8.1. Retry và idempotency

Retry có thể phục hồi lỗi tạm thời, nhưng có rủi ro tạo tác động lặp nếu trạng thái lần gửi trước không rõ. Chẳng hạn gọi API tạo đơn hàng thành công nhưng client timeout; retry không có khóa idempotency có thể tạo hai đơn hàng.

Một chiến lược gửi an toàn cần:

1. Phân loại lỗi **có thể thử lại** và lỗi **cần sửa dữ liệu/cấu hình**.
2. Giới hạn số lần retry, dùng backoff phù hợp để bảo vệ đích.
3. Giữ khóa nghiệp vụ ổn định, ví dụ **partnerId + orderId** hoặc event ID, qua các lần thử.
4. Có nơi lưu message lỗi hoặc trạng thái chưa hoàn tất để xử lý tiếp.
5. Đối soát với đích khi không biết chắc lần gửi trước đã thành công hay chưa.

**Message ID mới** được tạo khi dựng lại một Message không nhất thiết là khóa nhận diện nghiệp vụ ổn định. Với gửi lại, nên chọn identity do hợp đồng nghiệp vụ quy định.

### 8.2. Đường lỗi đồng bộ và bất đồng bộ

Với **DirectChannel**, exception của outbound handler có thể truyền ngược về producer. Với **ExecutorChannel** hoặc consumer lấy từ queue, lỗi có thể phát sinh sau khi producer đã hoàn tất bước gửi vào channel. Tùy cấu hình, Spring Integration có thể đưa ErrorMessage vào **errorChannel**, hoặc adapter/client dùng error handler và callback riêng.

Không nên cho rằng errorChannel mặc định tự xử lý tất cả lỗi, tự retry hoặc tự lưu message chưa gửi. Cần kiểm tra cơ chế lỗi của endpoint, kiểu channel và client đang dùng, rồi thiết kế rõ retry, dead-letter/cách ly hoặc đối soát.

## 9. Giao dịch và bảo đảm giao nhận

Khi tích hợp nhiều hệ thống, cần tách các khái niệm:

| Mốc | Điều đã biết | Điều chưa chắc |
| --- | --- | --- |
| Channel chấp nhận message | Producer đã đưa message vào cơ chế chuyển giao của channel | Đích ngoài đã nhận |
| Client/adapter báo thành công | Thao tác đạt mức xác nhận mà client hỗ trợ và đang cấu hình | Bên nhận đã hoàn thành nghiệp vụ |
| Có xác nhận nghiệp vụ từ đối tác | Hoàn thành theo hợp đồng nghiệp vụ đã thống nhất | Retry sau này tự động an toàn nếu thiếu idempotency |

Ví dụ, hệ thống ghi đơn hàng vào database rồi gửi event OrderCreated lên Kafka. Nếu tiến trình dừng **sau khi ghi database nhưng trước khi gửi event**, đối tác không biết có đơn hàng mới. Nếu Kafka đã nhận event nhưng ứng dụng chưa ghi nhận trạng thái đã gửi, lần chạy lại có thể gửi trùng.

**Transactional outbox** là mẫu thường dùng: thay đổi nghiệp vụ và bản ghi outbox được lưu trong cùng transaction của database; một worker đọc outbox rồi gửi message ra đích và ghi nhận tiến độ. Consumer phía đích vẫn cần idempotency vì các lần phát lại có thể xảy ra.

Không thể suy ra **exactly-once end-to-end** chỉ vì sử dụng outbound adapter. Một database transaction không tự bao phủ file system, SFTP, HTTP và Kafka cùng lúc. Nếu có cơ chế giao dịch riêng của broker hoặc JDBC, phạm vi bảo đảm cần được mô tả đúng theo tài nguyên được hỗ trợ.

## 10. Vòng đời kết nối và khả năng quan sát

Outbound adapter sử dụng tài nguyên như HTTP client, socket, SFTP session factory, JMS/AMQP connection factory, Kafka producer hay JDBC connection pool. Các tài nguyên này cần cấu hình thời gian chờ, số kết nối, xác thực, phục hồi kết nối và đóng khi ứng dụng dừng.

Một bảng kiểm vận hành hữu ích:

| Khía cạnh | Quan sát hoặc cấu hình |
| --- | --- |
| Lưu lượng | Message đã yêu cầu gửi, số thao tác gửi thành công/thất bại |
| Độ trễ | Thời gian gửi, timeout, thời gian chờ trong queue |
| Tồn đọng | Queue depth, outbox chưa xử lý, producer buffer, message lỗi |
| Độ tin cậy | Số lần retry, gửi trùng, trạng thái không rõ, kết quả đối soát |
| Kết nối | Session còn sống, lỗi xác thực, reconnect, giới hạn connection pool |
| Truy vết | Correlation ID, event ID, tên hệ thống đích, mã lỗi phù hợp |
| Bảo mật | Credential lưu an toàn, log không in payload nhạy cảm, kiểm soát đường dẫn và URL |

Nếu tốc độ tạo message cao hơn khả năng gửi lâu dài, phải áp dụng giới hạn tải, capacity, backoff hoặc hàng đợi bền vững. Không tăng concurrency vô hạn với hy vọng đích sẽ nhanh lên.

## 11. Tình huống tổng hợp: gửi đơn hàng ra file và Kafka

Giả sử sau khi ghi nhận đơn hàng, ứng dụng phải xuất file CSV cho đối tác và phát event Kafka cho hệ thống phân tích. Một thiết kế đáng cân nhắc:

~~~mermaid
flowchart LR
    A["OrderService"] --> DB[("Database")]
    DB --> OUT["Outbox: OrderExportEvent"]
    OUT --> P["Worker xuất bản"]
    P --> T["Chuẩn hóa payload + headers"]
    T --> R{"Router"}
    R --> CF["fileExportChannel"]
    R --> CK["kafkaExportChannel"]
    CF --> AF["File outbound adapter"]
    CK --> AK["Kafka outbound adapter"]
    AF --> F["Thư mục đối tác"]
    AK --> K["Kafka topic"]
    AF -. "Trạng thái / lỗi" .-> ST["Theo dõi và đối soát"]
    AK -. "Trạng thái / lỗi" .-> ST
~~~

Hai nhánh có hợp đồng riêng. Nhánh file cần tên file an toàn, định dạng CSV và quy ước chỉ công bố sau khi hoàn tất; nhánh Kafka cần topic, key, serializer và producer acknowledgment. **Router không biến hai thao tác ngoài hệ thống thành một transaction nguyên tử.** Nếu một nhánh thành công và một nhánh thất bại, cần lưu trạng thái theo từng đích để tiếp tục phần còn thiếu, tránh phát lại vô điều kiện cả hai nhánh.

Khóa nghiệp vụ như orderId/eventId nên giữ ổn định ở cả hai đích. Với đối tác có nhu cầu xác nhận nghiệp vụ, có thể thiết kế một luồng phản hồi/đối soát riêng để phân biệt **đã gửi** và **đã được xử lý**.

## 12. Các lỗi thiết kế thường gặp

**Nhầm outbound adapter với gateway.** Adapter một chiều không cung cấp response nghiệp vụ cho flow. Nếu bước sau cần response, hãy chọn gateway hoặc thiết kế cơ chế phản hồi bất đồng bộ có correlation ID.

**Dùng kết quả send để khẳng định đối tác đã xử lý.** Với channel bất đồng bộ, queue hoặc broker, send thành công có thể chỉ phản ánh một mốc trung gian.

**Đưa mọi DTO trực tiếp cho mọi adapter.** Mỗi đích có yêu cầu định dạng, serializer và header mapping riêng; nên đặt transformer ở ranh giới phù hợp.

**Retry vô hạn khi gặp lỗi.** Có thể gây nghẽn tải, ghi trùng và che giấu lỗi dữ liệu không thể phục hồi.

**Cho rằng QueueChannel mặc định lưu bền.** Hàng đợi trong bộ nhớ không tự bảo toàn message qua sự cố tiến trình.

**Gửi file mà không thống nhất dấu hiệu hoàn tất.** Đối tác có thể đọc file dở dang nếu quét thư mục quá sớm.

**Coi nhiều đích gửi là một kết quả duy nhất.** File và Kafka có thể thành công hoặc thất bại độc lập; cần theo dõi, phục hồi và đối soát mỗi đích.

## 13. Câu hỏi tự kiểm tra

1. Outbound channel adapter nhận message từ đâu và kết thúc trách nhiệm ở đâu?
2. Vì sao một outbound adapter vẫn có thể chặn luồng và ném exception dù được gọi là **one-way**?
3. Khi nào outbound HTTP gateway phù hợp hơn outbound HTTP adapter?
4. Khác biệt giữa outbound adapter tiêu thụ từ DirectChannel và QueueChannel là gì? Khi nào cần poller?
5. Một Kafka producer mất kết nối sau khi phát record nhưng trước khi nhận acknowledgment. Vì sao retry có nguy cơ tạo trùng?
6. Tại sao FileExistsMode.FAIL trong ví dụ chỉ giải quyết việc không ghi đè file và chưa bảo đảm idempotency toàn luồng?
7. Nếu xuất đơn hàng sang file và Kafka, trong khi chỉ một nhánh gửi thành công, cần lưu trạng thái nào để phục hồi an toàn?

## Tổng kết

**Luồng outbound** chuyển message từ hệ thống nội bộ qua MessageChannel đến **outbound channel adapter**, nơi payload và headers được ánh xạ thành thao tác với hệ thống ngoài. Adapter phù hợp với giao tiếp một chiều; outbound gateway phục vụ request–reply. Để gửi tin cậy, phải thiết kế đồng thời hợp đồng message, cách chuyển giao của channel, điểm xác nhận, retry/idempotency, giao dịch và khả năng quan sát. Những nguyên tắc này áp dụng cho file, SFTP, HTTP, JMS, AMQP, Kafka và database, dù cơ chế I/O và vòng đời của từng adapter khác nhau.
