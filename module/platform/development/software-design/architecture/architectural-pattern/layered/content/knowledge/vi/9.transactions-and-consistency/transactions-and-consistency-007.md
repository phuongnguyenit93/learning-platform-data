# Thiết kế thao tác lũy đẳng khi yêu cầu được gửi lại

Trong hệ thống phân tầng, một ca sử dụng có thể được gọi nhiều lần dù người dùng chỉ thực hiện một hành động. Client có thể gửi lại request sau khi timeout, trình duyệt có thể gửi hai lần do người dùng nhấn nút liên tiếp, hoặc message broker có thể chuyển lại một message khi consumer chưa xác nhận đã xử lý. Nếu mỗi lần nhận đều tạo ra một thay đổi mới, hệ thống có thể tạo đơn hàng trùng, trừ tiền nhiều lần hoặc gửi thông báo lặp.

Một thao tác **lũy đẳng (idempotent)** bảo đảm rằng thực hiện cùng một ý định nhiều lần có hiệu ứng nghiệp vụ tương đương với thực hiện một lần. Thiết kế này giúp ứng dụng chịu được retry và giao nhận lặp mà vẫn bảo vệ trạng thái dữ liệu.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, tầng Presentation tiếp nhận request, Application điều phối ca sử dụng, Domain bảo vệ quy tắc và Infrastructure lưu trạng thái hoặc gọi hệ thống ngoài. Tính lũy đẳng cần được thiết kế xuyên qua các ranh giới đó: nhận diện đúng yêu cầu lặp, phối hợp giao dịch và bảo đảm side effect không bị thực hiện nhiều lần.

## 1. Vì sao một yêu cầu có thể được gửi nhiều lần?

Retry thường xảy ra trong những tình huống hợp lệ:

- Client gửi request nhưng không nhận được response trước thời hạn timeout.
- Server đã commit transaction, nhưng kết nối bị đứt trước khi response đến client.
- Proxy, gateway hoặc thư viện HTTP tự retry khi gặp lỗi mạng tạm thời.
- Người dùng nhấn nút thanh toán hoặc đặt hàng nhiều lần vì giao diện chưa phản hồi.
- Message broker giao lại message khi consumer xử lý xong nhưng chưa kịp xác nhận.
- Một tác vụ nền được chạy lại sau khi worker bị dừng đột ngột.

Điểm khó là bên gửi không luôn biết lần xử lý trước đã thành công hay chưa. Ví dụ, server có thể đã lưu đơn hàng, nhưng client chỉ thấy timeout. Nếu client gửi lại một POST mới mà server không nhận ra đó là cùng một ý định, đơn hàng thứ hai có thể được tạo.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Presentation
    participant A as Application
    participant DB as Database
    C->>P: POST /orders (request K)
    P->>A: PlaceOrder(K)
    A->>DB: Tạo đơn và lưu kết quả
    DB-->>A: COMMIT thành công
    A-->>P: OrderCreated
    Note over P,C: Response bị mất trên mạng
    C->>P: Gửi lại POST /orders (request K)
    P->>A: PlaceOrder(K)
    A->>DB: Tra cứu idempotency key K
    DB-->>A: Đã hoàn tất, trả kết quả cũ
    A-->>P: OrderCreated (cùng orderId)
    P-->>C: Response của đơn hàng ban đầu
~~~

Server không thể chỉ dựa vào việc client có nhận được response hay không. Nó cần một định danh ổn định cho một ý định nghiệp vụ và một nơi lưu lại kết quả xử lý.

## 2. Lũy đẳng nghĩa là gì?

Một thao tác lũy đẳng có cùng hiệu ứng nghiệp vụ khi được thực hiện một lần hoặc nhiều lần với cùng một ý định. Nếu gọi thao tác đặt trạng thái giao hàng thành DELIVERED nhiều lần, trạng thái cuối vẫn là DELIVERED. Ngược lại, thao tác cộng thêm 1 vào số lượng mỗi lần được gọi không tự lũy đẳng: gửi lại hai lần sẽ làm số lượng tăng hai lần.

