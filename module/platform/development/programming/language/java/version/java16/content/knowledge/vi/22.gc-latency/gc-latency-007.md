# Cân đối Xmx, live set và headroom cho hoạt động GC đồng thời

**Module:** JAVA_VERSION_JAVA16  
**Chương:** GC và độ trễ  
**Áp dụng:** Java 16 trở lên; các nguyên tắc sizing heap và đo hoạt động GC vẫn áp dụng trong JDK hiện đại.

Thiết lập `-Xmx` không đơn giản là chọn một con số lớn để tránh `OutOfMemoryError`. Heap phải đủ chứa các object còn sống, đồng thời để lại khoảng trống cho ứng dụng tiếp tục cấp phát trong lúc garbage collector đang đánh dấu, thu gom hoặc di chuyển object. Khoảng trống này thường được gọi là **GC headroom**.

Nếu heap chỉ vừa đủ chứa live set, collector có thể không kịp thu hồi bộ nhớ trước khi ứng dụng cần cấp phát thêm. Kết quả có thể là GC chạy liên tục, allocation stall, evacuation failure, pause tăng hoặc hết heap. Ngược lại, đặt `-Xmx` quá cao có thể làm process vượt giới hạn container vì JVM còn cần Metaspace, thread stack, direct buffer, code cache và native memory.

Một cách sizing có cơ sở cần xem đồng thời:

- **Xmx:** giới hạn tối đa của Java heap.
- **Live set:** lượng object còn được giữ sống sau khi GC thu gom phần có thể thu hồi.
- **Allocation rate:** tốc độ ứng dụng tạo object mới.
- **GC cycle duration:** thời gian collector cần để hoàn thành phần công việc đồng thời.
- **Headroom:** phần heap còn có thể dùng trong khi collector xử lý workload, bao gồm khoảng dự phòng cho burst và yêu cầu riêng của collector.

## 1. Xmx không phải là tổng bộ nhớ của process

`-Xmx` đặt giới hạn tối đa cho Java heap. Nó không giới hạn tổng RSS hoặc tổng native memory của process.

Một JVM process còn sử dụng:

| Thành phần | Ví dụ |
| --- | --- |
| Java heap | Object, array, collection và object graph của ứng dụng |
| Metaspace | Class metadata và metadata liên quan đến class loader |
| Code cache | Mã máy do JIT compiler tạo |
| Thread stacks | Stack của Java thread và native thread |
| Direct/native buffers | `ByteBuffer.allocateDirect()` và buffer từ thư viện native |
| GC và JVM native structures | Cấu trúc quản lý heap, remembered sets, compiler/runtime data |
| JNI và thư viện native | Allocation do driver, compression, database client hoặc native library thực hiện |
| Memory-mapped files | File hoặc vùng dữ liệu được map vào address space |

Vì vậy, không nên đặt `-Xmx` bằng toàn bộ memory limit của container. JVM có thể chưa chạm tới Xmx nhưng process vẫn bị hệ điều hành hoặc container runtime kết thúc do tổng memory vượt giới hạn.

### Ví dụ ngân sách container

Giả sử container có giới hạn 2 GiB. Một ngân sách minh họa có thể là:

| Hạng mục | Ngân sách |
| --- | ---: |
| Java heap tối đa (`-Xmx`) | 1.300 MiB |
| Metaspace và code cache | 180 MiB |
| Thread stacks | 100 MiB |
| Direct buffers | 120 MiB |
| GC, JIT, JNI và native libraries | 150 MiB |
| Khoảng dự phòng cho biến động và thành phần khác | 198 MiB |
| **Tổng** | **2.048 MiB** |

Đây chỉ là ví dụ lập ngân sách, không phải tỷ lệ mặc định cho mọi ứng dụng. Hãy đo từng thành phần trên workload thật. Nếu container còn chạy sidecar hoặc nhiều process, ngân sách phải tính cả những thành phần đó theo giới hạn cgroup tương ứng.

