# Thu nhận dữ liệu IoT và tổng hợp theo cửa sổ thời gian

Trong chương **Mẫu ứng dụng thực tế**, một hệ thống IoT thường nhận telemetry từ hàng nghìn thiết bị với tốc độ và chất lượng kết nối không đồng đều. Thiết bị có thể gửi dữ liệu theo chu kỳ, gửi bù sau khi mất mạng, gửi trùng khi retry hoặc gửi event cũ sau khi reconnect. Ứng dụng serverless cần tiếp nhận luồng dữ liệu, xác thực nguồn gửi, kiểm tra schema, xử lý duplicate và tổng hợp số liệu theo cửa sổ thời gian mà không làm mất dữ liệu hoặc tạo tải đột biến.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Bài toán IoT kết hợp các nội dung này trong một pipeline thực tế: ingest, validate, buffer, aggregate, lưu kết quả và phục vụ truy vấn.

## 1. Bài toán IoT telemetry

Một thiết bị IoT có thể gửi các phép đo như:

- Nhiệt độ, độ ẩm, áp suất.
- Điện áp, dòng điện, công suất.
- Vị trí hoặc trạng thái chuyển động.
- Mức tiêu thụ năng lượng.
- Số lần bật/tắt hoặc trạng thái hoạt động.
- Cảnh báo khi vượt ngưỡng.

Ví dụ một cảm biến nhiệt độ gửi một bản tin mỗi 10 giây. Với 20.000 thiết bị, hệ thống nhận trung bình khoảng 2.000 event mỗi giây. Khi mạng di động hoặc gateway phục hồi, nhiều thiết bị có thể gửi bù dữ liệu đã lưu, khiến lưu lượng tăng đột ngột.

Ứng dụng thường không cần truy vấn mọi phép đo thô để hiển thị dashboard. Nó cần tổng hợp theo phút, theo thiết bị hoặc theo khu vực, ví dụ:

- Nhiệt độ trung bình, nhỏ nhất và lớn nhất mỗi phút.
- Tổng điện năng tiêu thụ mỗi giờ.
- Số lần thiết bị gửi cảnh báo trong một khoảng thời gian.
- Tỷ lệ thiết bị hoạt động theo khu vực.
- Độ trễ giữa thời điểm đo và thời điểm server nhận được dữ liệu.

Một pipeline tốt giữ dữ liệu thô đủ lâu theo policy, tạo aggregate có thể truy vấn nhanh và cho phép phát hiện hoặc sửa sai khi event đến trễ.

## 2. Kiến trúc tổng thể

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    DEV["IoT devices / gateways"] --> ING["IoT ingestion endpoint"]
    ING --> AUTH["Authenticate device and validate envelope"]
    AUTH --> STREAM["Durable stream or queue"]
    STREAM --> PROC["Java Lambda / stream processor"]
    PROC --> DEDUP["Deduplication and event-time window"]
    DEDUP --> RAW["Raw telemetry storage"]
    DEDUP --> AGG["Window aggregate store"]
    AGG --> API["Query API / dashboard"]
    STREAM --> DLQ["DLQ / quarantine"]
    PROC --> OBS["Metrics, logs and traces"]
    RAW --> LAKE["Data lake / offline analysis"]
~~~

Các thành phần có trách nhiệm riêng:

- **Device/gateway:** đo và phát telemetry, có device identity và sequence nếu có.
- **Ingestion endpoint:** xác thực thiết bị, giới hạn tốc độ và kiểm tra kích thước payload.
- **Stream hoặc queue:** hấp thụ burst, giữ event bền vững và tách producer khỏi consumer.
- **Processor:** parse, validate, deduplicate và tính aggregate.
- **Raw storage:** lưu telemetry thô để audit, phân tích hoặc rebuild.
- **Aggregate store:** lưu kết quả theo device, metric và window.
- **Query API:** phục vụ dashboard và ứng dụng.
- **DLQ/quarantine:** giữ event không xử lý được.
- **Observability:** đo ingest rate, lag, late event, lỗi và chi phí.

Không phải hệ thống nào cũng cần mọi thành phần. Với prototype nhỏ, một HTTP endpoint và database có thể đủ. Với fleet lớn, stream bền vững và processor có state thường phù hợp hơn.

## 3. Chọn giao thức và ingestion endpoint

IoT device có thể gửi dữ liệu qua MQTT, HTTP hoặc giao thức riêng qua gateway. Lựa chọn phụ thuộc kết nối, năng lượng, kích thước payload, yêu cầu latency và khả năng của thiết bị.

| Cách ingest | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|
| MQTT | Thiết bị kết nối lâu dài, telemetry nhỏ và thường xuyên | Device identity, topic authorization, QoS, reconnect |
| HTTP | Thiết bị/gateway có thể gửi request độc lập | Authentication, rate limit, request size, retry |
| Gateway protocol adapter | Thiết bị dùng giao thức công nghiệp hoặc mạng riêng | Gateway identity, buffering, mapping schema |
| Stream producer | Gateway hoặc backend đã gom batch | Partition key, throughput, backpressure |

