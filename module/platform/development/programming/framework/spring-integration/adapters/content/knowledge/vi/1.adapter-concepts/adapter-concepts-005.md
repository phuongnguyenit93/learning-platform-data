# Adapter so với service activator và transformer

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **channel adapter**, **service activator** và **transformer** theo trách nhiệm, đầu vào, đầu ra và tác động phụ.
- Giải thích vì sao ba loại endpoint thường xuất hiện nối tiếp trong cùng một **IntegrationFlow** nhưng không thể coi là thay thế trực tiếp cho nhau.
- Nhận diện vị trí của **MessageChannel**, **Message**, payload, headers và poller trong luồng nhận hoặc gửi dữ liệu.
- Viết một luồng Java DSL gồm file inbound adapter, transformer đọc/chuẩn hóa CSV, service activator xử lý đơn hàng và file outbound adapter xuất biên nhận.
- Chọn thành phần phù hợp khi tích hợp SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu; đánh giá lỗi, retry, idempotency và vòng đời kết nối.

## 1. Ba vai trò khác nhau trong một luồng tích hợp

Giả sử ứng dụng nhận file đơn hàng của đối tác, chuyển CSV thành dữ liệu Java, kiểm tra đơn hàng rồi ghi biên nhận ra thư mục khác. Một thiết kế Spring Integration thường gồm:

~~~mermaid
flowchart LR
    EXT["Thư mục đối tác"] --> IN["File inbound adapter"]
    IN --> CH1["MessageChannel"]
    CH1 --> TR["Transformer<br/>File/CSV → Order"]
    TR --> CH2["MessageChannel"]
    CH2 --> SA["Service activator<br/>kiểm tra và xử lý Order"]
    SA --> CH3["MessageChannel"]
    CH3 --> TR2["Transformer<br/>Receipt → CSV"]
    TR2 --> OUT["File outbound adapter"]
    OUT --> DEST["Thư mục biên nhận"]
~~~

Trong sơ đồ:

- **Channel adapter** nối luồng message với một nguồn hoặc đích **bên ngoài** ứng dụng, chẳng hạn file, SFTP, HTTP, JMS, AMQP, Kafka hoặc database.
- **Transformer** đổi **hình dạng/biểu diễn dữ liệu** của message để bước sau có thể sử dụng, chẳng hạn từ File thành nội dung CSV rồi thành đối tượng Order.
- **Service activator** kích hoạt **một phương thức dịch vụ hoặc hành động ứng dụng** để xử lý message, ví dụ kiểm tra quy tắc, tra cứu hoặc lưu nghiệp vụ.

Ba thành phần cùng tham gia một kiến trúc messaging, nhưng giải quyết ba câu hỏi khác nhau:

| Câu hỏi | Thành phần trả lời |
| --- | --- |
| Dữ liệu **đi vào/đi ra** ứng dụng qua giao thức nào? | Channel adapter |
| Dữ liệu **cần được biểu diễn lại** như thế nào? | Transformer |
| Ứng dụng **cần làm gì** với dữ liệu? | Service activator |

Tách các trách nhiệm này giúp đổi nguồn file thành SFTP hoặc Kafka mà ít tác động tới quy tắc xử lý đơn hàng. Tuy nhiên, khi thay adapter vẫn phải kiểm tra kiểu payload, metadata và ngữ nghĩa nhận/gửi của giao thức mới.

## 2. Bảng so sánh cốt lõi

| Tiêu chí | Channel adapter | Transformer | Service activator |
| --- | --- | --- | --- |
| Mục đích | Nối messaging flow với **hệ thống ngoài** | Biến đổi **payload/message** | Thực thi **logic hoặc dịch vụ** khi có message |
| Ví dụ | Đọc SFTP, nhận JMS, publish Kafka, ghi file | CSV → DTO, JSON → đối tượng, DTO → chuỗi | Kiểm tra đơn hàng, gọi OrderService, tính phí |
| Cơ chế nhận input | Inbound lấy từ nguồn ngoài; outbound nhận từ channel | Nhận message từ input channel | Nhận message từ input channel |
| Đầu ra | Inbound phát message lên channel; outbound tạo tác động bên ngoài | Thường tạo payload/message đã chuyển đổi cho flow tiếp | Có thể phát reply hoặc kết thúc nếu phương thức không trả kết quả |
| Tác động phụ | I/O với nguồn/đích là trách nhiệm chính | Nên ưu tiên ánh xạ dữ liệu, tránh I/O ẩn | Có thể gọi dịch vụ, truy vấn, ghi DB hoặc thực hiện nghiệp vụ |
| Quan tâm chính | Connection, poller/listener, ack, định dạng giao thức | Kiểu dữ liệu, schema, lỗi chuyển đổi, bảo toàn headers | Quy tắc nghiệp vụ, giao dịch, hiệu năng, exception |
| Dùng khi nào? | Khi cần nhận hoặc gửi ra bên ngoài | Khi dạng dữ liệu hiện tại chưa phù hợp | Khi cần kích hoạt hành động ứng dụng |

