# Old collection: theo dõi và chẩn đoán thu gom Old Generation

**Old collection** là hoạt động garbage collection có tác động tới vùng **Old Generation** của Java heap. Các object sống đủ lâu có thể được promote từ Young Generation sang Old Generation; khi vùng này tăng occupancy, JVM cần xác định object nào còn reachable và thu hồi vùng nhớ do object không còn được sử dụng chiếm giữ.

Trong HotSpot, thuật ngữ và cách thu hồi Old Generation phụ thuộc garbage collector. Với G1, việc thu hồi old regions thường diễn ra tăng dần qua nhiều **Mixed collections** sau một chu kỳ concurrent marking. Với Serial hoặc Parallel GC, old-generation collection thường gắn với một lần thu gom old generation toàn vùng. Vì vậy, không nên đồng nhất mọi old collection với một **Full GC**.

JFR cũng định nghĩa event `jdk.OldGarbageCollection`, cung cấp thời điểm, thời lượng và GC identifier cho old garbage collection khi collector phát event đó. Bài học này giải thích cách đọc event và GC log, xác định tác động lên pause time, và phân biệt áp lực bộ nhớ với memory leak.

## 1. Old Generation nằm ở đâu trong Java heap?

Các collector generational chia Java heap thành những vùng có vai trò khác nhau:

- **Eden:** nơi phần lớn object mới được cấp phát.
- **Survivor:** nơi object còn sống sau young collection có thể tiếp tục tồn tại trước khi được promote.
- **Old Generation:** nơi chứa object đã sống qua đủ số lần collection hoặc được cấp phát trực tiếp vào old space theo chính sách của collector.

Khi young collection xảy ra, JVM tìm object còn reachable trong Eden và Survivor. Object sống có thể được copy sang Survivor hoặc promote sang Old Generation. Object không còn reachable có thể được thu hồi.

Old Generation thường chứa object có lifetime dài hơn như cache, session, cấu trúc dữ liệu dùng chung và trạng thái ứng dụng. Tuy nhiên, tuổi của object không chứng minh object còn cần thiết: một reference bị giữ ngoài ý muốn cũng khiến object sống lâu và chiếm old space.

**Live set** là lượng heap còn được sử dụng sau khi các object không reachable đã được thu hồi. Theo dõi live set qua nhiều collection dưới workload ổn định là cách hữu ích để nhận biết old space có đang tăng bất thường hay không.

## 2. Old collection, young collection và Full GC

Các thuật ngữ thường gặp:

| Thuật ngữ | Ý nghĩa |
|---|---|
| Young collection | Thu gom các vùng thuộc Young Generation, thường là Eden và Survivor. |
| Old collection | Thu gom hoặc reclaim vùng thuộc Old Generation; cách thực hiện tùy collector. |
| Mixed collection | Với G1, một pause thu gom cả young regions và một tập old regions đã được chọn. |
| Full GC | Thu gom toàn bộ Java heap; thường có pause lớn và có thể compact heap. |
| Concurrent marking | Pha đánh dấu object còn sống, phần lớn chạy đồng thời với application threads trong G1. |

Trong tài liệu cũ, **minor GC** thường chỉ young collection và **major GC** thường chỉ old-generation collection. Hai cách gọi này không có một ý nghĩa thống nhất cho mọi collector và phiên bản JVM. Khi đọc log, hãy dựa vào loại collection, GC cause, phase và collector cụ thể.

Một Full GC có thể thu hồi old generation, nhưng một lần old collection không nhất thiết là Full GC. G1 là ví dụ rõ nhất: nó có thể reclaim old regions qua nhiều Mixed collections mà không cần Full GC toàn heap.

## 3. Vì sao Old Generation cần được thu gom?

Old collection có thể xuất hiện khi:

- Old Generation tiến gần ngưỡng occupancy khiến collector cần bắt đầu chu kỳ marking hoặc reclaim.
- Nhiều object từ young generation sống sót và được promote.
- Application tạo nhiều object có lifetime dài hoặc giữ reference lâu.
- Large/humongous objects chiếm nhiều old regions.
- Collector không reclaim kịp tốc độ cấp phát hoặc promotion.
- JVM nhận yêu cầu explicit GC từ `System.gc()` hoặc một công cụ bên ngoài.
- Một công cụ chẩn đoán yêu cầu heap statistics hoặc thao tác cần old/full collection.

