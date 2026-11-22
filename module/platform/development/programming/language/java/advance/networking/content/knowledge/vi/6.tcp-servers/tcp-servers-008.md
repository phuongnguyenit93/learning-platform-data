# Đồng bộ dữ liệu dùng chung mà không khóa toàn bộ đường đọc/ghi của máy chủ TCP

Một máy chủ TCP có thể phục vụ nhiều socket cùng lúc. Mỗi luồng xử lý một kết nối thường phải **đọc từ mạng, giải mã, kiểm tra yêu cầu, cập nhật trạng thái chung và ghi phản hồi**. Nếu đặt toàn bộ chu trình ấy trong một `synchronized` dùng chung, chỉ cần **một client chậm** cũng có thể khiến mọi client khác chờ khóa, dù các client đang thao tác trên dữ liệu độc lập.

Mục tiêu đúng là: **đồng bộ ở ranh giới dữ liệu thật sự cần nhất quán**, chọn cấu trúc thread-safe/atomic phù hợp và giữ đường I/O mạng độc lập với khóa bảo vệ dữ liệu. “Không khóa toàn bộ đường đọc/ghi” **không có nghĩa tuyệt đối không dùng khóa**; đôi khi khóa nhỏ, đúng phạm vi là lựa chọn đơn giản và an toàn nhất.

Bài này nằm trong chủ đề **Máy chủ TCP**, với Java 17+. Sau bài học, bạn có thể chọn giải pháp cho bộ đếm, session, room/subscription, quota hoặc trạng thái tổng hợp; phân biệt atomicity, visibility, thứ tự gửi phản hồi; và thiết kế backpressure thay vì tạo hàng đợi vô hạn.

## 1. Phân biệt I/O riêng của kết nối và dữ liệu được chia sẻ

Hãy tách những thứ mỗi client sở hữu khỏi những thứ nhiều client cùng truy cập.

```text
                         TCP SERVER
     accept() -> Socket A ---> Handler A --\
     accept() -> Socket B ---> Handler B ----+--> Shared State
     accept() -> Socket C ---> Handler C --/       |
             |                     |               +-- counters
             |                     |               +-- sessions/rooms
             v                     v               +-- quota/metrics
       socket-specific        socket-specific
       reader/writer           parser/buffers
```

- **Dữ liệu riêng từng kết nối:** `Socket` đã accept, bộ đệm đọc chưa đủ frame, parser state, số thứ tự request trong kết nối, output queue riêng của client. Nếu chỉ một handler sở hữu dữ liệu này, không cần khóa toàn cục.
- **Dữ liệu chia sẻ giữa các kết nối:** map các user đang hoạt động, số lần xử lý, quota, trạng thái một phòng chat, cache chung, subscription registry. Nhiều luồng cùng truy cập thì cần chính sách đồng bộ.
- **Dữ liệu bất biến:** cấu hình/read-only snapshot sau khi công bố an toàn thường có thể đọc không khóa; muốn thay đổi thì công bố một bản mới theo cơ chế atomic/visibility.

Điểm mấu chốt: `read()`, `readLine()`, `accept()` và `write()` có thể **chặn bởi mạng**, còn thao tác cập nhật map/counter thường chỉ nên chiếm một khoảng rất ngắn trong CPU/RAM. Không gộp hai loại công việc vào cùng một critical section trên mọi client.

## 2. Ví dụ thiết kế sai: giữ khóa toàn cục khi chờ socket

Mã sau là **đoạn minh họa, không phải chương trình độc lập**; giả định `serverLock`, `in`, `out` và `sharedMap` đã được định nghĩa:

```java
synchronized (serverLock) {
    String command = in.readLine();       // Có thể đợi dữ liệu vô hạn.
    updateSharedMap(sharedMap, command);  // Chỉ bước này cần đồng bộ.
    out.write("OK\n");                    // Có thể chờ peer nhận chậm.
    out.flush();
}
```

Nếu client A kết nối nhưng chậm gửi newline, handler A giữ `serverLock` trong `readLine()`. B, C, D dù đã có lệnh sẵn cũng không vào được phần xử lý. Nếu peer A đọc phản hồi chậm, thao tác ghi cũng có thể block trong khi vẫn giữ khóa. Đây là nguy cơ **head-of-line blocking do thiết kế khóa của ứng dụng**; nó khác với cơ chế giữ thứ tự byte nội bộ của TCP.

Cách tách hợp lý:

```text
Handler A:
  1. Đọc và ghép frame A       [không giữ khóa dữ liệu toàn cục]
  2. Validate, parse           [dữ liệu cục bộ]
  3. Atomic update nhỏ         [chỉ vùng dữ liệu cần thiết]
  4. Tạo response              [dữ liệu cục bộ]
  5. Gửi trên socket A         [không giữ khóa dữ liệu toàn cục]
```

