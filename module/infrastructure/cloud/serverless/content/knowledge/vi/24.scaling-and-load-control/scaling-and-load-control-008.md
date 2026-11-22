# Điều phối fan-out lớn mà không gây bão lời gọi

Trong chương **Mở rộng và điều tiết tải**, fan-out là cách một yêu cầu hoặc sự kiện được phân thành nhiều công việc con có thể chạy song song. Mẫu này hữu ích khi một đơn hàng cần cập nhật nhiều hệ thống, một file cần xử lý thành nhiều phần, hoặc một sự kiện cần được gửi tới nhiều consumer. Tuy nhiên, nếu phát hàng nghìn lời gọi cùng lúc mà không có giới hạn, hệ thống có thể tạo ra một đợt tải đột biến lên database, API bên ngoài, queue hoặc chính nền tảng serverless.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Điều phối fan-out cần tận dụng khả năng mở rộng của function nhưng vẫn kiểm soát concurrency, tốc độ gọi, retry, trạng thái và sức chịu tải của dependency.

## 1. Fan-out là gì?

Fan-out xảy ra khi một công việc cha tạo ra nhiều công việc con. Ví dụ, khi một khách hàng nhập một file gồm 20.000 bản ghi, hệ thống có thể chia file thành các phần nhỏ và xử lý song song. Một sự kiện OrderPlaced cũng có thể kích hoạt các công việc gửi email, cập nhật kho, tính điểm thưởng và tạo hóa đơn.

Fan-in là bước tổng hợp kết quả từ nhiều công việc con để xác định công việc cha đã hoàn tất hay chưa. Không phải mọi fan-out đều cần fan-in đồng bộ; nhiều hệ thống chỉ cần xử lý từng công việc con độc lập và lưu trạng thái kết quả.

~~~mermaid
flowchart TD
    P["Parent request / event"] --> D["Split into child tasks"]
    D --> Q["Durable queue or workflow"]
    Q --> W1["Worker A"]
    Q --> W2["Worker B"]
    Q --> W3["Worker C"]
    W1 --> R["Result store"]
    W2 --> R
    W3 --> R
    R --> A["Completion / fan-in"]
~~~

Fan-out có thể tăng throughput và giảm thời gian hoàn tất tổng thể nếu các công việc con độc lập. Nhưng số lượng công việc con không tự động đồng nghĩa với số lượng công việc nên chạy cùng lúc. Hệ thống phải tách tổng khối lượng công việc khỏi mức song song tối đa.

## 2. Vì sao fan-out không giới hạn gây call storm?

Giả sử một sự kiện tạo 5.000 công việc con. Nếu producer gửi tất cả ngay lập tức và mỗi worker tiếp tục gọi ba API downstream, một sự kiện có thể tạo ra 15.000 request gần như đồng thời. Nếu một trong các API chậm, request tồn tại lâu hơn, concurrency tăng và retry tiếp tục khuếch đại tải.

Một call storm thường có chuỗi nguyên nhân:

1. Một request cha tạo quá nhiều công việc con.
2. Nhiều function được kích hoạt cùng lúc.
3. Các function cùng gọi một database hoặc API có quota thấp hơn.
4. Dependency chậm hoặc throttling.
5. Worker timeout và retry.
6. Retry làm lượng request tăng thêm khi dependency đang quá tải.
7. Queue age, error rate và chi phí tăng nhanh.

Scale-out giúp tăng năng lực xử lý của worker, nhưng cũng có thể làm dependency bị quá tải nhanh hơn. Mục tiêu của điều phối tải là giữ lượng công việc đang chạy và tốc độ gọi trong giới hạn mà toàn bộ hệ thống có thể chịu được.

## 3. Phân biệt tổng số task, concurrency và request rate

Ba đại lượng cần được quản lý riêng:

| Đại lượng | Ý nghĩa | Ví dụ |
|---|---|---|
| Fan-out width | Số công việc con được tạo từ một công việc cha | Một file tạo 5.000 record task |
| Concurrency | Số công việc đang chạy cùng thời điểm | Tối đa 40 worker đang xử lý |
| Request rate | Số request được gửi trong một đơn vị thời gian | Tối đa 100 request/giây tới API |

Concurrency và request rate có liên hệ nhưng không thay thế nhau. Nếu mỗi request chỉ mất 5 ms, 20 worker đồng thời có thể tạo ra request rate rất cao. Nếu mỗi request mất 5 giây, cùng 20 worker tạo request rate thấp hơn.

