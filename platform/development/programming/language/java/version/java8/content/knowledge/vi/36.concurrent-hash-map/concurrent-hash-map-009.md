# ConcurrentHashMap: thứ tự, null và hợp đồng của Map trong Java 8+

## 1. Vì sao cần hiểu hợp đồng, không chỉ cách dùng put/get?

Một dịch vụ Java lưu job, cache, số lượt truy cập hoặc trạng thái dùng chung trên **ConcurrentHashMap<K,V>** để nhiều thread có thể cập nhật cùng cấu trúc. Dù đây là một Map, không thể suy mọi thuộc tính từ tên Map hoặc từ kết quả in console.

Ba câu hỏi cốt lõi:

1. **Thứ tự:** keySet/entrySet có theo thứ tự chèn, thứ tự key, thứ tự cập nhật hay không?
2. **null:** key hoặc value có được null không? Khi get trả null, nó có nghĩa gì?
3. **Hợp đồng Map:** equals, hashCode, views, các update và iterator bảo đảm điều gì, nhất là khi có writer đồng thời?

**Trả lời ngắn:** ConcurrentHashMap **không bảo đảm thứ tự duyệt**; **không nhận null key/value**; Map.equals/hashCode xét mapping thay vì thứ tự; các thao tác như **putIfAbsent, compute và merge** có hỗ trợ atomic per-key; iterator **weakly consistent**, không phải một snapshot giao dịch.

**ConcurrentHashMap là API hiện hành** trong java.util.concurrent, đã tồn tại trước Java 8. Các method computeIfAbsent, compute và merge từ Java 8 vẫn còn áp dụng, không phải kỹ thuật legacy.

## 2. Map không phải List, một key chỉ có tối đa một mapping

~~~java
ConcurrentHashMap<String, Integer> scores =
        new ConcurrentHashMap<>();

scores.put("alice", 10);
scores.put("alice", 12);

System.out.println(scores.get("alice")); // 12
~~~

Lần put thứ hai **thay giá trị** của key "alice", không tạo entry thứ hai.

Map<K,V> mô tả quan hệ key→value chứ không có "phần tử thứ 0" như List. Một số implementation có quy tắc thứ tự (LinkedHashMap hoặc sorted map), nhưng **bản thân interface Map không hứa insertion order cho mọi implementation**.

~~~java
Map<String, Integer> a = new ConcurrentHashMap<>();
Map<String, Integer> b = new LinkedHashMap<>();
~~~

Cùng được khai báo kiểu Map, nhưng runtime của a và b mang các quy tắc khác nhau về null, thread-safety và thứ tự. Phân biệt **kiểu interface** với **hợp đồng implementation thực tế**.

## 3. ConcurrentHashMap không bảo đảm iteration order

~~~java
ConcurrentHashMap<String, Integer> map =
        new ConcurrentHashMap<>();
map.put("third", 3);
map.put("first", 1);
map.put("second", 2);
~~~

Không có cam kết rằng map.keySet() sẽ duyệt **third, first, second** như thứ tự gọi put. Nó cũng không cam kết duyệt **first, second, third** theo alphabet, hoặc theo hashCode, bucket hay thứ tự thread hoàn thành.

**Không viết assert kiểu này:**

~~~java
// Test không hợp lệ theo contract:
// assertEquals("[third, first, second]", map.keySet().toString());
~~~

Một lần chạy tình cờ hiển thị thứ tự như mong muốn không phải bằng chứng về bảo đảm. Quy mô map, hash distribution, concurrent updates và các chi tiết implementation có thể khiến thứ tự thay đổi.

**Nếu thứ tự là yêu cầu nghiệp vụ, phải mô hình hóa nó.** Sort phục vụ hiển thị; một event sequence phục vụ thứ tự sự kiện. Không dùng thứ tự CHM keySet làm lịch sử giao dịch.

## 4. So sánh các implementation Map còn dùng hiện nay

| Loại Map | Update đồng thời an toàn không? | Thứ tự duyệt | null key/value |
| --- | --- | --- | --- |
| **HashMap** | Không tự thread-safe | Không bảo đảm | Cho phép null key và null values |
| **LinkedHashMap** | Không tự thread-safe | Insertion-order mặc định; có tùy chọn access-order | Cho phép null |
| **TreeMap** | Không tự thread-safe | Sorted theo key/comparator | null key tùy comparator; null values được hỗ trợ |
| **ConcurrentHashMap** | Có, theo contract concurrent map | Không bảo đảm | Cấm null key và null value |
| **ConcurrentSkipListMap** | Có | Sorted theo key/comparator | Cấm null key và null value |

