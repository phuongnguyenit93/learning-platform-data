# Phân biệt tên Micrometer với tên xuất ra Prometheus

Khi dùng Micrometer trong ứng dụng Spring AI, lập trình viên thường đăng ký một metric mang tên **app.ai.tool.execution.duration**, nhưng trên trang **/actuator/prometheus** lại nhìn thấy những chuỗi như **app_ai_tool_execution_duration_seconds_count**, **app_ai_tool_execution_duration_seconds_sum** hoặc **app_ai_tool_execution_duration_seconds_bucket**. Tìm nguyên tên Java trong PromQL rồi không thấy dữ liệu là một lỗi rất thường gặp. Nguy hiểm hơn, người viết dashboard có thể lấy nhầm **_count** làm thời gian, hiểu **_sum** là độ trễ trung bình hoặc so sánh số mili giây ở code với số giây trong Prometheus.

Vấn đề không đơn thuần là thay dấu chấm bằng dấu gạch dưới. Micrometer sử dụng một **meter ID logic**; Prometheus dùng một hoặc nhiều **time series** để biểu diễn Counter, Timer, DistributionSummary hoặc Gauge. Registry/exporter còn áp dụng quy tắc đặt tên, đơn vị và hậu tố theo loại metric. Vì vậy, **tên Micrometer**, **tên metric family** và **tên series xuất ra** phải được phân biệt rõ.

Bài học này thuộc chương **Thiết kế metric** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Trong module, chúng ta đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking, luồng RAG và gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm giữa các phiên bản prompt, model và pipeline. Đặt tên đúng và truy vấn đúng là điều kiện để những kết quả đánh giá không bị diễn giải sai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Micrometer Meter.Id**, tên theo **NamingConvention**, **Prometheus metric family** và những **sample series** thực sự có thể truy vấn.
2. Giải thích vì sao dấu chấm trong tên logic thường được chuyển thành dấu gạch dưới, vì sao đơn vị hoặc loại meter tạo thêm hậu tố, và vì sao một Timer có thể xuất nhiều series.
3. Dự đoán có điều kiện những dạng tên thường gặp của Counter, Timer, DistributionSummary và Gauge, đồng thời **không coi dự đoán là sự thật thay cho kết quả scrape**.
4. Dùng **MeterRegistry** để kiểm tra tên logic và **Prometheus scrape endpoint** để kiểm tra tên xuất ra.
5. Viết PromQL cho tốc độ sự kiện, tỷ lệ PASS, độ trễ trung bình, p95 histogram, token usage và số request đang chạy với đơn vị và mẫu số đúng.
6. Tránh xung đột tên sau chuẩn hóa, lỗi hậu tố, cardinality cao, chọn nhầm series và sai lệch khi thay phiên bản exporter.
7. Thiết kế kiểm thử hợp đồng metric cho ứng dụng Spring AI để bảo vệ dashboard, alert và báo cáo đánh giá hồi quy.

## 2. Bốn khái niệm tên phải tách biệt

| Khái niệm | Nơi xuất hiện | Ví dụ minh họa | Trách nhiệm |
| --- | --- | --- | --- |
| **Tên logic của meter** | Code Java, Micrometer registry | app.ai.tool.execution.duration | Mô tả phép đo trong ứng dụng |
| **Meter.Id** | Micrometer: name + tags + type + baseUnit + description | Timer với tool_family=retrieval | Định danh và metadata của meter |
| **Tên metric family đã chuẩn hóa** | Prometheus exposition | app_ai_tool_execution_duration_seconds | Họ metric với type/metadata chung |
| **Tên sample/time series** | Scrape output, truy vấn PromQL | ..._seconds_count, ..._seconds_sum, ..._seconds_bucket | Biểu diễn các đại lượng cụ thể |

**Meter.Id không chỉ là tên.** Hai meter cùng tên và loại nhưng khác tags có thể tạo các chuỗi phân biệt nhau. Ngược lại, hai tên logic khác nhau có thể **bị trùng tên xuất ra sau khi chuẩn hóa**.

Ví dụ:

~~~text
Micrometer name:
  app.ai.tool.execution.duration

Type:
  TIMER

Tags:
  tool_family = retrieval
  outcome     = success

Một dạng các series Prometheus có thể xuất:
  app_ai_tool_execution_duration_seconds_count
  app_ai_tool_execution_duration_seconds_sum
  app_ai_tool_execution_duration_seconds_max

Nếu bật histogram phù hợp:
  app_ai_tool_execution_duration_seconds_bucket
~~~

Các chuỗi trên là **ví dụ thường gặp**, không phải lời cam kết rằng một phiên bản registry nhất định luôn xuất đúng mọi series. **_max**, percentile, histogram và các hậu tố cụ thể phụ thuộc cấu hình, registry/client và phiên bản.

### Không đánh đồng ba bước quan sát

~~~mermaid
flowchart LR
    A["Java: MeterRegistry + Meter.Id<br/>app.ai.tool.execution.duration"] --> B["PrometheusMeterRegistry<br/>naming, type, baseUnit"]
    B --> C["Exposition /actuator/prometheus<br/>family + samples"]
    C --> D["Prometheus scrape và lưu time series"]
    D --> E["PromQL / Dashboard / Alert"]
    A --> F["/actuator/metrics<br/>tên logic và thống kê Micrometer"]
~~~

Chỉ nhìn vào mã đăng ký meter mới biết **ý định đặt tên**. Muốn biết tên Prometheus thật để truy vấn, phải quan sát **đầu ra sau exporter**.

## 3. Quy tắc chuẩn hóa tên thường gặp

Trong Micrometer, tên logic thường được viết bằng chữ thường và dấu chấm:

~~~text
app.ai.eval.case.completed
app.ai.model.request.duration
app.ai.tool.execution.duration
app.ai.rag.retrieval.size
app.ai.eval.relevance.score
app.ai.tool.inflight
~~~

Prometheus dùng quy ước tên tương thích với hệ sinh thái của nó. Một quy tắc rất phổ biến của Micrometer Prometheus registry là chuyển các dấu phân cấp **dấu chấm** thành **dấu gạch dưới**:

~~~text
app.ai.model.request.duration
           |
           v
app_ai_model_request_duration
~~~

Đây mới là bước **chuẩn hóa cơ sở**. Sau đó còn có hậu tố **đơn vị** (chẳng hạn seconds) và hậu tố **cấu trúc mẫu** (như total, sum, count, bucket).

### 3.1. Không sửa tên code để giống hoàn toàn tên series

Nếu Prometheus xuất **app_ai_model_request_duration_seconds_count**, không nên sửa tên Timer trong Java thành **app_ai_model_request_duration_seconds_count**. Khi đó registry vẫn có thể thêm hậu tố hoặc một lớp chuyển đổi nữa, gây ra tên khó hiểu và trùng chức năng.

Tên trong code phải diễn đạt phép đo: **model request duration**. Cấu trúc **count/sum/bucket** là cách exporter biểu diễn một Timer, không phải một Timer mới được ứng dụng đặt tên.

### 3.2. Đơn vị được đưa vào tên theo quy ước của exporter

Một Timer ghi duration trong ứng dụng có thể được xuất theo **seconds**, dù Java dùng **Duration.ofMillis(250)** hoặc đo thời gian bằng nano time. Đơn vị ở scrape và PromQL phải được kiểm tra trước khi đặt trục biểu đồ.

Một DistributionSummary có **baseUnit=bytes** có thể xuất series chứa hậu tố **_bytes**. Một Counter có **baseUnit=calls** có thể có dạng **_calls_total**. Nếu đơn vị đã được lặp trong tên logic, tên xuất ra có thể khó hiểu hoặc thay đổi theo quy tắc registry.

**Khuyến nghị:** đặt tên logic cho đại lượng; quản lý đơn vị bằng baseUnit và loại meter; kiểm tra series sau export, không đoán quy tắc ghép tên bằng tay.

### 3.3. Metric family khác tên sample

