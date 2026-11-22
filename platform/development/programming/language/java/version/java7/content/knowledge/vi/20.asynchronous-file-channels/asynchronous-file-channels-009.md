# Đo lợi ích theo kiểu tải thay vì giả định bất đồng bộ luôn nhanh hơn

## 1. Bài toán và thông điệp chính

Trong Java, lập trình viên có thể đọc/ghi tệp bằng **`FileChannel`** hoặc **`AsynchronousFileChannel`**. Khi nhìn thấy chữ *asynchronous*, một suy đoán rất dễ xuất hiện:

> “Đọc/ghi bất đồng bộ chắc chắn nhanh hơn đọc/ghi đồng bộ.”

Suy đoán đó **không đúng như một quy tắc tổng quát**.

Bất đồng bộ chủ yếu thay đổi **cách ứng dụng khởi tạo thao tác và nhận kết quả**, từ đó có thể chồng lấp công việc, cho phép nhiều yêu cầu đang chờ I/O hoặc tránh chặn một thread điều phối. Điều này có thể tăng throughput hoặc giảm nhu cầu thread của một số workload, nhưng cũng có thể thêm chi phí `Future`, callback, thread pool, chuyển ngữ cảnh, quản lý buffer và điều phối hàng đợi.

Lợi ích thực tế phụ thuộc vào **kiểu tải (workload)**, nền tảng I/O, số yêu cầu đồng thời, kích cỡ block, mô hình thread, trạng thái file-system cache, độ dài hàng đợi và mục tiêu của ứng dụng. Một workload nhỏ đã được cache có thể cho kết quả **đồng bộ nhanh hơn**, trong khi workload I/O độ trễ cao, nhiều thao tác độc lập có thể hưởng lợi khi có đủ request đang outstanding.

Bài này thuộc phần **Kênh tệp bất đồng bộ** trong Java 7, tập trung vào phương pháp **đo, so sánh và quyết định kiến trúc**, không biến việc học API thành một tuyên bố tốc độ thiếu kiểm chứng.

Sau bài này, bạn có thể:

1. Phân biệt “API không bắt caller chờ” với “thao tác hoàn tất nhanh hơn”.
2. Chọn các kiểu tải đọc/ghi phản ánh sản phẩm thật, bao gồm tuần tự, ngẫu nhiên và nhiều request đồng thời.
3. Xác định đúng **latency, throughput, IOPS, độ sâu hàng đợi, CPU, bộ nhớ và p95/p99**.
4. Thiết kế phép so sánh công bằng giữa `FileChannel` và `AsynchronousFileChannel`.
5. Đọc kết quả mà không nhầm hiệu năng **cache/JIT/test harness** với hiệu năng thiết bị lưu trữ.
6. Chạy một chương trình **Java 17+** kiểm chứng correctness và đo nhiều cấu hình.
7. Nhận diện trường hợp nên dùng async, trường hợp sync đơn giản hơn và trường hợp cần đo thêm.
8. Thiết kế thí nghiệm production-like trước khi quyết định chuyển một hệ thống từ sync sang async.

**Nguyên tắc xuyên suốt:** Không chọn `AsynchronousFileChannel` chỉ vì tên của nó. Trước tiên hãy nói rõ “tải nào, kích cỡ nào, concurrency bao nhiêu, giới hạn CPU nào, SLA nào, lưu trữ nào”; sau đó đo **cùng một công việc** và kiểm chứng kết quả.

## 2. API đồng bộ và bất đồng bộ thực sự khác nhau ở đâu?

### 2.1. `FileChannel`: caller chờ cho tới khi lời gọi read hoàn tất

Một lệnh đọc vị trí tuyệt đối:

```java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("data.bin");

try (FileChannel channel =
        FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);
    int bytesRead = channel.read(buffer, 0L);
    System.out.println(bytesRead);
}
```

Đây là **đoạn minh họa trong phương thức có xử lý `IOException`**; tệp phải tồn tại, độ dài thực tế có thể nhỏ hơn 4096 và `bytesRead` có thể là `-1` ở EOF. `FileChannel.read(buffer,position)` có thể **chặn thread đang gọi** trong lúc đọc. Đổi lại, luồng điều khiển thường đơn giản.

`FileChannel` cũng có I/O tại **vị trí tuyệt đối** nên phép so sánh không nên gắn nhãn sai rằng sync bắt buộc phải thay đổi con trỏ file dùng chung. API `read(dst,position)` không cập nhật current position của channel.

### 2.2. `AsynchronousFileChannel`: khởi tạo I/O và nhận kết quả sau

Mẫu dùng `Future<Integer>`:

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

Path path = Path.of("data.bin");

try (AsynchronousFileChannel channel =
        AsynchronousFileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);
    Future<Integer> pending = channel.read(buffer, 0L);

    // Thread có thể làm việc KHÔNG phụ thuộc buffer ở đây.
    int bytesRead = pending.get();
    System.out.println(bytesRead);
}
```

Đây là **đoạn minh họa trong phương thức xử lý `IOException`, `InterruptedException` và `ExecutionException`**, cùng các lỗi khởi tạo I/O có thể phát sinh. `channel.read(buffer,position)` **khởi tạo yêu cầu** và trả một `Future`; `pending.get()` có thể **chặn thread gọi cho tới khi hoàn tất**.

Nếu code gọi `future.get()` ngay sau **mọi** lần submit, nó thường không tạo được nhiều thao tác outstanding. Khi đó chỉ thêm tầng bất đồng bộ/cơ chế điều phối mà không tạo được khả năng chồng lấp công việc đáng kể.

### 2.3. Overload dùng `CompletionHandler`

```java
channel.read(buffer, position, requestId,
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer count, String id) {
                // Xử lý trạng thái hoàn tất; kiểm tra count và buffer.
            }

            @Override
            public void failed(Throwable failure, String id) {
                // Báo lỗi tới owner/caller theo cơ chế thread-safe.
            }
        });
