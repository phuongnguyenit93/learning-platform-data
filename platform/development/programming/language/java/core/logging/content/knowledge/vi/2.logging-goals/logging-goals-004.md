# Đo lường vận hành bằng logging trong Java

## 1. Log giúp đo điều gì trong vận hành?

Khi một ứng dụng chạy thật, câu hỏi không chỉ là “đã xảy ra lỗi gì?” mà còn là: trong một khoảng thời gian có bao nhiêu yêu cầu, bao nhiêu yêu cầu thất bại, người dùng phải chờ bao lâu, tác vụ nền có bị chậm hoặc xử lý lặp không, và tình hình đang tốt lên hay xấu đi? **Đo lường vận hành bằng logging** là ghi các sự kiện có cấu trúc đủ nhất quán để có thể đếm, phân nhóm, tính tỷ lệ và truy ngược từ dấu hiệu bất thường tới một lần xử lý cụ thể.

Ví dụ, một dòng `Payment completed` riêng lẻ chủ yếu cho biết một giao dịch đã kết thúc. Nếu mọi lần xử lý đều ghi sự kiện `payment.completed` với `status`, `duration_ms`, `payment_method` và `trace_id`, ta có thể tính số giao dịch mỗi phút, tỷ lệ lỗi theo phương thức thanh toán, phân bố độ trễ và tìm đường đi của giao dịch gặp sự cố.

Ba loại tín hiệu thường phối hợp với nhau:

- **Log:** bản ghi từng sự kiện có ngữ cảnh; thích hợp tìm nguyên nhân và kiểm tra trường hợp cụ thể.
- **Metric (chỉ số):** giá trị đã tổng hợp theo thời gian, như số yêu cầu/giây, tỷ lệ lỗi hay CPU; thích hợp cho biểu đồ và cảnh báo.
- **Trace (vết xử lý):** chuỗi các bước của cùng một yêu cầu qua nhiều thành phần; thích hợp xác định công đoạn chậm hoặc thất bại.

Log có thể là **nguồn để tạo metric**, nhưng không thay thế mọi phép đo trực tiếp. CPU, mức sử dụng bộ nhớ, độ đầy hàng đợi và số luồng đang chờ thường cần metric hoặc công cụ quan sát runtime chuyên dụng.

## 2. Chuyển câu hỏi vận hành thành phép đo

Một tập thông tin phổ biến cho ứng dụng HTTP là bốn tín hiệu sau:

| Tín hiệu | Câu hỏi | Cách tính từ sự kiện hoàn tất yêu cầu |
| --- | --- | --- |
| Lưu lượng (traffic) | Hệ thống đang nhận bao nhiêu yêu cầu? | `request_count / window_seconds`, đơn vị request/giây (RPS). |
| Lỗi (errors) | Bao nhiêu lần xử lý thất bại? | `error_count / total_count × 100%`; phải định nghĩa thế nào là lỗi. |
| Độ trễ (latency) | Một yêu cầu mất bao lâu? | Phân bố `duration_ms`; theo dõi p50, p95, p99 và xu hướng. |
| Bão hòa (saturation) | Tài nguyên có gần quá tải? | Kết hợp log chờ hàng đợi, từ chối tác vụ với metric CPU, heap, thread pool, queue depth. |

Các khái niệm cần phân biệt:

- **Count:** số sự kiện trong một cửa sổ thời gian. Đếm `request.completed` cho biết số lần xử lý đã kết thúc; không nhất thiết bằng số request *được nhận vào* nếu có yêu cầu còn treo hoặc tiến trình bị dừng đột ngột.
- **Rate:** count chia cho độ dài cửa sổ. `300 request / 60 giây = 5 RPS`. So sánh cửa sổ 1 phút và 1 giờ phải chú ý cách làm mượt đỉnh tải.
- **Error rate:** tỷ lệ lỗi theo một định nghĩa nhất quán. Với HTTP, có thể xem 5xx là lỗi phía máy chủ; 4xx thường là từ chối do yêu cầu phía khách, nhưng có sản phẩm xem một số 4xx là thất bại nghiệp vụ. Báo cáo phải nêu rõ tử số và mẫu số.
- **Latency percentile:** p95 xấp xỉ thời gian mà 95% quan sát có độ trễ nhỏ hơn hoặc bằng giá trị đó. p95/p99 giúp thấy nhóm chậm mà trung bình có thể che khuất. Tránh tính trung bình của các percentile theo từng máy rồi xem như percentile toàn hệ thống.
- **Success rate / SLI:** tỷ lệ yêu cầu đạt tiêu chí phục vụ đã định nghĩa; **SLO** là mục tiêu cho chỉ số ấy, ví dụ “99,9% yêu cầu hợp lệ thành công trong 30 ngày”. Log phải có đủ dữ liệu và quy tắc phân loại để tính SLI một cách nhất quán.

Đối với tác vụ nền, đổi đối tượng đo cho đúng: `job.started`, `job.completed`, `job.failed`, thời gian chạy, thời gian chờ hàng đợi, số lần thử lại. Phân biệt **lượt thử (attempt)** với **công việc logic (job)** để không vô tình tính một job thử lại ba lần thành ba job khác nhau.

## 3. Thiết kế một sự kiện có thể đếm và đối chiếu

Sự kiện nên có tên ổn định, dữ liệu có kiểu rõ ràng và đơn vị cố định. Ví dụ một request hoàn tất:

```text
ts=2026-01-01T00:00:02Z event=request.completed service=checkout
environment=prod route=/orders/{id} method=GET status=503
duration_ms=85 trace_id=tr-83 request_id=req-204
error_code=UPSTREAM_UNAVAILABLE
```

Các trường có vai trò khác nhau:

| Trường | Tác dụng |
| --- | --- |
| `ts` | Mốc thời gian sự kiện theo UTC/ISO 8601, dùng lọc theo cửa sổ. |
| `event` | Tên hành vi ổn định để chọn đúng loại bản ghi, ví dụ `request.completed`. |
| `service`, `environment`, `version` | Phân biệt dịch vụ, môi trường và bản phát hành. |
| `route`, `method` | Phân nhóm theo tuyến đã chuẩn hóa và phương thức; dùng `/orders/{id}` thay vì từng ID thật. |
| `status`, `outcome`, `error_code` | Phân loại kết quả, thống kê lỗi; mã lỗi nên ổn định. |
| `duration_ms` | Thời lượng xử lý theo mili giây, là số để tính phân bố. |
| `trace_id`, `request_id` | Liên kết log của một lần xử lý để điều tra chi tiết. |

Một dòng chứa nhiều trường chỉ là ví dụ hiển thị; khi dùng hệ thống thu thập log thực tế, **JSON có cấu trúc** hoặc định dạng mà bộ thu thập phân tích đúng sẽ dễ truy vấn hơn chuỗi ghép tùy ý. Đặt tên trường cố định, chọn một đơn vị duy nhất (`duration_ms` hoặc `duration_ns`), giữ số là số và dùng giá trị rõ ràng khi trường tùy chọn bị thiếu.

**Chọn đúng thời điểm ghi:** đối với HTTP, thường ghi *một sự kiện hoàn tất cho một lượt xử lý* ở lớp bao quanh request (filter/interceptor), sau khi biết status và thời lượng. Với exception, vẫn cố gắng ghi kết quả cuối trong khối `finally` hoặc cơ chế hoàn tất phù hợp, đồng thời tránh ghi cùng một sự kiện nhiều lần ở mỗi lớp. Không dựa vào log `request.started` để suy ra số request đã hoàn tất.

**Tính thời lượng:** dùng đồng hồ đo khoảng thời gian có tính đơn điệu như `System.nanoTime()` rồi đổi sang mili giây; `Instant.now()` dùng ghi mốc UTC, không nên trừ hai đồng hồ treo tường để tính latency vì giờ hệ thống có thể được điều chỉnh. Tách riêng thời gian chờ và thời gian thực thi khi đó là hai chỉ số cần phân tích.

