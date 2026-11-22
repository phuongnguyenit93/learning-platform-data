# Công cụ thời điểm chạy trong JDK

Các công cụ thời điểm chạy (runtime tools) giúp quan sát một JVM đang hoạt động: tiến trình đang chạy lớp nào, luồng đang chờ ở đâu, heap và bộ thu gom rác (GC) biến động ra sao, hoặc thời gian thực thi đang tập trung ở đoạn mã nào. Đây là nhóm công cụ quan trọng khi ứng dụng đã chạy nhưng xuất hiện lỗi chậm, treo, tăng bộ nhớ hoặc hoạt động khác với dự kiến.

Phần lớn công cụ dòng lệnh nằm trong thư mục **bin** của JDK. Chúng thường kết nối tới JVM cục bộ thông qua cơ chế Attach. Với hầu hết tình huống chẩn đoán, hãy bắt đầu bằng **jcmd**; sau đó chọn công cụ chuyên biệt theo loại dữ liệu cần quan sát.

## 1. Chọn công cụ theo mục tiêu

| Nhu cầu | Công cụ nên bắt đầu | Dữ liệu thu được |
|---|---|---|
| Tìm tiến trình Java | **jcmd -l** hoặc **jps** | PID, lớp chính hoặc JAR đang chạy |
| Xem cấu hình JVM | **jcmd** với **VM.flags** và **VM.command_line** | Cờ JVM và dòng lệnh khởi chạy |
| Điều tra luồng bị treo | **jcmd** với **Thread.print** hoặc **jstack** | Trạng thái luồng, stack trace, khóa đang giữ hoặc chờ |
| Theo dõi GC | **jstat** | Bộ đếm và mức sử dụng các vùng heap qua nhiều lần lấy mẫu |
| Kiểm tra heap | **jcmd** với **GC.heap_info** hoặc **GC.class_histogram** | Thông tin heap và số lượng đối tượng theo lớp |
| Phân tích bộ nhớ sâu | **jcmd GC.heap_dump** hoặc **jmap** | Tệp heap dump để phân tích ngoại tuyến |
| Phân tích hiệu năng theo thời gian | JDK Flight Recorder (JFR) và lệnh **jfr** | Sự kiện GC, luồng, cấp phát, lấy mẫu CPU và các sự kiện JVM |
| Quan sát qua giao diện | **jconsole** | Biểu đồ và các MBean qua JMX |
| Phân tích cấp thấp | **jhsdb** | Dữ liệu Serviceability Agent từ tiến trình hoặc core dump |

Không cần chạy tất cả công cụ cùng lúc. Hãy xác định câu hỏi cần trả lời trước, lấy dữ liệu ít ảnh hưởng nhất, rồi mới chuyển sang thao tác nặng hơn như heap dump.

## 2. Tìm đúng tiến trình JVM

Trước khi gửi lệnh chẩn đoán, cần xác định chính xác PID của ứng dụng. Hai lệnh thường dùng là:

~~~bash
jcmd -l
jps -lmv
~~~

- **jcmd -l** liệt kê các JVM cục bộ mà công cụ có thể nhận diện, thường kèm PID và lớp chính.
- **jps** liệt kê các JVM được công cụ phát hiện. Tùy chọn **-l** hiển thị tên lớp hoặc đường dẫn JAR đầy đủ hơn, **-m** hiển thị tham số truyền cho phương thức main, còn **-v** hiển thị tham số JVM.

Ví dụ, kết quả có thể chứa một dòng dạng:

~~~text
18420 com.example.orders.OrderApplication
~~~

Trong ví dụ này, **18420** là PID cần dùng cho các lệnh tiếp theo. PID thay đổi theo mỗi lần khởi chạy, vì vậy không sao chép PID từ một lần chạy cũ. Nếu máy có nhiều ứng dụng Java, hãy đối chiếu cả tên lớp, JAR và tham số khởi chạy để tránh tác động nhầm tiến trình.

## 3. jcmd — điểm bắt đầu cho chẩn đoán JVM

**jcmd** gửi các lệnh chẩn đoán tới một JVM đang chạy. Danh sách lệnh phụ thuộc phiên bản JVM và môi trường, vì vậy nên hỏi chính tiến trình đích trước:

~~~bash
jcmd <pid> help
jcmd <pid> help Thread.print
~~~

Một số lệnh thường hữu ích:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
~~~

Ý nghĩa:

- **VM.version** cho biết phiên bản VM đang chạy.
- **VM.command_line** hiển thị dòng lệnh khởi chạy JVM.
- **VM.flags** hiển thị các cờ VM hiện tại, hữu ích khi kiểm tra heap size, GC hoặc các tùy chọn runtime.
- **VM.system_properties** hiển thị system properties. Kết quả có thể chứa đường dẫn nội bộ hoặc thông tin nhạy cảm; hãy kiểm tra trước khi chia sẻ log.
- **Thread.print** in stack trace của các luồng Java, kèm trạng thái như RUNNABLE, BLOCKED, WAITING hoặc TIMED_WAITING.
- **GC.heap_info** cung cấp thông tin tổng quan về heap và các vùng bộ nhớ do GC quản lý.

Để xem thêm thông tin về các khóa đồng bộ, có thể dùng:

~~~bash
jcmd <pid> Thread.print -l
~~~

Để xem số lượng và tổng dung lượng đối tượng theo lớp:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Histogram giúp nhận ra lớp nào đang chiếm nhiều đối tượng hoặc bộ nhớ. Tuy nhiên, thao tác này có thể ảnh hưởng đáng kể tới ứng dụng, tùy kích thước heap và trạng thái JVM.

Khi thật sự cần snapshot heap, có thể yêu cầu JVM tạo heap dump:

~~~bash
jcmd <pid> GC.heap_dump /absolute/path/heap.hprof
~~~

Tệp **.hprof** có thể rất lớn. Việc tạo dump có thể gây pause và tiêu tốn dung lượng đĩa; cần kiểm tra nơi lưu còn đủ chỗ và bảo vệ tệp vì nó có thể chứa dữ liệu đang được ứng dụng giữ trong bộ nhớ.

Một trường hợp đặc biệt là bộ nhớ native. Lệnh sau chỉ cung cấp dữ liệu khi Native Memory Tracking (NMT) đã được bật từ lúc JVM khởi chạy:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Có thể bật NMT khi khởi chạy JVM bằng cờ như **-XX:NativeMemoryTracking=summary** hoặc **-XX:NativeMemoryTracking=detail**. Không thể bật tính năng này hồi tố cho một JVM đã chạy mà chưa khởi động với NMT.

## 4. jstat — theo dõi GC bằng các mẫu liên tiếp

**jstat** đọc các bộ đếm và chỉ số của JVM theo chu kỳ. Ví dụ:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

Lệnh lấy mẫu mỗi 1.000 mili giây và thực hiện 10 lần. Tùy chọn **-gcutil** hiển thị tỷ lệ sử dụng của các vùng heap cùng một số bộ đếm GC. Có thể dùng **-gc** để xem các giá trị dung lượng thay vì tỷ lệ phần trăm:

~~~bash
jstat -gc <pid> 1000 10
~~~

Các cột thường gặp gồm:

- **S0, S1**: mức sử dụng các vùng Survivor.
- **E**: mức sử dụng Eden.
- **O**: mức sử dụng Old Generation.
- **M**: mức sử dụng Metaspace.
- **YGC, YGCT**: số lần và tổng thời gian Young GC.
- **FGC, FGCT**: số lần và tổng thời gian Full GC.
- **GCT**: tổng thời gian GC được thống kê.

Tên cột và cách hiển thị có thể khác theo phiên bản JDK hoặc bộ thu gom rác. Hãy dùng phần tiêu đề do chính lệnh trả về để diễn giải kết quả.

Một mẫu đơn lẻ hiếm khi đủ để kết luận. Hãy quan sát xu hướng: Old Generation có tăng liên tục không, GC có diễn ra dày hơn không, tổng thời gian GC có tăng nhanh không, và heap có phục hồi sau GC không. Ví dụ, Old Generation tăng qua nhiều mẫu và không giảm sau các chu kỳ GC có thể là dấu hiệu cần kiểm tra đối tượng được giữ tham chiếu lâu dài. Nó chưa tự chứng minh có memory leak; cần kết hợp histogram, heap dump hoặc JFR.

## 5. jstack, jmap và jinfo

Đây là các công cụ chẩn đoán quen thuộc trong JDK. Nhiều tác vụ hiện có thể thực hiện bằng **jcmd**, nhưng vẫn nên biết cách đọc lệnh cũ khi gặp tài liệu hoặc quy trình vận hành đang sử dụng chúng.

### jstack — lấy thread dump

~~~bash
jstack -l <pid>
~~~

**jstack** in stack trace của các luồng trong JVM. Tùy chọn **-l** bổ sung thông tin về các khóa đồng bộ. Thread dump hữu ích khi:

- Nhiều luồng ở trạng thái BLOCKED và cùng chờ một monitor.
- Một luồng ở trạng thái WAITING hoặc TIMED_WAITING trong thời gian dài.
- Luồng xử lý yêu cầu liên tục xuất hiện ở cùng một đoạn stack.
- Cần kiểm tra dấu hiệu deadlock.

Với JDK hiện đại, có thể bắt đầu bằng **jcmd <pid> Thread.print -l**. Khi nghi ngờ ứng dụng bị treo, hãy lấy nhiều thread dump cách nhau vài giây. So sánh các snapshot giúp phân biệt luồng chỉ đang chờ bình thường với luồng bị mắc kẹt ở cùng một vị trí.

### jmap — xem histogram hoặc tạo heap dump

~~~bash
jmap -histo:live <pid>
jmap -dump:live,format=b,file=heap.hprof <pid>
~~~

**-histo:live** liệt kê các lớp và số lượng đối tượng còn sống sau khi JVM xác định các đối tượng có thể thu hồi. Tùy chọn **-dump** tạo heap dump định dạng nhị phân để phân tích bằng công cụ đọc heap dump.

Các thao tác này có thể gây GC hoặc pause đáng kể, đặc biệt với heap lớn. Trong quy trình mới, ưu tiên xem lệnh tương ứng qua **jcmd** và chỉ tạo heap dump khi đã có kế hoạch về dung lượng đĩa, thời gian thực hiện và nơi lưu tệp.

### jinfo — xem cờ và system properties

~~~bash
jinfo -flags <pid>
jinfo -sysprops <pid>
~~~

**jinfo** hiển thị cờ JVM và system properties của tiến trình. Nếu chỉ cần đọc thông tin, các lệnh **jcmd <pid> VM.flags** và **jcmd <pid> VM.system_properties** thường thuận tiện hơn. Một số tùy chọn của **jinfo** có thể thay đổi cờ runtime; không dùng lệnh thay đổi khi mục tiêu chỉ là quan sát.

## 6. Java Flight Recorder và lệnh jfr

Java Flight Recorder (JFR) ghi lại các sự kiện của JVM theo thời gian, chẳng hạn lấy mẫu thực thi, GC, hoạt động của luồng, cấp phát bộ nhớ và các sự kiện runtime khác. JFR đặc biệt hữu ích khi cần tìm nguyên nhân của vấn đề hiệu năng thay vì chỉ xem trạng thái tại một thời điểm.

Có thể bắt đầu một recording ngắn bằng **jcmd**:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=60s filename=runtime.jfr
~~~

Lệnh trên yêu cầu JVM ghi trong 60 giây rồi lưu kết quả vào **runtime.jfr**. **settings=profile** thu thập dữ liệu chi tiết hơn, phù hợp cho một khoảng điều tra ngắn. Với recording dài hơn, cân nhắc cấu hình **default** để giảm lượng dữ liệu và tác động.

Có thể kiểm tra recording đang chạy:

~~~bash
jcmd <pid> JFR.check
~~~

Nếu recording được khởi động mà chưa đặt thời lượng, có thể chủ động xuất hoặc dừng:

~~~bash
jcmd <pid> JFR.dump name=incident filename=runtime.jfr
jcmd <pid> JFR.stop name=incident
~~~

Sau khi có tệp, dùng công cụ **jfr** để phân tích ngoại tuyến:

~~~bash
jfr summary runtime.jfr
jfr print --events jdk.ThreadSleep,jdk.GarbageCollection runtime.jfr
~~~

**jfr summary** tóm tắt recording và các loại sự kiện. **jfr print** in dữ liệu sự kiện; bộ lọc **--events** giúp giới hạn kết quả vào những sự kiện cần kiểm tra. Với recording lớn, nên lọc sự kiện hoặc chuyển kết quả ra tệp để dễ phân tích.

JFR giúp nhìn thấy diễn biến theo thời gian. Ví dụ, sự kiện GC cho biết thời điểm và thời lượng các lần thu gom; sự kiện lấy mẫu thực thi giúp nhận diện stack thường xuất hiện khi CPU bận. Kết quả cần được đối chiếu với thời điểm người dùng báo lỗi, tải hệ thống và log ứng dụng. Tệp JFR cũng có thể chứa tên lớp, stack trace, đường dẫn hoặc thông tin môi trường; hãy lưu trữ và chia sẻ có kiểm soát.

## 7. jconsole — quan sát JVM qua JMX

**jconsole** là công cụ giao diện đồ họa sử dụng Java Management Extensions (JMX). Nó có thể hiển thị:

- Tổng quan JVM, thời gian hoạt động và mức sử dụng bộ nhớ.
- Biểu đồ heap và hoạt động GC.
- Danh sách luồng và thông tin luồng.
- Số lượng lớp đã nạp.
- Các MBean do JVM hoặc ứng dụng cung cấp.

Chạy lệnh sau để mở giao diện:

~~~bash
jconsole
~~~

Có thể kết nối tới tiến trình Java cục bộ mà công cụ phát hiện được. Với tiến trình từ xa, cần cấu hình JMX trên ứng dụng đích. Kết nối từ xa phải có xác thực và bảo vệ đường truyền phù hợp; không mở cổng JMX không xác thực ra mạng công cộng. JConsole thuận tiện để quan sát trực quan, còn **jcmd** và JFR phù hợp hơn khi cần thu thập dữ liệu dòng lệnh có thể lưu lại và so sánh.

## 8. jhsdb — phân tích cấp thấp

**jhsdb** là công cụ Serviceability Agent dành cho các tình huống điều tra sâu, chẳng hạn phân tích core dump hoặc cấu trúc nội bộ của JVM. Một số chế độ có thể lấy stack hoặc thông tin heap:

~~~bash
jhsdb jstack --pid <pid>
jhsdb jmap --heap --pid <pid>
~~~

Đây không phải lựa chọn đầu tiên cho chẩn đoán thông thường. Việc attach Serviceability Agent vào JVM đang chạy có thể làm tiến trình bị dừng trong lúc phân tích và gây ảnh hưởng rõ rệt tới ứng dụng. Chỉ dùng khi các công cụ cấp cao hơn chưa trả lời được câu hỏi, đã hiểu tác động và có quyền thao tác với tiến trình.

## 9. Quy trình điều tra theo triệu chứng

### Ứng dụng phản hồi chậm hoặc có dấu hiệu treo

1. Dùng **jcmd -l** hoặc **jps -lmv** để xác định đúng PID.
2. Lấy thread dump bằng **jcmd <pid> Thread.print -l**.
3. Lặp lại sau vài giây và so sánh các stack. Tìm luồng BLOCKED, monitor owner, deadlock hoặc nhóm luồng RUNNABLE liên tục nằm ở cùng đoạn mã.
4. Nếu vấn đề liên quan CPU, ghi JFR trong khoảng thời gian có hiện tượng và xem các sự kiện lấy mẫu thực thi.

Một luồng WAITING không nhất thiết là lỗi: luồng worker trong thread pool thường chờ công việc khi hệ thống rảnh. Cần xem trạng thái, stack, số lượng luồng và thời điểm xảy ra sự cố trong cùng một bối cảnh.

### Heap tăng hoặc nghi ngờ memory leak

1. Xem tổng quan bằng **jcmd <pid> GC.heap_info**.
2. Dùng **jstat -gcutil <pid> 1000 10** để quan sát xu hướng sử dụng heap và hoạt động GC.
3. Nếu cần xác định lớp chiếm nhiều bộ nhớ, lấy **GC.class_histogram** và so sánh các lần chụp.
4. Khi cần truy vết tham chiếu, tạo heap dump và phân tích ngoại tuyến.

Memory leak trong Java thường xảy ra khi đối tượng không còn cần thiết nhưng vẫn được giữ bởi một tham chiếu còn sống. Histogram chỉ cho biết số lượng và dung lượng theo lớp; heap dump mới cung cấp đồ thị tham chiếu để lần theo đối tượng nào đang giữ các đối tượng khác.

### GC diễn ra thường xuyên hoặc pause kéo dài

1. Dùng **jstat** để xem bộ đếm GC và mức sử dụng các vùng heap qua nhiều mẫu.
2. Dùng JFR để xem thời điểm, thời lượng và loại sự kiện GC.
3. Đối chiếu với tải yêu cầu, tốc độ cấp phát và cấu hình heap.
4. Chỉ điều chỉnh cờ JVM sau khi đã có bằng chứng về nguyên nhân và hiểu tác động của thay đổi.

Không nên kết luận chỉ từ một lần Full GC hoặc một giá trị phần trăm heap. Cần xem xu hướng, tần suất, thời gian pause và khả năng thu hồi bộ nhớ.

### Nghi ngờ bộ nhớ native tăng

