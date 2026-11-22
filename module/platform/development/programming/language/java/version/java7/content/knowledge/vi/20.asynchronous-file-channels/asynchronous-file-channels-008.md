# Kênh tệp bất đồng bộ trong Java: Quản lý executor cùng vòng đời kênh

## 1. Tại sao vòng đời của executor và channel phải được quản lý cùng nhau?

`AsynchronousFileChannel` là API NIO.2 được đưa vào từ Java 7 và **vẫn áp dụng trong Java 17+**. Nó nhận yêu cầu đọc/ghi tại những vị trí xác định trong file và trả kết quả qua `Future<Integer>` hoặc `CompletionHandler<Integer,A>`. Channel được gắn với một thread pool dùng cho các tác vụ xử lý sự kiện I/O và dispatch completion callbacks.

Khi ứng dụng tự truyền `ExecutorService` vào kênh, câu hỏi không chỉ là “đọc được bao nhiêu byte?” mà còn là:

- Ai **sở hữu** executor và có quyền shutdown?
- Một pool có thể dùng chung giữa nhiều file channels không?
- Khi nào được đóng kênh mà không làm hỏng tác vụ đang chờ?
- Có thể shutdown pool khi một channel còn mở không?
- Khi một operation timeout/cancel, buffer đã an toàn để tái sử dụng chưa?
- Nếu mở channel thứ hai thất bại, channel đầu và pool được dọn thế nào?
- `shutdown` khác `shutdownNow` và `awaitTermination` ở đâu?

**Quy tắc quan trọng nhất:** Tài liệu Java SE 17 về `AsynchronousFileChannel.open(Path, Set, ExecutorService, ...)` nêu rõ: **shutdown executor trong khi channel còn mở dẫn tới hành vi không được đặc tả (unspecified behavior)**. Vì vậy với pool do ứng dụng sở hữu, quy trình chuẩn là:

```text
Tạo ExecutorService
      |
Mở các AsynchronousFileChannel cùng dùng pool
      |
Gửi I/O có giới hạn, thu kết quả/exception
      |
Ngừng nhận công việc mới; drain/abort theo policy
      |
Đóng TẤT CẢ channels còn dùng pool
      |
executor.shutdown()
      |
executor.awaitTermination(...)
      |
Xác minh, báo trạng thái và cleanup
```

`channel.close()` và `executor.shutdown()` **không phải một thao tác**. Không cho callback của một channel nhỏ tự đóng pool của cả service.

## 2. Mở kênh có và không có executor được truyền vào

### 2.1. Dùng default thread pool

```java
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path source = Path.of("source.bin");

try (AsynchronousFileChannel channel =
        AsynchronousFileChannel.open(
                source, StandardOpenOption.READ)) {
    // Nhận Future hoặc CompletionHandler và xử lý hoàn tất.
}
```

Đây là **mã minh họa trong phương thức** có `throws IOException`. `open(Path, OpenOption...)` dùng default pool của runtime/provider; pool này **có thể được chia sẻ**. Caller chỉ chịu trách nhiệm đóng channel của mình; **không tự shutdown default pool**.

### 2.2. Dùng executor do ứng dụng tạo

```java
import java.nio.channels.AsynchronousFileChannel;
import java.nio.file.*;
import java.util.Set;
import java.util.concurrent.*;

ExecutorService pool = Executors.newFixedThreadPool(3);

try {
    try (AsynchronousFileChannel channel =
            AsynchronousFileChannel.open(
                    source, Set.of(StandardOpenOption.READ), pool)) {
        // Submit và chờ các logical I/O tasks cần hoàn tất.
    } // Đóng channel trước.
} finally {
    pool.shutdown();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
    }
}
```

**Đây là đoạn minh họa thứ tự ownership**, chưa đầy đủ handling cho `InterruptedException` và lần `awaitTermination` thứ hai sau `shutdownNow`. Ví dụ Java 17+ chạy độc lập ở mục 9 có đủ xử lý cleanup chính.

Chữ ký có executor:

```java
AsynchronousFileChannel.open(
        Path file,
        Set<? extends OpenOption> options,
        ExecutorService executor,
        FileAttribute<?>... attrs);
```

- `file`: đường dẫn file thật.
- `options`: ví dụ `READ`, `WRITE`, `CREATE_NEW`, `CREATE`, `TRUNCATE_EXISTING`.
- `executor`: pool được gắn với channel; `null` để chọn default pool theo contract.
- `attrs`: thuộc tính tùy chọn khi tạo file nếu provider hỗ trợ.

`CREATE_NEW` là lựa chọn tránh overwrite tệp đã tồn tại; `TRUNCATE_EXISTING` có thể làm mất nội dung cũ. Chọn đúng theo nghiệp vụ.

### 2.3. Ai shutdown?

