# Nguyên lý GC, pause time, throughput và allocation rate trong Java 27

Trong ứng dụng Java, chúng ta không cần tự giải phóng bộ nhớ của từng object như khi sử dụng một số ngôn ngữ quản lý bộ nhớ thủ công. **Garbage Collector (GC)** trong JVM xác định object nào không còn cần thiết và thu hồi vùng nhớ để cấp phát tiếp. Đổi lại, chương trình phải chấp nhận chi phí tìm đối tượng còn sống, di chuyển hoặc thu hồi object, các khoảng **tạm dừng** và hoạt động GC **đồng thời** với application.

Với Java 27, ba chỉ số thường quyết định hiệu năng thực tế là:

- **Pause time**: các khoảng thời gian JVM tạm dừng thực thi ứng dụng để thực hiện phần việc GC cần *stop-the-world*.
- **Throughput**: mức độ ứng dụng có thể tiến triển hữu ích; trong tài liệu tuning GC, thường được diễn đạt bằng tỷ lệ thời gian ứng dụng **không bị dừng bởi GC**.
- **Allocation rate**: tốc độ ứng dụng cấp phát object mới, thường đo bằng MiB/s hoặc byte/giây; đây là nguồn gây áp lực thu gom, **không phải** số byte heap tăng lên.

Bài thuộc chương **JVM, bộ nhớ và thu gom rác**, dùng các khái niệm và công cụ còn áp dụng ở **Java 27**, bao gồm **G1** (GC mặc định trên HotSpot ở mọi môi trường kể từ JDK 27), **Parallel GC**, **Serial GC**, **ZGC** hiện hành, unified logging `-Xlog`, Java Flight Recorder (JFR) và các API quản lý bộ nhớ. Không sử dụng cờ GC đã lỗi thời hay giả định về các collector đã bị loại bỏ.

> **Mục tiêu học tập:** sau bài này, bạn có thể phân biệt “heap đầy” với “allocation rate cao”, hiểu GC pause khác request latency, tự đọc thông tin GC và chọn hướng cải thiện phù hợp trước khi thay đổi cấu hình JVM.

## 1. GC làm gì và không làm gì?

GC quản lý vòng đời **bộ nhớ Java được cấp phát cho object**. Trong HotSpot, những công việc cốt lõi gồm:

1. Cấp vùng nhớ heap để ứng dụng tạo object khi cần.
2. Xác định những object còn **reachable** (có thể truy cập từ các gốc tham chiếu).
3. Thu hồi bộ nhớ của các object không còn reachable, tùy collector và chu kỳ GC.
4. Trong một số collector, di chuyển (*evacuate*) object còn sống để gom vùng trống liền nhau và giảm phân mảnh.
5. Điều chỉnh vùng heap committed và tổ chức các thế hệ/vùng nhớ tùy chính sách, tải và collector.

Không đồng nghĩa với:

- **Gọi `close()` cho mọi tài nguyên bên ngoài.** Socket, file, database connection, direct/native resource phải được đóng theo hợp đồng API, ví dụ `try-with-resources`.
- **Bảo đảm object bị thu hồi ngay khi biến ra khỏi scope.** Thời điểm GC do JVM quyết định.
- **Loại bỏ mọi memory leak.** Nếu object vẫn reachable qua cache, listener hay collection không giới hạn, GC không thể biết nghiệp vụ đã hết cần.
- **Bảo đảm không còn `OutOfMemoryError`.** Heap, metaspace, direct memory, native memory hoặc giới hạn tiến trình/container vẫn có thể bị cạn.
- **Bảo đảm request không bao giờ bị dừng.** Một số giai đoạn thu gom cần dừng ứng dụng.

### 1.1. Reachability thay vì “đếm tham chiếu”

Ý tưởng đơn giản:

```text
GC roots
  │
  ├── thread stacks / tham chiếu còn sống
  ├── các tham chiếu static/class loader đang hoạt động
  ├── JNI handles và một số roots do JVM quản lý
  ▼
Object A ───> Object B ───> Object C
  │
  └───────> Object D

Object X ───> Object Y       (không có đường đi từ GC roots)
   ▲             │
   └─────────────┘
```

Các object `A/B/C/D` được reachable từ roots, nên chưa thể thu hồi nếu các tham chiếu đó vẫn có hiệu lực. `X/Y` dù tham chiếu **vòng** lẫn nhau vẫn có thể được thu hồi vì không còn đường đi từ roots.

Sơ đồ chỉ minh họa nguyên lý; tập GC roots thực tế phụ thuộc vào JVM, trạng thái thực thi và các loại reference. **Không** kết luận “biến trong method đã ra khỏi scope là JVM bắt buộc thu hồi object ngay”; JIT và bộ thu gom quyết định thời điểm cấp phát/thu hồi.

### 1.2. Object tồn tại lâu không tự động là leak

```java
// Ví dụ: giữ 1000 kết quả trong cache có giới hạn.
java.util.Map<String, String> cache = new java.util.LinkedHashMap<>();
```

Nếu cache được quản lý đúng nhu cầu, những object được giữ là **live set hợp lệ**. Ngược lại, một `static List` giữ reference tới toàn bộ request đã xử lý có thể làm live set tăng mãi, gây **logical memory leak** dù không có bất kỳ “malloc không free” nào.

**Câu hỏi khi chẩn đoán:** object tăng vì ứng dụng tạo nhiều object **ngắn hạn**, hay vì ứng dụng đang **giữ lại ngày càng nhiều** object?

## 2. Heap và bộ nhớ tiến trình JVM khác nhau

GC chủ yếu xử lý **Java heap**; nhưng bộ nhớ hệ điều hành dùng bởi một Java process còn nhiều thành phần khác.

```text
Java process / container memory
┌────────────────────────────────────────────┐
│ Java heap (-Xms, -Xmx)                     │
│  ├─ young generation / vùng object mới      │
│  └─ old generation / vùng object lâu sống   │
├────────────────────────────────────────────┤
│ Metaspace / class metadata                 │
│ Thread stacks, native JVM structures       │
│ JIT code cache                             │
│ Direct ByteBuffer / native allocations     │
│ Memory-mapped files, native libraries      │
│ Các vùng bộ nhớ khác tùy JVM/OS             │
└────────────────────────────────────────────┘
```

| Chỉ số | Ý nghĩa | Đừng nhầm với |
| --- | --- | --- |
| **Heap used** | Byte heap đang dùng tại một thời điểm | Tổng byte object từng được cấp phát |
| **Heap committed** | Dung lượng heap JVM đã cam kết sử dụng theo cách báo của VM | Lượng object đang sống |
| **Heap max** | Giới hạn Java heap theo cấu hình/ergonomics `-Xmx` | Tổng RAM container hay RSS |
| **Live set** | Các object còn reachable, thường ước lượng sau một chu kỳ thu gom thích hợp | Tất cả object tạm thời từng tồn tại |
| **Process RSS** | Trang bộ nhớ vật lý đang hiện diện cho tiến trình theo hệ điều hành | Chỉ Java heap |
| **Native/direct usage** | Bộ nhớ ở ngoài Java object heap, ví dụ direct buffers | Dữ liệu GC có thể tự thu hồi đúng lúc nghiệp vụ cần |

