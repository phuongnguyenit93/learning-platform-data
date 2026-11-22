# Lựa chọn kiểu tích hợp theo yêu cầu nhất quán và mức độ phụ thuộc

## 1. Bài toán lựa chọn trong Spring Boot Integration

Trong một hệ thống **Spring Boot Integration**, ứng dụng thường cần kết nối HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter của Spring Integration. Khi thiết kế một luồng như **đặt hàng → giữ tồn kho → thanh toán → cập nhật tìm kiếm → gửi email**, chọn công nghệ chỉ là bước sau. Câu hỏi quan trọng hơn là: **bước nào cần thấy kết quả ngay, trạng thái nào phải đúng cùng lúc và các dịch vụ được phép phụ thuộc vào nhau đến mức nào?**

Ví dụ, khi khách bấm “Đặt hàng”, hệ thống có thể:

- Cần trả lời ngay rằng **đã tiếp nhận yêu cầu**.
- Chưa thể khẳng định **đã thanh toán** nếu cổng thanh toán chưa xác nhận.
- Phải bảo đảm **một sản phẩm không bị bán vượt số lượng được quản lý bởi dịch vụ tồn kho**.
- Cho phép email xác nhận và chỉ mục tìm kiếm cập nhật **sau một khoảng trễ có kiểm soát**.

Nếu dùng lời gọi HTTP nối tiếp cho mọi bước, một SMTP chậm có thể khiến toàn bộ yêu cầu đặt hàng chậm theo. Nếu đưa toàn bộ vào message queue mà không xác định trạng thái trung gian, giao diện lại có thể báo “thành công” khi thao tác quan trọng vẫn chưa hoàn tất. Vì vậy, lựa chọn đúng là lựa chọn dựa trên **ràng buộc nghiệp vụ và đặc tính lỗi**, không dựa trên việc công nghệ nào “hiện đại” hơn.

Sau bài này, bạn cần phân biệt được **nhất quán mạnh và nhất quán cuối cùng**, các dạng **phụ thuộc giữa thành phần**, so sánh các kiểu tích hợp phổ biến, và đưa ra quyết định có kiểm chứng bằng yêu cầu độ trễ, độ tin cậy, khối lượng và khả năng phục hồi.

## 2. Hiểu chính xác yêu cầu nhất quán

**Nhất quán dữ liệu (consistency)** trả lời câu hỏi: *khi nào các bên tham gia phải cùng nhìn thấy một trạng thái hợp lệ, và sai lệch tạm thời nào được phép xảy ra?* Không nên dùng một nhãn “strong consistency” cho toàn bộ hệ thống nếu mỗi luồng có yêu cầu khác nhau.

| Mức yêu cầu | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| **Bất biến phải đúng ngay trong một giao dịch** | Các thay đổi dữ liệu liên quan phải cùng thành công hoặc cùng thất bại trong **ranh giới giao dịch sở hữu dữ liệu**. | Trừ số lượng khả dụng và tạo bản ghi giữ hàng trong cùng cơ sở dữ liệu Inventory. |
| **Kết quả cần biết trước khi trả lời** | Người gọi chờ kết quả của một thao tác bên ngoài. Điều này bảo đảm tính kịp thời của **phản hồi**, nhưng không tự tạo giao dịch ACID xuyên dịch vụ. | Gọi HTTP sang Inventory để hỏi giữ hàng thành công hay bị từ chối. |
| **Nhất quán cuối cùng (eventual consistency)** | Các bản sao/đối tượng đọc có thể lệch tạm thời; nếu các cập nhật được truyền và xử lý thành công, chúng hội tụ về trạng thái phù hợp. | Search index nhận sự kiện `ProductUpdated` muộn vài giây. |
| **Chấp nhận dữ liệu ảnh chụp theo kỳ** | Dữ liệu được làm mới tại các mốc hoặc lô có lịch biểu. | Kho báo cáo cập nhật mỗi đêm. |

### 2.1. Bất biến nghiệp vụ khác với việc “có phản hồi HTTP”

Giả sử Inventory xử lý lệnh giữ hàng trong một transaction:

1. Kiểm tra số lượng khả dụng.
2. Ghi số lượng đã giữ và bản ghi `reservationId`.
3. Commit hoặc rollback cùng nhau.

Đó là bất biến **nội bộ Inventory**. Nếu Order gọi Inventory qua REST và nhận `200 OK`, Order biết Inventory đã báo thành công theo hợp đồng API; **giao dịch tại Order không tự động nằm chung transaction với Inventory**. Khi mạng đứt sau lúc Inventory commit nhưng trước khi Order nhận phản hồi, trạng thái có thể đã thay đổi dù phía gọi thấy timeout.

