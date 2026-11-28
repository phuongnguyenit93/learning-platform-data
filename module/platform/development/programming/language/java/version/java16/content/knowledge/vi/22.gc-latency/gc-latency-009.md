# G1 trả heap memory về hệ điều hành qua công việc uncommit đồng thời

Từ JDK 16, G1 có thể trả phần Java heap không còn cần thiết về hệ điều hành mà không phải thực hiện toàn bộ thao tác uncommit trong một GC pause. Thay đổi này được ghi nhận ở **JDK-8236926 — Concurrently Uncommit Memory in G1**. G1 vẫn quyết định cần thu nhỏ heap trong GC pause, nhưng chuyển phần uncommit tốn thời gian sang một luồng nền chạy đồng thời với ứng dụng và xử lý các vùng nhớ theo từng phần ngắn.

Điều này giúp giảm thời gian dừng ứng dụng khi heap cần co lại, nhất là với service có tải tăng mạnh rồi giảm, ứng dụng chạy trong container hoặc hệ thống có nhiều instance dùng chung máy. Đây là hành vi nội bộ của G1 trong HotSpot, được bật tự động từ JDK 16; ứng dụng không cần thêm một cờ riêng để kích hoạt concurrent uncommit.

## 1. Vấn đề trước JDK 16

G1 quản lý heap thành các **region** có kích thước bằng nhau. Khi ứng dụng cần nhiều bộ nhớ, JVM có thể commit thêm các vùng heap để phục vụ cấp phát. Khi nhu cầu giảm, G1 có thể quyết định thu nhỏ heap và trả phần committed không còn cần thiết về hệ điều hành.

Trước thay đổi JDK-8236926, khi G1 phát hiện heap có thể thu nhỏ trong một GC pause, thao tác trả bộ nhớ về hệ điều hành được thực hiện ngay trong pause đó. Nếu lượng memory cần uncommit rất lớn, ví dụ vài GB sau một đợt tải cao, thao tác hệ điều hành có thể kéo dài thời gian stop-the-world.

JDK 16 thay đổi cách thực hiện:

1. Trong GC pause, G1 xác định cần uncommit bao nhiêu memory và những vùng nào có thể trả lại.
2. G1 ghi nhận công việc cần thực hiện.
3. Sau pause, một luồng nền thực hiện uncommit đồng thời với các application thread.
4. Luồng nền xử lý các vùng theo từng phần nhỏ để tránh chiếm một khoảng thời gian dài ngay trước GC pause tiếp theo.

Theo ghi chú thay đổi của JDK 16, mỗi phần việc được chia nhỏ để thường chỉ mất tối đa vài mili giây. Mục tiêu là tránh một đợt uncommit lớn làm kéo dài pause.

## 2. Concurrent uncommit thay đổi điều gì?

| Khía cạnh | Trước JDK 16 | Từ JDK 16 với G1 |
|---|---|---|
| Quyết định thu nhỏ heap | Được thực hiện trong GC pause | Vẫn được thực hiện trong GC pause |
| Công việc uncommit thực tế | Có thể thực hiện ngay trong pause | Được chuyển sang luồng nền |
| Cách xử lý lượng memory lớn | Có thể làm pause dài hơn | Chia thành các phần nhỏ và xử lý đồng thời với ứng dụng |
| Cờ bật tính năng | Không có cờ riêng | Luôn bật trong G1, không cần cấu hình thêm |
| Mục tiêu | Thu nhỏ heap và trả memory | Giảm chi phí uncommit nằm trong stop-the-world pause |

Điểm quan trọng: **concurrent uncommit không biến toàn bộ GC thành concurrent**. G1 vẫn có các pha stop-the-world để xử lý object, cập nhật reference và quyết định kích thước heap. Chỉ phần uncommit memory được chuyển sang công việc nền.

## 3. Phân biệt object reclamation, heap shrink và uncommit

Ba thao tác này liên quan nhau nhưng không đồng nghĩa:

| Thao tác | Ý nghĩa |
|---|---|
| Object reclamation | GC xác định object nào không còn reachable và thu hồi vùng chứa chúng để tái sử dụng. |
| Heap shrink | G1 quyết định giảm dung lượng heap đã commit vì nhu cầu hiện tại thấp hơn. |
| Uncommit | JVM trả backing memory của các vùng heap không còn cần thiết về hệ điều hành. |