Nếu monitoring hiển thị heap chỉ chiếm 1 GiB nhưng process RSS là 2 GiB, **không** thể kết luận “GC bị rò rỉ 1 GiB”. Cần kiểm tra native memory, thread stacks, code cache, direct buffers và cả cách hệ điều hành tính RSS.

`-Xms` là kích thước heap khởi tạo/tối thiểu theo cấu hình, `-Xmx` là heap tối đa. Tăng `-Xmx` không tăng trực tiếp bộ nhớ cho mọi vùng native; nhưng nếu container có giới hạn RAM, heap lớn hơn có thể **thu hẹp headroom** cho bộ nhớ khác.

## 3. Vì sao JVM phân thế hệ? Young, old và vòng đời object

Các ứng dụng có rất nhiều object **sống ngắn**: iterator, DTO, đối tượng trung gian khi parse JSON, phần tử stream và dữ liệu tạm trong request. Đây là cơ sở của *weak generational hypothesis*: trong nhiều workload, phần lớn object chết sớm.

Collector theo thế hệ thường:

1. Cấp phát object mới tại vùng **young** khi điều kiện cho phép.
2. Thu gom young thường xuyên để giải phóng object không còn reachable.
3. Giữ lại các object sống sót; chúng có thể được sao chép hoặc chuyển dần sang **old** theo chính sách của collector.
4. Quản lý old generation với những giai đoạn thu gom thích hợp.

```text
Allocation requests
        │
        ▼
Young / Eden ── young GC ──► survivors
   │         (reclaim dead)       │
   │                               ▼
   └─ object chết sớm          old generation
                               (longer-lived data)
                                     │
                                old/mixed/concurrent work
                                     │
                              reclaim when unreachable
```

Đây là sơ đồ **khái niệm**, không phải bố trí vùng nhớ cố định của mọi collector. G1 sử dụng các **heap regions** có vai trò young/old theo thời gian; ZGC có tổ chức và thuật toán concurrent riêng. Không tự áp sơ đồ Eden/Survivor/Old theo các địa chỉ liền kề cho mọi JVM.

### 3.1. Young collection, mixed collection, full collection

- **Young GC**: tập trung vào vùng chứa object mới/young; thường có thể giải phóng nhiều object chết sớm.
- **Mixed GC**: trong ngữ cảnh **G1**, một đợt có thể thu gom cả các region young và những region old được chọn.
- **Concurrent work**: một phần công việc GC diễn ra cùng lúc application tiếp tục chạy, sử dụng CPU/băng thông bộ nhớ.
- **Full GC**: thường là hoạt động thu gom toàn heap hay một chu kỳ dự phòng nặng, có thể gây pause rất dài tùy collector và tình trạng bộ nhớ.

Không đồng nhất mọi dòng log chứa từ “GC” thành “Full GC”; cũng không suy ra “Full GC” ở tất cả collector dùng cùng một thuật toán. Khi chẩn đoán phải đọc **tên collector, cause, phase, heap before/after và thời gian** trong log tương ứng.

### 3.2. Thread-local allocation blocks (TLAB)

HotSpot có thể cấp phát nhanh nhiều object trong **TLAB** của thread, giảm cạnh tranh trên heap khi tạo object. Điều này có nghĩa **tạo một object nhỏ không nhất thiết phải gọi một allocator toàn cục đắt tiền**.

Tuy nhiên:

- JIT có thể dùng **escape analysis** và **scalar replacement** để loại bỏ một số cấp phát thực tế khi object không cần tồn tại.
- Một số object được cấp phát theo cơ chế khác tùy size, collector và cấu hình.
- Allocation profile phản ánh hành vi **runtime thực tế** dưới tối ưu JIT; đừng lấy số lần viết `new` trong code nguồn làm số byte cấp phát thực tế một cách cơ học.

## 4. Stop-the-world pause và công việc GC chạy đồng thời

**Stop-the-world (STW)** là một khoảng thời gian mà JVM tạm dừng những application threads liên quan để thực hiện công việc cần trạng thái nhất quán. Không phải toàn bộ thời gian của một chu kỳ GC đều là STW.

```text
Thời gian ──────────────────────────────────────────►

App thread:   RUN ───────┐ PAUSE ┌── RUN ────────┐ PAUSE ┌─ RUN
                         └───────┘               └───────┘
GC threads:   [concurrent work]   [concurrent work]
                         [STW]                 [STW]
```

- **Parallel GC** có thể sử dụng nhiều worker GC **trong khi application bị tạm dừng**.
- **Concurrent GC** thực hiện một số giai đoạn cùng lúc với application, giảm pause nhưng tranh chấp CPU/memory bandwidth với logic nghiệp vụ.
- Một collector có thể vừa dùng parallel trong pause vừa làm concurrent ngoài pause; đây là hai đặc tính **khác nhau**.
- Không có nghĩa “concurrent collector thì tuyệt đối zero pause”.

### 4.1. Pause time đo điều gì?

**GC pause duration** là thời gian của một sự kiện GC tạm dừng application; đơn vị thường là ms hoặc µs. Ví dụ log minh họa (không phải đầu ra cố định của JDK):

```text
[1.234s][info][gc] GC(3) Pause Young (Normal) (G1 Evacuation Pause) 80M->28M(256M) 9.2ms
```

Cách đọc:

- `GC(3)`: định danh sự kiện trong log.
- `Pause Young`: loại công việc GC ở pause này.
- `80M->28M(256M)`: heap được báo trước/sau đợt thu gom và capacity trong dòng log này; **không phải** số byte được cấp phát từ lần GC trước.
- `9.2ms`: thời gian của GC pause tương ứng.

Không nhầm **9,2 ms pause** với **9,2 ms tổng thời gian xử lý một HTTP request**. Request có thể đang chạy trên một hoặc nhiều thread, bị trễ do queue/lock/I/O/CPU và cả các safepoint không liên quan trực tiếp đến GC.

### 4.2. Mean, max, p95 và p99 pause

Giả sử trong một khoảng quan sát có các GC pause:

```text
5 ms, 6 ms, 7 ms, 8 ms, 60 ms
```

- **Trung bình** = `(5+6+7+8+60)/5 = 17,2 ms`.
- **Max** = `60 ms`.
- Những phân vị cao như **p95/p99** của pause cho thấy phần đuôi phân phối, nhưng với mẫu rất ít chúng không ổn định; cần nêu rõ cách tính percentile và cửa sổ thời gian.

