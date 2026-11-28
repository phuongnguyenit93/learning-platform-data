# Bài toán đồng bộ giữa luồng ứng dụng và luồng GC

## 1. Mục tiêu và bối cảnh

G1 là garbage collector mặc định của HotSpot trong các cấu hình JDK hiện hành. G1 hướng tới việc cân bằng throughput với các khoảng dừng GC tương đối ngắn và có thể dự đoán. Để thu gom một vùng heap mà không quét toàn bộ heap, G1 duy trì remembered set: tập các vị trí nằm ngoài vùng đang thu gom nhưng có tham chiếu trỏ vào vùng đó.

JEP 522, được đưa vào JDK 26, cải thiện throughput của G1 bằng cách giảm đồng bộ hóa giữa application threads (mutator threads) và các GC refinement threads. Thay đổi cốt lõi là dùng hai card table thay vì để hai nhóm thread cùng phối hợp trên một bảng. JDK 27 tiếp tục có cải tiến này; không cần thay đổi mã ứng dụng hay bật một tùy chọn GC riêng.

Bài học giải thích:

- Vì sao G1 cần card table và write barrier.
- Vì sao cập nhật tham chiếu trước JDK 26 tạo chi phí đồng bộ.
- Cơ chế hai card table và chuyển đổi vai trò bằng atomic swap.
- Workload nào có thể hưởng lợi, mức cải thiện và chi phí bộ nhớ.
- Cách kiểm tra G1 đang chạy và benchmark trước/sau khi nâng JDK.

## 2. G1 cần remembered set để làm gì?

### 2.1. Heap được chia thành region

G1 chia Java heap thành nhiều region có kích thước bằng nhau. Các region được sử dụng cho vùng trẻ (young) hoặc vùng già (old). Khi thu gom một collection set, G1 di chuyển các object còn sống ra khỏi những region được chọn và thu hồi phần còn lại.

Một object nằm ngoài collection set có thể giữ tham chiếu tới object bên trong collection set. G1 cần tìm các tham chiếu đi vào collection set để cập nhật chúng sau khi object được di chuyển.

Nếu mỗi lần GC phải quét mọi object trong toàn bộ heap để tìm tham chiếu như vậy, chi phí sẽ rất lớn. Remembered set giúp giới hạn phạm vi tìm kiếm vào những vị trí có khả năng chứa tham chiếu đi vào region cần thu gom.

### 2.2. Card là một vùng nhỏ của heap

G1 chia heap logic thành các card. Theo tài liệu G1 hiện hành, một card mặc định đại diện khoảng 512 byte heap. Card table lưu trạng thái của các card, chẳng hạn card đã bị ghi (dirty) sau khi ứng dụng thay đổi một tham chiếu.

Remembered set dùng card làm đơn vị đại diện gần đúng cho vị trí tham chiếu. Một card có thể chứa nhiều trường object; vì vậy card table không lưu từng con trỏ Java riêng lẻ mà ghi nhận vùng có thể cần refinement.

Ví dụ:

~~~text
Heap region A                         Heap region B
+-----------------------+             +-----------------------+
| Object A1             |             | Object B1             |
|   ref -> Object B1    | ----------> |                       |
|                       |             |                       |
+-----------------------+             +-----------------------+
       Card A1                                  Card B1
          |
          +-- được đánh dấu dirty khi ref thay đổi
~~~

Khi G1 thu gom region B, remembered set cho biết cần kiểm tra những card ở các region khác có thể chứa tham chiếu trỏ vào B.

## 3. Write barrier chạy khi ứng dụng thay đổi reference

Khi code Java gán một object reference vào field, ví dụ:

~~~java
order.setCustomer(customer);
node.next = nextNode;
cache.put(key, value);
~~~

JIT có thể chèn write barrier quanh thao tác ghi. Với G1, post-write barrier đánh dấu card chứa vị trí vừa cập nhật để GC biết rằng vùng đó cần được xem xét khi xây dựng hoặc cập nhật remembered set.

Write barrier là mã do JVM/JIT sinh ra; lập trình viên không cần tự gọi một API GC nào.

