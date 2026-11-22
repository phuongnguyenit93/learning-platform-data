# Atomic compound operations của ConcurrentHashMap trong Java Concurrency

> **Phạm vi:** Java SE concurrency nói chung, thuộc **Concurrent Collections**. Bài giải thích vì sao các thao tác riêng lẻ của `ConcurrentHashMap` thread-safe nhưng chuỗi đọc–quyết định–ghi không tự nguyên tử; cách sử dụng `putIfAbsent`, `remove(key,value)`, `replace`, `computeIfAbsent`, `computeIfPresent`, `compute` và `merge`; ranh giới nguyên tử theo từng khóa, việc sử dụng `LongAdder`, an toàn của remapping function, các lỗi thường gặp và kiểm thử Java 17. Những phần chỉ thuộc Spring được dành cho chương khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **thread-safe method** với **atomic compound operation**: `get` và `put` đều an toàn khi gọi riêng lẻ nhưng `get → tính toán → put` không phải một thao tác nguyên tử.
- Chỉ ra lịch xen kẽ gây **lost update**, check-then-act, duplicate initialization hoặc stale conditional update, ngay cả khi dùng một `ConcurrentHashMap`.
- Chọn đúng API: `putIfAbsent` cho khởi tạo nếu thiếu; `replace(key, oldValue, newValue)`/`remove(key, value)` cho cập nhật có điều kiện; `compute*`/`merge` cho biến đổi dựa trên giá trị hiện tại.
- Hiểu khác biệt giữa **mapping tồn tại/không tồn tại** và semantics `null` trong `ConcurrentHashMap`, bao gồm việc trả `null` từ remapping function có thể khiến mapping không được thêm hoặc bị xóa.
- Giải thích vì sao những thao tác compound này có bảo đảm **nguyên tử trên một mapping/khóa**, nhưng không tạo một giao dịch nguyên tử cho nhiều khóa, các collection khác hoặc side effects bên ngoài JVM.
- Thiết kế remapping function **ngắn, đơn giản, không làm I/O lâu, không cập nhật đệ quy cùng map, không dựa vào side effect để đo số lần thực thi**.
- Áp dụng mẫu `computeIfAbsent(key, k -> new LongAdder()).increment()` để đếm đồng thời, đồng thời nêu rõ giới hạn của `LongAdder.sum()` và nguy cơ thay thế/xóa mapping trong lúc các thread khác còn dùng counter cũ.
- Kiểm thử Java 17 có trình tự điều khiển để chứng minh lost update của `get/put` và kết quả chính xác khi dùng `merge` dưới nhiều threads.
- Đọc đúng các số liệu `size()`, `mappingCount()`, iterator, bulk operations và memory effects mà không coi chúng là snapshot transaction.

**Thông điệp cốt lõi:** `ConcurrentHashMap` giải quyết an toàn cho cấu trúc map và cung cấp **những phép biến đổi atomic theo từng khóa**. Nó **không tự biến mọi đoạn code có nhiều lời gọi map thành một giao dịch nguyên tử**.

## 2. Một method thread-safe khác một workflow thread-safe

Giả sử map giữ số lượt truy cập:

```java
ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
counts.put("java", 0);
```

Đây là đoạn code trong một method với import `java.util.concurrent.ConcurrentHashMap`. Hai lời gọi trên được thực thi trong cùng thread để tạo dữ liệu ban đầu.

Nhiều người viết:

```java
int old = counts.get("java");
counts.put("java", old + 1);
```

Đây là **mã minh họa không đồng bộ đúng cho phép tăng**. `get()` là thread-safe và `put()` cũng thread-safe, nhưng giữa chúng có một khoảng thời gian để thread khác chạy. Cả hai có thể đọc cùng một giá trị cũ rồi cùng ghi kết quả mới giống nhau.

```text
Ban đầu: count = 0

Thread T1                   Thread T2
-------------------------   -------------------------
get("java") -> 0
                            get("java") -> 0
put("java", 1)
                            put("java", 1)

Kết quả cuối: 1
Số lượt tăng dự kiến: 2
```

Đây là **lost update** do **read–modify–write không nguyên tử**, không phải vì ConcurrentHashMap “không thread-safe”. Mỗi operation riêng lẻ vẫn đúng theo hợp đồng concurrent collection của Java.

Một cách sửa đúng:

```java
counts.merge("java", 1, Integer::sum);
```

Đây là đoạn code trong method, với `counts` đã có. `merge` tính toán và cập nhật mapping hiện tại như **một compound operation atomic theo khóa**. Nếu hai threads cùng tăng cùng khóa, hai kết quả được áp dụng theo một thứ tự nguyên tử hợp lệ; không xảy ra lost update do `get/put` tách rời.

### Cần xác định invariant trước khi chọn primitive

- **Chỉ cần “nếu khóa chưa tồn tại thì đăng ký”** → `putIfAbsent`.
- **Chỉ cập nhật nếu giá trị hiện tại còn bằng giá trị đã quan sát** → `replace(key, expected, update)`.
- **Chỉ xóa nếu mapping chưa bị thay đổi** → `remove(key, expectedValue)`.
- **Cần tính toán từ giá trị hiện tại** → `compute`, `computeIfPresent`, `merge`.
- **Cần tạo object một lần nếu khóa vắng mặt** → `computeIfAbsent`.
- **Cần nguyên tử trên hai khóa hoặc database + map** → các API kể trên **chưa đủ**; cần thiết kế synchronization/transaction khác.

## 3. Atomic compound operation là gì?

Một **compound operation** gồm nhiều quyết định liên quan nhau, chẳng hạn “đọc hiện tại, kiểm tra điều kiện, tính giá trị tiếp theo, cập nhật”. Nếu thực hiện bằng các lời gọi tách biệt:

```text
get(key) -> decide -> put(key, next)
```

thì state có thể thay đổi giữa các bước. Khi dùng API atomic tương ứng, **quyết định và cập nhật được phối hợp thành một operation nguyên tử trên mapping**.

`ConcurrentHashMap` hỗ trợ các compound updates theo khóa thông qua `ConcurrentMap` và các overrides cụ thể. Không nên suy từ interface `Map` chung hoặc từ việc một map đồng bộ từng method rằng **mọi default implementation của compute/merge** đều có cùng mức bảo đảm; ở đây đang nói chính xác về **`ConcurrentHashMap` của Java SE 17**.

