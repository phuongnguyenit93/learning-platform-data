# Router theo biểu thức

## 1. Bài toán: quyết định đường đi từ dữ liệu của message

Trong một hệ thống nhận đơn hàng, đơn nội địa đi tới nhóm xử lý tại Việt Nam, đơn quốc tế đi tới nhóm kiểm tra hải quan, còn đơn có mức rủi ro cao phải được kiểm tra thủ công. Nếu tất cả handler đều tự viết `if/else` để chọn bước kế tiếp, logic định tuyến sẽ phân tán ở nhiều nơi, khó kiểm thử và khó theo dõi.

**Message Router** là một mẫu trong **Enterprise Integration Patterns (EIP)**: nhận thông điệp từ một channel, đánh giá quy tắc và chuyển thông điệp đến channel đích phù hợp. Trong Spring Integration, **router theo biểu thức** dùng **Spring Expression Language (SpEL)** để tính *routing key* hoặc đích từ payload/headers. Nhờ đó, quy tắc lựa chọn nhánh được mô tả tập trung tại endpoint Router, trong khi các consumer phía sau chỉ xử lý nghiệp vụ của nhánh mình.

Bài học thuộc chương **Message router** của module **SPRING_INTEGRATION_PATTERN**. Nó kết nối trực tiếp với mục tiêu xây dựng message flow ít phụ thuộc và dễ mở rộng bằng **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel và correlation**, đồng thời kiểm thử được từng đường đi.

Sau bài này, bạn có thể:

1. Phân biệt *routing expression*, *routing key*, *channel mapping* và *default output channel*.
2. Viết biểu thức SpEL đọc thuộc tính payload và header, kể cả điều kiện ba ngôi.
3. Cấu hình Expression Router trong Java DSL của Spring Integration.
4. Xử lý dữ liệu thiếu, nhánh không có ánh xạ và lỗi khi đánh giá biểu thức.
5. Kiểm thử cả nhánh chính, fallback, lỗi và khả năng theo dõi correlation.

## 2. Router đứng ở đâu trong message flow?

~~~mermaid
flowchart LR
    A["Gateway: OrderPlaced"] --> IN["orders.in"]
    IN --> T["Transformer: chuẩn hóa"]
    T --> R{"Expression Router<br/>payload.market()"}
    R -->|"VN"| VN["orders.vn"]
    R -->|"US"| US["orders.us"]
    R -->|"Khác"| O["orders.other"]
    VN --> H1["Consumer nội địa"]
    US --> H2["Consumer Hoa Kỳ"]
    O --> H3["Consumer cần phân loại thêm"]
~~~

Tại Router, một message đầu vào được đánh giá để xác định *đích nhận*. Router chuyển message theo cấu hình channel; bước nghiệp vụ cụ thể xảy ra **sau Router**. Nó không tự thực hiện biến đổi payload, không tự bảo đảm lưu trữ bền vững và cũng không tự áp dụng chính sách retry cho handler đích.

Ví dụ: message có `market = "VN"` tạo key `VN`; mapping `VN → orders.vn` xác định channel nhận. Message có `market = "FR"` không khớp mapping đã khai báo nên được đưa tới `orders.other` nếu có cấu hình fallback.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Input message** | Message mà Router nhận từ channel đầu vào | `Message<OrderPlaced>` |
| **Routing expression** | Biểu thức SpEL tính giá trị quyết định | `payload.market()` |
| **Routing key** | Kết quả đánh giá biểu thức | `"VN"` |
| **Channel mapping** | Ánh xạ key sang tên channel đích | `"VN" → "orders.vn"` |
| **Default output channel** | Đích dự phòng khi không xác định được đích từ key | `"orders.other"` |
| **Downstream consumer** | Endpoint xử lý message ở channel được chọn | Handler xử lý đơn VN |

Một nguyên tắc hữu ích: **biểu thức quyết định “đi đâu”; handler quyết định “làm gì”**. Nếu logic phân loại rủi ro phức tạp, hãy để một service thuần Java tính mức rủi ro trước, rồi Router chỉ đọc kết quả ấy để định tuyến.

## 3. Spring Expression Language trong Router

SpEL có thể truy cập dữ liệu message bằng các đối tượng quen thuộc:

- `payload`: nội dung nghiệp vụ của message.
- `headers`: tập metadata như mã nguồn, độ ưu tiên hoặc correlation ID.
- Các toán tử như `==`, `!=`, `>`, `and`, `or` và toán tử điều kiện `condition ? a : b`.
- Các phương thức thuộc đối tượng payload, khi được phép và phù hợp với kiểu runtime.

Một số biểu thức điển hình:

| Biểu thức SpEL | Giá trị dự kiến | Khi dùng |
|---|---|---|
| `payload.market()` | `"VN"` | Payload là Java record có phương thức `market()` |
| `payload.region` | `"VN"` | Payload là bean có thuộc tính đọc được, ví dụ `getRegion()` |
| `headers['tenantTier']` | `"PREMIUM"` | Quyết định theo header đã được kiểm soát |
| `headers['riskLevel'] == 'HIGH' ? 'REVIEW' : 'AUTO'` | `"REVIEW"` hoặc `"AUTO"` | Chọn key theo điều kiện |
| `payload.quantity() > 100 ? 'BULK' : 'STANDARD'` | `"BULK"` hoặc `"STANDARD"` | Phân loại theo thuộc tính định lượng |

**Chú ý về Java record:** khi dùng `record OrderPlaced(String market)`, phương thức được sinh là `market()`. Biểu thức `payload.market()` gọi trực tiếp phương thức này và tránh phụ thuộc vào việc framework diễn giải record accessor thành bean property ở từng phiên bản.

**Biểu thức được đánh giá khi chạy**, không được Java kiểm tra kiểu ở thời điểm biên dịch. Nếu payload runtime không có phương thức được gọi, hoặc một thuộc tính đang `null`, việc đánh giá có thể ném ngoại lệ. Vì vậy, ở cửa vào cần có bước kiểm tra schema/kiểu và chuẩn hóa dữ liệu trước Router.

Về mặt thiết kế, nên dùng biểu thức **ngắn, thuần tính toán, không có tác dụng phụ**. Không gọi database, HTTP hoặc cập nhật trạng thái bên trong SpEL chỉ để chọn nhánh; các thao tác đó nên là handler/service riêng để dễ quản lý timeout, transaction và retry.

## 4. Ví dụ: Router theo thị trường trong Java DSL

Xét message chứa đơn hàng:

~~~java
record OrderPlaced(
    String orderId,
    String market,
    int quantity
) {}
~~~

Chúng ta sẽ lọc dữ liệu sai, chuẩn hóa `market` rồi đánh giá biểu thức `payload.market()`. Các bean channel/consumer được thể hiện bằng tên rõ ràng để quan sát luồng.

~~~java
@Configuration
@EnableIntegration
class OrderRoutingFlows {

