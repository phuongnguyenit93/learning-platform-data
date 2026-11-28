# So sánh trước, sau trên cùng tải thay vì giả định mức tăng cố định

JDK 26 cải thiện throughput của G1 GC bằng cách giảm đồng bộ giữa luồng ứng dụng và các luồng xử lý card table nền. Thay đổi này được triển khai trong **JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization**. Nó đặc biệt có lợi cho workload thường xuyên ghi các tham chiếu giữa object; các phép thử được công bố ghi nhận mức tăng khoảng 5–15% ở workload cập nhật reference nhiều. Con số này là kết quả của những workload thử nghiệm cụ thể, không phải cam kết rằng mọi ứng dụng sẽ nhanh hơn cùng một tỷ lệ.

Cách đánh giá đúng là chạy cùng ứng dụng, cùng dữ liệu, cùng tải và cùng cấu hình G1 trên JDK trước và sau thay đổi, rồi so sánh throughput, latency, chi phí GC và bộ nhớ. Nếu thay đồng thời JDK, collector, heap, giới hạn CPU hoặc dữ liệu đầu vào, bạn sẽ không biết cải thiện đến từ JEP 522 hay từ yếu tố khác.

## 1. JEP 522 thay đổi điều gì?

G1 chia heap thành các region. Một object ở region này có thể giữ tham chiếu đến object ở region khác. Khi ứng dụng ghi một reference field, G1 cần ghi nhận vùng heap có thay đổi để có thể tìm các tham chiếu liên vùng trong quá trình thu gom rác. G1 dùng **card table** và các write barrier do JVM chèn vào mã đã biên dịch để theo dõi những thay đổi đó.

Ở các workload cập nhật reference thường xuyên, việc application threads và các luồng tối ưu hóa card table cùng thao tác trên cấu trúc dùng chung tạo ra chi phí đồng bộ. Write barrier và quá trình refinement phải phối hợp nhiều hơn; chi phí này có thể làm giảm throughput của ứng dụng và ảnh hưởng đến latency.

JEP 522 đưa vào card table thứ hai để tách hoạt động của application threads khỏi hoạt động tối ưu hóa nền:

1. Application threads ghi vào **active card table** mà không cần đồng bộ với các luồng tối ưu hóa.
2. Các luồng G1 xử lý/refine card table còn lại độc lập ở phía nền.
3. Khi G1 dự đoán việc quét active table có thể vượt mục tiêu pause time, JVM hoán đổi hai bảng một cách nguyên tử.
4. Bảng vừa trở thành inactive được xử lý trong khi application threads tiếp tục ghi vào bảng active mới.

Mô hình khái quát của hai card table:

    Application threads
             |
             v
       Active card table
             |
       atomic table swap
             |
             v
       Inactive card table ------> G1 background refinement
             |
       được xử lý và tái sử dụng

Cách tổ chức này giảm cạnh tranh giữa luồng ứng dụng và luồng GC khi theo dõi các reference update. JDK 26 không thay đổi API Java và không yêu cầu sửa mã ứng dụng để bật JEP 522. Khi G1 được chọn, cải tiến đã được tích hợp trong runtime; không có cờ riêng cần bật cho JEP 522.

## 2. Mức cải thiện được công bố có ý nghĩa gì?

Các phép thử được công bố cùng JEP 522 cho thấy:

- Workload cập nhật object reference nhiều có thể tăng throughput khoảng **5–15%**.
- Ngay cả workload có lượng reference update nhẹ cũng có trường hợp tăng đến khoảng **5%**.
- Pause time có thể giảm nhẹ.
- Write barrier trên x64 được mô tả giảm từ khoảng 50 xuống khoảng 12 instruction trong các trường hợp được phân tích.
- Card table bổ sung có chi phí native memory xấp xỉ 2 MB cho mỗi 1 GB heap, tương đương khoảng 0,2% dung lượng heap theo ước tính được công bố.

Đây là số liệu từ các phép thử của nhóm phát triển JDK, không phải ngưỡng hiệu năng được bảo đảm cho ứng dụng của bạn. Kết quả phụ thuộc kiến trúc CPU, JDK distribution, số luồng, heap, tỷ lệ reference update, live set và hành vi cấp phát của workload.

