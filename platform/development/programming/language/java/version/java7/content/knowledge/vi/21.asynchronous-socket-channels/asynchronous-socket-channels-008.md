# Tránh chặn callback hoặc tạo vòng chờ lẫn nhau trong Java NIO.2

**Chủ đề:** Java 7 — Kênh mạng bất đồng bộ  
**Bài học:** Tránh chặn callback hoặc tạo vòng chờ lẫn nhau  
**Môi trường:** Java 17+ với `AsynchronousSocketChannel`, `AsynchronousServerSocketChannel`, `AsynchronousChannelGroup`, `CompletionHandler`, `Future`, `CompletableFuture` và `java.util.concurrent`. Những API bất đồng bộ của NIO.2 được giới thiệu từ Java 7 và **vẫn là API Java hiện hành**. Các ví dụ TCP sử dụng loopback cùng port do hệ điều hành cấp để không phụ thuộc server bên ngoài.

## 1. Tình huống dễ gặp: callback không chạy tiếp vì chính nó đang chờ

Giả sử ứng dụng nhận dữ liệu qua `AsynchronousSocketChannel`:

1. Một thao tác `read` hoàn tất; runtime gọi `CompletionHandler.completed`.
2. Callback bắt đầu đọc header, parse message hoặc tạo một I/O mới.
3. Để đơn giản hóa, lập trình viên gọi `future.get()`, `join()`, `CountDownLatch.await()` hoặc đợi một tác vụ khác **ngay trong callback**.
4. Tác vụ mà callback đang chờ chỉ được chạy hoặc chỉ có thể thông báo kết quả nhờ một thread trong **chính nhóm xử lý completion** hiện đang bị chiếm.
5. Khi mọi thread có khả năng hoàn tất điều kiện đã bị chặn, hệ thống **không còn đường tiến**: deadlock hoặc thread-pool starvation; connection có thể timeout, backlog tăng và ứng dụng ngừng đáp ứng.

**Chủ đề của bài:** giữ completion handlers **nhanh, không chặn vì dependency có thể phụ thuộc chính nhóm threads**, chuyển công việc dài sang nơi thích hợp, nối tiếp tác vụ bằng completion callbacks/`CompletionStage` thay vì chờ đồng bộ bên trong callback, và tổ chức state machine sao cho không có **vòng chờ lẫn nhau**.

**Không hiểu thành “mọi lời gọi chặn trong callback đều chắc chắn deadlock”.** Một phép gọi rất ngắn, không chờ resource mà completion group cần, có thể hoàn tất; nhưng nó vẫn chiếm thread quý giá và có thể tạo tail latency. Deadlock cần một **chu trình phụ thuộc** hoặc tài nguyên cần thiết không còn thread để tiến. Thread starvation có thể xảy ra khi đủ nhiều callbacks bị chặn dù chu trình không hiển thị trực tiếp trong code.

### 1.1. Đọc lại vai trò của các API

| API | Công dụng | Nguy cơ nếu dùng sai trong callback |
| --- | --- | --- |
| `CompletionHandler.completed/failed` | Tiêu thụ kết quả thao tác I/O | Block lâu làm nghẽn thread dispatch completion |
| `AsynchronousChannelGroup` | Nhóm channels chia sẻ thread/resources để xử lý completions | Cả nhóm bị chiếm, không còn threads cho những I/O khác |
| `Future.get()` | Chờ I/O hoặc tác vụ hoàn tất | Chặn thread callback; có thể chờ kết quả cần chính group |
| `CompletableFuture.join()` | Chờ kết quả hoặc ném `CompletionException` | Vẫn là blocking wait, không “tự async” vì tên Future |
| `CompletableFuture.thenCompose` | Nối một bước bất đồng bộ với bước bất đồng bộ khác | Tránh trực tiếp `get` cho dependency; vẫn phải chọn executor hợp lý |
| `ExecutorService.execute/submit` | Chuyển công việc sang worker khác | Nếu queue/pool không giới hạn: backlog; nếu reject không xử lý: mất request |
| `CountDownLatch.await` | Đợi một tín hiệu | Dễ tạo vòng chờ khi tín hiệu do callback cùng group phát |
| `Future.get(timeout)` | Chặn có deadline | Không giải quyết kiến trúc phụ thuộc; timeout không tự cancel I/O |
| `AsynchronousSocketChannel.read/write` | Khởi động I/O | Chỉ một pending read và một pending write trên một channel |

**Quy tắc ngắn:** trong handler, hãy **ghi nhận result, cập nhật state ngắn, khởi động bước tiếp theo hoặc enqueue công việc có giới hạn rồi trả về**. Đừng đồng bộ đợi một bước có thể cần completion threads hiện đang chạy callback.

## 2. AsynchronousChannelGroup chạy callback trên thread nào?

Theo contract của `AsynchronousChannelGroup`, completion handlers cho các channel liên kết với group được thực thi bởi **các thread thuộc group**. Với I/O hoàn tất ngay, một completion handler **có thể** được gọi trực tiếp trên thread khởi tạo nếu thread đó đã thuộc chính group. Điều này quan trọng vì:

- Callback có thể **không chạy trên thread main**, và không cần một thread mới cho mỗi operation.
- Một group có số threads giới hạn là **tài nguyên chia sẻ** giữa nhiều connections.
- Handler chặn lâu làm giảm khả năng dispatch completions mới.
- Lập trình viên không được giả định callback luôn chạy “sau khi lời gọi read/write đã trả về” hoặc luôn trên một thread riêng.
- Nếu liên tục khởi tạo thao tác có thể hoàn tất ngay từ bên trong callback, implementation có thể gọi các handlers theo chuỗi trực tiếp; cần tránh tạo **đệ quy vô hạn** hoặc tăng stack không kiểm soát.

Mỗi provider/JDK/OS có thể có cách dispatch khác nhau. **Không dựa vào tên thread, số threads, thứ tự callback hoặc thời gian vài mili giây** như một phần của protocol.

### 2.1. Nhóm 1 thread và một callback gọi get()

```text
Group thread G (duy nhất)
  |
  |-- callback A nhận hoàn tất của read
  |       |
  |       +-- schedule completion của thao tác B lên group G
  |       +-- gọi futureB.get()   <------ block G
  |
  +-- callback B cần G chạy ----> KHÔNG CÒN THREAD RẢNH
                                      |
                                      +-- B không tiến để A thức dậy
```

Trong kịch bản trên, **A chờ B, B chờ thread mà A đang giữ**. Nếu không có thread khác hoặc cơ chế completion khác có khả năng thực hiện B, đó là một vòng chờ.

**Đây là mô hình lỗi có thể xảy ra, không phải bảo đảm rằng mọi cách sử dụng `AsynchronousChannelGroup.withFixedThreadPool(1)` sẽ tự sinh deadlock.** Chi tiết I/O/providing completion có thể khác giữa providers; bài test deterministic dùng executor một thread để chứng minh đúng quan hệ phụ thuộc, thay vì cố khóa chương trình mạng thật.

### 2.2. Starvation khác deadlock như thế nào?

**Deadlock:** các tác vụ giữ hoặc chiếm tài nguyên cần thiết và chờ lẫn nhau trong một chu trình; không ai có thể tiến mà không có tác nhân bên ngoài phá chu trình.

**Thread-pool starvation:** nhiều callbacks cùng chiếm threads bằng công việc dài hoặc blocking wait; các tasks mới phải xếp hàng rất lâu hoặc vô hạn. Có thể là deadlock **do giới hạn số threads**, nhưng không phải lúc nào cũng là một chu trình chờ hiển thị.

**High latency nhưng chưa deadlock:** callback gọi một API blocking 10 ms, group có 16 threads và đủ dự phòng; service vẫn tiến, nhưng throughput/latency có thể giảm. Đừng chờ đến khi deadlock mới tối ưu.

Một lời gọi `get(timeout)` bên trong handler giúp service *thoát khỏi wait sau thời hạn*, nhưng **không chữa nguyên nhân**: nó vẫn chiếm group thread cho đến khi hết deadline, và còn có thể làm timeout hàng loạt.

## 3. Anti-pattern: chặn callback để đợi I/O hoặc công việc tiếp theo

Mã minh họa **không nên dùng**:

```java
channel.read(buffer, requestId,
        new CompletionHandler<Integer, String>() {
            public void completed(Integer n, String id) {
                Future<Integer> next = channel.read(nextBuffer);
                int bytes = next.get(); // Lỗi thiết kế: chờ trong handler.
                process(bytes);
            }
            public void failed(Throwable error, String id) {
                reportFailure(error);
            }
        });
```

Đây chỉ là **pseudocode Java minh họa anti-pattern**, không phải class biên dịch độc lập: các biến `channel`, `buffer`, `requestId`, `nextBuffer`, `process` và `reportFailure` là thành phần nghiệp vụ; `get()` còn cần xử lý checked exceptions. Mục tiêu là nhận diện **đường chờ sai**, không khuyến nghị chạy đoạn này.

