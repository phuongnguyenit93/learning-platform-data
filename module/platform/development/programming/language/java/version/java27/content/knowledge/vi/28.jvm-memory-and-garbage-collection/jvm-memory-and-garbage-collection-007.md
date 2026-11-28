# G1 và các tham số điều chỉnh theo mục tiêu ứng dụng

Một ứng dụng Java có thể có thời gian đáp ứng trung bình rất tốt nhưng đôi lúc xuất hiện yêu cầu chậm bất thường; một ứng dụng xử lý hàng triệu bản ghi mỗi giờ có thể đạt throughput cao nhưng tiêu thụ CPU đáng kể cho thu gom rác. **G1 GC** (*Garbage-First Garbage Collector*) là bộ thu gom rác mặc định trong phần lớn cấu hình Java HotSpot hiện đại và là điểm khởi đầu hợp lý cho nhiều ứng dụng Java 27.

Điều chỉnh G1 không phải cuộc thi đặt thật nhiều `-XX` flags. Mục tiêu là **đạt yêu cầu của ứng dụng** với mức sử dụng CPU, RAM và chi phí vận hành chấp nhận được. Trước khi thay một thông số, phải biết liệu vấn đề thực sự nằm ở GC, ở việc cấp phát quá nhiều đối tượng, kết nối ngoài, lock contention hay ở bộ nhớ ngoài Java heap.

Bài này thuộc chương **JVM, bộ nhớ và thu gom rác** của module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung bám Java SE 27/HotSpot và tài liệu G1 hiện hành: mục tiêu thời gian dừng, heap sizing, cơ chế phân vùng heap, logging, chẩn đoán Full GC, humongous objects, concurrent marking, thử nghiệm có kiểm chứng. Theo yêu cầu chỉ dùng kiến thức còn áp dụng, bài **không khuyến nghị** các GC flags đời cũ như một bộ cấu hình cố định sao chép giữa dự án.

## 1. Bắt đầu từ mục tiêu ứng dụng, không từ danh sách flags

Trước khi cấu hình JVM, mô tả điều cần cải thiện bằng một tiêu chí **đo được**:

| Mục tiêu | Chỉ số nên theo dõi | Ví dụ tiêu chí minh họa |
| --- | --- | --- |
| **Latency/tail latency** | p95/p99/p99.9 thời gian đáp ứng, số và độ dài GC pauses | p99 API dưới 250 ms ở tải mục tiêu |
| **Throughput** | Requests/giây, jobs/giờ, CPU/đơn vị công việc | Xử lý nhiều hơn 15% jobs với cùng tài nguyên |
| **Bộ nhớ** | Java heap live set, used/committed heap, RSS/container memory | Chạy ổn trong memory limit đã cấp |
| **Độ ổn định** | Full GC, `OutOfMemoryError`, evacuation failure, restart | Không xảy ra Full GC do thiếu vùng cấp phát dưới tải mục tiêu |
| **Chi phí** | CPU-hours, memory/replica, số replicas cần để đáp ứng SLA | Không tăng chi phí quá mức so với hiệu quả |

Các con số là **ví dụ cách đặt mục tiêu**, không phải khuyến nghị chung cho mọi hệ thống.

### 1.1. Đừng đánh đồng GC pause với toàn bộ response time

Một yêu cầu mất 500 ms có thể do nhiều nguyên nhân:

```text
Request latency
    |
    +-- Chờ connection pool / database
    +-- Chờ mạng / downstream
    +-- Lock contention / scheduler delay
    +-- Business logic / allocation
    +-- JVM safepoint và GC pause
    +-- Các phần khác
```

`-XX:MaxGCPauseMillis=100` là **mục tiêu mềm** của G1, **không phải** cam kết “mọi request dưới 100 ms” hoặc “không GC nào được dừng quá 100 ms”. Phải so thời điểm slow requests với GC logs, traces và metrics trước khi quy trách nhiệm cho GC.

### 1.2. Ba mục tiêu có thể xung đột

- Giảm pause bằng cách thu gom mỗi lần ít việc hơn có thể làm **GC diễn ra thường xuyên hơn**, tăng tổng chi phí.
- Tăng heap có thể giảm áp lực thu gom nhưng tăng **memory footprint** và thay đổi hành vi các chu kỳ đánh dấu.
- Tối ưu throughput cực đại có thể chấp nhận **pause dài hơn**, không phù hợp dịch vụ online có SLO latency chặt.

Vì vậy, không có một bộ GC flags tối ưu cho tất cả workloads.

## 2. G1 là bộ thu gom rác như thế nào trong Java 27?

G1 là collector **generational**, chia heap thành nhiều **regions**, thu gom theo từng phần và dùng các pha **parallel/concurrent**. Nó cố cân bằng throughput với những khoảng dừng *stop-the-world* tương đối ngắn, có khả năng đáp ứng một pause-time goal với xác suất cao — **không phải collector real-time**.

Java SE 27 liệt kê G1 là collector mặc định; có thể chọn tường minh:

```shell
java -XX:+UseG1GC -jar app.jar
```

Trong phần lớn trường hợp, không cần thêm `-XX:+UseG1GC` nếu JVM đã chọn G1. Với môi trường đóng gói, cấu hình CPU/RAM rất hạn chế hoặc nhà phân phối JVM khác, hãy **xác minh collector thực sự đang dùng** thay vì đoán.

### 2.1. G1 chia heap thành regions

Thay vì coi young và old là các khoảng liên tục cố định theo kiểu minh họa cũ, G1 chia heap thành những vùng có cùng kích thước và gán vai trò:

```text
Java heap (minh họa, không phải vị trí vật lý cố định)

+------+------+------+------+------+------+------+------+
| Eden | Old  | Free | Surv | Eden | Old  | Humo | Humo |
+------+------+------+------+------+------+------+------+
| Free | Eden | Old  | Eden | Surv | Free | Old  | Free |
+------+------+------+------+------+------+------+------+

Eden/Surv -> young generation
Old       -> old generation
Humo      -> vùng dành cho humongous object
Free      -> region chưa được gán
```

- **Eden regions:** nơi cấp phát phần lớn đối tượng mới.
- **Survivor regions:** lưu những đối tượng còn sống qua các lần young collection.
- **Old regions:** giữ những đối tượng sống lâu hoặc được promote.
- **Humongous regions:** dành cho các đối tượng đủ lớn so với region; có hành vi cấp phát/thu hồi khác.
- **Free regions:** vùng có thể được gán lại khi cần.

Region là đơn vị quản lý/thu hồi của G1. G1 dùng **evacuation**: sao chép đối tượng còn sống từ vùng được chọn sang vùng khác, nhờ đó tạo vùng trống và giảm phân mảnh đối với các đối tượng được di chuyển.

### 2.2. Region size là tham số chuyên sâu

`-XX:G1HeapRegionSize` quyết định kích thước một region. HotSpot thường tự chọn theo kích thước heap và môi trường để cân đối số regions và chi phí quản lý.

Không nên chọn region size chỉ vì nhìn thấy heap lớn. Kích thước region ảnh hưởng ít nhất tới **số regions, remembered sets, ngưỡng humongous object** và lượng live data phải xử lý khi evacuation. Điều chỉnh nó có thể giúp một số trường hợp đặc biệt nhưng làm kém trường hợp khác.

## 3. Chu kỳ hoạt động: young collections, concurrent marking và mixed collections

G1 luân phiên giữa giai đoạn tập trung vào young generation và giai đoạn dọn các old regions được chọn:

```text
Ứng dụng cấp phát đối tượng
          |
          v
   Young GC (evacuation, STW)
          |
          +---- Đối tượng sống lâu -> Old
          |
          v
  Old occupancy tới ngưỡng khởi động
          |
          v
   Concurrent Start young GC
          |
          v
  Concurrent Marking (có các pause Remark/Cleanup)
          |
          v
    Mixed GCs (young + old regions được chọn)
          |
          v
     Trở lại chu kỳ young-only
```