Old collection không tự động có nghĩa là lỗi. Một collection định kỳ có thể là hoạt động bình thường. Cần đánh giá tần suất, pause duration, lượng bộ nhớ thu hồi và live set sau collection.

## 4. Cách các garbage collector xử lý Old Generation

| Collector | Cách xử lý old space | Điều cần chú ý |
|---|---|---|
| Serial GC | Thu gom old generation trong các pha stop-the-world; Full GC có thể compact heap. | Pause phụ thuộc kích thước heap và lượng object sống. |
| Parallel GC | Có thể reclaim và compact old generation như một khối trong Full GC. | Throughput cao, nhưng old/full pause có thể dài. |
| G1 GC | Mark old regions đồng thời với application, sau đó reclaim một tập old regions qua nhiều Mixed collections. | Phân biệt Mixed collection với Full GC fallback. |
| ZGC và Shenandoah | Dùng các pha concurrent và cơ chế reclaim riêng; generation và event/log naming phụ thuộc chế độ, phiên bản. | Không suy luận pause model chỉ từ cụm từ “old collection”. |

Các event và tag log cũng phụ thuộc collector. Nếu một recording không có `jdk.OldGarbageCollection`, vẫn có thể phân tích `jdk.GarbageCollection`, GC logs và các event phase mà collector cung cấp.

## 5. G1: chu kỳ reclaim Old Generation

G1 chia heap thành các **region**. Eden, Survivor và Old là những nhóm region logic, không nhất thiết nằm liền nhau trong địa chỉ bộ nhớ.

Chu kỳ G1 có hai pha lớn:

1. **Young-Only phase:** G1 thực hiện young collections và promote object sống vào old regions.
2. **Space-Reclamation phase:** sau khi concurrent marking hoàn tất, G1 thực hiện nhiều Mixed collections để thu hồi thêm old regions.

Một chu kỳ marking điển hình gồm:

- **Concurrent Start:** một young pause đồng thời khởi động quá trình marking.
- **Concurrent marking:** xác định các object còn sống trong old regions, phần lớn chạy song song với application.
- **Remark:** hoàn tất marking và xử lý reference.
- **Cleanup:** tổng hợp kết quả, xác định các region có thể reclaim.
- **Mixed collections:** thu gom young regions cùng một tập old regions được chọn.

G1 ưu tiên các old regions có tỷ lệ object chết cao và hiệu quả reclaim tốt. Nó phân bổ công việc qua nhiều pause để kiểm soát pause-time target.

## 6. G1 Mixed collection khác Full GC thế nào?

**Mixed collection** thu gom young regions và một tập old regions trong cùng collection set. Sau mỗi Mixed collection, G1 có thể tiếp tục thu hồi các old regions khác ở những pause tiếp theo. Khi đã reclaim đủ các region có hiệu quả, G1 quay lại Young-Only phase.

**Full GC** là phương án fallback thu gom toàn heap và compact heap. Trong G1, log `Pause Full (G1 Compaction Pause)` là dấu hiệu cần điều tra, đặc biệt khi trước đó xuất hiện evacuation failure với reason `Allocation`.

Full GC có thể xuất hiện khi application cấp phát object nhanh hơn khả năng reclaim, concurrent marking không hoàn tất kịp để bắt đầu Space-Reclamation, hoặc có nhiều humongous objects. Explicit `System.gc()` cũng có thể là nguyên nhân.

Đừng coi Mixed collection là lỗi chỉ vì nó chạm tới Old Generation. Hãy quan sát pause time, số old regions được reclaim và xu hướng old occupancy sau cả chu kỳ.

## 7. Humongous objects và áp lực Old Generation

Trong G1, object có kích thước từ một nửa region trở lên được gọi là **humongous object**. Các object này được cấp phát trực tiếp vào old generation dưới dạng một chuỗi region liên tiếp.

Các mảng lớn, buffer lớn hoặc payload được giữ lâu có thể làm tăng số humongous regions. Vì chúng cần vùng liên tục, G1 có thể gặp khó khăn cấp phát dù tổng free space nhìn chung vẫn còn.

