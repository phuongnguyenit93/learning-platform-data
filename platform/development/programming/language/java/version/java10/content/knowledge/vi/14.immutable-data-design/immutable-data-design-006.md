# Java 10 – Thiết kế dữ liệu chỉ đọc: Thay toàn bộ ảnh chụp cấu hình thay vì sửa tại chỗ

> **Bối cảnh:** Java 10 → **Thiết kế dữ liệu chỉ đọc** → **Thay toàn bộ ảnh chụp cấu hình thay vì sửa tại chỗ**. Nội dung tập trung vào kiến thức còn áp dụng trên Java 17+ và các JDK hiện đại. `Map.copyOf`, `List.copyOf` có từ Java 10; `Map.of`/`List.of` từ Java 9; `var` từ Java 10; `record` dùng trong ví dụ có từ Java 16. `volatile`, Java Memory Model và `AtomicReference` vẫn là cơ chế chuẩn để công bố/cập nhật state trong Java hiện đại.

## 1. Mục tiêu và kết luận cốt lõi

Sau bài học, bạn có thể:

1. Mô tả chiến lược **xây → kiểm tra → đóng băng → công bố → đọc một phiên bản** cho cấu hình dùng chung.
2. Giải thích vì sao **thay một tham chiếu tới snapshot hoàn chỉnh** thường phù hợp hơn sửa các phần tử Map/field của cấu hình đang được nhiều luồng sử dụng.
3. Dùng `Map.copyOf`, `List.copyOf`, value object/record và defensive copy để ngăn việc sửa nguồn làm hỏng cấu hình đã công bố.
4. Chọn `volatile` khi chỉ cần công bố một phiên bản mới, và `AtomicReference`/CAS/lock khi có nhiều writer cần hợp nhất cập nhật.
5. Hiểu quan hệ `happens-before`, vì sao `volatile Map` không làm `HashMap.put` thread-safe, và vì sao unmodifiable collection không tự deep-immutable.
6. Giữ tính nhất quán của mỗi request bằng cách lấy một local snapshot thay vì đọc registry nhiều lần.
7. Tránh mất cập nhật (lost update) với thao tác read-modify-write, đồng thời viết callback `updateAndGet` không có side effect.
8. Đánh giá versioning, validation, rollback, resource lifecycle và chi phí copy của snapshot.
9. Chạy và phân tích chương trình Java 17+ có hai writer cập nhật đồng thời, snapshot cũ và snapshot mới.

**Nguyên tắc:** Khi dữ liệu cấu hình được **đọc rất thường xuyên nhưng cập nhật hiếm**, hãy tạo một immutable snapshot mới, **công bố một reference** và cho reader đọc **một reference mỗi lượt xử lý**. Không mutate phiên bản đã công bố.

## 2. Vấn đề khi sửa cấu hình đang chia sẻ tại chỗ

Một dịch vụ có ba giá trị liên quan: bật tính năng, địa chỉ máy chủ và giới hạn retry. Đoạn dưới chỉ là minh họa về state rời rạc:

~~~java
class SharedConfig {
    volatile boolean enabled;
    volatile String endpoint;
    volatile int retryLimit;
}
~~~

Writer cập nhật:

~~~java
config.enabled = true;
config.endpoint = "api-v2";
config.retryLimit = 5;
~~~

Reader có thể chạy **giữa các phép ghi** và quan sát `enabled=true`, `endpoint` vẫn là `api-v1`. Mỗi field `volatile` có visibility/ordering của riêng nó, nhưng Java **không** biến chuỗi ba phép ghi thành một transaction. Nếu reader đọc từng field riêng, không có cam kết cả ba thuộc cùng phiên bản cấu hình nghiệp vụ.

Trường hợp map:

~~~java
class RiskyConfigStore {
    private volatile java.util.Map<String, String> settings =
            new java.util.HashMap<>();

    void update(String key, String value) {
        settings.put(key, value); // Không an toàn nếu nhiều thread truy cập
    }
}
~~~

`volatile` áp dụng cho **việc đọc/ghi reference của field**, không tự đồng bộ phép `put`/`remove` trên HashMap bên trong. Khi có concurrent mutation không bảo vệ, việc đọc/duyệt HashMap có thể race hoặc cho kết quả không nhất quán. Thậm chí `ConcurrentHashMap` giúp thao tác trên entry thread-safe theo hợp đồng riêng cũng **không tự cung cấp một snapshot nguyên tử của nhiều key** nếu nghiệp vụ yêu cầu chúng phải cùng đổi.

Suy ra: Nếu một nhóm field/mapping cần nhất quán ở mức **toàn bộ phiên bản**, hãy đóng gói nhóm đó trong **một object state** thay vì dựa vào cập nhật nhiều ô độc lập.

## 3. Mô hình build → validate → freeze → publish → read

~~~text
Writer / config-reload pipeline
    |
    +--> Parse input và chuẩn hóa
    +--> Validate toàn bộ điều kiện liên quan
    +--> Dựng state mới, không lộ mutable builder
    +--> Defensive copy và chốt phần tử immutable
    |
    v
Immutable Config(generation N+1)
    |
    +--> volatile write hoặc AtomicReference update
    |
    v
Registry.current ---> Config(N+1)
    |
    +--> Reader đọc current MỘT lần
    |
    v
Local snapshot -> xử lý toàn bộ request
~~~

Ý nghĩa từng bước:

1. **Build:** dựng cấu hình mới trong một phạm vi do writer sở hữu; không đưa object đang dở dang cho reader.
2. **Validate:** kiểm tra endpoint, quyền, giới hạn, null, xung đột cross-field và version.
3. **Freeze:** chuyển mutable builders thành các cấu trúc immutable/unmodifiable với immutable elements.
4. **Publish:** chuyển reference tới object hoàn chỉnh bằng cơ chế có memory semantics phù hợp.
5. **Read:** reader lấy một reference, dùng thống nhất toàn bộ các trường của snapshot ấy.
6. **Replace:** khi reload tiếp, dựng object khác và thay reference; **không sửa object cũ**.

