# Histogram, percentile và cách đọc độ trễ

Một trợ lý Spring AI có thể trả lời trong 200 mili giây ở đa số lượt, nhưng thỉnh thoảng mất 8–12 giây do truy xuất tài liệu, model tạo nhiều token hoặc công cụ backend bị chậm. Chỉ báo **độ trễ trung bình** sẽ che khuất những lần chờ đợi này. Ngược lại, một biểu đồ p95 tăng chưa chắc có nghĩa model trở nên kém chất lượng: nguyên nhân có thể là tập câu hỏi khó hơn, nhiều lời gọi tool hơn, retry, lỗi kết nối hoặc cách thu thập metric đã thay đổi.

**Histogram** giúp giữ thông tin về phân bố thời lượng theo các ngưỡng; **percentile** (hay quantile) giúp diễn đạt ngưỡng độ trễ mà một tỷ lệ mẫu nằm bên dưới. Muốn hiểu các chỉ số này, người đọc phải biết **độ trễ của hành động nào**, **đơn vị gì**, **bao gồm những ca nào**, **được đo trong cửa sổ nào** và **được ước lượng bằng cách nào**.

Bài này thuộc chương **Thiết kế metric** trong module **SPRING_AI_EVALUATION_OBSERVABILITY**. Mục tiêu là đọc và thiết kế metrics/traces để đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling, đồng thời phát hiện nguyên nhân suy giảm chất lượng, chi phí và độ trễ qua các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt độ trễ end-to-end, model, tool, retrieval, time-to-first-token và thời gian hoàn tất nghiệp vụ bất đồng bộ.
2. Giải thích phân bố độ trễ, trung bình, p50, p90, p95, p99, max và ảnh hưởng của mẫu hiếm hoặc cửa sổ quan sát.
3. Đọc **classic histogram buckets** tích lũy của Prometheus, các series **_count**, **_sum**, **_bucket** và nhãn **le**.
4. Biết hạn chế của percentile tính từ dữ liệu thô, percentile tính tại client và percentile ước lượng từ histogram.
5. Dùng Micrometer **Timer**, **publishPercentileHistogram**, **publishPercentiles**, **serviceLevelObjectives** và ngưỡng thời lượng phù hợp với SLO.
6. Viết PromQL cho mean, p95, tỷ lệ đáp ứng ngưỡng, throughput và phân tích độ trễ theo nhóm mà không cộng/trung bình percentile sai cách.
7. Kết hợp histogram với verdict, traces, token, tool calls và RAG relevance/fact checking để giải thích hồi quy hiệu suất.

## 2. Trước khi đo: “độ trễ” bắt đầu và kết thúc ở đâu?

Không phải mọi đại lượng có đơn vị giây đều là cùng một loại latency. Trong một request Spring AI có thể tồn tại nhiều đồng hồ thời gian khác nhau.

| Đại lượng | Thời điểm bắt đầu | Thời điểm kết thúc | Ví dụ mục đích |
| --- | --- | --- | --- |
| **User-response end-to-end latency** | Ứng dụng nhận yêu cầu người dùng | Toàn bộ phản hồi được hoàn tất theo hợp đồng API | Trải nghiệm chờ trả lời |
| **Time to first token / first chunk** | Bắt đầu yêu cầu streaming theo ranh giới đã định | Nhận chunk/token đầu tiên có ý nghĩa | Độ phản hồi ban đầu |
| **Time to full response** | Bắt đầu lượt trả lời | Nhận/ghi xong nội dung cuối | Tổng thời gian streaming |
| **Model request latency** | Bắt đầu gửi một request đến provider | Nhận response của model | Độ trễ của từng model call |
| **Tool execution latency** | Dispatcher bắt đầu chạy tool | Tool handler kết thúc hoặc báo lỗi | Hiệu suất thực thi công cụ |
| **RAG retrieval latency** | Bắt đầu truy xuất | Danh sách tài liệu/đoạn đã sẵn sàng | Hiệu suất retriever |
| **Evaluator latency** | Bắt đầu chấm một ca/claim | Oracle hoặc evaluator trả verdict | Chi phí thời gian đánh giá |
| **Business completion latency** | Yêu cầu nghiệp vụ được tiếp nhận theo hợp đồng | Backend xác minh hậu điều kiện đã đạt | Thời gian hoàn tất thực tế |
| **Verification lag** | Trạng thái nghiệp vụ thực sự thay đổi | Bộ đánh giá quan sát được bằng chứng | Độ trễ xác minh |

Ví dụ người dùng yêu cầu “Hoàn tiền đơn A123”. Công cụ có thể trả **ACCEPTED sau 150 ms**, nhưng backend mất 40 giây để xác nhận tiền đã được chuyển. Kết luận “hoàn tiền mất 150 ms” là sai nếu mục tiêu đo là **business completion**. Cần hai Timer hoặc hai nguồn quan sát có tên khác nhau.

### 2.1. Sơ đồ một request có RAG và tool

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant M as Model
    participant T as Tool/backend
    participant R as Retriever
    U->>A: Hỏi về đơn hàng và chính sách
    A->>M: Model request 1
    M-->>A: Đề nghị gọi công cụ
    A->>T: get_order_status
    T-->>A: Trạng thái + as-of
    A->>R: Truy xuất chính sách
    R-->>A: Tài liệu phù hợp
    A->>M: Model request 2 + evidence
    M-->>A: Câu trả lời cuối
    A-->>U: Hoàn tất phản hồi
~~~

Nếu các bước chạy tuần tự, tổng thời gian end-to-end bao gồm nhiều model calls, tool, retrieval và overhead. Nếu một số bước song song, **không thể cộng các p95 của từng bước để suy ra p95 toàn hành trình**. Hãy đo cả Timer end-to-end với ranh giới riêng.

### 2.2. Đơn vị thời gian

Micrometer **Timer** chuyên đo Duration; khi xuất sang Prometheus, những series thời lượng thường được biểu diễn bằng **seconds**. Ví dụ:

~~~text
250 milliseconds = 0.250 seconds
1.4 seconds      = 1400 milliseconds
125000000 ns     = 0.125 seconds
~~~

Trong dashboard, nếu dùng PromQL trên series **_seconds**, hãy hiển thị giây hoặc đổi sang mili giây đúng **một lần**. Đừng nhân 1.000 ở PromQL rồi tiếp tục bật phép đổi giây sang mili giây trong dashboard.

## 3. Phân bố độ trễ: vì sao mean không đủ?

Xét 20 request cùng loại; 19 request hoàn tất trong **200 ms**, một request mất **4.000 ms**:

~~~text
200, 200, 200, 200, 200,
200, 200, 200, 200, 200,
200, 200, 200, 200, 200,
200, 200, 200, 200, 4000  (đơn vị: ms)
~~~

Trung bình là:

\[
\overline{x}=\frac{19\times 200+4000}{20}=390\;\mathrm{ms}.
\]

**390 ms** không miêu tả tốt đa số lần chờ (200 ms) và cũng không phản ánh rõ trải nghiệm của request chậm nhất (4.000 ms). Độ trễ thường có phân bố **lệch phải**, với đuôi chậm đến từ tải cao, network, model dài, tool timeout hoặc retry.

### 3.1. Percentile là gì?

Với tập n mẫu được sắp tăng dần, **percentile bậc q** là một ngưỡng thời lượng tại hoặc dưới đó có xấp xỉ q phần dữ liệu. Một cách định nghĩa thực nghiệm đơn giản là **nearest-rank**: chọn mẫu ở vị trí \(\lceil qn\rceil\), với q nằm trong (0,1].

Trong ví dụ 20 mẫu, theo nearest-rank:

| Chỉ số | Vị trí | Giá trị |
| --- | ---: | ---: |
| p50 | ceil(0,50 × 20) = 10 | 200 ms |
| p90 | ceil(0,90 × 20) = 18 | 200 ms |
| p95 | ceil(0,95 × 20) = 19 | 200 ms |
| p99 | ceil(0,99 × 20) = 20 | 4.000 ms |
| Max | Mẫu lớn nhất | 4.000 ms |
| Mean | Tổng chia 20 | 390 ms |

**Một mẫu chậm chiếm 5% vẫn có thể không làm p95 nearest-rank thay đổi**. Điều này không làm p95 “sai”; nó chỉ cho thấy p95 không đại diện cho mọi phần đuôi. Với yêu cầu nghiêm ngặt, có thể cần cả p99, timeout rate và các ngưỡng SLO.

### 3.2. Các cách tính percentile có thể khác nhau

Nearest-rank là cách giải thích dễ hiểu, **không phải thuật toán bắt buộc** của Micrometer, Prometheus hay mọi thư viện thống kê. Các công cụ có thể nội suy giữa mẫu, dùng histogram hay cấu trúc dữ liệu gần đúng. Với tập nhỏ, p95 từ hai phương pháp có thể khác đáng kể.

Vì vậy, phải ghi **nguồn dữ liệu, phương pháp ước lượng, cửa sổ, bucket resolution và cỡ mẫu** khi so sánh percentile giữa dashboard hoặc phiên bản công cụ.

