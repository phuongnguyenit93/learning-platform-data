
# Ranh giới giao dịch cơ sở dữ liệu và xác nhận thông điệp

## 1. Mục tiêu bài học

Một message có thể đã được xử lý và ghi vào database thành công, nhưng broker vẫn giao lại vì ACK chưa được ghi nhận. Ngược lại, nếu message được ACK trước khi database commit, process có thể dừng và làm mất công việc. Hai hệ thống có vòng đời và cơ chế xác nhận riêng; hiểu nhầm ranh giới này là nguyên nhân phổ biến gây mất dữ liệu hoặc xử lý trùng.

Trong module **SPRING_CLOUD_FUNCTION**, logic nghiệp vụ được tổ chức bằng `Supplier`, `Function` và `Consumer`, đăng ký qua `FunctionCatalog` và triển khai qua HTTP, sự kiện hoặc serverless. Function xác định cách xử lý payload; adapter/binder điều phối nhận message và ACK; transaction manager điều phối commit/rollback dữ liệu. Ba trách nhiệm này phải phối hợp rõ ràng.

Bài thuộc chương **Độ tin cậy**, tập trung vào **ranh giới giao dịch cơ sở dữ liệu và xác nhận thông điệp**. Sau bài học, bạn có thể:

- Phân biệt DB commit, Function completion và broker ACK.
- Mô tả cửa sổ lỗi khi ACK trước hoặc sau commit.
- Đặt transaction ở application service được Function gọi qua Spring proxy.
- Dùng inbox/idempotency để xử lý redelivery sau commit.
- Dùng outbox khi cần ghi database và phát sự kiện.
- Hiểu giới hạn của transaction manager, binder transaction và distributed transaction.
- Phân biệt consumer imperative với reactive/asynchronous lifecycle.
- Kiểm thử rollback, redelivery và ACK theo binder thực tế.

> **Nguyên tắc thiết kế:** Với consumer ghi database, để transaction commit thành công trước khi adapter xác nhận message đã xử lý; chấp nhận rằng ACK có thể thất bại sau commit và bảo vệ lần giao lại bằng inbox/idempotency. Không giả định DB commit và broker ACK là một thao tác nguyên tử.

## 2. Ba sự kiện khác nhau: Function hoàn tất, DB commit, message ACK

Một luồng message có ba mốc:

1. **Function completion:** code xử lý của Function/Consumer kết thúc bình thường hoặc báo lỗi.
2. **Database commit:** transaction manager xác nhận các thay đổi DB được commit.
3. **Message acknowledgement:** broker/binder ghi nhận message đã được xử lý theo delivery protocol.

Ba mốc có liên hệ nhưng không đồng nghĩa:

| Sự kiện | Ai quản lý? | Ý nghĩa |
|---|---|---|
| Function hoàn tất | Application + adapter | Lời gọi xử lý đã trả về hoặc Publisher đã kết thúc |
| DB commit | Database + transaction manager | Các thay đổi thuộc transaction đã được xác nhận |
| ACK | Binder/broker/client protocol | Message được xác nhận theo cơ chế giao nhận |

Một lời gọi `repository.save(entity)` chưa chắc đã commit. ORM có thể trì hoãn SQL đến flush/commit; lỗi constraint hoặc connection có thể chỉ xuất hiện ở cuối transaction.

Tương tự, `Consumer.accept(message)` trả về không phải một lệnh ACK portable. Trong consumer imperative, binder thường dùng kết quả xử lý để quyết định hoàn tất/ACK theo cấu hình. Trong reactive function, completion của Publisher có vai trò khác và adapter phải quản lý subscription. Với manual ACK, ứng dụng có thể phải gọi API riêng của binder.

### 2.1. Sơ đồ vòng đời phổ biến

~~~text
Broker giao message
       |
       v
Spring Cloud Stream adapter
       |
       v
Spring Cloud Function Consumer
       |
       v
Application service
       |
       v
DB transaction BEGIN
       |
       +-- đọc/ghi dữ liệu
       +-- inbox marker
       +-- outbox event (nếu cần)
       |
       v
DB COMMIT
       |
       v
Function invocation hoàn tất
       |
       v
Binder ACK theo delivery policy
~~~

Đây là mô hình khái niệm cho consumer imperative có transaction DB kết thúc trước khi Function trả về. Thứ tự ACK thực tế và cách xử lý exception phải xác minh theo binder, phiên bản và chế độ ACK đang dùng.

### 2.2. Vì sao cần tách ba mốc?

- Function có thể trả về trước khi tác vụ async hoàn tất nếu code tự fire-and-forget.
- DB có thể commit rồi response/ACK bị mất trên mạng.
- Binder có thể retry hoặc redeliver message sau khi thấy lỗi/không nhận được ACK.
- Một Function thuần có thể hoàn tất mà chưa có bất kỳ side effect nào.

Khi điều tra sự cố, cần biết chính xác **mốc nào đã xảy ra**, không chỉ ghi “message thất bại”.

## 3. Hai thứ tự ACK/commit và hậu quả

### 3.1. ACK trước, commit sau: có thể mất công việc

~~~text
Broker giao message
       |
       v
ACK được gửi/offset được xác nhận
       |
       v
DB transaction ghi Quote
       |
       v
Process chết trước COMMIT
       |
       v
Broker không giao lại
       |
       v
DB không có Quote, message đã được xác nhận
~~~

Đây là cửa sổ **mất dữ liệu**. Nếu message đã được ACK/offset commit mà DB rollback, broker có thể không gửi lại. Việc ứng dụng ACK quá sớm không an toàn.

### 3.2. Commit trước, ACK sau: có thể redelivery nhưng có thể chống trùng

~~~text
Broker giao message
       |
       v
DB transaction ghi Quote + inbox
       |
       v
DB COMMIT thành công
       |
       v
Process chết trước ACK
       |
       v
Broker giao lại message
       |
       v
Inbox nhận diện event đã commit
       |
       v
Không ghi Quote lần hai; xử lý hoàn tất
~~~

Đây là thứ tự thường phù hợp cho consumer ghi DB theo mô hình at-least-once. Nó ưu tiên không mất message; đổi lại ứng dụng phải chịu được redelivery bằng inbox/idempotency.

### 3.3. Bảng so sánh

| Thứ tự | Cửa sổ lỗi | Hậu quả | Cách phòng vệ |
|---|---|---|---|
| ACK rồi mới commit DB | Process chết giữa ACK và commit | Mất công việc | Tránh ACK sớm; commit trước ACK |
| Commit DB rồi ACK | Process chết giữa commit và ACK | Message được giao lại | Inbox/unique key để no-op |
| Function trả về trước khi async DB hoàn tất | Binder có thể coi xử lý đã xong | ACK trước side effect | Chờ completion/error theo contract |
| ACK và DB commit ở hai hệ thống độc lập | Một bên thành công, bên kia thất bại | Không có atomicity end-to-end | Inbox/outbox, idempotency hoặc distributed transaction có chủ đích |

**Commit trước ACK không tạo exactly-once.** Nó tạo cửa sổ redelivery có thể xử lý an toàn nếu database lưu dấu và side effect được bảo vệ.

## 4. Spring Cloud Function và ranh giới adapter


### Các kiểu dữ liệu và port dùng trong ví dụ

~~~java
package example.functions;

public final class OrderModels {

    private OrderModels() {}

    public record OrderCreated(
            String tenantId,
            String eventId,
            String orderId,
            String payloadHash) {}
}
~~~

`payloadHash` nên được tính ở boundary tin cậy từ payload canonical đã xác thực; không mặc định tin hash do client tự gửi. Ví dụ dùng hash đã được chuẩn hóa để tập trung vào ranh giới transaction/ACK.

Các port được service sử dụng:

~~~java
package example.functions;

public interface ProcessedMessageRepository {
    boolean insertIfAbsent(
            String tenantId, String eventId, String payloadHash);

