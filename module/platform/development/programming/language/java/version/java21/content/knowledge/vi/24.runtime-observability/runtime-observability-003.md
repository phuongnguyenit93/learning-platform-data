# Đọc thread dump có hỗ trợ virtual thread bằng công cụ JDK 21

Virtual thread là `Thread` do Java runtime quản lý, không gắn cố định với một OS thread. Vì một JVM có thể chạy hàng nghìn hoặc hàng triệu virtual thread, thread dump truyền thống vốn tập trung vào platform thread không thể hiện đầy đủ hoạt động của ứng dụng dùng virtual thread.

Trong JDK 21, công cụ phù hợp để lấy dump có virtual thread là lệnh `jcmd <pid> Thread.dump_to_file`. Lệnh này xuất thread dump ra file ở định dạng text hoặc JSON, bao gồm platform thread và virtual thread. JSON phù hợp cho công cụ phân tích; text thuận tiện để đọc thủ công. Cần hiểu giới hạn của dump này: nó không cung cấp toàn bộ thông tin khóa, địa chỉ object, JNI hay heap statistics có trong thread dump truyền thống.

## 1. Vì sao cần thread dump riêng cho virtual thread?

Thread dump truyền thống thường được lấy bằng `jstack` hoặc `jcmd <pid> Thread.print`. Trên JDK 21, các công cụ này không liệt kê đầy đủ virtual thread. Một virtual thread có thể đang chờ I/O và đã unmount khỏi carrier; khi đó OS chỉ nhìn thấy platform thread/carrier, không nhìn thấy toàn bộ task Java đang chờ.

`jcmd <pid> Thread.dump_to_file` được bổ sung để quan sát cả platform thread lẫn virtual thread. Nó hữu ích khi điều tra:

- Request chậm hoặc bị treo trong ứng dụng thread-per-request.
- Nhiều virtual thread đang chờ socket hoặc một điều kiện đồng bộ.
- Task không hoàn tất dù số platform thread đang hoạt động thấp.
- Chênh lệch giữa số request đồng thời và số carrier thread.
- Tác vụ bị mắc ở một call stack, thư viện hoặc điểm chờ cụ thể.

Thread dump là ảnh chụp trạng thái tại một thời điểm, không phải lịch sử thực thi. Nếu cần biết một virtual thread đã chờ bao lâu, được unpark khi nào hoặc bị pin trong khoảng nào, hãy kết hợp thread dump với Java Flight Recorder (JFR).

## 2. Phân biệt virtual thread và carrier trong dump

Virtual thread là đơn vị thực thi của ứng dụng. Carrier là platform thread mà runtime mount virtual thread lên để thực thi mã. Khi virtual thread unmount trong lúc chờ, carrier có thể chạy virtual thread khác.

Vì vậy:

- Một carrier không đại diện cho một request cố định trong toàn bộ vòng đời.
- Một virtual thread có thể chạy trên nhiều carrier ở các thời điểm khác nhau.
- Khi virtual thread unmount, nó vẫn tồn tại và có thể đang chờ I/O hoặc synchronization.
- Số carrier trong dump không phản ánh tổng số virtual thread của ứng dụng.

Khi đọc dump, hãy tìm tên, ID, trạng thái và stack trace của virtual thread để hiểu request/task đang làm gì. Không suy ra rằng virtual thread không tồn tại chỉ vì nó không xuất hiện trong danh sách OS thread.

## 3. Điều kiện để chạy jcmd

`jcmd` là công cụ chẩn đoán đi kèm JDK. Nên dùng công cụ từ JDK tương thích với runtime của tiến trình đích. Trước khi chạy, kiểm tra:

1. Máy đang chạy `jcmd` là máy có JVM đích.
2. Người dùng chạy `jcmd` có cùng effective user và group với tiến trình JVM đích.
3. PID thuộc đúng tiến trình Java cần điều tra.
4. Đường dẫn file đích có thể được tiến trình JVM ghi vào và còn đủ dung lượng.
5. Quyền attach của JVM không bị vô hiệu hóa bởi cấu hình vận hành.