### 3.1. Các tên sự kiện trong log

| Sự kiện/pha | Ý nghĩa chính | Điều cần quan sát |
| --- | --- | --- |
| **Young GC / G1 Evacuation Pause** | Thu gom young regions trong stop-the-world pause | Tần suất, pause, lượng dữ liệu sống và promotion |
| **Concurrent Start** | Young GC khởi động concurrent marking | Có bắt đầu đủ sớm so với tốc độ tăng old? |
| **Concurrent Mark** | Phân tích đối tượng còn sống, phần lớn chạy cùng ứng dụng | CPU và thời gian hoàn tất chu kỳ |
| **Remark/Cleanup** | Những điểm dừng/hoàn tất thông tin marking | Pause riêng, reference processing |
| **Mixed GC** | Thu gom young và một số old regions được lựa chọn | Hiệu quả thu hồi old, độ dài pause |
| **Full GC** | Phương án dự phòng, compact toàn heap khi cần | Dấu hiệu nghiêm trọng nếu dài/lặp ở tải bình thường |

**Không kết luận cứ thấy Young GC liên tục là lỗi.** G1 được thiết kế cho các chu kỳ thu gom thường xuyên với nhiều ứng dụng cấp phát lớn. Vấn đề là GC có làm vượt SLO, tiêu tốn quá nhiều CPU hoặc không giải phóng được không gian cần thiết hay không.

### 3.2. Concurrent không có nghĩa không bao giờ stop-the-world

G1 thực hiện một phần công việc **đồng thời với các application threads**, nhưng vẫn có những pha **stop-the-world** khi dọn vùng và cập nhật tham chiếu. Nếu cần mức pause cực thấp hơn đặc tính phù hợp của G1, có thể thử nghiệm collector khác như ZGC theo tài liệu Java 27, nhưng phải so đo throughput và memory footprint. Không xem một collector là “tốt hơn tuyệt đối”.

## 4. Tuning theo bằng chứng: thu baseline trước

Một vòng tuning tối thiểu phải ghi nhận:

1. **Phiên bản JDK**, vendor và build cụ thể.
2. **GC được chọn** cùng flags thực sự đang chạy.
3. **CPU/RAM quota** của máy/container và số replicas.
4. **Số request/concurrent tasks**, kích thước payload, allocation rate.
5. **Response-time percentiles**, throughput và error rate.
6. **Heap used/committed, live set**, pause distribution, Full GC count.
7. **GC log/JFR và application traces** trên cùng khung thời gian.

Ví dụ đo baseline:

```shell
java -Xmx2g -Xlog:gc*:file=gc-baseline.log:time,uptime,level,tags:filecount=5,filesize=10M -jar app.jar
```

`-Xmx2g` chỉ là **giá trị giả định** minh họa. Lựa chọn thực phải xét giới hạn bộ nhớ của môi trường. `-Xlog:gc*` bật **unified GC logging** của JVM hiện đại; cú pháp file rotation giữ nhiều file với giới hạn kích thước để tránh log tăng vô hạn.

### 4.1. Đo dưới tải đại diện

Không tuning dựa vào vài giây startup hoặc một kịch bản chạy trên laptop nếu ứng dụng production có traffic bursts, cache warming, batch jobs và số CPUs khác hẳn.

Giữ ổn định khi so sánh A/B:

- Cùng phiên bản JDK/driver/framework.
- Cùng dữ liệu đầu vào, workload, concurrency và warm-up.
- Cùng CPU/memory limits, số replicas và network/DB conditions.
- Cùng thời lượng đo đủ để xuất hiện các chu kỳ marking/mixed collection nếu workload cần.

Nếu đổi application code, heap size và GC flags **cùng lúc**, sẽ không biết yếu tố nào gây thay đổi.

## 5. Hai nút điều chỉnh đầu tiên: `-Xmx` và `-Xms`

Theo hướng dẫn G1 Java 27, hãy **bắt đầu với defaults** rồi xem xét giới hạn heap và pause goal. `-Xmx` xác định heap tối đa; `-Xms` xác định kích thước ban đầu. Chúng không đại diện cho toàn bộ memory của JVM process.

```shell
# Ví dụ: heap ban đầu 512 MiB, tối đa 2 GiB.
java -Xms512m -Xmx2g -jar app.jar
```

| Thay đổi | Tác động có thể có | Rủi ro/đánh đổi |
| --- | --- | --- |
| **Tăng `-Xmx`** | Thêm chỗ cho live set, allocation bursts và marking; có thể giảm áp lực GC | Dùng nhiều RAM hơn, có thể làm tăng footprint và chi phí |
| **Giảm `-Xmx`** | Giảm trần heap, có thể giúp mật độ triển khai nếu workload chịu được | GC dày hơn, thiếu evacuation space, Full GC hoặc `OutOfMemoryError` |
| **Tăng `-Xms`** | Hạn chế một số lần mở rộng heap khi tải tăng | Commit/resident memory sớm hơn |
| **`-Xms = -Xmx`** | Có thể giảm biến động do heap resizing | Giữ bộ nhớ lớn ngay cả lúc nhàn rỗi, không phù hợp mọi container |

Đừng nghĩ “đặt heap càng lớn càng tốt”. Với mục tiêu cân bằng chi phí, phải đo live set và GC behavior trước khi cấp thêm bộ nhớ.

### 5.1. `-XX:+AlwaysPreTouch` không phải mặc định bắt buộc

Một cấu hình cần ổn định độ trễ có thể thử:

```shell
java -Xms2g -Xmx2g -XX:+AlwaysPreTouch -jar app.jar
```

`AlwaysPreTouch` yêu cầu JVM chạm các trang bộ nhớ lúc khởi động, chuyển một phần chi phí liên quan đến backing memory sang startup. **Đánh đổi:** tăng startup time và mức cam kết/resident memory; có thể bất lợi cho autoscaling, cold starts hoặc hệ thống bị giới hạn RAM chặt.

Đừng tự thêm `AlwaysPreTouch` chỉ vì đó là một flag “tối ưu GC” thường xuất hiện trong tài liệu tuning cũ. Hãy đo thời gian khởi động, RSS và latency thực tế.

## 6. `-XX:MaxGCPauseMillis`: mục tiêu mềm, không phải SLA

G1 dùng mô hình dự báo thời gian xử lý trong mỗi pause để chọn lượng vùng sẽ thu gom và điều chỉnh kích thước young generation. Flag chính để diễn đạt mục tiêu là:

```shell
# Ví dụ: G1 cố hướng tới GC pause khoảng 150 ms.
java -Xmx2g -XX:MaxGCPauseMillis=150 -jar app.jar
```

Theo tài liệu Java SE 27, mặc định G1 dùng **`-XX:MaxGCPauseMillis=200`** (mili giây). Đây là **soft goal**: G1 cố đạt theo mô hình và dữ liệu lịch sử, nhưng một pause cụ thể có thể vượt ngưỡng vì lượng đối tượng sống, reference processing, system time, Full GC hoặc yếu tố khác.

### 6.1. Hạ pause goal không phải lúc nào cũng tăng chất lượng

Giả sử một dịch vụ có p99 latency 400 ms và GC pauses thường 30 ms. Đổi pause goal từ 200 xuống 50 ms **chưa chắc cải thiện** p99, vì nghẽn thực tế có thể nằm ở SQL/HTTP hoặc application locking.

Khi giảm mục tiêu pause:

- G1 có thể **giảm số young regions** trong mỗi collection.
- Tần suất young collection có thể tăng.
- Tổng công việc GC/CPU và throughput có thể bị ảnh hưởng.
- Nếu mục tiêu thấp hơn khả năng thực tế của workload/hardware, G1 không thể bảo đảm đạt.

### 6.2. Tăng pause goal cũng có mục đích

Với batch job ưu tiên throughput, có thể thử:

```shell
java -Xmx2g -XX:MaxGCPauseMillis=300 -jar BatchMain
```

Cho G1 một khoảng pause mục tiêu rộng hơn **có thể** giúp nó thu gom nhiều vùng hơn mỗi lần và giảm một số overhead. Nhưng tăng từ 200 lên 300 ms **không bảo đảm** batch chạy nhanh hơn; cần benchmark thời gian hoàn thành và CPU/GC cost thực tế.

### 6.3. Pause target khác khoảng cách giữa các lần GC

`MaxGCPauseMillis` điều khiển mục tiêu **độ dài** dừng GC, không trực tiếp đặt “mỗi phút chỉ được GC một lần”. Tài liệu G1 còn mô tả một số điều chỉnh chuyên sâu về mật độ các pauses theo thời gian; chỉ nghiên cứu khi log cho thấy nhiều GC pauses xuất hiện liền nhau và thực sự gây vấn đề.

## 7. Đừng cố định young generation khi đang dùng pause goal của G1

Một sai lầm hay gặp là lấy cấu hình của collector khác rồi thêm:

```shell
# Không dùng làm bộ cấu hình G1 mặc định:
# -Xmn512m
# -XX:NewRatio=2
# -XX:NewSize=512m -XX:MaxNewSize=512m
```

Những lựa chọn này có thể **giới hạn hoặc cố định young generation**, khiến G1 mất đi phương tiện quan trọng để điều chỉnh công việc nhằm đạt pause goal. Hướng dẫn G1 Java 27 khuyến nghị **để young generation được JVM tự quyết định**, trừ khi đã đo chính xác trường hợp bất thường.

G1 điều chỉnh young generation qua vùng Eden/Survivor theo hành vi workload, không theo một công thức cố định “young luôn là 1/3 heap”. Với ứng dụng có allocation rate thay đổi, tự động thích nghi thường hiệu quả hơn một cấu hình cứng.

**Không có nghĩa mọi flag liên quan young generation đều đã bị xóa khỏi JVM**; vấn đề là **không nên dùng chúng như tối ưu mặc định của G1**, vì ảnh hưởng tới khả năng đáp ứng pause goal.

## 8. Phân biệt throughput, pause time và CPU dành cho GC

Một cấu hình có pauses ngắn hơn **có thể** dành nhiều thời gian CPU cho GC hơn. Cần theo dõi cả:

| Quan sát | Có thể là gì | Bước xác minh |
| --- | --- | --- |
| Pauses ngắn, rất nhiều lần/giây | Young gen nhỏ, allocation rate cao | Đo allocation, young sizing, CPU GC |
| Pauses ít, nhưng kéo dài | Mỗi collection làm nhiều việc hoặc xử lý nhiều live data | Đọc `gc+phases` và pause causes |
| Concurrent GC dùng nhiều CPU | Marking, remembered-set work, allocation pressure | So CPU ứng dụng/GC và throughput |
| Full GC xuất hiện | Không còn đủ vùng cấp phát, marking không bắt kịp hoặc tác nhân ngoài | Tìm nguyên nhân trong log, live set, humongous regions |
| App p99 cao nhưng GC pause thấp | Không chắc GC là nút thắt | So tracing, DB/network waits, safepoints |

Một phép đo thô có thể tính **thời gian dừng GC / wall-clock time** để hiểu pause overhead. Nhưng đó **không phải toàn bộ GC CPU cost**, vì G1 còn thực hiện công việc concurrent khi ứng dụng đang chạy. Không suy ra throughput thực chỉ từ tổng milliseconds stop-the-world.

## 9. Full GC và evacuation failure: xử lý theo nguyên nhân

G1 thông thường cố tránh các Full GC dài bằng cách dọn heap theo các regions và hoàn thành concurrent marking đủ sớm. Nếu không còn đủ vùng thích hợp để cấp phát/di chuyển đối tượng, một **Full GC (G1 Compaction Pause)** có thể xảy ra như biện pháp cuối cùng.

Các biểu hiện cần tìm trong GC log Java 27:

```text
Pause Full (G1 Compaction Pause)
Evacuation Failure: Allocation
Evacuation Failure: Pinned
```

Những chuỗi trên là **nhãn sự kiện**, không phải kết quả của một lần chạy cụ thể. `Evacuation Failure: Allocation` cho thấy G1 không tìm đủ chỗ đích để di chuyển một số đối tượng. `Pinned` liên quan tới những đối tượng không được di chuyển tại thời điểm đó, chẳng hạn khi được cố định cho hoạt động native/JNI theo cơ chế runtime.

### 9.1. Nguyên nhân khả dĩ

- Heap quá nhỏ so với **live set** và mức tăng đối tượng.
- Ứng dụng có allocation rate cao; các đối tượng survive/promote nhanh.
- Concurrent marking khởi động hoặc hoàn tất **quá muộn** so với tốc độ old generation tăng.
- Nhiều **humongous objects** chiếm các regions riêng và gây phân mảnh.
- Áp lực CPU cao khiến concurrent marking không theo kịp.
- Có `System.gc()` hoặc công cụ ngoài yêu cầu thu gom toàn heap.

Không thể kết luận chỉ từ một dòng “Full GC” rằng heap bị leak, hay chỉ cần tăng `-Xmx` là xong.

### 9.2. Thứ tự khắc phục

1. Đọc log để xác định Full GC đến từ **allocation failure**, explicit GC hay nguyên nhân khác.
2. Đo live set sau các chu kỳ thu gom; kiểm tra lượng đối tượng thật sự còn được tham chiếu.
3. Tìm humongous regions, allocation spikes, burst/queue và những object graphs sống lâu.
4. Đánh giá heap headroom, CPU quota và tiến độ marking.
5. Thử **một thay đổi có căn cứ**: giảm allocation, tăng bộ nhớ hợp lý, hoặc chỉ sau đó mới điều chỉnh thông số chuyên sâu.

Nếu Full GC vẫn lặp dù đã cấp đủ RAM, hãy điều tra **memory leak**, cache không giới hạn, dữ liệu tồn đọng hoặc reference retention; tăng heap chỉ trì hoãn sự cố.

## 10. Humongous objects: khi kích thước đối tượng là vấn đề

Trong G1, một object được coi là **humongous** khi kích thước của nó **từ một nửa kích thước region trở lên**. Những objects này được cấp phát trong một hoặc nhiều regions liên tiếp thuộc old generation và có quy tắc thu hồi/di chuyển đặc biệt.

Giả sử region size là 2 MiB (giả định minh họa):

```text
G1 region size = 2 MiB
                       |
                       v
Object có kích thước >= 1 MiB => humongous

Một object 2.2 MiB có thể chiếm 2 regions (4 MiB dung lượng vùng).
Phần không sử dụng trong region cuối không được cấp cho
object khác cho đến khi humongous object được thu hồi.
```

Con số trên chỉ là ví dụ về quy tắc phân vùng; kích thước thực tế của một `byte[]` còn có header/alignment overhead và có thể vượt ngưỡng dù số phần tử nhìn qua ít hơn một chút.

### 10.1. Dấu hiệu trong GC log

Ghi nhận số humongous regions bằng:

```shell
java -Xmx2g -Xlog:gc+heap=info -jar app.jar
```

Trong log, một dòng ví dụ có thể có dạng:

```text
Humongous regions: 12->7
```

Đây là **mẫu định dạng minh họa**, không phải mục tiêu tốt/xấu cố định. Cần so số humongous regions với số old regions, heap size, chu kỳ marking và những thời điểm Full GC.

