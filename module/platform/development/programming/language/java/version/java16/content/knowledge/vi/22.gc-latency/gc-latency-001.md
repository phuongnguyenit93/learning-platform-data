# ZGC concurrent thread-stack processing được cải tiến trong Java 16

Java 16 đưa một thay đổi quan trọng vào Z Garbage Collector (ZGC): xử lý stack của các Java thread được chuyển khỏi phần lớn công việc tại safepoint sang các giai đoạn concurrent. Trước thay đổi này, ZGC phải dừng ứng dụng để quét thread stack; thời gian pause vì vậy có thể tăng theo số lượng thread và lượng frame cần kiểm tra. Từ Java 16, ZGC dùng cơ chế **stack watermark** để xử lý stack theo cách lazy, cooperative, concurrent và incremental.

Cải tiến này vẫn là một phần nền tảng của ZGC hiện đại. Ứng dụng không cần sửa code hoặc bật một flag riêng cho thread-stack processing; khi chọn ZGC, JVM tự áp dụng cơ chế này. Bài học giải thích vì sao thread stack là GC root, cách stack watermark hoạt động, ảnh hưởng tới pause time và cách đánh giá ZGC trên workload thực tế.

## 1. ZGC và mục tiêu giảm độ trễ

ZGC là garbage collector hướng tới ứng dụng cần thời gian phản hồi thấp. Collector thực hiện phần lớn công việc nặng đồng thời với ứng dụng, nhờ đó giảm thời gian Java thread phải dừng để GC hoàn thành một giai đoạn.

ZGC phù hợp để đánh giá trong các hệ thống như:

- API hoặc dịch vụ cần giữ p99 và p99.9 latency thấp.
- Ứng dụng có heap lớn và tập dữ liệu sống lớn.
- Dịch vụ xử lý nhiều request đồng thời.
- Hệ thống có nhiều thread hoạt động và yêu cầu tránh các đợt pause dài.
- Ứng dụng có mục tiêu latency rõ ràng hơn mục tiêu throughput tối đa.

Không phải ứng dụng Java nào cũng cần ZGC. Nếu pause của collector mặc định đã đáp ứng SLA và throughput là ưu tiên chính, hãy đo trước khi đổi collector. ZGC dùng tài nguyên CPU để làm việc concurrent, nên lợi ích latency cần được cân nhắc cùng chi phí throughput và bộ nhớ.

## 2. Vì sao GC phải quét thread stack?

GC cần xác định object nào còn reachable để giữ lại, object nào không còn được tham chiếu để thu hồi. Những tham chiếu trực tiếp hoặc gián tiếp mà GC phải bắt đầu truy vết được gọi là **GC roots**.

Thread stack là một nguồn GC root quan trọng. Stack của mỗi Java thread chứa các frame của những method đang hoạt động. Frame có thể giữ tham chiếu tới object thông qua:

- Biến local đang sống.
- Tham số của method.
- Giá trị tạm được giữ trong frame.
- Tham chiếu được lưu trong các vùng stack mà JVM quản lý.

Ví dụ:

~~~java
public final class OrderService {
    public void process() {
        Order order = loadOrder();
        validate(order);
        persist(order);
    }

    private Order loadOrder() {
        return new Order();
    }

    private void validate(Order order) {
        // Kiểm tra dữ liệu.
    }

    private void persist(Order order) {
        // Ghi dữ liệu.
    }
}
~~~

Khi thread đang thực thi trong **process()**, các frame đang hoạt động có thể giữ tham chiếu tới đối tượng Order. GC phải nhận diện các tham chiếu còn sống này để không thu hồi nhầm object mà ứng dụng vẫn cần.

Nếu JVM không xử lý đúng stack roots, object đang được dùng có thể bị coi nhầm là garbage. Vì vậy, quét stack là một phần cần thiết của quá trình xác định object sống.

## 3. Safepoint và chi phí quét stack trước Java 16

