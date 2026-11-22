# Phân biệt thu gom trẻ, thu gom hỗn hợp và Full GC trong G1

## 1. Ba kiểu thu gom thường gặp của G1

**G1 (Garbage-First Garbage Collector)** là bộ thu gom rác theo thế hệ của HotSpot JVM. Nó chia Java heap thành nhiều **region**, cho phép ưu tiên những vùng có khả năng giải phóng bộ nhớ hiệu quả mà không phải lần nào cũng xử lý toàn bộ heap. Ba nhóm sự kiện quan trọng khi đọc GC log:

1. **Young-only collection (thu gom trẻ):** chủ yếu thu gom các region thuộc thế hệ trẻ (Eden/Survivor), copy object còn sống sang vùng đích và có thể promote object lên Old.
2. **Mixed collection (thu gom hỗn hợp):** thu gom region trẻ **và một số region Old được chọn**, nhằm lấy lại bộ nhớ Old theo nhiều đợt nhỏ.
3. **Full GC:** thu gom và compact ở phạm vi **toàn heap**, thường là đường đi dự phòng khi G1 không kịp tạo không gian trống hoặc có yêu cầu GC đặc biệt.

Những nhãn log điển hình của HotSpot:

~~~text
Pause Young (Normal) (G1 Evacuation Pause)
Pause Young (Mixed) (G1 Evacuation Pause)
Pause Full (G1 Compaction Pause)
~~~

**Trọng tâm Java 10:** JEP 307, **Parallel Full GC for G1**, được đưa vào JDK 10 để làm đường đi Full GC của G1 **song song** thay vì đơn luồng. Song song ở đây có nghĩa nhiều **GC worker threads** cùng thực hiện các pha cần thiết, **không** có nghĩa các luồng ứng dụng tiếp tục chạy trong Full GC. Full GC **vẫn stop-the-world (STW)**.

G1 thường cố gắng tránh Full GC qua Young-only, concurrent marking và Mixed; không có bảo đảm rằng chỉ vì JDK mới đã song song hóa Full GC thì mọi pause đều ngắn hay Full GC không thể xảy ra.

## 2. Region, Eden, Survivor, Old và collection set

Trong G1, thế hệ trẻ và già không nhất thiết là hai dải bộ nhớ vật lý liền kề. Heap được chia thành các **region** có kích thước cố định trong một runtime, nhưng mỗi region có thể đóng vai trò khác nhau.

| Loại region | Nội dung tiêu biểu | Ý nghĩa với GC |
| --- | --- | --- |
| Eden | Phần lớn object mới tạo | Thường là nguồn rác có vòng đời ngắn |
| Survivor | Object sống sót qua một hoặc nhiều Young GC | Object còn sống có thể chuyển tiếp hoặc được promote |
| Old | Object tồn tại lâu hoặc được promote | Ứng viên reclaim một phần trong Mixed |
| Humongous | Object lớn, thường ít nhất nửa kích thước region | Thuộc quy tắc phân bổ đặc biệt, nhiều region liên tiếp; không copy như object nhỏ thông thường |

G1 chọn một **collection set (CSet)** cho mỗi evacuation pause. CSet là tập region nguồn G1 định xử lý trong lần thu gom đó:

~~~text
Heap gồm nhiều region:
[Eden][Old ][Survivor][Old ][Eden][Old ][Humongous][Old ]

Young-only CSet:
[Eden]     [Survivor]      [Eden]

Mixed CSet:
[Eden][Old candidate][Survivor][Eden][Old candidate]

Full GC:
Thao tác đánh dấu/compact toàn heap, không chỉ một CSet nhỏ.
~~~

Nhìn vào CSet là cách phân biệt **chính xác hơn** so với suy đoán “có tác động đến Old thì phải là Mixed”: Young GC vẫn có thể **promote** object sang Old và G1 có tối ưu thu hồi sớm một số humongous object.

### Evacuation là gì?

Ở đường đi Young/Mixed bình thường, G1 di chuyển những object còn sống khỏi region nguồn:

1. Xác định object có thể truy cập được qua roots/tham chiếu.
2. Copy object còn sống sang region đích phù hợp (Survivor hoặc Old).
3. Điều chỉnh các tham chiếu tới object đã được di chuyển.
4. Giải phóng region nguồn đã evacuation thành công cho lần cấp phát tiếp theo.

Không phải tất cả object đều luôn có thể di chuyển. Object dạng humongous được quản lý đặc biệt; các trường hợp vùng/object bị pin hoặc không đủ vùng đích có thể gây **evacuation failure**.

## 3. Young-only GC: thu gom thế hệ trẻ

### 3.1. Phạm vi và mục đích

Young-only thường dọn các vùng **Eden và Survivor**. Nhiều object Java có vòng đời ngắn, nên cách thu gom thường xuyên vùng trẻ giúp G1 duy trì heap mà chưa cần đụng nhiều Old region.

Một đợt Young-only:

- Là một **stop-the-world evacuation pause**, không phải thu gom hoàn toàn concurrent.
- Thường gom các region Young trong CSet.
- Copy object còn sống sang Survivor hoặc Old tùy tuổi/chính sách.
- Reclaim các region trẻ khi hoàn tất.
- Có thể làm dung lượng **Old tăng** do promotion.