Một metric family như **app_ai_tool_execution_duration_seconds** có thể chứa nhiều sample thể hiện count, sum và bucket. Trong PromQL, thường truy vấn tên **sample cụ thể**; ví dụ dùng **_bucket** cho histogram_quantile và **_sum/_count** cho trung bình.

Không kết luận rằng family không tồn tại chỉ vì không thấy một sample có tên y hệt family trong dữ liệu Prometheus.

## 4. Phân biệt Counter, Timer, Summary và Gauge khi xuất Prometheus

| Micrometer meter | Dữ liệu muốn đo | Một dạng series Prometheus | Cách đọc đúng |
| --- | --- | --- | --- |
| **Counter** | Số sự kiện tích lũy | ..._total | Tích lũy; dùng rate/increase theo cửa sổ |
| **Timer** | Thời lượng mỗi lần thực thi | ..._seconds_count, ..._seconds_sum | Count là số mẫu; sum là tổng giây |
| **Timer + histogram** | Phân bố thời gian | ..._seconds_bucket cùng le | Dùng histogram_quantile để ước lượng p95 |
| **DistributionSummary** | Phân bố giá trị số | ..._count, ..._sum và bucket nếu bật | Trung bình = sum/count cùng nhóm |
| **Gauge** | Giá trị hiện tại | Tên normalized, có thể kèm unit | Ảnh chụp tại thời điểm scrape |

**Các dạng tên trong bảng là định hướng**, không phải schema xuất ra cố định cho tất cả backend hoặc phiên bản Prometheus client. Một số thống kê (max, percentile, created, bucket) là tùy chọn hoặc phụ thuộc runtime.

### 4.1. Counter: sự kiện tích lũy và hậu tố total

Đăng ký một Counter:

~~~java
Counter.builder("app.ai.eval.case.completed")
        .baseUnit("cases")
        .description("Final verdict for each evaluation case run")
        .tag("case_type", "rag")
        .tag("verdict", "pass")
        .register(registry)
        .increment();
~~~

Một tên series minh họa có thể là:

~~~text
app_ai_eval_case_completed_cases_total{
  case_type="rag", verdict="pass"
} 1
~~~

Ở đây **cases** là đơn vị được khai báo và **total** cho biết tính tích lũy của Counter trong lối đặt tên Prometheus thường gặp. Counter có thể reset khi process khởi động lại; với số ca PASS trong 5 phút, thường dùng **rate()** hoặc **increase()** thay vì trừ hai mẫu một cách ngây thơ.

**Không nên nối _total vào tên Java chỉ để cố điều khiển exporter.** Hậu tố và base unit phải tuân theo naming convention thực tế của registry.

### 4.2. Timer: count không phải milliseconds

Đăng ký Timer:

~~~java
Timer timer = Timer.builder(
                "app.ai.tool.execution.duration")
        .description("Executed tool latency")
        .tag("tool_family", "retrieval")
        .register(registry);

timer.record(java.time.Duration.ofMillis(250));
~~~

Ví dụ dạng scrape:

~~~text
app_ai_tool_execution_duration_seconds_count{
  tool_family="retrieval"
} 1

app_ai_tool_execution_duration_seconds_sum{
  tool_family="retrieval"
} 0.25
~~~

Diễn giải:

- **_count = 1:** một mẫu Timer được ghi, không phải một giây.
- **_sum = 0.25:** tổng thời lượng là **0,25 giây**, không phải 0,25 mili giây.
- **_sum/_count = 0,25 giây mỗi lời gọi** trong ví dụ một mẫu.

Nếu ghi thêm một lời gọi 750 ms:

~~~text
_count = 2
_sum   = 1.00 seconds
mean   = 1.00 / 2 = 0.50 seconds
~~~

Không đọc **_sum** như thời gian của một request riêng lẻ; nó là tổng từ khi meter bắt đầu trong vùng dữ liệu đo, tùy cách registry xuất. Cũng không dùng **_count** để biểu diễn độ trễ.

### 4.3. DistributionSummary: count và sum có đơn vị khác Timer

Giả sử muốn đo số tài liệu trong mỗi lượt retrieval. Tên logic là **app.ai.rag.retrieval.size** và base unit là **documents**:

~~~java
DistributionSummary summary = DistributionSummary.builder(
                "app.ai.rag.retrieval.size")
        .baseUnit("documents")
        .tag("source_family", "policy")
        .register(registry);

summary.record(3);
summary.record(7);
~~~

Một dạng series có thể là:

~~~text
app_ai_rag_retrieval_size_documents_count{
  source_family="policy"
} 2

app_ai_rag_retrieval_size_documents_sum{
  source_family="policy"
} 10
~~~

**_count = 2 retrieval samples; _sum = 10 documents**. Trung bình là 5 tài liệu/lượt truy xuất. Không hiểu **sum=10** là mười lượt truy xuất. Khi đọc Prometheus, kiểm tra tên series thực tế vì cách áp baseUnit có thể thay đổi theo kiểu meter/registry.

### 4.4. Gauge: giá trị hiện tại, không có count/sum tự nhiên

~~~java
AtomicInteger inFlight = new AtomicInteger(0);

Gauge.builder("app.ai.tool.inflight",
                inFlight, AtomicInteger::get)
        .baseUnit("calls")
        .register(registry);

inFlight.incrementAndGet();
~~~

Một dạng tên xuất có thể là **app_ai_tool_inflight_calls** với giá trị **1** ở thời điểm scrape. Khi công việc kết thúc và bộ đếm giảm về 0, Gauge trở về 0. Nó không biểu diễn tổng số lời gọi từng xảy ra.

Cần giữ **AtomicInteger** được tham chiếu sống đủ lâu; Gauge không tạo một counter lịch sử. Nếu muốn tổng số lời gọi, dùng Counter hoặc số mẫu từ Timer.

## 5. Một Timer có thể tạo nhiều series hơn bạn nghĩ

Một Timer được cấu hình histogram có thể tạo ra các dạng mẫu:

~~~text
..._seconds_count  -> số lượt được ghi nhận
..._seconds_sum    -> tổng số giây
..._seconds_max    -> max trong cửa sổ thống kê, khi được xuất
..._seconds_bucket{le="0.1"} -> số mẫu <= 0,1 giây
..._seconds_bucket{le="0.5"} -> số mẫu <= 0,5 giây
..._seconds_bucket{le="+Inf"} -> toàn bộ số mẫu
~~~

Không phải Timer nào cũng có **_bucket**. Histograms cần được bật theo cấu hình phù hợp và sẽ tăng số lượng time series. Client-side percentiles, histogram và max có tính chất khác nhau; không nên giả định tất cả đều xuất ở cùng registry.

### 5.1. Histogram buckets có tính tích lũy theo ngưỡng

Giả sử 5 mẫu thời lượng là 0,1 s; 0,2 s; 0,3 s; 0,9 s; 1,2 s. Bucket minh họa:

| le (giây) | Số mẫu có thời lượng không vượt ngưỡng |
| ---: | ---: |
| 0,1 | 1 |
| 0,5 | 3 |
| 1,0 | 4 |
| +Inf | 5 |

Đây là **buckets tích lũy**, không phải bốn nhóm rời nhau. Không cộng trực tiếp các bucket để lấy tổng số request. Dùng **_count** hoặc bucket +Inf theo hợp đồng của histogram đang dùng.

### 5.2. p95 cần histogram thích hợp

Trên Prometheus classic histogram, ví dụ:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Truy vấn này ước lượng **p95 thời lượng theo tool_family** từ buckets trong cửa sổ 5 phút. Kết quả là **giây** nếu metric xuất theo seconds.

Không thể thay thế bằng:

~~~text
average(p95_instance_A, p95_instance_B)
~~~

Trung bình hai percentile riêng lẻ không cho p95 của toàn bộ dữ liệu. Nếu cần gộp nhiều instance, histogram buckets cho phép tổng hợp hợp lệ theo cùng schema bucket; cần kiểm tra cấu hình tương thích trước khi cộng.

### 5.3. Native histogram và format mới

