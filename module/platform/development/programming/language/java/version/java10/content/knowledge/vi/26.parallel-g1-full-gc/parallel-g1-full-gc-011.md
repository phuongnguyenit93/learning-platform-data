# So sánh tải tương đương trước khi kết luận về hiệu năng G1 Full GC song song (Java 10+)

## 1. Mục tiêu: đo đúng điều gì, với tải có thực sự giống nhau không?

Khi đánh giá cải tiến **Parallel Full GC for G1** của Java 10, một kết luận hấp dẫn nhưng dễ sai là: “sau khi nâng JDK, một lần Full GC ngắn hơn, vậy ứng dụng nhanh hơn”. Chưa đủ cơ sở. Nếu môi trường trước/sau xử lý **khác số request, kích thước dữ liệu, mức chiếm dụng heap hoặc số luồng CPU**, các con số không đo cùng bài toán.

**Đề bài cần giải quyết:** xây dựng một phép thử **tải tương đương** để phân biệt:

1. **Hiệu quả một lần Full GC:** thời gian dừng ứng dụng trong những sự kiện `Pause Full (G1 Compaction Pause)`.
2. **Ảnh hưởng tổng thể đến ứng dụng:** throughput, latency theo percentile, thời gian GC tổng cộng, CPU và mức sử dụng bộ nhớ.
3. **Khả năng xảy ra Full GC:** số lần Full GC trên cùng đơn vị thời gian hoặc cùng số công việc.
4. **Chi phí tài nguyên của việc song song hóa:** số CPU sử dụng, contention, áp lực bộ nhớ, tác động lên các loại GC khác.

**Chỉ kết luận về hiệu năng khi cả hai cấu hình cùng xử lý một workload tương đương, trong môi trường được kiểm soát, và có dữ liệu đủ tin cậy.** Nếu không xuất hiện Full GC trong một lượt thử, **không thể dùng lượt ấy để khẳng định Full GC song song nhanh hơn**.

Các ví dụ sử dụng Java 17+ và HotSpot/G1 hiện hành. Java 10 được nhắc như mốc giới thiệu cải tiến, **không phải lời khuyên chạy Java 10 đã hết thời gian hỗ trợ thông thường trong production**.

## 2. Bối cảnh: JEP 307 thay đổi gì, và không thay đổi gì?

G1 (Garbage-First) là bộ gom rác cân bằng throughput và latency, thường chia heap thành các **region** và ưu tiên thu hồi qua các collection từng phần:

- **Young GC:** thu hồi vùng trẻ, thường là stop-the-world (STW) ngắn hơn Full GC.
- **Mixed GC:** thu hồi các region trẻ cùng một số region old được chọn sau quá trình đánh dấu.
- **Concurrent marking:** làm một phần việc trong khi ứng dụng vẫn chạy.
- **Full GC:** thu gom/compact toàn heap như cơ chế **dự phòng cuối cùng** khi quá trình thu hồi thông thường không theo kịp áp lực bộ nhớ.

Trước Java 10, phương án Full GC của G1 có phần công việc quan trọng chạy đơn luồng. **OpenJDK JEP 307 — Parallel Full GC for G1**, được đưa vào **Java 10**, song song hóa thuật toán xử lý Full GC nhằm giảm thời gian dừng dài khi phải thực hiện compaction toàn heap.

**Điểm cần khắc ghi:**

- “**Song song**” ở đây nghĩa nhiều GC worker có thể cùng xử lý công việc, **không phải ứng dụng tiếp tục chạy trong lúc Full GC**: Full GC của G1 vẫn là một **stop-the-world pause**.
- G1 được thiết kế để **tránh Full GC**; mục tiêu tốt thường là không để hệ thống rơi vào tình huống phải Full GC, thay vì chỉ rút ngắn một sự kiện Full GC.
- `-XX:ParallelGCThreads` có thể ảnh hưởng số worker làm việc song song trong **các pause Young/Mixed và Full GC**, nên thay đổi flag ấy **không phải phép cô lập riêng cơ chế Full GC**.
- Một JDK mới còn có thay đổi JIT, G1 ergonomics, mặc định heap/region, Java API, class loading và thư viện; chỉ so hai bản JDK rồi quy toàn bộ chênh lệch cho JEP 307 là sai.
- G1 là bộ gom rác mặc định trên nhiều cấu hình HotSpot hiện hành; có thể chọn rõ bằng `-XX:+UseG1GC` cho phép đo.

**Quy tắc học đúng:** JEP 307 là **mốc lịch sử của tính năng vẫn còn trong G1 hiện đại**. Khi đánh giá phiên bản mới, hãy tập trung vào **tải sản phẩm và GC logs hiện hành**, không tái sử dụng giả định rằng G1 Full GC ngày nay chỉ chạy một luồng.

## 3. Vì sao Full GC nhanh hơn chưa chắc ứng dụng tốt hơn?

Giả sử hai hệ thống được đo trong những điều kiện khác nhau:

| Lần đo | Request/giây | Full GC pause quan sát | Bối cảnh |
| --- | ---: | ---: | --- |
| A | 300 | 600 ms | Đầu vào nhẹ, ít request |
| B | 100 | 200 ms | Ít request hơn, live set nhỏ hơn |

**Không thể kết luận B tốt hơn** chỉ vì 200 ms nhỏ hơn 600 ms. Khi B làm ít việc hơn, heap có thể chứa ít object sống và phải compact ít dữ liệu hơn.

Tình huống ngược lại cũng thường gặp: B xử lý nhiều request hơn, khiến **Full GC xảy ra nhiều lần**; dù mỗi pause ngắn hơn, tổng thời gian STW có thể tăng.

Ví dụ **số liệu giả định chỉ để diễn giải**, không phải kết quả benchmark:

| Chỉ số trong cùng 10 phút | A | B |
| --- | ---: | ---: |
| Full GC count | 2 | 8 |
| Thời gian mỗi Full GC, ví dụ đồng đều | 400 ms | 180 ms |
| Tổng Full GC pause | 800 ms | 1.440 ms |

B có **mỗi pause ngắn hơn**, nhưng **tổng downtime do Full GC lại lớn hơn**. Và nếu latency request tại p99 xấu hơn, một cải tiến đơn lẻ trong GC không đủ để gọi là thắng lợi.

Một phép đánh giá phải giữ **đầu vào và điều kiện thử giống nhau** trước, sau đó mới phân tích trade-off giữa latency, throughput và resource cost.

## 4. Định nghĩa “tải tương đương” theo đúng loại hệ thống