Một quy tắc ước lượng theo định luật Little:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

Trong đó ArrivalRate là số công việc đến mỗi giây và AverageDuration là thời gian trung bình xử lý một công việc tính bằng giây.

Nếu worker nhận 50 task/giây và mỗi task mất trung bình 2 giây, concurrency ổn định xấp xỉ 100. Khi thời gian xử lý tăng lên 6 giây, cùng arrival rate có thể cần khoảng 300 slot đồng thời. Đây là lý do dependency chậm có thể làm concurrency tăng dù tốc độ tạo task không đổi.

## 4. Xác định giới hạn của dependency trước khi mở rộng

Trước khi chọn fan-out concurrency, cần hiểu sức chịu tải của các hệ thống phía sau:

- API bên ngoài có quota request/giây hoặc quota theo tenant không?
- Database chịu được bao nhiêu connection và query đồng thời?
- Queue hoặc stream có giới hạn throughput, partition hoặc shard nào?
- Dịch vụ có rate limit riêng cho từng credential hay account?
- Có giờ cao điểm hoặc batch khác dùng chung quota không?
- Khi bị throttling, dependency trả lỗi gì và có retry-after không?
- Một công việc con gọi bao nhiêu dependency và bao nhiêu lần?

Không dùng quota danh nghĩa làm concurrency cap mà không tính thời gian xử lý. Một API cho phép 100 request/giây không có nghĩa 100 worker là giới hạn phù hợp. Nếu request mất trung bình 2 giây, 100 request/giây có thể cần khoảng 200 request đang in-flight.

Nên dành headroom cho traffic tương tác, tác vụ vận hành và biến động latency. Một workload batch không nên chiếm hết capacity khiến API phục vụ người dùng thật bị chậm.

## 5. Kiến trúc fan-out an toàn

Một kiến trúc phổ biến có các thành phần:

- **Producer:** nhận công việc cha và tạo task con.
- **Queue hoặc event bus:** lưu và phân phối công việc bền vững.
- **Worker:** xử lý một task hoặc batch task.
- **Concurrency control:** giới hạn số worker đang hoạt động.
- **Rate control:** giới hạn tốc độ gọi dependency.
- **Result store:** lưu trạng thái và kết quả.
- **Retry/DLQ:** xử lý lỗi tạm thời và lỗi kéo dài.
- **Fan-in coordinator:** tổng hợp kết quả nếu nghiệp vụ cần barrier hoặc completion event.

~~~mermaid
flowchart LR
    API["HTTP / Event"] --> P["Fan-out producer"]
    P --> Q["Queue / Event bus"]
    Q --> W["Bounded workers"]
    W --> RL["Rate limiter"]
    RL --> DS["Downstream APIs / DB"]
    W --> RS["Result store"]
    W --> DLQ["DLQ for poison tasks"]
    RS --> C["Completion coordinator"]
    C --> DONE["Parent completed"]
~~~

Queue tạo khoảng đệm giữa tốc độ tạo task và tốc độ xử lý. Worker chỉ lấy công việc khi còn capacity. Nếu downstream chậm, queue age tăng lên nhưng producer không cần tạo thêm hàng nghìn kết nối đang chờ.

## 6. Chọn cơ chế điều phối phù hợp

| Cơ chế | Phù hợp khi | Điều cần quản lý |
|---|---|---|
| Gọi song song trực tiếp | Fan-out nhỏ, latency thấp và số task có giới hạn | In-flight limit, deadline và lỗi từng nhánh |
| SQS | Công việc độc lập, cần buffer và retry | Visibility timeout, batch, concurrency, DLQ |
| SNS/EventBridge | Phát sự kiện tới nhiều consumer | Retry target, DLQ, filtering và duplicate |
| Kinesis/DynamoDB Streams | Dòng dữ liệu có thứ tự theo partition/key | Shard, checkpoint, batch failure và lag |
| Step Functions Map | Cần orchestration, trạng thái và fan-in | MaxConcurrency, execution history và quota |
| Workflow riêng | Quy trình dài, nhiều bước và compensation | State persistence, timeout và recovery |

Không nên dùng một cơ chế duy nhất cho mọi kiểu fan-out. Nếu công việc con cần retry độc lập và có thể xử lý bất đồng bộ, queue thường là lựa chọn tự nhiên. Nếu cần biết mỗi nhánh đang ở bước nào và chỉ hoàn tất cha sau khi các nhánh kết thúc, workflow orchestration có thể phù hợp hơn.