## 2. Phân biệt heap used, committed, max và live set

Các số liệu heap thường gặp không thể thay thế cho nhau:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Heap used | Dung lượng đang được object sử dụng tại thời điểm đo |
| Heap committed | Dung lượng heap JVM đã commit và sẵn sàng sử dụng |
| Heap max | Giới hạn tối đa, thường tương ứng với cấu hình `-Xmx` sau khi áp dụng ergonomics |
| Live set | Ước lượng object còn reachable sau một chu kỳ thu gom phù hợp |

Heap used trước GC bao gồm cả object sắp được thu gom. Do đó, không lấy một snapshot used bất kỳ làm live set.

Live set cũng không phải một hằng số tuyệt đối:

- Nó thay đổi theo số request đang xử lý, cache, session và dữ liệu nghiệp vụ đang được giữ.
- Một số collector thu gom theo vùng hoặc thế hệ; số liệu sau một pha GC chưa chắc đại diện toàn bộ object còn sống trên heap.
- Workload cao điểm có thể làm live set tăng tạm thời vì nhiều request và object graph cùng tồn tại.
- Cache không có giới hạn có thể làm live set tăng theo thời gian.

Trong thực tế, hãy ước lượng live set bằng số liệu sau các chu kỳ GC đại diện, kết hợp heap analysis và workload. Đo ở cả trạng thái bình thường lẫn tải cao điểm.

## 3. Live set quyết định phần heap còn lại cho GC

Giả sử heap tối đa là 1.300 MiB và live set ổn định khoảng 720 MiB. Phần còn lại là khoảng trống lý thuyết:

```text
Heap max (Xmx):                  1.300 MiB
Live set sau GC:                   720 MiB
------------------------------------------
Khoảng trống lý thuyết:            580 MiB
```

Không phải toàn bộ 580 MiB đều có thể dùng làm allocation headroom:

- G1 cần vùng trống để evacuate object khỏi collection set.
- Collector đồng thời cần thời gian để đánh dấu và thu gom trong lúc ứng dụng tiếp tục cấp phát.
- Heap có thể bị phân mảnh hoặc có vùng chưa thể tái sử dụng ngay.
- Workload có thể tạo burst allocation lớn hơn tốc độ trung bình.
- CPU throttling có thể kéo dài chu kỳ GC và làm headroom bị tiêu thụ nhanh hơn.

Vì vậy, sizing chỉ theo công thức `Xmx = live set + một ít dung lượng` thường quá lạc quan.

## 4. Allocation rate và thời gian GC đồng thời

Trong khi concurrent marking hoặc concurrent relocation đang diễn ra, ứng dụng vẫn có thể tạo object mới. Phần cấp phát phát sinh trong thời gian collector làm việc cần được tính vào headroom.

Một mô hình ước lượng hữu ích:

\[
H_{\text{required}} \approx A \times T + B
\]

Trong đó:

- \(A\): allocation rate, tính theo MiB/giây.
- \(T\): thời gian của chu kỳ GC đồng thời cần xem xét, tính bằng giây.
- \(B\): dự phòng cho burst allocation, biến động live set và nhu cầu riêng của collector.

Phần headroom khả dụng có thể ước lượng:

\[
H_{\text{available}} \approx Xmx - L - R
\]

Trong đó:

- \(L\): live set đại diện.
- \(R\): khoảng dự phòng dành cho collector, evacuation, phân mảnh hoặc phần heap không thể dùng ngay.

Đây là mô hình tư duy để kiểm tra ngân sách, không phải công thức nội bộ chính xác của mọi GC. Cách tính cụ thể phụ thuộc collector, trạng thái heap, thế hệ, region và implementation của JDK.

### Ví dụ tính headroom

Giả sử:

- `Xmx` là 1.300 MiB.
- Live set đại diện là 720 MiB.
- Dành khoảng 130 MiB làm reserve/fragmentation allowance.
- Allocation rate trong giờ cao điểm là 90 MiB/giây.
- Chu kỳ concurrent GC kéo dài 2,5 giây.
- Burst allowance là 180 MiB.

Khi đó:

\[
H_{\text{available}} \approx 1300 - 720 - 130 = 450\ \text{MiB}
\]

\[
H_{\text{required}} \approx 90 \times 2.5 + 180 = 405\ \text{MiB}
\]

Khoảng chênh còn lại chỉ khoảng 45 MiB. Đây là headroom khá mỏng; một burst lớn hơn hoặc GC cycle kéo dài có thể khiến collector thiếu thời gian để bắt kịp allocation.

Nếu CPU container bị throttling làm chu kỳ kéo dài thành 4 giây:

\[
H_{\text{required}} \approx 90 \times 4 + 180 = 540\ \text{MiB}
\]

Nhu cầu đã vượt headroom 450 MiB. Có thể cần tăng heap trong giới hạn ngân sách process, giảm allocation rate, tăng CPU quota hoặc chọn cấu hình/collector phù hợp hơn. Chỉ tăng Xmx mà bỏ qua giới hạn container có thể chuyển vấn đề thành container OOM kill.

## 5. Vì sao CPU quota ảnh hưởng tới GC headroom?

Concurrent GC cần CPU để đánh dấu object, xử lý remembered set hoặc relocation. Nếu container bị giới hạn CPU:

1. GC worker nhận ít thời gian CPU hơn.
2. Concurrent cycle kéo dài.
3. Ứng dụng vẫn tiếp tục cấp phát trong thời gian đó.
4. Headroom bị tiêu thụ nhiều hơn trước khi GC hoàn tất.
5. Collector có thể phải chạy dồn dập, allocation bị chặn hoặc pause tăng.

Đây là lý do một heap chạy tốt trên máy developer có thể thiếu headroom trong container có CPU limit thấp hơn.

Khi điều tra, không chỉ xem heap. Hãy đối chiếu:

- CPU usage và CPU throttling của container.
- Allocation rate tại cùng thời điểm.
- Thời lượng concurrent marking/relocation.
- GC worker activity và thời gian pause.
- Số request đồng thời và latency của ứng dụng.

Không mặc định tăng số GC thread là giải pháp. Thêm worker có thể cạnh tranh CPU với application thread và làm latency tổng thể xấu đi nếu CPU quota không đủ.

## 6. G1: dành chỗ cho marking và evacuation

G1 là collector mặc định trong nhiều cấu hình HotSpot server hiện đại. G1 chia heap thành region, thực hiện concurrent marking và thu gom các region theo chu kỳ. Khi evacuation, object còn sống trong collection set được copy sang region khác.

Do đó, G1 cần headroom cho hai nhu cầu:

- **Concurrent marking:** collector cần thời gian và CPU để xác định vùng nào chứa object còn sống.
- **Evacuation:** collector cần region đích đủ trống để chuyển object còn sống ra khỏi region đang thu gom.

Nếu heap gần đầy, G1 có thể thiếu to-space cho evacuation. Các dấu hiệu cần điều tra gồm evacuation failure, Full GC bất thường, pause tăng hoặc old-generation occupancy tăng liên tục.

Các nguyên tắc sizing với G1:

1. Đo live set sau các chu kỳ mixed collection đại diện, không chỉ nhìn heap used trước GC.
2. Giữ reserve đủ cho evacuation và biến động allocation.
3. Quan sát thời điểm concurrent marking bắt đầu so với tốc độ tăng occupancy.
4. Kiểm tra humongous allocation nếu object lớn chiếm nhiều region.
5. Đánh giá pause target cùng throughput và CPU cost.

`-XX:MaxGCPauseMillis` là mục tiêu heuristic cho G1, không phải cam kết mọi pause đều thấp hơn giá trị đó. Mục tiêu quá tham vọng có thể khiến collector dành nhiều tài nguyên cho GC hoặc thu gom thường xuyên hơn.

