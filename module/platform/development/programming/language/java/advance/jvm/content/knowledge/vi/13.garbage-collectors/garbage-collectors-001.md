# Serial GC: cơ chế đơn giản và các môi trường ít tài nguyên

**Serial Garbage Collector (Serial GC)** là bộ thu gom rác của **HotSpot JVM** sử dụng **một GC worker thread** để làm công việc thu gom trong mỗi collection, thay vì huy động nhiều GC workers song song. Khi Serial GC thực hiện những pha thu gom thông thường, **application threads (mutators) bị tạm dừng theo cơ chế stop-the-world (STW)**. Thiết kế này giảm chi phí điều phối GC threads, khá dễ quan sát và có thể phù hợp với chương trình nhỏ, heap nhỏ hoặc tài nguyên CPU hạn chế; đổi lại, nó **không tận dụng nhiều CPU cores để rút ngắn khoảng dừng thu gom**.

Trong HotSpot JDK 17, có thể chọn rõ Serial GC bằng:

```bash
java -XX:+UseSerialGC MyApp
```

`MyApp` ở đây là tên class có `public static void main(String[] args)` đã biên dịch. `-XX:+UseSerialGC` là **HotSpot-specific flag**; đừng giả định mọi JVM khác của Java SE đều hỗ trợ cùng cú pháp.

Bài học giải thích **cơ chế hoạt động**, đặc biệt là **young copying collection**, **old mark-compact**, **GC roots**, **pause**, **promotion**, đồng thời hướng dẫn cách **đo lường, so sánh và chọn môi trường phù hợp**. Ví dụ tương thích **Java 17+** và chỉ coi output của chương trình Java là xác định; số dòng/tần suất/thời gian GC trong log **không được đoán trước**.

## 1. Phân biệt Serial GC với “ứng dụng chạy một thread”

Hai khái niệm thường bị lẫn:

- **Single-threaded garbage collection:** Serial GC dùng **một worker** để xử lý công việc thu gom theo các pha thu gom của nó.
- **Single-threaded application:** chương trình Java chỉ có một application thread.

Chọn Serial GC **không** buộc chương trình Java thành đơn luồng. Chương trình vẫn có thể tạo nhiều threads, dùng executors, networking, đồng bộ hóa hoặc virtual threads nếu JDK hỗ trợ. Điểm khác biệt là **công việc thu gom rác của collector này không được song song hóa qua nhiều GC workers** như Parallel GC.

```text
Ứng dụng đa luồng                     Serial GC pause
──────────────────────┐           ┌───────────────────────
Thread A chạy Java     ├── STW ────┤ Thread A tiếp tục
Thread B chạy Java     │           │ Thread B tiếp tục
Thread C chạy Java     │           │ Thread C tiếp tục
──────────────────────┘           └───────────────────────
                            │
                            ▼
                       Một GC worker
                       quét/copy/compact
```

Đây là **sơ đồ logic**: không trình bày chính xác điểm bắt đầu/kết thúc từng thread và mọi hoạt động VM runtime. JVM còn có những threads quản lý/JIT/VM khác; **“Serial GC dùng một GC thread” không có nghĩa toàn bộ JVM chỉ có đúng một thread OS**.

**Hệ quả chính:** GC không phải trả chi phí phối hợp nhiều GC worker threads cho cùng một collection; nhưng khi heap có nhiều object sống, **một worker phải làm nhiều việc tuần tự**, nên thời gian pause có thể lớn hơn collectors dùng parallel/concurrent work trong cùng workload.

## 2. Serial GC là generational collector

Trong mô hình generational truyền thống của HotSpot Serial GC, Java heap được phân thành **young generation** và **old (tenured) generation**. Giả thuyết thế hệ (generational hypothesis) cho rằng nhiều objects chết khá sớm, còn objects đã sống qua nhiều đợt thu gom có khả năng tiếp tục sống lâu hơn.

```text
Java Heap (mô hình Serial GC)
┌──────────────────────────────────────────┐
│ Young generation                         │
│   Eden ─── nơi cấp phát nhiều object mới  │
│   Survivor S0                            │
│   Survivor S1                            │
├──────────────────────────────────────────┤
│ Old / Tenured generation                 │
│   objects sống dài hơn, promoted objects │
└──────────────────────────────────────────┘

Ngoài Java heap:
  Metaspace, Code Cache, thread stacks,
  direct/native allocations ... (khác heap)
```

Đây là **khái niệm vùng heap**, không phải cam kết về địa chỉ, thứ tự regions hay số byte của mọi JVM. Cách tổ chức ở Serial GC khác G1, ZGC hay Shenandoah.

### Young generation

Young generation thường gồm:

- **Eden:** đa số object mới được tạo ban đầu.
- **Hai survivor spaces:** nguồn/đích để copy objects còn sống qua các đợt young GC.
- **Tenuring/promotion:** những object đã đủ tuổi, hoặc những object không phù hợp để tiếp tục ở survivor space, có thể được chuyển sang old generation theo chính sách của VM.

### Old generation

Old generation nhận objects sống lâu hoặc được chuyển đến từ young generation; khi không đủ không gian hoặc theo các điều kiện VM, **old-generation/full collection** có thể được thực hiện. Với HotSpot Serial collector truyền thống, công việc old collection gắn với **mark-compact**; khác với cách **copying** thường thấy trong young collection.

**Lưu ý:** Eden, survivor, old generation là mô hình runtime của collector. **Biến local nằm trên stack không có nghĩa object mà nó trỏ đến cũng nằm trên stack.** Object được cấp phát trong Java heap, trừ những optimizations loại bỏ allocation vật lý mà vẫn giữ đúng ngữ nghĩa Java.

## 3. Luồng cấp phát và vòng đời của một object

Ví dụ:

```java
byte[] data = new byte[1024];
```

Đây là một dòng Java đặt trong method. Trong cách thực thi điển hình của HotSpot Serial GC:

1. Khi cần object mới, VM tìm không gian cấp phát thích hợp, thường ở **Eden**.
2. Khi young generation không còn đủ chỗ hoặc điều kiện thu gom đến, JVM có thể yêu cầu **young GC**.
3. JVM tạm dừng mutator threads tại các điểm an toàn phù hợp (**STW pause**).
4. Collector xác định objects sống nhờ roots và references liên quan, **copy những young objects cần giữ sống** sang survivor/old space thích hợp.
5. Bộ nhớ Eden chứa objects chết có thể được dùng lại sau collection.
6. Objects sống qua nhiều đợt có thể tăng tuổi và **promote** vào old generation.
7. Khi old generation chịu áp lực hoặc một điều kiện khác phát sinh, VM có thể thực hiện **Full GC/old collection** theo chính sách collector.

Không phải mỗi object phải trải qua **đúng N lần** young GC rồi mới lên old generation. **Tenuring threshold**, survivor occupancy, object sizes và tình trạng bộ nhớ đều ảnh hưởng; object có thể được promote sớm hơn. Không có điều luật Java SE “mọi object sống hơn 15 lần thì chắc chắn promote ở lần thứ 16” bất kể cấu hình.

### TLAB và allocation

HotSpot có thể sử dụng **thread-local allocation buffers (TLABs)** để giúp các application threads cấp phát object nhanh trong young generation. TLAB không có nghĩa GC trở thành đa luồng hay không còn STW; nó chủ yếu giúp **đường cấp phát** khi ứng dụng đang chạy.

Trong thực nghiệm, một object được JIT chứng minh không escape có thể được xử lý bằng escape analysis/scalar replacement, vì vậy câu lệnh `new` ở source **không chứng minh một allocation heap thật đã xảy ra** trên mọi đường chạy.

## 4. Young GC: copying collection hoạt động như thế nào?

Young GC của Serial collector dùng cơ chế **stop-the-world copying scavenger**. Trong một đợt collection, collector bắt đầu từ những roots và các references đi vào young generation, phát hiện objects còn sống trong vùng đang thu gom, rồi copy chúng tới survivor space hoặc promote chúng đến old.

```text
TRƯỚC YOUNG GC

Eden:        [A sống][X chết][B sống][Y chết][Z chết]
Survivor S0: [C sống][W chết]
Survivor S1: [trống]

            stop-the-world
                │
                ▼
GC quét roots + những old-to-young references cần xét.
Đánh dấu logic object trẻ còn reachable; copy sang đích.
                │
                ▼

SAU YOUNG GC (sơ đồ minh họa)

Eden:        [trống / có thể cấp phát lại]
Survivor S0: [trống / sẵn sàng cho chu kỳ khác]
Survivor S1: [A][B][C]  (nếu vừa chỗ, chưa promote)
Old:         [một số object được promote nếu cần]
```

Thực tế thứ tự copy và survivor ages phụ thuộc references, sizes, allocation và policy. Sơ đồ chỉ nhằm giải thích **copying giữ lại live objects và bỏ qua garbage trong vùng nguồn**; không phải mỗi object minh họa đều được copy đúng một lần theo thứ tự A-B-C.

### Vì sao young copying hiệu quả khi nhiều object chết sớm?

Giả sử có 10.000 young objects, nhưng chỉ 150 objects cần giữ sống. Một copying scavenger có thể tập trung công việc di chuyển vào **live objects** thay vì phải copy toàn bộ 10.000 objects. Tất nhiên collector vẫn cần quét roots/references/metadata phù hợp; không kết luận chi phí toàn bộ GC đúng bằng số bytes objects sống.

**Lợi ích** là vùng nguồn có thể được tái sử dụng nhanh; vùng đích nhận objects sống liên tục, giúp giảm fragmentation ở young generation.

### GC roots và old-to-young references

Không chỉ stack locals hay static fields mới giữ young objects sống. Một old-generation object có thể có field trỏ tới young object:

```text
Old object ─────────► Young object
```

Young GC phải tính những **cross-generation references** này; HotSpot có cơ chế card table/remembered information và write barriers để hỗ trợ theo dõi, tránh bắt buộc quét toàn bộ old generation từng lần young collection.

Nếu quên old-to-young edge, GC có thể thu hồi nhầm young object vẫn reachable. Vì vậy **root scanning + các nguồn incoming references thích hợp** là điều kiện đúng đắn, không chỉ “duyệt mỗi Eden”.

### Survivor spaces không phải hai bản sao tồn tại vĩnh viễn

Hai survivor spaces thường luân phiên vai trò **from** và **to** qua các young collection. Một object sống có thể được copy theo đường phù hợp hoặc promote, không phải luôn lưu hai bản sao của object một cách đồng thời từ quan điểm chương trình.

Các Java references của ứng dụng phải được VM cập nhật/duy trì đúng sau khi object di chuyển. Object identity (`==`, `System.identityHashCode` semantics) không vì move vật lý mà biến thành một object Java khác.

## 5. Old generation: mark-compact khác young copying

Khi old-generation/full collection xảy ra, HotSpot Serial Old thực hiện công việc **mark-compact**, thường mô tả qua:

1. **Mark:** tìm các objects cần giữ sống bắt đầu từ roots và đường reference có ý nghĩa.
2. **Tính toán vị trí sau compaction:** xác định nơi sẽ đặt lại các live objects.
3. **Compact/move:** dồn live objects để gom không gian trống thành các vùng thuận lợi cho allocation.
4. **Cập nhật references:** bảo đảm những reference sống vẫn trỏ đúng objects sau di chuyển.

```text
Old trước GC:
[A live][gap][B live][gap][C live][gap][gap]

Old sau mark-compact (minh họa):
[A live][B live][C live][     free space     ]
```

Khác young scavenger chủ yếu copy giữa vùng nguồn/đích, old mark-compact phải xử lý những objects sống và fragmentation trong old generation. **Đó là công việc có thể tốn thời gian hơn khi live set lớn**, nhất là vì Serial sử dụng một GC worker trong stop-the-world pause.

