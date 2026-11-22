# Delivery attempt trong retry topic

Trong hệ thống Spring Kafka dùng **non-blocking retry**, record lỗi được phát sang một retry topic thay vì giữ consumer của topic chính chờ hết backoff. Record ấy tiếp tục được tiêu thụ ở những lần thử kế tiếp; nếu mọi lần thử đều thất bại, nó có thể được chuyển sang dead-letter topic (DLT). Khi một sự kiện đã đi qua nhiều topic, đội vận hành cần trả lời: **đang ở lần thử thứ mấy, còn bao nhiêu lần thử và bộ đếm đó có ý nghĩa gì?**

Spring Kafka có metadata dành riêng cho retry-topic infrastructure. Header tiêu biểu là `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS`, giúp thể hiện số lần thử được hệ thống non-blocking retry theo dõi. Nó cần được phân biệt với `KafkaHeaders.DELIVERY_ATTEMPT` của cơ chế delivery attempt ở listener container và blocking retry. Hai header này không phải cùng một bộ đếm và không nên cộng chúng một cách tùy tiện.

Bài học tập trung vào cách non-blocking retry tạo và truyền attempt header, cách đọc header an toàn, cách hiểu số lần thử trong `@RetryableTopic`, tác động của việc kết hợp blocking và non-blocking retry, cũng như cách sử dụng metadata để điều tra lỗi và vận hành replay.

## 1. Ôn lại luồng non-blocking retry

Ở mô hình blocking retry, listener container có thể thử lại record lỗi ngay trong luồng xử lý của nó, kèm backoff. Khi backoff dài, consumer có thể giữ partition và làm các record sau bị chậm.

Với **non-blocking retry**, Spring Kafka cấu hình một chuỗi topic và listener container liên quan:

1. Consumer nhận record từ topic chính.
2. Listener ném exception được phân loại là retryable.
3. Infrastructure publish record vào retry topic với metadata cần thiết.
4. Consumer chuyên xử lý retry topic nhận record sau khoảng delay dự kiến.
5. Nếu xử lý vẫn thất bại và còn lượt thử, record được chuyển sang lần retry tiếp theo.
6. Khi không còn lượt thử hoặc exception không retryable, record được chuyển tới DLT theo cấu hình.

Sơ đồ:

~~~text
orders.events (topic chính)
       |
       | attempt ban đầu thất bại
       v
orders.events-retry-... (retry topic, delay ngắn)
       |
       | vẫn thất bại
       v
orders.events-retry-... (retry topic, delay dài hơn)
       |
       | vẫn thất bại / hết retry
       v
orders.events-dlt (DLT, tên minh họa)
~~~

Tên topic thực tế do retry-topic configuration và suffix strategy quyết định. Không nên viết code dựa trên một tên retry topic cố định nếu tên ấy có thể thay đổi khi điều chỉnh delay, reuse topic hoặc cấu hình framework.

Điểm cần nhớ: **mỗi bước non-blocking retry là một lần publish/consume qua Kafka topic**, không phải chỉ gọi lại listener ngay trong cùng một poll. Vì vậy, metadata attempt được chuyển cùng record qua các lần publish.

## 2. Hai header attempt dễ bị nhầm

Spring Kafka có hai ngữ cảnh phổ biến để nói đến “attempt”:

| Header | Phạm vi chính | Cách hiểu |
|---|---|---|
| `KafkaHeaders.DELIVERY_ATTEMPT` | Lần giao record theo listener container và error handler hỗ trợ delivery attempt | Số lần giao trong chuỗi xử lý của container tương ứng |
| `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` | Chuỗi xử lý của non-blocking retry infrastructure | Thông tin lần thử của record khi đi qua retry topic |

### 2.1. KafkaHeaders.DELIVERY_ATTEMPT

Header này gắn với cơ chế delivery attempt của container. Với cấu hình tương thích, listener có thể đọc số lần record được giao lại do blocking error handling. Nó được bật qua thuộc tính `ContainerProperties.setDeliveryAttemptHeader(true)` và cần error handler có khả năng cung cấp số lần giao.

Giá trị thông thường bắt đầu từ 1 cho lần giao đầu tiên trong chuỗi xử lý tương ứng. Tuy nhiên, khi restart hoặc rebalance, không được giả định state đếm của container tồn tại xuyên suốt mọi sự cố.

### 2.2. RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS

Header này do retry-topic infrastructure quản lý khi record được đưa qua các lần non-blocking retry. Nó giúp xác định lần thử mà luồng retry topic đang theo dõi và được truyền như metadata trên record được republish.

Không nên giả định header non-blocking luôn có mặt trên record của **topic chính trước khi có lần retry đầu tiên**. Ở lần tiêu thụ ban đầu, record có thể chưa mang header do retry-topic infrastructure bổ sung. Trên retry topic, header được dùng để theo dõi số lần thử; giá trị cụ thể phải được đối chiếu với phiên bản Spring Kafka và chính sách đang chạy.

Để code chạy ổn định, hãy coi “header không có” là trạng thái hợp lệ, thay vì tự khẳng định mọi record đều mang attempt = 1 ở tầng Kafka headers.

### 2.3. Vì sao không cộng hai giá trị?

Ví dụ một listener trên retry topic cũng được bật blocking retry. Khi record của retry topic được thử lại nhiều lần ngay trong cùng container, `KafkaHeaders.DELIVERY_ATTEMPT` có thể tăng qua từng lần giao nội bộ. Trong khi đó, `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` phản ánh bước non-blocking retry tương ứng và không nhất thiết tăng theo từng lần blocking retry đó.

Nếu lấy hai số cộng lại, dashboard có thể đếm trùng một số lần xử lý. Không có công thức tổng quát chỉ dùng hai header này để tính chính xác số lần gọi nghiệp vụ từ lúc event được tạo.

## 3. Cấu hình @RetryableTopic và số lần thử

