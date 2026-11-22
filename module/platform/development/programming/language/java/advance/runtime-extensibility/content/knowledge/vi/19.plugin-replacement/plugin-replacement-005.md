# Xử lý yêu cầu đang chạy, chuyển trạng thái và quay lại phiên bản trước khi thay thế plugin

Thay một plugin trong ứng dụng Java đang phục vụ lưu lượng **không đơn giản là gỡ JAR cũ và nạp JAR mới**. Thời điểm chuyển phiên bản, một số request có thể đã lấy tham chiếu đến plugin cũ, một số request còn đang xếp hàng, một số tác vụ chạy bất đồng bộ hoặc giữ kết nối lâu dài. Phiên bản mới có thể vượt qua kiểm thử khởi động nhưng lỗi khi nhận lưu lượng thật; khi đó host cần **rollback**, tức đưa các request mới quay về phiên bản trước **mà không làm hỏng những request và dữ liệu đã đi qua phiên bản mới**.

Đối với mô-đun runtime extensibility, phải giải quyết đồng thời ba câu hỏi:

1. **Yêu cầu đang chạy xử lý thế nào?** Để nó hoàn tất trên thế hệ plugin mà nó đã chọn, hoặc hủy có kiểm soát theo chính sách, thay vì đóng class loader hoặc phá tài nguyên đang được dùng.
2. **Chuyển trạng thái thế nào?** Chuẩn bị, thử nghiệm, kích hoạt, ngừng nhận mới, chờ xả tải và thu hồi phiên bản cũ bằng các trạng thái và ranh giới đồng bộ hóa rõ ràng.
3. **Quay lại phiên bản trước thế nào?** Giữ một thế hệ plugin cũ còn khả dụng trong một khoảng rollback window, chuyển tuyến một cách nguyên tử và kiểm tra tương thích trạng thái, dữ liệu, API và side effects.

Bài học trình bày mô hình **generation + request lease + atomic cutover + graceful drain + controlled rollback**, minh họa bằng chương trình Java 17 độc lập, sau đó mở rộng sang hệ thống thật có HTTP, hàng đợi, long-running jobs, database và các plugin class loaders.

## 1. Vì sao thay nóng plugin dễ làm mất request?

Giả sử host cung cấp service **Formatter**. Thế hệ đang chạy là v1, chuẩn bị thay bằng v2. Tại một thời điểm có thể tồn tại những yêu cầu như sau:

~~~text
                        +--------------------+
Yêu cầu đã vào v1 ------>| Plugin v1 đang chạy |----->
                        +--------------------+
                                 ^
                                 | giữ tham chiếu/lease
                                 |
            thời điểm cutover -----|--------------------
                                 |
Yêu cầu mới --------->+--------------------+
                      | Plugin v2 đang chạy |----->
                      +--------------------+
~~~

Nếu host chỉ thay một biến currentPlugin bằng v2 rồi lập tức gọi stop/close trên v1, một request đã bắt đầu với v1 có thể truy cập một file, pool, service hoặc module đã bị dỡ. Lỗi xuất hiện giữa chừng dù thao tác chuyển biến currentPlugin nhìn bề ngoài đã thành công.

Ngược lại, nếu host khóa toàn bộ ứng dụng trong lúc đợi mọi request hoàn thành rồi mới thay plugin, request dài hoặc luồng streaming có thể làm triển khai bị treo, gây ngừng dịch vụ kéo dài. Hệ thống cần **chặn nhận mới ở phiên bản cũ nhưng cho tác vụ đã nhận quyền sử dụng tiếp tục**, có deadline và cơ chế xử lý task không chịu hoàn tất.

Điểm phân biệt cốt lõi là:

- **Request admission**: tại thời điểm tiếp nhận, chọn đúng generation đang ACTIVE.
- **Request execution**: thực thi trên generation đã chọn, ngay cả khi biến current sau đó chuyển sang generation khác.
- **Completion/release**: trả lại lease khi toàn bộ xử lý thật sự kết thúc, để generation cũ chỉ được dọn khi không còn người dùng.

Chỉ đổi pointer mà không quản lý request đang chạy, trạng thái và dữ liệu thường là **hot switch thiếu an toàn**, không phải hot replacement hoàn chỉnh.

## 2. Những đối tượng cần có trong thiết kế

Một host có thể dùng các khái niệm sau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Plugin generation** | Một lần nạp cụ thể của plugin, có ID/version, instance, class loader, cấu hình, tài nguyên và trạng thái | formatter-v2 / generation-42 |
| **Routing pointer** | Chọn generation nhận request **mới** | activeGeneration |
| **Lease / in-flight counter** | Ghi nhận có request đang dùng generation nào; chỉ release khi thực sự hoàn thành | v1.inFlight = 3 |
| **Lifecycle controller** | Quy định trạng thái, guard, timeout và quyết định activate/rollback/retire | PREPARED → ACTIVE → DRAINING |
| **Readiness/health gate** | Xác minh plugin sẵn sàng nhận tải, phụ thuộc đủ và đáp ứng tiêu chí vận hành | health checks, error rate |
| **Rollback candidate** | Generation cũ vẫn tồn tại và còn tương thích để kích hoạt lại khi cần | v1 giữ ở STANDBY |
| **State/data compatibility plan** | Bảo đảm kết quả do v2 viết không làm v1 không đọc được khi quay lại | expand–contract migration, versioned events |

Một **generation** không đồng nghĩa một phiên bản semantic version duy nhất. Cùng v2 có thể được nạp lại thành nhiều generation với class loader khác nhau, tài nguyên khác nhau hoặc cấu hình khác nhau. Điều cần quản lý là **danh tính thế hệ đang được các request giữ**, không chỉ chuỗi "2.0".

### In-flight là gì?

Một request được tính là in-flight từ lúc **host cấp lease** để bắt đầu dùng generation, cho tới lúc tất cả hoạt động của request đã hoàn tất và lease được giải phóng. Tùy ứng dụng, đó có thể là:

- HTTP request đồng bộ: từ khi route chọn plugin tới khi trả response và cleanup hoàn tất.
- CompletableFuture: cho tới khi future hoàn thành hoặc kết thúc bằng lỗi/hủy theo chính sách.
- Message consumer: cho tới khi xử lý và commit/ack hoặc đưa vào retry/DLQ theo quy tắc.
- Streaming/gRPC/WebSocket: có thể kéo dài toàn bộ session nếu session giữ tài nguyên/logic plugin.
- Scheduled job hoặc workflow dài: nhiều phút hoặc hàng giờ, có thể phải checkpoint và tiếp tục ở thế hệ khác theo giao thức được thiết kế riêng.