    String findPayloadHash(String tenantId, String eventId);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.OrderCreated;

public interface OrderRepository {
    void apply(OrderCreated event);
}
~~~

~~~java
package example.functions;

import example.functions.OrderModels.OrderCreated;

public interface OutboxRepository {
    void appendOrderUpdated(OrderCreated event);
}
~~~

~~~java
package example.functions;

public class DuplicateMessageConflictException
        extends RuntimeException {
    public DuplicateMessageConflictException(String message) {
        super(message);
    }
}
~~~

Các interface trên là hợp đồng minh họa. Adapter database phải triển khai các thao tác ghi/đọc trong cùng transaction manager; `insertIfAbsent` cần unique constraint/SQL nguyên tử.


Spring Cloud Function tập trung vào logic tái sử dụng. Ví dụ một Consumer:

~~~java
package example.functions;

import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import example.functions.OrderModels.OrderCreated;

@Configuration
public class OrderFunctions {

    @Bean
    public Consumer<OrderCreated> processOrder(
            OrderApplicationService service) {
        return service::handle;
    }
}
~~~

`OrderApplicationService` là application service do Spring inject. Consumer chỉ chuyển message vào service. Transaction nên đặt tại method application service hoặc component có ranh giới giao dịch rõ ràng, không phụ thuộc việc bean Function được gọi qua HTTP hay binder.

Ví dụ cấu hình lựa chọn Function:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: order-created
          group: order-service
~~~

Cấu hình minh họa việc chọn bean và binding. Ứng dụng cần thêm binder, serializer/converter, error handling và ACK/retry policy theo môi trường thực tế.

### 4.1. FunctionCatalog không quản lý DB transaction và ACK

`FunctionCatalog.lookup("processOrder")` giúp tìm Function theo tên. Nó không tự:

- Mở transaction database.
- Commit hoặc rollback dữ liệu.
- Gửi ACK theo một API chung cho mọi broker.
- Đảm bảo message chỉ được giao một lần.
- Tạo inbox/outbox hoặc unique constraint.
- Kết hợp transaction DB với transaction broker.

Các trách nhiệm này nằm ở application service, transaction manager, adapter và broker/binder.

### 4.2. Cùng một Function có thể được gọi từ nhiều adapter

- HTTP adapter nhận request rồi gọi Function.
- Stream binder nhận message rồi gọi Function.
- Serverless adapter ánh xạ event rồi gọi Function.

Mỗi adapter có lifecycle và cách phản hồi khác nhau. Một `Consumer<OrderCreated>` không thể tự giả định luôn có broker ACK; khi được gọi từ HTTP, kết quả được biểu diễn bằng response. Khi được gọi từ serverless, kết quả theo contract của trigger. Hãy để domain/application service quản lý transaction dữ liệu; adapter chịu trách nhiệm xác nhận giao thức.

## 5. Đặt @Transactional ở application service

Một application service imperative có thể gom inbox, cập nhật dữ liệu nghiệp vụ và outbox vào cùng transaction:

~~~java
package example.functions;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import example.functions.OrderModels.OrderCreated;

@Service
public class OrderApplicationService {