Một cách khai báo non-blocking retry là dùng `@RetryableTopic` cho một listener:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 8_000),
        include = {
                InventoryTemporaryException.class,
                RemoteServiceUnavailableException.class
        },
        exclude = {
                InvalidOrderEventException.class
        })
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void handle(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

Trong `@RetryableTopic`, `attempts = "4"` được hiểu là **tổng số lần thử**, bao gồm lần xử lý ban đầu và những lần non-blocking retry. Theo cấu hình minh họa, nếu lỗi thuộc nhóm được retry và vẫn thất bại, ứng dụng có thể có một lần ở topic chính và tối đa ba lần non-blocking retry trước khi chuyển sang recovery/DLT.

Điều này **khác** với tham số `maxAttempts` hoặc `maxRetries` của một số thư viện khác. Không được hiểu `attempts = "4"` là “bốn lần retry cộng với lần ban đầu” nếu đang nói về semantics của `@RetryableTopic`.

### 3.1. Bảng diễn tiến minh họa

Giả sử mỗi lần xử lý đều thất bại và chính sách cho phép bốn lần thử tổng cộng:

| Lần xử lý theo luồng non-blocking | Nơi xử lý | Hành động nếu tiếp tục thất bại |
|---:|---|---|
| 1 | Topic chính | Publish sang retry topic |
| 2 | Retry topic | Publish sang retry topic tiếp theo hoặc cùng topic theo chiến lược |
| 3 | Retry topic | Tiếp tục retry nếu còn attempt |
| 4 | Retry topic | Hết lượt; recovery/DLT theo cấu hình |

Các mức delay thực tế phụ thuộc backoff, chiến lược tạo/reuse topic, thời gian broker và consumer có thể poll. Không coi thời điểm xử lý lại là đúng tuyệt đối từng mili giây.

Header của retry topic phục vụ định danh **lần thử trong chuỗi**; nó không phải đồng hồ đếm thời gian delay. Muốn biết record đã chờ bao lâu, cần kết hợp timestamp và các header thời gian mà retry infrastructure quản lý.

### 3.2. Chỉ retry exception có khả năng phục hồi

Nếu record sai schema hoặc bị từ chối vĩnh viễn bởi nghiệp vụ, thêm nhiều attempt không làm nó hợp lệ. Nhóm `exclude` hoặc cấu hình exception classification giúp bỏ qua các retry không có ích và chuyển sang recovery đúng lúc.

Với lỗi tạm thời như timeout, HTTP 503 hoặc deadlock, retry có giới hạn và backoff phù hợp có thể giúp hệ thống phục hồi. Nhưng mỗi lần thử đều tiêu thụ tài nguyên downstream, nên giới hạn tổng số attempt cần dựa trên SLA và khả năng của dependency.

## 4. Đọc retry-topic attempt trong listener

Có hai cách thường dùng:

- Đọc header từ `ConsumerRecord.headers()` để kiểm tra trực tiếp bytes.
- Dùng tham số `@Header` và để cơ chế chuyển đổi header của Spring giải mã nếu phiên bản/cấu hình hỗ trợ.

Với luồng cần xử lý an toàn cả khi header vắng mặt, cách đọc trực tiếp giúp phân biệt rõ dữ liệu thực tế.

### 4.1. Đọc từ ConsumerRecord

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing")
public void handle(ConsumerRecord<String, OrderEvent> record) {

    Header header = record.headers()
            .lastHeader(RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS);

    Integer retryTopicAttempt = null;
    if (header != null
            && header.value() != null
            && header.value().length == Integer.BYTES) {
        retryTopicAttempt =
                ByteBuffer.wrap(header.value()).getInt();
    }

    log.info("topic={}, partition={}, offset={}, retryTopicAttempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            retryTopicAttempt == null
                    ? "absent"
                    : retryTopicAttempt);

    orderService.processIdempotently(record.value());
}
~~~

Ví dụ minh họa cách đọc một số nguyên 4 byte theo biểu diễn header của retry-topic infrastructure trong các phiên bản hỗ trợ. `ByteBuffer` sử dụng big-endian theo mặc định. Hãy xác nhận encoding của header trong phiên bản Spring Kafka đang chạy trước khi dùng cho logic phụ thuộc mạnh vào giá trị.

**Quan trọng:** ví dụ `@KafkaListener(topics = "orders.events")` trên chỉ thể hiện cách truy cập header của một record do listener nhận. Khi dùng `@RetryableTopic`, framework sẽ cấu hình các endpoint cho topic chính và retry topic theo chính sách, nên listener thực tế có thể được gọi ở nhiều topic. Không phải tự viết một listener thứ hai cho mọi retry topic chỉ để đọc header.

### 4.2. Đọc với @Header

Trong ứng dụng có chuyển đổi header phù hợp, có thể yêu cầu giá trị bằng tham số:

~~~java
@RetryableTopic(attempts = "4")
@KafkaListener(topics = "orders.events", groupId = "billing")
public void handle(
        OrderEvent event,
        @Header(
                name = RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS,
                required = false)
        Integer retryTopicAttempt) {

    log.debug("Non-blocking attempt header={}", retryTopicAttempt);
    orderService.processIdempotently(event);
}
~~~

`required = false` giúp listener không lỗi khi header chưa được gắn ở lần tiêu thụ đầu tiên. Kiểu chuyển đổi bytes thành `Integer` phụ thuộc hạ tầng Spring Messaging và phiên bản đang sử dụng; nếu không có conversion phù hợp, hãy nhận `byte[]` rồi giải mã có kiểm tra hoặc dùng `ConsumerRecord`.

Không đặt `required = true` chỉ vì muốn xuất metric. Một header quan sát bị thiếu không nên tạo thêm exception rồi kích hoạt vòng retry ngoài ý muốn.

### 4.3. Vì sao dùng lastHeader?

Kafka headers cho phép **nhiều header cùng tên** trên một record. Khi record được republish qua các retry topic, một số header có thể được bổ sung hoặc cập nhật. Phương thức `lastHeader(name)` lấy giá trị cuối cùng của tên header đó.

Trong Spring Kafka, các phiên bản mới có cơ chế kiểm soát việc giữ lại nhiều bản của retry headers nhằm tránh header tăng không giới hạn. Tuy vậy, code đọc trực tiếp nên thống nhất quy ước lấy bản cuối cùng khi muốn dùng giá trị hiện hành. Đừng giả định danh sách header không bao giờ có giá trị trùng tên trong mọi deployment.

## 5. Trường hợp header vắng mặt

Không thấy `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` không phải lúc nào cũng là lỗi. Có những tình huống hợp lệ:

1. Record được tiêu thụ lần đầu ở topic chính, chưa được republish bởi retry-topic infrastructure.
2. Record được phát trực tiếp vào retry topic bằng công cụ vận hành nhưng không có header chuẩn.
3. Hệ thống dùng blocking retry thay vì non-blocking retry.
4. Listener không nằm trong topology do `@RetryableTopic` hoặc retry-topic configuration tạo.
5. Pipeline custom producer đã thay đổi hoặc bỏ header khi republish.

Vì vậy, khi cần hiển thị attempt trên dashboard, nên phân biệt các trạng thái:

- `absent`: record không có retry-topic attempt header.
- `present`: đã đọc được giá trị số nguyên hợp lệ.
- `invalid`: header có bytes không đúng định dạng mong đợi.

Nếu muốn trình bày “lần xử lý đầu tiên” theo quy ước ứng dụng, có thể map `absent` tại topic chính sang nhãn `initial`. Tuy nhiên, cần giữ nguyên giá trị raw hoặc trạng thái thiếu header trong log điều tra để tránh diễn giải sai lịch sử.

## 6. Liên hệ với blocking retry trong retry-topic topology

Spring Kafka có thể kết hợp blocking retry và non-blocking retry cho các loại exception khác nhau. Ví dụ, một số lỗi mạng được thử lại nhanh vài lần trong cùng container; nếu vẫn thất bại, record mới được publish sang retry topic để chờ lâu hơn.

~~~text
Topic chính
    |
    +-- blocking attempt 1
    +-- blocking attempt 2
    +-- blocking attempt 3
    |
    v
Retry topic (bước non-blocking tiếp theo)
    |
    +-- blocking attempt 1
    +-- blocking attempt 2
    |
    v
Retry topic khác hoặc DLT
~~~

Trong ví dụ này:

- `KafkaHeaders.DELIVERY_ATTEMPT` phản ánh lần giao của container tại một bước xử lý có blocking retry.
- `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` phản ánh thông tin attempt theo chuỗi non-blocking retry.
- Một lần chuyển sang retry topic mới không đồng nghĩa chỉ có đúng một lần gọi nghiệp vụ trong suốt bước trước đó.

Để giới hạn **tổng số lần gọi downstream**, phải tính cả HTTP client retry, retry trong service, blocking error-handler retry và non-blocking retry topic. Không dựa vào một header duy nhất.

### 6.1. Tình huống có thể gây hiểu nhầm

Giả sử topic chính gọi nghiệp vụ 3 lần do blocking retry, sau đó record sang retry topic và ở đó tiếp tục gọi 2 lần. Người vận hành nhìn thấy retry-topic attempt cho biết đây là bước retry đầu tiên của non-blocking topology. Điều đó không chứng minh service chỉ được gọi hai lần tổng cộng.

Nếu hợp đồng nghiệp vụ giới hạn tối đa 5 lần gửi yêu cầu thanh toán, cần đếm attempt **bền vững** ở tầng nghiệp vụ (hoặc dùng workflow có trạng thái), không chỉ đọc Kafka retry headers.

## 7. Retry attempt và deadline của backoff

Trong non-blocking retry, record được chuyển đến retry topic và chỉ nên được xử lý khi đến thời điểm được phép theo backoff. Spring Kafka có header thời gian cho retry infrastructure, ví dụ metadata về thời điểm record được phép xử lý.

Attempt và timestamp trả lời hai câu hỏi khác nhau:

- **Attempt:** Record đang ở lần thử nào của chuỗi retry?
- **Next processing time:** Khi nào record đủ điều kiện để được listener xử lý?

Đừng tính thời gian chờ dựa trên công thức cứng chỉ từ attempt. Backoff có thể là fixed, exponential, random, được giới hạn giá trị tối đa hoặc có chính sách reuse retry topic. Ngoài ra, consumer scheduling, broker latency và tải hệ thống làm thời điểm thực thi thực tế có thể muộn hơn lịch.

Nếu cần kiểm tra “retry topic có đang xử lý đúng delay không?”, hãy ghi lại thời điểm publish vào retry topic, thời gian cho phép xử lý và thời điểm listener thực sự bắt đầu. Số attempt không đủ để kết luận lỗi scheduling.

## 8. DLT và metadata sau khi hết attempt

Khi tất cả lượt thử đã dùng hết hoặc một exception được phân loại non-retryable, infrastructure có thể chuyển record sang DLT. DLT thường giữ các header hữu ích cho việc phân tích, bao gồm exception metadata và thông tin nguồn theo cấu hình.

Tại DLT, người vận hành thường cần:

- Event id hoặc idempotency key ổn định.
- Topic, partition và offset của nguồn.
- Topic retry gần nhất.
- Exception class và nguyên nhân.
- Thông tin attempt của retry-topic infrastructure (nếu có).
- Thời điểm xuất hiện lỗi và thời điểm vào DLT.
- Schema/version hoặc metadata đủ cho replay.

### 8.1. Ví dụ DltHandler đọc attempt

~~~java
@DltHandler
public void handleDlt(
        ConsumerRecord<String, OrderEvent> record) {

    Header h = record.headers()
            .lastHeader(RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS);

    Integer attempt = null;
    if (h != null && h.value() != null
            && h.value().length == Integer.BYTES) {
        attempt = ByteBuffer.wrap(h.value()).getInt();
    }

    log.error(
            "DLT record: topic={}, partition={}, offset={}, " +
            "retryTopicAttempt={}",
            record.topic(), record.partition(), record.offset(),
            attempt == null ? "unknown" : attempt);
}
~~~

Đoạn code minh họa việc quan sát header tại DLT, không thay thế chính sách DLT. `@DltHandler` cần được dùng đúng vị trí trong topology `@RetryableTopic` và yêu cầu cấu hình serializer, converter, error handling phù hợp. Nếu môi trường không chuyển được payload thành `OrderEvent`, có thể cần cơ chế nhận raw bytes hoặc xử lý lỗi deserialization phù hợp.

### 8.2. Không coi attempt cao là lý do tự động xóa record

DLT là nơi lưu record phục vụ điều tra, đối soát hoặc replay. Số attempt giúp đánh giá record đã trải qua những bước nào nhưng không nói record an toàn để bỏ qua. Một exception validation ở lần đầu có thể nguy hiểm hơn nhiều so với timeout đã thử ba lần.

Chỉ replay sau khi đã giải quyết nguyên nhân, thử trên dữ liệu đại diện và có quy trình chống side effect trùng.

## 9. Restart, rebalance và khả năng giữ lịch sử attempt

Một lợi ích của non-blocking retry là record được republish vào Kafka retry topic, nên các header đi cùng record có thể sống qua restart consumer. Tuy nhiên, không nên hiểu điều này là Kafka duy trì một bộ đếm attempt lịch sử vĩnh viễn:

- Header có thể bị thay đổi bởi custom producer, serializer hoặc topology ngoài Spring Kafka.
- Một record được phát lại thủ công về topic chính có thể bắt đầu một chuỗi non-blocking retry mới.
- Blocking retry count ở một container vẫn có thể reset sau restart/rebalance.
- Khi thay đổi cấu hình topic, suffix hoặc retry strategy, việc ánh xạ attempt với bước xử lý thực tế có thể khác.
- Nếu dữ liệu đi qua nhiều dịch vụ với các retry topology độc lập, mỗi dịch vụ có thể có khái niệm attempt riêng.

**Nguồn sự thật cho replay và idempotency là event id và trạng thái nghiệp vụ**, không phải chỉ số attempt. Nếu cần enforce “tối đa N lần thử trong 24 giờ xuyên qua mọi deployment”, hãy ghi trạng thái trong database hoặc một workflow store bền vững.

## 10. Thứ tự record khi chuyển sang retry topic

Non-blocking retry cho phép topic chính tiếp tục xử lý record mới trong lúc record lỗi đang chờ trên retry topic. Vì thế, các side effect có thể xảy ra không theo thứ tự Kafka ban đầu.

Ví dụ với cùng một order id:

~~~text
orders.events partition 0
  offset 10: OrderCreated  -> lỗi -> retry topic
  offset 11: OrderPaid     -> được xử lý ngay
  offset 12: OrderShipped  -> được xử lý ngay

Một lúc sau:
  OrderCreated được xử lý lại từ retry topic
~~~

Retry-topic attempt header cho biết `OrderCreated` đã trải qua bước retry nào; nó **không** sửa được thứ tự side effect. Nếu nghiệp vụ yêu cầu `OrderCreated` trước `OrderPaid`, cần thiết kế xử lý tuần tự theo key, version check, state machine hoặc chọn blocking retry phù hợp.

Số lần attempt cũng không nên được dùng để ưu tiên áp dụng event cũ lên state mới. Thứ tự nghiệp vụ phải dựa trên version/sequence của aggregate hoặc hợp đồng sự kiện.

## 11. Idempotency khi record được republish

Non-blocking retry hoạt động theo hướng at-least-once; một record có thể được xử lý lại. Đặc biệt, nếu nghiệp vụ đã commit vào database nhưng container gặp lỗi trước khi publish/commit offset hoàn tất, sự kiện có thể được giao lại.

Một thiết kế inbox đơn giản:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Khi xử lý:

1. Bắt đầu transaction database.
2. Ghi event id vào inbox table bằng thao tác có unique constraint.
3. Nếu đã có event id, xem side effect tương ứng đã hoàn tất hoặc kiểm tra trạng thái nghiệp vụ.
4. Nếu event id mới, cập nhật dữ liệu nghiệp vụ trong cùng transaction.
5. Commit database transaction.
6. Để listener trả thành công hoặc acknowledge đúng theo container.

Không tạo event id mới trong mỗi retry. Header attempt được phép thay đổi giữa các lần thử; event id phải ổn định để nhận diện cùng một sự kiện.

## 12. Đo lường attempt trong retry topic

Hãy xem header như tín hiệu chẩn đoán, kết hợp cùng metrics ở nhiều tầng.

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Số record vào retry topic | Lượng sự kiện không xử lý được ngay | Phát hiện lỗi dependency hoặc release |
| Attempt distribution | Tỷ lệ record được xử lý ở các bước retry | Nhận diện nhiều record chỉ thành công sau nhiều bước |
| Retry topic lag | Backlog trong retry topology | Kiểm tra năng lực xử lý retry |
| Oldest retry record age | Thời gian tồn tại của record chưa xử lý | Theo dõi SLA |
| Processing duration | Thời gian xử lý mỗi lần listener được gọi | Tìm bottleneck |
| Exception rate by class | Nhóm nguyên nhân lỗi | Quyết định loại lỗi có retry hữu ích không |
| DLT publish rate | Số record đã hết retry hoặc fatal | Kích hoạt điều tra/replay |
| DLT publish failures | Rủi ro record không được recovery bền vững | Alert nghiêm trọng |

### 12.1. Cardinality khi đưa attempt vào metric

Giá trị attempt thường là tập hữu hạn theo policy, nhưng nếu tổ hợp với topic, exception, service, instance và nhiều tag khác, time series vẫn có thể tăng nhanh.

Có thể gom attempt thành nhóm:

- `initial` — lần xử lý đầu ở topic chính hoặc header chưa có, theo quy ước dashboard.
- `retry_1` hoặc `retry_2` — các bước retry được định nghĩa rõ.
- `retry_3_plus` — nhóm retry cao.
- `unknown` — header vắng mặt hoặc không thể giải mã.

Tránh dùng `eventId`, `orderId`, offset, message key hoặc trace id làm metric label. Các định danh này phù hợp với log/trace có kiểm soát hơn.

### 12.2. Alert hữu ích

Tùy SLA, có thể cảnh báo khi:

1. Lượng publish vào retry topic tăng đột biến.
2. Một exception class tăng đồng thời với retry-topic lag.
3. Tỷ lệ record ở các attempt cao tăng kéo dài.
4. Tuổi record cũ nhất trong retry topology vượt ngân sách.
5. DLT nhận nhiều record hơn baseline.
6. DLT publish lỗi hoặc recovery thất bại.

Không đặt alert chỉ vì một record có attempt bằng 3. Cần nhìn cùng số lượng record, exception type, thời gian backoff và mức độ quan trọng của luồng nghiệp vụ.

## 13. Logging và correlation khi điều tra

Một log hữu ích cần làm rõ record đến từ topic chính hay retry topic, thay vì chỉ ghi “attempt=3”:

~~~text
service=billing
topic=orders.events-retry-2000
partition=1
offset=128
eventId=evt-042
retryTopicAttempt=3
exception=RemoteServiceUnavailableException
~~~

Các giá trị trên chỉ là minh họa. Trong ứng dụng thực tế:

- Ghi service, listener id, consumer group và tên topic.
- Giữ event id xuyên suốt chuỗi retry và DLT.
- Ghi exception class, không log toàn bộ secret hoặc payload nhạy cảm.
- Thêm số attempt như một thuộc tính của log.
- Dùng trace id trong hệ thống tracing thay vì metric tag.

Nếu điều tra record đã bị chuyển qua nhiều topic, hãy ghép log bằng event id và thời gian, kết hợp retry headers. Offset của retry topic khác offset của topic chính; không dùng cùng offset để suy ra đây là cùng một record trên các topic.

## 14. Runbook: attempt hiển thị không như mong đợi

### 14.1. Header không có trên topic chính

Đây có thể là hành vi bình thường trước lần publish retry. Kiểm tra:

1. Record có đang được xử lý lần đầu không?
2. Listener thực sự dùng `@RetryableTopic` hoặc configuration builder cho non-blocking retry không?
3. Error handler đã từng republish record chưa?
4. Code đọc `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` hay đang đọc nhầm `KafkaHeaders.DELIVERY_ATTEMPT`?
5. Listener có sử dụng đúng header name và xử lý null không?

Đừng tạo retry giả chỉ để header xuất hiện.

### 14.2. Header trên retry topic không tăng

1. Xác nhận record thực sự đi qua một lần republish tiếp theo hay chỉ bị blocking retry trong cùng container.
2. Kiểm tra custom recoverer có preserve/overwrite headers không.
3. Xác nhận framework đang dùng đúng retry topic topology.
4. Kiểm tra có reuse một retry topic theo delay strategy không.
5. Xem record có bị republish thủ công thay vì đi qua retry-topic infrastructure không.

Nếu retry count của container tăng nhưng retry-topic attempt không tăng, có thể hai số đang phản ánh hai cơ chế khác nhau, không nhất thiết là lỗi.

### 14.3. Attempt vượt hoặc khác kỳ vọng của annotation

1. Kiểm tra phiên bản Spring Kafka.
2. Xem lại ý nghĩa của `attempts`: tổng số lần thử, không chỉ số lần retry thêm.
3. Kiểm tra blocking retry có được kết hợp không.
4. Kiểm tra có nhiều lớp retry trong service/HTTP client không.
5. Đối chiếu exception classification và DLT routing.
6. Xem có replay thủ công hoặc producer ngoài framework không.

Không điều chỉnh production policy chỉ dựa trên một giá trị header mà chưa dựng lại đường đi của record.

### 14.4. DLT nhận record sớm hơn kỳ vọng

Nguyên nhân có thể là exception không retryable, timeout hoặc chính sách DLT/retry topic đặc biệt. Kiểm tra exception class, cause chain, predicate phân loại và deadline.

Một record fatal vào DLT sau lần xử lý đầu không chứng minh infrastructure đã bỏ qua các attempt theo lỗi. Đó có thể chính là chính sách đúng.

### 14.5. Retry topic bị dồn backlog

1. Kiểm tra số consumer của retry topic và số partition.
2. Kiểm tra backoff/due timestamp có đang khiến record chờ hợp lệ không.
3. Kiểm tra dependency đang lỗi diện rộng hay không.
4. Đối chiếu exception rate, processing rate và consumer lag.
5. Giới hạn retry storm bằng backoff và concurrency hợp lý.
6. Xác nhận DLT có hoạt động khi hết retry.

Không giảm delay về 0 chỉ để lag biến mất; việc đó có thể gây thêm áp lực lên dependency đang yếu.

## 15. Kiểm thử attempt trong non-blocking retry

Integration test nên tập trung vào **đường đi của record qua các topic**, không chỉ đếm số lần gọi listener.

Kịch bản gợi ý:

1. Tạo topic chính và các retry/DLT topic bằng cấu hình tương đương môi trường dự kiến.
2. Đặt `@RetryableTopic(attempts = "4")` với backoff ngắn để dễ quan sát.
3. Gửi một record có event id ổn định.
4. Buộc listener lỗi retryable trong những lần đầu và thành công ở lần sau.
5. Ghi lại topic, partition, offset và attempt header trong mỗi lần xử lý.
6. Xác nhận record chuyển sang retry topic khi có lỗi, không phải chỉ gọi lại trong cùng container.
7. Đối chiếu attempt metadata và số lần xử lý với chính sách.
8. Làm record thất bại đến hết retry và xác nhận DLT nhận record.
9. Thử exception non-retryable để xác nhận recovery có thể xảy ra sớm.
10. Thử restart consumer ở giữa chuỗi retry để quan sát metadata được giữ qua Kafka record.
11. Thử blocking retry kết hợp non-blocking retry để phân biệt hai bộ đếm.
12. Kiểm tra consumer idempotent khi record được giao lại hoặc DLT được replay.

Ví dụ listener test thu thập ngữ cảnh:

~~~java
record AttemptObservation(
        String topic,
        int partition,
        long offset,
        Integer retryTopicAttempt) {}

List<AttemptObservation> observations =
        new CopyOnWriteArrayList<>();

@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 200))
@KafkaListener(
        topics = "orders.test",
        groupId = "orders-test")
