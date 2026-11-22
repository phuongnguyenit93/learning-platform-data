# 2.4 Chỉ số tức thời, bộ đếm tích lũy, tốc độ thay đổi và phân bố độ trễ

> **Java Advance – runtime-diagnostics** · **2. Phương pháp đo**

## 1. Mục tiêu và bản đồ khái niệm

Khi quan sát một ứng dụng Java, dashboard có thể hiển thị *heap used = 900 MiB*, *requests completed = 2.000.000*, *throughput = 120 request/s* và *p99 latency = 800 ms*. Cả bốn là con số, nhưng biểu diễn bốn loại thông tin khác nhau. Đánh đồng chúng dễ dẫn tới chẩn đoán nhầm: nhìn counter như số request đang chạy, nhìn gauge như throughput, lấy trung bình các p99, hoặc gọi mọi spike là nguyên nhân gốc.

Sau bài này, bạn có thể:

- Phân biệt **chỉ số tức thời (gauge)**, **bộ đếm tích lũy (counter)**, **tốc độ thay đổi (rate)** và **phân bố độ trễ (latency distribution)**.
- Chọn phép đo phù hợp cho heap, threads, queues, request, exception, GC, CPU, I/O và timeout trong Java runtime.
- Tính delta/rate/increase, nhận diện counter reset, thiếu mẫu, sai đơn vị và cửa sổ đo không phù hợp.
- Đọc mean, median, p95, p99, histogram cộng dồn, tỷ lệ request dưới ngưỡng SLO và giới hạn của phép tổng hợp.
- Kết hợp nhiều metric thành một giả thuyết chẩn đoán có thể kiểm chứng thay vì suy diễn nguyên nhân từ một biểu đồ.

| Kiểu | Câu hỏi | Ví dụ | Phép tính nên dùng |
| --- | --- | --- | --- |
| Gauge | **Hiện đang có bao nhiêu?** | Heap bytes used, số request đang xử lý, số connection đang mượn, queue depth | Giá trị tại thời điểm, min/max, xu hướng; không tự suy ra số sự kiện |
| Counter | **Đã xảy ra/tích lũy bao nhiêu?** | Requests completed, exceptions, GC collections, bytes sent, CPU time seconds | Hiệu số trong một đoạn không reset; rate/increase có xét reset |
| Rate | **Mỗi đơn vị thời gian xảy ra bao nhiêu?** | Request/s, error/s, bytes/s, GC/s, CPU seconds/s | Mức thay đổi counter chia thời gian; chọn cửa sổ có đủ mẫu |
| Distribution | **Các request mất bao lâu, đuôi chậm thế nào?** | Latency buckets, p50/p95/p99, duration sum/count | Histogram, percentile, fraction dưới SLO, mean có trọng số |

Một điểm mấu chốt: **rate thường được tính từ counter**, nhưng bản thân rate là phép biến đổi dữ liệu theo thời gian; **percentile được tính từ phân bố**, không phải từ rate request. Tên metric cần đi kèm đơn vị, đối tượng đo, thời điểm và phạm vi như route/instance/version.

## 2. Gauge – ảnh chụp trạng thái tại một thời điểm

Gauge \(G(t)\) biểu diễn một trạng thái ở thời điểm \(t\); nó có thể tăng, giảm, về 0 hoặc giữ nguyên.

Ví dụ trong Java/JVM:

- *jvm_memory_used_bytes*: số byte đang sử dụng ở vùng nhớ được đo.
- *jvm_threads_live_threads*: số thread đang tồn tại; khác số thread đang bận thực thi request.
- *active_connections*, *idle_connections*, *pending_connections*: trạng thái pool tại thời điểm lấy mẫu.
- *in_flight_requests*: số request đã vào phạm vi đo nhưng chưa kết thúc.
- *queue_depth*: số phần tử đang nằm trong hàng đợi.

Giả sử gauge in-flight có các mẫu:

| Thời điểm | In-flight requests |
| --- | ---: |
| 10:00:00 | 5 |
| 10:00:15 | 18 |
| 10:00:30 | 40 |
| 10:00:45 | 9 |

Ở 10:00:30 có **40 request chưa hoàn tất**. Không thể nói “có 40 request mới trong 15 giây” hoặc “throughput 40 request/s”. In-flight có thể tăng vì traffic đến nhiều hơn, request chạy lâu hơn, retry tăng, executor nghẽn hoặc downstream chậm. Muốn phân biệt, cần **arrival rate**, **completion rate**, **timeout count** và **latency** trong cùng khoảng thời gian.

**Tại sao gauge có thể đánh lừa?** Nếu scrape mỗi 15 giây, một đỉnh queue depth 300 phần tử chỉ tồn tại 2 giây giữa hai lần scrape có thể bị bỏ lỡ. Một biểu đồ lấy giá trị cuối cùng trong cửa sổ cũng không giống biểu đồ lấy giá trị lớn nhất trong cửa sổ. Cần biết panel hiển thị *last*, *avg*, *max*, min hay nội suy; nếu sự cố ngắn, kết hợp log/trace hoặc số đo max theo cửa sổ phù hợp.

