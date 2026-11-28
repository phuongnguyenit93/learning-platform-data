# Điều chỉnh chu kỳ lấy mẫu, thời lượng ghi và chi phí quan sát

## Mục tiêu bài học

**Java Flight Recorder (JFR)** là hệ thống ghi nhận sự kiện và dữ liệu chẩn đoán được tích hợp trong HotSpot JVM. JFR có thể thu thập stack sample của thread, garbage collection, allocation, lock contention, file/socket I/O và các sự kiện do ứng dụng tự định nghĩa. Để dùng JFR hiệu quả trong môi trường thật, cần kiểm soát ba nhóm thông số khác nhau:

- **Chu kỳ lấy mẫu (sampling period):** tần suất một loại sự kiện định kỳ được phát hoặc lấy mẫu.
- **Thời lượng ghi (recording duration):** khoảng thời gian recording hoạt động trước khi tự dừng.
- **Chi phí quan sát (observability overhead):** CPU, bộ nhớ, I/O và dung lượng dữ liệu phát sinh khi thu thập.

Bài **Điều chỉnh chu kỳ lấy mẫu, thời lượng ghi và chi phí quan sát** thuộc chương **Lấy mẫu JFR** của module **JAVA_VERSION_JAVA25**. Nội dung dùng API và công cụ JFR hiện hành trong Java 25, tập trung vào cấu hình có thể kiểm chứng và vận hành an toàn.

Sau bài này, bạn có thể:

1. Phân biệt sampling period, threshold, throttle và duration của recording.
2. Chọn cấu hình `default.jfc`, `profile.jfc` hoặc JFC tùy chỉnh theo mục tiêu quan sát.
3. Điều chỉnh chu kỳ của `jdk.ExecutionSample` và các periodic events mà không hiểu nhầm đây là lịch lấy mẫu thời gian thực tuyệt đối.
4. Bắt đầu, kiểm tra, dump và dừng recording bằng JVM flags hoặc `jcmd`.
5. Giới hạn thời gian và kích thước recording bằng `duration`, `maxage`, `maxsize`.
6. Đo overhead bằng benchmark có baseline, thay đổi một nhóm setting mỗi lần và nhận diện dữ liệu bị thiếu do cấu hình quá thưa.
7. Phân biệt JFR sampling thông thường với JFR CPU-time profiling thử nghiệm trên Linux trong Java 25.

> **Phiên bản:** JFR có sẵn trong HotSpot JDK hiện đại. Java 25 bao gồm các cải tiến JEP 518 (JFR Cooperative Sampling), JEP 520 (JFR Method Timing & Tracing) và JEP 509 (JFR CPU-Time Profiling, experimental). Các ví dụ chính sử dụng cấu hình JFR ổn định; tính năng CPU-time profiling được đánh dấu riêng là thử nghiệm và chỉ dành cho Linux. Không dùng tùy chọn đã lỗi thời hoặc cấu hình nội bộ của profiler bên thứ ba thay cho JFR API chính thức.

## 1. Ba trục cấu hình cần tách biệt

Một nhầm lẫn phổ biến là coi “lấy mẫu 20 ms” đồng nghĩa recording chỉ chạy 20 ms. Thực tế, đây là hai thiết lập độc lập:

| Trục | Câu hỏi | Ví dụ cấu hình | Tác động chính |
|---|---|---|---|
| Sampling period | Mỗi loại event định kỳ được phát/lấy mẫu với khoảng nào? | `jdk.ExecutionSample#period=20ms` | Độ chi tiết và số sample |
| Recording duration | Recording chạy trong bao lâu? | `duration=2m` | Khoảng thời gian được quan sát |
| Retention | Giữ dữ liệu disk trong bao lâu/tối đa bao nhiêu? | `maxage=1h,maxsize=512M` | Dung lượng và lịch sử còn lại |

Ví dụ, recording có thể chạy trong **10 phút**, lấy mẫu execution mỗi **20 ms**, đồng thời chỉ giữ tối đa **1 giờ** hoặc **512 MB** dữ liệu trên disk. Những thông số này không thay thế nhau.

~~~mermaid
flowchart TD
    A["Chọn cấu hình event"] --> B["Sampling period / threshold / throttle"]
    B --> C["Bắt đầu recording"]
    C --> D["Thu thập event trong duration"]
    D --> E["Giữ dữ liệu theo maxage / maxsize"]
    E --> F["Dump file .jfr"]
    F --> G["Phân tích bằng jfr / JDK Mission Control"]
~~~

JFR ghi nhận event theo thời điểm và cấu hình đã bật. Sampling period không bảo đảm cứ đúng mỗi N mili giây sẽ có một mẫu bất kể scheduler, tải CPU hay trạng thái thread. Hãy coi nó là **mức tần suất mục tiêu của event**, không phải đồng hồ real-time để đo deadline.

## 2. Chọn cấu hình JFR phù hợp

JDK cung cấp hai cấu hình có sẵn trong `$JAVA_HOME/lib/jfr` (Windows thường dùng `%JAVA_HOME%\\lib\\jfr`):