**ConcurrentSkipListMap** là lựa chọn khi vừa cần concurrent map vừa cần key order. Nó không có nghĩa duyệt theo thứ tự chèn.

**LinkedHashMap** giữ thứ tự chèn nhưng không tự an toàn cho nhiều writer. Nếu buộc chia sẻ một map có thứ tự chèn, cần cơ chế đồng bộ phù hợp; dùng Collections.synchronizedMap(...) thì phải chú ý cả cách đồng bộ khi duyệt.

**Comparator nhất quán với equals** là điều đáng quan tâm khi chọn sorted map. Nếu comparator đánh giá hai key bằng 0 nhưng equals của key khác, sorted map có thể coi hai key là cùng một mapping, khiến Map contract khó hiểu.

## 5. Muốn thứ tự khi xuất báo cáo thì tự sort

~~~java
ConcurrentHashMap<String, Integer> map =
        new ConcurrentHashMap<>();
map.put("third", 3);
map.put("first", 1);
map.put("second", 2);

List<String> sortedKeys = map.keySet().stream()
        .sorted()
        .collect(Collectors.toList());

System.out.println(sortedKeys);
// [first, second, third]
~~~

Đây là snippet bên trong method có import java.util.*, java.util.concurrent.* và java.util.stream.Collectors.

**Stream.sorted() sắp kết quả đã đọc, không thay đổi thứ tự nội bộ của CHM.**

Với mục đích tạo Map sorted copy:

~~~java
Map<String, Integer> orderedCopy = new TreeMap<>(map);
~~~

Nhưng một vòng duyệt/copy khi writer vẫn cập nhật không tạo **atomic snapshot**. Việc sắp key và việc bảo đảm tất cả value cùng thuộc một phiên bản dữ liệu là **hai bài toán khác nhau**.

Nếu cần sorted concurrent map **duy trì** thứ tự key, hãy cân nhắc ConcurrentSkipListMap. Nếu cần insertion-order của sự kiện, cấu trúc sorted theo key không thay thế event log hoặc sequence ID.

## 6. null key và null value đều không được phép

**ConcurrentHashMap không hỗ trợ null ở cả hai vị trí**:

~~~java
ConcurrentHashMap<String, Integer> map =
        new ConcurrentHashMap<>();
map.put("exists", 1);

// Các lệnh sau ném NullPointerException:
// map.put(null, 2);
// map.put("missing", null);
// map.get(null);
// map.containsValue(null);
~~~

Không phải chỉ put mới bị hạn chế; API tra cứu null key hoặc containsValue(null) cũng có quy tắc riêng. Các lệnh trên đã được kiểm thử trong chương trình runnable.

**Vì sao quan trọng?** Khi map không thể lưu value null, lời gọi **get(k) trả null** có nghĩa **không thấy mapping của k** tại lần tra cứu, không phải "key này đang chứa value null".

HashMap cho phép null key/value, vì thế với HashMap, get trả null có thể do key vắng mặt hoặc do value null; có thể cần containsKey để phân biệt khi không có update đồng thời.

**Không áp dụng quy tắc null của ConcurrentHashMap cho toàn bộ Map interface.** Mỗi implementation có contract về null và optional operations.

## 7. get(k)==null là thiếu mapping tại lần đọc, không phải kết luận vĩnh viễn

~~~java
ConcurrentHashMap<String, String> registry =
        new ConcurrentHashMap<>();

System.out.println(registry.get("unknown") == null);
// true
~~~

Nếu nhiều thread đang thay đổi map, một thread khác có thể thêm/xóa key **ngay sau khi get trả về**. Không viết code dựa vào kết luận rằng key sẽ vắng mặt ở mọi lệnh tiếp theo.

**Sai do check-then-act:**

~~~java
if (registry.get("job") == null) {
    registry.put("job", "READY");
}
~~~

Hai thread có thể cùng quan sát vắng mặt rồi cùng put.

**Cách phù hợp cho insert-if-absent:**

~~~java
String previous = registry.putIfAbsent("job", "READY");
~~~

putIfAbsent thực hiện thao tác theo contract atomic trên key đó. Nếu chưa có mapping, nó có thể chèn "READY" và trả null. Nếu có value trước, nó trả value cũ.

**getOrDefault(k, defaultValue)** trả fallback khi k chưa có mapping nhưng **không insert fallback** vào map:

~~~java
String result = registry.getOrDefault("unknown", "MISSING");
~~~

## 8. computeIfAbsent trả null nhưng không lưu null

Với Java 8+:

~~~java
ConcurrentHashMap<String, Integer> map =
        new ConcurrentHashMap<>();

Integer value = map.computeIfAbsent("optional", k -> null);

System.out.println(value); // null
System.out.println(map.containsKey("optional")); // false
~~~

Đây là **giá trị trả về của function** mang nghĩa "không có kết quả tạo value", không phải null value trong ConcurrentHashMap.

Nếu mappingFunction trả một value khác null, CHM có thể gắn value vào key vắng mặt theo semantics nguyên tử của method.

**compute** có ngữ nghĩa khác: function có thể nhận oldValue == null khi key vắng mặt; nếu nó trả null, mapping bị xóa hoặc giữ vắng mặt:

~~~java
map.put("optional", 4);
map.compute("optional", (key, old) -> null);

// Key "optional" không còn mapping.
~~~

**merge** yêu cầu tham số value đầu vào nonnull; khi key đã có value, function kết hợp hai value được gọi và nếu nó trả null thì mapping bị xóa:

~~~java
map.put("counter", 2);
map.merge("counter", 3, Integer::sum); // 5
map.merge("counter", 1, (oldValue, incoming) -> null);
// Key counter bị xóa.
~~~

**Không gọi put(key,null) hay merge(key,null,fn) để xóa key.** Nếu muốn xóa, dùng remove hoặc kết quả remapping theo đúng contract.

## 9. Bảng nhanh về hợp đồng null của CHM

| Cách gọi | Kết quả |
| --- | --- |
| put(null, value) | NullPointerException |
| put(key, null) | NullPointerException |
| get(null) | NullPointerException |
| containsValue(null) | NullPointerException |
| get(key không tồn tại) | null |
| putIfAbsent(key, nonnullValue) | Thêm nguyên tử khi vắng mặt |
| computeIfAbsent(key, fn trả null) | Không tạo mapping |
| computeIfPresent(key, fn trả null) | Xóa mapping đã có |
| compute(key, fn trả null) | Xóa hoặc giữ vắng mặt |
| merge(key, nonnullValue, fn trả null) | Xóa mapping nếu key đã có value |
| getOrDefault(key, fallback) | Trả fallback khi vắng, không ghi |
| keySet().add(key) | UnsupportedOperationException |
| keySet(mappedValue).add(key) | Thêm key với value được cho |

**Lưu ý merge:** nếu key **vắng mặt**, merge không gọi remapping function và sẽ gắn value đầu vào. Vì vậy không được nói "merge có callback trả null luôn xóa key" mà thiếu điều kiện key đã có.

**Function compute/merge nên ngắn và không sửa lại chính map** từ bên trong callback, theo hướng dẫn của Oracle API. Một số update khác có thể bị chặn khi tính toán cho key.

## 10. Khi nghiệp vụ có trạng thái thiếu, dùng một value nonnull rõ nghĩa

Các trạng thái khác nhau như PENDING, RUNNING, DONE, FAILED không nên bị nhồi vào null:

~~~java
enum Status { PENDING, RUNNING, DONE, FAILED }

ConcurrentHashMap<String, Status> jobs =
        new ConcurrentHashMap<>();
jobs.put("job-7", Status.PENDING);
~~~

Đây là snippet minh họa có enum ở scope class.

**Key vắng mặt** có thể nghĩa là job không tồn tại. **Status.PENDING** nghĩa job tồn tại nhưng chưa chạy. **Status.FAILED** nghĩa job đã thất bại. Cả ba khác nhau về business semantics.

Có thể dùng một value object mang status và payload; nếu muốn biểu diễn thiếu giá trị tùy ngữ cảnh, Optional<T> cũng là kiểu Java hiện hành, nhưng không mặc nhiên cần lưu Optional làm value trong mọi map.

Không dùng sentinel như -1 hoặc chuỗi "UNKNOWN" nếu chúng có thể trùng dữ liệu thật, trừ khi API đã công bố quy tắc phân biệt.

## 11. Map.equals, Map.hashCode độc lập với thứ tự duyệt

~~~java
ConcurrentHashMap<String, Integer> concurrent =
        new ConcurrentHashMap<>();
concurrent.put("third", 3);
concurrent.put("first", 1);
concurrent.put("second", 2);

LinkedHashMap<String, Integer> insertion =
        new LinkedHashMap<>();
