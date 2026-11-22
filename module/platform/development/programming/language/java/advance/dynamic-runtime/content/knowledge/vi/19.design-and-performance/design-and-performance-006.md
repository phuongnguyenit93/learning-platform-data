# 19.6 Công bố bộ nhớ đệm an toàn và kiểm soát cập nhật target khi chạy đồng thời

## 1. Mục tiêu và vấn đề thực tế

Trong các hệ thống **dynamic-runtime** của Java, một bước tra cứu hoặc liên kết động có thể tốn chi phí đáng kể: tìm `Method`/`MethodHandle`, kiểm tra chữ ký, tạo adapter, phân tích schema, liên kết call site, xây cây dispatch hoặc tạo một implementation mới. Để giảm chi phí, ứng dụng thường **cache** kết quả và chia sẻ nó cho nhiều thread.

Hai yêu cầu khác nhau phải được thỏa mãn đồng thời:

1. **Công bố cache an toàn (safe publication):** sau khi một thread tạo xong object, những thread khác phải nhìn thấy trạng thái **đã khởi tạo đầy đủ**, đúng key/version và không đọc dữ liệu từ một cấu trúc cache bị truy cập đồng thời sai quy tắc.
2. **Kiểm soát cập nhật target (target update):** khi logic cần được thay thế tại runtime, các lời gọi đang chạy và các thread đọc target phải có **quy tắc nhìn thấy cập nhật** rõ ràng. Việc gọi `setTarget` không có cùng memory semantics với mọi loại `CallSite`.

Nếu chỉ chăm chăm tối ưu đường gọi mà không thiết kế Java Memory Model (JMM), ta có thể gặp cache race, visibility bug, lost update, phối hợp sai nhiều field hoặc dispatch tới target phiên bản cũ. Các lỗi ấy thường **khó tái hiện**: chạy đơn luồng luôn đúng, chạy stress test đôi khi vẫn đúng, nhưng không vì thế mà chương trình có happens-before hợp lệ.

Trong bài này, ta tập trung vào:

- `happens-before`, `volatile`, `final`, `synchronized` và atomic references;
- `ConcurrentHashMap.computeIfAbsent` để cache `MethodHandle`/adapter;
- snapshot bất biến và khóa cache có version;
- sự khác biệt giữa **`ConstantCallSite`, `MutableCallSite` và `VolatileCallSite`**;
- `MutableCallSite.syncAll`, `SwitchPoint.invalidateAll`, `AtomicReference<MethodHandle>` và phạm vi visibility;
- thay target trong lúc có lời gọi đồng thời, giới hạn đối với lời gọi đã bắt đầu, kiểm soát nhiều writer;
- ví dụ **Java 17+ hoàn chỉnh**, đã biên dịch và chạy, cùng checklist kiểm thử và gỡ lỗi.

> **Nguyên tắc cốt lõi:** Cache đúng nghĩa cần **công bố an toàn** cả *reference lẫn trạng thái mà reference trỏ tới*. Target động cần **cơ chế publication riêng**, phù hợp với tần suất cập nhật và yêu cầu visibility. Đừng coi `ConcurrentHashMap`, `volatile` hay `MutableCallSite.setTarget` là các phép màu có thể biến toàn bộ một quy trình gồm nhiều thao tác thành một giao dịch atomic.

## 2. Hai lớp trách nhiệm: cache reference và liên kết target

Giả sử một framework động nhận yêu cầu `calculate(5)` và cần gọi một `MethodHandle`. Một thiết kế có thể gồm:

```text
request thread(s)
        |
        v
  đọc cấu hình/policy snapshot
        |
        v
 ConcurrentHashMap<Key, MethodHandle>
        | hit                    | miss
        |                        v
        |                build MethodHandle
        |                        |
        +-----------<------------+
        |
        v
 MethodHandle.invokeExact(...)
        |
        v
 kết quả nghiệp vụ
```

Với mô hình khác, cache giữ **một dynamic invoker ổn định**, trong khi target phía sau có thể thay:

```text
request thread(s)
        |
        v
 stable MethodHandle = callSite.dynamicInvoker()
        |
        v
  CallSite target (thay đổi tại runtime)
        |
        +--> version A target
        |
        +--> version B target sau publication hợp lệ
```

Đó là hai vấn đề:

- **Cache publication:** lấy hoặc công bố một `MethodHandle` / một object trạng thái đã xây xong. `ConcurrentHashMap` hay `AtomicReference` có thể chịu trách nhiệm publication này.
- **Call-site target visibility:** cập nhật **trường target** nằm trong `CallSite`. `MutableCallSite` và `VolatileCallSite` có hợp đồng bộ nhớ khác nhau. `ConcurrentHashMap` chứa reference tới call site **không tự biến target bên trong thành volatile**.

**Ví dụ sai về lập luận:** “Tôi đã đặt `MutableCallSite` vào `ConcurrentHashMap` nên `site.setTarget(newTarget)` chắc chắn hiển thị ngay cho mọi thread.” Không đúng. Map công bố **reference tới site**, nhưng các thay đổi sau đó của `MutableCallSite.target` vẫn theo memory semantics riêng của site.

## 3. Java Memory Model: visibility, atomicity, ordering

### 3.1. `happens-before` là hợp đồng cần thiết

JMM định nghĩa một quan hệ **happens-before** để giải thích khi nào tác động từ thread ghi được đảm bảo hiển thị cho thread đọc theo những quy tắc synchronization thích hợp.

Các cơ chế thường dùng:

| Cơ chế | Quan hệ đáng chú ý | Dùng khi |
| --- | --- | --- |
| Ghi/đọc cùng biến `volatile` | Volatile write có quan hệ synchronization với những volatile reads theo JMM | Công bố reference snapshot hoặc cờ trạng thái |
| `synchronized` trên cùng monitor | Unlock trước synchronizes-with lock sau trên monitor đó | Bảo vệ chuỗi thao tác nhiều bước |
| `AtomicReference.get/set/CAS` | Có volatile/atomic memory effects được định nghĩa | Thay snapshot hoặc target reference |
| `ConcurrentHashMap` | Theo API, update một key happens-before non-null retrieval báo mapping đó | Công bố object cache theo key |
| `Thread.start()`, `Thread.join()`, `CountDownLatch`, `Future.get()` | Thiết lập ordering/happens-before cụ thể | Điều phối việc chạy test/worker |
| `final` fields được khởi tạo đúng cách | Có initialization-safety guarantee cho giá trị final theo JMM | Thiết kế object immutable, nhưng không thay thế đồng bộ map/cache |

**Visibility** không đồng nghĩa **atomicity của cả transaction**. Một lần đọc reference `volatile` là atomic, nhưng hai field `volatile` riêng rẽ **không** biến một cặp giá trị thành atomic snapshot.

### 3.2. Ví dụ rủi ro: công bố object chưa hoàn tất

Đây là **phản ví dụ**, không chạy để minh họa tính đúng đắn:

```java
// PHẢN VÍ DỤ: không có happens-before an toàn cho publication.
class BadRegistry {
    static java.util.Map<String, Entry> cache = new java.util.HashMap<>();

    static Entry get(String key) {
        Entry value = cache.get(key);
        if (value == null) {
            value = new Entry();
            cache.put(key, value); // Có thể có writer/readers khác đồng thời.
        }
        return value;
    }

    static class Entry {
        int factor = 3;
        int offset = 2;
    }
}
```

Vấn đề không chỉ là hai thread cùng tạo `Entry`. `HashMap` **không cho phép concurrent mutation không đồng bộ**; đồng thời publication của các state fields không được thiết kế theo happens-before. Có thể xuất hiện duplicate construction, đọc cấu trúc map không nhất quán và các hành vi không được hợp đồng hỗ trợ.

Không nên dùng stress test “chạy 1000 lần đều ra đúng” để biện hộ cho data race.

### 3.3. `volatile` reference không khóa trạng thái bên trong

Ví dụ:

```java
// VẪN RỦI RO nếu nhiều thread chỉnh map sau khi công bố.
volatile java.util.Map<String, String> cache = new java.util.HashMap<>();

void update(String key, String value) {
    cache.put(key, value); // Mutation trong HashMap vẫn không thread-safe.
}
```

