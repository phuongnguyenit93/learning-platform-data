# Phân biệt change stream của cơ sở dữ liệu với sự kiện nghiệp vụ

Khi xây dựng ứng dụng với **Spring Data MongoDB**, chúng ta có thể theo dõi thay đổi document bằng **MongoDB change stream** thông qua driver, `MongoTemplate` hoặc `ReactiveMongoTemplate`. Tuy nhiên, việc một document thay đổi **không đồng nghĩa** với việc hệ thống đã phát sinh một sự kiện có ý nghĩa nghiệp vụ. Phân biệt hai loại sự kiện này giúp thiết kế tích hợp đáng tin cậy, tránh kích hoạt quy trình nghiệp vụ sai và giảm phụ thuộc giữa các hệ thống.

## 1. Hai khái niệm trả lời hai câu hỏi khác nhau

### Change stream: “Dữ liệu vừa thay đổi như thế nào?”

MongoDB change stream là luồng thông báo về những thay đổi **đã được ghi nhận** trong cơ sở dữ liệu. Ứng dụng có thể theo dõi ở phạm vi collection, database hoặc deployment (tùy API và quyền truy cập). Một thông báo thường mô tả loại thao tác (`insert`, `update`, `replace`, `delete`, ...), namespace, khóa document, thời điểm liên quan đến thay đổi và một **resume token** để tiếp tục đọc luồng.

Ví dụ collection `orders` có document:

~~~json
{
  "_id": "ORD-1042",
  "customerId": "CUS-88",
  "status": "CREATED",
  "totalMinor": 125000
}
~~~

Khi thao tác cập nhật `status` từ `CREATED` sang `PAID` được lưu thành công, change stream có thể phát ra một sự kiện `update` với `documentKey` là `ORD-1042` và `updateDescription.updatedFields.status` là `PAID`. Nó chỉ xác nhận **một thay đổi dữ liệu đã xảy ra**; riêng bản ghi này chưa chứng minh được ai tạo thay đổi, nguyên nhân, các quy tắc nghiệp vụ đã thỏa mãn hay nghĩa của trạng thái `PAID` trong hệ thống.

### Sự kiện nghiệp vụ: “Điều gì có ý nghĩa trong lĩnh vực kinh doanh vừa xảy ra?”

**Sự kiện nghiệp vụ** (*business event* hoặc *domain event*, tùy ranh giới hệ thống) ghi nhận một sự thật có ý nghĩa với người sử dụng và quy tắc kinh doanh: `OrderPlaced`, `PaymentCaptured`, `OrderCancelled`, `InventoryReserved`... Sự kiện thường được tạo ra sau khi xử lý lệnh và kiểm tra điều kiện nghiệp vụ.

Một hợp đồng sự kiện có thể có dạng:

~~~json
{
  "eventId": "evt-7d5b",
  "type": "PaymentCaptured",
  "version": 1,
  "aggregateId": "ORD-1042",
  "occurredAt": "2026-11-20T05:10:00Z",
  "payload": {
    "paymentId": "PAY-9001",
    "amountMinor": 125000,
    "currency": "VND"
  }
}
~~~

`PaymentCaptured` thể hiện giao dịch thu tiền đã thành công theo quy tắc thanh toán. Nó có thể dẫn tới nhiều thay đổi dữ liệu (thêm bản ghi thanh toán, cập nhật đơn hàng, ghi lịch sử); ngược lại, một thao tác sửa trường `status` không nhất thiết chứng minh đã thu tiền.

**Điểm mấu chốt:** Change stream phản ánh **thao tác lưu trữ**; sự kiện nghiệp vụ phản ánh **ý nghĩa và cam kết của hệ thống**.

## 2. So sánh trực tiếp

| Tiêu chí | MongoDB change stream | Sự kiện nghiệp vụ |
| --- | --- | --- |
| Nguồn phát sinh | MongoDB quan sát thay đổi dữ liệu đã ghi nhận | Logic ứng dụng hoặc domain xác định một sự thật nghiệp vụ |
| Câu hỏi trả lời | Document nào được thêm, sửa, thay thế, xóa? | Đơn hàng đã đặt, tiền đã thu, hàng đã giữ chỗ? |
| Cách đặt tên | `insert`, `update`, `replace`, `delete` | `OrderPlaced`, `PaymentCaptured`, `ShipmentDispatched` |
| Ngữ cảnh | Collection, document key, các trường thay đổi, resume token | Mã sự kiện, đối tượng nghiệp vụ, phiên bản schema, dữ liệu nghiệp vụ cần thiết |
| Mức trừu tượng | Gắn với mô hình lưu trữ | Gắn với ngôn ngữ và quy tắc của lĩnh vực |
| Tác động khi đổi schema DB | Consumer đọc trực tiếp dễ bị ảnh hưởng | Có thể giữ hợp đồng sự kiện ổn định dù đổi cách lưu |
| Tình huống phù hợp | Đồng bộ dữ liệu, cập nhật search index/cache, quan sát thay đổi, kích hoạt publisher của outbox | Giao tiếp giữa dịch vụ, quy trình thanh toán, thông báo, báo cáo nghiệp vụ |
| Khả năng phát lại | Dựa vào resume token và lịch sử còn giữ được trong oplog | Phụ thuộc kho lưu sự kiện/broker, chính sách lưu giữ và khả năng phát lại đã thiết kế |

