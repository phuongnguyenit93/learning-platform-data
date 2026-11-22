# Kiểm tra tác dụng phụ và chi phí bảo trì phát sinh

Một thay đổi có thể làm test hiện tại xanh nhưng đồng thời tạo thêm một cuộc gọi mạng, kéo dài thời gian giữ transaction, làm phát sinh retry, tăng số cấu hình phải quản lý hoặc buộc một nhóm khác cập nhật consumer. Những hệ quả này đôi khi không xuất hiện trong diff chính, nhưng lại quyết định hệ thống có còn dễ vận hành và thay đổi sau khi merge hay không.

**Tác dụng phụ (side effect)** là ảnh hưởng của một thao tác vượt ra ngoài việc tính toán và trả về kết quả, chẳng hạn ghi database, gửi message, thay đổi cache, ghi log, tạo file hoặc gọi dịch vụ khác. Tác dụng phụ là một phần bình thường của phần mềm. Điều cần kiểm tra là chúng có đúng với hợp đồng, xảy ra đúng thời điểm, có thể kiểm soát khi lỗi và có tạo ra chi phí bảo trì tương xứng hay không.

Bài học thuộc chương **Cải thiện liên tục** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module — hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không** — bài này hướng dẫn lập bản đồ tác động của một thay đổi, phát hiện hệ quả ngoài dự kiến, đánh giá chi phí bảo trì mới phát sinh, kiểm chứng trước và sau triển khai, rồi dùng kết quả để cải thiện cách phát triển.

## 1. Tác dụng phụ là gì và vì sao cần kiểm tra?

Một phép tính thuần nhận đầu vào và trả kết quả mà không thay đổi trạng thái bên ngoài. Ví dụ:

~~~java
static long discountVnd(long subtotalVnd) {
    return subtotalVnd >= 500_000L ? subtotalVnd / 10L : 0L;
}
~~~

Với cùng đầu vào, hàm trả cùng kết quả và không ghi dữ liệu, gửi mạng hay thay đổi state dùng chung.

Một thao tác có tác dụng phụ có thể:
- Lưu hoặc cập nhật bản ghi.
- Gửi email, SMS hoặc thông báo push.
- Phát event lên message broker.
- Ghi log hoặc audit record.
- Thay đổi cache, file hoặc trạng thái tiến trình.
- Gọi API thanh toán, vận chuyển hoặc xác thực.
- Lấy lock, mở connection hoặc tiêu thụ tài nguyên.
- Thay đổi quyền, cấu hình hoặc trạng thái của một đối tượng được chia sẻ.

Tác dụng phụ không mặc nhiên xấu. Ứng dụng cần ghi đơn hàng và gửi thông báo để thực hiện nghiệp vụ. Vấn đề xuất hiện khi một thay đổi làm **tác dụng phụ mới không được dự kiến, sai thứ tự, khó phục hồi, khó kiểm thử hoặc không có người chịu trách nhiệm**.

### 1.1. Phân biệt kết quả trực tiếp và hệ quả lan truyền

Một thay đổi thường có nhiều lớp kết quả:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Kết quả trực tiếp** | Hàm hoặc API trả gì? | Trả về mã đơn hàng |
| **Trạng thái bền vững** | Dữ liệu nào được ghi? | Một bản ghi đơn hàng được commit |
| **Tác dụng phụ bên ngoài** | Hệ thống khác nhận gì? | Event đơn hàng được phát |
| **Thời gian và thứ tự** | Việc gì xảy ra trước/sau? | Gửi email sau khi đơn được commit |
| **Tài nguyên** | Dùng thêm gì? | Một HTTP call và một connection |
| **Vận hành** | Cần theo dõi và xử lý gì? | Retry, dead-letter queue, cảnh báo |
| **Bảo trì** | Ai phải thay đổi khi hợp đồng đổi? | Team notification cập nhật consumer |

Một test chỉ kiểm tra giá trị trả về có thể không phát hiện email được gửi hai lần hoặc event được phát trước khi transaction commit. Vì vậy, cần xem **hành vi quan sát được của toàn luồng**, không chỉ kết quả của một method.

## 2. Các nhóm tác dụng phụ cần xem xét

### 2.1. Thay đổi trạng thái và dữ liệu

- Insert, update, delete trong database.
- Cập nhật cache hoặc session.
- Ghi file, object storage hoặc dữ liệu tạm.
- Thay đổi trạng thái workflow.
- Tạo bản ghi audit hoặc lịch sử.

Câu hỏi quan trọng: nếu thao tác chạy hai lần, chạy một phần hoặc bị timeout sau khi thành công, trạng thái cuối sẽ ra sao?

### 2.2. Giao tiếp với hệ thống bên ngoài

- HTTP/gRPC call.
- Gửi email, SMS, push notification.
- Publish message/event.
- Gọi cổng thanh toán hoặc đối tác.
- Truy vấn dịch vụ danh tính hoặc cấu hình.

Cần xem timeout, retry, rate limit, xác thực, dữ liệu gửi đi, hợp đồng phiên bản và cách xử lý khi hệ thống ngoài không sẵn sàng.

### 2.3. Thời gian và thứ tự

Một thay đổi có thể giữ nguyên số thao tác nhưng đổi thời điểm:
- Gửi event trước hay sau commit.
- Ghi log trước hay sau khi xác thực.
- Xóa cache trước hay sau khi cập nhật dữ liệu.
- Mở transaction trước hay sau lời gọi mạng.
- Chạy đồng bộ hay chuyển sang background worker.

Thứ tự có thể là một phần của hợp đồng. Ví dụ, gửi email trước khi lưu đơn có thể thông báo một giao dịch chưa tồn tại; gửi sau commit nhưng thất bại có thể để đơn đã tạo mà không có email.

### 2.4. Tài nguyên và tải

- Số lượng truy vấn database.
- Số lần gọi API bên ngoài.
- Thread, connection, lock và file handle.
- Bộ nhớ cache, kích thước queue và số message tồn đọng.
- CPU, thời gian serialize và kích thước payload.
- Thời gian giữ transaction hoặc lock.

Một thay đổi nhỏ trong code có thể nhân số lần gọi theo số phần tử, số tenant hoặc số request. Cần xem quy mô đầu vào và cách tải tăng theo thời gian.

### 2.5. Quan sát và dữ liệu nhạy cảm

Thêm log hoặc tracing cũng là thay đổi hành vi vận hành:
- Log có chứa token, email, địa chỉ hoặc thông tin thanh toán không?
- Số lượng log có tăng mạnh không?
- Correlation ID có được truyền qua async boundary không?
- Metric label có tạo cardinality quá cao không?
- Dữ liệu audit có đáp ứng yêu cầu truy vết và lưu giữ không?

