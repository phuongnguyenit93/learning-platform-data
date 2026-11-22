# Tình huống G1 phải dùng đến Full GC (Java 10+)

## 1. Khái niệm và mục tiêu

**Garbage-First Garbage Collector (G1 GC)** là bộ thu gom rác theo vùng (*regions*) của HotSpot JVM. G1 cố gắng thu hồi bộ nhớ từng phần, kết hợp các pause ngắn với những công việc chạy đồng thời với ứng dụng. Trong điều kiện bình thường, G1 sử dụng **young GC**, **concurrent marking** và **mixed GC**, không cần thường xuyên thu gom và nén toàn bộ heap.

Nhưng khi tiến độ thu hồi không đủ đáp ứng nhu cầu cấp phát, G1 có thể phải dùng **Full GC** như một phương án dự phòng (*fallback*). Đây là một lượt **stop-the-world (STW)** xử lý và nén toàn heap, thường gây độ trễ lớn hơn các young/mixed collections.

**Java 10 — JEP 307: Parallel Full GC for G1** cải thiện trường hợp dự phòng này bằng cách **thực hiện công việc Full GC song song bằng nhiều GC worker threads**. Song song **không có nghĩa concurrent**: application threads vẫn dừng trong Full GC và không có bảo đảm pause ngắn.

Bài học thuộc nhóm **G1 Full GC song song**, tập trung vào câu hỏi: **Trong tình huống nào G1 phải dùng đến Full GC, nhận biết ra sao và xử lý như thế nào?**

Sau bài học, bạn sẽ có thể:
1. Phân biệt **Full GC** với các pause/chu kỳ G1 bình thường.
2. Giải thích **evacuation failure**, đặc biệt là thiếu không gian đích (*to-space*).
3. Hiểu vì sao **old generation** tăng quá nhanh hoặc **concurrent marking** không hoàn tất kịp có thể dẫn tới fallback.
4. Giải thích **humongous object allocation**, yêu cầu các region liên tiếp và phân mảnh.
5. Phân biệt Full GC do **allocation pressure** và Full GC do **`System.gc()`**/công cụ bên ngoài.
6. Nhận diện `Pause Full` trong GC logs của JDK hiện đại mà không nhầm với `Pause Young`.
7. Hiểu cải tiến Full GC song song từ Java 10 và những giới hạn của nó.
8. Xây dựng quy trình điều tra dựa trên heap occupancy, GC cause, region counts, allocation rate và retained data.

**Phiên bản:** Kiến thức G1 được trình bày theo HotSpot/JDK hiện đại; ví dụ Java độc lập sử dụng **JDK 17+**. Các định dạng log JDK 17 và JDK mới hơn có thể khác nhau; không giả định một chuỗi log duy nhất tồn tại ở mọi bản.

## 2. Ôn lại cách G1 thu gom bình thường

Java heap dưới G1 được chia thành các **region** có kích thước đồng nhất. Những region ấy có thể được sử dụng cho:
- **Eden:** phần lớn object mới được cấp phát tại đây.
- **Survivor:** object trẻ sống sót qua GC.
- **Old:** object sống lâu hoặc được promote.
- **Humongous:** object rất lớn, thường được cấp trực tiếp vào old regions.
- **Free:** region còn trống để cấp phát hoặc di chuyển object.

Với young/mixed GC, G1 chọn một **collection set**. Các object còn sống trong những region được chọn thường được **copy sang region đích**, rồi các region nguồn có thể được tái sử dụng. Hoạt động này gọi là **evacuation**.

Chu trình được đơn giản hóa:

~~~text
Ứng dụng cấp phát object
      │
      ▼
Young GC: dọn Eden/Survivor
      │
      ├─ Object sống → Survivor/Old
      └─ Region nguồn → Free
      │
      ▼
Old occupancy tăng đến điều kiện khởi động marking
      │
      ▼
Concurrent marking: xác định object sống ở Old
      │
      ▼
Mixed GCs: thu hồi các old regions được chọn
      │
      ▼
Ứng dụng tiếp tục cấp phát
~~~

G1 có mục tiêu thu hồi bộ nhớ theo từng phần, với **pause-time goal** mềm. Nếu việc cấp phát hoặc di chuyển object không còn được đáp ứng, hệ thống có thể chuyển sang đường dự phòng:

~~~text
Free regions giảm
      │
      ├─ Concurrent marking chưa kịp tạo cơ hội thu hồi
      │
      ├─ Di chuyển object sống thiếu destination space
      │
      └─ Object lớn cần các regions liên tiếp
      │
      ▼
G1 tìm cách tiếp tục các GC phù hợp
      │
      ├─ Thu hồi đủ chỗ → ứng dụng tiếp tục
      │
      └─ Không thu hồi đủ → Full GC (STW, compact)
                                │
                                ├─ Có đủ chỗ → tiếp tục
                                └─ Vẫn thiếu → có thể OutOfMemoryError
~~~

Sơ đồ chỉ biểu diễn **chuỗi tình huống có thể xảy ra**; không phải state machine cố định ở mọi phiên bản G1.

## 3. Full GC khác Young GC, Mixed GC và Remark

