# Chuyển xử lý stack sang pha concurrent và tác động tới độ trễ

## 1. Bối cảnh: vì sao xử lý stack ảnh hưởng đến GC pause?

Garbage Collector (GC) phải xác định object nào còn được tham chiếu để giữ lại và object nào có thể thu hồi. Các tham chiếu trực tiếp từ thread đang chạy là một phần của tập gốc (GC roots). Một trong những nơi chứa tham chiếu đó là execution stack của từng Java thread.

Trên stack, mỗi frame của lời gọi method có thể chứa tham chiếu tới object, chẳng hạn biến local hoặc tham số. GC cần nhận diện các tham chiếu này để không thu hồi object mà chương trình vẫn còn sử dụng.

Trước Java 16, Z Garbage Collector (ZGC) xử lý việc quét thread stack trong các pha safepoint. Khi JVM vào safepoint, các Java thread phải dừng tại điểm an toàn để VM thực hiện công việc cần trạng thái thread nhất quán. Nếu ứng dụng có nhiều thread hoặc stack sâu, việc xử lý các tham chiếu trên stack có thể làm phần dừng này kéo dài hơn.

JEP 376, được đưa vào Java 16, thay đổi cách ZGC xử lý thread stack: chuyển phần lớn công việc này khỏi safepoint sang cách xử lý lazy, cooperative, concurrent và incremental. Nhờ đó, thời gian dừng ứng dụng của ZGC giảm phụ thuộc vào lượng công việc quét stack.

Bài học tập trung vào thay đổi của ZGC trong Java 16 và ý nghĩa của nó với các ứng dụng Java hiện đại. Đây là tối ưu nội bộ của GC; lập trình viên không cần tự quản lý stack watermark trong code ứng dụng.

Mục tiêu:

- Hiểu vì sao thread stack là một phần của GC roots.
- Phân biệt safepoint với concurrent phase.
- Giải thích thay đổi của JEP 376.
- Hiểu vai trò của stack watermark.
- Đánh giá tác động đến GC pause và tail latency.
- Biết cách bật ZGC, thu thập log và đo hiệu quả.
- Phân biệt đặc điểm Java 16 với trạng thái ZGC trong JDK hiện đại.

## 2. Thread stack chứa những tham chiếu nào?

Mỗi Java thread có execution stack riêng. Khi thread gọi method, JVM tạo một stack frame cho lời gọi đó. Theo trạng thái thực thi, frame và metadata liên quan giúp JVM xác định:

- Tham số của method.
- Biến local.
- Thông tin phục vụ thực thi bytecode.
- Dữ liệu điều khiển như địa chỉ quay về.

Một số biến local hoặc tham số là reference tới object trên heap. Những reference này có thể giữ object còn sống dù không có field nào khác trỏ tới object đó. Với code đã được JIT biên dịch, một số giá trị có thể nằm trong register thay vì một stack slot vật lý; JVM dùng thông tin frame/OopMap phù hợp để nhận diện các reference đang sống. Vì vậy, khi nói stack processing, ta đang nói đến việc HotSpot xử lý các reference gắn với execution stack của thread, không có nghĩa mọi biến local luôn nằm nguyên trong bộ nhớ stack.

Ví dụ:

~~~java
public final class OrderService {
    public void process() {
        Order order = new Order("A-100");
        validate(order);
    }

    private void validate(Order order) {
        // Trong khi method này còn hoạt động,
        // biến order có thể giữ reference tới object.
        System.out.println(order.id());
    }
}
~~~

Khi `process()` gọi `validate()`, stack có frame tương ứng với các method đang hoạt động. GC cần nhận biết reference tới `Order` còn được giữ trong trạng thái thực thi của thread để không thu hồi object quá sớm.

Điểm cần phân biệt:

- **Thread stack** là vùng thực thi riêng của thread, chứa stack frame và thông tin liên quan đến lời gọi method.
- **Java heap** là vùng lưu trữ object.
- **GC root** là điểm bắt đầu để GC lần theo reference tới các object còn sống.
- **Stack processing** trong bài này là việc JVM xử lý reference trên thread stack để phục vụ GC; không phải thao tác với class `java.util.Stack` hoặc cấu trúc stack do ứng dụng tự tạo.