Ví dụ, sau một đợt tải cao, heap có thể đã dùng 3 GB. Khi tải giảm, GC thu hồi nhiều object và vùng trống có thể được tái sử dụng. Nếu G1 quyết định heap hiện tại lớn hơn nhu cầu dự kiến, nó có thể thu nhỏ heap và uncommit một số region trống.

Concurrent uncommit chỉ xử lý bước trả backing memory. Nó không tự làm object trở thành unreachable, không thay thế GC và không giải quyết memory leak do ứng dụng giữ reference.

## 4. Quy trình hoạt động theo từng bước

~~~mermaid
flowchart TD
    A["Ứng dụng trải qua đợt tải cao"] --> B["G1 commit thêm heap regions"]
    B --> C["Tải giảm, GC thu hồi object không còn dùng"]
    C --> D["G1 đánh giá dung lượng heap có thể thu nhỏ"]
    D --> E["GC pause: xác định regions cần uncommit"]
    E --> F["Ứng dụng tiếp tục chạy"]
    F --> G["Luồng nền uncommit theo từng phần nhỏ"]
    G --> H["Committed heap giảm dần"]
    H --> I["Hệ điều hành có thể dùng lại memory"]
~~~

Diễn giải:

1. Ứng dụng tăng tải và cấp phát nhiều object.
2. G1 mở rộng heap trong giới hạn đã cấu hình.
3. Khi tải giảm, GC thu hồi object không còn reachable.
4. G1 đánh giá tỷ lệ free heap và nhu cầu dự kiến.
5. Nếu có thể thu nhỏ heap, G1 chọn các vùng region phù hợp để uncommit.
6. GC pause kết thúc sau khi quyết định và chuẩn bị công việc.
7. Luồng nền tiếp tục uncommit các vùng đã chọn.
8. Dung lượng committed giảm và memory được trả lại cho hệ điều hành.

Thứ tự này giải thích vì sao heap committed có thể giảm sau thời điểm GC pause kết thúc. Không nên chỉ chụp một số liệu ngay sau pause rồi kết luận tính năng chưa hoạt động.

## 5. Những điều kiện ảnh hưởng đến khả năng trả memory

G1 chỉ trả được vùng heap không còn cần thiết và nằm ngoài mức heap tối thiểu mà JVM phải duy trì. Một số yếu tố quan trọng:

- **Live set:** Object còn reachable vẫn cần chỗ trong heap. Nếu ứng dụng giữ nhiều object sống, G1 không thể thu nhỏ heap xuống dưới nhu cầu đó.
- **Heap minimum:** **-Xms** hoặc **-XX:MinHeapSize** đặt mức tối thiểu. G1 không thu nhỏ heap thấp hơn giới hạn này.
- **Heap maximum:** **-Xmx** đặt mức tối đa mà heap có thể mở rộng tới; nó không phải mức heap phải luôn giữ.
- **Free heap policy:** **-XX:MinHeapFreeRatio** và **-XX:MaxHeapFreeRatio** ảnh hưởng tỷ lệ free heap mà JVM muốn giữ sau GC.
- **GC activity:** Nếu không có GC hoặc chưa đến thời điểm G1 đánh giá shrink, memory có thể tiếp tục được giữ để tái sử dụng.
- **Region layout:** Chỉ những vùng có thể trả mà không ảnh hưởng object đang sống mới đủ điều kiện uncommit.

Do đó, không thể yêu cầu G1 trả một lượng memory cố định ngay khi request rate giảm. Đây là quyết định tự động dựa trên trạng thái heap và chính sách sizing của JVM.

## 6. Cấu hình heap để G1 có không gian thu nhỏ

Nếu đặt heap tối thiểu bằng heap tối đa, G1 không có khoảng để shrink:

~~~bash
java -Xms4g -Xmx4g -jar inventory-service.jar
~~~

Đây là cấu hình heap cố định 4 GB. Nó có thể phù hợp khi ưu tiên tính ổn định của dung lượng heap hoặc muốn tránh heap resizing, nhưng không phù hợp nếu mục tiêu là trả lại phần heap dư thừa cho hệ điều hành.

