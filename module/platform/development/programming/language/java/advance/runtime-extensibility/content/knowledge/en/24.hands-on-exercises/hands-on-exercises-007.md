# Bài thực hành: Thay phiên bản plugin khi đang có yêu cầu và kiểm tra dọn tài nguyên

Một hệ thống Java hỗ trợ plugin có thể cập nhật implementation khi ứng dụng vẫn phục vụ request. Khó khăn không nằm ở việc gán biến currentPlugin = newPlugin, mà ở **những request đã bắt đầu dùng plugin cũ** và **các tài nguyên của phiên bản cũ**. Nếu đóng file/JAR, connection pool hoặc worker đang được request sử dụng, request có thể lỗi giữa chừng; nếu không đóng bao giờ, host sẽ rò rỉ bộ nhớ, threads, file handles và class loaders sau mỗi lần thay phiên bản.

Bài thực hành này xây một **router có generation, lease và graceful drain**, cố tình cho một yêu cầu của v1 đứng chờ, chuyển router sang v2 khi yêu cầu ấy vẫn còn in-flight, xác nhận yêu cầu mới chạy v2, sau đó cho yêu cầu v1 kết thúc và kiểm tra việc dọn tài nguyên. Ví dụ dùng **Java 17+**, hai luồng có CountDownLatch để tạo trình tự kiểm thử lặp lại được, bộ đếm đóng tài nguyên để xác minh điều kiện **close đúng một lần**, không cần HTTP server, Maven, Gradle hoặc JAR bên ngoài.

Mục tiêu hoàn thành:

1. Một request nhận **lease của v1 trước thời điểm chuyển** luôn tiếp tục chạy trên v1, dù route đã chọn v2.
2. Các request **được nhận sau khi chuyển** đi qua v2.
3. v1 vào trạng thái **DRAINING**, không được đóng khi còn in-flight.
4. Khi lease cuối cùng của v1 được trả và đã có yêu cầu retire, resource v1 được đóng **đúng một lần**.
5. v2 vẫn mở khi đang ACTIVE, được đóng khi host shutdown và không còn request.
6. Không có việc xử lý request hoặc dọn tài nguyên nặng bên trong khóa route.
7. Phân biệt được bằng chứng **close được gọi**, **tài nguyên đã được hệ thống giải phóng**, và **class loader có thể được garbage collect**: đây là ba mức khẳng định khác nhau.

Đây là **bài thực hành mô hình một JVM**. Nó xác minh các bất biến nền tảng và kỹ thuật đồng bộ, nhưng không tự thay thế một plugin platform sản xuất có ModuleLayer, URLClassLoader, network streams, database, rollout nhiều node, các side effects và ranh giới bảo mật riêng.

## 1. Bối cảnh và yêu cầu kiểm thử

Giả sử host có hai phiên bản handler:

- **v1** trả kết quả có tiền tố v1.
- **v2** trả kết quả có tiền tố v2.
- **Request A** lấy v1 trước khi switch, rồi tạm dừng nhờ một latch.
- **Main thread** kích hoạt v2 và yêu cầu retire v1.
- **Request B** xuất hiện sau switch, đi vào v2.
- Main thread mới cho request A tiếp tục, sau đó đợi A hoàn thành.
- Host xác minh resource v1 đóng đúng một lần, kể cả khi gọi retire thêm lần nữa.
- Cuối cùng host shutdown v2 và xác minh resource v2 cũng đóng đúng một lần.

**Kịch bản cần quan sát:**

~~~text
Thời gian       Worker xử lý A                     Main / Router
-----------     -------------------------------     ---------------------------
t0                                                  v1 đang ACTIVE
t1              acquire(v1); inFlight(v1)=1
t2              chờ finishOld latch                 xác nhận đã acquire
t3                                                  activate(v2), v1 DRAINING
t4                                                  retire(v1): CHƯA đóng
t5                                                  acquire(v2), xử lý B
t6                                                  release(v2); v2 vẫn ACTIVE
t7                                                  mở finishOld latch
t8              dùng v1 để xử lý A
t9              release(v1); inFlight(v1)=0
t10             worker hoàn thành                   v1 CLOSED, closeCalls(v1)=1
t11                                                 retire(v1) lần 2: không đóng lặp
t12                                                 shutdown: v2 CLOSED
~~~

Các mốc trên mô tả **thứ tự logic được latch bảo đảm**, không giả định tốc độ của hệ điều hành hay dùng Thread.sleep để tạo race. Trong thực tế, request A có thể bắt đầu làm việc rồi đang chờ I/O, còn request B và các request mới đã dùng v2. Bài thực hành dùng latch để điều khiển đúng thời điểm mà không phải chờ một khoảng thời gian đoán mò.

### Phân biệt các từ khóa

| Thuật ngữ | Ý nghĩa trong bài | Không nên hiểu nhầm |
| --- | --- | --- |
| **Generation** | Một instance/version plugin cùng vòng đời, counter và trạng thái | Không đơn giản là chuỗi semantic version |
| **ACTIVE** | Generation nhận các request mới | Không có nghĩa mọi request hiện tại đều dùng generation này |
| **Lease** | Quyền sử dụng một generation gắn với một request | Không phải khóa giữ suốt thời gian chạy business logic |
| **inFlight** | Số lease đã cấp nhưng chưa trả | Không tự tính các callback chạy ngầm ngoài hợp đồng |
| **DRAINING** | Không nhận request mới, chờ lease cũ kết thúc | Không phải đóng tài nguyên ngay |
| **CLOSING** | Đã giành quyền thực hiện cleanup một lần | Không phải bằng chứng cleanup đã xong |
| **CLOSED** | Cleanup trả về thành công | Không khẳng định class đã unload ngay |
| **CLEANUP_FAILED** | Cleanup phát sinh lỗi | Không nên báo CLOSED giả hoặc tự retry mù quáng |

Điểm khó nhất là **atomicity của việc chọn version và tăng inFlight**. Nếu một thread đọc current=v1 rồi chưa kịp tăng inFlight, trong khi thread khác đổi sang v2, thấy inFlight(v1)=0 và đóng v1, request cũ có thể dùng một resource đã đóng. Vì thế trong ví dụ, cả **acquire** và **activate** đều làm việc trong cùng một monitor ngắn.

## 2. Kiến trúc nhỏ để thực hành

Mỗi generation sở hữu một Plugin và tài nguyên được theo dõi:

~~~text
+------------------------------- Host --------------------------------+
|                                                                     |
| Router                                                               |
|   gate: monitor                                                     |
|   active ----------------------------+                              |
|                                      |                              |
|    +---------------+       +---------v----------+                   |
|    | Generation v1 |       | Generation v2      |                   |
|    | DRAINING      |       | ACTIVE             |                   |
|    | inFlight = 1  |       | inFlight = 0        |                   |
|    | retire = true |       | retire = false      |                   |
|    | Plugin(v1)    |       | Plugin(v2)          |                   |
|    | Resource(v1)  |       | Resource(v2)        |                   |
|    +-------^-------+       +--------------------+                   |
|            |                                                        |
|      Lease của A                                                   |
|                                                                     |
+---------------------------------------------------------------------+
~~~

Ở đây, **TrackedResource** là tài nguyên giả lập có closeCalls. Nó thực sự được đóng bằng AutoCloseable.close, nhưng không mở file/JAR thật. Ưu điểm của tài nguyên giả là kết quả kiểm thử **chính xác, đo được, không phụ thuộc GC hoặc filesystem**. Bước mở rộng ở phần sau sẽ gắn vòng đời này với URLClassLoader và các tài nguyên thật.

### Các bất biến cần kiểm tra

- **B1 — Admission:** Chỉ generation ACTIVE nhận lease mới.
- **B2 — Pinning:** Lease giữ đúng generation ở thời điểm được cấp, không đọc lại active mỗi lần xử lý.
- **B3 — Safe retirement:** Một generation đang DRAINING có inFlight lớn hơn 0 không được đóng.
- **B4 — Exactly-once cleanup attempt:** Khi DRAINING, có retirementRequested và inFlight về 0, chỉ một thread được quyền chuyển sang CLOSING và gọi cleanup.
- **B5 — No counter underflow:** Mỗi lease chỉ release một lần, kể cả khi close được gọi lặp.
- **B6 — Short critical section:** Không chạy plugin.handle hoặc plugin.close bên trong monitor bảo vệ routing.
- **B7 — Shutdown:** Khi host ngừng nhận request mới, generation đang ACTIVE chuyển sang DRAINING rồi được đóng khi hết lease.
- **B8 — Failure visibility:** Nếu cleanup ném lỗi, chuyển sang CLEANUP_FAILED; không lẫn với CLOSED.

B1 đến B7 đều được quan sát trong ví dụ; B8 được minh họa bằng đường xử lý exception và có bài tập tạo lỗi ở phần 8.

## 3. Chuẩn bị môi trường

Yêu cầu:

- **JDK 17 trở lên**, có lệnh javac và java. Không yêu cầu thư viện bên thứ ba.
- Một thư mục làm việc chứa duy nhất file **PluginSwapLab.java** của bài thực hành.
- Terminal ở thư mục đó; có quyền tạo file .class khi biên dịch.
- Đọc được stdout và các lỗi nếu test thất bại.

Kiểm tra:

~~~bash
java -version
javac -version
~~~

Phiên bản thực tế phụ thuộc JDK được cài. Dùng **javac --release 17** để biên dịch hướng tới Java 17, miễn compiler hỗ trợ target đó.

Cấu trúc sau biên dịch:

~~~text
plugin-swap-lab/
├── PluginSwapLab.java
├── PluginSwapLab.class
├── PluginSwapLab$Router.class
├── PluginSwapLab$Generation.class
├── PluginSwapLab$Lease.class
├── PluginSwapLab$Plugin.class
├── PluginSwapLab$TrackedResource.class
└── ... các class lồng nhau khác do javac sinh
~~~

Danh sách .class chỉ mang tính minh họa cấu trúc; các class cụ thể như enum State có file .class tương ứng. Không cần gói các .class thành JAR để chạy bài này.

## 4. Chương trình Java 17 đầy đủ

