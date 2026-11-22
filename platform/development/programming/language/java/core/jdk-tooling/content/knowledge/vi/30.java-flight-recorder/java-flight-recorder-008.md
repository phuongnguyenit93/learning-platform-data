# Continuous recording với Java Flight Recorder

**Continuous recording** là chế độ ghi sự kiện liên tục của Java Flight Recorder (JFR), được thiết kế để giữ lại một cửa sổ dữ liệu gần đây của JVM. Khi một sự cố hiếm gặp xảy ra, người vận hành có thể xuất dữ liệu của khoảng thời gian ngay trước sự cố để phân tích, dù lúc đó không có ai bắt đầu profiling thủ công.

JFR được tích hợp trong HotSpot JDK. Nó ghi các sự kiện có timestamp về JVM và ứng dụng, chẳng hạn CPU samples, garbage collection, thread scheduling, lock contention, class loading và I/O. Với continuous recording, cấu hình `default.jfc` thường là lựa chọn khởi đầu phù hợp vì được thiết kế để ghi lâu dài với overhead thấp.

Continuous recording hoạt động như một lịch sử có giới hạn: dữ liệu cũ dần bị loại bỏ khi vượt quá thời gian hoặc dung lượng lưu giữ đã cấu hình. Khi cần điều tra, dùng `jcmd <pid> JFR.dump` để xuất một file `.jfr` của khoảng thời gian cần xem. Lệnh dump không dừng recording; JVM tiếp tục ghi sau khi tạo file.

## 1. Continuous recording giải quyết vấn đề gì?

Nhiều sự cố production không dễ tái hiện:

- Request thỉnh thoảng tăng latency trong vài giây.
- CPU tăng đột ngột rồi trở lại bình thường.
- Thread chờ lock hoặc I/O trong một khoảng thời gian ngắn.
- Garbage collection có pause bất thường.
- Một service có allocation rate tăng theo thời điểm.
- Ứng dụng bị chậm trước khi health check báo lỗi.
- Sự cố xảy ra ngoài giờ làm việc, không có người đang mở profiler.

Nếu chỉ bắt đầu profiling sau khi nhận cảnh báo, dữ liệu trước thời điểm sự cố có thể đã mất. Continuous recording giữ lại một cửa sổ sự kiện gần đây để có thể xem lại sau đó.

Ví dụ: cấu hình lưu sáu giờ gần nhất. Khi nhận cảnh báo lúc 14:00, người vận hành có thể xuất dữ liệu từ 13:30 trở đi và kiểm tra thread, GC, CPU, lock hoặc I/O quanh thời điểm bất thường.

Continuous recording phù hợp với điều tra sau sự cố và theo dõi các vấn đề khó tái hiện. Nó không thay thế metric, log ứng dụng, trace phân tán hoặc alerting; những nguồn đó giúp xác định thời điểm và request cần điều tra.

## 2. JFR ghi những loại dữ liệu nào?

JFR ghi dữ liệu dưới dạng event có timestamp. Tùy cấu hình, event có thể thuộc các nhóm:

| Nhóm event | Ví dụ dữ liệu | Câu hỏi điều tra |
|---|---|---|
| CPU và execution | Execution samples, CPU load | Thread hoặc method nào đang tiêu thụ CPU? |
| Thread và scheduling | Thread park, sleep, start/end | Thread đang chạy, chờ hay bị trì hoãn? |
| Synchronization | Monitor enter, lock contention | Thread nào chờ lock và chờ bao lâu? |
| Garbage collection | GC start/end, pause, heap summary | GC xảy ra khi nào và pause kéo dài bao lâu? |
| Memory và allocation | Allocation samples, object allocation khi được bật | Code nào tạo nhiều object? |
| Class loading | Class load/unload | Có class hoặc classloader tăng bất thường không? |
| I/O | File read/write, socket read/write | Độ trễ đến từ file hoặc network I/O? |
| JVM và environment | Runtime, process, CPU và OS data | JVM đang chạy trong môi trường nào? |
| Custom event | Event do ứng dụng tự định nghĩa | Một bước nghiệp vụ mất bao lâu? |

JFR có duration event, instant event, sample event và custom event. Template quyết định event nào được bật, chu kỳ lấy mẫu, threshold và việc có gắn stack trace hay không.

Một event không xuất hiện trong file có thể do event đó bị tắt, threshold chưa đạt, request period không phù hợp hoặc template không thu thập loại dữ liệu đó. Không suy luận rằng sự kiện chắc chắn không xảy ra chỉ vì không thấy event tương ứng.