MQTT QoS 1 thường có semantics giao ít nhất một lần, do đó duplicate có thể xảy ra. HTTP client cũng có thể retry sau timeout dù server đã nhận request. Không giả định giao thức sẽ tự bảo đảm mỗi phép đo chỉ xuất hiện một lần.

### 3.1. Xác thực thiết bị

Mỗi thiết bị hoặc gateway cần danh tính riêng. Tùy nền tảng có thể dùng certificate, token ngắn hạn hoặc cơ chế xác thực của IoT broker.

Cần:

- Gắn device identity với tenant/owner.
- Chỉ cho phép thiết bị publish vào topic hoặc resource của chính nó.
- Có quy trình cấp, rotate và revoke credential.
- Không dùng chung một secret cho toàn bộ fleet nếu có thể tránh.
- Giới hạn payload size và request rate.
- Chặn thiết bị bị thu hồi trước khi nhận dữ liệu mới.
- Ghi audit khi identity hoặc quyền truy cập thay đổi.

Không tin deviceId trong payload là bằng chứng xác thực. Server phải đối chiếu device identity đã xác thực với deviceId được khai báo trong event.

## 4. Event envelope cho telemetry

Một event nên chứa metadata đủ để xác định nguồn, thời điểm và thứ tự:

~~~json
{
  "eventId": "evt-thermo-8a71",
  "eventType": "TelemetryMeasured",
  "schemaVersion": 2,
  "tenantId": "tenant-17",
  "deviceId": "sensor-204",
  "sequence": 9182,
  "eventTime": "2026-11-17T10:20:30.250Z",
  "sentAt": "2026-11-17T10:20:31.010Z",
  "metric": "temperature",
  "value": 28.45,
  "unit": "Cel",
  "firmwareVersion": "3.8.1"
}
~~~

Ý nghĩa:

- eventId: định danh ổn định của phép đo hoặc event.
- tenantId/deviceId: phạm vi thiết bị.
- sequence: số thứ tự tăng dần do thiết bị hoặc gateway cấp.
- eventTime: thời điểm phép đo xảy ra.
- sentAt: thời điểm thiết bị gửi event.
- metric/value/unit: loại phép đo, giá trị và đơn vị.
- schemaVersion: phiên bản contract.

Nếu thiết bị không có đồng hồ đáng tin cậy, eventTime có thể sai. Có thể bổ sung receivedAt do ingestion service tạo. Không ghi đè eventTime gốc; giữ cả hai để phân biệt thời điểm đo và thời điểm nhận.

### 4.1. Chuẩn hóa đơn vị

Không cộng hoặc tính trung bình các giá trị khác đơn vị. Ví dụ nhiệt độ Celsius và Fahrenheit phải được chuẩn hóa trước khi aggregate. Điện năng kWh và công suất kW là hai đại lượng khác nhau; không thể cộng trực tiếp.

Schema cần quy định:

- Metric name ổn định.
- Unit chuẩn.
- Kiểu dữ liệu và độ chính xác.
- Miền giá trị hợp lệ.
- Quy tắc chuyển đổi đơn vị.
- Precision và rounding policy.

Với phép tính tài chính hoặc năng lượng yêu cầu độ chính xác, dùng BigDecimal hoặc số nguyên theo đơn vị nhỏ nhất thay vì floating-point tùy tiện. Ví dụ lưu millidegree hoặc milliampere nếu độ phân giải đã được xác định.

## 5. Event time và processing time

Hai khái niệm này không giống nhau:

- **Event time:** thời điểm thiết bị đo hoặc sự việc xảy ra.
- **Processing time:** thời điểm processor thực hiện xử lý.
- **Ingestion time:** thời điểm hệ thống nhận event.

Ví dụ, thiết bị mất kết nối từ 10:00 đến 10:05 và gửi bù phép đo 10:01 vào lúc 10:06. Event time là 10:01, còn ingestion/processing time khoảng 10:06.

Nếu tổng hợp theo processing time, dữ liệu sẽ bị đưa vào cửa sổ 10:06 dù nó phản ánh trạng thái tại 10:01. Với dashboard theo thời điểm đo, cần dùng event time và có chính sách late arrival.

Processing time vẫn hữu ích cho giám sát vận hành, ví dụ đo độ trễ từ lúc server nhận đến lúc xử lý xong. Không dùng một timestamp cho cả hai mục đích.

## 6. Các loại cửa sổ thời gian

Window xác định nhóm event nào được tính cùng nhau. Ba dạng phổ biến:

### 6.1. Tumbling window

Tumbling window có độ dài cố định, không chồng lấn. Ví dụ cửa sổ 1 phút:

- 10:00:00 đến trước 10:01:00.
- 10:01:00 đến trước 10:02:00.
- 10:02:00 đến trước 10:03:00.

Mỗi event thuộc một window cho cùng một metric/key. Loại này phù hợp với số đo theo phút/giờ và báo cáo định kỳ.

### 6.2. Sliding window

Sliding window có độ dài và bước trượt riêng. Ví dụ cửa sổ 5 phút, cập nhật mỗi 1 phút. Hai window liên tiếp chồng lấn nhau.

