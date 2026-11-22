# 11.8 Phân biệt heap tăng do tải, giữ dữ liệu hợp lệ và giữ tham chiếu ngoài ý muốn

## Mục tiêu học tập

Khi thấy Java heap tăng, cần trả lời ba câu hỏi khác nhau: **ứng dụng đang tạo nhiều đối tượng hơn do tải tăng**, **ứng dụng đang giữ dữ liệu còn cần dùng**, hay **một tham chiếu tồn tại quá lâu đang giữ lại dữ liệu lẽ ra phải được giải phóng**? Cả ba trường hợp đều có thể làm biểu đồ heap đi lên; không thể kết luận “memory leak” chỉ từ một đỉnh sử dụng bộ nhớ.

Sau bài này, bạn có thể đọc biểu đồ heap/GC theo vòng đời tải, thiết kế phép đo có đối chứng, phân tích chuỗi tham chiếu tới GC roots, và chọn cách khắc phục đúng bản chất của từng trường hợp.

## 1. Hiểu chính xác điều đang tăng

Java heap là vùng JVM quản lý để cấp phát phần lớn đối tượng và mảng. GC thu hồi **đối tượng không còn reachable từ các GC roots** (chẳng hạn tham chiếu từ stack của luồng còn sống, trường `static`, hoặc cấu trúc nội bộ JVM). Một đối tượng “không còn hữu ích về nghiệp vụ” vẫn **không được thu hồi** nếu còn một đường tham chiếu mạnh tới nó.

Phân biệt các đại lượng thường bị trộn lẫn:

| Chỉ số | Ý nghĩa | Điều không thể kết luận |
| --- | --- | --- |
| `heap used` tại một thời điểm | Dung lượng heap đang chứa đối tượng, bao gồm cả rác chưa được thu gom | Không đồng nghĩa toàn bộ là dữ liệu còn sống; một giá trị cao không tự chứng minh leak |
| `heap used` sau những pha GC **có thể so sánh** | Xấp xỉ tập dữ liệu còn sống sau lần thu gom tương ứng | Một lần GC trẻ (`young GC`) có thể không thu hết rác ở vùng già; không so tùy tiện với sau `mixed/full GC` |
| `heap committed` | Dung lượng JVM đã cam kết từ hệ điều hành cho heap | Không đồng nghĩa số byte đối tượng đang cần; JVM có thể giữ vùng đã commit sau khi tải giảm |
| `heap max`/`-Xmx` | Giới hạn heap cho phép | Không cho biết nguyên nhân tăng sử dụng |
| `allocation rate` | Tốc độ cấp phát đối tượng mới | Cao có thể gây GC dày nhưng không nhất thiết tăng dữ liệu giữ lâu |
| `process RSS` | Bộ nhớ vật lý tiến trình đang sử dụng | Bao gồm heap và nhiều vùng ngoài heap; RSS tăng không mặc nhiên là heap leak |

**Hai động lực cốt lõi** là *allocation* (cấp phát mới) và *retention* (giữ các đối tượng reachable). Một dịch vụ có thể cấp phát hàng GB mỗi phút và vẫn ổn định nếu các đối tượng chết nhanh, trong khi một cấu trúc giữ thêm ít KB ở mỗi request có thể khiến live set tăng không giới hạn qua thời gian.

Hình dung sử dụng heap trước GC thường tạo đường “răng cưa”: allocation đẩy used lên, GC kéo xuống. **Điểm đáy và xu hướng sau các lần GC tương đương**, kết hợp với tải và số lượng dữ liệu thực sự cần giữ, có ích hơn một ảnh chụp đỉnh răng cưa. Với collector đồng thời hoặc theo thế hệ, việc chọn đúng loại sự kiện GC và cùng giai đoạn hoạt động là bắt buộc.

## 2. Ba cơ chế khác nhau

