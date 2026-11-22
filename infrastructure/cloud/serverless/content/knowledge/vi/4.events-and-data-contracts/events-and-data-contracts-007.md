# Event time, processing time và sự kiện đến muộn

Trong kiến trúc serverless, một event có thể được phát sinh ở một thời điểm, đi qua mạng hoặc hàng đợi trong một khoảng thời gian, rồi mới kích hoạt Java function. Vì vậy, thời điểm nghiệp vụ xảy ra và thời điểm function xử lý event thường không giống nhau. Nếu dùng nhầm hai mốc thời gian, hệ thống có thể thống kê sai doanh thu theo ngày, đóng cửa sổ tổng hợp quá sớm hoặc bỏ qua một giao dịch hợp lệ chỉ vì message đến trễ.

Bài học này giải thích cách phân biệt event time, processing time và thời điểm tiếp nhận event; cách hiểu sự kiện đến muộn và sự kiện không đúng thứ tự; cũng như cách thiết kế hợp đồng dữ liệu, cửa sổ thời gian và chính sách xử lý phù hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt event time, ingestion/arrival time và processing time.
- Giải thích vì sao event có thể đến trễ hoặc không theo thứ tự phát sinh.
- Hiểu cửa sổ thời gian và watermark trong xử lý luồng.
- Chọn chính sách xử lý late event theo yêu cầu nghiệp vụ.
- Thiết kế event contract giữ nguyên thời điểm nghiệp vụ và metadata xử lý.
- Viết Java function đo độ trễ mà không làm thay đổi timestamp gốc của event.

## 1. Ba mốc thời gian trong một luồng event

Khi một sự kiện được tạo ra và xử lý qua nhiều dịch vụ, cần phân biệt ít nhất ba mốc thời gian.

| Mốc thời gian | Ý nghĩa | Ai thường ghi nhận? |
|---|---|---|
| **Event time** | Thời điểm sự việc nghiệp vụ thực sự xảy ra | Hệ thống hoặc thiết bị phát sinh sự kiện |
| **Ingestion / arrival time** | Thời điểm broker, gateway hoặc nền tảng tiếp nhận event | Queue, event bus, API gateway hoặc adapter |
| **Processing time** | Thời điểm consumer bắt đầu hoặc thực hiện xử lý event | Java function hoặc bộ xử lý luồng |

Một số hệ thống còn có **publication time**: thời điểm producer gửi event đi. Publication time có thể khác event time nếu ứng dụng ghi nhận sự việc trước nhưng chỉ gửi event sau đó. Không nên tự coi timestamp do broker gán là event time; hai mốc này phục vụ các mục đích khác nhau.

### Ví dụ: đơn hàng được tạo khi thiết bị ngoại tuyến

Một nhân viên bán hàng tạo đơn lúc 10:02 khi máy tính bảng đang mất kết nối. Ứng dụng lưu đơn cục bộ và đồng bộ lên cloud lúc 10:17. Queue nhận message lúc 10:17:01 và function bắt đầu xử lý lúc 10:17:02.

| Mốc | Thời điểm |
|---|---|
| Event time — đơn hàng được tạo | 10:02:00 |
| Publication time — ứng dụng gửi event | 10:17:00 |
| Ingestion time — queue nhận message | 10:17:01 |
| Processing time — function bắt đầu | 10:17:02 |

Nếu báo cáo doanh thu theo giờ dùng processing time, đơn hàng sẽ bị tính vào khoảng 10:15–10:30 dù nghiệp vụ xảy ra lúc 10:02. Với dashboard theo dõi tải của function, processing time lại là mốc phù hợp vì nó cho biết khi nào nền tảng thực sự làm việc.

**Quy tắc thực hành:** dùng event time cho câu hỏi nghiệp vụ “việc gì đã xảy ra khi nào”; dùng processing time cho câu hỏi vận hành “hệ thống đã xử lý khi nào”; dùng ingestion time để đo thời gian chờ từ lúc nền tảng nhận dữ liệu đến khi consumer xử lý.

## 2. Event time và processing time tạo ra hai cách nhìn khác nhau

