# G1: vùng heap, thu hồi ưu tiên và mục tiêu thời gian dừng

G1 (Garbage-First Garbage Collector) là garbage collector theo vùng (*region-based collector*) của HotSpot. Thay vì chia heap thành các không gian generation có ranh giới cố định, G1 chia heap thành nhiều vùng có kích thước bằng nhau; mỗi vùng có thể được dùng làm Eden, Survivor, Old hoặc Humongous theo nhu cầu. Khi thu gom, G1 chọn một tập vùng cần xử lý (*collection set*) và ưu tiên những vùng có thể thu hồi nhiều bộ nhớ với chi phí dự đoán phù hợp.

G1 hướng tới mục tiêu thời gian dừng do ứng dụng đặt ra bằng `-XX:MaxGCPauseMillis`. Đây là **mục tiêu mềm để JVM tối ưu**, không phải cam kết mọi pause đều nằm dưới con số đó. G1 dự đoán chi phí quét remembered set, sao chép object sống và xử lý vùng được chọn để quyết định lượng công việc có thể thực hiện trong một pause.

## Mục tiêu

- Hiểu cấu trúc heap region và vai trò động của từng vùng.
- Phân biệt Young GC, Mixed GC và concurrent marking cycle.
- Hiểu cách G1 chọn vùng có khả năng thu hồi cao.
- Nắm remembered set, card table và write barrier ở mức cần thiết để đọc GC log.
- Hiểu humongous object và tác động của kích thước region.
- Hiểu `-XX:MaxGCPauseMillis` là mục tiêu mềm và các đánh đổi khi thay đổi.
- Nhận biết evacuation failure, to-space exhaustion và Full GC.
- Đọc Unified GC log và quan sát heap bằng `jcmd`.
- Tuning G1 theo số liệu thực tế thay vì chỉnh nhiều flag cùng lúc.

## 1. G1 chia heap thành các region

G1 chia Java heap thành các region có kích thước bằng nhau. Kích thước thường được JVM chọn tự động theo dung lượng heap; giá trị hợp lệ là lũy thừa của hai trong khoảng 1 MB đến 32 MB. Mục tiêu là giữ số lượng region ở mức quản lý được trong nhiều cấu hình heap.

Ví dụ, nếu region size là 1 MB và heap tối đa là 32 MB, heap có khoảng 32 region. Nếu region size là 16 MB và heap tối đa là 1 GB, heap có khoảng 64 region. Đây chỉ là phép chia dung lượng minh họa; một phần heap có thể chưa được commit tại một thời điểm.

Flag liên quan:

~~~text
-XX:G1HeapRegionSize=<size>
~~~

Thông thường nên để JVM chọn region size theo ergonomics. Chỉ thay đổi khi có số liệu cho thấy kích thước mặc định không phù hợp, vì thay đổi region size ảnh hưởng cả số region, ngưỡng humongous và chi phí remembered set.

### 1.1. Các loại region

| Loại region | Vai trò |
| --- | --- |
| Free | Chưa chứa object đang sử dụng; có thể được cấp cho allocation hoặc evacuation |
| Eden | Nơi cấp phát phần lớn object mới trong young generation |
| Survivor | Giữ object sống sót qua một hoặc nhiều young collection |
| Old | Giữ object sống lâu hơn sau khi được promote hoặc được cấp phát vào old |
| Humongous | Dành cho object có kích thước lớn theo ngưỡng G1 |

Region không bị gắn cố định vào một generation suốt đời. Sau một collection, region được giải phóng có thể được tái sử dụng làm Eden, Survivor hoặc Old tùy quyết định của G1. Vì vậy không hình dung heap G1 như một dải Eden/Survivor/Old cố định.

### 1.2. Young, Survivor và Old trong G1

- Object mới thường được cấp phát trong Eden region.
- Object còn sống sau Young GC có thể được copy sang Survivor region.
- Object sống lâu có thể được promote sang Old region.
- G1 thay đổi số lượng region cho young/old theo áp lực cấp phát, số object sống và mục tiêu pause.