Nếu hệ thống có SLO HTTP p99 200 ms, cần theo dõi **p99 HTTP latency** song song với **GC pause distribution**; không được suy diễn “GC p99 dưới 100 ms thì HTTP p99 chắc dưới 200 ms”.

### 4.3. MaxGCPauseMillis là mục tiêu mềm, không phải SLA

Với G1 có thể yêu cầu:

```text
-XX:MaxGCPauseMillis=100
```

Đây là **gợi ý/mục tiêu** để G1 điều chỉnh lượng công việc trong từng pause, **không bảo đảm** không có pause nào dài hơn 100 ms. Ngay cả khi GC đạt mục tiêu, ứng dụng vẫn có thể có độ trễ cao do disk/network/lock/scheduling.

Trong Java 27, G1 mặc định có mục tiêu pause khoảng **200 ms** theo tài liệu HotSpot, nhưng không nên lấy giá trị mặc định làm SLO của tất cả ứng dụng. Kiểm tra cấu hình thực qua log/JVM flags và đo trên workload cụ thể.

## 5. Throughput: phân biệt hiệu quả GC với thông lượng nghiệp vụ

Có **hai** khái niệm cùng gọi là throughput mà nên tách bạch.

### 5.1. GC throughput — tỷ lệ thời gian application không bị dừng

Trong phép đo đơn giản chỉ tính các đoạn STW:

```text
GC throughput ≈ app-running time / (app-running time + GC pause time) × 100%
```

Ví dụ trong cửa sổ 60 giây, tổng thời gian STW GC là 3 giây:

```text
Tổng thời gian     = 60 s
Tổng GC pause      =  3 s
Thời gian còn lại  = 57 s
Throughput xấp xỉ  = 57 / 60 × 100% = 95%
```

Đây là cách diễn giải **GC throughput theo wall-clock pause time** phục vụ việc học, không phải một phép đo toàn diện của chi phí GC. Với concurrent collector:

- GC vẫn **dùng CPU** khi application đang chạy.
- Các barrier, ghi nhớ tham chiếu và chuyển object có thể có overhead.
- Phần thời gian concurrent GC **không xuất hiện** như STW pause trong phép chia trên.
- Vì vậy, `99,9%` “không pause” **không đồng nghĩa** chỉ `0,1%` CPU/tài nguyên được dùng cho GC.

### 5.2. Application throughput — công việc hữu ích/giây

Tùy hệ thống, một chỉ số nghiệp vụ có thể là:

- Request/s được xử lý thành công.
- Giao dịch/s đúng dữ liệu.
- Message/s tiêu thụ từ queue.
- MiB/s dữ liệu phân tích.
- Batch jobs hoàn tất/giờ.

Nếu đổi GC khiến **request/s giảm 15%** nhưng STW pause ngắn hơn, lựa chọn có thể tốt cho hệ thống ưu tiên **latency p99**, nhưng chưa chắc tốt cho batch processing ưu tiên số đơn vị công việc xử lý mỗi giây.

**Định nghĩa điều kiện đánh giá:** ghi rõ workload, CPU quota, RAM/heap, concurrency, mức tải và SLO trước khi nói “GC A tốt hơn GC B”.

### 5.3. Trade-off phổ biến

| Mong muốn | Chi phí/đánh đổi thường gặp |
| --- | --- |
| Pause ngắn hơn | Có thể nhiều lần pause hơn, thêm concurrent CPU/metadata overhead |
| Throughput cao hơn | Có thể cho phép pause dài hơn hoặc GC ít thường xuyên hơn |
| Heap footprint nhỏ hơn | Ít headroom cho allocation spike, tăng tần suất thu gom |
| Heap lớn hơn | Giảm áp lực trong một số workload nhưng tăng RAM và có thể làm một số công việc GC đắt hơn |
| Độ trễ đuôi thấp hơn | Có thể cần GC concurrent và dự phòng CPU/RAM |
| Giảm allocation rate | Có thể giảm GC pressure nhưng phải cân bằng với độ đơn giản/chi phí CPU của việc tái sử dụng object |

Không có một cấu hình tối ưu toàn cục. Đổi một tham số có thể cải thiện một chỉ số nhưng làm xấu chỉ số khác.

## 6. Allocation rate: tốc độ cấp phát không phải heap used

**Allocation rate** mô tả số byte **được cấp phát mới** trong một đơn vị thời gian:

```text
Allocation rate ≈ allocated bytes trong cửa sổ đo / elapsed seconds

Nếu 1.000 MiB object được cấp phát trong 5 giây:
  allocation rate = 1.000 / 5 = 200 MiB/s
```

Đây là **luồng cấp phát tích lũy**, không phải lượng heap tăng lên. Ví dụ:

```text
Cửa sổ 5 giây
  Object mới được cấp phát:       1.000 MiB
  Object chết và được thu hồi:      900 MiB (minh họa)
  Heap used tăng ròng:             100 MiB

Allocation rate: 200 MiB/s
Heap used delta: 100 MiB trong 5 giây
```

Hai con số mô tả hai hiện tượng khác nhau. Heap used có thể liên tục tăng trước GC và giảm mạnh sau GC; lấy `heapUsed(t2) - heapUsed(t1)` chia thời gian **không** cho ra allocation rate chính xác.

### 6.1. Allocation rate theo request

Nếu hệ thống cấp phát 2.000 MiB trong một khoảng có 10.000 request hoàn tất:

```text
Allocated bytes per request ≈ 2.000 MiB / 10.000 = 0,2 MiB/request
```

Chỉ số này có thể giúp so sánh hai phiên bản xử lý **cùng workload và cùng đầu vào**. Khi một endpoint đột nhiên tăng bytes/request, có thể có quá nhiều object tạm từ JSON mapping, regex, chuyển String, Stream pipeline, bản sao collection hoặc serialization.

**Hạn chế:** muốn tính chính xác, cần công cụ đo lượng cấp phát thật. **JFR allocation sampling** rất hữu ích để tìm *allocation hotspots* nhưng có thể dùng **mẫu thống kê**, không phải một phép đếm tuyệt đối tất cả object trong mọi cấu hình. Khi dùng các phép đo từ thread, phải xét thread và các hoạt động sinh object diễn ra trên thread khác.

### 6.2. Allocation rate, live set và headroom

Ba đại lượng khác nhau:

| Đại lượng | Câu hỏi |
| --- | --- |
| **Allocation rate** | Ứng dụng tạo mới bao nhiêu byte mỗi giây? |
| **Live set** | Sau một chu kỳ thu gom phù hợp, còn bao nhiêu dữ liệu reachable cần giữ? |
| **Headroom** | Heap còn đủ chỗ cho các allocations khi GC chưa kịp thu hồi không? |