**Không có quy tắc cấm service activator thực hiện I/O.** Một service activator hoàn toàn có thể gọi HTTP client hoặc repository. Nhưng nếu Spring Integration đã cung cấp adapter/gateway phù hợp cho giao thức đó, dùng endpoint chuyên dụng thường giúp làm rõ trách nhiệm kết nối, hợp đồng message và cấu hình lỗi. Quyết định cuối cùng phụ thuộc nhu cầu thực tế.

**Transformer không chỉ có thể biến đổi kiểu dữ liệu.** Nó có thể chuẩn hóa nội dung, ánh xạ trường, thay cấu trúc payload hoặc trả về một message mới. Dù vậy, nên giữ phép biến đổi dễ dự đoán và hạn chế tác động phụ để thuận tiện kiểm thử, retry và tái sử dụng.

## 3. Channel adapter: chịu trách nhiệm ở ranh giới giao thức

### 3.1. Inbound adapter

Một inbound adapter lấy dữ liệu từ hệ thống ngoài, tạo **Message<?>** và đưa nó vào **MessageChannel**. Tùy nguồn, nó hoạt động qua **poller** hoặc **listener/consumer**:

- **Polling:** đọc thư mục, đồng bộ SFTP hoặc truy vấn DB theo lịch; Spring Integration poller kích hoạt message source.
- **Message-driven:** listener JMS/AMQP, Kafka consumer hay endpoint được kích hoạt bởi sự kiện của hạ tầng. Cơ chế polling bên trong Kafka client không đồng nghĩa với việc người dùng phải thêm Spring Integration poller cho mọi Kafka inbound endpoint.

Ví dụ một file inbound adapter có thể tạo message với **payload là File**. Nó chưa biến nội dung file thành đối tượng Order; đó là việc của transformer/handler phía sau.

### 3.2. Outbound adapter

Một outbound adapter tiêu thụ message từ channel rồi thực hiện tác động ra bên ngoài: ghi file, gửi message tới broker, tải file lên SFTP hoặc cập nhật nguồn dữ liệu. Endpoint này thường kết thúc flow **một chiều**, không trả một message phản hồi nghiệp vụ.

Nếu cần lấy response rồi dùng trong flow, hãy cân nhắc **outbound gateway**. Ví dụ, khi gọi HTTP API để lấy hạn mức tín dụng, gateway phù hợp hơn adapter một chiều vì bước xử lý kế tiếp cần response body.

### 3.3. Adapter vẫn có thể có converter

Nhiều adapter hỗ trợ serializer, converter hoặc header mapper ngay ở ranh giới giao thức. Điều đó **không khiến adapter trở thành transformer nghiệp vụ**:

- Converter tại adapter giải quyết cách biểu diễn dữ liệu trong **giao thức** hoặc API của client.
- Transformer trong flow giải quyết cách biểu diễn dữ liệu **giữa các bước xử lý**, nhất là khi chuẩn hóa từ dữ liệu nguồn sang mô hình domain.

Ví dụ, Kafka adapter có thể deserialize bytes thành String theo cấu hình consumer; transformer tiếp theo parse nội dung JSON thành đối tượng Order. Hai phép biến đổi nằm ở các lớp trách nhiệm khác nhau.

## 4. Transformer: chuyển từ hợp đồng nguồn sang dữ liệu cần dùng

Transformer là một **message endpoint**: nhận message từ channel, biến đổi payload hoặc message và gửi kết quả tới bước tiếp theo. Trong Java DSL, có thể sử dụng thao tác **transform(...)** với lambda, bean hoặc các transformer có sẵn.

~~~mermaid
flowchart LR
    IN["Message<File><br/>headers: nguồn tệp"] --> TR["Transformer"]
    TR --> OUT["Message<Order><br/>headers: nguồn tệp + metadata"]
~~~

Một transformer có thể:

1. Chuyển bytes thành String bằng charset xác định.
2. Parse CSV hoặc JSON thành DTO.
3. Ánh xạ các tên trường của đối tác sang kiểu dữ liệu domain.
4. Chuẩn hóa timezone, mã trạng thái hoặc đơn vị đo.
5. Chuyển OrderReceipt thành chuỗi CSV hoặc JSON để outbound adapter gửi đi.