`volatile` bảo đảm các quy tắc read/write **đối với biến reference**, không biến mọi method của object được tham chiếu thành thread-safe. Nếu muốn copy-on-write snapshot, phải **tạo map mới**, hoàn thiện nó, rồi công bố reference tới một map không bị mutate nữa.

### 3.4. Snapshot bất biến cho nhiều trường liên quan

Hai fields độc lập:

```java
// PHẢN VÍ DỤ nếu multiplier và offset phải luôn đi thành một cặp.
volatile int multiplier;
volatile int offset;
```

Reader có thể quan sát multiplier của config mới nhưng offset của config cũ nếu writer cập nhật riêng. Cách an toàn hơn:

```java
record Config(int version, int multiplier, int offset) {}

private static final java.util.concurrent.atomic.AtomicReference<Config>
        CURRENT = new java.util.concurrent.atomic.AtomicReference<>(
                new Config(1, 2, 1));

// Writer tạo object hoàn tất TRƯỚC khi công bố.
CURRENT.set(new Config(2, 3, 2));

// Reader giữ một snapshot nhất quán.
Config snapshot = CURRENT.get();
int m = snapshot.multiplier();
int b = snapshot.offset();
```

Đây là **trích đoạn** để minh họa, không phải chương trình độc lập. `Config` là immutable record; `AtomicReference.set` công bố một reference hoàn chỉnh. Reader đọc **một lần** rồi lấy mọi field từ chính object đó.

Lưu ý: `CURRENT.set` không giải quyết mọi conflict giữa **nhiều writers** nếu mỗi writer cần cập nhật dựa trên state cũ. Với read-modify-write cần `compareAndSet` hoặc `updateAndGet` với một function **không có side effects**.

## 4. Công bố cache an toàn với `ConcurrentHashMap`

### 4.1. `computeIfAbsent` cho cache per-key

Một hướng quen thuộc khi cache `MethodHandle`:

```java
// Trích đoạn, giả định Key và buildHandle đã được định nghĩa.
private final java.util.concurrent.ConcurrentHashMap<Key, MethodHandle>
        cache = new java.util.concurrent.ConcurrentHashMap<>();

MethodHandle getHandle(Key key) {
    return cache.computeIfAbsent(key, this::buildHandle);
}
```

Những đặc tính cần hiểu:

1. `ConcurrentHashMap` hỗ trợ đọc/cập nhật đồng thời và **công bố mapping có memory-consistency semantics**.
2. Với `computeIfAbsent`, thao tác tạo mapping cho key đang vắng mặt được thực hiện atomically theo hợp đồng API; các competing updates liên quan có thể bị chặn trong lúc computation.
3. Nếu mapping function trả **`null`**, map **không** ghi mapping. Nếu function ném exception, mapping không được thiết lập bởi lần tính ấy; một lần truy cập tiếp theo có thể **tính lại**.
4. Nếu một key đã có value hợp lệ, reader lấy cache hit; không chạy mapping function chỉ để trả mapping đã có.
5. Không nên để mapping function **đệ quy cập nhật cùng map**, hoặc làm I/O lâu, phụ thuộc một lần khóa chéo khiến thread khác phải chờ.

**Không khẳng định “mapping function chạy đúng một lần mãi mãi”.** Một key có thể bị remove/replace; computation có thể trả null hoặc ném lỗi; lifecycle và cache eviction cho phép tính lại trong tương lai. Trong thí nghiệm bên dưới, ta không remove, function thành công, nên tám threads cùng key cùng nhận một handle và counter build bằng một.

### 4.2. Tạo hoàn chỉnh rồi mới publish

Hãy giữ mapping function theo một chuỗi rõ ràng:

```text
Key bất biến
   |
   v
Resolve MethodType + lookup access
   |
   v
Tạo/adapt MethodHandle xong
   |
   v
Kiểm tra type (nếu cần)
   |
   v
return MethodHandle
   |
   v
ConcurrentHashMap công bố mapping
```

Không đặt object chưa hoàn thành vào map rồi tiếp tục mutate các trường mà readers sẽ dùng. Với `MethodHandle`, nhiều adapter operation trả **một MethodHandle mới**, giúp xây dựng chain hoàn chỉnh trước khi công bố. Những object delegate mà handle `bindTo` phải tham chiếu cũng cần được khởi tạo và quản lý concurrency phù hợp.

### 4.3. Cache key phải đại diện đủ ngữ nghĩa

Ví dụ một framework định tuyến method theo class, signature và policy version. Khóa chỉ là `method.getName()` **không đủ**: overload khác chữ ký, class loader khác, policy version khác có thể bị gộp sai.

Gợi ý thành phần khóa khi phù hợp:

| Thành phần | Lý do |
| --- | --- |
| Owner / receiver type | Phân biệt class/interface và runtime class identity |
| Method name + parameter types + return type | Phân biệt overload và `MethodType` |
| Lookup/access context nếu có ảnh hưởng | Tránh dùng cache entry được resolve dưới quyền khác một cách sai ngữ nghĩa |
| Policy/config version hoặc hash | Không dùng nhầm target cũ sau cập nhật |
| Defining class loader / deployment identity | Phân biệt các phiên bản cùng binary name |
| Adapter flags/calling convention | Phân biệt `asType`, collector/spreader và các chuyển đổi khác |

Đừng nhét mọi thứ vào key một cách máy móc; key phải mô tả **mọi dữ liệu làm thay đổi meaning của kết quả cache**. Đồng thời, cache giữ `Class<?>`, `MethodHandle` hoặc class loader bằng strong references có thể khiến class loader không unload. Cần lifecycle, eviction hoặc thiết kế `ClassValue`/weak-keys thích hợp.

### 4.4. `ConcurrentHashMap` không cho phép null

`ConcurrentHashMap` không nhận key/value null. Nếu một lookup hợp lệ có thể trả “không tồn tại”, hãy cân nhắc `Optional`, sentinel object có type an toàn, negative cache có TTL hoặc cache riêng. Việc mapping function trả null chỉ để biểu diễn “not found” **không ghi negative result**, có thể dẫn đến tra cứu lại liên tục.

Negative caching cần cân nhắc: một method có thể xuất hiện sau khi plugin/version thay đổi; ghi “missing” vĩnh viễn không có version key sẽ làm invalidation khó xử lý.

## 5. Cache versioning, invalidation và snapshot nhất quán

### 5.1. Bất biến hóa dữ liệu cấu hình

Mẫu ở ví dụ chính:

```java
record Config(int version, int multiplier, int offset) {
    public int apply(int x) {
        return x * multiplier + offset;
    }
}
record CacheKey(int version, int multiplier, int offset) {}
```

Một config mới được công bố bằng `AtomicReference<Config>`; reader dùng **một snapshot** để tạo `CacheKey`. `MethodHandle` được build từ đúng dữ liệu key đó. Khi version mới ra đời, key mới tự phân biệt cache entry mới với entry cũ.

Điều này hỗ trợ **in-flight requests**: một request đã nắm config cũ có thể tiếp tục xử lý theo phiên bản cũ mà không bị object cấu hình cũ thay đổi bên dưới. Request mới lấy config mới và dùng cache key mới.

### 5.2. Cập nhật nhiều phần: thay snapshot thay vì in-place edits

**Không nên**:

```java
// PHẢN VÍ DỤ: state có thể bị thấy trong giai đoạn cập nhật dở.
registry.get("rule").setMultiplier(3);
registry.get("rule").setOffset(2);
registry.get("rule").setVersion(2);
```

Nếu ba setter được chạy giữa những request đồng thời, một request có thể nhìn thấy hỗn hợp không được thiết kế. Thay thế bằng object immutable hoàn tất rồi **công bố một reference**, hoặc khóa toàn bộ transaction nếu thật sự cần.

### 5.3. Version key không có nghĩa tự động dọn rác

Mỗi version mới có thể để lại key/handle cũ. Với plugin reload liên tục, cache có thể lớn vô hạn nếu không có bounded size/expiration/retirement policy. Một `MethodHandle` bound tới object có thể giữ class loader và toàn bộ graph phụ thuộc còn sống.