Không nên gọi mọi change stream message là “domain event”. Cũng không nên mặc định một business event chỉ ứng với đúng một thao tác CRUD.

## 3. Những tình huống dễ nhầm lẫn

Xét hệ thống đơn hàng dùng collection `orders`:

| Thay đổi nhìn thấy ở MongoDB | Kết luận *có thể* đúng | Kết luận không được tự suy ra |
| --- | --- | --- |
| `insert` document với `status: CREATED` | Có một document đơn hàng mới | Khách hàng vừa đặt hàng thành công: bản ghi có thể do nhập dữ liệu lịch sử hoặc khôi phục |
| `update status: PAID` | Trường trạng thái đã đổi | Cổng thanh toán thực sự đã thu tiền, vì cũng có thể là sửa tay/đồng bộ lại |
| `delete` document | Document đã bị xóa | Khách hàng yêu cầu hủy đơn: xóa có thể do TTL, tác vụ bảo trì hoặc quy định lưu giữ |
| Cập nhật nhiều trường trong một giao dịch | Một số dữ liệu cùng thay đổi | Mỗi trường tương ứng một business event riêng |
| Không thấy update trên `orders` | Collection chưa phát ra thay đổi quan sát được | Không có sự kiện nghiệp vụ nào: sự kiện có thể không làm đổi collection này |

Ví dụ: nếu nghiệp vụ quy định `OrderPaid` chỉ được phát khi nhận xác nhận hợp lệ từ nhà cung cấp thanh toán, việc lắng nghe trường `orders.status` chuyển thành `PAID` **không đủ** để đưa ra kết luận đó. Consumer phải dựa vào một hợp đồng nghiệp vụ đáng tin cậy, hoặc một lớp chuyển đổi có bằng chứng đầy đủ và quy tắc rõ ràng.

## 4. Dùng Spring Data MongoDB để đọc thay đổi dữ liệu

