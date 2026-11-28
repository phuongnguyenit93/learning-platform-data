# Chọn chế độ generational và xác minh bộ thu gom đang hoạt động

## 1. Mục tiêu: bật đúng chế độ và chứng minh JVM đang dùng nó

Shenandoah là bộ thu gom rác (Garbage Collector, GC) đồng thời của HotSpot, được thiết kế cho ứng dụng cần thời gian tạm dừng ngắn. Trong Java 25, Shenandoah có thêm chế độ generational đã được chuẩn hóa thành tính năng product theo **JEP 521**. Chế độ này chia heap thành thế hệ trẻ (*young generation*) và thế hệ già (*old generation*), dựa trên quan sát rằng phần lớn object thường chết sớm sau khi được cấp phát.

Khi dùng generational mode, JVM có thể thu gom vùng young thường xuyên hơn và xử lý old theo nhịp phù hợp với lượng object sống lâu. Mục tiêu là giảm công việc phải lặp lại trên những object đã tồn tại lâu, cải thiện throughput và khả năng xử lý workload có tỷ lệ cấp phát object cao, đồng thời giữ thiết kế low-pause của Shenandoah.

Có hai lựa chọn phải được phân biệt:

- **Chọn collector:** `-XX:+UseShenandoahGC` yêu cầu HotSpot dùng Shenandoah.
- **Chọn mode:** `-XX:ShenandoahGCMode=generational` yêu cầu Shenandoah chạy theo mô hình generational.

JDK 25 không tự chuyển Shenandoah sang generational mode chỉ vì JEP 521 đã final. Nếu chỉ bật collector mà không chỉ định mode, mode mặc định vẫn là `satb` (single-generation). Generational mode phải được chọn tường minh. Đây là điểm quan trọng nhất của bài.

Bài **Chọn chế độ generational và xác minh bộ thu gom đang hoạt động** thuộc chương **Generational Shenandoah** của module **JAVA_VERSION_JAVA25**. Nội dung hướng dẫn kiểm tra khả năng hỗ trợ của bản phân phối JDK, cấu hình JVM, xác minh collector/mode qua log và diagnostic command, đọc dữ liệu GC, rồi so sánh với workload đại diện.

### Sau bài này, bạn có thể

1. Giải thích vì sao generational GC tách object mới cấp phát và object sống lâu.
2. Phân biệt Shenandoah với generational Shenandoah, và phân biệt collector với mode.
3. Nhận biết trạng thái JEP 404 trong JDK 24 và JEP 521 trong JDK 25.
4. Bật Shenandoah generational bằng đúng hai JVM options cần thiết.
5. Xác định bản JDK/vendor/platform có đóng gói Shenandoah hay không.
6. Xác minh JVM thực sự khởi động với collector và mode đã chọn.
7. Thu thập GC logs, JFR và metrics để đánh giá hành vi runtime.
8. Thiết kế benchmark so sánh `satb` và `generational` mà không dựa vào con số quảng cáo.
9. Nhận biết các giới hạn về heuristics, heap sizing, container và cấu hình production.

> **Phạm vi phiên bản:** Generational Shenandoah là product feature trong JDK 25 theo JEP 521. Không cần `-XX:+UnlockExperimentalVMOptions` để bật mode này trên JDK 25. Không dùng hướng dẫn preview/experimental của JDK 24 như cấu hình hiện hành. Shenandoah không có trong mọi JDK distribution hoặc mọi platform build; luôn xác minh đúng runtime sẽ triển khai.

## 2. Vì sao cần generational garbage collection?

Một ứng dụng Java liên tục tạo object: request DTO, chuỗi, collection, buffer, kết quả truy vấn, message và object trung gian. Các object này có vòng đời khác nhau:

- Nhiều object chỉ tồn tại trong thời gian ngắn, ví dụ object phục vụ một request.
- Một phần object sống qua nhiều lần thu gom, ví dụ cache, cấu hình, session hoặc dữ liệu dùng chung.
- Một số object có vòng đời dài gần bằng thời gian sống của ứng dụng.

Đây là đặc điểm thường được mô tả bằng giả thuyết **most objects die young**: phần lớn object được tạo ra không tồn tại lâu. Generational GC khai thác đặc điểm này bằng cách chia heap thành các thế hệ.

~~~mermaid
flowchart TD
    A[Object được cấp phát] --> B[Young generation]
    B -->|Object chết trước lần thu gom| C[Reclaim vùng young]
    B -->|Object còn sống qua các chu kỳ| D[Promote / chuyển sang old]
    D --> E[Old generation]
    E -->|Object còn được tham chiếu| F[Tiếp tục tồn tại]
    E -->|Object không còn được tham chiếu| G[Thu hồi trong chu kỳ old phù hợp]
~~~

Ý tưởng chính:

1. Object mới đi vào young generation.
2. Young generation được thu gom thường xuyên hơn.
3. Object sống sót qua các chu kỳ có thể được promote sang old generation.
4. Old generation được xử lý ít thường xuyên hơn, tùy tình trạng heap và chính sách GC.
5. Việc thu gom một thế hệ cần tính đến reference từ thế hệ còn lại để không giải phóng nhầm object vẫn còn được sử dụng.

Không nên hiểu rằng tất cả object đều chắc chắn đi qua cùng một số lần young GC trước khi được promote. Chính sách tuổi, phân vùng heap và chi tiết implementation do collector quản lý; ứng dụng không nên dựa vào một ngưỡng promotion cố định nếu tài liệu JDK không cam kết.

### 2.1. Vì sao phân thế hệ có thể giảm công việc?

Với collector không phân thế hệ, collector phải quản lý toàn bộ heap theo chiến lược single-generation. Những object sống lâu vẫn có thể được xét lại trong các chu kỳ dù chúng ít thay đổi.

Với mô hình generational:

- Young collection tập trung vào vùng chứa nhiều object mới, trong đó thường có nhiều object đã chết.
- Old generation không nhất thiết phải được xử lý trong mọi young collection.
- Collector cần duy trì thông tin về tham chiếu giữa các vùng/thế hệ để vẫn tìm được object sống.
- Những chu kỳ xử lý old có thể được thực hiện theo nhịp riêng, dựa trên trạng thái heap.

Đổi lại, generational GC cần thêm cơ chế theo dõi quan hệ giữa các thế hệ và các quy tắc barrier phù hợp. Vì vậy, không thể kết luận generational luôn nhanh hơn cho mọi workload.

## 3. Shenandoah là collector nào?

Shenandoah là collector đồng thời, dựa trên region và tập trung giảm thời gian tạm dừng của application thread. Trong quá trình GC, nhiều công việc như marking, evacuation và cập nhật tham chiếu được thực hiện đồng thời với ứng dụng; vẫn có các pha pause ngắn để phối hợp trạng thái cần thiết.

Một chu kỳ Shenandoah ở mức khái niệm:

~~~mermaid
flowchart TD
    A[Application tiếp tục cấp phát] --> B[Concurrent marking]
    B --> C[Chọn vùng cần thu gom]
    C --> D[Concurrent evacuation]
    D --> E[Cập nhật tham chiếu]
    E --> F[Hoàn tất chu kỳ và giải phóng vùng]
    F --> A
~~~

Đây là sơ đồ đơn giản hóa. Pha thực tế, tên log và thứ tự chi tiết phụ thuộc mode và phiên bản HotSpot. Khi điều tra production, hãy đọc GC log của chính build đang chạy.

### 3.1. Low-pause không có nghĩa zero-pause

Shenandoah hướng tới các pause ngắn và thực hiện nhiều công việc đồng thời. Điều đó không có nghĩa:

- Không bao giờ có Stop-The-World pause.
- Mọi pause đều có độ dài cố định.
- Latency của ứng dụng luôn thấp bất kể tải CPU.
- GC không cần thêm CPU hoặc memory headroom.
- Một cấu hình heap bất kỳ đều đáp ứng SLA.

Khi concurrent GC chạy, nó sử dụng CPU và memory bandwidth cùng ứng dụng. Nếu container bị giới hạn CPU hoặc heap quá sát mức cần thiết, collector có thể thiếu thời gian để hoàn tất công việc trước khi áp lực cấp phát tăng cao.

### 3.2. Region-based heap

Shenandoah chia heap thành các region. Region là đơn vị quản lý heap của collector, phục vụ allocation, marking, evacuation và reclaim. Trong generational mode, region còn được quản lý theo thế hệ.

Không nên tự suy ra kích thước region, số region young/old hay cách bố trí cụ thể chỉ từ kích thước `-Xmx`. Những chi tiết này phụ thuộc implementation và ergonomics của JVM.

## 4. Trạng thái tính năng trong Java 24 và Java 25

| Phiên bản | Trạng thái Generational Shenandoah | Ý nghĩa khi cấu hình |
| --- | --- | --- |
| JDK 24 | Experimental theo JEP 404 | Cần mở khóa experimental VM options để thử mode |
| JDK 25 | Product feature theo JEP 521 | Có thể bật bằng mode flag mà không cần unlock experimental |
| JDK 25, chỉ bật Shenandoah | Single-generation mode mặc định là `satb` | Collector có thể chạy nhưng chưa phải generational |
| JDK 25, bật collector và mode | Generational mode được chọn rõ ràng | Đây là cấu hình thực hành của bài |

JEP 521 chuyển generational mode từ experimental sang product feature sau giai đoạn phát triển và ổn định. Điều này xác định trạng thái của tính năng trong HotSpot JDK 25; nó không có nghĩa mọi vendor build đều phải đóng gói Shenandoah trên mọi hệ điều hành.