**Không gọi I/O mạng, chờ `Future.get()`, `Thread.sleep()`, gọi remote API hoặc thao tác blocking dài bên trong khóa dữ liệu chung.** Khi nghiệp vụ cần chờ tài nguyên bên ngoài, nên tách bước đó ra và xác định lại cách giữ invariant (ví dụ chuyển sang reservation/state machine có trạng thái rõ ràng).

## 3. Ba thuộc tính của thread safety: atomicity, visibility và ordering

**Atomicity (tính nguyên tử):** thao tác được quan sát như một lần thay đổi không thể bị xen giữa tại phạm vi được hứa hẹn. Ví dụ `AtomicLong.incrementAndGet()` cập nhật một số nguyên tử; `ConcurrentHashMap.merge(key, 1L, Long::sum)` cập nhật nguyên tử giá trị cho **một key**.

**Visibility (khả năng nhìn thấy):** các thay đổi từ thread này được thread khác nhìn thấy theo quy tắc *happens-before* của Java Memory Model. Đồng bộ đúng có thể đến từ `volatile`, `synchronized`, `AtomicReference`, các lớp concurrency hoặc cơ chế công bố bất biến. Dùng `HashMap` thường rồi chỉ “hy vọng thread khác nhìn thấy” là không hợp lệ.

**Ordering (thứ tự):** thứ tự thay đổi dữ liệu chung và thứ tự response phải được định nghĩa rõ. TCP giữ thứ tự byte **trong từng chiều của từng kết nối**, nhưng không tự xếp thứ tự thao tác của các handler từ những socket khác nhau. Hai client gửi gần như cùng lúc không có “thứ tự toàn cục” mặc định.

Ví dụ `volatile long count; count++;` vẫn không an toàn cho bộ đếm: `volatile` giúp visibility của từng lần đọc/ghi, nhưng `count++` là **đọc → cộng → ghi**, có thể mất cập nhật khi nhiều thread xen nhau.

```java
// Minh họa đúng cho một bộ đếm dùng chung (không phải class độc lập).
AtomicLong count = new AtomicLong();
long next = count.incrementAndGet(); // read-modify-write nguyên tử
```

Nguyên tử của **một biến** vẫn không có nghĩa hai biến hoặc nhiều key được cập nhật trong **một giao dịch nguyên tử**.

## 4. Chọn cơ chế theo đúng invariant

| Dạng dữ liệu chung | Công cụ Java 17+ thường phù hợp | Phạm vi và hạn chế |
| --- | --- | --- |
| Một bộ đếm cần giá trị chính xác khi cập nhật | `AtomicLong.incrementAndGet()`, `compareAndSet` | Atomic cho đúng một biến; không gom nhiều trường |
| Bộ đếm thống kê nóng, nhiều luồng ghi | `LongAdder.increment()` | Tối ưu contention; `sum()` có thể không là snapshot nguyên tử khi đang ghi |
| Map với thao tác theo từng key | `ConcurrentHashMap.merge`, `compute`, `putIfAbsent` | Atomic theo key/operation; không tạo transaction qua nhiều key |
| Một nhóm trường cần đọc như một phiên bản nhất quán | Bản ghi immutable + `AtomicReference<State>` | Thay cả state bằng CAS; hàm cập nhật phải thuần và có thể chạy lại |
| Vài trường cần cập nhật đồng thời, contention không cao | `synchronized`/`ReentrantLock` quanh **đoạn cập nhật ngắn** | Chỉ khóa các biến có chung invariant; thả khóa trước I/O |
| Chủ sở hữu duy nhất cho một thực thể/phòng | Queue vào actor/owner task hoặc phân vùng theo key | Không chia sẻ mutable state giữa nhiều writer; phải có queue bounded và xử lý overload |
| Trạng thái chỉ thay bằng snapshot mới | `volatile` hoặc `AtomicReference` trỏ tới đối tượng immutable | Công bố nguyên bản; tuyệt đối không sửa map/list sau khi đã publish |

**Không có một primitive phù hợp mọi bài toán.** `ReadWriteLock` có thể hợp lý khi nhiều đọc và ít cập nhật trong RAM, nhưng nếu giữ read lock trong lúc ghi socket thì client chậm vẫn làm writer chờ. `StampedLock` yêu cầu sử dụng đúng quy tắc validate/retry, không phải bản nâng cấp mặc định cho mọi TCP server.

## 5. Bộ đếm và map dùng chung: loại bỏ read-modify-write không nguyên tử

