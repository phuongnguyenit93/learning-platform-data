# 2.7 Nhận diện sai lệch do khởi động, JIT, GC, lấy mẫu và chính công cụ quan sát

Một con số hiệu năng không tự giải thích nguyên nhân của nó. Cùng một phương thức Java có thể chạy chậm khi mới khởi động, nhanh hơn sau khi JIT tối ưu, chậm đột ngột vì GC hoặc bị hệ điều hành ngắt lịch. Một profiler có thể khiến hành vi thay đổi; một cách lấy mẫu không phù hợp có thể bỏ sót đúng những lần chậm nhất. Trong **phương pháp đo hiệu năng và chẩn đoán JVM**, nhiệm vụ không chỉ là thu thập con số, mà còn phải nhận diện **nó đại diện cho giai đoạn, đối tượng, công cụ và điều kiện nào**.

Bài này tập trung vào Java 21 và những nguyên lý có thể áp dụng cho nhiều JVM. Các lệnh **jcmd**, **-Xlog** và một số hành vi compiler được nêu cụ thể cho **JDK 21 dùng HotSpot**; khi dùng VM hoặc bản JDK khác, phải xác minh khả năng trên tiến trình thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:
- Phân biệt **startup/cold**, **warmup** và **steady state** khi thiết kế phép đo.
- Nhận biết dấu hiệu **JIT compilation, tiered compilation, OSR, deoptimization** có thể làm biến động kết quả, đồng thời tránh gán nguyên nhân khi chưa có chứng cứ.
- Phân tích ảnh hưởng **GC pause, GC đồng thời, allocation và safepoint** đến latency, throughput và CPU.
- Nhận diện **sampling bias**, chu kỳ lấy mẫu bị đồng bộ với sự kiện, p95/p99 thiếu mẫu và **coordinated omission**.
- Đánh giá **observer effect** do log, profiler, JFR, thread dump, agent, metric collection hoặc ngay cả vòng lặp đo thời gian.
- Thiết kế một lượt so sánh có baseline, kiểm soát biến, lặp lại, đối chiếu nhiều nguồn dữ liệu và lưu đầy đủ metadata.

## 1. Trước hết: định nghĩa chính xác “đã đo được gì”

Giả sử kết quả cho biết một request mất **120 ms**. Cần hỏi:

- **Mốc bắt đầu/kết thúc** là gì: tại load generator, cổng HTTP, hàng đợi, method Java hay database?
- Dùng **wall-clock elapsed time** hay **CPU time**? **System.nanoTime()** phù hợp để lấy khoảng thời gian trôi qua trong cùng tiến trình, nhưng wall time cũng tính cả lúc thread chờ I/O, chờ lock, bị ngừng vì GC hay không được OS cấp CPU.
- Đang đo **một invocation**, một batch, một request end-to-end, hay **thời gian đáp ứng của tất cả request**?
- Bao nhiêu phép đo đã được lấy? Có request nào bị bỏ qua, timeout, được retry hoặc bị loại khỏi phân phối không?
- Số liệu được lấy ở **giai đoạn cold, warmup, steady state** hay trộn cả ba?
- Quan sát được diễn ra **trước hay sau khi bật** log, profiler hoặc một diagnostic command?

Một mô hình tư duy hữu ích:

**Thời gian quan sát = công việc ứng dụng + thời gian chờ + tác động runtime + tác động quan sát + tương tác giữa các yếu tố.**

Đây **không phải phép cộng chính xác**: GC và ứng dụng có thể chạy đồng thời; JIT có thể thay đổi đường thực thi; công cụ quan sát có thể đổi tần suất GC hoặc lịch thread. Muốn truy nguyên, cần xem **timeline** thay vì trừ từng bộ đếm một cách máy móc.

| Chỉ số | Trả lời câu hỏi | Điều dễ hiểu sai |
| --- | --- | --- |
| **Latency end-to-end** | Người gọi chờ bao lâu, tính cả queue/network theo điểm đo | Đồng nhất với CPU time của method. |
| **Throughput** (request/s, op/s) | Hoàn tất được bao nhiêu đơn vị công việc trong thời gian xác định | Càng cao luôn có p99 càng tốt; throughput có thể tăng cùng lúc tail latency xấu đi. |
| **CPU time / CPU utilization** | Tài nguyên CPU đã dùng ở phạm vi đo | Không gồm đầy đủ thời gian chờ; CPU utilization cao chưa chứng minh ứng dụng compute-bound. |
| **Allocation rate / heap occupancy** | Đang sinh object và chiếm bộ nhớ ra sao | Heap sử dụng cao tự động đồng nghĩa GC pause dài. |
| **GC count / GC time / pause event** | Collector đã thực hiện công việc nào, khi nào | Cộng GC time là ra chính xác latency mỗi request. |
| **p50, p95, p99, max** | Phần đuôi phân phối độ trễ | Một vài mẫu hoặc trung bình các p99 có thể mô tả sai phân phối gốc. |

Trong báo cáo, ghi cả **đơn vị**, **quy tắc chọn mẫu** và **cửa sổ đo**. Ví dụ, “p99 80 ms của 50.000 request hoàn tất trong 5 phút sau warmup” hữu ích hơn “p99 = 80”.

## 2. Sai lệch do khởi động: cold khác steady state

### 2.1. Vì sao lần đầu không đại diện cho lần sau?

