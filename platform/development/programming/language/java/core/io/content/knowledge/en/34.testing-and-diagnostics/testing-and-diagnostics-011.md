# Kiểm tra event, callback và thao tác đồng thời theo cách xác định trong Java I/O

## 1. Vấn đề: I/O đúng nhưng bài test thất thường

Trong các chương trình Java I/O, nhiều sự kiện không xảy ra đúng một thời điểm cố định: `WatchService` nhận thay đổi thư mục, `CompletionHandler` báo hoàn tất đọc/ghi, thread pool chạy các thao tác tệp, hoặc callback tiếp tục công việc sau khi kênh hoàn thành một phần.

Một bài kiểm thử kiểu này dễ trở thành **flaky test**: cùng mã, cùng input nhưng có lúc pass, có lúc fail do tốc độ máy, lịch chạy thread, cache, hệ điều hành hay cơ chế của file system. Chẳng hạn:

~~~java
startAsyncCopy();
Thread.sleep(100);
assertOutputExists(); // Sai: 100 ms không chứng minh copy đã xong.
~~~

Đây là **mã minh họa lỗi**, không phải chương trình độc lập. Máy phát triển có thể hoàn thành nhanh hơn 100 ms, trong khi máy CI đang tải nặng có thể cần nhiều thời gian. Tăng lên 2 giây chỉ làm test chậm hơn chứ không xây dựng được mối quan hệ đúng về mặt nhân quả.

**Kiểm thử theo cách xác định (deterministic testing)** nghĩa là kiểm tra **trạng thái và điều kiện hoàn thành được xác định rõ**, điều khiển những điểm đồng bộ cần thiết, không lấy khoảng thời gian chờ làm bằng chứng công việc đã hoàn tất. Phải phân biệt:

- **Thứ tự logic mà bài test có quyền kiểm soát:** tạo input trước, đăng ký callback, đợi một tín hiệu hoàn thành, sau đó kiểm tra kết quả.
- **Thứ tự thực thi mà scheduler/OS quyết định:** thread nào chạy trước, callback vào lúc nào, số event được gộp ra sao. Đây thường **không** phải thứ tự nên assert cứng.
- **Sự đúng đắn của trạng thái cuối:** dữ liệu đọc/ghi đúng byte, mỗi request báo một kết quả kết thúc, không có dữ liệu ngoài phạm vi.
- **Tính chất cạnh tranh:** bài test có kiểm soát để tạo ra interleaving quan trọng và kiểm tra ứng dụng vẫn đúng khi các thao tác thực sự có thể chạy đồng thời.

Sau bài này, bạn sẽ dùng được `CountDownLatch`, `Future`, `CompletableFuture`, `CompletionHandler`, timeout hữu hạn, root tạm riêng và chiến lược kiểm tra sự kiện `WatchService` một cách đáng tin hơn.

## 2. Thế nào là một assertion xác định?

Câu hỏi đúng khi kiểm tra I/O bất đồng bộ không phải “Sau 100 ms có kết quả chưa?” mà là “**Điều kiện nào chứng minh thao tác đã hoàn thành?**”.

| Tình huống | Assertion dễ flaky | Cách kiểm tra vững hơn |
| --- | --- | --- |
| Ghi file bất đồng bộ | Ngủ 100 ms rồi `Files.exists` | Đợi callback/`Future` báo hoàn tất, sau đó đọc kiểm chứng nội dung |
| Nhận một callback | `sleep` rồi so bộ đếm | `CompletableFuture.get(timeout)` hoặc `CountDownLatch.await(timeout)` |
| Hai worker cùng chạy | Đợi vài ms rồi tin là song song | Dùng latch/barrier xác nhận **cả hai đã sẵn sàng** trước khi cho tiếp tục |
| `WatchService` báo tạo file | Cứng nhắc assert đúng 1 `ENTRY_CREATE` trên mọi OS | Test parser bằng event giả lập; integration test kết hợp snapshot trạng thái và quan sát event không bắt buộc |
| Xử lý dữ liệu trên socket | Một lần `read` phải ra trọn message | Dùng framing, lặp đọc đến đủ byte và đợi completion |
| Kiểm tra thứ tự hoàn thành | Callback A phải luôn trước B | Nếu yêu cầu nghiệp vụ có thứ tự, dùng sequence/id và điều phối; nếu không, assert tập kết quả |
| Kiểm thử timeout | Đợi vô hạn để xem có treo không | Deadline hữu hạn, báo rõ thời điểm thất bại và cleanup |
| Kiểm tra exception | Lỗi ở worker được tự ném vào thread test | Thu lỗi qua `Future.get`, completion hoặc bộ thu lỗi của test |

**Tính xác định không đồng nghĩa mọi thread chạy theo cùng lịch mỗi lần.** Ta cần làm cho điều kiện *pass/fail* không phụ thuộc sự may rủi của lịch chạy, hoặc chủ động điều khiển những điểm đua cần kiểm tra.

## 3. Nguyên tắc thiết kế để tránh flaky test