“Thêm log để dễ debug” vẫn cần đánh giá quyền truy cập, chi phí lưu trữ và chính sách dữ liệu.

## 3. Tác dụng phụ dự kiến và ngoài dự kiến

Không phải hệ quả mới nào cũng là bug. Một feature có thể cần gửi email hoặc tạo event. Điều cần phân biệt là **tác dụng phụ được yêu cầu và thiết kế** với **hệ quả phát sinh ngoài hợp đồng**.

| Tác dụng phụ | Được dự kiến khi | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Ghi thêm audit record | Có yêu cầu audit, schema và retention rõ | Ghi thiếu, ghi trùng hoặc chứa dữ liệu nhạy cảm |
| Gửi email xác nhận | Email là một phần luồng nghiệp vụ | Gửi trước commit, gửi hai lần hoặc không retry được |
| Thêm cache | Có mục tiêu giảm tải và chính sách freshness | Dữ liệu cũ, key sai tenant, cache không giới hạn |
| Phát event | Consumer cần phản ứng với thay đổi | Event sai phiên bản, sai thứ tự hoặc phát dù transaction rollback |
| Thêm log | Có câu hỏi vận hành cụ thể cần trả lời | Lộ bí mật, log quá nhiều hoặc khó liên kết request |
| Chuyển xử lý sang async | Có yêu cầu tách thời gian xử lý | Mất lỗi, mất context hoặc job tồn đọng không được giám sát |

Một nhận xét hữu ích nên nói rõ:
- Điều gì đã thay đổi.
- Hợp đồng nào cho phép hoặc yêu cầu thay đổi đó.
- Hệ quả nào là chủ ý.
- Hệ quả nào chưa được đánh giá.
- Bằng chứng nào xác nhận hành vi đúng.

## 4. Lập bản đồ tác động trước khi sửa

Trước khi đánh giá side effect, cần hiểu luồng thay đổi đi qua những thành phần nào.

Một bản đồ tác động đơn giản:

~~~mermaid
flowchart TD
    A[API request] --> B[Checkout service]
    B --> C[Validate order]
    C --> D[Database transaction]
    D --> E[Order record]
    D --> F[Outbox event]
    F --> G[Background publisher]
    G --> H[Message broker]
    H --> I[Notification consumer]
    H --> J[Analytics consumer]
~~~

Sơ đồ này chỉ minh họa một kiến trúc có outbox. Khi phân tích hệ thống thật, phải dùng luồng và thành phần đã xác minh; không suy ra có outbox hoặc consumer nào chỉ từ tên class.

### 4.1. Lần theo dữ liệu từ đầu vào tới tác dụng phụ

Với mỗi giá trị quan trọng, hỏi:
1. Ai tạo giá trị?
2. Nó có được xác thực và chuẩn hóa không?
3. Có chứa dữ liệu nhạy cảm không?
4. Nó đi qua những module nào?
5. Nó được lưu hoặc gửi ở đâu?
6. Có bị biến đổi hoặc serialize không?
7. Ai tiêu thụ và dựa vào hợp đồng nào?

Ví dụ, tenant ID lấy từ authentication context có ý nghĩa khác với tenant ID do client gửi trong request body. Nếu một thay đổi chuyển nguồn dữ liệu mà không kiểm tra quyền, tác dụng phụ có thể là truy cập hoặc ghi dữ liệu sai tenant.

### 4.2. Xác định chiều phụ thuộc và owner

Ghi lại:
- Thành phần gọi.
- Thành phần được gọi.
- Hợp đồng dữ liệu.
- Người sở hữu từng module hoặc dịch vụ.
- Ranh giới transaction.
- Điểm retry và timeout.
- Nơi quan sát lỗi.

Nếu không biết owner của consumer, một thay đổi event có thể bị merge mà không ai kiểm tra tương thích. Đây là chi phí phối hợp phát sinh cần được tính vào kế hoạch.

### 4.3. Phân biệt đường đồng bộ và bất đồng bộ

**Đồng bộ:** caller chờ kết quả. Lỗi có thể truyền ngược về caller và làm tăng latency.

**Bất đồng bộ:** caller thường không chờ consumer hoàn thành. Lỗi có thể xuất hiện muộn hơn, queue có thể tồn đọng và cần cơ chế quan sát riêng.

Chuyển một thao tác từ đồng bộ sang bất đồng bộ không chỉ là thay API. Nó thay đổi:
- Thời điểm caller biết thành công/thất bại.
- Cách truyền context và danh tính.
- Cách retry và chống trùng.
- Cách kiểm thử và debug.
- Trách nhiệm vận hành queue và worker.

## 5. Ví dụ xuyên suốt: thêm email xác nhận sau khi tạo đơn

Giả sử trước thay đổi, hệ thống tạo đơn và lưu vào database. Yêu cầu mới là gửi email xác nhận sau khi đặt hàng.

### 5.1. Luồng ban đầu

~~~java
record Order(String id, String customerEmail, long amountVnd) {}

interface OrderRepository {
    Order save(Order order);
}

final class OrderService {
    private final OrderRepository orders;

    OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    Order place(Order order) {
        return orders.save(order);
    }
}
~~~

Hành vi hiện tại: lưu đơn và trả kết quả theo hợp đồng repository. Ví dụ này không mô tả đầy đủ transaction hoặc validation của một hệ thống thật.

### 5.2. Thay đổi đơn giản nhưng tạo hệ quả mới

~~~java
interface ConfirmationSender {
    void send(Order order);
}

final class OrderService {
    private final OrderRepository orders;
    private final ConfirmationSender confirmations;

    OrderService(
            OrderRepository orders,
            ConfirmationSender confirmations) {
        this.orders = orders;
        this.confirmations = confirmations;
    }

    Order place(Order order) {
        Order saved = orders.save(order);
        confirmations.send(saved);
        return saved;
    }
}
~~~

Diff chỉ thêm một dependency và một lời gọi. Nhưng tác động đã thay đổi:

- Mỗi lần đặt hàng có thêm một lời gọi mạng hoặc dịch vụ gửi email.
- Latency của API phụ thuộc vào dịch vụ email nếu gửi đồng bộ.
- Email có thể thất bại sau khi đơn đã được lưu.
- Caller có thể nhận lỗi dù đơn đã tồn tại.
- Retry request có thể tạo đơn hoặc gửi email trùng.
- Test cần kiểm tra tương tác với sender.
- Môi trường local/CI cần fake hoặc cấu hình sender.
- Vận hành cần theo dõi lỗi, quota, timeout và backlog nếu chuyển async.

