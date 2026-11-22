# Lộ trình học từ message flow đến flow phân tán

## 1. Đích đến của lộ trình

Trong một ứng dụng nhỏ, ta có thể xử lý yêu cầu bằng một chuỗi lời gọi phương thức: nhận đơn hàng, kiểm tra dữ liệu, tính giá, lưu kết quả và trả lời. Khi hệ thống có nhiều nguồn dữ liệu, nhiều nhánh xử lý hoặc các dịch vụ triển khai độc lập, cách gọi trực tiếp này dễ làm các thành phần phụ thuộc lẫn nhau. **Spring Integration** giúp mô tả việc trao đổi dữ liệu thành *message flow* dựa trên các **Enterprise Integration Patterns (EIP)**: mỗi bước nhận thông điệp, xử lý một trách nhiệm rõ ràng rồi chuyển tới bước tiếp theo qua channel.

Mục tiêu của bài nhập môn này là lập một đường học có thể thực hành và đo kết quả, đi từ luồng đồng bộ trong một ứng dụng đến luồng bất đồng bộ, có khả năng phục hồi và được triển khai qua nhiều tiến trình. Các kỹ thuật trọng tâm gồm **Gateway, Filter, Transformer, Router, Splitter, Aggregator, correlation, retry, error channel**; kèm theo kiểm thử và quan sát từng nhánh xử lý.

Sau lộ trình, người học cần:

1. Giải thích được **message, payload, headers, channel, endpoint** và phân biệt lời gọi đồng bộ với truyền thông điệp bất đồng bộ.
2. Thiết kế luồng bằng Spring Integration Java DSL, xác định được thông điệp sẽ đi qua nhánh nào và vì sao.
3. Giữ được thông tin tương quan khi tách/gộp thông điệp và xử lý được lỗi, trùng lặp, quá hạn.
4. Quyết định đúng lúc cần broker, lưu trữ trạng thái, mở rộng nhiều instance và cơ chế bù trừ.
5. Chứng minh hành vi bằng test, metric, log và trace thay vì chỉ thấy chương trình chạy thành công một lần.

## 2. Mô hình nền tảng: từ lời gọi hàm tới message flow

Một **Message** gồm **payload** (dữ liệu nghiệp vụ) và **headers** (metadata, ví dụ ID thông điệp, thời gian, correlation ID, reply channel). **MessageChannel** vận chuyển message giữa các endpoint. **Endpoint** đảm nhiệm hành động như lọc, biến đổi, định tuyến, gọi dịch vụ hoặc kết nối hệ thống ngoài. Tách ba khái niệm này giúp thay đổi cách truyền nhận mà không phải viết lại toàn bộ xử lý nghiệp vụ.

~~~mermaid
flowchart LR
    G[Gateway: nhận yêu cầu] --> C[orders.in]
    C --> F{Filter: hợp lệ?}
    F -->|Không| X[orders.invalid]
    F -->|Có| T[Transformer: chuẩn hóa]
    T --> R{Router: khu vực}
    R -->|VN| V[orders.vn]
    R -->|Khác| I[orders.intl]
~~~

Trong sơ đồ này, **Gateway** là cửa vào, **Filter** kiểm tra điều kiện, **Transformer** tạo dạng dữ liệu nhất quán và **Router** chọn nhánh. Những thành phần này không bắt buộc biết ai tạo thông điệp và ai sẽ tiếp tục xử lý sau channel.

Điểm phân biệt quan trọng:

| Thành phần | Chức năng | Câu hỏi khi thiết kế |
|---|---|---|
| Gateway | Đưa lời gọi của ứng dụng vào flow, có thể nhận phản hồi | Bên gọi cần trả lời ngay hay chỉ cần xác nhận đã nhận? |
| Channel | Chuyển message giữa các endpoint | Truyền ngay, đưa vào hàng đợi hay giao cho executor? |
| Filter | Chấp nhận hoặc loại message theo điều kiện | Message bị loại sẽ đi đâu và có cần lưu lý do không? |
| Transformer | Đổi cấu trúc hoặc nội dung payload | Headers và thông tin định danh nào phải giữ lại? |
| Router | Chọn một hoặc nhiều nhánh đích theo tiêu chí | Có nhánh mặc định và cách xử lý giá trị lạ chưa? |
| Splitter | Tách một message thành nhiều phần | Nhận dạng nhóm và số lượng phần như thế nào? |
| Aggregator | Gom các message có liên hệ thành kết quả | Khi nào đủ phần để phát kết quả, khi nào timeout? |
| Service Activator | Gọi logic nghiệp vụ | Logic có gây tác dụng phụ, cần retry hoặc idempotency không? |