1. **Một scenario, một phạm vi tài nguyên riêng:** tạo thư mục tạm cho từng bài test; không dùng file chung cố định.
2. **Thiết lập trạng thái đầu rõ ràng:** khởi tạo file/queue/buffer trước khi phát sự kiện hoặc khởi chạy tác vụ.
3. **Sự kiện kết thúc có tên:** ví dụ `CompletableFuture<Void> saved` đại diện “đã lưu xong”, không phải “đã gọi phương thức lưu”.
4. **Chờ có giới hạn:** `get(5, TimeUnit.SECONDS)` hoặc `await(5, TimeUnit.SECONDS)`; nếu hết hạn, test fail và dọn tài nguyên.
5. **Chỉ dùng assertion trên dữ liệu đã đồng bộ:** không đọc `ByteBuffer` lúc I/O còn pending, không đọc file trước khi writer xác nhận xong nếu giao thức yêu cầu.
6. **Kiểm tra số byte thực tế:** một callback `completed(n, ...)` chỉ có thể báo số byte của **một lần** đọc/ghi, không chắc đủ toàn bộ request.
7. **Tách unit test logic event khỏi khả năng phát event native:** logic do ta kiểm soát có thể kiểm thử xác định; delivery từ `WatchService`/OS có giới hạn nền tảng.
8. **Đảm bảo trạng thái kết thúc trên đường lỗi:** lỗi callback phải hoàn tất future theo kiểu thất bại, không chỉ ghi log rồi để caller đợi mãi.
9. **Đóng thread pool, channel, WatchService và root tạm:** tránh tài nguyên tồn đọng làm sai kết quả test sau.
10. **Quan sát đủ thông tin khi fail:** lưu request ID, offset, byte count, trạng thái barrier, cause và thời gian chờ; không chỉ viết “assert failed”.

Không phải mọi lỗi race xuất hiện chỉ sau một lần chạy. Phối hợp test có thứ tự điều khiển, test stress, instrumentation và kiểm tra invariants cho các lịch chạy khác nhau.

## 4. `CountDownLatch`: điều khiển “bắt đầu cùng pha” thay vì ngủ

`CountDownLatch` là bộ đếm giảm dần về 0; một hoặc nhiều thread có thể `await()` đến khi đủ số lần `countDown()`. Khi counter về 0, những thread đang chờ được cho tiếp tục.

Giả sử có hai worker:

~~~java
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch go = new CountDownLatch(1);

// Mỗi worker:
ready.countDown();
if (!go.await(5, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Start signal timed out");
}
// Bắt đầu phần I/O cần kiểm tra.

// Thread kiểm thử:
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Workers not ready");
}
go.countDown();
~~~

Đây là **đoạn minh họa**, cần import `CountDownLatch` và `TimeUnit`; phải khởi chạy worker thật từ thread pool. `ready` cho biết hai worker đã tới điểm đồng bộ; `go` giải phóng chúng sau khi setup hoàn tất.

**Quan trọng:** một latch không ép CPU chạy hai worker đúng cùng một nanosecond. Nó tạo ra một ranh giới bắt đầu có chủ đích, giúp cả hai *có khả năng cạnh tranh* sau cùng một tín hiệu, và không phụ thuộc `Thread.sleep`.

Để tránh treo khi một worker không bao giờ tới barrier:

- Mọi `await` của test nên có timeout.
- Nếu `ready.await` thất bại, vẫn nên giải phóng `go` hoặc hủy worker để chúng không bị bỏ lại mãi.
- Dùng thread pool có **đủ worker**: nếu pool chỉ có một thread nhưng yêu cầu hai task cùng tới latch, có thể tự tạo deadlock/starvation.
- Thu tất cả kết quả qua `Future.get(timeout)`; exception bên worker không tự nổi lên ở luồng test.

`CountDownLatch` dùng một lần. Nếu cần các vòng đồng bộ lặp lại, cân nhắc `CyclicBarrier` hoặc `Phaser`; phải hiểu cách xử lý broken barrier và timeout.

## 5. `Future` và `CompletableFuture`: đợi kết quả, không đoán trạng thái

Một `Future<T>` cho phép lấy kết quả hoặc nguyên nhân lỗi:

~~~java
Future<String> work = executor.submit(() -> "done");
String result = work.get(5, TimeUnit.SECONDS);
if (!"done".equals(result)) {
    throw new AssertionError("Unexpected result");
}
~~~

Đây là **đoạn minh họa** dùng `ExecutorService executor` đã tạo; cần import `Future` và `TimeUnit`.

`get(timeout, unit)` tạo giới hạn thời gian cho thread test. `TimeoutException` báo rằng việc **chờ** đã hết thời gian, không nhất thiết worker đã dừng. `Future.cancel(true)` có thể yêu cầu hủy, nhưng thread bị interrupt không bắt buộc kết thúc ngay nếu tác vụ không hợp tác.

`CompletableFuture<T>` phù hợp khi cần kết nối callback vào một tín hiệu hoàn tất có thể đợi:

~~~java
CompletableFuture<Integer> finished = new CompletableFuture<>();

// Callback thành công:
finished.complete(actualBytes);

// Callback thất bại:
finished.completeExceptionally(error);

// Thread test:
int actualBytes = finished.get(5, TimeUnit.SECONDS);
~~~

Đây là **đoạn minh họa**, cần `CompletableFuture` và `TimeUnit`; biến `error` chỉ nguyên nhân lỗi. `CompletableFuture` có khả năng hoàn tất chỉ một lần: những lời gọi `complete` hoặc `completeExceptionally` đến sau không thay thế kết quả đã được công bố thành công.

**Lưu ý visibility:** việc nhận kết quả từ `Future.get`/`CompletableFuture.get` cung cấp điểm đồng bộ hữu ích để đọc trạng thái đã được tác vụ công bố. Nhưng nếu những thread khác vẫn còn sửa chung một buffer hoặc collection, không được suy ra rằng toàn bộ hệ thống đã yên; phải xác định ownership và phạm vi hoàn tất.

## 6. Kiểm tra `CompletionHandler` cho I/O bất đồng bộ

Java NIO.2 dùng các callback:

~~~java
channel.read(buffer, fileOffset, attachment,
        new CompletionHandler<Integer, RequestState>() {
            @Override
            public void completed(
                    Integer n, RequestState state) {
                // Một lần đọc hoàn tất: xử lý n và điều kiện đọc tiếp.
            }

            @Override
            public void failed(
                    Throwable error, RequestState state) {
                // Hoàn tất toàn bộ yêu cầu bằng lỗi.
            }
        });