Việc một object được promote không đồng nghĩa nó sẽ ở mãi trong cùng một region. Trong các collection sau, object sống có thể tiếp tục được copy sang region khác.

## 2. Collection Set và evacuation

Trong một pause, G1 chọn một tập region cần thu gom gọi là **Collection Set (CSet)**. G1 dừng các application thread cho phần evacuation pause, xác định object sống trong các region được chọn và copy chúng sang region đích.

Quy trình khái quát:

~~~text
Chọn các region vào CSet
          |
          v
Xác định object sống trong CSet
          |
          v
Copy object sống sang region đích
          |
          v
Cập nhật reference và metadata
          |
          v
Giải phóng region nguồn
~~~

Evacuation cho phép G1 thu hồi region bằng cách chuyển object sống ra ngoài, sau đó giải phóng toàn bộ region nguồn. Điều này cũng giúp giảm phân mảnh so với việc chỉ quét và giữ lại object tại chỗ.

Chi phí pause phụ thuộc vào số object sống phải copy, số reference từ bên ngoài trỏ vào CSet, số region được chọn, tốc độ bộ nhớ và các công việc phụ trợ. Một CSet lớn có thể thu hồi nhiều bộ nhớ nhưng thường cần nhiều thời gian hơn.

## 3. Young GC

Young GC thu gom các Eden và Survivor region thuộc young generation. Đây là stop-the-world evacuation pause: application thread tạm dừng trong khi G1 xử lý CSet.

Trong một Young GC:

1. G1 xác định các young region cần thu gom.
2. Tìm object sống, bao gồm object được tham chiếu từ ngoài CSet.
3. Copy object sống sang Survivor hoặc Old region phù hợp.
4. Cập nhật reference tới vị trí mới.
5. Giải phóng các region nguồn.

Young GC thường xảy ra khi Eden không còn đủ chỗ cho allocation mới. G1 có thể điều chỉnh kích thước young generation để đáp ứng pause-time goal và tốc độ cấp phát.

Log thường có dòng dạng:

~~~text
[info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) ...
~~~

Chi tiết thời gian, dung lượng trước/sau và phase phụ thuộc runtime. Không suy luận hiệu năng chỉ từ số lần Young GC; cần xem pause duration, allocation rate, object sống và mức độ ứng dụng chịu được pause.

## 4. Mixed GC và thu hồi Old region

Young GC chỉ xử lý young regions. Sau khi concurrent marking xác định mức độ sống của object trong old generation, G1 có thể bắt đầu chuỗi **Mixed GC**.

Mỗi Mixed GC thường đưa vào CSet:

- Các young region cần thu gom.
- Một tập con các Old region đã được đánh giá là có thể thu hồi.

G1 không nhất thiết thu gom toàn bộ Old region trong một pause. Nó chia công việc thành nhiều Mixed GC để cân bằng lượng bộ nhớ thu hồi và thời gian dừng. Sau khi hoàn thành chuỗi mixed collection, G1 quay lại chu kỳ young-only cho đến khi cần một chu kỳ marking khác.

Log có thể thể hiện pause như:

~~~text
[info][gc] GC(n) Pause Young (Mixed) (G1 Evacuation Pause) ...
~~~

Mixed GC là nơi ý nghĩa “Garbage-First” thể hiện rõ: G1 ưu tiên các Old region có lượng rác có thể thu hồi hấp dẫn so với chi phí xử lý dự đoán, đồng thời phải tuân theo giới hạn pause.

## 5. Concurrent marking cycle

Để biết Old region có bao nhiêu object sống, G1 cần đánh dấu object reachable trong heap. Concurrent marking cycle có các phase chính:

1. **Initial Mark:** bắt đầu đánh dấu; trong G1, phase này thường được piggyback lên một Young GC pause.
2. **Root Region Scan:** quét các root region liên quan; phase này chạy concurrent nhưng cần hoàn tất trước Young GC tiếp theo.
3. **Concurrent Mark:** đánh dấu object reachable trong khi application thread tiếp tục chạy.
4. **Remark:** hoàn tất thông tin marking và xử lý các cập nhật còn lại trong một pause.
5. **Cleanup:** tổng hợp kết quả, xác định vùng có thể thu hồi và chuẩn bị cho mixed collection.
6. **Mixed collections:** thu gom young regions cùng các Old region được chọn.