Ví dụ, dịch vụ chủ yếu chờ database hoặc xử lý chuỗi mà ít thay đổi object graph có thể không nhận được mức tăng giống một dịch vụ liên tục cập nhật graph lớn. Một ứng dụng bị giới hạn bởi CPU của business logic, lock riêng của ứng dụng hoặc I/O cũng có thể không thấy khác biệt rõ.

Không dùng con số 5–15% làm mục tiêu nghiệm thu. Hãy đo baseline của chính ứng dụng và xác định độ chênh lệch có lớn hơn độ dao động giữa các lần chạy hay không.

## 3. Chọn đúng cặp phiên bản để so sánh

Để đo riêng ảnh hưởng của JEP 522, cặp so sánh cơ bản là:

| Thành phần | Trước thay đổi | Sau thay đổi |
|---|---|---|
| Runtime | JDK 25 | JDK 26 |
| Garbage collector | G1 được chọn tường minh | G1 được chọn tường minh |
| JEP 522 | Chưa có | Đã tích hợp |
| Mã ứng dụng | Cùng một artifact | Cùng một artifact |
| Dữ liệu và tải | Cùng tập dữ liệu, cùng kịch bản | Cùng tập dữ liệu, cùng kịch bản |

Nên biên dịch benchmark và ứng dụng thành một artifact có bytecode tương thích với cả hai runtime, nếu ứng dụng không cần API mới của JDK 26. Ví dụ, có thể biên dịch bằng JDK 25 hoặc dùng tùy chọn **--release 25** rồi chạy cùng artifact đó trên cả JDK 25 và JDK 26. Như vậy, phép so sánh tập trung vào khác biệt runtime thay vì đồng thời thay đổi mã bytecode.

### Vì sao phải chọn G1 tường minh?

Trong JDK 26, HotSpot thường chọn G1 theo ergonomics, nhưng trên môi trường rất hạn chế tài nguyên (ví dụ một CPU hoặc dưới 1792 MB RAM vật lý), JVM có thể chọn Serial GC. Nếu JDK 25 chạy G1 còn JDK 26 chạy Serial, hoặc ngược lại, kết quả không còn cô lập được JEP 522.

Dùng **-XX:+UseG1GC** ở cả hai phiên bản để bảo đảm phép so sánh đang đo G1. Kiểm tra collector thực tế bằng log khởi tạo GC hoặc cờ JVM, không suy luận chỉ từ việc đã bỏ qua tùy chọn collector.

JDK 27 có thay đổi riêng theo **JEP 523 — Make G1 the Default Garbage Collector in All Environments**: G1 trở thành collector mặc định trong mọi môi trường HotSpot, trừ khi ứng dụng chọn collector khác hoặc bản phân phối không có G1. Thay đổi mặc định này không phải là JEP 522. Khi benchmark JDK 27, vẫn nên chọn G1 tường minh nếu mục tiêu là so sánh cùng collector qua các release.

## 4. Giữ cố định các điều kiện của phép đo

Một benchmark trước/sau có ý nghĩa cần cố định ít nhất các yếu tố sau:

| Yếu tố | Cần giữ giống nhau |
|---|---|
| Phần cứng | Cùng máy, CPU, kiến trúc, RAM và thiết bị lưu trữ |
| Hệ điều hành | Cùng phiên bản, kernel, container runtime và thiết lập hệ thống |
| CPU | Cùng CPU quota, CPU affinity, số core khả dụng và chế độ cấp CPU |
| Bộ nhớ | Cùng giới hạn container, -Xms, -Xmx và các giới hạn native memory liên quan |
| Collector | Cùng G1; không so sánh G1 với Serial hoặc Parallel |
| JVM flags | Cùng các cờ GC, pause-time goal, heap và JIT; chỉ khác phần mặc định do release thay đổi nếu đó là đối tượng đang nghiên cứu |
| Ứng dụng | Cùng artifact, dependency, cấu hình và logging |
| Dữ liệu | Cùng dataset, seed ngẫu nhiên, kích thước input và live set |
| Tải | Cùng số worker, concurrency, tốc độ request và phân bố request |
| Warmup | Cùng thời gian khởi động, giai đoạn warmup và điều kiện cache |

Đặt heap cố định giúp tránh trường hợp một bản chạy với heap lớn hơn và ít GC hơn. Ví dụ:

    -Xms4g -Xmx4g -XX:+UseG1GC