Nếu muốn heap có thể tăng khi cần và giảm khi tải hạ, đặt mức ban đầu/tối thiểu thấp hơn mức tối đa:

~~~bash
java -Xms512m -Xmx4g -jar inventory-service.jar
~~~

Trong ví dụ, heap có thể khởi đầu ở khoảng 512 MB và mở rộng tới 4 GB. Khi tải giảm, G1 có thể shrink nếu trạng thái heap và chính sách sizing cho phép.

Có thể dùng **-XX:MinHeapSize** và **-XX:InitialHeapSize** riêng để tách mức tối thiểu khỏi mức khởi tạo:

~~~bash
java \
  -XX:MinHeapSize=512m \
  -XX:InitialHeapSize=1g \
  -Xmx4g \
  -jar inventory-service.jar
~~~

Chỉ đặt các giá trị này sau khi đo live set, startup footprint và peak workload. Mức tối thiểu quá thấp có thể khiến JVM phải mở rộng heap thường xuyên khi tải quay trở lại.

## 7. MinHeapFreeRatio và MaxHeapFreeRatio

Hai tùy chọn này định hướng lượng free heap mà JVM muốn giữ sau GC:

| Tùy chọn | Ý nghĩa |
|---|---|
| **-XX:MinHeapFreeRatio** | Tỷ lệ free heap tối thiểu mong muốn; nếu free heap thấp hơn, JVM có thể mở rộng heap. |
| **-XX:MaxHeapFreeRatio** | Tỷ lệ free heap tối đa mong muốn; nếu free heap vượt mức, JVM có thể thu nhỏ heap. |

Tài liệu JDK 16 ghi nhận mặc định của **MinHeapFreeRatio** là 40 và **MaxHeapFreeRatio** là 70. Không nên vội giảm các giá trị này chỉ để làm RSS thấp hơn. Khi đặt quá thấp, heap có thể liên tục co rồi nở khi tải dao động, gây thêm GC, commit/uncommit và chi phí hệ điều hành.

Ví dụ sau chỉ minh họa cách truyền giá trị:

~~~bash
java \
  -XX:MinHeapFreeRatio=20 \
  -XX:MaxHeapFreeRatio=60 \
  -Xms512m \
  -Xmx4g \
  -jar inventory-service.jar
~~~

Hãy benchmark với workload có cả giờ cao điểm và giờ thấp điểm. Mục tiêu là cân bằng memory footprint với độ ổn định khi tải tăng trở lại.

## 8. Concurrent uncommit là mặc định, không có cờ bật riêng

JDK 16 release notes xác nhận **Concurrently Uncommit Memory in G1** luôn được bật. Không cần tìm hoặc thêm một tùy chọn như **-XX:+UseConcurrentUncommit** để kích hoạt.

Điều cần cấu hình là điều kiện để heap có thể shrink:

- Không khóa heap ở cùng mức **-Xms** và **-Xmx** nếu muốn giảm footprint.
- Đặt giới hạn heap tối đa hợp lý.
- Đo và điều chỉnh free heap policy nếu có bằng chứng.
- Bảo đảm workload có thời gian giảm tải để G1 có cơ hội thu hồi và shrink.

Concurrent uncommit là một thay đổi trong cách G1 thực hiện thao tác trả memory, không phải một chế độ GC mới mà ứng dụng phải tự chọn.

## 9. Phân biệt với G1 Periodic GC khi ứng dụng idle

G1 có một tính năng khác để xử lý trường hợp ứng dụng không hoạt động trong thời gian dài: **periodic garbage collection**. Tính năng này được điều khiển bằng **-XX:G1PeriodicGCInterval**.

Hai cơ chế có mục đích khác nhau:

| Cơ chế | Mục đích |
|---|---|
| Concurrent uncommit từ JDK 16 | Chuyển công việc uncommit heap đã được quyết định sang luồng nền để giảm thời gian pause. |
| Periodic GC | Tạo thêm cơ hội GC trong giai đoạn ứng dụng idle lâu, khi bình thường không có allocation để kích hoạt GC. |