| Cấu hình | Mục đích | Cách dùng |
|---|---|---|
| `default.jfc` | Ghi liên tục với tập event thiết yếu và overhead thấp | Production continuous recording |
| `profile.jfc` | Thu thập nhiều thông tin hơn để điều tra chuyên sâu | Recording ngắn, có mục tiêu |
| Custom `.jfc` | Điều chỉnh event, period, threshold, throttle theo câu hỏi chẩn đoán | Staging hoặc production có kiểm soát |

`default.jfc` là điểm bắt đầu phù hợp cho recording dài hạn. `profile.jfc` thu thập nhiều dữ liệu hơn và có thể tăng overhead, nên dùng trong khoảng thời gian ngắn khi cần phân tích sâu.

**Không sửa trực tiếp file `default.jfc` hoặc `profile.jfc` đi kèm JDK.** Hãy tạo một cấu hình mới từ file gốc để dễ review, version control và so sánh giữa các lần chạy.

Ví dụ bắt đầu recording ngắn với profile:

~~~bash
java -XX:StartFlightRecording:filename=profile.jfr,settings=profile,duration=2m -jar app.jar
~~~

Ví dụ ghi liên tục với cấu hình mặc định:

~~~bash
java -XX:StartFlightRecording:filename=continuous.jfr,settings=default,dumponexit=true -jar app.jar
~~~

Recording thứ hai không có `duration`, vì vậy tiếp tục cho tới khi JVM dừng hoặc recording được dừng bằng công cụ chẩn đoán. Với recording liên tục trên production, cần giới hạn retention bằng `maxage` và `maxsize` khi ghi ra disk để tránh dữ liệu tăng không kiểm soát.

## 3. Hiểu đúng sampling period

Một **periodic event** được phát theo một khoảng định kỳ. Setting `period` chỉ có ý nghĩa đối với event hỗ trợ cơ chế này. Ví dụ trong Java 25:

- `jdk.ExecutionSample`: lấy mẫu stack của thread đang thực thi Java code.
- `jdk.CPULoad`: ghi thông tin tải CPU theo chu kỳ.
- `jdk.JavaThreadStatistics`: thống kê thread theo chu kỳ.

Một số event khác không phải periodic sampling event; đặt `period` cho chúng không thay thế được `threshold` hoặc `throttle`.

### 3.1. Chu kỳ nhỏ và chu kỳ lớn

Giả sử cùng một workload chạy trong 60 giây:

| Chu kỳ | Số sample lý thuyết nếu phát đúng nhịp | Đặc điểm |
|---|---:|---|
| 5 ms | 12.000 | Chi tiết hơn, số event và chi phí có thể tăng |
| 10 ms | 6.000 | Mật độ mẫu cao |
| 20 ms | 3.000 | Cân bằng thường dùng để bắt đầu thử nghiệm |
| 50 ms | 1.200 | Ít dữ liệu hơn, có thể bỏ lỡ hotspot ngắn |
| 100 ms | 600 | Phù hợp quan sát xu hướng thô, ít phù hợp phân tích hotspot ngắn |

Các con số là **ước lượng toán học** từ thời lượng chia chu kỳ, không phải cam kết JFR sẽ ghi đúng số lượng đó. Sampling có thể chịu ảnh hưởng bởi lịch chạy thread, khả năng lấy stack và cách triển khai sampler.

Quy tắc thực hành:

- Giảm period khi cần tăng độ phân giải và đã xác định chi phí có thể chấp nhận.
- Tăng period khi chỉ cần xu hướng hoặc recording phải chạy dài.
- Không giảm period xuống mức rất nhỏ chỉ để “có nhiều dữ liệu hơn”; số sample lớn không tự động làm kết luận chính xác hơn.
- Luôn đối chiếu kết quả với CPU, throughput, latency và tải nền của ứng dụng.

### 3.2. Sampling không phải phép đo thời gian thực của từng method

`jdk.ExecutionSample` chụp stack của thread đang thực thi Java code tại các thời điểm lấy mẫu. Những thread đang chờ I/O, chờ lock hoặc thực thi native code có thể không được phản ánh như một Java execution sample tương ứng.

Nếu một method xuất hiện trong 40% sample, có thể diễn giải rằng method/stack đó chiếm tỷ lệ đáng kể trong tập mẫu quan sát được. Không được diễn giải rằng **chính xác 40% wall-clock time của mọi request** được tiêu tốn trong method đó.

Để đo thời lượng của một thao tác cụ thể, hãy dùng event duration phù hợp, custom JFR event có `begin()/end()`, tracing hoặc metric Timer. Sampling là công cụ tìm vùng nóng, không thay thế phép đo latency nghiệp vụ.

## 4. Điều chỉnh period cho event bằng JVM command line

JDK 25 cho phép ghi đè event setting ngay trên tùy chọn `-XX:StartFlightRecording`. Cú pháp chung:

~~~text
-XX:StartFlightRecording:<parameter>=<value>,<event-name>#<setting>=<value>
~~~

