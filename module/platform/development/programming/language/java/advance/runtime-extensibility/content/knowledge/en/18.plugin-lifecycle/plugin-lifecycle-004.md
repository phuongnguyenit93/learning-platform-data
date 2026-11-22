# Khởi tạo theo thứ tự phụ thuộc và hoàn tác khi chỉ một phần thành công

## 1. Bài toán của vòng đời plugin

Trong host hỗ trợ nhiều plugin, một plugin có thể cần service do plugin khác cung cấp. Ví dụ `storage` tạo kho lưu trữ, `cache` cần `storage`, còn `report` cần cả `cache` và `storage`. Nếu host gọi `start()` tùy ý, `report` có thể khởi động trước khi dependency sẵn sàng. Ngược lại, nếu plugin thứ ba thất bại sau khi hai plugin đầu đã mở file, socket hoặc thread, host phải **hoàn tác những phần đã khởi tạo thành công**, tránh trạng thái nửa vời.

Thiết kế đúng cần giải quyết ba vấn đề khác nhau:

1. **Dependency graph:** các plugin bắt buộc phải chạy trước plugin nào?
2. **Lifecycle transaction:** những bước nào đã thành công, và rollback chúng theo thứ tự nào?
3. **Failure semantics:** khi khởi tạo hoặc dọn dẹp lỗi, host báo nguyên nhân và giữ trạng thái nhất quán ra sao?

Không có transaction phân tán tự động cho plugin: `start()` có thể tạo side effect không đảo ngược được, nên rollback là **compensating action** dựa trên hợp đồng `stop()`/`close()` và tài nguyên thực tế.

## 2. Mô hình phụ thuộc: đồ thị có hướng không chu trình

Gọi mỗi plugin là một đỉnh. Với quan hệ `report -> cache`, nghĩa là **report phụ thuộc cache**, nên cache phải hoàn tất trước khi report bắt đầu. Một thứ tự hợp lệ cho ví dụ:

```text
storage  ---> cache  ---> report
    \___________________^
```

Ở đây mũi tên có nghĩa “phải khởi tạo trước”: `storage → cache`, `storage → report`, `cache → report`.

### 2.1. Topological sorting

Với DAG (Directed Acyclic Graph), sắp xếp topo trả về thứ tự sao cho mọi dependency đứng trước plugin phụ thuộc. Có thể dùng DFS kết hợp màu `WHITE/GRAY/BLACK` hoặc thuật toán Kahn với indegree.

Điều kiện cần kiểm tra **trước khi gọi `start()`**:

- Plugin ID duy nhất, không trùng registry.
- Mọi dependency bắt buộc tồn tại và version/contract tương thích.
- Không có chu trình (`A` cần `B` và `B` cần `A`, kể cả chu trình dài).
- Chính sách plugin optional rõ ràng: thiếu optional dependency có được phép bỏ qua không?
- Thứ tự giữa các plugin độc lập được xác định khi cần kết quả ổn định (ví dụ so theo ID).

Nếu graph chứa cycle, không thể tìm thứ tự topo; host nên dừng trước khi tạo bất kỳ resource nào. Không nên cố “khởi chạy thử” rồi xử lý lỗi vì phụ thuộc vòng.

### 2.2. Cài đặt kiểm tra version và capability

Chỉ kiểm tra dependency ID thường chưa đủ. Một provider có thể yêu cầu `storage-api` version 2 hoặc một capability cụ thể. Host phải xác minh yêu cầu ngay ở giai đoạn resolution (trước activation) và cung cấp **một bản contract API** thống nhất giữa các class loader; nếu không, plugin có thể khởi động xong nhưng thất bại ở lần gọi service đầu tiên.

## 3. Máy trạng thái lifecycle

Một mô hình hữu ích:

```text
DISCOVERED -> RESOLVED -> STARTING -> ACTIVE -> STOPPING -> STOPPED
                              |                     |
                              v                     v
                            FAILED              STOP_FAILED
```

