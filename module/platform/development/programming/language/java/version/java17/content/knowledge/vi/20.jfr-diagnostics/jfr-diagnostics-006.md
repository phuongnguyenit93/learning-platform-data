# Bắt đầu, lưu và dừng bản ghi JFR trong Java 17

## 1. JFR dùng để làm gì?

Java Flight Recorder (JFR) là cơ chế ghi lại các sự kiện xảy ra trong JVM và ứng dụng để hỗ trợ chẩn đoán hiệu năng. Một recording có thể chứa thông tin về:

- Garbage collection và heap.
- CPU sampling và hoạt động của thread.
- Lock contention, monitor và thread park.
- Allocation object.
- Class loading và biên dịch JIT.
- File I/O, socket I/O và một số sự kiện runtime khác.
- Custom event do ứng dụng hoặc thư viện phát ra.

JFR lưu dữ liệu dưới dạng file nhị phân có phần mở rộng `.jfr`. Sau khi ghi, có thể dùng công cụ `jfr` đi kèm JDK hoặc Java Mission Control (JMC) để xem tổng quan, lọc sự kiện và phân tích theo thời gian.

Trong Java 17, JFR đã là công nghệ được hỗ trợ trong JDK, có thể dùng trên môi trường production với cấu hình phù hợp. Không cần bật các cờ mở khóa tính năng thương mại hoặc cờ kích hoạt JFR từ những hướng dẫn JDK cũ.

Một quy trình làm việc điển hình:

~~~text
Chọn workload và thời gian ghi
          |
          v
Bắt đầu recording
          |
          v
Chạy workload / chờ sự cố
          |
          v
Kiểm tra trạng thái recording
          |
          v
Dump snapshot hoặc stop recording
          |
          v
Lưu file .jfr
          |
          v
Phân tích bằng jfr hoặc JMC
~~~

Sau bài học, người học cần:

1. Bắt đầu recording ngay khi JVM khởi động bằng `-XX:StartFlightRecording`.
2. Bắt đầu recording trên JVM đang chạy bằng `jcmd`.
3. Phân biệt `JFR.dump` và `JFR.stop`.
4. Lưu recording vào file và quản lý dung lượng/thời gian ghi.
5. Chọn cấu hình `default`, `profile` hoặc file cấu hình JFC phù hợp.
6. Tạo recording bằng API `jdk.jfr.Recording` trong Java code.
7. Xem lại file bằng `jfr summary`, `jfr print` hoặc JMC.
8. Quản lý overhead, dữ liệu nhạy cảm và vòng đời recording.

## 2. Chuẩn bị môi trường Java 17

### 2.1. Dùng công cụ đi kèm JDK

Các công cụ thường dùng:

| Công cụ | Vai trò |
|---|---|
| `java` | Khởi chạy ứng dụng và có thể bắt đầu recording ngay lúc startup |
| `jcmd` | Gửi diagnostic command tới một JVM đang chạy, bao gồm JFR start/check/dump/stop |
| `jfr` | Tóm tắt và in dữ liệu từ file recording |
| `jconsole` | Quan sát một số thông tin quản trị JVM qua JMX |
| Java Mission Control (JMC) | Phân tích recording bằng giao diện đồ họa; có thể cài riêng |

Kiểm tra phiên bản runtime và công cụ:

~~~bash
java -version
jcmd -h
jfr --help
~~~

Hãy dùng công cụ từ JDK tương thích với JVM đang chạy. Với thao tác attach, tiến trình cần nằm trong môi trường mà công cụ có thể nhìn thấy và người dùng chạy `jcmd` phải có quyền phù hợp.

### 2.2. JFR có sẵn trong Java 17

JFR được đưa vào OpenJDK và được mở rộng qua các phiên bản JDK. Với Java 17, có thể dùng trực tiếp:

- `-XX:StartFlightRecording` khi khởi chạy JVM.
- `jcmd <pid> JFR.start` để bắt đầu recording khi JVM đã chạy.
- API `jdk.jfr` nếu muốn điều khiển recording từ Java code.

Không dùng các hướng dẫn cũ yêu cầu `-XX:+UnlockCommercialFeatures` hoặc `-XX:+FlightRecorder` cho Java 17. Những cờ đó không phải bước khởi tạo cần thiết của JFR trong JDK hiện đại.