Ví dụ về phép biến đổi nhỏ, không cần nguồn I/O:

~~~java
record RawOrder(String orderId, String amount) {}
record Order(String orderId, long totalVnd) {}

static Order toOrder(RawOrder raw) {
    return new Order(
        raw.orderId().trim(),
        Long.parseLong(raw.amount().trim())
    );
}
~~~

Hàm này tập trung vào **thay đổi dữ liệu**. Nó chưa gọi database, chưa gửi Kafka và chưa quyết định đơn hàng có hợp lệ theo mọi quy tắc nghiệp vụ. Nếu đầu vào sai định dạng, transformer có thể ném exception; flow phải quy định đường xử lý lỗi.

### 4.1. Payload mới và headers

Message trong Spring Integration có **payload** và **headers**. Khi transformer trả về một payload mới, framework có thể xây dựng output message và giữ các headers thích hợp theo quy tắc của transformer, trừ những headers đặc biệt hoặc trường hợp được cấu hình khác.

Đừng tự giả định rằng mọi header đều luôn được bảo toàn trong mọi kiểu transformer hoặc đều được gửi sang giao thức đích. Cần kiểm tra riêng:

- Header định danh/correlation dùng cho truy vết và đối soát.
- Metadata của file, JMS/AMQP, Kafka hoặc HTTP còn có ý nghĩa ở bước sau hay không.
- Header dùng để định tuyến, đặt tên file, chọn topic hoặc ánh xạ phản hồi có bị thay đổi không.
- DTO được chuẩn hóa có cần giữ source ID và version của sự kiện không.

**MessageHeaders.ID** mới được tạo ở từng message không nên dùng thay **khóa idempotency nghiệp vụ** (ví dụ orderId hoặc eventId ổn định).

### 4.2. Vì sao không nên biến transformer thành nơi xử lý mọi thứ?

Giả sử transformer vừa parse CSV, vừa gọi REST API để kiểm tra hạn mức, vừa ghi database. Khi một lần gửi message bị retry, rất khó biết phép chuyển đổi đã hoàn tất đến đâu và liệu side effect có bị thực hiện lặp lại hay không.

Một thiết kế rõ ràng hơn là:

~~~text
File (adapter)
  -> String/Order (transformer)
  -> kiểm tra hạn mức, lưu thông tin (service activator)
  -> Receipt (transformer xuất định dạng)
  -> File/Kafka (outbound adapter)
~~~

Điều này không buộc mỗi phép biến đổi nhỏ phải có một bean riêng. Có thể dùng lambda cho chuyển đổi đơn giản; dùng class riêng cho mapping phức tạp, có schema hoặc cần kiểm thử độc lập.

## 5. Service activator: gọi dịch vụ xử lý một message

Service activator là một endpoint tiếp nhận message rồi gọi một phương thức Java hoặc một handler. Nó thường dùng để:

- Thực hiện validation theo quy tắc nghiệp vụ.
- Tính phí, phân loại đơn hàng hoặc quyết định trạng thái.
- Gọi application service hoặc repository.
- Ghi nhận trạng thái xử lý hoặc thực hiện một side effect cần kiểm soát giao dịch.
- Tạo đối tượng kết quả để flow tiếp tục.

Một service activator **không nhất thiết kết thúc flow**. Nếu phương thức trả về giá trị hoặc message phù hợp, Spring Integration có thể phát **reply** sang output channel hay replyChannel đã cấu hình.

~~~java
record Order(String orderId, long totalVnd) {}
record Receipt(String orderId, String status, long totalVnd) {}

class OrderService {
    public Receipt accept(Order order) {
        if (order.totalVnd() <= 0) {
            throw new IllegalArgumentException(
                "Tong tien phai lon hon 0");
        }
        return new Receipt(
            order.orderId(), "ACCEPTED", order.totalVnd());
    }
}
~~~

Ở đây, **accept(...)** là phương thức xử lý nghiệp vụ. Nó nhận Order và trả Receipt. Trả Receipt không khiến method trở thành transformer theo nghĩa thiết kế: công việc chính là **áp dụng quy tắc chấp nhận đơn hàng**, còn việc dữ liệu đầu ra đổi kiểu là hệ quả của nghiệp vụ.

Ngược lại, nếu một phương thức chỉ đổi tên trường và định dạng dữ liệu mà không áp dụng hành vi nghiệp vụ, transformer thường thể hiện ý định rõ hơn.