Prometheus có cả các cơ chế histogram khác nhau tùy phiên bản và cấu hình. Cú pháp dùng **_bucket** ở trên phù hợp với cách xuất **classic histogram** thường gặp. Nếu backend triển khai native histogram hoặc OpenMetrics theo định dạng khác, phải đọc các series/kiểu mẫu thực và điều chỉnh truy vấn; không coi ví dụ này là quy tắc chung tuyệt đối.

## 6. Tags Micrometer và labels Prometheus

Trong Micrometer, thuộc tính phân nhóm được gọi là **tags**; ở Prometheus, chúng xuất hiện dưới dạng **labels**.

~~~java
Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family", "retrieval")
        .tag("outcome", "success")
        .register(registry);
~~~

Trong scrape, các chiều có thể xuất thành:

~~~text
..._seconds_count{
  tool_family="retrieval",
  outcome="success"
} 12
~~~

Các tên label cũng có quy tắc chuẩn hóa và giới hạn hợp lệ. Đừng mặc định mọi dấu chấm, ký tự đặc biệt trong tên tag sẽ được giữ nguyên khi xuất ra Prometheus.

### 6.1. Không dùng dữ liệu riêng lẻ làm labels

Các labels phù hợp có thể là:

| Label | Giá trị hữu hạn |
| --- | --- |
| case_type | rag, tool, multi_turn, no_tool |
| verdict | pass, fail, inconclusive |
| tool_family | retrieval, order, payment, other |
| outcome | success, error, timeout, cancelled |
| model_group | group_a, group_b, other |
| error_class | auth, validation, transient, business |

Tránh **user_id, order_id, conversation_id, tool_call_id, case_id, run_id, trace_id, raw prompt, document_id** làm metric labels. Chúng gây cardinality cao và có thể lộ thông tin. Các định danh cụ thể thuộc kết quả đánh giá và trace/log được phân quyền.

### 6.2. Series là tổ hợp tên và labels

Với cùng tên Timer, hai giá trị:

~~~text
tool_family=retrieval, outcome=success
tool_family=retrieval, outcome=error
~~~

là **hai chuỗi riêng**. Nếu thêm 100.000 user IDs, số series tăng rất lớn, nhất là khi bật histogram. Khi thiết kế metric cho ứng dụng Spring AI, phải tính cả **số label combinations × số series do mỗi meter sinh ra**.

### 6.3. Thay tags có thể làm dữ liệu không nối tiếp

Nếu bản cũ dùng **tool_family=retrieval**, bản mới dùng **tool_family=search**, Prometheus có thể coi đây là hai chuỗi khác nhau. Dashboard cố định bộ lọc cũ có thể đột ngột không thấy dữ liệu. Hãy quản lý **tag dictionary** và version của metric contract khi thay tên/giá trị.

## 7. Những tên dễ xung đột sau chuẩn hóa

Hai tên logic:

~~~text
app.ai.tool.calls
app_ai_tool_calls
~~~

có thể đều bị chuẩn hóa thành một dạng gần như **app_ai_tool_calls**. Tên khác nhau trong Java không bảo đảm khác nhau ở exporter.

Tương tự, một Counter và một Gauge cùng tên logic hoặc những tên tạo hậu tố giống nhau có thể gây xung đột về loại metric hoặc family trong Prometheus. Kết quả tùy registry: có thể báo lỗi đăng ký/thu thập, không xuất như mong đợi, hoặc chỉ một bộ series được giữ.

Các quy tắc phòng tránh:

1. Đặt **tên logic khác nhau theo ngữ nghĩa**, không chỉ đổi dấu chấm thành dấu gạch dưới.
2. Không tạo Counter, Timer và Gauge cùng tên nhưng khác loại.
3. Tránh tự thêm hậu tố cấu trúc như **_total**, **_count**, **_sum** vào tên logic nếu exporter quản lý.
4. Đặt baseUnit có chủ đích; không vô tình tạo hậu tố đơn vị lặp.
5. Kiểm tra toàn bộ danh sách tên **sau export**, không chỉ danh sách name của MeterRegistry.
6. Nếu đổi tên metric đã dùng bởi dashboard hoặc alert, có kế hoạch migration và giai đoạn chuyển tiếp được quản lý.

## 8. Actuator metrics và Prometheus endpoint là hai góc nhìn

Trong ứng dụng Spring Boot có Micrometer và các endpoint phù hợp được bật, ta thường có hai nơi xem số liệu:

| Nơi truy cập | Thường hiển thị | Dùng để làm gì? |
| --- | --- | --- |
| **/actuator/metrics** | Danh sách tên meter logic; chi tiết measurement và available tags | Kiểm tra meter được đăng ký trong ứng dụng |
| **/actuator/metrics/{name}** | Thống kê Micrometer cho một tên logic | Xác minh dữ liệu ghi vào registry |
| **/actuator/prometheus** | Prometheus exposition text, tên series chuẩn hóa, HELP/TYPE và samples | Xác định tên chính xác cho PromQL |
| **Prometheus query API/UI** | Các series Prometheus đã scrape và lưu thành công | Kiểm tra truy vấn, label, rate/histogram |

Các đường dẫn và khả năng truy cập phụ thuộc cấu hình Spring Boot Actuator, dependency registry, security và base path. Endpoint có thể **không được expose mặc định**; việc không truy cập được endpoint không tự chứng minh metric không được ghi.

### 8.1. Luồng điều tra khi “không thấy metric”

~~~mermaid
flowchart TD
    A["Đã record metric trong code?"] --> B{"MeterRegistry có meter logic?"}
    B -->|Không| C["Kiểm tra điểm record, bean/registry, điều kiện thực thi"]
    B -->|Có| D{"Scrape endpoint có family tương ứng?"}
    D -->|Không| E["Kiểm tra registry Prometheus, filters, naming, collision và endpoint"]
    D -->|Có| F{"Prometheus có scrape target và series?"}
    F -->|Không| G["Kiểm tra target, auth, path, network, scrape lỗi và retention"]
    F -->|Có| H["Sửa tên PromQL, labels, range, đơn vị và query"]
~~~

Đây là **quy trình kiểm tra dữ liệu quan sát**, không phải một danh sách lỗi nhất thiết xảy ra cùng nhau.

### 8.2. Lời giải cho lỗi tìm nhầm tên

Nếu trong **/actuator/metrics** thấy **app.ai.tool.execution.duration** nhưng truy vấn Prometheus:

~~~promql
app.ai.tool.execution.duration
~~~

không trả dữ liệu, không vội kết luận Micrometer chưa ghi. Trước tiên kiểm tra scrape; nếu thấy:

~~~text
app_ai_tool_execution_duration_seconds_count
app_ai_tool_execution_duration_seconds_sum
~~~

thì dùng chính các series đó hoặc histogram bucket nếu có để xây truy vấn. **Tên logic không phải câu truy vấn Prometheus tự động hợp lệ**.

## 9. Ví dụ Java: so sánh Meter.Id với kết quả scrape

Ví dụ dưới đây đăng ký bốn loại meter bằng Micrometer, ghi vài mẫu thử và in cả **tên logic** lẫn **toàn bộ text scrape**. Đây là cách học sự khác nhau giữa tên trong Java và tên xuất ra rõ ràng nhất.

Ví dụ sử dụng package **io.micrometer.prometheusmetrics** của nhánh triển khai Prometheus registry mới. Một số dự án dùng các phiên bản cũ có thể có package **io.micrometer.prometheus**; cần chọn import và dependency đúng với phiên bản của dự án.

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;

public final class PrometheusNameProbe {

