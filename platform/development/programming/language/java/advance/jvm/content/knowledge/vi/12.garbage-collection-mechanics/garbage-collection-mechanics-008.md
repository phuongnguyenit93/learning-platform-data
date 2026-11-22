# Tốc độ cấp phát, lượng dữ liệu còn sống và khoảng trống cần cho GC

Một ứng dụng Java có thể tạo **rất nhiều objects mỗi giây** nhưng vẫn chạy ổn định nếu chúng chết nhanh và GC thu hồi được; ngược lại, ứng dụng cấp phát khá ít vẫn có thể gặp `OutOfMemoryError` nếu phần lớn objects được **giữ sống lâu dài**. Một hiện tượng thứ ba là Java heap còn có vẻ “dư” ở mức tổng số byte, nhưng collector **không còn đủ khoảng trống phù hợp để di chuyển objects đang sống** trong một collection.

Ba biến số này cần được đọc riêng:

1. **Allocation rate** – tốc độ cấp phát: mỗi giây application tạo ra bao nhiêu bytes/objects trên heap.
2. **Live set / retained live data** – lượng dữ liệu còn sống: có bao nhiêu bytes thực sự phải bảo toàn theo reachability tại mốc collection hoặc sau GC.
3. **Free-space headroom / evacuation space** – dung lượng trống hữu dụng: collector còn bao nhiêu không gian để tiếp tục cấp phát, chứa survivors/promoted objects, hoàn thành concurrent cycles hoặc xử lý biến động tải.

Bài đặt trong bối cảnh **Java 17, HotSpot và G1** để giải thích các hệ quả trong thực hành. Những công thức đơn giản được ghi rõ là **mô hình ước lượng**, không phải đẳng thức JVMS cho mọi garbage collector. Các thuật ngữ cụ thể như *to-space exhausted*, *mixed collection*, *reserve percent* và *adaptive IHOP* thuộc chiến lược G1 của HotSpot, không phải quy tắc bắt buộc cho mọi JVM.

## 1. Cùng là heap dùng nhiều nhưng có thể do ba nguyên nhân khác nhau

Giả sử hai ứng dụng đều có `-Xmx1g` và báo heap used quanh 700 MiB tại một thời điểm:

| Đặc điểm | Ứng dụng A | Ứng dụng B |
| --- | --- | --- |
| Allocation rate | 500 MiB/giây | 20 MiB/giây |
| Objects sống qua GC | Ít; phần lớn là dữ liệu request tạm | Nhiều; cache và session giữ lâu |
| Sau GC | Có thể giảm nhanh về 200 MiB | Có thể vẫn ở 670 MiB |
| GC behavior | Young collections thường xuyên | Ít collection hơn nhưng khả năng reclaim thấp |
| Hướng điều tra | Allocation hotspots, object lifetime, throughput | Retention, cache size, GC roots, live-set trend |

Các giá trị trong bảng chỉ là **tình huống giả định**, không phải benchmark. Bên ngoài hai trường hợp còn có thể xuất hiện **headroom pressure**: ví dụ GC đang cần copy 180 MiB surviving objects sang vùng đích nhưng không tìm được đủ destination regions phù hợp, dù dashboard hiển thị một số byte “free” theo cách tổng hợp.

**Điểm then chốt:** không chẩn đoán “GC chậm vì heap used cao” khi chưa biết **cấp phát nhanh đến mức nào**, **đối tượng nào còn sống** và **GC còn khoảng trống hiệu dụng nào để làm việc**.

## 2. Định nghĩa chính xác các chỉ số thường thấy

| Chỉ số | Đơn vị thường dùng | Ý nghĩa |
| --- | --- | --- |
| Allocation rate | MiB/s, GiB/s, objects/s | Lượng dữ liệu mới được cấp phát trong một khoảng thời gian |
| Young allocation rate | MiB/s | Phần allocations do collector tính cho vùng trẻ; phạm vi có thể khác tổng heap allocations |
| Live set | MiB/GiB | Objects cần giữ sống tại pha GC/snapshot xác định |
| Post-GC occupancy | MiB/GiB | Heap used sau một collection; không mặc định bằng live set toàn heap |
| Survival rate | % | Tỷ lệ live bytes trong tập objects/regions được thu gom |
| Promotion rate | MiB/s hoặc MiB/GC | Lượng object/bytes được chuyển sang old region/generation |
| Heap used | Bytes | Metric JVM về dung lượng heap hiện đang ghi nhận sử dụng |
| Heap committed | Bytes | Heap đã cam kết khả năng sử dụng |
| Heap max | Bytes | Giới hạn có thể dùng; thường liên quan `-Xmx` trên HotSpot |
| Free within committed | Bytes | `committed - used` trong một snapshot cùng phạm vi |
| Uncommitted capacity | Bytes | Phần khác biệt giữa max và committed, khi max hữu hạn; không chắc mở rộng được ngay |
| G1 to-space/headroom | Regions/bytes | Destination capacity thực tế phục vụ evacuation/promotion theo policy G1 |
| GC pause duration | ms | Khoảng dừng ứng dụng trong những phase STW cụ thể |
| GC overhead | % CPU hoặc % wall time, tùy nguồn | Phần tài nguyên/thời gian dùng cho GC; phải ghi rõ định nghĩa |

Hai số đo **used** và **committed** của `MemoryUsage` có quan hệ `used <= committed`; nếu `max` hữu hạn thì `committed <= max`. Nhưng không được lấy `max - used` rồi mặc định toàn bộ phần đó là **G1 to-space sẵn dùng ngay**, vì heap regions, evacuation reserves, generation occupancy, humongous objects, fragmentation và chính sách commit tham gia.

### Phân biệt “đang dùng” với “thực sự còn sống”

Giữa hai lần GC, heap có thể chứa objects **đã không còn reachable** nhưng GC chưa kịp reclaim. Chúng góp vào used cho đến khi thích hợp được thu hồi. Ngược lại, một young GC có thể chỉ collection một phần heap; số **post-young-GC heap used** vẫn chứa old objects chưa được full-heap tracing lại ở chu kỳ ấy. Không gọi tùy tiện mọi post-GC heap occupancy là “live bytes toàn JVM chính xác đến từng byte”.

## 3. Allocation rate: chương trình tạo ra bao nhiêu rác mỗi giây?

**Tốc độ cấp phát** phản ánh dữ liệu mới được application tạo trên heap, thường được biểu diễn:

```text
Allocation rate ≈ bytes allocated trong khoảng Δt / Δt

Đơn vị ví dụ:
  600 MiB allocated trong 3 giây -> 200 MiB/giây
```

Tốc độ này chịu tác động từ nhiều nguồn:

- Tạo DTOs, request objects, temporary strings, arrays, JSON trees.
- Boxing, intermediate collections, lambdas/closures có capture, stream pipeline materialization.
- Dữ liệu nén/giải nén, serialization và copies vào buffers.
- Batch transformations, sorting, grouping và object graphs trung gian.
- Logging và formatting có eager construction, kể cả khi output không thật sự cần.
- Workload thực tế: QPS × bytes allocated/request, với nhiều loại request có kích thước khác nhau.

**Allocation cao không tự là memory leak.** Nếu các object chết nhanh, generational GC có thể thu hồi rất hiệu quả. Tuy vậy, quá nhiều allocations vẫn có chi phí: áp lực Eden, GC frequency, write barriers, TLAB refills, copy survivors và CPU dành cho runtime.

