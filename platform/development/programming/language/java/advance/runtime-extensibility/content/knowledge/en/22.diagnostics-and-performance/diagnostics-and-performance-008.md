# Chọn phạm vi cache và phát hiện bộ nhớ tăng sau nhiều lần thay plugin trong Java

## 1. Bài toán: cache tối ưu lần gọi nhưng giữ lại phiên plugin đã thay thế

Một Java runtime hỗ trợ plugin có thể dùng một class loader riêng cho mỗi phiên bản (*generation*): nạp phiên bản A, chuyển sang B rồi tiếp tục với C mà không khởi động lại JVM. Cache giúp giảm chi phí reflection, tra cứu class, tạo serializer, đọc cấu hình hoặc khởi tạo provider. Nhưng nếu **cache sống lâu hơn plugin generation** và giữ một đối tượng do loader cũ định nghĩa, các class của generation cũ có thể không được giải phóng.

Hai câu hỏi phải được giải **cùng lúc**:

1. **Phạm vi cache:** dữ liệu này nên sống theo một request, một plugin generation, một tenant, một class hay toàn bộ host? Khóa cache có chứa *generation identity* không? Ai thực hiện invalidation khi plugin bị thay thế?
2. **Chẩn đoán bộ nhớ:** sau 10, 100 hoặc 1.000 lần thay plugin, có thật sự còn tham chiếu giữ loader cũ, hay chỉ là các đỉnh nhớ tạm thời, GC chưa chạy, JIT warmup, JAR cache hoặc chỉ số Metaspace chưa phản ánh class unloading ngay?

Không được kết luận “memory leak” chỉ bằng một đồ thị RSS tăng sau vài lần redeploy. Ngược lại, nếu host giữ `Class<?>` hoặc plugin instance của mọi generation trong một `static Map`, đó là **đường tham chiếu mạnh có thể chứng minh** mà không cần phỏng đoán hành vi GC.

**Mục tiêu:** chọn cache scope theo ownership/lifecycle, nhận diện cache giữ loader qua cả key lẫn value, tái hiện sự khác nhau giữa cache được dọn và cache tích lũy trong Java 17, xây phép đo nhiều vòng thay plugin có baseline nhất quán, rồi sử dụng heap dump và thống kê class loader để tìm nguyên nhân.

## 2. Vì sao một cache nhỏ cũng có thể giữ cả class loader?

Giả sử plugin có `demo.plugin.UpperRule` được định nghĩa bởi `URLClassLoader` A. Host lưu đối tượng của class này:

```text
GC Root
  -> static field của HostRegistry (được host loader định nghĩa)
  -> Map / cache
  -> UpperRule instance (generation A)
  -> Class<UpperRule>
  -> defining ClassLoader A
  -> các class / metadata mà A sở hữu
```

Cache cũng có thể giữ **trực tiếp** class hoặc loader:

```text
GC Root -> static Map<Class<?>, Handler> -> Class do A định nghĩa
GC Root -> static Map<PluginId, ClassLoader> -> URLClassLoader A
GC Root -> host serializer cache -> Method / Constructor của A
```

Điểm mấu chốt:

- **Đối tượng cache của host là một GC-root-reachable holder** nếu cache được giữ bởi một static field/registry còn sống. Nó có thể giữ plugin loader mà chính plugin không hề dùng cache.
- **Giữ class cũng có thể giữ loader:** `Class<?>`, reflection metadata, method handles, lambda, callback, proxy, provider hoặc plugin instance đều cần được xét, không chỉ những field có kiểu `ClassLoader`.
- **Static field của một lớp chỉ thuộc plugin A không tự nó đủ chứng minh leak.** Nếu cả graph loader A đã mất mọi đường từ GC roots, một chu trình nội bộ chỉ gồm class/object của A có thể được GC thu hồi. Phải tìm đường giữ từ *bên ngoài graph* vào A.
- **`URLClassLoader.close()` không ép unload class.** Nó kết thúc việc dùng tài nguyên loader như JAR handles; tính reachable của class/loader vẫn tùy tham chiếu còn sống và điều kiện GC.
- **Class identity có cả defining loader.** Hai class cùng binary name từ loader A và B không phải cùng đối tượng `Class<?>`. Dùng tên class làm khóa duy nhất có thể gây cache collision giữa các generation, ngoài vấn đề giữ reference cũ.

Cache quản lý sai thường tạo hai lỗi cùng lúc: **stale behavior** (lấy implementation/metadata của A khi B đang active) và **retained memory** (A không còn cần nhưng vẫn được cache giữ).

## 3. Chọn cache scope theo owner, dữ liệu và vòng đời

Một cache chỉ an toàn khi có **owner cụ thể** và **sự kiện kết thúc** rõ ràng. Bảng sau đưa ra phạm vi khuyến nghị:

| Đối tượng cần cache | Phạm vi thường phù hợp | Khóa và invalidation |
|---|---|---|
| Kết quả parse request/validation tạm | Request/task | Xóa khi request kết thúc, không đưa plugin object vào global state |
| Provider instance, reflective method, generated adapter của plugin | **Plugin generation** | Gắn theo `pluginId + generation`; dọn khi generation retired |
| Metadata riêng của `Class<?>` | Theo class hoặc generation | Cân nhắc `ClassValue` / cache nằm trong scope; tránh global `Map<Class<?>, ...>` không giới hạn |
| Serializer/DI factory dùng schema plugin | Plugin generation, đôi khi tenant + generation | Xóa đúng version; đóng object có resource khi retire |
| Dữ liệu immutable thuần Java platform, không chứa class/loader/plugin object | Host-wide **nếu thật sự độc lập version** | Bounded capacity/TTL; key có schema/config version nếu semantics thay đổi |
| Cấu hình theo tenant có thể đổi | Tenant + plugin generation | Khóa gồm tenant, plugin ID, generation/config version; cleanup tenant + gen |
| Cache kết quả tính toán theo input nhưng gọi plugin code | Thường generation + input key | Invalidate khi code/schema thay đổi, tránh trả kết quả của A cho B |
| Kết quả khám phá provider/resource theo loader | Loader/generation | Không giữ `ServiceLoader`, `Provider`, `Class<?>` cũ trong host-global cache |
| File/JAR/index được nhiều plugin thật sự chia sẻ | Host-wide có ref-count/lease rõ | Đóng khi không còn owner; kiểm tra quyền và version |

