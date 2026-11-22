# Phân biệt gọi hàm trực tiếp, HTTP và giao tiếp bằng thông điệp

> Mục tiêu: nhận biết ba cách các thành phần phần mềm trao đổi với nhau, hiểu sự khác nhau về luồng xử lý, mức độ phụ thuộc, xử lý lỗi và biết khi nào nên chọn từng cách trong ứng dụng Spring.

## 1. Bối cảnh: ba cách giao tiếp giải quyết ba nhu cầu khác nhau

Trong một hệ thống, một thành phần thường cần yêu cầu thành phần khác thực hiện công việc hoặc thông báo rằng một sự kiện đã xảy ra. Có ba cách phổ biến:

- **Gọi hàm trực tiếp (direct method call):** mã đang chạy gọi một phương thức của đối tượng khác trong cùng tiến trình.
- **HTTP:** một thành phần gửi request đến endpoint của thành phần khác và thường nhận response qua mạng.
- **Giao tiếp bằng thông điệp (messaging):** một thành phần gửi message đến channel hoặc broker; một hay nhiều consumer nhận và xử lý message.

HTTP cũng có cấu trúc message ở cấp giao thức. Tuy nhiên, trong ngữ cảnh thiết kế hệ thống và Spring Messaging, từ “messaging” thường chỉ mô hình producer–consumer qua message channel hoặc message broker, có thể xử lý bất đồng bộ và tách thời điểm gửi khỏi thời điểm xử lý.

Không có cách nào luôn tốt hơn hai cách còn lại. Lựa chọn phụ thuộc vào việc bên gửi có cần kết quả ngay hay không, các thành phần có nằm trong cùng tiến trình không, mức độ độc lập cần có và cách hệ thống phải phục hồi khi một thành phần gặp lỗi.

## 2. Gọi hàm trực tiếp

### Cách hoạt động

Một đối tượng giữ tham chiếu đến đối tượng khác và gọi phương thức của đối tượng đó. Trong ứng dụng Spring thông thường, Spring tạo các bean và inject dependency qua constructor. Khi một bean gọi phương thức của bean khác trong cùng ứng dụng, đó vẫn là lời gọi Java trong cùng JVM.

Ví dụ dưới đây là các đoạn mã minh họa, giả sử `OrderService` và `InventoryService` là hai bean trong cùng ứng dụng:

```java
@Service
class InventoryService {
    void reserve(String sku, int quantity) {
        // Kiểm tra và giữ số lượng hàng trong kho.
    }
}

@Service
class OrderService {
    private final InventoryService inventoryService;

    OrderService(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    void placeOrder(String sku, int quantity) {
        inventoryService.reserve(sku, quantity);
    }
}
```

Luồng thực thi thường diễn ra như sau:

1. `OrderService` gọi `placeOrder`.
2. `placeOrder` gọi `inventoryService.reserve`.
3. Phương thức `reserve` chạy ngay trên luồng gọi, trừ khi bên trong nó chủ động chuyển công việc sang cơ chế bất đồng bộ.
4. Khi `reserve` trả về, luồng gọi tiếp tục; exception chưa được xử lý có thể truyền ngược lên call stack.

### Đặc điểm

- **Độ trễ thấp:** không cần tạo HTTP request, truyền dữ liệu qua mạng hoặc đi qua broker.
- **Phản hồi trực tiếp:** bên gọi nhận giá trị trả về hoặc exception trong cùng luồng điều khiển.
- **Phụ thuộc lúc chạy:** bên gọi cần có đối tượng đích và phương thức tương ứng; hai thành phần thường phải cùng tiến trình.
- **Khó tách triển khai:** nếu cần chuyển `InventoryService` sang một tiến trình khác, lời gọi Java trực tiếp không tự biến thành lời gọi từ xa. Phải thay bằng một giao thức hoặc adapter khác.
- **Chia sẻ ngữ cảnh:** hai bean có thể cùng dùng transaction, security context hoặc dữ liệu trong bộ nhớ của ứng dụng, tùy cấu hình.