## 3. Continuous recording khác profiling recording như thế nào?

| Đặc điểm | Continuous recording | Time-fixed/profiling recording |
|---|---|---|
| Thời gian chạy | Liên tục, thường không đặt thời lượng kết thúc | Chạy trong khoảng thời gian xác định |
| Mục tiêu | Giữ lịch sử gần đây để điều tra sự cố hiếm | Thu thập dữ liệu chi tiết cho một phiên profiling |
| Cấu hình thường dùng | `default.jfc` hoặc Continuous template | `profile.jfc` hoặc Profiling template |
| Dung lượng | Có giới hạn tuổi dữ liệu và/hoặc kích thước | Thường xuất một file cho phiên ghi |
| Overhead | Thấp với cấu hình continuous mặc định | Thường cao hơn do nhiều event chi tiết |
| Khi lấy dữ liệu | Dump một khoảng thời gian khi cần | File được tạo khi recording kết thúc |

Một continuous recording có thể chạy trong nhiều ngày, nhưng chỉ giữ lại cửa sổ dữ liệu nằm trong giới hạn retention. Nó không có nghĩa là giữ vô hạn mọi event kể từ khi JVM khởi động.

Một profiling recording có thể bật thêm allocation profiling, method profiling hoặc event có stack trace chi tiết. Hãy dùng nó trong khoảng ngắn khi đã biết khu vực cần điều tra.

## 4. Chọn default.jfc hay profile.jfc?

JDK cung cấp hai cấu hình JFR dựng sẵn trong thư mục:

```text
<JAVA_HOME>/lib/jfr/default.jfc
<JAVA_HOME>/lib/jfr/profile.jfc
```

**`default.jfc`**

- Được thiết kế cho recording liên tục.
- Thu thập các event runtime quan trọng với overhead thấp.
- Phù hợp làm baseline cho production.
- Không bật heap statistics và allocation profiling chi tiết như một profiling recording.

**`profile.jfc`**

- Thu thập nhiều event hơn.
- Hữu ích khi cần method profiling, allocation profiling và thông tin sâu hơn.
- Tạo nhiều dữ liệu hơn và có thể ảnh hưởng hiệu năng rõ hơn.
- Phù hợp cho phiên điều tra ngắn khi cần thêm chi tiết.

Không nên thay file `default.jfc` hoặc `profile.jfc` được cài cùng JDK. Nếu cần tùy chỉnh, tạo file `.jfc` riêng dựa trên một cấu hình có sẵn, rồi dùng file đó khi khởi động recording.

Đối với continuous recording dài hạn, bắt đầu bằng `default`. Khi cần dữ liệu allocation hoặc method chi tiết, tạo một profiling recording ngắn hoặc custom configuration có phạm vi rõ ràng.

## 5. Hiểu rolling window, repository và file dump

Có ba khái niệm cần phân biệt:

1. **Buffer trong JVM:** JFR ghi event vào các buffer trong bộ nhớ trước khi flush thành chunk.
2. **Disk repository:** Khi recording dùng disk, JVM lưu các chunk tạm trong repository. Các chunk được quản lý theo giới hạn tuổi và dung lượng.
3. **File dump `.jfr`:** File độc lập được tạo khi người vận hành dump recording để phân tích, chia sẻ hoặc lưu trữ.

Trong continuous recording, JFR giữ lại dữ liệu gần đây. Khi giới hạn buffer hoặc retention đạt tới, dữ liệu cũ nhất được loại bỏ để dành chỗ cho dữ liệu mới. Đây là hành vi mong muốn của rolling history.

Repository là nơi lưu chunk tạm trong khi recording chạy. Nó không nhất thiết là nơi chứa file cuối cùng mà nhóm điều tra mở bằng JDK Mission Control (JMC). Khi dump, chỉ định đường dẫn mới cho file `.jfr`.

Ví dụ:

```text
/var/tmp/jfr-repository/        # Repository chứa chunk tạm
/var/tmp/jfr-dumps/incident.jfr # File dump để phân tích
```

Repository và thư mục dump cần có đủ dung lượng, quyền ghi phù hợp và chính sách lưu trữ riêng.

## 6. Giới hạn dữ liệu bằng maxage và maxsize

Hai tham số quan trọng:

| Tham số | Ý nghĩa |
|---|---|
| `maxage` | Giới hạn thời gian dữ liệu được giữ lại, ví dụ `6h` |
| `maxsize` | Giới hạn dung lượng dữ liệu recording được giữ trên disk, ví dụ `1g` |

Cả hai tham số chỉ áp dụng khi `disk=true`.

Ví dụ:

```text
disk=true
maxage=6h
maxsize=1g
```

Trong ví dụ, recording giữ tối đa sáu giờ dữ liệu và tối đa một gigabyte. Nếu tốc độ tạo event cao khiến giới hạn kích thước bị chạm trước sáu giờ, cửa sổ dữ liệu thực tế sẽ ngắn hơn. Nếu dữ liệu cũ hơn sáu giờ trước, nó bị loại bỏ ngay cả khi chưa chạm giới hạn kích thước.

Nếu không đặt `maxage` hoặc `maxsize`, dữ liệu trên disk có thể tăng không giới hạn. Vì vậy, continuous recording cần có retention rõ ràng và phải tính đến tốc độ event thực tế.

Giá trị `0` có nghĩa không đặt giới hạn tương ứng. Không nên dùng `maxage=0` và `maxsize=0` cho recording production dài hạn nếu chưa có cơ chế quản lý dung lượng khác.

`maxsize` phải đủ lớn so với giới hạn kích thước chunk JFR (`maxchunksize`). Nếu đặt quá nhỏ, JVM có thể từ chối cấu hình.

## 7. Bật continuous recording khi JVM khởi động

Có thể bật recording ngay trong lệnh khởi chạy ứng dụng:

```sh
java -XX:StartFlightRecording=disk=true,maxage=6h,maxsize=1g,settings=default -XX:FlightRecorderOptions=repository=/var/tmp/jfr -jar app.jar
```

Ý nghĩa:

- `-XX:StartFlightRecording`: khởi động JFR recording khi JVM bắt đầu.
- `disk=true`: ghi recording vào disk repository.
- `maxage=6h`: giữ dữ liệu tối đa sáu giờ.
- `maxsize=1g`: giới hạn dữ liệu recording ở một gigabyte.
- `settings=default`: dùng cấu hình low-overhead mặc định.
- `-XX:FlightRecorderOptions=repository=...`: chọn thư mục chứa chunk tạm.
- `-jar app.jar`: khởi chạy ứng dụng.

Không chỉ định `duration` nghĩa là recording không có thời điểm tự kết thúc; mặc định duration là `0`, tức chạy vô hạn. Có thể thêm `dumponexit=true` nếu muốn JVM dump recording khi shutdown bình thường.

Ví dụ:

```sh
java -XX:StartFlightRecording=disk=true,maxage=6h,maxsize=1g,settings=default,dumponexit=true -XX:FlightRecorderOptions=repository=/var/tmp/jfr -jar app.jar
```

Nếu không chỉ định filename cho dump-on-exit, JFR tạo tên file tự động trong thư mục làm việc của process. Hãy xác định vị trí file theo output và cấu hình triển khai.

`dumponexit` hỗ trợ shutdown bình thường. Không dựa vào nó như cơ chế bảo đảm lưu file khi máy mất điện, process bị kill cưỡng bức hoặc JVM crash.

## 8. Bật continuous recording cho JVM đang chạy bằng jcmd

Không cần khởi động lại ứng dụng để bắt đầu recording nếu JVM hỗ trợ JFR và diagnostic attach.

Trước hết tìm PID:

```sh
jcmd -l
```

Ví dụ output:

```text
24680 com.example.OrderService
```

Kiểm tra command có sẵn:

```sh
jcmd 24680 help JFR.start
```

Bắt đầu continuous recording:

```sh
jcmd 24680 JFR.start name=continuous settings=default disk=true maxage=6h maxsize=1g duration=0s
```

Các tham số:

- `name=continuous`: đặt tên dễ nhận biết để gọi lại recording.
- `settings=default`: dùng cấu hình mặc định.
- `disk=true`: ghi dữ liệu vào repository trên disk.
- `maxage=6h`: giữ tối đa sáu giờ.
- `maxsize=1g`: giới hạn dung lượng dữ liệu recording.
- `duration=0s`: không tự kết thúc theo thời lượng.

JVM trả về thông tin recording vừa tạo, thường gồm ID, tên và trạng thái. Lưu lại tên recording để dùng với `JFR.check`, `JFR.dump` và `JFR.stop`.

