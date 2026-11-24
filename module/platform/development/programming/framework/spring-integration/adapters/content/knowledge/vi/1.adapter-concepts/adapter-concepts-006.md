# Ánh xạ message với tài nguyên hoặc giao thức bên ngoài

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách Spring Integration chuyển dữ liệu giữa **Message** nội bộ và tài nguyên/giao thức bên ngoài thông qua **channel adapter** hoặc gateway.
- Phân biệt **payload mapping**, **header mapping**, **message conversion/serialization** và **transformer** nghiệp vụ.
- Thiết kế hợp đồng inbound/outbound cho file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu.
- Xây dựng một IntegrationFlow Java DSL minh họa ánh xạ File đầu vào thành nội dung String và ghi ra file mới với tên được chọn qua header.
- Kiểm tra những vấn đề quan trọng: kiểu dữ liệu, encoding, schema, metadata, lỗi ánh xạ, retry, idempotency và vòng đời kết nối.

## 1. Tại sao cần ánh xạ giữa message và hệ thống ngoài?

Mỗi hệ thống có cách biểu diễn dữ liệu khác nhau. File system lưu **tệp và đường dẫn**; HTTP trao đổi **method, URL, headers, body, status**; JMS/AMQP trao đổi **message và thuộc tính broker**; Kafka trao đổi **record có topic, key, value, partition, offset**; database lưu **hàng và cột**. Trong khi đó, các endpoint bên trong Spring Integration làm việc với một mô hình chung:

~~~text
Message<?>
├── payload: dữ liệu chính của message
└── headers: metadata phục vụ định tuyến, tương quan và xử lý
~~~

**Ánh xạ message (message mapping)** là quá trình xác định dữ liệu và metadata của một bên tương ứng với thành phần nào ở phía còn lại. Việc này diễn ra theo cả hai hướng:

- **Inbound:** tài nguyên hoặc biểu diễn của giao thức ngoài → payload/headers của Message → MessageChannel.
- **Outbound:** Message từ MessageChannel → payload/headers được chuyển thành tài nguyên hoặc lệnh gửi ra giao thức ngoài.

Ví dụ, khi nhận tệp CSV từ đối tác, một file inbound adapter có thể phát message với **payload là File**, chưa phải nội dung CSV đã parse. Bước tiếp theo có thể đọc file thành String rồi parse thành Order. Ngược lại, khi gửi Order ra Kafka, ứng dụng phải xác định **key, value, topic và serializer** trước khi producer có thể phát bản ghi.

~~~mermaid
flowchart LR
    IN["Hệ thống ngoài<br/>File / HTTP / Broker / DB"] --> A["Inbound adapter<br/>đọc và ánh xạ đầu vào"]
    A --> M1["Message<br/>payload + headers"]
    M1 --> C1["MessageChannel"]
    C1 --> T["Transformer / Service<br/>chuẩn hóa domain"]
    T --> C2["MessageChannel"]
    C2 --> M2["Message<br/>payload + headers"]
    M2 --> O["Outbound adapter<br/>ánh xạ đầu ra"]
    O --> OUT["Hệ thống đích"]
~~~

Channel adapter xử lý **ranh giới kết nối**; transformer thường xử lý **chuyển đổi biểu diễn bên trong flow**; service activator áp dụng **logic nghiệp vụ**. Một adapter có thể tích hợp converter hoặc header mapper chuyên dụng, nhưng không vì vậy mà mọi phép chuyển đổi phải nằm trong adapter.

## 2. Bốn lớp ánh xạ cần tách biệt

Khi một message đi qua biên của hệ thống, thường có bốn quyết định:

| Lớp | Đối tượng được ánh xạ | Ví dụ |
| --- | --- | --- |
| **1. Nguồn/đích** | Kết nối và tài nguyên được đọc/ghi | Thư mục SFTP, HTTP URL, JMS queue, Kafka topic, bảng DB |
| **2. Payload** | Dữ liệu được đóng gói trong Message hoặc nội dung gửi đi | File → String; JSON bytes → DTO; DTO → JSON bytes |
| **3. Headers/metadata** | Thông tin dùng để định tuyến, truy vết và điều khiển | File name, Content-Type, correlation ID, Kafka key, message properties |
| **4. Ngữ nghĩa giao nhận** | Thời điểm ghi nhận đã nhận/gửi, lỗi và xử lý lại | Commit offset, ACK, transaction, retry, idempotency |

Lớp thứ tư rất dễ bị bỏ sót. **Ánh xạ payload đúng chưa đủ để bảo đảm hệ thống hoạt động đúng.** Nếu dữ liệu đã được gửi ra ngoài nhưng ứng dụng mất kết nối trước khi nhận xác nhận, thao tác thử lại có thể gửi trùng. Tương tự, channel đã chấp nhận message chưa chắc hệ thống đích đã xử lý xong nghiệp vụ.

