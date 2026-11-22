# Vị trí của Full GC trong hoạt động của G1 — Full GC song song từ Java 10

## 1. Ý tưởng trọng tâm: Full GC là đường dự phòng, không phải nhịp chính của G1

**Garbage-First Garbage Collector (G1 GC)** cố gắng thu hồi bộ nhớ theo từng phần nhỏ của Java heap, đồng thời thực hiện nhiều bước phân tích đối tượng sống song song hoặc concurrent với ứng dụng. Phần lớn thời gian, G1 thu hồi qua **young collections** và **mixed collections** — không phải qua những lần Full GC quét toàn heap.

Khi những cơ chế bình thường **không kịp giải phóng đủ không gian**, hoặc có **yêu cầu thu gom toàn heap rõ ràng**, G1 có thể thực hiện **Full GC**. Đây là hoạt động **stop-the-world (STW)**: các luồng Java của ứng dụng tạm dừng, JVM xử lý live objects trên phạm vi heap và **nén heap tại chỗ (in-place compaction)** để khôi phục không gian cấp phát nếu có thể.

Từ **Java 10, JEP 307 — Parallel Full GC for G1** cải thiện worst-case latency bằng cách song song hóa phần công việc Full GC trên nhiều GC worker. Tuy nhiên:

- **Parallel**: nhiều **luồng GC** phối hợp xử lý cùng một tác vụ.
- **Concurrent**: GC xử lý trong lúc **luồng ứng dụng vẫn chạy**.
- **Parallel Full GC của G1 vẫn là STW**, không phải concurrent Full GC.

Đó là điểm phân biệt quan trọng nhất. G1 tận dụng nhiều worker để **rút ngắn khả năng phải dừng ứng dụng khi Full GC là bất khả kháng**, chứ không biến Full GC thành hoạt động “không có pause”.

**Thông điệp vận hành:** một ứng dụng G1 ổn định lý tưởng **hiếm khi cần Full GC do áp lực cấp phát**. Việc thấy Full GC xuất hiện liên tục không phải bằng chứng “GC đã chạy tốt hơn vì quét sạch toàn bộ heap”, mà là tín hiệu cần kiểm tra **allocation pressure, tỷ lệ live data, bộ nhớ old/humongous, concurrent marking và nguyên nhân kích hoạt**.

### Tính hiện hành

Bài thuộc chủ đề **G1 Full GC song song** của module Java 10, nhưng sử dụng cách giải thích và công cụ **vẫn áp dụng trên Java 17/21/26 và JDK HotSpot hiện đại**:

- JEP 307 được đưa vào **Java 10**; G1 Full GC song song vẫn tồn tại.
- Tài liệu Oracle JDK 26 vẫn mô tả Full GC là **in-place stop-the-world full heap compaction** khi G1 cần fallback.
- Chẩn đoán sử dụng Unified Logging `-Xlog:gc*`, `-Xlog:gc+heap=info` và `-Xlog:gc+phases=...`, thay vì các cách ghi log GC cũ đã deprecated/removed.
- Các số JVM flag và log cụ thể có thể thay đổi theo bản JDK/provider; ví dụ được kiểm thử trên một bản HotSpot JDK 24 và biên dịch theo `--release 17`.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ chu trình **Young-Only → concurrent marking → mixed collections → Young-Only** của G1 và đặt **Full GC** đúng vị trí **đường dự phòng**.
2. Giải thích khác nhau giữa **young**, **mixed**, **concurrent marking** và **full heap compaction**.
3. Phân biệt **GC song song** với **GC concurrent**, nhất là Full GC của G1.
4. Nêu mối liên hệ giữa JEP 307 của Java 10 và `-XX:ParallelGCThreads`.
5. Đọc log `Pause Full`, `G1 Compaction Pause`, `System.gc()` và **evacuation failure** theo đúng nguyên nhân.
6. Hiểu vì sao không đủ chỗ để chuyển đối tượng trong evacuation có thể dẫn đến Full GC, dù một lần evacuation failure không nhất thiết tạo Full GC ngay.
7. Hiểu ảnh hưởng của **old-generation occupancy**, **concurrent marking chưa hoàn tất**, **humongous objects** và **fragmentation**.
8. Biết Full GC có thể thu hồi memory nhưng **không bảo đảm** tránh `OutOfMemoryError`.
9. Chạy ví dụ Java 17+ để quan sát Full GC **có chủ đích trong phòng lab** bằng GC logging.
10. Tách stdout của ứng dụng khỏi log JVM và viết kiểm thử không dựa trên thời gian GC cố định.
11. Đưa ra thứ tự chẩn đoán/tối ưu dựa trên bằng chứng thay vì thêm JVM flags một cách ngẫu nhiên.
12. Tránh sử dụng `System.gc()` như “phương pháp tăng tốc”.
13. Hiểu giới hạn của `-XX:MaxGCPauseMillis` và lý do nó không phải cam kết cứng cho Full GC.
14. Xác định khi nào nên xem heap sizing, allocation patterns, ứng dụng rò rỉ dữ liệu hoặc native/JNI pinning.

## 3. Kiến trúc vùng bộ nhớ của G1

G1 chia **Java heap** thành nhiều **regions** (vùng bộ nhớ có kích thước bằng nhau trong một cấu hình cụ thể). Tại từng thời điểm, các region có thể đóng vai trò như:

- **Eden**: nơi thường cấp phát các đối tượng Java mới.
- **Survivor**: nơi lưu đối tượng còn sống sau thu gom young.
- **Old**: đối tượng sống lâu, đã được promote hoặc cấp phát theo quy tắc đặc biệt.
- **Humongous**: đối tượng lớn được cấp phát trực tiếp trong old generation, thường chiếm nhiều region liên tiếp.
- **Free**: region chưa được dùng, có thể cấp phát hoặc làm destination khi evacuation.

Khác với việc chỉ nghĩ heap là một dải young và một dải old liền nhau, G1 dùng **tập hợp regions**; vị trí các region mang vai trò young/old có thể phân tán trong heap.

```text
Java heap của G1 (minh họa logic)
+-----+-----+-----+-----+-----+-----+-----+-----+
| Eden| Old | Free| Eden|  S  | Old | Free|  H  |
+-----+-----+-----+-----+-----+-----+-----+-----+
                 Regions cùng kích thước
S = Survivor, H = Humongous
```

Phần minh họa không mô tả một trạng thái heap cụ thể của JVM bạn đang chạy; phân bố region, kích thước và số lượng là dữ liệu runtime.

### Vì sao cấu trúc region hỗ trợ tránh Full GC?

G1 có thể lựa chọn **một tập regions nhỏ** có nhiều rác để thu gom trong một lần pause, thay vì buộc phải quét và compact mọi vùng old generation. Khi tìm thấy đối tượng còn sống trong collection set, G1 thường **copy** chúng sang những region đích phù hợp (evacuation), sau đó tái sử dụng region nguồn.

Nếu G1 còn đủ **free destination regions**, cơ chế theo từng đợt này giúp xử lý áp lực cấp phát với các pause ngắn hơn nhiều so với một lần quét/nén **toàn bộ heap**.

Nhưng chính việc evacuation cần vùng đích cũng tạo ra rủi ro: **nếu không còn chỗ để copy đối tượng sống**, G1 có thể phải giữ lại đối tượng tại chỗ, phục hồi ở những lần GC tiếp theo và trong tình huống xấu phải fallback sang Full GC.

## 4. Chu trình bình thường của G1 và vị trí Full GC

