# I/O event trong Java Flight Recorder

**I/O event** trong Java Flight Recorder (JFR) là sự kiện ghi nhận một số thao tác đọc và ghi file hoặc socket của JVM, cùng thời gian thực hiện, thread, dữ liệu truyền và ngữ cảnh gọi. Những event này giúp tìm các điểm I/O chậm, xác định file hoặc remote host liên quan và lần theo stack trace dẫn tới thao tác.

Bốn event quan trọng là **jdk.FileRead**, **jdk.FileWrite**, **jdk.SocketRead** và **jdk.SocketWrite**. JFR còn cung cấp các view tổng hợp theo đường dẫn file, remote host và loại độ trễ. Khi phân tích, cần phân biệt thời gian của một thao tác I/O tại JVM với thời gian xử lý end-to-end của request; một lần đọc socket chậm không tự chứng minh server từ xa xử lý chậm.

Bài học hướng dẫn cách thu thập, đọc và diễn giải I/O event bằng JFR, JDK Mission Control (JMC), jcmd và jfr CLI; có lab Java 17+ tạo file I/O và loopback socket I/O để thực hành.

## 1. I/O event giải quyết câu hỏi gì?

Khi ứng dụng chậm, nguyên nhân có thể nằm ở CPU, garbage collection, lock contention, file system, network hoặc service phụ thuộc. I/O event giúp trả lời các câu hỏi:

- Thread nào đang đọc hoặc ghi file?
- File path nào có thao tác chậm?
- Ứng dụng đang đọc/ghi bao nhiêu byte?
- Remote host và port nào liên quan đến socket I/O?
- Một lần đọc socket kéo dài bao lâu?
- Stack trace nào dẫn tới thao tác I/O?
- Thao tác chậm tập trung ở một file, một host hay nhiều dependency?
- Độ trễ đến từ file read, file write, socket read hay socket write?

JFR ghi lại sự kiện ở các điểm I/O được JVM instrument. Dữ liệu có thể bao gồm thời gian bắt đầu, duration, thread, stack trace, đường dẫn file hoặc thông tin endpoint. JFR không ghi nội dung file hay payload mạng trong các event I/O chuẩn này.

### I/O event khác CPU profiling

CPU profiling lấy mẫu thread khi chúng đang thực thi code. I/O event ghi nhận thời gian của các thao tác I/O được instrument.

Một thread có thể dùng rất ít CPU nhưng vẫn làm request chậm vì đang chờ socket hoặc file. Ngược lại, một thread có thể liên tục tính toán sau khi đọc dữ liệu và tạo CPU hot method.

Nên kết hợp I/O event với CPU samples, thread states, lock events, GC events và application metrics để hiểu toàn bộ đường xử lý.

## 2. Bốn event I/O quan trọng

JFR JDK 24 định nghĩa bốn event chuẩn trong nhóm Java Application:

| Event | Ý nghĩa | Thông tin nổi bật |
|---|---|---|
| jdk.FileRead | Đọc dữ liệu từ file | Path, bytesRead, endOfFile |
| jdk.FileWrite | Ghi dữ liệu vào file | Path, bytesWritten |
| jdk.SocketRead | Đọc dữ liệu từ socket | Host, address, port, timeout, bytesRead, endOfStream |
| jdk.SocketWrite | Ghi dữ liệu vào socket | Host, address, port, bytesWritten |

Các event đều có start time, duration, event thread và stack trace theo metadata JFR. Stack trace được ghi khi cấu hình event cho phép.

### jdk.FileRead

Ghi thao tác đọc dữ liệu từ file. Các trường quan trọng:

- **startTime:** thời điểm bắt đầu thao tác.
- **duration:** thời gian thao tác kéo dài.
- **eventThread:** thread thực hiện thao tác.
- **stackTrace:** call stack tại vị trí event được ghi, nếu bật.
- **path:** đường dẫn đầy đủ của file; có thể là N/A nếu stream được tạo từ file descriptor như System.in.
- **bytesRead:** số byte đọc được, có thể bằng 0.
- **endOfFile:** cho biết đã chạm cuối file hay chưa.

Nếu một file có nhiều lần đọc chậm, hãy nhóm theo path, kiểm tra bytesRead và xem stack trace để xác định caller.

### jdk.FileWrite

Ghi thao tác ghi dữ liệu vào file:

- **path:** đường dẫn file; có thể là N/A với stream dựa trên file descriptor như System.out hoặc System.err.
- **bytesWritten:** số byte được ghi.
- **duration:** thời gian của thao tác ghi.
- **eventThread** và **stackTrace:** ngữ cảnh thread/call stack.

