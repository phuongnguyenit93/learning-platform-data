# Tránh giữ lock xuyên qua call không kiểm soát trong Java

## 1. Bài toán và nguyên tắc

Khi nhiều thread cùng truy cập trạng thái có thể thay đổi, lock giúp bảo vệ **bất biến (invariant)**: ví dụ một danh sách phải được cập nhật nhất quán, hoặc một đơn hàng chỉ được chuyển trạng thái theo quy tắc cho phép. Tuy nhiên, **giữ lock trong lúc gọi một hàm mà ta không kiểm soát được thời gian chạy, hành vi chặn hoặc các lock mà nó sẽ lấy** có thể biến một đoạn bảo vệ trạng thái rất ngắn thành điểm nghẽn hoặc deadlock.

**Nguyên tắc:** vùng critical section chỉ nên thực hiện thao tác ngắn, có thời gian dự đoán được, cần thiết để đọc/cập nhật trạng thái chung. Hãy lấy snapshot hoặc đặt trước một trạng thái hợp lệ dưới lock, **nhả lock**, rồi mới thực hiện callback, I/O hay công việc không kiểm soát được. Nếu cần cập nhật kết quả, vào lại lock và kiểm tra rằng tiền điều kiện vẫn đúng.

"Call không kiểm soát" không nhất thiết là mã bên thứ ba. Một lời gọi đến phương thức có thể bị override, listener do người dùng đăng ký, executor, logger, hoặc hàm nội bộ sau này thêm I/O đều có thể thay đổi hành vi mà nơi giữ lock không biết.

## 2. Vì sao giữ lock qua call nguy hiểm?

Giả sử thread T1 đang giữ lock L, rồi gọi một dịch vụ hoặc callback. Trong khi đó, thread T2 muốn lấy L để hoàn tất công việc mà call của T1 đang chờ:

```text
T1: lock(L) → gọi callback/đợi kết quả của T2 ───────┐
                                                    │ chờ T2
T2: cần lock(L) để hoàn tất công việc <──────────────┘
```

T1 không nhả L vì còn đợi call; T2 không tiến được vì L bị giữ: một chu kỳ chờ gây **deadlock**. Ngay cả khi không có chu kỳ, call chậm sẽ làm mọi thread khác cần L phải xếp hàng, tăng độ trễ và giảm throughput.

| Tình huống bên trong lock | Rủi ro chính |
| --- | --- |
| Gọi API mạng, truy vấn database, đọc/ghi file | Thời gian không giới hạn thực tế; timeout/chậm mạng; chặn thread khác |
| Gọi plugin, listener, callback, hàm có thể override | Mã tùy ý có thể lấy lock khác, gọi ngược, chờ task hoặc ném exception |
| `Future.get()`, `CompletableFuture.join()`, `Thread.join()`, chờ một task | Task đang chờ có thể cần chính lock đang giữ |
| `Executor.execute()`, `CompletableFuture.thenApply(...)` | Không được mặc định callback chạy ở thread khác: executor chạy trực tiếp hoặc stage đã hoàn thành có thể chạy đồng bộ |
| Logging hoặc gọi thư viện không rõ triển khai | Có thể lấy lock khác, flush/chặn I/O hoặc kích hoạt callback |
| `Thread.sleep(...)` hoặc xử lý CPU rất lâu | Vẫn giữ lock; làm tăng thời gian chờ, kể cả khi không có I/O |

Trong Java, `synchronized` nhả monitor khi rời block, kể cả khi có exception; `ReentrantLock` phải được `unlock()` trong `finally`. **Cả hai đều không tự nhả lock chỉ vì phương thức bên trong block đang chặn.** Riêng `Object.wait()` nhả monitor tương ứng khi đợi, và `Condition.await()` nhả lock gắn với condition trong lúc chờ rồi lấy lại trước khi trả về; đây là cơ chế phối hợp có chủ đích, không phải cách làm cho lời gọi tùy ý trở nên an toàn. Chúng cũng không nhả những lock khác mà thread đang giữ.

## 3. Phản ví dụ: gọi listener ngay trong vùng khóa

Đoạn trích sau minh họa thiết kế dễ gặp ở một registry. Listener do bên ngoài cung cấp, vì vậy không thể biết nó có chạy nhanh, gọi ngược registry, lấy lock khác hay chờ thread khác hay không.

```java
// Đoạn trích minh họa: KHÔNG phải chương trình Java độc lập.
private final Object lock = new Object();
private final List<Consumer<String>> listeners = new ArrayList<>();

void publishBad(String message) {
    synchronized (lock) {
        for (Consumer<String> listener : listeners) {
            listener.accept(message); // Chạy mã bên ngoài trong lúc giữ lock.
        }
    }
}
```

