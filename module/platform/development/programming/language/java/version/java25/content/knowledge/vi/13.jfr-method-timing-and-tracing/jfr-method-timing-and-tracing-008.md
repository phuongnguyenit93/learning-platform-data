# Thiết kế quy trình bật ngắn hạn, thu thập bằng chứng và tắt cấu hình chẩn đoán

## 1. Mục tiêu: chẩn đoán có thời hạn và để lại bằng chứng có thể kiểm tra

Khi một service Java gặp hiện tượng tăng latency, CPU cao, lock contention hoặc I/O bất thường, nhóm vận hành cần thu thập dữ liệu đủ chi tiết để tìm nguyên nhân. Bật mọi event, giữ recording vô thời hạn hoặc thêm logging dày đặc có thể làm tăng overhead, tạo dữ liệu nhạy cảm và khiến chính hoạt động chẩn đoán trở thành rủi ro vận hành.

**JDK Flight Recorder (JFR)** là framework thu thập event tích hợp trong JVM. JFR có thể bắt đầu recording khi JVM khởi động hoặc khi ứng dụng đang chạy, ghi event có timestamp, giới hạn thời lượng và dung lượng, rồi xuất file để phân tích sau. Quy trình tốt phải trả lời được bốn câu hỏi:

1. Cần bật loại dữ liệu nào để kiểm chứng giả thuyết?
2. Bật ở đâu, trong bao lâu và với giới hạn tài nguyên nào?
3. Bằng chứng được lưu, kiểm tra và chia sẻ như thế nào?
4. Làm sao xác nhận recording đã dừng và cấu hình tạm thời đã được thu hồi?

Bài **Thiết kế quy trình bật ngắn hạn, thu thập bằng chứng và tắt cấu hình chẩn đoán** thuộc chương **Đo và truy vết JFR** trong module **JAVA_VERSION_JAVA25**. Nội dung sử dụng JFR, `jcmd`, `jfr`, JDK Mission Control (JMC) và JFR API chính thức trong Java 25. Các hướng dẫn ưu tiên cấu hình theo từng recording, thu thập trong một khoảng thời gian xác định và lưu lại metadata đủ để kiểm tra kết quả.

### Sau bài này, bạn có thể

1. Phân biệt JFR recording, event setting, recording template và cấu hình JVM.
2. Chọn `default.jfc` hay `profile.jfc` theo mục tiêu và mức overhead.
3. Khởi động recording ngắn hạn lúc JVM start hoặc attach vào JVM đang chạy.
4. Dùng `JFR.check`, `JFR.dump` và `JFR.stop` đúng ngữ nghĩa, tránh vô tình làm mất dữ liệu.
5. Thu thập method samples, duration events, lock, thread, allocation, GC và I/O theo câu hỏi điều tra.
6. Tạo custom JFR duration event cho một operation nghiệp vụ có chọn lọc.
7. Lưu file `.jfr`, kiểm tra tính toàn vẹn, phân tích bằng CLI/JMC và ghi nhận metadata.
8. Dừng đúng recording, kiểm tra các recording còn chạy và khôi phục mọi cấu hình chẩn đoán tạm thời.
9. Kiểm soát overhead, quyền truy cập, dữ liệu nhạy cảm và vòng đời file evidence.

> **Phạm vi phiên bản:** bài sử dụng JFR và công cụ chẩn đoán của JDK 25 HotSpot. JFR là công nghệ chính thức trong JDK. Các ví dụ không yêu cầu preview API, không dựa vào cờ legacy để bật profiler và không thay thế công cụ tracing phân tán của framework. Tên event và mức overhead cần được kiểm tra theo JDK distribution, event metadata và workload thực tế.

## 2. JFR recording, event và settings khác nhau thế nào?

JFR là framework thu thập event tích hợp trong JVM. Một **recording** là phiên thu thập có cấu hình và vòng đời riêng. Trong recording, JFR chỉ ghi những event được bật theo settings tương ứng.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| JFR runtime | Cơ chế ghi event trong JVM | Flight Recorder của HotSpot |
| Recording | Một phiên thu thập có tên, thời lượng, giới hạn và trạng thái | `incident-2026-11-27` |
| Event | Dữ liệu được ghi với timestamp, duration hoặc payload | `jdk.ExecutionSample`, `jdk.JavaMonitorEnter` |
| Event setting | Điều khiển event có được ghi, threshold, period, stack trace | `jdk.JavaMonitorEnter#threshold=10ms` |
| JFC configuration | Tập hợp event settings có tên | `default.jfc`, `profile.jfc` |
| Recording file | File chứa dữ liệu đã ghi | `incident.jfr` |
| JFR CLI/JMC | Công cụ đọc, xem và phân tích file | `jfr summary`, JDK Mission Control |

Một recording có thể chạy đồng thời với recording khác. Khi một recording dừng, các recording còn lại vẫn có thể tiếp tục thu thập event của chúng. Vì vậy, cần đặt tên riêng và chỉ dừng đúng recording do mình tạo.

### 2.1. Event có ba dạng thời gian thường gặp

| Dạng event | Cách ghi | Ví dụ câu hỏi |
| --- | --- | --- |
| Instant event | Ghi một thời điểm xảy ra | Thread bị park, exception hoặc trạng thái thay đổi khi nào? |
| Duration event | Có thời điểm bắt đầu và kết thúc | Lock wait, socket read hoặc operation mất bao lâu? |
| Sample event | Lấy snapshot theo chu kỳ | Thread đang thực thi method nào trong các thời điểm được chọn? |

Không nên nhầm **sample** với **method timing**. `jdk.ExecutionSample` cho biết stack xuất hiện tại các thời điểm được lấy mẫu; nó không đo chính xác duration của từng invocation. Nếu cần đo duration của một operation nghiệp vụ, hãy dùng duration event phù hợp hoặc tạo custom event ở boundary có chọn lọc.

### 2.2. Vòng đời recording

~~~mermaid
stateDiagram-v2
    [*] --> New
    New --> Running: start / JFR.start
    Running --> Stopped: stop / JFR.stop
    Running --> Stopped: hết duration
    Stopped --> Closed: close / giải phóng
    Closed --> [*]