Trường hợp này cần **idempotency key**, API tra cứu kết quả theo mã yêu cầu hoặc luồng đối soát. Retry mù với một yêu cầu mới có thể giữ hàng hai lần. Ngay cả khi dùng HTTP đồng bộ, không thể xem timeout là bằng chứng rằng phía nhận **chưa** thực thi.

### 2.2. Nhất quán cuối cùng phải có giới hạn đo được

“Cập nhật sau” chưa phải là yêu cầu đủ rõ. Hãy nêu:

- **Nguồn sự thật (system of record)**: bên nào sở hữu trạng thái chính thức?
- **Độ trễ cho phép**: ví dụ, 99% thay đổi hiển thị ở Search trong vòng 5 giây, đây là mục tiêu minh họa cần được thỏa thuận theo sản phẩm.
- **Hành vi trong lúc chờ**: hiển thị “Đang xử lý”, dùng dữ liệu cũ có nhãn thời điểm, hoặc đọc trực tiếp từ nguồn chính.
- **Cách phục hồi**: retry, dead-letter queue (DLQ), replay, đối soát và cảnh báo khi độ trễ vượt ngưỡng.
- **Quy tắc khi sự kiện đến trễ/đảo thứ tự**: kiểm tra phiên bản hoặc thứ tự cập nhật theo từng đối tượng.

Đối với thông tin ảnh hưởng quyết định tài chính, quyền truy cập hoặc số dư, đôi khi cần kiểm tra trực tiếp trạng thái đã xác nhận ở nguồn chính trước khi cho thực hiện bước tiếp theo. Một read model cập nhật bất đồng bộ không phù hợp để làm căn cứ duy nhất cho mọi quyết định quan trọng.

## 3. Hiểu mức độ phụ thuộc giữa các hệ thống

**Coupling (mức độ phụ thuộc)** không chỉ là việc hai lớp Java import nhau. Trong một hệ phân tán, cần xem ít nhất năm chiều:

| Chiều phụ thuộc | Câu hỏi đánh giá | Ví dụ |
| --- | --- | --- |
| **Thời điểm hoạt động (temporal)** | Hai bên có bắt buộc cùng hoạt động tại lúc yêu cầu đến? | HTTP đồng bộ thường cần dịch vụ đích khả dụng ngay; queue có thể giữ việc cho consumer xử lý sau. |
| **Hợp đồng và dữ liệu** | Producer biết bao nhiêu về cấu trúc, trường, phiên bản và mục đích của consumer? | Sự kiện `OrderConfirmed` được phát theo hợp đồng nghiệp vụ; consumer không nên cần biết bảng nội bộ của Order. |
| **Vị trí/giao thức** | Producer cần biết endpoint cụ thể, giao thức, địa chỉ hoặc cách xác thực của bên đích? | HTTP client cần cấu hình URL/dịch vụ đích; producer gửi broker cần địa chỉ broker và tên channel/topic. |
| **Vận hành và lỗi** | Lỗi, tốc độ hoặc thay đổi triển khai ở một bên tác động trực tiếp đến bên kia thế nào? | Một HTTP chậm kéo dài latency request; consumer chậm làm queue lag tăng. |
| **Giao dịch** | Một thao tác muốn commit có phụ thuộc việc commit của bên còn lại? | Yêu cầu transaction xuyên hai database làm tăng phối hợp, phức tạp và khả năng nghẽn. |

Messaging thường **giảm phụ thuộc đồng thời theo thời gian**, nhưng không loại bỏ mọi phụ thuộc: producer vẫn phụ thuộc vào broker, hợp đồng message, chính sách giữ dữ liệu và khả năng xử lý trùng/lỗi. Một sự kiện chứa toàn bộ schema bảng cơ sở dữ liệu cũng có thể làm các consumer phụ thuộc chặt vào cấu trúc nội bộ.

Ngoài ra, **mức độ phụ thuộc** không đồng nghĩa với **số lượng kết nối**. Một HTTP API nhỏ, ổn định, có versioning rõ ràng có thể là lựa chọn tốt hơn một pipeline sự kiện quá phức tạp khi yêu cầu thực tế chỉ là truy vấn một kết quả tức thời.

## 4. So sánh các kiểu tích hợp chính