Safepoint là trạng thái mà JVM có thể tạm dừng các Java thread tại những điểm an toàn để thực hiện một số thao tác quản lý runtime. Trong một số pha GC, JVM cần đưa các thread tới safepoint trước khi xử lý dữ liệu nội bộ.

Trước cải tiến của Java 16, ZGC thực hiện xử lý thread stack trong các safepoint của một số pha GC. Thời gian quét phụ thuộc vào lượng stack phải xử lý. Ứng dụng càng có nhiều thread hoặc stack càng sâu thì công việc này có thể càng lớn.

Luồng khái quát trước Java 16:

~~~text
GC yêu cầu safepoint
        |
        v
Java threads tạm dừng
        |
        v
ZGC quét thread stacks
        |
        v
Hoàn tất xử lý stack roots
        |
        v
Java threads tiếp tục chạy
~~~

Dù ZGC đã thực hiện nhiều công việc concurrent, phần quét stack tại safepoint vẫn tạo ra một thành phần pause gắn với root set của các thread.

Vấn đề này đặc biệt đáng chú ý với dịch vụ có nhiều thread. Heap lớn không phải yếu tố duy nhất ảnh hưởng tới pause; lượng root cần xử lý cũng có thể tác động tới thời gian dừng ứng dụng.

## 4. Java 16 thay đổi điều gì?

JEP 376 đưa **Concurrent Thread-Stack Processing** vào ZGC. Mục tiêu là chuyển xử lý thread stack ra khỏi safepoint, đồng thời làm cho công việc này có thể diễn ra theo cách:

- **Lazy:** chỉ xử lý phần stack sâu hơn khi thực sự cần.
- **Cooperative:** thread ứng dụng và GC phối hợp để bảo đảm frame được xử lý trước khi sử dụng.
- **Concurrent:** xử lý diễn ra trong khi ứng dụng tiếp tục chạy.
- **Incremental:** chia công việc thành các phần nhỏ thay vì quét toàn bộ stack trong một pause.

Thay đổi này giúp loại bỏ phần quét thread stack khỏi thời gian dừng tại safepoint của ZGC. Các per-thread roots cũng có thể được xử lý trong pha concurrent.

Luồng khái quát từ Java 16:

~~~text
GC bắt đầu một checkpoint ngắn
        |
        v
JVM đánh dấu trạng thái stack cần xử lý
        |
        v
Java threads tiếp tục chạy
        |
        +-------------------------------+
        |                               |
        v                               v
Thread dùng hoặc unwind frame      GC xử lý frame còn lại
        |                               |
        +---------------+---------------+
                        |
                        v
           Stack được xử lý theo nhu cầu
~~~

Công việc xử lý stack không biến mất. JVM thay đổi thời điểm và cách phân phối công việc để phần quét lớn không còn nằm trong safepoint như trước.

## 5. Stack watermark hoạt động như thế nào?

Để trì hoãn việc quét toàn bộ stack mà vẫn bảo đảm an toàn, ZGC dùng cơ chế **stack watermark**.

Có thể hình dung stack watermark là một ranh giới trên stack, phân biệt:

- Các frame đã được xử lý và có thể được sử dụng an toàn.
- Các frame chưa được xử lý đầy đủ và cần xử lý trước khi được đưa vào sử dụng hoặc được stack walker đọc.

Khi một GC checkpoint xảy ra, JVM cập nhật trạng thái xử lý của stack. Một phần nhỏ ở đỉnh stack được xử lý ban đầu để thread có thể tiếp tục. Các frame sâu hơn được xử lý khi cần.

Ví dụ minh họa:

~~~text
Đỉnh stack
+---------------------------+
| Frame A: đã xử lý         |
+---------------------------+
| Frame B: đã xử lý         |
+---------------------------+
| ---- Stack watermark ---- |
+---------------------------+
| Frame C: chờ xử lý        |
+---------------------------+
| Frame D: chờ xử lý        |
+---------------------------+
| Frame E: chờ xử lý        |
+---------------------------+
Đáy stack
~~~