~~~

Với recording do `jcmd` quản lý, các lệnh điều khiển có ý nghĩa riêng:

- `JFR.start`: tạo và bắt đầu recording.
- `JFR.check`: xem trạng thái và settings.
- `JFR.dump`: xuất snapshot dữ liệu hiện có; recording vẫn chạy.
- `JFR.stop`: dừng recording và ghi file nếu cung cấp đường dẫn đích; nếu không cung cấp file theo cú pháp stop, dữ liệu có thể bị loại bỏ.
- `JFR.configure`: thay đổi một số tham số chung của JFR; nhiều tham số chỉ có thể đặt trước khi JFR được khởi tạo.

Phần vận hành bên dưới sẽ dùng `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop` làm các bước chính.

## 3. Chọn cấu hình phù hợp trước khi bật

JDK cung cấp hai recording templates phổ biến trong thư mục `JAVA_HOME/lib/jfr`:

| Template | Mục tiêu | Đặc điểm |
| --- | --- | --- |
| `default.jfc` | Recording liên tục hoặc giám sát dài hạn | Thu thập tập event hữu ích với overhead thấp |
| `profile.jfc` | Profiling ngắn hạn khi cần nhiều chi tiết | Thu thập nhiều event hơn và có thể tạo overhead lớn hơn |

**Chọn `default.jfc`** khi cần giữ dữ liệu nền trong thời gian dài hoặc chưa biết thời điểm sự cố xảy ra. **Chọn `profile.jfc`** khi đã có giả thuyết và cần một cửa sổ profiling ngắn để quan sát method, allocation, lock hoặc I/O chi tiết hơn.

Không có một mức overhead cố định cho mọi ứng dụng. Chi phí thực tế phụ thuộc event được bật, threshold, tần suất, stack trace, workload, JDK build và môi trường chạy. Hãy đo ở staging hoặc canary trước khi dùng cấu hình dày trên production.

### 3.1. Ma trận chọn settings theo câu hỏi

| Câu hỏi | Dữ liệu nên bắt đầu xem | Ghi chú |
| --- | --- | --- |
| CPU cao, chưa biết method nóng | `jdk.ExecutionSample` | Sampling là thống kê, không phải invocation count |
| Method cụ thể mất bao lâu | Custom duration event hoặc instrumentation phù hợp | Chỉ instrument boundary cần thiết |
| Thread chờ lock | `jdk.JavaMonitorEnter` | Chọn threshold phù hợp để tránh event quá dày |
| Thread park hoặc chờ đồng bộ | `jdk.ThreadPark` | Đối chiếu thread state và call stack |
| Socket I/O chậm | `jdk.SocketRead`, `jdk.SocketWrite` | Kiểm tra threshold và payload event |
| File I/O chậm | `jdk.FileRead`, `jdk.FileWrite` | Phân biệt latency hệ thống file với xử lý sau I/O |
| GC pause | Các event GC, ví dụ `jdk.GCPhasePause` | Đối chiếu heap, allocation và throughput |
| Allocation pressure | `jdk.ObjectAllocationSample` và event allocation phù hợp | Sampling allocation không đếm mọi object |
| Virtual thread bị pin | `jdk.VirtualThreadPinned` nếu runtime hỗ trợ | Xác nhận JDK và setting thực tế |

Danh sách trên là điểm khởi đầu. Hãy xác nhận event có trong JDK đang chạy bằng `jfr metadata` hoặc JMC; không giả định mọi distribution và mọi cấu hình có cùng event settings.

### 3.2. Chỉ bật event cần thiết

Không nên bật tất cả event với threshold bằng zero chỉ vì muốn “có càng nhiều dữ liệu càng tốt”. Một event có tần suất cao hoặc stack trace sâu có thể làm recording lớn và ảnh hưởng workload.

Ví dụ, nếu giả thuyết là lock contention kéo dài, hãy bắt đầu với `jdk.JavaMonitorEnter` và threshold phù hợp. Nếu nghi ngờ socket read chậm, bật event socket tương ứng và chỉ thu thập trong một khoảng thời gian đủ đại diện.

Có thể thêm setting vào một recording mà không chỉnh file template cài trong JDK. Với `jcmd`, event setting có dạng:

~~~text
<event-name>#<setting-name>=<value>
~~~

Để thêm setting cho một event không nằm trong template, dùng dấu `+` trước tên event theo cú pháp `jcmd`:

~~~text
+com.example.OrderOperation#enabled=true
~~~

Không sửa trực tiếp `default.jfc` hoặc `profile.jfc` trong `JAVA_HOME/lib/jfr`. Nếu cần một template riêng, hãy tạo bản sao có phiên bản và review rõ ràng.

## 4. Chuẩn bị trước khi bật chẩn đoán

Một recording có ích cần gắn với một sự cố hoặc giả thuyết cụ thể. Trước khi chạy lệnh, ghi lại:

- Mã incident/ticket hoặc tên cuộc điều tra.
- Service, môi trường, instance/pod và process ID.
- JDK version, build ứng dụng và cấu hình runtime.
- Múi giờ và thời điểm bắt đầu/kết thúc dự kiến.
- Triệu chứng quan sát được: CPU, latency, error rate, lock wait hoặc I/O.
- Workload cần xuất hiện trong cửa sổ recording.
- Event settings cần bật và lý do.
- Người sở hữu recording, nơi lưu file và thời hạn lưu trữ.

### 4.1. Đảm bảo công cụ điều khiển đúng JVM

Trên cùng máy với JVM, chạy:

~~~bash
java -version
jcmd -l
jcmd <pid> VM.version
jcmd <pid> help JFR.start
~~~

Thay `<pid>` bằng PID thực tế. `jcmd` phải chạy trên cùng máy và với effective user/group phù hợp với tiến trình JVM. Trong container, PID có thể khác PID nhìn thấy từ host; `jcmd -l` không nhất thiết liệt kê process nằm trong container riêng. Khi cần, kiểm tra PID trong đúng process namespace.