### 2.1. Payload là kiểu dữ liệu, không phải tên nghiệp vụ

Hai nguồn cùng cung cấp “đơn hàng” có thể tạo ra message khác nhau:

~~~text
File inbound adapter       Message<File>
HTTP inbound gateway       Message<String> hoặc Message<DTO>
JMS inbound adapter        Message<String / byte[] / DTO / ...>
Kafka inbound adapter      Message<record value tùy deserializer>
JDBC inbound adapter       Message<dữ liệu hàng/batch tùy cấu hình>
~~~

Không được suy ra rằng **mọi adapter trả về cùng một kiểu payload** chỉ vì dữ liệu có cùng ý nghĩa nghiệp vụ. Kiểu payload phụ thuộc adapter, converter/deserializer và cấu hình endpoint. Trước khi nối flow với handler, phải xác định kiểu dữ liệu đầu vào mà handler thực sự nhận.

### 2.2. Headers có thể thuộc nội bộ hoặc giao thức

Các header như **id**, **timestamp**, **replyChannel** và **errorChannel** phục vụ hạ tầng messaging. Một số header khác mô tả nguồn/đích như tên file, Content-Type, correlation ID hoặc routing key. Tuy nhiên:

- Không phải mọi header trong Message đều có trường tương đương ở giao thức đích.
- Không phải mọi metadata của nguồn đều được adapter tự động đưa vào headers.
- Tên header và cách ánh xạ phụ thuộc module/phiên bản/cấu hình cụ thể.
- Header chứa đối tượng nội bộ như MessageChannel thường **không phù hợp để serialize** sang broker hoặc HTTP.

Vì vậy nên có **danh sách cho phép (allowlist)** cho metadata thực sự cần truyền qua ranh giới tin cậy, thay vì sao chép nguyên toàn bộ MessageHeaders.

## 3. Ánh xạ inbound: từ tài nguyên ngoài thành Message

Inbound channel adapter được kích hoạt bởi poller hoặc cơ chế listener/consumer, nhận dữ liệu rồi đưa một Message vào channel. Có thể xét lần lượt:

1. **Nguồn:** dữ liệu đến từ file path, message broker, HTTP request hay câu lệnh truy vấn?
2. **Biểu diễn ban đầu:** File, byte array, String, record hoặc một đối tượng client?
3. **Chuyển đổi cần thiết:** giải mã charset, deserialize JSON, parse CSV, chuẩn hóa ngày giờ?
4. **Metadata cần giữ:** tên file, nguồn đối tác, event ID, correlation ID, thời gian nhận, key/offset?
5. **Thời điểm ghi nhận:** khi adapter đọc được, khi channel nhận hay sau khi nghiệp vụ hoàn tất?

### 3.1. File và SFTP

Với file inbound adapter, payload thường là **File** trỏ tới tệp được chọn. Các thông tin như tên file hoặc đường dẫn có thể dùng để truy vết hoặc quyết định bước xử lý. Nhưng **File không phải nội dung file**:

~~~mermaid
flowchart LR
    F["orders-1001.csv<br/>trên ổ đĩa"] --> IA["File inbound adapter"]
    IA --> MF["Message<File>"]
    MF --> TR["Đọc UTF-8 + parse CSV"]
    TR --> MO["Message<Order>"]
    MO --> CH["ordersChannel"]
~~~

Đối với SFTP, việc đồng bộ file từ máy chủ về máy cục bộ, đọc nội dung tệp từ xa hoặc sử dụng streaming message source tạo ra các hợp đồng payload khác nhau tùy kiểu endpoint và cấu hình. Không nên tự giả định một SFTP inbound adapter luôn trả về File cục bộ hoặc luôn trả InputStream.

Cần thỏa thuận cách **bàn giao file đã hoàn tất**: file ghi dở có thể được poller phát hiện nếu chỉ dùng bộ lọc tên. Quy ước file tạm rồi đổi tên, tín hiệu hoàn tất hoặc lọc theo tuổi file thường cần được bổ sung.

### 3.2. HTTP

HTTP chứa **method, URL, path/query parameters, headers và body**. Inbound endpoint cần quyết định phần nào đi vào payload, header nào được ánh xạ sang MessageHeaders và cách trả response.

Ví dụ một HTTP POST chứa JSON:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
X-Correlation-Id: req-517

{"orderId":"O-1001","totalVnd":150000}
~~~