Không tồn tại một con số “số thread bằng nhau” đủ mô tả mọi workload. Tải tương đương là **cùng công việc nghiệp vụ cần hoàn thành, cùng cách phát sinh nhu cầu và cùng giới hạn tài nguyên**.

### Với dịch vụ HTTP

Giữ giống nhau:

- **Mức tải chủ động gửi vào:** requests/second hoặc transactions/second theo một kịch bản xác định.
- **Phân bố loại request:** tỷ trọng GET/POST, endpoint đọc/ghi, request nhanh/chậm.
- **Payload:** kích thước request/response, dữ liệu đầu vào, số bản ghi, tỷ lệ cache hit/miss.
- **Concurrency:** số connection, số client độc lập, lịch đến của request, queue policy.
- **State:** dữ liệu DB, cache warming, session, số lượng user, persistence.
- **Thời lượng:** warm-up, thời gian đo, thời gian nghỉ giữa các lượt.

Một phép đo giữ cố định **100 người dùng ảo** chưa chắc tạo tải tương đương: nếu ứng dụng B nhanh hơn, 100 user trong closed-loop có thể gửi **nhiều request hơn mỗi giây**, làm thay đổi lượng công việc và tốc độ cấp phát đối tượng. Nếu muốn so latency ở **cùng offered load**, hãy dùng kịch bản phân phối request với **tốc độ gửi mục tiêu không phụ thuộc tốc độ phản hồi**, trong phạm vi khả năng công cụ tải.

### Với batch/CLI

Giữ:

- **Cùng bộ dữ liệu đầu vào**, kích thước và thứ tự xử lý.
- **Cùng số tác vụ**, kích thước item, tỷ lệ lỗi và thao tác I/O.
- **Cùng số worker ứng dụng** và mức parallelism ở tầng nghiệp vụ.
- **Cùng chính sách retry, timeout, cache và checkpoint**.
- **Cùng điều kiện lưu trữ/network**, hoặc mô phỏng chúng có kiểm soát.

Nếu A chạy với 1 triệu record còn B với 500 nghìn, không được so trực tiếp “thời gian GC” rồi kết luận về collector.

## 5. Các biến cần cố định và biến được phép thay đổi

Bảng kiểm tra một thí nghiệm **A/B kiểm soát**:

| Nhóm biến | Điều phải giữ tương đương | Vì sao ảnh hưởng đến GC |
| --- | --- | --- |
| Mã ứng dụng | Cùng commit, JAR, dependency và cấu hình nghiệp vụ | Khác cách cấp phát và giữ object |
| JDK/runtime | Cùng vendor và build khi so riêng một VM flag | Khác JIT, G1 ergonomics, implementation |
| Collector | `-XX:+UseG1GC` cho cả hai nếu đang đánh giá cấu hình G1 | Collector khác không cùng cơ chế |
| Heap | Cùng `-Xms`/`-Xmx`, chính sách region khi có cấu hình | Thay diện tích và kích thước tập sống |
| CPU | Cùng số core thực dùng, cgroup CPU quota, contention | Thay tốc độ mutator và GC worker |
| RAM/container | Cùng limit memory, swap, page size và điều kiện host | Thay áp lực bộ nhớ/OS |
| Request mix | Cùng tỷ lệ endpoint và payload | Thay allocation rate và survival |
| Data state | Cùng dữ liệu/caches/dependencies | Thay số object sống và thời gian request |
| Rate và duration | Cùng offered load và khoảng đo | Không thể so GC count giữa tải khác nhau |
| GC flags khác | Chỉ đổi **một biến thử nghiệm** đã xác định | Tránh nhiễu do nhiều lựa chọn cùng đổi |
| JVM warm-up | Cùng cách làm nóng JIT, cache và class loading | Tránh startup làm lệch steady state |
| Logging/profiling | Cùng `-Xlog`/JFR và sampling settings | Tránh chi phí đo không cân xứng |
| Host/time | Cùng loại máy hoặc phân bổ chạy A/B ngẫu nhiên/luân phiên | Tránh noisy neighbor, nhiệt độ/CPU frequency |

**Quan trọng về `-XX:ParallelGCThreads`:** nếu thí nghiệm A dùng `1` và B dùng `4`, hãy giữ **mọi flag khác** như nhau. Tuy nhiên, flag này thay song song GC nói chung; **nó không chỉ tác động Full GC**. Do đó có thể đánh giá tác động của **worker setting**, nhưng không tự kết luận rằng mọi thay đổi throughput hay young pause do “Parallel Full GC của Java 10”.

Một số cài đặt mặc định do JVM tự điều chỉnh theo CPU/heap. Không nên mặc định hai container có 4 vCPU “ghi trên giấy” sẽ có cùng CPU quota thực tế hoặc cùng số worker mà JVM thực sự dùng. Kiểm tra log khởi động và môi trường.

## 6. Chọn câu hỏi đo trước khi chạy benchmark

Trước khi thu log, ghi rõ một câu hỏi có thể kiểm chứng.

**Ví dụ câu hỏi hợp lý:**

> Với 1.000 request/giây cùng mix endpoint, trên cùng runtime và tài nguyên, cấu hình B có giảm p99 latency mà không tăng Full GC frequency, GC pause time và CPU đến mức không chấp nhận được không?

Hoặc:

> Trên cùng heap/live set, khi Full GC thật sự xảy ra, cấu hình B có giảm thời gian `Pause Full (G1 Compaction Pause)` trên đủ số sự kiện để tin cậy, mà không làm tổng throughput xấu đi không?

**Ví dụ câu hỏi không đủ rõ:** “Java mới có nhanh hơn không?” vì chưa chỉ rõ nhanh ở đâu: thao tác đơn lẻ, requests/second, p99, thời gian khởi động, một pause hay chi phí CPU?

Định nghĩa **tiêu chí chấp nhận** trước khi xem kết quả. Chẳng hạn: p99 dưới ngưỡng SLO và thông lượng không giảm quá mức chính sách cho phép. Không chọn tiêu chí sau khi thấy số đo chỉ để tuyên bố B thắng.

## 7. Chọn tải cố định hay tải cực đại?

Hai kiểu test cần phân biệt:

### A. Fixed offered load — phục vụ so sánh latency và GC ở cùng nhu cầu

Ví dụ driver gửi đều `500 req/s` với cùng request distribution, bất kể A hay B phản hồi nhanh/chậm. Khi cả hai cùng chịu **500 req/s** trong khoảng đo tương đương, có thể so:

- p50/p95/p99 latency.
- Số Full GC trên một khoảng đo giống nhau.
- Tổng thời gian STW, CPU và heap behavior.
- Tỷ lệ request lỗi/timeout.