`DISCOVERED` nghĩa metadata/JAR được nhìn thấy; `RESOLVED` nghĩa phụ thuộc phù hợp; `STARTING` cho phép khởi tạo; `ACTIVE` nghĩa start thành công; `STOPPING`/`STOPPED` là giải phóng. Tên trạng thái tùy hệ thống, nhưng host phải phân biệt **bắt đầu khởi tạo** với **đã hoạt động đầy đủ**.

**Quan trọng:** nếu `start()` tạo một số resource rồi ném exception, plugin đó chưa được ghi là ACTIVE. Tuy vậy nó vẫn sở hữu tài nguyên một phần và cần dọn dẹp. Vì thế `start()` nên hoặc tự dọn toàn bộ tài nguyên nó đã cấp phát trước khi ném lỗi, hoặc host cần một cơ chế `abortStart()`/`close()` an toàn cho đối tượng chưa khởi tạo xong.

## 4. Nguyên tắc rollback

Giả sử thứ tự activation là:

```text
start storage : OK
start cache   : OK
start report  : FAIL
```

Host phải dừng các plugin đã active theo thứ tự **ngược**:

```text
stop cache
stop storage
```

Không nên gọi `stop storage` trước `stop cache`, vì cache có thể vẫn cần storage để flush hoặc ghi trạng thái lúc shutdown. Một stack các plugin đã start thành công là cấu trúc tự nhiên cho rollback LIFO.

Để giữ nguyên nhân ban đầu, khi cleanup cũng thất bại:

- Giữ exception do `start report` làm **primary failure**.
- Đính các lỗi cleanup bằng `Throwable.addSuppressed(...)` hoặc báo theo cấu trúc tương đương.
- Tiếp tục cleanup các plugin còn lại dù một `stop()` gặp lỗi; không được dừng rollback ở lỗi đầu tiên.
- Chỉ đánh dấu `STOPPED` khi cleanup đạt trạng thái mong muốn; không nói rollback “thành công toàn bộ” khi tài nguyên có thể vẫn đang hoạt động.

## 5. Ví dụ Java 17+ chạy độc lập: topo + rollback LIFO

Ví dụ dưới đây dùng interface `Plugin` đơn giản, metadata dependency là `List<String>`, không cần framework. Plugin `report` được cố tình làm thất bại để thấy rollback hoạt động.

Tạo file **`PluginLifecycleDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class PluginLifecycleDemo {
    interface Plugin {
        String id();
        List<String> dependencies();
        void start();
        void stop();
    }

    static final class DemoPlugin implements Plugin {
        private final String id;
        private final List<String> deps;
        private final boolean failStart;

        DemoPlugin(String id, List<String> deps, boolean failStart) {
            this.id = id;
            this.deps = List.copyOf(deps);
            this.failStart = failStart;
        }

        public String id() { return id; }
        public List<String> dependencies() { return deps; }

        public void start() {
            System.out.println("start " + id);
            if (failStart) throw new IllegalStateException("failure in " + id);
        }

        public void stop() {
            System.out.println("stop " + id);
        }
    }

    static List<Plugin> topologicalOrder(List<Plugin> plugins) {
        Map<String, Plugin> registry = new HashMap<>();
        for (Plugin p : plugins) {
            if (registry.putIfAbsent(p.id(), p) != null) {
                throw new IllegalArgumentException("Duplicate ID: " + p.id());
            }
        }

        List<Plugin> order = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        Set<String> visiting = new HashSet<>();

        for (String id : registry.keySet().stream().sorted().toList()) {
            visit(id, registry, visited, visiting, order);
        }
        return order;
    }

    static void visit(String id, Map<String, Plugin> registry,
                      Set<String> visited, Set<String> visiting,
                      List<Plugin> order) {
        if (visited.contains(id)) return;
        Plugin p = registry.get(id);
        if (p == null) throw new IllegalArgumentException("Missing: " + id);
        if (!visiting.add(id)) {
            throw new IllegalArgumentException("Dependency cycle at " + id);
        }

        for (String dep : p.dependencies().stream().sorted().toList()) {
            visit(dep, registry, visited, visiting, order);
        }
        visiting.remove(id);
        visited.add(id);
        order.add(p);
    }

    static void startAll(List<Plugin> plugins) {
        List<Plugin> ordered = topologicalOrder(plugins);
        Deque<Plugin> started = new ArrayDeque<>();
        try {
            for (Plugin p : ordered) {
                p.start();
                started.push(p);
            }
            System.out.println("all active");
        } catch (RuntimeException failure) {
            System.out.println("startup failed: " + failure.getMessage());
            while (!started.isEmpty()) {
                Plugin p = started.pop();
                try {
                    p.stop();
                } catch (RuntimeException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            throw failure;
        }
    }

    public static void main(String[] args) {
        List<Plugin> plugins = List.of(
            new DemoPlugin("report", List.of("cache", "storage"), true),
            new DemoPlugin("storage", List.of(), false),
            new DemoPlugin("cache", List.of("storage"), false)
        );

        try {
            startAll(plugins);
        } catch (RuntimeException ex) {
            System.out.println("caught: " + ex.getMessage());
            System.out.println("suppressed: " + ex.getSuppressed().length);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PluginLifecycleDemo.java
java PluginLifecycleDemo
```

