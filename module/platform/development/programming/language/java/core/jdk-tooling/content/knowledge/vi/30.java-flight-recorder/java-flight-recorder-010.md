# Chi phí JFR

## 1. Chi phí JFR là gì?

Java Flight Recorder (JFR) thu thập sự kiện trong JVM và ứng dụng theo thời gian. Việc ghi sự kiện giúp điều tra CPU, garbage collection (GC), allocation, thread, lock, I/O và nhiều vấn đề runtime mà không cần thêm profiler bên ngoài.

**Chi phí JFR** là phần tài nguyên và tác động vận hành phát sinh khi ghi, lưu, chuyển và phân tích dữ liệu. Cần xem xét ít nhất năm nhóm:

1. **CPU:** JVM tạo event, lấy mẫu stack và ghi dữ liệu.
2. **Độ trễ:** một số loại dữ liệu hoặc thao tác bổ sung có thể tạo pause.
3. **Memory:** JFR dùng buffer trong JVM và có thể giữ dữ liệu trong repository.
4. **Disk I/O và dung lượng:** recording cần ghi chunk, lưu repository và file .jfr.
5. **Vận hành:** đội ngũ cần quản lý retention, bảo vệ dữ liệu và phân tích recording.

Chi phí thay đổi theo workload, số thread, tần suất event, cấu hình, thời gian ghi và loại dữ liệu cần thu thập. Không có một tỷ lệ overhead cố định áp dụng cho mọi ứng dụng.

## 2. JFR có overhead bao nhiêu?

JFR được thiết kế để thu thập dữ liệu với overhead thấp, nhưng không phải bằng không.

Oracle đưa ra các hướng dẫn tham khảo cho Java SE 24:

- Cấu hình **default.jfc** dành cho continuous recording thường có overhead dưới 1%.
- Continuous recording tiêu chuẩn với cấu hình mặc định thường không tạo ra ảnh hưởng hiệu năng đo được.
- Một recording profiling chạy trong thời gian cố định với default settings có overhead dưới 2% ở phần lớn ứng dụng.
- Cấu hình **profile.jfc** thu thập nhiều event hơn và có tác động hiệu năng lớn hơn **default.jfc**.

Đây là kết quả và hướng dẫn tham khảo của Oracle, không phải cam kết SLA. Một workload nhạy latency, tạo rất nhiều event hoặc bật thêm stack trace có thể có chi phí khác đáng kể.

Trong JDK 24, **jcmd <PID> help JFR.start** cũng cảnh báo rằng impact của **JFR.start** phụ thuộc settings và có thể từ thấp tới cao. Nếu sửa event settings mặc định, overhead có thể vượt 1%.

Vì vậy, hãy bắt đầu với **default.jfc**, đo trên workload đại diện và chỉ bật thêm dữ liệu khi câu hỏi điều tra yêu cầu.

Tài liệu: [Oracle Java SE 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html) và [Flight Recorder Overhead](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html).

## 3. So sánh default.jfc và profile.jfc

JDK cung cấp hai cấu hình dựng sẵn trong thư mục **JAVA_HOME/lib/jfr**:

| Cấu hình | Mục đích | Chi phí tương đối |
|---|---|---|
| default.jfc | Theo dõi liên tục, thu thập dữ liệu hữu ích với mức overhead thấp | Thấp |
| profile.jfc | Profiling chi tiết hơn trong một khoảng thời gian giới hạn | Cao hơn |

**default.jfc** phù hợp để luôn bật trên service cần khả năng điều tra sự cố hiếm gặp. Nó cân bằng giữa lượng dữ liệu và hiệu năng.

**profile.jfc** thường bật nhiều event hoặc lấy mẫu dày hơn. Dùng khi cần tìm hot method, allocation, compiler, lock contention hoặc bottleneck mà dữ liệu mặc định chưa đủ.

Không nên để profile recording chạy vô thời hạn chỉ vì muốn có nhiều dữ liệu. Ghi trong khoảng thời gian đủ để tái hiện vấn đề, sau đó dừng và phân tích.

Nếu cần tùy chỉnh, hãy sao chép file .jfc có sẵn rồi sửa bản sao. Không sửa trực tiếp **default.jfc** hoặc **profile.jfc** trong thư mục cài JDK vì thay đổi đó khó kiểm soát và có thể bị mất khi nâng cấp.

## 4. Chi phí CPU