Stack có thể sâu khi ứng dụng có nhiều tầng gọi method hoặc đệ quy. Nhiều thread và stack sâu làm tăng số frame mà GC cần xử lý. Đây là lý do công việc stack processing có thể ảnh hưởng tới pause nếu được thực hiện đồng bộ tại safepoint.

## 3. Safepoint và Stop-The-World

Safepoint là trạng thái phối hợp của JVM, tại đó các Java thread đã dừng ở vị trí an toàn để VM thực hiện một số thao tác cần trạng thái nhất quán. Một thao tác GC có thể có pha Stop-The-World (STW), nghĩa là ứng dụng tạm dừng trong khi VM thực hiện phần việc tương ứng.

Không phải mọi hoạt động GC đều là STW. ZGC thực hiện nhiều công việc tốn thời gian trong concurrent phase, nghĩa là GC thread làm việc đồng thời với Java application thread.

Có thể hình dung:

~~~text
Trước thay đổi ở Java 16:

Application threads:  chạy ---- DỪNG TẠI SAFEPOINT ---- chạy
ZGC:                              quét thread stacks

Sau JEP 376:

Application threads:  chạy -- safepoint ngắn -- chạy liên tục
ZGC:                                  xử lý stack concurrent
~~~

Sơ đồ chỉ minh họa vị trí của công việc stack processing. ZGC vẫn có các safepoint ngắn cho những pha điều phối cần thiết; JEP 376 không loại bỏ tất cả safepoint hoặc biến GC thành hoạt động hoàn toàn không dừng ứng dụng.

### Pause time và latency

- **GC pause time** là khoảng thời gian application thread bị dừng cho một pha GC STW.
- **Request latency** là thời gian một request của ứng dụng hoàn tất.
- **Tail latency** mô tả phần đuôi của phân phối latency, thường theo dõi các percentile như p95, p99 và p99.9.

GC pause có thể góp phần làm request chậm, đặc biệt khi request đang xử lý bị dừng hoặc nhiều request đồng thời phải chờ. Tuy nhiên, request latency còn chịu ảnh hưởng của CPU scheduling, lock contention, I/O, network và các thành phần khác.

Giảm pause là một cách giảm một nguồn gây tail latency; không đảm bảo mọi request đều nhanh hơn cùng một tỷ lệ.

## 4. Cách ZGC xử lý stack trước Java 16

Trước JEP 376, ZGC quét thread stack tại một pha safepoint. Các tham chiếu từ stack được xử lý trong lúc Java thread dừng.

Về mặt khái niệm:

1. ZGC yêu cầu JVM vào safepoint.
2. Java thread dừng tại điểm an toàn.
3. GC xử lý các tham chiếu cần thiết trên thread stack.
4. JVM tiếp tục các pha GC tiếp theo.
5. Java thread được tiếp tục thực thi sau khi safepoint kết thúc.

Cách làm này đơn giản về mặt đồng bộ hóa vì stack không thay đổi trong lúc thread dừng. Nhưng lượng công việc cần thực hiện tại safepoint có thể tăng khi số lượng thread hoặc số frame cần xử lý tăng.

Với ứng dụng có nhiều thread, stack sâu hoặc nhiều tham chiếu trên stack, thời gian xử lý roots có thể trở thành một thành phần đáng kể của pause.

Không nên suy ra rằng heap càng lớn thì stack pause càng dài. Đây là hai đại lượng khác nhau:

- Heap size và live set ảnh hưởng đến nhiều công việc GC khác.
- Số thread, stack depth và số frame cần xử lý ảnh hưởng đến công việc xử lý stack.
- JEP 376 nhắm tới việc loại bỏ xử lý thread stack khỏi safepoint của ZGC, giảm ảnh hưởng của root set từ stack lên pause.

## 5. JEP 376 thay đổi điều gì?

JEP 376 có tên **ZGC: Concurrent Thread-Stack Processing** và được phát hành trong Java 16.

Mục tiêu chính:

- Loại bỏ thread-stack processing khỏi các safepoint của ZGC.
- Làm cho stack processing có tính lazy, cooperative, concurrent và incremental.
- Loại bỏ các công việc xử lý per-thread roots khác khỏi safepoint của ZGC.
- Cung cấp cơ chế để các thành phần khác của HotSpot có thể xử lý stack theo nhu cầu.