Spring AOP có thể đặt proxy quanh bean, chẳng hạn để áp dụng `@Transactional`, logging hoặc security. Proxy đó vẫn không đồng nghĩa với giao tiếp HTTP hay messaging; nếu lời gọi được xử lý trong cùng JVM thì đây vẫn là lời gọi cục bộ.

### Khi nên dùng

Dùng lời gọi trực tiếp khi hai thành phần thuộc cùng ứng dụng, cần kết quả ngay và có thể chấp nhận phụ thuộc triển khai giữa chúng. Đây thường là lựa chọn phù hợp cho các service nội bộ trong một modular monolith hoặc cho các bước nghiệp vụ cần phối hợp đồng bộ.

## 3. Giao tiếp qua HTTP

### Cách hoạt động

HTTP cho phép các tiến trình giao tiếp qua mạng bằng request và response. Client gửi request đến một URL; request thường gồm method, path, headers và có thể có body. Server xử lý rồi trả response gồm status code, headers và có thể có body.

Ví dụ, một ứng dụng đặt hàng gọi dịch vụ kho qua endpoint `POST /inventory/reservations`. Dịch vụ kho có thể trả `200 OK` hoặc `204 No Content` khi hoàn tất, `400 Bad Request` khi dữ liệu không hợp lệ, hoặc `503 Service Unavailable` khi tạm thời không thể phục vụ.

Trong Spring MVC, endpoint có thể được khai báo bằng controller:

```java
@RestController
@RequestMapping("/inventory")
class InventoryController {
    private final InventoryService inventoryService;

    InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @PostMapping("/reservations")
    ResponseEntity<Void> reserve(@RequestBody ReserveRequest request) {
        inventoryService.reserve(request.sku(), request.quantity());
        return ResponseEntity.noContent().build();
    }
}

record ReserveRequest(String sku, int quantity) {}
```

Một client dùng `RestClient` của Spring Framework 6.1 trở lên có thể gọi endpoint đó như sau:

```java
RestClient client = RestClient.builder()
        .baseUrl("http://inventory-service")
        .build();

client.post()
        .uri("/reservations")
        .body(new ReserveRequest("BOOK-01", 2))
        .retrieve()
        .toBodilessEntity();
```

Đây là các đoạn mã minh họa, không phải một ứng dụng độc lập có thể chạy ngay. Ứng dụng thực tế cần cấu hình Spring MVC, client, địa chỉ dịch vụ, DTO và xử lý lỗi phù hợp. Với phiên bản Spring cũ hơn 6.1, dự án có thể dùng `RestTemplate` hoặc `WebClient` tùy nhu cầu và phiên bản.

### Đặc điểm

- **Ranh giới tiến trình rõ ràng:** client và server có thể chạy ở hai máy hoặc hai container khác nhau.
- **Hợp đồng được biểu diễn qua HTTP:** URL, method, status code, headers và schema của body tạo thành API mà hai bên cần thống nhất.
- **Request–response thuận tiện:** phù hợp khi client cần truy vấn hoặc cần biết kết quả xử lý ngay trong một tương tác.
- **Phụ thuộc thời gian:** trong lời gọi đồng bộ thông thường, client phải chờ server phản hồi hoặc timeout. Server chậm hay mất kết nối có thể ảnh hưởng trực tiếp đến request của client.
- **Cần xử lý lỗi mạng:** timeout không chứng minh rằng server chưa thực hiện thao tác. Server có thể đã xử lý xong nhưng response bị thất lạc; retry một thao tác ghi có thể tạo tác dụng phụ trùng lặp.
- **Có thể dùng bất đồng bộ:** HTTP client có API non-blocking hoặc asynchronous, và server có thể trả `202 Accepted` để báo đã tiếp nhận yêu cầu. Điều đó không tự tạo ra message broker hay bảo đảm việc xử lý nền.