Ví dụ:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("votes", 0);
map.compute("votes", (key, current) -> current + 1);
```

Đoạn code trong method, import `ConcurrentHashMap`. Với khóa `votes` đã tồn tại, `compute` lấy mapping hiện tại, tính từ giá trị đó và cập nhật dưới bảo đảm nguyên tử của operation. Nhiều threads gọi `compute` cùng khóa sẽ không bị kiểu mất cập nhật như hai lời gọi `get`/`put`.

### Nguyên tử đến đâu?

**Có:** một lời gọi `compute/merge/replace/putIfAbsent` thành công có effect trên **mapping đang liên quan** như một atomic operation theo contract.

**Không tự có:** một transaction của cả map; atomicity của hai khóa khác nhau; atomicity của việc thêm entry vào map rồi ghi database; atomicity của các trường bên trong object mutable được lưu làm value.

Đừng đánh đồng “mọi thao tác trên map đều concurrency-safe” với “mọi business invariant dùng map đều được đảm bảo”.

## 4. Vì sao cần ConcurrentHashMap cho compound operations?

`HashMap` không bảo đảm thread safety khi nhiều writers sửa cùng lúc. `ConcurrentHashMap` bảo vệ cấu trúc và cung cấp các phép cập nhật atomic có điều kiện theo mapping. Iterator của map là weakly consistent, không tạo snapshot nhất quán của toàn map.

Ở đây, câu hỏi cốt lõi là **điều kiện và cập nhật có nằm trong một phép atomic duy nhất hay không**. `ConcurrentHashMap` không tạo transaction nhiều key, không cho null key/value; các khác biệt nền tảng với `HashMap` đã được giải thích ở bài mở đầu chương.

## 5. Bảng chọn nhanh các thao tác nguyên tử

| API | Khi nào thực hiện cập nhật? | Giá trị trả về / ý nghĩa | Điểm cần nhớ |
|---|---|---|---|
| `putIfAbsent(k, v)` | Chỉ khi khóa chưa có mapping | Giá trị cũ, hoặc `null` nếu absent | Không ghi đè giá trị đã có |
| `remove(k, expectedValue)` | Chỉ khi mapping hiện tại bằng expectedValue | `boolean` | Compare-and-remove theo khóa/giá trị |
| `replace(k, expectedValue, newValue)` | Chỉ khi giá trị hiện tại khớp expectedValue | `boolean` | Compare-and-replace theo equality |
| `replace(k, newValue)` | Chỉ nếu khóa đã có mapping | Giá trị cũ hoặc `null` | Không tạo mapping mới |
| `computeIfAbsent(k, function)` | Chỉ tính và thêm khi absent | Giá trị hiện có/mới, có thể `null` nếu function trả null | Atomic lazy initialization |
| `computeIfPresent(k, function)` | Chỉ tính khi present | Giá trị mới hoặc `null` | Function trả null → xóa mapping |
| `compute(k, function)` | Tính trên current, kể cả absent | Giá trị mới hoặc `null` | Function nhận current là null nếu absent |
| `merge(k, value, function)` | Nếu absent, thêm value; nếu present, kết hợp với current | Giá trị kết quả hoặc `null` nếu mapping bị xóa | Thường hợp counter/aggregation |
| `replaceAll(function)` | Áp function cho các mappings | `void` | **Không** biến toàn bộ map thành một transaction snapshot |

Bảng áp dụng cho `ConcurrentHashMap` Java SE 17. `null` trong các API remapping là **tín hiệu điều khiển được định nghĩa riêng**; nó không có nghĩa CHM lưu null value trong map.

## 6. putIfAbsent: khởi tạo nếu còn thiếu

Sử dụng:

```java
ConcurrentHashMap<String, String> registry = new ConcurrentHashMap<>();
String first = registry.putIfAbsent("job-42", "CREATED");
String again = registry.putIfAbsent("job-42", "DUPLICATE");
System.out.println(first); // null
System.out.println(again); // CREATED
```

Đây là code trong method, với import `ConcurrentHashMap`. Lần đầu khóa chưa tồn tại nên giá trị CREATED được gắn vào, return `null`. Lần hai khóa đã có, method **không ghi đè**, trả giá trị cũ là CREATED.

### Vì sao không viết containsKey rồi put?

```java
if (!registry.containsKey("job-42")) {
    registry.put("job-42", "CREATED");
}
```

Đây là **mẫu check-then-act không nguyên tử**. Hai threads có thể đều thấy khóa absent rồi đều ghi; lần ghi sau sẽ ghi đè. Nếu cần “chỉ một writer thắng”, dùng `putIfAbsent`.

### Khởi tạo có side effect: putIfAbsent chưa chắc đủ

```java
ExpensiveValue candidate = loadFromNetwork();
ExpensiveValue winner = map.putIfAbsent(key, candidate);
```

Đây là code minh họa cần `ExpensiveValue`, `map`, `key`, `loadFromNetwork()`. Dù insert chỉ thắng một lần, **loadFromNetwork()` đã chạy trước `putIfAbsent`** ở mỗi thread gọi. Nhiều threads có thể cùng làm I/O tốn kém, dù chỉ một object được giữ.

`computeIfAbsent` cho phép gắn computation vào điều kiện absent một cách atomic theo khóa; tuy nhiên việc chuyển I/O chậm vào mapping function có thể làm blocking các updates khác và không tự mang durability/timeout. Cần cân nhắc mô hình loading riêng.

## 7. remove(key, value): xóa có điều kiện

`remove(key)` xóa mapping theo khóa. Nếu bạn đã đọc một giá trị trước đó và **chỉ muốn xóa khi mapping chưa đổi**, dùng:

```java
boolean removed = registry.remove("job-42", "CREATED");
```

Đây là code minh họa, `registry` đã định nghĩa ở phần trước. `true` chỉ khi mapping hiện tại khớp giá trị expected theo semantics của map. Nếu thread khác đã chuyển trạng thái sang RUNNING, lời xóa với expected CREATED sẽ trả false; bạn không xóa nhầm state mới.

**Sai lầm cần tránh:**

```java
if ("CREATED".equals(registry.get("job-42"))) {
    registry.remove("job-42"); // Có thể xóa state mới vừa bị thread khác ghi!
}
```

Đoạn này là **mã minh họa lỗi**: thread khác có thể đổi CREATED→RUNNING giữa `get` và `remove`.

Conditional remove có ích cho invalidating cached entries, cleanup một phiên bản đã biết hoặc xóa marker sau khi hoàn tất—nhưng nếu value có thể quay lại giá trị equal cũ, còn phải xét **ABA/generation** ở tầng business.

## 8. replace(key, old, new): compare-and-swap theo mapping

`ConcurrentHashMap.replace(key, expectedValue, newValue)` kiểm tra giá trị hiện tại của một khóa, rồi chỉ thay nếu nó khớp expected.

```java
ConcurrentHashMap<String, String> states = new ConcurrentHashMap<>();
states.put("order", "NEW");
boolean claimed = states.replace("order", "NEW", "PROCESSING");
boolean stale = states.replace("order", "NEW", "FAILED");
```

Đây là code minh họa. `claimed` sẽ true, `stale` sẽ false nếu không có thread khác can thiệp giữa hai phép gọi.

`replace(key, newValue)` là một overload khác: nó chỉ yêu cầu key **đã tồn tại**, không kiểm tra expected old value; return giá trị cũ hoặc null nếu absent.

### Equality thay vì identity

`replace(key, oldValue, newValue)` và `remove(key, value)` sử dụng **value equality (`equals`)** theo semantics map, không phải reference CAS identity `==` của `AtomicReference`. Nếu hai object khác instance nhưng equals bằng nhau, conditional replace có thể coi là khớp. Điều này rất quan trọng khi dùng enum, record, string hoặc value object có equality theo field.

**Cảnh giác:** nếu business invariant cần “đúng generation đã đọc”, equality giữa hai value objects ở hai thời điểm khác nhau chưa chắc đủ. Có thể cần immutable version field trong value, token/generation ID hoặc một giao thức optimistic versioning riêng.

### Compare-and-replace có xử lý toàn bộ workflow không?

Không. Nó chỉ bảo vệ một cập nhật mapping. Nếu caller đọc nhiều khóa A/B rồi chỉ replace A, value B có thể thay đổi trong khoảng đó. Khi business invariant phụ thuộc nhiều khóa, phải bảo vệ/kiểm chứng cả tập dependency.

## 9. computeIfAbsent: lazy initialization nguyên tử

`computeIfAbsent(key, mappingFunction)` là công cụ thường dùng khi muốn tạo value **nếu và chỉ nếu key đang absent**.

```java
ConcurrentHashMap<String, List<String>> buckets = new ConcurrentHashMap<>();
List<String> javaBucket = buckets.computeIfAbsent(
        "java", k -> new CopyOnWriteArrayList<>());
```

Đây là code trong method, cần imports `ConcurrentHashMap`, `List`, `CopyOnWriteArrayList`. Với khóa java absent, mapping function tạo list mới rồi map công bố một reference đến list đó. Nếu key đã có value, function không cần chạy.

Theo JavaDoc `ConcurrentHashMap` Java 17, **toàn bộ method invocation được thực hiện nguyên tử**, và mapping function được áp dụng **nhiều nhất một lần cho mỗi lần invocation / khóa tương ứng** trong quá trình tính toán của lời gọi. Các updates cạnh tranh trên map có thể phải chờ computation hoàn tất.

### Bốn trường hợp cần phân biệt

1. **Khóa present:** trả value hiện có, mapping function không được gọi.
2. **Khóa absent, function trả non-null:** thêm mapping mới rồi trả value đó.
3. **Khóa absent, function trả null:** **không thêm mapping** và trả null; lần gọi sau có thể thử tính lại.
4. **Function ném unchecked exception/Error:** exception được truyền cho caller theo contract, mapping chưa được thiết lập bởi lời gọi đó; ứng dụng phải xử lý failure.

**Không lưu null value vào ConcurrentHashMap.** Đặt null thông qua `put` bị cấm; việc `computeIfAbsent` trả null là kết quả “không tạo mapping”, không phải chứa null trong map.

### Có được coi computeIfAbsent là cache loader production?

Có thể dùng cho object initialization **nhẹ và nhanh**, nhưng không nên mặc định đặt network call/blocking I/O lâu vào function:

```java
// Minh họa nguy cơ: slow I/O trong mapping function.
CacheValue value = cache.computeIfAbsent(key, k -> loadRemote(k));
```

Đây là snippet, `CacheValue`/`cache`/`loadRemote` do ứng dụng định nghĩa. Một số threads cập nhật mapping bị ảnh hưởng có thể bị block khi computation dài. Nếu remote call timeout hoặc ném lỗi, key không được cache thành công và nhiều caller đến sau có thể thử lại, tạo stampede.