Một thay đổi có vẻ nhỏ đã tạo ra nhiều chi phí bảo trì mới. Không có nghĩa không nên thêm email; nghĩa là phải quyết định **hợp đồng thành công và phục hồi** trước khi triển khai.

## 6. Phân tích các tình huống lỗi của tác dụng phụ

Với luồng lưu đơn rồi gửi email đồng bộ, hãy xem:

| Tình huống | Trạng thái có thể xảy ra | Câu hỏi cần quyết định |
| --- | --- | --- |
| Lưu đơn thất bại | Không có đơn; email chưa được gọi | Caller nhận lỗi gì? |
| Lưu thành công, gửi email thành công | Có đơn và email đã gửi | Đây có phải hành vi mong muốn? |
| Lưu thành công, gửi email thất bại | Có đơn nhưng caller có thể nhận lỗi | Có retry email riêng hay retry toàn bộ request? |
| Gửi email thành công, response bị mất | Đơn và email đã tồn tại; caller không biết kết quả | Retry có tạo bản ghi/email trùng? |
| Sender timeout nhưng thực tế đã nhận yêu cầu | Kết quả gửi không xác định | Có idempotency key hoặc trạng thái tra cứu không? |
| Gửi email trước khi transaction commit | Email có thể thông báo đơn sẽ rollback | Làm sao bảo đảm thứ tự? |

Đây là lý do cần kiểm tra cả **thành công một phần**. Một luồng có nhiều hệ thống không tự động trở thành một giao dịch nguyên tử.

### 6.1. Không giữ transaction mở trong lúc gọi mạng nếu không cần

Nếu database transaction mở rồi gọi email provider, transaction có thể giữ connection và lock trong suốt thời gian chờ mạng. Khi provider chậm, tài nguyên DB bị giữ lâu hơn, tăng contention và làm các request khác chờ.

Có trường hợp cần phối hợp chặt giữa dữ liệu và tác dụng phụ, nhưng HTTP call không thể tự tham gia transaction ACID của database theo cách thông thường. Cần thiết kế ranh giới rõ thay vì giả định mọi thao tác cùng rollback.

## 7. Chọn chiến lược phù hợp cho side effect

Không có một cách duy nhất đúng cho mọi hệ thống. Cần chọn theo yêu cầu về thời gian phản hồi, độ tin cậy, khả năng chấp nhận gửi trễ và chi phí vận hành.

| Chiến lược | Khi phù hợp | Chi phí/rủi ro |
| --- | --- | --- |
| **Gửi đồng bộ** | Kết quả gửi là một phần của phản hồi và có hợp đồng rõ | Latency, lỗi bên ngoài truyền về caller, retry phức tạp |
| **Gửi sau commit** | Cần tránh thông báo dữ liệu chưa commit | Có thể mất sự kiện nếu process dừng giữa commit và publish |
| **Transactional outbox** | Cần ghi dữ liệu và sự kiện bền vững trong cùng transaction DB | Thêm bảng, publisher, retry, cleanup và monitoring |
| **Message queue** | Cần tách tải và xử lý bất đồng bộ | Queue, consumer, duplicate delivery, ordering và vận hành |
| **Job nền có lịch** | Có thể xử lý theo batch hoặc thời điểm định kỳ | Độ trễ, scheduling, idempotency và quan sát job |
| **Best effort** | Tác dụng phụ có thể mất mà không vi phạm nghiệp vụ | Cần nói rõ điều gì có thể mất và không tạo kỳ vọng sai |

### 7.1. Transactional outbox giải quyết vấn đề nào?

Nếu đơn hàng và một bản ghi outbox được ghi trong **cùng transaction database**, khi transaction commit thì cả hai cùng tồn tại; nếu rollback thì cả hai cùng rollback. Một worker riêng đọc outbox và phát event/email request sau đó.

~~~mermaid
flowchart TD
    A[Place order] --> B[Begin DB transaction]
    B --> C[Save order]
    C --> D[Insert outbox event]
    D --> E{Commit?}
    E -- No --> F[Rollback both]
    E -- Yes --> G[Publisher reads pending event]
    G --> H[Send to broker/provider]
    H --> I[Mark event delivered]
~~~

Outbox giúp tránh khoảng trống giữa “đã commit đơn” và “process dừng trước khi phát event”. Nhưng nó **không tự bảo đảm exactly-once delivery** tới hệ thống ngoài. Publisher có thể gửi thành công rồi chết trước khi đánh dấu delivered; lần sau gửi lại. Consumer hoặc provider vẫn cần idempotency phù hợp.

### 7.2. Ví dụ Java về ghi outbox cùng transaction

~~~java
record OrderPlaced(String eventId, String orderId) {}

interface OutboxRepository {
    void append(OrderPlaced event);
}

final class OrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    OrderService(OrderRepository orders, OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    // Giả định hai repository tham gia cùng một transaction DB.
    Order place(Order order) {
        Order saved = orders.save(order);
        outbox.append(new OrderPlaced(
                "order-placed:" + saved.id(), saved.id()));
        return saved;
    }
}
~~~

Comment trong ví dụ là điều kiện quan trọng: nếu hai repository không tham gia cùng transaction hoặc dùng hai database khác nhau, tính nguyên tử không được bảo đảm. Trong ứng dụng thực, annotation transaction, transaction manager và connection binding phụ thuộc framework.

### 7.3. Kiểm thử đúng ranh giới

Unit test có thể xác nhận service yêu cầu ghi order và thêm outbox event với ID phù hợp. Nhưng để xác nhận **cùng transaction**, cần integration test với database và transaction manager thật hoặc môi trường tương đương.

Các kiểm tra hữu ích:
- Khi transaction commit, cả order và outbox record đều tồn tại.
- Khi transaction rollback, cả hai đều không tồn tại.
- Publisher gửi event pending và chỉ đánh dấu sau kết quả phù hợp.
- Nếu gửi thành công nhưng worker dừng trước khi đánh dấu, lần gửi lại không tạo tác động nghiệp vụ trùng ở consumer.
- Outbox record lỗi lâu ngày được quan sát và xử lý.

## 8. Kiểm tra tính idempotent và retry

**Idempotent** là thao tác có thể được thực hiện lặp lại với cùng một khóa/ý nghĩa mà không tạo thêm tác động nghiệp vụ ngoài dự kiến.

Retry cần xem xét:
- Lỗi có thực sự transient không?
- Lần đầu có thể đã thành công dù caller timeout không?
- Có khóa idempotency ổn định không?
- Retry có deadline, backoff và giới hạn không?
- Có phân biệt lỗi không thể retry với lỗi tạm thời?
- Ai theo dõi message/job thất bại kéo dài?