Trong môi trường container, PID nhìn từ host có thể khác PID bên trong container. Thực hiện lệnh trong cùng container hoặc cùng PID namespace với JVM đích để tránh nhắm nhầm tiến trình.

## 4. Tìm PID của JVM

Chạy `jcmd -l` để liệt kê các tiến trình Java mà công cụ có thể nhìn thấy:

```bash
jcmd -l
```

Ví dụ kết quả:

```text
18420 com.example.OrderApplication
19208 com.example.WorkerApplication
```

Nếu ứng dụng cần điều tra là `OrderApplication`, dùng PID `18420` trong các lệnh tiếp theo. Không sao chép PID mẫu này vào môi trường thật; PID thay đổi theo từng lần chạy.

Nếu không thấy tiến trình:

- Kiểm tra JVM có chạy trên máy hoặc PID namespace hiện tại không.
- Kiểm tra user chạy `jcmd` có quyền attach không.
- Nếu chạy trong container, kiểm tra từ bên trong container.
- Dùng `jcmd <pid> help` để xác nhận tiến trình có nhận lệnh chẩn đoán.

## 5. Kiểm tra cú pháp lệnh trên JVM đích

Danh sách diagnostic command phụ thuộc JDK và VM đang chạy. Có thể hỏi trực tiếp JVM:

```bash
jcmd 18420 help Thread.dump_to_file
```

Để xem tất cả command có sẵn:

```bash
jcmd 18420 help
```

Thay `18420` bằng PID thực tế. Bước này đặc biệt hữu ích khi ứng dụng chạy trên nhiều phiên bản JDK hoặc khi script chẩn đoán được dùng ở nhiều môi trường.

## 6. Tạo thread dump dạng text

Trong JDK 21, lệnh sau ghi thread dump dễ đọc ra file:

```bash
jcmd 18420 Thread.dump_to_file -format=text /var/tmp/order-threads.txt
```

Chọn một đường dẫn tuyệt đối mà JVM đích có quyền ghi. Trên Windows có thể dùng đường dẫn như `C:\temp\order-threads.txt`; trên Linux có thể dùng `/var/tmp/order-threads.txt` hoặc một thư mục chẩn đoán đã được cấp quyền.

Text phù hợp khi kỹ sư cần mở file và đọc stack trace bằng editor. Nếu ứng dụng có rất nhiều virtual thread, file có thể lớn; hãy dự trù dung lượng và dùng tên file riêng cho mỗi lần lấy dump.

## 7. Tạo thread dump dạng JSON

Để đưa dump vào công cụ phân tích hoặc xử lý bằng script, dùng JSON:

```bash
jcmd 18420 Thread.dump_to_file -format=json /var/tmp/order-threads.json
```

JSON được thiết kế để công cụ đọc và phân tích. Tránh viết parser phụ thuộc vào các chi tiết nội bộ không được tài liệu hóa mà không kiểm tra phiên bản JDK. Nếu công cụ phân tích yêu cầu một schema cụ thể, hãy xác nhận nó hỗ trợ định dạng dump do JDK đang chạy tạo ra.

Trong cả hai định dạng, lệnh tạo file chứa thông tin thread của JVM đích. Không cần dừng hoặc restart ứng dụng chỉ để lấy dump.

## 8. Khác biệt với jstack và Thread.print trên JDK 21

| Công cụ | Nội dung chính trên JDK 21 | Khi nào dùng |
|---|---|---|
| `jstack <pid>` | Thread dump truyền thống, tập trung vào platform thread | Điều tra platform thread và stack trace truyền thống |
| `jcmd <pid> Thread.print` | Thread dump truyền thống của platform thread | Quan sát platform thread; có tùy chọn hiển thị lock của `java.util.concurrent` |
| `jcmd <pid> Thread.dump_to_file -format=text <file>` | Dump ra file có platform thread và virtual thread | Đọc thủ công ứng dụng dùng virtual thread |
| `jcmd <pid> Thread.dump_to_file -format=json <file>` | Dump ra JSON có platform thread và virtual thread | Công cụ phân tích, dashboard hoặc xử lý tự động |