Thay vì buộc GC quét toàn bộ stack trong một pha dừng ứng dụng, JVM theo dõi phần stack đã được xử lý và phần cần xử lý tiếp. Công việc được phân chia và thực hiện trong lúc ứng dụng tiếp tục chạy, theo các quy tắc đồng bộ an toàn.

Bốn đặc tính:

| Đặc tính | Ý nghĩa |
| --- | --- |
| Lazy | Chỉ xử lý phần stack khi cần, tránh bắt buộc quét toàn bộ cùng lúc. |
| Cooperative | Java thread và các thành phần VM phối hợp để duy trì trạng thái stack có thể xử lý an toàn. |
| Concurrent | Công việc stack processing có thể diễn ra đồng thời với ứng dụng. |
| Incremental | Stack được xử lý từng phần, thay vì dồn toàn bộ công việc vào một safepoint. |

Các đặc tính này phối hợp với nhau. Chúng cho phép ZGC chuyển khối lượng công việc xử lý stack ra khỏi pause và phân bổ nó trong thời gian ứng dụng đang chạy.

## 6. Stack watermark là gì?

Để xử lý stack đồng thời mà vẫn bảo đảm GC không bỏ sót reference, JVM cần biết phần nào của stack đã được xử lý và phần nào chưa.

JEP 376 sử dụng cơ chế stack watermark. Có thể hiểu watermark là một mốc theo dõi ranh giới giữa các frame đã được xử lý và phần stack còn cần xử lý.

Khi GC hoặc một thành phần HotSpot cần đọc reference ở một frame, JVM bảo đảm frame đó đã được xử lý theo trạng thái watermark trước khi reference được sử dụng cho mục đích tương ứng.

Ý tưởng tổng quát:

~~~text
Thread stack

+-----------------------------+
| Frame đang hoạt động        |
+-----------------------------+
| Frame đã xử lý              |
+-----------------------------+
| Frame đã xử lý              |
+=============================+  <- Stack watermark
| Frame chưa xử lý            |
+-----------------------------+
| Frame chưa xử lý            |
+-----------------------------+
~~~

Hình vẽ mang tính khái niệm; vị trí watermark và cách frame được xử lý do JVM quản lý.

Stack watermark giúp:

- Theo dõi tiến độ xử lý stack của từng thread.
- Cho phép xử lý từng phần.
- Phối hợp truy cập stack từ GC thread và Java thread.
- Bảo đảm stack walker không đọc reference ở frame chưa được xử lý theo yêu cầu của cơ chế.

Đây là chi tiết triển khai của HotSpot. Ứng dụng Java không cần gọi API hoặc tự đặt watermark.

## 7. Lazy và incremental processing diễn ra như thế nào?

Với cách xử lý cũ, GC quét stack trong một khoảng dừng. Với cách mới, JVM có thể khởi tạo xử lý sau một pha phối hợp ngắn, rồi tiếp tục xử lý các frame trong quá trình ứng dụng chạy.

Ở mức khái niệm:

1. GC chuyển pha và đánh dấu trạng thái stack cần được xử lý.
2. Khi Java thread tiếp tục chạy, JVM nhận biết trạng thái xử lý đã thay đổi.
3. JVM thực hiện phần xử lý ban đầu cần thiết để bảo đảm các frame đang hoạt động được an toàn.
4. Các frame còn lại có thể được xử lý dần khi thread chạy hoặc khi GC/HotSpot cần đọc sâu hơn.
5. Stack watermark được cập nhật để ghi nhận tiến độ.

Cách làm này tránh việc dồn toàn bộ stack processing vào một pause dài. Phần công việc được phân bổ ra nhiều thời điểm hơn.

### Vì sao cần xử lý ban đầu?

Ngay sau khi một thread rời safepoint, các frame đang hoạt động có thể thay đổi khi method gọi hoặc trả về. JVM cần bảo đảm một vùng đầu stack luôn ở trạng thái an toàn trước khi cho phép các thao tác tiếp theo.

Cơ chế watermark và các kiểm tra liên quan đến việc gọi/trả method giúp duy trì bất biến này. Chi tiết triển khai có thể khác nhau giữa interpreter, compiled code và nền tảng CPU; đó là công việc của JVM, không phải logic mà ứng dụng cần tự cài đặt.