### 3.3. p50, p95, p99 và max dùng vào việc gì?

| Thước đo | Nhìn thấy điều gì | Điểm mù |
| --- | --- | --- |
| **Mean** | Chi phí thời gian trung bình trên mỗi mẫu | Bị kéo bởi outlier |
| **p50 (median)** | Trải nghiệm điển hình | Bỏ qua phần lớn đuôi chậm |
| **p90** | Mức chờ ở nhóm 10% chậm hơn | Vẫn không thể hiện 1% cực chậm |
| **p95** | Phần đuôi 5% | Có thể chưa thể hiện timeout hiếm |
| **p99** | Phần đuôi 1%, hữu ích khi đủ mẫu | Cần nhiều mẫu, nhạy với cấu hình histogram |
| **Max** | Mẫu lớn nhất quan sát được trong phạm vi thống kê | Nhạy outlier và cửa sổ |

Không có percentile “tốt nhất” cho mọi hệ thống. Với trợ lý người dùng, p95 end-to-end thường rất hữu ích; với thanh toán hoặc SLA nghiêm ngặt, tail latency và tỷ lệ timeout có thể quan trọng hơn. Dù chọn giá trị nào, cần đủ mẫu và cùng nhóm tác vụ.

## 4. Histogram là gì và biểu diễn phân bố ra sao?

**Histogram** phân các giá trị thời lượng thành những ngưỡng hoặc vùng để ước lượng phân bố mà không cần lưu toàn bộ từng mẫu trong hệ thống metric. Trong **classic histogram của Prometheus**, mỗi bucket có nhãn **le** (*less than or equal*, nhỏ hơn hoặc bằng) và chứa **số mẫu tích lũy không vượt ngưỡng đó**.

Giả sử có 10 thời lượng giả lập (giây):

~~~text
0.06, 0.09, 0.12, 0.18, 0.20,
0.23, 0.40, 0.48, 0.90, 1.60
~~~

Các buckets tích lũy:

| Bucket le (s) | Số mẫu ≤ ngưỡng | Tỷ lệ tích lũy |
| ---: | ---: | ---: |
| 0,10 | 2 | 20% |
| 0,25 | 6 | 60% |
| 0,50 | 8 | 80% |
| 1,00 | 9 | 90% |
| 2,00 | 10 | 100% |
| +Inf | 10 | 100% |

Đây là histogram dạng **tích lũy**. Bucket **le=0,50** đã bao gồm cả 2 mẫu trong bucket **le=0,10** và 4 mẫu tiếp theo đến 0,25 giây; **không cộng số mẫu từ mọi bucket để lấy tổng số request**.

### 4.1. Ví dụ exposition của Prometheus

Tên series chỉ minh họa dạng phổ biến của Micrometer Prometheus registry; exporter thực có thể khác:

~~~text
app_ai_tool_execution_duration_seconds_bucket{tool_family="retrieval",le="0.1"} 2
app_ai_tool_execution_duration_seconds_bucket{tool_family="retrieval",le="0.25"} 6
app_ai_tool_execution_duration_seconds_bucket{tool_family="retrieval",le="0.5"} 8
app_ai_tool_execution_duration_seconds_bucket{tool_family="retrieval",le="1.0"} 9
app_ai_tool_execution_duration_seconds_bucket{tool_family="retrieval",le="2.0"} 10
app_ai_tool_execution_duration_seconds_bucket{tool_family="retrieval",le="+Inf"} 10
app_ai_tool_execution_duration_seconds_count{tool_family="retrieval"} 10
app_ai_tool_execution_duration_seconds_sum{tool_family="retrieval"} 4.26
~~~

Ở ví dụ:

- **_count = 10**: số mẫu thời lượng đã được ghi nhận.
- **_sum = 4,26 seconds**: tổng thời lượng của 10 mẫu.
- **Mean = 4,26 / 10 = 0,426 seconds**.
- **_bucket{le="1.0"} = 9**: chín trong mười request hoàn tất không quá một giây.
- **_bucket{le="+Inf"} = 10**: tổng số mẫu trong histogram.

Các dòng là **ảnh chụp giá trị tích lũy**. Trong một hệ thống nhiều instance qua thời gian, PromQL thường tính **rate(bucket[5m])** hoặc **increase(bucket[5m])**, không đọc một ảnh chụp rồi coi đó là dữ liệu chỉ của 5 phút gần đây.

### 4.2. Histogram và sample thô khác nhau

Histogram chỉ biết các mẫu nằm ở phía nào của một số ngưỡng, **không lưu đúng từng thời lượng** trong metric time series. Nếu hai yêu cầu lần lượt mất 0,26 s và 0,49 s, chúng có thể rơi vào cùng khoảng (0,25; 0,50]. Từ chỉ các bucket, bạn không thể lấy lại chính xác hai giá trị gốc.

Đổi lại, histogram cho phép theo dõi xu hướng trên lượng lớn request mà không lưu từng latency vào hệ thống metrics. Traces có thể giữ một số yêu cầu chi tiết, nhưng thường được lấy mẫu (sampling), nên không thay thế luôn cho phân bố toàn bộ request.

### 4.3. Histogram không tự có ở mọi Timer

Đăng ký một Timer không có nghĩa exporter đã phát **_bucket**. Micrometer có các cấu hình như **publishPercentileHistogram** hoặc **serviceLevelObjectives**; khả năng xuất bucket phụ thuộc registry, phiên bản và bộ lọc cấu hình. Hãy kiểm tra **scrape thực** trước khi viết truy vấn p95 từ histogram.

## 5. Percentile tính từ histogram là ước lượng

Với các bucket ở mục 4, để tìm p95, ta cần ngưỡng chứa mẫu ở mức 95%. Tỷ lệ tích lũy đến **1,00 s** chỉ đạt 90%; đến **2,00 s** đạt 100%. Vì vậy p95 phải nằm trong **khoảng (1,00; 2,00] s**, chứ histogram không biết chính xác mẫu thật ở 1,60 s.

Trong **Prometheus classic histogram**, hàm histogram_quantile thường nội suy tuyến tính **trong bucket** chứa quantile. Với các buckets ví dụ, p95 được ước lượng gần **1,5 giây**, mặc dù percentile nearest-rank tính từ mẫu thô ở vị trí 10 là **1,6 giây**.

Hai kết quả khác nhau vì **mất thông tin bên trong bucket** và khác phương pháp tính. Không nên coi histogram_quantile là phép khôi phục percentile chính xác từ dữ liệu gốc.

### 5.1. Công thức minh họa nội suy

Giả sử bucket chứa quantile có:

- Cận dưới L.
- Cận trên U.
- Cumulative fraction tại L là \(F_L\).
- Cumulative fraction tại U là \(F_U\).
- Mục tiêu quantile là q, nằm giữa hai fraction này.

Ước lượng tuyến tính đơn giản:

\[
P_q\approx L+\frac{q-F_L}{F_U-F_L}(U-L).
\]

Với q=0,95, L=1,00 s, U=2,00 s, \(F_L=0,90\), \(F_U=1,00\):

\[
P_{95}\approx1,00+\frac{0,95-0,90}{1,00-0,90}(2,00-1,00)
=1,50\;\mathrm{s}.
\]

Đây chỉ là diễn giải cơ bản cho **classic histogram với bucket có cận hữu hạn**. Prometheus có các quy tắc đặc biệt khi quantile rơi vào bucket đầu hoặc bucket +Inf, và các phiên bản/kiểu histogram có thuật toán xử lý khác. Không áp máy móc công thức này cho mọi trường hợp.

### 5.2. Bucket quá thưa làm sai số tăng

Nếu chỉ có bucket **le=1 s** và **le=10 s**, p95 có thể bị nội suy trong một khoảng dài 9 giây, rất kém hữu ích cho SLO 1,5 giây. Các bucket nên được chọn đủ dày **quanh vùng ngưỡng quan trọng**, nhưng không dày tới mức làm tăng chi phí thu thập quá mức.

Nếu phần lớn request nằm vượt ngưỡng hữu hạn cuối cùng và chỉ còn **+Inf**, histogram không đủ độ phân giải để ước lượng tốt phần đuôi. Hãy thiết kế các ngưỡng hữu hạn bao phủ phạm vi latency cần theo dõi.

### 5.3. Đọc percentile phải đi cùng số mẫu

Một p99 tính từ 8 request trong 5 phút có độ bất định rất lớn. Nếu dashboard cảnh báo p99 tăng nhưng tổng số request giảm mạnh, cần đọc **request count**, tỷ lệ lỗi và khoảng thời gian trước khi quy nguyên nhân.

Không nên so p95 của tập **10 request** với p95 của tập **100.000 request** như hai ước lượng có độ tin cậy giống nhau. Các percentile không bảo đảm cung cấp khoảng tin cậy; muốn đánh giá sự khác biệt có ý nghĩa, có thể cần bootstrap/thử nghiệm lặp hoặc cách tiếp cận thống kê phù hợp trên dữ liệu có thể truy xuất.

