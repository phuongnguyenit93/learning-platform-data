# Handler có state và thread safety trong Spring Integration

## Mục tiêu bài học

Khi xây dựng **Spring Integration Runtime**, message đi qua channel, endpoint, consumer, poller và executor trước khi đến handler. Một handler xử lý được từng message riêng lẻ chưa chắc đã đúng khi nhiều message đi vào cùng lúc. Bài này giúp bạn:

- Phân biệt **state của một lần xử lý**, **state lưu trong bean handler**, **state theo correlation key** và **state bền vững bên ngoài ứng dụng**.
- Xác định handler có thể được gọi đồng thời ở đâu, kể cả khi sử dụng DirectChannel.
- Nhận diện lost update, dữ liệu lẫn giữa các message, sai thứ tự, duplicate và race giữa retry với side effect.
- Chọn cơ chế bảo vệ phù hợp: dữ liệu bất biến, biến cục bộ, atomic operation, đồng bộ hóa, message group store hoặc transaction ở cơ sở dữ liệu.
- Quan sát và kiểm thử thread safety trong runtime thay vì suy luận từ tên channel.

> **Ý chính:** Thread safety là thuộc tính của *cách handler truy cập state được chia sẻ*, không phải một bảo đảm tự động đến từ annotation, bean singleton hay việc flow chạy đồng bộ.

## 1. State của handler nằm ở đâu?

Trong Spring Integration, một **MessageHandler** nhận message và thực hiện xử lý; service activator thường ủy quyền việc xử lý cho một phương thức của POJO. Bean handler hoặc service dùng chung thường sống lâu hơn rất nhiều so với một message.

| Phạm vi state | Ví dụ | Vấn đề cần kiểm soát |
| --- | --- | --- |
| **Theo lần gọi** | Biến cục bộ tính tổng tiền, DTO bất biến riêng cho message | An toàn hơn khi mỗi lần gọi giữ dữ liệu riêng; vẫn phải lưu ý đối tượng đầu vào được chia sẻ |
| **Trong instance handler** | Bộ đếm, cache, Map lưu đơn hàng đang xử lý | Nhiều luồng cùng đọc/ghi; restart sẽ mất nếu chỉ ở RAM |
| **Theo correlation key** | Nhóm message của một đơn hàng chờ đủ các phần | Nhiều message cùng key có thể đến đồng thời hoặc sai thứ tự |
| **Ngoài tiến trình** | Số dư trong DB, Redis, JDBC MessageStore | Nhiều instance, restart, transaction, duplicate và cơ chế lock phân tán |

Phân biệt **state có chủ đích** với **state bị rò rỉ ngoài ý muốn**. Ví dụ, trường lastCustomerId trong một singleton để “ghi nhớ khách hàng vừa xử lý” có thể khiến hai message ghi đè dữ liệu của nhau. Biến cục bộ customerId được lấy trực tiếp từ message không có vấn đề đó.

**MessageHeaders** được thiết kế như tập header không thể sửa trực tiếp sau khi tạo; nhưng điều này **không biến payload thành bất biến**. Nếu payload là ArrayList, Map hoặc một entity có setter, hai handler/luồng cùng tham chiếu vẫn có thể sửa nó. Nên truyền DTO bất biến hoặc tạo bản sao khi cần chuyển quyền sở hữu dữ liệu.

## 2. Channel quyết định nơi thực thi, nhưng không tự bảo vệ state

Sơ đồ dưới đây minh họa tình huống thường gây hiểu nhầm:

~~~mermaid
flowchart LR
    P1["Producer A · thread A"] --> DC["DirectChannel"]
    P2["Producer B · thread B"] --> DC
    DC --> H["Một singleton handler"]
    H --> S[("State dùng chung")]
~~~

DirectChannel gọi handler trên **thread của chính lần send**. Nếu hai producer gọi send cùng lúc thì hai lời gọi vào cùng handler vẫn có thể chồng lấn. “Một thread cho mỗi lần send” không đồng nghĩa “chỉ một thread cho toàn bộ handler”.

