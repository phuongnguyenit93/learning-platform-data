# Tệp lớn, backpressure ở mức ứng dụng và giới hạn bộ nhớ (Java 8+)

> **Chủ đề cha:** Tệp và I/O. Xử lý file lớn không chỉ là “đọc được file nhiều GB”: pipeline còn phải **đọc theo từng phần, giới hạn số việc đang đợi, không giữ toàn bộ dữ liệu trong heap, và làm chậm bên sinh dữ liệu khi bên xử lý/ghi không theo kịp**. Đó là *backpressure ở mức ứng dụng*. Bài tập trung vào những API Java NIO/I/O/concurrency vẫn được hỗ trợ, đồng thời phân biệt các tính năng chỉ xuất hiện trên JDK mới hơn Java 8.

## 1. Mục tiêu học tập

Bạn sẽ biết:
1. Vì sao `Files.readAllBytes`, `Files.readAllLines`, `collect(toList())` và queue vô hạn có thể gây OOM với file lớn.
2. Dùng `InputStream`, `BufferedInputStream`, `Files.lines` và `FileChannel` đúng bài toán, đóng resource và giới hạn chunk.
3. Tránh lỗi tái sử dụng buffer khi reader và worker hoạt động bất đồng bộ.
4. Thiết kế pipeline `reader → bounded queue → workers → downstream` và giải thích `parallelism`, queue capacity, payload bytes.
5. Dùng `ArrayBlockingQueue`, `CallerRunsPolicy` hoặc `Semaphore` để tạo backpressure thay vì tích lũy backlog.
6. Phân biệt giới hạn **số task** và **tổng byte**, xử lý bản ghi dài/UTF-8 nhiều byte.
7. Quản lý lỗi, timeout, cancellation, output chậm, checkpoints và tài nguyên bộ nhớ.
8. Kiểm thử chương trình Java 8 xử lý một file mẫu 1 MiB bằng chunk 8 KiB, executor 2 worker và queue capacity 2, có thử nghiệm `CallerRunsPolicy` bão hòa xác định.

## 2. Vấn đề: dung lượng file không thể là yêu cầu RAM

Một file 10 GiB không thể được đặt nguyên vẹn trong một `byte[]` của ứng dụng có heap 512 MiB. Kể cả file nhỏ hơn heap về mặt số học, dữ liệu còn có thể nhân lên khi decode thành String, parse thành objects, giữ list, future, queue và cache.

### 2.1. Các API đọc hết file không dành cho trường hợp khổng lồ

```java
byte[] all = Files.readAllBytes(path);
List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
```

JavaDoc nêu rõ `readAllBytes` và `readAllLines` là thao tác tiện lợi, **không dành cho file lớn**. `readAllBytes` có thể ném `OutOfMemoryError` khi không cấp phát được mảng đủ lớn. Không tự ép `Files.size(path)` (trả `long`) về `int` rồi cấp phát một mảng có dung lượng file.

**Dùng Stream nhưng vẫn gom vô hạn cũng sai:**

```java
try (Stream<String> stream = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> everything = stream.collect(Collectors.toList());
    // Nguồn lazy nhưng List vẫn giữ mọi dòng trong RAM.
}
```

`Files.lines` đọc lazy; terminal operation `collect(toList())` mới biến toàn bộ nội dung thành dữ liệu được giữ lại. Những cấu trúc như `ByteArrayOutputStream` ghi toàn file, `StringBuilder` nối mọi dòng, một `List<Future<?>>` cho mọi chunk cũng có vấn đề tăng RAM tương tự.

### 2.2. Kích thước dài và đếm bằng long

`Files.size(path)` và offset của `FileChannel` dùng `long`; tổng bytes/records của file rất lớn cũng nên dùng `long`. Một array/`ByteBuffer` riêng lẻ vẫn có giới hạn kích thước theo `int`: giải pháp là **đọc nhiều chunk nhỏ**, không phải tạo buffer bằng kích thước toàn file. Nếu tính count hoặc tổng số byte bằng `int`, có nguy cơ overflow.

## 3. Streaming với buffer cố định

Mẫu đơn luồng (snippet trong method có thể ném `IOException`):

```java
byte[] buffer = new byte[8 * 1024];
long totalBytes = 0L;
try (InputStream in = new BufferedInputStream(Files.newInputStream(path))) {
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n == 0) continue;
        // Xử lý chính xác buffer[0..n-1].
        totalBytes += n;
    }
}
```