    private final ProcessedMessageRepository inbox;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            ProcessedMessageRepository inbox,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void handle(OrderCreated event) {
        boolean claimed = inbox.insertIfAbsent(
                event.tenantId(),
                event.eventId(),
                event.payloadHash());

        if (!claimed) {
            String oldHash = inbox.findPayloadHash(
                    event.tenantId(), event.eventId());

            if (!event.payloadHash().equals(oldHash)) {
                throw new DuplicateMessageConflictException(
                        "Event ID duoc tai su dung voi payload khac");
            }

            return; // Event đã commit trong lần xử lý trước.
        }

        orders.apply(event);
        outbox.appendOrderUpdated(event);
    }
}
~~~

`ProcessedMessageRepository`, `OrderRepository` và `OutboxRepository` là các port/repository minh họa. Chúng phải dùng cùng datasource và transaction manager nếu cần commit atomically. `insertIfAbsent` cần được triển khai bằng unique constraint và lệnh insert nguyên tử, không phải `SELECT` rồi `INSERT` rời rạc.

Với consumer imperative gọi service qua Spring proxy, transaction interceptor bắt đầu transaction, chạy method và **commit trước khi lời gọi proxy trả về**. Consumer chỉ kết thúc sau đó nếu service không ném lỗi.

### 5.1. Consumer gọi qua proxy

~~~text
Spring Cloud Function Consumer
       |
       v
OrderApplicationService proxy
       |
       v
Transaction interceptor: BEGIN
       |
       v
handle(event)
       |
       +-- claim inbox
       +-- update order
       +-- insert outbox
       |
       v
COMMIT hoặc ROLLBACK
       |
       v
Proxy trả kết quả cho Consumer
       |
       v
Function invocation hoàn tất
       |
       v
Binder xử lý ACK/error theo policy
~~~

Đây là lý do nên để Function bean phụ thuộc một service Spring được inject, thay vì tự khởi tạo object bằng `new OrderApplicationService(...)` rồi kỳ vọng annotation tự hoạt động.

### 5.2. @Transactional cần đi qua Spring proxy

Transaction imperative của Spring thường được áp dụng qua proxy. Lời gọi từ một bean khác tới method được proxy quản lý là đường phổ biến.

Nếu một method gọi nội bộ `this.handle(...)` trong cùng object, self-invocation có thể bypass proxy; transaction có thể không được mở như mong muốn. Cũng cần kiểm tra proxy mode và cách bean được đăng ký.

### 5.3. Runtime exception và checked exception

Theo mặc định thông thường của Spring, `RuntimeException` và `Error` làm transaction rollback; checked exception không mặc định rollback trong mọi trường hợp. Nếu nghiệp vụ cần rollback khi checked exception xảy ra, khai báo rõ:

~~~java
@Transactional(rollbackFor = Exception.class)
public void handle(OrderCreated event) throws Exception {
    // Các thay đổi cần rollback nếu checked exception phát sinh.
}
~~~

Không thêm `rollbackFor` theo thói quen nếu có checked exception mà nghiệp vụ muốn commit. Chọn rule dựa trên loại lỗi và contract.

### 5.4. save() không phải lúc nào cũng là commit

ORM có thể trì hoãn SQL đến flush/commit. Constraint violation, deadlock hoặc mất kết nối có thể chỉ được báo ở cuối transaction. Vì vậy không ACK chỉ vì lệnh `repository.save(entity)` chưa ném lỗi; cần đợi **method transaction kết thúc thành công**.

## 6. Inbox pattern: gắn dấu message với thay đổi nghiệp vụ

Inbox (processed-message table) lưu định danh message đã được xử lý trong cùng transaction với dữ liệu nghiệp vụ. Khi broker giao lại sau commit, consumer phát hiện message cũ và không ghi lại.

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE processed_message (
    tenant_id       VARCHAR(80) NOT NULL,
    event_id        VARCHAR(120) NOT NULL,
    payload_hash    CHAR(64) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);
~~~

Khóa chính bảo vệ `tenant_id + event_id` không được claim hai lần. `payload_hash` giúp phát hiện event ID giống nhưng nội dung khác.

### 6.1. Claim event bằng một lệnh nguyên tử

~~~sql
INSERT INTO processed_message (
    tenant_id, event_id, payload_hash
)
VALUES (:tenantId, :eventId, :payloadHash)
ON CONFLICT (tenant_id, event_id) DO NOTHING
RETURNING event_id;
~~~

- Có một dòng trả về: transaction hiện tại claim được key.
- Không có dòng: key đã tồn tại hoặc transaction khác vừa claim; đọc fingerprint cũ và so sánh.
- Fingerprint giống: duplicate hợp lệ, không chạy lại side effect.
- Fingerprint khác: conflict, từ chối hoặc cách ly theo policy.

Trong PostgreSQL, unique constraint xử lý cạnh tranh ở storage. Ở isolation level READ COMMITTED, câu lệnh tiếp theo có thể đọc trạng thái đã commit sau khi insert chờ transaction cạnh tranh. Cần kiểm thử với DB thật và xử lý timeout/deadlock phù hợp.

### 6.2. Inbox và business write phải cùng commit

~~~text
BEGIN
  INSERT processed_message (unique tenant + event)
  UPDATE/INSERT order
  INSERT outbox_event
COMMIT
~~~

Nếu một bước lỗi trước commit, marker và dữ liệu nghiệp vụ cùng rollback. Nếu commit thành công rồi ACK mất, lần giao lại đọc marker đã commit và no-op.

Nếu inbox marker commit riêng trước order, process chết có thể khiến event bị coi là đã xử lý dù order chưa được ghi. Nếu order commit riêng trước marker, redelivery có thể ghi order lần nữa. **Cùng transaction** là điểm then chốt.

### 6.3. Duplicate hợp lệ nên kết thúc bình thường

Khi event đã commit với cùng fingerprint, service có thể return bình thường. Adapter có thể xem lần giao lại này là thành công và ACK theo policy.

Không ném lỗi transient cho event đã xử lý thành công; điều đó có thể tạo vòng lặp retry không cần thiết. Payload khác cùng key phải được báo conflict, không âm thầm coi là duplicate.

## 7. Ranh giới transaction và propagation

Một transaction chỉ bao phủ các tài nguyên được transaction manager quản lý. Nếu inbox, order và outbox cùng dùng một datasource/transaction manager, chúng có thể commit hoặc rollback cùng nhau.

### 7.1. REQUIRES_NEW có thể phá tính nguyên tử mong muốn

Giả sử `orders.apply(event)` tự mở transaction mới bằng `REQUIRES_NEW`:

~~~text
Outer transaction:
  claim inbox
       |
       +---- gọi orders.apply()
                  |
                  v
             New transaction
                  |
                COMMIT
       |
  outbox insert lỗi
       |
  Outer ROLLBACK
~~~

Kết quả có thể là order đã commit nhưng inbox/outbox của outer transaction rollback. Redelivery tiếp theo không thấy inbox marker và có thể áp dụng order lần nữa.

Nếu các thay đổi phải nguyên tử, repository/service con thường tham gia transaction hiện tại với propagation phù hợp, thường là `REQUIRED`. Chỉ dùng `REQUIRES_NEW` khi nghiệp vụ thực sự muốn một commit độc lập và hiểu rõ hậu quả.

### 7.2. Không giữ transaction mở quanh network call

Không nên giữ DB transaction trong khi chờ HTTP API hoặc broker publish lâu:

- Giữ connection/lock trong thời gian chờ.
- Tăng nguy cơ timeout, deadlock và contention.
- Remote side effect không rollback cùng DB.
- Nếu remote thành công nhưng DB rollback, hai hệ thống không còn nhất quán.

Hãy commit ý định qua outbox, sau đó worker riêng thực hiện network call.

### 7.3. Isolation level không thay thế idempotency

Isolation level quyết định transaction nhìn thấy thay đổi của nhau ra sao; nó không tự định nghĩa một request là duplicate. Unique constraint trên event key và business key vẫn cần thiết.

Một transaction có thể gặp deadlock hoặc serialization failure và cần retry toàn transaction. Nếu làm vậy, mọi side effect ngoài DB phải được loại khỏi transaction hoặc idempotent; không gửi email/HTTP trực tiếp trong callback có thể chạy lại.

### 7.4. Nhiều datasource không tự nằm trong cùng transaction

Nếu inbox ở database A còn order/outbox ở database B, một `@Transactional` mặc định thường chỉ chọn một transaction manager. Gọi repository ở datasource khác không tự khiến cả hai cùng commit/rollback.

~~~text
Transaction manager A: INSERT inbox → COMMIT
Transaction manager B: UPDATE order → ROLLBACK
~~~

Có thể để marker inbox tồn tại trong khi order chưa được cập nhật. Khi redelivery, consumer nhìn thấy marker và bỏ qua event sai.

Cần chọn rõ:

- Đưa inbox, domain data và outbox cần atomic vào cùng database/transaction manager nếu phù hợp.
- Nếu thật sự phải ghi nhiều resource độc lập, đánh giá XA/JTA và khả năng hỗ trợ/recovery.
- Hoặc thiết kế workflow/outbox/saga với trạng thái từng bước và cơ chế bù trừ.

Nếu ứng dụng có nhiều transaction manager, chỉ rõ manager phù hợp bằng cấu hình/qualifier, ví dụ `@Transactional("ordersTransactionManager")`. Việc chọn manager không tự tạo transaction phân tán.


## 8. ACK thuộc adapter/binder, không thuộc Function thuần

Spring Cloud Function cung cấp Function/Consumer độc lập giao thức. ACK là khái niệm của transport message; không có một lệnh ACK chung được đảm bảo hoạt động giống nhau trên Kafka, RabbitMQ và serverless.

### 8.1. Binder-managed acknowledgement

Với consumer imperative, binder thường gọi Function và dựa vào việc invocation kết thúc bình thường hay ném lỗi để áp dụng policy của nó. Tùy binder, ACK/offset commit, retry, requeue và dead-letter được điều phối bởi listener container hoặc client.

Trong mô hình này, Function không cần tự gọi ACK. Nó cần:

- Chỉ trả về sau khi transaction nghiệp vụ đã commit.
- Để exception thất bại truyền ra khi transaction rollback.
- Xử lý duplicate hợp lệ như thành công no-op.
- Không nuốt lỗi khiến binder hiểu nhầm xử lý đã hoàn tất.

### 8.2. Manual acknowledgement

Một số binder/client hỗ trợ manual ACK. Khi dùng, ứng dụng phải lấy đúng header/API dành cho binder cụ thể và chỉ ACK sau khi DB transaction đã commit.

Không truyền một đối tượng ACK giả định qua Function dùng chung rồi mong nó portable. Header, kiểu acknowledgment và semantics phụ thuộc binder/version. API manual ack của Spring Kafka không phải API chung của Spring Cloud Function hay Rabbit binder.

### 8.3. ACK, offset commit và message deletion không phải lúc nào giống nhau

- Kafka thường xác nhận tiến độ bằng offset commit theo partition/record/batch và cấu hình ack mode.
- RabbitMQ có cơ chế ACK/NACK cho delivery tag và requeue/dead-letter.
- Một số serverless event source dùng checkpoint hoặc cơ chế batch response.
- HTTP request thường kết thúc bằng response; không có broker ACK theo nghĩa tương tự.

Đừng suy luận semantics từ tên ACK. Hãy kiểm tra adapter cụ thể: ACK khi nào, một record hay batch, timeout ra sao, lỗi một phần batch được xử lý thế nào, redelivery có thể xảy ra không.

### 8.4. Ví dụ manual ACK chỉ dành cho Kafka adapter

Với Spring Kafka, khi container được cấu hình manual acknowledgement phù hợp, listener có thể nhận `Acknowledgment` và gọi `acknowledge()`. Nếu dùng Spring Cloud Stream Kafka binder, cách lấy header và cấu hình ACK phải theo binder/version đang chạy.

Pseudo-flow:

~~~java
// Minh họa ý tưởng; không phải API portable của mọi binder.
@Transactional
public void persist(OrderCreated event) {
    repository.apply(event);
}

// Sau khi method transaction trả về thành công:
// adapter Kafka-specific mới gọi acknowledgment.acknowledge().
~~~

Không gọi ACK trước khi method transaction hoàn tất. Cũng không dùng ví dụ pseudo-code này như cấu hình hoàn chỉnh: cần kiểm tra header, ack mode, record/batch semantics và thread mà ACK được gọi.

### 8.5. Manual ACK không giải quyết cửa sổ commit/ack

Ngay cả khi code gọi `acknowledge()` sau commit, process vẫn có thể chết giữa hai thao tác. Broker giao lại message là điều có thể xảy ra. Manual ACK giúp kiểm soát **thời điểm xác nhận**, còn inbox/idempotency xử lý **lần giao lại**.

## 9. Outbox: ghi database và ý định phát message cùng transaction

Một consumer có thể cập nhật order rồi cần phát event `OrderUpdated`. Nếu ghi DB và publish broker bằng hai lệnh độc lập, luôn có cửa sổ lỗi:

~~~text
DB commit thành công
       |
       v
Process chết trước khi publish
       |
       v
Order đã đổi nhưng không có event downstream
~~~

Nếu publish trước rồi DB rollback, downstream lại nhận event cho một thay đổi chưa commit.

**Transactional outbox** lưu ý định phát event vào bảng cùng transaction database với dữ liệu nghiệp vụ.

~~~text
BEGIN DB TRANSACTION
    UPDATE order
    INSERT outbox_event
COMMIT
       |
       v
Outbox worker đọc event chưa publish
       |
       v
Publish tới broker
       |
       v
Đánh dấu outbox đã publish
~~~

Nếu transaction rollback, cả order và outbox đều không xuất hiện. Nếu commit thành công, worker có thể phát event sau đó dù process gốc đã dừng.

### 9.1. Schema outbox minh họa

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(120) PRIMARY KEY,
    aggregate_id    VARCHAR(120) NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ
);
~~~