Tạo file **PluginSwapLab.java** và chép nguyên nội dung dưới đây. Mã có một public class duy nhất, dùng package mặc định để chạy gọn bằng java PluginSwapLab.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class PluginSwapLab {
    enum State { PREPARED, ACTIVE, DRAINING, CLOSING, CLOSED, CLEANUP_FAILED }

    static final class TrackedResource implements AutoCloseable {
        private final AtomicInteger closeCalls = new AtomicInteger();

        void checkOpen() {
            if (closeCalls.get() != 0) {
                throw new IllegalStateException("Resource was already closed");
            }
        }

        int closeCalls() { return closeCalls.get(); }

        @Override public void close() { closeCalls.incrementAndGet(); }
    }

    static final class Plugin implements AutoCloseable {
        final String version;
        final TrackedResource resource = new TrackedResource();

        Plugin(String version) { this.version = version; }

        String handle(String request) {
            resource.checkOpen();
            return version + ":" + request;
        }

        int closeCalls() { return resource.closeCalls(); }

        @Override public void close() { resource.close(); }
    }

    static final class Generation {
        final Plugin plugin;
        State state = State.PREPARED;
        int inFlight;
        boolean retirementRequested;

        Generation(String name) { plugin = new Plugin(name); }
    }

    static final class Lease implements AutoCloseable {
        private final Router router;
        private final Generation pinned;
        private final AtomicBoolean returned = new AtomicBoolean();

        Lease(Router router, Generation pinned) {
            this.router = router;
            this.pinned = pinned;
        }

        String handle(String input) {
            if (returned.get()) {
                throw new IllegalStateException("Lease was returned");
            }
            return pinned.plugin.handle(input);
        }

        @Override public void close() {
            if (returned.compareAndSet(false, true)) {
                router.release(pinned);
            }
        }
    }

    static final class Router {
        private final Object gate = new Object();
        private Generation active;

        Router(Generation initial) {
            if (initial.state != State.PREPARED) {
                throw new IllegalArgumentException("Initial is not prepared");
            }
            initial.state = State.ACTIVE;
            active = initial;
        }

        Lease acquire() {
            synchronized (gate) {
                Generation g = active;
                if (g == null || g.state != State.ACTIVE) {
                    throw new IllegalStateException("No active plugin");
                }
                g.inFlight++;
                return new Lease(this, g);
            }
        }

        void activate(Generation candidate) {
            synchronized (gate) {
                if (active == null || candidate.state != State.PREPARED) {
                    throw new IllegalStateException("Invalid cutover");
                }
                Generation old = active;
                old.state = State.DRAINING;
                candidate.state = State.ACTIVE;
                active = candidate;
            }
        }

        void retire(Generation g) {
            Plugin toClose;
            synchronized (gate) {
                if (g == active) {
                    throw new IllegalStateException("Still active");
                }
                if (g.state == State.CLOSED ||
                    g.state == State.CLOSING ||
                    g.state == State.CLEANUP_FAILED) {
                    return;
                }
                if (g.state != State.DRAINING) {
                    throw new IllegalStateException("Not draining");
                }
                g.retirementRequested = true;
                toClose = beginCleanupIfReady(g);
            }
            performCleanup(g, toClose);
        }

        void release(Generation g) {
            Plugin toClose;
            synchronized (gate) {
                if (g.inFlight <= 0) {
                    throw new IllegalStateException("Lease count underflow");
                }
                g.inFlight--;
                toClose = beginCleanupIfReady(g);
            }
            performCleanup(g, toClose);
        }

        private Plugin beginCleanupIfReady(Generation g) {
            if (g.state == State.DRAINING &&
                g.retirementRequested && g.inFlight == 0) {
                g.state = State.CLOSING;
                return g.plugin;
            }
            return null;
        }

        private void performCleanup(Generation g, Plugin plugin) {
            if (plugin == null) return;
            boolean success = false;
            try {
                plugin.close();
                success = true;
            } finally {
                synchronized (gate) {
                    g.state = success ? State.CLOSED : State.CLEANUP_FAILED;
                }
            }
        }

        void shutdown() {
            Generation old;
            synchronized (gate) {
                old = active;
                active = null;
                if (old != null) old.state = State.DRAINING;
            }
            if (old != null) retire(old);
        }

        State stateOf(Generation g) {
            synchronized (gate) { return g.state; }
        }

        int inFlightOf(Generation g) {
            synchronized (gate) { return g.inFlight; }
        }
    }

    public static void main(String[] args) throws Exception {
        Generation v1 = new Generation("v1");
        Generation v2 = new Generation("v2");
        Router router = new Router(v1);

        CountDownLatch oldHasLease = new CountDownLatch(1);
        CountDownLatch finishOld = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            Future<String> oldRequest = worker.submit(() -> {
                try (Lease lease = router.acquire()) {
                    oldHasLease.countDown();
                    if (!finishOld.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Timed out waiting");
                    }
                    return lease.handle("A");
                }
            });

            if (!oldHasLease.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not acquire");
            }

            System.out.println("old-inflight=" + router.inFlightOf(v1));

            router.activate(v2);
            router.retire(v1);

            System.out.println("old-during-switch=" + router.stateOf(v1));
            System.out.println("old-close-before-finish=" + v1.plugin.closeCalls());

            try (Lease lease = router.acquire()) {
                System.out.println("new-request=" + lease.handle("B"));
            }

            finishOld.countDown();
            System.out.println("old-request=" + oldRequest.get(10, TimeUnit.SECONDS));

            System.out.println("old-after-drain=" + router.stateOf(v1));
            System.out.println("old-close-count=" + v1.plugin.closeCalls());

            router.retire(v1);
            System.out.println("old-close-after-retry=" + v1.plugin.closeCalls());

            router.shutdown();
            System.out.println("new-after-shutdown=" + router.stateOf(v2));
            System.out.println("new-close-count=" + v2.plugin.closeCalls());
        } finally {
            finishOld.countDown();
            worker.shutdownNow();
            router.shutdown();
        }
    }
}
~~~

### Vì sao chương trình không cần thư viện plugin thực?

Mục tiêu của bài này là **xác minh bất biến thay phiên bản và dọn tài nguyên trước**, tránh nhiễu từ bộ phân giải classpath, ServiceLoader, ModuleLayer hoặc network. TrackedResource mô phỏng một tài nguyên phải close; vì vậy ta xác minh được chính xác khi nào tài nguyên bị dùng sau close hoặc bị close nhiều lần. Khi cơ chế generation/lease đúng, mới gắn loader, JAR và resource thật vào trong Plugin.

Một điểm đáng chú ý: TrackedResource cố ý **không tự bảo vệ để biến mọi lần close thành một**. Mỗi lần close đều làm AtomicInteger tăng. Nhờ đó, nếu router sai và đóng trùng, kiểm thử nhận thấy closeCalls=2 thay vì che lỗi bằng resource idempotent. Ở sản phẩm, từng loại resource có thể có hoặc không có hành vi idempotent; router vẫn phải bảo đảm không cố đóng lặp.

## 5. Biên dịch, chạy và đối chiếu stdout

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 PluginSwapLab.java
~~~

Chạy:

~~~bash
java PluginSwapLab
~~~

**Stdout đã kiểm chứng từ chương trình nguyên bản trên môi trường JDK 17+:**

~~~text
old-inflight=1
old-during-switch=DRAINING
old-close-before-finish=0
new-request=v2:B
old-request=v1:A
old-after-drain=CLOSED
old-close-count=1
old-close-after-retry=1
new-after-shutdown=CLOSED
new-close-count=1
~~~

Chương trình có timeout 10 giây để **báo lỗi rõ** trong môi trường bị treo hoặc scheduler không phản hồi. Trên máy làm việc bình thường với cả hai luồng được scheduler cho chạy, thứ tự stdout phía trên là xác định vì được đồng bộ bởi hai CountDownLatch và Future.get. Nếu timeout hoặc compiler không đúng phiên bản, đó là điều kiện lỗi cần điều tra, không thay bằng kỳ vọng một output tùy ý.

### Giải thích từng dòng

| Dòng | Bằng chứng |
| --- | --- |
| old-inflight=1 | Worker A đã cấp lease v1, router ghi nhận một request đang dùng v1 |
| old-during-switch=DRAINING | Switch đã dừng cấp lease mới vào v1 nhưng chưa đóng resource |
| old-close-before-finish=0 | v1 còn in-flight nên retire không được gọi close quá sớm |
| new-request=v2:B | Một lease lấy sau cutover đi đúng generation v2 |
| old-request=v1:A | Request A giữ đúng v1 dù v2 đã ACTIVE |
| old-after-drain=CLOSED | Khi A trả lease, counter về 0 và cleanup v1 thành công |
| old-close-count=1 | Cleanup resource v1 được thực hiện đúng một lần |
| old-close-after-retry=1 | Lệnh retire lặp không tạo lần đóng thứ hai |
| new-after-shutdown=CLOSED | Shutdown ngừng admission và dọn v2 sau khi hết lease |
| new-close-count=1 | Resource của v2 cũng được đóng đúng một lần |

**Tiêu chí pass**: tất cả các dòng theo thứ tự, các trạng thái phù hợp, không có exception, và worker kết thúc trong khoảng timeout của test. Chỉ quan sát "chương trình không crash" là chưa đủ, vì một thiết kế không đóng resource cũng có thể chạy hết business logic mà không thấy lỗi ngay.