    public static void main(String[] args) {
        PrometheusMeterRegistry registry =
                new PrometheusMeterRegistry(
                        PrometheusConfig.DEFAULT);

        // 1. Counter: số ca đánh giá có verdict cuối.
        Counter cases = Counter.builder(
                        "app.ai.eval.case.completed")
                .description("Finished evaluation case runs")
                .baseUnit("cases")
                .tag("case_type", "rag")
                .tag("verdict", "pass")
                .register(registry);
        cases.increment();
        cases.increment();

        // 2. Timer: thời gian thực thi tool, có histogram.
        Timer execution = Timer.builder(
                        "app.ai.tool.execution.duration")
                .description("Tool handler execution duration")
                .tag("tool_family", "retrieval")
                .tag("outcome", "success")
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1))
                .register(registry);
        execution.record(Duration.ofMillis(125));
        execution.record(Duration.ofMillis(750));

        // 3. Summary: số tài liệu trong mỗi lượt retrieval.
        DistributionSummary retrieved = DistributionSummary
                .builder("app.ai.rag.retrieval.size")
                .description("Documents returned by retrieval")
                .baseUnit("documents")
                .tag("source_family", "policy")
                .register(registry);
        retrieved.record(3);
        retrieved.record(7);

        // 4. Gauge: số tool đang chạy tại thời điểm scrape.
        AtomicInteger inFlight = new AtomicInteger(2);
        Gauge.builder("app.ai.tool.inflight",
                        inFlight, AtomicInteger::get)
                .description("Currently running tool calls")
                .baseUnit("calls")
                .register(registry);

        System.out.println("=== LOGICAL METER IDs ===");
        for (Meter meter : registry.getMeters()) {
            Meter.Id id = meter.getId();
            System.out.println(
                    id.getName()
                            + " | type=" + id.getType()
                            + " | baseUnit=" + id.getBaseUnit()
                            + " | tags=" + id.getTags());
        }

        System.out.println("=== PROMETHEUS SCRAPE ===");
        System.out.println(registry.scrape());

        inFlight.set(0);
        System.out.println("=== SCRAPE AFTER GAUGE CHANGE ===");
        System.out.println(registry.scrape());
    }
}
~~~

### 9.1. Những điểm cần quan sát

Trong khối **LOGICAL METER IDs**, những tên cần tìm là:

~~~text
app.ai.eval.case.completed
app.ai.tool.execution.duration
app.ai.rag.retrieval.size
app.ai.tool.inflight
~~~

Trong khối **PROMETHEUS SCRAPE**, hãy tìm các series tương ứng với từng tên. Với quy ước phổ biến, bạn có thể gặp những dạng như:

~~~text
app_ai_eval_case_completed_cases_total
app_ai_tool_execution_duration_seconds_count
app_ai_tool_execution_duration_seconds_sum
app_ai_tool_execution_duration_seconds_bucket
app_ai_rag_retrieval_size_documents_count
app_ai_rag_retrieval_size_documents_sum
app_ai_tool_inflight_calls
~~~

Danh sách chỉ nhằm giúp tìm kiếm. **Tên và các dòng thực sự phải lấy từ kết quả registry.scrape() của phiên bản chạy**, không được coi danh sách ví dụ là hợp đồng tự động của mọi Micrometer registry.

### 9.2. Mối quan hệ giữa mẫu và giá trị

Với fixture trong mã:

| Meter | Dữ liệu ghi | Ý nghĩa thống kê |
| --- | --- | --- |
| Counter completed | Tăng 2 lần | 2 ca PASS đã được ghi nhận |
| Timer duration | 125 ms và 750 ms | Count=2, tổng 0,875 giây |
| Summary retrieval.size | 3 và 7 documents | Count=2, tổng 10 documents |
| Gauge inFlight | 2, sau đó 0 | Giá trị tức thời có thể giảm |

Bạn có thể thấy các series khác như max hoặc nhiều bucket, nhưng không nên lấy chúng để thay đổi các kết luận số học trên. Histogram sẽ chứa nhiều ngưỡng, không làm tăng số lời gọi Timer.

### 9.3. Khi áp dụng trong Spring Boot

Một ứng dụng Spring Boot thường khai báo dependency **spring-boot-starter-actuator** và **micrometer-registry-prometheus** phù hợp. Việc expose endpoint phụ thuộc cấu hình và chính sách bảo mật. Ví dụ cấu hình môi trường phát triển:

~~~properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
~~~

Sau khi được cấu hình và có quyền truy cập thích hợp, dùng:

~~~text
GET /actuator/metrics
GET /actuator/metrics/app.ai.tool.execution.duration
GET /actuator/prometheus
~~~

Trong môi trường production, endpoint metrics có thể cần xác thực, mạng nội bộ hoặc chính sách hạn chế truy cập. Không mở công khai chỉ để dễ quan sát. Nếu ứng dụng có **management.endpoints.web.base-path** khác mặc định, đường dẫn cũng thay đổi.

### 9.4. Vì sao không hard-code tên xuất ra trong lớp ghi metric?

Một lớp nghiệp vụ Spring AI nên làm việc với **MeterRegistry và Meter.Id**, không tự xây tên output dạng **..._seconds_sum**. Nếu công cụ xuất từ Prometheus sang một backend khác, tên hậu tố và cách lưu time series có thể khác.

Ngược lại, các **dashboard Prometheus và alert rules** phải dùng đúng tên series thực mà exporter cung cấp. Ranh giới này cho phép giữ code tương đối độc lập nhưng vẫn truy vấn chính xác tại backend.

## 10. Viết PromQL theo series, không theo tên Java

Các biểu thức sau sử dụng **tên series giả định từ ví dụ** ở trên. Trước khi sao chép, phải kiểm tra exporter của hệ thống thực.

### 10.1. Tốc độ case-run PASS

~~~promql
sum(
  rate(
    app_ai_eval_case_completed_cases_total{verdict="pass"}[5m]
  )
)
~~~

Đơn vị là **cases/second**. Không gọi biểu thức này là tỷ lệ thành công: nó là **tốc độ sự kiện PASS**.

### 10.2. Pass rate trên các ca có verdict xác định

~~~promql
sum(rate(
  app_ai_eval_case_completed_cases_total{verdict="pass"}[5m]
))
/
sum(rate(
  app_ai_eval_case_completed_cases_total{verdict=~"pass|fail"}[5m]
))
~~~

Giá trị thuộc miền **[0,1]** khi dữ liệu và nhãn nhất quán. Dashboard có thể nhân 100 để hiển thị %. Nếu mẫu số bằng 0, báo thiếu dữ liệu thay vì tự gán 100%.

Nếu cần so sánh giữa hai cohort, phải lọc cùng **case_type**, dataset và cửa sổ đánh giá; rate trên tất cả loại ca có thể che giấu việc phân bố độ khó của tập thử thay đổi.

### 10.3. Coverage của kết quả đánh giá

~~~promql
sum(rate(
  app_ai_eval_case_completed_cases_total{verdict=~"pass|fail"}[5m]
))
/
sum(rate(app_ai_eval_case_completed_cases_total[5m]))
~~~

Coverage đo tỷ lệ ca có kết luận PASS hoặc FAIL trong số tất cả ca được chấm PASS/FAIL/INCONCLUSIVE. Nếu INCONCLUSIVE tăng mạnh, pass rate trên phần còn lại có thể trông tốt hơn thực tế.

### 10.4. Thời lượng tool trung bình

~~~promql
sum(rate(
  app_ai_tool_execution_duration_seconds_sum[5m]
))
/
sum(rate(
  app_ai_tool_execution_duration_seconds_count[5m]
))
~~~

Tử số là **seconds/second** theo tốc độ tăng của tổng thời gian; mẫu số là **calls/second**. Thương số có đơn vị **seconds/call**. Không dùng _sum riêng mà gọi đó là latency trung bình.

Nếu dashboard phân nhóm theo tool_family:

~~~promql
sum by (tool_family) (
  rate(app_ai_tool_execution_duration_seconds_sum[5m])
)
/
sum by (tool_family) (
  rate(app_ai_tool_execution_duration_seconds_count[5m])
)
~~~

Cả tử và mẫu phải gộp **cùng bộ label**. Trộn những nhóm khác nhau có thể tạo tỷ lệ sai hoặc không trả dữ liệu như mong muốn.

### 10.5. p95 tool latency

~~~promql
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Chỉ sử dụng khi có **classic histogram buckets** thực sự xuất ra. Nếu chưa bật histogram hoặc dùng native histogram với cách truy vấn khác, công thức này không thể áp dụng nguyên trạng.

### 10.6. Trung bình số tài liệu trên một lần retrieval

~~~promql
sum(rate(
  app_ai_rag_retrieval_size_documents_sum[5m]
))
/
sum(rate(
  app_ai_rag_retrieval_size_documents_count[5m]
))
~~~

