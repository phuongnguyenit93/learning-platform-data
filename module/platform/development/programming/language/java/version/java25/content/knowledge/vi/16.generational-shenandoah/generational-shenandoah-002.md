# Phân vùng thế hệ, vòng đời đối tượng và vai trò của thu gom đồng thời

> **Chương:** Generational Shenandoah
>
> **Phạm vi:** Java 25 / JDK 25, JEP 521 — Generational Shenandoah đã trở thành **product feature**. Bài học giải thích mô hình young/old theo region, vòng đời và promotion, các chu kỳ thu gom đồng thời, cách bật mode và cách đo hiệu quả trên workload thật.

## 1. Vì sao Shenandoah cần chế độ generational?

Shenandoah là garbage collector đồng thời (concurrent), hướng tới thời gian tạm dừng ngắn. Phần lớn công việc đánh dấu, di chuyển và cập nhật tham chiếu có thể diễn ra trong lúc các Java thread tiếp tục chạy. Tuy nhiên, Shenandoah truyền thống xử lý heap theo một thế hệ: mỗi chu kỳ phải xem xét tập đối tượng sống trên phạm vi heap rộng.

Trong nhiều ứng dụng, phần lớn object được tạo ra chỉ tồn tại trong thời gian ngắn:

- Object DTO, request wrapper, iterator và temporary buffer thường chỉ sống trong một request hoặc một lần xử lý.
- Object cache, cấu hình, session dài hạn hoặc dữ liệu dùng chung có thể tồn tại lâu hơn nhiều.
- Một phần object sống đủ lâu sẽ tiếp tục được tham chiếu qua nhiều chu kỳ thu gom.

Đây là **generational hypothesis**: phần lớn object chết trẻ, còn object đã sống lâu thường có xu hướng tiếp tục sống. Nếu tách object theo tuổi, collector có thể thu gom vùng trẻ thường xuyên hơn mà không phải quét toàn bộ vùng già trong mỗi lần.

Generational Shenandoah kết hợp hai ý tưởng:

1. **Generational collection:** phân chia heap thành các vùng thuộc young generation và old generation, tận dụng khác biệt về vòng đời object.
2. **Concurrent collection:** tiếp tục đánh dấu, evacuation và cập nhật tham chiếu đồng thời với ứng dụng để giữ pause ngắn.

Mục tiêu là tăng throughput bền vững, chịu tải allocation spike tốt hơn và sử dụng bộ nhớ hiệu quả hơn trên các workload phù hợp. Đây là mục tiêu thiết kế, không phải cam kết mọi ứng dụng sẽ nhanh hơn.

## 2. Trạng thái của Generational Shenandoah trong JDK 25

**JEP 521 đưa Generational Shenandoah thành product feature trong JDK 25.**

| Phiên bản | Trạng thái |
| --- | --- |
| JDK 24 | Generational Shenandoah được giới thiệu dưới dạng experimental theo JEP 404. |
| JDK 25 | JEP 521 đưa generational mode thành product feature; không cần bật experimental VM options. |
| JDK 25 mặc định | Shenandoah vẫn chạy mode `satb` single-generation cho tới khi ứng dụng chọn mode `generational`. |

Điều này có nghĩa là:

- Không cần thêm `-XX:+UnlockExperimentalVMOptions` trong JDK 25.
- Phải bật Shenandoah bằng `-XX:+UseShenandoahGC`.
- Phải chọn `-XX:ShenandoahGCMode=generational` nếu muốn dùng generational mode.
- Không được suy luận rằng chỉ nâng cấp lên JDK 25 sẽ tự chuyển Shenandoah sang generational mode.

**Kiểm tra JDK distribution:** Shenandoah không có trong mọi bản phân phối JDK. Oracle JDK không đóng gói Shenandoah; nhiều bản OpenJDK như Red Hat build of OpenJDK, Eclipse Temurin, Amazon Corretto, Azul Zulu hoặc các Linux distribution có thể cung cấp nó tùy build. Hãy xác minh đúng binary mà ứng dụng sẽ chạy trước khi cấu hình.

