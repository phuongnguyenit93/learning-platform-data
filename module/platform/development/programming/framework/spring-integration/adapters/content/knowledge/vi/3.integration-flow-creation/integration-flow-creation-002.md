# @InboundChannelAdapter cho nguồn polling

## 1. Bối cảnh và mục tiêu

Trong chương **Tạo integration flow**, `@InboundChannelAdapter` là một cách khai báo **điểm vào (inbound endpoint) chạy theo lịch polling** bằng annotation của Spring Integration. Khi nguồn dữ liệu không chủ động đẩy sự kiện đến ứng dụng, endpoint sẽ định kỳ gọi một `MessageSource`, nhận message nếu có dữ liệu và gửi message vào `MessageChannel` để phần còn lại của integration flow xử lý.

Bài này thuộc module **SPRING_INTEGRATION_ADAPTERS**: kết nối các hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; kiểm soát hợp đồng message, lỗi và vòng đời kết nối.

Sau bài học, người học cần có khả năng:

- Phân biệt `@InboundChannelAdapter`, `MessageSource`, `@Poller` và `MessageChannel`.
- Tạo inbound endpoint bằng `@Bean` kết hợp `@InboundChannelAdapter`.
- Hiểu mỗi lần poll gọi `receive()` như thế nào, kể cả trường hợp không có dữ liệu.
- Cấu hình `fixedDelay`, `fixedRate`, `cron`, `maxMessagesPerPoll` theo đặc tính nguồn và đích.
- Nối adapter với flow xử lý bằng Java DSL, rồi áp dụng cho nguồn file hoặc nguồn cần polling tương tự.
- Thiết kế hành vi khi lỗi, xử lý trùng, dừng/khởi động và quan sát hoạt động của endpoint.

**Điểm cốt lõi:** `@InboundChannelAdapter` đăng ký endpoint lấy dữ liệu từ nguồn theo lịch. **Nó không tự xác định cách đọc file/SFTP/database**; việc đọc được triển khai bởi đối tượng `MessageSource` mà method tạo ra.

## 2. Cách hoạt động của inbound polling

Một flow polling thường gồm bốn phần có trách nhiệm rõ ràng:

~~~mermaid
flowchart LR
    TIMER["TaskScheduler / Poller"]
    ADAPTER["@InboundChannelAdapter<br/>gọi MessageSource.receive()"]
    SOURCE[("Nguồn: file, SFTP,<br/>database, queue...")]
    CH["MessageChannel"]
    FLOW["Filter → Transform → Handle<br/>hoặc outbound adapter"]
    TIMER -->|"Kích hoạt theo lịch"| ADAPTER
    ADAPTER <-->|"Đọc dữ liệu"| SOURCE
    ADAPTER -->|"Message<T> nếu có"| CH
    CH --> FLOW
~~~

| Thành phần | Làm gì? | Phần không phụ trách |
| --- | --- | --- |
| `MessageSource<T>` | Định nghĩa cách lấy **một message** ở mỗi lần `receive()`; có thể trả `null`. | Không tự lên lịch thực thi. |
| `@InboundChannelAdapter` | Biến một bean `MessageSource` thành polling inbound endpoint; chỉ định channel và poller. | Không trực tiếp thay thế quy tắc đọc dữ liệu của nguồn. |
| `@Poller` | Quy định khi nào poll và có thể nhận tối đa bao nhiêu message trong một lượt. | Không bảo đảm message được lưu bền vững hoặc xử lý đúng một lần. |
| `MessageChannel` | Đưa message từ adapter tới consumer hoặc flow tiếp theo. | Không tự tạo consumer nhận message. |
| `IntegrationFlow` / handler | Validate, biến đổi, phân tuyến, ghi đích, trả kết quả hoặc xử lý lỗi. | Không tự sinh dữ liệu từ nguồn nếu chưa có adapter/gateway. |

Theo trình tự thông thường:

1. Spring khởi tạo bean `MessageSource` và endpoint gắn với annotation.
2. Poller được kích hoạt theo lịch; mỗi lần kích hoạt gọi `MessageSource.receive()`.
3. Nếu kết quả là `Message<?>`, endpoint gửi nó vào channel đã cấu hình. Với `maxMessagesPerPoll > 1`, endpoint có thể gọi `receive()` nhiều lần trong cùng một lượt.
4. Nếu `receive()` trả `null`, tức thời điểm đó không có message; việc polling hiện tại kết thúc, nhưng lịch polling vẫn tiếp tục.
5. Consumer nhận message qua channel, thực thi flow theo cơ chế đồng bộ hoặc bất đồng bộ của channel.

`null` có ý nghĩa *không có dữ liệu ngay lúc này*, khác với exception khi đọc nguồn hoặc gửi message thất bại. Đây là hợp đồng rất quan trọng khi tự viết `MessageSource`.

## 3. Chuẩn bị Spring Integration

Ví dụ dùng Java 17+, Spring Boot và Spring Integration với cơ chế quản lý phiên bản dependency của Spring Boot. Trong Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Các import quan trọng trong mã ví dụ:

~~~java
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
~~~

Một dự án Spring Boot đã dùng starter thường được auto-configure Spring Integration; ví dụ dưới đây khai báo `@EnableIntegration` tường minh để dễ thấy vai trò của framework. **Không dùng `@Scheduled` để gọi `receive()` thêm một lần nữa**, vì endpoint đã có poller riêng.

Ở dạng phổ biến, method cấu hình sẽ có cấu trúc:

~~~java
@Bean
@InboundChannelAdapter(
        value = "data.input",
        poller = @Poller(fixedDelay = "5000", maxMessagesPerPoll = "1"))
MessageSource<MyPayload> dataSource() {
    return () -> /* trả Message<MyPayload> hoặc null */;
}
~~~

Đoạn trên là **mẫu chữ ký**, `MyPayload` là kiểu dữ liệu ứng dụng tự định nghĩa; biểu thức sau `return` sẽ được triển khai trong ví dụ chạy được ở mục 4. Annotation gắn với **method trả về MessageSource**, không phải method handler xử lý message.

## 4. Ví dụ chạy được: polling một hàng đợi tác vụ

Để quan sát luồng mà không cần cài broker hoặc SFTP server, ta dùng một hàng đợi trong bộ nhớ. Hàng đợi ban đầu có ba mã tác vụ. Mỗi lần được poll, nguồn lấy tối đa một message cho mỗi lời gọi `receive()`; poller có thể lấy tối đa hai message trong mỗi đợt.

Đặt đoạn sau trong tệp `PollingDemoApplication.java`, package `demo.integration`.

~~~java
package demo.integration;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class PollingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PollingDemoApplication.class, args);
    }

    @Bean(name = "jobs.input")
    MessageChannel jobsInputChannel() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            value = "jobs.input",
            poller = @Poller(
                    fixedDelay = "2000",
                    maxMessagesPerPoll = "2"))
    MessageSource<String> jobSource() {
        Queue<String> pending = new ConcurrentLinkedQueue<>(
                List.of("JOB-001", "JOB-002", "JOB-003"));

        return () -> {
            String next = pending.poll();
            if (next == null) {
                return null;
            }

            return MessageBuilder.withPayload(next)
                    .setHeader("source", "memory-queue")
                    .build();
        };
    }

    @Bean
    IntegrationFlow jobProcessingFlow() {
        return IntegrationFlow.from("jobs.input")
                .filter(String.class, job -> job.startsWith("JOB-"))
                .handle(String.class, (job, headers) -> {
                    System.out.println("Đang xử lý: " + job
                            + " (source=" + headers.get("source") + ")");
                    return null; // kết thúc luồng một chiều
                })
                .get();
    }
}
~~~

### 4.1. Diễn giải từng điểm nối

- `@Bean(name = "jobs.input")` khai báo một `DirectChannel` với tên rõ ràng. Cả adapter và flow đều sử dụng đúng tên này.
- `@InboundChannelAdapter(value = "jobs.input", ...)` tạo endpoint gửi message vào channel đó.
- `jobSource()` chỉ được Spring gọi để **tạo bean source**. Sau khi khởi động, poller gọi `receive()` của source (lambda được trả về), chứ không định kỳ gọi lại method factory `jobSource()`.
- `Queue.poll()` lấy và loại một phần tử khỏi bộ nhớ; nếu queue hết dữ liệu, nó trả `null`.
- `MessageBuilder` tạo `Message<String>` với payload là mã tác vụ và header `source`.
- `IntegrationFlow.from("jobs.input")` gắn consumer vào channel. `filter` chỉ cho mã có tiền tố `JOB-` đi qua; `handle` in log và trả `null` vì đây là luồng một chiều.