Trong giai đoạn đầu của tiến trình Java, có thể xuất hiện:
1. JVM khởi tạo runtime, class loader, bộ nhớ và các thành phần hệ thống.
2. Class được **load, verify, link**, rồi **initialize** khi cần; static initializer của ứng dụng hoặc thư viện có thể thực hiện công việc lớn.
3. Framework tạo dependency, cấu hình kết nối, proxy, serializer; cache ứng dụng hoặc OS còn nguội.
4. Method ban đầu được thông dịch hoặc biên dịch ở mức thấp hơn; HotSpot thu thập profile để quyết định tối ưu.
5. JIT biên dịch và có thể biên dịch lại method; GC/heap thích ứng với nhịp allocation.
6. Sau một thời gian, các yếu tố chính có thể ổn định tương đối, nhưng **không có bảo đảm** rằng JVM đã đạt một trạng thái cố định vĩnh viễn.

Đó là lý do cùng một workload có thể có “**first call** chậm hơn” mà không phải regression. Ngược lại, nếu hệ thống sản xuất yêu cầu phản hồi ngay khi vừa deploy hoặc scale-out, **cold-start latency là yêu cầu thực**; không được làm đẹp kết quả bằng cách bỏ phần đầu.

### 2.2. Xác định chế độ đo trước khi chạy

**Đo startup** cần nhiều **tiến trình mới độc lập**, lấy mốc cụ thể (ví dụ, từ launch đến ready hoặc từ request đầu tiên đến response). Mỗi lần khởi động nên ghi điều kiện cache, warm filesystem, DNS, kết nối, số process song song và CPU quota. Khởi động lại Java process chưa chắc làm nguội OS filesystem cache; cần nêu giới hạn thí nghiệm.

**Đo steady state** cần warmup riêng với tải, dữ liệu, đường code, thread count và cấu hình gần giống giai đoạn measurement. **Không có số lượng warmup vòng lặp cố định** áp dụng cho mọi ứng dụng. Hãy xem xu hướng theo thời gian và dấu hiệu compiler/GC để chọn thời điểm; khi throughput, CPU, allocation hoặc tail latency còn trôi mạnh, gọi là steady state là quá sớm.

**Đo hành vi đổi pha** (ví dụ tăng tải, một feature mới lần đầu được gọi, cache hết hạn, resize thread pool) cần giữ toàn bộ timeline. Trộn warmup và steady state rồi chỉ báo một số trung bình sẽ xóa mất thông tin thực sự cần phân tích.

### 2.3. Sai lệch do lựa chọn điểm bắt đầu

- Bắt đầu stopwatch **trước khi class đầu tiên khởi tạo** đo cả startup/class initialization; bắt đầu sau khi class đã sẵn đo một phạm vi khác.
- Không “warmup” riêng nhánh **success** rồi đo cả nhánh **exception**; đường thực thi và cấu trúc branch khác.
- Warmup bằng dữ liệu nhỏ, cache trống, ít thread rồi đo dữ liệu lớn, cache đầy và nhiều thread **không phải** cùng một chế độ.
- So sánh hai bản build theo thứ tự cố định A rồi B có thể bị ảnh hưởng bởi cache, nhiệt độ CPU hoặc tải nền thay đổi. Lặp, đổi thứ tự và tách process để giảm rủi ro.

## 3. Sai lệch do JIT: mã Java có thể thay đổi đường thực thi ngay trong phép đo

### 3.1. Những cơ chế cần hiểu

Trong cấu hình HotSpot phổ biến của JDK 21, **tiered compilation** cho phép runtime dùng nhiều mức thực thi/biên dịch, thường kết hợp interpreter, compiler C1 và C2. Một method có thể được biên dịch khi nó đủ “nóng”; một vòng lặp đang chạy có thể chuyển sang compiled code thông qua **on-stack replacement (OSR)**. Compilation thường được xử lý bởi compiler threads ở nền, nên phép đo còn có thể bị ảnh hưởng bởi CPU mà compiler dùng.

HotSpot có thể dùng **inlining**, **constant folding**, **loop optimization** hoặc **escape analysis** theo thông tin runtime. Nếu các giả định tối ưu hóa không còn đúng, VM có thể **deoptimize**, sau đó chạy ở mức khác và có thể biên dịch lại. Đây là cơ chế bình thường của JVM; một điểm latency tăng không tự chứng minh đã có deoptimization.

Các nguồn nhiễu thường gặp:

| Hiện tượng | Biểu hiện có thể gặp | Cần bằng chứng gì? |
| --- | --- | --- |
| **Method được biên dịch dần** | Batch đầu biến động mạnh, batch sau nhanh hơn | Timeline theo batch, compiler activity, điều kiện workload không đổi. |
| **Biên dịch nền cạnh tranh CPU** | CPU tăng cùng lúc latency tăng | Compiler threads/event và CPU của toàn process; loại trừ tải khác. |
| **OSR / deoptimization / recompilation** | Thời gian đổi sau một số lần lặp hoặc đường nhánh mới | Dữ liệu compilation/deoptimization phù hợp với thời điểm, không chỉ đồ thị latency. |
| **Dead-code elimination hoặc constant folding trong benchmark** | Microbenchmark “quá nhanh để tin”, input thật bị thay bằng hằng | Kiểm tra dữ liệu runtime, side effect quan sát được và thiết kế benchmark. |
| **Escape analysis / inlining làm allocation biến mất** | Số object đo được khác số lần dùng cú pháp **new** | Định nghĩa phép đo allocation, trạng thái tối ưu và profile thực tế. |
| **Code/cache hoặc nhánh dữ liệu khác** | Cùng method nhưng kết quả phụ thuộc dữ liệu | Giữ input distribution, branch behavior và cấp phát tương đương. |

**Không dựa duy nhất vào chênh lệch batch đầu/batch sau để kết luận “do JIT”.** Class loading, page cache, GC, CPU frequency, scheduler và I/O đều có thể diễn ra đồng thời.

