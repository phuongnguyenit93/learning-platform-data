# 1.8 Phạm vi API chuẩn Java 21, công cụ HotSpot và khả năng thay đổi theo phiên bản

Trong **mô hình chẩn đoán JVM**, điều quan trọng đầu tiên là biết một phép đo hoặc lệnh chẩn đoán được bảo đảm bởi **Java SE 21**, được cung cấp bởi **một bản phân phối JDK**, hay phụ thuộc vào **VM HotSpot**. Ba lớp này có phạm vi tương thích, cách triển khai, chi phí vận hành và rủi ro khi nâng cấp khác nhau. Cùng chạy được trên Java 21 không có nghĩa là cùng được Java SE bảo đảm.

## Mục tiêu học tập

Sau bài này, bạn có thể:
- Phân loại API chẩn đoán theo hợp đồng Java SE, API JDK công khai và cơ chế riêng của HotSpot.
- Chọn điểm quan sát đủ tính di động trước khi dùng công cụ đặc thù của VM.
- Kiểm tra khả năng thực tế của **JDK 21 đang chạy ứng dụng**, thay vì suy luận từ tên phiên bản hoặc máy phát triển.
- Dự báo những gì cần kiểm thử khi đổi bản vá JDK, nhà cung cấp JVM, image triển khai hoặc phiên bản Java.

## 1. Ba tầng của hợp đồng chẩn đoán

| Tầng | Ví dụ trong Java 21 | Mức bảo đảm và phạm vi sử dụng |
| --- | --- | --- |
| **Java SE 21 (API chuẩn)** | **java.management** với JMX, **java.lang.management.ManagementFactory**, **ThreadMXBean**, **MemoryMXBean**; **java.instrument** với giao diện agent chuẩn | Các kiểu và hành vi được đặc tả bởi Java SE; có thể viết logic giám sát di động, nhưng từng khả năng đo đạc vẫn có thể là tùy chọn và phải được hỏi qua API. |
| **API JDK công khai, không thuộc Java SE** | **jdk.jfr** với **Recording**; **jdk.attach** với **VirtualMachine**; **jdk.management** với **com.sun.management.HotSpotDiagnosticMXBean** | Được tài liệu JDK mô tả, hữu ích trên JDK hỗ trợ; không bắt buộc tồn tại trong mọi triển khai Java SE hoặc image runtime tùy biến. API công khai không đồng nghĩa với API chuẩn Java SE. |
| **Công cụ/lệnh và tùy chọn VM** | **jcmd** với **Thread.print**, **GC.heap_info**, **JFR.start**; **jstat**, **jmap**, **jhsdb**; các cờ **-XX:** | Cú pháp, tập lệnh, định dạng đầu ra, quyền attach, chi phí và khả năng hiện diện phụ thuộc JDK, VM, nền tảng và bản phát hành. Phải kiểm tra trên tiến trình đích. |

Theo tài liệu API Java 21, các module **java.*** là phần của Java SE, còn module **jdk.*** cung cấp API riêng của JDK. Tuy nhiên, **tên package không đủ để phân loại**: package **com.sun.management** là API JDK được công bố qua module **jdk.management**; ngược lại các **jdk.internal.*** không phải hợp đồng công khai để ứng dụng phụ thuộc. Không nên khắc phục bằng cách tùy tiện mở module nội bộ với **--add-exports** hoặc **--add-opens** chỉ để chẩn đoán.

Cũng cần tách **giao diện chuẩn** khỏi **tính năng tùy chọn**. Ví dụ **ThreadMXBean** là API chuẩn, nhưng đo CPU time hoặc giám sát lock có thể không được VM hỗ trợ/đang bật. Kiểm tra các phương thức như **isThreadCpuTimeSupported()**, **isThreadCpuTimeEnabled()**, **isSynchronizerUsageSupported()** trước khi phụ thuộc vào phép đo. Một API tồn tại không bảo đảm mọi phép đo đều có dữ liệu.

## 2. Điểm quan sát di động: Java SE 21