FileWrite không chứng minh dữ liệu đã được ghi bền vững xuống thiết bị lưu trữ. Dữ liệu có thể vẫn nằm trong buffer của hệ điều hành hoặc filesystem cache. Nếu ứng dụng cần force cập nhật xuống storage, hãy xem thêm event **jdk.FileForce** hoặc các thao tác FileChannel.force().

### jdk.SocketRead

Ghi thao tác đọc dữ liệu từ socket:

- **host:** remote hostname.
- **address:** remote IP address.
- **port:** remote port.
- **timeout:** giá trị socket read timeout tính bằng milliseconds.
- **bytesRead:** số byte đọc được.
- **endOfStream:** cho biết đã gặp end-of-stream hay chưa.
- **duration**, **eventThread** và **stackTrace:** thời gian và ngữ cảnh gọi.

Một SocketRead kéo dài có thể phản ánh thread đang chờ dữ liệu, network delay, remote peer gửi chậm hoặc giao thức ứng dụng chờ đủ dữ liệu. Cần đối chiếu với timeout, bytesRead, host/port, stack trace và log của service từ xa.

### jdk.SocketWrite

Ghi thao tác ghi dữ liệu vào socket:

- **host**, **address**, **port:** endpoint từ xa.
- **bytesWritten:** số byte ghi vào socket.
- **duration:** thời gian của thao tác ghi tại JVM.
- **eventThread** và **stackTrace:** ngữ cảnh thực thi.

SocketWrite hoàn tất nhanh không chứng minh peer đã nhận hoặc xử lý dữ liệu. Lệnh write có thể chỉ chuyển bytes vào buffer của kernel rồi trả về. Muốn đo thời gian peer xử lý hoặc round-trip latency, cần correlation ID, protocol timing, tracing hoặc telemetry ở hai đầu kết nối.

## 3. Event duration và threshold

I/O event là duration event. JFR thường chỉ lưu những event có duration đạt ngưỡng được cấu hình.

Trong help của JFR.start trên OpenJDK 24.0.2 đã kiểm tra:

| JFR template | File I/O threshold | Socket I/O threshold |
|---|---:|---:|
| default.jfc | 20 ms | 20 ms |
| profile.jfc | 10 ms | 10 ms |

Giá trị thực tế có thể khác khi dùng custom .jfc hoặc thay đổi event settings. Hãy kiểm tra đúng template và cấu hình của recording.

### Vì sao event ngắn có thể không xuất hiện?

Giả sử ứng dụng thực hiện 10.000 lần đọc file, mỗi lần chỉ kéo dài 0,2 ms. Với threshold 10 ms, các thao tác này có thể không được ghi lại. Recording có thể không chứa event FileRead dù ứng dụng vẫn đọc file rất nhiều.

Vì vậy:

- Không thấy event không có nghĩa là không có I/O.
- Tổng bytes trong recording có thể thấp hơn tổng bytes thực tế.
- Số event không nhất thiết là tổng số lần gọi read/write.
- Các event còn lại bị thiên lệch về thao tác chậm hơn threshold.
- Không dùng số lượng event đã ghi để tính throughput đầy đủ nếu threshold đang loại bỏ thao tác ngắn.

### Giảm threshold cho điều tra

Có thể đặt threshold thấp hơn khi cần bắt nhiều thao tác:

~~~bash
jcmd <pid> JFR.start name=io-detail settings=profile duration=20s filename=io-detail.jfr jdk.FileRead#threshold=1ms jdk.FileWrite#threshold=1ms jdk.SocketRead#threshold=1ms jdk.SocketWrite#threshold=1ms
~~~

Ví dụ trên yêu cầu threshold 1 ms cho bốn event trong recording. Cần xác nhận syntax và event support của JDK mục tiêu.

Để ghi mọi duration, có thể đặt threshold 0 ms:

~~~bash
jcmd <pid> JFR.start name=io-all settings=profile duration=10s filename=io-all.jfr jdk.FileRead#threshold=0ms jdk.FileWrite#threshold=0ms jdk.SocketRead#threshold=0ms jdk.SocketWrite#threshold=0ms
~~~

Threshold 0 ms có thể tạo rất nhiều event, làm recording lớn hơn và tăng overhead. Chỉ dùng trong khoảng thời gian ngắn và khi đã đánh giá tác động.

### Tạo custom JFC

Có thể tạo cấu hình riêng dựa trên profile:

~~~bash
jfr configure --input profile.jfc jdk.FileRead#threshold=2ms jdk.FileWrite#threshold=2ms jdk.SocketRead#threshold=2ms jdk.SocketWrite#threshold=2ms --output io-detail.jfc
~~~

Sau đó dùng cấu hình:

~~~bash
jcmd <pid> JFR.start name=io-detail settings=io-detail.jfc duration=30s filename=io-detail.jfr
~~~

JVM mục tiêu phải truy cập được file io-detail.jfc. Nếu file không nằm trong thư mục JFR mặc định, dùng đường dẫn phù hợp trên máy chạy JVM.

## 4. Bắt đầu recording I/O bằng jcmd

Trước tiên xác định đúng JVM:

~~~bash
jcmd -l
~~~

Hoặc:

~~~bash
jps -l
~~~

Xác minh PID bằng công cụ hệ điều hành và đảm bảo đang thao tác đúng host, container và user.

Bắt đầu recording profile trong 30 giây:

~~~bash
jcmd <pid> JFR.start name=io-investigation settings=profile duration=30s filename=io-investigation.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

JFR.start có impact phụ thuộc settings; trên JDK 24, command được mô tả là Medium với mức tác động thay đổi từ thấp đến cao theo cấu hình. Profile thu thập nhiều dữ liệu hơn default và có overhead lớn hơn. Đối với production, hãy chọn thời lượng ngắn, giới hạn dung lượng và theo dõi ứng dụng trong lúc ghi.

### Default và profile

| Template | Đặc điểm | Cách dùng |
|---|---|---|
| default.jfc | Overhead thấp, phù hợp recording chạy liên tục | Theo dõi dài hạn hoặc continuous recording |
| profile.jfc | Thu thập nhiều dữ liệu hơn, bao gồm profiling chi tiết hơn | Điều tra ngắn khi cần thêm bằng chứng |

Nếu mục tiêu là I/O event, kiểm tra threshold của FileRead/FileWrite/SocketRead/SocketWrite trong template. Một recording profile vẫn có thể bỏ qua thao tác rất ngắn nếu threshold lớn hơn duration thực tế.

## 5. Phân tích I/O bằng jfr CLI

JDK 24 cung cấp các view tổng hợp I/O trong jfr CLI.

Xem summary:

~~~bash
jfr summary io-investigation.jfr
~~~

### File reads theo path

~~~bash
jfr view file-reads-by-path io-investigation.jfr
~~~

View nhóm các thao tác đọc theo đường dẫn file. Dùng để tìm file có hoạt động đọc nổi bật.

### File writes theo path

~~~bash
jfr view file-writes-by-path io-investigation.jfr
~~~

View giúp nhận diện file được ghi nhiều hoặc có thời gian ghi đáng chú ý.

### Socket reads theo host

~~~bash
jfr view socket-reads-by-host io-investigation.jfr
~~~

Dùng để xem remote host nào liên quan đến socket read trong recording.

### Socket writes theo host

~~~bash
jfr view socket-writes-by-host io-investigation.jfr
~~~

Dùng để xem các host nhận dữ liệu từ ứng dụng.

### Độ trễ theo loại

~~~bash
jfr view latencies-by-type io-investigation.jfr
~~~

View tổng hợp latency theo loại event được hỗ trợ. Đây là điểm bắt đầu để so sánh các nhóm I/O; vẫn cần mở event chi tiết và stack trace để tìm caller.

Có thể tăng chiều rộng bảng:

~~~bash
jfr view --width 160 file-reads-by-path io-investigation.jfr
~~~

Tên view và dữ liệu hiển thị phụ thuộc phiên bản JDK. Trên JDK cũ không có jfr view, có thể dùng JMC hoặc jfr print.

### In event thô

Để xem từng FileRead/FileWrite:

~~~bash
jfr print --events jdk.FileRead,jdk.FileWrite io-investigation.jfr
~~~

Để xem từng SocketRead/SocketWrite:

~~~bash
jfr print --events jdk.SocketRead,jdk.SocketWrite io-investigation.jfr
~~~

Có thể lọc riêng một event:

~~~bash
jfr print --events jdk.SocketRead io-investigation.jfr
~~~

Event thô cho biết start time, duration, thread, stack trace và các trường metadata. Khi recording có nhiều event, output có thể rất dài; hãy lọc theo event cần phân tích.

## 6. Phân tích I/O trong JDK Mission Control

