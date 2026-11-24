# Gom nhóm, lấy mẫu và giảm tần suất khi truyền dữ liệu thời gian thực

Trong hệ thống realtime, nguồn dữ liệu có thể phát hàng nghìn sự kiện mỗi giây trong khi client chỉ cần cập nhật màn hình vài lần mỗi giây. Nếu gửi từng sự kiện, hệ thống phải trả chi phí cho nhiều frame, metadata, callback, encode/decode và lần xử lý nhỏ. Nếu gom quá nhiều sự kiện hoặc giảm tần suất quá mạnh, dữ liệu đến chậm và có thể mất những thay đổi quan trọng.

Ba kỹ thuật thường dùng để cân bằng chi phí và độ trễ là:

- **Gom nhóm (batching)**: kết hợp nhiều sự kiện thành một payload hoặc một đơn vị xử lý.
- **Lấy mẫu (sampling)**: chỉ chọn một phần dữ liệu đại diện theo thời gian, số lượng hoặc quy tắc nghiệp vụ.
- **Giảm tần suất (throttling/rate control)**: giới hạn số lần phát hoặc xử lý trong một khoảng thời gian.

Các kỹ thuật này có mục tiêu khác nhau và có thể kết hợp. Ví dụ, hệ thống telemetry có thể gom tối đa 100 mẫu hoặc chờ 200 ms, sau đó chỉ gửi trạng thái mới nhất mỗi 250 ms cho dashboard. Trong khi đó, cảnh báo vượt ngưỡng vẫn phải được gửi ngay và không được loại bỏ bởi sampling.

## 1. Khi nào cần tối ưu luồng dữ liệu?

Giả sử một thiết bị gửi 2.000 phép đo mỗi giây. Mỗi phép đo chỉ có vài trường, nhưng nếu mỗi phép đo tạo một request riêng, server phải xử lý 2.000 lần định tuyến, decode, dispatch và phản hồi. Nếu dashboard chỉ vẽ biểu đồ 4 lần mỗi giây, phần lớn cập nhật trung gian có thể không tạo thêm giá trị hiển thị.

Một số tình huống phổ biến:

- Telemetry, cảm biến, CPU, memory hoặc network metrics phát dữ liệu liên tục.
- Bảng giá hoặc trạng thái tồn kho thay đổi nhanh hơn tốc độ màn hình cần cập nhật.
- Vị trí xe hoặc thiết bị được cập nhật nhiều lần trong một giây.
- Log và sự kiện vận hành có lưu lượng lớn, cần gom trước khi chuyển sang dịch vụ phân tích.
- Client di động hoặc mạng yếu không thể tiêu thụ mọi sự kiện nguồn.

Trước khi tối ưu, hãy xác định mục tiêu: giảm số message, giảm byte truyền, giảm tải xử lý, giới hạn độ trễ, hay giữ lại các sự kiện quan trọng. Một kỹ thuật không thể tối ưu tất cả mục tiêu cùng lúc.

## 2. Phân biệt batching, sampling và throttling

| Kỹ thuật | Cách hoạt động | Dữ liệu bị bỏ? | Tác động chính |
|---|---|---|---|
| Batching | Gom nhiều event thành một batch | Không, nếu batch được giữ nguyên đầy đủ | Giảm số lần gửi và overhead trên mỗi event |
| Sampling | Chọn một phần event hoặc giá trị đại diện | Có thể có | Giảm lượng dữ liệu cần truyền/xử lý |
| Throttling | Giới hạn số lần phát trong một khoảng thời gian | Tùy chính sách: có thể bỏ, giữ đầu tiên hoặc giữ mới nhất | Giới hạn tần suất cập nhật |
| Aggregation | Tính min/max/avg/count hoặc trạng thái tổng hợp từ nhiều event | Không giữ từng event riêng lẻ; giữ thông tin tổng hợp | Giảm dữ liệu nhưng bảo toàn một số đặc tính thống kê |
| Backpressure | Consumer yêu cầu số phần tử mà nó có thể xử lý | Không nhất thiết; upstream được điều tiết nếu hỗ trợ | Điều phối tốc độ producer/consumer |