```

Đây là **mã minh họa chưa chạy độc lập** vì `channel`, `buffer`, `position`, `requestId` và import `CompletionHandler` cần được khai báo trong ứng dụng. Completion handler nhận kết quả từ thread pool của async channel; không giả định callback chạy trên thread đã khởi tạo yêu cầu, cũng không giả định các callback hoàn tất đúng thứ tự submit.

### 2.4. “Async” không đồng nghĩa “native kernel non-blocking trên mọi OS”

Theo hợp đồng Java, `AsynchronousFileChannel` được liên kết với **thread pool** để xử lý event/dispatch completion. Các provider có thể triển khai bằng những cơ chế hệ điều hành khác nhau; API không hứa rằng mọi thao tác sẽ dùng một syscall bất đồng bộ thuần native hoặc không tiêu thụ thread ở tầng triển khai.

Do đó chi phí của:

- `Future`/`CompletionHandler`,
- đẩy việc vào thread pool,
- scheduling và context switching,
- quản lý callback,
- đồng bộ dữ liệu và ownership,
- giới hạn queue depth của provider,

có thể trở nên đáng kể khi file data đã ở trong page cache hoặc thao tác I/O rất nhỏ.

**Lợi ích của async là khả năng tổ chức concurrency và không chặn caller, không phải đảm bảo mỗi read mất ít nanosecond hơn.**

## 3. Trước khi benchmark: xác định câu hỏi cần trả lời

Không bắt đầu bằng “API nào nhanh hơn?”. Hãy thay bằng một mục tiêu có thể đo:

- “Đọc 4 KiB từ hàng nghìn vị trí ngẫu nhiên trên ổ SSD khi có 32 yêu cầu đồng thời, throughput và p99 latency thay đổi thế nào?”
- “Worker hiện đang chờ `FileChannel.read` và không xử lý công việc khác; nếu chuyển sang async, tổng thời gian xử lý một batch thực tế có giảm không?”
- “Với tệp 1 GiB đọc tuần tự, liệu async pipelining có tăng tốc so với sync read bằng buffer 1 MiB?”
- “Nếu một thread service phải phục vụ nhiều phiên đọc, có thể giảm số thread bị block mà vẫn đạt SLA?”
- “Khi storage ở xa có độ trễ cao, mức `inFlight` nào tạo điểm cân bằng giữa throughput và p99?”
- “Nếu cần đọc có checksum/parse sau mỗi block, tính toán có thể chồng lấp I/O không, hay trở thành bottleneck mới?”

### 3.1. Xác định mục tiêu ưu tiên

| Mục tiêu | Cần đo | Điều không nên suy |
| --- | --- | --- |
| Tăng số request hoàn tất mỗi giây | Operations/s hoặc IOPS có correctness | Async luôn tăng throughput |
| Chuyển nhiều byte hơn | MiB/s hoặc GiB/s | Đọc nhanh từ page cache bằng tốc độ SSD thật |
| Giảm độ trễ người dùng | End-to-end p50/p95/p99 và timeout | Chỉ giảm thời gian `read` là đủ |
| Giảm thread bị block | Thread count, blocked time, scheduler activity | Ít thread đồng nghĩa ít CPU |
| Giữ CPU thấp | CPU time/%, context switches, GC | Async không dùng CPU |
| Bảo vệ bộ nhớ | Bounded queue, số buffer × bytes, allocation rate | Tăng `inFlight` vô hạn là tốt |
| Hoàn tất trước deadline | Deadline violations/error rate | Throughput cao luôn cải thiện p99 |
| Tính đúng đắn và độ bền | Byte count, checksum, lỗi/partial I/O, `force` nếu write | Benchmark nhanh nhưng sai byte là hợp lệ |

Một thiết kế tốt có thể chấp nhận throughput thấp hơn đôi chút để đổi lấy p99 tốt hơn và ít biến động. Cũng có ứng dụng batch chấp nhận latency từng tác vụ cao hơn để tối đa hóa tổng throughput. **Không có một metric tối ưu cho mọi trường hợp.**

## 4. Kiểu tải ảnh hưởng tới lợi ích của async như thế nào?

| Workload | Đặc điểm | Lý do cần đo riêng |
| --- | --- | --- |
| Đọc tuần tự một file lớn | Truy cập offset tăng dần, block tương đối lớn | Read-ahead/page cache có thể làm sync đơn giản đã rất hiệu quả |
| Đọc ngẫu nhiên block nhỏ | Mỗi request ở offset khác nhau | IOPS/queue depth quan trọng; nhiều outstanding có thể giúp một số storage |
| Rất nhiều file nhỏ | Open/close/metadata có thể chiếm chi phí lớn | Bottleneck có thể không nằm ở `read` |
| Nhiều file đọc độc lập | Có thể có nhiều request cùng lúc | Async giúp tổ chức concurrency nhưng sync worker pool cũng là baseline |
| Đọc rồi parse/giải nén | I/O xen kẽ CPU | Có thể chồng lấp công việc độc lập; CPU có thể trở thành nút thắt |
| Ghi tuần tự | Byte stream lớn, cache ghi của OS | Cần tách tốc độ accept write với durability thực sự |
| Ghi ngẫu nhiên, overwrite | Nhiều offset, có thể xung đột | Phải xử lý thứ tự/ownership, checksum, flush |
| Ổ đĩa cơ học | Seek latency cao khi random | Queue sâu có thể làm seek nhiều hơn, không đảm bảo nhanh |
| NVMe SSD | Hỗ trợ nhiều request outstanding | Có thể tận dụng concurrency nếu stack/provider/hardware hỗ trợ |
| Network filesystem | Độ trễ, cache và giới hạn mạng | Pool, số round trip, tail latency và contention trở nên quan trọng |
| Data nóng trong page cache | Hầu như không chờ thiết bị | Overhead async có thể chiếm tỷ trọng lớn |
| Data vượt RAM/cache | Nhiều đọc thật tới thiết bị | Kết quả khác hoàn toàn warm-cache |
| Phần lớn request nhỏ, thỉnh thoảng request lớn | Phân phối kích thước lệch | p99 và fairness có thể xấu đi khi queue sâu |

**Không lấy một workload duy nhất để thay mặt các workload khác.** Đo đọc ngẫu nhiên 4 KiB không đủ để kết luận cho sao lưu tuần tự 1 MiB; đo một file tạm 4 MiB đọc lặp nhiều lần càng không thay được benchmark cold-cache trên một tập dữ liệu lớn hơn RAM.

### 4.1. Độ sâu yêu cầu đang chờ — `inFlight`

Giả sử ứng dụng submit các phép đọc async độc lập:

```text
depth=1:
submit A -> wait A -> submit B -> wait B -> submit C -> wait C

depth=4:
submit A,B,C,D -> collect completions -> submit next batch
```

`depth=4` cho phép nhiều I/O cùng outstanding, nhưng cũng yêu cầu nhiều buffer độc lập và có thể tăng áp lực queue/thread pool. Nếu storage hoặc CPU đã bão hòa, tăng depth chỉ làm **thời gian chờ trong hàng đợi** và p99 tăng.

Cần kiểm tra các mức ví dụ `1, 2, 4, 8, 16, 32` trong giới hạn môi trường, không coi `32` mặc định tốt hơn `8`.

### 4.2. Không so serial sync với async depth=32 rồi kết luận “API nhanh hơn”

Nếu bên sync chạy một thread với một request tại một thời điểm, còn bên async có 32 request cùng lúc, phép thử đã thay đổi **cả API lẫn concurrency**. Khi thấy async throughput cao hơn, không thể tách riêng tác động của bất đồng bộ với tác động của nhiều request outstanding.

Cần có baseline thứ ba:

- **Sync serial:** một `FileChannel`, một worker.
- **Sync concurrent:** nhiều worker với `FileChannel.read(ByteBuffer,position)` hoặc một thiết kế sync có concurrency tương đương.
- **Async concurrent:** `AsynchronousFileChannel`, cùng số request đang chờ và cùng giới hạn tài nguyên.

Chỉ khi so cùng mức concurrency, cùng data và điều kiện tương đương mới có cơ sở nói về **chi phí/lợi ích API** ngoài yếu tố đồng thời.

## 5. Các metric quan trọng và công thức

### 5.1. Throughput theo byte

Nếu một batch đọc thành công `B` byte trong `T` giây:

\[
\text{Throughput (MiB/s)}=\frac{B}{1024^2 \times T}
\]

Dùng **MiB** (1 MiB = 1.048.576 byte) khi chia cho `1024²`; nếu báo `MB/s` theo hệ thập phân phải chia cho `1.000.000`. Không trộn hai đơn vị khi so.

Ví dụ 40 MiB trong 2 giây cho throughput **20 MiB/s**. Nhưng nếu 40 MiB được đọc từ cache, con số không phải thông số băng thông vật lý của ổ đĩa.

### 5.2. IOPS và operations/s

\[
\text{Operations/s}=\frac{\text{Số thao tác hoàn tất}}{\text{Thời gian đo (giây)}}
\]

Với tất cả thao tác đều là một read 4 KiB, operations/s gần với **IOPS ở tầng lời gọi ứng dụng**. Nhưng **không tự đồng nhất** với số I/O thật gửi tới SSD: page cache, read-ahead và provider có thể ghép/tách những yêu cầu.

Nếu một request logical gồm nhiều `read` do partial completion, cần quyết định đếm **request logical** hay **lần gọi read vật lý/API**, và dùng định nghĩa nhất quán.

### 5.3. Latency của một request

Ví dụ một request bắt đầu lúc `t0` và hoàn tất lúc `t1`:

\[
L=t_1-t_0
\]

Phải nói rõ **ranh giới**:

- **Submission-to-completion latency:** tính từ lúc ứng dụng submit `read` đến callback/`Future` hoàn tất.
- **Queue + I/O + validation latency:** tính từ lúc request đi vào hàng đợi ứng dụng đến khi byte được kiểm chứng và sẵn sàng cho bước tiếp theo.
- **End-to-end user latency:** từ lúc nhận tác vụ người dùng đến khi trả kết quả, bao gồm queue, I/O, CPU, serialization, network và các bước khác.

Một benchmark chỉ đo `Future.get()` **sau khi operation đã chạy được một lúc** có thể đo thiếu phần thời gian thao tác xảy ra trước `get()`. Dùng mốc bắt đầu nhất quán để đo toàn bộ latency.

### 5.4. p50, p95 và p99

Với `N` thời gian **của từng request**, sắp xếp chúng và tính các phân vị:

- **p50:** 50% request có latency không vượt quá mức gần phân vị này.
- **p95:** mức gần 95% request không vượt quá.
- **p99:** phản ánh vùng đuôi độ trễ, quan trọng khi có SLA chặt.

**Không lấy “median của năm thời gian chạy cả batch” rồi gọi đó là “p50 request latency”.** Hai đối tượng thống kê khác nhau: một bên là **run-level elapsed time**, một bên là **request-level latency distribution**.

Với số quan sát nhỏ, ước lượng p99 kém ổn định. Muốn đo p99 nghiêm túc phải có đủ request, workload lặp có kiểm soát và ghi nhận outliers/retries.

### 5.5. CPU, GC, thread và context switch

Thời gian wall-clock không đủ để hiểu chi phí:

- `ThreadMXBean`/profiler có thể giúp đo thời gian CPU theo thread khi hỗ trợ.
- JFR (Java Flight Recorder), GC logs, metrics OS có thể hỗ trợ quan sát allocation, GC pause, thread scheduling và file I/O theo khả năng nền tảng.
- Theo dõi **số thread sống**, thread bị block, pool queue, callback latency, contention và số buffer đang outstanding.
- Tăng throughput nhưng CPU tăng mạnh hoặc GC nhiều hơn có thể không đáng với một dịch vụ cần tài nguyên ổn định.

**Không báo “async ít CPU hơn” chỉ dựa vào số thread ứng dụng không phải đợi trong `Future.get()`**; chi phí có thể chuyển sang thread pool của provider.

### 5.6. Error rate và completeness

Một bài đo performance hợp lệ cần kiểm tra:

- Tổng số logical operation mong đợi = thực tế hoàn tất.
- Số byte đọc/ghi, EOF và partial completions được xử lý đúng.
- ByteBuffer không bị sửa hoặc tái sử dụng khi I/O còn outstanding.
- Dữ liệu nhận được đúng offset/byte, có checksum/validation phù hợp.
- Timeout, cancellation, interrupted wait và channel close được xử lý minh bạch.
- Không âm thầm bỏ request lỗi rồi báo throughput cao.

**Nhanh nhưng đọc sai dữ liệu không phải một chiến thắng hiệu năng.**

## 6. Queueing: vì sao concurrency có điểm bão hòa?

Hãy xem một hệ thống nơi mỗi I/O phải đi qua hàng đợi ứng dụng, thread pool của async provider, file-system cache và thiết bị lưu trữ.

Khi tải thấp, tăng số yêu cầu đồng thời có thể giúp **giữ thiết bị bận**. Nhưng khi số yêu cầu đến vượt năng lực hoàn tất ổn định, backlog tăng:

```text
incoming requests
       |
       v