## 6. Giải phẫu các điểm đồng bộ hóa

### 6.1. Acquire một cách nguyên tử với việc switch

Trong Router.acquire:

~~~java
synchronized (gate) {
    Generation g = active;
    if (g == null || g.state != State.ACTIVE) {
        throw new IllegalStateException("No active plugin");
    }
    g.inFlight++;
    return new Lease(this, g);
}
~~~

Đây là đoạn **trích từ class Router**, không phải chương trình độc lập. Nó buộc việc đọc pointer, kiểm tra ACTIVE và tăng inFlight xảy ra trong cùng một critical section. Switch cũng lấy gate trước khi thay pointer và trạng thái cũ. Do đó chỉ có hai thứ tự được phép:

1. Acquire trước switch: request lấy v1 và inFlight(v1) đã tăng; switch không được dọn v1 sớm.
2. Switch trước acquire: request đọc active=v2 và lấy lease v2.

Không có trạng thái "đã chọn v1 nhưng chưa được tính inFlight, trong khi v1 đã đóng" như cách đọc pointer và tăng refcount ở hai bước không đồng bộ.

### 6.2. Lease pin generation, không gọi current lại

Lease giữ:

~~~java
private final Generation pinned;
~~~

Lệnh xử lý gọi pinned.plugin.handle(input), **không** gọi router.active.plugin.handle(input) một lần nữa. Vì thế request A có thể qua thời điểm cutover mà vẫn dùng v1 trong toàn bộ logic đã được cấp quyền.

Trong ứng dụng thật, một request có thể gọi plugin nhiều lần, chuyển qua callback hoặc xử lý transaction. Nên truyền lease/context có generation ID xuống mọi bước cần plugin; đừng lén resolve lại current giữa quy trình, vì một request có thể sử dụng API/data schema của hai version không tương thích.

### 6.3. Close của lease là idempotent ở mức đếm

Lease dùng AtomicBoolean:

~~~java
if (returned.compareAndSet(false, true)) {
    router.release(pinned);
}
~~~

Đây cũng là đoạn trích. Nếu close được gọi hai lần, chỉ lần đầu giảm inFlight. Điều này tránh underflow và tránh kích hoạt cleanup lặp. AtomicBoolean **không có nghĩa cùng một Lease được phép handle và close đồng thời từ nhiều thread**; người dùng Lease phải quản lý ownership của request và không sử dụng sau khi đóng. Trong code sản xuất, bảo vệ cả cuộc gọi plugin và thời điểm hoàn thành thực tế.

### 6.4. Chọn thread duy nhất có quyền dọn tài nguyên

Router.beginCleanupIfReady chỉ trả Plugin để đóng khi ba điều kiện đúng:

~~~java
g.state == State.DRAINING
    && g.retirementRequested
    && g.inFlight == 0
~~~

Trước khi rời critical section, phương thức đặt **g.state = CLOSING**. Một thread khác gọi retire hoặc release thấy state không còn DRAINING, nên không thể nhận lại cùng quyền cleanup. Cleanup thật (plugin.close) được gọi **bên ngoài gate**.

Điều này giải quyết hai lỗi trái ngược:

- **Đóng quá sớm**: chưa hết lease mà đã close.
- **Đóng trùng**: hai thread đồng thời thấy inFlight=0 và cùng close.

Nếu close ném unchecked exception, finally sẽ đưa state về CLEANUP_FAILED; nó không nói dối rằng resource đã được giải phóng. Bản sản xuất nên ghi lại lỗi và hỗ trợ một quy trình retry/compensation có chủ đích, không mù quáng thử lại một close có side effects không idempotent.

### 6.5. Cleanup nằm ngoài gate

Nếu plugin.close gọi tới thread pool, database hoặc callback về host, thao tác có thể chờ lâu hoặc reenter các component khác. Gọi close trong synchronized(gate) sẽ làm những request mới bị block và dễ tạo vòng chờ khóa.

Trong ví dụ, Router chỉ dùng gate để:

- kiểm tra/đổi trạng thái generation;
- tăng/giảm inFlight;
- quyết định ai có quyền cleanup;
- thay active pointer.

Còn phần **Plugin.handle** và **Plugin.close** diễn ra ngoài gate. Bản production cần thêm cấu trúc quản lý cleanup completion để controller có thể biết quá trình đóng dài đã kết thúc hay thất bại.

## 7. Thực hành có hướng dẫn: làm theo từng mốc

### Mốc A — quan sát v1 trước cutover

Chạy chương trình ban đầu. Giải thích vì sao main cần chờ:

~~~java
oldHasLease.await(10, TimeUnit.SECONDS)
~~~

Nếu main không chờ, nó có thể kích hoạt v2 trước khi worker thực sự nhận lease, khiến request A tình cờ lấy v2. Khi đó test không chứng minh được tình huống "đang có request v1".

**Câu hỏi tự kiểm tra:** Nếu bỏ latch và thay bằng Thread.sleep(100), liệu bài test còn bảo đảm A đã lấy v1 không? **Không.** Scheduler có thể trì hoãn worker lâu hơn 100 ms hoặc main tiến nhanh hơn dự tính. Cần một điều kiện đồng bộ biểu diễn đúng sự kiện.

### Mốc B — bật v2 trong lúc v1 vẫn in-flight

Khi worker đã cấp lease v1, main chạy:

~~~java
router.activate(v2);
router.retire(v1);
~~~

Tại thời điểm này inFlight(v1)=1. Vì thế state phải là DRAINING, closeCalls(v1)=0. Nếu bất kỳ dòng nào cho biết v1 đã CLOSED hoặc closeCalls lớn hơn 0, host đã vi phạm bất biến B3 hoặc bộ đếm không phản ánh đúng công việc thật.

Một thay đổi nhỏ trong phần routing có thể làm hỏng test: đóng v1 trực tiếp trong activate. Bài test được thiết kế để phát hiện lỗi đó khi worker tiếp tục gọi Plugin.handle.

### Mốc C — request mới thấy v2

Sau cutover, main lấy một lease khác:

~~~java
try (Lease lease = router.acquire()) {
    System.out.println("new-request=" + lease.handle("B"));
}
~~~

Kết quả bắt buộc là new-request=v2:B. Nếu ra v1:B, route pointer hoặc nguyên tắc admission chưa được chuyển đúng. Nếu bị block vô hạn, có thể đã giữ khóa trong khi chờ request cũ kết thúc.

### Mốc D — xả tải v1 và kiểm tra đóng đúng một lần

