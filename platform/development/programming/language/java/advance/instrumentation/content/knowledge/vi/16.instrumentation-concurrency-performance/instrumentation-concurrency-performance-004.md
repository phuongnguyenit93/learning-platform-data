# Chốt cấu hình nhất quán trong khi đổi bộ lọc hoặc bật/tắt điểm đo

Một Java agent đang đo thời gian method có thể được điều khiển **ngay khi ứng dụng chạy**: bật/tắt điểm đo, bổ sung tên method vào bộ lọc, thay tỷ lệ sampling, đổi nơi gửi metric hoặc thay quy tắc loại trừ. Những thao tác này thường đến từ một thread quản trị, trong khi hàng trăm thread ứng dụng đồng thời đi qua các hook đã được instrument.

Vấn đề khó nhất không phải viết `enabled = false`, mà là **xác định phiên bản cấu hình nào được áp dụng cho một lần gọi method**. Nếu entry hook đọc cờ `enabled` của phiên bản cũ, sau đó đọc filter của phiên bản mới, rồi exit hook lại đọc sink của phiên bản thứ ba, dữ liệu có thể trở nên không nhất quán: có exit mà không có entry, có duration thiếu điểm bắt đầu, ghi vào sai sink hoặc mất sự kiện.

Chủ đề thuộc phần **Đồng thời và hiệu năng** của Java Advance — instrumentation. Giải pháp trọng tâm là **chốt một snapshot cấu hình bất biến tại điểm bắt đầu invocation** và truyền một token/scope của invocation ấy tới điểm kết thúc. Một lần cập nhật cấu hình được **publish nguyên khối** bằng `AtomicReference` hoặc một tham chiếu `volatile` tới object bất biến; hook nóng chỉ đọc **một lần** rồi sử dụng đúng snapshot đó.

Bài này trình bày hợp đồng nhất quán, Java Memory Model, thiết kế filter/version/sink, thay đổi cấu hình khi invocation đang chạy, ví dụ Java 17+ có thể biên dịch và chạy, chi phí hiệu năng, các giới hạn với retransformation và checklist kiểm thử production.

## 1. Quy định rõ “nhất quán” nghĩa là gì

Trước khi viết code, phải xác định **đơn vị áp dụng cấu hình**.

| Đơn vị | Điều có thể cam kết | Hệ quả |
|---|---|---|
| **Một lần gọi method** (*per-invocation*) | Entry và exit dùng cùng cấu hình đã chốt ở entry | Invocation đang chạy vẫn có thể gửi sự kiện theo cấu hình cũ sau khi tắt |
| **Mỗi lần chạy hook** (*per-hook*) | Entry/exit lần nào cũng đọc cấu hình hiện tại | Dễ có entry của phiên bản A và exit của phiên bản B; phải xử lý mất cặp sự kiện |
| **Một request/trace** | Các method trong cùng request dùng một phiên bản cấu hình | Cần truyền snapshot theo request context, không chỉ giữ local trong từng method |
| **Toàn JVM ngay tức thì** | Sau khi cập nhật xong, không còn event từ cấu hình cũ | Đòi hỏi đồng bộ/chặn, thu hồi hoặc drain các invocation đang chạy; atomic reference đơn lẻ chưa đủ |

Trong đa số điểm đo **duration/counter/span** ở mức method, lựa chọn **per-invocation** dễ bảo toàn ngữ nghĩa nhất:

```text
entry(method="checkout") -- chốt config v1, enabled=true
          |
          | method đang chạy
          |
control thread: publish config v2, enabled=false
          |
          | method v1 vẫn tiếp tục
          v
exit(checkout) ----------- dùng token và sink của v1
```

**Kết quả đúng theo chính sách per-invocation:** event `checkout` phiên bản `v1` vẫn được phát khi method kết thúc. Cấu hình `v2` sẽ áp dụng cho **những lần gọi bắt đầu sau khi v2 đã được publish và được quan sát**.

Điều này không mâu thuẫn với “đã tắt điểm đo”: **tắt ở đây là ngừng nhận invocation mới**, không phải xóa lịch sử của invocation đang chạy. Nếu nghiệp vụ yêu cầu “không được gửi bất cứ event nào ngay sau thao tác tắt”, cần một chính sách khác, được thảo luận ở mục 10.

## 2. Lỗi thường gặp: nhiều biến `volatile` không tạo thành một giao dịch

Giả sử một agent có:

```java
private static volatile boolean enabled = true;
private static volatile Set<String> allowedMethods =
        Set.of("checkout");
```

Thread quản trị cập nhật:

```java
allowedMethods = Set.of("inventory"); // Bộ lọc mới
enabled = false;                      // Tắt điểm đo
```

Thread instrumented chạy:

```java
if (enabled && allowedMethods.contains(methodId)) {
    recordEvent();
}
```

Đây là **mã minh họa rời**, không phải class độc lập. `volatile` bảo đảm các quy tắc visibility/happens-before **cho các thao tác volatile thích hợp**, nhưng **không biến việc đọc hai field thành một snapshot nguyên tử của cả hai field**.

Ví dụ các thao tác có thể xen kẽ:

```text
Thời điểm       Control thread                 Worker thread
---------       --------------                 -------------
t0              enabled=true                   ...
                filter={checkout}
t1              allowedMethods={inventory}
t2                                             đọc enabled=true
t3                                             đọc filter={inventory}
t4              enabled=false
```

Worker nhìn thấy một **tổ hợp trạng thái** chưa từng được publish như một cấu hình hoàn chỉnh theo ý định của người quản trị. Nếu worker phải đọc thêm `samplingRate`, `reporter`, `excludedPackages` ở các thời điểm khác nhau, số trạng thái pha trộn còn tăng lên.

Đổi thứ tự hai phép gán **không giải quyết tổng quát** lỗi đọc nhiều field. `synchronized` bảo vệ cùng một lock ở **cả reader lẫn writer** có thể tạo tính nhất quán, nhưng khóa trên đường nóng của mọi method invocation thường gây contention và tăng latency. Một giải pháp gọn hơn là **immutable snapshot + atomic publication**.

### 2.1. Cẩn thận với collection mutable

Ngay cả khi tham chiếu filter là `volatile`:

```java
private static volatile Set<String> methods = new HashSet<>();
```

mà thread quản trị sửa **trực tiếp nội dung** `methods.add(...)`/`methods.remove(...)`, điều đó không khiến các thao tác trên `HashSet` trở thành thread-safe. Reader có thể thấy trạng thái không nhất quán hoặc gặp lỗi do concurrent modification.