## 6. Micrometer Timer: dữ liệu nguồn cho histogram thời lượng

Trong Micrometer, **Timer** là loại meter phù hợp để ghi một khoảng thời gian thực thi. Timer theo dõi ít nhất **số mẫu** và **tổng thời lượng**; tùy registry và cấu hình, có thể còn thống kê max, histogram, percentile.

Ví dụ:

~~~java
import java.time.Duration;
import io.micrometer.core.instrument.Timer;

Timer timer = Timer.builder("app.ai.tool.execution.duration")
        .description("Duration of executed tool handler calls")
        .tag("tool_family", "retrieval")
        .tag("outcome", "success")
        .register(registry);

timer.record(Duration.ofMillis(120));
timer.record(Duration.ofMillis(480));
~~~

Nếu chỉ quan tâm hai lượt hoàn tất và thời lượng trung bình:

~~~text
count = 2
totalTime = 0.600 seconds
mean = 0.600 / 2 = 0.300 seconds
~~~

**Không cần một Counter trùng chức năng** chỉ để đếm hai mẫu đã ghi vào Timer. Tuy nhiên, các khái niệm như **model-proposed tool calls**, **tool calls bị dispatcher chặn** và **verified business completions** khác với số tool executions, nên có thể cần Counter riêng.

### 6.1. publishPercentileHistogram

Khi cần truy vấn p95 gộp qua các instance trong một backend hỗ trợ histogram (như Prometheus classic histogram), có thể dùng:

~~~java
Timer timer = Timer.builder("app.ai.tool.execution.duration")
        .description("Tool handler duration")
        .tag("tool_family", "retrieval")
        .publishPercentileHistogram()
        .minimumExpectedValue(Duration.ofMillis(10))
        .maximumExpectedValue(Duration.ofSeconds(10))
        .register(registry);
~~~

**publishPercentileHistogram()** cho biết mong muốn xuất phân bố bucket phù hợp theo khả năng registry. **minimumExpectedValue** và **maximumExpectedValue** là gợi ý để giới hạn miền bucket cần thiết và tránh xuất một dải ngưỡng quá rộng.

Những lựa chọn này **không cắt bỏ hoặc tự ép mọi thời lượng nằm trong [10 ms; 10 s]**. Cấu hình thống kê và cách xuất các mẫu ngoài miền còn tùy registry/implementation; cần kiểm tra scrape và tài liệu phiên bản đang dùng. Không hiểu giới hạn histogram là deadline của nghiệp vụ.

### 6.2. serviceLevelObjectives: bucket ở ngưỡng phục vụ SLO

Giả sử nhóm cần biết có bao nhiêu lời gọi tool hoàn tất trong tối đa **250 ms**, **1 giây** và **3 giây**. Có thể bổ sung những ranh giới này:

~~~java
Timer timer = Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family", "retrieval")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(250),
                Duration.ofSeconds(1),
                Duration.ofSeconds(3))
        .register(registry);
~~~

Những ranh giới SLO giúp trả lời câu hỏi **“Bao nhiêu phần trăm lời gọi không vượt ngưỡng 1 giây?”** từ bucket cụ thể, thay vì bắt buộc ước lượng p95 với các bucket không gần 1 giây.

**Các ngưỡng là ví dụ thiết kế, không phải SLO mặc định của Spring AI.** Tool tra cứu, tool ghi dữ liệu, model sinh câu trả lời và retrieval thường có ngân sách thời gian khác nhau.

### 6.3. publishPercentiles: percentile ở phía client

Micrometer cũng có cấu hình:

~~~java
Timer timer = Timer.builder("app.ai.model.request.duration")
        .publishPercentiles(0.50, 0.95, 0.99)
        .register(registry);
~~~

Nó đề nghị tính và xuất các percentile ở phía client khi registry hỗ trợ. Giá trị này có thể hữu ích cho một instance hoặc một nhóm tags, nhưng **không thể cộng hoặc lấy trung bình trực tiếp các percentile client-side** để suy ra percentile của nhiều instance.

| Cấu hình | Ưu điểm | Giới hạn chính |
| --- | --- | --- |
| **publishPercentiles** | Dễ xem p50/p95 cục bộ | Percentile đã tính không tổng hợp tuyến tính giữa instance |
| **publishPercentileHistogram** | Bucket có thể gộp cho Prometheus classic histogram | Ước lượng phụ thuộc bucket, thêm nhiều series |
| **serviceLevelObjectives** | Đếm được mẫu theo những ngưỡng SLO cụ thể | Không thay thế toàn bộ phân bố nếu bucket thưa |

Một Timer có thể cấu hình nhiều phương thức, nhưng không nên bật tất cả một cách máy móc. Chọn theo câu hỏi vận hành, backend và ngân sách telemetry.

### 6.4. Timer.Sample và thời lượng thực thi

Micrometer hỗ trợ **Timer.Sample** để bắt đầu đo trước và chọn Timer/tag phù hợp khi đã biết kết quả:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";
try {
    executeTool();
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    Timer timer = Timer.builder("app.ai.tool.execution.duration")
            .tag("tool_family", "order")
            .tag("outcome", outcome)
            .register(registry);
    sample.stop(timer);
}
~~~

Cách này giúp ghi **cả ca lỗi**, nhưng chỉ thực sự đo được khi luồng chạy đến phần kết thúc đã instrument. Nếu một thao tác bị treo hoặc hủy ở tầng khác không đi qua nhánh finally, cần đo bổ sung ở **điểm áp deadline/cancellation** và ghi nhãn thiếu quan sát thay vì âm thầm bỏ mẫu.

## 7. Ví dụ Java hoàn chỉnh: đo model/tool/RAG mà không nhầm đơn vị

Để tránh trộn độ trễ giữa các tầng, lớp đo dưới đây sử dụng **ba tên Timer khác nhau**: model request, tool execution và retrieval. Nó không tự xây lại ChatClient hay tool dispatcher; ứng dụng gọi wrapper tại ranh giới phù hợp.

~~~java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.Callable;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class SpringAiLatencyMeters {

    private final MeterRegistry registry;

    public SpringAiLatencyMeters(MeterRegistry registry) {
        this.registry = registry;
    }

    // Đảm bảo tag có cardinality hữu hạn.
    private static String toolFamily(String value) {
        if ("retrieval".equals(value)
                || "order".equals(value)
                || "payment".equals(value)) {
            return value;
        }
        return "other";
    }

    private static String outcomeClass(Throwable failure) {
        if (failure == null) {
            return "success";
        }
        // Ứng dụng có thể mở rộng taxonomy cho timeout/cancelled.
        return "error";
    }

    // Ranh giới: từ lúc gọi handler đến lúc handler kết thúc.
    public <T> T measureTool(
            String rawToolFamily,
            Callable<T> operation
    ) throws Exception {
        String family = toolFamily(rawToolFamily);
        Timer.Sample sample = Timer.start(registry);
        Throwable failure = null;

        try {
            return operation.call();
        } catch (Exception ex) {
            failure = ex;
            throw ex;
        } catch (Error err) {
            failure = err;
            throw err;
        } finally {
            Timer timer = Timer.builder(
                            "app.ai.tool.execution.duration")
                    .description("Executed tool handler duration")
                    .tag("tool_family", family)
                    .tag("outcome", outcomeClass(failure))
                    .minimumExpectedValue(Duration.ofMillis(10))
                    .maximumExpectedValue(Duration.ofSeconds(15))
                    .serviceLevelObjectives(
                            Duration.ofMillis(250),
                            Duration.ofSeconds(1),
                            Duration.ofSeconds(3))
                    .publishPercentileHistogram()
                    .register(registry);
            sample.stop(timer);
        }
    }

    // Ranh giới: một lời gọi provider/model đã hoàn tất.
    public void recordModelLatency(
            String outcome,
            Duration elapsed
    ) {
        String normalized = "success".equals(outcome)
                ? "success" : "error";

        Timer.builder("app.ai.model.request.duration")
                .description("One model request duration")
                .tag("outcome", normalized)
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed);
    }

    // Ranh giới: một lần retriever hoàn tất.
    public void recordRetrievalLatency(
            String sourceFamily,
            Duration elapsed
    ) {
        String source = switch (sourceFamily) {
            case "policy", "knowledge", "orders" -> sourceFamily;
            default -> "other";
        };

        Timer.builder("app.ai.rag.retrieval.duration")
                .description("One retrieval duration")
                .tag("source_family", source)
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(300),
                        Duration.ofSeconds(1))
                .register(registry)
                .record(elapsed);
    }
}
~~~

Lưu ý **recordModelLatency** ở đây nhận một Duration đã được tính ở lớp phù hợp; phương thức không tự đo model end-to-end. **recordRetrievalLatency** tương tự. Nếu application hoặc Spring AI đã phát các Timer có cùng ngữ nghĩa, không nên ghi một bản thứ hai vào cùng meter mà không xác định rõ quyền sở hữu điểm đo.

### 7.1. Kiểm thử bằng dữ liệu cố định

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

