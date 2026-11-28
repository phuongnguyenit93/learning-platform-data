# Giảm đồng bộ hóa để cải thiện thông lượng

JDK 26 đưa vào **JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization**. Thay đổi này giảm phối hợp giữa các luồng ứng dụng (*mutator threads*) và các luồng refinement/optimizer của G1 khi theo dõi những vùng heap có tham chiếu vừa được cập nhật. Cơ chế mới dùng hai card table để tách công việc của ứng dụng khỏi công việc xử lý nền, nhờ đó giảm chi phí write barrier và cải thiện thông lượng.

JEP 522 là thay đổi triển khai của G1 trong JDK 26, không phải API mới, preview hay incubator. Ứng dụng đang dùng G1 nhận cải tiến này khi chạy trên JDK 26 trở lên mà không cần sửa mã nguồn hoặc bật một cờ riêng. JDK 27 tiếp tục giữ cải tiến này. Bài viết tập trung vào cơ chế và cách kiểm chứng hiệu quả trong workload thực tế.

## 1. Bối cảnh: vì sao G1 cần card table?

G1 chia Java heap thành nhiều region. Khi thu gom một tập region, G1 cần biết những object ở bên ngoài tập đang thu gom nhưng lại giữ reference trỏ vào object bên trong tập đó. Tập các vị trí tham chiếu như vậy được theo dõi qua **remembered set**.

Nếu phải quét toàn bộ heap để tìm mọi reference liên vùng trong mỗi lần thu gom, chi phí sẽ rất lớn. Vì vậy, G1 theo dõi những vùng nhỏ của heap gọi là **card**. Card table là metadata đánh dấu card nào có thể chứa reference vừa được cập nhật. Khi một ứng dụng ghi một object reference vào field, write barrier do JVM chèn vào mã thực thi sẽ thực hiện việc theo dõi card cần thiết.

Ví dụ, thao tác Java bình thường sau có thể kích hoạt write barrier của G1:

```java
order.setCustomer(customer);
```

Nếu `customer` là object được tham chiếu từ field của `order`, G1 cần theo dõi vùng heap chứa field đó để có thể cập nhật remembered set khi cần. Ứng dụng không gọi card table trực tiếp; đây là công việc nội bộ của JVM.

Các refinement threads xử lý những card đã dirty ở chế độ nền. Chúng quét các reference liên quan rồi cập nhật remembered sets để G1 có thể tìm heap roots hiệu quả trong các collection pause tiếp theo.

## 2. Vấn đề trước JEP 522

Trước JDK 26, mutator threads và refinement threads có thể cùng làm việc trên card table đang được sử dụng. Để tránh ghi đè hoặc bỏ sót thông tin khi hai nhóm thread thao tác đồng thời, G1 cần phối hợp ở mức chi tiết giữa các lần cập nhật card và quá trình refinement.

Điều này làm write barrier phức tạp hơn. Write barrier được thực thi trên đường ghi object reference của ứng dụng; vì vậy, chi phí nhỏ trên mỗi lần ghi có thể cộng dồn đáng kể trong workload có nhiều cập nhật reference.

Chi phí không chỉ nằm ở số lệnh CPU. Sự phối hợp giữa mutator và refinement còn có thể làm tăng tranh chấp, ảnh hưởng khả năng tối ưu của JIT và lấy đi CPU time mà ứng dụng có thể dùng để xử lý request.

## 3. JEP 522: tách công việc bằng hai card table

JDK 26 bổ sung một card table thứ hai. Hai bảng có vai trò luân phiên:

- **Active card table:** mutator threads ghi dấu các card dirty khi ứng dụng cập nhật object reference.
- **Refinement table:** refinement threads xử lý các card đã được tách khỏi bảng active và cập nhật remembered sets.

G1 có thể hoán đổi vai trò hai bảng bằng một thao tác atomic khi lượng card dirty trong bảng active tiến gần mức mà việc quét chúng trong pause có nguy cơ vượt pause-time target.