| Kiểu tích hợp | Tính nhất quán/độ mới dữ liệu thường hướng tới | Phụ thuộc nổi bật | Phù hợp khi | Đánh đổi cần chấp nhận |
| --- | --- | --- | --- | --- |
| **Request/response đồng bộ: REST, gRPC** | Lấy câu trả lời hiện tại từ bên sở hữu dữ liệu; bản thân HTTP không bảo đảm transaction phân tán. | Phụ thuộc thời gian chạy, endpoint, SLA và hợp đồng API. | Người dùng hoặc bước nghiệp vụ cần phản hồi ngay; truy vấn hoặc ra lệnh ngắn. | Timeout, lỗi dây chuyền, giới hạn concurrency, cần idempotency khi retry. |
| **Command bất đồng bộ qua queue** | Producer ghi nhận yêu cầu; kết quả được cập nhật về sau. | Giảm yêu cầu hai dịch vụ online cùng lúc; phụ thuộc broker và hợp đồng lệnh. | Công việc có thể xếp hàng, mất thời gian hoặc cần hấp thụ tải đột biến. | Phải quản lý trạng thái `PENDING`, retry, DLQ, xử lý trùng. |
| **Event publish/subscribe** | Consumer cập nhật read model hoặc phản ứng khi sự kiện được phát; thường eventual. | Producer ít biết consumer; các bên vẫn phụ thuộc schema và ý nghĩa sự kiện. | Một sự kiện nghiệp vụ cần nhiều consumer độc lập: email, analytics, search. | Quan sát luồng khó hơn, ordering/replay/schema evolution cần thiết kế. |
| **Event streaming/log** | Lưu luồng sự kiện có thể đọc lại theo offset; consumer tự xây dựng trạng thái. | Phụ thuộc topic, partition key, retention, event contract. | Nhiều consumer, lưu lượng lớn, cần replay hoặc xử lý dòng. | Quản lý partition, lag, offset, thứ tự trong phạm vi partition và dữ liệu phát lại. |
| **Batch/file/ETL theo lịch** | Ảnh chụp trạng thái theo kỳ; độ mới ở mức phút/giờ/ngày. | Phụ thuộc định dạng, lịch trao đổi, nơi chuyển file và quy trình đối soát. | Báo cáo, hệ thống kế thừa, khối lượng lớn nhưng không yêu cầu tức thời. | Dữ liệu cũ giữa hai đợt, xử lý lại lô, kiểm tra completeness. |
| **CDC kết hợp event/outbox** | Phát thay đổi DB sau commit; consumer vẫn hội tụ bất đồng bộ. | Phụ thuộc DB/log CDC, cấu trúc outbox hoặc mô hình biến đổi sự kiện. | Cần nối transaction cập nhật dữ liệu với việc phát thông điệp đáng tin cậy. | Cần relay, theo dõi độ trễ, giải quyết phát trùng, thứ tự và lỗi. |
| **Truy cập chung database/bảng** | Có thể thấy dữ liệu mới nhanh, nhưng không tự có quyền sở hữu hay hợp đồng ổn định. | Rất chặt về schema, quyền, migration và tải DB. | Chủ yếu là hệ thống cũ có ràng buộc không thể thay ngay. | Thay schema dễ phá consumer; làm mờ ownership, bảo mật và cô lập lỗi. |
| **Giao dịch phân tán XA/2PC** | Phối hợp commit giữa các tài nguyên có hỗ trợ để đạt atomicity trong phạm vi tham gia. | Rất chặt về giao dịch, kết nối, lock và tính sẵn sàng. | Trường hợp đặc biệt có nền tảng hỗ trợ và yêu cầu atomicity không thể tái thiết kế. | Độ trễ, điều phối, xử lý lỗi/phục hồi phức tạp; không phải mặc định cho microservice. |

Đây là **các công cụ bổ trợ nhau**: một dịch vụ hoàn toàn có thể dùng REST cho thao tác cần xác nhận, outbox để công bố `OrderConfirmed`, Kafka/RabbitMQ cho consumer và batch để đối soát. Kiểu vận chuyển không tự quyết định độ tin cậy; kết quả còn phụ thuộc transaction, broker acknowledgement, retry, schema, khóa chống trùng và việc xử lý lỗi tại consumer.

### 4.1. Đồng bộ khi cần quyết định ngay

Ví dụ dịch vụ Order gọi Inventory để đặt trước hàng trong lúc xử lý request. Người dùng có thể cần thông tin “Còn hàng/Không còn hàng” ngay để hoàn tất bước hiện tại. Thiết kế cần:

- API trả về ý nghĩa nghiệp vụ rõ ràng: `RESERVED`, `REJECTED`, hoặc tình trạng chưa chắc chắn khi timeout.
- **Connect/read timeout**, giới hạn số kết nối và concurrency hợp lý; dùng circuit breaker/bulkhead khi có nguy cơ một dịch vụ làm nghẽn toàn bộ luồng.
- Idempotency key giữ nguyên qua các lần thử của **cùng một thao tác**; phía Inventory cũng phải hỗ trợ chống trùng.
- Kế hoạch phục hồi khi không biết kết quả: tra cứu `reservationId`/`requestId` hoặc bù trừ nếu phát hiện đã giữ hàng mà Order không tiếp tục.

