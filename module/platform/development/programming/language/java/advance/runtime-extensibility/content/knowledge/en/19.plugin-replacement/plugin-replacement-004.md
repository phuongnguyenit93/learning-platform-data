# Chuẩn bị, kiểm tra rồi chuyển tham chiếu đang hoạt động sang thế hệ mới

**Thay thế plugin an toàn ở runtime không phải là ghi đè JAR, gọi lại `ServiceLoader` hoặc gán ngay một instance mới vào biến.** Một plugin có thể đang xử lý request, giữ tài nguyên, có thread nền, class loader riêng, cache và state. Muốn nâng từ phiên bản V1 sang V2 mà không làm hỏng những request đang chạy, cần tách rõ ba giai đoạn:

1. **Prepare:** dựng một *thế hệ plugin* (plugin generation) mới ở trạng thái chưa phục vụ traffic: tìm artifact, tải và cấu hình code, khởi tạo dependencies, làm warm-up.
2. **Validate:** kiểm tra compatibility, cấu hình, quyền, kết nối, behavior/health, ngân sách tài nguyên và khả năng cleanup; nếu không đạt thì hủy riêng candidate, **không đụng thế hệ đang hoạt động**.
3. **Publish / cutover:** công bố **một tham chiếu active** trỏ tới generation mới bằng thao tác atomic. Request mới được định tuyến tới thế hệ mới; request đã nhận V1 tiếp tục dùng V1. Sau đó *retire → drain → close* V1 theo chính sách vòng đời.

Đây là mô hình **prepare–validate–atomic switch–graceful retirement**. Bài viết trình bày cách xây dựng với Java 17+, lý do cần quản lý in-flight requests và lỗi dễ xuất hiện khi class loader, provider, resource hoặc state cũ còn được giữ.

## 1. “Thế hệ plugin” là gì và tại sao phải quản lý theo thế hệ?

Một *generation* là đơn vị triển khai bất biến về danh tính trong một vòng đời. Nó có thể giữ:

- `generationId` và `version` (hoặc hash artifact), plugin ID và metadata kiểm soát compatibility;
- loader riêng: `URLClassLoader` hoặc `ModuleLayer` cùng các module/class loader của layer;
- instance implementation của **API do host sở hữu**;
- cấu hình đã được validate, immutable routing table, codec list, endpoint hoặc capability metadata;
- handle tài nguyên: executor, cache, connection, listener, stream, file/JAR, registry registration;
- trạng thái vòng đời, số request đang sử dụng (reference count/lease) và cơ chế cleanup.

`Generation` không nhất thiết phải chứa tất cả những thứ này ở một class duy nhất, nhưng **phải có owner rõ ràng** chịu trách nhiệm khởi tạo/đóng. Một biểu diễn khái niệm:

```text
Host / PluginRegistry
    |
    | active (atomic reference)
    v
Generation V2  [ACTIVE]
    |- Plugin API instance
    |- ClassLoader / ModuleLayer V2
    |- Immutable configuration / routing
    |- Resources owned by V2
    +- In-flight lease count

Generation V1  [RETIRING]
    |- Plugin API instance
    |- ClassLoader / ModuleLayer V1
    |- Resources owned by V1
    +- In-flight lease count > 0  (chưa được close)
```

Cùng binary name `com.example.plugin.Handler` **không đồng nghĩa cùng class identity** ở hai loader khác nhau. Java coi kiểu theo **(class name, defining class loader)**. Với plugin code mới, thường cần class loader/module layer mới; không kỳ vọng file JAR thay đổi trên đĩa khiến các class V1 đã load tự biến thành V2.

**Tham chiếu active** là cổng chọn generation hiện hành, không phải một phương pháp unload class hay rollback dữ liệu. Các đối tượng ở V1 còn tồn tại đến khi không còn strong references; `URLClassLoader.close()` cũng không hủy ngay những `Class` hoặc object đã tạo.

## 2. Hợp đồng trạng thái: PREPARING → VALIDATED → ACTIVE → RETIRING → CLOSED

Một luồng lifecycle nên được định nghĩa trước khi viết code:

| Trạng thái | Ý nghĩa | Ai được sử dụng? | Hành động hợp lệ |
| --- | --- | --- | --- |
| `PREPARING` | Đang tải/khởi tạo candidate, chưa sẵn sàng | Chỉ thread quản lý plugin | Cấu hình, start, warm-up; lỗi → cleanup |
| `VALIDATED` / `READY` | Đã qua kiểm tra, vẫn chưa là active | Plugin manager, test có kiểm soát | Publish hoặc hủy candidate |
| `ACTIVE` | Generation được tham chiếu active chọn để nhận tác vụ | Request mới và request đang chạy | Acquire lease, xử lý nghiệp vụ |
| `RETIRING` | Không tiếp nhận tác vụ mới; chờ request cũ thoát | Chỉ người đã sở hữu lease hợp lệ | Drain, await completion, release |
| `CLOSED` | Đã đóng tài nguyên và bỏ references thuộc owner | Không ai | Không được gọi plugin hoặc tái sử dụng generation |
| `FAILED` | Candidate không qua prepare/validate hoặc phát sinh lỗi lifecycle | Chỉ quản lý để chẩn đoán và dọn dẹp | Quarantine, close, log, retry từ generation **mới** |

Các nhãn trạng thái ở trên là **mô hình ứng dụng**, không phải enum có sẵn trong JDK. Trong hệ thống thật có thể thêm `DISABLED`, `DEGRADED` hoặc `ROLLBACK_READY`. Điều quan trọng là **một generation chưa đạt điều kiện READY không được nhìn thấy từ active pointer**.

Một bất biến cần giữ:

> Nếu một request đã được chấp nhận và sở hữu lease của V1, V1 không được đóng tài nguyên mà request đó còn cần, kể cả khi `active` đã trỏ đến V2.

Vì thế thao tác `active.set(V2)` có thể đủ để *chọn generation* nhưng **không đủ để quản lý cleanup**.