**Không nên áp đặt rằng mọi GC thông thường luôn chạy old compaction.** Young GC diễn ra thường xuyên hơn; old/full collection cần điều kiện thích hợp. Một Full GC có thể liên quan nhiều vùng/generations và có nhiều nguyên nhân kích hoạt, tùy HotSpot version/policy.

### Mark-compact không giống mark-sweep đơn giản

- **Mark-sweep:** đánh dấu live objects rồi thu hồi khoảng trống, có thể để lại các holes rải rác.
- **Mark-compact:** đánh dấu rồi **dồn objects** để giảm fragmentation.
- **Copying:** chuyển live objects qua vùng đích và tái sử dụng vùng nguồn.

Trong mô hình HotSpot Serial GC truyền thống, **young copying và old mark-compact** có ý nghĩa khác nhau. Không nói chung chung rằng “Serial GC chỉ xóa những object chết tại chỗ”.

## 6. Stop-the-world: vì sao Serial GC có pause?

Khi Serial GC chạy các pha collection, application threads phải được **dừng** để collector quan sát/di chuyển objects an toàn. Quá trình này tạo **GC pause**, được tính trong latency của ứng dụng.

```text
Timeline minh họa

App:  ██████████░░░░██████████████░░░░████████
GC:             [YOUNG]                [FULL]
                STW                    STW
```

Trong hình, `░` là khoảng ứng dụng bị dừng do GC, không phải thước đo ms thật. Vì Serial dùng một GC worker, cùng một heap có thể mất thời gian dài hơn collector song song nếu lượng công việc GC lớn, nhưng **không thể định lượng mức chênh chính xác mà không benchmark cùng workload**.

### Pause time và throughput không đồng nghĩa

- **Pause time:** độ dài một đợt ứng dụng phải chờ GC.
- **Throughput:** tỉ lệ thời gian/khả năng xử lý công việc ứng dụng so với overhead GC và những chi phí khác.
- **Latency p95/p99:** độ trễ đuôi của requests; đặc biệt nhạy cảm với những pause lớn.
- **Footprint:** memory và CPU resources collector cùng JVM cần để vận hành.
- **Warm-up:** thời gian VM/JIT tối ưu ứng dụng sau khi bắt đầu.

Serial có thể giảm coordination overhead so với collector nhiều workers, giúp workload nhỏ chạy hiệu quả; nhưng khi heap lớn, live set dày đặc hoặc service cần latency chặt, **STW một worker** thường là bất lợi.

### Serial GC không cho phép “concurrent marking chính” như một collector low-pause

Với mục tiêu low-pause, một số collectors khác làm những giai đoạn GC **concurrently với application threads**, hoặc song song hóa công việc STW. Serial GC không có đặc tính này làm trọng tâm; không nên chọn Serial và kỳ vọng nó giải quyết yêu cầu “pause vài mili-giây cho heap nhiều GB”.

## 7. Vì sao Serial GC hợp máy ít tài nguyên?

Tài liệu HotSpot JDK 17 mô tả Serial collector dùng một GC thread, không có chi phí giao tiếp giữa các workers. Nó phù hợp với **single-processor machines** và có thể hữu ích trên multiprocessors với **small data sets**; tài liệu gợi ý mốc khoảng **100 MB** cho tập dữ liệu nhỏ như một guideline, **không phải hard limit hay ngưỡng tính đúng**.

### Các tình huống có thể cân nhắc

| Môi trường | Vì sao có thể phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Command-line utility nhỏ | Chạy ngắn, heap nhỏ, không cần pause guarantee | Startup, peak heap và tổng thời gian |
| Batch job nhỏ | Không chịu trực tiếp latency của request người dùng | Tổng thời gian và pause dài nhất |
| Container/VM giới hạn khoảng 1 CPU | Ít CPU để tận dụng nhiều GC workers | CPU quota, throttling, heap live set |
| Thiết bị/ứng dụng nhúng tương đối đơn giản | Ưu tiên footprint và ít overhead điều phối | Java runtime/vendor thực sự hỗ trợ |
| Workload object graph nhỏ | Ít live data để scan/copy/compact | Live bytes sau GC, allocation rate |
| Bài học/điều tra GC | Cơ chế dễ quan sát và so sánh | Phân biệt mục tiêu học với production tuning |

**“Ít tài nguyên” không đồng nghĩa mọi container đều nên dùng Serial.** Một container nhỏ nhưng chạy latency-critical API có thể không chịu nổi STW pauses; một container có giới hạn CPU vẫn có collectors khác phù hợp hơn tùy nhu cầu. Hãy đo **heap sau GC**, **pause**, **throughput** và **native memory** trên tải thực tế.

### Khi nào Serial thường không là lựa chọn tốt?

- Service tương tác cần **p99 latency thấp** và phản ứng đều.
- Heap/live set lớn, old-generation collection mất thời gian dài.
- Server có nhiều CPU cores và muốn GC tận dụng song song để rút ngắn pauses.
- Allocation rate cao khiến young collections quá thường xuyên.
- Workload dài ngày liên tục cập nhật lượng lớn object graphs.
- Các JVM công cụ/concurrent collectors hiện đại có performance mục tiêu đã được chứng minh bằng benchmark.

Đây là **dấu hiệu cần kiểm chứng**, không có luật cứng “heap từ 101 MB thì Serial sai”. Một lựa chọn phải dựa trên workload và SLO, không chỉ số core/heap.

## 8. So sánh Serial, Parallel, G1 và low-pause collectors

