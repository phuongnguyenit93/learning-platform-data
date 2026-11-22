# Phân biệt log và metric trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **log** ghi lại sự kiện gì, còn **metric** mô tả đặc tính định lượng nào của hệ thống.
- Chọn đúng loại dữ liệu khi cần điều tra một lỗi cụ thể, theo dõi xu hướng, đo hiệu năng hoặc đặt cảnh báo.
- Nhận diện các loại metric phổ biến: counter, gauge, histogram và summary.
- Biết cách kết hợp log và metric mà không làm tăng chi phí lưu trữ, lộ dữ liệu nhạy cảm hoặc tạo quá nhiều nhãn metric.
- Quan sát sự khác biệt qua một chương trình Java 17 chạy độc lập.

## 2. Log là gì? Metric là gì?

**Log** là một bản ghi về một *sự kiện cụ thể* xảy ra trong ứng dụng. Nó thường có thời điểm, mức độ, nguồn phát sinh, thông điệp và ngữ cảnh để trả lời câu hỏi: **“Đã xảy ra chuyện gì, ở đâu và vì sao?”**

Ví dụ log minh họa:

~~~text
2026-11-09T10:00:12Z ERROR checkout requestId=req-42 orderId=ORD-7 Payment timeout after 3000 ms
~~~

Từ log này, người vận hành có thể tìm một request, nhận biết thao tác checkout gặp timeout và tiếp tục lần theo ngoại lệ hay các sự kiện liên quan. Log hữu ích vì giữ **chi tiết của từng lần xảy ra**, nhưng một dòng log đơn lẻ chưa cho biết hệ thống đang lỗi trên diện rộng hay chỉ có một trường hợp.

**Metric** là một phép đo bằng **giá trị số**, được gắn với thời điểm và có thể đi kèm các nhãn phân loại (*labels/tags*) để tạo thành chuỗi số liệu theo thời gian. Metric trả lời câu hỏi: **“Có bao nhiêu, nhanh/chậm đến mức nào, thay đổi ra sao, có vượt ngưỡng không?”**

Ví dụ metric theo quy ước đặt tên của Prometheus (số liệu giả định):

~~~text
http_requests_total{service="checkout",status="500"} 42
http_requests_in_flight{service="checkout"} 3
~~~

Dòng đầu biểu diễn số đếm tích lũy của request có mã trạng thái 500 cho một nhóm nhãn; dòng thứ hai là số request đang xử lý tại thời điểm lấy mẫu. Hai giá trị này **không chứa requestId, stack trace hoặc nguyên nhân của từng lỗi**.

Điểm cốt lõi: **log lưu ngữ cảnh của từng sự kiện; metric lưu phép đo có thể tổng hợp và so sánh theo thời gian**. Hai loại bổ sung cho nhau, không thay thế hoàn toàn nhau.

## 3. Bảng so sánh log và metric

| Tiêu chí | Log | Metric |
| --- | --- | --- |
| Đơn vị thông tin | Một sự kiện/bản ghi, thường có thông điệp | Một quan sát bằng số hoặc chuỗi thời gian của giá trị số |
| Câu hỏi chính | “Chuyện gì đã xảy ra với request này?” | “Có bao nhiêu request lỗi trong 5 phút?” |
| Nội dung thường có | Timestamp, level, message, logger, ID tương quan, exception/stack trace | Tên phép đo, giá trị, thời điểm, đơn vị, labels/tags |
| Độ chi tiết | Có thể đi sâu tới thao tác và nguyên nhân cụ thể | Thể hiện mức tổng hợp, tỷ lệ, trạng thái hoặc phân bố |
| Tìm kiếm | Tìm theo chuỗi/trường, lọc sự kiện | Truy vấn số liệu theo thời gian và nhãn |
| Biểu đồ, cảnh báo | Có thể tạo từ tìm kiếm/đếm log, tùy hệ thống thu thập | Rất phù hợp để vẽ xu hướng và đặt ngưỡng/rule |
| Dung lượng | Phụ thuộc số sự kiện, kích thước thông điệp và stack trace | Phụ thuộc số chuỗi thời gian (số tổ hợp nhãn), tần suất thu thập và retention |
| Dữ liệu nhạy cảm | Rủi ro cao khi ghi request body, token hoặc thông tin cá nhân | Rủi ro nếu đưa thông tin nhạy cảm vào tên/giá trị nhãn |
| Công cụ Java thường gặp | java.util.logging (JUL), SLF4J với Logback/Log4j 2 | Micrometer, OpenTelemetry Metrics; hệ thống thu thập như Prometheus |
| Hạn chế khi dùng riêng | Khó thấy tổng thể nếu chỉ đọc từng dòng | Khó biết nguyên nhân cụ thể chỉ từ một điểm số |

