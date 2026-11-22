# GC độ trễ thấp — Concurrent marking, relocation và công việc song song với ứng dụng (Java 11+)

## Mục tiêu bài học

Khi ứng dụng Java phục vụ HTTP, giao dịch, streaming hay tác vụ có yêu cầu **P95/P99 latency**, không thể chỉ nhìn “GC chạy bao nhiêu lần”. Cần hiểu **GC làm gì trong lúc ứng dụng vẫn chạy**, công việc nào bắt buộc phải **stop-the-world (STW)**, và tại sao **concurrent marking** khác với **concurrent relocation**.

Từ Java 11 đến những JDK hiện đại, các collector như **G1**, **ZGC** và **Shenandoah** dùng các chiến lược khác nhau để cân bằng **pause time, throughput, CPU, memory headroom và độ phức tạp barrier**. G1 có marking đồng thời nhưng vẫn thực hiện nhiều đợt evacuation trong STW; ZGC hiện đại thực hiện phần lớn công việc nặng đồng thời, kể cả relocation; Shenandoah cũng thực hiện evacuation/concurrent reference processing với cơ chế triển khai riêng. Không có collector nào biến ứng dụng thành hệ thống real-time có deadline được bảo đảm tuyệt đối.

**Sau bài học, bạn sẽ:**

1. Phân biệt chính xác **concurrent**, **parallel**, **incremental** và **stop-the-world**.
2. Giải thích concurrent marking: duyệt đồ thị reachability trong khi **mutator threads** liên tục tạo/sửa/xóa references.
3. Hiểu vai trò của **write/read/load barriers**, **marking invariants**, **snapshot-at-the-beginning (SATB)**, remembered sets và forwarding information.
4. Mô tả **object evacuation/relocation** và vì sao moving objects khi application chạy đòi hỏi cập nhật references an toàn.
5. So sánh G1, ZGC, Shenandoah theo câu hỏi trọng tâm: pha nào chạy đồng thời với ứng dụng, pha nào STW, và chi phí được chuyển sang đâu.
6. Hiểu khác biệt phiên bản: G1 sẵn có ở Java 11; ZGC ban đầu thử nghiệm trên Java 11 nhưng là production collector ở JDK hiện đại; **ZGC hiện đại đã chuyển hoàn toàn sang generational từ JDK 24**, không sử dụng hướng dẫn cũ bật/tắt non-generational mode.
7. Dùng chương trình **Java 11 chạy được** cùng `-Xlog:gc` để quan sát mutators tạo allocation pressure trong lúc collector thu gom; không suy nhầm số lần GC với pause duration.
8. Đọc GC logs/JFR, đo **tail latency và CPU/memory**, xây thử nghiệm A/B thực tế thay vì chọn GC theo quảng cáo.
9. Tránh các lỗi điển hình: heap quá nhỏ, không đủ CPU cho concurrent workers, pinned objects, allocation stalls, full/degenerate collection, benchmark sai, tuning quá sớm và khẳng định “GC pause bằng 0”.

**Special Note:** chỉ dùng kiến thức **còn áp dụng** trên Java 11+ và các JDK hiện đại. Bài phân biệt những đặc điểm **lịch sử để giải thích tính tương thích**, nhưng không đưa cờ/tùy chọn đã bị loại bỏ thành cấu hình production hiện nay.

---

## 1. Vì sao có GC “độ trễ thấp”?

Trong JVM, object được tạo và nhiều object nhanh chóng trở thành **unreachable**. Collector phải tìm ra vùng bộ nhớ có thể tái sử dụng mà vẫn bảo đảm chương trình đọc/ghi references đúng theo Java Memory Model và đặc tả JVM.

Vấn đề với ứng dụng nhạy latency là **số lần thread bị tạm dừng**:

```text
Stop-the-world collector (sơ đồ khái niệm)

Time  ------------------------------------------------------------->
Application: RUN RUN RUN |------- PAUSED FOR GC -------| RUN RUN RUN
GC work:             ... |  mark / move / update / free | ...
Latency:                 ^ request có thể bị kéo dài ^
```

Một collector độ trễ thấp cố đưa phần lớn công việc nặng vào **concurrent phases**:

```text
Mostly/fully concurrent design (sơ đồ khái niệm)

Time  ----------------------------------------------------------------->
Application: RUN RUN |short STW| RUN RUN RUN RUN |short STW| RUN RUN RUN
GC:                root init   [mark / relocate ...]    handoff  [cleanup]
CPU:                             GC threads dùng CPU cùng mutators
```

Sơ đồ chỉ mô tả **ý tưởng**, không phải thứ tự pha được bảo đảm cho mọi collector/JDK. Một collector vẫn có thể cần safepoints, root handshakes, reference processing, termination checks, barriers và fallback; không nên tuyên bố “ứng dụng không bao giờ bị stop”.

**Trade-off cốt lõi:** giảm thời gian STW thường chuyển chi phí sang **CPU khi ứng dụng đang chạy, barriers trên đường đọc/ghi references, memory headroom và độ phức tạp của GC**. Vì vậy P99 latency có thể tốt hơn nhưng throughput hoặc resource cost không nhất thiết tốt hơn.

## 2. Bốn thuật ngữ thường bị dùng sai

| Thuật ngữ | Ý nghĩa chính | Có buộc application dừng? |
| --- | --- | --- |
| **Stop-the-world (STW)** | Các mutator threads bị tạm dừng để JVM thực hiện một phase hoặc handshake | **Có** trong pause đó |
| **Concurrent** | GC work diễn ra đồng thời theo thời gian với **mutator/application threads** | **Không nhất thiết**, trừ các pause/ngắt phase liên quan |
| **Parallel** | Nhiều GC worker threads làm **cùng một loại công việc GC** đồng thời | Có thể là **STW parallel** hoặc concurrent parallel |
| **Incremental** | Công việc lớn được chia thành những đợt/bước nhỏ | Các đợt có thể STW hoặc concurrent; không đồng nghĩa concurrent |

**Phân biệt:** G1 thường sử dụng **nhiều GC threads trong một evacuation pause**. Đó là *parallel stop-the-world evacuation*: nhiều core thực hiện GC cùng lúc, nhưng **ứng dụng vẫn đang pause**. Vì vậy không được nhìn thấy `ParallelGCThreads` rồi kết luận “GC chạy song song với ứng dụng”.

Ngược lại, **concurrent marking** thường dùng worker threads cạnh tranh CPU với ứng dụng. Nó là concurrent với *mutators*; bản thân marking có thể được xử lý bởi **nhiều GC workers**.

### Mutator là ai?

Trong thuật ngữ GC, **mutator** là code ứng dụng/JVM đang thay đổi heap object graph: tạo object, gán field references, thêm item vào list, v.v. Mutator threads không phải thứ gì riêng biệt với Java application threads. Khi nói “GC chạy concurrent với mutator”, nghĩa là Java code **tiếp tục thực thi và thay đổi references** trong khi GC làm việc.

Ví dụ:

```java
Object old = holder.next;   // đọc reference
holder.next = new Node();   // thay object graph
Object use = holder.next;   // tiếp tục truy cập
```

Đây là code minh họa với `holder` và `Node` do ứng dụng tự định nghĩa, không phải chương trình hoàn chỉnh. GC phải xử lý đúng các thao tác đọc/ghi đó ngay cả khi đang đánh dấu hoặc chuyển object.

## 3. Concurrent marking: tìm object sống khi đồ thị đang biến đổi

