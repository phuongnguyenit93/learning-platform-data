# Chọn mức quan sát phù hợp và bảo vệ dữ liệu nhạy cảm trong bản ghi JFR

Java Flight Recorder (JFR) là hệ thống ghi nhận sự kiện của JVM và ứng dụng. Nó giúp quan sát garbage collection, cấp phát bộ nhớ, hoạt động thread, khóa, I/O, exception và các sự kiện do ứng dụng tự định nghĩa. JFR được tích hợp trong JDK và có thể ghi liên tục với chi phí tương đối thấp khi cấu hình phù hợp.

Ghi càng nhiều sự kiện, càng nhiều stack trace và càng chi tiết thì bản ghi càng hữu ích cho một số cuộc điều tra, nhưng cũng có thể tăng overhead, dung lượng lưu trữ và lượng dữ liệu nhạy cảm xuất hiện trong file. Vì vậy, người vận hành cần chọn **mức quan sát vừa đủ cho câu hỏi đang điều tra**, đặt thời gian và giới hạn recording, đồng thời coi file JFR như dữ liệu vận hành có thể chứa thông tin nhạy cảm.

Bài học này tập trung vào cách chọn cấu hình JFR trong Java 17, điều chỉnh event và threshold, thu thập bản ghi có thời hạn, kiểm tra dữ liệu trước khi chia sẻ và thiết kế custom event an toàn.

## 1. JFR ghi lại điều gì?

JFR ghi nhận các sự kiện có cấu trúc theo thời gian. Mỗi event có thể chứa timestamp, duration, thread, stack trace và các trường dữ liệu tùy loại event.

Một số nhóm sự kiện thường dùng:

| Nhóm | Ví dụ thông tin có thể quan sát | Câu hỏi thường trả lời |
| --- | --- | --- |
| JVM và GC | Chu kỳ GC, pause, heap summary, safepoint | GC có gây pause dài? Heap thay đổi thế nào? |
| Allocation | Sự kiện cấp phát object hoặc mẫu cấp phát | Class nào tạo nhiều object? Allocation có tăng bất thường? |
| Thread và CPU | Execution sample, thread start/end, thread park | Thread đang dành thời gian ở đâu? Có thread bị block? |
| Synchronization | Contended monitor, lock event | Có tranh chấp khóa hoặc chờ monitor kéo dài? |
| I/O | File read/write, socket read/write | Ứng dụng chờ I/O ở đâu? Hoạt động nào kéo dài? |
| Exception và error | Một số sự kiện exception theo cấu hình | Exception có tăng đột biến? Nó xuất hiện từ đường code nào? |
| Class loading | Nạp class và hoạt động liên quan class loader | Startup hoặc dynamic loading có bất thường? |
| Application events | Event do ứng dụng tự định nghĩa | Một thao tác nghiệp vụ mất bao lâu? Nó có thuộc loại request nào? |

JFR là hệ thống event có cấu trúc, không phải bản sao đầy đủ của mọi hoạt động trong tiến trình. Một số dữ liệu được lấy mẫu; một số event chỉ được ghi khi vượt threshold; event khác chỉ xuất hiện khi được bật. Vì vậy, không được xem file JFR là nhật ký kiểm toán đầy đủ hoặc bằng chứng rằng mọi thao tác đều đã được ghi lại.

## 2. Chọn mức quan sát: default, profile hay cấu hình tùy chỉnh

JDK 17 cung cấp hai cấu hình JFR dựng sẵn phổ biến:

- **default.jfc**: hướng tới ghi liên tục với overhead thấp. Cấu hình này phù hợp để duy trì khả năng quan sát nền trong môi trường production.
- **profile.jfc**: ghi nhiều thông tin chi tiết hơn, hữu ích khi điều tra trong khoảng thời gian giới hạn. Nó có thể tạo nhiều event và stack trace hơn, do đó overhead và dung lượng thường cao hơn.

Tên cấu hình được chọn khi khởi động recording hoặc qua JFR API. Các file cấu hình mặc định thường nằm trong thư mục JDK dưới `lib/jfr/`, nhưng đường dẫn cụ thể phụ thuộc nơi cài JDK.

### 2.1. So sánh mức quan sát

| Mức | Khi nào chọn | Đặc điểm | Cách quản lý |
| --- | --- | --- | --- |
| Baseline liên tục | Muốn có dữ liệu nền để xem xu hướng hoặc điều tra sự cố vừa xảy ra | Dùng default settings, giới hạn kích thước và thời gian lưu | Recording liên tục dạng disk hoặc theo chính sách vận hành |
| Điều tra có mục tiêu | Đã có giả thuyết như GC pause, lock contention hoặc socket latency | Bật event liên quan, điều chỉnh threshold và stack trace | Ghi trong một khoảng thời gian xác định |
| Profile chi tiết | Chưa rõ nguyên nhân, cần quan sát rộng hơn trong thời gian ngắn | Dùng profile settings hoặc cấu hình chi tiết hơn | Giới hạn duration, max size và quyền truy cập file |
| Chẩn đoán đặc thù ứng dụng | Cần đo một thao tác nghiệp vụ hoặc một loại event riêng | Tạo custom event và chỉ ghi trường cần thiết | Có schema, sampling và chính sách dữ liệu rõ ràng |