### 10.2. Hướng xử lý theo thứ tự

1. Kiểm tra application code có tạo nhiều `byte[]` khổng lồ, buffer giữ lâu hoặc batch tải cả file vào heap hay không.
2. Nếu hợp đồng cho phép, chia nhỏ dữ liệu, stream theo chunks hoặc giới hạn kích thước payload trong bộ nhớ.
3. Nếu thật sự có nhiều humongous objects ảnh hưởng GC, thử **region size lớn hơn** bằng `-XX:G1HeapRegionSize` trong bài đo có kiểm soát.
4. Kiểm tra side effects: số regions, remembered sets, thời gian evacuation và mức lãng phí do regions lớn.

**Không nâng region size như một “mẹo” cố định cho mọi heap.** Thay đổi region size có thể làm giảm số đối tượng bị phân loại humongous nhưng cũng khiến G1 phải di chuyển nhiều live data mỗi region và thay đổi footprint.

## 11. IHOP và concurrent marking: hiểu trước khi chỉnh

Khi old generation đầy dần, G1 cần khởi động **concurrent marking** đủ sớm để có thông tin về các old regions có thể thu hồi. Ngưỡng kích hoạt được gọi là **IHOP** (*Initiating Heap Occupancy Percent*).

Trong cấu hình Java 27 hiện hành, G1 sử dụng **adaptive IHOP** theo mặc định: nó quan sát hành vi phân bổ/marking ở các chu kỳ trước để ước lượng thời điểm nên bắt đầu. Vì thế, giá trị khởi tạo **không phải một ngưỡng cứng cố định vĩnh viễn**.

```text
Old generation occupancy tăng
              |
       Adaptive IHOP estimate
              |
              v
       Concurrent Start
              |
              v
       Concurrent Marking
              |
       Marking đủ sớm?
           /       \
         có        không
         |           |
    Mixed GCs    Nguy cơ thiếu vùng
         |       dành cho evacuation
         v           |
     Thu hồi old      v
                  Full GC risk
```

### 11.1. Đừng sao chép ngưỡng tĩnh từ bài viết cũ

Java SE 27 mô tả các tùy chọn **`-XX:+G1UseAdaptiveIHOP`** và **`-XX:G1IHOP`**. Khi adaptive IHOP đang bật, `G1IHOP` chủ yếu là giá trị **khởi tạo** trước khi G1 có đủ dữ liệu để tự thích nghi. Có thể tắt adaptive theo cách được tài liệu hóa rồi đặt ngưỡng thủ công, nhưng hành động này chỉ phù hợp khi có bằng chứng rõ ràng rằng prediction đang sai dưới workload cụ thể.

**Không khuyến nghị** tắt adaptive IHOP hoặc cố định một con số lấy từ cấu hình đời cũ khi mới tối ưu G1. Đọc GC log, đo promotion/marking và ưu tiên xử lý allocation pressure hoặc heap headroom trước.

### 11.2. Các knobs chuyên sâu liên quan

| Tùy chọn | Mục đích | Khi nào mới cân nhắc |
| --- | --- | --- |
| `-XX:ConcGCThreads` | Số threads tối đa cho các tác vụ concurrent GC | Marking không theo kịp và còn CPU headroom |
| `-XX:ParallelGCThreads` | Số threads tối đa cho các công việc GC song song trong pause | Chứng cứ CPU/parallel phases bị nghẽn, không chỉ p99 cao |
| `-XX:G1IHOP` và adaptive IHOP | Dự báo/khởi động marking | Chỉ sau khi xác minh chu kỳ marking bắt đầu quá trễ |
| `-XX:G1ReservePercent` | Điều chỉnh reserve/headroom dùng trong adaptive occupancy calculation theo hướng dẫn tuning | Có evacuation pressure, đã xem xét heap/headroom |
| `-XX:G1HeapRegionSize` | Đổi kích thước region | Có humongous/remembered-set pressure rõ ràng |

Đây là **tùy chọn nâng cao**, không phải bộ flags nên bật đồng loạt. Trước khi triển khai, xác nhận tên/ý nghĩa flag bằng **tài liệu của đúng JDK build** và thử nghiệm có đo lường; HotSpot có thể thay đổi ergonomics và một số tên flag giữa các phiên bản.

## 12. Mục tiêu latency thấp: đọc breakdown của pause

Nếu GC logs cho thấy **Pause Young** hoặc **Mixed GC** vượt mục tiêu, cần biết thời gian đó được tiêu ở đâu. G1 hỗ trợ log các pha chi tiết:

```shell
java -Xmx2g -Xlog:gc*=debug:file=gc-debug.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
```

Log `gc*=debug` có thể rất nhiều dữ liệu; chỉ bật trong khoảng đo phù hợp hoặc khi cần điều tra. Có thể thu hẹp:

```shell
java -Xmx2g -Xlog:gc+phases=debug,gc+cpu=info -jar app.jar
```

### 12.1. Những nhóm thời gian đáng chú ý

- **Ext Root Scanning / Code Root Scan:** quét các nguồn tham chiếu cần thiết.
- **Merge Heap Roots / Scan Heap Roots:** xử lý remembered sets và tham chiếu liên vùng.
- **Object Copy:** sao chép đối tượng còn sống khi evacuation.
- **Reference processing:** xử lý các loại reference và cấu trúc liên quan.
- **GC CPU User/Sys/Real:** so CPU time và wall time của pause.

Không nên chỉ dựa vào tên một pha và thay flag tương ứng theo suy đoán. Ví dụ, Object Copy dài có thể phản ánh **nhiều live data** hoặc không đủ CPU/memory bandwidth; điều chỉnh `MaxGCPauseMillis` có thể giảm lượng việc mỗi pause, nhưng ứng dụng cũng có thể cần giảm số object sống hoặc lượng data phải sao chép.

### 12.2. Đọc User, Sys và Real đúng nghĩa

Trong GC CPU log:

```text
User=0.19s Sys=0.00s Real=0.01s
```

Đây là ví dụ định dạng được tài liệu mô tả. `User` tổng CPU time ở user space, `Sys` ở kernel, `Real` là wall-clock duration. Với nhiều GC worker threads song song, **User có thể lớn hơn Real** vì cộng thời gian CPU trên nhiều threads.

Nếu `Sys` hoặc `Real` cao bất thường, phải xét CPU throttling, OS scheduling, page faults và áp lực bộ nhớ của máy/container trước khi tinh chỉnh vùng heap.

## 13. Throughput: tối ưu dựa trên thời gian hoàn thành công việc

Với batch/ETL, throughput có thể quan trọng hơn pause-time tail:

```text
Ưu tiên số 1: batch hoàn thành nhanh
Ưu tiên số 2: CPU/RAM nằm trong ngân sách
Có thể chấp nhận GC pauses dài hơn
```

Quy trình hợp lý:

1. Đo wall time của cùng một batch và CPU tổng.
2. Tìm xem GC chiếm bao nhiêu CPU và ảnh hưởng thời gian xử lý.
3. Thử **nới pause goal** để G1 có thêm quyền chọn young/mixed work.
4. Kiểm tra liệu tăng heap có giúp giảm GC pressure hay chỉ tăng memory cost.
5. Nếu G1 vẫn không phù hợp và latency không phải yêu cầu, **benchmark Parallel GC** như một collector khác trong Java 27.

Ví dụ hai cấu hình **thay thế**:

```shell
# A: giữ cấu hình G1 với heap giả định.
java -Xmx2g -XX:+UseG1GC -jar BatchMain

# B: nới pause goal để kiểm tra throughput.
java -Xmx2g -XX:+UseG1GC -XX:MaxGCPauseMillis=300 -jar BatchMain
```