bounded application queue
       |
       v
in-flight budget / semaphore
       |
       v
AsynchronousFileChannel + provider thread pool
       |
       v
OS/filesystem/cache/storage
       |
       v
completion -> validation -> response
```

Nếu ứng dụng tiếp tục submit không giới hạn khi thiết bị đã bão hòa:

- Throughput có thể **không tăng thêm**.
- p95/p99 thường có nguy cơ tăng do hàng đợi dài.
- Bộ nhớ tăng theo số buffer và Future/request state.
- Callback/worker pool có thể trở thành bottleneck.
- Timeout có thể tăng; việc hủy có thể tạo thêm chi phí.
- Việc đóng/shutdown mất nhiều công việc dở hơn.

### 6.1. Little's Law để định hướng, không dùng mù quáng

Trong một hệ thống ổn định, một quan hệ thường dùng là:

\[
L=\lambda W
\]

Ở đây `L` là số request trung bình trong hệ thống, `λ` là thông lượng request/giây và `W` là thời gian một request trung bình ở trong hệ thống.

Ví dụ nếu 500 request/giây và mỗi request trung bình sống 0,02 giây, mức concurrency trung bình xấp xỉ `10` request. Đây là **ước tính ở trạng thái ổn định**, không phải lời hứa rằng đặt queue depth=10 luôn tối ưu.

Nếu hệ thống có burst, backlog không ổn định, p99 lớn hoặc saturation, phải đo phân phối và chính sách backpressure thực tế. Không lấy trung bình để thay cho tail-latency SLA.

### 6.2. Bounded in-flight và buffer budget

Mỗi yêu cầu async sử dụng `ByteBuffer` riêng 64 KiB và ứng dụng cho phép 128 request outstanding thì **riêng dung lượng payload của các buffer đó** đã là 8 MiB, chưa kể Future, metadata, cache, pool và object bổ trợ. Nếu buffer lớn hơn hoặc request tăng không giới hạn, bộ nhớ có thể tăng rất nhanh.

Cần quản lý **buffer ownership**: chỉ tái sử dụng buffer sau khi request liên quan đã thực sự hoàn tất, không chỉ sau khi đã submit hoặc khi một waiter timeout.

## 7. Quy trình thiết kế benchmark công bằng

### 7.1. Ghi giả thuyết, đừng chỉ thu số

Một giả thuyết có thể kiểm chứng:

> Với 1.000 request đọc độc lập, block 4 KiB, dataset lớn hơn RAM và storage hỗ trợ nhiều request đồng thời, async depth=8 có thể cải thiện throughput so với sync serial; nhưng muốn quy công cho async phải so thêm sync concurrent depth=8.

Các từ **“có thể”**, “khi” và mô tả điều kiện có ý nghĩa thật: kết quả không được xác định trước.

### 7.2. Đảm bảo cùng một lượng công việc

Giữa các biến thể:

- Cùng nội dung file và cùng tổng byte.
- Cùng danh sách offset, thứ tự tuần tự/ngẫu nhiên theo seed cố định nếu đó là yếu tố muốn kiểm soát.
- Cùng kích cỡ block và cách xử lý partial read.
- Cùng kiểm chứng byte kết quả.
- Cùng mức concurrency ở nhóm so sánh “API với API”; nếu thay queue depth, hãy ghi rõ.
- Cùng trạng thái cache mong muốn (warm hoặc cold), cùng pool/resource lifecycle được chỉ định.
- Cùng dữ liệu đầu ra/logging (tốt nhất không in log trong vùng đo).
- Không thay đồng thời kích thước block, thuật toán checksum và số thread rồi quy toàn bộ khác biệt cho async.

### 7.3. Tách setup khỏi đoạn timing

Một microbenchmark chỉ định đo read nên **không tính** vào vùng đo:

- Tạo fixture và ghi file ban đầu.
- Tạo danh sách offset ngẫu nhiên.
- Đọc cấu hình môi trường hoặc khởi động JVM.
- In log từng request.
- Tạo một thư mục tạm mỗi lần đọc.
- Mở/đóng channel, **trừ khi lifecycle mở/đóng là đúng điều bạn cần đo**.

Nếu sản phẩm cần mở và đóng một file cho mỗi tác vụ, benchmark end-to-end **phải tính cả open/close**. Còn nếu sản phẩm giữ channel lâu dài, benchmark steady-state nên mở channel trước đoạn đo. Hai phép thử trả lời hai câu hỏi khác nhau.

### 7.4. JIT warmup và thứ tự chạy

Một lần chạy đầu có thể mang overhead class loading, JVM/JIT compilation và khởi tạo thread pool. Cần:

1. Warmup mỗi biến thể.
2. Chạy nhiều vòng đo sau warmup.
3. Hoán đổi hoặc xoay thứ tự các biến thể để hạn chế một mode luôn hưởng lợi từ cache/JIT ở cuối.
4. Công bố phân phối theo lần đo thay vì chọn một sample đẹp.
5. Khi cần đo microbenchmark nghiêm túc, cân nhắc JMH, fork JVM và cơ chế blackhole/kiểm soát tối ưu hóa thích hợp; **đọc/ghi file vẫn cần thận trọng với page cache và môi trường I/O**.

Trong ví dụ chạy được phía dưới, có warmup và **năm vòng đo**, xoay thứ tự ba mode. Đây là **demo phương pháp**, không phải một bộ suite kết luận hiệu năng production.

### 7.5. Caching: warm-cache và cold-cache là hai workload khác nhau

Nếu tạo file 4 MiB rồi liên tục đọc lại trong một JVM, rất có khả năng dữ liệu vẫn ở **OS page cache**. Lúc đó con số MiB/s của read có thể chủ yếu phản ánh:

- Copy từ cache và overhead API;
- Chi phí callback/Future/scheduler;
- Cache CPU và mức tối ưu của hệ điều hành;
- JIT/allocator và đo thời gian ngắn.

Điều đó **không sai** nếu sản phẩm cũng thường đọc dữ liệu nóng từ cache. Nhưng không dùng nó để công bố throughput ổ NVMe hay kết luận về dữ liệu lạnh từ network share.

Muốn đo cold-cache cần **định nghĩa và kiểm soát trạng thái dữ liệu** theo môi trường: dataset đủ lớn, phương pháp chuẩn bị, ảnh hưởng của file system và OS, cùng quyền thao tác. Không khuyến nghị xóa cache toàn hệ thống trên máy dùng chung chỉ để làm benchmark và không nói rằng tạo tên file mới đảm bảo 100% cold-cache.

### 7.6. Môi trường hệ thống phải được ghi lại

Tối thiểu ghi:

- Phiên bản JDK/build/vendor, OS và Java runtime options.
- Loại file system và storage thực tế (SSD/HDD/NAS/network mount).
- Kích cỡ fixture và tỷ lệ so với RAM/page cache.
- CPU cores, bộ nhớ, cgroup/VM/container nếu có.
- Mức tải ngoài/antivirus/indexing, công việc song song.
- Cách cấu hình thread pool, số worker, `inFlight` và buffer memory.
- Kiểu đọc/ghi, block size, offset distribution, dataset và seed.
- Số vòng warmup, số vòng đo, đo wall-clock hay CPU.
- Lỗi, timeout và tỷ lệ hoàn tất.

Không dùng số benchmark từ một laptop làm đặc tả performance cho production server nếu không có kiểm chứng trên môi trường đích.

## 8. Bộ kiểm thử Java 17+ — so sánh cùng dữ liệu, không hardcode kết luận

Ví dụ **`WorkloadDrivenIoBenchmark.java`** thực hiện:

1. Tạo một file tạm **4 MiB**, gồm **1.024 block × 4.096 byte**, chứa dấu kiểm tra theo chỉ số block.
2. Chuẩn bị hai kiểu tải: đọc **tuần tự** và đọc theo thứ tự **xáo trộn có seed cố định**.
3. Mở **`FileChannel`** và **`AsynchronousFileChannel`** trên cùng file ở chế độ READ.
4. So ba phương án: **sync serial**, **async depth=1**, **async depth=8**.
5. Với mỗi kiểu tải, chạy thử mỗi phương án một lần để warmup và kiểm tra correctness.
6. Chạy **5 vòng đo**, xoay thứ tự ba phương án.
7. Dùng `System.nanoTime()` để tính **elapsed time của toàn bộ batch đọc**, không dùng timestamp làm độ trễ một request riêng lẻ.
8. Kiểm tra các byte dấu hiệu ở đầu/giữa/cuối block và fingerprint tổng, cùng số byte đã đọc.
9. In **median của năm thời gian batch** theo millisecond; kết quả này **không phải p50 latency của từng request**.
10. Đóng cả hai channel và xóa file tạm.

Đây là **benchmark giáo dục nhỏ**: tốt để thấy kết quả có thể trái với khẩu hiệu “async luôn nhanh hơn”, nhưng không có đủ điều kiện để tuyên bố API nhanh hơn nói chung hoặc thiết bị lưu trữ đạt throughput được đo trên dataset đã cache.

### 8.1. Mã đầy đủ: `WorkloadDrivenIoBenchmark.java`

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class WorkloadDrivenIoBenchmark {
    private static final int BLOCK_BYTES = 4096;
    private static final int BLOCKS = 1024;
    private static final int DEPTH = 8;
    private static final int ROUNDS = 5;

    record Sample(long nanos, long bytes, long fingerprint) {}
    record Pending(int index, long offset,
                   ByteBuffer buffer, Future<Integer> future) {}

    private static void check(boolean ok, String description) {
        if (!ok) throw new AssertionError(description);
    }

    private static void createFixture(Path file) throws IOException {
        try (FileChannel ch = FileChannel.open(file, StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {
            ByteBuffer buffer = ByteBuffer.allocate(BLOCK_BYTES);
            for (int index = 0; index < BLOCKS; index++) {
                buffer.clear();
                for (int j = 0; j < BLOCK_BYTES; j++) {
                    buffer.put((byte) (index + j));
                }
                buffer.putInt(0, index);
                buffer.flip();
                long offset = (long) index * BLOCK_BYTES;
                while (buffer.hasRemaining()) {
                    int wrote = ch.write(buffer, offset + buffer.position());
                    if (wrote <= 0) {
                        throw new IOException("Could not populate fixture");
                    }
                }
            }
        }
    }

    private static int[] order(boolean random) {
        int[] indices = new int[BLOCKS];
        for (int i = 0; i < BLOCKS; i++) indices[i] = i;
        if (random) {
            Random generator = new Random(1_234_567L);
            for (int i = indices.length - 1; i > 0; i--) {
                int j = generator.nextInt(i + 1);
                int temp = indices[i];
                indices[i] = indices[j];
                indices[j] = temp;
            }
        }
        return indices;
    }

    private static long validateAndFingerprint(ByteBuffer data, int index) {
        check(data.remaining() == BLOCK_BYTES,
                "Incomplete block " + index);
        check(data.getInt(0) == index,
                "Wrong marker at " + index);
        check(data.get(4) == (byte) (index + 4),
                "Wrong sample at " + index);
        check(data.get(BLOCK_BYTES - 1) ==
                (byte) (index + BLOCK_BYTES - 1),
                "Wrong end marker at " + index);
        return (long) index * 1_000_003L
                + Byte.toUnsignedInt(data.get(4)) * 257L
                + Byte.toUnsignedInt(data.get(BLOCK_BYTES - 1));
    }

    private static long expectedFingerprint(int[] indices) {
        long sum = 0;
        for (int index : indices) {
            sum += (long) index * 1_000_003L
                    + Byte.toUnsignedInt((byte) (index + 4)) * 257L
                    + Byte.toUnsignedInt(
                            (byte) (index + BLOCK_BYTES - 1));
        }
        return sum;
    }

    private static Sample synchronous(FileChannel ch, int[] indices)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(BLOCK_BYTES);
        long fingerprint = 0;
        long begin = System.nanoTime();
        for (int index : indices) {
            buffer.clear();
            long offset = (long) index * BLOCK_BYTES;
            while (buffer.hasRemaining()) {
                int read = ch.read(buffer, offset + buffer.position());
                if (read <= 0) {
                    throw new IOException("Unexpected EOF/no progress");
                }
            }
            buffer.flip();
            fingerprint += validateAndFingerprint(buffer, index);
        }
        return new Sample(System.nanoTime() - begin,
                (long) indices.length * BLOCK_BYTES, fingerprint);
    }

    private static Sample asynchronous(
            AsynchronousFileChannel ch,
            int[] indices, int depth) throws Exception {
        ByteBuffer[] buffers = new ByteBuffer[depth];
        for (int i = 0; i < depth; i++) {
            buffers[i] = ByteBuffer.allocate(BLOCK_BYTES);
        }
        long fingerprint = 0;
        long begin = System.nanoTime();
        for (int base = 0; base < indices.length; base += depth) {
            List<Pending> pending = new ArrayList<>(depth);
            for (int slot = 0;
                 slot < depth && base + slot < indices.length;
                 slot++) {
                int index = indices[base + slot];
                ByteBuffer buffer = buffers[slot];
                buffer.clear();
                long offset = (long) index * BLOCK_BYTES;
                pending.add(new Pending(
                        index, offset, buffer, ch.read(buffer, offset)));
            }
            for (Pending request : pending) {
                int read = request.future().get(10, TimeUnit.SECONDS);
                if (read <= 0) {
                    throw new IOException("Unexpected EOF/no progress");
                }
                ByteBuffer buffer = request.buffer();
                while (buffer.hasRemaining()) {
                    Future<Integer> more = ch.read(
                            buffer, request.offset() + buffer.position());
                    int additional = more.get(10, TimeUnit.SECONDS);
                    if (additional <= 0) {
                        throw new IOException("Unexpected EOF/no progress");
                    }
                }
                buffer.flip();
                fingerprint += validateAndFingerprint(
                        buffer, request.index());
            }
        }
        return new Sample(System.nanoTime() - begin,
                (long) indices.length * BLOCK_BYTES, fingerprint);
    }

    private static void verify(
            Sample s, int[] indices, long expected) {
        check(s.bytes() ==
                (long) indices.length * BLOCK_BYTES, "byte count");
        check(s.fingerprint() == expected, "data fingerprint");
        check(s.nanos() > 0, "nonpositive elapsed time");
    }

    private static double medianMillis(long[] samples) {
        long[] ordered = samples.clone();
        Arrays.sort(ordered);
        return ordered[ordered.length / 2] / 1_000_000.0;
    }

    private static void runCase(
            String label, FileChannel sync,
            AsynchronousFileChannel async,
            int[] indices) throws Exception {
        long expected = expectedFingerprint(indices);

        verify(synchronous(sync, indices), indices, expected);
        verify(asynchronous(async, indices, 1), indices, expected);
        verify(asynchronous(async, indices, DEPTH), indices, expected);

        long[][] trials = new long[3][ROUNDS];
        for (int round = 0; round < ROUNDS; round++) {
            for (int turn = 0; turn < 3; turn++) {
                int mode = (round + turn) % 3;
                Sample s = switch (mode) {
                    case 0 -> synchronous(sync, indices);
                    case 1 -> asynchronous(async, indices, 1);
                    default -> asynchronous(async, indices, DEPTH);
                };
                verify(s, indices, expected);
                trials[mode][round] = s.nanos();
            }
        }

        System.out.println("workload = " + label
                + ", ops = " + indices.length
                + ", blockBytes = " + BLOCK_BYTES);
        System.out.printf(Locale.ROOT,
                "sync serial median = %.3f ms%n",
                medianMillis(trials[0]));
        System.out.printf(Locale.ROOT,
                "async depth=1 median = %.3f ms%n",
                medianMillis(trials[1]));
        System.out.printf(Locale.ROOT,
                "async depth=" + DEPTH + " median = %.3f ms%n",
                medianMillis(trials[2]));
        System.out.println("fingerprint verified = true");
    }

    public static void main(String[] args) throws Exception {
        Path fixture = Files.createTempFile(
                "java-async-workload-", ".bin");
        try {
            createFixture(fixture);
            check(Files.size(fixture) ==
                    (long) BLOCKS * BLOCK_BYTES, "fixture size");
            System.out.println("fixture bytes = "
                    + Files.size(fixture));
            try (FileChannel sync =
                         FileChannel.open(
                                 fixture, StandardOpenOption.READ);
                 AsynchronousFileChannel async =
                         AsynchronousFileChannel.open(
                                 fixture, StandardOpenOption.READ)) {
                runCase("sequential", sync, async, order(false));
                runCase("shuffled", sync, async, order(true));
            }
            System.out.println("checks = PASS");
        } finally {
            Files.deleteIfExists(fixture);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 WorkloadDrivenIoBenchmark.java
java WorkloadDrivenIoBenchmark
```