### 3.1. Marking xác định điều gì?

Marking bắt đầu từ **GC roots** (ví dụ references trên stacks, static fields và các roots khác) rồi đi theo các edges trong object graph để xác định **reachable objects**.

```text
GC roots
   |
   +-- A --> B --> C
   |          \
   |           +--> D
   |
   +-- X --> Y

Object Z không còn reachable => ứng viên được thu hồi
```

Nếu mutators bị dừng, đồ thị tương đối ổn định trong khi đánh dấu. Nhưng khi marking **concurrent**, ứng dụng có thể:

- Tạo một object mới.
- Gán field `A.child = E`.
- Xóa edge `A.child = null`.
- Chuyển edge từ đối tượng này sang đối tượng khác.
- Chuyển đối tượng giữa các vùng nhớ/tuổi thế hệ theo hoạt động GC.

Nếu GC chỉ duyệt theo một graph “đang thay đổi” mà không có invariant, có thể **bỏ sót object vẫn sống** và thu hồi bộ nhớ mà ứng dụng còn dùng. Điều đó không được phép.

### 3.2. Write barrier giữ marking invariant

Collector chèn một số thao tác runtime quanh write/read reference, gọi là **barriers**. Chúng không phải lệnh Java API do lập trình viên phải tự gọi; JIT/interpreter/runtime cung cấp theo collector đã chọn.

Ví dụ ý tưởng:

```text
Mutator:
    oldReference = object.field
    object.field = newReference

Write barrier:
    thông báo / ghi nhớ reference liên quan
    để concurrent marker không bỏ sót reachable objects
```

Chi tiết phụ thuộc collector. **Không** coi mọi GC đều dùng cùng một write barrier hay cùng chính sách SATB.

### 3.3. SATB — Snapshot-At-The-Beginning

**G1** dùng cách marking dựa trên **SATB**: bảo toàn về mặt logic những objects được coi là live tại thời điểm bắt đầu vòng marking, dù một số references có thể bị xóa trong khi marking diễn ra.

Một ý tưởng của **SATB pre-write barrier** là theo dõi reference cũ khi mutator chuẩn bị ghi đè edge, để marker không bỏ lỡ những object tồn tại ở snapshot logic. Ví dụ:

```text
T0: Root --> A --> B       (B sống ở đầu vòng mark)
T1: Mutator đổi A.next từ B sang C
T2: Marker chưa nhìn thấy B nếu chỉ đọc A.next lúc T2

SATB barrier lưu thông tin reference cũ B,
để marker không coi B mất sống chỉ do edge bị đổi trong lúc duyệt.
```

**Hệ quả:** một object đã trở thành unreachable trong khi marking chạy có thể vẫn bị đánh dấu live theo snapshot và chưa được reclaim đến vòng sau. Đây thường được gọi là *floating garbage*, là chi phí hợp lệ để bảo toàn tính đúng đắn khi thao tác đồng thời.

Không được nhầm SATB với một bản sao heap snapshot thực sự được copy ra bộ nhớ; nó là **mô hình invariant và kỹ thuật barrier**, không phải file snapshot.

### 3.4. Marking có thể kết thúc bằng pause ngắn

Concurrent marking không có nghĩa toàn bộ marking không cần tạm dừng application:

- Một collector có thể có một lần khởi động marking tại safepoint/handshake.
- Có thể có **remark** để hoàn thành/tổng hợp work queues và reference processing.
- Có thể cần root scanning, class unloading hoặc các phase đặc thù.
- Nếu không theo kịp allocation rate, collector có thể phải dùng đường fallback.

Với G1, tài liệu Oracle nêu rõ **Remark** và **Cleanup** là stop-the-world phases liên quan marking cycle. Vì vậy **G1 có concurrent marking, nhưng không phải mọi phần của cycle đều concurrent**.

## 4. Relocation / evacuation: chuyển object đang sống

### 4.1. Tại sao cần di chuyển object?

Nếu chỉ reclaim những ô nhớ chết, heap có thể bị **fragmentation**. Một object lớn mới cần vùng bộ nhớ đủ liên tục dù tổng free bytes vẫn nhiều.

Các collector *moving/compacting* có thể chuyển những object còn sống từ vùng nhiều rác sang vùng mới:

```text
Before:
Region A: [LIVE 1][dead][LIVE 2][dead][LIVE 3] ...

After evacuation:
Region B: [LIVE 1][LIVE 2][LIVE 3][free ...]
Region A: [reclaim toàn bộ vùng nguồn khi an toàn]
```

*Evacuation* thường là copy live objects sang vùng khác; *relocation/compaction* là khái niệm rộng hơn về việc chuyển/cô đọng bố cục. Implementation và cách gọi phase khác nhau theo collector.

### 4.2. Thách thức khi di chuyển concurrent với mutator

Giả sử mutator có reference `refA` trỏ object A ở address cũ, trong khi collector đang copy A sang address mới:

```text
T0: Application refA --> old A
T1: GC copies old A to new A
T2: Application reads/writes refA
T3: GC wants to reclaim old region
```

Collector phải bảo đảm các thread tiếp tục dùng **một object logic thống nhất**, không đọc giá trị cũ hoặc sửa nhầm hai bản sao không nhất quán. Cần cơ chế xác định/điều hướng object location, forwarding state và cập nhật references phù hợp.

**Không** suy rằng chỉ cần copy bytes rồi free vùng cũ ngay. Giữa T1–T3 có thể vẫn còn references cũ nằm trên stack, trong fields hoặc ở compiled code.

### 4.3. Load/read barriers và forwarding

Một họ giải pháp sử dụng barriers trên đường truy cập references:

```text
Application đọc một reference
        |
        v
  GC/runtime kiểm tra trạng thái reference/object
        |
        +--> ổn định: đi tiếp
        |
        +--> đã được relocate:
               tìm/cập nhật target address hợp lệ
               rồi đi tiếp bằng object hiện hành
```

**ZGC** hiện đại sử dụng các kỹ thuật liên quan đến *colored references/pointers*, metadata bits và load/store barriers theo thiết kế hiện hành; chi tiết barrier đã thay đổi qua các thế hệ ZGC. **Shenandoah** sử dụng cơ chế barriers/forwarding và cập nhật references của riêng mình, cũng tiến hóa qua các phiên bản. Không nên sao chép mô tả một implementation năm 2018 thành lời khẳng định rằng bit layout hoặc forwarding path vẫn y hệt ở JDK 25+.

Điểm cần hiểu là **barrier bảo vệ tính đúng đắn khi application vẫn đọc/ghi object trong lúc relocation**. Chi phí của nó xảy ra trên những đường thực thi bình thường, là một phần trade-off của low-latency GC.

### 4.4. Khi nào có thể reclaim vùng nguồn?

Không phải ngay sau khi copy một object. Collector phải đảm bảo references đã được cập nhật hoặc đường truy cập cũ còn được xử lý an toàn, không còn đường nào có thể đọc vào memory đã free. Cách hoàn tất work (remapping/healing references, update-refs, handshakes, epoch changes, v.v.) là đặc thù collector.

Những pha **concurrent cleanup/reclaim** có thể diễn ra trong khi mutators tiếp tục tạo objects. Nhưng việc thiếu headroom, pinned references hoặc giới hạn runtime có thể buộc collector đi vào fallback/stall.

## 5. Phân biệt ba collector đang được dùng

