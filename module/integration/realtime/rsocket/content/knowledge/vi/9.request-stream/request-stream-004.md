# Lọc, chuyển đổi và giới hạn dữ liệu trước khi truyền

Một request-stream RSocket có thể phát dữ liệu liên tục trong thời gian dài. Nếu server gửi mọi sự kiện thô, client phải nhận và xử lý cả những phần tử không cần thiết, còn mạng và bộ nhớ phải gánh thêm lưu lượng. Một pipeline Reactor được thiết kế tốt có thể lọc dữ liệu theo yêu cầu, chuyển đổi sang cấu trúc phù hợp, giới hạn số lượng hoặc thời gian phát và điều tiết nhu cầu của nguồn trước khi payload được gửi qua RSocket.

Vị trí đặt operator rất quan trọng. Lọc và chuyển đổi ở phía server trước khi trả về Flux giúp giảm dữ liệu được serialize và truyền qua mạng. Nếu chỉ lọc sau khi client đã nhận dữ liệu, ứng dụng có thể giảm công việc ở giao diện nhưng băng thông đã bị tiêu thụ. Bài học này sử dụng Java, Project Reactor và Spring RSocket để xây dựng pipeline request-stream có kiểm soát.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Chọn vị trí lọc và chuyển đổi dữ liệu ở server hoặc client theo mục tiêu xử lý.
- Dùng các operator như filter, map, filterWhen, flatMap và concatMap để tạo pipeline.
- Giới hạn số phần tử hoặc thời gian sống của một stream bằng take, takeWhile và takeUntil.
- Giảm tần suất phát bằng sample hoặc debounce khi nghiệp vụ cho phép bỏ qua giá trị trung gian.
- Phân biệt limitRate với giới hạn số lượng, giới hạn tốc độ và flow control của RSocket.
- Chọn chính sách backpressure phù hợp cho nguồn dữ liệu nhanh hoặc không tuân theo demand.

## 1. Pipeline dữ liệu trước khi truyền

Trong mô hình request-stream, client gửi một request và server trả về một luồng nhiều phần tử. Với Spring RSocket, một handler có thể trả về Flux:

~~~java
@MessageMapping("sensors.readings")
public Flux<SensorReading> readings(
        @Payload SensorQuery query) {
    return sensorService.streamReadings(query.deviceId());
}
~~~

Spring chuyển các phần tử do publisher phát ra thành payload của stream. Mỗi phần tử đi qua các operator trước khi đến bước encode và gửi qua RSocket. Vì thế, pipeline ở server là nơi phù hợp để chọn dữ liệu, bỏ trường nhạy cảm hoặc chuyển đổi sang DTO công khai.

Một pipeline thường có dạng:

~~~text
Nguồn dữ liệu
    -> lọc theo điều kiện
    -> chuyển đổi sang DTO
    -> giới hạn số lượng/thời gian
    -> điều tiết demand và backpressure
    -> encode payload
    -> RSocket request-stream
~~~

Các operator là những bước xử lý lazy. Chúng được ghép khi tạo pipeline và thực thi khi có subscriber. Trong RSocket, mỗi request-stream tạo subscription cho publisher của request đó; việc hủy stream cần được truyền ngược về nguồn để giải phóng tài nguyên.

## 2. Lọc phần tử bằng filter

Operator filter chỉ phát tiếp phần tử thỏa điều kiện. Các phần tử không phù hợp bị loại khỏi luồng:

~~~java
Flux<SensorReading> highTemperatureReadings =
        sensorService.streamReadings("sensor-17")
                .filter(reading -> reading.temperatureCelsius() >= 30.0);
~~~

Ví dụ này chỉ phát những lần đo có nhiệt độ từ 30 độ C trở lên. Nếu nguồn phát 100 lần đo nhưng chỉ 8 lần thỏa điều kiện, subscriber chỉ nhận 8 phần tử.

### 2.1. Kết hợp nhiều điều kiện

Điều kiện có thể kết hợp bằng toán tử logic:

~~~java
Flux<SensorReading> selected = source
        .filter(reading ->
                reading.temperatureCelsius() >= 30.0
                && reading.batteryPercent() > 10
                && reading.quality() == ReadingQuality.VALID);