Chỉ kết luận B tốt hơn nếu trên cùng tải nó giảm thời gian hoàn thành/CPU hoặc đạt chỉ số mục tiêu khác. **Đừng chỉ thấy số lần GC giảm mà khẳng định hiệu năng tốt hơn**.

### 13.1. Có nên chỉnh số lượng GC threads?

HotSpot tự chọn `ParallelGCThreads` và `ConcGCThreads` theo CPU và heap. Với CPU quota nhỏ, đặt thủ công quá nhiều GC threads có thể gây contention/throttling; với CPU dồi dào, tăng threads cũng không tự bảo đảm tăng throughput vì chi phí đồng bộ và băng thông bộ nhớ.

Chỉ thử khi log/JFR cho thấy GC phase hoặc marking thực sự bị giới hạn bởi concurrency và môi trường còn nguồn lực. Thay đúng **một flag**, benchmark lại rồi quyết định giữ/bỏ.

## 14. Container memory: Java heap khác tổng bộ nhớ tiến trình

Memory limit của container bao gồm **nhiều hơn `-Xmx`**:

```text
Container memory / process footprint
      |
      +-- Java heap            (-Xmx là giới hạn tối đa của heap)
      +-- Metaspace / class metadata
      +-- JIT code cache
      +-- Native thread stacks
      +-- Direct buffers / native allocations
      +-- GC/JVM internal structures
      +-- Mapped memory và các thành phần hệ điều hành
```

Đặt `-Xmx` bằng 100% container memory **không an toàn** vì các thành phần khác vẫn cần RAM. Nếu container bị OS/orchestrator kill vì memory limit, bạn có thể **không thấy** Java `OutOfMemoryError: Java process bị dừng từ bên ngoài.

### 14.1. Heap cố định và heap theo tỷ lệ memory

Hai chiến lược phổ biến:

```shell
# Cách A: giới hạn heap tường minh (ví dụ).
java -Xmx1g -jar app.jar

# Cách B: tính trần heap theo tỷ lệ RAM khả dụng cho JVM (ví dụ).
java -XX:MaxRAMPercentage=60 -jar app.jar
```

`-XX:MaxRAMPercentage` tham gia xác định **kích thước Java heap tối đa** theo memory khả dụng được JVM nhận diện; nó **không** là giới hạn tuyệt đối cho toàn bộ process. Tỷ lệ 60% ở đây là **số giả định**, không phải mặc định Java 27 hoặc mức tối ưu cho mọi container.

Khi chọn tỷ lệ, dự trù metaspace, native allocations, thread stacks, buffers, GC overhead, page cache và spike. Xác minh JVM thực sự nhận diện memory/CPU quota theo runtime/container đang dùng.

### 14.2. `-Xms = -Xmx` có đánh đổi với autoscaling

Heap cố định và `AlwaysPreTouch` có thể làm latency do resizing ổn định hơn ở một số workload. Nhưng memory được giữ cao sớm sẽ ảnh hưởng tới **density**, cold starts, HPA/VPA behavior và chi phí. Trong deployment cần tiết kiệm RAM, G1 có thể thu hẹp/uncommit heap đã không còn dùng theo chính sách của JVM; đừng vô hiệu hóa khả năng này mà không đo.

### 14.3. Native memory cần công cụ riêng

Nếu RSS tăng mà heap used không tăng tương ứng, không nên chỉ tăng `-Xmx`. Có thể cần **Native Memory Tracking (NMT)**:

```shell
# Chọn từ khi khởi động JVM; có overhead.
java -XX:NativeMemoryTracking=summary -Xmx1g -jar app.jar
```

Với tiến trình có quyền truy cập, dùng `jcmd` để xem NMT summary; công cụ này tập trung vào các phân bổ mà JVM tracking hỗ trợ, **không bảo đảm bao phủ mọi native allocation từ thư viện bên ngoài**.

## 15. G1, ZGC và Parallel GC: lựa chọn theo workload

Java SE 27 có nhiều collectors. G1 là điểm khởi đầu tốt, **không phải** lựa chọn độc quyền.

| Collector | Đặc điểm mục tiêu | Tình huống nên thử |
| --- | --- | --- |
| **G1** | Cân bằng throughput, memory và pause-time goal | Phần lớn dịch vụ khi không có yêu cầu pause cực thấp |
| **ZGC** | Giảm pause tối đa qua công việc concurrent nhiều hơn, có đánh đổi throughput/CPU | Dịch vụ rất nhạy với latency và chấp nhận chi phí |
| **Parallel GC** | Chú trọng thông lượng, chấp nhận stop-the-world pauses | Batch/compute jobs không có SLA pause chặt |
| **Serial GC** | Ít overhead điều phối GC threads, dành cho môi trường rất hạn chế | Workload nhỏ/số CPUs rất thấp, cần benchmark |

Không có quy tắc “heap lớn thì bắt buộc ZGC” hoặc “batch luôn Parallel”. Hiệu quả còn phụ thuộc live set, allocation rate, hardware và JDK build. Nếu G1 với heap/goal hợp lý không đạt chỉ số, hãy benchmark collector thay thế trên **cùng workload**, thay vì thêm liên tiếp nhiều flags không hiểu rõ.

## 16. Unified GC logging: quan sát đúng trước khi điều chỉnh

Java SE 27 sử dụng **JVM Unified Logging** qua `-Xlog`. Các cờ logging kiểu cũ như `-XX:+PrintGCDetails` hay `-Xloggc` không phải cách triển khai mới nên ưu tiên.

### 16.1. Các mức ghi log thực dụng

```shell
# Quan sát GC cơ bản trên console.
java -Xlog:gc -jar app.jar

# Thông tin chi tiết các GC phases và heap, có thể rất nhiều dòng.
java -Xlog:gc* -jar app.jar

# Điều tra thời gian các phases và CPU usage.
java -Xlog:gc+phases=debug,gc+cpu=info -jar app.jar

# Ghi file có rotation (ví dụ; phải cấp quyền nơi ghi file).
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=10M -jar app.jar
```

Các lệnh là **các cách chạy thay thế**, không phải bắt buộc mở bốn JVM đồng thời. Khi có nhiều `-Xlog` options, thứ tự và quy tắc override cần được hiểu theo tài liệu JVM.

### 16.2. Đọc một dòng GC log

Một dòng theo dạng tổng quát có thể trông như:

```text
[2.345s][info][gc] GC(3) Pause Young (Normal)
                           (G1 Evacuation Pause) 90M->28M(256M) 12.3ms