| Thành phần runtime | Hành vi thực thi điển hình | Tác động tới handler có state |
| --- | --- | --- |
| **DirectChannel** | Handler chạy đồng bộ trên thread của sender; sender đợi xử lý kết thúc | Các sender khác nhau vẫn có thể gọi cùng handler đồng thời |
| **ExecutorChannel** | Giao việc dispatch cho TaskExecutor, thường chạy trên thread khác | Có thể song song, không mặc định giữ thứ tự; transaction theo thread của sender không truyền xuyên channel |
| **QueueChannel + polling consumer** | Message nằm trong queue; poller lấy và gọi handler | Một consumer tuần tự có thể giảm cạnh tranh, nhưng nhiều poller/task/executor có thể tăng song song |
| **PublishSubscribeChannel** | Gửi message tới các subscriber; mặc định thường đồng bộ, có thể cấu hình executor | Các subscriber có thể cùng thấy payload tham chiếu; gửi đồng thời hoặc executor gây cạnh tranh |
| **Aggregator/correlating endpoint** | Tập hợp message theo khóa tương quan qua MessageGroupStore | Cần đồng bộ theo group và quản lý vòng đời group, timeout, late arrival |

Một cách đọc flow hữu ích là lần theo **đường thread** từ producer qua từng channel, gateway, poller, executor, endpoint rồi mới đến handler. Chỗ chuyển thread cũng thường là chỗ thay đổi ranh giới transaction, ngữ cảnh ThreadLocal/MDC và cách lỗi được truyền về caller.

**Không nên dùng giả định “message đến đúng thứ tự”.** Trong hệ thống song song, message cùng một khóa có thể hoàn tất lệch thứ tự, retry có thể tạo lại thao tác cũ và message từ broker có thể được phân phối lại. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy định nghĩa rõ thứ tự theo khóa, cách tuần tự hóa hoặc điều kiện phiên bản trong kho dữ liệu.

## 3. Race condition: code chạy đúng với một message nhưng sai khi nhiều message

Ví dụ handler nhận yêu cầu giữ hàng tồn kho:

~~~java
import java.util.HashMap;
import java.util.Map;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

record ReserveCommand(String sku, String requestId) {}
record ReserveResult(String requestId, boolean accepted) {}

@Component
class UnsafeReservationHandler {
    private final Map<String, Integer> remaining = new HashMap<>();

    @ServiceActivator(inputChannel = "reservationRequests")
    public ReserveResult reserve(ReserveCommand command) {
        int before = remaining.getOrDefault(command.sku(), 0);
        if (before <= 0) {
            return new ReserveResult(command.requestId(), false);
        }

        remaining.put(command.sku(), before - 1);
        return new ReserveResult(command.requestId(), true);
    }
}
~~~

Giả sử tồn kho của SKU A là 1 và hai thread xử lý đồng thời:

1. Thread T1 đọc before = 1.
2. Thread T2 cũng đọc before = 1.
3. T1 ghi 0 và trả accepted = true.
4. T2 cũng ghi 0 và trả accepted = true.

Hệ thống đã xác nhận **hai** yêu cầu trong khi chỉ có **một** sản phẩm. Đây là lỗi *check-then-act* và *lost update*. HashMap còn không an toàn khi ghi đồng thời; thay nó bằng ConcurrentHashMap **chưa** khắc phục chuỗi đọc → kiểm tra → ghi vốn gồm nhiều thao tác.

Các biến thể dễ gặp:

- Trường currentOrder hoặc currentUser bị message khác ghi đè trước khi handler tạo response.
- Counter dùng count++ bỏ mất lượt cập nhật.
- Một ArrayList dùng chung bị sửa trong lúc thread khác đang duyệt.
- Handler gọi dịch vụ ngoài trong synchronized block làm tăng thời gian giữ lock, nghẽn throughput.
- Hai bản sao ứng dụng đều “đã khóa” bằng synchronized, nhưng mỗi bản sao chỉ khóa trong **JVM của mình**.