| Thuộc tính | G1 | ZGC hiện đại | Shenandoah hiện đại |
| --- | --- | --- | --- |
| Mục tiêu phổ biến | Cân bằng throughput và pause-time goal | Latency rất thấp và scalable heap | Latency thấp qua concurrent work |
| Concurrent marking | **Có** | **Có** | **Có** |
| Evacuation/relocation | **Chủ yếu STW** (young/mixed evacuation pauses) | **Concurrent** phần lớn relocation | **Concurrent** phần lớn evacuation |
| Có STW phases? | **Có**, rõ ràng ở evacuation, remark, cleanup | **Có** một số phase phối hợp ngắn | **Có** một số phase phối hợp ngắn |
| Barrier work với mutators | SATB, card/remembered set và barriers tương ứng | Colored references/barriers và scheme hiện đại | Barriers/forwarding theo mode/phiên bản |
| Heap generations | Generational (young/old) | **Generational-only từ JDK 24** | Generational mode có trên JDK hiện đại có hỗ trợ; tùy phiên bản/mode |
| Failure mode cần chú ý | Evacuation failure, Full GC STW | Allocation stalls/CPU starvation/thiếu headroom | Degenerated/Full GC fallback khi concurrent cycle không theo kịp |
| Lệnh chọn collector | `-XX:+UseG1GC` | `-XX:+UseZGC` | `-XX:+UseShenandoahGC` nếu runtime hỗ trợ |

**Đây là phân loại cơ chế, không phải bảng xếp hạng hiệu năng.** G1 có thể thắng về throughput/CPU trong workload cụ thể; ZGC hoặc Shenandoah có thể giảm tail pauses nhưng cần headroom và CPU; nếu cấu hình kém, application latency vẫn xấu.

## 6. G1: đánh dấu concurrent, di chuyển object trong STW

**G1** là collector có từ Java 11 và vẫn hiện hành, thường là mặc định trên những cấu hình HotSpot phổ biến. G1 chia heap thành **regions** và dùng mô hình young/old generations.

Một lộ trình khái quát:

```text
Young-only collections:
    [STW Young GC: evacuate live objects]

Khi old occupancy/heuristics cho thấy cần mark:
    [STW Concurrent Start] --> [Concurrent Mark]
                                     |
                      application vẫn chạy, tạo/sửa objects
                                     |
                          [STW Remark] [STW Cleanup]
                                     |
Mixed collections:
    [STW Mixed GC: evacuate young + selected old regions]
    [STW Mixed GC: ...]
```

G1 uses **SATB** để làm marking trong khi application thay đổi đồ thị. G1 sau đó chọn những regions có nhiều rác/tỷ lệ reclaim tốt để thu gom trong các pauses nhỏ hơn so với việc luôn quét/compact toàn heap.

**Tâm điểm bài học:**

- **Concurrent marking không đồng nghĩa concurrent evacuation.**
- G1 **evacuation** của những vùng trong young/mixed collection chủ yếu diễn ra trong **STW pauses**, có thể dùng nhiều GC worker threads để xử lý song song.
- `-XX:MaxGCPauseMillis` là **mục tiêu/heuristic**, không phải SLA tuyệt đối.
- G1 đôi khi có **Full GC** với STW dài hơn, đặc biệt khi không còn đủ không gian/evacuation không thành công.
- Một cycle **không nhất thiết** chạy concurrent mark trong bài thử ngắn: nếu object sống ít hoặc heuristics chưa kích hoạt mark, log chỉ có Young evacuation pauses; điều đó không chứng minh G1 không hỗ trợ concurrent marking.

### Vì sao log `Pause Young (G1 Evacuation Pause)` quan trọng?

Ở lần thử thực tế bên dưới, một dòng G1 tương tự:

```text
[0.094s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 96M->50M(128M) 1.584ms
```

Đó là **log thực tế của một lần chạy**, không phải output cố định trên mọi máy. Các con số diễn giải:

- `0.094s` là uptime lúc log.
- `GC(0)` là cycle/event ID theo logging implementation.
- `Pause Young ... (G1 Evacuation Pause)` xác nhận một **STW pause** để evacuate young regions.
- `96M->50M(128M)` là thống kê heap occupancy trước/sau trong heap tối đa/gc-heap context của dòng log.
- `1.584ms` là duration của pause này, **không phải toàn bộ CPU time GC, cũng không phải end-to-end latency của request**.

Một pause 1.584ms ở fixture không chứng minh production có P99 pause dưới 2ms. Cần đo dưới live-set, CPU quota, allocation spikes và traffic thật.

### SATB và remembered sets

- SATB giữ marking invariant.
- Remembered sets/card tables theo dõi cross-region/inter-generational references để G1 thu từng vùng mà không scan toàn heap trong mọi pause.
- Những cập nhật có chi phí CPU/memory và có thể làm GC pause dài hơn trong điều kiện đặc thù.
- Nếu application mutate references rất nhiều, barrier overhead và remembered-set refinement trở thành yếu tố cần quan sát.

## 7. ZGC: đánh dấu và relocation đồng thời với mutators

**ZGC** nhắm đến **pause time rất thấp** bằng cách chuyển phần lớn công việc nặng — marking, relocation/compaction và những công việc liên quan — sang các concurrent phases. Đối với JDK hiện đại, **`-XX:+UseZGC`** chọn collector này trên build/platform hỗ trợ.

### Phiên bản Java phải được nói đúng

| Thời điểm | Điều cần biết hôm nay |
| --- | --- |
| **Java 11** | ZGC xuất hiện như **experimental** và phạm vi platform/version có giới hạn lịch sử; không nên dùng lệnh nâng cấp cũ như cấu hình khuyến nghị cho JDK mới |
| **Java 15** | ZGC chuyển thành tính năng **production** |
| **Java 21** | Generational ZGC xuất hiện |
| **JDK 23** | Generational ZGC trở thành lựa chọn mặc định trong ZGC |
| **JDK 24+** | Non-generational ZGC mode **đã bị loại bỏ**; ZGC là **generational-only** và `ZGenerational` không còn là cờ tùy chọn cần dùng |

Vì Special Note yêu cầu kiến thức hiện hành, các ví dụ thực hành **không** dùng `-XX:+ZGenerational`/`-XX:-ZGenerational` của những giai đoạn chuyển tiếp, cũng không dùng legacy commercial flags. Khi cần chạy thử trên **JDK 11 thật**, hãy dùng G1 trong ví dụ cơ bản và xem tài liệu version/vendor cho khả năng ZGC experimental riêng của JDK 11; không giả định câu lệnh ZGC production mới áp dụng 1:1 cho Java 11.

### Một cycle ZGC có gì?

Một sơ đồ ý tưởng:

```text
Application mutators: RUN  |short pause| RUN RUN RUN RUN |short pause| RUN

ZGC:
  start/root coordination
       |
       +-- concurrent mark / process reachability
       |
       +-- select regions / relocation work
       |
       +-- concurrent relocation and reference healing
       |
       +-- reclaim when safe
```

**Sơ đồ không phải phase listing chính xác của mọi JDK.** Generational ZGC có young/old generations, work queues, remembered-set/barrier information và policies riêng. Cách đặt tên log events có thể thay đổi giữa JDK 11 thử nghiệm và JDK 25 hiện đại.

### Tại sao ZGC cần heap headroom?

Một collector chạy concurrent phải **đuổi theo allocation rate**. Trong lúc GC đánh dấu và di chuyển live objects, mutators vẫn tiếp tục sinh object mới và tiêu thụ heap.

Nếu không có enough headroom:

- GC cycle chưa kịp reclaim đủ chỗ trống.
- Mutator có thể phải chờ allocation (**allocation stall**).
- CPU quota quá chặt khiến concurrent GC workers chậm, kéo dài cycle.
- Chi phí barriers và relocation có thể ảnh hưởng throughput.
- Hệ thống có thể gặp OOM hoặc path không mong đợi nếu workload vượt khả năng heap/runtime.

Vì vậy khi dùng `-XX:+UseZGC`, quan trọng nhất thường là **kích thước heap tối đa và dung lượng trống** đủ cho concurrent work khi application tiếp tục allocation. Không chỉ tăng `ConcGCThreads` một cách tùy tiện: thêm worker cũng cạnh tranh CPU với application.

### Colored pointers/barriers — hiểu đúng mức

ZGC dùng cơ chế metadata trên references và barriers để nhận biết trạng thái liveness/relocation và sửa các references khi cần. Điều này cho phép **ứng dụng tiếp tục dùng object logic đúng** dù collector đang chuyển vị trí vật lý của object.

**Không** cố học thuộc số bit metadata, địa chỉ memory hoặc một barrier sequence từ bài viết cũ làm quy tắc của mọi JDK; modern generational ZGC tiếp tục được cải tiến và có những thay đổi nội bộ quan trọng. Với ứng dụng Java bình thường, interface cần quan tâm là **tính đúng đắn được JVM bảo đảm**, còn lựa chọn GC/heap đo qua performance evidence.

## 8. Shenandoah: concurrent evacuation và cập nhật references

**Shenandoah** là collector độ trễ thấp có tính năng **concurrent evacuation**; được tích hợp vào các bản OpenJDK hiện đại nhưng **không phải mọi distribution/build đều bật hoặc đóng gói nó**. Dùng `-XX:+UseShenandoahGC` **chỉ khi JVM thực tế hỗ trợ**.

Sơ đồ khái quát:

```text
Shenandoah cycle (tên pha có thể khác theo mode/JDK):
    short initialization / root coordination
                    |
           concurrent marking
                    |
             final mark / pause
                    |
          concurrent evacuation
                    |
       concurrent reference updates/cleanup
                    |
              reclaim safely
```

Shenandoah dùng barriers/forwarding để bảo vệ việc application truy cập object đang chuyển vùng. Trong mode/version khác nhau, các barrier operations và pha cập nhật references có thể được thiết kế khác; không nên khẳng định mọi bản đều dùng đúng một thuật toán Brooks pointer cố định.

### Shenandoah hiện đại và generational mode

Trong các JDK/build hiện đại có hỗ trợ, Shenandoah có thêm **generational mode** để cải thiện hiệu quả đối với object sống ngắn. Ở JDK 25, chế độ generational được đưa vào sản phẩm và có thể chọn theo tùy chọn hỗ trợ của build, ví dụ `-XX:ShenandoahGCMode=generational`. Tuy nhiên, **không tự giả định đó là mode mặc định** hoặc tính năng có trong mọi vendor/JDK 11.

Với Java 11: Shenandoah không phải collector có mặt đồng nhất trong mọi bản JDK 11; một số vendor có backport riêng. Trước khi dùng tùy chọn `UseShenandoahGC` trên Java 11, kiểm tra `java -version`, build info và flags được hỗ trợ. Bài không dựa vào các chi tiết backport để giải thích khái niệm còn áp dụng.

### Concurrent GC vẫn có fallback

Nếu concurrent marking/evacuation không hoàn thành kịp vì allocation rate, thiếu memory headroom, thread scheduling hoặc giới hạn khác, Shenandoah có thể có **degenerated/full GC** với STW dài hơn. Vì vậy `-XX:+UseShenandoahGC` không phải cam kết “luôn dưới 1ms”. Theo dõi cả những fallback cycles hiếm, đặc biệt vì **P99.9** nhạy với long-tail outliers.

### Bằng chứng trong log thực tế

Trong fixture được kiểm thử ở phần 10, log Shenandoah trên runtime hỗ trợ có những dòng dạng:

```text
[0.059s][info][gc] GC(0) Concurrent marking roots 0.180ms
[0.060s][info][gc] GC(0) Concurrent marking (unload classes) 0.974ms
[0.061s][info][gc] GC(0) Concurrent evacuation 0.102ms
```

Đây là **log thực tế của lần thử** với JDK có Shenandoah, không phải một biểu đồ đảm bảo độ dài cycles. Những dòng mang nhãn `Concurrent ...` biểu thị công việc GC diễn ra **khi mutators có thể chạy**, khác với `Pause Young` ở G1.

**Lưu ý:** duration của một concurrent phase **không phải GC pause time**. Không cộng các `0.180ms+0.974ms+0.102ms` rồi báo ứng dụng “đứng 1.256ms”. GC workers và application có thể đã tiến triển đồng thời trong phần lớn khoảng ấy.

## 9. Diễn giải phases theo ba trục độc lập

Một bảng giúp tránh nhầm:

| Pha/công việc | Có thể concurrent với mutators? | Có thể sử dụng nhiều GC workers song song? | Tác động dự kiến |
| --- | --- | --- | --- |
| G1 concurrent mark | **Có** | **Có** | CPU/barrier overhead khi application chạy |
| G1 young/mixed evacuation | **Không**, chủ yếu STW | **Có** | Tạo pause thực sự; mục tiêu chia thành đợt ngắn |
| G1 remark/cleanup | **Không** ở các pause tương ứng | Có tùy implementation | Stop-the-world ngắn/dài tùy workload |
| ZGC concurrent mark | **Có** | **Có** | CPU, barriers, live-set headroom |
| ZGC concurrent relocation | **Có** | **Có** | Thêm work và memory headroom, load/store barriers |
| Shenandoah concurrent mark | **Có** | **Có** | CPU/barriers đồng thời với mutators |
| Shenandoah concurrent evacuation | **Có** | **Có** | Object movement trong khi app hoạt động |
| Full/degenerate fallback | Tùy collector, thường **STW** ở nhiều đường | Có thể | Long-tail pause/throughput degradation |

**Song song giữa GC workers** là một trục khác với **đồng thời giữa GC và application**. Đừng dịch chung cả hai thành “parallel GC” rồi suy ra cùng hành vi latency.

## 10. Chương trình Java 11 chạy được: mutators tạo áp lực cấp phát

Mục tiêu fixture: tạo workload có **nhiều short-lived arrays** và một tập objects được giữ lại, trong lúc 2 mutator threads vẫn làm việc. Dùng `GarbageCollectorMXBean` để quan sát **số chu kỳ thu gom đã được JVM báo**, nhưng không coi count này là phép đo pause latency hoặc mô hình pha của collector.

**Chương trình không cố tạo synthetic object graph để mô phỏng internal barriers.** Điều đó là trách nhiệm JVM; ta cần đọc GC logs/JFR để biết collector thật đã làm gì.