### 4.1. Ba khái niệm không được nhầm

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| JVM distribution | OpenJDK build từ một vendor | Quyết định binary và collector nào được đóng gói |
| GC selection | `-XX:+UseShenandoahGC` | Chọn Shenandoah làm collector |
| GC mode | `-XX:ShenandoahGCMode=generational` | Chọn thuật toán/mode generational của Shenandoah |

JEP 521 final hóa **mode generational**. Nó không thay đổi mặc định collector của JVM và cũng không tự biến mode mặc định của Shenandoah thành generational.

## 5. Cấu hình Generational Shenandoah trên JDK 25

Cấu hình cốt lõi:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar app.jar
~~~

Trên PowerShell:

~~~powershell
java '-XX:+UseShenandoahGC' '-XX:ShenandoahGCMode=generational' -jar app.jar
~~~

Hai option có vai trò riêng:

- `-XX:+UseShenandoahGC`: bật collector Shenandoah.
- `-XX:ShenandoahGCMode=generational`: chọn chế độ generational.

**Không cần** thêm `-XX:+UnlockExperimentalVMOptions` cho generational mode trong JDK 25. Flag đó thuộc hướng dẫn khi mode còn experimental ở JDK 24.

### 5.1. Chỉ định heap và GC log trong lúc thử nghiệm

Ví dụ một service chạy với heap cố định để phép so sánh dễ lặp lại:

~~~bash
java \
  -Xms4g \
  -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  '-Xlog:gc*,gc+heap=debug:file=gc-generational.log:time,uptime,level,tags' \
  -jar app.jar
~~~

`-Xms` và `-Xmx` ở đây chỉ là ví dụ cho môi trường có đủ memory. Chọn heap theo live set, allocation rate, container limit và headroom của hệ thống. Không sao chép giá trị 4 GB vào production nếu chưa đo.

### 5.2. Không port nguyên cấu hình young generation từ GC khác

Generational Shenandoah có cơ chế quản lý thế hệ riêng. Không lấy các giá trị `-Xmn`, `-XX:NewSize`, `-XX:MaxNewSize`, `-XX:NewRatio` hoặc tuning của G1/ZGC rồi áp dụng máy móc. Các option đó có semantics và mức hỗ trợ khác nhau giữa collector; một cấu hình không được tài liệu JDK 25 xác nhận có thể bị bỏ qua, xung đột hoặc không đem lại hiệu quả mong đợi.

Bắt đầu với ergonomics mặc định của Shenandoah, đo workload rồi chỉ thay đổi option được tài liệu cho đúng mode hỗ trợ.

## 6. Xác minh bản JDK có hỗ trợ Shenandoah

Không phải mọi JDK distribution đều chứa cùng tập collector. Custom runtime image cũng có thể khác full JDK. Trước khi chỉnh cấu hình ứng dụng, hãy kiểm tra đúng binary sẽ chạy trong production.

### 6.1. Xác nhận version và vendor

~~~bash
java -version
~~~

Ghi lại vendor, version đầy đủ và build number. Không chỉ ghi “Java 25”, vì các distribution và patch release có thể khác nhau.

### 6.2. Kiểm tra option trên đúng runtime

Thử khởi động JVM ngắn với cấu hình cần dùng:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc+init=info \
  -version
~~~

Nếu runtime không hỗ trợ option/collector, JVM sẽ báo lỗi khi khởi động. Nếu lệnh thành công, đó là bước xác nhận cấu hình được chấp nhận; tiếp tục kiểm tra log để xác nhận collector và mode đã chọn.

### 6.3. Kiểm tra option sau khi ứng dụng đang chạy

Lấy PID của đúng process:

~~~bash
jcmd -l
~~~

Xem flags:

~~~bash
jcmd <pid> VM.flags -all
~~~

Tìm các giá trị liên quan:

- `UseShenandoahGC`
- `ShenandoahGCMode`
- `ShenandoahGCHeuristics`

Kết quả mong đợi là Shenandoah được bật và mode được đặt thành `generational`. Cú pháp/định dạng output của `VM.flags` có thể khác theo build; kiểm tra đúng process và đúng runtime.

### 6.4. Đối chiếu GC log lúc khởi tạo

Bật log khởi tạo:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc+init=info \
  -version
~~~

GC initialization log là bằng chứng hữu ích về collector/mode được HotSpot khởi tạo. Định dạng thông điệp có thể khác giữa vendor/build. Đọc log của chính binary đang triển khai thay vì phụ thuộc một chuỗi output cố định trong script.

### 6.5. Kiểm tra heap của process

~~~bash
jcmd <pid> GC.heap_info
~~~