```

**Đây là ví dụ định dạng minh họa**, các con số và event ID không phải đo từ ứng dụng thật. Có thể đọc:

- `2.345s`: uptime khi log sự kiện, tùy decorators được chọn.
- `GC(3)`: ID của sự kiện GC.
- `Pause Young (Normal)`: loại collection.
- `90M->28M(256M)`: heap occupancy trước/sau, và kích thước heap tại sự kiện.
- `12.3ms`: thời lượng pause được báo.

**Không** suy luận rằng khoảng giảm từ 90 MiB còn 28 MiB là toàn bộ memory tiết kiệm của process; đó là thông tin heap tại event, không tính toàn bộ native memory. Cũng không coi bất kỳ vùng “trống” trên heap đều đang được trả về OS ngay lập tức.

### 16.3. Thu log có kiểm soát

G1 debug logs có overhead lưu trữ và có thể thay đổi timing của workload; hãy chọn cửa sổ thu hợp lý, giới hạn retention/rotation và kiểm soát quyền đọc. GC logs thường ít nhạy cảm hơn heap dump, nhưng có thể chứa tên tiến trình, đường dẫn, tham số và chi tiết hệ thống — không đưa tùy tiện lên nguồn công khai.

## 17. `jcmd` và JFR: các công cụ quan sát hiện hành

`jcmd` là công cụ JDK để yêu cầu chẩn đoán từ JVM đang chạy, khi có quyền phù hợp và cơ chế attach được hỗ trợ.

Các lệnh mẫu dùng `12345` làm **PID giả định**:

```shell
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 VM.command_line
jcmd 12345 GC.heap_info
```

`VM.flags` giúp kiểm tra các giá trị HotSpot được chọn, tránh suy từ script triển khai. `GC.heap_info` cung cấp thông tin heap, **không** tự kết luận nguyên nhân latency cao.

### 17.1. Java Flight Recorder

**JFR** cho phép thu sự kiện runtime và liên hệ allocation/GC với ứng dụng:

```shell
# Ví dụ: thu trong 2 phút, file lưu tại thư mục có quyền bảo vệ.
jcmd 12345 JFR.start name=g1-review settings=profile duration=120s filename=g1-review.jfr
```

Nên khảo sát các nhóm dữ liệu:

- GC pauses và các phases.
- Allocation rate và allocation hotspots.
- CPU, thread activity, blocking/safepoint events thích hợp.
- Tương quan với requests/traces theo thời gian.

Các sự kiện/thống kê hiện diện phụ thuộc JDK, cấu hình recording và mức profiling. Không suy rằng chỉ bật JFR sẽ tự tạo đầy đủ mọi phân tích memory leak.

### 17.2. Native Memory Tracking

Nếu JVM đã khởi động với:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Có thể xem:

```shell
jcmd 12345 VM.native_memory summary
```

NMT có overhead và theo dõi chủ yếu bộ nhớ do HotSpot/JVM quản lý; không nhất thiết phát hiện mọi allocation trong thư viện native bên thứ ba. Đối với container RSS tăng không tương ứng Java heap, hãy kết hợp NMT với memory metrics của OS/container.

### 17.3. Heap histogram và heap dump

`jcmd` còn có các diagnostic commands:

```shell
jcmd 12345 GC.class_histogram
# Chỉ thực hiện heap dump khi được phê duyệt và có dung lượng/không gian bảo vệ:
# jcmd 12345 GC.heap_dump /secure/diagnostics/heap.hprof
```

Heap histogram và dump có thể gây overhead/pauses đáng kể. **Heap dump có thể chứa password, token, session data, thông tin cá nhân và toàn bộ object graph**, vì vậy cần phân quyền truy cập, encryption/retention và xử lý như dữ liệu nhạy cảm. Không chạy các lệnh tác động cao tùy tiện trên môi trường production.

## 18. Ví dụ Java 27: quan sát heap và GC counts

Ví dụ `Demo.java` dưới đây tạo lượng cấp phát nhỏ có kiểm soát, giữ lại một phần đối tượng và đọc `java.lang.management`. Nó **không** cố đo hiệu năng chính xác, không tạo memory leak và không yêu cầu thư viện ngoài.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.util.ArrayList;
import java.util.List;

public class Demo {
    private static final int BLOCK_BYTES = 16 * 1024;

    private static void printSnapshot(String phase) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        long used = memory.getHeapMemoryUsage().getUsed();
        long committed = memory.getHeapMemoryUsage().getCommitted();
        long max = memory.getHeapMemoryUsage().getMax();

        System.out.println(phase + " heap used=" + used
                + " committed=" + committed + " max=" + max);

        for (GarbageCollectorMXBean gc
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("  " + gc.getName()
                    + " collections=" + gc.getCollectionCount()
                    + " timeMs=" + gc.getCollectionTime());
        }
    }

    public static void main(String[] args) {
        printSnapshot("Before");

        List<byte[]> retained = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 12_000; i++) {
            byte[] block = new byte[BLOCK_BYTES];
            block[0] = (byte) i;
            checksum += block[0];

            if (i % 250 == 0) {
                retained.add(block);
            }
        }

        System.out.println("Retained blocks: " + retained.size());
        System.out.println("Checksum: " + checksum);
        printSnapshot("After ");
    }
}
```

Biên dịch và chạy để quan sát G1:

```shell
javac Demo.java
java -Xms32m -Xmx128m -XX:+UseG1GC -Xlog:gc* Demo
```

Giá trị `32m` và `128m` chỉ phục vụ chương trình thử nghiệm độc lập; **không** được sao chép thành heap size production.

### 18.1. Kết quả cần hiểu đúng

- Tên `GarbageCollectorMXBean`, số collections và thời gian phụ thuộc JDK/runtime; **không có đầu ra số liệu cố định**.
- Theo API, `getCollectionCount()` và `getCollectionTime()` có thể trả `-1` nếu giá trị không được xác định.
- `getCollectionTime()` là thời gian tích lũy xấp xỉ theo cách runtime ghi nhận, không phải một metric latency percentiles.
- `getHeapMemoryUsage()` là **snapshot**, không phải phép đo mức cao nhất hoặc memory leak detector.
- Ứng dụng có thể tối ưu một số allocation; log và con số không phải benchmark đáng tin cậy nếu thiếu workload chuẩn.

Đo GC tuning production cần load test đại diện, JFR/logs và SLO của ứng dụng, không dựa vào một demo nhân tạo.

## 19. Case study: API online nhạy với p99

**Bối cảnh giả định:** Một dịch vụ web có p99 response time 350 ms, yêu cầu p99 dưới 250 ms, heap tối đa 2 GiB, G1 mặc định.

### 19.1. Chẩn đoán trước

Quan sát:

```text
p99 HTTP: 350 ms
G1 Pause Young p99: 28 ms
DB query p99: 260 ms
```

Các con số **minh họa**, không phải dữ liệu đo thật. Trong trường hợp này, việc hạ `-XX:MaxGCPauseMillis` từ 200 xuống 100 **không giải quyết được** phần lớn tail latency. Cần ưu tiên query latency, pool wait, index và downstream.

Một trường hợp khác:

```text
p99 HTTP: 350 ms
G1 Mixed GC pauses nhiều lần 180-260 ms
Object Copy / Scan Heap Roots chiếm đa số pause
```

Khi đó GC có khả năng là thành phần đáng kể. Thử có kiểm soát:

1. Điều tra allocation và lượng live data, đặc biệt caches/buffers.
2. Kiểm tra heap headroom và concurrent marking.
3. Thử `-XX:MaxGCPauseMillis=100` hoặc tăng heap hợp lý **mỗi lần một yếu tố**.
4. So p99 ứng dụng, GC pause distribution, CPU và request throughput trên cùng tải.
5. Nếu pause tail vẫn không đạt yêu cầu và chi phí chấp nhận được, benchmark ZGC.

**Không cam kết p99 250 ms chỉ vì chọn pause goal 100 ms.**

## 20. Case study: batch job ưu tiên thông lượng

**Bối cảnh giả định:** Batch ETL xử lý 15 triệu bản ghi, không có SLA thời gian dừng ngắn, nhưng có giới hạn CPU và RAM.

Baseline:

```text
Thời gian hoàn thành: 22 phút
Pause Young ngắn nhưng rất thường xuyên
GC concurrent CPU đáng kể
Không có Full GC
```

Phương án cần đánh giá:

- Hạn chế object allocation không cần thiết trong vòng lặp chuyển đổi.
- Tăng kích thước xử lý theo batch phù hợp, không tải toàn bộ dataset vào heap.
- So `MaxGCPauseMillis` mặc định với mức cao hơn, ví dụ 300 ms.
- Nếu cần, so G1 và Parallel GC với cùng heap size/CPU quota.

**Đo kết quả bằng** thời gian hoàn thành, số bản ghi/giây và CPU/RAM/đơn vị công việc. Một cấu hình tăng số GC pauses nhưng hoàn thành job nhanh hơn vẫn có thể tốt nếu đáp ứng mục tiêu; ngược lại, tổng pause thấp nhưng CPU cost lớn có thể không đạt yêu cầu.