Đừng cho rằng `read(buffer)` luôn lấp đầy 8 KiB: kết quả có thể ngắn hơn. Với nguồn tùy chỉnh trả 0 nhiều lần, phải tránh vòng lặp busy-spin; các nguồn file thông thường đọc non-empty buffer thường trả dữ liệu hoặc EOF. Dùng `try-with-resources` để đóng file ngay cả khi parse thất bại.

### 3.1. Giao dữ liệu cho worker phải copy chunk

Mẫu sai:

```java
byte[] reuse = new byte[8192];
while ((n = in.read(reuse)) != -1) {
    executor.execute(() -> process(reuse));
    // Reader sẽ ghi đè reuse khi worker có thể chưa xử lý xong.
}
```

Mẫu đúng khi xử lý bất đồng bộ:

```java
byte[] ownedChunk = Arrays.copyOf(reuse, n);
executor.execute(() -> process(ownedChunk));
```

Các đoạn này là **snippet cần định nghĩa `in`, `n`, `executor` và `process`**; ví dụ đầy đủ bên dưới tự chứa toàn bộ code. `Arrays.copyOf` tạo dữ liệu riêng cho task, tránh race với reader. Nhưng nếu cứ copy hàng triệu chunk vào queue vô hạn thì RAM vẫn cạn: **sở hữu buffer đúng** phải đi cùng **giới hạn số chunk đang tồn tại**.

### 3.2. Kích thước chunk không có một số “thần kỳ”

Chunk quá nhỏ gây nhiều lời gọi I/O và tasks; chunk quá lớn làm tăng bộ nhớ mỗi item, chi phí copy và độ trễ. Bắt đầu với số đo đại diện (vài KiB đến vài trăm KiB tùy workload), benchmark trên môi trường thật. `8192` trong bài chỉ là kích thước minh họa, không phải khuyến cáo bắt buộc cho mọi đĩa hay dịch vụ.

## 4. Backpressure: chặn đà tăng backlog

Giả sử reader tạo 50.000 chunks/s nhưng downstream chỉ tiêu thụ 10.000 chunks/s. Nếu queue không giới hạn, backlog tăng 40.000 chunks/s, đạt 2,4 triệu chunks sau một phút. Mỗi item giữ `byte[]`, Runnable/lambda và metadata. Dù **đọc từng chunk**, cả pipeline vẫn có thể OOM.

```text
File reader (producer) -> [queue hữu hạn Q item] -> W workers -> output/DB
                             |
                             +-- queue đầy:
                                 producer đợi / tự xử lý / bị từ chối rõ
```

*Backpressure* là truyền áp lực từ tầng xử lý chậm **ngược về producer** để lượng công việc chưa xử lý không tăng vô hạn. Nó phải kéo dài đến **nút cổ chai thật**: nếu queue trước worker hữu hạn nhưng worker đổ tiếp sang một HTTP client có queue vô hạn, bộ nhớ có thể vẫn phình ở tầng sau.

### 4.1. Queue capacity tính item, không phải byte

`new ArrayBlockingQueue<>(10)` giữ tối đa 10 **item**, không biết mỗi item chiếm 1 KiB hay 100 MiB. Cần đồng thời:
- `MAX_CHUNK_BYTES` hoặc `MAX_RECORD_BYTES`;
- Giới hạn queued + running + producer-held;
- Giới hạn tổng bytes trong pipeline khi payload thay đổi kích thước.

Một dòng CSV/JSON cực dài hoặc object có nhiều fields có thể gây OOM dù số lượng items rất ít.

## 5. Các cách tạo backpressure trong Java 8

### 5.1. `BlockingQueue.put` / `offer(timeout)`

```java
BlockingQueue<byte[]> queue = new ArrayBlockingQueue<>(4);

// Producer chờ nếu queue đầy:
queue.put(ownedChunk);

// Consumer chờ nếu queue rỗng:
byte[] item = queue.take();
```

`ArrayBlockingQueue` có capacity cố định. `put` chờ chỗ trống, `offer(x,time,unit)` cho phép chờ có hạn rồi trả `false` khi quá tải. Với cancellation, hãy xử lý interrupt, trạng thái lỗi của consumer và quy trình dừng; đừng cho producer chờ mãi ở `put` nếu mọi consumer đã chết.

### 5.2. `ThreadPoolExecutor` hữu hạn + `CallerRunsPolicy`

```java
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        2, 2, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<Runnable>(2),
        new ThreadPoolExecutor.CallerRunsPolicy());
```