### 3.2. Tránh microbenchmark đánh lừa người đo

Ví dụ minh họa **không dùng để benchmark thực tế**:

~~~java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    int result = 21 * 2;
}
long elapsed = System.nanoTime() - start;
~~~

Đoạn này không độc lập thành chương trình hoàn chỉnh. **result** không được sử dụng, phép nhân là hằng số; compiler có thể loại bỏ hầu hết công việc. Thời gian báo được chủ yếu phản ánh vòng đo và những yếu tố runtime khác, không cho biết chi phí một phép nhân có đầu vào thật.

Tránh thêm **System.out.println()**, cấp phát object đo đạc hoặc ghi file vào **mỗi iteration** của đoạn đang benchmark nếu chúng không phải là công việc cần đo. Những hành động đó vừa tốn thời gian vừa thay đổi profile/JIT và allocation. Đừng “chữa” bằng cách chỉ tăng số vòng lặp: compiler có thể tối ưu khác khi vòng lặp dài hơn.

Khi đánh giá **một thao tác Java nhỏ**, nên dùng **JMH (Java Microbenchmark Harness)**, một harness của OpenJDK với warmup, measurement iterations, fork JVM và cơ chế tiêu thụ kết quả. Dùng trạng thái và đầu vào có ý nghĩa, kiểm tra tối ưu hóa, chạy nhiều fork độc lập và xem độ phân tán. JMH giúp giảm sai lệch phổ biến nhưng **không biến benchmark không đúng workload thành phép đo production**.

Với **request end-to-end**, load test kiểm soát tốc độ đến, thời gian chờ, phối hợp concurrent clients và quan sát runtime phù hợp hơn một JMH benchmark của method đơn lẻ.

## 4. Sai lệch do GC: không chỉ là pause

Một lần GC có thể ảnh hưởng quan sát theo nhiều cách:

- Một số pha **stop-the-world** làm application threads tạm dừng; request đang ở giai đoạn đó có thể tăng wall latency.
- Collector có các công việc **đồng thời**, vẫn tiêu thụ CPU/băng thông bộ nhớ và có thể cạnh tranh với ứng dụng dù không tạo một pause tương ứng.
- Application allocation rate, live set, heap sizing, GC policy và thời điểm thu gom ảnh hưởng đến hành vi, đôi khi đổi khi input hoặc JIT thay đổi.
- **Safepoint**, lock contention, OS scheduling và CPU throttling cũng gây khoảng dừng hoặc chờ; không được gắn nhãn “GC” chỉ vì thấy một khoảng trống trong timeline.
- Lệnh chẩn đoán như **GC.class_histogram** hoặc **GC.heap_dump** có thể có tác động lớn, thậm chí làm méo dữ liệu đang điều tra.

### 4.1. Kiểm tra tương quan theo thời gian

Giả sử request R mất **250 ms**, và trong khoảng request đó có một GC pause **40 ms**. Ta có chứng cứ rằng pause **có thể đóng góp** vào độ trễ, nhưng không thể tự động khẳng định “request mất 210 ms xử lý ứng dụng + 40 ms GC”: request có thể đã chờ hàng đợi/lock/I/O, và các khoảng thời gian có thể chồng lấn tùy điểm đo.

Để kết luận chắc hơn, hãy:
1. Đồng bộ hoặc chuyển đổi timestamp thành cùng một trục thời gian; phân biệt **timestamp tuyệt đối** và **JVM uptime**.
2. Đặt **request trace**, GC/safepoint event, load, CPU và queue depth cạnh nhau.
3. Xác định request bị ảnh hưởng có thực sự **overlap** pause hay không; đừng chỉ dựa vào GC count tăng trong cùng phút.
4. Xem còn tác nhân nào khác: chờ lock, disk/network, request backlog hoặc compiler contention.
5. Kiểm tra lại trên nhiều đợt thay vì một lần trùng hợp.

**GarbageCollectorMXBean.getCollectionCount()** và **getCollectionTime()** là chỉ số tích lũy, có thể trả **-1** khi không có dữ liệu hỗ trợ. Ý nghĩa/độ chính xác phụ thuộc implementation; đặc biệt **không lấy chênh lệch tổng GC time của nhiều collector rồi xem đó là tổng pause của một request**. Dùng GC log hoặc sự kiện JFR có timestamp khi cần quan hệ thời gian chính xác hơn.

### 4.2. Thu thập dữ liệu vừa đủ trên HotSpot/JDK 21

Khi bạn kiểm soát JVM lúc khởi động, có thể bật Unified Logging ở mức phù hợp. Ví dụ:

~~~bash
java -Xlog:gc,safepoint:file=gc.log:uptime,level,tags -jar application.jar
~~~

Lệnh minh họa với tên JAR của ứng dụng. Trên HotSpot, log ghi sự kiện mang tag **gc** hoặc **safepoint** vào file, với JVM uptime, level và tags. Chọn mức chi tiết cao hơn chỉ khi cần, xác nhận dung lượng/rotation và nhớ rằng **logging cũng tạo overhead**.

Với một tiến trình đang chạy, có thể xem lệnh được JVM đích hỗ trợ trước khi dùng:

~~~bash
jcmd 12345 help
jcmd 12345 help GC.heap_info
jcmd 12345 help JFR.start
jcmd 12345 VM.version
~~~

**12345 chỉ là PID minh họa**, phải thay bằng PID thực. Tập command, quyền attach và công cụ có sẵn phụ thuộc VM/JDK/container. Chỉ bật recording khi đã hiểu thời gian thu, dung lượng file, quyền và mức tác động. Với JFR, phân biệt **event duration**, **sampling event** và **counter**: không phải event nào cũng kể lại toàn bộ mọi lần chạy.