## 8. Cooperative và concurrent processing

Stack thuộc về từng thread, nên việc xử lý đồng thời cần phối hợp giữa thread sở hữu stack và các thread VM cần đọc stack.

JEP 376 cung cấp cơ chế để GC và các thành phần HotSpot truy cập stack theo cách an toàn. Các thao tác đọc stack cần bảo đảm frame đã ở trạng thái được xử lý phù hợp; JVM dùng đồng bộ hóa nội bộ và cơ chế phối hợp theo thread để tránh race condition.

Có thể hiểu sự phân công như sau:

- Java thread tiếp tục thực hiện chương trình.
- GC thread xử lý các phần stack cần thiết trong pha concurrent.
- JVM duy trì watermark để biết phần stack đã sẵn sàng.
- Khi một thành phần cần đọc frame, JVM bảo đảm frame được xử lý trước khi sử dụng các reference của nó.

Concurrent không có nghĩa GC đọc stack tùy ý trong khi thread thay đổi stack. Sự phối hợp và các quy tắc đồng bộ của HotSpot là điều kiện để cơ chế hoạt động đúng.

## 9. Tác động tới GC pause

Lợi ích trực tiếp của JEP 376 là loại bỏ công việc quét thread stack khỏi safepoint của ZGC. Do đó:

- Pause không còn phải gánh toàn bộ thời gian quét stack.
- Pause của ZGC ít phụ thuộc hơn vào số lượng frame và root reference trên thread stack.
- Ứng dụng có nhiều thread hoặc stack sâu có thể giảm một nguồn gây pause dài.
- Thời gian dừng có tính ổn định hơn đối với workload có root set lớn từ stack.

JEP 376 không làm mọi pha GC trở thành concurrent. ZGC vẫn cần các synchronization point ngắn để bắt đầu/kết thúc một số pha và bảo đảm trạng thái nhất quán.

Nó cũng không bảo đảm pause luôn bằng 0 hoặc mọi pause đều dưới một con số cố định. Pause thực tế phụ thuộc JDK, phần cứng, workload, các thao tác VM khác và cấu hình hệ thống.

## 10. Tác động tới latency của ứng dụng

Với ứng dụng nhạy cảm về độ trễ, một pause ngắn hơn có thể giảm thời gian request bị gián đoạn. Lợi ích có thể thấy rõ ở tail latency, nhất là khi pause trước đó trùng với thời điểm tải cao hoặc request quan trọng đang chạy.

Ví dụ một dịch vụ API có nhiều request đồng thời:

~~~text
Trước:
Request A: ===== xử lý ===== [GC pause dài] ===== hoàn tất
Request B: === xử lý ===     [GC pause dài] ===== hoàn tất
Request C: ======== xử lý ===[GC pause dài] == hoàn tất

Sau:
Request A: ===== xử lý ===== [pause ngắn] === hoàn tất
Request B: === xử lý ===     [pause ngắn] == hoàn tất
Request C: ======== xử lý ===[pause ngắn] == hoàn tất
ZGC:                       stack processing concurrent
~~~

Sơ đồ chỉ minh họa ảnh hưởng của pause; không phải lịch thực thi cố định của JVM.

Những ứng dụng có thể quan tâm:

- API server có yêu cầu p99 hoặc p99.9 latency.
- Hệ thống giao dịch có nhiều thread hoạt động đồng thời.
- Ứng dụng duy trì nhiều thread có stack sâu.
- Dịch vụ có live workload lớn và cần GC pause ngắn.

Tuy nhiên, giảm GC pause không đồng nghĩa throughput chắc chắn tăng. Công việc được chuyển sang pha concurrent vẫn tiêu thụ CPU. Nếu CPU đã bão hòa, phần công việc concurrent có thể cạnh tranh tài nguyên với application thread và làm latency tăng ở nơi khác.

## 11. Đánh đổi: pause ngắn hơn nhưng vẫn cần tài nguyên concurrent

Khi chuyển stack processing ra khỏi safepoint, JVM phân bổ công việc vào thời gian ứng dụng chạy. Vì vậy, cần đánh giá cả pause lẫn chi phí concurrent.