## 3. Heap theo thế hệ: young, old và region cohorts

Shenandoah quản lý heap bằng các region. Trong generational mode, các region được phân loại theo thế hệ:

- **Young regions:** nơi chứa object mới và object chưa đủ tuổi để chuyển sang old generation.
- **Old regions:** nơi chứa object hoặc region đã sống qua đủ chu kỳ để được xem là lâu dài.
- **Free regions:** vùng trống được giữ để allocation, evacuation và promotion có không gian hoạt động.

Có thể hình dung luồng vòng đời như sau:

~~~mermaid
flowchart TD
    A["Object mới được cấp phát"] --> B["Young regions"]
    B --> C{"Còn được tham chiếu sau young collection?"}
    C -->|Không| D["Thu hồi vùng chứa object chết"]
    C -->|Có| E["Tiếp tục ở young cohort hoặc được promote"]
    E --> F["Old regions"]
    F --> G["Old marking và mixed evacuation"]
    G --> H{"Object còn reachable?"}
    H -->|Không| I["Thu hồi region / reclaim memory"]
    H -->|Có| J["Giữ object trong old generation"]
~~~

**Region cohort** là cách nhìn phù hợp hơn so với việc tưởng tượng Shenandoah có các dải Eden/Survivor liên tục như Serial hoặc Parallel GC. Young và old là tập region có vai trò khác nhau; tuổi và chính sách promotion được collector quản lý. Không nên áp dụng máy móc các tham số như Eden size, SurvivorRatio hoặc NewRatio từ collector khác vào Shenandoah.

### 3.1. Object chết trẻ

Một object mới được cấp phát trong young generation. Nếu không còn reference tới nó trước hoặc trong chu kỳ thu gom young, collector có thể thu hồi vùng chứa object đó. Vì đa số temporary object chết sớm, young collection thường xử lý được nhiều garbage với phạm vi công việc nhỏ hơn một lần thu gom toàn heap.

### 3.2. Object sống qua nhiều chu kỳ

Object vẫn reachable sau nhiều lần young collection có thể được promotion sang old generation. Việc promotion giúp collector giảm số lần phải xử lý object lâu dài trong các chu kỳ young tiếp theo.

Promotion cần có không gian old generation để tiếp nhận dữ liệu sống. Nếu allocation và promotion tăng nhanh, collector phải cân đối dung lượng young/old và reserve cho evacuation; thiếu headroom có thể làm GC phải làm việc gấp hơn hoặc gặp tình huống thu gom suy giảm.

### 3.3. Không phải mọi object đều được phân loại bằng một bộ đếm tuổi đơn giản

Generational Shenandoah quản lý tuổi và promotion ở cấp region/cohort cùng các chính sách nội bộ của collector. Không nên tự suy ra rằng mọi object đều có một tuổi công khai, một ngưỡng promotion cố định hoặc một vùng Survivor giống G1. Những chi tiết này thuộc implementation và có thể thay đổi giữa các JDK.

## 4. Chu kỳ young, old và mixed collection

Generational Shenandoah có thể thực hiện các loại công việc thu gom khác nhau:

| Loại công việc | Phạm vi | Mục tiêu |
| --- | --- | --- |
| **Young collection** | Chủ yếu các young regions | Thu hồi object chết trẻ và xử lý object còn sống trong young generation. |
| **Old marking / old collection work** | Old generation | Xác định object còn reachable và tìm old regions có thể thu hồi. |
| **Mixed collection** | Young regions cùng một tập old regions được chọn | Thu hồi young garbage và từng phần old garbage trong cùng một lần evacuation. |