Các phương án thiết kế có thể gồm lưu `CompletableFuture<Value>` như một **placeholder cho in-flight computation**, dùng cache có đồng bộ loading và policy timeout/eviction, hoặc tách rate limit của upstream. Những phương án này cũng cần xử lý failed Future/retry/eviction riêng; CHM không tự giải quyết toàn bộ caching lifecycle.

## 10. computeIfPresent: chỉ xử lý giá trị đã tồn tại

`computeIfPresent(key, remappingFunction)` chỉ gọi function khi mapping hiện có.

```java
ConcurrentHashMap<String, Integer> attempts = new ConcurrentHashMap<>();
attempts.put("job", 1);
attempts.computeIfPresent("job", (k, current) -> current + 1);
```

Đây là code minh họa. Sau lời gọi, giá trị job thành 2.

Nếu key absent, function không chạy và map không tạo entry mới. Nếu function trả `null`, mapping hiện tại bị **xóa**:

```java
attempts.computeIfPresent("job", (k, current) -> null);
// "job" absent sau lời gọi nếu không có thread khác thêm lại.
```

Đây là minh họa hợp lệ theo contract CHM: null là một cách yêu cầu remove, không phải null value được lưu.

### Tình huống TTL/cleanup

Khi muốn xóa entry dựa trên thuộc tính value cũ mà không tách check-then-remove:

```java
cache.computeIfPresent(key, (k, entry) ->
        entry.expiredAt(now) ? null : entry);
```

Đây là đoạn minh họa, cần `cache`, `key`, `entry` có method `expiredAt` và `now` được xác định. Quyết định xóa mapping hiện tại dựa trên snapshot value mà function nhận **ngay trong compound operation**. Nhưng thời gian hệ thống/TTL policy và tính mutable của `entry` cần được định nghĩa; nếu entry mutable bị sửa ngoài map, function không tự khóa object.

## 11. compute: remapping tổng quát kể cả absent

`compute(key, (k, oldValue) -> newValue)` được gọi cả khi key present và absent. Nếu absent, `oldValue == null`. Đây là lý do phải xử lý null nếu cần tạo giá trị ban đầu.

```java
ConcurrentHashMap<String, Integer> counters = new ConcurrentHashMap<>();
counters.compute("java", (key, current) ->
        current == null ? 1 : current + 1);
```

Đây là code trong method. Kết quả java=1. Gọi thêm lần nữa cho java=2; mỗi lần đưa ra quyết định theo current mapping ở thời điểm thao tác atomic.

**Semantics trả về null:**

- Nếu mapping cũ tồn tại, function trả null → **xóa mapping**.
- Nếu mapping absent, function trả null → **không tạo mapping**.
- Nếu function ném unchecked exception hoặc Error, lỗi đi ra caller và mapping chưa được update bởi lời gọi đó.

### Không dùng compute để làm I/O hay transaction ngoài JVM

`compute` có thể serialize/coordinate các update cùng key trong map, nhưng function có thể cần được thực thi trong cơ chế đồng bộ nội bộ. Không nên gọi database transaction dài, gửi email, gọi API, hoặc đợi một task khác mà cần cập nhật cùng map từ function.

`compute` không biến tác động ngoài map thành nguyên tử cùng entry. Nếu function đã gửi email rồi xảy ra lỗi trước khi trả, state map có thể không thay đổi còn email đã gửi. Thiết kế phải dựa trên idempotency/outbox/transaction riêng nếu nghiệp vụ đòi hỏi.

## 12. merge: mẫu đơn giản nhất cho phép cộng và aggregation

`merge(key, value, remappingFunction)` có hai nhánh:

- **Absent:** đưa trực tiếp `value` (phải non-null) vào map; **không gọi remappingFunction**.
- **Present:** gọi `remappingFunction.apply(currentValue, value)`; nếu trả non-null thì ghi kết quả; nếu trả null thì **xóa mapping**.

```java
ConcurrentHashMap<String, Integer> totals = new ConcurrentHashMap<>();
totals.merge("clicks", 1, Integer::sum);
totals.merge("clicks", 1, Integer::sum);
```

Đây là code trong method. Kết quả clicks = 2.

### Vì sao merge chống lost update?

Giả sử có 4 threads, mỗi thread gọi `totals.merge("clicks", 1, Integer::sum)` 1.000 lần. Các lần cập nhật cùng khóa được thực thi với compound semantics nguyên tử. Nếu không overflow int và tất cả lời gọi hoàn tất, kết quả cuối là **4.000**.

Điều này khác bản cũ:

```java
// Sai khi nhiều threads tăng cùng key:
totals.put("clicks", totals.get("clicks") + 1);
```

Đây là **mã lỗi minh họa**: get/put có thể interleave và làm mất cập nhật.

### Tính đúng của phép toán

Nếu bạn dùng `Integer::sum` với `Integer`, phép cộng có thể overflow khi tổng vượt giới hạn 32-bit. Atomically applied updates **không** tự bảo đảm không overflow. Nếu yêu cầu miền giá trị lớn hơn, dùng `Long`/`LongAdder` hoặc kiểm tra bounds theo contract.

Nếu remappingFunction không giao hoán/kết hợp (ví dụ ghép String hoặc cập nhật state machine), thứ tự các atomic updates giữa threads có thể ảnh hưởng kết quả hợp lệ. Map bảo đảm atomicity theo khóa, **không áp đặt thứ tự nghiệp vụ** của mọi producer.

### merge và null

`merge(k, null, f)` không hợp lệ trên `ConcurrentHashMap`; `value` phải non-null. Nhưng `f` có thể trả null để yêu cầu remove một mapping tồn tại. Khi absent, `f` không được gọi; `value` được thêm trực tiếp.

## 13. Ví dụ Java 17 chạy độc lập: so sánh lỗi và các thao tác atomic

Ví dụ này có năm phần, tất cả đều được kiểm thử bằng `javac --release 17`:

1. Buộc hai threads đọc cùng count=0 trước khi cả hai ghi bằng `get/put`; kết quả lost update là 1 **một cách xác định**, không phụ thuộc may rủi scheduler.
2. Chạy bốn threads đồng thời, mỗi thread `merge` 1.000 lần; kết quả 4.000.
3. Thử `putIfAbsent`, `replace(key,old,new)` và `remove(key,value)`.
4. Dùng `computeIfAbsent` khởi tạo một `LongAdder` chung, bốn threads increment 1.000 lần; chứng minh factory chạy một lần trong workload đã cho.
5. Dùng `compute`/`computeIfPresent` và function trả null để xóa/không thêm mapping.

Tạo file **`ConcurrentMapAtomicDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentMapAtomicDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            ConcurrentHashMap<String, Integer> broken = new ConcurrentHashMap<>();
            broken.put("count", 0);
            CountDownLatch bothRead = new CountDownLatch(2);
            CountDownLatch mayWrite = new CountDownLatch(1);
            List<Future<?>> unsafeTasks = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                unsafeTasks.add(pool.submit(() -> {
                    int old = broken.get("count");
                    bothRead.countDown();
                    mayWrite.await();
                    broken.put("count", old + 1);
                    return null;
                }));
            }
            bothRead.await();
            mayWrite.countDown();
            for (Future<?> future : unsafeTasks) future.get();
            System.out.println("getThenPut=" + broken.get("count"));

            ConcurrentHashMap<String, Integer> totals = new ConcurrentHashMap<>();
            List<Future<?>> safeTasks = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                safeTasks.add(pool.submit(() -> {
                    for (int j = 0; j < 1000; j++) {
                        totals.merge("count", 1, Integer::sum);
                    }
                    return null;
                }));
            }
            for (Future<?> future : safeTasks) future.get();
            System.out.println("mergeTotal=" + totals.get("count"));

            ConcurrentHashMap<String, String> registry = new ConcurrentHashMap<>();
            System.out.println("firstInsert=" + (registry.putIfAbsent("id", "A") == null));
            System.out.println("secondReturned=" + registry.putIfAbsent("id", "B"));
            System.out.println("compareReplace=" + registry.replace("id", "A", "C"));
            System.out.println("staleReplace=" + registry.replace("id", "A", "D"));
            System.out.println("conditionalRemove=" + registry.remove("id", "C"));

            ConcurrentHashMap<String, LongAdder> counts = new ConcurrentHashMap<>();
            AtomicInteger factoryCalls = new AtomicInteger();
            List<Future<?>> counterTasks = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                counterTasks.add(pool.submit(() -> {
                    for (int j = 0; j < 1000; j++) {
                        counts.computeIfAbsent("java", k -> {
                            factoryCalls.incrementAndGet();
                            return new LongAdder();
                        }).increment();
                    }
                    return null;
                }));
            }
            for (Future<?> future : counterTasks) future.get();
            System.out.println("factoryCalls=" + factoryCalls.get());
            System.out.println("longAdderSum=" + counts.get("java").sum());

            ConcurrentHashMap<String, Integer> statuses = new ConcurrentHashMap<>();
            statuses.compute("attempts", (k, v) -> v == null ? 1 : v + 1);
            statuses.computeIfPresent("attempts", (k, v) -> v + 1);
            System.out.println("computeAndPresent=" + statuses.get("attempts"));
            statuses.computeIfPresent("attempts", (k, v) -> null);
            System.out.println("removedByNull=" + !statuses.containsKey("attempts"));
            System.out.println("absentOnNull=" +
                    (statuses.computeIfAbsent("missing", k -> null) == null
                            && !statuses.containsKey("missing")));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ConcurrentMapAtomicDemo.java
java ConcurrentMapAtomicDemo
```