| Trường hợp | Owner của pool | Trách nhiệm shutdown |
| --- | --- | --- |
| `open(path, READ)` | Runtime/provider | Caller **không** shutdown default pool |
| `open(path, opts, ownPool)` | Job/service tạo pool | Shutdown sau khi các channels đóng |
| Hai channels dùng chung `ownPool` | Scope bao trùm cả hai | Không shutdown khi một channel còn mở |
| Pool được dependency injection từ service cha | Service cha | Component chỉ đóng channel do mình sở hữu |

Không đưa tài nguyên chia sẻ vào `finally` của một component nhỏ nếu component đó không có quyền sở hữu pool.

## 3. Yêu cầu của executor theo Oracle Java SE 17

### 3.1. Cấu hình tối thiểu

Tài liệu `AsynchronousFileChannel.open` lưu ý executor cần hỗ trợ các công việc provider dùng cho I/O events và completion handlers; bản chất tasks là implementation-specific. Tối thiểu nó **nên hỗ trợ unbounded work queue** và **không chạy task trực tiếp trên caller thread của `execute`**.

`Executors.newFixedThreadPool(3)` là một lựa chọn tiện để minh họa: số worker threads cố định, queue không giới hạn. Ngược lại:

- Executor với **bounded queue + rejection** có thể từ chối những công việc mà provider phải submit.
- `CallerRunsPolicy` có thể chạy internal task ngay trên caller thread, trái cảnh báo của API.
- Một implementation của `ExecutorService` thực thi ngay task trong `execute` không nhất thiết phù hợp.

Không nên tự thay executor provider bằng một wrapper chỉ để có metric hoặc throttle mà bỏ qua các ràng buộc này.

### 3.2. Vì sao unbounded queue không có nghĩa ứng dụng được gửi vô hạn requests?

`newFixedThreadPool(3)` chỉ giới hạn worker threads; application vẫn có thể tạo hàng trăm nghìn `ByteBuffer` và `CompletableFuture` pending, gây cạn bộ nhớ hoặc backlog. Giới hạn nên nằm ở **tầng dispatcher**:

```java
Semaphore permits = new Semaphore(8);

for (Chunk chunk : chunks) {
    permits.acquire(); // Điều phối ở thread ngoài I/O pool.
    CompletableFuture<Result> f = submitAsync(chunk);

    f.whenComplete((value, error) -> {
        // Chỉ release sau khi logical I/O thật sự hoàn tất.
        permits.release();
    });
}
```

Đây là **pseudocode**: `Chunk`, `Result` và `submitAsync` do ứng dụng định nghĩa. Nếu `submitAsync` ném lỗi ngay, phải release permit ở nhánh lỗi. Nếu future wrapper bị timeout nhưng underlying I/O còn chạy, không trả buffer/permit dựa riêng vào timeout đó.

**Hai tầng khác nhau:** executor cần queue phù hợp API; ứng dụng cần bounded number of in-flight logical requests và tổng byte buffers.

### 3.3. Pool size, callback latency và khả năng I/O thực tế

Completion handler được gọi trên thread thuộc pool liên kết với channel. Khi operation hoàn tất tức thời và caller đang là thread của pool, handler có thể được gọi trực tiếp.

Không nên chạy parsing/nén/network blocking lâu trong handler; chúng có thể chiếm workers mà provider cần để dispatch completions khác. Tách việc nặng sang executor nghiệp vụ khác. Không giả định asynchronous API luôn tương ứng native nonblocking OS I/O; provider có thể dùng threads cho I/O.

Chọn pool size qua đo lường throughput, latency, số requests và đặc tính storage; không có giá trị “luôn tối ưu” cho mọi workload.

### 3.4. Phân biệt `AsynchronousChannelGroup`

`AsynchronousChannelGroup` thường gắn với các asynchronous socket channels. `AsynchronousFileChannel.open(Path,Set,ExecutorService,...)` nhận trực tiếp **`ExecutorService`**, không phải `AsynchronousChannelGroup`. Đừng áp nhầm nhóm socket và lifecycle `group.shutdown` để quản lý file channel.

## 4. Vòng đời khi nhiều channels chia sẻ một pool

Giả sử source và output dùng chung pool:

```text
FileIoService — owner
    |
    +--> ExecutorService pool
    |
    +--> Channel A: source.bin (read)
    |
    +--> Channel B: output.bin (write)
```

Nếu channel B hoàn tất trước A, B có thể được đóng nhưng **pool vẫn phải hoạt động** cho A. Chỉ scope sở hữu cả A và B mới quyết định shutdown khi cả hai channels đã đóng.

Snippet làm rõ ownership:

```java
ExecutorService pool = Executors.newFixedThreadPool(3);

try {
    try (AsynchronousFileChannel input =
            AsynchronousFileChannel.open(
                    source,
                    Set.of(StandardOpenOption.READ),
                    pool)) {

        try (AsynchronousFileChannel output =
                AsynchronousFileChannel.open(
                    destination,
                    Set.of(StandardOpenOption.WRITE,
                            StandardOpenOption.CREATE_NEW),
                    pool)) {

            // Chờ tất cả reads/writes cần hoàn thành.
        }
    }
} finally {
    pool.shutdown();
}
```

Đây là **minh họa**, không phải pipeline đủ logic short I/O và graceful wait. Nếu mở output lỗi, `try(input)` vẫn đóng input trước khi `finally` chạy, tránh rò channel đầu tiên.

Nếu pool do một service cha cung cấp cho nhiều jobs, những jobs **không được shutdown pool khi xong việc riêng**; owner cha phải ngừng nhận jobs, drain, đóng toàn bộ associated channels, rồi shutdown.

## 5. `close`, `shutdown`, `shutdownNow` và `awaitTermination`

| Method | Đối tượng | Ý nghĩa | Không bảo đảm |
| --- | --- | --- | --- |
| `channel.close()` | Channel | Đóng file channel; outstanding operations có thể hoàn thành với `AsynchronousCloseException` | File đã ghi đầy đủ |
| `pool.shutdown()` | Executor | Không nhận tasks mới, cho tasks đã submit tiếp tục | Đã terminated |
| `pool.shutdownNow()` | Executor | Cố dừng/interrupt tasks theo best effort | Dừng mọi task ngay |
| `pool.awaitTermination(timeout,unit)` | Executor | Chờ terminated/timeout/interrupt | Byte output chính xác |
| `Future.get()` | I/O operation | Chờ kết quả một operation | Không tự biến partial read thành full read |
| `CompletableFuture.allOf` | Logical futures | Đợi các futures được chỉ định | Các futures được complete đúng logic |
| `channel.force(false)` | File channel | Yêu cầu flush data theo storage contract | Multi-write atomic transaction |

### 5.1. Thứ tự đóng channel khi cần output thành công

`AsynchronousFileChannel.close` có thể được gọi khi I/O đang chờ; Java API quy định outstanding asynchronous operations hoàn thành với `AsynchronousCloseException` trong tình huống đóng channel. Do đó, nếu cần file hoàn chỉnh:

1. Ngừng submit yêu cầu mới.
2. Chờ đủ bytes hoặc nhận lỗi/EOF cho các logical requests.
3. Verify completion và dữ liệu; gọi `force` nếu cần durability.
4. Đóng channels.
5. Shutdown pool **sau đó**.

Trong nhánh abort, đóng channel có thể được dùng để làm các pending operations kết thúc với lỗi; file đã ghi dở vẫn có thể tồn tại. Không publish dữ liệu như thành công.

### 5.2. `shutdown()` không đợi pool kết thúc

`pool.isShutdown()` chỉ nói pool đã nhận yêu cầu shutdown. Cần `awaitTermination` để xác định termination; `pool.isTerminated()` là kiểm tra trạng thái cuối.

### 5.3. `shutdownNow()` không phải rollback

`shutdownNow()` chỉ cố interrupt/loại tasks chưa chạy, không bảo đảm I/O đang thực hiện bị đảo ngược. Nếu storage đã ghi vài bytes, chúng có thể vẫn tồn tại. Không dùng `shutdownNow()` như thay thế cho xử lý file staging và lỗi I/O.

### 5.4. Mẫu shutdown executor sau khi mọi channel đã đóng

```java
static void closeOwnedPool(ExecutorService pool)
        throws InterruptedException {

    pool.shutdown();

    try {
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Executor did not terminate");
            }
        }
    } catch (InterruptedException interrupted) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
        throw interrupted;
    }
}
```

Đây là helper minh họa cần import `ExecutorService`/`TimeUnit` và chỉ được gọi **sau khi associated channels đã đóng**. Timeout 5 giây không phải chuẩn bắt buộc; dùng giá trị cấu hình phù hợp.

## 6. CompletionHandler và Future ràng buộc việc đóng kênh

### 6.1. Một completion không nhất thiết là một logical task đã hoàn tất

`read`/`write` có thể trả ít byte hơn `ByteBuffer.remaining()`. Nếu một logical task cần 4 byte, callback nhận 2 byte phải tiếp tục xử lý hai byte còn lại trước khi complete logical future.

Ví dụ ý tưởng:

```java
channel.read(buffer, fileOffset, task,
        new CompletionHandler<Integer, Task>() {
            @Override
            public void completed(Integer n, Task t) {
                // Xử lý n, gửi tiếp nếu buffer.hasRemaining().
            }
            @Override
            public void failed(Throwable error, Task t) {
                // Complete future exceptionally.
            }
        });
```

Đây là mã minh họa; `Task` và các biến phải được định nghĩa. Không bỏ qua nhánh `failed`, vì caller có thể chờ mãi một `CompletableFuture` chưa complete.