Hãy xét một luồng event giao dịch. Có hai cách tổng hợp số giao dịch trong mỗi khoảng năm phút.

- **Theo event time:** giao dịch được xếp vào cửa sổ chứa thời điểm giao dịch thực sự xảy ra. Đây là cách phù hợp với báo cáo nghiệp vụ, thống kê hoạt động tại cửa hàng hoặc phân tích hành vi.
- **Theo processing time:** giao dịch được xếp vào cửa sổ mà function hoặc stream processor xử lý nó. Đây là cách phù hợp để đo throughput, tải tiêu thụ, năng lực xử lý và độ trễ vận hành.

Hai kết quả có thể khác nhau đáng kể khi producer ngoại tuyến, mạng chậm, queue tồn đọng hoặc hệ thống đang retry nhiều lần.

Ví dụ, 100 event có event time trong khoảng 10:00–10:05 nhưng đến queue trong khoảng 10:10–10:15. Báo cáo nghiệp vụ theo event time ghi nhận 100 giao dịch ở cửa sổ đầu. Dashboard processing time cho thấy 100 lần xử lý ở cửa sổ sau. Cả hai đều đúng vì chúng trả lời hai câu hỏi khác nhau.

### Không thay event time bằng thời điểm function chạy

Một lỗi thường gặp là function nhận event cũ nhưng ghi đè timestamp bằng thời gian hiện tại. Khi đó hệ thống mất thông tin về thời điểm nghiệp vụ thực sự xảy ra. Việc này làm sai báo cáo, gây khó khăn cho điều tra sự cố và khiến việc phát lại dữ liệu không thể tái tạo kết quả ban đầu.

Hãy giữ timestamp gốc bất biến trong event. Consumer có thể bổ sung metadata như receivedAt, processingStartedAt và processedAt trong log hoặc bản ghi xử lý riêng.

## 3. Vì sao event đến muộn hoặc không đúng thứ tự?

Trong hệ thống phân tán, thứ tự event được tạo ra không đảm bảo là thứ tự consumer nhận được. Một số nguyên nhân phổ biến:

1. **Thiết bị hoặc ứng dụng ngoại tuyến:** event được lưu cục bộ rồi gửi lên khi có mạng.
2. **Độ trễ mạng:** event đi qua các vùng địa lý, gateway hoặc dịch vụ trung gian có thời gian truyền khác nhau.
3. **Queue và partition:** message được phân vùng hoặc xử lý song song; các consumer hoàn thành với tốc độ khác nhau.
4. **Batching và backpressure:** nền tảng gom nhiều event hoặc bị chậm do tải cao, khiến event chờ lâu trước khi được xử lý.
5. **Retry và redelivery:** một message lỗi hoặc hết thời hạn xác nhận có thể được giao lại sau những message mới hơn.
6. **Replay và backfill:** đội vận hành chủ động phát lại dữ liệu lịch sử để sửa lỗi hoặc tái tạo báo cáo.
7. **Sai lệch đồng hồ:** đồng hồ trên thiết bị hoặc máy chủ producer có thể chạy nhanh, chậm hoặc chưa đồng bộ.

Cần phân biệt ba hiện tượng:

- **Out-of-order event:** event đến theo thứ tự khác với event time. Ví dụ, event lúc 10:04 được xử lý trước event lúc 10:03.
- **Late event:** event đến sau thời điểm mà bộ xử lý đã coi một khoảng dữ liệu là tương đối hoàn tất, thường được xác định bằng watermark và chính sách allowed lateness.
- **Duplicate event:** cùng một sự kiện được giao hoặc xử lý nhiều lần. Duplicate có thể đến đúng hạn hoặc đến muộn; đây là vấn đề khác với thứ tự.

Một event đến sau event khác chưa chắc đã là late theo chính sách xử lý. Nếu watermark chưa đi qua cửa sổ liên quan, processor vẫn có thể nhận event out-of-order và cập nhật kết quả bình thường.

### Timestamp cũng có thể sai

Event time do producer cung cấp chỉ đáng tin khi producer có quy tắc ghi nhận rõ ràng. Thiết bị sai đồng hồ có thể gửi event time nằm trong tương lai hoặc quá xa trong quá khứ. Vì vậy, hợp đồng dữ liệu cần quy định:

- Timestamp biểu thị thời điểm nào trong nghiệp vụ.
- Ai tạo timestamp và đồng hồ được đồng bộ ra sao.
- Định dạng, múi giờ và độ chính xác.
- Khoảng sai lệch cho phép và cách xử lý timestamp bất hợp lệ.

Đối với hệ thống cloud, nên trao đổi timestamp dưới dạng UTC, ví dụ ISO 8601 với ký hiệu Z, hoặc epoch có đơn vị được quy định rõ. Trong Java, Instant là kiểu phù hợp để biểu diễn một thời điểm tuyệt đối. Tránh dùng LocalDateTime đơn lẻ cho event xuyên vùng địa lý vì kiểu này không chứa offset hoặc timezone. Nếu báo cáo theo ngày làm việc tại một quốc gia, hãy chuyển Instant sang ZoneId nghiệp vụ ở lớp báo cáo; không thay timestamp gốc bằng giờ địa phương. Quy tắc này cũng giúp xử lý đúng ngày có thay đổi giờ mùa hè.

## 4. Cửa sổ thời gian trong xử lý event

Khi cần tính tổng, đếm hoặc thống kê theo khoảng thời gian, bộ xử lý thường gom event vào các **time window**.

| Loại cửa sổ | Cách hoạt động | Ví dụ |
|---|---|---|
| Tumbling window | Các cửa sổ cố định, liên tiếp và không chồng lấn | 10:00–10:05, 10:05–10:10 |
| Sliding window | Cửa sổ có độ dài cố định nhưng trượt theo bước nhỏ hơn, nên có thể chồng lấn | Cửa sổ 10 phút cập nhật mỗi phút |
| Session window | Gom event thành phiên theo hoạt động; phiên kết thúc sau một khoảng không có event | Một phiên mua sắm kết thúc sau 30 phút không hoạt động |

Cửa sổ theo event time gom theo timestamp của sự kiện. Cửa sổ theo processing time gom theo thời điểm processor quan sát hoặc xử lý event. Chọn sai loại cửa sổ sẽ khiến kết quả không khớp với mục tiêu đo lường.

### Ví dụ cửa sổ tumbling theo event time

Giả sử hệ thống đếm đơn hàng theo từng cửa sổ năm phút:

- Cửa sổ A: 10:00 đến trước 10:05.
- Cửa sổ B: 10:05 đến trước 10:10.
- Một đơn hàng có event time là 10:04:30 thuộc cửa sổ A, dù function chỉ nhận nó lúc 10:12.

Cần xác định rõ quy ước biên cửa sổ, ví dụ cửa sổ bao gồm thời điểm bắt đầu và không bao gồm thời điểm kết thúc. Quy ước này tránh một event đúng 10:05 bị tính vào cả hai cửa sổ hoặc không thuộc cửa sổ nào.

## 5. Watermark và allowed lateness

Một hệ thống xử lý event time cần cách ước lượng khi nào dữ liệu của một khoảng thời gian đã tương đối đầy đủ. **Watermark** là tín hiệu ước lượng tiến độ event time: processor cho rằng những event có timestamp nhỏ hơn một mốc nhất định có khả năng đã đến phần lớn.

Watermark không phải bằng chứng rằng sẽ không bao giờ còn event cũ hơn. Một thiết bị có thể đồng bộ lại sau nhiều giờ, một queue có thể tồn đọng, hoặc đội vận hành có thể replay dữ liệu lịch sử. Watermark là cơ chế điều phối tính toán dựa trên giả định về độ trễ, không phải cam kết tuyệt đối của nguồn event.

**Allowed lateness** là khoảng trễ mà hệ thống cho phép tiếp tục nhận và cập nhật kết quả cho một cửa sổ sau khi watermark đã đi qua mốc kết thúc theo quy tắc của processor.

Ví dụ minh họa:

- Cửa sổ nghiệp vụ kết thúc lúc 10:05.
- Watermark đã đi qua 10:05, nên processor có thể phát kết quả ban đầu.
- Chính sách cho phép trễ thêm 10 phút.
- Event có event time 10:04 đến lúc 10:09 vẫn có thể cập nhật kết quả của cửa sổ A.
- Sau thời hạn cho phép, event có thể bị loại, chuyển sang luồng riêng hoặc tạo một bản hiệu chỉnh tùy chính sách.

Chi tiết thời điểm đóng cửa sổ, giữ state và xử lý event quá hạn khác nhau giữa các stream processor và dịch vụ cloud. Cần đọc semantics của nền tảng cụ thể. Một queue-triggered function thông thường không tự có watermark hay event-time window; nếu cần những cơ chế đó, ứng dụng phải dùng stream processing service hoặc tự quản lý trạng thái và tiến độ xử lý.

### Minh họa tiến trình watermark

~~~mermaid
flowchart LR
    A["Event time của dữ liệu"] --> B["Gom event vào cửa sổ"]
    B --> C["Watermark đi qua cuối cửa sổ"]
    C --> D["Phát kết quả ban đầu"]
    D --> E["Nhận late event trong allowed lateness"]
    E --> F["Cập nhật hoặc phát bản hiệu chỉnh"]
    D --> G["Hết thời hạn cho phép"]
    G --> H["Đóng state / chuyển event quá hạn"]
~~~

Không nên chọn allowed lateness chỉ để làm cho số liệu trông đầy đủ. Khoảng này cần dựa trên phân bố độ trễ thực tế, yêu cầu thời gian phản hồi và chi phí giữ state. Cửa sổ giữ càng lâu có thể cần nhiều bộ nhớ hoặc dung lượng lưu trữ hơn và làm chậm thời điểm kết quả được xem là cuối cùng.

## 6. Chọn chính sách xử lý sự kiện đến muộn

Không có một chính sách late-event đúng cho mọi nghiệp vụ. Hãy xác định độ chính xác cần thiết, thời gian chờ chấp nhận được và khả năng sửa kết quả đã phát ra.

| Chính sách | Cách thực hiện | Phù hợp khi | Rủi ro hoặc chi phí |
|---|---|---|---|
| Chấp nhận và cập nhật | Mở state cửa sổ thêm một thời gian, cập nhật tổng hoặc số đếm | Báo cáo cần chính xác và event thường chỉ trễ ngắn | Kết quả có thể thay đổi sau khi đã hiển thị |
| Phát bản hiệu chỉnh | Giữ kết quả đã phát và phát correction/retraction khi có event muộn | Downstream cần biết kết quả thay đổi | Consumer phải hiểu phiên bản hoặc thao tác bù |
| Chuyển sang luồng riêng | Ghi event quá hạn vào DLQ hoặc late-event topic để xử lý sau | Cần điều tra, đối soát hoặc backfill | Cần quy trình vận hành và replay |
| Bỏ qua event quá hạn | Không thay đổi kết quả, chỉ ghi metric và log | Dashboard gần thời gian thực ưu tiên độ trễ thấp, dữ liệu có thể xấp xỉ | Kết quả nghiệp vụ có thể thiếu |
| Tính lại dữ liệu lịch sử | Chạy batch hoặc backfill để tái tạo kết quả | Báo cáo tài chính hoặc dữ liệu cần độ chính xác cao | Tốn tài nguyên và cần quản lý phiên bản kết quả |

### Chọn theo yêu cầu nghiệp vụ

- **Dashboard vận hành:** có thể chấp nhận số liệu gần đúng trong vài phút, miễn là hiển thị thời điểm cập nhật cuối và có cảnh báo độ trễ.
- **Báo cáo doanh thu:** cần quy tắc đối soát và khả năng hiệu chỉnh; không nên âm thầm bỏ giao dịch chỉ vì đến muộn.
- **Phát hiện gian lận:** cần cân bằng tốc độ cảnh báo với việc bổ sung bằng chứng đến sau. Một quyết định ban đầu có thể được cập nhật khi nhận thêm event.
- **Thông báo cho khách hàng:** cần tránh gửi lại thông báo hoặc thực hiện tác dụng phụ trùng lặp khi event cũ được replay.

