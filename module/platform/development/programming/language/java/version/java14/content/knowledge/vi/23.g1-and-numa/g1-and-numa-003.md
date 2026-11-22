# Cấp phát theo vùng của G1 (G1 Region-Based Allocation)

## 1. Mục tiêu của bài học

**Garbage-First Garbage Collector (G1 GC)** tổ chức Java heap thành nhiều **heap regions** có kích thước bằng nhau, thay vì coi Eden, Survivor và Old như ba vùng vật lý lớn, liên tục và cố định. Khi ứng dụng tạo đối tượng, G1 sử dụng các vùng phù hợp để cấp phát; khi GC chạy, G1 lựa chọn những nhóm vùng cần thu hồi rồi **sao chép các đối tượng còn sống** sang vùng đích trước khi tái sử dụng vùng nguồn.

Bài học tập trung vào câu hỏi **“Cấp phát theo vùng của G1 diễn ra như thế nào?”** trong ngữ cảnh **G1 và NUMA**, bao gồm:

- Heap region là gì? Vì sao region khác với một Java object hoặc một TLAB?
- Mảng và object thông thường được cấp phát ở **Eden regions** ra sao?
- Vai trò của **Thread-Local Allocation Buffer (TLAB)**, đường cấp phát nhanh và đường cấp phát khi TLAB không đủ chỗ.
- Phân biệt **Free, Eden, Survivor, Old** và **Humongous regions**.
- Điều gì xảy ra với các vùng khi **Young GC** hoặc **Mixed GC** chọn chúng để thu hồi?
- Tại sao object lớn có đường cấp phát đặc biệt và liên quan tới **ngưỡng bằng nửa region**?
- G1 sử dụng region để cải thiện khả năng quản lý **NUMA memory locality** như thế nào; tính năng này có điều kiện phần cứng/hệ điều hành gì?
- Đọc **Unified GC Logging** để thấy số region thực tế và kiểm chứng bằng một chương trình Java 17+.

**Phiên bản và tính hiện hành:** G1 đã là một garbage collector chuẩn từ lâu, đang được sử dụng trong các JDK hiện đại. Tối ưu **NUMA-aware memory allocation cho G1** xuất hiện trong **Java 14 (JEP 345)** và vẫn có ý nghĩa trên những hệ thống NUMA được hỗ trợ. Phần thực hành sử dụng **Java 17+ và các tùy chọn HotSpot đang được hỗ trợ**; không dạy cách ghi log `-XX:+PrintGCDetails` kiểu cũ như phương pháp chính, và không sử dụng các tính năng legacy/preview.

## 2. Khái niệm cốt lõi: heap region

Một **heap region** của G1 là một dải địa chỉ heap **liên tục trong không gian địa chỉ ảo**, có kích thước cố định trong một JVM đang chạy. G1 chia heap thành nhiều region bằng nhau và quản lý trạng thái của chúng.

Sơ đồ đơn giản, **không phải ảnh chụp heap thực tế**:

~~~text
Java heap (virtual address space)
+------+------+------+------+------+------+------+------+
| Eden | Old  | Free | Eden | Surv | Old  | Hum. | Eden |
+------+------+------+------+------+------+------+------+
   R0     R1     R2     R3     R4     R5     R6     R7

R0 ... R7: mỗi region cùng một kích thước.
Eden, Survivor, Old là các tập region theo vai trò.
Các region cùng thế hệ không bắt buộc nằm cạnh nhau.
~~~

Các ý quan trọng:

1. **Region là đơn vị cấp phát và thu hồi bộ nhớ ở cấp quản lý G1.** Một region thường chứa **nhiều object**, không phải “một object ứng với một region”.
2. **Kích thước region được chọn khi JVM khởi động** tùy cấu hình và heap maximum, trừ khi được chỉ định bằng `-XX:G1HeapRegionSize=...`.
3. Tại một thời điểm, một region có thể còn trống hoặc được phân công cho **young/old generation**.
4. **Eden và Survivor là hai vai trò thuộc young generation**; Old thuộc old generation; Humongous dùng riêng cho object rất lớn và được tính trong old generation.
5. Một region có thể **đổi vai trò qua các chu kỳ GC**, ví dụ từ Free thành Eden, sau đó được thu hồi để trở lại Free rồi được cấp lại dưới vai trò khác.
6. **Phân vùng logic** khác với khái niệm các trang RAM vật lý của NUMA. Việc biết region thuộc Eden không cho phép suy ra mọi trang nhớ của region đó nằm trên NUMA node nào.

### 2.1. Kích thước region có phải luôn là 1 MB hay 32 MB?

**Không.** HotSpot dùng heuristic chọn kích thước dựa trên heap (hướng tới khoảng **2.048 regions** khi thuận lợi), và thông thường các giá trị **mặc định được lựa chọn tự động** ở cỡ MiB, với giá trị tối đa theo heuristic là 32 MiB trong tài liệu Oracle hiện hành. Tập giá trị **được phép cấu hình tường minh** có thể rộng hơn tùy bản JDK. Vì vậy không nên học thuộc cứng “G1 chỉ có thể có 1–32 MB” cho mọi Java hiện đại.

Kích thước region có thể được yêu cầu bằng:

~~~bash
-XX:G1HeapRegionSize=2m
~~~

Trong một lệnh `java`, đây là **tùy chọn JVM**, không phải lệnh chạy riêng. `2m` tương ứng **2 MiB = 2.097.152 bytes** theo cách hiểu dung lượng thông thường của HotSpot.

- Giá trị phải phù hợp quy tắc của JDK đang sử dụng, thường ở dạng **lũy thừa của 2** trong khoảng mà JVM hỗ trợ.
- Chọn quá nhỏ làm tăng số region và chi phí metadata/remembered sets.
- Chọn quá lớn làm giảm độ linh hoạt khi lựa chọn region để GC, đồng thời **tăng ngưỡng humongous**.
- **Không tối ưu `G1HeapRegionSize` chỉ vì thấy trong một bài hướng dẫn.** Hãy bắt đầu bằng giá trị ergonomic mặc định, đo workload thực, rồi mới thử thay đổi có kiểm soát.

Để biết JVM **thực sự** chọn region size bao nhiêu, đọc dòng `Heap Region Size` từ GC initialization log, không tự suy từ `-Xmx`.

## 3. Vai trò của từng loại region