**Stdout chính xác**:

```text
start storage
start cache
start report
startup failed: failure in report
stop cache
stop storage
caught: failure in report
suppressed: 0
```

Giải thích: `topologicalOrder` yêu cầu `storage` trước `cache`, sau đó đến `report`, bất kể thứ tự khai báo input. `started.push(p)` **chỉ được gọi sau khi `start()` trả về thành công**. Khi `report.start()` ném lỗi, rollback chỉ chứa `cache` và `storage`, nên dừng đúng thứ tự ngược.

### Giới hạn có chủ ý của ví dụ

Ví dụ này giả định `start()` của plugin thất bại sẽ **tự dọn những tài nguyên được cấp phát dở** trước khi ném exception. Đây là hợp đồng cần được quy định rõ. Nếu plugin không thể đảm bảo điều đó, host phải gọi cleanup cho plugin đang fail hoặc cung cấp cơ chế transactional resource scope riêng; không thể chỉ dừng những plugin đã nằm trong `started`.

Các `stop()` trong demo không ném lỗi, nên suppressed count là 0. Trong production, rollback phải xử lý cả checked exceptions, `Error` khi phù hợp và những thao tác cleanup cần timeout. Không nên dùng một `catch(Throwable)` chung một cách mù quáng rồi tiếp tục chạy ở trạng thái JVM có thể đã hỏng.

## 6. Xử lý partial initialization bên trong từng plugin

Giả sử `report.start()` thực hiện ba bước: tạo client mạng, mở cache và đăng ký listener. Nếu bước đăng ký listener thất bại, client và cache đã được tạo cần được giải phóng.

Thiết kế một plugin tự dọn trước khi báo lỗi:

```java
final class ReportPlugin {
    private java.net.http.HttpClient client;
    private AutoCloseable subscription;

    void start() throws Exception {
        AutoCloseable newSubscription = null;
        try {
            client = java.net.http.HttpClient.newHttpClient();
            newSubscription = registerListener();
            subscription = newSubscription;
        } catch (Exception ex) {
            if (newSubscription != null) {
                try { newSubscription.close(); }
                catch (Exception cleanup) { ex.addSuppressed(cleanup); }
            }
            client = null;
            throw ex;
        }
    }

    AutoCloseable registerListener() {
        return () -> {};
    }

    void stop() throws Exception {
        if (subscription != null) {
            subscription.close();
            subscription = null;
        }
        client = null;
    }
}
```

**Đoạn minh họa**, chưa phải ứng dụng độc lập: `HttpClient` ở đây chỉ nhằm mô phỏng dependency tạo trước; trên Java 17, không nên khẳng định `HttpClient` tự đóng bằng `close()` như `AutoCloseable` của các phiên bản Java mới. Trong ví dụ này `client = null` chỉ bỏ tham chiếu; nếu tài nguyên thật cần đóng, phải dùng API close/stop đúng của tài nguyên đó. `registerListener()` minh họa subscription có `AutoCloseable`.