var registry = new SimpleMeterRegistry();
var metrics = new SpringAiLatencyMeters(registry);

metrics.recordModelLatency(
        "success", Duration.ofMillis(900));
metrics.recordModelLatency(
        "success", Duration.ofMillis(1100));

metrics.recordRetrievalLatency(
        "policy", Duration.ofMillis(125));
metrics.recordRetrievalLatency(
        "policy", Duration.ofMillis(375));

Timer retrieval = registry.find(
                "app.ai.rag.retrieval.duration")
        .tag("source_family", "policy")
        .timer();

System.out.println(retrieval.count()); // 2
System.out.println(retrieval.totalTime(TimeUnit.SECONDS)); // 0.5
~~~

Ví dụ dùng **SimpleMeterRegistry** để kiểm tra dữ liệu nội bộ; nó không chứng minh histogram buckets đã được xuất sang Prometheus. Muốn kiểm tra **_seconds_bucket**, cần dùng Prometheus registry/exporter phù hợp hoặc một kiểm thử tích hợp endpoint metrics.

### 7.2. Kiểm tra hình dạng series thực tế

Trong một môi trường Micrometer dùng **PrometheusMeterRegistry** tương thích, có thể:

~~~java
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;

PrometheusMeterRegistry prometheusRegistry =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

Timer timer = Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family", "retrieval")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(250),
                Duration.ofSeconds(1))
        .register(prometheusRegistry);

timer.record(Duration.ofMillis(150));
timer.record(Duration.ofMillis(900));

System.out.println(prometheusRegistry.scrape());
~~~

Package **io.micrometer.prometheusmetrics** phù hợp với nhánh Micrometer sử dụng Prometheus client mới; các dự án cũ có thể dùng namespace **io.micrometer.prometheus**. Tên series, số bucket, max và các metadata phải được xác minh qua **scrape thực** của đúng phiên bản, không suy ra chắc chắn từ ví dụ.

### 7.3. Ý nghĩa phép đo trong các trường hợp RAG và tool

- **Tool Timer** chỉ đo handler invocation; nếu model đề nghị gọi tool nhưng bị chặn trước handler, Timer này không ghi mẫu.
- **Model Timer** đo một request provider; một user task nhiều vòng tool/model có thể chứa nhiều model requests.
- **Retrieval Timer** đo một thao tác truy xuất; nếu pipeline retrieval song song từ nhiều nguồn, cần định nghĩa rõ thời lượng từng nguồn và thời gian tổng.
- **Business completion Timer** cần một nguồn hậu điều kiện riêng nếu tác vụ bất đồng bộ; không dùng Tool Timer để thay thế.
- **Evaluation Timer** đo thời gian chấm ca, còn **evaluation verdict Counter** kiểm tra chất lượng. Nhanh không đồng nghĩa đúng.

## 8. Prometheus: các series cần đọc và công thức PromQL

Giả sử exporter phát các series classic histogram cho Timer:

~~~text
app_ai_tool_execution_duration_seconds_count
app_ai_tool_execution_duration_seconds_sum
app_ai_tool_execution_duration_seconds_bucket
~~~

Tên series ở đây chỉ là **dạng ví dụ**; ứng dụng phải kiểm tra tên được xuất từ **/actuator/prometheus** hoặc **registry.scrape()**.

### 8.1. Throughput của tool đã hoàn tất

~~~promql
sum(rate(
  app_ai_tool_execution_duration_seconds_count[5m]
))
~~~

Giá trị là **completed tool attempts per second**, không phải end-to-end tasks/s và cũng không phải verified business completions/s. Nếu một tác vụ gọi tool ba lần, cả ba có thể đi vào count.

### 8.2. Mean latency trên cửa sổ

~~~promql
sum(rate(
  app_ai_tool_execution_duration_seconds_sum[5m]
))
/
sum(rate(
  app_ai_tool_execution_duration_seconds_count[5m]
))
~~~

Đơn vị kết quả là **giây/lần gọi**. Đây là trung bình theo các mẫu trong cửa sổ, không phải giá trị _sum riêng lẻ.

Để phân theo tool family:

~~~promql
sum by (tool_family) (
  rate(app_ai_tool_execution_duration_seconds_sum[5m])
)
/
sum by (tool_family) (
  rate(app_ai_tool_execution_duration_seconds_count[5m])
)
~~~

**Tử và mẫu phải cùng tập nhãn và cùng định nghĩa sự kiện.** Nếu mẫu số bằng 0 hoặc không có đủ mẫu cho rate, cần báo không xác định thay vì điền 0 giây.

### 8.3. p95 và p99 theo tool_family

~~~promql
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Với p99, thay **0.95** bằng **0.99**. Công thức dùng **classic histogram** và giữ label **le** khi gộp. Nó không hoạt động nguyên trạng nếu metric không có bucket hoặc backend dùng một loại histogram khác.

### 8.4. Tỷ lệ hoàn tất dưới ngưỡng SLO

Nếu Timer có bucket **le="1.0"** thật sự được xuất, tỷ lệ tool attempts hoàn tất không quá 1 giây:

~~~promql
sum(rate(
  app_ai_tool_execution_duration_seconds_bucket{le="1.0"}[5m]
))
/
sum(rate(
  app_ai_tool_execution_duration_seconds_count[5m]
))
~~~

Kết quả là **tỷ lệ trong [0,1]**. Phải dùng giá trị **le** đúng chính xác như trong scrape: tùy exporter, nó có thể được biểu diễn là **1**, **1.0** hoặc dạng khác. Nếu không có bucket tại đúng ngưỡng, không nên tự đổi điều kiện lọc sang bucket gần đó rồi gọi là phép đo SLO chính xác.

Quan trọng: biểu thức trên đếm **cả lời gọi lỗi hoàn tất nhanh** nếu Timer ghi chúng và không lọc outcome. Do đó nó đo **latency compliance**, chưa đo **successful service level**. Một yêu cầu vừa **nhanh** vừa **thành công** cần kết hợp điều kiện outcome=success với mẫu số tương ứng:

~~~promql
sum(rate(
  app_ai_tool_execution_duration_seconds_bucket{
    le="1.0",outcome="success"
  }[5m]
))
/
sum(rate(
  app_ai_tool_execution_duration_seconds_count[5m]
))
~~~

Biểu thức thứ hai là tỷ lệ **lời gọi hoàn tất thành công và trong ngưỡng** trên tất cả lời gọi đã hoàn tất có Timer sample. Nó vẫn **không bao gồm request bị treo hoặc bị mất instrumentation** nếu chưa ghi mẫu. Một SLO nghiêm ngặt ở cấp người dùng có thể cần một Counter riêng cho **total attempts including timeout**.

### 8.5. Chuyển giây sang mili giây

Nếu muốn biểu đồ p95 bằng milliseconds:

~~~promql
1000 *
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Trục dashboard phải ghi **ms**, không ghi s. Đừng đổi hai lần ở query và lớp hiển thị.

### 8.6. Lưu ý rate và increase

Các series **_bucket**, **_count**, **_sum** của classic histogram thông thường là các số liệu tích lũy phù hợp với việc lấy rate/increase trên khoảng thời gian. Khi process restart, counter-like series có thể reset; **rate** được thiết kế để xử lý reset trong điều kiện lấy mẫu phù hợp.

Với ít traffic, **rate(...[1m])** có thể rất nhiễu hoặc không đủ mẫu; có thể cần cửa sổ dài hơn và đọc số lượng sample thật. Nếu mục tiêu là số request hoàn tất trong 10 phút, **increase(count[10m])** diễn tả trực tiếp số mẫu trong khoảng đó hơn một tốc độ/s.

### 8.7. Không nhầm p95 qua các cấp

~~~text
p95(model request)    != p95(user request)
p95(tool execution)  != p95(business completion)
p95(retrieval)       != p95(RAG answer)
~~~

Ngay cả khi các bước tuần tự, **tổng các p95 của từng bước không bằng p95 của tổng thời gian một request**. Các phân bố không giữ quan hệ tuyến tính ở percentile; cần đo Timer end-to-end riêng và dùng trace để giải thích những request chậm.

## 9. Tổng hợp histogram nhiều instance và giới hạn của percentile client-side

Giả sử hệ thống Spring AI có ba replica chạy cùng phiên bản service. Mỗi replica ghi Timer riêng. Nếu cần p95 của **toàn hệ thống**, cách sai phổ biến là:

~~~text
p95(replica A) = 0.8 s
p95(replica B) = 1.2 s
p95(replica C) = 3.0 s

(0.8 + 1.2 + 3.0) / 3 = 1.67 s  <-- KHÔNG PHẢI p95 gộp
~~~

Ba replica có thể nhận số request khác nhau; ngay cả khi bằng nhau, percentile không cộng/trung bình được như tổng số mẫu. Để ước lượng p95 chung từ **classic histograms có schema bucket tương thích**, cộng **tốc độ bucket** theo **le** trước khi gọi **histogram_quantile**:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Nếu muốn giữ phân nhóm tool family:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