| Thao tác | Tính chất | Lý do |
|---|---|---|
| Đặt trạng thái đơn thành CANCELLED | Có thể lũy đẳng | Các lần gọi cùng đưa trạng thái về một giá trị |
| Lấy chi tiết đơn hàng | Lũy đẳng về hiệu ứng trạng thái | Query không thay đổi dữ liệu nghiệp vụ |
| Tạo một đơn hàng mới bằng POST | Không tự lũy đẳng | Mỗi request có thể tạo một đơn mới |
| Cộng thêm một khoản vào số dư | Không tự lũy đẳng | Mỗi lần gọi có thể làm số dư tăng thêm |
| Ghi nhận thanh toán với cùng mã yêu cầu duy nhất | Có thể lũy đẳng nếu được bảo vệ đúng | Hệ thống nhận diện và không ghi nhận cùng ý định hai lần |

Lũy đẳng không nhất thiết có nghĩa response phải giống từng byte trong mọi lần gọi. Hệ thống thường chọn trả lại cùng kết quả nghiệp vụ, chẳng hạn cùng orderId và trạng thái tạo đơn ban đầu. Header thời gian hoặc thông tin tracing có thể khác. Điều quan trọng là không phát sinh thêm hiệu ứng nghiệp vụ.

Cũng cần phân biệt lũy đẳng với “exactly once”. Trong hệ thống phân tán, mạng và tiến trình có thể lỗi ở nhiều thời điểm; rất khó bảo đảm một thông điệp chỉ được truyền và xử lý đúng một lần từ đầu đến cuối. Thiết kế thực tế thường chấp nhận giao nhận ít nhất một lần (at-least-once), rồi dùng idempotency và deduplication để hiệu ứng cuối cùng không bị nhân đôi.

## 3. Chọn định danh cho một ý định: Idempotency Key

Với một thao tác không tự lũy đẳng như tạo đơn hoặc thanh toán, client có thể gửi một **Idempotency Key**. Key là mã duy nhất đại diện cho một ý định nghiệp vụ cụ thể. Nếu client retry cùng ý định, nó phải dùng lại key đó. Khi người dùng bắt đầu một thao tác mới, client tạo key mới.

Ví dụ request:

~~~http
POST /api/orders
Idempotency-Key: 6a9d3b10-2ef5-4b76-8f3e-14dfe1a8c702
Content-Type: application/json

{
  "productId": "d9f0c19b-7b28-4c82-b6c5-5d0a10c4e300",
  "quantity": 2
}
~~~

Key nên được giới hạn theo phạm vi phù hợp, chẳng hạn tenant hoặc customer, tên thao tác và key:

- tenant/customer: ngăn một người dùng vô tình hoặc cố ý đụng key của người khác.
- operation: cùng một chuỗi key cho thao tác tạo đơn không xung đột với thao tác hoàn tiền.
- idempotency key: định danh lần thực hiện logic.

Một định danh có thể là UUID ngẫu nhiên do client tạo, hoặc được cấp bởi một API khởi tạo thao tác. Key không thay thế xác thực và phân quyền. Server vẫn phải xác thực người gọi và kiểm tra họ có quyền truy cập tài nguyên.

Không nên tạo key mới cho mỗi lần retry. Nếu key thay đổi, server sẽ coi đó là một ý định mới và có thể thực hiện lại nghiệp vụ.

## 4. Lưu dấu vết xử lý và kết quả

Server cần lưu trạng thái của key để nhận biết request đã được xử lý. Một bảng idempotency có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| tenant_id / customer_id | Phạm vi sở hữu key |
| operation | Tên thao tác, ví dụ CREATE_ORDER |
| idempotency_key | Định danh ý định |
| request_hash | Dấu vân tay nội dung yêu cầu |
| status | PROCESSING, COMPLETED hoặc trạng thái lỗi có thể retry |
| resource_id | ID tài nguyên được tạo hoặc thay đổi |
| response_status | Mã HTTP của kết quả ban đầu nếu cần phát lại |
| response_body | Nội dung response đã lưu nếu chính sách yêu cầu |
| created_at / expires_at | Thời điểm tạo và thời điểm hết hạn lưu key |

Một ràng buộc duy nhất trên bộ ba tenant, operation và idempotency_key là điều kiện quan trọng để nhiều request đồng thời không cùng chiếm một key.

~~~sql
CREATE TABLE idempotency_record (
    tenant_id        UUID NOT NULL,
    operation        VARCHAR(80) NOT NULL,
    idempotency_key  VARCHAR(120) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    status           VARCHAR(20) NOT NULL,
    resource_id      UUID,
    response_status  INTEGER,
    response_body    TEXT,
    created_at       TIMESTAMP NOT NULL,
    expires_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation, idempotency_key)
);
~~~