~~~

Đây là **đoạn minh họa API**, không phải chương trình độc lập. `channel` là `AsynchronousFileChannel`, `buffer` là `ByteBuffer`, `fileOffset` là `long`; `RequestState` là kiểu context của ứng dụng.

### 6.1. Đừng đánh đồng một callback với toàn bộ request

Ví dụ mục tiêu là đọc đủ 5 byte từ file, nhưng callback đầu tiên trả 2 byte:

- `n = 2` nghĩa là đã đọc được 2 byte trong lần gọi đó.
- `ByteBuffer.position()` đã tăng 2, **không tự tăng lần thứ hai**.
- Nếu buffer còn chỗ, khởi phát lần đọc tiếp với offset tệp tăng 2.
- Chỉ hoàn tất future bao trùm cả request khi đã có đủ byte hoặc chính sách cho phép EOF sớm.

Khi `n == -1` trên thao tác đọc, đã gặp EOF. Nếu request yêu cầu đủ số byte còn thiếu, báo lỗi `EOFException`. Với `n == 0`, phân biệt buffer hết chỗ, provider đặc biệt hoặc điều kiện không tiến triển; ví dụ kiểm thử tệp ổn định có thể chủ động báo lỗi thay vì retry nóng.

### 6.2. Test cả đường thành công và thất bại

Với logic callback do bạn sở hữu, nên kiểm tra:

- Callback `completed` được xử lý khi có số byte dương.
- Callback `failed` làm request kết thúc theo nhánh lỗi và vẫn có cleanup.
- Khi hoàn thành một phần, code khởi phát thêm thao tác hoặc tích lũy byte đúng.
- Một callback kết thúc muộn hoặc một sự kiện duplicate **không** gây xử lý nghiệp vụ lặp.
- Callback lỗi không bị nuốt, và thread test đọc được nguyên nhân qua future.

**Không tự gọi callback thực của channel một cách thủ công rồi coi đó là kiểm chứng kernel async I/O.** Với unit test logic, bạn có thể tách riêng adapter `readAsync` hoặc inject một fake completion source rồi gọi handler một cách kiểm soát. Với integration test, dùng channel thật và đợi bằng future/latch, nhưng không assert thread name hoặc thời điểm callback tuyệt đối.

## 7. `WatchService`: event không phải trạng thái đích

`WatchService` thông báo những thay đổi do provider phát hiện trên các thư mục đã đăng ký. Các event thường dùng là `ENTRY_CREATE`, `ENTRY_MODIFY` và `ENTRY_DELETE`. `OVERFLOW` báo có thể đã bỏ lỡ sự kiện.

Một số hành vi **không nên assert giống nhau trên mọi hệ điều hành/file system**:

- Một lần ghi tạo đúng một event.
- Event modify phải đến sau create với một số lượng/timing cố định.
- Một thay đổi từ máy khác trên NFS/SMB phải luôn đến.
- Một file vừa tạo đã được ghi hoàn tất khi nhận create.
- Một event `ENTRY_MODIFY` luôn có nghĩa nội dung đã thay đổi có ý nghĩa nghiệp vụ.

Do đó, chia kiểm thử thành hai loại:

| Loại kiểm thử | Mục tiêu | Assertion thích hợp |
| --- | --- | --- |
| **Unit test parser/reconciler** | Kiểm tra code xử lý một tập event đã biết | Cấp event giả lập có thứ tự, duplicate, `OVERFLOW`, key invalid; assert trạng thái/kết quả |
| **Integration test trên file system thật** | Kiểm tra API/provider có thể đăng ký và phát hiện thay đổi trong môi trường mục tiêu | Dùng deadline hợp lý, ghi lại event có/không, luôn kiểm tra snapshot file; chỉ assert khả năng delivery nếu môi trường đã định nghĩa rõ là điều kiện bắt buộc |
| **Test độ tin cậy NFS/SMB** | Đánh giá thay đổi do máy khác thực hiện | Thiết kế kịch bản từ hai máy, đo tỷ lệ phát hiện và latency, có đối chiếu quét directory |
| **Test recovery khi OVERFLOW** | Kiểm tra chính sách full rescan khi mất event | Inject tín hiệu overflow vào thành phần ứng dụng; không cần cố gây quá tải native để có overflow thật |

Nếu bài học có một file `marker.txt` được tạo sau khi đăng ký watcher, test portable **có thể** xác nhận file thực sự tồn tại và đúng nội dung, còn việc nhận event chỉ là quan sát. Đó là một test xác định cho **snapshot correctness**, không phải chứng minh watcher đã giao sự kiện.

### 7.1. Một vòng lấy sự kiện có giới hạn

~~~java
WatchKey key = watchService.poll(1, TimeUnit.SECONDS);
if (key != null) {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            requestFullRescan();
            continue;
        }
        // Đánh dấu đường dẫn dirty, sau đó kiểm tra trạng thái thật.
    }
    if (!key.reset()) {
        // Registration đã invalid; chuyển sang recovery.
    }
}
~~~

Đây là đoạn **minh họa** với `watchService` đang mở và `requestFullRescan()` do ứng dụng tự định nghĩa. `poll(timeout) == null` chỉ có nghĩa **chưa có key được báo** trong thời gian chờ; không kết luận directory không thay đổi. `event.context()` của sự kiện entry cần được xử lý như tên tương đối, xác thực trước khi truy cập path.

### 7.2. Giảm flaky bằng reconciliation

Khi event đến, xử lý nó như một hint “path có thể dirty”. Reconciler sẽ quét và đọc trạng thái file thực tế. Khi test, assert dữ liệu có đúng phiên bản sau khi reconciler báo hoàn tất; đừng assert số event.