Sau khi request B hoàn thành, main mở latch cho A tiếp tục:

~~~java
finishOld.countDown();
String result = oldRequest.get(10, TimeUnit.SECONDS);
~~~

Future.get đợi worker hoàn tất callable, bao gồm cả khi try-with-resources đã gọi Lease.close. Do đó lúc main đọc state, nếu cleanup không lỗi, v1 phải CLOSED và closeCalls(v1)=1.

Nhớ rằng Future.get chỉ xác nhận đúng phạm vi công việc mà callable đại diện. Nếu thực tế plugin tạo task fire-and-forget sau khi trả về, future kết thúc **không chứng minh** những task đó đã hết sử dụng version; phải đưa chúng vào lifecycle/lease của hệ thật.

### Mốc E — retire lặp và shutdown

Main cố ý gọi retire(v1) lần hai. Đây là một **bài test về idempotency của lifecycle controller**, không phải một lý do để production tự retry vô hạn. State CLOSED được bỏ qua, closeCalls vẫn bằng 1.

Sau đó router.shutdown: active pointer trở thành null, generation v2 ngừng nhận mới, rồi được retire. Vì không còn lease v2, cleanup v2 có thể hoàn thành ngay. Dòng new-close-count=1 chứng minh demo không để rò rỉ tài nguyên của phiên bản đang ACTIVE khi host kết thúc.

**Một phép thử bổ sung:** Sau shutdown, gọi router.acquire trong đoạn try/catch; nó phải ném IllegalStateException("No active plugin"). Không cho phép một request mới nhận generation đã đóng.

## 8. Bài tập biến thể để kiểm tra lỗi thật

Mỗi bài tập dưới đây nên chạy trên **bản sao tạm riêng của PluginSwapLab.java**, không sửa trực tiếp bài đã kiểm chứng nếu chưa lưu bản gốc. Các biến thể có chủ đích làm sai bất biến hoặc thay chính sách nên stdout/exception sẽ khác, vì vậy **không gán output chuẩn của phần 5** cho chúng.

### Bài tập 1 — cố ý đóng v1 quá sớm

Thử gọi v1.plugin.close() ngay sau activate(v2), trước khi finishOld.countDown(). TrackedResource.closeCalls tăng lên 1 khi request A vẫn chưa xong. Khi A tiếp tục handle, checkOpen ném IllegalStateException("Resource was already closed").

**Bài học:** Một pointer atomic tự nó không bảo đảm an toàn của resource cũ. Không được sửa lỗi bằng cách bỏ checkOpen; phải hoãn cleanup cho tới khi inFlight thực sự bằng 0.

### Bài tập 2 — không trả lease

Trong một bản thử nghiệm, bỏ try-with-resources ở worker và cố tình không gọi lease.close. Router đã cấp lease v1 nhưng counter không về 0; v1 ở DRAINING dù request business đã trả kết quả. Đây là một **lease leak**, có thể giữ JAR/thread pool lâu dài.

**Bài học:** Mỗi request path cần finally/try-with-resources hoặc completion callback chắc chắn. Một request không được tự ý “quên” trả lease khi gặp exception.

### Bài tập 3 — close hai lần

Đặt một lời gọi lease.close() bổ sung trước khi khối try-with-resources kết thúc. AtomicBoolean.compareAndSet khiến release chỉ thực hiện một lần. Kiểm tra inFlight không âm và closeCalls vẫn bằng 1.

**Bài học:** Close idempotent là một biện pháp phòng thủ ở biên API, nhưng không thay thế việc sở hữu lease đúng trong luồng xử lý.

### Bài tập 4 — shutdown trong lúc v2 vẫn có yêu cầu

Tạo một lease v2 sau cutover, giữ nó mở, gọi router.shutdown từ main. Vì v2 có inFlight lớn hơn 0, v2 phải chuyển DRAINING và **chưa** close. Sau khi đóng lease v2, v2 chuyển CLOSED và closeCalls=1.

**Bài học:** Cùng giao thức drain áp dụng cho **thay phiên bản** và **tắt host**; không cho shutdown phá tài nguyên đang dùng.

### Bài tập 5 — kiểm tra lỗi cleanup

Sửa TrackedResource.close để ném một RuntimeException có chủ đích, chạy trên bản sao dùng để thử lỗi. Router.performCleanup phải đưa state về CLEANUP_FAILED thông qua finally. Lúc này không thể tự tuyên bố resource đã được giải phóng; log lỗi và đưa vào chính sách operator review.

**Bài học:** Exactly-once attempt không đồng nghĩa exactly-once effect. Một close có thể đã giải phóng một phần resource rồi ném exception; retry không kiểm soát có thể hại thêm.

### Bài tập 6 — stress concurrent admission

Tạo nhiều worker bằng Executors.newFixedThreadPool, đồng bộ điểm bắt đầu bằng CountDownLatch, đồng thời gọi acquire và activate. Kiểm tra mỗi Lease chỉ gắn với một generation, không bao giờ xử lý trên CLOSED, counter cuối bằng 0 và không có duplicate close.

Tránh dùng một assert kiểu “chính xác 50% request vào v1” cho race kiểm thử; tỉ lệ được xác định bởi scheduler. Bất biến cần đo là **mỗi request được nhận hợp lệ trước hoặc sau điểm cutover** theo giao thức monitor.

### Bài tập 7 — tạo rollback window

Ở phần thực hành cơ bản, main gọi retire(v1) ngay sau switch nên sau khi drain xong v1 sẽ CLOSED. Không thể rollback nhanh vào v1 đã đóng.

Để hỗ trợ rollback, sửa controller theo hướng giữ v1 ở **STANDBY** khi inFlight=0 nhưng chưa có retirementRequested, đồng thời cho phép reactivate từ STANDBY sau khi kiểm tra data compatibility. Chỉ retire/close khi qua thời hạn rollback. Đây là **bài mở rộng**, không phải điều mà chương trình hiện tại đã làm. Trước khi bật rollback trong hệ thật phải kiểm tra schema dữ liệu, side effects và phiên bản API; đổi route không hoàn tác giao dịch đã xảy ra.

## 9. Từ tài nguyên giả sang tài nguyên thật của plugin

TrackedResource chỉ quan sát lời gọi close. Trong host Java thực tế, một generation có thể sở hữu:

- **URLClassLoader** mở các plugin JARs và resources.
- **Plugin instance** có stop/close hook.
- **ExecutorService** cho các tác vụ bất đồng bộ của plugin.
- **ScheduledExecutorService** cho timer hoặc polling.
- **Connection pool**, HTTP client, file handle, stream hoặc native resources.
- **Event listeners**, callback registrations, MBeans và ThreadLocal.
- **Cache** gắn với lớp/instance của plugin, các ServiceLoader hoặc ModuleLayer references.
- **Các request/stream** đang giữ object do class loader của generation ấy định nghĩa.

Ngừng nhận request mới là điều kiện cần nhưng chưa đủ. Trước khi close loader, cần chắc chắn code của generation không còn cần nạp class/resource từ đó, các background tasks đã được dừng, listeners bị hủy và mọi lease đã release.

### 9.1. Đóng class loader không có nghĩa unload class tức thì

URLClassLoader.close() đóng những tài nguyên như file/JAR do loader quản lý và hạn chế các lệnh tìm class/resource sau đó. Nó **không xóa Class object đã được định nghĩa**, không dừng thread đang chạy bytecode cũ và không ngay lập tức giải phóng metaspace nếu vẫn còn strong references.

Do đó ba assertion phải được phân biệt:

1. **Cleanup invoked:** host đã gọi close của đúng generation sau inFlight=0, đúng một lần.
2. **Resources released:** những file handle, thread pool, socket hoặc pool mà plugin quản lý đã được đóng/terminated theo hợp đồng. Cần đo từng loại thực tế.
3. **Class unloading eligible/observed:** những class/loader của generation không còn được tham chiếu; JVM **có thể** garbage collect và unload chúng. Thời điểm GC không xác định; không viết test cứng rằng WeakReference phải bị xóa trong một số mili-giây.

Trong test thật, có thể dùng JFR/class unloading diagnostics, WeakReference đến loader cùng một khoảng quan sát đủ dài, và kiểm tra số file handle/thread/metaspace sau nhiều lần reload. WeakReference là tín hiệu hữu ích nhưng **không phải tiêu chí pass xác định** khi gọi System.gc một lần.

### 9.2. Khung kết hợp AutoCloseable

Một plugin manager có thể gom nhiều tài nguyên vào một đối tượng sở hữu duy nhất. Ví dụ cấu trúc (không phải class độc lập vì phụ thuộc các thành phần host) :

~~~java
// MINH HỌA API CHO THỰC TẾ; cần các lớp/plugin cụ thể do host cung cấp.
final class PluginResources implements AutoCloseable {
    private final AutoCloseable pluginInstance;
    private final java.net.URLClassLoader loader;
    private final java.util.concurrent.ExecutorService executor;
    private final java.util.concurrent.atomic.AtomicBoolean closed =
            new java.util.concurrent.atomic.AtomicBoolean();

    PluginResources(
            AutoCloseable pluginInstance,
            java.net.URLClassLoader loader,
            java.util.concurrent.ExecutorService executor) {
        this.pluginInstance = pluginInstance;
        this.loader = loader;
        this.executor = executor;
    }

    @Override
    public void close() throws Exception {
        if (!closed.compareAndSet(false, true)) return;

        Exception failure = null;
        try {
            pluginInstance.close();
        } catch (Exception e) {
            failure = e;
        }

        executor.shutdown();
        // Production: awaitTermination theo deadline; có chính sách escalation.
        try {
            loader.close();
        } catch (Exception e) {
            if (failure == null) failure = e;
            else failure.addSuppressed(e);
        }

        if (failure != null) throw failure;
    }
}
~~~

Đây là **khung có thể biên dịch khi đặt trong file riêng** và đã đủ import nhờ dùng các tên đầy đủ, nhưng nó **chưa đủ an toàn để triển khai trực tiếp**: cần chờ executor thực sự kết thúc, chống task còn tiếp tục dùng loader sau khi close, xử lý sự cố từng bước và quản lý cleanup status/attempts. Thứ tự dừng callback/timer/task/loader phải theo hợp đồng plugin cụ thể; không coi executor.shutdown là đảm bảo worker đã ngừng.

### 9.3. Trường hợp Java module layer

Một plugin có thể được triển khai qua ModuleLayer thay vì URLClassLoader. Khi đó khái niệm generation, lease, drain và rollback **vẫn cần**, nhưng cleanup tùy cách class loader/ModuleLayer/resource được tạo. Không có API chung kiểu ModuleLayer.close() giúp dừng mọi class và resource. Host cần đóng những đối tượng có hợp đồng cleanup, loại strong references đến layer/loader và theo dõi task/callback.

Đừng tạo một ModuleLayer mới mỗi lần deploy rồi giữ tất cả layer trong static registry. Không còn request không đồng nghĩa layer tự biến mất nếu registry hoặc thread context class loader vẫn giữ tham chiếu.

## 10. Yêu cầu bất đồng bộ: lease sống đến completion thật

Bài demo worker dùng Future và try-with-resources: Future.get chỉ trả sau khi callable kết thúc và lease đã được đóng. Khi plugin trả CompletableFuture hoặc CompletionStage, cần **chuyển lease tới callback kết thúc**.

Sai:

~~~java
// MINH HỌA RỦI RO; giả định plugin.handleAsync trả CompletionStage<Result>.
try (PluginLease lease = router.acquire()) {
    return lease.plugin().handleAsync(input);
}
// Lease.close chạy ngay sau khi return stage, khi tác vụ còn sử dụng plugin.
~~~

Cách tổ chức đúng hơn:

~~~java
// MÃ MINH HỌA: PluginLease, router, input và Result do host định nghĩa.
PluginLease lease = router.acquire();
try {
    return lease.plugin().handleAsync(input)
            .whenComplete((result, error) -> lease.close());
} catch (RuntimeException | Error error) {
    lease.close();
    throw error;
}
~~~

Điều kiện là stage hoàn tất thực sự đại diện cho **mọi công việc** của plugin. Nếu method tạo thêm một thread fire-and-forget rồi trả stage đã completed, lease vẫn bị release quá sớm. Đối với worker không hợp tác/nguồn script chưa tin cậy, việc bắt buộc timeout ở cùng JVM thường không thể dừng execution an toàn; cần kiến trúc worker process.

Cần thiết kế Lease.close là idempotent và thread-safe ở mức lifecycle khi callback đến từ thread khác, còn use-versus-close race phải được xử lý bằng ownership rõ ràng. Không ép đóng loader khi còn stage đang hoạt động chỉ vì API timeout phía caller đã hết.

### Những loại tác vụ nên tính vào in-flight