**Bảo mật và chi phí:** không ghi mật khẩu, token, thông tin thanh toán, payload chứa dữ liệu cá nhân hoặc query string nhạy cảm. Giới hạn dữ liệu không cần thiết; `trace_id` hữu ích để tìm kiếm, nhưng không nên biến hàng triệu ID duy nhất thành nhãn (label) của metric. Phân nhóm bằng `route` chuẩn hóa, `status`, `service` hay `error_code` với số lượng giá trị được kiểm soát.

## 4. Ví dụ Java 17: sự kiện vận hành và phép tổng hợp

Ví dụ sau sử dụng `java.util.logging` có sẵn trong JDK. Dữ liệu và thời điểm được **cố định để chương trình chạy lại cho kết quả giống nhau**; trong ứng dụng thật, các giá trị này đến từ bộ xử lý request và đồng hồ đo thời lượng. Ví dụ vừa phát log cho từng request, vừa tính kết quả tổng hợp từ cùng tập sự kiện; trong môi trường vận hành, bộ thu thập hoặc hệ thống truy vấn thường thực hiện phần tổng hợp từ các log đã nhận.

Lưu tệp `OperationLogDemo.java`:

```java
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class OperationLogDemo {
    record Request(String traceId, int status, long durationMs) {}

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.operations");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        StreamHandler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + record.getMessage() + System.lineSeparator();
            }
        });
        output.setLevel(Level.INFO);
        logger.addHandler(output);

        List<Request> events = List.of(
                new Request("t1", 200, 12),
                new Request("t2", 200, 20),
                new Request("t3", 503, 85),
                new Request("t4", 404, 16),
                new Request("t5", 200, 34)
        );

        Instant windowStart = Instant.parse("2026-01-01T00:00:00Z");

        for (int i = 0; i < events.size(); i++) {
            Request event = events.get(i);
            String message = String.format(Locale.ROOT,
                    "ts=%s event=request.completed service=checkout"
                            + " route=/checkout status=%d duration_ms=%d trace_id=%s",
                    windowStart.plusSeconds(i),
                    event.status(), event.durationMs(), event.traceId());

            logger.log(event.status() >= 500 ? Level.WARNING : Level.INFO,
                    message);
        }
        output.flush();

        long serverErrors = events.stream()
                .filter(event -> event.status() >= 500).count();
        long[] sorted = events.stream()
                .mapToLong(Request::durationMs).sorted().toArray();

        // Ví dụ dùng quy tắc nearest-rank trên tập nhỏ.
        int p50Index = (int) Math.ceil(sorted.length * 0.50) - 1;
        int p95Index = (int) Math.ceil(sorted.length * 0.95) - 1;

        System.out.printf(Locale.ROOT,
                "window_s=10 requests=%d rps=%.2f errors_5xx=%d"
                        + " error_5xx_pct=%.1f%% p50_ms=%d p95_ms=%d%n",
                events.size(),
                events.size() / 10.0,
                serverErrors,
                serverErrors * 100.0 / events.size(),
                sorted[p50Index],
                sorted[p95Index]);

        logger.removeHandler(output);
        output.close();
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac OperationLogDemo.java
java OperationLogDemo
```

Kết quả chuẩn (mỗi sự kiện được hiển thị trên một dòng):

```text
INFO ts=2026-01-01T00:00:00Z event=request.completed service=checkout route=/checkout status=200 duration_ms=12 trace_id=t1
INFO ts=2026-01-01T00:00:01Z event=request.completed service=checkout route=/checkout status=200 duration_ms=20 trace_id=t2
WARNING ts=2026-01-01T00:00:02Z event=request.completed service=checkout route=/checkout status=503 duration_ms=85 trace_id=t3
INFO ts=2026-01-01T00:00:03Z event=request.completed service=checkout route=/checkout status=404 duration_ms=16 trace_id=t4
INFO ts=2026-01-01T00:00:04Z event=request.completed service=checkout route=/checkout status=200 duration_ms=34 trace_id=t5
window_s=10 requests=5 rps=0.50 errors_5xx=1 error_5xx_pct=20.0 p50_ms=20 p95_ms=85
```