## 4. Làm state trong một JVM an toàn bằng thao tác atomic

Nếu state chỉ dùng để minh họa hoặc đếm trong một tiến trình, có thể dùng **ConcurrentHashMap** kết hợp **AtomicInteger**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class LocalReservationHandler {
    private final ConcurrentMap<String, AtomicInteger> remaining =
            new ConcurrentHashMap<>();

    // Khởi tạo từng SKU khi bootstrap; không gọi lại để reset trong lúc xử lý.
    public void registerSku(String sku, int initialQuantity) {
        if (initialQuantity < 0) {
            throw new IllegalArgumentException("Quantity must be non-negative");
        }
        if (remaining.putIfAbsent(sku, new AtomicInteger(initialQuantity)) != null) {
            throw new IllegalStateException("SKU already registered: " + sku);
        }
    }

    @ServiceActivator(inputChannel = "reservationRequests")
    public ReserveResult reserve(ReserveCommand command) {
        AtomicInteger stock = remaining.get(command.sku());
        if (stock == null) {
            throw new IllegalArgumentException("Unknown SKU: " + command.sku());
        }

        int before = stock.getAndUpdate(qty -> qty > 0 ? qty - 1 : 0);
        return new ReserveResult(command.requestId(), before > 0);
    }
}
~~~

Hàm getAndUpdate thực hiện cập nhật atomic trên **một giá trị** và trả về giá trị trước cập nhật. Hai thread cùng thấy số lượng 1 sẽ không thể cùng giảm thành công. Hàm biến đổi nên là phép tính ngắn, thuần, không phát side effect vì có thể được đánh giá nhiều lần trong cơ chế cập nhật cạnh tranh.

**Giới hạn:** Ví dụ trên chỉ giữ state trong RAM của một JVM. Nó không lưu lịch sử requestId, không chống được cùng một request đến hai lần, không hỗ trợ nhiều replica cùng chia tồn kho, không chống mất dữ liệu khi restart và không bảo đảm đồng bộ với giao dịch cơ sở dữ liệu. Không dùng mẫu này làm nguồn sự thật cho tồn kho hoặc tiền.

### Khi một key chứa nhiều trường

Với state nhỏ, bất biến theo key, có thể cập nhật cùng lúc các trường bằng compute:

~~~java
record BatchProgress(int received, int failed) {}

private final ConcurrentMap<String, BatchProgress> progress =
        new ConcurrentHashMap<>();

void recordResult(String batchId, boolean successful) {
    progress.compute(batchId, (key, old) -> {
        BatchProgress current =
                old == null ? new BatchProgress(0, 0) : old;
        return new BatchProgress(
                current.received() + 1,
                current.failed() + (successful ? 0 : 1));
    });
}
~~~

Với một key, compute tránh cập nhật rời rạc received và failed. Tuy vậy, nó **không** làm cho thao tác trên nhiều key hoặc thao tác với DB thành một transaction. Tránh gọi HTTP, gửi message, ghi DB hay chờ lâu bên trong hàm compute; nếu callback bị gọi lại, side effect còn có thể nhân đôi.

Nếu handler có nhiều bất biến phụ thuộc nhau (ví dụ chuyển tiền giữa hai tài khoản), hãy đặt toàn bộ bất biến trong một transaction của kho dữ liệu có khả năng kiểm soát concurrency, thay vì ghép nhiều AtomicInteger.

## 5. Khi state thuộc về nhóm message: dùng cơ chế correlation

Một quy trình có thể nhận nhiều phần của một đơn hàng: thông tin thanh toán, vận chuyển, kiểm kho. Chúng có thể đến vào những thời điểm khác nhau. Dùng field mutable trên handler để “giữ message chờ đủ” rất dễ lẫn đơn hàng.

Spring Integration có **aggregator**, là một dạng **stateful message handler**. Nó:

1. Xác định **correlation key** để phân nhóm (mặc định thường lấy từ header correlationId).
2. Lưu message thuộc group qua **MessageGroupStore**.
3. Dùng **ReleaseStrategy** để quyết định khi nào group đủ điều kiện xuất kết quả.
4. Áp dụng lock theo group khi thao tác với group; mặc định dùng lock trong tiến trình.

~~~mermaid
flowchart TD
    M1["Message: order-42 / payment"] --> C["Correlation key = order-42"]
    M2["Message: order-42 / shipment"] --> C
    M3["Message: order-42 / inventory"] --> C
    C --> G[("MessageGroupStore")]
    G --> R{"ReleaseStrategy: đủ điều kiện?"}
    R -- "Chưa" --> G
    R -- "Rồi" --> O["Kết quả tổng hợp"]
~~~

**Điều không được suy diễn:** Aggregator bảo vệ những cập nhật group do endpoint của nó quản lý; nó không tự bảo vệ mọi field mutable trong POJO hay mọi side effect gọi từ ReleaseStrategy/processor. Các callback nghiệp vụ vẫn nên hạn chế state chia sẻ và tránh side effect không idempotent.

Khi **nhiều instance** cùng dùng một MessageGroupStore, cần xem xét **LockRegistry chia sẻ giữa các instance**. DefaultLockRegistry chỉ có hiệu lực trong một tiến trình. Phải phân biệt:

- **MessageGroupStore** bảo quản message và metadata của group; lựa chọn in-memory/persistent quyết định khả năng sống qua restart.
- **LockRegistry** phối hợp các bên cùng thao tác trên group; một kho lưu trữ dùng chung không tự động khiến lock trong JVM trở thành lock phân tán.
- **Idempotency/deduplication** ngăn xử lý lặp tác dụng nghiệp vụ; khóa group không thay thế unique constraint, idempotent receiver hoặc khóa yêu cầu đã xử lý.

Ngoài ra cần quyết định **group timeout**, xử lý message đến muộn, hủy group hoặc phát kết quả một phần, và chính sách dọn group cũ. Nếu giữ group mãi trong RAM, memory có thể tăng không giới hạn. Không đặt chung một MessageGroupStore cho nhiều aggregator có cơ chế expiry độc lập mà không thiết kế phân vùng và callback phù hợp.

## 6. Transaction, retry và boundary giữa các thread

Giả sử một handler cần trừ tồn kho trong DB, ghi lịch sử xử lý rồi gửi message xác nhận. Khi hoạt động đồng thời, **thread-safe trong RAM** và **transaction-safe trong kho dữ liệu** là hai yêu cầu khác nhau.

### Trường hợp giao dịch trong cùng thread

Với DirectChannel, phần gửi và xử lý đồng bộ có thể cùng tham gia transaction đang gắn với thread, **nếu** cấu hình transaction manager và các tài nguyên liên quan hỗ trợ. Khi handler ném lỗi, sender thường nhìn thấy lỗi trong lời gọi send đồng bộ. Nhưng rollback DB **không rollback tự động** giá trị AtomicInteger hoặc field của Java.

### Trường hợp chuyển sang executor

Với ExecutorChannel, xử lý thường diễn ra trên thread khác. Transaction/ThreadLocal của sender không mặc định chuyển qua thread của handler, và send có thể hoàn thành trước khi handler ném lỗi. Cần thiết kế transaction **ở phía consumer/handler** và định tuyến lỗi cho bước bất đồng bộ. Đừng dựa vào CallerRunsPolicy hoặc một lần tình cờ dùng chung thread để bảo đảm ranh giới giao dịch.

### Một mẫu an toàn hơn cho state nghiệp vụ

Với tồn kho trong DB, có thể dùng thao tác có điều kiện trong transaction:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = :sku AND available > 0;
~~~

Chỉ xác nhận giữ hàng nếu số dòng được cập nhật là 1. Nếu message có thể được phát lại, requestId cần được ghi nhận **idempotently** bằng unique constraint hoặc một bản ghi xử lý trong cùng transaction phù hợp; thứ tự kiểm tra và ghi nhận phải chịu được hai consumer đồng thời. Với nhiều tài nguyên phân tán, cân nhắc transactional outbox/inbox hoặc quy trình bù trừ thay vì giả định một transaction bao trùm broker, DB và HTTP.