### 8.2. Kết quả một lần chạy thực tế trong môi trường kiểm thử

Bản dưới là **stdout một lần chạy thành công đã kiểm chứng trên Windows/JDK 17, file system mặc định**. Những số millisecond **không phải output cố định**: chúng sẽ khác khi đổi máy, tải CPU, file system, JDK và ngay cả giữa hai lần chạy trên cùng máy.

```text
fixture bytes = 4194304
workload = sequential, ops = 1024, blockBytes = 4096
sync serial median = 2.574 ms
async depth=1 median = 15.652 ms
async depth=8 median = 5.930 ms
fingerprint verified = true
workload = shuffled, ops = 1024, blockBytes = 4096
sync serial median = 2.849 ms
async depth=1 median = 14.933 ms
async depth=8 median = 5.888 ms
fingerprint verified = true
checks = PASS
cleanup = done
```

Kết quả **trong một lần chạy này**:

- Cả ba cấu hình đều vượt kiểm tra dữ liệu.
- Đọc đồng bộ serial có median batch time thấp nhất trong cả hai kiểu tải.
- Async depth=8 tốt hơn async depth=1, nhưng vẫn chậm hơn sync serial ở fixture **4 MiB** này.
- Không có căn cứ khẳng định đây là xếp hạng đúng trên NVMe dưới tải cao, network filesystem, ứng dụng có CPU work xen kẽ, hoặc dataset lớn hơn RAM.
- Không có căn cứ suy ra số MiB/s tính từ kết quả này là throughput vật lý của thiết bị; file nhỏ có thể đã nằm trong page cache.