JDK Mission Control (JMC) cung cấp giao diện đồ họa để mở recording .jfr và phân tích I/O.

Quy trình:

1. Mở JMC.
2. Chọn Open File và mở recording.
3. Chờ JMC phân tích event.
4. Mở trang **I/O**.
5. Chọn File Reads, File Writes, Socket Reads hoặc Socket Writes.
6. Sắp xếp theo duration, bytes hoặc số lần xuất hiện nếu bảng hỗ trợ.
7. Chọn event để xem chi tiết.
8. Xem stack trace để tìm code tạo I/O.
9. Đối chiếu với thread, CPU, lock và application metrics.

JMC là công cụ riêng, không phải thành phần giao diện đi kèm mọi cài đặt JDK. Có thể dùng jfr CLI nếu không cài JMC.

### Cách đọc bảng File I/O

Tìm các file có:

- Nhiều thao tác read/write.
- Duration lớn.
- Tổng bytes lớn.
- Nhiều event từ cùng một stack trace.
- Đường dẫn trên network mount hoặc storage chậm.

Một file có nhiều event ngắn có thể phản ánh workload bình thường. Một file có ít event nhưng duration rất dài có thể gây request latency lớn.

### Cách đọc bảng Socket I/O

Tìm:

- Host có nhiều socket read/write.
- Remote port liên quan đến database, cache, API hoặc message broker.
- SocketRead duration cao.
- BytesRead thấp trong khi duration dài.
- SocketWrite duration cao hoặc số bytes lớn.
- Thread và stack trace gọi tới endpoint.

Nếu nhiều thread cùng chờ SocketRead tới một host, cần đối chiếu server-side latency và network metrics. Không thể chỉ từ phía client xác định chính xác remote application xử lý ở bước nào.

## 7. Diễn giải FileRead và FileWrite

### FileRead chậm

Có thể do:

- Storage latency cao.
- Network filesystem hoặc mount từ xa.
- Cache miss và phải đọc từ thiết bị lưu trữ.
- File lớn hoặc đọc nhiều vùng dữ liệu.
- Thread đang thực hiện I/O đồng bộ.
- Hệ thống đang chịu tải I/O cao.

Cần xem path, bytesRead, duration và stack trace. So sánh cùng file qua nhiều lần recording và đối chiếu OS disk metrics.

### FileWrite chậm

Có thể do:

- Storage hoặc filesystem bị nghẽn.
- Nhiều thread ghi đồng thời vào cùng volume.
- Ghi lượng dữ liệu lớn.
- Filesystem metadata operation tốn thời gian.
- Buffer hoặc flush behavior của ứng dụng.
- Antivirus, backup hoặc hoạt động hệ thống cạnh tranh I/O.

FileWrite đo thao tác ghi được instrument. Nó không nhất thiết là thời gian dữ liệu được persist hoàn toàn xuống media. Nếu ứng dụng gọi FileChannel.force() hoặc FileDescriptor.sync(), hãy xem thêm FileForce event và thời gian force.

### Nhiều bytes không đồng nghĩa chậm

Một lần ghi 10 MB hoàn tất trong 5 ms có thể có throughput tốt hơn một lần ghi 4 KB kéo dài 50 ms. Hãy xem cả duration và bytes.

Không cộng bytes từ recording đã dùng threshold rồi coi đó là tổng lượng I/O của ứng dụng; các thao tác ngắn có thể bị bỏ qua.

## 8. Diễn giải SocketRead và SocketWrite

### SocketRead duration cao

SocketRead có thể kéo dài khi thread đang chờ dữ liệu. Nguyên nhân có thể là:

- Remote service phản hồi chậm.
- Network congestion hoặc packet loss.
- Server gửi dữ liệu theo từng phần nhỏ.
- Protocol yêu cầu chờ thêm dữ liệu.
- Socket timeout được cấu hình quá dài.
- Ứng dụng đọc theo blocking I/O và không có dữ liệu sẵn.

Kiểm tra host, address, port, timeout, bytesRead, endOfStream và stack trace. So sánh với server-side trace để biết thời gian nằm ở client, network hay server.

### SocketWrite duration cao

Có thể liên quan đến:

- Socket send buffer đầy.
- Network backpressure.
- Peer đọc dữ liệu chậm.
- Gửi payload lớn.
- Congestion hoặc network path không ổn định.

Tuy nhiên, SocketWrite duration thấp không chứng minh peer đã nhận hoặc xử lý dữ liệu. Kernel có thể nhận bytes vào buffer rồi trả về ngay.