Phải thiết kế:

- Ngưỡng versions được giữ;
- thời điểm một version không còn request đang chạy;
- điều kiện remove cache entries và release reference;
- telemetry cache hit/miss, build latency, entry count;
- phối hợp với class loader lifecycle.

**Không xóa entry cũ ngay giữa một request** rồi giả định các reader đã ngừng dùng MethodHandle cũ. Xóa khỏi map không vô hiệu hóa reference đã được thread khác giữ; nó chỉ ảnh hưởng các lần lookup sau.

### 5.4. Cache của MethodHandle khác cache CallSite target

Nếu cache chứa **MethodHandle đã bind vào một Config bất biến**, entry ấy **không đổi target** khi config toàn cục cập nhật. Nếu muốn dispatch cùng một call site theo target mới, phải thiết kế một **tầng call-site target publication** riêng. Đây là lý do các phần tiếp theo đi vào `MutableCallSite` và `VolatileCallSite`.

## 6. `CallSite` và bản chất của target có thể thay

`java.lang.invoke.CallSite` gắn một call site với `MethodHandle` target và `MethodType` cố định. Ba loại thường gặp:

| Loại | Target cập nhật được? | Visibility khi có nhiều threads | Khi nên dùng |
| --- | --- | --- | --- |
| `ConstantCallSite` | Không | Target cố định sau khi tạo | Logic không thay; JIT có cơ hội tối ưu tốt |
| `MutableCallSite` | Có | Tựa như **field thường**, không tự buộc threads khác thấy update ngay | Link lại ít; kiểm soát publication bằng `syncAll` |
| `VolatileCallSite` | Có | Tựa như **volatile field**, readers có volatile semantics | Cập nhật thường xuyên hoặc cần visibility chặt chẽ |

`CallSite` có `type()` vĩnh viễn đối với site đó. `setTarget` **phải** nhận target có `MethodType` **bằng chính xác** type cũ (không tự coi mọi chuyển đổi `asType` là được áp dụng). Truyền `null` ném `NullPointerException`; truyền target khác type ném `WrongMethodTypeException` theo hợp đồng.

Ví dụ các `MethodHandle` cùng kiểu:

```java
// Hai Java methods:
static int plusOne(int x) { return x + 1; }
static int timesTen(int x) { return x * 10; }

// Hai handles có cùng MethodType (int)int:
MethodType signature = MethodType.methodType(int.class, int.class);
MethodHandle plus = MethodHandles.lookup()
        .findStatic(MyClass.class, "plusOne", signature);
MethodHandle times = MethodHandles.lookup()
        .findStatic(MyClass.class, "timesTen", signature);
```

Đây là **trích đoạn**; `MyClass` là tên minh họa, các imports và method definitions cần đặt trong class. Ví dụ hoàn chỉnh bên dưới có đúng `SafeCacheTargetDemo.class` và imports đầy đủ.

**Không** thay `(int)int` bằng `(String)String` rồi mong JVM tự chuyển khi `setTarget`. Nếu thật sự cần adaptation, dựng `newHandle.asType(site.type())` trước và xử lý `WrongMethodTypeException` nếu conversion không hợp lệ.

### 6.1. `dynamicInvoker()` khác `getTarget()`

`site.getTarget()` trả về **MethodHandle target ở thời điểm truy xuất**. Nếu giữ reference đó trong một biến và không lấy lại, lời gọi qua biến này có thể tiếp tục dùng target cũ sau khi site đổi.

`site.dynamicInvoker()` trả một MethodHandle **delegating through the call site**, có khả năng sử dụng target được site hiện tại cung cấp, với memory semantics của loại `CallSite`. Đây là lựa chọn thích hợp khi caller muốn giữ một invoker ổn định nhưng target bên dưới cần đổi.

```java
// Trích đoạn trong môi trường có VolatileCallSite site.
MethodHandle stableInvoker = site.dynamicInvoker();
int a = (int) stableInvoker.invokeExact(3);
site.setTarget(newHandle);
int b = (int) stableInvoker.invokeExact(3);
```

`invokeExact` là signature-polymorphic, nên việc ép kiểu `(int)` ở Java call site là **cần thiết để chữ ký JVM khớp** khi handle trả `int`. Xem code hoàn chỉnh và kiểm thử `WrongMethodTypeException` bên dưới.

### 6.2. CallSite không nhất thiết phải đến từ `invokedynamic`

Trong ví dụ của bài, `new MutableCallSite(...)` hoặc `new VolatileCallSite(...)` được tạo **trực tiếp** từ Java, rồi dùng `dynamicInvoker()`. Cách này tái hiện hợp đồng dispatch/visibility mà **không cần** tự sinh opcode `invokedynamic`. Trong một language runtime, một bootstrap method có thể trả các CallSite ấy để một instruction `invokedynamic` dùng chúng.

Cần phân biệt: dùng `dynamicInvoker()` từ Java là **test hợp đồng CallSite**, không phải khẳng định chương trình này đã phát ra instruction `invokedynamic` trong method `main`.

## 7. `MutableCallSite`: `setTarget` chưa đủ cho cross-thread visibility

### 7.1. Target của mutable site giống field thường

Theo Java SE 17 API, `MutableCallSite` có target tương tác với bộ nhớ **giống một non-volatile field**. Do đó:

```java
MutableCallSite site = new MutableCallSite(plus);
MethodHandle invoker = site.dynamicInvoker();
site.setTarget(times);
```

Trong **cùng thread** với ordering thông thường, bạn thường sẽ quan sát cập nhật. Nhưng ở **thread khác** không có synchronization thích hợp, các reader có thể tiếp tục dùng target cũ, thậm chí lâu hơn mong muốn. Không dùng phép thử đơn luồng để chứng minh visibility đa luồng.

### 7.2. Công bố bằng `MutableCallSite.syncAll`

Một writer được điều phối có thể:

```java
// Trích đoạn: site và times đã có cùng MethodType.
synchronized (updateLock) {
    site.setTarget(times);
    MutableCallSite.syncAll(new MutableCallSite[]{site});
}
```

`syncAll` buộc các thread khác bỏ những cached target values liên quan. Với một lần update đã hoàn tất synchronization và **không có writer khác can thiệp**, các future target readers được yêu cầu chấp nhận target mới nhất theo ngữ nghĩa API. Hãy dùng `syncAll` **sau** khi đặt target mới.

**Ba sắc thái quan trọng:**

1. Một reader có thể thấy **target mới sớm**, ngay từ sau `setTarget` và **trước** khi `syncAll` trả về.
2. Một reader có thể còn dùng **target cũ** cho tới khi synchronization hoàn tất. `syncAll` **không đảo ngược** một lời gọi đã bắt đầu trên target cũ.
3. Nếu có **nhiều writer**, cần external mutual exclusion cho chuỗi `setTarget + syncAll` để tránh writer nọ ghi đè, writer kia sync và application báo version sai. `syncAll` không tự làm transaction logic.

### 7.3. Batch nhiều sites để giảm chi phí

Có thể gom các sites cần công bố:

```java
// Trích đoạn giả định sites đều hợp lệ và caller có writer lock.
synchronized (updateLock) {
    siteA.setTarget(targetA);
    siteB.setTarget(targetB);
    MutableCallSite.syncAll(
            new MutableCallSite[]{siteA, siteB});
}
```

Batch có thể tiết kiệm overhead synchronization. Tuy nhiên, **không được xem đây là transaction atomic giữa hai site với readers đang chạy**: trong khoảng các lần `setTarget`, reader có thể quan sát siteA mới, siteB cũ. Ngay cả khi `syncAll` một lượt, các lời gọi đang diễn ra không bị rollback.

Nếu hệ thống đòi một cặp target cùng đổi **như một snapshot nguyên tử**, cân nhắc một **cấu trúc immutable routing table** và atomic publication của **một root reference**, thay vì hai mutable sites độc lập.

### 7.4. `syncAll` có thể đắt

API nói `syncAll` có thể tốn chi phí và nên hạn chế; cân nhắc batch. Vì thế `MutableCallSite` thường hợp với **ít lần relink**, không phải policy cần update mỗi microsecond. Không đoán tốc độ dựa trên tên class: hãy benchmark workload thực, tỷ lệ read/write và JVM warm-up.