Kết quả là **documents/retrieval** trên những retrieval có mẫu. Đây không phải số documents mỗi giây; muốn throughput documents/s thì chỉ xem tốc độ tăng _sum, kèm ngữ nghĩa thích hợp.

### 10.7. Tổng tool calls đang chạy

~~~promql
sum(app_ai_tool_inflight_calls)
~~~

Đây là giá trị Gauge **tại thời điểm quan sát**. Không áp dụng rate như với Counter để giả lập số tool executions đã hoàn tất. Nếu một burst xảy ra giữa hai lần scrape, Gauge có thể không ghi nhận đỉnh đó.

### 10.8. Khi query trả rỗng

Một truy vấn rỗng có thể do:

- Tên series chưa đúng với exporter.
- Chưa có mẫu được ghi vào meter, hoặc meter tạo theo nhu cầu và chưa từng chạy.
- Chưa scrape, target DOWN, sai đường dẫn hoặc thiếu quyền.
- Điều kiện lọc labels sai, ví dụ **outcome=ok** trong khi exporter đang dùng **outcome=success**.
- Khoảng thời gian [5m] chưa có đủ mẫu để tính rate.
- Histogram buckets chưa bật nhưng truy vấn lại dùng _bucket.
- Registry bị filter, meter được tạo ở registry khác hoặc bị xung đột tên.

Thứ tự xử lý hợp lý là **kiểm tra MeterRegistry → scrape → target → series → truy vấn**, không sửa đại tên code cho đến khi tìm ra tầng thiếu dữ liệu.

## 11. Tên metric cho Spring AI và evaluator: đâu là metric tự bổ sung?

Spring AI có cơ chế observability tích hợp với Micrometer Observation, nhưng **tên instrumentation, tags và phạm vi dữ liệu cụ thể phụ thuộc phiên bản**. Không nên coi những tên tùy chỉnh bắt đầu bằng **app.ai** trong bài là các meter Spring AI tự động cung cấp.

Ví dụ các metric **tự thiết kế** cho bộ đánh giá:

| Mục tiêu | Tên Micrometer logic | Dạng dữ liệu cần thiết |
| --- | --- | --- |
| Số ca evaluation PASS/FAIL | app.ai.eval.case.completed | Counter theo verdict |
| Thời gian chạy một ca evaluation | app.ai.eval.case.duration | Timer |
| Điểm relevance mỗi ca RAG | app.ai.eval.relevance.score | DistributionSummary miền [0,1] |
| Kết quả fact checking | app.ai.eval.fact_check.completed | Counter theo verdict |
| Thời gian handler tool | app.ai.tool.execution.duration | Timer |
| Số tool đề nghị bị từ chối | app.ai.tool.call.denied | Counter theo reason |
| Số documents trả mỗi retrieval | app.ai.rag.retrieval.size | Summary baseUnit documents |
| Số token mỗi model request | app.ai.model.token.usage | Summary baseUnit tokens |
| Tác vụ đang chờ | app.ai.operation.pending | Gauge |
| Thời gian đến verified outcome | app.ai.operation.completion.duration | Timer |

**Không tự tạo một meter trùng tên hoặc trùng ngữ nghĩa với meter Spring AI đã cung cấp** nếu không có lý do rõ. Có thể giữ meter framework cho latency/model usage, còn lớp evaluation chỉ phát verdict, điểm chất lượng và business outcome — những thứ framework không nhất thiết biết.

### 11.1. Một câu trả lời đúng không được suy từ latency thấp

Một tool có thể kết thúc nhanh nhưng chọn sai mã đơn. Một câu trả lời RAG có thể nhanh và liên quan nhưng dẫn nguồn hết hạn. Metric tốc độ không thay thế kết quả đánh giá relevance, groundedness, fact checking và quyền truy cập.

### 11.2. Một HTTP 200 không đồng nghĩa business completed

Một tool gửi lệnh hủy đơn có thể trả HTTP 200 hoặc ACCEPTED, trong khi nghiệp vụ còn PENDING. Nếu model nói “đã hủy hoàn tất”, oracle phải kiểm tra source of truth và có thể đánh FAIL. **Timer tool execution** chỉ đo thời gian tool, không đo thời gian nghiệp vụ chuyển trạng thái.

### 11.3. Tránh dùng tên quá rộng

Tên **app.ai.success** không nói thành công ở tầng nào. Nên phân biệt:

~~~text
app.ai.model.request.completed       (model call)
app.ai.tool.execution.completed      (tool handler)
app.ai.eval.case.completed           (oracle verdict)
app.ai.operation.verified.completed   (business outcome)
~~~

Tập tên này là ví dụ định hướng, không bắt buộc phải tạo tất cả các Counter. Timer đã có count, nên một Counter khác cùng event có thể là ghi trùng không cần thiết.

## 12. Bảo toàn đơn vị khi phân tích chất lượng, chi phí và độ trễ

Một ứng dụng Spring AI thường có nhiều đơn vị cùng lúc:

| Đại lượng | Ví dụ đơn vị | Loại meter gợi ý | Cần lưu ý |
| --- | --- | --- | --- |
| Model/tool/retrieval latency | duration; seconds trên exporter thường gặp | Timer | p50/p95 và error latency |
| Token input/output mỗi model request | tokens | DistributionSummary | Chỉ dùng usage có thật |
| Tài liệu/đoạn RAG | documents hoặc chunks | DistributionSummary | Không gộp hai loại |
| Relevance/groundedness score | [0,1], không đơn vị | DistributionSummary | Cùng rubric/phiên bản |
| Ca PASS/FAIL/INCONCLUSIVE | cases | Counter | Một verdict cuối/case-run |
| Cost/request | USD hoặc tiền tệ đã xác định | Summary | Estimated khác billed |
| In-flight tasks | tasks hoặc calls | Gauge | Giá trị tức thời |
| Verified outcomes | operations | Counter | Xác minh tại backend |

### 12.1. Đổi giây sang mili giây ở đúng chỗ

Nếu exporter phát **seconds**, PromQL trả kết quả theo giây. Dashboard muốn hiển thị mili giây có thể chuyển:

~~~promql
1000 * (
  sum(rate(app_ai_tool_execution_duration_seconds_sum[5m]))
  /
  sum(rate(app_ai_tool_execution_duration_seconds_count[5m]))
)
~~~

Khi hiển thị, phải ghi nhãn **ms/call**. Đừng nhân 1.000 rồi vẫn để nhãn s, hoặc chuyển đổi hai lần ở cả query và dashboard.

### 12.2. Điểm relevance không phải tỷ lệ PASS

Một evaluator có thể trả **relevance score = 0,87** cho một câu trả lời. Nó không chứng minh 87% các câu hỏi của hệ thống đúng. **Pass rate** phải được tính bằng các Counter verdict và mẫu số phù hợp, còn relevance score là phân bố kết quả theo rubric.

### 12.3. Token cost và đơn vị tiền tệ

Nếu sử dụng token để ước tính chi phí, cần ghi **input/output tokens**, bảng giá theo model và thời điểm, phạm vi phí, đơn vị tiền tệ, và phân biệt estimated/billed. Nếu không có usage hoặc giá có thẩm quyền, dùng UNKNOWN; không tạo một sample cost=0 rồi suy ra ứng dụng miễn phí.

Không cộng các metric USD và VND vào cùng một đơn vị tổng nếu không có phép quy đổi được kiểm chứng. Metric tổng hợp không phải ledger kế toán.

## 13. Cẩn trọng với Prometheus text format, OpenMetrics và phiên bản thư viện

Không có một công thức thay tên Java thành tên Prometheus hoàn toàn ổn định cho mọi cấu hình và thời gian:

1. **Micrometer core** giữ meter ID và định nghĩa loại meter.
2. **Prometheus registry** áp quy tắc chuyển tên và base units.
3. **Prometheus client** cùng định dạng exposition quyết định các chi tiết như hậu tố và metadata.
4. **Micrometer/Prometheus client versions** có thể thay cách diễn giải Counter naming hoặc histogram.
5. **Backend/Prometheus scrape** có thể thêm external labels hay áp các chính sách relabel khác.