Các vấn đề cụ thể:

- Callback chậm làm `subscribe()` và các thao tác khác dùng cùng lock phải chờ, dù registry chỉ cần bảo vệ danh sách listener.
- Callback có thể gọi ngược `subscribe()`. Monitor Java là **reentrant** nên cùng thread lấy lại chính monitor này không nhất thiết deadlock; tuy nhiên callback có thể quan sát hoặc thay đổi trạng thái tại thời điểm không mong muốn. Nếu sửa danh sách khi đang duyệt, có thể xảy ra `ConcurrentModificationException`.
- Callback có thể lấy lock B; một thread khác giữ B rồi cần lock registry sẽ tạo chu kỳ **A → B → A**.
- Exception từ một callback có thể ngăn các callback phía sau được gọi; dù monitor được nhả khi thoát block, hành vi phát sự kiện vẫn phải được định nghĩa rõ.

Không nên giả định phương thức `private` hoặc "code mình viết" luôn an toàn: một call hôm nay chỉ tính toán, ngày mai có thể thêm I/O hoặc gọi hook.

## 4. Mẫu đúng: snapshot dưới lock, gọi bên ngoài lock

Ví dụ độc lập sau chạy được trên **Java 17+**. Registry giữ danh sách listener có thể thay đổi; khi phát thông báo, nó tạo snapshot bất biến trong vùng khóa rồi gọi các listener sau khi nhả khóa.

**Tệp: `ListenerRegistryDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public final class ListenerRegistryDemo {
    private final Object lock = new Object();
    private final List<Consumer<String>> listeners = new ArrayList<>();

    public void subscribe(Consumer<String> listener) {
        Objects.requireNonNull(listener, "listener");
        synchronized (lock) {
            listeners.add(listener);
        }
    }

    public void publish(String message) {
        final List<Consumer<String>> snapshot;
        synchronized (lock) {
            snapshot = List.copyOf(listeners);
        }

        // Không giữ lock khi thực thi callback do bên ngoài cung cấp.
        for (Consumer<String> listener : snapshot) {
            listener.accept(message);
        }
    }

    public int subscriberCount() {
        synchronized (lock) {
            return listeners.size();
        }
    }

    public static void main(String[] args) {
        ListenerRegistryDemo registry = new ListenerRegistryDemo();
        registry.subscribe(msg -> System.out.println("listener: " + msg));
        registry.publish("hello");
        System.out.println("subscribers: " + registry.subscriberCount());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac ListenerRegistryDemo.java
java ListenerRegistryDemo
```

Stdout xác định của chương trình:

```text
listener: hello
subscribers: 1
```

**Giải thích tính đúng đắn:**

1. Mọi cập nhật `listeners` đi qua cùng một monitor; `List.copyOf` được tạo khi monitor đang bảo vệ danh sách, nên không duyệt một danh sách đang bị thread khác sửa.
2. Snapshot là một danh sách độc lập, không thể sửa qua API của chính danh sách đó. Lệnh `listener.accept` chạy sau khi đã ra khỏi `synchronized`; dù callback chậm, monitor của registry vẫn có thể được thread khác lấy.
3. Việc nhả/lấy monitor tạo quan hệ *happens-before* giữa các thao tác được đồng bộ hóa đúng cách. Ví dụ không cần `volatile` chỉ để bảo vệ danh sách này.
4. Một listener đăng ký **sau khi snapshot được lấy** sẽ không nhận lượt publish hiện tại. Nếu có thao tác hủy đăng ký, listener bị hủy sau snapshot vẫn có thể nhận lượt này. Đây là hợp đồng *snapshot semantics*, không phải lỗi đồng bộ.
5. Ví dụ cố ý để exception của listener truyền ra ngoài, nên các listener phía sau có thể không được gọi. Ứng dụng thực tế phải chọn chính sách rõ ràng: dừng, bắt lỗi từng listener, retry hoặc ghi nhận lỗi. Không nên tự ý nuốt lỗi.

Snapshot chỉ sao chép **danh sách tham chiếu**, không biến từng listener thành thread-safe và không bảo đảm listener luôn chạy nhanh. Nó chỉ giảm phạm vi lock của registry.

## 5. Khi cần thực hiện side effect rồi cập nhật trạng thái: giao thức nhiều pha

Chỉ chuyển lời gọi ra ngoài lock là chưa đủ nếu trạng thái có thể thay đổi trong lúc gọi. Ví dụ kiểm tra đơn hàng ở trạng thái `NEW`, nhả lock, gọi cổng thanh toán, rồi đặt `PAID` có thể khiến **hai thread cùng thanh toán** vì cả hai đều đã đọc `NEW`.