Ví dụ lấy mẫu execution mỗi 20 ms trong 2 phút:

~~~bash
java \
  -XX:StartFlightRecording:filename=execution-20ms.jfr,settings=profile,duration=2m,jdk.ExecutionSample#period=20ms \
  -jar app.jar
~~~

Để thử chu kỳ thưa hơn:

~~~bash
java \
  -XX:StartFlightRecording:filename=execution-50ms.jfr,settings=profile,duration=2m,jdk.ExecutionSample#period=50ms \
  -jar app.jar
~~~

Hai lần chạy cần dùng cùng JDK, artifact, heap options và workload. Chỉ thay period để so sánh số sample, kích thước file và overhead.

### 4.1. Đặt period cho một periodic event khác

Ví dụ muốn ghi CPU load mỗi giây:

~~~bash
java \
  -XX:StartFlightRecording:filename=cpu-load.jfr,settings=default,duration=5m,jdk.CPULoad#period=1s \
  -jar app.jar
~~~

Tên event và setting phải tồn tại trong JDK đang dùng. Dùng `jfr metadata` hoặc cấu hình JFC của đúng JDK để kiểm tra trước khi thêm event mới.

### 4.2. Tạo JFC tùy chỉnh bằng công cụ `jfr configure`

Cách dễ review là tạo một file settings riêng:

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/profile.jfc" \
  --output profile-execution-20ms.jfc \
  jdk.ExecutionSample#period=20ms
~~~

Trên PowerShell, dùng đường dẫn tương ứng:

~~~powershell
jfr configure --input "$env:JAVA_HOME\lib\jfr\profile.jfc" --output profile-execution-20ms.jfc jdk.ExecutionSample#period=20ms
~~~

Chạy recording với file mới:

~~~bash
java \
  -XX:StartFlightRecording:filename=profile-custom.jfr,settings=profile-execution-20ms.jfc,duration=2m \
  -jar app.jar
~~~

`jfr configure` có thể nhận nhiều event settings; các giá trị trên command line có thể ghi đè cấu hình trong JFC. Giữ file custom trong source control để nhóm vận hành có thể review và tái tạo kết quả.

## 5. Phân biệt period, threshold, throttle và stackTrace

Bốn setting thường được dùng để điều khiển lượng dữ liệu nhưng có ý nghĩa khác nhau:

| Setting | Ý nghĩa | Dùng cho | Ví dụ |
|---|---|---|---|
| `period` | Khoảng giữa các lần phát event định kỳ | Periodic events | `jdk.ExecutionSample#period=20ms` |
| `threshold` | Chỉ ghi duration event nếu thời lượng đạt ngưỡng | Event có duration | `jdk.SocketRead#threshold=10ms` |
| `throttle` | Giới hạn số event tối đa trong một đơn vị thời gian | Event có thể phát dày | `jdk.FileWrite#throttle=100/s` |
| `stackTrace` | Bật/tắt stack trace cho event | Event hỗ trợ stack trace | `jdk.FileWrite#stackTrace=false` |

### 5.1. Threshold không phải sampling period

Ví dụ:

~~~bash
java -XX:StartFlightRecording:filename=io.jfr,settings=default,jdk.SocketRead#threshold=10ms -jar app.jar
~~~

Cấu hình này chỉ ghi các socket read có duration từ ngưỡng trở lên theo semantics của event. Nó không lấy mẫu mỗi 10 ms.

### 5.2. Throttle không phải period

Ví dụ:

~~~bash
java -XX:StartFlightRecording:filename=io.jfr,settings=default,jdk.FileWrite#throttle=100/s -jar app.jar
~~~

`100/s` là giới hạn tốc độ event tối đa, không phải yêu cầu phát một event đúng mỗi 10 ms. Nếu workload chỉ có vài lần ghi file, JFR không tạo thêm event giả để đủ 100 event/giây.

### 5.3. Stack trace làm tăng chi phí và dung lượng

Stack trace rất hữu ích để xác định call path nhưng làm event lớn hơn và tốn công thu thập hơn. Với event không cần truy nguyên caller, có thể tắt stack trace bằng cấu hình tương ứng:

~~~bash
java -XX:StartFlightRecording:filename=light.jfr,settings=default,jdk.FileWrite#stackTrace=false -jar app.jar
~~~

Không tắt stack trace của mọi event chỉ để giảm dung lượng. Hãy xác định event nào cần stack trace để trả lời câu hỏi chẩn đoán, rồi đo lại overhead.

## 6. Điều chỉnh thời lượng recording

Thời lượng recording được điều khiển bằng `duration`. Ví dụ:

~~~bash
java -XX:StartFlightRecording:filename=checkout.jfr,settings=profile,duration=90s -jar app.jar
~~~

Các đơn vị thường dùng:

- `30s`: 30 giây.
- `5m`: 5 phút.
- `1h`: 1 giờ.
- `0`: không giới hạn thời gian.

