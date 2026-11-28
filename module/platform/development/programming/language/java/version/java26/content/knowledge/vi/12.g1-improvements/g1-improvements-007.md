# Ảnh hưởng của kiểu tải, tần suất ghi và dung lượng heap

Cải tiến G1 trong JDK 26 có lợi rõ nhất khi ứng dụng thường xuyên ghi các tham chiếu đối tượng vào heap. JEP 522 thay đổi cách G1 phối hợp giữa application thread và các thread tối ưu card table: thay vì cùng tranh chấp một bảng, G1 dùng hai card table để tách vùng ghi của ứng dụng khỏi vùng đang được xử lý nền. Kết quả benchmark được công bố cho thấy throughput tăng khoảng 5–15% với workload cập nhật tham chiếu nhiều; workload cập nhật tham chiếu nhẹ cũng có thể tăng tới khoảng 5%. Đổi lại, G1 dùng thêm native memory xấp xỉ 0,2% dung lượng heap.

Mức cải thiện phụ thuộc vào kiểu tải thực tế. Một ứng dụng tạo nhiều object ngắn hạn nhưng ít thay đổi reference có thể không nhận được lợi ích lớn từ JEP 522. Ứng dụng thường xuyên cập nhật graph đối tượng, cache, index hoặc quan hệ giữa các entity có khả năng hưởng lợi rõ hơn. Dung lượng heap lại tác động đến số card cần quản lý, thời gian G1 có để hoàn tất marking, tần suất collection và bộ nhớ native cần dành cho JVM.

Bài này giúp phân loại workload, hiểu mối quan hệ giữa reference writes, allocation rate và heap size, sau đó thiết kế phép đo để xác định thay đổi có cải thiện throughput và latency trên môi trường đích hay không.

## 1. G1 theo dõi những thay đổi nào trong heap?

G1 chia Java heap thành các region. Mỗi region có thể thuộc young generation hoặc old generation. Khi một collection chọn một nhóm region để thu hồi, G1 phải biết những object nằm ngoài nhóm đó có tham chiếu vào object bên trong hay không. Thông tin này được lưu qua remembered set.

G1 dùng card table để ghi nhận các vùng heap có thể chứa reference cần được xem xét. Một card đại diện cho một vùng bộ nhớ nhỏ; kích thước card mặc định là 512 byte. Khi code Java ghi một reference vào field hoặc phần tử array, write barrier do JVM chèn vào có thể đánh dấu card tương ứng là dirty. G1 refinement thread xử lý các card đã dirty để cập nhật remembered set.

Luồng khái quát:

1. Application thread ghi reference vào heap.
2. Write barrier đánh dấu card chứa vị trí được ghi.
3. G1 refinement thread đọc card đã dirty và cập nhật thông tin remembered set.
4. Khi collection xảy ra, G1 dùng remembered set để tìm các reference đi vào collection set.
5. G1 quét root, di chuyển object còn sống và thu hồi region.

Card table không lưu từng reference như một danh sách đầy đủ. Nó đánh dấu vùng có khả năng chứa reference cần xử lý, giúp giảm bộ nhớ và chi phí quét.

## 2. JEP 522 thay đổi gì trong JDK 26?

Trước cải tiến JEP 522, application thread và công việc tối ưu card table nền phải phối hợp trên cùng card table. Khi workload cập nhật reference dày đặc, hoạt động ghi và refinement có thể tạo ra tranh chấp đồng bộ. Chi phí này nằm trên đường chạy của application thread, nên có thể làm giảm throughput và ảnh hưởng latency.

JDK 26 bổ sung card table thứ hai:

- Application thread luôn ghi vào card table đang active, không cần đồng bộ với thread tối ưu bảng còn lại.
- Refinement thread làm việc trên card table kia, ban đầu là bảng rỗng.
- Khi G1 dự đoán việc quét active table có thể vượt mục tiêu pause, JVM hoán đổi vai trò hai bảng bằng thao tác atomic.
- Bảng vừa được application thread sử dụng trở thành bảng để refinement xử lý; bảng còn lại trở thành active table mới.

Mô hình này tách hoạt động ghi của mutator khỏi công việc xử lý card nền. G1 vẫn duy trì remembered set và quy trình collection như trước; thay đổi chủ yếu nằm trong cách phối hợp card table và write barrier.