**Stdout chính xác đã xác minh:**

```text
getThenPut=1
mergeTotal=4000
firstInsert=true
secondReturned=A
compareReplace=true
staleReplace=false
conditionalRemove=true
factoryCalls=1
longAdderSum=4000
computeAndPresent=2
removedByNull=true
absentOnNull=true
```

### Phân tích phần lost update có lịch thực thi kiểm soát

Hai tasks bắt đầu trong pool có **bốn workers**. Mỗi task:

1. Đọc `broken.get("count")` khi giá trị ban đầu là 0.
2. Gọi `bothRead.countDown()`.
3. Chờ `mayWrite.await()`.
4. Sau khi main đã nhận cả hai tín hiệu đã đọc, main gọi `mayWrite.countDown()`.
5. Cả hai tasks ghi `old + 1`; vì old đều là 0, cả hai cùng ghi 1.

Dù task nào ghi trước, giá trị cuối luôn là **1**. Đây là một test xác định chứng minh chính xác **hai method thread-safe không ghép thành atomic increment**.

### Phân tích merge 4.000 lần

Bốn tasks, mỗi task chạy vòng 1.000 lần, gọi:

```java
totals.merge("count", 1, Integer::sum);
```

Tổng 4.000 updates. Mỗi update được thực hiện với semantics nguyên tử theo mapping `count`, nên không mất lần tăng do concurrent interleaving. `Future.get()` ở main chờ các tasks hoàn tất, sau đó mới đọc kết quả. Vì tổng 4.000 nằm trong phạm vi int, không có overflow trong ví dụ.

### Phân tích registry

- `putIfAbsent("id","A")` lần đầu trả null; biểu thức in `firstInsert=true`.
- `putIfAbsent("id","B")` tiếp theo trả giá trị cũ A, không ghi đè; `secondReturned=A`.
- `replace("id","A","C")` thành công và map giữ C.
- `replace("id","A","D")` thất bại vì expected A đã stale.
- `remove("id","C")` xóa có điều kiện và trả true.

Tất cả các operation registry trong demo chạy tuần tự ở main để stdout không phụ thuộc scheduler. Đường concurrent behavior tương tự có thể được kiểm tra bằng latch nếu muốn kiểm thử tranh chấp cụ thể.

### Phân tích computeIfAbsent + LongAdder

Bốn threads gọi `computeIfAbsent("java", factory).increment()`. Vì key java được thêm và **không bị xóa hoặc replace** trong suốt test, một `LongAdder` duy nhất được share, factory chạy một lần trong tình huống đã kiểm tra, và 4.000 increments cộng dồn.

**Đừng suy từ `factoryCalls=1` của demo rằng mọi invocation trong đời ứng dụng sẽ luôn chỉ gọi factory đúng một lần tổng cộng:** nếu key bị remove, function trả null hoặc computation thất bại, những lời gọi sau có thể chạy factory lại. Bảo đảm phải đọc theo **mỗi key, mỗi operation và trạng thái mapping**.

### Phân tích null return

`compute("attempts",...)` khởi tạo thành 1; `computeIfPresent` tăng lên 2. `computeIfPresent` trả null thì **loại mapping**; `computeIfAbsent("missing", k -> null)` không tạo mapping. Hai biểu thức `removedByNull` và `absentOnNull` đều true.

## 14. LongAdder và computeIfAbsent: một mẫu counter hiệu quả

Javadoc `ConcurrentHashMap` có mẫu frequency map gần giống:

```java
ConcurrentHashMap<String, LongAdder> freq = new ConcurrentHashMap<>();
freq.computeIfAbsent(word, k -> new LongAdder()).increment();
```

Đây là đoạn minh họa với `word` định nghĩa bên ngoài, cần import `ConcurrentHashMap` và `java.util.concurrent.atomic.LongAdder`.

### Tại sao hai tầng đồng bộ?

1. **Map:** `computeIfAbsent` bảo đảm việc tạo/nhận reference counter cho key được điều phối atomically.
2. **Counter:** `LongAdder.increment()` thực hiện cập nhật thread-safe trên chính counter object theo API LongAdder.

Không phải `computeIfAbsent` bảo vệ toàn bộ thời gian thread đang gọi `increment()`. Khi function trả về, việc tăng diễn ra **ngoài** compound operation của map, nhưng LongAdder có concurrency semantics riêng.

### Caveat khi map bị remove hoặc replace

Giả sử thread T1 lấy reference LongAdder cũ:

```java
LongAdder oldCounter = freq.computeIfAbsent(word, k -> new LongAdder());
```

Sau đó T2 xóa mapping `word` khỏi map và tạo LongAdder mới. T1 vẫn có reference `oldCounter` và gọi `increment()` trên object **không còn được map trỏ tới**. Không có data race trong chính LongAdder, nhưng **logical count theo key có thể bị mất** khi bạn đọc current mapping mới.

Vì vậy mẫu này hoạt động tốt khi lifecycle của counter ổn định và **không xóa/replace counter trong lúc có updater đang dùng**. Nếu cần reset/rotate counters trong thời gian threads đang increment, hãy thiết kế epoch/generation ownership, snapshot/hand-off hoặc đồng bộ rõ ràng.

### `LongAdder.sum()` có phải snapshot atomic không?

Không. `sum()` trả tổng hiện tại được tính từ các phần của LongAdder, và **không phải snapshot nguyên tử tuyệt đối** khi các thread khác còn increment đồng thời. Nó thích hợp cho thống kê hiệu năng cao, nhưng không dùng làm tín hiệu transaction/sequence cần một giá trị tuyến tính hóa chính xác giữa concurrent writers.

Trong demo, main gọi `Future.get()` cho **tất cả** worker tasks xong rồi mới gọi `sum()`, nên không còn writer song song và kết quả 4.000 là xác định.

### Khi nào dùng AtomicLong thay LongAdder?

- `AtomicLong` phù hợp với counter cần các phép `compareAndSet`, `getAndIncrement` và giá trị đọc tức thời có semantics atomic của một biến.
- `LongAdder` có thể giảm contention đối với thống kê có rất nhiều threads cùng tăng, đổi lại `sum()` không phải một atomic snapshot khi updates đang diễn ra.
- Với counter nhỏ hoặc contention thấp, chọn loại đơn giản nhất rồi đo, không mặc định LongAdder luôn nhanh hơn.

## 15. Đừng mutate map bên trong remapping function

JavaDoc của `ConcurrentHashMap.compute/computeIfAbsent/computeIfPresent/merge` yêu cầu computation ngắn, đơn giản và **không nên cố cập nhật các mapping khác của cùng map ngay trong computation**. Việc update đệ quy có thể gây blocking hoặc một `IllegalStateException` khi JVM phát hiện recursive update không bao giờ hoàn tất.

Ví dụ sai:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.computeIfAbsent("a", k -> {
    map.put("b", 1); // Không làm việc này bên trong mapping function.
    return 2;
});
```

Đây là **ví dụ thiết kế cần tránh**, không có cam kết chương trình luôn ném exception trong mọi interleaving/keys. Bởi cách map điều phối cập nhật, việc thay một key khác có thể vô tình gây contention/reentrancy vấn đề; không phụ thuộc vào việc một lần test cho qua.

Ví dụ sai rõ hơn:

```java
map.computeIfAbsent("a", k ->
        map.computeIfAbsent("a", x -> 1)); // Recursive update.