Schema trên chỉ minh họa. Kiểu JSON, UUID, timestamp và cách lưu response cần điều chỉnh theo database. Không nhất thiết phải lưu toàn bộ response body; nếu tài nguyên có thể được truy xuất an toàn bằng resource_id và kết quả không thay đổi, có thể lưu ID cùng thông tin cần thiết rồi dựng lại response.

### Kiểm tra request fingerprint

Nếu một key đã được dùng với payload khác, server không nên trả kết quả của request cũ cho ý định mới. Ví dụ, client gửi key K với quantity = 2 rồi vô tình dùng lại K với quantity = 5. Hệ thống cần phát hiện sự khác biệt và trả lỗi xung đột theo hợp đồng API.

Server có thể tính request_hash từ biểu diễn chuẩn hóa của các trường có ý nghĩa đối với ý định: customer, product, quantity, loại tiền và các tùy chọn ảnh hưởng nghiệp vụ. Không nên hash toàn bộ JSON thô nếu thứ tự thuộc tính hoặc định dạng khoảng trắng có thể thay đổi nhưng ý nghĩa không đổi. Cũng không nên đưa các header thay đổi theo mỗi lần gửi như trace ID vào fingerprint.

## 5. Quy trình xử lý request có Idempotency Key

Một luồng đồng bộ có thể hoạt động như sau:

1. Presentation xác thực request, kiểm tra định dạng key và lấy danh tính người gọi.
2. Application tạo command và xác định phạm vi key cùng request fingerprint.
3. Infrastructure cố gắng tạo bản ghi idempotency với ràng buộc unique.
4. Nếu key đã hoàn tất và fingerprint khớp, Application trả lại kết quả của lần xử lý trước.
5. Nếu key đã tồn tại nhưng fingerprint khác, trả lỗi xung đột.
6. Nếu đây là lần đầu, thực hiện quy tắc nghiệp vụ và ghi thay đổi cùng kết quả idempotency trong một transaction.
7. Commit transaction rồi trả response.

Điểm mấu chốt là **claim key, thay đổi nghiệp vụ và lưu kết quả phải được phối hợp nguyên tử khi chúng cùng nằm trong một database**. Nếu đơn hàng đã được commit nhưng bản ghi idempotency chưa được lưu, retry có thể tạo đơn thứ hai. Nếu bản ghi idempotency báo COMPLETED nhưng thay đổi nghiệp vụ bị rollback, client có thể nhận kết quả thành công giả.

~~~mermaid
flowchart TD
    S[Nhận request và key] --> V[Authenticate, validate và tính fingerprint]
    V --> C{Key đã tồn tại?}
    C -->|Chưa| R[Claim key với unique constraint]
    R --> B[Thực hiện nghiệp vụ]
    B --> T[Lưu thay đổi và kết quả trong transaction]
    T --> O[Commit và trả response]
    C -->|Có| H{Fingerprint khớp?}
    H -->|Không| X[Trả lỗi xung đột]
    H -->|Có| D{Đã hoàn tất?}
    D -->|Có| P[Phát lại kết quả trước]
    D -->|Đang xử lý| W[Trả trạng thái đang xử lý hoặc hướng dẫn retry]
~~~

Không được triển khai bằng một chuỗi “đọc xem key có chưa, nếu chưa thì mới insert” mà không có bảo vệ đồng thời. Hai request có thể cùng đọc thấy chưa tồn tại rồi cùng thực hiện. Unique constraint hoặc cơ chế atomic claim/lock ở database mới là lớp bảo vệ cuối cùng.

### Phối hợp transaction trong ứng dụng Spring

Với thao tác chỉ thay đổi dữ liệu trong cùng một database, có thể thực hiện việc claim key, ghi đơn hàng và lưu kết quả trong cùng transaction:

~~~java
@Service
public class PlaceOrderService {
    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;

    public PlaceOrderService(
            IdempotencyRepository idempotency,
            OrderRepository orders) {
        this.idempotency = idempotency;
        this.orders = orders;
    }