Không cần đặt một giá trị heap giống ví dụ trên cho mọi ứng dụng; chọn dung lượng phù hợp với production rồi dùng đúng giá trị đó cho cả hai runtime. Nếu production dùng container memory limit, benchmark cũng cần chạy với cùng giới hạn và kiểm tra JVM nhận diện đúng giới hạn tài nguyên.

Không thêm các cờ G1 tuning mới chỉ ở một bên. Nếu cần dùng **-XX:MaxGCPauseMillis**, **-XX:G1HeapRegionSize** hoặc các cờ khác, giữ cùng giá trị và ghi rõ trong báo cáo. Tránh tinh chỉnh quá nhiều biến cùng lúc vì sẽ khó xác định nguyên nhân của thay đổi hiệu năng.

## 5. Thiết kế workload có thể làm lộ lợi ích

JEP 522 nhắm đến chi phí theo dõi thay đổi reference. Vì thế, workload cần đại diện được số lượng và nhịp độ ghi reference của ứng dụng.

Các workload hữu ích để kiểm tra gồm:

- Cập nhật liên tục các liên kết trong object graph còn sống.
- Cập nhật collection hoặc cấu trúc cây/đồ thị có nhiều object được giữ lại lâu.
- Duy trì các reference giữa các object được phân bố trên nhiều G1 region.
- Chạy nhiều application threads cùng cập nhật reference trong khi G1 thực hiện refinement.
- Có tỷ lệ cấp phát và live set gần với ứng dụng thực tế, để GC hoạt động tương tự production.

Không chỉ tạo một vòng lặp ghi đi ghi lại cùng một field rồi kết luận đó là benchmark G1 đầy đủ. Một card có thể đã được đánh dấu dirty, và một vòng lặp nhỏ không nhất thiết kích hoạt đủ quá trình refinement hoặc GC để thể hiện chi phí thực tế. Cần có graph đủ lớn, nhiều vị trí ghi và thời gian chạy đủ dài.

Một thiết kế benchmark có thể bắt đầu với các node có reference field:

    final class Node {
        final int id;
        Node next;

        Node(int id) {
            this.id = id;
        }
    }

    // Khởi tạo một graph lớn, giữ các node sống trong suốt phép đo.
    Node[] nodes = createGraph(nodeCount);

    // Trong giai đoạn đo, cập nhật các reference field ở nhiều node.
    for (int i = 0; i < updatesPerBatch; i++) {
        int sourceIndex = nextSourceIndex();
        int targetIndex = nextTargetIndex();

        nodes[sourceIndex].next = nodes[targetIndex];
    }

Đây là mô hình minh họa workload reference update, không phải benchmark hoàn chỉnh. Khi triển khai bằng JMH, hãy tạo graph ở **@Setup(Level.Trial)**, giữ graph sống qua các iteration, dùng nhiều thread count, trả về/consume kết quả để tránh dead-code elimination, và chạy đủ lâu để G1 thực hiện hoạt động nền. Nên bổ sung allocation churn và tỷ lệ object sống/chết theo ứng dụng thật.

Dùng hai lớp phép đo:

1. **Microbenchmark:** cô lập thao tác cập nhật reference để quan sát xu hướng của write barrier và throughput.
2. **Macrobenchmark:** chạy toàn bộ dịch vụ với dữ liệu và lưu lượng gần production để biết cải thiện có tác động đến KPI người dùng hay không.

Microbenchmark có thể giải thích cơ chế; macrobenchmark quyết định liệu nâng cấp có đáng giá cho hệ thống.

## 6. Chạy JMH trên JDK 25 và JDK 26

JMH giúp quản lý warmup, measurement iteration và fork của JVM. Hãy build một benchmark JAR duy nhất rồi chạy lần lượt bằng từng runtime.

Ví dụ PowerShell, thay các đường dẫn JDK bằng thư mục cài đặt thực tế:

    $jdk25Path = 'C:\Java\jdk-25'
    $jdk26Path = 'C:\Java\jdk-26'

Chạy trên JDK 25:

    & "$jdk25Path\bin\java.exe" -jar target\benchmarks.jar '.*ReferenceWriteBenchmark.*' -bm thrpt -f 5 -wi 5 -i 8 -w 10s -r 15s -t 8 -jvmArgsAppend "-Xms4g -Xmx4g -XX:+UseG1GC" -rf json -rff results-jdk25.json