**Không** release lease ngay sau khi gọi một phương thức trả Future nếu callback bất đồng bộ vẫn còn truy cập plugin. Tương tự, không chỉ đo số kết nối HTTP nếu một kết nối có thể gửi nhiều request; phải đếm đúng công việc đang dùng generation.

## 3. Máy trạng thái thay thế plugin

Một mô hình đơn giản có thể dùng:

~~~text
         tải JAR + cấu hình + dependency
                     |
                     v
                 PREPARED
                     |
           readiness / smoke tests
                     |
                     v
                 ACTIVATING
                     |
               atomic cutover
                     |
                     v
                   ACTIVE
                     |
          có generation khác thay thế
                     |
                     v
                  DRAINING
                     |
             inFlight về 0
                     |
                     v
                  STANDBY
                  /     \
       rollback     /       \ hết rollback window
                  v           v
                ACTIVE       CLOSED
                              |
                       đóng tài nguyên,
                      bỏ strong references
~~~

Đây là **mô hình thiết kế tham khảo**. Không có enum trạng thái nào được JDK mặc định quản lý sẵn cho plugin của ứng dụng; host phải hiện thực, lưu audit và kiểm tra chuyển trạng thái.

Ý nghĩa từng trạng thái:

- **PREPARED**: artifact đã được tìm, kiểm tra chữ ký/nguồn tin cậy, cấu hình, API compatibility và nạp trong scope riêng; **chưa** nhận request sản xuất.
- **ACTIVATING**: đang thực hiện các guard cần thiết và chuẩn bị xuất bản route; không mở public admission vào generation trước khi sẵn sàng.
- **ACTIVE**: là thế hệ hợp lệ để nhận **request mới**; mọi request lấy lease ở đây.
- **DRAINING**: không nhận request mới, nhưng request đã nhận trước đó tiếp tục sử dụng instance và tài nguyên cũ.
- **STANDBY**: không còn request đang chạy, tài nguyên cần cho rollback vẫn được giữ lại; generation có thể được kích hoạt lại nếu tương thích.
- **CLOSED**: không nhận request mới, không còn lease, tài nguyên được đóng theo hợp đồng và generation không được kích hoạt lại theo đường rollback nhanh.

Trong ví dụ Java chạy được ở phần 6, **ACTIVATING** được gộp vào thao tác activate giữ khóa ngắn để đơn giản hóa. Trong ứng dụng thật có health checks và distributed coordination, quá trình chuẩn bị và xác minh thường kéo dài ngoài critical section; chỉ đoạn **xuất bản pointer/routing rule** cần nguyên tử.

### Bất biến phải luôn đúng

1. **Một generation CLOSED không bao giờ được cấp lease mới.**
2. **Tại một route/tenant và một thời điểm, chỉ generation được chính sách admission cho phép mới nhận request mới.** Với canary có thể là nhiều generation ACTIVE theo trọng số; phải quy định rõ.
3. **Mỗi lease gắn bất biến với một generation**, không đổi nửa chừng khi pointer cutover.
4. **Không đóng generation có inFlight lớn hơn 0**, trừ tình huống khẩn cấp với chính sách hủy/ép dừng đã được xác định.
5. **Không rollback vào generation đã CLOSED hoặc không tương thích với state hiện tại.**
6. **Thay route và nhận lease phải phối hợp đồng bộ**, không có cửa sổ race khiến request mới được nhận vào generation đã ngừng admission.
7. **Rollback không xóa được side effects** đã tạo ra bởi phiên bản bị lỗi; phải đánh giá dữ liệu và giao dịch riêng.

Nếu không bảo vệ những bất biến này, hệ thống có thể có memory/resource leak, lỗi dùng plugin đã đóng, mất request hoặc rollback tạo dữ liệu không đọc được.

## 4. Bốn giai đoạn của một lần thay thế có kiểm soát

### Giai đoạn A — Prepare, chưa động vào lưu lượng thật

- Tải version mới vào **generation mới**, không thay trực tiếp class/instance ở generation cũ.
- Kiểm tra artifact provenance, phiên bản API, dependency graph, cấu hình và các capability được phép dùng.
- Khởi tạo instance và tài nguyên cần thiết; nếu plugin có start(), chạy theo hợp đồng startup đã thiết kế.
- Thực hiện readiness/smoke tests trên dữ liệu kiểm thử có kiểm soát. Có thể thử synthetic traffic hoặc shadow requests, nhưng **shadow không được ghi side effects thật** nếu có nguy cơ lặp giao dịch.
- Kiểm tra plugin có thể đọc schema dữ liệu hiện tại, tạo event phù hợp với consumer cũ/mới, và không yêu cầu migration phá hủy đường rollback.
- Đặt generation mới ở PREPARED/READY và ghi nhận generation ID, config hash, artifact checksum, health baseline.

Nếu chuẩn bị thất bại, **không chuyển tuyến**: đóng tài nguyên của generation mới đã khởi tạo một phần, giữ v1 ACTIVE và báo lỗi triển khai. Đây là cách rollback đơn giản nhất: **chưa commit cutover**.

### Giai đoạn B — Activate/cutover

Trong một ranh giới đồng bộ hóa ngắn:

1. Đảm bảo candidate đã sẵn sàng và chưa bị đóng.
2. Đọc generation đang ACTIVE.
3. Đánh dấu thế hệ cũ không còn nhận yêu cầu mới.
4. Xuất bản route/pointer sang thế hệ mới.
5. Đánh dấu thế hệ mới ACTIVE và ghi nhận cutover ID/thời điểm.

Bước chọn generation và tăng inFlight của một request **phải dùng cùng giao thức đồng bộ hóa** với bước cutover. Ví dụ dùng synchronized trên một monitor chung hoặc một cơ chế CAS+refcount được thiết kế chính xác. **AtomicReference.set(newGeneration) đơn độc không đủ** nếu request đọc pointer trước cutover rồi tăng refcount sau khi hệ thống đã đóng v1; phải có bước xác thực/đảm bảo admission sau khi tăng lease.

Kết quả cần đạt là **yêu cầu đã nhận lease v1 vẫn chạy ở v1**, còn **yêu cầu mới sau cutover nhận lease v2**. Hệ thống không buộc những request cũ đổi business logic ở giữa giao dịch.

### Giai đoạn C — Drain thế hệ cũ

v1 chuyển sang DRAINING, nhưng chưa đóng class loader, thread pool, connection pool hoặc state mà request của v1 đang dùng. In-flight counter giảm khi từng request kết thúc. Khi về 0, v1 có thể vào STANDBY trong thời hạn rollback.

Trong lúc drain cần theo dõi:

- v1.inFlight, v2.inFlight theo generation, route và tenant.
- Thời gian request cũ còn tồn tại, loại request và độ trễ của generation cũ.
- Các future/callback/timer/consumer hoặc stream còn giữ tham chiếu đến v1.
- Deadline tổng của rollout và cơ chế escalation cho request bị treo.

Nếu drain quá lâu, các lựa chọn phụ thuộc hợp đồng:

- **Chờ thêm có deadline** khi request hợp lệ và hệ thống có đủ tài nguyên.
- **Ngừng admission vào workload dài hoặc chuyển session mới** theo chính sách draining rõ.
- **Cancel với xác nhận kết thúc** cho job cho phép hủy; phải giải phóng tài nguyên sau khi tác vụ thực sự dừng.
- **Checkpoint/retry** ở ranh giới idempotent khi plugin hỗ trợ chuyển tiến độ giữa version.
- **Restart worker/process riêng** theo quy trình cưỡng bức nếu plugin không hợp tác; không coi thao tác đóng class loader trong cùng JVM là cách giết thread an toàn.

### Giai đoạn D — Commit hoặc rollback

Sau cutover, quan sát v2 theo cửa sổ được chọn: latency, lỗi, timeout, memory, resource usage, tác động nghiệp vụ và sự tương thích dữ liệu. Nếu v2 ổn định và hết rollback window, thu hồi v1 khi không còn in-flight/rollback dependence.

Nếu phát hiện vấn đề ở v2, **rollback route** về một generation tương thích (v1 còn sống), đưa v2 vào DRAINING, tiếp tục cho những request đã nhận lease v2 hoàn tất hoặc hủy có kiểm soát, rồi mới dọn v2. Rollback không nhất thiết quay lại toàn bộ thế giới về trạng thái trước khi v2 nhận request: **ghi DB, gửi email, charge/payment, publish event, update cache** có thể đã xảy ra.

## 5. Timeline minh họa ba request

~~~text
Thời gian   Ứng dụng / route         Request A         Request B         Request C
----------  -----------------------  ----------------  ----------------  ---------------
t0          active = v1              acquire v1
t1          chuẩn bị v2              đang xử lý v1
t2          cutover: active = v2     vẫn xử lý v1
t3          v1 DRAINING              hoàn tất v1      acquire v2
t4          v1 inFlight = 0                            xử lý v2
t5          v1 STANDBY                                  hoàn tất v2
t6          health v2 xấu            --                --                --
t7          rollback: active = v1                                        acquire v1
t8          v2 DRAINING/STANDBY                                          hoàn tất v1
t9          v2 CLOSED sau drain
~~~

Ở t2, không chuyển request A sang v2. Ở t7, những request đã được cấp lease v2 trước rollback tiếp tục xử lý v2 theo chính sách mặc định, còn request C được cấp lease v1. Khi đường nghiệp vụ không cho phép v2 tiếp tục tạo side effects nguy hiểm, cần thêm policy **stop/cancel/quarantine**, không chỉ đổi pointer.

Bảng này là **diễn tiến logic**, không phải cam kết rằng các request luôn hoàn tất theo thứ tự cố định. Với nhiều worker/process, các thời điểm t0–t9 phải được phối hợp bằng cơ chế điều phối triển khai và định danh epoch.

## 6. Ví dụ Java 17 chạy được: lease, cutover, draining và rollback

Ví dụ độc lập mô hình hóa hai generation v1/v2 của một plugin. Mục đích là chứng minh thứ tự trạng thái và khả năng giữ request cũ qua cutover **mà không phụ thuộc web server, database hoặc file JAR bên ngoài**.

**Lưu ý phạm vi:** ví dụ mô phỏng xử lý yêu cầu bằng hàm String và điều khiển tiến trình tuần tự để stdout xác định. Nó sử dụng một monitor chung nhằm minh họa sự phối hợp nguyên tử giữa **admission và cutover**; chưa phải plugin manager sản xuất, không tự dừng thread, không tích hợp network health check và chưa có cleanup thật của URLClassLoader. Phần sau giải thích cách nâng cấp.

### 6.1. File PluginCutoverDemo.java

~~~java
public final class PluginCutoverDemo {

    enum State {
        PREPARED, ACTIVE, DRAINING, STANDBY, CLOSED
    }

    @FunctionalInterface
    interface Handler {
        String handle(String input);
    }

    static final class Generation {
        final String version;
        final Handler handler;
        State state = State.PREPARED;
        int inFlight;

        Generation(String version, Handler handler) {
            this.version = version;
            this.handler = handler;
        }
    }

    static final class Router {
        private final Object gate = new Object();
        private Generation current;

        Router(Generation initial) {
            if (initial.state != State.PREPARED) {
                throw new IllegalArgumentException("Not prepared");
            }
            initial.state = State.ACTIVE;
            current = initial;
        }

        Lease acquire() {
            synchronized (gate) {
                Generation g = current;
                if (g == null || g.state != State.ACTIVE) {
                    throw new IllegalStateException("No active generation");
                }
                g.inFlight++;
                return new Lease(this, g);
            }
        }

        Generation activate(Generation candidate) {
            synchronized (gate) {
                if (candidate.state != State.PREPARED) {
                    throw new IllegalStateException("Candidate not prepared");
                }

                Generation previous = current;

                previous.state = previous.inFlight == 0
                        ? State.STANDBY : State.DRAINING;

                candidate.state = State.ACTIVE;
                current = candidate;
                return previous;
            }
        }

        void rollbackTo(Generation previous) {
            synchronized (gate) {
                if (previous == current ||
                        (previous.state != State.STANDBY &&
                         previous.state != State.DRAINING)) {
                    throw new IllegalStateException(
                            "Previous generation not reusable");
                }

                Generation failed = current;
                failed.state = failed.inFlight == 0
                        ? State.STANDBY : State.DRAINING;

                previous.state = State.ACTIVE;
                current = previous;
            }
        }

        void release(Generation generation) {
            synchronized (gate) {
                if (generation.inFlight <= 0) {
                    throw new IllegalStateException("Lease underflow");
                }
                generation.inFlight--;

                if (generation.inFlight == 0 &&
                        generation.state == State.DRAINING) {
                    generation.state = State.STANDBY;
                }
            }
        }

        void markClosed(Generation generation) {
            synchronized (gate) {
                if (generation == current ||
                        generation.state != State.STANDBY ||
                        generation.inFlight != 0) {
                    throw new IllegalStateException(
                            "Generation is still in use");
                }
                generation.state = State.CLOSED;
            }
        }

        State stateOf(Generation generation) {
            synchronized (gate) {
                return generation.state;
            }
        }
    }

    static final class Lease implements AutoCloseable {
        private final Router router;
        private final Generation pinned;
        private boolean closed;