Nếu ứng dụng idle nhiều giờ và không có GC nào diễn ra, heap có thể vẫn giữ memory committed dù nhiều object không còn cần thiết. Periodic GC giúp G1 kiểm tra và thu hồi vùng memory trong những khoảng idle đó.

Ví dụ cấu hình:

~~~bash
java \
  -XX:G1PeriodicGCInterval=300000 \
  -jar inventory-service.jar
~~~

Giá trị **300000** tương đương 5 phút. Đây là khoảng thời gian tối thiểu G1 dùng để xem xét periodic GC sau khi phát hiện trạng thái idle và kể từ GC pause trước đó. Đây không phải cam kết cứ đúng 5 phút sẽ có một GC hoặc RSS sẽ giảm ngay.

Theo tài liệu HotSpot hiện hành:

- **-XX:G1PeriodicGCInterval=0** là mặc định và tắt periodic GC.
- **-XX:+G1PeriodicGCInvokesConcurrent** là mặc định; periodic GC có thể bắt đầu concurrent marking hoặc tiếp tục chu kỳ đang diễn ra.
- Nếu dùng **-XX:-G1PeriodicGCInvokesConcurrent**, periodic GC có thể thực hiện Full GC, làm tăng rủi ro pause dài.
- **-XX:G1PeriodicGCSystemLoadThreshold** có thể ngăn periodic GC khi system load vượt ngưỡng; giá trị 0.0 tắt kiểm tra ngưỡng này.

Chỉ cân nhắc periodic GC khi ứng dụng thực sự có khoảng idle dài và cần nhường memory cho workload khác. Không bật chu kỳ GC dày đặc trên service luôn bận nếu chưa đo tác động.

## 10. Quan sát heap shrink và uncommit bằng GC logging

Unified logging giúp theo dõi heap và hoạt động GC. Bắt đầu với:

~~~bash
java \
  -Xlog:gc+heap=debug \
  -Xlog:gc=info \
  -Xms512m \
  -Xmx4g \
  -jar inventory-service.jar
~~~

Trong giai đoạn điều tra, có thể ghi log ra file:

~~~bash
java \
  '-Xlog:gc=info,gc+heap=debug:file=logs/gc-heap.log:time,uptime,level,tags:filecount=5,filesize=20m' \
  -Xms512m \
  -Xmx4g \
  -jar inventory-service.jar
~~~

Đọc log để xác định:

- Loại GC và nguyên nhân kích hoạt.
- Heap used trước và sau GC.
- Heap capacity/region count thay đổi theo thời gian.
- Thông tin G1 quyết định shrink heap.
- Thông tin về concurrent uncommit hoặc concurrent heap memory work nếu runtime phát ra ở mức log đã chọn.
- Thời gian pause và thời điểm công việc nền tiếp tục.

Chi tiết câu chữ trong log có thể thay đổi theo JDK vendor và release. Dùng **-Xlog:gc*=debug** trong môi trường điều tra khi cần nhiều chi tiết hơn, nhưng lưu ý lượng log có thể lớn. Không nên bật mức debug rộng trên toàn bộ production mà không có giới hạn file và thời gian.

## 11. Đối chiếu heap committed với bộ nhớ process

Để xác nhận memory đã được trả, cần nhìn nhiều lớp số liệu:

| Số liệu | Cho biết điều gì? |
|---|---|
| Heap used | Lượng object đang chiếm heap theo góc nhìn JVM. |
| Heap committed/capacity | Dung lượng heap đã được commit và có thể dùng để cấp phát. |
| Heap max | Mức tối đa được cấu hình hoặc JVM cho phép. |
| RSS của process | Trang memory đang resident theo cách hệ điều hành tính. |
| Container memory | Lượng memory cgroup tính cho container, có thể gồm nhiều thành phần ngoài heap. |

Lệnh kiểm tra JVM:

~~~bash
jcmd -l
jcmd 12345 GC.heap_info
jcmd 12345 VM.flags
~~~

Thay **12345** bằng PID thực tế. **GC.heap_info** cung cấp trạng thái heap tại thời điểm lấy mẫu; **VM.flags** giúp xác minh các giá trị heap và GC option.

Trên Linux, có thể kiểm tra RSS của process:

~~~bash
grep -E 'VmRSS|VmSize' /proc/12345/status
~~~