~~~

Nên kiểm tra điều kiện rẻ và có khả năng loại nhiều phần tử trước các bước xử lý tốn kém. Ví dụ, lọc thiết bị hoặc trạng thái hợp lệ trước khi gọi dịch vụ enrichment.

### 2.2. filter khác takeWhile

Hai operator có ý nghĩa khác nhau:

~~~java
Flux<Integer> values = Flux.just(2, 4, 7, 8, 10);

Flux<Integer> filtered = values.filter(value -> value % 2 == 0);
// Kết quả: 2, 4, 8, 10

Flux<Integer> prefix = values.takeWhile(value -> value < 7);
// Kết quả: 2, 4
~~~

filter kiểm tra từng phần tử và tiếp tục tìm các phần tử phù hợp ở phía sau. takeWhile kết thúc stream ngay khi gặp phần tử đầu tiên không thỏa điều kiện; phần tử làm điều kiện sai cũng không được phát ra. Vì vậy, hãy dùng takeWhile khi dữ liệu có thứ tự và điều kiện xác định một đoạn đầu của stream.

Nếu muốn phát cả phần tử đầu tiên làm điều kiện đúng, có thể dùng takeUntil:

~~~java
Flux<Integer> throughThreshold =
        Flux.just(2, 4, 7, 8, 10)
                .takeUntil(value -> value >= 7);
// Kết quả: 2, 4, 7
~~~

takeUntil phát phần tử khớp điều kiện rồi hoàn tất.

### 2.3. Lọc bằng điều kiện bất đồng bộ với filterWhen

Đôi khi điều kiện lọc cần gọi một dịch vụ bất đồng bộ, ví dụ kiểm tra quyền xem một thiết bị. Reactor cung cấp filterWhen để nhận một publisher boolean:

~~~java
Flux<SensorReading> visibleReadings =
        source.filterWhen(reading ->
                accessService.canRead(
                        authenticatedUserId,
                        reading.deviceId()));
~~~

filterWhen chỉ phát phần tử khi publisher điều kiện trả về true. Vì phép kiểm tra có thể truy cập cache hoặc service từ xa, cần giới hạn độ trễ và lỗi của nó. Với kiểm tra quyền, lỗi xác minh nên được xử lý theo hướng từ chối truy cập; không biến lỗi thành true để stream tiếp tục phát dữ liệu.

## 3. Chuyển đổi dữ liệu bằng map

map biến đổi từng phần tử thành một giá trị khác. Đây là cách phổ biến để chuyển entity nội bộ thành DTO dành cho client:

~~~java
public record SensorReading(
        String deviceId,
        double temperatureCelsius,
        double humidityPercent,
        double batteryPercent,
        Instant recordedAt,
        String internalDiagnostic) {
}

public record SensorReadingView(
        String deviceId,
        double temperatureCelsius,
        Instant recordedAt) {
}

Flux<SensorReadingView> publicReadings = source
        .map(reading -> new SensorReadingView(
                reading.deviceId(),
                reading.temperatureCelsius(),
                reading.recordedAt()));
~~~

DTO chỉ chứa những trường client cần. Việc chuyển đổi này cũng giúp tránh vô tình gửi trường nội bộ như thông tin chẩn đoán, khóa hệ thống hoặc dữ liệu không được phép tiết lộ.

### 3.1. Thứ tự filter và map

Thứ tự operator ảnh hưởng đến chi phí và ý nghĩa xử lý:

~~~java
Flux<SensorReadingView> result = source
        .filter(reading -> reading.temperatureCelsius() >= 30.0)
        .map(this::toPublicView);
~~~

Nếu có thể đánh giá điều kiện từ dữ liệu gốc, lọc trước rồi mới chuyển đổi. Khi đó các phần tử bị loại không phải đi qua bước tạo DTO hoặc xử lý bổ sung.

Tuy nhiên, nếu điều kiện chỉ có thể đánh giá trên kiểu đã chuyển đổi, cần map trước. Hãy chọn thứ tự dựa trên dữ liệu cần thiết và chi phí thực tế.