## 3. Giai đoạn Prepare: dựng candidate hoàn chỉnh nhưng chưa publish

Tầng plugin manager nên tạo candidate tách biệt với thế hệ đang chạy, ví dụ:

```text
Artifact V2 (JAR/module + metadata + checksum)
       |
       v
Policy / dependency / API compatibility checks
       |
       v
ClassLoader V2 hoặc ModuleLayer V2
       |
       v
Discover provider / instantiate plugin / inject config
       |
       v
Start resources + warm-up + build routing snapshot
       |
       v
Candidate Generation V2 [không phục vụ request]
```

### Những thứ cần chuẩn bị

**Artifact và dependency:** kiểm tra plugin ID, version và nguồn phát hành; verify checksum/chữ ký theo chính sách, scan dependency/module conflicts, xác nhận cả metadata và nội dung JAR thuộc đúng artifact được chấp thuận. Tránh tải V2 từ thư mục đang bị deploy in-place mà một writer khác đang thay đổi.

**Class loader/module:** giữ **service interface hoặc host API** ở một loader chung được kiểm soát; implementation V1 và V2 có thể ở loader/layer riêng. Nếu plugin nạp lại một bản sao của service interface trong child loader, host có thể gặp `ClassCastException` dù tên lớp giống nhau. Khi dùng JPMS, kiểm tra `requires`, `uses`, `provides` và module graph phù hợp.

**Dependencies và cấu hình:** validate syntax/schema/secret references, endpoint, permission/capability, mapping và chính sách tương thích. Cấu hình snapshot của generation nên là immutable hoặc chỉ được thay đổi qua cơ chế versioned riêng.

**Khởi tạo:** constructor, dependency injection, `start`, initialization và warm-up có thể **chạy code của plugin**. Không coi “chưa publish” là một sandbox: candidate vẫn có thể kết nối mạng, đăng ký listener hoặc tạo thread ngay lúc khởi tạo. Các side effect phải có owner và khả năng rollback/cleanup.

**Routing snapshot:** xây sẵn map từ command/service name đến handler cụ thể, không để request phải tự duyệt `ServiceLoader`/scan classpath khi đang xử lý. Điều này giảm race giữa discovery và cutover.

### Minh họa trách nhiệm, không phải code độc lập

```java
// Pseudocode kiểu Java: các type là contract do ứng dụng tự định nghĩa.
PreparedGeneration candidate = prepare(artifact, config);
try {
    validate(candidate);     // không chạm vào active pointer
    publish(candidate);      // atomic switch sau khi đã sẵn sàng
} catch (Exception failure) {
    if (!candidate.wasPublished()) {
        candidate.close();   // hủy riêng bản candidate
    }
    throw failure;
}
```

Trong code production cần có ownership/handoff rõ để tránh **đóng nhầm candidate đã publish** khi cleanup cũ thất bại *sau* cutover. Tốt nhất tách lỗi `prepare/validate` với lỗi `retire old`, và chỉ manager biết chính xác thời điểm chuyển sở hữu từ candidate sang registry. Các type/method ở đoạn trên là minh họa kiến trúc, **không thuộc Java SE**.

## 4. Validate trước cutover: từ “load được” đến “sẵn sàng phục vụ”

`ClassLoader.loadClass` hoặc `ServiceLoader.findFirst` thành công **không chứng minh** plugin đã sẵn sàng. Tùy hợp đồng API, điều kiện có thể bao gồm:

| Nhóm kiểm tra | Câu hỏi cần trả lời | Failure policy |
| --- | --- | --- |
| Tính nguyên vẹn | Artifact có đúng hash, chữ ký, nguồn phê duyệt không? | Reject ngay trước load |
| Compatibility | Plugin API/ABI, Java version, dependency, module reads/exports, schema có phù hợp không? | Reject |
| Cấu hình | Thiếu secret, invalid endpoint, feature flags hoặc mapping xung đột? | Reject trước publish |
| Discovery | Có đủ provider bắt buộc? Có trùng provider ID, conflict service name? | Reject hoặc chọn theo policy tường minh |
| Liveness/health | Plugin khởi tạo và phản hồi probe trong giới hạn? | Reject/timeout candidate |
| Behavior | Smoke test, contract test, dữ liệu biên, serialization format | Reject nếu contract bị vi phạm |
| Resource budget | Candidate có vượt giới hạn file descriptors, thread, connection, heap? | Reject hoặc trì hoãn rollout |
| Cleanup readiness | Khi close có dừng thread, hủy registration, giải phóng cache/stream? | Reject nếu không có vòng đời rõ |
| Isolation | Có quyền truy cập host API/hệ thống theo trust policy? | Chặn, không dùng class loader như sandbox |

**Warm-up và readiness test nên có side effect có thể cô lập hoặc hoàn tác.** Tránh một “test” vô tình gửi thanh toán, email hoặc thay đổi dữ liệu production. Nếu bắt buộc thử một thao tác có tác động ngoài, dùng môi trường kiểm thử, request idempotent hoặc cơ chế transaction được thiết kế rõ.

### Quy tắc thất bại trước publish

Nếu `prepare` hoặc `validate` thất bại, `active` vẫn chỉ V1, request đang chạy tiếp tục. Candidate được dọn theo scope riêng, ghi nguyên nhân và không tái sử dụng đối tượng/loader đã ở trạng thái bất định.

```text
V1 [ACTIVE] ---- vẫn phục vụ ----
              Candidate V2 [PREPARING]
                       |
                 validation FAIL
                       v
                 close/quarantine V2
V1 [ACTIVE] ---- không đổi -----
```

Đây là ưu điểm lớn của **“chuẩn bị xong rồi mới chuyển”** so với thao tác dỡ V1 trước rồi thử tải V2.

## 5. Atomic publication: chỉ chuyển một tham chiếu đã khởi tạo hoàn chỉnh

Có thể giữ active bằng:

```java
private final java.util.concurrent.atomic.AtomicReference<Generation> active =
        new java.util.concurrent.atomic.AtomicReference<>();
```