| Loại region | Chứa gì? | Khi nào được dùng? | Được tái sử dụng ra sao? |
| --- | --- | --- | --- |
| **Free** | Region chưa được dùng để chứa object sống theo vai trò hiện tại | G1 cần thêm không gian | Được phân công thành Eden, vùng đích GC, Old hoặc các mục đích khác |
| **Eden** | Phần lớn object mới thông thường | Java mutator threads đang cấp phát | Young GC evacuate object sống, rồi giải phóng region nguồn |
| **Survivor** | Object của young generation sống qua các lần GC | Khi Young GC sao chép object sống | Lần GC tiếp theo có thể sao chép tiếp sang Survivor mới hoặc promote lên Old |
| **Old** | Object đã được promote hoặc object sống lâu | Khi tuổi/heuristic cho biết object nên ở old generation | Mixed GC/Full GC và các cơ chế dọn dẹp tương ứng |
| **Humongous** | Object kích thước **lớn hoặc bằng một nửa region** | Có yêu cầu cấp phát object rất lớn | Thường được thu hồi theo cơ chế riêng; không evacuate như object thông thường |

### 3.1. Eden/Survivor/Old không phải ba dải địa chỉ cứng

Không nên hình dung:

~~~text
[Tất cả Eden liên tục][Tất cả Survivor liên tục][Tất cả Old liên tục]
~~~

Đó **không phải điều kiện G1 cần duy trì**. Eden, Survivor và Old là **tập hợp các regions** được gán vai trò tương ứng, có thể xen kẽ các vùng khác trong heap. Chính đặc điểm này giúp G1 điều chỉnh kích thước young generation linh hoạt bằng cách tăng/giảm **số region** mà không nhất thiết di chuyển ranh giới của một dải địa chỉ liên tục.

### 3.2. Free region không có nghĩa là Java object vừa tạo có nguyên một region riêng

G1 quản lý vùng cấp phát ở cấp region, còn việc tạo từng object thường xảy ra qua **TLAB** hoặc đường cấp phát tương ứng. Một region Eden có thể chứa nhiều TLAB thuộc các Java threads khác nhau cùng các object được cấp phát trực tiếp ngoài TLAB.

## 4. Luồng cấp phát của một object nhỏ

Ví dụ:

~~~java
StringBuilder builder = new StringBuilder();
byte[] small = new byte[4096];
~~~

Đây là **mã minh họa đặt trong một method**. Giả sử HotSpot G1 thông thường, các object nhỏ được tạo ở **young generation/Eden** trừ khi compiler tối ưu làm chúng không cần cấp phát trên heap.

Luồng logic:

~~~text
Ứng dụng: new SomeObject()
       |
       v
JIT / runtime xác định có cần cấp phát trên heap không?
       |
       +-- Có thể loại qua escape analysis / scalar replacement:
       |      không nhất thiết tạo object heap vật lý
       |
       +-- Cần cấp phát thật:
                |
                v
          Có chỗ trong TLAB của thread?
                |
       +--------+--------------------------+
       |                                   |
      Có                                  Không
       |                                   |
       v                                   v
 Cấp phát nhanh                        Xin TLAB mới /
 trong TLAB                            cấp phát ngoài TLAB
       |                                   |
       +---------------+-------------------+
                       |
                       v
                  Object ở Eden
                       |
                       v
              Young GC sau đó chọn
              Eden regions để xử lý
~~~

Đây là sơ đồ **mô tả khái niệm**, không phải trace bytecode chính xác của mọi máy. Cấp phát thực tế còn tùy C1/C2 JIT, kiến trúc CPU, object size, heap pressure và cấu hình JVM.

### 4.1. TLAB là gì?

**Thread-Local Allocation Buffer (TLAB)** là một phần không gian cấp phát dành cho một thread để nhanh chóng tạo object nhỏ với ít tranh chấp hơn. TLAB thường được lấy từ **Eden region**; khi hết chỗ, thread cần một vùng cấp phát mới hoặc phải đi qua đường cấp phát chậm hơn.

- TLAB **không phải một thế hệ GC**, cũng **không phải G1 region**.
- Một Eden region có thể cấp phát chỗ cho **nhiều TLAB**.
- Kích thước TLAB và khả năng phân phối thường được HotSpot tự điều chỉnh.
- Các object lớn hơn mức thích hợp cho TLAB có thể được cấp phát **ngoài TLAB**, nhưng **không phải mọi object ngoài TLAB đều là Humongous**.
- Để xem mức cấp phát và site tạo object, có thể sử dụng **JFR allocation events** hoặc GC/JVM profiling phù hợp; bản thân số lần `new` trong source không phải số allocation thực sự sau tối ưu JIT.

**Cần tránh:** nói rằng “mỗi thread được cấp một region Eden riêng”. Chính xác hơn, thread có thể có **TLAB riêng**, còn G1 quản lý các **Eden regions** dùng làm nguồn cấp phát TLAB.

### 4.2. Tại sao cấp phát tại Eden lại nhanh?

Với đường nhanh thông thường, HotSpot có thể sử dụng thao tác tiến con trỏ trong phần bộ nhớ còn trống của TLAB. Vì vậy phần lớn object sống ngắn có thể được tạo nhanh, rồi **được thu hồi theo nhóm region** trong Young GC thay vì trả từng object về bộ cấp phát hệ điều hành ngay khi hết tham chiếu.

Một object như `new byte[4096]` **không có API Java chuẩn** cho biết region cụ thể chứa nó. Các log GC cho thấy thống kê theo vùng; JFR/diagnostics có thể giúp quan sát allocation pressure, nhưng không nên quảng cáo một method Java đơn giản như `getRegion(object)` khi nó không tồn tại.

## 5. Khi Eden thiếu chỗ: G1 cấp thêm region và kích hoạt Young GC

Khi ứng dụng liên tục tạo object nhỏ:

1. Java threads tiêu thụ các TLAB đang có trong Eden.
2. Runtime tiếp tục cấp phát TLAB/đường ngoài TLAB từ không gian Eden sẵn có.
3. Khi cần, G1 **gán thêm Free regions thành Eden regions** trong phạm vi chính sách quản lý young generation.
4. Khi đến ngưỡng do G1 tính toán, GC có thể kích hoạt **Young GC** để giải phóng phần lớn Eden và chuẩn bị chỗ cho đợt cấp phát tiếp theo.

**Không có quy tắc cứng** rằng cứ “đầy đúng 1 region” là phải chạy Young GC. Quyết định GC liên quan young-generation target, không gian trống, object allocation rate, dự báo chi phí pause và nhiều điều kiện khác.

### 5.1. Kích thước young generation động

G1 quan sát lịch sử pause và hoạt động ứng dụng để chọn lượng công việc GC phù hợp với **mục tiêu pause time**. Số Eden regions được dùng giữa hai GC có thể thay đổi qua các chu kỳ.

Ví dụ, lệnh:

~~~bash
-XX:MaxGCPauseMillis=200
~~~