**Đây chính là thông điệp của chủ đề:** không đo thì không biết phương án nào phù hợp; đo **một lần** và bỏ qua workload thực cũng vẫn chưa đủ để quyết định production.

### 8.3. Vì sao ba cấu hình này **chưa** chứng minh async chậm hơn sync nói chung?

Phép so được thiết kế để dạy phương pháp, nhưng có các giới hạn cố ý và cần nói rõ:

1. Dataset chỉ **4 MiB**, nhiều khả năng **warm-cache**.
2. `FileChannel` chạy **một thread**, async depth=8 có nhiều request outstanding; mức concurrency chưa tương đương.
3. Biến thể async dùng `Future.get` theo **thứ tự submit**, có thể bị *head-of-line blocking* nếu request sau hoàn tất trước request đầu.
4. Async depth=8 submit **theo từng batch**, chưa có một sliding window liên tục để lấp chỗ trống ngay khi có request hoàn tất.
5. Chưa đo p50/p99 **của từng I/O**, cũng chưa đo CPU time, GC, pool queue hay context switch.
6. Chưa có sync thread-pool baseline depth=8.
7. Chưa thay block size, dataset size, read/write ratio, số producer hoặc mức tải ngoài.
8. Một file tạm vừa tạo đã được ghi 4 MiB trước khi benchmark, khiến cache có lợi cho các lượt đọc.
9. Median chỉ gồm năm vòng; dữ liệu chưa đủ cho kết luận độ ổn định dài hạn.
10. Không benchmark quá trình **mở channel/đóng channel**, vì đây là bài đo read steady-state, không phải end-to-end request lifecycle.

Thử nghiệm vẫn hợp lệ để **kiểm tra mã chạy, quan sát chi phí tương đối trong fixture cụ thể và dạy cách đọc kết quả**. Để đưa ra quyết định kiến trúc, mở rộng nó theo ma trận thử nghiệm ở các phần sau.

### 8.4. Vì sao code kiểm tra partial reads?

Kể cả một read yêu cầu 4096 byte, kết quả có thể chuyển **ít hơn số byte còn trống**. Do đó cả sync và async đều kiểm tra `buffer.hasRemaining()` và tiếp tục đọc tại `offset + buffer.position()` cho đến đủ block hoặc gặp lỗi.

Với `AsynchronousFileChannel`, một `Future<Integer>` hoàn tất mới bảo đảm **lần đọc đó** đã kết thúc; nếu còn byte thiếu, code submit một read tiếp theo sau completion. Không dùng cùng `ByteBuffer` cho hai operation outstanding cùng lúc. Mỗi slot của batch có buffer riêng, được tái sử dụng **chỉ sau khi toàn bộ batch đã được chờ hoàn tất**.

### 8.5. Vì sao dùng `get(10, TimeUnit.SECONDS)`?

Timeout 10 giây là **giới hạn test cho mỗi Future read**, giúp demo không chờ mãi nếu provider/storage gặp sự cố. Nó không có nghĩa async sẽ tự cancel request khi hết 10 giây. Trong ứng dụng production, timeout phải đi kèm state machine, chính sách cancellation, quản lý buffer và cleanup; không bỏ qua operation có thể hoàn tất muộn.

### 8.6. Vì sao không dùng phép đo p99 từ chương trình này?

Code đo thời gian của **1024 block như một batch**, mỗi biến thể có **năm thời gian đo**. `medianMillis` là median của **năm batch durations**, không phải p50 request-level latency. Muốn p95/p99 của request, phải ghi timestamp cho **từng logical I/O** (bao gồm hàng đợi theo định nghĩa) và có nhiều observation hơn.

### 8.7. Kiểm tra fingerprint có đủ để bảo đảm toàn vẹn sản xuất?

Không. Code kiểm tra dấu `int` ở đầu block, một byte gần đầu, byte cuối và tổng fingerprint — đủ phát hiện nhiều lỗi offset/partial read trong fixture, nhưng **không phải cryptographic digest và không kiểm chứng mọi byte của mọi block**.

Với một hệ thống lưu trữ dữ liệu quan trọng, benchmark cần checksum mạnh hơn hoặc đối chiếu toàn bộ payload, cùng xác nhận byte count và semantic correctness. Không lấy sự thành công của fingerprint minh họa làm bằng chứng nội dung mọi byte không thể sai.

## 9. Thiết kế benchmark nâng cao: baseline đồng bộ nhiều worker

Nếu muốn tách tác động **API** khỏi tác động **concurrency**, phải có nhóm sync concurrent với cùng `inFlight`.

Một hướng thiết kế:

1. Khởi tạo một `ExecutorService` có đúng `N` worker.
2. Với mỗi index, submit một `Callable` đọc một block bằng positional `FileChannel.read(buffer,offset)`, bảo đảm mỗi task có `ByteBuffer` riêng hoặc pool buffer có ownership rõ.
3. Bounded submission: chỉ cho phép tối đa `N` hoặc một giới hạn tương đương đang outstanding.
4. Dùng `CompletionService`, `Future` hoặc cơ chế khác để thu kết quả và thay request đã hoàn tất bằng request mới.
5. Không ghi log trong vùng đo; checksum/validation tương đương.
6. Chạy song song nhóm async depth=`N` trên cùng offset list và tài nguyên CPU/storage.
7. So cả throughput, p95/p99, CPU, số thread và memory footprint.

Đoạn khung minh họa:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorCompletionService;

ExecutorService pool = Executors.newFixedThreadPool(8);
try {
    ExecutorCompletionService<Long> completed =
            new ExecutorCompletionService<>(pool);

    // Submit các tác vụ đọc một block bằng FileChannel positional read,
    // giữ tối đa 8 task outstanding và đọc kết quả hoàn tất.
    // Mỗi tác vụ phải sở hữu buffer riêng; không ghi đồng thời một buffer.
} finally {
    pool.shutdown();
}
```

Đây là **đoạn phác thảo trong một phương thức**, chưa phải code runnable đầy đủ: phải khai báo tác vụ, channel, danh sách offsets và chờ kết quả/`awaitTermination`. Nó chỉ mô tả cách lập baseline, không giả vờ rằng vài dòng trên đã tạo một so sánh công bằng.

**Điểm quan trọng:** `FileChannel` hỗ trợ positional I/O và an toàn dùng nhiều thread theo hợp đồng; tuy nhiên implementation có thể tuần tự hóa một số operation và storage có thể là giới hạn. Benchmark cần đo **thực tế** thay vì cho rằng tám thread sync tương đương chính xác tám I/O đồng thời ở tầng kernel.

## 10. Cải thiện phép đo async: thu kết quả theo completion, không theo submit

Chương trình đầy đủ dùng từng batch depth=8 và đợi các Future **theo thứ tự gửi**. Đây là một thiết kế dễ hiểu cho người mới học, nhưng có thể gây *head-of-line blocking* ở thread thu kết quả.

Giả sử:

```text
t=0: submit A, B, C, D
t=2: B hoàn tất
t=3: C hoàn tất
t=4: D hoàn tất
t=20: A hoàn tất