## 8. `VolatileCallSite`: visibility giống một biến volatile

`VolatileCallSite` có target với volatile memory semantics.

```java
// Trích đoạn.
VolatileCallSite site = new VolatileCallSite(plus);
MethodHandle invoker = site.dynamicInvoker();
int before = (int) invoker.invokeExact(3);
site.setTarget(times);
int after = (int) invoker.invokeExact(3);
```

`getTarget` có semantics như **volatile read**, `setTarget` như **volatile write**. Những lời gọi dispatch thông qua `dynamicInvoker` quan sát target theo quy tắc site, không yêu cầu ứng dụng tự gọi `syncAll`.

**Điều không được suy diễn:** “VolatileCallSite đảm bảo mọi lời gọi đang chạy sẽ tự đổi sang method mới giữa chừng.” Không. Một invocation đã chọn target cũ và bắt đầu chạy có thể hoàn tất với logic cũ. Volatile chỉ quy định memory ordering/visibility của việc đọc/ghi target, không hủy hoặc dịch chuyển stack frames.

So với `MutableCallSite`:

- Cần visibility chặt, updates thường xuyên → `VolatileCallSite` là lựa chọn đáng cân nhắc.
- Updates rất hiếm, nhiều read paths cần tối ưu → `MutableCallSite` + `syncAll` có thể phù hợp.
- Logic không bao giờ đổi → `ConstantCallSite` và tránh nhu cầu publication target.

Không có kết luận hiệu năng “luôn nhanh nhất”. Volatile semantics thường kèm chi phí trên hot path, đặc biệt nếu liên tục đọc target khi các thread cạnh tranh.

### 8.1. `volatile` không tự giải quyết lost update từ nhiều writer

Nếu hai threads đọc policy version 1 rồi cùng tính target version 2, gọi `setTarget` đồng thời theo thứ tự tùy ý, target cuối cùng do thứ tự writes quyết định. Nếu business cần **compare-and-update** dựa trên version, hãy dùng external lock, CAS trên immutable routing state hoặc cơ chế sequence/versioning.

`VolatileCallSite` đảm bảo visibility, nhưng bản thân `setTarget` không nhận một `expectedTarget` để làm CAS. Đừng nhầm memory visibility với việc serialize quy trình cập nhật cấu hình.

## 9. `SwitchPoint`: vô hiệu hóa guard đã tối ưu

`java.lang.invoke.SwitchPoint` phù hợp khi có nhánh hot path được dùng **cho đến khi assumption không còn đúng**.

```java
SwitchPoint point = new SwitchPoint();
MethodHandle fastPath = point.guardWithTest(plus, times);

int first = (int) fastPath.invokeExact(3); // 4
SwitchPoint.invalidateAll(new SwitchPoint[]{point});
int second = (int) fastPath.invokeExact(3); // 30
```

Đây là trích đoạn; biến `plus`/`times` được tạo trong ví dụ đầy đủ. `guardWithTest(target,fallback)` chọn `target` khi point còn hợp lệ; sau `invalidateAll`, chọn `fallback` theo hợp đồng visibility toàn cục của `SwitchPoint`.

**Đặc tính đặc biệt:** invalidation của một `SwitchPoint` **chỉ đi một chiều**. Khi đã invalidated, không có API “reset valid=true”. Muốn bắt đầu một epoch tối ưu mới, phải tạo **`SwitchPoint` mới** và công bố guarded handle mới theo cơ chế an toàn.

### 9.1. `SwitchPoint` không phải target setter

Nó không đơn giản là `setTarget(newHandle)`:

- Nó là một cơ chế **bảo vệ một assumption** bằng guard.
- Sau invalidation, tất cả guarded handles gắn với point đó sẽ chọn fallback.
- Có thể một `SwitchPoint` bảo vệ nhiều handles/call sites.
- Không thể biến cùng point thành valid trở lại.

`SwitchPoint.invalidateAll` có thể có overhead; nếu invalidate nhiều points, cân nhắc batch. In-flight calls đã đi qua guard trước khi invalidation có thể đã chạy nhánh cũ; invalidation không “quay ngược thời gian”.

### 9.2. Thực tế trong inline caches

Một dynamic language runtime có thể giả định object shape vẫn ổn định: hot path dùng MethodHandle chuyên biệt. Khi shape thay đổi, runtime invalidate `SwitchPoint` để các calls sau chuyển sang fallback, nơi có thể relink một target thích hợp.

Cần phân biệt `SwitchPoint` (guard assumptions) với cache `ConcurrentHashMap` (lưu đã xây handle). Cả hai có thể xuất hiện cùng lúc nhưng giải quyết hai tầng khác nhau.

## 10. `AtomicReference<MethodHandle>`: một lựa chọn không dùng CallSite

Nếu ứng dụng không cần một `invokedynamic` call site thực sự, có thể giữ một reference tới `MethodHandle` và thay nguyên tử:

```java
AtomicReference<MethodHandle> current =
        new AtomicReference<>(plus);
int a = (int) current.get().invokeExact(3);
current.set(times);
int b = (int) current.get().invokeExact(3);
```

Ở đây:

- `get` có volatile-read semantics; `set` có volatile-write semantics.
- Mỗi invocation đọc **một reference MethodHandle** rồi gọi nó. Nếu writer đổi reference sau khi reader đã đọc, lời gọi đang chạy có thể vẫn dùng old handle.
- Nếu cần conditional swap, dùng `compareAndSet(expected,newHandle)`.
- Không có `CallSite` metadata hay JVM `invokedynamic` bootstrap; đây là **application-level dispatcher**.

Một `AtomicReference<MethodHandle>` không tự kiểm tra “new handle có cùng MethodType như old handle” ở lúc `set`. **Ứng dụng phải validate** `newHandle.type().equals(expectedType)` trước publication; nếu không, caller `invokeExact` có thể thất bại bằng `WrongMethodTypeException` khi gọi.

Do đó `VolatileCallSite` có lợi thế rõ: invariant **fixed MethodType** được `setTarget` kiểm tra. Với AtomicReference ta đổi được root reference nhưng phải tự bảo vệ contract.

### 10.1. Snapshot một bảng routing

Khi cần thay **nhiều target đồng thời theo một version**:

```java
// Trích đoạn minh họa.
record Routes(int version, Map<String, MethodHandle> handles) {}

AtomicReference<Routes> current =
        new AtomicReference<>(new Routes(1, Map.of(
                "read", oldReadHandle,
                "write", oldWriteHandle)));

// Writer tạo map immutable hoàn chỉnh, sau đó publish MỘT reference.
Routes next = new Routes(2, Map.of(
        "read", newReadHandle,
        "write", newWriteHandle));
current.set(next);

// Reader dùng MỘT snapshot cho tất cả lookups liên quan.
Routes snapshot = current.get();
MethodHandle read = snapshot.handles().get("read");
MethodHandle write = snapshot.handles().get("write");
```

Đây là **trích đoạn**, các handle được định nghĩa trong ứng dụng thực. `Map.of` chứa các entries bất biến; reader giữ một `Routes` duy nhất. Cách này giúp xử lý consistency của **một nhóm routes**, thay vì cập nhật nhiều sites/fields rời rạc.

Nếu writer cần cập nhật dựa trên version hiện tại, dùng CAS loop có check version. `AtomicReference.set` là atomic publication nhưng **không tự từ chối writer cũ**.

## 11. Ví dụ Java 17+ hoàn chỉnh: cache và thay target có kiểm soát

Ví dụ sau là **một chương trình chạy độc lập**, chỉ dùng standard JDK APIs. Nó minh họa cả hai lớp:

1. **Cache publication**: tám threads tranh cùng `CacheKey` qua `ConcurrentHashMap.computeIfAbsent`, nhận **cùng handle reference**; một immutable config snapshot mới dẫn đến key mới.
2. **Target publication**: writer cập nhật `VolatileCallSite`, một reader thread dùng `dynamicInvoker` trước và sau update; `MutableCallSite.syncAll`; `SwitchPoint.invalidateAll`; `AtomicReference<MethodHandle>`.
3. **Type safety**: thử đặt `MethodHandle ()String` vào site cố định `(int)int` và bắt `WrongMethodTypeException`.