### Phân biệt read timeout và end-of-stream

SocketRead có trường timeout và endOfStream. Đây là hai khái niệm khác nhau:

- **timeout:** giới hạn thời gian chờ được cấu hình cho thao tác đọc.
- **endOfStream:** peer đã đóng output hoặc không còn dữ liệu để đọc.

Nếu ứng dụng nhận EOF, cần kiểm tra lifecycle kết nối và protocol. Nếu read timeout xảy ra, hãy đối chiếu với socket configuration và exception logs.

## 9. Event duration không phải end-to-end request latency

Đây là giới hạn quan trọng nhất khi phân tích I/O event.

Ví dụ một request gọi API từ xa:

~~~text
Client request
  -> Serialize request
  -> SocketWrite
  -> Network
  -> Remote service processes request
  -> Network response
  -> SocketRead
  -> Deserialize response
  -> Client response
~~~

SocketWrite chỉ đo thao tác ghi socket được instrument. SocketRead đo thao tác đọc socket được instrument. Tổng thời gian request còn bao gồm serialization, network transit, remote processing, queueing, retries và các bước khác.

Tương tự, FileRead/FileWrite không đo toàn bộ thời gian xử lý nghiệp vụ quanh thao tác file.

Muốn đo end-to-end latency, dùng distributed tracing hoặc application-level timing với correlation ID. JFR I/O event giúp xác định thành phần I/O nào đáng điều tra, không thay thế trace toàn request.

## 10. Blocking, non-blocking và asynchronous I/O

Các event I/O chuẩn được ghi ở những điểm JDK instrument thao tác đọc/ghi. Cách diễn giải phụ thuộc API và implementation.

### Blocking I/O

Trong blocking read, thread có thể chờ cho đến khi có dữ liệu, EOF hoặc timeout. SocketRead duration có thể phản ánh khoảng thời gian thread ở trong thao tác đọc đó.

### Non-blocking I/O

Với NIO non-blocking, thao tác read/write có thể trả về ngay với số bytes bằng 0 hoặc một lượng dữ liệu nhỏ. Một event ngắn không cho biết toàn bộ thời gian chờ selector hoặc thời gian chờ logic của request.

### Asynchronous I/O

Với asynchronous channel hoặc framework event-driven, thao tác có thể được hoàn tất trên thread khác hoặc callback. Stack trace và event thread có thể phản ánh điểm I/O được instrument, không nhất thiết là thread khởi tạo request ban đầu.

### Memory-mapped và native I/O

Memory-mapped file access không tương đương từng lời gọi FileRead. Page fault và hoạt động storage có thể xảy ra ngoài event FileRead thông thường.

JNI, native libraries hoặc cơ chế I/O tự triển khai có thể không được biểu diễn đầy đủ bởi các event chuẩn. JFR I/O event không phải syscall trace toàn hệ điều hành.

Vì vậy, hãy kết hợp JFR với OS-level disk/network metrics và telemetry của framework khi phân tích ứng dụng dùng NIO, Netty, native transport hoặc memory-mapped file.

## 11. Ngưỡng và lọc event theo câu hỏi

Không nên đặt threshold bằng 0 ms cho mọi recording liên tục. Thay vào đó, bắt đầu với default/profile và giảm threshold khi cần.

Ví dụ chỉ hạ ngưỡng cho socket read:

~~~bash
jcmd <pid> JFR.start name=socket-detail settings=profile duration=15s filename=socket-detail.jfr jdk.SocketRead#threshold=2ms
~~~

Chỉ hạ ngưỡng cho file read/write:

~~~bash
jcmd <pid> JFR.start name=file-detail settings=profile duration=15s filename=file-detail.jfr jdk.FileRead#threshold=2ms jdk.FileWrite#threshold=2ms
~~~

Có thể bật stack trace nếu event setting hiện tại chưa bật:

~~~bash
jcmd <pid> JFR.start name=io-stacks settings=profile duration=15s filename=io-stacks.jfr jdk.FileRead#stackTrace=true jdk.FileWrite#stackTrace=true jdk.SocketRead#stackTrace=true jdk.SocketWrite#stackTrace=true
~~~

Việc bật stack trace làm recording hữu ích hơn để tìm caller nhưng có thể tăng overhead và dung lượng. Hãy chỉ thu thập trong khoảng cần thiết.

## 12. Lab Java 17+: tạo File I/O và Socket I/O

Lab sau tạo một file tạm, lặp lại thao tác ghi/đọc file và gửi dữ liệu qua socket loopback. Server thread đọc dữ liệu và chờ giữa các lần gửi để tạo SocketRead có duration đủ dài cho recording.