| Sự kiện | Công việc chính | Dừng ứng dụng? | Có phải Full GC? |
| --- | --- | --- | --- |
| `Pause Young (Normal)` | Thu gom collection set gồm young regions | Có, STW pause | **Không** |
| `Pause Young (Concurrent Start)` | Young collection và bắt đầu chu kỳ marking | Có ở young pause | **Không** |
| `Concurrent Mark Cycle` | Xác định object sống, phần lớn công việc concurrent | Có thể có các pause thành phần | **Không** |
| `Pause Remark` | Hoàn tất đánh dấu và công việc liên quan | Có | **Không** |
| `Pause Cleanup` | Hoàn tất công việc dọn/chuẩn bị | Có ở pause tương ứng | **Không** |
| `Pause Young (Mixed)` | Young + một số old regions | Có, STW pause | **Không** |
| `Pause Full` | Thu gom và nén toàn heap | **Có, STW** | **Có** |

**Không nhầm “STW” với “Full GC”.** Young GC cũng có stop-the-world pause. Ngược lại, **G1 Full GC dù song song bên trong vẫn là stop-the-world**.

Tùy chọn `-XX:MaxGCPauseMillis` biểu thị **mục tiêu mềm**; nó không bảo đảm rằng mọi GC, đặc biệt Full GC, đều kết thúc trước thời gian đã đặt.

## 4. Tình huống thứ nhất: evacuation failure vì thiếu vùng đích

Đây là nguyên nhân quan trọng nhất cần điều tra khi thấy Full GC do áp lực cấp phát.

### Evacuation cần destination space

Trong một young/mixed collection, G1 phải chuyển các object còn sống khỏi region nguồn sang survivor hoặc old region đích. Giả sử:
- Heap đã có nhiều old regions đang chứa object sống.
- Young GC có rất nhiều object sống sót và phải promote.
- Free regions còn ít.
- G1 không tìm được đủ chỗ để copy một số object.

Đây là **evacuation failure**. Trên những JDK khác nhau, tín hiệu có thể được ghi là:

~~~text
To-space exhausted
~~~

hoặc ở những phiên bản hỗ trợ reason chi tiết:

~~~text
Evacuation Failure: Allocation
~~~

`Allocation` ở đây phản ánh **không có đủ không gian đích để di chuyển object**.

### Failure không đồng nghĩa lập tức Full GC

Không nên lập luận:

~~~text
To-space exhausted ⇒ bắt buộc Full GC ở ngay pause kế tiếp
~~~

G1 có thể để lại các object chưa di chuyển và đưa những region liên quan vào kế hoạch xử lý trong các lượt GC sau. **Chỉ khi việc thu gom không cung cấp đủ dung lượng cần thiết**, G1 mới có thể phải dùng Full GC như phương án cuối.

Cách đọc đúng:
1. **Warning:** thấy `To-space exhausted` hoặc `Evacuation Failure`.
2. **Nguy cơ:** việc reclaim/evacuation không đạt mục tiêu.
3. **Bằng chứng Full GC:** xuất hiện **dòng `Pause Full`** riêng.
4. **Đánh giá kết quả:** xem heap occupied sau Full GC và các lần GC kế tiếp.

Evacuation failure có thể đi kèm allocation rate cao, promotion tăng, old live set lớn hoặc heap quá nhỏ. **Không kết luận memory leak chỉ từ một failure.**

### Vì sao thiếu vùng đích dù heap chưa đạt 100%?

Vì evacuation không chỉ cần “một tổng số byte rảnh”. Nó cần các destination regions đủ dùng **ngay thời điểm GC cần copy object**. Một phần dung lượng còn trống trên lý thuyết không nhất thiết chuyển được thành vùng đích phù hợp với tiến độ GC hiện tại.

Ngoài ra, ứng dụng có thể tăng allocation rate nhanh hơn khả năng G1 thu hồi free regions.

## 5. Tình huống thứ hai: concurrent marking và mixed GC không theo kịp

G1 dùng **concurrent marking** để xác định tình trạng sống/chết của object ở old generation. Sau khi có thông tin đủ phù hợp, **mixed collections** có thể chọn old regions chứa nhiều garbage để thu hồi.

Nếu **old occupancy tăng quá nhanh**, chu kỳ marking có thể **bắt đầu quá muộn hoặc hoàn tất quá muộn**. Khi đó mixed collections chưa có cơ hội thu hồi đủ bộ nhớ, trong khi ứng dụng vẫn cấp phát và promote object.

Chuỗi thường gặp:

~~~text
Allocation/promotion rate tăng
      │
      ▼
Old occupancy tăng nhanh
      │
      ▼
Concurrent marking chưa kịp hoàn tất
      │
      ▼
Mixed GC chưa thu hồi đủ Old
      │
      ▼
Free regions giảm
      │
      ▼
Evacuation/allocation pressure → Full GC có thể xảy ra
~~~

Ví dụ:
- Một tác vụ batch tạo rất nhiều object còn sống trong khoảng thời gian ngắn.
- Cache giữ nhiều phần tử lớn và đẩy nhanh việc sử dụng old generation.
- Một service nhận nhiều request cùng lúc, tạo queue dài.
- Ứng dụng có quá nhiều object sống để promotion so với heap budget.