| Dấu hiệu cần đối chiếu | Heap tăng do tải | Giữ dữ liệu hợp lệ | Giữ tham chiếu ngoài ý muốn |
| --- | --- | --- | --- |
| Nguồn tăng | Request/tác vụ đồng thời, buffer và đối tượng tạm | Cache, session, trạng thái phiên, index, dữ liệu đang được xử lý | Map/list không dọn, listener không hủy đăng ký, `ThreadLocal`, hàng đợi hoặc callback giữ đối tượng |
| Quan hệ với tải | Thường tăng cùng lưu lượng, concurrency hoặc kích thước batch | Tăng cùng số đối tượng nghiệp vụ cần phục vụ; có thể tăng khi “làm nóng” cache | Có thể tiếp tục tăng qua các chu kỳ cùng tải hoặc sau khi tác vụ đã kết thúc |
| Sau khi tải hạ và đủ thời gian thu gom | Dữ liệu tạm thường giảm về vùng nền tương đương | Vẫn còn phần dữ liệu có chủ đích; thường đạt plateau theo chính sách | Live set có xu hướng tăng qua các chu kỳ và không giảm như vòng đời mong đợi |
| Heap dump | Nhiều đối tượng gắn với công việc đang chạy | Đường tham chiếu từ các owner hợp lệ, khớp số lượng/TTL/giới hạn | Đường giữ từ owner sống lâu tới đối tượng hết hạn nghiệp vụ |
| Hướng xử lý | Giới hạn đồng thời/batch, giảm allocation, backpressure, điều chỉnh capacity | Định nghĩa ngân sách, TTL, eviction, thời điểm giải phóng theo nghiệp vụ | Xóa đường tham chiếu sai, cleanup theo lifecycle, giới hạn cấu trúc giữ dữ liệu |

### 2.1. Tăng do tải: có nhiều việc đang hoạt động

Ví dụ, lưu lượng tăng từ 100 lên 1.000 request/giây; mỗi request cần parse JSON, giữ byte buffer và tạo DTO trong một thời gian ngắn. Heap used tăng giữa các lần GC; allocation rate và GC frequency cũng có thể tăng. Khi giảm tải về 100 request/giây, số request đang xử lý và dữ liệu tạm dần giảm. Đây là phản ứng hợp lý của một workload thay đổi.

Nhưng **“do tải” không có nghĩa “không có vấn đề”**: lượng công việc đồng thời quá lớn, batch khổng lồ hoặc hàng đợi không giới hạn vẫn có thể làm `OutOfMemoryError`. Tối ưu là giới hạn in-flight request, chunk batch, đặt max queue, streaming/backpressure, hoặc tăng `-Xmx` sau khi chứng minh nhu cầu thật; không mặc định kết luận lỗi GC.

Một request đã trả response nhưng task bất đồng bộ của nó vẫn đang chạy thì dữ liệu liên quan có thể còn được giữ hợp lệ. Do đó phải đo *active work* (số request đang xử lý, task và queue depth), không chỉ số HTTP request/giây.

### 2.2. Giữ dữ liệu hợp lệ: bộ nhớ phục vụ mục đích rõ ràng

Cache có thể tăng từ 0 lên vài trăm MB trong giai đoạn warm-up rồi ổn định khi đạt số entry tối đa; session còn hạn, index tìm kiếm hoặc dữ liệu đang nằm trong cửa sổ tính toán cũng vậy. Dù live set cao sau GC, các đối tượng vẫn có owner và lý do tồn tại.

Chỉ được gọi là **giữ hợp lệ** sau khi chứng minh được: (1) mỗi dữ liệu gắn với nhu cầu nghiệp vụ còn hiệu lực; (2) có quy tắc kết thúc vòng đời; (3) có giới hạn bộ nhớ/số entry hoặc phép tính capacity rõ ràng; (4) quan sát thực tế đạt một plateau trong workload đã xác định. Cache không TTL, không maximum size, hoặc key có cardinality không bị chặn có thể bắt đầu là thiết kế hợp lệ nhưng trở thành **logical memory leak/capacity bug** theo thời gian.