Concurrent không có nghĩa toàn bộ chu kỳ không dừng ứng dụng. Initial Mark, Remark, Cleanup và các evacuation pause vẫn có phần stop-the-world; chỉ một số phase marking chạy đồng thời với application thread.

### 5.1. SATB — Snapshot-at-the-Beginning

G1 dùng kỹ thuật marking dựa trên snapshot-at-the-beginning (SATB). Khi concurrent marking bắt đầu, G1 cần bảo toàn khả năng nhận diện các object đã reachable tại thời điểm snapshot, dù ứng dụng tiếp tục thay đổi reference.

Write barrier trước khi ghi đè reference có thể lưu lại giá trị cũ vào buffer để marking xử lý sau. Nhờ vậy, một object từng reachable ở thời điểm snapshot không bị bỏ sót chỉ vì application thread xóa hoặc thay reference trong lúc marking chạy.

SATB là một phần của cơ chế bảo đảm tính đúng đắn của concurrent marking; không nên hiểu nó như một snapshot bất biến được copy toàn bộ heap tại một thời điểm.

### 5.2. Khi nào marking bắt đầu?

G1 cần bắt đầu concurrent marking đủ sớm để thu hồi Old region trước khi heap cạn chỗ. Nó dựa trên ngưỡng occupancy và cơ chế adaptive IHOP (Initiating Heap Occupancy Percent) để dự đoán thời điểm bắt đầu.

Flag liên quan:

~~~text
-XX:InitiatingHeapOccupancyPercent=<percent>
-XX:+/-G1UseAdaptiveIHOP
~~~

Trong các cấu hình hiện đại, adaptive IHOP được bật mặc định trên HotSpot; JVM dùng thông tin từ các chu kỳ trước để điều chỉnh ngưỡng. `InitiatingHeapOccupancyPercent` là giá trị ban đầu/đầu vào cho cơ chế này, vì vậy không nên giả định đặt một phần trăm cố định luôn kiểm soát trực tiếp thời điểm bắt đầu sau khi adaptive policy đã học được dữ liệu.

Chỉ tuning IHOP khi GC log cho thấy marking thường bắt đầu quá muộn hoặc quá sớm so với allocation rate và khả năng thu hồi.

## 6. Remembered set và card table

Vì mỗi pause chỉ thu gom một tập region, G1 cần tìm các reference từ region bên ngoài trỏ vào object trong CSet mà không phải quét toàn bộ heap.

Mỗi region có remembered set (RSet) lưu thông tin về các reference từ vùng khác trỏ vào region đó. G1 dùng card table và write barrier để theo dõi vùng nhớ có thể chứa reference đã thay đổi; thông tin được xử lý và cập nhật vào remembered set.

Ví dụ:

~~~text
Region A (Old) ---- reference ----> Region B (Young, nằm trong CSet)
        |                               |
        +---- RSet của B ghi nhận ------+
~~~

Khi G1 thu gom Region B, nó có thể dùng RSet để tìm các reference từ bên ngoài cần cập nhật sau khi object được copy. Không cần scan mọi object trong toàn bộ Region A.

RSet giúp collection theo region khả thi, nhưng việc quét và cập nhật RSet cũng có chi phí. Một ứng dụng có nhiều reference chéo giữa các region có thể làm tăng chi phí remembered-set processing trong pause.

Write barrier của G1 hỗ trợ cả hai nhu cầu:

- Pre-write barrier phục vụ SATB marking bằng cách ghi nhận reference cũ khi cần.
- Post-write barrier hỗ trợ theo dõi reference chéo region và cập nhật thông tin card/RSet.

Không nên cố loại bỏ write barrier bằng cách thay đổi code ứng dụng theo suy đoán. Trước tiên cần đo pause phase và allocation/reference pattern từ GC log.

## 7. Garbage-First: ưu tiên region có khả năng thu hồi