Gauge là trạng thái, không phải lượng công việc hoàn tất. Queue depth giảm 40 → 10 có thể do xử lý thành công, timeout, hủy, chuyển hàng đợi hoặc xóa; chỉ nhìn gauge không biết chính xác đã xử lý được 30 request.

**Lưu ý về bộ nhớ:** heap used tăng trong một khoảng ngắn không đủ để kết luận leak. Nhiều object mới được cấp phát rồi GC thu hồi vẫn có thể tạo đường cong răng cưa. Cần xem xu hướng sau những chu kỳ thu gom bình thường, allocation rate, heap committed, RSS và điều kiện tải. Metric heap used là **gauge**, còn số byte được cấp phát tích lũy (nếu có) là **counter**.

## 3. Counter – tổng tích lũy theo vòng đời của metric

Counter \(C(t)\) đếm số lần sự kiện xảy ra hoặc lượng công việc đã tiêu thụ. Trong một đoạn liên tục không reset, bộ đếm thường **không giảm**:

\[
C(t_2) \ge C(t_1)\quad \text{khi }t_2 \ge t_1.
\]

Các counter phổ biến: request hoàn tất, exception, retry, cache miss, bytes gửi, số lần GC, tổng thời gian CPU. Counter chứa **tổng từ thời điểm bắt đầu đếm**, không phải tổng của cửa sổ mà dashboard đang hiển thị.

Ví dụ tại cùng một JVM:

| Thời điểm | completed_requests_total |
| --- | ---: |
| 10:00:00 | 1.200 |
| 10:01:00 | 1.380 |

Trong đoạn 60 giây có **180 request hoàn tất** nếu counter không reset và cùng định nghĩa hoàn tất. Số 1.380 không nói rằng JVM có 1.380 request đang chạy đồng thời.

### Counter reset và việc đổi instance

JVM/process restart có thể làm counter quay về 0. Giả sử 10:01 counter = 1.380, 10:02 = 12 do restart. Hiệu số thô \(12-1380=-1368\) **không phải** âm 1.368 request; đây là một mốc reset. Nhiều hệ time series cung cấp hàm rate/increase có xử lý reset cho counter, nhưng độ chính xác vẫn phụ thuộc số mẫu và thời điểm thực tế của restart. Phần sự kiện phát sinh giữa hai scrape có thể không khôi phục chính xác được.

Khi có nhiều pod/JVM, **tính rate theo từng counter series trước khi cộng**. Tổng counter raw giữa các pod có thể giảm chỉ vì pod cũ biến mất, khiến phép trừ/tính rate sai. Cùng một nhãn service không đồng nghĩa cùng một lifecycle counter.

Một số counter không đếm **số sự kiện** mà cộng **thời lượng** hoặc **byte**. Ví dụ tổng CPU seconds tăng 120 trong 60 giây thực nghĩa là tốc độ CPU-time trung bình khoảng 2 CPU-seconds/second, tương ứng sử dụng trung bình thời gian của hai core trước khi xét hệ thống quota và cách dashboard quy đổi. Không được đọc trực tiếp tổng CPU seconds như phần trăm CPU tức thời.

Counter cũng có thể overflow hoặc bị tái khởi tạo theo lifecycle của bộ đo. Với phép tính cần độ chính xác, hãy kiểm tra hợp đồng instrument, timestamp và process start time.

## 4. Delta, increase và rate – lượng thay đổi trong một khoảng thời gian

Với một counter **không reset**, rate trung bình trên khoảng \([t_1,t_2]\) là:

\[
r=\frac{C(t_2)-C(t_1)}{t_2-t_1}.
\]

Nếu \(C\) có đơn vị request và \(t\) tính bằng giây, rate có đơn vị request/s. Với 1.200 → 1.380 request trong 60 giây:

\[
\Delta C=180\ \text{request};\qquad r=180/60=3\ \text{request/s}.
\]

| Cách đọc | Câu hỏi | Đơn vị |
| --- | --- | --- |
| Counter hiện tại | Từ lúc process bắt đầu, tổng đã hoàn tất? | request |
| Increase trong 5 phút | Có bao nhiêu request phát sinh trong 5 phút? | request |
| Rate 5 phút | Mỗi giây trung bình hoàn tất bao nhiêu request trong cửa sổ này? | request/s |
| Gauge in-flight | Ngay lúc lấy mẫu có bao nhiêu request đang xử lý? | request |
| Độ dốc gauge | Số lượng đang hiện diện thay đổi bao nhiêu mỗi giây? | request/s, nhưng **không phải throughput** |

Cách tính của hệ quan sát có thể phức tạp hơn hiệu hai điểm: hàm *rate* trong Prometheus dùng các mẫu của cửa sổ, xử lý counter reset và có ngoại suy đến ranh giới cửa sổ. Công thức hai điểm ở trên nhằm giải thích đơn vị và ý nghĩa, **không giả định thay thế hoàn toàn cho mọi time-series engine**.

### Error rate và error ratio là hai thứ khác nhau

Trong 60 giây, có 300 request hoàn tất, 12 request lỗi:

- **Request rate:** \(300/60=5\) request/s.
- **Error rate theo số sự kiện:** \(12/60=0{,}2\) lỗi/s.
- **Error ratio:** \(12/300=0{,}04=4\%\) request lỗi.