        Lease(Router router, Generation pinned) {
            this.router = router;
            this.pinned = pinned;
        }

        String execute(String input) {
            if (closed) {
                throw new IllegalStateException("Lease closed");
            }
            return pinned.handler.handle(input);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                router.release(pinned);
            }
        }
    }

    public static void main(String[] args) {
        Generation v1 = new Generation(
                "v1", input -> "v1:" + input);
        Generation v2 = new Generation(
                "v2", input -> "v2:" + input);

        Router router = new Router(v1);

        // Request A đã acquire lease v1 trước cutover.
        try (Lease pending = router.acquire()) {
            router.activate(v2);

            System.out.println(
                    "ongoing=" + pending.execute("A"));

            // Request B đến sau cutover, được route sang v2.
            try (Lease newer = router.acquire()) {
                System.out.println(
                        "new=" + newer.execute("B"));
            }

            System.out.println(
                    "old-while-inflight=" + router.stateOf(v1));
        }

        // Request A kết thúc, lease v1 được trả.
        System.out.println(
                "old-after-drain=" + router.stateOf(v1));

        // Giả định health gate quyết định v2 không đạt.
        router.rollbackTo(v1);

        try (Lease after = router.acquire()) {
            System.out.println(
                    "after-rollback=" + after.execute("C"));
        }

        System.out.println(
                "v2-after-rollback=" + router.stateOf(v2));

        router.markClosed(v2);
        System.out.println(
                "v2-after-retire=" + router.stateOf(v2));
    }
}
~~~

### 6.2. Biên dịch và chạy trên Java 17+

Lưu đúng tên **PluginCutoverDemo.java** ở encoding UTF-8, rồi dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 PluginCutoverDemo.java
java PluginCutoverDemo
~~~

**Stdout xác định:**

~~~text
ongoing=v1:A
new=v2:B
old-while-inflight=DRAINING
old-after-drain=STANDBY
after-rollback=v1:C
v2-after-rollback=STANDBY
v2-after-retire=CLOSED
~~~

### 6.3. Vì sao ví dụ đúng về admission/drain?

**Giai đoạn đầu:** router trỏ v1. Request A lấy Lease cho v1 và tăng v1.inFlight trong cùng gate. Sau đó activate(v2) chuyển pointer, nhưng Lease A vẫn giữ tham chiếu pinned=v1.

**Sau cutover:** Request B gọi acquire và nhìn thấy v2 ACTIVE, nên execute trả v2:B. Request A tiếp tục chạy v1:A; v1 đang DRAINING, không nhận request mới nhưng vẫn còn inFlight=1.

**Khi A kết thúc:** try-with-resources gọi Lease.close(), giảm inFlight của v1 từ 1 xuống 0. release chuyển v1 từ DRAINING sang STANDBY. Bài học là **đóng lease sau công việc**, không đóng plugin ngay sau khi thay pointer.

**Khi rollback:** rollbackTo(v1) đặt v2 vào STANDBY (vì request B đã hoàn tất), tái kích hoạt v1 và chuyển pointer về v1. Request C nhận v1 và trả v1:C.

**Khi retire:** markClosed(v2) chỉ đổi **trạng thái mô phỏng** sang CLOSED sau khi v2 không còn in-flight và không còn là pointer ACTIVE. Trong hệ thống thật, còn phải gọi stop/close các tài nguyên thực tế (sau khi không còn users hoặc rollback dependencies) và xử lý exception từ cleanup.

### 6.4. Giới hạn được chủ ý của demo

- Demo không khởi động hai Java thread cùng lúc; nó chứng minh bằng trình tự logic rằng request đã giữ v1 trước cutover vẫn dùng v1 sau cutover. Kiểm thử concurrency thật phải có thread pool, barrier và timeout riêng.
- Mỗi Lease trong demo thuộc sở hữu **một flow xử lý**. Trường closed là boolean thường, không có giao thức cho nhiều thread đóng/call đồng thời trên cùng Lease. Host production cần quy tắc ownership hoặc triển khai lease an toàn thread.
- Handler ở đây không nắm tài nguyên hoặc side effects. Production cần giữ cả DB connections, SDK handles, background jobs và callback theo scope generation.
- Router chỉ quản lý **một process**. Chuyển nhiều instance trong cluster cần bộ điều phối phiên bản/epoch, health gating và rollback đồng bộ.
- rollbackTo chỉ kiểm tra trạng thái mô phỏng. Production còn cần **tương thích schema**, tính tin cậy artifact, quyền sử dụng, trạng thái dữ liệu và chính sách rollback window.
- Không sử dụng Thread.stop, không trực tiếp unload class và không đóng class loader giữa lúc request chạy.

Đây là chương trình **học bất biến lifecycle**, không phải giải pháp thay nóng plugin đầy đủ với tất cả điều kiện vận hành.

## 7. Khi có tác vụ bất đồng bộ, lease phải sống tới khi hoàn thành thật

Sự khác biệt giữa API đồng bộ và async rất dễ gây lỗi. Với một phương thức trả CompletableFuture, code sau **sai về lifecycle**:

~~~java
// Ví dụ NGUY HIỂM: logic minh họa; không phải chương trình đứng riêng.
try (PluginLease lease = router.acquire()) {
    return lease.plugin().startAsync(input);
}
// Lease đóng ngay khi trả future, trong khi plugin vẫn chạy.
~~~

PluginLease là interface giả định do host định nghĩa, không phải Java API sẵn có. Trong đoạn trên, try-with-resources gọi close **trước khi future hoàn thành**; host có thể thấy inFlight=0, đóng generation và làm công việc bất đồng bộ thất bại.

Một cấu trúc thích hợp hơn:

~~~java
// MÃ MINH HỌA: giả định lease, router, input, Response đã được định nghĩa.
// CompletionStage<Response> là kết quả plugin trả về.
PluginLease lease = router.acquire();

try {
    return lease.plugin()
            .startAsync(input)
            .whenComplete((value, failure) -> lease.close());
} catch (RuntimeException | Error failure) {
    lease.close();
    throw failure;
}
~~~

Giữ lease cho đến khi completion stage kết thúc, cả success lẫn exception. Nhưng cần quan sát các điểm phụ:

1. **Cancellation** không nhất thiết làm tác vụ ở sâu bên dưới ngừng ngay; chỉ release khi chính sách đã xác nhận plugin không còn sử dụng tài nguyên generation, hoặc khi wrapper chịu trách nhiệm mọi hoạt động được gọi hoàn thành.
2. Completion callback có thể chạy trên thread bất kỳ; bản production cần **close idempotent và thread-safe** để tránh counter giảm hai lần nếu cancellation, timeout và completion đến gần nhau.
3. Nếu stage hoàn tất nhưng còn side effects bất đồng bộ không được stage đại diện (fire-and-forget), lease vẫn bị trả sớm. Phải gắn toàn bộ công việc thật với lifecycle.
4. Nếu close ném exception trong callback, cần ghi nhận và xử lý theo API nhưng không vô tình biến đổi hoặc che lỗi nghiệp vụ ban đầu.
5. Có thể dùng executor và scope/context để giữ thông tin generation, request ID và tenant xuyên thread.