Lệnh này cung cấp thông tin heap mà JVM expose tại thời điểm truy vấn. Dùng nó cùng `VM.flags`, GC initialization log và GC log; một dòng heap summary riêng lẻ không đủ để chứng minh mode đang hoạt động.

## 7. Đọc GC log để xác nhận hoạt động thực tế

Chỉ thấy JVM khởi động thành công chưa chứng minh workload đã chạy qua một chu kỳ GC. Hãy giữ GC log trong lúc tái hiện workload và đối chiếu với thời gian chạy.

### 7.1. Bật unified logging

Ví dụ:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  '-Xlog:gc*,gc+heap=debug:file=shenandoah-gc.log:time,uptime,level,tags' \
  -jar app.jar
~~~

Các thành phần:

- `gc*`: thu thập nhóm log tag GC.
- `gc+heap=debug`: bổ sung thông tin heap ở mức debug.
- `file=...`: ghi log ra file.
- `time,uptime,level,tags`: thêm thời gian, uptime, level và tag vào mỗi dòng.

Nếu log quá lớn, giảm mức chi tiết hoặc chỉ bật trong cửa sổ đo. Không mặc định `debug` phù hợp để bật liên tục trên production.

### 7.2. Những điều cần quan sát

| Nhóm dữ liệu | Câu hỏi |
| --- | --- |
| GC initialization | Collector nào và mode nào được khởi tạo? |
| Young collection | Young generation có được thu gom theo workload không? |
| Old collection | Old generation được xử lý với nhịp nào? |
| Pause duration | Các pha pause có nằm trong mục tiêu latency không? |
| Concurrent phases | GC tiêu thụ bao nhiêu thời gian/CPU khi chạy đồng thời? |
| Heap occupancy | Heap sau GC có xu hướng tăng, ổn định hay giảm? |
| Allocation pressure | Application có bị chậm cấp phát khi GC không theo kịp không? |
| Full GC | Có xuất hiện full collection hoặc tình huống fallback bất thường không? |

Tên pha và chi tiết log phụ thuộc JDK build. Dùng log để trả lời câu hỏi về hành vi, không phụ thuộc vào một tên phase không được cam kết ổn định.

### 7.3. Không diễn giải pause riêng lẻ

Một pause ngắn không chứng minh GC tốt hơn. Cần xem:

- Số lần pause trong một đơn vị thời gian.
- Phân phối pause (p50, p95, p99 và max nếu công cụ cung cấp).
- Concurrent CPU time.
- Throughput của ứng dụng.
- Allocation stall hoặc pacing.
- Heap occupancy và memory headroom.

Nếu pause giảm nhưng GC tiêu thụ nhiều CPU hơn, throughput có thể giảm hoặc latency của application thread vẫn tăng do cạnh tranh tài nguyên.

## 8. Thu thập JFR và metrics bổ trợ

GC log cho biết các pha và thời điểm của GC. JFR bổ sung event có timestamp và dữ liệu runtime để đối chiếu với request, thread, allocation và pause.

Bắt một recording giới hạn thời gian:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  '-XX:StartFlightRecording=name=shenandoah-lab,settings=profile,duration=180s,filename=shenandoah.jfr' \
  -jar app.jar
~~~

Nếu service đã chạy, có thể dùng `jcmd`:

~~~bash
jcmd <pid> JFR.start name=shenandoah-lab settings=profile duration=180s filename=shenandoah.jfr
jcmd <pid> JFR.check
jcmd <pid> JFR.stop name=shenandoah-lab filename=shenandoah-final.jfr
~~~

Đọc recording:

~~~bash
jfr summary shenandoah-final.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause,jdk.GCHeapSummary shenandoah-final.jfr
~~~

Các event có sẵn và field cụ thể cần được kiểm tra bằng metadata của recording/JDK đang chạy. Dùng JDK Mission Control để xem event timeline và đối chiếu với application metrics.

### 8.1. Metrics nên lưu cùng recording

- Process CPU usage và container CPU throttling.
- Heap used/committed/max.
- Allocation rate.
- Live set sau GC.
- GC count, duration và pause distribution.
- Application throughput.
- Request latency p50/p95/p99.
- Error rate, timeout và queue depth.
- Container memory usage và memory limit.

Một GC recording không đủ để kết luận hiệu năng service nếu thiếu tải ứng dụng và tài nguyên máy tại cùng thời điểm.

## 9. Generational mode và heuristic

Shenandoah dùng heuristic để quyết định thời điểm bắt đầu GC cycle và lượng công việc xử lý trong chu kỳ. Với generational mode trong JDK 25, heuristic được hỗ trợ là **`adaptive`**, cũng là mặc định.

`adaptive` hướng tới việc duy trì lượng free heap cần thiết trong quá trình GC. Mode generational không hỗ trợ tùy ý các heuristic như `static` hoặc `compact`; không chuyển tuning từ single-generation sang generational nếu chưa xác minh tài liệu cho mode này.