Để test idempotency, gửi cùng một event `ENTRY_MODIFY` hai lần và kiểm tra nghiệp vụ chỉ tạo một kết quả cuối hoặc dedup bằng version/id. Để test overflow, đưa vào một tín hiệu `OVERFLOW` rồi assert một lượt full scan được lên lịch, không khẳng định OS sẽ tự sinh overflow đúng thời điểm.

## 8. Kiểm thử concurrency: invariant quan trọng hơn lịch chạy

Giả sử hai tác vụ ghi các file khác nhau trong thư mục riêng. Bài test có thể cần đảm bảo:

1. Hai tác vụ đều **đã tới điểm sẵn sàng** trước khi bắt đầu giai đoạn cần kiểm tra.
2. Cả hai được mở khóa bởi cùng một tín hiệu điều phối.
3. Mỗi tác vụ ghi đúng file của nó; không ghi nhầm sang file của tác vụ kia.
4. Mỗi kết quả nghiệp vụ chỉ được công bố sau khi tác vụ đó đã hoàn thành.
5. Kết quả được lấy qua `Future.get`, để lỗi worker được chuyển về thread kiểm thử.
6. Nếu có timeout hoặc failure, executor không bị bỏ chạy vô thời hạn.

**Đừng assert “task A phải hoàn thành trước B”** trừ khi chương trình thật có hợp đồng yêu cầu điều đó. Sau `go.countDown()`, việc A hoặc B được OS chạy trước là không xác định.

### Cách so sánh kết quả không phụ thuộc thứ tự

Nếu tác vụ có id, thu kết quả vào `Map<Id, Result>` rồi so theo id; không dựa vào thứ tự arrival. Nếu muốn kiểm tra “mỗi id xử lý đúng một lần”, dùng bảng trạng thái và điều kiện atomic/idempotent thay vì đọc một biến đếm `int` đang bị nhiều thread sửa mà không đồng bộ.

Khi kiểm thử data race thật sự, đôi khi cần ép interleaving hiếm bằng hook/barrier **đặt ở vị trí logic cụ thể**. Ví dụ, cả hai worker đọc version cũ trước khi cùng cố ghi, qua đó kiểm tra compare-and-set hoặc transaction. Chỉ tăng số thread/stress không đảm bảo kích hoạt đúng race.

## 9. Ví dụ Java 17+ độc lập: event, callback và hai thao tác được điều phối

Ví dụ sau chạy ba kiểm tra trong một chương trình không cần thư viện ngoài:

- **Event:** đăng ký `WatchService` cho một thư mục tạm, tạo file `marker.txt`, chờ tối đa một khoảng ngắn để quan sát event. Event có thể đến hoặc không; kết quả pass của phần này xác nhận **snapshot nội dung**.
- **Callback:** đọc đầy đủ 5 byte `ready` qua `AsynchronousFileChannel.read(..., CompletionHandler)` và nối việc hoàn tất vào `CompletableFuture`.
- **Concurrency:** đưa hai tác vụ vào pool có 2 thread, dùng `ready` và `start` latch để chắc chắn cả hai đã đến điểm xuất phát trước khi phát tín hiệu. Mỗi tác vụ tạo một thư mục tạm riêng và ghi một file có cùng tên tương đối.

