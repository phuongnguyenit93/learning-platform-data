# Java 7 — Kênh mạng bất đồng bộ: AsynchronousChannelGroup và luồng xử lý callback

## 1. Mục tiêu bài học

`AsynchronousChannelGroup` là thành phần NIO.2 dùng để **gom các asynchronous network channels nhằm chia sẻ tài nguyên xử lý I/O và các completion handlers**. Nó không chỉ là tên đặt cho một nhóm socket; group có **thread pool** liên quan, quy tắc dispatch callback và vòng đời shutdown/termination riêng.

Khi viết server với `AsynchronousServerSocketChannel` và `AsynchronousSocketChannel`, người lập trình thường bối rối:

- Callback `CompletionHandler.completed(...)` được thực thi trên **thread nào**? Có phải thread đã gọi `read` hoặc `accept`?
- Đặt group có **2 threads** thì có đúng 2 connections tối đa không?
- Tại sao callback có thể hoàn thành “ngay lập tức”, và trường hợp nào có **inline execution**?
- Khi dùng `withFixedThreadPool`, `withCachedThreadPool` hoặc `withThreadPool` thì quyền sở hữu executor và chính sách shutdown khác nhau thế nào?
- `group.shutdown()` có **đóng các socket ngay** không? Phân biệt `isShutdown()` với `isTerminated()`.
- Vì sao không nên `Future.get()`, `Thread.sleep()` hoặc gọi DB chậm trực tiếp trong handler?
- Một socket được `accept` từ listener thuộc group nào?
- Mặc định khi mở channel mà không chỉ rõ group sẽ thế nào?

Bài học đi từ hợp đồng chính thức của Java NIO.2, qua ví dụ chạy được trên **Java 17+**, rồi đến cách thiết kế thread pool và shutdown cho ứng dụng thực tế. API có từ **Java 7**, vẫn được dùng trong Java SE 17+; không dùng lớp nội bộ hoặc kiến thức lỗi thời.

## 2. AsynchronousChannelGroup là gì — và không phải là gì?

Theo Java SE 17, `AsynchronousChannelGroup` là một **nhóm asynchronous channels để chia sẻ tài nguyên**. Group bao gói cơ chế:

1. Xử lý các **I/O events** từ các channels được bind vào group.
2. Dispatch kết quả tới `CompletionHandler` của những asynchronous operations.
3. Chạy các tác vụ phụ trợ cần thiết để triển khai asynchronous I/O.
4. Quản lý **thread pool** và vòng đời của pool đó thông qua group.

Sơ đồ logic:

```text
AsynchronousChannelGroup
├── Thread pool: aio-worker-1, aio-worker-2, ...
│   ├── xử lý I/O events của provider
│   ├── dispatch CompletionHandler.completed/failed
│   └── tác vụ hỗ trợ asynchronous I/O
│
├── AsynchronousServerSocketChannel (listener)
│   └── accept() ─► callback nhận connected child
│                      │
│                      ▼
│                AsynchronousSocketChannel (accepted child, cùng group)
│                    ├── read()  ─► callback
│                    └── write() ─► callback
│
└── AsynchronousSocketChannel (outbound client)
    └── connect() ─► callback
```

**Không phải**:

- Một danh sách socket có API “lấy tất cả thành viên”: `AsynchronousChannelGroup` không cung cấp collection public để iterate mọi channel.
- Một thread-per-connection executor: một group có thể quản lý **nhiều channels hơn số pooled threads**.
- Một đơn vị đảm bảo mỗi connection luôn được xử lý bởi **cùng một thread cố định** (*thread affinity*); Java chỉ bảo đảm callback chạy trên **một thread thuộc pool của group**.
- Một HTTP/TCP request scheduler cấp nghiệp vụ: group quản lý I/O/callback, còn parsing, rate limit, database và business requests cần tầng điều phối riêng.
- Một đối tượng `AutoCloseable`: group có `shutdown()`, `shutdownNow()`, `awaitTermination()`, **không** có `close()` theo API Java SE 17.

## 3. Những lớp và mối quan hệ cần nhớ

| API | Vai trò | Cần nhớ |
| --- | --- | --- |
| `AsynchronousChannelGroup` | Chia sẻ cơ chế I/O và thread pool; quản lý shutdown | Có group mặc định và group tạo riêng |
| `AsynchronousServerSocketChannel.open(group)` | Tạo listener gắn với group | Cần `bind(...)` trước `accept` |
| `AsynchronousSocketChannel.open(group)` | Tạo socket client gắn với group | Socket mới chưa connected |
| `AsynchronousServerSocketChannel.accept(...)` | Nhận connection theo Future/handler | Accepted channel **cùng group** với listener |
| `AsynchronousSocketChannel.connect/read/write(...)` | I/O bất đồng bộ của socket | Completion qua Future/handler |
| `CompletionHandler<V,A>` | Tiêu thụ success/failure của operation | Callback chạy trên group pool |
| `AsynchronousChannelProvider` | Provider tạo group và channel | Phải tương thích với group |
| `ThreadFactory` | Tạo pooled threads; tên/daemon/exception policy | Không dùng tên thread làm định danh request |
| `ExecutorService` | Executor có thể được giao cho group | Không shutdown riêng khi group còn sống |
| `ShutdownChannelGroupException` | Không thể bind channel mới vào group đã shutdown | Khác lỗi đóng một channel hiện có |

**Phạm vi của group trong bài:** network asynchronous channels, đặc biệt TCP. `AsynchronousFileChannel` có overload `open(Path, Set, ExecutorService, FileAttribute...)` riêng; không truyền một `AsynchronousChannelGroup` vào `AsynchronousFileChannel.open` như đối với socket. Đừng gom lẫn hai kiểu API vì chúng đều có tiền tố “Asynchronous”.

## 4. Cách tạo group: cố định, co giãn và dùng pool có sẵn

Java SE 17 cung cấp ba factory methods quan trọng:

```java
AsynchronousChannelGroup.withFixedThreadPool(
    int nThreads, ThreadFactory threadFactory);

AsynchronousChannelGroup.withCachedThreadPool(
    ExecutorService executor, int initialSize);

AsynchronousChannelGroup.withThreadPool(
    ExecutorService executor);
```

Đây là **chữ ký rút gọn để đọc API**, không phải code gọi độc lập. Cả ba có thể ném `IOException` khi không khởi tạo được group; một số tham số không hợp lệ có thể ném ngoại lệ như `IllegalArgumentException`.

### 4.1. withFixedThreadPool: giới hạn pooled threads xử lý việc của group

```java
ThreadFactory threads = Executors.defaultThreadFactory();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(2, threads);
```

Đây là snippet Java 17+ **trong phương thức**, cần imports NIO/concurrent và xử lý `IOException`. `2` là số **threads active tối đa để xử lý tác vụ của group tại một thời điểm** theo hợp đồng factory, **không phải** giới hạn 2 sockets và cũng không phải “mỗi socket một thread”.

Với group cố định, hãy chọn kích thước dựa trên tải I/O, callback duration, khả năng mở rộng và benchmark. Callback bị chặn lâu trên cả hai threads có thể trì hoãn handling của nhiều channels khác.

`withFixedThreadPool(0, factory)` không hợp lệ và ném `IllegalArgumentException`.

### 4.2. withCachedThreadPool: executor có thể tạo threads khi cần

```java
ExecutorService executor = Executors.newCachedThreadPool();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withCachedThreadPool(executor, 0);
```

Đây là snippet trong phương thức. `initialSize` có thể được provider dùng như **hint** về số tác vụ ban đầu, không phải giới hạn threads hay số channels. Giá trị âm có nghĩa provider chọn mặc định theo implementation; `0` là hint hợp lệ.

**Điều rất quan trọng:** executor truyền vào đây được thiết kế để group sử dụng **độc quyền**. Khi group termination, group sẽ shutdown executor theo hợp đồng. Tự `executor.shutdown()` khi group còn sống dẫn đến **hành vi không được đặc tả**. Nếu cần chia sẻ executor với business workers, đừng giao nó cho group mà vẫn mong các subsystem khác tự quản lý shutdown.

### 4.3. withThreadPool: executor người dùng cung cấp

```java
ExecutorService executor = Executors.newFixedThreadPool(4);
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(executor);
```

Đây là snippet trong phương thức; nó không làm `executor` trở thành pool “độc lập” mà caller được shutdown tùy ý. Group được phép dùng executor để dispatch completion events và quản lý shutdown của executor khi group termination.