Không nên bật profile chi tiết vĩnh viễn chỉ để “có càng nhiều dữ liệu càng tốt”. Hãy xác định câu hỏi trước, rồi chọn cấu hình phù hợp.

### 2.2. Một quy trình chọn mức quan sát

~~~text
Xác định câu hỏi cần trả lời
            |
            v
Có baseline JFR phù hợp?
       /            \
     Có              Chưa
     |                |
     v                v
Xem baseline       Chọn default hoặc profile
     |                |
     v                v
Còn thiếu dữ liệu?  Chỉ bật event liên quan
     |                |
     +------> Điều chỉnh threshold/stack trace
                      |
                      v
             Ghi trong khoảng có giới hạn
                      |
                      v
             Kiểm tra dữ liệu và bảo vệ file
~~~

Ví dụ:

- Nếu cần xem GC pause trong production, bắt đầu với default recording và kiểm tra các event GC.
- Nếu cần tìm allocation nóng, dùng profile settings trong khoảng tải có thể tái hiện hoặc bật event allocation có chọn lọc.
- Nếu cần tìm lock contention, tập trung vào event monitor/lock và stack trace, đồng thời đặt threshold phù hợp.
- Nếu cần đo thời gian một nghiệp vụ, cân nhắc custom event thay vì ghi payload của request.

## 3. Các thành phần của cấu hình JFR

Một JFR configuration là tập hợp thiết lập cho từng event. Các thiết lập thường gặp:

| Setting | Tác dụng |
| --- | --- |
| enabled | Bật hoặc tắt event. |
| threshold | Chỉ ghi event có duration đạt ngưỡng, áp dụng cho event có thời lượng. |
| stackTrace | Có ghi stack trace cho event hay không. |
| period | Khoảng thời gian lấy mẫu hoặc phát event định kỳ, tùy event. |
| cutoff | Giới hạn duration của event trong những trường hợp event hỗ trợ. |
| throttle | Giới hạn tốc độ ghi event trong những trường hợp event hỗ trợ. |

Không phải mọi setting đều có ý nghĩa cho mọi event. Ví dụ, threshold chủ yếu hữu ích với event có duration; period phù hợp với event định kỳ hoặc event lấy mẫu. Hãy xem metadata và cấu hình event cụ thể thay vì áp dụng một setting cho mọi loại.

### 3.1. Event threshold

Threshold giúp loại bỏ các event quá ngắn để giảm nhiễu và giảm lượng dữ liệu. Ví dụ, nếu đang điều tra I/O chậm, chỉ ghi những thao tác có thời gian từ 20 ms trở lên:

~~~bash
jfr configure --input profile.jfc --output io-investigation.jfc \
    jdk.SocketRead#enabled=true \
    jdk.SocketRead#threshold=20ms
~~~

Lệnh tạo một file cấu hình mới từ profile settings, bật event SocketRead và đặt threshold 20 ms. Sau đó dùng file cấu hình này với tùy chọn settings của recording. Cú pháp event-setting của lệnh configure giúp chỉnh một vài event mà không phải tự viết lại toàn bộ XML.

Threshold quá cao có thể bỏ lỡ các thao tác chậm vừa phải hoặc nhiều thao tác nhỏ cộng dồn thành độ trễ lớn. Threshold quá thấp có thể tạo rất nhiều event. Chọn ngưỡng dựa trên latency mục tiêu và phân phối thời gian thực tế.

### 3.2. Stack trace

Stack trace giúp biết đường gọi dẫn tới event. Nó đặc biệt hữu ích khi điều tra allocation, lock contention, I/O hoặc exception.

Stack trace cũng làm bản ghi lớn hơn và có thể tiết lộ:

- tên class và package nội bộ;
- tên phương thức, module hoặc framework;
- cấu trúc ứng dụng và các thành phần tích hợp;
- đường dẫn code hoặc chi tiết triển khai không nên công khai.

Chỉ bật stack trace cho event cần truy nguyên nguồn gốc. Nếu câu hỏi chỉ là “GC pause kéo dài bao lâu?”, stack trace cho mọi event không nhất thiết đem lại giá trị tương ứng.

### 3.3. Period và sampling

Một số event được ghi theo chu kỳ hoặc lấy mẫu. Period ngắn hơn có thể tăng độ phân giải nhưng làm tăng số event và overhead. Period dài hơn giảm lượng dữ liệu nhưng có thể bỏ qua những biến động ngắn.

Sampling không giống ghi lại mọi lần thực thi. Ví dụ execution sampling giúp ước lượng thread thường chạy ở đâu; nó không phải trace chính xác của mọi method invocation.

## 4. Chọn event theo câu hỏi điều tra