**JMX / ManagementFactory** phù hợp cho lớp thu thập dữ liệu cơ bản trong ứng dụng: danh tính JVM, thời gian hoạt động, thông tin bộ nhớ/GC, số platform thread, deadlock của platform thread, thông tin class loading và một số bộ đếm. Truy cập nội bộ qua MXBean không đòi hỏi attach vào tiến trình khác; truy cập JMX từ xa lại là một cấu hình vận hành khác, cần xác thực, mã hóa và giới hạn mạng.

Ví dụ hoàn chỉnh dưới đây dùng API Java SE để lấy dữ liệu, và chỉ dùng **ModuleFinder** (cũng thuộc Java SE) để kiểm tra module JFR có nằm trong runtime image hay không.

**Tệp DiagnosticCapabilities.java**

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;
import java.lang.module.ModuleFinder;

public class DiagnosticCapabilities {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("Java feature: " + Runtime.version().feature());
        System.out.println("VM name: " + runtime.getVmName());
        System.out.println("VM vendor: " + runtime.getVmVendor());
        System.out.println("Process ID: " + ProcessHandle.current().pid());
        System.out.println("Platform threads: " + threads.getThreadCount());
        System.out.println("Thread CPU time supported: "
                + threads.isThreadCpuTimeSupported());
        System.out.println("JFR module installed: "
                + ModuleFinder.ofSystem().find("jdk.jfr").isPresent());
    }
}
~~~

Biên dịch và chạy bằng **JDK 21**:

~~~bash
javac --release 21 DiagnosticCapabilities.java
java DiagnosticCapabilities
~~~

Các dòng nhãn luôn theo thứ tự như trong mã; **giá trị** VM, nhà cung cấp, PID, số thread và hai cờ boolean thay đổi theo môi trường. **--release 21** kiểm tra tập API chuẩn Java 21 của ví dụ này; nó không xác nhận sự sẵn có của lệnh **jcmd** hay các module JDK đặc thù. **ModuleFinder.ofSystem()** trả lời module **jdk.jfr** có trong image hay không, không chứng minh rằng recording sẽ khởi động thành công hoặc rằng attach từ ngoài được phép.

**Giới hạn rất dễ bỏ sót của Java 21:** **java.lang.management.ThreadMXBean** chỉ giám sát **platform threads**, không giám sát **virtual threads**. Vì vậy số lượng thread, thread ID, CPU time, stack snapshot và kết quả tìm deadlock từ MXBean này không đại diện cho toàn bộ virtual threads của ứng dụng. Với ứng dụng dùng virtual threads, cần kết hợp cơ chế chẩn đoán hỗ trợ chúng (chẳng hạn các event JFR tương ứng khi có và được bật) và kiểm tra phiên bản cụ thể.

**java.instrument** là API chuẩn để agent tương tác với lớp khi được cấp quyền; song cách **attach/load agent động** và những cảnh báo liên quan thuộc chính sách triển khai JDK/VM, không phải bảo đảm rằng mọi JVM đều cho phép gắn agent vào một tiến trình bất kỳ.

## 3. API JDK công khai: mạnh hơn nhưng có điều kiện

**Java Flight Recorder (JFR)** là lựa chọn quan trọng khi cần chuỗi sự kiện theo thời gian: GC, cấp phát, I/O, lock, CPU, lớp, thread hoặc event của ứng dụng. Java 21 cung cấp API công khai **jdk.jfr.Recording**, **jdk.jfr.Event** và API đọc file trong **jdk.jfr.consumer**. Đây là API **JDK-specific**, khác với các module **java.management** chuẩn. Tập event, tên/thuộc tính event, cấu hình và overhead cần được kiểm chứng theo JDK thực tế.

Ví dụ độc lập dưới đây minh họa việc tạo một recording ngắn trên **JDK 21 có JFR**. Đây là chương trình chủ động ghi dữ liệu của chính nó, không attach vào JVM khác.

**Tệp JfrSample.java**

~~~java
import java.nio.file.Path;
import jdk.jfr.Recording;

public class JfrSample {
    public static void main(String[] args) throws Exception {
        Path destination = Path.of("sample.jfr");

        try (Recording recording = new Recording()) {
            recording.setName("short-sample");
            recording.start();
            Thread.sleep(1000);
            recording.stop();
            recording.dump(destination);
        }

        System.out.println("Created sample.jfr");
    }
}
~~~