**DirectChannel** thường chuyển việc tới handler trong cùng luồng thực thi của bên gửi; không tạo ranh giới bền vững. **ExecutorChannel** đưa handler sang executor, thay đổi ngữ cảnh thực thi nhưng bản thân nó không cung cấp hàng đợi bền vững. **QueueChannel** lưu message trong hàng đợi cục bộ để một poller hoặc bên nhận lấy ra; việc bền vững qua khởi động lại phụ thuộc vào cấu hình message store. Broker như Kafka hoặc RabbitMQ mới tạo ranh giới giao tiếp giữa các tiến trình, nhưng vẫn cần thiết kế retry và bảo đảm dữ liệu phù hợp.

## 3. Lộ trình bảy chặng

Thực hiện lần lượt, vì mỗi chặng dùng kết quả của chặng trước. Bài tập xuyên suốt là **xử lý đơn hàng đa khu vực**: nhận order, xác thực, chuẩn hóa, phân loại, tách các dòng hàng, xử lý song song, gộp kết quả, ghi nhận lỗi và cuối cùng kết nối một dịch vụ độc lập.

| Chặng | Kiến thức cần nắm | Bài thực hành bắt buộc | Điều kiện qua chặng |
|---|---|---|---|
| **1. Message flow cục bộ** | Message, headers, channel, Gateway, Java DSL | Nhận order qua Gateway, chuyển tới handler | Vẽ và chạy được flow một chiều; kiểm tra payload và headers |
| **2. Rẽ nhánh và biến đổi** | Filter, Transformer, Router, discard/default channel | Loại order sai, chuẩn hóa khu vực, định tuyến VN/quốc tế | Mọi input có đường đi xác định, kể cả input lỗi |
| **3. Tách và gộp** | Splitter, Aggregator, sequence, correlation | Tách order thành line item, tính từng dòng rồi gộp | Không gộp lẫn hai order; xử lý nhóm thiếu phần hoặc quá hạn |
| **4. Bất đồng bộ và áp lực tải** | ExecutorChannel, QueueChannel, poller, ordering | Chuyển một đoạn flow sang xử lý bất đồng bộ, giới hạn công việc đang chờ | Đo được throughput, độ trễ và hành vi khi backlog tăng |
| **5. Phục hồi khi lỗi** | ErrorMessage, error channel, retry, backoff, idempotency | Mô phỏng timeout, lỗi tạm thời, message trùng | Phân biệt retry được/không được; lỗi có nơi nhận và theo dõi |
| **6. Phân tán qua broker** | AMQP/Kafka/JMS adapter, consumer, durability, outbox | Tách producer và worker thành hai ứng dụng trao đổi qua broker | Khởi động lại worker không làm mất nghiệp vụ đã xác nhận |
| **7. Kiểm thử và quan sát** | Flow test, correlation, metric, trace, tải, vận hành | Kiểm tra mọi nhánh và lỗi; dashboard theo luồng | Truy vết được một order từ đầu đến cuối và giải thích được các thất bại |

Các chặng là **mốc năng lực**, không phải số ngày cố định. Có thể chia thành bốn vòng thực hành: (1) flow cục bộ và nhánh, (2) split/aggregate và bất đồng bộ, (3) lỗi và tính tin cậy, (4) broker, kiểm thử tích hợp và quan sát.

## 4. Chặng 1–2: dựng một flow chạy được