Không nên hiểu rằng log luôn chỉ là văn bản còn metric luôn là dữ liệu tổng hợp sẵn. **Structured log** có thể chứa trường số, log có thể được đếm thành *log-based metric*, còn metric dạng counter có thể được cập nhật mỗi khi một sự kiện diễn ra. Khác biệt quan trọng nằm ở **mô hình dữ liệu và mục đích sử dụng**.

## 4. Các loại metric cần nhận diện

### 4.1. Counter — số đếm tích lũy

Counter thường tăng khi một sự kiện xảy ra, ví dụ số HTTP request đã xử lý, số lỗi, số lần retry. Một counter không tự giảm trong vòng đời của cùng một tiến trình/chuỗi đo; **khi tiến trình khởi động lại, giá trị có thể về 0**, vì vậy hệ thống truy vấn tốc độ phải xử lý reset.

Ví dụ:

~~~text
10:00  requests_total = 120
10:01  requests_total = 180
~~~

Trong khoảng 60 giây, nếu không có reset và dữ liệu đo đầy đủ, số request tăng 60, tương đương trung bình **1 request/giây**. Counter tích lũy không phải là throughput tại một thời điểm; throughput cần tính **mức tăng theo khoảng thời gian**.

### 4.2. Gauge — giá trị có thể tăng hoặc giảm

Gauge mô tả trạng thái đo được tại thời điểm lấy mẫu: số kết nối đang mở, số tác vụ đang xử lý, độ dài hàng đợi, lượng bộ nhớ đang sử dụng.

~~~text
active_connections = 12
queue_depth = 4
~~~

Một gauge có thể tăng, giảm hoặc giữ nguyên. Không dùng counter cho những giá trị cần giảm khi tài nguyên được giải phóng.

### 4.3. Histogram — phân bố các quan sát

Histogram thường phân loại các quan sát như thời gian đáp ứng vào **các bucket**, đồng thời theo dõi tổng số và tổng giá trị (phụ thuộc hệ thống metric cụ thể). Nhờ phân bố này, ta có thể ước lượng **p95/p99 latency**, phát hiện request chậm mà giá trị trung bình che lấp.

Ví dụ có 100 request, 95 request mất 20 ms nhưng 5 request mất 2000 ms: chỉ nhìn trung bình có thể không thể hiện đủ mức chậm của nhóm cuối. Một histogram với bucket được chọn hợp lý cho phép đặt câu hỏi “Bao nhiêu phần trăm request dưới 500 ms?”.

**Đơn vị quan trọng:** nhiều thư viện đo thời lượng bằng **giây** (seconds), dù một ứng dụng có thể trình bày bằng **mili giây**. Đặt tên, cấu hình và truy vấn cần thống nhất đơn vị.

### 4.4. Summary — thống kê các quan sát

Một số hệ thống cung cấp summary để giữ count, sum và đôi khi tính quantile ngay tại nơi ghi nhận. Việc gộp quantile tính sẵn từ nhiều instance thường **không cho ra quantile toàn hệ thống một cách hợp lệ**; histogram phù hợp hơn khi cần tổng hợp phân bố qua nhiều instance và tính quantile phía truy vấn. Không phải mọi thư viện metric đều cung cấp cùng một tập loại metric hay cùng quy tắc xuất dữ liệu.

## 5. Dùng log hay metric cho tình huống nào?