~~~bash
javac --add-modules jdk.jfr JfrSample.java
java --add-modules jdk.jfr JfrSample
jfr summary sample.jfr
~~~

Khi hai lệnh đầu thành công, chương trình in chính xác **Created sample.jfr** và tạo tệp **sample.jfr** tại thư mục chạy. Lệnh **jfr summary** sau đó in thống kê động, phụ thuộc những event được ghi và bản JDK. Tùy chọn **--add-modules jdk.jfr** nêu rõ phụ thuộc JDK; image thiếu module này sẽ không chạy được ví dụ. Đừng áp dụng máy móc **javac --release 21** cho mã dùng API ngoài tập Java SE mà không kiểm tra cách biên dịch của JDK và cấu hình module.

Các ví dụ API JDK khác cần phân biệt:
- **com.sun.management.OperatingSystemMXBean** mở rộng thông tin hệ điều hành/quá trình; phương thức và ý nghĩa các chỉ số phải đối chiếu Javadoc của JDK.
- **com.sun.management.HotSpotDiagnosticMXBean** có thể hỗ trợ lấy heap dump và tùy chọn chẩn đoán khi VM hỗ trợ; đây không phải hợp đồng đa JVM.
- **com.sun.tools.attach.VirtualMachine** trong **jdk.attach** cung cấp cơ chế attach; có class không bảo đảm tiến trình đích cho attach, có quyền tương ứng hoặc cho phép agent động.

Không nên dùng API nội bộ phản chiếu, địa chỉ bộ nhớ VM hay parsing chuỗi output của công cụ như thể đó là định dạng ổn định. Khi cần phân tích máy móc, ưu tiên API có kiểu rõ ràng hoặc định dạng/đầu đọc được tài liệu hỗ trợ.

## 4. Công cụ HotSpot/JDK: nhận diện trước, thực thi sau

**Lưu ý về thuật ngữ:** **HotSpot** là một triển khai JVM. **JDK** là bộ phân phối gồm runtime, công cụ và các module. Nhiều bản OpenJDK sử dụng HotSpot nhưng vẫn khác nhau về thành phần đóng gói và bản vá; JVM khác như OpenJ9 có công cụ/khả năng riêng. Có **Java 21** không đồng nghĩa với việc có mọi chương trình trong thư mục **bin**.

| Công cụ hoặc cơ chế | Dùng để làm gì | Phạm vi và điều kiện quan trọng |
| --- | --- | --- |
| **java -version**, **java --list-modules** | Xem runtime đang gọi, module trong image | Chạy trên đúng máy/container; bản **java** ở PATH có thể khác JVM đang chạy ứng dụng. |
| **jcmd -l**, **jcmd PID help** | Phát hiện JVM và danh sách lệnh khả dụng | Cần công cụ, cơ chế attach/quyền và khả năng nhìn thấy tiến trình; danh sách lệnh do JVM đích quyết định. |
| **jcmd PID VM.version / VM.command_line** | Kiểm tra VM và tham số khởi động thực tế | Thường hữu ích trước khi diễn giải các số liệu; không nên suy ra cấu hình chỉ từ lệnh java của terminal. |
| **jcmd PID Thread.print -l** | Snapshot stack/lock của các thread mà lệnh hỗ trợ | Có thể tốn thời gian khi rất nhiều thread; không mặc nhiên là dump đầy đủ mọi virtual thread. |
| **jcmd PID GC.heap_info** | Thông tin tổng quát về heap/GC | Không thay được heap dump; vẫn có tác động lên tiến trình. |
| **jcmd PID JFR.start / JFR.check / JFR.dump** | Thu thập, xem trạng thái và xuất recording | Yêu cầu target hỗ trợ JFR, quyền phù hợp, dung lượng lưu trữ; file được tạo trong hệ tệp mà JVM đích nhìn thấy. |
| **jfr summary / jfr print** | Đọc và lọc file JFR | Cần công cụ đọc hỗ trợ định dạng recording; dữ liệu/event phụ thuộc cấu hình thu thập. |
| **jstat**, **jmap**, **jstack**, **jhsdb** | Một số thao tác thống kê/heap/thread/Serviceability Agent | Công cụ và chế độ hỗ trợ khác nhau theo VM, OS, JDK. Một số thao tác làm dừng hoặc ảnh hưởng mạnh JVM; không dùng mù quáng trên production. |
| **-XX:...**, Native Memory Tracking | Tùy chọn và thống kê riêng của HotSpot | Phụ thuộc JVM; NMT cần bật bằng tùy chọn tương ứng từ khi JVM khởi động, không thể suy ra rằng luôn có dữ liệu. |