## 7. Dùng queue làm bộ đệm

Queue giúp tách tốc độ producer khỏi tốc độ worker. Producer có thể gửi task nhanh, còn consumer lấy task theo khả năng xử lý.

Ví dụ luồng xử lý:

1. API nhận yêu cầu xử lý một file.
2. Producer ghi metadata job và tạo các task con.
3. Task được gửi vào SQS.
4. Lambda event source mapping đọc message theo batch.
5. Worker xử lý với concurrency được giới hạn.
6. Message thành công được xóa khỏi queue; message lỗi được retry theo visibility timeout và redrive policy.
7. Message vượt ngưỡng retry được chuyển vào DLQ để điều tra.

Queue không làm công việc biến mất; nó biến một đợt tải đột biến thành backlog có thể quan sát và xử lý dần. Cần đặt cảnh báo cho queue age và DLQ depth để biết khi tốc độ xử lý thấp hơn tốc độ tạo task.

### 7.1. Đặt giới hạn concurrency cho consumer

Với AWS Lambda và SQS, có thể điều chỉnh maximum concurrency của event source mapping khi tính năng đó phù hợp với cấu hình đang dùng. Reserved concurrency của function cũng có thể giới hạn tổng invocation. Khi một function có nhiều event source mapping, cần tính tổng giới hạn của các mapping và để lại headroom cần thiết.

Không đặt concurrency của mapping cao hơn khả năng downstream. Cũng không đặt reserved concurrency quá thấp đến mức các mapping tranh nhau toàn bộ capacity mà không có chủ đích.

Nếu dùng nhiều queue cho các workload có mức ưu tiên khác nhau, có thể tách worker function hoặc dùng concurrency riêng để batch workload không làm nghẽn tác vụ tương tác.

### 7.2. Visibility timeout và batch

Visibility timeout phải đủ dài để worker xử lý message và để lần giao lại không xảy ra khi lần xử lý trước vẫn còn chạy. Cấu hình không phù hợp có thể khiến cùng message được giao đồng thời cho nhiều worker.

Batch size lớn giảm overhead nhưng làm tăng lượng công việc bị ảnh hưởng khi batch lỗi. Với partial batch response, worker có thể báo riêng record thất bại để những record thành công không phải retry lại cùng batch; cần bật và kiểm thử đúng cơ chế của event source mapping.

## 8. Dùng Step Functions Map để giới hạn song song

AWS Step Functions Map state cho phép chạy một bước xử lý trên tập item. Có thể đặt MaxConcurrency để giới hạn số item chạy đồng thời. Distributed Map phù hợp với tập dữ liệu lớn hơn và có thể đọc item từ nguồn dữ liệu được hỗ trợ.

Ví dụ cấu hình khái niệm:

~~~json
{
  "ProcessItems": {
    "Type": "Map",
    "ItemsPath": "$.items",
    "MaxConcurrency": 25,
    "ItemProcessor": {
      "StartAt": "ProcessOne",
      "States": {
        "ProcessOne": {
          "Type": "Task",
          "Resource": "arn:aws:states:::lambda:invoke",
          "End": true
        }
      },
      "End": true
    }
  }
}
~~~

Đây là ví dụ rút gọn về cấu trúc Map, cần bổ sung Parameters/Arguments, ResultPath hoặc ResultSelector theo input/output thực tế. Với Distributed Map, cần cấu hình ProcessorConfig và nguồn item phù hợp. Giá trị 25 chỉ minh họa, không phải giới hạn mặc định hoặc con số tối ưu.

MaxConcurrency giới hạn số item của Map đang chạy. Nếu mỗi item tự tạo thêm 100 request song song, tổng request vẫn có thể vượt giới hạn downstream. Do đó, giới hạn ở orchestration cần phối hợp với rate control trong worker.

## 9. Fan-out qua event bus và tách biệt consumer

Khi một sự kiện cần nhiều hệ thống quan tâm, event bus hoặc pub/sub giúp producer không phải gọi trực tiếp từng consumer.

Ví dụ OrderPlaced có thể được phát một lần tới:

- Consumer cập nhật inventory.
- Consumer gửi thông báo.
- Consumer tạo invoice.
- Consumer cập nhật analytics.

