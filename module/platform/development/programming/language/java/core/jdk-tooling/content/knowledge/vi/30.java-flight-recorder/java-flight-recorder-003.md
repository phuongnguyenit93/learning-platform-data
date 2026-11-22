# Dừng Java Flight Recorder recording

## 1. Dừng recording có nghĩa là gì?

**Java Flight Recorder (JFR)** thu thập các sự kiện runtime của JVM vào một recording. Tùy cấu hình, dữ liệu có thể bao gồm CPU, thread, allocation, garbage collection (GC), class loading, I/O và các hoạt động khác.

Dừng recording là kết thúc việc thu thập dữ liệu cho một recording cụ thể. JVM và ứng dụng Java vẫn tiếp tục chạy bình thường.

Khi dừng, cần xác định dữ liệu sẽ được lưu thành file .jfr hay bị loại bỏ. Một lệnh dừng có thể kết thúc recording thành công nhưng không tạo file nếu không có đích lưu.

Với JVM đang chạy, cách phổ biến là dùng diagnostic command của jcmd:

~~~bash
jcmd <pid> JFR.stop name=<recording-name> filename=<path-to-file>
~~~

Tên recording và PID phải thuộc đúng JVM cần thao tác. Hãy kiểm tra trạng thái trước khi dừng để tránh kết thúc nhầm recording khác.

## 2. Phân biệt JFR.stop, JFR.dump và lệnh jfr

Ba thao tác có mục đích khác nhau:

| Công cụ/lệnh | Tác dụng |
|---|---|
| jcmd PID JFR.check | Xem các recording đang chạy và tên của chúng. |
| jcmd PID JFR.dump | Ghi một bản sao dữ liệu hiện có ra file; recording vẫn tiếp tục chạy. |
| jcmd PID JFR.stop | Dừng recording được chọn và hoàn tất việc lưu dữ liệu nếu có đích lưu. |
| jfr summary file.jfr | Đọc thông tin tổng quát của file recording đã tạo. |
| jfr print file.jfr | In các event trong file theo bộ lọc được chọn. |

**JFR.dump không dừng recording.** Nó tạo snapshot tại thời điểm dump để có thể xem dữ liệu trong khi quá trình thu thập vẫn tiếp tục. Dùng JFR.stop khi muốn kết thúc recording và chốt dữ liệu cuối cùng.

Công cụ dòng lệnh jfr xử lý các file recording. Trên JDK 24.0.2, jfr help không có lệnh jfr stop. Việc điều khiển recording đang chạy được thực hiện bằng jcmd hoặc Java Flight Recorder API.

## 3. Tìm PID và xác định recording đang chạy

Trước tiên, tìm JVM đích:

~~~bash
jcmd -l
~~~

Ví dụ:

~~~text
12345 com.example.orders.OrderApplication
~~~

Kiểm tra các recording đang hoạt động:

~~~bash
jcmd 12345 JFR.check
~~~

Ví dụ output:

~~~text
12345:
Recording 1: name=OrdersProfile maxsize=250.0MB (running)
Recording 2: name=ContinuousMonitoring maxage=1h maxsize=512.0MB (running)
~~~

Tên và ID trong ví dụ chỉ mang tính minh họa. JVM có thể chạy nhiều recording đồng thời, mỗi recording có tên và cấu hình riêng.

Có thể lọc theo tên:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile
~~~

In thêm event settings:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile verbose=true
~~~

Hãy lấy đúng tên từ output của JFR.start hoặc JFR.check. Không đoán tên recording và không dùng PID cũ khi process đã restart.

## 4. Xem cú pháp JFR.stop của JVM đích

Trước khi thực hiện, xem help của command:

~~~bash
jcmd 12345 help JFR.stop
~~~

Trên JDK 24.0.2, cú pháp là:

~~~text
JFR.stop [options]

filename  (Optional) Name of the file to which the recording is written
          when the recording is stopped.
name      Name of the recording.
~~~

Hai option:

- **name:** tên recording cần dừng. Đây là option cần có để chọn recording.
- **filename:** đường dẫn file .jfr nhận dữ liệu khi dừng; có thể truyền lúc JFR.stop hoặc cấu hình lúc JFR.start.

JFR.stop có Impact: Low trên JDK 24.0.2. Dù vậy, vẫn cần kiểm tra đúng PID, recording name và đích lưu trước khi chạy trên production.

Nếu gọi JFR.stop không có name, không có recording nào được chọn để dừng. Lệnh không có nghĩa là dừng tất cả recording.

## 5. Dừng recording và lưu file ngay tại thời điểm stop