Đây là snippet, `Generation` là kiểu ứng dụng. Sau khi tạo/validate V2 hoàn chỉnh:

```java
Generation old = active.getAndSet(newGeneration);
retireWhenDrained(old);
```

Đây cũng là snippet; `retireWhenDrained` do ứng dụng định nghĩa. `getAndSet` có hiệu ứng atomic cho tham chiếu: reader thấy **V1 hoặc V2**, không thấy “nửa đối tượng”. Các thao tác atomic/volatile phù hợp cung cấp quan hệ **happens-before** để những dữ liệu V2 khởi tạo trước khi publish có thể được reader quan sát đúng.

**Điều atomic ở đây là con trỏ tham chiếu, không phải toàn bộ hệ thống ngoài JVM**. Việc đổi active không tự chuyển DB transaction, event subscription, cache, socket, schema dữ liệu hay tất cả request đang chạy sang phiên bản mới.

### Snapshot nhất quán theo request

Mỗi request nên **đọc active một lần khi vào** và giữ đúng generation đó trong suốt thao tác:

```java
Generation current = active.get();
return current.plugin.handle(request);
```

Đây là snippet **chưa có lease/lifecycle safety**, chỉ mô tả nguyên tắc snapshot. Nếu một request đọc `active` nhiều lần trong các bước khác nhau, nó có thể dùng V1 ở bước đầu và V2 ở bước cuối; trạng thái, serialization hoặc giao dịch sẽ bị trộn thế hệ.

Nếu registry có nhiều trường độc lập `activePlugin`, `activeConfig`, `activeLoader`, việc gán từng trường riêng có nguy cơ reader thấy plugin V2 nhưng cấu hình V1. Đặt các thứ liên quan trong **một immutable Generation/Snapshot** và publish *một reference*.

### Nhiều writer: atomic pointer chưa đủ

Hai thread cùng deploy V2 và V3 có thể cạnh tranh. `getAndSet` vẫn atomic cho từng lần, nhưng nếu không có policy, V3 có thể bị V2 ghi đè sau khi V3 đã publish hoặc cleanup sai thứ tự. Hãy:

- **Tuần tự hóa các writer** bằng lock hoặc queue theo plugin ID; hoặc
- dùng `compareAndSet(expectedGeneration, candidate)` cùng state machine rõ ràng và quản lý candidate thua race.

Chỉ một thread/manager được quyết định generation nào hợp lệ để active. Trong hệ thống nhiều instance/cluster, `AtomicReference` **chỉ có tác dụng trong một JVM**; cần một control plane/rollout policy riêng nếu phải phối hợp nhiều process.

## 6. Không thể đóng V1 ngay sau khi gán active = V2

Giả sử request A đã nhận V1 và đang dùng socket, codec hoặc state của V1. Ngay lúc đó manager chuyển sang V2. Nếu gọi `V1.close()` lập tức, A có thể gặp:

- `IllegalStateException: closed` từ provider;
- lỗi socket/file/database connection đã bị thu hồi;
- callback/listener bị unregister giữa transaction;
- dữ liệu không nhất quán khi workflow của A tiếp tục đọc từ V2 qua global registry.

Mô hình đúng là **graceful retirement**:

1. Sau cutover, V1 không nhận thêm *lease mới* cho request được chấp nhận sau ranh giới.
2. Những request đã có lease của V1 được dùng chính V1 đến hết, theo giới hạn thời gian và policy lỗi.
3. Khi reference count về 0, owner mới gọi cleanup của V1 **một lần**.
4. Chỉ sau cleanup mới được bỏ các strong references tới loader/layer/resources của V1 để GC có cơ hội thu hồi.

### Lease/reference count

Có thể thiết kế:

```text
active -> V1
request A: acquire(V1) -> inFlight(V1)=1

prepare/validate(V2)
atomic active -> V2
retire(V1)          -> V1 không nhận lease mới
request B: acquire(V2) -> inFlight(V2)=1

request A: release(V1) -> inFlight(V1)=0 -> close(V1)
request B: release(V2) -> V2 tiếp tục ACTIVE
```

Phần khó là **race giữa lấy active và acquire lease**. Reader có thể đọc tham chiếu V1 trước cutover, nhưng chậm đến sau khi manager đã retire V1. Vì vậy code cần kiểm tra state dưới cùng cơ chế đồng bộ của generation, và có thể **recheck active** sau acquire để tránh chấp nhận một generation đã không còn được công bố.

Nếu hệ thống đòi **ranh giới tuyệt đối** “mọi tác vụ bắt đầu chạy *sau thời điểm switch* bắt buộc dùng V2”, kể cả những task đã cầm lease trước nhưng chưa vào method, atomic reference + recheck riêng lẻ không cho một thời điểm khóa hoàn toàn giữa check và invoke; cần định nghĩa rõ thời điểm *admission* hoặc dùng gate/read-write lock phù hợp. Phần lớn hệ thống chấp nhận request đã được admission trên V1 là *in-flight* và cho phép nó hoàn tất.

## 7. Ví dụ Java 17 chạy độc lập: validate → atomic switch → drain → cleanup

Ví dụ không cần plugin JAR thật, nhằm **cô lập và kiểm tra chính xác cơ chế chuyển generation**. `DemoPlugin` đóng vai implementation đã được tải bởi plugin manager. Trong ứng dụng thực, `prepare` sẽ xây loader/module layer, `ServiceLoader` và provider; phần `Registry` quản lý tham chiếu/lifecycle vẫn áp dụng.

Ví dụ có những đặc điểm:

- `Registry` công bố generation qua `AtomicReference<Generation>`; mọi thao tác thay thế được tuần tự hóa bằng `synchronized`.
- `DemoPlugin.checkReady()` từ chối candidate không đạt trước khi publish; candidate lỗi được đóng và V1 giữ nguyên.
- Request lấy `Lease`; `Generation` bảo vệ `leases`/`retired` bằng monitor, bảo đảm cleanup chỉ được claim một lần.
- Khi `replace` thành công, V2 nhận request mới; một request đã vào V1 được giữ lại bằng `CountDownLatch` để chứng minh V1 **không bị đóng sớm**.
- Khi request V1 release lease cuối, V1 mới đóng; `shutdown` sau đó đóng V2.