Ví dụ, nếu mỗi lần retry tạo một event ID ngẫu nhiên mới, consumer có thể không nhận ra đó là cùng một yêu cầu. Nếu dùng khóa ổn định theo order ID và loại event, consumer có thể kiểm soát trùng lặp trong phạm vi hợp đồng.

**Không retry mù quáng** một thao tác trừ tiền, tạo đơn hoặc gửi thông báo mà chưa hiểu trạng thái lần trước.

## 9. Chi phí bảo trì phát sinh gồm những gì?

Một thay đổi có thể không làm chức năng sai ngay nhưng tạo thêm chi phí trong các lần sửa tiếp theo.

| Loại chi phí | Biểu hiện |
| --- | --- |
| **Cognitive cost** | Người bảo trì phải hiểu thêm nhiều trạng thái và đường đi |
| **Coupling cost** | Thay đổi một module buộc sửa hoặc phối hợp nhiều consumer |
| **Testing cost** | Test cần thêm mock, container, fixture hoặc môi trường |
| **Operational cost** | Cần dashboard, alert, retry, queue và runbook |
| **Resource cost** | Tăng DB connection, network call, storage, CPU hoặc memory |
| **Compatibility cost** | Phải duy trì nhiều phiên bản API/event/schema |
| **Data lifecycle cost** | Cần retention, cleanup, migration và xử lý dữ liệu cũ |
| **Security/privacy cost** | Thêm nơi lưu, truyền hoặc log dữ liệu nhạy cảm |
| **Ownership cost** | Cần owner mới hoặc phối hợp với team khác |
| **Change coordination cost** | PR phải chờ consumer, release window hoặc phê duyệt |

Chi phí không nhất thiết xuất hiện ngay trong sprint hiện tại. Một event mới có thể yêu cầu consumer duy trì nhiều năm; một cache mới có thể cần chính sách invalidation ở mọi luồng cập nhật; một dependency mới có thể phải theo dõi CVE và nâng phiên bản.

### 9.1. Chi phí trực tiếp và chi phí ẩn

**Trực tiếp:** thêm một service, một bảng, một job, một config, một test suite.

**Ẩn:** người mới cần hiểu thêm một vòng đời; lỗi xảy ra ở thời điểm khác; phải đối chiếu hai nguồn dữ liệu; cần thêm quyền truy cập; phải giữ tương thích cho client cũ.

Một kế hoạch đánh giá tác động chỉ liệt kê file thay đổi sẽ bỏ sót phần lớn chi phí ẩn.

### 9.2. Chi phí vận hành kéo dài

Khi thêm một queue, nhóm phải trả lời:
- Ai theo dõi độ sâu queue?
- Mức backlog nào cần cảnh báo?
- Message poison được xử lý ra sao?
- Có dead-letter queue không?
- Cách replay message có an toàn không?
- Ai chịu trách nhiệm khi consumer dừng?
- Có giới hạn lưu trữ và cleanup không?

Nếu không có owner và runbook, “chuyển sang async để nhanh hơn” có thể chỉ chuyển độ phức tạp từ request path sang vận hành.

## 10. Kiểm tra thay đổi bằng ma trận tác động

Trước khi merge, có thể lập bảng:

| Khía cạnh | Trước thay đổi | Sau thay đổi | Bằng chứng cần có |
| --- | --- | --- | --- |
| Kết quả nghiệp vụ | Chỉ tạo đơn | Tạo đơn và yêu cầu gửi xác nhận | Unit/contract tests |
| Database | Ghi order | Ghi order và outbox nếu chọn kiến trúc đó | Integration/transaction test |
| External call | Không có email | Có publisher/worker gửi email | Contract test, failure test |
| Latency | Không chờ email | Request không chờ worker nếu async | Benchmark/tracing |
| Retry | Retry request theo hợp đồng cũ | Retry publisher có idempotency | Duplicate/failure test |
| Monitoring | Theo dõi checkout | Thêm backlog và delivery failure | Dashboard/alert |
| Privacy | Email trong dữ liệu order | Email có thể xuất hiện trong event/log | Data classification và log review |
| Ownership | Checkout team | Có thể cần notification/platform owner | Owner xác nhận |

Ma trận này không phải biểu mẫu bắt buộc cho mọi thay đổi nhỏ. Dùng khi thay đổi có side effect, dependency hoặc chi phí vận hành đáng kể.

### 10.1. Phân loại mức độ tác động

Có thể đánh dấu:
- **Không đổi:** có bằng chứng hành vi và cấu trúc liên quan giữ nguyên.
- **Đã dự kiến:** thay đổi là mục tiêu của yêu cầu và có test/owner.
- **Cần xác minh:** chưa rõ consumer, thứ tự hoặc hợp đồng.
- **Ngoài phạm vi:** phát hiện thêm việc cần issue hoặc quyết định riêng.

Không nên đánh dấu “không đổi” chỉ vì file đó không xuất hiện trong diff. Một thay đổi interface có thể ảnh hưởng consumer không được sửa trực tiếp.

## 11. Kiểm tra chi phí trước và sau thay đổi

Cần có baseline trước khi tuyên bố thay đổi đã giảm chi phí.

Ví dụ:
- Thời gian unit test policy trước/sau.
- Số lần gọi HTTP hoặc DB trong một request.
- p50/p95/p99 latency theo workload đại diện.
- Số connection đồng thời và thời gian giữ connection.
- Queue depth, retry count và age của message cũ nhất.
- Tỷ lệ gửi trùng hoặc xử lý trùng.
- Thời gian review và số module phải thay đổi.
- Số cảnh báo hoặc sự cố liên quan trong cửa sổ theo dõi.

### 11.1. Đo cùng điều kiện

So sánh trước/sau cần:
- Cùng loại workload hoặc dữ liệu tương đương.
- Cùng cấu hình môi trường.
- Cùng cách thu thập metric.
- Ghi rõ phiên bản code và dependency.
- Tách ảnh hưởng của thay đổi khác.
- Nêu giới hạn nếu mẫu nhỏ hoặc biến động lớn.

Không so sánh test trên máy local trước thay đổi với CI runner sau thay đổi rồi kết luận thời gian giảm/tăng là do code.

### 11.2. Không tối ưu một metric bằng cách chuyển chi phí nơi khác

Ví dụ, chuyển gửi email sang async làm API latency giảm nhưng queue tăng và thời gian email tới người dùng dài hơn. Cần đánh giá cả:
- Request latency.
- Delivery latency.
- Failure rate.
- Backlog và retry.
- Chi phí vận hành.

Một metric tốt lên không có nghĩa toàn hệ thống tốt lên.

## 12. Kiểm thử tác dụng phụ theo cấp phù hợp