Giả sử service giữ lâu dài `1,5 GiB` cache/hồ sơ, có thể cấp phát thêm `200 MiB/s` DTO tạm, và GC concurrent cần thời gian để hoàn thành chu kỳ. Nếu `-Xmx` sát live set, ứng dụng có thể thiếu khoảng trống để tiếp tục cấp phát trong khi GC đang làm việc, dẫn tới **allocation stall**, thu gom khẩn cấp hoặc `OutOfMemoryError`.

Phép nhân `allocationRate × thời gian một chu kỳ GC` chỉ có thể dùng làm **ước lượng ban đầu về áp lực**, **không phải công thức sizing heap chính xác**. Tốc độ thu hồi, promotion, fragmentation, các đợt allocation spike, copy overhead và cơ chế collector đều ảnh hưởng nhu cầu headroom.

### 6.3. High allocation rate không tự động là memory leak

- Nếu nhiều object **chết nhanh**, heap used sau thu gom vẫn ổn định, GC có thể thường xuyên nhưng không có leak.
- Nếu **live set** tăng dần qua các lần thu gom thích hợp với cùng tải, cần xem object retention, cache không giới hạn, listener hoặc reference giữ ngoài ý muốn.
- Nếu Java heap ổn định nhưng **RSS tăng**, nghiêng về phân tích native/direct memory trước khi kết luận heap leak.
- Nếu allocation rate ổn định nhưng **pause tăng**, có thể live set hoặc thời gian xử lý live objects đã tăng; cũng có thể do CPU bị cạnh tranh.

Đừng sửa mọi “GC nhiều” bằng cách tăng heap. Hãy tìm xem vấn đề là **allocation churn**, **retention** hay **tài nguyên ngoài heap**.

## 7. Chọn collector hiện hành trong Java 27

Theo tài liệu Oracle HotSpot GC Tuning Guide 27, những lựa chọn chính gồm **Serial, Parallel, G1, ZGC**.

| Collector | Kích hoạt | Thế mạnh | Đánh đổi/điều kiện |
| --- | --- | --- | --- |
| **G1** | Mặc định, hoặc `-XX:+UseG1GC` | Cân bằng pause và throughput, tự điều chỉnh theo tải | Không cam kết hard pause bound; có concurrent overhead |
| **Parallel GC** | `-XX:+UseParallelGC` | Throughput cho workload chịu được STW dài hơn | Pause có thể dài, nhất là với lượng live data lớn |
| **Serial GC** | `-XX:+UseSerialGC` | Đơn giản, ít overhead đồng bộ GC; đôi khi hợp môi trường rất nhỏ | GC chủ yếu một thread, không tận dụng nhiều CPU cho thu gom |
| **ZGC** | `-XX:+UseZGC` | Pause thấp, các phần việc GC đắt được xử lý concurrent | Cần CPU/headroom, có thể đổi throughput và footprint lấy latency |

### 7.1. Java 27 thay đổi GC mặc định

Từ **JDK 27**, HotSpot chọn **G1 theo mặc định trong tất cả môi trường**, kể cả khi chỉ có một CPU hoặc ít RAM. Trước đó có cấu hình tài nguyên hạn chế được chọn Serial tự động; do vậy các hướng dẫn cũ mô tả “JVM nhỏ sẽ mặc định Serial GC” **không còn đúng** cho HotSpot JDK 27.

Điều này **không xóa Serial GC**. Khi có bằng chứng benchmark ứng dụng nhỏ dùng Serial phù hợp hơn, vẫn có thể chọn `-XX:+UseSerialGC` rõ ràng. Không thay đổi GC chỉ vì một lời khuyên tối ưu hóa không dựa trên profile.

### 7.2. G1: chọn tốt để bắt đầu

G1 chia heap thành nhiều regions, thường ưu tiên thu hồi các region có hiệu quả tốt, kết hợp young-only và mixed collections, cùng các công việc marking concurrent. Cấu hình ban đầu được Oracle khuyến nghị cho đa số workload:

```text
# Không đặt GC flag: HotSpot Java 27 tự chọn G1
java -Xmx1g -Xlog:gc MyApp
```

`MyApp` là tên lớp hoặc entry point giả định của ứng dụng. Giới hạn `-Xmx1g` chỉ minh họa, **không phải khuyến nghị chung**.

Nếu cần mục tiêu pause thấp hơn, thử một cấu hình riêng:

```text
java -XX:+UseG1GC -Xmx1g -XX:MaxGCPauseMillis=100 -Xlog:gc MyApp
```

**Lưu ý:** `100` là **mục tiêu mềm**, không phải mỗi request hoặc mỗi pause phải nhanh hơn 100 ms. G1 điều chỉnh kích thước young và lựa chọn collection set; cố định young size bằng `-Xmn`/`-XX:NewRatio` có thể làm giảm khả năng tự điều chỉnh pause của G1. Bắt đầu từ defaults rồi mới thử các knobs khi log và dữ liệu xác nhận nhu cầu.

### 7.3. ZGC: latency thấp, nhưng vẫn cần headroom

Trong Java 27, **ZGC là collector theo thế hệ** (*generational*) và đã chỉ còn mô hình này kể từ JDK 24. Tùy chọn `-XX:+ZGenerational` của những phiên bản chuyển tiếp đã **bị loại bỏ**, nên không dùng trong hướng dẫn Java 27.

```text
java -XX:+UseZGC -Xmx2g -Xlog:gc MyApp
```

ZGC thực hiện phần lớn công việc nặng concurrent để giảm thời gian tạm dừng. Nó phù hợp khi latency đuôi là ưu tiên mạnh, nhưng:

- Vẫn cần heap đủ lớn cho live set **và** allocation diễn ra khi GC chạy.
- Cần CPU cho concurrent GC; under-provision CPU có thể gây allocation stalls.
- Không đồng nghĩa mọi thời gian chờ của ứng dụng đều dưới một mili-giây.
- `-Xmx` là knob quan trọng; cần thử trên tải thực thay vì chỉ nhìn kích thước heap.

### 7.4. Không sử dụng công thức tuning cũ một cách máy móc

**Không khuyến khích** trong bài Java 27:

- Áp dụng CMS, PermGen hoặc các flag riêng của những GC đã bị loại bỏ.
- Dùng `-XX:+ZGenerational` như thể Java 27 vẫn cần bật ZGC thế hệ.
- Dùng `-XX:+PrintGCDetails` hay `-XX:+PrintGC` như cách chính để log; hiện tại dùng **unified logging `-Xlog`**.
- Dùng `System.gc()` lặp liên tục để “giữ heap sạch”. Đây không phải một giải pháp tự động về pause/throughput; JVM có thể xử lý lời gọi theo cấu hình và có thể làm tăng overhead.