Một thao tác ghi reference có thể xảy ra rất thường xuyên trong:

- Cache và cấu trúc dữ liệu liên kết.
- ORM và object graph của ứng dụng nghiệp vụ.
- Hệ thống xử lý request tạo/cập nhật nhiều object.
- In-memory index, graph, queue hoặc registry.
- Ứng dụng nhiều thread cùng cập nhật field tham chiếu.

Các phép ghi primitive như gán `int` hoặc `long` không phải kiểu ghi reference mà card-table write barrier này theo dõi. Vì vậy, workload chủ yếu cập nhật số nguyên hoặc tính toán số học có thể nhận lợi ích trực tiếp nhỏ hơn.

## 4. Vấn đề đồng bộ trước JDK 26

Trước JEP 522, G1 sử dụng một card table chung cho việc ghi nhận thay đổi và refinement. Application threads thực hiện write barrier để đánh dấu card dirty; concurrent refinement threads đọc và xử lý những card đó nhằm cập nhật remembered set.

Hai nhóm thread cùng tương tác với cấu trúc dữ liệu nên phải phối hợp để tránh ghi đè trạng thái hoặc bỏ sót card. Cơ chế cũ sử dụng các bước đồng bộ, dirty-card queue và đường xử lý phụ khi queue cần được chuyển giao.

Một write barrier vì thế không chỉ đánh dấu card:

1. Kiểm tra một số điều kiện để tránh xử lý các trường hợp không cần thiết.
2. Đồng bộ với thread refinement để đảm bảo trạng thái card nhất quán.
3. Đánh dấu card dirty.
4. Đưa thông tin card vào dirty-card queue.
5. Khi buffer đầy, chuyển buffer sang cấu trúc dùng chung để refinement thread xử lý.

Cách làm này bảo đảm tính đúng đắn, nhưng chi phí xuất hiện trên đường ghi reference của ứng dụng. Với workload cập nhật nhiều object reference, chi phí write barrier có thể chiếm phần đáng kể thời gian CPU.

### 4.1. Vì sao đồng bộ ảnh hưởng throughput?

Giả sử một ứng dụng xử lý hàng triệu thao tác cập nhật field tham chiếu mỗi giây. Mỗi thao tác ghi có thể phải chạy thêm các bước kiểm tra, đồng bộ và ghi nhận card.

Chi phí nhỏ trên một lần ghi sẽ tích lũy thành chi phí lớn khi:

- Có nhiều application threads ghi đồng thời.
- Có nhiều card cần refinement.
- Refinement threads và application threads phải phối hợp thường xuyên.
- Write barrier dài làm tăng code footprint và hạn chế một số tối ưu của JIT.

Throughput là lượng công việc ứng dụng hoàn thành trong một đơn vị thời gian. Khi ứng dụng dành nhiều CPU hơn cho write barrier, lượng CPU còn lại cho logic nghiệp vụ giảm. Trong một số workload, thời gian phối hợp cũng có thể ảnh hưởng latency.

## 5. JEP 522: hai card table thay vì một bảng dùng chung

### 5.1. Ý tưởng

JDK 26 đưa vào card table thứ hai. Hai bảng có vai trò tách biệt tại một thời điểm:

- **Active card table**: application threads ghi nhận card dirty khi cập nhật reference.
- **Refinement card table**: GC refinement/optimizer threads xử lý card đã được bàn giao để cập nhật remembered set.

Application threads chỉ ghi vào bảng active. Refinement threads làm việc trên bảng còn lại. Hai nhóm không phải liên tục đồng bộ trên cùng một card table cho từng lần ghi reference.

Khi G1 dự đoán việc quét active table trong pause tiếp theo có thể vượt mục tiêu thời gian dừng, JVM atomically swap vai trò của hai bảng:

1. Bảng đang được application threads ghi trở thành bảng refinement.
2. Bảng đã được refinement xử lý trở thành bảng active mới.
3. Application threads tiếp tục ghi vào bảng active mới.
4. Refinement threads xử lý bảng vừa được bàn giao.