`event_id` là định danh ổn định. Trong production, cần thêm index cho truy vấn pending, trạng thái claim/lease, retry metadata, retention và chính sách bảo vệ payload.

### 9.2. Worker publish có thể phát trùng

~~~text
Worker đọc outbox event E
       |
       v
Broker nhận E thành công
       |
       v
Process chết trước khi ghi published_at
       |
       v
Worker mới đọc E là pending
       |
       v
Broker nhận E lần nữa
~~~

Outbox bảo đảm ý định publish không bị mất cùng DB commit, nhưng publisher có thể có semantics **at-least-once** trong cửa sổ này. Consumer downstream cần inbox/dedupe theo `event_id`.

### 9.3. Đánh dấu published sau khi broker xác nhận

Worker không nên đánh dấu event đã publish trước khi gửi. Nhưng nếu đánh dấu sau khi broker ACK, vẫn có cửa sổ crash giữa ACK và update DB. Đây là lý do downstream phải chịu được event trùng.

Không có thứ tự đơn giản nào giữa hai hệ thống độc lập vừa tránh mất event vừa tránh duplicate nếu không có cơ chế phối hợp giao dịch. Outbox ưu tiên không mất ý định phát và dùng dedupe để kiểm soát duplicate.

## 10. Inbox và outbox phối hợp ở hai đầu

Một workflow event-driven có thể dùng cả hai mẫu:

~~~text
Producer service
  DB transaction:
    update domain data
    insert outbox event
  COMMIT
       |
       v
  Outbox publisher
       |
       v
     Broker
       |
       v
Consumer service
  DB transaction:
    claim inbox event ID
    update consumer domain data
    insert next outbox event (nếu cần)
  COMMIT
       |
       v
  Binder ACK
~~~

- **Outbox của producer:** gắn ý định phát với thay đổi database.
- **Inbox của consumer:** gắn việc nhận event với thay đổi database của consumer.
- **ACK:** xác nhận delivery theo broker/binder sau khi transaction consumer thành công.
- **Dedupe downstream:** bảo vệ event được phát lại từ outbox hoặc broker.

### 10.1. Consumer duplicate không được tạo outbox mới

Nếu event đầu tiên đã commit cả inbox, order và outbox, lần giao lại cùng fingerprint phải no-op. Nếu code append outbox trước khi kiểm tra inbox, mỗi redelivery có thể tạo event downstream mới.

Thứ tự trong transaction nên là **claim inbox → kiểm tra duplicate → cập nhật domain → ghi outbox**.

### 10.2. Outbox publisher cần claim/lease

Nhiều worker có thể đọc cùng event pending. Cần cơ chế claim nguyên tử, row lock hoặc lease để giảm việc gửi đồng thời. Lease phải có thời hạn và recovery khi worker chết; tuy vậy lease không loại bỏ crash window sau publish.

### 10.3. Outbox không thay thế workflow orchestration

Outbox giải quyết việc ghi ý định phát message trong transaction DB. Nó không tự xử lý quy trình nhiều dịch vụ có bước bù trừ, timeout nghiệp vụ hoặc chờ người dùng. Những trường hợp đó có thể cần saga/process manager và trạng thái workflow riêng.

## 11. DB transaction và broker transaction có tự atomic không?

Thông thường, transaction DB local và transaction broker **không tự trở thành một transaction duy nhất** chỉ vì code chạy trong cùng Function.

Ví dụ:

~~~java
@Transactional
public void updateOrder(Order order) {
    repository.save(order);
    streamBridge.send("order-updated", event);
}
~~~

Nếu `send` publish thành công nhưng DB commit thất bại, broker đã có event trong khi DB không có thay đổi tương ứng. Nếu DB commit trước và publish thất bại, database có thay đổi nhưng event có thể bị mất nếu không có outbox.

### 11.1. Transaction của broker có phạm vi riêng

Một số broker hỗ trợ transaction trong phạm vi broker. Ví dụ, Kafka transaction có thể kết hợp publish records và commit offsets trong các kịch bản Kafka-to-Kafka, theo cấu hình và semantics của Kafka. Điều đó **không tự bao gồm một database PostgreSQL/JPA độc lập**.

Tương tự, transaction trên channel của một broker không tự rollback transaction DB bên ngoài. Cần đọc phạm vi hỗ trợ của binder và transaction manager đang dùng.

### 11.2. Spring Cloud Stream binder transaction là broker-specific

Spring Cloud Stream có hỗ trợ transaction tùy binder và cấu hình. Cần phân biệt:

- Transaction broker quản lý publish/offset/ack trong phạm vi broker.
- Transaction DB quản lý bảng inbox/domain/outbox.
- Transaction phối hợp giữa DB và broker đòi hỏi cơ chế rõ ràng, không tự xuất hiện do bật `@Transactional`.

Không copy một property transaction của Kafka binder sang Rabbit binder hoặc ngược lại. Đọc tài liệu đúng phiên bản và kiểm thử crash window thực tế.

### 11.3. Distributed transaction / XA

Một số hệ thống có thể phối hợp nhiều resource manager bằng XA/two-phase commit nếu driver, broker, transaction manager và cấu hình cùng hỗ trợ.

Đổi lại, distributed transaction làm tăng độ phức tạp vận hành: coordinator, in-doubt transaction, timeout, recovery log, khóa tài nguyên và giới hạn hỗ trợ của nền tảng. Nó không phải mặc định của Spring Cloud Function và không phải lựa chọn bắt buộc cho mọi ứng dụng.

Outbox/inbox thường dễ triển khai hơn trong kiến trúc microservice: transaction local cho DB, delivery at-least-once và consumer idempotent. Chọn theo yêu cầu nhất quán, tải, latency và khả năng vận hành.

## 12. ACK mode, offset và batch: kiểm tra semantics thực tế

Một consumer có thể nhận message theo record hoặc batch. ACK một record, commit offset cao nhất đã xử lý hoặc xác nhận cả batch có thể có hậu quả khác nhau.

### 12.1. Kafka

Với Kafka, consumer theo dõi offset của từng partition. Commit offset là xác nhận tiến độ đọc, không phải commit database. Nếu offset được commit trước DB transaction, process chết có thể bỏ qua record chưa lưu. Nếu DB commit rồi offset chưa commit, record có thể được đọc lại.

Trong chế độ batch, một batch có thể chứa nhiều record. Nếu record thứ ba lỗi sau khi hai record đầu đã commit, cách binder/container commit offset và retry batch có thể làm một số record được xử lý lại. Vì vậy, mỗi record có side effect nên có idempotency riêng.

