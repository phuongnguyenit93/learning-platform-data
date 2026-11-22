# Đối chiếu quan sát JFR với số liệu ứng dụng

## 1. Mục tiêu: từ hai nguồn dữ liệu đến một giả thuyết kiểm chứng được

**Java Flight Recorder (JFR)** ghi lại các sự kiện của JVM và có thể ghi cả sự kiện nghiệp vụ mà lập trình viên tự định nghĩa. Trong khi đó, hệ thống ứng dụng thường đã có **metrics** (số yêu cầu, số lỗi, độ trễ), log và đôi khi tracing. Khi ứng dụng bị chậm, chỉ nhìn JFR hoặc chỉ nhìn dashboard ứng dụng đều dễ dẫn đến kết luận thiếu căn cứ.

Ví dụ: Dashboard báo **p95 độ trễ tăng** cùng lúc JFR hiển thị nhiều sự kiện GC. Đây là **tương quan thời gian**, chưa đủ kết luận GC là nguyên nhân. Cần xác minh cùng instance, cùng khoảng thời gian, cùng tập yêu cầu và mức ảnh hưởng của GC trước khi kết luận.

Bài này hướng dẫn cách:
- Xác định **JFR quan sát gì**, ứng dụng đo gì và vì sao hai nguồn không nhất thiết có cùng số bản ghi.
- Căn chỉnh **thời gian, instance, operation, phiên bản triển khai** và, khi cần, khóa tương quan của một thao tác.
- Đối chiếu **throughput, tỷ lệ lỗi, latency p50/p95/p99** với JFR **CPU, GC, allocation, blocking, thread, I/O**.
- Dùng **custom JFR event** để nối thông tin ứng dụng với sự kiện JVM khi telemetry mặc định không đủ ngữ cảnh.
- Tránh nhầm lẫn giữa **số đo chính xác, sự kiện bị lọc bởi threshold, mẫu lấy theo sampling và giả thuyết nguyên nhân**.
- Tạo một ví dụ Java 17+ sinh cả số liệu ứng dụng và tệp `.jfr`, sau đó kiểm tra sự khớp bằng API chuẩn.

**Tính hiện hành:** JFR (module `jdk.jfr`) là công cụ chính thức đã tồn tại từ trước Java 14 và tiếp tục được hỗ trợ trên JDK hiện đại. Bài chỉ dùng API và CLI còn áp dụng trong **Java 17+**, không dựa vào cách bật JFR hay cách cấp phép đã lỗi thời. Cách triển khai thực tế tùy JVM, cấu hình event và môi trường production.

## 2. Hai nguồn quan sát trả lời hai nhóm câu hỏi khác nhau

### 2.1. Số liệu do ứng dụng thu thập

Những số liệu thường có trong metrics ứng dụng:

| Chỉ số | Câu hỏi có thể trả lời | Phạm vi |
| --- | --- | --- |
| **Request count** | Có bao nhiêu yêu cầu được xử lý? | Service, endpoint/operation, instance, cửa sổ thời gian |
| **Throughput / RPS** | Tốc độ phục vụ là bao nhiêu yêu cầu/giây? | Tổng số yêu cầu chia thời lượng đo |
| **Error count / error rate** | Bao nhiêu yêu cầu thất bại? | Phải định nghĩa lỗi: 5xx, exception, timeout, kết quả nghiệp vụ? |
| **Latency p50/p95/p99** | 50%, 95%, 99% yêu cầu hoàn thành trong bao lâu? | Phải biết điểm đo đầu/cuối, cửa sổ và cách tạo histogram |
| **In-flight requests** | Bao nhiêu yêu cầu đang được xử lý? | Thời điểm hoặc cửa sổ đo |
| **Queue length, DB pool, retries** | Ứng dụng đang chờ ở đâu? | Thành phần nghiệp vụ hoặc phụ thuộc bên ngoài |

Các số liệu này mô tả **hành vi mà người dùng hoặc nghiệp vụ quan sát được**. Một request có thể chậm vì GC, CPU, lock, mạng, cơ sở dữ liệu, queue hoặc hệ thống khác. Metrics thường báo rằng vấn đề **đang xảy ra**, nhưng không luôn chỉ ra mã hoặc tài nguyên JVM nào gây ra nó.

### 2.2. Dữ liệu từ JFR

JFR ghi lại các **events** có kiểu, thời điểm và thông tin đi kèm. Tùy cấu hình recording, ví dụ có thể gồm:

| JFR event / nhóm quan sát | Giúp tìm hiểu | Lưu ý |
| --- | --- | --- |
| `jdk.CPULoad` | Tải CPU được JVM quan sát tại các thời điểm | Là số đo CPU theo chu kỳ, không phải % CPU cho một endpoint |
| `jdk.ExecutionSample` | Mẫu stack đang thực thi | Là **sampling**, không phải thống kê đầy đủ mọi lời gọi |
| `jdk.GarbageCollection`, `jdk.GCPhasePause` | GC xảy ra khi nào, các pha dừng đáng kể | GC event không tự chứng minh request nào bị chậm |
| `jdk.ObjectAllocationSample` | Các mẫu cấp phát đối tượng và stack liên quan | **Sample**, không phải danh sách toàn bộ allocation |
| `jdk.JavaMonitorEnter` | Thread bị chặn khi vào monitor | Có thể được lọc theo ngưỡng thời lượng |
| `jdk.ThreadPark`, `jdk.JavaMonitorWait` | Thread đợi/park hoặc chờ monitor | Chờ đợi có thể là hành vi bình thường, không mặc nhiên là bug |
| `jdk.SocketRead`, `jdk.SocketWrite` | Hoạt động I/O socket và thời gian chờ/hoàn thành | Cần xét ngưỡng, stack và dependency liên quan |
| **Custom Event** do ứng dụng tạo | Thời lượng một operation, kết quả, khóa tương quan | Chỉ có nếu ứng dụng đã instrument và event được bật/ghi |