```text
Trước JEP 522

  Mutator threads  ──┐
                    ├── cùng phối hợp trên card table
  Refinement threads┘

Sau JEP 522

  Mutator threads ───────> Active card table
                                │
                         atomic table swap
                                │
  Refinement threads <── Refinement table
                         (xử lý bảng đã tách)
```

Sau khi đổi bảng, mutator threads tiếp tục đánh dấu card trên bảng active mới, ban đầu đang rỗng. Refinement threads xử lý bảng cũ mà không phải tranh chấp từng lần ghi với ứng dụng. Khi cần, G1 lại hoán đổi vai trò hai bảng để chuyển một lô card dirty sang refinement.

Việc trao đổi công việc theo lô bằng cách đổi bảng giúp loại bỏ phần lớn đồng bộ hóa fine-grained trên đường write barrier. Thiết kế tổng thể của G1, remembered set và cách ứng dụng sử dụng GC không thay đổi.

## 4. Tác động đến write barrier và hiệu năng

Theo thông tin kỹ thuật của nhóm phát triển Java, thay đổi này rút gọn write barrier trên x64 từ khoảng **50 lệnh xuống khoảng 12 lệnh** trong trường hợp được mô tả. Ít lệnh hơn và ít phối hợp giữa mutator/refinement giúp giảm overhead trên các thao tác cập nhật object reference.

Các phép đo được công bố cho thấy:

| Đặc điểm workload | Kết quả được báo cáo |
| --- | --- |
| Cập nhật object reference thường xuyên | Throughput tăng khoảng 5–15% trong các workload được thử nghiệm |
| Cập nhật reference ít hơn trên x64 | Một số phép đo vẫn ghi nhận mức tăng đến khoảng 5% nhờ write barrier đơn giản hơn |
| GC pause | Thiết kế mới cũng ghi nhận pause time giảm nhẹ trong các phép đo được công bố |
| Native memory | Card table bổ sung cần khoảng 2 MB native memory cho mỗi 1 GB Java heap, tương đương xấp xỉ 0,2% heap capacity |

Đây là kết quả đo trên các workload và cấu hình cụ thể, không phải cam kết rằng mọi ứng dụng sẽ nhanh hơn đúng 5–15%. Mức lợi ích phụ thuộc tần suất cập nhật reference, kích thước heap, số thread, CPU, cấu hình GC và những bottleneck khác của ứng dụng.

Chi phí card table bổ sung là native memory, không phải Java heap. Khi lập ngân sách bộ nhớ cho container hoặc máy chủ, cần tính cả native memory của JVM thay vì chỉ nhìn `-Xmx`.

## 5. Workload nào có thể hưởng lợi nhiều?

JEP 522 nhắm tới overhead phát sinh khi ứng dụng thường xuyên ghi object reference. Một số workload có nhiều thao tác dạng này:

- Cache hoặc registry thường xuyên thay thế reference tới entry, node hoặc value object.
- Hệ thống xử lý entity graph, quan hệ object hoặc cấu trúc dữ liệu liên kết.
- In-memory index, graph traversal structure hoặc queue có cập nhật liên tục các liên kết object.
- Dịch vụ xử lý nhiều request đồng thời, mỗi request tạo hoặc thay đổi nhiều quan hệ giữa object.

Ví dụ đơn giản về workload có nhiều reference update:

```java
final class Node {
    Node next;
    Object value;
}

static void relink(Node[] nodes, Node[] targets) {
    for (int i = 0; i < nodes.length; i++) {
        nodes[i].next = targets[i];
    }
}
```

Mỗi phép gán `nodes[i].next` cập nhật một reference field. Trong chương trình thực tế, các phép ghi này thường nằm giữa nhiều logic nghiệp vụ và có thể diễn ra trên nhiều application threads.

Workload chủ yếu tính toán số học trên primitive, chờ I/O hoặc ít thay đổi reference có thể nhận lợi ích nhỏ hơn. Nếu ứng dụng đã bị giới hạn bởi database, network, lock của chính ứng dụng hoặc memory bandwidth, tối ưu write barrier có thể không thay đổi đáng kể throughput tổng thể.