GC log có thể hiển thị:

~~~text
[0.201s][info][gc,heap] GC(0) Old regions: 2->19
[0.201s][info][gc,heap] GC(0) Humongous regions: 0->0
~~~

Đây là số lượng region trước và sau collection, không phải số byte. Hãy đối chiếu với heap region size, tổng heap và kích thước object được cấp phát.

Nếu humongous regions tăng cao, kiểm tra các allocation lớn, việc giữ buffer, cách đọc/ghi file và xử lý payload. Chỉ điều chỉnh `-XX:G1HeapRegionSize` sau khi có bằng chứng rằng kích thước region là yếu tố giới hạn.

## 8. Bật Unified GC Logging

Từ JDK 9 trở lên, dùng Unified Logging với `-Xlog`. Một cấu hình chi tiết phù hợp để bắt đầu điều tra:

~~~bash
java -Xlog:gc*,gc+phases=debug:file=gc.log:uptime,level,tags -jar app.jar
~~~

Ý nghĩa:

- `gc*`: ghi các log tag bắt đầu bằng `gc`, gồm collection, heap và các thông tin liên quan.
- `gc+phases=debug`: ghi chi tiết các pha GC.
- `file=gc.log`: ghi vào file thay vì console.
- `uptime,level,tags`: thêm thời gian từ lúc JVM khởi động, log level và tag vào mỗi dòng.

G1 cũng khuyến nghị bắt đầu chẩn đoán bằng:

~~~bash
java -Xlog:gc*=debug -jar app.jar
~~~

Có thể giảm output hoặc tập trung vào một vấn đề sau khi đã hiểu log tổng quan.

## 9. Log tag và thông điệp Old collection

Unified Logging gắn tag cho thông điệp. Oracle minh họa một dòng có tag `gc,old` như sau:

~~~text
[6.567s][info][gc,old] Old collection complete
~~~

Đây là một ví dụ về log message và tag set của JVM. Không phải mọi collector đều phát đúng dòng này hoặc dùng cùng cách gọi. Với G1, các thông tin thường hữu ích hơn là `Pause Young`, `Pause Full`, `Mixed`, `Old regions`, `Humongous regions` và các phase.

Có thể lọc log tag khi cần, ví dụ:

~~~bash
java -Xlog:gc+heap=info,gc+phases=debug -jar app.jar
~~~

Để hiểu loại collection và cause, giữ log `gc` tổng quát trong giai đoạn đầu. Nếu chỉ bật một tag quá hẹp, có thể bỏ mất thông tin cần để ghép các dòng cùng GC ID.

## 10. Đọc một dòng GC log

Ví dụ:

~~~text
[0.201s][info][gc] GC(0) Pause Full (System.gc()) 31M->14M(64M) 7.278ms
~~~

| Thành phần | Cách hiểu |
|---|---|
| `0.201s` | Thời gian JVM đã chạy khi ghi log. |
| `info` | Mức log. |
| `gc` | Tag của thông điệp. |
| `GC(0)` | GC ID, dùng để ghép các dòng thuộc cùng collection. |
| `Pause Full` | Loại collection và pause. |
| `System.gc()` | Cause được ghi nhận cho collection. |
| `31M->14M(64M)` | Heap used trước và sau GC, cùng dung lượng heap hiện tại. |
| `7.278ms` | Thời gian pause được ghi trên dòng đó. |

Các giá trị trên là ví dụ từ một lần chạy kiểm thử. Thời gian, heap size, cause và log text thay đổi theo collector, workload và JDK.

## 11. Đọc heap và Old regions trước/sau collection

Để đánh giá hiệu quả reclaim, đối chiếu các dòng cùng GC ID:

~~~text
[0.201s][info][gc,heap] GC(0) Old regions: 2->19
[0.201s][info][gc] GC(0) Pause Full (System.gc()) 31M->14M(64M) 7.278ms
~~~

Một số lưu ý:

- `Old regions: X->Y` là số region trước và sau, không phải old-generation bytes.
- `Heap: X->Y` hoặc dòng heap tổng thể cho biết used heap trước/sau.
- `Humongous regions: X->Y` giúp phát hiện áp lực do object lớn.
- Với một Full GC, old regions sau collection có thể vẫn tăng nếu nhiều object đang được giữ và được đưa vào old generation.
- Một collection có thể giải phóng nhiều heap nhưng không trả toàn bộ committed memory về hệ điều hành.

Để so sánh theo thời gian, lấy nhiều collection liên tiếp dưới workload tương tự. Một dòng log đơn lẻ không đủ để kết luận memory leak hoặc cấu hình heap sai.

## 12. Đánh giá pause time và reclaim hiệu quả

Các chỉ số nên xem cùng nhau:

1. **Old occupancy trước GC:** old space đã gần đầy hay chưa?
2. **Old occupancy sau GC:** baseline sau collection có giảm không?
3. **Reclaimed space:** chênh lệch used bytes hoặc số region có ý nghĩa thế nào?
4. **Pause duration:** một collection có làm request bị chậm không?
5. **Sum of pauses:** tổng thời gian application thực sự bị dừng trong khoảng ghi nhận.
6. **Frequency:** old/full collections có xuất hiện quá sát nhau không?
7. **Live-set trend:** sau nhiều collection, lượng object còn sống có tăng dần không?

Với collector concurrent, tổng thời gian collection có thể dài nhưng application chỉ bị dừng trong một số pha. Vì vậy, tổng pause time thường phản ánh tác động latency tốt hơn tổng thời gian GC chạy nền.

## 13. JFR event jdk.OldGarbageCollection

Java Flight Recorder có event:

~~~text
jdk.OldGarbageCollection
~~~

Event này cung cấp thông tin bổ sung cho old garbage collection. Trên JDK 24 đã kiểm tra, metadata của event gồm:

| Field | Ý nghĩa |
|---|---|
| `startTime` | Thời điểm bắt đầu event. |
| `duration` | Thời lượng event. |
| `gcId` | GC identifier để liên kết với event khác của cùng collection. |

`jdk.OldGarbageCollection` không chứa đầy đủ mọi thông tin về nguyên nhân. Hãy ghép nó với `jdk.GarbageCollection` bằng `gcId`, vì event đó có thể cung cấp tên collector, cause, tổng pause và pause dài nhất.

`jdk.GCPhasePause` cung cấp các pause phase cùng thời lượng và GC ID. Event type và field được ghi nhận phụ thuộc collector, JDK và event settings.

## 14. Ghi JFR khi JVM đang chạy

Tìm process:

~~~bash
jcmd -l
~~~

Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=old-gc settings=profile maxage=30m maxsize=512M jdk.OldGarbageCollection#enabled=true jdk.GarbageCollection#enabled=true jdk.GCPhasePause#enabled=true
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check name=old-gc verbose=true
~~~

Tạo snapshot mà không dừng recording:

~~~bash
jcmd <pid> JFR.dump name=old-gc filename=old-gc-snapshot.jfr
~~~

Khi đã thu đủ dữ liệu, dừng và lưu file cuối:

~~~bash
jcmd <pid> JFR.stop name=old-gc filename=old-gc-final.jfr
~~~

`JFR.dump` chỉ sao chép dữ liệu hiện có ra file; recording tiếp tục chạy. `JFR.stop` mới kết thúc recording.

`default.jfc` phù hợp với recording dài và liên tục vì overhead thấp hơn. `profile.jfc` thu thập thêm dữ liệu nhưng có thể tạo overhead cao hơn; chỉ dùng trong khoảng thời gian cần profiling sâu.

## 15. Phân tích JFR bằng jfr CLI

Xem tổng quan recording:

~~~bash
jfr summary old-gc-snapshot.jfr
~~~

In old collection events:

~~~bash
jfr print --events jdk.OldGarbageCollection old-gc-snapshot.jfr
~~~

In các event liên quan để đối chiếu GC ID:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause old-gc-snapshot.jfr
~~~

Ví dụ rút gọn từ một recording:

~~~text
jdk.OldGarbageCollection {
  duration = 7.18 ms
  gcId = 0
}

jdk.GarbageCollection {
  duration = 7.18 ms
  gcId = 0
  name = "G1Full"
  cause = "System.gc()"
  sumOfPauses = 7.18 ms
  longestPause = 7.18 ms
}
~~~