### 7.1. Mã nguồn: PluginGenerationDemo.java

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class PluginGenerationDemo {
    static final class DemoPlugin implements AutoCloseable {
        final String version;
        final CountDownLatch entered;
        final CountDownLatch resume;
        final boolean healthy;
        final AtomicBoolean closed = new AtomicBoolean();

        DemoPlugin(String version, CountDownLatch entered,
                   CountDownLatch resume, boolean healthy) {
            this.version = version;
            this.entered = entered;
            this.resume = resume;
            this.healthy = healthy;
        }

        void checkReady() {
            if (!healthy || !execute("probe").equals(version + ":probe")) {
                throw new IllegalStateException("health check failed: " + version);
            }
        }

        String execute(String input) {
            if ("hold".equals(input) && entered != null) {
                entered.countDown();
                try {
                    resume.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("interrupted", ex);
                }
            }
            if (closed.get()) throw new IllegalStateException("already closed: " + version);
            return version + ":" + input;
        }

        @Override
        public void close() { closed.set(true); }
    }

    static final class Generation {
        final DemoPlugin plugin;
        private int leases;
        private boolean retired;
        private boolean cleanupClaimed;

        Generation(DemoPlugin plugin) { this.plugin = plugin; }

        synchronized Lease tryAcquire() {
            if (retired) return null;
            leases++;
            return new Lease(this);
        }

        void release() {
            DemoPlugin cleanup;
            synchronized (this) {
                if (leases <= 0) throw new IllegalStateException("unbalanced lease");
                leases--;
                cleanup = claimCleanup();
            }
            if (cleanup != null) cleanup.close();
        }

        void retire() {
            DemoPlugin cleanup;
            synchronized (this) {
                retired = true;
                cleanup = claimCleanup();
            }
            if (cleanup != null) cleanup.close();
        }

        // Only call while holding this generation's monitor.
        private DemoPlugin claimCleanup() {
            if (retired && leases == 0 && !cleanupClaimed) {
                cleanupClaimed = true;
                return plugin;
            }
            return null;
        }
    }

    static final class Lease implements AutoCloseable {
        final Generation owner;
        private final AtomicBoolean done = new AtomicBoolean();

        Lease(Generation owner) { this.owner = owner; }

        @Override
        public void close() {
            if (done.compareAndSet(false, true)) owner.release();
        }
    }

    static final class Registry {
        private final AtomicReference<Generation> active;

        Registry(DemoPlugin initial) {
            initial.checkReady();
            active = new AtomicReference<>(new Generation(initial));
        }

        String invoke(String input) {
            for (;;) {
                Generation current = active.get();
                if (current == null) throw new IllegalStateException("registry closed");
                Lease lease = current.tryAcquire();
                if (lease == null) continue;
                if (active.get() != current) {
                    lease.close();
                    continue;
                }
                try (lease) {
                    return current.plugin.execute(input);
                }
            }
        }

        // Serializes all writers. The candidate is checked before publication.
        synchronized void replace(DemoPlugin candidate) {
            try {
                candidate.checkReady();
            } catch (RuntimeException failure) {
                candidate.close();
                throw failure;
            }
            if (active.get() == null) {
                candidate.close();
                throw new IllegalStateException("registry closed");
            }
            Generation previous = active.getAndSet(new Generation(candidate));
            previous.retire();
        }

        synchronized void shutdown() {
            Generation previous = active.getAndSet(null);
            if (previous != null) previous.retire();
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch resume = new CountDownLatch(1);
        DemoPlugin first = new DemoPlugin("v1", entered, resume, true);
        Registry registry = new Registry(first);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<String> inFlight = pool.submit(() -> registry.invoke("hold"));
            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("old call did not start");
            }

            DemoPlugin bad = new DemoPlugin("bad", null, null, false);
            try {
                registry.replace(bad);
                throw new AssertionError("invalid candidate accepted");
            } catch (IllegalStateException expected) {
                System.out.println("rejected=" + bad.closed.get());
            }
            System.out.println("afterReject=" + registry.invoke("check"));

            DemoPlugin next = new DemoPlugin("v2", null, null, true);
            registry.replace(next);
            System.out.println("afterSwap=" + registry.invoke("check"));
            System.out.println("oldClosedBeforeDrain=" + first.closed.get());

            resume.countDown();
            System.out.println("inFlight=" + inFlight.get(5, TimeUnit.SECONDS));
            System.out.println("oldClosedAfterDrain=" + first.closed.get());

            registry.shutdown();
            System.out.println("newClosedOnShutdown=" + next.closed.get());
        } finally {
            resume.countDown();
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
            registry.shutdown();
        }
    }
}
```

### 7.2. Chạy với Java 17

Lưu file là `PluginGenerationDemo.java`. Trong thư mục chứa file:

```bash
javac --release 17 PluginGenerationDemo.java
java PluginGenerationDemo
```

**Stdout đã kiểm chứng bằng `javac --release 17` và `java`:**

```text
rejected=true
afterReject=v1:check
afterSwap=v2:check
oldClosedBeforeDrain=false
inFlight=v1:hold
oldClosedAfterDrain=true
newClosedOnShutdown=true
```

### 7.3. Giải thích chi tiết các điểm đồng bộ

**Candidate lỗi không ảnh hưởng active.** `DemoPlugin("bad", ..., false)` bị `checkReady` từ chối, được `close`; `afterReject=v1:check` chứng tỏ `Registry` vẫn đang định tuyến tới V1. Ở production, cleanup candidate còn cần đóng class loader/resources mà nó sở hữu.

**Atomic cutover sau readiness.** `registry.replace(next)` kiểm tra V2 trước, sau đó mới `active.getAndSet(new Generation(next))`. Nhờ vậy `afterSwap=v2:check` trong khi request cũ vẫn giữ V1. `synchronized replace/shutdown` ngăn hai writer tranh nhau; các request không phải khóa toàn bộ registry cho mỗi lần gọi.

**Lease được bảo vệ theo generation.** `Generation.tryAcquire/release/retire` dùng cùng monitor để cập nhật `leases` và `retired`. Nếu V1 đã retired, nó từ chối lease mới. Nếu V1 chưa retired nhưng pointer đã đổi, `Registry.invoke` phát hiện `active.get() != current`, release lease vừa lấy rồi thử lại với thế hệ mới.

**Đóng đúng một lần.** `cleanupClaimed` được cập nhật dưới monitor trong `claimCleanup`; chỉ thread cuối claim thành công mới gọi `plugin.close()`. Trong ví dụ `close` chỉ set `AtomicBoolean`, không làm tác vụ chậm. Ở production cần log/cô lập lỗi close và chạy phần shutdown nặng bên ngoài lock để không kéo dài thời gian chờ của tác vụ khác.

**Request cũ được bảo toàn.** `CountDownLatch` bảo đảm request V1 đã chạy tới `execute("hold")` trước lúc cutover, rồi giữ lại. `oldClosedBeforeDrain=false` cho biết V1 chưa bị đóng. Khi mở latch, request V1 hoàn thành, `Lease.close` giảm count về 0 và V1 đóng; `oldClosedAfterDrain=true` kiểm chứng trạng thái đó.

**Shutdown tôn trọng drain.** `Registry.shutdown()` gỡ active pointer, đánh dấu V2 retired. Trong demo lúc này không còn request V2 đang chạy nên V2 đóng ngay. Nếu còn lease, theo cùng logic V2 sẽ chỉ đóng khi lease cuối release.

**Giới hạn đã chủ đích:** ví dụ sử dụng plugin in-process đơn giản, *không* triển khai JAR/module isolation, distributed rollout, timeout cho drain, persistent state migration hoặc recovery sau crash. `DemoPlugin.checkReady` được thiết kế không gây side effects; ứng dụng thật phải định nghĩa health probes an toàn riêng. `DemoPlugin` có hành vi thread-safe đơn giản trong phạm vi ví dụ; plugin tùy ý không tự trở nên thread-safe chỉ vì Registry có lease.

## 8. Race conditions quan trọng cần hiểu

### Race A — Reader lấy V1 trước switch nhưng acquire sau retire

```text
Request R                         Writer W
-------------------------------   ------------------------------
g = active.get() -> V1
                                  active.getAndSet(V2)
                                  V1.retire()