Loại này phù hợp với rolling average, phát hiện xu hướng hoặc cảnh báo cần cập nhật thường xuyên. Một event có thể thuộc nhiều window nên số phép tính và state tăng lên.

### 6.3. Session window

Session window gom event thành một phiên dựa trên khoảng im lặng. Ví dụ, nếu một thiết bị không gửi dữ liệu trong 15 phút thì phiên telemetry được xem là kết thúc.

Session window phù hợp với phân tích phiên sử dụng hoặc hoạt động theo đợt. Cần định nghĩa gap timeout và cách xử lý event đến muộn có thể nối lại một session tưởng như đã kết thúc.

~~~mermaid
flowchart LR
    subgraph T["Tumbling: 1-minute windows"]
      T1["10:00-10:01"] --> T2["10:01-10:02"] --> T3["10:02-10:03"]
    end
    subgraph S["Sliding: 5-minute window, 1-minute step"]
      S1["10:00-10:05"]
      S2["10:01-10:06"]
      S3["10:02-10:07"]
    end
    subgraph E["Session: 15-minute inactivity gap"]
      E1["Events"] --> E2["Quiet gap"] --> E3["Session closes"]
    end
~~~

## 7. Xác định window key và ranh giới

Một aggregate key thường gồm:

- Tenant ID.
- Device ID hoặc group ID.
- Metric name.
- Window start time.
- Window definition/version.

Ví dụ: tenant-17 / sensor-204 / temperature / 10:20 UTC / 1-minute.

Window key cần ổn định để retry và replay cập nhật đúng aggregate. Nếu thay đổi kích thước window, không được âm thầm dùng cùng key format; cần thêm window specification/version.

Với tumbling window có kích thước W milliseconds, window start được tính:

\[
start = \left\lfloor \frac{eventTimeMillis}{W} \right\rfloor \times W
\]

Window có khoảng nửa mở: start inclusive, end exclusive. Event đúng 10:21:00 thuộc window bắt đầu 10:21, không thuộc window kết thúc tại 10:21.

Dùng UTC để tính window key và lưu timestamp. Chuyển sang timezone địa phương chỉ ở lớp hiển thị; tránh lỗi daylight saving time làm một giờ bị lặp hoặc thiếu.

### 7.1. Ví dụ Java tính tumbling window

~~~java
import java.time.Duration;
import java.time.Instant;

public record TimeWindow(Instant start, Instant end) {
    public static TimeWindow tumbling(
            Instant eventTime,
            Duration windowSize) {

        long sizeMillis = windowSize.toMillis();
        if (sizeMillis <= 0) {
            throw new IllegalArgumentException(
                    "windowSize must be positive");
        }

        long eventMillis = eventTime.toEpochMilli();
        long startMillis =
                Math.floorDiv(eventMillis, sizeMillis) * sizeMillis;

        Instant start = Instant.ofEpochMilli(startMillis);
        return new TimeWindow(start, start.plusMillis(sizeMillis));
    }
}
~~~

Dùng Math.floorDiv để xử lý đúng cả timestamp trước Unix epoch. Ví dụ chỉ phù hợp với window có kích thước nguyên theo millisecond; nếu cần độ phân giải cao hơn, dùng đơn vị thời gian và phép toán phù hợp.

## 8. Watermark và event đến muộn

Trong stream processing, watermark là ước lượng tiến độ event time. Nó cho biết processor tin rằng phần lớn event trước một thời điểm đã được quan sát. Watermark không phải bằng chứng tuyệt đối rằng sẽ không còn event cũ.

Ví dụ, watermark đang ở 10:10. Một event có eventTime 10:07 đến sau đó. Đây là late event so với watermark.

Một processor có thể cho phép lateness thêm 5 phút. Tùy engine, window 10:05-10:10 có thể phát kết quả lần đầu khi watermark đạt cuối window, nhưng vẫn giữ state để nhận event muộn; window chỉ hết thời gian cho phép cập nhật khi watermark vượt qua 10:15. Giá trị lateness cần dựa trên đặc điểm kết nối, buffering của thiết bị và yêu cầu latency của sản phẩm.

Chính sách late event có thể là:

- **Accept and update:** cập nhật lại aggregate nếu window còn trong allowed lateness.
- **Emit correction:** phát bản sửa đổi hoặc revision mới cho aggregate đã công bố.
- **Side output/quarantine:** đưa event quá cũ sang luồng điều tra.
- **Drop with audit:** chỉ bỏ nếu policy cho phép và có metric ghi nhận.

Không âm thầm bỏ event muộn nếu nó ảnh hưởng tới báo cáo hoặc nghĩa vụ nghiệp vụ.

### 8.1. Watermark trong Lambda

Một Lambda invocation độc lập không tự có watermark toàn cục. Nếu mỗi invocation chỉ xử lý một batch, nó không biết liệu các thiết bị khác còn event cũ chưa tới.

Có hai hướng:

1. Dùng stream processing engine có event-time state và watermark.
2. Tự quản lý watermark trong storage bền vững, với quy tắc rõ cho từng partition/key và nguồn tiến độ.