`gcId = 0` cho biết hai event thuộc cùng một GC. Đây là cách liên kết thời lượng old collection với cause và pause metrics. Event output thực tế có thể có thêm field và format khác theo JDK.

Nếu event không xuất hiện, kiểm tra event settings bằng `jcmd <pid> JFR.check name=old-gc verbose=true`, metadata bằng `jfr metadata --events jdk.OldGarbageCollection`, và xem collector đang dùng. Có thể dùng GC logs và `jdk.GarbageCollection` làm nguồn chẩn đoán bổ sung.

## 16. Phân tích bằng Java Mission Control

Java Mission Control (JMC) cung cấp giao diện phân tích recording:

1. Mở file JFR.
2. Xem **Automated Analysis Results** và phần Garbage Collections.
3. Mở **JVM Internals → Garbage Collections** để xem pause graph.
4. Kiểm tra số lần Full GC, Mixed GC và thời điểm xảy ra.
5. Đọc Sum of Pauses và pause dài nhất.
6. Đối chiếu heap usage và live-set trend.
7. Mở event detail để xem cause, GC ID, duration và stack/event context khi có.

JMC giúp nhìn xu hướng theo thời gian và drill down vào từng event. CLI phù hợp để lọc nhanh event hoặc tự động hóa phân tích.

## 17. Live set tăng sau Full GC có phải memory leak?

Một dấu hiệu đáng chú ý là Old Generation vẫn tăng sau nhiều Full GCs, trong khi lượng bộ nhớ được thu hồi rất ít.

Ví dụ log:

~~~text
GC(10) Pause Full 45M->44M(48M) 90.0ms
GC(11) Pause Full 46M->45M(48M) 92.0ms
GC(12) Pause Full 47M->46M(48M) 95.0ms
~~~

Nếu workload và tải đã ổn định, live set sau GC vẫn tăng theo thời gian, có thể có object đang bị giữ reference ngoài ý muốn. Tuy nhiên, đây chưa phải bằng chứng duy nhất của memory leak. Heap quá nhỏ so với live set hợp lệ hoặc workload tăng cũng có thể tạo hiện tượng tương tự.

Quy trình điều tra:

- So sánh live set sau GC ở nhiều thời điểm.
- Kiểm tra class/object types tăng nhanh.
- Xem allocation sites và reference retention.
- Dùng JMC Memory Leak Detection hoặc heap dump khi cần xác định object nào đang được giữ.
- Kiểm tra cache, collection, listener, ThreadLocal, session và static reference.

Heap dump giúp phân tích object graph và reference chain. JFR giúp quan sát allocation và xu hướng theo thời gian. Hai loại dữ liệu bổ sung cho nhau.

## 18. JFR Heap Statistics và explicit GC có thể làm sai phép đo

JFR có tính năng **Heap Statistics**. Oracle lưu ý tính năng này kích hoạt một old garbage collection ở đầu và cuối lần ghi. Những old GCs bổ sung tạo pause và có thể làm sai số đo latency.

Không bật Heap Statistics khi mục tiêu chỉ là profiling hiệu năng hoặc đo pause tự nhiên của ứng dụng. Chỉ bật khi cần điều tra live set hoặc memory leak và đã chấp nhận overhead.

Tương tự, `System.gc()` và lệnh `jcmd <pid> GC.run` yêu cầu JVM thực hiện explicit GC. Đây là thao tác có thể gây Full GC hoặc old collection tùy collector và cấu hình.

Không gọi `System.gc()` liên tục để xử lý memory leak. Nó không giải phóng object còn reachable. Khi chạy benchmark hoặc kiểm tra latency, ghi lại mọi explicit GC để tránh nhầm chúng với collection do áp lực allocation tự nhiên.

## 19. Dùng jcmd để kiểm tra heap và class histogram

Một số diagnostic command hữu ích:

~~~bash
jcmd <pid> GC.heap_info
~~~

Lệnh này cung cấp thông tin tổng quát về Java heap. Impact được JDK 24 mô tả ở mức Medium.