Không chuyển request đang chạy sang phiên bản mới bằng cách gọi lại handler trên v2 trong một callback bất kỳ. Điều đó có thể thực thi cùng nghiệp vụ hai lần nếu v1 đã tạo một phần side effects.

## 8. Khi nào hủy yêu cầu và khi nào để hoàn tất?

Một chính sách thay thế tốt cần phân loại workload thay vì áp dụng một timeout duy nhất.

| Loại công việc | Chính sách drain thường phù hợp | Điều cần bảo toàn |
| --- | --- | --- |
| HTTP request ngắn | Cho hoàn tất trong grace period | Trả response đúng với phiên bản đã nhận |
| Tác vụ đọc idempotent | Có thể cancel/retry nếu timeout rõ ràng | Không gây phản hồi trùng hoặc dữ liệu sai |
| Ghi DB hoặc thanh toán | Ưu tiên hoàn tất/đảm bảo transaction; retry có idempotency key | Không double-charge/double-write |
| Message queue consumer | Pause lấy message mới, hoàn tất/ack đang xử lý; dùng retry/DLQ phù hợp | At-least-once semantics và deduplication |
| Batch job nhiều giờ | Checkpoint ở ranh giới ổn định, resume có protocol | Không mất tiến độ hoặc thực hiện lại một phần vô kiểm soát |
| WebSocket/gRPC stream dài | Drain phiên, thông báo reconnect hoặc giữ generation cũ tới deadline | Không cắt kết nối tùy tiện |
| Background timers/scheduled callbacks | Ngừng lên lịch mới, chờ callback đã phát động và dọn handle | Không giữ loader cũ sau khi plugin retire |
| Plugin không tin cậy/không hợp tác | Cách ly trong worker process có thể restart/cancel | Không treo host JVM hoặc làm hỏng toàn hệ |

**In-flight=0 chỉ đáng tin nếu bạn đếm đủ mọi dạng sử dụng.** Các handle do plugin cung cấp mà host lưu trong cache, event listeners, thread locals, timer tasks hoặc static registries có thể tiếp tục giữ tham chiếu ngay cả khi không còn HTTP request. Chúng phải được liệt kê và đưa vào giao thức dừng/tháo đăng ký.

### Quy tắc cho timeout và graceful shutdown

- Đặt deadline ở cấp request và ở cấp rollout. Khi hết deadline, phân biệt những tác vụ **có thể hủy an toàn** với tác vụ đang ở pha commit không thể hủy tùy ý.
- Không dùng Thread.stop để ép dừng code plugin trong cùng JVM: nó có thể làm hỏng monitor và trạng thái chia sẻ.
- Việc Thread.interrupt() hoặc cancel(true) chỉ gửi tín hiệu/hủy theo cơ chế hỗ trợ; không bảo đảm code plugin đã dừng ngay.
- Với plugin chứa native code, I/O bất định hoặc thực thi script không tin cậy, worker process có giới hạn CPU/RAM/time và khả năng kill/restart thường dễ bảo đảm isolation hơn.
- Sau deadline, nếu còn in-flight chưa dừng, không được đánh dấu CLOSED một cách giả tạo rồi đóng loader. Thay vào đó đưa rollout vào trạng thái **BLOCKED/DEGRADED**, tiếp tục giám sát hoặc dùng chính sách cưỡng bức ở biên process.

## 9. Rollback route không đồng nghĩa rollback dữ liệu

Đây là giới hạn quan trọng nhất của hot replacement. Khi v2 từng ACTIVE, nó có thể đã:

- Ghi row mới vào database theo schema v2.
- Publish event mà consumer v1 không hiểu.
- Đánh dấu một giao dịch đã được xử lý hoặc gửi notification.
- Tạo cache entries với định dạng mới.
- Gọi API bên thứ ba thực hiện side effects khó đảo ngược.
- Thay đổi trạng thái file hoặc session nằm ngoài plugin class loader.

Chuyển pointer về v1 **chỉ quyết định nơi xử lý request mới**. Nó **không hoàn tác** những thay đổi đó.

### 9.1. Expand–contract migration

Trong khoảng cho phép rollback, ưu tiên thay đổi dữ liệu có tính **backward/forward compatibility**:

1. **Expand**: thêm cột hoặc trường mới tùy chọn; cả v1/v2 vẫn đọc được định dạng chung.
2. **Transition**: v2 ghi dạng tương thích hoặc dual-write/dual-read có kiểm soát; versioned payload và consumer thích ứng.
3. **Observe**: xác minh cả v1 và v2 xử lý dữ liệu/event quan trọng trong cửa sổ rollback.
4. **Contract**: chỉ xóa cột/trường cũ hoặc áp dụng migration phá vỡ tương thích **sau khi** hết cửa sổ rollback và không còn cần v1.

Ví dụ: v1 hiểu payload JSON gồm id và amount, v2 thêm trường optional currency. Nếu v1 bỏ qua field không biết và hợp đồng dữ liệu cho phép, rollback dễ hơn. Nếu v2 đổi amount từ số sang object có schema không tương thích và ghi dữ liệu sản xuất, v1 có thể không đọc được sau rollback; phải có kế hoạch down-migration có kiểm chứng hoặc chặn rollback tự động.

**Migrations giảm rủi ro, không phải bảo đảm:** tính tương thích tùy ORM, validation, API schema, query, sự kiện và hành vi business thực tế. Đừng chỉ chạy schema migration SQL rồi kết luận rollback an toàn.

### 9.2. Idempotency và xử lý request trong vùng giao nhau

Trong giai đoạn cutover/rollback, retries có thể đến generation khác. Nếu một request đã ghi DB qua v2 nhưng client không nhận phản hồi rồi retry vào v1, host phải tránh thực hiện lại cùng transaction.

Biện pháp điển hình:

- Gán request ID / idempotency key có phạm vi rõ ràng.
- Lưu trạng thái giao dịch/deduplication ở một nơi chia sẻ giữa các generation, không chỉ trong bộ nhớ của plugin.
- Sử dụng transactional outbox hoặc giao thức bền vững khi cần nhất quán DB và event.
- Áp dụng versioned events, bảo đảm consumer cũ chịu được loại event phát sinh trong rollback window.
- Phân biệt retry an toàn, compensation/saga và giao dịch không thể đảo ngược.