### 3.2. map, flatMap và concatMap

map dùng khi mỗi phần tử tạo ra đúng một giá trị đồng bộ. Nếu bước chuyển đổi trả về publisher, cần chọn cách kết hợp phù hợp:

~~~java
// Nhiều phép enrichment có thể chạy đồng thời.
Flux<EnrichedReading> concurrent = source
        .flatMap(reading -> enrichmentService.enrich(reading), 8);

// Chạy tuần tự, giữ thứ tự phần tử đầu vào.
Flux<EnrichedReading> ordered = source
        .concatMap(enrichmentService::enrich);

// Có thể chạy đồng thời nhưng phát kết quả theo thứ tự đầu vào.
Flux<EnrichedReading> concurrentOrdered = source
        .flatMapSequential(reading -> enrichmentService.enrich(reading), 8);
~~~

flatMap cho phép nhiều tác vụ bất đồng bộ chạy đồng thời, nên kết quả có thể đến không theo thứ tự ban đầu. Tham số concurrency giới hạn số publisher con đang hoạt động; prefetch cũng ảnh hưởng số phần tử được yêu cầu trước. concatMap chỉ xử lý publisher con tiếp theo sau khi publisher hiện tại hoàn tất, phù hợp khi thứ tự là bắt buộc. flatMapSequential cho phép xử lý đồng thời nhưng giữ thứ tự phát kết quả.

Không đặt concurrency quá lớn khi mỗi phần tử gọi dịch vụ từ xa. Quá nhiều tác vụ đồng thời có thể làm tăng số connection, hàng đợi và áp lực lên service phụ thuộc.

## 4. Giới hạn số phần tử được phát

Request-stream có thể kéo dài vô hạn. Khi nghiệp vụ chỉ cần một số phần tử nhất định, dùng take:

~~~java
Flux<SensorReading> firstHundred = source.take(100);
~~~

take(100) phát tối đa 100 phần tử rồi hoàn tất và hủy subscription upstream. Nếu pipeline nằm ở server, việc hủy này cho phép nguồn dừng công việc cho request đó. Với nguồn dùng chung, cần hiểu operator chia sẻ nguồn xử lý cancellation như thế nào để không vô tình dừng dữ liệu của subscriber khác.

### 4.1. Giới hạn sau khi lọc hay trước khi lọc

Hai cách viết sau không tương đương:

~~~java
// Phát tối đa 10 phần tử phù hợp.
Flux<SensorReading> tenMatches = source
        .filter(this::isImportant)
        .take(10);

// Chỉ xét 10 phần tử đầu, nên có thể phát ít hơn 10 phần tử phù hợp.
Flux<SensorReading> matchesInFirstTen = source
        .take(10)
        .filter(this::isImportant);
~~~

Nếu yêu cầu là “gửi 10 sự kiện quan trọng”, hãy lọc trước rồi giới hạn. Nếu yêu cầu là “chỉ xét 10 sự kiện mới nhất/đầu tiên của phiên”, giới hạn trước rồi lọc.

### 4.2. Giới hạn theo thời gian

take(Duration) hoàn tất stream sau một khoảng thời gian:

~~~java
Flux<SensorReading> readingsForThirtySeconds =
        source.take(Duration.ofSeconds(30));
~~~

Operator này hữu ích cho một phiên quan sát có thời hạn. Khi thời gian kết thúc, subscription upstream bị hủy. Cần phân biệt với timeout:

- take(Duration) kết thúc bình thường khi hết khoảng thời gian.
- timeout(Duration) phát lỗi nếu không có phần tử tiếp theo trong khoảng thời gian quy định.

~~~java
Flux<SensorReading> monitored = source
        .timeout(Duration.ofSeconds(5));
~~~

Timeout thường dùng để phát hiện nguồn im lặng ngoài dự kiến. Hãy quyết định có retry, fallback hay báo lỗi cho client. Retry request-stream có thể tạo subscription mới và phát lại một phần dữ liệu, vì vậy cần cân nhắc checkpoint hoặc sequence number nếu không muốn trùng/mất dữ liệu.

### 4.3. Giới hạn số lượng theo request của client