JEP 522 là cải tiến nội bộ của G1 trong JDK 26. Không có API Java mới và không cần cờ bật riêng. Nếu JVM thực sự đang chạy G1 trên JDK 26, cải tiến được áp dụng tự động. Nếu ứng dụng dùng ZGC, Parallel GC hoặc Serial GC thì JEP 522 không tác động đến collector đó.

### 2.1. Mức cải thiện đã được công bố

Các kết quả benchmark được nêu trong tài liệu JEP 522 và bài tổng hợp hiệu năng JDK 26:

| Kiểu workload | Kết quả được báo cáo |
|---|---:|
| Cập nhật reference nhiều | Throughput tăng khoảng 5–15% |
| Cập nhật reference nhẹ trên x64 | Có thể tăng tới khoảng 5% |
| Write barrier trên x64 trong trường hợp được đo | Số instruction giảm từ khoảng 50 xuống khoảng 12 |
| Chi phí bộ nhớ bổ sung | Khoảng 0,2% heap, tương đương khoảng 2 MB native cho mỗi 1 GB heap |

Đây là kết quả của workload và nền tảng benchmark cụ thể, không phải cam kết cho mọi ứng dụng. Tỷ lệ cải thiện có thể thấp hơn hoặc không đáng kể nếu bottleneck nằm ở allocation, I/O, lock ứng dụng, CPU computation hoặc memory bandwidth.

## 3. Phân biệt tần suất ghi reference với allocation rate

Hai chỉ số này thường tăng cùng nhau trong một số ứng dụng nhưng mô tả hai loại công việc khác nhau.

- **Allocation rate** là tốc độ tạo object mới, thường đo bằng byte/giây hoặc object/giây.
- **Reference write rate** là tần suất ghi hoặc thay thế tham chiếu trong field và array của object.
- **Promotion rate** là tốc độ object chuyển từ young generation sang old generation.
- **Live set** là lượng object còn sống tại một thời điểm hoặc sau collection.

Ví dụ:

~~~java
final class Account {
    Object currentSession;
    Object cachedResult;
    long requestCount;
}

Account account = new Account();

// Ghi primitive: không phải reference store.
account.requestCount++;

// Ghi reference: write barrier có thể đánh dấu card.
account.currentSession = new Object();
~~~

Tăng requestCount chỉ cập nhật một giá trị primitive. Gán currentSession thay đổi reference trong heap và đi qua cơ chế write barrier của G1.

Một workload có thể tạo hàng triệu object nhưng chỉ ghi reference lúc khởi tạo; workload khác có thể tạo ít object mới nhưng liên tục thay reference trong các object tồn tại lâu. Hai workload này tạo áp lực khác nhau lên G1.

| Kiểu hoạt động | Áp lực chính | JEP 522 có liên quan trực tiếp? |
|---|---|---|
| Tạo nhiều object ngắn hạn | Eden allocation và young GC | Không phải mục tiêu chính |
| Tạo nhiều object sống lâu, promotion cao | Old generation occupancy và concurrent marking | Có thể có lợi nếu đồng thời ghi nhiều reference |
| Liên tục thay reference trong object graph | Write barrier và card refinement | Có, đây là nhóm phù hợp |
| Ghi nhiều primitive vào mảng số | CPU và memory bandwidth | Ít liên quan |
| Đọc reference nhiều nhưng hiếm khi ghi | Memory access và cache locality | Không phải mục tiêu chính |
| Ghi reference vào nhiều vùng heap khác nhau | Dirty-card và remembered-set update | Có khả năng hưởng lợi |

Không dùng số lần gán reference thô làm dự báo duy nhất. G1 đánh dấu card, không tạo một record riêng cho mỗi phép gán. Nhiều lần ghi trên cùng card trước khi card được xử lý có thể được gộp thành một vùng dirty. Phân bố ghi trên heap, số card bị dirty, quan hệ giữa region và tốc độ refinement đều ảnh hưởng đến chi phí thực tế.

## 4. Kiểu workload nào có thể hưởng lợi nhiều hơn?

### 4.1. Cache và index thường xuyên thay thế reference

Một cache có thể liên tục thay giá trị gắn với key:

~~~java
final class CacheSlot {
    Object value;
}

CacheSlot[] slots = new CacheSlot[100_000];