HTTP thường được dùng để xây dựng REST API, tích hợp hệ thống, cung cấp API cho web/mobile client và gọi dịch vụ cần phản hồi trực tiếp. Giao tiếp HTTP không tự cung cấp hàng đợi bền vững cho công việc cần xử lý sau khi client ngắt kết nối.

### Khi nên dùng

Dùng HTTP khi một thành phần cần gọi chức năng hoặc truy vấn dữ liệu của thành phần khác qua ranh giới tiến trình, và luồng nghiệp vụ cần nhận response để tiếp tục. Đây là lựa chọn tự nhiên cho API công khai, API nội bộ giữa dịch vụ và các thao tác cần phản hồi trực tiếp.

## 4. Giao tiếp bằng thông điệp (messaging)

### Cách hoạt động

Trong mô hình messaging, producer tạo message và gửi đến một destination hoặc message channel. Broker hoặc hạ tầng messaging tiếp nhận message; consumer đăng ký nhận và xử lý message. Producer và consumer không nhất thiết phải chạy cùng lúc.

Luồng tổng quát:

1. Producer tạo message có payload và metadata cần thiết.
2. Producer gửi message đến queue, topic hoặc channel.
3. Hạ tầng messaging tiếp nhận và định tuyến message theo cấu hình.
4. Consumer nhận message và thực hiện công việc.
5. Consumer xác nhận xử lý theo cơ chế acknowledgement của nền tảng. Nếu xử lý thất bại, message có thể được gửi lại hoặc chuyển đến dead-letter queue tùy cấu hình.

Message thường biểu diễn một trong hai ý nghĩa:

- **Command:** yêu cầu một consumer thực hiện hành động, ví dụ `ReserveInventory`. Command thường hướng đến một bên chịu trách nhiệm xử lý.
- **Event:** thông báo một việc đã xảy ra, ví dụ `OrderCreated`. Event mô tả sự kiện trong quá khứ; nhiều consumer độc lập có thể cùng quan tâm.

Queue thường dùng cho mô hình một message được một consumer trong nhóm xử lý; nhiều consumer có thể chia tải. Topic hoặc mô hình publish–subscribe cho phép nhiều subscriber nhận bản sao sự kiện theo cơ chế của nền tảng. Cách phân phối cụ thể phụ thuộc broker và cấu hình.

### Ví dụ với Spring JMS

Spring JMS cung cấp `JmsTemplate` để gửi message và `@JmsListener` để nhận message từ JMS destination. Ví dụ sau giả sử ứng dụng đã cấu hình connection factory, listener container và một `MessageConverter` phù hợp với kiểu `OrderCreated` (chẳng hạn converter JSON):

```java
@Configuration
@EnableJms
class JmsConfiguration {
}

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.created", event);
    }
}

@Component
class BillingListener {
    @JmsListener(destination = "orders.created")
    public void handle(OrderCreated event) {
        // Kiểm tra event và thực hiện quy trình tính tiền.
    }
}
```

Producer gửi `OrderCreated` đến destination `orders.created`. Consumer xử lý message khi message được chuyển đến listener. Phương thức gửi có thể chờ broker xác nhận việc gửi theo cấu hình, nhưng producer không cần chờ toàn bộ nghiệp vụ tính tiền hoàn tất.

Spring cũng có các abstraction messaging như `Message<T>`, `MessageChannel` và `MessageHandler` trong package `org.springframework.messaging`. Chúng biểu diễn payload, headers, kênh gửi và thành phần xử lý message; Spring Integration và các tích hợp khác có thể dùng những abstraction này để xây dựng luồng xử lý. JMS là một tích hợp messaging cụ thể, không phải tên gọi chung cho mọi broker.

### Đặc điểm