## 8. Đọc GC log bằng unified logging

Java 27 dùng **JVM unified logging**. Bắt đầu với một cấu hình nhẹ:

```text
java -Xmx512m -Xlog:gc MyApp
```

Nếu cần phân tích chi tiết hơn, có thể log cả GC và safepoint, thêm thời điểm và xoay vòng file:

```text
java -Xmx512m -Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=10M MyApp
```

Các cờ trên là ví dụ chạy ứng dụng Java có class/main entry point `MyApp`, không phải lệnh đã thực thi trên máy người học.

- `gc*` chọn các tag set có `gc` để thấy nhiều chi tiết hơn.
- `safepoint` giúp phân biệt một số lần dừng JVM không thuần GC.
- `time,uptime,level,tags` là decorations để liên kết sự kiện với thời gian và loại.
- `filecount`/`filesize` giới hạn số log quay vòng, tránh ghi vô hạn khi bật logging chi tiết.

**Quan trọng:** mức `info` cho `gc*` có thể tạo nhiều log hơn `-Xlog:gc`. Trong production, đo chi phí và kích thước log; tăng sang `debug`/`trace` chỉ trong cửa sổ điều tra có kiểm soát.

### 8.1. Những trường nên trích từ log

| Trường | Ý nghĩa | Câu hỏi chẩn đoán |
| --- | --- | --- |
| GC timestamp/uptime | Sự kiện xảy ra khi nào | Có trùng đợt tải cao hay request p99 spike? |
| Collector/phase | Young, mixed, concurrent, Full | Có đang xử lý young liên tục hay gặp Full GC? |
| GC cause | Lý do khởi tạo thu gom | Normal allocation, allocation failure, explicit GC? |
| Heap before/after/capacity | Dung lượng tại hai thời điểm của sự kiện | Live set sau thu gom có tăng dần không? |
| Pause duration | Độ dài STW được log | Max/p95/p99 trên cửa sổ là bao nhiêu? |
| GC frequency | Số sự kiện theo thời gian | GC có thường xuyên do allocation rate tăng không? |
| Concurrent CPU/activity | Công việc ngoài STW, tùy collector/log | Có chiếm CPU làm giảm app throughput không? |
| Safepoint time | Thời gian dừng JVM do safepoint | Có nhầm các pause khác thành GC pause không? |

**Không suy luận sai từ before/after:** giá trị `80M->28M` là ảnh bộ nhớ trong một đợt thu gom, không phải tổng cấp phát giữa hai sự kiện. Để đo allocation rate, ưu tiên công cụ allocation-aware như JFR hoặc thread allocation counters phù hợp.

### 8.2. G1 Full GC đáng chú ý

Với G1, các dòng `Pause Full (G1 Compaction Pause)` là tín hiệu phải điều tra. Các nguyên nhân có thể gồm:

- Không có đủ vùng trống để evacuation/tiếp tục allocation.
- Live set lớn so với heap capacity.
- Allocation và promotion tăng quá nhanh so với tốc độ concurrent marking/reclamation.
- Large/humongous objects và fragmentation.
- Thiết lập heap/young/CPU khiến collector không hoàn thành kịp.

Không áp một phép sửa duy nhất như “tăng `-XX:ParallelGCThreads`” mà không xem GC phase breakdown, CPU quota và áp lực memory.

## 9. Ví dụ chạy được: tạo allocation pressure có giới hạn

Đây là ví dụ **quan sát GC**, không phải cách viết ứng dụng production. Nó cố ý tạo nhiều mảng ngắn hạn và giữ lại một phần nhỏ để minh họa allocation rate khác live set.

Lưu thành `AllocationPressureDemo.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.List;

public class AllocationPressureDemo {
    // Giữ tham chiếu mới nhất để JIT không loại bỏ toàn bộ allocations.
    private static volatile byte[] lastAllocated;

    private static void printSnapshot(String label) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

        System.out.printf(
            "%s: heap used=%.1f MiB, committed=%.1f MiB%n",
            label,
            heap.getUsed() / (1024.0 * 1024.0),
            heap.getCommitted() / (1024.0 * 1024.0)
        );

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            // -1 nghĩa là implementation không cung cấp chỉ số đó.
            System.out.printf(
                "  %s: count=%d, collectionTime=%d ms%n",
                gc.getName(),
                gc.getCollectionCount(),
                gc.getCollectionTime()
            );
        }
    }

    public static void main(String[] args) {
        final int iterations = 8_000;
        final int bytesPerArray = 16 * 1024;
        List<byte[]> retained = new ArrayList<>();

        printSnapshot("Before");

        for (int i = 0; i < iterations; i++) {
            byte[] block = new byte[bytesPerArray];
            block[0] = (byte) i;
            lastAllocated = block; // Tham chiếu volatile quan sát được

            if (i % 200 == 0) {
                retained.add(block); // Một phần nhỏ sống lâu hơn
            }
        }

        printSnapshot("After");
        System.out.println("Retained arrays = " + retained.size());
        System.out.printf(
            "Requested array payload = %.1f MiB%n",
            (iterations * (double) bytesPerArray) / (1024.0 * 1024.0)
        );
    }
}
```

Biên dịch và chạy trong **môi trường học tập có giới hạn tài nguyên**:

```text
javac AllocationPressureDemo.java
java -Xms32m -Xmx32m -Xlog:gc AllocationPressureDemo
```

Trong mã:

- `8.000 × 16 KiB = 125 MiB` là **tổng payload mảng được yêu cầu**; lượng heap cấp phát thực có thể lớn hơn vì header/alignment và có thể chịu tối ưu runtime.
- Mỗi lần lặp thay `lastAllocated` bằng mảng mới, nên đa số mảng trước đó không được chương trình giữ lâu.
- Khoảng `40` mảng được giữ trong `retained` (xấp xỉ `0,625 MiB` payload), bên cạnh mảng cuối cùng.
- Với heap `32 MiB`, GC **có khả năng** diễn ra trong khi chương trình tạo tổng số byte object lớn hơn dung lượng heap nhiều lần; số lần và thời lượng cụ thể phụ thuộc JDK, JVM, OS và tải.
- Hai giá trị `heap used` trước/sau **không** đo được tổng `125 MiB` đã cấp phát, cũng không chứng minh object còn sống lâu dài.
- Các chỉ số `GarbageCollectorMXBean` là điểm quan sát thô; chúng có thể thiếu hoặc có nghĩa khác nhau giữa collector/implementation và **không thay thế** phân tích pause p99.

**Không dùng `System.gc()` để cưỡng ép minh họa “sau thu gom sẽ còn bao nhiêu byte”**: lời gọi này là một yêu cầu tới JVM, không bảo đảm một chu kỳ GC cụ thể hay thời điểm hoàn thành theo cách mà bài học có thể dựa vào.