### 4.2. Điều gì xảy ra khi ứng dụng chạy?

Giả sử không có bước xử lý nào chậm và lịch poll được kích hoạt bình thường:

~~~text
Lượt poll 1:
  receive() -> Message("JOB-001") -> jobs.input -> handler
  receive() -> Message("JOB-002") -> jobs.input -> handler

Lượt poll 2:
  receive() -> Message("JOB-003") -> jobs.input -> handler
  receive() -> null                -> kết thúc lượt poll

Lượt poll sau:
  receive() -> null                -> không có message mới
~~~

`maxMessagesPerPoll = "2"` là **giới hạn số message mỗi lượt kích hoạt**, không phải kích thước batch được đóng gói trong một message. Một message vẫn có một payload `String` và các header. Vì nguồn ban đầu chỉ có ba tác vụ, sau đó sẽ không còn output, nhưng poller vẫn được kích hoạt định kỳ.

**Cảnh báo về tính tin cậy của demo:** `Queue.poll()` loại item khỏi hàng đợi trước khi handler hoàn tất. Nếu handler ném lỗi, queue bộ nhớ trong ví dụ không tự đưa item trở lại. Không nên dùng cách này như một hàng đợi tin cậy trong sản xuất; với hệ thống thật cần xác nhận xử lý, lưu bền vững, retry và idempotency phù hợp.

## 5. Hiểu đúng các tham số của @Poller

`@Poller` mô tả lịch nhận dữ liệu của endpoint. Các tham số thường gặp:

| Thuộc tính | Ý nghĩa | Khi sử dụng |
| --- | --- | --- |
| `fixedDelay = "5000"` | Khoảng trễ 5 giây sau khi một lần chạy kết thúc rồi mới chạy lần tiếp theo. | Nguồn cần tránh quét quá dày; xử lý có thời lượng biến động. |
| `fixedRate = "5000"` | Lịch nhắm tới chu kỳ kích hoạt mỗi 5 giây theo thời điểm bắt đầu; thời điểm thực tế phụ thuộc scheduler. | Cần tần suất đều, đã kiểm soát thời gian xử lý và concurrency. |
| `cron = "0 */5 * * * *"` | Kích hoạt vào giây 0, mỗi 5 phút theo cú pháp cron của Spring. | Nguồn cần quét theo lịch thời gian cụ thể. |
| `initialDelay = "1000"` | Trì hoãn lần poll đầu tiên khoảng 1 giây khi dùng trigger phù hợp. | Cho thành phần phụ thuộc có thời gian sẵn sàng. |
| `maxMessagesPerPoll = "10"` | Tối đa mười message được lấy trong một lượt; nếu `receive()` trả `null` sớm, lượt đó dừng sớm. | Giới hạn lượng công việc mỗi lần kích hoạt. |

Các giá trị thời gian dạng chuỗi trong ví dụ dùng đơn vị mili giây theo cấu hình thông thường. Với phiên bản Spring Integration hỗ trợ khai báo đơn vị thời gian, có thể thiết lập tường minh để giảm nhầm lẫn. Hãy đối chiếu với phiên bản framework thực tế trước khi sao chép cấu hình sang dự án khác.

Hai mẫu cấu hình minh họa **lựa chọn thay thế nhau** (mỗi adapter chọn một lịch phù hợp):

~~~java
@Poller(fixedDelay = "5000", maxMessagesPerPoll = "10")
~~~

~~~java
@Poller(cron = "0 */5 * * * *", maxMessagesPerPoll = "50")
~~~

Không trộn `fixedDelay`, `fixedRate` và `cron` trong cùng một poller khi muốn chỉ có một lịch kích hoạt.

### 5.1. Tốc độ polling không đồng nghĩa thông lượng xử lý