Hãy thiết kế một giao thức có **trạng thái trung gian/claim** thay vì giữ lock xuyên qua cổng thanh toán:

```text
Pha 1, dưới lock:
    kiểm tra trạng thái NEW
    chuyển NEW → PROCESSING; gắn operationId duy nhất
    nhả lock

Pha 2, ngoài lock:
    gọi cổng thanh toán với operationId làm idempotency key

Pha 3, dưới lock:
    kiểm tra operationId và trạng thái PROCESSING còn khớp
    ghi PAID hoặc trạng thái thất bại/chưa rõ kết quả
    nhả lock
```

Đây là **sơ đồ thuật toán**, không phải mã Java độc lập. Các điểm cần thiết khi triển khai:

- Chuyển `NEW → PROCESSING` phải nguyên tử trong cùng cơ chế đồng bộ mà các luồng xử lý khác tuân thủ. Chỉ thread claim thành công mới được phát lệnh thanh toán.
- Sau I/O, kiểm tra lại `operationId`, version hoặc trạng thái hiện tại trước khi commit; không dùng kết quả đọc cũ để ghi đè một thay đổi hợp lệ mới hơn.
- Timeout từ hệ thống bên ngoài **không chứng minh side effect thất bại**: request có thể đã được thực hiện nhưng response bị mất. Cần idempotency key được phía ngoài hỗ trợ, tra cứu trạng thái, reconciliation và chính sách retry an toàn.
- Nếu tiến trình dừng giữa hai pha, cần cách phát hiện và khôi phục việc `PROCESSING` bị treo (lease, timeout có kiểm soát hoặc quy trình phục hồi phù hợp); tuyệt đối không mặc định retry một side effect không idempotent.
- Nếu cần bảo đảm thứ tự tuyệt đối, hãy dùng queue/actor/serial executor hoặc một protocol có thứ tự và trạng thái tường minh. **Nhả lock thay đổi thời điểm tác vụ có thể xen vào**, vì vậy phải định nghĩa hợp đồng thứ tự thay vì ngầm trông cậy vào thời gian giữ lock.

Tùy phạm vi hệ thống, có thể dùng snapshot + version, optimistic validation, state machine, hoặc chuyển công việc sang worker chuyên trách. Mục tiêu là giữ việc bảo vệ invariant **ngắn và rõ ràng**, còn công việc chậm nằm ngoài lock.

## 6. Những trường hợp dễ tưởng là đã an toàn

### Callback ẩn bên trong thư viện

Một API trông như "đăng ký" hay "tính toán" vẫn có thể gọi code của caller ngay lúc đó. Ví dụ `CompletableFuture.thenApply` có thể chạy action ngay trong thread đang đăng ký khi future đã hoàn thành; và `Executor.execute` có thể chạy `Runnable` ngay tại caller với direct executor hoặc chính sách từ chối như `CallerRunsPolicy`. Vì vậy gọi chúng dưới lock vẫn cần xét đường chạy đồng bộ.

Nên chuẩn bị dữ liệu dưới lock, nhả lock rồi mới đăng ký/thực thi action. Nếu action cần thứ tự hoặc dữ liệu nhất quán, thiết kế trạng thái/queue để bảo đảm thay vì kỳ vọng callback luôn bất đồng bộ.

### `tryLock`, timeout và interrupt

`ReentrantLock.tryLock(timeout, unit)` giới hạn **thời gian đợi để lấy lock**, không giới hạn thời gian thread giữ lock sau khi đã lấy được. Timeout của network call có thể giảm thời gian chặn nhưng không loại bỏ chu kỳ phụ thuộc lock hoặc mọi đường chậm. `interrupt()` cũng không buộc mã bên ngoài bất kỳ phải dừng và không tự nhả lock; khả năng hủy phụ thuộc API và logic xử lý.

Mẫu nhả `ReentrantLock` đúng vẫn phải có `finally`:

```java
// Đoạn trích minh họa, giả sử lock là một ReentrantLock.
lock.lock();
try {
    // Chỉ đọc/cập nhật trạng thái chia sẻ ngắn và hữu hạn.
} finally {
    lock.unlock();
}

// Gọi I/O hoặc callback ở đây, ngoài vùng lock.
```

Không được thay bằng thao tác `unlock()` giữa chừng rồi dùng tiếp các giả định bất biến cũ mà không kiểm tra lại.

### Nested lock và reentrancy

Giữ lock A khi gọi phương thức có thể lấy lock B tạo một cạnh thứ tự **A → B**. Nếu code khác lấy B rồi A, deadlock có thể xảy ra dù từng lock riêng lẻ hoạt động đúng. Với `synchronized` và `ReentrantLock`, tái nhập cùng lock trên cùng thread thường được hỗ trợ; nhưng tái nhập có thể khiến callback quan sát trạng thái chưa hoàn tất hoặc thay đổi bộ sưu tập đang được duyệt. Vì vậy "lock reentrant" không đồng nghĩa "an toàn để gọi callback dưới lock".