### 5.1. Service activator trả kết quả hay chỉ thực hiện side effect?

| Kiểu phương thức/handler | Ý nghĩa |
| --- | --- |
| Trả về Receipt | Có reply để downstream tiếp tục, khi endpoint/flow được nối phù hợp |
| Trả về Message có headers mới | Có thể điều khiển thêm metadata trên kết quả |
| Trả về void hoặc null | Không có reply nghiệp vụ từ handler đó; phù hợp terminal handler, cần cân nhắc nếu phía trên đang chờ response |
| Ném exception | Flow đồng bộ có thể nhận lỗi trực tiếp; flow bất đồng bộ cần đường xử lý lỗi phù hợp |

Với gateway request–reply, một service activator trả null có thể khiến gateway đang chờ không có kết quả cho đến khi timeout. Không nên giả định kết quả side effect tự động trở thành message reply.

## 6. Ví dụ đầy đủ bằng Java DSL: adapter → transformer → service activator → adapter

Ví dụ tạo một luồng nhỏ:

1. File inbound adapter lấy file CSV mới từ **./data/inbox**.
2. Transformer đọc nội dung file thành String.
3. Transformer chuyển CSV một đơn hàng thành Order.
4. Service activator kiểm tra quy tắc và tạo Receipt.
5. Header enricher gắn tên file biên nhận; transformer định dạng Receipt thành CSV.
6. File outbound adapter ghi biên nhận vào **./data/receipts**.

~~~mermaid
flowchart LR
    F["./data/inbox/order.csv"] --> I["File inbound adapter<br/>poller 5 giây"]
    I --> T1["Transformer<br/>File → String → Order"]
    T1 --> S["Service activator<br/>OrderService.accept"]
    S --> T2["Header enricher + Transformer<br/>Receipt → CSV"]
    T2 --> O["File outbound adapter"]
    O --> R["./data/receipts/receipt-*.csv"]
~~~

### 6.1. DTO và service xử lý nghiệp vụ

Ví dụ dùng Java 17+ cho record. Trong ứng dụng thực tế, đặt các kiểu này trong các file Java phù hợp.

~~~java
public record Order(String orderId, long totalVnd) {}

public record Receipt(
        String orderId, String status, long totalVnd) {}
~~~

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public Receipt accept(Order order) {
        // Bảo đảm tên file được sinh từ một ID an toàn.
        if (order.orderId() == null
                || !order.orderId().matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                "Ma don hang khong hop le");
        }
        if (order.totalVnd() <= 0) {
            throw new IllegalArgumentException(
                "Tong tien phai lon hon 0");
        }
        return new Receipt(
            order.orderId(), "ACCEPTED", order.totalVnd());
    }
}
~~~

Trong ví dụ, service chỉ kiểm tra và tạo kết quả để thấy rõ sự khác biệt với transformer. Một dịch vụ thật có thể gọi repository và yêu cầu transaction, khóa chống xử lý trùng, kiểm soát trạng thái đơn hàng và điều kiện nghiệp vụ đầy đủ hơn.

### 6.2. Cấu hình IntegrationFlow

Với Spring Boot, thường dùng **spring-boot-starter-integration** cùng **spring-integration-file**, theo dependency management của phiên bản Boot đang chạy.

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
import org.springframework.integration.file.FileHeaders;
import org.springframework.integration.file.dsl.Files;
import org.springframework.integration.file.support.FileExistsMode;

@Configuration
@EnableIntegration
public class OrderImportConfiguration {

    @Bean
    public IntegrationFlow orderFileFlow(OrderService orderService) {
        return IntegrationFlow
            // 1. Inbound adapter: lay file tu he thong ngoai.
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))

            // 2. Transformer: File -> String.
            .transform(File.class, file -> {
                try {
                    return java.nio.file.Files.readString(
                        file.toPath(), StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })

            // 3. Transformer: CSV -> domain Order.
            .transform(String.class, csv -> {
                String[] rows = csv.strip().split("\\R");
                if (rows.length != 2
                        || !"orderId,totalVnd".equals(rows[0])) {
                    throw new IllegalArgumentException(
                        "CSV can header va mot dong du lieu");
                }
                String[] values = rows[1].split(",", -1);
                if (values.length != 2) {
                    throw new IllegalArgumentException(
                        "CSV phai co dung hai cot");
                }
                return new Order(
                    values[0].trim(),
                    Long.parseLong(values[1].trim()));
            })

            // 4. Service activator: xu ly domain Order -> Receipt.
            .handle(orderService, "accept")

            // 5. Header enricher + transformer chuan bi output.
            .enrichHeaders(spec -> spec.headerFunction(
                FileHeaders.FILENAME,
                message -> "receipt-"
                    + ((Receipt) message.getPayload()).orderId()
                    + ".csv"))
            .transform(Receipt.class, receipt ->
                "orderId,status,totalVnd\n"
                + receipt.orderId() + ","
                + receipt.status() + ","
                + receipt.totalVnd() + "\n")

            // 6. Outbound adapter: ghi CSV ra he thong ngoai.
            .handle(Files.outboundAdapter(
                    new File("./data/receipts"))
                .autoCreateDirectory(true)
                .fileNameGenerator(message ->
                    (String) message.getHeaders().get(
                        FileHeaders.FILENAME))
                .fileExistsMode(FileExistsMode.FAIL))
            .get();
    }
}
~~~