### 6.2. `ByteBuffer` không được tái sử dụng khi pending

```java
ByteBuffer shared = ByteBuffer.allocate(4096);
channel.read(shared, 0);
shared.clear(); // Sai: I/O có thể đang dùng buffer.
channel.read(shared, 4096); // Sai: hai requests tranh buffer.
```

Chỉ `flip/clear` hay trả buffer về pool khi đã biết underlying I/O hoàn tất và không còn ai sử dụng vùng nhớ. `ByteBuffer.duplicate()`/`slice()` chia sẻ storage, không phải bản sao bytes độc lập.

### 6.3. Timeout của `Future.get` không có nghĩa underlying I/O đã dừng

`future.get(5, TimeUnit.SECONDS)` có thể ném `TimeoutException`, nhưng operation vẫn có thể chạy. `CompletableFuture.orTimeout` cũng chỉ thay state wrapper theo deadline, không nhất thiết dừng I/O provider.

Không tự động reuse buffer hoặc shutdown pool chỉ vì wrapper timeout. Cần cancellation/quiescence policy rõ ràng.

### 6.4. Không block trong completion callback

Completion handler chạy trên thread của pool gắn với channel. Nếu callback gọi `Future.get()` chờ task khác cũng cần pool đó để hoàn tất, có nguy cơ starvation/deadlock. Callback nên ghi nhận count/error, submit phần còn lại nếu cần, complete future và để business work nặng chạy trên executor riêng.

## 7. Từ RUNNING tới TERMINATED

Một service có thể dùng state machine:

```text
STARTING -- tạo executor, mở channel, kiểm tra quyền
   |
RUNNING  -- submit bounded I/O, theo dõi futures/errors
   |
STOPPING -- không nhận request mới
   |
DRAINING -- wait/abort I/O theo policy
   |
CLOSING  -- close toàn bộ associated channels
   |
SHUTDOWN -- pool.shutdown/awaitTermination
   |
TERMINATED
```

Trường hợp lỗi:

- **Open lỗi:** cleanup channels đã mở, shutdown pool nếu owner là job này.
- **I/O lỗi:** fail logical future, không publish output sai; quyết định retry/abort có giới hạn.
- **EOF hoặc short write:** xử lý theo số byte thực, không coi một completion bằng full chunk.
- **Timeout:** không reuse buffer sớm; cần biết underlying operation còn pending.
- **Interrupt dispatcher:** cleanup, propagate và thường khôi phục interrupt flag.
- **Shutdown timeout:** `shutdownNow` best effort, đợi thêm, nếu chưa terminated phải báo chưa hoàn tất.
- **Crash cứng:** `finally` không đảm bảo chạy; cần staging/recovery cho dữ liệu quan trọng.

### 7.1. `force(false)` không làm nhiều writes thành atomic

Chỉ sau khi writes hoàn tất và trước close, có thể gọi `channel.force(false)` để yêu cầu flush nội dung theo contract. Nó không phải atomic transaction cho nhiều file offsets. Nếu cần replace một file quan trọng, tạo staging, verify bytes/checksum và publish theo khả năng atomic move của filesystem.

### 7.2. Nhiều writes phải xác định các vùng không chồng lấp

Ví dụ:

```text
Write offset 0:  WXYZ  → [0,4)
Write offset 4:  1234  → [4,8)
Write offset 8:  mnop  → [8,12)
Result: WXYZ1234mnop
```

Nếu ghi chồng lên cùng một khoảng byte, completion order không được đảm bảo; nội dung có thể phụ thuộc lịch I/O. Dùng phân vùng file hoặc synchronization/locking riêng.

## 8. Ví dụ Java 17+ độc lập đã kiểm thử

Chương trình tạo workspace tạm riêng để không đụng dữ liệu người dùng. Nó:

1. Tạo file nguồn `ABCDEFGHIJKL`.
2. Tạo custom pool ba threads tên `owned-file-io-N`.
3. Mở hai `AsynchronousFileChannel` cùng pool, một để đọc và một để ghi.
4. Gửi ba reads 4-byte vào offsets `0,4,8`; ghép `ABCD|EFGH|IJKL`.
5. Gửi ba writes `WXYZ`, `1234`, `mnop` vào các vùng tách biệt; xử lý partial writes và chờ tất cả completions.
6. Kiểm tra callbacks thuộc custom executor.
7. Gọi `target.force(false)` sau khi writes hoàn tất; đóng target/input trước khi shutdown pool.
8. `shutdown`/`awaitTermination` và xác minh `isTerminated`.
9. Đọc lại output `WXYZ1234mnop`; mở channel khác bằng default pool và đọc `ABCD`.
10. Cleanup đúng thư mục tạm do chương trình sở hữu.