Các cờ như `-XX:G1ReservePercent` và `-XX:InitiatingHeapOccupancyPercent` có thể ảnh hưởng reserve và thời điểm bắt đầu marking. Không chỉnh chúng theo công thức chung hoặc sao chép từ máy khác. G1 có cơ chế adaptive trong các JDK hiện đại; trước khi override, cần đọc log và chứng minh default không đáp ứng workload.

## 7. ZGC: cần headroom khi relocation diễn ra đồng thời

ZGC hướng tới pause ngắn bằng cách thực hiện nhiều công việc đánh dấu và relocation đồng thời với application thread. Vì ứng dụng vẫn cấp phát trong khi collector đang làm việc, heap cần khoảng trống để duy trì tiến độ.

Nếu allocation rate cao, live set lớn và concurrent cycle kéo dài, ZGC có thể gặp allocation stall hoặc phải tăng áp lực GC. Một collector có pause ngắn không có nghĩa nó hoạt động tốt khi heap gần đầy.

Khi sizing cho ZGC:

- Đo live set ở workload cao điểm.
- Đo allocation rate theo thời gian, bao gồm burst.
- Theo dõi thời lượng concurrent cycle và các dấu hiệu allocation stall trong log/JFR.
- Đảm bảo Xmx đủ headroom mà vẫn nằm trong memory limit của process/container.
- Kiểm tra CPU quota; concurrent relocation vẫn cần CPU.

ZGC có thể phù hợp khi latency là ưu tiên cao và workload có đủ memory/CPU headroom. G1 thường là điểm xuất phát cân bằng cho nhiều ứng dụng. Shenandoah cũng là lựa chọn low-latency trên các JDK build có hỗ trợ. Hãy xác minh collector có sẵn trong bản phân phối và phiên bản JDK thực tế.

## 8. Chọn collector theo mục tiêu ứng dụng

| Collector | Đặc điểm khái quát | Điều cần chú ý khi sizing |
| --- | --- | --- |
| G1 | Cân bằng throughput và pause; collector mặc định phổ biến | Live set, region evacuation reserve, marking headroom và pause/throughput trade-off |
| ZGC | Thiết kế cho latency thấp với nhiều công việc GC đồng thời | Allocation rate trong concurrent cycle, relocation headroom, CPU và memory budget |
| Shenandoah | Low-latency collector trên các bản JDK hỗ trợ | Concurrent work, allocation headroom và chi phí CPU |
| Parallel GC | Ưu tiên throughput, dùng các pha collection dừng application thread | Tổng heap, live set, thời gian pause chấp nhận được và throughput |

Không có collector tốt nhất cho mọi ứng dụng. Một API service có latency SLO chặt có thể chọn collector khác batch processing ưu tiên throughput. Hãy so sánh trên cùng workload, cùng giới hạn CPU và memory.

## 9. Đặt Xms và Xmx như thế nào?

`-Xms` đặt kích thước heap ban đầu; `-Xmx` đặt giới hạn heap tối đa. JVM có thể điều chỉnh heap đã commit trong giới hạn cho phép theo collector và ergonomics.

Một số điểm cần cân nhắc:

- `Xms` thấp hơn `Xmx` cho JVM thêm khả năng bắt đầu với heap nhỏ và tăng dần khi cần.
- `Xms` bằng `Xmx` có thể giảm biến động resize trong workload ổn định, nhưng làm heap commitment ban đầu lớn hơn và không phải lúc nào cũng phù hợp với container.
- Đặt `Xmx` quá thấp làm giảm headroom và có thể gây GC pressure.
- Đặt `Xmx` quá cao làm giảm ngân sách dành cho native memory và các process khác trong cgroup.

Không đặt `-Xms = -Xmx` chỉ vì muốn hiệu năng ổn định. Hãy đo thời gian startup, heap commitment, RSS, GC behavior và memory limit trong môi trường triển khai thật.