### 9.1. Có cần chỉ định adaptive?

Thông thường không cần. Ví dụ sau tương đương với việc giữ mặc định:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -XX:ShenandoahGCHeuristics=adaptive \
  -jar app.jar
~~~

Chỉ ghi flag này khi muốn làm rõ cấu hình trong một profile triển khai hoặc cần audit giá trị. Nếu không có yêu cầu đặc biệt, giữ mặc định giúp giảm số biến tuning.

### 9.2. Tránh ép heuristic không được hỗ trợ

Không dùng cấu hình như sau cho generational mode:

~~~bash
# Không dùng làm cấu hình Generational Shenandoah
-XX:ShenandoahGCHeuristics=static
-XX:ShenandoahGCHeuristics=compact
~~~

Hãy để JVM dùng `adaptive`, sau đó đánh giá bằng GC log và workload. Không tìm cách mở khóa experimental/diagnostic options để ép mode vào một cấu hình không được hỗ trợ.

## 10. Khi nào nên thử Generational Shenandoah?

Ứng viên đáng thử là ứng dụng có các đặc điểm:

- Allocation rate cao.
- Nhiều object request/operation có vòng đời ngắn.
- Heap tương đối lớn và cần kiểm soát pause.
- Có đủ CPU headroom cho concurrent GC.
- Có thể tái hiện workload và đo throughput/latency ổn định.
- JDK distribution đang dùng có hỗ trợ Shenandoah trên platform mục tiêu.

Không nên chọn chỉ dựa trên việc ứng dụng có heap lớn. Nếu live set chiếm gần hết heap, workload giữ object lâu hoặc container thiếu CPU, lợi ích có thể khác kỳ vọng.

### 10.1. Những tình huống cần đánh giá kỹ

| Đặc điểm workload | Điều cần kiểm tra |
| --- | --- |
| Allocation rate rất cao | Young GC frequency, allocation stall, concurrent CPU |
| Live set lớn | Old generation occupancy, memory headroom, old collection |
| Nhiều object sống lâu | Chi phí xử lý old generation và reference tracking |
| CPU quota thấp | Cạnh tranh CPU giữa ứng dụng và concurrent GC |
| Heap/container sát giới hạn | Committed heap, native memory và container RSS |
| Latency rất nhạy | Pause distribution và application p99 trong tải đỉnh |
| Service khởi động ngắn | Chi phí khởi tạo GC và thời gian warm-up |

## 11. So sánh `satb` và `generational`

JDK 25 có thể chạy Shenandoah ở hai mode liên quan trong bài:

| Tiêu chí | `satb` | `generational` |
| --- | --- | --- |
| Mô hình heap | Single-generation | Young và old generations |
| Ý tưởng | Xử lý heap theo một thế hệ | Thu gom vùng young thường xuyên hơn, old theo chu kỳ riêng |
| Cấu hình | Mode mặc định của Shenandoah | Phải chọn bằng `-XX:ShenandoahGCMode=generational` |
| JDK 25 status | Product mode | Product feature theo JEP 521 |
| Heuristic | Tùy mode và build hỗ trợ | `adaptive` là heuristic được hỗ trợ |
| Kỳ vọng | Baseline single-generation | Có thể cải thiện throughput/hiệu quả với workload phù hợp |
| Rủi ro | Có thể tốn công xử lý object sống lâu trong các chu kỳ | Có thêm chi phí quản lý thế hệ và cần kiểm chứng workload |

Không có phần trăm cải thiện chung cho mọi ứng dụng. Kết quả phụ thuộc object lifetime distribution, allocation rate, live set, CPU quota, heap size và build JDK. Hãy xem `satb` là baseline để so sánh, không coi một mode luôn thắng mode còn lại.

## 12. So sánh với G1 và ZGC

Chọn GC theo mục tiêu của service và kết quả đo:

| Collector | Định hướng | Khi nên đánh giá |
| --- | --- | --- |
| G1 | Cân bằng throughput, latency và memory footprint | Lựa chọn tổng quát cho nhiều ứng dụng server |
| ZGC | Low-latency, hướng tới pause rất ngắn và heap lớn | Khi yêu cầu latency chặt và build hỗ trợ |
| Shenandoah | Concurrent, low-pause và region-based | Khi cần low-pause và muốn đánh giá hành vi trên workload thực |
| Generational Shenandoah | Bổ sung quản lý young/old cho Shenandoah | Khi allocation nhiều và object thường chết trẻ |

Không dùng bảng này để suy ra GC nào nhanh nhất. Chạy cùng workload trên cùng phần cứng và JDK build để so sánh. Cũng không đồng nhất low-pause của collector với end-to-end latency của ứng dụng; queueing, lock, network và CPU scheduling vẫn ảnh hưởng mạnh.

