# Thời lượng recording trong Java Flight Recorder

## Mục tiêu

Sau bài này, bạn có thể chọn thời lượng phù hợp cho một Java Flight Recorder (JFR) recording; phân biệt recording có thời lượng cố định với recording liên tục; dùng duration, delay, maxage và maxsize đúng mục đích; bắt đầu, kiểm tra, dump và dừng recording bằng jcmd; cấu hình recording ngay khi JVM khởi chạy; quản lý recording bằng JDK Mission Control (JMC); điều khiển thời lượng qua JFR Recording API; phân tích file .jfr; và cân bằng độ chi tiết, overhead, dung lượng lưu trữ cùng cửa sổ sự cố cần điều tra.

## 1. Thời lượng recording là gì?

Java Flight Recorder (JFR) là framework thu thập event của JVM, JDK, hệ điều hành và ứng dụng Java. Một recording lưu các event có timestamp để bạn có thể phân tích hoạt động của process sau khi sự việc xảy ra.

**Thời lượng recording** là khoảng thời gian JFR tiếp tục thu thập event sau khi recording bắt đầu. Ví dụ, recording có duration 10 phút sẽ tự kết thúc sau khoảng 10 phút kể từ thời điểm bắt đầu thực tế.

Thời lượng ảnh hưởng đến:

- Khoảng thời gian của ứng dụng được quan sát.
- Khả năng bắt được sự cố chỉ xuất hiện theo chu kỳ hoặc khi tải tăng.
- Lượng event và kích thước file recording.
- Thời gian JFR tiếp tục chạy và mức overhead tích lũy.
- Khả năng giữ được dữ liệu trước, trong và sau thời điểm incident.

Một recording quá ngắn có thể bỏ lỡ tình huống hiếm gặp. Recording quá dài với profile nhiều event có thể tạo file lớn và thêm overhead không cần thiết. Hãy chọn thời lượng dựa trên câu hỏi điều tra và tần suất xảy ra vấn đề.

JFR hỗ trợ hai kiểu sử dụng chính:

- **Time-fixed recording:** ghi trong một khoảng thời gian xác định rồi tự dừng. Phù hợp với profiling có mục tiêu, kiểm tra một lần deploy, một bài load test hoặc một cửa sổ tái hiện lỗi.
- **Continuous recording:** chạy liên tục, giữ lại một cửa sổ dữ liệu gần nhất theo giới hạn thời gian hoặc dung lượng. Khi cần điều tra, người vận hành dump phần dữ liệu liên quan ra file.

## 2. Phân biệt duration, delay, maxage và maxsize

Bốn tham số này có liên quan tới thời gian hoặc dung lượng nhưng điều khiển các khía cạnh khác nhau.

| Tham số | Điều khiển | Ví dụ |
|---|---|---|
| duration | Recording chạy bao lâu rồi tự dừng | 10m |
| delay | Chờ bao lâu sau khi yêu cầu start rồi mới bắt đầu ghi | 30s |
| maxage | Chỉ giữ dữ liệu trên disk trong khoảng thời gian gần nhất | 2h |
| maxsize | Giới hạn dung lượng dữ liệu giữ trên disk | 512M |

### duration — thời gian chạy của recording

duration xác định vòng đời ghi dữ liệu. Khi hết duration, recording tự dừng. Với jcmd JDK 26, giá trị dùng đơn vị s, m hoặc h; 0s có nghĩa là không giới hạn thời lượng.

~~~bash
jcmd <PID> JFR.start name=checkout-profile settings=profile duration=10m filename=checkout-profile.jfr
~~~

Recording bắt đầu ngay và tự dừng sau 10 phút. File được ghi vào checkout-profile.jfr khi recording kết thúc.

### delay — trì hoãn thời điểm bắt đầu

delay xác định khoảng chờ trước khi JFR bắt đầu ghi event. Nó hữu ích khi muốn ứng dụng khởi động ổn định trước khi profiling, hoặc muốn recording bắt đầu gần thời điểm load test.

~~~bash
jcmd <PID> JFR.start name=after-warmup settings=profile delay=2m duration=8m filename=after-warmup.jfr
~~~

JFR chờ 2 phút, sau đó ghi trong 8 phút. Thời điểm kết thúc xấp xỉ 10 phút sau khi gửi lệnh, cộng thêm thời gian xử lý command và sai số lập lịch.

### maxage — giới hạn tuổi dữ liệu được giữ

maxage giới hạn khoảng thời gian dữ liệu được giữ trong disk repository. Khi dữ liệu cũ hơn giới hạn, JVM loại bỏ các chunk cũ.

~~~bash
jcmd <PID> JFR.start name=rolling settings=default disk=true maxage=2h
~~~

Recording có thể tiếp tục chạy lâu hơn hai giờ, nhưng repository chỉ giữ dữ liệu trong cửa sổ thời gian gần nhất khoảng hai giờ.