Thay vì rải cleanup logic qua nhiều field, có thể dùng `Deque<AutoCloseable>` trong `start()`: mỗi lần tạo xong resource thì push một hành động cleanup; khi bất kỳ bước nào lỗi, pop và close tất cả. Mẫu này cho phép rollback cục bộ theo thứ tự ngược và tái sử dụng cho `stop()`.

## 7. Resource scope và shutdown theo thứ tự phụ thuộc

Một mẫu thiết kế ở tầng host là ghi nhận các resource đã được cấp phát thành công:

```java
Deque<AutoCloseable> undo = new ArrayDeque<>();
try {
    AutoCloseable db = openDatabase();
    undo.push(db);
    AutoCloseable listener = registerListener(db);
    undo.push(listener);
    // Hoàn tất initialization: chuyển quyền sở hữu undo cho lifecycle manager.
} catch (Exception ex) {
    while (!undo.isEmpty()) {
        try { undo.pop().close(); }
        catch (Exception cleanup) { ex.addSuppressed(cleanup); }
    }
    throw ex;
}
```

Đoạn này **chỉ minh họa** vì `openDatabase()` và `registerListener(...)` là API giả định, không độc lập. Ý chính: *đăng ký hành động hoàn tác ngay sau khi mỗi bước thành công*, không chờ tới cuối mới tạo danh sách tài nguyên. Khi initialization thành công, owner của resource phải chuyển rõ ràng sang lifecycle manager; không được tự động đóng chúng ở cuối scope như một lỗi thiết kế.

Với nhiều plugin, thứ tự dừng toàn hệ thống là thứ tự ngược của topo order: dependent trước, dependency sau. Tuy nhiên shutdown không chỉ là `stop()`; còn có thể cần quiesce request, từ chối task mới, drain queues, flush dữ liệu, chờ thread hoàn thành rồi giải phóng external resources.

## 8. Khi một plugin cần nhiều dependency cùng lúc

Một plugin có thể phụ thuộc nhiều service, ví dụ:

```text
billing -> storage
billing -> audit
audit   -> storage
```

Topo hợp lệ: `storage`, `audit`, `billing`. Nếu `audit` bị lỗi, không nên chạy `billing`. Nếu `billing` lỗi, rollback `audit` trước `storage`.

Điều kiện version/capability nên được kiểm tra trước `startAll`. Nếu plugin là optional, host phải xác định có thể bỏ qua nó và những dependent nào cũng phải bị disable, thay vì để service thiếu xuất hiện ở runtime.

### Parallel startup?

Trong DAG, các plugin độc lập về phụ thuộc có thể được khởi tạo song song, nhưng rollback lúc này phức tạp hơn vì thứ tự hoàn thành không đồng nhất thứ tự topo. Cần xác định các plugin đã start thành công, chờ/cancel công việc đang start, rồi dừng theo quan hệ phụ thuộc. Chỉ triển khai parallel startup khi có nhu cầu rõ ràng và đã có lifecycle coordinator xử lý race, timeout và failure aggregation.

## 9. Idempotency, retry và rollback thất bại

Một `start()` tốt nên có hợp đồng rõ về việc gọi nhiều lần. Không tự động giả định idempotent; host cần state machine cấm hai `start()` đồng thời trên cùng instance. `stop()` nên an toàn khi gọi trong trạng thái đã stopped hoặc start thất bại nếu kiến trúc yêu cầu cleanup lặp, nhưng vẫn phải ghi rõ lỗi không thể phục hồi.

Phân biệt:

- **Retry**: thử lại initialization sau khi nguyên nhân tạm thời được khắc phục.
- **Rollback**: giải phóng side effect của những bước đã thành công.
- **Recovery**: đưa hệ thống về trạng thái có thể nhận lượt start mới.

Không nên retry bằng chính instance đã thất bại nếu nó giữ state dở dang. Cân nhắc tạo instance mới sau cleanup, bảo đảm tài nguyên cũ đã bị đóng và dependency vẫn ở trạng thái ACTIVE.

