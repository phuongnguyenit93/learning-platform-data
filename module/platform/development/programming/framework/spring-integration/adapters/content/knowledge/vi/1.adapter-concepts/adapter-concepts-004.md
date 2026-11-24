# Phân biệt adapter một chiều và gateway hai chiều

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **channel adapter** có hợp đồng thông điệp một chiều với **gateway** có hợp đồng request–reply.
- Nhận diện bốn trường hợp: inbound adapter, outbound adapter, inbound gateway và outbound gateway.
- Giải thích vai trò của MessageChannel, replyChannel, errorChannel, thời gian chờ và mã tương quan trong một lượt trao đổi.
- Chọn đúng endpoint khi tích hợp file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu.
- Đọc ví dụ Java DSL kết hợp một outbound file adapter và một messaging gateway trả kết quả.
- Đánh giá rủi ro retry, timeout, xử lý trùng và mức bảo đảm giao nhận của hai mô hình.

## 1. Bài toán: gửi đi hay cần nhận câu trả lời?

Giả sử ứng dụng xử lý đơn hàng cần thực hiện hai tác vụ:

1. Khi đơn hàng được duyệt, **xuất một tệp CSV** cho bộ phận vận hành. Ứng dụng chỉ cần biết thao tác ghi tệp có thực hiện được hay không, không cần một thông điệp nghiệp vụ trả về để tính tiếp.
2. Trước khi báo giá, **gọi dịch vụ tính giá** và sử dụng số tiền trả về để hoàn tất đơn hàng. Bước tiếp theo bắt buộc có kết quả của lời gọi.

Hai tác vụ khác nhau ở **hợp đồng giao tiếp**. Tác vụ xuất CSV phù hợp với **channel adapter một chiều**; tác vụ tính giá cần một **gateway request–reply**.

Trong Spring Integration, các endpoint trao đổi đối tượng **Message<?>** thông qua **MessageChannel**. Một message gồm **payload** (dữ liệu) và **headers** (siêu dữ liệu phục vụ định tuyến, tương quan, xử lý lỗi và ánh xạ giao thức).

**Channel adapter** kết nối luồng messaging với hệ thống bên ngoài theo một chiều của dòng thông điệp:

- **Inbound adapter:** đưa dữ liệu từ bên ngoài **vào** một MessageChannel.
- **Outbound adapter:** nhận dữ liệu từ MessageChannel rồi **gửi ra** bên ngoài.

**Gateway** kết nối hai phía theo hợp đồng **request–reply**: nhận hoặc tạo request, chuyển qua ranh giới giao thức/messaging và đưa response về phía cần nhận kết quả.

~~~mermaid
flowchart TB
  subgraph OneWay["Channel adapter: luồng thông điệp một chiều"]
    A["MessageChannel"] --> B["Outbound adapter"] --> C["Hệ thống đích"]
  end
  subgraph TwoWay["Gateway: request–reply"]
    X["Caller / Request channel"] --> G["Gateway"] --> Y["Hệ thống / Handler"]
    Y -->|Response| G
    G -->|Reply| R["Caller / Reply channel"]
  end
~~~

**Một chiều không đồng nghĩa với không có xác nhận kỹ thuật.** Outbound adapter vẫn có thể chờ ghi file, nhận ACK từ broker, gặp timeout hoặc ném exception. Điểm phân biệt là adapter **không tạo một message phản hồi nghiệp vụ trong flow** như gateway.

**Hai chiều không nhất thiết là kết nối mạng song công hoặc thực thi đồng bộ mọi lúc.** Gateway mô tả mối quan hệ request–reply ở mức ứng dụng; việc gửi và nhận có thể dùng channel khác nhau hoặc cần cơ chế tương quan bất đồng bộ.

## 2. Bốn loại endpoint cần phân biệt

Trước tiên xác định **hướng dữ liệu** so với ứng dụng Spring Integration; sau đó xác định **có cần reply nghiệp vụ hay không**.