Nếu adapter/gateway cấu hình nhận body dạng String, payload có thể là chuỗi JSON. Nếu có converter phù hợp, payload có thể là DTO. **X-Correlation-Id không tự biến thành khóa idempotency**; hai mục đích cần được xác định riêng theo hợp đồng.

Khi HTTP client **cần response body/status theo kết quả flow**, hãy chọn **inbound HTTP gateway** và cấu hình request–reply cùng timeout. Nếu chỉ cần đưa sự kiện một chiều vào hệ thống, inbound adapter có thể phù hợp tùy hợp đồng và loại endpoint.

### 3.3. JMS, AMQP và Kafka

Broker mang cả nội dung message và metadata giao thức:

| Nguồn | Nội dung có thể thành payload | Metadata cần xem xét |
| --- | --- | --- |
| JMS | TextMessage, BytesMessage hoặc đối tượng đã convert | Destination, message ID, correlation ID, properties, redelivery |
| AMQP | Body bytes hoặc đối tượng đã convert | Exchange, routing key, delivery tag, content type, headers |
| Kafka | Value sau deserializer, record hoặc payload tùy adapter | Topic, partition, offset, key, timestamp, consumer group |

Kafka consumer thường deserialize record value bằng cấu hình client trước khi adapter chuyển nó vào Spring Integration. **Spring Integration poller** không đồng nghĩa với vòng poll nội bộ của Kafka consumer.

Đặc biệt, **offset**, **acknowledgment** và **correlation ID** có ý nghĩa khác nhau:

- Offset Kafka đánh dấu vị trí record trong partition, không phải ID nghiệp vụ.
- ACK của JMS/AMQP/Kafka thuộc cơ chế giao nhận của từng công nghệ.
- Correlation ID giúp đối chiếu request/reply hoặc theo dõi luồng, không mặc nhiên ngăn tạo đơn hàng trùng.

## 4. Ánh xạ outbound: từ Message thành thao tác bên ngoài

Khi gửi ra ngoài, outbound channel adapter tiêu thụ Message từ channel, chuyển payload và headers thành đầu vào mà client đích hiểu được. Một số ví dụ:

| Đích | Payload/biểu diễn cần gửi | Thông tin định tuyến cần có |
| --- | --- | --- |
| File cục bộ | String, byte array, File hoặc payload được handler hỗ trợ | Đường dẫn thư mục, tên file, chế độ xử lý file đã tồn tại |
| SFTP | Nội dung/tệp theo cấu hình outbound adapter | Remote directory, tên tệp, session/credential, chính sách temp file |
| HTTP | Body bytes, String hoặc DTO qua converter | URL, method, Content-Type, auth và headers được phép |
| JMS | JMS Message thông qua converter | Destination, correlation và các JMS properties phù hợp |
| AMQP | Message body và properties | Exchange, routing key, content type và serializer |
| Kafka | ProducerRecord tương ứng topic/key/value | Topic, key, serializer, partition nếu cần |
| JDBC/DB | Các giá trị cho câu lệnh cập nhật/insert | Bảng, khóa, transaction, schema và tham số SQL |

**Adapter một chiều không trả message phản hồi nghiệp vụ về flow.** Nếu cần HTTP response body, reply của JMS request hoặc kết quả truy vấn được dùng tiếp, hãy cân nhắc gateway hay endpoint request–reply thích hợp. Adapter vẫn có thể ném exception hoặc nhận xác nhận ở cấp I/O.

### 4.1. Ví dụ một domain event được ánh xạ khác nhau

Giả sử bên trong ứng dụng có event:

~~~json
{
  "eventId": "evt-1001",
  "type": "ORDER_CREATED",
  "orderId": "O-1001",
  "totalVnd": 150000
}
~~~

Cùng một event có thể được trình bày khác nhau tùy đích:

- **File:** tên file theo event ID, nội dung JSON UTF-8, tránh ghi đè ngoài ý muốn.
- **HTTP:** JSON body, Content-Type application/json, header idempotency theo thỏa thuận với API.
- **Kafka:** value JSON hoặc Avro/Protobuf theo schema; key có thể là orderId để giữ thứ tự theo khóa trong phạm vi partition, topic được cấu hình.
- **JMS/AMQP:** body qua message converter, correlation ID/properties được ánh xạ đúng chuẩn.
- **Database:** ghi hàng có eventId là khóa duy nhất và các cột tương ứng.

Đây là **một sự kiện nghiệp vụ** nhưng không có nghĩa các adapter dùng chung cách serialize, header hay mức xác nhận.

## 5. Header mapping: giữ metadata nào, chuyển metadata nào?

Các hệ thống thường mắc lỗi khi cố chuyển toàn bộ headers của Spring Message thành headers của HTTP hoặc broker. Việc này có thể gây lỗi serialize, lộ dữ liệu nội bộ hoặc tạo nhầm định tuyến.