Nếu `next` cũng cần group completion đang bị callback chiếm, việc `get` có thể đóng góp vào vòng chờ. Ngay cả khi `get` hoàn tất được, callback vẫn block group thread mà các connections khác có thể cần.

**Sửa đúng về cấu trúc:** sau khi lần read trước **đã hoàn tất**, handler khởi động lần read mới và **trả về**; kết quả được xử lý trong **completion handler của thao tác mới**. Không gọi `Future.get` ngay trong callback.

### 3.1. Điều gì phải được giữ lại giữa các callbacks?

Một connection state object có thể chứa:

- `requestId`, connection identifier và stage đang thực hiện.
- `ByteBuffer` hiện tại; quyền sở hữu rõ trong mỗi pending I/O.
- Số bytes đã nhận, expected frame length, giới hạn tối đa.
- Outbound queue và flag `writing`.
- Terminal state, deadline và retry policy.
- `CompletableFuture<Response>` hoặc callback business để báo thành công/lỗi.
- Flags `closing/closed` để callbacks chạy trễ không khởi động I/O mới.

Object mutable dùng xuyên threads cần đồng bộ/atomic state đúng cách. **Handler hoàn thành nhanh không tự làm mutable state thread-safe.**

## 4. Mẫu chuẩn: nối read → write bằng completion handler, không đợi trong callback

Sau khi nhận một byte request, server có thể khởi động write response ngay trong `completed` mà **không chờ kết quả write** ở đó. Write có một callback riêng thông báo hoàn tất.

```text
server.read(request, readHandler) -> return
                       |
                    completed
                       |
               server.write(reply, writeHandler) -> return
                                           |
                                        completed
                                           |
                                    mark request DONE
```

### 4.1. Ví dụ runnable: callback echo không blocking