đặt **mục tiêu** pause time để G1 điều chỉnh heuristic. Nó **không phải giới hạn thời gian cứng**, không hứa mọi GC chắc chắn dưới 200 ms. Đây là tham số cấu hình tùy chọn, không nên thay nếu chưa có vấn đề đo được.

Tương tự, việc khóa young-generation size bằng các tùy chọn không phù hợp có thể làm giảm tính linh hoạt của G1. Trong vận hành thực tế, thông thường hãy ưu tiên **G1 defaults**, chỉ điều chỉnh sau khi đọc log và kiểm chứng tác động lên throughput/latency.

## 6. Young GC xử lý vùng nguồn và vùng đích như thế nào?

**Evacuation** là quá trình G1 sao chép **object còn sống** từ region thuộc **Collection Set (CSet)** sang region đích, cập nhật các reference, rồi giải phóng vùng nguồn khi đã chuyển thành công.

Sơ đồ ý tưởng:

~~~text
Trước Young GC:
  Eden R1:    [live A][garbage][live B][garbage]
  Eden R2:    [garbage][live C][garbage]
  Survivor:   [live D]
  Free:       [                  ] [                ]

Sau Young GC thành công:
  Survivor mới: [A][B][C] (object phù hợp giữ ở young)
  Old mới/cũ:   [D]       (nếu object đã đến điều kiện promote)
  R1, R2 ...:   Free / tái sử dụng được
~~~

Đây chỉ là **minh họa**, quyết định object nào vào Survivor hay Old tùy tuổi, chính sách tenuring, chỗ đích và heuristic tại thời điểm GC.

Các điểm cần ghi nhớ:

- G1 **không xóa từng object chết** trong Eden như thao tác `free(object)` của C. Nó xác định object sống cần giữ, **copy object sống**, rồi xử lý region nguồn.
- Object đã sống qua một lần GC có thể đi tới Survivor; object sống đủ lâu hoặc do các điều kiện GC có thể được **promote** lên Old.
- Sau khi vùng nguồn đã được xử lý thành công, vùng có thể trở về **Free** để G1 sử dụng cho các lần cấp phát sau.
- Các thread GC có thể làm việc **song song** trong các stop-the-world pauses để evacuate nhiều vùng.
- Bản thân object Java vẫn có danh tính logic theo ngữ nghĩa Java; GC chịu trách nhiệm cập nhật reference sau khi di chuyển object vật lý.

### 6.1. Collection Set là tập vùng **cần thu hồi**, không phải tập vùng để cấp phát mới

Trong Young GC, CSet gồm các young regions đang cần xử lý và một số điều kiện liên quan. Khi **Mixed GC** diễn ra, G1 còn lựa chọn các **old regions phù hợp** để thu hồi bên cạnh young regions.

**Không nhầm `Collection Set` với tập Free regions**: CSet là **nguồn** để xử lý object sống và thu hồi chỗ; Free regions có thể được dùng làm **đích** cho object được copy và làm nguồn cấp phát sau đó.

### 6.2. “Garbage-First” có nghĩa gì?

G1 ưu tiên những vùng mà theo ước lượng sẽ **thu hồi được nhiều bộ nhớ có hiệu quả**, đặc biệt trong Mixed GC, và cân đối lượng công việc theo pause target. Một old region chứa ít object sống có thể hấp dẫn để thu hồi vì chi phí copy object còn sống thấp hơn một vùng chứa gần đầy object sống.

Tuy nhiên, **không phải cứ chọn vùng nhiều rác nhất là toàn bộ CSet luôn chỉ có vùng đó**. G1 còn phải xử lý young regions, ràng buộc thời gian, kết nối references giữa các vùng và các điều kiện đặc biệt.

## 7. Remembered Set: vì sao có thể thu hồi từng nhóm region?

Khi GC một phần heap, có thể có reference từ **vùng ngoài CSet** tới một object nằm trong CSet:

~~~text
Old region O1                     Eden region E3 (được chọn GC)
+------------------+             +--------------------+
| object A --------+------------>| object B (live)    |
+------------------+             +--------------------+
~~~

Nếu chỉ quét references bên trong vùng E3, GC có thể nhầm B là không còn ai dùng. Vì vậy G1 sử dụng **Remembered Set (RSet)** và các cơ chế write barrier/card tracking để theo dõi gần đúng các vị trí tham chiếu từ ngoài vào các vùng cần GC.

**Tính ứng dụng với region allocation:**
- G1 có thể chọn **một phần heap** để thu hồi mà không phải quét toàn bộ object của old generation mỗi lần Young GC.
- RSet có **chi phí bộ nhớ/CPU**, đặc biệt với ứng dụng tạo nhiều cross-region references.
- Thời gian Merge Heap Roots / Scan Heap Roots / Object Copy có thể xuất hiện trong `-Xlog:gc+phases=debug` khi phân tích chi phí GC.

**Không cần học cấu trúc RSet nội bộ theo một JDK cũ như API cố định**: cách G1 nhóm và quản lý RSet đã được tối ưu qua các phiên bản. Ở mức ứng dụng, điều cần hiểu là **các reference ngoài CSet vẫn được xét khi di chuyển object**.

## 8. Humongous object: trường hợp **ngoại lệ của cấp phát Eden**

Một object có **kích thước thực tế lớn hơn hoặc bằng một nửa kích thước region** được G1 coi là **humongous**. “Kích thước object” ở đây là **kích thước trong heap sau tính toán layout** (header, alignment, phần tử mảng...), **không đơn giản là số phần tử** trong source.

Ví dụ khi `G1HeapRegionSize = 2 MiB`:

~~~text
Region size          = 2,097,152 bytes
Nửa region           = 1,048,576 bytes
byte[1,200,000]      = object vượt nửa region
=> humongous
~~~

### 8.1. Humongous được đặt ở đâu?

Khác phần lớn object mới được cấp ở Eden:
- Humongous objects được cấp **trực tiếp thuộc old generation**.
- Mỗi object lớn dùng một **chuỗi vùng liên tiếp về địa chỉ**, thường gọi vùng mở đầu và vùng tiếp nối (*StartsHumongous* / *ContinuesHumongous* trong thuật ngữ VM).
- Dung lượng không dùng hết ở **region cuối của chuỗi** có thể không dùng để cấp phát object khác cho tới khi cả humongous allocation được thu hồi.
- G1 **thường không evacuate humongous** theo cơ chế copy thường xuyên như những object nhỏ; nó có cách xác định liveness và thu hồi riêng. Trong các bản JDK hiện đại có **trường hợp di chuyển last-resort khi Full GC đặc biệt**, vì vậy không được dạy câu lỗi thời “humongous object tuyệt đối không bao giờ di chuyển”.

### 8.2. Ví dụ tính số region cần dùng