```

Đây là đoạn minh họa lỗi. Nếu một update đệ quy có thể bị phát hiện như non-terminating recursion, `ConcurrentHashMap` có thể ném `IllegalStateException`; không dùng exception đó làm một kiểu flow control thông thường.

**Nguyên tắc:** function nên là phép biến đổi thuần túy theo `key, current`, có thời gian chạy ngắn, không block, không thực hiện side effect không đảo ngược, không gọi những method cập nhật chính map đó. Nếu cần cập nhật nhiều khóa, hãy tách ra giao thức khác.

## 16. Vì sao slow remapping function có thể làm giảm throughput?

Một số compound methods của CHM giữ coordination với những update cạnh tranh khi remapping function đang thực hiện.

```java
// Minh họa anti-pattern: I/O dài trong compute.
map.compute(key, (k, old) -> {
    sleepOrCallRemoteService();
    return transform(old);
});
```

Đây là pseudocode Java minh họa; `sleepOrCallRemoteService` và `transform` do application định nghĩa.

Một computation lâu có thể làm **những updates khác bị block**, đặc biệt khi chúng cạnh tranh trên cùng mapping hoặc phần state nội bộ bị ảnh hưởng. Không được tuyên bố “compute block toàn bộ ConcurrentHashMap cho mọi key” — CHM được thiết kế cho concurrency giữa những keys; mức ảnh hưởng phụ thuộc các va chạm và implementation.

### Điều nên làm

- Chuẩn bị dữ liệu có thể tính **ngoài function** nếu không cần snapshot current.
- Nếu tính toán bắt buộc phụ thuộc current, làm phần **nhanh và thuần túy** trong `compute`.
- Với I/O dài, thường cần một state machine, placeholder Future, cache loading framework hoặc task queue để tách transaction thời gian dài khỏi map update.
- Đo tail latency và contention khi traffic thật, không chỉ throughput trung bình.
- Đặt deadline/timeout theo API ngoài map, không dùng map lock làm biện pháp chờ network bất tận.

## 17. Hàm mapping có thể được gọi lại không?

Không nên áp một câu trả lời cho mọi loại map hoặc mọi operation.

- Với **`ConcurrentHashMap.computeIfAbsent` Java SE 17**, function được áp dụng at most once cho key ở một invocation theo contract. Nếu key đã có mapping, function không chạy. Nhưng nếu lần trước trả null hoặc fail, lần invocation sau có thể gọi lại.
- Với `compute`/`merge` trong CHM, một invocation được điều phối atomically cho mapping; đừng giả định rằng function được dùng như một callback của transaction manager ngoài JVM hoặc sẽ được retry theo business policy của ứng dụng.
- Với một số `Map` khác, default methods triển khai bằng `get`/`put` không nhất thiết có cùng atomicity; phải đọc API của **class thực tế**.
- Với **các retry loop do caller viết**, function/task có thể chạy nhiều lần qua nhiều invocations; không đặt side effects không idempotent bên trong mà không kiểm soát.

Câu hỏi quan trọng hơn “function gọi mấy lần?” là: **function có side effect nào mà việc chạy trong một critical update làm thay đổi correctness hay throughput không?** Ngay cả một lần gọi duy nhất cũng có thể gây vấn đề nếu nó gửi tiền, xóa file hoặc chờ lock vòng phụ thuộc.

## 18. Multi-key invariants: những gì ConcurrentHashMap không tự làm

Giả sử bạn muốn chuyển 10 đơn vị từ tài khoản A sang B, cả hai nằm trong cùng ConcurrentHashMap:

```java
balances.compute("A", (k, a) -> a - 10);
balances.compute("B", (k, b) -> b + 10);
```

Đây là **đoạn minh họa không đủ an toàn cho giao dịch**: `balances` có các entries phù hợp và balance không null. Mỗi `compute` trên một key là atomic, **nhưng cả cặp không phải một atomic operation**. Một reader giữa hai lời gọi có thể thấy tổng tiền bị giảm 10, hoặc failure giữa hai lời gọi khiến A giảm mà B chưa tăng.

### Các giải pháp khả thi tùy yêu cầu

1. **External lock cho toàn bộ invariant:** bảo vệ cả hai updates và các readers cần snapshot nhất quán bằng cùng lock. Nếu nhiều locks, dùng thứ tự khóa ổn định để tránh deadlock.
2. **Một immutable aggregate state:** lưu một object chứa cả A và B trong `AtomicReference<ImmutableLedger>`, CAS thay nguyên object sau khi validate; bảo đảm cập nhật trên **một reference**. Phù hợp khi size/invariant cho phép.
3. **Transaction ở lớp lưu trữ:** nếu dữ liệu cần durability/consistency xuyên JVM hoặc database, dùng transaction phù hợp.
4. **Event sourcing/serial owner:** serialize commands qua một owner cập nhật ledger và công bố snapshots nhất quán; cần xử lý failure/recovery.

Không có magic `ConcurrentHashMap.computeAllKeysAtomically()` trong API chuẩn. Các bulk methods không biến nhiều keys thành transaction.

### replaceAll không phải global atomic snapshot

`replaceAll((k,v) -> ...)` áp một function lên các mappings, nhưng khi những threads khác đang mutate, nó không tạo **một lần chuyển toàn bộ map nguyên tử** như thay immutable snapshot. Nếu business invariant yêu cầu tất cả keys đổi cùng thời điểm, đừng dùng `replaceAll` làm transaction.

## 19. Iteration, size, mappingCount và snapshot semantics

`ConcurrentHashMap` cho phép iteration trong khi concurrent updates mà không ném `ConcurrentModificationException` theo kiểu fail-fast của HashMap; iterator có **weakly consistent semantics**.

Điều đó nghĩa là:

- Iterator có thể phản ánh một số updates concurrent tùy thời điểm quan sát, không phải một snapshot transaction của toàn bộ map.
- `size()` và `mappingCount()` hữu ích cho thống kê/monitoring, nhưng nếu threads đang update liên tục thì giá trị có thể mang tính ước lượng/transient.
- `mappingCount()` trả kiểu `long`, hữu ích khi mapping count có thể vượt giới hạn biểu diễn bởi `int` của `size()`.
- Một check như `if (map.size()==0) {...}` không giữ map “rỗng” cho phần code tiếp theo; key có thể được thêm ngay sau check.
- Các bulk operations `forEach`, `search`, `reduce` không áp dụng một global lock để tạo snapshot cô lập theo transaction.

Nếu cần snapshot ổn định, có thể phối hợp **external synchronization/quiescence protocol**, immutable snapshots hoặc kiến trúc versioned state. `new HashMap<>(concurrentMap)` có thể tạo một bản copy tại một giai đoạn, nhưng nếu writers đang chạy, bản copy đó **không mặc nhiên là một global point-in-time snapshot**.

## 20. Null, absent và giá trị mặc định

`ConcurrentHashMap` không cho phép null key và null value:

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
// map.put(null, 1);       // NullPointerException
// map.put("a", null);      // NullPointerException
```

Đây là đoạn minh họa với hai dòng cố tình được comment để không làm chương trình crash.

Việc cấm null tạo ra một ý nghĩa rõ ràng cho `get(key) == null`: tại thời điểm đọc, không có mapping tương ứng, khác `HashMap` có thể lưu null value.

Nhưng `get(key)==null` vẫn chỉ là **snapshot tạm thời**, không phải quyền đặt chỗ key. Hai threads cùng đọc null rồi gọi put vẫn có thể race. Để tạo nếu absent, gọi `putIfAbsent` hoặc `computeIfAbsent`.

### null từ compute/merge là điều khiển, không phải data value

| API | Return null từ function | Hành vi đối với map |
|---|---|---|
| `computeIfAbsent` | Không tạo entry | Key vẫn absent |
| `computeIfPresent` | Xóa entry hiện có | Key absent sau operation, trừ update concurrent sau đó |
| `compute` | Xóa nếu present; không thêm nếu absent | Key absent |
| `merge` | Xóa entry khi remappingFunction của present key trả null | Key absent |

**Không được viết code dựa vào “null value” đang nằm trong CHM.** Nếu business có hai trạng thái “unknown” và “absent”, phải dùng một wrapper/enum/record riêng để thể hiện unknown bằng non-null object.

## 21. ABA và value equality khi dùng conditional replace

Một tình huống tinh vi: T1 đọc value A. T2 thay A→B→A (giá trị cuối **equals** A). T1 thực hiện:

```java
boolean updated = map.replace(key, expectedA, next);
```

Đây là đoạn minh họa với `map`, `key`, `expectedA` và `next` đã định nghĩa.

Nếu mapping hiện tại equals expectedA, phép replace có thể thành công dù giữa đó đã có thay đổi. Đây là một hình thức **ABA ở cấp logic của optimistic compare/update**. Nếu business invariant yêu cầu “không một ai thay đổi mapping kể từ khi tôi đọc”, kiểm tra equality của value cuối có thể chưa đủ.

Một cách xử lý là gắn **generation/version** vào immutable value:

```java
record VersionedState(long generation, String status) { }

ConcurrentHashMap<String, VersionedState> states = new ConcurrentHashMap<>();
VersionedState observed = states.get("job");
if (observed != null) {
    VersionedState next = new VersionedState(
            observed.generation() + 1, "RUNNING");
    boolean changed = states.replace("job", observed, next);
}
```