Tạo file **IoEventsDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

public final class IoEventsDemo {
    public static void main(String[] args) throws Exception {
        int seconds = args.length == 0
                ? 20
                : Integer.parseInt(args[0]);

        if (seconds <= 0) {
            throw new IllegalArgumentException(
                    "seconds must be positive");
        }

        Path file = Files.createTempFile("jfr-io-demo-", ".bin");
        byte[] payload = new byte[16 * 1024];
        Arrays.fill(payload, (byte) 0x5A);

        AtomicReference<IOException> receiverFailure =
                new AtomicReference<>();

        try (ServerSocket server = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {

            Thread receiver = new Thread(() -> {
                try (Socket accepted = server.accept()) {
                    InputStream input = accepted.getInputStream();
                    byte[] buffer = new byte[8192];

                    while (input.read(buffer) != -1) {
                        // Consume the received bytes.
                    }
                } catch (IOException ex) {
                    receiverFailure.set(ex);
                }
            }, "io-demo-receiver");

            receiver.start();

            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(),
                    server.getLocalPort())) {

                OutputStream socketOutput =
                        client.getOutputStream();

                System.out.println("READY");

                long deadline = System.nanoTime()
                        + seconds * 1_000_000_000L;

                while (System.nanoTime() < deadline) {
                    try (OutputStream output =
                            Files.newOutputStream(file)) {
                        output.write(payload);
                    }

                    try (InputStream input =
                            Files.newInputStream(file)) {
                        byte[] buffer = new byte[8192];

                        while (input.read(buffer) != -1) {
                            // Consume the file bytes.
                        }
                    }

                    Thread.sleep(30);
                    socketOutput.write(payload);
                    socketOutput.flush();
                }

                client.shutdownOutput();
            }

            receiver.join();
        } finally {
            Files.deleteIfExists(file);
        }

        if (receiverFailure.get() != null) {
            throw receiverFailure.get();
        }