**Lưu tệp `AsyncChannelExecutorLifecycleDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class AsyncChannelExecutorLifecycleDemo {
    static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    static void markThread(AtomicBoolean valid) {
        if (!Thread.currentThread().getName()
                .startsWith("owned-file-io-")) {
            valid.set(false);
        }
    }

    static CompletableFuture<String> readExactly(
            AsynchronousFileChannel channel, long base, int length,
            AtomicBoolean correctExecutor) {
        ByteBuffer buffer = ByteBuffer.allocate(length);
        CompletableFuture<String> done = new CompletableFuture<>();
        CompletionHandler<Integer, Void> handler =
                new CompletionHandler<Integer, Void>() {
                    @Override public void completed(Integer count, Void none) {
                        markThread(correctExecutor);
                        if (count == null || count < 0) {
                            done.completeExceptionally(
                                    new EOFException("Unexpected EOF"));
                            return;
                        }
                        if (count == 0) {
                            done.completeExceptionally(
                                    new IOException("Read made no progress"));
                            return;
                        }
                        if (buffer.hasRemaining()) {
                            try {
                                channel.read(buffer, base + buffer.position(),
                                        null, this);
                            } catch (RuntimeException ex) {
                                done.completeExceptionally(ex);
                            }
                        } else {
                            buffer.flip();
                            byte[] data = new byte[buffer.remaining()];
                            buffer.get(data);
                            done.complete(new String(
                                    data, StandardCharsets.US_ASCII));
                        }
                    }
                    @Override public void failed(Throwable error, Void none) {
                        markThread(correctExecutor);
                        done.completeExceptionally(error);
                    }
                };
        try {
            channel.read(buffer, base, null, handler);
        } catch (RuntimeException ex) {
            done.completeExceptionally(ex);
        }
        return done;
    }

    static CompletableFuture<Void> writeExactly(
            AsynchronousFileChannel channel, long base, String text,
            AtomicBoolean correctExecutor) {
        ByteBuffer buffer = ByteBuffer.wrap(
                text.getBytes(StandardCharsets.US_ASCII));
        CompletableFuture<Void> done = new CompletableFuture<>();
        CompletionHandler<Integer, Void> handler =
                new CompletionHandler<Integer, Void>() {
                    @Override public void completed(Integer count, Void none) {
                        markThread(correctExecutor);
                        if (count == null || count <= 0) {
                            done.completeExceptionally(
                                    new IOException("Write made no progress"));
                            return;
                        }
                        if (buffer.hasRemaining()) {
                            try {
                                channel.write(buffer, base + buffer.position(),
                                        null, this);
                            } catch (RuntimeException ex) {
                                done.completeExceptionally(ex);
                            }
                        } else {
                            done.complete(null);
                        }
                    }
                    @Override public void failed(Throwable error, Void none) {
                        markThread(correctExecutor);
                        done.completeExceptionally(error);
                    }
                };
        try {
            channel.write(buffer, base, null, handler);
        } catch (RuntimeException ex) {
            done.completeExceptionally(ex);
        }
        return done;
    }

    static String defaultPoolRead(Path file) throws Exception {
        try (AsynchronousFileChannel channel =
                AsynchronousFileChannel.open(file, StandardOpenOption.READ)) {
            ByteBuffer buffer = ByteBuffer.allocate(4);
            while (buffer.hasRemaining()) {
                Future<Integer> future =
                        channel.read(buffer, buffer.position());
                int n = future.get(5, TimeUnit.SECONDS);
                if (n < 0) throw new EOFException("Default pool read EOF");
                if (n == 0) throw new IOException("No read progress");
            }
            buffer.flip();
            return StandardCharsets.US_ASCII.decode(buffer).toString();
        }
    }

    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult postVisitDirectory(
                    Path directory, IOException error) throws IOException {
                if (error != null) throw error;
                Files.delete(directory);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws Exception {
        Path work = Files.createTempDirectory("owned-async-channel-");
        try {
            Path source = work.resolve("source.bin");
            Path output = work.resolve("output.bin");
            Files.writeString(
                    source, "ABCDEFGHIJKL", StandardCharsets.US_ASCII);

            AtomicInteger threadNumber = new AtomicInteger();
            ExecutorService ownedPool = Executors.newFixedThreadPool(
                    3, task -> new Thread(
                            task, "owned-file-io-" +
                                    threadNumber.incrementAndGet()));
            AtomicBoolean onOwnedExecutor = new AtomicBoolean(true);
            boolean channelsClosed;

            try {
                AsynchronousFileChannel input =
                        AsynchronousFileChannel.open(
                                source, Set.of(StandardOpenOption.READ),
                                ownedPool);
                boolean outputClosed = false;

                try (input) {
                    AsynchronousFileChannel target =
                            AsynchronousFileChannel.open(
                                    output,
                                    Set.of(StandardOpenOption.WRITE,
                                            StandardOpenOption.CREATE_NEW),
                                    ownedPool);
                    try (target) {
                        List<CompletableFuture<String>> reads = List.of(
                                readExactly(input, 0, 4, onOwnedExecutor),
                                readExactly(input, 4, 4, onOwnedExecutor),
                                readExactly(input, 8, 4, onOwnedExecutor));
                        CompletableFuture.allOf(reads.toArray(
                                new CompletableFuture<?>[0]))
                                .get(10, TimeUnit.SECONDS);
                        String blocks = String.join("|",
                                reads.stream().map(
                                        CompletableFuture::join).toList());
                        System.out.println("read.blocks=" + blocks);
                        check(blocks.equals("ABCD|EFGH|IJKL"),
                                "Wrong read result");

                        List<CompletableFuture<Void>> writes = List.of(
                                writeExactly(target, 0, "WXYZ",
                                        onOwnedExecutor),
                                writeExactly(target, 4, "1234",
                                        onOwnedExecutor),
                                writeExactly(target, 8, "mnop",
                                        onOwnedExecutor));
                        CompletableFuture.allOf(writes.toArray(
                                new CompletableFuture<?>[0]))
                                .get(10, TimeUnit.SECONDS);
                        target.force(false);
                        check(input.isOpen() && target.isOpen(),
                                "Unexpected early close");
                    }
                    outputClosed = !target.isOpen();
                }
                channelsClosed = !input.isOpen() && outputClosed;
                System.out.println(
                        "handlers.ownedExecutor=" +
                                onOwnedExecutor.get());
                System.out.println(
                        "channels.closedBeforePoolShutdown=" + channelsClosed);
                check(channelsClosed && onOwnedExecutor.get(),
                        "Resource ownership");
            } finally {
                ownedPool.shutdown();
                try {
                    if (!ownedPool.awaitTermination(5, TimeUnit.SECONDS)) {
                        ownedPool.shutdownNow();
                        if (!ownedPool.awaitTermination(
                                5, TimeUnit.SECONDS)) {
                            throw new IOException("Pool did not terminate");
                        }
                    }
                } catch (InterruptedException error) {
                    ownedPool.shutdownNow();
                    Thread.currentThread().interrupt();
                    throw error;
                }
            }

            System.out.println("executor.shutdown=" + ownedPool.isShutdown());
            System.out.println("executor.terminated=" +
                    ownedPool.isTerminated());

            String actual = Files.readString(
                    output, StandardCharsets.US_ASCII);
            System.out.println("write.result=" + actual);

            String fromDefault = defaultPoolRead(source);
            System.out.println("defaultPool.read=" + fromDefault);

            check(ownedPool.isShutdown()
                    && ownedPool.isTerminated()
                    && actual.equals("WXYZ1234mnop")
                    && fromDefault.equals("ABCD"),
                    "Final checks");
            System.out.println("checks=PASS");
        } finally {
            deleteTree(work);
        }
        System.out.println("workspace.cleaned=" +
                !Files.exists(work));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 AsyncChannelExecutorLifecycleDemo.java
java AsyncChannelExecutorLifecycleDemo
```