**IHOP** (*Initiating Heap Occupancy Percent*) liên quan thời điểm G1 bắt đầu concurrent marking. HotSpot hiện đại thường sử dụng các heuristic thích ứng theo hoạt động trước đó. Khi workload thay đổi đột ngột, dự đoán có thể không đủ tốt.

### Điều tra trước khi chỉnh tuning flags

Kiểm tra:
- **Old occupancy** theo thời gian, không chỉ một mẫu.
- Allocation rate, promotion rate và peak load.
- Khi nào concurrent mark bắt đầu, kéo dài bao lâu, hoàn tất trước áp lực allocation không.
- Mixed GC có diễn ra không, thu hồi được bao nhiêu.
- Có xuất hiện `Evacuation Failure` và `Pause Full` trong cùng khoảng thời gian không.

Hướng xử lý thường cần xem **ứng dụng** trước:
1. Giảm số object sống lâu hoặc thời gian giữ tham chiếu.
2. Kiểm tra cache, queue, batch size, stream data thay vì giữ mọi thứ trên heap.
3. Tăng heap khi live set hợp lệ thực sự cần nhiều bộ nhớ và hệ thống còn RAM.
4. Sau khi có log, cân nhắc các cờ thích hợp như `-XX:G1ReservePercent`, `-XX:ConcGCThreads`, tham số IHOP đúng **phiên bản JDK**, không thay hàng loạt theo công thức cứng.

Oracle khuyến nghị **bắt đầu từ G1 defaults**, điều chỉnh ít tham số dựa trên dữ liệu đo được.

## 6. Tình huống thứ ba: humongous allocation và heap fragmentation

Trong G1, object có kích thước **bằng hoặc lớn hơn khoảng một nửa heap region** được xem là **humongous**.

Đặc điểm:
- Thường được cấp trực tiếp trong old-generation regions.
- Có thể chiếm **nhiều region liên tiếp**.
- Không di chuyển như object nhỏ trong các GC thông thường.
- Phần cuối region của một object humongous có thể còn dư nhưng không được tận dụng như các free regions bình thường.
- G1 có thể thu hồi object humongous đã chết trong những hoạt động GC phù hợp.

### Tổng chỗ trống khác chỗ trống liên tiếp

Ví dụ cấu trúc region đơn giản:

~~~text
[Free][Old][Free][Old][Free][Free][Old][Free]
~~~

Có **năm Free regions** nhưng **không có ba Free regions liền nhau**. Một object cần ba region liên tiếp có thể khó cấp phát dù tổng số region rảnh trông lớn hơn nhu cầu.

Đó là **fragmentation**. Khi thiếu contiguous regions:
- G1 có thể khởi động marking hoặc thu gom theo những cơ chế của nó.
- Những allocation humongous liên tục làm áp lực lớn hơn.
- Full GC có thể được dùng để compact, tìm thêm không gian liên tiếp.
- Nếu Full GC không tạo đủ chỗ, ứng dụng có thể gặp `OutOfMemoryError`.

### `G1 Humongous Allocation` không có nghĩa là Full GC

Dòng log dạng:

~~~text
Pause Young (Concurrent Start) (G1 Humongous Allocation)
~~~

chỉ thể hiện **young pause liên quan tới việc khởi động concurrent marking do humongous allocation**. Nó **không phải** một `Pause Full`.

Khi điều tra, tìm thêm:

~~~text
Humongous regions: 14->11
~~~

Đây là ví dụ hình thức log: số region humongous trước/sau một GC, không phải số liệu đo thực của người đọc. Kiểm tra cả **heap region size** và những loại object lớn như `byte[]`, `char[]`, buffer, cache blobs, dữ liệu serialization.

**Hướng xử lý:** tránh tạo object quá lớn không cần thiết, giới hạn batch/cache, xem cách chunk/stream dữ liệu. `-XX:G1HeapRegionSize` có thể thay đổi tỷ lệ object bị xếp loại humongous, nhưng có trade-off và cần đo, không phải cờ “chữa Full GC” phổ quát.

## 7. Tình huống thứ tư: live set quá lớn hoặc memory leak

Full GC không thể xóa những object **vẫn còn reachable** từ GC roots.

Khi phần lớn heap chứa dữ liệu còn sống:
- Young GC reclaim ít.
- Mixed GC reclaim ít nếu Old chủ yếu là live objects.
- Full GC có thể compact nhưng không tạo nhiều free space.
- Ứng dụng nhanh chóng đầy lại và có thể trải qua **Full GC liên tiếp**.
- Nếu vẫn không cấp phát được, có thể phát sinh `OutOfMemoryError: Java heap space` hoặc một lỗi tài nguyên khác tùy tình huống.

Ví dụ **giả lập về cách đọc occupancy**, không phải log đã thu từ JVM thật:

~~~text
GC(71) Pause Full (G1 Compaction Pause) 980M->945M(1024M)
GC(72) Pause Full (G1 Compaction Pause) 1001M->987M(1024M)
~~~