Với các phiên bản Micrometer dùng Prometheus client mới, Java package của registry thường là **io.micrometer.prometheusmetrics**. Một số bản cũ dùng **io.micrometer.prometheus**. Không thay import theo cảm tính; xem dependency thực tế và tài liệu tương ứng.

### 13.1. HELP/TYPE và sample lines

Một scrape endpoint có thể gồm:

~~~text
# HELP app_ai_eval_case_completed_cases_total ...
# TYPE app_ai_eval_case_completed_cases_total counter
app_ai_eval_case_completed_cases_total{case_type="rag",verdict="pass"} 2.0
~~~

Đây là **minh họa cấu trúc**, không phải bản dump cố định từ mọi phiên bản. Trong một số định dạng, tên ở dòng TYPE/HELP là tên family, còn tên sample có thể có hậu tố được định nghĩa theo loại metric. Hãy đọc toàn bộ context khi điều tra; không chỉ cắt một dòng bằng regex rồi suy ra loại meter.

### 13.2. Histograms và percentiles

Một Timer không bật histogram có thể vẫn xuất **count/sum** nhưng không có **bucket**. Bật histogram có thể tạo nhiều buckets và tăng cardinality. Client-side percentiles có thể xuất thông tin khác nhưng không phù hợp cho việc gộp p95 toàn hệ thống bằng phép trung bình.

Với native histogram hoặc cấu hình OpenMetrics khác, các tên và kiểu series có thể không giống ví dụ classic histogram. **Quyết định dựa trên dữ liệu scrape và khả năng backend thực tế**, không chỉ trên phần mở rộng tên.

### 13.3. Không coi khác biệt version là suy giảm chất lượng

Sau khi nâng cấp registry, tên Counter có thể thay đổi và dashboard cũ không còn dữ liệu. Đây là **lỗi hợp đồng telemetry/migration**, không chứng minh model, prompt hoặc RAG đột nhiên kém đi.

Trước khi nâng cấp, nên so sánh danh sách metric family, sample series, HELP/TYPE, tags, đơn vị và cảnh báo quan trọng giữa bản cũ với bản mới trong môi trường thử nghiệm.

## 14. Metric dictionary: giữ hai tên trong cùng một hợp đồng

Thay vì lưu trong tài liệu vận hành một tên duy nhất rồi đoán cách exporter đổi tên, nhóm phát triển nên có **metric dictionary** với:

- **Logical name:** tên Micrometer được ứng dụng đăng ký.
- **Meter type:** Counter, Timer, DistributionSummary, Gauge.
- **Observation unit:** một model request, một tool execution, một retrieval, một case-run...
- **Base unit:** duration, cases, documents, tokens, calls...
- **Tags:** tên và tập giá trị được phép.
- **Record event:** thời điểm chính xác meter được ghi.
- **Exporter family/samples:** tên Prometheus thực tế được xác minh ở một phiên bản.
- **Aggregation/query:** mẫu số, đơn vị đầu ra và cửa sổ thời gian.
- **Contract version:** được quản lý khi thay ngữ nghĩa hoặc exporter.

Một ví dụ YAML mang tính **đặc tả**, không phải tệp cấu hình Micrometer tự đọc:

~~~yaml
metric_contract_version: v1
logical_name: app.ai.tool.execution.duration
meter_type: timer
observation_unit: one_executed_tool_invocation
base_unit: duration
record_at: after_tool_handler_ends
include_errors: true
source: application_tool_wrapper
tags:
  tool_family: [retrieval, order, payment, other]
  outcome: [success, error, timeout, cancelled]
prometheus:
  exporter_version: verify_in_environment
  example_family: app_ai_tool_execution_duration_seconds
  expected_samples_when_present:
    - app_ai_tool_execution_duration_seconds_count
    - app_ai_tool_execution_duration_seconds_sum
  histogram_sample_if_enabled:
    - app_ai_tool_execution_duration_seconds_bucket
queries:
  average: rate(sum_series) / rate(count_series)
  percentile_95: histogram_quantile_on_bucket_rates
unit_after_export: seconds
invariants:
  - One Timer sample per completed tool execution
  - No user_id or tool_call_id in metric tags
  - Do not include time waiting for business completion
~~~

Chữ **verify_in_environment** nhắc người triển khai phải xác minh bằng scrape thực tế. Không nên dùng một file dictionary làm bằng chứng rằng exporter đã sinh đúng tên nếu chưa chạy registry tương ứng.

### 14.1. Một ví dụ dictionary tổng quát

| Tên logic Micrometer | Loại và đơn vị | Dạng series cần kiểm tra | Phép phân tích |
| --- | --- | --- | --- |
| app.ai.eval.case.completed | Counter, cases | ..._cases_total | Rate PASS, pass rate, coverage |
| app.ai.model.request.duration | Timer, duration | ..._seconds_count/sum | Mean model latency |
| app.ai.tool.execution.duration | Timer, duration | ..._seconds_bucket nếu bật | Tool p95 |
| app.ai.rag.retrieval.size | Summary, documents | ..._documents_count/sum | Mean documents/retrieval |
| app.ai.eval.relevance.score | Summary, score [0,1] | ..._count/sum | Mean relevance theo rubric |
| app.ai.tool.inflight | Gauge, calls | ..._calls | Current in-flight calls |

Tên series trong bảng chỉ là **dạng dự kiến** và phải được thay bằng tên xuất ra đã được kiểm chứng khi triển khai. Cùng một hợp đồng có thể có nhiều dashboard backend khác nhau, nên không đặt toàn bộ ngữ nghĩa vào riêng trường Prometheus.

### 14.2. Đặt owner và vòng đời

Một metric cần có người chịu trách nhiệm về:

1. Điểm record đúng, không mất hoặc ghi trùng mẫu.
2. Kiểu dữ liệu và giá trị đúng miền.
3. Tập labels hữu hạn.
4. Quy tắc thay đổi tên hoặc đơn vị.
5. Xác nhận dashboard và alert tiếp tục hoạt động sau nâng cấp.

Trong nhóm phát triển Spring AI, metric model có thể do nền tảng quan sát sở hữu, còn verdict và quality score do evaluation runner sở hữu. Không nên để hai nhóm cùng xuất một metric với tên giống nhau nhưng định nghĩa khác.

## 15. Kiểm thử tên và đơn vị như một hợp đồng API

Metrics là một giao diện dữ liệu. PromQL, dashboards, SLO và cảnh báo phụ thuộc vào tên series, labels và đơn vị; thay đổi âm thầm có thể làm hệ thống giám sát mất khả năng phát hiện lỗi.

### 15.1. Unit test với MeterRegistry

Với **SimpleMeterRegistry** hoặc registry phù hợp, kiểm tra:

- Meter logic đã đăng ký bằng đúng tên.
- Loại meter là Timer/Counter/Summary/Gauge như hợp đồng.
- Base unit và tags đúng.
- Số mẫu, tổng lượng, thời gian đã record đúng từ fixture.
- Không có tags chứa user ID, prompt hoặc run ID.
- Một ca đánh giá chỉ ghi một verdict cuối, ngay cả khi có retry nội bộ.

Ví dụ kiểm tra ở mức ý tưởng:

~~~java
Timer timer = registry.find(
        "app.ai.tool.execution.duration")
        .tag("tool_family", "retrieval")
        .timer();

if (timer == null) {
    throw new AssertionError("Missing logical Timer");
}
if (timer.count() != 2) {
    throw new AssertionError("Expected two Timer samples");
}

double seconds = timer.totalTime(
        java.util.concurrent.TimeUnit.SECONDS);

if (Math.abs(seconds - 0.875) > 1e-9) {
    throw new AssertionError("Duration unit mismatch");
}
~~~

Fixture trên giả định đã ghi hai thời lượng **125 ms và 750 ms** vào đúng Timer. Kiểm tra này cho biết **dữ liệu Micrometer bên trong** đúng; nó **chưa chứng minh tên series ở Prometheus**.