## 21. Case study: dịch vụ giới hạn container memory

**Bối cảnh giả định:** Một container có memory limit 1 GiB. Ứng dụng lúc cao điểm có heap used khoảng 550 MiB, còn native memory và các thành phần khác tiêu thụ thêm đáng kể.

Không nên đặt:

```shell
# Rủi ro khi container chỉ có 1 GiB:
# java -Xmx1g -jar app.jar
```

Đây là vì `-Xmx` chỉ giới hạn Java heap, **không** giới hạn process RSS. Một cách khởi đầu có thể thử là dành một tỷ lệ memory phù hợp cho heap:

```shell
# Ví dụ minh họa, KHÔNG phải cấu hình tối ưu chung:
java -XX:MaxRAMPercentage=60 -Xlog:gc -jar app.jar
```

Việc chọn 60% cần đi kèm kiểm chứng native footprint, GC headroom và giới hạn của container thật.

### 21.1. Phân nhánh theo kết quả

| Quan sát | Điều tra ưu tiên |
| --- | --- |
| Java heap gần `-Xmx`, old occupancy cao, GC lặp | Live set, retention/leak, heap sizing, allocation pressure |
| Container OOMKilled nhưng Java heap còn dư | Native memory, direct buffers, metaspace, thread stacks, external allocations |
| Full GC và humongous regions nhiều | Kích thước payload, streaming, region size **sau khi đã đo** |
| RSS tăng sau startup rồi ổn định | JIT, heap growth, caches, native allocator — chưa đủ chứng minh leak |
| Memory tăng không giới hạn qua nhiều chu kỳ tải | Heap dump/JFR/NMT phù hợp, object ownership và sự tồn tại của references |

Nếu chỉ nhìn JVM heap used trong dashboard, bạn có thể bỏ sót phần lớn lý do container bị kill.

### 21.2. Không để diagnostic tool làm vấn đề nặng hơn

Khi memory còn rất ít, một heap dump có thể làm dừng ứng dụng hoặc làm đầy filesystem. Bật NMT ở mức `detail` cũng có overhead. Hãy có phương án incident response an toàn: chụp metrics/logs sẵn có trước, chỉ lấy dump/recording với ngân sách được duyệt và nơi lưu được bảo vệ.

## 22. Bảng chẩn đoán: triệu chứng → bằng chứng → hành động

| Triệu chứng | Cần thu thập | Hành động ưu tiên |
| --- | --- | --- |
| p99 tăng, GC pauses vẫn ngắn | Traces, downstream latency, safepoints | Không chỉnh GC trước khi xác định bottleneck |
| Young GC rất thường xuyên | Allocation rate, young size, CPU GC, live data | Giảm allocation, cân nhắc pause goal/heap nếu phù hợp |
| Young pauses dài, `Object Copy` cao | `gc+phases=debug`, live bytes, promotion | Giảm live set/copying, kiểm tra young sizing |
| Mixed GC kéo dài | Old region candidates, remembered-set phases | Kiểm tra old live set, cross-region references, pause goal |
| Full GC do allocation failure | `Pause Full`, `Evacuation Failure`, heap/old occupancy | Giảm pressure, tăng headroom hợp lý, xem concurrent marking |
| Full GC gắn `System.gc()` | GC cause, ứng dụng/công cụ gọi | Xác định caller và loại bỏ explicit GC không cần |
| Nhiều humongous regions | `gc+heap=info`, object sizes, payload | Chia nhỏ/stream, chỉ sau đó thử `G1HeapRegionSize` |
| Concurrent marking không hoàn tất kịp | Mark cycles, promotion rate, CPU quota | Giảm allocation, tăng headroom; flags nâng cao khi có chứng cứ |
| GC CPU cao, throughput giảm | GC logs/JFR và CPU profiles | Tìm object churn, đánh giá nới pause goal |
| Heap không giảm sau GC | Live set sau marking, retained paths | Tìm cache không giới hạn, leak, backlog, static references |
| Container OOMKilled, không có Java OOME | Container event, RSS, NMT, direct buffers | Dự trù native memory; không tăng `-Xmx` mù quáng |
| GC logs cho thấy `Sys` cao | GC CPU lines, OS metrics | CPU throttling, page faults, memory pressure |
| Tăng heap nhưng p99 không cải thiện | Cùng workload và metrics A/B | Dừng tăng heap; xem bottleneck ngoài GC |

**Một triệu chứng có thể có nhiều nguyên nhân.** Bảng này là hướng đi điều tra, không phải ánh xạ “mỗi symptom ứng với đúng một flag”.

## 23. Quy trình tuning có kiểm chứng và rollback

Một thay đổi GC chỉ nên được chấp nhận sau khi xác minh **mục tiêu ứng dụng**, không chỉ “GC log nhìn đẹp hơn”.

### 23.1. Quy trình đề xuất

1. **Đặt baseline:** JDK build, collector, flags, CPU/memory limit, workload, pause p95/p99/max, throughput và app SLO.
2. **Đặt giả thuyết:** ví dụ “young collection quá nhiều vì pause goal quá thấp; nới mục tiêu có thể giảm CPU GC”.
3. **Thay một yếu tố:** ví dụ chỉ thay `MaxGCPauseMillis` từ 200 sang 300.
4. **Chạy cùng workload:** đủ lâu và đủ nhiều lần để tránh kết luận từ một run nhiễu.
5. **So kết quả nhiều chiều:** response-time tail, throughput, error rate, CPU, heap/RSS, GC pause, Full GC.
6. **Giữ hoặc rollback:** nếu không đạt mục tiêu hoặc gây regressions đáng kể, quay về cấu hình baseline.
7. **Ghi bằng chứng:** lưu experiment ID, JDK version, command-line options, metrics và quyết định.

### 23.2. Bảng so sánh ví dụ

Giả sử một dịch vụ đang được load test ở cùng mức tải:

| Chỉ số minh họa | Baseline G1 | Thử nghiệm A |
| --- | ---: | ---: |
| `-Xmx` | 2 GiB | 2 GiB |
| `MaxGCPauseMillis` | 200 ms | 100 ms |
| GC pause p99 | 85 ms | 62 ms |
| API p99 | 220 ms | 218 ms |
| Throughput | 6.000 req/s | 5.500 req/s |
| CPU tổng | 65% | 76% |

Tất cả con số **giả định**. Ở đây, A giảm GC pause p99 nhưng API p99 hầu như không cải thiện trong khi throughput giảm và CPU tăng. Nếu mục tiêu là tăng throughput với p99 dưới 250 ms, **A có thể không đáng giữ**.

Ngược lại, nếu ứng dụng có một giới hạn ngắn hơn nhiều và GC thực sự gây tail spikes, lợi ích có thể đủ lớn để chấp nhận CPU cost. Quyết định phải dựa trên SLO.

### 23.3. Vì sao phải lưu JDK build?

Từng phiên bản JDK có thể cải thiện chính sách G1, cách chọn region, tính toán heap hoặc chi phí các phases. Không áp nguyên flags tối ưu từ Java 11/17/21 vào Java 27 mà bỏ qua các mặc định mới.

Theo định hướng của bài này, thông số cần được **đối chiếu với tài liệu Oracle Java SE 27 và JVM đang dùng**. Những flags nâng cao/experimental hoặc tên flags đời trước không trở thành khuyến nghị bền vững chỉ vì chúng xuất hiện trên một blog cũ.

## 24. Các sai lầm thường gặp khi điều chỉnh G1