Với cấu hình, nên tạo **một `Set` mới đã được kiểm tra**, đóng nó trong object cấu hình bất biến, rồi thay **một tham chiếu chung**. Không mutate collection đang được các invocation cũ sử dụng.

## 3. Thiết kế: một object `Config` chứa toàn bộ quyết định liên quan

Mô hình:

```text
Config v1 (immutable):
  version=1
  enabled=true
  methods={checkout}
  sink=SinkA
           |
           | AtomicReference<Config>
           v
        [v1 pointer]  -- atomic update --> [v2 pointer]
                                            |
                                            v
                                     Config v2:
                                       version=2
                                       enabled=false
                                       methods={}
                                       sink=SinkA
```

Một worker làm:

```java
Config snapshot = current.get();
if (!snapshot.enabled()) {
    return;
}
if (!snapshot.methods().contains(methodId)) {
    return;
}
```

`current.get()` chỉ xuất hiện **một lần**. Hai điều kiện đều đọc từ **cùng object**. Một writer thay con trỏ `current` sau đó **không làm thay đổi object `snapshot`** đang được worker giữ.

### 3.1. Dùng `record` Java 17 và sao chép collection

Ví dụ khái niệm:

```java
record Config(
        long version,
        boolean enabled,
        Set<String> allowedMethods,
        Reporter reporter) {

    Config {
        allowedMethods = Set.copyOf(allowedMethods);
        Objects.requireNonNull(reporter);
    }
}
```

Đây là **trích đoạn**: `Reporter` cần được định nghĩa và các import `Set`, `Objects` phải có. Ví dụ hoàn chỉnh ở mục 6 dùng `Consumer<ProbeEvent>` thay `Reporter`.

Một `record` có các component field `final`, nhưng **không tự động deep-immutable**: nếu component trỏ tới `HashSet` mutable thì người khác vẫn có thể sửa nội dung. `Set.copyOf` bảo vệ tập method khỏi việc bị sửa qua reference nguồn. Nếu dùng map/lists/predicates có state, cũng phải thiết kế immutability tương ứng.

Lưu ý `reporter`/`sink` có thể là một object **có state** (queue, socket, metrics exporter). Snapshot chốt **danh tính và cấu hình sink** theo một policy; không làm sink tự trở thành immutable hoặc luôn sống mãi.

### 3.2. `AtomicReference<Config>` và memory visibility

```java
private final AtomicReference<Config> current =
        new AtomicReference<>(initialConfig);
```

Đây là **field minh họa**, trong đó `initialConfig` đã có. Theo Javadoc Java 17, `get()` có memory effects của volatile read, còn `set()` có memory effects của volatile write. Các threads có thể quan sát được object cấu hình đã được xây xong và publish đúng cách.

Với **một writer**, có thể dùng:

```java
private volatile Config current;

void publish(Config next) {
    current = next;
}
```

Reader phải giữ `Config c = current;` rồi dùng `c` cho tất cả quyết định trong invocation. **Không** đọc lặp `current.enabled()`, `current.allowedMethods()`, `current.reporter()` ở từng dòng — như vậy vẫn có thể trộn các phiên bản.

Với **nhiều writer** thay đổi một số trường của cấu hình, `AtomicReference.updateAndGet` hoặc vòng lặp `compareAndSet` phù hợp hơn vì cho phép cập nhật theo giá trị hiện tại một cách nguyên tử.

## 4. Snapshot phải sống cùng invocation, không chỉ cùng một hook

Chốt `Config` một lần ở entry là **chưa đủ** nếu exit hook lại gọi `current.get()`.

Mẫu dễ sai:

```text
ENTRY:
  if currentConfig.accepts(method):
      start = nanoTime()

EXIT:
  if currentConfig.accepts(method):
      emit(now-start)
```

Có hai lỗi nghiêm trọng:

1. **Entry được chấp nhận, exit bị tắt:** không ghi duration hoặc mất event hoàn tất.
2. **Entry bị từ chối, exit vừa được bật:** exit cố sử dụng `start` không được tạo, hoặc phát event không có event enter tương ứng.

Thiết kế đúng:

```text
ENTRY(methodId):
  Config c = current.get()       // chỉ đọc đúng một snapshot
  if (!c.accepts(methodId)):     // chốt enabled + filter + sampling
      return NO_TOKEN
  return Token(c, methodId, System.nanoTime())

EXIT(token, outcome):
  if token == NO_TOKEN:
      return
  token.finish(outcome)          // dùng config + sink đã chốt
```

`NO_TOKEN` có thể biểu diễn bằng `null` trong demo; thư viện thực tế có thể dùng một singleton noop scope hoặc cấu trúc tối ưu khác. **Token là state theo invocation**, không phải một field global ghi đè giữa các thread.

### 4.1. Quyết định nhất quán phải bao gồm các yếu tố liên quan

Một snapshot tốt không chỉ giữ `enabled`, mà còn:

- Tập method/class cho phép, hoặc predicate filter đã đóng băng.
- Tỷ lệ sampling / seed / rule sampling áp dụng cho invocation.
- Tên service, resource metadata cần đi kèm event.
- Version/generation để chẩn đoán sau reload.
- Reporter/sink hoặc một tham chiếu routing ổn định, nếu chính sách là mỗi invocation gửi vào sink đã chọn lúc bắt đầu.
- Các giới hạn về dữ liệu/ẩn thông tin nhạy cảm liên quan đến chính event.

Nếu `enabled` của v1 và filter của v2 nhưng sampler của v3, một token có thể phản ánh cấu hình chưa bao giờ tồn tại. **Một object snapshot** giúp ta định nghĩa chính xác policy sử dụng nhất quán.

### 4.2. Chọn “một lần gọi” hay “một request”?

Mỗi invocation có thể bắt đầu ở các thời điểm khác nhau. Nếu request gọi method A trước thời điểm reload và method B sau thời điểm reload, **per-invocation** có thể tạo A theo v1, B theo v2; điều này là hợp lệ.

Nếu toàn request bắt buộc dùng cùng phiên bản:

```text
request starts -> chốt Config v1 vào request context
   A uses v1
   config updated to v2
   B still uses v1
request ends
```

Khi đó phải **truyền snapshot qua request context**, bao gồm async boundaries và các thread liên quan; chỉ đọc `AtomicReference` ở mỗi method entry là chưa đủ để đạt request-level consistency.

## 5. Quy tắc áp dụng khi bật/tắt hoặc đổi filter

Giả sử cấu hình:

```text
v1: enabled=true,  methods={checkout}
v2: enabled=false, methods={}
v3: enabled=true,  methods={inventory}
```

Kết quả theo chính sách per-invocation:

| Invocation bắt đầu lúc | Method | Trong khi chạy | Kết quả |
|---|---|---|---|
| `v1` | `checkout` | Chuyển sang `v2` trước exit | **Ghi một event theo v1** |
| `v2` | `checkout` | Bật lại `v3` trước exit | **Không tạo event** |
| `v3` | `checkout` | Không đổi | **Không tạo event**, vì filter v3 không chứa method |
| `v3` | `inventory` | Không đổi | **Ghi event theo v3** |
| `v3` | `inventory` | Method ném exception | **Ghi exceptional event theo v3** nếu exit hook bao phủ ngoại lệ |

Từ “bật/tắt điểm đo” trong ngữ cảnh runtime này nói về **hook đã tồn tại nhưng có được thu thập hay không**. Nó không tự thêm hook vào một method **chưa từng được instrument**; khác biệt đó quan trọng ở mục 11.

## 6. Ví dụ Java 17+ hoàn chỉnh: khóa snapshot với `AtomicReference`

Ví dụ chạy trên JDK 17+ và **không cần Java agent thật** để kiểm tra concurrency logic. Ta mô phỏng entry/exit hook bằng `invoke(...)`, sau đó dùng `CountDownLatch` ép trình tự reload **xảy ra trong lúc một invocation đang chờ**. Điều này làm kết quả có thể tái lập, thay vì phụ thuộc `Thread.sleep()` và tốc độ máy.

Bài thực hành đã được biên dịch với `javac --release 17` và chạy trên OpenJDK 24.0.2. Đây là **thử nghiệm controller/hook logic**; khi tích hợp agent thật, phải đưa `enter` và `finish` vào bytecode advice phù hợp.

### 6.1. Cấu trúc thư mục

```text
config-snapshot-demo/
└── ConfigSnapshotDemo.java
```

Chỉ cần **một file Java**.

### 6.2. Toàn bộ `ConfigSnapshotDemo.java`

```java
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import java.util.function.Supplier;

public final class ConfigSnapshotDemo {
    record ProbeEvent(String method, long version,
                      String outcome, long durationNanos) {}

    record ProbeConfig(long version, boolean enabled,
                       Set<String> methods, Consumer<ProbeEvent> sink) {
        ProbeConfig {
            methods = Set.copyOf(methods);
            Objects.requireNonNull(sink, "sink");
        }

        boolean accepts(String method) {
            return enabled && methods.contains(method);
        }
    }

    static final class ProbeController {
        private final AtomicReference<ProbeConfig> current;

        ProbeController(ProbeConfig initial) {
            current = new AtomicReference<>(initial);
        }

        Ticket enter(String method) {
            ProbeConfig snapshot = current.get();
            if (!snapshot.accepts(method)) {
                return null;
            }
            return new Ticket(method, snapshot, System.nanoTime());
        }

        ProbeConfig configure(boolean enabled, Set<String> methods) {
            return current.updateAndGet(old ->
                    new ProbeConfig(old.version() + 1, enabled,
                                    methods, old.sink()));
        }
    }

    static final class Ticket {
        private final String method;
        private final ProbeConfig snapshot;
        private final long startedAt;
        private final AtomicBoolean finished = new AtomicBoolean();

        Ticket(String method, ProbeConfig snapshot, long startedAt) {
            this.method = method;
            this.snapshot = snapshot;
            this.startedAt = startedAt;
        }

        void finish(String outcome) {
            if (finished.compareAndSet(false, true)) {
                long duration = System.nanoTime() - startedAt;
                snapshot.sink().accept(new ProbeEvent(
                        method, snapshot.version(), outcome, duration));
            }
        }
    }

    static <T> T invoke(ProbeController probe,
                        String method, Supplier<T> operation) {
        Ticket ticket = probe.enter(method);
        T value;
        try {
            value = operation.get();
        } catch (RuntimeException | Error original) {
            if (ticket != null) ticket.finish("EXCEPTIONAL");
            throw original;
        }
        if (ticket != null) ticket.finish("NORMAL");
        return value;
    }

    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<ProbeEvent> events =
                new ConcurrentLinkedQueue<>();
        ProbeController probe = new ProbeController(
                new ProbeConfig(1, true, Set.of("checkout"), events::add));

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread inFlight = new Thread(() -> {
            invoke(probe, "checkout", () -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(e);
                }
                return 10;
            });
        }, "checkout-worker");
        inFlight.start();

        entered.await(); // checkout đã lấy snapshot v1.
        ProbeConfig disabled = probe.configure(false, Set.of());
        System.out.println("[reload] version=" + disabled.version()
                + " enabled=" + disabled.enabled());
        release.countDown();
        inFlight.join();

        invoke(probe, "checkout", () -> 11);
        System.out.println("[disabled] events=" + events.size());

        ProbeConfig filtered = probe.configure(
                true, Set.of("inventory"));
        invoke(probe, "checkout", () -> 12);
        invoke(probe, "inventory", () -> 13);
        try {
            invoke(probe, "inventory", () -> {
                throw new IllegalArgumentException("demo");
            });
        } catch (IllegalArgumentException expected) {
            // Application vẫn thấy exception gốc.
        }

        System.out.println("[filter] version=" + filtered.version()
                + " enabled=" + filtered.enabled());
        for (ProbeEvent e : events) {
            System.out.println("[event] " + e.method()
                    + " v=" + e.version()
                    + " outcome=" + e.outcome());
        }
        System.out.println("[total] events=" + events.size());
    }
}
```

### 6.3. Giải thích các quyết định trong code

**`ProbeConfig` là một record:**

- `version`, `enabled`, `methods`, `sink` được giữ trong **một object**.
- `Set.copyOf(methods)` tạo tập bất biến theo hợp đồng; code không mutate filter đang được token cũ dùng.
- `Objects.requireNonNull` từ chối sink null trước khi publish.
- `version` cho phép phân biệt event đến từ thời điểm cấu hình nào.

**`ProbeController` là nơi duy nhất publish cấu hình:**

```java
private final AtomicReference<ProbeConfig> current;
```

Mọi hook chỉ truy cập qua `enter` và gọi `current.get()` **một lần**. Phương thức `configure` dùng `updateAndGet` để publish một bản cấu hình mới với `version+1` nguyên tử; nếu có contention, function có thể được áp dụng lại. Vì thế function ở đây **không log, không gửi event, không cập nhật counter phụ**.