Tên, field và khả năng có mặt của từng event phụ thuộc **bản JDK, cấu hình recording, threshold, sampling và tình huống chạy**. Không giả định mọi `.jfr` đều có đầy đủ những event trong bảng. Kiểm tra `jfr summary`, `jfr metadata` và cấu hình nguồn trước khi phân tích.

### 2.3. Phân biệt “quan sát được” và “suy ra”

- JFR thấy **GC pause** cùng thời điểm p95 tăng: *có trùng thời gian*.
- JFR thấy **thread bị block** trong cùng thời điểm queue tăng: *có dấu hiệu nghẽn do đồng bộ*.
- JFR thấy **socket read lâu** cùng thời điểm latency tăng: *có thể đang chờ I/O*.
- Tracing thấy request cụ thể đi qua một bước DB chậm, JFR custom event của bước ấy cũng dài: *bằng chứng trực tiếp hơn ở phạm vi cùng thao tác*.

Không suy luận rằng **mọi khoảng thời gian không có JFR event đều là CPU đang làm việc**. Có thể event bị tắt, bị lọc, lấy mẫu hoặc thiếu khả năng quan sát tương ứng.

## 3. Chọn đúng khóa để đối chiếu

Để hai nguồn trở nên so sánh được, trước hết phải xác định **một đơn vị phân tích**.

| Thuộc tính / khóa | Metrics ứng dụng | JFR | Cách dùng |
| --- | --- | --- | --- |
| **Thời gian** | Timestamp, time window, biểu đồ time series | `getStartTime()`, `getEndTime()`, `getDuration()` | Đặt hai nguồn trên cùng trục thời gian |
| **Process / instance** | `service`, `instance`, host/container/pod | Tệp recording thu từ **một JVM cụ thể** | Không trộn JVM A với metric JVM B |
| **Operation** | Tên tuyến/handler/job có cardinality thấp | Custom event có field operation nếu instrument | Phân nhóm cùng loại việc |
| **Outcome** | `OK`, `ERROR`, timeout... | Custom event có outcome nếu instrument | So sánh đường thành công và thất bại |
| **Correlation key** | Log/trace có request ID hoặc span ID | Custom event có field ID do ứng dụng đưa vào | Ghép một sự kiện với đúng một request khi có nhu cầu |
| **Deployment** | Phiên bản app, config, feature flag | Thông tin thu cùng thời điểm; thường cần bổ sung từ môi trường | Tránh trộn hành vi trước/sau thay đổi |

**Không nên gắn requestId vào nhãn metric time series.** RequestId gần như luôn có cardinality rất cao, có thể làm hệ thống metrics tốn nhiều tài nguyên. Metrics nên dùng các nhóm **ổn định, cardinality thấp** như `operation`, `outcome`, `instance` khi hợp lý. Khi cần liên kết từng request, dùng **log, trace/span ID hoặc custom JFR event** đã kiểm soát kích thước, tần suất và quyền truy cập.

Trong ví dụ lớp học, khóa `lab-01`/`lab-02`/`lab-03` chỉ là dữ liệu giả để minh họa ghép bản ghi, **không phải lời khuyên ghi thông tin định danh người dùng hay bí mật vào JFR**.

## 4. Đồng bộ thời gian trước khi so sánh

### 4.1. Giờ tuyệt đối để ghép cửa sổ, thời gian đơn điệu để đo duration

Ứng dụng có thể ghi:

~~~java
java.time.Instant startedAt = java.time.Instant.now();
long beginNanos = System.nanoTime();
// Thực hiện công việc...
long elapsedNanos = System.nanoTime() - beginNanos;
~~~

Đây là **đoạn minh họa**, dùng trong một method. Hai giá trị giải quyết hai việc:

- `Instant.now()`: timestamp dựa trên **wall clock** để đặt sự kiện vào lịch thời gian và so với JFR/log/tracing.
- `System.nanoTime()`: đồng hồ **đơn điệu tương đối** thích hợp đo elapsed time trong cùng JVM. Không diễn giải một `nanoTime` trần thành ngày giờ UTC.

JFR `RecordedEvent` cung cấp các phương thức `getStartTime()`, `getEndTime()` và `getDuration()`. Để đối chiếu các event, dùng các kiểu `Instant` / `Duration` này thay vì ghép chuỗi giờ địa phương từ output console.

Nếu hai nguồn ở **hai máy khác nhau**, đồng bộ đồng hồ hệ thống (ví dụ NTP) và chú ý sai lệch clock. Trường hợp clock chưa tin cậy thì chỉ có thể so sánh **khoảng thời gian rộng hơn**, không nên tuyên bố hai sự kiện trùng chính xác tới millisecond.

### 4.2. Time zone và cửa sổ

Ví dụ, metrics được lưu dưới UTC, còn công cụ hiển thị JFR ở múi giờ máy phân tích. So sánh trực tiếp chuỗi `"10:00"` từ hai nguồn có thể sai nhiều giờ. Hãy chuyển timestamp về **cùng một mốc UTC / Instant**, sau đó mới chọn cửa sổ.

Quy trình khuyến nghị:

1. Xác định từ lúc nào đến lúc nào metrics báo bất thường.
2. Chuẩn hóa mốc bắt đầu/kết thúc, đơn vị `ms` hoặc `ns`, múi giờ và độ lệch clock.
3. Chỉ lấy JFR events từ **đúng JVM** và **đúng cửa sổ**.
4. So sánh với metrics cùng instance hoặc cùng tập instance tương ứng.
5. Ghi cả cửa sổ **trước**, **trong** và **sau** bất thường để có baseline.

