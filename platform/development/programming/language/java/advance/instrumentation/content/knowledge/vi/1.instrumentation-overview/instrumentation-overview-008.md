# Tính đúng đắn của ứng dụng, chi phí quan sát và giới hạn của dữ liệu thu thập

Instrumentation giúp ta hiểu chương trình đang làm gì bằng cách gắn các điểm ghi nhận vào đường chạy: counter, timer, log, trace/span, sự kiện Java Flight Recorder (JFR), profiler hoặc Java agent biến đổi bytecode. Nhưng chính thao tác đo cũng chạy trong JVM, tiêu thụ tài nguyên và có thể làm lệch đối tượng đang được quan sát. Một hệ thống có nhiều biểu đồ chưa chắc đúng hơn hoặc dễ chẩn đoán hơn.

Bài này đặt ba câu hỏi phải trả lời cùng lúc:

1. **Tính đúng đắn:** Khi bật instrumentation, ứng dụng có còn giữ nguyên hợp đồng nghiệp vụ, ngoại lệ, trạng thái, thứ tự tác dụng phụ và tính an toàn luồng không?
2. **Chi phí quan sát:** CPU, bộ nhớ, I/O, độ trễ, thông lượng, GC và bộ lưu trữ tăng bao nhiêu trong tải thực tế?
3. **Giới hạn dữ liệu:** Tín hiệu thu được đại diện cho phần nào của hệ thống, có mất mẫu hay sai lệch không, và những kết luận nào không thể rút ra từ chúng?

Mục tiêu sau bài học: thiết kế điểm đo an toàn, đánh giá overhead có kiểm soát, đọc dữ liệu theo độ bao phủ và độ tin cậy, rồi xác định điều kiện chấp nhận một cơ chế instrumentation.

## 1. Đặt instrumentation đúng vị trí trong luồng chạy

Một đường đo điển hình có hai phần:

~~~text
Yêu cầu -> mã nghiệp vụ -> hook/interceptor/agent -> tạo tín hiệu
                                        |
                                        v
                               SDK / bộ đệm / batch
                                        |
                                        v
                             exporter -> collector -> lưu trữ/UI
~~~

Hook có thể được gọi trước, trong hoặc sau thao tác nghiệp vụ. Ngay cả khi exporter chạy bất đồng bộ, việc tạo span, đọc đồng hồ, tăng counter, lấy stack trace, gắn thuộc tính hoặc đưa dữ liệu vào queue vẫn có thể nằm trên luồng xử lý request. Vì vậy, "export bất đồng bộ" không đồng nghĩa "chi phí trên request bằng 0".

Phân biệt một số cách thu thập:

| Cơ chế | Thu được gì | Giới hạn cần nghĩ tới |
| --- | --- | --- |
| Metrics (counter, gauge, histogram) | Tổng hợp số lượng, trạng thái, phân phối độ trễ | Mất chi tiết của từng lần gọi; nhãn có cardinality cao làm tăng chi phí |
| Traces/spans | Đường đi và quan hệ các bước của từng giao dịch được giữ lại | Sampling, thiếu propagation, span mất hoặc kết thúc sai |
| Logs | Ngữ cảnh và thông điệp tại điểm phát log | Khối lượng lớn, lọc theo mức log, thiếu liên kết, dữ liệu nhạy cảm |
| JFR | Sự kiện JVM và ứng dụng theo cấu hình ghi hình | Chỉ có loại sự kiện được bật, ngưỡng sự kiện và khoảng thời gian được ghi |
| Sampling profiler | Các mẫu stack/CPU/allocation theo cơ chế lấy mẫu | Không phải nhật ký đầy đủ mọi lần gọi; mẫu có sai số và thiên lệch |
| Java agent/bytecode instrumentation | Tự động thêm hook vào các lớp/phương thức được hỗ trợ | Phụ thuộc vị trí biến đổi, khả năng transform, class loader và phiên bản thư viện |

Đừng coi các nguồn tín hiệu là các bản sao tương đương của "sự thật". Một counter có thể đếm chính xác tại điểm chèn của nó, trong khi một trace chỉ phản ánh các span đã được ghi, được lấy mẫu và chuyển thành công tới backend.

## 2. "Không làm đổi hành vi" là một hợp đồng cần kiểm chứng

Trong phạm vi nghiệp vụ, instrumentation tốt cố gắng bảo toàn các thuộc tính quan sát được của chương trình:

- **Giá trị trả về và trạng thái:** kết quả, dữ liệu ghi xuống database, thông điệp gửi đi, trạng thái transaction không đổi do code ghi nhận.
- **Ngoại lệ:** khi nghiệp vụ lỗi, phải giữ nguyên loại lỗi, nguyên nhân và đường lan truyền; lỗi telemetry không tự biến thành thành công hay lỗi nghiệp vụ khác.
- **Số lần/thứ tự tác dụng phụ:** không gọi lại thanh toán, không ghi thêm một message nghiệp vụ, không đổi thời điểm commit/rollback để lấy số đo.
- **Đồng thời:** không tạo lock order mới dẫn tới deadlock, không rò context giữa request, không khiến việc xử lý interrupt/cancellation sai đi.
- **Tài nguyên:** không giữ tham chiếu request hoặc payload quá lâu, không mở stream/socket không đóng, không tạo queue vô hạn.
- **Bảo mật:** không đưa mật khẩu, token, dữ liệu cá nhân hoặc thông tin bí mật vào log/span/metric label.

Đây là mục tiêu **tương đương ngữ nghĩa ở ranh giới nghiệp vụ**, không phải lời hứa rằng hai lần chạy có cùng thời gian hoặc cùng thứ tự lịch trình luồng. Thêm một lệnh đọc đồng hồ cũng có thể làm thay đổi thời điểm được scheduler chạy, thứ tự tranh chấp lock, trạng thái JIT cache và khả năng lộ race condition. Trong chương trình đồng thời, "thêm log thì lỗi biến mất" là dấu hiệu kinh điển của *observer effect*; dữ liệu không thể được xem là ảnh chụp hoàn toàn trung lập.

Với những hoạt động có nghĩa vụ ghi nhận chính xác như sổ cái, audit nghiệp vụ bắt buộc hoặc outbox transaction, hãy thiết kế **cơ chế ghi nhận bền vững thuộc nghiệp vụ**. Traces/logs best-effort có thể bị drop và không thay thế được ràng buộc đó.

## 3. Các cách instrumentation vô tình phá tính đúng đắn

### 3.1. Trộn lỗi của telemetry với lỗi nghiệp vụ

Ví dụ không an toàn về mặt ý tưởng: đặt thao tác nghiệp vụ và lời gọi exporter trong cùng một khối try/catch, rồi catch bất kỳ lỗi nào để trả một giá trị mặc định. Khi exporter lỗi, một thao tác nghiệp vụ đã thành công cũng có thể bị coi là thất bại; hoặc ngoại lệ gốc bị nuốt.

Thường nên tách hai ranh giới: **nghiệp vụ quyết định kết quả**, còn **thu thập best-effort ghi nhận kết quả ấy**. Khối finally hữu ích để ghi lại thời gian cả lúc thành công lẫn lúc lỗi, nhưng bản thân mã trong finally vẫn có thể ném ngoại lệ và che khuất ngoại lệ gốc; cần cô lập các lỗi telemetry dự kiến.

### 3.2. I/O hoặc blocking trong đường nóng

Một hook gọi exporter đồng bộ khi đang giữ lock, đang xử lý transaction hoặc chạy trong event loop có thể kéo dài thời gian giữ tài nguyên. Khi mạng treo, timeout lớn hoặc backend không phản hồi, độ trễ tăng đột ngột; trường hợp xấu có thể gây nghẽn luồng, deadlock hoặc làm trễ commit. Queue/batch có giới hạn giúp giảm tác động, nhưng vẫn cần định nghĩa hành vi khi queue đầy và có bộ đếm số tín hiệu bị bỏ.

### 3.3. Thay đổi điều kiện đồng thời và context

- Đưa log vào vùng synchronized có thể làm thay đổi thứ tự tranh chấp lock.
- Dùng ThreadLocal/MDC/trace context mà không đóng scope ở finally có thể làm request kế tiếp nhận nhầm trace ID, đặc biệt trên thread pool.
- Chuyển công việc sang CompletableFuture, executor, callback hoặc messaging boundary mà không truyền context khiến trace đứt; cố gắng truyền context không đúng lại gây rò rỉ.
- Tự instrument lại HTTP client được exporter dùng có thể tạo vòng lặp telemetry -> export -> telemetry; cần loại trừ đường exporter khỏi hook phù hợp.

### 3.4. Instrument sai lớp hoặc giai đoạn chạy