Hãy bắt đầu từ triệu chứng và chọn nhóm event liên quan:

| Triệu chứng | Event/nhóm nên xem xét | Gợi ý cấu hình |
| --- | --- | --- |
| Request latency tăng | Execution samples, socket/file I/O, thread park, lock contention | Bật stack trace cho event liên quan; threshold gần ngưỡng latency cần điều tra |
| GC pause dài | GarbageCollection, GCPhasePause, heap summary, allocation | Bắt đầu từ default; profile nếu cần phân tích chi tiết |
| Heap tăng theo thời gian | Old object/heap statistics, allocation samples, class histogram hỗ trợ | Kết hợp JFR với heap dump khi cần tìm retention path |
| CPU tăng | Execution sampling, thread events | Sampling đủ chi tiết cho khoảng điều tra; tránh ghi mọi event không liên quan |
| Lock contention | JavaMonitorEnter/Wait hoặc event đồng bộ phù hợp | Dùng threshold và stack trace để tìm điểm tranh chấp |
| I/O chậm | FileRead/FileWrite, SocketRead/SocketWrite | Lọc event dài và kiểm tra host/path trước khi chia sẻ |
| Startup chậm | Class loading, module loading liên quan, thread và file I/O | Ghi từ lúc khởi động nếu cần phân tích startup |
| Nghi ngờ lỗi trong một thao tác nghiệp vụ | Custom event có duration và mã phân loại không nhạy cảm | Chỉ ghi metadata tối thiểu, không ghi payload hoặc bí mật |

Tên event chính xác và setting hỗ trợ được liệt kê trong metadata JFR của runtime. Có thể dùng công cụ `jfr metadata` để xem event có sẵn trong JDK đang chạy.

## 5. Ghi JFR bằng command line và jcmd

### 5.1. Bắt đầu recording khi khởi động JVM

Có thể bật JFR ngay khi chạy ứng dụng:

~~~bash
java -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=6h,maxsize=256m,dumponexit=true \
    -jar app.jar
~~~

Ý nghĩa:

- `name=baseline`: tên recording.
- `settings=default`: dùng cấu hình mặc định có sẵn.
- `disk=true`: recording có thể ghi dữ liệu ra disk.
- `maxage=6h`: giới hạn tuổi dữ liệu giữ trong recording dạng vòng.
- `maxsize=256m`: giới hạn dung lượng recording.
- `dumponexit=true`: dump recording khi JVM kết thúc bình thường.

Các giá trị trên chỉ là ví dụ. Chọn giới hạn theo dung lượng đĩa, thời gian điều tra, mức event và chính sách lưu trữ của môi trường.

### 5.2. Bắt đầu recording trên JVM đang chạy

Tìm process:

~~~bash
jcmd
~~~

Khởi động recording có thời hạn:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=5m filename=/secure/jfr/incident.jfr
~~~

Ví dụ này ghi trong năm phút bằng profile settings. Thư mục /secure/jfr phải tồn tại, được bảo vệ quyền truy cập và có đủ dung lượng. Trên Windows, dùng đường dẫn hợp lệ của hệ điều hành và ACL phù hợp.

Với recording chạy liên tục, có thể không đặt duration; khi cần thì dump và stop bằng các lệnh tương ứng.

### 5.3. Kiểm tra và quản lý recording

~~~bash
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=incident filename=/secure/jfr/incident-now.jfr
jcmd <pid> JFR.stop name=incident
~~~

- `JFR.check` liệt kê trạng thái recording đang hoạt động.
- `JFR.dump` ghi dữ liệu hiện có ra file.
- `JFR.stop` dừng recording theo tên.

Nếu recording đã được cấu hình duration và tự kết thúc, kiểm tra trạng thái trước khi dump hoặc stop. Không nên giả định mọi lệnh luôn thành công; hãy kiểm tra output của `jcmd`.

### 5.4. Xem tóm tắt và event trong file

JDK cung cấp công cụ `jfr`:

~~~bash
jfr summary /secure/jfr/incident.jfr
jfr metadata /secure/jfr/incident.jfr
jfr print --events jdk.GarbageCollection /secure/jfr/incident.jfr
~~~

`jfr summary` cho biết tổng quan recording và số lượng event. `jfr metadata` hiển thị metadata event. `jfr print` xuất event ra văn bản; kết quả này cũng có thể chứa thông tin nhạy cảm, nên phải được bảo vệ như file JFR gốc.

## 6. Điều chỉnh event bằng file .jfc

File .jfc là cấu hình JFR dạng XML. Có thể dùng cấu hình dựng sẵn hoặc tạo bản tùy chỉnh từ một cấu hình hiện có.

Một phần cấu hình minh họa:

~~~xml
<event name="jdk.SocketRead">
  <setting name="enabled">true</setting>
  <setting name="threshold">20 ms</setting>
  <setting name="stackTrace">true</setting>
</event>
~~~