Executor này có hai worker và tối đa hai task trong queue. Khi worker đều bận, queue đầy, `CallerRunsPolicy` chạy task bị từ chối ngay trên **thread gọi `execute`**. Nếu thread đó là producer, nó phải làm việc trước khi tiếp tục đọc file: backpressure tự nhiên.

**Hai lưu ý quan trọng:**

- `CallerRunsPolicy` chạy inline nên callback có thể block producer, làm tăng độ trễ của request đang gửi task; chỉ chọn khi đó là hành vi mong muốn.
- Khi executor **đã shutdown**, policy này **discard task thay vì chạy**, vì vậy nó không phải một lời hứa “never lose tasks”. Phải dừng intake trước khi shutdown, không submit sau shutdown và có chính sách xử lý tasks bị từ chối rõ ràng.

`AbortPolicy` là lựa chọn khác: ném `RejectedExecutionException` khi không nhận được task, để caller áp dụng timeout/retry/đưa sang persistent queue. `DiscardPolicy` và `DiscardOldestPolicy` có thể làm mất dữ liệu, thường không phù hợp nếu bắt buộc xử lý mọi record.

### 5.3. `Semaphore` giới hạn tổng số in-flight

Một semaphore với N permits có thể chặn producer **trước khi submit** task tiếp theo, bao gồm cả running và queued:

```java
Semaphore limit = new Semaphore(4);
limit.acquire();
try {
    executor.execute(() -> {
        try {
            process(ownedChunk);
        } finally {
            limit.release();
        }
    });
} catch (RejectedExecutionException ex) {
    limit.release();
    throw ex;
}
```

Snippet trên **giả định executor dùng rejection handler ném `RejectedExecutionException`**, không dùng handler silently discard. Cần thiết kế cẩn thận với task exception, cancellation và không được release permit **hai lần**. Nếu một policy thực thi callback inline rồi ném exception, logic xử lý phải kiểm tra quyền sở hữu permit tương ứng. Semaphore theo **số task**; với payload biến thiên rất lớn có thể cần weighted byte-budget riêng.

## 6. Ước lượng ngân sách bộ nhớ

Với `W` worker, queue tối đa `Q`, chunk tối đa `B` bytes, `CallerRuns` có thể làm thêm một task trên producer, và reader có một reusable buffer:

```text
payload (ước lượng) ~ (W + Q + 1 task trên caller + 1 buffer reader) * B
                       + metadata/buffer thư viện/runtime khác
```

Ví dụ W=2, Q=2, B=8192: phần **payload chính** trong thiết kế demo khoảng `(2+2+1+1)*8192 = 49152` bytes, **không phải giới hạn heap chính xác**. Còn có `BufferedInputStream`, Runnable, queue, JVM/GC, buffers ghi, page cache của OS và các cấu trúc khác. Dùng heap profiler và đo peak memory để kiểm chứng thay vì coi công thức là SLA.

Công thức chỉ đúng khi task thực sự giữ tối đa B bytes, queue hữu hạn và không có danh sách `Future`, cache, log buffer hay output staging tăng không giới hạn.

### 6.1. File lớn có thể chứa một record khổng lồ

`BufferedReader.readLine()` có thể tạo một String rất lớn **trước khi code kiểm tra `line.length()`**. Nếu input không đáng tin, phải kiểm tra giới hạn bytes/chars **trong lúc parser nhận từng phần**, chứ không chỉ kiểm tra sau khi đã ghép toàn bộ dòng. Ví dụ CSV một dòng 1 GiB có thể làm OOM ngay cả khi bạn xử lý “từng dòng”.


## 7. Văn bản, UTF-8 và ranh giới chunk

Khi file là **text**, không được biến từng chunk tùy ý thành String độc lập rồi nối lại mà không xét encoding. Một ký tự UTF-8 có thể được mã hóa bằng nhiều bytes; hai chunk có thể chia đôi mã đó. `new String(chunk, UTF_8)` trên từng khối có thể tạo ký tự thay thế hoặc giải mã sai khi gặp ranh giới.

### 7.1. Hai lựa chọn đúng