**`Ticket` chứa state của đúng một invocation:**

- `snapshot` lưu cấu hình của thời điểm entry.
- `startedAt` chỉ được lấy khi method được chấp nhận, giảm chi phí ở nhánh disabled.
- `AtomicBoolean finished` ngăn một token bị ghi event **hai lần** nếu code gọi `finish` lặp.
- `finish` phát event tới `snapshot.sink()`, **không đọc lại** `ProbeController.current`.
- `durationNanos` được giữ trong event nhưng **không in** ra stdout dự kiến vì giá trị thời gian phụ thuộc môi trường.

`AtomicBoolean` trong demo còn cho thấy cách bảo vệ token khỏi accidental double-finish. Một instrumentation tối ưu có thể bỏ bước atomic này nếu chứng minh mỗi invocation luôn chỉ kết thúc bằng đúng một hook, nhưng khi đó phải chắc chắn cả normal và exceptional paths đều được kiểm soát.

**`invoke` mô phỏng vị trí entry/exit:**

- Lấy ticket trước khi thực thi operation.
- Trả về giá trị gốc sau khi ghi `NORMAL`.
- Nếu operation ném `RuntimeException` hoặc `Error`, ghi `EXCEPTIONAL` rồi **rethrow cùng exception**.
- Mô hình `Supplier<T>` không hỗ trợ checked exceptions; khi instrument method Java tùy ý, cần xử lý chính xác cả đường thoát do `Throwable` theo hợp đồng JVM, không chỉ sao chép wrapper này.

**`CountDownLatch` làm ví dụ quyết định được thứ tự:**

1. Worker tạo ticket `checkout` ở v1.
2. Worker báo `entered.countDown()` rồi chờ `release`.
3. Main `entered.await()` nên biết ticket **đã được tạo**.
4. Main publish v2 disabled.
5. Main `release.countDown()` và `inFlight.join()`.
6. Worker finish với v1, dù v2 đã là cấu hình hiện tại.
7. Main kiểm tra một lần gọi mới ở v2 không phát event; sau đó publish v3 filter chỉ nhận `inventory`.

Nhờ đồng bộ này, bài test không cần `Thread.sleep` hoặc dự đoán scheduler.

### 6.4. Lệnh biên dịch và chạy

Tại thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 ConfigSnapshotDemo.java
java -cp . ConfigSnapshotDemo
```

`record`, `AtomicReference`, `CountDownLatch`, `Set.copyOf`, `ConcurrentLinkedQueue` đều có ở Java 17; không cần ASM, Byte Buddy hay preview feature.

**Stdout đã được kiểm tra thực tế:**

```text
[reload] version=2 enabled=false
[disabled] events=1
[filter] version=3 enabled=true
[event] checkout v=1 outcome=NORMAL
[event] inventory v=3 outcome=NORMAL
[event] inventory v=3 outcome=EXCEPTIONAL
[total] events=3
```

**Đọc kết quả đúng ngữ nghĩa:**

- `events=1` sau khi tắt **không phải lỗi**. Một `checkout` đã được chấp nhận ở v1 và hoàn tất sau reload; ticket chốt snapshot v1.
- Lời gọi `checkout` **mới** ở v2 không phát thêm event.
- Ở v3, `checkout` bị filter từ chối, còn hai invocation `inventory` được ghi.
- Một invocation `inventory` trả bình thường và một invocation ném `IllegalArgumentException`; hai event cùng v3, với outcome khác nhau.
- Tổng event là `3`; không có duplicate event do reload.

Đây là stdout ổn định cho **thứ tự lập trình đã được latch đảm bảo** và sink queue trong demo. Thời lượng `durationNanos` có thật trong record nhưng không được đưa vào expected stdout.

### 6.5. Bài test chứng minh điều gì, và chưa chứng minh điều gì?

Nó **chứng minh**:

- Một invocation có thể dùng snapshot v1 xuyên suốt, ngay cả khi v2 được publish giữa entry và exit.
- Quyết định filter, enabled và sink được lấy từ **cùng object**.
- Reload không làm invocation v1 tự chuyển sang v2.
- Các invocation mới dùng cấu hình mới khi bắt đầu sau publication.
- Code mô phỏng normal/exceptional exit mà không thay đổi kết quả của operation trong trường hợp sink hoạt động bình thường.

Nó **chưa tự chứng minh** một Java agent production đã chèn hook đúng tất cả return/exception paths, đã tránh recursion, hoặc event sink sẽ không bao giờ ném lỗi. Đó là các yêu cầu tích hợp riêng.

## 7. Khi có nhiều thread cùng sửa cấu hình

Nếu chỉ có một control thread được phép publish cấu hình trọn bộ, `volatile Config` với một lần gán là đủ cho **publication**. Nhưng nếu có nhiều nguồn thay đổi **từng phần** — ví dụ UI bật/tắt, server thay filter, pipeline đổi sink — cần chống **lost update**.

### 7.1. Mẫu cập nhật dễ mất dữ liệu

Giả sử:

```java
Config old = current.get();

// Admin A từ old tạo bản bật/tắt.
Config a = new Config(old.version() + 1, false,
                      old.allowedMethods(), old.reporter());

// Admin B cũng từ cùng old tạo bản thay filter.
Config b = new Config(old.version() + 1, old.enabled(),
                      Set.of("inventory"), old.reporter());

current.set(a);
current.set(b);
```

Đây là **pseudocode Java**, đòi các biến/type có sẵn. Sau `current.set(b)`, thay đổi `enabled=false` của A có thể bị ghi đè bằng `enabled` cũ từ B. Dù mỗi `set` được publish nguyên tử, **hai writers vẫn có thể làm mất ý định cập nhật từng phần**.

### 7.2. Dùng `updateAndGet` cho read-modify-write nguyên tử

Nếu muốn chỉ bật/tắt, giữ filter hiện tại:

```java
ProbeConfig updated = current.updateAndGet(old ->
        new ProbeConfig(
                old.version() + 1,
                false,
                old.methods(),
                old.sink()));
```

Nếu muốn chỉ thay filter, giữ cờ hiện tại:

```java
ProbeConfig updated = current.updateAndGet(old ->
        new ProbeConfig(
                old.version() + 1,
                old.enabled(),
                Set.of("inventory"),
                old.sink()));