Các yếu tố cần theo dõi:

- CPU sử dụng bởi GC thread.
- CPU còn lại cho application thread.
- Allocation rate của ứng dụng.
- Live set và dung lượng heap.
- Số thread và độ sâu stack.
- Thời gian các pha concurrent.
- Request throughput và latency percentiles.

Nếu ứng dụng tạo object nhanh hơn khả năng GC xử lý, hoặc CPU không đủ để chạy ứng dụng và GC đồng thời, ZGC có thể chịu áp lực về thời gian thu hồi. Việc giảm pause nhờ concurrent processing không loại bỏ nhu cầu cấp đủ CPU và heap headroom.

Không nên tăng số GC thread hoặc thay đổi heap chỉ dựa vào một lần quan sát. Trước tiên thu thập log, xác định bottleneck và đo lại với workload đại diện.

## 12. Bật ZGC để kiểm tra trên Java 16

Trong Java 16, ZGC đã là collector production. Có thể bật bằng:

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

Để thu thập GC và safepoint log:

~~~bash
java \
    -XX:+UseZGC \
    -Xlog:gc*,safepoint \
    -jar app.jar
~~~

Các log này giúp quan sát:

- Thời điểm các pha GC diễn ra.
- Pha nào là pause và pha nào là concurrent.
- Thời lượng pause.
- Safepoint xảy ra ngoài GC.
- Tần suất và thời lượng các chu kỳ GC.

Không cần một JVM flag riêng để bật JEP 376. Đây là thay đổi triển khai của ZGC trong Java 16, được sử dụng khi bật ZGC trên phiên bản đó.

### Lưu ý khi áp dụng trên JDK hiện đại

ZGC đã tiếp tục phát triển sau Java 16. Generational ZGC được giới thiệu ở JDK 21; trở thành mặc định từ JDK 23 và từ JDK 24 chỉ còn Generational ZGC, tùy chọn chuyển về non-generational đã bị loại bỏ.

Trên JDK hiện đại, dùng:

~~~bash
java -XX:+UseZGC -jar app.jar
~~~

Không sao chép các cờ chuyển đổi non-generational từ tài liệu JDK cũ vào cấu hình mới. Cơ chế concurrent thread-stack processing từ Java 16 vẫn là một phần của tiến trình phát triển ZGC; các thay đổi về generation là một bước tiến khác.

## 13. Đọc GC log và safepoint log

Có thể bật unified logging:

~~~bash
java \
    -XX:+UseZGC \
    -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags \
    -jar app.jar
~~~

Khi phân tích:

1. Tìm các dòng bắt đầu/kết thúc pha GC.
2. Nhận diện các pha có tiền tố hoặc nội dung biểu thị pause.
3. Ghi lại thời lượng của từng pause.
4. Đối chiếu thời điểm pause với safepoint log.
5. So sánh thời gian pause với các pha concurrent.
6. Xác định có safepoint dài không liên quan đến GC hay không.

Tên và mức chi tiết của log có thể khác nhau theo JDK. Không nên chỉ tìm một chuỗi cố định từ một bản JDK rồi giả định mọi bản đều xuất cùng định dạng.

Ví dụ, log có thể giúp phân biệt thời gian GC đang chạy concurrent với thời gian application thread bị dừng. Đây là khác biệt quan trọng khi phân tích latency.

## 14. Đo tác động bằng workload thực tế

Muốn biết thay đổi này có cải thiện hệ thống hay không, hãy đo ứng dụng dưới workload gần production.

Các chỉ số nên thu thập:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| GC pause p50/p95/p99/max | Pause điển hình và pause xấu nhất thay đổi thế nào? |
| Request latency p50/p95/p99/p99.9 | Người dùng có nhận thấy tail latency giảm không? |
| Throughput | Số request hoặc công việc hoàn tất mỗi giây có thay đổi không? |
| GC CPU time | Công việc concurrent tiêu thụ thêm bao nhiêu CPU? |
| Application CPU | CPU còn lại cho ứng dụng có đủ không? |
| Allocation rate | Ứng dụng tạo object nhanh đến mức nào? |
| Heap occupancy/live set | Heap có đủ headroom để GC xử lý concurrent không? |
| Safepoint duration | Có pause khác ngoài stack processing đang chi phối không? |