Với `DirectChannel` của ví dụ, việc gửi message thường thực thi consumer trên chính thread của poller. Nếu handler gọi API chậm mất 4 giây cho mỗi message, một lượt nhận hai message có thể cần ít nhất khoảng 8 giây, rồi mới có thêm khoảng trễ `fixedDelay` cho lần tiếp theo. Vì vậy **poll mỗi 2 giây không có nghĩa hai message được hoàn thành mỗi 2 giây**.

Khi đích xử lý chậm, hãy cân nhắc giới hạn `maxMessagesPerPoll`, thời gian gọi dịch vụ, timeout, khả năng chạy đồng thời, queue có giới hạn và cơ chế giảm tải. Nếu tách xử lý sang `ExecutorChannel` hoặc broker, ranh giới thread, transaction và xác nhận nguồn cũng thay đổi; cần thiết kế đường lỗi riêng.

### 5.2. Chọn số message mỗi poll

Đặt giới hạn nhỏ khi nguồn đích nhạy tải hoặc nghiệp vụ có side effect chậm. Tăng giới hạn khi đọc nhiều bản ghi ngắn và xử lý nhẹ. Đừng tự đặt một giá trị rất lớn rồi kỳ vọng scheduler công bằng giữa các endpoint: một lần poll dài có thể giữ tài nguyên lâu và gây trễ cho các tác vụ khác.

## 6. Tình huống thực tế: @InboundChannelAdapter đọc file CSV

Với nguồn file, Spring Integration đã có `FileReadingMessageSource`. Thay vì tự viết lambda kiểm tra thư mục, ta cấu hình message source này và gắn lịch poll. Cần dependency bổ sung:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

Ví dụ cấu hình dưới đây nằm trong class `CsvFilePollingConfiguration.java` của ứng dụng:

~~~java
package demo.integration;

import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.AcceptOnceFileListFilter;
import org.springframework.integration.file.filters.CompositeFileListFilter;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.MessageChannel;

@Configuration
class CsvFilePollingConfiguration {

    @Bean(name = "files.input")
    MessageChannel filesInputChannel() {
        return new DirectChannel();
    }

    @Bean
    @InboundChannelAdapter(
            value = "files.input",
            poller = @Poller(
                    fixedDelay = "5000",
                    maxMessagesPerPoll = "5"))
    MessageSource<File> csvFileSource() {
        var source = new FileReadingMessageSource();
        source.setDirectory(new File("./inbox"));

        var filters = new CompositeFileListFilter<File>();
        filters.addFilter(new SimplePatternFileListFilter("*.csv"));
        filters.addFilter(new AcceptOnceFileListFilter<>());
        source.setFilter(filters);

        return source;
    }

    @Bean
    IntegrationFlow csvFileFlow() {
        return IntegrationFlow.from("files.input")
                .handle(File.class, (file, headers) -> {
                    System.out.println("Phát hiện file CSV: "
                            + file.getAbsolutePath());
                    return null;
                })
                .get();
    }
}
~~~

Tạo thư mục `./inbox` trước khi khởi động ứng dụng; đường dẫn này tương đối với working directory của tiến trình. Mỗi message từ nguồn có **payload kiểu `File`**. Handler ví dụ chỉ log đường dẫn, chưa mở và xử lý nội dung CSV.

Ở đây có **hai lớp filter** khác nhau:

1. `SimplePatternFileListFilter("*.csv")` là bộ lọc danh sách **file**, quyết định file nào được đưa vào source.
2. `AcceptOnceFileListFilter` giảm việc phát lại một file trong thời gian ứng dụng đang chạy. Bộ lọc này dựa trên trạng thái trong bộ nhớ, không tự đảm bảo chống trùng xuyên lần restart.
3. `.filter(...)` của `IntegrationFlow` (nếu thêm) lọc **message đã được phát ra**, không thay thế chức năng kiểm soát file tại nguồn.

Khi chuyển sang môi trường thật, cần thêm cơ chế phát hiện file đã ghi xong, xử lý các file lỗi, di chuyển sang thư mục đã xử lý/quarantine, và lưu trạng thái đọc bền vững nếu cần chống trùng qua restart.