Đừng nhầm **synchronous** với **strong consistency toàn hệ thống**. HTTP chỉ giúp chờ một phản hồi; atomicity giữa hai dịch vụ cần chiến lược riêng hoặc thiết kế lại ranh giới sở hữu dữ liệu.

### 4.2. Command bất đồng bộ khi kết quả có thể đến sau

Một command như `GenerateInvoice` gửi tới queue biểu đạt: “hãy thực hiện công việc này”. Producer có thể trả về `202 Accepted` và một mã theo dõi; consumer xử lý khi rảnh. Lệnh nên có đích nghiệp vụ và owner rõ, trạng thái được theo dõi. Một command không đồng nghĩa với event: command yêu cầu làm điều gì đó; event thông báo một sự thật **đã xảy ra**.

Không trả về “hóa đơn đã tạo” khi mới chỉ enqueue. Tùy nhu cầu, hệ thống có thể cung cấp polling `GET /jobs/{id}`, callback, webhook hoặc đẩy trạng thái qua WebSocket/SSE. Phải nêu rõ quyền truy cập vào trạng thái công việc và thời hạn lưu kết quả.

### 4.3. Event khi cần mở rộng nhiều phản ứng độc lập

Sau khi Order **đã commit** trạng thái xác nhận, nó phát `OrderConfirmed`. Email, Search, Analytics đăng ký xử lý theo nhu cầu riêng. Order không cần gọi từng consumer. Khi một consumer gặp lỗi, các consumer khác vẫn có thể tiếp tục theo cơ chế broker.

Event cần mô tả **sự kiện có ý nghĩa nghiệp vụ**, không phải chỉ phát mọi thay đổi cột SQL. Định dạng nên có `eventId`, `eventType`, `aggregateId`, phiên bản schema, thời điểm xảy ra và payload tối thiểu cần thiết; thông tin cá nhân nhạy cảm không nên truyền tràn lan.

## 5. Sơ đồ quyết định theo nhất quán và phụ thuộc

Sơ đồ dưới đây giúp bắt đầu thảo luận thiết kế. Từng nhánh vẫn phải được kiểm tra với yêu cầu giao dịch và xử lý lỗi thực tế.

~~~mermaid
flowchart TD
    A["Có cần biết kết quả trước khi phản hồi?"] -->|Có| B{"Bất biến dữ liệu phải atomic?"}
    B -->|"Trong một owner"| C["Giữ thao tác trong một transaction cục bộ"]
    B -->|"Qua nhiều owner"| D["Xem lại ranh giới dữ liệu, saga hoặc phối hợp đặc biệt"]
    C --> E["Nếu cần bên ngoài: request/response có timeout, idempotency"]
    D --> E
    A -->|Không| F{"Một hay nhiều nơi cần xử lý?"}
    F -->|"Một owner thực hiện"| G["Queue command và trạng thái PENDING"]
    F -->|"Nhiều subscriber"| H["Publish event sau commit; pub/sub hoặc streaming"]
    H --> I{"Cần tránh mất event giữa DB và broker?"}
    G --> I
    I -->|Có| J["Transactional outbox + relay + dedupe consumer"]
    I -->|Không| K["Đánh giá lại cam kết mất mát/khôi phục"]
    A -->|"Dữ liệu chỉ cần theo kỳ"| L["Batch/ETL với đối soát"]
~~~

Trước khi quyết định, hãy hỏi người phụ trách nghiệp vụ những câu cụ thể:

1. **Bất biến nào tuyệt đối không được vi phạm?** Ai là owner duy nhất có quyền thực thi?
2. **Có được trả `PENDING`?** Nếu có, trong bao lâu và người dùng xem kết quả ở đâu?
3. **Khi đối tác mất kết nối, có được tiếp nhận yêu cầu không?** Hệ thống sẽ lưu lệnh ở đâu?
4. **Mất một thông điệp hay xử lý trùng có hậu quả gì?** Có thể bù trừ/đối soát không?
5. **Cần đọc dữ liệu mới trong bao lâu?** Tính theo phần trăm, trạng thái cực đại và hành vi khi vi phạm.
6. **Sẽ có bao nhiêu consumer và tần suất thay đổi hợp đồng?** Ai kiểm soát tương thích ngược?
7. **Tải bình thường và đột biến ra sao?** Cần backpressure, queue hay batch?

Một quyết định có giá trị khi gắn với số đo, ví dụ “giữ hàng phản hồi trong ngưỡng latency đã thỏa thuận ở phần lớn request”, “email được gửi trong vài phút” hoặc “Search lag được cảnh báo khi vượt SLO”. Các con số phải đo theo nhu cầu và điều kiện vận hành thực tế, không sao chép máy móc từ ví dụ.