Không chạy lệnh vào PID chưa xác định. Nếu nhiều instance cùng chạy một main class, dùng PID cụ thể thay vì tên class để tránh gửi diagnostic command tới nhiều process.

### 4.2. Kiểm tra recording đang chạy

~~~bash
jcmd <pid> JFR.check
~~~

Nếu có recording khác, kiểm tra tên, ID, thời lượng và settings trước khi bắt đầu recording mới. Không dừng recording do hệ thống giám sát hoặc nhóm khác sở hữu.

Muốn xem event settings chi tiết:

~~~bash
jcmd <pid> JFR.check verbose=true
~~~

Lệnh này giúp xác định event nào đã được bật và phát hiện một recording đang chạy trùng mục tiêu.

### 4.3. Chuẩn bị thư mục evidence

Ví dụ trên Windows:

~~~powershell
New-Item -ItemType Directory -Force -Path D:\jfr-evidence\INC-2026-042
~~~

Ví dụ trên Linux:

~~~bash
mkdir -p /var/tmp/jfr-evidence/INC-2026-042
~~~

Thư mục nên có quyền truy cập hạn chế. File JFR có thể chứa class names, method names, stack traces, thread names, địa chỉ I/O và payload của custom events. Xử lý file như dữ liệu chẩn đoán nội bộ, không mặc định là dữ liệu công khai.

## 5. Bắt đầu recording khi JVM đang chạy bằng jcmd

Đây là cách phù hợp khi service đã hoạt động và không cần restart.

Ví dụ bắt recording profile tối đa 5 phút, có giới hạn tuổi và kích thước dữ liệu:

~~~bash
jcmd <pid> JFR.start name=incident-INC-2026-042 settings=profile duration=5m maxage=10m maxsize=256M filename=/var/tmp/jfr-evidence/INC-2026-042/incident.jfr
~~~

Trên PowerShell:

~~~powershell
jcmd <pid> JFR.start name=incident-INC-2026-042 settings=profile duration=5m maxage=10m maxsize=256M filename=D:\jfr-evidence\INC-2026-042\incident.jfr
~~~

`duration=5m` là giới hạn an toàn để recording tự kết thúc nếu người vận hành quên dừng. `maxage` và `maxsize` giới hạn lượng dữ liệu giữ trên disk khi `disk=true` (mặc định). Giá trị `maxsize` phải tương thích với giới hạn chunk của JFR; nếu JVM có `maxchunksize` khác mặc định, kiểm tra điều kiện này trước khi chạy.

`filename` xác định file đầu ra khi recording dừng. Khi dừng thủ công, truyền lại `filename` tường minh cho `JFR.stop` để tránh nhầm lẫn hoặc bỏ mất dữ liệu.

### 5.1. Kiểm tra recording sau khi bắt đầu

~~~bash
jcmd <pid> JFR.check name=incident-INC-2026-042 verbose=true
~~~

Xác minh:

1. Tên recording đúng.
2. Trạng thái đang chạy.
3. Template `profile` hoặc settings được yêu cầu.
4. Thời lượng và giới hạn dung lượng đúng.
5. Event đặc biệt cần bật thực sự có trong settings.

Nếu `JFR.start` báo lỗi, đọc nguyên nhân và kiểm tra recording hiện tại trước khi thử lại. Không chạy nhiều recording trùng lặp chỉ vì lệnh đầu tiên trả về thông báo không rõ.

### 5.2. Bật thêm event theo mục tiêu

Ví dụ bật một event lock với threshold 10 ms trong recording ngắn:

~~~bash
jcmd <pid> JFR.start name=lock-investigation settings=profile duration=3m filename=/var/tmp/jfr-evidence/lock-investigation.jfr jdk.JavaMonitorEnter#threshold=10ms
~~~

Nếu event không có trong template, thêm setting bằng cú pháp `+`:

~~~bash
jcmd <pid> JFR.start name=order-operation settings=profile duration=3m filename=/var/tmp/jfr-evidence/order-operation.jfr +com.example.OrderOperation#enabled=true
~~~

Với event custom, class event phải được nạp bởi ứng dụng và có tên event trùng với setting. Hãy kiểm tra recording bằng `JFR.check verbose=true` hoặc đọc metadata sau khi dump.

Không dùng một lệnh mẫu cho mọi loại sự cố. Chọn event và threshold dựa trên giả thuyết, không dựa vào việc lệnh có thể chạy.

## 6. Bắt recording ngay từ lúc khởi động JVM

Nếu sự cố xảy ra trong giai đoạn startup, warm-up hoặc một khoảng thời gian sau khi ứng dụng bắt đầu, có thể cấu hình recording khi launch.

~~~bash
java -XX:StartFlightRecording:name=startup-investigation,settings=profile,delay=10s,duration=180s,filename=/var/tmp/startup-investigation.jfr -jar app.jar
~~~

Trên PowerShell:

~~~powershell
java '-XX:StartFlightRecording:name=startup-investigation,settings=profile,delay=10s,duration=180s,filename=D:\jfr-evidence\startup-investigation.jfr' -jar app.jar
~~~

Các tham số:

- `name`: tên recording.
- `settings`: template hoặc file JFC.
- `delay`: chờ trước khi bắt đầu.
- `duration`: thời gian recording.
- `filename`: file được ghi khi recording kết thúc.

Đặt `duration` hữu hạn. Tránh cấu hình recording vô thời hạn bằng `duration=0s` cho một cuộc điều tra ngắn. Nếu cần recording liên tục, phải có chính sách `maxage`, `maxsize`, nơi lưu và cơ chế dump rõ ràng.

### 6.1. Dùng default hay profile khi khởi động?

- `default`: phù hợp khi cần giữ dữ liệu nền với overhead thấp.
- `profile`: phù hợp cho cửa sổ điều tra ngắn, thu thập thêm thông tin về method và runtime.
- JFC tùy chỉnh: chỉ dùng khi có event/threshold cụ thể mà template chuẩn không đáp ứng.