## 3. Chọn cấu hình recording

JFR dùng cấu hình sự kiện (event settings) để quyết định sự kiện nào được ghi, tần suất lấy mẫu và ngưỡng ghi.

### 3.1. Cấu hình default

`default` hướng tới ghi nhận thông tin hữu ích với overhead thấp, phù hợp cho việc quan sát dài hơn hoặc recording nền trong nhiều trường hợp.

Ví dụ:

~~~bash
jcmd <pid> JFR.start name=continuous settings=default
~~~

Không nên hiểu `default` là ghi mọi sự kiện hoặc luôn đủ chi tiết để tìm mọi loại bottleneck. Nếu cần phân tích sâu hơn, hãy xem xét cấu hình profile hoặc JFC tùy chỉnh.

### 3.2. Cấu hình profile

`profile` ghi nhiều sự kiện chi tiết hơn, thường hữu ích cho một phiên profiling có thời hạn:

~~~bash
jcmd <pid> JFR.start name=investigation settings=profile duration=120s
~~~

Cấu hình profile có thể tạo nhiều dữ liệu và overhead cao hơn default. Hãy dùng khoảng thời gian phù hợp với mục tiêu điều tra, thay vì bật recording profile chi tiết vô thời hạn.

### 3.3. File cấu hình JFC tùy chỉnh

JFR hỗ trợ cấu hình dạng JFC. Có thể dùng cấu hình đi kèm JDK hoặc tạo một file riêng để bật/tắt sự kiện, thay đổi threshold, period và stack trace theo nhu cầu.

Ví dụ truyền file cấu hình:

~~~bash
jcmd <pid> JFR.start name=custom settings=/opt/app/jfr/custom.jfc
~~~

Đường dẫn phải tồn tại và JVM phải đọc được. Cấu hình tùy chỉnh nên được quản lý cùng phiên bản ứng dụng hoặc quy trình vận hành, tránh thay đổi không được ghi nhận giữa các lần chạy.

### 3.4. Chọn cấu hình theo mục tiêu

| Mục tiêu | Cấu hình khởi đầu |
|---|---|
| Ghi nền để giữ dữ liệu gần thời điểm xảy ra sự cố | `default`, có giới hạn dung lượng/thời gian |
| Điều tra CPU, allocation hoặc lock trong một khoảng ngắn | `profile` |
| Theo dõi một nhóm sự kiện cụ thể | JFC tùy chỉnh |
| Điều tra class/object retention sâu | Cấu hình có sự kiện phù hợp; cân nhắc chi phí và dữ liệu nhạy cảm |

Không bật mọi event ở mức chi tiết tối đa theo mặc định. Chọn sự kiện dựa trên giả thuyết cần kiểm tra.

## 4. Bắt đầu recording ngay khi JVM khởi động

Nếu muốn ghi từ giai đoạn startup, có thể truyền tùy chọn `-XX:StartFlightRecording` khi chạy ứng dụng.

~~~bash
java -XX:StartFlightRecording=name=startup,settings=profile,duration=2m,filename=recordings/startup.jfr,dumponexit=true -jar app.jar
~~~

Các thành phần:

- `name=startup`: tên recording.
- `settings=profile`: dùng cấu hình profile.
- `duration=2m`: recording tự kết thúc sau hai phút.
- `filename=recordings/startup.jfr`: file đích để lưu dữ liệu.
- `dumponexit=true`: yêu cầu dump recording khi JVM thoát.

Thư mục `recordings` phải được tạo trước và tiến trình cần quyền ghi. Dùng đường dẫn tuyệt đối trong môi trường triển khai để tránh phụ thuộc working directory.

### 4.1. Ghi từ đầu startup có ích khi nào?

Một số vấn đề chỉ xuất hiện trong quá trình:

- Nạp class và khởi tạo framework.
- Khởi tạo connection pool.
- JIT compile các method được gọi lần đầu.
- Warm-up cache.
- Đọc cấu hình hoặc tải dữ liệu ban đầu.

Nếu chỉ attach sau khi ứng dụng đã chạy ổn định, các sự kiện trước đó không nằm trong recording mới. Hãy dùng startup recording khi cần điều tra các giai đoạn này.

### 4.2. Recording không nhất thiết phải có duration