Một old-generation marking effort có thể chạy đồng thời với ứng dụng. Sau khi xác định vùng old có nhiều garbage, collector chọn một số region làm ứng viên cho các mixed evacuation tiếp theo. Young collection có thể tiếp tục diễn ra trong lúc old-generation work đang tiến hành; collector điều phối các công việc để không phải dừng ứng dụng cho toàn bộ quá trình.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Young as Young GC
    participant Old as Old-generation work
    participant Mixed as Mixed evacuation
    App->>Young: Allocation làm young regions cần thu gom
    Young-->>App: Thu gom young, promotion survivors
    App->>Old: Ứng dụng tiếp tục chạy
    Old-->>App: Concurrent marking old regions
    Old->>Mixed: Chọn old regions có thể reclaim
    App->>Young: Young collection vẫn có thể được kích hoạt
    Mixed-->>App: Evacuate young và một số old regions
    Mixed-->>Old: Xử lý hết ứng viên mixed
    Old-->>App: Tiếp tục old-generation cycle
~~~

Young collection thường có ít live data hơn nên có thể hoàn tất với ít công việc hơn. Mixed collection có thể dài hơn vì phải xử lý thêm old regions. Cả hai vẫn có các pha stop-the-world ngắn để xử lý root hoặc chuyển trạng thái; phần lớn công việc đánh dấu/di chuyển tiếp tục chạy đồng thời.

**Concurrent không có nghĩa là không có pause.** Shenandoah giảm lượng công việc phải làm trong pause, nhưng root scanning, final marking, bắt đầu/kết thúc pha hoặc các tình huống suy giảm vẫn có thể tạo pause. Hãy đo pause thực tế và tail latency của ứng dụng.

## 5. Vai trò của write barrier và card table

Generational collector phải xử lý một tình huống quan trọng: một object ở old generation có thể giữ reference tới object mới ở young generation.

Ví dụ:

~~~java
final class SessionCache {
    private UserRequest latestRequest; // SessionCache sống lâu
}

final class UserRequest {
    byte[] temporaryPayload; // Object mới, có thể chết sớm
}
~~~

Nếu chỉ thu gom young generation, collector vẫn phải biết old object nào đang trỏ tới young object. Nếu bỏ qua reference đó, một object còn sống có thể bị nhận nhầm là garbage.

Generational Shenandoah dùng card marking để theo dõi các vùng old có thể chứa reference tới young:

1. Ứng dụng ghi reference vào field.
2. Write barrier đánh dấu card tương ứng trong old generation.
3. Khi thu gom young, collector quét các card liên quan để tìm reference từ old sang young.
4. Reference được tìm thấy được xem như một phần của root set cho young collection.

~~~mermaid
flowchart LR
    A["Old object"] -->|field reference| B["Young object"]
    A --> C["Old-generation card"]
    C --> D["Write barrier đánh dấu dirty"]
    D --> E["Young collection quét card liên quan"]
    E --> B
~~~

Trong generational mode, các barrier phục vụ đồng thời nhiều invariant:

- Load-reference barrier hỗ trợ đọc reference đúng khi object được evacuation đồng thời.
- SATB pre-write barrier hỗ trợ concurrent marking.
- Card post-write barrier theo dõi reference old-to-young cho young collection.

Card table và write barrier tạo thêm công việc trên đường chạy của ứng dụng. Đây là một phần chi phí của generational collection; lợi ích từ việc thu gom young thường xuyên phải lớn hơn chi phí barrier và các công việc bookkeeping.

## 6. Bật Generational Shenandoah trên JDK 25

Trên một bản JDK có hỗ trợ Shenandoah, khởi động ứng dụng như sau:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xms4g \
  -Xmx4g \
  -Xlog:gc*=info:file=gc.log:time,uptime,level,tags \
  -jar application.jar
~~~

Ý nghĩa:

| Tùy chọn | Tác dụng |
| --- | --- |
| `-XX:+UseShenandoahGC` | Chọn Shenandoah GC. |
| `-XX:ShenandoahGCMode=generational` | Bật generational mode. |
| `-Xms4g` | Heap initial size minh họa. |
| `-Xmx4g` | Heap maximum size minh họa. |
| `-Xlog:gc*=info:file=gc.log:time,uptime,level,tags` | Ghi unified GC log ra file để phân tích. |