**Quy tắc ra quyết định:** hỏi “Một giá trị trong cache có thể tiếp tục đúng và không giữ plugin loader khi plugin này bị retire không?” Nếu câu trả lời **không**, đừng để giá trị sống trong cache toàn host không có generation key và đường eviction.

Không chọn phạm vi chỉ dựa vào “dữ liệu ít” hoặc “cần tối ưu nhanh”. Một cache chỉ có vài entry nhưng giữ `Class<?>` của các plugin cũ cũng đủ ngăn class unloading. Ngược lại, cache host-wide chứa chuỗi immutable, số học hoặc template không có reference tới plugin có thể hợp lý nếu có bounded size và semantics không đổi qua version.

## 4. Generation identity: tên plugin chưa đủ làm khóa

Một deployment có thể có:

```text
pluginId = "pricing"
generation = 41   -> loader A, code A
generation = 42   -> loader B, code B
generation = 43   -> loader C, code C
```

Khóa chỉ là `"pricing"` không phân biệt đối tượng thuộc A, B hay C. Khóa chỉ là `"com.acme.pricing.Rule"` còn thiếu defining loader. Kể cả hai generation biên dịch ra class cùng tên, runtime class identity vẫn khác nhau khi được định nghĩa bởi loader khác.

**Khóa cache phụ thuộc code nên bao gồm generation identity**, ví dụ:

```java
record CacheKey(String pluginId, long generation, String resourceName) {}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Generation ID nên được host cấp và bất biến cho một lần cài đặt; không dùng `System.identityHashCode(loader)` như một ID vĩnh viễn vì có thể trùng và không mang ý nghĩa business/version.

Hai lựa chọn hợp lệ:

1. **Một cache riêng bên trong đối tượng `PluginScope`/`PluginGeneration`.** Mỗi scope giữ đúng loader và resource của mình; khi retire thì `close()/clear()` scope và gỡ scope khỏi registry host. Trong cache nội bộ có thể dùng khóa đơn giản như `"entry"` vì generation đã được biểu diễn bằng owner.
2. **Một cache chung bắt buộc chia sẻ giữa generation:** key cần mang cả `pluginId`, `generation` và những biến thể như tenant/config/schema nếu ảnh hưởng kết quả. Eviction phải lọc đúng generation, không xóa entry của bản B khi tháo A.

**Đừng suy ra cache đã “update” thành B chỉ vì cập nhật một biến `currentPlugin = B`.** Mọi key/value khác trong map, callback, futures, ThreadLocal và reflection metadata vẫn có thể giữ A.

## 5. Chu kỳ thay plugin và thời điểm hủy cache

Một runtime thay thế plugin nên có state machine tường minh:

```text
DISCOVERED -> LOADING -> ACTIVE -> DRAINING -> RETIRED -> CLOSED
                             |
                             +--- generation B có thể ACTIVE
                                  trong khi A đang DRAINING
```

Đây là mô hình ứng dụng đề xuất, **không phải enum của Java**.

Trình tự hợp lý khi chuyển A sang B:

1. Chuẩn bị loader B và **cache của B** riêng; validate code/API/config trước khi publish.
2. Chuyển hướng request mới sang B bằng cơ chế swap nguyên tử phù hợp (chẳng hạn update một generation pointer/registry).
3. Đánh dấu A `DRAINING`, không tạo cache entry/task/subscription mới cho A sau thời điểm này.
4. Chờ hoặc hủy có kiểm soát các request/callback A còn chạy. Một request A đang hoạt động có thể cần sử dụng đúng cache của A cho đến khi hoàn tất.
5. Unregister listeners, dừng scheduler/jobs, xóa ThreadLocal/TCCL của worker theo ownership.
6. **Evict cache generation A** và release các tài nguyên cache value sở hữu (stream, handles, watchers, providers có lifecycle).
7. Gỡ scope A khỏi host registry, đóng loader và bỏ strong references khi mọi consumer hợp lệ đã kết thúc.
8. Theo dõi loader A ở trạng thái retired bằng weak probe/metrics nếu cần, tránh chính hệ thống monitoring giữ A bằng strong reference.

Không nên xóa cache A quá sớm khi các request in-flight còn đang chạy; họ có thể gặp lỗi hoặc tái tạo entry A sau khi evict. Mặt khác, không được giữ cache A vô thời hạn chỉ vì không biết còn request hay không. Production có thể dùng **lease/ref-count**, trạng thái draining và deadline để xác định lúc safe cleanup.

Một lỗi race hay gặp:

```text
Thread 1: bắt đầu clear cache A
Thread 2: request cũ đang chạy, gọi computeIfAbsent(A, ...)
Thread 1: thấy map trống và báo "unloaded"
Thread 2: tạo lại value A trong host cache -> giữ loader A
```

Muốn tránh, phải chặn write vào scope A trước, rồi drain consumers và mới clear. Chỉ gọi `Map.clear()` không đủ tạo một giao thức retire an toàn dưới concurrency.

## 6. Phản mẫu: cache toàn host giữ class và instance của mọi bản cũ

Đoạn **minh họa sai** sau không phải chương trình độc lập:

```java
// Class HostRegistry do application class loader định nghĩa.
static final Map<String, Class<?>> COMPILED_TYPES = new HashMap<>();

// Mỗi lần plugin được nạp, host lại lưu Class<?> của generation đó.
COMPILED_TYPES.put(pluginId + "#" + generation, implementationClass);