lease = V1.tryAcquire() -> null
R retry -> active.get() -> V2
```

Do V1 đã `retired`, request không được tạo lease mới cho V1; nó thử lại với V2.

### Race B — Reader acquire V1 ngay trước switch

```text
Request R                         Writer W
-------------------------------   ------------------------------
g = active.get() -> V1
lease = V1.tryAcquire() -> OK
                                  active.getAndSet(V2)
R thấy active.get() != g
R release V1; retry V2             V1.retire() / drain
```

**Recheck active** giảm nguy cơ request bị định tuyến nhầm generation cũ trong cửa sổ lấy reference → acquire. Nếu đã recheck thành công rồi writer mới switch, request đó được coi là đã được admission trên V1; nó giữ lease cho đến hết. Muốn tuyệt đối chặn cả trường hợp này, phải có cơ chế admission/switch mạnh hơn như gate hoặc read/write lock bao quanh điểm bắt đầu call.

### Race C — Last release và retire xảy ra đồng thời

```text
Request R                         Writer W
-------------------------------   ------------------------------
release(V1): leases từ 1 -> 0
                                  retire(V1): retired = true
         hoặc ngược thứ tự
Cả hai cập nhật dưới cùng monitor V1
=> chỉ một thread claim cleanup
=> close được gọi một lần
```

Nếu đếm in-flight bằng một `AtomicInteger` rồi tách biệt `retired` không có protocol rõ, có thể xảy ra close khi một thread vừa mới tăng lease. Sử dụng monitor/CAS state machine đúng, không cộng trừ counter tùy tiện.

### Race D — Người quản lý tiến hành hai bản thay thế cùng lúc

```text
Writer A: prepare V2
Writer B: prepare V3
Writer B: publish V3
Writer A: publish V2    (downgrade ngoài ý muốn)
```

`AtomicReference.getAndSet` **không ngăn tình huống nghiệp vụ này**. Demo khóa mọi writer bằng `synchronized`; hệ thống nhiều worker cần thêm version/sequence policy: chỉ publish candidate trên một expected generation hoặc một rollout epoch được phê duyệt. Với `compareAndSet` thất bại phải cleanup candidate chưa publish và báo conflict, không retry vô hạn trên version sai.

## 9. Khi candidate thất bại và khi active mới thất bại: hai chính sách khác nhau

| Thời điểm lỗi | Active đang phục vụ | Cách xử lý |
| --- | --- | --- |
| Tải artifact hoặc dựng loader V2 thất bại | V1 | Giữ V1; close phần V2 đã khởi tạo |
| Validation/health V2 không đạt | V1 | Reject V2, ghi diagnostics, giữ V1 |
| Writer tranh chấp và candidate mất quyền publish | Generation đã được writer khác chọn | Hủy candidate thua, không ghi đè |
| Publish V2 thành công, cleanup V1 lỗi | V2 | **Không** coi V2 chưa publish; log/quản lý retry cleanup V1 theo policy |
| V2 bắt đầu phục vụ rồi phát sinh lỗi hành vi | V2 (đã có request) | Điều tra, hạn chế traffic, cân nhắc rollback bằng generation hợp lệ |
| Process crash giữa các bước | Tùy thời điểm và restart policy | Phải có manifest/desired version và recovery độc lập với biến RAM |

**Lỗi sau cutover không thể được xử lý bằng câu “gán ngược con trỏ là rollback” một cách vô điều kiện.** Thế hệ V1 có thể đang retired, đã đóng tài nguyên hoặc không còn an toàn để tiếp tục. Nếu muốn rollback nhanh:

- có thể **giữ V1 ở trạng thái standby/rollback-ready** trong một khoảng thời gian, *chưa close*, với owner/lifecycle riêng, nhưng phải giới hạn resource và không cho request mới vào V1 nếu chưa được kích hoạt lại theo protocol;
- hoặc **prepare + validate một generation mới** từ artifact V1 đã biết tốt, rồi publish nó như một cutover bình thường;
- bảo đảm V1 vẫn tương thích với database schema, dữ liệu hoặc messages đã được V2 ghi. Rollback code **không tự rollback dữ liệu**.

Nếu V2 đã phát sinh external side effects (giao dịch, gửi event, gọi API khác), việc gỡ pointer V2 không hoàn tác các tác động đó. Cần transaction, idempotency, compensation hoặc kế hoạch migration dữ liệu phù hợp.

## 10. Phiên bản dữ liệu, session dài và hành vi xuyên thế hệ

Đối với plugin stateless đơn giản, request-scoped lease thường đủ. Nhưng nhiều plugin lưu session hoặc state qua request:

- user session được tạo bởi V1 nhưng request tiếp theo được route sang V2;
- token, cache, serialized payload hoặc database record do V2 tạo không được V1 đọc;
- workflow nhiều bước cần cùng version của policy/schema;
- queue message được bắt đầu xử lý ở V1 nhưng callback async hoàn thành sau cutover.

Khi đó cần định nghĩa **scope** của việc giữ generation:

| Trường hợp | Gợi ý |
| --- | --- |
| Request HTTP độc lập, stateless | Lease theo request |
| Stateful session | Pin session vào generation hoặc migration có version |
| Job chạy lâu / async callback | Lease theo toàn bộ job, kể cả callback và completion |
| Streaming connection | Lease trong thời gian stream sống; timeout/drain riêng |
| Scheduled task do plugin tự tạo | Task gắn owner generation, phải stop/join khi retire |
| Transaction nhiều bước | Pin cùng generation trong transaction hoặc thiết kế compatibility protocol |

Không “đọc lại `active` ở mỗi phương thức” trong một workflow stateful. Hãy truyền snapshot/lease xuống các tầng xử lý để nó chỉ dùng một thế hệ đã được chọn.

### State migration và compatibility

Nếu V2 phải kế thừa state từ V1, chọn một quy trình rõ:

- **Externalized state:** state nằm trong datastore với schema/version chung, mỗi generation dùng adapter tương thích; thường dễ cutover hơn.
- **Snapshot/restore:** lấy state V1 ở điểm nhất quán, validate V2 đọc được; có thể cần tạm dừng ghi/cấp request và thời gian cutover không còn hoàn toàn zero-downtime.
- **Dual read/dual write hoặc versioned data:** cần logic migration, reconciliation và rollback riêng; rủi ro tăng nếu hai generation hoạt động song song.
- **Session stickiness:** giữ V1 cho session cũ đến khi hết hạn, route session mới vào V2; phải dự toán tối đa thời gian giữ loader/tài nguyên.

**Atomic pointer chỉ giải quyết route generation**, không đảm bảo state transition nguyên tử ở hệ thống lưu trữ ngoài. Cần xác định trước compatibility window, migration order, rollback cutoff và hành vi khi còn state V1 chưa di chuyển.

## 11. Gắn với Java plugin loader thật: API chung, implementation cách ly

Trong ứng dụng Java, host nên định nghĩa interface dịch vụ/plugin trong class loader chung và chỉ cung cấp API ổn định cho plugin. Một pipeline khái niệm:

```text
Host interface (parent loader)
          ^
          | implements