Javadoc Java SE 17 yêu cầu thận trọng khi cấu hình: executor **nên hỗ trợ direct handoff hoặc hàng đợi không giới hạn**; thread gọi `execute` **không được tự chạy task inline ngay tại lời gọi** (*caller-runs executor* là thiết kế không phù hợp ở đây). Provider có thể áp thêm ràng buộc.

**Không tự áp dụng bounded ThreadPoolExecutor với chính sách CallerRunsPolicy** cho group mà không nghiên cứu hợp đồng/provider. Nếu cần backpressure ở tầng business, giới hạn **số requests/bytes đang chờ** ở ứng dụng; đừng làm group pool từ chối những task cần để xử lý I/O completion.

### 4.4. Chọn factory nào?

| Cách tạo | Sở hữu pool | Đặc tính chính | Điều cần tránh |
| --- | --- | --- | --- |
| `withFixedThreadPool(n, factory)` | Group tạo/quản lý pool qua ThreadFactory | Có giới hạn số threads xử lý group tasks | Callback chậm làm nghẽn pool |
| `withCachedThreadPool(executor, initialSize)` | Executor cung cấp ngoài nhưng **dành riêng cho group**, group shutdown | Có thể tạo threads khi cần; initialSize là hint | Shutdown executor từ ngoài |
| `withThreadPool(executor)` | Executor dành riêng cho group, group shutdown | Tùy chỉnh executor phù hợp hợp đồng | CallerRunsPolicy, queue không tương thích, chia sẻ ownership |
| Mặc định, không truyền group | JVM quản lý default group | Không cần tự chọn pool | Coi default group là pool riêng của một service |

Không có lựa chọn duy nhất tối ưu cho mọi ứng dụng. Chọn theo latency, workload, số sockets, callback duration, memory, shutdown semantics và thử nghiệm thực tế.

## 5. Group mặc định (system-wide default group)

Các lời gọi sau dùng **default group**:

```java
AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open();

AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open();
```

Tương đương với gọi overload có group bằng `null`, theo Javadoc:

```java
AsynchronousSocketChannel.open((AsynchronousChannelGroup) null);
AsynchronousServerSocketChannel.open((AsynchronousChannelGroup) null);
```

Đây đều là snippets trong phương thức, phải đóng channel đúng vòng đời. JVM giữ **default group** cho những asynchronous channels không được bind group cụ thể.

### 5.1. Có nên luôn tạo group riêng?

Không bắt buộc. Với chương trình nhỏ, default group đơn giản. Với service cần:

- Chủ động chọn thread factory/đặt tên để dễ quan sát.
- Cô lập khối I/O của một subsystem khác.
- Điều phối shutdown và chờ termination của riêng subsystem.
- Theo dõi số lượng pool threads và callback latency.
- Điều chỉnh số threads theo workload.

... một **group do ứng dụng sở hữu** có thể phù hợp hơn.

Không tạo một group riêng cho **mỗi request**: thread pool và resource setup/teardown tốn chi phí, và lifecycle trở nên khó kiểm soát. Thường tạo group tại ứng dụng/server component rồi bind nhiều channels vào đó.

### 5.2. Các system properties của default group

Java SE 17 nêu các property chuẩn:

- `java.nio.channels.DefaultThreadPool.threadFactory`: tên đầy đủ của class `ThreadFactory` được dùng cho default group; class phải load/khởi tạo được theo quy định của JVM.
- `java.nio.channels.DefaultThreadPool.initialSize`: số nguyên được dùng làm hint `initialSize` cho default group, dựa theo semantics `withCachedThreadPool`.

Nếu thread factory của default group không được cấu hình, các pooled threads của default group là **daemon threads** theo Java SE 17. Đây là kiến thức cấu hình hiện hành, nhưng **không** có nghĩa default pool được bảo đảm đúng N threads hoặc daemon threads là lý do để bỏ qua việc đóng sockets.

Không phụ thuộc property/internal implementation không được chuẩn hóa để tự đoán chính xác callback scheduling. Hai property trên không biến default group thành group custom có thể gọi `shutdown()` thông qua một reference API công khai.

## 6. Bind channel vào group như thế nào?

Để tạo network async channels trong một group:

```java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(
                2, Executors.defaultThreadFactory());

try (AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open(group);
     AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open(group)) {
    // server.bind(...), client.connect(...), accept/read/write...
} finally {
    group.shutdown();
    group.awaitTermination(5, TimeUnit.SECONDS);
}
```

Đây là snippet **trong một phương thức** cần xử lý `IOException` và `InterruptedException`, và có thể phát sinh lỗi I/O/shutdown. Trong code thực, server phải bind, client phải connect trước read/write; nếu `awaitTermination` trả false, cần có chính sách xử lý. Một demo đầy đủ, có callback và kết quả xác định, nằm ở phần 11.

`AsynchronousSocketChannel.open(group)` nhờ **provider đã tạo group** mở channel mới. Nếu group đã shutdown, lời gọi ném `ShutdownChannelGroupException`.

### 6.1. Socket được accept thuộc group nào?

Điểm quan trọng của Javadoc `AsynchronousServerSocketChannel.accept(...)`: một `AsynchronousSocketChannel` do **accept** trả về được bind vào **cùng AsynchronousChannelGroup của listener**.

```text
Group G
  │
  ├── server = AsynchronousServerSocketChannel.open(G)
  │       │
  │       └── accept completes
  │                 │
  │                 └── acceptedSocket ∈ G
  │                        └── read/write completion trên pool G
  │
  └── client = AsynchronousSocketChannel.open(G)
          └── connect completion trên pool G
```

Do vậy callback read/write của accepted socket được dispatch theo group của listener. Đừng giả định phải gọi `AsynchronousSocketChannel.open(G)` thủ công sau khi accept; `accept` đã tạo channel kết nối.

### 6.2. Group không là “client session ID”

Group chỉ quản lý cơ chế shared resources. Nếu cần biết callback thuộc request/session nào, hãy dùng:

- `CompletionHandler` attachment.
- Session object giữ socket, buffers, decoder, outbound queue.
- Connection/request ID ở tầng ứng dụng.
- Log structured fields, tracing context truyền tường minh.

Không dùng `Thread.currentThread().getName()` như ID của một connection. Cùng một pooled thread có thể xử lý callbacks cho **nhiều sockets**, và một socket có thể được callbacks bởi **nhiều pooled threads khác nhau** theo thời gian.

## 7. Bảo đảm chính thức: callback chạy ở thread nào?

Javadoc `AsynchronousChannelGroup` phần **Threading** nêu:

**CompletionHandler của một I/O operation trên channel thuộc group được bảo đảm thực thi bởi một trong các pooled threads của group đó.**

Điều này có nghĩa:

1. Callback **không bắt buộc** chạy trên thread đã gọi `read/accept/connect/write`.
2. Callback có thể chạy trên bất kỳ thread phù hợp nào thuộc group pool.
3. Không có **thread affinity cố định** giữa một connection và một worker.
4. Caller có thể chủ động đặt tên ThreadFactory để nhận diện worker khi log/metrics.
5. Provider có thể sử dụng pooled threads cho việc khác ngoài callback, ví dụ I/O event handling.
6. Java không hứa mọi callback sẽ được chạy đồng thời nếu thread pool đang nghẽn.

### 7.1. Ngoại lệ quan trọng: inline callback trong group pool

Nếu **operation hoàn thành ngay lập tức** và **thread khởi tạo operation vốn đang là một pooled thread của cùng group**, handler **có thể** được gọi trực tiếp ngay trên initiating thread. Điều này vẫn tuân thủ bảo đảm group pool, nhưng có thể làm call stack sâu hơn hoặc gây re-entrancy.

Một provider có thể áp giới hạn số lần handler được kích hoạt inline trên cùng stack nhằm tránh stack overflow. Không dựa vào việc callback luôn async-deferred để giữ giả định “code sau read(...) chạy trước callback”.

### 7.2. Ngoại lệ cho accept hoàn thành ngay

Javadoc `AsynchronousServerSocketChannel.accept(...)` ghi rõ: để cho phép xử lý các kết nối đồng thời, **accept handler không được gọi trực tiếp bởi initiating thread khi accept hoàn thành ngay**. Đây là đặc tả riêng cho accept. Không suy từ quy tắc inline tổng quát rằng mọi operation, kể cả accept, đều có thể inline trên initiating thread.

### 7.3. Tác động của inline execution lên thiết kế

Ví dụ handler read submit read kế tiếp:

```java
@Override
public void completed(Integer n, Session session) {
    if (n < 0) {
        closeSession(session);
        return;
    }
    handleBytes(session, n);
    session.socket.read(session.buffer, session, this);
}
```

Đây là **snippet minh họa**, `Session`, `handleBytes`, `closeSession` thuộc ứng dụng. Với read có thể hoàn tất tức thì và handler inline trên pooled thread, đoạn submit-next-read có thể dẫn tới **tái nhập handler lồng nhau**. JDK có thể giới hạn số tầng, nhưng code tốt vẫn nên tránh tăng stack không kiểm soát, giữ callback ngắn, có state machine và cơ chế điều phối/handoff khi cần.

Không dùng lock không thể tái nhập hoặc assumptions về thứ tự callback không được chứng minh; đặc biệt chú ý việc callback có thể được invoke khi bạn chưa ra khỏi phương thức submit nếu caller là group thread.

## 8. Callback cần làm những gì — và không nên làm những gì?

Một `CompletionHandler` có hai nhánh:

```java
new CompletionHandler<Integer, RequestState>() {
    @Override
    public void completed(Integer bytes, RequestState state) {
        // I/O đã hoàn tất; cập nhật state và chuyển bước tiếp theo.
    }

    @Override
    public void failed(Throwable error, RequestState state) {
        // Báo lỗi, dọn resource và hoàn tất request.
    }
};
```

Đây là mẫu **trong một phương thức**, `RequestState` do ứng dụng định nghĩa, không phải một program compile độc lập.

Callback nên:

- Ghi nhận số byte đọc/ghi, EOF, lỗi và latency.
- Chuyển trạng thái session theo nguyên tắc thread-safe.
- Xử lý dữ liệu nhẹ, có giới hạn.
- Gửi tiếp read/write đúng vòng đời trên socket khi phù hợp.
- Bàn giao công việc CPU nặng, blocking database, HTTP calls hoặc xử lý ảnh sang **executor/tầng business khác**.
- Đảm bảo request có tín hiệu success/failure rõ ràng, không bị treo.
- Giải phóng buffers/leases sau completion và đúng ownership.

Callback không nên:

- `Thread.sleep(...)` để “đợi client gửi tiếp”.
- Gọi `Future.get()` để đợi một operation khác trên cùng pool nếu gây nguy cơ **thread starvation**.
- Chạy một vòng parse/gzip/crypto dài bất tận trên pooled threads.
- Chặn DB/network không giới hạn trong handler.
- Cập nhật UI từ worker thread mà không dispatch.
- Sử dụng mutable collection/session state từ nhiều callbacks không synchronized.
- Giữ lock thời gian dài qua I/O hoặc callback dispatch.
- Nuốt `failed(Throwable, attachment)`, làm logic cho rằng request đã thành công.

### 8.1. Vì sao callback chặn có thể gây tắc nghẽn?

Giả sử group fixed pool có 2 threads, cả hai callbacks đều gọi một HTTP API chậm 30 giây. Trong lúc đó những I/O events/completions của nhiều sockets khác cần worker để dispatch có thể bị trì hoãn. Một group 2 threads **không có nghĩa giới hạn 2 connections**, nhưng nếu **2 threads đều đang bị chặn**, khả năng phục vụ completions mới giảm mạnh.

Thiết kế tốt tách:

```text
Async group threads (I/O/short callbacks)
                    │
          enqueue bounded job
                    │
                    ▼
Business executor (parse/DB/CPU)
                    │
           result / response
                    │
                    ▼
Session outbound queue ─► async write
```

Nếu business queue đầy, phải có **backpressure** như tạm dừng đọc hoặc báo quá tải theo protocol. Không biến group pool thành hàng đợi không giới hạn của mọi công việc nghiệp vụ.

### 8.2. Không phải CompletionHandler có “một thread riêng”

Một completion callback chỉ là **lời gọi mã** được dispatch trên pooled thread. Không tạo riêng một thread cho mỗi completion; không dùng `ThreadLocal` để lưu session mà tin lần callback sau cùng session sẽ chạy cùng worker. Dùng attachment/session object và concurrency controls.

## 9. Future với group pool: đợi ở đâu?

Asynchronous APIs thường có hai dạng:

```java
Future<Integer> pending = socket.read(buffer);
```

hoặc:

```java
socket.read(buffer, attachment, handler);
```

Với `Future`:

- `isDone()` cho biết thao tác đã hoàn thành/hủy, **không** chứng minh success.
- `get()` có thể **chặn caller** cho tới completion.
- `get(timeout, TimeUnit.SECONDS)` giới hạn thời gian chờ caller, **không** tự hủy read.
- Nếu operation lỗi, `get()` ném `ExecutionException` với root cause bên trong.
- Caller bị interrupt khi chờ thì nhận `InterruptedException`.
- `cancel(...)` có semantics hủy Future nhưng không làm TCP bytes trở thành transaction có rollback.

**Đặc biệt:** tránh gọi `Future.get()` từ chính các completion handlers trên group pool nếu nó có thể chờ một operation mà việc dispatch/completion lại cần các worker đó. Dù provider có thể khác nhau, đây là **mẫu rủi ro starvation/deadlock**, nhất là fixed pool nhỏ.

### 9.1. Đợi từ main thread trong chương trình demo có hợp lý không?

Có. Ở phần 11, main thread không phải pooled worker, nên dùng `client.connect(...).get(timeout)` và `client.write(...).get(timeout)` làm các bước đồng bộ cho bài thử. Các callback vẫn được chạy trong group pool. Trong ứng dụng server hiệu năng cao, code có thể dùng handler/async chain và không block thread nhận request.

## 10. Group có thread pool; còn Java Memory Model?

Bảo đảm callback trên group pool **không đồng nghĩa** mọi biến mutable của session tự động an toàn.

Ví dụ hai callbacks có thể cập nhật cùng một `HashMap` hoặc `StringBuilder` từ hai worker. Nếu không có synchronization, đó là data race. Nên dùng:

- `AtomicReference`, `AtomicInteger` cho trạng thái riêng đơn giản.
- `ConcurrentHashMap` hoặc queue thread-safe cho chia sẻ dữ liệu thích hợp.
- `CountDownLatch`, `CompletableFuture` hoặc `BlockingQueue` để handoff kết quả.
- Lock/actor/event-loop để serialize state transitions khi ordering quan trọng.
- Một owner cho inbound buffer và một owner cho outbound queue.

**Sự thật cần nhớ:** completion xảy ra **sau** I/O operation, nên buffer của operation mới có thể được đọc/flip/clear theo hợp đồng. Nhưng nếu một callback chuyển buffer sang thread business khác, phải dùng **safe publication/handoff** phù hợp Java Memory Model. Không dùng boolean thường không volatile rồi busy-loop từ main để chờ callback.

### 10.1. Một socket chỉ một outstanding read/write; group có thể nhiều callbacks

`AsynchronousSocketChannel` cho phép **một read đang chờ và một write đang chờ** trên socket, hai chiều được phép hoạt động đồng thời. Điều này không hứa hai callbacks phải chạy nối tiếp trên cùng thread. Vì vậy một `SessionState` cần phối hợp read/write state, outbound queue, close state đúng concurrency.

### 10.2. ByteBuffer gắn với operation, không gắn vĩnh viễn với worker

Không truy cập hay thay đổi `ByteBuffer` đã đưa vào một asynchronous read/write **trước khi operation hoàn thành**. Kể cả `position()` hoặc `flip()` cũng không được đụng từ thread khác trong lúc provider còn dùng buffer. Sau completed callback, handler có thể xử lý buffer rồi bàn giao cho worker khác có đồng bộ.

`duplicate()` và `slice()` tạo view chia sẻ backing memory; không phải snapshot độc lập của một buffer đang pending.

### 10.3. Attachment là cách mang request identity

```java
socket.read(destination, sessionId,
    new CompletionHandler<Integer, String>() {
        public void completed(Integer n, String id) {
            // id cho biết request/session nào; n là bytes của operation.
        }
        public void failed(Throwable error, String id) {
            // id giúp report lỗi đúng session.
        }
    });
```

Đây là snippet trong phương thức, `sessionId` là String, `destination` là ByteBuffer đã chuẩn bị; socket đã kết nối. Không phụ thuộc `Thread.currentThread().getId()` để suy request identity.

## 11. Chương trình Java 17+ hoàn chỉnh: chứng minh callback chạy trên group pool