Trong mô hình này, reader A có thể giữ snapshot phiên bản N trong khi reader B bắt đầu sau khi publish và dùng N+1. Đây là **tính nhất quán theo phiên bản trong từng lần xử lý**, không bắt buộc mọi request đang chạy đồng loạt chuyển phiên bản tức thời. Khi không còn ai giữ N, garbage collector có thể thu hồi dữ liệu N.

### 3.1. Dùng immutable state làm đơn vị thay thế

Ví dụ Java 17+:

~~~java
record AppConfig(long generation,
                 java.util.Map<String, String> flags,
                 java.util.List<String> endpoints) {
    AppConfig {
        if (generation < 0) {
            throw new IllegalArgumentException("negative generation");
        }
        flags = java.util.Map.copyOf(flags);
        endpoints = java.util.List.copyOf(endpoints);
    }
}
~~~

`record` có thể dùng như data carrier. Trong compact constructor, các tham số `flags`/`endpoints` được thay bằng collection đã chốt trước khi gán cho record components. `String` là immutable, nên ví dụ này có cấu trúc ổn định sau khi tạo. Field `generation` thể hiện phiên bản logic; có thể log và kiểm tra các yêu cầu monotonic version.

**Chú ý:** Record không tự deep-copy tất cả component. Nếu một component là `byte[]`, `StringBuilder`, `List<MutablePolicy>` hay entity có setter, cần xử lý sao chép phòng vệ hoặc chuyển thành immutable value object.

## 4. Tận dụng Java 10: `Map.copyOf` và `List.copyOf`

### 4.1. Tách cấu trúc khỏi nguồn mutable

~~~java
var builder = new java.util.HashMap<String, String>();
builder.put("mode", "safe");
var frozen = java.util.Map.copyOf(builder);

builder.put("mode", "unsafe");
System.out.println(builder.get("mode")); // unsafe
System.out.println(frozen.get("mode"));  // safe
~~~

Khi thao tác copy hoàn tất đúng cách, `Map.copyOf` trả một **Map không thể sửa mapping**; những lần sửa nguồn về sau không làm thay đổi mapping của kết quả. Tương tự:

~~~java
var sourceHosts = new java.util.ArrayList<>(
        java.util.List.of("api-primary"));
var snapshotHosts = java.util.List.copyOf(sourceHosts);
sourceHosts.add("api-secondary");

System.out.println(snapshotHosts); // [api-primary]
~~~

Hai API `copyOf` từ Java 10 đặc biệt phù hợp ở **ranh giới chuyển từ builder mutable sang state chỉ đọc**.

### 4.2. Phân biệt unmodifiable **view** với snapshot cấu trúc

~~~java
var backing = new java.util.HashMap<String, String>();
backing.put("feature", "off");
var view = java.util.Collections.unmodifiableMap(backing);
var detached = java.util.Map.copyOf(backing);

backing.put("feature", "on");
System.out.println(view.get("feature"));     // on
System.out.println(detached.get("feature")); // off
~~~

`Collections.unmodifiableMap` trả một wrapper **view** không cho gọi mutator thông qua wrapper nhưng phản ánh sửa đổi của backing Map qua alias khác. `Map.copyOf` là lựa chọn thích hợp khi cần **không phản ánh cập nhật mapping của nguồn** sau copy.

Không được suy luận rằng mọi object có tên “unmodifiable” đều độc lập khỏi nguồn. Nếu đã có Map unmodifiable phù hợp, Java có thể **tái sử dụng instance** trong `copyOf`; API không hứa `==` luôn true hoặc luôn false. Dùng nội dung và hợp đồng, không dùng identity hay tên implementation class.

### 4.3. Shallow copy khác deep immutability

~~~java
final class MutablePolicy {
    private int maxRetries;
    MutablePolicy(int maxRetries) { this.maxRetries = maxRetries; }
    int maxRetries() { return maxRetries; }
    void change(int value) { maxRetries = value; }
}

var policy = new MutablePolicy(3);
var map = java.util.Map.copyOf(
        java.util.Map.of("primary", policy));

policy.change(9);
System.out.println(map.get("primary").maxRetries()); // 9
~~~

`Map.copyOf` **không** copy object `MutablePolicy`. Nó giữ reference value và bảo vệ cấu trúc Map; nếu value bị mutate qua alias, reader vẫn thấy thay đổi. Nếu nhiều thread mutate/read value không đồng bộ, snapshot Map không tự giải quyết data race đó.

Chọn cách khắc phục theo domain:

- Dùng immutable value object như `record Policy(int maxRetries) {}`.
- Sao chép riêng từng object mutable sang DTO immutable.
- Không công bố reference tới builder/source còn được tiếp tục sửa.
- Với array primitive, `clone()` ở constructor/getter hoặc biểu diễn bằng immutable collection có thể cần thiết; với array object mutable, clone array vẫn chưa deep-copy element.
- Dùng immutable key để `equals`/`hashCode` không đổi sau khi đưa vào Map.

### 4.4. Null, thứ tự, identity

| Thuộc tính | Hợp đồng thích hợp |
| --- | --- |
| `Map.copyOf` | Từ chối source null, key null, value null; Map kết quả unmodifiable |
| `List.copyOf` | Từ chối source/element null; List kết quả unmodifiable |
| Thứ tự `List.copyOf` | Bảo toàn thứ tự encounter của source phù hợp |
| Thứ tự `Map.copyOf` | Không cam kết iteration order, kể cả source là LinkedHashMap |
| Phần tử lồng nhau | Không deep-copy key/value hoặc List element |
| Cấp phát mới | Có thể reuse nguồn unmodifiable phù hợp; không hứa identity |
| Thực hiện đồng thời với source mutable bị sửa | Không tự tạo snapshot atomic; cần phối hợp writer và copier |