Các nguyên tắc khi retry:

- Retry làm **thực thi lại** một đoạn xử lý; retry không có nghĩa là message mới hoặc tác dụng cũ đã được hoàn tác.
- Nếu handler đã gọi API thanh toán thành công rồi timeout khi nhận response, retry có thể gọi thanh toán lần nữa. Dùng idempotency key tại phía hệ thống đích hoặc thiết kế đối soát.
- Nếu message có thể đến trùng, **đếm số lần handleMessage** không đồng nghĩa **đếm số nghiệp vụ duy nhất**.
- Một lỗi bất đồng bộ cần được quan sát ở error flow/errorChannel phù hợp; đừng chỉ bắt exception quanh lời gọi send của producer rồi coi như đã bao phủ toàn bộ lỗi downstream.

## 7. Chọn cách bảo vệ state theo phạm vi

| Nhu cầu | Cách tiếp cận phù hợp | Giới hạn quan trọng |
| --- | --- | --- |
| Xử lý từng message độc lập | Stateless handler, biến cục bộ, DTO bất biến | Payload hoặc service phụ thuộc vẫn có thể chia sẻ state |
| Metric/counter chỉ trong một instance | AtomicLong, LongAdder hoặc cấu trúc concurrent | Không phải số liệu chính xác toàn cluster; reset sau restart |
| Cache tạm theo key | ConcurrentMap hoặc cache có TTL/giới hạn dung lượng | Cần chính sách eviction, invalidation, memory |
| Cập nhật nhiều trường của một key trong RAM | compute với object bất biến, lock theo key khi phù hợp | Không bao trùm nhiều key, DB, remote call |
| Tổng hợp message theo correlation | Aggregator + MessageGroupStore + release/expiry | Cần thiết kế group, duplicate, persistent store và distributed lock |
| Tồn kho, hạn mức, tiền, dedup qua nhiều replica | Transaction DB, unique constraint, cập nhật có điều kiện, optimistic locking | Cần xử lý conflict/retry và ngoại tác bên ngoài |
| Yêu cầu thứ tự theo entity/key | Consumer/partition theo key, cập nhật kiểm tra version, hoặc tuần tự hóa có chủ đích | Thứ tự toàn cục thường tốn throughput; scale-out cần cùng quy tắc phân vùng |

**Khóa toàn handler** bằng synchronized có thể giúp một số thao tác trong một JVM trở nên tuần tự, nhưng khiến các key không liên quan chờ nhau; không giải quyết concurrency giữa nhiều instance và dễ gây nghẽn nếu giữ khóa qua I/O. Nếu cần state theo key, ưu tiên bảo vệ đúng phạm vi key hoặc chuyển invariant xuống kho dữ liệu.

## 8. Thực hành đọc một flow đang chạy

Ví dụ một mô hình (sơ đồ ý tưởng, không phải cấu hình đầy đủ):

~~~text
HTTP/gateway
  └─ DirectChannel
       └─ transformer (stateless)
            └─ ExecutorChannel (thread pool 8)
                 └─ @ServiceActivator reservationHandler
                      ├─ DB update
                      └─ outbound event
~~~

Hãy lần lượt trả lời:

1. **Đường nào tạo concurrency?** Nhiều HTTP request có thể đến đồng thời; executor có tối đa nhiều task cùng xử lý; số lượng subscriber, poller và instance khác nhau có thể tăng concurrency thực tế.
2. **State thực sự nằm đâu?** Field của reservationHandler, cache/DAO dùng chung, DB, payload mutable, và hệ thống ngoài.
3. **Có cần thứ tự theo key không?** Hai yêu cầu cùng SKU hoặc orderId có thể đến lệch thứ tự; dùng version/check condition nếu thứ tự quyết định kết quả.
4. **Transaction bắt đầu ở đâu?** Không mặc định coi transaction của HTTP thread tiếp tục sau ExecutorChannel.
5. **Khi lỗi hoặc retry, điều gì có thể chạy lại?** Phân biệt message đã lấy khỏi queue, SQL đã commit, API ngoài đã xử lý và event đã phát.
6. **Khi stop/restart IntegrationFlow, state còn không?** State ở field handler và store in-memory phụ thuộc vòng đời bean/process; state persistent còn tùy cấu hình store. Stop một endpoint không có nghĩa tự động xóa toàn bộ state nghiệp vụ.