insertion.put("third", 3);
insertion.put("first", 1);
insertion.put("second", 2);

System.out.println(concurrent.equals(insertion));
// true
~~~

**Map.equals** dựa trên mapping key/value, không dựa trên thứ tự iterator. HashCode của Map theo contract được tính từ các entry, không theo vị trí.

Trong khi có writer, một lần so sánh map tổng thể không phải atomic transaction snapshot của mọi key. Nếu cần chứng minh hai registry đang nhất quán ở cùng một thời điểm, phải thiết kế đồng bộ hoặc snapshot ở tầng cao hơn.

**Key phải có equals/hashCode ổn định.** Khi object key mutable thay đổi trường tham gia hashCode sau khi chèn, lookup có thể không còn tìm đúng mapping. Ưu tiên immutable keys như String hoặc ID có invariant rõ.

## 12. keySet, values, entrySet là live views

Các collection views:

- **keySet()**: các key trong map.
- **values()**: các value trong map.
- **entrySet()**: các mapping đang có.

Đây là **views được backed by map**, không phải bản sao không thay đổi.

~~~java
ConcurrentHashMap<String, Integer> map =
        new ConcurrentHashMap<>();
map.put("a", 1);
map.put("b", 2);

Set<String> keys = map.keySet();
keys.remove("a");
System.out.println(map.containsKey("a")); // false
~~~

keySet mặc định hỗ trợ remove, removeAll, iterator.remove và clear ở các điều kiện được mô tả, nhưng **không hỗ trợ add/addAll** vì không có value dùng cho key mới.

~~~java
// Ném UnsupportedOperationException:
// map.keySet().add("new");
~~~

Khi muốn thêm key gắn với **value cố định**, dùng:

~~~java
ConcurrentHashMap<String, Boolean> flags =
        new ConcurrentHashMap<>();
Set<String> enabled = flags.keySet(Boolean.TRUE);
enabled.add("feature-A");
// flags.get("feature-A") == true.
~~~

Ngoài ra **ConcurrentHashMap.newKeySet()** tạo một concurrent Set chỉ quan tâm đến keys. Các method views và iterators vẫn cần được sử dụng theo contract riêng, không tự suy là bản copy bất biến.
## 13. Weakly consistent iteration: không CME nhưng cũng không snapshot

Iterator, Spliterator và Enumeration của ConcurrentHashMap có tính chất **weakly consistent**.

- Chúng không ném **ConcurrentModificationException** chỉ vì map bị cập nhật đồng thời.
- Một lượt duyệt có thể phản ánh entry ở thời điểm nào đó trong/sau khi iterator được tạo.
- Không bảo đảm thấy mọi key được thêm trong lúc duyệt.
- Không bảo đảm một tập entry tồn tại cùng lúc tại một thời điểm logic.
- **Một instance iterator không được thiết kế để hai thread cùng next đồng thời**; map an toàn với các iterator riêng, không có nghĩa bản thân một iterator được share tự do.

~~~java
Iterator<String> iterator = map.keySet().iterator();

map.put("new", 100);

while (iterator.hasNext()) {
    String key = iterator.next();
    // Không kết luận iterator chắc chắn có hoặc không có "new".
}
~~~

Đoạn trên là minh họa trong method có biến map.

Khác với HashMap có fail-fast theo best effort khi structural change, CHM duyệt yếu nhất quán để làm việc hữu ích giữa các update. **Không có CME không chứng minh snapshot đúng**.

## 14. Các phép trạng thái toàn map không thay thế đồng bộ

**size(), isEmpty(), containsValue()** phản ánh một quan sát tổng hợp; nếu thread khác đang update thì kết quả có thể thay đổi rất nhanh, không nên dùng làm điều kiện đồng bộ toàn hệ thống.

**mappingCount()** trả long và được Oracle mô tả là **ước lượng** khi có concurrent updates. Nó hữu ích nếu map đủ lớn để vượt phạm vi int, nhưng vẫn không có nghĩa đã chụp một snapshot nguyên tử.

~~~java
long numberObserved = map.mappingCount();
~~~

**Đừng viết if(map.isEmpty()) để khẳng định tất cả worker đã hoàn tất.** Worker có thể chưa ghi mapping hoặc có thể thêm ngay sau lần check.

Muốn chờ task, dùng **Future.get(), CountDownLatch, Phaser** hoặc completion protocol có nghĩa nghiệp vụ rõ. Muốn số liệu chính xác tại một thời điểm cho đối soát, cần cơ chế snapshot/quiescence/transaction phù hợp.

