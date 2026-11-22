# 15.7. Phân tích allocation sample, GC, heap summary và OldObjectSample bằng JFR

Khi một dịch vụ Java tăng sử dụng bộ nhớ hoặc tốn nhiều thời gian cho garbage collection, câu hỏi đầu tiên thường là “class nào tạo nhiều object?”. Nhưng **tạo nhiều object (allocation pressure)**, **GC hoạt động mạnh**, **dung lượng heap sau GC cao** và **đối tượng bị giữ lâu (retention)** là bốn hiện tượng khác nhau. Java Flight Recorder (JFR) cung cấp các nhóm event để điều tra theo thứ tự thay vì nhìn một bảng số liệu rồi vội kết luận rò rỉ bộ nhớ.

Bài này tập trung vào bốn lớp bằng chứng trên HotSpot/JDK hiện đại:

1. **Allocation sample:** `jdk.ObjectAllocationSample` giúp xác định loại object, thread và call stack tạo áp lực cấp phát.
2. **GC:** `jdk.GarbageCollection` cùng các event pause/phase cho thấy tần suất, loại collector và chi phí thu gom.
3. **Heap summary:** `jdk.GCHeapSummary` theo dõi lượng heap trước/sau GC, giúp nhận diện live set hoặc mức chiếm dụng tồn dư tăng.
4. **OldObjectSample:** `jdk.OldObjectSample` đưa ra mẫu những object tồn tại lâu, thông tin thời điểm cấp phát và, khi được thu thập, đường tham chiếu về GC roots.

Đầu ra đúng của một cuộc điều tra không phải “có nhiều `byte[]` nên leak”, mà là **một giả thuyết cụ thể được hỗ trợ bởi các sự kiện cùng khoảng thời gian**, ví dụ: request parsing tạo phần lớn allocation → GC xảy ra dày → heap sau GC vẫn ổn định → đây là **churn tạm thời**, không phải leak; hoặc cache giữ object từ nhiều chu kỳ tải → đáy heap sau GC tăng → `OldObjectSample` cho thấy đối tượng còn reachable từ một cache không giới hạn.

## 1. Bốn góc nhìn, bốn câu hỏi khác nhau

| Event/góc nhìn | Câu hỏi nó giúp trả lời | Dữ liệu thường quan sát | Không được suy ra trực tiếp |
| --- | --- | --- | --- |
| `jdk.ObjectAllocationSample` | Object **được tạo ở đâu**? Thành phần nào tạo áp lực cấp phát? | `objectClass`, `weight`, event thread, stack trace nếu bật | Số instance chính xác; những instance đó vẫn sống; retained heap |
| `jdk.GarbageCollection` và pause/phase events | GC diễn ra lúc nào, bao lâu, vì nguyên nhân nào? | `gcId`, `name`/`cause` khi có, `duration`, các GC phase | Mọi `duration` là thời gian stop-the-world; nguyên nhân gốc của leak |
| `jdk.GCHeapSummary` | Heap dùng bao nhiêu **trước/sau một GC**? | `gcId`, `when`, `heapUsed`, `heapSpace` (reserved/committed) | Phần heap sau GC đều là leak; riêng event này đã phân loại retained object |
| `jdk.OldObjectSample` | Object nào **sống đủ lâu để đáng điều tra**, được cấp phát khi nào và ai có thể đang giữ? | `allocationTime`, `objectAge`, `object`, `root`, stack trace khi có | Danh sách tất cả object đang sống; heap histogram đầy đủ; bằng chứng leak chắc chắn |

**Ghi nhớ sự khác biệt cốt lõi:**

- **Allocation rate cao**: nhiều byte/object được tạo mỗi giây; nhiều object có thể chết rất nhanh.
- **GC pressure**: GC phải chạy thường xuyên hoặc gây pause đáng kể; có thể do allocation churn, heap nhỏ, live set cao hay cấu hình GC.
- **Heap occupancy**: mức đang sử dụng tại thời điểm đo; chu kỳ tăng/giảm dạng “răng cưa” là bình thường.
- **Retention**: các object còn reachable sau thời gian/chu kỳ GC; chỉ đáng nghi khi vòng đời vượt quá nhu cầu thiết kế và làm live set tăng không kiểm soát.

JFR là **dòng sự kiện được lấy mẫu hoặc phát theo thời điểm**, không phải dump toàn bộ object graph. Khi cần chứng minh đúng cấu trúc các object bị giữ và retained sizes, HPROF/heap dump và công cụ như Eclipse MAT thường bổ sung giá trị.

## 2. Chuẩn bị và kiểm tra recording có dữ liệu phù hợp

Giả sử đã có một file tên `memory-investigation.jfr`. Trước khi phân tích, dùng JDK tương thích để kiểm tra:

~~~bash
jfr summary memory-investigation.jfr
jfr metadata --events jdk.ObjectAllocationSample,jdk.GarbageCollection,jdk.GCHeapSummary,jdk.OldObjectSample memory-investigation.jfr
~~~

- `jfr summary` cho biết khoảng thời gian ghi, kích thước và số lượng từng loại event có trong file; **event không xuất hiện có thể do không bật, không phát sinh hoặc không được thu trong khoảng thời gian này**.
- `jfr metadata` mô tả tên và kiểu field, tránh đoán schema khi so file từ các bản JDK khác nhau.
- Đối chiếu thời gian ghi với **thời điểm xảy ra spike**, tốc độ request, tải, deploy, mức `-Xmx` và phiên bản JVM/collector. File nhỏ hoặc khoảng thu quá ngắn có thể bỏ qua vấn đề cần quan sát.
- Nếu có nhiều recording song song, xác minh tên recording và scope khi dump; đừng mặc định file chứa chính xác một phiên nếu khi dump không chỉ định `name`.

Khi cần thu mới trên HotSpot JDK 21, xác nhận đúng PID qua `jcmd -l` và PID của ứng dụng, ví dụ **12345** (đây chỉ là PID minh họa, thay bằng PID thật):

~~~bash
jcmd 12345 help JFR.start
jcmd 12345 help JFR.dump
jcmd 12345 JFR.start name=memory-investigation settings=profile disk=true maxage=15m maxsize=256m
jcmd 12345 JFR.check name=memory-investigation verbose=true
~~~

Chờ ứng dụng trải qua tải cần nghiên cứu và dùng **đường dẫn ghi được bởi JVM đích** để xuất:

~~~bash
jcmd 12345 JFR.dump name=memory-investigation filename=/var/tmp/jfr/memory-investigation.jfr
jcmd 12345 JFR.check name=memory-investigation
~~~

Lệnh `JFR.dump` tạo snapshot **mà không tự dừng recording**. `settings=profile` thường có thông tin allocation/stack chi tiết hơn `default` và có thể tốn thêm tài nguyên. Giới hạn `maxage`/`maxsize` là chính sách **giữ dữ liệu**, không khôi phục được những khoảng đã mất.

Khi không cần ghi nữa, lưu dữ liệu cuối rồi dừng đúng phiên:

~~~bash
jcmd 12345 JFR.stop name=memory-investigation filename=/var/tmp/jfr/memory-investigation-final.jfr
~~~

Không nên dùng tên file trùng giữa các lần dump/stop. Nếu ứng dụng chạy trong container, file được tạo tại filesystem của **JVM đích**, có thể khác máy người gọi. Hãy kiểm tra attach permissions, quota, dung lượng đĩa, nơi lưu artifact và độ nhạy dữ liệu trước khi thu ở production.

### Bật event đúng phạm vi

JFR có các cấu hình mặc định `default.jfc` và `profile.jfc` trong JDK; event settings có thể được bật/tắt hoặc đổi sampling threshold. Để biết **thực tế** event nào đang được ghi, xem `JFR.check ... verbose=true` hoặc file `.jfc`. Với JDK 17+, có thể truyền event settings qua tham số khởi tạo/`JFR.start`; khi cần chính xác, kiểm tra tài liệu của JVM đích trước khi cấu hình.

Cần phân biệt:

- `jdk.ObjectAllocationSample` là **mẫu phân bố cấp phát**. Nó thường phù hợp hơn để phân tích nơi tạo object với overhead có thể kiểm soát. Các event `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB` cũng tồn tại trong nhiều HotSpot JDK nhưng ý nghĩa lấy mẫu và cấu hình khác; không cộng số event như thể mỗi event tương đương một object.
- `jdk.GarbageCollection` và `jdk.GCHeapSummary` thường có trong các profile JFR phổ biến; các event chi tiết theo collector như `jdk.G1HeapSummary` phụ thuộc collector/JDK. Nếu không thấy `G1...` khi đang dùng collector khác, đó không phải lỗi.
- `jdk.OldObjectSample` cần điều kiện lấy mẫu/thời gian sống của đối tượng; **không thể bảo đảm luôn có event** chỉ bằng việc bật JFR. Thông tin `root` có thể thiếu nếu chưa yêu cầu thu đường đến GC roots.

## 3. Allocation sample: xác định “ai tạo áp lực cấp phát”

Trích các event sample:

~~~bash
jfr print --events jdk.ObjectAllocationSample --stack-depth 15 memory-investigation.jfr
~~~

Trên HotSpot JDK 21, event `jdk.ObjectAllocationSample` có các trường đáng chú ý:

- `objectClass`: class của đối tượng được chọn làm mẫu, chẳng hạn `byte[]`, `java.lang.String` hoặc đối tượng của ứng dụng.
- `weight`: **trọng số mẫu** biểu thị một lượng allocation được đại diện thống kê. Tổng các weight trong nhiều sample theo class/thread/stack giúp **ước lượng xu thế allocation pressure**, nhưng **weight của một sample không nhất thiết bằng kích thước chính object được chọn**.
- `eventThread`: thread liên quan đến mẫu, khi có.
- `stackTrace`: vị trí cấp phát, khi collection settings cho phép ghi stack.

**Tránh nhầm đếm sample với đếm object:** 150 sample không đồng nghĩa có đúng 150 object được tạo. Cũng không thể lấy số sample nhân “kích thước instance trung bình” rồi khẳng định byte cấp phát thực tế. Nếu so các lần chạy, phải dùng khoảng thời gian và chính sách sampling tương đương, đồng thời xem throughput.

### 3.1. Cách đọc stack trace

Giả sử (dữ liệu **minh họa**) nhiều sample `byte[]` có stack:

~~~text
HttpDecoder.decode(...)
  -> PayloadParser.parse(...)
     -> Arrays.copyOf(...)
~~~

Điều đó chỉ ra **điểm cấp phát**: code parse payload tạo mảng sao chép thường xuyên. Nó **không** cho biết các mảng có đang bị giữ lâu hay không. Có thể đa số đã bị GC giải phóng ngay sau request. Bước tiếp theo là xem GC frequency, mức heap sau GC và, nếu nghi retention, `OldObjectSample`/heap dump.

Trong JDK 21, `jfr view` có thể tổng hợp nhiều loại event thành bảng:

~~~bash
jfr --help view
jfr view types memory-investigation.jfr
~~~

Chọn **view có thật** trong kết quả help của phiên JDK đó, vì tên view và khả năng tổng hợp thay đổi theo phiên bản. Không nên giả định một tên view bất kỳ có sẵn trên tất cả JDK 17/21. Ngoài CLI, Java Mission Control (JMC) giúp nhóm allocation samples theo **class, thread, stack trace** và xem heat map qua thời gian.

### 3.2. Kết luận hợp lệ từ allocation samples

Có thể nói: “Trong cùng tải, stack `PayloadParser.parse` chiếm phần lớn *estimated allocation weight*, tương ứng với nhiều lần tạo `byte[]`”. Chưa thể nói: “`PayloadParser.parse` giữ các mảng đó trong heap” trừ khi có bằng chứng retention độc lập.

Một tỷ lệ allocation cao có thể làm GC bận dù **đáy heap sau GC ổn định**. Tối ưu trường hợp này có thể tập trung vào reuse buffer, giảm copy, batching hợp lý hoặc hạn chế tạo object trung gian; cần đo lại latency/throughput sau thay đổi để tránh tối ưu vô ích.

## 4. GC events: xem tần suất, thời gian và loại GC

Các event thường dùng:

~~~bash
jfr print --events jdk.GarbageCollection memory-investigation.jfr
jfr print --events jdk.GCPhasePause memory-investigation.jfr
~~~

`jdk.GarbageCollection` thể hiện một hoạt động GC được JVM ghi nhận, thường có `gcId`, collector name/cause và `duration`. `jdk.GCPhasePause` bổ sung thông tin về những pha pause liên quan. Phân biệt **thời lượng hoạt động GC** với **thời gian ứng dụng thật sự bị stop-the-world**: với collector concurrent, toàn bộ hoạt động GC có thể gồm các pha chạy đồng thời cùng application threads; không lấy mọi `GarbageCollection.duration` làm tổng STW pause.

Điểm cần đọc theo thời gian:

1. GC có **lặp dày** đúng khi traffic hay allocation weight tăng không?
2. Pause p95/max có tăng, kéo theo tail latency của request không? Cần xem các pause cụ thể, không chỉ trung bình.
3. `gcId` nào tương ứng với bước giảm heap trong `GCHeapSummary`?
4. Collector có tạo thêm các concurrent cycle, full/old collection hoặc thay đổi kiểu hành vi? Tên event và loại collection phụ thuộc JDK/collector.
5. Có nhiều GC nhưng heap sau GC xuống thấp và ổn định không? Khi đó allocation churn là nghi phạm hơn retention leak.

**Ví dụ giả định:**

| Phút | Allocation pressure | GC count/phút | Heap sau GC | Cách hiểu ban đầu |
| --- | ---: | ---: | ---: | --- |
| 10:00 | Thấp | 2 | 180 MiB | Bình thường |
| 10:01 | Cao | 13 | 185 MiB | Nhiều object tạm, GC đang xử lý được |
| 10:02 | Cao | 15 | 184 MiB | Churn còn cao, chưa thấy live set tăng |
| 10:03 | Thấp | 2 | 181 MiB | Tải giảm, đáy heap quay lại bình thường |