// Khi generation retired, code quên remove key đó.
```

Kết quả: `HostRegistry` sống theo tiến trình, nên từng `Class<?>` của A/B/C được giữ thông qua map. Dù đã `URLClassLoader.close()` từng loader cũ, JVM vẫn có strong references tới các class của chúng.

Các biến thể cũng nguy hiểm:

- `Map<Class<?>, Serializer>`: cả **key** lẫn **value** có thể giữ plugin loader.
- `Map<String, MethodHandle>`: value có thể giữ method/class của plugin.
- `Map<String, Supplier<?>>`: lambda capture plugin instance mà log không hiện tên class rõ.
- `LoadingCache` với unlimited size: TTL hoặc maximum size bị cấu hình thiếu hoặc không được đánh giá ở thời điểm retire.
- `Map<PluginId, List<Callback>>`: callback còn đăng ký trong host registry sau khi switch generation.
- `WeakHashMap<ClassLoader, Scope>`: nếu value `Scope` giữ chính loader dùng làm key, tham chiếu mạnh từ map tới value tới key có thể làm weak key không đủ để giải phóng loader.
- Cache service provider: `ServiceLoader`, `Provider<?>`, listener hoặc DI objects có thể giữ provider class và defining loader.

Dấu hiệu quan trọng trong heap dump là **đường từ root do host sở hữu đến class/instance của generation retired**, không phải mọi cache trong hệ thống đều đáng xóa.

## 7. Ví dụ Java 17 chạy được: cache theo generation so với giữ history

Ví dụ tạo một interface ở host, một implementation ở plugin và một host manager. Mỗi lần “thay plugin” host tạo **URLClassLoader mới cho cùng bytecode** để tái hiện vòng đời class/loader. Thực tế production sẽ dùng các JAR phiên bản khác nhau; trong demo dùng cùng class file để cô lập yếu tố *cache scope*.

Có hai chế độ:

- **`clean`:** retire generation trước khi giữ generation mới; map host luôn chỉ giữ một scope active.
- **`leak`:** cố ý không retire generation trước ngay trong vòng lặp; host registry tích lũy 1 → 2 → 3 scopes. Dù cùng implementation name, mỗi scope sở hữu một loader mới.
- Cả hai chế độ đều dọn các scopes còn lại trong `finally` trước khi process kết thúc. Như vậy `leak` là **mô phỏng retention trong lúc chương trình đang chạy**, không phải cố tình bỏ rò tài nguyên sau khi process kết thúc.

Đây là demo **đo deterministic entry count**, không phải kiểm thử thời điểm JVM thực sự unload class.

### 7.1. Cấu trúc thư mục

```text
cache-scope-demo/
  src/
    api/demo/api/Rule.java
    plugin/demo/plugin/UpperRule.java
    host/demo/app/CacheScopeDemo.java
  build/
    api/
    plugin/
    host/
```

**Tệp `src/api/demo/api/Rule.java`:**

```java
package demo.api;

public interface Rule {
    String apply(String input);
}
```

**Tệp `src/plugin/demo/plugin/UpperRule.java`:**

```java
package demo.plugin;

import demo.api.Rule;
import java.util.Locale;