Giải thích:

1. Cửa sổ được **quy ước** là 10 giây; 5 request cho `5 / 10 = 0,50 RPS`. Dấu thời gian của 5 sự kiện chỉ trải từ giây 0 đến giây 4, nên không được lấy chênh lệch giữa timestamp đầu và cuối làm mẫu số rồi kết luận 1,25 RPS.
2. Có một response 503 trên tổng 5 response, nên tỷ lệ **5xx là 20%**. Response 404 được giữ trong mẫu số nhưng không tính là lỗi 5xx; quy tắc này phải được thống nhất với sản phẩm.
3. Dãy thời lượng sau khi sắp xếp là `[12, 16, 20, 34, 85]` ms. Với quy tắc *nearest-rank*, p50 = 20 ms và p95 = 85 ms. Trên chỉ 5 mẫu, p95 gần như phản ánh giá trị lớn nhất; cần nhiều mẫu và cửa sổ phù hợp trước khi đưa ra đánh giá xu hướng.
4. `trace_id=t3` giúp mở bản ghi 503 và truy tìm các sự kiện liên quan; bản thân trường ID này không phải là một chiều phù hợp để vẽ biểu đồ tổng hợp.

`StreamHandler` ở ví dụ được cấu hình chỉ để tạo đầu ra ổn định, không đại diện cho định dạng log production. Dự án thực tế có thể sử dụng SLF4J kết hợp Logback/Log4j2 hoặc hệ thống logging khác; nguyên tắc về sự kiện và cách đo không phụ thuộc vào thư viện.

## 5. Biến log thành biểu đồ và cảnh báo

Quy trình điển hình:

```text
Request / job
    -> ghi event có cấu trúc
    -> thu thập, truyền và lưu log
    -> phân tích event + trường dữ liệu
    -> lọc theo service, môi trường, cửa sổ thời gian
    -> count / rate / tỷ lệ lỗi / percentile
    -> dashboard + cảnh báo + liên kết tới trace/log gốc
```

Ví dụ một câu hỏi vận hành: “Trong 5 phút vừa qua, tỷ lệ 5xx của `checkout` có tăng không?”. Cách xử lý là chỉ chọn `event=request.completed` với `service=checkout` và `environment=prod`, lấy cùng một cửa sổ 5 phút, đếm toàn bộ request đã hoàn tất làm mẫu số, đếm `status >= 500` làm tử số, rồi so với thời kỳ trước hoặc ngưỡng cảnh báo. Nếu tăng, phân nhóm tiếp theo `route`, `version` hoặc `error_code`; dùng `trace_id` để đi từ biểu đồ đến từng trường hợp.

Các điểm phải quy định trước khi đưa chỉ số vào dashboard:

- **Cửa sổ và thời gian:** ghi rõ 1 phút/5 phút/30 ngày, múi giờ hiển thị và dùng timestamp nào (thời gian xảy ra sự kiện hay thời gian bộ thu thập nhận được). Sự kiện đến muộn có thể làm số liệu cửa sổ cũ thay đổi.
- **Mẫu số:** tất cả request, request hợp lệ, request hoàn tất hay yêu cầu nghiệp vụ duy nhất? Không được thay đổi âm thầm khi so sánh các biểu đồ.
- **Gộp nhóm:** chuẩn hóa route; tách môi trường `prod` và `staging`; tránh gộp công việc nền với HTTP hoặc cộng nhầm lượt thử lại vào số giao dịch thành công.
- **Phần trăm và phân vị:** chỉ tính khi đủ số mẫu; nêu rõ cách tính percentile. Khi phân nhóm xong, nên tổng hợp từ dữ liệu gốc hoặc cấu trúc histogram phù hợp, không lấy trung bình các p95.
- **Cảnh báo:** thường kết hợp mức độ nghiêm trọng và khoảng thời gian kéo dài. Ví dụ “5xx vượt 2% trong 5 phút và có ít nhất 100 yêu cầu” giúp giảm báo động sai khi chỉ có vài mẫu; đây là ví dụ thiết kế, không phải ngưỡng phù hợp cho mọi dịch vụ.
- **Truy nguyên:** dashboard nên dẫn về log hoặc trace chứa `request_id/trace_id`, trạng thái, mã lỗi và version của triển khai gần nhất để người trực vận hành có thể hành động.