Đoạn trên chỉ minh họa cấu trúc setting của một event; file .jfc hoàn chỉnh còn có phần tử cấu hình và metadata khác. Không nên thay toàn bộ file cấu hình chuẩn bằng một đoạn XML rút gọn.

Quy trình thực tế:

1. Sao chép cấu hình default.jfc hoặc profile.jfc từ JDK.
2. Đổi tên bản sao để phân biệt môi trường và mục tiêu.
3. Chỉ bật event cần thiết.
4. Đặt threshold, period và stackTrace phù hợp. Có thể dùng lệnh jfr configure để tạo file tùy chỉnh:

~~~bash
jfr configure --input default.jfc --output gc-focused.jfc \
    jdk.GarbageCollection#enabled=true \
    jdk.GCPhasePause#enabled=true
~~~

5. Kiểm tra cấu hình bằng runtime Java 17 mục tiêu.
6. Chạy thử trên môi trường tương tự production và đo overhead.

Ví dụ dùng file tùy chỉnh:

~~~bash
java -XX:StartFlightRecording=name=targeted,settings=/etc/myapp/jfr/io-investigation.jfc,duration=3m,filename=/secure/jfr/io.jfr \
    -jar app.jar
~~~

Không chỉnh trực tiếp file cấu hình đi kèm JDK nếu muốn giữ nguyên baseline. Hãy tạo bản riêng để việc thay đổi có thể review, version control và rollback.

## 7. Ghi JFR bằng Java API

Ứng dụng có thể tạo recording bằng API trong module `jdk.jfr`. Nếu ứng dụng dùng JPMS, module descriptor cần khai báo `requires jdk.jfr;`. Ví dụ:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;

public class RecordingExample {
    public static void main(String[] args) throws IOException {
        Configuration configuration =
                Configuration.getConfiguration("default");

        try (Recording recording = new Recording(configuration)) {
            recording.setName("targeted-operation");
            recording.setMaxAge(Duration.ofMinutes(10));
            recording.setMaxSize(128L * 1024 * 1024);
            recording.setToDisk(true);

            recording.start();
            performOperation();
            recording.stop();
            recording.dump(Path.of("recordings", "operation.jfr"));
        }
    }

    private static void performOperation() {
        // Thực hiện công việc cần quan sát.
    }
}
~~~

API cho phép cấu hình và quản lý vòng đời recording ngay trong ứng dụng. Trong ví dụ, file đích phải nằm trong thư mục đã tồn tại và được bảo vệ. try-with-resources đóng Recording sau khi xử lý xong.

### 7.1. Bật một event cụ thể qua API

Có thể thêm hoặc điều chỉnh event trong recording:

~~~java
import jdk.jfr.EventSettings;

EventSettings socketRead = recording.enable("jdk.SocketRead");
socketRead.withThreshold(Duration.ofMillis(20));
socketRead.withStackTrace();
~~~

Đoạn này giả định biến `recording` đang tham chiếu tới một Recording đã được tạo. Tên event phải tồn tại trong runtime; chỉ bật event khi nó trả lời câu hỏi đang điều tra.

### 7.2. Đặt giới hạn recording

Các giới hạn thường cân nhắc:

- maxAge: giới hạn tuổi dữ liệu trong recording.
- maxSize: giới hạn dung lượng dữ liệu recording trên disk.
- duration: giới hạn thời gian chạy trong một số cách khởi động.
- setToDisk: quyết định recording có ghi dữ liệu ra disk hay không.

Giới hạn này giúp recording liên tục không chiếm đĩa vô hạn. Tuy nhiên, khi vòng buffer quay vòng, dữ liệu cũ có thể bị loại bỏ; hãy cân nhắc khoảng thời gian sự cố có thể xảy ra và tần suất dump.

## 8. Đánh đổi giữa độ chi tiết, overhead và dung lượng

Mỗi lựa chọn quan sát có chi phí:

| Tăng mức quan sát | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Bật thêm event | Có thêm góc nhìn về JVM và ứng dụng | Tăng số event, dung lượng và chi phí xử lý |
| Giảm threshold | Thu được event ngắn hơn | Nhiều event hơn, nhiễu và overhead lớn hơn |
| Bật stack trace | Biết nguồn gọi event | Recording lớn hơn, thu lộ cấu trúc nội bộ |
| Tăng sampling frequency | Độ phân giải thời gian tốt hơn | Tăng chi phí lấy mẫu và dữ liệu |
| Ghi lâu hơn | Có thể bắt được sự cố hiếm | Tăng dung lượng, thời gian lưu và phạm vi dữ liệu nhạy cảm |
| Ghi payload custom event | Có thêm ngữ cảnh nghiệp vụ | Rủi ro cao với PII, token, dữ liệu khách hàng hoặc bí mật |

JFR được thiết kế để có overhead thấp khi dùng đúng cấu hình, nhưng không có mức overhead bằng không. Với production, hãy đo trên workload đại diện thay vì giả định mọi event setting đều miễn phí.

## 9. Vì sao file JFR có thể chứa dữ liệu nhạy cảm?