Watermark không phải một vùng nhớ chứa object. Nó là trạng thái quản lý để JVM biết frame nào đã được xử lý trong pha GC hiện tại.

### Khi thread chuẩn bị quay về frame sâu hơn

Khi method kết thúc, thread có thể chuẩn bị quay về caller frame. Nếu frame sắp được đưa trở lại luồng thực thi vẫn nằm dưới watermark, JVM phải xử lý frame đó trước khi tiếp tục.

Cơ chế barrier ở đường return/unwind kiểm tra trạng thái watermark. Nếu frame chưa an toàn, JVM thực hiện phần xử lý cần thiết rồi mới cho phép thread tiếp tục.

### Khi stack walker cần đọc stack

Một số thành phần JVM cần duyệt stack, ví dụ công cụ runtime hoặc cơ chế lấy stack trace. Nếu stack walker muốn truy cập frame chưa được xử lý, JVM phải bảo đảm frame đó được xử lý trước khi tham chiếu trong frame được đọc.

Nhờ vậy, xử lý lazy không làm thay đổi quy tắc an toàn của GC. JVM trì hoãn công việc nhưng vẫn xử lý trước thời điểm frame cần được quan sát hoặc thực thi.

## 6. Vì sao xử lý lazy giúp giảm pause?

Nếu quét mọi frame trong tất cả thread tại một safepoint, pause phải chờ phần công việc này hoàn tất. Với cách mới, JVM chỉ cần thực hiện phần khởi tạo nhỏ tại checkpoint; phần còn lại được phân phối sang giai đoạn concurrent.

Điều này đem lại hai thay đổi chính:

1. Pause không phải chờ quét toàn bộ thread stack.
2. Thời gian pause không còn tăng theo root-set size chỉ vì phần quét stack nằm trong safepoint.

So sánh:

| Trước Java 16 | Từ Java 16 |
| --- | --- |
| Quét thread stack trong safepoint | Thread-stack processing được chuyển sang concurrent phase |
| Pause chịu ảnh hưởng của lượng stack phải quét | Phần pause liên quan tới quét stack được loại bỏ |
| Xử lý stack theo đợt lớn tại checkpoint | Xử lý lazy và incremental |
| Thread phải chờ phần quét stack hoàn tất tại safepoint | Thread tiếp tục chạy, barrier bảo đảm frame được xử lý khi cần |

Cải tiến này đặc biệt hữu ích cho workload có nhiều thread hoặc stack sâu. Với ứng dụng chỉ có ít thread và stack ngắn, mức cải thiện thực tế có thể nhỏ hơn.

## 7. Xử lý concurrent không có nghĩa là miễn phí

Khi chuyển công việc ra khỏi safepoint, JVM vẫn phải dùng CPU để xử lý stack. Công việc được phân phối trong thời gian ứng dụng đang chạy.

Điều đó có nghĩa:

- GC và ứng dụng có thể cạnh tranh CPU.
- Nếu CPU đã bão hòa, concurrent work có thể ảnh hưởng throughput hoặc latency của thread ứng dụng.
- Nếu allocation rate quá cao, ZGC cần đủ heap headroom để thu gom trong khi ứng dụng tiếp tục cấp phát.
- Workload có live set lớn cần heap đủ để chứa dữ liệu sống và phần cấp phát mới trong thời gian GC chạy.

Concurrent processing giảm thời gian dừng, nhưng không làm tổng công việc GC biến mất.

## 8. Cách bật ZGC trong Java 16

Concurrent thread-stack processing là một phần của triển khai ZGC từ Java 16. Không có tùy chọn riêng để bật hoặc tắt JEP 376.

Trên Java 16, có thể bật ZGC bằng:

~~~bash
java -XX:+UseZGC -jar application.jar
~~~

Ví dụ bật ZGC và ghi log GC cùng safepoint:

~~~bash
java -XX:+UseZGC \
  -Xms2g \
  -Xmx4g \
  -Xlog:gc*,safepoint=info \
  -jar application.jar