Tạo `NonBlockingEchoCallbackDemo.java`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.util.concurrent.*;
public class NonBlockingEchoCallbackDemo {
  public static void main(String[] args) throws Exception {
    try (AsynchronousServerSocketChannel listener =
             AsynchronousServerSocketChannel.open().bind(
               new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
         AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
      Future<AsynchronousSocketChannel> accepting = listener.accept();
      client.connect(listener.getLocalAddress()).get(5, TimeUnit.SECONDS);
      try (AsynchronousSocketChannel peer = accepting.get(5, TimeUnit.SECONDS)) {
        CompletableFuture<String> processed = new CompletableFuture<>();
        ByteBuffer request = ByteBuffer.allocate(1);
        peer.read(request, "job-7", new CompletionHandler<Integer,String>() {
          public void completed(Integer n, String tag) {
            if (n < 0) {
              processed.completeExceptionally(new IOException("Early EOF"));
              return;
            }
            if (n == 0) { peer.read(request, tag, this); return; }
            ByteBuffer reply = ByteBuffer.wrap(new byte[]{82});
            peer.write(reply, tag, new CompletionHandler<Integer,String>() {
              public void completed(Integer count, String label) {
                if (count < 0) {
                  processed.completeExceptionally(new IOException("Invalid write"));
                } else if (reply.hasRemaining()) {
                  peer.write(reply, label, this);
                } else {
                  processed.complete(label + ":sent");
                }
              }
              public void failed(Throwable error, String label) {
                processed.completeExceptionally(error);
              }
            });
          }
          public void failed(Throwable error, String tag) {
            processed.completeExceptionally(error);
          }
        });
        ByteBuffer outgoing = ByteBuffer.wrap(new byte[]{81});
        while(outgoing.hasRemaining()) {
          if(client.write(outgoing).get(5,TimeUnit.SECONDS)<=0) throw new IOException("No progress");
        }
        System.out.println("callback="+processed.get(5,TimeUnit.SECONDS));
        ByteBuffer inbound=ByteBuffer.allocate(1);
        while(inbound.hasRemaining()) {
          if(client.read(inbound).get(5,TimeUnit.SECONDS)<0) throw new IOException("EOF");
        }
        inbound.flip();
        System.out.println("response="+(char)inbound.get());
      }
    }
  }
}
```

Biên dịch, chạy bằng Java 17+:

```bash
javac -encoding UTF-8 -Xlint:all NonBlockingEchoCallbackDemo.java
java NonBlockingEchoCallbackDemo
```

**stdout đã kiểm thử qua loopback:**

```text
callback=job-7:sent
response=R
```

**Phân tích:**

1. Main thread tạo listener, client, khởi động `accept` và `connect` trên loopback port 0.
2. Server-side `peer` bắt đầu `read(request,...)` với buffer chỉ chứa một byte.
3. Client viết byte decimal 81 (`Q`).
4. `read.completed` **không gọi `get`**; nếu nhận một byte, nó gửi một byte response decimal 82 (`R`) bằng `peer.write` rồi **trả về**.
5. `write.completed` chỉ tiếp tục nếu `reply.hasRemaining()`, còn nếu hết thì hoàn thành `processed`. Không tạo write thứ hai trước khi write thứ nhất hoàn tất.
6. Main thread **trong test harness** chờ `processed.get(timeout)` và đọc response, chứ **không chặn completion handler**.

**Đặc biệt:** có `Future.get` trong chương trình **không có nghĩa chương trình vi phạm chủ đề**. Vấn đề là **ở đâu** ta chờ, **nó chờ ai**, và liệu thread bị chặn có phải tài nguyên mà completion cần để tiến hay không. Một thread điều phối ở test/main có thể chờ có deadline; callback thuộc group nên tránh chờ phụ thuộc nhóm.

**Giới hạn:** demo chỉ xử lý một byte trên một request, thích hợp để thấy cấu trúc callback. Production cần message framing, quota, pending write queue, per-connection state, error handling toàn diện và shutdown policy.

## 5. Không chặn callback để parse, gọi database hay logging chậm

Ngay cả khi callback **không đợi chính Future của mình**, nó có thể làm nghẽn group bằng:

- Parse JSON/XML lớn trong `completed`.
- Giải nén archive hoặc hash file nhiều GiB.
- Chờ JDBC query/transaction hoặc một remote HTTP call.
- `Thread.sleep`, retry backoff bằng sleep trong callback.
- Đợi lock do thread khác đang giữ, hoặc đợi `CountDownLatch.await`.
- Ghi log đồng bộ tới filesystem/network storage chậm.
- Làm synchronous DNS lookup hoặc truy cập filesystem trong một critical section lớn.

**Tách I/O completion và business processing:**

```text
AsynchronousChannelGroup threads
  read.completed(n)
     |
     +-- quick validation (n, bounds, state)
     +-- enqueue bounded worker job
     +-- return nhanh
                    |
                    v
            Business worker pool
              parse / validate / DB
                    |
             enqueue response
                    |
            per-connection write scheduler
              write(..., handler)
```

**Không tạo một `new Thread` vô hạn cho mỗi callback.** Điều đó chuyển deadlock trong group thành khả năng quá tải threads/memory. Dùng executor có cấu hình capacity, quota và chính sách từ chối/backpressure rõ.

### 5.1. Ví dụ runnable: đẩy xử lý từ group sang executor khác

Tạo `CallbackOffloadDemo.java`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
public class CallbackOffloadDemo {
  public static void main(String[] args) throws Exception {
    ThreadFactory groupThreads = task -> new Thread(task, "io-completion");
    AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(1, groupThreads);
    ExecutorService business = Executors.newSingleThreadExecutor(
        task -> new Thread(task, "business-worker"));
    try {
      try (AsynchronousServerSocketChannel listener =
               AsynchronousServerSocketChannel.open(group).bind(
                 new InetSocketAddress(InetAddress.getLoopbackAddress(),0));
           AsynchronousSocketChannel client = AsynchronousSocketChannel.open(group)) {
        var accepted = listener.accept();
        client.connect(listener.getLocalAddress()).get(5,TimeUnit.SECONDS);
        try(AsynchronousSocketChannel peer=accepted.get(5,TimeUnit.SECONDS)) {
          ByteBuffer incoming=ByteBuffer.allocate(1);
          CompletableFuture<String> done=new CompletableFuture<>();
          AtomicReference<Thread> ioThread = new AtomicReference<>();
          peer.read(incoming,"req",new CompletionHandler<Integer,String>(){
            public void completed(Integer n,String tag) {
              if(n != 1) {done.completeExceptionally(new IOException("Expected one byte"));return;}
              ioThread.set(Thread.currentThread());
              try {
                business.execute(()->{
                  incoming.flip();
                  boolean separate=Thread.currentThread()!=ioThread.get();
                  done.complete(tag+":"+(char)incoming.get()+":"+separate);
                });
              } catch(RejectedExecutionException ex) {done.completeExceptionally(ex);}
            }
            public void failed(Throwable error,String tag) {done.completeExceptionally(error);}
          });
          ByteBuffer one=ByteBuffer.wrap(new byte[]{65});
          while(one.hasRemaining()){
            if(client.write(one).get(5,TimeUnit.SECONDS)<=0)throw new IOException("No progress");
          }
          System.out.println("offloaded="+done.get(5,TimeUnit.SECONDS));
        }
      }
    } finally {
      business.shutdown();
      if(!business.awaitTermination(5,TimeUnit.SECONDS))business.shutdownNow();
      group.shutdown();
      if(!group.awaitTermination(5,TimeUnit.SECONDS))group.shutdownNow();
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CallbackOffloadDemo.java
java CallbackOffloadDemo
```

**stdout đã kiểm thử:**

```text
offloaded=req:A:true
```

Trong test:

- Channel group chỉ có **một group thread**.
- Callback lấy kết quả read, ghi nhận group thread, chuyển việc xử lý byte sang **business worker** rồi trả về.
- Worker sở hữu buffer sau khi read **đã completed**, gọi `flip()`, lấy `A` và ghi nhận hai threads khác nhau.
- `CompletableFuture` báo kết quả cho **main thread**. Main đợi có deadline chỉ để kiểm thử.
- Shutdown business pool và group sau khi các channels liên quan đóng.

**Đây là ví dụ về nguyên tắc ownership, không phải server production đầy đủ:** một `Executors.newSingleThreadExecutor` mặc định có hàng đợi không giới hạn. Với tải lớn, dùng **bounded executor + rejection/backpressure** được minh họa riêng ở phần 10; không copy nguyên lựa chọn executor demo để nhận vô hạn messages.

### 5.2. Bàn giao ByteBuffer như thế nào?

Khi read callback đã được gọi, operation tương ứng **đã hoàn thành**. Bạn có thể chuyển quyền xử lý bytes cho worker, với điều kiện:

1. Không khởi động read mới **vào cùng buffer** trước khi worker hoàn tất hoặc copy nội dung.
2. Giữ buffer sống và không sửa trong thread khác khi worker đang parse.
3. Nếu muốn re-arm read ngay, dùng **buffer khác** hoặc copy một lượng bytes có giới hạn sang object riêng.
4. Có quyền sở hữu data rõ ràng; không để callback A và worker B cùng thay đổi `position/limit` trên buffer.
5. Nếu queue đầy, không silently drop payload mà vẫn trả success; áp dụng backpressure, close hoặc ghi trạng thái lỗi.

Trong hệ thống phân tích dữ liệu có kích thước lớn, việc copy có thêm chi phí nhưng làm ownership dễ kiểm soát. Hãy benchmark và chọn chiến lược buffer pooling/ref-count khi thật sự cần.

## 6. Vòng chờ trong một executor thread: demo deterministic, không treo vô hạn

Mẫu sai:

```text
Single-thread executor E (1 worker)
  Task A đang chạy:
    -> đợi Future B.get()
  Task B được queue vào E:
    -> chỉ có thể chạy khi A trả thread về E

A cần B; B cần thread do A giữ.
Không có tác nhân ngoài thì hai bên không thể tiến.
```

Một `ThreadPoolExecutor` có nhiều workers có thể che dấu lỗi khi chưa quá tải; khi số callbacks chặn đủ lớn để chiếm hết group threads, vấn đề vẫn tái xuất hiện.

**Ví dụ sau không cố tạo deadlock vô hạn.** Nó dùng timeout trong task A để phá vòng chờ, chứng minh bằng stdout rằng B chỉ tiến sau khi A nhả thread.

### 6.1. Ví dụ runnable: dependency vòng kín bị giới hạn bằng timeout

Tạo `SingleThreadWaitCycleDemo.java`:

```java
import java.util.concurrent.*;
public class SingleThreadWaitCycleDemo {
  public static void main(String[] args) throws Exception {
    ExecutorService one=Executors.newSingleThreadExecutor();
    CountDownLatch proceed=new CountDownLatch(1);
    CompletableFuture<String> continuation=new CompletableFuture<>();
    try {
      Future<String> waiting=one.submit(()->{
        proceed.await();
        try {
          return continuation.get(100,TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
          return "TIMEOUT";
        }
      });
      Future<?> queued=one.submit(()->continuation.complete("READY"));
      proceed.countDown();
      System.out.println("guarded-wait="+waiting.get(5,TimeUnit.SECONDS));
      queued.get(5,TimeUnit.SECONDS);
      System.out.println("continuation="+continuation.get(5,TimeUnit.SECONDS));
    }finally{
      proceed.countDown();
      one.shutdownNow();
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SingleThreadWaitCycleDemo.java
java SingleThreadWaitCycleDemo
```

**stdout đã kiểm thử:**

```text
guarded-wait=TIMEOUT
continuation=READY
```

**Giải thích:**

- Executor chỉ có một worker. Task A được submit đầu tiên và chờ latch `proceed`.
- Task B được submit vào **cùng executor** và được xếp hàng sau A.
- Main thả latch; A gọi `continuation.get(100,...)`. B **không thể chạy** vì A đang giữ worker.
- Khi A hết thời hạn chờ và trả thread, B mới được chạy, hoàn tất `continuation` với `READY`.
- Nếu bỏ timeout khỏi lời chờ bên trong A, trạng thái có thể mắc kẹt vô hạn.

**Đây là bài test mô hình wait-for dependency của executor, không phải khẳng định Java NIO.2 bắt buộc vận hành mọi I/O giống một single-thread executor này.** Nó làm rõ nguyên tắc thiết kế chung: **không block một tài nguyên mà chính thao tác bạn chờ cần dùng**.

## 7. CompletableFuture.thenCompose: nối các bước, đừng get ngay trong callback

`CompletableFuture` cung cấp các operations về **composition**:

- `thenApply`: biến đổi result đã có.
- `thenCompose`: nối một bước trả về một `CompletionStage` khác, rồi **flatten** kết quả thay vì tạo nested stage.
- `thenAccept`: tiêu thụ kết quả.
- `whenComplete`/`handle`: xử lý success/failure.
- `exceptionally`: phục hồi lỗi theo policy.
- `thenApplyAsync`/`thenComposeAsync`: lập lịch bước xử lý lên executor (mặc định hoặc chỉ định).

**Quan trọng:** `thenApply`, `thenCompose` và các non-async continuations **có thể chạy trực tiếp trên thread hoàn tất upstream stage**. Nếu upstream là I/O callback thread, việc đưa CPU-heavy parse vào `thenApply` vẫn có thể chiếm completion group thread. Khi cần offload, truyền **executor riêng** cho các phiên bản `Async` và quản lý queue/backpressure.

### 7.1. Ví dụ runnable: compose không tạo blocking wait

Tạo `CompletionStageChainDemo.java`:

```java
import java.util.concurrent.*;
public class CompletionStageChainDemo {
  public static void main(String[] args) throws Exception {
    CompletableFuture<Integer> first=new CompletableFuture<>();
    CompletableFuture<String> composed=first.thenCompose(
      length->CompletableFuture.completedFuture("payload-"+length))
      .thenApply(String::toUpperCase);
    System.out.println("queued-not-blocking="+!composed.isDone());
    first.complete(4);
    System.out.println("composed="+composed.get(5,TimeUnit.SECONDS));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CompletionStageChainDemo.java
java CompletionStageChainDemo
```

**stdout đã kiểm thử:**

```text
queued-not-blocking=true
composed=PAYLOAD-4
```

Chương trình nối hai stages **trước khi** hoàn tất `first`, nhưng không block bất kỳ thread nào đang đóng vai trò callback. `composed.get` ở cuối nằm trên main/test thread, chỉ để quan sát kết quả.

**Trong ứng dụng thật**, hàm `length -> ...` có thể bắt đầu một I/O khác và trả `CompletableFuture` được bridge từ completion handler. Sự kết hợp vẫn không đòi hỏi `get` bên trong callback.

### 7.2. Bridge từ CompletionHandler sang CompletableFuture

Snippet minh họa:

```java
CompletableFuture<Integer> result = new CompletableFuture<>();
socket.read(buffer, requestId,
    new CompletionHandler<Integer, String>() {
        public void completed(Integer count, String id) {
            result.complete(count);
        }
        public void failed(Throwable error, String id) {
            result.completeExceptionally(error);
        }
    });
```

Đây là **snippet**, các biến `socket`, `buffer`, `requestId` đã được chuẩn bị và socket đang connected. Trong code thực, phải kiểm tra synchronous exceptions từ chính lời gọi `read` và quản lý timeout/close.

**Bridge không làm kết quả bỗng có cancellation semantics của socket.** Nếu caller cancel `CompletableFuture`, điều đó **không tự cancel** underlying `AsynchronousSocketChannel.read`. Cần có một lifecycle coordinator và định nghĩa hủy thật sự.

### 7.3. Không nhầm CompletionStage với “thread pool riêng”

Nếu `future.thenApply(this::parse)` được hoàn tất bởi callback group thread, `parse` có thể chạy **trên chính thread hoàn tất**. Nếu parse có blocking DB call, bạn vẫn có nguy cơ chiếm group. Chọn `thenApplyAsync(this::parse, boundedBusinessExecutor)` khi cần và hiểu rejection policy của executor.

**Không lấy `CompletableFuture.join()` thay cho `get()` rồi cho rằng không chặn:** cả hai là thao tác chờ, chỉ khác cách báo exceptions.

## 8. Chaining nhiều reads: mỗi lần hoàn tất mới khởi động lần tiếp theo

`AsynchronousSocketChannel` hỗ trợ **tối đa một pending read và một pending write** trên mỗi channel. Khởi tạo read thứ hai trước khi read đầu hoàn tất gây `ReadPendingException`. Tương tự cho write là `WritePendingException`.

Đây là lý do tốt để dùng **continuation callback**: callback đã nhận kết quả của read thứ nhất thì có thể khởi tạo lần read mới, **không cần chờ lần mới trong callback**.

### 8.1. Ví dụ runnable: đọc hai byte nối tiếp qua callbacks

Tạo `CallbackReadContinuationDemo.java`:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.util.concurrent.*;
public class CallbackReadContinuationDemo {
  public static void main(String[] args) throws Exception {
    try(AsynchronousServerSocketChannel listener =
          AsynchronousServerSocketChannel.open().bind(
             new InetSocketAddress(InetAddress.getLoopbackAddress(),0));
        AsynchronousSocketChannel client=AsynchronousSocketChannel.open()) {
      var accepting=listener.accept();
      client.connect(listener.getLocalAddress()).get(5,TimeUnit.SECONDS);
      try(AsynchronousSocketChannel peer=accepting.get(5,TimeUnit.SECONDS)){
        CompletableFuture<String> done=new CompletableFuture<>();
        ByteBuffer single=ByteBuffer.allocate(1);
        StringBuilder result=new StringBuilder();
        class Reader implements CompletionHandler<Integer,Void> {
          public void completed(Integer n, Void unused) {
            if(n<0){done.completeExceptionally(new IOException("Early EOF"));return;}
            if(n==1){
              single.flip();
              result.append((char)single.get());
              single.clear();
            }
            if(result.length()==2)done.complete(result.toString());
            else peer.read(single,null,this);
          }
          public void failed(Throwable error,Void unused){done.completeExceptionally(error);}
        }
        peer.read(single,null,new Reader());
        ByteBuffer outbound=ByteBuffer.wrap(new byte[]{79,75});
        while(outbound.hasRemaining()){
          if(client.write(outbound).get(5,TimeUnit.SECONDS)<=0)throw new IOException("No progress");
        }
        System.out.println("assembled="+done.get(5,TimeUnit.SECONDS));
      }
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CallbackReadContinuationDemo.java
java CallbackReadContinuationDemo
```

**stdout đã kiểm thử:**

```text
assembled=OK
```

Mỗi read nhận **một byte**; callback lưu lại và **khởi tạo read tiếp theo khi cần**. Không có hai pending reads đồng thời, không gọi `get` trong callback. StringBuilder được thao tác như state của **chuỗi callbacks tuần tự**; nếu chuyển sang multi-thread processing/đọc song song ngoài chuỗi này, phải có synchronization phù hợp.

**Giới hạn:** demo dùng 2 bytes ASCII để dễ quan sát. Một real network protocol cần framing có giới hạn, partial reads, Unicode decoder có trạng thái, request deadline và buffer pooling.

### 8.2. Tránh callback đệ quy vô hạn

Một số I/O operations có thể hoàn tất **ngay**. JavaDoc cho phép completion handler được invoked trực tiếp khi initiating thread cũng là group thread. Một callback re-issue operations liên tục có thể tạo một chuỗi callback lồng nhau trong một số implementations.

Đừng thiết kế một vòng vô hạn mà mỗi `completed` tạo một operation zero-length hoặc lập tức hoàn tất rồi gọi `completed` đồng bộ một cách tự chế. Hãy:

- Chỉ khởi tạo read khi còn dữ liệu cần nhận và buffer có `remaining > 0`.
- Xử lý `n == 0` hợp lý, có giới hạn retry/deadline và tránh hot spin.
- Trả control về event loop/scheduler khi muốn xử lý hàng loạt operations; không phải lúc nào cũng chain trực tiếp tất cả trong cùng stack.
- Kiểm soát số outstanding operations và backpressure.
- Hạn chế parse/dispatch recursive chains; đưa phần dài sang executor phù hợp.

## 9. Timeouts không thay thế việc giải dependency

Có hai khái niệm cần phân biệt:

**Timeout khi CHỜ Future:** `future.get(timeout,unit)` ném `TimeoutException` nếu tại thời điểm deadline kết quả chưa sẵn sàng. Điều này chỉ hạn chế **thời gian chờ của caller**. Không có cam kết I/O thật đã bị cancel.

**Timeout của I/O operation:** các overload `AsynchronousSocketChannel.read/write(...,timeout,...,handler)` có thể báo `InterruptedByTimeoutException`. JavaDoc cảnh báo timeout này có thể để **channel/connection hoặc ByteBuffer** ở trạng thái không thể dùng tiếp an toàn; implementation có thể cấm các read/write mới khi không biết thao tác trước đã chuyển bytes hay chưa.

Vì vậy:

- **Không chuyển** `Future.get(5,SECONDS)` vào callback chỉ để “tránh deadlock bằng deadline”.
- Với kết nối cần phục hồi, xác định behavior sau I/O timeout, thường teardown session và thiết lập channel mới khi state không còn đáng tin.
- Đừng reuse buffer ngay khi một lời chờ timeout; operation có thể đang diễn ra.
- Phân biệt cancellation signal với confirmation I/O completion/cleanup.
- Nếu request có tác động nghiệp vụ, retry phải có request ID/idempotency để không tạo duplicate.

### 9.1. Ví dụ runnable: timeout khi chờ không cancel operation

Tạo `WaitTimeoutVsOperationDemo.java`:

```java
import java.util.concurrent.*;
public class WaitTimeoutVsOperationDemo {
  public static void main(String[] args) throws Exception {
    CompletableFuture<String> pending=new CompletableFuture<>();
    boolean timedOut=false;
    try{pending.get(1,TimeUnit.MILLISECONDS);}
    catch(TimeoutException ex){timedOut=true;}
    System.out.println("wait-timed-out="+timedOut);
    System.out.println("future-cancelled="+pending.isCancelled());
    pending.complete("LATE");
    System.out.println("late-result="+pending.get(1,TimeUnit.SECONDS));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all WaitTimeoutVsOperationDemo.java
java WaitTimeoutVsOperationDemo
```

**stdout đã kiểm thử:**

```text
wait-timed-out=true
future-cancelled=false
late-result=LATE
```

Đây là **mô hình CompletableFuture deterministic**, không mở socket. Ta giữ `pending` chưa hoàn tất trong lúc `get(1ms)` chờ nên chắc chắn timeout; sau đó hoàn tất nó bình thường. Tương tự, timeout của **lời chờ** đối với Future của socket không phải bằng chứng underlying I/O đã bị hủy.

**Điểm khác với `orTimeout`:** `CompletableFuture.orTimeout` hoàn tất **chính CompletableFuture** theo timeout; nó vẫn **không tự kết thúc** thao tác socket bên dưới nếu bạn chỉ bridge handler vào future. Chương trình thực cần coordinator xử lý timeout, hủy/close và buffer ownership.

## 10. Backpressure: offload cũng có thể gây quá tải nếu queue vô hạn

Một giải pháp nửa vời là chuyển mọi callback vào `Executors.newCachedThreadPool` hoặc `newSingleThreadExecutor` không giới hạn queue. Khi tốc độ nhận > xử lý, hệ thống sẽ tích lũy:

- Nhiều business tasks chưa xử lý.
- Các `ByteBuffer` bị giữ bởi closures/jobs.
- Các connections còn active nhưng không còn được phục vụ kịp.
- RAM/threads tăng nhanh.
- Độ trễ tăng cho cả request mới và cũ.

**Giới hạn tài nguyên là một phần của tránh starvation**. Một pattern production cho công việc blocking business có thể là `ThreadPoolExecutor` với `ArrayBlockingQueue`, số workers định trước và một chính sách khi `RejectedExecutionException` xảy ra. Khi queue đầy, quyết định:

- Tạm ngừng/giới hạn việc đọc thêm từ connection đang quá tải (backpressure).
- Trả thông điệp BUSY hoặc mã lỗi protocol có giới hạn.
- Đóng connection trong điều kiện cần bảo vệ service.
- Đẩy sang durable broker nếu kiến trúc có thành phần đó và đã xác thực/kiểm soát quota.
- Ghi metrics và alert khi reject xảy ra.

**Không dùng `CallerRunsPolicy` tùy tiện khi gọi `execute` từ completion handler**: nếu queue đầy, policy này có thể chuyển **công việc blocking/CPU-heavy chạy ngay trên callback thread**, triệt tiêu mục tiêu offload.

### 10.1. Ví dụ runnable: queue một slot và từ chối tác vụ thứ ba

Tạo `BoundedOffloadQueueDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public class BoundedOffloadQueueDemo {
  public static void main(String[] args) throws Exception {
    ThreadPoolExecutor pool=new ThreadPoolExecutor(
        1,1,0L,TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(1),
        new ThreadPoolExecutor.AbortPolicy());
    CountDownLatch started=new CountDownLatch(1);
    CountDownLatch release=new CountDownLatch(1);
    AtomicInteger processed=new AtomicInteger();
    try {
      Future<?> first=pool.submit(()->{
        started.countDown();
        try{release.await();}catch(InterruptedException ex){Thread.currentThread().interrupt();return;}
        processed.incrementAndGet();
      });
      if(!started.await(5,TimeUnit.SECONDS))throw new IllegalStateException("Worker not started");
      Future<?> second=pool.submit(processed::incrementAndGet);
      boolean rejected=false;
      try{pool.submit(processed::incrementAndGet);}
      catch(RejectedExecutionException ex){rejected=true;}
      System.out.println("third-rejected="+rejected);
      release.countDown();
      first.get(5,TimeUnit.SECONDS);
      second.get(5,TimeUnit.SECONDS);
      System.out.println("processed="+processed.get());
    }finally{
      release.countDown();
      pool.shutdownNow();
      pool.awaitTermination(5,TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BoundedOffloadQueueDemo.java
java BoundedOffloadQueueDemo
```

**stdout đã kiểm thử:**

```text
third-rejected=true
processed=2
```

Demo **không cần ngủ** và không phụ thuộc may mắn thread scheduling:

1. Task đầu tiên chạy và chờ `release`, giữ worker.
2. Task thứ hai được queue ở slot duy nhất.
3. Task thứ ba bị từ chối bởi `AbortPolicy`.
4. Main thả latch để task đầu tiên trả worker; task thứ hai được xử lý sau.
5. Kết quả có đúng **2 jobs được xử lý**, và **1 job bị reject rõ ràng**.

**Không áp dụng queue size=1 như một ngưỡng cố định cho mọi sản phẩm.** Giá trị production cần dựa vào SLA, CPU, memory, độ lớn payload và tốc độ nhập/xử lý. Ngay cả khi queue đầy, handler phải **chuyển request thành trạng thái terminal/được backpressure**; không được log rồi để `CompletableFuture` vĩnh viễn pending.

## 11. Tác động khi callback thất bại: hoàn tất promise, tránh waiter kẹt vô thời hạn

Handler có **hai đường kết thúc**:

- `completed(result, attachment)`: operation hoàn tất, kể cả trường hợp read trả **-1 (EOF)**. EOF không phải một network exception, nhưng có thể là **lỗi ở tầng protocol** nếu bạn đang chờ body chưa đủ.
- `failed(Throwable, attachment)`: operation bất đồng bộ thất bại (connection reset, channel closed hoặc lỗi khác).

**Nếu callback chỉ log failure mà không hoàn thành promise**, thread/actor đang đợi response có thể treo vĩnh viễn. Nguyên tắc:

1. Mọi code path phải đưa request tới trạng thái **success** hoặc **failure** (hoặc cancellation có quy tắc).
2. Gọi `completeExceptionally(cause)` khi không thể thực hiện operation.
3. Dùng `whenComplete/handle` hoặc state coordinator để dọn resource kể cả khi lỗi.
4. Chỉ phát **một terminal event**; dùng `CompletableFuture.complete` trả boolean hoặc state atomic để chống double completion.
5. Không cố retry trong handler bằng một vòng lặp blocking với `Thread.sleep`.
6. Không xóa buffer trước khi underlying I/O đã terminal hoặc trước khi lifecycle coordinator xử lý cancellation.

### 11.1. Ví dụ runnable: EOF được nâng thành lỗi protocol

Tạo `CallbackEofErrorDemo.java`:

```java
import java.io.EOFException;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.util.concurrent.*;
public class CallbackEofErrorDemo {
  public static void main(String[] args) throws Exception {
    try(AsynchronousServerSocketChannel listener =
          AsynchronousServerSocketChannel.open().bind(
            new InetSocketAddress(InetAddress.getLoopbackAddress(),0));
        AsynchronousSocketChannel client=AsynchronousSocketChannel.open()){
      var accept=listener.accept();
      client.connect(listener.getLocalAddress()).get(5,TimeUnit.SECONDS);
      try(AsynchronousSocketChannel peer=accept.get(5,TimeUnit.SECONDS)){
        CompletableFuture<Integer> received=new CompletableFuture<>();
        client.read(ByteBuffer.allocate(1),"tag",
          new CompletionHandler<Integer,String>(){
            public void completed(Integer n,String tag) {
              if(n==-1)received.completeExceptionally(new EOFException("closed"));
              else received.complete(n);
            }
            public void failed(Throwable ex,String tag){received.completeExceptionally(ex);}
          });
        peer.shutdownOutput();
        try{received.get(5,TimeUnit.SECONDS);}
        catch(ExecutionException ex){System.out.println("error-type="+ex.getCause().getClass().getSimpleName());}
      }
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all CallbackEofErrorDemo.java
java CallbackEofErrorDemo
```

**stdout đã kiểm thử:**

```text
error-type=EOFException
```

Peer không gửi payload mà half-close chiều gửi. Client đọc nhận **-1**, callback chuyển điều đó thành lỗi **EOFException** theo yêu cầu protocol (mong ít nhất một byte). Main nhận đúng cause qua `ExecutionException`. Không có blocking wait nào trong `completed` hoặc `failed`.

**Nhớ:** EOF có thể là tín hiệu **bình thường** với protocol đọc đến EOF. Trong demo, nó là lỗi vì contract của message đòi dữ liệu. Đừng xem mọi `-1` là lỗi không điều kiện.

## 12. Vòng chờ lẫn nhau không chỉ có Future.get

Các dependency cycles phổ biến trong hệ thống NIO.2:

### 12.1. Callback A đợi callback B

```text
Callback A -> Future B.get()
Callback B -> đợi group thread đang bị A chiếm
```

**Sửa:** A đăng ký continuation của B rồi trả thread. Nếu phải chạy business work dài, offload sang một pool không phụ thuộc cùng group và có backpressure.

### 12.2. Callback giữ lock khi gọi wait

```text
Thread A (completion handler):
  lock(state)
  wait(result)
  
Thread B (business worker):
  cần lock(state) để complete(result)
```

Nếu A giữ lock trong khi đợi B, còn B không lấy được lock để hoàn tất result, đây là **deadlock lock/wait** dù có nhiều threads. Dùng **critical section thật ngắn** chỉ để cập nhật state, thả lock trước khi chờ hoặc tốt hơn tránh blocking wait.

### 12.3. Two-way request/response cycle

```text
Client A gửi message, đợi response của B
Server B đợi thêm byte từ A trước khi tạo response
Client A không gửi vì đang đợi B
```

Đây là **protocol deadlock**, không chỉ vấn đề executor. Ví dụ một phía dùng `read-to-EOF` nhưng phía kia chờ response trước khi `shutdownOutput()`. Sửa bằng **framing rõ ràng**: length-prefix/delimiter hoặc half-close theo một hợp đồng thống nhất.

### 12.4. Callback chờ executor mà nó đang làm nghẽn

```text
I/O callback -> submit CPU job -> job cần lấy shared lock
I/O callback -> giữ lock trong khi chờ Future CPU job
```

Chuyển task sang executor riêng **không giải quyết vòng chờ lock** nếu callback vẫn giữ điều kiện mà job cần. Phải phân tích **wait-for graph**.

### 12.5. Server accept mà không đăng ký lại

Một `AsynchronousServerSocketChannel` chỉ có **một pending accept**. Sau khi accepted connection, nếu handler bị blocking parse và không re-arm `accept`, server không nhận thêm connections đúng nhịp. Đây thường là **liveness/throughput bug**, có thể chưa phải deadlock. Re-arm accept nhanh, đưa công việc accepted channel sang connection handler riêng và có giới hạn active connections.

### 12.6. Hai callbacks giành ByteBuffer hoặc một read pending

`AsynchronousSocketChannel` chỉ cho một read pending và một write pending đồng thời; lời gọi read thứ hai khi first read chưa hoàn tất ném `ReadPendingException`. Đây là exception của **concurrency contract**, không phải cơ chế chờ. Đừng cố sửa bằng cách tạo latch để chờ first read **ngay trong callback**. Hãy làm một read coordinator và chỉ re-arm read sau khi result của read hiện tại đã terminal.

### 12.7. CompletableFuture tự phụ thuộc vào chính nó

Một stage có thể bị lập trình nhầm để `join` hoặc đợi chính future mà nó chịu trách nhiệm hoàn tất. Đó là một chu trình logic:

```text
complete F cần chạy callback C
callback C chờ F.join()
```

Chọn composition bằng `thenCompose` hoặc tổ chức state machine khác; không xây một stage phải tự đợi chính mình hoàn tất.

## 13. Shutdown cũng dễ tạo deadlock nếu đợi ngay trong callback

Giả sử handler thuộc group G gọi:

```java
group.shutdown();
group.awaitTermination(30, TimeUnit.SECONDS);
```

Đây là **snippet sai vị trí** (không phải runnable program). Theo lifecycle `AsynchronousChannelGroup`, termination yêu cầu các channels trong group đã đóng và **các completion handlers đang thực thi đã kết thúc**. Nếu callback đang thực thi lại chờ group terminated, có thể tạo vòng chờ với chính nó.

**Sửa:** callback chỉ **phát tín hiệu shutdown** tới coordinator rồi trả về. Một thread quản lý **ngoài group callback** sẽ đóng listener, ngừng nhận jobs mới, drain/cancel pending sessions theo SLA, đóng accepted channels, yêu cầu `group.shutdown` và đợi termination có thời hạn.

### 13.1. Thứ tự graceful shutdown hợp lý

1. Đặt trạng thái `STOPPING` để reject/không khởi tạo request mới.
2. Dừng/restrict `accept` mới; đóng listener khi policy yêu cầu.
3. Ngừng đọc frame mới trên active sessions; hoàn tất hoặc fail rõ các requests đang xử lý.
4. Nếu protocol cần trả response, drain write queue theo deadline, không giữ callback group chờ.
5. Đóng từng client/accepted `AsynchronousSocketChannel`.
6. Hoàn tất/giải phóng các promises, buffers và business jobs còn dở.
7. Yêu cầu group `shutdown()` hoặc `shutdownNow()` theo mức độ graceful.
8. **Từ coordinator ngoài callback**, `awaitTermination` với deadline.
9. Đóng business executors sau khi không còn job sử dụng; log trạng thái shutdown/unfinished operations.

**`shutdownNow` không phải “ngay lập tức mọi callback biến mất”.** Nó có thể yêu cầu đóng channels, nhưng cần xử lý các callbacks/lỗi đang chạy và chờ termination theo contract.

### 13.2. Tại sao không giữ lock khi close?

`close()` có thể làm pending I/O hoàn tất lỗi, và exception callback có thể cần state lock để dọn tài nguyên. Nếu coordinator giữ một lock lớn khi chờ các callbacks cleanup, có thể tự tạo deadlock. Nên cập nhật state dưới lock ngắn, **thả lock trước khi đợi** completion/termination.

## 14. Có nên dùng virtual threads hoặc CompletableFuture thay toàn bộ NIO.2?

Java 17 hỗ trợ `CompletableFuture`/executors và NIO.2; những ví dụ trong bài đều chạy trên Java 17+. Ở Java 21+ có **virtual threads** giúp biểu diễn nhiều tác vụ dùng blocking API theo phong cách tuần tự, nhưng điều đó **không xóa wait-for cycle** nếu A chờ B và B chờ A, hoặc nếu bạn giữ lock mà B cần để hoàn tất.

Phân biệt:

- **Callback completion-based:** cố giữ handler ngắn và kết hợp operations bằng continuation.
- **Thread-per-request với blocking I/O:** có thể dễ đọc hơn khi số lượng request lớn và runtime hỗ trợ virtual threads; vẫn cần giới hạn memory/IO/connections/DB pool và tránh circular waits.
- **CompletableFuture composition:** hỗ trợ viết dependency graph; nếu dùng `join/get` trong continuation, code vẫn blocking.
- **AsyncChannelGroup:** cơ chế quản lý channels/completion trên các thread có giới hạn; **không** phải tự động thay thế executor dành cho business logic dài.

Không nên khẳng định “virtual threads sửa hết deadlock” hoặc “NIO.2 lỗi thời”. Chọn architecture theo workload, operational needs, TLS, framework và độ phức tạp được chấp nhận.

## 15. Đo và chẩn đoán starvation/deadlock

Một service có thể **không có stack trace với từ deadlock**, nhưng vẫn bị nghẽn vì completion threads đang chờ Future/latch/lock. Cần cả metrics lẫn thread diagnostics.

### 15.1. Những metrics đáng thu thập

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số connections đang active | Quy mô tài nguyên sockets |
| Pending reads / writes | I/O outstanding theo chiều |
| Completion handler duration (P50/P95/P99) | Callback có đang chạy quá lâu? |
| Pending business jobs và queue age | Worker pool có bị nghẽn? |
| Executor rejected tasks | Bounded queue có đạt giới hạn? |
| I/O timeouts | Kết nối không tiến hoặc peer chậm |
| Frame decode/validation failures | Dữ liệu đến không hợp lệ |
| Group shutdown latency | Có callback chưa trả về? |
| Active threads theo state | Số đang RUNNABLE/WAITING/BLOCKED |
| Stalled request age | Phát hiện request không có terminal state |
| Per-connection outbound queue bytes | Slow receivers/backpressure |
| Tail latency theo operation | Ảnh hưởng dây chuyền của starvation |

**Không chỉ nhìn CPU:** một deadlock thường có CPU thấp vì threads đang chờ. Heap/threads/queue depth, request age và stack dumps cho biết điều gì đang thực sự diễn ra.

### 15.2. Sử dụng thread dump đúng cách

Trong môi trường vận hành được phép, sử dụng diagnostic tooling của JDK như `jcmd <pid> Thread.print` (hoặc công cụ tương ứng) để lấy thread stacks. Trong dump, tìm:

- Thread thuộc group bị kẹt ở `CompletableFuture.join`, `FutureTask.get`, `CountDownLatch.await` hoặc `LockSupport.park`.
- Handler nào giữ monitor/lock và chờ một task khác.
- Worker pool có threads đang WAITING/BLOCKED, queue backlog mà không có worker rảnh.
- Callback đang chạy JDBC/HTTP/disk I/O blocking.
- Chuỗi Future/CompletionStage không bao giờ được hoàn tất trên đường lỗi.
- Lifecycle/close/awaitTermination được gọi từ chính group handler.

**Lưu ý:** Java deadlock detector thường phát hiện một số chu kỳ lock/monitor, **không nhất thiết phát hiện** starvation hoặc cycles qua `CompletableFuture`/application protocol. Việc diagnostic không báo deadlock **không chứng minh** mọi dependency đang tiến.

### 15.3. Thu thập logs vừa đủ

Logs cần correlation ID, connection ID, stage, bytes thực nhận/gửi, timeout, queue status và cause của `ExecutionException`. Không log payload/tokens/credentials, không để blocking log appender trở thành nút nghẽn mới của completion thread.

## 16. Error handling: handler phải kết thúc nhanh và không nuốt lỗi

Trong hệ thống real-time, error path cũng là một phần của liveness:

- `handler.failed` phải báo rõ nguyên nhân và hoàn tất promises.
- Nếu `read.completed(-1)` là lỗi protocol, chuyển thành failure rồi cleanup.
- `RejectedExecutionException` từ offload phải được xử lý: backpressure/close/fail, không nuốt.
- `ReadPendingException` hoặc `WritePendingException` chỉ ra lỗi điều phối, thường không nên retry bằng blocking wait trong callback.
- `ExecutionException.getCause()` cho biết lỗi thật của Future; không log mỗi wrapper.
- `InterruptedException` khi thread chờ bị hủy cần được propagate/restore interrupt đúng boundary.
- `TimeoutException` khi chờ là signal không đủ thời gian, không tự chứng minh bytes đã ngừng chuyển.
- `InterruptedByTimeoutException` ở timed network operation có thể để buffer/channel không đáng tin; không reuse mù quáng.
- `AsynchronousCloseException` khi đóng channel trong lúc I/O pending có thể là shutdown bình thường hoặc unexpected, tùy state.
- `ShutdownChannelGroupException` cho biết group không còn nhận operations/channels theo contract.

**Không gọi trực tiếp `throw new RuntimeException(...)` trong callback rồi hy vọng thread main nhận lỗi đó**. Exception ném ra khỏi callback không tự chuyển vào request Future do ứng dụng tạo. Dùng `completeExceptionally`/error channel có owner.

### 16.1. Checklist exception và hành động

| Vấn đề | Nơi phát sinh | Hướng sửa |
| --- | --- | --- |
| Blocking `get()` trong handler | Callback logic | Nối continuations; bỏ wait |
| CompletableFuture tự chờ chính mình | Dependency graph | Thiết kế lại graph không có cycle |
| Sử dụng hai reads pending | Channel read coordinator | Chỉ re-arm sau completion |
| Callback parse quá lâu | Handler CPU/blocking work | Bounded offload, không CallerRuns trên callback |
| Executor reject | Offload boundary | Backpressure/terminal state |
| EOF trong frame chưa đủ | `completed(-1)` | Trả lỗi protocol, close |
| Future waiting timeout | Thread đang chờ | Xử lý deadline/lifecycle; I/O có thể còn pending |
| Timed I/O operation timeout | `failed(InterruptedByTimeoutException)` | Teardown nếu state không đáng tin |
| Connection close khi pending | `AsynchronousCloseException` | Hoàn tất promises, cleanup |
| Async group shutdown | Group management | Stop accept, close channels, await từ coordinator |
| Peer không phản hồi | Application protocol | Idle deadlines, max frame, heartbeat khi cần |
| TLS/auth không có | Network boundary | Dùng TLS stack, authorization, input validation |

## 17. An toàn dữ liệu và bảo mật khi thiết kế callback

**Tránh deadlock không tự biến network service thành an toàn.** Một callback nhanh vẫn có thể xử lý thông tin sai hoặc phản hồi client không được xác thực.

Các lớp phòng vệ:

1. **Length-prefix/valid framing**: mỗi message có giới hạn bytes/frames.
2. **Input validation**: reject invalid lengths, unsupported versions, malformed encoding.
3. **TLS/authentication/authorization**: raw TCP NIO.2 không mã hóa/kiểm tra danh tính.
4. **Per-connection quotas**: số requests, bytes in-flight, queue sizes và total connection limits.
5. **Buffer ownership**: không dùng chung mutable buffers với pending I/O hoặc worker khác.
6. **Deadline/cancellation**: service phải có khả năng dọn sessions treo dù peer không gửi bytes.
7. **Replay/idempotency**: write hoàn tất không chứng minh peer đã commit business operation.
8. **Offload bounded**: tránh biến backpressure thành memory leak.
9. **Nonblocking logging**: tránh I/O chậm trong group handler; log có giới hạn và redaction.
10. **Shutdown discipline**: ngăn callbacks mới thao tác vào state đã freed/closed, đồng bộ terminal status.

## 18. Hướng dẫn kiểm thử đáng tin

### 18.1. Unit tests và mô hình phụ thuộc

Không cần một TCP connection thật để chứng minh một worker đang đợi task được queue **sau nó** trên cùng single-thread executor. `SingleThreadWaitCycleDemo` làm được điều đó deterministically và tự phá vòng chờ bằng deadline.

`CompletionStageChainDemo` kiểm tra composition mà không cần tạo thread riêng, còn `WaitTimeoutVsOperationDemo` tách wait timeout với cancellation.

### 18.2. Integration tests qua loopback

`NonBlockingEchoCallbackDemo`, `CallbackOffloadDemo`, `CallbackReadContinuationDemo` và `CallbackEofErrorDemo` dùng loopback, port 0, `Future.get(timeout)` chỉ ở main/test threads để xác minh I/O.

**Không viết tests dựa vào:**

- Callback phải đến trong 1–5 ms trên mọi CI.
- Callback phải chạy trên một thread name cố định của default group.
- Một socket write luôn được đối diện nhận bằng đúng một socket read.
- Nếu call `sleep(10)` thì callback chắc chắn đã hoàn tất.
- Một read trả 0 là peer đã đóng; EOF là -1.
- Một queued completion chạy cùng thứ tự requests được submit.
- ThreadPoolExecutor queue luôn có độ dài như mong đợi mà không điều phối bằng latch.
- Timed wait đóng underlying socket tự động.

### 18.3. Lệnh chạy tất cả chương trình

Lưu từng chương trình vào file có **tên trùng `public class`**. Với JDK 17+, chạy:

```bash
javac -encoding UTF-8 -Xlint:all NonBlockingEchoCallbackDemo.java
javac -encoding UTF-8 -Xlint:all CallbackOffloadDemo.java
javac -encoding UTF-8 -Xlint:all SingleThreadWaitCycleDemo.java
javac -encoding UTF-8 -Xlint:all CompletionStageChainDemo.java
javac -encoding UTF-8 -Xlint:all CallbackReadContinuationDemo.java
javac -encoding UTF-8 -Xlint:all WaitTimeoutVsOperationDemo.java
javac -encoding UTF-8 -Xlint:all BoundedOffloadQueueDemo.java
javac -encoding UTF-8 -Xlint:all CallbackEofErrorDemo.java
```

Sau đó chạy các lệnh `java <TênClass>` tương ứng. Các chương trình chỉ dùng API thuộc JDK, không cần Maven/Gradle/dependency thứ ba.

**Môi trường QA:** các ví dụ hoàn chỉnh đã được biên dịch với `javac -encoding UTF-8 -Xlint:all` và chạy kiểm tra stdout; những đoạn ngắn ghi là “snippet” hoặc “pseudocode” chỉ minh họa ý tưởng chứ không được xem là chương trình tự chạy.

### 18.4. Kiểm thử áp lực và lỗi

- Tạo nhiều clients gửi frames dài/chậm; giám sát callback duration và queue age.
- Dùng test double cho business worker chậm; xác minh callback trả nhanh, queue reject/backpressure.
- Thử tự tạo wait-for graph có chu trình trong unit test, luôn đặt deadline để CI không treo.
- Cho peer half-close trước khi gửi frame; đảm bảo promise kết thúc bằng lỗi protocol.
- Đóng connection khi read/write còn pending; đảm bảo pending request được fail/cleanup.
- Shutdown group với nhiều active channels; coordinator phải đóng channels trước khi await.
- Test connection timeout/read timeout; không assert ByteBuffer còn nguyên khi I/O timeout.
- Mô phỏng completion callback exception; verify request không bị mất terminal state.
- Đảm bảo resource teardown không block group thread đang đợi chính nó.
- Dùng profiling để xác minh không có parsing/DB blocking trong handlers.

## 19. Các anti-pattern và cách sửa

| Anti-pattern | Hậu quả | Hướng phù hợp |
| --- | --- | --- |
| Callback gọi `future.get()` để đợi I/O tiếp theo | Block completion thread, có nguy cơ cycle | Chain handler/CompletionStage |
| Callback dùng `CompletableFuture.join()` | Vẫn là blocking | `thenCompose` và async stages |
| Callback dùng `CountDownLatch.await()` | Chờ thread phát tín hiệu có thể cùng pool | Async state transition |
| Callback giữ synchronized lock rồi wait | Thread khác không lấy được lock để complete | Thả lock, tránh chờ dưới lock |
| Group 1 thread, task A chờ task B queued cùng group | Deadlock/starvation | Không block group; offload/compose |
| Parse JSON lớn trong callback | Dispatch completions chậm | Offload có giới hạn |
| Gọi JDBC/HTTP blocking trong callback | Pool dễ nghẽn dưới tải | Business executor/async client phù hợp |
| Offload sang unbounded queue | Tích lũy RAM/buffers/latency | Bounded queue/backpressure |
| `CallerRunsPolicy` trên caller là handler | Chạy business task ngay trên group thread | Explicit reject/backpressure |
| Không xử lý `RejectedExecutionException` | Request mất state terminal | Fail/close/retry theo policy |
| `thenApply` chứa blocking function | Có thể chạy trên completing thread | `thenApplyAsync(..., executor)` |
| Đọc lại cùng ByteBuffer khi worker vẫn xử lý | Data race/corruption | Chuyển ownership/copy buffer |
| Gọi read thứ hai khi read pending | `ReadPendingException` | Một read coordinator |
| Gọi write thứ hai khi write pending | `WritePendingException` | Một write queue |
| Gọi `shutdownOutput` khi write còn pending | State/bytes khó đoán | Drain writes trước half-close |
| Chờ group.awaitTermination trong callback thuộc group | Có thể chờ chính callback hiện tại kết thúc | Coordinator ngoài group await |
| Callback failed chỉ log mà không complete request | Promise pending mãi | `completeExceptionally` |
| `Future.get(timeout)` bị coi là cancel socket | Operation có thể còn running | Explicit lifecycle cancellation |
| Timeout xong dùng lại buffer | I/O có thể còn ghi/đọc vào buffer | Điều phối cleanup/teardown |
| Callback có vòng lặp zero-length reads | Có thể hot spin/recursion | Giới hạn retries/deadline |
| Dùng raw TCP không framing | Peer đợi bytes mà client không gửi, protocol cycle | Length-prefix/delimiter |
| Coi close listener là đóng mọi accepted sockets | Rò rỉ sessions | Close từng accepted channel |
| Không có metrics request age/queue age | Không nhìn thấy starvation | Instrument nhóm và business workers |

## 20. Checklist code review

1. Mỗi `CompletionHandler` có trả về nhanh sau khi xử lý `n` và trạng thái cần thiết không?
2. Có `Future.get`/`join`/`await`/`sleep`/blocking lock **trong callback** không?
3. Với mỗi blocking wait, đã vẽ được dependency nó đang chờ và thread/lock mà dependency cần chưa?
4. Group có số threads đủ dùng cho I/O/completion, không dùng thay business pool dài hạn không?
5. Có tránh `awaitTermination` **từ trong** callback thuộc group đó không?
6. Có một read pending và một write pending tối đa trên mỗi channel không?
7. Có write queue và coordinator khi nhiều business tasks muốn gửi response không?
8. Có re-arm read sau completion, không tự chặn callback để đợi read mới không?
9. Có hiểu TCP là byte stream và lập framing/partial transfer/EOF theo protocol không?
10. Có mã hóa UTF-8 và tính length theo **bytes**, không phải `String.length()` không?
11. Có giữ `ByteBuffer` không bị sửa cho đến khi I/O terminal không?
12. Khi offload, có chuyển quyền sở hữu buffer/copy dữ liệu hợp lệ không?
13. Có giới hạn business queue, số workers, memory, active connections và pending bytes không?
14. Khi queue đầy, có xử lý rejection/backpressure thay vì drop không?
15. Có tránh `CallerRunsPolicy` khiến blocking work chạy ngay trên completion thread không?
16. Có tránh `thenApply` chạy blocking task trên completing thread không?
17. Có dùng `thenCompose`/`thenApplyAsync` với executor thích hợp cho bước dài không?
18. Mọi `completed/failed` đều đưa request tới terminal state không?
19. Có chuyển lỗi qua `completeExceptionally` thay vì throw mà không ai nhận không?
20. Có quản lý retry, deadline, cancellation và idempotency đúng không?
21. Có phân biệt Future waiting timeout với I/O operation timeout và buffer undefined state không?
22. Có không dùng lại channel sau connect thất bại không?
23. Có chỉ đóng channels/group ở component sở hữu, theo trình tự graceful shutdown không?
24. Có chờ group termination ngoài callback không?
25. Có tránh synchronized lock dài, không chờ trong critical section không?
26. Có metrics handler duration, group thread state, business queue age và rejection rate không?
27. Có thu thread dump khi nghi deadlock/starvation, không chỉ dựa CPU không?
28. Có đảm bảo TLS/authentication/quotas và validate input không?
29. Có test bằng loopback port 0 và deadline, không dùng sleep timing tùy ý không?
30. Có kiểm tra lời gọi blocking ở thư viện gián tiếp như JDBC, DNS, log appender không?
31. Có phân biệt deadlock với starvation và chỉ slow operation không?
32. Có hiểu thêm threads không tự giải quyết vòng chờ lock/protocol không?

## 21. Bài tập

**Bài 1 — Tránh get trong handler.** Chạy `NonBlockingEchoCallbackDemo`. Vẽ thứ tự `read.completed → write(...) → write.completed`. Tại sao `processed.get` ở main/test không tạo cùng dependency nguy hiểm như `get` trong group callback?

**Bài 2 — Dependency graph.** Chạy `SingleThreadWaitCycleDemo`. Bỏ timeout **trong một sơ đồ phân tích** (không nên để chương trình treo vô hạn trên CI); vẽ A→B→E và nêu điều kiện để B chạy.

**Bài 3 — Offload.** Chạy `CallbackOffloadDemo`. Thay business task bằng parser giả lập có nhiều dữ liệu. Thiết kế queue có giới hạn và chính sách khi worker xử lý chậm.

**Bài 4 — Continuations.** Chạy `CompletionStageChainDemo`. Thêm một `CompletableFuture` đại diện I/O sau khi đọc header, nối bằng `thenCompose` thay vì `join` trong continuation.

**Bài 5 — Direct continuation.** Xem trường hợp một stage đã hoàn tất trước khi bạn gọi `thenApply`. Vì sao transformation có thể chạy trên thread gọi đăng ký stage, và tại sao `thenApplyAsync` với executor riêng hữu ích cho parse nặng?

**Bài 6 — Read chaining.** Chạy `CallbackReadContinuationDemo` với 5 bytes. Mỗi callback khởi tạo read tiếp theo **sau khi** read hiện tại hoàn tất; giới hạn số bytes và deadline.

**Bài 7 — Backpressure.** Chạy `BoundedOffloadQueueDemo`. Đổi queue capacity thành 2 rồi kiểm tra cách nhận biết task bị reject. Đề xuất phản hồi protocol BUSY/close phù hợp.

**Bài 8 — Handler error.** Chạy `CallbackEofErrorDemo`. Chuyển `EOFException` thành terminal business error và đảm bảo không để promise mãi pending khi peer đóng sớm.

**Bài 9 — Timeout.** Chạy `WaitTimeoutVsOperationDemo`. Phân biệt `get(timeout)` với `CompletableFuture.orTimeout` và timed socket read/write; không tuyên bố chúng có cùng cancellation semantics.

**Bài 10 — Lock cycle.** Tạo unit test với hai tasks chia sẻ một `ReentrantLock` và một `CompletableFuture`, nhưng đặt deadline để kiểm thử không treo. Thiết kế lại để thả lock trước khi đợi.

**Bài 11 — Accept loop.** Thiết kế `AsynchronousServerSocketChannel.accept` với callback re-arm nhanh và giới hạn active connections. Không thực hiện DB work trực tiếp trong accept handler.

**Bài 12 — Write queue.** Nhiều business workers muốn gửi 10 messages trên một connection. Thiết kế một per-connection write coordinator, xử lý partial writes và `WritePendingException` mà không blocking.

**Bài 13 — Shutdown.** Thiết kế coordinator riêng dừng listener, drain/close accepted channels, shutdown business executor, shutdown group rồi await termination. Giải thích nguy cơ callback chờ chính group của nó.

**Bài 14 — Logging.** Đo P99 callback duration khi appender ghi đồng bộ vào file/network. Chuyển logs sang pipeline có giới hạn và fallback an toàn.

**Bài 15 — Virtual threads.** So sánh code dùng Java 21+ virtual threads cho blocking per-request với NIO.2 completion handlers. Vì sao vòng chờ A↔B vẫn là deadlock bất kể model threads?

**Bài 16 — Security.** Xây gateway nhận length-prefixed frames với authentication, max frame size, per-client quota và timeout; đảm bảo callback không parse payload lớn trong group thread.

**Bài 17 — Metrics.** Tạo dashboard theo dõi active connections, handler duration, business queue depth, rejected submissions và stalled request age. Chọn cảnh báo phát hiện starvation trước khi service ngừng phản hồi.

## 22. Tổng kết

- **Completion handler của NIO.2 cần ngắn và không đợi đồng bộ một dependency có thể cần chính completion threads để tiến.**
- **Deadlock** là vòng chờ lẫn nhau; **thread-pool starvation** là cạn threads cho tasks cần chạy. Chặn callback có thể gây một trong hai hoặc làm tail latency tăng mạnh.
- `Future.get` và `CompletableFuture.join` **đều block khi kết quả chưa sẵn**; việc đặt chúng trong callback không biến code thành asynchronous.
- **Nối callbacks hoặc `thenCompose`** để mô tả dependency mà không giữ group thread; các continuations nặng cần offload sang executor phù hợp.
- **Offload phải bounded**, có rejection/backpressure và rõ ownership của `ByteBuffer`; queue vô hạn hoặc `CallerRunsPolicy` trên callback không phải giải pháp.
- Một socket có **tối đa một pending read và một pending write**; khởi tạo lần tiếp theo sau completion, không dùng wait để “đợi chỗ”.
- **Mọi success/failure path cần hoàn tất request state**; đừng để callback failed chỉ log và bỏ promise.
- **Timeout khi chờ Future không đồng nghĩa underlying I/O đã cancel**; timed socket operation lại có cảnh báo riêng về trạng thái channel/buffer.
- **Shutdown không được chờ group termination từ chính callback thuộc group**; coordinator ngoài group quản lý các channels và resource lifecycle.
- **TCP protocol, security và backpressure** vẫn là trách nhiệm của ứng dụng; NIO.2 không tự cung cấp framing, TLS, idempotency hoặc bảo vệ tài nguyên.
- Nội dung dùng **API hiện hành của Java 17+**, không áp dụng các mẹo legacy hoặc hành vi phụ thuộc ngẫu nhiên vào lịch hệ điều hành.

## Tài liệu chính thức

- [AsynchronousChannelGroup — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): threading, completion dispatch, shutdown và termination.
- [CompletionHandler — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): handler completed/failed và yêu cầu hoàn tất nhanh.
- [AsynchronousSocketChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): pending read/write, buffer, timed I/O, shutdown/close.
- [AsynchronousServerSocketChannel — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): accept và AcceptPendingException.
- [Future — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): get, waiting timeout và cancellation.
- [CompletableFuture — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): thenApply, thenCompose, async continuations, completion errors.
- [ThreadPoolExecutor — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded queue, rejection, worker management.
- [ByteBuffer — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position/limit và buffer ownership.
- [AsynchronousCloseException — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): I/O pending khi channel bị đóng.