Đừng bật `profile` vô thời hạn chỉ để “phòng khi có lỗi”. Nếu cần giữ dữ liệu liên tục, cân nhắc recording `default` có giới hạn và chỉ tạo một recording profile ngắn khi điều tra.

## 7. Snapshot recording mà không dừng

Đôi khi cần lấy bằng chứng tại một thời điểm nhưng vẫn muốn recording tiếp tục chạy để quan sát diễn biến sau đó. Dùng `JFR.dump`:

~~~bash
jcmd <pid> JFR.dump name=incident-INC-2026-042 filename=/var/tmp/jfr-evidence/INC-2026-042/snapshot-01.jfr
~~~

`JFR.dump` ghi dữ liệu hiện có ra file và **recording vẫn tiếp tục chạy**. Có thể dump nhiều snapshot với tên file khác nhau nếu cần so sánh các khoảng thời gian.

Có thể giới hạn khoảng dữ liệu dump bằng `begin` và `end`:

~~~bash
jcmd <pid> JFR.dump name=incident-INC-2026-042 begin=-5m filename=/var/tmp/jfr-evidence/INC-2026-042/last-five-minutes.jfr
~~~

`begin` và `end` chấp nhận thời gian theo định dạng được `java.time` phân tích hoặc cú pháp thời gian tương đối được hỗ trợ. Kiểm tra `jcmd <pid> help JFR.dump` trên đúng JDK trước khi dùng giá trị thời gian đặc biệt. Ví dụ an toàn và phổ biến là `begin=-5m` với `filename` riêng.

Không ghi đè snapshot cũ. Mỗi file cần tên thể hiện thời điểm hoặc số thứ tự để không mất bằng chứng trước đó.

## 8. Dừng recording và lưu file đúng cách

Khi đã thu thập đủ dữ liệu, dừng đúng recording:

~~~bash
jcmd <pid> JFR.stop name=incident-INC-2026-042 filename=/var/tmp/jfr-evidence/INC-2026-042/incident-final.jfr
~~~

Trên PowerShell:

~~~powershell
jcmd <pid> JFR.stop name=incident-INC-2026-042 filename=D:\jfr-evidence\INC-2026-042\incident-final.jfr
~~~

**Điểm cần nhớ:** `JFR.stop` dừng recording. Nếu không cung cấp đường dẫn file theo cú pháp stop, dữ liệu recording có thể bị loại bỏ. Luôn dùng tên recording chính xác và `filename` đích tường minh khi cần lưu evidence.

Nếu recording được cấu hình `filename` khi bắt đầu, vẫn nên nêu rõ đường dẫn đích ở lệnh stop để quy trình dễ review và tránh phụ thuộc vào giả định về cấu hình trước đó.

### 8.1. Xác nhận recording đã dừng

~~~bash
jcmd <pid> JFR.check
~~~

Kiểm tra recording mục tiêu không còn trạng thái RUNNING. Nếu còn recording khác, xác định owner và mục tiêu của chúng; không dừng tất cả recording bằng một lệnh không phân biệt.

### 8.2. Nếu recording tự hết duration

Nếu recording kết thúc theo `duration`, xác minh file đầu ra đã được tạo và có kích thước lớn hơn zero. Nếu không có file, kiểm tra `filename`, trạng thái recording, log JVM và kết quả `JFR.check` trước đó. Không mặc định recording đã được lưu chỉ vì thời lượng đã hết.

### 8.3. Phân biệt dump và stop

| Lệnh | Kết quả | Recording sau lệnh |
| --- | --- | --- |
| `JFR.check` | Xem recording và settings | Không đổi |
| `JFR.dump` | Xuất snapshot ra file | Vẫn chạy |
| `JFR.stop` | Dừng recording; lưu file nếu có filename | Đã dừng |
| `JFR.configure` | Thay tham số JFR ở cấp JVM | Không phải lệnh dừng recording |

Một lỗi vận hành thường gặp là gọi `JFR.dump` rồi tưởng recording đã dừng, hoặc gọi `JFR.stop` mà quên filename. Runbook phải ghi rõ lệnh cần chạy ở mỗi bước.

## 9. Thu thập evidence có thể kiểm tra

Một file `.jfr` là bằng chứng chính, nhưng để hiểu đúng file cần lưu metadata kèm theo:

| Metadata | Ví dụ |
| --- | --- |
| Incident ID | `INC-2026-042` |
| Service / instance | `orders-api / pod-7c9...` |
| PID | PID trong process namespace |
| JDK | `25.0.x`, vendor/build |
| App build | Git commit hoặc artifact version |
| Recording name | `incident-INC-2026-042` |
| Settings | `profile` + event overrides |
| Start/end time | ISO-8601 kèm timezone |
| Workload | số request, loại thao tác, tải ước lượng |
| File | path, size, checksum nếu quy trình yêu cầu |
| Người thu thập | owner hoặc nhóm chịu trách nhiệm |
| Giới hạn | recording ngắn, event thiếu, workload không đại diện |

Có thể dùng PowerShell kiểm tra file:

~~~powershell
Get-Item D:\jfr-evidence\INC-2026-042\incident-final.jfr |
    Select-Object FullName, Length, LastWriteTime
Get-FileHash D:\jfr-evidence\INC-2026-042\incident-final.jfr -Algorithm SHA256
~~~

Trên Linux:

~~~bash
ls -lh /var/tmp/jfr-evidence/INC-2026-042/incident-final.jfr
sha256sum /var/tmp/jfr-evidence/INC-2026-042/incident-final.jfr
~~~

Checksum giúp phát hiện file thay đổi trong quá trình chuyển giao; nó không làm file trở nên an toàn hoặc ẩn dữ liệu nhạy cảm.

### 9.1. Kiểm tra file bằng JFR CLI

~~~bash
jfr summary incident-final.jfr
jfr metadata incident-final.jfr
~~~

`jfr summary` cho biết thời lượng và số lượng event. `jfr metadata` hiển thị metadata/event schema trong recording. Nếu file không đọc được hoặc không có event mong đợi, kiểm tra lại recording trước khi kết luận.

In một số event cần thiết:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.JavaMonitorEnter,jdk.ThreadPark incident-final.jfr
~~~