Ví dụ: 500 phép đo trong một giây có thể được gom thành 5 batch, mỗi batch 100 mẫu. Nếu dashboard chỉ cần một điểm mỗi 250 ms, có thể lấy mẫu trạng thái mới nhất 4 lần/giây. Nếu mục tiêu là phân tích chất lượng tín hiệu, thay vì bỏ mẫu, hãy gửi `min`, `max`, `average`, `count` và `last` của từng cửa sổ.

## 3. Chọn chính sách theo loại dữ liệu

Không phải dữ liệu realtime nào cũng được phép giảm. Hãy phân loại trước khi áp dụng operator:

| Loại dữ liệu | Chiến lược phù hợp | Vì sao |
|---|---|---|
| Trạng thái hiện tại như nhiệt độ hoặc vị trí mới nhất | Sampling giữ giá trị mới nhất | Client thường chỉ cần trạng thái gần nhất |
| Telemetry cần xu hướng | Aggregation theo cửa sổ thời gian | Giữ min/max/avg/count thay vì mọi mẫu |
| Log hoặc metric số lượng lớn | Batching theo số lượng và thời gian | Giảm overhead nhưng vẫn giữ từng event |
| Cập nhật UI có thể gộp | Throttling hoặc debounce | Tránh render quá thường xuyên |
| Cảnh báo an toàn, thanh toán, lệnh điều khiển | Không sampling/drop; dùng delivery và acknowledgement phù hợp | Mất một event có thể gây hậu quả nghiệp vụ |
| Sự kiện cần kiểm toán | Lưu bền vững rồi phân phối theo batch | Không được thay thế bản ghi gốc bằng mẫu đại diện |

Một thiết kế thường tách hai luồng: luồng đầy đủ được lưu hoặc chuyển tới hệ thống xử lý tin cậy; luồng đã sampling/aggregation phục vụ dashboard. Không dùng dữ liệu đã giảm tần suất làm nguồn dữ liệu kiểm toán hoặc đối soát.

## 4. Batching theo số lượng và thời gian

Nếu chỉ gom theo số lượng, batch có thể chờ rất lâu khi lưu lượng thấp. Nếu chỉ gom theo thời gian, batch có thể chứa quá nhiều phần tử khi lưu lượng tăng đột biến. Thực tế thường dùng hai điều kiện cùng lúc:

- Gửi khi đủ `maxBatchSize` phần tử.
- Hoặc gửi khi đã hết `maxWait`, dù batch chưa đầy.

Ví dụ: tối đa 100 event hoặc 200 ms, điều kiện nào tới trước sẽ kích hoạt batch. Điều này giới hạn cả kích thước batch và độ trễ chờ gom nhóm.

### Dùng Reactor bufferTimeout

`bufferTimeout(maxSize, maxTime)` gom các phần tử thành `List<T>`. Batch được phát khi đạt kích thước tối đa hoặc hết thời gian chờ:

```java
Flux<List<MetricEvent>> batches = metricSource
    .bufferTimeout(100, Duration.ofMillis(200));
```

Nếu nguồn phát đều, batch thường đầy trước khi hết 200 ms. Nếu nguồn thưa, timer giúp batch nhỏ vẫn được gửi để không chờ vô hạn. Cần đặt `maxSize` và `maxTime` theo kích thước payload, tốc độ nguồn và SLA độ trễ.

### Tạo DTO đại diện cho một batch

Nên có schema rõ ràng cho batch thay vì gửi một `List` không có ngữ cảnh:

```java
public record MetricEvent(
    String deviceId,
    long timestamp,
    double value
) {}

public record MetricBatch(
    String batchId,
    String deviceId,
    List<MetricEvent> events
) {}
```

Tạo batch từ luồng event:

```java
Flux<MetricBatch> batches = metricSource
    .bufferTimeout(100, Duration.ofMillis(200))
    .filter(events -> !events.isEmpty())
    .map(events -> new MetricBatch(
        UUID.randomUUID().toString(),
        events.getFirst().deviceId(),
        events
    ));
```

Ví dụ dùng `List.getFirst()` yêu cầu Java 21. Nếu project dùng Java 17, thay bằng `events.get(0)`. Đoạn mã giả định `metricSource` đã được giới hạn vào một device/partition. Trong thực tế, chỉ gom event cùng device/tenant/partition vào một batch; không lấy device ID từ phần tử đầu tiên nếu batch có thể chứa nhiều thiết bị. Nếu cần gom nhiều partition, hãy tách luồng theo khóa trước khi buffer và đặt giới hạn cho số partition hoạt động.

### Dùng windowTimeout khi cần xử lý theo cửa sổ

`windowTimeout(maxSize, maxTime)` tạo các `Flux<T>` con thay vì gom ngay thành `List<T>`. Cách này hữu ích khi muốn xử lý từng phần tử trong cửa sổ bằng pipeline reactive:

```java
Flux<MetricSummary> summaries = metricSource
    .windowTimeout(100, Duration.ofMillis(200))
    .concatMap(window -> window.collectList()
        .filter(events -> !events.isEmpty())
        .map(this::summarize));
```

`bufferTimeout` thuận tiện khi service cần một collection; `windowTimeout` phù hợp khi muốn áp dụng pipeline lên từng cửa sổ. Dù dùng operator nào, vẫn cần giới hạn số phần tử và kích thước byte của batch.

Các cửa sổ của `bufferTimeout`/`windowTimeout` dựa trên processing time của subscription, không tự căn theo mốc đồng hồ như đầu mỗi phút. Nếu cần bucket căn theo wall clock hoặc event time, hãy tính bucket key từ timestamp và quản lý cửa sổ tương ứng ở tầng ứng dụng.

## 5. Giới hạn kích thước byte của batch

Giới hạn số phần tử chưa chắc giới hạn được dung lượng. Một batch gồm 100 ID ngắn khác rất nhiều so với 100 payload JSON chứa văn bản dài hoặc dữ liệu nhị phân.

Khi thiết kế batch, cần đặt:

- `maxBatchSize`: số event tối đa.
- `maxBatchBytes`: tổng dung lượng encode tối đa.
- `maxWait`: thời gian tối đa một event chờ trong batch.
- Giới hạn kích thước từng event và metadata.
- Chính sách cho event vượt giới hạn: từ chối, gửi riêng nếu hợp lệ, hoặc ghi vào kho bền vững.

Ví dụ, nếu payload inbound tối đa là 64 KB, không nên cấu hình batch mục tiêu đúng 64 KB vì còn overhead serialization, metadata và framing. Hãy dành khoảng trống an toàn và kiểm tra kích thước sau encode ở nơi phù hợp. `bufferTimeout` chỉ giới hạn số phần tử và thời gian; nó không tự giới hạn tổng byte.

Nếu một event có thể rất lớn, hãy kiểm tra kích thước event trước khi đưa vào batch. Không chia một payload tùy ý thành nhiều event mà không có giao thức ghép lại, vì server có thể không biết thứ tự, tính toàn vẹn hoặc ranh giới dữ liệu ban đầu.

## 6. Aggregation: giữ thông tin thay vì giữ mọi mẫu

Sampling bỏ một phần event; aggregation tính giá trị đại diện cho một nhóm event. Với telemetry, các thống kê thường hữu ích là:

- `count`: số mẫu trong cửa sổ.
- `min` và `max`: biên độ biến động.
- `average`: giá trị trung bình.
- `last`: giá trị mới nhất.
- `sum`: tổng, phù hợp với counter hoặc lượng tích lũy.

Ví dụ DTO tổng hợp:

```java
public record MetricSummary(
    String deviceId,
    long windowStart,
    long windowEnd,
    long count,
    double min,
    double max,
    double average,
    double last
) {}
```