| Khía cạnh | Serial GC | Parallel GC | G1 GC | ZGC/Shenandoah (khi được hỗ trợ) |
| --- | --- | --- | --- | --- |
| GC workers trong STW collection chính | Một | Nhiều | Có nhiều worker cho một số pha | Tùy thiết kế |
| Concurrent work với application | Không là đặc trưng chính | Không là đặc trưng chính | Có concurrent marking | Được thiết kế cho nhiều công việc concurrent |
| Nhóm mục tiêu | Small heap/ít CPU/đơn giản | Throughput, multiprocessor | Cân bằng throughput và pause targets | Low latency với trade-offs riêng |
| Overhead điều phối GC | Tương đối thấp | Có phối hợp nhiều workers | Có nhiều metadata/phases | Có barriers/concurrent metadata/threads |
| Pause | Có thể dài khi live set lớn | Có thể giảm thời gian work nhờ song song | Hướng tới pause goals theo policy | Mục tiêu giảm pause qua concurrent work |
| Cấu hình HotSpot điển hình | `-XX:+UseSerialGC` | `-XX:+UseParallelGC` | `-XX:+UseG1GC` | `-XX:+UseZGC`, hoặc cấu hình riêng |

Bảng **mô tả xu hướng**, không là cam kết mỗi lần collection sẽ nhanh/chậm hơn một số ms. Đặc biệt cấu hình ZGC và Shenandoah thay đổi theo JDK vendor/release; hãy xem documentation cho đúng runtime.

### Serial so với Parallel GC

Cả hai có thể dùng mô hình generational. Điểm khác biệt nổi bật là **Parallel GC dùng nhiều GC workers** để xử lý công việc collection và thường phù hợp workload tận dụng nhiều cores nhằm cải thiện throughput. Serial giảm coordination overhead nhưng không được lợi từ nhiều workers khi heap lớn.

### Serial so với G1

G1 thiết kế theo regions và concurrent marking kết hợp các pha STW, đặt pause-time goals theo heuristics. Serial đơn giản hơn nhưng không có cơ chế tối ưu mục tiêu pause theo kiểu G1. **Có G1 không có nghĩa pause bằng 0**; vẫn cần quan sát GC log và benchmark.

### Serial so với ZGC/Shenandoah

Các low-pause collectors làm nhiều công việc concurrent, sử dụng thêm barriers/metadata và có các trade-offs khác. **Không được kết luận chúng luôn tốt hơn Serial** trên command-line job vài giây và heap nhỏ; so startup, throughput, native overhead và resource limits trước khi chọn.

## 9. Bật Serial GC và xác minh bằng flags

Cú pháp Java 17 HotSpot:

```bash
javac -encoding UTF-8 SerialGcDemo.java
java -XX:+UseSerialGC SerialGcDemo
```

File `SerialGcDemo.java` được cung cấp đầy đủ tại mục 12. Nếu chưa tạo file, lệnh `javac` chưa thể chạy; hãy tạo đúng file trước.

### Xác minh collector được chọn

```bash
java -XX:+UseSerialGC -Xlog:gc=info -version
```

Trên HotSpot JDK 17, GC logging có thể cho dòng thông báo tương tự:

```text
[info][gc] Using Serial
```

Đây là **mẫu**, không phải stdout chính xác: thời gian/log decorators và wording phụ thuộc phiên bản. `java -version` thường ghi phiên bản lên stderr; không nhầm GC logging với output ứng dụng.

Một cách khác xem flags:

```bash
java -XX:+UseSerialGC -XX:+PrintFlagsFinal -version
```

Lọc các flags như `UseSerialGC`, `UseParallelGC`, `UseG1GC`, `MaxHeapSize`, `NewSize`, `MaxNewSize`. Các mặc định có thể phụ thuộc số cores, heap limit, container awareness và JDK vendor.

**Đừng suy diễn từ phần cứng rằng collector chắc chắn là Serial.** HotSpot có ergonomics, có thể tự chọn collector khác trên máy nhiều cores; startup flags xác minh tốt hơn suy đoán.

## 10. Heap sizing: `-Xms`, `-Xmx` và cấu hình thế hệ

Các tùy chọn thường cần hiểu:

| Option | Mục đích | Ghi chú |
| --- | --- | --- |
| `-Xms<size>` | Initial Java heap size | Ảnh hưởng heap được khởi tạo/commit theo VM |
| `-Xmx<size>` | Maximum Java heap size | Không giới hạn toàn bộ process RSS/native memory |
| `-Xmn<size>` | Đặt kích thước young generation theo option hỗ trợ | Có thể làm thay đổi tính năng sizing policy |
| `-XX:NewRatio=n` | Tỷ lệ old/young theo quy tắc HotSpot liên quan | Tác dụng phụ thuộc sizing constraints |
| `-XX:SurvivorRatio=n` | Điều chỉnh Eden-to-survivor sizing phù hợp | Không cam kết mọi lần survivor occupancy theo tỷ lệ cố định |
| `-XX:MaxTenuringThreshold=n` | Giới hạn tuổi tenuring theo policy | Có thể promote sớm vì survivor pressure |
| `-XX:+UseSerialGC` | Chọn Serial collector | Không đồng nghĩa heap nhỏ |

**Nguyên tắc:** bắt đầu từ sizing hợp lý cho workload; **tránh tùy chỉnh hàng loạt flags generation/survivor** khi chưa có số liệu. JVM có thể tự chọn sizes hợp lý hơn một bộ giá trị copy từ ứng dụng khác.

### Young quá nhỏ

Nếu Eden quá nhỏ so với allocation rate, young collections có thể xảy ra nhiều lần:

```text
App allocation nhanh
  → Eden đầy thường xuyên
  → Young GC STW liên tục
  → pause overhead cộng dồn tăng
```

Tăng young generation có thể giảm tần suất, nhưng các đợt young GC có thể xử lý nhiều live data hơn và yêu cầu trade-off với old generation capacity.

### Old quá nhỏ hoặc live set quá lớn

Nếu objects sống lâu tăng, old generation có thể thiếu capacity và gây old/full collection thường xuyên. Một worker mark-compact lượng lớn live data có thể tạo **pause dài**. Tăng `-Xmx` không tự sửa memory leak: nếu root paths vẫn giữ dữ liệu tăng vô hạn, heap lớn chỉ trì hoãn OOME.

### Heap vs toàn bộ tiến trình

Serial GC có thể có footprint quản lý thấp hơn một số collectors, nhưng process vẫn gồm:

```text
Process memory
  = Java heap
  + Metaspace/class metadata
  + Code Cache/JIT
  + thread stacks
  + direct/native buffers
  + GC/VM structures và libraries
```

Đây là **phân loại**, không phải công thức tính RSS chính xác. Container 256 MB không nên được cấu hình `-Xmx256m` rồi giả định JVM vẫn có đủ chỗ cho mọi native allocations. Cần tính giới hạn OS/container thực tế.

## 11. Cơ chế STW và metrics cần đo

Để quyết định Serial GC phù hợp, hãy thu số liệu thay vì chỉ nhìn flags.

| Metric | Vì sao quan trọng |
| --- | --- |
| **Young GC count/time** | Tần suất và tổng thời gian pause do young collection |
| **Full GC count/time** | Có vấn đề old generation/full collection liên tục không? |
| **Max/p95/p99 pause duration** | Ảnh hưởng user-facing latency hoặc deadline |
| **Heap used after GC** | Live set có tăng đều qua nhiều cycles không? |
| **Allocation rate** | Eden có bị lấp quá nhanh không? |
| **Promoted bytes/tenuring** | Bao nhiêu objects sống lâu được đưa vào old? |
| **Throughput/job completion time** | GC overhead có đáng kể so tổng công việc không? |
| **CPU quota/throttling** | CPU ít có phải nguyên nhân hiệu năng không? |
| **Container memory/RSS** | Có đủ budget cho heap và native allocations không? |

Một lần `System.gc()` không thể thay thế benchmark workload thật: nó có thể gây Full GC ở một số cấu hình nhưng không đại diện cho chu kỳ automatic young collections thông thường.

### Percentiles đáng tin hơn một con số trung bình

Giả sử phần lớn requests mất 10 ms nhưng vài request chịu pause 250 ms. Average latency có thể vẫn trông khá ổn trong khi p99 xấu. Serial GC ở workload thích hợp có thể chấp nhận được; nhưng service có SLO 50 ms cần phân tích pause tail cẩn thận.

**Không tự khẳng định Serial pause luôn >50 ms hay <10 ms.** Pause phụ thuộc heap, live data, references, CPU, workload và JVM. Luôn đo trên deployment target.

## 12. Lab Java 17+: chương trình cấp phát để quan sát Serial GC

Tạo file duy nhất **`SerialGcDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SerialGcDemo {
    private static volatile Object sink;

    public static void main(String[] args) {
        List<byte[]> survivors = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 600; i++) {
            byte[] block = new byte[128 * 1024];
            block[0] = (byte) (i % 100);

            checksum += block[0] & 0xffL;

            // Một số ít mảng được giữ sống xuyên nhiều lượt.
            if (i % 100 == 0) {
                survivors.add(block);
            }

            // Publication khiến mỗi block thực sự escape;
            // không phụ thuộc compiler giữ hay bỏ local allocation.
            sink = block;
        }

        System.out.println("checksum: " + checksum);
        System.out.println("survivors: " + survivors.size());
        System.out.println("one survivor bytes: "
                + survivors.get(0).length);
        System.out.println("done");
    }
}
```

### Biên dịch và chạy

```bash
javac -encoding UTF-8 SerialGcDemo.java
java -XX:+UseSerialGC -Xms32m -Xmx32m SerialGcDemo
```

**Standard output chương trình, khi không bật GC logging:**

```text
checksum: 29700
survivors: 6
one survivor bytes: 131072
done
```

Giải thích giá trị:

- Vòng lặp chạy 600 lần, mỗi `block` dài **128 × 1024 = 131072 bytes**.
- Phần tử đầu nhận các giá trị 0–99, lặp 6 chu kỳ. Tổng `0 + 1 + ... + 99 = 4950` nên `checksum = 6 × 4950 = 29700`.
- Danh sách giữ block tại `i=0,100,200,300,400,500`, vì vậy có đúng **6 survivors** ở cấp độ logic của ứng dụng.
- `sink` là field `volatile` được gán lần lượt cho từng block; nó giúp tránh việc compiler bỏ qua toàn bộ đường cấp phát trong demo, đồng thời làm block mới nhất có reference sống. Nhưng GC/JIT vẫn có các quyết định runtime khác; con số GC cycles không xác định.
- Tổng bytes tạm được yêu cầu cấp phát vượt 32 MiB trong cả lượt chạy, nên JVM sẽ phải tái sử dụng vùng nhớ qua những cơ chế phù hợp. **Không đoán trước young/full GC count** khi chưa đọc logs.
- Trong Java source, `survivors` là list giữ những tham chiếu; nó không chứng minh chính xác 6 blocks phải được promote sang old generation theo một tenuring threshold nhất định.

**Không thêm `System.gc()` để “bảo đảm” log số lần young GC**: manual Full GC làm thay đổi điều cần quan sát, còn mục tiêu ở đây là **automatic GC dưới allocation pressure**.

### Bật GC logging

```bash
java -XX:+UseSerialGC -Xms32m -Xmx32m -Xlog:gc*:info SerialGcDemo
```

Khi bật log, Java output bốn dòng trên vẫn là nội dung do code sinh ra, nhưng console sẽ có **các dòng GC logs xen kẽ**. Số lượng, thời điểm, duration, occupancy và wording của những dòng logs phụ thuộc VM và máy.

Ví dụ hình thức log có thể trông như:

```text
[info][gc] Using Serial
[info][gc,start] GC(...) Pause Young (Allocation Failure)
[info][gc,heap] ... DefNew: ... -> ...
[info][gc] GC(...) Pause Young (Allocation Failure) ...ms
```

Đây là **mô tả minh họa**, không phải stdout chính xác và không phải mẫu bắt buộc cho mọi HotSpot release. Dấu `...` biểu thị dữ liệu không cố định. Với một HotSpot 17 Serial build, bạn có thể thấy những tên vùng/log labels khác nhau như `DefNew` và `Tenured`; hãy dựa vào logs thực tế.