Theo tài liệu Oracle JDK 26, có thể mô tả hai pha lớn của chu trình G1:

**Pha A — Young-Only**

- G1 thực hiện nhiều **normal young collections**.
- Đối tượng sống được giữ ở survivor hoặc chuyển vào old.
- Khi old occupancy tới ngưỡng được mô hình hóa (IHOP), G1 lên lịch một **Concurrent Start young collection** để khởi động quá trình marking.
- Trong lúc **concurrent marking** chạy cùng ứng dụng, các normal young collections khác vẫn có thể diễn ra.
- Chu kỳ marking kết thúc với những đoạn **Remark** và **Cleanup** có STW pauses.

**Pha B — Space-Reclamation (mixed collections)**

- Dựa trên kết quả marking, G1 chọn những old regions phù hợp để thu hồi.
- Mỗi **mixed collection** thu gom các young regions và **một tập old regions**.
- G1 chia công việc old-generation ra nhiều lần pause, dựa vào chi phí dự đoán và mục tiêu pause.
- Khi việc thu hồi old regions tiếp tục không còn đáng công hoặc đã xong, G1 quay về Young-Only.

```text
                    [Ứng dụng tiếp tục cấp phát]
                               |
                  +------------v------------+
                  | Young-Only: young GCs   |
                  | STW, incremental,       |
                  | evacuation              |
                  +------------+------------+
                               |
                   Old occupancy / IHOP
                               v
                   [Concurrent Start GC]
                               |
                  Concurrent marking chạy
                  cùng ứng dụng (có young
                  collections xen kẽ)
                               |
                         Remark/Cleanup
                               |
                               v
                  +------------------------+
                  | Mixed collections      |
                  | Young + một phần Old   |
                  | STW, incremental       |
                  +------------+-----------+
                               |
                          Trở lại Young-Only

      Nếu không thu hồi đủ / không tiến triển được,
      hoặc có yêu cầu toàn heap rõ ràng:
                         |
                         v
               +---------------------+
               | FULL GC (fallback)  |
               | STW toàn JVM        |
               | nén toàn Java heap  |
               | nhiều GC workers    |
               +---------------------+
```

Sơ đồ là mô hình khái quát, **không phải finite-state machine bắt buộc** với mọi trạng thái và nguyên nhân Full GC. Ví dụ, `System.gc()` hoặc một công cụ bên ngoài có thể yêu cầu Full GC mà không cần old occupancy đạt ngưỡng nào.

**Điểm quan trọng:** Full GC **không phải pha định kỳ bắt buộc sau mỗi chuỗi mixed collections**. Một vòng G1 lý tưởng có thể đi qua nhiều chu kỳ Young-Only / mixed mà không hề Full GC.

## 5. Phân biệt young, mixed, concurrent marking và Full GC

| Hoạt động | Phạm vi chính | Luồng ứng dụng có phải dừng? | Vai trò |
| --- | --- | --- | --- |
| **Young GC / Normal Young** | Young regions | **Có**, trong evacuation pause | Giải phóng các đối tượng young không còn sống, promote survivors |
| **Concurrent marking** | Phân tích live data ở old/whole-heap context | **Phần lớn không**, nhưng có điểm STW liên quan | Chuẩn bị thông tin để chọn old regions |
| **Remark/Cleanup** | Kết thúc marking, làm sạch/hoàn thiện dữ liệu | **Có** ở những đoạn STW | Chốt live set, chọn đối tượng/region cho mixed |
| **Mixed GC** | Young + một phần old regions | **Có**, incremental STW evacuation | Thu hồi old dần dần, tránh Full GC |
| **Full GC của G1** | **Toàn Java heap** | **Có, STW toàn bộ** | Fallback in-place compaction hoặc xử lý yêu cầu explicit |

Từ **parallel** trong tài liệu G1 xuất hiện ở nhiều chỗ: young và mixed evacuations có thể sử dụng nhiều worker, concurrent marking cũng có thể có nhiều thread, và từ Java 10 Full GC được song song hóa.

Vì vậy không thể suy luận:

- “G1 là concurrent collector” ⇒ “mọi pha đều concurrent”.
- “Full GC là parallel” ⇒ “application threads vẫn chạy”.
- “Mixed GC có old regions” ⇒ “mixed là Full GC”.
- “GC pause của young là STW” ⇒ “young GC luôn lâu như Full GC”.

G1 là một collector **mostly concurrent**, chứ không phải **fully concurrent**; phần lớn space-reclamation bằng evacuation vẫn có những **STW pauses**.

## 6. Vì sao Full GC là đường dự phòng?

G1 ưu tiên thu hồi **theo từng tập region** vì thời lượng pause có thể được dự đoán và điều chỉnh tương đối. Full GC xử lý phạm vi lớn hơn nhiều: cần xác định các đối tượng còn sống, cập nhật tham chiếu và compact heap, nên thường có **worst-case latency cao**.

Khi tải hệ thống bình thường và chính sách heap phù hợp:

1. Young GC dọn phần lớn đối tượng chết sớm.
2. Concurrent marking giúp G1 nhìn thấy old regions có nhiều rác.
3. Mixed GC dọn các old regions phù hợp theo nhiều lần pause.
4. Free regions vẫn đủ để ứng dụng cấp phát và GC evacuation.

Trong tình huống xấu:

1. Ứng dụng cấp phát quá nhanh, promote nhiều đối tượng sang old.
2. Old occupancy tăng, concurrent marking/space-reclamation chưa kịp hoàn thành.
3. G1 thiếu free regions dành cho việc copy đối tượng còn sống.
4. Evacuation có thể thất bại; nếu GC không giải phóng đủ chỗ để tiếp tục hoạt động, JVM fallback sang **Full GC**.
5. Full GC cố nén và giải phóng heap trên phạm vi toàn bộ, nhưng nếu **live set vẫn quá lớn**, ứng dụng vẫn có thể nhận `OutOfMemoryError`.

Không có một quy tắc đơn giản “cứ old occupancy trên X% thì Full GC ngay”: G1 dùng heuristics về marking, eviction, allocation, tốc độ thay đổi heap và trạng thái thực tế.

### Full GC không phải “dọn rác định kỳ”

Không nên vận hành service bằng lịch gọi `System.gc()` mỗi 5 phút để “dọn sạch heap”. Điều đó có thể tạo STW pause không cần thiết, giảm throughput và che khuất nguyên nhân giữ đối tượng quá lâu.

Thay vào đó, xem các Full GC do thiếu bộ nhớ là **tín hiệu** để cải thiện allocation, giữ dữ liệu, sizing hoặc cấu hình có bằng chứng.

## 7. JEP 307 và ý nghĩa “Full GC song song” của Java 10

Trước Java 10, phần Full GC của G1 là đường dự phòng với thuật toán **mark-sweep-compact chạy đơn luồng** trong triển khai trước JEP 307. Khi fallback xảy ra, việc dùng một luồng tạo nguy cơ pause kéo dài.

**JEP 307 — Parallel Full GC for G1** (được triển khai trong Java 10) thay đổi điều này bằng cách song song hóa những công việc Full GC, nhằm **giảm worst-case latency** khi không thể tránh Full GC.

Các điểm cần hiểu đúng:

- **Mục đích:** làm tình huống xấu ít tốn thời gian hơn, không biến Full GC thành lựa chọn thu gom thường xuyên.
- **Tính chất:** vẫn **STW**; chỉ nhiều worker GC chạy đồng thời.
- **Worker count:** liên quan `-XX:ParallelGCThreads`, cũng tác động tới các GC pause khác của G1.
- **Không bảo đảm tăng tốc tuyến tính:** 4 workers không chắc pause chỉ bằng 1/4 so với một worker; có chi phí đồng bộ, memory bandwidth, lượng live data và điều kiện CPU.
- **Không biến G1 thành Parallel GC collector:** G1 với parallel Full GC **vẫn là G1**, sử dụng regions, concurrent marking và mixed collections làm hoạt động chính.
- **Không tạo khả năng mới để thu hồi live objects:** nếu đối tượng còn reachable hoặc memory requirement thực sự vượt heap, nhiều worker cũng không biến chúng thành rác.

Ví dụ cấu hình lab:

```bash
java -XX:+UseG1GC -Xms64m -Xmx64m \
     -XX:ParallelGCThreads=2 \
     G1FullGcRoleDemo
```

Số worker được cho phép không chắc bằng số worker thực sự sử dụng trong mọi pause: JVM có thể điều chỉnh theo heap size, CPU, tác vụ và heuristics. **Kiểm log runtime** để biết số worker thực tế.

## 8. “Parallel” khác “concurrent”: minh họa theo luồng

Giả sử có ba luồng ứng dụng và hai GC workers:

**Concurrent marking:**

```text
Thời gian --->

App A:  [chạy] [chạy] [chạy] [chạy]
App B:  [chạy] [chạy] [chạy] [chạy]
App C:  [chạy] [chạy] [chạy] [chạy]
GC 1:          [mark] [mark]
GC 2:          [mark] [mark]

(Có một số STW pause nhỏ/điểm đồng bộ khác xen kẽ.)
```

**Parallel Full GC của G1:**

```text
Thời gian --->

App A:  [chạy] |---- tạm dừng ----| [chạy]
App B:  [chạy] |---- tạm dừng ----| [chạy]
App C:  [chạy] |---- tạm dừng ----| [chạy]
GC 1:          |mark/compact/...  |
GC 2:          |mark/compact/...  |

=> GC workers song song; ứng dụng vẫn bị STW trong pause.
```

Chú ý: hình minh họa tối giản, không mô tả cấu trúc khóa hoặc scheduling nội bộ. Điều cần nhớ là **nhiều GC workers không đồng nghĩa application concurrency**.

Nếu hệ thống có SLA latency nghiêm ngặt, mục tiêu thường là **tránh Full GC do exhaustion**, không chỉ tăng số worker để làm một lần Full GC nhanh hơn.

## 9. Những nguyên nhân có thể đưa G1 tới Full GC

### 9.1. Áp lực cấp phát vượt tốc độ thu hồi

Ứng dụng tạo đối tượng rất nhanh; nhiều đối tượng sống lâu khiến old generation tăng nhanh. G1 có thể chưa kịp completing marking và mixed collections để lấy lại đủ free regions.

Ví dụ thường gặp:

- Cache tăng không giới hạn.
- Hàng đợi request/stream tích tụ.
- Batch tạo nhiều objects được giữ tham chiếu quá lâu.
- Dữ liệu đọc toàn bộ vào RAM trong khi có thể xử lý streaming.
- Tăng tải đột ngột làm tốc độ allocation/promotions lớn hơn dự đoán.

Không nên quy tất cả Full GC cho “leak”. Một service có **live set lớn nhưng hữu ích** cũng có thể cần heap lớn hơn hoặc cách tổ chức memory khác.

### 9.2. Evacuation failure vì thiếu destination space

G1 đang copy đối tượng sống từ collection set sang regions đích nhưng **không tìm được đủ không gian**. Log có thể ghi `Evacuation Failure: Allocation`. Đây là tín hiệu rất quan trọng khi phân tích Full GC do old occupancy cao.

**Không phải cứ có evacuation failure là Full GC lập tức**. G1 có thể tiếp tục vận hành, giữ một số đối tượng ở chỗ cũ, ưu tiên collection set phù hợp để dọn trong những pause sau. Nhưng nếu không thu hồi đủ không gian, **Full GC có thể được lên lịch**.

### 9.3. Humongous objects và phân mảnh

Các đối tượng rất lớn so với region size được G1 cấp phát theo cơ chế **humongous regions**. Tập hợp các đối tượng lớn có thể làm thiếu những **regions liền nhau** cần thiết, kể cả khi một số khu vực khác còn trống.

Có thể dẫn đến:

- Áp lực old generation tăng.
- Khả năng thu hồi từ mixed collections thấp hơn mong đợi.
- Các lần concurrent start/marking diễn ra sớm.
- Full GC hoặc `OutOfMemoryError` trong điều kiện cực đoan.

Theo Oracle JDK 26, Full GC đôi khi có thể diễn ra **trước khi tổng Java heap thật sự cạn hết** vì nhu cầu dãy regions liên tiếp và fragmentation liên quan humongous allocation.

### 9.4. Yêu cầu Explicit GC hoặc công cụ quản trị

`System.gc()` có thể kích hoạt Full GC (trong cấu hình mặc định phù hợp với HotSpot G1), ngay cả khi ứng dụng **không thiếu bộ nhớ**. Một số công cụ quản trị cũng có thể yêu cầu thu gom toàn heap.

Vì vậy log `Pause Full (System.gc())` nói lên **nguồn yêu cầu rõ ràng**, không phải chứng cứ mặc định về memory pressure.

### 9.5. Các điều kiện provider/configuration khác

Tùy JDK và flag được cấu hình, có thể có full collection do periodic GC hoặc thao tác dịch vụ cụ thể. Đừng kết luận mọi `Pause Full` đều là evacuation failure. **Đọc reason trong log** và đối chiếu nguồn sự kiện/flags/runtime.

## 10. Evacuation failure: bước trung gian quan trọng

**Evacuation** là quá trình G1 copy các live objects trong collection set tới destination regions rồi sử dụng lại không gian nguồn. Nó xuất hiện trong Young/Mixed GC, vốn là hoạt động bình thường của G1.

Khi không thể di chuyển một số objects, runtime hiện đại có thể ghi:

```text
... Pause Young (Normal) (G1 Evacuation Pause)
    (Evacuation Failure: Allocation) ...
```

Trong tài liệu Oracle mới còn có reason **`Pinned`**: một đối tượng bị giữ tại vị trí để tương tác an toàn với native code, như JNI `GetPrimitiveArrayCritical`. Một log có thể ghi `Allocation/Pinned` nếu cả hai yếu tố cùng xuất hiện.

**Ý nghĩa phân biệt:**

| Reason | Diễn giải |
| --- | --- |
| `Allocation` | Không có đủ destination space để copy đối tượng theo đường GC đang chạy |
| `Pinned` | Một số đối tượng không thể di chuyển vì đang bị pin/khóa tại vị trí phù hợp với native access |
| `Allocation/Pinned` | Có thể đồng thời gặp cả hai điều kiện |

Một evacuation failure **không đồng nghĩa ngay lập tức** với Full GC: G1 vẫn có thể tiếp tục và thu hồi regions trong các lần sau.

Nếu GC không tạo được tiến triển để có đủ không gian, **Full GC** là đường dự phòng nhằm compact toàn Java heap. Ở JDK mới, thông tin log và chiến lược thu hồi sau evacuation failure có thể tinh vi hơn; không nên dựa trên một thông điệp lỗi lịch sử đã thay đổi để xây parser cứng.

### To-space exhausted ≠ “ứng dụng chắc chắn đã leak”

Một ứng dụng có thể thiếu destination regions do:

- Live set quá lớn so với heap.
- Promotion và allocation tăng đột ngột.
- Reserve/headroom không đủ.
- Humongous allocation và fragmentation.
- Marking chưa kịp hoàn tất.
- Các đối tượng tạm thời sống lâu hơn bình thường do backlog.

Muốn kết luận leak, cần thêm evidence: heap dump, dominator tree, retained sizes, số lượng object theo thời gian, hoặc phân tích dữ liệu ứng dụng.

## 11. Full GC thực sự làm gì?

Tài liệu Oracle mô tả G1 Full GC là **in-place stop-the-world full heap compaction**. Tùy JDK, log có thể chia thành những pha như:

1. **Mark live objects**: tìm object còn reachable.
2. **Prepare compaction**: chuẩn bị cách bố trí đối tượng còn sống.
3. **Adjust pointers**: cập nhật tham chiếu theo vị trí sau khi di chuyển.
4. **Compact heap**: nén các đối tượng còn sống để tái tổ chức không gian.
5. **Reset Metadata**: hoàn thiện metadata và cấu trúc quản lý bộ nhớ.

Ví dụ một log trên **HotSpot JDK 24**:

```text
GC(1) Pause Full (System.gc())
GC(1) Using 2 workers of 2 for full compaction
GC(1) Phase 1: Mark live objects
GC(1) Phase 2: Prepare compaction
GC(1) Phase 3: Adjust pointers
GC(1) Phase 4: Compact heap
GC(1) Phase 5: Reset Metadata
GC(1) Pause Full (System.gc()) 15M->1M(64M) 1.752ms
```

Đây là trích đoạn **từ một lần chạy thử** và đã lược timestamp/tags để dễ đọc. **Không hardcode số GC ID, thời gian, memory before/after, tên từng phase hoặc worker count làm output bắt buộc trên mọi JDK**.

### Full GC có cứu ứng dụng không?

Có thể — nếu vẫn còn đủ **garbage có thể thu hồi** và heap sau compaction có chỗ để ứng dụng tiếp tục cấp phát.

Không chắc — nếu live data đã chiếm gần hết heap, hoặc vẫn không thể tạo khoảng cấp phát phù hợp. Khi đó ứng dụng vẫn có thể ném `OutOfMemoryError: Java heap space` hoặc gặp lỗi tài nguyên khác.

**Không nhầm:** “Full GC quét toàn heap” không có nghĩa nó sẽ thu hồi mọi objects. Những đối tượng **vẫn reachable** theo luật của GC phải được giữ lại.

## 12. GC logging: nhận biết Full GC trong hệ thống thật

Từ Java 9, HotSpot dùng **Unified Logging**. Với Java 17+ có thể bắt đầu bằng:

```bash
java -XX:+UseG1GC -Xlog:gc* -jar app.jar
```

Lệnh này chạy JAR có `Main-Class` đúng; đối với ứng dụng tên class, có thể dùng `-cp app.jar your.pkg.Main` thay `-jar`.

**Để lưu log:**

```bash
java -XX:+UseG1GC \
     -Xlog:gc*=info:file=gc.log:uptime,level,tags \
     -jar app.jar
```

Các thuộc tính quan trọng:

- `gc`: sự kiện GC cơ bản (young, mixed, full).
- `gc,start`: thời điểm bắt đầu pause.
- `gc,phases`: thời gian các pha nội bộ nếu level phù hợp.
- `gc,heap`: before/after occupancy, humongous regions.
- `gc,cpu`: `User`, `Sys`, `Real` — hỗ trợ đọc CPU vs elapsed pause.
- `gc,task`: có thể cho biết số GC workers được dùng.

Khi phân tích Full GC, tìm mẫu:

```text
Pause Full (G1 Compaction Pause)
Pause Full (System.gc())
Using N workers of M for full compaction
```

Các chuỗi là **ví dụ thường gặp**, không phải tiêu chuẩn ổn định cho mọi HotSpot/JDK. Reason khác nhau rất quan trọng:

- `G1 Compaction Pause` → thường liên quan fallback do thiếu tiến triển/không gian.
- `System.gc()` → có lời gọi explicit GC.
- Những reason khác → đọc tiếp events xung quanh và cấu hình JVM.

### Không kết luận Full GC chỉ vì thấy “Concurrent Mark”

`Concurrent Mark` là thành phần **bình thường** của G1, không phải Full GC. Tương tự `Pause Young (Mixed)` là một **mixed collection**, không phải quét toàn heap.

Hãy tìm đúng tên sự kiện `Pause Full` và phân tích **nguyên nhân**; không tính mọi GC pause như Full GC.

## 13. Ví dụ Java 17+ đầy đủ: tạo Full GC có kiểm soát trong phòng lab

Tạo tệp **`G1FullGcRoleDemo.java`**:

```java
import java.util.ArrayList;

public final class G1FullGcRoleDemo {
    private static volatile long checksum;

    public static void main(String[] args) {
        var retained = new ArrayList<byte[]>();

        for (int i = 0; i < 400; i++) {
            byte[] block = new byte[64 * 1024];
            block[0] = (byte) i;
            checksum += block[0] & 0xff;

            if (i % 8 == 0) {
                retained.clear();
            }
            retained.add(block);
        }

        System.out.println("retained=" + retained.size());
        System.out.println("checksum=" + checksum);
        System.out.println("explicitGC=before");

        // Chỉ dùng để quan sát hành vi GC trong lab riêng, KHÔNG dùng
        // như một kỹ thuật tối ưu startup hay latency production.
        System.gc();

        System.out.println("explicitGC=after");
    }
}
```

Chương trình:

- Tạo 400 mảng nhỏ (`64 KiB` mỗi mảng) để có hoạt động cấp phát.
- Mỗi 8 vòng lặp xóa danh sách giữ tham chiếu, nên sau vòng cuối còn `8` mảng trong danh sách.
- Tính checksum của byte đầu từng mảng. Đây là **logic thuần**, không phụ thuộc collector hoặc GC schedule.
- In một marker trước và sau lời gọi `System.gc()`.
- Chỉ dùng `System.gc()` **trong lab**, để chủ động tạo một yêu cầu explicit GC dễ quan sát trên cấu hình đã chọn. **Không thêm lời gọi này để “tối ưu” ứng dụng thực tế.**

Biên dịch với JDK 17+:

```bash
javac --release 17 -encoding UTF-8 G1FullGcRoleDemo.java
```

Chạy với heap nhỏ (thí nghiệm HotSpot, không phải cấu hình production):

```bash
java -XX:+UseG1GC \
     -Xms64m -Xmx64m -XX:ParallelGCThreads=2 \
     -Xlog:gc*=info:file=g1.log:uptime,level,tags \
     G1FullGcRoleDemo
```

Trên PowerShell, viết trên một dòng:

```powershell
java -XX:+UseG1GC -Xms64m -Xmx64m -XX:ParallelGCThreads=2 "-Xlog:gc*=info:file=g1.log:uptime,level,tags" G1FullGcRoleDemo
```

**Stdout chính xác của chương trình:**

```text
retained=8
checksum=42936
explicitGC=before
explicitGC=after
```

Vì log đã được chuyển vào `g1.log`, stdout ứng dụng vẫn chỉ có bốn dòng. Không cần `sleep`, không cần tạo memory pressure sát `OutOfMemoryError`.

**Kiểm tra log riêng:**

```bash
grep -E 'Pause Full|full compaction|Phase [0-9]' g1.log
```

PowerShell:

```powershell
Select-String -Path .\g1.log -Pattern 'Pause Full|full compaction|Phase [0-9]'
```