Với event custom:

~~~bash
jfr print --events com.example.OrderOperation incident-final.jfr
~~~

Có thể xuất JSON khi pipeline phân tích cần định dạng máy đọc:

~~~bash
jfr print --json --events jdk.ExecutionSample incident-final.jfr
~~~

Đừng in toàn bộ recording vào terminal nếu file lớn. Lọc theo event, khoảng thời gian hoặc dùng JMC để duyệt theo bảng và call tree.

## 10. Đọc bằng chứng theo giả thuyết

Sau khi xác minh file, phân tích theo câu hỏi ban đầu. Không bắt đầu bằng việc đọc mọi event theo thứ tự.

### 10.1. CPU cao

- Mở Method Profiling hoặc hot methods trong JMC.
- Xem `jdk.ExecutionSample` và call tree.
- Tìm method xuất hiện nhiều trong stack.
- Đối chiếu với throughput, request rate và CPU metrics cùng thời điểm.
- Kiểm tra inline frames, thread state và workload.
- Không coi sample count là số lần invocation hoặc thời gian method tuyệt đối.

### 10.2. Lock contention

- Xem `jdk.JavaMonitorEnter`.
- Kiểm tra duration, monitor class và stack trace.
- Xác định thread giữ lock và thread chờ lock nếu dữ liệu có thể hiện.
- Kiểm tra threshold có loại bỏ các lần chờ ngắn hay không.
- Không hạ threshold quá thấp nếu mục tiêu chỉ là tìm contention dài.

### 10.3. I/O chậm

- Xem `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead` hoặc `jdk.FileWrite` nếu được bật.
- Đối chiếu duration với endpoint, peer, file và stack trace.
- Phân biệt thời gian chờ I/O với thời gian xử lý sau khi nhận dữ liệu.
- Không ghi payload ứng dụng nhạy cảm chỉ để tìm một socket chậm.

### 10.4. Allocation và GC

- Đối chiếu event allocation với GC events và heap behavior.
- Phân biệt allocation sample với số lượng object chính xác.
- Xem các pha GC và pause duration.
- Nếu cần đường dẫn tới GC roots, cân nhắc chi phí trước khi bật `path-to-gc-roots`; việc thu thập này tốn thời gian và chỉ nên dùng khi nghi ngờ memory leak.

### 10.5. Latency nghiệp vụ

JFR có thể ghi duration event ở application boundary. Hãy đối chiếu event đó với request/trace ID và timestamp của framework tracing. JFR không tự thay thế distributed tracing, không tự gửi context qua HTTP và không tự tạo span cho mọi method.

## 11. Method sampling không phải method timing

Một điểm quan trọng khi thu thập evidence:

- `jdk.ExecutionSample` chụp stack ở một số thời điểm.
- Duration event ghi thời gian từ `begin()` tới `end()` hoặc một operation có duration do JFR hỗ trợ.
- Custom event có thể đo thời gian của một operation nghiệp vụ cụ thể.
- Tracing framework có thể mô hình hóa quan hệ parent/child và lan truyền trace context qua service boundary.

Nếu câu hỏi là “method nào chiếm CPU?”, bắt đầu với method sampling. Nếu câu hỏi là “operation tạo hóa đơn này mất bao lâu?”, cần duration event ở boundary phù hợp. Không bật sampling dày hơn với kỳ vọng nó sẽ trở thành phép đo duration chính xác.

## 12. Tạo custom JFR duration event cho operation quan trọng

Có thể định nghĩa một event riêng để ghi thời gian của operation nghiệp vụ, ví dụ xử lý đơn hàng hoặc tạo báo cáo. Hãy instrument **boundary có ý nghĩa** thay vì bọc mọi method nhỏ; event quá dày có thể làm tăng chi phí và dung lượng.

Ví dụ event:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;

@Name("com.example.OrderOperation")
@Label("Order operation")
@Category({"Application", "Orders"})
@Description("Duration of a selected order operation")
@Threshold("20 ms")
@StackTrace(false)
public final class OrderOperationEvent extends Event {

    @Label("Operation")
    public String operation;

    @Label("Outcome")
    public String outcome;
}
~~~

Sử dụng:

~~~java
static void recordOrderOperation(String operation, Runnable action) {
    OrderOperationEvent event = new OrderOperationEvent();

    if (!event.isEnabled()) {
        action.run();
        return;
    }

    event.operation = operation;
    event.begin();

    String outcome = "failed";

    try {
        action.run();
        outcome = "success";
    } finally {
        event.end();
        event.outcome = outcome;

        if (event.shouldCommit()) {
            event.commit();
        }
    }
}
~~~

Giải thích:

1. `isEnabled()` kiểm tra có recording nào bật event này hay không.
2. Nếu event không được bật, operation chạy bình thường và không tạo event.
3. `begin()` bắt đầu đo duration.
4. `finally` luôn gọi `end()`, kể cả khi action ném exception.
5. `outcome` được ghi là `failed` nếu action thoát bất thường.
6. `shouldCommit()` kiểm tra event có được bật và có vượt threshold không.
7. `commit()` ghi event vào recording.

`@Threshold("20 ms")` chỉ lưu những operation vượt ngưỡng mặc định của event, trừ khi recording settings ghi đè threshold. `@StackTrace(false)` tránh ghi stack cho event này khi không cần; nếu cần biết call site, có thể bật stack trace trong template/settings và đánh giá overhead.

### 12.1. Bật custom event trong recording

Khi custom event đã được load, có thể bật bằng setting:

~~~bash
jcmd <pid> JFR.start name=order-operation settings=profile duration=3m filename=/var/tmp/order-operation.jfr +com.example.OrderOperation#enabled=true
~~~

Đọc file:

~~~bash
jfr print --events com.example.OrderOperation /var/tmp/order-operation.jfr
~~~

Nếu event không xuất hiện, kiểm tra class đã được load, tên event có khớp `@Name`, setting có được thêm và recording có chạy trong thời gian operation thực thi hay không.

### 12.2. Thiết kế payload an toàn

Chỉ đưa vào event những trường thực sự cần cho phân tích:

- Tên operation đã chuẩn hóa.
- Outcome như `success`, `failed`, `timeout`.
- Một số đo đã được giới hạn như item count hoặc batch size.
- Correlation ID nếu chính sách cho phép và có lợi ích điều tra.

Không đưa password, access token, session cookie, raw SQL có dữ liệu người dùng, request body hoặc secret vào event. JFR file phải được bảo vệ như một artifact chẩn đoán có thể chứa dữ liệu nội bộ.

### 12.3. Không instrument mọi method

Custom duration event phù hợp cho operation có ranh giới nghiệp vụ rõ. Nếu tạo event cho mọi getter/setter hoặc method chạy hàng triệu lần, overhead và lượng dữ liệu có thể lớn hơn lợi ích. Dùng threshold, event enable setting và một cửa sổ recording ngắn.

## 13. Tự động hóa vòng đời bằng JFR API

Ngoài `jcmd`, ứng dụng có thể điều khiển recording bằng API `jdk.jfr.Recording`. Cách này hữu ích cho một diagnostic workflow nội bộ có kiểm soát, ví dụ chỉ bật recording khi một điều kiện vận hành đã được thỏa mãn.

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;

import jdk.jfr.Configuration;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;

public final class ShortJfrCapture {

    public static void capture(Path destination, Runnable workload)
            throws IOException {

        Configuration profile = Configuration.getConfiguration("profile");

        try (Recording recording = new Recording(profile)) {
            recording.setName("short-diagnostic-capture");
            recording.setMaxAge(Duration.ofMinutes(5));
            recording.setMaxSize(256L * 1024 * 1024);
            recording.setDumpOnExit(false);
            recording.setDestination(destination);
            recording.setDuration(Duration.ofMinutes(2));

            recording.start();

            try {
                workload.run();
            } finally {
                if (recording.getState() == RecordingState.RUNNING) {
                    recording.stop();
                }
            }
        }
    }
}
~~~

Trong ví dụ, `setDestination()` chỉ định file đầu ra khi recording dừng; sau khi ghi thành công, recording tự đóng theo contract của API. `setDuration()` giới hạn thời gian tối đa. `try-with-resources` bảo đảm `close()` được gọi khi thoát khỏi block.

Đoạn code chỉ là khung tích hợp. Trong service production, không nên chạy workload dài đồng bộ bên trong một request chỉ để tạo recording. Hãy đặt lifecycle ở một component vận hành riêng, có authorization, giới hạn tần suất, timeout và audit.

### 13.1. Không vô tình dừng recording khác

Mỗi `Recording` object tạo một recording riêng. Nếu ứng dụng quản lý nhiều recording, chỉ gọi `stop()`/`close()` trên instance do workflow đó sở hữu. Không dùng một lệnh toàn cục hoặc API quản trị để dừng recording của thành phần khác.

### 13.2. Giới hạn dữ liệu giữ lại

`setMaxAge()` và `setMaxSize()` giúp giới hạn lượng dữ liệu trong repository của recording. Nếu không đặt giới hạn, recording ghi ra disk có thể tăng không giới hạn theo thời gian. Dùng giới hạn phù hợp với cửa sổ điều tra và dung lượng môi trường.

## 14. Tắt cấu hình chẩn đoán sau khi thu thập

Đây là bước thường bị bỏ quên. Hoàn tất phân tích ban đầu không có nghĩa recording vẫn nên tiếp tục chạy.

### 14.1. Dừng đúng recording

~~~bash
jcmd <pid> JFR.stop name=order-operation filename=/var/tmp/order-operation-final.jfr
jcmd <pid> JFR.check
~~~

Xác nhận recording mục tiêu không còn trong danh sách đang chạy. Nếu vẫn thấy recording, kiểm tra tên và ID; không dừng recording khác.

### 14.2. Nếu dùng JFR.start có duration

Recording sẽ tự kết thúc khi duration hết. Tuy nhiên, vẫn phải kiểm tra file đầu ra và `JFR.check`; không chỉ dựa vào đồng hồ hoặc giả định lệnh đã hoàn tất.

### 14.3. Nếu dùng JFR startup flag

Với `-XX:StartFlightRecording`, duration hữu hạn giúp recording tự dừng. Nếu flag được thêm vào script/container/manifest để điều tra, hãy xóa hoặc revert flag ở lần deploy tiếp theo nếu nó không thuộc cấu hình vận hành dài hạn.

Không cần restart JVM chỉ để “gỡ” một recording `jcmd` đã dừng. Nếu thay đổi một startup option hoặc tham số JFR chỉ được đọc khi khởi tạo, phải thay ở cấu hình khởi động và áp dụng ở lần restart/deploy phù hợp.

### 14.4. Không dùng JFR.configure như công tắc event tạm thời

`JFR.configure` thay một số tham số của JFR ở cấp JVM. Nhiều tham số như `memorysize`, `stackdepth`, `maxchunksize` không thể thay đổi sau khi JFR đã được khởi tạo. Đối với điều tra ngắn, ưu tiên event settings gắn với recording cụ thể thay vì chỉnh tham số toàn JVM.

Nếu đã thay đổi một tham số runtime khác bằng công cụ chẩn đoán, ghi lại giá trị ban đầu và khôi phục đúng giá trị sau điều tra theo khả năng của option. Một số JVM option chỉ áp dụng lúc khởi động và cần deploy/restart để hoàn nguyên.

### 14.5. Kiểm tra tất cả recording còn hoạt động

~~~bash
jcmd <pid> JFR.check verbose=true
~~~

Đối chiếu với danh sách recording trước khi bắt đầu:

- Recording do mình tạo đã dừng.
- Recording liên tục của hệ thống vẫn hoạt động nếu được yêu cầu.
- Không còn recording profile ngoài ý muốn.
- Không có recording trùng lặp do thử lệnh nhiều lần.

JFR runtime vẫn sẵn sàng cho lần điều tra sau; việc dừng recording không có nghĩa phải tắt toàn bộ JFR subsystem của JVM.

## 15. Quản lý file evidence và quyền truy cập