    @Transactional
    public PlaceOrderResult execute(
            PlaceOrderCommand command,
            IdempotencyScope scope,
            String key,
            String requestHash) {

        var existing = idempotency.find(scope, key);

        if (existing.isPresent()) {
            var record = existing.get();

            if (!record.matches(requestHash)) {
                throw new IdempotencyKeyConflictException();
            }

            if (record.isCompleted()) {
                return record.toResult();
            }

            throw new RequestAlreadyProcessingException();
        }

        // Phải được thực hiện bằng insert/claim có unique constraint.
        // Nếu một request khác cùng claim key, chỉ một request được thắng.
        idempotency.claim(scope, key, requestHash);

        Order order = Order.place(
                command.customerId(),
                command.productId(),
                command.quantity()
        );
        orders.save(order);

        var result = new PlaceOrderResult(order.getId());
        idempotency.complete(scope, key, result);

        return result;
    }
}
~~~

Đây là ví dụ mô tả luồng, không phải implementation hoàn chỉnh cho mọi database. claim phải dựa vào thao tác atomic được database bảo vệ bằng unique constraint. Nếu một request khác thắng cuộc đua, request thua cần đọc lại bản ghi sau khi transaction của request thắng đã commit, rồi phát lại kết quả hoặc trả trạng thái đang xử lý. Cách xử lý unique violation và transaction rollback phụ thuộc database và framework; không nên bắt lỗi constraint trong cùng transaction rồi tiếp tục dùng một transaction đã bị đánh dấu rollback-only.

Trong ví dụ đồng bộ, bản ghi key và thay đổi đơn hàng được commit cùng nhau. Nếu xử lý nghiệp vụ thất bại trước commit, transaction rollback cả hai. Nếu commit thành công nhưng response bị mất, retry sẽ thấy bản ghi COMPLETED và trả lại cùng orderId.

## 6. Xử lý request đồng thời và trạng thái đang xử lý

Hai request cùng key có thể đến gần như đồng thời. Hệ thống phải xác định rõ request nào sở hữu việc thực hiện:

- Một request claim key thành công và xử lý nghiệp vụ.
- Request còn lại gặp unique conflict hoặc đọc được bản ghi đang PROCESSING.
- Request thứ hai không chạy lại nghiệp vụ. Nó có thể đợi trong giới hạn thời gian, trả trạng thái “đang xử lý” kèm hướng dẫn retry, hoặc trả 409/425 theo hợp đồng API.

Nếu thao tác ngắn và mọi việc nằm trong một transaction, bản ghi idempotency có thể chưa hiển thị trạng thái PROCESSING cho transaction khác trước khi commit. Request cạnh tranh sẽ bị database điều phối qua unique constraint; sau khi transaction đầu commit, request sau đọc kết quả hoàn tất. Đây thường là mô hình đơn giản.

Với tác vụ dài hoặc xử lý bất đồng bộ, có thể commit trạng thái PROCESSING trước, kèm lease_until hoặc owner token. Worker xử lý rồi cập nhật COMPLETED. Khi worker chết, một tiến trình phục hồi có thể nhận lại công việc sau khi lease hết hạn. Cần dùng cơ chế claim có kiểm soát để hai worker không cùng xử lý một tác vụ.

Không nên giữ một transaction database mở trong nhiều phút chỉ để biểu diễn tác vụ đang chạy. Giao dịch dài giữ lock và connection, làm giảm khả năng phục vụ. Với xử lý bất đồng bộ, hãy lưu ý định công việc và outbox trong transaction ngắn, sau đó xử lý bên ngoài.

## 7. Phân biệt lỗi có thể retry và kết quả đã hoàn tất

Không phải mọi lỗi đều nên được lưu như một kết quả hoàn tất:

- Lỗi validation trước khi chấp nhận command thường có thể trả ngay; tùy hợp đồng, key có thể chưa được claim.
- Lỗi nghiệp vụ xác định như sản phẩm không còn bán có thể được lưu hoặc không lưu như kết quả cuối cùng, miễn chính sách được định nghĩa rõ.
- Lỗi tạm thời như database unavailable hoặc timeout trước khi commit thường cần cho phép retry.
- Lỗi sau khi side effect bên ngoài đã có thể xảy ra nhưng chưa nhận được kết quả là tình huống không xác định; không được đơn giản xóa key và gọi lại như thể chưa có gì xảy ra.