CPU được dùng cho việc phát sinh event, lấy mẫu thread, thu thập stack trace và xử lý buffer.

Các yếu tố làm CPU tăng:

- Bật nhiều event hơn.
- Tăng tần suất sampling.
- Bật stack trace cho nhiều loại event.
- Giảm event threshold để ghi cả những thao tác rất ngắn.
- Ghi allocation chi tiết hoặc profiling method dày hơn.
- Chạy nhiều recording hoặc nhiều JVM cùng lúc.

Trong các cấu hình dựng sẵn, nhiều Java Application duration event chỉ được ghi khi thời gian vượt ngưỡng, thường là 20 ms. Ngưỡng này giúp hạn chế số event. Hạ xuống 1 ms có thể làm xuất hiện nhiều event hơn, tăng CPU, kích thước file và công sức phân tích.

Ví dụ cấu hình bắt đầu một recording với event threshold thấp hơn:

§§§bash
jcmd <PID> JFR.start name=short-profile settings=profile duration=5m jdk.JavaMonitorEnter#threshold=1ms
§§§

Chỉ hạ threshold cho event liên quan câu hỏi cần điều tra. Không hạ đồng loạt tất cả threshold trên production.

## 5. Chi phí latency và GC pause

Một số dữ liệu có thể làm tăng pause hoặc thay đổi thời gian phản hồi.

**Heap Statistics** là ví dụ quan trọng. Tính năng này tắt mặc định vì việc thu thập có thể kích hoạt một old garbage collection ở đầu và cuối recording. Hai lần GC này có thể tạo thêm pause cho ứng dụng.

Nếu mục tiêu là đo latency hoặc throughput, không bật Heap Statistics một cách mặc định. Chỉ bật khi điều tra memory leak hoặc cần xác định live set của ứng dụng và đã chấp nhận chi phí pause.

Tùy chọn **path-to-gc-roots** giúp truy tìm đường tham chiếu tới object từ GC roots, hữu ích khi điều tra memory leak. Tuy nhiên, thu thập dữ liệu này tốn thời gian và có thể làm ứng dụng pause trong một khoảng ngắn. Chỉ bật khi đã có nghi ngờ cụ thể về leak.

Ví dụ dump một recording và yêu cầu thêm đường dẫn GC roots:

§§§bash
jcmd <PID> JFR.dump name=memory-investigation path-to-gc-roots=true filename=memory-investigation.jfr
§§§

Không dùng tùy chọn này như cấu hình continuous mặc định. Nếu cần đánh giá latency, so sánh p95/p99 và GC pause khi tắt/bật tính năng trong môi trường thử nghiệm.

## 6. Chi phí memory trong JVM

JFR dùng buffer để thu thập event trước khi dữ liệu được ghi thành chunk. Memory sử dụng phụ thuộc cấu hình, số thread, event rate và thời gian dữ liệu được giữ trong buffer.

Một số giá trị cấu hình thường gặp trong JDK 24:

| Tham số | Giá trị mặc định | Vai trò |
|---|---:|---|
| memorysize | 10 MB | Tổng bộ nhớ JFR dành cho buffer |
| maxchunksize | 12 MB | Kích thước tối đa của một chunk |
| stackdepth | 64 | Độ sâu stack trace |
| thread_buffer_size | 8 KB | Buffer cục bộ cho mỗi thread |

Các giá trị này mô tả cấu hình JFR, không phải tổng mức tiêu thụ memory tuyệt đối của toàn bộ JVM. Tổng footprint thực tế còn phụ thuộc số thread, recording và hoạt động của runtime.

Một số lưu ý:

- Tăng **stackdepth** vượt mặc định 64 có thể làm giảm hiệu năng.
- Thay đổi **thread_buffer_size** có thể làm hiệu năng giảm và không được khuyến nghị nếu chưa có lý do đo đạc rõ ràng.
- Các tham số như **memorysize**, **maxchunksize** và **stackdepth** không thể thay đổi sau khi JFR đã được khởi tạo.
- Không tăng buffer chỉ để cố thu thập mọi event. Hãy kiểm tra data loss, event volume và mục tiêu điều tra trước.

Có thể xem cấu hình JFR của JVM:

§§§bash
jcmd <PID> JFR.configure
§§§

Đọc kết quả trước khi quyết định thay đổi startup option. Tham khảo cú pháp và giới hạn trong tài liệu của đúng JDK đang chạy.