### 9.1. Điều kiện để tổng hợp có ý nghĩa

1. Các instance đo **cùng đại lượng**: cùng start/end, cùng đơn vị và cùng đối tượng đo.
2. Các histogram có **bucket boundaries tương thích**.
3. Chỉ gộp những labels thực sự có cùng ngữ nghĩa; khi muốn xem sự khác biệt, giữ lại chiều phân nhóm.
4. Không gộp ca thành công với lỗi mà quên giải thích **outcome**.
5. Không coi một phần dữ liệu bị thiếu scrape như toàn bộ lưu lượng.
6. Không trộn các phiên bản Timer đã đổi ngữ nghĩa mà giữ nguyên tên.

Ví dụ, nếu một phiên bản ghi **thời gian tool handler**, phiên bản khác ghi **cả thời gian chờ queue** dưới cùng tên, percentile gộp không còn miêu tả một phép đo thống nhất.

### 9.2. Vấn đề thay đổi cơ cấu tác vụ

Một hệ thống có:

- **Tra cứu đơn hàng**: đa số yêu cầu nhanh.
- **RAG phân tích hợp đồng dài**: yêu cầu lâu hơn nhiều.

Nếu tuần A có 90% tra cứu đơn hàng và 10% phân tích hợp đồng, còn tuần B có 40% tra cứu và 60% phân tích, p95 chung có thể tăng mạnh dù **p95 của từng nhóm không đổi**.

Đây là vấn đề **case mix** (thay đổi tỷ trọng các nhóm). Khi điều tra hồi quy, xem p95 theo **route_family, case_type, tool_family hoặc workload class** hữu hạn, rồi so cùng dataset hoặc chuẩn hóa phân bố tác vụ nếu cần.

**Không dùng raw user ID, order ID hoặc prompt làm labels** chỉ để giữ mọi khác biệt: cardinality sẽ tăng và có thể lộ dữ liệu. Những thông tin riêng lẻ nên đặt trong traces hoặc kho kết quả đánh giá được phân quyền.

## 10. Chọn bucket theo SLO và ngân sách cardinality

Một histogram rất chi tiết không phải lúc nào cũng tốt. Mỗi bucket bổ sung, khi kết hợp với tags, có thể tạo thêm time series trong Prometheus.

### 10.1. Bắt đầu từ câu hỏi cần quyết định

Giả sử nhóm muốn biết:

- **95% retrieval** phải hoàn tất trong 500 ms.
- **99% tool status reads** nên dưới 1 giây.
- **Timeout** xảy ra khi vượt 5 giây theo hợp đồng của tool.

Một dãy bucket hữu hạn minh họa có thể là:

~~~text
0.05 s
0.10 s
0.25 s
0.50 s   <- ngưỡng SLO retrieval
0.75 s
1.00 s   <- ngưỡng cho tool reads
2.00 s
3.00 s
5.00 s   <- ngưỡng deadline
10.0 s
+Inf
~~~

Đây là **bộ ngưỡng minh họa**. Với model sinh câu trả lời dài, phạm vi vài chục giây có thể quan trọng hơn 50 ms; với API nội bộ nhỏ, khoảng dưới 100 ms lại đáng quan tâm hơn. Không áp chung một histogram cho mọi loại thao tác chỉ vì đều dùng Timer.

### 10.2. SLO bucket và histogram percentile phục vụ hai việc khác nhau

**Ngưỡng SLO**: “Bao nhiêu yêu cầu không vượt 500 ms?” Một bucket tại 0,5 s cho phép đếm trực tiếp số mẫu dưới ngưỡng, nếu có đủ bằng chứng và mẫu số.

**Percentile**: “Ngưỡng mà 95% yêu cầu nằm dưới là bao nhiêu?” Cần ước lượng từ phân bố; độ chính xác phụ thuộc các bucket ở vùng chứa quantile.

Không bắt buộc phải có nhiều bucket để tính **tỷ lệ đáp ứng một ngưỡng SLO cụ thể**, nhưng cần đủ bucket để percentile có độ phân giải hợp lý và để điều tra nhiều miền thời lượng.

### 10.3. Ngân sách series

Giả sử một Timer có:

| Chiều | Số giá trị |
| --- | ---: |
| tool_family | 4 |
| outcome | 3 |
| region | 2 |
| deployment_cohort | 2 |

Có thể có **4 × 3 × 2 × 2 = 48 tổ hợp tags**. Nếu mỗi tổ hợp xuất 20 buckets cùng count, sum và một số series bổ sung, tổng số series có thể vượt **1.000** chỉ cho một metric.

Vì vậy:

- Chỉ giữ tags thực sự cần cho phân tích hoặc SLO.
- Giới hạn tập giá trị của mỗi tag.
- Dùng bucket phù hợp thay vì bật cấu hình rộng nhất.
- Không tạo nhãn độc nhất theo mỗi request/case/document.
- Kiểm tra series thực tế và chi phí lưu trữ sau khi bật histogram.

### 10.4. Chọn cửa sổ truy vấn

Các cửa sổ ngắn giúp phát hiện biến động nhanh nhưng thiếu mẫu hoặc nhiều nhiễu. Cửa sổ dài giúp ước lượng ổn định hơn nhưng làm mờ sự kiện đột biến.

| Cửa sổ | Ưu điểm | Giới hạn |
| --- | --- | --- |
| 1 phút | Phản ứng nhanh | Dễ thiếu mẫu, nhất là p99 |
| 5 phút | Phổ biến cho dashboard | Vẫn nhiễu với traffic thấp |
| 30 phút | Mượt hơn | Chậm phát hiện hồi quy ngắn |
| 1 ngày | Xu hướng tổng quát | Trộn nhiều đợt deploy, tải và case mix |

Không có cửa sổ đúng tuyệt đối. Với bộ đánh giá offline, **một evaluation run với cùng dataset** thường là đơn vị so sánh hữu ích hơn nhiều so với mọi request production trong cùng một giờ.

## 11. Timeout, cancellation và những mẫu không hoàn tất

Một biểu đồ p95 chỉ từ **những request thành công** có thể tạo ảo giác hệ thống nhanh lên khi các request chậm nhất chuyển thành timeout và bị loại khỏi mẫu. Ví dụ:

~~~text
Trước thay đổi:
  100 requests
  100 complete
  p95 = 1.2 s

Sau thay đổi:
  100 requests
   85 complete
   15 timeout at 10 s
  p95 chỉ trên 85 successes = 0.9 s
~~~

Chỉ số **p95 success = 0,9 s** trông tốt hơn, nhưng **15% timeout** khiến trải nghiệm tổng thể tệ hơn. Đây là **selection bias**: tập mẫu đo đã thay đổi.

### 11.1. Thiết kế metric để không che khuất thất bại

| Số liệu | Công cụ đo | Ý nghĩa |
| --- | --- | --- |
| Thời gian của các attempt hoàn tất | Timer với outcome | Phân bố execution latency |
| Số attempt bắt đầu | Counter bắt đầu | Mẫu số gồm cả attempt chưa kết thúc |
| Số timeout/cancelled | Counter theo reason/outcome | Theo dõi lỗi và bị hủy |
| Số in-flight hiện tại | Gauge | Phát hiện backlog |
| Thời gian đến deadline | Timer/counter ở điểm deadline | Đo nhánh timeout có thể quan sát |
| Verified business outcome | Oracle + backend state | Phân biệt hoàn tất với tiếp nhận |

Đừng ghi thời lượng **0** cho request timeout chỉ vì thiếu thời gian kết thúc; cũng đừng ghi **COMPLETED** khi công cụ mới trả ACCEPTED.

### 11.2. Right-censoring và tác vụ đang chạy

Một tác vụ đã chạy 5 giây nhưng chưa kết thúc khi dashboard được đọc **không phải một mẫu duration hoàn tất bằng 5 giây**, cũng không phải một mẫu 0 giây. Đây là dạng quan sát **chưa hoàn tất** (*right-censored*, tùy mô hình thống kê).

Nếu bài toán cần ước lượng thời gian hoàn tất của tác vụ rất dài hoặc bất đồng bộ, chỉ xem percentile của những tác vụ hoàn tất có thể gây thiên lệch. Cần theo dõi:

- Số tác vụ chưa hoàn tất.
- Tuổi của tác vụ đang pending.
- Số deadline bị vượt.
- Kết quả cuối VERIFIED_SUCCESS/VERIFIED_FAILURE/UNKNOWN.
- Cửa sổ quan sát và quy tắc hết hạn chờ.

Đối với các tác vụ đủ đơn giản, Timer hoàn tất cộng timeout rate có thể đủ. Đối với workflow hàng giờ hoặc nhiều ngày, cần thêm **mô hình sự kiện trạng thái**, không ép mọi thứ vào histogram request latency.

### 11.3. Khi có retry

Nếu một user task gọi tool ba lần vì hai lần đầu timeout:

~~~text
Tool attempt #1: timeout
Tool attempt #2: timeout
Tool attempt #3: success
Final user task: success
~~~