Không lưu watermark trong static field của Java Lambda. Execution environment có thể bị thay thế, scale-out tạo nhiều bản sao và mỗi bản sao sẽ có trạng thái khác nhau.

## 9. Xử lý duplicate và sequence gap

Thiết bị có thể retry sau khi mất ACK, gateway có thể gửi lại batch và stream consumer có thể retry record. Cần eventId ổn định để deduplicate.

Nếu thiết bị có sequence tăng dần, processor có thể phát hiện:

- Sequence nhỏ hơn hoặc bằng sequence đã thấy: có thể là duplicate hoặc event cũ.
- Sequence bằng sequence kế tiếp: event tiếp theo bình thường.
- Sequence nhảy có khoảng trống: có thể mất event hoặc event trước đang đến trễ.
- Sequence reset sau reboot: cần boot/session identifier hoặc epoch để tránh nhầm.

Không chỉ dùng deviceId + sequence nếu sequence có thể reset. Có thể tạo identity từ deviceId + bootId + sequence, hoặc eventId ngẫu nhiên ổn định do thiết bị tạo.

Deduplication retention phải dài ít nhất bằng khoảng retry/replay mà hệ thống hỗ trợ. Nếu xóa dedup record quá sớm, một event được replay sau đó có thể bị tính hai lần.

## 10. Partitioning và hot key

Stream thường chia dữ liệu theo partition key. Một key tốt giúp event cùng thiết bị được xử lý gần nhau và có thể giữ thứ tự trong phạm vi partition. Tuy nhiên, nếu một thiết bị gửi quá nhiều dữ liệu hoặc mọi thiết bị cùng dùng một key, một partition có thể trở thành hot key.

Các lựa chọn:

- Partition theo deviceId khi cần thứ tự trong từng thiết bị.
- Partition theo tenantId nếu cần gom theo tenant, nhưng tenant lớn có thể gây hot partition.
- Thêm shard suffix cho thiết bị có throughput rất cao, nếu có thể chấp nhận xử lý song song và tổng hợp lại.
- Phân phối theo hash của deviceId để cân bằng.
- Tách telemetry và alert thành luồng khác nếu yêu cầu ưu tiên khác nhau.

Không chọn partition key chỉ dựa vào số lượng thiết bị. Cần xem phân bố event rate, kích thước payload và nhu cầu ordering.

## 11. Lưu telemetry thô và aggregate

Thường nên tách dữ liệu thô khỏi kết quả tổng hợp:

| Store | Dữ liệu | Mục đích |
|---|---|---|
| Stream/queue | Event đang chờ xử lý | Buffer, retry và phân phối |
| Raw object storage | Telemetry gốc theo batch/time partition | Audit, replay, offline analytics |
| Aggregate database | Sum/count/min/max theo window | Dashboard và truy vấn nhanh |
| Metadata store | Device registry, calibration, schema | Validation và quản lý thiết bị |
| DLQ/quarantine | Event lỗi | Điều tra và phục hồi |

Không cần giữ mọi raw event trong database phục vụ API nếu khối lượng lớn. Object storage hoặc data lake phù hợp hơn cho dữ liệu lịch sử dung lượng cao; database aggregate phục vụ truy vấn theo key và time range.

Retention của raw data và aggregate có thể khác nhau. Aggregate có thể giữ lâu hơn nếu đã loại bỏ thông tin nhạy cảm và đáp ứng policy.

## 12. Công thức aggregate cơ bản

Với mỗi window và metric, các giá trị phổ biến:

- count: số event hợp lệ.
- sum: tổng giá trị.
- average: sum chia count.
- min/max: giá trị nhỏ nhất/lớn nhất.
- last: giá trị có event time hoặc sequence mới nhất.
- rate: số event hoặc tổng lượng trên một đơn vị thời gian.

Average không nên cộng trực tiếp các average của từng batch nếu batch có số event khác nhau. Cần cộng sum và count rồi tính average cuối:

\[
average = \frac{\sum value_i}{count}
\]

Ví dụ batch A có 10 mẫu trung bình 20°C, batch B có 2 mẫu trung bình 30°C. Trung bình tổng là (10×20 + 2×30)/12 = 21,67°C, không phải (20+30)/2 = 25°C.

Với năng lượng, nếu mỗi event là công suất tức thời, không thể cộng các giá trị công suất rồi gọi đó là điện năng. Cần tích phân theo thời gian hoặc dùng meter reading phù hợp.

### 12.1. Precision và outlier

Không dùng double cho phép tính cần độ chính xác thập phân nghiêm ngặt. Dùng BigDecimal hoặc integer scale cố định. Quy định rounding ở đầu ra.

Cần xác định cách xử lý outlier:

- Giá trị ngoài physical range.
- Sensor báo lỗi hoặc calibration invalid.
- Giá trị lặp bất thường.
- Spike do nhiễu.
- Sensor drift.

Không tự động xóa outlier nếu cần audit. Có thể đánh dấu quality flag, lưu raw value và loại khỏi aggregate theo rule version.

## 13. Ví dụ Java model và validation