| Loại | Ranh giới release thích hợp |
| --- | --- |
| HTTP request đồng bộ | Kết thúc toàn bộ xử lý và response/cleanup mà plugin cần |
| CompletableFuture | Khi computation hoàn tất thực, including error/cancel |
| Message listener | Sau xử lý cùng ack/nack/transaction, theo delivery semantics |
| Stream lâu dài | Khi stream kết thúc hoặc đã handoff an toàn |
| Scheduled task | Khi callback thực sự kết thúc và registration đã hủy |
| Database transaction | Sau commit/rollback hoàn tất và không còn dùng resource |
| External callback | Khi ngừng callback, đã deregister hoặc chuyển ownership an toàn |

Thời điểm release được thiết kế theo hợp đồng workload chứ không phải một event ngẫu nhiên như "trả Java object Future".

## 11. Tài nguyên bị rò rỉ qua các tham chiếu vô hình

Ngay cả sau khi close và inFlight=0, một loader cũ có thể vẫn chưa được thu gom vì:

- Thread không thuộc router còn chạy code plugin và giữ context class loader.
- ThreadLocal của thread pool host giữ instance hoặc Class từ loader cũ.
- Event bus/registry/scheduler chưa gỡ listener/callback của plugin.
- Singleton static trong host giữ Class, Method, service provider hoặc object plugin.
- ServiceLoader, logging/metrics, reflection caches hoặc proxy giữ tham chiếu liên quan.
- Một Future, Throwable, completion callback hoặc request context giữ object của v1.
- JMX/MBean hoặc framework integration chưa unregister.

Checklist dọn v1 phải kiểm tra cả **resource cleanup** lẫn **reference cleanup**, chứ không chỉ gọi close. Khi hệ thống có nhiều lần reload, theo dõi xu hướng class loaders/metaspace/threads/handles sau khi các generation cũ hết lease và rollback window.

**Lưu ý về memory test:** Sự kiện GC và class unloading do JVM quyết định. Một smoke test không chứng minh được "không rò rỉ" chỉ vì số liệu ổn sau một vòng reload; cần stress cycles, diagnostics và một khoảng quan sát hợp lý. Đừng đặt logic sản xuất dựa vào System.gc() như một cách thu hồi plugin.

## 12. Khi nào không nên đóng tài nguyên ngay cả khi inFlight=0?

Một số hệ có thời gian **rollback** hoặc các handle lưu lâu dài mà counter request chưa bao phủ. Trong các trường hợp đó, một quyết định dọn phải thêm các điều kiện:

- Generation đã bị loại khỏi routing table và không thể cấp lease mới.
- Không có request hoặc background job nào còn sử dụng generation.
- Đã hết thời hạn giữ để rollback hoặc có quyết định retire chính thức.
- Không còn session/callback/external consumer chưa được tính lease.
- Dữ liệu và API đã xác nhận không cần generation cũ để tiếp tục.
- Những resource thuộc shared scope không bị một generation đơn lẻ đóng nhầm.

Trong ví dụ này, main **chủ động gọi retire(v1)** ngay sau switch: nếu inFlight về 0 thì v1 được đóng, không có rollback window. Đó là lựa chọn của bài thực hành, **không phải quy tắc duy nhất cho mọi sản phẩm**.

Nếu muốn rollback nhanh về v1, nên giữ v1 ở trạng thái STANDBY (không nhận request mới nhưng còn resource hợp lệ) cho tới khi cần khôi phục hoặc hết thời hạn cho phép. Lúc đó controller phải có cơ chế rõ ràng để tái kích hoạt STANDBY sau readiness/data compatibility guard; không cố gọi activate trên một Generation đã CLOSED.

## 13. Checklist kiểm tra dọn tài nguyên khi thay phiên bản thật

| Thời điểm | Kiểm tra bắt buộc | Dấu hiệu lỗi |
| --- | --- | --- |
| Trước switch | v2 đã chuẩn bị, startup/health của v2 ổn; v1 còn ACTIVE | Bật v2 trước khi dependency sẵn sàng |
| Request v1 đã vào | Có lease v1, inFlight(v1) tăng | Request không được đếm nhưng vẫn dùng plugin |
| Sau switch | New route vào v2; v1 DRAINING | Request mới vẫn vào v1 hoặc v1 đóng sớm |
| Trong lúc A đang xử lý | closeCalls(v1)=0, resources v1 còn hợp lệ | File/loader/pool bị đóng khi vẫn còn in-flight |
| Sau A completion | inFlight(v1)=0; cleanup đúng một lần | Counter âm, double close hoặc lease leak |
| Sau cleanup | old resources thực sự close/terminate | Sockets/threads/JAR handles còn mở |
| Sau retire lặp | Không xuất hiện cleanup thứ hai | Resource.close bị gọi lại ngoài ý muốn |
| Sau host shutdown | v2 không nhận mới và được dọn sau drain | Thread pool còn sống hoặc v2 chưa close |
| Sau nhiều lần reload | Không có retained listeners/ThreadLocal/loader vô hạn | Số loader, thread, metaspace tăng theo số lần deploy |

Với sản phẩm thực, mỗi lần kiểm tra cần **generation ID**, không chỉ version label. Cùng version v2 có thể được nạp nhiều lần với class loader, artifact/config và resource handle khác nhau. Dọn nhầm generation có thể phá hủy request của một phiên hợp lệ khác.

## 14. Kiểm thử lỗi và quan sát

### 14.1. Những test nên viết trong CI

1. **In-flight swap**: một worker đã giữ v1, main bật v2, v1 không close trước release.
2. **Post-cutover admission**: request mới dùng v2; không tham chiếu v1 thông qua active pointer.
3. **Concurrent acquire/cutover race**: hai trường hợp thứ tự đều hợp lệ, không dùng resource đã đóng.
4. **Release exception path**: business handler ném exception, lease vẫn được release trong finally/try-with-resources.
5. **Double close lease**: inFlight không âm, cleanup không lặp.
6. **Retire while in-flight**: state vẫn DRAINING, closeCalls=0.
7. **Retire after in-flight=0**: cleanup kích hoạt đúng một lần.
8. **Cleanup failure**: state CLEANUP_FAILED, metric/error và quy trình thu hồi phù hợp.
9. **Shutdown with in-flight**: không cấp lease mới; chờ các task cũ kết thúc theo deadline.
10. **Async future**: lease không được release trước completion stage thực.
11. **Actual URLClassLoader/resource cleanup**: JAR handles/threads/listeners được đóng theo lifecycle.
12. **Repeated deployments**: nhiều chu kỳ v1→v2→v3 không làm tăng references vô thời hạn.

### 14.2. Chẩn đoán khi bài thực hành không đạt