G1 đánh giá Old region dựa trên lượng object chết có thể thu hồi và chi phí dự đoán để xử lý region đó. Region có nhiều garbage và chi phí thu gom tương đối thấp thường là ứng viên hấp dẫn.

Việc lựa chọn không chỉ dựa trên tỷ lệ rác. G1 còn xét:

- Số byte dự kiến có thể thu hồi.
- Số object sống phải copy.
- Chi phí quét remembered set.
- Chi phí xử lý và cập nhật reference.
- Dự đoán thời gian pause còn có thể sử dụng.
- Mục tiêu thời gian dừng và các giới hạn nội bộ của collector.

Vì vậy, “Garbage-First” không có nghĩa G1 luôn chọn region có tỷ lệ rác cao nhất một cách độc lập với chi phí. Nó tối ưu tập region theo mô hình dự đoán để thu hồi hiệu quả trong giới hạn pause.

### 7.1. Collection Set và pause budget

Trong một pause, G1 dùng pause-time model để dự đoán có thể xử lý bao nhiêu region. Nếu mục tiêu pause ngắn, CSet có thể nhỏ hơn; nếu mục tiêu cho phép pause dài hơn, G1 có thể chọn nhiều region hơn.

Điều này tạo ra sự cân bằng:

| Lựa chọn | Tác động thường gặp |
| --- | --- |
| CSet nhỏ | Pause ngắn hơn nhưng thu hồi ít region mỗi lần; có thể cần nhiều lần collection hơn |
| CSet lớn | Thu hồi nhiều hơn trong một pause nhưng thời gian dừng có thể dài hơn |
| Region có nhiều object sống | Chi phí copy cao, lượng bộ nhớ thu hồi thấp hơn |
| Region nhiều garbage | Có thể thu hồi nhiều dung lượng, nhưng RSet/copy cost vẫn quan trọng |

## 8. Humongous object

G1 xem một object là **humongous** nếu kích thước của object bằng hoặc lớn hơn một nửa region size. Object như vậy được cấp phát trực tiếp vào một hoặc nhiều humongous region liền kề thay vì đi qua Eden như allocation thông thường.

Ví dụ với region size 1 MB, object từ khoảng 512 KB trở lên thuộc nhóm humongous. Object lớn hơn một region có thể chiếm nhiều region liền nhau.

Humongous allocation có các đặc điểm:

- Bắt đầu tại một humongous start region; các region kế tiếp có thể là continuation regions.
- Cần các region liền kề, nên phân mảnh vùng trống có thể khiến allocation khó khăn dù tổng free space còn đáng kể.
- Có thể tạo áp lực lên old generation và ảnh hưởng thời điểm marking/collection.
- Các object humongous không được xử lý giống đường cấp phát Eden thông thường.

GC log có thể hiển thị số `Humongous regions`. Theo dõi chỉ số này nếu ứng dụng thường xuyên tạo byte array lớn, buffer lớn hoặc object lớn khác.

Không nên tăng region size chỉ để làm giảm số object bị xem là humongous mà chưa đo tác động. Region lớn hơn làm thay đổi số region toàn heap, remembered set và độ chi tiết của collection.

## 9. Mục tiêu thời gian dừng với MaxGCPauseMillis

Flag chính:

~~~text
-XX:MaxGCPauseMillis=<milliseconds>
~~~

Giá trị mặc định thường là 200 ms trong HotSpot. Đây là mục tiêu ergonomics: G1 dùng nó để điều chỉnh kích thước young generation và lượng region đưa vào CSet dựa trên dự đoán chi phí.

**Đây không phải hard real-time deadline hoặc giới hạn cứng.** Một pause vẫn có thể vượt mục tiêu do live data lớn, remembered set lớn, object copy chậm, allocation pressure, thiếu vùng đích, hệ điều hành hoặc workload thay đổi.

### 9.1. Hạ mục tiêu pause

Ví dụ:

~~~text
-XX:MaxGCPauseMillis=100
~~~

Giá trị thấp hơn yêu cầu G1 hướng tới pause ngắn hơn. Hệ quả có thể là:

- Young generation nhỏ hơn.
- CSet nhỏ hơn trong một số pause.
- GC xảy ra thường xuyên hơn.
- Nhiều chi phí GC/concurrent work hơn và throughput có thể giảm.
- Nếu allocation rate cao, collector có thể chịu áp lực thu hồi liên tục.

Giảm con số không tự động làm ứng dụng nhanh hơn. Hãy đo percentile pause và throughput trước/sau.

### 9.2. Tăng mục tiêu pause

Ví dụ:

~~~text
-XX:MaxGCPauseMillis=300
~~~

Mục tiêu cao hơn cho G1 nhiều khoảng thời gian hơn để xử lý region trong một pause. Điều này có thể giảm số lần collection hoặc tăng lượng Old region được thu hồi mỗi Mixed GC, nhưng pause có thể dài hơn và độ trễ người dùng tăng.

### 9.3. Chọn mục tiêu theo SLO

Chọn mục tiêu dựa trên latency budget của ứng dụng, không dựa vào giá trị càng thấp càng tốt:

1. Xác định pause percentile đang ảnh hưởng tới request latency.
2. Phân biệt pause do GC với thời gian chờ khác của ứng dụng.
3. Đặt một mục tiêu thử nghiệm phù hợp với SLO.
4. Chạy cùng workload và quan sát pause distribution, throughput, allocation rate và heap occupancy.
5. Giữ thay đổi chỉ khi kết quả tổng thể tốt hơn.

## 10. Evacuation failure và Full GC

G1 cần đủ region trống làm nơi copy object sống ra khỏi CSet. Nếu không có đủ vùng đích, evacuation có thể thất bại hoặc xuất hiện tình trạng `to-space exhausted`.

Nguyên nhân thường gặp:

- Heap quá nhỏ so với live set.
- Allocation rate cao khiến free region bị tiêu thụ nhanh.
- Object sống nhiều nên lượng cần copy lớn.
- Humongous allocation chiếm vùng trống liền kề.
- Concurrent marking bắt đầu quá muộn hoặc mixed collection chưa thu hồi đủ Old region.

Khi evacuation không thể hoàn tất như dự kiến, G1 có thể cần một Full GC. Full GC là stop-the-world và thường rất tốn kém; G1 thực hiện compaction toàn heap như đường phục hồi.

Không xem Full GC là một cách thu gom bình thường. Nếu log cho thấy Full GC hoặc to-space exhaustion, cần điều tra heap sizing, live set, allocation rate, humongous allocation và tiến độ marking.

### 10.1. G1ReservePercent

`-XX:G1ReservePercent` dành một phần heap làm vùng dự trữ để giảm nguy cơ thiếu to-space trong evacuation.

~~~text
-XX:G1ReservePercent=<percent>
~~~

Tăng reserve có thể giảm rủi ro evacuation failure trong một số workload nhưng cũng giảm phần heap còn lại cho ứng dụng. Không tăng tùy tiện nếu chưa có bằng chứng từ log; trước tiên xác định vì sao G1 thiếu region đích.

## 11. Các flag G1 thường dùng hiện nay

| Flag | Mục đích | Ghi chú |
| --- | --- | --- |
| `-XX:+UseG1GC` | Chọn G1 rõ ràng | Hữu ích để tái lập cấu hình; G1 là collector mặc định trong server configurations từ JDK 9 |
| `-Xms<size>` | Heap initial/minimum | Có thể đặt cùng `-Xmx` nếu cần heap size ổn định |
| `-Xmx<size>` | Heap maximum | Phải đủ cho live set và allocation pressure |
| `-XX:MaxGCPauseMillis=<ms>` | Pause-time goal | Mục tiêu mềm, không phải hard bound |
| `-XX:G1HeapRegionSize=<size>` | Chọn region size | Mặc định ergonomics; chỉ chỉnh khi có số liệu |
| `-XX:G1ReservePercent=<percent>` | Reserve cho evacuation | Tăng reserve làm giảm heap hữu dụng |
| `-XX:InitiatingHeapOccupancyPercent=<percent>` | Ngưỡng ban đầu cho concurrent marking | Adaptive IHOP có thể điều chỉnh sau các chu kỳ |
| `-XX:+/-G1UseAdaptiveIHOP` | Bật/tắt adaptive IHOP | Thường nên giữ mặc định trừ khi có dữ liệu tuning |