Cần phân biệt:
- `used` sau GC cao nhưng ổn định với cache hit rate tốt và số entry đúng ngân sách: có thể chấp nhận.
- Cache tăng không giới hạn cùng số key duy nhất dù traffic ổn định: giữ dữ liệu theo chủ đích nhưng **chính sách retention sai**.
- Cache bị evict nhưng heap committed/RSS không giảm tức thì: không phải bằng chứng object vẫn được tham chiếu.

### 2.3. Giữ tham chiếu ngoài ý muốn: vòng đời tham chiếu dài hơn vòng đời dữ liệu

Trong Java, “memory leak” thường là **đối tượng đã hết ích lợi nhưng vẫn reachable**, chứ không phải bộ cấp phát quên giải phóng như một số lỗi quản lý bộ nhớ thủ công. Các nguồn điển hình:

- `static Map` hoặc singleton lưu kết quả theo request/user ID, không xóa; số key tăng liên tục.
- Listener/observer được đăng ký nhưng không unregister, khiến publisher sống lâu giữ subscriber và toàn bộ đồ thị mà subscriber tham chiếu.
- `ThreadLocal` không `remove()` trong thread pool: giá trị có thể ở lại trong thread sống lâu giữa nhiều request.
- Hàng đợi, cache hoặc danh sách retry không giới hạn; `Future`/callback giữ context và payload sau thời điểm đáng ra phải giải quyết.
- Class loader còn được thread, registry, driver hoặc static reference giữ sau khi reload module; lớp và đối tượng của loader cũ chưa thể thu gom.

**Không thể xác nhận leak chỉ vì thấy một `HashMap` lớn**. Phải hỏi map có owner nào, mỗi entry có còn cần không, có max/TTL không, số entry và tổng retained bytes biến động thế nào, và khi nghiệp vụ “xong” có đường tham chiếu nào lẽ ra phải biến mất.

## 3. Đọc biểu đồ theo vòng đời workload

Thực hiện quan sát thành các giai đoạn có thể lặp lại thay vì nhìn một đường duy nhất:

1. **Baseline/warm-up:** khởi động, làm nóng JIT, load class, thiết lập connection pool/cache. Đừng lấy đỉnh hoặc điểm đáy đầu tiên làm nền lâu dài.
2. **Tải ổn định A:** giữ request rate, concurrency, kích thước payload và mẫu key gần như cố định; lấy biểu đồ heap used, allocation rate, GC events/pauses, số task hoạt động và số entry quan trọng.
3. **Tăng tải B:** nâng một biến có kiểm soát (ví dụ concurrency), ghi nhận đỉnh heap và hoạt động GC.
4. **Hạ tải và cho xử lý hoàn tất:** xác nhận queue đã drain, session/TTL đủ thời gian hết hạn; so các điểm *sau những sự kiện GC tương đương*, không ép `System.gc()` chỉ để tạo một điểm đẹp.
5. **Lặp tải A:** nếu sau những vòng A giống nhau, live set nền và số owner/entry còn tiếp tục tăng, đặt giả thuyết retention ngoài kỳ vọng rồi kiểm tra heap dump.

Ví dụ định tính:

| Quan sát sau hai vòng cùng tải | Giải thích có khả năng | Bằng chứng còn cần |
| --- | --- | --- |
| Đỉnh used tăng lúc B, trở về nền tương đương khi A trở lại | Đối tượng tạm tăng theo tải | Số active task giảm, allocation/GC tương quan |
| Nền tăng ở warm-up rồi ổn định, cache đạt 5.000/5.000 entry | Giữ dữ liệu hợp lệ có giới hạn | Hit rate, policy eviction, TTL, byte budget |
| Nền sau GC tăng sau mỗi vòng A, map tăng 5.000 → 10.000 → 15.000 key | Nghi ngờ retention ngoài kỳ vọng | Key còn hiệu lực không, path to GC roots, thời điểm cleanup |
| Heap used giảm nhưng committed/RSS gần như đứng yên | JVM giữ dung lượng đã cấp phát | So live objects và non-heap; không suy leak từ RSS |