| Loại kiểm tra | Điều cần xác minh |
| --- | --- |
| **Unit test** | Logic quyết định side effect nào cần xảy ra, với dữ liệu nào |
| **Interaction test** | Gọi dependency đúng số lần và đúng tham số khi tương tác là hợp đồng |
| **Integration test** | Transaction, persistence, adapter và serialization hoạt động đúng |
| **Contract test** | Provider và consumer hiểu cùng schema/semantics |
| **Failure-path test** | Timeout, exception, rollback và retry tạo trạng thái đúng |
| **Concurrency test** | Nhiều request/message không làm trùng hoặc ghi đè state |
| **Performance/load test** | Tải, latency và tài nguyên trong workload đại diện |
| **Operational smoke test** | Health, log, metric, alert và worker hoạt động sau deploy |

Không phải mọi thay đổi đều cần tất cả các loại test. Chọn theo đường tác động và hậu quả nếu sai.

### 12.1. Test tương tác không thay test kết quả

Một test xác nhận notifier được gọi một lần không chứng minh email thực sự được gửi đúng, cũng không chứng minh transaction đã commit. Cần phân biệt:
- Service có yêu cầu gửi không?
- Adapter có gửi đúng request không?
- Provider có chấp nhận không?
- Người nhận có nhận được không?
- Retry có thể gửi trùng không?

Mỗi câu hỏi thuộc một lớp bằng chứng khác nhau.

### 12.2. Test thất bại một phần

Các kịch bản quan trọng:
- Database thành công, provider thất bại.
- Provider thành công, response timeout.
- Outbox insert lỗi trước commit.
- Worker chết sau publish nhưng trước khi mark delivered.
- Consumer xử lý message hai lần.
- Cache update lỗi sau khi database commit.

Test cần xác nhận trạng thái và khả năng phục hồi, không chỉ exception được ném ra.

## 13. Kiểm tra bảo mật và quyền riêng tư của side effect

Mỗi nơi mới nhận hoặc lưu dữ liệu là một ranh giới cần xem xét:
- Event có chứa dữ liệu cá nhân không cần thiết không?
- Log có ghi token, mật khẩu hoặc thông tin thanh toán không?
- Notification có thể gửi nhầm người do email/tenant ID sai không?
- Consumer có xác thực nguồn và kiểm tra quyền phù hợp không?
- Secret của provider được lưu và xoay vòng thế nào?
- Dữ liệu trong outbox, queue và dead-letter queue có retention không?
- Replay message có thể tạo lại tác dụng phụ nguy hiểm không?

**Tối thiểu hóa dữ liệu** thường giúp giảm rủi ro và chi phí. Event chỉ nên mang thông tin consumer cần theo hợp đồng; không đưa toàn bộ object nghiệp vụ vào message theo thói quen.

## 14. Theo dõi sau triển khai

Một thay đổi có side effect mới cần quan sát cả thành công và thất bại.

Ví dụ với notification worker:
- Số event được tạo.
- Số event đang chờ.
- Tuổi của event chờ lâu nhất.
- Tỷ lệ publish thành công.
- Số retry và dead-letter.
- Thời gian từ lúc tạo đơn đến lúc gửi.
- Tỷ lệ gửi trùng nếu provider hoặc consumer hỗ trợ nhận diện.
- Lỗi xác thực, quota và timeout.

### 14.1. Alert phải gắn với hành động

Một alert tốt trả lời:
- Điều kiện nào đang vượt ngưỡng?
- Người nhận alert là ai?
- Người đó cần kiểm tra dashboard/log nào?
- Có runbook xử lý không?
- Khi nào cần escalation?

Alert chỉ tăng số thông báo mà không có owner hoặc hành động sẽ tạo thêm chi phí vận hành.

### 14.2. Cửa sổ quan sát phụ thuộc vào hành vi

Một luồng có tải thấp hoặc chạy batch theo tuần không thể được đánh giá bằng vài phút sau deploy. Chọn cửa sổ theo:
- Tần suất giao dịch.
- Chu kỳ batch/job.
- Thời gian queue có thể tồn tại.
- Thời gian provider phản hồi.
- Số lượng mẫu đủ để so sánh.
- Mức độ nghiêm trọng nếu vấn đề bị phát hiện muộn.

## 15. Rollout và rollback khi tác dụng phụ thay đổi

Nếu thay đổi thêm event, queue, bảng outbox hoặc schema, rollback source không tự đảo ngược những gì đã được phát đi.

Trước deploy, xác định:
- Artifact cũ có đọc được dữ liệu mới không?
- Consumer cũ có xử lý được event mới không?
- Có thể tắt publisher mà không mất event không?
- Message đã gửi có thể replay không?
- Có dữ liệu nào cần bù trừ hoặc đối soát?
- Feature flag có kiểm soát được cả write path và read path không?
- Khi rollback, event tồn đọng được xử lý thế nào?

### 15.1. Thay đổi tương thích theo giai đoạn

Với schema/event, có thể cần:
1. Mở rộng schema để consumer cũ vẫn hoạt động.
2. Triển khai consumer hiểu cả dạng cũ và mới.
3. Chuyển producer sang dạng mới.
4. Theo dõi và đối chiếu.
5. Chỉ bỏ dạng cũ khi không còn consumer phụ thuộc.

Đây là ví dụ về chiến lược chuyển đổi, không phải trình tự áp dụng cho mọi hệ thống. Cần kiểm tra khả năng tương thích thực tế của schema và consumer.

### 15.2. Đừng dùng rollback như kế hoạch phục hồi duy nhất

Một email đã gửi không thể thu hồi bằng Git. Một payment đã thực hiện cần đối soát hoặc giao dịch bù, không thể đơn giản chạy lại code cũ. Một event đã được consumer xử lý có thể đã tạo dữ liệu downstream.

Kế hoạch cần phân biệt:
- **Rollback code:** trở lại artifact trước.
- **Rollback config/flag:** tắt đường mới nếu an toàn.
- **Data recovery:** khôi phục hoặc sửa dữ liệu.
- **Compensating action:** hành động nghiệp vụ bù trừ.
- **Replay/reconciliation:** xử lý lại hoặc đối chiếu các sự kiện.

## 16. Chi phí bảo trì trong vòng đời dài hạn

Một thay đổi được chấp nhận hôm nay có thể tạo nghĩa vụ trong nhiều tháng hoặc năm.

### 16.1. Dependency và nâng cấp

Thêm SDK/provider mới đồng nghĩa:
- Theo dõi phiên bản và lỗ hổng.
- Xử lý thay đổi API.
- Quản lý credential và quota.
- Cập nhật test contract.
- Xem xét điều khoản và mức độ phụ thuộc nhà cung cấp.