Một recording có duration hữu hạn sẽ tự dừng khi hết thời gian và ghi file theo cấu hình. `dumponexit=true` có ý nghĩa khi muốn dump recording đang chạy lúc JVM shutdown; với recording đã có duration và filename rõ ràng, vẫn nên kiểm tra file đầu ra sau khi hoàn tất.

### 6.1. Bắt đầu recording khi ứng dụng đang chạy bằng jcmd

Không cần restart ứng dụng để tạo một recording ngắn. Dùng `jcmd`:

~~~bash
jcmd -l
jcmd 12345 JFR.start name=CheckoutProfile settings=profile duration=2m filename=/tmp/checkout-profile.jfr
~~~

Thay `12345` bằng PID thật. `jcmd` phải chạy trên cùng máy với JVM và cùng effective user/group đã khởi chạy process. Với process trong container, cần thực thi `jcmd` ở đúng PID namespace/container hoặc dùng cơ chế chẩn đoán được nền tảng hỗ trợ.

Kiểm tra recording:

~~~bash
jcmd 12345 JFR.check verbose=true
~~~

Nếu cần dừng trước thời hạn:

~~~bash
jcmd 12345 JFR.stop name=CheckoutProfile filename=/tmp/checkout-profile.jfr
~~~

Nếu chỉ cần dump dữ liệu tại thời điểm hiện tại nhưng muốn recording tiếp tục:

~~~bash
jcmd 12345 JFR.dump name=CheckoutProfile filename=/tmp/checkout-snapshot.jfr
~~~

`JFR.dump` không dừng recording; dữ liệu tiếp tục được thu thập sau khi dump.

### 6.2. Chọn duration theo câu hỏi

| Mục tiêu | Khoảng ghi gợi ý | Vì sao |
|---|---|---|
| Kiểm tra một request hoặc thao tác tái hiện được | 30–120 giây | Đủ bao quanh workload có kiểm soát |
| Profiling ngắn trong staging | 2–5 phút | Thu đủ chu kỳ request và GC |
| Điều tra spike không thường xuyên | Recording liên tục có retention giới hạn | Giữ được dữ liệu trước sự cố |
| Theo dõi xu hướng JVM | Recording liên tục với `default.jfc` | Thu dữ liệu thiết yếu với overhead thấp |
| Method profiling chi tiết | Thời lượng ngắn với `profile.jfc` | Thu nhiều event và stack hơn |

Đây là khoảng thời gian khởi đầu, không phải quy tắc cứng. Nếu sự cố xảy ra mỗi 15 phút, recording 30 giây có thể bỏ lỡ nó. Nếu tải có chu kỳ theo giờ, cần ghi đủ một hoặc nhiều chu kỳ để so sánh.

## 7. Recording liên tục với maxage và maxsize

Một recording liên tục hữu ích khi chưa biết lúc nào sự cố xảy ra. JFR có thể giữ một cửa sổ dữ liệu gần đây, sau đó dump khi cần.

~~~bash
jcmd 12345 JFR.start \
  name=Continuous \
  settings=default \
  maxage=6h \
  maxsize=1G
~~~

Ở đây:

- `settings=default`: cấu hình phù hợp cho continuous recording.
- `maxage=6h`: giữ dữ liệu disk tối đa 6 giờ.
- `maxsize=1G`: giới hạn dữ liệu disk tối đa 1 GB.
- Không đặt `duration`: recording tiếp tục chạy cho tới khi được dừng hoặc JVM kết thúc.

Khi có sự cố, dump khoảng 15 phút gần nhất:

~~~bash
jcmd 12345 JFR.dump \
  name=Continuous \
  begin=-15m \
  filename=/var/log/java/incident-last-15m.jfr
~~~

Recording tiếp tục hoạt động sau khi dump. Khi không còn cần continuous recording:

~~~bash
jcmd 12345 JFR.stop name=Continuous
~~~

### 7.1. Vì sao cần cả maxage và maxsize?

- `maxage` giới hạn độ dài lịch sử.
- `maxsize` giới hạn dung lượng trên disk.
- Nếu một giới hạn đạt trước, JFR loại bỏ dữ liệu cũ để nhường chỗ cho dữ liệu mới.
- Nếu không đặt giới hạn phù hợp, disk usage có thể tăng theo thời gian.

Không đặt retention theo cảm tính. Đo tốc độ sinh file của ứng dụng dưới tải đại diện, tính dung lượng dự kiến và để lại khoảng trống an toàn cho log, heap dump và file tạm.

### 7.2. Phân biệt disk recording và buffer trong JVM

JFR dùng buffer nội bộ để thu event. Với disk recording, dữ liệu được ghi ra repository/file theo cơ chế chunk. Recording liên tục có thể giữ dữ liệu mới nhất và loại bỏ phần cũ theo giới hạn retention.

Không nên tăng buffer hoặc stack depth chỉ để cố “không mất event” mà chưa xác định nguyên nhân. Trước hết kiểm tra:
- Event nào tạo lượng dữ liệu lớn.
- Stack trace có thực sự cần không.
- Period/threshold/throttle có phù hợp không.
- Disk throughput và dung lượng repository.
- Recording có bị giới hạn bởi maxage/maxsize hay không.