Đo các điểm *cùng điều kiện* quan trọng hơn một ngưỡng cứng. Ví dụ hai lần used sau GC 400 MB và 600 MB không thể so nếu lần sau có gấp đôi số session hợp lệ. Hãy chuẩn hóa theo số session, entry, kích thước batch và concurrency để đánh giá “byte trên một đơn vị công việc/dữ liệu”.

### Ba câu hỏi kiểm định giả thuyết

- **Allocation tăng?** Quan sát allocation rate, số request và object tạo mỗi request. Nếu tăng mạnh nhưng live set sau GC không tăng dài hạn, ưu tiên giảm churn/GC cost.
- **Retention tăng có lý do?** Đếm entry/session/index, tuổi dữ liệu và cấu hình capacity. Nếu số lượng khớp nhu cầu và có giới hạn/eviction, kiểm thử mức plateau.
- **Đối tượng nào giữ dữ liệu quá hạn?** So heap histogram/dump cùng điều kiện, tìm GC root → owner sống lâu → tập đối tượng, đối chiếu với thời điểm nghiệp vụ phải giải phóng.

## 4. Minh họa Java 17+: cùng là cấp phát mảng nhưng vòng đời khác nhau

Ví dụ độc lập sau cố ý dùng các mảng nhỏ, để quan sát **tham chiếu và số entry** bằng kết quả xác định; đây không phải chương trình benchmark hay phép đo heap chính xác.

```java
// File: HeapGrowthCases.java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public class HeapGrowthCases {
    private static final Map<Integer, byte[]> UNBOUNDED = new HashMap<>();

    private static final Map<Integer, byte[]> BOUNDED =
            new LinkedHashMap<Integer, byte[]>(16, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(
                        Map.Entry<Integer, byte[]> eldest) {
                    return size() > 4;
                }
            };

    public static void main(String[] args) {
        int checksum = 0;
        for (int i = 0; i < 10; i++) {
            byte[] temporary = new byte[1024];
            temporary[0] = (byte) i;
            checksum += temporary[0];

            BOUNDED.put(i, new byte[1024]);
            UNBOUNDED.put(i, new byte[1024]);
        }

        System.out.println("temporary checksum=" + checksum);
        System.out.println("bounded entries=" + BOUNDED.size());
        System.out.println("unbounded entries=" + UNBOUNDED.size());

        UNBOUNDED.clear(); // Mô phỏng cleanup khi dữ liệu đã hết hạn.
        System.out.println("unbounded after cleanup=" + UNBOUNDED.size());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac HeapGrowthCases.java
java HeapGrowthCases
```

Stdout xác định:

```text
temporary checksum=45
bounded entries=4
unbounded entries=10
unbounded after cleanup=0
```

Giải thích từng trường hợp:

1. `temporary` chỉ dùng để cộng checksum trong một lượt lặp; không được đưa vào cấu trúc lưu trữ sống lâu. Sau lần dùng cuối, mảng có thể không còn reachable, nhưng **không bảo đảm GC chạy tức thì**.
2. `BOUNDED` là cache kiểu LRU có tối đa 4 entry nhờ `removeEldestEntry`. Dữ liệu vẫn được giữ hợp lệ nếu 4 entry phục vụ nhu cầu thực tế; giới hạn entry **không thay thế** ngân sách theo byte nếu mỗi value có kích thước biến thiên.
3. `UNBOUNDED` nhận từng key mới và vẫn được trường `static` giữ. Nếu vòng lặp được lặp lại theo request với các key khác nhau mà không cleanup, dữ liệu cũ có thể còn reachable mãi; gọi `clear()` ở thời điểm kết thúc vòng đời làm mất các tham chiếu từ map tới value, cho phép GC thu gom khi không còn owner khác.

Một map `static` không mặc nhiên là lỗi, và `clear()` không phải phương án chung: trong ứng dụng thật, hãy xác định chính sách lifecycle, TTL, eviction hoặc giải phóng theo owner. Sau `clear()`, `heap used` có thể chưa giảm cho đến lần GC phù hợp; `committed` cũng có thể giữ nguyên.

## 5. Bộ công cụ chẩn đoán trên JVM