Nếu cần endpoint ưu tiên theo thứ tự, nên giữ `List<String>` hơn là suy ra thứ tự từ `Map.copyOf`.

## 5. `volatile`: công bố toàn bộ một state qua một reference

Một store đơn giản:

~~~java
final class VolatileConfigStore {
    private volatile AppConfig current;

    VolatileConfigStore(AppConfig initial) {
        current = java.util.Objects.requireNonNull(initial);
    }

    AppConfig snapshot() {
        return current; // volatile read
    }

    void replace(AppConfig next) {
        current = java.util.Objects.requireNonNull(next); // volatile write
    }
}
~~~

Writer xây `AppConfig` mới hoàn chỉnh **trước** phép gán `current`. Reader đọc `current` thông qua volatile read và nhận một object snapshot đã được công bố đúng theo Java Memory Model. Một phép ghi volatile vào field happens-before các volatile read phù hợp sau đó theo synchronization order của cùng field; nhờ vậy các ghi xây dựng trước publish được quan sát theo quan hệ HB.

`volatile` giúp **visibility/ordering của reference**, không biến object mà reference trỏ tới thành immutable. Khi snapshot chứa mutable elements hoặc writer tiếp tục sửa chính object đã publish, code vẫn có thể race.

**Giới hạn quan trọng:**

- Gán một tham chiếu là một thao tác; không có “nửa reference”.
- Người đọc có thể thấy phiên bản cũ hoặc mới tùy vị trí đọc trong lịch trình cập nhật.
- Một lần đọc một snapshot immutable cho nhóm field nhất quán; **hai lần đọc registry liên tiếp có thể trả hai phiên bản**.
- `volatile` không biến ba phép ghi vào ba field thành atomic transaction.
- `volatile` không tự giải quyết lost update của nhiều writer.
- Các cơ chế này áp dụng trong **một JVM/process**; không tự làm mọi server/distributed cache đổi config nguyên tử.

### 5.1. Chốt local snapshot một lần

Ví dụ **không phù hợp** khi mode và endpoint phải thuộc cùng version:

~~~java
// Hai lời gọi snapshot() có thể trả hai generation khác nhau:
if ("fast".equals(store.snapshot().flags().get("mode"))) {
    callEndpoint(store.snapshot().endpoints().get(0));
}
~~~

`callEndpoint` là phương thức giả định của ứng dụng. Reader có thể đọc mode của N rồi endpoint của N+1 nếu writer công bố giữa hai lần.

Cách nên dùng:

~~~java
var cfg = store.snapshot();
if ("fast".equals(cfg.flags().get("mode"))) {
    var endpoint = cfg.endpoints().get(0);
    callEndpoint(endpoint);
}
~~~

Giữ reference `cfg` cố định cho toàn bộ request hoặc operation. Các method nội bộ nên nhận `cfg` thay vì tự truy vấn store nhiều lần khi cần cùng version.

### 5.2. Tại sao đọc immutable snapshot có thể không cần lock mỗi field?

Khi object đã được xây xong, các phần tử đều immutable/không còn mutation, và reference được công bố qua cơ chế HB, các reader chỉ đọc có thể duyệt/lookup snapshot mà không cần monitor riêng trên từng Map entry. Đây là ưu điểm lớn trong hệ thống read-heavy. Khi cập nhật, writer chịu chi phí xây/copy/publish phiên bản mới.

Đừng dùng object từ `Map.of`, `List.of` hoặc `copyOf` như monitor `synchronized` chỉ vì thấy nó có thể được tái sử dụng: unmodifiable factory objects được mô tả là value-based, identity không được khuyên dựa vào để khóa. Khi cần lock, tạo object riêng do ứng dụng sở hữu.

## 6. Nhiều writer và lỗi `lost update`

Tưởng tượng snapshot ban đầu:

~~~text
generation = 0
flags = {}
~~~

Writer A và writer B cùng đọc version 0. A tạo Map mới có `alpha=on`; B tạo Map mới có `beta=on`. Nếu cả hai gọi `store.replace(...)` từ các bản old độc lập, lần `set` sau có thể ghi đè **toàn bộ** bản của lần trước. Kết quả chỉ còn một key.

Lỗi không phải vì phép gán tham chiếu bị xé: từng `set` có thể hoàn toàn nguyên tử, nhưng chuỗi thao tác **read → build → set** không nguyên tử như một cập nhật dựa trên giá trị cũ.

### 6.1. `AtomicReference.updateAndGet` giải quyết cập nhật phụ thuộc state cũ

~~~java
final class AtomicConfigStore {
    private final java.util.concurrent.atomic.AtomicReference<AppConfig> current;

    AtomicConfigStore(AppConfig initial) {
        current = new java.util.concurrent.atomic.AtomicReference<>(initial);
    }

    AppConfig snapshot() {
        return current.get();
    }

    void putFlag(String key, String value) {
        current.updateAndGet(old -> {
            var nextFlags = new java.util.HashMap<>(old.flags());
            nextFlags.put(key, value);
            return new AppConfig(old.generation() + 1,
                                 nextFlags, old.endpoints());
        });
    }
}
~~~

`updateAndGet` thực hiện cập nhật dựa trên state mà nó đọc và thử thay bằng compare-and-set. Nếu một writer khác thay reference trước, thuật toán có thể **gọi lại function** với state mới; nhờ đó không mất update do hai writer dùng cùng old snapshot.