Mỗi consumer nên có retry và dead-letter handling riêng để lỗi ở email không ngăn inventory được cập nhật. Với EventBridge hoặc SNS, cần cấu hình retry policy, target permissions và DLQ theo khả năng của dịch vụ.

Event bus phân tán sự kiện nhưng không tự giới hạn tốc độ xử lý của từng consumer. Nếu một target scale quá nhanh, vẫn cần concurrency cap, queue buffer hoặc rate limiter ở consumer.

## 10. Giới hạn fan-out ngay từ producer

Producer cần kiểm soát số lượng task được tạo và kích thước từng batch. Không nên đọc một file lớn vào memory rồi tạo hàng chục nghìn object, future hoặc HTTP request cùng lúc.

Các biện pháp:

- Chia input thành chunk có kích thước giới hạn.
- Stream dữ liệu từ object storage thay vì tải toàn bộ vào heap.
- Lưu metadata job trước khi phát task.
- Đặt giới hạn số task tối đa cho một parent job.
- Phân trang hoặc tạo task theo từng batch.
- Dùng queue/bulk API thay cho một request riêng cho từng item khi có thể.
- Chặn fan-out đệ quy vượt quá depth hoặc branching factor được phép.

Một giới hạn producer không thay thế giới hạn worker. Nó giúp tránh tạo ra lượng message hoặc state quá lớn trong thời gian ngắn và giữ chi phí orchestration trong dự kiến.

### 10.1. Ví dụ chia batch trong Java

~~~java
import java.util.List;

public final class TaskBatcher {
    private TaskBatcher() {
    }

    public static <T> void publishInBatches(
            List<T> items,
            int batchSize,
            BatchPublisher<T> publisher) throws Exception {

        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }

        for (int start = 0; start < items.size(); start += batchSize) {
            int end = Math.min(start + batchSize, items.size());
            List<T> batch = List.copyOf(items.subList(start, end));
            publisher.publish(batch);
        }
    }

    public interface BatchPublisher<T> {
        void publish(List<T> batch) throws Exception;
    }
}
~~~

Ví dụ này giới hạn số item trong mỗi lần publish nhưng vẫn nhận một List đã có sẵn trong memory. Với file rất lớn, nên đọc và tạo batch theo stream hoặc iterator thay vì materialize toàn bộ danh sách trước.

## 11. Giới hạn số lời gọi đồng thời trong Java

Nếu một worker phải gọi nhiều dependency, có thể dùng semaphore để giới hạn số lời gọi đang in-flight trong một process hoặc execution environment.

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeoutException;

public final class LocalCallGate {
    private final Semaphore permits;

    public LocalCallGate(int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.permits = new Semaphore(maxInFlight);
    }

    public <T> T call(
            Callable<T> operation,
            long waitMs) throws Exception {

        boolean acquired = permits.tryAcquire(waitMs, TimeUnit.MILLISECONDS);
        if (!acquired) {
            throw new TimeoutException("Local downstream capacity is full");
        }

        try {
            return operation.call();
        } finally {
            permits.release();
        }
    }
}
~~~

Semaphore này chỉ giới hạn số lời gọi trong một instance Java. Nếu Lambda scale thành 100 execution environment và mỗi environment cho phép 8 lời gọi, tổng cộng có thể có tới 800 lời gọi đồng thời. Vì vậy, local gate không phải global rate limiter.

Tạo LocalCallGate một lần trong object worker/service được tái sử dụng và inject vào các nhánh xử lý cần chia sẻ cùng giới hạn. Nếu tạo semaphore mới cho từng task, mỗi task sẽ có một bộ permits riêng và giới hạn dự kiến không còn tác dụng.

Cần kết hợp local limit với concurrency cap ở event source/orchestrator hoặc một rate limiter dùng chung. Nếu một downstream có quota theo account, giới hạn phải được tính trên toàn bộ worker cùng sử dụng account đó.

## 12. Rate limiting: giới hạn request theo thời gian

Rate limiting trả lời câu hỏi có thể gửi bao nhiêu request trong một giây hoặc một phút. Token bucket là một thuật toán phổ biến:

- Bucket có capacity tối đa.
- Token được bổ sung theo tốc độ xác định.
- Mỗi request cần tiêu thụ một hoặc nhiều token.
- Nếu không còn token, request phải chờ, bị từ chối hoặc được đưa lại queue.