Việc chuyển vai trò diễn ra bằng một lần chuyển đổi nguyên tử ở cấp bảng. Nó thay thế phần phối hợp fine-grained lặp đi lặp lại giữa mutator và refinement threads.

### 5.2. Sơ đồ trước và sau JDK 26

~~~mermaid
flowchart TB
  subgraph OLD["Trước JDK 26: một card table dùng chung"]
    A1["Application threads"] --> W1["Write barrier"]
    G1["GC refinement threads"] --> W1
    W1 --> C1["Shared card table / dirty-card queues"]
    C1 --> S1["Fine-grained synchronization"]
  end
  subgraph NEW["JDK 26 trở đi: hai card table"]
    A2["Application threads"] --> W2["Write barrier"]
    W2 --> T1["Active card table"]
    G2["GC refinement threads"] --> T2["Refinement card table"]
    T1 --> SW["Atomic swap khi cần bàn giao"]
    T2 --> SW
    SW --> T1
    SW --> T2
  end
~~~

Sơ đồ thể hiện ý tưởng tách đường ghi card của ứng dụng khỏi đường refinement. G1 vẫn cần phối hợp để chuyển đổi vai trò và thực hiện các pha GC; JEP 522 loại bỏ phần đồng bộ fine-grained trên đường ghi reference, không loại bỏ toàn bộ synchronization trong garbage collector.

### 5.3. Minh họa một lần chuyển bảng

~~~text
Trước khi swap:

Application threads  --->  Card table A (active)
Refinement threads   --->  Card table B (đang được xử lý)

Khi cần bàn giao:

              atomic swap

Sau khi swap:

Application threads  --->  Card table B (active mới)
Refinement threads   --->  Card table A (bảng vừa bàn giao)
~~~

Bảng mà ứng dụng ghi và bảng mà refinement threads xử lý được đổi vai trò. Ứng dụng tiếp tục ghi mà không phải chờ refinement xử lý từng card trên cùng bảng.

## 6. Write barrier được đơn giản hóa như thế nào?

Khi application threads sở hữu riêng active card table, chúng không cần phối hợp fine-grained với refinement threads trên cùng bảng cho mỗi lần ghi. Write barrier vì thế ngắn hơn và ít công việc phụ hơn.

Theo số liệu JEP 522 được Inside Java công bố:

- Trên x64, write barrier của G1 giảm từ khoảng 50 instruction xuống khoảng 12 instruction.
- Workload cập nhật object reference nhiều ghi nhận mức tăng throughput khoảng 5–15%.
- Ngay cả workload ít cập nhật reference hơn cũng có thể đạt mức tăng đến khoảng 5% trong các phép đo được nêu.
- Pause time giảm nhẹ trong các phép đo đó.

Các con số trên là kết quả benchmark của JEP và những workload đã thử nghiệm, không phải cam kết rằng mọi ứng dụng sẽ nhanh hơn đúng tỷ lệ đó. Kết quả thực tế phụ thuộc CPU, JDK build, heap, mức đồng thời, cấu trúc object và tỷ lệ cập nhật reference.

## 7. Chi phí bộ nhớ và các giới hạn

### 7.1. Card table thứ hai tiêu tốn bao nhiêu?

Một card table bổ sung có chi phí xấp xỉ 0,2% dung lượng heap, tương đương khoảng 2 MB native memory cho mỗi 1 GB heap theo số liệu JEP 522.

Ví dụ quy đổi gần đúng:

| Java heap | Native memory cho card table bổ sung |
|---:|---:|
| 1 GB | 2 MB |
| 4 GB | 8 MB |
| 8 GB | 16 MB |
| 16 GB | 32 MB |
| 32 GB | 64 MB |

Đây là ước lượng để lập ngân sách bộ nhớ, không phải kích thước cố định trên mọi nền tảng. Card table dùng native memory, không phải vùng object heap Java. Khi đánh giá container memory, cần tính cả native memory và các thành phần ngoài heap.

### 7.2. Không phải workload nào cũng tăng tốc như nhau

JEP 522 đặc biệt hữu ích khi ứng dụng có nhiều thao tác ghi reference. Nếu ứng dụng chủ yếu:

- Tính toán số học trên primitive.
- Đọc dữ liệu mà ít thay đổi reference.
- Bị giới hạn bởi I/O hoặc network.
- Bị giới hạn bởi lock của nghiệp vụ hoặc database.
- Dành phần lớn thời gian ở một bottleneck khác.

thì cải thiện write barrier có thể không tạo khác biệt lớn ở throughput tổng thể.

JEP 522 cũng không thay đổi thuật toán G1 thành một collector mới. Các đặc tính chính của G1 như region-based collection, remembered set, concurrent marking, evacuation và pause-time heuristics vẫn giữ vai trò như trước.

## 8. Ứng dụng có cần sửa code hoặc bật flag không?

Không. JEP 522 là cải tiến nội bộ của HotSpot G1:

- Không có API Java mới cần gọi.
- Không cần thêm module.
- Không cần bật `--enable-preview`.
- Không cần một flag riêng để kích hoạt hai card table.
- Không cần sửa các phép gán object reference trong ứng dụng.

Khi chạy trên JDK 26 trở lên và sử dụng G1, cơ chế mới được sử dụng tự động. JDK 27 tiếp tục giữ cải tiến này.

JDK 27 chọn G1 làm collector mặc định nếu người dùng không chỉ định collector khác. Có thể xác nhận collector đang dùng qua GC log:

~~~bash
java -Xlog:gc -version
~~~

Hoặc khi khởi chạy ứng dụng:

~~~bash
java -Xlog:gc -jar app.jar
~~~

Log sẽ cho biết collector được JVM sử dụng, ví dụ `Using G1`. Nếu ứng dụng đang dùng ZGC hoặc Parallel GC, JEP 522 không thay đổi collector đó; lợi ích của JEP này chỉ áp dụng khi chạy G1.

## 9. Quan sát hoạt động G1 bằng unified logging

JDK hiện hành dùng unified JVM logging. Có thể bắt đầu với:

~~~bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Khi cần phân tích sâu hơn, dùng:

~~~bash
java -Xlog:gc*=debug:file=gc-debug.log:time,uptime,level,tags -jar app.jar
~~~

Một số tag hữu ích:

| Logging selector | Mục đích |
|---|---|
| `gc` | Loại collection, pause và lượng heap trước/sau GC |
| `gc+phases=info` | Thời gian các pha GC ở mức thông tin |
| `gc+phases=debug` | Chi tiết hơn về từng pha, bao gồm Scan Heap Roots |
| `gc+heap=info` | Trạng thái heap và region |
| `gc+cpu=info` | User, system và real time trong pause |
| `safepoint` | Thông tin các safepoint và thời gian ứng dụng bị dừng |

Ví dụ:

~~~bash
java -Xlog:gc+phases=debug,gc+heap=info,gc+cpu=info -jar app.jar
~~~

Log GC giúp quan sát pause, pha xử lý remembered set và CPU tiêu thụ. Nó không trực tiếp cho biết chính xác bao nhiêu phần trăm CPU đã dành cho từng lệnh write barrier; để xác định chi tiết ở mức máy, cần profiler hoặc phân tích mã máy được JIT sinh ra.

Không dùng các cờ logging GC cũ như `-XX:+PrintGCDetails` hoặc `-XX:+PrintGCDateStamps` cho cấu hình mới. Hãy dùng unified logging `-Xlog`.

## 10. Benchmark để xác định ứng dụng có hưởng lợi hay không

Muốn đánh giá JEP 522, cần so sánh cùng workload trên JDK trước và sau khi có cải tiến, với điều kiện chạy tương đương.

### 10.1. Chọn workload có cập nhật reference

Ví dụ một cấu trúc dữ liệu liên kết có nhiều field reference được cập nhật:

~~~java
final class Node {
    Node next;
    Node previous;
    Node parent;
}