Có thể bắt đầu recording khi startup và để nó chạy cho tới khi JVM thoát hoặc được điều khiển bằng cơ chế phù hợp:

~~~bash
java -XX:StartFlightRecording=name=background,settings=default,filename=recordings/background.jfr,dumponexit=true -jar app.jar
~~~

Với recording dài hạn, cần quản lý dung lượng. Không để file tăng không kiểm soát trên filesystem nhỏ hoặc container ephemeral.

### 4.3. Các tùy chọn thường gặp

| Tùy chọn | Ý nghĩa |
|---|---|
| `name` | Tên recording |
| `settings` | Cấu hình JFC hoặc cấu hình dựng sẵn như default/profile |
| `duration` | Thời lượng recording |
| `filename` | Nơi ghi file khi recording được dump/hoàn tất theo cấu hình |
| `dumponexit` | Dump recording khi JVM thoát |
| `maxage` | Giới hạn tuổi dữ liệu giữ lại trong disk recording |
| `maxsize` | Giới hạn dung lượng dữ liệu giữ lại trong disk recording |
| `disk` | Chọn lưu dữ liệu recording trên đĩa hay trong bộ nhớ |

Các tùy chọn cụ thể và cách kết hợp cần tuân theo cú pháp của Java 17. Dùng:

~~~bash
java -XX:StartFlightRecording=help
~~~

để xem mô tả tùy chọn được runtime hỗ trợ.

## 5. Bắt đầu recording trên JVM đang chạy bằng jcmd

Đây là cách phổ biến khi cần điều tra một ứng dụng đã khởi động mà không muốn restart.

### 5.1. Tìm PID

Liệt kê các JVM mà công cụ có thể attach:

~~~bash
jcmd -l
~~~

Kết quả có thể gồm PID và tên main class/JAR. Chọn đúng tiến trình ứng dụng cần ghi. Trong container, PID nhìn thấy từ bên trong container có thể khác PID trên host; chạy công cụ trong đúng namespace hoặc môi trường quản trị.

### 5.2. Kiểm tra recording hiện tại

~~~bash
jcmd <pid> JFR.check
~~~

Lệnh cho biết các recording đang tồn tại và trạng thái của chúng. Có thể dùng dạng verbose để xem thêm chi tiết:

~~~bash
jcmd <pid> JFR.check verbose=true
~~~

Kiểm tra trước khi start giúp tránh tạo nhiều recording trùng lặp hoặc nhầm tên.

### 5.3. Bắt đầu recording có thời hạn

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=120s filename=/var/tmp/incident.jfr
~~~

JVM bắt đầu recording có tên `incident`. Recording sẽ tự kết thúc sau khoảng thời gian chỉ định; file đích được dùng để lưu dữ liệu. Thư mục đích phải có quyền ghi.

Có thể kiểm tra lại:

~~~bash
jcmd <pid> JFR.check
~~~

Nếu cần cú pháp chính xác của runtime:

~~~bash
jcmd <pid> help JFR.start
~~~

### 5.4. Bắt đầu recording nền có giới hạn

Để giữ một cửa sổ dữ liệu gần đây cho điều tra sự cố:

~~~bash
jcmd <pid> JFR.start name=continuous settings=default disk=true maxage=6h maxsize=512M
~~~

Ý nghĩa:

- `disk=true`: recording dùng lưu trữ trên đĩa.
- `maxage=6h`: giữ dữ liệu trong cửa sổ thời gian tối đa khoảng sáu giờ.
- `maxsize=512M`: giới hạn dung lượng dữ liệu được giữ theo cấu hình.

Khi giới hạn tuổi hoặc kích thước đạt tới, dữ liệu cũ có thể bị loại bỏ để giữ cửa sổ recording gần đây. Đây là cách hữu ích cho recording nền, nhưng phải cân nhắc disk I/O và dung lượng còn lại.

## 6. Dump, stop và save khác nhau thế nào?

Ba thao tác cần phân biệt:

| Lệnh | Tác dụng | Recording có tiếp tục không? |
|---|---|---|
| `JFR.check` | Xem trạng thái recording | Có |
| `JFR.dump` | Ghi snapshot dữ liệu hiện có ra file | Có |
| `JFR.stop` | Dừng recording và có thể ghi dữ liệu ra file | Không |