### 5.1. Thu thập số đo liên tục trước khi lấy snapshot

Ưu tiên biểu đồ theo thời gian với nhãn phiên bản, workload, GC collector và cấu hình heap:

- Heap used/committed/max; nếu có, usage theo generation/region và baseline sau GC phù hợp collector.
- Allocation rate, GC count/time/pause, CPU dành cho GC, p95/p99 latency, throughput.
- Request concurrency, queue depth, batch size, session count, cache size/hit/miss/eviction, số key duy nhất.
- RSS và non-heap để nhận ra vấn đề nằm ngoài Java heap.

Ghi GC log từ lúc khởi động, ví dụ Java 17+:

```bash
java -Xms256m -Xmx1g -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
```

`app.jar` là JAR ứng dụng của bạn; đây là mẫu dòng khởi động, không phải lệnh chạy ví dụ `HeapGrowthCases.java`. Phân tích collector và loại GC thực tế: với G1, một young GC đơn lẻ không chứng minh toàn bộ old generation đã được dọn. GC log giúp ghép timestamp, loại collection và pause với biểu đồ workload; nó không tự chỉ ra owner giữ đối tượng.

### 5.2. `jcmd`: xem tình trạng và lấy bằng chứng có chọn lọc

Tìm PID và xem thông tin heap:

```bash
jcmd -l
jcmd <pid> GC.heap_info
```

Khi cần phân bố loại đối tượng:

```bash
jcmd <pid> GC.class_histogram
```

Histogram cho số object và shallow bytes theo class. Nó giúp phát hiện kiểu đối tượng tăng bất thường, nhưng **không cho biết vì sao object còn reachable**. Một số lệnh GC của `jcmd` có thể gây dừng ứng dụng/GC tốn kém; xem `jcmd <pid> help <command>` đúng JDK đang chạy trước khi dùng trên production. Tùy chọn `-all` ở các lệnh liên quan có thể bao gồm cả object không reachable, làm thay đổi ý nghĩa kết quả.

Có thể ghi Java Flight Recorder trong một cửa sổ quan sát:

```bash
jcmd <pid> JFR.start name=heap-check settings=profile duration=120s filename=heap-check.jfr
```

JFR cho timeline allocation, GC và sự kiện JVM được bật trong cấu hình recording; kiểm tra đúng các event thực sự có trong file. JFR thường hữu ích để tìm vị trí cấp phát và thời điểm tăng áp lực, nhưng **allocation stack trace không tự chứng minh vị trí giữ tham chiếu**.

### 5.3. Heap dump: tìm đường giữ đối tượng

Khi đã có bằng chứng live set tăng ngoài kỳ vọng và có thể chấp nhận chi phí snapshot:

```bash
jcmd <pid> GC.heap_dump heap.hprof
```

Heap dump có thể lớn, gây pause/áp lực disk và chứa dữ liệu nhạy cảm; thu thập tại thời điểm được phép, lưu trữ và xóa theo quy định. Lệnh dump mặc định có thể yêu cầu Full GC, nên đừng so “trước/sau dump” như một thí nghiệm không tác động hệ thống.

Mở `heap.hprof` bằng Eclipse Memory Analyzer (MAT) hoặc công cụ tương đương và đi theo trình tự:

1. Xem **histogram**: class nào có instance/shallow size tăng qua các snapshot cùng điều kiện?
2. Xem **dominator tree** và **retained size**: owner nào đang giữ cả một đồ thị đối tượng? Retained size ước lượng lượng bộ nhớ có thể trở nên thu hồi được nếu loại bỏ owner đó trong đồ thị tham chiếu đang phân tích; khác với shallow size của bản thân owner.
3. Với object đáng nghi, xem **Path to GC Roots**, chú ý có hay không weak/soft references khi diễn giải. Tìm `static field`, thread/`ThreadLocal`, cache singleton, listener, queue hoặc class loader đang giữ nó.
4. So khớp chủ sở hữu với nghiệp vụ: object này có còn session/tác vụ/cache entry hợp lệ không, hay vòng đời thực đã kết thúc?
5. Tìm điểm tạo **và** điểm phải xóa reference trong code. Fix chính sách cleanup ở đúng lifecycle; lặp lại phép đo để chứng minh live set/entry count ổn định.