Ở lần đầu, heap giảm **35 MiB**, lần sau giảm **14 MiB**, trong khi sau Full GC vẫn gần đầy. Đây là tín hiệu **live set/retention cao**, không phải bằng chứng tự động của memory leak.

Có thể là:
- Một ứng dụng hợp lệ cần rất nhiều RAM nhưng heap budget không đủ.
- Cache không giới hạn; hàng đợi backlog.
- Dữ liệu batch được giữ hết trong bộ nhớ.
- Đường tham chiếu GC roots giữ object ngoài ý muốn.

Muốn phân biệt, kiểm tra **heap dump**, retained-size analysis, object histogram, object counts theo thời gian và các đường tham chiếu đến GC roots.

**Không chỉ tăng `-Xmx` để giấu một leak thực**. Tăng heap có thể giúp khi live set lớn hợp lệ nhưng chỉ trì hoãn một cache tăng vô hạn.

## 8. Tình huống thứ năm: Full GC do yêu cầu rõ ràng

Không phải mọi Full GC đều do allocation failure.

### `System.gc()`

~~~java
System.gc();
~~~

Đây là **lời yêu cầu**, không phải bảo đảm JVM sẽ tạo đúng một Full GC ở mọi runtime.

Trên HotSpot/G1, explicit GC có thể dẫn tới một Full GC tùy cấu hình. Các JVM options liên quan:

~~~text
-XX:+ExplicitGCInvokesConcurrent
-XX:+DisableExplicitGC
~~~

- `ExplicitGCInvokesConcurrent`: làm yêu cầu `System.gc()` trên G1 sử dụng một hướng thu gom concurrent phù hợp thay vì mặc định yêu cầu full-heap STW theo cách thông thường.
- `DisableExplicitGC`: bỏ qua yêu cầu `System.gc()` từ code; **không ngăn JVM tự thu gom khi thiếu bộ nhớ**.

Đây là những **lựa chọn cần đánh giá theo runtime và ứng dụng**, không phải hai cờ nên bật mặc định. Một số ứng dụng/thư viện có lý do riêng để yêu cầu thu gom; cần xác định call site trước khi thay đổi.

### Công cụ quản trị

Một agent hoặc công cụ bên ngoài có thể yêu cầu GC theo cơ chế được VM hỗ trợ. Khi log có Full GC nhưng không có dấu hiệu heap thiếu chỗ, phải xem **GC cause** và hoạt động quản trị trong khoảng thời gian tương ứng.

Không chạy một lệnh cưỡng bức GC trên production **chỉ để thử**: nó có thể gây STW pause và ảnh hưởng người dùng.

### Periodic GC khi cấu hình đặc biệt

Một số HotSpot G1 hỗ trợ periodic GC với tùy chọn như `-XX:G1PeriodicGCInterval` và hành vi concurrent/full tùy các cờ liên quan. Đây không phải khẳng định mọi JDK luôn thực hiện Full GC khi hệ thống idle. Kiểm tra **cấu hình thực tế** và tài liệu của bản JDK đang dùng.

### Bảng phân biệt nguyên nhân

| Nhóm | Tín hiệu quan trọng | Không nên kết luận ngay |
| --- | --- | --- |
| Allocation pressure | Old occupancy cao, evacuation failure, heap gần đầy | Chắc chắn có leak |
| Marking không theo kịp | Old tăng mạnh, concurrent cycle chưa reclaim kịp | Mọi concurrent marking là vấn đề |
| Humongous fragmentation | Nhiều humongous regions, cần vùng liên tiếp | Mỗi humongous allocation đều Full GC |
| Explicit request | GC cause `System.gc()` hoặc request ngoài | Heap bị thiếu chỗ |
| Config/periodic | Full GC trùng lịch periodic được cấu hình | Đây là mặc định mọi JVM |

## 9. Evacuation failure trên JDK mới: `Allocation` khác `Pinned`

HotSpot/G1 đã phát triển cơ chế eviction/evacuation và ghi log chi tiết hơn trong các JDK mới. Một số bản có thể hiển thị:

~~~text
Evacuation Failure: Allocation
Evacuation Failure: Pinned
Evacuation Failure: Allocation/Pinned
~~~

- **Allocation:** thiếu vùng đích để copy object.
- **Pinned:** một object/region bị giữ tại vị trí hiện tại vì tương tác native/JNI; GC chưa thể di chuyển nó như bình thường.
- **Allocation/Pinned:** có thể có hơn một yếu tố trong cùng pause.

**Pinning không đồng nghĩa heap leak hoặc cạn bộ nhớ.** G1 được cải tiến khả năng region pinning trong các JDK mới, liên quan **JEP 423**. Nếu vì pinning một region không được dọn như dự kiến, cần nhìn thêm kết quả của những lần GC sau đó để biết có gây pressure nghiêm trọng không.

Dùng hướng tiếp cận theo phiên bản:
- JDK 17 thường có tín hiệu `To-space exhausted`.
- Nhiều JDK mới sử dụng `Evacuation Failure` và có thể in reason chi tiết.
- **Dấu hiệu failure** không thay thế việc xác nhận **`Pause Full`**.
- Không tự viết parser chỉ tìm một từ rồi dùng cho tất cả JDK.