Thiết kế sau có **lost update** dù map là `ConcurrentHashMap`:

```java
// Minh họa sai: get + put không phải một phép tăng nguyên tử.
long previous = counters.getOrDefault("apple", 0L);
counters.put("apple", previous + 1);
```

Giả sử A và B cùng đọc `previous=10`, mỗi thread tính `11` rồi đều ghi `11`. Kết quả đáng ra là `12` nhưng chỉ là `11`. ConcurrentMap bảo vệ cấu trúc nội bộ khỏi race, **không tự ghép hai API call thành một transaction**.

Thay bằng một operation có tính nguyên tử trên key:

```java
// Minh họa với counters là ConcurrentHashMap<String, Long>.
counters.merge("apple", 1L, Long::sum);
```

`merge` dùng thao tác atomic theo key và áp dụng hàm cộng trên giá trị hiện có. Hàm remapping trong `merge`/`compute` cần **nhanh, không blocking, không side effect**, không gọi socket, log mạng hoặc làm thay đổi chính map một cách đệ quy. Dùng `Long` có nguy cơ tràn khi quá lớn; hệ thống thực cần chọn kiểu và chính sách overflow.

Nếu chỉ cần đo metric tại thời điểm có tải, có thể dùng:

```java
// Minh họa, cùng package java.util.concurrent.
ConcurrentHashMap<String, LongAdder> hits = new ConcurrentHashMap<>();
hits.computeIfAbsent("apple", ignored -> new LongAdder()).increment();
long currentEstimate = hits.get("apple").sum();
```

`LongAdder` giúp giảm tranh chấp khi nhiều writer, nhưng `sum()` **không phải giao dịch nguyên tử đối với các update đang đồng thời**. Đừng dùng tổng này như một cơ chế giữ quota/hạn mức tài chính cần chính xác.

## 6. Chương trình Java 17+: nhiều client TCP cập nhật shared state