Nếu một cấu hình không đủ khả năng duy trì tải, phải ghi nhận backlog, queueing, timeout và drop, **không chỉ lấy mẫu các request thành công**. Các công cụ tải cần tránh lỗi đo **coordinated omission** (bỏ qua những yêu cầu lẽ ra đến trong khi hệ thống đang chậm).

### B. Maximum sustainable throughput — phục vụ so năng lực xử lý

Tăng offered load theo các bậc có cấu trúc, quan sát điểm throughput bão hòa trong khi vẫn đạt error rate và latency SLO. Kết quả là **capacity**; ở đây các cấu hình có thể xử lý request/sec khác nhau theo chủ đích.

**Không trộn kết quả A/B:** nếu ở phép đo throughput B đã xử lý nhiều request hơn, so trực tiếp tổng số Full GC giữa A và B **mà không chuẩn hóa theo lượng công việc và live set** có thể gây kết luận sai.

Cả hai loại test đều hữu ích nhưng trả lời **hai câu hỏi khác nhau**.

## 8. Live set, allocation rate và promotion quyết định áp lực GC

Đặc biệt khi nghiên cứu Full GC của G1, “cùng số operation” đôi khi chưa đủ:

- **Allocation rate:** số byte cấp phát mỗi giây. Cùng 100.000 request có thể tạo lượng object khác nhau nếu đầu vào khác.
- **Live set:** lượng dữ liệu còn được tham chiếu sau GC. Heap chứa nhiều object sống thì compaction cần xử lý nhiều dữ liệu hơn.
- **Object lifetime:** tỷ lệ object ngắn hạn và dài hạn quyết định promotion và mức chiếm dụng old generation.
- **Humongous objects:** object đủ lớn so với G1 region có cách cấp phát/xử lý riêng, có thể làm tăng fragmentation/áp lực Full GC.
- **Heap occupancy at GC start:** hai Full GC với occupancy khác nhau không phải hai trường hợp tương đương.
- **Allocation bursts:** lưu lượng đột biến làm thay nhịp đánh dấu đồng thời và nhu cầu evacuation.

Muốn so thời gian **một lần Full GC**, cần ghi nhận ít nhất **lượng bộ nhớ trước/sau, old occupancy, số region humongous và nguyên nhân Full GC**. Nếu A compact 2 GiB object sống còn B compact 200 MiB, thời gian thấp hơn ở B không chứng minh algorithm hay cấu hình tốt hơn.

Không ép mọi benchmark phải “đạt bằng được một Full GC” bằng cách cấp phát vô hạn, vì chương trình có thể OOM hoặc thay đổi mục tiêu đo. Có thể làm stress test trong môi trường cô lập nếu cần đánh giá **đường đi lỗi/khôi phục**, nhưng phải tách khỏi benchmark phục vụ quyết định production.

## 9. Các chỉ số cần thu cùng nhau

| Chỉ số | Cách diễn giải | Lưu ý |
| --- | --- | --- |
| Throughput | Request/giây, giao dịch/giây, records/giây | Phải biết lượng công việc và error rate |
| p50 latency | Trải nghiệm request phổ biến | Không đại diện tail latency |
| p95/p99/p99.9 | Tail latency và ảnh hưởng pause dài | Cần đủ mẫu và đo cả timeout/queue |
| Full GC count | Tần suất rơi vào cơ chế dự phòng | Chuẩn hóa theo cùng thời gian/tải |
| Full GC pause duration | Thời gian dừng của sự kiện Full GC | Chỉ lấy sự kiện `Pause Full`, không lẫn Young |
| Full GC total pause | Tổng thời gian dừng do Full GC | Count × pause, tính từ log thực |
| All GC STW total | Tổng thời gian pause của Young/Mixed/Full và những pause GC khác | Không chỉ xem Full GC |
| Old/heap occupancy | Áp lực, dữ liệu sống và khả năng thu hồi | Cùng heap khác live set vẫn không công bằng |
| Humongous regions | Áp lực object lớn/fragmentation | Theo dõi log phù hợp |
| CPU utilization | Chi phí mutator và GC workers | Parallel GC có thể dùng nhiều CPU hơn |
| RSS/container memory | Mức bộ nhớ tiến trình và container | `-Xmx` không phải tổng RSS |
| Allocation/promotion rate | Vì sao GC xảy ra | Cần telemetry/profiler/JFR phù hợp |
| Error/timeout rate | Dịch vụ có hoàn thành công việc không | Không bỏ request thất bại khỏi so sánh |

**Đừng chỉ xem average GC pause.** Một Full GC duy nhất kéo dài nhiều giây có thể ảnh hưởng p99/p99.9 của request trong khi giá trị trung bình GC của hàng trăm young pause vẫn nhỏ.

**Đừng chỉ xem p99 request** mà không xem Full GC logs: nếu không hề có Full GC trong khoảng test, p99 khác nhau là kết quả của nhiều nguyên nhân khác, không thể tự động gắn cho JEP 307.

## 10. Thu GC log bằng Unified Logging hiện hành

Với HotSpot/JDK 17+, Unified Logging `-Xlog` là công cụ phù hợp để xem sự kiện G1 và các phase. Ví dụ chạy cùng chương trình dưới hai cấu hình:

```bash
java -XX:+UseG1GC -Xms128m -Xmx128m \
     -XX:ParallelGCThreads=1 \
     -Xlog:gc*,gc+phases=debug:file=gc-A.log:uptime,level,tags \
     G1ComparableLoadDemo
```

```bash
java -XX:+UseG1GC -Xms128m -Xmx128m \
     -XX:ParallelGCThreads=4 \
     -Xlog:gc*,gc+phases=debug:file=gc-B.log:uptime,level,tags \
     G1ComparableLoadDemo
```