Giả sử một humongous object có kích thước **khoảng 5 MiB** và region là **2 MiB**:

~~~text
Object size ~5 MiB
Region size 2 MiB
ceil(5 / 2) = 3 regions
Dùng khoảng 6 MiB địa chỉ vùng liên tiếp
Phần cuối có thể dư khoảng 1 MiB
~~~

Đây là **phép tính minh họa**, vì object size thực phải gồm overhead và alignment, có thể làm kết quả khác gần ranh giới. G1 cần một chuỗi vùng **liền nhau trong không gian địa chỉ vùng** cho một humongous allocation.

### 8.3. Tại sao humongous quan trọng?

- Có thể làm tăng áp lực Old/Humongous regions dù nhiều object nhỏ vẫn chết nhanh ở Eden.
- Cần vùng liên tiếp đủ lớn, có thể gặp **fragmentation** và phân bổ heap không hiệu quả.
- Việc cấp phát humongous có thể thúc đẩy một chu kỳ concurrent mark sớm trong một số điều kiện.
- Một vài kiểu humongous (chẳng hạn mảng primitive có điều kiện phù hợp) có thể được **eager reclaim** ở các lần GC; không đồng nghĩa toàn bộ humongous được thu hồi nhanh như Eden.
- Thay đổi region size cũng thay đổi ngưỡng humongous, nhưng **không phải cứ tăng region size là chắc chắn cải thiện hiệu năng tổng thể**.

### 8.4. Phân biệt ba tình huống

| Tình huống | Đường cấp phát phổ biến | Có phải humongous? |
| --- | --- | --- |
| Object rất nhỏ | TLAB thuộc Eden | Không |
| Object lớn hơn TLAB nhưng nhỏ hơn ngưỡng humongous | Có thể cấp ngoài TLAB trong Eden | **Không nhất thiết** |
| Object có heap size ≥ nửa region | Humongous / old generation | **Có** |

**Một sai lầm hay gặp:** “Không nằm trong TLAB tức là Humongous”. Hai ranh giới này **khác nhau**: TLAB phục vụ tốc độ cấp phát theo thread, còn ngưỡng humongous xác định đường cấp phát đặc biệt dựa trên region size.

## 9. Cấp phát vùng và NUMA: hai tầng khác nhau

**NUMA (Non-Uniform Memory Access)** là kiến trúc trong đó CPU truy cập bộ nhớ gần node của nó với độ trễ/băng thông khác so với bộ nhớ trên node khác. Trên máy nhiều NUMA nodes, placement của các **trang nhớ vật lý** ảnh hưởng hiệu năng.

G1 region là dải **địa chỉ ảo** trong Java heap. CPU/OS quản lý ánh xạ các trang vật lý ở bên dưới. Vì vậy:

- **Một region không đồng nghĩa một NUMA node.**
- “Eden region” không có nghĩa mọi trang trong region luôn ở node của thread đang đọc nó.
- GC có thể di chuyển các object trong heap, JVM threads có thể thay CPU/node, OS có thể thay memory placement.
- Lợi ích NUMA **phụ thuộc hệ điều hành, topology, CPU affinity, JVM options, workload**, và phải được đo.

### 9.1. JEP 345 đã cải thiện điều gì?

**JEP 345: NUMA-Aware Memory Allocation for G1 (Java 14)** mở rộng khả năng G1 **ưu tiên phân phối Eden regions theo NUMA node** trên hệ thống được hỗ trợ. Khi Java thread yêu cầu thêm không gian cấp phát Eden, G1 có thể cố gắng lấy region gần node liên quan đến thread/CPU đang chạy, để tăng khả năng sử dụng bộ nhớ cục bộ.

Sơ đồ ý tưởng:

~~~text
             NUMA node 0                 NUMA node 1
          CPUs + local RAM            CPUs + local RAM
                |                           |
      Thread A đang chạy             Thread B đang chạy
                |                           |
       Yêu cầu Eden region           Yêu cầu Eden region
                |                           |
           G1 ưu tiên                    G1 ưu tiên
          Eden gần node 0              Eden gần node 1
                |                           |
         Cấp phát TLAB                  Cấp phát TLAB
                |                           |
         Các object nhỏ               Các object nhỏ

Ưu tiên vị trí (best effort), KHÔNG phải bảo đảm cứng.
~~~

**Giới hạn cần nhớ:**
- Phạm vi ban đầu của cải tiến tập trung vào **Eden / young allocation locality**, **không hứa mọi old, survivor và humongous object đều luôn node-local**.
- Khi một node thiếu free regions, G1 có thể chọn vùng khác để duy trì cấp phát.
- NUMA placement do JVM đề nghị còn phụ thuộc chính sách/bố trí trang vật lý của OS.
- Trên máy có **một NUMA node**, những kỹ thuật này không có chênh lệch “local vs remote” rõ ràng để tối ưu.
- Không nên bật cấu hình NUMA hàng loạt khi chưa biết máy thực sự có nhiều nodes và workload hưởng lợi.

### 9.2. Cách kiểm tra trên Linux NUMA thật

Trước hết, xem topology (nếu đã cài `numactl`):

~~~bash
numactl --hardware
~~~

Sau đó, trong một môi trường **HotSpot/JDK hỗ trợ G1 NUMA** và có nhiều NUMA nodes, có thể chạy thử riêng:

~~~bash
java -XX:+UseG1GC -XX:+UseNUMA -Xlog:gc+heap+numa=debug -Xms2g -Xmx2g -jar app.jar
~~~

Đây là **lệnh cấu hình minh họa cho hệ thống có sẵn app.jar và RAM phù hợp**, **không phải lệnh demo đã benchmark**. `-XX:+UseNUMA` có thể bị vô hiệu/không mang lại lợi ích tùy platform và khả năng quan sát của JVM; mức `2g` chỉ là ví dụ heap, không phải con số chuẩn cho mọi hệ thống. Tag cụ thể có thể kiểm tra qua `java -Xlog:help` trên JDK đang chạy.

**Đừng dùng `-Xlog:gc+numa=debug` một cách máy móc:** trên OpenJDK 21 thử nghiệm, VM báo không có tag set `gc+numa` và gợi ý `gc+heap+numa`. Cần đối chiếu cú pháp logging thật của bản JDK.

**Phân biệt kiểm chứng:** Bài thực hành phần 10 đã chạy GC logs trên một môi trường Linux **một NUMA node**. Nó **chứng minh cấp phát theo G1 regions**, **không chứng minh cải thiện hiệu năng NUMA trên máy nhiều node**. Muốn kết luận NUMA có lợi, phải benchmark trên topology thật với workload/affinity nhất quán.