public void handleTest(
        ConsumerRecord<String, OrderEvent> record) {

    Header h = record.headers()
            .lastHeader(RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS);
    Integer attempt = (h != null
            && h.value() != null
            && h.value().length == Integer.BYTES)
            ? ByteBuffer.wrap(h.value()).getInt()
            : null;

    observations.add(new AttemptObservation(
            record.topic(),
            record.partition(),
            record.offset(),
            attempt));

    throw new TemporaryTestException("Injected failure");
}
~~~

Đoạn code minh họa dữ liệu cần quan sát, không phải test class độc lập có thể chạy ngay. Trong test thực tế, cần đồng bộ chờ đủ lần publish/consume, gắn listener và DLT handler, reset trạng thái test và tránh timeout quá ngắn gây flakiness.

## 16. Các lỗi triển khai phổ biến

**Nhầm retry-topic attempt với delivery attempt của container.** Hai header đại diện hai cơ chế khác nhau. Hãy dùng đúng constant cho câu hỏi cần trả lời.

**Giả định header luôn có ở topic chính.** Trước khi record được republish, header có thể vắng mặt. Code phải xử lý null.

**Đọc raw bytes sai định dạng.** Chỉ giải mã theo hợp đồng header của phiên bản đang sử dụng; kiểm tra độ dài trước khi dùng `ByteBuffer`.

