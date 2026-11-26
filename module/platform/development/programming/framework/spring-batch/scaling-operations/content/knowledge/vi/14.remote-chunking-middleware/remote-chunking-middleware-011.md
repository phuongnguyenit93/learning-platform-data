# Đảm bảo thứ tự nếu nghiệp vụ yêu cầu trong remote chunking

## Mục tiêu bài học

**Remote chunking** giúp Spring Batch phân phối phần xử lý và ghi dữ liệu sang nhiều worker JVM. Manager thường đọc dữ liệu, tạo chunk rồi chuyển chunk qua middleware; các worker xử lý và ghi, sau đó phản hồi kết quả. Đây là cách tận dụng tài nguyên phân tán khi CPU hoặc I/O của worker là nút thắt. Tuy nhiên, **các chunk được gửi theo thứ tự không có nghĩa chúng được xử lý, commit và tạo tác dụng nghiệp vụ theo cùng thứ tự**.

Với nhiều bài toán như nạp log để thống kê, thứ tự không quan trọng nếu dữ liệu ghi độc lập. Với nghiệp vụ như cập nhật số dư theo chuỗi giao dịch, áp dụng sự kiện thay đổi trạng thái đơn hàng hoặc xuất bản sự kiện phiên bản hóa, xử lý sai thứ tự có thể tạo kết quả không hợp lệ. Khi đó, muốn mở rộng Spring Batch an toàn phải đưa **hợp đồng thứ tự** vào thiết kế middleware, worker, transaction và cơ chế retry/restart.

Bài thuộc chương **Middleware remote chunking** của module **SPRING_BATCH_SCALING_OPERATIONS**. Trọng tâm là đảm bảo thứ tự *khi nghiệp vụ yêu cầu*, cân bằng giữa thread safety, tính đúng dữ liệu, throughput, khả năng khôi phục và chi phí vận hành.

Sau bài học, bạn có thể:

- Phân biệt thứ tự đọc, thứ tự gửi, thứ tự nhận, thứ tự xử lý và thứ tự commit trong remote chunking.
- Xác định nghiệp vụ cần **thứ tự toàn cục**, **thứ tự theo khóa** hay **không cần thứ tự**.
- Hiểu giới hạn FIFO của broker, consumer concurrency, prefetch, redelivery và retry.
- Thiết kế worker có **sequence/version guard**, idempotency và xử lý khoảng trống chuỗi sự kiện.
- Chọn giữa xử lý tuần tự, affinity theo khóa, reorder buffer và đổi sang partitioning.
- Đo tác động đến throughput và head-of-line blocking khi giảm concurrency để giữ thứ tự.
- Kiểm chứng tính đúng khi chunk đến đảo thứ tự, worker chết, response mất và job restart.

## 1. Vì sao remote chunking có thể phá vỡ thứ tự?

Giả sử manager đọc các giao dịch theo thứ tự:

~~~text
Chunk A: [giao dịch 101, giao dịch 102]
Chunk B: [giao dịch 103, giao dịch 104]
Chunk C: [giao dịch 105, giao dịch 106]
~~~

Manager lần lượt phát A, B, C. Nếu có nhiều worker, B có thể gặp dữ liệu nhẹ, hoàn thành trước A; C có thể commit trước B. Một worker cũng có thể xử lý A xong nhưng reply bị mất khiến A được xác minh hoặc thực hiện lại sau những chunk khác.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Middleware
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant DB as Database

    M->>Q: Gửi Chunk A
    M->>Q: Gửi Chunk B
    Q->>W1: Chunk A (xử lý chậm)
    Q->>W2: Chunk B (xử lý nhanh)
    W2->>DB: Commit Chunk B
    W2-->>M: Reply B
    W1->>DB: Commit Chunk A
    W1-->>M: Reply A
~~~

Kết quả **B commit trước A** mặc dù A được đọc và gửi trước. Điều này hoàn toàn có thể xảy ra trong kiến trúc song song và không mặc nhiên là lỗi framework.

Nếu A/B chỉ ghi các bản ghi độc lập bằng khóa duy nhất, sự đảo thứ tự có thể chấp nhận được. Nếu B là thao tác “giao hàng” còn A là thao tác “đã thanh toán” trên cùng đơn hàng, việc áp dụng B trước A có thể vi phạm quy tắc trạng thái.

**Kết luận đầu tiên:** phải phân biệt thứ tự mà middleware hỗ trợ với thứ tự **hiệu ứng nghiệp vụ đã commit ở đích**.

## 2. Năm loại thứ tự cần phân biệt

| Mức thứ tự | Ý nghĩa | Điều gì có thể làm thay đổi? |
| --- | --- | --- |
| **Read order** | Manager đọc item theo một thứ tự nguồn | SQL không ORDER BY, dữ liệu cập nhật, reader state |
| **Dispatch order** | Manager tạo và gửi chunk theo thứ tự | Thread khác, buffering, publish async, retry gửi |
| **Delivery order** | Broker giao message tới consumer | Partition/queue, nhiều consumer, prefetch, redelivery |
| **Processing order** | Worker bắt đầu/kết thúc xử lý | Thời gian khác nhau, thread pool, retry và backoff |
| **Commit/effect order** | Transaction hoặc side effect thật hoàn thành | DB lock, transaction, API latency, worker lỗi |

Một broker có thể có một dạng FIFO trong điều kiện nhất định nhưng **không hứa** rằng nhiều consumer kết thúc xử lý theo thứ tự FIFO. Ngay cả worker bắt đầu A trước B, nếu A thực hiện request HTTP lâu hơn thì B có thể tạo side effect trước.

### Chỉ định mức bảo đảm mong muốn

Nên viết yêu cầu dưới dạng kiểm chứng được:

- *Không yêu cầu thứ tự*: kết quả cuối cùng không phụ thuộc thứ tự item độc lập.
- *Theo khóa*: với cùng `orderId`, sự kiện phiên bản 8 phải được áp dụng trước phiên bản 9; các `orderId` khác có thể chạy đồng thời.
- *Theo nhóm/tenant*: mọi sự kiện thuộc một tenant phải được áp dụng theo sequence của tenant.
- *Toàn cục*: sự kiện `globalSequence = n` phải được áp dụng trước `n+1` trên toàn tập dữ liệu.

**Thứ tự theo khóa** thường là lựa chọn thực tế nhất nếu các aggregate độc lập: nó giữ đúng chuỗi của từng entity nhưng vẫn cho phép nhiều entity chạy song song.

## 3. Có thật sự cần giữ thứ tự không?

Trước khi viết cơ chế điều phối, kiểm tra tính chất toán học và nghiệp vụ của writer.

### 3.1. Ghi độc lập, có thể không cần thứ tự

Ví dụ mỗi item là một đơn hàng với business key riêng và writer upsert toàn bộ bản ghi. Nếu không có quan hệ phụ thuộc giữa các item, A rồi B hoặc B rồi A có thể cho cùng kết quả.

~~~sql
INSERT INTO normalized_orders(order_id, status)
VALUES (:orderId, :status)
ON CONFLICT (order_id)
DO UPDATE SET status = EXCLUDED.status;
~~~

Cần thận trọng: nếu cùng một `orderId` có nhiều version, phép upsert không có điều kiện có thể cho kết quả **phụ thuộc thứ tự** vì phiên bản cũ có thể ghi đè phiên bản mới.

### 3.2. Phép toán giao hoán vẫn có điều kiện

Phép cộng hai delta số học thường giao hoán, nhưng retry có thể cộng trùng. Vì vậy ngay cả khi thứ tự không quan trọng, **idempotency** vẫn quan trọng.

Hai giao dịch `+100` và `-50` trên một số dư có thể cho cùng số cuối trong phép cộng thuần, nhưng nghiệp vụ **không cho âm số dư** làm thứ tự trở nên quan trọng. Phải hiểu điều kiện nghiệp vụ, không chỉ nhìn kết quả tổng số học.

### 3.3. Chuỗi trạng thái phụ thuộc thứ tự

Ví dụ đơn hàng có các sự kiện:

~~~text
order-42 / seq=1: CREATED
order-42 / seq=2: PAID
order-42 / seq=3: SHIPPED
order-42 / seq=4: DELIVERED
~~~

Áp dụng seq=3 trước seq=2 có thể bị từ chối. Khi đó yêu cầu đúng là **thứ tự theo orderId**, không nhất thiết toàn cục giữa mọi đơn hàng.

### Câu hỏi thiết kế

1. Hai item khác business key có độc lập không?
2. Với cùng key, dữ liệu có sequence/version đơn điệu không?
3. Nếu thiếu một phiên bản trung gian, có được bỏ qua không?
4. Có thể áp dụng lại cùng event mà không tạo side effect trùng không?
5. Có yêu cầu downstream nhận message theo đúng thứ tự không, hay chỉ cần trạng thái DB cuối đúng?
6. Thứ tự phải đúng tại **bắt đầu xử lý**, tại **commit**, hay cả chuỗi giao tiếp bên ngoài?