### maxsize — giới hạn dung lượng dữ liệu được giữ

maxsize giới hạn dung lượng dữ liệu của recording trên disk. Khi giới hạn bị vượt, JFR loại bỏ chunk cũ để có chỗ cho dữ liệu mới.

~~~bash
jcmd <PID> JFR.start name=rolling settings=default disk=true maxsize=512M
~~~

Nếu event được tạo nhanh, cửa sổ thời gian thực tế được giữ có thể ngắn hơn dự kiến vì giới hạn dung lượng bị chạm trước maxage.

### duration không thay thế maxage/maxsize

- duration giới hạn tổng thời gian recording tồn tại.
- maxage và maxsize giới hạn lượng dữ liệu lịch sử được giữ trong repository khi recording đang chạy trên disk.

Một recording có duration 30 phút nhưng maxage 5 phút có thể chỉ còn dữ liệu của 5 phút cuối khi kết thúc. Tương tự, maxsize có thể khiến chunk cũ bị loại bỏ trước khi duration kết thúc.

Nếu muốn thu toàn bộ một lần profiling kéo dài 15 phút, hãy bảo đảm maxage/maxsize đủ lớn hoặc không đặt giới hạn repository không cần thiết. Nếu muốn giữ một cửa sổ gần nhất cho incident bất ngờ, hãy dùng recording liên tục với maxage/maxsize hữu hạn.

## 3. Recording có thời lượng cố định và recording liên tục

| Tiêu chí | Time-fixed | Continuous |
|---|---|---|
| Vòng đời | Tự dừng sau duration | Tiếp tục cho đến khi dừng hoặc JVM kết thúc |
| Dữ liệu được giữ | Toàn bộ cửa sổ trong giới hạn repository | Cửa sổ gần nhất theo maxage/maxsize |
| Cách lấy file | File được ghi khi recording dừng | Dump tại thời điểm cần, recording vẫn tiếp tục |
| Mục đích | Profiling một tình huống đã biết | Điều tra sự cố hiếm hoặc không dự đoán được |
| Template thường dùng | profile hoặc default tùy mục tiêu | default hoặc Continuous |

### Khi dùng time-fixed recording

Chọn time-fixed khi có thể tái hiện vấn đề trong một cửa sổ thời gian; muốn đo hiệu năng trước/sau thay đổi; chạy benchmark hoặc load test có thời gian xác định; hoặc muốn giới hạn rõ thời gian profiling trên production.

~~~bash
jcmd <PID> JFR.start name=api-profile settings=profile duration=5m filename=api-profile-%p-%t.jfr
~~~

### Khi dùng continuous recording

Chọn continuous khi sự cố xuất hiện ngẫu nhiên, chưa biết thời điểm latency/GC bất thường xảy ra, hoặc cần giữ dữ liệu trước khi alert được kích hoạt.

~~~bash
jcmd <PID> JFR.start name=production-ring settings=default disk=true maxage=6h maxsize=512M dumponexit=true
~~~

Trong cấu hình này, duration mặc định là 0s, tức recording không tự dừng theo thời gian. Khi cần phân tích, dump một snapshot ra file riêng.

## 4. Chọn template trước khi quyết định thời lượng

Thời lượng chỉ cho biết recording kéo dài bao lâu. Template và event settings quyết định loại dữ liệu nào được thu thập trong khoảng thời gian đó.

| Template | Dữ liệu | Overhead |
|---|---|---|
| default.jfc | Bộ event nền tảng hữu ích cho theo dõi liên tục | Thấp |
| profile.jfc | Nhiều event chi tiết hơn, hữu ích cho profiling | Cao hơn default |

### default

default phù hợp cho recording liên tục hoặc quan sát nền trong thời gian dài. Template này được thiết kế với overhead thấp. Continuous recording dùng default không thu thập heap statistics hoặc allocation profiling mặc định.

### profile

profile thu thập nhiều dữ liệu hơn để tìm method nóng, allocation, contention và bottleneck. Do nhiều event được bật hơn, template này có thể tạo overhead và dung lượng lớn hơn. Dùng trong thời gian ngắn khi cần độ chi tiết cao hơn.

### Điều chỉnh event settings

Event settings quyết định event nào được ghi, có stack trace hay không, sampling period và threshold cho duration event.

Threshold thấp hơn giúp thấy nhiều sự kiện hơn nhưng có thể tăng overhead và kích thước recording. Hãy xem cấu hình bằng công cụ jfr và tài liệu của event cụ thể trước khi thay đổi. Không bật toàn bộ event ở mức chi tiết tối đa chỉ vì recording được giới hạn thời gian.

## 5. Thời lượng recording khác duration event