Phân bố **tool attempt latency** có ba mẫu (nếu instrument đủ), nhưng **task duration** có một mẫu. Không dùng số tool attempts làm mẫu số thành công tác vụ. Retry có thể tăng cost và end-to-end latency dù một attempt thành công riêng lẻ nhanh.

Giữ thêm các chỉ số **retries per task**, **model turns per task** và **cost per verified success** để đánh giá ảnh hưởng thật của thay đổi prompt/model/tool pipeline.

## 12. Streaming: time-to-first-token khác time-to-last-token

Với phản hồi streaming, người dùng có thể thấy chữ đầu tiên sau 300 ms nhưng phải đợi thêm 15 giây để nhận đầy đủ nội dung. Nếu chỉ đo **time to first token (TTFT)**, dashboard có thể kết luận trải nghiệm tốt trong khi câu trả lời quá dài hoặc stream bị ngắt.

| Tình huống | TTFT | Full response | Ý nghĩa |
| --- | ---: | ---: | --- |
| Model trả nhanh một câu ngắn | 0,25 s | 0,90 s | Tốt ở cả hai |
| Model trả lời dài | 0,25 s | 12,0 s | Phản hồi sớm nhưng chậm hoàn tất |
| Stream khởi tạo chậm | 4,00 s | 5,00 s | Khởi đầu chậm |
| Stream lỗi sau một phần nội dung | 0,30 s | Không hoàn tất hợp lệ | Không chấm full success |

Định nghĩa TTFT phải thống nhất: tính từ lúc request đến ứng dụng hay từ lúc gọi provider? “Token đầu tiên” là token do model sinh hay chunk metadata đầu tiên? Nếu API gửi sự kiện mở stream ngay lập tức, không được coi đó là token nội dung nếu mục tiêu đo là lúc người dùng nhìn thấy nội dung có ý nghĩa.

Một thiết kế metric rõ ràng:

~~~text
app.ai.response.first_token.duration  -> Timer
app.ai.response.full.duration         -> Timer
app.ai.response.stream.completed      -> Counter (status)
~~~

**Tên là ví dụ ứng dụng tự định nghĩa.** Nếu Spring AI/provider đã phát những meter tương đương, ưu tiên dùng instrumentation có sẵn và tài liệu của đúng phiên bản.

### 12.1. Lời gọi streaming thất bại sau chunk đầu

Một stream có thể phát token đầu rồi lỗi. TTFT có một mẫu hợp lệ, nhưng **full response success** không được đánh PASS. Cần lưu outcome, số token/chunk đã phát nếu có, và lý do lỗi. Không suy ra hoàn thành chỉ từ sự kiện mở stream hoặc HTTP status của kết nối.

### 12.2. Khác biệt client-side và server-side

Thời gian từ lúc **client gửi yêu cầu** đến khi **client nhận nội dung** có thể gồm network và rendering, trong khi Timer đặt trong server chỉ thấy phần xử lý server. Muốn đo trải nghiệm người dùng toàn diện, có thể cần telemetry phía client. Đừng đặt tên server processing duration là "user-perceived latency" nếu không đo đủ ranh giới.

## 13. Kết hợp độ trễ với chất lượng và chi phí Spring AI

Một truy vấn RAG nhanh chưa chắc có nguồn đúng. Một tool nhanh chưa chắc gọi đúng đối số. Khi đánh giá thay đổi model hoặc prompt, cần đặt những phân bố latency cạnh **verdict của oracle**, **usage** và **bằng chứng nghiệp vụ**.

| Lớp | Chỉ số chất lượng | Chỉ số thời gian | Chỉ số nguồn lực |
| --- | --- | --- | --- |
| Model | Groundedness, factual correctness | Model request p50/p95 | Input/output tokens |
| Tool calling | Chọn tool/đối số đúng, kết quả nghiệp vụ đạt | Tool execution p95, task p95 | Call count, retry, phí API |
| RAG | Retrieval relevance, source freshness, answer faithfulness | Retrieval p95, answer p95 | Documents/chunks/tokens |
| Multi-turn | Context consistency, trajectory success | Time per turn, end-to-end scenario | Số lượt model/tool |
| Evaluation | PASS/FAIL/INCONCLUSIVE, coverage | Eval latency p95 | Số lần gọi evaluator, chi phí chấm |

### 13.1. Đừng chỉ lọc những ca PASS để so tốc độ

Giả sử bản Prompt A trả đúng 95/100 ca với p95=2,5 s; bản B chỉ đúng 60/100 ca nhưng p95 trên ca PASS là 1,0 s. Nếu báo “B nhanh hơn 2,5 lần” mà không nói tỷ lệ FAIL, kết luận không phục vụ mục tiêu chất lượng.

Nên báo:

1. **Latency trên tất cả ca có observation hợp lệ** và taxonomy outcome.
2. **Latency của ca PASS** như một lát cắt bổ sung, không thay chỉ số tổng.
3. **Verified success** và tỷ lệ INCONCLUSIVE.
4. **Timeout/cancellation rate**.
5. **Cost per verified success**, không chỉ cost/request.

Mỗi chỉ số phải có mẫu số và miền quan sát rõ ràng. Phân tầng theo **case_type** nếu bộ dataset gồm ca khó/dễ khác nhau.

### 13.2. Prompt dài hơn có thể tăng latency và chất lượng

Một prompt có nhiều chỉ dẫn về kiểm tra nguồn và quyền có thể tăng input tokens, tăng thời lượng model nhưng giảm hallucination. Nhìn riêng Timer tăng có thể khiến nhóm bỏ mất lợi ích chất lượng. Cần đánh giá trade-off theo yêu cầu sản phẩm, không mặc định latency thấp luôn tốt hơn mọi mặt.

### 13.3. Không hiểu histogram là bằng chứng nhân quả

Histogram cho biết **phân bố thay đổi**, không tự giải thích **vì sao**. Muốn quy nguyên nhân, cần traces và thông tin phiên bản/ca thử:

~~~text
case_id -> prompt/model version -> model calls
        -> tool/retrieval spans -> source data
        -> answer + oracle verdict -> latency + cost
~~~

Không đưa case_id, conversation_id hay trace_id vào labels Prometheus cho từng request. Dùng kho trace và kết quả đánh giá có phân quyền; metric chỉ chứa nhóm giá trị hữu hạn như tool_family, outcome và case_type.

## 14. Ví dụ điều tra hồi quy: p95 tăng sau khi đổi prompt

Giả sử cùng bộ **200 ca RAG + tool calling** được chạy với hai prompt, model, dữ liệu, tool fixtures và oracle giống nhau. Số liệu **giả định**:

| Chỉ số | Prompt A | Prompt B |
| --- | ---: | ---: |
| Verified trajectory success | 84% | 89% |
| Fact-check PASS trên ca chấm được | 91% | 90% |
| End-to-end p50 | 1,1 s | 1,3 s |
| End-to-end p95 | 2,8 s | 4,9 s |
| Tool execution p95 | 0,45 s | 0,47 s |
| Retrieval p95 | 0,31 s | 0,32 s |
| Model request p95 | 1,7 s | 2,3 s |
| Input tokens/model request | 820 | 1.380 |
| Model calls/user task | 1,4 | 2,1 |
| Estimated cost/verified success | 0,012 USD | 0,019 USD |

**Điều có thể khẳng định từ bảng:** thành công toàn trajectory tăng, độ trễ và chi phí tăng, model calls/token tăng, còn p95 tool/retrieval gần như không đổi. **Điều chưa thể khẳng định:** nguyên nhân duy nhất là prompt dài hơn hay model chậm đi. Các thay đổi trong lịch sử memory hoặc cách model quyết định gọi tool cũng có thể ảnh hưởng.

### Quy trình điều tra

1. **Kiểm tra metric contract:** p95 của hai bản có cùng start/end, đơn vị giây, tags, histogram config và cửa sổ không?
2. **Kiểm tra coverage:** cả 200 ca có được chấm và đo đúng; ca lỗi/timeout có bị lọc khác nhau không?
3. **Phân nhóm theo case type:** p95 tăng ở RAG, tool-only hay multi-turn?
4. **Xem token/call count:** model có phải đọc thêm nhiều context hoặc sinh thêm vòng gọi không?
5. **Mở traces chậm:** request nào tốn nhiều model turns, chờ provider, retrieval hoặc retry?
6. **Đối chiếu oracle:** các ca tăng thời gian có mang lại kết quả tốt hơn hay chỉ là gọi thừa?
7. **Quyết định trade-off:** mục tiêu chất lượng và ngân sách latency/cost của sản phẩm có chấp nhận được không?

Ví dụ, nếu trace cho thấy model tự gọi lại cùng tool khi dữ liệu đã đủ mới, hướng xử lý có thể là cải thiện chính sách dừng hoặc cách cung cấp tool result. Nếu gọi lại do timeout thật, cần điều tra backend/transport. **Chung một biểu hiện p95 tăng có thể có nhiều nguyên nhân khác nhau.**

## 15. Thiết kế dashboard độ trễ có khả năng giải thích