## 6. Ví dụ xuyên suốt: tích hợp hệ thống đặt hàng

Giả sử có bốn bounded context: `Order` (sở hữu trạng thái đơn), `Inventory` (sở hữu tồn kho), `Payment` (quản lý thanh toán với nhà cung cấp), và `Notification/Search` (cập nhật dữ liệu dẫn xuất).

~~~mermaid
flowchart LR
    U["Người dùng"] --> O["Order API"]
    O -->|"HTTP reserve / trả lời ngay"| I["Inventory"]
    O -->|"Transaction: Order + outbox"| DB[("Order DB")]
    DB --> R["Outbox relay"]
    R --> MQ[("Broker")]
    MQ -->|"OrderConfirmed"| N["Notification"]
    MQ -->|"OrderConfirmed"| S["Search read model"]
    O <-->|"Payment request/result hoặc trạng thái PENDING"| P["Payment"]
~~~

| Bước | Nhất quán được yêu cầu | Kiểu tích hợp hợp lý | Nếu lỗi |
| --- | --- | --- | --- |
| Giữ hàng | Inventory không cho giữ vượt số lượng hiện có; giao diện muốn biết kết quả sớm. | Transaction trong Inventory; Order gọi HTTP đồng bộ và dùng idempotency key. | Timeout phải tra cứu trạng thái hoặc thực hiện bù trừ đúng quy trình. |
| Tiếp nhận đơn | Order tạo bản ghi `PENDING` bền vững và trả mã đơn. | Giao dịch cục bộ ở Order. | Không trả trạng thái hoàn tất khi chưa commit. |
| Thanh toán | Không được đánh dấu `PAID` khi chưa có xác nhận đáng tin cậy; callback có thể chậm hoặc lặp. | Gọi API đồng bộ nếu cần chuyển trạng thái ngay; callback/event và đối soát để chốt kết quả cuối. | Giữ `PAYMENT_PENDING` hoặc trạng thái cần xác minh, không suy thất bại từ timeout. |
| Gửi email | Không được mất thông báo quan trọng nhưng cho phép trễ. | `OrderConfirmed` qua outbox + broker + consumer email. | Retry có backoff, DLQ, tra cứu và xử lý trùng. |
| Cập nhật Search | Chỉ mục có thể chậm; Order vẫn là nguồn sự thật. | Event streaming/pub-sub đến consumer cập nhật read model. | Kiểm soát thứ tự/phiên bản, đo lag và rebuild khi cần. |
| Báo cáo ngày | Không cần realtime từng giao dịch. | Batch/ETL theo lịch và đối soát tổng hợp. | Chạy lại lô theo khóa/id, kiểm tra tổng số bản ghi và số tiền. |

Một luồng đáng tin cậy không nhất thiết cố giữ toàn bộ Order + Inventory + Payment + SMTP trong **một transaction phân tán**. Với các bước kéo dài hoặc có hệ thống ngoài tổ chức, một **saga** có trạng thái trung gian và hành động bù trừ thường phù hợp hơn:

- Giữ hàng thành công nhưng thanh toán thất bại: phát lệnh hủy reservation theo một `reservationId` xác định.
- Thanh toán có kết quả chưa rõ: kiểm tra với nhà cung cấp theo idempotency key trước khi quyết định thu tiền lại.
- Hoàn tiền là một **giao dịch nghiệp vụ bù trừ**, không phải rollback tức thời của giao dịch thu tiền đã hoàn tất.
- Nếu timeout khi gọi hủy giữ hàng, cần theo dõi việc hủy cho tới khi có kết quả xác nhận hoặc một cơ chế hết hạn reservation.

## 7. Triển khai điểm tích hợp đồng bộ trong Spring Boot

Spring Boot 3.2+ hỗ trợ `RestClient` để gọi HTTP theo kiểu đồng bộ. Ví dụ sau minh họa lời gọi Inventory; URL và timeout chỉ là giá trị ví dụ, cần chọn theo latency budget và khả năng của đối tác.

~~~java
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class InventoryHttpConfig {
    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String baseUrl) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1_000);
        factory.setReadTimeout(1_500);
        return builder.requestFactory(factory)
                .baseUrl(baseUrl)
                .build();
    }
}

record ReserveStock(
        UUID orderId, UUID orderLineId, String sku, int quantity) {}

record ReservationReply(String reservationId, boolean accepted) {}

class InventoryClient {
    private final RestClient client;

    InventoryClient(RestClient inventoryRestClient) {
        this.client = inventoryRestClient;
    }

    ReservationReply reserve(ReserveStock request) {
        String key = request.orderId() + ":reserve:" + request.orderLineId();
        return client.post()
                .uri("/reservations")
                .header("Idempotency-Key", key)
                .body(request)
                .retrieve()
                .body(ReservationReply.class);
    }
}
~~~