**Đọc theo dòng** nếu bản ghi có giới hạn kích thước tin cậy:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng, không giữ toàn bộ vào List.
    }
}
```

**`Files.lines` (Java 8)** cho pipeline lazy, nhưng **phải đóng Stream**:

```java
try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isEmpty()).count();
}
```

`Files.lines` không tự bảo đảm giới hạn kích thước một dòng và không tạo backpressure nếu downstream lại `collect(toList())`. Nếu đọc file đang bị writer thay đổi trong khi xử lý, hợp đồng kết quả có thể không còn xác định; nên dùng file đầu vào bất biến/versioned hoặc phối hợp việc ghi.

Nếu input có record dài không đáng tin cậy, dùng parser tăng dần trên `Reader`/`CharsetDecoder` với một giới hạn bytes/chars **trước khi phân bổ String khổng lồ**. `CharsetDecoder` có khả năng duy trì trạng thái qua ranh giới byte buffers; hãy xử lý `underflow`, `overflow` và malformed input theo policy (reject/replace/report) rõ ràng.

### 7.2. File binary không cần decode text

Chương trình hoàn chỉnh ở phần 11 chỉ đếm byte ASCII `'A'`; do đó cắt file binary thành những chunk 8192 bytes không làm thay đổi ngữ nghĩa. Nó **không giả làm parser CSV/JSON**. Nếu bạn cần parse protobuf/JSON lines hoặc record có cấu trúc, phải giữ phần record chưa hoàn chỉnh qua ranh giới chunk và giới hạn size của phần tích lũy đó.

### 7.3. Một file dài hàng GB cũng có thể đổi khi đang xử lý

Nếu file bị truncate/append/replace trong lúc đọc, `Files.size` đo trước không còn chắc chắn bằng số bytes thực tế đã đọc. Dùng checksum, version/rename-atomic, immutable object storage hoặc hợp đồng “file đã đóng” tùy hệ thống. Đừng dùng file size làm nguồn sự thật duy nhất khi input có thể thay đổi đồng thời.

## 8. `FileChannel`, transfer và memory-mapped file

`FileChannel` có thể dùng khi cần đọc theo vị trí, làm việc với `ByteBuffer`, random access hoặc chuyển bytes giữa channels. `FileChannel.transferTo` có thể hiệu quả cho sao chép/chuyển file theo khả năng hệ điều hành, nhưng **không được mặc định luôn chuyển hết lượng yêu cầu trong một lần**.

```java
long position = 0L;
long size = source.size();
while (position < size) {
    long moved = source.transferTo(position, size - position, target);
    if (moved <= 0L) {
        throw new IOException("Transfer made no progress");
    }
    position += moved;
}
```

Snippet này giả định `source` là `FileChannel` đọc, `target` là `WritableByteChannel` phù hợp và method có thể throws `IOException`; khi transfer không tiến triển, production có thể fallback sang copy bằng buffer. Dùng `long` cho offset. Đừng coi `transferTo` là lệnh “đọc cả file vào Java heap”.

`MappedByteBuffer` cho truy cập dữ liệu file qua vùng nhớ ánh xạ, nhưng mapping **không phải miễn phí về tài nguyên**: liên quan virtual address space, OS page cache, file lifecycle, unmapping và kích thước mapping. Không mặc định mmap có bộ nhớ tối thiểu hay thích hợp với mọi file, nhất là khi chỉ cần scan tuần tự một lần.

`ByteBuffer.allocateDirect` dùng off-heap/direct memory, vì vậy heap metric riêng có thể trông thấp trong khi process vẫn thiếu bộ nhớ vật lý. Cần theo dõi **heap, direct/native memory và OS page cache** tùy bài toán.

## 9. Làm gì khi output/DB chậm?

Nếu reader và CPU workers rất nhanh nhưng mỗi kết quả cuối cùng được gửi sang DB/network có throughput thấp, memory có thể dồn **sau** worker:

```text
Disk -> parser -> bounded worker queue -> CPU workers -> [unbounded DB requests]
                                                     -> OOM dời sang tầng khác