Server nên kiểm tra các tham số giới hạn do client gửi. Không để client yêu cầu số lượng tùy ý:

~~~java
private static final int MAX_SAMPLES = 1_000;

private int normalizeMaxSamples(int requested) {
    return Math.max(1, Math.min(requested, MAX_SAMPLES));
}
~~~

Khi handler nhận query, dùng giá trị đã chuẩn hóa:

~~~java
int maxSamples = normalizeMaxSamples(query.maxSamples());

return sensorService.streamReadings(query.deviceId())
        .filter(this::isValid)
        .take(maxSamples);
~~~

Giới hạn phía server là chính sách tài nguyên và nghiệp vụ. Client vẫn có thể hủy sớm hơn, nhưng không thể buộc server phát nhiều hơn giới hạn mà server cho phép.

## 5. Giảm tần suất dữ liệu

Một số stream phát trạng thái mới liên tục, trong khi client chỉ cần một bản cập nhật gần nhất theo chu kỳ. Khi nghiệp vụ cho phép bỏ các giá trị trung gian, có thể giảm tần suất phát.

### 5.1. sample

sample(Duration) phát giá trị gần nhất trong mỗi khoảng thời gian:

~~~java
Flux<SensorReading> sampled = source
        .sample(Duration.ofMillis(250));
~~~

Ví dụ, màn hình biểu đồ chỉ cần cập nhật khoảng bốn lần mỗi giây. Các lần đo xuất hiện giữa hai thời điểm lấy mẫu có thể không được phát ra.

### 5.2. debounce

debounce chỉ phát một phần tử khi không có phần tử mới trong một khoảng thời gian:

~~~java
Flux<String> searchTerms = inputEvents
        .debounce(Duration.ofMillis(300));
~~~

Operator này phù hợp với luồng nhập liệu tìm kiếm, nơi ứng dụng chỉ muốn gọi backend sau khi người dùng tạm dừng gõ. Với telemetry hoặc audit event, debounce có thể làm mất những sự kiện quan trọng; không dùng nếu mỗi sự kiện đều phải được lưu hoặc xử lý.

### 5.3. Sampling không phải rate limit bảo đảm

sample và debounce thay đổi tập dữ liệu được phát. Chúng không bảo đảm giới hạn chính xác số byte mỗi giây, cũng không thay thế flow control của RSocket. Nếu cần giới hạn tốc độ theo quota, hãy áp dụng cơ chế rate limiter phù hợp với nghiệp vụ và theo dõi lưu lượng thực tế.

## 6. Gom nhóm dữ liệu trước khi gửi

Nếu từng phần tử quá nhỏ và tần suất phát rất cao, có thể gom nhiều phần tử thành một batch:

~~~java
Flux<List<SensorReadingView>> batches = source
        .map(this::toPublicView)
        .buffer(50);
~~~

Mỗi batch chứa tối đa 50 phần tử. Spring RSocket có thể serialize mỗi list thành một payload trong request-stream nếu codec của ứng dụng hỗ trợ kiểu dữ liệu đó.

Gom nhóm giúp giảm số message và chi phí framing, nhưng làm tăng độ trễ vì phải chờ đủ phần tử hoặc kết thúc nguồn. Với stream vô hạn, buffer theo kích thước sẽ chỉ phát khi đạt kích thước; nếu tốc độ thấp, có thể cần buffer theo thời gian:

~~~java
Flux<List<SensorReadingView>> timedBatches = source
        .map(this::toPublicView)
        .bufferTimeout(50, Duration.ofMillis(200));
~~~

bufferTimeout phát batch khi đạt số phần tử hoặc hết thời gian. Kích thước batch cần được giới hạn để tránh payload quá lớn và áp lực bộ nhớ.

## 7. Backpressure và limitRate

RSocket request-stream có flow control. Client gửi nhu cầu dữ liệu theo số phần tử, và server không nên phát vượt quá demand đã được cấp. Reactive Streams biểu diễn nhu cầu đó bằng request(n). Khi client tiêu thụ chậm, demand giảm; publisher upstream cần tôn trọng tín hiệu này.