Hai lệnh minh họa cho shell hỗ trợ dấu `\` nối dòng, khi đã biên dịch `G1ComparableLoadDemo.java`. Chúng dùng **cùng workload và heap**, chỉ thay `ParallelGCThreads`.

**Cảnh báo quan trọng:** đây là phép thử **ảnh hưởng cấu hình số worker trên cùng JDK**, **không phải** tái hiện chính xác cải tiến Java 9 → 10. `-XX:ParallelGCThreads` cũng ảnh hưởng **Young/Mixed pauses**, nên khi có chênh lệch phải xem từng loại sự kiện.

Trong GC log, có thể gặp:

```text
GC(17) Pause Young (Normal) (G1 Evacuation Pause) ...
GC(18) Pause Young (Mixed) (G1 Evacuation Pause) ...
GC(19) Pause Full (G1 Compaction Pause) ...
```

Đây là **mẫu nhận diện** đã lược bớt trường thông số, **không phải stdout chuẩn của chương trình demo**. Cần tra các dòng thực tế trong log: mỗi dòng có timestamp, tag, GC ID, cause, heap before/after và duration theo phiên bản JDK.

Điểm phân biệt:

- `Pause Young` không phải Full GC.
- `Pause Young (Mixed)` cũng không phải Full GC, dù thu hồi cả old regions.
- `Pause Full (G1 Compaction Pause)` là sự kiện cần thu riêng khi đánh giá đường đi Full GC.

Oracle G1 Tuning Guide hiện hành hướng dẫn dùng `-Xlog:gc*=debug` khi chẩn đoán, và xem Full GC qua cụm từ **`Pause Full (G1 Compaction Pause)`**.

### Kiểm tra tên cấu hình worker trong JVM

Có thể quan sát các flag trên một tiến trình đang chạy bằng công cụ `jcmd` của JDK:

```bash
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
```

`<pid>` trong hai lệnh trên là **vị trí điền ID tiến trình** khi chạy thật, không phải chuỗi literal để copy nguyên. Việc `jcmd` attach cần quyền và môi trường cho phép; container/CI có thể hạn chế.

Để xem thông tin flag cuối cùng ở lúc khởi chạy, có thể chạy:

```bash
java -XX:+UseG1GC -XX:+PrintFlagsFinal -version
```

Lượng output khá lớn; chỉ chọn các flag liên quan `UseG1GC`, `ParallelGCThreads`, `MaxGCPauseMillis` và kích thước heap. **Giá trị `ParallelGCThreads` là giới hạn/cấu hình worker; không được phép suy luận luôn luôn có đúng N thread hoạt động hữu ích trong mỗi phase.** Số worker thực tế có thể do G1 điều chỉnh theo điều kiện pause/heap.

## 11. Java Flight Recorder (JFR) giúp đối chiếu pause và hoạt động ứng dụng

Ngoài GC log, **Java Flight Recorder (JFR)** trên JDK hiện đại có thể ghi GC events, allocation, CPU, thread và nhiều sự kiện hữu ích cho phân tích.

Ví dụ bắt đầu ghi khi khởi chạy:

```bash
java -XX:+UseG1GC -Xms128m -Xmx128m \
     -XX:StartFlightRecording=filename=sample-A.jfr,settings=profile \
     G1ComparableLoadDemo
```

Đây là **mẫu command**; cần quyền ghi file và JDK hỗ trợ JFR. Ghi profile có overhead, nên hai cấu hình A/B phải dùng **cùng settings JFR** và nên đo thêm baseline khi cần xác định chi phí giám sát.

Dùng `jfr` command hoặc **JDK Mission Control** để xem:

- GC events, GC ID/cause và tổng pause.
- Allocation rates, heap/old generation, event liên quan GC.
- CPU và thread behavior trong thời điểm pause.
- Chuỗi sự kiện trước khi Full GC: allocation burst, evacuation failure, humongous pressure.

**Phân biệt:** JFR và GC logs bổ trợ nhau; một chỉ số CPU % cao của GC workers không đồng nghĩa latency giảm, và một Full GC duration ngắn chưa chắc throughput tốt. Hãy đặt chúng cạnh request/transaction metrics cùng thời gian.

## 12. Warm-up, số lần đo và thứ tự A/B

Java có **JIT compilation**, class loading, code cache, caching ở ứng dụng và JVM ergonomics. Lượt chạy đầu thường không đại diện steady state. Một kế hoạch đo tốt:

1. Đảm bảo môi trường giống nhau và không có job nặng đang chạy cạnh tranh.
2. Chạy **warm-up** cùng kịch bản và thời lượng phù hợp để các code path chính được sử dụng.
3. Chỉ mở **cửa sổ đo** sau warm-up đã xác định, hoặc đánh dấu rõ phần startup nếu chính startup là thứ muốn đo.
4. Chạy một block **A–B–B–A** hoặc thay thứ tự ngẫu nhiên để giảm bias do nhiệt độ máy, CPU throttling và thời điểm.
5. Lặp nhiều block độc lập, có điều kiện reset state/caches được định nghĩa rõ.
6. Lưu đầy đủ raw measurements và cấu hình của từng lần chạy, không chỉ lưu một ảnh chụp kết quả đẹp nhất.
7. Tính median và khoảng biến thiên giữa các lượt, đồng thời xem percentile của **request latency trong từng lượt** và sample size.

**Không có một số lần chạy cố định phù hợp mọi hệ thống.** Nếu Full GC là sự kiện hiếm, một lượt thử 30 giây có thể không có sự kiện nào. Khi đó không nên tự thay đổi workload A/B riêng biệt cho đến khi thấy Full GC, vì phép so sẽ mất tính tương đương.

**Tối thiểu phải báo số lượng mẫu:** p99 của hai Full GC events không phải chỉ số thống kê đáng tin cậy. Nếu không đủ quan sát, kết luận nên là “chưa đủ dữ liệu Full GC”, thay vì ép ra một tỷ lệ cải thiện.

## 13. Công thức và ví dụ diễn giải kết quả

Với cùng workload/điều kiện, thay đổi phần trăm thời gian có thể tính:

```text
change_pct = (B - A) / A × 100%

A: p99 Full GC pause = 800 ms
B: p99 Full GC pause = 600 ms
change_pct = (600 - 800) / 800 × 100% = -25%
```

**Đây là ví dụ giả định để đọc phép tính**, không phải kết quả của G1 hoặc JEP 307.

Nhưng trước khi nói “B giảm p99 Full GC pause 25%”, còn cần hỏi:

- Có đủ số Full GC observations để p99 có ý nghĩa không?
- Live set, occupancy trước GC, cause, fragmentation của A/B có tương đương?
- Tổng Full GC count và tổng STW time có thay đổi?
- Throughput và p99 request latency có giữ SLO?
- CPU sử dụng có tăng quá mức do nhiều GC workers không?
- Khoảng biến thiên giữa các lần chạy có nhỏ hơn hiệu ứng đo được không?

Nếu A không có Full GC còn B có 1 Full GC, **không thể lấy p99 Full GC của A là 0 để tính “tăng vô hạn”**. Phép so về **độ dài một Full GC** khi bên A không có mẫu là **không xác định**. Cần báo riêng tần suất sự kiện và latency ứng dụng.

Cũng không lấy tổng Full GC pause chia cho số request rồi gọi đó là p99 request latency: stop-the-world pause và request latency là hai phân phối có quan hệ nhưng không phải phép biến đổi 1–1.

## 14. Java 17+ hoàn chỉnh: workload cấp phát giống nhau, checksum xác định

Ví dụ này được thiết kế để **xác minh đầu vào tải logic giống nhau giữa các lần khởi động JVM**. Nó tạo các mảng byte với kích thước cố định, thay đổi một vài byte, giữ reference của 256 mảng gần nhất để tránh mọi thứ chỉ tồn tại dưới dạng phép tính vô nghĩa, rồi in checksum và tổng số byte payload được **yêu cầu cấp phát**.

**Đây không phải một benchmark Full GC có thể kết luận hiệu năng ngay.** Nó không cố ý kích hoạt `System.gc()`, không tạo memory leak và **không bảo đảm có Full GC**. Mục đích của nó là minh họa cách giữ cùng số operation và payload khi so các lần chạy. Đối với dịch vụ thật, hãy thay bằng request mix/tải nghiệp vụ tương đương.

Tạo tệp `G1ComparableLoadDemo.java`:

```java
import java.util.Arrays;
import java.util.Objects;