Không nên chỉnh đồng thời nhiều flag. Thay một yếu tố, chạy cùng workload và so sánh GC log để biết tác động thực.

### 11.1. Tránh cố định young generation một cách tùy tiện

G1 cần tự điều chỉnh kích thước young generation để đáp ứng pause-time goal. Ép một kích thước cố định bằng các thiết lập như `-Xmn` hoặc `-XX:NewRatio` có thể hạn chế khả năng điều chỉnh của G1 và làm mục tiêu pause khó đạt hơn.

Chỉ cố định generation size khi có lý do đo đạc rõ ràng và hiểu tác động tới ergonomics của collector.

## 12. Đọc Unified GC log

JDK 9 đưa vào Unified Logging. Để quan sát G1, có thể bắt đầu với:

~~~text
-Xlog:gc*:stdout:uptime,level,tags
~~~

Muốn xem chi tiết heap region và các phase:

~~~text
-Xlog:gc*=info,gc+heap=debug,gc+phases=debug:stdout:uptime,level,tags
~~~

Hoặc ghi vào file có rotation:

~~~text
-Xlog:gc*=info,gc+heap=debug,gc+phases=debug:file=logs/gc-%p.log:uptime,level,tags:filecount=5,filesize=10M
~~~

Các dấu hiệu nên tìm:

| Dòng log/phase | Câu hỏi cần trả lời |
| --- | --- |
| `Pause Young` | Tần suất và thời gian Young GC ra sao? |
| `Pause Young (Mixed)` | G1 đang thu hồi Old region qua mixed collection? |
| `Concurrent Mark` | Marking bắt đầu/kết thúc khi nào và kéo dài bao lâu? |
| `Eden regions` | Eden thay đổi thế nào sau pause? |
| `Survivor regions` | Có bao nhiêu region chứa object sống sót? |
| `Old regions` | Old region tăng hay giảm sau collection? |
| `Humongous regions` | Có áp lực từ object lớn không? |
| `To-space exhausted` | Có thiếu region đích khi evacuation không? |
| `Pause Full` | G1 đã phải dùng Full GC? Vì sao? |

Không đọc một dòng đơn lẻ rồi kết luận. Ghép pause duration, heap before/after, region count, marking cycle và allocation rate để hiểu nguyên nhân.

## 13. Quan sát JVM bằng jcmd

`jcmd` cho phép truy vấn process đang chạy:

~~~text
jcmd -l
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> VM.command_line
~~~

- `VM.flags` cho biết các JVM flag đang có hiệu lực.
- `GC.heap_info` hiển thị thông tin heap hiện tại theo collector.
- `VM.command_line` giúp kiểm tra tùy chọn khởi chạy.

Chạy lệnh bằng user có quyền phù hợp và trên đúng host/container namespace. Các diagnostic command có chi phí khác nhau; tránh chạy các thao tác có thể gây dừng dài trên production khi chưa đánh giá.

## 14. Ví dụ hoàn chỉnh chạy trên Java 9+

Chương trình sau tạo nhiều batch byte array ngắn hạn, giữ lại một số array sống lâu và tính checksum để xác nhận dữ liệu đã được sử dụng. Chạy với heap nhỏ để quan sát G1 young evacuation và thống kê region. Kích thước 1 MB trong ví dụ có thể được xem là humongous khi region size 1 MB, vì ngưỡng humongous là một nửa region.

**Tệp:** `G1RegionPressureDemo.java`

~~~java
import java.util.ArrayList;
import java.util.List;

public class G1RegionPressureDemo {
    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();
        long checksum = 0;