Một ứng dụng xử lý request lâu có thể bắt đầu ở cuối cửa sổ A và kết thúc trong cửa sổ B. Cần quy định metrics tính latency theo **start time hay completion time**, đồng thời xét cả `startTime/endTime` của event JFR. Nếu bỏ qua cách phân cửa sổ, số liệu có thể lệch dù cả hai nguồn đều đúng.

## 5. Không thể so sánh trực tiếp mọi số đếm và latency

### 5.1. Request count khác JFR event count

Một request có thể sinh:
- Không có custom event vì event bị tắt.
- Một custom event bao toàn bộ xử lý.
- Nhiều events (DB, cache, external call, phase xử lý) trong cùng request.
- Các JVM events độc lập như GC, allocation sample, socket read.

Vì vậy **`requests = 10_000` không suy ra `JFR events = 10_000`**. Chỉ trong tình huống kiểm soát chặt như ví dụ phần 9 (một custom event trên mỗi lời gọi, không lọc, recording bắt trọn thời gian) mới có kỳ vọng số bản ghi tương đương.

### 5.2. Percentile và duration không giống nhau

**p95 latency** là giá trị ngưỡng mà khoảng 95% quan sát có thời gian không vượt quá nó, tùy thuật toán histogram/quantile của hệ thống metrics. Nó **không phải tổng** của các JFR duration.

Một tập số liệu giả, đơn vị `ms`:

~~~text
10, 20, 30, 40, 100
~~~

Nếu dùng phương pháp **nearest-rank** với 5 phần tử, vị trí p95 là `ceil(0.95 * 5) = 5`, nên p95 là **100 ms**, còn trung bình là **40 ms**. Các công cụ có thể chọn thuật toán quantile khác; vì thế phải thống nhất định nghĩa trước khi so sánh dashboard.

JFR event có thể ghi `duration` của **một GC pause, monitor block, socket read hoặc custom request phase**. Những durations đó đo các đoạn cụ thể, có thể **chồng lấn** hoặc không bao trùm toàn bộ request. Không cộng tùy tiện chúng để “ra p95”.

### 5.3. Threshold và sampling

Nhiều JFR events được ghi có điều kiện:
- **Threshold**: sự kiện thời lượng ngắn hơn ngưỡng có thể không được lưu.
- **Sampling**: chỉ một số mẫu stack/allocation được ghi theo cấu hình, không phải tất cả hoạt động.
- **Enabled settings**: một event có thể hoàn toàn không được bật.
- **Giới hạn recording**: cửa sổ giữ dữ liệu, max age/size và điều kiện hệ thống có thể khiến dữ liệu cần tìm không còn trong tệp.

Vậy nên **không thấy event không có nghĩa hoạt động không hề xảy ra**. Trước khi rút kết luận, kiểm tra số mẫu, ngưỡng, việc ghi có bao trùm sự cố và loại JFR event đang xét.

## 6. Một quy trình đối chiếu JFR với metrics ứng dụng

### Bước 1 — Đặt câu hỏi cụ thể

Thay vì “JFR có gì lạ?”, hãy bắt đầu:

> “Trong 10 phút p95 của operation LOOKUP tăng, JVM nào bị ảnh hưởng, và thời gian xử lý tăng chủ yếu đi cùng GC, CPU, blocking hay I/O?”

Việc này xác định **chỉ số mục tiêu**, cách chọn cửa sổ và những event đáng kiểm tra.

### Bước 2 — Chốt bối cảnh

Ghi lại `service`, `instance`, PID/JVM, `deployment version`, giờ bắt đầu/kết thúc, môi trường và workload. Với hệ thống nhiều replica, dashboard tổng có thể che giấu một replica bất thường. Nếu chưa biết instance nào bị ảnh hưởng, phân tích metrics theo instance trước.

### Bước 3 — Đối chiếu baseline với khoảng bất thường

Chọn một khoảng **baseline** có tải gần tương đương và một khoảng **incident**. So sánh:
- RPS, tỷ lệ lỗi, p50/p95/p99.
- Tỷ lệ operation, thay đổi payload, pool và queue.
- JVM process CPU, heap usage, GC, allocation, thread.
- Có deploy, cấu hình mới hoặc thay đổi traffic mix không?

Tránh so sánh 5 request ở baseline với 50.000 request lúc incident rồi kết luận p99 tăng chỉ vì JVM.

### Bước 4 — Thu hoặc mở recording đúng instance

Với JVM chạy sẵn, công cụ `jcmd` có các lệnh `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop`. Ví dụ sau là **mẫu lệnh chẩn đoán**, trong đó PID `12345` chỉ để minh họa: hãy thay bằng PID JVM thực tế sau khi xem `jcmd -l`.

~~~bash
jcmd -l
jcmd 12345 JFR.start name=incident settings=profile duration=2m filename=incident.jfr
jcmd 12345 JFR.check
jfr summary incident.jfr
jfr print --events jdk.GarbageCollection,jdk.CPULoad incident.jfr
~~~

Chờ recording có tệp hoàn tất trước khi chạy `jfr summary`. Nếu cần ghi tệp khi recording đang chạy, dùng `JFR.dump` với tên và đường dẫn phù hợp. `settings=profile` thường thu thêm thông tin để điều tra hơn mặc định; hãy đánh giá overhead, quyền, retention và chính sách vận hành trước khi bật trên production. Không nên bật mọi event/stacktrace ở tần suất tối đa vô hạn.

**Lưu ý lệnh:** `jcmd` cần quyền attach thích hợp trên máy/JVM đích; `jfr` là công cụ làm việc với tệp `.jfr`. Lệnh `jfr print --events ...` chỉ hiện events tồn tại trong recording; nếu không có dòng kết quả, kiểm tra `jfr summary`, tên event và cấu hình trước khi kết luận.

### Bước 5 — Chồng trục thời gian và kiểm tra giả thuyết