Dữ liệu như vậy **không chứng minh leak**, dù tổng byte cấp phát rất lớn. Nếu latency xấu ở 10:01–10:02, ta có thể ưu tiên vị trí allocation nóng và pause metrics.

### GC ID và đối chiếu sự kiện

Các event GC/heap có thể cùng `gcId` để nối *trước GC → quá trình GC → sau GC*. Phân tích phải dựa trên ID và timestamp của recording cụ thể, đừng ghép tùy tiện mọi “before” và “after” liền kề nếu có event bị thiếu hay các cycle concurrent.

## 5. Heap summary: nhận diện xu hướng “đáy heap sau GC”

Lệnh xem:

~~~bash
jfr print --events jdk.GCHeapSummary memory-investigation.jfr
~~~

Với `jdk.GCHeapSummary` trên HotSpot, các field đáng quan tâm:

- `gcId`: mã nhận diện một GC cycle/collection trong dữ liệu.
- `when`: biểu thị thời điểm **Before GC** hay **After GC**.
- `heapUsed`: số byte heap đang được JVM báo sử dụng tại điểm snapshot.
- `heapSpace`: thông tin không gian heap, bao gồm vùng reserved và committed theo model của event.

Phân tích đúng cách là **ghép các cặp before/after theo `gcId`**. Ví dụ hoàn toàn giả định:

| GC ID | Heap trước GC | Heap sau GC | Chênh lệch | Ý nghĩa ban đầu |
| --- | ---: | ---: | ---: | --- |
| 41 | 730 MiB | 260 MiB | 470 MiB | Nhiều dung lượng được thu hồi |
| 42 | 740 MiB | 262 MiB | 478 MiB | Live set có vẻ ổn định |
| 43 | 780 MiB | 320 MiB | 460 MiB | Cần kiểm tra vì đáy tăng |
| 44 | 820 MiB | 390 MiB | 430 MiB | Có thể retention hoặc workload khác |

Số giảm giữa before/after phản ánh thay đổi occupancy trong một collection, **không phải** phép đo chính xác “số object đã chết” hay “số byte leak”. Heap committed có thể thay đổi độc lập; một số GC chỉ thu gom **một phần heap**, nên `After GC` của collection trẻ không tương đương “toàn heap đã được quét sạch”. Với G1 hoặc collector concurrent, cần hiểu phạm vi GC và trạng thái ứng dụng; đừng kết luận old generation tăng chỉ từ một vài young GC.

### 5.1. Phân biệt used, committed, reserved và max

- **Used:** dung lượng heap đang dùng theo phép đo tại thời điểm event.
- **Committed:** dung lượng JVM đã cam kết cho heap; không nhất thiết trùng với used hoặc RSS.
- **Reserved:** không gian địa chỉ ảo dành cho heap; không có nghĩa toàn bộ đang resident trong RAM.
- **Max heap:** giới hạn cấu hình JVM, thường liên hệ `-Xmx`; không đồng nhất với used/committed/reserved.

Cả `jdk.GCHeapSummary` và JFR metadata đều không phải thay thế cho việc kiểm tra `-Xmx` thực tế, non-heap, native memory và container memory. Khi process RSS tăng nhưng heap used sau GC không tăng, hãy kiểm tra thread stack, direct buffer, Metaspace, NMT/OS metrics thay vì gọi đó là Java heap leak.

### 5.2. “Đáy sau GC tăng” có ý nghĩa gì?

Nếu các lần Full GC/mixed/old GC ở tải tương đương cho thấy **after-GC heap** tăng dần và không giảm sau khi tải hạ, đây là dấu hiệu đáng kiểm tra của **retention**. Nhưng cũng có thể do cache warm-up hợp lệ, thêm connection/session, thay đổi dataset, request backlog hoặc collector chưa thu toàn bộ các vùng. Cần tìm ai giữ object rồi so với giới hạn/vòng đời thiết kế.

GC heap summary **không phải** histogram theo class; nó chưa chỉ ra class hay đường tới GC root. Đó là lý do cần kết hợp allocation sample, OldObjectSample và có thể HPROF.

## 6. OldObjectSample: điều tra object sống lâu và gốc tham chiếu

In các sự kiện:

~~~bash
jfr print --events jdk.OldObjectSample --stack-depth 20 memory-investigation.jfr
~~~

Một `jdk.OldObjectSample` có thể chứa:

| Trường | Cách hiểu |
| --- | --- |
| `allocationTime` | Thời điểm object được cấp phát, giúp phân biệt object cũ với object mới xuất hiện |
| `objectAge` | Tuổi của object mẫu khi JVM ghi nhận sự kiện |
| `object` | Đối tượng và một phần chain tham chiếu được công cụ mô tả; không phải toàn bộ heap graph |
| `root` | Thông tin gốc GC nếu việc thu đường GC root được bật và có dữ liệu |
| `stackTrace` | Stack tại nơi cấp phát khi profile/settings hỗ trợ |
| `lastKnownHeapUsage` | Mức heap usage gần nhất gắn với mẫu; xem theo xu hướng, không coi là retained size của riêng object |
| `eventThread` | Thread ghi nhận sự kiện, hỗ trợ truy dấu bối cảnh |

**Object sống lâu không đồng nghĩa leak.** Singleton, cache có giới hạn, dữ liệu cấu hình, class metadata liên quan đến runtime và các object dùng trọn vòng đời ứng dụng thường phải tồn tại lâu. Leak là **retention không còn phục vụ mục đích nhưng tiếp tục làm tăng live set**.

### 6.1. Muốn có đường tới GC roots: thu đúng thời điểm

Theo `jcmd` của **JDK 21**, tham số đúng trên lệnh dump là **`path-to-gc-root=true`** (dạng số ít `root`):

~~~bash
jcmd 12345 JFR.dump name=memory-investigation filename=/var/tmp/jfr/memory-roots.jfr path-to-gc-root=true
~~~

Thu đường tới GC roots có thể gây tạm dừng đáng kể và làm tăng chi phí xử lý. Chỉ bật khi có giả thuyết leak cụ thể, ở đúng recording và cửa sổ vận hành thích hợp. Tài liệu cấu hình JVM có thể dùng tên tùy chọn khác trong ngữ cảnh khởi động và giữa phiên bản; **luôn kiểm tra `jcmd 12345 help JFR.dump` trên JVM đích**, không sao chép nguyên xi tham số từ nguồn khác.

Nếu file không có `OldObjectSample`, không có nghĩa “không có leak”. Nguyên nhân có thể là recording quá ngắn, không đủ mẫu còn sống, collector/JDK không hỗ trợ trường hợp cần đo, profile chưa bật event, hoặc snapshot không đúng thời điểm. Cũng không thể tạo lại allocation stack đã bỏ lỡ trước lúc JFR bắt đầu ghi.

### 6.2. Đọc chuỗi tham chiếu

Ví dụ **minh họa** một sample của `com.example.Session` được giữ qua:

~~~text
GC Root (static field)
  -> SessionRegistry.INSTANCE
  -> ConcurrentHashMap.values
  -> Session(id=...)
~~~

Đường đi này gợi ý `SessionRegistry` đang giữ session sau khi user đã logout, nhưng mới là **giả thuyết**. Cần xác minh chính sách cleanup/TTL, số session đang hợp lệ, xu hướng kích thước map và đường dẫn GC roots của nhiều mẫu. Nếu cùng một registry tăng đều theo giờ và after-GC heap tăng cùng chiều, bằng chứng retention thuyết phục hơn.

Ngược lại, nếu một sample lớn được giữ bởi cache có giới hạn số entry và memory được thu hồi khi eviction, objectAge cao không tạo thành leak. Không dùng `OldObjectSample` như bảng kê chính xác số instance mỗi class; sampling sẽ bỏ sót object.

### 6.3. Phân biệt OldObjectSample với heap dump

| Tiêu chí | JFR `OldObjectSample` | HPROF heap dump |
| --- | --- | --- |
| Tập đối tượng | Mẫu các object sống lâu/có khả năng giữ | Ảnh chụp phạm vi lớn của Java heap tại một thời điểm |
| Dữ liệu về thời gian | Có thể gồm allocation time, tuổi object và bối cảnh ghi | Chủ yếu đồ thị trạng thái tại thời điểm chụp |
| Đường tới GC root | Có thể ghi khi yêu cầu và JVM hỗ trợ | Công cụ như MAT phân tích từ toàn bộ snapshot |
| Mức độ chi tiết | Mẫu, có thể không thấy thủ phạm | Có thể tính histogram và retained graph rộng hơn |
| Tác động | Thu mẫu thường nhẹ hơn heap dump nhưng tính GC roots có thể tốn kém | Heap dump thường nặng, có thể gây pause dài và tạo file rất lớn |

Nếu JFR cho thấy class/cache đáng nghi nhưng không đủ chứng cứ, dùng heap dump có thời điểm phù hợp để xem dominator tree/retained size. Đừng cộng `weight` từ allocation samples với `lastKnownHeapUsage` rồi gọi đó là retained heap.

## 7. Quy trình điều tra liên kết cả bốn nguồn bằng chứng