        System.out.println("DONE");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 IoEventsDemo.java
~~~

Chạy chương trình trong terminal thứ nhất:

~~~bash
java IoEventsDemo 20
~~~

Stdout chính xác:

~~~text
READY
DONE
~~~

READY xuất hiện ngay trước vòng lặp I/O. DONE xuất hiện sau khi chương trình hoàn thành thời lượng được truyền vào. Đường dẫn file tạm được JVM tạo tự động và xóa khi chương trình kết thúc.

### Bắt đầu recording từ terminal thứ hai

Tìm PID:

~~~bash
jps -l
~~~

Tìm dòng IoEventsDemo, rồi bắt đầu recording 10 giây với threshold 0 ms:

~~~bash
jcmd <pid> JFR.start name=io-lab settings=profile duration=10s filename=io-lab.jfr jdk.FileRead#threshold=0ms jdk.FileWrite#threshold=0ms jdk.SocketRead#threshold=0ms jdk.SocketWrite#threshold=0ms
~~~

Kiểm tra:

~~~bash
jcmd <pid> JFR.check
~~~

Sau khi recording kết thúc:

~~~bash
jfr summary io-lab.jfr
~~~

Xem các view:

~~~bash
jfr view file-reads-by-path io-lab.jfr
jfr view file-writes-by-path io-lab.jfr
jfr view socket-reads-by-host io-lab.jfr
jfr view socket-writes-by-host io-lab.jfr
jfr view latencies-by-type io-lab.jfr
~~~

In event chi tiết:

~~~bash
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite io-lab.jfr
~~~

Kết quả có thể khác nhau theo JDK, hệ điều hành, filesystem và network stack. SocketRead thường có duration lớn hơn vì receiver thread chờ 30 ms trước khi client gửi dữ liệu. FileRead/FileWrite và SocketWrite có thể rất ngắn; threshold 0 ms giúp tăng khả năng ghi nhận chúng.

Nếu không thấy event, kiểm tra event có được bật trong recording settings, threshold, PID, quyền attach và JDK version. Không coi số event thực tế là cố định vì runtime có thể thực hiện thêm các thao tác I/O khác.

## 13. Đọc kết quả lab

### File events

Tìm path chứa prefix jfr-io-demo. Các event FileWrite và FileRead cho biết số bytes và thời gian thao tác.

Nếu nhiều event có duration rất thấp, điều đó cho thấy file operation hoàn tất nhanh trong môi trường local hiện tại. Không suy ra production storage sẽ có cùng latency.

### Socket events

Tìm host loopback và port được cấp động cho ServerSocket. SocketRead ở receiver thread có thể có duration xấp xỉ thời gian chờ giữa các lần client gửi.

Port và address thay đổi theo lần chạy. Không dùng số port trong ví dụ làm giá trị cố định.

### Stack trace

Mở event và xem stack trace. Với lab, call path sẽ dẫn tới các thao tác FileInputStream/FileOutputStream hoặc Socket input/output. Stack trace có thể khác theo JDK implementation và cách thư viện triển khai I/O.

## 14. Kết hợp I/O event với các nguồn dữ liệu khác

I/O event cho biết thao tác nào chậm; các nguồn dữ liệu khác giúp giải thích vì sao.

| Dữ liệu bổ sung | Câu hỏi cần trả lời |
|---|---|
| JFR CPU samples | Thread có đang tiêu thụ CPU hay chủ yếu chờ I/O? |
| Thread states | Thread đang RUNNABLE, WAITING hay BLOCKED? |
| GC events | Pause hoặc allocation pressure có trùng thời điểm I/O chậm không? |
| Lock events | Thread có bị lock contention trước khi gọi I/O không? |
| Application tracing | Request nào tương ứng với thao tác I/O? |
| Server-side tracing | Remote service xử lý request mất bao lâu? |
| OS disk metrics | Storage latency, queue depth và throughput thế nào? |
| OS network metrics | Retransmission, congestion và interface throughput ra sao? |
| Container metrics | CPU throttling, disk quota hoặc network policy có ảnh hưởng không? |

### Ví dụ phân tích API chậm

Giả sử SocketRead tới db.internal:5432 có duration cao.

1. Kiểm tra event thread và stack trace để xác định call site.
2. Xem timeout và bytesRead.
3. Đối chiếu cùng thời điểm với database server metrics.
4. Dùng distributed trace để xác định thời gian query trên server.
5. Kiểm tra network latency và connection pool.
6. Xác định vấn đề là client wait, network, server processing hay queueing.

Không tăng socket timeout hoặc retry count chỉ để che dấu độ trễ. Trước tiên phải xác định nguyên nhân và tác động tới request concurrency.

## 15. Lỗi thường gặp khi phân tích I/O event

### Không thấy FileRead hoặc FileWrite

Có thể thao tác ngắn hơn threshold, event bị disable, file access đi qua native/memory-mapped path hoặc recording không bao phủ thời điểm I/O. Kiểm tra event settings và hạ threshold trong recording ngắn.

### Không thấy SocketRead

Có thể socket read rất ngắn, non-blocking read trả về ngay, event dưới threshold hoặc code dùng native/async path khác. Kiểm tra SocketRead event settings và stack trace.

### SocketRead duration cao nhưng remote server log không chậm

Client có thể đang chờ dữ liệu được gửi theo từng phần, network delay hoặc protocol framing. So sánh timestamp hai đầu và xem bytesRead/endOfStream.

### SocketWrite duration thấp nhưng request vẫn chậm

Write có thể chỉ chuyển bytes vào kernel buffer. Remote processing và response read nằm ở giai đoạn sau. Dùng trace end-to-end và server-side metrics.

### FileWrite nhanh nhưng dữ liệu persist chậm

FileWrite không bảo đảm dữ liệu đã được force xuống storage. Kiểm tra FileForce event, FileChannel.force(), filesystem và OS storage metrics.

### Recording không có stack trace

Event setting có thể chưa bật stackTrace hoặc event không được cấu hình thu thập stack. Bật stackTrace cho event cần thiết trong recording ngắn và đo overhead.

### JFR recording quá lớn

Giảm duration, tăng threshold, chỉ bật event cần thiết hoặc dùng maxsize/maxage. Không bật threshold 0 ms liên tục nếu chưa đánh giá event volume.

### Không kết nối được jcmd

Xác minh PID, host, user/group, container namespace và quyền attach. jcmd phải chạy trên cùng máy với JVM mục tiêu và có quyền phù hợp.

## 16. Bảo mật và quyền riêng tư của I/O recording

I/O event chuẩn không ghi payload file hoặc dữ liệu socket, nhưng metadata vẫn nhạy cảm:

- Full file paths có thể tiết lộ username, cấu trúc thư mục và tên khách hàng.
- Hostname, IP và port có thể tiết lộ topology nội bộ.
- Stack trace có thể tiết lộ package, class và đường dẫn triển khai.
- Thread names có thể chứa tên service hoặc tenant.
- JFR recording còn có thể chứa system properties, JVM flags và các event khác tùy settings.

Vì vậy:

- Lưu file .jfr ở thư mục có quyền truy cập hạn chế.
- Dùng encryption và retention policy phù hợp.
- Không gửi recording qua kênh công khai.
- Redact hostname, path và thông tin nhạy cảm trước khi chia sẻ.
- Không commit recording vào Git.
- Ghi lại người thu thập, thời điểm, host, PID và mục đích.
- Xóa recording khi hết thời hạn điều tra.

## 17. Quy trình điều tra I/O bottleneck

1. Xác định service, host, JVM PID và workload gặp vấn đề.
2. Ghi nhận JDK version, JVM flags và thời điểm sự cố.
3. Bắt đầu JFR recording với default hoặc profile settings.
4. Nếu cần, giảm threshold cho đúng event I/O.
5. Dùng file-reads-by-path, file-writes-by-path, socket-reads-by-host và socket-writes-by-host để tìm nhóm nổi bật.
6. Mở event chi tiết, xem duration, bytes, thread và stack trace.
7. Phân biệt thời gian local I/O với request end-to-end latency.
8. Đối chiếu CPU, GC, lock, OS disk/network và remote service metrics.
9. Đưa ra giả thuyết có thể kiểm chứng.
10. Thay đổi một yếu tố và chạy lại workload tương đương.
11. So sánh duration, throughput, bytes, request latency và error rate.
12. Lưu recording và báo cáo theo retention policy.

## 18. Checklist I/O event

- Xác nhận đúng JVM, PID, host và user.
- Kiểm tra bốn event FileRead, FileWrite, SocketRead, SocketWrite.
- Kiểm tra threshold trong default/profile/custom settings.
- Nhớ thao tác ngắn hơn threshold có thể không được ghi.
- Xem duration, bytes, path hoặc host/port.
- Xem event thread và stack trace.
- Phân biệt FileWrite với FileForce.
- Phân biệt SocketWrite với remote acknowledgement.
- Không coi SocketRead duration là end-to-end request latency.
- Kiểm tra blocking, non-blocking và asynchronous behavior.
- Dùng JMC I/O page hoặc jfr CLI views.
- Dùng jfr print để xem event thô.
- Kết hợp OS metrics, distributed tracing và server-side logs.
- Hạ threshold chỉ trong thời gian cần thiết.
- Bảo vệ path, host và recording metadata.
- Đo lại sau tối ưu bằng workload tương đương.

## 19. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| I/O event | Sự kiện ghi nhận thao tác input/output |
| JFR | Java Flight Recorder, framework ghi runtime events |
| jdk.FileRead | Event đọc dữ liệu từ file |
| jdk.FileWrite | Event ghi dữ liệu vào file |
| jdk.SocketRead | Event đọc dữ liệu từ socket |
| jdk.SocketWrite | Event ghi dữ liệu vào socket |
| jdk.FileForce | Event force cập nhật file xuống storage |
| Duration | Thời gian một thao tác event kéo dài |
| Threshold | Ngưỡng duration để event được ghi |
| Stack trace | Chuỗi method call dẫn tới thao tác |
| Blocking I/O | Thao tác có thể chờ cho đến khi hoàn tất hoặc timeout |
| Non-blocking I/O | Thao tác có thể trả về ngay dù chưa có dữ liệu |
| Asynchronous I/O | I/O hoàn tất bất đồng bộ qua callback/future |
| Backpressure | Tình trạng phía nhận hoặc network không theo kịp tốc độ gửi |
| End-of-stream | Không còn dữ liệu để đọc từ stream |
| JMC | JDK Mission Control, công cụ phân tích JFR |
| JFC | Cấu hình recording JFR |
| Distributed tracing | Theo dõi một request qua nhiều service |
| Loopback | Kết nối mạng quay về chính máy hiện tại |

I/O event trong JFR giúp xác định file, endpoint, thread và call path liên quan đến thao tác I/O chậm. Hãy kiểm tra threshold trước khi diễn giải số liệu, phân biệt duration của thao tác với latency end-to-end, rồi kết hợp JFR với tracing và OS metrics để tìm nguyên nhân thực sự.

## Tài liệu tham khảo

- Oracle JDK 24 — [Java Flight Recorder](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- Oracle JDK 24 — [Troubleshooting Guide: Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- Oracle — [JDK Mission Control](https://docs.oracle.com/en/java/java-components/jdk-mission-control/index.html)