`jcmd` phải chạy trên cùng máy với JVM đích và dùng effective user/group ID giống tài khoản đã khởi chạy JVM. Trong container, chạy công cụ trong đúng namespace và dùng PID mà namespace đó nhìn thấy. Nếu attach bị từ chối, kiểm tra user/group, quyền hệ điều hành và attach mechanism trước khi kết luận JFR không khả dụng.

Nếu command báo JFR không khả dụng, hãy kiểm tra vendor/JDK version, JVM target và các diagnostic command được hỗ trợ. Không giả định mọi Java implementation đều có cùng tập command.

## 9. Kiểm tra recording đang chạy

Dùng:

```sh
jcmd 24680 JFR.check
```

Lệnh hiển thị thông tin các recording đang hoạt động. Có thể chỉ định tên:

```sh
jcmd 24680 JFR.check name=continuous
```

Muốn xem event settings chi tiết:

```sh
jcmd 24680 JFR.check name=continuous verbose=true
```

Kiểm tra:

- Recording có đang chạy không?
- Tên và ID có đúng không?
- Recording dùng disk hay memory?
- Settings file nào đang được sử dụng?
- `maxage` và `maxsize` có đúng retention mong muốn không?
- Những event nào đang được bật?

`JFR.check` là lệnh kiểm tra trạng thái, không dừng hoặc thay đổi recording.

## 10. Dump dữ liệu gần thời điểm sự cố mà không dừng recording

Khi nhận cảnh báo, xuất một khoảng thời gian gần nhất:

```sh
jcmd 24680 JFR.dump name=continuous filename=/var/tmp/jfr-dumps/incident-last-30m.jfr begin=-30m
```

`begin=-30m` yêu cầu lấy dữ liệu từ 30 phút trước thời điểm dump. Có thể dùng `begin=-1h` để lấy một giờ gần nhất.

Có thể chỉ định cả thời điểm bắt đầu và kết thúc:

```sh
jcmd 24680 JFR.dump name=continuous filename=/var/tmp/jfr-dumps/incident-window.jfr begin=2026-11-10T09:00:00 end=2026-11-10T09:30:00
```

Thời điểm phải theo định dạng mà `java.time` có thể parse, ví dụ local time, local date-time hoặc ISO-8601 instant. Hãy đối chiếu timezone của event với timezone của log ứng dụng trước khi chọn mốc.

Điều quan trọng: **JFR.dump không dừng recording.** Sau khi file được tạo, continuous recording tiếp tục thu thập event mới và rolling window vẫn được duy trì.

Nếu không chỉ định tên recording trong `JFR.dump`, dữ liệu từ tất cả recording đang hoạt động có thể được đưa vào file. Nên chỉ định `name` khi JVM có nhiều recording để tránh file chứa dữ liệu ngoài phạm vi cần thiết.

## 11. Dừng recording và lưu file cuối cùng

Khi không cần continuous recording nữa, có thể dừng và lưu dữ liệu:

```sh
jcmd 24680 JFR.stop name=continuous filename=/var/tmp/jfr-dumps/continuous-final.jfr
```

Lệnh này dừng recording có tên `continuous` và ghi dữ liệu vào file được chỉ định.

Nếu gọi `JFR.stop` mà không có filename, dữ liệu recording có thể bị loại bỏ thay vì tạo file để phân tích. Vì vậy, hãy chỉ dừng khi đã xác định có cần giữ lại dữ liệu hay không.

| Thao tác | Kết quả |
|---|---|
| `JFR.dump` | Xuất file, recording vẫn chạy |
| `JFR.stop` có filename | Dừng recording và lưu file |
| `JFR.stop` không filename | Dừng recording, không giữ file dump |

Với continuous recording cần hoạt động lâu dài, ưu tiên dump theo thời điểm sự cố và để recording tiếp tục. Chỉ stop khi chủ động kết thúc việc thu thập.

## 12. Lấy dữ liệu qua JDK Mission Control

JDK Mission Control (JMC) là công cụ GUI để xem và phân tích file `.jfr`. JMC không nằm trong mọi bản cài JDK tiêu chuẩn; có thể cần cài riêng.

Quy trình cơ bản:

1. Mở JMC.
2. Mở file `.jfr` đã dump.
3. Xem Automated Analysis Results để tìm cảnh báo ban đầu.
4. Chọn khoảng thời gian quanh sự cố.
5. Mở các trang Code, Memory, Threads, Locks, Garbage Collections và I/O.
6. Đối chiếu event timestamp với log ứng dụng và distributed trace.
7. Drill down vào stack trace hoặc thread liên quan.