### Ví dụ số: allocation rate theo request throughput

Giả sử (chỉ để ước lượng):

- Tải: **2.000 requests/giây**.
- Mỗi request cấp phát trung bình **120 KiB** objects/arrays trên heap.
- Phần lớn sống không quá một request.

Ước lượng:

```text
2.000 requests/s × 120 KiB/request
= 240.000 KiB/s
≈ 234,375 MiB/s
```

Con số này chưa tính background jobs, GC/internal allocations và những biến động theo request payload; cũng chưa nói **bao nhiêu trong 234 MiB/s sẽ sống qua GC**. Phải đo survival/retention tiếp.

Một tuyến xử lý cùng QPS nhưng allocation giảm một nửa có thể giảm young GC pressure, **nhưng không chắc giảm p99 latency** nếu bottleneck chính nằm ở database/I/O hoặc live set vẫn quá lớn. Luôn đo end-to-end.

## 4. Thread Local Allocation Buffer (TLAB) và allocation fast path

HotSpot có thể cho mỗi thread một vùng **Thread Local Allocation Buffer (TLAB)** để nhiều allocations nhỏ diễn ra nhanh bằng cách tăng con trỏ trong buffer. Khi buffer hết chỗ, runtime refill hoặc dùng allocation path khác.

Ý nghĩa:

- Allocation thường **rẻ hơn** thao tác xin memory từ OS cho từng object.
- Allocation bytes vẫn phải được GC quản lý, kể cả khi cấp rất nhanh.
- Thống kê allocation thông qua TLAB/ngoài TLAB có các góc nhìn hạch toán khác nhau; dùng cùng nguồn metric nếu so rate.
- Một phần object có thể bị JIT **scalar replacement/escape analysis**, nên số allocations vật lý quan sát được không nhất thiết bằng số `new` trong source.
- TLAB thuộc nội bộ HotSpot; đừng coi nó là Java API bắt buộc mọi JVM có cùng memory layout.

### Vì sao giảm số `new` chưa chắc là tối ưu đúng?

Một object nhỏ, ngắn hạn có thể được cấp phát rất nhanh, rồi bị GC thu hồi rẻ. Thay nó bằng **object pool thủ công** có thể làm object sống lâu hơn, tăng synchronization contention, giữ graph lớn và **tăng live set**. Ưu tiên **đo allocation hotspots và GC pressure** trước khi tái sử dụng object bằng pooling.

## 5. Live set: cái GC không thể đơn giản bỏ qua

**Live set** là phần object graph được coi cần giữ sống ở một thời điểm/snapshot theo quy tắc collector. Nó có thể bao gồm:

- Objects đang được active requests sử dụng.
- Cache entries, session data, singleton registries.
- Queued tasks, pending futures, retries, event listeners.
- Long-lived maps, object graphs của database/application state.
- ThreadLocal values đang được worker threads giữ.
- Các object còn reachable qua nhiều owners/GC roots.

Live data quan trọng vì collector phải:

1. Xác định liveness qua tracing/marking và metadata.
2. Bảo toàn object fields, references và identity.
3. Khi dùng evacuation/compaction, **copy hoặc di chuyển một phần live bytes** tới vùng đích.
4. Tiếp tục giữ những objects thực sự thuộc tập sống, dù ứng dụng có muốn giữ chúng quá lâu hay không.

Không thể “tune GC” để thu hồi một object vẫn còn **strongly reachable** mà Java code có thể sử dụng hợp lệ. Nếu live set tăng do listener chưa unsubscribe hoặc cache không có bound, vấn đề nằm ở **ownership/lifecycle** chứ không chỉ GC flags.

### Live set lớn tác động tới pause/CPU như thế nào?

- **Marking/scanning:** nhiều live objects và reference edges có thể làm công việc tracing nhiều hơn.
- **Copy/evacuation:** nhiều live bytes trong collection set thì phải copy nhiều, tốn bandwidth và destination regions.
- **Old occupancy:** object sống lâu chuyển hoặc nằm ở old regions, làm old regions khó thu hồi.
- **Headroom:** live data chiếm phần dung lượng đáng ra có thể dùng làm vùng đích hoặc khoảng đệm cho allocation trong lúc concurrent marking chạy.
- **Fragmentation/humongous objects:** live data layout có thể khiến collector không có vùng liên tục hoặc đủ regions cho yêu cầu cấp phát cụ thể.

**Không có công thức “GC pause = live bytes / bandwidth” dùng chung**: ngoài copy bytes, còn root scanning, reference processing, synchronization giữa GC workers, card/remembered sets, OS/JIT và CPU competition.

## 6. Tỷ lệ sống (survival rate) và lượng copy

Trong một GC xử lý một collection set, định nghĩa mô hình:

```text
CSet occupancy trước collection  = live bytes + dead bytes
survival rate (mô hình)          = live bytes / occupancy

Giả sử:
  occupancy = 400 MiB
  live      = 40 MiB
  dead      = 360 MiB

survival rate = 40 / 400 = 10%
```

Nếu collector evacuation phải copy gần 40 MiB (bỏ qua chi tiết tối ưu/objects không move), việc reclaim 360 MiB có thể khá có lợi.

Một collection set khác với occupancy 400 MiB nhưng live 360 MiB:

```text
survival rate = 360 / 400 = 90%
dead = 40 MiB
```

Lần này GC phải bảo toàn/có thể copy rất nhiều bytes để thu hồi ít hơn. **Cùng 400 MiB occupancy nhưng GC efficiency khác xa**.

### Tại sao không lấy `heap used trước - heap used sau` làm live set chính xác?

- Collection có thể chỉ xử lý young regions chứ không toàn heap.
- Mutators có thể chạy giữa các mốc đo, đặc biệt trong concurrent GC.
- Promotion, surviving objects, metadata và compaction có thể thay đổi distribution.
- GC log có thể báo region occupancy/evacuation theo định nghĩa collector riêng.
- Live data ở old regions không nhất thiết được rà soát đầy đủ ở mỗi young GC.

Chỉ dùng chênh lệch trước–sau làm **ước lượng reclaim dưới điều kiện ghi rõ**, không gọi nó là tập object thực tế duy nhất của toàn heap.

## 7. Promotion rate: vì sao objects sống lâu tạo áp lực old generation?

Trong generational collection, objects sống qua một hoặc nhiều young GCs có thể được **promote** từ young/survivor sang old, tùy collector, age threshold, survivor capacity và các điều kiện policy.

Mô hình:

```text
Allocation -> Eden
                |
           Young collection
          /              \
     chết/reclaim       sống/copy
                          |
                    survivor / age
                          |
                    promote to old
                          |
                  old occupancy tăng
```

**Promotion rate** đo lượng dữ liệu chuyển sang old trong một khoảng thời gian hoặc mỗi collection. Nó khác allocation rate:

- 500 MiB/s allocation có thể chỉ promote vài MiB/s nếu phần lớn objects chết nhanh.
- 50 MiB/s allocation có thể promote đáng kể nếu dữ liệu giữ xuyên nhiều requests.
- Một spike promotion ngắn chưa chắc leak; có thể là batch/cached warm-up.
- Promotion tăng liên tục cùng old occupancy sau collection tăng có thể báo cần điều tra retained graph hoặc collector capacity.