### Kiểm tra bằng concurrent test

Tạo dữ liệu thử 1 SKU có tồn kho 50, phát đồng thời 200 lệnh reserve với **200 requestId khác nhau**, chờ tất cả xử lý xong rồi kiểm tra:

- Với giả định mỗi lệnh được phát **đúng một lần**, số kết quả accepted phải đúng 50, rejected đúng 150 và tồn cuối cùng bằng 0.
- Lặp phép thử qua nhiều thread, nhiều lần; nếu có broker/retry thì phải đo riêng số message và số requestId duy nhất.
- Cho **cùng một requestId** chạy hai lần để xem logic idempotency thực sự hoạt động hay chưa.
- Nếu chạy nhiều application instance, kiểm tra bằng DB hoặc store chung; test chỉ trong một JVM không chứng minh được tính đúng đắn khi scale-out.
- Thêm lỗi giả lập giữa ghi DB và gửi event để kiểm tra duplicate, rollback, timeout và cơ chế phục hồi.

### Quan sát khi chẩn đoán production

Trong log/trace, nên có messageId, correlationId, business key (orderId/SKU), endpoint, thread name và mã attempt hoặc requestId. Không log dữ liệu nhạy cảm nếu không cần thiết. Theo dõi số thread đang bận, hàng đợi executor, task bị từ chối, độ trễ poller, độ dài backlog, group tồn đọng/timeout, tỉ lệ retry, duplicate và thời gian giữ lock. Những triệu chứng như throughput giảm khi tăng pool size, số request được chấp nhận vượt giới hạn hoặc group chờ mãi thường báo hiệu vấn đề về đồng bộ state, bất biến nghiệp vụ hoặc correlation.

## 9. Checklist trước khi triển khai handler có state

- **Ownership:** State nào sống theo message, theo bean, theo key, theo JVM, theo cluster?
- **Concurrency:** Ai có thể gọi handler cùng lúc? Có thread boundary, nhiều poller, nhiều endpoint tham chiếu cùng bean hoặc nhiều replica không?
- **Atomicity:** Thao tác “đọc → kiểm tra → ghi” có nằm trong một atomic operation/transaction không?
- **Immutability:** Payload/callback có sửa đối tượng đang được handler khác cùng sử dụng không?
- **Ordering:** Có cần xử lý đúng thứ tự theo key? Nếu có, ai bảo đảm?
- **Duplication:** Với retry/redelivery, liệu requestId đã xử lý có bị áp dụng lại?
- **Persistence:** Restart, redeploy, stop/start flow và hết hạn group ảnh hưởng state thế nào?
- **Error path:** Exception xảy ra sau ExecutorChannel đi đâu; có đủ khả năng quan sát và phục hồi không?
- **Operations:** Có giới hạn bộ nhớ, TTL, backpressure, timeout, lock monitoring và bài kiểm thử đồng thời không?

## Kết luận

Handler an toàn nhất thường là handler **không giữ state nghiệp vụ trong field mutable**: mỗi lời gọi làm việc với message riêng và ủy quyền sự nhất quán cho kho dữ liệu hoặc cơ chế message group phù hợp. Khi bắt buộc giữ state, hãy xác định phạm vi chia sẻ của nó trước, bảo vệ đúng bất biến và kiểm thử dưới concurrency thật. Channel và executor quyết định *đường thực thi*; message store, lock và transaction quyết định *cách giữ state nhất quán*.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Framework Overview](https://docs.spring.io/spring-integration/reference/overview.html)