**Lưu ý về code:** Đây là ví dụ CSV đơn giản với đúng một bản ghi và hai cột. Hàm split theo dấu phẩy không hỗ trợ đầy đủ quy tắc CSV khi dữ liệu chứa dấu phẩy, dấu nháy hoặc xuống dòng; dữ liệu thực cần thư viện CSV parser/encoder và kiểm tra schema. File inbound được poll theo lịch nên việc nhìn thấy tên file chưa chứng minh bên gửi đã ghi hoàn tất. Ứng dụng thật cần quy ước bàn giao file an toàn.

### 6.3. Kết quả mong đợi

Giả sử đặt file **./data/inbox/order-1001.csv** với nội dung:

~~~csv
orderId,totalVnd
O-1001,150000
~~~

Nếu điều kiện ghi cho phép và file đích chưa tồn tại, flow sẽ tạo **./data/receipts/receipt-O-1001.csv**:

~~~csv
orderId,status,totalVnd
O-1001,ACCEPTED,150000
~~~

Diễn giải:

- File inbound adapter nhận **File**, không tự hiểu Order.
- Transformer thứ nhất đổi **File → String**; transformer thứ hai đổi **String → Order**.
- Service activator nhận Order, áp dụng quy tắc kiểm tra rồi tạo Receipt.
- Header enricher bổ sung **FileHeaders.FILENAME** để outbound adapter biết tên biên nhận.
- Transformer cuối đổi Receipt sang **String CSV**; outbound file adapter ghi nội dung ra file.

Mỗi bước có trách nhiệm cụ thể nên có thể kiểm thử việc parse CSV, quy tắc OrderService và cấu hình ghi file một cách riêng biệt.

### 6.4. Lưu ý về header sau transformer

Khi transformer trả về payload mới, Spring Integration thường dựng output message và sao chép những headers được phép theo cơ chế của transformer. Trong ví dụ, **FileHeaders.FILENAME** được gắn trước transformer cuối để outbound adapter đọc từ message nhận được. Nếu dùng transformer tùy chỉnh tự tạo Message hoặc can thiệp headers, hãy kiểm tra việc bảo toàn filename/correlation bằng kiểm thử tích hợp.

Không nên dựa vào tên file đầu vào làm khóa nghiệp vụ duy nhất khi đối tác có thể gửi lại cùng đơn hàng bằng tên khác. Khóa chống trùng nên lấy từ dữ liệu nghiệp vụ ổn định, ví dụ partnerId và orderId.

## 7. Chọn adapter, transformer hay service activator trong tình huống thực tế

| Tình huống | Thành phần thường phù hợp | Vì sao? |
| --- | --- | --- |
| Lấy tệp từ SFTP theo lịch | SFTP inbound adapter + poller | Quản lý giao thức nhận file và lịch lấy |
| Đổi File thành nội dung UTF-8 | Transformer | Đổi biểu diễn payload để bước tiếp sử dụng |
| Parse JSON thành Order | Transformer | Ánh xạ hợp đồng dữ liệu |
| Kiểm tra tồn kho và ghi nhận đơn hàng | Service activator | Gọi nghiệp vụ và có thể thực hiện transaction |
| Publish OrderCreated lên Kafka | Kafka outbound adapter | Giao tiếp producer/broker theo cấu hình |
| Chuyển OrderCreated thành JSON | Transformer hoặc converter tại biên | Chuyển định dạng theo hợp đồng đích |
| Đọc thông điệp JMS vào flow | JMS inbound adapter | Tiếp nhận message từ nguồn ngoài |
| Gọi một REST API để lấy response dùng tiếp | Outbound HTTP gateway | Hợp đồng request–reply, khác adapter một chiều |
| Ghi một bản cập nhật ra database | JDBC outbound adapter hoặc service activator gọi repository | Chọn theo nhu cầu trừu tượng hóa, transaction và kiểm soát nghiệp vụ |
| Từ Java gọi flow và lấy kết quả | Messaging gateway | Cầu nối phương thức Java với messaging flow |