### 12.2. RabbitMQ

RabbitMQ delivery thường dùng ACK/NACK theo delivery tag. ACK xác nhận delivery cho broker; nó không commit database. Nếu channel/connection đóng trước ACK, message có thể được requeue tùy trạng thái và cấu hình.

Khi xử lý nhiều message đồng thời, cần hiểu semantics của multiple ACK, prefetch, requeue và dead-letter. Không dùng delivery tag làm idempotency key nghiệp vụ: nó thuộc delivery/session, không nhất thiết ổn định qua lần giao lại.

### 12.3. Batch event source và serverless

Một số event source gửi batch và cho phép phản hồi lỗi một phần. Nếu chỉ báo batch thành công/thất bại, một record lỗi có thể khiến các record khác được giao lại. Cần dùng partial batch response nếu nền tảng hỗ trợ và bảo đảm record đã commit không tạo side effect lần hai.

### 12.4. Câu hỏi cần trả lời trước khi bật ACK mode

- ACK được gửi khi Function trả về hay khi Publisher complete?
- Transaction DB đã commit trước mốc đó chưa?
- Một ACK áp dụng một record, nhiều record hay offset/batch?
- Exception ở một phần batch có khiến cả batch được gửi lại không?
- ACK timeout hoặc connection mất thì broker xử lý ra sao?
- Có manual ack không, và API nào thuộc binder?
- Khi redelivery, định danh message nào ổn định?

Không có một câu trả lời portable cho mọi binder.

## 13. Reactive Function: transaction kết thúc khi Publisher hoàn tất

Với imperative service, transaction proxy có thể commit trước khi method trả về caller. Với reactive service, công việc thường được trì hoãn; transaction reactive phải bao Publisher và kết thúc theo terminal signal của Publisher.

Một method trả `Mono` có thể được quản lý bởi reactive transaction manager:

~~~java
@Service
public class ReactiveOrderService {

    private final ReactiveInboxRepository inbox;
    private final ReactiveOrderRepository orders;
    private final ReactiveOutboxRepository outbox;