## 10. Ví dụ thực hành Java 17+: thấy Eden, Survivor, Old và Humongous trên GC log

Chương trình tạo nhiều **mảng nhỏ có vòng đời ngắn** và một số **mảng lớn được giữ lại**. Đặt heap nhỏ và region size rõ ràng để G1 có cơ hội thực hiện Young GC, đồng thời một số mảng lớn vượt ngưỡng humongous.

**Tệp: `G1RegionAllocationDemo.java`**

~~~java
import java.util.ArrayList;
import java.util.List;

public final class G1RegionAllocationDemo {
    public static void main(String[] args) {
        List<byte[]> temporary = new ArrayList<>();
        List<byte[]> large = new ArrayList<>();
        long verifiedBytes = 0;

        for (int round = 0; round < 48; round++) {
            temporary.clear();

            for (int i = 0; i < 160; i++) {
                byte[] block = new byte[32 * 1024];
                block[0] = (byte) round;
                temporary.add(block);
            }

            verifiedBytes += temporary.get(0).length;

            if (round % 8 == 0) {
                large.add(new byte[1_200_000]);
            }
        }

        System.out.println("Small arrays per round: 160");
        System.out.println("Rounds: 48");
        System.out.println("Retained large arrays: " + large.size());
        System.out.println("Verified bytes: " + verifiedBytes);
    }
}
~~~

### 10.1. Giải thích workload

- Có **48 rounds**, mỗi round tạo **160 mảng kích thước 32 KiB**.
- `temporary.clear()` đầu mỗi round bỏ các reference giữ từ round trước, nên nhiều mảng cũ có thể trở thành rác.
- Mảng `32 KiB` nhỏ hơn ngưỡng humongous khi region size là 2 MiB, nên được cấp phát theo đường thông thường (có thể TLAB/ngoài TLAB tùy runtime).
- Mỗi 8 rounds, chương trình giữ lại một mảng `new byte[1_200_000]` trong `large`. Tổng có **6 mảng lớn**, mỗi mảng vượt **nửa region 2 MiB**, là ứng viên humongous.
- `verifiedBytes` cộng 32 KiB mỗi round, không phải tổng byte cấp phát. Kết quả là `48 * 32768 = 1_572_864` bytes.
- Mục tiêu là **quan sát quản lý vùng và GC**, không phải benchmark production hoặc chứng minh tối ưu NUMA.

### 10.2. Biên dịch và chạy

Sử dụng **JDK 17 trở lên**, hỗ trợ HotSpot Unified Logging:

~~~bash
javac -encoding UTF-8 --release 17 G1RegionAllocationDemo.java

java -XX:+UseG1GC -Xms128m -Xmx128m -XX:G1HeapRegionSize=2m -Xlog:gc+init=info,gc+heap=info:file=g1-regions.log:uptime,level,tags G1RegionAllocationDemo
~~~

Giải nghĩa:

| Tùy chọn | Vai trò |
| --- | --- |
| `-XX:+UseG1GC` | Chọn G1 tường minh (trên nhiều HotSpot hiện đại G1 thường đã là mặc định) |
| `-Xms128m -Xmx128m` | Đặt heap ban đầu và tối đa 128 MiB cho bài lab |
| `-XX:G1HeapRegionSize=2m` | Yêu cầu region size bằng 2 MiB |
| `-Xlog:gc+init=info,gc+heap=info:...` | Ghi kích thước region và các thống kê vùng GC ra file |
| `file=g1-regions.log` | Tệp log được ghi tại **working directory** của lệnh |
| `uptime,level,tags` | In elapsed time, cấp log, các tag để dễ đối chiếu |

**Lưu ý an toàn:** Đặt `-Xmx128m` chỉ để dễ quan sát GC trong bài lab. Đừng sao chép nguyên heap nhỏ này vào hệ thống production. Lần chạy nào tạo ra bao nhiêu GC còn tùy máy, JIT, OS và version JDK; không nên viết test dựa trên chính xác số lần GC.

### 10.3. Stdout chương trình

**Stdout chính xác đã kiểm chứng trên OpenJDK 21, biên dịch bằng `--release 17`:**

~~~text
Small arrays per round: 160
Rounds: 48
Retained large arrays: 6
Verified bytes: 1572864
~~~

Bốn dòng này được tính từ logic chương trình. Việc chương trình in ra `6` mảng lớn **không trực tiếp cho biết số Humongous regions luôn bằng 6**, vì số regions phụ thuộc kích thước object, trạng thái GC và cách JVM quản lý.

### 10.4. Tìm các dòng cần đọc trong log

Trên Linux/macOS:

~~~bash
grep -E "Heap Region Size|Eden regions|Survivor regions|Old regions|Humongous regions" g1-regions.log
~~~

Trên Windows PowerShell:

~~~powershell
Select-String -Path g1-regions.log -Pattern "Heap Region Size|Eden regions|Survivor regions|Old regions|Humongous regions"
~~~

**Trích đoạn GC log đã được quan sát**, chỉ để minh họa; timestamp và số region có thể khác trên máy bạn:

~~~text
[0.009s][info][gc,init] Heap Region Size: 2M
[0.054s][info][gc,heap] GC(0) Eden regions: 6->0(37)
[0.054s][info][gc,heap] GC(0) Survivor regions: 0->1(1)
[0.054s][info][gc,heap] GC(0) Old regions: 1->1
[0.054s][info][gc,heap] GC(0) Humongous regions: 1->1
[0.170s][info][gc,heap] GC(1) Eden regions: 37->0(36)
[0.170s][info][gc,heap] GC(1) Survivor regions: 1->2(5)
[0.170s][info][gc,heap] GC(1) Old regions: 1->1
[0.170s][info][gc,heap] GC(1) Humongous regions: 2->2
~~~

### 10.5. Cách đọc từng dòng

**`Heap Region Size: 2M`**

- Xác nhận yêu cầu region size được VM áp dụng.
- Từ đây có thể suy ra ngưỡng object humongous **khoảng ≥1 MiB** cho chương trình thử nghiệm.
- Không dựa vào số phần tử của `byte[]` để xác định đúng byte ngưỡng vì còn object header và alignment.

**`Eden regions: 6->0(37)`**

- Trước pause có **6 Eden regions** trong thống kê này.
- Sau evacuation của pause đó còn **0 Eden regions** ở thời điểm ghi log.
- Phần số trong ngoặc **(37)** biểu thị **young/eden target sizing liên quan chu kỳ tiếp theo**, không phải kết luận “37 object được cấp phát”, “37 regions vừa được thu hồi” hay “37 regions còn trống”.
- Số Eden regions có thể thay đổi qua các lần GC theo heuristic.

**`Survivor regions: 0->1(1)`**