### Survivor capacity và premature promotion

Nếu survivor space/regions không đủ, một số objects có thể được đưa lên old sớm hơn tuổi thọ thiết kế lý tưởng của collector. Điều này làm **old occupancy tăng nhanh**, dù nhiều object sớm chết ở old. Khi đó GC phải tổ chức thêm marking/mixed collections để thu hồi old garbage.

Không có quy tắc “mọi object phải sống đúng N young GCs mới promotion”: age threshold/regions đều có tính động và thay đổi theo flags/workload.

## 8. Free space, committed và max là ba lớp giới hạn khác nhau

Một số liệu Java heap có thể có:

```text
Heap max       = 2048 MiB
Heap committed = 1536 MiB
Heap used      = 1200 MiB

Trong cùng snapshot:
  committed - used = 336 MiB
  max - committed  = 512 MiB
  max - used       = 848 MiB
```

Nhưng **848 MiB không tự bằng “space available for G1 evacuation”**.

- `committed - used` là phần heap chưa used trong mức committed; nó có thể phân bố ở regions/segments với chức năng khác nhau.
- `max - committed` là khả năng mở rộng **theo metric**, không bảo đảm luôn commit thêm ngay vì OS/container physical/native budget hoặc GC decisions.
- `max - used` là mức chênh lệch tổng hợp, không mô tả fragmentation, pinned/humongous regions hay reservation policy.
- G1 chọn **destination regions/to-space** dựa trên cấu trúc regions và policy. Cần đủ free regions để copy survivors/promoted objects thuộc CSet.
- Collector còn phải duy trì **headroom cho allocations xảy ra trong khi concurrent marking hoặc background reclamation chưa xong**.

### Vì sao heap có “free” vẫn không cấp phát được object?

Một collector có thể không tìm được **liên tục hoặc đúng loại vùng** đủ chứa một object; hoặc phải giữ những regions làm GC reserve; hoặc đang chịu **to-space exhaustion** khi copy những live objects. Tương tự, JVM có thể gặp allocation failure và thử GC/heap expansion trước khi báo OOME.

**Đừng đồng nhất** “heap used thấp hơn max” với “GC chắc chắn thành công trong một pause tiếp theo”.

## 9. Headroom: khoảng đệm mà GC cần để tiếp tục tiến triển

**Headroom** là dung lượng khả dụng hoặc được dự phòng giúp collector xử lý tình huống **trong lúc garbage vẫn chưa được reclaim**. Với relocating collector, nó có hai vai trò lớn:

1. **Mutator allocation headroom:** application vẫn tạo objects mới giữa các collections/trong concurrent phases.
2. **Evacuation/relocation headroom:** cần destination memory cho những live objects được copy/promote, trước khi source regions có thể được reclaim an toàn.

Mô hình ngân sách cực giản:

```text
Giả sử (minh họa):
  H = tổng heap capacity phù hợp
  L = occupied live data sau collection
  G = lượng allocation mới cần chịu trong một khoảng chờ GC
  E = yêu cầu destination/to-space + dự phòng GC
  M = safety margin

Muốn tránh pressure trong khoảng ấy:
  H phải đủ cho L + G + E + M
```

**Không dùng như điều kiện cần-đủ JVMS.** Các khoản có thể chồng lấn theo pha GC, một phần source heap được tái sử dụng, collectors có policy khác nhau, và `L`/`G` không nhất thiết đo cùng mốc. Công thức hữu ích để **nhớ các loại nhu cầu** nhưng không phải bộ tính heap size tự động.

### Minh họa to-space

```text
Trước evacuation:
  Region R0 (CSet) [live A B C + dead objects]
  Region R1 (CSet) [live D E + dead objects]
  Region R2 (free)
  Region R3 (free)
  Region R4 (old, ngoài CSet)

GC copy A,B,C,D,E sang R2,R3 (khi đủ chỗ).
Sau đó R0,R1 trở thành free và có thể tái sử dụng.

Nếu R2,R3 không đủ destination cho live data,
việc reclaim R0,R1 có thể không diễn ra trọn kế hoạch.
```

Trong trường hợp nguồn và đích chồng chéo bất hợp lý hoặc không còn free regions phù hợp, collector phải có kế hoạch fallback chứ không được đè object đang sống.

### G1 và `-XX:G1ReservePercent`

Trên HotSpot G1, `-XX:G1ReservePercent` là một tỷ lệ heap được **dự phòng như một false ceiling** để giảm rủi ro promotion/evacuation failure. Ví dụ thiết lập tùy mục đích:

```bash
java -Xms512m -Xmx2g -XX:+UseG1GC -XX:G1ReservePercent=15 -jar app.jar
```

`app.jar` là tên minh họa; lệnh chỉ hợp lệ nếu bạn có ứng dụng JAR tương ứng. **Không hiểu 15% là một vùng RAM vật lý cố định khóa riêng và không bao giờ được dùng.** Đây là **GC policy reserve** trong phần heap mà HotSpot quản lý; tác dụng, default và quan hệ tới adaptive IHOP/young sizing phụ thuộc JDK build.

**Không chỉnh reserve đơn độc theo một quy tắc máy móc.** Tăng reserve có thể giảm khả năng eviction/to-space exhaustion trong một workload, nhưng nó giảm effective heap capacity dành cho application và có thể đòi điều chỉnh total heap budget. Cần xem GC logs và benchmark.

## 10. G1 Java 17: tốc độ cấp phát quyết định nhịp young GC

G1 chia heap thành regions, dùng các young/old/survivor regions theo policy. Một chuỗi hoạt động có thể là:

1. Application allocation tạo objects, phần lớn vào Eden/young regions; có những trường hợp khác như humongous allocations.
2. Khi young collection được kích hoạt, G1 chọn collection set, root scan/remembered-set processing và **evacuate live objects** sang survivor/old destinations trong STW pause.
3. Source regions được reclaim; application tiếp tục allocation.
4. Old occupancy/projections tăng khiến G1 khởi động **concurrent marking** để chuẩn bị reclaim old regions.
5. Sau marking, **mixed collections** có thể thu hồi selected old regions cùng young collections.

Với allocation rate cao, Eden/young capacity có thể được dùng hết nhanh hơn → young GC có thể xảy ra thường xuyên hơn. Đây là xu hướng chứ **không phải công thức 1:1**: G1 thích nghi young-generation sizing, pause goals, GC causes và space availability.

### Mối quan hệ giữa Eden size, allocation rate và chu kỳ GC

Ước lượng rất thô trong một đoạn workload ổn định:

```text
Thời gian lấp đầy một budget Eden tương đương
≈ budget có thể cấp phát trong young / allocation rate

Ví dụ:
  budget hữu dụng ≈ 240 MiB
  allocation rate ≈ 120 MiB/s
  thời gian ≈ 2 s
```

**Đây không phải dự báo thời gian Young GC chính xác.** Có TLABs, humongous allocations, survivor occupancy, young sizing, pretenuring/other allocation paths và GC triggers khác. Nếu log thực tế cho thấy 0,5 s giữa young GCs, đừng “sửa số liệu” để khớp công thức; hãy điều tra nguyên nhân thật.