Không nên ép thứ tự toàn cục nếu nghiệp vụ chỉ cần thứ tự từng account: làm như vậy tự tạo một bottleneck tuần tự không cần thiết.

## 4. Cách manager và worker hoạt động với các chunk

Một remote chunking pipeline có thể hình dung:

~~~mermaid
flowchart LR
    SRC[("Nguồn")] --> M["Manager Step<br/>ItemReader + chunk"]
    M --> Q[["Middleware<br/>requests"]]
    Q --> W1["Worker A<br/>process + write"]
    Q --> W2["Worker B<br/>process + write"]
    Q --> W3["Worker C<br/>process + write"]
    W1 --> DEST[("Đích")]
    W2 --> DEST
    W3 --> DEST
    W1 -. "reply" .-> R[["Reply channel"]]
    W2 -. "reply" .-> R
    W3 -. "reply" .-> R
    R -.-> M
~~~

Trong Spring Batch, các thành phần remote chunking và Spring Batch Integration cung cấp cơ chế trao đổi request/reply phù hợp với version được triển khai. **Hợp đồng chunk request không mặc định là hợp đồng thứ tự của business aggregate**.

Hai việc khác nhau cần được kiểm chứng:

1. **Kết quả xử lý chunk**: manager biết request nào được hoàn thành, thất bại hoặc chưa rõ trạng thái.
2. **Thứ tự hiệu ứng nghiệp vụ**: các thao tác đã commit ở DB/API đúng chuỗi cần thiết.

Việc manager cuối cùng nhận đủ reply **không tự chứng minh** các side effect đã xảy ra đúng thứ tự.

### Thứ tự trong một chunk

Item được đưa vào một chunk theo trình tự reader tạo ra có thể được processor/writer tiêu thụ trong trình tự tương ứng với cấu hình chuẩn, nhưng **không nên mặc định mọi custom writer, asynchronous processor hay DB engine đều ghi/commit từng item theo một thứ tự có ý nghĩa nghiệp vụ**.

Ví dụ writer batch gửi nhiều SQL update; điều cần kiểm tra là **trạng thái cuối và ràng buộc version trong DB**, chứ không chỉ thứ tự các phần tử trong danh sách đầu vào.

### Thứ tự giữa các chunk

Khi có nhiều worker hoặc chunk requests đang inflight, không có sự bảo đảm mặc định rằng chunk N commit trước chunk N+1. Nếu một business key nằm ở hai chunk liên tiếp, cần cơ chế bổ sung.

## 5. Đọc nguồn có thứ tự là điều kiện cần, chưa đủ

Giả sử nguồn là database. Một truy vấn không có `ORDER BY` không hứa thứ tự bản ghi, ngay cả khi hiện tại DB tình cờ trả kết quả tăng theo ID.

~~~sql
SELECT event_id, account_id, sequence_no, delta_cents
FROM account_events
WHERE business_date = :businessDate
ORDER BY account_id, sequence_no, event_id;
~~~

Mẫu này tạo thứ tự theo `account_id`, rồi theo `sequence_no`, rồi theo `event_id`. Cần có ràng buộc nghiệp vụ làm rõ uniqueness của sequence:

~~~sql
ALTER TABLE account_events
ADD CONSTRAINT uq_account_event_sequence
UNIQUE (account_id, sequence_no);
~~~

**Lưu ý:** thêm `event_id` vào ORDER BY chỉ có vai trò sắp xếp dứt khoát khi vẫn có dữ liệu trùng sequence ngoài dự kiến; ràng buộc uniqueness mới là cách bắt lỗi dữ liệu nguồn. Thứ tự đọc này là bước chuẩn bị, nhưng các chunk sau đó vẫn có thể bị worker xử lý đảo thứ tự.

### Không để bản ghi cùng khóa rơi tùy ý vào lane khác nhau

Nếu hệ thống muốn xử lý tuần tự theo `account_id`, phải xác định cách một key được gắn vào một **lane** xử lý. Chỉ sort dữ liệu theo accountId nhưng phát chunk qua một queue có nhiều consumer **không tự giữ tính tuần tự**.

Ngoài ra, một account có thể có 2.000 event, còn chunk size là 500. Account đó vẫn trải qua nhiều chunk; ngay cả khi toàn bộ bốn chunk đến cùng worker, việc xử lý đồng thời bốn request cũng có thể đảo commit.

## 6. Broker FIFO không đồng nghĩa commit-order

### 6.1. Queue kiểu RabbitMQ/AMQP

Một queue có thể giao message theo trật tự queue trong những điều kiện phù hợp, nhưng khi có:

- Nhiều consumer nhận từ cùng queue;
- Prefetch nhiều message cho mỗi consumer;
- Retry với requeue hoặc dead-letter;
- Các worker mất kết nối/khởi động lại;
- Các handler có thời gian xử lý khác nhau;

thì **thứ tự hoàn tất và side effect** không còn suy ra được chỉ từ thứ tự publish.

Một request B có thể đã được worker 2 commit trong khi worker 1 còn xử lý A. Requeue A sau lỗi càng làm khó lập luận về thứ tự.

### 6.2. Log phân vùng kiểu Kafka

Kafka duy trì thứ tự log **trong từng topic-partition**. Điều này hữu ích nếu mọi event của cùng aggregate được định tuyến nhất quán tới **một partition** và consumer xử lý tuần tự phần việc cần thứ tự, quản lý offset/retry phù hợp.

Nhưng Kafka **không cung cấp thứ tự toàn cục giữa mọi partition**, và thứ tự append trong log **không tự bảo đảm commit DB** diễn ra theo thứ tự nếu consumer dispatch message bất đồng bộ.

**Bẫy với remote chunking:** một chunk có thể chứa nhiều `account_id`. Nếu đặt Kafka key theo ID của item đầu tiên, những item còn lại trong chunk **không tự được đặt đúng lane theo aggregate**. Muốn dùng key affinity, cần thiết kế cách nhóm/bọc chunk theo key ngay từ manager hoặc một tầng chuyển tiếp có hợp đồng rõ.

### 6.3. Delivery guarantee và ordering là hai chiều độc lập

| Thuộc tính | Câu hỏi |
| --- | --- |
| Delivery | Message có thể bị mất, gửi lại hay bị trùng không? |
| Broker order | Message đi qua queue/partition theo thứ tự nào? |
| Consumer execution | Có mấy consumer/handler chạy đồng thời? |
| Commit order | Transaction DB/API tạo hiệu ứng lúc nào? |
| Recovery | Sau timeout/redelivery, phần việc cũ có thể chạy lại không? |

Không đánh đồng **at-least-once delivery**, **FIFO** và **exactly-once business effect**. Ba điều này không tự suy ra lẫn nhau.

## 7. Cấp độ bảo đảm thứ tự: chọn cái rẻ nhất đủ dùng

| Cấp độ yêu cầu | Giải pháp khả thi | Chi phí/chướng ngại |
| --- | --- | --- |
| Không cần thứ tự | Worker xử lý các chunk độc lập | Tối đa parallelism, nhưng vẫn cần idempotency |
| Thứ tự toàn cục | Một luồng xử lý/commit tại một thời điểm hoặc coordinator tuần tự nghiêm ngặt | Throughput bị giới hạn bởi đường tuần tự |
| Thứ tự theo key | Affinity theo key + một phần việc cùng key đang thực thi hoặc guard DB | Cần routing đúng, xử lý hot key |
| Trạng thái cuối không lùi version | Conditional update theo version | Có thể bỏ qua dữ liệu trung gian nếu business yêu cầu đủ mọi event |
| Áp dụng **đầy đủ và đúng thứ tự** | Sequence gap detection + chờ/park/retry hoặc reorder buffer bền vững | Tăng state, latency, recovery complexity |
| Chỉ output cuối được sắp xếp | Ghi kết quả độc lập rồi sort ở downstream | Không đảm bảo tác dụng bên ngoài được tạo theo thứ tự |

Cần làm rõ từ đầu: **“không cho phiên bản cũ ghi đè phiên bản mới”** là yêu cầu yếu hơn **“mọi event được áp dụng đúng thứ tự, không bỏ qua event nào”**.

Ví dụ một projection chỉ lưu trạng thái mới nhất có thể dùng last-version-wins có điều kiện nếu toàn bộ state có trong mỗi event. Nhưng hệ thống tính số dư theo **delta** không thể bỏ qua seq=10 rồi áp dụng seq=11: làm vậy mất một phần thay đổi.

## 8. Phương án A: tuần tự hoàn toàn khi nghiệp vụ yêu cầu global order