Ứng dụng phải xử lý rõ trường hợp `.body(...)` trả `null`, phản hồi `4xx/5xx` và ngoại lệ I/O; không mặc định mọi lỗi đều có thể retry. Mã từ chối nghiệp vụ (hết hàng) khác lỗi mạng. **Idempotency-Key** chỉ phát huy tác dụng nếu Inventory lưu và tái sử dụng kết quả cho cùng khóa/phạm vi, có quy định thời gian lưu và xử lý xung đột payload. Phía gọi phải giữ nguyên khóa khi retry cùng thao tác.

Để không biến một điểm lỗi thành lỗi dây chuyền, cần cấu hình timeout, giới hạn connection pool hoặc concurrency, theo dõi tỷ lệ timeout và phân bổ latency budget từ API bên ngoài vào các bước nội bộ. Với luồng gọi dài hoặc tải đồng thời lớn, có thể dùng `WebClient` và lập trình reactive, nhưng tính reactive **không thay đổi** bản chất phụ thuộc vào kết quả phản hồi.

## 8. Phát sự kiện sau commit: transactional outbox

Vấn đề phổ biến là **dual write**:

~~~text
1. Commit đơn hàng vào database.
2. Publish OrderConfirmed lên broker.
~~~

Nếu tiến trình chết giữa hai bước, Order đã commit nhưng không có sự kiện. Đảo thứ tự hai bước cũng không an toàn: broker nhận event trước khi database commit; transaction DB có thể rollback sau đó.

**Transactional outbox** khắc phục khoảng hở này bằng cách ghi **dữ liệu nghiệp vụ và bản ghi outbox trong cùng một transaction của một database**:

~~~sql
BEGIN;

INSERT INTO orders (id, customer_id, status)
VALUES (:orderId, :customerId, 'CONFIRMED');

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, schema_version, payload_json, created_at)
VALUES
    (:eventId, :orderId, 'OrderConfirmed', 1, :payloadJson, CURRENT_TIMESTAMP);

COMMIT;
~~~

Đây là SQL minh họa với named parameters, giả định các bảng và ràng buộc đã được định nghĩa. Trong Spring Boot có thể dùng `@Transactional` để ghi Order và Outbox thông qua cùng transaction manager/datasource. Sau commit, một relay đọc outbox và publish lên broker; relay có thể chạy polling hoặc dùng CDC trên bảng outbox.

~~~mermaid
sequenceDiagram
    participant API as Order Service
    participant DB as Order DB
    participant Relay as Outbox Relay
    participant Broker as Broker
    participant Consumer as Search Consumer
    API->>DB: Transaction: update Order + insert Outbox
    DB-->>API: Commit
    Relay->>DB: Đọc event chưa phát
    DB-->>Relay: OrderConfirmed
    Relay->>Broker: Publish event
    Broker-->>Relay: Ack theo cơ chế broker
    Relay->>DB: Đánh dấu đã phát
    Broker->>Consumer: Giao event
    Consumer->>Consumer: Xử lý idempotent
~~~

Đặc điểm cần ghi nhớ:

- Outbox bảo đảm **bản ghi dự kiến phát event nằm trong cùng commit** với thay đổi Order; nó **không** bảo đảm publisher chỉ phát đúng một lần.
- Nếu relay publish thành công rồi chết trước khi đánh dấu đã phát, event có thể được gửi lại. Consumer phải xử lý trùng.
- Nếu nhiều relay hoặc nhiều aggregate, cần cơ chế claim/lock, quản lý retry và bảo đảm thứ tự phù hợp theo **aggregate key**, khi nghiệp vụ yêu cầu.
- Outbox không thay thế xác nhận broker đã lưu bền vững; cấu hình publish confirm/ack tương ứng với công nghệ broker và không đánh dấu đã phát trước khi có xác nhận cần thiết.
- Cần theo dõi tuổi bản ghi outbox lâu nhất chưa phát, số lần retry, tỷ lệ lỗi publish và chính sách dọn dữ liệu sau khi đã bảo đảm khả năng đối soát.

### 8.1. Hợp đồng sự kiện và tương thích phiên bản

Ví dụ hợp đồng `OrderConfirmed`:

~~~json
{
  "eventId": "a3d5a426-ef0a-4e82-a5dd-2c1ef303c7c9",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "aggregateId": "o-123",
  "occurredAt": "2026-11-20T03:30:00Z",
  "payload": {
    "orderId": "o-123",
    "customerId": "c-456"
  }
}
~~~