### 10.1. Tệp `ConcurrentGcWorkDemo.java`

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public final class ConcurrentGcWorkDemo {
    private static final int WORKERS = 2;
    private static final int LOOPS = 120_000;
    private static final int BUFFER_BYTES = 4096;
    private static volatile Object published;

    private static long collectionCount() {
        long count = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value >= 0) {
                count += value;
            }
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        List<byte[]> retained = new ArrayList<>();
        for (int i = 0; i < 24; i++) {
            retained.add(new byte[1024 * 1024]);
        }

        long gcBefore = collectionCount();
        AtomicLong completed = new AtomicLong();
        AtomicReference<Throwable> failure =
                new AtomicReference<>();
        CountDownLatch start = new CountDownLatch(1);
        List<Thread> workers = new ArrayList<>();

        for (int workerId = 0; workerId < WORKERS; workerId++) {
            final int id = workerId;
            Thread worker = new Thread(() -> {
                try {
                    byte[][] recent = new byte[128][];
                    start.await();
                    for (int i = 0; i < LOOPS; i++) {
                        byte[] bytes = new byte[BUFFER_BYTES];
                        bytes[0] = (byte) (i ^ id);
                        recent[i & 127] = bytes;
                        if ((i & 1023) == 0) {
                            published = bytes;
                            Thread.yield();
                        }
                    }
                    if (recent[(LOOPS - 1) & 127] == null) {
                        throw new AssertionError(
                                "missing allocation");
                    }
                    completed.incrementAndGet();
                } catch (Throwable ex) {
                    failure.compareAndSet(null, ex);
                }
            }, "mutator-" + workerId);
            workers.add(worker);
            worker.start();
        }

        start.countDown();
        for (Thread worker : workers) {
            worker.join();
        }
        if (failure.get() != null) {
            throw new IllegalStateException(
                    "Work failed", failure.get());
        }
        if (completed.get() != WORKERS
                || retained.size() != 24) {
            throw new AssertionError(
                    "Mutator work incomplete");
        }

        long gcAfter = collectionCount();
        long delta = gcAfter - gcBefore;
        System.out.println("mutatorThreadsCompleted="
                + completed.get());
        System.out.println("allocatedByMutatorsMiB="
                + (WORKERS * (long) LOOPS * BUFFER_BYTES
                        / 1024 / 1024));
        System.out.println("retainedMiB=" + retained.size());
        System.out.println("gcCollectionCountDelta=" + delta);
        System.out.println("workCompleted="
                + (completed.get() == WORKERS));
        System.out.println("gcObserved=" + (delta > 0));
    }
}
```

**Điểm quan trọng khi đọc code:**

- `WORKERS=2`: có 2 mutator threads thực hiện allocation cùng lúc.
- Mỗi thread tạo `120.000` arrays kích thước `4096` byte.
- `allocatedByMutatorsMiB` là **ước lượng số bytes payload được yêu cầu**, được tính theo integer division và **không** bao gồm array header, padding, object metadata, JVM runtime allocation hay chi phí GC; nó **không phải** số liệu đo heap allocation thật.
- `retained` giữ 24 arrays dung lượng 1 MiB; `retainedMiB=24` là cách demo kiểm tra số slot giữ lại, **không phải live-set memory thực đo**.
- `recent` giữ một vòng ring arrays để mô phỏng references thay đổi liên tục; `published` là volatile reference dùng trong fixture.
- `CountDownLatch` cho hai threads bắt đầu gần nhau; Java threads có thể bị scheduler đan xen khác nhau.
- `GarbageCollectorMXBean.getCollectionCount()` cho số lần thu gom mà bean báo cáo; nếu bean trả `-1` thì code bỏ qua. **Không** biết từng pause, từng concurrent phase hoặc thời gian chờ application từ chỉ một count.
- Code không gọi `System.gc()` để ép full GC, tránh một thao tác có thể làm sai kết quả latency.
- Nếu một collector/JDK không kích hoạt GC trong bài chạy ngắn, `gcObserved=false` không có nghĩa collector không tồn tại; tăng workload hoặc giảm heap trong môi trường test thay vì khẳng định cơ chế GC sai.

**Lưu ý:** đây là **test stress cục bộ**, không phải bài benchmark chuẩn để tuyên bố collector nào nhanh hơn. Đừng chạy với heap rất nhỏ trên dịch vụ production, và đừng suy throughput/tail latency từ thời gian test startup ngắn.

### 10.2. Biên dịch/chạy bằng Java 11 API

Lưu tệp là `ConcurrentGcWorkDemo.java`. Để test **G1**, tương thích Java 11 và các JDK hiện đại:

```bash
javac --release 11 -encoding UTF-8 ConcurrentGcWorkDemo.java

java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc=info ConcurrentGcWorkDemo
```

Trên **JDK hiện đại có ZGC**, thực hiện một lần chạy riêng để đối chiếu:

```bash
java -Xms128m -Xmx128m -XX:+UseZGC -Xlog:gc=info ConcurrentGcWorkDemo
```

Trên **JDK/build có Shenandoah**, thực hiện một lần chạy riêng:

```bash
java -Xms128m -Xmx128m -XX:+UseShenandoahGC -Xlog:gc=info ConcurrentGcWorkDemo
```

**Không bật nhiều collectors cùng lúc trên một JVM.** Đây là ba lần chạy **độc lập**, không phải ba flags có thể ghép chung. Nếu JVM báo `Unrecognized VM option` hoặc collector unavailable, hãy xác minh JDK/vendor/platform thay vì tự đổi sang một collector khác và ghi kết quả như thể chạy collector yêu cầu.

### 10.3. Stdout chương trình và GC log phải tách riêng

Trong một lần thử thực tế với **G1 trên JDK hiện đại**, các dòng do **chương trình Java** in:

```text
mutatorThreadsCompleted=2
allocatedByMutatorsMiB=937
retainedMiB=24
gcCollectionCountDelta=16
workCompleted=true
gcObserved=true
```

Số `gcCollectionCountDelta=16` là **kết quả quan sát của lần chạy cụ thể**, không phải output cố định trên mọi máy. Khi chạy với **ZGC**, lần thử cùng fixture có `gcCollectionCountDelta=92`; cả hai mutator threads vẫn hoàn thành. **Không được suy rằng ZGC kém hơn G1 92/16 lần**: các GC beans/cycle definitions/thresholds và heap management không đo cùng một đơn vị công việc hay latency.

Những giá trị ổn định theo code nếu chạy thành công là:

```text
mutatorThreadsCompleted=2
allocatedByMutatorsMiB=937
retainedMiB=24
workCompleted=true
```

Còn `gcObserved` và số lần GC phụ thuộc collector, heap, CPU, JIT optimization và thời điểm chạy. Khi bạn bật `-Xlog:gc=info`, JVM còn in **những dòng log GC riêng**, không thuộc stdout cố định của application fixture.

### 10.4. Kết quả validation thực tế

Mã nguồn đã được kiểm thử bằng:

- `javac --release 11 -encoding UTF-8` → **PASS**.
- G1: **PASS**, có 2 mutators, tạo lượng allocation dự kiến, log nhiều **`Pause Young (G1 Evacuation Pause)`**.
- ZGC trên runtime hiện đại: **PASS**, chương trình kết thúc, GC beans ghi nhận hoạt động trong fixture.
- Shenandoah trên runtime có hỗ trợ: **PASS**, log hiện rõ **`Concurrent marking roots`**, **`Concurrent marking`** và **`Concurrent evacuation`**.
- Các biến thể chạy với `-Xms128m -Xmx128m` và không chỉnh file repository/project; chỉ dùng thư mục test tạm.

**Cảnh báo thực nghiệm:** không dùng số liệu một lần chạy này làm báo cáo hiệu năng; phải warm up, đo lặp lại, dùng workload thực tế, cùng SLA, tài nguyên, version JDK, CPU quotas và heap sizes được ghi rõ.

## 11. Đọc GC logs để nhận ra STW và concurrent phases

Java 11 trở lên có **Unified JVM Logging (JEP 158)** qua `-Xlog:...`. Cách dễ nhất:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC \
     -Xlog:gc=info ConcurrentGcWorkDemo
```