Trong container cgroup v2, có thể xem:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
~~~

Các đường dẫn cgroup có thể khác theo runtime/container orchestrator. Với Windows, dùng Performance Monitor hoặc công cụ process monitor để theo dõi Working Set và Private Bytes.

### 11.1. Vì sao heap committed giảm nhưng RSS chưa giảm tương ứng?

RSS có thể không giảm cùng thời điểm hoặc cùng số byte với heap committed:

- OS accounting và memory page reclaim có độ trễ riêng.
- Process vẫn dùng native memory cho Metaspace, code cache, thread stack, direct buffer và JNI.
- Một số page hoặc mapping khác vẫn resident.
- Heap có thể đã uncommit nhưng process vẫn có vùng address space reserved.
- Memory của container bao gồm cả tiến trình phụ và page cache tùy cách đo.

Vì vậy, hãy xác nhận cả GC log, heap committed và số liệu hệ điều hành. Không kết luận concurrent uncommit thất bại chỉ vì RSS không giảm ngay về một giá trị cụ thể.

## 12. Ví dụ: service tăng tải rồi trở về trạng thái idle

Giả sử một service khởi động với heap tối thiểu 512 MB và tối đa 4 GB:

~~~bash
java -Xms512m -Xmx4g -jar inventory-service.jar
~~~

Trong giờ cao điểm, service nạp dữ liệu và xử lý nhiều request:

~~~text
Heap max       = 4 GB
Heap committed = 3.5 GB
Heap used      = 2.8 GB
~~~

Sau giờ cao điểm, request giảm và một phần object không còn reachable:

~~~text
Heap committed = 3.5 GB
Heap used      = 450 MB
~~~

G1 có thể quyết định thu nhỏ heap dựa trên trạng thái này và chính sách sizing. Trong GC pause, G1 xác định các vùng cần uncommit. Sau khi ứng dụng chạy tiếp, luồng nền thực hiện uncommit từng phần.

Kết quả có thể quan sát theo thời gian:

| Thời điểm | Heap used | Heap committed | Ý nghĩa |
|---|---:|---:|---|
| Đỉnh tải | 2.8 GB | 3.5 GB | Heap đã mở rộng để phục vụ tải. |
| Sau khi GC thu hồi object | 450 MB | 3.5 GB | Nhiều object đã được thu hồi, nhưng heap chưa shrink xong. |
| Trong lúc concurrent uncommit | 450 MB | 2.4 GB | Luồng nền đang trả các vùng không cần thiết. |
| Khi ổn định | 450 MB | 1.2 GB | Heap committed đã giảm, vẫn còn headroom cho tải tiếp theo. |

Số liệu trên chỉ minh họa. Kết quả thực tế phụ thuộc live set, region layout, heap minimum, free heap policy và workload.

## 13. Ảnh hưởng đến latency và throughput

Concurrent uncommit được thiết kế để giảm phần công việc trả memory nằm trong stop-the-world pause. Lợi ích có thể thấy rõ khi heap cần shrink một lượng lớn sau tải cao.

Tuy nhiên, nó không miễn phí:

- Luồng nền vẫn sử dụng CPU và tài nguyên hệ điều hành.
- Uncommit có thể cạnh tranh tài nguyên với ứng dụng trong thời điểm tải tăng trở lại.
- Nếu heap liên tục nở rồi co, hệ thống có thể phát sinh commit/uncommit lặp lại.
- Memory trả về quá sớm có thể khiến JVM phải commit lại khi workload tăng.
- GC pause do marking, evacuation, reference processing hoặc Full GC vẫn tồn tại.

Do đó, không nên tối ưu riêng số RSS thấp nhất. Hãy đánh giá đồng thời:

- p95/p99 request latency.
- GC pause duration và frequency.
- Heap committed và RSS theo thời gian.
- CPU usage của application và GC.
- Tần suất commit/uncommit trong workload dao động.

## 14. Tác động trong container và môi trường nhiều JVM

Concurrent uncommit hữu ích khi nhiều service chia sẻ cùng node. Khi một service giảm tải, memory heap dư có thể được trả lại để service khác hoặc tiến trình khác sử dụng.

Trong container:

- **-Xmx** cần phù hợp với memory limit của container.
- **-Xms** không nên đặt quá cao nếu muốn heap co lại khi idle.
- Tính cả Metaspace, thread stack, direct buffer, code cache, GC structures và native library vào budget.
- Theo dõi cgroup memory cùng heap committed; không dùng heap used làm đại diện cho tổng memory.
- Kiểm thử khi tải quay lại ngay sau giai đoạn uncommit để xem chi phí commit lại và ảnh hưởng latency.

Nếu nhiều JVM cùng dùng chung node, việc một JVM trả memory có thể giúp node tránh OOM kill khi workload của JVM khác tăng.

## 15. Cách kiểm thử concurrent uncommit

Để kiểm thử có thể lặp lại, tạo workload có hai pha rõ ràng:

1. **Pha tải cao:** cấp phát đủ object để heap tăng gần tới peak dự kiến.
2. **Pha giảm tải:** ngừng cấp phát lớn, bỏ reference tới object tạm và để ứng dụng trở về trạng thái idle.
3. Thu thập GC log và heap metrics trong cả hai pha.
4. So sánh heap committed trước và sau khi G1 shrink.
5. Đối chiếu RSS/process memory và container memory.
6. Lặp lại nhiều chu kỳ để xem heap có dao động quá mức hay không.

Ma trận tối thiểu:

| Test | Cấu hình | Mục tiêu |
|---|---|---|
| T01 | **-Xms512m -Xmx4g** | Xác nhận heap có thể tăng rồi shrink khi tải giảm. |
| T02 | **-Xms4g -Xmx4g** | Xác nhận mức heap tối thiểu cố định ngăn shrink xuống thấp hơn 4 GB. |
| T03 | **-Xms512m -Xmx4g** với workload dao động | Đo tác động của commit/uncommit lặp lại. |
| T04 | Container memory limit | Xác nhận memory được trả và node/container có headroom. |
| T05 | Periodic GC bật trong service idle dài | Đánh giá liệu cần GC định kỳ để tạo cơ hội shrink khi không có GC tự nhiên. |

Không dùng **System.gc()** trong ứng dụng production để ép shrink. Trong bài kiểm thử cô lập, có thể dùng thao tác GC có kiểm soát để tạo tình huống thử nghiệm, nhưng phải ghi rõ đây không phải hành vi workload tự nhiên.

## 16. Khi nào cần G1PeriodicGCInterval?

Nếu ứng dụng thường xuyên idle trong thời gian dài, G1 có thể không chạy GC vì không có allocation đủ để kích hoạt chu kỳ mới. Khi đó memory đã có thể thu hồi vẫn còn nằm trong heap committed.

**-XX:G1PeriodicGCInterval** cho phép G1 xem xét periodic GC trong các khoảng idle:

~~~bash
java \
  -XX:G1PeriodicGCInterval=300000 \
  -XX:+G1PeriodicGCInvokesConcurrent \
  -Xms512m \
  -Xmx4g \
  -jar inventory-service.jar
~~~

Trong cấu hình này:

- G1 kiểm tra periodic GC theo khoảng tối thiểu 5 phút khi xác định ứng dụng idle.
- **G1PeriodicGCInvokesConcurrent** giữ hành vi concurrent marking cho periodic GC khi cần.
- Sau GC, nếu G1 quyết định heap có thể shrink, concurrent uncommit của G1 xử lý phần trả memory.

Đây là hai bước phối hợp nhưng khác chức năng: periodic GC tạo cơ hội thu hồi object và đánh giá heap trong thời gian idle; concurrent uncommit thực hiện phần trả vùng committed đã được quyết định.