### Quy trình nhận diện một tiến trình thực tế

Ví dụ lệnh sau dùng **PID 12345 để minh họa**; thay bằng PID thật thu được từ công cụ quản lý tiến trình của môi trường đích.

~~~bash
java -version
javac -version
java --list-modules
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 help
jcmd 12345 help Thread.print
~~~

Thứ tự có chủ đích: biết **tool đang gọi** trước, biết **VM đích** tiếp theo, rồi mới khám phá lệnh **đích hỗ trợ**. Nếu **jcmd -l** không liệt kê tiến trình, chưa thể kết luận ứng dụng không chạy: PID namespace/container, user chạy JVM, cơ chế attach, image runtime rút gọn và phân quyền đều có thể ảnh hưởng khả năng khám phá.

**Không chạy công cụ JDK trên máy host rồi mặc định nó attach được vào JVM trong container.** Cần xét PID namespace, quyền hệ điều hành, filesystem dùng cho attach và chỗ tệp output xuất hiện. Image tạo bởi **jlink** hoặc image runtime tối giản có thể không mang theo **jcmd**, **jfr**, **jmap**, cũng có thể loại bỏ các module JDK không cần cho ứng dụng.

## 5. Chọn công cụ theo bài toán và chi phí

Một lượt chẩn đoán có thể đi theo mức tác động tăng dần:

1. **Xác nhận ngữ cảnh:** thời điểm sự cố, PID, VM name/vendor/version, uptime, cờ khởi động, container và tải ứng dụng. Việc chạy **java -version** ở shell chỉ là kiểm tra môi trường shell, không thay cho xác minh JVM đích.
2. **Quan sát ít xâm lấn:** số liệu JMX/MXBean sẵn có, metrics của ứng dụng, log và các lệnh thông tin như **VM.version**; đối chiếu phép đo với thời gian và tải.
3. **Thu thập có thời hạn:** JFR với cấu hình, thời lượng và file đích xác định; thread dump khi điều tra nghẽn hoặc deadlock. Đọc tài liệu impact của từng **jcmd** diagnostic command.
4. **Đi sâu có kiểm soát:** class histogram, heap dump, agent động, debugger/Serviceability Agent hoặc thay đổi cờ VM chỉ khi dấu hiệu hiện có biện minh cho chi phí, ảnh hưởng latency, bộ nhớ, CPU và lưu trữ.

Ví dụ xử lý giả định JVM **HotSpot/JDK 21** hỗ trợ đúng các lệnh sau:

~~~bash
jcmd 12345 Thread.print -l
jcmd 12345 GC.heap_info
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=/tmp/triage.jfr
jcmd 12345 JFR.check
~~~

Sau khi recording kết thúc và file đã có, chạy **jfr summary /tmp/triage.jfr** ở nơi có thể truy cập file và có công cụ JFR tương thích. **/tmp/triage.jfr** là đường dẫn nhìn từ **JVM đích**; với container, bạn có thể phải sao chép file ra môi trường phân tích.

**Không xem các lệnh trên là “zero overhead”.** Ngay cả **Thread.print** có mức tác động tùy số thread; **GC.heap_info** có tác động; **GC.class_histogram** và **GC.heap_dump** được tài liệu JDK 21 xếp vào nhóm tác động cao tùy kích thước/nội dung heap. Heap dump có thể lớn, làm tạm dừng ứng dụng, tiêu tốn đĩa và chứa dữ liệu nhạy cảm. JFR thường phù hợp cho quan sát có thời hạn nhưng mức overhead vẫn phụ thuộc event và cấu hình, nhất là profile/stack trace.