Trên **HotSpot JDK 24** trong môi trường kiểm thử, lệnh trên đã ghi được:

```text
Pause Full (System.gc())
Using 2 workers of 2 for full compaction
Phase 1: Mark live objects
Phase 2: Prepare compaction
Phase 3: Adjust pointers
Phase 4: Compact heap
Phase 5: Reset Metadata
```

**Những kết quả này chỉ minh họa đúng cơ chế trên runtime đã thử**, không cam kết các bản Java hoặc cấu hình khác sẽ sinh từng dòng giống hệt.

### Vì sao `System.gc()` không bảo đảm Full GC trong mọi hoàn cảnh?

`System.gc()` gửi **yêu cầu** tới runtime, không có hợp đồng Java API bắt buộc JVM phải thực thi một Full GC ngay lập tức. HotSpot có các option và đường xử lý như:

- `-XX:+DisableExplicitGC`: bỏ qua yêu cầu `System.gc()`.
- `-XX:+ExplicitGCInvokesConcurrent`: có thể hướng yêu cầu explicit GC sang xử lý concurrent thay vì Full GC theo cách thông thường.
- Runtime/collector khác G1 có cách xử lý khác.
- Cấu hình JVM hoặc trạng thái hiện tại có thể ảnh hưởng hành vi.

Vì vậy **test phải kiểm log của runtime thực**, không chỉ nhìn `System.gc()` trong source rồi tuyên bố chắc chắn có Full GC.

## 14. Đọc log của bài thử theo đúng ý nghĩa

Giả sử một phần log chứa:

```text
GC(1) Pause Full (System.gc())
GC(1) Using 2 workers of 2 for full compaction
GC(1) Pause Full (System.gc()) 15M->1M(64M) 1.752ms
```

Có thể diễn giải:

- `Pause Full`: runtime thực hiện một Full GC.
- `(System.gc())`: reason của pause là **explicit request**, không phải chứng cứ hệ thống thiếu bộ nhớ.
- `Using 2 workers of 2 for full compaction`: JVM đã sử dụng hai worker GC cho công việc full compaction.
- `15M->1M(64M)`: lượng heap báo trước/sau hoạt động trong tổng heap tại ví dụ.
- `1.752ms`: thời lượng của lần pause **trong một lần chạy cụ thể**.

Không được suy ra:

- “Mọi Full GC chỉ mất 1.752 ms”.
- “G1 đã chạy concurrent vì có hai workers”.
- “15 MB đều là leak vì được dọn hết sau GC”.
- “Tối ưu bằng cách gọi `System.gc()` liên tục sẽ làm service nhanh hơn”.
- “Giới hạn `MaxGCPauseMillis` luôn được bảo đảm”.

### Vì sao checksum không phụ thuộc GC?

Dòng `checksum=42936` được tính bằng phép cộng các giá trị số 0..255 và 0..143. Nó là kết quả thuật toán, không phải số byte còn sống sau GC hoặc số lượng object được collector xử lý. Do đó thích hợp để đối chiếu stdout giữa các lần thử có cấu hình GC khác nhau.

## 15. So sánh với GC logs khi G1 chịu memory pressure thật

Bài lab dùng `System.gc()` vì dễ tái hiện và không đẩy ứng dụng đến `OutOfMemoryError`. Trong production, muốn hiểu **fallback Full GC do thiếu bộ nhớ**, cần đọc các event **trước Full GC**, ví dụ:

```text
... Pause Young (...) (Evacuation Failure: Allocation) ...
... Pause Full (G1 Compaction Pause) ...
```

Đây là **chuỗi sự kiện minh họa**, không phải log thu được từ chương trình lab hay một quy tắc bắt buộc.

Hãy đối chiếu:

1. Các lần young/mixed có thu hồi được nhiều không?
2. Old regions và humongous regions có tăng liên tục không?
3. Concurrent marking đã bắt đầu và hoàn tất kịp trước khi heap gần đầy chưa?
4. Có dấu `Evacuation Failure` nào không? Lý do là `Allocation` hay `Pinned`?
5. Có đợt cấp phát/nhập dữ liệu bất thường tương ứng không?
6. Sau Full GC, heap giảm **đáng kể** hay chỉ rất ít?
7. Có dấu hiệu `OutOfMemoryError` hay hệ thống chỉ tạm thời thiếu headroom?

Nếu heap sau Full GC vẫn gần `-Xmx`, nguyên nhân có thể là **live set lớn, retention không mong muốn hoặc heap nhỏ so với workload**. Nếu heap giảm mạnh, có thể workload tạo nhiều đối tượng tạm thời nhưng G1 không kịp thu hồi theo nhịp bình thường. Cần quan sát nhiều lần, không kết luận chỉ từ một snapshot.

## 16. Humongous allocation và nguy cơ Full GC

Một object có kích thước đủ lớn so với region size được coi là **humongous** và thường đặt trực tiếp vào old-generation regions. Các humongous objects có yêu cầu cấp phát khác objects nhỏ: cần một chuỗi regions phù hợp và có thể khiến **fragmentation** trở thành vấn đề.

Ví dụ nghiệp vụ:

- Đọc một file lớn thành một `byte[]` liên tục.
- Ghép JSON payload cực lớn vào một `String`.
- Tích luỹ dữ liệu batch lớn trong một array.
- Tạo buffer lớn dù hoàn toàn có thể xử lý dạng streaming.

**Không mặc định tăng `-Xmx` sẽ giải quyết nguyên nhân gốc**. Nếu chương trình tạo mảng khổng lồ không cần thiết, trước tiên đánh giá khả năng xử lý streaming, chunking hoặc kiến trúc dữ liệu khác.

Nếu cần chẩn đoán humongous occupancy:

```bash
java -XX:+UseG1GC -Xlog:gc+heap=info -jar app.jar
```

Tìm các dòng về `Humongous regions: X->Y`. Số region chỉ là một phần của bằng chứng; kích thước region, life span, total heap và thời điểm đo đều quan trọng.

Tham số `-XX:G1HeapRegionSize` có thể thay ngưỡng/chi phí của humongous allocation, nhưng **không nên điều chỉnh chỉ vì thấy một số humongous regions**. Theo Oracle, cần đo số lượng, fragmentation và tác động ứng dụng; cấu hình region size có trade-off với các collection phases khác.

## 17. Vì sao tăng GC workers không phải cách chữa mọi Full GC?

Số GC workers cho Full GC song song có liên hệ với `-XX:ParallelGCThreads`. Khi tăng:

- Một số pha Full GC có thể rút ngắn nếu khối lượng công việc và CPU phù hợp.
- CPU và memory bandwidth có thể trở thành nút thắt.
- Việc phối hợp các worker có chi phí riêng.
- **Young/Mixed** GC sử dụng số worker này cũng bị ảnh hưởng, nên dễ thay đổi latency và throughput toàn ứng dụng.

Không nên:

```bash
# Không phải quy tắc tối ưu chung:
java -XX:+UseG1GC -XX:ParallelGCThreads=64 -jar app.jar
```

Số `64` chưa chắc phù hợp với container chỉ có vài CPU cores. Runtime thường chọn ergonomic defaults theo số CPU và heap size; giới hạn CPU của container và lịch CPU của hệ điều hành cũng ảnh hưởng.

Hãy bắt đầu với **mặc định**, ghi nhận số worker thực qua `-Xlog:gc+task=info` hoặc `-Xlog:gc*`, rồi chỉ thay khi số liệu benchmark cho thấy tác động tích cực.