Đừng nói Young-only “chỉ thu gom Eden”: vùng Survivor cũng là thành phần của thế hệ trẻ.

### 3.2. Khi nào xảy ra?

Khi ứng dụng cấp phát nhiều object, Eden dần đầy. G1 dựa vào heuristic về heap, tốc độ cấp phát, tuổi object và pause-time goal để quyết định thời điểm/khối lượng công việc.

Một log **minh họa**, không phải kết quả máy nào cũng phải sinh ra:

~~~text
[0.240s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 70M->15M(256M) 4.200ms
~~~

- `Pause Young (Normal)`: loại thu gom trẻ bình thường.
- `70M->15M(256M)`: heap used trước/sau cùng kích thước heap theo log.
- `4.200ms`: pause time của event.
- `GC(0)`: ID giúp gom các dòng thông tin thuộc cùng sự kiện.

Không suy ra số byte chênh lệch là “rác Eden chính xác” vì thống kê heap chịu ảnh hưởng việc copy, promote và những cơ chế reclaim khác.

### 3.3. Normal, Concurrent Start, Prepare Mixed đều có chữ Young

Có thể gặp:

~~~text
Pause Young (Normal) (G1 Evacuation Pause)
Pause Young (Concurrent Start) (G1 Evacuation Pause)
Pause Young (Prepare Mixed) (G1 Evacuation Pause)
~~~

Cả ba đều là các sự kiện **Young-only** về việc chọn Old CSet thông thường:

- **Normal**: lượt thu gom trẻ bình thường.
- **Concurrent Start**: một Young GC đồng thời khởi động chu kỳ **concurrent marking** để chuẩn bị cho reclaim Old về sau; bản thân event đó chưa phải Mixed.
- **Prepare Mixed**: một Young GC chuyển tiếp sau đánh dấu, chuẩn bị bước vào các Mixed collections; đừng gọi nó là Mixed chỉ vì có chữ `Mixed` trong tên.

Một parser log kiểm `line.contains("Mixed")` quá đơn giản sẽ gộp nhầm **Prepare Mixed** vào **Mixed**.

### 3.4. Vì sao Old có thể tăng sau Young-only?

Một object sống sót đủ lâu có thể được **promote** sang Old. Vì vậy log chi tiết có thể ghi số `Old regions` tăng sau một Young-only. Đây không phải dấu hiệu Mixed; Mixed đòi hỏi trong CSet có **những Old region được chọn để evacuate**, không chỉ có promotion sang Old.

Young-only cũng phải xem những tham chiếu từ Old vào Young để bảo toàn object còn sống. Công việc xử lý cross-region references **không đồng nghĩa** Old region được thêm vào CSet như Mixed.

## 4. Mixed GC: thu gom trẻ cộng một số vùng Old

### 4.1. Đặc điểm

Mixed collection là một G1 evacuation pause trong đó CSet gồm **Young và những Old region được chọn**. Nó giúp lấy lại bộ nhớ của Old generation từng đợt, tránh phải dồn tất cả công việc Old vào một Full GC.

Dòng log điển hình:

~~~text
[2.680s][info][gc] GC(7) Pause Young (Mixed) (G1 Evacuation Pause) 183M->126M(256M) 7.400ms
~~~

**Điểm dễ nhầm:** nhãn bắt đầu bằng `Pause Young`, nhưng phần `(Mixed)` là thông tin phân loại quan trọng. Hãy gọi đúng là **Mixed GC**, không phải Young-only.

### 4.2. Vì sao Mixed không xử lý tất cả Old?

G1 ưu tiên những Old region có tỷ lệ object sống thấp và triển vọng reclaim tốt. Dựa vào thông tin liveness từ chu kỳ đánh dấu, G1 chọn các ứng viên theo dự đoán chi phí:

- Old region chứa nhiều object đã chết có thể giải phóng nhiều vùng trống.
- Old region gần như toàn object sống thường không có lợi bằng khi tính chi phí copy.
- Giới hạn pause time khiến G1 phân chia công việc Old qua **nhiều Mixed collections**.
- G1 có thể kết thúc pha reclaim Old khi các ứng viên còn lại không đáng thu gom trong chu kỳ đó.

Vì vậy **Mixed không có nghĩa compact toàn bộ Old**. Một lần Mixed chỉ thu hồi một tập con Old candidates cùng với Young regions. Những Old region không chọn vẫn giữ nguyên cho giai đoạn khác.

### 4.3. Mixed thường đến sau concurrent marking

Để chọn được Old candidates, G1 cần có thông tin về object còn sống. Nó thu thập thông tin này chủ yếu thông qua chu kỳ **concurrent marking**, phần lớn tiến hành song song với ứng dụng.

Sơ đồ khái niệm:

~~~text
Young-only phase
   |
   +-- Young Normal ...
   |
   +-- Young Concurrent Start
   |       |
   |       +-- Concurrent Mark Cycle
   |       +-- Pause Remark        (STW)
   |       +-- Pause Cleanup       (STW)
   |
   +-- Young Prepare Mixed         (vẫn young-only)
   |
   v
Space-Reclamation phase
   |
   +-- Young Mixed                 (young + chọn old)
   +-- Young Mixed
   +-- ... nếu còn ứng viên có lợi
   |
   v
Young-only phase tiếp theo
~~~

Đây không phải chuỗi sự kiện có số lượng cố định. G1 có thể thực hiện Young Normal trong lúc marking, có thể không tạo Mixed đáng kể nếu ít ứng viên Old phù hợp, và các event cụ thể phụ thuộc JVM/workload.

### 4.4. Concurrent Mark Cycle không phải Mixed hoặc Full

- **Concurrent marking:** tìm object còn sống, phần lớn hoạt động khi các thread ứng dụng vẫn chạy.
- **Remark/Cleanup:** những pause phục vụ hoàn tất chu kỳ mark/chọn ứng viên.
- **Mixed:** một evacuation pause có CSet Young + một số Old.
- **Full:** đường đi compact toàn heap, STW.

Nếu log có `Concurrent Mark Cycle`, không được báo “Full GC đang chạy”. Nếu log có `Pause Remark`, đó cũng không phải Mixed eviction/evacuation.

### 4.5. Vì sao Mixed GC có thể chậm?

Mixed phải xử lý các region trẻ **cộng thêm** lượng object còn sống trong Old regions. Tốc độ copy/scan và số lượng cross-region references có thể khiến pause dài hơn dự đoán.

Oracle gợi ý sử dụng `-Xlog:gc+ergo+cset=debug` để xem G1 dự tính phần Young và Old mất bao nhiêu thời gian, trước khi cân nhắc tinh chỉnh các cờ như:

- `-XX:G1MixedGCCountTarget`: mục tiêu về số đợt mixed trong pha reclaim.
- `-XX:G1MixedGCLiveThresholdPercent`: điều kiện live occupancy của Old region ứng viên.
- `-XX:G1HeapWastePercent`: mức reclaim còn lại có thể chấp nhận trước khi kết thúc pha.

Những cờ này **không phải công thức tăng tốc chung**. Trải công việc ra thêm nhiều đợt có thể giảm từng pause nhưng làm tăng số pause; giới hạn Old candidates có thể giảm độ trễ mà cũng làm giảm lượng bộ nhớ được reclaimed.

## 5. Full GC: thu gom toàn heap và dừng ứng dụng

### 5.1. Bản chất

G1 được thiết kế để tránh phải thường xuyên làm Full GC. Nhưng khi không có đủ vùng trống hoặc các đường đi bình thường không tiến triển, JVM có thể cần **full heap compaction**.

Log ví dụ:

~~~text
[8.200s][info][gc] GC(42) Pause Full (G1 Compaction Pause) 250M->219M(256M) 430.000ms
~~~

Đây là **ví dụ minh họa** để nhận diện chuỗi `Pause Full (G1 Compaction Pause)`. Các con số heap/time thay đổi theo môi trường, không thể coi là stdout chuẩn.

Full GC thường liên quan:

- Áp lực bộ nhớ Old quá cao.
- Concurrent marking không hoàn thành đủ sớm để có Mixed reclamation.
- Tốc độ cấp phát/promotion cao hơn tốc độ reclaim.
- Thiếu vùng đích cho evacuation và các lần thu gom sau không giải quyết được tình trạng.
- Humongous allocation/fragmentation.
- Yêu cầu thu gom từ ứng dụng hoặc công cụ (tùy cấu hình).

### 5.2. Full GC khác Mixed ở phạm vi

Mixed chọn một nhóm Old regions có lợi ích thu gom, làm từng đợt; Full GC thực hiện quá trình mark/sweep/compact ở **phạm vi toàn heap**.

Không được giải thích rằng mọi byte đều được di chuyển. Một số đối tượng đặc biệt như **humongous objects** có giới hạn di chuyển theo cơ chế G1. “Full” diễn tả **phạm vi công việc thu gom/compact**, không phải cam kết mọi object còn sống đều đổi địa chỉ.

Nếu phần lớn object vẫn reachable, Full GC có thể giải phóng rất ít dung lượng và ứng dụng vẫn có thể rơi vào `OutOfMemoryError`.

### 5.3. Full GC có phải luôn được chạy ngay sau evacuation failure?

Không. `Evacuation Failure` là tình huống G1 không thể copy một số object sang region đích. Nó có thể xử lý phần còn lại của pause và cho ứng dụng chạy tiếp; chỉ khi không đủ chỗ/không thể tiến triển về sau, Full GC mới có thể xuất hiện.

Muốn kết luận Full GC đã diễn ra, hãy tìm **event `Pause Full` thực tế**, không dựa vào một dấu hiệu báo trước duy nhất.

### 5.4. System.gc() không bảo đảm một Full GC

`System.gc()` chỉ là lời yêu cầu. Cấu hình HotSpot có thể:

- Cho phép xử lý yêu cầu theo đường đi GC phù hợp.
- Bỏ qua yêu cầu với `-XX:+DisableExplicitGC`.
- Thực hiện một kiểu concurrent GC với `-XX:+ExplicitGCInvokesConcurrent`.

Đừng ép `System.gc()` trong test để tuyên bố chắc chắn đã có Full GC. Một bài demo có thể chỉ quan sát kết quả G1 quyết định, không bắt JVM phải sinh event bằng cách cố tình gây `OutOfMemoryError`.

## 6. Điểm mới Java 10: Parallel Full GC for G1 (JEP 307)

### 6.1. Trước và sau JEP 307

Trước cải tiến này, đường đi Full GC của G1 trong tình huống dự phòng sử dụng thuật toán mark-sweep-compact **đơn luồng**. JEP 307 đưa việc song song hóa các pha Full GC vào **Java 10** để giảm độ trễ trường hợp xấu.

| Tiêu chí | Full GC cũ trước Java 10 | Full GC từ Java 10+ |
| --- | --- | --- |
| Phạm vi | Toàn heap | Toàn heap |
| Kiểu xử lý | Đường đi đơn luồng | **Song song**, có nhiều GC worker |
| Luồng ứng dụng có chạy cùng lúc? | Không, STW | **Không, vẫn STW** |
| Mục đích | Reclaim và compact khi cần | Như cũ, giảm worst-case latency |
| Có bảo đảm không còn Full GC? | Không | Không |
| Có bảo đảm pause tối đa? | Không | Không |

**Parallel** nghĩa là nhiều GC thread hoạt động cùng lúc.

**Concurrent** nghĩa là GC thực hiện một phần công việc đồng thời với **mutator/application threads**.

Do đó, Full GC song song từ JDK 10 **không đồng nghĩa** Full GC concurrent. Nói “JDK 10 đã bỏ Full GC STW của G1” là sai.

### 6.2. Cờ điều khiển số worker

~~~text
-XX:ParallelGCThreads=<number>
-XX:ConcGCThreads=<number>
~~~

- `ParallelGCThreads` ảnh hưởng số thread dùng cho công việc GC **trong các pause song song**, gồm Young/Mixed/Full.
- `ConcGCThreads` điều chỉnh thread làm việc **concurrent**, trong đó có đánh dấu.
- JVM có heuristic riêng dựa trên CPU và heap; không cần đặt hai cờ bằng số core một cách mù quáng.
- Nếu chỉ muốn cải thiện Full GC, tăng `ParallelGCThreads` có thể ảnh hưởng cả Young/Mixed, thay đổi throughput, overhead và mức tranh chấp CPU.

JEP 307 không biến một lệnh Java thông thường thành API tùy chỉnh Full GC. Lợi ích ở mức **HotSpot collector implementation**, không cần sửa source code để bật đường đi Full GC đã được song song hóa.

### 6.3. Tại sao Full GC vẫn có thể rất lâu?

Đường đi song song vẫn phải:

1. Dừng ứng dụng.
2. Tìm các object còn sống trên phạm vi heap.
3. Thực hiện các bước chuẩn bị và compact/điều chỉnh tham chiếu.
4. Hoàn tất để trả quyền chạy lại cho các thread ứng dụng.

Heap quá lớn, live-data set lớn, memory bandwidth giới hạn, CPU quota thấp, object graph phức tạp hoặc nhiều humongous regions đều có thể khiến Full GC tốn thời gian. Một số pha có chi phí không chia hoàn toàn đều giữa các worker.

**Không coi JEP 307 là cách chữa memory leak**: đối tượng còn reachable vẫn tồn tại sau Full GC, dù JVM có nhiều thread hỗ trợ.

## 7. Bảng so sánh tổng hợp

| Thuộc tính | Young-only | Mixed | Full GC |
| --- | --- | --- | --- |
| Region chính trong tập xử lý | Eden + Survivor | Eden/Survivor + **một số Old** | **Toàn heap** |
| Thu hồi Old bằng chọn CSet | Không như Mixed | Có, các Old candidates | Full heap compaction |
| Có thể promote object lên Old? | Có | Có | Thu gom/compact toàn heap, không phải promotion Young thông thường |
| Cần concurrent mark hoàn tất trước? | Không | Thường có để có Old candidates | Không phải điều kiện bắt buộc |
| Stop-the-world? | Có | Có | Có |
| Công việc trong pause có song song? | Có thể | Có thể | **Có, từ Java 10** |
| Nhãn GC log điển hình | `Pause Young (Normal)` | `Pause Young (Mixed)` | `Pause Full` |
| Tần suất/mục đích | Thường xuyên | Theo pha reclaim Old | Dự phòng/đặc biệt |
| Pause goal là hard guarantee? | Không | Không | Không |
| Khi đọc log cần chú ý | Concurrent Start/Prepare Mixed vẫn là Young | `(Mixed)` chọn thêm Old | Full STW không bị xóa bởi song song hóa |

### Những ngoại lệ tinh tế

- Young-only có thể **promote** object lên Old hoặc reclaim một số humongous regions. Điều đó không làm nó thành Mixed.
- Mixed không xử lý **tất cả** Old regions. Nó tránh làm quá nhiều công việc Old trong cùng một pause.
- `Pause Young (Prepare Mixed)` là Young-only chuyển tiếp; `Pause Young (Mixed)` mới là Mixed.
- Các pha `Pause Remark`, `Pause Cleanup` hỗ trợ marking, không được gọi là “Full GC” chỉ vì có STW.
- Không suy rằng G1 sẽ luôn có một Mixed ngay sau mỗi concurrent marking cycle; có thể không đủ ứng viên có lợi.

## 8. Đọc log GC trên JDK hiện đại

### 8.1. Bật G1 và unified logging

Chọn G1 tường minh khi muốn test một kết quả nhất quán về **loại collector**:

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx256m -Xlog:gc=info -cp . G1Workload
~~~

Để ghi log chi tiết vào file:

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx256m -Xlog:gc*=info:file=g1.log:uptime,level,tags -cp . G1Workload
~~~

Khi cần chẩn đoán sâu, tăng level:

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx256m -Xlog:gc*=debug:file=g1-debug.log:uptime,level,tags -cp . G1Workload
~~~

Các con số heap trong lệnh **chỉ dành cho demo**, không phải khuyến nghị mặc định cho ứng dụng thực. `-Xlog` thuộc hệ thống **Unified Logging** và vẫn là cơ chế hiện đại. Mức `debug` có thể tạo log rất lớn hoặc gây overhead; không bật mọi lúc trong benchmark latency.

### 8.2. Nhãn và ý nghĩa

| Chuỗi xuất hiện trong log | Phân loại |
| --- | --- |
| `Pause Young (Normal)` | Young-only |
| `Pause Young (Concurrent Start)` | Young-only bắt đầu một chu kỳ mark |
| `Concurrent Mark Cycle` | Quá trình marking; không phải một Mixed pause |
| `Pause Remark` | Pause marking, không phải Mixed hoặc Full |
| `Pause Cleanup` | Pause kiểm ứng viên/thu hồi liên quan mark |
| `Pause Young (Prepare Mixed)` | Young-only chuyển tiếp |
| `Pause Young (Mixed)` | **Mixed**: Young + Old candidates |
| `Pause Full (G1 Compaction Pause)` | **Full**: heap compaction |
| `Evacuation Failure: Allocation` | Một lý do khó khăn khi copy, không tự xác nhận Full |
| `Evacuation Failure: Pinned` | Có object/region bị pin theo khả năng JVM hiện đại |

Một số log còn thêm cause sau loại pause như `G1 Humongous Allocation` hoặc `System.gc()`. Đó là **lý do kích hoạt**, không thay thế phân loại collection.

### 8.3. Đọc heap và thời gian pause

~~~text
[2.600s][info][gc] GC(12) Pause Young (Mixed) (G1 Evacuation Pause) 180M->120M(256M) 7.600ms
~~~

Đây là **log mẫu** để phân tích, không phải stdout cố định:

- `[2.600s]`: uptime/decoration của log.
- `GC(12)`: ID của một collection.
- `Pause Young (Mixed)`: Mixed GC.
- `180M->120M(256M)`: heap used trước/sau và mức heap được log.
- `7.600ms`: pause duration.

Không khẳng định chênh lệch `60M` là rác Old vì Mixed xử lý cả Young và có thể move nhiều object. Để phân tích từng region, bật `gc+heap` hoặc `gc+ergo+cset` theo nhu cầu.

## 9. Ví dụ Java 17+ hoàn chỉnh để phân loại log

Một chương trình ngắn **không thể bảo đảm** JVM sẽ sinh đủ Young/Mixed/Full theo một thứ tự cố định: quyết định phụ thuộc heap, allocation/promotion rate, CPU và timing.

Vì vậy, ví dụ chính sau dùng **dòng GC log minh họa** cố định để dạy cách phân loại. Nó **không giả vờ thực hiện Full GC thật**.

Lưu file **`G1CollectionTypesDemo.java`**:

~~~java
import java.util.List;

public class G1CollectionTypesDemo {

    enum Kind {
        YOUNG_ONLY,
        MIXED,
        FULL,
        OTHER
    }

    record Sample(String name, String logLine) {}

    static Kind classify(String line) {
        if (line.contains("Pause Full")) {
            return Kind.FULL;
        }

        // Kiểm Mixed trước Pause Young tổng quát.
        if (line.contains("Pause Young (Mixed)")) {
            return Kind.MIXED;
        }

        // Normal, Concurrent Start, Prepare Mixed đều là young.
        if (line.contains("Pause Young (")) {
            return Kind.YOUNG_ONLY;
        }

        return Kind.OTHER;
    }

    public static void main(String[] args) {
        var samples = List.of(
                new Sample(
                        "normal",
                        "GC(1) Pause Young (Normal) (G1 Evacuation Pause)"),
                new Sample(
                        "startMark",
                        "GC(2) Pause Young (Concurrent Start)"
                                + " (G1 Evacuation Pause)"),
                new Sample(
                        "mark",
                        "GC(3) Concurrent Mark Cycle"),
                new Sample(
                        "remark",
                        "GC(3) Pause Remark"),
                new Sample(
                        "prepareMixed",
                        "GC(4) Pause Young (Prepare Mixed)"
                                + " (G1 Evacuation Pause)"),
                new Sample(
                        "mixed",
                        "GC(5) Pause Young (Mixed) (G1 Evacuation Pause)"),
                new Sample(
                        "full",
                        "GC(6) Pause Full (G1 Compaction Pause)")
        );

        for (Sample sample : samples) {
            System.out.println(sample.name() + "="
                    + classify(sample.logLine()));
        }

        long young = samples.stream()
                .filter(s -> classify(s.logLine()) == Kind.YOUNG_ONLY)
                .count();
        long mixed = samples.stream()
                .filter(s -> classify(s.logLine()) == Kind.MIXED)
                .count();
        long full = samples.stream()
                .filter(s -> classify(s.logLine()) == Kind.FULL)
                .count();

        System.out.println("youngOnlyCount=" + young);
        System.out.println("mixedCount=" + mixed);
        System.out.println("fullCount=" + full);
        System.out.println("prepareMixedIsYoung="
                + (classify(samples.get(4).logLine())
                        == Kind.YOUNG_ONLY));
        System.out.println("mixedNotYoungOnly="
                + (classify(samples.get(5).logLine())
                        != Kind.YOUNG_ONLY));
    }
}
~~~

Biên dịch và chạy trên **Java 17+**:

~~~bash
javac --release 17 G1CollectionTypesDemo.java
java G1CollectionTypesDemo
~~~

**Stdout chính xác:**

~~~text
normal=YOUNG_ONLY
startMark=YOUNG_ONLY
mark=OTHER
remark=OTHER
prepareMixed=YOUNG_ONLY
mixed=MIXED
full=FULL
youngOnlyCount=3
mixedCount=1
fullCount=1
prepareMixedIsYoung=true
mixedNotYoungOnly=true
~~~

### Giải thích và giới hạn của ví dụ

1. `Normal`, `Concurrent Start`, `Prepare Mixed` đều là các sự kiện Young-only.
2. `Concurrent Mark Cycle` và `Pause Remark` thuộc marking, nên `OTHER`.
3. `Pause Young (Mixed)` phải được ưu tiên nhận diện trước quy tắc `Pause Young` tổng quát.
4. `Pause Full` được phân loại FULL.
5. Trong tập bảy mẫu, có ba Young-only, một Mixed, một Full và hai sự kiện khác.
6. Đây là bộ phân loại **đơn giản dành cho học tập**, không phải parser production cho mọi kiểu log HotSpot. Log thực có thể có decorations, nhiều dòng cùng `GC(id)`, giai đoạn con, reason tags và khác biệt phiên bản.

Khi cần phân tích log thực, dùng định dạng/tags nhất quán trên JDK mục tiêu, kiểm chính xác event summary và thêm test với các mẫu log thực tế.

## 10. Quan sát hành vi G1 thật mà không ép số lượng GC

Lưu file **`G1Workload.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class G1Workload {

    private static volatile int checksum;

    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();

        for (int i = 0; i < 20_000; i++) {
            byte[] block = new byte[4 * 1024];
            block[0] = (byte) i;
            checksum += block[0];

            // Giữ lại một phần; những mảng khác sớm thành rác.
            if (i % 400 == 0) {
                retained.add(block);
            }
        }

        System.out.println("retained=" + retained.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 G1Workload.java
java -XX:+UseG1GC -Xms128m -Xmx256m -Xlog:gc*=info:file=g1.log:uptime,level,tags G1Workload
~~~

**Stdout ứng dụng chính xác:**

~~~text
retained=50
~~~

File `g1.log` có thể ghi một số event, nhưng **không có bảo đảm** sẽ xuất hiện Mixed hoặc Full trong một lượt chạy như vậy. Số lượng GC, lý do và pause time phụ thuộc heap, thời điểm, GC heuristics và hệ điều hành. Vì thế, việc không thấy `Pause Full` ở test nhỏ này không chứng minh ứng dụng không thể có Full trong production.

### Không dùng System.gc() để chứng minh Full GC bắt buộc

Một số cờ như `-XX:+DisableExplicitGC` có thể khiến JVM bỏ qua lời gọi, hoặc `-XX:+ExplicitGCInvokesConcurrent` cho phép thực hiện đường đi concurrent thay vì Full GC theo giả định.

Nếu muốn kiểm Full GC thực, hãy phân tích **GC log từ tình huống xảy ra thật** hoặc từ môi trường tái hiện được, không thiết kế một unit test dựa vào ý tưởng `System.gc()` luôn ra một Full GC.

### Bài học từ log thật

- Xem `Pause Young (Normal)` có xảy ra thường xuyên không.
- Khi G1 đạt ngưỡng marking, xem `Pause Young (Concurrent Start)`, `Concurrent Mark Cycle`, `Pause Remark` và `Pause Cleanup`.
- Sau đó, nếu có Old candidates đáng reclaim, tìm `Pause Young (Mixed)`.
- Nếu có `Pause Full (G1 Compaction Pause)`, xem sự kiện trước đó và mức heap còn sống.
- Kiểm `Evacuation Failure`, humongous regions và old occupancy khi GC gặp áp lực.
- Phân biệt số liệu của ứng dụng (latency, throughput) với chi phí quan sát do bật log.

## 11. G1 tuning: hành động theo triệu chứng

### 11.1. Bắt đầu bằng cấu hình đơn giản

Oracle khuyên thường nên để G1 tự điều chỉnh nhiều tham số. Một ví dụ chọn collector, heap và pause goal:

~~~bash
java -XX:+UseG1GC -Xms512m -Xmx2g -XX:MaxGCPauseMillis=200 -jar app.jar
~~~

Các mức `512m`, `2g` và `200` ms chỉ mang tính **minh họa**, không phải khuyến nghị mặc định. `MaxGCPauseMillis` là **mục tiêu mềm**. G1 cố gắng đạt mục tiêu với xác suất cao, chứ không bảo đảm một pause không bao giờ vượt ngưỡng.

Đừng vội cố định Young size bằng `-Xmn`: điều này có thể làm mất khả năng G1 tự cân đối Young generation theo pause-time goal.

### 11.2. Young GC quá nhiều hoặc chậm

Xem:

- Allocation rate của object và khả năng giảm tạo object tạm.
- Tỷ lệ object sống sót, promotion rate sang Old.
- Cỡ Young generation và khả năng JVM tự điều chỉnh.
- Object copy/scan roots/remembered sets cost.
- CPU budget, heap thực, container quota.
- Độ trễ ứng dụng và throughput thay vì chỉ một GC event.

Không kết luận cứ Young lớn hơn là tốt: số event có thể giảm nhưng mỗi pause lại lâu hơn.

### 11.3. Mixed GC quá dài

Kiểm `gc+ergo+cset`: mất bao nhiêu thời gian dự kiến cho Young và Old. Nếu cần, cân nhắc `-XX:G1MixedGCCountTarget`, `-XX:G1MixedGCLiveThresholdPercent`, `-XX:G1HeapWastePercent` theo log.

Trải reclaim Old ra nhiều event có thể giảm thời gian mỗi pause nhưng tăng số lượng GC; bỏ bớt region sống nhiều sẽ giảm chi phí mà cũng có thể giảm lượng reclaimed. Cần benchmark cùng workload và theo dõi cả latency lẫn hiệu quả giải phóng bộ nhớ.

### 11.4. Full GC quá thường xuyên

Nên điều tra **nguyên nhân gốc**:

1. Heap quá nhỏ so với **live-data set**?
2. Có cache/collection giữ reference vượt nhu cầu, gây retention hoặc leak?
3. Promotion rate hoặc humongous allocation tăng?
4. Concurrent marking không kịp kết thúc?
5. Có `System.gc()` hoặc công cụ bên ngoài yêu cầu Full?
6. Có mất cân đối CPU, quota, region fragmentation hay pressure từ container?
7. Sau Full, heap giảm ít hay nhiều?

Nếu Full GC giải phóng rất ít bộ nhớ, ưu tiên phân tích reference graph, heap dump/JFR/profiler và các cấu trúc giữ object. Tăng heap có thể làm giảm áp lực nhất thời nhưng không tự sửa leak.

### 11.5. Vì sao song song hóa Full chưa đủ?

Một Full GC của G1 từ Java 10 có thể dùng nhiều GC worker, nhưng application threads **vẫn phải dừng**. Nếu live set lớn, CPU thiếu hoặc memory bandwidth bị giới hạn, pause vẫn có thể rất dài.

Thay đổi `ParallelGCThreads` tác động công việc song song ở cả Young/Mixed/Full. `ConcGCThreads` là nhóm khác cho concurrent work. Nếu chưa có số liệu cho thấy JVM chọn số worker không phù hợp, tránh ép cấu hình chỉ dựa trên tổng số CPU logic.

## 12. Các lỗi hiểu nhầm phổ biến

| Nhận định sai | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Young GC chỉ thu gom Eden | CSet Young còn có Survivor | Hiểu Eden + Survivor, và promotion |
| Young-only hoàn toàn không động tới Old | Có promotion/cross-region refs/humongous reclaim | Phân biệt Old CSet với ảnh hưởng gián tiếp |
| Mixed xử lý tất cả Old | Nó chỉ chọn một số Old candidates | Kiểm collection set và liveness |
| Hễ có chữ Young là Young-only | `Pause Young (Mixed)` là Mixed | Đọc đầy đủ nhãn |
| `Prepare Mixed` đã là Mixed | Đây là Young collection chuyển tiếp | Chỉ `(Mixed)` mới là Mixed |
| `Concurrent Mark Cycle` = Full GC | Marking phần lớn concurrent | Không gộp marking với full compaction |
| G1 Full GC trên JDK 17 vẫn đơn luồng | JEP 307 đã song song hóa từ Java 10 | Full parallel nhưng STW |
| Full parallel = không dừng ứng dụng | Parallel khác concurrent | Hiểu GC worker với mutator threads |
| MaxGCPauseMillis là SLA cứng | G1 chỉ cố đạt soft target | Đo p95/p99 |
| Evacuation Failure tức thì là Full | G1 có thể tiếp tục không Full | Kiểm `Pause Full` thực |
| Full luôn giải phóng nhiều heap | Object vẫn reachable không thể reclaim | Điều tra live set |
| System.gc luôn kích hoạt Full | JVM có cờ bỏ qua/chuyển concurrent | Không dùng làm test bắt buộc |
| Tăng GC threads chỉ làm Full nhanh | Ảnh hưởng nhiều pause và CPU overhead | Đo tổng thể |
| Mixed luôn xuất hiện sau mọi mark | Có thể không đủ candidates | Xem Cleanup và điều kiện chọn |
| Cứ tăng -Xmn sẽ giảm pause | Cố định Young có thể gây pause dài | Giữ adaptive sizing |
| Nhãn Minor/Major ở collector khác giống G1 | Tên event tùy collector | Xác định G1 trước khi parse |

## 13. Checklist và tự kiểm tra

### Checklist khi điều tra GC

1. Xác nhận JVM thực dùng G1, kiểm JDK build và GC flags.
2. Thu `-Xlog:gc*=info`; chỉ bật debug khi cần.
3. Tách Young Normal, Young Concurrent Start, Young Prepare Mixed, Young Mixed và Pause Full.
4. Không đếm Remark, Cleanup hay Concurrent Mark Cycle như Full.
5. Đọc GC ID, heap used trước/sau, thời gian pause và biến động Old.
6. Quan sát `Evacuation Failure` và humongous regions trước Full.
7. Ghi nhận CPU quota, heap, workload, thời gian warm-up và JDK.
8. Đo p95/p99 latency và throughput thực thay vì một log điển hình.
9. Benchmark không bật logging debug quá nhiều.
10. Nếu điều chỉnh cờ GC, so kết quả trước/sau trong điều kiện nhất quán.

### Câu hỏi tự đánh giá

**Câu 1.** Young-only chỉ thu gom Eden?

**Đáp án:** Không, có cả Survivor trong CSet Young; object còn sống có thể promote lên Old.

**Câu 2.** `Pause Young (Mixed)` có phải Young-only?

**Đáp án:** Không. Đây là Mixed collection vì CSet có Young và một số Old regions.

**Câu 3.** `Pause Young (Prepare Mixed)` đã thu gom Old candidates?

**Đáp án:** Nó là Young collection chuyển tiếp, không phải Mixed evacuation bình thường.

**Câu 4.** Mixed có xử lý toàn bộ Old như Full không?

**Đáp án:** Không. Nó chọn một số Old candidates, thường phân chia qua nhiều pause.

**Câu 5.** Concurrent marking có phải Full GC?

**Đáp án:** Không. Nó dùng để nhận diện object sống, phần lớn diễn ra đồng thời với ứng dụng.

**Câu 6.** Java 10 thay đổi gì về G1 Full GC?

**Đáp án:** JEP 307 song song hóa đường đi Full GC nhằm giảm worst-case pause latency.

**Câu 7.** Full GC sau Java 10 còn STW không?

**Đáp án:** Có. Song song giữa GC workers không đồng nghĩa concurrent với ứng dụng.

**Câu 8.** Evacuation failure có chắc sinh Full ngay không?

**Đáp án:** Không. G1 có thể xử lý pause hiện tại và tiếp tục; Full là trường hợp khi không tiến triển được hoặc do nguyên nhân khác.

**Câu 9.** Một Full GC giải phóng rất ít heap nói lên điều gì?

**Đáp án:** Có thể live-data set lớn hoặc object bị giữ bởi tham chiếu; cần phân tích root/reference graph.

**Câu 10.** Vì sao không ép `System.gc()` rồi kỳ vọng luôn có `Pause Full`?

**Đáp án:** JVM có thể bỏ qua hoặc dùng cơ chế concurrent tùy option.

**Câu 11.** `-XX:ParallelGCThreads` chỉ điều khiển Full?

**Đáp án:** Không. Nó ảnh hưởng công việc GC song song ở Young/Mixed/Full.

**Câu 12.** Nên tăng `-Xmn` để G1 tự tối ưu pause?

**Đáp án:** Không mặc định; cố định Young size có thể cản cơ chế tự điều chỉnh của G1.

## 14. Nguồn chính thức hiện còn áp dụng

- [Oracle Java SE 26 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html): young-only phase, space-reclamation phase, Mixed, Full GC, CSet và evacuation failure.
- [Oracle Java SE 25 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html): hướng dẫn đọc `Pause Full (G1 Compaction Pause)`, tìm nguyên nhân Full và mixed pause.
- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): phân loại Young/Mixed/Full theo chu kỳ G1 của Java 17.
- [Oracle Java SE 17 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html): cấu hình/diagnostic trên Java 17.
- [OpenJDK JEP 307 — Parallel Full GC for G1](https://openjdk.org/jeps/307): thay đổi Java 10 giúp G1 Full GC chạy song song, vẫn là STW.
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+UseG1GC` và `-Xlog`.
- [OpenJDK JEP 423 — Region Pinning for G1](https://openjdk.org/jeps/423): các trường hợp object/region bị pin trong G1 hiện đại.
- [Dev.java — The G1 Garbage Collector](https://dev.java/learn/jvm/tool/garbage-collection/g1gc-overview/): tổng quan và hướng dẫn G1 hiện hành.

**Ghi nhớ:** **Young-only** xử lý các region trẻ; **Mixed** xử lý region trẻ **cộng một tập con Old** sau khi có thông tin marking; **Full GC** compact **toàn heap** và là **STW**. Từ Java 10, JEP 307 giúp G1 Full GC **song song** nhưng không biến nó thành concurrent. Khi chẩn đoán, phải đọc đúng nhãn log, thời gian pause, phạm vi CSet và áp lực bộ nhớ thực tế.