Trong giao tiếp, có nơi gọi 4% là “error rate”; khi viết dashboard hãy ghi rõ **errors/s** hay **error ratio (%)** cùng mẫu số. Khi không có request nào trong cửa sổ, biểu thức 0/0 **không xác định**; không tự báo 0% như hệ thống khỏe mạnh.

Không trộn retry attempt với logical request: nếu một request của người dùng retry ba lần, counter network attempts có thể tăng 3 trong khi counter logical requests tăng 1. Hai đại lượng đều hữu ích nhưng phải đặt tên và điểm đo riêng.

### Cửa sổ ngắn, cửa sổ dài và số mẫu

- Rate 30 giây phản ứng nhanh với spike, nhưng dễ nhiễu khi scrape thưa.
- Rate 5 phút thường ổn định hơn, nhưng có thể che một nghẽn kéo dài 20 giây.
- Rate 1 giờ hợp với bức tranh tải tổng quát, không thay thế điều tra timeline ngắn.
- Mất scrape không có nghĩa metric về 0. Nếu chỉ có một mẫu, không đủ cơ sở để tính rate đáng tin.
- Dùng timestamp thực tế khi so hai điểm; scrape trễ 8 giây khiến phép chia cứng cho 15 giây sai.
- Với counter reset, cần hàm có ngữ nghĩa counter hoặc chia các đoạn không reset; không dùng hiệu âm làm tốc độ.

**Đặc biệt với gauge:** \((G(t_2)-G(t_1))/\Delta t\) đo độ dốc trạng thái, không phải số sự kiện đến. Queue depth tăng 20 phần tử/phút có thể do arrival − departure = 20/phút, còn arrival rate thật có thể lớn hơn nhiều.

## 5. Latency là một phân bố, không phải một con số

Độ trễ \(L_i\) phải được định nghĩa bởi **điểm bắt đầu và kết thúc** cụ thể. Thời gian client nhìn thấy có thể bao gồm network, proxy, retry, kết nối và chờ trước khi ứng dụng xử lý; server handler latency có thể không bao gồm các phần này. Không so trực tiếp hai metric không cùng phạm vi rồi suy ra nguyên nhân bằng hiệu số.

Xét 10 request giả định với thời lượng đã sắp xếp (ms):

\[
20,\ 30,\ 35,\ 40,\ 45,\ 50,\ 70,\ 100,\ 300,\ 900.
\]

Tổng = **1.590 ms**; mean = \(1590/10=159\) ms. Tuy nhiên phần lớn request chỉ mất 20–100 ms, còn một request mất 900 ms. Mean **không cho biết hình dạng đuôi chậm**.

### Mean, median, p95 và p99

- **Mean:** tổng latency chia số request. Hữu ích cho tổng thời gian xử lý và ước lượng khối lượng công việc; rất nhạy với outlier.
- **p50/median:** mốc mà xấp xỉ 50% quan sát không vượt quá.
- **p95:** mốc mà xấp xỉ 95% quan sát không vượt quá; quan tâm đến 5% đuôi chậm.
- **p99:** mốc mà xấp xỉ 99% quan sát không vượt quá; quan trọng khi SLO nhạy với tail.
- **Max:** quan sát lớn nhất trong một cửa sổ, nhạy với một request bất thường.

Quantile của mẫu hữu hạn có nhiều quy ước. Với cách **nearest-rank**, sau khi sắp xếp \(n\) quan sát, phân vị \(p\) là phần tử ở vị trí \(\lceil p\cdot n\rceil\), đánh số từ 1. Trong 10 request ví dụ:

| Chỉ số | Kết quả |
| --- | ---: |
| Min / Max | 20 ms / 900 ms |
| Mean | 159 ms |
| p50 | 45 ms |
| p90 | 300 ms |
| p95 | 900 ms |
| p99 | 900 ms |

p95 và p99 cùng bằng 900 ms vì **chỉ có 10 mẫu**; đây không phải bằng chứng các percentile ấy “ổn định” ở 900 ms. Thư viện dùng phép nội suy khác có thể đưa ra con số khác. Đối chiếu dashboard phải biết phương pháp tính và cửa sổ đo.

Nếu route chỉ nhận 20 request trong một phút, p99 gần như do một request lớn nhất quyết định; không nên kết luận xu hướng tail latency với độ chính xác quá cao. Theo dõi **số request**, tỷ lệ timeout, p50/p95/p99 và phân bố để đọc đúng câu chuyện.

### Vì sao timeout có thể làm p99 đẹp giả tạo?

Một timer chỉ được ghi khi request **thành công** có thể bỏ qua những request bị timeout, reject hoặc hủy. Khi hệ thống tệ đi, request chậm nhất biến mất khỏi tập mẫu, khiến p99 của *successful requests* giảm! Vì vậy cần nhìn song song *arrival*, *completed*, *errors*, *timeouts*, *drops*, in-flight và độ trễ theo outcome. Định nghĩa metric là một phần của bằng chứng.

## 6. Histogram – lưu phân bố dưới dạng các bucket

Histogram đếm số quan sát theo ngưỡng. Với **classic cumulative histogram**, bucket “≤100 ms” chứa cả các request ở bucket “≤50 ms”. Tức bucket được **cộng dồn theo ranh giới**.