## 10. Java 10: Full GC của G1 được song song hóa, nhưng vẫn STW

**JEP 307 — Parallel Full GC for G1** ra đời để giảm worst-case latency của G1 khi buộc phải thực hiện Full GC. Trước cải tiến này, đường Full GC của G1 còn có hạn chế về khả năng sử dụng nhiều luồng. Từ Java 10, các pha xử lý liên quan Full GC được song song hóa bằng GC worker threads.

Phân biệt hai từ thường bị nhầm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Parallel GC work** | Nhiều GC worker threads cùng thực hiện công việc GC |
| **Concurrent GC work** | Một phần công việc GC diễn ra đồng thời với application threads |
| **Stop-the-world** | Application threads tạm dừng trong một giai đoạn GC |

G1 Full GC có thể **parallel** bên trong mà vẫn **stop-the-world**. Nó cũng **không tự chuyển sang collector `ParallelGC` riêng**.

### Threads và thời gian pause

Tùy chọn `-XX:ParallelGCThreads` có thể ảnh hưởng đến số worker ở các pha GC song song. Nhưng tăng số luồng **không bảo đảm Full GC nhanh hơn**, vì:
- Bộ nhớ và băng thông cache có giới hạn.
- CPU quota/container limits có thể thấp.
- Live set và fragmentation ảnh hưởng khối lượng công việc.
- Quá nhiều luồng có thể tạo overhead và cạnh tranh CPU.
- Cờ này còn tác động đến các pha khác, không riêng Full GC.

**Bài học từ Java 10:** Full GC có thể xử lý tốt hơn trong trường hợp xấu, nhưng **cần ngăn nguyên nhân khiến G1 rơi vào Full GC**, thay vì coi song song hóa là lời giải triệt để.

## 11. Cách nhận diện Full GC bằng Unified Logging

Trên HotSpot JDK hiện đại, có thể bật log:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info:file=g1.log:time,uptime,level,tags -jar app.jar
~~~

Đây là lệnh **minh họa**: cần sẵn `app.jar`, quyền ghi file log và dung lượng đủ. Không phải lệnh tự kích hoạt Full GC. Trong production, quản lý vòng quay log và chọn mức logging phù hợp để tránh I/O overhead.

Để xem phân bố các loại region:

~~~bash
java -XX:+UseG1GC -Xlog:gc*,gc+heap=info:file=g1.log:time,uptime,level,tags -jar app.jar
~~~

**Không dùng các GC logging flags legacy đã bị thay bằng Unified Logging** trên JDK hiện đại.

### Mẫu cần tìm

| Chuỗi trong log | Diễn giải |
| --- | --- |
| `Pause Full` | Có sự kiện **Full GC** |
| `G1 Compaction Pause` | Nhãn của quá trình Full GC compaction ở một số JDK |
| `To-space exhausted` | Thiếu destination space trong evacuation, format thường gặp ở JDK cũ hơn |
| `Evacuation Failure: Allocation` | Evacuation thiếu vùng đích ở JDK mới |
| `Evacuation Failure: Pinned` | Evacuation bị ảnh hưởng bởi pinning |
| `G1 Humongous Allocation` | Sự kiện liên quan allocation object lớn; **không đồng nghĩa Full GC** |
| `Humongous regions: X->Y` | Region humongous trước/sau GC |
| `System.gc()` | Một GC cause/request có thể xuất hiện |
| `Pause Young (Mixed)` | Mixed GC, **không phải Full GC** |
| `Pause Remark` | Pause thuộc marking, **không phải Full GC** |

### Cú pháp Full GC thay đổi giữa các phiên bản

Một số JDK báo nguyên nhân `Allocation Failure` trong dòng Full GC; các JDK khác dùng nhãn `G1 Compaction Pause`. **Đừng chỉ tìm `Allocation Failure` để đếm Full GC.** Đầu mối chính là `Pause Full` cùng GC ID và thông tin lân cận.

Dòng **giả lập về cấu trúc**, không phải một phép đo thực tế:

~~~text
[12.345s][info][gc] GC(45) Pause Full (G1 Compaction Pause) 950M->700M(1024M) 450.0ms
~~~

Ý nghĩa:
- `GC(45)`: ID của sự kiện, giúp nối các dòng liên quan.
- `Pause Full`: bằng chứng một Full GC.
- `950M->700M(1024M)`: heap occupied trước, sau và capacity ở thời điểm được báo.
- `450.0ms`: thời gian pause được báo cho sự kiện.
- `12.345s`: uptime trong decorator của log nếu cấu hình có.

Từ số liệu mẫu, heap giảm `250 MiB`. Không thể chỉ từ một dòng khẳng định object loại nào được dọn hoặc nguồn gốc Full GC. Cần xem **old/humongous regions, sự kiện trước đó, concurrent cycle và dữ liệu ứng dụng**.

### Dấu hiệu đáng lo

- `Pause Full` xuất hiện nhiều lần trong thời gian ngắn.
- Heap occupied sau mỗi Full GC vẫn gần `-Xmx`.
- Thời gian pause tăng cao hoặc làm request timeout.
- Nhiều `Evacuation Failure` trước Full GC.
- Humongous region count tăng và nhiều object lớn.
- Concurrent marking chưa kịp hoàn tất trước áp lực cấp phát.