Một lựa chọn thực tế là phát kết quả sơ bộ sớm, sau đó cho phép cập nhật trong một khoảng allowed lateness đã xác định. Với nghiệp vụ cần số liệu cuối cùng, có thể chạy đối soát hoặc batch backfill sau thời điểm chốt.

## 7. Thiết kế event contract để giữ đúng ngữ nghĩa thời gian

Event contract nên nói rõ timestamp nào là thời điểm nghiệp vụ, timestamp nào do hạ tầng thêm vào và consumer phải hiểu chúng ra sao.

Một event đơn hàng có thể chứa:

~~~json
{
  "eventId": "evt-8f31",
  "eventType": "OrderPlaced",
  "occurredAt": "2026-11-17T03:02:00Z",
  "publishedAt": "2026-11-17T03:17:00Z",
  "data": {
    "orderId": "ORD-1042",
    "total": 1250000,
    "currency": "VND"
  }
}
~~~

Trong ví dụ, occurredAt là event time; publishedAt là thời điểm producer gửi event. Ingestion time và processing time thường do broker hoặc consumer ghi nhận, không nhất thiết phải được producer đưa vào payload. Nếu nhiều consumer cùng dùng event, mỗi consumer có processing time riêng.

Các nguyên tắc thiết kế:

1. **Giữ eventId ổn định:** retry và replay phải giữ cùng định danh của sự kiện gốc để consumer có thể deduplicate.
2. **Giữ occurredAt bất biến:** không thay bằng thời điểm publish, enqueue hoặc function chạy.
3. **Định nghĩa rõ timestamp:** tên trường phải thể hiện ý nghĩa; tránh một trường chung chung tên timestamp mà không có hợp đồng.
4. **Dùng UTC và định dạng thống nhất:** xác định rõ ISO 8601 hay epoch milliseconds/seconds; không trộn đơn vị.
5. **Lưu nguồn timestamp khi cần:** nếu event đến từ thiết bị, có thể lưu source hoặc clock metadata để đánh giá độ tin cậy.
6. **Tách metadata giao nhận:** deliveryAttempt, receivedAt và processedAt thuộc ngữ cảnh xử lý; không sửa event nghiệp vụ gốc.
7. **Quy định cách xử lý timestamp bất hợp lệ:** event có thời điểm tương lai quá xa hoặc quá cũ cần được quarantine, cảnh báo hoặc xác minh theo nghiệp vụ.

Với dữ liệu cần kiểm toán, có thể lưu event gốc bất biến và lưu kết quả xử lý hoặc bản hiệu chỉnh ở bản ghi riêng. Nhờ đó, hệ thống giữ được lịch sử nguồn và giải thích được vì sao số liệu hiện tại khác với kết quả đã phát trước đó.

## 8. Ví dụ Java: đo độ trễ mà không ghi đè event time

Ví dụ sau minh họa event contract và cách function ghi nhận thời điểm xử lý. Event time đến từ producer; processing time được lấy từ Clock của consumer. Ngưỡng 10 phút chỉ là ngưỡng cảnh báo độ trễ vận hành, không phải watermark hay định nghĩa đầy đủ về late event trong stream processor.

Ví dụ dùng Java record (Java 16 trở lên).

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public record OrderPlaced(
        String eventId,
        String orderId,
        Instant occurredAt,
        Instant publishedAt,
        BigDecimal total,
        String currency) {
}

public record ProcessingObservation(
        Instant processingTime,
        Duration eventAge,
        boolean exceedsOperationalDelay,
        boolean producerClockAhead) {
}

public final class OrderEventHandler {
    private static final Duration MAX_OPERATIONAL_DELAY =
            Duration.ofMinutes(10);
    private static final Duration MAX_FUTURE_SKEW =
            Duration.ofSeconds(30);

    private final Clock clock;

    public OrderEventHandler(Clock clock) {
        this.clock = clock;
    }