```

Backpressure cần tới điểm tiêu thụ thực: bounded output queue, số connection/request in-flight, semaphore với byte/task budget và timeout. Khi ghi file, dùng `BufferedOutputStream`/`BufferedWriter` và write theo chunk; không giữ toàn bộ output trong `ByteArrayOutputStream` chỉ để viết một lần.

Các giới hạn nên có: kích thước batch, số batch đang chờ ghi, deadline mỗi operation, downstream concurrency, disk quota cho spill-to-disk, chính sách reject/quarantine/retry có idempotency. Backpressure **không làm tăng tốc dịch vụ đích**; nó ngăn hệ thống tự giết mình khi đích chậm.

## 10. Lỗi và lifecycle là một phần của giới hạn bộ nhớ

### 10.1. Không quên kiểm tra lỗi của worker

Trong demo, worker chỉ đếm byte, hầu như không có lỗi nghiệp vụ. Trong production, task được gửi bằng `execute` có thể ném unchecked exception trên worker; `awaitTermination` **không tự ném lại** exception ấy cho reader. Cần thu lỗi qua `Future`, `CompletionService`, shared `AtomicReference<Throwable>` hoặc kênh lỗi rõ ràng.

**Tránh lại tạo lỗi bộ nhớ:** đừng giữ một `List<Future>` cho từng chunk trong file hàng trăm triệu chunks. Dùng giới hạn số futures đang pending, drain completed futures thường xuyên, hoặc một shared error signal và bộ đếm/bộ đồng bộ hoàn tất không tăng theo file size.

### 10.2. Thất bại giữa chừng thì sao?

Nếu đã xử lý 70% file rồi downstream trả lỗi, dừng producer, dừng/đợi workers có kiểm soát, quyết định hủy hay hoàn tất những task đang in-flight, đóng I/O và lưu trạng thái/checkpoint theo record boundary thích hợp. Nếu chạy lại từ đầu sau lỗi, side effects đã hoàn thành có thể **bị lặp**: cần idempotency/deduplication/checkpoint, không coi “đọc file một lần” đồng nghĩa exactly-once.

Với file UTF-8 hoặc record dài, checkpoint ở offset byte tùy ý có thể nằm giữa ký tự hoặc một bản ghi; phải định nghĩa cách resume đúng ranh giới dữ liệu.

### 10.3. Interruption và timeout

`BlockingQueue.put/take`, `Semaphore.acquire`, `Future.get` và `awaitTermination` có thể bị interrupt; đừng lờ `InterruptedException`. Khi lớp hiện tại không propagate được, thường restore interrupt flag bằng `Thread.currentThread().interrupt()` rồi thoát theo policy. Timeout của `Future.get(timeout)` không tự đảm bảo cancel I/O hoặc giải phóng socket/file; cần đóng nguồn và hủy tác vụ thật sự.

`shutdown()` từ chối task mới nhưng vẫn cho phép các task trước hoàn thành; `shutdownNow()` chỉ **yêu cầu** ngắt, không cam kết chấm dứt mọi I/O. Không gọi shutdown trước khi gửi xong tất cả chunks nếu đang dùng CallerRunsPolicy, vì task gửi sau shutdown có thể bị discard.

## 11. Chương trình Java 8 hoàn chỉnh có backpressure thật

Ví dụ dùng **file tạm 1.048.576 bytes** (128 chunk × 8192 bytes), tự tạo bằng `Files.newOutputStream` theo mẫu byte `'A','B','A','B'...`. Reader đọc và xử lý từng chunk, **copy đúng số bytes** trước khi submit.

Executor có **2 worker**, queue có tối đa **2 Runnable**, và `CallerRunsPolicy` khi bão hòa. Sau khi reader đọc hết, chương trình gọi `shutdown`/`awaitTermination` rồi xác minh tổng bytes và số byte `'A'`, không giả định thứ tự xử lý. File tạm được xóa trong `finally`.

Một thử nghiệm thứ hai chứng minh **CallerRuns được kích hoạt thật**, không phụ thuộc timing ngẫu nhiên: pool có 1 worker và queue capacity 1; worker đầu chờ latch, task thứ hai lấp queue, task thứ ba buộc chạy trên thread producer. Sau đó mở latch và đợi worker kết thúc. Thử nghiệm cố định này giải thích cơ chế chứ không đo throughput.

**Lưu vào file `LargeFileBackpressureDemo.java`.** Đây là source Java độc lập, không cần thư viện ngoài JDK:


```java
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.LongAdder;

public class LargeFileBackpressureDemo {
    private static final int CHUNK_BYTES = 8 * 1024;
    private static final int CHUNK_COUNT = 128;

    private static void createSample(Path file) throws IOException {
        byte[] chunk = new byte[CHUNK_BYTES];
        for (int i = 0; i < chunk.length; i++) {
            chunk[i] = (byte) (i % 2 == 0 ? 'A' : 'B');
        }
        try (OutputStream out = Files.newOutputStream(file)) {
            for (int i = 0; i < CHUNK_COUNT; i++) {
                out.write(chunk);
            }
        }
    }