### Quy trình benchmark

1. Chọn workload có tốc độ request, concurrency và dữ liệu đại diện.
2. Ghi lại JDK vendor/version, collector, heap, CPU và cấu hình máy.
3. Warm up ứng dụng trước khi lấy số liệu.
4. Chạy đủ lâu để quan sát nhiều chu kỳ GC.
5. Ghi GC log, safepoint log và request latency histogram.
6. Lặp lại nhiều lần trong điều kiện tương đương.
7. So sánh percentile và CPU usage, không chỉ so sánh giá trị trung bình.
8. Kiểm tra cả throughput và latency để nhận diện đánh đổi.

Nếu so sánh Java 15 với Java 16 để quan sát thay đổi của JEP 376, giữ workload và phần cứng tương đương. Tuy nhiên, một bản JDK mới có thể chứa nhiều thay đổi khác; không quy mọi khác biệt hiệu năng cho riêng JEP 376 nếu chưa cô lập được yếu tố đó.

## 15. Dùng JFR để bổ sung dữ liệu

Java Flight Recorder (JFR) có thể thu thập dữ liệu về GC, safepoint, thread và hoạt động JVM trong một khoảng thời gian.

Có thể bắt đầu một recording bằng `jcmd`:

~~~bash
jcmd <pid> JFR.start name=gc-latency settings=profile duration=5m filename=gc-latency.jfr
~~~

Thay `<pid>` bằng process ID của JVM cần theo dõi.

Sau khi recording hoàn tất, mở file JFR bằng Java Mission Control hoặc công cụ phân tích JFR phù hợp. Đối chiếu:

- GC phases và pause.
- Safepoint events.
- CPU load và thread activity.
- Allocation và heap behavior.
- Khoảng thời gian request latency tăng.

JFR bổ sung góc nhìn về hoạt động JVM; nó không thay thế metric latency của ứng dụng. Nên kết hợp GC log, JFR và histogram từ hệ thống request để hiểu tác động thực tế.

## 16. Phân biệt thay đổi này với các GC khác

JEP 376 là thay đổi trong ZGC. Không áp dụng kết luận này cho mọi garbage collector.

| Collector | Đặc điểm tổng quát | Phạm vi của JEP 376 |
| --- | --- | --- |
| ZGC | Collector low-latency, thực hiện nhiều công việc GC concurrent. | JEP 376 thay đổi cách ZGC xử lý thread stack. |
| G1 | Mostly concurrent, có các pha collection STW. | Không phải cơ chế stack watermark của JEP 376. |
| Parallel GC | Ưu tiên throughput, nhiều công việc GC thực hiện trong STW. | Không áp dụng thay đổi của ZGC. |
| Serial GC | Collector đơn luồng, phù hợp workload nhỏ hoặc môi trường hạn chế. | Không áp dụng thay đổi của ZGC. |

Chọn collector dựa trên yêu cầu latency, throughput, footprint, heap và đặc điểm workload. Không chuyển sang ZGC chỉ vì một tính năng của ZGC giảm pause; cần đo trên ứng dụng thực tế.

## 17. Các giới hạn cần nhớ

- JEP 376 không loại bỏ tất cả safepoint của JVM.
- Nó không làm mọi pha GC trở thành concurrent.
- Stack watermark không phải API dành cho ứng dụng.
- ZGC vẫn tiêu thụ CPU cho concurrent work.
- Request latency còn phụ thuộc lock, I/O, scheduler, network và code ứng dụng.
- Kết quả benchmark phụ thuộc workload, số thread, stack depth, CPU và heap.
- ZGC không nhất thiết là lựa chọn tốt nhất cho mọi ứng dụng.
- Trên JDK hiện đại, cần dùng tài liệu đúng phiên bản vì ZGC đã có thêm Generational ZGC và nhiều thay đổi khác sau Java 16.

## 18. Lỗi thường gặp và cách khắc phục