JFR có hai khái niệm cùng liên quan tới thời gian nhưng hoàn toàn khác nhau:

- **Recording duration:** tổng thời gian JFR thu thập dữ liệu, ví dụ 10 phút.
- **Event duration/threshold:** thời gian của một hoạt động trong ứng dụng, hoặc ngưỡng tối thiểu để event được ghi nhận, ví dụ một lần chờ lock kéo dài 20 ms.

Ví dụ, recording chạy 10 phút có thể ghi lại hàng trăm event JavaMonitorEnter. Mỗi event có duration riêng cho biết thread đã chờ monitor trong bao lâu.

Nếu threshold là 20 ms, các lần chờ ngắn hơn có thể không được ghi lại theo cấu hình event đó. Recording vẫn chạy đủ 10 phút; threshold không làm recording dừng sau 20 ms.

JFR còn có periodic event, được ghi theo chu kỳ lấy mẫu. Periodic event có period riêng, không phải recording duration.

Khi không thấy một event trong file, hãy kiểm tra event có được bật không, threshold có quá cao không và period có phù hợp không. Đừng kết luận rằng recording duration quá ngắn nếu vấn đề thực chất nằm ở event settings.

## 6. Bắt đầu recording có thời lượng bằng jcmd

jcmd là cách phổ biến để điều khiển JFR trên JVM đang chạy.

### Xác định PID

~~~bash
jcmd -l
~~~

Chọn PID đúng của ứng dụng. jcmd phải chạy trên cùng máy với JVM và cùng effective user/group đã dùng để khởi chạy JVM.

### Bắt đầu recording 10 phút

~~~bash
jcmd <PID> JFR.start name=incident-10m settings=profile duration=10m filename=incident-10m-%p-%t.jfr
~~~

- name: tên để nhận diện recording trong các lệnh JFR tiếp theo.
- settings: template hoặc file cấu hình event.
- duration: thời gian thu thập trước khi tự dừng.
- filename: đường dẫn file được ghi khi recording dừng.
- %p: được thay bằng PID của JVM.
- %t: được thay bằng timestamp hiện tại.

Nếu không truyền name, JVM tự tạo tên và hiển thị tên đó trong kết quả command. Hãy ghi lại tên do JVM trả về để dùng cho JFR.check, JFR.dump và JFR.stop.

### Kiểm tra recording

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.check name=incident-10m verbose=true
~~~

Kiểm tra recording đang chạy, thời gian bắt đầu, settings và trạng thái được hiển thị. Đừng chỉ dựa vào việc command start trả về thành công; hãy kiểm tra recording đúng tên đang hoạt động.

### Chờ recording tự kết thúc

Khi duration hết, JFR tự dừng recording. Nếu filename đã được cấu hình, dữ liệu được ghi vào file đó khi recording kết thúc.

Xác nhận file tồn tại, kích thước hợp lý và có thể đọc bằng công cụ jfr hoặc JMC.

### Dừng sớm trước khi hết duration

~~~bash
jcmd <PID> JFR.stop name=incident-10m filename=incident-10m-early-stop.jfr
~~~

Khi dừng thủ công, truyền filename để lưu dữ liệu. Theo cú pháp JDK 26, nếu JFR.stop không có đường dẫn file thì dữ liệu của recording bị loại bỏ. Hãy dùng tên file riêng để tránh ghi đè một recording trước đó.

## 7. Dump snapshot mà không dừng recording

Với recording liên tục, không nhất thiết phải dừng nó để lấy dữ liệu điều tra.

~~~bash
jcmd <PID> JFR.dump name=production-ring filename=incident-snapshot.jfr
~~~

JFR.dump ghi dữ liệu hiện có ra file, còn recording tiếp tục chạy. Bạn có thể tiếp tục theo dõi và dump lần nữa khi có incident khác.

### Chỉ lấy một cửa sổ thời gian

JFR.dump hỗ trợ begin và end để chọn khoảng dữ liệu. Có thể dùng timestamp hoặc khoảng thời gian tương đối so với hiện tại.

~~~bash
jcmd <PID> JFR.dump name=production-ring begin=-15m filename=last-15-minutes.jfr
~~~

Ví dụ lấy một khoảng theo timestamp:

~~~bash
jcmd <PID> JFR.dump name=production-ring begin=2026-11-10T09:00:00 end=2026-11-10T09:15:00 filename=morning-window.jfr
~~~

Timestamp cần theo định dạng mà LocalTime, LocalDateTime hoặc Instant có thể parse. begin/end tham chiếu timestamp bên trong recording.

Dump một khoảng ngắn hơn không làm thay đổi duration hoặc trạng thái của recording gốc. Đây chỉ là lựa chọn dữ liệu được ghi ra file snapshot.

### Dump và stop khác nhau thế nào?