- **Tách thời điểm gửi và xử lý:** producer có thể hoàn tất bước gửi sau khi hạ tầng tiếp nhận message, trong khi consumer xử lý sau đó.
- **Giảm phụ thuộc trực tiếp:** producer thường không cần biết instance consumer nào sẽ xử lý message hoặc consumer được triển khai ở đâu.
- **Hấp thụ tải đột biến:** queue có thể lưu message để consumer xử lý theo năng lực hiện có, miễn là dung lượng và chính sách broker đáp ứng tải.
- **Hỗ trợ nhiều consumer:** một event có thể kích hoạt nhiều quy trình độc lập, tùy kiểu destination và cấu hình subscription.
- **Phản hồi nghiệp vụ không tức thời:** producer thường không nhận ngay kết quả cuối cùng của consumer. Nếu cần kết quả, hệ thống phải thiết kế request–reply, callback hoặc một API tra cứu trạng thái.
- **Cần quản lý vòng đời message:** schema, version, thời hạn lưu, retry, dead-letter, thứ tự, acknowledgement và xử lý message trùng lặp đều cần được thiết kế.

Messaging không mặc nhiên bảo đảm “exactly once”. Nền tảng có thể cung cấp các mức giao nhận khác nhau như at-most-once hoặc at-least-once; một số nền tảng có bảo đảm mạnh hơn trong phạm vi và điều kiện nhất định. Ứng dụng vẫn nên thiết kế consumer idempotent để xử lý an toàn khi message được giao lại.

### Khi nên dùng

Dùng messaging cho công việc nền, xử lý theo sự kiện, tích hợp nhiều consumer, hấp thụ tải theo hàng đợi hoặc khi producer và consumer cần độc lập về thời gian triển khai và vận hành. Đây là lựa chọn hữu ích khi việc xử lý có thể hoàn tất sau và bên gửi không cần kết quả cuối cùng ngay lập tức.

## 5. So sánh trực tiếp

| Tiêu chí | Gọi hàm trực tiếp | HTTP | Messaging |
|---|---|---|---|
| Phạm vi thường gặp | Cùng tiến trình/JVM | Giữa các tiến trình qua mạng | Giữa producer và consumer qua channel/broker |
| Cách trao đổi | Gọi phương thức, tham số và giá trị trả về | Request và response | Message có payload và headers |
| Thời điểm phản hồi | Thường ngay trong call stack | Thường chờ response; có thể dùng client bất đồng bộ | Thường chỉ cần xác nhận gửi/tiếp nhận; consumer xử lý sau |
| Phụ thuộc vào bên nhận | Cần đối tượng hoặc proxy đích | Cần endpoint và hợp đồng API | Cần hợp đồng message và destination; không cần biết instance consumer |
| Kết quả nghiệp vụ | Trả về hoặc exception trực tiếp | Status/body hoặc lỗi giao tiếp | Thường theo dõi qua event, trạng thái hoặc request–reply riêng |
| Xử lý khi bên nhận tạm ngừng | Lời gọi thường thất bại nếu đối tượng không sẵn sàng | Request có thể timeout hoặc lỗi kết nối | Broker có thể giữ message để xử lý sau, tùy cấu hình và độ bền |
| Trường hợp phù hợp | Logic nội bộ, cần kết quả ngay | API và tương tác đồng bộ qua mạng | Event, tác vụ nền, hàng đợi và nhiều consumer |

Bảng trên mô tả cách dùng phổ biến. Một hệ thống có thể dùng HTTP bất đồng bộ ở client, messaging có request–reply, hoặc gọi phương thức qua proxy. Hãy phân biệt bản chất giao thức và cơ chế vận hành thực tế thay vì chỉ nhìn tên API.

## 6. Những khác biệt quan trọng khi thiết kế

### 6.1. Mức độ phụ thuộc và khả năng triển khai độc lập

Gọi hàm trực tiếp tạo phụ thuộc rõ nhất vào cấu trúc mã và vòng đời đối tượng. HTTP tách hai bên thành tiến trình riêng nhưng vẫn có phụ thuộc thời gian: client cần server sẵn sàng để nhận request và trả response. Messaging giảm phụ thuộc thời gian vì broker có thể lưu message trong lúc consumer chưa chạy; đổi lại, hai bên phải thống nhất schema và ý nghĩa của message.