Nếu phải thu thập từ xa, cần phân biệt **JMX remote** (mở kênh giám sát có xác thực và bảo vệ truyền tải) với **local attach** của **jcmd**. Hai cơ chế có mô hình quyền và bề mặt vận hành khác nhau. Không bật public JMX port hoặc mở quyền attach chỉ để thử chẩn đoán.

## 6. Những thay đổi quan trọng theo phiên bản

Phân biệt ít nhất **bốn trục thay đổi**:

| Trục | Điều có thể thay đổi | Kiểm chứng trước khi dùng |
| --- | --- | --- |
| **Java SE 21 so với Java SE phiên bản khác** | API, ngôn ngữ, giới hạn tính năng và quy tắc tương thích của bản nền tảng | Javadoc và thông số kỹ thuật **đúng feature release**; biên dịch phần Java SE bằng **--release 21** khi mục tiêu là Java 21. |
| **JDK vendor, VM implementation** | Có/không JFR, attach provider, MXBean mở rộng, lệnh chẩn đoán, cấu hình mặc định | **VM.version**, module trong image, tài liệu vendor, kết quả kiểm tra khả năng trong tiến trình đích. |
| **Bản cập nhật và cấu hình của cùng JDK 21** | Bản vá lỗi, quyền, tùy chọn, hành vi diagnostics/JFR, giới hạn tài nguyên | Ghi lại **full runtime version + vendor + flags**, không chỉ số **21**; thử lại quy trình sau update. |
| **Môi trường triển khai** | Công cụ bị loại khỏi image, module bị bỏ, quyền container, filesystem, PID và chính sách bảo mật | Kiểm tra trong chính container/host chạy service; xác nhận module, executable, quyền và nơi ghi file. |

Đặc biệt với **JDK 21**, **JEP 451** đưa ra **cảnh báo khi agent được nạp động** để chuẩn bị cho chính sách chặt hơn trong các bản tương lai. Không đồng nhất cảnh báo JDK 21 với việc mọi dynamic agent đều đã bị chặn ở JDK 21. Nếu sản phẩm cần instrumentation, ưu tiên định nghĩa rõ agent được nạp lúc khởi động hay qua attach, kiểm tra chính sách JVM phiên bản đích và kiểm thử trước khi nâng cấp.

Với **virtual threads** được chuẩn hóa trong Java 21, khả năng quan sát càng cần nhìn theo API và công cụ cụ thể: **ThreadMXBean** chuẩn chỉ thấy platform threads, trong khi JFR/những công cụ khác có thể cung cấp dữ liệu bổ sung theo khả năng của bản JDK. Không dùng tổng platform-thread count để tuyên bố số virtual threads đang hoạt động.

Cũng không coi **định dạng text** do **jcmd**, **jstack** hoặc **jmap** in ra là giao thức ổn định để tích hợp dài hạn. Nếu phải tự động hóa, lưu version được kiểm chứng, kiểm tra exit status, xử lý thiếu lệnh/thiếu cột và có nhánh fallback; tránh parser dựa vào vị trí dòng cố định.

## 7. Mẫu chiến lược tương thích cho công cụ chẩn đoán

Một thư viện hoặc quy trình vận hành có thể tách thành ba đường:

- **Baseline luôn ưu tiên Java SE:** đọc MXBean chuẩn, log có cấu trúc và metric ứng dụng; kiểm tra cờ hỗ trợ của từng phép đo.
- **Nâng cấp khi có capability:** nếu module **jdk.jfr** hiện diện và thử recording thành công, bật JFR theo chính sách; nếu JVM đích cho phép và có **jcmd**, dùng những diagnostic command mà **jcmd PID help** thật sự liệt kê.
- **Fallback tường minh:** khi thiếu module/tool/quyền hoặc VM khác HotSpot, tiếp tục quan sát bằng baseline; ghi rõ bằng chứng nào chưa lấy được thay vì xuất số 0 hoặc báo “không có sự cố”.