Nếu có một chuỗi sự kiện toàn cục mà mọi event phải được commit tuần tự, phương án dễ chứng minh nhất là **một đường xử lý có một phần việc inflight tại một thời điểm**.

Các yêu cầu đồng thời:

1. Manager đọc với thứ tự toàn cục ổn định và sequence không có khoảng trống ngoài chính sách.
2. Chỉ giao chunk kế tiếp khi chunk trước **đã thực sự hoàn tất nghiệp vụ**.
3. Worker xử lý nội dung chunk theo sequence; transaction, writer và side effect tuân thủ ràng buộc.
4. Retry của chunk cũ phải được giải quyết trước khi tiếp tục chunk mới.
5. Manager và worker có state bền vững để phục hồi từ checkpoint hợp lệ.

**Không đủ** nếu chỉ cấu hình một consumer nhưng manager đã gửi nhiều chunk đang chờ, rồi worker có callback hoặc writer bất đồng bộ. Phải xác minh ở **commit boundary**.

Thực tế, khi bắt buộc global order, lợi ích của remote chunking có thể rất hạn chế. Hãy cân nhắc giữ một step tuần tự và tối ưu reader, writer, commit interval hoặc thuật toán xử lý trước khi thêm middleware.

### Ước lượng giới hạn

Nếu mỗi item có thao tác phụ thuộc trước đó, thời gian tối thiểu theo mô hình tuần tự gần:

\[
T_{\mathrm{ordered}}\geq N \times t_{\mathrm{serial}}
\]

Trong đó `t_serial` là phần thời gian bắt buộc nằm trên critical path cho mỗi event. Con số đo thực tế còn phụ thuộc batch write, network và những phần có thể chuẩn bị song song. Việc có nhiều CPU core không xóa được phụ thuộc logic này.

## 9. Phương án B: giữ thứ tự theo khóa nhưng chạy nhiều khóa song song

Với nghiệp vụ theo `account_id`, các tài khoản độc lập có thể chạy đồng thời, nhưng chuỗi sự kiện **trong cùng tài khoản** phải được áp dụng tuần tự.

~~~mermaid
flowchart TB
    M["Manager: event có accountId"]
    M --> H["Routing theo aggregate key"]
    H --> L1["Lane 1: Account A, D, ..."]
    H --> L2["Lane 2: Account B, E, ..."]
    H --> L3["Lane 3: Account C, F, ..."]
    L1 --> W1["Worker 1: một key lần lượt"]
    L2 --> W2["Worker 2: một key lần lượt"]
    L3 --> W3["Worker 3: một key lần lượt"]
    W1 --> DB[("DB trạng thái")]
    W2 --> DB
    W3 --> DB
~~~

Điều kiện để giải pháp này **thực sự bảo đảm** thứ tự theo key:

- Tất cả phần việc chứa cùng key phải được đưa đến **cùng lane** trong vòng đời áp dụng chính sách.
- Mỗi lane phải giới hạn concurrent processing hoặc có hàng đợi theo key với cơ chế tuần tự thích hợp.
- Một key có thể trải qua nhiều chunk; cần giữ thứ tự **giữa các chunk của key đó**, không chỉ thứ tự trong mỗi chunk.
- Lỗi/retry ở event cũ phải chặn event sau của key cho đến khi xử lý hoặc có quyết định nghiệp vụ rõ.
- Rebalance khi tăng worker không được để key cũ đồng thời chạy trên hai lane trong khoảng chuyển giao.
- Writer và DB vẫn phải có idempotency/sequence guard để phòng trường hợp delivery trùng hoặc trạng thái không rõ.

### Ví dụ hash routing

Một hàm router minh họa:

~~~java
public final class KeyLaneRouter {
    private KeyLaneRouter() {}

    public static int laneFor(String aggregateId, int laneCount) {
        if (laneCount <= 0) {
            throw new IllegalArgumentException("laneCount must be positive");
        }
        return Math.floorMod(aggregateId.hashCode(), laneCount);
    }
}
~~~

Hàm xác định lane nhất quán **khi laneCount không đổi và key không đổi**, nhưng nó **không tự bảo đảm thứ tự**. Phần dispatch/worker phải thực sự tuân thủ lane ownership và xử lý tuần tự trên lane đó.

Nếu thay `laneCount` từ 8 lên 12 giữa một lần chạy, nhiều key có thể chuyển lane, gây nguy cơ key cũ đang chạy trên lane cũ mà event mới được giao tới lane mới. Cần kế hoạch drain/rebalance và ranh giới version của topology.

### Tại sao chunk thông thường khó gán một key?

Một chunk có thể chứa `[A:1, B:1, A:2, C:1]`. Không thể gán toàn bộ chunk cho *một account* mà vẫn nói chunk được định tuyến đúng theo từng key, trừ khi logic grouping hoặc một writer cấp dưới tách item thành các lane và có barrier/ack thích hợp.

Nếu việc cấu hình remote chunking chuẩn không đáp ứng được key-affinity, **không nên sửa message header đơn giản rồi tuyên bố đã giữ thứ tự**. Hãy cân nhắc remote partitioning, với worker đọc dữ liệu theo nhóm key/shard độc lập.

## 10. Phương án C: dùng sequence/version guard tại database

Ngay cả khi thiết kế router tốt, hệ thống phân tán vẫn phải đối mặt với **duplicate delivery, timeout và worker restart**. Một lớp bảo vệ cuối tại database giúp từ chối hiệu ứng sai thứ tự.

Giả sử mỗi event có:

~~~java
public record AccountEvent(
        java.util.UUID eventId,
        long accountId,
        long version,
        long deltaCents) {}
~~~

Dữ liệu nghiệp vụ cần có:

- `eventId` bất biến, duy nhất để nhận diện lần áp dụng lại.
- `accountId` xác định aggregate.
- `version` tăng từng bước theo aggregate, khởi đầu từ 1.
- `deltaCents` là biến động phải **áp dụng chính xác một lần**.
- Nếu event được sửa, payload hash/version hoặc chính sách correction phải được định nghĩa.

### Schema minh họa PostgreSQL