### 6.1. Dump snapshot nhưng tiếp tục ghi

Khi muốn lưu dữ liệu đến thời điểm hiện tại mà vẫn tiếp tục quan sát:

~~~bash
jcmd <pid> JFR.dump name=continuous filename=/var/tmp/incident-snapshot.jfr
~~~

Lệnh dump tạo file snapshot. Recording `continuous` vẫn tiếp tục chạy, nên có thể dump lần nữa sau khi có thêm dữ liệu.

Đây là lựa chọn phù hợp khi:

- Vừa phát hiện latency tăng và muốn giữ dữ liệu trước khi nó bị vòng đệm loại bỏ.
- Cần lưu một snapshot để phân tích, nhưng vẫn muốn theo dõi diễn biến tiếp theo.
- Muốn lấy nhiều mốc thời gian để so sánh trước/sau một hành động.

### 6.2. Stop recording và lưu file

Khi đã đủ dữ liệu:

~~~bash
jcmd <pid> JFR.stop name=continuous filename=/var/tmp/continuous-final.jfr
~~~

Lệnh dừng recording có tên `continuous` và ghi dữ liệu còn lại vào file đích. Sau khi stop, recording đó không tiếp tục nhận event mới.

Nếu đã cấu hình filename lúc start, runtime có thể dùng destination đã chỉ định. Khi vận hành, truyền filename rõ ràng lúc dump/stop giúp biết chính xác file kết quả được lưu ở đâu.

### 6.3. Duration tự kết thúc

Nếu start với:

~~~bash
jcmd <pid> JFR.start name=short-profile settings=profile duration=90s filename=/var/tmp/short-profile.jfr
~~~

thì recording tự dừng sau thời lượng đã đặt. Không cần gửi `JFR.stop` nếu mục tiêu chỉ là ghi đúng khoảng thời gian đó. Có thể dùng `JFR.check` để xem recording còn chạy hay đã kết thúc.

### 6.4. Dump không thay thế stop

Một lỗi vận hành thường gặp là dump file xong rồi quên recording vẫn đang chạy. File snapshot đã được lưu nhưng JVM vẫn tiếp tục thu thập sự kiện và tiêu thụ tài nguyên.

Nếu không còn cần recording, hãy stop:

~~~bash
jcmd <pid> JFR.stop name=incident
~~~

Nếu cần file cuối cùng, chỉ định filename ở lệnh stop hoặc dùng destination đã cấu hình từ trước. Sau đó kiểm tra lại bằng `JFR.check`.

## 7. Lưu trữ và quản lý dung lượng

### 7.1. Đặt filename rõ ràng

File recording thường có đuôi `.jfr`. Nên đặt tên thể hiện:

- Tên dịch vụ hoặc instance.
- Mốc thời gian hoặc mã incident.
- Mục tiêu recording.
- Phiên bản ứng dụng nếu cần.

Ví dụ:

~~~text
orders-api-2026-11-15-p99-spike.jfr
~~~

Tránh tên chung như `recording.jfr` nếu nhiều instance hoặc nhiều lần chạy có thể ghi đè/nhầm file.

### 7.2. Giới hạn maxage và maxsize

Với disk recording chạy dài, dùng `maxage` và `maxsize` để kiểm soát cửa sổ dữ liệu:

~~~bash
jcmd <pid> JFR.start name=rolling settings=default disk=true maxage=2h maxsize=256M
~~~

Hai giới hạn này giúp tránh lưu dữ liệu vô hạn. Chúng có thể khiến sự kiện cũ bị loại bỏ khi recording tiếp tục chạy; vì thế khi phát hiện sự cố, dump snapshot sớm để giữ dữ liệu cần phân tích.

### 7.3. Memory recording và disk recording

JFR có thể giữ dữ liệu trong bộ nhớ hoặc trên đĩa:

- Disk recording phù hợp khi cần ghi lâu hơn và quản lý bằng giới hạn tuổi/kích thước.
- Memory recording phù hợp với cửa sổ ngắn hoặc khi muốn kiểm soát cách snapshot; dữ liệu chưa dump có thể mất khi JVM kết thúc.

Ví dụ bắt đầu recording trong bộ nhớ:

~~~bash
jcmd <pid> JFR.start name=memory-window settings=profile disk=false
~~~

Khi cần lưu snapshot:

~~~bash
jcmd <pid> JFR.dump name=memory-window filename=/var/tmp/memory-window.jfr
~~~

Không dùng memory recording dài hạn mà không hiểu giới hạn bộ nhớ và cơ chế dữ liệu cũ bị loại bỏ. Với tình huống production cần giữ dữ liệu qua restart, phải dump ra file trước khi tiến trình kết thúc.

### 7.4. Dữ liệu recording có thể nhạy cảm

JFR có thể ghi stack trace, tên thread, tên class, đường dẫn file, thông tin I/O, exception message và custom event. Tùy event/configuration, recording có thể tiết lộ chi tiết triển khai hoặc dữ liệu ứng dụng.

Hãy:

- Lưu file vào vị trí có quyền truy cập giới hạn.
- Không đính kèm recording vào ticket công khai nếu chưa xem xét dữ liệu.
- Quy định thời hạn lưu và xóa file theo chính sách vận hành.
- Bảo vệ đường dẫn và quyền truy cập trong container/host.
- Kiểm tra custom event không chứa secret, token hoặc thông tin cá nhân không cần thiết.

## 8. Dùng công cụ jfr để xem recording

Sau khi có file, JDK 17 cung cấp lệnh `jfr` để đọc nội dung cơ bản.

### 8.1. Tóm tắt file

~~~bash
jfr summary /var/tmp/incident-snapshot.jfr
~~~

Summary cho biết thời gian recording, số lượng event theo loại và các thông tin tổng quan. Đây là bước đầu để xác nhận file có dữ liệu và xem loại sự kiện nào xuất hiện.

### 8.2. In một nhóm sự kiện

~~~bash
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample /var/tmp/incident-snapshot.jfr
~~~

Có thể chọn các event khác tùy mục tiêu, chẳng hạn:

- `jdk.CPULoad`.
- `jdk.ThreadPark`.
- `jdk.JavaMonitorEnter`.
- `jdk.SocketRead`.
- `jdk.FileRead`.
- `jdk.ObjectAllocationSample`.

Tên event và dữ liệu có sẵn phụ thuộc cấu hình recording. Nếu event không được bật hoặc không xảy ra trong khoảng ghi, file có thể không chứa event đó.

### 8.3. In theo định dạng JSON

Để chuyển dữ liệu event sang dạng JSON phục vụ xử lý tiếp:

~~~bash
jfr print --json --events jdk.GarbageCollection /var/tmp/incident-snapshot.jfr
~~~

JSON output có thể lớn; hãy giới hạn event hoặc khoảng dữ liệu phù hợp. Không nên in toàn bộ recording rất lớn ra terminal nếu mục tiêu chỉ là kiểm tra một vài sự kiện.

### 8.4. Xem bằng Java Mission Control

JMC cung cấp giao diện để:

- Xem timeline và sự kiện theo thời gian.
- Phân tích CPU samples và hot method.
- Xem GC pauses và heap behavior.
- Tìm thread blocked, park hoặc lock contention.
- Phân tích allocation và I/O.
- Lọc sự kiện theo thread, class, stack trace hoặc khoảng thời gian.

JMC có thể được cài riêng; không nhất thiết nằm trong mọi bản cài JDK. Dùng phiên bản JMC hỗ trợ định dạng JFR từ Java 17.

## 9. Điều khiển JFR từ Java code

Nếu ứng dụng hoặc công cụ kiểm thử cần bắt đầu/dừng recording theo một kịch bản cụ thể, có thể dùng API `jdk.jfr.Recording`.

### 9.1. Ví dụ programmatic recording

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

import java.nio.file.Path;
import java.time.Duration;

public class ProgrammaticJfr {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("recordings/workload.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("workload");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(10));
            recording.setMaxSize(256L * 1024 * 1024);

            recording.start();

            runWorkload();

            recording.stop();
            recording.dump(output);
        }
    }

    private static void runWorkload() {
        // Chạy tác vụ cần đo.
    }
}
~~~

Giải thích:

1. `Configuration.getConfiguration("profile")` lấy cấu hình profile dựng sẵn.
2. `new Recording(configuration)` tạo recording mới.
3. `setName` đặt tên để nhận diện.
4. `setToDisk(true)` chọn recording dùng disk.
5. `setMaxAge` và `setMaxSize` đặt giới hạn dữ liệu giữ lại.
6. `start()` bắt đầu ghi.
7. `stop()` dừng ghi.
8. `dump(output)` ghi dữ liệu đã thu được ra file.
9. `close()` từ try-with-resources đóng recording và giải phóng tài nguyên quản lý.

Thư mục đích phải tồn tại và có quyền ghi. Nếu dự án dùng module system, khai báo dependency:

~~~java
module com.example.app {
    requires jdk.jfr;
}
~~~

### 9.2. Dump snapshot rồi tiếp tục recording

Trong API, có thể dump dữ liệu đã ghi trong khi recording vẫn đang hoạt động:

~~~java
recording.dump(Path.of("recordings/snapshot.jfr"));
~~~

Sau snapshot, recording vẫn tiếp tục. Khi muốn hoàn tất:

~~~java
recording.stop();
recording.dump(Path.of("recordings/final.jfr"));
~~~

Hãy chọn tên file khác nhau để tránh nhầm snapshot giữa chừng với file cuối cùng.

### 9.3. Dùng RecordingStream cho xử lý event liên tục

`RecordingStream` có thể dùng để nhận event từ JFR trong lúc chúng được phát ra, hữu ích cho công cụ quan sát hoặc cảnh báo tùy chỉnh. Đây là API khác với việc chỉ ghi một file rồi phân tích sau.

Nếu mục tiêu là lưu một recording để điều tra, `Recording` thường trực tiếp hơn. Chỉ dùng `RecordingStream` khi ứng dụng thật sự cần xử lý event liên tục và đã tính đến callback, backpressure, chi phí xử lý cũng như vòng đời stream.

## 10. Chọn cách bắt đầu recording theo tình huống

| Tình huống | Cách làm phù hợp |
|---|---|
| Cần ghi cả startup | `-XX:StartFlightRecording` |
| JVM đang chạy và vừa xuất hiện spike latency | `jcmd JFR.start` hoặc dump recording nền đang có |
| Muốn giữ cửa sổ dữ liệu gần đây | Recording nền với `default`, `disk=true`, `maxage` và `maxsize` |
| Cần profiling chi tiết trong thời gian ngắn | `profile` với `duration` |
| Ứng dụng cần điều khiển recording theo code path | API `jdk.jfr.Recording` |
| Cần xem dữ liệu nhanh trong terminal | `jfr summary` và `jfr print` |
| Cần phân tích timeline/stack trực quan | JMC |

Đừng tạo recording mới nếu đã có recording nền phù hợp. Kiểm tra bằng `JFR.check`, dump snapshot nếu cần và stop recording khi không còn mục đích thu thập.

## 11. Lỗi thường gặp khi start, dump hoặc stop

### 11.1. Không tìm thấy JVM để attach

`jcmd -l` không liệt kê tiến trình mong muốn.

Nguyên nhân có thể:

- Đang chạy `jcmd` ở host/container namespace khác.
- User chạy công cụ không có quyền attach.
- JVM đã thoát hoặc PID thay đổi.
- Runtime bị giới hạn attach theo cấu hình môi trường.

Kiểm tra lại PID, user, container và JDK đang dùng. Không nhầm lỗi attach với việc JFR không được hỗ trợ.

### 11.2. Recording không được lưu thành file

Nguyên nhân có thể:

- Chưa gọi `JFR.dump` hoặc `JFR.stop` với filename phù hợp.
- Thư mục đích không tồn tại hoặc không có quyền ghi.
- JVM kết thúc trước khi memory recording được dump.
- Recording đã bị stop hoặc tên recording không đúng.

Kiểm tra `JFR.check`, đường dẫn và quyền ghi; dùng tên recording chính xác.

### 11.3. Dump xong nhưng recording vẫn chạy

Đây là hành vi đúng của `JFR.dump`. Dump chỉ tạo snapshot.

Nếu không muốn tiếp tục ghi, gọi `JFR.stop` hoặc để recording tự kết thúc theo `duration`.

### 11.4. Stop nhưng không có file mong đợi

Hãy kiểm tra filename được cấu hình lúc start và filename truyền khi stop. Không giả định file được lưu vào thư mục hiện tại nếu đường dẫn không được chỉ định rõ.

### 11.5. Recording quá lớn