## 6. Không cần bật một cờ riêng cho JEP 522

JEP 522 là một phần của implementation G1 trong JDK 26. Khi chạy G1 trên JDK 26 hoặc mới hơn, cơ chế hai card table được sử dụng tự động. Không có API Java để gọi và không cần `--enable-preview`, `--add-modules` hoặc một cờ bật JEP 522 riêng.

Có thể chọn G1 rõ ràng bằng:

```bash
java -XX:+UseG1GC -jar application.jar
```

JDK 26 dùng G1 làm collector mặc định trong các môi trường server-class theo lựa chọn ergonomics; môi trường tài nguyên hạn chế có thể chọn Serial GC. Nếu muốn chắc chắn ứng dụng đang dùng G1 khi kiểm thử JDK 26, hãy chỉ định `-XX:+UseG1GC`.

Từ JDK 27, **JEP 523** làm G1 trở thành collector mặc định của HotSpot trong mọi môi trường, kể cả những môi trường trước đó có thể chọn Serial GC. JEP 523 là thay đổi mặc định lựa chọn collector; nó khác với JEP 522, vốn tối ưu cách G1 đồng bộ hóa card table. Khi so sánh hiệu năng giữa JDK 25, 26 và 27, hãy chỉ định cùng một collector để tránh nhầm tác động của hai thay đổi này.

## 7. Xác nhận JVM đang dùng G1

Bật unified GC logging để xác nhận collector được chọn và thu thập dữ liệu GC:

```bash
java -XX:+UseG1GC \
     -Xlog:gc*=info:file=gc.log:time,uptime,level,tags \
     -jar application.jar
```

Ở phần log khởi động, kiểm tra dòng thông báo collector, chẳng hạn `Using G1`. File `gc.log` giúp xem các collection pause, thời gian GC và hoạt động của G1 trong lúc ứng dụng chạy.

Có thể kiểm tra nhanh trên một JDK cụ thể:

```bash
java -XX:+UseG1GC -Xlog:gc*=info -version
```

Không cần tìm một dòng log riêng nói rằng JEP 522 đã bật. JEP 522 là thay đổi nội bộ của G1 được dùng tự động trong các JDK có triển khai nó; xác nhận G1 đang chạy trên JDK 26+ là điều kiện thực tế cần kiểm tra.

## 8. Đo hiệu quả trên ứng dụng thực tế

Để đánh giá lợi ích, so sánh cùng workload trên JDK 25 và JDK 26/27. JDK 25 là baseline trước JEP 522; JDK 26 là phiên bản đầu tiên tích hợp thay đổi. JDK 27 tiếp tục có cải tiến này.

Giữ các điều kiện càng giống nhau càng tốt:

1. Cùng CPU, hệ điều hành, container limit và số CPU được cấp.
2. Cùng ứng dụng, dữ liệu đầu vào, số request và concurrency.
3. Cùng heap size (`-Xms`, `-Xmx`) và cùng collector (`-XX:+UseG1GC`).
4. Cùng cấu hình pause-time goal và các JVM options khác.
5. Có warmup trước khi đo; chạy nhiều lần và dùng cùng khoảng thời gian đo.
6. Chạy workload đại diện cho production, nhất là đường code có nhiều cập nhật object reference.

Thu thập ít nhất các chỉ số sau:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Application throughput (request/s, operation/s) | Ứng dụng hoàn thành được nhiều công việc hơn không? |
| Latency p50, p95, p99 | Thời gian phản hồi trung bình và tail latency có thay đổi không? |
| GC CPU time / process CPU time | GC đang tiêu thụ bao nhiêu CPU so với toàn tiến trình? |
| GC pause duration và tần suất pause | Pause có giảm, tăng hay giữ ổn định? |
| Heap occupancy và allocation rate | Mức sử dụng heap và tốc độ cấp phát có tương đương giữa các lần đo không? |
| Process RSS / native memory | Chi phí bộ nhớ ngoài Java heap có thay đổi không? |