Event phải phản ánh sự thật đã xảy ra và có ID duy nhất cho việc dedupe. Khi thay đổi schema, ưu tiên thêm trường tùy chọn, giữ ý nghĩa trường cũ và kiểm thử compatibility với consumer hiện có. Với thay đổi phá vỡ hợp đồng, cần lên kế hoạch nâng phiên bản và chuyển đổi consumer. Timestamp giúp quan sát, nhưng **không đủ** để bảo đảm thứ tự tuyệt đối giữa các producer; nên bổ sung version tăng dần theo aggregate nếu logic consumer phụ thuộc thứ tự.

### 8.2. Idempotent consumer và kết quả “effectively once”

Nhiều broker hoạt động với cơ chế **at-least-once delivery** khi có retry; nhận trùng là điều bình thường. Một cách kiểm soát là tạo bảng inbox có unique key trên `(consumer_name, event_id)`, rồi thực hiện **ghi dấu đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction cục bộ**.

Ví dụ tư duy xử lý với PostgreSQL:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (consumer_name, event_id)
VALUES ('search-indexer', :eventId)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Chỉ khi INSERT thực sự thêm 1 dòng:
--   cập nhật dữ liệu cục bộ hoặc tạo tác vụ index tương ứng.
-- Nếu có 0 dòng: event đã được nhận trước đó, bỏ qua tác dụng lặp.

COMMIT;
~~~

Trong mã chạy thực tế, kiểm tra số hàng được thêm và đặt logic cập nhật cùng transaction; định nghĩa unique constraint trong database. Nếu tác dụng cuối là một hệ thống **ngoài** transaction đó (ví dụ gửi email), inbox cục bộ chưa tự bảo đảm chỉ gửi đúng một email: cần thêm idempotency ở đích, trạng thái gửi và cơ chế đối soát theo khóa ổn định. Nên nói **“xử lý tác dụng nghiệp vụ đúng một lần trong phạm vi ràng buộc được thiết kế”** thay vì mặc định mọi broker đem lại exactly-once end-to-end.

## 9. Spring Integration trong bức tranh lựa chọn

**Spring Integration** cung cấp các mẫu Enterprise Integration Patterns như `MessageChannel`, `Gateway`, `Transformer`, `Router`, `Filter`, `Service Activator` và adapter cho hệ thống bên ngoài. Chúng giúp chia xử lý thành các bước có hợp đồng rõ, gắn các endpoint và quan sát luồng.

Chẳng hạn, một sự kiện từ broker có thể đi qua:

~~~mermaid
flowchart LR
    A["Inbound broker adapter"] --> B["MessageChannel"]
    B --> C["Filter schema/version"]
    C --> D["Transformer sang command nội bộ"]
    D --> E["Service Activator"]
    E --> F[("Database / SMTP / API")]
    C -->|"không hợp lệ"| X["Error channel / DLQ policy"]
~~~

Tuy nhiên, các pattern như channel hay router **không tự biến hai database thành một giao dịch**. Cần xem rõ:

- Điểm bắt đầu và kết thúc transaction tại inbound adapter, xử lý dữ liệu và ack broker.
- Hành vi `retry`, `errorChannel`, DLQ và khả năng xử lý một message nhiều lần.
- Channel đồng bộ hay bất đồng bộ: `DirectChannel` gọi handler trong cùng call stack, còn `ExecutorChannel` chuyển công việc sang executor; thay đổi này ảnh hưởng ngữ cảnh transaction/thread.
- Message header như correlation ID, trace ID, tenant và version cần được quản lý rõ ràng, tránh gửi dữ liệu nhạy cảm không cần thiết.

Tương tự, sử dụng cache như Redis để tăng tốc đọc **không làm dữ liệu tự nhiên nhất quán** với database. Phải chọn cache-aside, write-through hoặc cơ chế invalidation, TTL và chính sách làm mới phù hợp với độ cũ chấp nhận được. Cache không nên là căn cứ duy nhất cho bất biến quan trọng nếu không có thiết kế đồng bộ phù hợp.

## 10. Các tình huống hỏng cần thiết kế trước

| Tình huống | Kiểu tích hợp bị ảnh hưởng | Cách ứng phó |
| --- | --- | --- |
| HTTP timeout **sau khi** bên nhận đã commit | Request/response | Dùng idempotency key, API tra cứu trạng thái, đối soát trước retry. |
| Một dependency chậm làm cạn worker/thread | HTTP, JDBC | Timeout, connection pool, bulkhead, circuit breaker; theo dõi timeout và saturation. |
| Broker tạm ngừng | Queue, pub/sub, streaming | Durable storage/buffer theo khả năng, outbox, retry với backoff, theo dõi backlog. |
| Message được giao nhiều lần | Queue, pub/sub, streaming | Dedupe theo event ID và transaction cục bộ, thiết kế handler idempotent. |
| Message đến không đúng thứ tự | Nhiều consumer, partition, retry | Key/partition phù hợp, version theo aggregate, bỏ qua cập nhật cũ hoặc đối soát. |
| Consumer không đọc được schema mới | Event/API contract | Contract tests, compatibility rule, versioning và rollout có thứ tự. |
| Search/cache chậm cập nhật | Read model/cache | Lag metric, TTL/invalidation, đọc từ source of truth khi bắt buộc mới nhất. |
| Batch chạy lại hoặc chạy một nửa | Batch/ETL | Checkpoint, idempotent upsert, khóa lô, kiểm tra số dòng/tổng và ghi lỗi từng phần. |
| Saga bị kẹt giữa các bước | Orchestration/choreography | Timeout nghiệp vụ, retry, compensating action, cảnh báo và công cụ can thiệp thủ công. |