JFR file có thể chứa nhiều thông tin hơn một log message thông thường: tên class/method, stack trace, thread name, socket/file metadata, custom event fields và các dữ liệu runtime khác. Hãy áp dụng nguyên tắc quản lý evidence:

1. Lưu vào thư mục có ACL/quyền truy cập giới hạn.
2. Không ghi file vào thư mục public web root hoặc thư mục tạm dùng chung không kiểm soát.
3. Không đính kèm file `.jfr` vào ticket công khai hoặc gửi qua kênh chat không được phê duyệt.
4. Chỉ chia sẻ cho người cần phân tích.
5. Ghi thời hạn lưu và xóa sau khi kết thúc incident theo policy.
6. Nếu cần chia sẻ bên ngoài, thực hiện quy trình rà soát/redaction đã được tổ chức phê duyệt.
7. Không ghi secret hoặc dữ liệu cá nhân vào custom JFR events.
8. Không mặc định file đã được bảo vệ chỉ vì có phần mở rộng `.jfr`.

### 15.1. Không nhầm checksum với bảo mật

SHA-256 checksum có thể xác nhận file không bị thay đổi trong quá trình sao chép, nhưng không mã hóa nội dung. Nếu file cần lưu hoặc truyền qua ranh giới bảo mật, dùng storage encryption và access control theo policy.

### 15.2. Không giữ nhiều snapshot không cần thiết

Mỗi lần `JFR.dump` có thể tạo thêm một file. Đặt tên rõ ràng, giữ lại snapshot có ý nghĩa và xóa các bản thử nghiệm dư thừa sau khi xác nhận file cuối cùng đã đủ evidence.

## 16. Overhead và các giới hạn khi bật ngắn hạn

Một recording ngắn vẫn có thể ảnh hưởng workload. Các yếu tố chính:

- `profile.jfc` thu thập nhiều event hơn `default.jfc`.
- Stack trace dài hơn làm tăng chi phí và kích thước recording.
- Threshold quá thấp tạo nhiều duration events.
- Custom events quá dày có thể tạo lượng dữ liệu lớn.
- `path-to-gc-roots` có thể tốn thời gian và gây pause ngắn; chỉ bật khi nghi ngờ memory leak.
- Recording dài không giới hạn có thể làm tăng dung lượng disk.
- Một workload ngắn hoặc không đại diện có thể làm profile sai lệch.

### 16.1. Cách giảm overhead

- Chọn cửa sổ 1–5 phút nếu giả thuyết có thể kiểm chứng trong khoảng đó.
- Dùng `profile` khi cần chi tiết, `default` cho recording nền.
- Bật event chuyên biệt và threshold phù hợp.
- Giới hạn `maxage` và `maxsize`.
- Không tăng stack depth nếu không có lý do.
- Không bật path-to-GC-roots chỉ để “xem thêm dữ liệu”.
- Ghi trong thời điểm có workload đại diện.
- So sánh metrics trước, trong và sau recording.

### 16.2. Không coi JFR là công cụ không overhead

JFR được thiết kế để có overhead thấp và dùng được trong production với cấu hình phù hợp. Điều đó không đồng nghĩa mọi event setting đều miễn phí. Một cấu hình profile dày trong workload nhạy latency cần được đánh giá trước và theo dõi trong suốt thời gian thu thập.

## 17. Quy trình hoàn chỉnh dạng runbook

Một runbook có thể được chuẩn hóa thành các bước:

~~~mermaid
flowchart TD
    A[Xác định giả thuyết và cửa sổ] --> B[Kiểm tra PID, JDK và recording hiện có]
    B --> C[Chọn event settings và giới hạn]
    C --> D[JFR.start với tên riêng]
    D --> E[JFR.check xác minh]
    E --> F[Chờ workload tái hiện]
    F --> G[JFR.dump nếu cần snapshot]
    G --> H[JFR.stop và lưu file cuối]
    H --> I[JFR.check xác nhận đã dừng]
    I --> J[jfr summary / metadata / JMC]
    J --> K[Đối chiếu evidence và metrics]
    K --> L[Lưu metadata, checksum, quyền truy cập]
    L --> M[Khôi phục cấu hình tạm thời và dọn recording]
~~~

### Checklist trước khi bật

- [ ] Có incident hoặc giả thuyết rõ.
- [ ] Xác định đúng PID và process namespace.
- [ ] Đã kiểm tra recording khác đang chạy.
- [ ] Chọn template và event cần thiết.
- [ ] Đặt tên recording duy nhất.
- [ ] Đặt duration, maxage, maxsize.
- [ ] Xác định đường dẫn output có quyền ghi và dung lượng đủ.
- [ ] Đánh giá dữ liệu nhạy cảm và quyền truy cập.

### Checklist trong lúc thu thập

- [ ] `JFR.check` xác nhận recording đúng.
- [ ] Workload có tái hiện triệu chứng.
- [ ] Metrics ứng dụng được ghi cùng mốc thời gian.
- [ ] Có thể tạo snapshot bằng `JFR.dump` nếu cần.
- [ ] Không tạo thêm recording trùng lặp.
- [ ] Theo dõi overhead và dung lượng.

### Checklist khi kết thúc

- [ ] `JFR.stop` đúng tên recording và filename.
- [ ] `JFR.check` xác nhận recording mục tiêu đã dừng.
- [ ] File `.jfr` tồn tại và có kích thước hợp lý.
- [ ] `jfr summary` và `jfr metadata` đọc được.
- [ ] Đã lưu JDK version, app build, thời gian, settings và checksum.
- [ ] Đã phục hồi startup flags hoặc runtime diagnostics tạm thời.
- [ ] Đã xác định owner và thời hạn lưu file evidence.
- [ ] Không còn recording profile ngoài ý muốn.