## 15. Atomic per-key nhưng không phải giao dịch nhiều key

Các thao tác thích hợp cho concurrency:

~~~java
map.putIfAbsent(key, value);
map.replace(key, expectedOld, newValue);
map.remove(key, expectedValue);
map.computeIfAbsent(key, mappingFunction);
map.compute(key, remappingFunction);
map.merge(key, delta, combiningFunction);
~~~

Đây là các lời gọi có biến giả định, không phải một chương trình độc lập.

**Cách tăng counter dễ mất cập nhật:**

~~~java
Integer old = map.get("hits");
map.put("hits", old == null ? 1 : old + 1);
~~~

Hai writer có thể cùng đọc old rồi ghi cùng số mới. Dùng:

~~~java
map.merge("hits", 1, Integer::sum);
~~~

**merge** cập nhật mapping cho một key với ngữ nghĩa nguyên tử của CHM. Tuy nhiên việc trừ account A rồi cộng account B bằng hai lần compute riêng **không** tạo transaction atomic giữa hai key. Các invariant nhiều key cần cơ chế riêng.

Các callback compute/merge nên ngắn, đơn giản và không tự cập nhật lại chính map trong lúc callback chạy; có thể phát sinh contention hoặc illegal recursive update nếu dùng sai.

## 16. Function trả null, function throw, và update chỉ một key

| API | Mô hình | Function trả null |
| --- | --- | --- |
| computeIfAbsent | Khởi tạo lazy khi không có mapping | Không chèn |
| computeIfPresent | Chỉ chạy khi có value | Xóa |
| compute | Tính mapping từ old value; old có thể null khi thiếu | Xóa/giữ thiếu |
| merge | Kết hợp value cũ và value mới nếu có mapping | Xóa nếu callback chạy và trả null |
| replaceAll | Biến đổi các value được thấy | Không thể ghi value null vào CHM |

Trong CHM, các method compute/merge được thiết kế để phối hợp update phù hợp **trên key của invocation**. **Không đồng nghĩa toàn bộ vòng forEach hoặc nhiều lần compute trên nhiều key atomic với nhau.**

Khi function ném unchecked exception, exception được chuyển cho caller; mapping không nhận một value tính toán mới như thể function thành công.

Không biến callback trong compute thành thao tác gửi email hoặc thanh toán không idempotent mà không có thiết kế riêng. Một operation map atomic không bảo đảm side effect ở hệ thống ngoài diễn ra đúng một lần nếu tầng gọi retry.

## 17. Thread-safety của map không tự làm value thread-safe

~~~java
ConcurrentHashMap<String, List<String>> groups =
        new ConcurrentHashMap<>();

groups.put("team", new ArrayList<String>());
~~~

Nhiều thread cùng gọi groups.get("team").add(...) vẫn có thể race vì ArrayList không thread-safe.

Tùy yêu cầu:

- Dùng immutable values rồi replace/compute một mapping mới.
- Dùng ConcurrentLinkedQueue nếu value cần một queue concurrent.
- Dùng LongAdder nếu value là counter nhiều writer, hiểu sum() không là atomic snapshot khi update.
- Đồng bộ riêng cho invariant của object chứa trong value nếu cần.

CHM cung cấp visibility/happens-before cho cập nhật và lần đọc nonnull quan sát mapping tương ứng, **nhưng không biến nhiều lệnh trên value mutable thành một giao dịch**.

## 18. Chương trình Java 17: null, thứ tự và Map contract

Tạo tệp **ConcurrentMapContractDemo.java**:

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;