Áp dụng 10 request ở trên:

| Bucket cộng dồn | Số request |
| --- | ---: |
| ≤50 ms | 6 |
| ≤100 ms | 8 |
| ≤500 ms | 9 |
| +Inf | 10 |

Những phép suy ra đúng:

- Số request trong khoảng (50,100] ms là \(8-6=2\).
- Trong khoảng (100,500] ms là \(9-8=1\).
- Trên 500 ms là \(10-9=1\).
- Tỷ lệ request ≤100 ms là \(8/10=80\%\).

**Không cộng 6 + 8 + 9 + 10 để nói có 33 request.** Các bucket đều chứa những request ở ngưỡng nhỏ hơn. Bucket **+Inf** chứa toàn bộ phép đo hợp lệ.

Một classic duration histogram thường xuất:

- **_bucket{le="..."}**: bộ đếm tích lũy theo ngưỡng \(le\) (*less than or equal*).
- **_count**: tổng số phép đo đã ghi.
- **_sum**: tổng duration đã đo, cùng đơn vị với metric.

Đối với duration **không âm**, các đại lượng trên có ngữ nghĩa counter. Mean latency trong một cửa sổ có thể tính bằng:

\[
\overline{L}_{\text{window}} =
\frac{\Delta\text{duration\_sum}}{\Delta\text{duration\_count}}.
\]

Các hệ metrics có thể dùng native histogram hoặc summary/quantile sketches thay vì classic buckets; hãy kiểm tra loại metric và cách tổng hợp cụ thể. Đừng mặc định mọi histogram đều xuất một series *_bucket*.

### Percentile từ histogram chỉ là ước lượng

Từ bucket ≤500 ms có 9 request và +Inf có 10, không thể biết request cuối là **501 ms, 900 ms hay 30 s**. Histogram bucket chỉ lưu thông tin ngưỡng, không lưu mọi thời lượng chính xác. Ước lượng p95/p99 phải dựa trên ranh giới và quy tắc nội suy; bucket quá rộng sẽ làm ước lượng thô.

Thiết kế bucket gần ngưỡng SLO: nếu mục tiêu là **95% request ≤300 ms**, có ngưỡng **0.3 s** giúp tính trực tiếp tỷ lệ đạt SLO. Bucket quá dày trên nhiều nhãn làm chi phí metric tăng, bucket quá thưa làm mất thông tin ở đuôi. Với nhiều pod, bucket cần ranh giới và đơn vị **tương thích** trước khi cộng.

### Không lấy trung bình p99 của các instance

p99 không có tính kết hợp: nếu JVM A có p99=100 ms, JVM B có p99=900 ms, **500 ms không phải p99 toàn dịch vụ**. Để tính percentile toàn hệ, cần gộp dữ liệu phân bố (histogram buckets tương thích hoặc cấu trúc thống kê có khả năng merge), rồi mới ước lượng. Summary client-side với quantile xuất sẵn thường không cho phép suy ra global p99 bằng phép cộng/trung bình đơn giản.

Mean cũng có bẫy trọng số: instance A xử lý **1** request với mean 900 ms, B xử lý **99** request với mean 100 ms. Mean toàn hệ = \((1\cdot900+99\cdot100)/100=108\) ms, **không phải** trung bình thô \((900+100)/2=500\) ms. Hãy gộp **duration sum** và **duration count** rồi chia.

## 7. Thiết kế phép đo trong Java: đồng hồ, lifecycle và đa luồng

### Dùng đồng hồ thích hợp

- Dùng **System.nanoTime()** lấy chênh lệch elapsed time trong cùng tiến trình. Giá trị tuyệt đối của nanoTime không phải timestamp lịch và không để so trực tiếp giữa các JVM.
- Dùng **Instant.now()** hoặc timestamp có timezone khi cần gắn sự kiện vào timeline; wall clock có thể bị điều chỉnh.
- Chọn điểm bắt đầu/kết thúc theo câu hỏi: từ lúc HTTP request vào server, từ lúc handler chạy, từ lúc lấy connection hay từ lúc gọi dependency?

Ví dụ **minh họa, không phải chương trình độc lập**: trong handler có một tác vụ *work.run()* được truyền vào, đo:

~~~java
long startedNanos = System.nanoTime();
try {
    work.run();
} finally {
    long elapsedNanos = System.nanoTime() - startedNanos;
    // Ghi elapsedNanos vào duration recorder/histogram ở đây.
}
~~~

Không quên ghi metric trong nhánh lỗi hoặc timeout theo định nghĩa quan sát. Đổi nano giây sang mili giây/giây **nhất quán** và không làm tròn sớm. Với in-flight gauge, tăng khi request bắt đầu và giảm trong *finally* để lỗi không làm số đo bị “rò rỉ”.

### Instrument counter và histogram đa luồng

Để mỗi request chỉ tính một lần, đặt đúng điểm đếm:

- *started_total* tăng tại điểm chấp nhận request.
- *completed_total* tăng tại điểm kết thúc được định nghĩa; status chỉ biết sau khi xử lý.
- *in_flight* tăng ở đầu, giảm ở cuối dù exception.
- *duration* được quan sát đúng một lần cho mỗi request hoàn tất hoặc kết thúc theo chính sách đo.
- Retry attempt và logical request phải có metric riêng nếu cả hai cùng được theo dõi.