```

Hai đoạn là **minh họa thuộc lớp quản lý cấu hình**, không phải class runnable độc lập. `AtomicReference.updateAndGet` thực hiện atomic read-modify-write; lambda có thể chạy lại khi CAS contention xảy ra, do đó **phải side-effect-free**.

Nếu hệ thống quản lý cấu hình theo **revision do client cung cấp**, có thể dùng `compareAndSet(expected, next)` để từ chối một bản cập nhật dựa trên revision cũ. `version` do server tăng để audit không tự thay thế kiểm tra concurrency của client; cần chính sách rõ ràng cho last-write-wins, conflict rejection hoặc merge.

### 7.3. Build, validate, rồi publish

Một chuỗi triển khai an toàn:

```text
Nhận yêu cầu cập nhật
          |
          v
Parse + validate config mới
          |
          v
Biên dịch filter/pattern ngoài hot path
          |
          v
Tạo immutable Config snapshot
          |
          v
AtomicReference.set/updateAndGet/CAS
          |
          v
New invocation bắt đầu nhìn config mới
```

**Không publish cấu hình nửa xong**, ví dụ publish `enabled=true` trước rồi mới nạp danh sách regex hoặc tạo sink. Nếu tạo sink mới thất bại, giữ cấu hình cũ thay vì công khai một cấu hình không sử dụng được.

Nếu filter chứa regex, cần giới hạn độ dài/độ phức tạp của pattern và xác định lỗi regex **trước publication**, không để hook nóng phát hiện lỗi config đầu vào.

## 8. Khi tắt điểm đo, các invocation cũ có nên tiếp tục phát event?

Đây là quyết định nghiệp vụ, không chỉ quyết định dùng `volatile` hay `AtomicReference`.

| Chính sách | Lợi ích | Cái giá |
|---|---|---|
| **Per-invocation snapshot** | Một invocation được chọn có dữ liệu hoàn chỉnh theo cùng phiên bản | Event v1 có thể xuất hiện sau khi v2 đã tắt |
| Kiểm tra lại cờ `enabled` khi exit | Có thể ngăn phát event sau khi tắt | Dễ bỏ mất exit của invocation đã có enter; timeline thiếu dữ liệu |
| Dùng `epoch` để drop event cũ tại sink | Ngăn lưu event thế hệ cũ | Chủ động bỏ dữ liệu in-flight; phải ghi rõ sampling/drop semantics |
| **Quiesce + drain** invocation cũ trước khi tuyên bố tắt hoàn toàn | Có thể đạt ranh giới mạnh hơn | Cần protocol admission/draining, chờ lâu và chi phí đồng bộ |
| Instrument/retransform lại class để bỏ hook | Có thể giảm overhead về sau | Chi phí retransform lớn, nhiều class/frame cũ còn đang chạy và giới hạn JVM |

Một `AtomicReference.set(v2)` chỉ nói **từ nay reference trỏ tới v2** theo memory semantics; nó **không** đợi các thread đã giữ v1 hoàn tất, cũng không có phép thuật ngăn chúng dùng v1.

Nếu yêu cầu thực sự là “sau API disable trả về, không có event cũ nào được gửi nữa”, cần định nghĩa **điểm tuyến tính hóa** và hợp đồng xác nhận:

1. Ngăn admission mới của v1.
2. Theo dõi/tranh thủ chặn admission đang đua với disable.
3. Chờ hoặc hủy/đánh dấu in-flight v1 theo policy.
4. Chỉ báo hoàn tất sau khi đáp ứng điều kiện mà hệ thống đã cam kết.

**Đếm `active` bằng `AtomicInteger` rồi chỉ chờ đến `0` là chưa đủ nếu không khóa được cuộc đua giữa reader vừa lấy v1 nhưng chưa tăng `active`.** Một protocol drain đúng phải đồng bộ **admission + counter + publication**; không suy rằng hai biến atomic riêng lẻ tự tạo hàng rào giao dịch.

### 8.1. “Dữ liệu cuối đến sau thời điểm tắt” không nhất thiết là vi phạm

Với event chứa:

```text
method=checkout
configVersion=1
startedAt=t1
finishedAt=t3
```

trong khi config v2 được publish ở `t2` (`t1 < t2 < t3`), event xuất hiện sau `t2` nhưng **thuộc invocation đã bắt đầu trước `t2`**. Gắn version/generation và timestamp phù hợp giúp dashboard không báo nhầm lỗi cấu hình.

Không nên đặt tên nhãn là `currentVersion` nếu thực tế event dùng `entryVersion`; chọn tên diễn đạt đúng hợp đồng.

## 9. Bật/tắt runtime guard khác thay đổi bytecode bằng retransform

Một Java agent có thể chèn vào body của method:

```text
onMethodEnter:
  ticket = ProbeRuntime.enter(methodId)

original method body

onMethodExitNormal:
  ProbeRuntime.finish(ticket, NORMAL)

onMethodExitExceptional(Throwable t):
  ProbeRuntime.finish(ticket, EXCEPTIONAL)
  rethrow same Throwable
```

Đây là **pseudocode instrumentation**, không phải Java source runnable. Nó diễn tả dữ liệu `ticket` phải đi từ entry sang cả hai nhánh exit.

Sau khi bytecode hook đã được chèn, có thể thay `ProbeRuntime.currentConfig` để bật/tắt thu thập **mà không retransform lại class cho mỗi lần nhấn nút**. Nhánh disabled chỉ đọc config và bỏ qua những thao tác ghi event tốn kém.

Nhưng hai tầng phải phân biệt:

- **Tầng bytecode topology**: class/method nào đã được JVM instrument? Cần transformer, đôi khi cần `retransformClasses` nếu class đã load.
- **Tầng runtime policy**: trong những hook đã có, invocation nào được ghi? Có thể điều khiển bằng immutable config snapshot.

**Nếu một method chưa có hook, việc thêm tên method vào filter không khiến nó tự được instrument.** Có thể cần retransform những class liên quan để bổ sung hook, tùy chiến lược và capability.

### 9.1. `removeTransformer` không gỡ hook đã cài vào class

`Instrumentation.removeTransformer(t)` chỉ hủy đăng ký transformer cho các sự kiện biến đổi class phù hợp **về sau**. Nó không tự đảo ngược bytecode của class đã được load/transformed. Vì vậy dùng `removeTransformer` thay cho cờ enabled là sai nếu mục tiêu là tắt **việc ghi sự kiện ngay trong code đã instrument**.

`retransformClasses` có chi phí và giới hạn riêng: khả năng retransform do JVM/manifest quyết định; class đã load phải modifiable; các active frames có thể tiếp tục chạy old bytecodes. Nếu thay cấu hình bằng cách retransform hàng nghìn class, đừng gọi đó là một atomic transaction trên tất cả method đang chạy.

## 10. Chốt filter và sampling khi có async, recursion và exception

### 10.1. Method ID phải đủ phân biệt

Filter chỉ bằng method name `"get"` rất dễ bắt nhầm hàng trăm method khác nhau. Một ID thực tế nên gồm:

```text
class binary name + method name + descriptor
```

Và khi cần tránh gộp các runtime class khác nhau, cân nhắc **defining class loader/module identity**.

Ví dụ:

```text
com.example.OrderService.checkout(Ljava/lang/String;)Z
```

Tên này thể hiện cả signature; không dựa vào một method overload cụ thể chỉ từ tên đơn giản.

### 10.2. Sampling cũng cần quyết định một lần

Nếu quyết định sample ở entry nhưng exit đọc một `samplingRate` mới, event có thể trở thành không có cặp. Hãy xác định `sampled` trong cùng snapshot (hoặc một token tạo từ snapshot), rồi giữ quyết định đó suốt invocation.

Với distributed trace, có thể cần dùng trace sampling decision từ context của request thay vì random độc lập ở mỗi method. **Không** dùng `ThreadLocalRandom` ở exit để “kiểm tra lại” một phép lấy mẫu đã được quyết định ở entry.

### 10.3. Recursion và nested method calls

Một method tự gọi lại hoặc gọi method khác được instrument khiến các invocation **lồng nhau**:

```text
enter A (token A1)
  enter B (token B1)
    enter A (token A2)
    exit A (token A2)
  exit B (token B1)