Trên JDK 21, không dùng `jstack` hoặc `Thread.print` làm bằng chứng rằng không có virtual thread đang chờ. Hãy lấy thêm `Thread.dump_to_file` để quan sát virtual thread.

### Lưu ý khi chạy trên JDK mới hơn

Hành vi của công cụ chẩn đoán đã tiếp tục được mở rộng sau JDK 21. Tài liệu `jcmd` của JDK 26 mô tả `Thread.print` có thể in platform thread và các virtual thread đang mounted. Điều này vẫn không tương đương với dump toàn bộ virtual thread, vì virtual thread đã unmount không phải là mounted virtual thread tại thời điểm lấy dump.

`Thread.dump_to_file` vẫn là lựa chọn để ghi toàn bộ thread ra file. Khi điều tra trên JDK mới hơn, kiểm tra `jcmd <pid> help Thread.print` và tài liệu đúng phiên bản runtime thay vì áp dụng nguyên xi giới hạn của JDK 21.

## 9. Đọc trạng thái và stack trace

Khi mở file dump, nên đọc theo thứ tự:

1. Tìm virtual thread theo tên hoặc ID.
2. Xem trạng thái thread tại thời điểm dump.
3. Đọc stack trace từ frame ứng dụng xuống các frame thư viện/JDK.
4. Xác định lời gọi blocking, điểm chờ hoặc đoạn xử lý đang chạy.
5. So sánh nhiều dump được lấy cách nhau một khoảng thời gian để xem stack có thay đổi không.

Các trạng thái thường gặp:

| Trạng thái | Cách hiểu khi điều tra |
|---|---|
| `RUNNABLE` | Thread có thể chạy hoặc đang chạy; không đảm bảo nó luôn tiêu thụ CPU tại đúng thời điểm dump |
| `WAITING` | Đang chờ một hành động khác, thường không có timeout |
| `TIMED_WAITING` | Đang chờ có giới hạn thời gian, ví dụ sleep hoặc timed wait |
| `BLOCKED` | Đang chờ lấy intrinsic monitor |
| `TERMINATED` | Thread đã kết thúc; thường không còn là task đang hoạt động |

`Thread.State` là mô tả tổng quát. Đặc biệt, `RUNNABLE` không chứng minh thread đang sử dụng CPU liên tục; một số lời gọi native hoặc hoạt động của hệ điều hành có thể làm thread không tiến triển dù trạng thái vẫn là `RUNNABLE`.

Không kết luận deadlock chỉ từ một thread ở `BLOCKED` hoặc `WAITING`. Cần xem các thread liên quan, tài nguyên chúng chờ và quan hệ khóa. Dump `Thread.dump_to_file` của JDK 21 không cung cấp đầy đủ lock information hoặc deadlock detection như dump truyền thống.

## 10. Nhận diện các mẫu stack thường gặp

Một số mẫu stack có thể gợi ý hướng điều tra:

| Dấu hiệu trong stack | Khả năng cần kiểm tra |
|---|---|
| Socket read hoặc network client call | Request đang chờ phản hồi từ dịch vụ bên ngoài; kiểm tra timeout, latency và kết nối |
| `LockSupport.park` hoặc lớp đồng bộ `java.util.concurrent` | Task đang chờ queue, semaphore, lock hoặc future; tìm thành phần đánh thức nó |
| `Thread.sleep` | Task đang chủ động chờ; kiểm tra backoff, retry hoặc delay |
| Database driver hoặc JDBC call | Truy vấn hoặc lấy connection đang chờ; kiểm tra connection pool và thời gian truy vấn |
| Nhiều stack giống nhau trong cùng một service call | Có thể là tải cao, một dependency chậm hoặc một điểm nghẽn chung |
| Cùng một virtual thread xuất hiện với stack không đổi qua nhiều lần dump | Task có thể bị kẹt, chờ lâu hoặc phụ thuộc vào sự kiện chưa xảy ra |