**`ConcurrentTcpCounters.java`** tạo một `ServerSocket` trên loopback với port do OS cấp, 4 client và 4 handler. Mỗi client gửi 200 lượt gồm hai lệnh `INC apple` và `INC orange`, sau đó đóng **chiều gửi** để server biết stream lệnh của client đã kết thúc. Handler đọc và xử lý từ socket **riêng**, cập nhật map chung qua `merge`, rồi trả `OK 400`. Không có một `synchronized` nào bọc vòng `readLine()` hoặc `write()` của tất cả client.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentTcpCounters {
    private static final int CLIENTS = 4;
    private static final int ROUNDS = 200;

    private static void handle(
            Socket socket, ConcurrentHashMap<String, Long> counters)
            throws IOException {
        try (socket) {
            socket.setSoTimeout(10_000);
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            socket.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            socket.getOutputStream(), StandardCharsets.UTF_8));

            int processed = 0;
            String line;
            while ((line = in.readLine()) != null) {
                String key;
                if (line.equals("INC apple")) {
                    key = "apple";
                } else if (line.equals("INC orange")) {
                    key = "orange";
                } else {
                    throw new IOException("Invalid command");
                }
                counters.merge(key, 1L, Long::sum);
                processed++;
            }

            // Only this handler writes to this client's output stream.
            out.write("OK " + processed);
            out.newLine();
            out.flush();
        }
    }

    private static String runClient(InetAddress address, int port)
            throws IOException {
        try (Socket socket = new Socket(address, port)) {
            socket.setSoTimeout(10_000);
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            socket.getOutputStream(), StandardCharsets.UTF_8));
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            socket.getInputStream(), StandardCharsets.UTF_8));

            for (int i = 0; i < ROUNDS; i++) {
                out.write("INC apple");
                out.newLine();
                out.write("INC orange");
                out.newLine();
            }
            out.flush();
            socket.shutdownOutput();

            return in.readLine();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        ConcurrentHashMap<String, Long> counters =
                new ConcurrentHashMap<>();
        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(CLIENTS);
        ExecutorService clientWorkers =
                Executors.newFixedThreadPool(CLIENTS);

        try (ServerSocket server = new ServerSocket(0, CLIENTS, loopback)) {
            server.setSoTimeout(10_000);
            int port = server.getLocalPort();

            List<Future<String>> clients = new ArrayList<>();
            for (int i = 0; i < CLIENTS; i++) {
                clients.add(clientWorkers.submit(
                        () -> runClient(loopback, port)));
            }

            List<Future<?>> handlers = new ArrayList<>();
            for (int i = 0; i < CLIENTS; i++) {
                Socket accepted = server.accept();
                handlers.add(serverWorkers.submit(() -> {
                    handle(accepted, counters);
                    return null;
                }));
            }

            boolean allAcknowledged = true;
            for (Future<String> response : clients) {
                allAcknowledged &=
                        ("OK " + (2 * ROUNDS)).equals(response.get());
            }
            for (Future<?> handler : handlers) {
                handler.get();
            }

            Map<String, Long> afterAllHandlers = Map.copyOf(counters);
            System.out.println("All responses OK: " + allAcknowledged);
            System.out.println(
                    "apple: " + afterAllHandlers.get("apple"));
            System.out.println(
                    "orange: " + afterAllHandlers.get("orange"));
        } finally {
            clientWorkers.shutdownNow();
            serverWorkers.shutdownNow();
        }
    }
}
```

Chạy trên JDK 17+:

```sh
javac -encoding UTF-8 ConcurrentTcpCounters.java
java ConcurrentTcpCounters
```

Stdout khi chạy thành công:

```text
All responses OK: true
apple: 800
orange: 800
```

Tại sao kết quả xác định?

1. Mỗi client gửi `200 × 2 = 400` lệnh hợp lệ; mỗi handler tăng bộ đếm **nguyên tử theo key**. Bốn client tạo tổng `800` lần tăng cho từng key.
2. `Future.get()` trên tất cả handler hoàn thành trước khi main đọc kết quả cuối. Khi đó không còn writer vào map, nên `Map.copyOf(counters)` biểu diễn đúng trạng thái **sau khi hoạt động đã yên**.
3. Trong khi các handler vẫn đang chạy, `Map.copyOf(counters)` hay việc duyệt `ConcurrentHashMap` **không tạo snapshot nguyên tử đồng thời cho nhiều key**. Giữa một lệnh tăng `apple` và một lệnh tăng `orange`, hai giá trị có thể tạm lệch.
4. Client nhận ACK của **giao thức demo** sau khi server đã gọi `merge` cho tất cả lệnh trên kết nối đó. Đây không phải bằng chứng dữ liệu đã được ghi xuống ổ đĩa: demo lưu toàn bộ counter **trong RAM** và chỉ định nghĩa ACK theo phạm vi RAM.

Mã giới hạn loopback, số client và số lượt gửi để demo xác định. Trên production phải hạn chế số kết nối đang hoạt động, độ dài dòng, số request, thời gian hoạt động và trạng thái xử lý khi client gửi quá nhanh hoặc không gửi newline. `BufferedReader.readLine()` **không tự giới hạn chiều dài dòng**; nếu dữ liệu đến từ Internet cần parser bounded.

Lưu ý Java 17: `ExecutorService` chưa được dùng dưới cú pháp try-with-resources trong ví dụ; chương trình gọi `shutdownNow()` trong `finally` sau khi chờ futures. Với server dài hạn cần thiết kế quiesce/shutdown chính xác hơn; gọi shutdown pool **không tự động đóng mọi socket đang block ở I/O**.

## 7. Khi nhiều trường phải nhất quán: thay cả state bất biến

Giả sử máy chủ ghi hai metric `accepted` và `rejected`, và luồng monitoring phải nhìn thấy cả hai ở **cùng một thời điểm logic**. Hai `AtomicLong` riêng rẽ chống lost update cho mỗi trường, nhưng đọc `accepted.get()` rồi `rejected.get()` không đảm bảo hai giá trị thuộc cùng một phiên bản.

Có thể công bố một bản ghi immutable gồm cả hai trường bằng `AtomicReference<Metrics>`. Mỗi cập nhật dùng CAS để thay **toàn bộ bản ghi**. Một luồng đọc `metrics.get()` lấy đúng một snapshot nhất quán của hai trường. Ví dụ độc lập **`AtomicTcpMetrics.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicTcpMetrics {
    private record Metrics(long accepted, long rejected) {}

    public static void main(String[] args) throws Exception {
        AtomicReference<Metrics> metrics =
                new AtomicReference<>(new Metrics(0, 0));
        ExecutorService workers = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int worker = 0; worker < 4; worker++) {
                final boolean accept = worker % 2 == 0;
                jobs.add(workers.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        metrics.updateAndGet(old -> accept
                                ? new Metrics(
                                        old.accepted() + 1, old.rejected())
                                : new Metrics(
                                        old.accepted(), old.rejected() + 1));
                    }
                }));
            }
            for (Future<?> job : jobs) {
                job.get();
            }

            Metrics snapshot = metrics.get();
            System.out.println("Accepted: " + snapshot.accepted());
            System.out.println("Rejected: " + snapshot.rejected());
            System.out.println("Total: " +
                    (snapshot.accepted() + snapshot.rejected()));
        } finally {
            workers.shutdownNow();
        }
    }
}
```

Chạy:

```sh
javac -encoding UTF-8 AtomicTcpMetrics.java
java AtomicTcpMetrics
```

Kết quả xác định:

```text
Accepted: 2000
Rejected: 2000
Total: 4000
```

`updateAndGet(old -> new Metrics(...))` có thể gọi lại lambda khi CAS thất bại vì một writer khác vừa cập nhật. Vì vậy lambda phải **thuần**: không ghi socket, không tăng bộ đếm bên ngoài, không gọi cơ sở dữ liệu, không gửi message. Trong ví dụ, mọi side effect thực sự là duy nhất lần công bố state mới thành công.

**Đánh đổi:** mỗi cập nhật tạo object mới và CAS có thể phải retry nhiều khi contention cao. Phù hợp cho state nhỏ có invariant gắn chặt, cấu hình phiên bản hoặc metadata quản lý; không mặc định dùng cho hàng triệu counter nóng. Khi một transaction liên quan DB, trạng thái bền vững và quy tắc exactly-once, atomic snapshot trong RAM **không thay được transaction của kho dữ liệu**.

## 8. Những invariant nào cần khóa ngắn hoặc thiết kế lại dữ liệu?

Giả sử có `maxConnections=100`, và thread phải thực hiện “chỉ nhận client mới nếu còn slot”. Đoạn sau có race:

```java
// Sai khi nhiều handler đồng thời kiểm tra rồi tăng.
if (active.get() < maxConnections) {
    active.incrementAndGet();
    admitClient();
}
```

Hai thread có thể đều quan sát 99 rồi đều tăng lên 101. Một giải pháp CAS kiểm tra và tăng **trong cùng một vòng**:

```java
// Method minh họa độc lập về mặt chữ ký.
static boolean tryReserve(AtomicInteger active, int max) {
    while (true) {
        int count = active.get();
        if (count >= max) {
            return false;
        }
        if (active.compareAndSet(count, count + 1)) {
            return true;
        }
    }
}
```

Chỉ gọi `admitClient()` **sau khi** reserve thành công. Khi xử lý kết thúc, trả slot **đúng một lần** trong `finally` tương ứng; nếu reserve thất bại thì không được giảm. Nếu giới hạn chứa nhiều điều kiện/phần dữ liệu liên quan (user, room, quota tổng), có thể cần **một lock ngắn bảo vệ toàn bộ invariant**, một actor phụ trách key, hoặc transaction DB — không dùng các thao tác atomic rời rạc rồi cho rằng cả cụm nguyên tử.

Ví dụ mô hình khóa ngắn:

```java
// Minh họa: chỉ cập nhật state trong RAM dưới khóa.
Decision decision;
synchronized (stateLock) {
    decision = decideAndMutateSharedState(command);
}
// Sau khi thả khóa, mới thực hiện I/O mạng.
sendResponse(socket, decision);
```

`decision` nên là kết quả bất biến cho request đó. Nếu `sendResponse` thất bại, trạng thái đã cập nhật không tự rollback: chính sách nghiệp vụ phải định nghĩa liệu response lỗi có cần retry/idempotency hay cơ chế bù trừ. Nếu validation dài hoặc phụ thuộc I/O, đừng giữ lock để chờ nó.

## 9. Cùng một socket: đồng bộ **đầu ghi của kết nối**, không khóa toàn server

Tránh khóa chung **không đồng nghĩa nhiều thread muốn ghi gì lên cùng `OutputStream` cũng được**. Khi nhiều nhiệm vụ bất đồng bộ cùng trả response cho một client, các byte của hai message có thể xen nhau nếu các lệnh ghi, header và payload bị interleave theo thời điểm. TCP chỉ bảo đảm thứ tự **dãy byte đã thực sự ghi**, nó không định nghĩa biên message và không tự giữ frame nguyên vẹn cho code Java.

Ví dụ có hai producer muốn gửi hai frame length-prefix:

```text
Producer A: [length(A)] [payload(A)]
Producer B: [length(B)] [payload(B)]