Nếu chỉ thấy nhiều `byte[]`, `String` hoặc `HashMap$Node`, đừng vội sửa class đó: chúng thường là **payload**, không phải chủ sở hữu. Hãy truy tới owner dominator và đường GC roots. Một heap dump duy nhất hiếm khi chứng minh *xu hướng* leak; histogram so sánh hoặc nhiều snapshot dưới tải tương đương mạnh hơn.

## 6. Quy trình điều tra và quyết định hành động

### Bước 1 — Khoanh đúng loại bộ nhớ

Đối chiếu heap used, committed/max, RSS, metaspace, direct buffer, thread stack. Nếu chỉ RSS tăng còn heap used/live set ổn định, mở nhánh điều tra **native/off-heap memory**; tăng `-Xmx` hoặc tìm Java object leak có thể đi sai hướng.

### Bước 2 — Đặt giả thuyết có thể bác bỏ

Ví dụ:
- H1: “Heap tăng vì concurrent request tăng; khi drain queue, live set quay về mức nền.”
- H2: “Heap tăng vì cache hợp lệ đang warm-up tới giới hạn 5.000 entry, sau đó giữ plateau.”
- H3: “Mỗi request gắn một payload vào singleton mà không xóa; số payload sống sau GC tăng theo tổng request.”

Mỗi giả thuyết phải có chỉ số và thử nghiệm kiểm chứng; không ghi “nghi leak” như kết luận cuối.

### Bước 3 — Giữ cố định các biến gây nhiễu

Ghi chính xác JDK/GC, `-Xms/-Xmx`, phiên bản build, traffic pattern, payload size, unique-key cardinality, cache TTL, số thread, thời gian warm-up. Tăng **một** yếu tố, quan sát đủ lâu, rồi hạ. So kết quả sau cùng loại pha GC và sau khi công việc đã kết thúc.

### Bước 4 — Ghép đồ thị hành vi với số owner

Nếu live set tăng, vẽ đồng thời cache entry count, queue depth, session count và tỉ lệ expired/evicted. Một đường tăng song hành với entry còn hiệu lực là bằng chứng cho retention có lý do; tăng khi entry hết hạn hoặc queue đã trống là tín hiệu cần truy đường tham chiếu.

### Bước 5 — Chọn công cụ sâu theo câu hỏi

- **Allocation quá nhiều?** Dùng JFR allocation profiling, GC logs, profiler để tìm nơi tạo object và giảm churn.
- **Không biết object nào giữ heap?** Heap histogram/dump, dominator tree, GC roots.
- **Cache đúng chức năng nhưng memory không đạt plateau?** Kiểm tra max size, TTL, key cardinality, byte-weight, eviction và policy load.
- **Heap ổn mà tiến trình vẫn lớn?** Đo native/off-heap/mapped memory và thread stack.

### Bước 6 — Sửa đúng cơ chế

| Kết luận đã được kiểm chứng | Thay đổi đúng chỗ | Tiêu chí xác nhận |
| --- | --- | --- |
| Burst/concurrency làm vượt ngân sách tạm thời | Giảm peak in-flight, streaming/chunk, backpressure, tối ưu cấp phát, điều chỉnh sizing sau load test | Thông lượng/latency đạt SLO, dùng heap trở về nền phù hợp, không OOME |
| Cache/session/index hợp lệ nhưng cần capacity | Max entry/weight, TTL, eviction, giới hạn session, thiết kế kích thước state | Plateau được chứng minh với cardinality cao; hit rate và nghiệp vụ vẫn đúng |
| Chủ sở hữu giữ object hết hạn | `remove` theo lifecycle, unregister listener, `ThreadLocal.remove()` trong `finally`, cancel/close resource hợp lý, tránh queue vô hạn | Số object quá hạn không tích lũy; owner path biến mất; live set không còn tăng qua vòng lặp |