## 8. Đo và kiểm soát chi phí quan sát

JFR được thiết kế cho chẩn đoán production với overhead thấp, nhưng **không có một con số overhead đúng cho mọi ứng dụng**. Chi phí phụ thuộc vào loại event, tần suất, stack trace, số thread, tốc độ event và storage.

Các nguồn overhead chính:

| Nguồn | Tác động | Cách kiểm soát |
|---|---|---|
| Sampling period quá nhỏ | Tăng số sample và công việc lấy stack | Tăng period nếu cần giảm chi phí |
| Nhiều event enabled | Tăng event generation và data volume | Chỉ bật event liên quan câu hỏi |
| Stack trace | Tốn công thu thập, tăng kích thước event | Tắt ở event không cần stack |
| Threshold quá thấp | Ghi nhiều duration event ngắn | Đặt threshold theo vấn đề cần phát hiện |
| Throttle quá cao hoặc off | Event có thể phát rất dày | Đặt rate limit phù hợp |
| Recording duration dài | Tăng lượng dữ liệu cần lưu | Giới hạn duration/maxage/maxsize |
| Profile template | Nhiều thông tin hơn, overhead có thể cao hơn | Dùng thời gian ngắn |
| Path to GC roots | Có thể gây pause để thu thập thông tin | Chỉ bật khi điều tra memory leak |

### 8.1. Default và profile khác nhau về chi phí

`default.jfc` được Oracle khuyến nghị cho continuous recording, với tập event ít tác động và phù hợp giám sát lâu dài. `profile.jfc` thu nhiều dữ liệu hơn và có thể có overhead lớn hơn; hãy dùng nó trong thời gian ngắn khi điều tra.

Không nên lấy một benchmark trên máy dev rồi khẳng định JFR luôn có overhead dưới một tỷ lệ cố định. Hãy đo trong môi trường gần production, với cùng workload, JDK, CPU, heap và storage.

### 8.2. Quy trình đo overhead

Thực hiện ba lần đo:

1. **Baseline:** chạy ứng dụng không có recording bổ sung hoặc với cấu hình giám sát hiện tại.
2. **Low-overhead:** bật JFR với `default.jfc`.
3. **Focused profile:** bật `profile.jfc` hoặc custom JFC với các event cần thiết trong khoảng ngắn.

Ghi nhận:

| Chỉ số | Baseline | Default | Focused profile |
|---|---:|---:|---:|
| Startup time | Đo | Đo | Đo |
| CPU utilization | Đo | Đo | Đo |
| Request throughput | Đo | Đo | Đo |
| p50/p95/p99 latency | Đo | Đo | Đo |
| File size / phút | — | Đo | Đo |
| GC pause / allocation rate | Đo | Đo | Đo |

Tính phần trăm thay đổi:

\[
\text{Overhead}_{CPU} =
\frac{CPU_{\text{recording}} - CPU_{\text{baseline}}}
     {CPU_{\text{baseline}}} \times 100\%
\]

Với latency, throughput và dung lượng file cũng cần so sánh cùng cửa sổ workload. Nếu baseline gần 0, phần trăm có thể gây hiểu lầm; khi đó báo cáo cả giá trị tuyệt đối.

**Không thay nhiều setting trong cùng một lần thử.** Nếu đồng thời đổi period, stackTrace, threshold và duration, bạn sẽ khó biết yếu tố nào gây ra thay đổi overhead.

## 9. Java 25: những cải tiến JFR đáng chú ý

Java 25 có ba cải tiến JFR cần nhận diện:

| JEP | Tính năng | Ý nghĩa khi vận hành |
|---|---|---|
| **JEP 518** | JFR Cooperative Sampling | Cải thiện độ ổn định khi JFR lấy mẫu stack bất đồng bộ; giảm safepoint bias bằng cách đi stack tại safepoint |
| **JEP 520** | JFR Method Timing & Tracing | Bổ sung khả năng timing/tracing method qua bytecode instrumentation; cần chọn lọc vì có thể tăng dữ liệu và chi phí |
| **JEP 509** | JFR CPU-Time Profiling (**Experimental**) | Thêm CPU-time sampling chính xác hơn trên Linux; không phải event mặc định dùng cho mọi nền tảng |

### 9.1. JFR Cooperative Sampling — JEP 518

JEP 518 cải thiện độ ổn định của việc lấy mẫu stack bất đồng bộ. JFR đi stack ở safepoint nhưng giảm safepoint bias, nhằm tránh việc mẫu chỉ phản ánh những vị trí mà thread thường xuyên dừng tại safepoint.

Đối với người vận hành, điều này giúp kết quả sampling ổn định hơn khi phân tích hotspot. Tuy nhiên, sample vẫn là sample; không biến nó thành phép đo chính xác thời gian từng method.

### 9.2. CPU-Time Profiling — JEP 509

`jdk.ExecutionSample` phản ánh thread đang thực thi Java code tại thời điểm lấy mẫu. Nó không trực tiếp cho biết CPU time thực tế trong native code hoặc mọi trạng thái chờ.