public final class UpperRule implements Rule {
    @Override
    public String apply(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

**Tệp `src/host/demo/app/CacheScopeDemo.java`:**

```java
package demo.app;

import demo.api.Rule;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class CacheScopeDemo {
    record GenKey(String pluginId, int generation) {}

    private static final Map<GenKey, Scope> SCOPES = new LinkedHashMap<>();

    private static final class Scope implements AutoCloseable {
        private final URLClassLoader loader;
        private final Map<String, Rule> cache = new HashMap<>();

        Scope(Path pluginDirectory) throws IOException {
            this.loader = new URLClassLoader(
                    new URL[] { pluginDirectory.toUri().toURL() },
                    Rule.class.getClassLoader());
        }

        Rule getRule() throws Exception {
            Rule cached = cache.get("entry");
            if (cached != null) {
                return cached;
            }
            Class<?> implementation = Class.forName(
                    "demo.plugin.UpperRule", true, loader);
            Rule result = implementation.asSubclass(Rule.class)
                    .getDeclaredConstructor().newInstance();
            cache.put("entry", result);
            return result;
        }

        boolean ownsRule(Rule rule) {
            return rule.getClass().getClassLoader() == loader;
        }

        int cacheSize() {
            return cache.size();
        }

        @Override
        public void close() throws IOException {
            cache.clear();
            loader.close();
        }
    }

    private static void retire(GenKey key) throws IOException {
        Scope scope = SCOPES.remove(key);
        if (scope != null) {
            scope.close();
        }
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "clean" : args[0];
        if (!mode.equals("clean") && !mode.equals("leak")) {
            throw new IllegalArgumentException("Use clean or leak");
        }
        System.out.println("mode=" + mode);
        Path pluginDirectory = Path.of("build/plugin").toAbsolutePath();
        GenKey prior = null;

        try {
            for (int i = 1; i <= 3; i++) {
                if (mode.equals("clean") && prior != null) {
                    retire(prior);
                }
                GenKey key = new GenKey("upper", i);
                Scope scope = new Scope(pluginDirectory);
                SCOPES.put(key, scope);
                Rule rule = scope.getRule();
                int entries = SCOPES.values().stream()
                        .mapToInt(Scope::cacheSize).sum();
                System.out.println("round-" + i
                        + ":scopes=" + SCOPES.size()
                        + ",cache-entries=" + entries
                        + ",result=" + rule.apply("java")
                        + ",child-defined=" + scope.ownsRule(rule));
                prior = key;
            }
            System.out.println("retired-left=" + (SCOPES.size() - 1));
        } finally {
            for (GenKey key : List.copyOf(SCOPES.keySet())) {
                retire(key);
            }
            System.out.println("after-close=" + SCOPES.size());
        }
    }
}
```

**Cơ chế đáng chú ý:**

1. `Rule` được biên dịch/đưa lên classpath của host; child loader lấy chính interface đó qua parent, tránh class identity mismatch giữa host và plugin.
2. `pluginDirectory` **không** nằm trong runtime host classpath. Nếu bỏ nhầm `build/plugin` vào `-cp`, plugin implementation có thể được application loader tìm thấy qua delegation và làm test không còn đúng ranh giới child.
3. Mỗi `new Scope(pluginDirectory)` tạo một `URLClassLoader` mới, cho phép cùng tên class được định nghĩa riêng theo generation. `scope.ownsRule(rule)` kiểm tra điều đó.
4. `Scope.cache` chứa instance implementation, nên scope là owner rõ ràng. `SCOPES` của host chỉ được phép giữ những scope còn active/draining.
5. Ở chế độ `clean`, `retire(prior)` gỡ scope cũ khỏi host map và xóa cache trước khi đóng loader.
6. Ở chế độ `leak`, host map tích lũy các scope cũ; đây là retained reference đủ để **ngăn đồ thị loader cũ trở thành unreachable trong giai đoạn mô phỏng**.
7. Khối `finally` dọn hết map vào cuối demo, kể cả khi lỗi xuất hiện trong vòng lặp. Trong production, teardown phải xử lý exception của từng scope độc lập để lỗi đóng một loader không khiến các scope khác không được dọn.
8. `LinkedHashMap`/`HashMap` ở đây cố ý **không thread-safe** để demo dễ hiểu. Host thực chạy đồng thời phải có lease, khóa và trạng thái DRAINING/RETIRED rõ ràng; không sao chép code này nguyên xi cho hệ thống concurrent.

### 7.2. Biên dịch và chạy trên Windows PowerShell

Đứng trong `cache-scope-demo/`, dùng JDK 17 trở lên:

```powershell
New-Item -ItemType Directory -Force -Path build/api,build/plugin,build/host | Out-Null
javac --release 17 -d build/api src/api/demo/api/Rule.java
javac --release 17 -cp build/api -d build/plugin src/plugin/demo/plugin/UpperRule.java
javac --release 17 -cp build/api -d build/host src/host/demo/app/CacheScopeDemo.java
java -cp "build/api;build/host" demo.app.CacheScopeDemo clean
java -cp "build/api;build/host" demo.app.CacheScopeDemo leak
```

### 7.3. Biên dịch và chạy trên Linux/macOS

```bash
mkdir -p build/api build/plugin build/host
javac --release 17 -d build/api src/api/demo/api/Rule.java
javac --release 17 -cp build/api -d build/plugin src/plugin/demo/plugin/UpperRule.java
javac --release 17 -cp build/api -d build/host src/host/demo/app/CacheScopeDemo.java
java -cp "build/api:build/host" demo.app.CacheScopeDemo clean
java -cp "build/api:build/host" demo.app.CacheScopeDemo leak
```

### 7.4. Stdout chính xác, chế độ clean

```text
mode=clean
round-1:scopes=1,cache-entries=1,result=JAVA,child-defined=true
round-2:scopes=1,cache-entries=1,result=JAVA,child-defined=true
round-3:scopes=1,cache-entries=1,result=JAVA,child-defined=true
retired-left=0
after-close=0
```

### 7.5. Stdout chính xác, chế độ leak

```text
mode=leak
round-1:scopes=1,cache-entries=1,result=JAVA,child-defined=true
round-2:scopes=2,cache-entries=2,result=JAVA,child-defined=true
round-3:scopes=3,cache-entries=3,result=JAVA,child-defined=true
retired-left=2
after-close=0
```

Hai kết quả đã được kiểm tra bằng việc biên dịch với `javac --release 17` và chạy cả hai chế độ. Kết quả chứng minh **registry/caches đang giữ bao nhiêu scope** và implementation đến từ child loader trong lúc chạy, **không chứng minh số class đã được GC unload**.

Đặc biệt, `after-close=0` chỉ xác nhận map host đã được dọn trong demo; còn local variables trên stack/JIT, GC timing và những references từ component khác có thể ảnh hưởng class unloading. Không viết unit test “`close()` thì Metaspace lập tức giảm” dựa trên ví dụ này.

## 8. Cách đọc thí nghiệm: retention, eviction và memory leak là ba điều khác nhau

Ở chế độ `clean`, registry luôn có đúng một scope khi in số liệu; ở chế độ `leak`, registry chứa 3 scope và 3 entry ở vòng 3. Đường giữ là:

```text
CacheScopeDemo.class
  -> static SCOPES
  -> LinkedHashMap entry (GenKey of upper#1)
  -> Scope generation 1
  -> Scope.loader (URLClassLoader #1)
  -> Scope.cache["entry"]
  -> UpperRule instance of generation 1
```

Cấu trúc tương tự có ở generation 2. Đây là **các strong references còn reachable từ host**, không cần chạy GC để biết đối tượng còn được tham chiếu.

Tuy nhiên:

- **Retention có chủ đích:** hai generation cũ có thể còn đang DRAINING vì request in-flight, nên giữ cache một lúc là đúng. Cần định nghĩa grace period/lease trước khi gọi đó là leak.
- **Eviction đúng:** khi không consumer nào dùng generation cũ nữa, retire xóa map entry, clear cache, đóng tài nguyên. Đây là hành vi deterministic có thể assert.
- **Leak thực sự:** sau khi generation đã RETIRED/CLOSED và hết thời gian cho phép, host vẫn giữ entry/loader qua một hoặc nhiều nguồn; xu hướng này tiếp tục qua nhiều lần replace.
- **Chưa GC không phải leak:** dù registry đã sạch, JVM có thể chưa unload classes hoặc chưa trả Metaspace/native pages về OS ngay.
- **GC đã dọn loader không có nghĩa ứng dụng dùng đúng cache:** vẫn có thể có stale cache value thuần `String`/DTO được trả cho generation mới. Cần kiểm thử correctness riêng với resource ownership.

**Đo hai thứ khác nhau:** (1) các reference và cache entries có đúng lifecycle không; (2) heap/Metaspace/native memory có xu hướng bất thường sau nhiều lần thay và các cơ hội GC tương đương không.

## 9. TTL, LRU, WeakHashMap, ClassValue: chọn kỹ thuật nào?

### 9.1. Cache giới hạn dung lượng và thời gian

LRU/maximum size hoặc TTL có ích để tránh tăng không giới hạn với kết quả request hoặc dữ liệu thuần. Nhưng **TTL không thay thế việc retire**: một callback/class của plugin A còn trong cache thêm 30 phút có thể giữ loader A suốt 30 phút, trong khi chính sách cho phép chỉ 1 phút. TTL có thể chỉ được quét theo truy cập hoặc lịch dọn riêng tùy implementation.

Với cache chứa đối tượng plugin, ưu tiên **eviction chủ động theo generation**, rồi dùng size/TTL làm phòng tuyến bổ sung. Nếu cache value sở hữu tài nguyên (stream, scheduled task, closeable adapter), eviction còn phải thực thi hàm close/dispose tương ứng, không chỉ xóa map entry.

### 9.2. Weak key không phải giải pháp mặc định

Xem ví dụ phản mẫu:

```java
// Chỉ minh họa rủi ro, không phải đoạn code độc lập.
WeakHashMap<ClassLoader, PluginScope> registry = new WeakHashMap<>();
registry.put(pluginLoader, new PluginScope(pluginLoader));
```

Nếu value của `PluginScope` giữ strong reference tới `pluginLoader`, có đường `registry → value → key` nên weak key không bảo đảm tự hết hiệu lực. Dù key/value yếu có thể giúp một số use case, chúng **không** thực thi cleanup resource/registrations, không tạo deadline GC và không thay thế owner-defined `close()`.

### 9.3. ClassValue cho metadata đúng theo Class

Java 17 có `ClassValue<T>` để liên kết giá trị tính toán với từng `Class<?>`. Với metadata chỉ phụ thuộc type:

```java
// Minh họa: giá trị gắn với type chứ không dùng host-global Map<Class<?>,...>.
private static final ClassValue<String> BINARY_NAMES = new ClassValue<>() {
    @Override
    protected String computeValue(Class<?> type) {
        return type.getName();
    }
};
```

Đoạn code này cần đặt trong class. Nó chỉ cache `String` tên lớp; một hệ thống thật có thể lưu cấu trúc plan có owner rõ ràng. `ClassValue` giúp tránh nhiều lỗi từ map khóa class do host tự quản, nhưng không có nghĩa cứ dùng `ClassValue` là chắc chắn unload được loader. Các reference khác, value có resource/closure, static registry, ThreadLocal và callback vẫn cần được dọn. `ClassValue.remove(type)` xóa một association cụ thể, không “gỡ class khỏi JVM”.

### 9.4. Cache nằm trong plugin scope

Đây là mặc định tốt cho factory/reflection/provider có lifetime cùng generation:

```text
Host plugin registry
  -> PluginScope generation 42
     -> Loader42
     -> Cache42
     -> subscriptions42
     -> worker/timer handles42

retire(42):
  stop new work -> drain -> unregister -> Cache42.clear()
  -> close resources -> remove PluginScope42 from host registry
```

Khi owner và scope cùng lifetime, việc audit trở nên dễ hơn. Nếu cache được dùng bởi nhiều plugin thì cần policy chia sẻ riêng, không tự động kéo theo lifetime của generation dài nhất.

## 10. Chọn phạm vi còn phụ thuộc tenant, request và schema

Bốn cấp dễ bị trộn lẫn:

1. **Request scoped:** object tạm, transaction, request context. Không giữ trong static cache sau khi request kết thúc. Nếu request được thực hiện bởi plugin A, phải thả lease A khi task xong.
2. **Tenant scoped:** cùng plugin code nhưng cấu hình, quyền truy cập, schema hoặc dữ liệu của tenant khác nhau. Khóa `pluginId + generation` chưa đủ nếu value phụ thuộc tenant. Cache không phân vùng có thể gây **lộ dữ liệu** chứ không chỉ memory leak.
3. **Plugin-generation scoped:** class, method handle, provider, adapter, compiled rule, serialization plan. Lấy code identity từ generation, không chỉ binary class name.
4. **Host-wide:** dữ liệu thực sự chung và không giữ class/loader/plugin instance. Cache global vẫn cần limit/metrics/expiration vì input cardinality có thể vô hạn.

Một mẫu khóa có thể là:

```java
record Key(String tenantId, String pluginId,
           long generation, String schemaVersion, String item) {}
```

Đây là **đoạn minh họa**. Không dùng một key nhiều trường cho mọi cache nếu trường đó không liên quan; mục tiêu là biểu đạt đúng **những yếu tố làm thay đổi semantics/value**, đồng thời tránh giữ mạnh `ClassLoader` hoặc `Class<?>` làm key ngoài phạm vi owner cần thiết.

Khi plugin B thay thế A nhưng contract vẫn giống, host có thể **chủ động chuyển một cache dữ liệu thuần** sang B sau kiểm tra tương thích. Tuy nhiên, không chuyển theo mặc định các runtime objects, `Class<?>`, method handles, classloader-bound proxies hoặc provider instances của A.

## 11. Đo bộ nhớ qua nhiều vòng thay plugin: đo cùng điều kiện

Để biết hệ thống có tăng bộ nhớ thực sự sau reload, hãy làm phép thử có kiểm soát thay vì quan sát ngẫu nhiên:

**Chuẩn bị:** một JVM test với workload ổn định, JDK/GC flags cố định, các plugin generations có ID, số request đồng thời/queue như nhau, output logs định danh loader. Warm up runtime trước khi lấy baseline để giảm nhiễu từ class loading của framework và JIT.

**Mỗi vòng thử** (ví dụ A→B, B→C, ...):

1. Tạo generation mới; đo các cache entries và classes/loader phát sinh.
2. Chuyển new traffic sang generation mới.
3. Dừng traffic mới tới generation cũ, đợi in-flight consumers kết thúc.
4. Retire generation cũ: unregister callbacks, cancel tasks, dọn TCCL/ThreadLocal, clear generation-scoped caches, đóng loader và gỡ registry entry.
5. Sau một **cửa sổ ổn định tương đương** giữa các vòng, lấy snapshot số scope còn active/draining/retired, cache entries, loader counts và bộ nhớ. Nếu quy trình cho phép GC trong staging, ghi rõ lúc thực hiện; không dựa vào một lần `System.gc()` như sự bảo đảm.
6. Lặp nhiều vòng đủ để nhìn xu hướng, ghi cả peak và **post-collection baseline** khi dữ liệu GC thực tế có sẵn.

So sánh các đại lượng:

| Metric | Giải thích | Điều cần phân biệt |
|---|---|---|
| Active generation count | Số phiên plugin hợp lệ đang phục vụ | Có thể lớn hơn 1 khi rolling replacement |
| Retired generation references | Những scope/cache/registrations còn giữ phiên đã retire | Sau grace period nên về 0 theo thiết kế |
| Cache entries/weight per generation | Quy mô cache còn reachable | Bounded-size/TTL không thay thế eviction khi retire |
| Current loaded class count | Số class hiện đang loaded trong JVM | Tăng vì framework/JIT/feature mới chưa chắc leak |
| Total loaded / total unloaded classes | Cumulative counters từ JVM | Total loaded tăng theo định nghĩa; không được yêu cầu giảm |
| Heap used sau các cơ hội GC tương đương | Object payload và registries | Allocation peak khác retained heap floor |
| Metaspace used/committed | Metadata class và cấu trúc liên quan | Used/committed/reserved khác nhau; không luôn trả ngay về OS |
| RSS / native memory | Bộ nhớ tiến trình ngoài heap và phần heap resident | Có thể tăng bởi direct buffer, code cache, threads/JNI |
| Class unload events | JVM có thông báo class được unload hay không | Vắng event trong khoảng ngắn chưa chứng minh leak |

**Mẫu suy luận:** nếu sau 100 vòng, app luôn có 1 generation active nhưng cache/loader registry vẫn giữ 100 generation và Metaspace tăng dần, đó là bằng chứng cần điều tra. Nếu registry đúng 1 scope, loaded class count ổn định theo thời gian nhưng RSS vẫn tăng, hãy kiểm tra heap/native allocations/fragmentation thay vì kết luận ngay là class-loader leak.

## 12. Theo dõi bằng JMX/MXBeans từ Java

Java 17 cung cấp `ClassLoadingMXBean` và `MemoryPoolMXBean` qua `ManagementFactory`. Trong application có thể định kỳ ghi nhận:

```java
// Đoạn minh họa đặt trong một class và gọi tại điểm lấy snapshot.
var classStats = java.lang.management.ManagementFactory
        .getClassLoadingMXBean();
int currentLoaded = classStats.getLoadedClassCount();
long everLoaded = classStats.getTotalLoadedClassCount();
long everUnloaded = classStats.getUnloadedClassCount();

for (var pool : java.lang.management.ManagementFactory
        .getMemoryPoolMXBeans()) {
    if (pool.getType() == java.lang.management.MemoryType.NON_HEAP
            && pool.getName().contains("Metaspace")) {
        var usage = pool.getUsage();
        if (usage != null) {
            long used = usage.getUsed();
            long committed = usage.getCommitted();
            // Log used/committed + timestamp + plugin generation ID.
        }
    }
}
```

Đây là **mã minh họa**, không phải chương trình độc lập và không in stdout cố định. Tên pool phụ thuộc JVM/vendor; đoạn code chọn pool có tên chứa `Metaspace` trên HotSpot điển hình, có thể không có ở JVM khác. Ghi rõ metadata như Java version, collector, process ID và cấu hình test.

Các phép so sánh hợp lệ:

- `getLoadedClassCount()` là **số hiện tại**, không phải số class thuộc plugin. Muốn phân biệt plugin A/B cần instrument registry hoặc phân tích classloader-specific data.
- `getTotalLoadedClassCount()` và `getUnloadedClassCount()` là **tổng tích lũy từ khi JVM khởi động**; đừng coi tổng loaded tăng là leak.
- Một pool `Metaspace` có `used` và `committed` khác nhau; phần memory trả về OS còn phụ thuộc runtime/GC, không nhất thiết trùng biến động này.
- Gắn samples với **thời điểm sau retire** và các sự kiện GC để so được nhiều vòng. Một sample ở peak allocation không đại diện cho steady state.
- Không cố ép một ngưỡng kiểu “sau 3 lần thay thì heap phải bằng baseline tuyệt đối”. JIT, class initialization, framework caches và asynchronous cleanup tạo biến thiên hợp lệ.

Lưu ý bảo mật/chi phí: metrics ít nhạy cảm hơn heap dump nhưng vẫn có thể làm lộ tên plugin, class, tenant hoặc đường dẫn nội bộ. Nên log generation ID đã được phép chia sẻ và giới hạn cardinality của metrics labels.

## 13. Điều tra sâu với jcmd, GC logs và Native Memory Tracking

Trên HotSpot/JDK 17 trong môi trường cho phép attach, có thể dùng `jcmd` để so với counters trong host:

```bash
# Thay <pid> bằng PID tiến trình Java cần kiểm tra.
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_info
jcmd <pid> GC.heap_dump /path/to/plugin-retention.hprof
```

- `VM.classloader_stats` giúp quan sát thống kê class loader/class-loader data; không tự động nói loader nào bị giữ bởi cache nào.
- `GC.class_histogram` cho thống kê object trên heap, có thể gây tác động cao theo tài liệu công cụ. Không chạy liên tục trên production nếu chưa cân nhắc.
- `GC.heap_dump` tạo HPROF, có thể tiêu tốn disk, gây pause và theo cấu hình mặc định có thể yêu cầu full GC. Heap dump có thể chứa credentials, dữ liệu khách hàng và thông tin nhạy cảm: phải có quy trình phê duyệt, mã hóa/lưu trữ an toàn và xóa sau phân tích.
- `GC.heap_info` là bức tranh heap, không bao gồm toàn bộ native/JNI allocations.
- Với test khởi động JVM bằng logging tương thích, có thể quan sát class unloading:

```bash
java -Xlog:class+unload=info -cp "build/api:build/host" demo.app.CacheScopeDemo clean
```

Lệnh này minh họa cho Linux/macOS và có thể tạo log khác nhau tùy GC/timing; nó **không có stdout cố định**. Trên Windows thay dấu phân cách classpath bằng `;`. Không nhìn thấy log unload trong demo ngắn không chứng minh cache vẫn còn giữ loader.

### Native Memory Tracking (NMT)

Khi RSS tăng nhưng heap/Metaspace metrics không giải thích được, NMT có thể giúp phân loại phần JVM-native. Với HotSpot, NMT cần bật từ khi khởi động:

```bash
java -XX:NativeMemoryTracking=summary -cp "build/api:build/host" demo.app.CacheScopeDemo clean
```

Khi tiến trình test thực sự còn sống (demo trên kết thúc nhanh), các lệnh sau có thể dùng trong **quy trình kiểm thử dài hạn khác**:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

NMT có overhead và không phải bộ đo toàn bộ native memory của các thư viện bên thứ ba/JNI. Trình tự trên **không** nhằm chạy attach vào demo đã kết thúc; cần một host process đang hoạt động với NMT đã bật. `summary.diff` so với NMT baseline, không phải “memory sau GC của Java heap”. Dữ liệu cần được so sánh với metrics host, GC/JFR và profiler để tránh quy kết nhầm cho plugin loader.

## 14. Dùng heap dump để tìm Path to GC Roots

Khi metric cho thấy những generation RETIRED vẫn còn class loader, bước chẩn đoán quyết định là **reference path**:

1. Chọn đúng plugin ID/generation đã retire; không nhầm loader mới đang active với loader cũ.
2. Trong Eclipse Memory Analyzer (MAT) hoặc profiler tương đương, tìm `java.net.URLClassLoader`/custom `PluginClassLoader` hoặc một `Class<?>` do loader đó định nghĩa.
3. Dùng chức năng **Path to GC Roots** và ưu tiên xem strong references; tùy công cụ, lọc những đường chỉ có weak/soft/phantom refs để nhìn owner giữ mạnh.
4. Lần theo từng edge tới class host, field static, cache key/value, thread, executor queue, listener hoặc DI container. Đừng dừng ở lớp nội bộ `HashMap$Node` mà chưa xác định registry nào sở hữu nó.
5. Nếu thấy `HostRegistry → Map → Class<PluginType>`, sửa eviction ở owner của map. Nếu thấy `Thread → ThreadLocalMap.value → PluginContext`, dọn context trên đúng worker. Nếu thấy `EventBus → listeners → callback`, unregister subscription đúng generation.
6. Sau sửa, lặp lại quá trình thay plugin và so sánh retained paths ở cùng tình huống. Một loader có thể còn **nhiều đường mạnh độc lập**; xóa một đường chỉ làm lộ đường khác.

Ví dụ retained path của cache:

```text
GC Root: HostCache.class
  -> HostCache.ACTIVE_AND_OLD
  -> ConcurrentHashMap$Node.value
  -> PluginScope(upper, generation=12)
  -> Scope.cache["serializer"]
  -> PluginSerializer instance
  -> Class<PluginSerializer> defined by Loader12
```

Thông điệp sửa lỗi không phải “GC không hoạt động”, mà là: **HostCache vẫn giữ generation 12 sau trạng thái RETIRED**. Xác định nơi `retire(12)` đáng ra được gọi, kiểm tra exceptions/races và bổ sung regression test.

Nếu heap analyzer cho thấy loader được giữ bởi **thread stack** của một request A còn đang chạy, có thể là retention tạm thời hợp lệ. Muốn kết luận leak cần biết SLA drain, trạng thái task và liệu đường đó còn tồn tại sau deadline hợp lý.

## 15. WeakReference để theo dõi loader cũ, không ép GC

Host có thể giữ *probe* bằng `WeakReference<ClassLoader>` của loader A khi release strong references:

```java
// Mẫu minh họa, không phải chương trình độc lập.
java.lang.ref.WeakReference<ClassLoader> probe =
        new java.lang.ref.WeakReference<>(loaderA);
// Sau khi retire: không được giữ loaderA trong các static registries,
// callback, task, class metadata caches hay một monitor strong reference.
// probe.get() == null có thể xuất hiện khi JVM thực sự thu gom referent.
```

**Không** xem `probe.get() != null` ngay sau `close()` là lỗi chắc chắn: JVM có thể chưa GC, JIT/stack locals còn sống, hoặc runtime đang giữ loader hợp lệ. `System.gc()` chỉ là đề nghị và không tạo deadline bắt buộc cho collection. Mặt khác, `probe.get() == null` là tín hiệu hữu ích về referent đã được thu gom tại thời điểm quan sát, nhưng **không** chứng minh mọi native resource/file handle/plugin callback đã được đóng đúng.

Khi theo dõi hàng trăm generation, giữ danh sách **weak references và metadata thuần** (pluginId, generation, thời điểm retire), không giữ `Class<?>` hoặc loader mạnh trong metrics registry. Một “leak detector” lưu `Map<GenerationId, ClassLoader>` để kiểm tra lại về sau có thể tự tạo ra leak mà nó định chẩn đoán.

Có thể dùng `ReferenceQueue` để nhận thông báo khi referent trở nên eligible/cleared theo cơ chế references, nhưng thời điểm vẫn phụ thuộc GC; không lấy một số giây cố định làm tiêu chí chính. Assert mạnh hơn nằm ở **owner map trống, callback unsubscribed, TCCL restored và loader no longer registered**.

## 16. Khi đã dọn cache mà memory vẫn tăng

Không phải mọi trường hợp tăng bộ nhớ sau reload đều do cache. Phải mở rộng phạm vi điều tra theo tín hiệu:

| Triệu chứng sau nhiều vòng | Nguồn cần điều tra | Cách kiểm tra |
|---|---|---|
| Retired scope count tăng theo generation | Registry/cache lifetime sai | Đếm scope/entry theo generation, xem owner map |
| Heap floor tăng, retained path từ host static → plugin object | Cache/DI/callback giữ strong reference | MAT Path to GC Roots, sửa eviction/unregister |
| Heap floor tăng, root từ thread | ThreadLocal, TCCL, pending tasks, thread target | Dump thread + heap, dọn trên đúng worker |
| Metaspace và loaded classes tăng, retired loader vẫn reachable | Class metadata/loader retention | Classloader stats, heap paths, class unload events |
| RSS tăng nhưng Java heap ổn | Native/direct buffers, code cache, thread stacks, mmap/JAR/JNI | NMT khi phù hợp, OS metrics, buffer pool metrics |
| Class unload có xảy ra nhưng RSS không giảm ngay | Native allocator/committed vs resident | Phân biệt used/committed/RSS, theo dõi dài hạn |
| Memory tăng theo workload nhưng không theo số lần reload | Cache request/tenant, queue, traffic | So sánh cùng workload và cache hit/eviction |
| Chỉ xuất hiện khi chạy song song | Race giữa generation drain và computeIfAbsent | Repro đồng thời, bảo vệ state và write gate |
| File JAR không xóa được trên Windows | Loader/JAR stream còn mở | Đóng đúng resource, kiểm tra file handles |
| CPU/latency tăng sau mỗi lần reload | Cache thrashing, nhiều listener/task cũ còn chạy | Event counts, worker/task queues, allocation profiles |

**Một phân tích đúng cần xác định loại memory nào đang tăng:** object heap, metaspace/class metadata, memory manager/JVM-native, direct buffers, code cache hay thread stacks. Từ đó mới chọn công cụ chẩn đoán phù hợp. “Đồ thị Task Manager tăng” không chỉ ra đường tham chiếu cụ thể.

## 17. Regression test: deterministic ownership trước, GC trend sau

Một bộ test hữu ích nên có hai tầng.

### 17.1. Unit/integration tests có thể assert chắc chắn

- Sau `install(A)`, cache scope A tồn tại và mọi value/class đúng generation A.
- Sau `install(B)` + `retire(A)`, registry host không còn key A; cache A được clear và các `AutoCloseable` value đóng đúng một lần.
- B vẫn hoạt động bình thường; eviction A không xóa B.
- Không request A mới được nhận sau DRAINING; task in-flight hoàn tất hoặc được cancel theo contract.
- Hai class trùng binary name từ loader A/B không bị cache key `String className` làm lẫn.
- Các cache có tenant dimension không trả value của tenant khác.
- Callback, timer, listener, executor task, TCCL và ThreadLocal được dọn theo generation.
- Inject exception vào một cleanup step; những bước độc lập còn lại vẫn được cố thực hiện, không tuyên bố retire thành công giả.
- Thử concurrency giữa `retire(A)` và `cache.get(A,key)`; không cho phép tái tạo cache A sau khi scope đóng.

Mã demo mục 7 là một bài test cấp đầu: chế độ `clean` có `retired-left=0`, chế độ `leak` có `retired-left=2` sau ba lần install. Những assertion này **không phụ thuộc vào GC**.

### 17.2. Soak test nhiều vòng thay plugin

Trong môi trường staging:

1. Warm up host, ghi baseline sau khi ứng dụng ổn định.
2. Lặp 50–200 vòng install/retire với workload gần thực tế; mỗi vòng ghi active/retired scope count, cache size/weight, process memory, classloader/class counters và GC events.
3. Sau mỗi nhóm vòng, xác nhận owner maps sạch; lấy snapshot bộ nhớ ở **những thời điểm có điều kiện đo tương tự**, tránh đối chiếu peak với post-GC.
4. Ghi xu hướng retained loader/class counts sau nhiều cơ hội GC phù hợp, không đòi `WeakReference.get()==null` đúng ở một deadline nhỏ.
5. Nếu thấy xu hướng tăng, chụp heap dump, xác định đường từ GC root, sửa cache owner rồi chạy lại cùng test.
6. Đo latency/cache hit rate sau khi thêm eviction để bảo đảm không vô tình chuyển thành việc khởi tạo lại plugin quá thường xuyên.

**Không tự động kết luận leak chỉ từ “Metaspace chưa về đúng baseline byte-for-byte”.** GC/class unloading có thể không diễn ra ngay; một số classes mới thuộc host/framework được load một lần rồi giữ hợp lệ. Điều quan trọng là *retired generation count/retaining paths* và xu hướng memory sau các pha tương đương.

## 18. Một số lỗi thiết kế dễ mắc

1. **Cache toàn process chỉ khóa theo tên class.** Hai generation trùng tên nhưng khác class identity/semantics.
2. **Không gắn generation vào owner và metrics.** Không phân biệt cache của bản A đã retire và bản B đang active.
3. **Dùng TTL thay teardown.** Loader A còn bị giữ suốt TTL, hoặc cache không được quét khi idle.
4. **Dùng weak key và nghĩ đã hết leak.** Value có thể tham chiếu ngược tới key/loader.
5. **Cho cache value chứa plugin instance nhưng owner là host singleton.** Root của host giữ loader cũ dù đã close.
6. **Chỉ đo tổng loaded classes.** Đây là counter tích lũy, không phải retained current classes.
7. **Nhìn RSS/Metaspace peak như retained memory.** Phải phân biệt peak, used, committed, post-GC và OS accounting.
8. **Đánh giá sau một lần reload.** Cần nhiều vòng và workload ổn định.
9. **Tạo strong reference trong chính leak detector.** Metrics/registry có thể biến thành thủ phạm.
10. **Đóng class loader trước khi drain task.** Task A còn dùng lazy class/resource có thể thất bại.
11. **Clear cache rồi cho task cũ computeIfAbsent lại.** Cache A có thể tái xuất hiện sau teardown.
12. **Dọn mọi cache toàn host khi retire A.** Làm hỏng B và tạo cache stampede; evict đúng owner.
13. **Đo trên một JDK/collector rồi suy ra chính xác mọi JVM.** GC/NMT/MemoryPool names và tuning phụ thuộc runtime.
14. **Chụp heap dump production mà không kiểm soát dữ liệu nhạy cảm.** HPROF có thể chứa toàn bộ objects/secrets.
15. **Coi `URLClassLoader.close()` là `unloadClass()`.** API không hứa điều đó.
16. **Dùng ClassValue rồi không dọn thread/callback.** Một loại cache đúng không loại bỏ đường giữ khác.
17. **Vừa đổi current generation vừa bỏ qua rollback.** Nếu B không hợp lệ, A có thể cần duy trì một thời gian, nhưng phải ghi rõ trạng thái ACTIVE/ROLLBACK và deadline giải phóng.
18. **Giải thích tăng native memory bằng heap dump mà không kiểm tra JNI/direct buffers.** Các lớp memory khác nhau cần công cụ khác nhau.

## 19. Checklist kiến trúc và kết luận

Trước khi phát hành runtime extensibility, hãy đi qua checklist:

- [ ] Mỗi lần cài đặt plugin có `pluginId` và `generationId` bất biến; defining loader được định danh trong log.
- [ ] Cache chứa class/provider/serializer/metadata của plugin có scope thuộc generation, hoặc global key + eviction contract tương đương.
- [ ] Host-global cache chỉ giữ dữ liệu thật sự độc lập code/loader hoặc được partition đúng tenant/version.
- [ ] Đã định nghĩa ACTIVE → DRAINING → RETIRED; chặn cache write mới khi generation cũ bắt đầu retire.
- [ ] Dừng/đợi callback và request in-flight trước khi dọn cache/đóng loader.
- [ ] Owner clear entry, close cache values/resources và gỡ registration handles, ThreadLocal, TCCL/threads đúng nơi.
- [ ] Có metrics **cache entries/weight và retired generation count** chứ không chỉ memory MB.
- [ ] JMX/GC/NMT/profiler được cấu hình theo môi trường và quyền hạn; so sánh memory ở các thời điểm tương đương.
- [ ] Heap analyzer có quy trình tìm **Path to GC Roots** khi loader retired còn reachable.
- [ ] Soak test nhiều lần replace + fault injection + race tests không dựa vào một lần `System.gc()`.
- [ ] Các chỉ số leak detector chỉ giữ metadata/weak probes, không giữ mạnh loader cũ.
- [ ] Đã kiểm tra hiệu năng sau eviction: cache hit rate, recomputation cost và latency của generation mới.

**Ghi nhớ:** *Phạm vi cache là quyết định về ownership và lifecycle, không chỉ là lựa chọn cấu trúc dữ liệu.* Cache lưu `Class<?>`/plugin instance phải gắn với **plugin generation** và được dọn khi generation retired. Để phát hiện memory tăng sau nhiều lần thay plugin, kết hợp **deterministic reference counts/eviction assertions**, **xu hướng heap/Metaspace/classloader qua nhiều vòng**, và **retaining paths từ GC roots**. Không dùng `URLClassLoader.close()`, weak references hoặc một lần gọi GC làm bằng chứng duy nhất.

**Tài liệu chính thức Java 17:** [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html), [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html), [ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html), [URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html), [java launcher / NMT options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html), [Java 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/).