Đặt biểu đồ **latency p95, error rate, RPS** bên cạnh các event JFR đã lọc đúng instance/time window. Tìm:
- Các **GC pauses** có xảy ra đúng lúc một số request dài bất thường?
- Khi latency tăng, **process CPU** cao cùng với mẫu execution ở một nhóm method?
- Có nhiều **monitor enter/blocking** hoặc `ThreadPark` ở các thread quan trọng?
- Event **socket read/write** dài có cùng khoảng thời gian với lỗi timeout ngoài ứng dụng?
- Custom event của operation cụ thể có bắt đầu trước, kết thúc sau các hiện tượng đó không?

Nếu phát hiện tương quan, tiếp tục xác minh bằng stack trace, span, log, profile, thí nghiệm tải hoặc thay đổi có kiểm soát; **không khẳng định nguyên nhân chỉ từ sự trùng thời điểm**.

### Bước 6 — Kết luận kèm mức tin cậy

Một kết luận kỹ thuật nên ghi:
- **Dữ kiện quan sát được:** ví dụ “p95 tăng từ 120 ms lên 420 ms trên instance X”.
- **Tín hiệu JVM phù hợp:** ví dụ “JFR có khoảng dừng GC trong cùng phút”.
- **Khả năng giải thích khác:** thay đổi mix yêu cầu, DB, downstream, CPU contention.
- **Kiểm chứng tiếp theo:** lọc request ở đúng thời điểm, xem timeline và kiểm tra khi GC được cải thiện.

Không kết luận “GC gây mọi request chậm thêm 300 ms” khi mới có một event GC 150 ms hoặc một biểu đồ ghi theo phút.

## 7. Custom JFR event để nối dữ liệu ứng dụng với JVM

Khi cần biết một thời điểm GC hoặc blocking có nằm trong **một operation cụ thể** hay không, ta có thể tự định nghĩa event:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Name;

@Name("edu.demo.RequestWork")
class RequestWork extends Event {
    String operation;
    String correlationKey;
    String outcome;
}
~~~

Đây là **ví dụ định nghĩa type độc lập**, cần tổ chức thành class phù hợp khi tích hợp. JFR event có thể mang các field primitive và các kiểu reference được hỗ trợ như `String`. Không dùng tùy ý các object phức tạp, mảng hoặc collection làm field event và kỳ vọng chúng tự được serialize vào JFR.

Một đường instrument thông thường:

~~~java
RequestWork event = new RequestWork();
event.operation = "LOOKUP";
event.correlationKey = "lab-01"; // ID giả trong bài thực hành.
event.begin();
try {
    // Xử lý operation.
} finally {
    event.outcome = "OK";
    event.commit();
}
~~~

Đây là **đoạn minh họa**, và cần định nghĩa đúng outcome thực tế trong `catch`/`finally` của ứng dụng. `begin()` đánh dấu lúc bắt đầu, `commit()` kết thúc duration (nếu chưa gọi `end()`) và yêu cầu ghi event theo settings. Có thể sử dụng `end()` tường minh nếu muốn đóng khoảng đo trước khi làm một việc khác.

Trong code production có nhiều request, hãy:
- Đặt tên event và field ổn định, không gắn PII, token hoặc payload nhạy cảm.
- Chỉ thêm field thật sự giúp phân tích: operation, outcome, loại nghiệp vụ, khóa tương quan có kiểm soát.
- Cân nhắc `Event.isEnabled()` và `Event.shouldCommit()` trước khi tính các field đắt đỏ.
- Thiết lập **threshold, stacktrace và sampling strategy** phù hợp mục tiêu; có thể bỏ sự kiện ngắn một cách có chủ đích.
- Không biến JFR thành hệ thống metrics/tracing chính: nó là nguồn chẩn đoán bổ trợ, có chi phí và vòng đời recording riêng.

## 8. Sơ đồ quy trình đối chiếu một request

~~~text
APPLICATION                               JVM / JFR
-----------                               ---------
Nhận request ID: lab-02
  | Ghi timestamp + operation
  | Khởi tạo JFR custom event  -------->  event.begin()
  | Xử lý; chờ CPU / GC / I/O  -------->  JFR ghi các events JVM nếu được bật
  | Ghi outcome=ERROR, timer  -------->  event.commit()
  | Tăng metrics requests/errors
  v
Metrics aggregate theo operation/time
  |
  +-- log/trace (ID, operation, outcome, duration)
  |
  +-- custom JFR event (ID, operation, outcome, startTime, duration)
                   |
                   v
        Ghép đúng JVM + khoảng thời gian + ID
                   |
                   v
         So sánh; kiểm tra giả thuyết
~~~

**Một chú ý quan trọng:** Dù custom JFR event có cùng ID với log/trace, nó không tự khẳng định request đã trải qua một GC pause cụ thể. Để phân tích quan hệ thời gian, cần xem **khoảng bắt đầu/kết thúc của request** và **khoảng event JVM** có giao nhau không, từ đúng JVM và đúng thread khi thông tin có sẵn. Trùng khoảng thời gian toàn JVM chỉ là một dấu hiệu, không phải quan hệ nhân quả.

## 9. Chương trình Java 17+ hoàn chỉnh: ghép custom JFR event với metrics giả lập

Ví dụ này dùng một `List<AppMetric>` trong bộ nhớ để mô phỏng số liệu ứng dụng. Nó **không phải backend metrics production** (không xuất Prometheus, OpenTelemetry hay logs thực), nhưng cho phép kiểm chứng việc ghép hai phía bằng dữ liệu đơn giản. Chương trình:

1. Khởi động một `Recording` chỉ bật custom event `edu.demo.RequestWork`, threshold bằng `Duration.ZERO`.
2. Chạy ba thao tác giả lập với `Thread.sleep` để có duration; hai thao tác `LOOKUP` và một `UPDATE`.
3. Ghi mỗi thao tác thành một **AppMetric** có correlation key, operation, outcome, timestamp và duration đo bằng `System.nanoTime()`.
4. Ghi **một JFR custom event** cho mỗi thao tác, tạo tệp `correlation-demo.jfr`.
5. Đọc lại tệp bằng `RecordingFile.readAllEvents` để đối chiếu cùng key, operation/outcome, khoảng thời gian và số event.

**Tên tệp: `JfrMetricsCorrelationDemo.java`**

~~~java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class JfrMetricsCorrelationDemo {
    @Name("edu.demo.RequestWork")
    @Label("Request Work")
    @Category({"Demo", "Application"})
    static class RequestWork extends Event {
        @Label("Operation")
        String operation;
        @Label("Correlation Key")
        String correlationKey;
        @Label("Outcome")
        String outcome;
    }

    record AppMetric(String key, String operation, String outcome,
                     Instant startedAt, long elapsedNanos) {}

    static AppMetric runRequest(String key, String operation, boolean fail)
            throws InterruptedException {
        String outcome = fail ? "ERROR" : "OK";
        Instant startedAt = Instant.now();
        long beganNanos = System.nanoTime();
        RequestWork event = new RequestWork();
        event.correlationKey = key;
        event.operation = operation;
        event.begin();
        try {
            Thread.sleep(fail ? 25 : 15);
        } finally {
            event.outcome = outcome;
            event.commit();
        }
        return new AppMetric(key, operation, outcome,
                startedAt, System.nanoTime() - beganNanos);
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of(args.length > 0 ? args[0] : "correlation-demo.jfr");
        List<AppMetric> app = new ArrayList<>();
        try (Recording recording = new Recording()) {
            recording.setName("lesson-correlation");
            recording.enable(RequestWork.class)
                     .withThreshold(Duration.ZERO).withoutStackTrace();
            recording.start();
            app.add(runRequest("lab-01", "LOOKUP", false));
            app.add(runRequest("lab-02", "LOOKUP", true));
            app.add(runRequest("lab-03", "UPDATE", false));
            recording.stop();
            recording.dump(output);
        }

        Map<String, AppMetric> byKey = new HashMap<>();
        for (AppMetric m : app) {
            byKey.put(m.key(), m);
        }

        int jfrCount = 0;
        int joined = 0;
        boolean attributesMatch = true;
        boolean timesMatch = true;
        boolean durationsPresent = true;
        for (RecordedEvent event : RecordingFile.readAllEvents(output)) {
            if (!event.getEventType().getName().equals("edu.demo.RequestWork")) {
                continue;
            }
            jfrCount++;
            AppMetric m = byKey.get(event.getString("correlationKey"));
            if (m == null) {
                attributesMatch = false;
                timesMatch = false;
                continue;
            }
            joined++;
            attributesMatch &= m.operation().equals(event.getString("operation"));
            attributesMatch &= m.outcome().equals(event.getString("outcome"));
            timesMatch &= !event.getStartTime().isBefore(m.startedAt().minusSeconds(5));
            timesMatch &= !event.getStartTime().isAfter(m.startedAt().plusSeconds(5));
            durationsPresent &= !event.getDuration().isNegative();
        }

        System.out.println("App requests: " + app.size());
        System.out.println("App errors: " + app.stream()
                .filter(m -> m.outcome().equals("ERROR")).count());
        System.out.println("LOOKUP requests: " + app.stream()
                .filter(m -> m.operation().equals("LOOKUP")).count());
        System.out.println("App durations positive: " + app.stream()
                .allMatch(m -> m.elapsedNanos() > 0));
        System.out.println("JFR custom events: " + jfrCount);
        System.out.println("Joined by correlation key: " + joined);
        System.out.println("Operation/outcome agree: " + attributesMatch);
        System.out.println("Timestamps aligned: " + timesMatch);
        System.out.println("JFR durations nonnegative: " + durationsPresent);
        System.out.println("Recording created: " + Files.isRegularFile(output));
    }
}
~~~

### 9.1. Chạy thử

Cần **JDK 17 trở lên** có module `jdk.jfr` và các công cụ đi cùng JDK. Thực hiện trong thư mục chứa tệp mã nguồn:

~~~bash
javac -encoding UTF-8 --release 17 JfrMetricsCorrelationDemo.java
java JfrMetricsCorrelationDemo correlation-demo.jfr
jfr summary correlation-demo.jfr
jfr print --events edu.demo.RequestWork correlation-demo.jfr
~~~

**10 dòng stdout của chương trình đã được kiểm chứng khi chạy trên JDK hỗ trợ JFR:**

~~~text
App requests: 3
App errors: 1
LOOKUP requests: 2
App durations positive: true
JFR custom events: 3
Joined by correlation key: 3
Operation/outcome agree: true
Timestamps aligned: true
JFR durations nonnegative: true
Recording created: true
~~~

Sau đó `jfr summary` sẽ liệt kê thống kê event trong recording, trong lần kiểm chứng có một dòng `edu.demo.RequestWork` với **Count = 3**. Lệnh `jfr print --events edu.demo.RequestWork` lọc các event có tên này và cho thấy các field `operation`, `correlationKey`, `outcome` tương ứng ba lần xử lý.

**Cần phân biệt:** Số lượng những **JFR event types khác** trong recording và các giá trị `startTime`, `duration` có thể thay đổi theo JVM và lần chạy; chỉ có stdout kiểm tra invariant ở trên được thiết kế ổn định. Không dùng ví dụ này để suy ra số lượng event JVM tổng quát hoặc thời lượng chính xác trên máy khác.

### 9.2. Vì sao ba event ghép được ba metrics?