**Stdout đã kiểm chứng thực tế trên JDK 17+:**

```text
read.blocks=ABCD|EFGH|IJKL
handlers.ownedExecutor=true
channels.closedBeforePoolShutdown=true
executor.shutdown=true
executor.terminated=true
write.result=WXYZ1234mnop
defaultPool.read=ABCD
checks=PASS
workspace.cleaned=true
```

### 8.1. Giải thích kết quả

- `read.blocks=ABCD|EFGH|IJKL`: ba khối nguồn đọc đúng offsets; kết quả ghép theo thứ tự index thay vì thứ tự callback.
- `handlers.ownedExecutor=true`: trong lần chạy thử, handlers chạy trên threads với tên do `ThreadFactory` của custom pool đặt.
- `channels.closedBeforePoolShutdown=true`: channel đọc và ghi đều đã đóng trước khi đến `finally` shutdown pool.
- `executor.shutdown=true`: đã phát lệnh shutdown.
- `executor.terminated=true`: `awaitTermination` xác nhận pool thực sự terminated.
- `write.result=WXYZ1234mnop`: file đích có đúng 12 byte sau khi writes hoàn tất và kênh đóng.
- `defaultPool.read=ABCD`: một channel khác dùng default pool; chương trình chỉ đóng channel đó, không shutdown default executor.
- `checks=PASS`: assertions kiểm tra resource ownership và nội dung đạt.
- `workspace.cleaned=true`: chỉ workspace tạm do chương trình sở hữu được xóa.

### 8.2. Giới hạn của ví dụ