Nếu lợi ích chỉ là tiện lợi nhỏ, dependency mới có thể không đáng chi phí.

### 16.2. Schema và dữ liệu lịch sử

Thêm field hoặc event có thể yêu cầu:
- Migration.
- Backfill.
- Tương thích phiên bản.
- Retention và cleanup.
- Công cụ replay.
- Chính sách xử lý dữ liệu lỗi.

Không nên đánh giá chi phí chỉ dựa trên việc thêm một cột hoặc một record Java.

### 16.3. Tài liệu và onboarding

Nếu thay đổi tạo một worker, queue hoặc state mới, cần cập nhật:
- Sơ đồ luồng.
- Hợp đồng event.
- Runbook.
- Cấu hình môi trường.
- Hướng dẫn debug và replay.
- Owner và kênh escalation.

Thiếu tài liệu khiến kiến thức tập trung ở người triển khai ban đầu và làm tăng thời gian xử lý sự cố sau này.

### 16.4. Phụ thuộc vào một cá nhân hoặc team

Nếu chỉ một người biết cách replay dead-letter message hoặc khôi phục cache, đó là chi phí tổ chức. Cần:
- Chia sẻ cách vận hành.
- Có ít nhất người dự phòng phù hợp.
- Ghi quy trình và quyền cần thiết.
- Thực hành phục hồi trong môi trường an toàn.
- Xác định team sở hữu hợp đồng với hệ thống ngoài.

## 17. Cân nhắc lợi ích với chi phí mới

Không nên thêm abstraction, queue, cache hay service chỉ vì chúng là kỹ thuật phổ biến. Mỗi cơ chế tạo ra nghĩa vụ.

| Lựa chọn | Lợi ích tiềm năng | Chi phí cần tính |
| --- | --- | --- |
| Cache | Giảm tải và latency | Invalidation, stale data, memory, tenant isolation |
| Queue | Tách tải và retry | Backlog, ordering, duplicate, monitoring, replay |
| Event-driven | Giảm coupling thời gian chạy | Schema, consumer ownership, eventual consistency |
| Audit log | Truy vết | Retention, access control, data volume |
| Retry | Chịu lỗi transient | Duplicate side effect, backoff, retry storm |
| Circuit breaker | Giới hạn tác động dependency lỗi | Cấu hình threshold, trạng thái, alert và test |
| Thêm abstraction | Cô lập thay đổi | Hợp đồng, indirection, onboarding và maintenance |
| Thêm dependency | Tận dụng chức năng có sẵn | Upgrade, CVE, license, compatibility |

### 17.1. Đánh giá theo tổng chi phí sở hữu

Một mô hình suy nghĩ:

~~~text
Tổng chi phí vòng đời =
    chi phí triển khai ban đầu
  + chi phí kiểm thử và tích hợp
  + chi phí vận hành và quan sát
  + chi phí bảo trì/nâng cấp
  + chi phí tương thích và chuyển đổi
  + chi phí xử lý lỗi và phục hồi
~~~

Đây là mô hình phân tích, không phải công thức tài chính chính xác. Mỗi hạng mục cần dữ liệu và giả thiết riêng nếu dùng để so sánh phương án.

### 17.2. Đừng tính lợi ích bằng số liệu chưa có

Nếu thêm cache, không tuyên bố “giảm tải 50%” trước khi đo. Nếu thêm queue, không tuyên bố “hệ thống tin cậy hơn” chỉ vì request không chờ provider. Hãy định nghĩa mục tiêu:
- Giảm bao nhiêu latency trong workload nào?
- Tỷ lệ mất/duplicate event cho phép là gì?
- Mức độ trễ notification có chấp nhận được không?
- Ai chịu chi phí vận hành mới?

## 18. Khi nào nên từ chối hoặc hoãn một side effect mới?

Một side effect có thể chưa nên thêm nếu:
- Chưa có yêu cầu nghiệp vụ hoặc người dùng cần nó.
- Không xác định được owner của provider/consumer.
- Không biết dữ liệu nào sẽ được gửi.
- Chưa có cách xử lý timeout, retry hoặc duplicate.
- Chi phí vận hành lớn hơn lợi ích hiện tại.
- Không có cách kiểm tra tác dụng phụ trong môi trường an toàn.
- Thay đổi phá hợp đồng hoặc rollback mà chưa có kế hoạch.
- Không có metric hoặc runbook cho luồng mới có rủi ro đáng kể.

Có thể triển khai từng phần:
- Bắt đầu bằng audit record nội bộ nếu đó là yêu cầu đã xác nhận.
- Chạy shadow hoặc dry-run chỉ khi không tạo side effect thật.
- Giới hạn rollout theo nhóm người dùng.
- Giữ feature flag có owner và thời hạn.
- Tách phần tích hợp provider thành một bước riêng.

Không nên tạo cơ chế tạm thời rồi để lại vĩnh viễn mà không có tiêu chí kết thúc.

## 19. Ghi nhận tác động của thay đổi

Một ghi chú ngắn giúp reviewer, người vận hành và người tiếp quản biết điều gì đã thay đổi.

~~~markdown
### CHANGE-IMPACT-007 — <tên thay đổi>

Mục tiêu:
- Yêu cầu hoặc vấn đề cần giải quyết:

Hành vi trước thay đổi:
- Input/output:
- Trạng thái được ghi:
- Side effect hiện có:

Hành vi sau thay đổi:
- Side effect mới hoặc thay đổi:
- Thứ tự và thời điểm:
- Dependency/consumer:
- Dữ liệu được truyền:

Tính đúng và phục hồi:
- Timeout/failure:
- Retry/idempotency:
- Transaction/rollback:
- Compatibility:

Chi phí bảo trì:
- Test và môi trường:
- Monitoring/alert/runbook:
- Resource và dependency:
- Owner và phối hợp:

Bằng chứng:
- Unit/integration/contract tests:
- Performance/load data nếu có:
- Kết quả staging/production:
- Điều chưa xác minh:

Rollout:
- Phạm vi và điều kiện mở rộng:
- Tín hiệu dừng:
- Rollback/data recovery:
- Người quyết định:

Theo dõi:
- Metric:
- Cửa sổ quan sát:
- Owner:
- Điều kiện đóng:
~~~

Không cần tạo tài liệu đầy đủ cho mọi thay đổi nhỏ. Dùng khi có side effect mới, dependency ngoài, schema, retry hoặc chi phí vận hành đáng kể.

## 20. Ví dụ nhận xét review có trọng tâm

### 20.1. Gửi email đồng bộ sau khi lưu

**Nhận xét yếu:** “Không nên gọi email ở đây.”