Tên lớp và method cụ thể phụ thuộc implementation, provider, driver và JDK. Hãy bắt đầu từ frame thuộc ứng dụng hoặc thư viện mà ứng dụng trực tiếp sử dụng, rồi lần theo lời gọi xuống tầng JDK.

## 11. Dùng tên virtual thread có ý nghĩa

Tên mặc định có thể giúp phân biệt virtual thread, nhưng không phải lúc nào cũng cho biết request hoặc loại tác vụ. Khi tạo virtual thread trực tiếp, đặt tên theo vai trò và có thể thêm sequence number:

```java
Thread requestThread = Thread.ofVirtual()
        .name("http-request-", 0)
        .start(() -> handleRequest(request));
```

Với executor tạo virtual thread cho từng task, có thể truyền `ThreadFactory`:

```java
import java.util.concurrent.Executors;

var factory = Thread.ofVirtual()
        .name("background-job-", 0)
        .factory();

try (var executor = Executors.newThreadPerTaskExecutor(factory)) {
    executor.submit(this::rebuildIndex);
}
```

Tên thread nên mô tả loại công việc, không nên chứa access token, dữ liệu cá nhân hoặc toàn bộ request URL có query nhạy cảm. Nếu cần liên kết với một request cụ thể, dùng request ID đã được kiểm soát trong log/tracing thay vì nhúng secret vào thread name.

## 12. Giới hạn của thread dump JDK 21

Thread dump từ `Thread.dump_to_file` giúp nhìn thấy virtual thread, nhưng không thay thế mọi công cụ chẩn đoán khác.

Các giới hạn quan trọng trên JDK 21:

- Không có object addresses.
- Không có thông tin lock như thread dump truyền thống.
- Không có JNI statistics hoặc heap statistics.
- Không thực hiện deadlock detection.
- Dump không phải một snapshot stop-the-world đồng nhất; trạng thái có thể thay đổi trong khi dump được tạo.
- Khi có rất nhiều virtual thread, file có thể rất lớn và việc tạo/đọc dump có chi phí I/O, CPU và dung lượng.

Vì vậy:

- Dùng `Thread.dump_to_file` để thấy virtual thread và call stack của chúng.
- Dùng `Thread.print -l` để kiểm tra lock của platform thread theo khả năng của dump truyền thống trên JDK 21.
- Dùng JFR để xem sự kiện theo thời gian, bao gồm pinning và các thao tác I/O.
- Dùng heap dump hoặc công cụ quản lý bộ nhớ khi vấn đề liên quan đến object retention hay heap; thread dump không phải heap dump.

## 13. Kết hợp với Java Flight Recorder

Thread dump cho biết task đang ở đâu tại thời điểm lấy mẫu. JFR cung cấp các sự kiện theo thời gian để trả lời câu hỏi task bắt đầu, kết thúc hoặc bị pin khi nào.

Các event liên quan virtual thread trong JDK 21:

| Event | Ý nghĩa | Cấu hình mặc định |
|---|---|---|
| `jdk.VirtualThreadStart` | Virtual thread bắt đầu | Tắt mặc định |
| `jdk.VirtualThreadEnd` | Virtual thread kết thúc | Tắt mặc định |
| `jdk.VirtualThreadPinned` | Virtual thread bị pin và carrier không được giải phóng lâu hơn ngưỡng | Bật mặc định, ngưỡng 20 ms |
| `jdk.VirtualThreadSubmitFailed` | Không thể start hoặc unpark virtual thread, thường do vấn đề tài nguyên | Bật mặc định |

Có thể đọc các event đã được ghi trong file JFR:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

`jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd` phải được bật trong JFR configuration hoặc JDK Mission Control trước khi ghi nếu cần dùng chúng. `jdk.VirtualThreadPinned` giúp tìm các trường hợp pinning đủ lâu theo ngưỡng; không có event này không chứng minh mọi thao tác blocking đều unmount thành công.