Chương trình không mô phỏng provider lỗi, hủy I/O giữa chừng hay tải hàng nghìn requests. Nó coi completion trả 0 byte là no-progress error thay vì busy-loop. Timeouts 5 và 10 giây chỉ dành cho kiểm thử nhỏ, không phải cấu hình bắt buộc.

`force(false)` yêu cầu đẩy nội dung xuống storage nhưng không làm một nhóm writes thành atomic transaction. Trong production phải xác định durability và publish/recovery policy phù hợp.

## 9. Mẫu quy trình dừng cho service thực

Một service có thể dùng các trạng thái:

```text
STARTING
   |
RUNNING: nhận I/O có giới hạn
   |
STOPPING: ngừng nhận requests mới
   |
DRAINING: chờ/abort logical operations
   |
CLOSING: đóng toàn bộ associated channels
   |
SHUTDOWN: pool.shutdown(), awaitTermination()
   |
TERMINATED
```

**Graceful shutdown:** ngừng nhận jobs mới, đợi tất cả operations cần hoàn tất hoặc fail rõ, xác minh bytes, đóng channels, rồi shutdown pool và đợi termination.

**Abort:** đóng channels, xử lý `AsynchronousCloseException` và output dở dang; sau khi channels đóng mới shutdown pool; không báo output thành công khi chỉ mới dừng threads.