Một luồng thực tế có thể gồm nhiều transformer và service activator sau **một** inbound adapter, hoặc một transformer cấp dữ liệu cho nhiều outbound adapter. Số lượng endpoint phụ thuộc kiến trúc và nhu cầu chứ không nhất thiết là một cặp adapter + transformer + service activator cố định.

### 7.1. Khi service activator gọi HTTP hoặc Kafka trực tiếp có sai không?

Không nhất thiết. Service activator là một điểm gọi mã Java nên có thể gọi HTTP client, repository hoặc producer. Tuy nhiên cần cân nhắc:

- Có adapter/gateway Spring Integration phù hợp, giúp cấu hình chuyển giao message, routing, timeout hoặc error flow rõ hơn không?
- Đoạn xử lý đang thể hiện **quy tắc nghiệp vụ** hay chỉ đang gói API I/O của hệ thống ngoài?
- Cần xử lý kết quả **request–reply** hay chỉ gửi một chiều?
- Có thể kiểm thử nghiệp vụ mà không cần kết nối thực đến hệ thống ngoài không?

Nếu endpoint chỉ gửi message lên Kafka, outbound adapter thể hiện ý định tốt hơn so với đặt toàn bộ producer code trong một service activator. Nếu logic ghi DB là một bước nghiệp vụ với transaction và bất biến phức tạp, service activator gọi application service/repository có thể rất phù hợp.

## 8. Khi ba thành phần phối hợp, lỗi thuộc về ai?

Một flow có thể thất bại ở các ranh giới khác nhau:

~~~mermaid
flowchart TD
    A["Inbound adapter"] --> B{"Nhận dữ liệu thành công?"}
    B -- "Không" --> E1["Lỗi kết nối / đọc nguồn"]
    B -- "Có" --> C["Transformer"]
    C --> D{"Dữ liệu đúng định dạng?"}
    D -- "Không" --> E2["Lỗi parse / schema"]
    D -- "Có" --> S["Service activator"]
    S --> V{"Nghiệp vụ hợp lệ?"}
    V -- "Không" --> E3["Lỗi nghiệp vụ"]
    V -- "Có" --> O["Outbound adapter"]
    O --> Z{"Ghi/gửi thành công?"}
    Z -- "Không" --> E4["Lỗi I/O / giao thức đích"]
    Z -- "Có" --> DONE["Hoàn tất theo hợp đồng hiện tại"]
~~~

| Vị trí lỗi | Ví dụ | Phản ứng cần thiết |
| --- | --- | --- |
| Inbound adapter | SFTP timeout, file không đọc được, JMS connection bị đóng | Reconnect, retry có giới hạn, ghi lại trạng thái nguồn |
| Transformer | CSV thiếu cột, JSON sai schema, số tiền không parse được | Phân loại lỗi dữ liệu, cách ly payload, sửa hợp đồng |
| Service activator | Hết tồn kho, vi phạm quy tắc, database transaction lỗi | Trả kết quả nghiệp vụ hoặc rollback/đánh dấu lỗi phù hợp |
| Outbound adapter | HTTP 5xx, broker không nhận, không có quyền ghi file | Retry có backoff, đối soát, lưu trạng thái chưa xuất |

### 8.1. Exception và kiểu MessageChannel

Với **DirectChannel**, downstream thường xử lý trên cùng luồng gửi; exception từ transformer, service activator hoặc outbound adapter có thể truyền ngược về endpoint trước đó.

Với **ExecutorChannel** hoặc **QueueChannel**, lỗi có thể xảy ra sau khi nguồn đã gửi message vào channel. Khi đó cần cấu hình **errorChannel**, advice/retry, callback hoặc cơ chế xử lý lỗi thích hợp cho endpoint. Không giả định errorChannel mặc định lưu lại mọi message lỗi hoặc tự bảo đảm retry.

**QueueChannel** mặc định không đồng nghĩa với hàng đợi bền vững trên đĩa. Nếu cần khôi phục message sau khi tiến trình dừng, cần cơ chế lưu bền thích hợp hoặc kiến trúc như transactional outbox.

### 8.2. Retry có thể chạy lại cả chuỗi