Có thể lấy class histogram:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Class histogram cho biết thống kê heap theo class, hữu ích khi muốn tìm loại object chiếm nhiều bộ nhớ. Tuy nhiên, JDK đánh giá impact của lệnh này là High và phụ thuộc kích thước/nội dung heap. Cân nhắc tải và pause trước khi chạy trên production.

Nếu cần phân tích object graph hoặc retained size, dùng heap dump và công cụ phân tích chuyên biệt. Không dùng histogram như bằng chứng duy nhất để kết luận memory leak.

## 20. Những dấu hiệu và hướng xử lý thường gặp

| Dấu hiệu | Khả năng cần kiểm tra | Hướng điều tra |
|---|---|---|
| Full GC xuất hiện liên tục | Old occupancy cao, marking không hoàn tất kịp, allocation pressure hoặc explicit GC. | Đọc GC cause, evacuation failure và live set. |
| Full GC thu hồi rất ít | Nhiều object còn reachable, heap nhỏ so với live set hoặc memory leak. | So sánh sau-GC baseline, JFR và heap dump. |
| Mixed collection pause dài | G1 phải evacuate nhiều old regions hoặc vùng có tỷ lệ object sống cao. | Bật `gc+ergo+cset=debug`, xem predicted old region time. |
| Old regions tăng nhanh | Promotion rate cao, allocation dài hạn hoặc humongous objects. | Kiểm tra allocation rate, `Humongous regions` và lifetime object. |
| JFR không có OldGarbageCollection | Event chưa bật hoặc collector không phát event này. | Kiểm tra JFR settings, metadata và GC logs. |
| Old GC xuất hiện khi bắt đầu recording | Có thể đã bật JFR Heap Statistics hoặc gọi explicit GC. | Kiểm tra recording configuration và lệnh từ công cụ bên ngoài. |
| GC log có `Pause Full (G1 Compaction Pause)` | G1 phải dùng Full GC fallback. | Tìm evacuation failure, allocation pressure và marking timing. |

## 21. Tuning G1 khi old collection gây pause dài

Trước khi thay JVM flags, xác định nguyên nhân từ log và workload. Oracle khuyến nghị bắt đầu với G1 defaults, chỉ điều chỉnh khi có bằng chứng.

Một số option có thể hữu ích trong trường hợp cụ thể:

- `-XX:G1MixedGCCountTarget`: tăng số Mixed collections mục tiêu để trải việc reclaim old regions qua nhiều pause hơn.
- `-XX:G1MixedGCLiveThresholdPercent`: điều chỉnh ngưỡng live occupancy để chọn old regions làm collection candidates.
- `-XX:G1HeapWastePercent`: điều chỉnh mức heap waste mà G1 chấp nhận khi kết thúc Space-Reclamation phase.
- `-XX:G1ReservePercent`: thay đổi buffer dự trữ nhằm giúp G1 có thêm khoảng trống cho evacuation.
- `-XX:InitiatingHeapOccupancyPercent`: đặt ngưỡng bắt đầu concurrent marking khi adaptive IHOP bị tắt.

Tăng số Mixed collections có thể giảm phần công việc old-generation trong một pause, nhưng kéo dài thời gian hoàn tất reclaim. Thay đổi ngưỡng candidate có thể làm giảm pause nhưng cũng giảm lượng space thu hồi.

Với Full GC do allocation pressure, hãy xem xét giảm allocation rate, giảm object lifetime không cần thiết, kiểm tra humongous allocation và bảo đảm concurrent marking bắt đầu đủ sớm. Chỉ tăng heap khi live set và yêu cầu ứng dụng cho thấy heap hiện tại không đủ.

## 22. Ví dụ Java 17+: tạo và phân tích Old collection bằng JFR

Ví dụ sau giữ một số byte arrays trong Old Generation, yêu cầu hai explicit Full GCs và ghi các JFR events liên quan. Đây là lab để quan sát, không phải mẫu gọi `System.gc()` trong ứng dụng production.

Tệp OldCollectionDemo.java:

~~~java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import jdk.jfr.Recording;