## 10. Container-aware sizing và MaxRAMPercentage

Các JDK hiện đại có khả năng nhận biết giới hạn bộ nhớ container trong các môi trường được hỗ trợ. Ergonomics có thể dùng giới hạn đó để tính heap mặc định. Tuy vậy, JVM không tự biết chính xác ứng dụng cần bao nhiêu direct buffer, native allocation hoặc memory của sidecar.

`-XX:MaxRAMPercentage` cho phép điều chỉnh tỷ lệ bộ nhớ được JVM dùng để suy ra giới hạn heap tối đa khi không đặt `-Xmx` trực tiếp. Đây là tỷ lệ trên memory mà JVM nhận diện; nó không phải cam kết phần còn lại luôn đủ cho mọi native allocation.

Khi triển khai container:

1. Xác nhận JVM nhận đúng cgroup memory limit.
2. Xem `VM.flags` và heap max thực tế.
3. Đo non-heap/native memory dưới peak load.
4. Dành khoảng dự phòng cho burst, sidecar và biến động môi trường.
5. Theo dõi cả Java `OutOfMemoryError` và container OOM kill.

Container OOM kill có thể kết thúc process mà JVM không kịp phát ra `OutOfMemoryError`. Vì vậy, chỉ xem exception log của Java là chưa đủ để điều tra memory pressure.

## 11. Đo allocation rate và live set

Để sizing có cơ sở, cần thu thập dữ liệu trong workload đại diện:

| Dữ liệu | Cách quan sát | Câu hỏi cần trả lời |
| --- | --- | --- |
| Heap used/committed/max | GC log, JMX hoặc `jcmd` | Heap đang tăng ở pha nào? |
| Live set ước lượng | Occupancy sau các chu kỳ GC đại diện, heap analysis | Object nào thực sự được giữ sống? |
| Allocation rate | JFR allocation events hoặc GC telemetry | Ứng dụng tạo bao nhiêu object mỗi giây? |
| Concurrent cycle duration | GC log và JFR | Collector mất bao lâu để hoàn thành công việc đồng thời? |
| Pause duration | GC log, JFR | Pause p95/p99 có đáp ứng latency SLO không? |
| GC CPU | JFR, process/container metrics | GC có cạnh tranh CPU với application thread không? |
| Container memory/RSS | Cgroup và OS metrics | Process còn bao nhiêu khoảng trống trước memory limit? |
| Native memory | NMT nếu đã bật | Phần memory ngoài heap tăng ở nhóm nào? |

Không lấy một lần Full GC trong môi trường staging làm đại diện duy nhất cho live set production. Full GC có thể thay đổi hành vi và pause; dùng nhiều nguồn telemetry trong workload thực tế.

## 12. Bật unified GC logging

Unified logging là cách hiện hành để thu thập GC events:

```sh
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar application.jar
```

Log giúp xem:

- Heap occupancy trước/sau các pha GC.
- Thời điểm và thời lượng concurrent cycle.
- Pause duration và loại collection.
- Metaspace/heap pressure khi bật tag phù hợp.
- Dấu hiệu evacuation failure, allocation stall hoặc Full GC.

Giữ log đủ lâu để bao phủ startup, steady state và peak traffic. Cấu hình rotation/retention phù hợp để log không chiếm hết disk.

## 13. Dùng JFR và jcmd để đối chiếu

Có thể thu JFR recording trong một khoảng thời gian đại diện:

```sh
jcmd <pid> JFR.start name=gc-sizing settings=profile duration=120s filename=gc-sizing.jfr
```

JFR có thể cung cấp allocation events, GC events, pause và thông tin thread/CPU tùy recording settings và JDK. Profile recording có overhead; hãy cân nhắc môi trường và thời lượng trước khi bật ở production.

Một số lệnh hỗ trợ kiểm tra process:

```sh
jcmd <pid> GC.heap_info
jcmd <pid> VM.flags
jcmd <pid> VM.native_memory summary
```

`VM.native_memory summary` cần Native Memory Tracking đã được bật khi JVM khởi động. Đầu ra và tùy chọn có thể khác giữa các phiên bản; dùng `jcmd <pid> help` để xác minh lệnh có trên runtime đang chạy.

## 14. Quy trình sizing Xmx có thể lặp lại

Thực hiện theo thứ tự:

1. **Xác định giới hạn triển khai:** memory limit, CPU quota, số process/sidecar và latency SLO.
2. **Lập ngân sách ngoài heap:** Metaspace, code cache, stacks, direct buffers, JNI/native libraries và phần dự phòng.
3. **Đo live set:** ở steady state, peak traffic và sau các chu kỳ GC đại diện.
4. **Đo allocation rate:** lấy trung bình, percentile cao và burst ngắn.
5. **Đo thời gian concurrent cycle:** trên cùng CPU quota và workload production-like.
6. **Ước lượng headroom:** dùng allocation trong thời gian GC hoạt động cộng burst allowance và reserve phù hợp collector.
7. **Chọn collector:** dựa vào latency, throughput, CPU và memory budget.
8. **Chạy load test:** bao phủ warm-up, peak, burst và thời gian đủ dài để phát hiện xu hướng.
9. **Điều chỉnh một biến mỗi lần:** Xmx, CPU quota hoặc collector; ghi lại kết quả trước/sau.
10. **Xác minh trong container thật:** theo dõi OOM kill, RSS, GC logs và application latency.

Nếu không đủ headroom, các hướng xử lý có thể gồm tăng heap trong giới hạn process, giảm live set bằng cách giới hạn cache/session, giảm allocation rate, rút ngắn thời gian xử lý request hoặc cấp thêm CPU để GC hoàn tất concurrent cycle sớm hơn.

## 15. Dấu hiệu headroom đang thiếu

| Dấu hiệu | Khả năng cần kiểm tra |
| --- | --- |
| GC cycle gần như nối tiếp nhau | Allocation rate cao so với tốc độ thu gom |
| Old occupancy tăng sau các chu kỳ G1 | Live set lớn, marking/mixed collection không theo kịp hoặc workload giữ thêm object |
| G1 evacuation failure | Thiếu to-space/reserve hoặc heap quá chật/phân mảnh |
| ZGC allocation stall | Collector không theo kịp tốc độ cấp phát hoặc thiếu headroom |
| Pause tăng khi traffic tăng | Collection set, live data hoặc CPU pressure thay đổi |
| Container bị OOMKilled dù heap chưa chạm Xmx | Native memory, direct buffer, stacks, sidecar hoặc RSS vượt cgroup limit |
| GC CPU cao và application CPU bị throttling | GC và ứng dụng đang cạnh tranh CPU trong quota hạn chế |

Đừng phản ứng bằng cách tăng Xmx ngay. Trước hết xác định vấn đề là live set, allocation rate, concurrent cycle kéo dài, native memory hay container budget.

## 16. Những tuning không nên áp dụng máy móc

- Không đặt `Xmx` bằng memory limit container mà không tính non-heap/native memory.
- Không coi heap used trước GC là live set.
- Không đặt heap chỉ vừa đủ cho live set mà không dự phòng allocation trong concurrent cycle.
- Không giảm `MaxGCPauseMillis` quá thấp với kỳ vọng đây là SLA cứng.
- Không tăng số GC thread khi container đang bị CPU throttling mà chưa đo.
- Không sao chép `G1ReservePercent` hoặc `InitiatingHeapOccupancyPercent` từ workload khác.
- Không tăng `MaxMetaspaceSize` để chữa heap pressure; đây là giới hạn vùng metadata riêng.
- Không dùng cờ CMS/PermGen hoặc hướng dẫn GC đã bị loại bỏ trong JDK hiện đại.