## 5. Sai lệch do lấy mẫu: đo nhiều chưa chắc đo đúng

### 5.1. Phân biệt mẫu và tổng thể

**Sampling** tiết kiệm tài nguyên bằng cách chỉ quan sát một phần sự kiện, request, thời điểm hoặc stack. Nhưng mẫu có thể không đại diện:

- **Periodic aliasing:** lấy mẫu mỗi 1 giây có thể luôn rơi vào pha rảnh hoặc pha bận của một chu kỳ 1 giây.
- **Selection bias:** chỉ ghi request hoàn tất thành công, bỏ timeout, fail-fast và request bị từ chối; số liệu về latency có thể đẹp giả tạo.
- **Survivorship bias:** chỉ xem JVM còn sống, bỏ những process đã crash/OOM hoặc restart trước khi snapshot.
- **Threshold bias:** profiler/event JFR chỉ ghi những sự kiện thỏa điều kiện duration/size; sự kiện “không có” có thể nghĩa là chưa vượt ngưỡng hoặc event chưa được bật.
- **Nonuniform sampling:** mẫu chỉ từ một thread, instance, AZ, route hoặc khoảng tải; ghép lại không trọng số làm lệch đại diện.
- **Burst masking:** lấy trung bình theo phút che mất spike vài trăm mili giây, dù spike đủ ảnh hưởng người dùng.

Lấy mẫu CPU stack **khác** lấy mẫu độ trễ của request. Stack sampling cho biết code xuất hiện trong các mẫu theo chính sách profiler; tần suất xuất hiện không trực tiếp là phần trăm thời gian một request end-to-end dùng ở method đó. Các cách lấy mẫu phụ thuộc safepoint hoặc thread state có thể làm stack collection bị thiên lệch; phải hiểu profiler đang dùng cơ chế nào.

### 5.2. Ví dụ Java 21 chạy được: lấy mẫu trùng chu kỳ

Giả sử có **100 request**. Cứ request số 10, 20, 30, … lại có latency **100 ms**; 90 request còn lại **10 ms**. Phân phối thực có **mean = 19 ms**, **p50 = 10 ms**, **p95 = 100 ms** (nearest-rank). Nếu chỉ lấy mỗi request thứ 10, kết quả phụ thuộc hoàn toàn **pha bắt đầu**.

**Tệp SamplingAliasDemo.java**

~~~java
import java.util.Arrays;

public class SamplingAliasDemo {
    private static int latencyMs(int requestNumber) {
        return requestNumber % 10 == 0 ? 100 : 10;
    }

    private static int sampleMean(int firstRequest) {
        int total = 0;
        int count = 0;
        for (int request = firstRequest; request <= 100; request += 10) {
            total += latencyMs(request);
            count++;
        }
        return total / count;
    }

    private static int percentileNearestRank(double percentile) {
        int[] values = new int[100];
        for (int request = 1; request <= 100; request++) {
            values[request - 1] = latencyMs(request);
        }
        Arrays.sort(values);
        int index = (int) Math.ceil(percentile * values.length) - 1;
        return values[index];
    }

    public static void main(String[] args) {
        System.out.println("True mean: 19 ms");
        System.out.println("True p50: " + percentileNearestRank(0.50) + " ms");
        System.out.println("True p95: " + percentileNearestRank(0.95) + " ms");
        System.out.println("Sample 5,15,... mean: " + sampleMean(5) + " ms");
        System.out.println("Sample 10,20,... mean: " + sampleMean(10) + " ms");
    }
}
~~~

~~~bash
javac --release 21 SamplingAliasDemo.java
java SamplingAliasDemo
~~~

**stdout chính xác:**

~~~text
True mean: 19 ms
True p50: 10 ms
True p95: 100 ms
Sample 5,15,... mean: 10 ms
Sample 10,20,... mean: 100 ms
~~~

Trong ví dụ này, dòng mean được in theo số đã tính bằng tay: **(90 × 10 + 10 × 100) / 100 = 19**. Hai nhóm sample đều có 10 request nhưng cho hai kết luận trái ngược. Đây là ví dụ mô phỏng xác định, **không phải mô phỏng cách JFR lấy stack**. Bài học là phải kiểm tra **cách chọn mẫu và pha lấy mẫu**, không chỉ đếm số mẫu.

Cải thiện bằng cách đổi pha/chọn thời điểm một cách phù hợp, thu thập đủ các phân đoạn, kết hợp event-based metrics và không loại bỏ thất bại; nếu lấy mẫu không đều, dùng trọng số đúng theo xác suất chọn mẫu thay vì lấy trung bình thô.

### 5.3. Percentile, sample size và coordinated omission

- **p99** là percentile của **phân phối các latency quan sát được**, không thể tính bằng cách lấy trung bình p99 của nhiều JVM, thread hoặc từng phút. Muốn p99 toàn cục cần dữ liệu phân phối gộp hoặc một cấu trúc histogram có thể merge đúng cách.
- Với **100 request**, p99 nearest-rank chỉ là một trong những giá trị lớn nhất; sự bất định ở tail cao. Cần báo số lượng mẫu, số request bị lỗi/timeout, và khoảng thời gian đo.
- **Coordinated omission** xảy ra trong một số load generator **closed-loop**: client đợi request trước hoàn thành rồi mới gửi request tiếp, nên trong lúc hệ thống đình trệ, những request đáng lẽ đến theo lịch không xuất hiện trong dataset. Latency báo cáo có thể thấp hơn trải nghiệm dưới tải **open-loop** có lịch đến độc lập. Để đánh giá khả năng đáp ứng với một tốc độ đến dự kiến, theo dõi **scheduled arrival time**, thời gian chờ hàng đợi và timeout; chọn load generator/kiểu tải theo mục tiêu, đừng tùy tiện “bù” số liệu không có căn cứ.
- Sampling profiler có thể bỏ sót spike rất ngắn do sampling interval hoặc policy; giảm interval có thể tăng cơ hội thấy spike nhưng cũng tăng overhead. Đừng giải thích “không có sample” là “không có hành vi”.