`4g` chỉ là giá trị minh họa; hãy đặt heap theo live set, allocation rate, giới hạn container và headroom dành cho concurrent evacuation. Không mặc định mọi ứng dụng cần heap initial bằng maximum.

### 6.1. Kiểm tra collector có trong JDK

Có thể thử khởi động một JVM ngắn:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xlog:gc+init=info -version
~~~

Nếu build không có Shenandoah, JVM sẽ báo không nhận diện được collector hoặc option liên quan. Nếu collector được khởi tạo, log `gc+init` giúp xác nhận thông tin khởi tạo ở startup; `-version` chỉ là phép kiểm tra ngắn, không thay thế việc xác minh GC log trên workload thật. Hãy kiểm tra vendor, build và nền tảng của JDK trước khi đưa option vào service.

### 6.2. Không mang cờ experimental cũ từ JDK 24 sang JDK 25

Trong JDK 24, generational mode còn experimental và cần:

~~~text
-XX:+UnlockExperimentalVMOptions
~~~

Trong JDK 25, JEP 521 đã đưa mode này thành product feature. Cấu hình JDK 25 chỉ cần hai cờ Shenandoah ở mục 6; không thêm cờ unlock cũ vào tài liệu triển khai hiện tại.

### 6.3. Heuristics trong generational mode

Shenandoah mặc định dùng heuristic `adaptive` để điều chỉnh thời điểm bắt đầu GC và lượng công việc cần xử lý. Trong generational mode của JDK 25, `adaptive` là heuristic được hỗ trợ; không áp dụng `static` hoặc `compact` từ mode khác rồi giả định chúng có hiệu lực.

## 7. Đọc GC log để xác nhận các thế hệ hoạt động

Dùng unified logging:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc*=info:file=gc.log:time,uptime,level,tags \
  -jar application.jar
~~~

Trong log, tìm các thông tin về:

- Khởi tạo Shenandoah và mode đang sử dụng.
- Young collection và thời lượng pause.
- Old-generation marking/concurrent work.
- Mixed collection và số region được xử lý.
- Promotion, evacuation, heap occupancy và dung lượng còn trống.
- Degenerated hoặc Full GC nếu collector không hoàn tất công việc đồng thời theo kế hoạch.

Một số bản JDK/vendor có thể thay đổi chi tiết tên phase hoặc định dạng log. Hãy xem log thực tế của đúng JDK 25 build; không phụ thuộc vào một chuỗi log cụ thể trong script production.

### Ví dụ cách đọc một chu kỳ

~~~text
[info][gc] GC(12) Pause Young ...
[info][gc] GC(13) Concurrent Mark ...
[info][gc] GC(14) Pause Mixed ...
~~~

Đây là sơ đồ tên sự kiện minh họa, không phải bản sao log bảo đảm xuất hiện nguyên văn trên mọi build. Điều cần nhận ra là young work, old marking và mixed evacuation có thể đan xen trong khi ứng dụng vẫn tiếp tục xử lý request.

### Phân biệt pause và concurrent duration

Không cộng thời lượng concurrent mark/evacuation vào tổng stop-the-world pause. Concurrent work diễn ra song song với ứng dụng; nó tiêu thụ CPU và có thể cạnh tranh tài nguyên, nhưng không đồng nghĩa toàn bộ ứng dụng bị dừng trong khoảng đó.

Khi đánh giá latency, phân tích riêng:

- Tổng thời gian pause.
- Pause dài nhất và percentile pause.
- Thời gian concurrent work.
- CPU do GC workers tiêu thụ.
- Throughput và request latency của ứng dụng trong cùng khoảng thời gian.

## 8. Khi nào generational mode có lợi?

Generational Shenandoah đáng thử khi workload có phân bố tuổi object rõ:

- Nhiều request tạo DTO, collection, serializer buffer và object tạm thời.
- Allocation rate cao nhưng phần lớn object chết sau một hoặc vài chu kỳ.
- Có một tập object sống lâu tương đối ổn định như cache hoặc metadata.
- Ứng dụng cần pause ngắn và có đủ CPU/headroom cho concurrent GC.