    public ProcessingObservation handle(OrderPlaced event) {
        Instant processingTime = clock.instant();

        if (event.occurredAt() == null) {
            throw new IllegalArgumentException("occurredAt is required");
        }

        if (event.occurredAt().isAfter(
                processingTime.plus(MAX_FUTURE_SKEW))) {
            throw new IllegalArgumentException(
                    "occurredAt is too far in the future");
        }

        Duration rawEventAge =
                Duration.between(event.occurredAt(), processingTime);
        boolean producerClockAhead = rawEventAge.isNegative();
        Duration eventAge = producerClockAhead
                ? Duration.ZERO
                : rawEventAge;

        boolean delayed =
                eventAge.compareTo(MAX_OPERATIONAL_DELAY) > 0;

        // Lưu observation vào log/metric; không thay đổi event.occurredAt().
        return new ProcessingObservation(
                processingTime, eventAge, delayed, producerClockAhead);
    }
}
~~~

Ở môi trường thực tế, adapter của function cần chuyển event từ HTTP, queue hoặc event source thành OrderPlaced. Clock nên được inject để unit test có thể cố định thời gian. Nếu event time chỉ nhanh hơn processing clock trong giới hạn sai lệch cho phép, ví dụ trên, observation đánh dấu producerClockAhead và đặt eventAge đo lường về 0; timestamp gốc vẫn được giữ nguyên. Event vượt quá giới hạn cần được phân loại thành lỗi dữ liệu và chuyển đến luồng xử lý phù hợp. Nếu cứ ném exception khiến nguồn retry vô hạn, hệ thống có thể tạo thêm tải mà không sửa được dữ liệu.

### Đo độ trễ nào?

Có thể theo dõi các khoảng sau nếu các timestamp được ghi nhận đáng tin cậy:

- **Event age:** processingTime trừ occurredAt. Cho biết event đã cũ bao lâu khi consumer xử lý.
- **Producer delay:** publishedAt trừ occurredAt. Cho biết producer mất bao lâu từ lúc sự việc xảy ra đến lúc phát event.
- **Queue wait:** processingStartedAt trừ receivedAt/enqueuedAt. Cho biết event chờ bao lâu trước khi consumer bắt đầu.
- **Execution duration:** processedAt trừ processingStartedAt. Cho biết function xử lý trong bao lâu.

Không nên cộng hoặc so sánh các timestamp từ đồng hồ không đồng bộ mà không tính đến clock skew. Đối với đo thời lượng bên trong một process, monotonic clock hoặc công cụ đo duration phù hợp đáng tin cậy hơn việc trừ hai wall-clock timestamp có thể bị điều chỉnh.

## 9. Retry, replay và idempotency với late event

Late event và retry thường xuất hiện cùng nhau nhưng cần được xử lý riêng.

- **Retry:** cùng một message được giao lại vì lần xử lý trước thất bại hoặc không xác nhận đúng hạn.
- **Replay:** event cũ được phát lại có chủ đích để khôi phục hoặc tái tạo kết quả.
- **Late arrival:** event lần đầu đến consumer sau khi watermark đã đi qua vị trí event time của nó theo quy tắc cửa sổ và chính sách lateness.

Trong cả ba trường hợp, event time gốc và eventId cần được giữ nguyên. Consumer có thể ghi deliveryAttempt, replayRunId hoặc receivedAt ở metadata riêng. Nếu mỗi lần retry lại thay occurredAt bằng thời điểm hiện tại, hệ thống sẽ biến một event cũ thành event mới về mặt thời gian và làm sai kết quả tổng hợp.

Để xử lý an toàn:

1. Dùng eventId hoặc business key làm khóa idempotency.
2. Lưu trạng thái đã xử lý cùng kết quả nghiệp vụ trong một thao tác nguyên tử nếu có thể.
3. Tách lỗi dữ liệu vĩnh viễn khỏi lỗi hạ tầng có thể retry.
4. Xác định replay có được cập nhật kết quả hiện tại hay chỉ phục vụ kiểm tra.
5. Nếu kết quả đã được phát ra downstream, dùng version hoặc correction event để thể hiện thay đổi.
6. Ghi nhận event bị bỏ qua, đưa vào DLQ hoặc quá hạn để có thể đối soát.

Idempotency bảo vệ tác dụng phụ khỏi việc xử lý lặp, nhưng không tự giải quyết bài toán cập nhật cửa sổ thời gian. Một event có thể được xử lý đúng một lần mà vẫn đến sau khi báo cáo đã chốt; khi đó cần chính sách late-event riêng.