Trong ứng dụng reactive, `ReactiveMongoTemplate` cung cấp API tạo một `Flux` các `ChangeStreamEvent`. Ví dụ sau chỉ theo dõi thay đổi kỹ thuật của collection `orders`; nó **chưa phát** sự kiện nghiệp vụ:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class OrderChangeFeed {
    private final ReactiveMongoTemplate mongo;

    public OrderChangeFeed(ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Flux<ChangeStreamEvent<Document>> changes() {
        return mongo.changeStream(
            "orders",
            ChangeStreamOptions.empty(),
            Document.class
        );
    }
}
~~~

Ứng dụng cần **đăng ký subscriber** để thực sự nhận dữ liệu. Trong triển khai thực tế, phải quản lý vòng đời subscription, lỗi kết nối, backpressure, lưu checkpoint và khởi động lại; không đặt một lệnh `subscribe()` tùy tiện trong mỗi HTTP request rồi bỏ mặc luồng đang chạy. Với tác vụ đồng bộ, Spring Data MongoDB cũng cung cấp cơ chế lắng nghe change stream qua API tương ứng của `MongoTemplate` và message listener container.

Các giới hạn kỹ thuật cần hiểu:

- **Điều kiện MongoDB:** Change streams cần MongoDB chạy dạng replica set hoặc sharded cluster; không hoạt động như change stream thông thường trên một standalone server. Tài khoản theo dõi phải có quyền phù hợp.
- **Dữ liệu trong event:** Khi `update`, sự kiện có thể chứa *update description* mà không có toàn bộ document mới. Chế độ tra cứu `fullDocument` (ví dụ `updateLookup`) là truy vấn lấy lại document và không nên coi là snapshot bất biến đúng tại từng thao tác; với `delete` thường không còn document để truy vấn. Không thiết kế nghiệp vụ trên giả định `fullDocument` luôn tồn tại.
- **Thứ tự và khả năng phục hồi:** Resume token giúp tiếp tục luồng khi lịch sử thay đổi cần thiết vẫn còn. Nếu token đã quá cũ so với oplog hoặc luồng bị vô hiệu hóa, hệ thống cần kế hoạch khởi tạo lại/đối soát, không thể giả định sẽ phát lại mọi thay đổi từ vô hạn quá khứ.
- **Ngữ nghĩa giao nhận:** Change stream không tự bảo đảm exactly-once cho việc xử lý tại ứng dụng bên ngoài MongoDB. Subscriber vẫn phải xử lý retry, duplicate và checkpoint một cách có chủ đích.

## 5. Từ change stream sang sự kiện nghiệp vụ: các kiến trúc thường gặp

### Cách A — Suy diễn trực tiếp từ collection nghiệp vụ

Một consumer có thể theo dõi `orders` rồi ánh xạ `update status = PAID` thành `OrderPaid`. Cách này chỉ an toàn khi **mọi** đường ghi dữ liệu tuân thủ cùng một quy tắc, đủ thông tin để chứng minh điều kiện nghiệp vụ và đã xác định được cách xử lý dữ liệu lịch sử, sửa thủ công, update trùng và thay đổi schema.

Nếu có nhiều luồng ghi (API, batch, migration, công cụ quản trị), sự suy diễn dễ sai. Nó cũng có thể tạo kết nối chặt giữa consumer và cấu trúc collection. Đối với nghiệp vụ quan trọng như ghi nhận thu tiền, trừ tồn kho hoặc hoàn tiền, nên phát sự kiện tại điểm mà ứng dụng **biết chắc** sự thật nghiệp vụ đã xảy ra.

### Cách B — Transactional outbox với MongoDB change stream

Ứng dụng xác nhận điều kiện nghiệp vụ, ghi trạng thái và ghi một **outbox record** biểu diễn business event trong cùng một giao dịch MongoDB. Sau khi giao dịch được commit, một publisher theo dõi change stream trên collection `outbox_events`, lấy nội dung sự kiện và chuyển tới broker hoặc hệ thống nhận.

~~~mermaid
flowchart LR
    A[Nhận lệnh đặt hàng] --> B[Kiểm tra quy tắc nghiệp vụ]
    B --> C[MongoDB transaction]
    C --> D[(orders)]
    C --> E[(outbox_events)]
    E --> F[Change stream của outbox]
    F --> G[Publisher]
    G --> H[Broker / bên nhận]
    H --> I[Consumer xử lý idempotent]
~~~

Ở đây có **hai lớp khác nhau**:

1. Thông báo `insert` vào `outbox_events` là **database change event**, dùng làm tín hiệu vận chuyển.
2. Document outbox có `type: OrderPlaced`, `eventId`, `aggregateId`, `payload`... là **business event** mà hệ thống muốn công bố.

Ví dụ tối giản sử dụng `MongoTemplate` để ghi dữ liệu và outbox cùng một transaction:

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {
    private final MongoTemplate mongo;

    public PlaceOrderService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional
    public void placeOrder(String orderId, long totalMinor) {
        // Trong thực tế: xác thực lệnh và kiểm tra quy tắc nghiệp vụ trước khi ghi.
        mongo.insert(new Document("_id", orderId)
            .append("status", "PLACED")
            .append("totalMinor", totalMinor), "orders");

        mongo.insert(new Document("_id", UUID.randomUUID().toString())
            .append("type", "OrderPlaced")
            .append("version", 1)
            .append("aggregateId", orderId)
            .append("occurredAt", Date.from(Instant.now()))
            .append("payload", new Document("totalMinor", totalMinor)),
            "outbox_events");
    }
}
~~~

**Điều kiện bắt buộc của ví dụ:** Phải cấu hình `MongoTransactionManager` và MongoDB hỗ trợ multi-document transaction (replica set hoặc sharded cluster phù hợp). Nếu không có transaction thực sự, hai thao tác insert có thể thành công một phần, làm mất tính nhất quán giữa dữ liệu và outbox. Trong mã sản xuất, còn phải xử lý idempotency của lệnh, khóa định danh, lỗi nghiệp vụ và quy tắc chuyển trạng thái.

Publisher theo dõi `outbox_events` chỉ chuyển tiếp **hợp đồng sự kiện đã ghi**, không đoán lại ý nghĩa từ các trường `orders`. Nếu broker gửi thành công nhưng publisher gặp lỗi trước khi lưu checkpoint, sự kiện có thể được gửi lại. Vì vậy outbox giải quyết bài toán **ghi trạng thái cùng ghi ý định công bố**, còn xử lý giao nhận lặp cần `eventId` và consumer idempotent.

## 6. Thiết kế giao nhận, khôi phục và kiểm thử

### Lưu checkpoint và tránh mất sự kiện

Khi sử dụng resume token để tiếp tục đọc change stream, thứ tự thao tác cần được thiết kế theo luồng thực tế:

1. Nhận thay đổi ở collection outbox cùng resume token.
2. Đẩy business event tới broker; đợi kết quả xác nhận mà hệ thống coi là đã ghi nhận thành công.
3. **Sau đó** mới lưu checkpoint bền vững. Khi khởi động lại, tiếp tục từ checkpoint phù hợp.

Lưu checkpoint **trước khi** broker xác nhận có thể làm mất sự kiện. Lưu sau khi xác nhận có thể khiến một sự kiện được gửi hai lần nếu tiến trình hỏng ở khoảng giữa hai bước. Đây là lý do cần consumer chống xử lý trùng, thường thông qua `eventId` và một cơ chế ghi nhận đã xử lý phù hợp với nghiệp vụ.

Ngoài checkpoint, cần chính sách xử lý khi token hết hiệu lực: tạm dừng, báo lỗi rõ, đối soát/tái quét outbox còn lưu, rồi tiếp tục từ mốc nhất quán. Không xóa outbox sớm hơn khả năng phục hồi của consumer; TTL hay dọn dẹp dữ liệu phải gắn với yêu cầu lưu giữ và phát lại.

### Những điểm cần quan sát khi vận hành

- **Độ trễ phát sự kiện:** thời gian từ lúc outbox commit đến lúc broker xác nhận; cảnh báo khi backlog tăng.
- **Khả năng khôi phục:** thời điểm checkpoint cuối, lỗi resume token, đứt kết nối, thời gian oplog còn đủ phục hồi.
- **Chất lượng hợp đồng:** định danh sự kiện duy nhất, `type` và `version` có quy ước, không để consumer phụ thuộc cấu trúc nội bộ của document.
- **An toàn dữ liệu:** payload chỉ chứa dữ liệu consumer cần; không sao chép thông tin nhạy cảm từ document sang broker một cách mặc định.
- **Khả năng mở rộng:** xử lý sai hỏng, retry có giới hạn, dead-letter/reconciliation phù hợp; bảo toàn thứ tự theo từng aggregate nếu nghiệp vụ yêu cầu và có thiết kế đảm bảo.

### Kịch bản kiểm thử đáng làm

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Insert order hợp lệ | Ghi order và outbox trong cùng transaction; phát `OrderPlaced` đúng một định danh nghiệp vụ |
| Transaction rollback | Không còn order/outbox được ghi nửa chừng; không phát event của giao dịch thất bại |
| Cập nhật `status` bằng script bảo trì | Không bị hiểu nhầm thành `PaymentCaptured` nếu không có bằng chứng nghiệp vụ |
| Publisher gửi broker thành công rồi dừng trước checkpoint | Có thể gửi lại; consumer không thực hiện tác dụng nghiệp vụ hai lần |
| Consumer dừng lâu quá khoảng giữ oplog | Có cảnh báo và quy trình tái đồng bộ/đối soát, không bỏ qua âm thầm |
| Thêm field hoặc đổi cấu trúc lưu `orders` | Hợp đồng `OrderPlaced` vẫn tương thích hoặc có nâng phiên bản rõ ràng |

Khi kiểm thử tích hợp change stream và transaction, dùng MongoDB replica set thực (chẳng hạn môi trường Testcontainers được cấu hình đúng) thay vì giả định MongoDB standalone sẽ có cùng hành vi.

## 7. Chọn công cụ đúng với mục tiêu

Nếu mục tiêu là **đồng bộ chỉ mục tìm kiếm, làm mới cache, nắm bắt thay đổi document hoặc điều khiển outbox publisher**, change stream là công cụ phù hợp. Nó cung cấp dấu vết về thao tác dữ liệu và cách tiếp tục đọc, nhưng consumer vẫn cần thiết kế retry và kiểm tra tính nhất quán.

Nếu mục tiêu là **thông báo một sự thật nghiệp vụ cho hệ thống khác** (ví dụ đơn hàng đã chốt, thanh toán đã thu, hoàn tiền đã duyệt), hãy định nghĩa sự kiện bằng ngôn ngữ nghiệp vụ và phát tại nơi kiểm tra được điều kiện của nó. Với Spring Data MongoDB, transactional outbox kết hợp change stream thường là một lựa chọn thực dụng để vận chuyển sự kiện đó ra ngoài một cách bền vững.

**Ghi nhớ:** `update orders.status` là thông tin về dữ liệu; `PaymentCaptured` là cam kết về nghiệp vụ. Chúng có thể liên quan, nhưng không thể thay thế nhau chỉ dựa vào sự giống nhau của giá trị một trường.