| Header/metadata | Mục đích | Lưu ý khi vượt biên |
| --- | --- | --- |
| **id, timestamp** | Theo dõi vòng đời Message | Có thể đổi khi tạo Message mới; không thay event ID nghiệp vụ |
| **correlation ID** | Truy vết nhiều bước hoặc ghép request/reply | Thống nhất tên, kiểu và phạm vi với đối tác |
| **replyChannel / errorChannel** | Định tuyến reply và error nội bộ | Thường là tham chiếu hạ tầng, không serialize trực tiếp |
| **file name** | Đặt tên file đầu ra hoặc truy vết nguồn | Kiểm tra path traversal, ký tự không hợp lệ, quy tắc trùng tên |
| **Content-Type** | Chỉ kiểu media của body | Phải khớp serializer và charset thực tế |
| **Kafka key/topic** | Định tuyến record theo broker | Dùng header/DSL đúng module và cấu hình; không giả định giống JMS |
| **JMS/AMQP properties** | Thuộc tính giao thức và tương quan | Header mapper/converter quyết định trường được mang qua |
| **eventId/schemaVersion** | Định danh nghiệp vụ và version hợp đồng | Nên định nghĩa rõ trong payload/header theo thỏa thuận hai bên |

Ví dụ, nếu Message có **replyChannel** là một đối tượng DirectChannel, việc chuyển nguyên header này sang JSON hoặc Kafka properties không có ý nghĩa đối với consumer phía ngoài. Ngược lại, **eventId** và **schemaVersion** có thể cần được lưu trong body để đối tác xử lý chính xác.

### 5.1. Whitelist, blacklist và an toàn dữ liệu

Nên xác định rõ:

1. Những header **bắt buộc** phải có.
2. Những header **được phép** đi qua ranh giới hệ thống.
3. Header nào cần **đổi tên, đổi kiểu hoặc chuẩn hóa giá trị**.
4. Header nào mang dữ liệu nhạy cảm, không được đưa vào log hoặc broker.
5. Có hay không cần **ký/xác thực** dữ liệu ở mức giao thức.

Đối với HTTP, chỉ chuyển những header phù hợp như Content-Type, correlation ID hoặc header nghiệp vụ được cho phép. Đối với JMS/AMQP, dùng header mapper và converter của module tương ứng. Không dựa vào việc một tên header xuất hiện ở Spring Message để kết luận client sẽ tự gửi header đó ra bên ngoài.

### 5.2. Metadata nguồn không nhất thiết là metadata đích

Giả sử file nguồn tên **orders-1001.csv** được parse thành một đối tượng Order, rồi gửi thành event Kafka:

- Tên file nguồn có thể có ích cho audit.
- Kafka key nên được chọn theo ID đơn hàng hoặc khóa phân vùng phù hợp.
- Kafka topic thuộc cấu hình định tuyến sự kiện.
- Offset Kafka sẽ do broker xác định cho record được ghi, không thể lấy tên file để gán tùy tiện.

Việc ghép đúng metadata cần dựa trên **ngữ nghĩa của từng hệ thống**, không chỉ sao chép các chuỗi header trùng tên.

## 6. Converter, serializer và transformer: dùng ở lớp nào?

Mỗi dạng chuyển đổi nên được đặt ở lớp phù hợp:

| Cơ chế | Thường xử lý | Ví dụ |
| --- | --- | --- |
| **Deserializer** của client | Byte từ giao thức → kiểu dữ liệu client | Kafka byte[] → String/record |
| **Message converter** của adapter | Đối tượng của giao thức ↔ payload hoặc message | JMS TextMessage ↔ String; HTTP JSON ↔ DTO |
| **Header mapper** | Thuộc tính giao thức ↔ MessageHeaders | HTTP headers, JMS/AMQP properties |
| **Transformer** trong flow | Payload/message nội bộ → hình dạng mà downstream cần | String CSV → Order; Order → JSON DTO |
| **Serializer** của client | Dữ liệu ứng dụng → bytes/record gửi đi | Kafka String/DTO → bytes |

Một phép chuyển đổi có thể thực hiện ở nhiều chỗ, nhưng phải **biết rõ nơi nào chịu trách nhiệm chính**. Ví dụ, nếu HTTP message converter đã chuyển JSON thành DTO thì transformer phía sau không nên parse JSON thêm lần nữa. Nếu source Kafka chỉ cung cấp String JSON, cần transformer hoặc converter thích hợp để tạo DTO trước service activator.

### 6.1. Charset, Content-Type và schema