Một dashboard chỉ có một đường **p95 toàn hệ thống** thường không đủ để xác định sự cố. Nên kết hợp **khối lượng mẫu**, **phân bố**, **tỷ lệ lỗi** và **các lớp xử lý**.

### 15.1. Bảng cấu trúc dashboard đề xuất

| Nhóm panel | Metric/đơn vị | Câu hỏi được trả lời |
| --- | --- | --- |
| Traffic | Request/task throughput, tasks/s | Có bao nhiêu tác vụ đang vào hệ thống? |
| Model latency | p50, p95, p99 theo seconds | Model request có chậm hơn? |
| Tool latency | p95 theo tool_family/outcome | Nhóm công cụ nào gây đuôi chậm? |
| Retrieval latency | p50/p95 và số docs/retrieval | Retriever có bị chậm hoặc trả ít nguồn? |
| End-to-end | p95 và SLO compliance | Người dùng thực sự đợi bao lâu? |
| Errors | Timeout/cancelled/error rate | Ca chậm có bị loại khỏi Timer thành công? |
| Work in progress | In-flight/queue depth Gauge | Có backlog đang tích tụ? |
| Quality | Verified success, fact-check, grounding | Có nhanh hơn nhưng sai hơn không? |
| Resources | Tokens/request, calls/task, cost/success | Chậm do nhiều model calls hay context? |
| Observability coverage | Cỡ mẫu, missing usage, missing trace | Có đủ dữ liệu để kết luận? |

Trục của mỗi panel phải ghi **đơn vị phù hợp**. Ví dụ: **tool p95 (s)** khác **tool p95 (ms)**; **requests/s** khác **requests per evaluation run**.

### 15.2. Thực hành đặt ngưỡng cảnh báo

Ví dụ một nhóm quyết định:

~~~text
Latency objective:
  >= 95% successful user tasks hoàn tất <= 3 seconds

Reliability objective:
  timeout rate <= 1% trên tổng user tasks

Quality gate:
  verified task success >= 90% trên dataset đã cố định
  unauthorized side effects = 0
~~~

Những ngưỡng trên chỉ để minh họa cách tách các mục tiêu; **không phải tiêu chuẩn mặc định của Spring AI**. Bộ đo phải định nghĩa chính xác successful user task, điểm bắt đầu/kết thúc, xử lý timeout và tập ca. Nếu ứng dụng chỉ có Timer cho **model requests**, không được dùng nó để tuyên bố đạt SLO **user tasks**.

### 15.3. Ưu tiên bucket ratio nếu câu hỏi là một ngưỡng

Để trả lời **“Bao nhiêu request dưới 3 giây?”**, bucket đúng ngưỡng giúp tính tỷ lệ trực tiếp. Để trả lời **“p95 hiện là bao nhiêu?”**, dùng histogram_quantile. Hai biểu thức có mục tiêu khác nhau; một p95 ước lượng xấp xỉ 3 giây không thay thế hoàn toàn phép kiểm tra tỷ lệ đáp ứng SLO ở bucket 3 giây.

Nếu dùng p95 làm alert, cần xem cả cỡ mẫu và histogram configuration. Với traffic rất thấp, một outlier có thể làm p95 dao động mạnh; thêm điều kiện về lưu lượng và khoảng thời gian có thể giảm báo động giả.

## 16. Kiểm thử histogram và percentile bằng dữ liệu cố định

Bộ đánh giá tự động cần có **metric contract tests**. Mục tiêu không phải chỉ xác nhận Timer tồn tại, mà là kiểm tra ý nghĩa của những sample đã ghi và cách exporter trình bày chúng.

### 16.1. Những phép kiểm có thể quyết định bằng mã

| Test | Fixture | Điều kiện đạt |
| --- | --- | --- |
| Đúng đơn vị | Duration 125 ms và 750 ms | count=2, totalTime=0,875 seconds |
| Include error | Tool ném exception sau khi chạy | Timer ghi một sample outcome=error |
| SLO bucket | Durations 100, 250, 800 ms | Bucket 1 s có đủ 3 mẫu |
| Không có histogram | Timer không bật bucket | Không giả định _bucket tồn tại |
| Bucket tích lũy | Các ngưỡng 0,1/0,25/1 s | Giá trị bucket không giảm khi le tăng |
| Mean | sum và count khác 0 | Mean = sum/count, đúng đơn vị |
| p95 sample nhỏ | 10 mẫu | Báo cỡ mẫu; không kết luận quá mạnh |
| Reset process | Counter reset sau restart | Truy vấn rate/increase xử lý đúng |
| Label cardinality | 1.000 user IDs khác nhau | Không phát 1.000 series theo user ID |
| No successful observations | Tất cả lỗi timeout | SLO report không đánh PASS giả |
| Streaming failure | Có first token rồi stream lỗi | Không chấm full response COMPLETED |
| Wrong timer boundary | Model call vs task call | Hai tên metric, hai mẫu số rõ |

### 16.2. Kiểm thử mean bằng SimpleMeterRegistry

Một ví dụ đơn giản để kiểm tra tính đúng của Timer:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

var registry = new SimpleMeterRegistry();
Timer timer = Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family", "retrieval")
        .register(registry);

timer.record(Duration.ofMillis(125));
timer.record(Duration.ofMillis(750));

if (timer.count() != 2) {
    throw new AssertionError("Wrong Timer sample count");
}

double sumSeconds = timer.totalTime(TimeUnit.SECONDS);
if (Math.abs(sumSeconds - 0.875) > 1e-9) {
    throw new AssertionError("Wrong Timer total seconds");
}

double meanSeconds = sumSeconds / timer.count();
if (Math.abs(meanSeconds - 0.4375) > 1e-9) {
    throw new AssertionError("Wrong mean latency");
}
~~~

Kiểm thử này **không khẳng định cách Prometheus nội suy p95**. Với histogram, cần kiểm tra riêng **PrometheusMeterRegistry** hoặc endpoint scrape của phiên bản đang dùng. Tránh so khớp toàn bộ văn bản scrape nguyên xi nếu các giá trị runtime hoặc thứ tự sample có thể thay đổi; kiểm tra tên, labels, bucket boundaries và số liệu quan trọng.

### 16.3. Kiểm thử với Prometheus exposition

Quy trình gợi ý:

1. Cấp một registry/ứng dụng sạch, không chịu ảnh hưởng từ ca khác.
2. Tạo Timer có histogram và SLO buckets cần thiết.
3. Ghi các Duration cố định.
4. Lấy scrape text và kiểm tra **_count, _sum, _bucket** cùng nhãn le.
5. Kiểm tra các buckets có tính tích lũy và ngưỡng đã chọn xuất hiện.
6. Chạy PromQL tương ứng trên môi trường tích hợp nếu mục tiêu cần xác minh toàn bộ đường đi.
7. Ghi phiên bản Micrometer/Prometheus registry và những giới hạn nếu tên/định dạng khác.

**Lưu ý:** việc có bucket ở ngưỡng đúng SLO không bảo đảm histogram_quantile chính xác tuyệt đối. Test không nên đòi một p95 bằng mẫu nearest-rank nếu backend thực tế sử dụng nội suy trong bucket.

## 17. Các sai lầm thường gặp khi đọc độ trễ

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Báo mean là trải nghiệm của mọi người dùng | Đuôi chậm bị che khuất | Xem phân bố/p95 và timeout |
| Hiểu p95 là “95% request mất đúng số giây đó” | p95 là ngưỡng, không phải thời lượng cố định | Nêu định nghĩa quantile |
| Lấy trung bình p95 từ nhiều replica | Percentile không cộng gộp tuyến tính | Gộp histogram buckets tương thích |
| Cộng các p95 của model/tool/RAG | Percentile của tổng không bằng tổng percentile | Đo end-to-end riêng |
| Coi histogram bucket là nhóm rời nhau | Classic buckets tích lũy | Không cộng trực tiếp bucket counts |
| Bỏ nhãn le khi gộp buckets | Mất ranh giới histogram | Giữ le trong sum by |
| Tự đọc _sum như mean | _sum là tổng thời lượng | Chia rate(sum) cho rate(count) |
| Hiểu _count của Timer là số giây | _count là số mẫu | Dùng _sum cho tổng seconds |
| Không bật histogram nhưng dùng _bucket | Series không tồn tại | Bật histogram/SLO nếu cần |
| Bucket quá thưa quanh p95 | Nội suy kém chính xác | Chỉnh bucket resolution |
| Dùng p99 từ vài request | Ước lượng thiếu ổn định | Ghi count, mở rộng cửa sổ |
| Chỉ ghi Timer trên success | Timeout/ca chậm bị loại | Đo cả lỗi và báo failure rate |
| Ghi timeout bằng 0 ms | Làm latency thấp giả | Ghi đúng deadline/cancellation event |
| Dùng accepted latency làm business completion | Hai trạng thái khác nhau | Đo source of truth và hậu điều kiện |
| Trộn streaming first token với full output | Hai trải nghiệm khác nhau | Hai Timer với ranh giới rõ |
| Gắn user ID vào histogram labels | Cardinality tăng mạnh | Phân nhóm hữu hạn, ID trong trace |
| Trộn traffic RAG khó/dễ giữa hai bản | p95 chịu ảnh hưởng case mix | Dùng cùng dataset hoặc phân tầng |
| So p95 từ hai exporter có schema khác nhau | Khác bucket/đơn vị/phương pháp | Version hóa metric contract |
| Chỉ xem latency mà không xem quality | Nhanh nhưng sai vẫn bị đánh giá cao | Kết hợp oracle và error/usage |