public class ConcurrentMapContractDemo {
    static String thrownBy(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        map.put("third", 3);
        map.put("first", 1);
        map.put("second", 2);

        System.out.println("sorted keys: " +
                map.keySet().stream().sorted().collect(Collectors.toList()));
        LinkedHashMap<String, Integer> insertion = new LinkedHashMap<>();
        insertion.put("third", 3);
        insertion.put("first", 1);
        insertion.put("second", 2);
        System.out.println("linked keys: " + insertion.keySet());
        System.out.println("equal mappings: " + map.equals(insertion));
        System.out.println("equal hash codes: " +
                (map.hashCode() == insertion.hashCode()));
        System.out.println("missing get null: " + (map.get("absent") == null));
        System.out.println("missing containsKey false: " +
                !map.containsKey("absent"));

        System.out.println("put null key: " +
                thrownBy(() -> map.put(null, 1)));
        System.out.println("put null value: " +
                thrownBy(() -> map.put("bad", null)));
        System.out.println("get null key: " +
                thrownBy(() -> map.get(null)));
        System.out.println("contains null value: " +
                thrownBy(() -> map.containsValue(null)));

        System.out.println("putIfAbsent existing: " +
                map.putIfAbsent("first", 999));
        System.out.println("first unchanged: " + map.get("first"));
        System.out.println("computeIfAbsent null: " +
                map.computeIfAbsent("fourth", key -> null));
        System.out.println("null mapping absent: " +
                !map.containsKey("fourth"));
        System.out.println("computeIfAbsent value: " +
                map.computeIfAbsent("fourth", key -> 4));
        System.out.println("compute null removes: " +
                map.compute("fourth", (key, old) -> null));
        System.out.println("fourth removed: " + !map.containsKey("fourth"));
        System.out.println("merge result: " +
                map.merge("first", 5, Integer::sum));
        System.out.println("merge null removes: " +
                map.merge("second", 1, (old, value) -> null));
        System.out.println("second removed: " +
                !map.containsKey("second"));

        Set<String> liveKeys = map.keySet();
        System.out.println("keySet.add rejected: " +
                thrownBy(() -> liveKeys.add("x")));
        liveKeys.remove("third");
        System.out.println("keySet.remove changed map: " +
                !map.containsKey("third"));

        Iterator<String> weak = map.keySet().iterator();
        map.put("added", 7);
        while (weak.hasNext()) {
            weak.next();
        }
        System.out.println("weak iterator finished without CME: true");

        ConcurrentSkipListMap<String, Integer> sorted =
                new ConcurrentSkipListMap<>(map);
        System.out.println("skip list keys: " + sorted.keySet());
        System.out.println("skip list null key: " +
                thrownBy(() -> sorted.put(null, 1)));

        final int workers = 4;
        final int operationsPerWorker = 2000;
        ConcurrentHashMap<String, Integer> tally = new ConcurrentHashMap<>();
        ExecutorService executor = Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    try {
                        start.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(ex);
                    }
                    for (int j = 0; j < operationsPerWorker; j++) {
                        tally.merge("hits", 1, Integer::sum);
                    }
                }));
            }
            start.countDown();
            for (Future<?> f : futures) f.get();
        } finally {
            executor.shutdown();
        }
        System.out.println("atomic hits: " + tally.get("hits"));
        System.out.println("mapping count: " + tally.mappingCount());
    }
}
~~~

Lệnh chạy với JDK 17+:

~~~bash
javac ConcurrentMapContractDemo.java
java ConcurrentMapContractDemo
~~~

**Stdout đã kiểm chứng thực tế:**

~~~text
sorted keys: [first, second, third]
linked keys: [third, first, second]
equal mappings: true
equal hash codes: true
missing get null: true
missing containsKey false: true
put null key: NullPointerException
put null value: NullPointerException
get null key: NullPointerException
contains null value: NullPointerException
putIfAbsent existing: 1
first unchanged: 1
computeIfAbsent null: null
null mapping absent: true
computeIfAbsent value: 4
compute null removes: null
fourth removed: true
merge result: 6
merge null removes: null
second removed: true
keySet.add rejected: UnsupportedOperationException
keySet.remove changed map: true
weak iterator finished without CME: true
skip list keys: [added, first]
skip list null key: NullPointerException
atomic hits: 8000
mapping count: 1
~~~

**Giải thích:** sorted keys có được nhờ sorted(), không phải do CHM. LinkedHashMap duy trì thứ tự chèn nhưng vẫn Map.equals với CHM khi mapping bằng nhau. Các phép null ném NPE. computeIfAbsent callback null không chèn; compute và merge callback null xóa mapping đã có. keySet view hỗ trợ remove nhưng không add mặc định. Weak iterator không báo CME nhưng không được kiểm thử theo số lượng key nhìn thấy. Counter merge tổng 8000 vì 4 worker × 2000 lần, và main đã đợi các Future hoàn tất trước khi đọc.

## 19. Java 8 runnable: LongAdder và keySet(mappedValue)

Tạo tệp **ConcurrentMapJava8Demo.java**:

~~~java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.LongAdder;