Đối với String/bytes, cần quy định charset (thường UTF-8) khi encode/decode. Đừng xem Content-Type là lời bảo đảm nội dung luôn đúng định dạng. Chẳng hạn header application/json không ngăn payload chứa JSON sai cú pháp.

Với JSON, CSV, Avro hoặc Protobuf, cần quy định:

- Schema/version nào đang được dùng.
- Trường bắt buộc, trường tùy chọn, giá trị mặc định.
- Cách xử lý trường mới hoặc trường không còn dùng.
- Cách chuyển kiểu dữ liệu số, ngày giờ, timezone và định danh.
- Cách phản ứng khi dữ liệu không tương thích.

Đối với CSV, split theo dấu phẩy không đủ cho dữ liệu có dấu phẩy, dấu nháy hoặc xuống dòng. Với dữ liệu thực, cần thư viện CSV parser/encoder đúng chuẩn và kiểm tra độ lớn đầu vào.

## 7. Ví dụ Java DSL: ánh xạ File đầu vào thành file đầu ra

Ví dụ tập trung vào hai ranh giới:

1. **Inbound file adapter** đọc nguồn **./data/inbox** và tạo Message có payload kiểu File.
2. **Transformer** chuyển nội dung file thành String UTF-8.
3. **Header enricher** tạo header ứng dụng **exportFileName** trước khi payload đổi kiểu.
4. **Outbound file adapter** dùng payload String làm nội dung file, lấy **exportFileName** làm tên file đích.

Đầu vào ví dụ là file văn bản **order-1001.txt**. Đầu ra dự kiến là **mapped-order-1001.txt** trong thư mục **./data/outbox**. Đây là ví dụ diễn giải cơ chế mapping, chưa phải hệ thống xử lý đơn hàng hay CSV parser.

~~~mermaid
flowchart LR
    F["./data/inbox/order-1001.txt"] --> IA["File inbound adapter"]
    IA --> MF["Message<File>"]
    MF --> EH["Header enricher<br/>exportFileName"]
    EH --> TR["Transformer<br/>File → String UTF-8"]
    TR --> MS["Message<String><br/>exportFileName"]
    MS --> OA["File outbound adapter"]
    OA --> OUT["./data/outbox/mapped-order-1001.txt"]
~~~

### 7.1. Cấu hình Spring Integration

Trong Spring Boot, dùng dependency cho Spring Integration cùng module **spring-integration-file** phù hợp với phiên bản được Spring Boot quản lý.

~~~java
import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;

@Configuration
@EnableIntegration
public class FileMappingConfiguration {

    @Bean
    public IntegrationFlow fileMappingFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.txt"),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))

            // Khi payload con la File, co the lay ten tep nguon.
            .enrichHeaders(spec -> spec.headerFunction(
                "exportFileName",
                message -> {
                    File source = (File) message.getPayload();
                    return "mapped-" + source.getName();
                }))