### 7.1. limitRate điều tiết demand upstream

limitRate chia nhỏ yêu cầu từ downstream thành các đợt nhỏ hơn trước khi chuyển lên upstream:

~~~java
Flux<SensorReading> controlled = source
        .limitRate(64);
~~~

Điều này có thể giúp nguồn upstream không nhận một yêu cầu rất lớn cùng lúc và kiểm soát lượng phần tử được prefetch. Tuy nhiên:

- limitRate không giới hạn tổng số phần tử của stream.
- limitRate không phải bộ giới hạn tốc độ theo giây.
- limitRate không đồng nghĩa với kích thước frame hoặc số byte tối đa của RSocket.
- Nó điều chỉnh demand giữa các operator trong pipeline; flow control của RSocket vẫn hoạt động ở tầng giao thức.

Muốn giới hạn tổng số phần tử, dùng take. Muốn giới hạn thời gian, dùng take(Duration). Muốn giảm tần suất, cân nhắc sample hoặc debounce. Muốn giới hạn số request đồng thời khi enrichment, cấu hình concurrency cho flatMap.

### 7.2. Nguồn push nhanh và chính sách backpressure

Một số nguồn hot hoặc callback bên ngoài có thể phát dữ liệu mà không chờ demand. Khi đó cần xác định chính sách rõ ràng:

~~~java
// Giữ dữ liệu trong buffer có giới hạn; overflow sẽ làm stream lỗi.
Flux<SensorReading> buffered = hotSource
        .onBackpressureBuffer(256);

// Bỏ các phần tử đến khi downstream chưa có demand.
Flux<SensorReading> dropping = hotSource
        .onBackpressureDrop();

// Chỉ giữ giá trị mới nhất cho consumer chậm.
Flux<SensorReading> latest = hotSource
        .onBackpressureLatest();
~~~

Chọn theo ý nghĩa dữ liệu:

| Chính sách | Khi consumer chậm | Phù hợp với |
|---|---|---|
| Buffer có giới hạn | Giữ phần tử trong hàng đợi; overflow có thể phát lỗi | Sự kiện cần xử lý đủ trong giới hạn tải |
| Drop | Bỏ phần tử mới đến khi chưa có demand | Mẫu telemetry có thể mất |
| Latest | Thay giá trị đang chờ bằng giá trị mới nhất | Trạng thái hiện tại, số đo tức thời |
| Error khi quá tải | Kết thúc stream khi không thể nhận thêm | Hệ thống cần báo quá tải rõ ràng |

Không dùng buffer không giới hạn cho stream dài hạn. Nếu tốc độ nguồn luôn lớn hơn tốc độ tiêu thụ, hàng đợi sẽ tăng liên tục và cuối cùng gây áp lực bộ nhớ. Với buffer có giới hạn, cần định nghĩa cách ghi nhận overflow, báo lỗi hoặc phục hồi stream.

### 7.3. Backpressure end-to-end

Khi server trả Flux từ handler, demand của RSocket peer được chuyển thành nhu cầu của publisher theo chuỗi operator. Một filter có thể phải yêu cầu thêm phần tử upstream để tìm đủ số phần tử phù hợp; vì thế số phần tử nguồn được đọc có thể lớn hơn số payload được gửi.

Nếu pipeline có flatMap, buffer, sample hoặc một nguồn hot, các operator này có thể thay đổi cách demand được truyền hoặc giữ phần tử trong bộ nhớ. Hãy theo dõi số phần tử được đọc, số phần tử bị lọc, số payload được phát, độ trễ và kích thước buffer. Flow control của giao thức không tự giải quyết được mọi hàng đợi nằm trong ứng dụng.

## 8. Tích hợp pipeline với Spring RSocket

Ví dụ sau minh họa một handler request-stream. Server xác thực người dùng bằng Principal, kiểm tra tham số, lọc dữ liệu, chuyển đổi DTO và giới hạn số phần tử trước khi truyền:

~~~java
public record SensorQuery(
        String deviceId,
        double minimumTemperature,
        int maxSamples) {
}

public record SensorReadingView(
        String deviceId,
        double temperatureCelsius,
        Instant recordedAt) {
}