File JFR không chỉ chứa số liệu tổng hợp. Tùy event và cấu hình, nó có thể chứa metadata giúp nhận diện hệ thống hoặc người dùng:

- tên thread, tên class, package, method và stack trace;
- địa chỉ host, port hoặc thông tin kết nối từ event I/O;
- đường dẫn file hoặc tên tài nguyên;
- tên module, class loader và chi tiết cấu trúc ứng dụng;
- trường dữ liệu do custom event ghi vào;
- các giá trị cấu hình hoặc metadata khác tùy event và phiên bản runtime.

Đặc biệt, custom event có thể ghi bất kỳ chuỗi hoặc trường nào mà người viết code đưa vào. Nếu event ghi email, customer ID, URL đầy đủ, nội dung request, access token hoặc authorization header, các giá trị đó có thể xuất hiện trong bản ghi và bản xuất văn bản.

Không được giả định JFR tự động che mọi dữ liệu nhạy cảm. Cũng không nên giả định mọi file JFR đều chứa mật khẩu; dữ liệu thực tế phụ thuộc event được bật, phiên bản JDK và custom event của ứng dụng. Cách an toàn là xem recording là dữ liệu có thể nhạy cảm và kiểm tra trước khi chia sẻ.

## 10. Nguyên tắc bảo vệ dữ liệu trong bản ghi

### 10.1. Thu thập dữ liệu tối thiểu

Chỉ bật event cần thiết để trả lời câu hỏi:

- Tắt event không liên quan.
- Chỉ bật stack trace cho event cần tìm nguồn gốc.
- Đặt threshold để loại bớt event không có ý nghĩa.
- Giới hạn duration và dung lượng.
- Tránh ghi request/response body hoặc dữ liệu người dùng vào custom event.

Thu thập tối thiểu vừa giảm overhead vừa giảm lượng dữ liệu cần bảo vệ.

### 10.2. Không ghi secret vào custom event

Ví dụ không an toàn:

~~~java
@Name("com.acme.Request")
@Label("Request")
class RequestEvent extends Event {
    String userEmail;
    String authorizationHeader;
    String requestBody;
}
~~~

Các trường này có thể chứa thông tin cá nhân, credential hoặc nội dung nghiệp vụ. Không nên đưa chúng vào JFR event.

Thay bằng metadata đã được giới hạn và không nhạy cảm:

~~~java
@Name("com.acme.Request")
@Label("Request")
@Category({"Acme", "Service"})
class RequestEvent extends Event {
    String operation;
    String outcome;
    int statusCode;
}
~~~

Chỉ ghi những trường thực sự cần để phân loại sự kiện. Nếu cần liên kết các log với nhau, cân nhắc correlation ID ngẫu nhiên hoặc đã được pseudonymized theo chính sách nội bộ; không dùng email, số điện thoại hoặc access token làm correlation ID.

### 10.3. Không dùng hash đơn giản để ẩn danh dữ liệu ít entropy

Hash một email, số điện thoại hoặc mã khách hàng không tự động biến dữ liệu thành vô danh. Nếu không gian giá trị nhỏ hoặc có thể đoán, người có bản ghi có thể thử hash hàng loạt để khôi phục giá trị.

Nếu cần liên kết dữ liệu qua nhiều event:

- dùng ID ngẫu nhiên chỉ có ý nghĩa trong phạm vi recording hoặc phiên điều tra;
- hoặc dùng tokenization/HMAC với khóa được quản lý riêng, theo chính sách bảo mật của tổ chức;
- không đưa khóa, salt bí mật hoặc mapping table vào file JFR.

Chỉ sử dụng phương pháp pseudonymization đã được phê duyệt cho dữ liệu thực tế.

### 10.4. Bảo vệ file khi lưu và truyền

File JFR và file văn bản xuất từ JFR nên được xử lý như dữ liệu vận hành nội bộ:

- lưu trong thư mục riêng, quyền đọc chỉ dành cho người cần điều tra;
- tránh đặt file trong web root, thư mục public hoặc thư mục tạm có quyền quá rộng;
- áp dụng mã hóa ổ đĩa hoặc mã hóa file theo chính sách của môi trường;
- truyền qua kênh bảo mật và xác minh người nhận;
- không đính kèm vào issue công khai, chat công khai hoặc ticket không có quyền phù hợp;
- không đưa file vào kho artifact có retention không kiểm soát.

JFR không tự mã hóa file recording chỉ vì ứng dụng đang dùng TLS. Bảo vệ đường truyền và bảo vệ dữ liệu lưu trữ là hai việc riêng.

### 10.5. Đặt retention và xóa đúng lúc

Định nghĩa trước:

- thời gian lưu recording nền;
- thời gian lưu file phục vụ incident;
- người chịu trách nhiệm duyệt và xóa;
- cách xử lý bản sao trong thư mục download, máy phân tích và ticket;
- cách xác nhận bản ghi đã được loại bỏ theo quy định.