~~~

Trong ví dụ:

- **-XX:+UseZGC** chọn ZGC.
- **-Xms2g** đặt heap ban đầu.
- **-Xmx4g** đặt heap tối đa.
- **-Xlog:gc*,safepoint=info** ghi thông tin GC và safepoint để phục vụ phân tích.

Các giá trị heap chỉ là ví dụ. Cần chọn theo live set, allocation rate, giới hạn bộ nhớ và đặc điểm workload.

## 9. Cấu hình ZGC trên JDK hiện đại

Cơ chế concurrent thread-stack processing được duy trì trong ZGC hiện đại. Khi dùng JDK mới, vẫn chọn ZGC bằng:

~~~bash
java -XX:+UseZGC -jar application.jar
~~~

Có một khác biệt lịch sử cần biết: ZGC trong Java 16 chưa có generational mode. Từ JDK 24, ZGC chỉ còn chế độ generational. Khi dùng JDK hiện đại, hãy theo tài liệu của đúng phiên bản runtime; không mang cấu hình lịch sử của Java 16 sang bản JDK mới.

Điểm quan trọng của bài học vẫn giữ nguyên: stack watermark và concurrent thread-stack processing là một phần của ZGC, không phải một chế độ GC riêng cần bật.

## 10. Chọn heap đủ headroom cho concurrent GC

ZGC thực hiện công việc đồng thời với ứng dụng, vì vậy heap phải đủ chỗ cho:

- Live set hiện tại.
- Object mới được cấp phát trong lúc GC đang chạy.
- Biến động allocation rate trong giờ cao điểm.
- Khoảng trống cần thiết để GC hoàn tất chu kỳ thu gom.

Nếu heap quá nhỏ so với live set và allocation rate, ứng dụng có thể phải chờ GC xử lý đủ bộ nhớ để tiếp tục cấp phát. Đây là vấn đề sizing và khả năng xử lý allocation, không phải lỗi riêng của thread-stack processing.

Cách tiếp cận:

1. Đo live set sau khi ứng dụng ổn định.
2. Đo allocation rate trong tải bình thường và tải đỉnh.
3. Đặt max heap đủ chứa live set cùng headroom.
4. Chạy workload đại diện và theo dõi GC cycle, pause, CPU.
5. Điều chỉnh heap sau khi có số liệu.

Oracle khuyến nghị chọn max heap đủ cho live set và headroom để allocation tiếp tục được phục vụ trong lúc GC chạy. Càng nhiều headroom thường càng giúp ZGC dễ theo kịp allocation, nhưng vẫn phải cân bằng với giới hạn bộ nhớ của máy.

## 11. CPU và số lượng concurrent GC threads

ZGC có thể tự chọn số concurrent GC threads dựa trên môi trường và workload. Tùy chọn **-XX:ConcGCThreads** điều chỉnh số thread GC chạy concurrent.

Không nên đặt số thread tùy ý ngay từ đầu:

- Quá nhiều thread GC có thể lấy CPU khỏi ứng dụng.
- Quá ít thread GC có thể khiến GC xử lý không kịp tốc độ cấp phát.
- CPU quota trong container có thể khiến hành vi khác với máy vật lý có cùng số core.
- Tải ứng dụng thay đổi theo thời gian, nên kết quả benchmark phải phản ánh cả giờ cao điểm.

Hãy bắt đầu bằng cấu hình tự động của JVM. Chỉ điều chỉnh số concurrent GC threads khi log và benchmark cho thấy CPU hoặc tốc độ thu gom là nút thắt.

## 12. Quan sát pause và safepoint

Có thể bật unified logging để ghi GC và safepoint:

~~~bash
java -XX:+UseZGC \
  -Xlog:gc*,safepoint=info \
  -jar application.jar
~~~

Khi đọc log, tập trung vào:

- Thời lượng các pause của ZGC.
- Thời gian safepoint.
- Thời lượng các pha concurrent.
- Tần suất và khoảng cách giữa các chu kỳ GC.
- Dấu hiệu ứng dụng phải chờ cấp phát vì GC chưa thu hồi kịp.
- CPU sử dụng bởi tiến trình trong và ngoài chu kỳ GC.

Không nên chỉ nhìn tổng thời gian GC. Với ứng dụng latency-sensitive, cần quan sát cả thời gian dừng, phân phối latency của request và throughput.

Có thể xem các flag JVM đang chạy bằng:

~~~bash
jcmd <pid> VM.flags
~~~

Và xem thông tin heap:

~~~bash
jcmd <pid> GC.heap_info
~~~

Các diagnostic command có thể khác giữa JVM vendor và phiên bản. Kiểm tra danh sách hỗ trợ trên runtime đang chạy nếu cần thêm dữ liệu.

## 13. Đánh giá tác động bằng workload thực tế

Để biết concurrent thread-stack processing có đem lại lợi ích cho ứng dụng hay không, cần đo trên workload đại diện.

Một quy trình benchmark có thể gồm:

1. Chọn kịch bản có số lượng thread gần với production.
2. Dùng cùng dữ liệu, allocation pattern và request mix.
3. Chạy đủ thời gian để JVM warm up và workload ổn định.
4. Ghi GC log và safepoint log.
5. Thu thập p50, p95, p99 và p99.9 latency.
6. Ghi throughput, CPU utilization và heap occupancy.
7. Lặp lại nhiều lần để tránh kết luận từ một lần chạy.
8. So sánh kết quả với SLA thực tế.

Nếu hệ thống có nhiều thread, có thể kiểm tra xu hướng pause khi số thread tăng trong môi trường thử nghiệm. Không cần tạo số lượng thread cực lớn trong production chỉ để tận dụng tính năng này.

Khi so sánh các bản JDK, giữ nguyên cấu hình heap, phần cứng, container quota, dữ liệu và workload càng nhiều càng tốt. JDK mới có thể chứa nhiều thay đổi khác ngoài JEP 376, nên không quy toàn bộ chênh lệch hiệu năng cho một cải tiến.

## 14. Giới hạn cần hiểu đúng

Concurrent thread-stack processing giải quyết một thành phần pause của ZGC. Nó không bảo đảm mọi thao tác trong JVM đều không dừng thread.

Các pause khác vẫn có thể tồn tại do checkpoint hoặc công việc runtime khác. Ngoài GC, latency của ứng dụng còn phụ thuộc:

- Scheduler và mức tranh chấp CPU.
- Lock contention và synchronization.
- I/O, network và database.
- JIT compilation và class loading.
- Stop-the-world work của các thành phần JVM khác.
- Tạm dừng của hệ điều hành hoặc môi trường ảo hóa.

Tài liệu ZGC hiện đại mô tả pause time ở mức dưới một millisecond trong điều kiện phù hợp, nhưng đây không phải cam kết rằng p99.9 latency của toàn bộ request luôn dưới một millisecond. Hãy đo end-to-end latency trên môi trường triển khai.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| ZGC không còn safepoint | ZGC vẫn có safepoint; cải tiến này chuyển thread-stack processing ra khỏi phần pause |
| Thread stack không còn cần quét | Stack vẫn chứa GC roots và vẫn phải được xử lý |
| Concurrent nghĩa là không tốn CPU | Công việc vẫn cần CPU, chỉ được phân phối concurrent |
| Có thể bật riêng JEP 376 bằng một flag | Đây là hành vi tích hợp trong ZGC từ Java 16 |
| Chỉ heap size quyết định pause | Root processing, thread stack và các công việc runtime khác cũng quan trọng |
| ZGC bảo đảm toàn bộ request latency dưới 1 ms | Tài liệu mô tả pause của GC; latency ứng dụng còn nhiều thành phần khác |
| Tăng số GC threads luôn làm latency tốt hơn | Quá nhiều GC threads có thể tranh CPU với ứng dụng |
| JDK 16 và JDK hiện đại có cùng mô hình generation của ZGC | ZGC đã chuyển sang generational-only từ JDK 24 |