Nếu đồng thời ghi lên cùng output:
[length(A)] [length(B)] [payload(A)] [payload(B)]
=> Parser peer có thể hiểu nhầm length(B) là đầu payload(A).
```

Giải pháp ưu tiên là **một writer owner cho mỗi connection**:

```text
Request handler A --\
Request handler B ----> bounded outbound queue(socket-42) -> WRITER(socket-42)
Notification task ----/                                   -> Socket OutputStream
```

Producer tạo **frame hoàn chỉnh, immutable** rồi `offer` vào queue; một writer lấy các frame và gửi theo thứ tự nhận vào queue. Nếu dùng `ArrayBlockingQueue`/`BlockingQueue`, chọn capacity, timeout hoặc policy khi đầy. Queue đảm bảo thứ tự **enqueue thành công**, không tự quyết định “thứ tự nghiệp vụ” giữa hai producer đồng thời; nếu cần order theo request ID thì phải lập quy tắc tại layer giao thức.

Trong hệ thống đơn giản, một lock **riêng cho socket đó** có thể bao quanh quá trình ghi trọn frame để tránh interleaving, nhưng ghi vào socket có thể block khi peer chậm; không được chia lock ấy cho mọi socket. Với nhiều producer/lưu lượng lớn, bounded queue + owner writer thường cho phép cô lập client chậm và áp dụng backpressure rõ hơn.

## 10. Đồng bộ theo key, actor, hoặc event loop: chọn theo cách chia sẻ

**Per-key atomic update:** Map chứa counter, session hoặc object của từng user/room. Những thay đổi chỉ ảnh hưởng một key có thể dùng `ConcurrentHashMap.compute` hoặc atomic state trong value. Callback tính toán phải ngắn; tránh gọi thao tác blocking hoặc sửa đệ quy cùng map từ callback.

**Single-writer / actor theo room:** Tất cả thay đổi của cùng room đi qua một hàng đợi và một owner task, trong khi các room khác vẫn tiến triển độc lập. Ưu điểm là invariant của room có thể dễ suy luận; chi phí là queue phải bounded và owner chậm có thể làm room đó backlog. Một TCP connection đọc chưa xong frame thì handler riêng phải ghép/parse đủ rồi mới gửi command vào actor.

**Sharding/partitioning:** Chọn owner theo `hash(key)` hoặc phân vùng cố định. Các key cùng shard có thứ tự update theo queue, key khác shard xử lý song song. Thao tác qua nhiều shard cần giao thức phối hợp hoặc storage transaction; không tự xuất hiện atomicity toàn hệ thống.

**NIO/event loop:** Với `SocketChannel` và `Selector`, một event loop có thể quản lý nhiều connection, giảm số thread blocking. Dù vậy, **không làm I/O mạng ngoài blocking, xử lý CPU nặng hoặc chờ DB ngay trong event-loop thread**. Shared state vẫn cần ownership hoặc synchronization khi có nhiều event loop/worker. Event loop không tự giải quyết race dữ liệu của các thread khác.

Một nguyên tắc chung: **để dữ liệu đi đến đúng owner**, rồi xử lý cập nhật ngắn; đừng đặt một khóa dài trên toàn bộ dòng dữ liệu chỉ vì có nhiều socket.

## 11. Backpressure và giới hạn tài nguyên là một phần của thiết kế đồng thời

Nếu handler cập nhật rất nhanh nhưng writer gửi response đến client chậm, output queue sẽ tăng liên tục trừ khi có giới hạn. Tương tự, một `ExecutorService` có hàng đợi tác vụ không giới hạn có thể giữ quá nhiều frame, byte[] hoặc context của client, dẫn tới áp lực heap/GC và đứt dịch vụ.

Chọn các giới hạn cụ thể:

- **Kết nối:** số socket/handler đồng thời, timeout khi kết nối idle, giới hạn theo tenant/client.
- **Input:** kích thước frame, số byte chưa hoàn chỉnh, số command trong một window, tốc độ đọc/parse.
- **Shared state:** kích thước map, TTL/cleanup của session, số key, giới hạn giá trị.
- **Output:** bounded queue riêng cho connection, cách xử lý khi queue đầy (chờ có giới hạn, trả lỗi, drop thông báo được phép, hoặc đóng peer).
- **Worker pool:** queue bounded và rejection policy; không bỏ qua `RejectedExecutionException` hoặc tạo thread vô hạn để xử lý backlog.

`BlockingQueue.put()` có thể chặn thread gửi khi full; `offer()` có thể từ chối ngay, `offer(timeout)` chờ có giới hạn. Quyết định phụ thuộc SLA/protocol. **Nếu không được phép làm mất response bắt buộc**, không tự chọn drop như một tối ưu; trả lỗi/giảm tốc độ/đóng kết nối có kiểm soát và đảm bảo state nghiệp vụ nhất quán.

Đừng đưa `Socket.write` vào callback `ConcurrentHashMap.compute` hoặc giữ `ReentrantLock` của state trong lúc đợi queue rỗng. Làm vậy sẽ đưa tốc độ của peer chậm trở thành bottleneck của toàn bộ các request cần state ấy.

## 12. Công bố snapshot và quan sát metric đúng mức đảm bảo

Một dashboard có thể chấp nhận metric *best effort*, nhưng bộ kiểm soát quota cần kết quả nhất quán:

| Câu hỏi | Cách đọc/đồng bộ phù hợp |
| --- | --- |
| “Mỗi key đã nhận bao nhiêu lệnh khi không còn update?” | Đọc `ConcurrentHashMap` sau khi `Future.get()`/quiescence |
| “Ước lượng request/s lúc hệ thống đang chạy?” | `LongAdder`, sampling; chấp nhận số đo giữa chừng |
| “Có thể nhận thêm một session mà không vượt quota?” | CAS/lock/actor atomic cho **check + reserve** |
| “Hai trường accepted/rejected phải cùng version?” | Immutable `State` + `AtomicReference.get()` |
| “Cần báo cáo chính xác trên nhiều key trong khi vẫn có writer?” | State tổng thể được version hóa, quiesce, snapshot protocol, hoặc transaction — không kỳ vọng `Map.copyOf` tự đóng băng tất cả writer |
| “Response nghiệp vụ phải sau khi commit DB?” | Transaction DB + protocol acknowledgement; bộ nhớ concurrent chỉ giải quyết trong một JVM |

Phân biệt **thread-safe collection** với **thread-safe algorithm**. Một `ConcurrentHashMap` cho phép `get` và `put` an toàn về mặt cấu trúc, nhưng chuỗi “kiểm tra còn chỗ → tăng counter → cấp tài nguyên → trả response” cần hợp đồng atomicity của **toàn bộ quyết định**.

Với cấu hình read-mostly, công bố một đối tượng immutable mới qua `volatile`/`AtomicReference` cho phép các reader dùng một bản không đổi mà không tranh lock. Tránh trả reference đến `HashMap`/`ArrayList` mutable rồi để thread khác cập nhật sau khi publish.

## 13. Kết thúc kết nối, huỷ tác vụ và vòng đời state dùng chung

Đồng bộ dữ liệu chung còn liên quan tới việc xóa/giải phóng tài nguyên:

1. Khi handler rời kết nối, thực hiện cleanup trong `finally`, hủy subscription, trả quota đã reserve và đóng `Socket` một cách **idempotent** nếu nhiều đường lỗi có thể cùng gọi cleanup.
2. **`ExecutorService.shutdown()`** ngừng nhận task mới; `awaitTermination` chờ trong một khoảng có giới hạn; khi buộc dừng, `shutdownNow()` yêu cầu interrupt nhưng **không bảo đảm** đánh thức mọi blocking socket read trên classic `Socket`. Chủ sở hữu cần quản lý và đóng socket tương ứng để giải phóng I/O.
3. Nếu sở hữu queue output, định nghĩa cách đóng queue, flush frame còn lại, xử lý “poison pill”/trạng thái dừng mà không bị mắc kẹt vì queue đầy. Không chờ vô hạn dưới lock của shared state.
4. **Đóng kết nối sau khi gửi response** không chứng minh peer đã đọc/commit response. Nếu request thay đổi dữ liệu bền vững, thiết kế idempotency và application acknowledgement riêng.
5. Map session có nguy cơ stale entry khi handler crash/timeout; dùng identity/token theo session để tránh cleanup của phiên cũ xóa nhầm phiên mới cùng user. Ví dụ `sessions.remove(userId, expectedSession)` chỉ xóa khi value còn đúng object mong đợi.

Với bất kỳ cơ chế concurrency nào, hãy nêu rõ ai là **owner của socket**, owner của entry trong shared map, và ai được quyền đóng/evict. Nếu không xác định owner, các race cleanup thường khó chẩn đoán hơn race tăng counter.

## 14. Kiểm thử tính đúng đắn thay vì dựa vào timing

Một thử nghiệm “chạy một client, thấy OK” không chứng minh server không race. Kiểm thử cần nhiều client và **kiểm tra invariant cuối cùng**:

- Cho nhiều client đồng thời gửi lệnh lên cùng key; nếu mỗi client gửi `N` lệnh, giá trị cuối phải bằng `clients × N` (không lost update).
- Cho các client gửi trên **nhiều key**; xác nhận từng key và kiểm tra các invariant chỉ sau quiescence, hoặc dùng snapshot atomic nếu cần kiểm tra trong lúc đang update.
- Chủ động tạo client chậm gửi/đọc, client không gửi newline, disconnect giữa frame, socket timeout, writer queue full; xác minh các client độc lập vẫn tiến triển.
- Nếu nhiều producer gửi response cùng một socket, thử interleaving header/payload; parser đối diện chỉ được thấy frame hợp lệ, đúng thứ tự đã định nghĩa.
- Dùng `CountDownLatch`/`CyclicBarrier` để đồng bộ điểm khởi đầu khi cần tái hiện race; không dùng `Thread.sleep` như chứng cứ rằng mọi thread đã xử lý xong.
- Thu thập thời gian giữ khóa, số lần CAS retry, độ sâu queue, số handler, số socket, p95/p99 và timeout. Thông lượng tăng nhưng độ trễ một số client tăng bất thường có thể biểu thị contention hoặc backpressure chưa đúng.

Hai chương trình ở trên kiểm tra các bất biến **đếm chính xác sau các task hoàn thành** và **snapshot bất biến nhiều trường**. Chúng không chứng minh performance trong production, vì số client, mạng loopback, độ dài request và tải thực tế khác nhau.

## 15. Lỗi thiết kế thường gặp

1. **Đồng bộ bằng `synchronized(server)` quanh toàn bộ `read/process/write`:** một client chậm chặn tất cả. Chỉ giữ khóa ở vùng dữ liệu chung cần cập nhật.
2. **Đổi `HashMap` thành `ConcurrentHashMap` rồi vẫn viết `get→put`:** cấu trúc map an toàn nhưng cập nhật có thể mất. Dùng `merge`/`compute`/CAS.
3. **Dùng `volatile int` cho `++`:** visibility không tạo atomicity cho read-modify-write. Dùng `AtomicInteger` hoặc cơ chế mạnh hơn.
4. **Dùng hai `AtomicLong` và kỳ vọng snapshot của cả hai cùng lúc:** hai `get` không thuộc một phiên bản. Dùng immutable state hoặc lock ngắn.
5. **Đọc `LongAdder.sum()` để quyết định quota tuyệt đối:** kết quả có thể thay đổi trong lúc cập nhật. Dùng reservation atomic/transaction phù hợp.
6. **Gọi socket/DB bên trong `compute` hoặc CAS lambda:** rủi ro blocking, retry và side effect lặp. Đưa I/O ra ngoài.
7. **Nhiều thread ghi header và body lên cùng socket mà không điều phối:** byte stream có thể làm hỏng framing. Dùng một writer per connection hoặc lock ghi trọn frame của riêng socket.
8. **Queue giữa handler và writer không có giới hạn:** client chậm khiến heap tăng vô hạn. Đặt capacity và overload policy.
9. **Không trả quota trong `finally` hoặc trả hai lần:** lệch state khi lỗi/timeout. Quản lý reservation theo ownership và cleanup idempotent.
10. **Kiểm thử bằng sleep và assert thứ tự giữa các socket:** TCP không định nghĩa thứ tự toàn cục cho các connection độc lập. Kiểm tra invariant và thứ tự protocol bạn đã định nghĩa.
11. **Thấy `Future.get()`/ACK thì cho rằng DB transaction thành công:** phải dựa trên hợp đồng commit/response của ứng dụng, không dựa vào thread pool/TCP.
12. **Dùng read lock để đọc rồi ghi socket:** lock giữ dài vì mạng; nên sao chép snapshot cần thiết rồi thả lock trước I/O.

## 16. Checklist ra quyết định cho một TCP server

Trước khi thêm khóa, trả lời lần lượt:

1. **Trạng thái nào thực sự dùng chung?** Chia local state theo socket khỏi state theo user/room/global.
2. **Invariant là gì?** Một counter/key có thể dùng atomic operation; nhiều trường/key có thể cần một transaction/state version.
3. **Critical section có thể block không?** Không nên đặt socket, remote I/O hoặc hàng đợi đợi vô hạn trong khóa data.
4. **Ai ghi vào một connection?** Chỉ một owner hoặc một cơ chế serialize full frame, với giới hạn output queue.
5. **Hệ thống làm gì khi quá tải?** Bounded concurrency, timeout, backpressure và cleanup rõ.
6. **Thứ tự nào cần cam kết?** Theo connection, theo key/room hay toàn cục; lưu ý mỗi scope có chi phí khác nhau.
7. **Đã kiểm tra tình huống lỗi?** Disconnect, retry, timeout, race cleanup, queue full, response chưa tới và snapshot đang update.

Nguyên tắc thực hành: **đọc/ghi mạng là việc của connection owner; cập nhật trạng thái dùng chung là thao tác nguyên tử nhỏ theo đúng invariant; giao thức ACK, queue và vòng đời kết nối phải có giới hạn và ownership rõ ràng**. Nhờ vậy các client độc lập có thể tiến triển song song mà tính đúng đắn của state vẫn được bảo đảm.

Nguồn API để tham khảo:
- [Java SE 17 `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [`AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html), [`AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html) và [`LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`BlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [`Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html), [`ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html).