Token bucket cho phép burst ngắn trong giới hạn capacity nhưng giữ tốc độ trung bình theo refill rate. Nếu API cho phép 100 request/giây nhưng chỉ chấp nhận burst 20, bucket có thể được cấu hình refill 100 token/giây và capacity 20, tùy semantics quota của provider.

Các cơ chế rate limit có thể nằm ở API Gateway, service mesh, API client, Redis hoặc một dịch vụ điều phối chung. Khi chạy nhiều Lambda environment, rate limiter cần có phạm vi chia sẻ phù hợp với quota thật.

Không dùng sleep trong mỗi Lambda để chờ token nếu queue có thể giữ công việc. Sleep giữ invocation và concurrency trong khi không tạo tiến triển. Với workload bất đồng bộ, để message ở queue và xử lý lại sau thường tiết kiệm tài nguyên hơn.

## 13. Backpressure và admission control

Backpressure là tín hiệu cho producer biết consumer hoặc dependency đang không theo kịp. Thay vì tiếp tục tăng lượng công việc, hệ thống có thể làm chậm producer, giảm concurrency hoặc từ chối phần tải vượt khả năng.

Một số cách áp dụng:

- Dựa vào queue age để giảm tốc độ tạo task.
- Dựa vào số message visible để điều chỉnh batch producer.
- Giảm worker concurrency khi downstream latency hoặc throttling tăng.
- Dùng quota theo tenant để một khách hàng không chiếm hết capacity.
- Trả HTTP 429 hoặc 503 khi API đồng bộ không nhận thêm tải.
- Dùng retry-after hoặc thông tin backoff khi caller có thể tuân thủ.
- Tạm dừng consumer hoặc giảm poll rate trong sự cố có kiểm soát.

Admission control nên được đặt trước điểm hệ thống tiêu tốn tài nguyên đắt tiền. Nếu function đã tạo hàng nghìn child event rồi mới phát hiện quota hết, queue đã nhận thêm backlog và chi phí lưu trữ/điều phối vẫn phát sinh.

## 14. Retry có thể khuếch đại call storm

Retry giúp phục hồi lỗi tạm thời nhưng có thể làm hệ thống quá tải hơn nếu mọi worker retry cùng lúc.

Ví dụ, downstream bắt đầu throttling 429. Nếu 1.000 worker đều retry sau đúng một giây, chúng có thể tạo một đợt 1.000 request mới đúng thời điểm quota chưa phục hồi.

Nên dùng:

- Exponential backoff.
- Random jitter để phân tán thời điểm retry.
- Retry budget hoặc giới hạn số lần thử.
- Tôn trọng Retry-After nếu dependency cung cấp.
- Phân loại lỗi transient và permanent.
- DLQ cho task không thể xử lý sau số lần thử.
- Circuit breaker hoặc load shedding khi dependency đang mất khả năng phục vụ.

Không retry validation error, lỗi dữ liệu vĩnh viễn hoặc AccessDenied như thể đó là lỗi mạng. Retry cần được đặt ở một số tầng có chủ đích; nếu SDK, worker và caller đều retry độc lập, số lần gọi thực tế có thể nhân lên.

### 14.1. Exponential backoff có jitter

Một công thức minh họa:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Jitter giúp nhiều worker không thức dậy cùng một thời điểm. Cần giới hạn maxDelay và tổng retry duration theo deadline của workflow.

Với message queue, thay vì tự sleep trong handler, có thể để message được retry theo visibility timeout hoặc retry policy của nền tảng. Cần tránh tạo vòng lặp retry quá nhanh làm queue liên tục giao lại message đang lỗi.

## 15. Circuit breaker và load shedding

Circuit breaker theo dõi lỗi của dependency và tạm ngừng gọi khi tỷ lệ lỗi vượt ngưỡng. Các trạng thái thường gặp:

- **Closed:** cho phép request đi qua và theo dõi lỗi.
- **Open:** chặn request trong một khoảng thời gian để dependency phục hồi.
- **Half-open:** cho một số request thử nghiệm để xác định dependency đã phục hồi chưa.

Load shedding loại bỏ hoặc từ chối công việc vượt quá capacity thay vì để tất cả request chờ đến timeout. Có thể ưu tiên tác vụ tương tác, bỏ hoặc trì hoãn tác vụ batch ít khẩn cấp.

Trong serverless, state của circuit breaker đặt trong memory chỉ có hiệu lực trong một execution environment. Khi có nhiều environment, mỗi instance có thể có trạng thái khác nhau. Nếu cần circuit breaker hoặc quota toàn cục, dùng một cơ chế chia sẻ hoặc gateway/service quản lý chung; đồng thời tránh tạo dependency mới quá mong manh chỉ để điều khiển tải.