@Controller
public class SensorController {

    private static final int MAX_SAMPLES = 1_000;

    private final SensorService sensorService;

    public SensorController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensors.readings")
    public Flux<SensorReadingView> readings(
            @Payload SensorQuery query,
            Principal principal) {

        int maxSamples = Math.max(
                1, Math.min(query.maxSamples(), MAX_SAMPLES));

        return sensorService.streamForUser(
                        principal.getName(),
                        query.deviceId())
                .filter(reading ->
                        reading.temperatureCelsius()
                                >= query.minimumTemperature())
                .map(reading -> new SensorReadingView(
                        reading.deviceId(),
                        reading.temperatureCelsius(),
                        reading.recordedAt()))
                .take(maxSamples)
                .limitRate(64);
    }
}
~~~

Trong ví dụ này:

1. Service giới hạn dữ liệu theo người dùng đã xác thực và thiết bị được phép truy cập.
2. filter bỏ các lần đo dưới ngưỡng nhiệt độ.
3. map chỉ giữ các trường được phép gửi cho client.
4. take giới hạn số phần tử được phát.
5. limitRate điều tiết demand chuyển lên publisher upstream.

Các bước này chạy trước khi framework encode từng phần tử thành RSocket payload. Do đó dữ liệu không phù hợp không cần serialize và truyền qua mạng.

### 8.1. Client nhận và hủy stream

Client có thể gửi query và nhận Flux:

~~~java
Flux<SensorReadingView> readings = requester
        .route("sensors.readings")
        .data(new SensorQuery("sensor-17", 30.0, 500))
        .retrieveFlux(SensorReadingView.class);
~~~

Client cũng có thể đặt giới hạn cục bộ:

~~~java
Disposable subscription = readings
        .take(100)
        .subscribe(this::updateDashboard);
~~~

Khi client nhận đủ 100 phần tử, take hủy subscription. Cancellation được truyền qua RSocket để server dừng stream tương ứng nếu publisher và nguồn dữ liệu hỗ trợ hủy. Giới hạn client là cách bảo vệ consumer, còn giới hạn server vẫn cần thiết để thực thi chính sách tài nguyên.

Khi component hoặc màn hình kết thúc trước khi stream hoàn tất, hãy hủy Disposable:

~~~java
subscription.dispose();
~~~

Đối với nguồn dùng chung nhiều subscriber, cần đảm bảo việc hủy một client chỉ dừng subscription của client đó. Nguồn upstream chỉ nên bị hủy khi chính sách chia sẻ xác định không còn subscriber cần dữ liệu.

## 9. Những lỗi thường gặp

### Lọc ở client nhưng kỳ vọng giảm băng thông

Nếu server đã gửi tất cả phần tử và client mới gọi filter, dữ liệu vẫn đi qua mạng. Đưa điều kiện lọc có thể thực hiện an toàn lên request và áp dụng ở server trước khi serialize.

### Dùng take trước filter sai yêu cầu

take(10).filter(...) chỉ xét 10 phần tử đầu, có thể trả về ít hơn 10 kết quả. Nếu cần 10 kết quả thỏa điều kiện, filter trước take.

### Dùng takeWhile cho điều kiện không liên tục

takeWhile kết thúc khi gặp phần tử đầu tiên không thỏa. Nếu các phần tử phía sau vẫn có thể hợp lệ, dùng filter.

### Chuyển đổi bất đồng bộ bằng flatMap không giới hạn

flatMap có thể chạy nhiều publisher con cùng lúc. Hãy đặt concurrency và prefetch phù hợp, hoặc dùng concatMap nếu cần thứ tự và xử lý tuần tự.

### Coi limitRate là giới hạn tổng số phần tử

limitRate điều tiết demand upstream. Nó không thay thế take, timeout hoặc một bộ giới hạn tốc độ theo thời gian.

### Gom toàn bộ stream vô hạn vào bộ nhớ

collectList hoặc buffer không giới hạn có thể giữ dữ liệu cho đến khi nguồn hoàn tất. Với stream dài hạn, hãy dùng batch có kích thước hoặc thời gian giới hạn.