Với một flow File → Transformer → Service activator → Outbound adapter, nếu service đã ghi database thành công nhưng adapter ghi file thất bại, việc retry toàn bộ flow có thể chạy lại nghiệp vụ. Đây là lý do phải xác định:

- Bước nào có thể chạy lại an toàn?
- Bước nào đã sinh side effect trước khi có lỗi?
- Có khóa **idempotency** ổn định như orderId/eventId không?
- Thời điểm xác nhận/commit của nguồn liên quan thế nào đến thời điểm ghi dữ liệu ở đích?
- Có cần lưu trạng thái từng bước hoặc dùng outbox để phục hồi phần chưa hoàn tất không?

**Transformer thuần ánh xạ** thường dễ retry hơn service activator hoặc adapter tạo side effect. Dù vậy, bản thân nguồn và đích vẫn có thể giao lại hoặc thực hiện trùng theo cơ chế của chúng.

### 8.3. Transaction không tự bao phủ mọi adapter

Giao dịch database của OrderService không tự tạo một transaction chung với file system, HTTP, SFTP hay Kafka. Muốn bảo đảm nhất quán giữa cập nhật nghiệp vụ và gửi thông điệp, thường cần thiết kế outbox/inbox, idempotent consumer, sự kiện bù trừ hoặc transaction được hạ tầng hỗ trợ đúng phạm vi.

Không thể kết luận **exactly-once end-to-end** chỉ vì luồng dùng Spring Integration, một loại channel hay một adapter cụ thể.

## 9. Poller, gateway và vòng đời kết nối thuộc trách nhiệm nào?

**Poller** là cơ chế điều phối việc chủ động lấy dữ liệu từ một MessageSource hoặc PollableChannel. Poller không đồng nghĩa adapter, transformer hay service activator, dù nó có thể kích hoạt endpoint tương ứng:

- File inbound adapter thường có poller để quét file.
- Một outbound adapter tiêu thụ **QueueChannel** có thể cần polling consumer để lấy message khỏi hàng đợi nội bộ.
- Một message-driven JMS/AMQP/Kafka adapter thường được kích hoạt bởi listener container/client giao thức.

**Gateway** phục vụ hợp đồng request–reply. Khi service activator tạo kết quả để một outbound HTTP gateway gửi yêu cầu ra ngoài hoặc để một inbound HTTP gateway trả response, điều cần xem xét là channel trả lời, timeout, error flow và correlation giữa request/reply.

**Vòng đời kết nối** chủ yếu thuộc tầng giao tiếp: SFTP session, JDBC pool, Kafka producer/consumer, JMS/AMQP connection factory và HTTP client. Service activator sử dụng repository cũng có dependency vận hành của riêng nó; transformer thuần chuyển đổi dữ liệu thường không cần quản lý phiên kết nối bên ngoài.

## 10. Kiểm thử theo từng trách nhiệm

Trong một flow, kiểm thử tách rời giúp xác định lỗi nhanh hơn:

| Thành phần | Kiểm thử hữu ích |
| --- | --- |
| Transformer File/CSV → Order | Dữ liệu đúng, thiếu header, sai kiểu số, sai charset, nhiều dòng |
| Service activator OrderService | Tổng tiền hợp lệ/không hợp lệ, ID không an toàn, quy tắc nghiệp vụ, trường hợp trùng đơn |
| File inbound adapter | Bộ lọc tên file, dữ liệu được chọn theo poller, file đang ghi dở, restart |
| File outbound adapter | Tên file, quyền ghi, thư mục thiếu, file đã tồn tại, nội dung xuất |
| Cả IntegrationFlow | Header được giữ đúng, lỗi được phát hiện đúng nơi, dữ liệu ra đúng hợp đồng |

### 10.1. Thử nghiệm thủ công với ví dụ

1. Khởi động ứng dụng có cấu hình OrderImportConfiguration và OrderService.
2. Đặt một file **order-1001.csv** có hai dòng ví dụ vào **./data/inbox**.
3. Sau khi poller nhận file, kiểm tra **receipt-O-1001.csv** được tạo ở **./data/receipts**.
4. Thay tổng tiền thành số âm để quan sát exception nghiệp vụ từ service activator.
5. Thay header thành tên không khớp để thấy lỗi nằm ở transformer CSV.
6. Tạo sẵn file biên nhận trùng tên để quan sát lỗi outbound với FileExistsMode.FAIL.

Không nên dùng riêng việc xuất hiện file làm bằng chứng toàn bộ nghiệp vụ có tính idempotency. Đặc biệt trong ví dụ, FileExistsMode.FAIL chỉ ngăn ghi đè cùng tên; chưa thay thế cơ chế chống xử lý lại đơn hàng khi nguồn được nhận lại.