public final class G1ComparableLoadDemo {

    // Làm kết quả còn được quan sát sau khi vòng lặp kết thúc.
    static volatile byte[][] keepAlive;
    static volatile long sink;

    public static void main(String[] args) {
        final int operations = 240_000;
        final int bytesPerObject = 1_024;
        final int ringSlots = 256;

        byte[][] recent = new byte[ringSlots][];
        long checksum = 0;
        long start = System.nanoTime();

        for (int i = 0; i < operations; i++) {
            byte[] data = new byte[bytesPerObject];
            data[0] = (byte) i;
            data[bytesPerObject - 1] = (byte) (i >>> 8);

            // Mỗi object mới chiếm một vị trí ring.
            // Các reference cũ bị thay bằng reference mới.
            recent[i % ringSlots] = data;

            checksum += (data[0] & 0xff)
                    + (data[bytesPerObject - 1] & 0xff);
        }

        long elapsed = System.nanoTime() - start;

        keepAlive = recent;
        sink = checksum;

        long live = Arrays.stream(keepAlive)
                .filter(Objects::nonNull)
                .count();

        if (live != ringSlots || checksum != sink) {
            throw new AssertionError("Unexpected workload state");
        }

        System.out.println("operations=" + operations);
        System.out.println("payloadBytes=" + bytesPerObject);
        System.out.println("requestedPayloadBytes="
                + ((long) operations * bytesPerObject));
        System.out.println("liveSlots=" + live);
        System.out.println("checksum=" + checksum);
        System.out.println("elapsedPositive=" + (elapsed > 0));
        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy độc lập:

```bash
javac --release 17 G1ComparableLoadDemo.java
java -XX:+UseG1GC -Xms128m -Xmx128m G1ComparableLoadDemo
```

Stdout **đã kiểm tra bằng JDK 24**:

```text
operations=240000
payloadBytes=1024
requestedPayloadBytes=245760000
liveSlots=256
checksum=59315136
elapsedPositive=true
tests=PASS
```

**Cách đọc output:**

- `operations=240000`: cùng số vòng công việc logic giữa mọi cấu hình.
- `payloadBytes=1024`: kích thước payload yêu cầu cho mỗi mảng byte.
- `requestedPayloadBytes=245760000`: `240000 × 1024`, **không phải tổng byte heap JVM thực sự đã cấp phát**; còn object headers, alignment, ring array, class metadata và tối ưu JIT.
- `liveSlots=256`: các slot ring cuối đều có reference, giúp xác nhận state dự kiến.
- `checksum=59315136`: output nghiệp vụ xác định để phát hiện mã đầu vào/tác vụ thay đổi.
- `elapsedPositive=true`: kiểm tra đơn giản `System.nanoTime()` tiến lên, **không phải** phép đo tốc độ chuẩn để so JDK.
- `tests=PASS`: các assertion về công việc và state đã đạt.

Tại sao không in một con số `elapsedMs` cố định? Bởi vì thời gian thực phụ thuộc CPU, JIT, OS scheduling, GC và thí nghiệm. Ghi một giá trị benchmark giả thành “output chuẩn” sẽ dạy sai về đo hiệu năng. Trong benchmark thật, **phải đo thời gian và lượng công việc thực tế ở từng lượt**, lưu kết quả riêng, không xem con số ấy là hằng số Java.

**Giới hạn của workload này:** mảng byte đều nhau và vòng lặp đơn luồng không mô phỏng đầy đủ lifetime distribution, network, DB, cache, concurrency hoặc tail latency của dịch vụ. Nó có thể gây Young GC, nhưng **không bảo đảm G1 phải Full GC**. Không lấy nó để tuyên bố lợi ích Full GC song song khi log không có sự kiện tương ứng.

## 15. Chạy A/B cùng workload sau khi biên dịch

Với JDK 17+ và file `G1ComparableLoadDemo.class` đã tạo, thử:

**A — một GC worker cấu hình:**

```bash
java -XX:+UseG1GC -Xms128m -Xmx128m \
     -XX:ParallelGCThreads=1 \
     -Xlog:gc*,gc+phases=debug:file=gc-one.log:uptime,level,tags \
     G1ComparableLoadDemo
```

**B — bốn GC workers cấu hình:**

```bash
java -XX:+UseG1GC -Xms128m -Xmx128m \
     -XX:ParallelGCThreads=4 \
     -Xlog:gc*,gc+phases=debug:file=gc-four.log:uptime,level,tags \
     G1ComparableLoadDemo
```

Cần làm đúng:

1. Chạy A và B trên **cùng bản JDK build, OS, CPU limit, RAM limit**.
2. Kiểm tra **cùng stdout workload** ở phần 14; nếu khác checksum hoặc số operation, không được so hiệu năng.
3. Kiểm tra log `gc-one.log` và `gc-four.log`; xác minh collector G1 được dùng.
4. So sánh riêng Young, Mixed, Full pauses; không gộp tất cả GC events thành “Full GC”.
5. Thực hiện nhiều lần và đổi thứ tự A/B; demo quá ngắn có thể chịu ảnh hưởng startup/JIT rất lớn.
6. Nếu **không có Full GC**, kết luận đúng là phép đo **chưa tạo quan sát Full GC**. Không nói “Full GC B nhanh hơn A”.
7. Nếu có Full GC, so **điều kiện ngay trước pause và cause**, không chỉ mỗi thời lượng.

**Nhấn mạnh:** `-XX:ParallelGCThreads=1` là cách chủ động giảm GC parallelism trong một phép thử trên JDK hiện hành, **không tái tạo nguyên trạng thuật toán G1 Full GC trước Java 10**. `=4` cũng không chứng minh thực tế bốn worker luôn làm việc. Những giả định ấy phải được thay bằng GC phase logs và quan sát đúng loại sự kiện.

## 16. Khi không thấy Full GC thì phải làm gì?

Trong các workload lành mạnh, **không có Full GC** thường là tín hiệu tích cực: G1 đã thu hồi bộ nhớ mà không cần đường đi dự phòng toàn heap.

Khi thiếu Full GC events:

- Báo **Full GC count = 0** trong thời gian quan sát, kèm số operation/requests và mức tải.
- Báo **thời gian pause Full GC không có mẫu**, không tự gán mean/p99 = 0 ms như một giá trị đã đo.
- Có thể so throughput, latency và các Young/Mixed GC pauses nếu điều kiện A/B tương đương.
- Nếu cần nghiên cứu một **đường đi Full GC bị vấn đề trong production**, dùng workload/mẫu heap đại diện cho incident trên **staging cô lập**, phân tích nguyên nhân và đảm bảo có thể dừng test an toàn.
- Xác nhận sự kiện Full GC là do **allocation/evacuation pressure**, không phải vô tình do `System.gc()`, tool hoặc thao tác kiểm tra heap gây ra.

**Không bật `System.gc()` liên tục trong benchmark ứng dụng để tạo nhiều Full GC** rồi coi đó là throughput bình thường. Javadoc và Oracle GC Tuning Guide cho thấy explicit GC có hành vi chịu cấu hình/collector; một sự kiện do `System.gc()` không nhất thiết tương đương Full GC xảy ra vì hết không gian cấp phát.

Tương tự, đừng cố ý làm JVM OOM trong cùng cụm production để “lấy thêm mẫu”. Nếu cần stress/chaos, thực hiện trong môi trường giới hạn bộ nhớ/quyền rõ ràng và có quy trình an toàn.

## 17. Đọc nguyên nhân Full GC thay vì chỉ tối ưu thời lượng

Oracle G1 Tuning Guide hiện hành hướng dẫn tìm `Pause Full (G1 Compaction Pause)` trong log và xét những sự kiện trước đó, chẳng hạn **evacuation failure**, allocation pressure và old-region occupancy.

Ví dụ nhóm dấu hiệu cần kiểm tra:

| Tín hiệu | Có thể gợi ý | Hành động phân tích |
| --- | --- | --- |
| Full GC sau `Evacuation Failure` | Không đủ chỗ để di chuyển object còn sống | Xem heap occupancy, old regions, free regions |
| Humongous regions tăng | Object lớn tạo áp lực vùng liên tiếp | Xem kích thước object, heap regions, fragmentation |
| Promotion rất cao | Nhiều object sống lâu | Xem lifetime/cache, số liệu allocation |
| Concurrent marking chưa hoàn thành | GC không thu hồi old kịp | Xem allocation rate, IHOP và CPU time marking |
| `System.gc()` trong GC cause | Mã ứng dụng hoặc công cụ chủ động yêu cầu GC | Xem nguồn gọi, tránh xem đây như load bình thường |
| Full GC count tăng mạnh | Hệ thống thường xuyên vào fallback | Tìm nguyên nhân trước khi tập trung vào worker count |

Các hướng cải thiện có thể gồm **giảm object dài hạn**, **giảm object humongous**, lựa chọn heap size phù hợp, xem cơ chế marking và chỉ điều chỉnh GC flags sau khi có bằng chứng. Hướng dẫn Oracle khuyên bắt đầu với G1 mặc định, điều chỉnh mục tiêu pause và heap khi có lý do, không vội cố định young generation size bằng `-Xmn` hoặc flag tương tự vì có thể làm mất khả năng G1 tự điều chỉnh để đáp ứng pause target.

**Tối ưu tốt có thể làm Full GC không xảy ra nữa**; đó thường là kết quả đáng giá hơn việc chỉ rút ngắn những Full GC vốn quá thường xuyên.

## 18. So sánh JDK cũ/mới: vì sao khó quy kết cho riêng JEP 307?

JEP 307 xuất hiện ở Java 10. Nếu so **Java 9 và Java 10**, khác biệt không chỉ có một đường Full GC: runtime còn thay JIT, các tối ưu VM, API và những thay đổi khác. Đây là một ví dụ về **confounding variables**.

Trong học thuật có thể đọc JEP 307 để hiểu ý tưởng song song hóa, nhưng **không nên đưa Java 9/10 đã cũ vào production để benchmark tính năng hiện hành**. Nếu buộc phải nghiên cứu hành vi lịch sử, thực hiện trong lab cô lập, ghi rõ JDK build và giới hạn kết luận.

Đối với dự án vận hành hiện nay, cách đánh giá có giá trị hơn thường là:

- Cùng ứng dụng, cùng dữ liệu, cùng workload.
- Runtime JDK được sản phẩm hỗ trợ và được vá.
- So thay đổi **một cấu hình** hoặc **một bản JDK** trong môi trường tương đương.
- Khi đổi JDK, mô tả kết quả là **ảnh hưởng tổng thể của nâng JDK**, **không tự quy cho JEP 307**.
- Nếu mục tiêu là Full GC, yêu cầu có **đủ sự kiện Full GC tương đương** và GC-phase evidence.
- Nếu không có Full GC, báo cáo đúng rằng **không có cơ sở so thời lượng Full GC**, nhưng vẫn có thể đánh giá lợi ích vận hành chung của nâng JDK.

Thứ tự phát hành Java 9/10 chỉ mang ý nghĩa **bối cảnh tính năng**. Về mặt áp dụng hôm nay, dùng G1 và công cụ đo hiện hành mới quan trọng.

## 19. Mẫu báo cáo kết quả có thể ra quyết định

Một báo cáo A/B tối thiểu nên có những trường sau:

| Nhóm | Giá trị cần báo |
| --- | --- |
| Runtime | JDK vendor, build, architecture, container image |
| VM configuration | G1 enabled, `-Xms`, `-Xmx`, `ParallelGCThreads` và các flag khác |
| Phần mềm | Commit, JAR/dependency, config, dữ liệu |
| Tải | Offered RPS, concurrency, payload mix, time window, warm-up |
| Thành công | Requests hoàn thành, lỗi, timeout, backlog |
| Latency | p50/p95/p99/p99.9, số mẫu, cách xử lý timeout |
| Throughput | Throughput đo được theo mỗi lượt |
| GC | Young/Mixed/Full counts, total STW, Full pause distribution |
| Memory | Heap/old live set, allocation rate, humongous regions, RSS |
| CPU | CPU limit, GC/user CPU usage, throttling |
| Phép thử | Số lần chạy, thứ tự A/B, điều kiện reset |
| Kết luận | Thay đổi có ý nghĩa theo SLO không; còn thiếu dữ liệu nào |

Không nhất thiết luôn cần mọi ô, nhưng **ít nhất phải có workload và context đủ để lặp lại**. Chỉ có hai ảnh chụp GC pause chart là chưa đủ.

Ví dụ **một cách viết kết luận đúng**:

> “Trong ba block A/B có cùng tải, cấu hình B có p99 request latency thấp hơn, tổng STW pause thấp hơn và throughput không giảm quá mức đo được. Có đủ Full GC events tương đương nên có thể xem xét thêm riêng tác động Full GC. Tuy nhiên đây là so sánh cấu hình `ParallelGCThreads` trên JDK hiện hành, không phải phép chứng minh độc lập cho JEP 307.”

Ví dụ **kết luận đúng khi thiếu mẫu**:

> “Cả A và B đều không có Full GC trong cửa sổ đo. Benchmark chứng minh hai cấu hình hoàn thành workload đã định và cho số liệu throughput/Young GC; không thể rút ra kết luận về hiệu năng Full GC song song.”

Đây là **mẫu diễn đạt cách kết luận**, không phải báo cáo đã đo thật từ chương trình demo.

## 20. Kiểm tra log và kết quả với công cụ dòng lệnh

Nếu đã chạy các lệnh ở phần 15 và tạo `gc-one.log`/`gc-four.log`, trên hệ thống kiểu Unix có thể tìm Full GC:

```bash
grep 'Pause Full' gc-one.log
grep 'Pause Full' gc-four.log
```

Với PowerShell:

```powershell
Select-String -Path gc-one.log -Pattern 'Pause Full'
Select-String -Path gc-four.log -Pattern 'Pause Full'
```

Không có dòng nào phù hợp **không có nghĩa GC bị tắt**: có thể chỉ có Young/Mixed GC; cũng phải kiểm tra log thực sự được ghi, mức logging có đủ và khoảng đo phù hợp.

Muốn đối chiếu các worker/phase, bật `gc+phases=debug` trong cửa sổ test rồi xem sự kiện theo GC ID. Khi phân tích tự động, cần parser phù hợp log version của JDK; không mặc định mọi JDK/vendor in cùng một biểu thức văn bản bất biến.

Với Full GC events, nên xuất bảng gồm:

```text
run_id, gc_id, cause, pause_ms,
heap_before_mb, heap_after_mb, old_live_mb,
humongous_regions, process_cpu_load,
offered_rps, successful_requests, error_requests
```

Danh sách trên là **gợi ý schema thu dữ liệu**, không phải tên các field mà Java GC log luôn in sẵn trong một dòng. Nhiều trường cần tổng hợp từ metrics/JFR/GC logs; chúng phải được **đồng bộ theo thời gian và run id**.

Một bảng đo giàu ngữ cảnh giúp giải thích vì sao một Full GC kéo dài lâu hơn thay vì chỉ cộng/trừ các con số.

## 21. Những lỗi thường gặp khi tuyên bố “G1 song song nhanh hơn”

| Cách làm sai | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| So log của 100 req/s với log 1.000 req/s | Khác số object tạo ra, live set, heap pressure | Đặt cùng offered load/request mix |
| Cố định 100 virtual users và coi RPS chắc chắn bằng nhau | Closed-loop cho RPS khác nếu latency khác | Đo RPS thực; dùng open-loop nếu cần fixed arrival |
| So một Full GC của A với một Full GC của B | Nhiễu rất lớn và occupancy có thể khác | Lấy đủ mẫu, kiểm tra cause/live set |
| So Young GC pause rồi gọi là Full GC | Sai loại event | Chọn `Pause Full (G1 Compaction Pause)` |
| Chỉ đo throughput, không có GC log | Không biết Full GC có xảy ra | Thu logs/JFR đồng bộ |
| `Full GC count = 0` nhưng ghi “Full GC p99 = 0 ms” | Không có mẫu, không phải một pause 0 ms | Báo “không có dữ liệu để ước lượng” |
| Dùng `System.gc()` liên tục để mô phỏng production | Khác nguyên nhân GC, méo workload | Dùng tải đại diện; thử explicit GC riêng |
| Đổi `-Xmx`, JDK, worker count cùng lúc | Không biết yếu tố nào tạo cải thiện | Kiểm soát biến, thay một biến |
| Tăng `ParallelGCThreads` và cho rằng chỉ Full GC bị ảnh hưởng | Young/Mixed cũng thay đổi | Phân tích từng loại pause |
| Lấy `ParallelGCThreads=4` là bằng chứng 4 worker hiệu quả | Số thread thực tế và CPU quota có thể khác | Xem GC phase log/CPU |
| Chạy trên một máy nóng và một máy rảnh | OS scheduling/CPU contention thay đổi | Cùng host hoặc ABBA/randomized runs |
| Chỉ đo lần startup đầu, coi đó là steady state | JIT/class loading/cache gây sai lệch | Warm-up và định nghĩa window |
| Chỉ lấy trung bình latency | Bỏ tail latency do STW pause dài | Báo p95/p99/p99.9 và timeout |
| Kết luận theo 1 run nhanh nhất | Selection bias | Lặp nhiều lần, báo phân phối |
| Không đo CPU/memory footprint | Parallelism có thể gây chi phí khác | Báo tài nguyên cạnh latency |
| So Java 9 với Java 10 rồi gán mọi cải thiện cho JEP 307 | JDK đổi nhiều tính năng | Chỉ mô tả correlation; cô lập bằng bằng chứng phù hợp |
| Ép OOM trên production để tạo Full GC | Rủi ro ngắt dịch vụ | Stress trong lab cô lập |
| Cố định young generation quá sớm | G1 mất khả năng tự điều chỉnh pause target | Bắt đầu bằng G1 defaults theo tài liệu Oracle |

## 22. Bài tập tự kiểm tra

### Bài 1: cùng số user, có cùng tải không?

Một hệ thống chạy 50 virtual users. A phản hồi 200 ms, B phản hồi 100 ms, client gửi request tiếp ngay sau khi nhận response.

**Đáp án:** Không nhất thiết cùng requests/giây. B có thể nhận **nhiều request hơn** do vòng closed-loop nhanh hơn. Khi so GC tại cùng offered load, phải giữ tốc độ gửi và request mix tương đương hoặc chuẩn hóa kết quả một cách rõ ràng.

### Bài 2: không Full GC trong cả hai lần thử

A và B đều hoàn thành 1 triệu operation. GC log chỉ có Young/Mixed events.

**Đáp án:** Có thể so overall throughput và Young/Mixed pauses ở điều kiện tương đương. **Không thể kết luận** Full GC song song nhanh hay chậm vì chưa có Full GC observation.

### Bài 3: `ParallelGCThreads=1` và `=4`

Đặt A là 1, B là 4 trên cùng JDK. B nhanh hơn.

**Đáp án:** Kết luận hợp lệ đầu tiên là **cấu hình B của benchmark này có kết quả tốt hơn trong điều kiện thử**. Không khẳng định ngay JEP 307 làm tốt hơn vì `ParallelGCThreads` cũng ảnh hưởng Young/Mixed GC, và ứng dụng có thể không Full GC.

### Bài 4: Full GC ít hơn nhưng p99 xấu đi

B giảm Full GC count nhưng p99 request latency tăng, error rate cũng tăng.

**Đáp án:** Chưa thể tuyên bố B tốt hơn. Đánh giá theo SLO của ứng dụng: có thể B tạo CPU contention, các pause khác kéo dài, throughput không đủ hoặc queueing tăng. Cần đo cả request metrics và GC details.

### Bài 5: dữ liệu sống không giống nhau

A và B đều heap 4 GiB. Khi Full GC, A có 3 GiB live objects, B có 1 GiB.

**Đáp án:** Mặc dù `-Xmx` bằng nhau, lượng công việc compact không tương đương. Phải xem phân bố object sống, input mix, cache và occupancy trước khi dùng pause duration để kết luận.

### Bài 6: một phép tính cải thiện

A có p99 Full GC 800 ms; B có 600 ms trên đủ mẫu và tải tương đương. Tỷ lệ thay đổi?

**Đáp án:** `(600 - 800) / 800 × 100% = -25%`: B có p99 Full GC pause thấp hơn 25%. Nhưng vẫn cần kiểm tra tổng Full GC count, tổng STW, application latency/throughput và tài nguyên trước khi gọi B là lựa chọn tốt hơn toàn hệ thống.

### Bài 7: muốn buộc Full GC để lấy dữ liệu?

Người thử nghiệm muốn thêm `System.gc()` sau mỗi 100 request vào source production, chỉ để tạo GC log.

**Đáp án:** Không phù hợp. Nó thay đổi đường vận hành và có thể gây pause không đại diện. Chọn workload/incident reproducer ở môi trường test phù hợp; để production hoạt động và đo phản ánh thực tế.

## 23. Checklist trước khi chốt một kết luận hiệu năng

1. **Câu hỏi đo** đã viết rõ: throughput, tail latency hay Full GC pause?
2. **A/B cùng workload**: offered load, endpoint mix, payload, data state, số operation.
3. **A/B cùng tài nguyên**: heap, CPU quota, RAM limit, JDK/vendor/build nếu so VM flag.
4. **Chỉ một biến thay đổi** ở thí nghiệm chính; mọi flag khác được giữ.
5. **Không nhầm closed-loop concurrency với fixed RPS**; theo dõi actual RPS và backlog.
6. **Đủ warm-up**, thời lượng đo và số lần lặp; thử ABBA để hạn chế order bias.
7. **GC log/JFR có thật**, cùng settings trong hai bên, xem đúng event `Pause Full`.
8. **Đã có Full GC samples đủ dùng chưa?** Nếu chưa, báo không đủ dữ liệu, không ép kết luận.
9. **Heap/live set và cause trước Full GC** có tương đương không?
10. **Tổng Full GC và tổng STW** cùng request p99/p99.9 được xem cùng nhau?
11. **CPU, RSS, GC workers, throttling** có làm biến đổi performance?
12. **Kết quả từ nhiều run** có nhất quán hơn noise không?
13. **Không dùng System.gc để mô phỏng Full GC tự nhiên** trong benchmark thông thường.
14. **Không nhầm cải thiện từ Java 10 JEP 307 với mọi thay đổi JDK khác**.
15. **Kết luận dựa trên SLO** và ghi rõ phạm vi áp dụng, không chỉ một con số pause.

## Kết luận

**G1 Parallel Full GC (Java 10+)** giúp song song hóa công việc Full GC vốn có thể gây **stop-the-world pause dài**, nhưng **một Full GC nhanh hơn không tự động có nghĩa toàn bộ ứng dụng nhanh hơn**.

Một phép so sánh có giá trị phải giữ **tải thực sự tương đương** — số request, hỗn hợp nghiệp vụ, kích thước dữ liệu, allocation rate, live set, heap, CPU limit, warm-up và cách đo — rồi đối chiếu **Full GC count/duration với tổng STW, throughput, p95/p99 latency và chi phí tài nguyên**. Nếu log không có Full GC, báo **không đủ dữ liệu để đánh giá Full GC**; đừng biến việc không có sự kiện thành một giá trị pause bằng 0.

Trên Java/HotSpot hiện đại, ưu tiên **tránh phát sinh Full GC** bằng việc hiểu và giảm áp lực heap, chứ không chỉ tăng số GC workers. Chỉ chốt hiệu năng khi kết quả được lặp lại và đáp ứng tiêu chí của ứng dụng.

## Tài liệu tham khảo chính thức và hiện hành

- [OpenJDK JEP 307 — Parallel Full GC for G1](https://openjdk.org/jeps/307): mốc lịch sử Java 10, mục tiêu song song hóa Full GC, rủi ro và phạm vi phép đo.
- [Oracle Java SE 26 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html): cấu trúc G1, Young/Mixed/Full, parallelism, fallback Full GC và mục tiêu latency.
- [Oracle Java SE 26 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): cách quan sát `Pause Full (G1 Compaction Pause)`, nguyên nhân Full GC và khuyến nghị tuning.
- [Oracle Java SE 26 — JVM Unified Logging (`-Xlog`)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): thu gc/phase logs và cấu hình worker/heap.
- [Oracle Java SE 26 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/): GC logs, JFR, nguyên nhân pause và cách điều tra.
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): công cụ benchmark dành cho các bài toán nano/microbenchmark có kiểm soát, warmup và fork; **không thay thế load test dịch vụ toàn hệ thống**.
- [Dev.java — The Garbage-First (G1) Garbage Collector](https://dev.java/learn/jvm/tool/garbage-collection/g1gc-overview/): mô hình G1 và đánh đổi throughput/latency trên JVM hiện đại.