## 11. G1 concurrent marking: cần hoàn thành trước khi old đầy

Một điều G1 cần tránh: old regions tiếp tục tăng vì promotion/allocation, nhưng **concurrent marking chưa hoàn thành đủ sớm** để mixed collections thu hồi vùng old không còn live.

Khi quá trình chuẩn bị old-space reclamation chậm hơn nhịp tăng occupancy:

- Những young collections vẫn có thể xảy ra trong lúc concurrent marking đang chạy.
- Old occupancy có thể tiếp tục tăng qua promotion/humongous allocations.
- Khoảng trống cho evacuation/to-space và allocation mới thu hẹp.
- Nếu marking/reclamation không bắt kịp, có thể phát sinh **evacuation failure/to-space exhausted**, Full GC và trong tình huống nặng là OOME.

G1 sử dụng cơ chế **Initiating Heap Occupancy Percent (IHOP)** và có thể tự thích nghi ngưỡng bắt đầu marking dựa vào dự báo. Điều quan trọng là **mark sớm đủ để GC hoàn thành và bắt đầu reclaim old regions trước khi hết headroom**, chứ không phải cứ giảm một flag tới mức rất thấp là tốt.

### Liveness trong G1 Concurrent Marking không luôn là liveness “ngay lúc này”

G1 có sử dụng **Snapshot-At-The-Beginning (SATB)** cho concurrent marking. Object còn live ở đầu snapshot có thể được coi live trong marking cycle dù về sau đã không còn strongly reachable. Vì vậy:

- Phép đếm liveness trong một cycle có thể mang tính **conservative**.
- Một số objects chết sau snapshot có thể chỉ reclaim hiệu quả ở cycle về sau.
- Heap occupancy không giảm ngay khi code bỏ reference.
- “Object vừa bị dereference” không đồng nghĩa “G1 sẽ lập tức trả toàn bộ memory cho allocator”.

Đây là một lý do phải so **trends qua nhiều cycles**, không chỉ một con số sau đúng một marking phase.

## 12. Evacuation failure, to-space exhaustion và Full GC

Theo tài liệu G1 Java 17, khi collection giữ sống nhiều bytes đến mức **không tìm đủ destination space để copy**, G1 có thể gặp evacuation failure. Collector duy trì tính đúng bằng cách xử lý objects đã move và những objects chưa move theo cơ chế fallback; GC phase có thể tốn thêm thời gian.

Nếu application vẫn không có đủ headroom để tiếp tục cho đến khi reclaim old space thành công, G1 có thể phải dùng **Full GC, in-place compaction**, thường đắt hơn những young/mixed collections thông thường.

Các dấu hiệu trong GC logs tùy JDK build:

- `to-space exhausted` hoặc dấu hiệu evacuation failure.
- `Pause Full (Allocation Failure)` / Full GC variants.
- Old regions tăng nhanh, free regions giảm, young/mixed collections dày.
- Concurrent marking kéo dài so với tốc độ old occupancy tăng.
- Humongous regions nhiều, fragmentation/region pressure.

**Không suy rằng cứ thấy Full GC là Java heap leak.** Full GC có thể do retained live set lớn, allocation spikes, thiếu to-space, concurrent marking không kịp hoặc humongous allocations; cũng có thể là `System.gc()`/diagnostic action theo cấu hình. Cần xem **GC cause và timeline**.

### Humongous objects tạo áp lực khác bình thường

Trong G1, objects có kích thước lớn theo ngưỡng region size được xử lý đặc biệt dưới dạng **humongous objects/regions**. Chúng có thể chiếm nhiều regions liên tiếp và gây khó khăn cho region utilization, không nhất thiết theo đường young object thông thường.

- Allocation một array lớn có thể tiêu tốn một số nguyên regions, còn phần cuối chưa dùng vẫn không trở thành vùng tự do chung ngay.
- Nhiều humongous objects có thể làm old occupancy cao và tạo fragmentation theo regions.
- G1 có thể cần khởi động marking hoặc có các cơ chế reclaim đặc biệt tùy version.
- Điều chỉnh region size để thay ngưỡng humongous phải dựa trên **histogram kích thước objects và GC log thực tế**, không phải giải pháp mặc định.

## 13. Một bài toán số: allocation, live bytes và destination pressure

Giả sử (tất cả số đều minh họa):

- Một vùng collection chứa **300 MiB allocated**.
- Trong đó **30 MiB live** và **270 MiB dead**.
- Trước evacuation có **80 MiB destination capacity** theo giả định.

Ở đây GC có thể cần copy khoảng 30 MiB và vùng đích 80 MiB **có vẻ đủ** trong mô hình đơn giản. Sau evacuation, nó có thể reclaim 300 MiB source regions và còn lại khoảng 50 MiB destination capacity giả định, bỏ qua overhead.

Nếu tỷ lệ sống tăng:

- Collection set vẫn 300 MiB.
- Live data thành **250 MiB**.
- Destination capacity vẫn 80 MiB.

Một evacuating collector **không thể copy 250 MiB sống vào chỉ 80 MiB destination theo mô hình ấy**. Nó phải thay đổi CSet/policy hoặc fallback; với G1, một số dạng evacuation failure/to-space exhaustion có thể xảy ra trong tình huống headroom quá thấp.

**Quan trọng:** ví dụ này không phải công thức exact về G1 to-space vì collector có thể tái dùng regions, cập nhật schedule, mixed CSet và các vùng dự phòng khác. Nó minh họa **vì sao live bytes và destination capacity phải được xét cùng nhau**.

### Tập dữ liệu giống nhau, nhu cầu copy khác nhau

```text
Case A:
  CSet occupied  = 300 MiB
  live           = 30 MiB
  dead/reclaim   = 270 MiB
  survival       = 10%

Case B:
  CSet occupied  = 300 MiB
  live           = 250 MiB
  dead/reclaim   = 50 MiB
  survival       ≈ 83,33%
```

Allocation rate của application thậm chí có thể bằng nhau ở hai cases; khác biệt sống sót mới tạo độ khó GC khác hẳn.

## 14. Chương trình Java 17: tính các con số mô hình một cách xác định

Tạo file **`GcBudgetMath.java`**:

```java
public class GcBudgetMath {
    private static final long MIB = 1024L * 1024L;

    static long allocatedPerSecond(long requestsPerSecond,
                                   long bytesPerRequest) {
        return requestsPerSecond * bytesPerRequest;
    }

    static long deadBytes(long occupied, long live) {
        if (live < 0 || occupied < live) {
            throw new IllegalArgumentException("invalid liveness");
        }
        return occupied - live;
    }

    public static void main(String[] args) {
        long rateBytes = allocatedPerSecond(1024L, 128L * 1024L);
        long occupied = 300L * MIB;
        long live = 30L * MIB;
        long destination = 80L * MIB;

        System.out.println("rateMiBps=" + rateBytes / MIB);
        System.out.println("occupiedMiB=" + occupied / MIB);
        System.out.println("liveMiB=" + live / MIB);
        System.out.println("deadMiB=" + deadBytes(occupied, live) / MIB);
        System.out.println("survivalPercent=" + live * 100 / occupied);
        System.out.println("destinationEnough=" + (destination >= live));
    }
}
```

```bash
javac --release 17 GcBudgetMath.java
java GcBudgetMath
```