**Nhận xét có ích:**

> “Sau khi repository lưu thành công, lời gọi sender vẫn chạy trong request. Nếu provider timeout, caller có thể nhận lỗi dù đơn đã tồn tại; retry có thể tạo đơn hoặc email trùng. Cần thống nhất hợp đồng lỗi và idempotency trước khi merge. Nếu email không cần nằm trong phản hồi đồng bộ, cân nhắc outbox/worker và integration test cho transaction.”

### 20.2. Thêm cache nhưng không có invalidation

**Nhận xét yếu:** “Cache dễ lỗi.”

**Nhận xét có ích:**

> “Kết quả được cache theo product ID nhưng giá còn phụ thuộc tenant và currency. Hai tenant có thể nhận cùng một cache entry dù chính sách khác nhau. Cần đưa mọi chiều ảnh hưởng vào cache key hoặc xác nhận dữ liệu thực sự dùng chung; thêm test hai tenant và currency khác nhau.”

### 20.3. Thêm log chứa dữ liệu nhạy cảm

**Nhận xét yếu:** “Đừng log request.”

**Nhận xét có ích:**

> “Request object có thể chứa token và email nhưng đang được ghi toàn bộ khi provider lỗi. Log có thể được nhiều nhóm truy cập và lưu lâu hơn dữ liệu nghiệp vụ. Hãy log correlation ID và mã lỗi cần thiết, loại bỏ hoặc che trường nhạy cảm; xác nhận chính sách log hiện hành.”

### 20.4. Thêm retry không giới hạn

**Nhận xét yếu:** “Retry không tốt.”

**Nhận xét có ích:**

> “Vòng lặp retry hiện không có giới hạn và không phân biệt lỗi transient với lỗi xác thực. Khi provider từ chối credential, worker có thể gọi liên tục và làm tăng tải. Cần deadline/backoff, giới hạn attempt, phân loại lỗi và trạng thái dead-letter có owner.”

## 21. Cải thiện liên tục từ những tác dụng phụ đã quan sát

Sau khi một thay đổi được triển khai, hãy so sánh điều đã dự kiến với điều thực tế:

1. Tác dụng phụ nào đã xảy ra?
2. Tác dụng phụ nào không xuất hiện như dự kiến?
3. Có lỗi một phần hoặc trạng thái không xác định không?
4. Chi phí vận hành mới có phát sinh?
5. Metric nào xác nhận lợi ích?
6. Có chi phí nào bị chuyển sang team hoặc hệ thống khác?
7. Có tài liệu, test hoặc quy trình cần cập nhật?
8. Có thể loại bỏ cơ chế tạm thời nào?

Một vòng cải thiện:

~~~mermaid
flowchart TD
    A[Đề xuất thay đổi] --> B[Lập bản đồ tác động]
    B --> C[Định nghĩa kiểm chứng và chi phí]
    C --> D[Triển khai có kiểm soát]
    D --> E[Quan sát hành vi thực tế]
    E --> F{Kết quả phù hợp?}
    F -- Có --> G[Ghi nhận và chuẩn hóa]
    F -- Không --> H[Điều tra side effect/chi phí]
    H --> I[Sửa, rollback hoặc điều chỉnh]
    I --> E
    G --> J[Cập nhật checklist và kế hoạch tiếp theo]
~~~

Cải thiện liên tục không có nghĩa mọi metric phải tăng sau mỗi PR. Nó có nghĩa nhóm **học từ kết quả thật và cập nhật cách làm**, kể cả khi kết quả cho thấy giả thuyết ban đầu sai.

## 22. Những sai lầm thường gặp

**“Tác dụng phụ là xấu, nên loại bỏ tất cả.”** Không. Ứng dụng cần tương tác với dữ liệu và thế giới bên ngoài. Mục tiêu là quản lý hợp đồng, thứ tự, lỗi và chi phí.

**“Thêm một lời gọi email chỉ là thêm một dòng.”** Nó có thể tạo dependency, latency, lỗi một phần, retry và trách nhiệm vận hành mới.

**“Database đã commit thì gửi event chắc chắn thành công.”** Không. Process có thể dừng giữa commit và publish. Nếu cần bảo đảm bền vững, phải thiết kế lưu event và phát lại phù hợp.

**“Transactional outbox bảo đảm exactly once.”** Không. Nó giúp lưu thay đổi và event cùng transaction DB; publish/consume vẫn có thể lặp, nên cần idempotency.

**“Retry càng nhiều càng đáng tin.”** Retry vô hạn có thể tạo retry storm, duplicate side effect và backlog. Cần deadline, backoff, giới hạn và phân loại lỗi.

**“Chuyển sang async làm hệ thống đơn giản hơn.”** Nó có thể giảm latency request nhưng thêm queue, worker, eventual consistency, monitoring và replay.

**“Test gọi notifier một lần là đủ.”** Test đó không chứng minh provider nhận đúng, transaction đã commit hay email không bị gửi trùng.

**“Không thấy side effect trong diff thì không có tác động.”** Thay đổi contract hoặc state có thể lan qua caller, consumer, config và dữ liệu ngoài repository.

**“Thêm log luôn giúp debug.”** Log có thể lộ dữ liệu nhạy cảm, tăng chi phí lưu trữ và làm nhiễu cảnh báo.

**“Metric tốt lên nghĩa toàn hệ thống tốt lên.”** Một chi phí có thể chỉ bị chuyển sang queue, worker hoặc team khác. Phải đo cả hai phía.

**“Rollback code sẽ đảo ngược mọi thứ.”** Message đã phát, email đã gửi, payment đã thực hiện và dữ liệu đã ghi cần xử lý riêng.

**“Mọi thay đổi cần một bản đồ tác động dài.”** Không. Chọn mức phân tích theo side effect, phạm vi và hậu quả nếu sai.

## 23. Bài tập vận dụng

### Tình huống A — Gửi email sau khi lưu đơn

Một PR thêm lời gọi email ngay sau repository save. Nếu email provider timeout, request trả lỗi nhưng đơn đã tồn tại.

**Câu hỏi:** cần xác định những hợp đồng và kiểm tra nào?

**Gợi ý:** trạng thái thành công của API, retry request, duplicate order/email, timeout, idempotency và thời điểm commit. Nếu email có thể gửi trễ, cân nhắc outbox/worker; integration test phải xác minh order và outbox cùng transaction nếu chọn thiết kế đó.

### Tình huống B — Thêm cache theo product ID

Giá sản phẩm phụ thuộc tenant và loại tiền, nhưng cache key chỉ chứa product ID.

**Câu hỏi:** side effect hoặc hệ quả nào có thể xảy ra?