JMC có thể giúp trả lời:

- Thread nào tiêu thụ CPU?
- Có lock contention nào kéo dài?
- GC pause xảy ra khi nào?
- Heap usage thay đổi ra sao?
- I/O nào có latency cao?
- Class hoặc allocation site nào đáng chú ý?

Dữ liệu JFR chỉ phản ánh những event mà recording đã thu thập. Nếu cần allocation profiling nhưng recording liên tục đang dùng `default.jfc`, hãy tạo một recording profiling ngắn hoặc custom configuration phù hợp.

## 13. Phân tích file bằng công cụ dòng lệnh jfr

JDK cung cấp công cụ `jfr` trong thư mục `bin`.

Xem tổng quan file:

```sh
jfr summary /var/tmp/jfr-dumps/incident-last-30m.jfr
```

Lệnh summary hiển thị số lượng event, thời gian recording và dung lượng dữ liệu. Nó hữu ích để xác nhận file có event và đánh giá event settings.

In các event GC:

```sh
jfr print --categories GC /var/tmp/jfr-dumps/incident-last-30m.jfr
```

In một event cụ thể:

```sh
jfr print --events jdk.GCHeapSummary /var/tmp/jfr-dumps/incident-last-30m.jfr
```

In event ở dạng JSON để xử lý tiếp:

```sh
jfr print --json --events jdk.ExecutionSample /var/tmp/jfr-dumps/incident-last-30m.jfr
```

Có thể xem danh sách event metadata:

```sh
jfr metadata /var/tmp/jfr-dumps/incident-last-30m.jfr
```

Không nên in toàn bộ recording lớn ra terminal nếu không cần thiết. Hãy lọc theo category hoặc event để giảm output và tập trung vào câu hỏi điều tra.

## 14. Điều chỉnh event settings cho continuous recording

Template quy định event nào được thu thập và mức độ chi tiết. Nếu cần thêm event:

- Dùng JMC Template Manager để tạo custom configuration.
- Hoặc dùng công cụ `jfr configure` để tạo file `.jfc` mới.
- Giữ file custom trong thư mục cấu hình do ứng dụng quản lý.
- Khởi động recording với `settings=/path/to/custom.jfc`.

Ví dụ tạo cấu hình mới dựa trên default:

```sh
jfr configure --input default.jfc --output continuous-custom.jfc
```

Có thể thay đổi event setting theo cú pháp:

```text
<event-name>#<setting-name>=<value>
```

Ví dụ một số event có threshold hoặc period. Giảm threshold sẽ thu thập event ngắn hơn và tăng số event; tăng stack trace hoặc bật thêm event có thể làm file lớn hơn và tăng overhead.

Không chỉnh trực tiếp file `default.jfc` hoặc `profile.jfc` được JDK cài đặt. Tạo bản sao/custom file để dễ review, version-control và tái sử dụng giữa môi trường.

Khi thay đổi cấu hình, kiểm tra recording mới bằng `JFR.check name=... verbose=true` và xem `jfr summary` sau một khoảng thu thập thử nghiệm.

## 15. Continuous recording mặc định không phải allocation profiler

Đây là giới hạn quan trọng khi điều tra memory:

- `default.jfc` phù hợp ghi liên tục với overhead thấp.
- Cấu hình này không thu thập heap statistics và allocation profiling đầy đủ như một profiling recording.
- Nếu chỉ bật continuous recording mặc định, có thể không đủ dữ liệu để xác định chính xác method nào cấp phát nhiều object nhất.
- Khi nghi ngờ memory leak, dùng histogram, heap dump hoặc một profiling recording có event allocation phù hợp.

Một quy trình thường dùng:

1. Giữ continuous recording mặc định để có lịch sử runtime.
2. Khi heap hoặc live set tăng bất thường, dump khoảng thời gian liên quan.
3. Dùng JMC xem GC, heap và event sẵn có.
4. Nếu cần allocation site, bắt đầu profiling recording ngắn với `profile.jfc` hoặc custom settings.
5. Nếu cần object graph và reference chain, tạo heap dump theo quy trình vận hành phù hợp.

Không tăng mọi event lên mức chi tiết cao trong continuous recording chỉ để “phòng trường hợp cần”. Điều đó có thể làm file lớn, tăng chi phí ghi và tạo thêm dữ liệu khó phân tích.