public class OldCollectionDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        Path output = Path.of(
                args.length == 0 ? "old-collection.jfr" : args[0]);

        try (Recording recording = new Recording()) {
            recording.setName("old-collection-demo");
            recording.setToDisk(true);
            recording.enable("jdk.GarbageCollection");
            recording.enable("jdk.OldGarbageCollection");
            recording.enable("jdk.GCPhasePause");
            recording.start();

            for (int i = 0; i < 48; i++) {
                RETAINED.add(new byte[256 * 1024]);
            }
            System.out.println("RETAINED_OBJECTS=" + RETAINED.size());

            System.gc();
            System.out.println("AFTER_FIRST_FULL_GC");

            RETAINED.clear();
            System.gc();
            System.out.println("AFTER_SECOND_FULL_GC");

            recording.stop();
            recording.dump(output);
        }

        System.out.println("JFR_FILE_CREATED=" + output.getFileName());
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/OldCollectionDemo.java
~~~

Chạy với G1, heap cố định 64 MB và GC log chi tiết:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC "-Xlog:gc*,gc+phases=debug:file=gc.log:uptime,level,tags" -cp out OldCollectionDemo old-collection.jfr
~~~

Stdout chính xác:

~~~text
RETAINED_OBJECTS=48
AFTER_FIRST_FULL_GC
AFTER_SECOND_FULL_GC
JFR_FILE_CREATED=old-collection.jfr
~~~

Đọc GC log bằng text editor hoặc công cụ tìm kiếm, chú ý các dòng `Pause Full`, `Old regions`, `Humongous regions` và GC cause.

Đọc JFR:

~~~bash
jfr summary old-collection.jfr
jfr print --events jdk.OldGarbageCollection old-collection.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause old-collection.jfr
~~~

Trong lần kiểm thử trên Azul OpenJDK 24.0.2 với G1, chương trình biên dịch bằng `javac --release 17`, chạy thành công, tạo hai `jdk.OldGarbageCollection` events và hai `jdk.GarbageCollection`/`jdk.GCPhasePause` records. Các event liên kết bằng `gcId`; GC log ghi `Pause Full (System.gc())` và số `Old regions` trước/sau collection.

Thời lượng, GC ID và số event có thể khác giữa các lần chạy, collector và cấu hình. Nếu JVM khởi chạy với `-XX:+DisableExplicitGC`, lời gọi `System.gc()` trong ví dụ có thể bị bỏ qua.

## 23. Quy trình chẩn đoán Old collection

Khi một ứng dụng có old GC thường xuyên hoặc pause dài:

1. Xác định collector, JDK version, heap size và JVM flags.
2. Bật `-Xlog:gc*,gc+phases=debug` để thu loại collection, cause, occupancy và phase duration.
3. Với G1 Mixed collections, bổ sung `-Xlog:gc+ergo+cset=debug`.
4. Ghi JFR bằng `default` cho quan sát dài hoặc `profile` cho profiling ngắn.
5. Đối chiếu `jdk.OldGarbageCollection`, `jdk.GarbageCollection` và `jdk.GCPhasePause` qua `gcId`.
6. So sánh old occupancy trước/sau GC và live set qua nhiều chu kỳ.
7. Kiểm tra promotion, allocation rate, humongous regions và explicit GC.
8. Nếu live set tăng dưới tải ổn định, tìm object retention bằng JMC hoặc heap dump.
9. Thay đổi một tham số tại một thời điểm, sau đó đo lại pause, throughput và reclaim.
10. Lưu GC logs, JFR recording, JVM flags và workload context để có thể so sánh các lần điều tra.

Old collection là một phần bình thường của quản lý heap generational. Chẩn đoán chính xác cần kết hợp loại collection, GC cause, old occupancy, lượng reclaim, pause time và live-set trend. Khi đọc các dữ liệu này theo cùng GC ID và cùng khoảng workload, bạn có thể phân biệt collection bình thường, allocation pressure, heap sizing issue và memory leak candidate.

## Tài liệu tham khảo

- Oracle JDK 24 — [Garbage-First (G1) Garbage Collector](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html).
- Oracle JDK 24 — [Garbage-First Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html).
- Oracle JDK 24 — [Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-memory-leaks.html).
- Oracle JDK 24 — [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html).
- Oracle JDK 24 — [The java Command and Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html).
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html).
- Oracle JDK 24 — [JFR API Package](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