- Có object sống được chuyển tới Survivor ở trạng thái sau GC (trong lần chạy quan sát).
- Không phải mọi object sống đều được giữ ở Survivor mãi; một số có thể promote sang Old.

**`Old regions: 1->1`**

- Ở pause đó số old regions không thay đổi.
- Điều này **không chứng minh** old generation hoàn toàn không hoạt động, chỉ nói số region theo loại này giữ nguyên trong phép đo.

**`Humongous regions: 1->1`**, rồi `2->2`

- JVM đang dùng những Humongous regions cho object lớn.
- Đây là **số region**, không phải một bảo đảm về **số Java objects**.
- Nếu một object trải qua nhiều regions, chỉ một object cũng có thể làm con số này tăng nhiều đơn vị.
- Lượng vùng thu hồi hoặc giữ lại tùy liveness, điểm GC, kích thước và heuristic.

### 10.6. Có thể dùng JFR để bổ sung

Trong hệ thống thật, sau khi thấy humongous hoặc allocation pressure trên GC log, có thể dùng **Java Flight Recorder (JFR)** để tìm allocation sites/stack samples, lượng cấp phát theo class/thread và các GC pause đáng chú ý. JFR allocation events thường có **sampling/threshold**, không có nghĩa ghi lại từng phép cấp phát `new`.

Các công cụ trả lời câu hỏi khác nhau:
- **GC log**: heap region counts, GC phase và biến động sau pause.
- **JFR**: allocation sites, GC pauses và hành vi JVM ở góc nhìn profiler.
- **Application metrics**: RPS, latency, error rate, peak traffic và kết quả nghiệp vụ.

Đừng kết luận “Humongous regions tăng chắc chắn do memory leak” khi chưa biết các object có còn sống, lượng cache, batch size và thời gian chúng được giữ.

## 11. Thử thay đổi region size và diễn giải đúng

Thực hành mở rộng: giữ nguyên source, thử region 4 MiB trên cùng máy:

~~~bash
java -XX:+UseG1GC -Xms128m -Xmx128m -XX:G1HeapRegionSize=4m -Xlog:gc+init=info,gc+heap=info:file=g1-regions-4m.log:uptime,level,tags G1RegionAllocationDemo
~~~

Khi đó:
- Region size là **4 MiB**.
- Ngưỡng humongous xấp xỉ **2 MiB**, cao hơn kích thước mỗi mảng `1_200_000` bytes.
- Vì vậy các mảng lớn trong demo này **không còn được phân loại humongous chỉ do kích thước**; chúng được xử lý theo đường object thường (có thể ngoài TLAB).
- Tổng số regions của heap 128 MiB giảm so với lựa chọn 2 MiB.

Đây là **dự đoán từ quy tắc G1**, không phải một lời hứa rằng toàn bộ GC log sẽ “tốt hơn” hoặc “nhanh hơn” với 4 MiB. Cần chạy và so sánh dưới cùng workload, lấy nhiều mẫu và kiểm tra hiệu năng thực.

### 11.1. Vì sao tùy chỉnh region size có tác động hai chiều?

| Region size nhỏ hơn | Region size lớn hơn |
| --- | --- |
| Có thể tăng độ linh hoạt chọn vùng để thu hồi | Có thể giảm số lượng region/metadata quản lý |
| Ngưỡng humongous thấp hơn | Ngưỡng humongous cao hơn |
| Một số object trung bình trở thành humongous | Một số object trước đó humongous có thể không còn |
| Có thể tăng overhead theo số region | Có thể tăng độ hạt của một quyết định thu hồi/vùng nhớ |
| Không tự đảm bảo pause ngắn hơn | Không tự đảm bảo throughput cao hơn |

Vì vậy, để tối ưu, đo **p95/p99 latency, pause distribution, throughput, allocation rate, số humongous allocations, GC CPU và mức nhớ**. Có thể region size lớn làm bớt humongous nhưng lại tăng chi phí ở chỗ khác.

## 12. Mối liên hệ giữa region allocation và các chỉ số GC

| Quan sát trên log/metrics | Có thể gợi ý điều gì? | Chưa đủ để kết luận điều gì? |
| --- | --- | --- |
| Eden regions tăng nhanh giữa các pauses | Allocation rate cao hoặc young sizing thích ứng | Chắc chắn memory leak |
| Survivor regions lớn hơn sau GC | Nhiều object sống vượt qua Young GC | Object sẽ tồn tại mãi |
| Old regions tăng dần theo thời gian | Promotion hoặc cấp phát Old/humongous và áp lực heap | 100% do object leak |
| Humongous regions nhiều | Có object rất lớn hoặc nhiều objects vượt ngưỡng | Chắc chắn cần tăng `G1HeapRegionSize` |
| Pause Young GC xảy ra thường xuyên | Young generation quay vòng nhanh, allocation pressure | Mọi request đều bị pause dài |
| Mixed GC xuất hiện | G1 đang thu hồi thêm các old regions được chọn | Toàn bộ Old được quét/compacted mỗi lần |
| Evacuation Failure xuất hiện | Không di chuyển hết object từ CSet vì thiếu chỗ/pinning và điều kiện liên quan | Java heap chỉ còn 0 byte free |
| Full GC xảy ra | Một đường fallback tốn kém khi điều kiện bình thường không đủ | Cứ thêm TLAB sẽ giải quyết được |
| NUMA local/remote metrics khác nhau | Có thể có hiệu ứng placement/CPU affinity | Chắc chắn G1 lỗi nếu có remote access |

### 12.1. Evacuation Failure có nghĩa là gì?

Thông thường G1 cần **to-space** để copy object còn sống ra khỏi source regions. Nếu không có đủ chỗ (hoặc có những tình huống object bị pin), việc evacuation có thể thất bại một phần. G1 có các cơ chế xử lý/retry và cuối cùng có thể phải Full GC nếu áp lực rất lớn.

Trên các JDK hiện đại, cũng cần biết **pinning và xử lý humongous** đã có cải tiến theo thời gian. Không dạy những khẳng định tuyệt đối dựa trên bản HotSpot cũ như “G1 không thể giải phóng vùng có pinned object trong bất kỳ tình huống nào” hay “humongous không bao giờ di chuyển”.

### 12.2. Khi nào cần xem thêm heap sizing?

Nếu ứng dụng có throughput cao nhưng heap bị giới hạn quá nhỏ, có thể liên tục phải làm Young GC và promote nhiều object. Nhưng **tăng `-Xmx` cũng có chi phí** và không thay thế sửa thiết kế tạo quá nhiều object. Cần nhìn cả:
- Live-set sau GC.
- Allocation rate và promotion rate.
- Pause target, pause thực tế và GC CPU.
- Container memory limit / RSS, không chỉ Java heap.
- Mức hoạt động của native/direct memory ngoài Java heap nếu ứng dụng sử dụng.