## 16. Quản lý repository và dung lượng disk

Repository thường nằm trong temporary directory của hệ điều hành nếu không chỉ định. Có thể chọn thư mục riêng ngay lúc JVM khởi động:

```sh
java -XX:StartFlightRecording=disk=true,maxage=6h,maxsize=1g,settings=default -XX:FlightRecorderOptions=repository=/var/tmp/jfr-repository -jar app.jar
```

Khi chọn repository:

- Đảm bảo thư mục tồn tại hoặc JVM có thể tạo thư mục.
- Tài khoản chạy JVM phải có quyền đọc/ghi.
- Chọn filesystem có dung lượng và hiệu năng phù hợp.
- Tránh thư mục tạm bị dọn trong lúc JVM còn chạy.
- Theo dõi dung lượng toàn repository và các file dump cuối cùng.
- Đặt quyền truy cập hạn chế vì event có thể chứa thông tin nội bộ.

Giới hạn `maxsize` áp dụng cho recording data được giữ trong repository. File `.jfr` đã dump ra thư mục khác là artifact riêng và cần retention policy riêng. Không giả định giới hạn repository sẽ tự xóa các file dump cũ.

Có thể dùng `-XX:FlightRecorderOptions=preserve-repository=true` nếu cần giữ chunk repository sau khi JVM thoát để phục vụ recovery. Mặc định repository thường được dọn khi process kết thúc. Chỉ bật preserve khi có quy trình quản lý và dọn dẹp rõ ràng, vì các chunk có thể tiếp tục chiếm disk.

## 17. Khôi phục recording từ repository sau sự cố

JFR ghi file theo chunk. Nếu JVM gặp lỗi nghiêm trọng, một số chunk đã hoàn tất có thể vẫn còn trong repository. Khi repository được giữ lại, có thể dùng:

```sh
jfr assemble /var/tmp/jfr-repository /var/tmp/jfr-dumps/recovered.jfr
```

`jfr assemble` ghép các chunk hợp lệ theo thứ tự thời gian thành một recording. Chunk chưa hoàn tất có thể bị loại khỏi quá trình assemble.

Recovery phụ thuộc vào chunk còn tồn tại và không bị hỏng. Không có gì bảo đảm mọi event ngay trước crash đều được flush đầy đủ.

Nếu cần giữ repository qua lần JVM exit/crash, cấu hình `preserve-repository=true` và kiểm tra đường dẫn thực tế trước khi triển khai. Sau khi recovery, xác minh file bằng `jfr summary` và mở thử bằng JMC.

## 18. Tác động hiệu năng và cách vận hành an toàn

JFR được thiết kế để ghi event với overhead thấp, nhưng chi phí phụ thuộc vào event settings, workload, event rate, stack depth và thời gian ghi.

Khuyến nghị:

- Dùng `default.jfc` cho continuous recording dài hạn.
- Dùng `profile.jfc` trong thời gian ngắn khi cần dữ liệu sâu hơn.
- Giữ `maxage` và `maxsize` trong giới hạn dung lượng đã được tính toán.
- Không bật stack trace hoặc allocation event rộng hơn nhu cầu nếu chưa đánh giá overhead.
- Không tăng stack depth tùy tiện; giá trị lớn hơn mặc định có thể ảnh hưởng hiệu năng.
- Theo dõi dung lượng repository và thư mục dump.
- Thử nghiệm trên staging với workload gần production trước khi triển khai toàn bộ.
- Ghi lại JDK version, template, event settings và retention trong runbook.

Một continuous recording có thể làm tăng I/O ghi disk. Nếu disk chậm hoặc gần đầy, tác động có thể xuất hiện ngoài bản thân JFR. Hãy giám sát cả dung lượng trống và latency storage.

Không nên dùng JFR làm hệ thống lưu trữ log vô hạn. Hãy giữ cửa sổ đủ dài để bắt được sự cố, nhưng có giới hạn để tránh chiếm hết disk.

## 19. Bảo mật dữ liệu trong file JFR

File `.jfr` có thể chứa:

- Tên class, package và method nội bộ.
- Stack trace và đường dẫn code.
- Tên thread, host, process và thông tin runtime.
- Tên file, socket endpoint và dữ liệu I/O metadata.
- Thông tin về hoạt động của ứng dụng và thời điểm request.
- Custom event fields do ứng dụng tự ghi, có thể chứa dữ liệu nghiệp vụ nếu thiết kế không cẩn thận.