## 13. Thiết kế benchmark có thể lặp lại

Một benchmark tốt phải kiểm soát các biến ngoài GC. Khi so sánh `satb` với `generational`, giữ nguyên:

1. JDK vendor, version và build.
2. Máy, CPU, NUMA, container limit và CPU quota.
3. `-Xms`, `-Xmx` và các tham số heap khác.
4. Ứng dụng, dependencies và build artifact.
5. Dataset, request mix và concurrency.
6. Warm-up và thời lượng đo.
7. Số lần chạy và cách tổng hợp kết quả.

Chỉ thay đổi mode:

**Baseline single-generation:**

~~~bash
java -Xms4g -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=satb \
  -jar app.jar
~~~

**Generational:**

~~~bash
java -Xms4g -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar app.jar
~~~

Cả hai lệnh dùng cùng heap size và workload. `satb` là mode single-generation để làm baseline; `generational` là mode cần đánh giá.

### 13.1. Metrics để so sánh

| Nhóm | Metrics |
| --- | --- |
| Application | Throughput, request latency p50/p95/p99, error rate |
| GC pauses | Count, total duration, p50/p95/p99/max |
| GC work | Concurrent CPU time, cycle frequency, allocation stall |
| Memory | Heap used/committed, live set, RSS, peak container memory |
| Runtime | CPU utilization, CPU throttling, thread count |
| Stability | Timeout, OOM, full GC, pause outlier |

### 13.2. Tránh các sai lệch benchmark

- Không so sánh một lần chạy `satb` với một lần chạy `generational`.
- Không chạy đồng thời hai benchmark tranh chấp cùng CPU hoặc disk.
- Không thay đổi heap size giữa hai mode.
- Không dùng workload synthetic quá nhỏ rồi suy ra hành vi production.
- Không bỏ qua warm-up và JIT compilation.
- Không chỉ so sánh average pause; latency tail mới thường quan trọng với service.
- Không bỏ qua GC CPU time và throughput khi pause giảm.

### 13.3. Tiêu chí quyết định

Chỉ đưa generational mode vào rollout nếu:

- Workload đại diện cho thấy throughput hoặc latency cải thiện theo mục tiêu.
- Pause distribution phù hợp SLA.
- CPU và memory headroom vẫn đủ ở tải đỉnh.
- Không xuất hiện OOM, full GC hoặc allocation stall bất thường.
- Kết quả lặp lại được trên nhiều lần chạy.
- Logging, monitoring và rollback path đã sẵn sàng.

## 14. Thực hành tạo workload cấp phát object

Ví dụ sau tạo nhiều object ngắn hạn và giữ lại một phần nhỏ để mô phỏng workload có nhiều object chết trẻ. Đây là workload minh họa để quan sát GC, không phải benchmark chuẩn.

~~~java
import java.util.ArrayList;
import java.util.List;

public class AllocationWorkload {

    private static volatile List<byte[]> retained = List.of();

    static void allocateBatch(int count, int objectSize, int keepEvery) {
        List<byte[]> survivors = new ArrayList<>();

        for (int i = 0; i < count; i++) {
            byte[] payload = new byte[objectSize];
            payload[0] = (byte) i;

            if (i % keepEvery == 0) {
                survivors.add(payload);
            }
        }

        retained = survivors;
    }

    public static void main(String[] args) throws Exception {
        int count = args.length > 0 ? Integer.parseInt(args[0]) : 100_000;
        int objectSize = args.length > 1 ? Integer.parseInt(args[1]) : 1024;
        int keepEvery = args.length > 2 ? Integer.parseInt(args[2]) : 100;

        for (int batch = 0; batch < 200; batch++) {
            allocateBatch(count, objectSize, keepEvery);
            Thread.sleep(100);
        }

        System.out.println("Retained arrays: " + retained.size());
    }
}
~~~

Biên dịch:

~~~bash
javac --release 25 AllocationWorkload.java
~~~

Chạy single-generation:

~~~bash
java -Xms2g -Xmx2g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=satb \
  '-Xlog:gc*:file=satb.log:time,uptime,level,tags' \
  AllocationWorkload
~~~

Chạy generational:

~~~bash
java -Xms2g -Xmx2g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  '-Xlog:gc*:file=generational.log:time,uptime,level,tags' \
  AllocationWorkload
~~~

Chương trình tạo một mẫu allocation có kiểm soát tương đối đơn giản. Số object sống sót chỉ được giữ qua batch hiện tại; nó không mô phỏng đầy đủ cache, graph object hoặc dữ liệu sống lâu của một service thật. Hãy tăng độ phức tạp và dùng workload production-like khi đánh giá.

## 15. Triển khai trong container và môi trường production

### 15.1. Kiểm tra đúng JDK trong image