| Loại endpoint | Dữ liệu đi theo hướng | Có reply nghiệp vụ trong flow? | Trường hợp minh họa |
| --- | --- | --- | --- |
| **Inbound channel adapter** | Hệ thống ngoài → MessageChannel | Không | Quét file, đọc SFTP, nhận message JMS |
| **Outbound channel adapter** | MessageChannel → hệ thống ngoài | Không | Ghi file, publish Kafka, gửi message AMQP |
| **Inbound gateway** | Hệ thống ngoài → request channel → reply về bên gọi | Có | HTTP POST chờ kết quả xử lý và HTTP response |
| **Outbound gateway** | Request channel → hệ thống ngoài → reply channel | Có | Gọi HTTP API và lấy response body để xử lý tiếp |

### 2.1. Inbound adapter: tiếp nhận mà không có cặp reply nghiệp vụ

Ví dụ một File inbound adapter được poller kích hoạt mỗi vài giây. Nó lấy một tệp, đóng gói đối tượng File thành message và gửi lên channel. Subscriber tiếp tục đọc CSV, kiểm tra và lưu đơn hàng. File system không phải là caller đang chờ một message reply trả về từ flow.

Với các giao thức có acknowledgment như JMS, AMQP hoặc Kafka, adapter có thể tham gia cơ chế ACK/commit/redelivery của nguồn. Những tín hiệu đó thuộc **mức giao nhận**; không biến một inbound adapter thành inbound gateway.

### 2.2. Outbound adapter: tạo side effect

Một message chứa CSV được đưa lên exportChannel. Outbound file adapter tiêu thụ message, ghi file vào thư mục đích rồi kết thúc endpoint một chiều. Nếu xảy ra lỗi quyền ghi hoặc file đã tồn tại, adapter có thể báo lỗi theo cấu hình; lỗi này khác với một **response nghiệp vụ**.

Tương tự, outbound Kafka adapter publish record. Producer có thể nhận callback hoặc acknowledgment từ broker, nhưng một message reply mang kết quả xử lý của consumer không mặc nhiên quay trở lại flow.

### 2.3. Inbound gateway: bên ngoài gọi vào và cần kết quả

Ví dụ một HTTP client gọi API tạo báo giá:

~~~text
HTTP client --POST /quotes--> HTTP inbound gateway
               |
               v
         requestChannel
               |
               v
        Validate + PriceService
               |
               v
           reply message
               |
               v
HTTP client <--HTTP response-- HTTP inbound gateway
~~~

Gateway tạo message request từ HTTP request, chuyển vào flow, chờ hoặc nhận message reply theo hợp đồng đã cấu hình và ánh xạ nó thành HTTP response. Nếu không có reply trong thời hạn cho phép, cần xử lý timeout; không được để client chờ vô hạn.

### 2.4. Outbound gateway: flow gọi ra ngoài và dùng kết quả

Giả sử hệ thống cần lấy hạn mức tín dụng trước khi xác nhận đơn hàng. Outbound HTTP gateway gửi request đến API của đối tác, nhận response rồi chuyển thành message cho bước định tuyến hoặc kiểm tra tiếp theo.

~~~mermaid
sequenceDiagram
    participant F as Flow nội bộ
    participant G as Outbound HTTP gateway
    participant S as API đối tác
    F->>G: Message<CreditCheckRequest>
    G->>S: HTTP request
    S-->>G: HTTP response
    G-->>F: Message<CreditCheckResponse>
    F->>F: Kiểm tra kết quả và quyết định
~~~

Điểm quan trọng là flow **cần dữ liệu phản hồi để tiếp tục**. Nếu chỉ muốn phát một sự kiện thông báo, outbound adapter thường đơn giản và phù hợp hơn.

## 3. Messaging gateway khác HTTP/JMS gateway ở điểm nào?

Spring Integration còn có **messaging gateway**, thường được khai báo qua **@MessagingGateway** và giao diện Java. Đây là **cửa vào/ra cho mã Java gọi một integration flow như gọi phương thức**:

~~~java
@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface QuoteGateway {
    QuoteResponse calculate(QuoteRequest request);
}
~~~

Caller chỉ nhìn thấy phương thức calculate, trong khi gateway tạo message request, gửi đến channel, rồi chuyển reply thành giá trị trả về. Với lời gọi trả giá trị, đây là hợp đồng request–reply.

Phân biệt ba khái niệm:

- **Messaging gateway (@MessagingGateway):** nối **phương thức Java ↔ messaging flow**; có thể dùng interface trả kết quả hoặc một phương thức một chiều.
- **Inbound protocol gateway:** nối **request của hệ thống ngoài → messaging flow → response bên ngoài**; ví dụ HTTP inbound gateway.
- **Outbound protocol gateway:** nối **messaging flow → request tới hệ thống ngoài → response trở lại flow**; ví dụ HTTP outbound gateway.

Một phương thức trong messaging gateway trả **void** có thể là lời gọi một chiều. Do đó không phải mọi API mang tên gateway đều luôn đợi kết quả; hãy xem **hợp đồng phương thức/endpoint cụ thể**.

## 4. MessageChannel và hợp đồng request–reply

Ở mô hình adapter, dữ liệu được chuyển một chiều qua channel. Ở mô hình gateway, ngoài đường request còn phải có **đường trả lời**.

~~~mermaid
flowchart LR
    Caller["Caller"] --> G["Messaging gateway"]
    G --> Req["requestChannel"]
    Req --> H["Service activator<br/>xử lý request"]
    H --> Rep["replyChannel / Temporary channel"]
    Rep --> G
    G --> Caller
~~~

Khi một **@MessagingGateway** được gọi và cần kết quả, framework có thể tạo hoặc sử dụng channel nhận reply rồi gắn tham chiếu vào header **replyChannel** của request. Handler tạo reply; framework định tuyến reply về channel đó để gateway hoàn tất lời gọi. Tùy cấu hình, có thể chỉ định **defaultReplyChannel** hoặc dùng channel trả lời tạm.

Những headers thường liên quan:

| Header / cơ chế | Ý nghĩa trong request–reply |
| --- | --- |
| **replyChannel** | Chỉ ra nơi nhận message reply khi flow hoặc endpoint hỗ trợ hợp đồng reply |
| **errorChannel** | Nơi có thể chuyển ErrorMessage khi một đường xử lý lỗi được cấu hình phù hợp |
| **correlationId** | Ghép phản hồi với request khi xử lý nhiều request hoặc qua kênh bất đồng bộ |
| **id, timestamp** | Nhận diện và theo dõi message, nhưng không nên dùng thay khóa nghiệp vụ ổn định |
| **replyTimeout** | Giới hạn thời gian chờ reply trong mô hình gateway đồng bộ |
| **requestTimeout** | Giới hạn thời gian gửi/đưa request vào channel khi cấu hình và channel có hỗ trợ |

Một reply có thể do service activator, transformer, gateway bên ngoài hoặc nhánh định tuyến tạo ra. Nếu handler không sinh reply, trả về null hoặc làm mất replyChannel, gateway đang chờ kết quả có thể hết thời gian chờ. Không nên giả định mọi lỗi đều tự động chuyển thành một message reply hợp lệ.

### 4.1. Vai trò của loại channel

| Loại channel | Hệ quả với adapter | Hệ quả với gateway |
| --- | --- | --- |
| **DirectChannel** | Gọi subscriber đồng bộ, tác vụ I/O chậm có thể giữ luồng producer | Dễ dùng cho xử lý request–reply đồng bộ; exception thường lan trên chuỗi gọi |
| **ExecutorChannel** | Xử lý bất đồng bộ qua executor | Phải xét thời điểm reply, timeout, lỗi và thứ tự |
| **QueueChannel** | Cần consumer/poller lấy message khỏi queue | Có thể dùng làm request hoặc reply channel, nhưng cần consumer và điều kiện tương quan rõ |
| **PublishSubscribeChannel** | Phân phát sự kiện cho nhiều subscriber | Không mặc nhiên xác định reply nào là kết quả của một request khi có nhiều nhánh |

Channel không quyết định hệ thống đích đã xử lý thành công hay chưa. Việc một gateway nhận reply thành công chỉ có ý nghĩa trong **hợp đồng phản hồi được hai phía thống nhất**.

### 4.2. Đồng bộ, bất đồng bộ và thời gian chờ

Gateway đồng bộ thường khiến caller chờ cho đến khi có reply hoặc hết timeout. Nếu flow gọi HTTP API mất nhiều giây, tổng thời gian có thể gồm chờ channel, xếp hàng, gửi mạng, xử lý phía đích và nhận phản hồi. Cần đặt giới hạn rõ cho từng đoạn để caller không bị giữ mãi.