| Command | Kết quả | Recording gốc |
|---|---|---|
| JFR.dump | Ghi snapshot ra file | Tiếp tục chạy |
| JFR.stop | Kết thúc recording và lưu file nếu có filename | Dừng |
| duration hết hạn | Recording tự dừng | Dừng tự động |

Nếu đang điều tra incident và muốn tiếp tục thu thập dữ liệu nền, dùng JFR.dump. Nếu đã hoàn thành và muốn kết thúc recording, dùng JFR.stop.

## 8. Dùng recording liên tục với giới hạn thời gian và dung lượng

Continuous recording hữu ích khi không thể dự đoán lúc sự cố xảy ra.

~~~bash
jcmd <PID> JFR.start name=rolling-default settings=default disk=true maxage=6h maxsize=512M dumponexit=true
~~~

Ý nghĩa:

- duration mặc định là 0s nên recording chạy liên tục.
- disk=true ghi dữ liệu vào disk repository.
- maxage=6h giữ dữ liệu tối đa trong cửa sổ 6 giờ.
- maxsize=512M giới hạn dung lượng repository.
- dumponexit=true yêu cầu dump recording khi JVM shutdown.

JFR loại bỏ chunk cũ khi vượt maxage hoặc maxsize. Vì vậy, cửa sổ dữ liệu thực tế có thể ngắn hơn sáu giờ nếu recording tạo event nhanh và chạm giới hạn dung lượng trước.

### Lấy dữ liệu khi có alert

~~~bash
jcmd <PID> JFR.check name=rolling-default
jcmd <PID> JFR.dump name=rolling-default begin=-20m filename=incident-last-20m.jfr
~~~

Lệnh dump lấy dữ liệu 20 phút gần nhất trong phạm vi repository còn giữ. Recording tiếp tục chạy để thu thập cho các sự cố tiếp theo.

Nếu cần lấy thêm dữ liệu sau khi alert, chờ một khoảng thích hợp rồi dump lần nữa với filename khác.

### Dừng recording liên tục

~~~bash
jcmd <PID> JFR.stop name=rolling-default filename=rolling-final.jfr
~~~

Dùng filename để lưu dữ liệu cuối cùng. Nếu recording đã được cấu hình dumponexit, JVM cũng có thể dump khi shutdown theo cấu hình đó.

### Chọn maxage và maxsize

Hãy dựa vào event rate và dung lượng thực tế:

- maxage dài hơn giúp giữ nhiều lịch sử hơn.
- maxsize lớn hơn giúp giữ cửa sổ dài hơn khi event rate cao.
- profile thường tạo dữ liệu nhanh hơn default.
- maxsize quá nhỏ có thể khiến dữ liệu biến mất trước khi incident được phát hiện.
- maxage/maxsize quá lớn có thể chiếm nhiều disk.

Theo dõi kích thước recording và dung lượng filesystem trong môi trường thử nghiệm trước khi áp dụng giới hạn cho production.

## 9. Bắt đầu recording ngay khi JVM khởi chạy

Có thể cấu hình JFR bằng tùy chọn -XX:StartFlightRecording của launcher java. Cách này hữu ích nếu cần ghi lại cả giai đoạn startup hoặc muốn recording tự bắt đầu trước khi ứng dụng nhận traffic.

~~~bash
java -XX:StartFlightRecording.delay=20s,duration=60s,name=startup-profile,filename=startup-profile.jfr,settings=profile -jar app.jar
~~~

Trong đó:

- delay=20s: chờ 20 giây sau khi ứng dụng khởi chạy.
- duration=60s: ghi trong 60 giây sau khi delay kết thúc.
- name: tên recording.
- filename: file output.
- settings=profile: dùng template profile.

Thời điểm bắt đầu ghi xấp xỉ 20 giây sau khi process được tạo; thời điểm dừng xấp xỉ 80 giây sau khi khởi chạy. Nếu JVM không chạy đủ lâu đến hết duration, recording có thể kết thúc do JVM shutdown; cân nhắc dumponexit khi cần lưu dữ liệu lúc shutdown.

### Continuous recording từ startup

~~~bash
java -XX:StartFlightRecording=settings=default,disk=true,maxage=6h,maxsize=512M,dumponexit=true -jar app.jar
~~~

Cấu hình này tạo recording liên tục với retention giới hạn. Sau đó có thể dùng jcmd JFR.dump để lấy cửa sổ dữ liệu khi cần.

Không thêm profile vào mọi JVM production theo mặc định. Chọn settings theo mục tiêu, kiểm tra overhead và bảo đảm dung lượng repository phù hợp.

## 10. Quản lý thời lượng recording bằng JDK Mission Control

JDK Mission Control (JMC) cung cấp giao diện để bắt đầu và quản lý recording.

Quy trình cơ bản:

1. Mở JMC và tìm JVM trong JVM Browser.
2. Chọn JVM đích.
3. Mở Start Flight Recording.
4. Chọn Time fixed recording hoặc Continuous recording.
5. Chọn template như Continuous/default hoặc Profiling/profile.
6. Với time-fixed, nhập duration và file đích.
7. Với continuous, đặt maximum age hoặc maximum size.
8. Xem lại event settings và threshold nếu cần.
9. Bắt đầu recording.
10. Khi cần, dump snapshot, dừng hoặc đóng recording theo mục tiêu.

JMC cho phép quản lý recording đang chạy: dump toàn bộ, dump phần gần nhất, chỉnh sửa settings, stop hoặc close. Stopping một profiling recording tạo file recording; closing recording có thể loại bỏ dữ liệu nếu chưa dump.

### Chọn time-fixed trong JMC

Dùng khi có một khoảng profiling đã biết. Ví dụ chọn 5 phút profile trong lúc chạy load test.

### Chọn continuous trong JMC

Dùng khi muốn theo dõi nền. Chọn maximum age/size để giới hạn dữ liệu lịch sử và dump khi incident xảy ra.

Giao diện có thể khác theo phiên bản JMC. Hãy xác nhận tên trường và hành vi trong bản JMC đang sử dụng.

## 11. Dùng JFR Recording API để đặt duration trong Java

JDK cung cấp API jdk.jfr. Class Recording có thể cấu hình tên, template, duration, max age, max size và file đích.

| Method | Tác dụng |
|---|---|
| setDuration(Duration) | Đặt thời gian recording chạy trước khi tự dừng |
| setMaxAge(Duration) | Giới hạn tuổi dữ liệu giữ trong disk repository |
| setMaxSize(long) | Giới hạn dung lượng dữ liệu giữ trong repository |
| setDestination(Path) | Đặt file đích được ghi khi recording dừng |
| setToDisk(boolean) | Chọn recording có ghi liên tục vào disk repository hay không |
| scheduleStart(Duration) | Lên lịch recording bắt đầu sau một khoảng chờ |
| start() | Bắt đầu recording |
| stop() | Dừng recording |
| dump(Path) | Ghi recording data ra file |
| close() | Giải phóng dữ liệu gắn với recording |

Đặt duration và destination trước khi start là cách rõ ràng để tạo một recording time-fixed có file output tự động.

### Ví dụ Java 17+: recording tự dừng sau 5 giây