## 7. Chi phí disk I/O và repository

Khi recording ghi ra disk, JFR lưu dữ liệu theo chunk trong một disk repository. Repository là nơi giữ dữ liệu tạm trong lúc recording chạy; file .jfr được tạo khi dump hoặc dừng recording theo cách đã cấu hình.

Trên Windows, repository mặc định nằm trong thư mục tạm được chỉ định bởi biến TMP. Trên Linux, thư mục tạm mặc định thường là /tmp.

Nếu không giới hạn thời gian hoặc kích thước, recording có thể giữ dữ liệu ngày càng nhiều. Vì vậy, continuous recording trên production nên có retention policy rõ ràng.

Hai giới hạn chính:

- **maxage:** thời gian tối đa giữ dữ liệu trong repository.
- **maxsize:** dung lượng tối đa giữ trên disk.

Cả hai chỉ có hiệu lực khi **disk=true**. Khi một giới hạn đạt tới, dữ liệu chunk cũ nhất bị loại bỏ để nhường chỗ cho dữ liệu mới. Nếu đặt cả hai, recording phải tuân theo giới hạn thời gian và dung lượng; giới hạn nào chạm trước sẽ quyết định lượng dữ liệu còn giữ.

Giá trị **0** có nghĩa là không giới hạn. Không dùng **maxage=0** và **maxsize=0** cho continuous recording trên máy có dung lượng đĩa hữu hạn nếu chưa có cơ chế quản lý bên ngoài.

Ví dụ cấu hình continuous recording giữ tối đa sáu giờ hoặc hai gigabyte dữ liệu:

§§§bash
jcmd <PID> JFR.start name=continuous settings=default disk=true maxage=6h maxsize=2G
§§§

Nếu repository dùng thư mục tạm có dung lượng thấp, hãy chọn repository path trên volume được giám sát và có đủ dung lượng. Đảm bảo tài khoản chạy JVM có quyền ghi và quy trình dọn dẹp không xóa file repository đang được JVM sử dụng.

## 8. Ước tính dung lượng recording

Dung lượng file JFR phụ thuộc event rate và cấu hình, do đó không nên dự đoán chỉ bằng thời gian ghi.

Có thể ước tính ban đầu từ recording thử nghiệm:

§§§text
Dung lượng dự kiến
  = Dung lượng trung bình mỗi giờ
    × Số giờ retention
    × Số JVM
    × Hệ số dự phòng
§§§

Ví dụ minh họa:

- Một JVM tạo trung bình 40 MB dữ liệu mỗi giờ.
- Muốn giữ 6 giờ.
- Có 20 JVM.
- Chọn hệ số dự phòng 1,5.

§§§text
40 MB × 6 × 20 × 1,5 = 7.200 MB
§§§

Với các giả định trên, cần khoảng 7,2 GB dung lượng cho repository của toàn bộ 20 JVM. Đây chỉ là phép tính minh họa; hãy dùng tốc độ tăng file thực tế của ứng dụng để lập ngân sách.

Khi sizing production, tính thêm:

- Dung lượng file .jfr được dump ra ngoài repository.
- Số recording đồng thời trên mỗi JVM.
- File tạm khi upload hoặc phân tích.
- Khoảng thời gian giữ bản sao phục vụ incident.
- Headroom cho thời điểm traffic hoặc event rate tăng đột biến.

Theo dõi kích thước repository theo thời gian thay vì chỉ kiểm tra một lần ngay sau khi bật JFR.

## 9. Giới hạn thời gian và kích thước khi ghi

**JFR.start** hỗ trợ **duration**, **maxage**, **maxsize**, **disk**, **filename** và **settings**.

Ví dụ profiling có thời hạn mười phút:

§§§bash
jcmd <PID> JFR.start name=profile settings=profile duration=10m disk=true maxage=15m maxsize=512M filename=/var/log/jfr/short-profile.jfr
§§§

Recording tự dừng khi hết thời gian. Kích thước và thời gian retention giới hạn lượng dữ liệu giữ trên disk trong lúc recording.

Kiểm tra recording đang chạy:

§§§bash
jcmd <PID> JFR.check
§§§

Dump dữ liệu của continuous recording ra file:

§§§bash
jcmd <PID> JFR.dump name=continuous filename=/var/log/jfr/continuous-snapshot.jfr
§§§

Có thể dump một khoảng thời gian tương đối, ví dụ dữ liệu của giờ gần nhất:

§§§bash
jcmd <PID> JFR.dump name=continuous begin=-1h filename=/var/log/jfr/last-hour.jfr
§§§

**JFR.dump** ghi dữ liệu ra file nhưng recording vẫn tiếp tục. Khi không cần ghi nữa, dừng recording:

§§§bash
jcmd <PID> JFR.stop name=continuous
§§§

Nếu muốn ghi ngay từ lúc ứng dụng khởi động, có thể dùng startup option:

§§§bash
java -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=2G -jar app.jar
§§§

Các ví dụ dùng đường dẫn Linux; trên Windows, thay bằng đường dẫn phù hợp và bảo đảm tài khoản service có quyền ghi.

## 10. Chọn event settings để kiểm soát chi phí

Mỗi event có thể có các setting như:

| Setting | Vai trò | Ảnh hưởng khi tăng thu thập |
|---|---|---|
| enabled | Bật/tắt event | Nhiều event hơn khi bật thêm loại |
| threshold | Thời gian tối thiểu để ghi duration event | Hạ ngưỡng làm tăng số event |
| period | Chu kỳ phát sinh periodic event | Chu kỳ ngắn tạo nhiều mẫu hơn |
| stackTrace | Ghi stack trace của event | Thêm chi phí CPU và dữ liệu |

Chỉ bật event cần thiết. Ví dụ:

- Điều tra lock contention: xem **jdk.JavaMonitorEnter** và **jdk.JavaMonitorWait**.
- Điều tra I/O: xem **jdk.FileRead**, **jdk.FileWrite**, **jdk.SocketRead**, **jdk.SocketWrite**.
- Điều tra CPU: xem **jdk.ExecutionSample**, **jdk.CPULoad** và **jdk.ThreadCPULoad**.
- Điều tra GC: xem **jdk.GarbageCollection**, **jdk.GCPhasePause** và các event GC liên quan.
- Điều tra allocation: chọn allocation profiling phù hợp và chấp nhận file có thể lớn hơn.

Nếu cần tùy chỉnh, tạo bản sao của cấu hình hiện tại và điều chỉnh bằng JDK Mission Control hoặc **jfr configure**. Không bật mọi event ở mức chi tiết cao chỉ vì muốn có dữ liệu đầy đủ; cấu hình như vậy có thể tạo rất nhiều dữ liệu và làm overhead tăng mạnh.