### 15.2. Integration test với PrometheusMeterRegistry

Một bước kiểm tra bổ sung:

~~~java
String scrape = prometheusRegistry.scrape();

// Kiểm tra đặc tính có ý nghĩa thay vì so toàn bộ
// nội dung scrape theo thứ tự và timestamp.
if (!scrape.contains(
        "app_ai_tool_execution_duration_seconds_count")) {
    throw new AssertionError("Expected count series absent");
}

if (!scrape.contains(
        "app_ai_tool_execution_duration_seconds_sum")) {
    throw new AssertionError("Expected sum series absent");
}
~~~

Đây là ví dụ minh họa một bộ tên **đã xác nhận từ phiên bản exporter dùng trong test**. Với phiên bản khác, test contract phải được cập nhật có chủ đích. Khi test thực tế, nên parse các dòng và metadata thay vì chỉ **contains** nếu cần phát hiện chính xác collisions, labels và types.

Đừng snapshot và so sánh toàn bộ scrape text nguyên văn nếu thứ tự series, giá trị thay đổi hay dữ liệu runtime không ổn định. Tốt hơn là kiểm tra **các invariants quan trọng**: tên, loại, đơn vị, labels được phép, count/sum, bucket và không có xung đột.

### 15.3. Bảng ca kiểm thử hữu ích

| Ca thử | Hành động | Điều kiện đạt |
| --- | --- | --- |
| Logical name | Đăng ký Timer app.ai.tool.execution.duration | MeterRegistry tìm đúng Timer |
| Name conversion | Gọi scrape | Có family và series đúng convention |
| Unit conversion | Ghi 250 ms | Sum phản ánh 0,250 giây nếu exporter xuất seconds |
| Counter suffix | Ghi 2 ca PASS | Series Counter thể hiện đúng 2 sự kiện |
| Histogram | Bật publishPercentileHistogram | Có buckets phù hợp với cấu hình |
| Histogram disabled | Tắt histogram | Dashboard không được phụ thuộc vào bucket không tồn tại |
| Gauge lifecycle | Thay đổi AtomicInteger 2 → 0 | Hai scrape có giá trị phản ánh trạng thái |
| Label normalization | Đăng ký tags hữu hạn | Scrape có labels đúng và không chứa ID |
| Collision | Thử hai tên logic có thể chuẩn hóa trùng | Test phát hiện hoặc ngăn va chạm |
| Exporter upgrade | Đổi phiên bản registry | Contract diff cho biết tên/đơn vị/tags thay đổi |
| Missing samples | Chưa gọi tool | Không kết luận metric lỗi nếu meter lazy chưa tạo |
| Reset | Restart tiến trình | Rate/alert xử lý counter reset phù hợp |

### 15.4. Kiểm tra với Actuator

Một bài kiểm tra tích hợp có thể:

1. Tạo một fixture kích hoạt tool và evaluation result.
2. Xác minh tên logic qua **/actuator/metrics** nếu endpoint được phép truy cập.
3. Lấy **/actuator/prometheus**, ghi nhận family và sample names.
4. Kiểm tra target Prometheus đang scrape đúng endpoint.
5. Chạy PromQL tối thiểu và so giá trị kỳ vọng trên cửa sổ đủ mẫu.
6. Xác nhận dashboard và alert dùng đúng đơn vị.

Không mở hoặc giảm bảo vệ endpoint production chỉ để thực hiện bài kiểm tra. Nên chạy trên môi trường test/staging với quyền và cấu hình tương đương.

## 16. Troubleshooting: từ lỗi hiển thị tới nguyên nhân thực

| Dấu hiệu | Điều tra đầu tiên | Hướng giải quyết |
| --- | --- | --- |
| Tìm tên dấu chấm không thấy | Scrape endpoint | Dùng tên normalized series |
| _count có dữ liệu nhưng _bucket rỗng | Timer histogram settings | Bật histogram nếu thật sự cần p95 |
| _sum tăng nhưng dashboard hiển thị độ trễ lớn bất thường | Đơn vị seconds/ms | Đổi đơn vị đúng một lần |
| Counter có giá trị, rate rỗng | Range window, số scrape samples | Mở rộng cửa sổ hoặc kiểm tra target |
| Gauge về 0 | Công việc kết thúc hoặc object bị GC | Kiểm tra vòng đời, source state |
| Metric trong registry nhưng không có ở Prometheus | Registry/exporter/target/filters | Kiểm tra scrape và cấu hình |
| Có hai family tên giống nhau | Tên logic và naming collisions | Đổi tên có ngữ nghĩa riêng |
| Một metric biến mất sau nâng cấp | Version/naming/client changes | Diff scrape, migration dashboard |
| Label outcome=success không còn thấy | Tag dictionary thay đổi | Đồng bộ bộ giá trị và query |
| Histogram phát sinh quá nhiều series | Buckets × labels | Giảm cardinality/cấu hình histogram |
| p95 tăng mà mean không tăng | Phần đuôi phân bố chậm | Xem bucket, trace ca chậm, timeout |
| Pass rate tăng dù nhiều ca không được chấm | INCONCLUSIVE bị bỏ khỏi mẫu số | Báo coverage riêng |
| Model metric có hai nguồn trùng nhau | Instrumentation chồng lấp | Chọn một chủ sở hữu, tránh double count |

### Quy trình chẩn đoán một truy vấn rỗng

**Bước 1 — Kiểm tra sự kiện:** ca thử đã thực sự chạy qua điểm record chưa? Nếu chưa có tool invocation, Timer tạo theo nhu cầu có thể chưa tồn tại.

**Bước 2 — Kiểm tra registry:** MeterRegistry đã nhận meter với tên logic, loại và tags dự kiến chưa?

**Bước 3 — Kiểm tra scrape:** có family và sample nào tương ứng, đơn vị/hậu tố là gì? Có vấn đề tên va chạm không?

**Bước 4 — Kiểm tra Prometheus target:** scrape có thành công, có đúng thời điểm và retention không?

**Bước 5 — Kiểm tra PromQL:** có sai tên sample, label filter, khoảng thời gian, histogram mode hoặc phép tính không?

**Bước 6 — Kiểm tra nội dung nghiệp vụ:** nếu truy vấn có dữ liệu nhưng ý nghĩa sai, quay lại metric dictionary, event source và oracle.

Một dashboard trả rỗng có thể là **lỗi trình bày/thu thập**, không đồng nghĩa ứng dụng Spring AI ngừng gọi model. Tương tự, một Timer giảm không chứng minh chất lượng fact checking được cải thiện.

## 17. Đọc kết quả đánh giá Spring AI qua hai lớp tên

Giả sử hai phiên bản prompt A và B được chạy trên **cùng tập 200 case-run**, cùng snapshot tài liệu RAG và cùng rubric evaluator. Các số liệu minh họa:

| Chỉ số và đơn vị | Prompt A | Prompt B |
| --- | ---: | ---: |
| Verified task success (%) | 84% | 88% |
| Fact checking PASS trên ca chấm được (%) | 91% | 86% |
| Model latency p95 (s) | 1,4 | 2,1 |
| Tool latency trung bình (ms) | 120 | 135 |
| Input tokens/model request | 800 | 1.150 |
| Tool executions/user task | 1,7 | 2,3 |
| Estimated cost/verified success (USD) | 0,010 | 0,016 |

Nếu metric dictionary quy định model Timer xuất seconds, nhưng dashboard mới gắn đơn vị milliseconds, người xem có thể tưởng thời gian model giảm 1.000 lần. Trước khi kết luận Prompt B nhanh/chậm hơn, cần kiểm tra **tên series, phép đổi đơn vị, bộ lọc model và cửa sổ đo**.

Sau khi xác nhận phép đo đúng, ta thấy Prompt B có verified task success cao hơn nhưng **fact-check giảm**, độ trễ, token, số tool calls và chi phí tăng. Đây không phải tình huống có thể kết luận bằng một metric duy nhất.

### 17.1. Gắn một error class có ý nghĩa

Một ca RAG có thể FAIL vì:

- **wrong_source_version**: truy xuất bản chính sách cũ.
- **unsupported_claim**: câu trả lời có mệnh đề không được nguồn hỗ trợ.
- **wrong_tool_arguments**: dùng sai orderId hoặc ngày.
- **false_completion_claim**: nói COMPLETED khi backend mới ACCEPTED.

Error class là một tag hữu hạn có thể giúp dashboard tổng hợp, trong khi chi tiết case_id, document_id hoặc tool call ID vẫn nằm ở evaluation trace/audit. Đó là cách kết hợp **metric tổng quan** với **bằng chứng điều tra** mà không tăng cardinality.

### 17.2. So sánh nguồn lỗi

Khi Prompt B có nhiều lời gọi tool hơn:

1. Kiểm tra model có đề nghị tool thừa không.
2. Kiểm tra dispatcher có retry do timeout không.
3. Kiểm tra kết quả RAG có đủ nguồn hay phải truy xuất thêm.
4. Kiểm tra memory có làm mất dữ liệu đã có ở lượt trước không.
5. Kiểm tra actual backend events để biết có tác động trùng không.

Counter tool calls và Timer tool duration chỉ cho biết một phần. Việc chọn đúng công cụ, giữ đúng ngữ cảnh và kết quả nghiệp vụ phải được **oracle riêng** xác minh.

## 18. Bài thực hành

**Bối cảnh:** một ứng dụng Spring AI dùng Micrometer để theo dõi hai công cụ đọc đơn hàng và truy xuất chính sách, đồng thời có evaluator relevance/fact checking. Cần cấu hình dashboard Prometheus cho nhóm phát triển.

### Phần A — Dự đoán tên nhưng không dừng ở dự đoán

1. Đăng ký một Counter logic **app.ai.eval.case.completed** với baseUnit=cases.
2. Đăng ký một Timer logic **app.ai.tool.execution.duration**.
3. Đăng ký Summary logic **app.ai.rag.retrieval.size** với baseUnit=documents.
4. Đăng ký Gauge logic **app.ai.tool.inflight** với baseUnit=calls.
5. Viết danh sách tên series **dự kiến**, rồi chạy registry để lấy **scrape thật**; so sánh hai danh sách.
6. Ghi lại sự khác biệt nếu thư viện Prometheus client của dự án có quy tắc hậu tố khác ví dụ.

### Phần B — Chọn đúng sample và đơn vị

1. Ghi hai tool durations: 125 ms và 750 ms. Kiểm tra Timer count=2 và sum=0,875 giây.
2. Giải thích vì sao không được lấy _count làm latency.
3. Ghi Summary 3 và 7 documents; tính trung bình 5 documents/retrieval từ _sum/_count.
4. Thay Gauge in-flight từ 2 thành 0; giải thích vì sao Gauge không phải Counter.
5. Bật histogram và viết truy vấn p95 theo tool_family; kiểm tra có bucket thực tế.

### Phần C — Actuator và PromQL

1. So sánh danh sách ở **/actuator/metrics** với tên ở **/actuator/prometheus** trong môi trường được phép.
2. Viết PromQL cho PASS rate, coverage, mean tool latency, p95 tool latency và in-flight calls.
3. Nếu Prometheus trả rỗng, dùng quy trình **registry → scrape → target → query** để tìm lỗi.
4. Kiểm tra tất cả trục biểu đồ hiển thị đúng giây/mili giây, cases/second hoặc tỷ số phần trăm.

### Phần D — Kiểm tra contract và nâng cấp

1. Viết metric dictionary cho bốn meter đã đăng ký.
2. Thử tạo hai tên logic khác nhau nhưng có thể chuẩn hóa trùng; xác minh bộ kiểm tra phát hiện xung đột.
3. Thêm một tag user_id giả lập có hàng nghìn giá trị và giải thích vì sao phải loại bỏ trước production.
4. Mô phỏng nâng cấp exporter: chụp danh sách series của bản A và B rồi lập bảng những thay đổi tên, tags, units, type.
5. Đề xuất kế hoạch migration cho dashboard và alert mà không làm mất khả năng phát hiện lỗi chất lượng Spring AI.

### Câu hỏi tự kiểm tra

- Tên trong **Meter.Id** khác với tên time series Prometheus ở những điểm nào?
- Vì sao Timer trong Java chỉ có một tên nhưng Prometheus có thể xuất cả _count, _sum, _bucket?
- _seconds_count có đơn vị giây không?
- Để tính thời gian trung bình của tool, cần những series nào?
- Vì sao _bucket không phải lúc nào cũng tồn tại?
- Có thể lấy trung bình các giá trị p95 của nhiều instance không?
- Nếu dùng Counter với baseUnit=cases, vì sao cần kiểm tra tên thực tế của series thay vì tự nối hậu tố?
- Vì sao không dùng case_id hoặc prompt làm labels?
- Khi nâng cấp Micrometer, dashboard biến mất dữ liệu có nghĩa model đã ngừng hoạt động không?
- Vì sao việc sửa tên metric trong code không phải cách đầu tiên để khắc phục một truy vấn PromQL rỗng?
- Tool HTTP 200 có chứng minh tác vụ nghiệp vụ đã hoàn tất chưa?
- Tại sao đánh giá Spring AI cần cả metrics, traces và oracle?

## 19. Những điều cần ghi nhớ

1. **Tên Micrometer và tên Prometheus là hai lớp khác nhau.** Meter.Id chứa tên logic, tags, loại và đơn vị; exporter có thể chuyển tên và tạo nhiều series.
2. **Dấu chấm thường chuyển thành dấu gạch dưới**, nhưng còn quy tắc đơn vị và hậu tố loại metric. Không chỉ thay dấu chấm là đủ.
3. **Counter thường có series tích lũy, Timer có count/sum, Histogram có bucket, Summary có count/sum và Gauge có một giá trị tức thời.** Những thông tin tùy chọn phụ thuộc cấu hình.
4. **Count của Timer là số mẫu, sum là tổng thời lượng**, thường được xuất bằng giây ở Prometheus; trung bình cần sum/count trên cùng tập.
5. **Đừng đoán tên series cho dashboard.** Xem MeterRegistry để biết tên logic, rồi xem scrape để biết tên Prometheus thực tế và labels.
6. **Tên xuất có thể va chạm sau chuẩn hóa.** Không tự gắn _total/_count/_sum vào tên code để ép exporter; quản lý names/units/tags như một hợp đồng.
7. **Cardinality và quyền riêng tư quan trọng.** Dùng labels hữu hạn cho metric, lưu ID riêng trong trace/audit có phân quyền.
8. **Kiểm thử hợp đồng trước khi nâng cấp.** Diff metric families, sample names, units, types và alerts; một thay đổi telemetry không tự là sự suy giảm chất lượng model.
9. **Metrics chỉ cho biết mô hình vận hành ra sao.** Tính đúng của RAG, tool calls và kết quả nghiệp vụ cần dataset/oracle và bằng chứng source of truth; traces giúp tìm nguyên nhân cụ thể.

## Tài liệu tham khảo

- [Micrometer Reference — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): tên logic và naming conventions theo registry.
- [Micrometer Reference — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): Prometheus registry, các phiên bản client và cách scrape.
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đặc tính đếm sự kiện.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): thời lượng, count và tổng thời gian.
- [Micrometer Reference — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): các mẫu giá trị số và đơn vị.
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): giá trị tức thời.
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): histogram, percentile và phép tổng hợp.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): quan sát hoạt động ChatClient, model, công cụ và các thành phần Spring AI.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): registry, endpoint và quản lý metric.
- [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/): quy ước đặt tên và đơn vị.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): các series histogram/summary và quantile.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate và histogram_quantile.

**Lưu ý phiên bản:** các tên series ở bài là **ví dụ cho những dạng phổ biến**, không phải hợp đồng cứng của mọi bản Micrometer, Prometheus client, Spring Boot hay exporter. Khi xây hệ thống thật, kiểm tra **Meter.Id**, scrape endpoint, metadata HELP/TYPE, đơn vị và labels của chính phiên bản ứng dụng đang sử dụng trước khi cố định PromQL, dashboard hoặc alert.