1. **Nghĩ stack là `java.util.Stack`:** JEP 376 nói về execution stack của Java thread và các frame chứa object reference.
2. **Cho rằng stack processing là quét heap:** stack processing tìm GC roots trên thread stack; quét object graph trên heap là công việc khác.
3. **Nói ZGC không còn safepoint:** JEP 376 chuyển stack processing ra khỏi safepoint, không loại bỏ mọi safepoint.
4. **Cho rằng pause bằng 0:** ZGC vẫn có các synchronization point và công việc STW khác.
5. **Đánh đồng GC pause với request latency:** pause là một yếu tố có thể làm request chậm; cần đo cả latency của ứng dụng.
6. **Chỉ nhìn pause trung bình:** theo dõi p95, p99, p99.9 và max để hiểu tail latency.
7. **Bỏ qua CPU của concurrent GC:** công việc concurrent có thể cạnh tranh CPU với ứng dụng.
8. **Cho rằng JEP 376 áp dụng cho G1 hoặc Parallel GC:** đây là thay đổi của ZGC.
9. **Dùng cờ ZGC cũ trên JDK hiện đại:** từ JDK 24, ZGC chỉ còn generational và cờ chuyển chế độ cũ đã bị loại bỏ.
10. **Tăng GC thread ngay khi thấy pause:** thu thập số liệu và xác định bottleneck trước khi tuning.
11. **So sánh hai JDK với workload khác nhau:** giữ concurrency, allocation rate, heap và phần cứng tương đương.
12. **Kết luận chỉ từ một lần benchmark:** lặp lại và kiểm tra độ ổn định của phân phối latency.

## 19. Bài tập thực hành

1. Giải thích vì sao thread stack chứa GC roots.
2. Vẽ sơ đồ một stack frame giữ reference tới object trên heap.
3. Mô tả cách ZGC xử lý thread stack trước Java 16.
4. Trình bày bốn đặc tính lazy, cooperative, concurrent và incremental trong JEP 376.
5. Giải thích vai trò của stack watermark.
6. Phân biệt safepoint, Stop-The-World và concurrent phase.
7. Chạy ứng dụng Java 16 với `-XX:+UseZGC`.
8. Bật `-Xlog:gc*,safepoint` và xác định các pha pause/concurrent.
9. Đo pause time p50/p95/p99/max dưới workload có nhiều thread.
10. Đo request latency p99 và p99.9 trước/sau khi thay JDK.
11. Thu thập JFR và đối chiếu GC phase với safepoint.
12. Phân tích một workload CPU-bound để xem concurrent GC ảnh hưởng throughput thế nào.
13. Giải thích vì sao kết quả giảm pause không bảo đảm request latency giảm cùng tỷ lệ.
14. Nêu khác biệt giữa ZGC trong Java 16 và Generational ZGC trong JDK hiện đại.
15. Viết báo cáo benchmark gồm JDK version, GC, heap, thread count, allocation rate, GC pause, CPU và request latency.

## Ghi nhớ

JEP 376 đưa concurrent thread-stack processing vào ZGC từ Java 16. Thread stack chứa các reference có thể giữ object trên heap sống, vì vậy GC phải xử lý chúng như một phần của root set. Trước thay đổi này, ZGC quét thread stack tại safepoint; sau thay đổi, HotSpot dùng cơ chế lazy, cooperative, concurrent và incremental cùng stack watermark để xử lý stack an toàn trong lúc ứng dụng tiếp tục chạy. Điều này loại bỏ một phần công việc khỏi GC pause và giảm sự phụ thuộc của pause vào root set từ thread stack. ZGC vẫn có safepoint và vẫn tiêu thụ CPU cho concurrent work. Hãy đánh giá hiệu quả bằng GC/safepoint log, JFR, throughput và request latency percentiles trên workload thực tế. Kiến thức stack processing vẫn áp dụng cho ZGC hiện đại; từ JDK 24, ZGC là generational và không còn tùy chọn quay lại non-generational.

**Tài liệu tham khảo chính thức:**

- [JEP 376 – ZGC: Concurrent Thread-Stack Processing](https://openjdk.org/jeps/376)
- [JEP 377 – ZGC: Production Ready](https://openjdk.org/jeps/377)
- [JEP 439 – Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 474 – ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
- [JEP 490 – ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490)
- [Oracle Java 26 – The Z Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/z-garbage-collector.html)
- [Oracle Java 16 – The java Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html)
- [Oracle presentation – Concurrent Thread-Stack Processing in ZGC](https://cr.openjdk.org/~pliden/slides/ZGC-Joker-2021.pdf)