Chương trình tạo một custom group với **2 threads được đặt tên** `aio-worker-1`, `aio-worker-2`. Nó tạo listener và client **đều bind vào group**, kết nối qua loopback, submit accept/read bằng CompletionHandler, client gửi một byte ASCII và main đợi kết quả bằng `CountDownLatch`. Khi kết thúc, đóng listener/client/accepted child trước rồi shutdown group.

**Tệp: `GroupCallbackDemo.java`**

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class GroupCallbackDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger workerIds = new AtomicInteger();
        ThreadFactory threads = task -> {
            Thread thread = new Thread(task, "aio-worker-" + workerIds.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        };
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, threads);
        AtomicReference<AsynchronousSocketChannel> peerHolder =
                new AtomicReference<>();
        AtomicReference<Throwable> error = new AtomicReference<>();
        AtomicReference<String> received = new AtomicReference<>();
        AtomicReference<String> acceptThread = new AtomicReference<>();
        AtomicReference<String> readThread = new AtomicReference<>();
        CountDownLatch accepted = new CountDownLatch(1);
        CountDownLatch readDone = new CountDownLatch(1);
        boolean terminated;

        try {
            try (AsynchronousServerSocketChannel server =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(
                                         InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {

                server.accept(null,
                        new CompletionHandler<AsynchronousSocketChannel, Void>() {
                    @Override
                    public void completed(AsynchronousSocketChannel peer, Void ignored) {
                        peerHolder.set(peer);
                        acceptThread.set(Thread.currentThread().getName());
                        ByteBuffer destination = ByteBuffer.allocate(1);
                        peer.read(destination, null, new CompletionHandler<Integer, Void>() {
                            @Override
                            public void completed(Integer count, Void unused) {
                                if (count != 1) {
                                    error.compareAndSet(null,
                                            new IOException("Expected 1 byte, got " + count));
                                } else {
                                    destination.flip();
                                    received.set(String.valueOf(
                                            (char) (destination.get() & 0xff)));
                                }
                                readThread.set(Thread.currentThread().getName());
                                readDone.countDown();
                            }
                            @Override
                            public void failed(Throwable failure, Void unused) {
                                error.compareAndSet(null, failure);
                                readDone.countDown();
                            }
                        });
                        accepted.countDown();
                    }
                    @Override
                    public void failed(Throwable failure, Void ignored) {
                        error.compareAndSet(null, failure);
                        accepted.countDown();
                        readDone.countDown();
                    }
                });

                client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
                if (!accepted.await(5, TimeUnit.SECONDS))
                    throw new IOException("accept timeout");
                if (error.get() != null)
                    throw new IOException("accept failure", error.get());

                ByteBuffer payload = ByteBuffer.wrap(new byte[] { (byte) 'A' });
                int sent = client.write(payload).get(5, TimeUnit.SECONDS);
                if (sent != 1) throw new IOException("send did not complete");

                if (!readDone.await(5, TimeUnit.SECONDS))
                    throw new IOException("read timeout");
                if (error.get() != null)
                    throw new IOException("read failure", error.get());

                System.out.println("accept callback on group worker = " +
                        acceptThread.get().startsWith("aio-worker-"));
                System.out.println("read callback on group worker = " +
                        readThread.get().startsWith("aio-worker-"));
                System.out.println("received = " + received.get());
                System.out.println("listener open before close = " + server.isOpen());
            } finally {
                AsynchronousSocketChannel peer = peerHolder.get();
                if (peer != null) peer.close();
            }
        } finally {
            group.shutdown();
            terminated = group.awaitTermination(5, TimeUnit.SECONDS);
            if (!terminated) {
                group.shutdownNow();
                group.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
        System.out.println("group shutdown = " + group.isShutdown());
        System.out.println("group terminated = " + group.isTerminated());
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 GroupCallbackDemo.java
java GroupCallbackDemo
```

**Stdout thực nghiệm được kiểm thử trên Windows/JDK 24, TCP loopback:**

```text
accept callback on group worker = true
read callback on group worker = true
received = A
listener open before close = true
group shutdown = true
group terminated = true
```

**Giải thích đầu ra:**

1. Hai callbacks ghi lại tên thread đã chạy `completed()`. `startsWith("aio-worker-")` đúng, vì thread factory đặt tên cho pooled threads. Chương trình **không khẳng định** cùng một thread xử lý cả hai callbacks.
2. `received = A` cho biết accepted socket hoàn tất một read byte ASCII và callback mới đọc buffer sau completion.
3. `listener open before close = true` được in **trước khi thoát try-with-resources**. Đây là điều kiện ở vị trí được đo, không phải “listener sẽ luôn mở”.
4. Khi thoát, TWR đóng server/client; khối finally đóng accepted child.
5. Gọi `group.shutdown()`, đợi `awaitTermination` rồi in trạng thái group. Như vậy test không để lại group đang hoạt động.
6. `CountDownLatch` và `AtomicReference` giúp main quan sát dữ liệu các callback mà không dựa vào thứ tự in console của nhiều threads.

**Giới hạn/portability:** chương trình yêu cầu hệ thống cho phép mở TCP loopback và async channel provider tương ứng. Timeouts 5 giây là giới hạn của demo; khi test trên máy rất chậm hoặc chính sách firewall hạn chế, có thể phát sinh ngoại lệ thay vì stdout trên. Group pool bảo đảm callback chạy trên pooled thread; **tên thread và thứ tự scheduling chỉ do chương trình demo tự quy định**, không phải mặc định của Java.

### 11.1. Vì sao không in ngay bên trong callbacks?

Nếu nhiều callbacks in trực tiếp, thứ tự các dòng có thể thay đổi theo scheduling. Ví dụ lưu tên thread/payload vào `AtomicReference` rồi đợi `CountDownLatch` làm đầu ra dễ đọc hơn và kiểm chứng chính xác các điều Java API thật sự bảo đảm.

### 11.2. Vì sao accepted child được đóng riêng?

Accepted child là channel **mới được tạo sau khi accept**, không nằm trong danh sách TWR của `server` và `client`. Phải đóng child đó theo ownership của session khi không còn dùng; đóng listener không phải một lệnh “đóng mọi kết nối đã accept”. Ở demo, `peerHolder` giữ reference cho finally cleanup.

### 11.3. Vì sao dùng callback và Future cùng lúc?

Hai API này bổ sung cho nhau. Main thread gọi `client.connect(...).get(...)` / `write(...).get(...)` để test có thứ tự rõ. Accepted socket đọc bằng CompletionHandler để minh họa callback thật sự chạy trên pooled thread. Không có yêu cầu tất cả operations của cùng một chương trình phải dùng duy nhất một kiểu Future hoặc handler.

## 12. Vòng đời của group: ACTIVE, SHUTDOWN, TERMINATED

Group có ba trạng thái cần phân biệt:

```text
ACTIVE
  ├── channels mới có thể bind vào group
  ├── callbacks/I/O events hoạt động
  └── shutdown() ───────────────────────────► SHUTDOWN
                                              ├── từ chối bind channel mới
                                              ├── channels hiện có có thể vẫn mở
                                              ├── không hủy/interrupt handlers đang chạy
                                              └── khi đóng hết channels, handlers xong,
                                                  giải phóng resource ─► TERMINATED

ACTIVE hoặc SHUTDOWN ── shutdownNow() ─────► SHUTDOWN
                                              └── đóng tất cả open channels,
                                                  đợi handlers đang chạy kết thúc,
                                                  giải phóng resource ─► TERMINATED
```

**Quan trọng:** `isShutdown()` cho biết group đã được đánh dấu shutdown; `isTerminated()` cho biết group **đã kết thúc hoàn toàn**. Hai giá trị này không đồng nghĩa.

### 12.1. shutdown() — dừng nhận channel mới, không tự đóng channel cũ

`group.shutdown()` yêu cầu shutdown **có trật tự** (*orderly*). Nó đánh dấu group đã shutdown, khiến những lần `AsynchronousSocketChannel.open(group)` hoặc `AsynchronousServerSocketChannel.open(group)` sau đó ném `ShutdownChannelGroupException`.

Tuy nhiên, nó **không đóng các channels hiện đã bind**. Group chỉ termination sau khi:

- Mọi asynchronous channels gắn với group đã đóng.
- Mọi completion handlers đang thực thi đã chạy xong.
- Các resource của group đã được giải phóng.

Group cũng **không cố dừng/interrupt** thread đang chạy handler. Nếu handler block vô hạn, group có thể không termination trong thời gian bạn muốn.

### 12.2. shutdownNow() — đóng channels, nhưng không cưỡng bức dừng handler đang chạy

`group.shutdownNow()` thực hiện hành vi shutdown và **gọi close cho tất cả open channels** trong group. Pending I/O có thể thất bại do đóng kênh; ứng dụng cần xử lý lỗi. Nhưng `shutdownNow()` **không** có nghĩa thread handlers đang chạy sẽ bị stop/interrupt ngay.

Nó có thể ném `IOException` khi đóng channels. Sau khi gọi, vẫn cần `awaitTermination(timeout, unit)` nếu muốn chắc đã termination.

### 12.3. awaitTermination() — lời gọi có thể chặn caller

```java
group.shutdown();
boolean done = group.awaitTermination(5, TimeUnit.SECONDS);
if (!done) {
    group.shutdownNow();
}
```

Đây là snippet trong phương thức với imports `TimeUnit`, xử lý `InterruptedException` và `IOException`. `awaitTermination` **đợi** cho tới khi termination, timeout hoặc interruption. Nó không tự kích hoạt shutdown và không tự đóng channels. Nếu chờ hết hạn, trả `false`.

Tham số timeout **0 hoặc âm** của `awaitTermination` có nghĩa **không chờ**, theo Java SE 17. Đừng nhầm với các timeout APIs khác có semantics riêng.

### 12.4. isShutdown() không có nghĩa mọi callback đã kết thúc

Ngay sau `group.shutdown()`:

```java
System.out.println(group.isShutdown());   // true
System.out.println(group.isTerminated()); // Có thể false
```

Đây là snippet trong phương thức. Các callbacks có thể còn đang chạy, channels còn mở, hoặc pool chưa termination. Chỉ khi `isTerminated()` trả true mới xác nhận group đã hoàn thành quá trình giải phóng theo hợp đồng.

### 12.5. shutdownNow() có phải interrupt tất cả worker không?

**Không.** Java SE 17 ghi `shutdownNow()` không cố stop/interrupt threads đang chạy CompletionHandler. Điều này khác với một số kỳ vọng của người quen `ExecutorService.shutdownNow()`; hai APIs không có semantics giống hệt nhau. Code handler phải hợp tác dừng và timeout ở tầng ứng dụng.

## 13. Chương trình Java 17+ hoàn chỉnh: so sánh shutdown và shutdownNow

**Tệp: `GroupShutdownDemo.java`**

```java
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.ShutdownChannelGroupException;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class GroupShutdownDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup graceful =
                AsynchronousChannelGroup.withFixedThreadPool(
                        1, Executors.defaultThreadFactory());

        try (AsynchronousSocketChannel socket =
                     AsynchronousSocketChannel.open(graceful)) {
            graceful.shutdown();
            System.out.println("graceful isShutdown = " + graceful.isShutdown());
            System.out.println("socket stays open = " + socket.isOpen());

            boolean rejected = false;
            try (AsynchronousSocketChannel ignored =
                         AsynchronousSocketChannel.open(graceful)) {
                // Không tới đây vì group đã shutdown.
            } catch (ShutdownChannelGroupException expected) {
                rejected = true;
            }
            System.out.println("new channel rejected = " + rejected);
        } finally {
            graceful.shutdown();
        }

        System.out.println("graceful terminated = " +
                graceful.awaitTermination(5, TimeUnit.SECONDS));

        AsynchronousChannelGroup forced =
                AsynchronousChannelGroup.withFixedThreadPool(
                        1, Executors.defaultThreadFactory());
        AsynchronousSocketChannel another =
                AsynchronousSocketChannel.open(forced);

        try {
            forced.shutdownNow();
            System.out.println("force closes socket = " + !another.isOpen());
            System.out.println("forced terminated = " +
                    forced.awaitTermination(5, TimeUnit.SECONDS));
        } finally {
            another.close();
            forced.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 GroupShutdownDemo.java
java GroupShutdownDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
graceful isShutdown = true
socket stays open = true
new channel rejected = true
graceful terminated = true
force closes socket = true
forced terminated = true
```

**Đọc đúng kết quả:**

- `graceful isShutdown = true`: group nhận lệnh graceful shutdown.
- `socket stays open = true`: sau `shutdown()`, channel **vẫn mở**; đây là ví dụ phản chứng “shutdown đóng hết sockets”.
- `new channel rejected = true`: không được bind channel mới vào group sau shutdown; nhận `ShutdownChannelGroupException`.
- Khi `socket` đóng qua TWR, `awaitTermination(...)` cho group graceful trả true trong thử nghiệm.
- Với group khác, `shutdownNow()` tự đóng `another` và group eventually terminates.

**Giới hạn:** đây là test không có I/O đang pending hoặc handler đang block. Khi có handlers chạy lâu, `awaitTermination(5, SECONDS)` có thể trả false. Đừng kết luận mọi group trong mọi workload chắc kết thúc trong 5 giây từ kết quả demo.

## 14. Ai sở hữu group và pool? Quy tắc tránh resource leak

Một kiến trúc vận hành cần chỉ rõ ba lớp owner:

1. **Group owner**: tạo group, giữ reference, gọi shutdown/awaitTermination khi server dừng.
2. **Channel/session owner**: tạo hoặc accept channel, đóng session khi hoàn tất/lỗi.
3. **Application/business executor owner**: quản lý công việc ngoài I/O callback pool.

Ví dụ tổ chức:

```text
Application
 ├── IoGroupManager
 │    └── AsynchronousChannelGroup
 │         ├── listener(s)
 │         └── client / accepted sessions
 └── BusinessExecutor
      └── parse / validation / database / compute
```

### 14.1. Khi group do service tạo

Một service có group riêng nên:

- Khởi tạo group một lần tại startup.
- Tạo listener/client sử dụng group này.
- Theo dõi accepted channels và pending requests ở tầng app.
- Khi shutdown: ngừng nhận request mới, đóng listener, điều phối đóng sessions, sau đó `group.shutdown()` và `awaitTermination()`.
- Nếu cần forced shutdown, gọi `group.shutdownNow()` và ghi nhận lỗi/unfinished work.

**Không** coi GC sẽ tự shutdown group. Group có threads/resources, cần lifecycle rõ ràng.

### 14.2. Khi truyền ExecutorService vào group

Với `withThreadPool(executor)` hoặc `withCachedThreadPool(executor, initialSize)`, executor đó **dành riêng** cho group. Javadoc nói shutdown group sẽ dẫn tới shutdown executor; tự shutdown executor từ bên ngoài dẫn tới **hành vi không được đặc tả**.

Vì vậy đừng tái dùng chính executor đó để chạy tất cả business jobs rồi gọi `shutdown()` theo yêu cầu của một subsystem khác. Tách pool giữa I/O completion và blocking business để tránh cả ownership conflict lẫn starvation.

### 14.3. Mở group trong try-with-resources được không?

`AsynchronousChannelGroup` không implements `AutoCloseable` như `AsynchronousSocketChannel`. Mẫu:

```java
try (AsynchronousChannelGroup group = ...) {
    // ...
}
```

**không biên dịch** theo Java SE 17. Đây là anti-pattern. Cần `try/finally` với `shutdown/awaitTermination`, còn từng channel có thể dùng TWR vì chúng là Closeable.

### 14.4. Đóng listener có tự đóng accepted clients?

Không. Listener và accepted connections là **các channels khác nhau**, dù cùng group. Đóng listener không tự động đóng mọi accepted child. Bạn cần quản lý sessions; `shutdownNow()` ở cấp group mới đóng tất cả open channels theo hợp đồng.

## 15. Shutdown server: trình tự khuyến nghị

Đối với một TCP server có group riêng:

1. Đánh dấu **stopping** trong application state, ngừng nhận logical business requests mới.
2. Đóng listener hoặc không submit accept kế tiếp. Với accept đang chờ, đóng listener giúp operation thất bại được báo qua handler.
3. Phối hợp session owners xử lý các requests đã được chấp nhận: hoàn tất hoặc fail theo deadline.
4. Không để callback submit thêm công việc vô hạn khi shutdown đã bắt đầu.
5. Đóng accepted sockets/outbound sockets sau khi yêu cầu/ACK theo protocol đã kết thúc hoặc vượt deadline.
6. Gọi `group.shutdown()` sau khi phù hợp, ngăn bind channels mới vào group.
7. Gọi `group.awaitTermination(timeout, unit)` từ **một thread quản lý shutdown**, không block completion handler của chính group.
8. Nếu timeout và ứng dụng cần buộc dừng, gọi `group.shutdownNow()`; nó đóng open channels nhưng **không bảo đảm interrupt handler đang chạy**.
9. Kiểm tra `group.isTerminated()`, ghi metric/log, giải phóng business resources theo dependency order.

Đây là một chính sách tham khảo; thứ tự giữa bước đóng listener và group.shutdown có thể điều chỉnh theo protocol, nhưng phải tránh tạo channels mới sau shutdown và không chặn các pooled threads đang cần hoàn tất callbacks.

### 15.1. Vì sao không gọi awaitTermination bên trong CompletionHandler?

Nếu group có một pooled thread và handler đó gọi `awaitTermination(60, SECONDS)`, chính handler đang chạy là một điều kiện khiến group **chưa thể termination**. Nó có thể chờ tới timeout của chính nó, gây stall. Hãy điều phối shutdown từ management thread hoặc tầng lifecycle riêng.

### 15.2. Nếu shutdown gây lỗi của I/O đang pending

Khi channel bị đóng trong lúc có outstanding read/write, Future/callback có thể nhận lỗi như `AsynchronousCloseException`. Đây có thể là **kết quả mong đợi của shutdown chủ động**, không nên log thành lỗi hỏng storage nghiêm trọng nếu đã có trạng thái stopping. Tuy nhiên vẫn cần hoàn tất/fail request nghiệp vụ, giải phóng buffers và không bỏ qua mọi exception.

### 15.3. Không thể dùng nhóm như một durable request queue

`AsynchronousChannelGroup` không lưu lại requests qua tiến trình crash, không đảm bảo exactly-once business processing, không thay database/queue và không cho rollback TCP writes. Nếu cần giao nhận tin cậy, tầng application phải có message IDs, ACK, retry/idempotency, persistence và recovery riêng.

## 16. Khi nào CompletionHandler được gọi trực tiếp?

Tình huống cụ thể:

```text
Pool worker W đang chạy callback của connection X
           │
           └── W gọi socket.read(..., nextHandler)
                         │
                   I/O hoàn thành ngay
                         │
               provider có thể gọi nextHandler
               trực tiếp ngay trên W trước khi read() trả về
```

Đây là **khả năng được API cho phép**, không phải cam kết mọi read sẽ inline. Nếu initiating thread **không thuộc group pool**, hợp đồng bảo đảm handler chạy trên pooled thread; provider không được tùy tiện dispatch callback trên một thread ngoài pool.

### 16.1. Re-entrancy làm hỏng những assumption nào?

- “Callback không thể chạy khi tôi còn giữ lock quanh submit.”
- “Tôi có thời gian cập nhật shared state sau khi gọi read.”
- “Thread id của callback khác thread gọi read.”
- “Handler chỉ gọi sau khi method submit đã return.”
- “Callback recursion luôn được triển khai bằng queue, không bao giờ inline.”

Vì vậy state machine phải cập nhật **trạng thái pending/buffer ownership trước khi submit** (theo synchronization phù hợp) và có logic rollback khi submit ném synchronous exception.

### 16.2. Khi handler submit handler kế tiếp

Một reader nhiều messages thường dùng:

```java
@Override
public void completed(Integer n, Session session) {
    if (n < 0) {
        closeSession(session);
        return;
    }
    parseAvailableBytes(session, n);
    if (session.shouldReadAgain()) {
        session.prepareNextBuffer();
        session.socket.read(session.buffer, session, this);
    }
}
```

Đây là snippet minh họa trong CompletionHandler của ứng dụng. Nếu operation mới hoàn thành tức thì và callback được inline, call stack có thể nối nhiều handler calls. Provider có thể giới hạn số tầng, nhưng code không nên dựa vào giới hạn ẩn để quản lý re-entrancy hoặc stack depth.

Trong hệ thống phức tạp, cân nhắc phân việc parser/next-read theo event queue/serial executor, giữ callback ngắn và tránh recursion nghiệp vụ không giới hạn.

## 17. Tối ưu thread pool mà không phá hợp đồng

### 17.1. Đừng chọn số threads bằng số connections

Một group có 2 threads có thể phục vụ nhiều hơn 2 sockets đang chờ network events; sockets **không chiếm riêng** một worker khi idle. Nhưng nếu mọi callback dài, số pooled threads trở thành điểm nghẽn. Benchmark theo loại traffic:

- Connections chủ yếu idle.
- Rất nhiều short completions.
- Large payload và parsing lâu.
- Slow clients, bursts, file/DB calls.
- TLS/user-space crypto (nếu sử dụng tầng trên NIO.2).
- Shutdown latency, callback queue wait.

### 17.2. Quan sát điều gì?

- Callback latency: thời gian từ lúc operation có thể hoàn tất đến khi business xử lý (không nên coi đây là thước đo tuyệt đối ở cấp kernel).
- Request end-to-end latency và p95/p99.
- Active connections, pending read/write, error/timeout counts.
- Thời gian handler chạy, số handler đang xử lý.
- Số jobs/bytes trong business queue.
- Group threads CPU usage và throughput.
- Thời gian từ shutdown tới termination.

Không dùng chỉ tên thread để suy đúng một request hoặc số connections.

### 17.3. Deadlock/starvation thường gặp

Ví dụ group fixed pool có 1 thread:

```text
pool worker:
   handler A chạy
      └── chờ Future B.get()
                 │
                 └── completion B cần pool worker để dispatch
                                (không còn thread rảnh)
```

Đây là **một khả năng starvation/deadlock** tùy provider và design, không phải lịch trình cố định của mọi OS. Giải pháp: không chờ operation khác ở group callback; dùng composition, callbacks, hoặc chuyển blocking wait sang executor riêng.

### 17.4. ThreadFactory đặt tên và daemon policy

ThreadFactory có thể đặt tên, daemon flag và `UncaughtExceptionHandler`:

```java
AtomicInteger index = new AtomicInteger();
ThreadFactory factory = task -> {
    Thread worker = new Thread(task, "network-callback-" + index.incrementAndGet());
    worker.setDaemon(true);
    return worker;
};
```

Đây là snippet Java 17+ với imports `AtomicInteger` và `ThreadFactory`. Trong production, cân nhắc lifecycle và observability. Daemon threads không thay thế clean shutdown; process exit đột ngột có thể làm requests dở dang.

### 17.5. Security/permissions và provider constraints

Group được tạo bởi system-wide default `AsynchronousChannelProvider` trong các factory chuẩn. Các socket channels bind vào group được tạo qua **provider của group**. Không giả định một custom provider hoặc môi trường runtime đặc thù hỗ trợ chính xác same thread scheduling/performance như JDK default trên Windows/Linux. Javadoc là hợp đồng portability; tune theo môi trường deploy.

## 18. Sự khác nhau giữa nhóm mạng async và executor file async

Dễ nhầm khi thấy hai API cùng dùng thread pool:

**Network async:**

```java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(2, factory);
AsynchronousSocketChannel socket = AsynchronousSocketChannel.open(group);
```

**File async:**

```java
ExecutorService filePool = Executors.newFixedThreadPool(4);
AsynchronousFileChannel file = AsynchronousFileChannel.open(
        path, Set.of(StandardOpenOption.READ), filePool);
```

Đây là **hai snippets trong phương thức**, cần owner đóng channel và shutdown group/executor đúng lifecycle. `AsynchronousFileChannel` gắn với ExecutorService để xử lý I/O events/completions theo API riêng, **không có overload nhận AsynchronousChannelGroup**.

Đừng truyền nhầm `AsynchronousChannelGroup` cho file API hoặc cho rằng `shutdownNow` của network group đóng `AsynchronousFileChannel` được mở độc lập bằng file executor. Mỗi subsystem cần owner và dependency graph riêng.

## 19. Những ngoại lệ quan trọng

| Ngữ cảnh | Ngoại lệ/trạng thái | Ý nghĩa |
| --- | --- | --- |
| `withFixedThreadPool(0, ...)` | `IllegalArgumentException` | nThreads phải dương |
| Group factory có lỗi I/O | `IOException` | Không tạo được group |
| `AsynchronousSocketChannel.open(group)` sau shutdown | `ShutdownChannelGroupException` | Group đã từ chối bind channel mới |
| `AsynchronousServerSocketChannel.open(group)` sau shutdown | `ShutdownChannelGroupException` | Tương tự cho listener |
| Socket chưa connected mà read/write | `NotYetConnectedException` | Cần connect completion |
| Accept mới khi accept cũ pending | `AcceptPendingException` | Một outstanding accept trên listener |
| Read thứ hai khi read cũ pending | `ReadPendingException` | Một outstanding read trên socket |
| Write thứ hai khi write cũ pending | `WritePendingException` | Một outstanding write trên socket |
| Operation async thất bại | `CompletionHandler.failed(Throwable, attachment)` | Trả lỗi tới session/request owner |
| `Future.get()` khi operation lỗi | `ExecutionException` | Lỗi thật nằm trong cause |
| `Future.get(timeout)` | `TimeoutException` | Caller hết thời gian chờ, operation có thể pending |
| Thread chờ bị interrupt | `InterruptedException` | Theo interrupt policy |
| `shutdownNow()` không đóng được một resource | `IOException` | Không tự giả định mọi channels đã clean |
| Group chưa termination khi await timeout | `awaitTermination() == false` | Cần shutdown policy/metrics |
| Đóng channel khi I/O đang pending | `AsynchronousCloseException`/lỗi liên quan | Fail pending I/O có thể là shutdown bình thường |

**Không** bắt tất cả ngoại lệ rồi coi lỗi do một socket trùng với lỗi group shutdown. `ShutdownChannelGroupException` là điều kiện **vòng đời group**; `ReadPendingException` là điều kiện **điều phối read** của một channel; `ExecutionException` là wrapper của lỗi **asynchronous operation**.

### 19.1. Xử lý InterruptedException khi chờ termination

```java
try {
    boolean finished = group.awaitTermination(5, TimeUnit.SECONDS);
    if (!finished) {
        group.shutdownNow();
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Bàn giao shutdown policy cho tầng quản lý.
}
```

Đây là snippet có `AsynchronousChannelGroup group`, có thể ném IOException từ shutdownNow; cần xử lý ở method signature hoặc catch. Thread đang đợi termination bị interrupt không có nghĩa group tự kết thúc, và không nên nuốt interrupt rồi báo success.

## 20. Các điều kiện cạnh tranh khi start/stop

### 20.1. Một request đang chuẩn bị tạo socket khi group.shutdown

Thread A chuẩn bị:

```java
AsynchronousSocketChannel.open(group);
```

cùng lúc Thread B gọi `group.shutdown()`. Tùy thứ tự thực tế, việc mở channel có thể thành công trước shutdown hoặc bị từ chối. Ứng dụng cần bắt `ShutdownChannelGroupException` và trả lỗi rõ ràng cho request mới, thay vì retry tạo sockets liên tục trên group đã shutdown.

### 20.2. Callback nhận accepted connection khi shutdown vừa bắt đầu

Một accept callback có thể tới khi app đang stopping. Nếu `sessionManager.isStopping()` đã true, nên đóng child socket mới và không bắt đầu business request dài. Đừng nhầm “listener.accept callback thành công” với “server nhất định phải phục vụ request mới dù hệ thống đang shutdown”.

### 20.3. Callback submit async operation khi socket vừa đóng

`socket.isOpen()` có thể true tại thời điểm kiểm tra nhưng channel bị đóng trước lệnh `read/write`. Đây là TOCTOU race; bắt ngoại lệ đồng bộ và xử lý lỗi completion bất đồng bộ theo session state. Không dựa vào một boolean không khóa để bảo đảm I/O luôn thành công.

### 20.4. Pool executor bị shutdown từ bên ngoài

Với `withThreadPool` hoặc `withCachedThreadPool`, gọi `executor.shutdown()` độc lập khi group vẫn mở là **hành vi không được định nghĩa**. Đừng “sửa” bằng cách bắt `RejectedExecutionException` rồi tiếp tục submit read; ownership của group phải được giải quyết.

## 21. Kiểm thử đúng các guarantees của callback threading

Một bộ test chất lượng nên tách:

**A. Hợp đồng API có thể xác minh:**

- Group do factory tạo có thể bind socket/listener.
- Accepted child cùng group theo Javadoc.
- Handler của I/O được chạy trên **pooled group thread**, không cần cùng thread qua các callbacks.
- Group shutdown từ chối bind channels mới.
- Graceful shutdown **không tự đóng** channel đang mở.
- Group termination chỉ sau khi channels đóng và handlers đang chạy hoàn thành.
- shutdownNow đóng các open channels, không bảo đảm interrupt handlers.
- Thread count của fixed pool là giới hạn active tasks, **không phải max connections**.
- Future và callback đều là cách nhận completion hợp lệ.

**B. Điều không nên hard-code trong portable tests:**

- Callback A luôn chạy trên thread số 1.
- Callback A luôn chạy trước callback B trên các connections khác.
- Callback luôn chạy trên thread khác initiating thread.
- Handler luôn được dispatch về sau, không inline.
- Một accepted socket always dùng cùng worker cho cả read/write.
- Khi `shutdown()` được gọi thì group termination ngay.
- Mọi callbacks nhất thiết chạy trong 10 ms.
- Thread pool mặc định có đúng một số threads cố định trên mọi JDK/provider.
- Kiểu scheduling trên Windows bằng với mọi Linux/macOS/custom provider.

**C. Các tình huống lỗi nên mô phỏng:**

- Handler block và group termination vượt timeout.
- Callback throws exception, làm request thiếu error handoff.
- Business queue quá tải.
- Accepted child chưa được close.
- Group bị shutdown giữa lúc tạo client mới.
- Callback được gọi trong lúc đang bắt đầu stopping.
- Thread interrupted trong awaitTermination.
- Pending read bị lỗi vì socket closed.
- Executor custom bị shutdown sai owner.
- ThreadFactory có lỗi tạo worker hoặc đặt tên trùng/không hữu ích.
- Nguy cơ recursion/re-entrancy do inline completion.

## 22. Những lỗi phổ biến và cách sửa

**1. “Mỗi connection được cấp một thread riêng trong group.”** Sai. Nhiều sockets chia sẻ pooled threads để xử lý I/O/completions.

**2. “Group fixed pool 2 threads chỉ cho phép 2 sockets.”** Sai. Số channels không được định nghĩa bằng nThreads.

**3. “Callback luôn chạy trên thread gọi read.”** Sai; handler được chạy trên **thread thuộc group pool**.

**4. “Mỗi socket luôn có một worker thread cố định.”** Không có thread-affinity guarantee.

**5. “Callback luôn chạy trên một thread khác.”** Sai; nếu initiating thread là pooled worker và operation hoàn thành ngay, callback có thể inline, trừ operation có quy tắc riêng.

**6. “Accept completion callback cũng có thể inline trên initiating thread ngay tức thì.”** Javadoc `accept` đặc biệt **ngăn điều này** khi accept completed immediately.

**7. “ThreadFactory chỉ thay đổi tên thread, không liên quan runtime.”** Nó có thể ảnh hưởng daemon/priority/exception handling; cần thiết kế có ý thức.

**8. “withCachedThreadPool initialSize là số threads tối đa.”** Sai; initialSize chỉ là hint ban đầu.

**9. “withThreadPool có thể dùng chung executor với business code rồi bên nào cũng shutdown.”** Sai, executor được dành riêng cho group và group quản lý shutdown.

**10. “CallerRunsPolicy luôn tương thích với group.”** Không; Javadoc khuyến cáo không để thread gọi execute trực tiếp chạy task.

**11. “AsynchronousChannelGroup có close(), dùng try-with-resources là được.”** Sai theo Java SE 17; dùng `shutdown/awaitTermination`.

**12. “group.shutdown() đóng hết sockets.”** Sai, đây là orderly shutdown, vẫn giữ channels hiện có.

**13. “group.isShutdown() == true là đã giải phóng hết threads.”** Sai; cần `isTerminated()`.

**14. “shutdownNow chắc chắn interrupt CompletionHandler đang chạy.”** Sai; docs nói không cố interrupt handlers.

**15. “awaitTermination tự shutdown group.”** Sai; cần gọi shutdown trước.

**16. “awaitTermination timeout nghĩa tất cả channels đã đóng.”** Sai; timeout trả false, cần policy tiếp.

**17. “Đóng listener là đã đóng tất cả accepted sockets.”** Sai; child là channels riêng.

**18. “Có thể gọi Future.get() dài trong mọi handler mà không ảnh hưởng server.”** Nguy cơ chặn pooled threads, starvation.

**19. “Một callback lỗi bị nuốt không sao, I/O thread tiếp tục.”** Request có thể bị treo, mất resource, khó debug; phải propagate lỗi.

**20. “ThreadLocal là nơi tốt để lưu session qua nhiều callbacks.”** Sai; callback cùng socket có thể tới pooled threads khác nhau.

**21. “ByteBuffer an toàn để sửa ngay sau khi gọi read vì API là asynchronous.”** Sai; phải đợi completion.

**22. “CompletionHandler.completed nghĩa đã xử lý xong message TCP.”** Sai, nó chỉ báo I/O operation hoàn tất một số bytes; protocol cần framing.

**23. “AsynchronousFileChannel cũng bind vào AsynchronousChannelGroup.”** Sai; file API nhận ExecutorService riêng.

**24. “Group mặc định có thể tùy ý shutdown bằng một reference từ API.”** API không cấp công cụ public trực tiếp tương đương custom group factory cho default group.

**25. “Tạo một group cho mỗi HTTP request là mô hình scale tốt.”** Thường sai; group là tài nguyên chia sẻ để phục vụ nhiều channels.

**26. “Không cần quản lý lifecycle vì pooled daemon threads tự hết.”** Sai; cần đóng sockets, shutdown và xử lý pending work.

**27. “shutdownNow làm business request idempotent.”** Không; close socket không thay durable ACK/protocol.

**28. “Có thể so sánh log thread name để biết đúng request đã hoàn thành.”** Không; cần request/session ID trong attachment.

## 23. Checklist review ứng dụng dùng AsynchronousChannelGroup

- [ ] Có xác định **group owner** và session/channel owners?
- [ ] Channel mở bằng `open(group)` và group có tồn tại/chưa shutdown?
- [ ] Listener được bind, accepted child được đóng riêng khi hoàn tất?
- [ ] Không trộn default group với custom group nếu đang kỳ vọng một pool duy nhất?
- [ ] Đã xác định thread factory, kích thước pool và policy daemon khi cần?
- [ ] Đã hiểu `nThreads` không phải số connections tối đa?
- [ ] Callback có chạy ngắn, không sleep/block DB/Future.get trong group pool?
- [ ] Có executor riêng cho CPU-intensive/business blocking tasks?
- [ ] Có backpressure và bounded business queue để tránh overload?
- [ ] Có dùng attachment/session ID thay vì ThreadLocal hoặc thread name làm request identity?
- [ ] Có biết callback có thể inline nếu initiating thread là pooled thread?
- [ ] Không giữ lock gây re-entrancy/deadlock khi submit async operations?
- [ ] Có xử lý `completed`, `failed` và exception ném đồng bộ khi submit?
- [ ] Đã đồng bộ shared mutable state giữa callbacks và worker threads?
- [ ] ByteBuffer không bị caller sửa khi I/O pending?
- [ ] Không để nhiều reads/writes pending vượt giới hạn mỗi socket?
- [ ] Nếu dùng custom executor, nó có dành riêng cho group?
- [ ] Có tránh gọi `executor.shutdown()` bên ngoài group?
- [ ] Với `withThreadPool`, executor có chính sách queue/handoff tương thích?
- [ ] Có xử lý `ShutdownChannelGroupException` khi nhóm dừng nhận channels?
- [ ] Có phân biệt `shutdown()`, `shutdownNow()` và `awaitTermination()`?
- [ ] Có bảo đảm graceful shutdown vẫn đóng từng socket trước khi đợi group termination?
- [ ] Có deadline và fallback khi `awaitTermination()` trả false?
- [ ] Có biết `shutdownNow()` không interrupt handlers đang chạy?
- [ ] Có đưa logic chờ termination ra khỏi callback threads?
- [ ] Có metrics group lifecycle, callback latency, worker pool và active connections?
- [ ] Có test trong môi trường Java 17+ và provider/OS cần deploy?
- [ ] Có báo lỗi/cancel/retry ở tầng protocol thay vì tin rằng close socket = durable rollback?

## 24. Câu hỏi tự kiểm tra

**1.** `AsynchronousChannelGroup` dùng để làm gì? — Gom các asynchronous network channels để **chia sẻ I/O handling và completion thread pool**, có vòng đời shutdown.

**2.** Nó có nhất thiết lưu danh sách public mọi socket không? — Không, đây không phải API collection quản lý sessions.

**3.** Một group fixed pool 2 threads có bị giới hạn 2 TCP sockets không? — Không.

**4.** Handler completion được chạy ở đâu? — Trên **một thread thuộc pooled threads của group**.

**5.** Callback có bắt buộc chạy trên initiating thread không? — Không.

**6.** Một socket có bảo đảm mọi callback cùng thread không? — Không.

**7.** Callback có thể inline khi nào? — Khi I/O hoàn tất ngay và initiating thread vốn thuộc group pool, ngoại trừ operation có quy tắc riêng.

**8.** Accept callback có thể được gọi trực tiếp từ initiating thread khi accept ngay không? — Không theo quy tắc riêng của AsynchronousServerSocketChannel.accept.

**9.** Accepted child thuộc group nào? — Cùng group với listener.

**10.** `AsynchronousSocketChannel.open()` không truyền group dùng group nào? — System-wide default group.

**11.** Default group có hệ thống thread pool không? — Có, cấu hình được một số property theo Java SE 17.

**12.** Pooled threads mặc định của default group có daemon khi không cấu hình ThreadFactory không? — Có.

**13.** `withFixedThreadPool(n, factory)` có yêu cầu n > 0 không? — Có.

**14.** `withCachedThreadPool(executor, initialSize)` có coi initialSize là max threads không? — Không; là hint.

**15.** Executor truyền vào `withThreadPool` có dùng chung/shutdown tùy ý được không? — Không; dành riêng cho group, group owns shutdown.

**16.** `AsynchronousChannelGroup` có implement AutoCloseable không? — Không theo Java SE 17.

**17.** `shutdown()` có tự đóng active channels không? — Không.

**18.** `shutdown()` có từ chối bind channels mới không? — Có, gây ShutdownChannelGroupException.

**19.** Khi nào `isTerminated()` true? — Khi mọi channels đã đóng, handlers đang chạy đã kết thúc và resources được giải phóng.

**20.** `shutdownNow()` làm gì thêm? — Đóng tất cả open channels trong group.

**21.** `shutdownNow()` có cố interrupt CompletionHandler đang chạy không? — Không.

**22.** `awaitTermination()` có thể block không? — Có.

**23.** `awaitTermination(timeout)==false` nghĩa là gì? — Chưa termination trước timeout, cần policy xử lý.

**24.** Gọi `Future.get()` ngay trong handler có rủi ro gì? — Chặn pooled thread, có thể gây starvation khi pool nhỏ.

**25.** Đọc/ghi file qua `AsynchronousFileChannel` có bind AsynchronousChannelGroup không? — Không; file API có executor riêng.

**26.** Dùng ThreadLocal làm session data qua callbacks có an toàn không? — Không bảo đảm cùng worker; dùng session/attachment.

**27.** Khi shutdown server, có phải đóng accepted child không? — Có, quản lý session riêng.

**28.** Group callback pool thay cho mọi business tasks được không? — Không nên cho workload blocking/CPU nặng; tách pool và backpressure.

**29.** Biết callback thread name có đủ xác định request không? — Không; cần request ID/attachment.

**30.** Vì sao mã demo dùng CountDownLatch/AtomicReference? — Chờ callback hoàn tất và truyền kết quả từ pooled threads về main một cách thread-safe.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 — AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): group factories, thread pool, default group, threading/inline callback, graceful/forced shutdown, awaitTermination.
- [Java SE 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): open(group), connect/read/write, I/O completion và error handling.
- [Java SE 17 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): open(group), accepted child same group, accept callback threading, single pending accept.
- [Java SE 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed và attachment.
- [Java SE 17 — AsynchronousChannelProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/spi/AsynchronousChannelProvider.html): provider tạo group/channels.
- [Java SE 17 — ShutdownChannelGroupException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ShutdownChannelGroupException.html): không bind channel mới sau group shutdown.
- [Java SE 17 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): khác biệt executor file so với group network.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, timeout, cancel, completion.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown/termination semantics ở tầng executor.
- [Java SE 17 — ThreadFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html): tạo/naming threads.

**Tóm tắt cốt lõi:** `AsynchronousChannelGroup` chia sẻ I/O event handling và **pooled callback threads** cho nhiều asynchronous network channels. Callback được bảo đảm chạy trong **pool của group**, nhưng **không có thread affinity**; nếu initiating thread là group worker và operation xong ngay thì callback có thể **inline** (với quy tắc riêng cho accept). `shutdown()` chỉ từ chối bind channel mới; nó **không tự đóng** channels hiện có. `shutdownNow()` đóng open channels nhưng **không cố interrupt handlers**. Muốn sạch tài nguyên, ứng dụng phải **đóng session channels, shutdown group, đợi termination**, quản lý executor ownership và giữ handlers ngắn gọn, thread-safe.