**Stdout chính xác:**

```text
rateMiBps=128
occupiedMiB=300
liveMiB=30
deadMiB=270
survivalPercent=10
destinationEnough=true
```

Giải thích:

- `1024 requests/s × 128 KiB = 128 MiB/s`.
- Phần live 30 MiB trong 300 MiB là 10%, phần dead là 270 MiB.
- `destinationEnough=true` **chỉ là so sánh số trong mô hình**, không phải kết quả kiểm tra G1 thực tế. Runtime còn có region granularity, collector reserve, object alignment, old occupancy, humongous allocations và nhiều trạng thái khác.
- Biểu thức `live * 100 / occupied` là **số nguyên** và sẽ làm tròn xuống nếu tỷ lệ không nguyên. Không dùng nó thay measurement precision cho GC metrics thực.

## 15. Chương trình Java 17: allocation churn không đồng nghĩa retention leak

Tạo file **`AllocationChurnDemo.java`**:

```java
public class AllocationChurnDemo {
    static volatile Object sink;

    public static void main(String[] args) {
        final int count = 4000;
        final int bytesPerAllocation = 32 * 1024;

        for (int i = 0; i < count; i++) {
            byte[] block = new byte[bytesPerAllocation];
            block[0] = (byte) i;
            sink = block;
        }

        long totalBytes = (long) count * bytesPerAllocation;
        System.out.println("iterations=" + count);
        System.out.println("nominalAllocatedMiB="
                + totalBytes / (1024 * 1024));
        System.out.println("lastBlockLength="
                + ((byte[]) sink).length);
    }
}
```

```bash
javac --release 17 AllocationChurnDemo.java
java AllocationChurnDemo
```

**Stdout của đường chạy bình thường, khi cấp phát thành công:**

```text
iterations=4000
nominalAllocatedMiB=125
lastBlockLength=32768
```

Trong vòng lặp, `sink` chỉ giữ **block mới nhất**; các blocks cũ không còn reachable qua `sink` (trừ những đường giữ sống đặc biệt khác). Vì vậy mã tạo **125 MiB dung lượng array danh nghĩa cộng dồn** nhưng không giữ lại 125 MiB arrays trong một collection thông thường.

**Không coi 125 MiB là kết quả đo allocation profiler chính xác**: object headers, alignment và các optimizations/runtime costs có thể khác, và ứng dụng còn cấp phát nhiều objects khác. `sink` volatile khiến việc publish reference diễn ra thật theo ngữ nghĩa, nhưng **không cam kết có đúng N lần GC** hoặc một cách tối ưu allocation cố định.

### Chạy thử với heap nhỏ và GC logs

Trên HotSpot Java 17:

```bash
java -Xms32m -Xmx64m -XX:+UseG1GC -Xlog:gc AllocationChurnDemo
```

Số collections, GC IDs, regions và pauses trong log **không cố định**; không đưa ra một stdout chung cho các dòng GC. Ba dòng do `System.out.println` trong code vẫn như trên nếu chương trình chạy xong không có OOME/resource failure.

## 16. Chương trình Java 17: giữ sống nhiều dữ liệu có chủ đích

Tạo file **`RetainedDataDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RetainedDataDemo {
    static final List<byte[]> KEEP = new ArrayList<>();

    public static void main(String[] args) {
        for (int i = 0; i < 8; i++) {
            byte[] block = new byte[1024 * 1024];
            block[0] = 1;
            KEEP.add(block);
        }

        System.out.println("retainedEntries=" + KEEP.size());
        System.out.println("retainedNominalMiB="
                + KEEP.size() * 1024 * 1024 / (1024 * 1024));

        KEEP.clear();
        System.out.println("afterClear=" + KEEP.size());
    }
}
```

```bash
javac --release 17 RetainedDataDemo.java
java RetainedDataDemo
```

**Stdout chính xác:**

```text
retainedEntries=8
retainedNominalMiB=8
afterClear=0
```

Trong trường hợp này, static `KEEP` giữ **8 entries** tới khi `clear()` xóa các references. Đây là mô hình retention đơn giản; một real cache có thể giữ hàng triệu entries với graphs lớn hơn nhiều.

**Không suy từ `afterClear=0` rằng GC đã chạy hay RSS phải giảm ngay.** `clear()` chỉ cắt những đường reference từ list; vẫn có thể có references khác và GC có thời điểm làm việc riêng.

### Giữ sống cao không luôn là leak

Nếu 8 MiB này là model data mà ứng dụng cần dùng lại trong toàn bộ vòng đời, giữ chúng là đúng. Vấn đề xảy ra khi retention vượt **business lifecycle hoặc memory budget**, ví dụ cache không có limit, listener không được unregister, `ThreadLocal` giữ request cũ. Cách phân biệt là **ownership + lifecycle + xu hướng post-GC occupancy**, không phải object vẫn còn sau một lần collection.

## 17. Đo heap thật bằng `MemoryMXBean`

Java Management API cung cấp các snapshots của heap:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public class HeapSnapshotDemo {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage();

        System.out.println("usedMiB=" + heap.getUsed() / MIB);
        System.out.println("committedMiB=" + heap.getCommitted() / MIB);
        System.out.println("maxMiB=" +
                (heap.getMax() < 0
                        ? "undefined"
                        : Long.toString(heap.getMax() / MIB)));
    }
}
```

```bash
javac --release 17 HeapSnapshotDemo.java
java -Xms64m -Xmx256m HeapSnapshotDemo
```

**Output có ba dòng nhưng giá trị phụ thuộc JVM/OS/timing**; không có “stdout chính xác chung” về heap used. `MemoryMXBean` cũng **không trả allocation rate** trực tiếp; nó là snapshot occupancy/commit/max, không thay thế profiler hoặc cumulative allocation counters.

Để ước lượng allocation rate bằng cách lấy delta của những **allocation counters có định nghĩa phù hợp**, phải đảm bảo metric thật sự **đếm bytes đã allocated**, không chỉ là used heap snapshot vốn có thể giảm do GC. **Không tính `(used2-used1)/seconds` thành allocation rate**: GC và object reclamation có thể làm chênh lệch âm dù application vẫn allocate nhanh.

## 18. Đo allocation rate, live set và GC pressure bằng công cụ nào?

| Câu hỏi | Quan sát phù hợp | Không nên dùng một cách máy móc |
| --- | --- | --- |
| Allocation nhiều đến từ method nào? | JFR allocation events, allocation profiling (async profiler/YourKit/JMC...) | Chỉ nhìn `-Xmx` |
| Allocation rate theo thời gian? | JFR/GC logs/counters có semantics allocation rõ ràng | `Δ(heap used)/Δt` khi có GC |
| Young collections diễn ra dày không? | `-Xlog:gc`, `jstat -gc` với đúng collector | Lấy tần suất cố định từ mã source |
| Survivors/promotions tăng không? | GC logs về Eden/Survivor/Old; collector-specific counters | Gọi mọi survivor bytes là old allocation |
| Post-GC live set có tăng đều? | Occupancy sau các collections đủ đại diện; heap dump/histogram | Một số used heap bất kỳ trước GC |
| Vì sao objects vẫn sống? | Heap dump, dominator tree, paths to GC roots | Đổ lỗi cho `byte[]` chỉ vì có shallow bytes lớn |
| G1 còn to-space/headroom không? | GC logs về free regions, evacuation failures, heap/region state | `-Xmx - heapUsed` coi là exact to-space |
| Full GC/OOME do gì? | GC cause, full GC timeline, object retention, memory limit | Mặc định “GC quá yếu” |
| Container có đủ tổng memory? | Cgroup memory metrics, RSS/PSS, heap + native budget | `-Xmx` đại diện toàn process |

**JFR (Java Flight Recorder)** hữu ích khi cần liên hệ allocation hotspots với CPU/time và GC events. Recording có chi phí runtime, sampling granularity và event thresholds; một allocation profiling view không nhất thiết bắt mọi allocation vật lý với độ chính xác byte tuyệt đối.

### Quy trình đơn giản khi đo một service Java 17

Đầu tiên, ghi lại:

- `java -version`, JVM vendor/build và GC đang dùng.
- `-Xms`, `-Xmx`, G1 flags liên quan và container memory limit.
- Tải thực: requests/s, concurrency, bytes/request, batch sizes.
- GC logging và metric timestamps theo cùng PID.
- Heap occupancy sau collection, young/old regions, promotion, pauses và percent time in GC.

Đo ít nhất ba giai đoạn: **warm-up**, **steady state** và **peak/burst**. Không lấy một lần khởi động vừa JIT/initialize cache xong làm đại diện cho steady-state.

## 19. Unified GC Logging Java 17: cách đọc nhịp GC

Trên HotSpot:

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Xlog:gc* -jar app.jar
```