maxAge và maxSize kiểm soát dữ liệu trong recording dạng vòng; chúng không tự xóa mọi bản dump đã được tạo, bản sao đã tải xuống hoặc file văn bản xuất bằng jfr print.

### 10.6. Kiểm tra trước khi chia sẻ

Trước khi gửi JFR cho đồng nghiệp hoặc nhà cung cấp:

1. Xác định người nhận và mục đích cần phân tích.
2. Tạo bản recording có phạm vi tối thiểu nếu có thể tái hiện sự cố.
3. Kiểm tra custom event và các trường string.
4. Dùng jfr summary và jfr print trên bản sao được bảo vệ để xem loại event và dữ liệu có thể xuất hiện.
5. Loại bỏ hoặc thay thế trường nhạy cảm theo quy trình được phê duyệt.
6. Chia sẻ qua kênh có kiểm soát quyền truy cập.
7. Đặt hạn lưu và xóa các bản sao sau khi hoàn thành.

Không chỉnh sửa nhị phân file JFR bằng công cụ tùy tiện để “xóa” một trường. Nếu recording đã chứa secret, hãy coi secret đó có thể đã bị lộ tới những nơi file được sao chép; xử lý theo quy trình ứng phó tương ứng, bao gồm rotate credential khi cần.

## 11. Thiết kế custom JFR event an toàn

Custom event cho phép ứng dụng ghi dấu mốc nghiệp vụ hoặc thời gian xử lý mà không cần log toàn bộ payload.

Ví dụ:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.acme.PaymentOperation")
@Label("Payment Operation")
@Description("Thời gian xử lý thao tác thanh toán")
@Category({"Acme", "Business"})
class PaymentOperationEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Outcome")
    String outcome;

    @Label("HTTP Status")
    int statusCode;
}
~~~

Sử dụng event:

~~~java
PaymentOperationEvent event = new PaymentOperationEvent();
boolean recordingEnabled = event.isEnabled();
if (recordingEnabled) {
    event.operation = "authorize";
    event.begin();
}

try {
    authorizePayment();
    event.outcome = "success";
    event.statusCode = 200;
} catch (RuntimeException e) {
    event.outcome = "failure";
    event.statusCode = 500;
    throw e;
} finally {
    if (recordingEnabled) {
        event.end();
        event.commit();
    }
}
~~~

Event trên ghi operation, outcome và status code. Nó không ghi số thẻ, mã bảo mật, token, email, nội dung request hoặc thông tin thanh toán.

### 11.1. Kiểm tra event có được bật không

Để tránh tạo và commit event khi không được ghi, có thể kiểm tra isEnabled():

~~~java
PaymentOperationEvent event = new PaymentOperationEvent();
boolean recordingEnabled = event.isEnabled();
if (recordingEnabled) {
    event.operation = "authorize";
    event.begin();
}

try {
    authorizePayment();
} finally {
    if (recordingEnabled) {
        event.end();
        event.commit();
    }
}
~~~

Trong code production, cần giữ logic begin/end nhất quán: không gọi end nếu event chưa begin. Có thể đặt phần tạo và commit trong một helper hoặc dùng một cấu trúc rõ ràng hơn nếu nhiều nhánh xử lý.

### 11.2. Tránh ghi dữ liệu có thể tái nhận diện

Ngay cả trường như customerId, accountId, tenantName hoặc orderReference cũng có thể là dữ liệu nhạy cảm tùy chính sách và khả năng liên kết với nguồn khác.

Trước khi thêm một field custom event, hãy hỏi:

- Có thực sự cần field này để trả lời câu hỏi chẩn đoán không?
- Có thể thay bằng loại thao tác, status code, kích thước bucket hoặc ID tạm thời không?
- Giá trị có thể chứa token, PII, dữ liệu người dùng hoặc nội dung tự do không?
- Ai có thể đọc file JFR và file export?

Không đưa object tùy ý hoặc payload lớn vào custom event. Ưu tiên số, boolean, enum hoặc chuỗi đã được giới hạn giá trị.

## 12. Kiểm tra bản ghi và xuất dữ liệu có kiểm soát

### 12.1. Xem summary trước

~~~bash
jfr summary incident.jfr
~~~

Summary giúp biết event nào xuất hiện và số lượng event. Đây là bước đầu để xác định recording có chứa dữ liệu vượt phạm vi dự kiến hay không.

### 12.2. Chỉ xuất event cần thiết

~~~bash
jfr print --events jdk.GarbageCollection incident.jfr
~~~

Chỉ xuất nhóm event liên quan thay vì dump toàn bộ recording ra console hoặc file text. Dữ liệu xuất vẫn có thể chứa metadata nhạy cảm.

### 12.3. Giới hạn đầu ra

Khi cần chia sẻ, tạo bản phân tích chỉ gồm:

- khoảng thời gian liên quan;
- event cần thiết;
- số liệu tổng hợp;
- stack trace đã được xem xét;
- thông tin môi trường ở mức cần thiết.