Một chính sách thường dùng là chỉ đánh dấu COMPLETED cho kết quả đã được quyết định và commit. Với lỗi tạm thời trước khi có side effect, transaction rollback để lần retry có thể thực hiện. Với tác vụ bất đồng bộ, record có thể chuyển sang FAILED_RETRYABLE hoặc FAILED_FINAL tùy nguyên nhân.

Điều quan trọng là xác định trạng thái và hành vi khi retry cho từng loại lỗi. Nếu mọi exception đều được lưu thành COMPLETED, client sẽ không thể retry lỗi tạm thời. Nếu mọi lỗi đều xóa key, side effect đã thực hiện có thể bị lặp.

## 8. Bảo vệ side effect ngoài database

Một transaction cơ sở dữ liệu không tự động bao phủ lời gọi HTTP tới cổng thanh toán, gửi email hoặc publish message. Ví dụ, ứng dụng có thể gọi thanh toán thành công nhưng bị timeout trước khi lưu trạng thái đơn hàng. Retry toàn bộ use case có thể thu tiền lần thứ hai.

Có một số biện pháp:

**Dùng idempotency key ở nhà cung cấp.** Nếu cổng thanh toán hỗ trợ key, gửi cùng một key cho cùng một ý định thanh toán. Khi request bị retry, nhà cung cấp có thể trả kết quả của giao dịch đã thực hiện. Phạm vi key và thời gian lưu của nhà cung cấp cần được kiểm tra.

**Dùng Transactional Outbox cho việc phát sự kiện.** Trong cùng transaction với thay đổi nghiệp vụ và bản ghi idempotency, lưu một outbox message. Worker đọc outbox và gửi message ra broker. Nếu worker gửi thành công nhưng chết trước khi đánh dấu đã gửi, message có thể được gửi lại; consumer vẫn cần deduplicate theo event ID hoặc xử lý lũy đẳng.

**Dùng state machine và reconciliation.** Với thanh toán hoặc tích hợp không hỗ trợ idempotency, lưu trạng thái như PENDING, AUTHORIZED, CAPTURED hoặc UNKNOWN. Khi kết quả không rõ, truy vấn nhà cung cấp bằng merchant reference hoặc transaction reference để đối soát trước khi gửi lại. Có thể cần thao tác bù trừ nếu các bước không thể rollback.

~~~mermaid
flowchart LR
    A[Application transaction] --> B[(Order + Idempotency + Outbox)]
    B --> C[Outbox worker]
    C --> D[External provider / Broker]
    D --> E[Consumer]
    E --> F[(Deduplication record + Effect)]
~~~

Đây là phối hợp nhiều bước, không phải một transaction phân tán tự động. Outbox giúp không mất ý định phát sự kiện khi database commit, nhưng không tự bảo đảm consumer chỉ nhận một lần. Consumer cần idempotency riêng.

## 9. Key scope, bảo mật và thời hạn lưu

Idempotency key cần được quản lý như dữ liệu điều khiển giao dịch:

- Phạm vi key phải gắn với tenant hoặc người dùng và tên operation để tránh xung đột ngoài ý muốn.
- Trước khi phát lại kết quả, vẫn phải xác thực người gọi và kiểm tra quyền truy cập tài nguyên. Không để key trở thành token cho phép đọc dữ liệu của người khác.
- Không ghi key hoặc payload nhạy cảm vào log theo cách làm lộ thông tin. Có thể log một dạng hash hoặc mã tương quan an toàn.
- Giới hạn độ dài và định dạng key để tránh lạm dụng tài nguyên.
- Quy định thời hạn lưu phù hợp với khoảng retry và thời gian đối soát. Xóa key quá sớm có thể khiến một retry muộn tạo tác dụng lần nữa.
- Khi hết hạn, cần có chính sách rõ: từ chối key cũ, cho phép dùng lại sau khi cleanup, hay duy trì tombstone lâu hơn. Không nên để hành vi phụ thuộc ngẫu nhiên vào lịch dọn dữ liệu.

Nếu response chứa dữ liệu cá nhân hoặc dữ liệu có thể thay đổi quyền truy cập, cân nhắc lưu resource ID và dựng lại response sau khi kiểm tra quyền thay vì phát lại nguyên văn response body cũ.

## 10. Thiết kế API và phản hồi khi request được gửi lại