Với Spring Boot, có thể bắt đầu bằng dependency `spring-boot-starter-integration`; phần kiểm thử thêm `spring-integration-test` ở scope `test`. Java DSL mô tả tuyến xử lý rõ ràng và dễ đặt tên cho các channel.

Ví dụ tối giản dưới đây sử dụng Java record (Java 17+) để minh họa **Gateway → Filter → Transformer → Router**. Các import quen thuộc của Java, Spring và Spring Integration được lược bớt cho dễ đọc.

~~~java
record Order(String id, String region, BigDecimal amount) {}
record NormalizedOrder(String id, String region, BigDecimal amount) {}

@MessagingGateway(defaultRequestChannel = "orders.in")
interface OrderGateway {
    void submit(Order order);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderFlows {
    @Bean
    IntegrationFlow classifyOrders() {
        return IntegrationFlow.from("orders.in")
            .filter(Order.class,
                o -> o.id() != null && !o.id().isBlank()
                    && o.region() != null && !o.region().isBlank()
                    && o.amount() != null && o.amount().signum() > 0,
                f -> f.discardChannel("orders.invalid"))
            .transform(Order.class,
                o -> new NormalizedOrder(
                    o.id(),
                    o.region().trim().toUpperCase(Locale.ROOT),
                    o.amount()))
            .route(NormalizedOrder.class, NormalizedOrder::region,
                r -> r.channelMapping("VN", "orders.vn")
                    .defaultOutputChannel("orders.intl"))
            .get();
    }

    @Bean
    IntegrationFlow vnOrders() {
        return IntegrationFlow.from("orders.vn")
            .handle(m -> System.out.println("VN: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow internationalOrders() {
        return IntegrationFlow.from("orders.intl")
            .handle(m -> System.out.println("INTL: " + m.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow rejectedOrders() {
        return IntegrationFlow.from("orders.invalid")
            .handle(m -> System.out.println("INVALID: " + m.getPayload()))
            .get();
    }
}
~~~

Gọi `orderGateway.submit(new Order("O-101", "vn", new BigDecimal("120000")))` sẽ qua nhánh VN. Khu vực `SG` đi vào nhánh quốc tế; ID rỗng hoặc số tiền không hợp lệ bị chuyển sang kênh loại bỏ. Đây là **ví dụ học tập**: handler đang in log, còn hệ thống thật nên gọi các service thích hợp và ghi lý do từ chối theo chính sách nghiệp vụ.

Trong một flow dùng `DirectChannel`, các endpoint có thể chạy trên thread của bên gửi. Vì vậy **Gateway có return type `void` không có nghĩa là xử lý nền**. Chỉ khi đưa vào ranh giới bất đồng bộ hoặc hàng đợi phù hợp mới thay đổi hành vi chờ và lỗi của bên gọi.

**Bài tập mở rộng:** thêm một Router cho loại khách hàng, tạo nhánh mặc định khi giá trị chưa được hỗ trợ và bảo đảm mỗi nhánh đều có handler. Kiểm tra ba trường hợp: order hợp lệ nội địa, order quốc tế và order không hợp lệ. Chú ý giữ `orderId` trong payload hoặc header để phục vụ truy vết về sau.

## 5. Chặng 3: Splitter, Aggregator và correlation

Một đơn hàng có nhiều dòng hàng thường cần kiểm tra tồn kho hoặc tính phí từng dòng. **Splitter** tạo các thông điệp con; **Aggregator** chỉ gom những phần thuộc cùng một nhóm. Đây là bước biến flow tuyến tính thành flow nhiều nhánh hợp nhất.

~~~mermaid
flowchart LR
    O[Order O-101: ba dòng] --> S[Splitter]
    S --> A[Line 1]
    S --> B[Line 2]
    S --> C[Line 3]
    A --> P[Kiểm tra / tính giá]
    B --> P
    C --> P
    P --> G[Aggregator theo correlation]
    G --> R[Kết quả order]
~~~

Splitter của Spring Integration có thể bổ sung các sequence headers như `correlationId`, `sequenceNumber`, `sequenceSize`. Aggregator mặc định có thể dựa vào thông tin tương quan và chuỗi để tập hợp/release nhóm. Khi qua một hệ thống ngoài, **phải xác minh adapter và phép chuyển đổi có giữ các headers cần thiết hay không**; nếu không, hãy ánh xạ rõ ràng vào metadata sự kiện hoặc payload.

Trong bài toán thực tế, nên có khóa nghiệp vụ ổn định như `orderId`. Đừng nhầm `messageId` của từng lần phát message với khóa tương quan của cả order. Đặc biệt khi retry/redelivery, một order có thể tạo ra nhiều message khác nhau.

Thiết kế Aggregator cần trả lời đồng thời bốn câu hỏi:

1. **Correlation:** Những message nào thuộc cùng một nhóm? Có trộn `tenantId` hoặc `orderId` giữa các khách hàng không?
2. **Release:** Đủ `sequenceSize` là phát kết quả, hay chỉ phát khi đủ các loại kết quả theo quy tắc nghiệp vụ?
3. **Timeout:** Nếu một dòng hàng không bao giờ hoàn tất, nhóm sẽ chờ bao lâu? Phát kết quả một phần, đánh dấu thất bại hay chuyển sang xử lý thủ công?
4. **Message store:** Nhóm đang nằm trong RAM hay store bền vững? Điều gì xảy ra nếu instance giữ nhóm bị khởi động lại?

Để luyện tập, hãy tạo hai order A và B, mỗi order có ba dòng; cho các kết quả về xen kẽ và cố ý làm chậm một dòng của A. Tiêu chí đạt: không có kết quả của B lọt vào A, không phát tổng kết khi chưa đạt điều kiện release, và nhóm quá hạn tạo được thông tin lỗi có `orderId`.

## 6. Chặng 4: đổi cách thực thi và kiểm soát áp lực tải

Chuyển từ đồng bộ sang bất đồng bộ không đơn thuần là thêm thread. Phải xét **sức chứa hàng đợi, thứ tự xử lý, độ trễ, cơ chế dừng và khả năng khôi phục**.

| Cách nối flow | Thích hợp | Điểm cần thử |
|---|---|---|
| `DirectChannel` | Xử lý ngắn, đồng bộ trong một tiến trình | Một handler chậm có chặn bên gửi? Exception truyền ngược như thế nào? |
| `ExecutorChannel` | Giao việc sang executor trong cùng ứng dụng | Thread pool và hàng đợi đầy xử lý ra sao? Thứ tự có thay đổi? |
| `QueueChannel` + poller | Tách tốc độ producer/consumer trong cùng ứng dụng | Poller lấy bao nhiêu message, tồn đọng bao lâu, store có bền không? |
| Broker + inbound/outbound adapter | Chuyển message giữa tiến trình hoặc dịch vụ | Ack, redelivery, partition, consumer restart và duplicate ra sao? |

Thử nghiệm có kiểm soát: phát 1.000 order tới một handler giả lập mất 100 ms/order; đo **tốc độ nhận**, **tốc độ hoàn tất**, **p95 latency**, **số message đang chờ** và **lỗi khi hàng đợi đầy**. Thay đổi số worker, kích thước queue và tốc độ đầu vào để quan sát: throughput có thể tăng nhưng latency và bộ nhớ cũng có thể tăng. Giới hạn concurrency, batch size và khả năng từ chối nhận thêm phải được thiết kế theo tải thực tế.

Không giả định xử lý bất đồng bộ sẽ giữ thứ tự tổng thể. Nếu thứ tự theo `orderId` là yêu cầu cứng, cần thiết kế partition/key hoặc cơ chế serialize phù hợp tại ranh giới có thể chạy song song.

## 7. Chặng 5: lỗi, retry và idempotency

Luồng tin cậy phải trả lời được: **khi một bước hỏng, message đang ở đâu, ai nhận lỗi, có chạy lại không và chạy lại có gây tác dụng phụ hay không?**

**Phân loại lỗi trước khi retry:**

- **Lỗi dữ liệu/quy tắc nghiệp vụ:** ví dụ giá trị âm hoặc trạng thái order không hợp lệ. Thường chuyển qua kênh từ chối có lý do, không retry vô hạn.
- **Lỗi tạm thời:** ví dụ timeout hoặc dịch vụ phụ thuộc trả lỗi quá tải. Có thể retry với số lần giới hạn, backoff và jitter, sau đó chuyển đến nơi xử lý thất bại.
- **Lỗi không xác định kết quả:** ví dụ đã ghi thanh toán thành công nhưng kết nối đứt trước phản hồi. Retry trực tiếp có thể tạo bản ghi trùng nếu thiếu idempotency.

Trong Spring Integration, các endpoint có thể áp dụng **retry advice** cho thao tác phù hợp. Với phần xử lý bất đồng bộ, dùng **error channel** để nhận `ErrorMessage` theo cơ chế phát lỗi của endpoint/adapter; trong luồng đồng bộ, exception có thể truyền ngược về Gateway. Không nên mặc định rằng mọi lỗi đều tự đi tới cùng một error channel. Kiểm tra rõ đường lỗi của từng inbound adapter và channel.

Ví dụ chính sách cho thao tác ghi hóa đơn:

| Tình huống | Hành động mong muốn |
|---|---|
| HTTP 429/503 nhất thời | Retry tối đa số lần đã định, backoff tăng dần |
| Dữ liệu schema sai | Chuyển sang `orders.invalid`, không retry |
| Timeout sau thao tác ghi | Tra cứu theo idempotency key trước khi thực hiện lại |
| Retry đã hết | Gửi tới hàng lỗi (DLQ) hoặc quy trình xử lý thủ công, kèm context |
| Nhận lại sự kiện đã xử lý | Nhận diện trùng theo business key và xử lý an toàn |

Gắn `orderId`, `eventId`, `attempt` và correlation/tracing context cho từng lần xử lý. **Idempotency** có thể được triển khai bằng khóa nghiệp vụ duy nhất, ràng buộc unique ở database hoặc bảng đánh dấu đã xử lý. Chỉ ghi nhận đã xử lý khi tác dụng phụ thực sự thành công, đồng thời thiết kế transaction/ghi nhận thích hợp để tránh lỗi ở khoảng giữa.

Kiểm thử fault injection ít nhất gồm: handler ném exception, dependency timeout, broker redelivery, nhận cùng sự kiện hai lần, lỗi sau khi ghi dữ liệu nhưng trước khi ack. Một flow không được coi là đáng tin cậy chỉ vì có khối retry.

## 8. Chặng 6: đưa message flow qua ranh giới phân tán

Sau khi hiểu flow trong một tiến trình, hãy tách **producer** (nhận order) và **worker** (xử lý order) thành hai ứng dụng. Thêm message broker thông qua adapter tương ứng của Spring Integration (chẳng hạn RabbitMQ/AMQP hoặc Kafka tùy yêu cầu). Lúc này, thời gian sống của thông điệp và của một tiến trình không còn giống nhau.

~~~mermaid
flowchart LR
    C[Client] --> API[Order API / Gateway]
    API --> V[Validate + normalize]
    V --> OUT[Outbound adapter]
    OUT --> Q[(Broker: order events)]
    Q --> IN1[Worker A: inbound adapter]
    Q --> IN2[Worker B: inbound adapter]
    IN1 --> F1[Process + persist]
    IN2 --> F2[Process + persist]
    F1 --> RES[(Kết quả / DB)]
    F2 --> RES
    F1 --> ERR[(DLQ / error workflow)]
    F2 --> ERR
~~~

Sơ đồ là kiến trúc logic; **việc một event được gửi đến một hay nhiều consumer** phụ thuộc cấu hình queue, topic, consumer group và subscription. Nếu cần tách từng đơn hàng cho một worker, thiết kế consumer group phù hợp. Nếu cần phát cùng event cho nhiều nghiệp vụ độc lập, thiết kế nhóm subscriber riêng.

Khi vượt qua ranh giới dịch vụ, cần quyết định rõ:

| Vấn đề | Quyết định phải ghi thành hợp đồng |
|---|---|
| **Event contract** | Tên sự kiện, phiên bản schema, trường bắt buộc, quy tắc tương thích |
| **Delivery** | Ack khi nào, điều kiện redelivery, retry tại ứng dụng hay broker |
| **Durability** | Broker, database và message store nào giữ dữ liệu qua restart |
| **Ordering** | Thứ tự bắt buộc theo khóa nào, partition hoặc queue nào bảo toàn được |
| **Deduplication** | Khóa idempotency, thời hạn giữ khóa, xử lý bản sao |
| **Correlation** | `orderId`, `correlationId`, `traceId` đi qua các adapter thế nào |
| **Consistency** | Làm gì khi database commit nhưng publish event thất bại, hoặc ngược lại |
| **Failure recovery** | DLQ, replay, cảnh báo, quy trình bù trừ và trách nhiệm xử lý |

Với nghiệp vụ ghi database rồi phát sự kiện, cân nhắc **transactional outbox** để giảm rủi ro mất sự kiện tại ranh giới commit/publish. Với một chuỗi thao tác trải qua nhiều dịch vụ, tìm hiểu **saga/compensation** thay vì kỳ vọng một transaction database duy nhất ôm toàn bộ flow.

**Điểm cần phân biệt:** broker và Spring Integration giúp triển khai truyền thông điệp, nhưng không tự bảo đảm *exactly-once* cho mọi tác dụng phụ ở database, HTTP hoặc hệ thống thanh toán. Thực hành thực tế thường kết hợp at-least-once delivery, idempotency và cơ chế kiểm soát dữ liệu.

Đầu ra của chặng này là hai ứng dụng chạy riêng: API phát order event và worker nhận/xử lý. Thử dừng worker trong khi producer vẫn phát message, khởi động lại rồi kiểm tra số order thực sự hoàn tất, số lần redelivery và số kết quả trùng.

## 9. Chặng 7: test và quan sát toàn bộ nhánh

Kiểm thử EIP nên được xây quanh **đường đi thông điệp** và **trạng thái quan sát được**. Spring Integration cung cấp công cụ test giúp thay thế hoặc theo dõi endpoint; với flow có broker cần thêm integration test thực sự khởi chạy adapter và hạ tầng tương ứng.

| Nhóm test | Input/kích thích | Điều kiện PASS |
|---|---|---|
| Filter | Order thiếu ID, amount không dương | Không tới handler xử lý; có nhánh loại bỏ |
| Transformer | Region có khoảng trắng/chữ thường | Region chuẩn hóa, các trường nghiệp vụ giữ đúng |
| Router | VN, quốc tế, giá trị chưa biết | Tới đúng channel theo quy tắc; nhánh mặc định rõ ràng |
| Split/Aggregate | Hai order đan xen, số phần khác nhau | Kết quả nhóm đúng correlation, không trộn dữ liệu |
| Timeout | Thiếu một phần của nhóm | Có chính sách timeout/release hoặc lỗi đo được |
| Retry | Lỗi tạm thời rồi thành công | Đúng số lần thử, không tạo tác dụng phụ trùng |
| Error channel | Lỗi tại endpoint bất đồng bộ | ErrorMessage có context và được xử lý |
| Broker | Worker restart, message redelivery | Không mất order đã cam kết; duplicate được kiểm soát |
| Load | Tăng tốc producer vượt consumer | Có số đo backlog, latency và hành vi quá tải dự kiến |

Tối thiểu mỗi message nên có thông tin phục vụ truy vết: `orderId` (khóa nghiệp vụ), `correlationId` (nhóm xử lý), `traceId` (theo dõi xuyên dịch vụ), loại event và trạng thái xử lý. Với mỗi endpoint, theo dõi **số message nhận/xử lý/lỗi**, **thời gian xử lý**, **backlog**, **retry** và **timeout**. Dùng Micrometer/observability khi tích hợp với Spring Boot và hệ thống quan sát phù hợp; kiểm tra cấu hình instrumentation và propagation tại từng adapter.

Khi điều tra một order thất bại, người vận hành cần lần được đường đi **Gateway → Filter → Router → Splitter → Worker → Aggregator hoặc Error**, kèm lý do chọn nhánh và các lần thử lại. Chỉ log payload đầy đủ thường vừa thiếu context vừa có nguy cơ lộ dữ liệu; nên ưu tiên định danh, trạng thái và trường chẩn đoán cần thiết.

## 10. Bài thực hành tổng kết

Xây dựng một hệ thống **Order Processing Integration Flow** theo hai giai đoạn.

**Giai đoạn A — một ứng dụng:**

1. Gateway nhận `OrderPlaced(orderId, customerId, region, lines)`.
2. Filter loại dữ liệu sai và ghi lý do vào nhánh invalid.
3. Transformer chuẩn hóa mã vùng và từng dòng hàng.
4. Router chọn luồng nội địa hoặc quốc tế.
5. Splitter tách các `lines`; xử lý độc lập rồi Aggregator gộp theo `orderId`, có timeout rõ ràng.
6. Một bước gọi dịch vụ giả lập lỗi tạm thời để thực hành retry và error channel.

**Giai đoạn B — hai ứng dụng:** thay ranh giới giữa nhận order và xử lý bằng broker; chạy nhiều worker, giữ correlation/idempotency; triển khai thử nghiệm restart, redelivery, backlog và quan sát qua metrics/traces.

Chỉ coi bài tập hoàn tất khi bạn trả lời được bằng log, test hoặc số đo:

- Một order hợp lệ đã đi qua những endpoint nào, vì sao Router chọn nhánh đó?
- Với hai order xử lý đan xen, Aggregator có gộp đúng nhóm không?
- Nếu một dòng hàng lỗi hoặc tới muộn, kết quả cuối cùng là gì?
- Nếu message bị gửi lại, nghiệp vụ có bị ghi/trừ tiền hai lần không?
- Nếu worker ngừng hoạt động, dữ liệu nào còn trong broker/store và khôi phục ra sao?
- Khi tăng tải, điểm nghẽn và giới hạn hàng đợi nằm ở đâu?

## 11. Các sai lầm thường gặp khi đi lên phân tán

**Đưa mọi thứ lên broker quá sớm.** Khi chưa xác định payload, header, contract và điều kiện phát kết quả, broker chỉ làm vấn đề khó quan sát hơn. Hãy làm rõ flow cục bộ trước, rồi đặt ranh giới phân tán tại nơi thật sự cần tách vòng đời hoặc mở rộng độc lập.

**Cho rằng bất đồng bộ đồng nghĩa với bền vững.** Executor hoặc queue trong bộ nhớ không tự bảo toàn message sau restart. Tính bền vững phụ thuộc vào store, broker và chính sách ack/transaction.

**Không giữ correlation khi split/aggregate.** Khi qua service khác, các headers có thể bị thiếu hoặc đổi biểu diễn. Hãy định nghĩa rõ khóa tương quan và kiểm thử end-to-end.

**Retry mọi lỗi và không có idempotency.** Retry nghiệp vụ đã thành công nhưng không nhận được phản hồi có thể gây tác dụng phụ trùng. Hãy phân loại lỗi, giới hạn retry, xác định khóa chống trùng và có nơi nhận thất bại cuối cùng.

**Chỉ kiểm tra happy path.** Một flow có nhiều nhánh cần test cho discard, default route, message đến muộn, timeout, worker restart và redelivery. Quan sát từng nhánh phải là một phần tiêu chí hoàn thành.

## 12. Thứ tự đào sâu tiếp theo

Sau bài nhập môn, học theo chuỗi **Channel/Gateway → Filter/Transformer/Router → Splitter/Aggregator/Correlation → Executor/Queue/Poller → Retry/Error Channel → Broker Adapters → Testing/Observability**. Ở mỗi chủ đề, giữ cùng một bài toán order để so sánh được hành vi trước và sau khi thêm pattern.

Mốc trưởng thành của một flow không nằm ở số pattern đã dùng mà ở khả năng chứng minh **dữ liệu đến đúng nơi, xử lý đúng nhóm, chịu lỗi có kiểm soát và quan sát được khi hệ thống mở rộng qua nhiều tiến trình**.