Khi đánh giá kiến trúc, đừng chỉ thử đường thành công. Các lỗi giữa những bước đã commit và chưa commit mới thể hiện rõ ràng buộc phụ thuộc và giới hạn nhất quán thực tế.

## 11. Kiểm thử, quan sát và tiêu chí chấp nhận

Một lựa chọn tích hợp tốt phải kiểm chứng được bằng dữ liệu vận hành. Các nhóm chỉ số nên gồm:

- **Đồng bộ**: độ trễ p95/p99, timeout rate, lỗi theo mã HTTP/nghiệp vụ, tỷ lệ retry, connection pool saturation và số request chờ.
- **Messaging**: độ sâu queue, consumer lag, độ tuổi message/outbox lớn nhất, số lần redelivery, retry, DLQ, tỷ lệ duplicate và thời gian đến trạng thái hoàn tất.
- **Dữ liệu**: số bản ghi lệch khi đối soát, độ trễ read model, số lỗi schema/serialization và số cập nhật bị bỏ qua do version cũ.
- **Nghiệp vụ**: tỷ lệ Order ở `PENDING` quá hạn, reservation chưa được giải phóng, thanh toán chưa đối soát và email không được gửi trong ngưỡng cam kết.

Kết hợp trace ID/correlation ID xuyên HTTP, outbox và broker, nhưng phân biệt **request ID**, **operation idempotency key**, **event ID** và **aggregate ID**: chúng có vòng đời và mục đích khác nhau. Metric và log nên cho phép tìm từ mã đơn tới toàn bộ chuỗi xử lý mà không ghi thẻ thanh toán, token hoặc nội dung bí mật.

Các ca kiểm thử có giá trị cao:

1. **Mất phản hồi sau commit từ Inventory**: gọi lại với cùng idempotency key không giữ hai lần.
2. **Order commit, relay chết trước publish**: khởi động lại thì event vẫn được phát.
3. **Publish thành công, relay chết trước ghi nhận hoàn tất**: event có thể lặp nhưng consumer không tạo tác dụng lặp.
4. **Consumer nhận event mới trước event cũ**: read model không bị ghi đè bằng version thấp.
5. **Broker dừng vài phút**: yêu cầu vẫn giữ đúng trạng thái đã cam kết; backlog được xử lý sau khi broker phục hồi.
6. **Thay đổi schema**: consumer cũ vẫn xử lý bản tin theo chính sách tương thích đã thống nhất.
7. **Batch chạy lại**: số liệu tổng hợp không bị nhân đôi, có kết quả đối soát.

Các bài kiểm thử cần bao gồm lỗi mạng, crash process, message trùng và transaction rollback; mock một phương thức trả `true` chưa chứng minh được bảo đảm của giao thức hoặc database.

## 12. Tổng hợp cách chọn

Đầu tiên, **xác định bất biến** và đặt các thay đổi cần atomicity dưới một owner cùng ranh giới transaction khi có thể. Tiếp theo, xác định **thời gian người dùng phải biết kết quả**: nếu cần ngay, dùng request/response có timeout và idempotency; nếu chờ được, command bất đồng bộ với trạng thái theo dõi giúp giảm phụ thuộc thời gian. Nếu nhiều bên cần phản ứng với một sự thật nghiệp vụ đã commit, dùng **event** với contract ổn định. Nếu cần bảo đảm sự kiện không thất lạc giữa database và broker, áp dụng **outbox** và consumer idempotent. Khi độ mới dữ liệu chỉ cần theo kỳ, **batch** đơn giản có thể hợp lý hơn streaming liên tục.

Sau khi chọn kiểu tích hợp, còn phải thiết kế **hợp đồng dữ liệu, transaction, retry, trùng lặp, lỗi, observability và phép thử phục hồi**. Những quyết định này mới xác định hệ thống Spring Boot duy trì nhất quán ở mức được yêu cầu và giảm được mức độ phụ thuộc thực sự trong vận hành.