public class ConcurrentMapJava8Demo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, LongAdder> frequencies =
                new ConcurrentHashMap<>();
        final int workers = 4;
        final int repeats = 3000;
        ExecutorService executor = Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<Future<?>>();
        try {
            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    try {
                        start.await();
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                        throw new RuntimeException(exception);
                    }
                    for (int n = 0; n < repeats; n++) {
                        frequencies.computeIfAbsent("click",
                                key -> new LongAdder()).increment();
                    }
                }));
            }
            start.countDown();
            for (Future<?> task : futures) {
                task.get();
            }
        } finally {
            executor.shutdown();
        }
        System.out.println("click count: " +
                frequencies.get("click").sum());
        System.out.println("missing key get null: " +
                (frequencies.get("missing") == null));
        System.out.println("contains click: " +
                frequencies.containsKey("click"));

        ConcurrentHashMap<String, Boolean> flags = new ConcurrentHashMap<>();
        Set<String> active = flags.keySet(Boolean.TRUE);
        active.add("feature-A");
        System.out.println("mapped key set: " + flags.get("feature-A"));
        active.remove("feature-A");
        System.out.println("removed from map: " +
                !flags.containsKey("feature-A"));

        Map<String, String> snapshot = new TreeMap<String, String>();
        snapshot.put("z", "end");
        snapshot.put("a", "start");
        System.out.println("sorted snapshot keys: " + snapshot.keySet());
    }
}
~~~

Lệnh chạy (biên dịch kiểm thử với mục tiêu Java 8):

~~~bash
javac ConcurrentMapJava8Demo.java
java ConcurrentMapJava8Demo
~~~

**Stdout:**

~~~text
click count: 12000
missing key get null: true
contains click: true
mapped key set: true
removed from map: true
sorted snapshot keys: [a, z]
~~~

Chương trình dùng 4 worker × 3000 lần LongAdder.increment. **LongAdder.sum() không phải snapshot nguyên tử trong lúc update**; output xác định ở đây vì main đợi Future.get() của tất cả task. keySet(Boolean.TRUE) cho phép add và ghi TRUE vào map, khác với keySet() mặc định.

## 20. Snapshot và export: ordering khác consistency

~~~java
Map<String, Integer> sortedCopy = new TreeMap<>(map);
sortedCopy.forEach((key, value) ->
        System.out.println(key + "=" + value));
~~~

Đây là đoạn minh họa trong method, map là Map nguồn.

**Điều sortedCopy giải quyết:** thứ tự key của dữ liệu đã copy. **Điều nó không tự giải quyết:** nhiều entry được copy có phải một trạng thái giao dịch ở cùng một thời điểm không, nếu writer đang tiếp tục thay đổi map.

**Map.copyOf(map)** (Java 10+) tạo bản sao unmodifiable theo contract, nhưng không tự dừng writer ở source, không hứa iteration order nhất định và không nhận null key/value.

Khi cần trạng thái kiểm toán ở một mốc, ứng dụng phải có quiescence, versioned immutable state, transaction database hoặc protocol đồng bộ cụ thể. Đừng gọi copy/sort rồi gọi kết quả là atomic snapshot.

## 21. Bulk operations và thứ tự xử lý

CHM cung cấp các bulk operations như **forEach, search và reduce**, kể cả một số overload nhận parallelismThreshold. Tài liệu Oracle nhấn mạnh việc chúng có thể hữu ích với map concurrent, nhưng **không nên phụ thuộc thứ tự phần tử**.

- Callback của parallel search/reduce không nên dựa trên thứ tự duyệt.
- Phép kết hợp của reduce nên **associative và commutative** khi muốn kết quả không phụ thuộc cách chia/chạy song song.
- Search có thể trả một kết quả nonnull tìm thấy, **không phải "phần tử đầu tiên theo key"**.
- Trong một số function, trả null có nghĩa là không có kết quả/không đưa vào reduce, không có nghĩa map lưu value null.
- Song song không bảo đảm nhanh hơn với map nhỏ, vì có overhead.
- Một kết quả tổng hợp khi writer đang update phản ánh các quan sát per-element, thường không phải snapshot atomic toàn map.

Nếu muốn tìm top N theo một tiêu chí deterministic, nên định nghĩa comparator rõ và xử lý tập dữ liệu được quan sát theo chính sách snapshot thích hợp.

## 22. Checklist để tránh lỗi production

**Thứ tự:** bạn có cần insertion-order, sorted key hay chỉ stable display? CHM không tự cung cấp insertion/sorted order. Sort result hoặc dùng ConcurrentSkipListMap/thiết kế thứ tự phù hợp.