## 6. Sai lệch do chính công cụ quan sát: observer effect

Chẩn đoán không phải hoạt động vô hình. Thêm instrumentation có thể làm tăng công việc, allocation, sync, I/O, volume của sự kiện và thay đổi điểm tối ưu của JIT.

| Công cụ/cách đo | Nguồn tác động có thể có | Cách hạn chế hoặc kiểm chứng |
| --- | --- | --- |
| **System.nanoTime() quanh một batch** | Chi phí đọc đồng hồ, thời điểm bắt đầu/kết thúc, scheduler | Đo đủ công việc mỗi batch và so sánh overhead khi thay granularity; không đo mỗi phép toán cực nhỏ bằng timer riêng rồi tin tuyệt đối. |
| **Logging mỗi iteration/request** | Format string, allocation, lock, I/O, flush, backpressure | Chỉ ghi ngoài vùng hot path khi có thể; tách cấu hình logging; đo A/A với và không có log. |
| **JMX/metrics scraping** | Getter/counter, lock, serialization, network, tần suất polling | Chọn interval và độ chi tiết hợp lý, theo dõi chi phí exporter; không polling quá mức. |
| **JFR** | Ghi event/buffer/stack, overhead theo cấu hình, duration threshold | Bắt đầu bằng event/template phù hợp, recording có thời hạn, kiểm tra overhead và event loss. |
| **Sampling profiler** | Signals/timer/stack walking/agent; cơ chế phụ thuộc profiler | Ghi tần suất sampling, loại stack, số sample mất; so sánh baseline tương đương. |
| **Thread dump** | Thu stack/lock, có thể ảnh hưởng tiến trình; tăng theo số thread | Thu đúng lúc cần, đánh dấu timestamp; đừng chụp dồn dập để “tăng độ chắc”. |
| **Heap dump / class histogram** | Tác động lớn, pause và I/O, file có thể rất lớn | Chỉ dùng khi điều tra heap yêu cầu; ghi rõ thời điểm để không nhầm dump-induced pause với sự cố gốc. |
| **Agent, bytecode instrumentation** | Thêm branch/method, context propagation, allocation, class transformation | Kiểm tra ảnh hưởng với workload tương đương; phân biệt agent nạp lúc khởi động và agent động. |

Nếu biến thể **A** không bật profiler và **B** bật profiler, thấy p99 B cao hơn chỉ gợi ý **có thể** có overhead. Cần giữ request rate, phần cứng, dữ liệu, process state, GC và thời gian tương đương; thử **A/A** hoặc **A–B–B–A**/nhiều lượt có đổi thứ tự, rồi mới quy kết.

**Đừng nghĩ công cụ tác động chỉ theo một hướng.** Instrumentation đôi khi làm tăng thời gian, nhưng cũng có thể đổi lịch thread, mức nóng của code, nhịp GC và thời điểm tranh chấp, khiến một số lần đo *nhanh hơn* hoặc khiến lỗi hiếm biến mất. Vì thế đo overhead đơn thuần bằng “lấy số bật công cụ trừ số tắt công cụ” chỉ là ước lượng dưới điều kiện kiểm soát, không phải hằng số để cộng/trừ khỏi mọi request.

## 7. Ví dụ Java 21: thấy sự trôi của các batch nhưng không vội gán nguyên nhân

Ví dụ hoàn chỉnh sau ghi elapsed time theo **System.nanoTime()** và chênh lệch số lượt collection từ MXBean nếu được hỗ trợ. Nó tạo công việc phụ thuộc vào input để compiler không thể đơn giản bỏ toàn bộ kết quả, nhưng **không phải JMH benchmark** và không chứng minh chênh lệch quan sát là do riêng JIT hoặc GC.

**Tệp MeasurementPhases.java**

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Locale;

public class MeasurementPhases {
    private static volatile long published;

    private static long work(int seed) {
        long value = seed | 1L;
        for (int i = 0; i < 3_000; i++) {
            value = Long.rotateLeft(
                    value + 0x9E3779B97F4A7C15L + i, 9)
                    ^ (value >>> 11);
        }
        return value;
    }

    private static long totalCollections() {
        long count = 0;
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long current = bean.getCollectionCount();
            if (current < 0) {
                return -1;
            }
            count += current;
        }
        return count;
    }

    private static void runBatch(String label, int seedOffset) {
        long beforeGc = totalCollections();
        long start = System.nanoTime();

        long checksum = 0;
        for (int i = 0; i < 1_000; i++) {
            checksum ^= work(seedOffset + i);
        }

        long elapsedNanos = System.nanoTime() - start;
        long afterGc = totalCollections();
        published ^= checksum;

        String gcDelta = beforeGc >= 0 && afterGc >= 0
                ? Long.toString(afterGc - beforeGc)
                : "unknown";
        System.out.printf(Locale.ROOT,
                "%s: %.3f ms, GC count delta=%s%n",
                label, elapsedNanos / 1_000_000.0, gcDelta);
    }

    public static void main(String[] args) {
        runBatch("first", 1);
        for (int i = 0; i < 8; i++) {
            runBatch("warmup-" + (i + 1), 1_001 + i * 1_000);
        }
        runBatch("measurement-1", 20_001);
        runBatch("measurement-2", 21_001);
        System.out.println("Published checksum: " + published);
    }
}
~~~