    private static boolean proveCallerRuns() throws InterruptedException {
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);
        AtomicBoolean ranOnCaller = new AtomicBoolean(false);
        Thread producerThread = Thread.currentThread();
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());
        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!workerStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            pool.execute(() -> { }); // Chiếm vị trí duy nhất trong queue.
            pool.execute(() -> ranOnCaller.set(
                    Thread.currentThread() == producerThread));
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Proof pool did not terminate");
            }
            return ranOnCaller.get();
        } finally {
            releaseWorker.countDown();
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("streaming-backpressure-", ".bin");
        try {
            createSample(file);
            LongAdder processedBytes = new LongAdder();
            LongAdder countedA = new LongAdder();
            LongAdder submittedChunks = new LongAdder();

            ThreadPoolExecutor workers = new ThreadPoolExecutor(
                    2, 2, 0L, TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<Runnable>(2),
                    new ThreadPoolExecutor.CallerRunsPolicy());
            try {
                try (InputStream in = new BufferedInputStream(
                        Files.newInputStream(file))) {
                    byte[] reusableBuffer = new byte[CHUNK_BYTES];
                    int size;
                    while ((size = in.read(reusableBuffer)) != -1) {
                        if (size == 0) {
                            continue;
                        }
                        byte[] ownedChunk = Arrays.copyOf(
                                reusableBuffer, size);
                        workers.execute(() -> {
                            long localA = 0L;
                            for (byte value : ownedChunk) {
                                if (value == 'A') {
                                    localA++;
                                }
                            }
                            countedA.add(localA);
                            processedBytes.add(ownedChunk.length);
                        });
                        submittedChunks.increment();
                    }
                }
                workers.shutdown();
                if (!workers.awaitTermination(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Workers did not finish");
                }
            } finally {
                workers.shutdownNow();
            }

            boolean queueEmpty = workers.getQueue().isEmpty();
            boolean callerRunsProof = proveCallerRuns();
            long fileBytes = Files.size(file);
            long processed = processedBytes.sum();
            long countA = countedA.sum();
            long chunks = submittedChunks.sum();

            System.out.println("Input file size: " + fileBytes);
            System.out.println("Chunk bytes: " + CHUNK_BYTES);
            System.out.println("Worker count: 2");
            System.out.println("Queue capacity: 2");
            System.out.println("Submitted chunks: " + chunks);
            System.out.println("Processed bytes: " + processed);
            System.out.println("Count of A: " + countA);
            System.out.println("Queue empty after shutdown: " + queueEmpty);
            System.out.println("CallerRuns at saturation: " + callerRunsProof);

            if (fileBytes != 1_048_576L || chunks != 128L
                    || processed != fileBytes || countA != 524_288L
                    || !queueEmpty || !callerRunsProof) {
                throw new AssertionError("Backpressure demo mismatch");
            }
            System.out.println("Checks passed.");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch trên JDK 17+ với API/ngôn ngữ Java 8, hoặc dùng `javac` của JDK 8:

```bash
javac --release 8 LargeFileBackpressureDemo.java
java LargeFileBackpressureDemo
```

**Stdout đã kiểm chứng trên OpenJDK 24:**


```text
Input file size: 1048576
Chunk bytes: 8192
Worker count: 2
Queue capacity: 2
Submitted chunks: 128
Processed bytes: 1048576
Count of A: 524288
Queue empty after shutdown: true
CallerRuns at saturation: true
Checks passed.
```

### 11.1. Phân tích chương trình

- File mẫu được **ghi theo 128 lượt** với cùng một mảng 8 KiB, không tạo mảng 1 MiB trước khi ghi. Đây chỉ là file demo, không phải phép kiểm tra tốc độ đĩa.
- Reader chỉ giữ một reusable buffer và tạo `ownedChunk` dài đúng `size` cho mỗi task. Worker không thấy buffer bị producer ghi đè.
- Executor dùng 2 workers, queue capacity 2. Khi bão hòa, CallerRuns làm producer xử lý ngay một chunk, nhờ đó không tích lũy tasks vô hạn.
- `LongAdder` lưu tổng bytes và số byte A; các lần cập nhật này đến từ nhiều threads nhưng chương trình chỉ đọc `sum()` **sau khi mọi task đã kết thúc**, nên kết quả cuối chính xác cho file mẫu không thay đổi.
- Dữ liệu có nửa số bytes là A (524.288 trong 1.048.576 bytes), tổng chunks là 128. Không in thread name hay thứ tự chunks vì scheduling không được bảo đảm.
- Thử nghiệm `proveCallerRuns` dùng latch để **chắc chắn** worker đang bận và queue đã đầy, từ đó kiểm tra task thứ ba chạy trong producer thread. Nó không suy ra rằng mọi request trong thực tế đều sẽ chạy ở caller.
- Sau khi mọi tác vụ kết thúc, queue rỗng; file tạm được xóa trong finally kể cả khi kiểm tra thất bại.

**Giới hạn của demo:** Worker chỉ đếm bytes, không có lỗi xử lý nghiệp vụ hay ghi DB. Nếu worker thực sự có thể thất bại, phải có kênh thông báo lỗi và stop/cancel policy; đừng coi `awaitTermination` là phép tự thu mọi throwable của `execute`. Khi thay bằng parse text, phải quản lý encoding, record boundaries và max record size riêng.

## 12. Bảng kiểm thử cần làm trên dữ liệu thật

| Kiểm thử | Cần xác nhận |
| --- | --- |
| File lớn hơn heap nhiều lần | Peak memory không tăng tuyến tính với file size |
| Producer nhanh hơn consumer | Queue không vượt capacity; producer bị chậm/reject theo policy |
| Một record hoặc line cực dài | Bị giới hạn **trước khi** cấp phát object khổng lồ |
| UTF-8 ký tự nhiều byte cắt giữa chunk | Decoder giữ trạng thái, không hỏng ký tự |
| File kết thúc ở chunk chưa đầy | Chỉ xử lý `size` bytes thực đọc |
| Đầu vào thay đổi giữa lúc đọc | Policy snapshot/version được xác định |
| Worker throw exception | Reader nhận lỗi, dừng/cleanup, không “thành công giả” |
| Queue đầy khi hủy | Producer/consumer đều có đường thoát |
| Downstream ghi DB/HTTP chậm | Không có queue ẩn tích lũy vô hạn ở tầng sau |
| Retry sau xử lý được một phần | Checkpoint/idempotency tránh đếm trùng |
| Process bị shutdown giữa chừng | Không submit sau shutdown; không discard âm thầm |
| Buffer direct/mapped | Đo cả native/direct memory, không chỉ Java heap |

Theo dõi throughput bytes/s, queue depth, thời gian producer bị chặn, số running/rejected tasks, GC pause, heap sử dụng, direct/native memory, thời gian I/O và p95/p99 latency của downstream. Chọn batch, queue, worker count và timeout theo số đo workload thật, không chỉ theo kích thước file.

## 13. Lựa chọn API trên JDK mới hơn

**Java 9+:** `java.util.concurrent.Flow` định nghĩa giao thức Publisher/Subscriber/Subscription; `Subscription.request(n)` cho phép consumer **yêu cầu thêm** n phần tử theo mô hình demand. Nhưng API chỉ cung cấp hợp đồng: một producer triển khai sai vẫn có thể buffer vô hạn. `Flow` không tồn tại trong Java 8, do đó **không** được copy code `Flow` vào project giới hạn Java 8.

**Java 11+:** `HttpClient.sendAsync` cung cấp API bất đồng bộ cho HTTP; cũng không tự động giới hạn số request bạn tạo. Nếu file reader tạo vô hạn futures HTTP, vẫn phải áp dụng semaphore/rate limit/backpressure.

**Java 21+:** virtual threads rất phù hợp với nhiều task I/O blocking, nhưng **không tự giới hạn số task hay bytes được giữ**. Virtual threads không thay thế bounded queue, record size cap, giới hạn kết nối hoặc chính sách cancellation. Với workload CPU-bound, cần phân tích pool/parallelism riêng.

**Trong Java 8:** `InputStream`, `BufferedInputStream`, `Files.lines`, `FileChannel`, `ArrayBlockingQueue`, `ThreadPoolExecutor`, `Semaphore` đã đủ để xây pipeline streaming có memory bound; không cần dùng API lỗi thời.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `Files.readAllBytes` với file hàng GB | OOM hoặc array size limit | Đọc theo buffer/chunk |
| `Files.lines` rồi `collect(toList())` | Vẫn giữ toàn bộ file trong RAM | Xử lý tuần tự/streaming không tích lũy |
| Quên đóng `Files.lines` | Rò file handle | Try-with-resources |
| Nhiều tasks nhưng queue không giới hạn | Backlog và heap tăng không dừng | Bounded queue + backpressure |
| Bounded queue nhưng item cực lớn | Memory vẫn quá hạn | Max record/chunk bytes |
| Dùng chung reusable `byte[]` với worker | Race, dữ liệu bị ghi đè | `Arrays.copyOf(buffer,n)` |
| Giả định `read` luôn đầy buffer | Bỏ/sai dữ liệu ở chunk cuối | Dùng chính xác `n` |
| Decode UTF-8 riêng từng chunk | Hỏng ký tự đa byte | Streaming decoder/Reader đúng |
| Dùng `readLine` rồi kiểm tra line length | Quá muộn với dòng rất lớn | Chặn size trong parser tăng dần |
| Dùng `CallerRunsPolicy` sau executor shutdown | Task bị discard | Đóng intake trước, kiểm tra lifecycle |
| Dùng `DiscardPolicy` cho giao dịch không được mất | Mất records âm thầm | Abort/retry/persistent staging |
| Giữ mọi `Future` trong list | O(N) memory theo chunks | Bounded in-flight/drain completions |
| Nghĩ `awaitTermination` tự ném lỗi worker | Lỗi bị che | Thu lỗi explicit |
| Chỉ giới hạn queue trước CPU, để output queue vô hạn | Dời OOM sang tầng sau | Backpressure end-to-end |
| Gọi `transferTo` một lần rồi tin copy hết | Có thể chỉ chuyển một phần | Loop/fallback khi no progress |
| Dùng int cho total file byte count | Overflow | `long` |
| Nghĩ virtual threads giải quyết memory bound | Tạo vô hạn task vẫn OOM | Byte/task budgets riêng |

## 15. Bài tập và đáp án

**1.** Có file 6 GiB với heap 512 MiB, nên gọi `Files.readAllBytes`? — Không. Đọc theo chunk nhỏ và xử lý streaming.

**2.** `Files.lines(path).collect(toList())` có còn memory bound không? — Không. Stream lazy nhưng kết quả bị gom vô hạn.

**3.** Producer đọc buffer 8192 bytes rồi submit vào worker và đọc tiếp với cùng mảng; sai ở đâu? — Worker có thể đọc mảng đã bị ghi đè. Copy mỗi chunk hoặc dùng pool buffer với ownership an toàn.

**4.** Queue capacity 3, mỗi record có thể dài 200 MiB. Queue có thật sự “nhỏ” không? — Không. Cần giới hạn payload size và tổng bytes.

**5.** Khi pool 2 worker và queue 2 đầy, `CallerRunsPolicy` làm gì? — Thực thi task mới trên thread gọi `execute` **nếu executor chưa shutdown**; nếu đã shutdown, policy discard task.

**6.** Muốn producer chờ đến khi queue có chỗ thay vì reject? — `ArrayBlockingQueue.put`; nếu cần deadline, `offer(timeout)`.

**7.** Một chunk UTF-8 cắt giữa ký tự có thể decode riêng sang String an toàn không? — Không. Dùng decoder có trạng thái hoặc Reader.

**8.** Sau khi `ThreadPoolExecutor.awaitTermination` trả true, có chắc toàn bộ worker thành công không? — Không. Cần kiểm tra kênh errors/results độc lập.

**9.** `FileChannel.transferTo` trả ít bytes hơn yêu cầu thì sao? — Theo dõi vị trí, tiếp tục vòng lặp/fallback, không bỏ phần còn lại.

**10.** Virtual threads Java 21 có làm queue chứa vô hạn byte trở nên an toàn không? — Không. Vẫn cần giới hạn số lượng/bytes, downstream và lifecycle.

## 16. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `readAllBytes`, `readAllLines`, `lines`, `newInputStream` và đóng resource.
- [Oracle Java SE 26 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): capacity cố định, `put/take/offer`.
- [Oracle Java SE 26 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue, saturation, thread management, rejection.
- [Oracle Java SE 26 — CallerRunsPolicy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html): thực thi trên caller khi bão hòa, discard sau shutdown.
- [Oracle Java SE 26 — FileChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/FileChannel.html): đọc/ghi theo channel, `transferTo`.
- [Oracle Java SE 26 — Flow.Subscription](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(n)` và consumer demand, **chỉ từ Java 9+**.
- [Oracle Java SE 8 — Files](https://docs.oracle.com/javase/8/docs/api/java/nio/file/Files.html), [ThreadPoolExecutor](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ThreadPoolExecutor.html): các API runnable tương thích Java 8.

**Kết luận:** Muốn xử lý file lớn an toàn, cần **đọc theo chunk hoặc record có giới hạn**, **không tích lũy mọi task/result**, **áp dụng backpressure ở điểm downstream chậm nhất**, và tính ngân sách theo **bytes đang in-flight**, không chỉ số items. Streaming + bounded queue + lifecycle/error handling đúng là một thiết kế; chỉ đổi `readAllBytes` sang `Files.lines` hoặc `supplyAsync` là chưa đủ.