Trên PowerShell/CMD của Windows, không dùng dấu `\` tiếp dòng kiểu Bash; hãy đặt lệnh lên **một dòng**. Lệnh cùng ý nghĩa:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc=info ConcurrentGcWorkDemo
```

Muốn có thông tin chi tiết theo tags/levels trên JVM hỗ trợ:

```bash
java -Xms128m -Xmx128m -XX:+UseG1GC -Xlog:gc*=info ConcurrentGcWorkDemo
```

Lệnh có `gc*=info` có thể in **rất nhiều dòng**, dùng để điều tra cục bộ và cân nhắc ghi vào file có luân chuyển/retention cho production. Cú pháp `-Xlog` được hỗ trợ từ Java 9, tiếp tục hiện hành; tags và các phase names khác nhau theo collector/JDK.

### Nhận diện đúng các dòng

| Log phrase | Ý nghĩa nên hiểu |
| --- | --- |
| `Pause Young ... (G1 Evacuation Pause)` | Ứng dụng đã có **STW young evacuation** |
| `Pause Remark` / `Pause Cleanup` (G1) | Một phase đánh dấu/chuẩn bị cleanup **STW** |
| `Concurrent Mark`, `Concurrent marking` | GC xử lý marking **cùng thời gian với mutators** |
| `Concurrent evacuation`, `Concurrent relocation` | GC di chuyển live objects trong concurrent phase |
| `Allocation Stall` | Mutator có thể không cấp phát tiếp kịp vì GC/memory |
| `Full GC` / `Degenerated GC` | Có thể là đường fallback có pause lớn |
| `GC(n) ... Xms` | Duration của **event log được ghi**, không mặc định là thời gian JVM ngừng toàn bộ |

**Câu hỏi quan trọng:** một dòng `Concurrent marking 120ms` có phải request bị pause 120ms? **Không.** Nó nói concurrent phase kéo dài 120ms, trong khi Java code có thể vẫn chạy. Ngược lại, một dòng `Pause Young 5ms` thường phản ánh STW pause thật và có thể tác động tới request latency.

### Khi collector log không in phase mong đợi

Nếu fixture G1 chỉ tạo Young pauses mà không có Concurrent Mark, đó có thể chỉ là do heap occupancy và kích thước live-set chưa khiến G1 cần concurrent marking trong khoảng thử nghiệm. Đừng đổi tên Young evacuation thành concurrent mark. Muốn nghiên cứu G1 marking, dùng workload giữ nhiều old objects lâu hơn, đủ heap pressure và logging tương ứng; **không cần ép một loạt internal flags lỗi thời** chỉ để thấy đúng keyword.

## 12. JFR và metrics: nhìn GC đồng thời mà không đọc log bằng mắt

Có thể kết hợp GC logs với **JDK Flight Recorder** để phân tích theo timeline:

```bash
jcmd -l
jcmd 12345 JFR.start name=GcStudy settings=profile disk=true maxage=10m maxsize=64m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=GcStudy filename=gc-study.jfr
jcmd 12345 JFR.stop name=GcStudy
```

`12345` chỉ là PID **minh họa**; dùng PID thực tế từ `jcmd -l`. File tương đối được JVM target tạo trong filesystem/working directory mà target thấy; có thể khác thư mục terminal đang chạy jcmd.

Sau khi có file:

```bash
jfr summary gc-study.jfr
jfr print --events jdk.GarbageCollection gc-study.jfr
```

**Không suy rằng JFR chỉ chứa một loại GC event.** Tùy JDK/settings, những sự kiện về GC pauses, phases, allocations, heap summary hoặc concurrent phases có thể khác nhau. Dùng `jfr summary`/`jfr metadata` để xem types thật trong file, rồi dùng `jfr print` hoặc JDK Mission Control để phân tích.

**JFR.dump tạo snapshot, không dừng recording**; `JFR.stop` mới kết thúc. Tùy settings, các event ít chi tiết/không được bật có thể không xuất hiện. File JFR có thể chứa class/method names, host/path và thông tin nhạy cảm; áp dụng quyền truy cập/retention.

### Theo dõi những metric nào?

| Mục tiêu | Metric hoặc nguồn phù hợp | Vì sao |
| --- | --- | --- |
| User latency | P50/P95/P99/P99.9 request duration theo route/operation | SLA nằm ở ứng dụng, không phải log GC |
| GC pause | STW pause duration distribution, max/p99 | Đo điểm JVM tạm dừng mutators |
| Concurrent GC | Số cycles và duration concurrent phases | Nhìn CPU/time consumed đồng thời |
| Allocation pressure | Allocation rate, young/old occupancy, live-set | GC cần theo kịp mức tạo rác |
| Headroom | Heap used/committed/max, free trước/during cycle | Tránh allocation stalls/OOM |
| CPU contention | GC worker CPU + application CPU + cgroup quotas | Concurrent workers cạnh tranh với mutators |
| Fallback | Full/degenerate collections, stalls, evacuation failures | Long-tail latency thường xấu ở các trường hợp hiếm |
| Application throughput | Requests/s, transactions/s, CPU per request | Đánh giá chi phí đổi lấy pause thấp |
| Memory footprint | RSS, native memory, heap committed | JVM dùng cả bộ nhớ ngoài heap |
| Business outcomes | Error rate, timeout/retries/backpressure | GC là một trong nhiều yếu tố ảnh hưởng |

**Không đánh giá chỉ bằng `getCollectionCount()`.** Counter có semantics khác nhau giữa các beans/collectors. Phải ghép với pause times, concurrent phase times, CPU usage và **latency thực của application**.

## 13. Khi nào concurrent GC không giảm latency như kỳ vọng?

### 13.1. Heap quá nhỏ

Mutators tạo rác nhanh trong khi concurrent GC cần thời gian đánh dấu/copy. Nếu free space cạn trước khi hoàn thành, application có thể **allocation-stall** hoặc gặp fallback, thậm chí OOM.

**Hướng xử lý:** cấp heap đủ cho **live-set + allocation during concurrent cycle + safety margin**, đo chứ không copy một công thức % cố định từ workload khác.

### 13.2. Thiếu CPU quota

Trong container có CPU quota thấp, GC concurrent threads và application threads tranh cùng số CPU được cấp. Một GC cycle có thể kéo dài, kéo theo pressure lớn hơn dù STW pauses riêng lẻ ngắn.

**Hướng xử lý:** quan sát cgroup CPU throttling, throughput, CPU usage của JVM và heap pressure; điều chỉnh resources/tuning theo benchmark thực, không tự tăng GC threads vô hạn.

### 13.3. Write-heavy reference churn

Application liên tục đổi edges (large maps, caches, intrusive linked structures) làm tăng barrier/remembered-set work. Collector vẫn đúng về semantics nhưng throughput có thể giảm.

**Hướng xử lý:** đo allocation rate, objects lifetime, reference mutation patterns; ưu tiên giảm object churn và cải thiện design khi có bằng chứng, trước khi chỉnh internal barrier flags.

### 13.4. JNI/pinned objects

Một số đường native/foreign API hoặc vùng memory pinned có thể làm di chuyển objects khó hơn. Ảnh hưởng khác nhau theo collector và JDK, có thể gây fallback hoặc tăng pause trong điều kiện nhất định.

**Hướng xử lý:** xác định native/critical sections, kiểm tra GC log, runtime version, các JEP/flags đã được vendor hỗ trợ; tránh mô tả mọi collector có chính sách pinning giống nhau.