## 17. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Concurrent uncommit làm toàn bộ GC chạy nền. | Chỉ phần uncommit được chuyển sang luồng nền; G1 vẫn có stop-the-world pause. |
| G1 sẽ trả memory ngay sau khi request giảm. | G1 cần cơ hội GC, đánh giá heap và thực hiện uncommit; không có cam kết thời điểm tức thì. |
| **-Xmx** là dung lượng heap luôn được giữ. | **-Xmx** là giới hạn trên; heap có thể nhỏ hơn nếu mức tối thiểu và chính sách cho phép. |
| **-Xms** không ảnh hưởng khả năng shrink. | **-Xms** đặt minimum và initial heap size; đặt quá cao sẽ giữ mức heap tối thiểu cao. |
| Heap used giảm thì RSS phải giảm bằng đúng lượng đó. | Heap used, committed và RSS đo các khía cạnh khác nhau. |
| Cần cờ riêng để bật concurrent uncommit. | Tính năng JDK 16 của G1 luôn bật. |
| **G1PeriodicGCInterval** bật concurrent uncommit. | Nó kích hoạt periodic GC khi idle; concurrent uncommit là thay đổi riêng của G1 từ JDK 16. |
| **System.gc()** là cách vận hành để thu nhỏ heap. | Đây không phải chiến lược production ổn định; hãy dựa vào GC policy và workload. |
| RSS không giảm ngay nghĩa là G1 không uncommit. | Cần đối chiếu heap committed, GC log và memory accounting của OS/container. |

## 18. Quy trình tuning đề xuất

1. Bắt đầu với G1 default và một **-Xmx** phù hợp.
2. Chọn **-Xms** theo startup footprint và mức heap tối thiểu thực tế.
3. Giữ khoảng cách giữa heap minimum và maximum nếu cần co giãn.
4. Đo live set sau warm-up và sau giờ cao điểm.
5. Bật GC logging phù hợp để quan sát heap sizing và concurrent uncommit.
6. Đối chiếu heap committed với RSS và cgroup memory.
7. Nếu heap không shrink, kiểm tra **-Xms**/**MinHeapSize**, free heap policy, live set và thời điểm GC.
8. Nếu service idle dài mà không có GC, cân nhắc periodic GC sau khi đo chi phí.
9. Thử tải tăng trở lại sau khi heap đã uncommit để đo commit latency và request p99.
10. Chỉ thay đổi **MinHeapFreeRatio**/**MaxHeapFreeRatio** khi số liệu cho thấy chính sách mặc định không phù hợp.

## 19. Cách áp dụng trong Java hiện đại

- Concurrent uncommit của G1 là tính năng được bật mặc định từ JDK 16 qua thay đổi JDK-8236926.
- G1 vẫn quyết định shrink heap trong GC pause; luồng nền thực hiện uncommit từng phần sau đó.
- Dùng khoảng cách hợp lý giữa **-Xms**/**MinHeapSize** và **-Xmx** nếu muốn heap trả memory khi tải giảm.
- Không đặt **-Xms** bằng **-Xmx** khi mục tiêu là giảm heap committed trong giai đoạn idle.
- Theo dõi heap used, heap committed, RSS và cgroup memory riêng biệt.
- Dùng **-Xlog:gc+heap=debug**, **jcmd GC.heap_info** và công cụ hệ điều hành để kiểm chứng.
- Chỉ dùng **G1PeriodicGCInterval** khi ứng dụng idle dài và cần thêm cơ hội GC; đây là tính năng riêng với concurrent uncommit.
- Đánh giá p95/p99 latency và CPU khi tải tăng trở lại, không chỉ nhìn mức memory giảm.
- Không dựa vào **System.gc()** làm giải pháp vận hành.

Concurrent uncommit giúp G1 giảm công việc trả heap memory nằm trong GC pause. Khi heap được phép co giãn, ứng dụng có thể nhường lại memory dư thừa cho hệ điều hành mà không phải thực hiện toàn bộ thao tác uncommit trong một lần dừng dài. Muốn tận dụng hiệu quả, cần cấu hình heap minimum hợp lý, đo workload thực tế và xác nhận bằng cả GC log lẫn số liệu memory của hệ điều hành.

## Tài liệu tham khảo

- [Oracle JDK 16 — Consolidated Release Notes: Concurrently Uncommit Memory in G1](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [JDK-8236926 — Concurrently Uncommit Memory in G1](https://bugs.java.com/bugdatabase/view_bug.do?bug_id=JDK-8236926)
- [Thomas Schatzl — JDK 16 G1/Parallel GC Changes](https://tschatzl.github.io/2021/03/12/jdk16-g1-parallel-gc-changes.html)
- [Oracle JDK 16 — The java Command: Heap Sizing Options](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [Oracle JDK 26 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html)
- [Oracle JDK 26 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