    public ReactiveOrderService(
            ReactiveInboxRepository inbox,
            ReactiveOrderRepository orders,
            ReactiveOutboxRepository outbox) {
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public Mono<Void> handle(OrderCreated event) {
        return inbox.claim(event)
                .flatMap(claimed -> {
                    if (!claimed) {
                        return inbox.verifySamePayload(event)
                                .then();
                    }

                    return orders.apply(event)
                            .then(outbox.append(event));
                });
    }
}
~~~

Đây là ví dụ theo **reactive repository/R2DBC**. Các repository phải trả Publisher và tham gia cùng reactive transaction manager. Không thay bằng JDBC blocking rồi giả định transaction tự truyền qua scheduler.

### 13.1. Commit không xảy ra lúc method tạo Mono trả về

~~~text
Gọi handle(event)
       |
       v
Nhận Mono (chưa chạy DB)
       |
       v
Adapter subscribe
       |
       v
Transaction bắt đầu trong reactive context
       |
       v
Các thao tác DB phát tín hiệu
       |
       v
onComplete → commit
onError    → rollback
~~~

Nếu adapter chỉ tạo Publisher rồi không subscribe/không quản lý completion, transaction chưa thực thi. Với Spring Cloud Function reactive adapter, cần hiểu contract subscription của binder đang dùng.

### 13.2. Một transaction cho cả Flux hay một transaction cho mỗi message?

Nếu nhận một `Flux<OrderCreated>` dài, không mặc định nên bọc toàn bộ stream trong một transaction duy nhất. Một lỗi ở message thứ 100 có thể ảnh hưởng tới transaction dài và giữ connection/lock quá lâu.

Thường cần một transaction **cho mỗi message**:

~~~java
Flux<Void> results = events.concatMap(event ->
        transactionalOperator.execute(status ->
            inbox.claim(event)
                .flatMap(claimed -> {
                    if (!claimed) {
                        return inbox.verifySamePayload(event);
                    }

                    return orders.apply(event)
                            .then(outbox.append(event));
                })
        ).then()
);
~~~

`TransactionalOperator` là dependency được tạo từ reactive transaction manager; `events` và repository là các Publisher reactive. Ví dụ minh họa ranh giới per-item; cần điều chỉnh kiểu trả về của các port cho đúng ứng dụng.

### 13.3. Cancellation khác commit thành công

Nếu subscriber hủy subscription, Publisher có thể nhận cancel thay vì complete. Không được coi cancellation là commit thành công. Transaction manager có thể rollback theo lifecycle của transaction; nhưng một lời gọi I/O đã thoát khỏi quản lý hoặc side effect ngoài DB vẫn có thể đã xảy ra.

## 14. Vì sao fire-and-forget làm sai ACK?

Một Consumer có thể tự khởi chạy công việc async rồi trả về:

~~~java
@Bean
Consumer<OrderCreated> unsafe(OrderApplicationService service) {
    return event -> {
        service.handleAsync(event); // Không chờ completion.
    };
}
~~~

Nếu `handleAsync` trả `CompletableFuture`/Publisher nhưng Consumer bỏ qua kết quả, adapter chỉ thấy `accept` kết thúc. Nó có thể ACK trong khi DB chưa commit hoặc công việc sau đó thất bại.

Cách an toàn:

- Với consumer imperative, gọi một service đồng bộ có transaction và để exception truyền ra.
- Với reactive/async adapter, trả Publisher/CompletionStage đúng contract và để adapter quan sát terminal signal.
- Không tự `subscribe()` rồi bỏ lỗi.
- Không gọi manual ACK trước khi transaction hoàn tất.

### 14.1. @TransactionalEventListener(AFTER_COMMIT) không thay outbox

Một ứng dụng có thể dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` để chạy một listener sau commit. Nó hữu ích cho side effect in-process, nhưng **không phải durable message delivery**:

~~~text
DB COMMIT
   |
   v
Process chết trước listener
   |
   v
Listener không chạy, event có thể bị mất
~~~

Nếu listener publish broker nhưng broker gửi thành công rồi process chết trước khi ghi nhận trạng thái, event cũng có thể bị phát lại. Với yêu cầu không mất ý định publish, ghi outbox trong transaction và để worker riêng gửi.

## 15. Lỗi và retry: ai chịu trách nhiệm sau rollback?

Khi transaction DB ném lỗi trước commit:

~~~text
Function gọi application service
       |
       v
DB transaction
       |
       +-- lỗi
       |
       v
ROLLBACK
       |
       v
Exception/error signal truyền về adapter
       |
       v
Binder áp dụng retry/DLQ/requeue theo policy
~~~

Không nên bắt exception trong Consumer rồi trả bình thường nếu transaction thất bại. Binder có thể hiểu invocation thành công và ACK message.

### 15.1. Phân biệt lỗi vĩnh viễn và tạm thời

| Loại lỗi | Hành động tham khảo |
|---|---|
| Payload không hợp lệ | Không retry cùng payload; reject/quarantine |
| Duplicate cùng key, cùng payload đã commit | No-op và hoàn tất |
| Cùng key, payload khác | Conflict; không retry mù quáng |
| Deadlock/serialization failure | Có thể retry **toàn transaction DB** với giới hạn |
| DB tạm thời không kết nối | Retry theo ngân sách, deadline |
| Lỗi lập trình | Đưa ra quan sát và sửa code, không fallback giả |
| Commit outcome không rõ | Tra cứu theo idempotency key hoặc retry idempotent |

### 15.2. Retry transaction DB cần chạy lại cả transaction

Deadlock hoặc serialization failure có thể khiến transaction hiện tại không thể tiếp tục. Nếu retry, phải mở **transaction mới** và chạy lại các thao tác DB thuộc transaction đó.

Không retry một lệnh giữa transaction đã bị đánh dấu rollback-only. Không gửi email/publish HTTP trực tiếp trong transaction callback có thể chạy lại.

### 15.3. Binder retry không phải transaction rollback

Binder có thể gọi lại Function khi nhận exception, nhưng nó không thể tự rollback một transaction đã commit trước đó. Nếu commit thành công rồi ACK thất bại, retry sẽ chạy với dữ liệu đã có; inbox phải nhận diện duplicate.

### 15.4. Hết lượt retry

Khi transaction rollback và binder hết lượt, ứng dụng cần policy rõ: DLQ, error channel, requeue hoặc failure response tùy adapter. Không đánh dấu inbox DONE nếu nghiệp vụ chưa commit. Nếu payload vĩnh viễn không hợp lệ, tránh requeue vô hạn.

## 16. Transactional outbox so với publish sau commit

Có thể bắt gặp cách viết:

~~~java
@Transactional
public void update(Order order) {
    repository.save(order);
    applicationEventPublisher.publishEvent(
            new OrderUpdated(order.id()));
}
~~~

Nếu listener dùng `@TransactionalEventListener(AFTER_COMMIT)`, nó chạy sau commit trong cùng process. Điều này tránh publish trước commit, nhưng không bảo đảm event được lưu bền vững nếu process chết giữa commit và listener.

So sánh:

| Cách làm | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|
| Publish ngay trong transaction | Code ngắn | Broker có thể nhận event dù DB rollback |
| AFTER_COMMIT listener | Chỉ gọi listener sau DB commit | Process crash có thể làm mất event |
| Transactional outbox | Ý định phát được commit cùng DB | Publisher có thể phát trùng; cần downstream dedupe |
| XA/distributed transaction | Có thể phối hợp nhiều resource nếu hỗ trợ | Vận hành phức tạp, không phải mặc định |

Khi event là một phần quan trọng của hợp đồng giữa các service, outbox thường là lựa chọn rõ ràng hơn callback in-process.

## 17. Spring Cloud Stream: ACK và transaction cần kiểm chứng theo binder

Cấu hình functional binding chọn Consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: order-created
          group: order-service
~~~

Cấu hình trên không nói hết ACK semantics. Cần biết binder nào được dùng và những property chuyên biệt của binder.

### 17.1. Với Kafka binder

Cần xác định:

- Consumer đang xử lý record hay batch.
- Offset được commit theo ack mode nào.
- Binder transaction có bật không và transaction bao phủ những thao tác broker nào.
- Manual acknowledgement header/API nào được sử dụng nếu cần.
- Lỗi giữa batch được retry thế nào và offset nào đã commit.
- DB transaction có được phối hợp hay vẫn là transaction local độc lập.

Kafka transaction có thể cung cấp atomicity trong phạm vi Kafka (ví dụ publish record và commit offset theo cấu hình phù hợp). Nó không tự bao gồm JDBC/JPA database.

### 17.2. Với Rabbit binder

Cần xác định:

- ACK/NACK và requeue được quản lý theo container như thế nào.
- Channel transaction có được cấu hình không.
- Consumer xử lý một message hay nhiều message đồng thời.
- Prefetch, redelivery và dead-letter exchange/queue hoạt động ra sao.
- DB transaction có cùng resource manager hay độc lập.

Transaction/ACK trên Rabbit channel không tự commit database bên ngoài.

### 17.3. Đừng copy cấu hình ACK giữa binder

Property của Kafka binder có thể không tồn tại hoặc mang ý nghĩa khác trong Rabbit binder. Hãy dùng đúng tài liệu version đang chạy, sau đó kiểm thử:

1. Gây lỗi trước commit.
2. Gây lỗi sau commit nhưng trước ACK.
3. Tắt process khi message đang xử lý.
4. Kiểm tra redelivery và trạng thái DB.
5. Kiểm tra DLQ/requeue sau hết lượt.

### 17.4. Test binder không mô phỏng mọi broker behavior

Test binder có ích để kiểm tra binding và luồng function ở cấp ứng dụng, nhưng không tự chứng minh semantics offset, ACK/NACK, broker restart, prefetch hay redelivery thật. Cần integration test với broker tương ứng cho những bảo đảm đó.

## 18. Kiểm thử ranh giới transaction và ACK

Một unit test gọi `Consumer.accept(event)` không đủ chứng minh DB commit xảy ra trước ACK. Cần test service qua Spring proxy, database thật hoặc test database tương thích, và adapter/broker khi kiểm tra delivery semantics.

Các đoạn dưới đây là skeleton của integration test; helper `testEvent` và các truy vấn `countBy...` thuộc test fixture/repository adapter của dự án. Chúng minh họa assertion cần có, không phải một class hoàn chỉnh có thể chạy khi chưa cung cấp các fixture đó.

### 18.1. Test service commit rồi gọi lại cùng event

~~~java
@SpringBootTest
class OrderApplicationServiceIntegrationTest {

    // Các import cần có: JUnit 5, Spring Boot Test,
    // OrderModels.OrderCreated và static Assertions.

    @Autowired
    OrderApplicationService service;

    @Autowired
    OrderRepository orders;

    @Autowired
    ProcessedMessageRepository inbox;

    @Autowired
    FaultInjectingOutboxRepository outbox;

    @Test
    void repeatedInvocationDoesNotApplyOrderTwice() {
        OrderCreated event = testEvent("evt-901", "ORD-901");

        service.handle(event); // Proxy transaction commit trước khi return.
        service.handle(event); // Mô phỏng redelivery sau commit.

        assertEquals(1, orders.countByOrderId("ORD-901"));
        assertEquals(1, inbox.countByEventId("evt-901"));
    }
}
~~~

`testEvent` là fixture do test cung cấp; repository methods là hợp đồng minh họa. Test method **không nên tự nằm trong transaction bao ngoài** nếu mục tiêu là kiểm tra commit thật của service. Một test-level `@Transactional` có thể khiến service join transaction của test và chỉ rollback ở cuối test, che giấu thứ tự commit mong muốn.

### 18.2. Test rollback inbox cùng dữ liệu nghiệp vụ

~~~java
@Test
void failureBeforeCommitRollsBackInboxAndOrder() {
    OrderCreated event = testEvent("evt-902", "ORD-902");
    outbox.failNextInsert();

    assertThrows(RuntimeException.class,
            () -> service.handle(event));

    assertEquals(0, inbox.countByEventId("evt-902"));
    assertEquals(0, orders.countByOrderId("ORD-902"));
}
~~~

`outbox.failNextInsert` là cơ chế fault injection của test repository. Nếu transaction đúng và exception làm rollback, cả marker inbox và order đều không tồn tại. Trong production, lỗi commit/flush cũng cần được kiểm tra vì exception có thể chỉ xuất hiện cuối transaction.

### 18.3. Mô phỏng commit thành công nhưng ACK thất bại

~~~java
@Test
void redeliveryAfterCommitIsNoOp() {
    OrderCreated event = testEvent("evt-903", "ORD-903");

    service.handle(event); // DB commit thành công.

    // Mô phỏng process/connection chết trước khi ACK:
    service.handle(event); // Broker giao lại cùng event.

    assertEquals(1, orders.countByOrderId("ORD-903"));
    assertEquals(1, inbox.countByEventId("evt-903"));
    assertEquals(1, outbox.countByAggregateId("ORD-903"));
}
~~~

Test này mô phỏng logic redelivery ở application layer. Nó chưa chứng minh broker thật sẽ giao lại theo cách cụ thể; cần một integration test với binder để kiểm tra ACK, timeout và redelivery.

### 18.4. Không để test transaction che mất commit

Trong Spring Test, test method có `@Transactional` thường rollback transaction test khi kết thúc. Nếu service được gọi trong cùng transaction, các thao tác có thể chỉ join transaction ngoài thay vì commit độc lập tại thời điểm service return.

Để kiểm tra ranh giới thật:

- Không đánh dấu test method transaction nếu cần quan sát commit của service.
- Hoặc chủ động kết thúc transaction test bằng cơ chế test transaction phù hợp.
- Đọc dữ liệu bằng transaction/connection mới khi cần xác nhận commit.
- Dùng database integration test cho unique constraint, locking và rollback.

## 19. Kiểm thử adapter: ACK sau commit

### 19.1. Kịch bản cần có với broker thật

| Kịch bản | Cách tạo lỗi | Điều cần xác minh |
|---|---|---|
| Lỗi trước DB commit | Repository ném exception | Transaction rollback; adapter không ACK như thành công |
| Lỗi ở flush/commit | Constraint/connection failure | Exception tới adapter; không mất message |
| Commit xong, trước ACK | Dừng consumer hoặc làm mất connection | Message có thể redeliver; inbox no-op |
| Duplicate hợp lệ | Gửi cùng event hai lần | Một thay đổi nghiệp vụ |
| Same ID, payload khác | Gửi hai payload cùng key | Conflict/quarantine |
| Batch có một record lỗi | Gây lỗi ở giữa batch | Xác định record/offset nào được retry |
| Broker restart | Dừng broker trong delivery | Xác minh redelivery và persistence |
| Consumer rebalance | Dừng một instance khi đang xử lý | Không tạo side effect trùng |

Không chỉ assert rằng “consumer đã nhận message”. Cần kiểm tra **số dòng database**, **inbox/outbox**, **offset/ACK**, **DLQ** và số lần side effect.

### 19.2. Test binder và test broker thật có vai trò khác nhau

Test binder giúp kiểm tra Spring Cloud Function được bind đúng tên và payload có đi tới Consumer. Broker thật mới giúp kiểm tra protocol cụ thể như Kafka offset commit, Rabbit ACK/NACK, redelivery, partition/queue và dead-letter.

Đừng dùng kết quả test binder để kết luận toàn bộ guarantee của broker.

### 19.3. Test manual ACK

Nếu ứng dụng dùng manual ACK, test phải xác minh:

1. Method transaction đã commit trước khi gọi ACK.
2. Exception trước commit không gọi ACK.
3. Process chết sau commit trước ACK dẫn tới redelivery có thể xảy ra.
4. Duplicate redelivery kết thúc bình thường.
5. ACK/NACK được gọi trên đúng thread/context mà binder yêu cầu.

Không dùng mock `Acknowledgment` đơn lẻ để kết luận behavior offset/broker thật.

## 20. Quan sát transaction và ACK trong production

Để điều tra một message bị lặp hoặc bị mất, cần trace các mốc:

~~~text
received
  → transaction_started
  → inbox_claimed / duplicate_detected
  → domain_write
  → outbox_inserted
  → transaction_committed / rolled_back
  → function_completed
  → ack_attempted / ack_observed
~~~

Tên event ở đây là gợi ý observability, không phải event mặc định của Spring.

### 20.1. Trường log/trace hữu ích

- `eventId` và `tenantId` đã được xác thực.
- `aggregateId` hoặc business operation/version.
- `deliveryAttempt` nếu adapter cung cấp.
- `transactionId`/correlation ID nếu hệ thống có.
- Bước xử lý và kết quả: new, duplicate, conflict, rollback.
- Thời điểm commit và trạng thái ACK.
- Binder/destination/partition/offset hoặc delivery tag khi phù hợp.
- `traceId` xuyên các service.
- Lý do retry/DLQ, không log payload nhạy cảm.

Không giả định mọi binder cung cấp một delivery count ổn định. Offset/partition và delivery tag là metadata transport, không thay thế business key.

### 20.2. Metric nên phân biệt commit và ACK

| Metric gợi ý | Ý nghĩa |
|---|---|
| `message_received_total` | Số lượt nhận |
| `db_transaction_committed_total` | Transaction DB commit |
| `db_transaction_rolled_back_total` | Transaction DB rollback |
| `message_ack_attempt_total` | Số lần ứng dụng/binder cố ACK nếu quan sát được |
| `message_duplicate_total` | Lần nhận lại được inbox nhận diện |
| `message_conflict_total` | Cùng key nhưng payload khác |
| `message_redelivery_total` | Redelivery theo metadata binder nếu có |
| `outbox_pending_count` | Event đang chờ publish |
| `outbox_oldest_age_seconds` | Tuổi event pending lâu nhất |
| `message_processing_duration` | Thời gian xử lý |

Không phải ACK nào cũng có callback để metric trực tiếp ở application. Nếu binder quản lý ACK, có thể phải dùng listener/container metrics, broker metrics hoặc tracing instrumentation.

### 20.3. Alert theo bất thường

- Transaction commit thành công nhưng redelivery tăng cao: kiểm tra ACK/network/broker.
- Message nhận nhiều nhưng DB commit thấp: kiểm tra lỗi trước commit hoặc poison payload.
- DB commit tăng nhưng outbox pending ngày càng cũ: publisher không theo kịp.
- Duplicate/conflict tăng: kiểm tra producer resend, key reuse hoặc retention.
- Consumer latency tăng và ACK timeout: kiểm tra transaction quá dài, lock hoặc connection pool.

## 21. Bảng quyết định thiết kế

| Tình huống | Transaction DB | ACK/delivery | Bảo vệ chính |
|---|---|---|---|
| Consumer ghi một database | Một transaction cho inbox + domain write | Sau khi Function/service thành công theo binder | Inbox + unique key |
| Consumer ghi DB rồi phát event | Inbox + domain + outbox cùng transaction | ACK sau commit | Outbox + downstream inbox |
| HTTP POST tạo dữ liệu | Transaction lưu key + resource + kết quả | HTTP response sau commit | Idempotency-Key |
| Serverless event ghi DB | Transaction local dùng storage chung | Trigger xác nhận sau completion | Durable inbox/business key |
| Reactive stream nhiều event | Transaction per item nếu phù hợp | Adapter quản lý completion | Per-item inbox/idempotency |
| DB và broker cần atomicity chặt | XA nếu các resource hỗ trợ hoặc thiết kế outbox | Theo transaction strategy | Đánh giá trade-off rõ |
| Batch có lỗi một phần | Transaction/commit theo record hoặc batch đã định nghĩa | Partial ACK/checkpoint nếu hỗ trợ | Dedupe từng record |

Không có một mẫu transaction/ACK tối ưu cho mọi ứng dụng. Chọn theo delivery guarantee, tài nguyên cần commit, yêu cầu latency, khả năng vận hành và hậu quả khi replay.

## 22. Checklist trước production

### 22.1. Transaction

- [ ] Đã xác định datasource và transaction manager quản lý các bảng nào.
- [ ] Inbox marker và dữ liệu nghiệp vụ cần cùng commit.
- [ ] Outbox được ghi trong cùng transaction với thay đổi domain.
- [ ] Không dùng propagation độc lập vô tình phá tính nguyên tử.
- [ ] @Transactional đi qua Spring proxy thật.
- [ ] Rollback policy cho runtime/checked exception đã rõ.
- [ ] Commit/flush exception được truyền về adapter.
- [ ] Không giữ DB transaction quanh remote network call lâu.

### 22.2. ACK và delivery

- [ ] Biết binder/adapter và ACK mode đang dùng.
- [ ] Xác định ACK/offset áp dụng record hay batch.
- [ ] Function chỉ hoàn tất sau transaction commit.
- [ ] Manual ACK, nếu có, được gọi sau commit.
- [ ] Exception rollback không bị nuốt.
- [ ] Đã kiểm thử process chết sau commit trước ACK.
- [ ] Redelivery duplicate được xử lý no-op.
- [ ] Poison message có retry limit và DLQ/quarantine phù hợp.

### 22.3. Khả năng phối hợp DB và broker

- [ ] Không giả định @Transactional DB bao phủ broker publish.
- [ ] Broker transaction được giới hạn trong phạm vi thực sự hỗ trợ.
- [ ] Outbox publisher có retry/claim/lease.
- [ ] Consumer downstream có inbox/dedupe.
- [ ] XA/distributed transaction chỉ dùng khi đã đánh giá support và recovery.

### 22.4. Reactive và kiểm thử

- [ ] Biết ai subscribe Publisher và ai quan sát terminal signal.
- [ ] Transaction reactive dùng đúng reactive transaction manager.
- [ ] Transaction per-item được cân nhắc cho stream dài.
- [ ] Không fire-and-forget rồi ACK sớm.
- [ ] Unit test rollback và duplicate.
- [ ] Integration test commit rồi redelivery.
- [ ] Broker thật được dùng để test ACK/offset/DLQ semantics.
- [ ] Có metric/trace cho transaction, duplicate, redelivery và outbox.

## 23. Bài tập thực hành

**Bài 1 — ACK trước commit.** Consumer ACK message, sau đó transaction DB rollback. Điều gì xảy ra với message và dữ liệu? Vì sao đây là cửa sổ mất công việc?

**Bài 2 — Commit trước ACK.** DB commit thành công nhưng process chết trước ACK. Broker giao lại. Hãy mô tả vai trò của inbox.

**Bài 3 — Function completion.** Vì sao `Consumer.accept(event)` trả về không luôn chứng minh DB đã commit? Nêu trường hợp async/fire-and-forget và ORM flush.

**Bài 4 — @Transactional proxy.** Một Function gọi `service.handle(event)` qua Spring bean proxy. Khi nào transaction commit so với lúc lời gọi service trả về? Điều gì xảy ra nếu dùng `new Service()` hoặc self-invocation?

**Bài 5 — Rollback.** Inbox insert, update order và outbox insert cùng transaction. Outbox ném exception trước commit. Những thay đổi nào phải rollback?

**Bài 6 — Propagation.** `orders.apply` dùng `REQUIRES_NEW` và commit, sau đó outer transaction rollback. Vì sao inbox/outbox có thể không còn nhất quán?

**Bài 7 — Outbox.** DB commit thành công nhưng process chết trước publish. Outbox giải quyết cửa sổ nào? Nó có bảo đảm broker chỉ nhận một message không?

**Bài 8 — Publish rồi crash.** Broker nhận event, publisher chết trước khi đánh dấu outbox published. Vì sao downstream inbox vẫn cần thiết?

**Bài 9 — Kafka.** Offset commit trước DB commit có rủi ro gì? DB commit trước offset commit có rủi ro gì? Vì sao inbox cần thiết?

**Bài 10 — RabbitMQ.** ACK/NACK theo delivery tag có commit database không? Nếu channel đóng trước ACK, điều gì có thể xảy ra?

**Bài 11 — Reactive.** Một Function trả Publisher nhưng không được subscribe. Transaction DB đã chạy chưa? Khi nào reactive transaction commit?

**Bài 12 — Transaction per-item.** Một Flux nhận 1.000 event. Vì sao transaction duy nhất cho cả stream có thể gây rủi ro? Khi nào nên dùng transaction cho từng event?

**Bài 13 — Manual ACK.** Vì sao gọi `acknowledge()` ngay sau khi tạo Mono nhưng trước subscribe là sai? Hãy nêu đúng thứ tự.

**Bài 14 — AFTER_COMMIT.** Vì sao `@TransactionalEventListener(AFTER_COMMIT)` không tương đương transactional outbox?

**Bài 15 — Distributed transaction.** Kafka transaction có tự commit một database PostgreSQL độc lập không? Khi nào cần cân nhắc XA?

**Bài 16 — Test.** Đề xuất một test chứng minh transaction rollback cả inbox/order và một test mô phỏng commit thành công nhưng ACK thất bại.

**Bài 17 — Batch.** Một batch có năm record, record thứ tư lỗi. Vì sao phải hiểu offset/partial batch ACK trước khi kết luận record 1–3 không bị xử lý lại?

**Bài 18 — Observability.** Nêu các trường log/metric giúp phân biệt transaction rollback, commit thành công, duplicate redelivery và ACK failure.

### Gợi ý đáp án

- **Bài 1:** Broker có thể không giao lại vì đã ACK; DB không có dữ liệu, công việc bị mất.
- **Bài 2:** Lần giao lại đọc marker đã commit, so sánh fingerprint rồi no-op; không tạo side effect lần hai.
- **Bài 3:** Consumer có thể bỏ qua async completion; ORM có thể chỉ flush/commit sau; cần chờ transaction hoàn tất.
- **Bài 4:** Proxy transaction interceptor commit trước khi trả caller; tự khởi tạo hoặc self-invocation có thể bypass proxy.
- **Bài 5:** Inbox, order và outbox cùng rollback nếu dùng chung transaction manager.
- **Bài 6:** Order commit riêng nhưng inbox/outbox rollback; redelivery có thể áp dụng lại.
- **Bài 7:** Outbox giữ ý định publish cùng DB commit; publisher vẫn có thể gửi trùng sau crash.
- **Bài 8:** Downstream có thể nhận lại cùng event; inbox/idempotency ngăn side effect trùng.
- **Bài 9:** Commit offset trước DB có thể mất record; DB trước offset có thể redeliver; inbox bảo vệ lần lặp.
- **Bài 10:** ACK xác nhận delivery, không commit DB; channel đóng trước ACK có thể làm message được giao lại.
- **Bài 11:** Chưa subscribe thì công việc lazy thường chưa chạy; reactive transaction kết thúc theo complete/error của Publisher.
- **Bài 12:** Transaction dài giữ connection/lock và một lỗi ảnh hưởng cả stream; per-item transaction cô lập event độc lập.
- **Bài 13:** Tạo Publisher chưa thực thi/commit; phải subscribe và đợi transaction hoàn tất rồi mới ACK.
- **Bài 14:** Listener in-process có thể không chạy nếu process chết sau commit; outbox lưu ý định phát bền vững.
- **Bài 15:** Kafka transaction chỉ bao phạm vi Kafka; XA cần resource manager/driver/transaction manager hỗ trợ và có chi phí recovery.
- **Bài 16:** Gây lỗi ở outbox để assert inbox/order rollback; commit service rồi mô phỏng mất ACK và gọi lại cùng event.
- **Bài 17:** Batch retry/offset semantics có thể phát lại record trước; cần idempotency từng record.
- **Bài 18:** Event ID, transaction outcome, ACK attempt, delivery count, binder/partition/offset, duplicate outcome và outbox age.

## 24. Ghi nhớ

- **Function completion, DB commit và broker ACK là ba mốc riêng biệt.**
- ACK trước DB commit có thể làm mất message nếu transaction rollback; commit trước ACK có thể gây redelivery.
- Với consumer ghi DB, để transaction hoàn tất trước khi binder xác nhận thành công và dùng inbox/unique key để xử lý giao lại.
- Đặt `@Transactional` ở application service được Spring proxy gọi; chú ý self-invocation, propagation, rollback rule và lỗi chỉ xuất hiện lúc flush/commit.
- Inbox marker phải commit cùng thay đổi nghiệp vụ; outbox ghi ý định publish cùng DB transaction.
- Outbox có thể publish trùng; downstream vẫn cần inbox/dedupe.
- Kafka/Rabbit/serverless có ACK, offset, batch và retry semantics khác nhau; không có API ACK portable do Spring Cloud Function cung cấp.
- Reactive transaction kết thúc theo lifecycle Publisher; không fire-and-forget rồi giả định adapter đã quan sát completion.
- Transaction broker không tự bao gồm database độc lập; XA/distributed transaction chỉ có khi resource và cấu hình hỗ trợ.
- Kiểm thử cả rollback trước commit, redelivery sau commit, ACK failure, batch và broker thật để xác minh trạng thái dữ liệu sau sự cố.