**Tệp `DeterministicIoTestDemo.java`:**

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class DeterministicIoTestDemo {
    private static final int WAIT_SECONDS = 5;

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("deterministic-io-");
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Path watched = Files.createDirectory(root.resolve("watched"));
            Path marker = watched.resolve("marker.txt");

            // Event được quan sát nhưng không quyết định test pass/fail.
            try (WatchService watch =
                         FileSystems.getDefault().newWatchService()) {
                watched.register(
                        watch,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY);

                Files.writeString(
                        marker, "ready", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);

                WatchKey key = watch.poll(1, TimeUnit.SECONDS);
                boolean sawCreate = false;
                if (key != null) {
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.ENTRY_CREATE
                                && marker.getFileName()
                                        .equals(event.context())) {
                            sawCreate = true;
                        }
                    }
                    key.reset();
                }

                // Biến được dùng trong logic diagnostic, không dùng làm
                // tiêu chí pass: provider có thể không phát event.
                if (sawCreate) {
                    // Ở ứng dụng thật có thể cập nhật metrics.
                }
            }

            boolean snapshotOk = "ready".equals(
                    Files.readString(marker, StandardCharsets.UTF_8));
            if (!snapshotOk) {
                throw new AssertionError("File snapshot mismatch");
            }
            System.out.println("Snapshot verified: true");
            System.out.println("Watch event required for pass: false");

            int callbackBytes = readFullyWithHandler(marker);
            System.out.println("Callback bytes read: " + callbackBytes);

            CountDownLatch ready = new CountDownLatch(2);
            CountDownLatch start = new CountDownLatch(1);

            Future<String> alpha = pool.submit(
                    () -> runScenario(root, "alpha", "ONE", ready, start));
            Future<String> beta = pool.submit(
                    () -> runScenario(root, "beta", "TWO", ready, start));

            boolean bothReady = ready.await(
                    WAIT_SECONDS, TimeUnit.SECONDS);
            start.countDown(); // Giải phóng cả hai kể cả khi lỗi setup.

            if (!bothReady) {
                throw new IllegalStateException("Workers did not get ready");
            }

            // Đọc theo id cố định: không phụ thuộc task nào xong trước.
            System.out.println("alpha result: "
                    + alpha.get(WAIT_SECONDS, TimeUnit.SECONDS));
            System.out.println("beta result: "
                    + beta.get(WAIT_SECONDS, TimeUnit.SECONDS));
            System.out.println("All checks passed");
        } finally {
            pool.shutdownNow();
            // Đợi worker dừng trước khi xóa dữ liệu đang được dùng.
            boolean stopped =
                    pool.awaitTermination(WAIT_SECONDS, TimeUnit.SECONDS);
            if (stopped) {
                deleteTree(root);
            } else {
                throw new IllegalStateException(
                        "Executor did not terminate; temp root retained");
            }
        }
    }

    private static int readFullyWithHandler(Path file)
            throws Exception {
        try (AsynchronousFileChannel channel =
                     AsynchronousFileChannel.open(
                             file, StandardOpenOption.READ)) {
            ByteBuffer data = ByteBuffer.allocate(5);
            CompletableFuture<Integer> finished =
                    new CompletableFuture<>();

            CompletionHandler<Integer, Long> handler =
                    new CompletionHandler<>() {
                private int total;

                @Override
                public void completed(Integer n, Long offset) {
                    if (n == -1) {
                        finished.completeExceptionally(
                                new EOFException("Incomplete payload"));
                        return;
                    }
                    if (n == 0) {
                        finished.completeExceptionally(
                                new IOException("Read made no progress"));
                        return;
                    }

                    total += n;
                    if (!data.hasRemaining()) {
                        finished.complete(total);
                        return;
                    }
                    long next = offset + n;
                    try {
                        channel.read(data, next, next, this);
                    } catch (RuntimeException error) {
                        finished.completeExceptionally(error);
                    }
                }

                @Override
                public void failed(Throwable error, Long offset) {
                    finished.completeExceptionally(error);
                }
            };

            channel.read(data, 0L, 0L, handler);
            int total = finished.get(WAIT_SECONDS, TimeUnit.SECONDS);
            data.flip();
            if (!"ready".equals(
                    StandardCharsets.UTF_8.decode(data).toString())) {
                throw new AssertionError("Callback payload mismatch");
            }
            return total;
        }
    }

    private static String runScenario(
            Path parent, String name, String payload,
            CountDownLatch ready, CountDownLatch start)
            throws Exception {
        Path ownRoot = Files.createTempDirectory(parent, name + "-");
        ready.countDown();

        if (!start.await(WAIT_SECONDS, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Start signal timed out");
        }

        Path file = ownRoot.resolve("same-name.txt");
        Files.writeString(
                file, payload, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);

        String actual = Files.readString(file, StandardCharsets.UTF_8);
        if (!payload.equals(actual)) {
            throw new AssertionError("Unexpected concurrent write");
        }
        return actual;
    }

    private static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attributes)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException error) throws IOException {
                if (error != null) {
                    throw error;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 DeterministicIoTestDemo.java
java DeterministicIoTestDemo
~~~

**Stdout kỳ vọng khi provider hỗ trợ WatchService, file I/O hoạt động và các tác vụ hoàn tất trong deadline:**

~~~text
Snapshot verified: true
Watch event required for pass: false
Callback bytes read: 5
alpha result: ONE
beta result: TWO
All checks passed
~~~

### Giải thích những điểm quyết định tính đúng

1. `Files.createTempDirectory` cấp vùng riêng cho toàn bộ ví dụ. Hai task `alpha` và `beta` còn tạo hai thư mục con riêng, nên cùng ghi tên `same-name.txt` mà không xung đột.
2. Đăng ký watcher **trước** khi tạo `marker.txt`. `watch.poll(1, SECONDS)` là quan sát có deadline, không phải sự kiện bắt buộc để test snapshot pass. `key.pollEvents()` và `key.reset()` được gọi khi nhận key.
3. `sawCreate` chỉ là dữ liệu diagnostic, không xuất hiện trong stdout để giữ kết quả kỳ vọng ổn định. Trong test theo môi trường cụ thể, bạn có thể ghi nó vào log hoặc metric để thống kê tỷ lệ delivery.
4. Assertion về sự tồn tại/nội dung thật được thực hiện bằng `Files.readString`. Bài test không phụ thuộc vào số lần `ENTRY_MODIFY` hoặc lịch callback của OS.
5. `AsynchronousFileChannel` đọc theo offset tường minh. Một callback nhận `n` byte thì `ByteBuffer.position()` đã tiến `n`; nếu còn chỗ, code tiếp tục ở offset `offset + n`. Chỉ khi đủ 5 byte mới `finished.complete(total)`.
6. `CompletableFuture.get(5, SECONDS)` là điểm đồng bộ. Sau đó chương trình mới `flip` buffer và giải mã đúng chuỗi `ready`. Các lỗi I/O hoàn tất `finished` theo nhánh exception.
7. `pool` có **hai worker**, phù hợp hai task cùng đợi ở điểm `start`. `ready.await` chứng minh cả hai đã đến mốc đồng bộ trước khi luồng chính giải phóng `start`.
8. Nếu setup một worker không tới mốc đúng hạn, `start.countDown()` vẫn được gọi trước khi test báo lỗi. Điều này tránh để worker khác kẹt vô thời hạn ở latch.
9. `alpha.get` và `beta.get` có timeout và được in theo **thứ tự định danh cố định**, không phải thứ tự thread thực tế hoàn thành.
10. `finally` gọi `shutdownNow()` rồi `awaitTermination` để giảm nguy cơ xóa file khi worker còn truy cập. Nếu worker không dừng đúng hạn, ví dụ cố ý giữ root lại và báo lỗi thay vì xóa một cây đang được sử dụng.
11. `Files.walkFileTree` xóa file trước thư mục, không theo symbolic link theo mặc định. Không dùng lệnh xóa đệ quy trên đường dẫn từ bên ngoài.

**Giới hạn minh bạch:** đây là integration demo đơn giản, không phải một công cụ bảo đảm mọi race trong production đều được phát hiện. Timeout 5 giây là lựa chọn cho demo; máy CI tải nặng có thể vượt deadline và báo lỗi dù thuật toán không sai. Test suite thực tế cần deadline theo SLA môi trường, tài nguyên test phù hợp và quan sát rõ khi timeout. `finally` trong ví dụ có thể báo lỗi cleanup/termination thay thế lỗi trước đó; framework thực tế nên giữ lỗi gốc và gắn cleanup error làm suppressed exception.

## 10. Kiểm thử logic event/callback bằng fake để điều khiển thứ tự

Để unit test có thể **chủ động sinh event A, B, A trùng lặp, rồi OVERFLOW**, đừng chờ OS tạo đúng lịch đó. Tách logic ứng dụng khỏi adapter nhận event.

Ví dụ giao diện:

~~~java
interface EventSink {
    void onCreated(Path relativePath);
    void onModified(Path relativePath);
    void onOverflow();
}
~~~

Đây là **API minh họa**, với import `Path`. Production adapter `WatchService` chuyển `WatchEvent` thành lời gọi trên `EventSink`; unit test có thể tự gọi:

~~~java
sink.onCreated(Path.of("input.txt"));
sink.onModified(Path.of("input.txt"));
sink.onModified(Path.of("input.txt")); // Event lặp.
sink.onOverflow();
~~~

Đây là **đoạn minh họa**, giả định `sink` là đối tượng test đã khởi tạo; không độc lập. Assertions nên kiểm tra:

- `input.txt` chỉ được đưa vào danh sách “dirty” đúng một lần nếu ứng dụng có cơ chế dedup.
- `onOverflow()` đánh dấu cần full reconciliation; các event sau đó không làm mất yêu cầu rescan.
- Consumer thực thi parse/IO khi snapshot sẵn sàng; event giả không tự biến thành file vật lý.
- Khi nội dung hiện tại không đổi, xử lý lại event không sinh tác dụng phụ ngoài ý muốn (idempotency).

Tương tự với `CompletionHandler`, tách code xử lý kết quả sang thành phần có thể inject một completion source. Unit test có thể phát `completed(2)` rồi `completed(3)`, hoặc `failed(IOException)`, mà không cần ép file system thật luôn tạo partial read đúng hai lượt.

**Không dùng fake để thay thế hoàn toàn integration test.** Fake kiểm tra đúng logic của bạn; bài kiểm thử riêng phải xác nhận adapter hoạt động với thư viện/JDK/provider thật trong môi trường triển khai.

## 11. Race và thứ tự sự kiện: kiểm thử điều thực sự phải đúng

### 11.1. Race đọc/ghi chung một file

Hai thread cùng ghi vào một file hoặc một `ByteBuffer` mutable không được đồng bộ có thể tạo kết quả phụ thuộc lịch. Để kiểm thử một chiến lược đồng bộ, hãy định nghĩa invariant rõ:

- Mỗi record có một sequence ID duy nhất.
- Nếu writer công bố version mới, reader không thấy record bị cắt nửa.
- Không có duplicate commit với cùng request ID.
- Không đọc buffer trước khi thao tác I/O đã hoàn tất.
- Không có file tạm nào được công bố như bản hoàn chỉnh sau khi lỗi.

Đặt latch/barrier ngay quanh đoạn tranh chấp mà bạn muốn test; ví dụ hai worker cùng thấy phiên bản cũ rồi cùng thử compare-and-set. Sau khi barrier mở, chỉ một commit hợp lệ được chấp nhận. Không assert thread tên `pool-1-thread-1` phải thắng.

### 11.2. Lost update và visibility

Một biến `int count` được hai thread cùng thực hiện `count++` có thể bị **lost update** do thao tác không nguyên tử. Nếu test cần kiểm tra số lần callback, dùng `AtomicInteger` hoặc công cụ đồng bộ thích hợp thay vì đọc/ghi biến trần không an toàn.

Khi test chỉ chờ `CountDownLatch.await` thành công, các hành động trước `countDown` của worker có quan hệ happens-before với các hành động sau `await` thành công trong thread chờ theo hợp đồng concurrency. Tuy nhiên, các hành động **sau** khi worker gọi `countDown` chưa chắc đã hoàn tất khi waiter được mở khóa; hãy đặt tín hiệu sau khi trạng thái cần công bố thực sự xong.

### 11.3. Callback được gọi lại nhiều lần

Nếu một adapter hoặc tầng ứng dụng có khả năng phát tín hiệu duplicate, việc `CompletableFuture.complete` trả `false` khi future đã hoàn tất có thể là điểm bắt đầu để tránh công bố kết quả hai lần. Tuy vậy, **future hoàn tất một lần không tự bảo vệ side effect trước lời gọi `complete`**. Nếu callback đã ghi database hai lần rồi mới gọi `complete`, duplicate vẫn có thể xảy ra. Phải đặt idempotency/dedup trước side effect nghiệp vụ.

## 12. Trường hợp cần kiểm thử timeout, hủy và lỗi

Với mọi thao tác bất đồng bộ, test nên có đường lỗi độc lập:

| Tình huống | Cách kích hoạt kiểm soát | Điều phải kiểm chứng |
| --- | --- | --- |
| Callback thành công | Fake handler phát `completed(n)` hoặc I/O file thật | Có kết quả đúng và đủ byte |
| Callback thất bại | Fake handler gọi `failed(exception)` | Future của yêu cầu hoàn tất lỗi, không đợi mãi |
| Partial read | Fake trả lần đầu 2 byte, lần sau phần dư | Offset/buffer được cập nhật đúng, không xử lý nội dung thiếu |
| EOF sớm | Dùng file ngắn hơn kích thước yêu cầu | Báo lỗi thiếu dữ liệu, không coi thành công |
| Timeout chờ | Delay có điều khiển bằng latch/future chưa hoàn tất | `get(timeout)` ném timeout, có chính sách hủy/cleanup |
| Task failure | `Callable` chủ động ném exception | `Future.get` trả `ExecutionException` chứa cause |
| Concurrent start | Hai worker cùng đến `ready` rồi nhận `go` | Không xung đột file và invariants đúng |
| Watch event duplicate/overflow | Inject fake event source | Dedup và full rescan theo thiết kế |
| Watch native không phát event | Kịch bản trên provider hỗ trợ bất định | Snapshot vẫn được reconcile hoặc fallback polling |
| Worker không dừng | Fake task không hợp tác với interruption | Báo lỗi timeout, không báo “cleanup thành công” |

**Thời gian trong test** nên có hai vai trò tách biệt: (1) **deadline bảo vệ** để không treo vô hạn; (2) **thời gian nghiệp vụ** cần điều khiển bằng fake clock/ticker nếu logic phụ thuộc vào “sau 10 phút”. Không dùng `Thread.sleep(10 * 60 * 1000)` để test thời gian nghiệp vụ.

Với `ScheduledExecutorService`, kiểm thử logic timer có thể inject scheduler/clock giả để chủ động chạy task đến hạn. Nếu chỉ có integration test scheduler thật, kiểm tra với khoảng dư và deadline hợp lý; không đòi scheduler chạy đúng mili giây.

## 13. Tài nguyên và cleanup cũng là một phần của assertion

Kết quả dữ liệu đúng nhưng test để lại thread pool hoặc file handle có thể làm suite thất thường về sau. Do đó:

- Mỗi scenario tạo root tạm riêng; helper chỉ xóa root **do nó tạo và sở hữu**.
- Mở stream, channel, watch service bằng `try-with-resources` khi phù hợp.
- ExecutorService cần `shutdown`/`shutdownNow` và `awaitTermination`; trên Java 17 không nên dựa vào cú pháp `try (ExecutorService e = ...)`.
- Không xóa thư mục nếu tác vụ còn đang sử dụng nó. Thực hiện shutdown và xác minh đã kết thúc trước cleanup khi có race đáng kể.
- Nếu callback pending hoặc task timeout, cần quyết định hủy/đóng resource, đợi termination hoặc giữ artifact với cảnh báo rõ.
- Khi cleanup thất bại, giữ nguyên lỗi gốc bằng suppressed exception hoặc cơ chế của framework.
- Trên Windows, file/channel còn mở có thể khiến xóa file thất bại. Phải đóng chúng trước khi xóa.
- `WatchService` có thể ném `ClosedWatchServiceException` khi đóng trong lúc thread đang chờ; coi đây là nhánh vòng đời cần được kiểm soát, không đơn giản nuốt mọi exception.
- Khi root chứa symlink, `walkFileTree` mặc định không đi theo symlink; vẫn tránh cây bị tiến trình không tin cậy sửa đồng thời.

Test nên kết thúc với trạng thái rõ: mọi task hoàn thành/đã hủy, mọi future được quan sát, không còn handle bị bỏ quên, thư mục tạm đã dọn hoặc có cảnh báo vì lý do giữ lại.

## 14. Làm sao kiểm chứng tính ổn định?

Một lần pass chỉ chứng minh bài test pass **trong lần đó**. Để tăng độ tin cậy:

1. Chạy lặp lại với nhiều mức tải CPU/I/O và nhiều mức concurrency; thu tỷ lệ fail.
2. Kiểm tra cả Linux/Windows/macOS nếu ứng dụng cần portable; quan sát khác biệt `WatchService` trên file system cục bộ/NFS/SMB.
3. Giữ các assertion **không phụ thuộc độ trễ cụ thể**: có thể dùng thời hạn chờ đủ cho môi trường, không dùng “callback phải về trong 20 ms” trừ khi kiểm thử SLA.
4. Ghi trace có id, thread, offset, số byte thực tế và trạng thái barrier khi có lỗi.
5. Không dùng test lặp/stress như lý do bỏ các test kiểm soát interleaving. Stress chỉ tăng cơ hội thấy race, không đảm bảo khám phá mọi lịch chạy.
6. Xem xét test lỗi như overflow, duplicate, EOF sớm, failure callback và timeout bằng fake hoặc fault injection để không cần chờ lỗi hiếm tự xuất hiện.
7. Không cho test ảnh hưởng hệ thống bên ngoài không kiểm soát (thư mục công cộng, cổng cố định, database thật) nếu không có cô lập.

### Một ma trận QA ngắn cho dự án

| Kiểm thử | Có điều khiển? | Pass dựa trên |
| --- | --- | --- |
| Unit: parser xử lý `ENTRY_MODIFY` lặp | Có, fake event source | Chỉ một trạng thái cập nhật hợp lệ |
| Unit: callback đọc 2 + 3 byte | Có, fake completion | Buffer/offset đúng, hoàn tất đúng 5 byte |
| Integration: `AsynchronousFileChannel` | Một phần; lịch callback do provider | Future hoàn tất, byte thực tế/nội dung đúng |
| Integration: `WatchService` local | Giới hạn; delivery do provider | Snapshot đúng; event quan sát và ghi nhận |
| Integration: hai worker có start barrier | Có ở điểm xuất phát; lịch tiếp theo do OS | Hai kết quả đúng, không collision |
| Stress: nhiều worker đọc/ghi | Không cố định interleaving | Invariants và tỷ lệ lỗi qua nhiều lượt |
| End-to-end: xử lý file từ NFS/SMB | Chỉ điều khiển khâu sinh file, khó kiểm soát remote delivery | Dữ liệu cuối đúng, watcher + reconciliation, giám sát độ trễ |

## 15. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `Thread.sleep` rồi assert file tồn tại | Flaky trên máy nhanh/chậm | Chờ tín hiệu hoàn tất rồi kiểm tra |
| `Future.get()` không timeout | Test có thể treo vĩnh viễn | `get(timeout, unit)` và cleanup |
| `CountDownLatch.await()` không thời hạn | Kẹt nếu worker fail trước `countDown` | `await(timeout, unit)` |
| Pool 1 thread nhưng barrier cần 2 task | Starvation/deadlock | Pool đủ worker hoặc đổi thiết kế đồng bộ |
| Assertion số event WatchService chính xác | Khác nhau theo OS/provider | Assert trạng thái hoặc injection vào parser |
| Giả định event tới nghĩa file đã ghi xong | Có thể đọc file dở | Await producer completion hoặc protocol publish |
| Gọi callback rồi coi toàn bộ request hoàn tất | Sai khi partial I/O | Theo dõi tổng byte và offset |
| Quên `failed(...)` của CompletionHandler | Test đợi future mãi | `completeExceptionally` |
| Đọc buffer khi async read pending | Race/đọc dữ liệu thiếu | Chờ completion và kiểm soát ownership |
| Assert callback chạy trên thread tên cố định | Provider/executor khác nhau | Chỉ assert kết quả, có thể test executor riêng nếu contract yêu cầu |
| Chia sẻ một file path giữa các test parallel | Collision và false failure | Mỗi scenario có root riêng |
| Dùng biến đếm thường cho callback đa thread | Lost update/visibility lỗi | `AtomicInteger`/lock và synchronization |
| Assert thứ tự hoàn tất task không có contract | Kết quả thay đổi | So kết quả theo id hoặc tập hợp |
| Hủy Future và nghĩ side effect đã rollback | File có thể ghi một phần | Cleanup/staging và trạng thái hủy rõ |
| Cleanup trước khi worker dừng | Race, file deletion thất bại | Shutdown, await termination, sau đó xóa |
| Chỉ kiểm tra success path | Lỗi/EOF/timeout không được xử lý | Test cả failure và recovery bằng fake/injection |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một thread gọi `Thread.sleep(500)` trước khi kiểm tra file được writer bất đồng bộ tạo. Đây có phải bằng chứng writer đã hoàn tất?

**Đáp án:** Không. Sleep chỉ làm thread chờ thời gian, không xác nhận callback, channel hoặc writer đã hoàn tất. Hãy đợi tín hiệu do writer công bố.

**Câu 2.** Vì sao cần hai latch `ready` và `start` khi chạy hai worker?

**Đáp án:** `ready` cho thread kiểm thử biết cả hai worker đã tới mốc setup; `start` cho phép giải phóng chúng sau khi mọi thứ sẵn sàng, giảm phụ thuộc scheduler trước thời điểm cạnh tranh.

**Câu 3.** `CompletableFuture.get(5, SECONDS)` timeout. Có được lập tức tái sử dụng `ByteBuffer` đang được cấp cho I/O đó?

**Đáp án:** Không. Timeout chỉ kết thúc việc đợi; thao tác I/O có thể còn chạy và đang dùng buffer. Cần đóng/hủy/đợi kết thúc theo hợp đồng.

**Câu 4.** `WatchService` phát hai `ENTRY_MODIFY` cho một file. Test có nên thất bại vì mong đúng một event?

**Đáp án:** Không, trừ khi bạn đang kiểm thử hợp đồng provider cụ thể đã xác minh điều đó. Logic ứng dụng nên chấp nhận duplicate và đối chiếu trạng thái thực.

**Câu 5.** Cần chắc chắn parser gọi full rescan khi overflow, nhưng không dễ gây overflow thật trên máy CI. Nên làm gì?

**Đáp án:** Tách parser/reconciler ra thành API nhận event và unit test bằng cách inject event `OVERFLOW`. Giữ một integration test riêng cho adapter WatchService.

**Câu 6.** Hai task chạy song song trả về đúng kết quả nhưng hoàn tất theo thứ tự khác nhau qua các lượt. Có phải test lỗi?

**Đáp án:** Không nếu nghiệp vụ không yêu cầu thứ tự. Assert kết quả theo request ID, không theo thời điểm completion.

**Câu 7.** Callback đọc 2 byte, lần tiếp 3 byte. Có nên dùng offset cũ cho lần tiếp không?

**Đáp án:** Không. Với `AsynchronousFileChannel`, phải đọc tại offset cũ + 2, đồng thời giữ `ByteBuffer.position()` đã được hệ thống cập nhật.

**Câu 8.** Một test đã pass nhưng executor không được shutdown và còn thread đang ghi file. Có thể coi test đã cô lập hoàn toàn?

**Đáp án:** Chưa. Tác vụ còn chạy có thể ảnh hưởng test sau hoặc gây leak. Chờ termination và kiểm soát cleanup là một phần của bài test đáng tin.

## 17. Ghi nhớ

- **Kiểm tra theo tín hiệu hoàn tất và invariants**, không theo thời gian ngủ ngẫu nhiên.
- **Event của WatchService là gợi ý thay đổi, không phải cam kết số lượng/thứ tự hay thời điểm file hoàn tất**; dùng fake để test logic và snapshot/reconciliation để test trạng thái.
- **Callback của NIO.2 cần xử lý partial I/O, failure và ownership buffer**; nối trạng thái yêu cầu với `CompletableFuture`/`CountDownLatch` để đợi có timeout.
- **Concurrency test cần barrier ở đúng điểm tranh chấp**, pool đủ thread và assertion không phụ thuộc scheduler.
- **Cleanup cũng phải xác định:** giữ phạm vi tài nguyên riêng, shutdown/await worker trước khi dọn, không để exception bất đồng bộ bị thất lạc.