Muốn tập trung GC phases/heap với mức chi tiết tùy build:

```bash
java -Xms256m -Xmx1g -XX:+UseG1GC \
  -Xlog:gc*,gc+heap=info,gc+phases=debug \
  -jar app.jar
```

Đây là **lệnh mẫu cho shell hỗ trợ backslash line continuation**; trên Windows PowerShell 5.1 phải viết thành một dòng hoặc dùng cú pháp tiếp dòng của PowerShell. `app.jar` là tên minh họa của một ứng dụng thật, không phải file được tạo sẵn trong bài.

Trong G1 logs, tìm:

- **Young GC cadence:** khoảng thời gian giữa các collections và bytes/regions Eden đã được dùng.
- **Eden/Survivor/Old regions:** vùng nào tăng/giảm sau pauses.
- **Evacuation time:** phases scan/merge heap roots, object copy, reference processing (tên thay theo JDK).
- **Concurrent Start/Remark/Cleanup:** marking có bắt đầu và hoàn thành đủ sớm không.
- **Mixed GC:** old region reclamation có diễn ra và thu hồi đáng kể không.
- **Humongous regions:** vùng bị object rất lớn giữ, có xu hướng tăng hay không.
- **Evacuation Failure / to-space exhausted:** có phải collector thiếu destination memory?
- **Full GC:** lý do/cause và pause duration, sau đó heap reclaim được bao nhiêu.

**Đừng coi một dấu hiệu đơn lẻ là kết luận root cause.** Ví dụ young GC dày có thể do allocation rate cao, young sizing nhỏ, heap pressure hoặc collector policy; cần xem thêm allocation histogram/throughput/live set.

### Dùng `jcmd` và `jstat` đúng bối cảnh

```bash
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jstat -gc <PID> 1000 5
```

`<PID>` là placeholder cho process Java đang chạy đủ lâu. Đơn vị/counters của `jstat` có thể khác collector, và một số fields không áp dụng. Đừng giả định các số `S0U`/`S1U` hoặc `OU` ở các collector hiện đại luôn tương ứng đúng một contiguous memory block theo mô hình Serial GC cổ điển.

## 20. Cách ước lượng memory budget để có headroom

Đặt mục tiêu rõ:

- Peak concurrent requests/batches làm live working set tăng bao nhiêu?
- Allocation rate trong steady state và burst cao nhất là bao nhiêu?
- Young survival rate thay đổi ra sao giữa các loại request?
- Old live occupancy sau marking/mixed cycles là bao nhiêu?
- Tỷ lệ heap cần duy trì làm GC reserve/evacuation space phù hợp?
- Container còn headroom cho **native memory, metaspace, code cache, thread stacks, direct buffers, OS/cgroup accounting** hay không?

Mô hình ngân sách vận hành (không phải phép cộng chính xác của mọi metrics):

```text
Cần có không gian cho:
  - ổn định: live objects còn cần cho ứng dụng
  - biến động: allocation trong lúc collector đang làm việc
  - di chuyển: survivors/promotion/to-space
  - bất định: spikes, humongous objects, fragmentation, reserve
  - ngoài heap: native memory + container headroom
```

Khi đặt `-Xmx` rất sát container limit, dù heap chưa chạm max, process vẫn có thể bị OOMKilled bởi **native/process total memory**. Tăng heap để chữa to-space pressure có thể đòi tăng container budget, giảm native usage hoặc chỉnh đồng thời các memory consumers khác.

### Vì sao tăng heap không luôn làm pause tốt hơn?

Một heap lớn hơn có thể giảm GC frequency vì nhiều allocation headroom, nhưng có thể làm lượng memory cần scan/mark/reclaim của một số phases lớn hơn, tăng native/physical footprint và khiến garbage tồn tại lâu hơn giữa cycles. Kết quả phụ thuộc GC và workload; phải đo **throughput, p95/p99 pauses, footprint** trước–sau, không chỉ nhìn “GC ít đi”.

## 21. Tối ưu allocation rate: các chiến lược ít rủi ro

Trước tiên tìm hot paths có **allocation nhiều mà không cần thiết**:

1. Giảm tạo object trung gian trong serialization/parsing khi đã có API stream/buffer phù hợp.
2. Tránh copy `String`/arrays/collections nhiều lần nếu có thể dùng view hoặc immutable reference an toàn.
3. Trong vòng lặp hot path, tránh boxing/unboxing ngoài ý muốn và các temporary collections có thể thay bằng primitive data structures khi được chứng minh đáng giá.
4. Nếu logging disabled, tránh eager formatting/concatenation gây allocations không cần thiết; dùng parameterized logging phù hợp.
5. Giới hạn batch sizes, ưu tiên streaming/backpressure thay vì đọc toàn bộ dữ liệu vào RAM.
6. Nếu tái sử dụng buffers, định nghĩa rõ ownership/size limit và tránh giữ buffer quá lớn cho workloads nhỏ.
7. Tối ưu theo **allocation bytes/op + CPU + latency + retained heap**, không chỉ giảm số lệnh `new` trong source.
8. Cẩn trọng object pooling: giữ object lâu làm tăng live set, fragment memory hoặc thêm contention.

**Nguyên tắc:** giảm allocation **vô ích**, không nhất thiết giảm mọi allocation ngắn hạn. Young GC được thiết kế để xử lý nhiều object chết nhanh.

## 22. Tối ưu live set và tránh retention leak

Một live set lớn có thể hoàn toàn hợp lệ (ví dụ dữ liệu model đang phục vụ users), nhưng nếu tăng theo thời gian không giới hạn cần kiểm tra:

- Cache không có maximum size/weight/TTL hoặc invalidation.
- Listener/observer đã đăng ký nhưng không unsubscribe.
- `ThreadLocal` giữ request context trong worker thread pool vì thiếu `remove()` trong `finally`.
- Pending tasks/futures/queues/backpressure không có giới hạn.
- Static singleton giữ toàn bộ session, transaction hoặc plugin data.
- References từ long-lived class loader/TCCL/JNI handles giữ class metadata/object graphs.
- Heap dump chỉ ra một object root hoặc path giữ sống có retained size bất thường.

Không ép `System.gc()` để xóa một object còn strongly reachable. Sửa tại **owner của reference path** bằng bounded caching, unsubscribe, cancel/release resources hoặc hoàn tất lifecycle.

### Ví dụ phân biệt allocation spike và retained growth

- **Spike 1:** Service tạo tạm 500 MiB buffer data khi xử lý một batch rồi bỏ hết. Heap used có thể tăng nhanh, GC sau đó reclaim, live set ổn định.
- **Spike 2:** Service thêm mỗi batch một entry 20 MiB vào static cache không eviction. Sau 20 batches, cache đã giữ thêm 400 MiB live data. GC không reclaim entry đó, dù không còn request chạy.
- **Spike 3:** Service giữ đúng 400 MiB state cần thiết suốt phiên làm việc. Đây không phải leak nếu có budget/lifecycle được chấp nhận, nhưng vẫn cần headroom cho GC.

Cả ba có thể trông “heap increased 400–500 MiB” trên dashboard tại một thời điểm, nhưng fix hoàn toàn khác nhau.

## 23. GC frequency, pause time và overhead: đọc cùng nhau

Tăng allocation rate thường làm young collections xuất hiện thường xuyên hơn **nếu capacity và policy tương đương**, nhưng pause duration có thể không tăng tương ứng khi survival rate thấp. Ngược lại, live data lớn trong CSet có thể làm một pause đắt dù young collections không quá dày.

Ví dụ hai profile giả định:

| Metric | Profile X | Profile Y |
| --- | ---: | ---: |
| Allocation rate | 600 MiB/s | 100 MiB/s |
| Young survival ratio | 3% | 60% |
| Young GC frequency | Cao | Có thể thấp hơn |
| Bytes phải copy mỗi collection | Thấp so với occupancy | Cao so với occupancy |
| Risk | CPU/throughput do GC cadence | Pause/to-space pressure và old occupancy |

Kết luận nào về p99 latency cũng cần xem **actual pauses**, thread scheduling và workload. Một collector có thể phải chịu overhead concurrent CPU ngay cả khi số STW pauses nhỏ.

### Little’s Law là gợi ý, không phải phép đo exact live set

Có thể dùng trực giác **bytes in-flight ≈ input rate × average time kept**, tương tự Little’s Law, nếu hệ thống ổn định và units/ownership được định nghĩa:

```text
100 MiB/s object payload
× 2 s average retention
≈ 200 MiB dữ liệu đang in-flight (mô hình)
```

Phép tính này **không phải live heap đo bằng GC**, vì kích thước object graph, duplication, caching, peak concurrency và JVM layout làm con số khác. Nó hữu ích để suy ra nếu request latency tăng gấp đôi mà throughput giữ nguyên, **số dữ liệu đang đồng thời sống** có thể tăng.

## 24. Tình huống chẩn đoán: allocation cao, live set thấp

**Dấu hiệu:** nhiều young GCs nhưng old generation ổn định; post-young-GC occupancy giảm mạnh; Full GC hiếm; CPU GC đáng kể.

**Giả thuyết:** ứng dụng tạo nhiều short-lived intermediates; GC reclaim tốt nhưng phải chạy quá thường xuyên.

**Hướng làm:**

1. Dùng JFR/allocation profiler xác định methods phân bổ nhiều bytes/op.
2. Đối chiếu GC rate với QPS và request types; nhận diện request hay payload gây burst.
3. Tối ưu allocation hot path (giảm temporary objects/copies) hoặc cân nhắc young sizing/heap capacity sau khi có benchmark.
4. Đo lại CPU/throughput, p99 và live set để chắc rằng tối ưu không giữ data lâu hơn.
5. Không tăng heap vô hạn chỉ nhằm tránh một vài young GCs; kiểm tra footprint và latency budget.

## 25. Tình huống chẩn đoán: allocation vừa phải, live set tăng

**Dấu hiệu:** old occupancy tăng qua các cycles, post-GC heap used không về baseline, GC reclaim ratio giảm, cuối cùng heap gần max.

**Giả thuyết:** cache/listener/ThreadLocal/queue giữ những object graphs không còn cần, hoặc legitimate working set đang tăng theo dữ liệu người dùng.

**Hướng làm:**

1. Chụp heap dump/histogram tại mốc phù hợp, đọc retained size và paths to GC roots.
2. So với business lifecycle: object có lẽ phải hết sau request/logout/component close.
3. Nếu leak, cắt reference path từ owner có vòng đời dài hơn.
4. Nếu live data hợp lệ, điều chỉnh retention policy, sharding/batching hoặc capacity budget phù hợp.
5. Tái kiểm tra post-GC occupancy trên workload tương đương sau fix.

**Không kết luận một static map lớn tự động là leak.** Nếu nó là cache có giới hạn và hit rate tốt, lượng memory giữ có thể là purposeful working set.

## 26. Tình huống chẩn đoán: thiếu to-space dù heap chưa báo 100%

**Dấu hiệu:** G1 log có `to-space exhausted`/evacuation failure, old regions cao, mixed collections không kịp, Full GC hoặc pause spikes.

**Giả thuyết:** nhiều survivors cần copy, free regions hiệu dụng không đủ hoặc old marking/reclamation đến quá muộn. Cũng có thể có humongous region pressure.

**Hướng làm:**

1. Đọc **GC cause**, old/young/humongous regions, evacuation/marking timeline.
2. Xác định **live bytes và promotion rate** có tăng không; kiểm tra retained objects bằng heap dump nếu nghi leak.
3. Kiểm tra allocation bursts/humongous allocations và concurrency của workload.
4. Dùng tài liệu đúng JDK/GC để xem `G1ReservePercent`, adaptive IHOP, heap sizing và concurrent marking capacity.
5. Cân nhắc tăng heap/headroom **cùng container limit phù hợp** sau khi xác minh ứng dụng thực sự cần live set ấy.
6. Benchmark lại p99 pauses, throughput, memory footprint; tránh đổi nhiều flags cùng lúc không thể quy nguyên nhân.

Một Full GC có thể giải quyết nhất thời fragmentation và phục hồi headroom, nhưng không sửa được một retained graph tăng vô hạn.

## 27. Những nhầm lẫn cần loại bỏ