### 11.1. File `SafeCacheTargetDemo.java`

Tạo file có tên chính xác **`SafeCacheTargetDemo.java`** với nội dung:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.SwitchPoint;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class SafeCacheTargetDemo {
    record Config(int version, int multiplier, int offset) {
        public int apply(int x) {
            return x * multiplier + offset;
        }
    }

    record CacheKey(int version, int multiplier, int offset) {}

    private static final AtomicReference<Config> CURRENT =
            new AtomicReference<>(new Config(1, 2, 1));
    private static final ConcurrentHashMap<CacheKey, MethodHandle> CACHE =
            new ConcurrentHashMap<>();
    private static final AtomicInteger BUILDS = new AtomicInteger();

    private static MethodHandle build(CacheKey key) {
        BUILDS.incrementAndGet();
        Config snapshot = new Config(
                key.version(), key.multiplier(), key.offset());
        try {
            return MethodHandles.lookup().findVirtual(
                    Config.class, "apply",
                    MethodType.methodType(int.class, int.class)
            ).bindTo(snapshot);
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static CacheKey key(Config c) {
        return new CacheKey(c.version(), c.multiplier(), c.offset());
    }

    public static int plusOne(int input) {
        return input + 1;
    }

    public static int timesTen(int input) {
        return input * 10;
    }

    public static void main(String[] args) throws Throwable {
        Config snapshot1 = CURRENT.get();
        CacheKey key1 = key(snapshot1);

        ExecutorService workers = Executors.newFixedThreadPool(8);
        try {
            CountDownLatch start = new CountDownLatch(1);
            List<Future<MethodHandle>> tasks = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                tasks.add(workers.submit(() -> {
                    start.await();
                    return CACHE.computeIfAbsent(
                            key1, SafeCacheTargetDemo::build);
                }));
            }
            start.countDown();

            MethodHandle first = tasks.get(0).get();
            boolean identical = true;
            for (Future<MethodHandle> task : tasks) {
                identical &= first == task.get();
            }
            System.out.println("same cached handle=" + identical);
            System.out.println("cache entries=" + CACHE.size());
            System.out.println("builds after contention=" + BUILDS.get());
            System.out.println("old snapshot result=" +
                    (int) first.invokeExact(5));

            CURRENT.set(new Config(2, 3, 2));
            Config snapshot2 = CURRENT.get(); // Đọc một snapshot.
            MethodHandle second = CACHE.computeIfAbsent(
                    key(snapshot2), SafeCacheTargetDemo::build);
            System.out.println("new snapshot result=" +
                    (int) second.invokeExact(5));
            System.out.println("old handle remains=" +
                    (int) first.invokeExact(5));
            System.out.println("cache entries after version=" + CACHE.size());
            System.out.println("builds after version=" + BUILDS.get());
        } finally {
            workers.shutdown();
            if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
                workers.shutdownNow();
                throw new IllegalStateException("workers did not terminate");
            }
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(int.class, int.class);
        MethodHandle plus = lookup.findStatic(
                SafeCacheTargetDemo.class, "plusOne", signature);
        MethodHandle times = lookup.findStatic(
                SafeCacheTargetDemo.class, "timesTen", signature);

        // VolatileCallSite: một reader thread đọc trước/sau writer.
        VolatileCallSite volatileSite = new VolatileCallSite(plus);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        CountDownLatch before = new CountDownLatch(1);
        CountDownLatch afterUpdate = new CountDownLatch(1);
        ExecutorService reader = Executors.newSingleThreadExecutor();
        try {
            Future<int[]> readPair = reader.submit(() -> {
                try {
                    int oldResult = (int) volatileInvoker.invokeExact(3);
                    before.countDown();
                    afterUpdate.await();
                    int newResult = (int) volatileInvoker.invokeExact(3);
                    return new int[]{oldResult, newResult};
                } catch (Throwable ex) {
                    throw new IllegalStateException(ex);
                }
            });
            before.await();
            volatileSite.setTarget(times);
            afterUpdate.countDown();
            int[] pair = readPair.get();
            System.out.println("volatile other thread=" +
                    pair[0] + " -> " + pair[1]);
        } finally {
            afterUpdate.countDown();
            reader.shutdown();
            if (!reader.awaitTermination(10, TimeUnit.SECONDS)) {
                reader.shutdownNow();
                throw new IllegalStateException("reader did not terminate");
            }
        }

        // MutableCallSite: công bố update cho readers bằng syncAll.
        MutableCallSite mutable = new MutableCallSite(plus);
        MethodHandle mutableInvoker = mutable.dynamicInvoker();
        System.out.println("mutable before=" +
                (int) mutableInvoker.invokeExact(3));
        synchronized (mutable) {
            mutable.setTarget(times);
            MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        }
        System.out.println("mutable after syncAll=" +
                (int) mutableInvoker.invokeExact(3));

        // SwitchPoint: một chiều valid -> invalid.
        SwitchPoint switchPoint = new SwitchPoint();
        MethodHandle guarded = switchPoint.guardWithTest(plus, times);
        System.out.println("switch before=" +
                (int) guarded.invokeExact(3));
        SwitchPoint.invalidateAll(new SwitchPoint[]{switchPoint});
        System.out.println("switch after=" +
                (int) guarded.invokeExact(3));

        // AtomicReference<MethodHandle>: application-level dispatch.
        AtomicReference<MethodHandle> reference =
                new AtomicReference<>(plus);
        System.out.println("atomic ref before=" +
                (int) reference.get().invokeExact(3));
        reference.set(times);
        System.out.println("atomic ref after=" +
                (int) reference.get().invokeExact(3));

        // CallSite từ chối target khác MethodType.
        try {
            volatileSite.setTarget(
                    MethodHandles.constant(String.class, "bad"));
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrong target type=" +
                    ex.getClass().getSimpleName());
        }
    }
}
```

### 11.2. Biên dịch và chạy

Trong thư mục chứa source trên, sử dụng **JDK 17 trở lên**:

```bash
javac --release 17 SafeCacheTargetDemo.java
java SafeCacheTargetDemo
```

**Stdout chính xác đã kiểm chứng trên JDK bằng biên dịch và thực thi thực tế:**

```text
same cached handle=true
cache entries=1
builds after contention=1
old snapshot result=11
new snapshot result=17
old handle remains=11
cache entries after version=2
builds after version=2
volatile other thread=4 -> 30
mutable before=4
mutable after syncAll=30
switch before=4
switch after=30
atomic ref before=4
atomic ref after=30
wrong target type=WrongMethodTypeException
```

Phép kiểm chứng đã hoàn tất với `javac` exit code **0** và `java` exit code **0**.

### 11.3. Vì sao kết quả phần cache xác định?

`CURRENT` ban đầu là `Config(version=1, multiplier=2, offset=1)`, nên `apply(5)` trả `5 * 2 + 1 = 11`. Tám tác vụ trên một `ExecutorService` được giải phóng bằng `CountDownLatch.start` và cùng gọi `computeIfAbsent(key1, ...)`.

Với đúng key đó, **mapping function thành công**, không có remove/update cạnh tranh và map ban đầu rỗng, nên `CACHE` chứa một mapping. `builds after contention=1`; mọi future nhận cùng `MethodHandle` reference, nên `same cached handle=true`.

Khi `CURRENT.set(new Config(2,3,2))`, reader lấy **một snapshot mới**; key khác và cache build handle mới. `apply(5)` trả `17`. Nhưng `first` vẫn bị bind vào config cũ, nên `old handle remains=11`. Đây là hành vi **versioned cache** được thiết kế, không phải stale visibility bug.

`cache entries after version=2` và `builds after version=2` là kết quả thử nghiệm vì ứng dụng **cố ý giữ cả hai versions**; production phải có policy eviction.

### 11.4. Vì sao cập nhật `VolatileCallSite` dùng hai latch?

Reader thread thực hiện:

1. Lấy `volatileInvoker` đã tạo và gọi với `3`; nhận `4` từ `plusOne`.
2. Báo writer rằng lần đọc đầu đã xong qua `before.countDown()`.
3. Chờ `afterUpdate.await()`.
4. Gọi cùng `volatileInvoker` lần nữa, sau khi writer `setTarget(times)`, nhận `30`.

Latches **làm thứ tự sự kiện tái lập được** và tự chúng cũng thiết lập synchronization. Vì vậy thí nghiệm là kiểm chứng behavior và API usage, **không phải phép đo độc lập chứng minh chỉ riêng volatile memory barrier**. Bằng chứng về visibility semantics phải dựa vào Java SE 17 API/JMM, không từ một output stress test.

Nếu bỏ latches và để race tự do, reader có thể chọn target cũ hoặc mới tùy thời điểm; không nên assert mọi lần bắt đầu đồng thời đều thấy target mới.

### 11.5. `MutableCallSite`: kết quả sau `syncAll`

`mutable before=4` và `mutable after syncAll=30`. Code dùng **một writer**, nên `synchronized (mutable)` là cách minh họa vùng writer-critical-section; nếu có nhiều writers trong cùng registry, mọi writer phải tuân thủ **chính cùng một lock** để việc `setTarget/syncAll` được serialize.

Kết quả trong cùng thread cho thấy code hoạt động, nhưng không thay thế contract `syncAll` đối với other threads. Một call đã vào target cũ trước publication vẫn có thể hoàn tất với giá trị cũ; `syncAll` không phải transaction rollback.

### 11.6. `SwitchPoint` và `AtomicReference`

`switch before=4`, sau invalidate `switch after=30`, tương ứng target/fallback. Một `SwitchPoint` đã invalidated không thể quay lại trạng thái valid; dùng point mới cho một optimized epoch mới.

`atomic ref before=4` và `atomic ref after=30` minh họa application-level volatile reference publication. Ở đây code đã chủ động thay MethodHandle reference. **AtomicReference không làm cùng việc như JVM `invokedynamic` linkage**, và không ép MethodType khi `set`.

### 11.7. Kiểm soát kiểu target

`volatileSite` có type cố định **`(int)int`**. `MethodHandles.constant(String.class,"bad")` có type **`()String`**. `VolatileCallSite.setTarget` từ chối bằng `WrongMethodTypeException`:

```text
wrong target type=WrongMethodTypeException
```

Không có việc JVM tự thêm tham số `int` hoặc tự chuyển kiểu trả `String` sang `int`. Nếu cần adapter, phải kiểm tra và xây `MethodHandle` **đúng type** trước khi công bố.

## 12. Những race conditions hay bị bỏ sót

### 12.1. Double-checked locking thiếu `volatile`

Một ví dụ cổ điển:

```java
// PHẢN VÍ DỤ: singleton không có publication hợp lệ.
private static Registry instance;