**Null:** có null input không? Callback compute/merge trả null có đang vô tình xóa mapping hoặc không chèn? Có value nonnull diễn đạt đủ trạng thái nghiệp vụ chưa?

**Map contract:** key equals/hashCode ổn định chưa? Có so hai Map theo mapping thay vì thứ tự không? Có dùng keySet, values, entrySet như live views và hiểu tác dụng của remove không?

**Concurrency:** còn đoạn get rồi put dễ mất cập nhật không? Dùng compute/merge atomic per-key có đúng ngữ nghĩa không? Có nhầm size/isEmpty là tín hiệu worker đã xong? Có thể chờ Future/latch thay cho sleep không?

**Snapshot:** kết quả copy/sort có được hiểu đúng là dữ liệu quan sát được, không phải transaction? Nếu cần nhất quán nhiều key, đã có cơ chế riêng chưa?

**Value:** nếu value mutable, nó đã an toàn khi nhiều thread cùng mutate chưa? Có cần immutable key/value hoặc một concurrent collection bên trong không?

## 23. Bài tập có đáp án

**1.** map.put("x",null) với ConcurrentHashMap? — **NullPointerException**.

**2.** map.get("x")==null có phải x→null? — **Không**. Lần đọc không thấy mapping, nhưng writer có thể cập nhật ngay sau.

**3.** put("c"),put("a"),put("b") có hứa keySet là c,a,b? — **Không**; phải định nghĩa ordering riêng.

**4.** ConcurrentHashMap và LinkedHashMap cùng mapping nhưng hiển thị khác thứ tự có equals? — **Có**, khi mapping bằng nhau và ổn định.

**5.** computeIfAbsent callback trả null? — **Không chèn mapping**.

**6.** compute callback trả null ở key có mapping? — **Xóa mapping**.

**7.** merge callback trả null khi key đã có? — **Xóa mapping**; khi vắng, merge dùng value đầu vào.

**8.** keySet().add(key) có được? — **Không**, UnsupportedOperationException; keySet(mappedValue) là một view khác.

**9.** Iterator weakly consistent có thấy mọi key mới không? — **Không có cam kết**; nó không phải snapshot.

**10.** map.size()==0 có đủ chứng minh mọi worker xong? — **Không**, phải có completion protocol.

**11.** Value ArrayList có tự thread-safe vì nằm trong CHM không? — **Không**.

**12.** new TreeMap<>(chm) tạo atomic snapshot khi writer còn chạy? — **Không**, chỉ có sorted copy dữ liệu được quan sát.

**13.** Hai update atomic per-key là transaction hai key? — **Không**, invariant nhiều key cần đồng bộ riêng.

**14.** Vì sao counter bằng 8000? — 4 worker × 2000 merge nguyên tử, rồi main đợi tất cả Future.get() xong mới đọc.

## 24. Tổng kết và tài liệu Oracle hiện hành

**10 nguyên tắc:**

1. **ConcurrentHashMap không bảo đảm iteration order** theo chèn, key hoặc hash.
2. **Không cho null key/value**; get trả null khi lần đọc không nhìn thấy mapping.
3. **Map.equals/hashCode độc lập thứ tự duyệt**; key cần hashCode/equals ổn định.
4. **computeIfAbsent trả null không ghi mapping**, còn compute/merge remapping trả null có thể xóa.
5. **putIfAbsent/compute/merge nguyên tử ở mức key**, không phải transaction nhiều key.
6. **keySet/values/entrySet là backed views**, không phải bản copy; keySet mặc định remove được, add không được.
7. **Weakly consistent iterators** không ném CME vì concurrent update nhưng không cung cấp atomic snapshot.
8. **size/isEmpty/mappingCount** không thay thế coordination giữa workers.
9. **Sort kết quả** là order của dữ liệu đã thấy, không bảo đảm consistency của toàn map.
10. **Value mutable cần tự được bảo vệ**; thread-safe map không giải quyết mọi race bên trong value.

**Tài liệu chính thức Java SE 25 đang được hỗ trợ:**

- ConcurrentHashMap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- ConcurrentMap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentMap.html
- Map: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html
- HashMap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html
- LinkedHashMap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html
- ConcurrentSkipListMap: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html
- LongAdder: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html

**Phiên bản:** CHM đã có từ trước Java 8, nhưng mọi method được học ở bài đều vẫn còn áp dụng. Ví dụ chính được chạy trên Java 17; ví dụ thứ hai đã biên dịch với target Java 8. Map.copyOf được nêu có đánh dấu Java 10+, không nhầm với Java 8.