Gateway cũng có thể triển khai tương tác bất đồng bộ tùy API, kiểu trả về và endpoint. Khi đó request và reply cần có thông tin tương quan hoặc cơ chế completion phù hợp. **Request–reply là mô hình trao đổi**, không phải lời khẳng định mọi request đều được thực hiện trên một thread.

## 5. Ví dụ Java DSL: một chiều xuất file, hai chiều tính báo giá

Ví dụ này đặt hai flow cạnh nhau để thấy rõ kết quả tại ranh giới messaging:

1. **Adapter:** service gửi CSV vào exportChannel; outbound file adapter ghi ra thư mục. Service không nhận QuoteResponse hay message nghiệp vụ nào từ adapter.
2. **Messaging gateway:** mã Java gọi PriceGateway.quote(...) với PriceRequest; flow tính giá tạo PriceReply và gateway trả kết quả cho caller.

Ví dụ dùng Spring Integration Java DSL với Spring Boot, module spring-integration-file, và Java 17+ cho các record. Có thể sử dụng dependency management của Spring Boot để chọn phiên bản Spring Integration tương thích.

### 5.1. Khai báo hai flow

~~~java
import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class AdapterGatewayConfiguration {

    @Bean
    public MessageChannel exportChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow exportFlow() {
        return IntegrationFlow.from("exportChannel")
            .handle(Files.outboundAdapter(new File("./data/export"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(FileHeaders.FILENAME))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }

    @Bean
    public MessageChannel priceRequests() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow priceFlow() {
        return IntegrationFlow.from("priceRequests")
            .handle(PriceRequest.class, (request, headers) -> {
                if (request.quantity() <= 0) {
                    throw new IllegalArgumentException(
                        "quantity phai lon hon 0");
                }
                long total = request.quantity() * 50_000L;
                return new PriceReply(request.productId(), total);
            })
            .get();
    }
}

@MessagingGateway(
    defaultRequestChannel = "priceRequests",
    defaultReplyTimeout = "3000")
interface PriceGateway {
    PriceReply quote(PriceRequest request);
}

record PriceRequest(String productId, int quantity) {}

record PriceReply(String productId, long totalVnd) {}
~~~

**Đọc flow export:** exportChannel là DirectChannel; outbound file adapter đăng ký nhận từ channel. Adapter lấy payload và tên file từ header FileHeaders.FILENAME. Khi hoàn thành việc ghi theo hợp đồng, luồng kết thúc tại handler một chiều, không phát sinh reply nghiệp vụ.

**Đọc flow price:** khi PriceGateway.quote được gọi, messaging gateway tạo request message, gửi đến priceRequests. Service activator kiểm tra số lượng và trả một đối tượng PriceReply; framework tạo/dẫn reply về gateway, rồi phương thức quote trả PriceReply cho mã gọi.

**defaultReplyTimeout = "3000"** đặt thời hạn chờ nhận reply của messaging gateway là 3.000 mili giây. Cơ chế lỗi cụ thể khi timeout hoặc khi handler ném exception cần được xử lý theo cấu hình và API gọi. Timeout không tự hủy công việc đã chuyển sang xử lý bất đồng bộ.

### 5.2. Producer so sánh hai cách gọi

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.file.FileHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class DemoBusinessService {

    private final MessageChannel exportChannel;
    private final PriceGateway priceGateway;

    DemoBusinessService(
            @Qualifier("exportChannel") MessageChannel exportChannel,
            PriceGateway priceGateway) {
        this.exportChannel = exportChannel;
        this.priceGateway = priceGateway;
    }

    PriceReply execute() {
        boolean accepted = exportChannel.send(
            MessageBuilder.withPayload("productId,quantity\nP-100,2\n")
                .setHeader(FileHeaders.FILENAME, "order-P-100.csv")
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "Khong dua duoc message vao exportChannel");
        }

        return priceGateway.quote(new PriceRequest("P-100", 2));
    }
}
~~~

Nếu thư mục đích ghi được và chưa có file trùng tên, flow adapter sẽ cố gắng ghi tệp **./data/export/order-P-100.csv** với hai dòng CSV. Lời gọi gateway sẽ trả một PriceReply với **productId = P-100** và **totalVnd = 100000** theo quy tắc tính giả lập.

**Điểm khác nhau của hai dòng tương tác:** phương thức send đưa một message vào channel; còn quote có **giá trị trả về nghiệp vụ** được tạo từ reply của flow. Với DirectChannel, lỗi ghi file có thể truyền ngược đến producer dưới dạng exception; điều này không biến file adapter thành gateway.

Đoạn mã là ví dụ học tập: số tiền được tính cố định, chưa có bảng giá thật; tên file phải được kiểm tra trước khi dùng với dữ liệu người dùng; nội dung CSV thực tế cần encoder để xử lý dấu phẩy, dấu nháy và xuống dòng. Không nên xem việc ghi file thành công là xác nhận đối tác đã xử lý đơn hàng.

### 5.3. Khi thay handler tính giá bằng dịch vụ HTTP ngoài

Trong ví dụ trên, PriceGateway là **cổng từ phương thức Java vào flow nội bộ**. Nếu giá cần được tính bởi một hệ thống ngoài, có thể thay service activator nội bộ bằng **outbound HTTP gateway** gửi PriceRequest đến API và nhận PriceReply. Sơ đồ trở thành:

~~~text
Java code
  |
  v
@MessagingGateway interface
  |
  v
priceRequests
  |
  v
Outbound HTTP gateway ---> API tính giá bên ngoài
  ^                              |
  |                              |
  +---------- HTTP response -----+
  |
  v
Reply trở về Java caller
~~~

Lúc đó phải cấu hình endpoint HTTP, method, URL, serializer/deserializer, xác thực, thời gian chờ kết nối và response, xử lý HTTP status. Outbound HTTP gateway phù hợp vì flow thực sự **cần body phản hồi**. Nếu chỉ thông báo “đơn hàng đã tạo” mà không cần body, outbound adapter một chiều có thể phù hợp hơn.

## 6. Cách lựa chọn trong các hệ thống tích hợp phổ biến

| Tình huống | Gợi ý lựa chọn | Lý do |
| --- | --- | --- |
| Đọc tệp mới ở thư mục chung | File inbound adapter + poller | Không có caller đang chờ reply nghiệp vụ |
| Đồng bộ file từ SFTP theo lịch | SFTP inbound adapter | Lấy dữ liệu một chiều; xử lý bản ghi trong flow |
| Ghi hoặc tải một file lên SFTP | File/SFTP outbound adapter | Thực hiện xuất dữ liệu một chiều |
| HTTP client gọi POST /orders và cần mã đơn hàng | HTTP inbound gateway | Cần ánh xạ reply của flow thành HTTP response |
| Flow gọi REST API và phải dùng response body | HTTP outbound gateway | Request–reply để tiếp tục xử lý |
| Gửi event OrderCreated lên Kafka | Kafka outbound adapter | Publish một chiều; broker ACK không phải business reply |
| Tiêu thụ event OrderCreated từ Kafka | Kafka inbound adapter | Đưa record vào messaging flow; có cơ chế offset riêng |
| Gửi thông báo tới JMS/AMQP queue | JMS/AMQP outbound adapter | Tạo message cho hệ thống nhận |
| Gửi JMS request và đợi reply từ reply destination | JMS outbound gateway | Cần cơ chế correlation và đợi phản hồi |
| Truy vấn database để lấy kết quả cho bước kế tiếp | Endpoint/gateway có request–reply phù hợp | Flow cần sử dụng dữ liệu phản hồi, không chỉ thực hiện update |
| Ứng dụng Java muốn gọi flow như phương thức | @MessagingGateway | Che chi tiết channel/message với caller |

Không có quy tắc rằng **một giao thức chỉ có một loại endpoint**. Cùng là HTTP có thể có inbound adapter, inbound gateway, outbound adapter hoặc outbound gateway; loại nào phù hợp phụ thuộc vào hợp đồng request và response. Tương tự, JMS có cả adapter nhận/gửi một chiều lẫn gateway request–reply.

## 7. Timeout, retry và lỗi: khác nhau thế nào?

### 7.1. Adapter một chiều

Adapter chủ yếu báo trạng thái theo việc nhận hoặc gửi ở cấp endpoint/client. Lỗi có thể do dữ liệu không hợp lệ, kết nối, quyền truy cập, cấu hình destination, quá tải hoặc I/O thất bại.

- Với **DirectChannel**, outbound handler đồng bộ có thể ném exception ngược về caller.
- Với **ExecutorChannel** hoặc QueueChannel, tác vụ gửi có thể thất bại sau khi producer đã được trả về thành công; cần cơ chế ErrorMessage, retry hoặc lưu trạng thái riêng.
- Với inbound message-driven adapter, cần xét acknowledgment/commit/redelivery của nguồn; với inbound polling, phải xét poller, bộ lọc nguồn và cách khôi phục sau restart.

Adapter không tự bảo đảm dữ liệu không trùng hay không mất. Ví dụ, một Kafka producer mất kết nối sau khi broker đã nhận event nhưng trước khi client có xác nhận; nếu gửi lại, consumer có thể thấy hai event cùng nội dung.

### 7.2. Gateway request–reply

Gateway có thêm yêu cầu **hoàn tất một lượt trao đổi**: phải nhận đúng reply, chuyển nó thành kiểu mà caller mong đợi và xử lý nếu reply không đến.

- **Timeout:** đặt thời hạn chờ phản hồi phù hợp với SLA của hệ thống. Timeout chỉ cho biết caller chưa nhận reply kịp, **không chứng minh tác vụ bên đích chưa chạy**.
- **Tương quan:** khi có nhiều request đồng thời hoặc reply qua broker, cần sử dụng correlation ID/reply destination thích hợp để trả kết quả về đúng caller.
- **Kết quả lỗi:** cần phân biệt lỗi kỹ thuật như timeout với phản hồi nghiệp vụ như “hết hạn mức”, “không đủ tồn kho”. Có thể thiết kế payload phản hồi hoặc kênh lỗi riêng.
- **Retry:** một gateway retry request có thể tạo side effect lặp lại ở đích. Với lệnh tạo tài nguyên, cần idempotency key ổn định và cơ chế đối soát.
- **Response contract:** phải quy định kiểu dữ liệu reply, schema, mã lỗi, thông tin tương quan và thời hạn còn giá trị của kết quả.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant S as Hệ thống đích
    C->>G: Request #A
    G->>S: Gửi request #A
    Note over G: Chờ trong giới hạn timeout
    G-->>C: Timeout
    S-->>G: Reply #A đến muộn
    Note over G,S: Cần xử lý reply muộn<br/>và trạng thái công việc
~~~

Sơ đồ cho thấy vì sao retry sau timeout phải được thiết kế cẩn thận. Lần gọi trước có thể đã làm thay đổi trạng thái ở hệ thống đích. Reply đến muộn cũng cần được xử lý theo quy tắc của gateway và hạ tầng; không được mặc nhiên coi nó là reply của một request mới.

### 7.3. errorChannel không đồng nghĩa replyChannel

**replyChannel** phục vụ dữ liệu trả về cho hợp đồng request–reply. **errorChannel** được dùng trong các cấu hình xử lý lỗi để tiếp nhận ErrorMessage. Khi một handler ném exception, cách lỗi được báo về caller, được chuyển sang errorChannel hoặc được listener container xử lý phụ thuộc thread, channel, endpoint và cấu hình thực tế.

Không nên gửi thẳng một ErrorMessage bất kỳ vào replyChannel rồi giả định caller luôn nhận được một phản hồi nghiệp vụ hợp lệ. Cần định nghĩa rõ cách biến lỗi thành mã/trạng thái và dữ liệu mà đối tác hoặc API caller hiểu được.

## 8. Số lượt gọi và năng lực xử lý

Gateway tạo thêm quan hệ thời gian giữa caller và kết quả:

| Tiêu chí | Channel adapter một chiều | Gateway request–reply |
| --- | --- | --- |
| Caller có cần đợi dữ liệu nghiệp vụ trả về? | Không | Có, trừ khi thiết kế API bất đồng bộ riêng |
| Rủi ro khi downstream chậm | Backlog hoặc giữ luồng tùy channel/client | Backlog, giữ request đang chờ, timeout và kết quả đến muộn |
| Theo dõi tương quan | Hữu ích cho truy vết/đối soát | Thiết yếu khi có nhiều request/reply bất đồng bộ |
| Giới hạn tải | Poller, concurrency, queue capacity, rate limit | Các giới hạn trên cộng với số request đang chờ, timeout, pool kết nối |
| Mức xác nhận | Theo adapter và giao thức | Theo hợp đồng phản hồi cùng bảo đảm của đích |
| Retry an toàn | Cần idempotency khi có side effect | Càng cần kiểm soát vì timeout có thể che giấu việc side effect đã xảy ra |

Chẳng hạn, API xử lý mất 30 giây trong khi HTTP gateway timeout sau 3 giây sẽ khiến caller thấy lỗi dù API có thể hoàn tất muộn. Trong một nghiệp vụ dài, nên xem xét thiết kế **202 Accepted + job ID + tra cứu trạng thái/callback** thay vì bắt một kết nối request–reply chờ quá lâu.

Mô hình bất đồng bộ này có thể dùng adapter để tiếp nhận hoặc phát sự kiện, nhưng hợp đồng truy vấn trạng thái cần được mô tả riêng. Đổi endpoint không thay thế việc quyết định UX và SLA của hệ thống.

## 9. Giao dịch và mức bảo đảm giao nhận

Một request–reply thành công không tự bảo đảm **exactly-once end-to-end**. Ví dụ:

1. Gateway gọi API tạo thanh toán; phía đích tạo thanh toán thành công.
2. Kết nối mất trước khi response đến caller.
3. Caller nhận timeout và gửi lại cùng thao tác.

Nếu API thiếu idempotency key, có thể tạo hai giao dịch. Tương tự, khi outbound adapter gửi sự kiện tới broker nhưng trạng thái gửi chưa kịp được ghi nhận, lần chạy lại có thể phát lại.

Những cơ chế cần đánh giá:

- **Idempotency key:** khóa nghiệp vụ ổn định giữa các lần retry, được phía xử lý kiểm tra.
- **Correlation ID:** để đối soát request–reply và truy vết, không mặc nhiên thay thế idempotency key.
- **Outbox/inbox:** giúp quản lý việc lưu trạng thái nghiệp vụ và phát/tiêu thụ message qua nhiều tài nguyên.
- **Acknowledgment/offset:** phải hiểu cơ chế JMS, AMQP, Kafka khi phát hoặc nhận message.
- **Transaction:** chỉ khẳng định phạm vi nguyên tử khi các tài nguyên và cấu hình thực sự hỗ trợ.
- **Compensation:** xử lý khi nhiều hệ thống đã ghi thành công một phần và không có transaction chung.

Với file/SFTP, vấn đề tương tự xuất hiện khi tệp đã được ghi nhưng ứng dụng ngừng trước khi đánh dấu “đã xuất”; việc xuất lại cần quy tắc đặt tên/ghi đè và đối soát. Với HTTP gateway, cần quy định ý nghĩa các mã status và khả năng gọi lại sau khi timeout.

## 10. Hướng dẫn thiết kế một flow thực tế

Khi chọn endpoint, làm theo trình tự:

1. **Xác định ai khởi tạo tương tác.** Hệ thống ngoài gửi vào, hay flow trong ứng dụng gửi ra?
2. **Xác định dữ liệu có cần phản hồi.** Bước tiếp theo có bắt buộc lấy kết quả nghiệp vụ từ bên kia không?
3. **Thiết kế payload và headers.** Chọn kiểu request/reply, schema, correlation ID, idempotency key và header được ánh xạ sang giao thức.
4. **Lựa chọn channel.** DirectChannel cho đường đồng bộ đơn giản; ExecutorChannel/QueueChannel khi cần tách tải, kèm capacity và đường lỗi.
5. **Đặt giới hạn thời gian.** Timeout gửi request, kết nối, nhận reply và retry backoff không nhất thiết là một giá trị.
6. **Xác định mức hoàn tất.** Gửi vào channel, đích chấp nhận, hay nghiệp vụ cuối hoàn thành?
7. **Kiểm tra lỗi và khởi động lại.** Mất kết nối, reply muộn, message trùng, queue đầy, thay đổi schema và sự cố tiến trình.

### 10.1. Kịch bản kiểm thử tối thiểu

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Adapter ghi file thành công | File có đúng nội dung, tên và vị trí |
| Adapter ghi file thất bại | Exception hoặc error flow được quan sát, không báo thành công sai |
| Gateway nhận reply bình thường | Kết quả đúng kiểu, đúng request và đúng thời hạn |
| Gateway không có reply | Timeout được phát hiện; caller có phương án xử lý |
| Handler ném exception | Lỗi được ánh xạ đúng, không treo caller vô hạn |
| Hai request đồng thời | Reply không bị trả nhầm giữa các request |
| Reply đến sau timeout | Không gây trạng thái nghiệp vụ hoặc phiên gọi sai |
| Retry khi trạng thái không rõ | Khóa idempotency vẫn ổn định, không tạo tác động trùng |
| Ứng dụng khởi động lại | Message chưa xử lý/đã gửi được khôi phục theo chính sách đã chọn |

## 11. Những nhầm lẫn thường gặp

**“Một chiều” nghĩa là không cần xử lý lỗi.** Sai: lỗi kết nối, serialize, quyền ghi và timeout vẫn phải được báo hoặc quản lý.

**Nhận ACK của broker nghĩa là đã có reply nghiệp vụ.** ACK xác nhận một mức giao nhận của broker; thường không nói gì về việc consumer hoàn tất nghiệp vụ.

**Gateway hai chiều bảo đảm không mất hoặc trùng message.** Request–reply chỉ mô tả hợp đồng trao đổi; cần transaction, idempotency và xác nhận phù hợp để kiểm soát giao nhận.

**Cứ gọi HTTP là phải dùng gateway.** Nếu flow cần response body thì outbound HTTP gateway phù hợp; nếu chỉ cần phát một thao tác một chiều, có thể dùng adapter theo khả năng endpoint và hợp đồng API.

**@MessagingGateway luôn gọi ra hệ thống ngoài.** Annotation này tạo giao diện Java đối với flow nội bộ; bên trong flow mới quyết định có dùng HTTP/JMS gateway hay không.

**Gateway hết timeout thì thao tác bên đích chắc chắn thất bại.** Hệ thống đích có thể đã thực hiện, đang thực hiện hoặc reply đã mất; phải thiết kế đối soát.

**replyChannel và errorChannel là một.** Một kênh chuyển reply nghiệp vụ, kênh kia dành cho đường xử lý lỗi tùy cấu hình; không được đánh đồng hợp đồng của chúng.

## 12. Câu hỏi tự kiểm tra

1. Một outbound adapter ghi file thành công nhưng không trả về message nghiệp vụ. Vì sao việc ghi file xong không biến nó thành gateway?
2. Nếu HTTP client gọi vào ứng dụng và cần nhận mã đơn hàng ngay trong response, bạn chọn inbound adapter hay inbound gateway? Vì sao?
3. Khi flow gọi một API tính thuế rồi sử dụng giá trị thuế để tính tổng tiền, vì sao outbound gateway phù hợp?
4. Trong Spring Integration, @MessagingGateway giải quyết bài toán nào khác với outbound HTTP gateway?
5. Header replyChannel có vai trò gì? Khi nào phải dùng correlation ID?
6. Nếu gateway trả timeout nhưng đối tác đã tạo đơn hàng, retry cần bổ sung cơ chế gì để tránh tạo hai đơn hàng?
7. Vì sao DirectChannel và ExecutorChannel dẫn đến cách quan sát lỗi khác nhau?
8. Khi một message Kafka được broker chấp nhận, mức xác nhận đó có phải business reply từ consumer không?

## Tổng kết

**Channel adapter** kết nối các hệ thống ngoài vào hoặc ra khỏi Spring Integration theo **luồng message một chiều**; **gateway** bổ sung **hợp đồng request–reply** để caller hoặc flow nhận và sử dụng kết quả. Lựa chọn đúng bắt đầu từ hai câu hỏi: **ai khởi tạo tương tác** và **có cần dữ liệu phản hồi nghiệp vụ không**. Sau đó cần thiết kế channel, payload/headers, replyChannel, errorChannel, timeout, correlation, retry và idempotency theo giao thức cụ thể. Cách phân biệt này giúp triển khai đúng luồng file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu mà không nhầm xác nhận kỹ thuật với kết quả nghiệp vụ.