### 13.5. Reference processing và class unloading

Soft/weak/phantom references, finalization legacy, class unloading và việc quản lý metadata có chi phí. Một số công việc có thể concurrent; một số vẫn có điểm phối hợp. Không suy rằng “mark và relocation concurrent” đồng nghĩa **mọi công việc GC** cũng không cần pause.

### 13.6. Full GC, degenerated cycle hoặc allocation stall

Đây là những **long-tail outliers**. Một application có 99% pauses tốt nhưng 0.1% fallback dài vẫn có thể vi phạm SLO P99.9. Phải theo dõi số lần fallback, nguyên nhân và context cụ thể.

### 13.7. Overcommit hoặc memory bên ngoài heap

Không dùng `-Xmx` như đại diện cho RSS/cgroup limit. JVM còn native stacks, metaspace, direct buffers, JIT code cache, GC metadata và memory của thư viện native. Heap Xmx chiếm gần toàn memory limit có thể dẫn đến process bị OOM-kill dù GC làm việc đúng.

### 13.8. Compiler/JIT warm-up và ứng dụng khác

Trong benchmark ngắn, JIT compilation, class loading, filesystem caches, scheduler và background services có thể lấn át GC effects. Muốn so collector, phải warm-up đủ và chạy lặp lại trong điều kiện khả so sánh.

## 14. Quy trình đánh giá collector cho ứng dụng thực tế

### Bước 1 — Xác lập SLO

Ví dụ (chỉ minh họa):

- P99 HTTP latency dưới một ngưỡng đã được nhóm xác lập.
- Throughput tối thiểu yêu cầu.
- CPU/cgroup limit và memory limit hữu hạn.
- Tỷ lệ timeout, retry, full GC, allocation stalls chấp nhận được.

Không dùng duy nhất “max GC pause dưới 10ms” làm SLO ứng dụng nếu queueing/I/O còn lớn.

### Bước 2 — Đo baseline trước khi chỉnh

Thu:

- P50/P95/P99/P99.9 latency theo endpoint.
- GC pauses, concurrent phase durations và số fallback.
- Allocation rate, live heap, occupancy, CPU, RSS và cgroup throttling.
- Business error rate và throughput.
- Cấu hình JVM hiện tại, JDK vendor/version, GC flags, container resources.

### Bước 3 — So G1 với collector thích hợp

G1 là điểm khởi đầu hợp lý cho rất nhiều Java 11+ services. Nếu user-facing tail latency bị chi phối bởi G1 pauses và có resource headroom, kiểm thử ZGC/Shenandoah trên **JDK/build đã hỗ trợ**. Không bật experimental collector trên Java 11 chỉ để bắt chước bài blog mới hơn.

### Bước 4 — Cố định workload và resources

Để A/B có ý nghĩa:

- Cùng JDK build hoặc nêu khác biệt nếu tính năng GC bắt buộc phiên bản mới.
- Cùng CPU/memory limits, heap settings, storage/network conditions.
- Cùng allocation workload, live-set, request mix, load shape, retry patterns.
- Warm-up và sampling duration đủ dài.
- Lặp nhiều lần để ước lượng biến động, đặc biệt tail percentiles.

### Bước 5 — So trade-off thay vì một số đơn

Một collector có P99 pauses thấp hơn có thể tốn **CPU nhiều hơn**, giảm throughput hoặc cần heap lớn hơn. Nếu ứng dụng đã CPU-bound, concurrent GC có thể cạnh tranh resources khiến **end-to-end latency** không cải thiện tương ứng.

### Bước 6 — Phát hiện rủi ro khi tăng tải đột biến

Thử allocation spikes và sustained load, không chỉ steady-state trung bình. Theo dõi nếu collector bắt đầu **đuổi không kịp mutators**, dẫn đến stalls/fallback.

### Bước 7 — Tối ưu lần lượt

Thứ tự thực tế:

1. Chọn collector và heap đúng nhu cầu.
2. Đo bottleneck khi chạy tải thật.
3. Tăng memory headroom hoặc CPU khi cần.
4. Giảm allocation churn/reference churn ở code.
5. Chỉ sau đó thử những GC knobs chuyên sâu có tài liệu hiện hành và đo lại.

**Không đổi một lúc hàng chục cờ `-XX`** rồi không biết cờ nào làm tốt/xấu; đặc biệt tránh cờ internal/experimental không còn phù hợp phiên bản JDK.

## 15. Các hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Concurrent = parallel GC workers” | Parallel có thể xảy ra trong STW | Concurrent là **với mutators**, parallel là **giữa GC workers** |
| “G1 concurrent mark nên object relocation cũng concurrent” | G1 evacuates young/mixed regions chủ yếu trong pauses | Tách marking và evacuation |
| “G1 có goal `MaxGCPauseMillis=...` thì không bao giờ vượt” | Goal heuristic, không phải hard SLA | Đo distribution/fallback |
| “ZGC không có STW lần nào” | Vẫn có điểm phối hợp/pause ngắn | Nói phần lớn work concurrent, không zero-pause |
| “ZGC hiện đại vẫn có non-generational mode” | Mode đó đã bị loại từ JDK 24 | Dùng `-XX:+UseZGC` trên JDK hỗ trợ |
| “Cần bật `-XX:+ZGenerational` trên JDK 25” | Flag chuyển tiếp đã obsolete/removed | Không dùng nó như cấu hình hiện hành |
| “Java 11 ở mọi vendor có Shenandoah” | Support/backport tùy distribution | Kiểm tra JDK/build và flags |
| “Concurrent mark 100ms = pause 100ms” | Mutators có thể chạy trong phase | Dựa vào STW pause durations |
| “Chỉ cần số lần GC ít là tốt” | Count khác collector, không đo latency | So pause p99 + application latency + CPU |
| “Headroom thừa là lãng phí chắc chắn” | Concurrent GC cần nơi cho allocations trong khi chạy | Right-size theo live-set/pressure |
| “Thêm GC threads sẽ luôn tốt” | GC workers tranh CPU với app | Đo, không chỉnh theo trực giác |
| “Barriers miễn phí” | Chúng thêm work trên paths đọc/ghi references | So throughput/CPU bên cạnh pause |
| “SATB đồng nghĩa không có floating garbage” | Snapshot giữ object vừa chết có thể qua vòng sau | Đây là trade-off đúng đắn |
| “Full/degenerate GC không thể xuất hiện ở low-latency collector” | Thiếu memory/resources có thể gây fallback | Theo dõi long-tail và stalls |
| “JFR heap event là heap dump” | JFR events không chứa toàn bộ object graph | Phân biệt JFR với heap dump |
| “Chạy benchmark một lần là đủ” | JIT/OS/scheduler nhiễu và tail latency dao động | Warm-up, lặp nhiều lần, đo định lượng |
| “`-Xmx` bằng container RSS” | JVM còn native memory ngoài heap | Theo dõi RSS và memory limit |
| “Không thấy concurrent mark trong GC log nghĩa JVM không hỗ trợ” | Workload có thể chưa kích hoạt phase | Kiểm tra threshold/phase/log level |
| “Collector nào cũng dùng một loại write barrier” | Implementation và generation khác nhau | Học invariant trước, chi tiết theo version |
| “GC pause thấp => request latency thấp” | Request có DB/network/queue/locks | Đo ứng dụng end-to-end |

## 16. Bài tập và lời giải