Một model telemetry có thể biểu diễn:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record TelemetryEvent(
        String eventId,
        String tenantId,
        String deviceId,
        String bootId,
        long sequence,
        Instant eventTime,
        Instant receivedAt,
        String metric,
        BigDecimal value,
        String unit,
        int schemaVersion) {
}
~~~

Validation cần kiểm tra:

- Device đã đăng ký và chưa bị revoke.
- Tenant trong event khớp với identity đã xác thực.
- Event type và schema version được hỗ trợ.
- Metric/unit thuộc registry cho phép.
- Value nằm trong miền hợp lệ.
- eventTime không quá xa trong tương lai hoặc quá cũ ngoài policy.
- Payload size và sequence hợp lệ.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;

public final class TelemetryValidator {
    private static final Duration MAX_FUTURE_SKEW =
            Duration.ofMinutes(2);

    private TelemetryValidator() {
    }

    public static void validate(
            TelemetryEvent event,
            Instant serverNow) {

        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (event.deviceId() == null || event.deviceId().isBlank()) {
            throw new IllegalArgumentException("Missing deviceId");
        }
        if (event.value() == null) {
            throw new IllegalArgumentException("Missing value");
        }
        if (event.eventTime() == null) {
            throw new IllegalArgumentException("Missing eventTime");
        }
        if (event.eventTime().isAfter(
                serverNow.plus(MAX_FUTURE_SKEW))) {
            throw new IllegalArgumentException("Event time is in future");
        }
        if (event.value().compareTo(new BigDecimal("-80")) < 0
                || event.value().compareTo(new BigDecimal("150")) > 0) {
            throw new IllegalArgumentException(
                    "Temperature outside configured range");
        }
    }
}
~~~

Khoảng -80 đến 150 chỉ là ví dụ cho một loại cảm biến cụ thể. Mỗi metric cần range và calibration policy riêng. Không dùng validation nhiệt độ này cho mọi loại telemetry.

## 14. Cập nhật aggregate an toàn trong DynamoDB

Với tumbling window đơn giản, Lambda có thể cập nhật state trong DynamoDB. Một aggregate item có key gồm tenant, device, metric và windowStart.

Để chống duplicate, có thể dùng TransactWriteItems gồm:

1. Put một dedup item với condition attribute_not_exists.
2. Update aggregate item tăng count và sum.
3. Cả hai thao tác commit hoặc rollback cùng nhau.

Ví dụ update expression khái niệm:

~~~text
SET #sum = if_not_exists(#sum, :zero) + :value,
    #updatedAt = :now
ADD #count :one
~~~

Dedup item và aggregate item phải là hai item khác nhau trong transaction. Nếu điều kiện dedup thất bại, transaction không cập nhật aggregate; consumer coi event là duplicate sau khi xác minh lỗi conditional đúng loại.

Dùng BigDecimal/Number theo precision đã chọn, tránh chuyển giá trị sang binary floating point không cần thiết. Min/max cần conditional logic hoặc stream processor hỗ trợ state; không thể thay bằng phép cộng đơn giản.

### 14.1. State expiry và finalization

Aggregate state không nên bị xóa ngay khi cửa sổ kết thúc nếu vẫn cho phép late event. Giữ state thêm allowed lateness, sau đó finalizer chuyển trạng thái sang FINALIZED bằng conditional update.

DynamoDB TTL có thể dọn item sau khi hết retention, nhưng TTL là bất đồng bộ. Không dùng TTL event để quyết định chính xác thời điểm phát kết quả cuối. Finalizer cần được điều khiển bởi watermark hoặc scheduled sweep có điều kiện.

Nếu late event đến sau finalization, policy có thể tạo correction revision, gửi side output hoặc từ chối có audit. Không sửa aggregate cuối một cách âm thầm nếu consumer downstream đã sử dụng kết quả cũ.

## 15. Khi nào dùng stream processor có state?

Khi cần event-time window, watermark, allowed lateness, session window hoặc state lớn, một stream processing engine thường phù hợp hơn việc tự xây toàn bộ state trong Lambda.

Stream processor có thể cung cấp:

- Event-time timestamp assignment.
- Watermark generation.
- Tumbling/sliding/session window.
- Stateful aggregation.
- Checkpoint và recovery.
- Late-event side output.
- Exactly-once hoặc at-least-once state semantics tùy connector/configuration.

Ví dụ kiến trúc:

- IoT broker đưa telemetry vào Kinesis Data Streams hoặc Kafka.
- Managed stream processor đọc partition.
- Processor gán event time, áp dụng watermark và tính window.
- Aggregate được ghi vào database hoặc data lake.
- Dashboard truy vấn aggregate store.

Cần kiểm tra semantics thực tế của sink. Một processor có checkpoint exactly-once không tự bảo đảm external HTTP side effect được thực hiện đúng một lần nếu sink không tham gia protocol tương ứng.

## 16. Lambda stateless và stateful aggregation

Lambda phù hợp với xử lý event độc lập, validation, enrichment, routing hoặc cập nhật state bền vững. Nhưng một Lambda invocation không phải một stream processor stateful toàn cục.

Không nên:

- Giữ sum/count trong static map và coi đó là aggregate đáng tin cậy.
- Giả định invocation kế tiếp chạy trên cùng execution environment.
- Dùng memory của một instance để phối hợp các thiết bị.
- Finalize window chỉ vì một invocation không thấy event mới.
- Dựa vào thứ tự hoàn tất của Lambda để suy ra event order.

Nếu dùng Lambda, state phải ở DynamoDB, Redis hoặc database bền vững; dedup và aggregate update cần atomic. Nếu yêu cầu event-time phức tạp, dùng stream engine thay vì tự mô phỏng watermark bằng một biến global.

## 17. Batch size, concurrency và backpressure

Batching giúp giảm số invocation nhưng làm tăng lượng dữ liệu mỗi invocation phải xử lý. Batch quá lớn có thể:

- Tăng memory và duration.
- Làm timeout khi có record chậm.
- Tăng blast radius khi batch lỗi.
- Tạo retry lặp lại các record đã xử lý nếu partial failure không bật.
- Làm aggregate key nóng hơn.

Concurrency cao giúp giảm stream lag nhưng có thể làm database quá tải. Cần giới hạn event source mapping concurrency hoặc reserved concurrency theo capacity của aggregate store.

Theo dõi:

- Incoming records per second.
- Iterator age hoặc queue age.
- Concurrent executions.
- Duration p95/p99.
- Throttles và retry.
- Database write throttles/latency.
- DLQ count và oldest event age.

Backpressure có thể thực hiện bằng giảm consumer concurrency, điều tiết producer, queue buffer hoặc rate limiter. Không tăng concurrency khi database đang throttling; điều đó có thể làm tình hình tệ hơn.

## 18. Hot device và skewed traffic

Một số thiết bị có thể gửi nhiều event hơn phần còn lại do firmware bug hoặc chế độ sampling quá nhanh. Nếu partition key chỉ là deviceId, một thiết bị có thể tạo hot partition.

Biện pháp:

- Rate limit theo device và tenant.
- Đặt maximum sample rate.
- Phát hiện sequence tăng bất thường hoặc duplicate burst.
- Dùng quota riêng cho từng tenant.
- Tách luồng alert khỏi telemetry thường.
- Cân nhắc shard suffix cho thiết bị tốc độ cao, sau đó merge aggregate.
- Cảnh báo khi một device chiếm tỷ trọng traffic bất thường.

Không để một thiết bị lỗi làm cạn concurrency hoặc write capacity của toàn bộ fleet.

## 19. Xử lý dữ liệu lỗi và quarantine

Một số event không thể đưa vào aggregate:

- Schema version không hỗ trợ.
- Metric hoặc unit không được phép.
- Device đã revoke.
- Event time quá xa trong tương lai.
- Sequence xung đột.
- Payload hỏng.
- Value ngoài range.
- Tenant/device mismatch.

Phân loại lỗi:

| Loại lỗi | Hành động |
|---|---|
| Lỗi mạng hoặc throttling | Retry có backoff |
| Schema chưa hỗ trợ | Quarantine và nâng consumer/transform |
| Device unauthorized | Từ chối, audit và cảnh báo |
| Payload malformed | DLQ/quarantine |
| Event duplicate | Bỏ qua idempotently, tăng metric |
| Late event trong allowance | Cập nhật/correction |
| Event quá cũ | Side output hoặc bỏ theo policy |
| Sensor value bất thường | Đánh quality flag hoặc quarantine |

Không đưa mọi lỗi vào retry. Event unauthorized hoặc malformed sẽ không tự sửa sau vài lần giao lại.

## 20. Raw data, replay và rebuild aggregate

Aggregate có thể cần tính lại khi:

- Công thức được sửa.
- Calibration được cập nhật.
- Event lỗi được khôi phục.
- Window definition thay đổi.
- Một nhóm event bị thiếu hoặc duplicate.
- Có yêu cầu audit.

Lưu raw event theo retention phù hợp giúp rebuild. Khi replay:

1. Chọn khoảng thời gian và thiết bị/tenant.
2. Chọn phiên bản aggregation logic.
3. Tạo output vào namespace/version mới.
4. Chạy kiểm tra đối soát.
5. So sánh với aggregate hiện tại.
6. Promote kết quả mới khi được xác nhận.

Không replay trực tiếp lên aggregate production mà không có version hoặc dedup strategy. Replay cùng event có thể tăng count/sum lần nữa nếu không reset state hoặc dùng generation key riêng.

Một aggregate key có thể gồm aggregationVersion để cho phép chạy lại logic mới song song với kết quả cũ.

## 21. Phát hiện thiết bị im lặng và dữ liệu thiếu

Một thiết bị không gửi telemetry không nhất thiết là thiết bị đã hỏng. Có thể mất mạng, hết pin, đang bảo trì hoặc chỉ gửi khi có thay đổi.

Có thể định nghĩa heartbeat hoặc expected reporting interval:

- expectedInterval: chu kỳ gửi dự kiến.
- gracePeriod: thời gian cho phép trễ.
- lastSeenAt: lần cuối nhận event hợp lệ.
- status: ONLINE, STALE, OFFLINE hoặc UNKNOWN.

