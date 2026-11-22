# So sánh G1 với Generational ZGC trên workload đại diện

G1 và Generational ZGC đều là garbage collector có khả năng thu gom theo thế hệ trong HotSpot, nhưng hướng tối ưu khác nhau. G1 thường phù hợp với ứng dụng cần cân bằng throughput, độ trễ và mức sử dụng bộ nhớ. Generational ZGC hướng tới độ trễ pause rất thấp, đặc biệt hữu ích với workload có heap lớn, tốc độ cấp phát cao và yêu cầu p99 latency nghiêm ngặt.

Không có collector tốt nhất cho mọi ứng dụng. Lựa chọn nên dựa trên đặc điểm workload và số liệu đo trong môi trường gần production: throughput, p95/p99 latency, thời gian pause, CPU dành cho GC, allocation stall và mức sử dụng bộ nhớ. Việc chỉ nhìn vào một lần GC hoặc một con số pause nhỏ không đủ để kết luận.

## 1. Vai trò của G1 và Generational ZGC

**G1 (Garbage-First)** chia heap thành các region có kích thước tương đối đồng nhất. Collector thu gom các vùng young thường xuyên và có thể thu gom thêm các region old trong mixed collection. G1 thực hiện nhiều công việc đồng thời với ứng dụng, nhưng các pha evacuation vẫn có stop-the-world pause. Nó hướng tới sự cân bằng giữa throughput và mục tiêu thời gian pause.

**Generational ZGC** là chế độ generational của ZGC, được đưa vào Java 21. Nó chia object thành young và old generation, tận dụng thực tế rằng nhiều object thường chết sớm. ZGC thực hiện phần lớn công việc thu gom đồng thời với ứng dụng và được thiết kế để giữ pause rất ngắn, kể cả khi heap lớn. Đổi lại, collector cần CPU và tài nguyên để chạy công việc concurrent; ứng dụng cũng cần đủ headroom trong heap để cấp phát trong khi GC đang xử lý.

Hai collector đều có cơ chế thu gom theo thế hệ. Điểm khác biệt chính là chiến lược quản lý heap, mức độ công việc concurrent, đặc tính pause và chi phí CPU/memory của từng workload.

## 2. So sánh tổng quan

| Tiêu chí | G1 | Generational ZGC |
|---|---|---|
| Mục tiêu chính | Cân bằng throughput và pause time | Giữ pause time rất thấp |
| Tổ chức heap | Heap chia thành các region; thu gom young và mixed | Heap được quản lý theo young và old generation với cơ chế của ZGC |
| Công việc GC | Kết hợp stop-the-world và concurrent phases | Phần lớn công việc GC diễn ra concurrent |
| Pause | Có thể dài hơn khi heap/collection pressure tăng; có thể điều chỉnh mục tiêu pause | Thường rất ngắn và ít phụ thuộc vào dung lượng heap hơn |
| CPU dành cho GC | Thay đổi theo allocation rate, live set và pause goal | Có thể cần thêm CPU cho concurrent work và barriers |
| Throughput | Thường là lựa chọn cân bằng, có thể đạt throughput tốt | Có thể thấp hơn trong một số workload do chi phí concurrent, nhưng phải đo thực tế |
| Heap lớn | Có thể hoạt động tốt, nhưng pause có thể tăng theo áp lực thu gom | Là lựa chọn đáng cân nhắc khi cần heap lớn và pause thấp |
| Tính phù hợp | Web service, ứng dụng tổng hợp, batch có mức dung sai pause vừa phải | Service nhạy latency, heap lớn, allocation cao và nhiều request đồng thời |

Bảng này mô tả xu hướng thiết kế, không phải cam kết hiệu năng. Kết quả thực tế phụ thuộc JDK build, phần cứng, số core, dung lượng heap, live set, allocation rate, object lifetime và cấu hình ứng dụng.

## 3. Cách G1 xử lý workload

G1 chia heap thành các region và phân loại region theo trạng thái sử dụng. Trong chu kỳ hoạt động điển hình:

1. G1 thực hiện young collection để thu gom các region chứa object mới.
2. Collector đánh dấu các object còn sống trong old generation qua các pha concurrent marking.
3. Sau khi đánh dấu, G1 có thể chọn các old region có nhiều dung lượng có thể thu hồi để đưa vào mixed collection.
4. Các region được chọn sẽ được evacuation trong các pha stop-the-world.

G1 cố gắng chọn tập region sao cho lượng bộ nhớ thu hồi có lợi so với chi phí pause. Tham số `-XX:MaxGCPauseMillis` đặt mục tiêu pause cho G1; đây là mục tiêu để collector điều chỉnh hành vi, không phải giới hạn thời gian cứng được bảo đảm.

G1 thường là điểm bắt đầu hợp lý khi:

- Ứng dụng cần throughput tốt và pause ở mức chấp nhận được.
- Heap ở quy mô vừa hoặc lớn nhưng không có yêu cầu latency cực thấp.
- Workload có sự pha trộn giữa request ngắn, xử lý nền và object sống lâu.
- Hệ thống muốn dùng collector mặc định của HotSpot server configuration trước khi có bằng chứng cần đổi.

Ví dụ, một dịch vụ nội bộ xử lý báo cáo, truy vấn và cập nhật dữ liệu với SLA tính bằng hàng trăm millisecond có thể phù hợp với G1 nếu pause GC không chiếm phần đáng kể trong latency.

## 4. Cách Generational ZGC xử lý workload

Generational ZGC phân chia object thành young và old generation. Object mới được cấp phát trong young generation; object sống qua nhiều chu kỳ có thể được giữ lại và trở thành object thuộc old generation. Nhờ phân biệt tuổi thọ object, collector có thể thu gom object ngắn hạn thường xuyên mà không phải xử lý toàn bộ heap theo cùng một cách.

ZGC sử dụng các cơ chế như colored pointers và load barriers để theo dõi, cập nhật tham chiếu trong khi phần lớn công việc thu gom diễn ra đồng thời với ứng dụng. Một số pha ngắn vẫn cần dừng application thread, nên không nên diễn giải “concurrent” thành “không có pause”.

Generational ZGC đáng cân nhắc khi:

- Ứng dụng có heap lớn và live set đáng kể.
- Tốc độ tạo object cao, đặc biệt có nhiều object ngắn hạn.
- Pause GC gây ảnh hưởng rõ tới p99/p999 latency.
- Hệ thống có đủ CPU và memory headroom để GC làm việc đồng thời.
- Độ trễ ổn định quan trọng hơn việc tối đa hóa throughput trên từng core.

Ví dụ, một API gateway hoặc hệ thống giao dịch cần duy trì latency thấp khi có nhiều request đồng thời có thể thử Generational ZGC, nhất là khi profiling cho thấy các pause của G1 là một phần đáng kể của tail latency.

## 5. Workload A: API service nhạy với p99 latency

Giả sử một API service nhận nhiều request đồng thời, mỗi request tạo nhiều object tạm như DTO, JSON buffer và kết quả chuyển đổi. SLA yêu cầu p99 ổn định; một pause GC dài có thể làm nhiều request cùng bị trễ.

Với workload này, nên thử cả hai collector dưới cùng tải:

- G1 có thể cung cấp throughput tốt, nhưng các pause evacuation có thể xuất hiện trong tail latency.
- Generational ZGC có thể giảm tác động của pause GC lên p99 nhờ phần lớn công việc diễn ra concurrent.
- Nếu CPU đã gần bão hòa, chi phí concurrent GC của ZGC có thể làm giảm năng lực xử lý request.
- Nếu live set chiếm gần hết heap, ZGC cũng có thể thiếu headroom để cấp phát trong khi thu gom.

Không nên kết luận rằng Generational ZGC luôn làm p99 thấp hơn. Cần kiểm tra p99 cùng throughput: một collector có p99 thấp hơn nhưng làm throughput giảm mạnh có thể không phù hợp với mục tiêu vận hành.

## 6. Workload B: batch ưu tiên throughput

Một batch job xử lý hàng triệu bản ghi, có thể chấp nhận pause dài hơn miễn là tổng thời gian hoàn thành tốt. Công việc thường chạy theo đợt, CPU được sử dụng liên tục và latency của từng thao tác không phải chỉ tiêu chính.