~~~bash
javac --release 21 MeasurementPhases.java
java MeasurementPhases
~~~

**Cách đọc kết quả:** chương trình luôn in nhãn **first**, **warmup-1** đến **warmup-8**, **measurement-1**, **measurement-2**, rồi **Published checksum** theo thứ tự. **Không có stdout số thời gian cố định** vì nanos, GC count và hoạt động compiler phụ thuộc máy/JVM/tải. **GC count delta=0** chỉ có nghĩa là bộ đếm được đọc không tăng trong khoảng đó; nó không chứng minh JVM không có hoạt động GC đồng thời hoặc không có tác động runtime. **GC count delta=unknown** nghĩa là ít nhất một collector không công bố counter.

Mặc dù kết quả được đưa vào biến **volatile** để tránh hoàn toàn không sử dụng, điều này **chưa đủ** để loại trừ mọi tối ưu hóa, scheduler noise, CPU frequency, safepoint, cache hay chênh lệch input. Tám batch warmup chỉ phục vụ minh họa, **không bảo đảm steady state**. Nếu muốn so sánh hiệu năng của chính hàm **work**, hãy chuyển nó thành benchmark JMH với dữ liệu và fork được kiểm soát.

Để đối chiếu hoạt động GC của ví dụ trên HotSpot/JDK 21, bạn có thể chạy riêng một lần với logging:

~~~bash
java -Xlog:gc,safepoint:file=measurement-gc.log:uptime,level,tags MeasurementPhases
~~~

Đây là **một lượt khác**: việc bật logging và tạo file là một biến quan sát. Không tự so sánh thời gian giữa hai lệnh như một thí nghiệm nguyên nhân nếu chưa lặp, đổi thứ tự, kiểm soát trạng thái và đánh giá overhead.

## 8. Kịch bản chẩn đoán: p99 tăng sau deploy

Giả định một service Java 21 trên HotSpot có p99 latency tăng từ **80 ms** lên **230 ms** sau deploy. Đây là dữ kiện **giả định để luyện phân tích**, chưa xác nhận nguyên nhân. Một quy trình hợp lý:

**Bước 1 — Xác nhận dữ liệu và phạm vi.** Kiểm tra p99 tính từ cùng điểm đo, cùng route/tải/concurrency, bao gồm timeout và các request lỗi phù hợp. Đối chiếu số request ở p99, thời gian warmup, nền tảng triển khai, CPU quota và JDK runtime đang chạy. Nếu bản mới được đo ngay sau khởi động, bản cũ đo sau 30 phút, chưa thể so sánh trực tiếp.

**Bước 2 — Nhìn timeline thay vì một số cuối.** Vẽ latency p50/p95/p99, throughput, CPU và request queue theo thời gian. Nếu chỉ 2 phút đầu xấu rồi hồi phục, ưu tiên giả thuyết startup/cache/JIT. Nếu tail tăng theo chu kỳ, đặt câu hỏi về GC, batch jobs, lock và sampling alias. Nếu toàn bộ giai đoạn xấu, xét workload, cấu hình và regression code thực sự.

**Bước 3 — Tìm tín hiệu runtime tương quan.** Dùng nguồn nhẹ nhất có sẵn: JMX/metrics, GC/safepoint log, JFR có giới hạn, request tracing. Với JDK 21 HotSpot, xác minh quyền và danh sách **jcmd PID help** trước khi dùng lệnh. Nếu cùng lúc GC pause tăng, kiểm tra request có overlap pause và allocation/live set có thay đổi không. Nếu compiler activity tăng vào đầu phiên, kiểm tra biến động có giảm sau warmup không.

**Bước 4 — Loại tác động công cụ.** Nếu chỉ bản mới bật debug log/agent/profiler, thực hiện lượt đối chứng với cấu hình tương đương. Không kết luận nguyên nhân từ một biểu đồ có observer configuration khác nhau.

**Bước 5 — Lặp lại để kiểm chứng.** Chạy nhiều lượt A/B trên điều kiện tương đồng, ngẫu nhiên hoặc đảo thứ tự hợp lý, tách startup và steady-state, ghi cả phân phối cùng số sample. Chỉ sau đó đưa ra kết luận, mức tin cậy và việc cần sửa.

Ví dụ các kết luận **có chứng cứ** khác nhau:

| Quan sát đã kiểm chứng | Giả thuyết được củng cố | Điều chưa thể kết luận |
| --- | --- | --- |
| Chậm chủ yếu ở 90 giây đầu; sau đó ổn định | Warmup, class initialization, cache hoặc compiler activity | Không đủ căn cứ nói hoàn toàn do JIT. |
| Các spike request overlap pause GC và tăng cùng allocation | GC có khả năng góp phần vào tail latency | Không thể quy 100% thời gian spike cho GC. |
| Mỗi chu kỳ 10 giây có đỉnh, mẫu cố định theo chu kỳ luôn bỏ qua | Sampling bị aliasing với chu kỳ tải | Chưa biết chính xác phân phối thực nếu chưa bổ sung mẫu. |
| Chậm chỉ khi bật logging chi tiết, A/A lặp lại cùng workload cũng chậm | Overhead quan sát là một thành phần đáng kể | Chưa biết overhead cố định cho mọi request. |
| Chậm ở mọi pha sau khi giữ môi trường và thu thập tương đương | Có khả năng thay đổi đường code, I/O, contention hoặc cấu hình | Không đủ căn cứ loại JIT/GC nếu chưa xem telemetry. |