static Registry get() {
    if (instance == null) {
        synchronized (Registry.class) {
            if (instance == null) {
                instance = new Registry();
            }
        }
    }
    return instance;
}
```

Đây là **trích đoạn chống chỉ định**. Reader bên ngoài synchronization không đọc một `volatile` reference, nên double-checked locking không có publication guarantee phù hợp.

Sửa bằng `private static volatile Registry instance;` và khởi tạo đầy đủ object trước khi publish, hoặc dùng holder idiom / initialization-on-demand của JVM khi chỉ cần singleton bất biến.

Không nên tự cài đặt double-checked cache phức tạp nếu `ConcurrentHashMap.computeIfAbsent` hoặc class initialization đã giải quyết bài toán rõ ràng hơn.

### 12.2. Check-then-act không atomic

```java
// PHẢN VÍ DỤ với map thường (hoặc ngay cả với concurrent map
// nếu yêu cầu duy nhất một build/update).
if (!cache.containsKey(key)) {
    cache.put(key, build(key));
}
```

Ngay cả khi `cache` là `ConcurrentHashMap`, tách `containsKey` và `put` thành hai operations vẫn cho phép hai writers chen vào giữa. Nếu mapping function đắt hoặc phải bảo đảm một mapping được chọn hợp lệ, dùng `computeIfAbsent` đúng chỗ, với semantics khi function trả null/throw đã hiểu.

### 12.3. “Cứ `volatile` là tăng counter atomic”

`volatile int count` với `count++` **không atomic**. Đó là đọc → cộng → ghi; threads có thể mất cập nhật. Dùng `AtomicInteger.incrementAndGet`, `LongAdder` (cho thống kê tần suất cao, không dùng để tạo thứ tự giao dịch duy nhất) hoặc lock.

Trong bài thực hành, `BUILDS` là `AtomicInteger`; nếu dùng `int++` thường rồi dựa vào count trong stress test, một vài build có thể xảy ra mà counter vẫn đánh lừa do lost updates.

### 12.4. Writer thắng theo thứ tự khác mong muốn

Hai writers đồng thời có thể công bố:

```text
W1 build target(version=11) --------------- publish
W2 build target(version=12) ---- publish
```

Nếu W1 hoàn tất build chậm hơn W2 rồi `setTarget` cuối cùng, target có thể **quay lại version 11**. `VolatileCallSite` vẫn hoàn toàn thỏa memory semantics; **business invariant “version chỉ tăng”** bị phá vì thiếu coordination.

Cần:

- một lock/serialized update queue;
- CAS trên record `(version, target)`;
- hoặc rejection nếu proposed version không mới hơn current.

`CallSite.setTarget` không có built-in version check. Đừng dựa vào thứ tự hoàn tất network/config loader để quyết định latest config.

### 12.5. Multi-site updates không phải một atomic release

Khi một request cần cả `routeA` và `routeB` cùng version, nếu code set hai sites riêng, reader có thể lấy “A version 2, B version 1” giữa các cập nhật. `syncAll` cuối cùng cải thiện visibility nhưng **không biến hai sites thành một global transaction**.

Với invariants cần nhất quán, dùng một immutable routing snapshot trong `AtomicReference` và đọc **một lần mỗi request**. Ngoài ra, có thể dùng khóa chung hoặc protocol generation/seqlock phù hợp, nhưng phải chứng minh correctness.

### 12.6. In-flight requests và rollback

Kể cả khi writer đã công bố target mới, một invocation đã đọc target cũ **trước publication** có thể vẫn đang thực thi. Không có `CallSite` API nào “dừng mọi frame cũ” chỉ vì `setTarget` hoặc `invalidateAll`.

Nếu việc đổi target có ý nghĩa security hoặc business critical, phải xác định thêm:

- Có cần chặn request mới trong giai đoạn chuyển đổi không?
- Có cho phép requests cũ hoàn tất không?
- Có cần quiescence/barrier/epoch reclamation không?
- Khi nào được dọn resources/class loader version cũ?
- Có dùng validation tại **thời điểm commit hành động** thay vì chỉ tại điểm dispatch không?

Target visibility chỉ giải quyết **chọn đường gọi ở thời điểm quan sát**, không thay cho protocol quản trị chuyển version.

## 13. Chọn mô hình theo tần suất cập nhật và contract

| Nhu cầu | Mô hình phù hợp | Trade-off |
| --- | --- | --- |
| Cache lookup/adapter theo key, ít đổi | `ConcurrentHashMap.computeIfAbsent` | Key chính xác, mapping function nhanh và bounded cache |
| Công bố nhóm cấu hình immutable nhất quán | `AtomicReference<Config>` hoặc `volatile Config` | Mỗi request phải đọc một snapshot và giữ nó |
| Một target chỉ link một lần | `ConstantCallSite` | Không update target |
| Relink hiếm, muốn tối ưu đường đọc | `MutableCallSite.setTarget` + `syncAll` | Sync operations có thể đắt; writers phải phối hợp |
| Target đổi thường xuyên, readers cần volatile visibility | `VolatileCallSite` | Có thể thêm chi phí volatile ở hot path |
| Invalidate assumption hot path một chiều | `SwitchPoint` | Không reset; tạo point mới cho epoch mới |
| Không dùng `invokedynamic`, chỉ thay Java dispatch reference | `AtomicReference<MethodHandle>` | Tự validate `MethodType` và version |
| Thay nhiều routes như một snapshot | `AtomicReference<ImmutableRoutes>` | Xây đủ bảng mới và publish một root |
| Nhiều writers cần conditional update | CAS/version check hoặc external lock | Cần xử lý retries/conflict rõ ràng |
| Runtime reload nhiều class loaders | Per-loader/weak/ClassValue cache + lifecycle | Tránh strong-reference/metaspace retention |

### 13.1. Quy tắc “đọc nhiều, cập nhật ít”

Nếu read path cực nóng và update hiếm, `MutableCallSite` cùng batch `syncAll` có thể hấp dẫn. Nhưng nếu update nhiều, hãy đo xem cost của syncAll và coordination có vượt chi phí volatile reads không.

Nếu target thay từng request, ngay từ thiết kế có thể **không nên** giữ mutable call site: dùng một `AtomicReference` tới policy hoặc target function phù hợp thường rõ ràng hơn.

### 13.2. Cache và target đều phải giữ đúng `MethodType`

Với MethodHandle adapters, hãy xác nhận:

```java
if (!newHandle.type().equals(expectedType)) {
    throw new IllegalArgumentException(
            "Target type mismatch: " + newHandle.type());
}
```

Đây là **trích đoạn** với biến có sẵn. Đặc biệt nếu cache key không chứa full signature, một handle khác type có thể bị trả nhầm cho call site và gây `WrongMethodTypeException`.

Không tùy tiện gọi `asType` như phương án “ép mọi trường hợp cho qua”: conversion phải hợp lệ và có thể thêm boxing/unboxing/casts/overhead. Nếu adapter không đúng business semantics, việc type-check pass cũng không bảo đảm logic đúng.

## 14. Kiểm thử concurrency một cách đáng tin

### 14.1. Vì sao test đa luồng qua được vẫn chưa đủ?

Một bug visibility có thể không xuất hiện với số lượng thread nhỏ, trong interpreter mode, hoặc trên CPU/cache topology cụ thể. Compiler/JIT có quyền tối ưu theo JMM; code có data race không có bảo đảm mà chỉ “chạy đúng hôm nay” không nên được dùng trong production.

Phân biệt các loại QA:

- **API correctness test:** build `MethodHandle` với chữ ký đúng, `invokeExact` trả đúng.
- **Publication test:** map/cache tạo và công bố object đã hoàn tất.
- **Concurrency scenario test:** readers/writers hoạt động dưới contention, không deadlock, không lost updates ngoài chính sách.
- **Memory-model reasoning:** dựa trên happens-before/volatile/atomic contracts, không dựa vào số lần chạy.
- **Performance benchmark:** dùng JMH hoặc công cụ thích hợp, có warm-up, nhiều JVM forks, không đo từ một `System.nanoTime` loop đơn giản.

### 14.2. Các barrier trong code ví dụ

Code sử dụng `CountDownLatch` và `Future.get()` để điều phối, vì muốn stdout xác định. Chúng cũng là **synchronization actions**, do đó:

- Test đã kiểm chứng pipeline và behavior.
- Nó **không chứng minh riêng** rằng một reader chạy race liên tục có thể nhìn thấy target mới chỉ nhờ những operations nào.
- Để khảo sát các reorderings/happens-before trong môi trường cạnh tranh, nên dùng công cụ chuyên dụng như **JCStress**, đồng thời đọc JLS/Javadoc.

**Không** viết test loop không đồng bộ rồi chờ đến khi thấy lỗi: nếu không thấy lỗi, đó không phải bằng chứng.

### 14.3. Ma trận test tối thiểu

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| 8 threads `computeIfAbsent` cùng key, function thành công | Một mapping có giá trị nhất quán; không lấy object chưa xây |
| Mapping function trả null hoặc throw | Không coi kết quả ấy là cached successful value |
| Hai config versions liên tiếp | Cache key phân biệt; old handle còn gắn old version |
| Cập nhật config trong lúc request chạy | Request dùng một immutable snapshot, không trộn fields |
| Writer `VolatileCallSite.setTarget` | Reader tiếp theo theo contract volatile, hiểu giới hạn in-flight |
| Writer `MutableCallSite.setTarget` trước sync | Không giả định readers khác đã thấy update |
| `MutableCallSite.syncAll` hoàn tất | Future readers chấp nhận target được công bố đúng khi không có write cạnh tranh |
| Hai writers cùng thay target | Có serialized ordering/CAS version, không downgrade ngầm |
| `SwitchPoint.invalidateAll` | Guard sang fallback và không thể reset point |
| Target khác `MethodType` | `WrongMethodTypeException` hoặc validation failure |
| Cache eviction/class loader reload | Không giữ strong references vô hạn; in-flight requests an toàn |
| Update nhiều routes cùng epoch | Reader giữ một routing snapshot nhất quán |
| Thread interruption/exceptions trong build | Không để cache ở trạng thái nửa hoàn tất |

## 15. Bài tập và lời giải

**Câu 1.** Một `HashMap<String,MethodHandle>` được nhiều threads `get` và `put` không khóa. Có an toàn vì `MethodHandle` thường bất biến không?  
**Giải:** Không. Tính bất biến của value không làm `HashMap` thread-safe hay tạo publication/happens-before cho map updates. Dùng `ConcurrentHashMap` hoặc immutable map snapshot với publication đúng.

**Câu 2.** Map cache được khai báo `volatile Map<...>`, nhưng writer vẫn `map.put` trên một `HashMap` chung. Vậy đủ không?  
**Giải:** Không. `volatile` của reference không biến nội dung `HashMap` thành concurrent collection. Tạo bản immutable mới rồi `volatile`-publish hoặc dùng concurrent map.

**Câu 3.** Hai biến `volatile int factor` và `volatile int offset` được cập nhật riêng. Reader có chắc thấy cả hai từ một version không?  
**Giải:** Không. Mỗi field có memory semantics riêng, không tạo một atomic multi-field snapshot. Dùng immutable config object và một reference publication.

**Câu 4.** `ConcurrentHashMap.computeIfAbsent` có thể trả null từ mapping function thì null có được cache không?  
**Giải:** Không. `ConcurrentHashMap` không lưu null values; một lần truy cập khác có thể compute lại.

**Câu 5.** Mapping function ném exception. Có thể kết luận từ đó mọi lần lookup sau sẽ thấy cùng exception đã cache không?  
**Giải:** Không. Cache không thiết lập mapping bởi lần compute lỗi; lần sau có thể thử lại. Điều này **khác** với các cơ chế JVM failed resolution ở một số symbolic references.

**Câu 6.** Cache key chỉ gồm tên `"process"` dù có `process(String)` và `process(int)`. Rủi ro gì?  
**Giải:** Hai method overload bị gộp sai `MethodHandle`. Cần key gồm class/owner và full signature, cùng ngữ cảnh làm thay đổi meaning.

**Câu 7.** `MutableCallSite.setTarget` được writer gọi. Reader thread khác bắt buộc nhìn thấy target mới ngay không?  
**Giải:** Không. Mutable target hoạt động giống field thường; cần synchronization thích hợp, thường là `MutableCallSite.syncAll` để force visibility theo hợp đồng.

**Câu 8.** `MutableCallSite.syncAll` có hủy một invocation đã bắt đầu chạy target cũ không?  
**Giải:** Không. Nó không rollback in-flight invocation. Cần protocol cấp ứng dụng nếu yêu cầu quiescence hoặc thu hồi quyền mạnh hơn.

**Câu 9.** Một thread gọi `VolatileCallSite.setTarget`. Cần thêm `MutableCallSite.syncAll` không?  
**Giải:** Không. `VolatileCallSite` đã có volatile memory semantics; `syncAll` là API static dành cho `MutableCallSite[]`.

**Câu 10.** Đặt một `MutableCallSite` trong `ConcurrentHashMap` có khiến `site.setTarget` tự có volatile visibility không?  
**Giải:** Không. Map publish reference tới site; target field bên trong `MutableCallSite` vẫn có semantics của mutable site.

**Câu 11.** Muốn thay hai routes như một snapshot nhất quán. Có thể gọi hai lần `VolatileCallSite.setTarget` rồi coi atomic không?  
**Giải:** Không. Reader có thể quan sát hỗn hợp trước khi cả hai updates xong. Dùng một immutable routing snapshot với một root `AtomicReference` hoặc protocol synchronization.

**Câu 12.** `SwitchPoint.invalidateAll` xong, có thể reset cùng point để dùng fast target cũ không?  
**Giải:** Không. Invalidation một chiều. Dựng point mới và guarded chain mới nếu cần epoch mới.

**Câu 13.** Một `AtomicReference<MethodHandle>` thay được target bằng handle sai type không?  
**Giải:** `AtomicReference.set` tự nó không kiểm tra `MethodType`. Application phải validate; lỗi có thể xuất hiện khi `invokeExact`. `CallSite.setTarget` thì giữ invariant type cố định.

**Câu 14.** Hai writers cùng thay target version 7/8. `VolatileCallSite` có bảo đảm không bao giờ bị downgrade về version 7?  
**Giải:** Không. Volatile chỉ cung cấp memory semantics; version ordering cần CAS/external lock/policy riêng.

**Câu 15.** Trong ví dụ, tám threads nhận cùng handle và `BUILDS==1`. Có được kết luận rằng mapping function chạy đúng một lần trong mọi chương trình và mọi thời điểm không?  
**Giải:** Không. Kết quả đúng với một mapping thành công không bị remove, không trả null/throw và các điều kiện thí nghiệm. Key có thể bị evict/compute lại về sau.

**Câu 16.** `MethodHandle` bound vào `Config(version=1)` có tự chuyển sang Config version 2 sau khi `CURRENT.set` không?  
**Giải:** Không. Bound handle giữ object đã bind. Versioned cache tạo entry mới; existing in-flight calls có thể dùng old config.

**Câu 17.** `volatile` write/read và `synchronized` đều liên quan happens-before, vậy chúng làm mọi đoạn code thành atomic không?  
**Giải:** Không. Chúng có các memory/synchronization guarantees cụ thể; transaction gồm nhiều steps cần protocol/lock/CAS và invariant rõ.

**Câu 18.** Sau `syncAll`, người gọi nhận kết quả cũ trong một invocation đã bắt đầu trước đó. Có nhất thiết là visibility bug không?  
**Giải:** Không. In-flight invocation có thể đã chọn target cũ. Chỉ dựa vào value trả về không đủ để suy ra khi nào target được đọc.

**Câu 19.** Vì sao `newHandle.type().equals(expected)` cần được kiểm tra khi thay target?  
**Giải:** Vì `CallSite` giữ fixed `MethodType`; target mới sai signature bị từ chối. `AtomicReference` không tự kiểm tra, nên càng cần validate.

**Câu 20.** Khi plugin loader cũ đã bị thay thế, chỉ `cache.remove(key)` có đảm bảo loader được unload ngay không?  
**Giải:** Không. Other threads, bound objects, MethodHandles, static registries hoặc external callbacks vẫn có thể giữ strong references. Unload cần dọn lifecycle và điều kiện GC phù hợp.

## 16. Checklist triển khai và chẩn đoán production

Để đưa thiết kế cache/target publication vào ứng dụng thực:

1. **Định danh invariant:** cần consistent value per request, không downgrade version, bao nhiêu versions active, có cho phép in-flight calls dùng old logic?
2. **Chọn publication root:** `ConcurrentHashMap` cho mapping per-key, immutable snapshot + `AtomicReference`/`volatile` cho một nhóm fields.
3. **Cấu trúc key đúng:** full signature, class identity/loader, version, lookup context khi có ảnh hưởng.
4. **Khởi tạo xong trước khi publish:** đừng bỏ half-built adapter/registry vào shared cache.
5. **Chọn CallSite type:** `ConstantCallSite` nếu bất biến; `MutableCallSite+syncAll` nếu hiếm relink; `VolatileCallSite` nếu updates nhiều và cần volatile visibility.
6. **Giữ invariant MethodType:** không cập nhật site với target sai type; adapter `asType` phải hợp lệ.
7. **Serialize writers:** lock, CAS hoặc update coordinator, nhất là khi `setTarget + syncAll` và config versions có thể tranh nhau.
8. **Phân biệt thời điểm thấy update:** readers có thể thấy new target sớm; in-flight calls cũ không bị thu hồi. Không mô tả `syncAll` là global atomic transaction.
9. **Chọn invalidation:** versioned key, atomic routing snapshot hoặc `SwitchPoint` (one-way), không trộn semantics.
10. **Giữ safe lifecycle:** bounded cache, classloader/version retirement, cleanup bound references và handles.
11. **Ghi telemetry:** hit/miss/build count, cache size, build duration, relink count, syncAll duration, target version, error types.
12. **Test dưới contention:** nhiều readers/writers, absent key, failed computation, exceptions, version changes; dùng barriers cho reproducible behavior.
13. **Lý luận theo JMM:** benchmark/test không thay thế happens-before proof; đọc Java API/JLS.
14. **Benchmark trước khi tối ưu:** tách chi phí build, dispatch, relink/sync, memory; sử dụng JMH với warm-up/forks.
15. **Thiết kế rollback:** nếu cần rollback business policy, thực hiện một **bản công bố target/snapshot mới** có version phù hợp; không kỳ vọng đảo ngược calls đã chạy.

Một hệ thống có thể đồng thời sử dụng **versioned ConcurrentHashMap cache** cho expensive lookup và **VolatileCallSite** cho một chỗ dispatch cần thay. Điều quan trọng là xác định được **mỗi concurrency primitive chịu trách nhiệm cho biến/trạng thái nào**, chứ không phải gom càng nhiều primitives càng an toàn.

## 17. Tổng kết và tài liệu chính thức

### 17.1. Ghi nhớ dưới dạng bảng ngắn

| Câu hỏi | Câu trả lời |
| --- | --- |
| Cache `MethodHandle` ở nhiều threads bằng cách nào? | `ConcurrentHashMap.computeIfAbsent` hoặc immutable snapshot với publication rõ |
| Có thể giữ một `Config` có nhiều fields theo version nhất quán không? | Có, nếu dùng immutable config và đọc một published reference |
| `MutableCallSite.setTarget` có tự đảm bảo cross-thread visibility ngay không? | Không; target như field thường, dùng synchronization thích hợp/`syncAll` |
| `VolatileCallSite.setTarget` khác gì? | Volatile memory semantics cho target |
| Muốn invalidation một chiều cho optimized path? | `SwitchPoint.invalidateAll` |
| Muốn thay dispatch reference ngoài CallSite? | `AtomicReference<MethodHandle>`, tự validate signature |
| `syncAll` có transaction across sites hoặc rollback in-flight calls không? | Không |
| Đổi target có thể đổi MethodType không? | Không, site giữ fixed MethodType |
| Cache map có tự thay state bên trong mutable callsite không? | Không |
| Việc test đa luồng chạy đúng đã chứng minh memory model chưa? | Chưa; cần JMM reasoning, thêm test/benchmark phù hợp |

**Kết luận:** Tách bạch **công bố cache reference**, **công bố immutable configuration snapshot** và **công bố CallSite target**. Mỗi tầng có công cụ và hợp đồng memory visibility riêng. Chọn kỹ thuật dựa trên invariants và tần suất relink, đừng dựa vào việc code “trông có vẻ chạy ổn” dưới một số lần stress test.

### 17.2. Tham khảo chính thức Java SE 17

- [`java.lang.invoke.MutableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): semantics của target như field thường; `syncAll`, batch cost, racing updates, in-flight calls.
- [`java.lang.invoke.VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target như volatile variable, `dynamicInvoker` và `setTarget`.
- [`java.lang.invoke.CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): fixed `MethodType` và các loại CallSite.
- [`java.lang.invoke.SwitchPoint`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): `guardWithTest` và invalidation một chiều.
- [`java.util.concurrent.ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `computeIfAbsent`, per-key happens-before, constraints với mapping functions, null values.
- [`java.util.concurrent.atomic.AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): volatile/CAS memory semantics và conditional updates.
- [`java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): acquire/release/volatile/atomic access modes.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, synchronization order, happens-before, final-field semantics.
- [`java.util.concurrent.CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html) và [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): các synchronization guarantees dùng trong test code.