Plugin V1 implementation (loader L1)
Plugin V2 implementation (loader L2)

PluginManager:
  prepare V2 -> create L2 -> discover provider -> validate
  publish Generation(V2, L2)
  retire V1 -> drain -> close provider/resources/L1
```

Ví dụ dựng candidate với classpath SPI thường có dạng **snippet**:

```java
URLClassLoader candidateLoader = new URLClassLoader(
        new URL[] {pluginJar.toUri().toURL()},
        PluginApi.class.getClassLoader());

ServiceLoader<PluginApi> discovery =
        ServiceLoader.load(PluginApi.class, candidateLoader);

List<PluginApi> found = new ArrayList<>();
for (PluginApi provider : discovery) {
    found.add(provider);
}
// Chọn provider theo plugin ID/version/capabilities; validate trước publish.
// Candidate owner phải đóng loader và provider resources nếu bị reject.
```

Đoạn trên cần `PluginApi`, `pluginJar` đã được định nghĩa và imports `URLClassLoader`, `URL`, `ServiceLoader`, `ArrayList`, `List`; **không phải chương trình chạy độc lập**. JAR plugin cần có metadata SPI `META-INF/services/<fully-qualified-API-name>` khi dùng classpath; với named modules có `provides`/`uses` và `ModuleLayer`. `ServiceLoader` không phải bộ quản lý thế hệ; nó chỉ giúp discovery. Không dùng chung một instance `ServiceLoader` cho các thread đồng thời khi reload/discover.

### Nguy cơ parent-first và class identity

- Loader V2 có thể vẫn lấy class/resource từ loader cha nếu trùng tên do parent-first. Cần cô lập implementation namespace và kiểm thử việc chọn đúng artifact.
- `PluginApi` không được có một bản được nạp bởi parent và một bản riêng ở child mà rồi bị cast chéo. Host API nên thuộc shared parent, implementation thuộc plugin loader.
- Với module layer, cần kiểm tra ModuleFinder, `Configuration.resolve/resolveAndBind` và class loader mapping; `ModuleLayer` mới không tự thay layer cũ.
- `ClassLoader`/`ModuleLayer` có thể giữ class/metadata đến khi không còn tham chiếu; hot swap theo thế hệ không phải class redefinition.

### Cleanup loader, provider và tài nguyên ngoài JVM

Một owner thực tế thường phải quản lý:

1. Ngừng nhận job/timer/callback mới cho V1, dừng scheduling và unregister event listeners.
2. Chờ in-flight task, stream và async callback hoàn tất hoặc hết deadline.
3. `close()` provider theo contract; flush/rollback tài nguyên còn sở hữu, đóng DB/network clients đúng cách.
4. Shutdown/join executor mà plugin tạo; dọn `ThreadLocal`, TCCL và các references giữ plugin class loader.
5. Unregister MBean, JDBC driver, registry hoặc cache liên quan, nếu plugin đã đăng ký.
6. Đóng `URLClassLoader` khi đã hết hoạt động cần các tài nguyên do nó quản lý. `close()` **không đảm bảo unload ngay những class đã nạp**.
7. Bỏ strong references của host tới plugin instances, loader, reflection `Method`, `Class`, lambdas, caches hoặc thread.
8. Theo dõi heap/metaspace/class unloading và close failures; không “nuốt” lỗi cleanup khiến generation lỗi tồn tại vĩnh viễn.

Tránh tạo thread nền sống vô hạn với context class loader của V1: ngay cả khi registry đã bỏ pointer V1, thread còn sống có thể giữ loader cũ. Tương tự, callback đăng ký trong một singleton host có thể giữ object plugin qua listener reference.

## 12. Cutover và cleanup không nên nằm chung một failure boundary

Một thiết kế production nên phân biệt **thời điểm đã commit cutover** với các bước cleanup diễn ra sau đó. Ví dụ:

```text
prepare V2 ──> validate V2 ──> atomic publish V2
     |               |                  |
     | FAIL          | FAIL             | SUCCESS (committed)
     v               v                  v
  close V2         close V2          schedule retire/drain V1
  V1 active        V1 active         V2 active
                                          |
                                  close V1 có thể fail
                                          |
                                  record / retry cleanup
                                  KHÔNG tự coi publish đã hủy