Trong ví dụ, mỗi lần `runRequest(...)`:
- Nhận một key giả duy nhất trong tập `lab-01`, `lab-02`, `lab-03`.
- Gán key và operation vào `RequestWork`.
- `event.begin()` trước thao tác; `event.commit()` trong `finally`.
- Trả về một bản ghi `AppMetric` cho cùng key và outcome.
- Cấu hình recording bật event class và threshold bằng zero, đảm bảo các sự kiện này **đủ điều kiện được ghi**, không bị loại chỉ vì thời lượng thấp hơn một ngưỡng dương.

Sau recording, `byKey.get(event.getString("correlationKey"))` tìm metric tương ứng. Hai field `operation` và `outcome` được đối chiếu để tránh “cùng ID nhưng khác nghiệp vụ”. Cửa sổ ±5 giây trong ví dụ chỉ là **ngưỡng kiểm tra rộng cho bài thực hành**, không phải cam kết độ chính xác đo thời gian hoặc ngưỡng được khuyến nghị cho hệ thống production.

### 9.3. Không so sánh cứng duration của hai phía

Ứng dụng đo `elapsedNanos` từ thời điểm ngay **trước khi tạo event**, trong khi `RequestWork` bắt đầu lúc gọi `event.begin()` và kết thúc ở `event.commit()`. Hai cặp mốc đo không hoàn toàn trùng nhau, và việc ghi event cũng có overhead. Vì vậy ví dụ chỉ kiểm tra duration **dương / không âm**, không khẳng định chúng phải bằng nhau tới nanosecond.

Khi muốn phân tích latency production:
- Xác định chính xác các điểm bắt đầu/kết thúc của **request SLA** và **JFR custom event**.
- Nếu đo toàn bộ request ở cả hai nơi, dùng cùng ranh giới logic nhất quán.
- So sánh phân bố/độ lệch trong cửa sổ có đủ mẫu, không đối chiếu một số `nanoseconds` lẻ.
- Khi đo mỗi **phase**, đừng kỳ vọng tổng phase durations bằng 100% wall-clock latency nếu có thời gian chồng lấn, queue hoặc overhead chưa instrument.

### 9.4. Vì sao không đưa toàn bộ danh sách request vào metric labels?

Ứng dụng dùng `List<AppMetric>` để tiện thử nghiệm trên **ba phần tử**, nhưng hệ thống thực thường lưu **số đếm và histogram** cho từng operation/status/window. Correlation key dạng requestId nên đi vào **log/trace hoặc custom event đã giới hạn dữ liệu**, không phải nhãn metrics có cardinality rất cao.

Với production, không giữ một danh sách request vô hạn trong heap chỉ để tính count/p95. Dùng hệ thống metrics/tracing thích hợp và chính sách thời gian lưu, sampling và bảo vệ dữ liệu.

### 9.5. Ghi chú về ví dụ `fail`

Trong demo, `fail == true` được dùng để **gán outcome = ERROR** và mô phỏng một yêu cầu được coi là lỗi; nó **không ném exception thực**. Vì thế `App errors: 1` là kết quả theo **nhãn outcome trong dữ liệu thử nghiệm**, không phải số exception JVM.

Trong ứng dụng thật, outcome cần phản ánh hợp đồng nghiệp vụ của service (HTTP status, timeout, validation error, exception...) và nên được ghi nhất quán trên cả metrics, log/trace và custom JFR event.

## 10. Nếu tệp JFR lớn: đọc theo luồng

`RecordingFile.readAllEvents(path)` rất tiện cho ví dụ nhỏ vì nó nạp danh sách các event vào bộ nhớ. Với recording lớn, Oracle ghi rõ API đó **không dành cho các tệp lớn**. Dùng `RecordingFile` theo hướng duyệt từng event:

~~~java
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Path;

public final class JfrStreamExample {
    public static void main(String[] args) throws Exception {
        try (RecordingFile file =
                     new RecordingFile(Path.of("correlation-demo.jfr"))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if ("edu.demo.RequestWork".equals(
                        event.getEventType().getName())) {
                    System.out.println(event.getString("operation"));
                }
            }
        }
    }
}
~~~

Đây là một **chương trình độc lập thứ hai**, lưu vào `JfrStreamExample.java` và chạy sau khi ví dụ chính tạo `correlation-demo.jfr`. Nó in ba dòng operation theo thứ tự event được đọc trong lần demo tương ứng, nhưng với các recording tổng quát khác thứ tự/số lượng tùy thời gian thu. Không cần nạp mọi event vào RAM để kiểm tra một loại event hoặc duy trì bộ đếm theo time window.

Đọc JFR từ **nguồn tin cậy** và tuân thủ quyền truy cập: tệp có thể chứa tên method, stack trace, path, host, thread và metadata nhạy cảm, tùy cấu hình.

## 11. Ví dụ phân tích tình huống thực tế: p95 tăng

Giả sử hệ thống có dữ liệu **minh họa**, không phải số đo của một hệ thống thực:

| Metric trên cùng một instance | Baseline 10 phút | Khoảng bất thường 10 phút |
| --- | ---: | ---: |
| RPS | 70 | 72 |
| Error rate | 0,2% | 2,0% |
| p50 latency | 35 ms | 40 ms |
| p95 latency | 120 ms | 420 ms |
| p99 latency | 200 ms | 800 ms |

Quan sát JFR cùng JVM trong khoảng bất thường cho thấy một số GC pauses và nhiều thread chờ I/O lâu hơn baseline.

**Cách suy luận đúng:**