        for (int batchIndex = 0; batchIndex < 64; batchIndex++) {
            List<byte[]> batch = new ArrayList<>();
            for (int item = 0; item < 8; item++) {
                byte[] data = new byte[256 * 1024];
                data[0] = (byte) (batchIndex + item);
                data[data.length - 1] = (byte) item;
                checksum += data[0] + data[data.length - 1];
                batch.add(data);
            }

            if (batchIndex % 16 == 0) {
                byte[] survivor = new byte[1024 * 1024];
                survivor[0] = (byte) batchIndex;
                retained.add(survivor);
            }

            batch.clear();
        }

        System.out.println("retained arrays: " + retained.size());
        System.out.println("checksum: " + checksum);
    }
}
~~~

Biên dịch với Java 9 API:

~~~text
javac --release 9 G1RegionPressureDemo.java
~~~

Chạy với G1 và log chi tiết:

~~~text
java -Xms32m -Xmx32m -XX:+UseG1GC -XX:MaxGCPauseMillis=100 -Xlog:gc*=info,gc+heap=debug,gc+phases=debug:stdout:uptime,level,tags G1RegionPressureDemo
~~~

Output ứng dụng:

~~~text
retained arrays: 4
checksum: 19712
~~~

GC log sẽ có thêm các dòng thay đổi theo runtime, ví dụ:

~~~text
[info][gc] Using G1
[info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) ...
[info][gc,heap] GC(0) Eden regions: ...
[info][gc,heap] GC(0) Survivor regions: ...
[info][gc,heap] GC(0) Old regions: ...
[info][gc,heap] GC(0) Humongous regions: ...
~~~

Trong lần chạy kiểm thử trên OpenJDK 24.0.2 với heap 32 MB, G1 region size được ergonomics chọn là 1 MB; log thể hiện Young evacuation pause và số Eden, Survivor, Old, Humongous region. Số pause và số region cụ thể phụ thuộc JDK build, máy và workload; không xem chúng là stdout cố định của ứng dụng.

## 15. Quy trình tuning G1 có kiểm soát

1. Đo baseline với workload đại diện: throughput, request latency, allocation rate và pause percentiles.
2. Bật `-Xlog:gc*` và thu thập đủ một chu kỳ tải thực tế.
3. Xác định vấn đề thuộc young allocation, old occupancy, marking, remembered set, humongous allocation hay evacuation.
4. Kiểm tra live set và heap headroom trước khi tăng `-Xmx`.
5. Nếu vấn đề là pause duration, thử điều chỉnh `MaxGCPauseMillis` từng bước và đo trade-off.
6. Nếu marking bắt đầu quá muộn, kiểm tra adaptive IHOP và allocation rate trước khi chỉnh ngưỡng.
7. Nếu có humongous pressure, xem lại kích thước object và cách quản lý buffer; chỉ đổi region size sau khi đo.
8. Nếu evacuation failure, kiểm tra free regions, reserve, live set và tốc độ cấp phát.
9. Chỉ thay một nhóm flag mỗi lần, ghi lại cấu hình và so sánh cùng workload.
10. Tắt log debug/trace khi không còn cần chẩn đoán.

## 16. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ G1 có Eden/Survivor/Old là các vùng vật lý cố định | G1 dùng region có vai trò thay đổi | Theo dõi loại region trong GC log |
| Nghĩ mọi Young GC thu gom Old region | Young GC tập trung vào young regions | Mixed GC mới bổ sung các Old region được chọn |
| Nghĩ Mixed GC thu gom toàn bộ Old heap trong một pause | G1 chọn tập con để giữ pause budget | Theo dõi chuỗi mixed collections |
| Nghĩ Garbage-First chỉ chọn tỷ lệ rác cao nhất | G1 còn xét cost và pause prediction | Đọc CSet/phase timing và reclaimable bytes |
| Coi `MaxGCPauseMillis` là hard deadline | Đây chỉ là mục tiêu ergonomics | Đánh giá percentile thực tế; pause có thể vượt mục tiêu |
| Giảm pause target càng thấp càng tốt | Có thể tăng tần suất GC và giảm throughput | Chọn theo SLO và đo cả latency lẫn throughput |
| Bỏ qua humongous regions | Object lớn có thể cần vùng liền kề và gây áp lực | Kiểm tra kích thước buffer/object và region size |
| Tăng `G1ReservePercent` quá cao | Làm giảm heap hữu dụng cho ứng dụng | Chỉ chỉnh khi log cho thấy thiếu to-space |
| Chỉnh IHOP cố định khi adaptive IHOP đang hoạt động | Ngưỡng có thể được adaptive policy điều chỉnh | Xem trạng thái adaptive và marking cycle trước |
| Ép young generation size | Giảm khả năng tự điều chỉnh của G1 | Để G1 ergonomics quản lý trừ khi có số liệu đặc biệt |
| Bỏ qua `to-space exhausted` | Có thể dẫn tới evacuation failure và Full GC | Điều tra live set, free regions và allocation rate |
| Kết luận từ một lần GC | Workload và GC timing thay đổi theo thời gian | Thu log đủ lâu và đối chiếu cùng workload |