JEP 509 thêm event `jdk.CPUTimeSample` cho CPU-time profiling trên Linux. Tính năng này được đánh dấu **experimental** trong Java 25 và không nên dùng như baseline bắt buộc cho mọi hệ điều hành/JDK vendor.

Có thể thử trong môi trường Linux tương thích:

~~~bash
java \
  -XX:StartFlightRecording:filename=cpu-time.jfr,settings=profile,duration=60s,jdk.CPUTimeSample#enabled=true \
  -jar app.jar
~~~

Trước khi sử dụng, kiểm tra event có sẵn trong đúng bản JDK:

~~~bash
jfr metadata
~~~

Nếu event không được hỗ trợ hoặc không có trên nền tảng hiện tại, không suy luận rằng JFR hỏng. Dùng `jdk.ExecutionSample` và các sự kiện CPU/thread phù hợp với nền tảng.

### 9.3. Method Timing & Tracing — JEP 520

JEP 520 bổ sung khả năng ghi nhận timing/tracing method qua bytecode instrumentation. Đây là một hướng thu thập khác với việc chỉ lấy sample stack.

Không bật instrumentation cho hàng nghìn method trên production nếu chưa đo overhead và dung lượng. Chọn method hoặc package cần điều tra, giới hạn recording và so sánh với baseline. Khi mục tiêu là tìm vùng CPU nóng, sampling thường là bước đầu ít xâm lấn hơn; khi cần thời lượng method cụ thể, cân nhắc event timing có chọn lọc.

## 10. Ví dụ điều chỉnh recording bằng JFR API

Ngoài command line và `jcmd`, Java 25 có thể tạo recording bằng `jdk.jfr.Recording`. Ví dụ:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public final class RecordingPeriodExample {

    public static void main(String[] args) throws Exception {
        Path output = Path.of("checkout.jfr");

        try (Recording recording = new Recording()) {
            recording.setName("CheckoutFocused");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(10));
            recording.setMaxSize(128L * 1024 * 1024);

            recording.enable("jdk.ExecutionSample")
                    .withPeriod(Duration.ofMillis(20));

            recording.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));

            recording.start();

            runRepresentativeWorkload();

            recording.stop();
            recording.dump(output);
        }
    }

    private static void runRepresentativeWorkload() {
        // Chạy workload cần quan sát trong ứng dụng thử nghiệm.
    }
}
~~~

Ví dụ này tạo recording với hai periodic event và giới hạn dữ liệu lưu trên disk. Trong ứng dụng thật, workload phải được chạy giữa `start()` và `stop()`; không dùng một method rỗng rồi kết luận đã đo được hiệu năng.

Các setting được cấu hình qua `Recording.enable(...)` và `EventSettings.withPeriod(...)`. API này phù hợp khi recording cần được điều khiển bởi chính ứng dụng hoặc test harness. Với vận hành production, `jcmd` thường tiện hơn vì không cần thêm logic quản lý recording vào code nghiệp vụ.

## 11. Phân tích file recording

Sau khi có file `.jfr`, dùng JDK tool để kiểm tra tổng quan:

~~~bash
jfr summary checkout.jfr
~~~

Xem các event execution sample:

~~~bash
jfr print --events jdk.ExecutionSample checkout.jfr
~~~

Xem một số event cụ thể:

~~~bash
jfr print --events jdk.CPULoad,jdk.GarbageCollection checkout.jfr
~~~

Xem view có sẵn:

~~~bash
jfr --help view
jfr view all-views checkout.jfr
jfr view all-events checkout.jfr
~~~

Sau khi xem danh sách, chọn một view được JDK hiện tại hỗ trợ bằng `jfr view <view-name> checkout.jfr`; cũng có thể dùng tên event làm view. Tên view và dữ liệu hiển thị phụ thuộc phiên bản JDK và nội dung recording. Có thể mở file `.jfr` bằng **JDK Mission Control (JMC)** để phân tích stack, method profiling, GC, lock, I/O và timeline. JMC là công cụ riêng, không nhất thiết được cài kèm JDK.

### 11.1. Xác minh setting thực tế

Đừng chỉ dựa vào lệnh bạn đã nhập. Kiểm tra cấu hình recording đang chạy:

~~~bash
jcmd 12345 JFR.check verbose=true
~~~

Thông tin verbose giúp xem các event settings đang áp dụng. Đối chiếu:
- Event có enabled không?
- Period có đúng giá trị không?
- Threshold/throttle có đang lọc event không?
- Recording có đang chạy hay đã stopped?
- Duration còn lại và file output có đúng không?

Khi dùng JFC, lưu file cấu hình cùng recording để người khác tái lập kết quả. Nếu có ghi đè từ command line, ghi lại cả lệnh đầy đủ trong báo cáo.

## 12. Chọn cấu hình theo tình huống