Tách tiến trình không đồng nghĩa tách hoàn toàn hợp đồng. Thay đổi tên field, kiểu dữ liệu hoặc ý nghĩa của message có thể làm consumer cũ lỗi. API HTTP và message event đều cần quản lý tương thích ngược, versioning và quy trình triển khai.

### 6.2. Timeout, retry và thao tác trùng lặp

Với HTTP, nếu client timeout thì không thể kết luận server chưa làm gì. Với messaging, broker có thể giao lại message khi không nhận được acknowledgement. Cả hai tình huống đều có thể khiến một thao tác được thực hiện nhiều lần.

Để giảm rủi ro:

- Dùng idempotency key hoặc business identifier ổn định cho các thao tác ghi quan trọng.
- Lưu dấu message/event đã xử lý trong cùng ranh giới transaction phù hợp, để lần giao lại không lặp tác dụng phụ.
- Chỉ retry lỗi có khả năng phục hồi; dùng giới hạn số lần, backoff và jitter để tránh tạo thêm tải khi hệ thống đang lỗi.
- Với message không thể xử lý sau các lần retry, đưa vào dead-letter queue và cung cấp quy trình kiểm tra, sửa dữ liệu hoặc phát lại có kiểm soát.

### 6.3. Thứ tự và tính nhất quán

Không nên mặc định mọi message đều được xử lý đúng thứ tự toàn cục. Thứ tự có thể chỉ được bảo đảm trong một queue, session, partition hoặc nhóm khóa cụ thể. Nếu thứ tự theo đơn hàng là quan trọng, hãy dùng khóa định tuyến phù hợp và thiết kế consumer để phát hiện trạng thái đến sai thứ tự.

Một transaction cơ sở dữ liệu không tự bao trùm một HTTP call hoặc một lần publish đến broker. Nếu ứng dụng cập nhật database rồi publish event, lỗi xảy ra giữa hai thao tác có thể làm dữ liệu và event lệch nhau. Với yêu cầu nhất quán cao, cân nhắc transactional outbox: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database, sau đó một tiến trình riêng phát event từ outbox. Consumer có thể dùng inbox hoặc bảng deduplication để chống xử lý trùng.

### 6.4. Quan sát và truy vết

Khi lời gọi đi qua nhiều tiến trình, log riêng lẻ không đủ để tái dựng toàn bộ luồng. Nên truyền correlation ID hoặc trace context qua HTTP headers và message headers; ghi nhận message ID, event type, thời điểm gửi/nhận, số lần retry và kết quả xử lý. Tránh đưa dữ liệu bí mật hoặc thông tin cá nhân không cần thiết vào log.

## 7. Kết hợp ba cách trong cùng một hệ thống

Ba cách giao tiếp có thể bổ sung cho nhau. Ví dụ khi khách hàng đặt hàng:

1. `OrderController` nhận HTTP request từ ứng dụng khách và trả response cho client.
2. `OrderService` gọi trực tiếp các thành phần nội bộ trong cùng ứng dụng để kiểm tra dữ liệu và ghi đơn hàng.
3. Sau khi đơn hàng được ghi thành công, hệ thống phát event `OrderCreated` để các consumer như thanh toán, email và phân tích xử lý độc lập.
4. Ứng dụng khách có thể gọi HTTP để tra cứu trạng thái đơn hàng sau đó.

Ở đây HTTP phù hợp với ranh giới API và truy vấn trạng thái; lời gọi trực tiếp phù hợp với logic trong cùng tiến trình; messaging phù hợp để thông báo sự kiện và khởi chạy các quy trình có thể hoàn tất sau.