Trong trường hợp này, young collection có thể thu hồi lượng lớn object chết trẻ mà không phải quét toàn bộ old generation mỗi lần. Old generation được đánh dấu và thu gom theo chu kỳ riêng; mixed evacuation thu hồi một phần old regions khi có lợi.

### Khi lợi ích có thể thấp

- Hầu hết object sống lâu, khiến young collection phải di chuyển nhiều survivor.
- Allocation rate thấp, không tạo áp lực thu gom young thường xuyên.
- Ứng dụng bị giới hạn CPU; GC concurrent cạnh tranh CPU với worker threads.
- Heap quá sát live set, thiếu vùng trống để evacuation và promotion.
- Chi phí card marking/barrier lớn so với lượng garbage được thu hồi.

Không chọn collector chỉ dựa trên tên generational. Hãy đo trên workload đại diện và so sánh với collector hiện tại.

## 9. Thiết kế benchmark công bằng

Để đánh giá JEP 521 trong một service:

1. Chọn cùng một JDK 25 vendor/build có Shenandoah.
2. Giữ nguyên ứng dụng, dữ liệu, cấu hình heap và môi trường.
3. Chạy baseline với Shenandoah single-generation mode.
4. Chạy lại với `-XX:ShenandoahGCMode=generational`.
5. Warm up ứng dụng và thực hiện nhiều lần đo có cùng thời lượng.
6. Ghi GC log, CPU utilization, heap occupancy, allocation rate, throughput và latency percentiles.
7. So sánh median và tail behavior, không chỉ một lần chạy tốt nhất.

### Bảng số liệu cần thu

| Chỉ số | Điều cần biết |
| --- | --- |
| Throughput | Số request/transaction mỗi giây. |
| p50 / p95 / p99 / p99.9 latency | Độ trễ điển hình và tail latency. |
| Pause time | Tổng pause, max pause và phân bố pause. |
| Concurrent GC CPU | Mức CPU GC sử dụng trong khi ứng dụng chạy. |
| Allocation rate | Số byte được cấp phát mỗi giây. |
| Promotion rate | Lượng object/region được chuyển sang old generation. |
| Live set / heap occupancy | Lượng dữ liệu thực sự còn sống và headroom. |
| Degenerated / Full GC | Dấu hiệu collector không theo kịp hoặc gặp áp lực bộ nhớ. |
| Process RSS | Ảnh hưởng tới footprint ở cấp hệ điều hành/container. |

### Không so sánh bằng pause time đơn lẻ

Một collector có thể giảm pause nhưng dùng nhiều CPU concurrent hơn, làm giảm throughput hoặc tăng tail latency do cạnh tranh tài nguyên. Ngược lại, pause nhỏ không đảm bảo ứng dụng không có latency spike vì còn network, lock, scheduling và các nguyên nhân khác.

## 10. Điều chỉnh heap và headroom

Shenandoah thực hiện evacuation đồng thời trong khi ứng dụng vẫn allocation. Collector cần đủ vùng trống để:

- Chuyển object còn sống ra khỏi region đang thu gom.
- Tiếp nhận object được promotion từ young sang old.
- Duy trì khoảng trống để ứng dụng tiếp tục cấp phát trong lúc GC chạy.

Nếu heap quá nhỏ so với live set và allocation pressure, GC có thể không theo kịp tốc độ cấp phát. Khi đó có nguy cơ evacuation failure, degenerated collection hoặc Full GC; những trường hợp này có thể làm pause tăng đáng kể.

Các bước điều chỉnh thực tế:

1. Đo live set sau các chu kỳ GC và allocation rate ở tải đỉnh.
2. Đặt `-Xmx` đủ lớn để có headroom cho concurrent work.
3. Quan sát promotion rate và old-generation occupancy.
4. Nếu mixed collection không reclaim đủ old regions, kiểm tra live set, promotion và fragmentation.
5. Chạy lại cùng workload sau mỗi thay đổi; không tăng heap và đổi collector cùng lúc nếu muốn biết thay đổi nào tạo khác biệt.