Một retry **không phải** rollback. Compensation (nếu nghiệp vụ cho phép) cần được thiết kế và kiểm chứng riêng, có audit.

### 9.3. Stateful plugin và chuyển trạng thái

Nếu plugin chỉ là hàm thuần trên input, rollback khá đơn giản. Nếu plugin giữ state trong RAM, session, cache, connection hoặc actor, cần quyết định:

- **Sticky/pinned sessions**: session cũ tiếp tục ở v1 cho tới khi kết thúc, session mới đi v2; rollback có thể cần đưa session mới về version được hỗ trợ.
- **State snapshot**: serialize state theo schema có phiên bản, khôi phục vào thế hệ khác theo quy trình thử nghiệm.
- **Shared external state**: cả v1/v2 truy cập store tương thích, có khóa/transaction version để tránh race.
- **Dual-run/shadow**: v2 được cấp bản sao input để đánh giá kết quả nhưng không thực hiện side effects thật; không thể tùy tiện shadow cho giao dịch ghi.
- **Irreversible state**: nếu v2 thay đổi trạng thái mà v1 không phục hồi được, tắt rollback tự động và chuyển sang phương án khắc phục phù hợp.

Không được serialize object của class loader v2 rồi deserialize trực tiếp trong v1 nếu class identity hoặc schema Java đã khác. Nên dùng DTO/JSON/Protobuf hoặc định dạng bền vững có kiểm soát phiên bản thay vì nội suy rằng Java Serializable giải quyết hot swap.

## 10. Readiness, health gate, canary và tiêu chí quyết định

Có hai loại kiểm tra khác nhau:

- **Readiness trước cutover**: plugin khởi tạo đúng, dependency có sẵn, contract API hợp lệ, kết nối cần thiết hoạt động, smoke test không gây side effects ngoài ý muốn.
- **Health sau cutover**: phiên bản mới chịu được lưu lượng thật và có tỷ lệ lỗi/độ trễ, mức tài nguyên, tỷ lệ thành công nghiệp vụ trong ngưỡng đã định.

Một plugin có thể vượt qua readiness nhưng thất bại sau khi nhận một loại request hiếm hoặc một mức concurrency lớn. Vì thế nên dùng health window và tiêu chí rollback đã xác định **trước khi triển khai**.

Ví dụ chính sách (giá trị chỉ là minh họa, phải hiệu chỉnh theo SLO thực tế):

~~~text
PREPARE:
  validate artifact, API, dependencies
  warmup and smoke test isolated candidate

ACTIVATE:
  switch 5% eligible new requests to v2
  pin each request to its chosen generation

OBSERVE:
  compare v1/v2 error rate and latency
  inspect business outcomes, queues and saturation
  preserve v1 as rollback candidate

PROMOTE:
  increase traffic gradually when gates pass

ROLLBACK:
  route new requests back to v1 if gates fail
  drain already-started v2 requests
  retain evidence, preserve versioned state

RETIRE:
  close old generation only after rollback window,
  zero leases and dependency checks
~~~

**Canary** nghĩa là có thể có hai generation nhận request mới theo chính sách trọng số; máy trạng thái phải mở rộng từ một active pointer đơn sang **routing table có version/epoch**, đồng thời mỗi request vẫn chỉ lấy **một lease của một generation**. Những yêu cầu trong cùng session/transaction có thể cần sticky routing; random 5% từng message không luôn đúng.

### Gợi ý thước đo và audit

Ghi tối thiểu:

- plugin ID, generation ID, artifact hash, config revision, host API version;
- generation được route vào từng request, idempotency key và rollout/cutover epoch;
- số in-flight, số request mới theo thế hệ, độ trễ, lỗi, timeout, cancel;
- kích hoạt/rollback/retire: thời điểm, người hay policy ra quyết định, lý do;
- hiệu quả nghiệp vụ và dấu hiệu data compatibility;
- số tài nguyên chưa dọn, class loader references, background tasks còn sống.

Không thu thập payload bí mật chỉ để debug nếu không cần; kiểm soát quyền truy cập log. Bằng chứng vận hành phải đủ để phân biệt lỗi plugin mới, lỗi phụ thuộc bên ngoài và lỗi chính cơ chế cutover.

## 11. Ranh giới class loader và tài nguyên khi rollback

Trong Java, mỗi generation của plugin thường được nạp bằng **class loader riêng** hoặc ModuleLayer phù hợp. Nếu muốn giữ v1 cho rollback, host phải giữ reference có chủ đích tới instance, loader, config và tài nguyên cần dùng, nhưng **không để các reference đó rò rỉ vô hạn** sau khi hết rollback window.

### Giữ chung API, tách implementation

Ví dụ kiến trúc:

~~~text
Host / parent loader
└── Plugin API: com.example.spi.Formatter
     |
     +-- Generation v1 loader → FormatterImpl v1, deps v1
     |
     +-- Generation v2 loader → FormatterImpl v2, deps v2

Host router:
  ACTIVE → v2
  STANDBY → v1
  leases(v1) = 0
  leases(v2) = 3
~~~

Interface service cần có cùng **Class identity** giữa host và provider; tránh để child-first plugin loader định nghĩa bản sao API tách biệt khiến ClassCastException hoặc ServiceConfigurationError. Host không nên giữ tham chiếu static đến implementation class của v1 sau khi đã retire nếu muốn class loader được GC.

### URLClassLoader.close() có ý nghĩa gì?

Ở Java 17, **URLClassLoader.close()** đóng các tài nguyên file/JAR mà loader mở theo hợp đồng, ngừng hỗ trợ nạp những **class/resource mới** được xác định bởi loader đó; các class đã được định nghĩa trước vẫn tồn tại và có thể truy cập. **close() không unload class ngay lập tức** và không tự dừng threads đang chạy code của plugin.

Một lớp có thể vẫn tồn tại nếu còn strong references đến Class, instance, thread context class loader, ThreadLocal, callback, listener, scheduled task hoặc singleton cache. Không đóng loader đang có thread nạp class, vì kết quả của class loading đồng thời với close có thể không xác định theo hợp đồng. Chỉ close sau khi đã kiểm soát mọi công việc và đường nạp liên quan.

Tương tự, **ServiceLoader.reload()** chỉ xóa cache provider của chính đối tượng ServiceLoader; nó không tự chuyển route, không chờ in-flight, không hoàn tác side effects và không đảm bảo unload một generation. Hot replacement ở mức sản xuất cần lifecycle manager phía host.

### Thứ tự thu hồi có kiểm soát