## 10. Kiểm thử các tình huống thời gian

Unit test chỉ dùng event đến đúng thứ tự và cùng thời điểm với processing time sẽ bỏ sót nhiều lỗi. Hãy tạo test case có timestamp cố định để tái hiện các tình huống:

| Tình huống | Dữ liệu kiểm thử | Điều cần xác minh |
|---|---|---|
| Event đến đúng lúc | occurredAt gần processingTime | Được xếp vào cửa sổ đúng |
| Event đến muộn | occurredAt cũ hơn processingTime đáng kể | Đo đúng event age và áp dụng chính sách late |
| Event out-of-order | Nhận event 10:04 trước event 10:03 | Cửa sổ event time được cập nhật đúng |
| Duplicate | Gửi lại cùng eventId | Không lặp tác dụng phụ |
| Timestamp tương lai | occurredAt vượt quá clock skew cho phép | Được quarantine hoặc xử lý lỗi dữ liệu |
| Replay lịch sử | Event cũ được phát lại có chủ đích | Không bị nhầm thành event mới; kết quả được version/correction đúng |
| Ranh giới cửa sổ | occurredAt đúng thời điểm kết thúc cửa sổ | Theo đúng quy ước biên đã công bố |
| Múi giờ và ngày chuyển mùa | Sự kiện từ nhiều timezone | Báo cáo UTC và giờ địa phương nhất quán |

Với Java, dùng Clock.fixed trong unit test để cố định processing time. Kiểm thử integration cần xác minh semantics thật của queue hoặc stream processor: retry, ordering, watermark, thời gian lưu state và DLQ có thể khác với emulator cục bộ.

## 11. Checklist thiết kế thời gian cho event-driven function

- [ ] Event contract định nghĩa rõ occurredAt và ý nghĩa nghiệp vụ của nó.
- [ ] Timestamp dùng UTC hoặc có offset/timezone được quy định.
- [ ] Đơn vị timestamp và độ chính xác được thống nhất.
- [ ] EventId giữ nguyên qua retry và replay.
- [ ] Ingestion time và processing time được ghi riêng.
- [ ] Có metric event age, queue wait và execution duration.
- [ ] Đã xác định event nào được xem là late và mốc nào quyết định điều đó.
- [ ] Nếu dùng stream window, đã chọn loại window, watermark và allowed lateness.
- [ ] Đã có chính sách cập nhật, hiệu chỉnh, quarantine, bỏ qua hoặc backfill event muộn.
- [ ] Consumer có idempotency để tránh tác dụng phụ khi redelivery.
- [ ] Timestamp tương lai, quá cũ hoặc không hợp lệ có cách xử lý rõ ràng.
- [ ] Có test cho out-of-order, late event, duplicate, replay và ranh giới cửa sổ.

## Tự kiểm tra

1. Vì sao event time của một đơn hàng có thể là 10:02 trong khi processing time của function là 10:17?
2. Khi đo throughput của function, nên dùng event time hay processing time? Vì sao?
3. Event out-of-order có luôn là late event không? Vai trò của watermark trong việc phân biệt là gì?
4. Allowed lateness giúp hệ thống xử lý dữ liệu đến muộn như thế nào và phải trả giá gì?
5. Vì sao retry hoặc replay không được ghi đè occurredAt bằng thời điểm hiện tại?
6. Idempotency có giải quyết được việc một event đến sau khi cửa sổ báo cáo đã chốt không? Cần cơ chế nào bổ sung?

Trong hệ thống serverless, event có thể đi qua nhiều tầng trước khi đến Java function. Giữ riêng thời điểm nghiệp vụ, thời điểm tiếp nhận và thời điểm xử lý giúp báo cáo phản ánh đúng thực tế, vận hành đo đúng độ trễ và consumer có thể xử lý dữ liệu muộn theo chính sách rõ ràng. Khi kết hợp event contract ổn định, watermark phù hợp, idempotency và quy trình hiệu chỉnh, hệ thống có thể vừa phản hồi nhanh vừa bảo toàn tính đúng đắn của dữ liệu.