Trong trường hợp log bị lấy mẫu, bị rơi do nghẽn/tiến trình chết, bị ghi trùng khi gửi lại, hoặc chỉ bật ở mức `WARN`, phép đếm từ log sẽ **không còn đại diện chắc chắn cho toàn bộ lưu lượng**. Các chỉ số dùng để cảnh báo SLA/SLO quan trọng thường cần metric được instrument trực tiếp hoặc một tuyến thu thập sự kiện có kiểm soát độ đầy đủ và trùng lặp. Log chi tiết vẫn rất hữu ích để giải thích *vì sao* chỉ số thay đổi.

## 6. Sai lầm thường gặp

1. **Chỉ log thông báo tự do:** `"slow!"` hoặc `"something failed"` không có đơn vị, route hay mã kết quả nên khó tổng hợp. Hãy dùng tên sự kiện và trường ổn định.
2. **Đếm log lỗi như tỷ lệ lỗi request:** một request có thể phát 5 stack trace hoặc không phát log lỗi nào; cần sự kiện hoàn tất nhất quán với mẫu số chính xác.
3. **Dùng timestamp hệ thống để đo thời lượng:** đồng hồ treo tường có thể nhảy; dùng `System.nanoTime()` cho elapsed time, `Instant.now()` để đánh dấu thời điểm.
4. **Gộp 4xx và 5xx thiếu định nghĩa:** gây nhầm sự cố máy chủ với request không hợp lệ; trình bày riêng hoặc mô tả chính sách thành công/thất bại.
5. **Nhóm theo ID hoặc URL thô:** mỗi request một nhãn mới làm số chuỗi metric tăng vọt; dùng route chuẩn hóa để tổng hợp, giữ ID để tìm log cụ thể.
6. **Tin hoàn toàn vào log không đầy đủ:** log có thể bị lấy mẫu, mất, trùng hoặc tới muộn; so sánh với metric thu thập trực tiếp nếu đo mục tiêu độ tin cậy.
7. **Chỉ theo dõi giá trị trung bình:** trung bình bình thường vẫn có thể che giấu nhiều request rất chậm; dùng phân vị kèm số mẫu và phân tích theo route.
8. **Ghi mọi thứ ở mức INFO:** làm tăng chi phí lưu trữ và có nguy cơ lộ dữ liệu. Chọn sự kiện nghiệp vụ/vận hành có giá trị, mức log phù hợp, chính sách giữ và che dữ liệu.

## 7. Bài tập tự kiểm tra

Một dịch vụ có 200 sự kiện `request.completed` trong 60 giây, gồm 8 response 5xx và 12 response 4xx. Hãy tính RPS, tỷ lệ 5xx và xác định có nên xem 4xx là lỗi máy chủ không.

**Đáp án:** RPS = `200 / 60 ≈ 3,33`; tỷ lệ 5xx = `8 / 200 × 100% = 4%`. Theo chính sách “lỗi máy chủ = 5xx”, 12 response 4xx không tính vào tử số 5xx, nhưng vẫn có thể phân tích riêng nếu ảnh hưởng trải nghiệm người dùng. Muốn kết luận có vi phạm mục tiêu vận hành hay không, cần thêm định nghĩa SLI/SLO, chất lượng dữ liệu và khoảng thời gian quan sát.

**Tự kiểm tra bài đã hiểu:** Bạn có thể chỉ ra sự kiện nào được đếm, mẫu số của mỗi tỷ lệ, đơn vị thời lượng, lý do dùng `System.nanoTime()`, cách lần từ spike trên dashboard về `trace_id` và ít nhất hai tình huống khiến số liệu suy ra từ log bị sai lệch.