### 6.1. Vì sao không chỉ dùng @Scheduled và tự send?

Có thể tự viết code đọc file bằng `@Scheduled` rồi gửi tới `MessageChannel`, nhưng khi đã dùng Spring Integration, `@InboundChannelAdapter` diễn đạt trực tiếp vòng đời **source → poller → channel**. Framework quản lý endpoint và hỗ trợ cách cấu hình poller, channel, advice, metric và error handling theo cùng mô hình với các adapter khác.

Một tác vụ `@Scheduled` tự viết có thể hợp lệ cho xử lý nền đơn giản; tuy nhiên nếu mục tiêu là xây dựng integration flow, `@InboundChannelAdapter` giúp tách **nguồn dữ liệu** khỏi **bước xử lý message** rõ ràng hơn.

## 7. Đặt @InboundChannelAdapter vào kiến trúc tích hợp

### 7.1. Nguồn nào phù hợp với polling?

| Nguồn | Có phù hợp với inbound polling? | Ghi chú |
| --- | --- | --- |
| File trong thư mục | Có. | Dùng `FileReadingMessageSource`, filter và chiến lược trạng thái file. |
| SFTP thư mục từ xa | Có. | Cần adapter/module SFTP và cơ chế đồng bộ/chọn file, session, reconnect. |
| Database | Có, nếu truy vấn dữ liệu mới theo dấu mốc. | Cần query, checkpoint, transaction và tránh đọc lặp. |
| REST API chỉ hỗ trợ lấy dữ liệu định kỳ | Có thể, qua source/service tùy chỉnh. | Phải giới hạn rate, timeout, page, retry và số lượng kết quả. |
| HTTP request gửi vào ứng dụng | Thông thường không. | Dùng HTTP inbound gateway nhận request được đẩy đến. |
| JMS/AMQP/Kafka consumer | Thường ưu tiên listener/message-driven adapter. | Broker có cơ chế nhận/ack riêng; không tự thay listener bằng poller chung nếu không có lý do. |

Trong module `SPRING_INTEGRATION_ADAPTERS`, điểm chung giữa các nguồn là sau khi adapter phát ra `Message<?>`, phần transform, route và outbound trong Java DSL có thể dùng lại. Khác biệt nằm ở **cách nhận dữ liệu, độ bền trạng thái và xác nhận đã xử lý** của từng protocol.

### 7.2. Inbound adapter khác gateway

- **Inbound adapter:** nhận dữ liệu rồi gửi message theo hướng đi vào ứng dụng. Không có quy ước phải trả response trực tiếp về nguồn ban đầu.
- **Inbound gateway:** nhận request và thường cần gửi response về caller tương ứng (ví dụ HTTP).
- **Outbound adapter:** nhận message trong flow để gửi một chiều ra hệ thống đích.
- **Outbound gateway:** gửi request từ flow ra hệ thống đích và nhận reply đưa trở lại flow.

Một nguồn file hoặc polling database thường là inbound adapter. Với API HTTP server nhận request để trả JSON, inbound HTTP gateway phù hợp hơn.

## 8. Hợp đồng message và tính đúng đắn khi đọc nguồn

`MessageSource<T>` quyết định payload và header của message tại ranh giới tích hợp. Thống nhất hợp đồng trước khi cho flow hoạt động:

| Thành phần hợp đồng | Ví dụ | Lý do |
| --- | --- | --- |
| Kiểu payload | `File`, `OrderEvent` hoặc `List<Row>`. | Consumer biết kiểu và hành vi xử lý. |
| Định danh nguồn | `sourceSystem = "sftp-a"`. | Phân loại lỗi, truy vết nguồn. |
| Định danh nghiệp vụ | `eventId` hoặc `orderId`. | Idempotency và đối soát. |
| Timestamps | `eventTime` và thời điểm nhận. | Theo dõi độ trễ và dữ liệu đến muộn. |
| Điểm đánh dấu đã đọc | offset, ID tăng dần, thời gian cập nhật. | Khôi phục sau restart; ngăn bỏ sót/đọc lặp. |
| Xử lý khi sai cấu trúc | Lỗi có mã, quarantine, cảnh báo. | Không để dữ liệu sai đi vào handler ghi đích. |