Hãy bắt đầu từ ergonomics mặc định của JDK được hỗ trợ, đo bằng log/JFR, rồi chỉ thay đổi flag có giả thuyết rõ ràng và kết quả kiểm chứng.

## 17. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| `Xmx` là giới hạn tổng RAM của JVM process. | **Sai** | Nó chỉ giới hạn Java heap; native memory và các thành phần khác vẫn cần ngân sách. |
| Heap used trước GC là live set. | **Sai** | Nó bao gồm object có thể được thu gom trong chu kỳ tiếp theo. |
| Heap vừa đủ chứa live set là đủ. | **Sai** | Cần headroom cho allocation, concurrent work, burst và reserve của collector. |
| Concurrent GC cần CPU trong lúc application vẫn chạy. | **Đúng** | CPU quota thấp có thể kéo dài cycle và làm headroom bị tiêu thụ nhanh hơn. |
| G1 pause target là cam kết thời gian pause tối đa. | **Sai** | Đây là mục tiêu heuristic, không phải SLA cứng. |
| ZGC pause ngắn nghĩa là không cần heap headroom. | **Sai** | Allocation vẫn diễn ra trong lúc concurrent relocation. |
| Container OOM kill luôn tạo `OutOfMemoryError` trong Java log. | **Sai** | Kernel/container runtime có thể kết thúc process trước khi JVM phát exception. |
| RSS không giảm chứng minh GC chưa thu gom object. | **Sai** | RSS còn bao gồm committed pages, heap, stacks và native allocations khác. |

## 18. Checklist trước khi chốt Xmx

1. Đã biết memory limit và CPU quota thật của container chưa?
2. Đã dành ngân sách cho Metaspace, code cache, thread stacks, direct buffers và native libraries chưa?
3. Live set được đo sau các chu kỳ GC đại diện chưa?
4. Đã đo allocation rate ở peak và burst chưa?
5. Đã đo thời lượng concurrent cycle dưới đúng CPU quota chưa?
6. Headroom có đủ cho `allocation rate × cycle duration` cộng burst allowance không?
7. Đã tính reserve/evacuation needs phù hợp với collector chưa?
8. Đã xem cả pause, throughput, GC CPU và application latency chưa?
9. Đã phân biệt Java OOME với container OOM kill chưa?
10. Đã kiểm tra RSS và native memory khi heap chưa chạm Xmx chưa?
11. Mọi thay đổi flag có giả thuyết, log và phép đo trước/sau chưa?
12. Đã chạy lại workload peak sau khi thay đổi Xmx/collector chưa?

**Ghi nhớ:** Chọn Xmx bằng cách cân đối live set, allocation rate, thời gian concurrent GC và ngân sách memory ngoài heap. Heap phải có headroom để ứng dụng tiếp tục cấp phát trong khi G1 marking/evacuation hoặc ZGC relocation diễn ra. CPU throttling làm chu kỳ GC dài hơn và cần thêm khoảng trống. Xmx không phải giới hạn RSS; trong container, luôn dành ngân sách cho Metaspace, stacks, direct buffers, code cache và native libraries. Đo bằng GC logs, JFR, jcmd và cgroup metrics trước khi chỉnh tuning flags.

## Tài liệu chính thức

- [JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248).
- [Java SE 26 `java` Launcher — Heap size, GC selection and Unified Logging options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [Java SE 26 `jcmd` Tool — `GC.heap_info`, `VM.flags` and JFR commands](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html).
- [Java SE 26 Flight Recorder — JFR overview and configuration](https://docs.oracle.com/en/java/javase/26/jfapi/flight-recorder-configurations.html).
- [JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/333).
- [JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector, Production in Java 15](https://openjdk.org/jeps/377).
- [JEP 379 — Shenandoah: A Low-Pause-Time Garbage Collector](https://openjdk.org/jeps/379).