## 10. Đo allocation rate bằng ThreadMXBean: có giới hạn rõ

Trong HotSpot, interface mở rộng `com.sun.management.ThreadMXBean` có phương thức `getThreadAllocatedBytes(threadId)` trả số byte heap được cấp phát **xấp xỉ** bởi một **platform thread** còn sống, nếu JVM hỗ trợ và đã bật phép đo.

Đây không phải API phù hợp để theo dõi mọi **virtual thread**: tài liệu Java SE 27 quy định `getThreadAllocatedBytes(long)` trả `-1` cho ID virtual thread. Với service sử dụng nhiều virtual threads, ưu tiên các công cụ event/allocation profile hoặc bộ đo toàn quá trình có semantics thích hợp.

Ví dụ độc lập cho một platform thread chạy `main`:

```java
// File: ThreadAllocationRateDemo.java
import java.lang.management.ManagementFactory;
import com.sun.management.ThreadMXBean;

public class ThreadAllocationRateDemo {
    private static volatile Object sink;

    public static void main(String[] args) {
        var standard = ManagementFactory.getThreadMXBean();

        if (!(standard instanceof ThreadMXBean bean)
                || !bean.isThreadAllocatedMemorySupported()
                || !bean.isThreadAllocatedMemoryEnabled()) {
            System.out.println("Thread allocation measurement unavailable");
            return;
        }

        long id = Thread.currentThread().threadId();
        long beforeBytes = bean.getThreadAllocatedBytes(id);
        long started = System.nanoTime();

        for (int i = 0; i < 10_000; i++) {
            byte[] block = new byte[4 * 1024];
            block[0] = (byte) i;
            sink = block;
        }

        long elapsedNanos = System.nanoTime() - started;
        long afterBytes = bean.getThreadAllocatedBytes(id);

        if (beforeBytes < 0 || afterBytes < 0 || elapsedNanos <= 0) {
            System.out.println("No valid measurement");
            return;
        }

        double mib = (afterBytes - beforeBytes) / (1024.0 * 1024.0);
        double seconds = elapsedNanos / 1_000_000_000.0;

        System.out.printf(
            "Approx allocated = %.2f MiB; avg rate = %.2f MiB/s%n",
            mib, mib / seconds
        );
    }
}
```

Chạy:

```text
javac ThreadAllocationRateDemo.java
java ThreadAllocationRateDemo
```

Nếu project dùng **Java module** riêng, cần đọc hợp đồng module và khai báo `requires jdk.management;` để dùng extension `com.sun.management`. Nếu capability chưa bật, ví dụ chỉ in thông báo thay vì tự thay đổi cấu hình monitoring của JVM production.

**Giới hạn diễn giải:**

- Con số là xấp xỉ **heap allocation** do thread đo, không phải kích thước RSS hoặc native/direct allocation.
- Một lần chạy rất ngắn chịu tác động từ warmup JIT, scheduling và thiết bị, nên tốc độ MiB/s đơn lẻ **không** là benchmark.
- Object cấp phát ở thread khác không nằm trong counter của thread này.
- Không dùng mã mẫu trên để suy ra global allocation rate của hệ thống nhiều virtual threads.
- Khi đo production, nên chọn công cụ hỗ trợ **số liệu theo cửa sổ đủ dài** và liên hệ với response throughput.

## 11. Java Flight Recorder (JFR) và Java Mission Control (JMC)

**JFR** là công cụ profiling/event recording được JDK hỗ trợ, dùng để quan sát GC, allocation sites, CPU, thread, lock và I/O trong một cửa sổ thời gian. **JMC** giúp phân tích trực quan recording và tìm điểm nóng.

Ví dụ tạo recording trong 60 giây:

```text
java -XX:StartFlightRecording=duration=60s,filename=memory.jfr,settings=profile -Xmx512m MyApp
```

Hoặc với một JVM đã chạy:

```text
jcmd -l
jcmd <PID> JFR.start name=mem settings=profile duration=60s filename=memory.jfr
```

`<PID>` là process ID của Java process cần quan sát; thay bằng số thật khi sử dụng lệnh. Các lệnh `jcmd` có thể cần quyền truy cập cùng user/host và có overhead. **Không** gửi lệnh diagnostic bừa bãi tới môi trường production không được phép.

Xem recording bằng công cụ JDK:

```text
jfr summary memory.jfr
jfr print --categories GC memory.jfr
```

Hoặc mở `memory.jfr` bằng JMC và xem các trang **Garbage Collections**, **Memory**, **Allocation** và **Method Profiling** (tên trang tùy bản công cụ).

### 11.1. Khi nào dùng GC log, JFR, heap dump?

| Công cụ | Mạnh ở | Hạn chế và lưu ý |
| --- | --- | --- |
| **Unified GC logs** | GC pause/cause, trước/sau heap, giai đoạn, cadence | Không tự chỉ ra dòng Java nào cấp phát nhiều |
| **JFR/JMC** | Correlate pause, allocation samples, CPU, I/O và thread events | Sampling/event settings có overhead; mẫu cấp phát không luôn là đếm tuyệt đối |
| **`jcmd PID GC.heap_info`** | Snapshot thông tin heap đang chạy | Không phải allocation rate hay một chuỗi thời gian |
| **`jcmd PID VM.flags`** | Cờ JVM đang có hiệu lực | Không thay được quan sát tải |
| **Heap dump và histogram** | Tìm object retention, dominators, references | Có thể gây pause/overhead; dump rất lớn, có dữ liệu nhạy cảm |
| **Native Memory Tracking (NMT)** | Phân tích một số vùng native memory của JVM | Cần cấu hình trước khi chạy; có chi phí và không bao gồm tất cả native allocations của thư viện tùy ý |

### 11.2. Heap dump khi gặp OutOfMemoryError