### Lock chỉ bảo vệ phần cục bộ, không bảo vệ cả hành động bên ngoài

Nếu cần bảo đảm snapshot, dùng bản sao bất biến hoặc DTO chứa các giá trị cần thiết. Nếu nhiều trường phải cùng nhất quán, chụp chúng trong cùng critical section. Nếu muốn commit sau call, dùng version/claim và so khớp lại. Một `volatile` riêng lẻ không thay thế transaction/lock cho invariant liên quan nhiều trường; `AtomicInteger` cũng không tự động làm các cập nhật nhiều đối tượng trở nên nguyên tử.

### Hàm tính toán trên concurrent collection

Một số API như `ConcurrentHashMap.computeIfAbsent` hoặc `compute` thực hiện logic cập nhật nguyên tử theo hợp đồng của collection. Mapping/remapping function không nên thực hiện I/O lâu, chờ future, cập nhật đệ quy cùng map hoặc gọi code khó kiểm soát; việc dùng concurrent collection không loại bỏ nguy cơ contention/blocking bên trong phép cập nhật.

## 7. Kiểm tra và chẩn đoán trong hệ thống thực tế

Khi review concurrency code, bắt đầu từ từng đoạn `synchronized`, `Lock.lock()`/`unlock()`, read/write lock và callback chạy trong phần cập nhật nguyên tử. Với mỗi call bên trong, hỏi:

1. Call có thể block vì I/O, chờ future, chờ thread, sleep, queue đầy hoặc tài nguyên ngoài JVM không?
2. Call có thể chạy code chưa biết trước (listener, override, plugin, executor, callback, logger) hoặc lấy lock thứ hai không?
3. Code được gọi có thể gọi ngược và làm thay đổi trạng thái đang được duyệt/cập nhật không?
4. Có thể snapshot/claim trong lock rồi chuyển call ra ngoài không? Nếu chuyển ra, invariant, thứ tự và trường hợp stale result được xử lý như thế nào?
5. Có chính sách rõ ràng cho exception, timeout, retry và side effect có kết quả không chắc chắn không?

Triệu chứng cần quan sát gồm thời gian chờ lock tăng, request tail latency cao, throughput giảm, nhiều thread ở trạng thái `BLOCKED` hoặc `WAITING`, và chu kỳ chờ tài nguyên. Thread dump (`jcmd <pid> Thread.print`) và Java Flight Recorder có thể giúp tìm contention; nhưng trạng thái `WAITING`/đợi I/O không tự nó chứng minh deadlock. Cần lần theo **thread nào đang giữ lock nào và đang chờ điều gì**; một số deadlock liên quan I/O/callback có thể không được detector monitor truyền thống nhận ra.

Khi đo thời gian, phân biệt **thời gian chờ để lấy lock** với **thời gian giữ lock**. Log/metric phải hạn chế overhead và bản thân đường ghi metric không được trở thành call chặn kéo dài ngay dưới lock.

## 8. Quy tắc áp dụng

- **Giữ lock cho phần trạng thái chia sẻ:** validate invariant, snapshot, claim, cập nhật ngắn, publish trạng thái nội bộ.
- **Nhả lock trước lời gọi không kiểm soát:** network/file I/O, callbacks, hooks, listeners, task scheduling có thể chạy inline, chờ kết quả và các thao tác có latency không rõ.
- **Vào lại lock có điều kiện:** kiểm tra version/state/operationId trước khi áp dụng kết quả; định nghĩa xử lý cạnh tranh và thứ tự.
- **Có thiết kế lỗi và side effect:** exception/timeout/retry/idempotency/reconciliation; không dùng lock cục bộ để giả vờ biến API bên ngoài thành transaction nguyên tử.
- **Xác minh bằng quan sát:** đo lock hold time, chờ lock, trace/thread dump, thử callback chậm, callback gọi ngược và hai thread cạnh tranh.

**Câu hỏi tự kiểm tra:** một phương thức đang giữ `synchronized(lock)` rồi gọi `future.join()`. Future chỉ hoàn tất sau một task cần vào `synchronized(lock)`. Điều gì xảy ra? **Đáp án:** thread giữ lock chờ future; task cần lock lại không thể hoàn tất, tạo vòng chờ. Hãy quyết định trạng thái cần đọc/cập nhật dưới lock, nhả lock trước khi chờ, rồi kiểm tra lại trạng thái sau khi future hoàn tất.