Đừng sao chép nguyên bộ cờ tuning của G1 hoặc ZGC sang Shenandoah. Generational Shenandoah có chính sách region, promotion, evacuation reserve và heuristic riêng.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| Generational Shenandoah vẫn experimental trong JDK 25 | JEP 521 đã đưa mode thành product feature trong JDK 25. |
| Phải dùng `-XX:+UnlockExperimentalVMOptions` trong JDK 25 | Không cần; cờ này chỉ thuộc hướng dẫn JDK 24 experimental cũ. |
| JDK 25 tự bật generational mode | Không; mode `satb` single-generation vẫn là mặc định của JDK 25. |
| Shenandoah có mặt trong mọi JDK vendor | Không; phải dùng build có đóng gói Shenandoah. Oracle JDK không ship collector này. |
| Young/old của Shenandoah giống hệt Eden/Survivor của G1 | Shenandoah dùng region cohorts và chính sách promotion riêng; không áp dụng máy móc layout/flags của G1. |
| Concurrent GC không có stop-the-world pause | Vẫn có pause ngắn ở các pha cần đồng bộ/root processing và có thể có pause dài trong tình huống suy giảm. |
| Generational luôn nhanh hơn single-generation | Kết quả phụ thuộc allocation profile, live set, CPU, heap và write-barrier cost. |
| Heuristic static/compact có thể bật như mode khác | Generational mode JDK 25 chỉ hỗ trợ heuristic adaptive. |

## 12. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| JVM báo không nhận diện `UseShenandoahGC` | JDK build không đóng gói Shenandoah | Xác minh vendor/build hoặc dùng một distribution có Shenandoah. |
| Generational mode không được bật | Thiếu `-XX:ShenandoahGCMode=generational` hoặc option không được truyền vào JVM thật | Kiểm tra command line, startup logs và cấu hình container/service. |
| JVM từ chối cờ `UnlockExperimentalVMOptions` trong script cũ | Script đang mang cấu hình experimental từ JDK 24 hoặc một option không cần thiết | Bỏ cờ unlock khỏi cấu hình JDK 25; chỉ giữ các cờ product feature. |
| Young GC diễn ra liên tục | Young allocation pressure cao hoặc young capacity nhỏ so với tải | Đo allocation rate, promotion và heap headroom; benchmark với workload thật. |
| Old occupancy tăng liên tục | Live set lớn, promotion cao hoặc old reclamation không theo kịp | Kiểm tra object retention, old marking/mixed work và live set. |
| Pause tăng bất thường | Root processing, evacuation failure, degenerated/Full GC hoặc workload cạnh tranh tài nguyên | Đọc phase logs, heap headroom và CPU; xác định đúng nguyên nhân trước khi tuning. |
| Throughput giảm dù pause thấp | Concurrent GC và write barriers dùng thêm CPU | Đo CPU GC workers, allocation rate và throughput; so sánh với baseline. |
| Mixed collections kéo dài | Old regions được chọn có nhiều live data hoặc evacuation reserve hạn chế | Xem tỷ lệ live/garbage, promotion và headroom; không chỉ tăng số GC workers một cách mù quáng. |
| Không thấy young/old trong log | Log level/tag chưa đủ hoặc đang chạy mode single-generation | Xác nhận mode và dùng unified GC logging phù hợp. |

## 13. Bài tập thực hành

### Bài A — Xác minh mode

Chọn một JDK 25 build có Shenandoah, khởi động ứng dụng thử với `-XX:+UseShenandoahGC` và `-XX:ShenandoahGCMode=generational`.

**Điều kiện đạt:** xác nhận đúng JDK vendor/build và GC log cho thấy Shenandoah được chọn ở generational mode.

### Bài B — Tạo workload nhiều object ngắn hạn