## 9. Quy trình đo ít sai lệch, có thể lặp lại

### 9.1. Trước khi thu thập

1. **Viết câu hỏi đo**: cold-start readiness, time/op của thuật toán, CPU, throughput dưới tải hay p99 end-to-end? Không thể dùng một biểu đồ trả lời tất cả.
2. **Giữ đơn vị công việc rõ ràng**: request route, payload size, tỷ lệ read/write, số client, tốc độ đến, trạng thái cache, tỉ lệ lỗi, timeout, retry và concurrency.
3. **Ghi môi trường**: Java full version, VM name/vendor, GC, JVM flags/heap, CPU/core quota, RAM/container, build, OS, network, tool versions, timezone và clock source.
4. **Chọn chế độ**: các lượt cold start độc lập, hoặc warmup + steady-state; nếu cần cả hai thì báo riêng.
5. **Định nghĩa cách lấy mẫu**: tất cả requests hay sampling? Sample rate, sampling frame, duration, event threshold, missing/lost samples và chính sách xử lý timeout.
6. **Ước lượng observer cost**: công cụ nào bắt buộc trong production, công cụ nào chỉ bật tạm, tác động có thể chấp nhận.

### 9.2. Trong lượt đo

- Đo bằng **System.nanoTime()** cho elapsed duration trong JVM; với hệ thống phân tán, đánh dấu wall-clock timestamp ở mỗi service và xử lý chênh lệch clock.
- Tách các cửa sổ **startup → warmup → measurement** theo mốc rõ ràng. Đừng bỏ dữ liệu lúc chuyển pha nếu đó chính là vấn đề người dùng gặp.
- Ghi request rate, concurrency, queue depth, CPU, GC và error rate **cùng mốc thời gian** với latency. Dữ liệu không đồng bộ thời gian có thể tạo quan hệ nhân quả giả.
- Dùng mức chi tiết tối thiểu để trả lời câu hỏi; tăng dần từ metric/JMX sang JFR/log hoặc dump khi thực sự có lý do.
- Không đổi heap, GC, logging level, profiler interval hoặc workload giữa hai phép đo được gọi là “cùng điều kiện” mà không ghi nhận sự thay đổi.
- Khi phát hiện **GC, safepoint, compiler activity hoặc profiler sampling loss**, chú thích lên timeline thay vì tự động xóa cả khoảng đó khỏi thống kê.

### 9.3. Sau lượt đo

- Báo **số lần chạy độc lập (fork/process)**, số samples trong từng lần, trung vị giữa các lần, độ phân tán và phân phối request latency; thêm khoảng tin cậy nếu phương pháp và số lượt thực sự hỗ trợ.
- Đối chiếu p50/p95/p99 theo từng khoảng thời gian hoặc load level. Không gộp percentile bằng phép trung bình số học; gộp raw data/histogram phù hợp khi muốn một percentile chung.
- Giữ các phép đo **A/A** để ước lượng biến động tự nhiên, sau đó đánh giá hiệu ứng A/B có lớn hơn nhiễu đó và lặp lại nhất quán không.
- Lưu đầu vào, cấu hình, command, baseline và evidence (file JFR, GC logs, metrics). Với container, ghi rõ đường dẫn **trong container** hay **trên host**.
- Ghi một kết luận phân biệt: **quan sát**, **giả thuyết**, **bằng chứng**, **giải thích cạnh tranh**, **mức chắc chắn** và **bước xác minh tiếp**.

### 9.4. Một bảng dữ liệu tối thiểu cho mỗi lượt

| Trường | Vì sao cần |
| --- | --- |
| **Run ID / build / commit** | Liên hệ kết quả với mã thực tế. |
| **Java full version / VM / vendor / flags** | Giải thích khác biệt JIT/GC/công cụ giữa runtime. |
| **Host/container CPU quota, RAM, OS** | Kiểm soát scheduler, throttling và tài nguyên. |
| **Cold/warmup/measurement timestamps** | Tránh trộn giai đoạn, xác định sự kiện trên timeline. |
| **Payload, rate, concurrency, route, cache state** | Bảo đảm đo cùng loại công việc. |
| **Sample policy, sample count, failures/timeouts** | Biết mẫu đại diện cho tổng thể nào và còn mất gì. |
| **p50/p95/p99, throughput, CPU, allocation, GC/safepoint events** | Đối chiếu triệu chứng và nguồn gây nhiễu. |
| **Profiler/JFR/logging config, overhead comparison** | Đánh giá tác động của chính cách quan sát. |

## 10. Bản đồ phân biệt triệu chứng và nguyên nhân

| Dấu hiệu | Giả thuyết nên kiểm tra | Câu hỏi phân biệt |
| --- | --- | --- |
| Lần gọi đầu chậm, sau đó nhanh | Class init, cache, tiered JIT, I/O ban đầu | Mỗi **process mới** đều lặp lại hay chỉ lần đầu của **một method**? |
| Sau vài phút tự chậm lại rồi nhanh | Deoptimization, recompile, GC, CPU throttling, contention | Có compiler/GC/CPU/queue event đồng thời không? |
| p99 tăng nhưng p50 gần giữ nguyên | GC pause, lock convoy, queue spike, outlier network | Tail có overlap với pause/queue/lock; mẫu đủ chưa? |
| CPU cao nhưng throughput không tăng | Spin, GC đồng thời, contention, compiler, quá tải | CPU thuộc application threads, GC hay compiler; đã đụng CPU quota chưa? |
| Heap tăng rồi giảm theo chu kỳ | Nhịp allocation/GC bình thường hoặc bất thường | Live set sau GC có tăng lâu dài không; tần suất pause ra sao? |
| Profiler báo “không thấy” một method | Method rất ngắn, sample rate thấp, tối ưu JIT, sampling bias | Công cụ sample CPU hay wall; threshold và stack policy là gì? |
| Bật debug logging thì lỗi chậm biến mất | Observer effect thay đổi concurrency/timing | A/A có tái hiện khi đổi thứ tự, giữ workload không? |
| Load test báo p99 tốt dù server bị khựng | Coordinated omission, timeout bị loại, client queue không tính | Request arrival theo lịch độc lập hay client đợi response mới gửi? |