Nếu công cụ phân tích hỗ trợ lọc theo thời gian hoặc event, hãy dùng bộ lọc để giảm phạm vi. Không đưa toàn bộ recording vào nơi lưu trữ công khai chỉ vì file đã được nén.

## 13. Kiểm tra overhead và chất lượng dữ liệu

Sau khi tạo cấu hình mới, kiểm tra cả chi phí và khả năng trả lời câu hỏi:

### 13.1. Đo overhead

So sánh workload trước và sau khi bật recording:

- throughput;
- p50/p95/p99 latency;
- CPU usage;
- allocation rate;
- GC pause và GC CPU;
- dung lượng recording theo phút;
- I/O ghi file JFR.

Thử nghiệm trong điều kiện tải đại diện. Một recording ngắn trên máy developer không đủ để kết luận overhead production.

### 13.2. Kiểm tra recording có đủ dữ liệu không

Một bản ghi quá nhẹ có thể không chứa event cần thiết. Kiểm tra:

- event cần điều tra có được bật không;
- threshold có quá cao không;
- recording có bao phủ thời điểm xảy ra sự cố không;
- stack trace có được bật ở event cần thiết không;
- maxAge/maxSize có làm mất dữ liệu cũ trước khi dump không;
- sampling period có đủ độ phân giải không.

Nếu thiếu dữ liệu, điều chỉnh có mục tiêu rồi ghi lại. Không nên bật mọi event cùng lúc như phản ứng mặc định.

### 13.3. Dùng JFR cùng các nguồn quan sát khác

JFR bổ sung cho metrics, logs, traces và heap dump:

| Nguồn | Mạnh ở điểm nào |
| --- | --- |
| Metrics | Xu hướng tổng hợp, alert, so sánh theo thời gian. |
| Application logs | Ngữ cảnh nghiệp vụ và thông báo do ứng dụng chủ động ghi. |
| Distributed traces | Đường đi của request qua nhiều service. |
| JFR | Chi tiết sự kiện JVM, thread, GC, allocation, I/O và custom event. |
| Heap dump | Object đang được giữ lại và đường dẫn tới GC roots tại thời điểm dump. |

Không có một nguồn nào thay thế hoàn toàn các nguồn còn lại. Chọn công cụ theo câu hỏi và bảo vệ dữ liệu theo cùng một chính sách.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Recording quá lớn | Dùng profile quá lâu, nhiều event hoặc stack trace. | Dùng default cho baseline, giới hạn duration/maxSize/maxAge và bật event có chọn lọc. |
| Không thấy event cần điều tra | Event bị tắt, threshold quá cao hoặc recording không bao phủ thời điểm sự cố. | Kiểm tra metadata/settings, hạ threshold có mục tiêu và ghi lại. |
| Recording gây overhead cao hơn dự kiến | Event quá chi tiết, sampling quá dày hoặc nhiều stack trace. | Đo workload, tắt event không liên quan và giảm độ chi tiết. |
| File JFR bị mất dữ liệu cũ | Recording dạng vòng đạt maxAge hoặc maxSize. | Điều chỉnh retention và dump sớm hơn theo quy trình incident. |
| Không thể tạo file recording | Thư mục không tồn tại, thiếu quyền hoặc hết dung lượng. | Kiểm tra path, ACL/quyền, dung lượng và output của jcmd. |
| File JFR có dữ liệu không nên chia sẻ | Event I/O, stack trace hoặc custom event chứa metadata nhạy cảm. | Hạn chế người đọc, kiểm tra bản ghi, tạo bản tối thiểu và xử lý theo chính sách dữ liệu. |
| Secret xuất hiện trong custom event | Code ghi trực tiếp token, payload hoặc thông tin cá nhân. | Dừng ghi field đó, sửa schema event và xử lý bản ghi cũ như dữ liệu có thể bị lộ. |
| File jfr print chứa nhiều thông tin hơn dự kiến | Xuất toàn bộ event và trường metadata. | Chỉ xuất event cần thiết và kiểm tra đầu ra trước khi chia sẻ. |
| Không biết nên dùng default hay profile | Chưa xác định câu hỏi điều tra. | Xác định triệu chứng; bắt đầu bằng baseline, nâng mức trong khoảng thời gian ngắn nếu thiếu dữ liệu. |
| JFR không có stack trace | Setting stackTrace bị tắt hoặc event không hỗ trợ. | Kiểm tra setting của đúng event; chỉ bật stack trace ở nơi cần thiết. |
| Cấu hình .jfc không được áp dụng | Sai đường dẫn, cấu hình không hợp lệ hoặc tên setting/event sai. | Kiểm tra file, runtime metadata và output khi khởi động. |
| Nghĩ JFR là audit log đầy đủ | Event có thể được lấy mẫu, lọc theo threshold hoặc tắt. | Dùng audit log chuyên dụng cho yêu cầu kiểm toán; JFR dùng chẩn đoán. |

## 15. Checklist trước khi bật recording trên production

Trước khi triển khai, xác định rõ:

- Câu hỏi vận hành nào cần trả lời?
- Có thể dùng default settings hay cần profile/custom?
- Event nào thực sự cần thiết?
- Threshold, period và stack trace có phù hợp?
- Recording chạy bao lâu và giới hạn maxAge/maxSize là gì?
- File được lưu ở đâu, ai có quyền đọc?
- File có thể chứa hostname, path, stack trace, ID hoặc custom field nhạy cảm nào?
- Có cần pseudonymize hoặc loại field trước khi chia sẻ?
- Có quy trình kiểm tra, truyền, lưu và xóa file không?
- Overhead đã được đo trên workload đại diện chưa?

Checklist này nên được đưa vào runbook của nhóm vận hành để người trực sự cố có thể tạo recording nhanh nhưng vẫn bảo vệ dữ liệu.

## 16. Bài tập tự luyện

### Bài 1 — Chọn mức recording

Một dịch vụ production cần giữ khả năng xem lại GC và thread activity trong sáu giờ gần nhất. Khi sự cố xảy ra, nhóm có thể bật profile trong ba phút.

Hãy chọn cấu hình baseline và cấu hình incident. Giải thích vì sao không nên dùng profile chi tiết liên tục nếu default đã đủ cho baseline.

### Bài 2 — Chọn threshold

API có mục tiêu p99 là 300 ms. Nhóm nghi ngờ socket read kéo dài. Hãy đề xuất cách chọn threshold ban đầu và cách điều chỉnh sau khi xem số liệu. Vì sao không nên mặc định threshold bằng 0?

### Bài 3 — Bảo vệ custom event

Một developer muốn ghi userEmail, authorizationHeader, requestBody, tenantId và duration vào custom event. Hãy xác định trường nào nên bỏ, trường nào có thể thay bằng metadata ít nhạy cảm hơn và vì sao.

### Bài 4 — Điều tra recording bị thiếu event

File JFR không có event socket read. Hãy liệt kê những điều cần kiểm tra: event setting, threshold, recording duration, event metadata và cách dump recording.

### Bài 5 — Xử lý file JFR trước khi gửi

Một nhà cung cấp cần xem recording để hỗ trợ incident. Hãy lập quy trình từ việc xác định người nhận, chọn event, kiểm tra dữ liệu, tạo bản tối thiểu, truyền file và đặt retention.

### Bài 6 — Phân biệt JFR và audit log

Giải thích vì sao JFR không nên là nguồn duy nhất cho yêu cầu kiểm toán cần ghi nhận mọi giao dịch. Nêu vai trò phù hợp của JFR, application log và audit log.

## 17. Ghi nhớ khi chọn mức quan sát và bảo vệ JFR

- Dùng default.jfc cho baseline liên tục; cân nhắc profile.jfc hoặc custom settings cho điều tra ngắn hạn.
- Chọn event từ câu hỏi chẩn đoán; không bật mọi event theo mặc định.
- Điều chỉnh threshold, period và stack trace theo nhu cầu, vì độ chi tiết tăng có thể làm tăng overhead và dung lượng.
- Đặt duration, maxAge và maxSize để recording không chiếm tài nguyên vô hạn.
- Dùng jcmd để start/check/dump/stop recording và jfr summary, jfr metadata, jfr print để xem dữ liệu.
- JFR có thể chứa hostname, path, stack trace, metadata kết nối và dữ liệu từ custom event; không giả định file đã được tự động che dữ liệu nhạy cảm.
- Không ghi password, token, authorization header, request body hoặc PII vào custom event.
- Ưu tiên metadata tối thiểu, giá trị phân loại có giới hạn và ID tạm thời đã được phê duyệt.
- Bảo vệ file JFR và bản xuất văn bản bằng quyền truy cập, mã hóa, kênh truyền an toàn và retention rõ ràng.
- Kiểm tra recording trước khi chia sẻ; nếu secret đã được ghi, xử lý theo quy trình ứng phó và rotate credential khi cần.
- Đo overhead trên workload đại diện và kiểm tra recording có đủ event để trả lời câu hỏi.
- JFR phục vụ chẩn đoán runtime; không thay thế metrics, distributed tracing hoặc audit log đầy đủ.

### Tài liệu tham khảo

- [Java SE 17 JFR Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-runtime-guide.html) — quản lý recording trong runtime.
- [Java SE 17 JFR Configuration](https://docs.oracle.com/en/java/javase/17/jfapi/configuration.html) — cấu hình event và file JFC.
- [Java SE 17 JFR API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — Recording, Event, EventSettings và custom event.
- [Java SE 17 jcmd documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html) — lệnh JFR.start, JFR.check, JFR.dump và JFR.stop.
- [Java SE 17 jfr tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html) — summary, metadata, print và thao tác với file recording.
- [JEP 328: Flight Recorder](https://openjdk.org/jeps/328) — kiến trúc và mục tiêu của JFR.
- [JEP 349: JFR Event Streaming](https://openjdk.org/jeps/349) — streaming event JFR.