// Trong luồng xử lý request:
slots[index].value = result;
~~~

Nếu các slot tồn tại lâu và được nhiều thread cập nhật liên tục, reference writes có thể tạo áp lực lên card table. JEP 522 giảm đồng bộ giữa đường ghi của ứng dụng và refinement nền.

Kết quả thực tế vẫn phụ thuộc vào cách phân bố slot, object lifetime, số thread và số card bị dirty. Một cache có lock toàn cục hoặc contention ở tầng ứng dụng có thể bị giới hạn bởi lock trước khi card-table overhead trở thành bottleneck.

### 4.2. Object graph và quan hệ entity thay đổi thường xuyên

Ứng dụng quản lý graph đối tượng, session, entity relationship hoặc cấu trúc cây có thể thường xuyên cập nhật các reference:

~~~java
node.left = replacementLeft;
node.right = replacementRight;
parent.child = newChild;
entity.owner = newOwner;
~~~

Nếu các object cha sống lâu và liên tục trỏ đến object mới hoặc object ở region khác, write barrier và remembered-set refinement có thể trở thành một phần đáng kể của CPU time. Đây là loại workload đáng đưa vào benchmark khi nâng cấp lên JDK 26.

Không phải mọi thay đổi graph đều tạo cùng chi phí. Nếu object được tạo và liên kết hoàn toàn trong young generation rồi chết sớm, áp lực có thể khác với việc ghi reference từ object sống lâu ở old generation sang object ở region khác.

### 4.3. Workload allocation-heavy nhưng ít mutation

Một parser hoặc pipeline chuyển đổi dữ liệu có thể tạo rất nhiều object tạm thời, nhưng sau khi tạo xong thì ít thay đổi reference. Bottleneck chính có thể là tốc độ allocation, số young collection và lượng object sống sót sau mỗi collection.

JEP 522 không làm giảm số byte ứng dụng yêu cầu cấp phát và cũng không làm object chết sớm hơn. Với kiểu workload này, hãy đo allocation rate, object survival, promotion và pause của young collection trước khi kỳ vọng cải thiện lớn từ JEP 522.

### 4.4. Workload số học trên primitive array

Một phép tính trên int[], long[], float[] hoặc double[] chủ yếu đọc và ghi primitive values. G1 không cần ghi nhận các primitive value như một heap reference. Vì vậy, cải tiến card-table write barrier không phải lý do chính để kỳ vọng throughput của vòng lặp số học tăng.

Nếu workload này chậm, hãy kiểm tra JIT compilation, vectorization, memory bandwidth, cache locality và khả năng sử dụng Vector API; không quy mọi thay đổi hiệu năng của JDK 26 cho JEP 522.

## 5. Tần suất ghi và phân bố ghi quan trọng như thế nào?

Hai ứng dụng có cùng số lần ghi reference mỗi giây vẫn có thể tạo chi phí card refinement khác nhau.

| Mẫu ghi | Đặc điểm | Cần quan sát |
|---|---|---|
| Nhiều lần ghi lặp vào một số ít object/card | Có thể nhiều lần ghi được gộp ở mức card | Số pending cards và thời gian refinement |
| Ghi phân tán trên nhiều card | Nhiều vùng heap cần được xử lý | Scan Heap Roots và chi phí remembered set |
| Nhiều thread ghi đồng thời | Có thể tăng cạnh tranh trên đường write barrier và cache coherence | CPU application, throughput và latency |
| Ghi reference từ object sống lâu sang object mới | Có thể tạo liên kết qua generation/region | Promotion, dirty cards và refinement backlog |
| Ghi reference trong object ngắn hạn rồi object sớm chết | Tác động có thể thấp hơn nếu object không tồn tại qua collection | Young GC và object survival |
| Đọc nhiều, ghi ít | Ít tạo dirty card mới | Cache miss và memory bandwidth |

Không nên suy ra rằng mọi phép gán reference đều gây một lần refinement ngay lập tức. Write barrier đánh dấu card; refinement thường diễn ra bất đồng bộ. Nếu ứng dụng ghi nhanh hơn khả năng xử lý nền, số pending cards có thể tăng và G1 có thể phải xử lý thêm công việc trong pause.