| Tình huống | Cấu hình khởi đầu | Mục tiêu |
|---|---|---|
| Theo dõi JVM production liên tục | `default.jfc`, maxage/maxsize có giới hạn | Giữ dữ liệu sự cố gần đây với overhead thấp |
| CPU hotspot trong một workload ngắn | `profile.jfc`, ExecutionSample period có kiểm soát, duration hữu hạn | Tìm stack/method nóng |
| CPU load theo xu hướng | `jdk.CPULoad#period=1s` | Quan sát biến động CPU |
| Socket/file I/O chậm | Event tương ứng với threshold/throttle | Tìm thao tác I/O vượt ngưỡng |
| Memory leak nghi ngờ | Profile có chọn lọc; chỉ bật path-to-GC-roots khi cần | Xác định object còn được giữ và GC roots |
| CPU time trong native code trên Linux | Thử nghiệm JEP 509 nếu JDK hỗ trợ | Phân tích CPU time chính xác hơn |
| Timing một method cụ thể | JEP 520 instrumentation có chọn lọc | Đo method duration với phạm vi hẹp |

Không dùng cùng một profile cho tất cả tình huống. Hãy bắt đầu bằng câu hỏi chẩn đoán, chọn event trả lời câu hỏi đó và chỉ thu dữ liệu bổ sung khi kết quả đầu tiên chưa đủ.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| File JFR quá lớn | Profile nhiều event, duration dài hoặc period quá ngắn | Giảm duration, tăng period, giới hạn maxsize/maxage |
| Không thấy ExecutionSample | Event bị disable hoặc workload ít chạy Java code | Kiểm tra event settings và tạo workload phù hợp |
| Không thấy native CPU hotspot | ExecutionSample chỉ phản ánh Java execution | Cân nhắc JEP 509 experimental trên Linux hoặc công cụ phù hợp |
| Recording không dừng | Duration = 0 hoặc recording liên tục | Dùng duration hữu hạn hoặc JFR.stop |
| File không được tạo | Sai filename path hoặc quyền ghi | Kiểm tra thư mục, user và JFR.stop filename |
| Dump không làm recording kết thúc | JFR.dump chỉ ghi snapshot | Dùng JFR.stop nếu cần dừng |
| Recording mất dữ liệu cũ | maxage/maxsize đã đạt giới hạn | Tăng retention có kiểm soát hoặc dump thường xuyên hơn |
| Overhead tăng mạnh | Quá nhiều event/stack trace hoặc profile kéo dài | Chuyển default, giảm event, tăng period, đặt threshold/throttle |
| Không thấy event ngắn | Threshold đặt quá cao | Giảm threshold hoặc bỏ threshold nếu cần |
| Event I/O xuất hiện quá nhiều | Threshold thấp và throttle cao/off | Đặt threshold/throttle phù hợp với câu hỏi |
| Không đọc được file JFR trong JMC | JMC quá cũ hoặc recording dùng event metadata mới | Cập nhật JMC tương thích với JDK/recording |
| Kết quả sample không ổn định | Workload khác nhau, thời lượng ngắn hoặc CPU throttling | Lặp lại cùng workload, ghi đủ thời gian và theo dõi môi trường |

### 13.1. Không dùng path-to-gc-roots như mặc định

`path-to-gc-roots=true` có thể hữu ích khi nghi ngờ memory leak, nhưng việc thu thập đường dẫn tới GC roots tốn thời gian và có thể làm ứng dụng pause trong một khoảng ngắn.

Chỉ bật khi có câu hỏi cụ thể về object còn được giữ. Không bật cho continuous recording thông thường.

### 13.2. Stack depth lớn không miễn phí

JFR có giới hạn stack depth mặc định. Tăng sâu hơn có thể làm suy giảm hiệu năng. Nếu stack bị cắt, trước tiên xem liệu call chain cần thiết đã được ghi lại chưa; chỉ thay đổi stack depth khi có bằng chứng và đã đo tác động.

## 14. Quy trình kiểm chứng overhead

Một bài thử có thể tái lập cần giữ cố định:

- JDK vendor và version.
- Application artifact và dependency.
- Heap/GC/JVM options.
- Số CPU, memory limit và container quota.
- Dataset, request rate và thời gian warm-up.
- Thời lượng recording và workload.

Thực hiện:

1. Chạy baseline không bật profiling bổ sung.
2. Chạy cùng workload với `default.jfc`.
3. Chạy lại với `profile.jfc`.
4. Thay period của `jdk.ExecutionSample` từ 20 ms sang 50 ms (hoặc ngược lại).
5. So sánh CPU, latency, throughput, file size và số sample.
6. Lặp lại nhiều lần, báo median và độ phân tán.
7. Chọn cấu hình đáp ứng câu hỏi chẩn đoán với chi phí chấp nhận được.

**Không kết luận overhead bằng một lần chạy.** Nếu biến động môi trường lớn hơn khác biệt do JFR, cần kiểm soát môi trường tốt hơn trước khi chọn cấu hình production.

## 15. Ma trận thực hành nghiệm thu