**Bắt buộc:** Hàm `old -> new AppConfig(...)` nên **không có side effects bên ngoài**. Không gửi email, ghi database, phát event, tính phí, log một hành động không idempotent hoặc commit giao dịch trong callback — nó có thể chạy lại khi contention. Nên tách side effect sau bước cập nhật thành công và quản lý exactly-once/idempotency ở tầng phù hợp.

### 6.2. `compareAndSet` và version conflict

~~~java
var old = reference.get();
var candidate = transform(old); // giả định hàm thuần
boolean published = reference.compareAndSet(old, candidate);
~~~

Đây là **đoạn minh họa**, với `reference` kiểu `AtomicReference<AppConfig>` và `transform` do chương trình định nghĩa. `compareAndSet` so sánh **reference identity** của expected old; nếu false, caller có thể retry với state hiện tại hoặc báo xung đột. Dùng generation/version token riêng cho ý nghĩa domain và khi cần đối phó vấn đề ABA.

Không nhầm identity của object state do ứng dụng quản lý cho CAS với identity của value-based `Map.copyOf`/`List.copyOf`: **không dùng identity collection factory-produced làm ID phiên bản**.

### 6.3. Khi nào `set` vẫn là lựa chọn đúng?

Nếu nguồn cung cấp **một cấu hình đầy đủ** và policy là “bản được phê duyệt mới thay thế hoàn toàn bản trước”, `AtomicReference.set` hoặc field `volatile` đủ để publish một reference. Nhưng nếu nhiều loader có thể hoàn thành **không theo thứ tự version** (bản cũ tải chậm về sau), nên kiểm tra version monotonic và điều phối bằng CAS/lock để không vô tình rollback.

Nếu có nhiều writer thay các phần **khác nhau** của state, cần hợp nhất bằng `updateAndGet`/CAS/lock thay vì blind replace dựa trên snapshot cũ.

## 7. Nhất quán giữa các field: một state thay vì nhiều volatile fields

Với trạng thái:

~~~java
record RoutePolicy(boolean enabled, String endpoint, int retryLimit) {}
~~~

registry giữ:

~~~java
private volatile RoutePolicy current =
        new RoutePolicy(false, "api-v1", 1);
~~~

Writer tạo `new RoutePolicy(true, "api-v2", 5)` rồi gán:

~~~java
current = new RoutePolicy(true, "api-v2", 5);
~~~

Reader đọc một lần:

~~~java
var snapshot = current;
// Các accessor trên snapshot đọc cùng một phiên bản.
~~~

Đây là các đoạn mã minh họa **bên trong một class**, không phải file độc lập. Nếu object `RoutePolicy` immutable và không bị mutate sau khi publish, reader không quan sát “enabled mới, endpoint cũ” từ **cùng object snapshot**. Việc writer thay một reference giúp bảo toàn các invariant cross-field đã validate.

Nhưng không được mở rộng khẳng định này thành “thay một JVM reference là một giao dịch phân tán”: database, connection pool, remote service, cache trên host khác và các tác dụng phụ bên ngoài có lifecycle riêng. Phải dùng version coordination/transaction/rollout protocol nếu muốn các hệ thống đó chuyển cùng nhau.

## 8. Pipeline reload đáng tin: validate trước rồi publish

~~~text
Nhận config mới
   ↓
Parse/normalize/validate input
   ↓
Kiểm tra invariant xuyên field, null, quyền, version
   ↓
Dựng object immutable và defensive-copy Map/List
   ↓
Candidate có hợp lệ hoàn toàn?
   ├── Không → giữ snapshot cũ; báo lỗi rõ
   └── Có
         ↓
   Kiểm tra conflict/version nếu nhiều writer
         ↓
   Publish đúng một reference
         ↓
   Ghi log/metrics generation và điều phối resource lifecycle
~~~

Các điều kiện nên xem xét:

- Nếu feature bật, endpoint và thông số retry phải hợp lệ.
- Key/value/element null có được cho phép không; `Map.copyOf`/`List.copyOf` từ chối null.
- Các ID/khóa trùng có được xử lý theo một chính sách rõ ràng trước khi tạo Map.
- Version/generation có được yêu cầu tăng đơn điệu, nguồn dữ liệu có timestamp đáng tin không.
- Các rule bảo mật, allowlist, tenant scope hoặc quota đã được kiểm tra.
- Builder có còn alias dẫn tới object lồng nhau mutable sau publish không.
- Tài nguyên ngoài config (connection, file descriptor, credential lease) cần tạo/đóng theo phiên bản như thế nào.

Nếu parse/validate thất bại, **không sửa current**, vì reader vẫn cần dùng bản hợp lệ trước đó. Đây là tính chất “all-or-nothing publication” tại JVM; không cần rollback từng field như cách sửa tại chỗ.

### 8.1. Versioning và rollback

Đưa `generation` vào immutable state giúp log “request dùng config N”, so sánh trước/sau, phân biệt loader cũ hoàn tất chậm, kiểm tra monotonicity và audit. Rollback nên được thực hiện bằng việc **công bố một snapshot hợp lệ** theo policy phiên bản, không dùng một chuỗi thao tác sửa từng key của bản đang phục vụ.

Đừng dùng `System.identityHashCode` hoặc `Map == otherMap` để làm generation token. Với factory collections, identity không phải hợp đồng phiên bản.

### 8.2. Old request tiếp tục dùng snapshot cũ

~~~text
T0: registry.current → generation 1
    Request A đọc reference generation 1

T1: Writer validate xong generation 2
T2: Writer publish một reference → generation 2

T3: Request A vẫn dùng generation 1
    Request B đọc registry và dùng generation 2
~~~

Đây là hành vi dự kiến; không có mutation trên generation 1. Các request cũ có thể làm snapshot cũ còn sống cho tới khi hoàn tất. Nếu business yêu cầu dừng ngay mọi request dùng config cũ, bạn cần barrier/cancellation/graceful drain, không được giả định một phép `volatile set` tự hủy các task đó.