Ở Java, agent có thể biến đổi bytecode lúc load lớp hoặc, khi môi trường cho phép, retransformation cho lớp đã tải. Không phải mọi lớp đều có thể sửa và không phải mọi thay đổi cấu trúc lớp đều được hỗ trợ khi retransform. Kết hợp sai giữa Java agent, module access, class loader, thư viện và JVM có thể gây lỗi linkage, verify, khởi động hoặc coverage thiếu. Đừng suy luận rằng cứ bật agent là mọi phương thức trong process đều đã được quan sát.

### 3.5. Dữ liệu quan sát trở thành tác dụng phụ không mong muốn

Ví dụ: lấy chuỗi của toàn bộ object để ghi log có thể gọi toString() đắt đỏ, truy cập trạng thái lazy, ném lỗi, thậm chí rò thông tin. Capture body lớn có thể tăng allocation và thời gian GC. Gắn user ID hoặc request ID thành metric label có thể làm số time series tăng không kiểm soát. Đây là vấn đề đúng đắn về tài nguyên và bảo mật, bên cạnh chi phí lưu trữ.

## 4. Ví dụ Java 17+: giữ ngoại lệ nghiệp vụ khi recorder bị lỗi

Ví dụ sau minh họa **một tính chất cụ thể**: lỗi RuntimeException từ nơi ghi telemetry được cô lập để không thay giá trị trả về hay ngoại lệ nghiệp vụ. Đây là ví dụ chạy độc lập, chưa phải một exporter production tối ưu.

Tệp: **ObservationSafetyDemo.java**

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.LongAdder;

public class ObservationSafetyDemo {
    private static final LongAdder DROPPED = new LongAdder();

    @FunctionalInterface
    interface Recorder {
        void record(long elapsedNanos);
    }