Có thể do:

- Dùng profile quá lâu.
- Bật quá nhiều event hoặc threshold quá thấp.
- Không đặt maxage/maxsize cho recording nền.
- Ghi nhiều custom event có payload lớn.

Giảm thời lượng, chọn settings phù hợp, giới hạn dung lượng và lọc event theo mục tiêu.

### 11.6. Không thấy event cần tìm

Event có thể không được bật trong settings, không phát sinh trong thời gian ghi hoặc bị loại bỏ bởi threshold/period. Kiểm tra JFC configuration và khoảng thời gian recording trước khi kết luận.

### 11.7. Dùng cờ legacy

Không thêm `-XX:+UnlockCommercialFeatures` hoặc `-XX:+FlightRecorder` theo hướng dẫn cũ. JFR đã được tích hợp và hỗ trợ trong JDK 17; hãy dùng cú pháp hiện hành của `java`/`jcmd`.

## 12. Overhead và an toàn dữ liệu

JFR được thiết kế để ghi sự kiện với overhead thấp trong nhiều tình huống, nhưng không phải bằng không. Mức ảnh hưởng phụ thuộc:

- Settings và số lượng event được bật.
- Tần suất event và stack trace.
- Thời gian ghi.
- Workload, số thread và tốc độ phát sinh event.
- Thiết bị lưu trữ và cấu hình disk recording.

Trước khi bật recording chi tiết trên production:

1. Chọn settings phù hợp với mục tiêu.
2. Đặt duration hoặc maxage/maxsize.
3. Đo tác động của recording trên workload đại diện.
4. Xác định nơi lưu và quota dung lượng.
5. Kiểm tra dữ liệu nhạy cảm có thể xuất hiện trong event.
6. Có quy trình dump/stop và dọn file sau khi điều tra.

Nếu cần theo dõi dài hạn, bắt đầu bằng default và giới hạn cửa sổ dữ liệu. Khi sự cố xảy ra, dump snapshot trước khi dữ liệu cũ bị loại bỏ. Chỉ chuyển sang profile chi tiết trong khoảng thời gian cần thiết.

## 13. Kịch bản thực hành: bắt recording khi p99 tăng

Giả sử một dịch vụ Java 17 đang chạy và p99 latency đột ngột tăng. Một quy trình có thể là:

### Bước 1: Kiểm tra JVM và recording hiện tại

~~~bash
jcmd -l
jcmd <pid> JFR.check
~~~

Nếu đã có recording nền, có thể dump snapshot trước để giữ dữ liệu quanh thời điểm sự cố.

### Bước 2: Dump recording nền

~~~bash
jcmd <pid> JFR.dump name=continuous filename=/var/tmp/orders-before-change.jfr
~~~

Recording vẫn tiếp tục sau lệnh này.

### Bước 3: Bắt profiling chi tiết có thời hạn

~~~bash
jcmd <pid> JFR.start name=p99-investigation settings=profile duration=120s filename=/var/tmp/orders-p99-profile.jfr
~~~

Chạy hoặc chờ workload gây ra spike trong khoảng ghi. Tránh tạo thêm tải nhân tạo không giống production nếu mục tiêu là tìm nguyên nhân thực tế.

### Bước 4: Kiểm tra trạng thái

~~~bash
jcmd <pid> JFR.check verbose=true
~~~

Nếu recording còn chạy và đã đủ dữ liệu, có thể dump snapshot:

~~~bash
jcmd <pid> JFR.dump name=p99-investigation filename=/var/tmp/orders-p99-snapshot.jfr
~~~

### Bước 5: Dừng khi không cần ghi nữa

~~~bash
jcmd <pid> JFR.stop name=p99-investigation filename=/var/tmp/orders-p99-final.jfr
jcmd <pid> JFR.stop name=continuous
~~~

Chỉ stop recording nền nếu không còn cần giữ cửa sổ dữ liệu. Nếu recording nền là chính sách quan sát lâu dài, để nó tiếp tục theo quy trình vận hành.

### Bước 6: Xem summary và event

~~~bash
jfr summary /var/tmp/orders-p99-final.jfr
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample,jdk.ThreadPark /var/tmp/orders-p99-final.jfr
~~~

Mở file trong JMC để đối chiếu GC, CPU sample, thread state và lock event theo timestamp của spike.