Future.get theo thứ tự: đợi A tới t=20, rồi mới thu B/C/D.
Completion-driven: thu B/C/D từ t=2,3,4 và có thể nạp request mới.
```

Các thời điểm là **ví dụ tưởng tượng minh họa thuật toán**, không phải kết quả thực của một JVM/thiết bị cụ thể.

Khi ứng dụng có nhiều request độc lập, hãy thử thiết kế **completion-driven sliding window**:

- Cấp phát trước tối đa `depth` buffer/request state.
- Submit `depth` request ban đầu.
- Mỗi callback `completed` xác minh byte/partial read, ghi nhận kết quả rồi **trả buffer về pool** khi không còn outstanding.
- Khi một request logical hoàn tất, submit request tiếp theo để giữ mức outstanding gần với mục tiêu.
- Nếu một operation fail/timeout, đánh dấu trạng thái và điều phối cleanup; không mất buffer ownership.
- Dùng `Semaphore`/bounded queue nếu producer có thể đưa vào nhanh hơn consumer/thiết bị.
- Tránh block callback thread trên tác vụ CPU nặng hoặc một `Future.get()` đợi kết quả của callback khác cùng pool.

Một mô hình sai là submit hàng triệu `channel.read(...)` cùng lúc chỉ để “tận dụng async”. Nó có thể chiếm nhiều heap, tạo queue rất dài và làm tail latency tồi hơn.

### 10.1. Mẫu callback có trách nhiệm ownership

```java
channel.read(buffer, offset, requestId,
        new CompletionHandler<Integer, String>() {
            @Override
            public void completed(Integer count, String id) {
                // Kiểm tra count; nếu partial, phải lên lịch phần còn lại.
                // Khi logical request xong, trả buffer về pool an toàn.
                // Chuyển kết quả tới tầng ứng dụng theo cơ chế thread-safe.
            }

            @Override
            public void failed(Throwable error, String id) {
                // Đánh dấu lỗi, thu hồi request state/buffer an toàn,
                // chuyển nguyên nhân tới owner, cập nhật quota in-flight.
            }
        });