## 13. Cách tư duy về NUMA locality khi benchmark

Bài này không khuyên bật `UseNUMA` mặc định ở mọi nơi. Một phép benchmark đáng tin nên:

1. **Xác nhận có nhiều NUMA nodes** và CPU/node topology phù hợp.
2. Xác nhận JVM/hệ điều hành hỗ trợ **G1 NUMA-aware allocation** trong cấu hình thật.
3. Giữ ổn định JDK version, G1, heap, workload, cấu hình GC và cách warm-up.
4. Đặt cùng CPU affinity/thread placement nếu cần để tránh nhiễu.
5. Chạy nhiều lần **baseline** và **candidate**, không chỉ một lần.
6. Đọc throughput, p95/p99 latency, GC pauses, CPU utilization, memory bandwidth và dữ liệu node locality nếu thu được.
7. Kiểm tra có thay đổi bất lợi về tải trên từng node hoặc remote memory accesses không.
8. Chỉ kết luận có lợi khi kết quả **lặp lại ổn định** và phù hợp cả mục tiêu ứng dụng.

**Chú ý:** Bộ test trên máy chỉ có NUMA node 0 **không thể đo cải thiện locality giữa hai nodes**. Việc bật cờ `-XX:+UseNUMA` nhưng log không có sự kiện NUMA không có nghĩa mọi object đều local; cần kiểm tra khả năng hỗ trợ và topology.

## 14. Các lỗi phổ biến và cách sửa

### Lỗi 1 — “Một region chứa một object”

**Sai:** region là đơn vị quản lý của G1; object nhỏ có thể cùng nằm trong TLAB/Eden region. Một humongous object còn có thể chiếm **nhiều regions**.

**Sửa:** phân biệt ba cấp **object → TLAB/đường cấp phát → G1 region**.

### Lỗi 2 — “Eden là một dải bộ nhớ liên tục duy nhất”

**Sai:** trong G1, Eden là một **tập regions**, thường không liên tiếp.

**Sửa:** khi đọc `Eden regions: N->M`, nghĩ đến **số lượng regions thuộc vai trò Eden**, không phải ranh giới duy nhất giữa Eden/Old.

### Lỗi 3 — “Object mới luôn ở Eden”

**Sai nếu hiểu tuyệt đối:** humongous objects được cấp **trực tiếp trong old generation**. Ngoài ra, JIT có thể loại bỏ cấp phát heap cho object không escape.

**Sửa:** nói **phần lớn object thông thường cần heap** được cấp ở Eden, ngoại trừ humongous và những tối ưu/đường đặc biệt.

### Lỗi 4 — “TLAB và region là cùng một thứ”

**Sai:** TLAB là phần cấp phát cục bộ theo Java thread, thường lấy từ Eden regions.

**Sửa:** đọc tài liệu về `UseTLAB` và GC TLAB diagnostics; đừng suy ra một TLAB đồng nghĩa một Eden region.

### Lỗi 5 — “Ngoài TLAB tức là humongous”

**Sai:** object có thể quá lớn cho TLAB nhưng **nhỏ hơn nửa region** và vẫn cấp qua đường thường.

**Sửa:** kiểm tra **hai ngưỡng khác nhau**: TLAB-size policy và humongous half-region rule.

### Lỗi 6 — “Humongous được cấp ở Eden rồi promote như object nhỏ”

**Sai:** humongous có **đường cấp trực tiếp old/humongous**.

**Sửa:** đọc `Humongous regions` trong GC log; cân nhắc đặc tính mảng lớn và cách lưu dữ liệu.

### Lỗi 7 — “Humongous không bao giờ di chuyển trên mọi JDK”

**Không đúng với HotSpot hiện đại:** có tình huống **last-resort Full GC** liên quan khả năng di chuyển humongous objects.

**Sửa:** hiểu quy tắc thông thường (không evacuate như object nhỏ) và ngoại lệ hiện hành, tránh phát biểu tuyệt đối dựa trên tài liệu lịch sử.

### Lỗi 8 — “Chọn CSet nghĩa là region được giải phóng ngay”

**Sai:** các object sống phải được xử lý, copy và cập nhật references trước khi vùng nguồn có thể tái sử dụng.

**Sửa:** phân biệt **source regions của CSet** với **destination/to-space regions** và các trường hợp evacuation failure.

### Lỗi 9 — “G1 luôn đạt pause target”

**Sai:** `MaxGCPauseMillis` là **mục tiêu mềm**, phụ thuộc workload và áp lực bộ nhớ.

**Sửa:** đo phân bố pause thực; cân nhắc concurrency, heap size, RSet, humongous và workload.

### Lỗi 10 — “Bật NUMA là mọi object nằm trên local node”

**Sai:** G1 NUMA-aware allocation là tối ưu ưu tiên placement khi có hỗ trợ; thread migration, memory pressure và OS có thể ảnh hưởng vị trí.

**Sửa:** đo trên máy NUMA thật, không suy đoán từ một tùy chọn JVM.

### Lỗi 11 — “JVM logging cho biết chính xác vị trí mỗi Java object”

**Sai:** `gc+heap` cung cấp thống kê theo regions, không có map public đơn giản của object → region.

**Sửa:** phối hợp GC logs, JFR/heap profiling khi cần, và không làm rò rỉ dữ liệu production trong dump.

### Lỗi 12 — “Có 6 mảng humongous thì chắc chắn có đúng 6 Humongous regions”

**Sai:** số region phụ thuộc size và liveness; một object có thể chiếm nhiều regions.

**Sửa:** đọc con số log riêng biệt và tính theo **object heap size / region size** nếu cần dự đoán số vùng.

## 15. Bài tập và đáp án

### Bài 1 — Phân loại region

Bạn có các vùng `R0=Eden`, `R1=Old`, `R2=Free`, `R3=Survivor`. Thread tạo nhiều object nhỏ và cần thêm không gian Eden.

**Hỏi:** G1 có thể sử dụng `R2` vào việc gì?

**Đáp án:** G1 có thể **gán Free region R2 làm Eden** để cấp phát thêm chỗ, tùy chính sách và không gian hiện có. Không nên hiểu thread tạo một object và chiếm nguyên R2; R2 có thể chứa nhiều object/TLAB.

### Bài 2 — Tính ngưỡng humongous

Nếu region size là **4 MiB**, một object có heap size **3 MiB** có phải humongous không?

**Đáp án:** **Có**, vì nửa region là **2 MiB** và `3 MiB ≥ 2 MiB`. Object được xử lý theo đường humongous/old chứ không phải cấp thông thường trong Eden.