## 16. Khi nào nên đánh giá ZGC?

ZGC đáng được benchmark khi ứng dụng có mục tiêu latency nghiêm ngặt và các pause GC đang ảnh hưởng rõ tới tail latency.

Các dấu hiệu nên điều tra:

- GC pause xuất hiện trong những request chậm nhất.
- Ứng dụng có nhiều thread hoạt động đồng thời.
- Workload có stack sâu hoặc nhiều frame đang hoạt động.
- Heap lớn và live set cao.
- G1 hoặc collector hiện tại không đạt mục tiêu latency dù đã được cấu hình hợp lý.

Nếu throughput là ưu tiên lớn nhất và pause hiện tại đã đáp ứng yêu cầu, ZGC có thể không phải lựa chọn tốt hơn. Quyết định cần dựa trên benchmark có cùng workload và giới hạn tài nguyên.

## 17. Checklist vận hành

- [ ] Đã xác định pause GC có ảnh hưởng tới p99/p99.9 latency hay không.
- [ ] Đã xác nhận ZGC được hỗ trợ trên runtime và nền tảng triển khai.
- [ ] Đã chọn ZGC bằng **-XX:+UseZGC** khi cần.
- [ ] Heap đủ chứa live set và headroom cho allocation trong lúc GC chạy.
- [ ] Đã bật log GC và safepoint trong môi trường kiểm thử.
- [ ] Đã theo dõi CPU và throughput khi GC chạy concurrent.
- [ ] Đã benchmark với số lượng thread gần với production.
- [ ] Đã kiểm tra plugin, native code và framework có ảnh hưởng đến stack walking nếu ứng dụng sử dụng.
- [ ] Đã đánh giá trên đúng phiên bản JDK dự kiến triển khai.
- [ ] Đã kiểm tra end-to-end latency thay vì chỉ dựa vào GC pause.

## 18. Kết luận

Java 16 cải tiến ZGC bằng cách chuyển xử lý thread stack ra khỏi safepoint. Cơ chế stack watermark đánh dấu frame đã xử lý và frame còn chờ, cho phép JVM xử lý phần sâu của stack theo cách lazy, cooperative, concurrent và incremental. Nhờ đó, phần pause do quét thread stack không còn tăng theo kích thước root set như trước.

Cải tiến này vẫn có ý nghĩa trong ZGC hiện đại và không cần cấu hình riêng. Để tận dụng đúng, hãy chọn ZGC khi workload cần latency thấp, cung cấp đủ heap headroom, theo dõi CPU và đo pause cùng latency thực tế. Concurrent processing giảm thời gian dừng ứng dụng, nhưng công việc GC vẫn cần tài nguyên và các thành phần khác của hệ thống vẫn có thể ảnh hưởng tới thời gian phản hồi.

## Tài liệu tham khảo

- [JEP 376: ZGC: Concurrent Thread-Stack Processing](https://openjdk.org/jeps/376)
- [The Z Garbage Collector — Java SE 16](https://docs.oracle.com/en/java/javase/16/gctuning/z-garbage-collector.html)
- [Significant Changes in JDK 16 Release — Oracle Migration Guide](https://docs.oracle.com/en/java/javase/16/migrate/significant-changes-jdk-release.html)
- [Concurrent Thread-stack Processing in the Z Garbage Collector — Inside Java](https://inside.java/2022/05/31/zgc-concurrent-thread-stack-processing/)
- [ZGC Concurrent Thread-Stack Processing — OpenJDK/Oracle technical presentation](https://cr.openjdk.org/~pliden/slides/ZGC-Joker-2021.pdf)
- [The Z Garbage Collector — Java SE 24](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html)
- [Available Collectors — Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/available-collectors.html)
- [Significant Changes in JDK 24 Release — Oracle Migration Guide](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)