    static <T> T observe(Callable<T> business, Recorder recorder)
            throws Exception {
        long started = System.nanoTime();
        try {
            return business.call();
        } finally {
            long elapsed = System.nanoTime() - started;
            try {
                recorder.record(elapsed);
            } catch (RuntimeException telemetryFailure) {
                DROPPED.increment();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Recorder unavailable = elapsed -> {
            throw new IllegalStateException("collector offline");
        };

        System.out.println(observe(() -> "OK", unavailable));

        try {
            observe(() -> {
                throw new IllegalArgumentException("invalid order");
            }, unavailable);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println("dropped=" + DROPPED.sum());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ObservationSafetyDemo.java
java ObservationSafetyDemo
~~~

Standard output đúng:

~~~text
OK
invalid order
dropped=2
~~~

Lần đầu nghiệp vụ trả "OK"; lần sau ném IllegalArgumentException như ban đầu. Cả hai lần recorder đều lỗi, được đếm vào DROPPED thay vì thay đổi hai kết quả nghiệp vụ. System.nanoTime() dùng đo khoảng thời gian tương đối trong cùng một JVM; nó không phải thời gian lịch để gắn timestamp giữa nhiều máy.

**Giới hạn của ví dụ:** lời gọi record vẫn đồng bộ; nếu recorder block lâu, request vẫn chậm. Nó chỉ cô lập RuntimeException của recorder, không cam kết an toàn trước mọi Error hay tài nguyên JVM cạn kiệt. Trong hệ thống thực tế, ưu tiên queue hữu hạn/batch, timeout phù hợp, cơ chế bỏ tín hiệu có kiểm soát, chống recursion và metrics cho số lượng bị drop. Không tạo vòng lặp bằng cách lại gửi lỗi exporter qua chính exporter đang lỗi.

## 5. Chi phí quan sát sinh ra ở đâu?

Một phép đo có thể thêm chi phí ở nhiều lớp, không chỉ trong lệnh gửi mạng:

| Thành phần | Chi phí thường gặp | Dấu hiệu có thể thấy |
| --- | --- | --- |
| Hook/interceptor/bytecode | Lời gọi phụ, đọc clock, lấy context, đường code không còn tối ưu như cũ | CPU tăng, latency trên hot path tăng |
| Thu thập chi tiết | Format log, serialize, stack trace, sao chép body, tạo attributes | Allocation/GC tăng, CPU tăng, dữ liệu nhạy cảm |
| Đồng bộ/bộ đệm | Lock, atomic update, queue contention, batch management | p99 nhảy vọt, throughput giảm, queue đầy |
| Export và mạng | Nén, serialization, retry, socket, TLS | Băng thông, CPU, thread, lỗi và độ trễ gửi |
| Backend | Parse/index/store/query, retention, cardinality | Dung lượng, số series, chi phí lưu trữ/truy vấn |
| Startup/class transform | Agent initialization, class loading/transformation | Startup chậm, lỗi tương thích, tải đầu phiên tăng |

Có thể hình dung độ trễ request quan sát được bằng **độ trễ nghiệp vụ cộng chi phí trên đường tới hạn và tác động tương tác**. Đây chỉ là mô hình tư duy: GC, contention, scheduler, JIT và queueing khiến tác động không cộng tuyến tính. Export chạy sau request có thể vẫn ảnh hưởng độ trễ của request khác do dùng chung CPU, memory, network.

Đặc biệt chú ý:

- **Per-event cost:** số lượng event mỗi giây và payload size; sự kiện hiếm có thể quá đắt nếu luôn lấy stack trace hoặc body.
- **Cardinality:** thêm một label động như full URL, user ID hay transaction ID có thể tạo số time series rất lớn. Dùng route template và tập nhãn có giới hạn.
- **Sampling:** giảm số trace xuất đi không có nghĩa giảm tương ứng phần trăm chi phí; vẫn có chi phí quyết định sampling, tạo context và một số hook/metric.
- **Backpressure:** buffer hữu hạn bảo vệ bộ nhớ nhưng đồng nghĩa có drop; buffer vô hạn có nguy cơ cạn heap. Chọn chính sách có ý thức.
- **JFR/profiling:** overhead phụ thuộc sự kiện, ngưỡng và cấu hình. Không áp một con số "JFR luôn không tốn chi phí" cho mọi workload hoặc mọi tập sự kiện.

## 6. Đo overhead bằng thực nghiệm, không suy từ số event

Trước khi triển khai rộng, xác định **ngân sách quan sát** với mục tiêu SLO của chính ứng dụng: độ trễ, thông lượng, CPU, heap, GC, network, kích thước telemetry và phần trăm tín hiệu bị bỏ. Không có một ngưỡng phần trăm phù hợp cho mọi dịch vụ.

Một phép đo so sánh có ý nghĩa nên:

1. Có **baseline** khi tắt hook đang đánh giá; so với cấu hình bật hook nhưng không export và cấu hình bật đầy đủ để phân biệt chi phí tạo tín hiệu với xuất tín hiệu.
2. Chạy cùng mã nghiệp vụ, JDK/JVM flags, heap, hạ tầng, tập dữ liệu và tải đủ đại diện cho production. Warm up để giảm nhiễu JIT/class loading.
3. So sánh ở **cùng offered load** khi xét latency, đồng thời đo thông lượng tối đa và mức bão hòa riêng. Thử cả tải thấp, tải ổn định, burst, concurrency cao và khi backend telemetry chậm/mất kết nối.
4. Lặp nhiều lần, luân phiên thứ tự cấu hình khi có thể, quan sát độ phân tán; tránh kết luận từ một lượt chạy đơn lẻ.
5. Ghi p50/p95/p99, throughput, error rate, CPU, allocation, GC pause, heap, queue length, dropped/failed exports, network và bộ nhớ backend.
6. Xem lại tính đúng đắn sau mỗi cấu hình, vì phép đo "nhanh" nhưng làm mất dữ liệu nghiệp vụ không thể được chấp nhận.

Ví dụ số liệu **giả định**, đo trên cùng loại request và điều kiện tải:

| Đại lượng | Không instrumentation | Bật instrumentation |
| --- | ---: | ---: |
| p99 latency | 80 ms | 88 ms |
| Throughput tối đa | 5.000 req/s | 4.700 req/s |
| Collector queue drop | 0 | Có khi tải đột biến |

Overhead p99 = (88 - 80) / 80 × 100% = **10%**. Mức giảm throughput tối đa = (5.000 - 4.700) / 5.000 × 100% = **6%**. Hai con số trả lời hai câu hỏi khác nhau; không thể dùng một tỉ lệ để suy ra tỉ lệ còn lại. "Collector queue drop" phải đo bằng số đếm/tỷ lệ thật trước khi quyết định triển khai; bảng này không ngầm khẳng định một tỷ lệ drop cụ thể.

Cần giữ nguyên tập endpoint, khung thời gian, cách sinh tải và cách tính percentile. p99 từ hai quần thể khác nhau không chứng minh overhead; p99 của một tập không thể tính bằng trung bình p99 của các nhóm. Nếu dùng histogram có bucket tương thích, có thể cộng số lượng bucket rồi ước tính quantile trên phân phối gộp.

## 7. Tại sao số liệu thu thập có thể không đầy đủ hoặc sai lệch?

Có ít nhất bảy lớp giới hạn. Khi nhìn dashboard, hãy hỏi dữ liệu đã đi qua lớp nào.

### 7.1. Coverage: có đặt hook ở đúng đường đi không?

Một HTTP server span chỉ bao phủ thời gian request tại server được instrument, chưa chắc có đầy đủ queue time phía trước, truy cập native code, công việc async sau khi trả response, background scheduler, message consumer hoặc bước ngoài process. Proxy/AOP chỉ bắt các điểm mà proxy thực sự đi qua; gọi nội bộ vượt qua proxy có thể không xuất hiện. Agent có thể thiếu hỗ trợ một phiên bản framework, bỏ qua lớp đã load, hoặc thiếu quyền transform.

Vì vậy, **không thấy một span** có thể là chưa instrument, mất context, bị sample, bị drop, hoặc công việc thực sự chưa chạy. Chưa có đủ dữ kiện để chọn một khả năng.

### 7.2. Sampling: mẫu được giữ không đồng nghĩa toàn bộ giao dịch

- **Head sampling** quyết định sớm (thường dựa trên trace ID và xác suất), giúp tiết kiệm tài nguyên nhưng chưa biết request sau đó sẽ lỗi hay chậm.
- **Tail sampling** quyết định sau khi thấy toàn bộ hoặc phần lớn trace để có thể ưu tiên lỗi/latency cao; đổi lại phải giữ dữ liệu tạm, chờ quyết định và có nguy cơ mất dữ liệu khi buffer đầy hoặc quá thời hạn.
- **Sampling không đồng đều** cố ý giữ nhiều giao dịch bất thường, hữu ích khi điều tra nhưng làm tập trace không đại diện ngẫu nhiên cho toàn bộ traffic. Không suy error rate trực tiếp từ tỷ lệ lỗi trong các trace được ưu tiên giữ.

Ví dụ: có 20.000 request, trong đó 20 request lỗi; lấy mẫu độc lập mỗi trace với xác suất 1%, không ưu tiên lỗi. Xác suất **không giữ được trace lỗi nào** xấp xỉ (1 - 0,01)^20 = **81,8%**. Dashboard trace có "0 lỗi đã quan sát" vẫn có thể tương ứng với 20 lỗi thật. Dùng bộ đếm lỗi độc lập, có ngữ nghĩa đúng và phạm vi bao phủ rõ ràng để đánh giá tổng số lỗi; dùng trace để điều tra đường đi của những trường hợp được ghi.

### 7.3. Mất dữ liệu: không có event chưa chắc sự kiện không xảy ra

Dữ liệu có thể mất tại SDK queue, lúc flush, khi process crash, do bộ lọc, quota, timeout, mạng, collector, storage retention hoặc truy vấn sai thời gian. Một event tới muộn cũng làm dashboard thời gian gần hiện thiếu. Cần tách:

- **Giá trị bằng 0 đã đo:** hệ thống đo hoạt động, cửa sổ quan sát và mẫu số xác định.
- **Không có điểm dữ liệu:** chưa biết do không xảy ra sự kiện hay pipeline bị gián đoạn.
- **Đã lấy mẫu:** chỉ biết về tập được giữ.
- **Đã drop hoặc chậm xuất:** pipeline ghi nhận thiếu hoặc chậm so với thực tế.

Cần theo dõi "sức khỏe của chính telemetry": failed export, queue usage, dropped spans/logs, thời gian batch, số collector nhận, độ trễ ingest, tình trạng flush và retention.

### 7.4. Độ chính xác đo lường và clock

Một timer đúng điểm bắt đầu/kết thúc mới đo đúng đại lượng định nghĩa. Đo từ khi server nhận request không đo toàn bộ thời gian từ phía người dùng. Ghi thời gian xử lý sau khi response đã gửi sẽ tạo một đại lượng khác. Clock treo tường có thể bị điều chỉnh; đồng hồ giữa các máy có thể lệch nhau. Dùng đồng hồ monotonic như System.nanoTime() cho thời lượng cục bộ, và xử lý cẩn thận việc so sánh timestamp xuyên máy.

Histogram có giới hạn độ phân giải do bucket; aggregation làm mất hình dạng phân phối chi tiết. Độ chính xác phép đo và độ chính xác **ý nghĩa** của metric là hai vấn đề khác nhau: một timer chính xác đến microsecond vẫn không cứu được việc chèn sai ranh giới nghiệp vụ.

### 7.5. Aggregation và mẫu số

Một giá trị như "500 lỗi" vô nghĩa nếu không biết cửa sổ, service, phiên bản, route, loại lỗi và tổng request tương ứng. Counter theo process có thể reset khi restart; rate cần xử lý reset phù hợp. Không được lấy trung bình p95/p99 của các nhóm để xem là p95/p99 của toàn bộ người dùng. Không nhân số trace sampled lên 100 lần để tạo số lỗi nếu cơ chế sampling không thỏa giả định xác suất và đại diện cần thiết.

### 7.6. Thiên lệch do thay đổi hệ thống

Instrumentation có thể làm ứng dụng chậm đi, đổi scheduling, thay chiến lược JIT hoặc làm queue đầy: dữ liệu sau khi bật agent là dữ liệu của **hệ thống đã có agent**. Profiler với tần suất cao có thể thay đổi chính hiện tượng đang tìm. Cần đối chiếu baseline, dùng công cụ ít xâm lấn khi phù hợp và mô tả rõ môi trường đo.

### 7.7. Ngữ cảnh, bảo mật và cách diễn giải

Một trace ID không chứng minh hai event có quan hệ nhân quả nếu propagation sai; correlation cùng thời điểm không tự chứng minh nguồn gốc lỗi. Nhãn sai hoặc tên sự kiện đổi giữa hai phiên bản làm dashboard nhìn liên tục nhưng ngữ nghĩa khác. Việc xóa/redact dữ liệu nhạy cảm có thể khiến trường chi tiết bị thiếu một cách chủ ý; đó là ràng buộc thiết kế, không phải lỗi cần "khắc phục" bằng cách ghi thêm bí mật.

## 8. Chọn tín hiệu đúng với câu hỏi cần trả lời

| Câu hỏi | Tín hiệu ưu tiên | Không nên kết luận |
| --- | --- | --- |
| Tỷ lệ request lỗi trong 5 phút? | Counter có định nghĩa rõ outcome và mẫu số; kiểm tra coverage/drop | Tỷ lệ lỗi trong trace đã sample = tỷ lệ lỗi toàn hệ thống |
| Một request chậm ở bước nào? | Trace đủ span/context; đối chiếu log và timer | Span vắng mặt = bước không chạy |
| Có lock contention/GC pause không? | JVM metrics, JFR và profiler được cấu hình phù hợp | Một stack sample đại diện toàn bộ execution |
| Memory tăng vì đâu? | Heap/allocation metrics, JFR/profiler, heap dump khi cần | Một event allocation là toàn bộ lượng cấp phát |
| Bao nhiêu đơn đã thanh toán thành công? | Nguồn dữ liệu nghiệp vụ đáng tin (DB/outbox/ledger) | Tổng số log "payment success" chắc chắn chính xác |
| Có quá tải collector không? | Queue utilization, failed exports, drops, ingest delay | Dashboard im lặng nghĩa là ứng dụng bình thường |

Quy tắc chẩn đoán: dùng ít nhất **một nguồn độc lập** để xác thực giả thuyết quan trọng, đặc biệt khi telemetry pipeline vừa có dấu hiệu lỗi. Định nghĩa rõ cửa sổ đo, môi trường, phiên bản triển khai, tags và tỷ lệ sampling.

## 9. Chính sách thiết kế để kiểm soát rủi ro

### 9.1. Giữ observer ở chế độ có thể thất bại an toàn

- Tránh network I/O đồng bộ và xử lý nặng trên đường request; giới hạn latency/CPU budget của hook.
- Giới hạn queue, batch size, payload size và số attributes; định nghĩa hành vi khi đầy (drop có đếm, sample thêm hoặc cơ chế khác đã được chấp nhận).
- Tách domain error với telemetry error. Với best-effort signals, lỗi exporter không quyết định kết quả transaction.
- Đảm bảo đóng scope/span/context trong finally hoặc try-with-resources phù hợp; không leak ThreadLocal trên executor.
- Chặn instrumentation vòng lặp và recursion; hạn chế instrument logic nội bộ của exporter.
- Có công tắc tắt/giảm chi tiết/sampling trong lúc sự cố và quy trình rollback được diễn tập.

### 9.2. Thu dữ liệu có chủ đích

- Chọn tên metric, unit, điểm chèn và outcome theo ngữ nghĩa nhất quán; tài liệu hóa "bắt đầu/kết thúc tính từ đâu".
- Dùng nhãn có cardinality thấp, ví dụ route template thay vì raw URI có ID. Tránh đưa dữ liệu định danh hoặc bí mật vào nhãn.
- Chỉ log thuộc tính giúp xử lý câu hỏi cụ thể; che hoặc bỏ dữ liệu nhạy cảm ngay trước khi đưa vào pipeline.
- Gắn service/environment/version, trace/span context và sampling policy để người đọc biết đang nhìn tập nào.
- Có giới hạn retention phù hợp mục tiêu điều tra; biết rằng dữ liệu cũ bị xóa theo chính sách.

### 9.3. Thiết kế kiểm chứng được

Với mỗi điểm đo quan trọng, ghi rõ bốn điều:

1. **Đại lượng:** định nghĩa chính xác sự kiện nào được tính, đơn vị là gì, và nhãn hợp lệ.
2. **Nguồn và coverage:** những đường chạy nào có hook; path nào không được quan sát.
3. **Chính sách mất dữ liệu:** sampling, giới hạn buffer, drop/retry, shutdown/flush, retention.
4. **Ngân sách và guardrail:** overhead tối đa chấp nhận được theo SLO, chỉ số sức khỏe pipeline, hành động khi vượt ngưỡng.

Đây là hợp đồng cho cả tác giả instrumentation lẫn người sử dụng dashboard. "Có metric" chỉ có ý nghĩa khi có định nghĩa, coverage và chất lượng dữ liệu đi kèm.

## 10. Quy trình QA trước khi bật trên diện rộng

Thử trên môi trường đại diện, rồi triển khai canary với tiêu chí dừng rõ ràng.

| Tình huống thử | Phải kiểm tra |
| --- | --- |
| Request thành công, trả dữ liệu, gọi DB/message | Kết quả và số lần tác dụng phụ như baseline; duration/attributes đúng phạm vi |
| Request ném exception, rollback, timeout, interrupt/cancel | Ngoại lệ gốc còn nguyên; không swallow, không thêm commit; scope/context đóng |
| Collector mất mạng, trả lỗi, chậm bất thường | Nghiệp vụ giữ SLO mục tiêu; retry/queue hữu hạn; lost telemetry được đếm |
| Tải cao, burst, nhiều luồng, lock contention | p95/p99, CPU, heap, GC, throughput; không deadlock hoặc rò context |
| Sampling thay đổi, exporter queue đầy, process restart | Biết những gì bị sample/drop; flush/shutdown theo chính sách; cảnh báo mất dữ liệu |
| Nâng JDK/framework/agent, class loading khác | Không lỗi class transform/linkage; kiểm tra lại coverage ở những điểm đo chính |
| Nội dung input mang token, user ID, payload lớn | Redaction đúng, không high-card label; giới hạn dung lượng và retention |

Ngoài thử ví dụ chạy thành công, hãy làm **fault injection** ở hệ thống quan sát: tắt collector, gây timeout, làm queue đầy, rút mạng, restart process, giảm sampling. Việc instrumentation còn hoạt động bình thường khi collector hoạt động tốt mới là điều kiện cần, chưa phải điều kiện đủ.

Tiêu chí chấp nhận nên tách ba trục:

- **Correctness PASS:** contract nghiệp vụ và các nhánh lỗi giữ đúng, không sinh side effect không mong muốn, kiểm tra concurrency/security.
- **Overhead PASS:** mức tăng latency/CPU/allocation và mức giảm throughput nằm trong ngân sách đã thống nhất dưới tải đại diện; biết chi phí backend.
- **Data-quality PASS:** có thể phát hiện drop/lag, coverage được ghi rõ, sampling và semantics được tài liệu hóa; dashboard không biến missing thành zero.

Khi một trục thất bại, giảm tần suất/tập dữ liệu, sửa vị trí hook, sửa exporter hoặc rollback. Không chấp nhận lỗi nghiệp vụ chỉ để có thêm trace.

## 11. Tình huống tổng hợp: tìm chậm ở luồng thanh toán

Một dịch vụ thanh toán được bật agent để theo dõi latency. Sau triển khai, p99 tăng từ 80 ms lên 88 ms; dashboard trace cho thấy ít lỗi, trong khi hệ thống thanh toán ghi nhận một số giao dịch thất bại.

Phân tích theo thứ tự:

1. **Xác nhận đúng đắn:** so sánh transaction status, idempotency key và số lệnh gửi gateway từ nguồn nghiệp vụ. Kiểm tra hook không gọi lại thanh toán hoặc nuốt exception khi exporter lỗi.
2. **Khoanh vùng overhead:** giữ cùng offered load, chạy baseline, chỉ local recording, rồi full export. So sánh CPU, allocation, lock, queue depth và p99 theo cùng request mix; thử collector bị chậm.
3. **Đọc dữ liệu đúng phạm vi:** kiểm tra sampling policy, trace context qua gateway và queue, số failed exports/dropped spans, độ trễ ingest. Ít trace lỗi không đủ chứng minh ít lỗi nghiệp vụ.
4. **Giảm chi phí có kiểm chứng:** bỏ raw payload, giảm attributes/high-card labels, giới hạn queue, điều chỉnh sampling hợp lý; đo lại và xác nhận transaction semantics.
5. **Ra quyết định:** chỉ giữ cấu hình mới nếu correctness, overhead và data-quality đều qua ngưỡng đã đặt, có cách phát hiện khi telemetry suy giảm.

Cùng một số "p99 tăng 10%" có thể đến từ hook, exporter tranh CPU, GC do allocation, lock contention hoặc workload thay đổi; cần dữ kiện phân tách trước khi quy lỗi cho một thành phần. Cùng một số "0 trace lỗi" có thể do không có lỗi, sampling, coverage thiếu hoặc pipeline mất dữ liệu; cần nguồn đối chứng.

## 12. Các nhầm lẫn cần tránh

- **"Đã có trace nên đã quan sát toàn bộ request."** Sai khi có sampling, thiếu propagation, đường chạy không được instrument hoặc mất export.
- **"Không thấy log nghĩa là không có lỗi."** Log có thể bị lọc, drop, ghi sai nơi hoặc chưa tới backend.
- **"Exporter async thì không ảnh hưởng latency."** Hook, allocation, queue và cạnh tranh tài nguyên vẫn có chi phí.
- **"Càng nhiều attributes càng tốt."** Cardinality, privacy, payload và chi phí xử lý có giới hạn.
- **"Bật JFR/profiler luôn có overhead cố định."** Chi phí tùy phiên bản, event/cấu hình và workload; phải đo.
- **"Instrumentation chỉ đọc nên không thể thay đổi hành vi."** Probe effect, lock, logging/toString, exception, biến đổi bytecode và tài nguyên có thể thay đổi kết quả.
- **"Trung bình các p99 bằng p99 chung."** Quantile không có tính chất cộng/trung bình như tổng số đếm.
- **"Mất telemetry là thất bại nghiệp vụ."** Chỉ đúng nếu thiết kế nghiệp vụ quy định tín hiệu đó là bắt buộc; thông thường observability best-effort cần tách khỏi transaction.

## 13. Câu hỏi tự kiểm tra

1. Nếu exporter ném RuntimeException trong finally của interceptor, điều gì có thể xảy ra với một exception nghiệp vụ đang được lan truyền? Bạn sẽ cô lập hai nguồn lỗi ra sao?
2. Vì sao giảm trace sampling từ 100% xuống 10% không đảm bảo giảm 90% CPU overhead?
3. Một dashboard không còn điểm dữ liệu sau deploy. Ba cách giải thích khác nhau là gì, và bạn cần chỉ số nào để phân biệt?
4. Với 20 lỗi và head sampling 1%, vì sao hoàn toàn có thể không có trace lỗi được lưu?
5. Làm thế nào kiểm tra instrumentation không phá transaction, không giữ lock quá lâu và không lộ dữ liệu nhạy cảm?
6. Bạn sẽ chọn metric, trace, log, JFR hoặc dữ liệu nghiệp vụ nào khi cần xác nhận một đơn hàng thực sự đã thanh toán?

**Điểm cốt lõi:** Quan sát hữu ích khi ứng dụng vẫn đúng, chi phí nằm trong ngân sách, và người đọc hiểu dữ liệu đại diện cho phần nào của thực tế. Luôn đánh giá ba mặt ấy cùng nhau.

## Tài liệu đọc thêm

- [Oracle Java 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): cơ chế Java agent, premain/agentmain và biến đổi bytecode.
- [Oracle Java 21 — Instrumentation API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): khả năng và giới hạn retransform lớp.
- [Oracle — Java Flight Recorder troubleshooting](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html): overhead của JFR phụ thuộc ứng dụng/cấu hình.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head/tail sampling và hệ quả khi suy luận từ tập trace được giữ.