Không coi bảng là công cụ chẩn đoán tự động. Các triệu chứng có thể có **nhiều nguyên nhân đồng thời**. Luôn đối chiếu timestamp và đủ phạm vi đo.

## 11. Những lỗi thường gặp

1. **“Bỏ 10 lần chạy đầu là đã warmup.”** Không có ngưỡng vạn năng; compiler và dữ liệu ứng dụng có thể tiếp tục đổi sau đó.
2. **“Batch sau nhanh hơn, chắc chắn JIT đã tối ưu.”** Chưa loại cache, GC, OS scheduling, CPU frequency hoặc phép đo biến dạng.
3. **“Không có GC count tăng nên mọi latency spike đều không liên quan GC.”** Counter có phạm vi và độ trễ cập nhật; concurrent GC/safepoint hoặc time windows khác vẫn cần xem.
4. **“Thời gian GC bằng tổng thời gian request bị chậm.”** Pause time không tự cộng tuyến tính vào mọi request và có thể chồng lấn các hoạt động.
5. **“Một thread dump đúng lúc là mẫu đại diện.”** Nó là một snapshot tại một thời điểm, chịu tác động của cách lấy và không mô tả tần suất hành vi cả phiên.
6. **“p99 của 100 request đủ so sánh hai bản build.”** Tail thiếu tính ổn định với mẫu ít; cần xem sample count và lặp lại.
7. **“Trung bình p99 mỗi instance là p99 toàn hệ thống.”** Sai về thống kê; phải gộp dữ liệu gốc/histogram tương thích.
8. **“Profiler là người quan sát trung lập.”** Bật profiler/logging/agent có thể đổi đường thực thi và thời gian.
9. **“Càng logging chi tiết, kết quả càng chính xác.”** Dữ liệu nhiều hơn có thể đồng thời gây overhead lớn hơn, mất event hoặc nghẽn I/O.
10. **“Không thấy spike trong sampled data nghĩa là không có spike.”** Sample policy, phase, event threshold và sample loss quyết định khả năng phát hiện.
11. **“JMH đo nhanh hơn thì người dùng chắc chắn nhanh hơn.”** Microbenchmark không thay thế latency end-to-end dưới tải, queueing và I/O.
12. **“Kết quả production và laptop khác nhau chỉ do phần cứng.”** JDK vendor/flags, GC, container quota, workload và observer configuration cũng khác.

## 12. Tự kiểm tra và bài tập áp dụng

**Câu 1.** Một lần cold start mất 2,5 giây, sau đó API ổn định 40 ms/request. Bạn báo một chỉ số hay hai? **Gợi ý:** ít nhất báo startup readiness và steady-state request latency riêng, vì chúng có mốc và mục tiêu khác nhau.

**Câu 2.** Khi bật JFR, p99 tăng 12%. Có thể kết luận JFR gây đúng 12% overhead không? **Gợi ý:** chưa; cần A/A, nhiều lượt tương đương, xét biến động tải, event settings, profiling overhead và mối liên hệ nhân quả.

**Câu 3.** Một API có latency trung bình 12 ms, p99 500 ms. Nên nghi ngờ điều gì trước? **Gợi ý:** kiểm tra phân phối, số mẫu, lỗi/timeout, request queue, GC/safepoint timeline và tail events; không thay p99 bằng average.

**Câu 4.** JIT activity và GC pause xuất hiện cùng lúc một request chậm. Làm sao kết luận? **Gợi ý:** chỉ từ sự trùng thời gian chưa đủ; đo overlap, loại các giả thuyết cạnh tranh, lặp lại và ghi độ chắc chắn thay vì gắn duy nhất một nhãn.

**Câu 5.** Test client đợi response rồi mới gửi request mới; trong đợt server treo 10 giây, thống kê có ít request latency cao. **Gợi ý:** kiểm tra coordinated omission và thời điểm request được lên lịch đến. Client có thể ngừng tạo tải trong lúc service tắc.

## Tài liệu tham khảo chính

- [Java SE 21 — System.nanoTime và đồng hồ elapsed time](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime())
- [Java SE 21 — GarbageCollectorMXBean và giới hạn bộ đếm](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [JDK 21 — jcmd và tác động của từng diagnostic command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK 21 — lệnh java và Unified Logging (-Xlog)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [OpenJDK JMH — hướng dẫn benchmark và mẫu chính thức](https://github.com/openjdk/jmh)
- [JDK 21 — Java Flight Recorder và công cụ chẩn đoán](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)

**Kết quả mong đợi của một phép đo đáng tin:** bạn có thể nói **đo cái gì, trên tập nào, ở giai đoạn nào, bằng cách lấy mẫu nào, đã bật công cụ gì, công cụ có làm thay đổi hệ thống không, và bằng chứng nào giúp phân biệt JIT/GC/tải/quan sát**. Nếu chưa trả lời được, chưa nên coi chênh lệch số đo là regression hoặc cải thiện hiệu năng đã được xác minh.