static void rewriteReferences(Node[] nodes, int rounds) {
    int length = nodes.length;

    for (int round = 0; round < rounds; round++) {
        for (int i = 0; i < length; i++) {
            Node current = nodes[i];

            current.next = nodes[(i + 1) % length];
            current.previous = nodes[(i + length - 1) % length];
            current.parent = nodes[(i * 31) % length];
        }
    }
}
~~~

Ví dụ này minh họa workload ghi nhiều object reference. Nó chưa phải benchmark hoàn chỉnh: benchmark thật phải tạo dữ liệu đại diện, giữ kết quả được sử dụng và đo trong một harness có warmup để tránh JIT loại bỏ công việc hoặc làm sai kết quả.

### 10.2. Điều kiện so sánh

Khi so sánh JDK 25 với JDK 26 hoặc JDK 27:

1. Dùng cùng phần cứng, hệ điều hành, CPU quota và cấu hình container.
2. Dùng cùng dữ liệu đầu vào, số thread, thời gian chạy và tải request.
3. Giữ heap size và collector giống nhau; nếu so sánh G1 thì cả hai lần đều phải dùng G1.
4. Giữ các JVM options giống nhau nếu option còn hợp lệ ở cả hai bản.
5. Chạy warmup và nhiều lần đo; không kết luận từ một lần chạy.
6. Đo cả throughput, latency và GC pause.
7. Kiểm tra ứng dụng hoàn thành cùng lượng công việc và trả kết quả tương đương.

Không có flag riêng để tắt JEP 522 trong JDK 26/27 nhằm tạo một baseline cũ ngay trong cùng runtime. So sánh thực tế thường dùng JDK 25 làm baseline và JDK 26/27 làm phiên bản sau nâng cấp; cần ghi nhận các thay đổi JDK khác cũng có thể ảnh hưởng kết quả.

### 10.3. Các chỉ số cần theo dõi

| Chỉ số | Điều cần quan sát |
|---|---|
| Throughput | Số request hoặc công việc hoàn thành mỗi giây |
| p50/p95/p99 latency | Thay đổi độ trễ ở các phân vị |
| CPU utilization | CPU dành cho ứng dụng và GC |
| Tổng thời gian pause | Mức dừng ứng dụng do GC |
| Pause p95/p99 | Những lần GC pause dài |
| Heap occupancy | Mức dùng heap và xu hướng tăng trưởng |
| GC phase time | Thời gian Scan Heap Roots và các pha liên quan |
| Native memory | Chi phí card table bổ sung và các vùng native khác |

Kỳ vọng hợp lý là write barrier nhẹ hơn và throughput tăng ở workload reference-heavy. Không nên mặc định pause sẽ giảm mạnh; JEP 522 chủ yếu hướng tới throughput và chỉ ghi nhận mức giảm pause nhẹ trong các phép đo được công bố.

## 11. Cách nâng cấp và cấu hình G1 hiện hành

### 11.1. Chọn JDK còn được hỗ trợ

JEP 522 có từ JDK 26 và tiếp tục có trong JDK 27. Tính đến ngày 27/11/2026:

- JDK 27 là feature release GA mới hơn.
- JDK 26 đã kết thúc vòng đời hỗ trợ theo lộ trình Oracle từ tháng 09/2026.
- Chính sách hỗ trợ có thể khác nhau giữa Oracle JDK và các nhà cung cấp OpenJDK khác.

Nếu cần sử dụng cải tiến G1 này, hãy chọn JDK 26+ còn được nhà cung cấp hỗ trợ. Với hệ thống cần LTS, hãy cân nhắc rằng JDK 25 LTS chưa chứa JEP 522; việc chọn LTS hay feature release cần dựa trên chính sách nâng cấp và hỗ trợ của tổ chức.

### 11.2. Bắt đầu với cấu hình G1 mặc định

Tài liệu Oracle khuyến nghị bắt đầu bằng G1 default settings, chỉ điều chỉnh mục tiêu pause hoặc heap size khi có số liệu chứng minh cần thiết.

Ví dụ cấu hình cơ bản:

~~~bash
java -Xms2g -Xmx4g -Xlog:gc -jar app.jar
~~~

Nếu muốn chỉ định G1 tường minh:

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx4g -Xlog:gc -jar app.jar
~~~