Tạo một endpoint hoặc chương trình sinh nhiều DTO, collection và buffer tạm thời; giữ một cache nhỏ có object sống lâu.

**Điều kiện đạt:** mô tả được khác biệt giữa object chết trẻ và object sống lâu qua nhiều chu kỳ.

### Bài C — So sánh hai mode

Chạy cùng workload một lần với mode `satb` và một lần với mode `generational`, giữ nguyên heap, CPU quota và dữ liệu đầu vào.

**Điều kiện đạt:** báo cáo throughput, p99 latency, pause distribution, concurrent CPU, allocation và promotion; giải thích được trade-off quan sát thấy.

### Bài D — Đọc young/old/mixed activity

Thu GC log và tìm các pha young collection, old marking và mixed evacuation.

**Điều kiện đạt:** phân biệt được pause time với concurrent duration và nêu được collector đã xử lý phần heap nào.

### Bài E — Điều tra áp lực old generation

Tăng tỷ lệ object sống lâu hoặc giữ reference trong cache, sau đó quan sát old occupancy và promotion.

**Điều kiện đạt:** xác định liệu old growth đến từ live set thật, retention ngoài ý muốn hay allocation/promotion pressure.

## 14. Checklist trước khi triển khai

- [ ] JDK 25 vendor/build có hỗ trợ Shenandoah.
- [ ] Generational mode được bật rõ bằng `-XX:ShenandoahGCMode=generational`.
- [ ] Không còn cờ `-XX:+UnlockExperimentalVMOptions` từ hướng dẫn JDK 24.
- [ ] Hiểu rằng mode mặc định của JDK 25 vẫn là `satb` single-generation.
- [ ] Heuristic đang dùng là `adaptive`.
- [ ] GC logging được bật ở mức đủ để quan sát young/old/mixed work.
- [ ] Heap có headroom cho concurrent evacuation và promotion.
- [ ] Benchmark dùng cùng workload, heap, CPU quota và runtime build.
- [ ] Đã đo throughput, latency percentiles, pause, concurrent CPU, allocation và promotion.
- [ ] Có kiểm tra degenerated/Full GC và evacuation failure.
- [ ] Đã kiểm tra RSS/container memory và giới hạn vận hành.
- [ ] Có kế hoạch quay lại collector/mode trước đó nếu kết quả production không đạt mục tiêu.

## 15. Tài liệu tham khảo

1. [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): đưa generational mode thành product feature trong JDK 25.
2. [JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): lịch sử triển khai experimental trong JDK 24.
3. [OpenJDK — Shenandoah GC Wiki](https://wiki.openjdk.org/display/shenandoah/Main): đặc tính collector, mode, hiệu năng, chẩn đoán và availability theo vendor.
4. [Red Hat build of OpenJDK 25 — New Features](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features): generational mode trong JDK 25 và cờ bật mode.
5. [Eclipse Temurin 25 — Release Notes](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html-single/release_notes_for_eclipse_temurin_25/openjdk25-features): thông tin generational Shenandoah trong bản phân phối Temurin 25.
6. [OpenJDK JDK 25 — java command options](https://github.com/openjdk/jdk/blob/jdk-25-ga/src/java.base/share/man/java.md): `-XX:+UseShenandoahGC`, `-XX:ShenandoahGCMode` và `-XX:ShenandoahGCHeuristics`.
7. [Oracle Java 25 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-collector-implementation.html): generational hypothesis và vòng đời object nói chung trong HotSpot.

**Ghi nhớ:** Generational Shenandoah trong JDK 25 là product feature, nhưng vẫn là mode cần bật tường minh trên một JDK build có hỗ trợ Shenandoah. Young collection tận dụng việc object thường chết trẻ; old marking và mixed evacuation xử lý dữ liệu sống lâu theo từng vùng, trong khi phần lớn công việc GC diễn ra đồng thời với ứng dụng. Chỉ chọn mode này sau khi đo trên workload thật và theo dõi cả pause, concurrent CPU, promotion lẫn headroom của heap.