JEP 522 giảm đồng bộ trên đường ghi, nhưng không loại bỏ công việc cần thiết để duy trì remembered set. Nếu heap có nhiều reference chéo region, G1 vẫn cần quét và hợp nhất thông tin đó khi collection.

## 6. Dung lượng heap ảnh hưởng đến hiệu năng ra sao?

Dung lượng heap ảnh hưởng cả bộ nhớ dành cho ứng dụng và cấu trúc quản lý của G1.

### 6.1. Chi phí card table tăng theo heap

JEP 522 bổ sung một card table, với chi phí được báo cáo xấp xỉ 0,2% dung lượng heap dưới dạng native memory.

| Heap capacity | Native memory bổ sung ước tính |
|---:|---:|
| 1 GB | 2 MB |
| 4 GB | 8 MB |
| 8 GB | 16 MB |
| 16 GB | 32 MB |
| 32 GB | 64 MB |
| 64 GB | 128 MB |

Đây là ước lượng theo tỷ lệ được công bố, không phải số đo chính xác của mọi JVM. Bộ nhớ này nằm ngoài Java heap. Khi triển khai trong container, phải tính nó cùng metaspace, code cache, thread stacks, direct buffers và các vùng native khác trong giới hạn memory của tiến trình.

Không lấy -Xmx làm tổng mức RAM cần cấp cho container. Nếu container chỉ có đúng lượng RAM bằng -Xmx, phần native memory có thể làm tiến trình vượt giới hạn.

### 6.2. Heap quá nhỏ tạo áp lực collection

Khi heap nhỏ so với live set và allocation rate:

- Eden nhanh đầy và young collection xuất hiện thường xuyên.
- Old generation có thể tăng nhanh do object được promote.
- Concurrent marking có ít thời gian hơn để hoàn tất trước khi old generation cạn vùng trống.
- Evacuation failure hoặc Full GC có thể xuất hiện nếu G1 không có đủ vùng đích.

Tăng heap có thể tạo thêm headroom và thời gian cho concurrent marking. Tuy nhiên, tăng heap không sửa được việc ứng dụng tạo quá nhiều object sống lâu, giữ reference không cần thiết hoặc cấp phát object khổng lồ liên tục.

### 6.3. Heap lớn không tự động nhanh hơn

Heap lớn có thể giảm tần suất collection, nhưng cũng tăng footprint và có thể giữ nhiều live data hơn. G1 phải quản lý các region, remembered set và object sống lâu. Nếu object graph có nhiều reference chéo region, chi phí quét remembered set vẫn có thể đáng kể.

G1 tự điều chỉnh heap trong giới hạn min/max dựa trên hành vi ứng dụng và mục tiêu GC. Vì vậy, hãy bắt đầu với ergonomic defaults, chỉ đặt -Xmx hoặc -Xms khi có yêu cầu bộ nhớ hoặc kết quả đo cụ thể.

### 6.4. Region size và object lớn

G1 chia heap thành các region có kích thước được chọn tự động dựa trên heap tối đa; mục tiêu mặc định thường vào khoảng 2.048 region. Region size do JVM chọn có thể khác nhau theo -Xmx.

Object có kích thước bằng hoặc lớn hơn một nửa region được xem là humongous object. Chúng được cấp phát trong old generation qua một chuỗi region liền kề; phần dư của region cuối có thể bị lãng phí cho đến khi object được thu hồi.

Nếu log cho thấy nhiều humongous regions hoặc fragmentation, có thể xem xét giảm kích thước object, thay đổi cách lưu buffer hoặc thử -XX:G1HeapRegionSize. Region lớn hơn có thể giảm số object bị phân loại humongous và giảm cross-region references, nhưng cũng có thể khiến mỗi region chứa nhiều live object hơn và tăng thời gian evacuation. Chỉ thay đổi sau khi có bằng chứng từ log.

## 7. Đọc log để phân biệt vấn đề reference writes, allocation và heap

Bắt đầu bằng Unified GC Logging:

~~~sh
java \
  -Xlog:gc*=debug:file=gc.log:time,uptime,level,tags \
  -Xms4g -Xmx4g \
  -jar application.jar
~~~

Ví dụ này cố định heap ở 4 GB để làm phép so sánh có kiểm soát. Không nhất thiết nên đặt -Xms bằng -Xmx cho mọi production workload; cấu hình cố định làm giảm biến động do heap resize nhưng tăng lượng heap được dành sẵn.