Tính summary cho một batch:

```java
MetricSummary summarize(List<MetricEvent> events) {
    double min = events.stream().mapToDouble(MetricEvent::value).min().orElseThrow();
    double max = events.stream().mapToDouble(MetricEvent::value).max().orElseThrow();
    double average = events.stream().mapToDouble(MetricEvent::value).average().orElseThrow();
    MetricEvent last = events.getLast();

    return new MetricSummary(
        last.deviceId(),
        events.getFirst().timestamp(),
        last.timestamp(),
        events.size(),
        min,
        max,
        average,
        last.value()
    );
}
```

Ví dụ trên giả định event đã được sắp xếp theo timestamp và cùng một device. Nếu dữ liệu đến trễ hoặc không đúng thứ tự, cần xác định rõ `windowStart`, `windowEnd` theo event time và chính sách xử lý late event; không mặc định phần tử cuối cùng luôn là event mới nhất theo thời gian.

Aggregation phù hợp với dashboard và phân tích xu hướng. Nếu cần điều tra chi tiết từng sự kiện, hãy lưu raw event ở một luồng riêng trước khi tổng hợp.

## 7. Sampling theo thời gian với Reactor

Với trạng thái thay đổi nhanh nhưng client chỉ cần giá trị mới nhất định kỳ, `sample(Duration)` là lựa chọn phù hợp. Operator lấy giá trị gần nhất trong mỗi khoảng lấy mẫu:

```java
Flux<MetricEvent> latestEvery250ms = metricSource
    .sample(Duration.ofMillis(250));
```

Ví dụ, nếu nguồn phát 50 giá trị trong 250 ms, client nhận giá trị mới nhất của khoảng đó. Đây là lựa chọn cho trạng thái hiển thị, không phù hợp cho event mà từng lần phát đều quan trọng.

Nếu cần giữ event đầu tiên sau mỗi khoảng thời gian rồi bỏ các event đến trong thời gian còn lại, có thể dùng `sampleFirst`:

```java
Flux<MetricEvent> firstEvery250ms = metricSource
    .sampleFirst(signal -> Mono.delay(Duration.ofMillis(250)));
```

Hai chính sách khác nhau:

| Operator | Giữ lại | Trường hợp phù hợp |
|---|---|---|
| `sample(Duration)` | Giá trị mới nhất của mỗi khoảng | Trạng thái mới nhất cho UI |
| `sampleFirst(...)` | Giá trị đầu tiên, rồi bỏ các giá trị trong cửa sổ | Chỉ cần biết một lần xuất hiện trong mỗi khoảng |

Sampling theo thời gian thường phát ít phần tử hơn nguồn. Nó không bảo đảm phát đúng một phần tử mỗi cửa sổ nếu cửa sổ không có dữ liệu.

## 8. Throttle, debounce và distinctUntilChanged

Các operator giảm tần suất thường bị nhầm lẫn:

| Kỹ thuật | Hành vi | Ví dụ sử dụng |
|---|---|---|
| Throttle-first | Cho event đầu tiên đi qua, bỏ event tiếp theo trong khoảng khóa | Không xử lý nút bấm lặp liên tục |
| Sample/throttle-last | Định kỳ phát event mới nhất | Cập nhật trạng thái UI |
| Debounce | Chỉ phát event khi không có event mới trong một khoảng chờ | Chờ người dùng ngừng nhập tìm kiếm |
| `distinctUntilChanged` | Bỏ các giá trị liên tiếp không thay đổi | Không gửi lại trạng thái giống hệt |

Ví dụ debounce với `sampleTimeout`:

```java
Flux<String> searchTerms = keyStrokes
    .map(KeyStroke::text)
    .sampleTimeout(term -> Mono.delay(Duration.ofMillis(300)));
```