### Dùng drop hoặc latest cho dữ liệu bắt buộc phải lưu

Các chính sách này chủ động bỏ phần tử. Chỉ dùng khi nghiệp vụ chấp nhận mất các giá trị trung gian; với giao dịch hoặc audit event, cần cơ chế lưu bền vững và xác nhận xử lý.

## 10. Kiểm thử pipeline bằng StepVerifier

Có thể kiểm tra filter, map và take mà không cần mở kết nối RSocket:

~~~java
Flux<String> pipeline = Flux.just(18, 31, 27, 35, 22)
        .filter(value -> value >= 30)
        .map(value -> "temperature=" + value)
        .take(2);

StepVerifier.create(pipeline)
        .expectNext("temperature=31")
        .expectNext("temperature=35")
        .verifyComplete();
~~~

Ngoài kết quả, nên kiểm tra hành vi hủy khi take đạt giới hạn:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(10))
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source.take(2))
        .expectNext(0L, 1L)
        .verifyComplete();

assertThat(cancelled).isTrue();
~~~

Với tích hợp RSocket, kiểm thử thêm các trường hợp client hủy sớm, server lỗi giữa stream, nguồn không phát dữ liệu, consumer chậm và buffer overflow. Kiểm tra số phần tử thực sự được server đọc và gửi để xác nhận lọc diễn ra trước ranh giới truyền tải.

## 11. Hướng dẫn chọn operator

| Yêu cầu | Operator hoặc cơ chế | Ghi chú |
|---|---|---|
| Chỉ gửi phần tử thỏa điều kiện | filter | Điều kiện được kiểm tra trên từng phần tử |
| Điều kiện cần publisher bất đồng bộ | filterWhen | Xử lý lỗi và độ trễ của predicate |
| Chuyển entity thành DTO | map | Giữ phép biến đổi đồng bộ, một-một |
| Gọi dịch vụ enrichment bất đồng bộ | flatMap, concatMap, flatMapSequential | Chọn concurrency và thứ tự |
| Phát tối đa N phần tử | take(N) | Hoàn tất và hủy upstream |
| Phát trong tối đa một khoảng thời gian | take(Duration) | Hoàn tất bình thường khi hết thời gian |
| Kết thúc nếu stream im lặng quá lâu | timeout(Duration) | Phát lỗi timeout |
| Kết thúc tại phần tử đầu tiên vượt ngưỡng | takeUntil | Bao gồm phần tử khớp điều kiện |
| Chỉ phát đoạn đầu còn thỏa điều kiện | takeWhile | Loại phần tử đầu tiên không thỏa |
| Lấy mẫu trạng thái theo chu kỳ | sample(Duration) | Có thể bỏ giá trị trung gian |
| Chờ luồng yên lặng rồi phát | debounce(Duration) | Phù hợp tìm kiếm hoặc input |
| Gom phần tử thành batch | buffer(N), bufferTimeout | Giới hạn kích thước và độ trễ batch |
| Điều tiết nhu cầu upstream | limitRate(N) | Không giới hạn tổng số phần tử |
| Nguồn push nhanh hơn consumer | onBackpressureBuffer/Drop/Latest | Chọn theo khả năng mất dữ liệu |

## 12. Tổng kết

Lọc, chuyển đổi và giới hạn dữ liệu ở phía server giúp RSocket chỉ serialize và truyền những payload mà client thực sự cần. filter chọn phần tử, map tạo biểu diễn phù hợp, flatMap và concatMap xử lý bước bất đồng bộ, còn take giới hạn số lượng hoặc thời gian của stream. sample, debounce và buffer thay đổi tần suất hoặc cách đóng gói khi nghiệp vụ cho phép.

limitRate điều tiết demand upstream, trong khi flow control của RSocket quản lý nhu cầu truyền ở tầng giao thức. Với nguồn hot hoặc push, cần chọn buffer có giới hạn, drop hoặc latest và theo dõi overflow. Một pipeline tốt phải cân bằng tính đúng đắn của dữ liệu, thứ tự, độ trễ, băng thông, bộ nhớ và khả năng hủy subscription.