Một số log hữu ích:

~~~sh
-Xlog:gc+heap=info
-Xlog:gc+phases=debug
-Xlog:gc+cpu=info
-Xlog:gc+ergo+cset=debug
~~~

| Log | Câu hỏi cần trả lời |
|---|---|
| gc+heap=info | Heap và các generation đang dùng bao nhiêu region? Có bao nhiêu humongous regions? |
| gc+phases=debug | Pause mất thời gian ở phase nào? Scan Heap Roots, Merge Heap Roots hay Object Copy có nổi bật không? |
| gc+cpu=info | Thời gian pause nằm ở VM CPU, system CPU hay thời gian thực do hệ điều hành scheduling? |
| gc+ergo+cset=debug | G1 dự đoán collection set và thời gian evacuation như thế nào? |
| gc*=debug | Có diễn biến gì trước, trong và giữa các collection? |

Trong Scan Heap Roots, chú ý Pending Cards so với Scanned Cards. Pending Cards cao có thể cho thấy còn nhiều công việc refinement cần xử lý trong pause. Kết hợp chỉ số này với thời gian concurrent refinement, throughput ứng dụng và CPU utilization để xác định có áp lực remembered set hay không.

Không có một dòng log đơn lẻ nào đo trực tiếp toàn bộ số reference writes trong ứng dụng. GC log giúp nhận diện công việc G1 phải xử lý; muốn quy nguyên nhân về write frequency, cần benchmark workload có kiểm soát hoặc profiler CPU.

## 8. Thiết kế phép đo theo kiểu tải

Để đánh giá JEP 522, không chỉ so sánh một lần khởi động trước và sau nâng cấp. Cần giữ các yếu tố khác ổn định và thay đổi một trục workload mỗi lần.

### 8.1. Tạo các nhóm workload đối chiếu

| Nhóm thử nghiệm | Hành vi | Mục đích |
|---|---|---|
| A — Allocation-heavy | Tạo nhiều object tạm, ít cập nhật reference vào object sống lâu | Đo tác động chủ yếu từ allocation và young GC |
| B — Reference-write-heavy | Cập nhật liên tục field/array reference của object sống lâu | Kiểm tra nhóm workload JEP 522 nhắm tới |
| C — Primitive-write-heavy | Ghi nhiều số nguyên hoặc số thực vào array | Làm nhóm đối chứng ít liên quan đến card-table reference writes |
| D — Mixed | Vừa cấp phát object, vừa thay reference thường xuyên | Quan sát lợi ích khi nhiều nguồn áp lực cùng tồn tại |
| E — Large live set | Giữ nhiều object sống lâu và quan hệ chéo region | Quan sát remembered set, marking và heap headroom |

Khi xây dựng workload B, giữ các object chứa reference đủ lâu để chúng được promote; nếu chỉ tạo object mới rồi bỏ ngay, bài đo có thể chủ yếu phản ánh allocation. Khi xây dựng workload C, dùng primitive array để tách chi phí ghi dữ liệu khỏi reference write barrier.

### 8.2. So sánh JDK trong cùng điều kiện

1. Chạy cùng ứng dụng và cùng input trên JDK trước đó và JDK 26.
2. Giữ cùng CPU, số core được cấp, container limit, hệ điều hành và phiên bản ứng dụng.
3. Giữ cùng -Xms, -Xmx, collector và các tùy chọn GC khác.
4. Warmup đến khi JIT và workload ổn định.
5. Chạy đủ lâu để quan sát nhiều chu kỳ young, mixed và concurrent marking.
6. Lặp lại nhiều lần và so sánh median, p95/p99 thay vì chỉ chọn lần nhanh nhất.
7. Ghi nhận throughput, request latency, GC CPU, pause distribution, allocation rate, promotion rate, heap occupancy và native memory.
8. Chỉ thay đổi heap size sau khi đã có baseline với cùng heap capacity.

JEP 522 được kỳ vọng chủ yếu cải thiện throughput trên workload ghi reference. Pause có thể giảm nhẹ, nhưng không nên chỉ dùng p99 pause để kết luận. Nếu throughput tăng trong khi pause không đổi nhiều, kết quả đó vẫn phù hợp với mục tiêu của cải tiến.