exit A (token A1)
```

Nếu code lưu `currentToken` trong **một static field**, token của A1 có thể bị ghi đè bởi A2/B1; dữ liệu sai ngay cả khi cấu hình đã atomic. Một ticket đúng phải gắn với **invocation cụ thể**, thường lưu vào local state do bytecode advice cấp hoặc cấu trúc context stack phù hợp.

Nếu dùng `ThreadLocal`, phải có **stack push/pop** thay vì một slot đơn lẻ, bảo đảm pop cả khi exception xảy ra và xử lý yêu cầu truyền context qua async tasks. Không tự giả định mọi continuation chạy trên cùng Java thread.

### 10.4. Exceptional exit phải dùng cùng token

Method có thể kết thúc bằng một trong sáu return opcodes hoặc do ngoại lệ không được xử lý trong chính method. Nếu exit hook chỉ cắm trước `return`, các invocation exception sẽ mất event và giữ state. Nếu chỉ hook `ATHROW`, vẫn bỏ sót ngoại lệ JVM phát sinh ngầm hoặc từ callee truyền ra.

Dù dùng ASM, Byte Buddy hay Class-File API, phải đảm bảo normal/exceptional exit được quan sát đúng và truyền **token entry** sang đúng exit tương ứng. Tracer không được làm thay đổi giá trị return hoặc Throwable gốc.

## 11. Hiệu năng: nhánh disabled càng rẻ càng tốt

Vì hook chạy trên đường nóng của ứng dụng, mỗi chi phí nhỏ có thể nhân lên hàng triệu lần:

| Thao tác | Nhánh disabled | Nhánh enabled/accepted |
|---|---|---|
| Đọc `AtomicReference.get()` hoặc `volatile Config` | **Một lần** | **Một lần** |
| Kiểm tra cờ enabled | Có | Có |
| Tra cứu filter | Có thể bỏ qua nếu disabled (short-circuit) | Có |
| `System.nanoTime()` | **Không cần** | Có nếu đo duration |
| Tạo `Ticket` | **Không cần** | Có trong demo |
| Tạo `ProbeEvent` | Không | Khi kết thúc |
| Đẩy vào sink/queue | Không | Khi kết thúc |
| Đồng bộ qua lock chung | Nên tránh | Nên tránh trên hot path |

`AtomicReference.get()` có volatile-read memory semantics. Nó không “miễn phí”, nhưng thường rẻ hơn việc lock một mutex dùng chung cho mọi method entry. Kết quả cụ thể phụ thuộc JVM, CPU, JIT, allocation pressure, contention và kích thước filter; **đo bằng benchmark/JFR trên workload thực**, không đưa một con số nano-giây chung.

### 11.1. Đừng biên dịch regex ở hook

Không làm:

```java
if (Pattern.compile(config.regex()).matcher(methodId).matches()) {
    // ...
}
```

mỗi invocation. Cần chuẩn bị `Pattern` **trước** khi publish config, hoặc chuyển filter thành các tập/hash/predicate tối ưu. Đảm bảo predicate không mutate state chia sẻ, không I/O và không ném lỗi ngoài ý muốn.

### 11.2. Sink cần có hợp đồng không can thiệp

Trong demo, `events::add` ghi vào `ConcurrentLinkedQueue` thread-safe. Queue này **không có giới hạn dung lượng**, nên **không phù hợp mặc định cho production telemetry tốc độ cao**.

Trong thực tế:

- Chọn queue bounded/ring buffer hoặc backpressure/drop policy rõ ràng.
- Không ghi log đồng bộ, gọi mạng hoặc parse cấu hình ở entry/exit hook nóng.
- Theo dõi số event được nhận, bị drop, lỗi exporter và độ trễ.
- Tránh high-cardinality labels (stack trace, request ID, user-specific values) ở metrics.
- Recorder không nên ném exception làm đổi kết quả application.
- Khi thay sink, các ticket cũ có thể còn giữ sink cũ; không đóng sink cũ ngay nếu vẫn muốn hoàn tất event cũ.

### 11.3. `AtomicBoolean finished` không đồng nghĩa exactly-once delivery

`Ticket.finished.compareAndSet(false, true)` ngăn code **cố gửi** từ cùng ticket nhiều lần. Nó **không** bảo đảm exporter đã nhận/bền vững ghi event. Sau khi `finished` chuyển thành true, việc sink lỗi có thể khiến event bị mất, dù không có duplicate.

Nếu cần độ tin cậy phát hành mạnh hơn, phải thiết kế queue, retry, idempotency và khóa định danh event ở **lớp transport/storage**; không thể suy “exactly once end-to-end” chỉ từ `AtomicBoolean`.

### 11.4. Java agent không được gây recursion vô hạn

Nếu agent instrument luôn các class trong recorder, thì `ProbeRuntime.enter` có thể gọi code bị instrument, code đó lại gọi `ProbeRuntime.enter`... dẫn tới recursion hoặc lỗi nạp class. Thực tế phải **loại trừ helper/recorder classes khỏi filter và transformer**, hoặc có guard reentrancy chuyên biệt.

## 12. Khi nào nên dùng `volatile`, `AtomicReference` hay lock?

| Cơ chế | Khi phù hợp | Điều không tự bảo đảm |
|---|---|---|
| `volatile Config` bất biến | Một writer publish trọn object; readers chỉ đọc snapshot | Cập nhật đọc-sửa-ghi giữa nhiều writers |
| `AtomicReference<Config>` + `set` | Publish nguyên object, semantics rõ ràng | Không chống lost-update nếu writers tạo từ stale snapshots |
| `AtomicReference.updateAndGet` | Nhiều writers cập nhật từ bản hiện tại | Không tự giải quyết các xung đột nghiệp vụ/rollback |
| `compareAndSet(expected,next)` | Kiểm tra optimistic revision, từ chối writer dùng stale state | Caller phải retry hoặc báo conflict |
| `synchronized`/`Lock` | Cần phối hợp nhiều tài nguyên ngoài config, hoặc barrier thật sự | Tăng contention nếu readers trên hot path cũng lock |
| `ReadWriteLock` | Một số workload đọc nhiều và cần nhất quán tài nguyên phức tạp | Có thể vẫn nặng hơn một immutable snapshot read |
| `LongAdder`/`AtomicLong` | Đếm event hoặc số lần drop độc lập | Không thay cho atomic snapshot của nhiều field |

**Không có một primitive nào tự biến cấu hình, classloader, bytecode topology và exporter thành một giao dịch duy nhất.** Chọn ranh giới consistency dựa trên hợp đồng quan sát mà hệ thống cần.

### 12.1. Tránh ABA và rollback không mong đợi

Nếu hai snapshots có nội dung `enabled/filter` giống nhau nhưng được publish ở hai thời điểm khác nhau, chúng vẫn là **hai generations** khác nhau. Giữ `version` tăng đơn điệu giúp audit, so sánh rollout và phát hiện event cũ.

`AtomicReference.compareAndSet` so reference identity, không so nội dung config; đừng dùng `equals` như một thay thế tự động khi áp dụng CAS. Nếu muốn rollback, publish **một snapshot mới với revision mới** chứa nội dung cần khôi phục, thay vì đưa version về số cũ và tạo event khó truy vết.

## 13. Chiến lược kiểm thử concurrent reload có thể tái lập

Không nên chỉ viết test:

```java
Thread.sleep(100);
config.enabled = false;
```

rồi đoán invocation đã chạy tới đâu. Lệnh `sleep` không chứng minh luồng công việc đang ở đúng giai đoạn. Dùng `CountDownLatch`, `CyclicBarrier` hoặc điều kiện chờ có hợp đồng rõ ràng.

Những scenario cần test:

1. Invocation bắt đầu ở v1 được chấp nhận; đổi sang v2 disabled trước exit. **Chỉ một event v1**.
2. Invocation bắt đầu ở disabled v2; bật v3 trước exit. **Không phát event** cho invocation đó.
3. Filter v1 chỉ nhận `checkout`, v3 chỉ nhận `inventory`. Method bắt đầu trong mỗi phiên bản phải dùng đúng filter.
4. Reload đồng thời từ hai control threads. Không có **cấu hình pha trộn** hoặc lost update ngoài policy đã định nghĩa.
5. Cấu hình mới có regex/sink không hợp lệ. Không publish nửa chừng; giữ snapshot cũ.
6. Method throw exception. Exit nhận cùng token, outcome exceptional, không làm mất Throwable.
7. Method gọi lồng nhau hoặc recursive. Token của từng invocation không đè lên nhau.
8. Nhiều class loaders định nghĩa cùng method name. Filter cần định danh không nhập nhằng.
9. Disabled hot path không tạo event/ticket và tránh clock calls không cần thiết.
10. Exporter chậm/lỗi/drop. Instrumentation không đổi hành vi business code; loss counters thể hiện rõ.
11. Thay sink trong lúc có invocation cũ. Sink cũ sống đủ lâu hoặc có drain protocol.
12. Reconfiguration có hàng nghìn concurrent readers; đo CPU, allocation, tail latency và throughput.
13. Nếu yêu cầu hard disable, kiểm thử cả cuộc đua **reader lấy v1 nhưng chưa register in-flight**.
14. Nếu có async continuations, kiểm tra truyền request-level config/context và không leak thread-local state.

Một biểu đồ log có `configVersion` ở **event** sẽ giúp phân biệt “event đến muộn” và “điểm đo đọc nhầm phiên bản”.

## 14. Những lỗi thiết kế thường gặp

| Nhầm lẫn | Hậu quả | Sửa thế nào |
|---|---|---|
| Dùng hai cờ `volatile` độc lập | Reader nhìn trạng thái v1/v2 pha trộn | Publish một Config bất biến |
| Chốt config ở entry nhưng đọc lại ở exit | Thay filter giữa chừng làm mất cặp event | Truyền ticket chứa snapshot |
| Sửa `HashSet` filter đang dùng | Data race, kết quả bất định | `Set.copyOf`, thay object |
| Dùng một static `startedAt` cho mọi thread | Duration lẫn invocation | Token per invocation |
| Một `ThreadLocal` slot cho nested calls | Outer scope bị inner ghi đè | Stack/push-pop hoặc local token |
| `updateAndGet` lambda gọi I/O/log | Lambda có thể chạy lại do contention | Lambda side-effect-free |
| Dùng `set` từ stale snapshot ở nhiều writers | Lost updates | CAS / `updateAndGet` có merge policy |
| Publish enable trước khi tạo sink | Hook có thể gọi sink chưa sẵn sàng | Build/validate rồi publish một lần |
| Tắt `enabled` được hiểu là chờ mọi call cũ xong | Có event v1 sau thời điểm tắt | Công bố per-invocation semantics hoặc drain |
| Thay filter khiến method chưa instrument tự có hook | Không có event dù allowed | Chèn hook theo topology/retransform khi cần |
| `removeTransformer` để gỡ hook cũ | Bytecode đã cài vẫn gọi probe | Runtime guard hoặc retransform phù hợp |
| Sink callback ném exception | Thay đổi kết quả method business | Reporter nonthrowing/failure isolation |
| Queue vô hạn | Memory tăng khi exporter chậm | Bounded buffer + drop policy |
| In duration thật trong expected stdout | Test không ổn định | Chỉ assert outcome/version/count |
| Không ghi version trong event | Khó giải thích event cũ đến muộn | Chốt generation ở token |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao hai field `volatile boolean enabled` và `volatile Set<String> filter` chưa đủ?

**Đáp án:** Chúng có visibility riêng nhưng reader đọc hai thời điểm khác nhau có thể ghép giá trị của hai phiên bản. Cần một object snapshot bất biến được publish qua một reference.

**Câu 2.** Vì sao gọi `current.get()` một lần ở entry tốt hơn gọi lại ở exit?

**Đáp án:** Entry, filter, sampler, start timestamp và sink đều thuộc cùng cấu hình. Đọc lại ở exit có thể tạo event thiếu cặp hoặc sai sink.

**Câu 3.** Đã tắt ở v2 nhưng thấy event v1 tới sau. Theo per-invocation semantics có sai không?

**Đáp án:** Không. Invocation được chấp nhận ở v1 và vẫn có quyền hoàn tất theo snapshot v1. Để cam kết không còn event cũ cần policy mạnh hơn.

**Câu 4.** Tại sao `Set.copyOf(methods)` quan trọng?

**Đáp án:** Tránh việc một reference bên ngoài mutate tập filter đang được nhiều invocation dùng; record field `final` một mình không làm collection mutable trở nên bất biến.

**Câu 5.** `updateAndGet` có thể gọi lambda nhiều lần không?

**Đáp án:** Có, khi CAS contention. Lambda phải side-effect-free.

**Câu 6.** Một method chưa từng được instrument nhưng filter vừa thêm method đó. Có tự xuất hiện event không?

**Đáp án:** Không. Cần có bytecode hook trước; runtime config chỉ điều khiển hook đã tồn tại.

**Câu 7.** Có thể dùng `ThreadLocal<Ticket>` một slot cho recursion không?

**Đáp án:** Không an toàn cho nested invocation vì token mới ghi đè token ngoài. Dùng stack hoặc local token riêng theo invocation.

**Câu 8.** Một `AtomicBoolean finished` bảo đảm event đã được server nhận đúng một lần?

**Đáp án:** Không. Nó chỉ ngăn gọi `finish` lặp trên ticket; exporter/queue có thể làm mất hoặc gửi lặp event khi retry nếu chưa có giao thức tương ứng.

**Câu 9.** Muốn ngăn tất cả old-version events sau khi disable API trả về, `AtomicReference.set` có đủ không?

**Đáp án:** Không. Phải thiết kế admission/quiescence/drain hoặc chính sách drop epoch phù hợp, chú ý race giữa nhận snapshot và đăng ký in-flight.

**Câu 10.** Trong ví dụ, vì sao kết quả in `checkout v=1` sau khi log `[reload] version=2`?

**Đáp án:** Thread worker đã tạo ticket v1 trước khi main publish v2, nhờ latch. `finish` dùng snapshot trong ticket chứ không đọc lại config.

**Câu 11.** Nếu hai control threads muốn thay hai trường độc lập và cùng dùng `set` từ stale snapshot thì sao?

**Đáp án:** Có nguy cơ lost update. Dùng atomic read-modify-write (`updateAndGet`/CAS), xác định chính sách merge và conflict.

**Câu 12.** Trong ví dụ, một `inventory` ném `IllegalArgumentException` thì event nào được ghi?

**Đáp án:** `inventory v=3 outcome=EXCEPTIONAL`; exception được truyền lại cho caller nếu sink không can thiệp.

## 16. Checklist áp dụng cho Java instrumentation thật

| Hạng mục | Điều cần xác nhận |
|---|---|
| Đơn vị consistency | Invocation hay request; có cần hard disable không? |
| Cấu hình được publish nguyên khối | Một immutable Config object |
| Mutable collection đã được sao chép | Không mutate filters đang dùng |
| Hot path đọc bao nhiêu lần? | Một atomic/volatile snapshot read tại entry |
| Entry token chứa gì? | Config version, sampling decision, start time, sink/routing |
| Disabled path | Không tạo ticket/event, không clock/I/O thừa |
| Exit hook | Dùng **đúng token entry**; bao phủ normal/exception |
| Nested/recursive | Không overwrite token khác invocation |
| Async boundaries | Context được truyền có chủ ý |
| Concurrent writers | CAS/updateAndGet, conflict policy rõ ràng |
| Validate trước publish | Filter/sink/regex hợp lệ |
| In-flight policy | Event v1 có được gửi sau v2 không? |
| Sink lifetime | Old sink chưa bị đóng khi còn token cũ |
| Exporter failures | Không phá business result; có drop metrics |
| Instrumentation topology | Method đã có hook? Nếu chưa, cần transformer |
| Hiệu năng | Đo allocation, CPU, tail latency dưới tải |
| QA | Latches, exceptional path, reload stress, event version |

## 17. Kết luận

- **Không** cập nhật `enabled`, `filter`, `sampler`, `sink` bằng nhiều mutable fields rồi kỳ vọng mọi thread nhìn một cấu hình nhất quán.
- Hãy tạo một **Config bất biến**, validate trước, rồi publish **một tham chiếu nguyên tử**.
- Ở method entry, đọc snapshot **đúng một lần**; lưu vào **token riêng của invocation**. Method exit phải dùng token đó, không đọc config hiện tại lần nữa.
- Theo chính sách per-invocation, lời gọi bắt đầu ở **v1** được ghi theo v1 ngay cả khi control thread đã publish **v2 disabled** trước khi nó kết thúc.
- `AtomicReference.updateAndGet` giúp cập nhật từ bản hiện tại khi nhiều writers cạnh tranh; lambda phải **không có side effects**.
- Atomic config không tự gỡ bytecode hook, không tự làm hard stop mọi invocation cũ và không giải quyết exporter/backpressure. Đó là những hợp đồng riêng.
- Ví dụ Java 17+ chứng minh bằng `CountDownLatch` rằng **filter, enabled, version và sink được chốt nhất quán** trong điều kiện reload đồng thời.

## Tài liệu tham khảo chính thức

- Oracle JDK 17 — [`AtomicReference`: `get`, `set`, `compareAndSet`, `updateAndGet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).
- Oracle JDK 17 — [`AtomicBoolean`: `compareAndSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html).
- Oracle JDK 17 — [`CountDownLatch`: happens-before và await`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).
- Oracle JDK 17 — [`Set.copyOf` và immutable collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)).
- Oracle JDK 17 — [`ConcurrentLinkedQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html).
- Oracle Java SE 17 — [Java Language Specification §17.4: Memory Model, synchronization và happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4).
- Oracle JDK 17 — [`Instrumentation`: transformer, retransform, removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle JDK 17 — [`ClassFileTransformer`: callback và chaining contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