~~~sql
CREATE TABLE account_projection (
    account_id      BIGINT PRIMARY KEY,
    last_version    BIGINT NOT NULL DEFAULT 0,
    balance_cents   BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE applied_account_event (
    event_id        UUID PRIMARY KEY,
    account_id      BIGINT NOT NULL,
    version         BIGINT NOT NULL,
    payload_sha256  TEXT NOT NULL,
    CONSTRAINT uq_account_event_version
        UNIQUE (account_id, version)
);
~~~

Dự kiến các account được khởi tạo với `last_version=0` và số dư đúng nghiệp vụ trước khi phát chuỗi update. Với dữ liệu mới, phải có đường tạo account an toàn giao dịch.

### Guard sequence liên tiếp

~~~sql
UPDATE account_projection
SET balance_cents = balance_cents + :deltaCents,
    last_version = :eventVersion
WHERE account_id = :accountId
  AND last_version = :eventVersion - 1;
~~~

Chỉ khi hàng có version trước đúng bằng `eventVersion - 1` mới có thể áp dụng delta. Nếu số hàng update bằng 0, **không** mặc định rằng event đã được xử lý và có thể bỏ qua: có thể là duplicate, event đến quá sớm, account chưa tồn tại, hoặc dữ liệu bị lỗi.

Trong cùng **transaction DB**, cần phối hợp kiểm tra/insertion vào bảng `applied_account_event` và update projection để bảo đảm không có trạng thái đã cập nhật mà ledger chưa ghi (hoặc ngược lại). Tùy phương án, dùng `SELECT ... FOR UPDATE` hoặc conditional update và unique constraint; cần kiểm thử concurrency thật.

**Không đủ nếu chỉ dùng `last_version > eventVersion` để bỏ qua event.** Trong bài toán delta, một event cũ chưa từng được áp dụng mà bị bỏ qua vẫn có thể làm số dư sai. Phải có lịch sử event hoặc trạng thái version đủ tin cậy để xác minh.

## 11. Bốn trạng thái xử lý một event có sequence

Giả sử projection của account X đang ở `last_version=9` và worker nhận event:

| Tình huống | Dữ liệu | Hành động đúng khi yêu cầu đủ mọi event |
| --- | --- | --- |
| **Expected next** | `version=10`, chưa có trong ledger | Áp dụng atomically; ghi ledger; tăng last_version |
| **Exact duplicate** | `version=10` đã có, eventId và payload khớp | Trả kết quả idempotent, không áp dụng delta lần nữa |
| **Gap / too early** | `version=11`, version 10 chưa có | Không áp dụng; chờ/retry/park để 10 tới trước |
| **Stale/conflict** | `version<=9` nhưng eventId không khớp ledger | Báo conflict hoặc quy trình đối soát; không âm thầm bỏ qua |

Ở bảng này, `last_version` phải được kiểm tra **cùng ledger và trong transaction phù hợp**. Thứ tự kiểm tra trạng thái quan trọng: nếu gặp duplicate, nên xác nhận eventId, key, version và payload hash tương ứng; **không chỉ so version**.

### Pseudocode transactional projector

~~~java
// Pseudocode nghiệp vụ. Mọi thao tác DB trong CÙNG một
// transaction; hàng aggregate được lock/guard phù hợp.
void apply(AccountEvent event) {
    AppliedRecord prior = ledger.findByEventId(event.eventId());

    if (prior != null) {
        if (!prior.matches(event)) {
            throw new ConflictingDuplicateException();
        }
        return; // cùng event đã được áp dụng
    }

    AccountProjection current =
            projectionRepository.lockByAccountId(event.accountId());

    if (event.version() > current.lastVersion() + 1) {
        throw new SequenceGapException(
                event.accountId(), event.version());
    }

    if (event.version() <= current.lastVersion()) {
        throw new StaleOrConflictingEventException();
    }

    projectionRepository.applyDeltaAndAdvance(
            event.accountId(), event.deltaCents(), event.version());

    ledger.insert(
            event.eventId(), event.accountId(),
            event.version(), sha256OfCanonicalPayload(event));

    // Commit DB một lần, sau khi CẢ projection và ledger hợp lệ.
}
~~~

Đây là **mã giả mô tả thuật toán**, không phải lớp Java độc lập có thể biên dịch ngay. Những interface/exception và transaction boundary phải được ứng dụng tự định nghĩa. Nên dùng unique constraint để chặn race kể cả khi code sai; test hai worker cố áp dụng cùng version hoặc cùng eventId.

### Không giữ transaction chờ event còn thiếu

Nếu version 11 tới khi chưa có 10, **không nên mở transaction rồi sleep trong khi giữ row lock** chờ 10. Điều này gây head-of-line blocking, chiếm connection, làm tăng timeout và có thể tạo deadlock.

Thay vào đó: fail/defer nhanh, giải phóng transaction và dùng cơ chế điều phối/chờ có giới hạn hoặc inbox bền vững theo key.

## 12. Gap detection khác với “last write wins”

Có hai bài toán nghiệp vụ khác nhau:

### 12.1. Trạng thái snapshot đầy đủ

Nếu event version 12 chứa **toàn bộ snapshot trạng thái hiện tại** và nghiệp vụ chỉ cần trạng thái mới nhất, có thể dùng conditional update kiểu:

~~~sql
UPDATE customer_snapshot
SET name = :name,
    tier = :tier,
    last_version = :version
WHERE customer_id = :customerId
  AND last_version < :version;
~~~

Phép này ngăn version cũ **lùi trạng thái**. Nhưng nó **không áp dụng toàn bộ thay đổi trung gian** và không phù hợp khi mỗi event có side effect cần xảy ra hoặc khi transition phải hợp lệ.

### 12.2. Event delta hoặc state machine

Nếu event chỉ chứa **delta** hoặc một transition quan trọng, phải áp dụng đầy đủ version 10 rồi 11 rồi 12. Chỉ giữ version lớn nhất **làm mất event 10/11**. Cần **sequence liên tiếp**, phát hiện gap và quy trình giải quyết.

| Yêu cầu | Cách kiểm soát |
| --- | --- |
| Chỉ cần snapshot mới nhất | Monotonic version guard có thể đủ |
| Cần đủ tất cả delta | Ledger + next-version check + gap handling |
| Cần công bố mọi sự kiện ra hệ thống khác | Sequencing/ordering ở outbox hoặc downstream |
| Có chuyển trạng thái không hợp lệ | State-machine validation trong transaction |
| Có event bổ sung/correction | Version/correction policy rõ, không tùy tiện đảo thứ tự |

## 13. Phương án D: reorder buffer hoặc inbox bền vững

Nếu middleware cho phép chunk đến đảo thứ tự và không thể chặn dispatch theo key, có thể đặt một **reorder layer** trước khi áp dụng nghiệp vụ.

~~~mermaid
flowchart TB
    Q[["Chunk requests đến có thể đảo thứ tự"]]
    Q --> V["Validate eventId / key / version"]
    V --> I[("Durable inbox theo aggregate")]
    I --> G["Key sequencer<br/>chọn version kế tiếp"]
    G --> P["Processor/Writer"]
    P --> S[("State + applied ledger")]
    P --> O[["Ack/reply theo hợp đồng"]]
~~~

Ý tưởng:

1. Chuyển từng event vào inbox bền vững có unique key `(aggregateId, version)` và eventId.
2. Với mỗi aggregate, xác định `expectedVersion = lastApplied + 1`.
3. Chỉ chọn event có đúng expectedVersion để thực thi nghiệp vụ.
4. Sau commit, thử tiếp version kế tiếp; nếu thiếu thì dừng key đó và chờ.
5. Có metric và chính sách cho gap kéo dài, dữ liệu lỗi, TTL và DLQ.
6. Không đồng thời có hai sequencer cùng sở hữu một key mà không có lock/lease/fencing.

### Một schema inbox minh họa

~~~sql
CREATE TABLE pending_account_event (
    event_id       UUID PRIMARY KEY,
    account_id     BIGINT NOT NULL,
    version        BIGINT NOT NULL,
    payload        JSONB NOT NULL,
    received_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_pending_account_version
        UNIQUE (account_id, version)
);
~~~

Worker có thể lưu tạm event 11 trước 10 mà **không áp dụng delta 11**. Sau khi 10 được xử lý, sequencer lấy 11 từ inbox theo version.

### Ranh giới quan trọng trong Spring Batch

Nếu worker của remote chunking **chỉ lưu inbox rồi trả reply thành công**, manager có thể coi chunk đã hoàn thành trong khi hiệu ứng nghiệp vụ chính **chưa xảy ra**. Khi đó cần định nghĩa rõ:

- Job hoàn thành có nghĩa **đã ingest vào inbox** hay **đã áp dụng đến projection cuối cùng**?
- Ai theo dõi backlog inbox và điều kiện đã drain hết?
- Nếu sequencer xử lý thất bại sau khi manager báo COMPLETED, hệ thống xử lý như thế nào?
- Dữ liệu inbox được retention/cleanup ra sao và có thể replay thế nào?

Nếu SLA yêu cầu **toàn bộ hiệu ứng được áp dụng trước khi job COMPLETED**, cần barrier kiểm tra per-key backlog và lỗi, hoặc không tách việc apply ra ngoài vòng đời step mà thiếu cơ chế đồng bộ phù hợp.

**Reorder buffer không miễn phí**: nó thêm bảng/kênh, worker sở hữu key, trạng thái timeout, lưu trữ và khôi phục. Chỉ dùng khi yêu cầu thứ tự thực sự biện minh cho complexity này.

## 14. Phương án E: đổi sang remote partitioning theo khóa

Nếu nguồn có thể đọc trực tiếp theo `account_id`, `tenant_id` hoặc shard ổn định, **remote partitioning** đôi khi là mô hình tự nhiên hơn remote chunking cho bài toán per-key order.

Trong remote partitioning:

- Manager tạo partition với input theo aggregate range/shard.
- Mỗi worker `StepExecution` tự đọc dữ liệu nguồn theo `ORDER BY aggregate_id, sequence_no`.
- Các aggregate thuộc shard khác nhau có thể chạy đồng thời.
- Trong mỗi worker, giữ chunk execution tuần tự nếu cần.
- Writer dùng guard và idempotency để chống retry/redelivery.

~~~mermaid
flowchart LR
    M["Manager: chia aggregate/shard"] --> Q[["Yêu cầu partition"]]
    Q --> A["Worker A: keys 0..99"]
    Q --> B["Worker B: keys 100..199"]
    Q --> C["Worker C: keys 200..299"]
    A --> DB[("Nguồn/đích")]
    B --> DB
    C --> DB
~~~

So với remote chunking, manager **không phải đọc rồi chuyển toàn bộ item** qua broker. Mỗi worker sở hữu một phạm vi dữ liệu và có checkpoint riêng. Nhưng remote partitioning vẫn yêu cầu:

- Chia key **không chồng lấn**, ổn định khi restart.
- Bảo đảm một aggregate không được giao đồng thời cho hai StepExecution.
- Reader có thứ tự theo key/version, phù hợp index và dataset ổn định.
- Không tự bật multi-threaded step trong một partition nếu việc đó phá thứ tự theo key.
- JobRepository, worker lifecycle, rollback/restart và writer idempotent hoạt động đúng.

**Chọn mô hình theo dữ liệu và nghiệp vụ**, không cố giữ remote chunking nếu phải viết quá nhiều cơ chế phụ để cưỡng ép thứ tự.

## 15. Thứ tự trong Spring Integration flow: đặt bảo đảm ở đâu?

Với Spring Integration, có thể xây flow khái niệm:

~~~text
Manager reader/chunk
    → outbound gateway/channel
    → broker request destination
    → inbound adapter tại worker
    → remote chunk handler
    → worker processor/writer
    → reply channel
    → manager
~~~

Những nơi có thể làm thay đổi concurrency:

- Outbound channel có buffering hoặc gửi async.
- Broker có nhiều partition/queue.
- Inbound listener có nhiều consumer.
- Channel dùng executor để giao message cho nhiều thread.
- Worker handler xử lý đồng thời nhiều chunk.
- Writer gọi API async hoặc DB transaction hoàn tất khác thời điểm.
- Error flow retry/requeue trong khi các chunk sau vẫn tiếp tục.

### Hỏi đúng câu ở từng tầng

| Tầng | Điều phải xác minh |
| --- | --- |
| Manager reader | Có thứ tự nguồn ổn định và input snapshot không? |
| Chunk boundary | Một key có thể trải qua nhiều chunk không? |
| Outbound gateway | Có giới hạn inflight và correlation đúng không? |
| Broker | FIFO theo queue/partition nào, redelivery ra sao? |
| Inbound consumer | Concurrency/prefetch/retry làm thay đổi completion order không? |
| Worker handler | Có xử lý chunk song song trong cùng JVM không? |
| Writer | Sequence guard/idempotency ở transaction thật chưa? |
| Reply handling | Reply đảo thứ tự hoặc reply cũ có được gắn đúng request không? |

**Không dùng một cấu hình như `concurrency=1` ở một tầng để suy ra an toàn toàn tuyến.** Nó chỉ giới hạn một phần của hệ thống. Nếu manager gửi nhiều chunk qua nhiều channel hoặc writer async, các phần khác vẫn có thể tạo đảo thứ tự.

### Mã minh họa ranh giới kiểm soát concurrency

~~~java
// Ví dụ cấu hình executor ở một adapter tùy biến.
// Đây KHÔNG phải cấu hình remote chunking hoàn chỉnh.
@Bean
public java.util.concurrent.ExecutorService
        orderedLaneExecutor() {
    return java.util.concurrent.Executors
            .newSingleThreadExecutor();
}
~~~

Một lane một thread xử lý các task lần lượt **theo thứ tự mà lane nhận task**, không tự bảo đảm thứ tự nghiệp vụ khi chúng đến đã bị đảo. Cần thêm sequence validation và kiểm soát việc enqueue, ack/retry/commit. Trong production phải quản lý lifecycle/shutdown của executor phù hợp, không mở thread pool tự do trong mỗi chunk.

Các builder và adapter của Spring Batch Integration/Spring Integration thay đổi theo phiên bản; hãy dựa trên contract của version dự án khi nối flow thật, không copy một cấu hình broker thiếu reply/error handling rồi giả định đã bảo đảm ordering.

## 16. Retry và redelivery dễ phá vỡ thứ tự hơn happy path

Giả sử:

~~~text
T0: Chunk A (seq 10) được giao Worker 1.
T1: Chunk B (seq 11) được giao Worker 2.
T2: Worker 1 gặp timeout, A phải retry.
T3: Worker 2 ghi seq 11 thành công.
T4: A được giao lại và ghi seq 10.
~~~

Nếu writer không có sequence guard, trạng thái có thể sai. Nếu writer có guard liên tiếp, B phải **tạm dừng hoặc thất bại có thể retry** khi 10 chưa được áp dụng.

### Retry tại các tầng khác nhau

| Tầng retry | Ví dụ | Rủi ro với order |
| --- | --- | --- |
| **Item-level** | Processor lỗi tạm thời trên một item | Item sau có bị xử lý trước không? |
| **Chunk transaction** | Một SQL statement lỗi, cả chunk rollback | Chunk sau có đang chạy/commit không? |
| **Message transport** | Broker redeliver request vì ack thiếu | Chunk cũ có thể đến sau chunk mới |
| **Manager/request timeout** | Manager chưa nhận reply | Chunk có thể đã commit nhưng trạng thái chưa rõ |
| **Job restart** | Chạy lại worker/chunk chưa hoàn tất | Input/sequence và idempotency có ổn định không? |

**RetryLimit lớn không thay thế việc giữ thứ tự.** Nếu seq 10 bị lỗi dữ liệu vĩnh viễn, retry liên tục chỉ làm key đó tắc. Cần phân loại lỗi tạm thời với lỗi nghiệp vụ và chính sách điều tra/khắc phục.

### Poison message và head-of-line blocking

Một event hỏng tại version 10 khiến version 11, 12, 13 không thể áp dụng nếu yêu cầu strict order. Đẩy version 10 sang dead-letter rồi cho 11 chạy **không bảo đảm đúng** nếu thiếu 10 là một bước bắt buộc.

Các cách xử lý:

- Dừng riêng aggregate đó, không nhất thiết dừng mọi aggregate khác.
- Đưa lỗi vào hàng điều tra với cảnh báo và quy trình sửa/phát lại version 10.
- Định nghĩa **skip có ngữ nghĩa** nếu nghiệp vụ thực sự cho phép; ghi nhận gap đã được chấp nhận.
- Áp dụng bản snapshot bù hoặc correction event khi có quy trình được duyệt.
- Không giữ DB transaction/chunk thread vô thời hạn trong lúc chờ xử lý thủ công.

## 17. Reply đến đảo thứ tự có phải lỗi?

Không nhất thiết. Trong remote chunking, manager có thể nhận:

~~~text
Request A gửi trước B
Reply B nhận trước A
~~~

Điều quan trọng với quản lý execution là **reply được ghép đúng request/chunk và trạng thái tương ứng**, không phải cố sắp xếp reply theo thời điểm đến rồi suy ra processing order.

Nếu một reply A đến muộn sau timeout, cần kiểm tra **correlation ID**, JobExecution/StepExecution và trạng thái request. Không coi reply đến muộn là kết quả của chunk đang chờ khác.

**Tách hai trách nhiệm:**

- **Protocol correctness:** không nhầm reply, không mất dấu work item và xử lý trạng thái lỗi đúng.
- **Business ordering:** DB/API không áp dụng transition sai thứ tự, không bỏ qua event bắt buộc.

Một hệ thống có thể có protocol đúng nhưng business ordering sai; cũng có thể giữ business ordering bằng guard DB dù reply đến đảo thứ tự. Hai loại kiểm thử cần độc lập.

## 18. Chunk size và số worker ảnh hưởng ordering như thế nào?

Một chunk nhỏ giảm số item có thể bị rollback khi lỗi nhưng tăng request/reply, broker traffic và chi phí coordination. Chunk lớn giảm số message nhưng:

- Tăng payload, serialization và thời gian xử lý một request.
- Có thể chứa nhiều aggregate lẫn nhau, khó route theo key.
- Có thể khiến một aggregate trải qua nhiều chunk vẫn không có thứ tự xuyên chunk.
- Làm retry của chunk nặng hơn.
- Tăng nguy cơ một hot key giữ lane quá lâu.

### Ví dụ tính số chunk

Với 2 triệu item và chunk size `c`, số chunk lý tưởng:

\[
N_{\mathrm{chunks}}\approx\left\lceil\frac{2.000.000}{c}\right\rceil
\]

| Chunk size | Số chunk gần đúng | Điều cần theo dõi |
| ---: | ---: | --- |
| 100 | 20.000 | Lượng message/metadata lớn |
| 500 | 4.000 | Điểm benchmark trung gian |
| 1.000 | 2.000 | Payload và rollback tăng |
| 5.000 | 400 | Ít request, hot key/chunk lớn |

Số message thực còn có reply, retry, redelivery và protocol metadata. Không lấy số chunk làm số message chính xác trong broker.

**Khi strict order theo key**, kích thước chunk cần được chọn cùng chính sách nhóm key và giới hạn inflight; không chỉ tune theo commit overhead.

### Throughput cận trên

Nếu một key bắt buộc được xử lý tuần tự với tốc độ `r_key` và có `K` key độc lập, throughput lý tưởng theo mô hình đơn giản:

\[
R \leq \min(K\times r_{\mathrm{key}},
            R_{\mathrm{read}},R_{\mathrm{write}},
            R_{\mathrm{transport}})
\]

Tổng throughput còn chịu phân bố key và giới hạn chung. Một key nóng chiếm 80% dữ liệu có thể quyết định thời gian job dù nhiều lane còn rảnh. Công thức minh họa chỉ có ích khi key tương đối đồng đều; không coi nó là dự báo chính xác.

## 19. Cân bằng tải khi có một hot key

Giả sử 10 triệu event thuộc 100.000 account, nhưng 60% event lại thuộc một account đặc biệt.

Nếu mọi event của account nóng phải đi đúng thứ tự, **một lane cho account đó** có thể là bottleneck. Tăng từ 8 lên 32 worker không làm một account có thể chạy song song nếu nghiệp vụ cấm.

~~~mermaid
flowchart TB
    K["10 triệu events"]
    K --> H["Hot account: 6 triệu events"]
    K --> O["99.999 accounts còn lại: 4 triệu"]
    H --> L["Một ordered lane<br/>critical path dài"]
    O --> P["Nhiều lane song song"]
    L --> J["Job kết thúc khi mọi lane hoàn thành"]
    P --> J
~~~

Các lựa chọn khả thi:

1. **Tối ưu thuật toán của hot key**: batch/coalesce các event nếu phép biến đổi cho phép mà vẫn giữ ngữ nghĩa.
2. **Dùng snapshot trung gian có xác thực**: giảm số event phải replay, nếu nghiệp vụ cho phép.
3. **Thay cách mô hình hóa aggregate**: tách thành các sub-aggregate độc lập thật sự.
4. **Chấp nhận SLA khác cho key nóng** hoặc cửa sổ xử lý dài hơn.
5. **Giữ strict order** thay vì cố phân tán cùng key bằng cách không hợp lệ.

Đừng tách một account thành nhiều lane chỉ vì muốn dùng hết CPU nếu các thay đổi cùng account vẫn phụ thuộc nhau.

## 20. Mô hình lưu trạng thái bền vững cho ordering

Một `HashMap<accountId,lastVersion>` trong worker JVM có thể giúp kiểm tra tạm thời, nhưng **không đủ** khi:

- Worker JVM bị kill và được thay thế.
- Cùng key chuyển sang worker khác sau rebalance.
- Manager gửi lại chunk sau timeout.
- Có nhiều process cùng ghi trạng thái đích.
- Job restart với checkpoint khác.

**Nguồn sự thật cho thứ tự đã áp dụng** nên được đặt ở lưu trữ bền vững hoặc cơ chế sequencer có khả năng phục hồi, thường gần với giao dịch ghi kết quả.

### State tối thiểu cần có

| State | Ý nghĩa |
| --- | --- |
| Aggregate ID | Xác định chuỗi độc lập |
| Last applied version | Mốc sequence đã commit |
| Applied event IDs / payload hash | Nhận biết duplicate và conflict |
| Pending gap/inbox | Theo dõi phiên bản đến trước thời điểm có thể áp dụng |
| Ownership/lease/fencing (nếu dùng) | Ngăn hai sequencer cùng sở hữu key |
| Checkpoint/StepExecution | Trạng thái Spring Batch theo phần việc |
| Correlation/request ID | Đối chiếu request/reply transport |

Không gom mọi dữ liệu business và ledger vào `ExecutionContext` của StepExecution. Context nên giữ trạng thái checkpoint cần thiết; history/idempotency theo aggregate thường thuộc DB nghiệp vụ hoặc store chuyên biệt.

### At-least-once + idempotency

Một hướng thiết kế thực dụng là chấp nhận middleware **có thể giao lại** message, rồi bảo vệ side effect ở DB bằng **unique key + sequence guard + transaction**. Đó là cách đạt **hiệu ứng nghiệp vụ lặp lại an toàn** cho những nguồn lực nằm trong transaction được thiết kế.

Không hứa “exactly once” trên toàn bộ DB, broker và API ngoài khi chưa có cơ chế giao dịch/phối hợp rõ ràng.

## 21. Restart Spring Batch không tự tái tạo business order

Spring Batch dùng JobRepository, StepExecution và ExecutionContext để theo dõi trạng thái và hỗ trợ restart. Nhưng các thành phần này **không tự biết** rằng event 101 của account X phải commit trước event 102.

Khi restart, cần:

- Input snapshot/cutoff và reader order ổn định.
- Chunks đã xử lý được nhận diện chính xác theo giao thức/metadata.
- Worker chưa chắc chết khi manager timeout; phải tránh chạy đồng thời cùng phần việc.
- Ledger/version guard bảo vệ dữ liệu khi replay.
- Key routing hoặc ownership được giữ đúng nếu dùng affinity.
- Gap và pending inbox được phục hồi, không mất khi JVM chết.
- Chính sách poison message không cho vượt qua event bắt buộc một cách im lặng.

### Nhầm lẫn phổ biến

**“Reader saveState(true) thì mọi event giữ đúng thứ tự.”** Sai. Reader checkpoint giúp phục hồi vị trí đọc theo cơ chế của reader, nhưng không bảo đảm thứ tự commit giữa nhiều worker sau khi item đã rời manager.

**“StepExecution COMPLETED nghĩa là mọi side effect đã xảy ra đúng thứ tự.”** Sai. Nó phản ánh kết quả thực thi theo framework/protocol; cần kiểm tra trạng thái nghiệp vụ và những thao tác ngoài transaction.

### Kiểm tra sau restart

Đối soát theo key:

~~~sql
SELECT account_id, MAX(version) AS max_applied_version,
       COUNT(*) AS applied_events
FROM applied_account_event
GROUP BY account_id;
~~~

Truy vấn giúp thống kê, nhưng **MAX(version) = COUNT(*) không đủ** nếu version không bắt đầu từ 1 hoặc có dữ liệu sửa/xóa. Cần so với tập event nguồn được chốt, kiểm tra uniqueness, khoảng trống sequence, eventId/payload hash và projection.

## 22. Kiểm thử đảo thứ tự một cách có chủ đích

Đừng chỉ test happy path với một worker. Một test ordering đúng phải cố ý tạo tình huống **B hoàn tất trước A** và chứng minh kết quả nghiệp vụ vẫn đúng hoặc B bị trì hoãn an toàn.

### 22.1. Test phần lõi theo sequence

Với account 42, events:

~~~text
E1: version=1, delta=+100
E2: version=2, delta=-20
E3: version=3, delta=+50
Expected balance: 130
Expected lastVersion: 3
~~~

Gửi theo thứ tự **E3, E1, E2**. Kỳ vọng:

1. E3 không được áp dụng khi thiếu version 1 và 2.
2. E1 được áp dụng một lần.
3. E2 được áp dụng sau E1.
4. E3 được áp dụng sau E2.
5. Sau duplicate E2, balance vẫn 130 và ledger không tăng.
6. Sau một event khác có cùng eventId nhưng payload khác, hệ thống báo conflict.

### 22.2. Test hai worker cùng key

Cho hai worker cố áp dụng version 2 đồng thời. DB transaction/unique constraint phải ngăn cả hai cùng tăng số dư. Với version 2 và 3 chạy đồng thời, chỉ version 2 có thể áp dụng khi lastVersion=1; version 3 phải chờ/retry sau đó.

### 22.3. Test broker/worker

| Tình huống | Kỳ vọng |
| --- | --- |
| Chunk B tới worker trước A | Không áp dụng transition B nếu thiếu A |
| A xử lý chậm, B xử lý nhanh | Thứ tự commit nghiệp vụ vẫn hợp lệ |
| Worker kill trước commit | Event chưa commit được làm lại |
| Worker kill sau commit trước ack/reply | Redelivery không áp dụng delta hai lần |
| Manager nhận reply B trước A | Correlation đúng; không suy ra ordering từ reply |
| Retry/requeue A | B không vượt A trong cùng aggregate |
| Key chuyển lane khi scale worker | Không có hai owner đang áp dụng cùng key |
| Poison version 10 | Version 11/12 bị chặn hoặc xử lý theo policy được phê duyệt |
| Restart JobInstance | Không mất inbox/ledger, không đổi key ownership thiếu kiểm soát |
| API downstream timeout sau khi nhận request | Idempotency key ngăn side effect lặp |

### 22.4. Test bộ dữ liệu lớn

Với nhiều account:

- Random hóa độ trễ mỗi worker.
- Phân phối event không đều, có hot key.
- Tạo duplicate và stale events.
- Cho một số version mất tạm thời rồi đến muộn.
- Kiểm tra output theo **tập event và trạng thái từng account**, không chỉ tổng writeCount.
- Chạy nhiều lần, so cùng dataset và kiểm tra p95/p99 latency của key bị chờ.

Một stress test không phát hiện lỗi vẫn **không** chứng minh rằng mọi interleaving đều đúng. Hợp đồng dữ liệu, transaction và protocol phải được chứng minh ở mức thiết kế rồi mới được kiểm chứng bằng test.

## 23. Observability: không chỉ đếm message

Trong production, một job “đang chờ” có thể vì DB chậm, một key bị gap hay broker tích lũy request.

| Metric | Vai trò |
| --- | --- |
| `chunk.request.sent` / `chunk.reply.received` | Lưu lượng và hoàn tất protocol |
| **Inflight chunks** | Có bao nhiêu phần việc chưa rõ kết quả |
| **Queue depth/age** | Broker đang tồn đọng bao lâu |
| **Per-key backlog** | Một aggregate đang chờ bao nhiêu event |
| **Sequence gap count/age** | Có thiếu version trung gian không, đợi bao lâu |
| **Duplicate/conflict count** | Retry bình thường hay vi phạm hợp đồng dữ liệu |
| **Reorder buffer size** | Bộ nhớ/DB inbox có vượt ngân sách không |
| **Last applied version** | Mốc tiến triển thực tế của business aggregate |
| **DB commit/lock wait** | Bị nghẽn ở transaction thay vì middleware |
| **Retry/rollback/timeout** | Lỗi vận hành ảnh hưởng ordering |
| **End-to-end job elapsed** | Có đáp ứng SLA không |
| **Reconciliation errors** | Có mất/nhân event hay projection sai không |

Log minh họa:

~~~text
jobExecutionId=8012
stepExecutionId=8066
chunkCorrelationId=chunk-4439
worker=chunk-worker-03
aggregateId=account-42
eventId=8fe2f99c-xxxx
eventVersion=11
lastAppliedVersion=9
orderingDecision=DEFER_GAP
reason=WAITING_FOR_VERSION_10
retryAttempt=2
status=PENDING
~~~

Dữ liệu giả định. Đừng đưa raw account IDs hay event IDs thành metric label có cardinality quá cao; log/tracing có kiểm soát phù hợp hơn cho chi tiết. Tránh log nội dung nhạy cảm hoặc token.

### Cảnh báo quan trọng

- Gap tồn tại quá thời gian SLA.
- Head-of-line blocking ở key nóng tăng.
- Duplicate/conflict tăng sau rollout.
- Queue age tăng dù worker CPU rảnh.
- DB connection wait tăng theo consumer concurrency.
- Job được đánh dấu hoàn thành nhưng inbox còn pending ngoài chính sách.
- Một key có nhiều owner hoặc hai worker cùng áp dụng một version.

## 24. Đánh đổi throughput khi buộc giữ thứ tự

Đảm bảo thứ tự thường giảm mức song song **trên phần dữ liệu có phụ thuộc**, nhưng không nhất thiết làm toàn job trở nên tuần tự.

Ví dụ giả định:

| Kiến trúc | Worker | Throughput hữu ích | Tính đúng theo key | Ghi chú |
| --- | ---: | ---: | --- | --- |
| Remote chunking không guard | 8 | 18.000 event/s | **FAIL** | Commit đảo thứ tự |
| Một lane tuần tự toàn cục | 1 | 2.800 event/s | PASS | Không tận dụng nhiều key |
| Bốn lane theo key + sequence guard | 4 | 9.200 event/s | PASS | Các key chạy song song |
| Tám lane theo key + sequence guard | 8 | 13.800 event/s | PASS | Tăng tốc có ích |
| Mười sáu lane theo key | 16 | 14.100 event/s | PASS | Gần giới hạn DB |
| Tám lane + inbox/reorder | 8 | 12.300 event/s | PASS | Chi phí lưu/chờ bổ sung |

Tất cả con số là **ví dụ giả định**, không phải benchmark của Spring Batch hay broker cụ thể. Điểm đáng chú ý là cấu hình **18.000 event/s nhưng sai dữ liệu không hợp lệ**, còn cấu hình giữ đúng thứ tự và đáp ứng SLA mới có giá trị.

### Phân tích điểm bão hòa

Nếu CPU worker còn dư nhưng `sequence_gap_age` tăng, có thể lỗi do key routing/thiếu event hơn là thiếu CPU. Nếu DB lock wait tăng khi tăng lane, cơ sở dữ liệu có thể là bottleneck. Nếu chỉ một hot key có backlog, tăng số lane cho các key khác có thể không giảm thời gian job.

Nên benchmark cùng dataset, cùng sequence distribution, cùng tỷ lệ duplicate/late events và thử fault injection. Không tối ưu chỉ dựa vào **số message/s**: nhiều message được “xử lý” nhưng bị reject vì gap không tương đương nhiều event đã áp dụng thành công.

## 25. Tình huống thực tế: 12 triệu sự kiện trạng thái đơn hàng

Một doanh nghiệp nạp **12 triệu sự kiện** từ nhiều đơn hàng vào hệ thống trạng thái. Mỗi đơn hàng có một chuỗi `orderVersion` bắt đầu từ 1. SLA: hoàn thành trong **20 phút** sau khi chốt đầu vào.

Throughput áp dụng thành công tối thiểu theo phép chia lý tưởng:

\[
R_{\mathrm{required}}=
\frac{12.000.000}{20\times60}
=10.000\ \mathrm{events/s}
\]

Giả sử hệ thống ban đầu remote chunking có tám worker. Manager đọc ORDER BY `order_id, version`, nhưng chunk có thể chứa nhiều đơn hàng và worker xử lý song song.

### Hiện trạng: tốc độ cao, state sai

Trong benchmark giả định:

- Đọc/gửi đạt 17.000 event/s.
- Worker báo ghi được 15.000 event/s.
- Một số đơn hàng kết thúc ở trạng thái `SHIPPED` dù thiếu event `PAID`.
- Một số event version cũ ghi đè trạng thái version mới.
- Khi giảm worker xuống một, lỗi giảm mạnh nhưng SLA có nguy cơ không đạt.

**Nguyên nhân:** dữ liệu được manager đọc có thứ tự nhưng chunk commit khác thứ tự. FIFO của broker không bảo vệ business state khi nhiều worker cùng xử lý.

### Phương án 1 — Thêm guard ở đích

Thiết kế bảng projection có `last_version` và ledger eventId. Worker chỉ áp dụng version kế tiếp trong cùng transaction, exact duplicate được chấp nhận idempotently, gap được hoãn để xử lý sau.

Điều này **ngăn kết quả sai**, nhưng nếu chunk chứa nhiều key và chỉ một event gap làm cả chunk rollback, throughput có thể giảm mạnh. Cần xác định chính sách xử lý item lỗi và tránh việc các key không liên quan bị chặn quá lâu.

### Phương án 2 — Thiết kế lane theo orderId

Chuyển trách nhiệm grouping/routing theo `order_id` vào pipeline được thiết kế rõ. Mọi event của một order đi cùng lane và chỉ có một phần việc order inflight. Các order khác vẫn song song. Worker giữ guard DB làm hàng rào cuối cho redelivery/restart.

Nếu remote chunking hiện có **không thể tạo chunk phù hợp key** mà không thay đổi lớn, nhóm đánh giá remote partitioning để worker tự đọc order ranges.

### Phương án 3 — Đo lại tài nguyên

Giả định sau khi thay thiết kế:

| Cấu hình | Throughput áp dụng thành công | Trạng thái dữ liệu | Thời gian lý tưởng với 12 triệu |
| --- | ---: | --- | ---: |
| 1 lane toàn cục | 3.000 event/s | PASS | 66,7 phút |
| 4 lanes theo orderId | 8.200 event/s | PASS | 24,4 phút |
| 8 lanes theo orderId | 11.500 event/s | PASS | 17,4 phút |
| 12 lanes theo orderId | 11.800 event/s | PASS | 16,9 phút |

Số liệu **giả định** và thời gian là phép tính `N/R`, chưa tính khởi tạo, retry hay bước tổng hợp. Trong kịch bản này, tám lane vượt ngưỡng lý tưởng 10.000 event/s; tuy nhiên còn phải bảo đảm đủ dư địa cho overhead và lỗi. Tăng lên 12 lane chỉ cải thiện nhỏ trong khi có thể làm tăng DB contention.

### Kiểm thử trước production

1. Chọn một order có ít nhất 20 events, chia chúng cố ý vào nhiều chunk.
2. Làm chậm chunk đầu, cho chunk sau đến trước.
3. Kiểm tra không có transition trái sequence.
4. Kill worker sau commit trước reply; replay event và xác nhận không áp dụng hai lần.
5. Tạo một gap vĩnh viễn; kiểm tra SLA/alert và quy trình xử lý poison event.
6. Kiểm tra hot order và mức backlog theo key.
7. Restart JobInstance; so business state cuối với nguồn được chốt.

**Kết luận tình huống:** một cơ chế bảo đảm thứ tự hữu ích phải duy trì **tính đúng** trong mọi đường lỗi được hỗ trợ và vẫn đáp ứng throughput. “Broker có FIFO” hoặc “manager đọc ORDER BY” không đủ.

## 26. Khi nào không nên dùng remote chunking để giữ thứ tự?

Nên cân nhắc thay kiến trúc nếu xuất hiện các dấu hiệu:

- Nghiệp vụ yêu cầu thứ tự **toàn cục tuyệt đối** cho phần lớn item.
- Một key kéo dài qua nhiều chunk và hệ thống không thể ràng buộc chỉ một chunk key đang inflight.
- Bắt buộc mọi side effect xảy ra tuần tự nhưng writer gọi nhiều API ngoài khó đồng bộ transaction.
- Reorder buffer, per-key lane, ledger và barrier khiến remote chunking trở nên phức tạp hơn partitioning.
- Reader manager đã là bottleneck, nên truyền chunk qua broker không còn giá trị.
- Thời gian xử lý các key quá lệch, hot key quyết định SLA.
- Không có stable eventId/sequence và nguồn không thể bổ sung: muốn bảo đảm order chính xác sẽ rất khó chứng minh.

Các hướng thay thế:

- Step tuần tự có JDBC batching/query tối ưu.
- Parallel steps cho các flow nghiệp vụ độc lập.
- Local partitioning theo aggregate nếu một JVM đủ tài nguyên.
- Remote partitioning theo key/range với worker tự đọc.
- Ingestion vào durable inbox và xây một sequencer chuyên trách khi yêu cầu phức tạp.
- Đổi mô hình dữ liệu sang snapshot/versioned state khi nghiệp vụ chấp nhận.

Không có giải pháp tốt chung cho mọi bài toán: chọn kiến trúc ít phức tạp nhất đã được kiểm chứng là đáp ứng **order contract, correctness, SLA và restart**.

## 27. Các nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật cần nhớ |
| --- | --- |
| “Manager ORDER BY nên worker chắc commit đúng thứ tự.” | Dispatch/read order không quyết định worker completion/commit order. |
| “Broker hỗ trợ FIFO nên nhiều consumer vẫn ghi FIFO.” | Nhiều consumer và latency khác nhau làm completion order thay đổi. |
| “Kafka bảo đảm thứ tự của toàn topic.” | Kafka bảo đảm thứ tự log trong **mỗi partition**, không toàn cục các partition. |
| “Chunk đầu tiên chứa account A nên cả chunk là lane của A.” | Một chunk có thể chứa nhiều key; routing theo key cần hợp đồng ở cấp item/group. |
| “Một consumer là đủ bảo đảm mọi thứ tự.” | Còn async handler, requeue, retry, transaction và logic manager. |
| “Tăng consumer sẽ không ảnh hưởng nghiệp vụ.” | Có thể làm chunk sau commit trước chunk trước. |
| “Chỉ dùng last-version-wins là đúng cho delta.” | Bỏ qua version trung gian sẽ làm mất một phần hiệu ứng. |
| “Duplicate version có thể bỏ qua mà không cần ledger.” | Cần kiểm tra eventId/payload và lịch sử để phân biệt duplicate với conflict. |
| “Gap có thể giải quyết bằng sleep trong transaction.” | Giữ lock/connection để chờ dễ gây timeout và deadlock. |
| “DLQ version 10 xong cứ xử lý version 11.” | Strict order yêu cầu xử lý/ra quyết định rõ về version 10. |
| “Ack của broker đồng nghĩa DB commit đúng một lần.” | Ack và commit có thể không atomic; cần idempotency. |
| “Remote chunking tự giữ thứ tự theo account.” | Không mặc định; phải thiết kế routing/sequence/writer. |
| “Job COMPLETED có nghĩa inbox đã drain.” | Nếu chỉ ingest vào inbox, phải có barrier và điều kiện hoàn tất rõ. |
| “Chỉ cần đếm writeCount là biết projection đúng.” | Cần đối soát business key, version, gap và trạng thái cuối. |

## 28. Checklist thiết kế bảo đảm thứ tự

- [ ] Đã ghi rõ yêu cầu order toàn cục/theo key/không cần order.
- [ ] Đã phân biệt thứ tự read, dispatch, delivery, processing, commit và downstream effect.
- [ ] Nguồn có `ORDER BY` ổn định và input snapshot/cutoff phù hợp.
- [ ] Business key, eventId và sequence/version được định nghĩa rõ, có uniqueness phù hợp.
- [ ] Biết một key có thể trải qua bao nhiêu chunk và các chunk ấy được điều phối ra sao.
- [ ] Không giả định FIFO broker là bảo đảm commit-order.
- [ ] Nếu key affinity, có routing đúng, single-owner/concurrency control và kế hoạch rebalance.
- [ ] Worker có sequence guard, ledger/idempotency và transaction hợp lệ.
- [ ] Có chính sách rõ cho gap, stale/conflicting event, duplicate và poison message.
- [ ] Không giữ transaction mở chỉ để chờ event phiên bản trước.
- [ ] Nếu dùng inbox, đã xác định job COMPLETED có nghĩa ingest hay applied.
- [ ] Có retry/backoff hữu hạn, timeout, ack/redelivery và cơ chế tương quan request/reply.
- [ ] Restart không làm đổi input/order contract hoặc mất trạng thái per-key.
- [ ] Có test đảo thứ tự cố ý, kill worker sau commit, duplicate request và reply đến trễ.
- [ ] Đo throughput **đã áp dụng thành công**, không chỉ message được gửi/nhận.
- [ ] Có metric per-key backlog, sequence gap age, DB lock wait và head-of-line blocking.
- [ ] Đã đánh giá có nên chuyển sang local/remote partitioning thay vì tăng độ phức tạp remote chunking.
- [ ] SLA cùng tính đúng dữ liệu được xác minh với tải và sự cố đại diện.

## 29. Câu hỏi tự kiểm tra

**1. Vì sao broker FIFO không bảo đảm hai chunk commit theo cùng thứ tự?**

Vì các chunk có thể được giao cho nhiều consumer, mất thời gian xử lý khác nhau hoặc retry. FIFO của một kênh không đồng nghĩa với thứ tự hiệu ứng DB/API sau khi xử lý.

**2. Một đơn hàng có bốn phiên bản nhưng các bản ghi được chia vào hai chunk. Chỉ sort mỗi chunk có đủ không?**

Không. Cần giữ thứ tự **xuyên chunk** cho cùng đơn hàng; nếu hai chunk đến hai worker khác nhau, chunk phiên bản sau có thể commit trước.

**3. Thế nào là khác biệt giữa last-version-wins và strict sequential application?**

Last-version-wins có thể chấp nhận trạng thái snapshot mới nhất mà không áp dụng event trung gian. Strict sequential application bắt buộc áp dụng mọi event theo nextVersion, đặc biệt với delta và state machine.

**4. Nếu projection đang ở version 9 mà nhận version 11, writer nên làm gì?**

Không áp dụng delta 11. Phải báo gap và hoãn/retry/park theo chính sách, chờ version 10 hoặc có quyết định nghiệp vụ rõ.

**5. Vì sao sequence guard cần phối hợp với ledger trong một transaction?**

Để bảo vệ trạng thái đã áp dụng và nhận biết exact duplicate, không cập nhật projection hai lần hoặc mất ledger khi worker chết giữa các thao tác.

**6. Có thể route chunk theo accountId của item đầu tiên không?**

Không an toàn nếu chunk có nhiều accountId. Muốn key affinity phải nhóm/routing sao cho mọi event cùng key đi đúng lane và có cơ chế thứ tự xuyên chunk.

**7. Nếu worker lưu event vào inbox rồi trả reply thành công, job đã hoàn thành nghiệp vụ chưa?**

Chỉ nếu hợp đồng job quy định việc hoàn thành nghĩa là **ingest vào inbox**. Nếu cần projection đã áp dụng xong, phải có điều kiện đồng bộ/đối soát backlog trước khi kết luận.

**8. Vì sao nhiều worker có thể không giúp một hot account?**

Vì strict order của cùng account tạo critical path tuần tự. Thêm worker xử lý account khác không rút ngắn phần phụ thuộc của hot account.

**9. Remote partitioning có thể đơn giản hơn remote chunking trong tình huống nào?**

Khi nguồn có thể chia theo key/range ổn định và worker tự đọc thứ tự của phần mình, tránh phải route các chunk trộn nhiều key và giữ barrier xuyên chunk qua broker.

**10. Làm sao kiểm chứng ordering khi restart?**

Tạo test chunk đảo thứ tự, kill worker giữa/sau commit, phát lại duplicate, kiểm tra lastAppliedVersion, ledger/eventId, gap và trạng thái nghiệp vụ cuối theo nguồn đã chốt.

---

**Ghi nhớ:** Trong remote chunking, **thứ tự manager đọc và gửi không bảo đảm thứ tự worker commit**. Chỉ ép toàn bộ pipeline tuần tự khi nghiệp vụ thật sự cần global order; nếu cần per-key order, hãy thiết kế key affinity hoặc durable sequencer, kết hợp **sequence/version guard, idempotency, retry/restart và đối soát dữ liệu**. Broker FIFO là một thuộc tính vận chuyển, không phải bảo đảm tính đúng nghiệp vụ. Kiến trúc tốt là kiến trúc đạt **yêu cầu thứ tự với mức song song và chi phí vận hành hợp lý**.