Mỗi ký tự mới tạo một timer. Nếu có ký tự tiếp theo trước khi timer hoàn tất, timer trước bị thay thế; chỉ giá trị cuối cùng sau 300 ms yên lặng được phát. Debounce phù hợp cho tìm kiếm, nhưng không phù hợp cho telemetry liên tục vì khi nguồn không ngừng phát, giá trị có thể không bao giờ được phát.

Ví dụ loại bỏ trạng thái trùng liên tiếp:

```java
Flux<DeviceState> stateChanges = deviceStateSource
    .distinctUntilChanged();
```

Với record, `distinctUntilChanged()` so sánh theo `equals`. Nó chỉ loại bỏ phần tử giống phần tử liền trước; không phải cơ chế deduplicate mọi event từng xuất hiện. Nếu cần chống event gửi lại sau reconnect, hãy dùng event ID và kho dedup có TTL hoặc lưu bền vững, tránh giữ một tập ID vô hạn trong bộ nhớ.

## 9. Giảm tần suất không giống giới hạn tốc độ cứng

Một số operator có tên gần giống nhau nhưng tác động khác nhau:

- `sample`/`sampleFirst` chọn hoặc bỏ event theo cửa sổ thời gian.
- `limitRate(n)` điều chỉnh số phần tử Reactor yêu cầu upstream trong các đợt prefetch; nó không đặt giới hạn cố định theo giây.
- `delayElements(d)` tạo khoảng cách thời gian giữa các phần tử được phát nhưng có thể làm tăng backlog và độ trễ.
- Rate limiter token bucket/sliding window từ chối hoặc trì hoãn request khi vượt quota trong một khoảng thời gian.
- RSocket `REQUEST_N` là credit-based flow control cho stream, giới hạn số payload responder được phép phát theo demand; nó không giới hạn request mới mỗi giây hoặc số byte của payload.

Nếu yêu cầu là “mỗi user tối đa 20 request/giây”, hãy dùng rate limiter theo principal/tenant/route. Nếu yêu cầu là “dashboard chỉ nhận trạng thái mới nhất 4 lần/giây”, hãy dùng sampling. Nếu yêu cầu là “mỗi lần gửi tối đa 100 event”, hãy dùng batching.

## 10. Kết hợp batching và sampling trước khi gửi qua RSocket

Một pipeline telemetry có thể gom các event thành batch rồi gửi qua `request-channel`:

```java
Flux<MetricBatch> batches = metricSource
    .bufferTimeout(100, Duration.ofMillis(200))
    .filter(events -> !events.isEmpty())
    .map(events -> new MetricBatch(
        UUID.randomUUID().toString(),
        events.getFirst().deviceId(),
        events
    ));

Flux<BatchAck> acknowledgements = requester
    .route("metrics.ingest")
    .data(batches, MetricBatch.class)
    .retrieveFlux(BatchAck.class);
```

Luồng `metricSource` trong ví dụ cần được giới hạn vào một device/partition trước khi gom. Nếu nguồn trộn nhiều thiết bị, hãy tách theo khóa và giới hạn số group đang hoạt động; nếu không, batch có thể chứa event của nhiều thiết bị nhưng chỉ mang `deviceId` của phần tử đầu tiên.

Server nhận stream các batch và xử lý tuần tự để giữ thứ tự:

```java
@Controller
public class MetricsController {

    @MessageMapping("metrics.ingest")
    public Flux<BatchAck> ingest(@Payload Flux<MetricBatch> batches) {
        return batches.concatMap(batch -> metricService.store(batch)
            .map(result -> new BatchAck(batch.batchId(), result.acceptedCount())));
    }
}
```

Ở đây, một phần tử của request-channel là một `MetricBatch`; responder trả một `BatchAck` cho mỗi batch được xử lý. `concatMap` bảo đảm chỉ xử lý batch tiếp theo sau khi batch trước hoàn tất. Nếu cần throughput cao hơn, có thể dùng `flatMap(..., concurrency)` nhưng cần chấp nhận thứ tự phản hồi có thể khác thứ tự đầu vào.