Đây là code trong method với `record` (Java 17 hỗ trợ). `record` sinh equality dựa trên components, nên version khác nhau làm expected value khác nhau. **Điều kiện:** mọi đường thay mapping phải giữ quy tắc tăng generation, không reset/reuse generation khi reader cũ còn tồn tại.

Không dùng versioning nếu invariant thực sự chỉ cần current state equality; thêm phức tạp mà không mang thêm correctness cần thiết.

## 22. Mutable values: ConcurrentHashMap không khóa object bên trong

`ConcurrentHashMap<K, V>` an toàn cho **cấu trúc key→reference**. Nếu value là một `ArrayList`, `HashMap`, POJO mutable hoặc counter thường, việc giữ reference trong CHM **không tự làm phương thức của value thread-safe**.

```java
ConcurrentHashMap<String, ArrayList<String>> map = new ConcurrentHashMap<>();
map.put("queue", new ArrayList<>());
map.get("queue").add("item"); // Race nếu nhiều threads add cùng ArrayList.
```

Đây là **code minh họa thiếu an toàn**, cần imports tương ứng. Nhiều threads có thể cùng mutate `ArrayList` không synchronized dù container là CHM.

Giải pháp:

- Dùng value immutable và thay bằng atomic `compute` hoặc `replace`.
- Dùng value thread-safe phù hợp, ví dụ `LongAdder`, `ConcurrentLinkedQueue` hoặc một lock-protected object.
- Dùng ownership transfer để một thread là owner duy nhất của mutable value tại một thời điểm.
- Đừng trả mutable object cho caller để caller mutate tùy ý nếu state phải tuân thủ invariant được map update quản lý.

### compute có bảo vệ mutation bên trong value không?

Trong một `compute` theo key, logic của function được phối hợp với **các atomic mapping updates cùng key**. Nhưng nếu thread khác đã giữ reference đến value mutable và sửa field trực tiếp **không thông qua compute/lock cùng protocol**, nó vẫn có thể race. Bởi vậy, chỉ sử dụng mutable value được bao bọc đúng giao thức, hoặc ưu tiên immutable replacement.

## 23. Memory consistency trong ConcurrentHashMap

Java concurrent collections có memory consistency guarantees: hành động trong một thread **trước khi công bố object vào concurrent collection** *happen-before* những hành động trong thread khác **sau khi truy cập hoặc lấy object đó** qua collection theo hợp đồng liên quan.

Trong `ConcurrentHashMap`, một lần `get(key)` trả một giá trị non-null có quan hệ memory ordering phù hợp với insertion/update tương ứng của mapping, cho phép công bố object đã chuẩn bị an toàn nếu dùng đúng protocol.

Ví dụ:

```java
record Item(int id, String payload) {}
ConcurrentHashMap<String, Item> items = new ConcurrentHashMap<>();
items.put("order-1", new Item(1, "created"));
// Thread khác get("order-1") rồi dùng immutable record.
```

Đây là đoạn code trong method, với import `ConcurrentHashMap`, record Java 17. Nếu thread khác đọc được Item đã được publish qua map đúng cách, các giá trị đã khởi tạo trước publication được quan sát theo contract.

Nhưng:

1. CHM không làm mutable fields của object tự có happens-before nếu threads tiếp tục sửa chúng **ngoài** map.
2. Đọc `get` ở hai keys khác nhau không tự tạo **snapshot nhất quán** của một business transaction hai khóa.
3. Việc `Future.get()` chờ workers trong demo tạo completion/visibility ở main; nó **không** tự sửa race `get+put` diễn ra trước đó giữa workers.
4. `Thread.sleep()` không là synchronization mechanism thay thế `compute/merge/replace`.
5. Atomic mapping update là điểm phối hợp **trên reference/value mapping**; nó không làm side effect database, network hoặc file system trở nên atomic với map.

Phân biệt atomicity, visibility và consistency của invariant giúp chọn đúng công cụ.

## 24. Rejection và exception từ remapping function

Các method mapping có thể ném ngoại lệ:

- `NullPointerException` khi key/function/value bắt buộc non-null bị truyền null.
- `IllegalStateException` trong một số recursive update có thể phát hiện theo contract.
- Runtime exception hoặc Error do mapping/remapping function ném. Với `compute`/`merge`/`computeIfAbsent`, mapping không được cập nhật bởi lời gọi bị lỗi theo semantics được công bố.
- Application-specific runtime exception do kiểm tra invariant và cố tình throw.

Ví dụ:

```java
try {
    map.compute("job", (k, old) -> {
        if (old != null && old < 0) {
            throw new IllegalStateException("negative state");
        }
        return old == null ? 1 : old + 1;
    });
} catch (IllegalStateException e) {
    reportFailure(e);
}
```

Đây là code minh họa với `map` kiểu `ConcurrentHashMap<String,Integer>`, `reportFailure` do ứng dụng định nghĩa. Khi function ném, không được coi cập nhật đã thành công. Nhưng một side effect mà function làm **trước khi throw** có thể đã xảy ra, nên đừng đặt tác động không đảo ngược trong đó.

### Không nhầm failed update với rejected executor task

Các exceptions trên xảy ra trong lời gọi map. Nếu code gọi map từ một task `ExecutorService.submit()`, ngoại lệ đó có thể được đóng gói trong `Future` và caller quan sát qua `ExecutionException.getCause()`. Việc đó thuộc đường xử lý lỗi task, không thay đổi semantics atomic của CHM. Không nhầm `RejectedExecutionException` của thread pool với một “rejection” từ CHM; ConcurrentHashMap compound methods không dùng rejection handler của executor.

## 25. So sánh với Collections.synchronizedMap và ConcurrentSkipListMap

### Collections.synchronizedMap

Một map được wrap:

```java
Map<String, Integer> synchronizedMap =
        Collections.synchronizedMap(new HashMap<>());
```

Đây là code trong method, cần imports `Map`, `Collections` và `HashMap`. Wrapper đồng bộ các method, nhưng **nhiều lời gọi tách biệt** vẫn cần synchronized block của caller nếu muốn một compound operation.

```java
synchronized (synchronizedMap) {
    int old = synchronizedMap.get("count");
    synchronizedMap.put("count", old + 1);
}
```

Đây là ví dụ đúng về việc dùng **cùng monitor của wrapper** cho cả hai bước. Cần đảm bảo **mọi access khác liên quan cùng invariant** cũng tuân thủ giao thức khóa. So với CHM, một global lock có thể làm các keys độc lập tranh chấp mạnh hơn dưới workload concurrent.

### ConcurrentSkipListMap

`ConcurrentSkipListMap` là một ordered concurrent map dựa trên sort order của keys. Nó phù hợp khi cần sorted/navigable operations. Nhưng **không suy rằng mọi phương thức compute của mọi ConcurrentMap** có cùng implementation atomic semantics như CHM: hãy đọc JavaDoc của class thực tế và xác định yêu cầu per-key vs multi-key.

### AtomicReference với immutable whole-state

Nếu business invariant phụ thuộc nhiều keys và số lượng dữ liệu tương đối nhỏ/có thể copy, một `AtomicReference<ImmutableState>` cho phép CAS thay **toàn bộ snapshot state** có thể phù hợp hơn CHM. Chi phí copy và contention cần cân nhắc; không có giải pháp nào luôn tốt nhất.

## 26. Hiệu năng và thiết kế key

Atomic compound operations có chi phí coordination. Không có một “benchmark winner” chung.

Những yếu tố ảnh hưởng:

- Số threads truy cập **cùng một hot key** hay phân tán trên nhiều keys.
- Độ dài remapping function.
- Chất lượng phân bố `hashCode()` và collisions.
- Tần suất resize, số lượng entries, memory/GC pressure.
- Chi phí tạo object cho mỗi update, boxing `Integer`, churn của entries.
- Tính chất workload CPU-bound/I/O-bound.
- Mức contention thực, kích thước concurrency trong executor.
- Phương án dùng `LongAdder` hay immutable value replacement.

### Hot key và LongAdder

Nếu mọi thread cùng `merge("globalCount", 1, Integer::sum)`, update vào **cùng mapping** tạo contention. Đối với thống kê frequency, đặt `LongAdder` làm value giúp nhiều threads increment trên counter có thiết kế giảm contention.

Nhưng `LongAdder.sum()` không phải snapshot atomic khi updates đang tiếp diễn, và việc map entry bị reset/replace cần ownership/epoch protocol. Không dùng LongAdder cho sequence ID hoặc invariant cần một giá trị CAS xác định nếu API không phù hợp.