| Nhu cầu | Ưu tiên | Lý do |
| --- | --- | --- |
| Xem vì sao request cụ thể bị lỗi | **Log** kèm request ID và exception | Cần thông điệp, stack trace, ngữ cảnh |
| Biết tỷ lệ lỗi tăng trong 5 phút qua | **Metric**: lỗi / tổng request | Cần thống kê theo cửa sổ thời gian |
| Cảnh báo latency p95 vượt ngưỡng | **Metric** dạng histogram | Cần phân bố thời gian xử lý |
| Điều tra trường hợp một người dùng gặp lỗi hiếm | **Log** có correlation ID, loại bỏ dữ liệu nhạy cảm | Cần lần theo chuỗi sự kiện |
| Biết số request đang chạy hiện tại | **Metric** dạng gauge | Trạng thái tức thời, có thể tăng/giảm |
| Biết ai đã thay đổi quyền truy cập | **Audit log** thích hợp | Cần lịch sử sự kiện có giá trị kiểm tra; yêu cầu bảo toàn có thể cao hơn application log |
| Tìm dịch vụ nào làm request chậm trong hệ phân tán | **Tracing**, kết hợp metric và log | Trace/span mô tả đường đi; metric nêu xu hướng, log cho chi tiết lỗi |

Ví dụ trong sự cố checkout:

1. **Metric** cho thấy tỷ lệ request lỗi tăng từ 1% lên 8% trong 10 phút và latency p95 tăng cao. Đây là tín hiệu “có vấn đề”, giúp quyết định cần điều tra.
2. Người vận hành lọc **log** của dịch vụ checkout trong khoảng thời gian đó, tìm requestId và exception để xem những lần thất bại thực sự xảy ra như thế nào.
3. Nếu lời gọi chạy qua nhiều dịch vụ, **trace ID** liên kết request với các span; log có cùng ID làm rõ nội dung lỗi ở từng dịch vụ.
4. Sau khi sửa, tiếp tục nhìn **metric** để kiểm tra tỷ lệ lỗi/latency trở về mức mong đợi, đồng thời xem log để chắc rằng lỗi cụ thể không tái diễn.

Không thể suy ra nguyên nhân gốc như “database hết kết nối” **chỉ** từ việc metric báo lỗi tăng. Cần bằng chứng từ log, trace, trạng thái hệ thống hoặc nguồn quan sát khác.

## 6. Ví dụ Java 17+: cùng một lần xử lý, log và metric ghi khác nhau

Ví dụ sau sử dụng **java.util.logging** có sẵn trong JDK để ghi một sự kiện lỗi, đồng thời dùng **LongAdder** để đếm request, đếm lỗi và cộng thời lượng. Đây là mô hình học tập cho dễ thấy khác biệt, **chưa phải hệ thống phát hành metric chuẩn**: trong ứng dụng thực, instrument bằng Micrometer hoặc OpenTelemetry Metrics và cho hệ thống giám sát thu thập.