## 18. Các lỗi vận hành thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Bắt đầu recording không có duration | Recording có thể chạy lâu ngoài dự kiến | Đặt duration hữu hạn và có người theo dõi |
| Dùng `profile` liên tục | Overhead và dung lượng lớn hơn cần thiết | Dùng `default` cho recording nền |
| Gọi `JFR.stop` không có filename | Có thể mất dữ liệu recording | Luôn chỉ định filename khi cần lưu |
| Gọi `JFR.dump` rồi tưởng recording đã dừng | Recording tiếp tục chạy | Kiểm tra bằng `JFR.check`, sau đó stop |
| Dừng recording không thuộc quyền sở hữu | Mất evidence của nhóm khác | Dùng tên/ID cụ thể |
| Không kiểm tra PID/container | Gửi lệnh tới sai process hoặc không tìm thấy process | Xác minh namespace và user |
| Bật quá nhiều event | File lớn và overhead cao | Chọn event theo giả thuyết |
| Bật `path-to-gc-roots` tùy tiện | Tốn thời gian, có thể pause ngắn | Chỉ bật khi điều tra memory leak |
| Ghi file vào thư mục chia sẻ rộng | Lộ stack/payload metadata | Hạn chế ACL và thời hạn lưu |
| Không ghi app build/JDK version | Khó đối chiếu hoặc tái hiện | Lưu metadata cùng recording |
| Xóa file ngay sau khi dump | Mất evidence trước khi phân tích | Xác minh và lưu theo policy |
| Dựa vào JFR sample để kết luận method duration | Diễn giải sai dữ liệu | Dùng custom duration event hoặc timing instrumentation |

## 19. Bài tập thực hành

### Bài tập A — recording ngắn bằng jcmd

Chạy một ứng dụng Java trong môi trường thử nghiệm. Dùng `jcmd -l` tìm PID, bắt recording `profile` trong ba phút, kiểm tra bằng `JFR.check`, rồi dừng với filename rõ ràng.

**Đạt khi:** file `.jfr` được tạo, `jfr summary` đọc được và recording không còn chạy.

### Bài tập B — snapshot và tiếp tục recording

Bắt recording tên `snapshot-lab`, dump một snapshot giữa quá trình chạy rồi tiếp tục workload. Cuối cùng dừng recording và lưu file cuối.

**Đạt khi:** giải thích được `JFR.dump` không dừng recording còn `JFR.stop` có dừng.

### Bài tập C — method samples và duration event

Bật `jdk.ExecutionSample` để quan sát method profile. Sau đó thêm custom `OrderOperationEvent` để đo duration một operation.

**Đạt khi:** phân biệt sample count với operation duration và chỉ bật custom event trong recording cần thiết.

### Bài tập D — khôi phục cấu hình

Tạo một recording profile ngắn và một recording khác đang hoạt động trong môi trường test. Dừng đúng recording do mình tạo, kiểm tra recording còn lại vẫn chạy.

**Đạt khi:** không dừng nhầm recording của thành phần khác và xác minh được trạng thái sau điều tra.

### Bài tập E — phân tích evidence

Dùng `jfr summary`, `jfr metadata`, `jfr print` và JMC để tìm một method nóng hoặc một lock wait kéo dài. Ghi lại giả thuyết, event, timestamp và giới hạn của kết luận.

**Đạt khi:** có thể giải thích dữ liệu dựa trên event cụ thể, không suy ra invocation count từ sampling.

### Bài tập F — thiết kế runbook

Viết runbook cho một service có latency tăng đột biến, bao gồm PID, event settings, thời lượng, giới hạn file, quyền lưu trữ, lệnh stop và cách xác nhận recording đã dừng.

**Đạt khi:** một người khác có thể thực hiện theo runbook và không để recording chẩn đoán chạy ngoài cửa sổ đã định.

### Checklist nghiệm thu cuối bài

- [ ] Phân biệt recording, event, event settings và JFC template.
- [ ] Chọn `default`/`profile` theo mục tiêu và overhead.
- [ ] Bắt đầu recording khi JVM chạy hoặc khi launch với duration hữu hạn.
- [ ] Kiểm tra recording bằng `JFR.check`.
- [ ] Biết `JFR.dump` xuất snapshot nhưng tiếp tục chạy.
- [ ] Biết `JFR.stop` dừng recording và cần filename khi muốn giữ dữ liệu.
- [ ] Đọc file bằng `jfr summary`, `jfr metadata`, `jfr print` hoặc JMC.
- [ ] Phân biệt method sampling với duration timing.
- [ ] Chỉ tạo custom event ở boundary có ý nghĩa.
- [ ] Dừng đúng recording và xác nhận không còn recording profile ngoài ý muốn.
- [ ] Khôi phục startup/runtime diagnostic settings tạm thời.
- [ ] Lưu evidence cùng metadata, checksum, quyền truy cập và thời hạn lưu.
- [ ] Không để secret hoặc payload nhạy cảm trong custom event.

## 20. Tài liệu tham khảo chính thức

1. [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): cú pháp và tùy chọn `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, `JFR.configure`.
2. [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:StartFlightRecording`, `duration`, `filename`, `settings`, `maxage` và `maxsize`.
3. [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): JFR, JMC, time-fixed recording, continuous recording và quy trình thu thập.
4. [Java SE 25 API — jdk.jfr.Recording](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình, start, stop, dump, max age, max size và close.
5. [Java SE 25 API — jdk.jfr.Event](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): custom event, begin/end/commit, `isEnabled()` và `shouldCommit()`.
6. [Java SE 25 API — jdk.jfr.Threshold](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Threshold.html): threshold cho duration event.
7. [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): phân tích recording, method profiling, event timeline và call tree.
8. [JDK Flight Recorder Event Reference for JDK 25](https://sap.github.io/jfrevents/25.html): tên event, fields và settings của JFR trên JDK 25.

**Kết quả mong đợi:** người học có thể thực hiện một cuộc điều tra JFR có giới hạn và có thể kiểm chứng: xác định đúng process, chọn event theo giả thuyết, bật recording trong thời gian ngắn, lưu và xác minh file, phân tích bằng chứng, rồi dừng đúng recording và khôi phục cấu hình chẩn đoán tạm thời. Điều quan trọng là sau khi thu thập xong, JVM không còn recording profile ngoài ý muốn và file evidence được quản lý theo chính sách của hệ thống.