Quy trình điều tra hữu ích là lấy thread dump khi vấn đề đang xảy ra, đồng thời giữ JFR recording bao phủ khoảng thời gian đó. Sau đó đối chiếu thread name/ID, stack trace, thời điểm và event pinning.

## 14. Quy trình điều tra sự cố thực tế

Khi ứng dụng dùng virtual thread bị chậm hoặc có dấu hiệu treo, có thể làm theo các bước:

1. Ghi nhận thời điểm, phiên bản JDK, PID, tải request và triệu chứng.
2. Chạy `jcmd -l` để xác nhận PID.
3. Kiểm tra cú pháp bằng `jcmd <pid> help Thread.dump_to_file`.
4. Lấy một dump text để đọc nhanh và một dump JSON nếu cần phân tích tự động.
5. Tìm các virtual thread theo tên, trạng thái và stack trace liên quan.
6. Lặp lại dump sau một khoảng thời gian để xác định stack nào không thay đổi.
7. Nếu nghi ngờ pinning hoặc vấn đề theo thời gian, lấy JFR và xem các event virtual thread.
8. Kiểm tra dependency bên ngoài, connection pool, timeout, lock và giới hạn tài nguyên theo stack đã tìm thấy.
9. Lưu dump và recording ở nơi có quyền truy cập hạn chế; xóa hoặc hết hạn chúng theo chính sách vận hành.

Không nên chỉ tăng số carrier hoặc restart ứng dụng ngay khi thấy nhiều virtual thread đang chờ. Trước tiên cần xác định chúng đang chờ I/O, lock, semaphore, connection pool hay một task khác.

## 15. Bảo vệ file thread dump

Thread dump thường chứa tên thread, tên class, package, đường dẫn code và thông tin nội bộ của ứng dụng. Một số tên thread hoặc stack có thể tiết lộ tenant, endpoint hoặc cấu trúc hệ thống nếu ứng dụng đưa dữ liệu đó vào tên.

Hãy xem file dump là artifact chẩn đoán nội bộ:

- Ghi vào thư mục có quyền truy cập hạn chế.
- Không đặt file dump trong thư mục public hoặc web root.
- Không đính kèm vào ticket công khai nếu chưa rà soát thông tin nội bộ.
- Kiểm soát thời gian lưu và quyền tải xuống.
- Dùng tên file có PID/thời điểm nhưng không chứa dữ liệu nhạy cảm.

JSON không làm dữ liệu trong dump trở nên ít nhạy cảm hơn text. Hãy bảo vệ cả hai định dạng như nhau.

## 16. Tổng kết

Trên JDK 21, dùng `jcmd <pid> Thread.dump_to_file -format=text <file>` để đọc thủ công hoặc `-format=json` để đưa vào công cụ phân tích. Đây là lệnh chuyên dụng để quan sát platform thread và virtual thread; `jstack` và `jcmd Thread.print` truyền thống không hiển thị đầy đủ virtual thread trong JDK 21.

Đọc dump bằng cách xác định thread, trạng thái và stack trace, rồi so sánh nhiều lần lấy mẫu. Hãy nhớ giới hạn của dump JDK 21 về lock information, object address, JNI/heap statistics và deadlock detection. Kết hợp JFR khi cần hiểu diễn biến theo thời gian hoặc điều tra pinning. Khi chạy trên JDK mới hơn, kiểm tra lại khả năng của `Thread.print` và `Thread.dump_to_file` theo đúng phiên bản runtime.

## Tài liệu tham khảo

- [Oracle Java 21 — Virtual Threads: Viewing Virtual Threads in jcmd Thread Dumps](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — lệnh `Thread.dump_to_file`, định dạng text/JSON và giới hạn của dump.
- [Java SE 21 — jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — cách gửi diagnostic command tới JVM đang chạy và các yêu cầu vận hành.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) — lý do có thread dump riêng cho virtual thread và các đặc điểm của định dạng dump.
- [Oracle Java 21 — JDK Flight Recorder Events for Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — event start/end, pinned và submit failed.
- [Java SE 26 — jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — hành vi mới hơn của `Thread.print`, gồm platform thread và mounted virtual thread.