Không giả định file JFR chỉ chứa metric vô danh. Hãy coi recording là artifact chẩn đoán nội bộ.

Khi lưu hoặc chia sẻ:

- Chỉ cấp quyền truy cập cho người cần phân tích.
- Không upload file lên nơi công khai.
- Mã hóa khi chuyển qua mạng hoặc lưu ở nơi dùng chung.
- Xóa file theo retention policy.
- Che hoặc loại event nhạy cảm trước khi gửi ra ngoài.

Có thể dùng `jfr scrub` để loại một số event, category hoặc thread khỏi file:

```sh
jfr scrub --exclude-categories "File I/O,Socket I/O" input.jfr sanitized.jfr
```

Hãy kiểm tra lại file đã scrub bằng `jfr summary` và `jfr print`. Scrub có thể làm mất dữ liệu cần cho chẩn đoán; chỉ loại event sau khi hiểu ảnh hưởng đến phân tích.

## 20. Ví dụ Java 17+: chạy ứng dụng và bật continuous recording

Tạo file `JfrContinuousDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class JfrContinuousDemo {
    private static volatile byte[] lastPayload;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                byte[] payload = new byte[16 * 1024];
                payload[0] = 1;
                lastPayload = payload;

                try {
                    Thread.sleep(100);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "jfr-demo-worker");

        worker.setDaemon(true);
        worker.start();

        System.out.println("READY");
        new CountDownLatch(1).await();
    }
}
```

Biên dịch:

```sh
javac JfrContinuousDemo.java
```

Chạy:

```sh
java JfrContinuousDemo
```

Stdout chính xác:

```text
READY
```

Chương trình giữ JVM hoạt động và tạo allocation workload nhỏ trong background. Mở terminal thứ hai và tìm PID:

```sh
jcmd -l
```

Giả sử PID của demo là `24680`, bật continuous recording:

```sh
jcmd 24680 JFR.start name=continuous settings=default disk=true maxage=30m maxsize=256m duration=0s
```

Kiểm tra:

```sh
jcmd 24680 JFR.check name=continuous verbose=true
```

Sau một khoảng thời gian, dump 10 phút gần nhất:

```sh
jcmd 24680 JFR.dump name=continuous filename=continuous-demo.jfr begin=-10m
```

Xem tổng quan file:

```sh
jfr summary continuous-demo.jfr
```

Sau khi thực hành, có thể tiếp tục dump để xác nhận recording vẫn chạy. Dừng và lưu file cuối cùng:

```sh
jcmd 24680 JFR.stop name=continuous filename=continuous-final.jfr
```

PID trong ví dụ chỉ minh họa. Thay bằng PID thực tế từ `jcmd -l`. Sau khi dừng recording, quay lại terminal chạy chương trình và nhấn Ctrl+C để kết thúc demo.

## 21. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jcmd: command not found` | Chưa cài JDK hoặc `JAVA_HOME/bin` chưa có trong PATH | Dùng `jcmd` thuộc JDK và kiểm tra đường dẫn |
| Không tìm thấy PID | PID sai, process đã dừng hoặc container namespace khác | Dùng `jcmd -l`, `jps -l` hoặc công cụ OS trong đúng namespace |
| Attach bị từ chối | Khác user/group hoặc attach bị vô hiệu hóa | Chạy bằng cùng tài khoản với JVM và kiểm tra runtime |
| `JFR.start` không tồn tại | JVM không hỗ trợ command hoặc JFR không khả dụng | Chạy `jcmd PID help` và kiểm tra JDK/vendor |
| Recording không còn trong `JFR.check` | Recording đã stop, JVM restart hoặc dùng sai tên | Kiểm tra tên, ID, PID và trạng thái JVM |
| Không có file sau `JFR.dump` | Đường dẫn không hợp lệ hoặc target JVM không có quyền ghi | Dùng đường dẫn tuyệt đối có quyền ghi trên máy đích |
| Recording không giữ đủ sáu giờ | `maxsize` bị chạm trước `maxage` do event rate cao | Tăng giới hạn dung lượng hoặc giảm event volume |
| Repository đầy | Không đặt retention, có nhiều recording hoặc dump files không được dọn | Cấu hình maxage/maxsize và dọn file dump theo policy |
| File JFR nhỏ hoặc thiếu event mong đợi | Template không bật event hoặc threshold chưa đạt | Kiểm tra `JFR.check verbose=true`, settings và event threshold |
| Không thấy allocation profiling | Dùng `default.jfc` continuous template | Tạo profiling recording ngắn hoặc custom configuration |
| Recording bị dừng khi dump | Nhầm `JFR.dump` với `JFR.stop` | Dùng `JFR.dump` để xuất file mà vẫn tiếp tục recording |
| File JFR không mở được sau crash | Chunk cuối chưa hoàn tất hoặc repository đã bị xóa | Dùng repository được preserve và thử `jfr assemble` |
| JFR làm tăng disk I/O | Event rate cao, profile template hoặc recording quá chi tiết | Trở về default, điều chỉnh event settings và theo dõi storage |
| Không tìm thấy repository sau khi JVM thoát | Repository mặc định bị xóa khi process kết thúc | Cấu hình preserve repository nếu cần recovery |