1. Ngừng admission mới vào generation được retire.
2. Chờ leases về 0 hoặc áp dụng chính sách hủy có xác nhận.
3. Hủy đăng ký listeners, timers, scheduled jobs và những callback riêng của generation.
4. Gọi plugin.stop()/close() có timeout/chính sách lỗi phù hợp, ngoài các khóa route quan trọng.
5. Đóng resources và class loader khi không còn load operation.
6. Xóa tham chiếu trong router, registry, cache và ThreadLocal; kiểm tra memory/classloader leak.
7. Đánh dấu CLOSED và ghi kết quả cleanup/audit. Nếu cleanup thất bại, ghi **cleanup pending/failed** thay vì báo đóng thành công giả tạo.

Ở production, các bước có thể có cơ chế prepare/commit và failure handling riêng; ví dụ Java chỉ mô phỏng guard trước khi đánh dấu CLOSED, không triển khai tất cả bước resource teardown.

## 12. Đa instance, nhiều luồng và rollback trong cluster

Mã Java ví dụ dùng một monitor trong một JVM. Nếu ứng dụng có nhiều replica, mỗi replica có active pointer riêng thì một lần cập nhật một instance không đủ để tạo cutover nhất quán toàn cluster. Cần định nghĩa:

- **Rollout epoch/generation** trong một nơi quản lý cấu hình hoặc control plane.
- Các instance **prepare cùng artifact và config**, ghi readiness riêng trước khi chấp nhận traffic.
- Load balancer/router phân luồng theo version, tenant/session hoặc nhãn deployment; tránh lẫn kết quả khi không tương thích.
- Quy tắc **fencing** nếu có nhiều tác nhân cùng ra lệnh activate/rollback, không cho một lệnh deploy cũ ghi đè chỉ đạo mới.
- Health window và metrics theo replica/version để tránh bỏ sót một instance lỗi.
- Quản lý in-flight ở mỗi instance; **global in-flight=0** chỉ được kết luận sau khi có bằng chứng đủ từ các instance cần xét.
- Khi rollout một phần thất bại, chính sách dừng hoặc rollback phần đã chuyển và cách phục hồi traffic.

### Vì sao pointer atomic chưa đủ trong cluster?

AtomicReference chỉ tạo một lựa chọn nguyên tử **trong JVM đã thực hiện thao tác**. Nó không thay đổi routing ở các process khác và không tự đồng bộ những side effects trong database. Với rollback, phải thực hiện theo control plane và xác nhận từng instance hoặc load balancer đã áp dụng phiên bản mong muốn; cần xử lý replica mất kết nối, retry lệnh và lệnh đến sai thứ tự.

Khi có hai controller, mỗi thao tác chuyển trạng thái nên mang **expected epoch** và **new epoch**; controller chỉ commit nếu trạng thái hiện tại khớp. Cơ chế này giúp tránh một rollback lỗi thời đưa hệ thống quay về phiên bản không còn được chấp nhận.

### Không đợi task dài trong khóa routing

Thao tác lấy lease và cutover nên cực ngắn. Đừng giữ synchronized(gate) trong khi:

- gọi plugin.processRequest, plugin.stop hoặc plugin.close;
- thực hiện database query, remote health check, network I/O;
- chờ Thread.join, Future.get hoặc đợi inFlight về 0;
- thực hiện migration hoặc rollback dữ liệu.

Giữ khóa quá lâu có thể làm kẹt admission toàn hệ thống và tạo deadlock khi plugin callback ngược về registry. Bản mẫu giải quyết bằng cách **chỉ giữ gate để thay pointer/counter/state**, còn Handler.handle chạy ngoài khóa.

## 13. Thiết kế rollback có kiểm chứng

Rollback đáng tin cậy cần trả lời ít nhất bốn nhóm điều kiện:

1. **Còn code cũ không?** Generation v1 chưa CLOSED, artifact và phụ thuộc chưa bị xóa, instance vẫn sẵn sàng/khởi động lại được.
2. **Dữ liệu vẫn tương thích không?** Database schema, event, cache và session từ v2 có thể được v1 xử lý hoặc có đường phục hồi được kiểm chứng.
3. **Request đang chạy thế nào?** Những lease v2 còn mở sẽ hoàn tất, hủy hoặc được checkpoint ra sao? Liệu nó còn tạo side effects nguy hiểm khi traffic đã quay v1?
4. **Tuyến đã thực sự đổi chưa?** Router và load balancer của mọi replica dùng đúng epoch/generation, không còn một node âm thầm nhận request mới cho v2.

Nếu điều kiện rollback không đạt, **không tự kích hoạt v1 chỉ vì health v2 xấu**. Có thể cần pause traffic, chuyển sang chế độ read-only, dùng bản vá tương thích v2, thực hiện restore/compensation theo runbook, hoặc điều phối rollback nhiều bước. Phải báo rõ rollback bị chặn vì data schema, state hoặc in-flight chưa an toàn.

### Rollback tự động và thủ công

- **Tự động** phù hợp khi health gates có tín hiệu đáng tin, việc quay route đã thử nghiệm, state tương thích và không có side effects không đảo ngược cần quyết định con người.
- **Thủ công** phù hợp khi có giao dịch nhạy cảm, migration phá vỡ tương thích, cần phối hợp bên thứ ba hoặc rủi ro hủy task lớn.

Dù theo hướng nào, mỗi lần rollback phải có reason code, version/epoch nguồn–đích, audit và kế hoạch tiếp tục sau rollback. Tránh vòng auto-rollback/auto-promote lặp vô hạn do health dao động; cần cooldown và chính sách retry.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách phòng tránh/khắc phục |
| --- | --- | --- |
| Request cũ lỗi ngay sau cutover | Đóng instance/loader v1 trước khi lease kết thúc | Pin request theo generation, đợi drain rồi mới close |
| inFlight về 0 dù task vẫn đang chạy | Release lease khi trả Future thay vì khi hoàn tất | Liên kết lease với completion thực sự, kể cả cancellation |
| Request mới vẫn vào v1 sau cutover | Đọc current và tăng refcount thiếu phối hợp | Dùng cùng admission gate hoặc giao thức CAS/refcount chuẩn |
| Không thể rollback dù v1 còn artifact | Đã stop/close resources hoặc xóa state v1 | Giữ v1 STANDBY trong rollback window |
| Rollback route thành công nhưng v1 lỗi DB | v2 ghi schema/data không tương thích | Expand–contract, versioned payload, kiểm thử backward compatibility |
| Retry tạo giao dịch trùng | Request đi lại qua v1/v2 không có key chung | Idempotency key và dedupe store dùng chung |
| Drain treo vô thời hạn | Streaming/job lâu, orphan callbacks hoặc lease leak | Deadline, metrics per generation, cancellation/checkpoint policy |
| Dùng ServiceLoader.reload() rồi tưởng đã hot swap | Cache reload không thay routing/lifecycle | Quản lý generation, loader và admission riêng |
| OOM/metaspace tăng sau nhiều lần thay | ThreadLocal/listener/class cache giữ loader cũ | Cleanup toàn bộ references, test unload và memory leak |
| Lệnh rollback cũ ghi đè deploy mới | Thiếu epoch/fencing | Versioned control-plane commands và expected-state check |
| Plugin v2 được bật trước readiness | Routing nhận request trước khi dependencies sẵn sàng | Prepare/warmup và health gate trước cutover |
| Rollback che lỗi nhưng side effects đã tồn tại | Hiểu rollback là khôi phục tất cả dữ liệu | Tách route rollback khỏi compensation/DB restore |