Tạo file DurationRecordingDemo.java:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class DurationRecordingDemo {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("duration-demo.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("duration-demo");
            recording.setToDisk(true);
            recording.setDuration(Duration.ofSeconds(5));
            recording.setDestination(output);

            recording.start();
            System.out.println("recording-started");

            Thread.sleep(7_000);

            System.out.println(
                    "recording-file-exists=" + Files.exists(output));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 DurationRecordingDemo.java
java DurationRecordingDemo
~~~

Output chính xác:

~~~text
recording-started
recording-file-exists=true
~~~

Giải thích:

- Configuration.getConfiguration("default") chọn template default.
- setDuration đặt recording tự dừng sau 5 giây.
- setDestination đặt file được ghi khi recording dừng.
- setToDisk(true) cho phép recording ghi dữ liệu vào disk repository.
- Thread.sleep 7 giây để chương trình chờ lâu hơn duration, đủ thời gian cho recording kết thúc và file được ghi.
- try-with-resources đóng Recording khi chương trình kết thúc.

File duration-demo.jfr được tạo trong working directory. Kích thước và event bên trong phụ thuộc JDK, môi trường và hoạt động của process.

### Ví dụ recording liên tục qua API

Nếu muốn recording không tự dừng, bỏ setDuration hoặc không đặt duration. Có thể giới hạn dữ liệu giữ trong repository:

~~~java
Recording recording =
        new Recording(Configuration.getConfiguration("default"));

recording.setName("continuous-demo");
recording.setToDisk(true);
recording.setMaxAge(Duration.ofHours(2));
recording.setMaxSize(256L * 1024 * 1024);
recording.start();
~~~

Đoạn code này chỉ minh họa phần cấu hình và khởi chạy; ứng dụng phải quản lý vòng đời recording, dump dữ liệu khi cần và gọi stop/close khi kết thúc.

## 12. Chọn duration theo mục tiêu điều tra

Không có một giá trị duration đúng cho mọi ứng dụng. Hãy bắt đầu từ tần suất xuất hiện của vấn đề và lượng dữ liệu cần để phân tích.

| Mục tiêu | Cách chọn |
|---|---|
| Kiểm tra một thao tác chậm có thể tái hiện | Recording ngắn bao quanh thao tác |
| Load test có thời lượng xác định | Ghi từ trước khi test bắt đầu đến sau khi test kết thúc |
| So sánh trước/sau deploy | Hai recording có duration và workload tương đương |
| Điều tra GC pause hiếm | Recording dài hơn chu kỳ xuất hiện, hoặc continuous |
| Điều tra latency bất chợt | Continuous với maxage/maxsize rồi dump khi alert |
| Kiểm tra startup | Bắt đầu từ startup hoặc dùng delay ngắn |
| Điều tra memory leak | Recording đủ dài để thấy xu hướng allocation/live set; có thể cần nhiều snapshot |

### Tình huống 1: vấn đề xảy ra đều mỗi phút

Nếu một tác vụ scheduled chạy mỗi phút, recording chỉ dài 10 giây có thể không bắt được tác vụ. Chọn ít nhất một vài chu kỳ để có dữ liệu so sánh.

### Tình huống 2: lỗi xuất hiện sau vài giờ

Nếu vấn đề thường xuất hiện sau 3 giờ, recording time-fixed 10 phút bắt đầu ngay sau deploy sẽ không đủ. Dùng continuous recording với maxage đủ dài, hoặc lên lịch recording gần thời điểm dự kiến.

### Tình huống 3: cần đo latency chính xác

Chọn một cửa sổ ngắn bao trọn thao tác cần đo, và dùng template/event settings phù hợp. Không kéo dài profile recording không cần thiết vì sẽ thu thêm dữ liệu ngoài phạm vi và có thể tăng overhead.

### Tình huống 4: so sánh hai phiên bản

Giữ duration, template, event threshold, workload và thời gian warm-up gần tương đương. Nếu một recording dùng default 5 phút và recording kia dùng profile 30 phút, khác biệt có thể do cấu hình thu thập chứ không phải do phiên bản ứng dụng.

## 13. Ước lượng kích thước file và quản lý disk

Kích thước JFR phụ thuộc duration, template, event settings, event rate, số thread, stack trace, threshold/period, mức chi tiết profiling và cấu hình disk repository.

Không thể suy ra kích thước file chính xác chỉ từ duration. Hai recording cùng 10 phút có thể khác nhau nhiều lần về dung lượng.

### Đo thực tế

Thực hiện một recording thử trong môi trường tương tự production:

~~~bash
jcmd <PID> JFR.start name=size-test settings=profile duration=5m filename=size-test.jfr
~~~

Sau khi recording kết thúc, kiểm tra kích thước file bằng công cụ hệ điều hành.

Linux:

~~~bash
ls -lh size-test.jfr
~~~

Windows PowerShell:

~~~powershell
Get-Item size-test.jfr | Select-Object Name, Length, LastWriteTime
~~~

Từ kết quả thử, ước lượng dung lượng theo event rate thực tế, nhưng vẫn chừa headroom vì tải và event có thể thay đổi.

### Disk repository và file output

JFR có thể ghi chunk vào repository tạm trong lúc recording chạy. Khi dump hoặc stop, dữ liệu được ghi ra file output mà bạn chọn.

- Repository là nơi lưu dữ liệu tạm trong khi recording hoạt động.
- Destination/file output là artifact để phân tích hoặc lưu trữ.
- maxage/maxsize giới hạn dữ liệu được giữ trong repository khi recording ghi lên disk.
- File output cần được bảo vệ và quản lý retention riêng.

Không xóa repository hoặc file tạm khi JVM đang dùng chúng. Dùng command JFR để quản lý recording và để JVM xử lý việc loại bỏ chunk cũ.

## 14. Phân tích file recording sau khi kết thúc

Sau khi có file .jfr, có thể dùng JMC hoặc công cụ jfr của JDK.

### Xem summary

~~~bash
jfr summary duration-demo.jfr
~~~

Summary cho biết metadata, khoảng thời gian recording, số event và kích thước tổng quan.

### In event cụ thể

~~~bash
jfr print --events jdk.GCPhasePause duration-demo.jfr
~~~

Có thể chọn event phù hợp với mục tiêu, ví dụ GC pause, execution sample, monitor wait, socket read/write hoặc allocation event nếu template đã bật.

### Mở bằng JMC

Mở file .jfr trong JMC để phân tích recording duration và timeline, CPU usage và method samples, garbage collection và pause time, thread state, monitor contention và lock wait, file/socket I/O, allocation và memory behavior nếu event settings có thu thập, cùng custom event của ứng dụng.

JFR chỉ lưu event được bật và vượt qua threshold/period tương ứng. Không có event trong file không đồng nghĩa hoạt động đó chắc chắn không xảy ra.

## 15. Tác động hiệu năng và giới hạn khi chọn thời lượng

JFR được thiết kế để thu thập dữ liệu runtime với overhead thấp, nhưng overhead thực tế phụ thuộc event settings.

1. Bắt đầu với default khi cần recording liên tục.
2. Dùng profile trong khoảng ngắn khi cần dữ liệu chi tiết hơn.
3. Chọn duration đủ dài để bao trọn tình huống, không dài hơn nhu cầu nếu dùng profile.
4. Dùng maxage/maxsize cho recording liên tục để tránh repository không giới hạn.
5. Kiểm tra disk, quota và retention policy.
6. Hạn chế stack trace hoặc event có chi phí cao nếu không cần.
7. Không hạ event threshold quá thấp trên production khi chưa đo overhead.
8. Ghi lại settings, duration, JDK version và workload để so sánh kết quả.

Một số event settings có thể làm JVM thu thập thêm thông tin hoặc thực hiện công việc bổ sung. Ví dụ, bật heap statistics có thể kích hoạt old GC ở đầu và cuối test run, làm tăng pause time. Nếu đang đo latency nhạy với pause, không bật heap statistics trừ khi mục tiêu điều tra yêu cầu.

Duration dài không tự làm một event đắt hơn, nhưng kéo dài thời gian thu thập và tăng lượng dữ liệu có thể ghi. Event settings và event rate quyết định nhiều đến overhead và file size.

## 16. Lỗi thường gặp và cách xử lý

### Recording tự dừng sớm hơn dự kiến

**Dấu hiệu:** recording kết thúc trước khoảng thời gian mong muốn.

**Nguyên nhân:** duration đặt quá ngắn, recording bị JFR.stop, JVM shutdown hoặc recording bị đóng bởi ứng dụng quản lý.

**Cách xử lý:** kiểm tra JFR.check, command start, thời điểm shutdown và nơi quản lý vòng đời Recording API. Phân biệt duration của recording với delay trước khi bắt đầu.

### Recording chạy mãi không dừng

**Dấu hiệu:** đã chờ quá thời lượng dự kiến nhưng recording vẫn hoạt động.

**Nguyên nhân:** duration không được đặt, duration=0s hoặc command được gửi tới nhầm JVM/recording.

**Cách xử lý:** kiểm tra đúng PID và name bằng JFR.check; đặt duration dương hoặc dừng bằng JFR.stop kèm filename.

### Recording kết thúc nhưng không có file

**Dấu hiệu:** recording đã dừng nhưng không thấy file .jfr.

**Nguyên nhân:** filename sai, thư mục không tồn tại, thiếu quyền ghi, disk đầy hoặc JFR.stop được gọi mà không có filename.

**Cách xử lý:** kiểm tra destination, quyền và dung lượng; truyền filename rõ ràng ở JFR.start hoặc JFR.stop; kiểm tra log và file được tạo.

### Recording liên tục chỉ chứa dữ liệu gần đây

**Dấu hiệu:** file dump không có dữ liệu từ thời điểm recording bắt đầu.

**Nguyên nhân:** maxage hoặc maxsize đã loại bỏ chunk cũ khỏi repository.

**Cách xử lý:** tăng retention nếu cần cửa sổ dài hơn; theo dõi event rate và dump trước khi dữ liệu bị loại bỏ.

### File recording quá lớn

**Dấu hiệu:** file tăng nhanh hoặc chiếm nhiều disk.

**Nguyên nhân:** profile settings, event rate cao, stack trace nhiều, threshold quá thấp hoặc duration quá dài.

**Cách xử lý:** dùng default khi theo dõi nền; rút ngắn profile; tăng threshold phù hợp; giới hạn maxage/maxsize; đo file size trong staging trước.

### Recording có duration đủ dài nhưng không thấy event mong muốn

**Dấu hiệu:** file có thời lượng đúng nhưng thiếu event cần phân tích.

**Nguyên nhân:** event không được bật, threshold quá cao, sampling period quá thưa hoặc template không thu thập loại dữ liệu đó.

**Cách xử lý:** kiểm tra event settings trong JMC/JFR; chọn template phù hợp; xác minh event name và threshold; chỉ tăng độ chi tiết khi đã hiểu overhead.

### Dump snapshot không làm recording dừng

**Dấu hiệu:** JFR.dump xong nhưng JFR.check vẫn thấy recording đang chạy.

**Nguyên nhân:** đây là hành vi đúng của JFR.dump.

**Cách xử lý:** tiếp tục thu thập nếu cần; dùng JFR.stop khi muốn kết thúc recording.

### maxage/maxsize không có tác dụng

**Dấu hiệu:** dữ liệu không được giới hạn như mong đợi.

**Nguyên nhân:** disk=false hoặc tham số không hợp lệ; maxsize nhỏ hơn maxchunksize được cấu hình.

**Cách xử lý:** xác nhận disk=true; kiểm tra JFR.configure; chọn maxsize không nhỏ hơn maxchunksize; dùng đơn vị đúng.

### Recording API không tự tạo file

**Dấu hiệu:** chương trình Java kết thúc nhưng file destination không xuất hiện.

**Nguyên nhân:** chưa gọi start, chưa đặt destination, duration chưa hết, recording bị đóng trước khi dữ liệu được ghi hoặc đường dẫn không ghi được.

**Cách xử lý:** đặt setDestination trước start; đặt setDuration trước start; chờ quá duration; kiểm tra IOException và quyền ghi; nếu không dùng destination, gọi stop rồi dump(Path).

## 17. Quy trình vận hành đề xuất

### Profiling có mục tiêu

1. Xác định thao tác hoặc workload cần đo.
2. Chọn profile hoặc event settings phù hợp.
3. Đặt duration bao trọn workload.
4. Chỉ định filename duy nhất và thư mục đủ dung lượng.
5. Bắt đầu recording.
6. Kiểm tra bằng JFR.check.
7. Chờ tự dừng hoặc stop sớm với filename.
8. Xác minh file và mở bằng JMC.
9. Ghi lại settings, duration, JDK version và workload.

### Theo dõi liên tục production

1. Chọn default/Continuous template.
2. Bắt đầu recording từ startup hoặc attach bằng jcmd.
3. Đặt maxage và maxsize hữu hạn.
4. Bật dumponexit nếu cần giữ recording khi JVM shutdown.
5. Theo dõi trạng thái recording và dung lượng repository.
6. Khi alert xảy ra, dump cửa sổ dữ liệu gần nhất.
7. Giữ recording tiếp tục nếu còn cần theo dõi.
8. Dừng recording khi không còn mục tiêu thu thập.
9. Phân tích file và lưu trữ theo retention policy.

### So sánh trước và sau thay đổi

1. Chọn cùng template và event settings.
2. Chọn duration tương đương.
3. Giữ workload, warm-up và môi trường gần giống nhau.
4. Ghi riêng từng file, đặt tên có phiên bản và timestamp.
5. So sánh cùng nhóm event trong JMC.
6. Phân biệt thay đổi thật của ứng dụng với khác biệt do cấu hình recording.

## 18. Checklist về thời lượng recording

### Trước khi start

- [ ] Xác định mục tiêu: profiling cố định hay theo dõi liên tục.
- [ ] Chọn template default hoặc profile.
- [ ] Chọn duration đủ bao trọn tình huống nếu là time-fixed.
- [ ] Chọn delay nếu muốn trì hoãn thời điểm bắt đầu.
- [ ] Chọn maxage/maxsize nếu recording liên tục.
- [ ] Kiểm tra disk=true khi dùng maxage/maxsize.
- [ ] Xác định filename và thư mục output.
- [ ] Kiểm tra dung lượng, quota và quyền ghi.
- [ ] Xem event settings, threshold và period.

### Trong khi recording

- [ ] Xác nhận đúng JVM PID và recording name.
- [ ] Dùng JFR.check để xem trạng thái.
- [ ] Theo dõi dung lượng repository.
- [ ] Dump snapshot bằng JFR.dump nếu cần mà vẫn muốn recording tiếp tục.
- [ ] Không nhầm duration với event threshold.
- [ ] Không dừng recording trước khi lưu dữ liệu cần thiết.

### Sau khi recording

- [ ] Xác nhận recording đã dừng hoặc vẫn tiếp tục theo mục tiêu.
- [ ] Xác nhận file .jfr tồn tại và có kích thước hợp lý.
- [ ] Dùng jfr summary hoặc JMC để kiểm tra file.
- [ ] Ghi lại duration thực tế, template và event settings.
- [ ] Đối chiếu thời gian recording với incident timeline.
- [ ] Bảo vệ file và áp dụng retention policy.
- [ ] So sánh recording dưới điều kiện workload tương đương.

## 19. Tài liệu tham khảo chính thức

- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — JFR.start, duration, delay, maxage, maxsize, JFR.check, JFR.dump và JFR.stop.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — tùy chọn -XX:StartFlightRecording, duration, delay, filename, maxage, maxsize và dumponexit.
- [Recording — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html) — setDuration, setMaxAge, setMaxSize, setDestination, scheduleStart, start, stop và dump.
- [Flight Recorder — JDK Mission Control User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/8/user-guide/using-jdk-flight-recorder.html) — time-fixed/continuous recording, template, duration và quản lý recording bằng JMC.
- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — các cách tạo Flight Recording từ JMC, startup flags và diagnostic command.
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html) — event, threshold, overhead và cách dùng recording để tìm bottleneck.

Thời lượng recording quyết định JFR thu thập trong bao lâu; maxage và maxsize quyết định dữ liệu lịch sử nào còn được giữ; event settings quyết định loại event và mức chi tiết. Chọn ba yếu tố này cùng nhau để thu đúng cửa sổ sự cố, giữ đủ bằng chứng và kiểm soát overhead cùng dung lượng lưu trữ.