## 9. Ví dụ Java 17+ độc lập đã kiểm chứng

Chương trình minh họa:

- Input Map/List mutable được sửa sau khi tạo `AppConfig`, nhưng snapshot đã chốt không đổi.
- Writer thread publish generation 2 qua `volatile` reference, reader giữ generation 1 vẫn đọc được old state.
- `Collections.unmodifiableMap` live view khác `Map.copyOf` detached structural snapshot.
- Hai writer cùng update thông qua `AtomicReference.updateAndGet`, kết quả có cả hai key và generation tăng hai lần.
- Output có thứ tự ổn định: dùng `TreeSet` khi in key từ Map; dùng `Thread.join` để bảo đảm test hoàn tất. `join` cũng tạo happens-before nên demo không phải benchmark isolating visibility của `volatile`.

Lưu file đúng tên **`ConfigSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeSet;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class ConfigSnapshotDemo {
    record AppConfig(long generation, Map<String, String> flags,
                     List<String> endpoints) {
        AppConfig {
            if (generation < 0) {
                throw new IllegalArgumentException("negative generation");
            }
            flags = Map.copyOf(flags);
            endpoints = List.copyOf(endpoints);
        }
    }

    static final class VolatileConfigStore {
        private volatile AppConfig current;

        VolatileConfigStore(AppConfig initial) {
            current = Objects.requireNonNull(initial);
        }

        AppConfig snapshot() {
            return current;
        }

        void replace(AppConfig next) {
            current = Objects.requireNonNull(next);
        }
    }

    static final class AtomicConfigStore {
        private final AtomicReference<AppConfig> current;

        AtomicConfigStore(AppConfig initial) {
            current = new AtomicReference<>(Objects.requireNonNull(initial));
        }

        AppConfig snapshot() {
            return current.get();
        }

        void putFlag(String key, String value) {
            current.updateAndGet(old -> {
                var nextFlags = new HashMap<>(old.flags());
                nextFlags.put(key, value);
                return new AppConfig(old.generation() + 1,
                                     nextFlags, old.endpoints());
            });
        }
    }

    public static void main(String[] args) throws InterruptedException {
        var inputFlags = new HashMap<String, String>();
        inputFlags.put("mode", "safe");
        var inputEndpoints = new ArrayList<>(List.of("api-primary"));

        var initial = new AppConfig(1, inputFlags, inputEndpoints);
        inputFlags.put("mode", "unsafe");
        inputEndpoints.add("api-secondary");
        System.out.println("initial-mode=" + initial.flags().get("mode"));
        System.out.println("initial-endpoints=" + initial.endpoints().size());

        var store = new VolatileConfigStore(initial);
        var before = store.snapshot();
        var newFlags = new HashMap<>(before.flags());
        newFlags.put("mode", "fast");
        var replacement = new AppConfig(2, newFlags, List.of("api-v2"));
        var publisher = new Thread(() -> store.replace(replacement));
        publisher.start();
        publisher.join();
        var after = store.snapshot();
        System.out.println("before-generation=" + before.generation());
        System.out.println("before-mode=" + before.flags().get("mode"));
        System.out.println("after-generation=" + after.generation());
        System.out.println("after-mode=" + after.flags().get("mode"));
        System.out.println("after-endpoints=" + after.endpoints());

        try {
            after.flags().put("mode", "override");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot-mutation=blocked");
        }

        var backing = new HashMap<String, String>();
        backing.put("feature", "off");
        var liveView = Collections.unmodifiableMap(backing);
        var detached = Map.copyOf(backing);
        backing.put("feature", "on");
        System.out.println("live-view=" + liveView.get("feature"));
        System.out.println("detached=" + detached.get("feature"));

        var atomic = new AtomicConfigStore(
                new AppConfig(0, Map.of(), List.of()));
        var atomicBefore = atomic.snapshot();
        var go = new CountDownLatch(1);
        Thread one = new Thread(() -> {
            try {
                go.await();
                atomic.putFlag("alpha", "on");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });
        Thread two = new Thread(() -> {
            try {
                go.await();
                atomic.putFlag("beta", "on");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            }
        });
        one.start();
        two.start();
        go.countDown();
        one.join();
        two.join();

        var combined = atomic.snapshot();
        System.out.println("atomic-generation=" + combined.generation());
        System.out.println("atomic-flags=" + new TreeSet<>(combined.flags().keySet()));
        System.out.println("old-atomic-still-empty=" + atomicBefore.flags().isEmpty());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ConfigSnapshotDemo.java
java ConfigSnapshotDemo
~~~

**Stdout chính xác** (đã biên dịch và chạy thành công trên JDK hiện có):

~~~text
initial-mode=safe
initial-endpoints=1
before-generation=1
before-mode=safe
after-generation=2
after-mode=fast
after-endpoints=[api-v2]
snapshot-mutation=blocked
live-view=on
detached=off
atomic-generation=2
atomic-flags=[alpha, beta]
old-atomic-still-empty=true
~~~

### 9.1. Phân tích các kết quả

1. `initial-mode=safe`, `initial-endpoints=1`: thay đổi Map/List nguồn sau khi record đã tạo không thay đổi cấu trúc snapshot.
2. `before-generation=1`, `before-mode=safe`: reader cầm snapshot phiên bản cũ.
3. `after-generation=2`, `after-mode=fast`, `after-endpoints=[api-v2]`: sau publish, registry trỏ tới một object mới đã đầy đủ các field.
4. `snapshot-mutation=blocked`: Map trong record không cho `put`.
5. `live-view=on`, `detached=off`: wrapper view vẫn phản ánh backing Map, trong khi Map.copyOf không nhận sửa đổi sau copy.
6. `atomic-generation=2` và `atomic-flags=[alpha, beta]`: hai writer cùng thêm flag riêng, `updateAndGet` bảo toàn hai cập nhật.
7. `old-atomic-still-empty=true`: người đọc đã cầm snapshot cũ không bị đổi state khi registry update.

### 9.2. Giới hạn của demo

`Thread.join()` cũng tạo happens-before và dùng để chờ kết thúc nên không thể dùng output này làm phép đo hiệu lực của `volatile` một cách riêng biệt. Ví dụ không thực hiện I/O network, không chứng minh mọi lịch trình đồng thời, không tự xử lý phân phối config qua nhiều JVM, và không deep-immutable mọi kiểu phần tử có thể có. Tính đúng đắn cần được lập luận bằng **Java Memory Model + immutable snapshot + giao thức update**.

## 10. Những trường hợp cần đánh giá kỹ

### 10.1. Builder mutable vẫn còn reference sau publish

Không được dựng một `Map` mới rồi publish trực tiếp nó, sau đó tiếp tục `put` trên chính Map ấy:

~~~java
// Phản ví dụ:
var builder = new HashMap<String, String>();
builder.put("mode", "safe");
// current = builder; // Nếu current chia sẻ mutable Map, builder còn alias
builder.put("mode", "unsafe");
~~~

Nếu muốn snapshot độc lập, dùng `Map.copyOf(builder)` tại ranh giới và không để mutable nested objects tiếp tục bị sửa. Một instance record dùng `Map.copyOf` trong constructor giúp thực thi invariant ở mỗi nơi khởi tạo.

### 10.2. Source bị sửa **đồng thời trong lúc copy**

~~~java
// Thread A: mutableMap.put(...)
// Thread B: Map.copyOf(mutableMap)
~~~

`Map.copyOf` không phải cơ chế khóa. Copy từ `HashMap` đang mutate không đồng bộ có thể race/không nhất quán. Nếu source dùng chung, bảo vệ cả update lẫn copy bằng cùng monitor, hoặc chuẩn bị riêng một bản mới trước khi công bố.

### 10.3. Array hoặc object lồng nhau mutable

~~~java
record ByteSnapshot(byte[] content) {
    ByteSnapshot {
        content = content.clone();
    }
    @Override
    public byte[] content() {
        return content.clone();
    }
}
~~~

Với array primitive, copy ở constructor và getter giúp tránh caller làm đổi mảng nội bộ. Với array object mutable hoặc List chứa entity có setter, cần thêm chính sách copy/immutable element riêng.

### 10.4. `final` không giống bất biến

~~~java
final var map = new java.util.HashMap<String, String>();
map.put("mode", "fast"); // vẫn hợp lệ
~~~

`final` chỉ ngăn gán lại reference; Map vẫn mutable. Tương tự, `volatile` không tự ngăn mutation, còn `Map.copyOf` không tự làm thread-safe mọi value object chứa trong Map.

## 11. Trình tự reload đáng tin trong production

Một flow được kiểm soát có thể gồm:

1. Nhận dữ liệu cấu hình mới từ file, database hoặc config service.
2. Parse, normalize và kiểm tra kiểu.
3. Xác thực invariant xuyên field, ID, null, endpoint, retry limit và quyền truy cập.
4. Chuyển dữ liệu lồng nhau sang immutable value objects; `Map.copyOf`/`List.copyOf` sau khi đã hoàn tất builder.
5. Gắn `generation`/`version` rõ ràng; từ chối bản cũ nếu cần monotonicity.
6. Chọn một writer hoặc cơ chế CAS/lock để thực hiện publish không mất update.
7. Công bố **một reference duy nhất**.
8. Log generation có kiểm soát, cập nhật metrics và điều phối lifecycle tài nguyên ngoài state.
9. Cho request đang dùng bản cũ hoàn tất theo policy; giữ bản cũ còn sống nếu request vẫn tham chiếu.
10. Nếu cần rollback, **công bố lại một snapshot hợp lệ**; không tự sửa từng key của snapshot đang phục vụ.

Nếu validate thất bại, nên **giữ nguyên current** và báo lỗi cụ thể, thay vì publish object dở dang rồi cố sửa tiếp. Đây là một lợi thế quan trọng khi thay thế toàn bộ snapshot.

### 11.1. Version chống loader cũ ghi đè loader mới

Nếu loader A bắt đầu trước nhưng hoàn tất sau loader B, thao tác `set` đơn thuần có thể publish bản A có version cũ. Nếu domain không cho downgrade, dùng kiểm tra version và CAS/lock:

~~~java
registry.updateAndGet(old -> {
    if (candidate.generation() <= old.generation()) {
        return old;
    }
    return candidate;
});
~~~

Đoạn này là minh họa với `registry` kiểu `AtomicReference<AppConfig>` và `candidate` đã validate. Không làm I/O trong callback. Quy tắc “version lớn hơn” cần phù hợp với dữ liệu nguồn thật: nếu có restart/reset generation hoặc nhiều source độc lập, hãy xác định thứ tự phiên bản cẩn thận.

### 11.2. Resource lifecycle không nằm gọn trong Map

Thay config trỏ tới endpoint mới không tự động mở connection mới một cách nguyên tử cùng database, và cũng không tự đóng connection cũ an toàn cho request đang chạy. Khi các tài nguyên bên ngoài phải được chuyển tiếp, dùng state/resource holder theo phiên bản, cơ chế drain, rollback và coordination riêng. Snapshot replacement chỉ giải quyết **công bố một state logic trong JVM**.

## 12. Hiệu năng và khi nào không nên dùng snapshot replacement

| Hoàn cảnh | Cách chọn | Lưu ý |
| --- | --- | --- |
| Nhiều reader, ít writer, config nhỏ/vừa | Immutable snapshot + `volatile` | Hot-path read nhẹ, writer copy |
| Nhiều writer, mỗi người cập nhật một key trong cùng state | `AtomicReference` + CAS/updateAndGet hoặc lock | Có thể retry và copy nhiều lần |
| Map rất lớn, cập nhật từng entry liên tục | Concurrent Map hoặc thiết kế phân vùng state | Không tự có snapshot nhất quán nhiều key |
| Config thay hoàn toàn theo nguồn duy nhất | Build/validate/freeze rồi `set` | Có thể cần version monotonic |
| Reader cần tất cả field cùng generation | Một immutable object state, đọc một lần | Giữ reference xuyên call chain |
| Cấu hình gắn với connection dài sống | Versioned resource lifecycle + snapshot | Cần xử lý drain/cleanup |
| State khởi tạo một lần, không reload | Immutable `static final` hoặc constructor injection | Không cần dynamic registry |

Chi phí phải xét theo **số phần tử cần copy, kích thước object graph, nhịp cập nhật và thời gian request giữ snapshot**. Khi nhiều generation còn được reader giữ, memory footprint tăng tạm thời. `Map.copyOf` có thể tái sử dụng nguồn unmodifiable phù hợp; đây là tối ưu hóa implementation chứ không phải lời hứa identity hoặc tốc độ. Không khẳng định mọi `copyOf` luôn `O(1)` hay zero allocation.

## 13. Lỗi thường gặp khi review code

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Sửa riêng nhiều volatile fields | Không có transaction trên cả nhóm | Immutable state + một reference |
| `volatile Map` khiến `put` thread-safe | Chỉ reference có volatile semantics | Tránh mutate sau publish |
| `Collections.unmodifiableMap` là detached snapshot | Đây là live view của backing Map | `Map.copyOf` trên source ổn định |
| `Map.copyOf` deep-copy value object | Chỉ chốt mapping/tham chiếu phần tử | Immutable values/defensive copy |
| Record tự deep-immutable | Mutable component vẫn mutable | Compact constructor và copy sâu khi cần |
| Gọi snapshot nhiều lần trong một request | Có thể mix generation N và N+1 | Đọc một lần vào local variable |
| Hai writer cùng read rồi set | Có thể lost update | CAS/updateAndGet/lock |
| Callback `updateAndGet` có side effect | CAS có thể retry | Hàm thuần, effect sau khi commit |
| Copy Map khi writer khác mutate Map | Không có consistent snapshot atomic | Đồng bộ hoặc build dữ liệu riêng |
| Dựa identity của Map factory | Value-based Map không hứa identity | Dùng generation/token logic |
| Dựa iteration order `Map.copyOf` | Không được bảo đảm | Dùng List/sort |
| Một JVM set là toàn bộ distributed transaction | Không phối hợp process/service khác | Version/rollout protocol |
| Publish trước validate xong | Reader thấy state sai hoặc nửa hợp lệ | Validate trước publish |
| Nghĩ old readers tự chuyển sang new | Họ giữ reference cũ | Policy drain/barrier khi cần |
| Chạy test một lần không thấy race | Không chứng minh absence of race | Lập luận JMM và test đúng invariant |

## 14. Checklist kiểm thử và vận hành

Khi đưa thiết kế này vào code thật, kiểm tra:

1. Sau khi tạo snapshot, sửa source mutable có làm snapshot đổi mapping/list không? Kết quả mong muốn: **không**.
2. Các thao tác mutator trên snapshot có bị từ chối? Kết quả: `UnsupportedOperationException` ở collection unmodifiable.
3. Object value/element có còn alias mutable có thể được sửa không?
4. Khi reload lỗi validate, reference hiện tại có giữ bản hợp lệ cũ không?
5. Một request đọc một snapshot có luôn dùng cùng generation xuyên hàm gọi không?
6. Khi writer publish N+1, reader giữ N có còn đọc N ổn định không?
7. Với hai writer dùng state cũ, có lost update không? Đã áp dụng CAS/lock?
8. Có chính sách rõ ràng khi version cũ hoàn thành sau version mới không?
9. Callback `updateAndGet` có side effects có thể bị chạy lại không?
10. Có null keys/values/elements trong nguồn `copyOf` không?
11. Có cần thứ tự config entries không? Nếu có, đừng dựa vào `Map.copyOf` order.
12. Reader đang dùng resource liên quan phiên bản cũ có được graceful drain không?
13. Test có tránh `assertSame`/`assertNotSame` trên Map factory-produced không?
14. Có đo GC/latency ở nhịp reload thật, thay vì giả định copy rẻ hoặc đắt?
15. Có ghi lại generation và lỗi reload để chẩn đoán mà không tiết lộ thông tin nhạy cảm trong config không?

**Về concurrency test:** Một stress test không thấy lỗi không chứng minh chương trình không có data race. Dựa vào JMM/happens-before và kiểm thử các invariant có thể quan sát. Dùng `CountDownLatch`/`join` để điều phối kiểm thử, không dùng `Thread.sleep` như bảo đảm đồng bộ.

## 15. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Tại sao ba field `volatile` riêng không đảm bảo reader thấy một bộ cấu hình cùng version?

**Đáp án:** Các field được cập nhật bằng các phép ghi khác nhau. Reader có thể chạy giữa chúng và trộn các giá trị trước/sau cập nhật; volatile không tạo transaction nhiều field.

**Câu 2.** `volatile Map<String,String> cfg = new HashMap<>()` có làm nhiều thread cùng `cfg.put(...)` an toàn không?

**Đáp án:** Không. Volatile chỉ áp dụng cho reference field, không biến HashMap thành concurrent map.

**Câu 3.** Sửa nguồn sau `Map.copyOf(source)` có làm result nhận mapping mới không?

**Đáp án:** Không khi copy hoàn tất hợp lệ; result không phản ánh thay đổi mapping của source sau đó. Nó không deep-copy object value.

**Câu 4.** `Collections.unmodifiableMap(source)` có tách nội dung khỏi source mutable không?

**Đáp án:** Không. Đây là wrapper live view; sửa source qua alias có thể hiện ra khi đọc view.

**Câu 5.** `record Config(Map<String,String> flags)` có tự sao chép Map trong constructor mặc định không?

**Đáp án:** Không. Cần `Map.copyOf(flags)` hoặc chính sách phòng vệ thích hợp nếu caller có thể sửa nguồn.

**Câu 6.** Nếu `Map.copyOf` chứa value `StringBuilder`, state đã immutable sâu chưa?

**Đáp án:** Chưa. Value giữ cùng tham chiếu và vẫn có thể bị mutate; phải chuyển sang String/value object immutable.

**Câu 7.** Reader lấy snapshot N rồi writer publish N+1. Reader có bị chuyển sang N+1 tự động không?

**Đáp án:** Không. Reader giữ reference N; nếu snapshot N không bị mutate thì reader đọc ổn định N.

**Câu 8.** Vì sao nên đọc `var cfg = registry.snapshot();` một lần trong request?

**Đáp án:** Vì các lời gọi snapshot liên tiếp có thể thấy các generation khác nhau khi writer publish giữa các lần; local reference giữ một phiên bản cho toàn bộ thao tác.

**Câu 9.** Khi nào `volatile` đủ?

**Đáp án:** Khi writer được điều phối hoặc ý định là thay một bản cấu hình hoàn chỉnh, không phải gộp read-modify-write từ nhiều writer.

**Câu 10.** Hai writer cùng đọc thế hệ 0, lần lượt thêm key A/B rồi `set`; điều gì có thể xảy ra?

**Đáp án:** Lost update: kết quả cuối có thể chỉ còn một key. Cần CAS/updateAndGet/lock khi mong cả hai thay đổi.

**Câu 11.** Tại sao hàm truyền vào `AtomicReference.updateAndGet` phải side-effect-free?

**Đáp án:** CAS có thể thất bại khi contention và callback có thể chạy lại. Side effects như gửi email/ghi database có thể bị lặp.

**Câu 12.** `AtomicReference.set` có đồng nghĩa một distributed transaction trên nhiều máy chủ không?

**Đáp án:** Không. Nó thay một reference trong một JVM; các dịch vụ/process khác cần coordination/version riêng.

**Câu 13.** Nếu `List.copyOf` chứa array mutable thì list có immutable sâu chưa?

**Đáp án:** Chưa. Cấu trúc List không thay đổi, nhưng array element vẫn sửa được qua alias.

**Câu 14.** `Map.copyOf` có luôn tạo một object mới không?

**Đáp án:** Không. Nó có thể tái sử dụng một Map unmodifiable thích hợp; identity không phải hợp đồng.

**Câu 15.** Khi reload dữ liệu nguồn bị lỗi parse/validation, nên làm gì với current?

**Đáp án:** Giữ snapshot đã công bố trước đó; chỉ publish candidate đã được validate/freeze toàn bộ.

**Câu 16.** Tại sao test ví dụ in key bằng `TreeSet`?

**Đáp án:** Để stdout ổn định, không phụ thuộc thứ tự duyệt của Map/HashMap không được cam kết.

**Câu 17.** Có nên tiếp tục sửa `HashMap` nguồn khi một thread khác đang gọi `Map.copyOf(source)` không?

**Đáp án:** Không nếu không có phối hợp; copy không tự tạo atomic snapshot của HashMap mutable bị sửa đồng thời. Dùng chung khóa hoặc build riêng.

**Câu 18.** Khi config đang được request cũ dùng, làm sao chuyển endpoint mới mà không cắt nguồn cũ đột ngột?

**Đáp án:** Thiết kế resource lifecycle theo phiên bản, cho request cũ drain, chuẩn bị resource mới, publish ở boundary phù hợp. Snapshot replacement không tự đóng/mở mọi tài nguyên ngoài.

## 16. Tài liệu tham khảo chính thức còn áp dụng

1. [Java SE 17 – Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): hợp đồng unmodifiable mapping, không phản ánh sửa đổi nguồn sau copy và từ chối null.
2. [Java SE 17 – List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): snapshot cấu trúc List, thứ tự, null và phần tử mutable.
3. [Java SE 17 – AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): `get`/`set`/`compareAndSet`/`updateAndGet`; callback có thể bị thực thi lại khi tranh chấp CAS.
4. [Java Language Specification – Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): `volatile`, `happens-before`, quy tắc đồng bộ và data races.
5. [Java SE 17 – Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): unmodifiable view có backing Map.
6. [Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối thread và memory consistency.
7. [Java SE 17 – Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): record và trách nhiệm phòng vệ mutable components.
8. [Oracle – Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html): khác biệt giữa unmodifiable copies và views.
9. [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): `var` từ Java 10, chỉ suy luận kiểu cục bộ chứ không mang tính bất biến/đồng bộ.
10. [Java SE 17 – HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): Map mutable và giới hạn concurrent access không đồng bộ.

**Kết luận:** Khi cần nhiều reader dùng một nhóm thông số cấu hình có quan hệ với nhau, hãy **xây và kiểm tra phiên bản mới hoàn chỉnh**, bảo vệ object graph khỏi mutation rồi **công bố một tham chiếu mới** bằng `volatile` hoặc `AtomicReference`. Reader nên giữ **một local snapshot** cho mỗi lượt xử lý. Nếu có nhiều writer cập nhật dựa trên state cũ, cần CAS/`updateAndGet`/lock để tránh lost update và không đưa side effect vào callback có thể retry. Đây là tính nhất quán theo phiên bản **trong một JVM**, không phải một giao dịch tự động trên các hệ thống khác.