**Một Full GC đơn lẻ có explicit cause không có cùng ý nghĩa với chuỗi Full GC vì thiếu bộ nhớ.**

## 12. Chương trình Java 17+ độc lập: đọc tín hiệu Full GC

Không cần cố gây `OutOfMemoryError` chỉ để học. Chương trình sau phân loại một tập **dòng log giả lập** có thể đọc độc lập và cho stdout xác định. Nó minh họa vì sao cần phân biệt `Pause Full`, `To-space exhausted`, `G1 Humongous Allocation` và `System.gc()`.

Tạo file **G1FullGcSignalsDemo.java**:

~~~java
import java.util.List;

public class G1FullGcSignalsDemo {

    static void analyze(List<String> lines) {
        int fullEvents = 0;
        int explicitFullEvents = 0;
        int evacuationWarnings = 0;
        int humongousSignals = 0;

        for (String line : lines) {
            boolean full = line.contains("Pause Full");

            if (full) {
                fullEvents++;
                if (line.contains("System.gc()")) {
                    explicitFullEvents++;
                }
            }

            if (line.contains("To-space exhausted")
                    || line.contains("Evacuation Failure: Allocation")) {
                evacuationWarnings++;
            }

            if (line.contains("G1 Humongous Allocation")) {
                humongousSignals++;
            }
        }

        System.out.println("full events = " + fullEvents);
        System.out.println("explicit full events = " + explicitFullEvents);
        System.out.println("other full events = "
                + (fullEvents - explicitFullEvents));
        System.out.println("evacuation warnings = "
                + evacuationWarnings);
        System.out.println("humongous signals = " + humongousSignals);
        System.out.println("warning forces immediate Full GC = false");
        System.out.println("humongous event itself is Full GC = false");
    }