Trong hệ thống được quản lý, có thể chuẩn bị:

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure/dumps
```

Chỉ cấu hình khi đủ không gian đĩa, quyền truy cập và **chính sách lưu giữ bảo mật**. Heap dump có thể chứa token, tên người dùng, payload, khóa API và dữ liệu nhạy cảm. Không tự động upload heap dump lên công cụ phân tích công khai hoặc chia sẻ không kiểm soát.

### 11.3. Native Memory Tracking không phải heap profiling

Để chẩn đoán native memory trong một quy trình **được phép quan sát**, NMT có thể được bật lúc khởi động:

```text
-XX:NativeMemoryTracking=summary
```

Sau đó:

```text
jcmd <PID> VM.native_memory summary
```

NMT cho cái nhìn theo các loại memory mà JVM theo dõi, không phải tổng hợp mọi allocation của native libraries do ứng dụng gọi. Nếu heap ổn định nhưng RSS tăng, xem cả NMT, native direct buffers, thread count, memory mapping và báo cáo container/OS.

## 12. Chiến lược tuning dựa trên mục tiêu, không dựa trên cờ ngẫu nhiên

Một quy trình có thể lặp lại:

1. **Xác định SLO:** ví dụ HTTP p99 dưới một giới hạn, request/s tối thiểu, giới hạn RSS/container và CPU quota.
2. **Tạo baseline:** cùng workload, warmup, số users, concurrency, payload, traffic pattern và thời gian đo.
3. **Bật quan sát phù hợp:** GC log, JFR, heap/RSS, CPU, allocation và request latency.
4. **Phân loại vấn đề:** pause dài, GC quá thường xuyên, throughput ứng dụng thấp, retention tăng hay native memory.
5. **Chọn một thay đổi nhỏ:** giảm allocation, sửa cache, tăng headroom, điều chỉnh G1 pause target hoặc thử một collector khác khi có lý do.
6. **Đo lại với cùng điều kiện:** lấy mean/p95/p99, request/s, CPU, memory và GC logs.
7. **Đánh giá trade-off:** không tối ưu một đồ thị mà làm xấu một SLO khác.
8. **Ghi cấu hình và rollback:** cờ, JDK build, CPU quota, container memory và tải ứng dụng.

### 12.1. Nếu GC pause dài

Ưu tiên điều tra:

- Có phải **Full GC** hay một phase bất thường không?
- Live set có tăng liên tục không?
- Có humongous object, promotion cao, fragmentation hoặc CPU contention không?
- Pause dài trùng với safepoint/OS scheduling hay request load spike không?
- G1 đang dùng tham số `-Xmn`/`NewRatio` cố định khiến adaptive pause khó hoạt động?

Chỉ sau khi có dữ liệu, thử mục tiêu `-XX:MaxGCPauseMillis` phù hợp hoặc collector latency thấp hơn. Một mục tiêu quá gắt có thể **tăng số lần GC** và làm mất throughput.

### 12.2. Nếu throughput thấp

Đo cả:

- **Application transactions/s**, CPU thực của service.
- Tổng pause time và **concurrent CPU used by GC**.
- Allocation rate, bytes/request, sống sót/promotion.
- I/O, lock contention, DB/network vì throughput thấp không nhất thiết do GC.

Nếu pause dài nhưng được chấp nhận trong batch workload, **Parallel GC** có thể là một lựa chọn đáng benchmark. Nếu ứng dụng nhạy latency p99, xem G1/ZGC và tổng CPU/RAM. Không tuyên bố một collector chắc chắn tốt hơn trước khi đo.

### 12.3. Nếu GC chạy quá thường xuyên

Tìm allocation hotspot trong JFR, giảm object tạm không cần thiết và các chuyển đổi/chụp collection dư thừa. Có thể tăng headroom heap khi memory budget cho phép. **Đừng tạo object pool cho mọi object nhỏ**: JVM/TLAB/JIT hiện đại thường cấp phát ngắn hạn rất hiệu quả; pooling sai có thể khiến object sống lâu hơn, tăng retention/đồng bộ và gây nhiều GC work hơn.

### 12.4. Nếu heap used sau GC tăng mãi

Kiểm tra cache, collection có retention dài, listeners, references từ static fields, ThreadLocal và object graph. Heap dump + dominator tree có thể hữu ích, nhưng tránh thu dump không kiểm soát ở production. Tăng `-Xmx` chỉ có thể **trì hoãn** lỗi nếu nguyên nhân là retention vô hạn.

## 13. Các tình huống minh họa theo số liệu

### 13.1. Tình huống A — allocation rate cao, heap ổn định

```text
Allocated:       400 MiB/s
Post-GC heap:    ~350 MiB, khá ổn định
GC pauses:       8–15 ms, nhiều lần mỗi giây
HTTP p99:        trong giới hạn
```

Có thể chấp nhận nếu CPU và throughput còn đủ ngân sách. Nếu CPU GC tăng hoặc throughput không đạt, xem allocation hotspots. **Không** gọi đó là leak chỉ vì allocation rate cao.

### 13.2. Tình huống B — live set tăng, Full GC xuất hiện

```text
Post-GC heap:    500 → 700 → 900 MiB
Xmx:             1 GiB
Full GC:         bắt đầu xuất hiện
Request/s:       giảm
```

Nghi ngờ object retention hoặc live data tăng theo tải. Dùng heap dump/JFR để xem object nào giữ tham chiếu. Trước khi “tăng heap lên 4 GiB”, xác định đó là **dữ liệu nghiệp vụ hợp lệ** hay cache/collection không giới hạn.

### 13.3. Tình huống C — ZGC pause thấp, CPU cao

```text
GC pauses:       nhỏ và ổn định
JVM process CPU: cao
Application rps: thấp hơn baseline G1
Heap headroom:   đủ
```

Có thể concurrent GC tốn CPU hoặc workload không hưởng đủ lợi ích từ latency thấp. So sánh trên **cùng điều kiện** và quyết định theo SLO. Pause thấp **không** bảo đảm throughput cao.

### 13.4. Tình huống D — heap ổn định nhưng container OOM

```text
Java heap used:  ~700 MiB
Xmx:             1 GiB
Container limit: 1.5 GiB
Process RSS:     tiến gần giới hạn container
```

Cần kiểm tra direct memory, metaspace, stacks, code cache, native libraries, memory mapping và số threads. Hạ/điều chỉnh `-Xmx` có thể để dành chỗ cho native memory nếu phù hợp, nhưng không thể đoán thủ phạm từ heap GC logs.

## 14. Lỗi hiểu nhầm thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Java có GC nên không thể leak” | Object còn reachable vẫn được giữ | Memory leak logic vẫn tồn tại |
| “Allocation rate là heap used tăng bao nhiêu MB” | Object mới có thể được thu hồi trong cửa sổ | Đo tổng byte cấp phát, không đo delta occupancy |
| “GC pause bằng response latency” | Request còn I/O, lock, CPU, queue | Đo GC pause và HTTP p99 riêng |
| “G1 MaxGCPauseMillis=100 bảo đảm dưới 100 ms” | Đây là mục tiêu mềm | Đọc distribution thực tế |
| “G1 mặc định chỉ khi máy nhiều CPU/RAM” | **Sai với JDK 27** | G1 mặc định mọi cấu hình HotSpot |
| “Cứ tăng -Xmx là hết GC” | GC vẫn cần chạy; footprint tăng | Tăng heap có thể giảm tần suất nhưng phải đo |
| “ZGC không bao giờ pause” | Vẫn có các đoạn STW ngắn | ZGC chủ yếu concurrent, không có SLA tuyệt đối |
| “ZGC cần bật ZGenerational” | Flag đã bị loại từ JDK 24 | Java 27 ZGC chỉ có mô hình generational |
| “GC throughput 99% nghĩa GC chỉ dùng 1% CPU” | Concurrent GC CPU không nằm trong pause fraction | Quan sát CPU/transactions/s riêng |
| “Heap committed bằng RSS” | JVM còn native/direct/stack/mapped memory | Quan sát memory theo nhiều tầng |
| “GC count tăng là chương trình lỗi” | Nhiều object ngắn hạn là bình thường | Xét pause, throughput, allocation và SLO |
| “Có 1000 lần new nên chắc cấp phát 1000 object” | JIT có thể loại bỏ/biến đổi allocation | Dùng profiler và đo runtime |
| “G1 Full GC luôn do heap quá nhỏ” | Có thể do retention, humongous, pressure, tuning | Đọc causes và live set |
| “JFR profile luôn đếm chính xác mọi allocation” | Một số event là sampling | Biết chính xác event/settings và độ lệch |
| “System.gc() làm sạch heap ngay” | Không đảm bảo thời điểm hoặc hiệu quả | Không dùng làm công cụ memory management thường xuyên |
| “Tăng pool object sẽ luôn tăng tốc” | Pooling kéo dài lifetime và tăng contention | Benchmark trước, ưu tiên giảm allocation không cần |
| “GC log có thể cho biết code line tạo rác nhiều nhất” | Log chủ yếu nêu GC activity | Dùng JFR allocation profile/heap analysis |
| “Native OOM luôn sửa bằng tăng Xmx” | Native memory nằm ngoài heap | Phân tích RSS/NMT và memory budget |

## 15. Checklist đưa kiến thức GC vào vận hành

- **Hiểu rõ collector đang chạy:** kiểm tra log và JVM flags, nhớ Java 27 HotSpot chọn G1 mặc định ở mọi cấu hình.
- **Xác định SLO nghiệp vụ:** tail latency và throughput thực, chứ không chỉ GC pause.
- **Phân biệt ba đại lượng:** allocation rate, live set và heap headroom.
- **Theo dõi cả max/p95/p99 pause:** một số liệu trung bình có thể che pause cực dài.
- **Không dùng số GC throughput để thay thế CPU utilization:** concurrent GC có chi phí ngoài STW.
- **Quan sát heap và native memory:** `-Xmx` không phải giới hạn toàn bộ process.
- **Đo đúng bằng công cụ phù hợp:** `-Xlog` cho events, JFR/JMC cho hotspots, `jcmd` cho snapshot.
- **Xác thực allocation hotspots:** nhìn bytes/request, allocations/s; cẩn thận với sampling và JIT.
- **Không chỉnh nhiều knobs cùng lúc:** thay một biến, đo lại và lưu baseline.
- **Không cố định young generation của G1 tùy tiện:** có thể phá khả năng tự tối ưu pause.
- **Không dùng flag legacy hoặc đã bị loại bỏ:** dùng unified logging và collector hiện hành.
- **Ưu tiên giải quyết retention hoặc object churn trong code** trước khi tăng tài nguyên vô thời hạn.
- **Giới hạn dữ liệu quan sát:** log, JFR và heap dump có overhead, dung lượng và thông tin nhạy cảm.
- **Có kế hoạch rollback:** GC tuning phải có benchmark, SLO và cấu hình có thể khôi phục.

## 16. Bài tập tự kiểm tra

1. Service cấp phát `2.400 MiB` object trong `12 giây` nhưng heap used chỉ tăng `100 MiB`. Allocation rate xấp xỉ bao nhiêu? **200 MiB/s**. Vì sao không thể lấy `100 / 12` để đo allocation rate?
2. Trong một phút, tổng STW GC pause là `1,8 giây`. Theo định nghĩa đơn giản, GC throughput khoảng bao nhiêu? **97%**. Con số đó có cho biết CPU dành cho concurrent GC không? **Không**.
3. GC log có nhiều young pauses ngắn, heap sau thu gom ổn định và HTTP p99 đạt SLO. Có nhất thiết phải “fix” không? **Không**; cần xem throughput/CPU và ngân sách vận hành.
4. Cùng một service chạy G1 mặc định, khi đặt `-XX:MaxGCPauseMillis=50` thì pauses ngắn hơn nhưng CPU và request latency trung bình xấu đi. Giải thích: G1 có thể điều chỉnh số lần/lượng công việc GC, gây trade-off throughput.
5. Một container có RAM 1 GiB, `-Xmx1g`; process bị OOM dù heap chưa đầy. Nêu hai vùng cần kiểm tra ngoài heap: **direct/native memory, thread stacks, metaspace** và những thành phần khác.
6. Với JDK 27, nếu không chỉ định GC và có một CPU/ít RAM, JVM HotSpot tự chọn collector nào? **G1**, không phải mặc định Serial như một số hướng dẫn cũ.
7. Vì sao không cần `-XX:+ZGenerational` trong Java 27? Vì ZGC hiện hành đã **chỉ còn generational** từ JDK 24; tùy chọn đã bị loại bỏ.

## Tài liệu tham khảo chính thức (Java SE 27)

- [Oracle Java SE 27 — HotSpot VM Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/index.html) — tài liệu nền tảng theo đúng phiên bản.
- [Introduction to Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/introduction-garbage-collection-tuning.html) — vai trò GC và lựa chọn collector mặc định.
- [Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-collector-implementation.html) — reachability, generational hypothesis, throughput và latency.
- [Ergonomics](https://docs.oracle.com/en/java/javase/27/gctuning/ergonomics.html) — mục tiêu pause, throughput và quy tắc chọn GC mặc định trong JDK 27.
- [Available Collectors](https://docs.oracle.com/en/java/javase/27/gctuning/available-collectors.html) — Serial, Parallel, G1, ZGC.
- [Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html) — G1 regions, hoạt động thu gom và pause goal.
- [Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html) — tuning có mục đích và phân tích Full GC.
- [The Z Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/z-garbage-collector.html) — ZGC generational hiện hành, headroom và concurrent collection.
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — `-Xms`, `-Xmx`, GC selection và `-Xlog`.
- [The jcmd Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — `GC.heap_info`, `VM.flags`, `JFR.start`, `VM.native_memory`.
- [The jfr Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jfr.html) — `summary`, `print` và xuất thông tin JFR.
- [Diagnostic Tools — Java SE 27](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html) — JFR, JMC, allocation profile và điều tra GC.
- [`com.sun.management.ThreadMXBean` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/com/sun/management/ThreadMXBean.html) — số byte được cấp phát bởi platform thread, giới hạn của phép đo.
- [OpenJDK JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523) — thay đổi mặc định của JDK 27.