Trong Java, các biến dùng chung cần thao tác an toàn đồng thời như **AtomicInteger** hoặc **LongAdder**, hoặc thư viện metrics. Nhưng việc **mỗi biến cập nhật an toàn không bảo đảm một snapshot xuyên qua count/sum/buckets là nguyên tử**; một lần scrape đang chạy giữa các bước cập nhật có thể thấy sai khác nhỏ. Đây là lý do nên chọn thư viện observability phù hợp, hiểu độ trễ cập nhật và không dùng các snapshot tức thời để chứng minh bất biến tuyệt đối.

Một ứng dụng có lưu lượng cao không nên giữ vô hạn mọi giá trị latency chỉ để tính percentile; dùng histogram, summary hoặc quantile sketch có hợp đồng rõ ràng và chi phí được kiểm soát.

## 8. Ví dụ Java 17+ chạy được: từ gauge đến phân bố latency

Chương trình dưới đây dùng **JDK thuần**, không cần thư viện ngoài. Để có kết quả lặp lại, các duration được định sẵn: đây là **mô phỏng phép đo**, không phải benchmark tốc độ thật. Tạo file **MetricsDemo.java**.

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class MetricsDemo {
    private static final long[] LIMITS_MS = {50, 100, 500};
    private final AtomicInteger inFlight = new AtomicInteger();
    private final LongAdder completed = new LongAdder();
    private final LongAdder durationSumMs = new LongAdder();
    private final LongAdder[] buckets = {
        new LongAdder(), new LongAdder(), new LongAdder()
    };

    private void beginRequest() {
        inFlight.incrementAndGet();
    }

    private void endRequest(long elapsedMs) {
        if (elapsedMs < 0) throw new IllegalArgumentException("Negative latency");
        durationSumMs.add(elapsedMs);
        for (int i = 0; i < LIMITS_MS.length; i++) {
            if (elapsedMs <= LIMITS_MS[i]) buckets[i].increment();
        }
        completed.increment();
        inFlight.decrementAndGet();
    }

    private static long nearestRank(long[] sorted, double quantile) {
        return sorted[(int) Math.ceil(quantile * sorted.length) - 1];
    }

    public static void main(String[] args) {
        MetricsDemo m = new MetricsDemo();
        long[] observedMs = {20, 30, 35, 40, 45, 50, 70, 100, 300, 900};

        for (long ms : observedMs) {
            m.beginRequest();
            m.endRequest(ms);
        }
        // Có ba request mới còn đang xử lý tại lúc đọc gauge.
        for (int i = 0; i < 3; i++) m.beginRequest();

        System.out.println("in_flight=" + m.inFlight.get());
        System.out.println("completed_total=" + m.completed.sum());
        for (int i = 0; i < LIMITS_MS.length; i++) {
            System.out.println("duration_le_" + LIMITS_MS[i]
                + "_ms_total=" + m.buckets[i].sum());
        }
        System.out.println("duration_le_inf_total=" + m.completed.sum());
        System.out.println("duration_sum_ms=" + m.durationSumMs.sum());

        long[] sorted = observedMs.clone();
        Arrays.sort(sorted);
        System.out.printf(Locale.ROOT, "mean_ms=%.1f%n",
            (double) m.durationSumMs.sum() / m.completed.sum());
        System.out.println("p50_ms=" + nearestRank(sorted, 0.50));
        System.out.println("p95_ms=" + nearestRank(sorted, 0.95));
        System.out.println("p99_ms=" + nearestRank(sorted, 0.99));

        // Hai snapshot của một counter khác, cách nhau 60 giây.
        long counterBefore = 1200, counterAfter = 1380;
        System.out.printf(Locale.ROOT, "rate_per_second=%.1f%n",
            (counterAfter - counterBefore) / 60.0);
    }
}
~~~

Lệnh:

~~~bash
javac MetricsDemo.java
java MetricsDemo
~~~

Stdout:

~~~text
in_flight=3
completed_total=10
duration_le_50_ms_total=6
duration_le_100_ms_total=8
duration_le_500_ms_total=9
duration_le_inf_total=10
duration_sum_ms=1590
mean_ms=159.0
p50_ms=45
p95_ms=900
p99_ms=900
rate_per_second=3.0
~~~

Diễn giải:

- **in_flight=3** là gauge, biểu thị ba yêu cầu đang mở.
- **completed_total=10** là counter, đã hoàn tất mười yêu cầu.
- **duration_le_100_ms_total=8** là một bucket cộng dồn; **8/10** request hoàn tất trong 100 ms.
- **duration_sum_ms=1590** dùng với count 10 để tạo mean 159 ms.
- Quantile trong ví dụ tính **từ mảng dữ liệu gốc đã sắp xếp** theo nearest-rank, không suy ra từ bucket.
- **rate_per_second=3.0** tính từ hai snapshot counter giả định 1.200 và 1.380 **khác** counter mười request của demo; tách chúng để minh họa phép tính rate có đúng đơn vị.