| Hiểu sai | Cách hiểu chính xác |
| --- | --- |
| “Allocation rate cao là memory leak” | Allocation có thể là short-lived churn; leak là retention không còn cần |
| “GC càng thường xuyên thì live set càng lớn” | GC frequency còn phụ thuộc rate, young sizing và policy |
| “Heap used là toàn bộ live bytes” | Used còn chứa garbage chưa reclaim; partial collections không đo toàn heap |
| “Sau một young GC, old occupancy là live set exact” | Old regions có objects chưa trace đầy đủ ở mốc đó |
| “Tổng free heap bằng toàn bộ G1 to-space” | G1 dùng regions, reserve, policy và destination constraints |
| “`-Xmx - used` là headroom có thể dùng ngay” | Chưa xét committed, OS limits, fragmentation và GC reserves |
| “Copying collector không cần extra space” | Evacuation cần destination cho live objects |
| “Survival rate cao luôn tốt vì objects còn sống” | Nó làm copy/retention cost cao và reclaim ratio thấp |
| “Promotion luôn là lỗi” | Một phần dữ liệu hợp lệ sống lâu và cần old storage |
| “Tăng `-Xmx` luôn giảm pause” | Có thể giảm frequency nhưng tăng footprint hoặc work per cycle |
| “Tăng reserve luôn tăng throughput” | Reserve giảm usable application capacity và cần benchmark |
| “`System.gc()` giải phóng object còn được cache giữ” | GC không bỏ qua strong reachability |
| “Allocation rate = thay đổi heap used theo giây” | Heap used có thể giảm do GC, không đếm cumulative allocated bytes |
| “Có Full GC chắc chắn leak” | Cần phân tích GC cause, live data, to-space và OS limits |
| “G1 concurrent marking nghĩa object copy hoàn toàn concurrent” | G1 Java 17 evacuates CSet chủ yếu trong STW pauses |
| “Humongous objects giống objects nhỏ trong Eden” | G1 có chính sách special region allocation/reclaim |
| “Đo một snapshot đủ để biết xu hướng” | Cần timeline qua workload/GC cycles tương đương |
| “Collector nhanh nhất là collector có ít GC events nhất” | Cần cả throughput, tail latency, CPU và footprint |

## 28. Checklist thực hành khi chọn cách xử lý GC pressure

Trước khi tune flags, hãy trả lời được:

1. **Allocation rate hiện tại** là bao nhiêu MiB/s và phân bổ theo endpoint/job nào?
2. Workload **steady-state hay burst**? QPS/concurrency và payload sizes có biến động không?
3. **Survival rate/bytes copied** của các collection sets có cao bất thường không?
4. **Promotion rate** và old occupancy đang tăng, ổn định hay giảm?
5. **Post-GC live data** có ổn định sau các chu kỳ tương đương không?
6. Có **heap retention graph** không còn hợp lệ (cache/listener/ThreadLocal/queues)?
7. G1 có **free regions/to-space** đủ cho survivors/promotions không?
8. Concurrent marking bắt đầu **đủ sớm** để mixed collections reclaim old space?
9. Có nhiều **humongous objects**, fragmentation hay to-space exhaustion không?
10. Hiện tượng xảy ra ở JVM heap hay ở **native/container memory** ngoài `-Xmx`?
11. GC time chiếm bao nhiêu % CPU/wall time; **p95/p99 pause** có vi phạm SLO?
12. Có thể giảm **allocation không cần thiết**, giảm retention, giới hạn concurrency trước khi tăng heap?
13. Các flags có được hỗ trợ bởi **JDK 17 build** đang chạy không?
14. Thay đổi đã được **benchmark từng biến** và có plan rollback khi p99/footprint xấu hơn chưa?

## 29. Câu hỏi tự kiểm tra

**Câu 1:** Service A tạo 800 MiB/s nhưng post-GC live set giữ ổn định 200 MiB. Có thể kết luận bị leak?

**Không.** Đây có thể là allocation churn rất cao; cần kiểm tra GC frequency/CPU và allocation hotspots, không khẳng định retained graph tăng.

**Câu 2:** Service B tạo 20 MiB/s nhưng sau mỗi chu kỳ old occupancy lại tăng. Hướng điều tra?

**Retention và promotion**, có thể cache/ThreadLocal/listener hoặc working set hợp lệ tăng; dùng heap dump và owner/lifecycle analysis.

**Câu 3:** 400 MiB CSet có 40 MiB live và 360 MiB dead. Survival rate theo mô hình?

**10%**. Khoảng 40 MiB live phải được bảo toàn; 360 MiB là reclaimable trong mô hình.

**Câu 4:** Heap max 2 GiB, used 1,6 GiB. Có chắc 0,4 GiB là to-space rảnh của G1?

**Không.** Đây chỉ là tổng chênh lệch; phải xem committed, regions, reserve và các constraints khác.

**Câu 5:** Vì sao G1 có thể Full GC sau to-space exhausted?

Collector thiếu destination hoặc không reclaim old space kịp; fallback full-heap compaction có thể được dùng để tạo tiến triển.

**Câu 6:** `G1ReservePercent` có phải reservation RAM vật lý tách riêng ngoài `-Xmx`?

**Không.** Nó là policy reserve/false ceiling liên quan dung lượng heap nhằm giảm nguy cơ to-space/promotion failure.

**Câu 7:** Vì sao concurrent marking có thể chưa reclaim một object vừa trở nên unreachable?

G1 SATB có thể vẫn coi object snapshot-live trong marking cycle đang diễn ra; reclamation có thể xảy ra ở cycle tiếp theo.

**Câu 8:** Hai ứng dụng có allocation rate như nhau nhưng survival 5% và 90%. Evacuation cost có thể khác không?

**Có.** Tập live cần bảo toàn/copy khác đáng kể, ảnh hưởng GC CPU, pause và destination space.

**Câu 9:** Dùng `(heapUsed2 - heapUsed1)/Δt` có đo chính xác allocation rate không?

**Không.** GC có thể reclaim giữa hai lần đọc, nên chênh lệch là occupancy change chứ không phải cumulative allocation.

**Câu 10:** Một heap dump thấy nhiều `byte[]` lớn. Đã chứng minh nơi allocation chúng là lỗi chưa?

**Chưa.** Cần truy path to GC roots/retained owner và xem lifecycle; nơi tạo bytes có thể hợp lý nhưng nơi giữ quá lâu mới là bug.

## 30. Tài liệu tham chiếu

- [Oracle Java SE 17 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): collection phases, SATB marking, mixed collections, regions, evacuation failure và chính sách thu hồi.
- [Oracle Java SE 17 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html): allocation pressure, Full GC, to-space exhaustion, reserve/IHOP và cách chẩn đoán.
- [Oracle Java SE 17 — Introduction to Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/introduction-garbage-collection-tuning.html): throughput, pause goals, allocation/reclamation và các cơ chế GC.
- [Oracle Java SE 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC và lựa chọn collector.
- [Java SE 17 — `MemoryUsage` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html): used, committed, max và init.
- [Java SE 17 — `MemoryMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap usage.
- [Java SE 17 — `ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread diagnostics.
- [Java SE 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`/`-Xmx`, `-Xlog`, `G1ReservePercent` và các VM flags.
- [Java SE 17 — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html) và [`jstat` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): heap/GC runtime diagnostics.
- [Java SE 17 — Flight Recorder API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html): nền tảng thu thập sự kiện runtime và hỗ trợ quan sát allocations/GC.

**Ghi nhớ:** **Allocation rate** giải thích tốc độ heap được tiêu thụ; **live set/survival** giải thích GC phải giữ hoặc copy bao nhiêu dữ liệu; **headroom/to-space** giải thích collector có đủ chỗ để tiếp tục trong khi chưa reclaim được source space hay không. Chỉ khi đo và liên hệ cả ba với **GC phases, old occupancy, promotion, humongous regions, pause/throughput và giới hạn process/container** mới có thể phân biệt allocation churn bình thường, memory retention leak và evacuation pressure.