### Bước 7 — Xác nhận bằng chạy lại phép thử ban đầu

Chạy cùng tải, cùng duration và các bộ đếm, so baseline trước/sau sửa. Kiểm tra không làm sai session, cache, tính đúng dữ liệu hay throughput. **Tăng `-Xmx` chỉ tăng khoảng đệm**: có thể hợp lý cho working set thực nhưng không loại bỏ retention vô hạn. Ép `System.gc()` hoặc dựa vào restart định kỳ có thể che triệu chứng, không thay thế sửa vòng đời tham chiếu.

## 7. Những ca dễ nhầm

**Ca A — “Heap tăng theo RPS; vậy chắc chắn bình thường?”** Không chắc. Nếu concurrency và queue tăng vì downstream chậm, số task đang giữ payload có thể tích lũy ngay cả khi RPS không còn tăng. Đo cả queue age/depth và thời gian task hoàn tất. Tăng do backlog vẫn có thể gây OOME mà không phải leak tham chiếu sau khi task hoàn tất.

**Ca B — “Cache được thiết kế để giữ dữ liệu, sao lại bị gọi leak?”** Vì mục tiêu có thật chưa đủ: nếu cache dùng key luôn mới và không giới hạn entry/byte, retention có thể vô hạn. Đây là lỗi chính sách vòng đời/capacity; sửa max size/TTL/eviction và đánh giá hit rate.

**Ca C — “Sau khi xóa map, RSS không giảm; cleanup thất bại?”** Chưa thể kết luận. Object có thể chưa GC, vẫn có owner khác, hoặc JVM đã giải phóng object nhưng giữ lại committed pages. Xem object count và đường GC roots, phân biệt used với committed/RSS.

**Ca D — “GC chạy liên tục, chắc có leak?”** GC dày cũng xuất hiện ở ứng dụng có allocation rate cao nhưng live set ổn định. Xem allocation rate, GC CPU, pause và baseline sau GC. Leak thường làm live set ngày càng lớn, nhưng không phải nguyên nhân duy nhất của GC pressure.

**Ca E — “Histogram cho thấy rất nhiều String/byte[]; nên sửa chúng?”** Chúng có thể chỉ là value của cache, HTTP body trong queue, hoặc kết quả parse. Điều tra dominator và Path to GC Roots để tìm owner, không suy thủ phạm từ tên class.

**Ca F — “Đã dùng WeakReference/SoftReference thì an toàn?”** Weak/soft reference có chính sách thu gom riêng, không thay thế owner lifecycle hoặc giới hạn bộ nhớ; nếu còn đường tham chiếu mạnh khác, object vẫn reachable. Đặc biệt tránh xem `SoftReference` là eviction policy có dung lượng dự đoán được.

## 8. Checklist kết luận điều tra

Trước khi ghi “heap tăng do tải”, “retention hợp lệ” hoặc “leak”, hãy trả lời đủ:

- **Đang đo gì?** `used`, sau GC, `committed` hay RSS? Biết collector, heap max và loại GC?
- **Tải nào?** RPS, concurrent request, queue, batch, unique key và số session/cache entry ở từng mốc?
- **Độ bền tăng?** Sau warm-up, hạ tải, drain queue, TTL hết hạn và các chu kỳ GC tương đương, live set có quay lại, plateau hay tiếp tục đi lên?
- **Ai đang giữ object?** Owner, loại reference, path to GC roots, thời điểm hết hạn nghiệp vụ và chính sách dọn dữ liệu?
- **Bằng chứng sửa lỗi?** Kết quả lặp cùng workload, object count/retained size, GC/latency, và hành vi nghiệp vụ sau thay đổi?

**Nguyên tắc quyết định:** chỉ gọi là giữ tham chiếu ngoài ý muốn khi chứng minh dữ liệu đã hết vòng đời nhưng vẫn reachable. Heap tăng tự nó chỉ là triệu chứng; tương quan tải, live set sau GC phù hợp và đồ thị owner mới phân biệt được ba cơ chế.