Nếu một lần gọi API nguồn trả 100 bản ghi và source tạo **một message mang danh sách 100 bản ghi**, `maxMessagesPerPoll = "10"` vẫn được hiểu là tối đa **10 message**, không phải 10 bản ghi. Muốn mỗi bản ghi trở thành một message riêng, có thể thay đổi source để nhận từng bản ghi hoặc thêm bước splitter, rồi quyết định cách tương quan lỗi/ack.

### 8.1. Polling an toàn khi có lỗi và restart

Ba mốc cần phân biệt:

1. **Đã đọc từ nguồn:** file/record/event đã được lấy hoặc nhìn thấy.
2. **Đã chuyển vào channel:** message đã được bàn giao cho thành phần tiếp theo.
3. **Đã xử lý nghiệp vụ thành công:** dữ liệu đã được ghi ra đích, xác nhận và có thể đối soát.

Ba sự kiện này **không tự động xảy ra trong cùng một transaction**. Chẳng hạn, một hàng đợi trong bộ nhớ có thể mất item nếu đã `poll()` nhưng handler lỗi. Một API có thể trả lại cùng event khi retry dù event trước đã được ghi. Một file chưa ghi xong có thể bị đọc quá sớm.

Tùy nguồn, cần checkpoint sau thành công, xác nhận (acknowledgement) đúng thời điểm, vùng chờ xử lý lỗi và idempotency key ở đích. Không thể cam kết exactly-once chỉ nhờ `@InboundChannelAdapter` hoặc `maxMessagesPerPoll`.

## 9. Xử lý lỗi trong flow polling

Với `DirectChannel` đồng bộ, handler thường chạy cùng thread của poller. Nếu handler ném exception, việc gửi message có thể thất bại ngay trong lượt poll. Trong các cấu hình poller bất đồng bộ, framework có thể xuất bản `ErrorMessage` tới error channel được cấu hình. Cách lan truyền lỗi và retry cụ thể phụ thuộc channel, scheduler, advice và cấu hình endpoint.

### 9.1. Phân loại lỗi

- **Không có dữ liệu:** `receive() == null`, không phải lỗi; không cần retry ngay.
- **Nguồn không truy cập được:** mất kết nối SFTP, database timeout, file permissions. Ghi nhận nguyên nhân, dùng backoff và cảnh báo nếu kéo dài.
- **Message sai cấu trúc:** payload không thỏa hợp đồng; chuyển quarantine hoặc xử lý lỗi nghiệp vụ có thể đối soát.
- **Đích xử lý thất bại:** broker ngắt kết nối, API trả lỗi, database không ghi được. Cân nhắc retry có giới hạn, idempotency và dead-letter.
- **Lỗi không xác định trạng thái:** đích có thể đã ghi thành công nhưng response bị mất. Tránh retry mù nếu tác vụ có side effect không lặp lại được.

### 9.2. Quyết định chính sách retry ở đúng tầng

Ví dụ đọc SFTP gặp lỗi đăng nhập nên retry ở tầng kết nối/nguồn. Ví dụ đọc được file CSV nhưng dòng số 27 sai schema nên xử lý ở tầng validation và quarantine. Ví dụ đơn hàng đã được gửi sang đích nhưng timeout nên phải hỏi đích hoặc dùng idempotency key trước khi ghi lại.

Poller chạy lại **không đồng nghĩa** tự động retry đúng record thất bại; nếu record đã bị đánh dấu tiêu thụ, lần poll kế tiếp có thể không nhìn thấy nó nữa. Đây là lý do cần phân biệt trạng thái nguồn, việc gửi message và xác nhận thành công.

## 10. Vòng đời endpoint, thread và quan sát

Spring Integration khởi tạo poller endpoint cùng application context và quản lý chúng theo cơ chế lifecycle của framework. Trong môi trường có nhiều instance, tất cả có thể cùng poll nguồn nếu không có cơ chế điều phối, phân vùng hoặc lock thích hợp. Hãy quyết định rõ mô hình single consumer, competing consumers hoặc partition ngay từ thiết kế.