**Hiểu attempts = 4 là bốn lần retry cộng một lần ban đầu.** Trong `@RetryableTopic`, attempts là tổng lần thử theo chính sách.

**Coi attempt là lịch sử nghiệp vụ toàn cục.** Replay thủ công hoặc nhiều service có thể bắt đầu topology mới. Dùng state bền vững nếu cần giới hạn xuyên nhiều đợt xử lý.

**Bỏ qua thứ tự xử lý.** Non-blocking retry cho phép record phía sau vượt record đang chờ. Thứ tự nghiệp vụ cần được bảo vệ riêng.

**Ack nguồn khi republish recovery chưa thành công.** Nếu publish sang retry/DLT thất bại, phải bảo đảm hệ thống không xác nhận mất record. Cấu hình recoverer, acknowledgement và error handling phải phù hợp.

**Chỉ theo dõi attempt mà không theo dõi DLT, lag, tuổi record.** Một chuỗi retry có thể kéo dài và vi phạm SLA dù số attempt còn nhỏ.

**Lấy attempt làm idempotency key.** Nó có thể trùng hoặc reset. Phải dùng event id hoặc business key ổn định.

## 17. Checklist trước khi vận hành

### Topology và cấu hình

- [ ] Phiên bản Spring Kafka hỗ trợ retry topic và header constant đang dùng.
- [ ] `@RetryableTopic` hoặc builder được cấu hình đúng số tổng attempt.
- [ ] Backoff, timeout, exception classification và DLT policy được xác định.
- [ ] Các retry topic/DLT có partition, replication, retention và ACL phù hợp.
- [ ] Nếu kết hợp blocking retry, đã hiểu rõ sự khác biệt giữa hai bộ đếm.