```

Nếu `old.retire()` đồng bộ và `close()` của plugin cũ ném exception sau `getAndSet`, method thay thế có thể trả lỗi cho caller dù V2 **đã active**. Code gọi bên ngoài không nên hiểu exception đó là “V2 chưa lên”. Hợp đồng tốt hơn là phân tách kết quả cutover với trạng thái cleanup, hoặc cho cleanup chạy bất đồng bộ theo policy và có log/metrics rõ ràng.

Trong ví dụ phần 7, `DemoPlugin.close()` chỉ set boolean và không ném lỗi; vì vậy luồng chính minh họa logic cutover một cách gọn. Với plugin tùy ý phải cô lập exception của close và đảm bảo shutdown không gọi code tùy ý dưới monitor đang bảo vệ state.

### Đóng tài nguyên cũ trong thời hạn bao lâu?

Có hai chính sách chính:

- **Graceful drain không giới hạn:** tránh cắt request nhưng có nguy cơ giữ class loader/connection V1 vô thời hạn nếu request treo.
- **Graceful drain có deadline:** đợi một khoảng được cấu hình; sau đó cancel/cooperative stop hoặc cô lập process. Trong cùng JVM, không có cách an toàn tổng quát để cưỡng bức kill mọi thread đang chạy plugin Java. Nếu vẫn còn request sử dụng tài nguyên thì gọi close cưỡng bức có thể gây lỗi; phải quy định rủi ro này và cách xử lý.

Khi cần deadline cứng cho plugin không tin cậy, cân nhắc chạy mỗi thế hệ trong **worker process** riêng: route request mới tới process V2, chờ V1 drain, sau hạn có thể terminate process V1 bằng cơ chế OS. Process boundary giúp giới hạn CPU/RAM/IO và tách crash, nhưng còn cần quản lý idempotency và external side effects.

## 13. Quan sát và kiểm thử để tin được một quy trình nâng phiên bản

Các metric/log hữu ích nên gắn ít nhất `pluginId` và `generationId`:

- Thời gian `prepare`, `validate`, warm-up, cutover, drain và cleanup.
- Candidate rejected count, lý do invalid, artifact hash/version, provider ID.
- Active generation hiện tại, phiên bản yêu cầu/đang chạy và số lần rollout conflict.
- In-flight leases theo generation, age của request cũ, số generation đang RETIRING.
- Exception/error rate, latency và chất lượng đầu ra của V1 so với V2 sau cutover.
- Số executor/thread còn sống, connection/file descriptor, heap/metaspace sau khi close.
- Rollback count và lý do, chênh lệch state/schema, cache migration errors.

**Đừng log secrets, token, dữ liệu khách hàng hoặc mã plugin nhạy cảm** chỉ để debug. Audit event cần trả lời được *ai yêu cầu*, *artifact nào được validate*, *generation nào đã publish*, *khi nào được retired*, *cleanup có hoàn tất hay không*.

### Bộ kiểm thử tối thiểu

| Test | Điều phải chứng minh |
| --- | --- |
| Prepare thất bại | V1 vẫn active, candidate được close, không có partial publish |
| Contract/health fail | Không đổi active pointer; không làm request cũ lỗi |
| Cutover thành công | Request mới thấy V2 nhất quán; không thấy nửa V1/nửa V2 |
| Request V1 còn chạy | V1 chưa đóng khi lease > 0; request hoàn thành bằng V1 |
| Last release vs retire | Cleanup chỉ một lần dù interleaving khác nhau |
| Acquire trước/sau cutover | Không cấp lease mới cho retired generation; logic retry hoạt động |
| Hai writer cạnh tranh | Có serialize/CAS/version policy; không downgrade trái phép |
| Shutdown đồng thời request | Request mới bị từ chối, request đã lease được drain đúng policy |
| Plugin giữ background thread/listener | Cleanup thực sự unregister/stop và bỏ references |
| Cleanup V1 ném exception | V2 vẫn được ghi nhận là active; lỗi cleanup được theo dõi |
| Rollback sau cutover | Không tái dùng generation đã CLOSED; state/schema tương thích |
| Class loader isolation | Không trùng API identity, artifact/version đúng, loader cũ có thể được GC |
| Async/stream/session | Lease bao phủ toàn bộ vòng đời, không giải phóng quá sớm |
| Nhiều lần nâng nhanh | Không tích lũy generation RETIRING hoặc resource leak |

**Đừng chỉ test bằng `Thread.sleep` tùy ý.** Dùng `CountDownLatch`, `CyclicBarrier`, `Phaser` hoặc điều phối kiểm thử có rào đồng bộ để tạo đúng interleaving; ví dụ phần 7 dùng latch cho biết request cũ đã bước vào plugin trước khi cutover.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gỡ hoặc đóng plugin V1 **trước** khi validate V2 | V2 lỗi làm mất dịch vụ | Prepare và validate candidate độc lập, V1 vẫn active |
| Thay `activePlugin` rồi thay `activeConfig`, `activeLoader` lần lượt | Request thấy dữ liệu lẫn hai phiên bản | Publish một immutable generation/snapshot |
| `active = newPlugin` trên biến thường không có đồng bộ | Không bảo đảm visibility/publication thích hợp | `AtomicReference`, `volatile` hoặc lock theo JMM |
| Atomic switch rồi close V1 ngay | Request cũ vẫn sử dụng V1 gặp lỗi | Retire, chặn lease mới, drain rồi mới close |
| Chỉ đọc active nhưng không giữ lease | Cleanup race với request | Admission + lease gắn request/job |
| Đếm active request không có protocol với retire | Race khiến close sớm hoặc đóng hai lần | Monitor/CAS state machine chung |
| Đọc lại active giữa nhiều bước xử lý | Một request trộn V1/V2 | Pin generation theo scope công việc |
| Tạo V2 bằng cùng loader cũ rồi kỳ vọng class thay đổi | Java tiếp tục dùng class definition cũ | Loader/layer mới khi cần version mới |
| Gọi `ServiceLoader.reload()` và cho rằng đã hot swap | Cache discovery được xóa, không đổi tất cả references/layer | Dựng generation mới, atomic publish |
| Gán ngược pointer V1 đã CLOSED để rollback | Gọi vào object/tài nguyên đã dọn | Giữ rollback-ready có ownership hoặc tái dựng V1 thành generation mới |
| Bỏ qua class identity và static cache | `ClassCastException`/metaspace leak | Shared API parent, cô lập plugin code và dọn strong references |
| Candidate health test có side effect thật | Chưa publish đã tạo tác động ngoài | Dùng test/probe vô hại hoặc transaction/cô lập |
| Cleanup lỗi làm method báo publish thất bại | Caller retry và có thể deploy lặp | Phân biệt cutover commit với lỗi cleanup |
| Không giới hạn drain | V1 giữ thread/socket/metaspace mãi | Deadline, monitoring, cooperative cancel hoặc process isolation |
| Coi plugin chạy trong class loader là sandbox | Plugin vẫn có thể truy cập quyền của JVM | Trust validation, least privilege, process boundary nếu không tin cậy |

## 15. Checklist triển khai từng bước

**Trước prepare**

- [ ] Chốt hợp đồng `PluginApi`, version/capability và namespace được host sở hữu.
- [ ] Xác định class loader/module layer riêng của mỗi thế hệ khi cần; bảo đảm host/plugin chia sẻ đúng interface.
- [ ] Chỉ tải artifact từ nguồn được phê duyệt, verify checksum/chữ ký, compatibility và dependency graph.
- [ ] Chỉ rõ resource owner và scope cho executor, connection, listener, cache, file/class loader.

**Prepare và validate**

- [ ] Dựng V2 hoàn chỉnh nhưng chưa publish; giữ V1 tiếp tục phục vụ.
- [ ] Thực hiện readiness/contract checks và warm-up không làm thay đổi dữ liệu production ngoài ý muốn.
- [ ] Candidate lỗi phải được close/quarantine mà active pointer không đổi.
- [ ] Version/schema/state compatibility phải được phê duyệt trước cutover.

**Cutover**

- [ ] Mỗi plugin có một writer policy: lock hoặc CAS với expected generation/version.
- [ ] Gộp plugin instance + config + routing + loader reference thành một generation/snapshot bất biến.
- [ ] Publish đúng một `AtomicReference`/volatile pointer **sau** khi validate xong.
- [ ] Request đọc và pin generation, acquire lease, tránh đọc active lại tùy tiện giữa workflow.
- [ ] Xác định chính xác “đã nhận request” tại thời điểm admission nào để đánh giá concurrency đúng.

**Retire và hậu kiểm**

- [ ] Ngừng nhận tác vụ mới cho V1, drain tất cả request/job/stream/session đang sở hữu V1.
- [ ] Cleanup V1 chỉ một lần sau khi hết lease; không đóng class loader/tài nguyên còn được dùng.
- [ ] Có deadline, logs, metrics và recovery khi drain/close thất bại.
- [ ] Rollback không tái sử dụng generation đã CLOSED; kiểm tra state/data compatibility.
- [ ] Kiểm tra threads, context class loader, static caches, registrations và class unloading sau nhiều lần nâng.
- [ ] Test interleavings của prepare-fail, concurrent writers, cutover, last-release, shutdown, rollback.

### Tài liệu Java 17 liên quan

- [`AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [`AutoCloseable` và try-with-resources](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`URLClassLoader.close()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [`CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Kết luận:** một cơ chế thay thế plugin đáng tin cậy phải **dựng và kiểm tra candidate trước**, sau đó **công bố atomically một tham chiếu active** tới generation mới, rồi mới **retire và drain** thế hệ cũ. Atomic switch bảo đảm reader chọn snapshot nhất quán; lease và lifecycle bảo đảm không đóng tài nguyên quá sớm. Rollback, state migration, class loader unloading và tác động bên ngoài là các trách nhiệm tách biệt cần được thiết kế rõ, không được suy ra chỉ từ một phép gán tham chiếu.