    public static void main(String[] args) {
        List<String> trainingLog = List.of(
            "GC(11) Pause Young (Normal) (G1 Evacuation Pause)",
            "GC(12) Pause Young (Concurrent Start)"
                    + " (G1 Humongous Allocation)",
            "GC(13) To-space exhausted",
            "GC(13) Pause Young (Normal) (G1 Evacuation Pause)",
            "GC(14) Pause Full (G1 Compaction Pause)",
            "GC(15) Pause Full (System.gc())"
        );

        analyze(trainingLog);
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac --release 17 G1FullGcSignalsDemo.java
java G1FullGcSignalsDemo
~~~

**Stdout chính xác:**

~~~text
full events = 2
explicit full events = 1
other full events = 1
evacuation warnings = 1
humongous signals = 1
warning forces immediate Full GC = false
humongous event itself is Full GC = false
~~~

Giải thích:
1. Có hai dòng `Pause Full`, nên bộ đếm Full bằng 2.
2. Một Full GC chứa `System.gc()`, được phân loại explicit.
3. Có một dòng `To-space exhausted`, chỉ báo warning.
4. Có một dòng `G1 Humongous Allocation`, nhưng đây là **young pause**, không phải Full GC.
5. Hai dòng kết quả `false` diễn giải đúng rằng **warning không chứng minh Full GC lập tức**.

**Giới hạn:** Các dòng training là **giả lập**, không phải GC log đã đo trên máy. Trình đọc bằng `String.contains` chỉ để học; công cụ production cần xử lý event IDs, timestamps, log multiline, format JDK khác nhau, heap/region stats và nguyên nhân thực. **Không cộng các dòng log tùy ý rồi coi đó là số event đáng tin nếu một sự kiện được in nhiều dòng.**

## 13. Có nên cố ép JVM sinh Full GC để kiểm tra?

Thông thường **không cần**. Dùng một workload giữ các mảng lớn trong heap rất nhỏ có thể làm GC tăng, nhưng kết quả phụ thuộc:
- `-Xmx`, heap thực, container quota và phiên bản JDK;
- Tốc độ tạo object, tỷ lệ object còn sống;
- Kích thước region, humongous threshold;
- CPU và chính sách G1;
- Những thay đổi tối ưu giữa các phiên bản.

Thậm chí thử nghiệm có thể kết thúc bằng `OutOfMemoryError`, container bị kill hoặc pause quá dài.

Nếu có ứng dụng test độc lập, bạn có thể bật log dưới một heap budget thử nghiệm:

~~~bash
java -XX:+UseG1GC -Xmx256m -Xlog:gc* -jar test-app.jar
~~~

Lệnh này **không tự tạo Full GC**; nó chọn G1, đặt giới hạn heap của bài test và bật log. Không dùng `256m` như khuyến nghị production.

Đặc biệt, **`System.gc()` chỉ là một lời yêu cầu** và các JVM flags có thể điều khiển cách xử lý; không dùng việc gọi này để tuyên bố rằng đã benchmark đúng đường fallback Full GC vì allocation failure.

## 14. Quy trình điều tra khi nhìn thấy `Pause Full`

### Bước 1 — Xác nhận event và JVM

Xác nhận process đang dùng G1, thông tin JDK build/vendor, heap settings và Unified GC Logging. Không suy từ log của một process khác.

### Bước 2 — Đọc GC cause

Xác định có:
- `Allocation Failure` hoặc diễn giải Full compaction;
- `Evacuation Failure` trước đó;
- `G1 Humongous Allocation`;
- `System.gc()` hoặc explicit request;
- periodic GC configuration.

Đừng dùng nhãn **`G1 Compaction Pause`** một mình làm phân tích nguyên nhân: nó nói **loại pause**, không nhất thiết lý do phải dùng fallback.

### Bước 3 — Đọc heap occupied trước/sau

Một Full GC ước lượng dọn ít bộ nhớ trong khi heap sau Full vẫn gần đầy là tín hiệu **live set cao**. Cần xem nhiều lượt, không kết luận leak chỉ từ một event.

### Bước 4 — Kiểm tra old/humongous

Kiểm tra old regions, humongous regions và loại object lớn; xem có **fragmentation** hoặc tỷ lệ retention cao.

### Bước 5 — Xem tiến độ concurrent marking

Đối chiếu thời điểm marking bắt đầu/kết thúc với tốc độ cấp phát. Nếu bắt đầu muộn hoặc tải tăng đột ngột, G1 có thể không thu hồi kịp.

### Bước 6 — Tìm root cause ở ứng dụng

Kiểm tra cache không giới hạn, queue backlog, batch size, object lifetime, heap dump, retained references và profiler. Tuning GC không thể thu hồi object vẫn còn được ứng dụng giữ hợp lệ.

### Bước 7 — Chọn biện pháp đúng nguyên nhân

| Phát hiện | Hướng xử lý |
| --- | --- |
| Live set hợp lệ lớn, heap budget thiếu | Cân đối RAM/container và tăng heap nếu khả thi |
| Object retention/leak | Sửa cache/queue/references, giảm thời gian sống |
| Marking không theo kịp | Giảm promotion/allocations; đánh giá reserve/IHOP theo log |
| Nhiều humongous objects | Giảm allocation khối lớn, xem region size và workload |
| Explicit `System.gc()` | Tìm caller, cân nhắc chính sách explicit GC |
| Native pinning | Điều tra JNI pinning và các GC events có liên quan |
| Không có `Pause Full` | Không chẩn đoán sai thành Full GC |

### Bước 8 — Đo lại

Dùng cùng workload, cùng runtime, cùng heap budget khi so sánh, báo **Full GC count, pause p95/p99, throughput và memory**. Thay **một nhóm biến tại một thời điểm** để biết điều gì đem lại cải thiện.

## 15. Sai lầm thường gặp

**Sai 1 — “G1 luôn Full GC nếu heap hơn 80%.”**  
Không có luật phổ quát này. Full GC phụ thuộc tiến độ dọn bộ nhớ, allocation pressure, free regions, explicit requests và nhiều điều kiện.

**Sai 2 — “Young GC có STW nên chắc là Full GC.”**  
Sai: Young/mixed GC có pause nhưng không thu gom toàn heap.

**Sai 3 — “Có `To-space exhausted` là lập tức Full GC.”**  
Sai: đó là cảnh báo evacuation failure, G1 có thể phục hồi.

**Sai 4 — “`G1 Humongous Allocation` chứng minh Full GC.”**  
Sai: đó có thể là nguyên nhân của một `Pause Young (Concurrent Start)`.

**Sai 5 — “Full GC song song từ Java 10 tức application vẫn chạy.”**  
Sai: nhiều GC workers cùng làm nhưng ứng dụng **STW**.

**Sai 6 — “`MaxGCPauseMillis=200` bảo đảm Full GC dưới 200 ms.”**  
Sai: pause target của G1 là mục tiêu mềm, Full GC có thể dài hơn nhiều.

**Sai 7 — “Cứ thấy Full GC thì tăng `ParallelGCThreads`.”**  
Sai: thread count không giải quyết heap pressure/retention, và có thể tạo overhead.

**Sai 8 — “Sau Full GC còn nhiều heap occupied nghĩa chắc chắn leak.”**  
Chưa đủ: live set lớn hợp lệ cũng có thể gây hiện tượng này.

**Sai 9 — “`System.gc()` luôn ném ra Full GC.”**  
Sai: explicit request phụ thuộc JVM/cờ và không đảm bảo một kiểu GC duy nhất.

**Sai 10 — “`Evacuation Failure: Pinned` đồng nghĩa thiếu destination memory.”**  
Sai: pinning native/JNI là một nguyên nhân khác.

**Sai 11 — “Một dòng log đủ kết luận root cause.”**  
Sai: phải xem chuỗi sự kiện, GC ID, heap/region states và workload.

**Sai 12 — “Tăng `-Xmx` là giải pháp bền vững cho mọi Full GC.”**  
Sai: heap lớn hơn không sửa cache vô hạn hoặc lỗi giữ object.

**Sai 13 — “Full GC luôn được sinh ra do allocation pressure.”**  
Sai: yêu cầu explicit hoặc cấu hình periodic có thể gây Full GC.

**Sai 14 — “Đổi vài GC flags cùng lúc rồi so hiệu năng là đủ.”**  
Sai: không cô lập được nguyên nhân; cần đo có đối chứng.

## 16. Tự kiểm tra kiến thức

**Câu 1. Full GC của G1 được gọi là fallback vì sao?**  
Vì các cơ chế incremental/concurrent bình thường đôi khi không thu hồi được đủ không gian để tiếp tục cấp phát.

**Câu 2. Evacuation failure xảy ra khi nào?**  
Khi G1 không thể di chuyển một số object cần di chuyển, phổ biến do **thiếu destination space**, và trên JDK mới còn có thể liên quan **pinning**.

**Câu 3. Evacuation failure có nhất thiết kích hoạt Full GC ngay không?**  
Không. G1 có thể xử lý trong các collection kế tiếp; phải xác nhận bằng dòng `Pause Full`.

**Câu 4. Vì sao concurrent marking chậm có thể dẫn đến Full GC?**  
Old occupancy tăng nhanh hơn tốc độ phân tích/thu hồi, free regions cạn trước khi mixed collections dọn được đủ.

**Câu 5. Humongous object liên quan gì đến fragmentation?**  
Nó có thể cần nhiều region liên tiếp, trong khi free regions bị phân tán khiến không đủ một dải liên tục.

**Câu 6. Dòng `Pause Young (Concurrent Start) (G1 Humongous Allocation)` là Full GC không?**  
Không. Đó là young pause gắn với humongous allocation.

**Câu 7. Full GC G1 được song song hóa từ phiên bản nào?**  
Java 10, **JEP 307**.

**Câu 8. Full GC song song có còn STW không?**  
Có. “Parallel” nói về GC workers, không có nghĩa application threads chạy concurrent.

**Câu 9. Cờ `-XX:MaxGCPauseMillis` có giới hạn cứng Full GC không?**  
Không. Đây là mục tiêu mềm của G1.

**Câu 10. Full GC do `System.gc()` có chứng minh heap thiếu không?**  
Không. Cần xác định explicit cause; không suy ra allocation pressure.

**Câu 11. Nếu heap sau mỗi Full GC vẫn gần đầy, nên làm gì?**  
Kiểm tra live set, retained references, cache, queue, heap dump và giới hạn heap.

**Câu 12. Tại sao không nên dùng một chuỗi log duy nhất để đếm Full GC trên mọi JDK?**  
Format GC log và cách diễn tả evacuation failure/full compaction có thể thay đổi. Tìm đúng `Pause Full`, GC ID và ngữ cảnh.

**Câu 13. Có cần dùng `System.gc()` để tái hiện lỗi Full GC vì thiếu bộ nhớ không?**  
Không. Explicit GC có thể đi qua đường xử lý khác; dùng workload đại diện và logging để điều tra.

**Câu 14. Nếu tăng heap giúp giảm Full GC, có thể kết luận vấn đề đã sửa triệt để không?**  
Chưa chắc. Cần đánh giá leak, cache, live set và xu hướng sử dụng bộ nhớ qua thời gian.

**Câu 15. Vì sao một Full GC trong G1 là tín hiệu đáng xem xét dù JEP 307 đã song song hóa?**  
Vì Full GC vẫn STW, có thể gây pause dài và thường phản ánh áp lực cấp phát hoặc yêu cầu thu gom ngoài luồng bình thường.

## 17. Tóm tắt

- **G1 bình thường** cố gắng dọn heap bằng young/mixed collections và concurrent marking, không cần Full GC thường xuyên.
- **Full GC có thể cần thiết** khi thiếu vùng đích khi evacuation, old occupancy tăng nhanh, concurrent marking chưa thu hồi kịp, humongous fragmentation hoặc live set quá lớn.
- **Không đồng nhất tín hiệu với kết luận:** `To-space exhausted` và `Evacuation Failure` là cảnh báo; `G1 Humongous Allocation` thường liên quan young GC. Chỉ `Pause Full` xác nhận Full GC trong log.
- **Không phải mọi Full GC do thiếu heap:** `System.gc()`, công cụ quản trị hoặc các cấu hình đặc biệt có thể là nguyên nhân.
- **Java 10 / JEP 307** giúp G1 Full GC xử lý song song, nhưng vẫn **stop-the-world** và không được đảm bảo dưới pause target.
- Khi Full GC lặp lại và reclaim ít bộ nhớ, phải điều tra **live set, cache, queue, heap dump và object retention**.
- Dùng **Unified Logging `-Xlog`**, theo dõi GC ID, occupancy, old/humongous regions, concurrent cycles và workload trước khi điều chỉnh JVM flags.
- **Chỉ tuning có bằng chứng**, và đo lại trên cùng điều kiện sau mỗi thay đổi.

**Tài liệu chính thức còn áp dụng:**
- [Oracle Java SE 25 — G1 Garbage Collector Tuning: Full GC và Humongous Object Fragmentation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java SE 24 — G1 Garbage Collector: marking, evacuation failure, humongous objects](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html).
- [Oracle Java SE 17 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java SE 25 — `java` launcher và G1 JVM options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).
- [OpenJDK — JEP 307: Parallel Full GC for G1](https://openjdk.org/jeps/307).
- [OpenJDK — JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423).