Khi cấu hình thực tế, theo dõi ít nhất:

- Lần poll gần nhất, số lượt không có dữ liệu và độ trễ giữa các lượt.
- Số message đã đọc, đã gửi vào channel, đã xử lý thành công và đã lỗi.
- Thời gian `receive()`, thời gian handler, timeout của hệ thống ngoài.
- Tốc độ nguồn so với tốc độ đích, độ sâu queue, số lần retry và số item bị đưa vào quarantine.
- Trạng thái khởi động/dừng của endpoint, lỗi kết nối, tài nguyên thread và connection/session pool.

Không nên log toàn bộ payload chứa thông tin bí mật. Dùng ID hoặc correlation ID để nối log adapter với log của handler, và chỉ log metadata cần thiết.

### 10.1. Polling với nhiều instance

Nếu hai instance quét cùng một thư mục hoặc cùng một bảng dữ liệu mà không phối hợp, cả hai có thể nhận cùng bản ghi. Filter chỉ lưu trạng thái ở bộ nhớ của từng instance sẽ **không** giúp ngăn trùng giữa hai tiến trình. Cần cơ chế phân vùng, lock phân tán, claim record hoặc repository trạng thái bền vững phù hợp.

Khi dừng ứng dụng, cần xét riêng việc **dừng lịch poll mới**, **đợi message đang xử lý**, và **đóng session/connection**. Channel bất đồng bộ hoặc bộ đệm có thể còn message chờ khi scheduler đã dừng.

## 11. Kiểm thử nguồn và endpoint polling

Để kiểm tra logic `MessageSource`, có thể gọi trực tiếp `receive()` một cách có kiểm soát mà không cần đợi scheduler. Đoạn dưới là JUnit 5 test với class ví dụ ở mục 4:

~~~java
package demo.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.springframework.integration.core.MessageSource;

class JobSourceTest {

    @Test
    void returnsThreeMessagesThenNull() {
        MessageSource<String> source =
                new PollingDemoApplication().jobSource();

        assertEquals("JOB-001", source.receive().getPayload());
        assertEquals("JOB-002", source.receive().getPayload());
        assertEquals("JOB-003", source.receive().getPayload());
        assertNull(source.receive());
    }
}
~~~

Test này chỉ kiểm tra **hợp đồng của source**: trả đúng ba message rồi trả `null`. Nó không chứng minh lịch của `@Poller` hay flow đã được Spring đăng ký, vì bean được tạo trực tiếp ngoài context.

Để kiểm tra toàn bộ đường đi, nên thêm integration test chạy Spring context, lắp consumer kiểm chứng vào channel đầu ra hoặc kiểm tra kết quả cuối, và chờ message bằng công cụ đồng bộ kiểm thử thay vì `Thread.sleep()` cố định. Với nguồn file, dùng thư mục tạm, đưa vào một file `.csv` hợp lệ và một file không hợp lệ, kiểm tra nguồn chỉ phát file cần đọc; sau đó thử restart để xác định giới hạn của filter trong bộ nhớ.

Dependency JUnit/Spring Boot test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong bài học này không cần khởi động SFTP server hay database thật để chứng minh logic `receive()`. Khi kiểm thử ranh giới giao thức, nên có test riêng cho reconnect, xác nhận, lỗi mạng, restart và duplicate.

## 12. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy message từ adapter. | `receive()` luôn trả `null`; channel sai tên; endpoint chưa chạy. | Log có giới hạn tại source, kiểm tra tên channel và lifecycle endpoint. |
| App gọi source liên tục làm quá tải nguồn. | Chu kỳ quá ngắn hoặc mỗi lượt lấy quá nhiều message. | Điều chỉnh trigger, giới hạn poll, latency và backpressure. |
| Chỉ thấy một message dù có nhiều bản ghi trong payload. | Source đóng gói cả batch thành một `Message<List<?>>`. | Xem lại hợp đồng source; tách message bằng splitter nếu cần. |
| File bị đọc lặp sau restart. | Filter chỉ giữ trạng thái trong RAM. | Dùng metadata/persistent filter hoặc idempotency theo mã file. |
| File bị bỏ sót sau lỗi xử lý. | Source đã đánh dấu hoặc loại record trước khi handler thành công. | Thiết kế checkpoint/ack và retry theo kết quả nghiệp vụ. |
| Cấu hình poller đúng nhưng handler chậm. | `DirectChannel` xử lý đồng bộ làm một lượt poll kéo dài. | Đo thời gian handler, điều chỉnh thông lượng và cân nhắc channel phù hợp. |
| Cùng record được xử lý ở nhiều instance. | Nhiều poller cùng quét nguồn mà không có điều phối. | Chọn khóa phân tán, claim record, partition hoặc một instance chuyên đọc. |
| Đường lỗi không hoạt động như kỳ vọng. | Lỗi ở thread khác hoặc filter bỏ message mà không báo. | Phân biệt lỗi source/handler, thread, error channel và timeout. |