Nếu heap không tăng tương ứng nhưng bộ nhớ tiến trình vẫn tăng, cần kiểm tra phần native như thread stack, code cache hoặc vùng cấp phát native. Khi JVM đã bật NMT từ đầu, dùng:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT cung cấp góc nhìn về các nhóm cấp phát native do JVM theo dõi. Nó không thay thế công cụ giám sát hệ điều hành và không thể giải thích mọi vùng nhớ native do thư viện bên ngoài cấp phát.

## 10. Ví dụ thực hành với Java 17+

Chương trình sau giữ lại một lượng dữ liệu nhỏ trên heap, tạo một luồng có tên rõ ràng và chờ để có thời gian quan sát. Nó không phụ thuộc thư viện bên ngoài.

Tạo tệp **RuntimeToolsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class RuntimeToolsDemo {
    private static volatile List<byte[]> retained;

    public static void main(String[] args) throws InterruptedException {
        retained = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            retained.add(new byte[1024 * 1024]);
        }

        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(1_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-worker");
        worker.start();

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Ready for diagnostics.");
        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch và chạy trong terminal thứ nhất:

~~~bash
javac RuntimeToolsDemo.java
java RuntimeToolsDemo
~~~

Chương trình in PID của chính JVM và giữ tiến trình hoạt động:

~~~text
PID=<PID của tiến trình hiện tại>
Ready for diagnostics.
~~~

Giá trị PID thay đổi theo mỗi lần chạy. Mở terminal thứ hai và thay **<PID>** bằng giá trị vừa in:

~~~bash
jcmd <PID> VM.version
jcmd <PID> Thread.print -l
jcmd <PID> GC.heap_info
jstat -gcutil <PID> 1000 5
~~~

Trong thread dump, tìm luồng có tên **demo-worker**. Luồng này thường ở trạng thái TIMED_WAITING vì đang ngủ trong **Thread.sleep**. Đây là trạng thái dự kiến của ví dụ, không phải deadlock.

Có thể ghi JFR trong 30 giây:

~~~bash
jcmd <PID> JFR.start name=demo settings=profile duration=30s filename=runtime-demo.jfr
~~~

Sau khi recording kết thúc, phân tích tệp:

~~~bash
jfr summary runtime-demo.jfr
jfr print --events jdk.ThreadSleep,jdk.GarbageCollection runtime-demo.jfr
~~~

Nếu chạy trong môi trường thật, hãy thay tên tệp bằng đường dẫn tuyệt đối tới thư mục mà tiến trình JVM có quyền ghi. Kết thúc chương trình demo bằng Ctrl+C trong terminal thứ nhất.

## 11. Nguyên tắc vận hành an toàn

- **Xác định đúng tiến trình:** luôn đối chiếu PID với tên lớp, JAR và tham số chạy trước khi gửi lệnh.
- **Đúng quyền và môi trường:** Attach thường yêu cầu công cụ chạy trên cùng máy và cùng người dùng hiệu lực với JVM đích. Trong container, PID namespace có thể khác máy host; khi cần, chạy công cụ trong chính container hoặc dùng đúng PID mà container nhìn thấy.
- **Kiểm tra khả năng Attach:** JVM có thể được khởi chạy với **-XX:+DisableAttachMechanism**, hoặc môi trường bảo mật có thể chặn Attach. Khi đó lệnh có thể không kết nối được dù PID đúng.
- **Ưu tiên công cụ tương thích:** dùng JDK có phiên bản phù hợp với JVM đích; đọc **help** của chính tiến trình để biết lệnh nào được hỗ trợ.
- **Đánh giá tác động:** thread dump thường nhẹ hơn heap dump, histogram hoặc thao tác buộc GC. Không chạy liên tục các lệnh nặng trên hệ thống đang chịu tải cao.
- **Chuẩn bị nơi lưu:** heap dump và JFR có thể lớn. Kiểm tra dung lượng đĩa, quyền ghi và chính sách lưu trữ trước khi tạo tệp.
- **Bảo vệ dữ liệu chẩn đoán:** heap dump có thể chứa dữ liệu ứng dụng trong bộ nhớ; system properties, command line, JFR và thread dump cũng có thể để lộ thông tin nội bộ. Không tải lên nơi công cộng hoặc gửi nguyên trạng khi chưa rà soát.

Một quy trình tốt bắt đầu bằng câu hỏi cụ thể, chọn công cụ có tác động thấp, lưu lại dữ liệu cùng thời điểm xảy ra sự cố và so sánh nhiều mẫu. Dùng **jcmd** cho trạng thái JVM, **jstat** cho xu hướng GC, JFR cho diễn biến hiệu năng và heap dump khi cần truy vết tham chiếu sâu.