Nếu dashboard chỉ cần trạng thái mới nhất, sampling có thể diễn ra trước batching:

```java
Flux<MetricEvent> reduced = metricSource
    .sample(Duration.ofMillis(250));

Flux<MetricBatch> dashboardBatches = reduced
    .bufferTimeout(20, Duration.ofMillis(500))
    .filter(events -> !events.isEmpty())
    .map(this::toMetricBatch);
```

Pipeline này phù hợp với dữ liệu hiển thị có thể bỏ bớt mẫu. Không áp dụng nó cho lệnh điều khiển, cảnh báo hoặc event cần lưu đầy đủ.

## 11. Backpressure và giới hạn buffer trong RSocket

RSocket dùng `REQUEST_N` để requester cấp credit cho responder trong `request-stream` và `request-channel`. Khi client xử lý chậm, demand giảm và nguồn reactive có thể được điều tiết nếu hỗ trợ backpressure.

Credit được tính theo số payload RSocket, không theo số event bên trong DTO. Nếu một payload là `MetricBatch` chứa 100 event thì nó tiêu thụ một đơn vị demand; vì vậy `REQUEST_N` cần được kết hợp với giới hạn số event và tổng byte của từng batch.

Tuy nhiên, backpressure không tự động làm cho mọi nguồn dữ liệu chậm lại. Một hot publisher như sensor callback hoặc event bus có thể tiếp tục phát ngay cả khi subscriber không yêu cầu thêm. Khi đó cần chính sách rõ ràng:

- Buffer có giới hạn và từ chối khi đầy.
- Drop event cũ nếu chỉ cần trạng thái mới nhất.
- Sampling hoặc aggregation trước khi gửi.
- Ghi vào broker bền vững nếu không được phép mất event.
- Tách luồng critical và best-effort để một consumer chậm không chặn cảnh báo.

Không dùng buffer không giới hạn để che giấu tốc độ producer lớn hơn consumer. Buffer chỉ trì hoãn thời điểm hết bộ nhớ; nó không làm tăng năng lực xử lý thật.

## 12. Batch acknowledgement, retry và chống trùng

Khi gửi batch qua request-channel, cần xác định rõ acknowledgement biểu thị điều gì:

- `RECEIVED`: server đã nhận payload.
- `ACCEPTED`: server đã chấp nhận và có thể xử lý sau.
- `PERSISTED`: batch đã được lưu bền vững.
- `PROCESSED`: các event đã được xử lý nghiệp vụ.

Không dùng chung một từ “success” cho các trạng thái này nếu caller cần biết độ bền dữ liệu. Nếu client retry batch sau timeout, server có thể đã lưu batch nhưng acknowledgement bị mất. Vì vậy:

- Gắn `batchId` duy nhất và `eventId` cho từng event.
- Lưu idempotency key cùng kết quả xử lý.
- Xác định batch nào đã được xác nhận bền vững.
- Chỉ retry lỗi tạm thời và dùng backoff.
- Không coi sampling là cơ chế chống trùng; hai kỹ thuật giải quyết vấn đề khác nhau.

Với dữ liệu telemetry best-effort, có thể chấp nhận mất một số batch và ghi metric về số mẫu bị drop. Với dữ liệu nghiệp vụ, cần durable queue/outbox và acknowledgement phù hợp.

## 13. Chọn cửa sổ thời gian và xử lý dữ liệu đến trễ

Batch theo thời gian cần định nghĩa rõ thời gian nào được dùng:

- **Processing time**: thời điểm server/client nhận và xử lý event.
- **Event time**: timestamp do nguồn tạo ra, phản ánh thời điểm sự kiện thực sự xảy ra.

`bufferTimeout` và `windowTimeout` vận hành theo thời gian xử lý của pipeline. Chúng không tự sắp xếp hoặc gom theo event timestamp. Nếu thiết bị có thể gửi trễ hoặc đồng hồ không đồng bộ, cần xử lý event time ở tầng ứng dụng:

- Gắn timestamp và sequence number từ nguồn.
- Chấp nhận một khoảng trễ (lateness) đã định nghĩa.
- Cập nhật lại bucket nếu event tới muộn trong thời hạn cho phép.
- Ghi nhận hoặc loại event quá trễ theo chính sách.
- Đồng bộ đồng hồ thiết bị nếu cần so sánh thời gian tuyệt đối.

Không dùng timestamp của client làm căn cứ bảo mật hoặc thứ tự tuyệt đối nếu client không đáng tin cậy. Với thứ tự trong một thiết bị, sequence number tăng dần thường dễ phát hiện mất hoặc lặp event hơn.

## 14. Kiểm thử batching và sampling

Nên kiểm thử cả tải thấp, tải cao và tình huống nguồn ngừng đột ngột:

1. Phát ít event hơn `maxBatchSize` và xác nhận batch được flush theo `maxWait`.
2. Phát nhanh để batch đầy trước timeout và xác nhận kích thước không vượt ngưỡng.
3. Hoàn tất nguồn khi batch chưa đầy và kiểm tra chính sách flush phần còn lại của pipeline.
4. Gửi event có kích thước lớn để xác nhận giới hạn byte, không chỉ giới hạn số phần tử.
5. Kiểm tra sampling giữ giá trị đầu tiên hoặc mới nhất đúng chính sách.
6. Kiểm tra debounce khi event tiếp tục đến và khi nguồn yên lặng.
7. Mô phỏng consumer chậm để kiểm tra `REQUEST_N`, buffer và overflow.
8. Hủy request-channel giữa chừng và xác nhận tài nguyên được giải phóng.
9. Retry một batch sau khi mất acknowledgement và xác nhận idempotency.
10. Đưa event đến trễ hoặc sai thứ tự để kiểm tra event-time policy.

Với Reactor, dùng `StepVerifier.withVirtualTime(...)` để kiểm tra các operator dựa trên thời gian mà không phải chờ thời gian thực. Bổ sung load test để đo throughput, p95/p99 latency, batch size, queue depth, số event bị drop và bộ nhớ heap/direct memory.

## 15. Checklist thiết kế luồng realtime

- [ ] Phân loại event nào được phép sampling/drop và event nào phải giữ đầy đủ.
- [ ] Chọn `maxBatchSize`, `maxBatchBytes` và `maxWait` theo SLA.
- [ ] Chỉ gom event cùng partition/device/tenant khi hợp đồng yêu cầu.
- [ ] Có batch ID, event ID và sequence number nếu cần retry hoặc phát hiện mất/lặp.
- [ ] Chọn aggregation giữ các thống kê cần thiết như min/max/avg/count/last.
- [ ] Dùng `sample` cho giá trị mới nhất; dùng debounce cho input cần chờ yên lặng.
- [ ] Không nhầm `limitRate` hoặc `REQUEST_N` với rate limiter theo giây.
- [ ] Giới hạn concurrency, buffer theo số phần tử và tổng byte.
- [ ] Xác định semantics của acknowledgement: received, accepted, persisted hay processed.
- [ ] Có chính sách event-time, late event và thứ tự dữ liệu.
- [ ] Kiểm thử slow consumer, cancellation, retry và overflow.
- [ ] Theo dõi batch size, flush delay, dropped events, queue depth và latency.

Gom nhóm giúp giảm overhead khi gửi nhiều event; sampling và throttling giảm số cập nhật khi consumer chỉ cần một phần dữ liệu; aggregation giữ lại thông tin thống kê thay vì từng mẫu. Kết hợp đúng các kỹ thuật này với backpressure, buffer hữu hạn và acknowledgement rõ ràng sẽ giúp luồng RSocket realtime đạt throughput tốt mà vẫn kiểm soát độ trễ, bộ nhớ và tính toàn vẹn dữ liệu.

## Tài liệu tham khảo

- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket Protocol — Flow Control and REQUEST_N](https://rsocket.io/about/protocol/)