## 16. Idempotency và xử lý trùng lặp

Fan-out qua queue và event bus thường có semantics giao ít nhất một lần. Một child task có thể được giao lại khi worker timeout sau khi đã ghi kết quả nhưng trước khi ACK message.

Mỗi task con cần một idempotency key ổn định. Ví dụ:

~~~java
public record WorkItem(
        String parentJobId,
        String itemId,
        int operationVersion) {

    public String idempotencyKey() {
        return parentJobId + ":" + itemId + ":" + operationVersion;
    }
}
~~~

Key phải đại diện cho một thao tác nghiệp vụ duy nhất. Không tạo key mới theo mỗi lần retry, vì như vậy lần giao lại sẽ bị xem như công việc mới.

Ở storage, dùng conditional write hoặc transaction để ghi nhận trạng thái task. Chỉ đánh dấu hoàn tất sau khi side effect được thực hiện hoặc có cơ chế outbox/transaction phù hợp. Idempotency store cần TTL phù hợp với khoảng thời gian retry/redrive và khả năng phát lại event.

## 17. Fan-in và tổng hợp kết quả bền vững

Nếu parent job phải đợi tất cả child task, không nên giữ một Lambda invocation mở trong khi hàng nghìn task chạy. Invocation có thể timeout, tốn concurrency và không giữ được trạng thái bền vững.

Có thể lưu trạng thái tổng hợp:

- Parent job ID.
- Tổng số task đã tạo.
- Số task thành công.
- Số task thất bại.
- Số task đang chờ hoặc đang chạy.
- Thời điểm bắt đầu/kết thúc.
- Trạng thái hoàn tất hoặc cần can thiệp.

Khi child task hoàn tất, worker cập nhật kết quả và tăng bộ đếm theo thao tác atomic/conditional. Việc chuyển trạng thái child và ghi nhận completion cần được thực hiện trong transaction nếu storage hỗ trợ, hoặc qua outbox/consumer idempotent để không xảy ra trường hợp child đã hoàn tất nhưng aggregate chưa được tăng. Khi mọi task đã ở trạng thái kết thúc, coordinator phát sự kiện ParentCompleted hoặc ParentFailed.

Cần chống cập nhật trùng lặp: cùng child completion event không được tăng bộ đếm nhiều lần. Có thể dùng trạng thái child và conditional transition từ RUNNING sang SUCCEEDED/FAILED trước khi cập nhật aggregate.

Với workflow phức tạp, Step Functions hoặc workflow engine có thể giữ trạng thái và xử lý retry/fan-in thay cho việc tự xây một coordinator.

## 18. Kiểm soát fan-out đệ quy và fairness

Một worker có thể phát thêm event, event đó lại tạo fan-out mới. Nếu không kiểm soát, hệ thống có thể tạo cây công việc tăng theo cấp số nhân.

Ví dụ, mỗi task tạo 10 task con và độ sâu là 4, tổng số task có thể lên đến hàng nghìn chỉ từ một root. Cần xác định:

- Maximum fan-out width.
- Maximum workflow depth.
- Loại event nào được phép tạo child event.
- Idempotency key của mỗi cấp.
- Budget tổng số task cho một parent job.
- Cơ chế phát hiện vòng lặp event.
- Tenant hoặc customer quota.

Fairness giúp một tenant không chiếm hết worker capacity. Có thể dùng queue riêng theo tier, weighted scheduling, concurrency theo tenant hoặc rate limit theo API key. Chỉ dùng một global queue có thể khiến batch lớn của một tenant làm chậm tất cả tenant khác.

## 19. Payload, batch size và dữ liệu lớn

Không nên truyền một payload rất lớn qua mọi tầng fan-out. Message nên mang định danh và tham chiếu đến dữ liệu bền vững.

Ví dụ message:

~~~json
{
  "parentJobId": "job-2026-001",
  "itemId": "part-00042",
  "source": {
    "bucket": "processing-input",
    "key": "jobs/job-2026-001/input.jsonl"
  },
  "operationVersion": 3
}
~~~

Worker đọc đúng phần dữ liệu được chỉ định từ object storage. Cách này giảm kích thước message và tránh sao chép cùng payload qua nhiều lần retry.