Container có thể dùng một JRE/custom runtime khác với JDK ở máy build. Chạy kiểm tra trong chính image:

~~~bash
java -version
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xlog:gc+init=info -version
~~~

Nếu custom runtime image hoặc vendor build không có Shenandoah, JVM có thể từ chối option. Không suy ra collector có mặt chỉ vì image có tên “OpenJDK 25”.

### 15.2. Cấp CPU và memory phù hợp

Concurrent GC cần CPU để hoàn tất công việc khi application tiếp tục chạy. Nếu container bị throttling mạnh, GC có thể không theo kịp tốc độ cấp phát. Khi thử nghiệm, ghi lại:

- CPU request/limit.
- Memory request/limit.
- Heap max (`-Xmx`).
- RSS và native memory.
- CPU throttling.
- Số lượng instance và request concurrency.

Không đặt `-Xmx` sát container memory limit mà quên metaspace, thread stacks, code cache, direct buffers và native memory. Generational mode không loại bỏ nhu cầu có headroom.

### 15.3. Canary trước khi mở rộng

Một quy trình rollout an toàn:

1. Chọn một instance hoặc nhóm nhỏ.
2. Giữ nguyên build và heap sizing, chỉ thay GC mode.
3. Ghi GC log và application metrics.
4. So sánh với instance baseline ở cùng tải.
5. Theo dõi pause tail, throughput, CPU và memory.
6. Mở rộng dần khi kết quả ổn định.
7. Giữ cấu hình `satb` làm phương án rollback.

Đây là quy trình thay đổi cấu hình runtime; không cần sửa code nghiệp vụ chỉ để bật generational mode.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `Unrecognized VM option 'UseShenandoahGC'` | Distribution/build không đóng gói Shenandoah hoặc option không có trên runtime | Xác minh vendor/build và thử trên JDK có Shenandoah |
| JVM báo mode không hợp lệ | Sai chính tả hoặc build không hỗ trợ mode | Kiểm tra `ShenandoahGCMode` và version |
| Cấu hình chạy nhưng không thấy GC log | Log selector/output path không đúng hoặc workload chưa kích hoạt GC | Kiểm tra `-Xlog`, quyền ghi file và thời gian chạy |
| Chỉ thấy `satb` | Chưa đặt mode generational hoặc option bị cấu hình khác ghi đè | Kiểm tra command line và `jcmd VM.flags -all` |
| Pause thấp nhưng throughput giảm | Concurrent GC cạnh tranh CPU/memory bandwidth | Đối chiếu CPU, allocation rate và throughput |
| Old generation tăng liên tục | Live set tăng, workload giữ object hoặc old collection chưa giải phóng đủ | Kiểm tra retention, heap summary và GC cycles |
| Allocation stall | GC không theo kịp allocation hoặc heap headroom thấp | Kiểm tra CPU quota, heap size, allocation rate |
| OOM trong container | Heap cộng native memory vượt giới hạn | Đối chiếu `-Xmx`, RSS, direct memory và container limit |
| Benchmark không ổn định | Warm-up/tải/CPU contention khác nhau | Chuẩn hóa môi trường và chạy lặp lại |

### 16.1. JVM không nhận option

Nếu lệnh báo không nhận `UseShenandoahGC`, đừng thêm `UnlockExperimentalVMOptions` để thử chữa. JEP 521 không thể bổ sung collector vào một binary đã build mà không có Shenandoah. Hãy đổi sang JDK distribution/platform có hỗ trợ hoặc chọn collector sẵn có.

### 16.2. JVM khởi động nhưng mode chưa đúng

Kiểm tra command line thực tế, biến môi trường `JDK_JAVA_OPTIONS`, script entrypoint, manifest/container args và các cấu hình JVM do framework thêm vào. Sau đó đối chiếu `jcmd <pid> VM.flags -all` với GC initialization log.

### 16.3. Generational không cải thiện

Điều đó không nhất thiết là lỗi. Workload có ít allocation, nhiều object sống lâu, CPU hạn chế hoặc heap sizing khác có thể không hưởng lợi. So sánh với baseline và chọn collector đáp ứng SLA tổng thể.

## 17. Những điều không nên cấu hình theo thói quen cũ

Để giữ bài học đúng với Java 25 hiện hành:

- Không thêm `-XX:+UnlockExperimentalVMOptions` cho Generational Shenandoah JDK 25.
- Không giả định Shenandoah tự động được chọn làm collector mặc định.
- Không giả định mode mặc định của Shenandoah là generational; mặc định vẫn là `satb`.
- Không áp dụng `static` hoặc `compact` heuristic cho generational mode; mode này hỗ trợ heuristic mặc định `adaptive`.
- Không port nguyên các tham số young generation của G1 hoặc collector khác.
- Không đặt mục tiêu pause cố định rồi coi đó là cam kết của Shenandoah.
- Không dùng số benchmark từ máy khác để dự đoán phần trăm cải thiện cho service của mình.
- Không coi `java -version` thành công là bằng chứng collector đã được chọn; cần xem flags và GC initialization log.