**Gợi ý:** cache có thể trả giá của tenant hoặc currency khác. Kiểm tra mọi chiều ảnh hưởng đến kết quả, key, invalidation và test hai tenant/currency. Đừng chỉ đo hit rate.

### Tình huống C — Retry khi timeout

Một client gọi API tạo payment. Request timeout, client retry và provider thực tế đã xử lý request đầu.

**Câu hỏi:** cần thiết kế gì để tránh trừ tiền hai lần?

**Gợi ý:** idempotency key ổn định, tra cứu trạng thái giao dịch, phân biệt timeout với từ chối, đối soát khi kết quả không xác định. Không giả định timeout nghĩa là thao tác chưa xảy ra.

### Tình huống D — Thêm log toàn bộ payload

Một worker ghi toàn bộ event vào log để hỗ trợ debug. Event chứa email và địa chỉ khách hàng.

**Câu hỏi:** chi phí và rủi ro mới là gì?

**Gợi ý:** privacy, quyền truy cập log, retention, storage, cardinality và khả năng tìm kiếm. Chỉ log trường tối thiểu, dùng correlation ID và che dữ liệu nhạy cảm theo chính sách.

### Tình huống E — Chuyển gửi thông báo sang queue

API trả nhanh hơn sau khi chuyển notification sang worker. Nhưng một số notification đến chậm và queue tăng dần.

**Câu hỏi:** metric nào cần theo dõi để đánh giá toàn bộ thay đổi?

**Gợi ý:** request latency, delivery latency, queue depth, oldest message age, retry/dead-letter, provider errors và chi phí worker. Xác định SLO giao thông báo và owner backlog.

### Tình huống F — Outbox nhưng consumer xử lý trùng

Publisher gửi event thành công, sau đó worker dừng trước khi đánh dấu event đã gửi. Lần chạy tiếp theo gửi lại.

**Câu hỏi:** outbox đã hỏng hay consumer cần thay đổi?

**Gợi ý:** đây là khả năng giao ít nhất một lần thường gặp. Consumer cần idempotency theo event ID hoặc khóa nghiệp vụ; kiểm tra side effect downstream và trạng thái đánh dấu. Không tuyên bố exactly-once chỉ nhờ outbox.

### Tình huống G — Thêm audit table

Một thay đổi ghi audit record cho mọi lần đọc hồ sơ. Dữ liệu tăng nhanh và query báo cáo chậm.

**Câu hỏi:** cần xem những chi phí nào?

**Gợi ý:** volume, index, retention, partition/archival, access control, query workload và yêu cầu audit thật. Xác định sự kiện nào cần lưu, không mặc định mọi lần đọc đều phải ghi chi tiết giống nhau.

### Tình huống H — Thay đổi thứ tự cache và database

Code mới xóa cache trước khi database commit. Khi transaction rollback, cache bị xóa dù dữ liệu không đổi; điều này gây tải đọc tăng.

**Câu hỏi:** tác dụng phụ phát sinh là gì và nên kiểm chứng thế nào?

**Gợi ý:** thứ tự invalidation thay đổi có thể tạo cache miss không cần thiết. Xem consistency model, thời điểm commit và failure path; test rollback và quan sát cache hit/miss cùng DB load.

## 24. Checklist kiểm tra tác dụng phụ và chi phí bảo trì

### Trước thay đổi

- **Hợp đồng:** kết quả trực tiếp và hành vi quan sát được hiện tại là gì?
- **Dữ liệu:** trạng thái nào được đọc, ghi, xóa hoặc gửi đi?
- **Dependency:** hệ thống, provider và consumer nào liên quan?
- **Thời gian:** thứ tự, transaction, async boundary và timeout là gì?
- **Lỗi:** nếu từng bước thất bại, trạng thái cuối ra sao?
- **Lặp lại:** retry hoặc duplicate request có tạo side effect trùng?
- **Tài nguyên:** DB, network, thread, storage và queue thay đổi thế nào?
- **Bảo mật:** dữ liệu nhạy cảm và quyền truy cập ở các boundary?
- **Owner:** ai chịu trách nhiệm code, consumer và vận hành?

### Khi review và kiểm thử

- **Bản đồ tác động:** đã xem caller và consumer ngoài diff?
- **Test:** có unit, integration, contract hoặc failure-path test phù hợp?
- **Transaction:** có kiểm tra commit/rollback và side effect liên quan?
- **Idempotency:** có kiểm soát retry và delivery lặp?
- **Performance:** workload và baseline đo có tương đương?
- **Quan sát:** log, metric, trace và alert có đủ mà không lộ dữ liệu?
- **Chi phí:** dependency, cấu hình, runbook và test mới có owner?
- **Phạm vi:** có đang trộn refactor, feature và migration không?

### Sau triển khai

- **Hành vi:** tác dụng phụ thực tế có khớp điều đã dự kiến?
- **Metric:** latency, error, backlog, resource và duplicate có trong giới hạn?
- **Phục hồi:** rollback, replay, reconciliation và bù trừ có hoạt động?
- **Chi phí:** có phát sinh việc bảo trì hoặc phối hợp mới?
- **Tài liệu:** sơ đồ, hợp đồng, runbook và owner đã cập nhật?
- **Học hỏi:** cần thay đổi checklist hoặc quy trình để tránh lặp lại?

## 25. Kết luận

**Kiểm tra tác dụng phụ giúp nhìn thấy những gì một thay đổi làm với toàn hệ thống, còn đánh giá chi phí bảo trì giúp biết nhóm sẽ phải chăm sóc những gì sau khi thay đổi được triển khai.** Một lời gọi mạng, cache, event hoặc log mới có thể hợp lý, nhưng cần được đặt trong hợp đồng rõ về dữ liệu, thứ tự, lỗi, retry, quyền và trách nhiệm vận hành.

Hãy lập bản đồ tác động, kiểm tra cả đường thành công lẫn thất bại, đo trước/sau trong điều kiện tương đương và theo dõi sau triển khai. Nếu lợi ích không tương xứng với nghĩa vụ mới, hãy thu hẹp hoặc hoãn thay đổi; nếu tác dụng phụ là cần thiết, thiết kế cách quan sát và phục hồi ngay từ đầu.

Trong **CODE_QUALITY_FUNDAMENTALS**, kiểm tra tác dụng phụ và chi phí bảo trì phát sinh giúp mã **đáng tin cậy hơn nhờ quản lý trạng thái và lỗi xuyên hệ thống, dễ hiểu hơn nhờ hợp đồng và luồng tác động rõ ràng, và dễ thay đổi hơn nhờ nhận diện chi phí vòng đời trước khi chúng trở thành gánh nặng**.