Khi gặp lỗi, xác định recording đang chạy hay đã dừng trước. Sau đó kiểm tra PID, quyền attach, tên recording, đường dẫn repository, retention và event settings.

## 22. Quy trình continuous recording cho production

Một quy trình vận hành có thể triển khai:

1. Chọn JDK có JFR và xác nhận các command `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop` được hỗ trợ.
2. Chọn `default.jfc` cho continuous recording nền.
3. Xác định cửa sổ lịch sử cần giữ, ví dụ sáu giờ.
4. Tính dung lượng cần thiết từ tốc độ event thực tế; đặt `maxage` và `maxsize`.
5. Chọn repository trên filesystem đủ dung lượng và có quyền ghi.
6. Bật recording lúc startup hoặc dùng `jcmd` cho JVM đang chạy.
7. Xác nhận bằng `JFR.check`.
8. Khi alert xảy ra, ghi lại timestamp, timezone, PID và incident ID.
9. Dump khoảng thời gian trước và sau sự cố nếu cần.
10. Mở file bằng JMC hoặc dùng `jfr summary`/`jfr print`.
11. Đối chiếu event với application log, metric và trace.
12. Lưu file điều tra theo retention policy và bảo vệ quyền truy cập.
13. Nếu cần allocation/method profiling, tạo recording ngắn với cấu hình chi tiết hơn.
14. Sau khi điều tra xong, stop recording chỉ khi không còn nhu cầu thu thập.

Trong runbook, ghi rõ ai được phép dump recording, file được lưu ở đâu, ai được truy cập, thời hạn lưu trữ và cách scrub dữ liệu trước khi chia sẻ.

## 23. Checklist

- [ ] Đã xác nhận JFR được hỗ trợ trên JVM mục tiêu.
- [ ] Đã chọn `default.jfc` cho continuous recording nền.
- [ ] Đã hiểu khác biệt giữa continuous recording và profiling recording.
- [ ] Đã đặt `disk=true` nếu cần lưu rolling data trên disk.
- [ ] Đã đặt `maxage` và/hoặc `maxsize`.
- [ ] Đã kiểm tra dung lượng và quyền ghi của repository.
- [ ] Đã biết cách tìm PID và attach bằng `jcmd`.
- [ ] Đã kiểm tra recording bằng `JFR.check`.
- [ ] Đã biết dump một khoảng thời gian bằng `JFR.dump`.
- [ ] Đã phân biệt `JFR.dump` với `JFR.stop`.
- [ ] Đã hiểu default continuous recording không bật allocation profiling chi tiết.
- [ ] Đã biết mở file bằng JMC và kiểm tra bằng `jfr summary`.
- [ ] Đã có retention policy cho repository và file dump.
- [ ] Đã bảo vệ file JFR và scrub event nhạy cảm trước khi chia sẻ.
- [ ] Đã ghi lại JDK version, event settings, timezone và incident timestamp.

## 24. Tài liệu tham khảo

- Oracle JDK 21 Troubleshooting Guide — Flight Recorder and Continuous Recordings: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 Tool Reference — The `java` Command and `-XX:StartFlightRecording`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 Tool Reference — The `jfr` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Java SE 21 API — `jdk.jfr.Recording`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html

Continuous recording giữ lại lịch sử runtime gần đây để điều tra sự cố sau khi nó xảy ra. Hãy dùng cấu hình `default` với retention có giới hạn, dump đúng khoảng thời gian bằng `JFR.dump`, và chỉ chuyển sang profiling chi tiết khi câu hỏi điều tra cần thêm dữ liệu. Quản lý repository, file dump và quyền truy cập như các artifact chẩn đoán production.