Chạy đúng benchmark đó trên JDK 26:

    & "$jdk26Path\bin\java.exe" -jar target\benchmarks.jar '.*ReferenceWriteBenchmark.*' -bm thrpt -f 5 -wi 5 -i 8 -w 10s -r 15s -t 8 -jvmArgsAppend "-Xms4g -Xmx4g -XX:+UseG1GC" -rf json -rff results-jdk26.json

Trong ví dụ:

- **-bm thrpt**: đo throughput.
- **-f 5**: chạy 5 fork JVM độc lập.
- **-wi 5**: 5 warmup iteration.
- **-i 8**: 8 measurement iteration.
- **-w 10s**, **-r 15s**: thời gian mỗi warmup và measurement iteration.
- **-t 8**: dùng 8 benchmark thread.
- **-Xms4g -Xmx4g -XX:+UseG1GC**: cố định heap và collector cho hai phiên bản.

Chọn thời lượng và số thread phù hợp với workload. Không nhất thiết phải dùng đúng các con số ví dụ nếu chúng không đại diện cho production. Chạy JDK 25 và JDK 26 luân phiên hoặc trong cùng một khoảng thời gian kiểm thử để giảm ảnh hưởng do tải máy và môi trường thay đổi. Không chạy đồng thời hai benchmark trên cùng máy nếu chúng tranh CPU hoặc RAM.

Nếu dùng benchmark dịch vụ, hãy chạy riêng một bài với tốc độ request cố định để so sánh latency và error rate; sau đó chạy bài tìm saturation point để đo throughput tối đa. Không dùng kết quả từ hai kiểu tải này thay thế cho nhau.

## 7. Thu thập log GC và số liệu bổ sung

Chạy một lượt chẩn đoán riêng để thu thập GC log:

    -Xlog:gc*,safepoint:file=gc-%p.log:time,uptime,level,tags

Dùng cùng cấu hình log cho cả JDK 25 và JDK 26. File name có PID giúp các fork ghi ra file riêng. GC logging có overhead, vì vậy nên có lượt benchmark chính không bật log nặng và lượt chẩn đoán bật log để giải thích kết quả.

Có thể bật JFR ở một lượt riêng:

    -XX:StartFlightRecording:filename=run-%p.jfr,settings=profile,dumponexit=true

Dùng JFR và GC log để tìm hiểu:

- Tần suất và thời lượng young/mixed/full GC.
- Pause time p50, p95, p99 và pause dài nhất.
- Thời gian GC chạy đồng thời và mức sử dụng CPU của GC.
- Tỷ lệ cấp phát, promotion và kích thước live set.
- Thời gian ứng dụng bị dừng tại safepoint.
- Heap occupancy trước/sau collection và mức sử dụng native memory.

Nếu cần xác nhận collector và JVM flags đang dùng, kiểm tra log khởi tạo hoặc dùng **jcmd <pid> VM.flags**. Kiểm tra heap bằng **jcmd <pid> GC.heap_info**. Không chỉ dựa vào cấu hình dòng lệnh đã viết; hãy kiểm tra cấu hình runtime thực sự nhận được.

## 8. Chọn KPI và tính mức thay đổi

Không chỉ nhìn vào thời gian GC pause. JEP 522 nhắm đến throughput của ứng dụng bằng cách giảm chi phí đồng bộ; một ứng dụng có thể tăng số request xử lý mỗi giây dù tổng pause time chỉ thay đổi rất ít.

Nên ghi lại các nhóm số liệu sau:

| Nhóm | Chỉ số |
|---|---|
| Throughput | Operations/second, requests/second, số tác vụ hoàn thành |
| Latency | p50, p95, p99, max latency |
| Độ ổn định | Error rate, timeout, queue depth, độ dao động giữa các lần chạy |
| CPU | CPU utilization, CPU time trên mỗi request, mức dùng CPU của GC |
| GC | Số collection, tổng pause time, pause dài nhất, thời gian concurrent phase |
| Memory | Heap occupancy, live set, allocation rate, promotion, RSS/native memory |

Tính phần trăm thay đổi throughput:

    throughputGain =
        (throughputJdk26 / throughputJdk25 - 1) * 100%

Tính phần trăm thay đổi latency p99:

    p99Change =
        (p99Jdk26 / p99Jdk25 - 1) * 100%

Ví dụ, nếu JDK 25 đạt 20.000 request/s và JDK 26 đạt 21.000 request/s, throughput tăng 5%. Nếu p99 giảm từ 80 ms xuống 76 ms, p99 giảm 5%. Đây chỉ là ví dụ tính toán, không phải kết quả chuẩn của JEP 522.