Ví dụ: một service trên JDK 21 HotSpot chạy ở development có đủ **jcmd + jfr**, nhưng image production chỉ chứa runtime modules. Hai môi trường có thể có cùng bytecode ứng dụng và cùng Java feature version, song thao tác chẩn đoán từ shell sẽ khác. Giải pháp đúng là khai báo yêu cầu vận hành từ lúc đóng gói image, hoặc bố trí cách quan sát được hỗ trợ, không ràng buộc logic business vào sự tồn tại của executable ngoài ứng dụng.

Đối với kết quả chẩn đoán, nên ghi kèm **timestamp, PID, Java feature/full version, VM name/vendor, source (API hay command), tập capability và cấu hình thu thập**. Nhờ đó dữ liệu có thể so sánh được sau nâng cấp và người đọc biết một ô trống là “không hỗ trợ/chưa thu thập” hay thực sự là giá trị không.

## 8. Các lỗi nhận thức thường gặp

1. **“API có trong JDK 21 nên là Java SE 21.”** Sai: **jdk.jfr**, **jdk.attach**, **jdk.management** là JDK-specific; cần phân biệt với **java.management** hoặc **java.instrument**.
2. **“JVM là Java 21 nên chắc chắn có jcmd.”** Sai: lệnh là thành phần công cụ JDK, có thể bị bỏ trong image hoặc không dùng được với VM/quyền hiện tại.
3. **“ThreadMXBean đếm tất cả thread.”** Sai trên Java 21: nó chỉ quản lý platform threads, không bao gồm virtual threads.
4. **“Không có deadlock trong MXBean nên không thể có vấn đề đồng bộ.”** Sai: phạm vi API, loại lock và virtual threads quyết định những gì được phát hiện; thiếu tín hiệu không chứng minh hệ thống khỏe.
5. **“Lệnh chạy được thì an toàn trên production.”** Sai: các lệnh dump/heap/agent có thể tạo pause, I/O lớn và dữ liệu nhạy cảm; phải đánh giá tác động.
6. **“Bản vá hoặc đổi JVM không ảnh hưởng script.”** Sai: danh sách lệnh, flags, định dạng text, event và điều kiện attach cần được kiểm tra lại.
7. **“Module hiện diện nghĩa là tính năng hoạt động.”** Sai: quyền, runtime flags, chính sách VM, cấu hình và filesystem vẫn có thể ngăn thao tác.

## 9. Tự kiểm tra

- Nếu muốn lấy số platform threads và bộ nhớ từ **nhiều JVM Java 21**, hãy bắt đầu với **java.management** và các kiểm tra capability. Nếu cần dòng thời gian sự kiện, cân nhắc **jdk.jfr** sau khi xác minh runtime.
- Nếu có **jcmd** trên máy phát triển nhưng thiếu trong container production, kiểm tra loại image và công cụ ở container; không suy luận từ phiên bản Java hoặc PATH của máy phát triển.
- Nếu một phép đo biến mất sau khi bật virtual threads hoặc thay VM, hãy hỏi **API đó đo đối tượng nào, có được hỗ trợ không, và dữ liệu được thu thập từ runtime nào** trước khi kết luận ứng dụng thay đổi hành vi.

**Tiêu chí áp dụng được:** với mỗi số liệu/lệnh chẩn đoán, bạn nói rõ được **hợp đồng nào bảo đảm nó**, **nơi nào chạy được**, **điều kiện/quyền cần có**, **chi phí thu thập**, và **cách xử lý khi nó không tồn tại hoặc thay đổi**. Đây là ranh giới thiết yếu để thiết kế mô hình chẩn đoán JVM đáng tin cậy.

## Tài liệu gốc để đối chiếu

- [Java SE 21 & JDK 21 API Specification — phân biệt module Java SE và JDK](https://docs.oracle.com/en/java/javase/21/docs/api/)
- [ThreadMXBean, Java SE 21 — phạm vi platform threads và capability tùy chọn](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [jcmd, JDK 21 — diagnostic commands và mức impact](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [jfr, JDK 21 — đọc file JFR](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [jlink, JDK 21 — runtime image tùy biến](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [JEP 451 — cảnh báo nạp agent động trong JDK 21](https://openjdk.org/jeps/451)