Batch size lớn giảm overhead invocation nhưng tăng memory và thời gian xử lý mỗi batch. Batch quá nhỏ làm tăng số invocation và chi phí điều phối. Cần benchmark theo payload size, failure rate và khả năng partial batch response.

Nếu xử lý record độc lập, batch worker nên lưu kết quả từng record hoặc dùng partial batch failure để tránh một record lỗi làm mất tiến độ của các record thành công.

## 20. Quan sát một workflow fan-out

Mỗi parent job nên có correlation ID; mỗi child task nên có child ID và idempotency key. Log và trace cần liên kết được parent-child để điều tra một nhánh lỗi.

Các metric nên theo dõi:

- Fan-out width trung bình và lớn nhất.
- Tổng task được tạo theo parent job.
- Active concurrency và request rate.
- Queue depth và age of oldest message.
- Downstream latency, 429/5xx và connection count.
- Retry count, duplicate count và DLQ depth.
- Fan-in completion time và số job chưa hoàn tất.
- Cost trên mỗi parent job hoặc mỗi item thành công.

Tránh dùng parent ID, child ID hoặc customer ID làm metric dimension nếu cardinality cao. Có thể ghi các ID trong log/trace có kiểm soát, còn metric dùng dimension hữu hạn như function, environment, operation type và result.

Một dashboard chỉ hiển thị Lambda Duration có thể bỏ lỡ queue backlog và fan-in bị kẹt. Cần theo dõi toàn bộ đường đi từ producer đến kết quả cuối.

## 21. Bảo vệ hệ thống bằng quota và ưu tiên

Không phải mọi task đều có độ ưu tiên như nhau. Một hệ thống có thể phân loại:

- Interactive: người dùng đang chờ phản hồi.
- High priority async: nghiệp vụ cần hoàn tất nhanh nhưng không giữ HTTP connection.
- Batch: khối lượng lớn, có thể trì hoãn.
- Background maintenance: có thể chạy khi còn capacity.

Mỗi loại có thể dùng queue hoặc concurrency allocation riêng. Dành capacity cho interactive traffic và đặt quota cho batch. Nếu tất cả loại task dùng chung một concurrency pool, một đợt import lớn có thể làm API xử lý đơn hàng bị throttling.

Quota cần có owner, giới hạn, metric sử dụng và quy trình thay đổi. Không chỉ dựa vào một giá trị cấu hình cố định; hãy theo dõi xu hướng để biết khi nào cần tăng capacity hoặc giảm fan-out.

## 22. Chi phí của fan-out

Chi phí tăng theo số lượng task, invocation, thời gian chạy, message, state transition, data transfer và log.

Các nguồn chi phí thường gặp:

- Lambda invocation và GB-seconds.
- SQS request và thời gian lưu message.
- EventBridge event/target delivery.
- Step Functions state transition hoặc workflow execution.
- Database read/write cho idempotency và result store.
- Data transfer và object storage.
- Retry, duplicate processing và DLQ.
- Log/trace ingestion.

Một parent job tạo 100.000 child task có thể phát sinh chi phí điều phối đáng kể ngay cả khi mỗi task rất nhỏ. Batching có thể giảm overhead nhưng cần cân bằng failure isolation và latency.

Nên đo cost trên mỗi parent job, mỗi child task hoàn tất và mỗi đơn vị nghiệp vụ. Một cấu hình worker nhanh hơn nhưng retry nhiều có thể tốn hơn cấu hình chậm hơn và ổn định.

## 23. Ví dụ điều phối fan-out cho xử lý file

Một quy trình xử lý file lớn có thể thiết kế như sau:

1. API tạo ParentJob ở trạng thái ACCEPTED.
2. Producer đọc metadata file và xác định số partition.
3. Producer phát task theo batch vào queue.
4. SQS event source mapping giới hạn worker concurrency.
5. Worker lấy một task, đọc partition và xử lý với rate limit.
6. Worker lưu kết quả bằng idempotency key.
7. Worker phát ChildCompleted sau khi kết quả bền vững.
8. Coordinator cập nhật số lượng task đã hoàn tất.
9. Khi tất cả partition kết thúc, coordinator đánh dấu ParentJob COMPLETED.
10. Task lỗi quá số lần thử chuyển vào DLQ và parent job được đánh dấu NEEDS_ATTENTION hoặc FAILED theo policy.