Lấy median hoặc phân bố của nhiều fork, không chọn lần chạy tốt nhất. Nếu chênh lệch giữa JDK 25 và JDK 26 nhỏ hơn độ dao động tự nhiên của phép đo, hãy tăng thời lượng, số lần chạy hoặc cải thiện điều kiện benchmark trước khi kết luận.

## 9. Phân biệt JEP 522 với các thay đổi G1 khác

JDK 26 có nhiều thay đổi GC khác ngoài JEP 522. Nếu workload của bạn sử dụng các kiểu object đặc biệt hoặc đi vào tình trạng thiếu heap nghiêm trọng, các thay đổi đó có thể ảnh hưởng đến kết quả trước/sau.

| Thay đổi | Tác động | Cách tách khỏi phép đo JEP 522 |
|---|---|---|
| JEP 522 — giảm đồng bộ card table | Giảm chi phí theo dõi reference update, hướng tới throughput | So sánh cùng G1 trên JDK 25 và 26 với cùng workload reference-heavy |
| Eager reclamation humongous objects có references (JDK-8048180) | Có thể thu hồi sớm humongous object không còn reachable tại một GC pause, không cần chờ concurrent marking toàn heap | Nếu workload dùng object lớn hơn nửa G1 region, đo riêng số lượng, thời điểm thu hồi và heap occupancy |
| G1 hỗ trợ **UseGCOverheadLimit** | Có thể phát sinh OutOfMemoryError khi GC overhead và free heap vượt các ngưỡng được cấu hình trong nhiều collection liên tiếp | Giữ nguyên cờ và điều kiện heap; kiểm thử riêng tình huống gần cạn heap |

Đặc biệt, nếu workload tạo nhiều humongous object chứa reference, đừng gộp mức giảm heap occupancy do eager reclamation vào kết luận về throughput của JEP 522. Hãy ghi rõ workload có object lớn hay không và theo dõi heap sau GC.

## 10. Cách đọc kết quả

| Kết quả quan sát | Cách diễn giải |
|---|---|
| Throughput tăng, latency ổn định hoặc giảm | Kết quả phù hợp với mục tiêu của JEP 522; kiểm tra thêm CPU và memory để xác nhận không chuyển chi phí sang nơi khác |
| Throughput gần như không đổi | Workload có thể không bị giới hạn bởi reference-update synchronization; đây không phải bằng chứng G1 không được cải thiện |
| Throughput tăng nhưng p99 xấu đi | Có thể có queueing, GC pause outlier hoặc CPU saturation; cần xem latency distribution và tải offered rate |
| Pause giảm nhưng throughput không đổi | GC pause không phải nút thắt chính của workload, hoặc cải thiện không đủ tác động đến tổng thời gian xử lý |
| Heap/RSS tăng | Kiểm tra native memory, card table bổ sung, heap sizing và live set; không chỉ xem heap used |
| JDK 26 nhanh hơn nhưng JDK 27 chậm hơn | Kiểm tra JEP 523 và collector thực tế, compact object headers, JDK update, flags và các thay đổi runtime khác trước khi quy kết cho G1 |

Một kết quả không tăng throughput vẫn có giá trị: nó cho biết workload không khai thác đáng kể phần tối ưu này. Không nên thay đổi cấu trúc object graph chỉ để cố tạo ra mức tăng từ benchmark nếu thay đổi đó làm ứng dụng phức tạp hơn hoặc tiêu thụ nhiều bộ nhớ hơn.

## 11. Những sai lầm làm phép so sánh mất giá trị

- So sánh JDK 25 chạy Serial với JDK 26 chạy G1 rồi quy toàn bộ chênh lệch cho JEP 522.
- Thay đổi heap, CPU quota, số thread hoặc pause-time goal giữa hai lần chạy.
- Dùng dataset khác nhau hoặc thay đổi seed ngẫu nhiên.
- Đo một lần duy nhất và chọn lần chạy tốt nhất.
- Chạy benchmark trước/sau đồng thời trên cùng máy, khiến hai JVM tranh tài nguyên.
- Chỉ đo một vòng lặp rất ngắn, không có warmup hoặc không tạo đủ hoạt động GC.
- Chỉ đo GC pause mà không đo throughput và latency của ứng dụng.
- Bật GC logging/JFR ở một phía nhưng không bật phía còn lại.
- Dùng workload chỉ cấp phát object mà không có reference update, rồi kết luận JEP 522 không có tác dụng.
- Thay nhiều cờ GC cùng lúc và không lưu lại cấu hình thực tế.