**Interrupted dispatcher:** cleanup ở scope owner, thường khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`, không nuốt tín hiệu rồi tiếp tục vô hạn.

**Khởi tạo thất bại:** khi output channel mở lỗi, scope `try(input)` phải đóng input; `finally` shutdown pool do job tạo. Không để exception thứ hai từ cleanup che mất lỗi chính mà không ghi nhận/suppressed đúng.

## 10. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Sửa |
| --- | --- | --- |
| `pool.shutdown` khi channel còn mở | Hành vi không được đặc tả | Đóng tất cả associated channels trước |
| Quên shutdown custom pool | Rò thread | Owner shutdown và awaitTermination |
| Helper shutdown shared pool | Ảnh hưởng channels khác | Owner cấp cao quản lý |
| Dùng `CallerRunsPolicy` | Trái ràng buộc executor của channel | Executor phù hợp, throttle ở tầng app |
| Gửi vô hạn pending requests | Cạn buffers/futures/queue | Bounded in-flight |
| Callback block chờ future trong cùng pool | Starvation/deadlock | Callback ngắn |
| Không xử lý `failed` | Caller chờ mãi | Complete exceptionally |
| Một `read/write` được coi là full chunk | Thiếu bytes | Xử lý partial/EOF |
| Reuse `ByteBuffer` khi pending | Race | Reuse sau completion thật |
| `Future.get(timeout)` được coi đã hủy I/O | I/O vẫn có thể chạy | Quiescence/cancellation policy |
| Đóng kênh trước writes xong | Output bị thiếu và pending errors | Drain trước close |
| `shutdown()==true` được coi terminated | Pool có thể còn tasks | `awaitTermination` |
| `shutdownNow` được coi chắc chắn dừng | Best effort | Chờ thêm và báo timeout |
| Bỏ qua `InterruptedException` | Không tôn trọng cancellation | Re-interrupt, cleanup |
| Dùng `AsynchronousChannelGroup` cho overload file channel | Sai API | Quản lý trực tiếp `ExecutorService` |
| `force(false)` được coi atomic commit | Không có transaction | Staging/verify/publish |
| Mở channel B lỗi gây rò A | Resource leak | Nested try-with-resources |
| Cleanup xóa dữ liệu ngoài job | Mất dữ liệu | Chỉ xóa staging có ownership |

## 11. Kiểm thử lifecycle

Các ca tối thiểu:

1. Pool tự tạo + một channel, shutdown sau close.
2. Hai channels cùng pool, không shutdown khi chỉ một channel đóng.
3. Callback thread thuộc custom pool đã được truyền.
4. Nhiều reads/writes đúng bytes ở các vùng không chồng lấp.
5. Channel dùng default pool, không shutdown default pool.
6. `shutdown()`, `awaitTermination` và `isTerminated` cho trạng thái chính xác.
7. Output channel open lỗi sau input open; input vẫn được đóng.
8. `CREATE_NEW` không ghi đè file đã có.
9. Short I/O, EOF và failure callback.
10. Timeout/cancel khi buffer còn pending.
11. Thread bị interrupt khi chờ, cleanup đúng.
12. Pending operation khi close, xử lý `AsynchronousCloseException`.
13. Pool không terminated sau `shutdownNow`, phải báo trạng thái chưa dừng.
14. Đường dẫn và file permissions/provider không hợp lệ.

Đừng viết test khẳng định “shutdown pool trước close chắc chắn ném một exception X”: API đã xác định trường hợp đó là không được đặc tả. Nên kiểm tra **thứ tự ownership** bằng các fake/instrumented resources hơn là cố chạy hành vi sai.

## 12. Câu hỏi ôn tập

**Câu 1.** `AsynchronousFileChannel.open(file, READ)` dùng executor nào?  
**Đáp án:** Pool mặc định do runtime/provider quản lý.

**Câu 2.** Ai shutdown pool được truyền vào `open(path, opts, pool)`?  
**Đáp án:** Owner của pool, khi mọi associated channels đã đóng.

**Câu 3.** Vì sao không shutdown pool khi channel còn mở?  
**Đáp án:** Javadoc quy định hành vi không được đặc tả, pool có thể cần cho I/O và callbacks.

**Câu 4.** `channel.close()` có đồng nghĩa `pool.shutdown()` không?  
**Đáp án:** Không, đây là hai tài nguyên khác nhau.

**Câu 5.** Hai channels dùng chung pool, một channel xong có được shutdown pool?  
**Đáp án:** Không nếu channel khác vẫn mở.

**Câu 6.** `shutdown()` có chờ pool terminated không?  
**Đáp án:** Không; dùng `awaitTermination` và `isTerminated`.

**Câu 7.** `shutdownNow()` có bảo đảm dừng ngay mọi tasks?  
**Đáp án:** Không, chỉ best effort.

**Câu 8.** Vì sao tránh `CallerRunsPolicy`?  
**Đáp án:** Provider yêu cầu executor không chạy task trực tiếp trên caller thread của `execute`.

**Câu 9.** Fixed pool có tự giới hạn số pending I/O không?  
**Đáp án:** Không; ứng dụng cần bounded dispatcher.

**Câu 10.** `Future.get(timeout)` timeout có nghĩa I/O nền đã dừng không?  
**Đáp án:** Không. Không tái sử dụng buffer chỉ vì wrapper timeout.

**Câu 11.** Đóng channel đang có pending writes làm gì?  
**Đáp án:** Outstanding operations có thể hoàn thành với `AsynchronousCloseException` và output có thể dở.

**Câu 12.** `force(false)` có atomic transaction cho nhiều writes không?  
**Đáp án:** Không; nó chỉ yêu cầu flush theo storage contract.

**Câu 13.** Vì sao dùng nested try-with-resources?  
**Đáp án:** Đảm bảo nếu mở output thất bại thì input vẫn được đóng trước khi shutdown pool.

**Câu 14.** CompletionHandler chạy trên thread nào?  
**Đáp án:** Thread thuộc pool gắn với channel; thứ tự callbacks không được bảo đảm.

## 13. Checklist triển khai

- [ ] Phân biệt default executor với pool do ứng dụng sở hữu.
- [ ] Xác định owner của pool và từng file channel.
- [ ] Không shutdown pool khi có channel gắn vào còn mở.
- [ ] Không shutdown shared pool trong callback/helper nhỏ.
- [ ] Dùng đúng `open` overload và file options.
- [ ] Pool đáp ứng ràng buộc queue và caller thread của JDK.
- [ ] Giới hạn logical requests và buffer memory ở tầng app.
- [ ] Callback nhẹ, không block chéo trên cùng pool.
- [ ] Quản lý buffer cho tới khi I/O hoàn tất thực.
- [ ] Xử lý partial reads/writes, EOF và lỗi.
- [ ] Không coi timeout của future là underlying I/O đã dừng.
- [ ] Ngừng submit trước khi drain/abort.
- [ ] Đợi operations cần hoàn tất, không dùng `Thread.sleep` thay thế.
- [ ] Đóng tất cả channels trước khi shutdown pool.
- [ ] Shutdown/awaitTermination, xử lý timeout và interruption.
- [ ] Xác minh bytes; staging/atomic publish nếu cần.
- [ ] Cleanup chỉ resources có ownership.
- [ ] Test cả success, failure, shared pool và pending operations.

## 14. Kết luận và tài liệu chính thức

**Quản lý executor cùng vòng đời kênh** đúng nghĩa là quản lý ba dạng sở hữu: executor, file channel và từng I/O request/ByteBuffer. Với custom executor: **gửi I/O → nhận đủ completions → đóng mọi channels → shutdown và await executor**. Với pool mặc định, **chỉ đóng channel** và không tự shutdown default pool.

Những quy tắc này còn hiệu lực trong Java 17+ và cần đi cùng exception handling, kiểm soát pending operations, timeout, forced abort và xác minh output.

Tài liệu chính thức Java SE 17:

- [Oracle `AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): open overload, executor rules, close và I/O.
- [Oracle `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, shutdownNow và awaitTermination.
- [Oracle `CompletionHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed callbacks.
- [Oracle `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, timeout, cancel.
- [Oracle `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): aggregation và exceptional completion.
- [Oracle `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffer state và ownership.
- [Oracle `Executors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): pool factories.
- [Oracle `AsynchronousChannelGroup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): phân biệt socket channel group với file channel executor.