**Bài 1 — Concurrent vs parallel.** Một GC dùng 8 workers để evacuate objects trong một STW pause. GC đó có concurrent với mutators không? **Không.** Đó là parallel GC work trong khi application dừng.

**Bài 2 — G1.** G1 có concurrent marking không? **Có.** G1 có concurrent evacuation của mọi young/mixed regions trong Java 11 không? **Không**, evacuation chủ yếu nằm trong STW pauses.

**Bài 3 — SATB.** Object B sống lúc đầu marking, sau đó edge tới B bị xóa. Vì sao B có thể bị giữ qua vòng hiện tại? SATB xem B là **live theo snapshot logic**, đảm bảo an toàn khi mutators thay đổi đồ thị.

**Bài 4 — Barriers.** Khi mutator ghi một reference trong khi marking, GC có thể cần làm gì? **Ghi nhớ hoặc xử lý reference cũ/mới** theo invariant của collector để tránh bỏ sót object còn live.

**Bài 5 — Relocation.** Tại sao concurrent GC không thể chỉ copy object A rồi free ngay address cũ? Vì references cũ có thể còn được mutators sử dụng; cần **forwarding/healing/remapping/barriers** và điều kiện an toàn trước reclaim.

**Bài 6 — G1 log.** Dòng `Pause Young (G1 Evacuation Pause) ... 2ms` nói gì? Có **STW pause** khoảng 2ms cho event ấy. Nó không chứng minh service P99 latency đúng 2ms.

**Bài 7 — Concurrent log.** Dòng `Concurrent marking 120ms` có phải request bị stop 120ms? **Không**. Đây là khoảng concurrent phase có thể cùng diễn ra với app.

**Bài 8 — ZGC version.** Trên JDK 25 cần bật `-XX:+ZGenerational` để chọn generational mode không? **Không**; non-generational mode bị loại từ JDK 24, hãy dùng `-XX:+UseZGC` trên JVM hỗ trợ.

**Bài 9 — Shenandoah availability.** Có thể mặc định mọi JDK 11 có `-XX:+UseShenandoahGC` không? **Không**, phụ thuộc vendor/backport.

**Bài 10 — Heap.** Nếu ZGC thường allocation-stall, chỉ giảm `-Xmx` có làm tốt hơn không? **Không mặc định**; cần kiểm tra headroom, allocation rate, live-set, CPU và memory limits.

**Bài 11 — CPU.** Concurrent workers có thể làm ứng dụng chậm dù pause thấp không? **Có**, khi CPU bị cạnh tranh/throttling.

**Bài 12 — Count.** G1 có 16 collections còn ZGC có 92 ở fixture. Collector nào chắc chắn tốt hơn? **Không thể biết** chỉ từ count; phải đo pause/application latency/throughput và hiểu semantics beans.

**Bài 13 — JFR.** Dùng gì để xem phases/pauses cùng request latency? **GC logs, JFR/JMC và metrics/traces**; không chỉ heap size.

**Bài 14 — Full GC.** Low-latency GC có bảo đảm không có fallback dài? **Không**; phải kiểm tra full/degenerate cycles, allocation stalls và failures.

**Bài 15 — Heap memory.** Vì sao `Xmx=4G` không bảo đảm container 4 GiB là đủ? Vì còn metaspace, code cache, stacks, direct/native memory, GC metadata và OS overhead.

**Bài 16 — Java 11.** `javac --release 11` trên JDK mới có chứng minh chương trình đã chạy trên JDK 11 thật? **Chưa**; cần chạy test trên Java 11 runtime nếu đó là cam kết hỗ trợ.

### Checklist QA cuối bài

1. Phân biệt STW, concurrent, parallel và incremental đúng?
2. Có giải thích concurrent marking khi object graph biến đổi?
3. Có biết SATB và barrier đóng vai trò giữ tính đúng đắn?
4. Có phân biệt concurrent mark với concurrent relocation?
5. Có mô tả G1 evacuation là STW, không gọi nó concurrent?
6. Có hiểu ZGC hiện đại là generational-only từ JDK 24?
7. Có xác minh Shenandoah availability theo vendor/JDK?
8. Có nhận diện GC logs có `Pause` và `Concurrent`?
9. Có phân biệt concurrent phase duration với application pause?
10. Có đo headroom, CPU quota, throughput và tail latency?
11. Có kiểm tra allocation stalls, full/degenerate GC và OOM?
12. Có test đúng runtime Java 11 nếu cần, không chỉ `--release 11`?
13. Có tránh các obsolete/experimental flags không còn áp dụng?
14. Có dùng JFR/GC log từ **workload thực tế** để kiểm tra giả thuyết?
15. Có quản lý chi phí logging, recording files và dữ liệu nhạy cảm?

## 17. Tài liệu chính thức và tài liệu hiện hành

- [Oracle Java SE 11 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/11/gctuning/garbage-first-g1-garbage-collector3.html): G1, concurrent marking, SATB, mixed evacuation và STW phases.
- [Oracle Java SE 25 — Garbage-First GC](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): G1 trong JDK hiện đại, pause goals/marking.
- [Oracle Java SE 25 — Available Collectors](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html): chọn G1, ZGC theo mục tiêu latency/throughput.
- [Oracle Java SE 24 — The Z Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): generational-only ZGC và việc loại `ZGenerational`.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+UseG1GC`, `-XX:+UseZGC`, `-XX:+UseShenandoahGC` và các JVM flags còn được hỗ trợ theo build.
- [OpenJDK JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/333): cơ sở ra đời ZGC trên JDK 11.
- [OpenJDK JEP 377 — ZGC: A Scalable Low-Latency GC (Production)](https://openjdk.org/jeps/377): ZGC production từ Java 15.
- [OpenJDK JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): thế hệ hóa ZGC.
- [OpenJDK JEP 490 — Remove the Non-Generational ZGC Mode](https://openjdk.org/jeps/490): loại mode non-generational trên JDK 24.
- [OpenJDK JEP 379 — Shenandoah: A Low-Pause-Time Garbage Collector (Production)](https://openjdk.org/jeps/379): concurrent evacuation/production Shenandoah.
- [OpenJDK JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): giai đoạn phát triển generational Shenandoah.
- [OpenJDK JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): generational Shenandoah trong JDK hiện đại.
- [Oracle Java SE 11 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): collection count/time và giới hạn của counters.
- [Oracle Java SE 11 — java Command / Unified Logging](https://docs.oracle.com/en/java/javase/11/tools/java.html): `-Xlog:gc` và GC logging trên Java 11.
- [Oracle Java SE 11 — jcmd](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html): chẩn đoán JVM đang chạy.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR có sẵn trong OpenJDK 11+.
- [JDK Mission Control project](https://openjdk.org/projects/jmc/): phân tích JFR, thread, memory, GC và runtime events.

**Kết luận:** **concurrent marking** là xác định live objects trong lúc mutators vẫn thay đổi graph; **concurrent relocation** là di chuyển objects trong lúc mutators tiếp tục truy cập, cần barriers và forwarding để duy trì tính đúng đắn. **G1 có marking concurrent nhưng evacuation thường STW; ZGC và Shenandoah chuyển phần lớn marking/relocation sang concurrent phases.** Điều đó đổi pause latency lấy CPU/barrier/memory headroom, **không phải lời hứa zero pause hoặc real-time**. Hãy đọc `Pause` vs `Concurrent` trong GC logs, đối chiếu JFR với P99 latency và test đúng JDK/workload để chọn GC phù hợp.