### Key phải có equality/hash ổn định

Nếu key là object mutable và `hashCode()/equals()` phụ thuộc những field bị thay đổi sau khi insert, truy vấn có thể không tìm đúng entry và hành vi logical map bị phá, dù collection thread-safe. Ưu tiên immutable keys như String, record bất biến hoặc identifier có equality ổn định.

### Đừng benchmark bằng một lần System.nanoTime

Khi so sánh `merge`, `compute`, `AtomicLong` và `LongAdder`, dùng workload thực và benchmark methodology phù hợp (ví dụ JMH). Một vài microseconds khác biệt trong một lần thử không đủ kết luận. Quan trọng hơn: chỉ so sánh những phương án **đều đúng về invariant**.

## 27. Kiểm thử concurrent updates đáng tin

Test concurrency nên có hai lớp:

### A. Test invariant và interleaving cụ thể

1. **get→put lost update:** buộc hai threads cùng đọc 0 trước khi ghi; kết quả phải cho thấy lý do code sai (demo đã làm).
2. **merge increments:** bốn threads × N increments; sau khi mọi Future hoàn tất, giá trị bằng 4N.
3. **putIfAbsent contest:** N threads cùng cố insert một key; xác minh chỉ một mapping cuối cùng và giá trị thuộc một candidate hợp lệ, không khẳng định thread nào thắng.
4. **Conditional replace race:** T1 và T2 cùng expected old; tại most một thao tác replace sang hai next values khác nhau thành công nếu không có thao tác đưa value về old ở giữa.
5. **computeIfAbsent one-key initialization:** nhiều threads cùng yêu cầu một key absent; tạo một object value non-null ổn định và quan sát factory invocation theo contract.
6. **Null return:** compute/computeIfPresent/merge trả null đúng nhánh sẽ xóa mapping; computeIfAbsent trả null không insert.
7. **Exception:** mapping function throw; xác nhận không có mapping mới do chính lời gọi đó.
8. **Mutable value race:** test sự khác biệt giữa map atomicity và value operations không thread-safe.
9. **Multi-key transfer:** stress reader/writer để thấy per-key updates không làm tổng của hai account bất biến tại mọi thời điểm.
10. **Lifecycle:** không xóa/reuse LongAdder khi threads vẫn giữ reference nếu invariant yêu cầu count không mất.

### B. Stress và instrumentation

- Dùng `CountDownLatch`/`CyclicBarrier` đặt checkpoint, thay vì đoán bằng `Thread.sleep()`.
- Dùng `Future.get(timeout, unit)` để test có deadline và lấy exception của worker.
- Kiểm tra tổng đúng sau khi **tất cả** writers hoàn tất; nếu đọc trước thì bạn có thể quan sát một giá trị trung gian hợp lệ.
- Với contention cao, ghi metrics về throughput/latency, không log mỗi operation làm lệch workload.
- Test keys có hash collisions hợp lệ và key classes có equals/hashCode chuẩn.
- Nếu cần khẳng định algorithm hoàn toàn linearizable, có thể kết hợp event histories/model checking; “stress test chạy được một lần” chưa phải formal proof.

**Không thử “sửa” lost update bằng `Thread.sleep` giữa `get` và `put`.** Nó chỉ làm race dễ xảy ra hơn/chuyển timing; giải pháp là thao tác compound đúng.

## 28. Những lỗi triển khai phổ biến

1. **Dùng get rồi put để tăng counter.** Hai lời gọi thread-safe không tạo atomic increment; dùng `merge`/`compute` hoặc counter atomic.
2. **Dùng containsKey rồi put làm lazy initialization.** Check-then-act race; dùng `putIfAbsent`/`computeIfAbsent`.
3. **Tạo expensive object trước putIfAbsent rồi tưởng factory chạy một lần.** Nhiều threads có thể tạo trùng candidates, chỉ insert một winner.
4. **Đặt I/O dài trong computeIfAbsent.** Mapping function có thể block competing updates; cân nhắc loading protocol riêng.
5. **Mutate map trong remapping function.** Recursive/cross-key update có thể gây lỗi hoặc blocking khó đoán.
6. **Cho rằng computeIfAbsent trả null là lưu null.** Không: mapping không được thiết lập.
7. **Cho rằng computeIfPresent gọi function ngay cả khi absent.** Không: chỉ present mapping.
8. **Cho rằng merge gọi remapping function cả khi absent.** Không: khi absent, dùng value supplied trực tiếp.
9. **Nhầm replace(key,newValue) với replace(key,expected,newValue).** Overload đầu không kiểm tra expected value.
10. **Nhầm remove(key) với remove(key,expectedValue).** Remove chỉ theo key có thể xóa state mới.
11. **Cho rằng value equality nghĩa là đúng generation.** A→B→A có thể tạo stale compare/update; cần version nếu invariant đòi.
12. **Dùng HashMap trong nhiều threads mà không synchronization.** Không có thread safety của CHM.
13. **Dùng Collections.synchronizedMap nhưng không giữ lock cho nhiều operations.** Compound sequence vẫn có race nếu không khóa cả chuỗi.
14. **Dùng LongAdder rồi xóa key trong lúc threads vẫn increment old counter.** Có thể mất logical updates dù LongAdder thread-safe.
15. **Cho rằng LongAdder.sum là snapshot atomic khi concurrent writes.** Không; cần quiescence hoặc cơ chế khác nếu yêu cầu đọc chính xác tại một thời điểm.
16. **Cho rằng compute bảo vệ mutable fields của object được lưu.** Chỉ mapping được coordinated; direct mutation ngoài protocol vẫn race.
17. **Dùng replaceAll để làm transaction đổi mọi keys.** Không có global atomic update.
18. **Dùng size()/isEmpty() làm chốt quyết định không đổi.** Concurrency có thể thay đổi ngay sau snapshot.
19. **Cho rằng iterator tạo snapshot cô lập.** CHM iterator weakly consistent.
20. **Dùng mutable key với hashCode thay đổi sau insert.** Làm key lookup sai.
21. **Đặt network/email side effect trong remapping function.** Operation map không cùng transaction với external side effect.
22. **Bỏ qua exception từ mapper.** Mapping không update, nhưng external side effect trước exception có thể đã xảy ra.
23. **Cho rằng method có chữ atomic nghĩa mọi business state atomic.** Scope của operation theo một mapping, không theo cả workflow.
24. **Đo size trước rồi tin map còn trống lúc put.** Dùng atomic admission method thay check-then-act.
25. **Giả định thứ tự hoàn tất của threads trong merge có ý nghĩa nghiệp vụ.** Với function không giao hoán, thứ tự khác nhau tạo kết quả khác; phải thiết kế ordering nếu cần.
26. **Tăng boxed Integer quá lớn mà không xét overflow/allocations.** Counter có miền và hiệu năng constraints riêng.
27. **Dùng computeIfAbsent làm cache lỗi vĩnh viễn.** Nếu function throw/null, không có mapping; caller sau có thể chạy lại; cần failure/negative cache policy khi cần.
28. **Dùng putIfAbsent cho “execute only once” external effect.** Chỉ mapping insertion là atomic, external effect cần idempotency và recovery.
29. **Đọc get(key) non-null rồi tin nó không thay đổi trong lúc xử lý.** Mapping có thể đổi; dùng conditional replace/compute nếu cần validate khi commit.
30. **Coi ConcurrentHashMap là distributed lock.** Nó là in-process concurrent collection, không cung cấp cross-process mutual exclusion/durability.

## 29. Checklist review code production

Trước khi merge một đoạn code dùng `ConcurrentHashMap`, kiểm tra:

- **Invariant:** một khóa độc lập hay phụ thuộc nhiều keys/resources?
- **Read–modify–write:** có bất kỳ đoạn `get` rồi `put/remove` mà mục đích là atomic không?
- **API:** đã chọn đúng `putIfAbsent`/`replace`/`remove(k,v)`/`compute*`/`merge`?
- **Absent:** function có xử lý current null đúng khi key vắng mặt?
- **Null result:** return null có vô tình xóa mapping hoặc không tạo mapping không?
- **Side effect:** mapping/remapping function có I/O, lock, network, writes ngoài map hoặc recursive update?
- **Duration:** computation trong function có ngắn, bounded và không làm contention nghiêm trọng?
- **Equality:** expected value có dùng equals thích hợp? Cần generation để ngăn ABA không?
- **Value safety:** object mutable trong map có được bảo vệ bằng cơ chế riêng không?
- **LongAdder lifecycle:** có xóa/reset counter trong khi threads vẫn giữ reference không?
- **Visibility:** state được chuẩn bị trước publication có immutable/ownership protocol đúng?
- **Capacity:** số keys có thể tăng không giới hạn và gây memory pressure không?
- **Metrics:** hot keys, collision, latency, memory, mapper failures và throughput có được theo dõi?
- **Testing:** có test interleaving bằng latch và test kết quả sau Future.get? Có stress cùng key và nhiều keys?
- **Failure semantics:** nếu operation throw sau side effect trước đó, recovery/idempotency ra sao?
- **Compatibility:** API có sẵn trong JDK triển khai (ví dụ Java 17) không?