**Quan trọng:** tăng worker có thể rút ngắn thời gian xử lý một Full GC, **không xử lý live set quá lớn, memory leak hay tình trạng thiếu heap liên tục**.

## 18. `MaxGCPauseMillis` là mục tiêu mềm, không là cam kết cứng

G1 cung cấp `-XX:MaxGCPauseMillis=<N>` làm **mục tiêu** khi điều chỉnh lượng công việc trong nhiều collection pauses. Một cấu hình ví dụ:

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar app.jar
```

Điều đó **không** có nghĩa mọi young, mixed và nhất là Full GC bắt buộc dưới 200 ms. G1 không phải real-time collector và có thể vượt mục tiêu trong tình huống xấu.

Trên một heap có live set rất lớn, Full GC stop-the-world có thể kéo dài hơn nhiều; việc chỉ giảm `MaxGCPauseMillis` xuống 50 ms không khiến full heap compaction có thể tự chia nhỏ thành các pause 50 ms.

**Chiến lược đúng hơn:**

- Tối ưu để **không phải fallback sang Full GC do exhaustion**.
- Để G1 tự điều chỉnh kích thước young generation và collection set.
- Quan sát phân phối p95/p99 của latency và GC pauses.
- Cân nhắc tăng heap, giảm allocation/retention hoặc chuyển collector theo yêu cầu latency nếu đã có bằng chứng.

Hướng dẫn Oracle khuyến nghị **giữ mặc định** cho G1 trước, và tránh khóa kích thước young quá cứng (`-Xmn` hoặc cặp `NewSize/MaxNewSize`) vì việc đó giảm khả năng G1 tự điều chỉnh theo mục tiêu pause.

## 19. Đọc các số `-Xmx`, `-Xms` và nguyên nhân OOME

`-Xmx` đặt giới hạn tối đa Java heap. `-Xms` là initial heap size (và có thể bằng `-Xmx` nếu muốn kích thước heap ổn định theo thiết kế).

Ví dụ:

```bash
java -XX:+UseG1GC -Xms2g -Xmx2g -jar app.jar
```

Đây **chỉ là ví dụ cú pháp** cho một ứng dụng đủ tài nguyên; không khuyến nghị mọi service dùng 2 GiB.

Nếu Full GC liên tiếp mà không thu hồi đủ memory, JVM có thể gặp `OutOfMemoryError: Java heap space`. Cần phân biệt:

- **Heap không đủ cho live set hợp lệ:** có thể cần tăng heap hoặc giảm concurrent work/backlog.
- **Retention/leak:** cần sửa logic giữ reference, cache, queue hoặc tài nguyên.
- **Humongous fragmentation:** cần đánh giá kích thước objects và region layout.
- **Native memory, metaspace, direct buffers hoặc thread stacks:** không được tự quy mọi vấn đề RAM cho heap G1; những lỗi này có cơ chế riêng.

Full GC **không làm giảm tất cả các loại memory**; nó chủ yếu xử lý Java heap và một số hoạt động GC liên quan. Nó không phải phương thức chung để giải quyết thiếu RAM của hệ điều hành hoặc giới hạn bộ nhớ container.

### Vì sao Full GC có thể xảy ra mà chưa chạm giới hạn `-Xmx`?

Vì mất khả năng cấp phát trong **điều kiện vùng bộ nhớ cụ thể** hoặc fragmentation liên quan humongous objects. “Tổng heap còn vài MB” không bảo đảm tìm được đúng **dãy regions liên tiếp** hay đủ không gian di chuyển live objects ở thời điểm cần.

## 20. Quy trình điều tra Full GC khi có sự cố production

Một quy trình làm việc theo bằng chứng:

1. **Xác định runtime và collector:** version JDK/HotSpot, JVM flags, có đúng `-XX:+UseG1GC` hay G1 default.
2. **Bật/thu GC logs:** bắt đầu `-Xlog:gc*`, không dựa vào duy nhất biểu đồ heap.
3. **Đếm Full GC và thời lượng:** tìm `Pause Full`, ghi thời điểm, reason, trước/sau heap và pause time.
4. **Phân biệt explicit và exhaustion:** `System.gc()` / tool hay `G1 Compaction Pause` sau evacuation failure?
5. **Xem các GC ngay trước Full:** young/mixed, trạng thái concurrent marking, recovery được bao nhiêu.
6. **Xem old/humongous occupancy:** có tăng theo thời gian hay đột biến?
7. **Đo allocation và live data:** heap histogram, JFR allocation events, heap dump theo quy định an toàn.
8. **Liên hệ workload:** deploy, batch job, request burst, cache warmup, queue backlog.
9. **Ưu tiên sửa ứng dụng nếu có vấn đề:** streaming, giới hạn queue/cache, tránh giữ data không cần, giảm object lớn.
10. **Cân nhắc sizing:** điều chỉnh `-Xmx`/headroom theo RAM container và live-set thực, không đặt quá gần memory limit.
11. **Chỉ sau đó tuning G1:** xem adaptive IHOP, concurrent marking threads, heap reserve, region size nếu log hỗ trợ giả thuyết.
12. **Thử nghiệm có đối chứng:** cùng workload, cùng JDK, số lần đủ nhiều; đo p95/p99, throughput, GC CPU và memory.
13. **Theo dõi sau triển khai:** Full GC count, time-in-GC, old/humongous occupancy và tình trạng OOME.

Không nên làm ngược bằng cách xem `ParallelGCThreads` là một “núm thần kỳ” rồi tăng lên rất cao mà chưa kiểm nguyên nhân và tác động CPU.

### Khi nào dùng JFR, heap dump hoặc công cụ ngoài?

- **JFR (Java Flight Recorder):** phân tích allocation patterns, GC events, pauses, object statistics khi được hỗ trợ.
- **Heap dump:** điều tra retained objects/dominator tree khi nghi ngờ leak; có thể tốn memory/disk và chứa dữ liệu nhạy cảm.
- **GC logs:** quan sát trình tự events và pause durations với overhead thường phù hợp cho vận hành nếu cấu hình thận trọng.
- **Metrics/observability:** GC pause time, JVM memory pools, request latency, request rate, heap occupancy.

Không upload heap dump thật lên nơi công cộng; nó có thể chứa nội dung nghiệp vụ, token hoặc dữ liệu người dùng. Cần tuân thủ chính sách bảo mật và quyền truy cập hệ thống.

## 21. `System.gc()` và những lựa chọn kiểm soát Explicit GC

Một số thư viện hoặc phần mềm cũ có thể gọi `System.gc()` để “dọn bộ nhớ”. Trên G1, yêu cầu ấy có thể gây pause Full GC không mong muốn.

Nếu không thể loại bỏ nguồn gọi explicit GC ngay, Oracle nêu các lựa chọn:

```bash
# Có thể yêu cầu G1 xử lý explicit GC theo hướng concurrent:
-XX:+ExplicitGCInvokesConcurrent