### 8.3. Dùng profiler và tải ứng dụng thực

JMH phù hợp để đo một đoạn code cô lập như vòng lặp cập nhật reference, nhưng benchmark micro không thay thế load test của dịch vụ thực. Với ứng dụng nhiều thread, cache, ORM hoặc graph mutation, cần chạy integration/load test để giữ nguyên phân bố object lifetime và quan hệ region.

Kết hợp:
- JMH cho kernel hoặc thao tác nhỏ có thể cô lập.
- Unified GC log cho hoạt động collection và remembered set.
- JFR hoặc profiler CPU để xem thời gian ứng dụng tiêu thụ trong write barrier/refinement và các phần code khác.
- Load test để kiểm tra throughput và latency theo concurrency gần production.

Không dùng một benchmark tạo object mới liên tục rồi kết luận JEP 522 có hoặc không có lợi cho ứng dụng reference-heavy. Workload phải tái hiện đúng nơi và cách reference được cập nhật.

## 9. Tuning khi đã xác định bottleneck

G1 được thiết kế để hoạt động tốt với mặc định. Chỉ thay đổi tham số sau khi log chỉ ra một vấn đề cụ thể.

### 9.1. Khi throughput là mục tiêu chính

-XX:MaxGCPauseMillis là mục tiêu mềm. Nới lỏng mục tiêu pause có thể giúp G1 tăng kích thước young generation và giảm tần suất collection, từ đó cải thiện throughput. Đổi lại, pause có thể dài hơn.

Không cố định young generation bằng -Xmn hoặc -XX:NewRatio nếu vẫn muốn G1 điều chỉnh tự động theo pause target. Oracle khuyến nghị tránh các thiết lập này trong cấu hình G1 thông thường.

### 9.2. Khi concurrent refinement chiếm nhiều CPU

-XX:G1RSetUpdatingPauseTimePercent điều khiển lượng remembered-set refinement được xử lý trong pause so với xử lý concurrent. Tăng giá trị có thể giảm lượng refinement chạy đồng thời với application thread, nhưng chuyển thêm việc vào pause. Giảm giá trị có thể tăng lượng refinement chạy concurrent.

Chỉ thử thay đổi khi log gc+phases=debug cho thấy pending cards và Scan Heap Roots đáng kể, đồng thời profiler cho thấy refinement đang cạnh tranh CPU với ứng dụng. Đo lại cả throughput và pause sau mỗi thay đổi.

Không tắt concurrent refinement chỉ để tăng throughput nếu ứng dụng có yêu cầu latency thấp; chuyển toàn bộ công việc vào pause có thể làm pause tăng đáng kể.

### 9.3. Khi Full GC xuất hiện do thiếu headroom

Kiểm tra:
- Old generation occupancy và tốc độ promotion.
- Thời gian concurrent marking so với tốc độ cấp phát.
- Evacuation failure với lý do Allocation.
- Humongous regions và fragmentation.
- -Xmx so với giới hạn RAM thực của container/host.

Có thể tăng heap nếu hệ thống còn đủ RAM, cho marking thêm thời gian hoặc giảm allocation của object sống lâu. Nếu workload thay đổi nhanh, adaptive IHOP có thể cần thời gian học lại; chỉ điều chỉnh IHOP sau khi hiểu log và hành vi của ứng dụng.

### 9.4. Khi remembered-set scan chiếm nhiều thời gian

Nếu Merge Heap Roots hoặc Scan Heap Roots chiếm tỷ trọng lớn trong pause, hãy kiểm tra cross-region references và số pending cards. Region lớn hơn có thể giảm số cross-region references nhưng cũng có thể làm tăng số live object phải evacuation trong một region. Đây là đánh đổi cần benchmark, không phải quy tắc luôn tăng region size.

## 10. Ví dụ đọc kết quả theo tình huống