### Những điều không nên làm

- Thay trực tiếp object singleton v1 bằng object v2 rồi xóa ngay mọi tham chiếu v1 trong khi request cũ còn sử dụng.
- Gọi plugin.stop() dưới một khóa mà request đang chạy cần để kết thúc hoặc release lease.
- Dùng sleep vài giây như bằng chứng inFlight đã về 0; đo bằng bộ đếm và trạng thái có ownership rõ.
- Ép đổi logic của một request đang thực thi từ v1 sang v2 nếu chưa có state transfer protocol.
- Xem việc rollback code là khả năng rollback mọi transaction, event và schema.
- Giữ mọi plugin loader cũ vô hạn để “an toàn rollback”; đặt rollback TTL và quy trình thu hồi.
- Sử dụng Thread.stop hoặc URLClassLoader.close để cưỡng bức dừng request đang xử lý.

## 15. Chiến lược kiểm thử trước khi phát hành

Một hệ hot replacement tốt phải kiểm thử cạnh tranh và lỗi, không chỉ ví dụ happy path:

1. **Concurrent admission và cutover:** nhiều thread acquire trong lúc đổi pointer; tất cả lease thuộc một generation hợp lệ, counter không âm và không có request mới vào thế hệ đã ngừng admission sau thời điểm commit.
2. **Request giữ v1 lâu:** cutover v2 trong khi v1.inFlight > 0; v1 không được CLOSED khi lease chưa release.
3. **Future hoàn tất muộn:** async request vẫn tính inFlight tới kết thúc; callback exception/cancellation không release hai lần.
4. **Kích hoạt thất bại trước cutover:** v1 vẫn ACTIVE, candidate được cleanup, không có route trỏ vào generation chưa sẵn sàng.
5. **v2 lỗi sau cutover:** rollback về v1 còn sống; request mới dùng v1; request v2 đã được cấp lease xử lý theo chính sách drain/cancel rõ.
6. **Rollback khi v1 còn DRAINING:** controller phải có quy tắc cho phép tái admission hoặc chặn nếu tài nguyên v1 đã bị đóng một phần.
7. **Rollback bị chặn vì schema không tương thích:** không silently chuyển v1; phát status và đưa ứng dụng vào chiến lược phục hồi.
8. **Two-controller race:** hai lệnh activate/rollback với epoch khác nhau, lệnh stale bị từ chối.
9. **Drain timeout và leaked lease:** metrics, cảnh báo, chính sách escalation; không giả báo zero khi thực tế vẫn có task.
10. **Tài nguyên sau retire:** thread pool, listeners, timer, class loader, JAR handles và references được giải phóng, không có memory leak kéo dài.
11. **Idempotency xuyên generation:** client retry sau timeout không tạo side effects trùng khi route thay.
12. **Canary và sticky sessions:** đúng tỷ lệ chọn phiên bản và các yêu cầu liên quan cùng session dùng policy nhất quán.

Với test concurrency, dùng CountDownLatch, CyclicBarrier, ExecutorService và timeout có kiểm soát để tạo ra các liên lịch khó xảy ra, tránh kiểm tra bằng Thread.sleep đơn thuần. Khi test plugin có thể treo, chạy trong worker JVM/process để không làm kẹt toàn bộ bộ kiểm thử.

Kiểm thử rollback tối thiểu gồm hai phía: **route/lease state** và **data compatibility/side effects**. Pass một test chuyển pointer không đủ để kết luận có thể rollback sản phẩm.

## 16. Checklist khi chuẩn bị thay thế plugin

- **Generation identity**: mỗi lần nạp có ID, artifact hash, config và resource scope riêng.
- **Prepare**: kiểm tra dependency, API type identity, quyền, compatibility và readiness trước khi nhận tải.
- **Admission**: request mới được cấp lease theo routing policy một cách nguyên tử với cutover.
- **Pinning**: request đã bắt đầu tiếp tục dùng đúng generation của nó.
- **Async lifecycle**: lease chỉ kết thúc khi toàn bộ công việc thật hoàn tất hoặc hủy có xác nhận.
- **Drain**: thế hệ cũ ngừng nhận mới nhưng giữ tài nguyên khi inFlight > 0; có timeout và escalation.
- **Rollback candidate**: giữ v1 STANDBY đủ lâu, không close/garbage-collect trước khi hết rollback window.
- **Rollback guard**: schema/data/event/cache/session có tương thích với v1 không, side effects v2 xử lý thế nào.
- **Health gates**: định nghĩa ngưỡng lỗi, latency, business metrics, canary và audit trước rollout.
- **Concurrency/cluster**: không dùng pointer cục bộ để suy ra toàn cluster đã chuyển; có epoch/fencing.
- **Retire**: khi không còn lease/rollback dependence, ngắt callback/timer và đóng resources ngoài khóa route.
- **Observability**: metric và log có generation ID, request ID, trạng thái, cutover epoch, lỗi, drain time.
- **Tests**: luyện tập cutover + rollback thật trong môi trường có tải và dữ liệu tương thích.

**Kết luận:** Thay thế plugin an toàn là **quản lý vòng đời thế hệ và những request đang sở hữu nó**, không chỉ nạp class mới. Dùng lease để pin request, cutover nguyên tử để chuyển yêu cầu mới, drain có deadline để giữ request cũ tới lúc hoàn tất, và rollback có guard để đưa traffic quay lại phiên bản còn tương thích. Trong hệ thống có trạng thái, **khả năng rollback dữ liệu và side effects phải được thiết kế trước lần bật v2**, không thể tạo ra chỉ bằng việc đổi pointer sau khi sự cố xảy ra.

## Tài liệu tham khảo

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): danh tính class/loader và hợp đồng nạp lớp.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): close() và giới hạn đối với class đã nạp.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): cache/reload, class loader và khả năng khám phá provider.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): giải phóng lease với try-with-resources.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion stage và whenComplete cho async lifecycle.