# Có thể yêu cầu JVM bỏ qua các lời gọi explicit GC:
-XX:+DisableExplicitGC
```

Đây là **các tùy chọn JVM**, không phải dòng lệnh độc lập; khi dùng phải đặt trong lệnh `java` và hiểu tác động tới mọi code trong tiến trình.

**Cẩn trọng:**

- Không dùng hai cờ này chỉ để che log Full GC khi chưa biết ai gọi `System.gc()`.
- Tác dụng và hỗ trợ phụ thuộc collector/JDK; cần xác minh trên runtime thật.
- Tắt explicit GC có thể ảnh hưởng kỳ vọng của một số thư viện/native-resource-management; không tự giả định vô hại trong mọi ứng dụng.
- Các công cụ quản trị bên ngoài vẫn có thể yêu cầu Full GC theo cơ chế khác; `DisableExplicitGC` không phải chặn tuyệt đối mọi nguồn Full GC.
- Một Full GC do thiếu heap thực sự **không được chữa** chỉ bằng cách tắt `System.gc()`.

Bài lab phía trên cố tình **không** bật các flag này, để quan sát Full GC theo reason `System.gc()` trên runtime đã thử.

## 22. So sánh G1 Full GC với Parallel GC và một collector concurrent khác

| Thuộc tính | G1 bình thường | G1 khi Full GC | Parallel GC | ZGC hiện đại |
| --- | --- | --- | --- | --- |
| Mục tiêu vận hành | Cân bằng throughput/latency | Dự phòng khi cần xử lý toàn heap | Ưu tiên throughput | Latency rất thấp |
| Phạm vi thu hồi | Một số regions (young/mixed) | Toàn Java heap | Theo thế hệ/pha | Phụ thuộc cơ chế collector |
| Concurrency với ứng dụng | Concurrent marking + STW pauses | **STW** | Thu gom STW | Phần lớn công việc concurrent |
| Có thể dùng nhiều GC workers? | Có | **Có, từ Java 10** | Có | Có |
| Pause time tương đối | Cố gắng ngắn, không có cam kết cứng | **Có thể rất dài** | Theo workload/heap | Hướng đến pause ngắn |
| Có phải cùng “Parallel GC” collector? | Không | **Không** | Chính nó | Không |

Bảng chỉ mô tả **định hướng kỹ thuật**, không phải bảng xếp hạng tuyệt đối giữa các collector hoặc hứa hẹn số millisecond.

Nếu yêu cầu là **không được có pause hàng giây**, cần so sánh các collector và workload thật với SLA, không chỉ điều chỉnh số thread Full GC của G1.

## 23. Những lỗi nhận thức và hành động thường gặp

### Lỗi A — “G1 chỉ chạy concurrent, vì thế Full GC không dừng ứng dụng”

Sai. G1 **mostly concurrent**, nhưng young/mixed có STW pauses; Full GC **STW toàn heap**.

**Sửa:** luôn kiểm log pause và phân biệt parallel với concurrent.

### Lỗi B — “Parallel Full GC Java 10 là một collector mới tên ParallelGC”

Sai. JEP 307 **song song hóa Full GC của G1**, không thay collector G1 thành `-XX:+UseParallelGC`.

**Sửa:** xác định collector đang dùng bằng JVM flags/log runtime.

### Lỗi C — “Mixed GC chính là Full GC”

Sai. Mixed GC thu gom **young + một phần old regions**, không phải full heap compaction.

**Sửa:** đọc tên sự kiện và vùng thu gom thay vì chỉ thấy chữ “old”.

### Lỗi D — “Sau mỗi concurrent mark phải có Full GC”

Sai. Marking chuẩn bị **mixed collections**, không phải full heap compaction định kỳ.

**Sửa:** xem Full GC là fallback/explicit operation, không đưa nó vào chu kỳ bình thường.

### Lỗi E — “Có evacuation failure là Full GC ngay”

Không nhất thiết. G1 có thể tiếp tục và dọn trong các lần GC sau.

**Sửa:** đọc chuỗi log thực tế và xem liệu collector có tiến triển.

### Lỗi F — “Có Full GC nghĩa là memory leak”

Không đủ bằng chứng. Explicit GC, sudden allocation, humongous fragmentation hoặc live set hợp lệ cũng có thể góp phần.

**Sửa:** dùng heap history, JFR, allocation data và phân tích retained objects.

### Lỗi G — “Full GC luôn cứu được `OutOfMemoryError`”

Không. Live set có thể vẫn quá lớn hoặc không tìm được chỗ cấp phát phù hợp.

**Sửa:** đo retained heap và sửa nguyên nhân, tăng heap khi phù hợp.

### Lỗi H — “Cứ tăng `ParallelGCThreads` là Full GC hết chậm”

Không chắc. Có overhead, contention, giới hạn CPU/container và tác động tới young/mixed pauses.

**Sửa:** đo trên môi trường tương đương production, giữ defaults nếu chưa có bằng chứng.

### Lỗi I — “`MaxGCPauseMillis=100` nghĩa là Full GC dưới 100 ms”

Sai. Đó là mục tiêu mềm của G1, không phải SLA thời gian thực.

**Sửa:** theo dõi pause distribution và mục tiêu tránh Full GC do exhaustion.

### Lỗi J — “Gọi `System.gc()` sau mỗi request sẽ làm ứng dụng khỏe hơn”

Không có cơ sở. Việc này có thể tạo Full GC STW không cần thiết.

**Sửa:** để collector tự quản lý; chỉ gọi trong lab có chủ đích hoặc trường hợp cực kỳ đặc biệt đã kiểm chứng.

### Lỗi K — “`Pause Full (System.gc())` chứng tỏ heap gần cạn”

Sai. Nó là **reason explicit request**, không chỉ ra áp lực memory.

**Sửa:** đọc reason và heap before/after.

### Lỗi L — “Vài dòng `gc+heap` cho biết chắc chắn leak”

Không. Snapshot là dữ liệu tức thời; leak cần bằng chứng retained objects tăng không cần thiết theo thời gian.

**Sửa:** ghép log, heap dump, profiling và workload.

### Lỗi M — “Dùng flags GC cũ từ bài viết Java 8 là ổn”

Một số flag/logging trước Unified Logging đã deprecated hoặc bị loại bỏ.

**Sửa:** dùng `-Xlog:gc*` và tài liệu **đúng phiên bản JDK đang triển khai**.

### Lỗi N — “Humongous objects luôn được copy như object nhỏ trong mixed GC”

Không. G1 xử lý humongous objects khác, thường xác định liveness và reclaim chúng khi đã chết; việc move humongous objects chỉ xảy ra trong tình huống fallback đặc biệt theo tài liệu hiện hành.

**Sửa:** đọc riêng phần Humongous Objects trong tài liệu G1, kiểm region size và fragmentation.

## 24. Checklist vận hành G1 không phụ thuộc giả định lỗi thời

1. **Đã xác minh JVM thật sự đang dùng G1 chưa?**
2. **Có bật `-Xlog:gc*` với rotation/retention hợp lý chưa?**
3. **Có phân biệt Young/Mixed/Concurrent Mark/Full theo reason không?**
4. **Có biết số Full GC và tổng pause time trong khoảng quan sát không?**
5. **Có event `Evacuation Failure: Allocation` hoặc `Pinned` trước đó không?**
6. **Nếu có Full GC, có phải do `System.gc()` hoặc external tool không?**
7. **Old regions và humongous regions đang tăng, ổn định hay giảm?**
8. **Concurrent marking có hoàn tất kịp để bước mixed chạy không?**
9. **Có backlog, cache hoặc batch giữ object sống quá lâu không?**
10. **Đã phân biệt heap live set và native memory/OS memory chưa?**
11. **Có kiểm tình trạng heap sau Full GC sát `-Xmx` không?**
12. **Có hiểu `MaxGCPauseMillis` là target mềm không?**
13. **Có đang khóa young generation gây giảm khả năng tự điều chỉnh của G1 không?**
14. **Đã để mặc định `ParallelGCThreads` trừ khi benchmark chứng minh cần thay chưa?**
15. **Nếu đổi `G1HeapRegionSize`, đã có dữ liệu humongous allocation chưa?**
16. **Có dùng đủ CPU headroom cho concurrent marking không?**
17. **Có nghĩ Full GC song song nghĩa concurrent không?** Nếu có, cần sửa.
18. **Có dùng `System.gc()` chỉ trong môi trường lab thay vì production không?**
19. **Có test trên đúng version/JDK build và CPU/container limits thực tế không?**
20. **Có kiểm memory leak và request latency cùng với số liệu GC không?**
21. **Có tránh bật cờ cũ đã removed/deprecated không?**
22. **Có ghi lại thay đổi cấu hình và benchmark before/after không?**

## 25. Bài tập và đáp án

**Câu 1.** Trong chu trình G1 bình thường, công việc thu hồi old generation chủ yếu do Full GC hay mixed collections thực hiện?

**Câu 2.** Sau một chuỗi young collections, khi old occupancy tăng, bước nào giúp G1 xác định old regions nên được thu hồi?

**Câu 3.** `Concurrent Mark` có đồng nghĩa `Full GC` không?

**Câu 4.** G1 Full GC từ Java 10 có hai tính chất “parallel” và “concurrent” đồng thời không?

**Câu 5.** Tại sao `ParallelGCThreads=2` không có nghĩa có hai luồng ứng dụng tiếp tục chạy trong Full GC?

**Câu 6.** Nếu log có `Pause Full (System.gc())`, có thể kết luận ngay heap thiếu chỗ không?

**Câu 7.** `Evacuation Failure: Allocation` có ý nghĩa gì?

**Câu 8.** Một evacuation failure có chắc dẫn đến Full GC ngay ở lần GC đó không?

**Câu 9.** G1 Full GC làm gì để xử lý heap fragmentation?

**Câu 10.** Vì sao Full GC có thể kết thúc bằng `OutOfMemoryError`?

**Câu 11.** Tại sao nhiều humongous objects có thể làm tăng rủi ro Full GC?

**Câu 12.** Vì sao tăng `-Xmx` có thể hữu ích trong một số trường hợp nhưng không thay thế sửa memory leak?

**Câu 13.** `-XX:MaxGCPauseMillis=200` có buộc mọi Full GC dưới 200 ms không?

**Câu 14.** Làm sao xác định Full GC thật sự sử dụng nhiều GC workers?

**Câu 15.** Vì sao không nên cố benchmark GC bằng chương trình gọi `System.gc()` rồi coi đó là workload production?

**Câu 16.** Theo tài liệu, G1 Full GC là cơ chế bình thường phải xảy ra sau mỗi pha mixed không?

**Câu 17.** Nếu một GC log ghi `Pause Young (Mixed)`, có thể gọi đó là quét toàn heap không?

**Câu 18.** Sự khác nhau giữa `-Xlog:gc*` và `-Xlog:gc+heap=info` là gì?

**Câu 19.** Khi heap sau Full GC vẫn gần `-Xmx`, cần điều tra vấn đề gì?

**Câu 20.** Nếu một service thực sự cần pause cực ngắn và G1 có Full GC kéo dài, nên làm gì trước khi kết luận “chỉ cần tăng worker”?

**Đáp án:**

1. **Mixed collections** (cùng với concurrent marking để chọn regions), không phải Full GC thường xuyên.
2. **Concurrent marking** chuẩn bị thông tin live data để G1 chọn old regions.
3. Không. Marking là phần bình thường của chu trình G1.
4. **Parallel có, concurrent Full GC không**; nó vẫn STW.
5. Hai worker đều là **GC worker**; application threads dừng trong pause.
6. Không. Reason cho thấy có lời gọi explicit GC.
7. Không đủ destination space để di chuyển object trong evacuation.
8. Không. G1 có thể tiếp tục và dọn trong những pauses sau; tình huống xấu mới fallback.
9. **In-place full heap compaction**, di chuyển/tổ chức lại các live objects khi có thể.
10. Vì live objects có thể vẫn chiếm gần hết heap hoặc không đủ chỗ cấp phát sau compaction.
11. Chúng cần dãy regions phù hợp, có thể làm tăng fragmentation và chi phí old-generation.
12. Heap lớn hơn tăng headroom; leak vẫn giữ object và có thể làm heap lại đầy.
13. Không; đó là mục tiêu mềm, không phải hard latency guarantee.
14. Tìm log về số worker, ví dụ `Using 2 workers of 2 for full compaction`.
15. `System.gc()` là yêu cầu nhân tạo và có thể được xử lý khác production; không đo được pressure/throughput thực.
16. Không. Full GC là fallback/explicit operation, không phải pha bắt buộc sau mixed.
17. Không. Mixed chỉ thu young và **một phần old regions**.
18. `gc*` cho sự kiện GC rộng hơn; `gc+heap` tập trung thông tin heap/regions theo level chọn.
19. Live set lớn, retention/leak, insufficient heap hoặc allocation patterns.
20. Đọc logs, reason, workload, heap, JFR và thử sizing/code fixes; sau đó mới cân nhắc JVM tuning hay collector khác theo SLA.

## 26. Tổng kết

- G1 là collector **generational, incremental, parallel và mostly concurrent**, không phải “mọi hoạt động đều concurrent”.
- Chu trình chính là **young collections → concurrent marking → mixed collections**; **Full GC** là fallback khi không thu hồi đủ không gian hoặc do một số yêu cầu explicit.
- Full GC của G1 làm **stop-the-world full heap compaction**; **từ Java 10, JEP 307 song song hóa nó** để giảm worst-case latency.
- **Parallel ≠ concurrent**: nhiều GC worker không giúp Java application threads tiếp tục chạy trong Full GC.
- **Evacuation failure** có thể báo Allocation/Pinned; không phải mọi thất bại đều ngay lập tức tạo Full GC.
- Old occupancy cao, marking chậm, thiếu free regions và humongous allocation có thể tạo áp lực dẫn đến Full GC.
- **`System.gc()`** có thể tạo Full GC dù heap không đầy; chỉ dùng có chủ đích trong lab và không xem nó là cách tối ưu production.
- Dùng **`-Xlog:gc*`**, phân tích **Pause Full reason**, số workers, trước/sau heap và các GC trước đó để xác định nguyên nhân.
- **`MaxGCPauseMillis` không bảo đảm Full GC ngắn**, Full GC không bảo đảm tránh OOME. Mục tiêu là giảm nhu cầu fallback thông qua thiết kế memory và sizing phù hợp.
- Hướng dẫn còn áp dụng trên Java hiện đại; không cần/không nên dựa vào flags GC đã legacy.

## 27. Tài liệu chính thức

1. [Oracle Java SE 26 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html): mô hình regions, young/mixed, concurrent marking, evacuation failure, Full GC fallback và humongous objects.
2. [Oracle Java SE 26 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): Full GC, G1 Compaction Pause, evacuation failure, tuning dựa trên logs, explicit GC.
3. [OpenJDK JEP 307 — Parallel Full GC for G1](https://openjdk.org/jeps/307): mục tiêu Java 10 và giải pháp song song hóa Full GC của G1.
4. [Oracle Java SE 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): cú pháp `-XX:+UseG1GC`, `-XX:ParallelGCThreads`, `-XX:MaxGCPauseMillis` và `-Xlog`.
5. [Oracle Java SE 26 — Garbage Collector Implementation](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-collector-implementation.html): ví dụ Unified Logging và cách diễn giải `gc+task`, `gc+cpu`.
6. [Oracle Java SE 26 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/): phân tích sự cố, GC logs, JFR và heap diagnostics.
