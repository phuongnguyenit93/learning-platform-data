# Dump file JFR trong Java Flight Recorder

**Java Flight Recorder (JFR)** là hệ thống ghi nhận sự kiện của JVM và ứng dụng Java theo dòng thời gian. Một **JFR dump file** là tệp recording có phần mở rộng \`.jfr\`, chứa các event được thu thập trong một khoảng thời gian. Có thể dùng tệp này để phân tích CPU, garbage collection, allocation, thread, lock contention, class loading, I/O và các sự kiện do ứng dụng tự định nghĩa.

JFR dump thường được tạo khi cần điều tra một sự cố đã xảy ra hoặc lưu lại dữ liệu để phân tích sau. Tệp \`.jfr\` là dữ liệu nhị phân, không phải văn bản thuần; dùng lệnh \`jfr\` hoặc Java Mission Control (JMC) để đọc và phân tích.

## 1. JFR dump file là gì?

Một JFR recording thu thập các sự kiện có cấu trúc. Mỗi event có thể chứa:

- Thời điểm xảy ra và thời lượng nếu event đo một thao tác kéo dài.
- Loại event và các trường dữ liệu đặc trưng.
- Thread phát sinh event.
- Stack trace tại vị trí event được ghi, nếu cấu hình bật.
- Metadata mô tả event, field, kiểu dữ liệu và category.

Ví dụ, một recording có thể lưu các event về garbage collection, CPU load, object allocation, thread park, monitor contention, file I/O, socket I/O, exception và custom event do ứng dụng tạo.

Tệp \`.jfr\` thường chứa metadata và một hoặc nhiều data chunk. Chunk là đơn vị dữ liệu nội bộ của recording; công cụ JFR dùng chúng để đọc, tóm tắt, lọc hoặc ghép recording. Không chỉnh sửa file bằng text editor hoặc tự thay byte trong file.

## 2. Phân biệt recording, dump file và heap dump

Ba khái niệm thường bị nhầm:

| Khái niệm | Nội dung | Dùng khi nào |
|---|---|---|
| JFR recording | Quá trình JVM đang thu thập event. | Theo dõi JVM trong một khoảng thời gian. |
| JFR dump file (\`.jfr\`) | Bản ghi event đã được ghi ra file để lưu trữ và phân tích. | Điều tra hiệu năng, GC, thread, allocation và sự kiện runtime. |
| Heap dump (\`.hprof\`) | Ảnh chụp object graph trong heap tại một thời điểm. | Tìm object đang được giữ, retained size và nguyên nhân memory leak. |

JFR không phải heap dump. Recording có thể chứa thông tin về allocation và object sampling, nhưng không phải bản sao đầy đủ của mọi object đang tồn tại trong heap. Nếu cần xem object nào giữ reference tới object khác, hãy lấy heap dump và phân tích bằng công cụ phù hợp.

Thread dump cũng khác JFR: thread dump là ảnh chụp stack/state tại một thời điểm; JFR lưu nhiều event theo thời gian nên hữu ích để thấy diễn biến trước, trong và sau sự cố.

## 3. Khi nào cần tạo JFR dump?

JFR phù hợp khi cần trả lời những câu hỏi có yếu tố thời gian:

- Method hoặc thread nào tiêu thụ CPU nhiều?
- Garbage collection xảy ra lúc nào, pause kéo dài bao lâu?
- Allocation tăng ở class hoặc call site nào?
- Thread nào chờ monitor hoặc synchronizer lâu?
- Có nhiều exception, class loading hoặc deoptimization bất thường không?
- File read/write hoặc socket read/write nào có latency cao?
- Ứng dụng bắt đầu chậm từ thời điểm nào?
- Custom event của ứng dụng cho thấy bước nghiệp vụ nào kéo dài?

JFR thường được dùng trong hai tình huống:

1. **Time-fixed recording:** ghi trong một khoảng thời gian xác định để tái hiện hoặc đo một workload.
2. **Continuous recording:** duy trì recording với giới hạn dung lượng/thời gian, sau đó dump phần dữ liệu cần xem khi có sự cố.

JFR có overhead thấp trong cấu hình mặc định phù hợp, nhưng không phải bằng không. Cấu hình nhiều event, stack trace sâu hoặc threshold quá thấp có thể làm tăng CPU, bộ nhớ và dung lượng file.

## 4. Cấu hình default.jfc và profile.jfc

JDK cung cấp các mẫu cấu hình trong thư mục \`JAVA_HOME/lib/jfr\`:

| Mẫu | Đặc điểm | Cách dùng |
|---|---|---|
| \`default.jfc\` | Thu thập tập event được chọn với overhead thấp. | Recording chạy lâu hoặc liên tục. |
| \`profile.jfc\` | Thu thập nhiều dữ liệu hơn, thường có thêm thông tin profiling. | Recording ngắn khi cần phân tích sâu hơn. |

Khi bắt đầu recording bằng \`jcmd\`, có thể chọn:

~~~bash
jcmd <pid> JFR.start name=baseline settings=default
jcmd <pid> JFR.start name=profile-run settings=profile
~~~

Tên cấu hình có thể được truyền dưới dạng tên file hoặc đường dẫn tới file \`.jfc\` tùy môi trường. Kiểm tra \`JAVA_HOME/lib/jfr\` trên JDK đang chạy để biết các cấu hình có sẵn.

Không mặc định bật mọi event. Event có stack trace hoặc threshold rất thấp có thể tạo nhiều dữ liệu và tăng overhead. Chọn cấu hình dựa trên câu hỏi cần điều tra.

## 5. Vòng đời của một recording

Một recording thường đi qua các bước:

1. Tìm PID của JVM cần theo dõi.
2. Bắt đầu recording với cấu hình event phù hợp.
3. Kiểm tra recording có đang chạy hay không.
4. Dump snapshot ra file khi cần lưu dữ liệu hiện tại.
5. Tiếp tục recording nếu vẫn cần thu thập thêm.
6. Stop recording để kết thúc và lưu file cuối.
7. Phân tích file bằng \`jfr\` hoặc JMC.

Các diagnostic command của JFR được gửi qua \`jcmd\`. Công cụ \`jcmd\` phải chạy trên cùng máy với JVM đích và thường cần cùng effective user/group đã khởi chạy JVM đó.

Tìm JVM:

~~~bash
jcmd -l
~~~

Hoặc:

~~~bash
jps -l
~~~

Sau khi có PID, dùng các lệnh JFR với đúng tiến trình đó.

## 6. Bắt đầu recording bằng jcmd JFR.start

Ví dụ bắt đầu recording có tên \`incident\`:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile
~~~

Có thể đặt giới hạn dung lượng và thời gian lưu trên disk:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile disk=true maxage=30m maxsize=512M
~~~

Các tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
|---|---|
| \`name\` | Tên recording để tham chiếu trong các lệnh tiếp theo. |
| \`settings\` | File/cấu hình event, thường là \`default\` hoặc \`profile\`. |
| \`disk\` | Ghi dữ liệu recording xuống disk trong khi thu thập. |
| \`duration\` | Thời lượng recording; \`0s\` có nghĩa là chạy cho tới khi stop. |
| \`delay\` | Khoảng chờ trước khi bắt đầu recording. |
| \`filename\` | File đích được ghi khi recording kết thúc. |
| \`dumponexit\` | Ghi recording ra file khi JVM shutdown. |
| \`maxage\` | Giới hạn thời gian dữ liệu được giữ trên disk. |
| \`maxsize\` | Giới hạn dung lượng dữ liệu được giữ trên disk. |
| \`path-to-gc-roots\` | Thu thập đường dẫn tới GC roots khi recording kết thúc; có thể làm ứng dụng pause. |

Ví dụ recording tự kết thúc sau 5 phút:

~~~bash
jcmd <pid> JFR.start name=short-profile settings=profile duration=5m filename=short-profile.jfr
~~~

Ví dụ bật lưu khi JVM shutdown:

~~~bash
jcmd <pid> JFR.start name=shutdown-capture settings=default dumponexit=true
~~~

Nếu cần kiểm tra option cụ thể, dùng:

~~~bash
jcmd <pid> help JFR.start
~~~

## 7. Kiểm tra recording bằng JFR.check

Liệt kê recording đang chạy:

~~~bash
jcmd <pid> JFR.check
~~~

Xem một recording theo tên:

~~~bash
jcmd <pid> JFR.check name=incident
~~~

Hiển thị thêm event settings:

~~~bash
jcmd <pid> JFR.check name=incident verbose=true
~~~

Output thường cho biết recording ID, tên, trạng thái running/stopped, max age, max size và cấu hình event nếu bật verbose. Ghi lại tên hoặc ID được trả về để dùng đúng recording khi dump hoặc stop.

Nếu không có recording mang tên đã nhập, kiểm tra lại PID, tên và trạng thái JVM trước khi thực hiện lệnh tiếp theo.

## 8. Tạo snapshot bằng JFR.dump

\`JFR.dump\` ghi dữ liệu hiện có của recording ra một file \`.jfr\`:

~~~bash
jcmd <pid> JFR.dump name=incident filename=incident-snapshot.jfr
~~~

Điểm quan trọng: **JFR.dump không kết thúc recording**. Sau khi snapshot được ghi, recording vẫn tiếp tục chạy và có thể dump thêm lần nữa.

Có thể dùng nhiều snapshot theo thời điểm:

~~~bash
jcmd <pid> JFR.dump name=incident filename=incident-01.jfr
jcmd <pid> JFR.dump name=incident filename=incident-02.jfr
~~~

Các snapshot giúp so sánh dữ liệu thu thập ở những thời điểm khác nhau. Đặt tên file có timestamp hoặc mã incident để tránh ghi đè nhầm file cũ.

JFR.dump có thể chọn một khoảng thời gian hoặc giới hạn dữ liệu bằng các option như \`begin\`, \`end\`, \`maxage\` và \`maxsize\`. Ví dụ lấy dữ liệu gần đây:

~~~bash
jcmd <pid> JFR.dump name=incident maxage=15m filename=last-15-minutes.jfr
~~~

Giá trị thời gian có thể dùng đơn vị giây, phút hoặc giờ. Đọc \`jcmd <pid> help JFR.dump\` trên đúng JDK để xác nhận option và định dạng timestamp được hỗ trợ.

## 9. Kết thúc recording bằng JFR.stop

Khi đã thu đủ dữ liệu, dừng recording:

~~~bash
jcmd <pid> JFR.stop name=incident filename=incident-final.jfr
~~~

Lệnh này kết thúc recording và ghi phần dữ liệu cuối cùng ra file đích. Sau đó recording không còn ở trạng thái running.

Kiểm tra:

~~~bash
jcmd <pid> JFR.check
~~~

Không dùng \`JFR.stop\` chỉ vì vừa tạo snapshot bằng \`JFR.dump\`; hai lệnh có mục đích khác nhau. Dùng dump để lấy bản sao trong lúc tiếp tục ghi, dùng stop khi đã hoàn tất thu thập.

## 10. Recording liên tục và quản lý dung lượng

Continuous recording hữu ích khi sự cố xuất hiện không theo lịch. Có thể duy trì recording với cấu hình \`default\` và giới hạn dung lượng/thời gian:

~~~bash
jcmd <pid> JFR.start name=continuous settings=default disk=true maxage=2h maxsize=1G
~~~

- \`maxage\` giới hạn tuổi dữ liệu được giữ.
- \`maxsize\` giới hạn dung lượng dữ liệu trên disk.
- Khi giới hạn được áp dụng, dữ liệu cũ có thể bị loại bỏ để duy trì cửa sổ ghi gần đây.
- \`disk=true\` cho phép dữ liệu recording được ghi xuống disk trong lúc thu thập.

Nếu không giới hạn dữ liệu, recording kéo dài có thể chiếm nhiều dung lượng. Hãy đặt giới hạn dựa trên event rate, dung lượng lưu trữ và thời gian cần giữ lịch sử.

Không đặt maxsize quá nhỏ so với kích thước chunk tối đa được cấu hình trong JFR. Xem \`jcmd <pid> JFR.configure\` để kiểm tra \`maxchunksize\`, repository path và các thông số liên quan.

## 11. JFR repository và nơi lưu recording

Trong lúc recording, JFR có thể ghi các chunk vào disk repository tạm thời. Repository không phải file dump cuối cùng mà người phân tích thường gửi hoặc mở bằng JMC.

Một số cấu hình JFR:

- \`repositorypath\`: vị trí lưu chunk tạm.
- \`dumppath\`: vị trí ghi recording khi JVM gặp lỗi nghiêm trọng.
- \`preserve-repository\`: quyết định có giữ repository sau khi JVM thoát hay không.
- \`memorysize\`: tổng bộ nhớ buffer JFR.
- \`maxchunksize\`: kích thước tối đa của một chunk.
- \`stackdepth\`: độ sâu stack trace được ghi.

Xem cấu hình:

~~~bash
jcmd <pid> JFR.configure
~~~

Đặt repository path:

~~~bash
jcmd <pid> JFR.configure repositorypath=/var/tmp/jfr-repository
~~~

Các tham số như memory size, max chunk size và stack depth có giới hạn thay đổi sau khi JFR đã được khởi tạo. Không tùy tiện thay đổi buffer hoặc thread buffer trong production vì có thể ảnh hưởng hiệu năng.

Nếu JVM crash và chỉ còn repository chunk, công cụ \`jfr assemble\` có thể ghép các chunk còn lại thành recording khi repository được bảo toàn và dữ liệu còn hợp lệ.

## 12. Đọc tổng quan file bằng jfr summary

Sau khi có file, kiểm tra tính hợp lệ và nội dung tổng quan:

~~~bash
jfr summary incident-final.jfr
~~~

Lệnh hiển thị:

- Phiên bản định dạng recording.
- Số chunk.
- Thời điểm bắt đầu và thời lượng.
- Danh sách event type.
- Số lượng event theo loại.
- Kích thước dữ liệu của từng loại event.

Ví dụ, nếu file có nhiều event \`jdk.GarbageCollection\`, \`jdk.ObjectAllocationSample\` hoặc \`jdk.JavaMonitorEnter\`, có thể lọc các event đó để điều tra GC, allocation hoặc lock contention.

\`jfr summary\` là bước kiểm tra nhanh trước khi phân tích sâu. Nếu file rỗng, hỏng hoặc không có event cần thiết, kiểm tra lại recording settings và thời điểm bắt đầu/kết thúc.

## 13. In event bằng jfr print

Dùng \`jfr print\` để đọc event dưới dạng văn bản:

~~~bash
jfr print incident-final.jfr
~~~

Nên lọc theo event để giảm output:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause incident-final.jfr
~~~

Lọc theo category:

~~~bash
jfr print --categories "GC,JVM,Java*" incident-final.jfr
~~~

Giới hạn stack trace:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 incident-final.jfr
~~~

Xuất JSON:

~~~bash
jfr print --json --events jdk.GarbageCollection incident-final.jfr
~~~

Xuất XML:

~~~bash
jfr print --xml --events jdk.GarbageCollection incident-final.jfr
~~~

JSON/XML hữu ích khi cần xử lý tiếp bằng script. Định dạng hiển thị phụ thuộc phiên bản JDK và metadata của event; tránh giả định mọi JFR file có cùng field.

## 14. Tổng hợp bằng jfr view

\`jfr view\` hiển thị dữ liệu event dưới dạng bảng tổng hợp. Một số view thường dùng:

| View | Mục đích |
|---|---|
| \`hot-methods\` | Xem method xuất hiện nhiều trong các sample. |
| \`gc-pauses\` | Phân tích các pause liên quan GC. |
| \`allocation-by-class\` | Xem allocation theo class. |
| \`allocation-by-site\` | Xem allocation theo vị trí code. |
| \`contention-by-class\` | Tổng hợp contention theo class. |
| \`thread-cpu-load\` | Quan sát CPU load theo thread. |
| \`file-reads-by-path\` | Tổng hợp file read theo đường dẫn. |
| \`socket-reads-by-host\` | Tổng hợp socket read theo host. |

Ví dụ:

~~~bash
jfr view hot-methods incident-final.jfr
jfr view gc-pauses incident-final.jfr
jfr view allocation-by-class incident-final.jfr
~~~

Tên view có sẵn phụ thuộc JDK. Dùng \`jfr help view\` hoặc \`jfr view all-views <file>\` để xem danh sách của phiên bản đang dùng.

## 15. Xem metadata và tùy chỉnh event bằng JFR

Metadata mô tả event type và field:

~~~bash
jfr metadata incident-final.jfr
~~~

Lọc metadata theo event:

~~~bash
jfr metadata --events jdk.GarbageCollection incident-final.jfr
~~~

JFR dùng file cấu hình \`.jfc\` để xác định event nào được bật, threshold, stack trace và các option liên quan.

Tạo cấu hình tùy chỉnh từ mẫu profile:

~~~bash
jfr configure --input profile.jfc --output custom.jfc
~~~

Có thể chỉnh event setting, ví dụ:

~~~bash
jfr configure --input profile.jfc --output custom.jfc jdk.JavaMonitorEnter#threshold=10ms
~~~

Sau đó bắt đầu recording với file cấu hình:

~~~bash
jcmd <pid> JFR.start name=custom-profile settings=custom.jfc
~~~

Cấu hình event cần bám theo câu hỏi cần điều tra. Bật quá nhiều event hoặc đặt threshold quá thấp có thể làm tăng dung lượng file và overhead.

## 16. Lọc dữ liệu trước khi chia sẻ bằng jfr scrub

JFR file có thể chứa thông tin nội bộ như environment variables, system properties, đường dẫn file, tên thread, hostname, command line hoặc stack trace. Trước khi gửi file ra ngoài nhóm, hãy kiểm tra nội dung và loại bỏ event không cần thiết.

\`jfr scrub\` tạo một recording mới sau khi lọc event, category hoặc thread:

~~~bash
jfr scrub --exclude-events jdk.InitialEnvironmentVariable,jdk.InitialSystemProperty incident-final.jfr incident-scrubbed.jfr
~~~

Chỉ giữ một nhóm event:

~~~bash
jfr scrub --include-events jdk.GarbageCollection,jdk.ExecutionSample incident-final.jfr focused.jfr
~~~

Loại một category:

~~~bash
jfr scrub --exclude-categories OS incident-final.jfr no-os-events.jfr
~~~

Lọc theo thread:

~~~bash
jfr scrub --include-threads main incident-final.jfr main-thread-only.jfr
~~~

Scrub tạo file đầu ra đã lọc; giữ bản gốc trong vùng lưu trữ có kiểm soát nếu còn cần phân tích đầy đủ. Scrub không thay thế việc rà soát thủ công các dữ liệu nhạy cảm còn lại.

## 17. Ghép và chia nhỏ recording

Một recording có thể gồm nhiều chunk. Các lệnh nâng cao:

~~~bash
jfr assemble <repository> assembled.jfr
~~~

Dùng \`assemble\` để ghép các chunk còn lại trong disk repository thành file recording.

Chia recording lớn thành các file nhỏ hơn:

~~~bash
jfr disassemble --output chunks incident-final.jfr
~~~

Có thể điều chỉnh số chunk hoặc dung lượng tối đa mỗi file:

~~~bash
jfr disassemble --max-chunks 2 --output chunks incident-final.jfr
~~~

\`disassemble\` chỉ hữu ích khi recording có đủ chunk để chia. File nhỏ chỉ có một chunk có thể không cần hoặc không thể chia theo giới hạn mặc định. Dùng \`jfr help assemble\` và \`jfr help disassemble\` để xem cú pháp của đúng JDK.

## 18. Phân tích bằng Java Mission Control

Java Mission Control (JMC) là giao diện đồ họa hỗ trợ phân tích JFR recording. Mở file \`.jfr\` bằng JMC để xem các trang tổng hợp và drill down vào event.

Một quy trình thường dùng:

1. Mở recording trong JMC.
2. Xem overview để nhận biết CPU, heap, GC và thread.
3. Mở phần Java Application để xem hot methods, allocation và lock contention.
4. Mở Garbage Collections để xem pause, collector và heap usage.
5. Mở Threads để điều tra thread sample, park và monitor wait.
6. Mở I/O để xem file/socket event.
7. Chọn event hoặc khoảng thời gian để xem stack trace và field chi tiết.

JMC phù hợp khi cần tương tác với dữ liệu lớn và liên kết nhiều event. CLI \`jfr\` phù hợp để kiểm tra nhanh, lọc event và tự động hóa một số bước xử lý.

## 19. Tạo JFR dump bằng Java Flight Recorder API

Ứng dụng có thể tạo recording trực tiếp bằng API trong module \`jdk.jfr\`. Cách này hữu ích khi muốn kiểm soát thời điểm bắt đầu/kết thúc, thêm custom event hoặc gắn recording vào một workflow kiểm thử.

Ví dụ dưới đây tạo event \`demo.Work\` và ghi 10 lần xử lý batch vào file.

Tệp \`src/com/acme/WorkEvent.java\`:

~~~java
package com.acme;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.Work")
@Label("Demo Work")
@Category({"Demo", "JFR"})
class WorkEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Item Count")
    int itemCount;
}
~~~

Tệp \`src/com/acme/JfrDumpDemo.java\`:

~~~java
package com.acme;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class JfrDumpDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of(args[0]);

        try (Recording recording =
                new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("jfr-dump-demo");
            recording.setToDisk(true);
            recording.enable(WorkEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();

            recording.start();

            for (int i = 1; i <= 10; i++) {
                WorkEvent event = new WorkEvent();
                event.operation = "process-batch";
                event.itemCount = i * 10;

                event.begin();
                Thread.sleep(25);
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(output);
            System.out.println("JFR_DUMP_CREATED=" + output.getFileName());
        }
    }
}
~~~

Event class có tên \`WorkEvent\`, nhưng metadata đăng ký event với tên \`demo.Work\`. Hai field \`operation\` và \`itemCount\` được lưu cùng thời điểm, thời lượng, thread và stack trace nếu event setting bật stack trace.

## 20. Biên dịch và chạy ví dụ Java 17+

Từ thư mục gốc dự án:

~~~bash
javac --release 17 -d out \
  src/com/acme/WorkEvent.java \
  src/com/acme/JfrDumpDemo.java
~~~

Chạy chương trình và chỉ định file đích:

~~~bash
java -cp out com.acme.JfrDumpDemo demo-recording.jfr
~~~

Stdout chính xác:

~~~text
JFR_DUMP_CREATED=demo-recording.jfr
~~~

Kiểm tra file:

~~~bash
jfr summary demo-recording.jfr
~~~

In custom event:

~~~bash
jfr print --events demo.Work demo-recording.jfr
~~~

Xem bảng event:

~~~bash
jfr view demo.Work demo-recording.jfr
~~~

Xem metadata:

~~~bash
jfr metadata --events demo.Work demo-recording.jfr
~~~

Trong lần kiểm thử trên Azul OpenJDK 24.0.2, chương trình biên dịch bằng \`javac --release 17\`, tạo file \`demo-recording.jfr\` và ghi đúng 10 event \`demo.Work\`. Lệnh \`jfr print\` hiển thị operation \`process-batch\`, các giá trị itemCount từ 10 đến 100 và stack trace tại \`JfrDumpDemo.main\`.

## 21. Ví dụ workflow đầy đủ cho JVM đang chạy

Giả sử ứng dụng Java đã chạy và bạn muốn ghi dữ liệu trong lúc tái hiện sự cố.

Tìm PID:

~~~bash
jcmd -l
~~~

Bắt đầu recording:

~~~bash
jcmd 12345 JFR.start name=incident settings=profile disk=true maxage=30m maxsize=512M
~~~

Kiểm tra:

~~~bash
jcmd 12345 JFR.check name=incident
~~~

Khi sự cố đang xảy ra, tạo snapshot:

~~~bash
jcmd 12345 JFR.dump name=incident filename=incident-snapshot.jfr
~~~

Recording vẫn tiếp tục. Nếu cần theo dõi thêm, chờ thêm một khoảng thời gian rồi dump snapshot thứ hai. Khi đã thu đủ:

~~~bash
jcmd 12345 JFR.stop name=incident filename=incident-final.jfr
~~~

Phân tích:

~~~bash
jfr summary incident-snapshot.jfr
jfr view hot-methods incident-snapshot.jfr
jfr view gc-pauses incident-snapshot.jfr
jfr print --events jdk.GarbageCollection incident-final.jfr
~~~

PID \`12345\` chỉ là ví dụ; thay bằng PID thực tế. Nếu recording đã tự dừng theo duration hoặc JVM shutdown, kiểm tra file đích và trạng thái trước khi gọi stop lần nữa.

## 22. Bảo mật và bảo vệ JFR dump file

JFR file có thể chứa dữ liệu nhạy cảm từ môi trường và ứng dụng. Trước khi chia sẻ:

- Kiểm tra event \`jdk.InitialEnvironmentVariable\` và \`jdk.InitialSystemProperty\`.
- Rà soát đường dẫn file, hostname, command line và tên thread.
- Kiểm tra custom event có vô tình ghi token, user data hoặc payload nghiệp vụ không.
- Giới hạn quyền đọc file và thư mục lưu trữ.
- Mã hóa file khi lưu hoặc truyền qua hệ thống có hỗ trợ.
- Dùng \`jfr scrub\` để loại bỏ event không cần thiết trước khi gửi.
- Giữ bản gốc trong vùng lưu trữ nội bộ nếu cần điều tra tiếp.

Không ghi password, access token, session ID hoặc dữ liệu cá nhân vào custom event. Stack trace và system properties cũng có thể tiết lộ tên package, thư mục triển khai hoặc cấu hình nội bộ.

## 23. Overhead, giới hạn và khả năng tương thích

JFR được thiết kế cho profiling và troubleshooting với overhead thấp trong cấu hình phù hợp, nhưng mức ảnh hưởng phụ thuộc event settings và workload.

Một số lưu ý:

- \`default.jfc\` thường phù hợp cho recording dài; \`profile.jfc\` thu thập nhiều thông tin hơn và thường dành cho khoảng thời gian ngắn hơn.
- Bật stack trace cho nhiều event có thể tăng dung lượng và CPU.
- Recording disk cần dung lượng tạm và file đích đủ lớn.
- \`path-to-gc-roots\` có thể làm ứng dụng pause; chỉ bật khi nghi ngờ memory leak.
- JFR file là binary format; dùng JDK/JMC tương thích để phân tích.
- Event type và field có thể khác theo JDK, vendor, collector và cấu hình.
- Một recording không tự kết luận nguyên nhân gốc; cần đối chiếu với logs, metrics, request traces và bối cảnh workload.
- \`jcmd\` cần chạy trên cùng máy và tài khoản có quyền attach tới JVM đích.
- Trong container, cần xác định PID đúng namespace và chạy công cụ từ môi trường có thể nhìn thấy process.

JFR dump thường cho biết điều gì xảy ra trong JVM, nhưng không thay thế phân tích heap object graph, network trace hoặc distributed tracing khi vấn đề nằm ngoài phạm vi event đã thu thập.

## 24. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| \`jcmd\` không tìm thấy JVM | Sai PID, khác user, JVM ở container namespace khác hoặc attach bị tắt. | Dùng \`jcmd -l\`, xác minh user/PID và kiểm tra môi trường container. |
| \`JFR.start\` báo recording đã tồn tại | Đã có recording trùng tên hoặc đang chạy. | Dùng \`JFR.check\`, chọn tên khác hoặc stop recording cũ nếu đã xác nhận không cần. |
| Không tạo được file dump | Sai đường dẫn, thiếu quyền ghi hoặc ổ đĩa đầy. | Chọn thư mục có quyền ghi, kiểm tra dung lượng và đường dẫn. |
| File \`.jfr\` có dung lượng rất nhỏ | Recording quá ngắn, event settings không bật event cần thiết hoặc workload chưa phát sinh event. | Kiểm tra \`JFR.check verbose=true\`, settings và thời gian thu thập. |
| \`jfr summary\` không đọc được file | File bị cắt, chưa hoàn tất ghi hoặc không phải JFR recording hợp lệ. | Kiểm tra lệnh dump/stop, file size và thử lại với file đã ghi hoàn chỉnh. |
| Không thấy event mong đợi | Event bị tắt, threshold quá cao hoặc không xảy ra trong thời gian recording. | Kiểm tra \`.jfc\`, metadata và event setting; kéo dài recording nếu phù hợp. |
| Recording chiếm nhiều dung lượng | Profile quá chi tiết, event rate cao hoặc không đặt giới hạn. | Chọn default settings, đặt maxage/maxsize và lọc event cần thiết. |
| JMC không mở được file | File không hoàn chỉnh hoặc phiên bản JMC không hỗ trợ định dạng recording. | Xác minh bằng \`jfr summary\`, dùng JMC/JDK phù hợp và tạo lại dump nếu cần. |
| File có dữ liệu nhạy cảm | Event ghi environment, system properties hoặc thông tin ứng dụng. | Không chia sẻ bản gốc; scrub và rà soát file đầu ra. |

## 25. Quy trình làm việc khuyến nghị

Khi nhận một sự cố hiệu năng Java:

1. Xác định JVM, PID và user sở hữu process.
2. Chọn \`default\` cho quan sát dài hoặc \`profile\` cho profiling ngắn.
3. Bắt đầu recording có tên rõ ràng và giới hạn maxage/maxsize.
4. Dùng \`JFR.check\` để xác nhận recording đang chạy.
5. Tái hiện workload hoặc chờ sự cố xảy ra.
6. Dùng \`JFR.dump\` để chụp snapshot mà không dừng recording.
7. Khi đã thu đủ dữ liệu, dùng \`JFR.stop\` để kết thúc và lưu file cuối.
8. Kiểm tra file bằng \`jfr summary\`.
9. Dùng \`jfr view\`, \`jfr print\` hoặc JMC để phân tích event liên quan.
10. Scrub dữ liệu nhạy cảm trước khi chia sẻ.
11. Lưu recording, cấu hình event và thông tin thời điểm thu thập để có thể tái hiện phân tích.

JFR dump file là bằng chứng có cấu trúc về hoạt động của JVM theo thời gian. Khi hiểu vòng đời recording, phân biệt dump với stop, biết cách đọc file và bảo vệ dữ liệu, bạn có thể dùng JFR để điều tra hiệu năng một cách có hệ thống.

## Tài liệu tham khảo

- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html).
- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html).
- Oracle JDK 24 — [Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