Scheduled function có thể tìm thiết bị quá grace period và phát alert. Cần tránh quét toàn bộ device registry ở mỗi invocation; dùng index theo lastSeenAt hoặc stream cập nhật trạng thái.

Không coi thiếu event là giá trị đo bằng 0. Nếu không có phép đo, aggregate nên biểu diễn count=0 hoặc trạng thái thiếu dữ liệu, không tự điền số 0 vào average.

## 22. Phục vụ truy vấn và dashboard

Dashboard thường truy vấn theo:

- Tenant.
- Device hoặc nhóm thiết bị.
- Metric.
- Khoảng thời gian.
- Granularity (phút, giờ, ngày).

Aggregate store cần key/index hỗ trợ query theo access pattern. Ví dụ partition key theo tenant/device/metric và sort key theo window start. Nếu query toàn tenant, cần một projection tổng hợp theo tenant hoặc khu vực; tránh scan toàn bảng.

API query nên giới hạn time range và số điểm trả về. Nếu người dùng yêu cầu 1 năm dữ liệu ở granularity 1 giây, API nên chọn aggregate coarse hơn hoặc downsample để tránh trả hàng chục triệu điểm.

Có thể giữ nhiều tầng aggregate:

- 1 phút trong vài ngày.
- 1 giờ trong vài tháng.
- 1 ngày trong thời gian dài hơn.

Thời hạn cụ thể phải dựa trên policy và chi phí storage.

## 23. Bảo mật và quyền riêng tư của dữ liệu IoT

Telemetry có thể tiết lộ vị trí, lịch sinh hoạt, trạng thái nhà máy hoặc hành vi người dùng. Cần:

- Xác thực từng device/gateway.
- IAM least privilege cho ingestion và processor.
- Mã hóa khi truyền và lưu.
- Không log raw payload nếu có dữ liệu nhạy cảm.
- Tách tenant data bằng key/partition và authorization.
- Quản lý certificate/token rotation và revoke.
- Giới hạn retention raw telemetry.
- Audit truy cập và export.
- Không đưa device secret vào event.
- Bảo vệ command channel riêng với telemetry ingest.

Telemetry ingest và device command là hai luồng quyền khác nhau. Một thiết bị được phép publish số đo không mặc nhiên được phép nhận lệnh điều khiển.

## 24. Chi phí của pipeline IoT

Các nguồn chi phí:

- MQTT/API ingestion request.
- Stream shard/throughput hoặc queue request.
- Lambda invocation và GB-seconds.
- Stateful stream processing capacity.
- DynamoDB write/read và storage.
- Object storage raw telemetry.
- Logs, metrics và traces.
- Data transfer.
- DLQ, archive và replay.
- Query API và dashboard.

Chi phí tăng theo số thiết bị, tần suất sampling, payload size, retention và số lần retry. Giảm sampling có thể giảm chi phí nhưng cũng làm giảm khả năng phát hiện sự kiện ngắn. Cần cân bằng yêu cầu sản phẩm với chi phí.

Một số biện pháp:

- Batch telemetry ở gateway khi phù hợp.
- Nén payload nếu thiết bị và backend hỗ trợ.
- Loại field không cần thiết.
- Dùng stream/queue có throughput phù hợp.
- Chỉ log metadata cần thiết.
- Aggregate sớm nhưng vẫn giữ raw theo policy.
- Tách hot/cold data.
- Giới hạn replay và retry.
- Dùng sampling cho tracing ở lưu lượng cao.

Không tối ưu chi phí bằng cách bỏ qua raw event nếu nghiệp vụ cần audit hoặc rebuild. Hãy xác định retention và khả năng tái tính toán trước khi giảm dữ liệu lưu.

## 25. Kiểm thử hệ thống IoT

Các test quan trọng:

- Event hợp lệ từ device đã xác thực.
- Device bị revoke nhưng vẫn gửi.
- Payload schema cũ và schema mới.
- Duplicate event cùng eventId.
- Event sequence đến sai thứ tự.
- Event time lệch đồng hồ.
- Event đến sau allowed lateness.
- Burst khi nhiều gateway reconnect.
- Một device tạo hot key.
- Database throttling hoặc stream lag.
- Lambda timeout giữa dedup và aggregate update.
- Replay cùng raw dataset.
- Window boundary đúng tại đầu/cuối window.
- Chuyển timezone hiển thị nhưng window vẫn tính UTC.
- Thiết bị ngừng gửi heartbeat.
- DLQ redrive sau khi sửa consumer.

Kiểm thử aggregation cần xác minh sum/count/average và window membership. Ví dụ event tại đúng 10:01:00 phải thuộc window [10:01, 10:02), không thuộc [10:00, 10:01).

Với hệ thống lớn, chạy load test có phân bố traffic thực tế, bao gồm một số device gửi nhanh hơn phần còn lại. Đo throughput, lag, p95/p99, throttling, database write capacity và cost.

## 26. Quy trình triển khai từng bước

Một lộ trình triển khai thực tế:

1. Định nghĩa metric, unit, schema và event identity.
2. Đăng ký device identity và authorization.
3. Chọn ingestion protocol và durable buffer.
4. Chọn partition key theo ordering và throughput.
5. Lưu raw telemetry theo policy.
6. Chọn window type và event-time semantics.
7. Chọn stream processor hoặc Lambda + state store.
8. Thiết kế deduplication và late-event policy.
9. Tạo aggregate store và query access pattern.
10. Cấu hình retry, DLQ và replay.
11. Thiết lập dashboard, alert và cost metrics.
12. Load test, chaos test và kiểm tra data correctness.
13. Canary theo một nhóm device.
14. Mở rộng fleet và theo dõi lag/hot key.
15. Ghi lại aggregation version và quy trình rebuild.

Không triển khai toàn bộ fleet cùng lúc khi chưa biết capacity. Canary một nhóm thiết bị giúp đo event rate, payload distribution và lỗi thực tế trước khi mở rộng.

## 27. Những lỗi thường gặp

**Dùng processing time thay event time:** Event gửi bù bị tính vào sai cửa sổ. Giữ timestamp đo và timestamp nhận riêng.

**Dùng static map trong Lambda làm aggregate store:** State không chia sẻ giữa execution environment và có thể mất. Dùng database bền vững hoặc stream processor có state.

**Không deduplicate:** Retry làm sum/count tăng nhiều lần. Dùng eventId và atomic dedup + aggregate update.

**Dùng timestamp để suy ra thứ tự:** Đồng hồ thiết bị lệch. Dùng sequence hoặc version khi có thể.

**Chọn một partition key cho mọi traffic:** Hot device/tenant làm nghẽn partition. Phân tích traffic skew và shard phù hợp.

**Đóng window quá sớm:** Event đến muộn bị bỏ. Dùng watermark và allowed lateness hoặc correction policy.

**Dùng TTL để finalization:** TTL cleanup bất đồng bộ. Dùng watermark hoặc finalizer có điều kiện.

**Average của average:** Kết quả sai khi batch có số lượng mẫu khác nhau. Cộng sum và count rồi chia.

**Cộng công suất thành điện năng:** Sai đơn vị vật lý. Tích phân theo thời gian hoặc dùng meter reading.

**Replay trực tiếp lên aggregate hiện tại:** Count/sum bị nhân đôi. Dùng aggregation version hoặc rebuild namespace riêng.

**Không phân biệt thiếu dữ liệu với giá trị zero:** Dashboard hiển thị sai. Lưu count và data quality status.

**Tăng concurrency khi database throttling:** Tạo thêm tải và lag. Điều tiết worker theo downstream capacity.

**Log toàn bộ telemetry:** Lộ dữ liệu và tăng chi phí. Log metadata đã lọc.

## 28. Checklist production

- [ ] Device identity được xác thực và gắn đúng tenant.
- [ ] Device chỉ publish vào topic/resource được phép.
- [ ] Event envelope có eventId, eventTime, receivedAt, schemaVersion và unit.
- [ ] Có sequence/boot ID nếu cần phát hiện gap và reset.
- [ ] Metric và unit được chuẩn hóa.
- [ ] Event time và processing time được phân biệt.
- [ ] Window type, size, step và timezone được định nghĩa.
- [ ] Có watermark/allowed lateness hoặc late-event policy rõ ràng.
- [ ] Deduplication và aggregate update được thực hiện atomic.
- [ ] State tổng hợp nằm trong storage bền vững.
- [ ] Partition key được kiểm tra hot key và traffic skew.
- [ ] Raw telemetry có retention và encryption policy.
- [ ] DLQ/quarantine có owner và redrive runbook.
- [ ] Batch size và concurrency phù hợp downstream capacity.
- [ ] Có metric ingest rate, lag, late event, duplicate và window completion.
- [ ] Có kiểm thử window boundary và replay.
- [ ] Có quy trình rebuild aggregate theo version.
- [ ] Dashboard phân biệt missing data với zero.
- [ ] Log không chứa credential hoặc payload nhạy cảm.
- [ ] Có load test và canary trước khi mở rộng toàn fleet.
- [ ] Có cost metric theo device, event và aggregate window.

## Kết luận

Pipeline IoT serverless cần xác thực thiết bị, chuẩn hóa event envelope, buffer dữ liệu bền vững và xử lý event theo thời gian đo. Tumbling, sliding và session window phục vụ các kiểu tổng hợp khác nhau; event-time watermark và allowed lateness giúp xử lý dữ liệu gửi bù hoặc đến trễ. Duplicate phải được kiểm soát bằng event identity và cập nhật aggregate atomic.

Java Lambda phù hợp với validation, routing và aggregation đơn giản có state lưu bên ngoài. Với luồng lớn hoặc yêu cầu window phức tạp, stream processor có state thường phù hợp hơn. Không dùng memory của execution environment làm nguồn trạng thái; cần theo dõi lag, hot key, late event, retry, DLQ và cost. Khi raw data, aggregate version và replay policy được thiết kế ngay từ đầu, hệ thống có thể mở rộng số thiết bị mà vẫn giữ kết quả đúng và có thể kiểm chứng.