    @Bean
    IntegrationFlow classifyOrders() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderPlaced.class,
                order -> order.orderId() != null
                    && !order.orderId().isBlank()
                    && order.market() != null
                    && !order.market().isBlank()
                    && order.quantity() > 0,
                filter -> filter.discardChannel("orders.invalid"))
            .transform(OrderPlaced.class,
                order -> new OrderPlaced(
                    order.orderId(),
                    order.market().trim().toUpperCase(Locale.ROOT),
                    order.quantity()))
            .route("payload.market()",
                router -> router
                    .channelMapping("VN", "orders.vn")
                    .channelMapping("US", "orders.us")
                    .defaultOutputChannel("orders.other"))
            .get();
    }

    @Bean
    IntegrationFlow vnOrders() {
        return IntegrationFlow.from("orders.vn")
            .handle(m -> System.out.println("VN: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow usOrders() {
        return IntegrationFlow.from("orders.us")
            .handle(m -> System.out.println("US: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow otherOrders() {
        return IntegrationFlow.from("orders.other")
            .handle(m -> System.out.println("OTHER: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow invalidOrders() {
        return IntegrationFlow.from("orders.invalid")
            .handle(m -> System.out.println("INVALID: " + m.getPayload()))
            .get();
    }
}
~~~

Ví dụ dùng **Spring Integration Java DSL** và Java record (Java 17+); các import Java/Spring được lược bỏ để tập trung vào flow. `IntegrationFlow.from("orders.in")` tạo đường nhận message theo tên channel; các flow khác kết nối consumer với từng channel đích. Khi tích hợp vào ứng dụng, đặt các bean ở cấu hình Spring được quét và cung cấp dependency của Spring Integration tương ứng.

Phân tích theo dữ liệu:

| Input | Sau Filter/Transformer | Routing key | Channel nhận |
|---|---|---|---|
| `("O-1", " vn ", 2)` | `market="VN"` | `VN` | `orders.vn` |
| `("O-2", "US", 1)` | `market="US"` | `US` | `orders.us` |
| `("O-3", "DE", 3)` | `market="DE"` | `DE` | `orders.other` |
| `("O-4", "", 2)` | Bị Filter loại | Không đánh giá | `orders.invalid` |
| `("O-5", "VN", 0)` | Bị Filter loại | Không đánh giá | `orders.invalid` |

**Filter discard khác Router fallback.** `orders.invalid` nhận dữ liệu không hợp lệ **trước** khi đánh giá expression; `orders.other` nhận dữ liệu có thể hợp lệ nhưng chưa có tuyến xử lý chuyên biệt. Phân biệt này giúp log, cảnh báo và quy tắc retry có ý nghĩa.

Ví dụ sử dụng handler in console để quan sát. Ở hệ thống thật, mỗi nhánh có thể gọi một service, phát sang outbound adapter hoặc thực hiện workflow riêng. Cần tránh cho handler ghi side effect nhiều lần nếu message được retry/redeliver.

## 5. Router theo header thay vì payload

Một quyết định định tuyến có thể phụ thuộc vào metadata, ví dụ loại khách hàng hoặc mức ưu tiên do ứng dụng đã kiểm tra. Khi ấy, biểu thức đọc header:

~~~java
@Bean
IntegrationFlow priorityRoutingFlow() {
    return IntegrationFlow.from("priority.in")
        .route("headers['riskLevel'] == 'HIGH' ? 'REVIEW' : 'AUTO'",
            r -> r.channelMapping("REVIEW", "orders.review")
                  .channelMapping("AUTO", "orders.automatic")
                  .defaultOutputChannel("orders.unknown"))
        .get();
}
~~~

Ví dụ này chọn `orders.review` khi header `riskLevel` là `"HIGH"` và chọn `orders.automatic` cho mọi trường hợp khác. **Header bị thiếu cũng dẫn tới `AUTO`** vì biểu thức điều kiện sai, chứ không đi vào default output. Đây có thể là hành vi nguy hiểm nếu `riskLevel` chưa được xác định.

Khi thiếu header phải được xử lý riêng, hãy viết điều kiện tường minh:

~~~java
.route(
    "headers['riskLevel'] == null ? 'UNKNOWN' : headers['riskLevel']",
    r -> r.channelMapping("HIGH", "orders.review")
          .channelMapping("LOW", "orders.automatic")
          .defaultOutputChannel("orders.unknown"))
~~~

Đoạn thứ hai là **một bước trong flow thay thế** cho Router trên; không gắn nối tiếp hai Router vào cùng ví dụ nếu chưa định nghĩa ranh giới xử lý mong muốn. Với header `null`, expression trả về `UNKNOWN`, không có mapping chuyên biệt và Router chuyển sang `orders.unknown`.

Lưu ý: header có thể đến từ hệ thống ngoài và không đáng tin cậy. Không nên cho giá trị header tự do quyết định tên bean/channel, nhất là channel dành cho nghiệp vụ nhạy cảm. Hãy kiểm tra nguồn và giá trị hợp lệ, sau đó dùng mapping tường minh cho các nhánh được hỗ trợ.

## 6. Routing key, channel mapping và fallback hoạt động thế nào?

Quy trình logic của một Router theo biểu thức:

~~~mermaid
flowchart TD
    M["Message tới Router"] --> E["Đánh giá SpEL"]
    E -->|Kết quả hợp lệ| K["Routing key"]
    E -->|Lỗi đánh giá| EX["Exception / đường xử lý lỗi"]
    K --> MAP{"Có channel mapping / đích phù hợp?"}
    MAP -->|Có| OUT["Gửi tới channel được chọn"]
    MAP -->|Không| DEF{"Có default output channel?"}
    DEF -->|Có| FALL["Gửi tới fallback"]
    DEF -->|Không| NO["Không có tuyến hợp lệ: xử lý theo cấu hình router"]
~~~

**Ba tình huống cần phân biệt:**

1. **Key có mapping**: ví dụ `VN` được ánh xạ thành `orders.vn`.
2. **Key không có mapping phù hợp**: dùng `defaultOutputChannel` nếu đã khai báo; không nên mặc định rằng mọi giá trị lạ đều được bỏ qua an toàn.
3. **Biểu thức ném exception**: lỗi xảy ra **trước bước tra mapping**. `defaultOutputChannel` không phải cơ chế `catch` cho lỗi cú pháp, thiếu method, lỗi chuyển kiểu hay exception từ logic được gọi.

Nếu không cấu hình fallback, hành vi khi không xác định được channel còn phụ thuộc các tùy chọn độ bắt buộc của router và việc phân giải tên channel. Đối với nghiệp vụ quan trọng, hãy **cấu hình nhánh fallback hoặc cơ chế báo lỗi rõ ràng**, thay vì chấp nhận message biến mất mà không được quan sát.

Nhánh fallback cũng cần giới hạn trách nhiệm: `orders.other` có thể ghi nhận để phân loại tiếp, còn `orders.invalid` dành cho dữ liệu sai schema hoặc điều kiện nghiệp vụ cơ bản. Không dùng fallback như nơi giấu mọi lỗi.

## 7. Biểu thức điều kiện: ngắn gọn nhưng phải diễn đạt nghiệp vụ rõ

SpEL hỗ trợ toán tử điều kiện:

~~~text
headers['tenantTier'] == 'VIP' ? 'PRIORITY' : 'STANDARD'
payload.quantity() >= 100 ? 'BULK' : 'NORMAL'
headers['market'] == null ? 'UNKNOWN' : headers['market']
~~~

Trong Java DSL, có thể định tuyến theo số lượng:

~~~java
.route(
    "payload.quantity() >= 100 ? 'BULK' : 'NORMAL'",
    r -> r.channelMapping("BULK", "orders.bulk")
          .channelMapping("NORMAL", "orders.standard"))
~~~

Ví dụ này là **đoạn riêng** sử dụng payload `OrderPlaced` đã kiểm tra và chuẩn hóa. Điều kiện `quantity >= 100` có thể là quy tắc phân loại đơn giản; nếu ngưỡng thực tế phụ thuộc hợp đồng khách hàng, thời gian hoặc dữ liệu tồn kho, nên tính `OrderCategory` trong một bước nghiệp vụ thuần Java và định tuyến theo category đã tính.

Các biểu thức ngày càng dài là dấu hiệu cần chuyển quyết định sang một hàm kiểm thử được:

~~~java
record RoutedOrder(
    String orderId,
    String market,
    String processingLane
) {}

// Service tính business category theo quy tắc riêng:
String lane = routingPolicy.determineLane(order);

// Router chỉ đọc category đã được công bố trên payload:
// .route("payload.processingLane()", spec -> ...)
~~~

Cách này giữ **Pipes and Filters** độc lập: Transformer/Service Activator tính phân loại, Router chọn channel, handler đích thực hiện hành động. Thay đổi quy tắc nghiệp vụ không bắt buộc phải nhúng thêm mã phức tạp vào SpEL.

## 8. So sánh Expression Router với các cách định tuyến khác

Spring Integration có nhiều cách thể hiện quyết định định tuyến. Chọn theo độ phức tạp và nơi lưu quy tắc:

| Cơ chế | Tiêu chí | Nên dùng khi |
|---|---|---|
| **ExpressionEvaluatingRouter** | Biểu thức SpEL từ payload/headers | Quy tắc đọc thuộc tính hoặc điều kiện ngắn |
| **HeaderValueRouter** | Giá trị của một header được chỉ định | Chỉ cần route theo một header, không cần SpEL phức tạp |
| **PayloadTypeRouter** | Kiểu runtime của payload | Mỗi class sự kiện đi tới flow phù hợp |
| **MethodInvokingRouter** | Kết quả method Java được gọi | Quy tắc tính route cần mã Java có thể unit test |
| **RecipientListRouter** | Danh sách recipient theo điều kiện | Cùng message cần gửi tới nhiều đích theo chính sách |

**Router theo biểu thức** thường diễn đạt một khóa lựa chọn nhánh; nó phù hợp với tình huống “VN hay US?”. Nếu cần gửi một message đồng thời tới nhiều subscriber, hãy đánh giá **Recipient List Router** hoặc cơ chế publish-subscribe thích hợp. Không mặc định một expression trả về chuỗi chứa dấu phẩy sẽ tự được tách thành nhiều tên channel.

**Router không thay thế Filter.** Filter giải quyết “message này có được đi tiếp hay không?”. Router giải quyết “message hợp lệ đi theo nhánh nào?”. **Transformer không thay Router**: Transformer thay payload/headers; Router chọn đường đi. Thực hành kết hợp ba pattern giúp flow rõ ràng và dễ kiểm thử.

## 9. Kiểu payload và vấn đề null

Một expression phụ thuộc vào hình dạng dữ liệu tại **đúng thời điểm** router nhận message. Nếu Transformer đổi `OrderPlaced` thành một `Map`, biểu thức `payload.market()` sẽ không còn phù hợp. Vì vậy đầu vào Router cần một hợp đồng rõ ràng.

Ví dụ:

~~~java
record OrderPlaced(String orderId, String market, int quantity) {}

Message<OrderPlaced> msg = MessageBuilder
    .withPayload(new OrderPlaced("O-21", "VN", 3))
    .setHeader("correlationId", "O-21")
    .build();
~~~

Với kiểu này:

- `payload.market()` gọi phương thức record.
- `headers['correlationId']` lấy header có tên tương ứng.
- `payload['market']` **không** được mặc định coi là cú pháp tương đương trên mọi loại payload: cú pháp truy cập map/index và cú pháp gọi getter có cơ chế khác nhau.

Khi biểu thức dùng header có thể vắng, hãy phân biệt **null**, chuỗi rỗng và giá trị không được hỗ trợ. Ví dụ `headers['riskLevel'] == null` chỉ phát hiện thiếu/null; chuỗi `""` cần bước validate hoặc điều kiện riêng. Với dữ liệu nhận từ HTTP/broker, thực hiện decode, validation, normalization tại ingress để Router nhận cấu trúc ổn định.

### Vì sao không tạo expression từ dữ liệu người dùng?

**Không ghép chuỗi input không tin cậy thành biểu thức SpEL rồi đánh giá.** SpEL là một ngôn ngữ biểu thức có khả năng truy cập thuộc tính/phương thức; một expression xây từ dữ liệu người dùng có thể gây lỗi hoặc tạo quyền thực thi ngoài ý định nếu không bị giới hạn. Hãy giữ expression là cấu hình do ứng dụng kiểm soát, còn dữ liệu người dùng chỉ được dùng như **giá trị được đọc** từ payload/header và được đối chiếu với whitelist key.

Với nhiều tenant, cũng không nên dựng tên channel theo chuỗi `"orders." + tenantId` rồi gửi tới mọi bean có tên phù hợp. Hãy mapping theo danh sách tenant/route đã được phép, có nhánh unknown và cảnh báo khi gặp giá trị lạ.

## 10. Router có thay đổi message hoặc correlation ID không?

Router chủ yếu quyết định **channel đích**. Nó không phải Transformer, nên thông thường payload của message chuyển tiếp vẫn giữ giá trị mà Router nhận được. Những header phục vụ tracing và correlation cũng có thể được giữ theo cách thức flow/adapter truyền message.

Tuy nhiên, **không dựa vào sự giữ nguyên header một cách mù quáng** khi có Transformer, Gateway, broker adapter hoặc serializer giữa các bước: header mapping, filter và cách tạo message mới có thể thay đổi metadata. Với flow sử dụng **Splitter → Router → Aggregator**, đặc biệt cần xác minh `correlationId`, `sequenceNumber` và `sequenceSize` để các phần của cùng một đơn hàng được gom đúng nhóm.

~~~mermaid
flowchart LR
    S["Splitter: order O-10"] --> A["Line 1 + correlation O-10"]
    S --> B["Line 2 + correlation O-10"]
    A --> R{"Router: loại hàng"}
    B --> R
    R --> X["Xử lý hàng thường"]
    R --> Y["Xử lý hàng đặc biệt"]
    X --> G["Aggregator theo correlation"]
    Y --> G
    G --> RES["OrderSummary O-10"]
~~~

Trong ví dụ, Router có thể chuyển từng dòng sang một nhánh khác nhau; Aggregator vẫn cần thông tin tương quan để biết chúng thuộc cùng đơn. Nếu một nhánh bị giữ lại, lỗi hoặc bị drop, hãy thiết kế **timeout, release strategy và đường xử lý nhóm thiếu phần** thay vì chờ vô hạn.

Khi một thông điệp được giao lại qua broker, `messageId` của đối tượng Spring Message có thể thay đổi. Muốn chống xử lý trùng phải dùng định danh nghiệp vụ hoặc event ID ổn định được quy định trong hợp đồng, không lấy ID mới của từng message làm bảo đảm duy nhất.

## 11. Hành vi đồng bộ, bất đồng bộ và backpressure

Router không tự quyết định luồng sẽ chạy đồng bộ hay bất đồng bộ. Điều này phụ thuộc channel đầu vào/đầu ra và endpoint phía sau:

| Channel sau Router | Cách xử lý thường gặp | Điều cần quan sát |
|---|---|---|
| `DirectChannel` | Consumer chạy trong thread gửi theo cơ chế dispatch đồng bộ | Handler chậm có làm chậm producer? |
| `ExecutorChannel` | Công việc được giao sang executor | Queue executor đầy, lỗi bất đồng bộ, thứ tự hoàn tất |
| `QueueChannel` | Message được đưa vào queue chờ polling consumer | Backlog, capacity, timeout gửi, mất dữ liệu khi restart |
| Outbound adapter tới broker | Message được gửi tới hệ thống ngoài | Ack/publish confirm, retry, độ bền, delivery semantics |

Ví dụ Router chuyển 90% message vào một nhánh xử lý chậm. Dù biểu thức đánh giá rất nhanh, queue và worker của nhánh đó vẫn có thể quá tải. Vì vậy cần đo **tỷ lệ message trên từng route, throughput, latency, lỗi, backlog và tuổi message**.

Hạn chế biểu thức tính toán nặng hoặc truy cập tài nguyên ngoài. Quy tắc routing không nên trở thành nút nghẽn chung của mọi message.

## 12. Error channel, fallback và retry: ba trách nhiệm khác nhau

Không nên gom mọi trường hợp thành “đưa về default”:

| Trường hợp | Cơ chế phù hợp | Ví dụ |
|---|---|---|
| Message sai dữ liệu nghiệp vụ/contract trước Router | Filter discard hoặc validation error | `quantity <= 0` |
| Message hợp lệ nhưng chưa có nhánh cụ thể | Router default output channel | `market="DE"` khi chỉ hỗ trợ VN/US |
| Biểu thức SpEL không đánh giá được | Exception/error handling của flow | Payload sai kiểu, gọi method trên `null` |
| Channel đích gặp lỗi tạm thời | Retry theo loại lỗi và ranh giới thực thi | Handler gọi dịch vụ tồn kho bị timeout |
| Message đã retry hết | Error workflow, DLQ/quarantine hoặc xử lý thủ công | Broker redelivery vượt giới hạn |

**Default output channel không bắt được mọi exception.** Nếu `payload.market()` ném lỗi, framework không tự coi lỗi này là key `OTHER`. Với flow đồng bộ dùng DirectChannel, exception có thể truyền ngược về caller/Gateway; trong flow bất đồng bộ, poller hoặc adapter có chính sách error channel/error handler riêng.

Retry nên dành cho các sự cố **tạm thời**. Retry nhiều lần một biểu thức sai vì thiếu method hoặc một payload không hợp schema thường không giải quyết được nguyên nhân. Nếu một handler đã tạo tác dụng phụ trước khi lỗi xuất hiện, retry có thể thực hiện lại nghiệp vụ; cần **idempotency**, giới hạn số lần và backoff rõ ràng.

Thiết kế metric riêng cho fallback và exception: số lượng message vào `orders.other` cao cho thấy có thể xuất hiện thị trường mới, còn số lỗi SpEL tăng thể hiện sự không khớp contract hoặc vấn đề cấu hình.

## 13. Kiểm thử Router theo biểu thức

Muốn kiểm thử tuyến đường một cách xác định, có thể dùng **channel nhận kết quả là QueueChannel trong cấu hình test**. Khi đó, gửi message vào `orders.in` và dùng `receive(timeout)` để lấy message từ channel mong đợi, thay vì chỉ kiểm tra log console.

Ví dụ khai báo các channel đích **chỉ cho môi trường test** (thay thế các flow tiêu thụ message trong ví dụ chạy ứng dụng):

~~~java
@TestConfiguration
class RoutingTestChannels {

    @Bean(name = "orders.vn")
    PollableChannel vn() {
        return new QueueChannel();
    }

    @Bean(name = "orders.us")
    PollableChannel us() {
        return new QueueChannel();
    }

    @Bean(name = "orders.other")
    PollableChannel other() {
        return new QueueChannel();
    }

    @Bean(name = "orders.invalid")
    PollableChannel invalid() {
        return new QueueChannel();
    }
}
~~~

Với Spring test context có flow `classifyOrders()` và các bean test trên, một phép thử cho nhánh nội địa có thể viết:

~~~java
@Autowired
ApplicationContext context;

@Test
void routesNormalizedVietnamOrder() {
    MessageChannel input = context.getBean(
        "orders.in", MessageChannel.class);
    PollableChannel vn = context.getBean(
        "orders.vn", PollableChannel.class);
    PollableChannel us = context.getBean(
        "orders.us", PollableChannel.class);

    Message<OrderPlaced> event = MessageBuilder
        .withPayload(new OrderPlaced("O-101", " vn ", 2))
        .setHeader("correlationId", "O-101")
        .build();

    assertTrue(input.send(event));
    Message<?> received = vn.receive(1000);

    assertNotNull(received);
    assertEquals("VN", ((OrderPlaced) received.getPayload()).market());
    assertEquals("O-101",
        received.getHeaders().get("correlationId"));
    assertNull(us.receive(0));
}
~~~

Ví dụ chỉ minh họa phần thân test; cần cấu hình JUnit/Spring test để nạp flow và class test configuration. **Không khai báo đồng thời consumer production trên `orders.vn` và QueueChannel test cùng tên.** Test channel thay thế đích thực thi để quan sát chính xác message.

Ma trận kiểm thử tối thiểu:

| Case | Input | Kênh/điều kiện kỳ vọng |
|---|---|---|
| VN chuẩn | `market="VN"` | `orders.vn` |
| VN chưa chuẩn hóa | `market=" vn "` | Sau Transformer tới `orders.vn` |
| US | `market="US"` | `orders.us` |
| Chưa khai báo | `market="DE"` | `orders.other` |
| Thị trường trống | `market=""` | `orders.invalid`, không chạy Router |
| Số lượng âm | `quantity=-1` | `orders.invalid` |
| Header thiếu | Không có `riskLevel` | Nhánh unknown nếu expression đã thiết kế theo null |
| Payload sai kiểu | Producer gửi `String` thay cho `OrderPlaced` | Lỗi chuyển đổi/đánh giá được quan sát, không route âm thầm |
| Consumer lỗi | Handler downstream ném exception | Đường lỗi phù hợp với kiểu channel, retry có giới hạn |
| Hai order xen kẽ | Khác `correlationId` | Không trộn nhóm khi qua Splitter/Aggregator |

Với flow bất đồng bộ, dùng latch hoặc assertion có thời hạn; tránh dựa vào `Thread.sleep` cố định. Khi kiểm tra error channel cần biết exception xuất hiện ở caller, thread executor hay poller, rồi chọn đúng điểm quan sát.

## 14. Quan sát và chẩn đoán định tuyến

Để giải thích “đơn hàng này đã đi đâu?”, nên có các thông tin:

- **Routing key được tính** và **tên route/channel đích** ở mức log hoặc metric không chứa dữ liệu nhạy cảm.
- **Correlation ID**, event ID và order ID để nối các bước Gateway → Transformer → Router → consumer.
- Số message vào mỗi nhánh, tỷ lệ dùng fallback, số lỗi đánh giá SpEL.
- Thời gian xử lý từng nhánh và backlog của các nhánh bất đồng bộ.
- Số lần retry, timeout và message được chuyển tới quy trình xử lý thất bại.

Nếu bật observation/Micrometer cho Spring Integration, hãy cấu hình tên channel và endpoint nhất quán. Đừng đưa nguyên payload, tài khoản, token hay thông tin khách hàng vào nhãn metric vì dễ gây lộ dữ liệu và làm tăng số lượng chuỗi nhãn (*cardinality*).

Khi một Router dường như đưa message sai nhánh, kiểm tra theo thứ tự: **payload runtime type → dữ liệu sau Transformer → giá trị expression → mapping/fallback → bean channel được phân giải → consumer downstream**. Đây là đường chẩn đoán rõ ràng hơn việc chỉ nhìn log ở handler cuối.

## 15. Sai lầm phổ biến khi dùng Router theo biểu thức

**Đặt nghiệp vụ phức tạp trong SpEL.** Expression dài, truy vấn dữ liệu hoặc gọi service gây khó test. Để một domain policy/service tính kết quả, rồi route theo trường/key ổn định.

**Nhầm default với error channel.** Default dùng khi key không khớp tuyến phù hợp. Exception trong đánh giá expression hoặc khi gửi sang channel cần cơ chế error/recovery riêng.

**Giả định header luôn có.** Một header thiếu có thể tạo `null` hoặc điều kiện sai rồi đi nhầm nhánh; định nghĩa riêng unknown/invalid và test đủ dữ liệu thiếu.

**Đưa tên channel trực tiếp từ input không tin cậy.** Routing tùy ý theo giá trị user/tenant có thể mở sai đường xử lý. Dùng danh sách key được cho phép với channel mapping tường minh.

**Chỉnh Transformer mà quên expression.** Sau thay đổi kiểu payload, gọi method/property cũ có thể gây lỗi runtime. Viết contract test cho đầu vào/đầu ra của từng đoạn flow.

**Quên consumer của nhánh fallback.** Có mapping nhưng không có channel/handler đích hợp lệ sẽ làm flow lỗi hoặc thông điệp không được xử lý như kỳ vọng. Tất cả route đều cần chủ sở hữu rõ.

**Không kiểm tra ảnh hưởng đến correlation.** Định tuyến thông điệp con của Splitter sang nhiều nhánh có thể làm một nhánh chậm hoặc hỏng; Aggregator cần timeout và điều kiện release an toàn.

**Cho rằng Router bảo đảm exactly-once.** Router chỉ điều phối channel. Delivery, idempotency, transaction, retry và tính bền vững phụ thuộc các thành phần quanh nó.

## 16. Bài thực hành tổng hợp

Xây dựng flow **OrderRouting** gồm:

1. **Gateway** nhận `OrderPlaced(orderId, market, quantity)`.
2. **Filter** loại đơn có ID trống, thị trường rỗng hoặc số lượng không dương.
3. **Transformer** chuẩn hóa mã thị trường về chữ hoa.
4. **Expression Router** đọc `payload.market()` và chuyển `VN → orders.vn`, `US → orders.us`, còn lại tới `orders.other`.
5. Thêm Router khác dựa trên header `riskLevel`; trường hợp thiếu header phải được đưa tới quy trình phân loại riêng.
6. Consumer của từng nhánh ghi kết quả vào channel test hoặc gọi service giả lập. Một nhánh có thể chạy qua executor/queue để quan sát khác biệt đồng bộ và bất đồng bộ.
7. Cố ý tạo lỗi handler; xác định đường lỗi, retry phù hợp, idempotency và correlation khi gửi lại message.

**Tiêu chí hoàn thành:** Có sơ đồ flow, bảng routing key → channel, test cho đủ ba thị trường và input invalid, test cho header thiếu và expression error, số liệu message theo nhánh và khả năng truy vết một order xuyên Router. Nếu bổ sung Splitter/Aggregator, chứng minh các phần vẫn được gom theo đúng correlation ID.

## 17. Ghi nhớ

**Expression Router** dùng SpEL để tính quyết định định tuyến từ message, còn **channel mapping** gắn quyết định đó với channel đích. **Default output channel** xử lý key không có tuyến phù hợp; **error channel/exception handling** giải quyết lỗi thực thi, và **Filter** loại dữ liệu không hợp lệ trước Router.

Trong Spring Integration, giữ biểu thức ngắn, kiểm tra kiểu và giá trị trước khi route, cấu hình fallback rõ ràng, bảo toàn correlation qua các adapter và kiểm thử mọi nhánh. Khi kết hợp với các EIP khác, Router giúp luồng thông điệp dễ thay đổi và mở rộng mà không trộn logic truyền nhận với logic nghiệp vụ.