| Quan sát | Cách diễn giải | Bước tiếp theo |
|---|---|---|
| Throughput tăng trên workload B, gần như không đổi trên A và C | Phù hợp với lợi ích giảm chi phí reference-write barrier | Giữ cấu hình và xác nhận bằng load test production-like |
| Allocation rate cao, young GC dày, B không có lợi rõ | Bottleneck có thể nằm ở allocation/young collection thay vì card-table synchronization | Giảm object tạm, kiểm tra survival/promotion và heap |
| Pending Cards cao, Scan Heap Roots tăng | Refinement chưa theo kịp hoặc remembered-set work lớn | Kiểm tra reference-write pattern, số cross-region references và concurrency |
| Heap occupancy cao, concurrent marking kết thúc muộn | Headroom không đủ so với live set và allocation trong thời gian marking | Kiểm tra promotion, humongous objects, heap max và thời điểm IHOP |
| Nhiều humongous regions | Object lớn có thể gây fragmentation hoặc chiếm nhiều region | Giảm object lớn, dùng buffer/chunk phù hợp; chỉ thử region size khi có dữ liệu |
| CPU tăng nhưng pause giảm nhẹ | Có thể do concurrent GC/refinement cạnh tranh tài nguyên | Đối chiếu CPU của application và GC, không chỉ pause time |
| Native memory tăng gần tỷ lệ heap | Có thể bao gồm card table thứ hai của JEP 522 | So sánh native memory trên cùng heap và kiểm tra các nguồn native khác |

## 11. Những hiểu nhầm cần tránh

- JEP 522 không làm mọi phép ghi nhanh hơn; nó nhắm vào đồng bộ card table của G1 khi cập nhật reference.
- Allocation rate và reference-write rate là hai chỉ số khác nhau.
- Primitive writes vào int[] hoặc float[] không tạo cùng loại reference barrier như gán object reference.
- Số lần gán reference không đồng nghĩa số card phải refinement; nhiều ghi có thể cùng nằm trong một card.
- JEP 522 không loại bỏ remembered set, write barrier hoặc công việc scan card.
- Heap lớn hơn không tự động làm ứng dụng nhanh hơn; cần tính live set, allocation rate, native memory và giới hạn container.
- G1 không phải real-time collector; MaxGCPauseMillis là mục tiêu mềm, không phải cam kết cho từng pause.
- JEP 522 không cần cờ bật riêng và không tác động nếu ứng dụng không chạy G1.
- Tăng G1RSetUpdatingPauseTimePercent có thể giảm concurrent work nhưng tăng công việc trong pause; phải đo cả hai mặt.
- Không thay đổi nhiều cờ GC cùng lúc vì sẽ không biết yếu tố nào tạo ra kết quả.

## 12. Checklist đánh giá workload và heap

- [ ] Xác nhận JVM thực sự dùng G1 trên JDK 26.
- [ ] Phân loại workload: allocation-heavy, reference-write-heavy, primitive-write-heavy, mixed hoặc large live set.
- [ ] Đo riêng allocation rate, promotion rate và live set.
- [ ] Xác định object sống lâu nào thường xuyên thay đổi reference.
- [ ] Xem reference writes tập trung trên ít card hay phân tán trên nhiều vùng heap.
- [ ] Tính native-memory budget, bao gồm chi phí card table bổ sung xấp xỉ 0,2% heap.
- [ ] Thu thập -Xlog:gc*=debug và log phase khi cần.
- [ ] Kiểm tra Pending Cards, Scan Heap Roots, Merge Heap Roots và humongous regions.
- [ ] So sánh JDK cũ và JDK 26 với cùng phần cứng, heap, collector, input và concurrency.
- [ ] Đo throughput, p50/p95/p99 latency, GC CPU, pause và native memory.
- [ ] Chỉ tuning region size, pause goal hoặc refinement sau khi có bằng chứng.
- [ ] Kiểm tra lại bằng load test gần production trước khi áp dụng cấu hình mới.

## Tài liệu tham khảo

- [JEP 522 — G1 GC Improves Throughput by Reducing Synchronization](https://openjdk.org/jeps/522): thiết kế hai card table và mục tiêu giảm đồng bộ giữa mutator và refinement.
- [Performance Improvements in JDK 26 — Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/): kết quả benchmark throughput, số instruction write barrier và chi phí native memory.
- [Java SE 26 — Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html): region, card, remembered set, heap sizing và ergonomic defaults.
- [Java SE 26 — Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): chẩn đoán Full GC, humongous objects, throughput, pause và remembered-set refinement.
- [Java SE 26 — Ergonomics](https://docs.oracle.com/en/java/javase/26/gctuning/ergonomics.html): cách JVM chọn collector, heap và điều chỉnh theo hành vi ứng dụng.