### Đọc header

- [ ] Dùng `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` cho non-blocking retry.
- [ ] Dùng `KafkaHeaders.DELIVERY_ATTEMPT` khi cần quan sát delivery attempt của container.
- [ ] Xử lý header vắng mặt hoặc sai định dạng an toàn.
- [ ] Không giả định offset của topic chính giống offset của retry topic.
- [ ] Không dùng attempt để thay thế event id và trạng thái xử lý bền vững.

### Observability và recovery

- [ ] Ghi log có event id, topic, partition, offset và attempt.
- [ ] Có metrics retry publish rate, lag, tuổi record và DLT.
- [ ] Cảnh báo khi dependency lỗi, retry tăng hoặc DLT xuất hiện bất thường.
- [ ] Recovery chỉ hoàn tất khi record được chuyển lưu an toàn.
- [ ] Quy trình replay có idempotency và kiểm soát tốc độ.
- [ ] Đã thử restart/rebalance, fatal exception và blocking + non-blocking retry.

## Kết luận

Trong Spring Kafka non-blocking retry, `RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS` giúp nhận biết bước xử lý của record khi nó được republish qua retry topics. Giá trị và sự hiện diện của header cần được hiểu trong phạm vi retry-topic infrastructure, khác với `KafkaHeaders.DELIVERY_ATTEMPT` do listener container cung cấp. `@RetryableTopic(attempts = "N")` giới hạn tổng số lần thử theo policy, nhưng số lần xử lý thực tế có thể còn chịu tác động của blocking retry hoặc retry trong dependency client. Hãy đọc header an toàn, theo dõi cả topic và event id, kiểm tra backoff, DLT và consumer lag, đồng thời dùng idempotency để đảm bảo retry/replay không lặp side effect. Khi cần một bộ đếm xuyên restart, replay và nhiều dịch vụ, phải thiết kế trạng thái bền vững riêng thay vì chỉ dựa vào header.