Cách rõ ràng nhất là truyền cả tên và đường dẫn file:

~~~bash
jcmd 12345 JFR.stop name=OrdersProfile filename=C:\recordings\orders-profile.jfr
~~~

Ví dụ phản hồi:

~~~text
12345:
Stopped recording "OrdersProfile", 12.4 MB written to:

C:\recordings\orders-profile.jfr
~~~

Tên file, kích thước và PID thực tế sẽ khác nhau.

Khi command trả về thành công, JVM đã dừng recording được chọn và ghi dữ liệu cuối cùng vào file. Kiểm tra file tồn tại, kích thước lớn hơn 0 và có thể đọc được trước khi chuyển sang phân tích.

Đường dẫn đích phải tồn tại hoặc có thể được tạo theo quy tắc của môi trường, tài khoản chạy JVM phải có quyền ghi và ổ đĩa phải còn đủ dung lượng. Nên dùng đường dẫn tuyệt đối để tránh nhầm thư mục làm việc của process.

## 6. Cấu hình filename khi bắt đầu recording

Có thể đặt file đích ngay lúc start:

~~~bash
jcmd 12345 JFR.start name=OrdersProfile settings=default disk=true filename=C:\recordings\orders-profile.jfr
~~~

Sau đó kiểm tra:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile
~~~

Khi muốn kết thúc sớm:

~~~bash
jcmd 12345 JFR.stop name=OrdersProfile
~~~

Nếu filename đã được cấu hình lúc JFR.start, JFR.stop có thể dùng đích đó dù không truyền filename lần nữa. Hành vi này đã được kiểm tra trên JDK 24.0.2.

Cách này thuận tiện khi đã biết trước vị trí lưu. Nếu chưa đặt filename lúc start, hãy truyền filename ở lệnh stop để đảm bảo dữ liệu được lưu.

## 7. Điều gì xảy ra nếu không có filename?

JFR.stop có thể dừng recording mà không lưu dữ liệu thành file.

Quy tắc thực tế:

- Nếu filename đã được cấu hình lúc JFR.start, lệnh stop sẽ hoàn tất vào file đó.
- Nếu chưa cấu hình filename lúc start, có thể truyền filename ở JFR.stop.
- Nếu không có đích lưu ở cả hai thời điểm, dữ liệu recording bị loại bỏ khi dừng.

Ví dụ dừng và loại bỏ dữ liệu:

~~~bash
jcmd 12345 JFR.stop name=TemporaryCheck
~~~

Chỉ dùng cách này khi chủ động không cần giữ recording. Nếu cần điều tra sự cố hoặc bàn giao cho người khác, hãy lưu file trước khi dừng.

Trên JDK 24.0.2, thử nghiệm với recording không có filename lúc start và cũng không có filename lúc stop đã xác nhận JFR.stop trả về thành công nhưng không tạo file .jfr trong thư mục kiểm thử.

## 8. Dùng JFR.dump để lưu snapshot nhưng tiếp tục ghi

Có trường hợp cần xem dữ liệu hiện có ngay nhưng vẫn muốn recording tiếp tục thu thập. Khi đó dùng JFR.dump:

~~~bash
jcmd 12345 JFR.dump name=OrdersProfile filename=C:\recordings\orders-snapshot.jfr
~~~

Kiểm tra lại trạng thái:

~~~bash
jcmd 12345 JFR.check name=OrdersProfile
~~~

Recording vẫn ở trạng thái running sau JFR.dump. File snapshot chứa dữ liệu đã được ghi tới thời điểm dump; các event mới tiếp tục được thu thập vào recording đang chạy.

Sau khi đã có snapshot, có thể tiếp tục quan sát và dừng recording sau:

~~~bash
jcmd 12345 JFR.stop name=OrdersProfile filename=C:\recordings\orders-final.jfr
~~~

Nên dùng tên file khác nhau cho snapshot và file cuối để tránh ghi đè dữ liệu. Nếu không chỉ định name cho JFR.dump, command có thể dump dữ liệu từ tất cả recording; hãy chọn rõ tên recording khi JVM chạy nhiều recording.

## 9. Chọn thời điểm dừng recording

Dừng quá sớm có thể khiến file không chứa đủ dữ liệu để tái hiện vấn đề. Dừng quá muộn có thể làm file lớn hơn và tăng chi phí lưu trữ.

Một quy trình hợp lý:

1. Xác định sự kiện hoặc khoảng thời gian cần quan sát.
2. Kiểm tra recording name và settings.
3. Chờ cho tới khi hiện tượng cần điều tra đã xuất hiện.
4. Ghi lại thời điểm và bối cảnh workload.
5. Dừng recording và lưu file.
6. Xác nhận file đã hoàn tất trước khi phân tích.