### Quan sát Full GC

Nếu workload hoặc heap policy gây Full GC, có thể thấy dòng thuộc nhóm `Pause Full` hoặc `Full GC` tùy JVM/log configuration. Không nhất thiết sẽ có Full GC trong một lượt lab có đủ heap cho các objects sống; **đừng gọi `System.gc()` rồi trình bày đó là kết quả mặc định của automatic old collection**.

## 13. Quan sát Serial GC với GC logs

Unified logging trên HotSpot JDK 17 có thể cho thêm tags:

```bash
java -XX:+UseSerialGC -Xms32m -Xmx32m -Xlog:gc*,safepoint=info SerialGcDemo
```

Đối với công việc sản xuất, hãy cấu hình file log và vòng đời log phù hợp. Thí nghiệm trên console đơn giản chỉ nhằm học cách đọc các sự kiện.

### Cách đọc một sự kiện GC

Khi log hiển thị một pause:

- **GC ID:** giúp gom các dòng cùng một collection cycle.
- **Cause:** ví dụ `Allocation Failure` khi không cấp phát từ vùng phù hợp.
- **Type:** Young hay Full theo thông điệp collector.
- **Before → after:** heap/generation occupancy thay đổi.
- **Duration:** thời gian event; cần đọc đơn vị thực trong log.
- **Generation details:** có thể giúp xem Eden/Survivor/Old occupancy và promotions.
- **Safepoint timing:** một phần chi phí dừng threads/điểm an toàn, khi bật logging liên quan.

**Đừng trộn các chỉ số:** time trong một dòng young GC không đồng nghĩa toàn bộ end-to-end response latency, nhưng STW pause có thể đóng góp trực tiếp vào latency. Allocation failure là tên GC cause thường thấy, **không tự đồng nghĩa OutOfMemoryError**.

### Mẫu phân tích

```text
Pause Young ... 24M->5M(32M) 4.7ms
```

Đây là **số giả định để luyện đọc**, không phải log được đo. Nó nói rằng trong một event được báo, một số measure về occupied heap thay đổi từ 24 MiB xuống 5 MiB trên capacity 32 MiB và duration 4,7 ms theo reporting context. Không thể suy ra riêng 19 MiB của một class cụ thể được thu hồi; muốn biết object graph phải dùng profiler/heap dump.

## 14. Dùng Java Management API để xem collectors