Nếu throughput quan trọng hơn pause, có thể đánh giá việc nới mục tiêu pause bằng `-XX:MaxGCPauseMillis`. Đây là mục tiêu cho heuristic, không phải cam kết mọi pause đều không vượt quá giá trị đặt ra.

Không nên khóa cứng young generation bằng `-Xmn` hoặc `-XX:NewRatio` nếu chưa hiểu ảnh hưởng. Những tùy chọn này có thể làm G1 mất khả năng tự điều chỉnh kích thước young generation để đáp ứng pause-time goal.

JEP 522 không yêu cầu bật một option kiểu `G1UseModernWriteBarrier`; không thêm flag không được tài liệu JDK chính thức công bố để cố kích hoạt tính năng.

## 12. Phân biệt cải tiến JEP 522 với các vấn đề GC khác

JEP 522 xử lý chi phí đồng bộ trên đường ghi nhận thay đổi reference. Nó không tự giải quyết mọi vấn đề hiệu năng hoặc bộ nhớ.

| Triệu chứng | Có phải vấn đề JEP 522 trực tiếp xử lý? | Hướng điều tra |
|---|---|---|
| CPU cao khi ứng dụng cập nhật nhiều object reference | Có thể liên quan | Benchmark JDK 25 với JDK 26+ trên cùng workload |
| Pause dài do evacuation hoặc Full GC | Không trực tiếp | Kiểm tra GC log, heap pressure, evacuation failure và humongous objects |
| Heap tăng liên tục do giữ reference không cần thiết | Không | Phân tích object retention, heap dump và memory leak |
| Latency cao do lock nghiệp vụ | Không | Dùng profiler và thread dump để tìm lock contention |
| Allocation rate quá cao | Không trực tiếp | Giảm allocation hoặc tối ưu vòng đời object |
| CPU chủ yếu bị chiếm bởi I/O, database hoặc network | Thường không đáng kể | Tối ưu bottleneck tương ứng |

G1 vẫn phải thực hiện marking, refinement, remembered-set processing, evacuation và reclaim. Việc giảm chi phí write barrier không đồng nghĩa GC không còn pause hoặc không cần concurrent work.

## 13. Kết luận

Bài toán của G1 trước JDK 26 là application threads và refinement threads phải phối hợp khi cùng tương tác với card table và dirty-card tracking. Các bước đồng bộ lặp lại làm write barrier dài và tốn CPU, đặc biệt trong ứng dụng cập nhật object reference thường xuyên.

JEP 522 đưa vào card table thứ hai để tách hai nhóm công việc. Application threads ghi vào active table; refinement threads xử lý bảng còn lại. Khi cần bàn giao công việc, G1 atomically swap vai trò của hai bảng. Nhờ đó, write barrier ngắn hơn, throughput có thể tăng và pause time có thể giảm nhẹ.

Các điểm cần nhớ:

- Card table giúp G1 xây dựng remembered set mà không phải quét toàn bộ heap.
- Write barrier ghi nhận card bị thay đổi khi ứng dụng cập nhật object reference.
- Hai card table loại bỏ phần đồng bộ fine-grained giữa mutator và refinement threads trên cùng bảng.
- Benchmark JEP ghi nhận 5–15% throughput ở workload reference-heavy; kết quả thực tế tùy ứng dụng.
- Card table bổ sung cần khoảng 2 MB native memory cho mỗi 1 GB heap theo ước lượng được công bố.
- JDK 26+ sử dụng cải tiến này tự động khi chạy G1; không cần API hoặc flag riêng.
- Hãy benchmark trên JDK và workload thực tế, quan sát GC bằng unified logging và bắt đầu từ cấu hình G1 mặc định.

## Tài liệu tham khảo chính thức

- [JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522)
- [Performance Improvements in JDK 26 — Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
- [G1 Garbage Collector — Java SE 27 GC Tuning Guide](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)
- [Garbage-First Garbage Collector Tuning — Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html)
- [Introduction to Garbage Collection Tuning — Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/introduction-garbage-collection-tuning.html)
- [The java Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