1. **p50 gần ổn định, p95/p99 tăng mạnh**: vấn đề tập trung ở đuôi phân bố, không nhất thiết mọi request đều chậm.
2. **RPS gần tương đương**: giảm khả năng nguyên nhân chỉ do số lượng request tăng, nhưng workload mix hoặc kích thước payload vẫn có thể đổi.
3. **Error rate tăng**: có thể liên quan timeout hoặc downstream; cần xem mã lỗi và operation.
4. **GC pauses trùng thời gian**: một giả thuyết đáng kiểm tra, nhưng phải so độ dài các pauses, thread liên quan và số request bị ảnh hưởng.
5. **Socket events kéo dài**: giả thuyết khác là dependency I/O chậm; cần xem trace, log và metric downstream.

**Không kết luận:** “p95 tăng thêm 300 ms do GC” chỉ vì có một GC pause 150 ms trong cùng phút. Thời lượng GC, tần suất, mức chồng lấn với request và độ trễ ngoài JVM phải được đối chiếu định lượng.

**Bằng chứng tốt hơn:** Chọn một số request chậm được xác định từ trace/log, xem custom JFR event/operation cùng thời điểm, so sánh với các sự kiện GC/blocked/socket xảy ra trong đúng khoảng duration của request, rồi lặp lại trên nhiều request, nhiều cửa sổ. Với hệ thống nhiều instance, chỉ phân tích JFR của instance thực sự xử lý request đó.

## 12. Bẫy thường gặp khi đối chiếu

| Bẫy | Vì sao sai? | Cách làm tốt hơn |
| --- | --- | --- |
| So `request count` trực tiếp với `jdk.ExecutionSample` count | ExecutionSample là mẫu stack, không phải một event/request | Dùng request metrics cho throughput; sampling cho hotspot CPU |
| Không thấy `SocketRead` nên kết luận không có I/O | Event có thể bị tắt/lọc/ngưỡng, hoặc I/O xảy ra theo con đường khác | Kiểm tra JFR settings, threshold và trace/log |
| So p95 toàn service với JFR của một JVM | Hai nguồn không cùng tập instance | Phân nhóm metrics theo instance hoặc thu JFR tương ứng |
| Ghép theo giờ local từ hai máy khác múi giờ | Dễ lệch thời gian | Chuẩn hóa timestamp sang UTC/Instant |
| Trộn RPS theo phút với duration từng request mà không hiểu denominator | Một bên là aggregate, bên kia là observation | Chọn cửa sổ, population và đơn vị thống nhất |
| Lấy `ThreadPark` nhiều làm bằng chứng lỗi | Thread park có thể là hoạt động điều phối bình thường | Xem stack, thread role, thời lượng và ảnh hưởng SLA |
| Cộng mọi GC/socket/monitor duration thành request latency | Các khoảng có thể chồng lấn và không cùng request | Dựng timeline request/phase, xác định phần giao nhau |
| Đưa requestId vào labels metric | Cardinality bùng nổ | Đưa key vào trace/log hoặc custom event được kiểm soát |
| So sánh `nanoTime()` giữa hai JVM | Giá trị nanoTime không phải epoch timestamp chung | Dùng wall-clock đã đồng bộ để căn timeline |
| Tưởng custom event tự được ghi bất kể threshold | JFR có enabled/threshold/sampling/retention settings | Đọc cấu hình và kiểm tra có event trong `jfr summary` |
| Dùng `readAllEvents` cho file rất lớn | Nạp toàn bộ event vào RAM | Dùng `RecordingFile` duyệt từng event |
| Chứa email, token, payload trong event JFR | Có nguy cơ lộ dữ liệu qua recording | Chỉ ghi trường tối thiểu, không chứa dữ liệu nhạy cảm |
| Một biểu đồ cùng tăng là đủ xác nhận nguyên nhân | Tương quan không chứng minh nhân quả | Tìm stack/trace, can thiệp kiểm chứng, so baseline |
| Mở recording dày đặc vô hạn trên production | Có thể tạo overhead và dữ liệu lớn | Giới hạn duration, size, threshold, quyền và retention |

## 13. Thiết kế dashboard đối chiếu tối thiểu

Một dashboard chẩn đoán hiệu quả có thể chia thành ba tầng:

**Tầng ứng dụng (SLO):**
- RPS, error count/rate, p50/p95/p99 latency theo service/operation.
- Queue depth, active requests, retries hoặc dependency latency khi có.
- Chỉ số gắn đúng instance hoặc có khả năng lọc theo instance/deployment.

**Tầng JVM/JFR:**
- Process CPU, heap/GC activity, allocation signals.
- Thread blocking, park/wait, socket operations, execution sample nếu có.
- Một timeline JFR có thể truy ngược tới stack trace và event detail.

**Tầng tương quan:**
- Cùng cửa sổ UTC, cùng instance và deployment.
- Đánh dấu mốc deploy, tăng traffic, sự cố dependency.
- Custom event hoặc trace/log để nối request chậm đến operation JVM khi cần.

Lưu ý rằng JFR không tự cung cấp một **time-series dashboard metrics** giống hệ thống giám sát. Có thể mở recording trong **JDK Mission Control (JMC)** hoặc xử lý bằng `jfr`/API, rồi so sánh với hệ thống metrics. Quy trình xuất/nhập, quyền truy cập và phiên bản công cụ phải được dự án quản lý riêng.

## 14. Bài tập thực hành

### Bài 1 — Chọn đúng phép đối chiếu

Metrics báo `LOOKUP p95 = 350 ms` trong một phút, còn `jfr summary` báo `jdk.ExecutionSample` có 200 events. Có thể kết luận `200` trong số request LOOKUP chậm không?

**Đáp án:** Không. `jdk.ExecutionSample` là **mẫu thực thi**, không phải event đếm request. Cần biết số yêu cầu, phân bố latency và các trace/custom event thực sự tương ứng với LOOKUP.

### Bài 2 — Tìm nguyên nhân mismatch số event

Ứng dụng log 10.000 request trong 10 phút, recording chỉ có 200 custom events. Liệt kê ít nhất bốn cách giải thích.