Một tình huống cần lưu ý đặc biệt: dashboard có thể báo p95 giảm trong khi **thực tế timeout tăng**. Đó thường là lý do kiểm tra **phạm vi mẫu và coverage** trước khi tuyên bố có cải thiện.

## 18. Bài thực hành

**Bối cảnh:** bạn có một ứng dụng Spring AI gồm một ChatClient, công cụ **get_order_status**, một retriever chính sách và bộ đánh giá relevance/fact checking. Nhiệm vụ là thiết kế hệ thống đo độ trễ phục vụ phân tích thay đổi prompt hoặc pipeline.

### Phần A — Định nghĩa chính xác thời gian

1. Viết định nghĩa **bắt đầu/kết thúc** của model request latency, tool execution latency, RAG retrieval latency và end-to-end response latency.
2. Phân biệt thời điểm nhận yêu cầu **ACCEPTED** với thời điểm **VERIFIED_COMPLETED** của một tác vụ nghiệp vụ giả lập.
3. Nếu dùng streaming, định nghĩa time to first token và time to full response; nêu cách xử lý stream lỗi sau chunk đầu.
4. Lập bảng đơn vị gốc và đơn vị hiển thị cho từng Timer.

### Phần B — Tính toán từ các mẫu

Cho 10 thời lượng (s):

~~~text
0.06, 0.09, 0.12, 0.18, 0.20,
0.23, 0.40, 0.48, 0.90, 1.60
~~~

1. Tính mean và p50/p95 nearest-rank.
2. Tạo bảng classic histogram theo ngưỡng **0,1; 0,25; 0,5; 1; 2; +Inf giây**.
3. Tìm bucket chứa p95 và ước lượng p95 bằng nội suy tuyến tính.
4. Giải thích vì sao nội suy bucket có thể khác percentile từ mẫu thô.
5. Tính tỷ lệ request hoàn tất trong tối đa 1 giây từ bucket.

**Đáp án kiểm tra nhanh:** mean = **0,426 s**; p50 nearest-rank = **0,20 s**; p95 nearest-rank = **1,60 s**; bucket p95 nằm trong **(1; 2] s**, nội suy minh họa ≈ **1,50 s**; tỷ lệ dưới hoặc bằng 1 giây = **9/10 = 90%**.

### Phần C — Micrometer và Prometheus

1. Tạo Timer cho **app.ai.tool.execution.duration** với **publishPercentileHistogram**.
2. Thêm SLO buckets 250 ms, 1 s và 3 s.
3. Ghi một số lượt success, error và timeout giả lập; xác minh outcome được phân nhóm bằng tag hữu hạn.
4. Kiểm tra count và totalTime bằng SimpleMeterRegistry.
5. Dùng PrometheusMeterRegistry hoặc endpoint Actuator được cấp quyền để xem tên series **_seconds_count/_sum/_bucket** thực tế.
6. Viết PromQL tính mean, p95 theo tool_family và tỷ lệ lời gọi dưới 1 giây.
7. Xác nhận đơn vị giây trong metric và đơn vị hiển thị của dashboard.

### Phần D — Hồi quy chất lượng và chi phí

1. Chuẩn bị cùng 100 ca RAG/tool calling với fixture và oracle cố định.
2. Chạy hai phiên bản prompt/model; báo **p50, p95, p99**, count và tỷ lệ timeout.
3. Báo thêm **verified outcome**, relevance, fact-check, số model/tool calls và input/output tokens.
4. Chọn ca chậm nhưng PASS và ca nhanh nhưng FAIL; dùng traces phân biệt nguyên nhân.
5. Thử thay tỷ trọng ca RAG khó/dễ và giải thích sự thay đổi p95 chung.
6. Mô phỏng một request bị treo quá deadline: quyết định metric nào ghi được và khi nào phải đánh dấu UNKNOWN/PENDING.
7. Trình bày quyết định chọn phiên bản: chất lượng, độ trễ, chi phí và rủi ro nào quan trọng nhất với mục tiêu sản phẩm?

### Câu hỏi tự kiểm tra

- p95 có nghĩa là 95% request mất đúng thời gian p95 hay không?
- Vì sao p95 nearest-rank và p95 từ classic histogram có thể khác nhau?
- Trong Prometheus, nhãn **le** dùng để biểu diễn điều gì?
- Vì sao không được cộng số mẫu của tất cả buckets classic histogram?
- Khi nào nên dùng histogram_quantile, khi nào dùng tỷ lệ bucket tại ngưỡng SLO?
- Vì sao client-side percentile không thể lấy trung bình giữa các instance?
- Nếu bucket lớn nhất chỉ là +Inf, điều đó ảnh hưởng thế nào tới độ chính xác ở phần đuôi?
- Một Timer không có _bucket có nghĩa là không ghi latency hay không?
- Nếu timeout tăng nhưng p95 trên ca thành công giảm, kết luận hệ thống nhanh hơn có đúng không?
- Vì sao thời gian model request khác thời gian người dùng chờ phản hồi hoàn chỉnh?
- Khi stream gửi token đầu tiên nhưng thất bại trước khi xong, metric nào vẫn có dữ liệu hợp lệ?
- Tại sao phải so latency với verified success, fact checking, token và cost?

## 19. Những điều cần ghi nhớ

1. **Độ trễ luôn có ranh giới đo và đơn vị.** Model, tool, retrieval, streaming, end-to-end và business completion là những đại lượng khác nhau.
2. **Mean, p50, p95, p99 và max cho các góc nhìn khác nhau.** Một trung bình nhỏ không loại trừ những request rất chậm.
3. **Classic histogram của Prometheus có bucket tích lũy theo le.** _count là số mẫu, _sum là tổng thời lượng, _bucket là số mẫu không vượt ngưỡng.
4. **Percentile từ histogram là ước lượng theo bucket.** Càng thưa ở vùng quan trọng, độ chính xác càng kém; số mẫu và thời gian quan sát cũng ảnh hưởng khả năng diễn giải.
5. **Micrometer Timer là điểm ghi thời lượng phù hợp.** Cấu hình publishPercentileHistogram, publishPercentiles và serviceLevelObjectives theo mục tiêu, backend và ngân sách telemetry.
6. **Không tổng hợp percentile bằng cộng hoặc trung bình.** Với classic histogram tương thích, gộp bucket rates trước khi dùng histogram_quantile.
7. **p95 phải đi cùng throughput, errors, timeouts và coverage.** Chỉ đo ca PASS có thể che những ca chậm nhất.
8. **Độ trễ theo từng bước không thay độ trễ end-to-end.** Nhiều tool/model calls, retry hoặc streaming tạo thêm thời gian và chi phí.
9. **Metrics cần được đặt cạnh chất lượng và bằng chứng thực tế.** Relevance, fact checking, verified task success và traces giúp phân biệt nhanh do tối ưu với nhanh vì bỏ qua bước cần thiết.
10. **Đánh giá hồi quy trên cùng dataset và metric contract.** Giữ nhất quán start/end, đơn vị, tags, bucket configuration và cách xử lý thiếu dữ liệu trước khi kết luận một phiên bản tốt hơn.

## Tài liệu tham khảo

- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer, Duration, recording, count và total time.
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): publishPercentileHistogram, publishPercentiles, SLO buckets và khả năng tổng hợp.
- [Micrometer Reference — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): registry, exposition và cấu hình liên quan.
- [Micrometer Reference — Meter Naming](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): tên logic và quy tắc xuất tên theo registry.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): observation và metrics cho ChatClient, model và tool trong hệ sinh thái Spring AI.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, endpoint metrics và export.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): classic histogram, cumulative buckets và cách diễn giải quantile.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): histogram_quantile, rate, increase và các hàm thống kê.
- [Prometheus — Native Histograms](https://prometheus.io/docs/specs/native_histograms/): giới thiệu cách biểu diễn native histogram khác classic histogram.

**Lưu ý về phiên bản và áp dụng thực tế:** tên series, khả năng xuất max/percentiles, loại histogram, cách cấu hình SLO buckets và API quan sát Spring AI có thể khác theo phiên bản Micrometer, Prometheus client, Spring Boot và backend telemetry. Các tên **app.ai** và ngưỡng SLO trong bài chỉ là ví dụ tự định nghĩa. Khi triển khai, cần kiểm tra **API của đúng phiên bản và scrape thực tế**, đồng thời bảo đảm quyền truy cập và bảo vệ dữ liệu nhạy cảm trong metrics/traces.