### Bài 3 — Dự đoán số region

Một object có kích thước heap **9 MiB**, region size **4 MiB**. Cần tối thiểu bao nhiêu regions liên tiếp?

**Đáp án:** `ceil(9/4) = 3` regions, tổng dung lượng vùng 12 MiB; phần còn lại của chuỗi vùng có thể bị lãng phí cho đến lúc object được thu hồi.

### Bài 4 — Giải thích log Eden

~~~text
Eden regions: 10->0(22)
~~~

**Hỏi:** Có phải 22 object vừa được tạo không?

**Đáp án:** **Không**. Dòng này nói về **số Eden regions**: trước GC là 10, sau GC là 0, số 22 trong ngoặc liên quan mục tiêu/cấu hình young/eden cho giai đoạn kế tiếp, không phải object count.

### Bài 5 — TLAB có lợi gì?

**Hỏi:** Vì sao G1/HotSpot không cần một global lock cho mọi lần tạo object nhỏ?

**Đáp án:** Các Java threads thường cấp phát nhanh trong **TLAB riêng**, giảm tranh chấp ở đường cấp phát thường gặp. Khi TLAB không còn chỗ, runtime phải xin thêm vùng cấp phát hoặc dùng đường thích hợp.

### Bài 6 — Tại sao Mixed GC không chỉ gom rác Eden?

**Đáp án:** Mixed GC vẫn xử lý young generation, đồng thời lựa chọn các **old regions** phù hợp dựa trên dữ liệu liveness/hiệu quả dự đoán. Điều này giúp G1 thu hồi old incrementally thay vì mỗi lần phải dọn toàn old generation.

### Bài 7 — Phân biệt cải thiện NUMA và thay đổi region size

Bạn benchmark trên server **chỉ có một NUMA node**, bật `UseNUMA` và thấy throughput khác 1%.

**Hỏi:** Có thể kết luận G1 đã tối ưu remote memory latency nhờ NUMA không?

**Đáp án:** **Không**. Một node không có sự phân biệt remote node để kiểm chứng. Cần khảo sát nhiễu benchmark, JIT, load, GC/heap settings; phải thử trên topology nhiều nodes phù hợp mới có căn cứ cho hiệu quả NUMA-local placement.

### Bài 8 — Thiết kế thử nghiệm region size

Chương trình tạo nhiều `byte[1_200_000]`; khi region size 2 MiB có Humongous regions, khi thử 4 MiB chúng không còn vượt ngưỡng.

**Hỏi:** Có nên kết luận chắc chắn ứng dụng nhanh hơn với 4 MiB không?

**Đáp án:** **Không**. Việc giảm humongous allocations có thể có lợi, nhưng region size lớn còn ảnh hưởng kích thước/chi phí thu hồi, số regions và memory waste. Phải đo throughput/latency/pause trên workload thật trước khi chọn.

## 16. Checklist điều tra cấp phát G1

- [ ] Đã xác nhận JVM thật sự dùng **G1** (không suy từ mặc định của môi trường khác).
- [ ] Đã xem **Heap Region Size** thực tế trong `gc+init` log.
- [ ] Có số vùng **Eden/Survivor/Old/Humongous** qua vài lần GC.
- [ ] Phân biệt **số regions** với **số Java objects**.
- [ ] Biết allocation chủ yếu đi qua **Eden/TLAB**; object quá lớn dùng đường humongous.
- [ ] Đã xem target pause thực tế, không coi đó là cam kết cứng.
- [ ] Kiểm tra allocation rate, survivor occupancy, promotion và old live-set.
- [ ] Phân biệt Young GC, Mixed GC, Full GC và evacuation failure.
- [ ] Không tự chỉnh `G1HeapRegionSize` hoặc `-Xmx` chỉ từ một log đơn lẻ.
- [ ] Với NUMA, đã kiểm tra **OS, CPU topology, JDK support và affinity**.
- [ ] Chỉ so sánh hiệu năng NUMA với baseline/candidate đủ mẫu trên cùng workload.
- [ ] Nếu cần root cause, phối hợp GC log với **JFR và ứng dụng metrics**, không chỉ nhìn region count.

## 17. Tóm tắt cần nhớ

- G1 chia Java heap thành **các regions bằng nhau**; các tập Eden, Survivor và Old **không bắt buộc liên tục** trong địa chỉ heap.
- Phần lớn object mới cần heap được tạo ở **Eden**, thường qua **TLAB** giúp đường cấp phát theo thread nhanh.
- Khi cần thêm Eden, G1 có thể gán Free regions cho young generation; quá trình quản lý dựa trên **số region** và **pause-time heuristics**.
- Khi Young GC hoặc Mixed GC xảy ra, G1 **evacuate object sống**, xử lý references (có sự trợ giúp của RSet), rồi giải phóng **vùng nguồn**.
- Object có kích thước heap **≥ một nửa region** được coi là **humongous** và cấp trực tiếp trong old/humongous regions, có thể trải nhiều vùng liên tiếp.
- **TLAB threshold và humongous threshold là hai khái niệm khác nhau**. Không phải mọi object được cấp ngoài TLAB đều là humongous.
- **JEP 345 (Java 14)** bổ sung khả năng NUMA-aware lựa chọn **Eden regions** trên hệ thống hỗ trợ, nhưng việc placement chỉ có tính ưu tiên, không phải một bảo đảm tuyệt đối cho từng object.
- Có thể quan sát bằng **`-Xlog:gc+init=info,gc+heap=info`**, đọc `Eden regions`, `Survivor regions`, `Old regions`, `Humongous regions` và áp dụng đo đạc thực tế trước khi tuning.

**Nguồn chính thức và đang còn áp dụng:**
- [Oracle JDK 25 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): heap layout, region allocation, collection set, humongous objects, ergonomic sizing.
- [Oracle JDK 21 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html): định nghĩa regions, Young/Mixed GC và huấn luyện các thuật ngữ.
- [Oracle JDK 24 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html): TLAB, object allocation và quan sát bằng JFR.
- [JEP 345 — NUMA-Aware Memory Allocation for G1](https://openjdk.org/jeps/345): cơ chế NUMA-aware allocation cho G1 từ Java 14.
- [Oracle Java 14 Release Notes](https://www.oracle.com/java/technologies/javase/14-relnote-issues.html): mô tả việc dùng `-XX:+UseNUMA` và ranh giới Eden/Old/Humongous.
- [OpenJDK JEP 423 — Region Pinning for G1](https://openjdk.org/jeps/423): cải tiến liên quan pinning của G1 trên JDK hiện đại.
- [Oracle JDK 21 — `java` launcher options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): các JVM flags và Unified GC Logging.