## 12. Quy trình thực hành đề xuất

1. Chọn một workload production có cập nhật reference đáng kể và ghi lại traffic trace/dataset.
2. Tạo benchmark artifact dùng chung cho JDK 25 và JDK 26.
3. Chọn G1 tường minh ở cả hai runtime; giữ heap, CPU và các JVM flags giống nhau.
4. Xác nhận collector và flags thực tế bằng log khởi tạo hoặc **jcmd**.
5. Chạy JMH nhiều fork hoặc tải dịch vụ với cùng concurrency và tốc độ request.
6. Thu throughput, latency, CPU, GC pause, concurrent phase, allocation và memory.
7. Chạy lượt chẩn đoán với GC log/JFR để giải thích khác biệt.
8. Tính median và độ dao động; kiểm tra chênh lệch có lớn hơn noise không.
9. Nếu workload có humongous objects, tách ảnh hưởng eager reclamation khỏi JEP 522.
10. Lặp lại trên JDK 27 nếu đó là runtime đích; kiểm tra JEP 523 và các thay đổi release khác.
11. Chỉ đưa kết luận vào báo cáo khi nêu rõ JDK build, collector, máy, heap, workload, tải và flags.

## 13. Checklist trước khi tuyên bố G1 nhanh hơn

- [ ] Cùng artifact ứng dụng và benchmark.
- [ ] Cùng dữ liệu, seed, live set và workload.
- [ ] Cùng phần cứng, CPU quota, RAM và môi trường.
- [ ] Cùng collector G1 ở hai phía.
- [ ] Cùng **-Xms**, **-Xmx** và các cờ GC/JIT liên quan.
- [ ] Đã kiểm tra collector thực tế và JVM flags.
- [ ] Có warmup, nhiều fork và nhiều lần đo.
- [ ] Đã đo throughput cùng latency p50/p95/p99.
- [ ] Có GC log/JFR để giải thích kết quả.
- [ ] Đã kiểm tra allocation, live set, native memory và humongous objects.
- [ ] Đã tách JEP 522 khỏi thay đổi default collector của JDK 27.
- [ ] Kết luận dựa trên median và độ dao động, không dựa vào con số phần trăm được quảng bá.

JEP 522 là cải tiến runtime đã tích hợp trong G1 của JDK 26, không phải preview hoặc incubator và không yêu cầu bật bằng cờ riêng. Mức tăng thực tế chỉ có thể xác định bằng phép đo trên workload của bạn. Hãy xem các con số 5–15% được công bố như dữ liệu tham khảo để đặt giả thuyết, rồi dùng benchmark trước/sau có kiểm soát để kiểm chứng.

## Tài liệu chính thức

- [JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522): mục tiêu, thiết kế hai card table và kết quả thử nghiệm.
- [Oracle — Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): xác nhận throughput G1 được cải thiện bằng cách giảm đồng bộ giữa application threads và GC threads.
- [Inside Java — Performance Improvements in JDK 26](https://inside.java/2026/06/09/jdk-26-performance-improvements/): giải thích active/inactive card table, thao tác hoán đổi nguyên tử, số liệu throughput và chi phí bộ nhớ.
- [Oracle — Consolidated JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html): các thay đổi G1 khác trong JDK 26, gồm eager reclamation humongous objects và hỗ trợ GC overhead limit.
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523): thay đổi default collector từ JDK 27.
- [Inside Java — JDK 27: Default G1 in All Environments](https://inside.java/2026/07/20/quality-heads-up/): điều kiện default G1 trước JDK 27 và khuyến nghị benchmark collector trên môi trường hạn chế.
- [Oracle — Introduction to Garbage Collection Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/introduction-garbage-collection-tuning.html): cách tiếp cận chọn collector, heap và đo hiệu năng.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ benchmark JVM có warmup, fork và measurement iteration.

Các kết quả và mô tả trong bài được đối chiếu với tài liệu JDK 26/27 hiện hành tại ngày 27-11-2026. JEP 522 là thay đổi đã tích hợp trong G1; phần trăm throughput chỉ là kết quả thử nghiệm tham khảo, không phải bảo đảm cho mọi ứng dụng.