**Bước 1 — xác nhận symptom và thời gian.** Ghi lại latency, throughput, heap occupancy, GC pause, container memory và mốc release. Một spike allocation do warm-up có thể hoàn toàn hợp lệ.

**Bước 2 — đọc `jfr summary`.** Xác minh khoảng thời gian có chứa sự cố; kiểm tra đủ `ObjectAllocationSample`, `GarbageCollection`, `GCHeapSummary` và (khi cần) `OldObjectSample`. Số event 0 không phải kết luận về hành vi ứng dụng trước khi kiểm tra settings và sampling.

**Bước 3 — tìm allocation hot spots.** Nhóm sample theo stack/class/thread, ưu tiên **tổng weight đã được lấy mẫu trên cùng cửa sổ thời gian** hơn số event thô. Xác định code path cấp phát và biến động khi tải đổi.

**Bước 4 — đối chiếu GC.** Đếm GC theo đơn vị thời gian, xem causes, collector phases và **pause durations**; xác định load spike có trùng với tăng allocation, GC hoặc latency không.

**Bước 5 — ghép heap trước/sau theo `gcId`.** Nếu after-GC ổn định, nghi churn tạm; nếu sau các GC phù hợp mà live set tăng không kiểm soát, chuyển sang retention.

**Bước 6 — xem `OldObjectSample` và GC roots.** Chú ý objectAge, allocationTime, object class, owner chain, root, cùng chính sách vòng đời ứng dụng. Nếu thiếu root data, lên kế hoạch dump có `path-to-gc-root=true`; cân nhắc tác động pause.

**Bước 7 — kiểm chứng giả thuyết.** Xem metric của queue/cache/session, source code liên quan, heap dump khi cần; thay đổi logic lưu trữ, TTL, giới hạn cache hoặc giảm allocation và **đo lại cùng tải**. Nếu sau thay đổi allocation weight giảm nhưng after-GC không đổi, đó là cải thiện churn, không nhất thiết là sửa leak.

### Ma trận kết luận theo dạng bằng chứng

| Allocation weight | GC frequency/pause | Heap sau GC | Old objects/roots | Cách ưu tiên điều tra |
| --- | --- | --- | --- | --- |
| Cao | Tăng | Ổn định | Không có bằng chứng retention | Tìm allocation churn; tối ưu copy/object trung gian |
| Bình thường | Tăng, pause dài | Gần max | Object sống lâu tăng và root giữ trái kỳ vọng | Nghi retention/leak hoặc live set lớn |
| Cao | Cao | Tăng nhưng trở lại khi tải giảm | Object còn sống đúng vòng đời request/cache | Tải hoặc sizing; đừng gán leak khi chưa đủ bằng chứng |
| Không tăng | Không tăng | Ổn định | Không thấy nghi phạm | Nếu RSS vẫn tăng, điều tra native/off-heap |
| Thấp | Ít GC | Tăng dần | Có root tới map/list không giới hạn | Nghi cache/collection giữ object dù cấp phát mới không quá nhiều |

Các dòng chỉ là **mô hình suy luận**, không phải luật tuyệt đối. Trong thực tế GC có thể thu từng vùng, các kiểu collector có semantics khác nhau và sampling có sai số.

## 8. Thực hành Java 17+: tạo tải cấp phát và giữ một phần object

Ví dụ sau tạo mảng tạm thời và giữ một số mảng trong danh sách static để minh họa **allocation** và **retention**. Nó không mô phỏng đầy đủ một memory leak sản xuất, và dữ liệu được cố ý giới hạn để không làm cạn heap.