**Đáp án gợi ý:**
1. JFR chỉ ghi trong **một phần** của 10 phút.
2. Recording lấy từ **một replica**, metrics cộng nhiều replica.
3. Custom event bị **threshold** lọc hoặc không được bật ở một phần khoảng thời gian.
4. Chỉ instrument một nhóm operation hoặc một số request được **sample**.
5. Bản ghi bị giới hạn bởi retention/max age/size hoặc có sai lệch thời gian giữa hai nguồn.

Không tự gọi đó là “mất 9.800 request” khi chưa kiểm tra cách thu thập.

### Bài 3 — Nối ID và so sánh operation

Giả sử:
- App metric/log: `lab-02, LOOKUP, ERROR, 25 ms`.
- Custom JFR event: `lab-02, LOOKUP, ERROR, duration≈24 ms`.
- Một GC event xảy ra trong cùng cửa sổ 1 phút.

**Hỏi:** Khẳng định chắc chắn nào hợp lý?

**Đáp án:** Hai bản ghi custom và app có cùng key, operation, outcome và duration gần nhau nên **có thể tương ứng cùng thao tác**, nếu key là duy nhất trong phạm vi thu. Chưa thể khẳng định GC là nguyên nhân; phải kiểm tra **start/end time**, chính JVM, phần giao thời gian và các bằng chứng khác.

### Bài 4 — Phân biệt timestamp và duration

~~~java
Instant now = Instant.now();
long before = System.nanoTime();
// Work...
long elapsed = System.nanoTime() - before;
~~~

**Hỏi:** Dùng `now` hay `before` để đặt sự kiện lên trục UTC của dashboard?

**Đáp án:** `now` là mốc wall clock có thể chuyển sang UTC. `before` chỉ là số đếm đơn điệu tương đối của JVM, thích hợp tính duration trong cùng tiến trình chứ không phải mốc ngày giờ chung giữa máy.

### Bài 5 — Thay đổi demo để thử mismatch

Trong chương trình `JfrMetricsCorrelationDemo`, hãy đổi field `event.outcome` thành `"UNKNOWN"` cho riêng `lab-02`, nhưng giữ AppMetric là `ERROR`. Dự đoán output nào đổi.

**Đáp án:** `Operation/outcome agree: false`. `Joined by correlation key` vẫn là `3` nếu khóa không đổi, cho thấy **ghép được cùng key không đồng nghĩa dữ liệu hai phía hoàn toàn nhất quán**.

### Bài 6 — Tại sao p95 không bằng “GC pause dài nhất”?

Giả sử p95 request latency là 420 ms, GC pause dài nhất được ghi là 150 ms. Có được suy ra GC chiếm 150/420 của p95 không?

**Đáp án:** Không. p95 là **thống kê phân bố nhiều request**, còn GC pause dài nhất là **một sự kiện JVM**. Chúng không cùng đối tượng đo hoặc mẫu số. Phải đối chiếu các khoảng request cụ thể với các GC pauses và phân bố bị ảnh hưởng trước khi ước lượng đóng góp.

## 15. Checklist trước khi kết luận một sự cố

- [ ] Xác định **số đo đích** (p95, errors, throughput...) và định nghĩa chính xác.
- [ ] Cùng **service, instance/JVM, deployment, operation** khi so sánh.
- [ ] Timestamp đã thống nhất múi giờ, có đánh giá clock skew, cửa sổ baseline/incident rõ ràng.
- [ ] Phân biệt **wall-clock timestamp** với elapsed time đo bằng `System.nanoTime()`.
- [ ] Đã xem **JFR event type, cấu hình, threshold, sampling và retention**.
- [ ] Không dùng `ExecutionSample` / `ObjectAllocationSample` count thay request count.
- [ ] Không dùng percentile tổng hợp để thay duration của một event riêng lẻ.
- [ ] Có trace/log/custom event nếu muốn gắn dấu hiệu JVM tới một request.
- [ ] Đã kiểm tra dữ kiện chống lại giả thuyết, không chỉ những dữ kiện ủng hộ.
- [ ] Recording được thu theo chính sách quyền truy cập, dữ liệu nhạy cảm, dung lượng và overhead.

## 16. Ghi nhớ trọng tâm

1. **Metrics ứng dụng** cho biết ảnh hưởng đến người dùng/nghiệp vụ; **JFR** cho biết hiện tượng JVM và các custom events đã instrument.
2. Muốn đối chiếu đúng, phải thống nhất **time window, process/instance, operation và population**. Đối với một request cụ thể, có thể thêm **correlation key có kiểm soát**.
3. **Count ≠ sampled event count; p95 ≠ tổng duration**. Phải hiểu threshold/sampling trước khi đọc ý nghĩa số liệu.
4. `Instant` đặt sự kiện trên timeline; `System.nanoTime()` đo elapsed time trong cùng JVM.
5. `jdk.jfr.Event` và `RecordingFile` cho phép thực hiện tương quan ở mức application event; `jfr summary`/`print` và `jcmd` là các công cụ CLI hiện hành.
6. Kết luận chính xác là **giả thuyết có bằng chứng**, không phải “hai biểu đồ cùng tăng nên A gây ra B”.

**Tài liệu chính thức (còn áp dụng):**
- [Oracle Java SE 17 — Flight Recorder API, tạo và ghi custom events](https://docs.oracle.com/en/java/javase/17/jfapi/creating-and-recording-your-first-event.html).
- [Oracle Java SE 17 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Oracle Java SE 17 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Oracle Java SE 17 — `RecordingFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Oracle Java SE 17 — lệnh `jfr`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html), gồm `summary`, `print` và lọc event.
- [Oracle Java SE 17 — lệnh `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html), gồm `JFR.start`, `JFR.dump`, `JFR.stop`.
- [Oracle Java SE 17 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