Presentation nên công bố rõ cách sử dụng key. Ví dụ, endpoint tạo đơn yêu cầu header Idempotency-Key; tài liệu API nói client phải giữ nguyên key khi retry cùng một hành động.

Các trường hợp có thể được biểu diễn như sau:

| Tình huống | Hành vi API gợi ý |
|---|---|
| Key mới, request hợp lệ | Thực hiện và trả kết quả tạo tài nguyên |
| Key đã hoàn tất, fingerprint giống | Trả lại kết quả của lần xử lý trước |
| Key đã dùng với payload khác | Trả lỗi xung đột, chẳng hạn 409 Conflict |
| Key đang được xử lý | Trả trạng thái đang xử lý hoặc cho phép client retry sau |
| Key hết hạn | Áp dụng chính sách hết hạn đã công bố |

Mã HTTP cụ thể phụ thuộc hợp đồng API. Có thể dùng 202 Accepted cho công việc bất đồng bộ đã được tiếp nhận nhưng chưa hoàn tất; 409 Conflict hoặc một mã phù hợp khác cho key đang được dùng với payload khác. Response phát lại nên giữ ý nghĩa của kết quả gốc, chẳng hạn cùng resource ID và status code ban đầu nếu API đã cam kết điều đó.

Không nên coi mọi request có cùng body là cùng một ý định. Người dùng có thể hợp pháp tạo hai đơn hàng giống hệt nhau. Chính key ổn định mới xác định client đang retry cùng một hành động; fingerprint chỉ giúp phát hiện key bị dùng sai với nội dung khác.

## 11. Kiểm thử tính lũy đẳng

Kiểm thử nên chứng minh hiệu ứng nghiệp vụ chỉ xảy ra một lần trong các trường hợp retry:

- Gửi hai lần cùng key và cùng payload: chỉ có một đơn hàng được tạo, hai response trỏ tới cùng orderId.
- Gửi cùng key nhưng payload khác: request sau bị từ chối theo hợp đồng.
- Gửi hai request đồng thời cùng key: chỉ một request được quyền thực hiện side effect.
- Transaction rollback trước commit: lần retry hợp lệ có thể thực hiện lại.
- Commit thành công nhưng response bị mất: retry trả lại kết quả đã lưu.
- Người dùng khác hoặc tenant khác dùng cùng chuỗi key: không được đọc kết quả ngoài phạm vi.
- Consumer nhận lại cùng event: không áp dụng hiệu ứng nghiệp vụ lần thứ hai.
- Key hết hạn: hành vi đúng theo chính sách retention đã định nghĩa.

Với Spring, có thể dùng integration test và chạy các request song song bằng ExecutorService hoặc CountDownLatch để kiểm tra unique constraint và transaction. Test cần xác minh số bản ghi nghiệp vụ, số lần gọi provider giả và kết quả được trả cho từng request. Một unit test chỉ mock repository không đủ để chứng minh race condition được database ngăn chặn.

## 12. Checklist thiết kế thao tác lũy đẳng

Trước khi triển khai endpoint hoặc consumer có thể được retry, hãy tự hỏi:

1. Đâu là một ý định nghiệp vụ và ai tạo định danh ổn định cho ý định đó?
2. Key được giới hạn theo tenant/user và operation như thế nào?
3. Server có kiểm tra fingerprint để phát hiện key bị dùng với payload khác không?
4. Unique constraint hoặc atomic claim nào ngăn hai request cùng thực hiện?
5. Thay đổi nghiệp vụ và kết quả idempotency có được commit nguyên tử không?
6. Nếu request đang xử lý, client sẽ nhận phản hồi và retry theo cách nào?
7. Side effect ngoài database có hỗ trợ key riêng, outbox, deduplication hoặc reconciliation không?
8. Key được giữ bao lâu và xử lý thế nào khi hết hạn?
9. Có test retry, lỗi sau commit, cạnh tranh đồng thời và message giao lại không?

Thiết kế lũy đẳng không chỉ là thêm một header vào controller. Nó là hợp đồng xuyên tầng về việc nhận diện một ý định, phối hợp trạng thái và phát lại kết quả. Khi Presentation giữ key, Application điều phối ca sử dụng, Domain bảo vệ quy tắc và Infrastructure dùng transaction, unique constraint cùng cơ chế deduplication phù hợp, hệ thống có thể chịu được retry mà không nhân đôi hiệu ứng nghiệp vụ.