Nếu biết trước thời gian thu thập, có thể cấu hình duration lúc start:

~~~bash
jcmd 12345 JFR.start name=ShortProfile settings=profile duration=5m filename=C:\recordings\short-profile.jfr
~~~

JVM sẽ tự kết thúc recording sau khoảng thời gian đã đặt. Nếu cần kết thúc sớm hơn, dùng JFR.stop với đúng tên recording.

## 10. Chọn settings và giới hạn dung lượng trước khi start

Việc dừng recording chỉ là một phần của quản lý vòng đời. Cấu hình lúc start ảnh hưởng kích thước file, loại event và overhead.

Hai cấu hình có sẵn thường dùng:

- **default:** thu thập bộ sự kiện cơ bản với overhead thấp, phù hợp recording chạy liên tục.
- **profile:** thu thập nhiều dữ liệu hơn, có overhead cao hơn; phù hợp cửa sổ điều tra ngắn khi cần thêm chi tiết.

Ví dụ:

~~~bash
jcmd 12345 JFR.start name=Continuous settings=default maxage=1h maxsize=512M filename=C:\recordings\continuous.jfr
~~~

~~~bash
jcmd 12345 JFR.start name=ShortProfile settings=profile maxsize=256M filename=C:\recordings\short-profile.jfr
~~~

Một số option liên quan:

| Option | Ý nghĩa |
|---|---|
| name | Đặt tên recording để kiểm tra, dump và stop. |
| settings | Chọn cấu hình event, ví dụ default hoặc profile. |
| filename | Đường dẫn file được dùng khi recording dừng. |
| duration | Thời gian ghi trước khi tự dừng. |
| delay | Chờ một khoảng thời gian trước khi bắt đầu. |
| maxage | Giới hạn tuổi dữ liệu giữ trên disk khi disk recording được bật. |
| maxsize | Giới hạn kích thước dữ liệu giữ trên disk. |
| dumponexit | Ghi recording ra file khi JVM shutdown. |
| disk | Bật ghi dữ liệu ra disk trong lúc recording chạy. |

JFR.start có Impact: Medium trên JDK 24.0.2 và impact thực tế phụ thuộc settings. Không mặc định dùng profile cho recording kéo dài nếu chưa đánh giá overhead.

## 11. Kiểm tra file sau khi dừng

Sau khi JFR.stop hoàn tất, kiểm tra file bằng jfr:

~~~bash
jfr summary C:\recordings\orders-profile.jfr
~~~

summary hiển thị:

- Phiên bản định dạng recording.
- Số chunk.
- Thời điểm bắt đầu và thời lượng.
- Số lượng event theo từng loại.
- Dung lượng event.

Nếu cần xem event cụ thể:

~~~bash
jfr print --events jdk.ExecutionSample C:\recordings\orders-profile.jfr
~~~

Có thể xem các event khác như GC, thread, allocation hoặc class loading bằng cách đổi event filter. Không phải event nào cũng có dữ liệu; kết quả phụ thuộc settings và hoạt động thực tế trong lúc recording.

Nếu file không đọc được, kiểm tra đường dẫn, kích thước và thông báo từ JFR.stop. Đảm bảo recording đã dừng và file đã được ghi hoàn tất trước khi phân tích.

## 12. Ví dụ hoàn chỉnh với jcmd

Tạo file **JfrStopProbe.java**:

~~~java
public class JfrStopProbe {
    public static void main(String[] args) throws Exception {
        System.out.println(
                "JfrStopProbe ready; pid=" + ProcessHandle.current().pid());

        long end = System.nanoTime() + 120_000_000_000L;
        long count = 0;

        while (System.nanoTime() < end) {
            byte[] payload = new byte[128 * 1024];
            payload[0] = (byte) count++;
            Thread.sleep(20);
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 JfrStopProbe.java
~~~

Chạy:

~~~bash
java JfrStopProbe
~~~

Ví dụ stdout:

~~~text
JfrStopProbe ready; pid=12345
~~~

Mở terminal thứ hai. Thay PID bằng giá trị thực tế và bắt đầu recording:

~~~bash
jcmd 12345 JFR.start name=StopPractice settings=default disk=true
~~~

Xem trạng thái:

~~~bash
jcmd 12345 JFR.check name=StopPractice
~~~

Dừng và lưu:

~~~bash
jcmd 12345 JFR.stop name=StopPractice filename=C:\recordings\stop-practice.jfr
~~~

Xác nhận file:

~~~bash
jfr summary C:\recordings\stop-practice.jfr
~~~

Trên JDK 24.0.2, JfrStopProbe đã được biên dịch bằng javac --release 17. JFR.start, JFR.check, JFR.dump và JFR.stop đều chạy thành công; file snapshot và file cuối đều được jfr summary đọc thành công.

Sau khi thực hành, dừng chương trình mẫu bằng Ctrl+C.

## 13. Dừng recording bằng Java Flight Recorder API

Ứng dụng cũng có thể tự quản lý recording bằng API trong module jdk.jfr.

Các bước chính:

- Tạo Recording với cấu hình event.
- Gọi start() để bắt đầu thu thập.
- Gọi stop() để kết thúc thu thập.
- Gọi dump(Path) để lưu dữ liệu đã thu thập.
- Đóng Recording để giải phóng tài nguyên.

Ví dụ Java 17+:

~~~java
import java.nio.file.Path;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class ProgrammaticJfrStop {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("programmatic-stop.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("ProgrammaticStop");
            recording.start();

            Thread.sleep(1500);

            recording.stop();
            recording.dump(output);

            System.out.println(
                    "Recording stopped and saved: " +
                    output.toAbsolutePath());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ProgrammaticJfrStop.java
java ProgrammaticJfrStop
~~~

Output có dạng:

~~~text
Recording stopped and saved: <absolute-path>\programmatic-stop.jfr
~~~

Đường dẫn tuyệt đối phụ thuộc thư mục chạy chương trình.

stop() kết thúc việc thu thập nhưng recording object vẫn còn dữ liệu để dump. dump(Path) ghi dữ liệu đó ra file. try-with-resources gọi close() khi thoát block để giải phóng tài nguyên. Nếu cần giữ dữ liệu, hãy dump trước khi đóng recording.

Ví dụ này đã được biên dịch và chạy trên JDK 24.0.2 bằng mã nguồn tương thích Java 17; file tạo ra đã được xác nhận bằng jfr summary.

## 14. Phân biệt stop recording với JVM shutdown

JFR.stop chỉ dừng recording được chọn. JFR.stop không dừng JVM, không restart JVM và không tắt ứng dụng.

Nó cũng không dừng các recording khác đang chạy. Nếu JVM có nhiều recording, từng recording phải được chọn theo tên.

Nếu JVM shutdown, các recording có dumponexit=true có thể được ghi ra file theo cấu hình. Đây là cơ chế lưu khi process kết thúc, khác với thao tác dừng một recording trong lúc JVM vẫn chạy.

Ví dụ cấu hình lưu khi JVM shutdown:

~~~bash
jcmd 12345 JFR.start name=ShutdownCapture settings=default dumponexit=true
~~~

Nếu muốn chốt dữ liệu ngay khi ứng dụng vẫn chạy, dùng JFR.stop. Nếu muốn giữ recording tới khi JVM shutdown, cấu hình dumponexit phù hợp và đảm bảo đường dẫn lưu có quyền ghi.

## 15. Quyền truy cập, đường dẫn và bảo mật file

jcmd cần attach vào JVM đích. Các điều kiện thường gặp:

- Chạy jcmd trên cùng máy với JVM.
- Dùng tài khoản có quyền attach vào process đích.
- Trên Unix, user và effective group cần phù hợp với process sở hữu JVM.
- Attach mechanism không bị vô hiệu hóa.
- Trong container, chạy từ đúng PID namespace và môi trường có thể nhìn thấy JVM.

Đường dẫn file phải có thể ghi bởi process JVM. Một terminal có quyền ghi vào thư mục không đảm bảo JVM chạy dưới tài khoản khác cũng có quyền đó.

Áp dụng nguyên tắc least privilege: chỉ cấp quyền attach và quyền đọc recording cho người thực sự cần chẩn đoán process đó.

JFR file có thể chứa tên thread, class, stack trace, đường dẫn file, thông tin I/O và dữ liệu vận hành khác tùy event settings. Hãy xem file recording là dữ liệu chẩn đoán nhạy cảm:

- Lưu trong thư mục giới hạn quyền truy cập.
- Không đính kèm file thô vào ticket hoặc nơi công khai nếu chưa được phép.
- Xóa hoặc lưu trữ theo chính sách retention.
- Không ghi đè file quan trọng bằng một recording khác.
- Kiểm tra dung lượng đĩa trước khi dump recording lớn.

## 16. Lỗi thường gặp khi dừng recording

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jcmd không tìm thấy PID | PID sai hoặc JVM đã kết thúc. | Chạy jcmd -l và xác minh lại process. |
| Không tìm thấy recording | Sai tên, recording đã dừng hoặc tên được tạo tự động. | Chạy JFR.check và dùng đúng name. |
| JFR.stop không dừng recording mong muốn | Đã chọn nhầm recording hoặc bỏ qua option name. | Kiểm tra danh sách rồi chỉ rõ name. |
| JFR.stop thành công nhưng không có file | Không cấu hình filename lúc start hoặc stop. | Truyền filename ở JFR.stop hoặc đặt filename lúc JFR.start. |
| Permission denied khi lưu | JVM user không có quyền ghi thư mục đích. | Chọn thư mục mà tài khoản JVM được phép ghi. |
| File .jfr rỗng hoặc không đọc được | Dump chưa hoàn tất, file bị gián đoạn hoặc sai đường dẫn. | Xác nhận thông báo stop, kiểm tra kích thước và chạy jfr summary. |
| JFR.dump xong nhưng recording vẫn chạy | Đây là hành vi đúng: dump chỉ tạo snapshot. | Dùng JFR.stop khi cần kết thúc recording. |
| File quá lớn | Recording kéo dài, profile settings hoặc giới hạn dung lượng chưa phù hợp. | Đặt duration, maxage, maxsize và chọn settings phù hợp. |
| Attach failure | Khác user, namespace hoặc Attach mechanism bị tắt. | Kiểm tra process owner, container và cấu hình JVM. |
| jfr báo unknown command stop | Đang dùng jfr CLI để điều khiển live recording. | Dùng jcmd PID JFR.stop; jfr dùng để đọc và xử lý file. |
| Recording dừng nhưng dữ liệu không đủ | Dừng trước khi hiện tượng cần điều tra xuất hiện. | Kiểm tra thời lượng, event settings và bối cảnh workload. |

## 17. Quy trình vận hành an toàn

Trước khi dừng recording trên môi trường thật:

1. Xác định JVM và PID mới nhất.
2. Chạy JFR.check để xem tên và trạng thái recording.
3. Chọn đúng recording theo mục tiêu điều tra.
4. Xác định filename đã được đặt lúc start hay chưa.
5. Kiểm tra quyền ghi và dung lượng đĩa.
6. Nếu cần snapshot mà vẫn tiếp tục thu thập, dùng JFR.dump.
7. Nếu cần kết thúc, dùng JFR.stop với đúng name và filename.
8. Đọc phản hồi của jcmd để xác nhận recording đã dừng và dữ liệu đã ghi.
9. Chạy jfr summary để kiểm tra file.
10. Lưu file theo chính sách truy cập và retention.
11. Chỉ sau khi xác nhận dữ liệu đã được bảo toàn mới kết thúc phiên điều tra.

Nếu JVM đang chạy nhiều recording, dừng từng recording theo tên đã xác minh. Không giả định một lệnh JFR.stop sẽ dừng tất cả.

## 18. Checklist trước khi kết thúc recording

- [ ] Đã xác định đúng PID của JVM.
- [ ] Đã chạy JFR.check và xác nhận tên recording.
- [ ] Đã chọn đúng recording cần dừng.
- [ ] Đã kiểm tra filename được cấu hình lúc start hoặc sẽ truyền lúc stop.
- [ ] Đã xác nhận thư mục đích có quyền ghi và đủ dung lượng.
- [ ] Đã phân biệt JFR.dump với JFR.stop.
- [ ] Đã hiểu rằng stop không dừng JVM hoặc các recording khác.
- [ ] Đã xem phản hồi thành công từ jcmd.
- [ ] Đã xác nhận file .jfr tồn tại và có kích thước hợp lý.
- [ ] Đã chạy jfr summary để xác nhận file đọc được.
- [ ] Đã bảo vệ file recording như dữ liệu chẩn đoán nhạy cảm.
- [ ] Đã kiểm tra rằng không còn recording ngoài ý muốn tiếp tục chạy.

## 19. Tài liệu tham khảo

- Oracle JDK 24 — The jcmd Command, các lệnh JFR.start, JFR.check, JFR.dump và JFR.stop: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — Diagnostic Tools, phần Java Flight Recorder: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Java SE 24 API — jdk.jfr.Recording: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html

Dừng recording đúng cách gồm ba việc: xác nhận đúng recording, chọn rõ nơi lưu dữ liệu và kiểm tra file sau khi kết thúc. Dùng JFR.check để nhận diện, JFR.stop để kết thúc, JFR.dump để lấy snapshot trong lúc tiếp tục ghi và jfr summary để xác nhận file đã sẵn sàng cho phân tích.