G1 có thể là lựa chọn tốt nếu:

- Throughput tổng thể cao.
- Pause không làm vượt deadline batch.
- CPU overhead của GC ở mức hợp lý.
- Heap và allocation rate không tạo ra những chu kỳ mixed collection quá tốn kém.

Generational ZGC vẫn có thể chạy workload này, nhưng công việc concurrent và load barriers có thể tiêu tốn CPU mà không đem lại lợi ích rõ ràng nếu pause không phải vấn đề. Trên máy có ít core, phần CPU dành cho GC có thể cạnh tranh trực tiếp với batch computation.

Với batch, nên so sánh tổng thời gian hoàn thành, records/second, CPU time và GC CPU. Không nên chỉ so sánh pause dài nhất.

## 7. Workload C: heap lớn và object sống lâu

Một hệ thống phân tích hoặc cache có thể giữ nhiều object sống lâu trong heap, đồng thời liên tục tạo object tạm trong quá trình truy vấn. Khi heap lớn, thời gian xử lý các pha GC và ảnh hưởng của pause trở thành yếu tố cần đo.

Generational ZGC có thể phù hợp nếu yêu cầu pause thấp và hệ thống có đủ tài nguyên cho concurrent collection. G1 vẫn là lựa chọn hợp lệ nếu throughput tốt và pause thực tế nằm trong SLA.

Cần phân biệt heap capacity với live set:

- **Heap capacity** là dung lượng heap JVM có thể sử dụng.
- **Live set** là phần object còn được tham chiếu và cần giữ lại.
- **Allocation rate** là tốc độ ứng dụng tạo object mới.
- **Headroom** là phần dung lượng còn lại để ứng dụng tiếp tục cấp phát trong khi GC đang thu gom.

Một collector không thể giải quyết việc live set gần bằng heap capacity. Nếu dữ liệu sống chiếm gần toàn bộ heap, cần xem lại heap sizing, cache retention, object graph và giới hạn bộ nhớ trước khi đổi collector.

## 8. Workload D: ứng dụng nhỏ hoặc giới hạn CPU

Trong container nhỏ, ứng dụng có ít CPU quota và heap không lớn. Generational ZGC có thể không mang lại lợi ích đủ lớn để bù cho chi phí concurrent work.

G1 thường là điểm bắt đầu phù hợp khi:

- Pause hiện tại đã nằm trong SLA.
- CPU quota thấp và ứng dụng cần dành phần lớn CPU cho business logic.
- Heap nhỏ hoặc vừa.
- Không có dấu hiệu rõ ràng rằng GC pause là nguyên nhân gây tail latency.

Tuy nhiên, đây không phải quy tắc tuyệt đối. Nếu workload nhỏ nhưng có yêu cầu latency rất nghiêm ngặt, vẫn có thể benchmark Generational ZGC. Quyết định cần dựa trên CPU throttling, throughput và latency thực tế trong container.

## 9. Cấu hình chạy thử trên Java 21

Để so sánh công bằng, chạy cùng ứng dụng và cùng bộ dữ liệu với mỗi collector trong một lần chạy riêng.

G1:

```bash
java -XX:+UseG1GC \
  -Xms4g -Xmx4g \
  -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags \
  -jar application.jar
```

Generational ZGC trên Java 21:

```bash
java -XX:+UseZGC -XX:+ZGenerational \
  -Xms4g -Xmx4g \
  -Xlog:gc*,safepoint:file=zg-gc.log:time,uptime,level,tags \
  -jar application.jar
```

Trong Java 21, Generational ZGC được bật tường minh bằng `-XX:+ZGenerational` cùng `-XX:+UseZGC`. Từ JDK 23, generational trở thành chế độ mặc định của ZGC và chế độ non-generational bị deprecated; từ JDK 24, chế độ non-generational đã bị loại bỏ. Khi triển khai trên JDK mới hơn, hãy kiểm tra tài liệu của đúng phiên bản runtime thay vì sao chép nguyên cấu hình Java 21.

Các tham số `-Xms` và `-Xmx` trong ví dụ chỉ để minh họa cùng một heap size khi benchmark. Chúng cần được điều chỉnh theo memory limit của container, live set và headroom thực tế. Không nên ép cả hai collector dùng một heap size không đủ để chạy ổn định chỉ nhằm tạo ra một phép so sánh có vẻ ngang bằng.