Nếu file có hàng triệu bản ghi, không cần tạo một message cho mỗi record. Có thể chia thành partition hoặc chunk có kích thước phù hợp, rồi worker xử lý từng chunk. Kích thước chunk cần được chọn qua benchmark memory, duration và retry cost.

## 24. Những lỗi thường gặp

**Tạo mọi child task cùng lúc:** Gây burst lên queue, orchestration và downstream. Chia batch, giới hạn producer và dùng buffer.

**Chỉ giới hạn concurrency:** Request ngắn vẫn có thể tạo RPS quá cao. Quản lý thêm rate limit.

**Dùng semaphore cục bộ làm global quota:** Mỗi execution environment có semaphore riêng. Dùng event source cap hoặc rate limiter dùng chung.

**Để worker retry ngay lập tức:** Nhiều worker đồng bộ retry và tiếp tục gây throttling. Dùng backoff, jitter và retry budget.

**Giữ parent invocation chờ mọi child:** Tốn concurrency và có nguy cơ timeout. Lưu trạng thái fan-in bền vững hoặc dùng workflow engine.

**Không idempotent:** Message giao lại tạo side effect trùng. Dùng key ổn định và conditional state transition.

**Batch quá lớn:** Một record lỗi có thể làm retry nhiều record đã thành công. Dùng partial batch response và batch size dựa trên số đo.

**Không giới hạn fan-out đệ quy:** Một event có thể tạo ra lượng task tăng theo cấp số nhân. Giới hạn depth, width và tổng budget.

**Dùng một queue cho mọi loại tải:** Batch có thể làm nghẽn interactive work. Tách queue và quota theo ưu tiên.

**Không quan sát queue age:** Worker có vẻ khỏe nhưng backlog tăng liên tục. Theo dõi age, depth và throughput.

**Không xử lý DLQ:** Task lỗi bị bỏ quên hoặc redrive hàng loạt gây bão lần nữa. Điều tra, sửa nguyên nhân và redrive có kiểm soát.

**Truyền payload lớn qua message:** Tăng chi phí và nguy cơ vượt giới hạn payload. Truyền object reference và partition metadata.

## 25. Checklist trước khi phát hành fan-out lớn

- [ ] Đã ước lượng tổng fan-out width và branching factor.
- [ ] Có giới hạn số child task cho mỗi parent job.
- [ ] Có giới hạn fan-out depth và ngăn event loop.
- [ ] Đã xác định concurrency tối đa của worker.
- [ ] Đã xác định request rate tối đa cho từng downstream.
- [ ] Local semaphore không bị nhầm là global rate limiter.
- [ ] Queue hoặc workflow buffer tách tốc độ producer và consumer.
- [ ] Event source mapping và function concurrency được phối hợp.
- [ ] Batch size phù hợp với memory, duration và partial failure.
- [ ] Visibility timeout, retry, DLQ và redrive policy được kiểm thử.
- [ ] Retry có backoff, jitter, budget và phân loại lỗi.
- [ ] Child task có idempotency key ổn định.
- [ ] Fan-in state được lưu bền vững và cập nhật chống trùng.
- [ ] Payload lớn được lưu ngoài message và truyền bằng reference.
- [ ] Có quota/fairness theo tenant hoặc loại workload.
- [ ] Có metric queue age, concurrency, RPS, throttles và DLQ.
- [ ] Có kiểm thử tải và downstream failure ở môi trường riêng.
- [ ] Có ước lượng cost trên mỗi parent job và mỗi task thành công.
- [ ] Có quy trình redrive DLQ theo batch có kiểm soát.
- [ ] Có phương án giảm tải, tạm dừng hoặc rollback khi dependency quá tải.

## Kết luận

Fan-out giúp tận dụng khả năng xử lý song song của serverless, nhưng cần giới hạn tổng task, concurrency và request rate theo các lớp riêng. Queue hoặc workflow engine tạo buffer và lưu trạng thái; event source concurrency cap bảo vệ worker; rate limiter bảo vệ quota downstream; backpressure, retry có jitter và circuit breaker giúp hệ thống phản ứng khi dependency chậm.

Với Java, semaphore có thể giới hạn lời gọi trong một execution environment nhưng không tạo quota toàn cục khi function scale-out. Task con cần idempotency key ổn định, fan-in cần trạng thái bền vững và metric phải theo dõi từ producer đến kết quả cuối. Điều phối tốt cho phép xử lý khối lượng lớn mà vẫn giữ được giới hạn tải, độ tin cậy và chi phí có thể dự đoán.