```

Đây là **khung ý tưởng** với các biến chưa định nghĩa, không phải chương trình hoàn chỉnh. Không release buffer ngay sau `channel.read` trả về; chỉ làm vậy khi operation chắc chắn đã hoàn tất và không còn thao tác async nào giữ tham chiếu.

### 10.2. Không đảm bảo thứ tự hoàn tất

`AsynchronousFileChannel` có thể có nhiều request outstanding; **thứ tự thực hiện và thứ tự callback không được bảo đảm** trùng với thứ tự khởi tạo. Nếu ứng dụng ghi nhiều vùng chồng lấn vào cùng file, cần cơ chế điều phối thứ tự và dữ liệu đúng — không dựa vào việc “submit A rồi B nên A chắc chắn ghi xong trước B”.

## 11. Ma trận thử nghiệm theo workload

Một kế hoạch có tính đại diện có thể chia biến thành những chiều độc lập:

| Chiều | Các mức ví dụ | Cần ghi nhận |
| --- | --- | --- |
| I/O operation | Read, write, mixed | Tỷ lệ, sync/durability policy |
| Access pattern | Sequential, random, clustered, hot set | Seed và phân phối offset |
| Block size | 4 KiB, 16 KiB, 64 KiB, 1 MiB | Byte/read, allocation budget |
| Dataset size | 4 MiB, 1 GiB, lớn hơn cache | Dung lượng so RAM |
| Concurrency | 1, 2, 4, 8, 16, 32 | In-flight thực tế và số thread |
| File count | 1 file, vài file, nhiều file nhỏ | Open/close và metadata |
| Storage | Local SSD, HDD, NAS, remote mount | Cache, latency, throughput nền |
| Cache state | Warm, cold-like, mixed | Chuẩn bị dữ liệu và tính lặp |
| CPU work | I/O only, checksum, parse, transform | Có chồng lấp CPU và I/O được không |
| Runtime config | Default async pool, controlled executor | Số worker và queue |
| Duration | Warmup, steady state, burst | Khoảng thời gian và outlier |
| Correctness | Byte count, checksum, error/timeouts | Không bỏ request lỗi |

Đây là ma trận **thiết kế thí nghiệm**, không khuyên chạy tất cả tổ hợp theo tích Descartes nếu quá tốn nguồn lực. Chọn các tổ hợp phản ánh tải thật và tách từng yếu tố cần nghiên cứu.

### 11.1. Các kịch bản ưu tiên

**Kịch bản A — đọc ngẫu nhiên block nhỏ, dataset lớn:** đánh giá IOPS, queue depth, p99 và CPU. Async có thể đem lại lợi ích nếu storage/pool xử lý được nhiều outstanding; nhưng sync concurrent cũng phải được đưa vào baseline.

**Kịch bản B — đọc tuần tự file lớn:** đánh giá MiB/s, kích thước block, read-ahead/cache, số thread và mức CPU. Một `FileChannel` đọc tuần tự đơn giản có thể đã tốt, hoặc một chiến lược mapped/transfer (khi đúng bài toán) có thể phù hợp hơn.

**Kịch bản C — rất nhiều file nhỏ:** đánh giá tổng thời gian open/read/close và metadata. Nếu chi phí file lookup/permission/metadata chiếm đa số, chỉ thay read API có thể ít tác dụng.

**Kịch bản D — I/O xen kẽ CPU:** đo thời gian end-to-end khi có thể xử lý block A trong lúc B đang đọc. Nếu CPU chiếm phần lớn thời gian, thêm I/O concurrency có thể không tăng throughput nữa.

**Kịch bản E — ghi có yêu cầu durable:** đo cả chính sách `force`/flush đúng hợp đồng, thay vì gọi write rồi tuyên bố thành công trước khi dữ liệu được cam kết theo yêu cầu. So async và sync phải có **cùng mức bảo đảm**.

**Kịch bản F — network storage:** đo round-trip, biến động tail latency, queue depth, timeouts và khả năng phục hồi. Kết luận từ file cache trên máy local có thể hoàn toàn không áp dụng.

### 11.2. Cùng ổ đĩa nhưng khác phân phối offset

Một benchmark random uniform trên toàn file khác workload có **hot 10% data** hoặc 90% request tập trung vào một số block. Storage cache/IO scheduler và concurrency có thể phản ứng rất khác. Nếu hệ thống thật có skew, nên tái tạo skew đó thay vì chỉ `Collections.shuffle` một lượt.

### 11.3. Tách read vs write

Ghi dữ liệu có những yếu tố khác đọc:

- OS có thể nhận write vào page cache rồi flush xuống storage sau.
- Thời điểm callback/Future write hoàn tất không nhất thiết cùng mức **durability** mà ứng dụng yêu cầu.
- `AsynchronousFileChannel.force(boolean)` và `FileChannel.force(boolean)` cung cấp thao tác ép dữ liệu/metadata xuống thiết bị theo hợp đồng, nhưng thêm chi phí và có giới hạn phụ thuộc nền tảng.
- Ghi chồng lấn offset có thể gây nondeterminism về thứ tự hoàn tất.
- File có thể thay đổi kích thước trong khi đo, tạo nhiễu metadata/allocation.

Không đo “sync có `force` sau mỗi ghi” rồi so với “async không `force`” và kết luận async nhanh hơn — hai phép đo không cùng mức đảm bảo.

## 12. Đọc kết quả một cách khoa học

### 12.1. Chênh lệch nhỏ có thể chỉ là nhiễu

Nếu hai mode có median cách nhau rất ít và phân phối run-to-run chồng lấn lớn, chưa đủ bằng chứng để khẳng định mode nào tốt hơn. Cần tăng thời lượng, số vòng, kiểm soát môi trường, test trên thiết bị đích và đo confidence/variance theo mục tiêu.

Không chọn duy nhất một lần có số thấp nhất rồi gắn nhãn “fastest”; đó có thể là may mắn từ cache/scheduler.

### 12.2. Amdahl's Law: tối ưu I/O không chữa được mọi bottleneck

Nếu chỉ 20% thời gian end-to-end thật nằm ở I/O bạn định tối ưu, kể cả rút ngắn I/O đó xuống gần 0 cũng không thể giảm tổng thời gian quá 20% theo mô hình lý tưởng đơn giản. Các bước CPU, network, serialization, locks hoặc DB vẫn tồn tại.

Có thể viết dạng khái niệm:

\[
S_\text{overall}=\frac{1}{(1-f)+f/s}
\]

Trong đó `f` là tỷ phần thời gian có thể tối ưu và `s` là hệ số tăng tốc của phần đó. Nếu phần I/O chỉ chiếm một tỷ lệ nhỏ, việc chuyển sang async có thể tăng độ phức tạp mà đem lại ít lợi ích tổng.

### 12.3. Async có thể giúp concurrency dù một operation không nhanh hơn

Một thread phải đồng thời giám sát nhiều phép đọc, xử lý request khác và nhận kết quả khi I/O hoàn tất. Trong tình huống đó, async có thể giúp **thread không bị chặn** khi công việc khác vẫn sẵn có, dù latency một I/O giống hoặc cao hơn sync.

**Đừng đo nhầm:** Nếu mục tiêu là giải phóng request-handling threads, metric cần có số thread block, throughput end-to-end và p99 service latency, không chỉ thời gian đọc một block đơn lẻ.

### 12.4. Sync concurrent cũng có giá trị

Một mô hình `FileChannel` + worker pool với positional reads thường **dễ suy luận và debug**. Trong một ứng dụng có concurrency vừa phải, sync pool có thể đạt SLA với ít complexity hơn async callbacks. Hãy cân nhắc:

- Dễ triển khai/cancellation và exception propagation.
- Resource ownership rõ.
- Tác động heap/CPU.
- Khi overload, queue có bị giới hạn không?
- Debugging, tracing, profiling và p99.
- Độ ổn định giữa OS/JDK/provider.

Không chỉ tối ưu số millisecond trên một bài đo rồi bỏ qua khả năng vận hành và bảo trì.

## 13. Lỗi thường gặp khi đo hiệu năng

| Sai lầm | Vì sao gây sai kết luận | Cách sửa |
| --- | --- | --- |
| “Bất đồng bộ mặc định nhanh hơn” | API model không đảm bảo thời gian I/O nhỏ hơn | Xây giả thuyết theo workload, đo |
| So sync serial với async depth=32 | Vừa đổi API vừa đổi concurrency | Thêm baseline sync concurrent |
| Gọi `Future.get()` ngay sau mỗi submit | Chỉ còn một request outstanding | Pipeline/CompletionHandler khi phù hợp |
| Submit vô hạn Future | Tăng memory/queue, tail latency | Bounded in-flight, backpressure |
| Không kiểm tra bytes read | Partial read/EOF gây benchmark “nhanh” sai | Đọc đủ hoặc báo lỗi |
| Tái sử dụng ByteBuffer trước completion | Data race/corruption | Một buffer mỗi outstanding request |
| In log mỗi block trong vùng đo | Console I/O lấn át file I/O | Ghi metrics ngoài timing |
| Tạo fixture ngay trong timing | So chi phí ghi setup, không chỉ read | Tách setup và đo |
| Không warmup | Class loading/JIT/pool startup lẫn vào kết quả | Warmup, nhiều vòng |
| Luôn chạy sync trước async | Cache/JIT ưu ái mode chạy sau | Xoay/random hóa thứ tự |
| Dữ liệu 4 MiB rồi gọi là “đo tốc độ SSD” | Có thể hoàn toàn nằm trong cache | Ghi rõ warm-cache; dataset lớn cho cold-like |
| So MB/s với MiB/s | Khác hệ chia số byte | Nêu đơn vị tường minh |
| Gọi median batch time là p50 I/O | Không cùng tập quan sát | Instrument per-request latency |
| Quên p99 | Throughput cao có thể kèm tail latency xấu | Ghi phân phối latency |
| Không đo CPU/GC | Hidden scheduling/allocation cost | Dùng JFR/metrics OS |
| Benchmark chỉ một run | Rất nhạy nhiễu và outlier | Lặp, median/variance |
| Đọc/ghi không cùng byte/offset | Công việc khác nhau | Cùng fixture, seed và dữ liệu |
| So write có flush với write không flush | Durability khác nhau | Đồng nhất chính sách |
| Gọi buffer checksum giả làm hash hoàn chỉnh | Có thể bỏ sót dữ liệu sai | Dùng checksum/digest đầy đủ khi cần |
| Tin completion order bằng submit order | Async không đảm bảo thứ tự completion | Có request ID và coordinator |
| Chặn callback với phép tính nặng | Saturate completion threads | Offload sang pool thích hợp |
| Quên error/timeout trong kết quả | Thống kê chỉ request thành công | Báo success/error/deadline rate |
| Tắt GC hoặc cache hệ thống tùy tiện | Làm môi trường không phản ánh thực tế hoặc gây hại | Kiểm soát có chủ đích và được phép |
| Chạy cùng máy có tải nền thất thường | Nhiễu hệ thống | Cô lập/ghi nhận tải |
| Không thử storage sản xuất | Kết quả môi trường khác không áp dụng | Benchmark trên đích thực |
| Chỉ benchmark microseconds | Bỏ open/close, parse, queue, retry | Có thêm end-to-end test |
| Đổi Java flags/pool mà không ghi nhận | Kết quả không tái lập | Ghi configuration/version |
| Không chờ async tasks hoàn tất trước đóng | Missing results/cancellation | Quản lý lifecycle và outstanding |

## 14. Các câu hỏi phân tích sau khi có số liệu

Một quyết định chuyển sang `AsynchronousFileChannel` nên trả lời được:

1. Với workload đại diện, **throughput** tăng bao nhiêu? So với sync concurrent **cùng concurrency** thì sao?
2. **p95/p99 end-to-end** tăng hay giảm khi concurrency cao?
3. CPU/GC/thread pool cost có tăng bao nhiêu? Có bị bottleneck mới ở callback executor không?
4. Khi giảm/increase block size, xu hướng có giữ nguyên không?
5. Khi tăng dataset vượt cache, kết quả đổi chiều không?
6. Khi storage bị tải nền hoặc network jitter, timeout rate thế nào?
7. Byte correctness, partial reads, Buffer ownership và cleanup có được xác nhận?
8. Khi có cancellation/shutdown, request nào có thể hoàn tất muộn? Có rò rỉ buffer/resource không?
9. Nếu chỉ một phần workload hưởng lợi, có thể áp dụng async **có chọn lọc** thay vì chuyển toàn hệ thống không?
10. Mức complexity vận hành so với lợi ích hiệu năng có chấp nhận được không?

**Quyết định tốt có thể là không đổi API.** Nếu `FileChannel` hiện đáp ứng SLA, có CPU thấp, dễ vận hành và async không cải thiện kết quả đại diện, lựa chọn giữ sync là hoàn toàn hợp lý.

## 15. Bài tập tự luyện có đáp án

### Bài 1 — Đọc nhanh từ cache

Một demo tạo file 4 MiB rồi đo 20 lần liên tiếp và thấy sync nhanh hơn async. Có thể kết luận async chậm hơn trên mọi hệ thống không?

**Đáp án:** Không. Data rất có thể nằm trong page cache, khiến overhead Future/pool trở nên nổi bật. Kết luận chỉ có giá trị với workload/môi trường đo; muốn suy rộng cần dataset, storage, concurrency và nhiều chỉ tiêu phù hợp.

### Bài 2 — Future không tự tạo concurrency

`for` lần lượt gọi `channel.read(buffer,offset).get()`. Vì sao có thể không có lợi ích async đáng kể?

**Đáp án:** Vì mỗi request được đợi hoàn tất trước khi submit request kế tiếp; chỉ có khoảng một request outstanding. Cần pipeline hoặc cơ chế điều phối nhiều request độc lập nếu muốn kiểm tra lợi ích concurrency.

### Bài 3 — So sánh công bằng

Sync dùng một thread còn async submit 16 read song song. Async nhanh hơn 2 lần. Có thể quy khác biệt do bản thân API async không?

**Đáp án:** Không. Đã thay đổi concurrency. Cần thêm baseline sync dùng nhiều worker và giới hạn outstanding tương đương.

### Bài 4 — Tính MiB/s

Đọc 80 MiB trong 4 giây đạt bao nhiêu MiB/s?

**Đáp án:** `80 / 4 = 20 MiB/s`. Phải bảo đảm 80 MiB thực sự đọc/hoàn tất và 4 giây là khoảng đo đã định.

### Bài 5 — p50 của request hay của run?

Chạy benchmark năm lần rồi lấy median thời gian mỗi lần đọc 1.024 block. Đã có p50 I/O latency chưa?

**Đáp án:** Chưa. Đó là median **batch run duration**, không phải phân phối latency của 1.024 logical requests. Muốn p50/p99 request phải đo thời gian từng request với ranh giới rõ ràng.

### Bài 6 — Queue depth

Async depth=16 đạt throughput gần bằng depth=8 nhưng p99 tăng rất mạnh và memory nhiều hơn. Nên luôn chọn 16 vì “nhiều request hơn” không?

**Đáp án:** Không. Độ sâu lớn có thể đẩy hệ thống vào saturation/queueing. Chọn điểm cân bằng throughput, p99, CPU và memory theo SLA; có thể depth=8 tốt hơn.

### Bài 7 — Bộ nhớ của buffer

Có 64 request đang chờ, mỗi request giữ ByteBuffer 128 KiB. Chỉ riêng dung lượng payload buffer là bao nhiêu?

**Đáp án:** `64 × 128 KiB = 8.192 KiB = 8 MiB`, chưa kể object, queue, Future, heap overhead và caching.

### Bài 8 — Partial read

`channel.read(buffer,position)` hoàn tất với 2.048 byte khi buffer cần 4.096. Có thể đếm là một block 4.096 byte hoàn tất không?

**Đáp án:** Không. Phải tiếp tục đọc phần còn thiếu hoặc báo EOF/lỗi. Không tính bytes mong muốn thành bytes đã đọc nếu operation chỉ hoàn tất một phần.

### Bài 9 — Thứ tự callback

Submit write A rồi write B vào cùng vùng byte. Có thể chắc callback A đến trước B và file cuối cùng chứa dữ liệu B không?

**Đáp án:** Không. Async không đảm bảo completion order theo submission order. Cần điều phối các write phụ thuộc và quyết định rõ ownership/thứ tự.

### Bài 10 — Cold cache

Benchmark sau khi vừa ghi file tạm 4 MiB có thể tuyên bố đo được tốc độ đọc từ đĩa lạnh không?

**Đáp án:** Không. Fixture mới được ghi có thể đã nằm trong OS page cache. Cần phương pháp kiểm soát cache/dataset có preconditions và ghi rõ giới hạn.

### Bài 11 — I/O vs CPU bottleneck

Ứng dụng tốn 80% thời gian để parse dữ liệu và chỉ 20% để đọc file. Việc giảm thời gian đọc một nửa có bảo đảm toàn bộ ứng dụng nhanh gấp đôi không?

**Đáp án:** Không. Theo mô hình đơn giản, tổng thời gian từ `0,8+0,2 =1` giảm xuống `0,8+0,1=0,9`, tức nhanh hơn khoảng `1/0,9≈1,11` lần, không phải 2 lần. Và con số thực có thể khác do chồng lấp/chờ.

### Bài 12 — Async callback nặng

Callback `completed()` thực hiện parse một file rất lớn ngay trên callback executor. Rủi ro gì?

**Đáp án:** Làm thread xử lý completion bị chiếm lâu, có thể chặn các completion khác và giảm throughput. Nên giữ callback gọn, bàn giao task sang worker có backpressure theo ownership rõ ràng.

### Bài 13 — Checksum mẫu

Một benchmark chỉ kiểm tra 3 byte mỗi block rồi in “verified”. Có chứng minh toàn bộ payload đúng tuyệt đối không?

**Đáp án:** Không. Chỉ kiểm tra các vị trí lấy mẫu, có thể bỏ qua lỗi ở byte khác. Khi cần bảo đảm toàn vẹn, dùng hash/checksum toàn bộ hoặc so byte đầy đủ và xác minh semantics.

### Bài 14 — Timeout của Future

`future.get(100,MILLISECONDS)` timeout. Có chắc operation đã dừng hoặc buffer có thể tái sử dụng ngay không?

**Đáp án:** Không. Timeout của waiter không tự cancel operation. Buffer vẫn có thể đang được I/O sử dụng; cần quản lý completion/cancellation/cleanup đúng lifecycle.

### Bài 15 — Chi phí mở channel

Ứng dụng thực tế mở một file, đọc 1 KiB rồi đóng cho mỗi request. Benchmark chỉ đo read trên channel đã mở sẵn có đại diện cho toàn request không?

**Đáp án:** Không. Phải đo thêm end-to-end open/read/close vì lifecycle có thể chiếm phần lớn latency của workload file nhỏ.

### Bài 16 — Chọn kiến trúc

Sau nhiều vòng đo đúng tải, sync thread pool 8 có throughput tương đương async depth 8, p99 thấp hơn và code dễ vận hành hơn. Có cần vẫn chọn async không?

**Đáp án:** Không. Có thể giữ sync vì đạt SLA tốt hơn ở workload thật. Async chỉ là một lựa chọn thiết kế; không phải mục tiêu tự thân.

### Bài 17 — Benchmark theo tốc độ của thiết bị

Một file 4 MiB trong cache được đọc ở tốc độ tính toán nhiều GiB/s. Điều đó chứng minh SSD vật lý đạt con số này không?

**Đáp án:** Không. Đó có thể là throughput từ OS page cache sang memory. Phải tách cold/warm, dataset vượt cache, I/O thật và đo thiết bị khi cần.

### Bài 18 — Chọn loại metric

Một service có p99 yêu cầu dưới 100 ms. Async tăng tổng operations/s 20% nhưng p99 tăng từ 80 lên 180 ms. Có thể gọi là cải thiện toàn diện không?

**Đáp án:** Không. Dù throughput tăng, nó **vi phạm SLA p99**. Cần đánh đổi/giảm depth/backpressure hoặc chọn cấu hình khác.

## 16. Checklist trước khi quyết định dùng AsynchronousFileChannel

- [ ] Có mô tả workload thực: kích thước file, phân phối offset, block size, read/write mix, concurrency.
- [ ] Đã phân biệt mục tiêu **không chặn caller** với mục tiêu **giảm thời gian hoàn tất I/O**.
- [ ] Có baseline `FileChannel` serial, và baseline sync concurrent khi so với async có nhiều outstanding.
- [ ] Cùng dữ liệu, tổng byte, offset list, validation và điều kiện resource.
- [ ] Có giới hạn `inFlight`/bounded queue và memory buffer budget.
- [ ] Không gọi `Future.get()` ngay sau mọi submit nếu định đo lợi ích pipelining.
- [ ] Có xem xét head-of-line blocking của thứ tự Future và completion-driven window.
- [ ] Có benchmark warm-cache và workload có tính đại diện cho storage/dataset thực tế.
- [ ] Warmup mỗi biến thể, xoay thứ tự và chạy nhiều vòng đo.
- [ ] Ghi JDK, OS, filesystem, storage, page cache, CPU load, pool config và runtime flags.
- [ ] Đo throughput và đúng đơn vị MB/s hoặc MiB/s, không trộn.
- [ ] Đo per-request p50/p95/p99 riêng, không nhầm median batch thời gian với latency của request.
- [ ] Đo CPU/GC/thread count/context switch/buffer memory và error/timeout rate.
- [ ] Xử lý partial read/write, EOF và không tái sử dụng buffer khi I/O còn pending.
- [ ] Không bỏ kết quả lỗi khi tính throughput hoặc so sánh.
- [ ] Với write, cùng chính sách durability/`force` khi so.
- [ ] Không mặc định async callbacks hoàn tất đúng thứ tự submit.
- [ ] Không chặn callback thread với công việc nặng.
- [ ] Có kiểm chứng tính đúng đắn dữ liệu đủ mạnh cho nghiệp vụ.
- [ ] Có test end-to-end với open/close/parse/queue nếu ứng dụng thật có các bước đó.
- [ ] Có test trên môi trường storage mà production đang dùng.
- [ ] Kết luận có điều kiện theo workload, SLA, maintenance và độ tin cậy, **không tuyên bố async luôn nhanh hơn**.
- [ ] Ghi rõ Java NIO.2 API từ Java 7; ví dụ full dùng `record`/`switch expression` của Java hiện đại và biên dịch với `--release 17`.

## 17. Nguồn tham khảo chính thức

- [Java SE 17 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): Future/CompletionHandler, thread pool, I/O positional, nhiều operation outstanding và không đảm bảo thứ tự completion.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): positioned read/write, synchronous I/O và cấu trúc channel.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, remaining, flip/clear và trách nhiệm sử dụng buffer đúng vòng đời.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ microbenchmark cho mã JVM; cần bổ sung kiểm soát filesystem/cache khi benchmark I/O thật.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): thời gian đơn điệu để tính elapsed duration; không dùng như timestamp epoch.

## 18. Kết luận

**`AsynchronousFileChannel` không tự động nhanh hơn `FileChannel`.** Nó thay đổi mô hình **khởi tạo và nhận kết quả I/O**, cho phép nhiều thao tác outstanding và giúp caller tổ chức công việc trong lúc chờ. Lợi ích performance chỉ xuất hiện khi workload, queue depth, thread pool, storage và ứng dụng thật cho phép tận dụng concurrency đó; overhead bất đồng bộ cũng có thể làm một benchmark nhỏ đã cache chạy chậm hơn.

Một kết luận đáng tin phải đi từ **workload đại diện, baseline công bằng, kiểm tra byte đúng, warmup và nhiều vòng đo**, rồi tới **throughput, p95/p99, CPU, GC, memory, tail latency và lỗi**. Ví dụ Java 17 đã chạy cho thấy trong **một môi trường thử nghiệm cụ thể**, sync serial nhanh hơn async depth=1 và depth=8 trên tệp 4 MiB; điều đó minh họa phương pháp đo chứ không phải quy luật chung.

Hãy quyết định theo SLA, tính đúng đắn và chi phí vận hành: có khi async phù hợp để phục vụ nhiều I/O độc lập hoặc chồng lấp xử lý CPU; có khi sync worker pool đơn giản, ổn định và đạt cùng hiệu quả. Điều không nên làm là chọn kiến trúc chỉ vì chữ “bất đồng bộ”.