## 10. Thiết kế benchmark công bằng

Một benchmark có ý nghĩa cần kiểm soát các biến số ngoài collector:

1. Dùng cùng JDK vendor và build, cùng cấu hình CPU/memory và cùng container limit.
2. Dùng cùng phiên bản ứng dụng, dữ liệu đầu vào, số client và phân bố request.
3. Giữ cùng heap size ban đầu và tối đa trong lần so sánh đầu tiên.
4. Chạy warm-up đủ lâu để JIT và ứng dụng đạt trạng thái ổn định.
5. Đo nhiều lần, đổi thứ tự collector giữa các lần chạy để giảm sai lệch do môi trường.
6. Tách thời gian startup khỏi giai đoạn steady-state nếu SLA không tính startup.
7. Thu thập cả GC log, JFR, CPU, memory và latency của ứng dụng.
8. Chạy đủ lâu để bao phủ các chu kỳ old-generation collection và workload theo thời gian.

Không nên so sánh một lần chạy G1 sau warm-up với một lần chạy ZGC ngay sau khi JVM khởi động. JIT compilation, cache lạnh, dữ liệu đầu vào và trạng thái hệ điều hành có thể tạo ra sai lệch lớn hơn khác biệt giữa collector.

## 11. Chỉ số cần theo dõi

| Chỉ số | Vì sao cần đo |
|---|---|
| Throughput (requests/s hoặc records/s) | Đo lượng công việc hoàn thành |
| p50, p95, p99, p999 latency | Nhìn thấy ảnh hưởng lên tail latency |
| GC pause count và pause duration | Xác định tần suất và độ dài pause |
| Tổng thời gian application bị dừng | Đánh giá tác động stop-the-world |
| CPU utilization và GC CPU | Phát hiện chi phí concurrent collection |
| Allocation rate | Hiểu tốc độ tạo object |
| Live set và heap occupancy | Biết dung lượng object còn sống |
| Allocation stall | Phát hiện ứng dụng phải chờ GC giải phóng dung lượng |
| Process RSS và container memory | Đảm bảo không vượt giới hạn bộ nhớ ngoài heap |
| Full GC hoặc chu kỳ thu gom bất thường | Tìm dấu hiệu áp lực bộ nhớ hoặc cấu hình chưa phù hợp |

Một số event JFR và nguồn dữ liệu hữu ích gồm các event GC phase, garbage collection, heap summary và allocation stall nếu được runtime ghi nhận. GC log với `-Xlog:gc*` cũng giúp xem chu kỳ thu gom và pause. Nên phân tích dữ liệu theo cùng khoảng thời gian với latency của ứng dụng để xác định pause có thực sự trùng với các request chậm hay không.

## 12. Cách diễn giải kết quả

Một số tình huống thường gặp:

| Kết quả benchmark | Cách diễn giải |
|---|---|
| G1 throughput cao hơn, p99 cả hai đều đạt SLA | G1 thường là lựa chọn đơn giản và hiệu quả hơn |
| ZGC giảm rõ p99, throughput vẫn đạt mục tiêu | Generational ZGC có lợi thế cho workload nhạy latency |
| ZGC giảm pause nhưng CPU tăng và throughput giảm mạnh | Kiểm tra CPU headroom; lợi ích latency có thể không bù được chi phí |
| Cả hai đều có allocation stall hoặc memory pressure | Xem lại heap, live set, allocation rate và memory limit |
| G1 có pause dài nhưng ít xảy ra và không ảnh hưởng SLA | Có thể chưa cần đổi collector |
| ZGC có pause ngắn nhưng request vẫn chậm | Điều tra lock contention, I/O, scheduler, network và application latency |
| Kết quả thay đổi nhiều giữa các lần chạy | Benchmark chưa ổn định hoặc workload/environment không được kiểm soát |

GC chỉ là một thành phần trong latency. Nếu p99 cao do database, network, lock contention hoặc CPU throttling, đổi collector có thể không cải thiện vấn đề.

## 13. Lựa chọn theo workload đại diện