## 30. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `ConcurrentHashMap.get` và `put` đều thread-safe. Tại sao `put(k, get(k)+1)` vẫn có thể mất cập nhật?  
**Đáp án:** Vì hai lời gọi tách biệt. Hai threads có thể cùng đọc giá trị cũ rồi cùng ghi một giá trị mới; không có atomic read–modify–write.

**Câu 2.** Muốn tăng counter int cho một key, lời gọi đơn giản là gì?  
**Đáp án:** `map.merge(key, 1, Integer::sum)`, với miền int không overflow và không cần multi-key transaction.

**Câu 3.** Hai threads đều gọi `putIfAbsent(k, newValue)`, chuyện gì được bảo đảm?  
**Đáp án:** Một mapping chỉ được thêm theo điều kiện absent; nếu đã present, call sau không ghi đè mà trả giá trị hiện tại theo contract.

**Câu 4.** Tại sao `putIfAbsent(key, loadExpensive())` có thể tính toán trùng?  
**Đáp án:** Biểu thức argument `loadExpensive()` chạy **trước** lời gọi putIfAbsent ở mỗi thread; method chỉ bảo vệ insertion.

**Câu 5.** `computeIfAbsent` function trả null thì key có được lưu với null value không?  
**Đáp án:** Không. ConcurrentHashMap không cho phép null value; mapping không được thêm.

**Câu 6.** `computeIfPresent` function trả null khi key đã tồn tại có nghĩa gì?  
**Đáp án:** Yêu cầu xóa mapping của key đó như phần của compound update.

**Câu 7.** `merge` khi key absent có gọi remapping function không?  
**Đáp án:** Không. Nó đặt supplied non-null value trực tiếp.

**Câu 8.** `replace(k, old, new)` so old bằng identity hay equality?  
**Đáp án:** Theo value equality của map (equals), không phải CAS reference identity.

**Câu 9.** `remove(k, v)` khác `remove(k)` thế nào?  
**Đáp án:** Nó chỉ xóa nếu mapping hiện tại khớp expected value; giúp tránh xóa một state đã bị thread khác thay đổi.

**Câu 10.** Một `compute` trên A và `compute` trên B có cùng tạo transaction atomic hai khóa không?  
**Đáp án:** Không. Mỗi compound update là atomic theo khóa, không phải một commit chung.

**Câu 11.** Vì sao remapping function không nên cập nhật chính map đệ quy?  
**Đáp án:** Có thể vi phạm contract, tạo blocking/non-termination hoặc `IllegalStateException` khi recursive update bị phát hiện.

**Câu 12.** Một remapping function gọi API network rồi trả value có thể gây vấn đề gì?  
**Đáp án:** Làm competing updates chờ lâu, có timeout/partial side effect không nằm trong transaction của map, và gây retry/consistency phức tạp.

**Câu 13.** Mẫu `computeIfAbsent(k, ignored -> new LongAdder()).increment()` có hai nguồn thread safety nào?  
**Đáp án:** CHM phối hợp initialization của mapping; LongAdder bảo vệ increment trên counter object.

**Câu 14.** Nếu thread khác remove key rồi tạo LongAdder mới, thread đã giữ old LongAdder có thể tiếp tục increment không?  
**Đáp án:** Có. Nó tăng object cũ không còn được map trỏ tới, nên logical count theo key có thể bị mất.

**Câu 15.** `LongAdder.sum()` là atomic snapshot hoàn hảo khi writers vẫn đang increment không?  
**Đáp án:** Không. Nó là phép lấy tổng không phải snapshot atomic trong lúc update concurrent.

**Câu 16.** `ConcurrentHashMap.size() == 0` chứng minh map sẽ tiếp tục rỗng tới sau lời gọi tiếp theo không?  
**Đáp án:** Không. Snapshot/estimate có thể thay đổi ngay; cần atomic operation/giao thức khóa khác.

**Câu 17.** Iterator của ConcurrentHashMap có snapshot nhất quán theo một thời điểm chung không?  
**Đáp án:** Không. Nó weakly consistent và có thể phản ánh một số thay đổi concurrent.

**Câu 18.** `computeIfAbsent` có phải đảm bảo external API chỉ được gọi một lần vĩnh viễn cho key không?  
**Đáp án:** Không. Mapping có thể bị remove, computation có thể fail/null, các invocations sau có thể thử lại, và external side effects không có exactly-once guarantee.

**Câu 19.** Hai value objects bằng nhau theo equals nhưng thuộc hai generation khác nhau. `replace(k, old, new)` có phát hiện generation không?  
**Đáp án:** Không nếu equality không chứa generation. Cần version field/immutable state nếu invariant phải phân biệt thế hệ.

**Câu 20.** Vì sao test demo dùng latch cho `get/put` nhưng Future.get cho `merge`?  
**Đáp án:** Latch buộc hai threads cùng đọc giá trị cũ để chứng minh lost update một cách xác định; Future.get chờ tất cả updates atomic kết thúc trước khi xác minh 4.000.

## 31. Bài tập thực hành nâng cao

### Bài tập A — khởi tạo một cache entry

Cho 20 threads yêu cầu cùng một key absent. Viết hai phiên bản:

- `putIfAbsent(k, expensiveFactory())` và đo số lần factory chạy.
- `computeIfAbsent(k, k2 -> cheapFactory())` và đo số lần function chạy khi mapping được giữ ổn định.

Giải thích vì sao factory có side effect external là bài toán khác với initialization một object trong map. Hãy dùng `CountDownLatch`/`Future.get(timeout)` để phối hợp test, không dựa vào sleep.

### Bài tập B — state transition

Tạo `record JobState(long generation, String status)`. Nhiều threads cố chuyển `NEW→CLAIMED` bằng `replace(k, expected, next)`. Chứng minh chỉ một thread có thể thắng cho cùng expected state khi không có phép đưa state quay lại expected. Sau đó thử mô phỏng ABA và bổ sung generation.

### Bài tập C — word frequency

Tạo frequency map từ một tập từ, các threads chia input, dùng `computeIfAbsent(word, k -> new LongAdder()).increment()`. Chờ tất cả Futures rồi xác minh tổng số từ. Thử đọc `sum()` trong khi writers còn chạy và giải thích vì sao snapshot chưa chắc linearizable.

### Bài tập D — cleanup có điều kiện

Dùng `computeIfPresent` để xóa entry nếu record hết hạn. Test một thread cập nhật bản ghi mới đúng lúc thread khác muốn cleanup, đảm bảo bản ghi mới không bị xóa do `get+remove` stale check.

### Bài tập E — nhiều khóa

Mô phỏng chuyển điểm A→B và một reader đọc tổng A+B liên tục. Chứng minh hai `compute` tách biệt không cung cấp atomic snapshot hai khóa. Thiết kế lại bằng một immutable aggregate state hoặc lock chung, rồi test invariant.

## 32. Tài liệu tham khảo chính thức

- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): đặc tả atomic `computeIfAbsent`, `computeIfPresent`, `compute`, `merge`, bulk ops, null, mappingCount, weakly consistent views và `LongAdder` frequency map.
- [Java SE 17 — ConcurrentMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentMap.html): semantics của `putIfAbsent`, conditional remove/replace và interface contract.
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): bản đồ key/value, equality và các default methods.
- [Java SE 17 — LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): increment/sum và giới hạn snapshot khi concurrent updates.
- [Java SE 17 — AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic counter và CAS.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordination tạo interleaving trong test và memory consistency.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/shutdown và lifecycle.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion, exception và memory effects khi `get`.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before, data races và memory ordering.

**Kết luận:** `ConcurrentHashMap` không làm `get → kiểm tra → put` tự nguyên tử. Hãy dùng **compound operation đúng theo invariant và theo khóa**: `putIfAbsent` để insert-if-missing, `replace/remove` có expected value cho compare-and-update, `compute*` để remap theo current, và `merge` để cộng/aggregate. Hàm remapping phải ngắn, không recursive update và không đặt side effect không idempotent. Nếu state phụ thuộc nhiều khóa, mutable referents hoặc external systems, phải thiết kế đồng bộ/transaction/lifecycle bổ sung — thread safety của map **không thay thế** correctness của toàn bộ workflow.