### 10.2. Bộ câu hỏi chọn thành phần

Khi phân tích một bước mới trong flow, hãy tự hỏi:

1. **Bước này đọc/ghi hệ thống ngoài?** Tìm adapter hoặc gateway có hợp đồng giao tiếp phù hợp.
2. **Bước này chỉ đổi kiểu hoặc cấu trúc dữ liệu?** Ưu tiên transformer.
3. **Bước này áp dụng quy tắc hoặc gọi dịch vụ nghiệp vụ?** Ưu tiên service activator.
4. **Bước tiếp theo cần response của hệ thống ngoài?** Xem xét gateway thay adapter một chiều.
5. **Bước này có side effect và có thể retry?** Thiết kế idempotency, rollback hoặc phục hồi trạng thái rõ ràng.

## 11. Những nhầm lẫn thường gặp

**“Transformer và service activator đều là handler nên giống nhau.”** Cả hai nhận message qua endpoint, nhưng transformer diễn tả phép **ánh xạ dữ liệu**, còn service activator diễn tả **hành động/dịch vụ**. Cả hai có thể tạo output; khác biệt nằm ở ý định và trách nhiệm.

**“Outbound adapter sẽ trả giá trị nếu hệ thống đích thành công.”** Một adapter một chiều có thể nhận xác nhận kỹ thuật hoặc ném exception, nhưng không tạo message reply nghiệp vụ như gateway request–reply.

**“Inbound adapter phải trả DTO domain.”** Không bắt buộc. Nguồn file có thể phát File, broker có thể phát String/byte/record; transformer chuẩn hóa dữ liệu theo hợp đồng nội bộ.

**“Service activator không được truy cập database.”** Service activator là điểm kích hoạt dịch vụ ứng dụng, có thể gọi repository và chịu transaction nghiệp vụ. Cần phân biệt đây là xử lý nghiệp vụ hay chỉ là thao tác giao thức mà adapter chuyên dụng đã đáp ứng.

**“Transformer là nơi tốt nhất để vừa parse, vừa gọi API, vừa lưu.”** Gộp quá nhiều side effect khiến retry, kiểm thử và quan sát lỗi khó hơn. Hãy tách phép biến đổi và hành động nghiệp vụ khi cần.

**“Một flow luôn cần cả ba thành phần.”** Không. Flow có thể chỉ nhận từ adapter và ghi ra adapter, hoặc gồm transformer và service activator nội bộ không có adapter tại endpoint đó. Sơ đồ là mẫu tổ chức, không phải quy tắc bắt buộc.

## 12. Câu hỏi tự kiểm tra

1. Trong luồng nhận SFTP rồi parse JSON thành Order, tại sao parse JSON thường thuộc transformer mà kết nối SFTP thuộc adapter?
2. Khi service activator trả về Receipt, vì sao nó vẫn là service activator thay vì tự động được coi là transformer?
3. Outbound Kafka adapter khác một service activator tự gọi KafkaProducer ở khía cạnh trách nhiệm và khả năng cấu hình như thế nào?
4. Nếu transformer làm mất header đặt tên file, hậu quả nào có thể xuất hiện ở file outbound adapter?
5. Tại sao retry toàn flow có thể khiến service activator tạo tác động nghiệp vụ trùng, ngay cả khi transformer hoàn toàn thuần dữ liệu?
6. Khi handler cần gọi REST API và dùng response body để quyết định nghiệp vụ, nên chọn loại endpoint nào? Vì sao?
7. Trong ví dụ CSV, lỗi thiếu cột và lỗi tổng tiền không hợp lệ nên xuất hiện ở những bước nào?
8. Khi thay file inbound bằng Kafka inbound, phần nào của flow có khả năng được giữ lại và phần nào phải đánh giá lại?

## Tổng kết

Trong Spring Integration, **adapter kết nối hệ thống ngoài**, **transformer chuẩn hóa và chuyển đổi message**, còn **service activator kích hoạt xử lý nghiệp vụ**. Chọn đúng vai trò làm rõ hợp đồng payload/headers, vị trí phát sinh lỗi và mức bảo đảm giao nhận. Một luồng thực tế thường phối hợp nhiều endpoint, MessageChannel, poller hoặc gateway để xử lý file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Khi triển khai, cần kiểm soát tác động phụ, retry, idempotency, transaction và vòng đời kết nối ở đúng ranh giới thay vì dồn tất cả vào một handler.