### Bước 7: Ghi lại kết quả

Lưu:

- Tên recording và settings.
- Thời gian start/stop.
- PID, phiên bản JDK và phiên bản ứng dụng.
- Workload trong khoảng ghi.
- File JFR và nơi lưu an toàn.
- Các event hoặc stack trace có liên quan tới giả thuyết.

Không kết luận chỉ từ một event. Hãy đối chiếu với metric ứng dụng, log, tracing và tài nguyên hệ điều hành.

## 14. Bài tập thực hành

### Bài 1 — Recording lúc startup

Khởi chạy một ứng dụng Java 17 với `-XX:StartFlightRecording`, tên `startup`, settings `profile`, duration 60 giây và filename cụ thể. Mở file bằng `jfr summary` và ghi lại số lượng event.

### Bài 2 — Attach vào JVM đang chạy

Chạy ứng dụng nền, tìm PID bằng `jcmd -l`, bắt đầu recording `default`, kiểm tra bằng `JFR.check`, sau đó stop và lưu file.

### Bài 3 — Dump mà không stop

Bắt đầu recording không đặt duration. Gọi `JFR.dump` hai lần ở hai thời điểm khác nhau. Xác nhận recording vẫn tồn tại giữa hai lần dump; sau đó gọi `JFR.stop`.

### Bài 4 — Giới hạn recording nền

Khởi động disk recording với `maxage` và `maxsize`. Giải thích vì sao đây là cách kiểm soát cửa sổ dữ liệu cho recording dài hạn.

### Bài 5 — So sánh default và profile

Chạy cùng workload với settings default và profile trong thời lượng tương đương. So sánh số lượng event, kích thước file và overhead quan sát được. Không giả định profile luôn tốt hơn.

### Bài 6 — Dùng API trong Java code

Tạo recording bằng `Configuration.getConfiguration("profile")`, start, chạy một tác vụ, stop và dump ra file. Đảm bảo recording được đóng ngay cả khi workload phát sinh exception.

### Bài 7 — Phân tích file

Dùng `jfr summary` và `jfr print` để lọc GarbageCollection và ExecutionSample. Mở file trong JMC và tìm mối liên hệ giữa CPU, GC và thread activity.

## 15. Tiêu chí hoàn thành

Người học hoàn thành bài khi có thể:

1. Giải thích recording JFR thu thập sự kiện gì và file kết quả có dạng nào.
2. Bắt đầu recording khi JVM khởi động bằng `-XX:StartFlightRecording`.
3. Tìm PID và dùng `jcmd` để start/check/dump/stop recording.
4. Phân biệt dump snapshot với stop recording.
5. Chọn default, profile hoặc JFC tùy mục tiêu.
6. Giới hạn thời lượng, dung lượng và tuổi dữ liệu của recording.
7. Dùng API `jdk.jfr.Recording` để điều khiển recording từ Java code.
8. Xem file bằng `jfr summary`, `jfr print` hoặc JMC.
9. Nhận diện overhead, quyền truy cập attach, đường dẫn lưu và dữ liệu nhạy cảm.
10. Không dùng cờ JFR legacy hoặc để recording chạy/lưu dữ liệu không kiểm soát.

## 16. Tài liệu chính thức

- [Java SE 17 JFR Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html): tổng quan Java Flight Recorder và cách sử dụng.
- [Java SE 17 API — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): tạo, start, stop, dump và đóng recording.
- [Java SE 17 API — `jdk.jfr.Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Configuration.html): cấu hình dựng sẵn và JFC.
- [Java SE 17 man page — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): diagnostic command cho JVM đang chạy.
- [Java SE 17 man page — `java`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn `-XX:StartFlightRecording`.
- [Java SE 17 man page — `jfr`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): summary, print và các thao tác với file recording.
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR trong OpenJDK.

**Ghi nhớ:** `JFR.start` bắt đầu thu thập, `JFR.dump` lưu snapshot nhưng recording tiếp tục, còn `JFR.stop` kết thúc recording. Hãy chọn settings theo mục tiêu, giới hạn thời gian/dung lượng, lưu file ở nơi an toàn và phân tích dữ liệu cùng metric của ứng dụng. Java 17 đã hỗ trợ JFR trực tiếp; không cần các cờ mở khóa JFR cũ.