Tạo tệp **LogMetricDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.atomic.LongAdder;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LogMetricDemo {
    private static final Logger LOG =
            Logger.getLogger(LogMetricDemo.class.getName());

    private static final LongAdder REQUESTS = new LongAdder();
    private static final LongAdder ERRORS = new LongAdder();
    private static final LongAdder DURATION_MS_SUM = new LongAdder();

    private static void recordRequest(
            String requestId, int durationMs, boolean success) {
        // Ba phép đo số học được cập nhật cho từng request.
        REQUESTS.increment();
        DURATION_MS_SUM.add(durationMs);

        if (!success) {
            ERRORS.increment();

            // Log có ngữ cảnh của đúng request gặp sự cố.
            LOG.warning("requestId=" + requestId
                    + " outcome=error durationMs=" + durationMs);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        output.setLevel(Level.INFO);
        LOG.addHandler(output);

        // Dữ liệu giả lập và cố định để output xác định.
        recordRequest("req-101", 12, true);
        recordRequest("req-102", 18, false);
        recordRequest("req-103", 30, true);

        // StreamHandler có buffer: flush trước khi in phần tổng hợp.
        output.flush();

        long requests = REQUESTS.sum();
        long errors = ERRORS.sum();
        long durationSum = DURATION_MS_SUM.sum();

        System.out.println("requests_total " + requests);
        System.out.println("request_errors_total " + errors);
        System.out.println("request_duration_ms_sum " + durationSum);
        System.out.printf(Locale.ROOT,
                "request_duration_ms_avg %.1f%n",
                (double) durationSum / requests);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ trong terminal hỗ trợ UTF-8:

~~~bash
javac -encoding UTF-8 LogMetricDemo.java
java LogMetricDemo
~~~

**Stdout chính xác** của chương trình trong một lần chạy bình thường:

~~~text
WARNING | requestId=req-102 outcome=error durationMs=18
requests_total 3
request_errors_total 1
request_duration_ms_sum 60
request_duration_ms_avg 20.0
~~~

Phân tích từng phần:

- Dòng **WARNING** là **log**: cho biết *request nào* thất bại và có thông điệp cụ thể. Với ngoại lệ thật, có thể dùng **LOG.log(Level.SEVERE, "Không xử lý được request " + requestId, exception)** để lưu stack trace, thay vì chỉ log message.
- **requests_total = 3** và **request_errors_total = 1** là **counter minh họa** cho tổng request và tổng lỗi; chúng không mang requestId.
- **request_duration_ms_sum = 60** và phép chia cho 3 cho giá trị **20.0 ms** trung bình. Chỉ có sum/count **không thể xác định p95**; muốn đo p95 phải thu phân bố (chẳng hạn histogram).
- **LongAdder** phù hợp khi nhiều luồng cập nhật số đếm; tuy nhiên **sum() không phải ảnh chụp nguyên tử của toàn bộ các cập nhật đồng thời**. Trong ví dụ chạy tuần tự, các kết quả là xác định.
- **StreamHandler** được cấu hình riêng để xuất ra stdout và chỉ in level + thông điệp. Logging thực tế nên bổ sung timestamp, tên dịch vụ, logger và ID tương quan; mặc định handler/cấu hình khác có thể tạo output khác.
- Những dòng có tên kết thúc bằng **_total** ở trên chỉ là **in tổng hợp ra console để học**. Chúng không tự biến thành metric được Prometheus scrape, không tạo HTTP endpoint và không có backend lưu chuỗi thời gian.

Trong hệ thống thật, bộ thư viện metric đảm nhiệm việc đăng ký phép đo, xuất dữ liệu, quản lý nhãn và tương tác với backend. Mã ứng dụng chỉ nên cập nhật các phép đo có ý nghĩa, không tự xây một hạ tầng metrics chỉ để đếm request.

## 7. Log và metric có thể kết hợp như thế nào?

Giả sử một API có đường dẫn **/orders/{id}**. Một chiến lược hợp lý là:

**Metric** (nhãn có số lượng giá trị hữu hạn):

~~~text
http_requests_total{route="/orders/{id}",method="GET",status="500"} 17
~~~

**Log** cho sự kiện lỗi riêng lẻ:

~~~text
ERROR service=order-api requestId=req-781 route=/orders/{id} orderId=ORD-781 cause="database timeout"
~~~

Metric nói rằng số lượng phản hồi 500 đang tăng ở route nào; log giúp tìm từng request tương ứng và nguyên nhân. **Không gắn requestId hoặc orderId vào label của metric**: gần như mỗi request sẽ tạo một tổ hợp label khác nhau, làm số chuỗi thời gian bùng nổ (*high cardinality*), tăng bộ nhớ và chi phí thu thập.

Nên dùng label như **service**, **method**, **status**, **route template** (ví dụ /orders/{id}); kiểm soát số lượng giá trị của chúng. ID riêng lẻ, thông điệp ngoại lệ đầy đủ và stack trace thuộc phần ngữ cảnh log hoặc trace khi có nhu cầu hợp lệ.

Ở hệ thống hỗ trợ, **exemplar/trace ID** có thể giúp nhảy từ một điểm metric sang trace liên quan. Điều này liên kết các nguồn quan sát mà không cần đưa ID duy nhất thành label của mọi time series.

## 8. Hiểu đúng khía cạnh thời gian và chi phí

**Log** thường có dấu thời gian từng sự kiện; việc phát, đệm, gửi và đánh chỉ mục có thể làm bản ghi xuất hiện trễ trong công cụ tìm kiếm. Không mặc định thứ tự các dòng thu về từ nhiều thread hoặc nhiều instance phản ánh thứ tự thực thi tuyệt đối.

**Metric** thường được backend lấy mẫu hoặc nhận theo chu kỳ. Một điểm dữ liệu có thể phản ánh thời điểm đo, giá trị tích lũy hoặc kết quả tổng hợp trên một khoảng; không suy luận rằng một điểm sample là một request đơn lẻ. Độ phân giải, độ trễ ghi nhận và khoảng thời gian truy vấn đều ảnh hưởng tới kết quả.

Về chi phí:

- Log quá chi tiết ở INFO cho mọi bước nhỏ có thể tạo lượng dữ liệu rất lớn, nhất là trong vòng lặp hoặc API lưu lượng cao; chọn level, retention và sampling phù hợp.
- Metric tuy gọn cho việc theo dõi xu hướng nhưng có thể rất tốn kém khi tổ hợp label tăng không kiểm soát. Mỗi bộ giá trị label thường tạo chuỗi thời gian riêng.
- Một hệ thống cũng có thể **tạo metric từ log** bằng cách đếm/cộng trường dữ liệu. Cách này hữu ích khi đã có log phù hợp, nhưng cần xét chi phí ingest, độ trễ và mức chính xác; không mặc định tương đương với metric được instrument trực tiếp.
- Cần quản lý thời gian lưu, quyền truy cập và việc xóa dữ liệu theo yêu cầu. **Không ghi password, token, API key hay nội dung nhạy cảm của request** vào log; cũng không dùng thông tin cá nhân làm label metric.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Có log INFO là đã có metric” | Log mô tả sự kiện; metric cần phép đo và quy trình thu thập/truy vấn số liệu |
| “Counter hiện tại bằng 300 nghĩa là 300 request/giây” | Counter là số tích lũy; cần xét mức tăng theo thời gian để tính rate |
| “Tổng thời lượng / số request là p95” | Đó là **trung bình**, không phải percentile; p95 cần phân bố quan sát |
| “Metric càng nhiều label càng chi tiết càng tốt” | Label có giá trị gần như duy nhất gây high cardinality |
| “Thêm requestId vào mọi metric để điều tra” | Giữ ID trong log/trace, metric dùng nhãn phân loại có tập giá trị giới hạn |
| “Nhìn thấy error rate tăng là biết lỗi code nào” | Metric phát hiện thay đổi; cần log/trace và chứng cứ liên quan để xác định nguyên nhân |
| “Đọc từng dòng log đủ để đo sức khỏe toàn hệ thống” | Cần metric để theo dõi tổng quan, tỷ lệ, phân bố và alert có ngưỡng |
| “Metric luôn tăng và không bao giờ reset” | Counter có thể reset khi restart; gauge có thể tăng hoặc giảm |
| “Ghi log thì chắc chắn log đã lưu” | Buffer, lỗi truyền tải, giới hạn hệ thống nhận hoặc retention có thể làm log thất lạc |

## 10. Cách tự kiểm tra kiến thức

**Câu 1.** Bạn muốn biết trong 5 phút gần nhất có bao nhiêu phần trăm HTTP request trả 5xx. Chọn gì?

**Đáp án:** Metric — đếm số request 5xx và tổng request trong cùng cửa sổ thời gian, sau đó tính tỷ lệ; kết quả chỉ có nghĩa khi định nghĩa request và nhãn nhất quán.

**Câu 2.** Một request riêng lẻ gây NumberFormatException; bạn cần kiểm tra tham số xử lý và vị trí lỗi. Chọn gì?

**Đáp án:** Log có ngữ cảnh đủ dùng, request ID và throwable/stack trace. Che hoặc không ghi giá trị đầu vào nhạy cảm.

**Câu 3.** Muốn xem 95% request phản hồi nhanh hơn bao nhiêu mili giây. Chọn gì?

**Đáp án:** Metric dạng phân bố, điển hình là histogram với bucket/độ phân giải phù hợp. Counter tổng số hoặc phép tính trung bình không đủ để xác định p95.

**Câu 4.** Hai request cùng mã 500. Có nên đưa hai requestId vào label của http_requests_total không?

**Đáp án:** Không. Label nên giữ số tổ hợp có giới hạn; request ID thuộc log hoặc trace.

**Câu 5.** Hệ thống phát cảnh báo tỷ lệ lỗi tăng nhưng bạn không biết vì sao. Bước tiếp theo?

**Đáp án:** Thu hẹp service, route và khoảng thời gian bằng metric; tra log lỗi cùng khoảng thời gian và đối chiếu request/trace ID để tìm bằng chứng nguyên nhân.

**Ghi nhớ:** **Log trả lời “điều gì đã xảy ra với một sự kiện cụ thể?”, metric trả lời “hệ thống đang hoạt động như thế nào trên quy mô và theo thời gian?”.** Dùng metric để phát hiện và định lượng, log để điều tra chi tiết; kết hợp tracing khi request đi qua nhiều thành phần.