JDK 26 có `MemoryMXBean.getTotalGcCpuTime()` để lấy tổng CPU time dành cho hoạt động GC theo nanosecond. Có thể dùng cùng process CPU time từ `com.sun.management.OperatingSystemMXBean` để theo dõi tỷ lệ CPU của GC. Khi so sánh, dùng cùng cách thu thập số liệu trên tất cả JDK.

Không nên chỉ so một lần chạy hoặc chỉ nhìn thời gian một GC pause. JEP 522 chủ yếu giảm chi phí phối hợp trên đường ghi reference; chỉ workload có hành vi tương ứng mới thể hiện rõ lợi ích. Nếu kết quả không đổi, hãy kiểm tra bottleneck của ứng dụng trước khi kết luận cải tiến không hoạt động.

## 9. Những điều JEP 522 không làm

- Không thay đổi API Java và không yêu cầu sửa code ứng dụng.
- Không loại bỏ write barrier; G1 vẫn phải theo dõi reference để duy trì remembered sets chính xác.
- Không biến G1 thành collector không pause hoặc real-time GC.
- Không bảo đảm throughput luôn tăng 5–15% trên mọi workload.
- Không tự động thay đổi heap size, pause-time target hay concurrency của ứng dụng.
- Không làm các vấn đề như allocation quá cao, memory leak, lock contention trong business code hoặc I/O chậm biến mất.
- Không phải một tùy chọn tuning có thể bật/tắt độc lập trong ứng dụng; nó là thay đổi implementation của G1.

G1 vẫn hướng tới cân bằng giữa throughput và pause time. Nếu yêu cầu của ứng dụng thay đổi, cần đánh giá collector dựa trên latency, throughput, heap footprint và đặc điểm workload tổng thể, thay vì chỉ dựa vào một benchmark reference-write.

## 10. Ghi nhớ

- JEP 522 được tích hợp trong JDK 26 và giảm đồng bộ hóa giữa mutator threads với G1 refinement threads.
- G1 dùng hai card table: ứng dụng đánh dấu bảng active, refinement xử lý bảng còn lại; hai bảng đổi vai trò bằng atomic swap.
- Write barrier đơn giản hơn giúp giảm chi phí khi ứng dụng cập nhật object reference.
- Các phép đo được công bố ghi nhận throughput tăng 5–15% ở workload reference-heavy; đây không phải mức tăng được bảo đảm cho mọi ứng dụng.
- Card table bổ sung cần khoảng 2 MB native memory trên mỗi 1 GB Java heap.
- Không cần API, preview flag hoặc cờ riêng; chọn G1 trên JDK 26+ là đủ để dùng implementation mới.
- JDK 27 còn có JEP 523 làm G1 thành collector mặc định trong mọi môi trường; đây là thay đổi riêng với JEP 522.
- Đánh giá bằng workload production-like, giữ cấu hình nhất quán và đo cả throughput, tail latency, GC CPU, pause và native memory.

## Tài liệu tham khảo

- [JEP 522 — G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522) — mục tiêu và thiết kế thay đổi card table.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — xác nhận JEP 522 là cải tiến hiệu năng trong JDK 26.
- [Java 26 for DevOps, Inside.java](https://inside.java/2026/03/02/jdk-26-rn-ops/) — giải thích hai card table, write barrier và kết quả benchmark được công bố.
- [Performance Improvements in JDK 26, Inside.java](https://inside.java/2026/06/09/jdk-26-performance-improvements/) — mô tả chi tiết cơ chế active/refinement table và chi phí bộ nhớ.
- [Garbage-First (G1) Garbage Collector, Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html) — remembered sets, G1 internals, pause-time goal và cách bật G1.
- [The `java` Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — `-XX:+UseG1GC` và unified GC logging.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — JEP 523 đưa G1 thành collector mặc định trong mọi môi trường.
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523) — thay đổi lựa chọn GC mặc định từ JDK 27.