| Mã | Thao tác | Kết quả mong đợi |
|---|---|---|
| J1 | Start recording với `settings=default` | Recording bắt đầu với tập event low-overhead |
| J2 | Start recording với `settings=profile` và duration hữu hạn | Recording tự dừng sau khoảng thời gian đã đặt |
| J3 | Đặt `jdk.ExecutionSample#period=20ms` | Event setting phản ánh period đã cấu hình |
| J4 | Đổi period sang 50 ms với cùng workload | Số sample và file size thay đổi theo xu hướng phù hợp |
| J5 | Đặt threshold cho SocketRead | Các event ngắn hơn threshold không được ghi theo setting |
| J6 | Đặt throttle cho FileWrite | Rate event bị giới hạn |
| J7 | Tắt stack trace cho event được chọn | Event không còn stack trace theo setting |
| J8 | Dùng `JFR.check verbose=true` | Xác minh recording và settings đang chạy |
| J9 | Dùng `JFR.dump` khi recording liên tục | File snapshot được tạo, recording tiếp tục |
| J10 | Dùng `JFR.stop` | Recording dừng và file được ghi nếu chỉ định filename |
| J11 | Đặt `maxage` và `maxsize` | Dữ liệu cũ bị loại bỏ theo retention limit |
| J12 | So sánh default với profile | Xác định khác biệt về event volume và overhead |
| J13 | Thử JEP 509 trên Linux JDK hỗ trợ | Kiểm tra event CPU-time experimental nếu khả dụng |
| J14 | Mở file trong JMC hoặc dùng `jfr view` | Phân tích được stack, event và timeline |
| J15 | Lặp lại benchmark nhiều lần | Có số liệu đủ tin cậy để chọn cấu hình |

## 16. Bài tập tổng hợp

Bạn vận hành một dịch vụ Java có đỉnh CPU không ổn định vào giờ cao điểm. Log ứng dụng cho thấy request chậm, nhưng chưa biết nguyên nhân nằm ở code Java, GC hay I/O.

Thực hiện:

1. Bật continuous recording với `default.jfc`, `maxage=4h`, `maxsize=512M`.
2. Khi alert CPU tăng, dump 15 phút gần nhất.
3. Phân tích CPU load, execution samples, GC pauses, thread states và I/O events.
4. Tạo recording ngắn dùng `profile.jfc` trong staging với workload tái hiện.
5. Thử period 20 ms và 50 ms; so sánh số sample, file size và CPU overhead.
6. Chỉ bật event bổ sung khi đã có giả thuyết, ví dụ socket read chậm hoặc allocation tăng.
7. Nếu nghi native CPU time trên Linux, đánh giá JEP 509 experimental trong môi trường kiểm thử.
8. Viết báo cáo lựa chọn cấu hình cuối cùng, lý do, giới hạn dữ liệu và hướng dẫn rollback.

**Sản phẩm nghiệm thu:** file JFC tùy chỉnh, lệnh start/dump/stop, một file recording đã loại bỏ dữ liệu nhạy cảm nếu có, bảng benchmark và runbook thu JFR khi sự cố xảy ra.

## 17. Checklist vận hành

- Chọn `default.jfc` cho continuous recording và `profile.jfc` cho profiling ngắn.
- Điều chỉnh period chỉ cho event hỗ trợ periodic setting.
- Dùng threshold cho duration event và throttle để giới hạn event rate.
- Đặt duration hữu hạn cho recording điều tra.
- Giới hạn maxage/maxsize cho recording dài hạn.
- Ghi lại JDK, JVM flags, JFC file và workload.
- Dùng `JFR.check verbose=true` để xác minh settings thật.
- Phân biệt JFR.dump (snapshot) với JFR.stop (kết thúc recording).
- Đo overhead bằng baseline và workload có thể tái lập.
- Không mặc định CPU-time profiling experimental có trên mọi OS.
- Bảo vệ file JFR: recording có thể chứa tên lớp, method, đường dẫn, thông tin hệ thống và dữ liệu ứng dụng.
- Xóa hoặc lưu trữ recording theo retention policy của tổ chức.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 25 — Configure Events and Flight Recorder](https://docs.oracle.com/en/java/javase/25/jfapi/configuration.html): event settings, period, threshold, stack trace và cấu hình JFR.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:StartFlightRecording`, duration, settings, maxage và maxsize.
- [Oracle Java SE 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Java SE 25 API — jdk.jfr](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event settings và định dạng `period`, `threshold`, `throttle`.
- [Java SE 25 API — Recording](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình và vòng đời recording bằng Java API.
- [Java SE 25 API — EventSettings](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `withPeriod`, `withThreshold`, `withStackTrace`.
- [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): continuous recording, profiling và JDK Mission Control.
- [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): cải thiện độ ổn định khi lấy mẫu stack bất đồng bộ trong Java 25.
- [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): CPU-time sampling thử nghiệm trên Linux.
- [JEP 520 — JFR Method Timing & Tracing](https://openjdk.org/jeps/520): method timing và tracing bằng bytecode instrumentation.
- [Oracle JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): tổng quan các cải tiến JFR trong Java 25.