Bên cạnh GC logs, Java SE cung cấp `java.lang.management.GarbageCollectorMXBean`. Tạo file **`GcBeanDemo.java`**:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public class GcBeanDemo {
    public static void main(String[] args) {
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("collector: " + bean.getName());
            System.out.println("count: " + bean.getCollectionCount());
            System.out.println("time(ms): " + bean.getCollectionTime());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GcBeanDemo.java
java -XX:+UseSerialGC GcBeanDemo
```

**Kết quả phụ thuộc implementation:** với HotSpot Serial collector, names có thể là **`Copy`** và **`MarkSweepCompact`**; collection counts và times phụ thuộc workload. Không bịa một bộ stdout số cố định. Một bean có thể trả `-1` cho metric không được hỗ trợ.

**Ý nghĩa:**

- `getName()` phản ánh tên collector mà JVM expose qua management API.
- `getCollectionCount()` và `getCollectionTime()` là metrics tại thời điểm hỏi.
- Hai metrics không nói object cụ thể nào được reclaim hoặc bao nhiêu reference paths đã thay đổi.
- Những JVM ngoài HotSpot có thể expose các bean names khác; tên beans không phải chuẩn định danh Serial GC portable.

### So sánh với Parallel/G1 qua cùng chương trình

Có thể chạy:

```bash
java -XX:+UseSerialGC -Xms32m -Xmx32m -Xlog:gc=info SerialGcDemo
java -XX:+UseParallelGC -Xms32m -Xmx32m -Xlog:gc=info SerialGcDemo
java -XX:+UseG1GC -Xms32m -Xmx32m -Xlog:gc=info SerialGcDemo
```

**Chỉ dùng nếu JVM và heap sizes hỗ trợ.** Với heap nhỏ, startup options và minimum region constraints của từng collector có thể khác; nếu một lần chạy từ chối flags, ghi nhận đó là kết quả cấu hình không hợp lệ thay vì ép so sánh.

Một chương trình demo nhỏ có thể không bộc lộ ưu thế collectors mạnh trên nhiều cores. So sánh nghiêm túc phải dùng **workload gần production**, nhiều lần đo, sau warm-up thích hợp, cùng CPU/memory limits và phiên bản JVM.

## 15. Java Flight Recorder, jcmd và giám sát ngoài code

### Xác định JVM process

```bash
jcmd -l
```

Khi có PID của tiến trình Java còn chạy:

```bash
jcmd PID VM.flags
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
```

Thay **`PID` bằng mã số tiến trình thật**. `jcmd PID help` để xác minh lệnh được build/runtime hỗ trợ. Các công cụ như heap histogram có thể yêu cầu safepoint và gây overhead/pause; không tùy tiện dùng trên môi trường nhạy cảm.

`GC.heap_info` thường giúp nhìn heap layout hiện tại. `VM.flags` giúp xác minh flag collector, heap size và tùy chọn liên quan thực tế.

### Java Flight Recorder

JFR có thể ghi GC events và thống kê allocation/pauses của tiến trình tương ứng. Nó có thể hữu ích khi muốn đối chiếu những GC pauses với độ trễ ứng dụng. Tuy nhiên tính năng/cấu hình recording, sampling và event names phụ thuộc JDK version và profile.

Không so sánh một số đo trong JFR với output `System.currentTimeMillis()` rồi tự kết luận causal relationship nếu chưa đồng bộ thời gian và kiểm tra event boundaries.

### Native memory và container limits

Serial GC giảm phần overhead liên quan nhiều GC workers, nhưng **không bảo đảm memory process rất nhỏ**. JIT code cache, class metadata, thread stacks, direct buffers và những vùng native khác vẫn tồn tại. Trong container nên giám sát **process RSS/container memory**, không chỉ `MemoryMXBean.getHeapMemoryUsage().getUsed()`.

## 16. Các lỗi/chẩn đoán thường gặp với Serial GC

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng điều tra |
| --- | --- | --- |
| Young GC quá thường xuyên | Eden quá nhỏ, allocation rate cao, nhiều short-lived objects | GC logs, allocation profiling, heap sizing |
| Full GC lặp lại | Live set/old occupancy tăng, promotion pressure, fragmentation hoặc giới hạn heap | After-GC occupancy, root paths, sizing |
| GC pauses kéo dài | Một GC worker xử lý nhiều live objects, large old compaction, CPU chậm | Max pause, live bytes, CPU quota |
| Throughput kém trên máy nhiều cores | Serial không song song hóa GC work | Thử Parallel/G1 với tải tương đương |
| `OutOfMemoryError: Java heap space` | Live set quá lớn hoặc allocation cần heap không đủ | Heap dump, leak analysis, `-Xmx` thực tế |
| RSS cao dù heap nhỏ | Native memory/code cache/metaspace/thread stacks | Process metrics, NMT khi hỗ trợ |
| GC logs không thấy Serial | JVM chưa chạy với flag đúng, JVM khác hoặc command-line không đúng | `java --version`, `VM.flags`, startup logs |
| Container bị throttled | CPU quota/scheduling làm cả app và GC thiếu CPU | cgroup metrics, CPU profiles, observed pauses |
| `System.gc()` tạo Full pause | Explicit request và collector policy | Tìm GC cause; đừng lẫn với automatic workload |
| Không thấy Full GC trong demo | Old generation chưa cần thu gom | Không tự kết luận Serial Old không tồn tại |

### GC có sửa memory leak không?

Không khi có **strong references không chủ ý**. Ví dụ static `List<Object>` giữ 100.000 items mà application không loại bỏ; tracing collector đúng phải giữ objects reachable đó. Tăng heap chỉ trì hoãn vấn đề; **cần xóa đường giữ sống không còn cần** hoặc giới hạn cache.

### Pause dài có luôn do GC không?

Không. JVM còn có lock contention, class loading, JIT compilation, I/O, thread scheduling, safepoint operations và OS throttling. Đối chiếu event timestamps trong GC logs/JFR với request traces trước khi khẳng định nguyên nhân.

## 17. Các hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Serial GC nghĩa là Java app chỉ chạy một thread.” | GC worker là một; mutators vẫn có thể đa luồng |
| “Serial không dừng ứng dụng.” | Cơ chế collection truyền thống của Serial là STW |
| “Serial GC luôn chậm.” | Workload nhỏ có thể lợi vì ít overhead; phải đo |
| “Máy có 8 cores thì Serial tự chạy GC trên cả 8.” | Không; Parallel GC mới dùng nhiều workers cho GC work |
| “Serial chỉ có một heap generation.” | Có young/old theo mô hình generational truyền thống |
| “Young GC chỉ xóa objects, không copy.” | Serial young là copying scavenger |
| “Old GC chỉ mark-sweep để lại holes.” | Serial Old dùng mark-compact |
| “Mọi object được promote sau đúng 15 young collections.” | Threshold/promotion policy có thể khác và promote sớm |
| “GC là việc của một Java application thread bình thường.” | VM GC worker và mutators có vai trò khác nhau |
| “Một young GC chỉ cần quét các young roots.” | Cần xét incoming references từ old và root metadata |
| “Serial không bao giờ phù hợp trên máy nhiều cores.” | Có thể phù hợp khi data set nhỏ; không tận dụng multiple cores cho GC work |
| “Heap dưới 100 MB bắt buộc phải dùng Serial.” | Mốc guideline, không phải giới hạn/cấu hình bắt buộc |
| “Full GC luôn chạy sau mỗi young GC.” | Không; old/full collection phụ thuộc điều kiện |
| “Bật Serial giúp memory leak tự biến mất.” | Các root paths còn giữ objects thì collector phải giữ |
| “`System.gc()` đảm bảo tất cả rác được xóa tức thì.” | Lời gợi ý có hạn chế; đừng dùng làm test GC behavior |
| “`-Xmx` là giới hạn toàn bộ tiến trình.” | Nó giới hạn Java heap, không gồm mọi native memory |
| “Một log young pause nói chính xác p99 latency.” | Phải đối chiếu với request metrics và thời điểm event |
| “Cần tối ưu `-Xmn`/tenuring trước khi đo.” | Ưu tiên baseline và metrics, tránh tuning tùy tiện |

## 18. Bài tập tự kiểm tra (có đáp án)

**Bài 1.** Serial GC có bao nhiêu GC worker cho collection chính?  
**Đáp án:** Một. Điều này không ngăn ứng dụng có nhiều Java threads.

**Bài 2.** Young generation của Serial GC thường gồm các vùng nào?  
**Đáp án:** Eden và hai survivor spaces; survivors luân phiên vai trò source/destination theo quy tắc collection.

**Bài 3.** Một object có thể lên old generation khi nào?  
**Đáp án:** Khi sống qua các collections theo policy hoặc khi survivor space không phù hợp/đủ chỗ, tùy thresholds và VM state; không có số lần cố định áp dụng cho mọi cấu hình.

**Bài 4.** Vì sao copying young collector có thể hiệu quả?  
**Đáp án:** Khi phần lớn young objects đã chết, chỉ cần chuyển những live objects phù hợp, đồng thời tái sử dụng vùng nguồn nhanh.

**Bài 5.** Hai objects trỏ lẫn nhau nhưng không còn đường từ GC roots có nhất thiết sống mãi?  
**Đáp án:** Không. Tracing GC có thể reclaim chu trình unreachable.

**Bài 6.** Serial Old thường áp dụng thuật toán nào trong HotSpot truyền thống?  
**Đáp án:** Mark-compact, giúp giảm fragmentation qua việc dồn live objects.

**Bài 7.** Khi Serial young GC chạy, Java threads còn thực thi application code song song với collection không?  
**Đáp án:** Trong STW pause, mutators bị tạm dừng; JVM GC worker thực hiện thu gom theo cơ chế collector.

**Bài 8.** Vì sao Serial có thể phù hợp với môi trường 1 CPU?  
**Đáp án:** Một GC worker tránh overhead điều phối nhiều workers vốn không thể chạy song song hiệu quả trên CPU hạn chế. Cần vẫn đo pauses/heap.

**Bài 9.** Một service cần latency p99 < 20 ms với heap lớn; có nên chọn Serial chỉ vì “đơn giản”?  
**Đáp án:** Không mặc định. Serial STW một worker có thể không đáp ứng; phải benchmark collector khác theo SLO.

**Bài 10.** `-XX:+UseSerialGC` có chuẩn Java SE cho mọi JVM?  
**Đáp án:** Không. Đây là option HotSpot, phải xác minh runtime thực tế.

**Bài 11.** Trong `SerialGcDemo`, vì sao `checksum` là 29700?  
**Đáp án:** 600 lần gồm sáu chu kỳ 0..99; mỗi chu kỳ tổng 4950.

**Bài 12.** Nếu GC logs có `Allocation Failure` thì chắc chắn JVM ném `OutOfMemoryError`?  
**Đáp án:** Không. Đây có thể là GC cause thông thường khi một vùng không cấp phát tiếp được trước collection.

**Bài 13.** Chỉ số `-Xmx32m` có chứng minh process dưới 32 MB RSS không?  
**Đáp án:** Không; còn metaspace, code cache, stacks và các native allocations khác.

**Bài 14.** Young GC của Serial có thể bỏ qua old-to-young reference không?  
**Đáp án:** Không; phải xét incoming references phù hợp để không thu hồi nhầm object.

**Bài 15.** Old generation used tăng liên tục sau nhiều collections, nên làm gì?  
**Đáp án:** Xem live set, retained size/Paths to GC Roots, queues/cache, allocation/promotions và heap sizing; đừng gọi explicit GC liên tục để che leak.

**Bài 16.** Bật `-XX:+UseSerialGC` có đảm bảo startup nhanh nhất cho mọi app?  
**Đáp án:** Không; JIT, class loading, memory, I/O và workload khác vẫn chi phối. Benchmark mới kết luận được.

**Bài 17.** Vì sao không cần chèn `System.gc()` vào workload để kiểm tra young GC?  
**Đáp án:** Explicit request có thể làm xuất hiện Full GC khác workload tự động, khiến phép quan sát sai mục tiêu.

**Bài 18.** Parallel GC khác Serial ở điểm cốt lõi nào?  
**Đáp án:** Dùng nhiều GC worker threads để thu gom, tận dụng multiprocessor hardware; trade-off coordination/footprint khác.

## 19. Checklist trước khi đưa Serial GC vào production

- [ ] Đã xác nhận **JVM vendor/release** và flag `UseSerialGC` thực sự có hiệu lực.
- [ ] Đã biết ứng dụng chịu **CPU quota** và container memory limit bao nhiêu.
- [ ] Đã đo **live heap sau GC**, allocation rate và peak heap.
- [ ] Đã quan sát young/full GC **count, cause, duration**.
- [ ] Đã kiểm tra **p95/p99 latency** hoặc batch job completion time.
- [ ] Đã ước tính **native memory budget** ngoài `-Xmx`.
- [ ] Đã so Serial với ít nhất một baseline collector phù hợp cùng workload.
- [ ] Đã tránh các flags sizing phức tạp khi chưa có bằng chứng.
- [ ] Đã xác minh root paths nếu heap live set tăng bất thường.
- [ ] Có khả năng rollback/restart sau thay đổi JVM flags.
- [ ] Không xem “đơn luồng” là đồng nghĩa “không tốn CPU”.
- [ ] Không dự đoán số GC cycles từ source code demo.
- [ ] Đã theo dõi throughput lẫn pause time; không chỉ average.
- [ ] Đã đánh giá dữ liệu/threads của application trong giờ cao điểm.

## 20. Tổng kết

**Serial GC** là một collector **generational, stop-the-world, single-worker** của HotSpot: young-generation collection chủ yếu dùng **copying**, còn old-generation collection truyền thống dùng **mark-compact**. Nó giảm chi phí điều phối GC workers và dễ hiểu, có thể hợp với **small heaps, đơn giản, ít CPU, batch/CLI jobs ngắn**; đổi lại, khi lượng live data lớn, GC chỉ có một worker và application threads phải chờ collection hoàn tất.

Không chọn Serial chỉ vì cấu hình nhỏ, cũng không loại bỏ nó chỉ vì máy có nhiều cores. **Đánh giá bằng workload thực, heap live set, GC pauses, CPU/memory budget, throughput và latency SLO.**

### Tài liệu chuẩn

- **Oracle JDK 17 — HotSpot Garbage Collection Tuning Guide, Available Collectors** (Serial/Parallel/G1/ZGC và bối cảnh chọn collector): https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- **Oracle JDK 17 — The java Command** (flags `-XX:+UseSerialGC`, `-Xms`, `-Xmx` và GC options): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle JDK 17 — HotSpot GC Tuning Guide** (các khái niệm generations, sizing, collector ergonomics): https://docs.oracle.com/en/java/javase/17/gctuning/
- **Oracle JDK 17 — jcmd** (đọc VM flags, heap info và commands thực tế): https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- **Java SE 17 — GarbageCollectorMXBean** (management API collection count/time): https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html

Thông tin về Serial GC ở đây áp dụng cho **HotSpot JVM được xác minh qua JDK 17 và những nguyên lý generational liên quan**. JVM khác như GraalVM Native Image có thể có “Serial GC” nhưng **không nhất thiết cùng triển khai/flags/heap layout**, nên không áp các kết luận HotSpot mà không đối chiếu tài liệu riêng.