## 18. Bài tập thực hành

### Bài tập A — kiểm tra trạng thái JDK 25

Chạy `java -version`, sau đó thử `-XX:+UseShenandoahGC` cùng `-XX:ShenandoahGCMode=generational` và `-Xlog:gc+init=info`.

**Đạt khi:** xác định được binary có hỗ trợ Shenandoah và log cho thấy mode generational đã khởi tạo.

### Bài tập B — phân biệt collector và mode

Chạy lần lượt:
1. Không có Shenandoah flags.
2. Chỉ `-XX:+UseShenandoahGC`.
3. Cả `-XX:+UseShenandoahGC` và `-XX:ShenandoahGCMode=generational`.

**Đạt khi:** giải thích được vì sao chỉ chọn Shenandoah chưa có nghĩa đã chọn generational mode.

### Bài tập C — đọc GC log

Dùng `AllocationWorkload` để tạo allocation. Ghi log cho cả `satb` và `generational`, đọc số chu kỳ, pause và heap occupancy.

**Đạt khi:** nhận diện được các hoạt động GC và không kết luận từ một pause đơn lẻ.

### Bài tập D — so sánh hiệu năng

Chạy workload giống nhau với hai mode, cùng heap, CPU limit, warm-up và thời gian đo. Ghi throughput, p99, GC pause, CPU và RSS.

**Đạt khi:** có bảng kết quả lặp lại và giải thích được trade-off.

### Bài tập E — thử container

Tạo một image dùng đúng JDK 25 runtime, xác minh Shenandoah có sẵn, rồi chạy canary với mode generational.

**Đạt khi:** xác minh đúng runtime trong container, không dựa vào JDK ở máy host.

### Bài tập F — viết rollback plan

Chuẩn bị hai cấu hình khởi chạy `satb` và `generational`. Mô tả điều kiện quay lại baseline nếu throughput, latency hoặc memory xấu đi.

**Đạt khi:** có thể rollback bằng thay đổi JVM option và deploy lại, không cần thay code nghiệp vụ.

### Checklist nghiệm thu

- [ ] Hiểu vai trò young và old generation.
- [ ] Biết Shenandoah là concurrent low-pause collector và vẫn có pause.
- [ ] Biết JEP 521 đưa Generational Shenandoah thành product feature trong JDK 25.
- [ ] Phân biệt JEP 404 experimental của JDK 24 với trạng thái JDK 25.
- [ ] Dùng đúng `-XX:+UseShenandoahGC`.
- [ ] Dùng đúng `-XX:ShenandoahGCMode=generational`.
- [ ] Không thêm `-XX:+UnlockExperimentalVMOptions` cho JDK 25.
- [ ] Biết `satb` vẫn là mode mặc định nếu không chọn generational.
- [ ] Xác minh collector/mode qua GC initialization log và `jcmd VM.flags`.
- [ ] Biết không phải mọi JDK distribution đều đóng gói Shenandoah.
- [ ] Giữ heuristic mặc định `adaptive` cho generational mode.
- [ ] So sánh bằng workload, heap, CPU và tải giống nhau.
- [ ] Đánh giá throughput, pause tail, CPU, heap và allocation stalls.
- [ ] Có canary, GC logging, monitoring và rollback plan.

## 19. Tài liệu tham khảo chính thức

1. [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): đưa generational mode từ experimental thành product feature trong JDK 25.
2. [JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): bối cảnh ban đầu của generational mode trong JDK 24.
3. [OpenJDK — The java Command](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): mô tả `-XX:+UseShenandoahGC`, `-XX:ShenandoahGCMode`, mode `satb`/`generational` và heuristic được hỗ trợ.
4. [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp launcher và unified logging options; kiểm tra hỗ trợ collector theo JDK distribution cụ thể.
5. [OpenJDK — Shenandoah GC Wiki](https://wiki.openjdk.org/display/shenandoah/Main): kiến trúc, modes, heuristics và cách vận hành Shenandoah.
6. [Inside Java — What's New in JDK 25](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/): xác nhận JEP 521 là tính năng final trong JDK 25.

**Kết quả mong đợi:** người học có thể chọn đúng generational mode trên một JDK 25 có hỗ trợ Shenandoah, chứng minh mode thực sự được khởi tạo bằng flags và GC log, rồi đánh giá lợi ích bằng workload đại diện. Cần nhớ rằng JEP 521 final hóa tính năng nhưng không thay đổi mặc định: Shenandoah phải được chọn tường minh và mode `generational` cũng phải được yêu cầu tường minh.