## 17. Quy tắc thực hành

1. Để G1 tự chọn region size trong đa số trường hợp.
2. Hiểu region có vai trò động; không coi generation là vùng cố định.
3. Phân biệt Young GC, Mixed GC và concurrent marking.
4. Nhớ Mixed GC chỉ thu gom tập Old region được chọn trong từng pause.
5. Đọc remembered-set và evacuation phase khi pause cao.
6. Theo dõi humongous regions nếu ứng dụng tạo object lớn.
7. Xem `MaxGCPauseMillis` là mục tiêu mềm, không phải cam kết thời gian thực.
8. Đo cả pause percentile và throughput khi thay đổi pause target.
9. Giữ adaptive IHOP và các ergonomic defaults trừ khi log chỉ ra vấn đề cụ thể.
10. Tránh cố định young generation bằng flag không cần thiết.
11. Dùng Unified Logging để quan sát trước khi tuning.
12. Điều tra to-space exhaustion/Full GC thay vì chỉ tăng heap theo cảm tính.
13. Thử từng thay đổi một và giữ lại số liệu baseline.

## 18. Tự kiểm tra

- G1 chia heap thành gì? Các region có kích thước bằng nhau.
- Region có cố định là Eden/Survivor/Old không? Không; vai trò có thể thay đổi.
- Young GC xử lý nhóm nào? Eden và Survivor region trong young generation.
- Mixed GC thêm nhóm nào vào CSet? Một tập Old region được chọn cùng young regions.
- G1 chọn Old region theo tiêu chí nào? Khả năng thu hồi so với chi phí dự đoán và pause budget.
- Concurrent marking dùng để làm gì? Xác định object sống trong heap/Old regions để chuẩn bị thu hồi.
- SATB là gì? Snapshot-at-the-Beginning, giúp marking bảo toàn liveness tại thời điểm snapshot.
- Remembered set có vai trò gì? Theo dõi reference từ region khác trỏ vào một region.
- Humongous object có ngưỡng thế nào? Kích thước bằng hoặc lớn hơn một nửa region size.
- `MaxGCPauseMillis` có phải hard limit không? Không, đó là mục tiêu tối ưu mềm.
- Hạ pause target có thể gây trade-off gì? GC thường xuyên hơn và throughput thấp hơn.
- Evacuation failure thường liên quan điều gì? Không đủ region đích để copy object sống.
- `G1ReservePercent` làm gì? Dành heap reserve để giảm nguy cơ thiếu to-space.
- Vì sao cần `-Xlog:gc*`? Quan sát pause, region, marking, humongous và evacuation.
- `jcmd <pid> GC.heap_info` dùng làm gì? Xem thông tin heap của JVM đang chạy.

## Tài liệu tham khảo

- [JEP 248: Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248)
- [G1 Garbage Collector — Java 24 Tuning Guide](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector.html)
- [G1 Garbage Collector Tuning — Java 24 Tuning Guide](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html)
- [java command — Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)

Điểm cốt lõi: **G1 chia heap thành region, thu gom theo collection set và ưu tiên Old region có khả năng thu hồi tốt trong pause budget.** `MaxGCPauseMillis` giúp G1 điều chỉnh lượng công việc dự đoán, nhưng không phải cam kết hard real-time; cần đọc GC log và đo workload thực tế để tuning.