Khi rollback bị lỗi, host phải giữ dấu vết `FAILED_CLEANUP` hoặc trạng thái tương đương. Trạng thái `STOPPED` chỉ nên dùng khi đã biết tài nguyên được giải phóng đủ theo contract. Nếu resource là transaction ngoài (DB, message broker, filesystem), compensation có thể không đảo ngược hoàn toàn side effect; cần idempotency key hoặc thao tác bù cụ thể.

## 10. Monitoring và log vòng đời

Để chẩn đoán lỗi production, mỗi plugin activation nên ghi:

- Plugin ID, version, API version và dependent IDs.
- Thời gian bắt đầu/kết thúc từng `start` và `stop`.
- Dependency path tới plugin bị fail.
- Nguyên nhân chính và suppressed cleanup errors.
- Trạng thái cuối sau rollback, resource chưa chắc đã giải phóng.

Ví dụ log có cấu trúc (minh họa):

```text
event=plugin_start id=storage status=SUCCESS
event=plugin_start id=cache status=SUCCESS
event=plugin_start id=report status=FAILED reason=CONFIG
event=plugin_stop id=cache status=SUCCESS rollback=true
event=plugin_stop id=storage status=SUCCESS rollback=true
```

Không log credential, token, URL chứa secret hoặc full configuration của plugin. Với tài nguyên nhạy cảm, dùng định danh an toàn và telemetry có giới hạn.

## 11. Các lỗi phổ biến

| Lỗi | Tác hại | Cách khắc phục |
|---|---|---|
| Khởi chạy theo thứ tự JAR được quét | Dependent có thể chạy trước dependency | Topological sort với dependency metadata |
| Không phát hiện cycle trước khi start | Deadlock/log lỗi muộn | Validate graph và báo cycle rõ ràng |
| Ghi plugin vào stack trước khi `start()` xong | Rollback gọi `stop` trên instance chưa sẵn sàng | Chỉ push sau success; xử lý partial-start riêng |
| Không rollback khi plugin thứ ba lỗi | Leak resource của plugin đã active | Rollback reverse order |
| Rollback dừng ngay khi một `stop()` lỗi | Các plugin còn lại không được cleanup | Tiếp tục cleanup, addSuppressed |
| Bắt exception rồi tiếp tục phục vụ | Hệ thống ở trạng thái thiếu service | Fail startup hoặc degrade theo policy có kiểm soát |
| Dùng lại instance start lỗi để retry | State dở dang, tài nguyên cũ còn sót | Cleanup, tạo instance mới hoặc cơ chế reset chính thức |
| Gọi `stop()` không theo dependency | Dependency bị đóng khi dependent còn dùng | Shutdown reverse topological order |

## 12. Checklist trước khi phát hành plugin host

- [ ] Plugin metadata mô tả ID, version và dependency bắt buộc/optional.
- [ ] Host validate missing IDs, duplicate IDs, cycles và API compatibility trước activation.
- [ ] Thứ tự start topo có kết quả ổn định khi nhiều plugin độc lập.
- [ ] `start()` có hợp đồng xử lý partial failure; ownership của resource rõ ràng.
- [ ] Host ghi nhận plugin ACTIVE sau thành công và rollback theo LIFO.
- [ ] Cleanup errors được gắn với primary failure nhưng không cản dọn các plugin còn lại.
- [ ] Có timeout/quiescence/retry policy và trạng thái rõ khi cleanup thất bại.
- [ ] Có integration test: tất cả thành công, thiếu dependency, cycle, fail giữa chừng, fail cleanup.

**Kết luận:** Quản lý vòng đời plugin đáng tin cậy bắt đầu từ dependency graph được xác minh trước khi kích hoạt. Start theo thứ tự topo, ghi nhận từng thành công, rollback theo thứ tự ngược và dọn cả trạng thái partial initialization. Đây là nền tảng giúp host khởi động nhất quán và phục hồi khi chỉ một phần hệ thống plugin khởi tạo thành công.