Chương trình là mẫu học tập chạy đơn luồng về logic ghi nhận phép đo; không có thư viện scrape, không ghi metric theo route/status và không mô phỏng concurrency thực. Với ứng dụng sản xuất, cần timer/gauge/counter thread-safe của thư viện phù hợp, metric có phạm vi và lifecycle rõ, cùng một định nghĩa request hoàn tất, và kiểm tra sai lệch khi đọc nhiều counter đồng thời.

## 9. Ví dụ truy vấn khi dùng Prometheus classic histogram

Các tên metric dưới đây là **giả định minh họa**. Chỉ áp dụng nếu hệ thống thực sự export những metric và label đó; với native histogram hoặc backend khác, API truy vấn có thể khác.

**Throughput toàn dịch vụ**, request/s:

~~~promql
sum(rate(http_requests_total[5m]))
~~~

**Tốc độ lỗi 5xx**, errors/s:

~~~promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
~~~

**Error ratio** (0–1), với điều kiện có request và cùng điểm đếm:

~~~promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
~~~

Nếu mẫu số là 0/không có series, cần xử lý **no traffic/no data** đúng nghĩa, không tùy tiện gán thành 0% lỗi.

**Ước lượng p95 mỗi route từ classic cumulative buckets**, đơn vị giây:

~~~promql
histogram_quantile(
  0.95,
  sum by (route, le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

**Mean latency toàn hệ** trong cửa sổ 5 phút:

~~~promql
sum(rate(http_request_duration_seconds_sum[5m]))
/
sum(rate(http_request_duration_seconds_count[5m]))
~~~

**Fraction hoàn tất trong tối đa 300 ms**, chỉ khi bucket 0,3 giây thật sự tồn tại:

~~~promql
sum(rate(http_request_duration_seconds_bucket{le="0.3"}[5m]))
/
sum(rate(http_request_duration_seconds_count[5m]))
~~~

Điểm cần kiểm tra:

1. Hậu tố *_seconds* cho biết đơn vị **giây**; 0,3 s = 300 ms, không nhập 300 vào ngưỡng theo giây.
2. Nhãn **le** phải được giữ khi tổng hợp buckets classic cho *histogram_quantile*.
3. Tính **rate theo từng counter series rồi mới sum** để xử lý reset/membership có ngữ nghĩa.
4. Khi group theo *route*, chỉ gộp những instance có cùng ranh giới bucket và cách ghi latency.
5. Bucket lớn hơn ngưỡng SLO không thể suy ra chính xác fraction dưới SLO nhỏ hơn nếu không có ranh giới tương ứng.
6. Quantile từ bucket **là ước lượng**, phụ thuộc độ rộng bucket và lượng mẫu.

Không dùng raw request ID, user ID, order ID hoặc URL chứa ID động làm metric label: cardinality tăng gần theo **tích** số giá trị các nhãn, dễ làm đầy bộ lưu trữ metrics và lộ dữ liệu nhạy cảm. Dùng route template như */orders/{id}*, còn ID chi tiết đặt ở trace/log được kiểm soát.

## 10. Nhiều JVM, nhiều route và traffic mix

Khi aggregate hệ thống phân tán, câu hỏi đầu tiên là: các series có **cùng đơn vị, cùng cửa sổ, cùng điểm đếm, cùng định nghĩa outcome** không? Những phép kết hợp hợp lệ thường là:

- Cộng rate mỗi JVM để ra total request/s.
- Cộng in-flight gauge nếu request chỉ bị đếm một lần trong phạm vi mong muốn.
- Cộng duration sum và count, sau đó chia để có mean có trọng số.
- Cộng histogram bucket rates có cùng ranh giới, sau đó ước lượng percentile.
- Tính tỷ lệ lỗi bằng tổng error rate chia tổng request rate, thay vì trung bình ratio của pod ít và nhiều traffic như nhau.

Các phép kết hợp dễ sai:

- Trung bình p99 của các pod như global p99.
- Trung bình mean của các pod mà không theo số request.
- Cộng absolute counter của pod mới và cũ rồi lấy hiệu khi membership thay đổi.
- Gộp latency của route rất nhanh và rất chậm mà không nhìn theo route; traffic mix thay đổi có thể làm p99 toàn hệ tốt hơn dù một route đang regression.

Ví dụ: route A có 9.900 request nhanh, route B có 100 request rất chậm. Global p99 có thể che nhiều thông tin về B. Vì vậy dashboard nên giữ cả **view tổng** (ảnh hưởng toàn bộ) và **view theo route/status/version/instance** (khoanh vùng), với nhãn hữu hạn để không bùng nổ cardinality.

Các dashboard có thể thay đổi công thức hiển thị theo resolution: một panel trả percentile từ raw samples, panel khác từ histogram trên 5 phút. Hai giá trị ấy không nhất thiết giống hệt; cần kiểm tra nguồn và phép tổng hợp trước khi so sánh.

## 11. Sampling, mất mẫu và bẫy khi đo tail latency

### Số mẫu và độ ổn định thống kê

p99 ở cửa sổ chỉ có 10–20 request gần như bị chi phối bởi một quan sát chậm nhất. Với 100 request, vùng 1% cũng chỉ tương ứng khoảng một request. Khi phân tích low-traffic routes, báo kèm số request hoặc kéo dài cửa sổ một cách có giải thích, không tuyên bố p99 từng phút như một sự thật ổn định.

### Missing data khác giá trị 0

Một JVM vừa restart, một scraper không tiếp cận được endpoint hoặc time series bị bỏ nhãn có thể tạo lỗ dữ liệu. Đừng tự nội suy thành 0 request/s hoặc 0 heap used mà không xác minh. Khi nối timeline từ dashboard và log/JFR, đối chiếu timezone, timestamp, clock skew và độ trễ xử lý của pipeline.

### Trace sampling khác metrics

Trace có thể chỉ lấy mẫu 1% request, hoặc cố tình giữ lại các trace chậm/lỗi. Mẫu đó rất tốt để tìm stack/cơ chế, nhưng **không tự đại diện cho phân bố latency toàn bộ traffic**. Nếu histogram ghi mọi request còn tracing có sampling, không được tính p99 “toàn hệ” trực tiếp từ một tập trace ưu tiên lỗi mà thiếu trọng số và phương pháp lấy mẫu.

### Timeout và coordinated omission

Nếu bộ phát tải chỉ gửi request mới khi request cũ hoàn tất, lúc server nghẽn, arrival rate đo được có thể giảm theo server. Điều này có thể ẩn độ trễ mà người dùng ở tốc độ đến cố định sẽ chịu (**coordinated omission**). Khi benchmark, cần nêu arrival schedule, timeout, reject và cách ghi request chưa hoàn tất.

Cũng vậy, một histogram latency chỉ tính những request xử lý thành công có thể loại bỏ các request bị timeout/drop; p99 giảm nhưng trải nghiệm thực tệ đi. Đọc **p99 + request volume + timeout/drop/reject + error ratio** cùng nhau.

## 12. Tình huống thực hành: tìm vì sao p99 API tăng

*Tình huống giả định: số liệu minh họa phương pháp chẩn đoán, không phải kết quả benchmark.*

Sau một bản deploy, API /orders có p99 tăng từ 180 ms lên 1,4 s trong 10 phút. Dashboard cho thấy:

| Dữ liệu | Trước | Trong sự cố | Kiểu |
| --- | ---: | ---: | --- |
| Completed request rate | 120/s | 115/s | Counter → rate |
| In-flight | 12 | 90 | Gauge |
| Pending DB pool | 0 | 35 | Gauge |
| Timeout rate | 0,05/s | 5/s | Counter → rate |
| p99 server latency | 180 ms | 1,4 s | Distribution |
| Mean latency | 90 ms | 240 ms | Sum/count |
| Heap used | 620 MiB | 670 MiB | Gauge |
| GC pause p99 | 10 ms | 12 ms | Distribution |

**Điều có thể nói ngay:** in-flight và pending connection tăng trong khi completion rate không tăng, p99 và timeout rate tăng. Các dấu vết phù hợp với giả thuyết request đang **chờ tài nguyên** hoặc dependency trả lời chậm, nhưng chưa đủ để kết luận “DB pool config sai”.

**Giả thuyết H1 – DB pool cạn do giữ connection lâu:** nếu đúng, cần thấy thời gian acquire connection hoặc thời gian query tăng, nhiều request chờ pool, có stack/trace chỉ ra đường gọi.

**Giả thuyết H2 – traffic hoặc retry vượt công suất:** nếu đúng, arrival rate/attempt rate có thể tăng mạnh hơn completion rate; queue và in-flight tích tụ, retry từ gateway/client có thể khuếch đại vấn đề.

**Giả thuyết H3 – GC pauses:** với p99 GC pause 12 ms nhưng request p99 1,4 s, H3 ít được ủng hộ hơn nếu các mốc pause không trùng độ trễ. Tuy nhiên cần kiểm tra đúng cửa sổ, instance và các stop-the-world event khác trước khi loại trừ hoàn toàn.

**Bước điều tra:** so trace chậm với connection-acquire spans và DB latency; xem metrics pool/queue và thread states; đối chiếu arrival/completion/timeout rate, bản deploy, các instance đối chứng. Nếu giải pháp thử giảm thời gian giữ connection làm pending giảm và p99 ổn định trong tải tương đương, có thêm bằng chứng về cơ chế. Không tăng pool size ngay nếu DB đã bão hòa: tăng concurrency có thể khiến upstream và DB cùng suy giảm.

Một báo cáo chính xác cần nêu **tương quan**, **dấu vết ủng hộ/bác bỏ**, **cơ chế có thể kiểm**, **điều kiện tái hiện**, **biện pháp sửa** và **đo trước/sau**. Một metric riêng lẻ không chứng minh quan hệ nhân quả.

## 13. Lỗi thường gặp khi tạo hoặc đọc dashboard

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đọc raw request counter là throughput | Counter là tổng từ mốc khởi đầu | Tính rate trên cửa sổ, xét reset |
| Coi in-flight là request/s | In-flight đếm request tồn tại, không đếm sự kiện hoàn tất | Xem arrival/completion rate và latency |
| Tính rate từ hai mẫu nhưng dùng khoảng cách scrape lý tưởng | Timestamp thực tế có thể khác, có missing sample | Dùng timestamp thật/hàm rate của hệ đo |
| Tính rate âm sau JVM restart | Counter đã reset | Nhận diện reset, tính theo series |
| Lấy trung bình p99 của pod | Quantile không tổng hợp tuyến tính | Merge histogram hoặc phân bố rồi tính |
| Lấy trung bình mean pod không theo traffic | Pod xử lý số request khác nhau | Sum(duration_sum)/sum(duration_count) |
| Cộng các cumulative buckets | Một request bị đếm ở nhiều bucket | Tổng dùng count/+Inf; khoảng dùng hiệu bucket |
| Dùng bucket 1 s để khẳng định SLO 300 ms | Không có số request chính xác trong 300 ms | Tạo ranh giới 0,3 s ở instrument |
| So latency ms với metric *_seconds* không quy đổi | Sai 1.000 lần | Công bố đơn vị, quy đổi đúng |
| Chỉ nhìn p99 khi traffic thấp | Tail sample quá ít | Báo count và cửa sổ/phương pháp |
| p99 success giảm ⇒ chất lượng tăng | Timeout bị loại khỏi mẫu có thể tăng | Xem timeout/drop và mọi outcome |
| Heap used tăng ⇒ memory leak | Heap là gauge, có thể biến động theo GC/tải | Xem retained trend, allocation rate, RSS |
| Không phân biệt logical request và retry attempt | Double-count và sai error ratio | Tách metric theo điểm đếm |
| Metric label chứa ID động | Cardinality/chi phí và rủi ro thông tin | Dùng route template và nhãn hữu hạn |

## 14. Checklist đo và diễn giải trong runtime diagnostics

Trước khi kết luận, trả lời đủ các câu hỏi:

1. **Số này đo cái gì?** Gauge/counter/rate/histogram/summary? Đơn vị gì?
2. **Điểm đo ở đâu?** Client, gateway, handler, queue, pool, database, JVM hay OS?
3. **Thời điểm/cửa sổ nào?** Scrape interval, event timestamp, timezone, restart/missing sample?
4. **Mẫu số là gì?** Có bao nhiêu request thực sự được ghi? Có bỏ timeout, failed, dropped không?
5. **Tổng hợp ra sao?** Per-route, per-instance hay toàn dịch vụ? Bucket tương thích? Có lấy trung bình percentile sai?
6. **Số liệu có biến dạng do tải không?** Traffic mix, autoscaling, retry, sampling, queue, GC, heap và CPU quota?
7. **Giả thuyết nào có thể bị bác bỏ?** Metric nào hoặc trace/stack/JFR nào sẽ xác nhận/cải thiện mức tin cậy?
8. **Sau sửa có đo lại không?** So cùng điều kiện, theo dõi latency distribution, rate, errors, in-flight và chi phí tài nguyên.

## 15. Bài tập có đáp án

**A.** Counter request hoàn tất từ 2.400 lên 2.760 trong đúng 2 phút, không reset. Có bao nhiêu request và bao nhiêu request/s?

**Đáp án:** 360 request, \(360/120=3\) request/s.

**B.** Queue depth tăng 15 → 35 sau một phút. Có thể kết luận arrival rate là 20 request/phút không?

**Đáp án:** Không. Đây là tăng ròng 20 phần tử; cần số lần enqueue, dequeue, timeout/drop để biết arrival và completion.

**C.** Trong một phút có 240 request hoàn tất, 18 lỗi. Request rate, error rate theo số sự kiện và error ratio?

**Đáp án:** 4 request/s, 0,3 lỗi/s và 7,5%.

**D.** Classic histogram có ≤100 ms: 80, ≤300 ms: 95, +Inf: 100. Bao nhiêu request trong (100,300] ms và bao nhiêu request >300 ms?

**Đáp án:** 95−80=15 request trong (100,300] ms; 100−95=5 request trên 300 ms.

**E.** Pod A có 1 request mean 900 ms, pod B có 99 request mean 100 ms. Mean toàn dịch vụ?

**Đáp án:** 108 ms, bằng tổng duration chia tổng count. Không lấy trung bình thô 500 ms.

**F.** Hai pod có p99 lần lượt 100 ms và 900 ms. Global p99 có bằng 500 ms không?

**Đáp án:** Không thể suy ra như thế; cần dữ liệu phân bố/histogram tương thích và lượng request.

**G.** Sau deploy, p99 của request thành công giảm nhưng timeout/s và in-flight đều tăng. Có thể báo hệ thống đã nhanh hơn không?

**Đáp án:** Chưa. Slow requests có thể đã timeout và biến mất khỏi phân bố success; kiểm tra mọi outcome, arrival/completion, pending queue và trace.

## Ghi nhớ

**Gauge = hiện đang có**, **counter = đã tích lũy**, **rate = tốc độ thay đổi theo thời gian**, **distribution = latency trải ra như thế nào**. Đơn vị, cửa sổ, reset và số mẫu quyết định giá trị chẩn đoán. Mean không thay thế p99; p99 của các pod không thể lấy trung bình để thành global p99. Hãy kết hợp throughput, gauges về tình trạng chờ, histogram/quantiles, lỗi/timeout, metric JVM và trace trên cùng timeline để đi từ triệu chứng đến giả thuyết có thể kiểm chứng.