## 13. Bài tập thực hành

**Đề bài:** ứng dụng nhận `PaymentRequest` từ một nguồn polling mô phỏng, tối đa 3 message mỗi lượt, cách nhau 1 giây. Mỗi `PaymentRequest` có `id`, `amount` và `currency`. Sau khi đọc, flow phải:

1. Bỏ qua request không có mã `id` và gửi chúng vào một nhánh kiểm tra lỗi đã định nghĩa.
2. Tạo header `sourceSystem` ở source và ghi correlation ID vào log xử lý.
3. Phân tuyến `VND`, `USD` tới hai handler riêng; handler phải chống ghi trùng theo `id`.
4. Mô phỏng một handler lỗi ở lần xử lý đầu, rồi kiểm tra chính sách retry có tái xử lý được đúng request đó hay không.
5. Cho nguồn trả `null` khi không còn dữ liệu; chứng minh app vẫn hoạt động và lịch poll vẫn tiếp tục.
6. Thay nguồn mô phỏng bằng `FileReadingMessageSource` rồi giải thích những gì cần bổ sung để không mất hoặc đọc trùng file sau restart.

**Tiêu chí đạt:** nêu rõ số message được lấy trong mỗi lượt, phân biệt từng loại lỗi, mô tả được thời điểm xác nhận đã xử lý và có kiểm thử chứng minh duplicate không tạo side effect lặp lại.

## 14. Tự kiểm tra nhanh

1. Method có `@InboundChannelAdapter` trả về `MessageSource<T>`; vậy đối tượng nào được poller gọi mỗi lần có lịch?
2. `receive()` trả `null` có phải framework dừng vĩnh viễn adapter không?
3. `maxMessagesPerPoll = "5"` khác gì với việc một message chứa danh sách 5 bản ghi?
4. Vì sao `fixedDelay = "1000"` không bảo đảm một message được xử lý hoàn tất mỗi giây?
5. Một file đã đọc thành công nhưng handler ghi database thất bại: muốn xử lý lại an toàn cần quản lý trạng thái ở đâu?
6. Khi ứng dụng chạy ba instance, bộ lọc `AcceptOnceFileListFilter` trên từng instance có đủ để loại duplicate không?

**Gợi ý trả lời:** poller gọi `MessageSource.receive()`; `null` chỉ biểu thị tạm chưa có dữ liệu; giới hạn poll đếm message; channel đồng bộ gắn thời gian xử lý với lần poll; cần checkpoint/ack/idempotency theo nguồn và đích; filter ở bộ nhớ cục bộ không phối hợp giữa các instance.

## 15. Tổng kết

`@InboundChannelAdapter` là cách đưa **nguồn cần polling** vào Spring Integration thông qua một `MessageSource`. Poller quyết định lịch và số message được nhận; channel nối nguồn với các bước xử lý trong `IntegrationFlow`; business handler chịu trách nhiệm về kết quả cuối và side effect.

Khi áp dụng cho file, SFTP, database hoặc API định kỳ, hãy thiết kế song song ba việc: **hợp đồng payload/headers**, **điều tiết lịch và thông lượng**, **quản lý lỗi, trạng thái đã đọc và tính idempotent**. Cú pháp annotation gọn, nhưng chất lượng của luồng tích hợp phụ thuộc vào việc làm rõ các hành vi đó từ đầu.