| Cách làm | Vì sao không phù hợp | Thay thế |
| --- | --- | --- |
| Sao chép 20 flags từ một cấu hình GC cũ | Chồng can thiệp vào ergonomics và flags có thể đổi nghĩa | Bắt đầu defaults, chỉ chỉnh khi đã đo |
| Coi `MaxGCPauseMillis=50` là SLA cứng | G1 không phải real-time collector | Theo dõi pause distribution và app SLO |
| Hạ pause goal càng thấp càng tốt | GC thường xuyên hơn, có thể giảm throughput | Thử có kiểm chứng theo latency/CPU |
| Cố định young size bằng `-Xmn` | Hạn chế khả năng G1 tự chọn việc trong pause | Để young sizing thích nghi |
| Chỉ nhìn số lần GC, không đo elapsed work | Ít GC không đồng nghĩa nhanh hơn | Đo throughput và p99 |
| Tăng `-Xmx` cho mọi vấn đề | Không giải quyết database, CPU, lock hay native OOM | Xác định nguồn bottleneck |
| Đặt `-Xmx` bằng 100% container limit | Không còn RAM cho native memory | Để headroom và đo RSS |
| Đặt `-Xms` bằng `-Xmx` cho mọi microservice | Tăng startup và memory footprint không cần | Dùng khi latency/footprint chứng minh lợi ích |
| Bật `AlwaysPreTouch` ở mọi container | Có thể tăng cold-start và RSS | Kiểm tra mục tiêu, đo trade-off |
| Chỉnh `G1HeapRegionSize` mà không xem humongous logs | Có thể tăng lượng live data cần di chuyển | Đo `gc+heap=info` trước |
| Tắt adaptive IHOP ngay | Tước khả năng học từ workload | Giữ adaptive, chỉ đổi khi evidence rõ |
| Coi concurrent GC là hoàn toàn không có pause | G1 vẫn có stop-the-world phases | Đọc đúng các pause events |
| Dùng `System.gc()` để “làm sạch” trước mỗi request | Gây hoạt động thu gom tốn kém, không giải quyết retention | Để JVM quản lý; sửa object lifecycle |
| Coi `OutOfMemoryError` luôn do GC cấu hình sai | Có thể là leak, allocation hoặc native/DB resource | Điều tra root cause |
| So kết quả load test khác CPU/memory quotas | Không có cơ sở so sánh | A/B cùng môi trường |
| Đọc heap used rồi kết luận RSS bằng heap | JVM còn nhiều vùng ngoài heap | NMT và container metrics |
| Lấy một heap dump production không kiểm soát | Pause/IO lớn, có thể lộ dữ liệu nhạy cảm | Chỉ theo quy trình chẩn đoán có quyền |
| Dùng flags deprecated chỉ vì ví dụ cũ | Không phù hợp Java 27, có thể không còn tác dụng | Dùng `-Xlog` và flags hiện hành |
| Coi mọi p99 spike đều do GC | Hệ thống còn network/SQL/scheduler | Correlate traces và GC timing |
| Chọn collector theo xu hướng | Collector nào cũng có trade-offs | Benchmark G1/ZGC/Parallel theo SLO |

## 25. Checklist vận hành trước khi thay G1 flags

1. **Đã xác nhận JVM HotSpot/Java 27 build và GC hiện tại chưa?** Dùng `VM.flags` hoặc startup log.
2. **Mục tiêu chính là latency, throughput hay memory footprint?** Có tiêu chí định lượng không?
3. **Đã đo GC pause p95/p99/max và tần suất chưa?** Có so với application traces không?
4. **Có phải GC thật sự đóng góp đáng kể vào SLO violation không?**
5. **Heap used, committed, live set và allocation rate ra sao?** Có object retention bất thường không?
6. **`-Xmx` có phù hợp memory budget không?** Đã tính native memory/container limit?
7. **Có cần đổi `-Xms` hoặc `AlwaysPreTouch`?** Đã đo startup/RSS?
8. **`MaxGCPauseMillis` có đang quá chặt so với throughput mục tiêu không?** Có dữ liệu trước khi hạ/nới?
9. **Có đang cố định young generation bằng `-Xmn`/`NewRatio` không?** Nếu có, đã xác định tác động?
10. **Có Full GC hoặc evacuation failure không?** Đã xác định nguyên nhân từ log?
11. **Có nhiều humongous objects không?** Đã thử thay đổi cấu trúc allocation/payload trước khi tăng region size?
12. **Concurrent marking có hoàn tất đủ sớm không?** CPU quota/headroom có phù hợp?
13. **Đã quan sát các GC phases và `gc+cpu` chưa?** Có system-time/throttling bất thường?
14. **Các lệnh `-Xlog` có rotation, retention và quyền truy cập an toàn không?**
15. **Dữ liệu JFR/heap dumps có thể chứa bí mật không?** Đã có chính sách bảo vệ chưa?
16. **Nếu heap ổn nhưng RSS tăng, đã xem NMT/native allocations chưa?**
17. **Cấu hình mới có được so ở cùng workload, JDK, CPU/RAM và dữ liệu không?**
18. **Đã đo application throughput, p99, CPU và error rate sau thay đổi chưa?**
19. **Có phương án rollback và lưu lại experiment metadata không?**
20. **Nếu G1 không đạt mục tiêu, đã benchmark collector thay thế thay vì thêm flags ngẫu nhiên chưa?**

## 26. Tổng kết

**G1** là lựa chọn mặc định và hợp lý cho nhiều ứng dụng Java 27 vì cân bằng throughput và những khoảng dừng GC tương đối ngắn. Nhưng **G1 không bảo đảm pause time tuyệt đối**; việc đạt SLO phụ thuộc cả ứng dụng, workload, live set, CPU, RAM và những hệ thống ngoài JVM.

Thứ tự điều chỉnh nên là **đặt mục tiêu → thu baseline → hiểu log → đo heap và object allocation → thử heap size/pause goal → đánh giá workload-level metrics**. Với G1, ưu tiên bắt đầu từ mặc định, `-Xmx`/`-Xms` khi cần và `-XX:MaxGCPauseMillis` như một **soft goal**. Không cố định young generation hoặc tắt adaptive heuristics khi chưa có bằng chứng.

Khi gặp Full GC, evacuation failure hoặc humongous pressure, hãy điều tra **nguyên nhân**, không chỉ tìm một flag có tên tương ứng. Khi JVM chạy trong container, nhớ rằng **Java heap khác tổng memory của process** và log/JFR/NMT phải được sử dụng có kiểm soát.

Mục đích cuối cùng của GC tuning không phải giảm mọi GC event xuống mức thấp nhất: đó là **đáp ứng yêu cầu của ứng dụng với tài nguyên và chi phí chấp nhận được**, dựa trên thử nghiệm có thể lặp lại và có phương án rollback.

## Tài liệu tham khảo

- [Java SE 27 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html) — regions, young/old, concurrent marking, mixed collections, humongous objects và defaults.
- [Java SE 27 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html) — default-first guidance, heap/pause goal, Full GC, latency/throughput tuning.
- [Java SE 27 — Available Collectors](https://docs.oracle.com/en/java/javase/27/gctuning/available-collectors.html) — G1, Parallel, Serial và ZGC, tiêu chí lựa chọn.
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — `-Xmx`, `-Xms`, `MaxGCPauseMillis`, `MaxRAMPercentage`, `-Xlog` và logging file rotation.
- [Java SE 27 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html) — `jcmd`, JFR, native memory tracking và công cụ xử lý vấn đề hiệu năng.
- [Java SE 27 — The jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — `VM.flags`, `GC.heap_info`, `VM.native_memory` và `JFR.start`.
- [Java SE 27 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html) — `getCollectionCount` và `getCollectionTime`.
- [Java SE 27 — MemoryMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryMXBean.html) — thông tin sử dụng heap và non-heap.
- [Java SE 27 — Java Flight Recorder API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — runtime event recording và phân tích.