| Triệu chứng | Vùng nên kiểm tra |
| --- | --- |
| old-request in ra v2:A | Lease không pin version hoặc worker chỉ acquire sau cutover |
| old-close-before-finish lớn hơn 0 | Cleanup quá sớm, thiếu inFlight guard |
| old-after-drain vẫn DRAINING | Lease chưa được release hoặc retirementRequested chưa set |
| old-close-count bằng 2 | Không đánh dấu CLOSING trong khóa hoặc lifecycle retry sai |
| new-request không phải v2:B | active pointer chưa chuyển/đọc ngoài gate |
| Timeout tại Future.get | Worker chưa được mở latch, bị deadlock hoặc tác vụ treo |
| new-close-count bằng 0 sau shutdown | Không retire active generation hoặc còn lease |
| CLOSE gọi rồi nhưng tài nguyên thật vẫn bận | stop hook không đóng đủ; thread/callback giữ resource |
| Class loader chưa bị GC sau close | Còn strong references hoặc GC chưa xảy ra |
| Không thể rollback về v1 | v1 đã CLOSED/thiếu rollback window, hoặc schema không tương thích |

Nếu timeout, thu **thread dump** khi tiến trình đang kẹt bằng jcmd/jstack theo môi trường và quyền cho phép. Tìm thread đang giữ gate, thread đang chờ latch, thread thực hiện close có I/O hay callback vào router, và những lock của plugin. Không giải quyết một deadlock bằng cách tăng sleep hoặc gọi Thread.stop.

### 14.3. Metrics phù hợp trong production

- active_generation{plugin,tenant,instance}, rollout epoch.
- in_flight{plugin,generation}, oldest_in_flight_age và drain_duration.
- requests_started/finished/failed{generation}.
- cleanup_attempts, cleanup_success, cleanup_failures, cleanup_duration{generation}.
- resources_open{type,generation}, plugin_threads_active, callback_registrations.
- loader_retirement_pending, classloader_retained_after_window (quan sát theo chu kỳ).
- version_switch_count, rollback_count và lý do.

Không xuất raw request payload, secrets hay classpath nội bộ tùy tiện trong metrics/log. Đảm bảo metric cardinality có giới hạn nếu generation IDs rất nhiều, tránh hệ metrics trở thành nguồn DoS.

## 15. Bài tập nâng cao và tiêu chí hoàn thành

Một bài thực hành hoàn chỉnh nên trải qua ba mức:

### Mức 1 — chạy đúng kịch bản đã cho

**Bắt buộc:** Biên dịch và chạy PluginSwapLab.java; nhận stdout đã chỉ ra, xác nhận resource v1 không close trước khi request A hoàn thành, v1/v2 mỗi version close một lần. Giải thích bằng lời tại sao CountDownLatch làm kết quả đáng tin hơn Thread.sleep.

### Mức 2 — có kiểm thử tình huống thất bại

**Bắt buộc đối với người triển khai plugin thật:** Tạo biến thể close sớm, thiếu release, double-close, shutdown khi in-flight và cleanup exception. Test phải phát hiện sai đúng bằng trạng thái, counter hoặc exception; không chỉ quan sát chương trình có chạy xong hay không. Không tạo deadlock thật trên test runner dùng chung mà không có timeout/isolated process.

### Mức 3 — gắn tài nguyên thật và kiểm tra vòng đời

Mở rộng Generation để sở hữu URLClassLoader, một executor và một registration trên event bus giả lập. Kết quả được coi là đạt khi:

- v1 còn lease thì các resource v1 chưa bị đóng;
- khi hết lease/rollback window, executor đã terminated, listener bị unregister và loader.close trả về thành công;
- mỗi resource đóng một lần hoặc theo hợp đồng idempotent đã ghi rõ;
- host không còn giữ tham chiếu không cần thiết đến v1 sau retire;
- khi chạy nhiều chu kỳ switch, không còn các thread/callback rác, JAR handles được giải phóng và xu hướng memory không tăng mất kiểm soát.

**Định nghĩa pass/fail phải dựa trên từng resource thực**, không coi System.gc hoặc WeakReference cleared là chứng cứ bắt buộc trong một thời hạn tuyệt đối.

## 16. Checklist tổng kết

- [ ] Có ít nhất hai generation riêng cho hai lần nạp/phiên bản plugin.
- [ ] Request đang chạy giữ lease gắn với generation đã chọn.
- [ ] Acquire và activate phối hợp nguyên tử khi đọc route/tăng inFlight.
- [ ] Generation cũ ngừng nhận mới trước khi retire.
- [ ] Trong khi inFlight > 0, tài nguyên cũ chưa bị đóng.
- [ ] Sau inFlight về 0 và retire requested, close được gọi đúng một lần.
- [ ] Cleanup chạy ngoài khóa routing và có trạng thái lỗi rõ ràng.
- [ ] Async callbacks, timers, background tasks được tính vào lifecycle.
- [ ] Shutdown ngừng admission, drain request và dọn active generation.
- [ ] Với class loader thật, không nhầm close với unload/GC ngay lập tức.
- [ ] Nếu hỗ trợ rollback, giữ generation cũ có chủ đích và kiểm tra tương thích dữ liệu.
- [ ] Có CI tests cho race, exception, timeout, repeated replacement và resource leaks.

**Kết luận:** Thay plugin an toàn cần **pin request bằng lease, chuyển routing atomically, chờ in-flight drain và chỉ dọn đúng generation ở đúng thời điểm**. Chương trình Java 17 đã kiểm chứng trong bài cho thấy hai việc tưởng xung đột có thể cùng đúng: request A tiếp tục dùng v1 sau switch, trong khi request B nhận v2; v1 chỉ được close sau khi A trả lease, còn v2 được dọn khi shutdown. Đây là nền tảng để nâng cấp sang URLClassLoader/ModuleLayer và hệ runtime extensibility có nhiều plugin, nhưng việc kiểm tra resource thật, state compatibility và rollback policy vẫn phải thiết kế riêng.

## Tham khảo chính thức

- Java SE 17 — [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối thứ tự giữa các thread mà không dựa vào sleep.
- Java SE 17 — [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý worker và shutdown.
- Java SE 17 — [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): đợi completion và xử lý timeout.
- Java SE 17 — [AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): try-with-resources.
- Java SE 17 — [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): close() và giới hạn của class loading/unloading.
- Java SE 17 — [AtomicBoolean](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): bảo vệ việc release lease một lần.
- Java SE 17 — [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion callbacks cho các tác vụ bất đồng bộ.