            // Payload: File -> String, giu exportFileName cho buoc sau.
            .transform(File.class, source -> {
                try {
                    return java.nio.file.Files.readString(
                        source.toPath(), StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })

            // Payload String tro thanh noi dung file dich.
            .handle(Files.outboundAdapter(new File("./data/outbox"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(
                        "exportFileName"))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }
}
~~~

**Điều diễn ra ở từng bước:**

| Bước | Payload | Header đáng chú ý | Trách nhiệm |
| --- | --- | --- | --- |
| Inbound adapter | File | Metadata nguồn nếu được cung cấp | Tìm/nhận tệp từ thư mục |
| Header enricher | File | exportFileName = mapped-order-1001.txt | Quy định tên xuất theo hợp đồng nội bộ |
| Transformer | String | exportFileName được mang qua theo cơ chế transformer | Đọc UTF-8 từ file |
| Outbound adapter | String | Đọc exportFileName | Ghi nội dung String ra tệp đích |

Header **exportFileName** do ứng dụng tự đặt tên; nó **không phải header giao thức mặc định**. Outbound adapter chỉ sử dụng được header này vì fileNameGenerator đã được cấu hình để đọc nó. Đây là một ví dụ quan trọng của **ánh xạ có chủ đích** giữa MessageHeaders và thuộc tính tài nguyên ngoài.

### 7.2. Kiểm chứng kết quả

1. Khởi động ứng dụng có FileMappingConfiguration.
2. Tạo tệp **./data/inbox/order-1001.txt** chứa nội dung **Order O-1001 confirmed**.
3. Sau khi poller chọn file, kiểm tra tệp **./data/outbox/mapped-order-1001.txt** chứa đúng nội dung UTF-8.
4. Tạo tệp **notes.csv** trong inbox: bộ lọc **patternFilter("*.txt")** không chọn file này.
5. Đặt sẵn file đích trùng tên: chế độ **FileExistsMode.FAIL** phải làm thao tác ghi báo lỗi, thay vì âm thầm ghi đè.
6. Thử file chứa dấu tiếng Việt để kiểm tra encoding UTF-8; xem xét cấu hình khi đối tác gửi charset khác.

**Giới hạn của ví dụ:** File inbound chỉ chọn file theo bộ lọc tên; chưa bảo đảm bên gửi đã ghi xong. Cách đặt tên minh họa dùng File.getName(), nhưng với tên do người dùng/đối tác kiểm soát cần xác thực kỹ ký tự, độ dài, path traversal và quy tắc ghi đè. Bản này chưa hỗ trợ file rất lớn hoặc xử lý stream và chưa thiết kế trạng thái nhận lại sau restart. FileExistsMode.FAIL chỉ ngăn ghi đè cùng tên, không phải giải pháp idempotency nghiệp vụ hoàn chỉnh.

## 8. Ví dụ hợp đồng cho một sự kiện đơn hàng

Giả sử nguồn gửi sự kiện OrderCreated và hệ thống cần phổ biến sự kiện qua HTTP và Kafka. Nên mô tả **hợp đồng nội bộ** trước:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "ORDER_CREATED",
  "schemaVersion": 1,
  "orderId": "O-1001",
  "totalVnd": 150000
}
~~~

Sau đó tách cấu hình từng hệ thống:

| Trường hợp | Quy tắc ánh xạ |
| --- | --- |
| HTTP outbound | JSON UTF-8 thành body; Content-Type application/json; URL/method và auth do client/endpoint quản lý; eventId được gửi như idempotency key nếu API hỗ trợ theo hợp đồng |
| Kafka outbound | JSON/Avro/Protobuf thành value theo serializer; topic được định tuyến; key có thể là orderId để phục vụ phân vùng; eventId/schemaVersion nằm ở body hoặc header theo hợp đồng |
| File outbound | Body JSON hoặc CSV theo yêu cầu; tên file được tạo từ eventId đã kiểm tra; cân nhắc ghi tạm rồi công bố |
| JMS/AMQP outbound | Converter ánh xạ payload sang message body; correlation/properties được mapping theo cấu hình broker |
| Database | eventId thành khóa duy nhất trong bảng sự kiện, các trường khác thành cột; transaction và xử lý trùng thuộc hợp đồng lưu trữ |

Không được suy diễn rằng một lần **Kafka producer acknowledgment** nghĩa là consumer đã xử lý đơn hàng. Tương tự, HTTP 202 Accepted không nhất thiết là công việc đã hoàn thành. Hợp đồng phải làm rõ “gửi thành công” nghĩa là mức nào.

### 8.1. Chuẩn hóa một lần hay nhiều lần?

Trong một hệ thống lớn, có thể chọn một **DTO/domain event chuẩn** sau inbound:

~~~text
Nguồn A (CSV) ──┐
                ├──> OrderEvent chuẩn ───> JSON HTTP
Nguồn B (Kafka) ┤                    ├───> Avro Kafka
Nguồn C (HTTP) ─┘                    └───> CSV SFTP
~~~

Cách này giảm phụ thuộc chéo giữa nguồn và đích, nhưng không xóa yêu cầu converter riêng. Khi thay định dạng wire format của Kafka, phần nghiệp vụ có thể giữ nguyên; serializer, schema registry, headers và cách xác nhận phải được kiểm tra lại.

## 9. Ánh xạ sai sẽ gây lỗi gì?

### 9.1. Lỗi dữ liệu

- **Sai payload type:** handler nhận File nhưng downstream mong String hoặc DTO.
- **Sai charset:** UTF-8 bị decode bằng charset khác, dẫn tới dữ liệu tiếng Việt lỗi.
- **Sai schema:** đổi tên trường, thiếu trường bắt buộc hoặc dùng kiểu số không phù hợp.
- **Converter không tương thích:** deserializer/serializer của producer và consumer khác nhau.
- **Header không đúng kiểu:** adapter nhận giá trị header không thể ánh xạ thành thuộc tính giao thức.
- **Metadata bị mất:** correlation ID hoặc event ID cần thiết cho downstream không còn sau transformer tùy chỉnh.

Giải pháp thường là kiểm tra kiểu dữ liệu, schema và header tại đúng ranh giới; chuyển dữ liệu lỗi sang đường cách ly hoặc thông báo lỗi có cấu trúc. **Retry không tự sửa được dữ liệu sai định dạng.**

### 9.2. Lỗi khi gửi/nhận

- Không kết nối được SFTP, HTTP, JMS, AMQP, Kafka hoặc database.
- Hệ thống đích từ chối quyền, kích thước dữ liệu hoặc định dạng không hợp lệ.
- Queue/buffer đầy, producer timeout hoặc server quá tải.
- Tệp được đọc khi bên gửi chưa ghi xong.
- Request đã được gửi nhưng phản hồi mất, khiến trạng thái thành công không rõ.

Với **DirectChannel**, exception downstream có thể lan ngược về luồng gọi gửi. Với **ExecutorChannel** hoặc QueueChannel, lỗi có thể xuất hiện sau khi producer được báo đã chuyển message vào channel; cần **errorChannel**, error handler/advice hoặc callback tương ứng. Không giả định errorChannel mặc định tự retry hoặc lưu bền mọi message lỗi.

~~~mermaid
flowchart TD
    M["Message tại ranh giới"] --> V{"Payload / headers / schema đúng?"}
    V -- "Không" --> BAD["Lỗi hợp đồng: cách ly hoặc sửa dữ liệu"]
    V -- "Có" --> IO["Adapter gọi tài nguyên bên ngoài"]
    IO --> R{"Kết quả I/O"}
    R -- "Thành công" --> OK["Ghi nhận tiến độ"]
    R -- "Lỗi tạm thời" --> RET["Retry có giới hạn và backoff"]
    R -- "Không rõ trạng thái" --> REC["Đối soát + idempotency"]
    R -- "Lỗi không thể phục hồi" --> ERR["Cách ly / cảnh báo"]
    RET --> IO
~~~

## 10. Giao nhận, idempotency và transaction sau bước ánh xạ

Ánh xạ đúng chỉ cho biết dữ liệu **đúng cấu trúc**. Độ tin cậy còn phụ thuộc ngữ nghĩa giao nhận:

1. **Nguồn đã phát dữ liệu**: không có nghĩa inbound adapter đã nhận.
2. **Inbound adapter đã gửi Message vào channel**: không có nghĩa service activator đã hoàn thành.
3. **Outbound adapter đã gửi yêu cầu**: không có nghĩa đích đã xác nhận hoặc xử lý xong.
4. **Đích đã xác nhận ở cấp giao thức**: không có nghĩa bên nhận cuối đã hoàn thành nghiệp vụ.

Ví dụ, đơn hàng O-1001 đã được ghi database nhưng tiến trình dừng trước khi publish Kafka event. Khi chạy lại, có thể phát lại hoặc bỏ sót sự kiện nếu không có chính sách lưu tiến độ. Các mẫu như **transactional outbox**, **idempotent consumer** và khóa nghiệp vụ ổn định giúp giảm rủi ro mất/trùng dữ liệu.

Khóa như **eventId** hoặc **partnerId + orderId** cần ổn định giữa các lần thử. Đừng dùng mỗi MessageHeaders.ID mới sinh ở từng message như bằng chứng duy nhất rằng hai lần nhận là hai nghiệp vụ khác nhau. Cũng không nên tự khẳng định **exactly-once end-to-end** khi file system, HTTP, broker và database không nằm trong một transaction chung.

### 10.1. Vòng đời kết nối ảnh hưởng đến mapping

Mapping và I/O không thể tách rời hoàn toàn khi vận hành:

- **SFTP:** session và remote path phải tồn tại; reconnect/retry có thể đọc lại file.
- **HTTP:** cấu hình client, content negotiation, auth, timeout, response status.
- **JMS/AMQP:** connection factory, listener container, converter, ack/requeue.
- **Kafka:** serializer/deserializer, consumer group, offset, producer acknowledgment.
- **Database:** JDBC connection pool, transaction isolation, khóa duy nhất.
- **File:** quyền truy cập, đường dẫn, kích thước, charset, chính sách công bố file.

Khi nguồn hoặc đích thay đổi phiên bản, cần kiểm tra lại **hợp đồng wire format**, cấu hình connector và hành vi retry. Một thay đổi chỉ ở payload type có thể làm downstream handler ngừng hoạt động dù kết nối vẫn khỏe.

## 11. Kiểm thử ánh xạ một cách có hệ thống

Một bộ kiểm thử có ích nên tập trung vào những ranh giới thực:

| Hạng mục | Kiểm tra cụ thể |
| --- | --- |
| Kiểu payload | Inbound tạo đúng kiểu; transformer và handler nhận kiểu đã định |
| Nội dung | String/bytes đúng charset; JSON/CSV đúng schema và escaping |
| Headers | Các header bắt buộc được gắn, giữ qua transformer và ánh xạ ra ngoài đúng |
| Tên file/địa chỉ | File name không thoát thư mục; topic, URL, destination hợp lệ |
| Kết quả gửi | Kiểm tra file/record/request thực tế, không chỉ dựa trên send vào channel |
| Lỗi dữ liệu | Sai schema, giá trị null, header thiếu, payload quá lớn |
| Lỗi kết nối | Timeout, broker/repository không sẵn sàng, quyền truy cập thiếu |
| Retry | Bản gửi lại có giữ eventId và không tạo side effect trùng? |
| Khởi động lại | Trạng thái nhận/gửi và backlog được khôi phục theo chính sách |
| Bảo mật | Header không cho phép không bị đẩy ra ngoài; log không lộ payload nhạy cảm |

Một cách thiết kế thuận lợi là giữ **unit test cho transformer** và kiểm thử tích hợp riêng đối với adapter. Transformer thuần dữ liệu có thể kiểm thử bằng đối tượng đầu vào/đầu ra. Adapter phải được kiểm thử với tài nguyên hoặc test double tương ứng vì đúng schema chưa chứng minh đường truyền hoạt động.

## 12. Sai lầm thường gặp

**Nhầm Message với dữ liệu thô của giao thức.** Message là mô hình payload/headers nội bộ; cần converter/adapter để biến thành file, HTTP request hay broker record.

**Cho rằng header được sao chép tự động qua mọi giao thức.** Mỗi adapter có header mapping và giới hạn riêng; nên định nghĩa danh sách header được phép và quy tắc chuyển đổi.

**Parse dữ liệu nghiệp vụ ngay trong mọi adapter.** Có thể dùng converter ở biên, nhưng nên tách logic chuẩn hóa domain khỏi trách nhiệm kết nối để dễ kiểm thử và đổi nguồn.

**Coi serializer và transformer là một.** Serializer biến dữ liệu thành biểu diễn wire format; transformer đổi biểu diễn trong flow theo hợp đồng downstream. Có thể kết hợp nhưng phải thống nhất một nơi chịu trách nhiệm cho mỗi phép chuyển đổi.

**Dùng correlation ID thay idempotency key.** Correlation giúp ghép request/reply và truy vết; chống tạo nghiệp vụ trùng cần khóa ổn định và logic kiểm tra phía xử lý.

**Coi ACK của broker là kết quả xử lý cuối.** ACK có phạm vi theo giao thức; consumer có thể chưa chạy nghiệp vụ.

**Bỏ qua schema version.** Một event mới thiếu tương thích có thể làm consumer cũ thất bại dù kết nối và topic không đổi.

**Tin rằng bộ lọc tên file đủ cho tính toàn vẹn.** File đúng đuôi vẫn có thể đang được ghi dở hoặc chứa dữ liệu sai định dạng.

## 13. Câu hỏi tự kiểm tra

1. Vì sao File inbound adapter thường tạo Message có payload File, còn bước parse CSV thành Order nên do transformer thực hiện?
2. Một Message có header replyChannel là đối tượng nội bộ. Có nên chuyển nguyên header đó sang Kafka hoặc JMS properties không? Vì sao?
3. Nếu đổi từ HTTP JSON sang Kafka Avro, những lớp ánh xạ nào phải xem xét lại, và phần nào của mô hình domain có thể giữ nguyên?
4. Khi một serializer lỗi do schema không tương thích, retry có giải quyết được không? Nên xử lý thế nào?
5. Tại sao Kafka offset không nên được dùng thay eventId nghiệp vụ?
6. Trong ví dụ Java DSL, điều gì giúp outbound file adapter biết tên file là mapped-order-1001.txt?
7. Nếu message đã gửi vào ExecutorChannel nhưng file chưa xuất hiện, có thể kết luận adapter thất bại chỉ từ kết quả send không?
8. Tại sao retry sau HTTP timeout có thể tạo giao dịch trùng, ngay cả khi payload và headers đã ánh xạ đúng?
9. Những kiểm thử nào giúp phát hiện lỗi charset, header mapping và xử lý file trùng tên?

## Tổng kết

**Ánh xạ message với tài nguyên hoặc giao thức bên ngoài** là hợp đồng chuyển đổi giữa **payload/headers của Spring Integration Message** và dữ liệu, metadata, phương thức giao nhận của hệ thống kết nối. Inbound adapter đưa dữ liệu vào MessageChannel; outbound adapter chuyển message thành thao tác ra ngoài. Converter, serializer, header mapper và transformer giải quyết các lớp chuyển đổi khác nhau. Khi xây dựng luồng file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu, cần thống nhất đồng thời kiểu payload, schema, charset, metadata, thời điểm xác nhận, retry, idempotency và vòng đời kết nối. Ánh xạ đúng giúp hệ thống hiểu dữ liệu; thiết kế giao nhận đúng giúp dữ liệu được xử lý an toàn.