Tài liệu: [Flight Recorder Event Configuration](https://docs.oracle.com/en/java/javase/24/jfapi/configuration.html).

## 11. Đo overhead JFR một cách công bằng

Không thể đánh giá overhead chỉ bằng cảm giác hoặc một lần chạy. Hãy so sánh trên cùng workload.

Quy trình đề xuất:

1. Chuẩn bị môi trường staging hoặc benchmark gần production.
2. Cố định JDK vendor/version, OS, heap, GC, CPU quota và cấu hình ứng dụng.
3. Chạy workload không bật JFR để lấy baseline.
4. Chạy lại cùng workload với **default.jfc**.
5. Chạy lại với **profile.jfc** trong thời gian giới hạn.
6. Lặp lại các lượt đo đủ số lần để giảm ảnh hưởng của nhiễu.
7. So sánh throughput, p50/p95/p99 latency, CPU, allocation rate, GC pause, RSS và disk write.
8. Kiểm tra recording có đủ event cần thiết và có **jdk.DataLoss** hay không.
9. Ghi lại cấu hình, thời gian đo và điều kiện tải để lần sau có thể tái lập.

Bảng so sánh mẫu:

| Chỉ số | Không JFR | Default | Profile |
|---|---:|---:|---:|
| Throughput (req/s) | 10.000 | 9.980 | 9.850 |
| p99 latency (ms) | 80 | 81 | 86 |
| CPU (%) | 65 | 65,5 | 68 |
| GC pause (ms/phút) | 120 | 121 | 126 |
| Disk write (MB/giờ) | 0 | 35 | 180 |

Các số trên chỉ là dữ liệu minh họa cách trình bày. Không dùng chúng làm ngưỡng chuẩn hoặc kết quả kỳ vọng cho hệ thống thật.

Công thức tham khảo:

§§§text
CPU overhead (%) =
  (CPU_with_JFR - CPU_baseline) / CPU_baseline × 100

Latency change (%) =
  (p99_with_JFR - p99_baseline) / p99_baseline × 100
§§§

Khi baseline bằng 0 hoặc quá nhỏ, phần trăm có thể không có ý nghĩa; khi đó so sánh giá trị tuyệt đối. Nếu workload biến động, dùng nhiều lần chạy và phân tích phân bố thay vì chỉ lấy một con số trung bình.

## 12. Đọc recording để kiểm soát chi phí

Sau khi có file .jfr, dùng lệnh **jfr** để xem tóm tắt:

§§§bash
jfr summary recording.jfr
§§§

In một nhóm event cụ thể:

§§§bash
jfr print --events jdk.ExecutionSample,jdk.CPULoad recording.jfr
§§§

Kiểm tra event mất dữ liệu:

§§§bash
jfr print --events jdk.DataLoss recording.jfr
§§§

Mở file trong JDK Mission Control (JMC) để xem timeline, event count, hot methods, allocation, GC và thread activity.

Nếu file lớn bất thường:

- Kiểm tra event nào chiếm nhiều byte hoặc có số lượng quá lớn.
- Xem threshold và period có thấp hơn nhu cầu không.
- Kiểm tra stack trace có bật trên nhiều event không.
- So sánh **default** với **profile**.
- Giảm phạm vi event và thời gian recording.
- Dùng **maxage**/**maxsize** để giữ repository trong giới hạn.

Không xóa event chỉ để làm file nhỏ nếu event đó là bằng chứng cần cho câu hỏi điều tra. Hãy cân bằng dung lượng với khả năng giải thích sự cố.

## 13. Mẹo giảm chi phí khi chạy trên production

- Bắt đầu với **default.jfc** cho continuous recording.
- Giới hạn retention bằng **maxage** và **maxsize**.
- Chọn repository path trên volume đủ dung lượng và được giám sát.
- Dùng **profile.jfc** trong thời gian ngắn khi cần dữ liệu sâu hơn.
- Chỉ bật Heap Statistics khi điều tra memory leak hoặc live set.
- Chỉ bật **path-to-gc-roots** khi thực sự cần truy vết object.
- Giữ stack depth mặc định trừ khi có bằng chứng cần stack sâu hơn.
- Không tăng **thread_buffer_size** nếu chưa đo được lợi ích.
- Chỉ hạ event threshold cho loại event cụ thể.
- Tránh chạy nhiều profiling recording trên cùng JVM nếu không cần.
- Dừng recording tạm thời sau khi hoàn tất điều tra.
- Đo lại overhead sau mỗi thay đổi cấu hình.

Nếu ứng dụng nhạy latency, hãy đánh giá thêm thời gian GC pause và p99 latency thay vì chỉ nhìn CPU trung bình.

## 14. Ví dụ Java 17+: tạo recording có giới hạn bằng JFR API

JFR API cho phép ứng dụng tự tạo recording và đặt giới hạn retention. Ví dụ dưới đây dùng **default** configuration, bật ghi ra disk và giới hạn dữ liệu trong repository ở tối đa năm phút hoặc 64 MB.

Tạo file **JfrCostDemo.java**:

§§§java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class JfrCostDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("jfr-cost-demo.jfr");

        try (Recording recording = new Recording(
                Configuration.getConfiguration("default"))) {
            recording.setName("jfr-cost-demo");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(64L * 1024 * 1024);
            recording.start();

            long deadline = System.nanoTime()
                    + Duration.ofSeconds(2).toNanos();
            long checksum = 0;

            while (System.nanoTime() < deadline) {
                checksum += System.nanoTime() & 0xff;
            }

            recording.stop();
            recording.dump(output);

            if (checksum == Long.MIN_VALUE) {
                throw new AssertionError("unreachable");
            }
        }

        System.out.println(
            "Recording created: " + Files.exists(output));
    }
}
§§§

Biên dịch và chạy:

§§§bash
javac JfrCostDemo.java
java JfrCostDemo
§§§

Stdout chính xác:

§§§text
Recording created: true
§§§

File **jfr-cost-demo.jfr** được tạo trong thư mục hiện tại. Xem nội dung tóm tắt:

§§§bash
jfr summary jfr-cost-demo.jfr
§§§

Kích thước và số lượng event thay đổi theo JDK, máy và thời điểm chạy. Ví dụ này minh họa cách giới hạn recording và tạo file; vòng lặp không phải benchmark overhead JFR. Muốn đo overhead, hãy chạy workload ứng dụng thực tế trong các lượt baseline/default/profile như mục trước.

## 15. Lỗi thường gặp liên quan chi phí JFR

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| CPU tăng sau khi bật JFR | Dùng **profile.jfc**, nhiều event hoặc sampling dày | Chuyển về **default**, giảm event và đo lại |
| p99 latency tăng | Bật Heap Statistics hoặc thu thập event tốn pause | Tắt heap stats; chỉ dùng khi điều tra memory leak |
| Disk đầy | Không giới hạn recording hoặc event rate tăng | Đặt **maxage**, **maxsize**, theo dõi repository |
| File .jfr lớn bất thường | Threshold quá thấp, nhiều stack trace hoặc profiling kéo dài | Kiểm tra **jfr summary**, giảm event và thời lượng |
| Không có event mong muốn | Event bị disable hoặc threshold quá cao | Kiểm tra .jfc và bật đúng event |
| Có **jdk.DataLoss** | Event rate vượt khả năng buffer/consumer trong điều kiện hiện tại | Kiểm tra tải, buffer, event volume và cấu hình recording |
| **JFR.start** báo maxsize không hợp lệ | maxsize nhỏ hơn maxchunksize | Đặt maxsize tối thiểu bằng maxchunksize đang cấu hình |
| Repository chiếm nhiều dung lượng | maxage/maxsize không đặt hoặc disk không như dự kiến | Kiểm tra **JFR.check**, **JFR.configure** và retention |
| Dump tạo pause | Bật **path-to-gc-roots** hoặc workload đang rất bận | Chỉ thu thập GC roots khi có mục tiêu memory leak rõ ràng |
| File không được tạo khi JVM thoát | dumponexit chưa bật hoặc process bị kill cưỡng bức | Cấu hình **dumponexit=true** hoặc dump chủ động trước shutdown |

## 16. Bảo vệ recording và chi phí vận hành

File JFR có thể chứa tên thread, class, method, command line, system property, environment variable, đường dẫn file, hostname và thông tin kết nối tùy event được bật.

Vì vậy:

- Lưu file ở thư mục có quyền truy cập hạn chế.
- Không đính kèm recording vào ticket công khai hoặc gửi qua kênh không được phê duyệt.
- Kiểm tra dữ liệu nhạy cảm trước khi chia sẻ cho vendor hoặc bên thứ ba.
- Xóa hoặc lưu trữ file theo retention policy của tổ chức.
- Ghi lại PID, vendor, JDK version, cấu hình .jfc, thời điểm bắt đầu/kết thúc và workload.
- Tính cả chi phí truyền file, lưu trữ bản sao và thời gian phân tích vào kế hoạch incident.

Một recording hữu ích phải trả lời được câu hỏi điều tra. Ghi nhiều dữ liệu hơn không tự động làm chẩn đoán tốt hơn; nó cũng làm tăng dung lượng, độ phức tạp và rủi ro lộ thông tin.

## 17. Tổng kết

JFR có thể được bật liên tục với overhead thấp khi dùng cấu hình phù hợp, nhưng chi phí thực tế vẫn phụ thuộc ứng dụng và event settings.

Những nguyên tắc cần nhớ:

- Dùng **default.jfc** cho continuous recording và đo overhead trên workload thật.
- Dùng **profile.jfc** trong khoảng thời gian giới hạn khi cần dữ liệu sâu hơn.
- Không bật Heap Statistics hoặc **path-to-gc-roots** tùy tiện vì chúng có thể tạo GC pause hoặc pause bổ sung.
- Giới hạn disk retention bằng **maxage** và **maxsize**.
- Giữ stack depth và thread buffer mặc định trừ khi có số liệu chứng minh cần thay đổi.
- Kiểm tra event count, dung lượng file và **jdk.DataLoss**.
- So sánh baseline, default và profile bằng throughput, p99 latency, CPU, GC pause và disk I/O.
- Bảo vệ recording như dữ liệu vận hành có thể chứa thông tin nhạy cảm.

**Tài liệu tham khảo chính thức:**

- [Oracle Java SE 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html)
- [Oracle Java SE 24 — Flight Recorder Overhead](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle Java SE 24 — The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [Oracle Java SE 24 — Recording API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java SE 24 — Flight Recorder Event Configuration](https://docs.oracle.com/en/java/javase/24/jfapi/configuration.html)
- [Oracle Java SE 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