Tạo file **`JfrMemoryLab.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class JfrMemoryLab {
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile int checksum;

    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());

        for (int i = 0; i < 1_500; i++) {
            byte[] temporary = new byte[128 * 1024];
            temporary[0] = (byte) i;
            checksum += temporary[0];

            if (i % 100 == 0) {
                byte[] retained = new byte[256 * 1024];
                retained[0] = (byte) i;
                RETAINED.add(retained);
            }

            if (i % 150 == 0) {
                Thread.sleep(20L);
            }
        }

        System.out.println("Retained arrays=" + RETAINED.size());
        Thread.sleep(30_000L);
        System.out.println("Finished");
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ (HotSpot có JFR):

~~~bash
javac JfrMemoryLab.java
java -Xms32m -Xmx96m -XX:StartFlightRecording=name=memlab,settings=profile,filename=memlab.jfr,dumponexit=true JfrMemoryLab
~~~

Các dòng stdout do **chính chương trình** in:

~~~text
PID=<PID thực tế tại lần chạy>
Retained arrays=15
Finished
~~~

Mỗi lần khởi chạy PID khác nhau; dòng `Retained arrays=15` là xác định vì các giá trị `i=0,100,...,1400` thỏa điều kiện giữ mảng. `Finished` xuất hiện sau khoảng 30 giây chờ, trừ khi JVM bị ngắt. Tổng số mảng tạm được tạo là 1.500, nhưng JFR **không nhất thiết ghi 1.500 `ObjectAllocationSample`** vì đó là event lấy mẫu. Cấu hình `-Xmx96m` làm ví dụ trong phạm vi heap nhỏ, nhưng không bảo đảm một số lượng GC cố định trên mọi JVM.

Sau khi chương trình kết thúc bình thường, kiểm tra:

~~~bash
jfr summary memlab.jfr
jfr print --events jdk.ObjectAllocationSample --stack-depth 10 memlab.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary memlab.jfr
jfr print --events jdk.OldObjectSample memlab.jfr
~~~

- File `memlab.jfr` được yêu cầu ghi khi kết thúc bởi `dumponexit=true`; tên tệp được tính theo working directory của JVM.
- Tùy GC, JDK, event settings và thời gian lấy mẫu, **không có tập event hay con số sample/GC xác định chung**. Nếu `OldObjectSample` trống, đây không phải lỗi test.
- Trong 30 giây JVM còn chạy, có thể dùng `jcmd <PID> JFR.check` và chủ động `JFR.dump` với `path-to-gc-root=true` nếu thật sự cần thử root capture; cân nhắc chi phí và dùng file name khác.
- Sau khi exit, không thể attach vào PID cũ; hãy chạy lần mới nếu muốn thao tác tiếp.

### 8.1. Phân tích file bằng JFR Consumer API

Đây là chương trình **độc lập thứ hai**, không phụ thuộc class `JfrMemoryLab`. Nó đọc tuần tự event thay vì nạp toàn bộ một file lớn vào bộ nhớ, và in số mẫu theo nhóm event. Tạo file **`JfrMemoryReport.java`**:

~~~java
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.consumer.RecordedClass;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrMemoryReport {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java JfrMemoryReport <file.jfr>");
            return;
        }

        long allocationSamples = 0;
        long totalSampleWeight = 0;
        long gcEvents = 0;
        long heapSummaries = 0;
        long oldObjectSamples = 0;
        Map<String, Long> weightByClass = new HashMap<>();

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                String type = event.getEventType().getName();

                switch (type) {
                    case "jdk.ObjectAllocationSample" -> {
                        allocationSamples++;
                        long weight = event.getLong("weight");
                        totalSampleWeight += weight;

                        RecordedClass clazz = event.getClass("objectClass");
                        String name = clazz == null ? "<unknown>" : clazz.getName();
                        weightByClass.merge(name, weight, Long::sum);
                    }
                    case "jdk.GarbageCollection" -> gcEvents++;
                    case "jdk.GCHeapSummary" -> heapSummaries++;
                    case "jdk.OldObjectSample" -> oldObjectSamples++;
                    default -> { /* Other JFR event types are ignored. */ }
                }
            }
        }

        System.out.println("Allocation samples=" + allocationSamples);
        System.out.println("Sample weight (bytes)=" + totalSampleWeight);
        System.out.println("GC events=" + gcEvents);
        System.out.println("Heap summary events=" + heapSummaries);
        System.out.println("Old object samples=" + oldObjectSamples);
        weightByClass.entrySet().stream()
                .sorted((a, b) -> Long.compare(b.getValue(), a.getValue()))
                .limit(5)
                .forEach(e -> System.out.println(
                        e.getKey() + " => " + e.getValue()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac JfrMemoryReport.java
java JfrMemoryReport memlab.jfr
~~~

Chương trình in các nhãn `Allocation samples=...`, `GC events=...` cùng top 5 class. **Các con số và tên class là dữ liệu runtime**, nên không có stdout số cố định đáng tin. Tổng `Sample weight (bytes)` chỉ là cách **cộng trọng số mẫu để so áp lực allocation**, không phải chính xác “số byte còn sống” hay tổng byte được cấp phát; nếu dùng để so hai build cần cùng profile, cửa sổ ghi và khối lượng công việc.

Lưu ý: ví dụ báo cáo đơn giản mới **đếm** event GC và heap; để phân tích nghiêm túc phải đọc thêm `getDuration()` của event GC, `gcId`/`when`/`heapUsed` của `GCHeapSummary`, timestamp và stack trace. Dữ liệu input phải là file JFR đáng tin cậy; không mở các file đến từ nguồn không rõ trong tool có quyền cao.

## 9. Ba tình huống chẩn đoán và cách tránh kết luận vội

### A. Allocation cao, GC nhiều nhưng heap sau GC ổn định

Bảng JMC cho thấy `byte[]` allocation weight rất lớn tại một HTTP decoder. Số GC/phút tăng khi request throughput tăng, song after-GC heap vẫn quanh 250 MiB. `OldObjectSample` không chỉ ra object giữ bất thường. Đây giống **allocation churn**. Đo lượng copy mỗi request, batch parsing, buffer management; thử tối ưu rồi so throughput, GC pause và allocation weight trên cùng tải.

### B. Allocation không vượt trội, after-GC heap tăng liên tục

Tổng sample weight của request handler không lớn hơn trước, nhưng heap sau các GC phù hợp tăng từ 200 → 400 → 650 MiB khi số người dùng thực tế không đổi. `OldObjectSample` nhiều lần dẫn tới một static `ConcurrentHashMap` giữ dữ liệu session cũ. Đây là **nghi vấn retention**: xem TTL, cleanup job, key cardinality, số map entry, thao tác remove và xác minh bằng heap dump/MAT nếu cần. Không gọi chắc chắn leak nếu chưa phân biệt cache warming với session không còn hợp lệ.

### C. RSS tăng, heap sau GC không đổi

Khi JFR cho thấy after-GC heap ổn định và allocation pressure không tăng, nhưng OS/container báo memory tiến trình ngày càng lớn, chưa có chứng cứ Java heap leak. Hãy xem **direct buffers, thread stacks, Metaspace, JNI/native allocations** với NMT/OS/cgroup, không bắt `OldObjectSample` giải thích mọi loại memory.

## 10. Lỗi và giới hạn thường gặp

| Dấu hiệu | Giải thích/cách xử lý |
| --- | --- |
| Không có `ObjectAllocationSample` | Chưa bật event, cửa sổ quá ngắn, workload không đủ mẫu hoặc recording không chứa thời điểm cần đo. Xem `jfr summary` và settings |
| Có sample nhưng không thấy stack | Event stack trace có thể bị tắt/rút ngắn; xem `verbose` settings hoặc `jfr print --stack-depth` |
| `ObjectAllocationSample.weight` khác kích thước object | Đúng thiết kế: weight biểu thị allocation được đại diện thống kê; không lấy làm kích thước chính object |
| Nhiều `GCHeapSummary` nhưng không ghép được | Cần `gcId` và `when`; một số cặp missing do recording boundary/lọc, hoặc loại GC chỉ báo một phần |
| After-GC heap cao sau young GC | Young GC có thể không thu các đối tượng old; cần xem loại GC và xu hướng qua các lần collection phù hợp |
| `GarbageCollection.duration` lớn | Với collector concurrent, duration không phải hoàn toàn STW; xem thêm pause/phase events |
| `OldObjectSample` trống | Không đủ mẫu sống lâu, event không bật, runtime/collector không hỗ trợ hoặc ghi sai thời điểm; không suy ra “không có leak” |
| `OldObjectSample.root` thiếu | Chưa yêu cầu GC roots hoặc chưa thu được; cân nhắc `JFR.dump ... path-to-gc-root=true` và chi phí pause |
| File `.jfr` lớn/thiếu lịch sử | Cân bằng profile, duration, retention `maxage`/`maxsize`; lịch sử đã bị loại không thể tạo lại |
| `jcmd` không attach được | Kiểm tra PID, user/group, container namespace, runtime và việc JVM còn sống; dùng JFR flag khi start nếu không thể attach |
| Đọc `.jfr` nhầm là HPROF | JFR là event timeline; HPROF là heap snapshot. Dùng công cụ thích hợp cho từng loại |
| Đếm số event rồi suy ra hiệu năng | Sampling và điều kiện kích hoạt khác nhau; cần chuẩn hóa theo thời gian, workload và settings |

**Quy tắc quyết định cuối:** hỏi **“ai cấp phát?”** bằng allocation sample; **“GC làm gì và tốn bao lâu?”** bằng GC events; **“bao nhiêu heap còn lại sau GC?”** bằng heap summary; **“ai còn giữ object sống lâu?”** bằng OldObjectSample và GC roots. Kết hợp các góc nhìn trên cùng timeline mới giúp phân biệt allocation churn, GC pressure và memory retention.

## Tài liệu tham khảo

- Oracle Java SE 21 — *The jfr Command* (summary, print, metadata, view): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java SE 21 — *The jcmd Command* (JFR.start/JFR.dump, `path-to-gc-root`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java SE 21 — *Troubleshoot Memory Leaks* (giải thích `OldObjectSample`, allocation time, GC roots): https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html
- Oracle Java SE 21 — *Diagnostic Tools* (phân tích GC, allocation, JMC): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Java SE 21 — *RecordingFile* trong JFR Consumer API: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html
- Dev.java — *Configuring the JDK Flight Recorder* (`default.jfc`, `profile.jfc`, event settings và GC roots): https://dev.java/learn/jvm/jfr/configure/