| Workload | Điểm xuất phát | Khi nên thử collector còn lại |
|---|---|---|
| API service, SLA latency vừa phải, throughput quan trọng | G1 | Khi GC pause chiếm đáng kể p99 |
| API service, p99/p999 rất nghiêm ngặt, heap lớn | Generational ZGC | Benchmark G1 nếu CPU hoặc throughput là giới hạn |
| Batch xử lý dữ liệu, ưu tiên records/second | G1 | Khi pause gây vượt deadline hoặc gián đoạn pipeline |
| Cache lớn, nhiều object sống lâu và allocation cao | Benchmark cả hai | Chọn theo live set, pause và headroom đo được |
| Container ít CPU, heap nhỏ, latency đã đạt yêu cầu | G1 | Chỉ thử ZGC nếu có vấn đề latency GC cụ thể |
| Dịch vụ nhiều request blocking và object tạm | Benchmark cả hai | ZGC đáng thử nếu pause là nguyên nhân của tail latency |

Các hàng trong bảng là điểm bắt đầu để thiết kế thử nghiệm, không phải luật cố định. Mỗi hệ thống có thể có object lifetime, allocation rate và mức độ nhạy latency khác nhau.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Generational ZGC không có stop-the-world pause | ZGC vẫn có các pha pause ngắn |
| ZGC luôn nhanh hơn G1 | ZGC tối ưu pause; throughput phụ thuộc workload và tài nguyên |
| G1 không phải generational collector | G1 có young và old generation |
| Heap càng lớn thì ZGC luôn càng tốt | Live set lớn và thiếu headroom vẫn gây áp lực bộ nhớ |
| Chỉ cần so sánh pause time | Cần xem cả p99, throughput, CPU và allocation stall |
| G1 pause goal là giới hạn cứng | `MaxGCPauseMillis` là mục tiêu điều chỉnh, không phải bảo đảm |
| Đổi sang ZGC sẽ sửa mọi latency spike | I/O, lock contention, scheduler và CPU throttling vẫn có thể gây chậm |
| Cấu hình ZGC Java 21 áp dụng nguyên vẹn cho mọi JDK mới | Mặc định và chế độ ZGC đã thay đổi ở các JDK sau |

## 15. Quy trình chọn collector cho ứng dụng Java 21

Có thể áp dụng quy trình sau:

1. Bắt đầu bằng G1 nếu ứng dụng chưa có số liệu chứng minh GC pause là vấn đề.
2. Thu thập latency distribution, throughput, GC log, JFR, CPU và memory trong workload đại diện.
3. Nếu pause GC làm p99/p999 vượt SLA, thử Generational ZGC.
4. Trên Java 21, bật bằng `-XX:+UseZGC -XX:+ZGenerational`.
5. Giữ các điều kiện benchmark giống nhau và chạy đủ lâu để quan sát cả young lẫn old collection.
6. So sánh mức cải thiện latency với thay đổi throughput, CPU, RSS và allocation stall.
7. Chọn collector đáp ứng SLA với chi phí vận hành phù hợp; ghi lại JDK build và cấu hình đi kèm.
8. Khi nâng JDK, kiểm tra lại mặc định và tùy chọn GC vì hành vi, trạng thái hỗ trợ có thể thay đổi giữa các phiên bản.

Với Java 21, G1 là lựa chọn cân bằng và là điểm xuất phát tốt cho nhiều ứng dụng. Generational ZGC phù hợp để thử khi pause GC ảnh hưởng rõ đến tail latency, đặc biệt với heap lớn và allocation rate cao. Kết quả benchmark dưới tải thực tế mới là cơ sở quyết định; không nên chọn chỉ dựa trên tên collector hoặc một con số pause riêng lẻ.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Available Garbage Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html)
- [Oracle Java SE 21 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector.html)
- [Oracle Java SE 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector.html)
- [JEP 439 — Generational ZGC (JDK 21)](https://openjdk.org/jeps/439)
- [JEP 474 — ZGC: Generational Mode by Default (JDK 23)](https://openjdk.org/jeps/474)
- [JEP 490 — ZGC: Remove the Non-Generational Mode (JDK 24)](https://openjdk.org/jeps/490)