Không nên chuyển mọi lời gọi nội bộ thành message chỉ vì muốn dùng broker. Nếu caller bắt buộc phải biết kết quả ngay để quyết định bước tiếp theo, một lời gọi trực tiếp hoặc HTTP thường dễ hiểu hơn. Ngược lại, không nên tạo chuỗi HTTP đồng bộ dài cho những tác vụ nền độc lập vì lỗi hoặc độ trễ của một dịch vụ có thể lan truyền đến toàn bộ chuỗi.

## 8. Lỗi thiết kế thường gặp

- **Coi lời gọi Java là giao tiếp từ xa:** inject một bean khác trong cùng JVM không tạo ra khả năng chịu lỗi mạng hay tách triển khai.
- **Coi HTTP timeout là bằng chứng thao tác thất bại:** server có thể đã xử lý request; retry thao tác ghi cần idempotency.
- **Dùng `202 Accepted` như bằng chứng nghiệp vụ đã hoàn tất:** status này chỉ thể hiện request đã được chấp nhận để xử lý, không khẳng định kết quả cuối cùng.
- **Giả định gửi message đồng nghĩa consumer đã xử lý xong:** gửi thành công và xử lý thành công là hai mốc khác nhau.
- **Giả định broker không bao giờ giao message trùng:** consumer cần chịu được retry và redelivery.
- **Không quản lý schema event:** thay đổi payload có thể làm hỏng consumer đang chạy phiên bản cũ.
- **Không có dead-letter hoặc quy trình vận hành:** message lỗi có thể bị retry vô hạn hoặc bị bỏ quên.
- **Dùng messaging cho truy vấn cần câu trả lời tức thời:** request–reply qua broker có thể làm được nhưng thêm độ phức tạp; HTTP thường phù hợp hơn cho truy vấn đồng bộ.
- **Không đo độ trễ và độ dài hàng đợi:** queue tăng liên tục là dấu hiệu consumer không theo kịp tốc độ gửi hoặc đang gặp lỗi.

## 9. Quy trình chọn cách giao tiếp

Có thể dùng các câu hỏi sau để quyết định:

1. Hai thành phần có nằm trong cùng tiến trình và cùng vòng đời triển khai không? Nếu có, và cần kết quả ngay, hãy cân nhắc gọi hàm trực tiếp.
2. Hai bên chạy ở các tiến trình riêng và caller cần response để tiếp tục không? Hãy cân nhắc HTTP.
3. Công việc có thể xử lý sau, cần đệm tải, phát sự kiện cho nhiều consumer hoặc cần producer hoạt động độc lập với consumer không? Hãy cân nhắc messaging.
4. Nếu cần retry, hãy xác định thao tác có idempotent không, timeout/acknowledgement có ý nghĩa gì và xử lý message lỗi ở đâu.
5. Nếu cần nhất quán giữa database và message, hãy xác định transaction boundary và cân nhắc outbox/inbox.
6. Nếu nhiều phiên bản producer và consumer chạy đồng thời, hãy xác định quy tắc tương thích schema và cách triển khai thay đổi.

## 10. Kết luận

- **Gọi hàm trực tiếp** là lựa chọn đơn giản và nhanh cho các thành phần nội bộ trong cùng tiến trình, khi cần kết quả trong luồng gọi.
- **HTTP** là lựa chọn phổ biến để các tiến trình trao đổi qua API request–response, đặc biệt khi caller cần phản hồi trực tiếp.
- **Messaging** phù hợp với event và tác vụ nền, khi muốn tách thời điểm gửi khỏi thời điểm xử lý, đệm tải hoặc cho nhiều consumer phản ứng độc lập.

Khi thiết kế hệ thống Spring, hãy bắt đầu từ yêu cầu về kết quả, độ trễ, ranh giới triển khai, khả năng phục hồi và tính nhất quán. Chọn cơ chế giao tiếp đáp ứng các yêu cầu đó, rồi thiết kế hợp đồng, timeout, retry, idempotency và quan sát vận hành tương ứng.