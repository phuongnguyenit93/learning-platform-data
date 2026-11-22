# Chọn Concurrent Collection theo read/write ratio và yêu cầu ordering trong Java

## 1. Tại sao một collection thread-safe chưa chắc là lựa chọn đúng?

Java có nhiều collection hỗ trợ truy cập đồng thời: `ConcurrentHashMap`, `ConcurrentSkipListMap`, `CopyOnWriteArrayList`, `ConcurrentLinkedQueue`, `LinkedBlockingQueue`, `ArrayBlockingQueue`, `PriorityBlockingQueue`, các synchronized wrappers và nhiều cấu trúc khác. Chúng đều giải quyết một phần của bài toán chia sẻ dữ liệu giữa thread, nhưng **không có collection nào tối ưu cho mọi mô hình đọc/ghi và mọi loại thứ tự**.

Chẳng hạn:
- Một danh sách cấu hình được đọc hàng triệu lần và cập nhật vài lần/ngày phù hợp với cơ chế snapshot, dù mỗi lần sửa tốn sao chép.
- Một map đếm sự kiện cập nhật liên tục không nên dùng copy-on-write list hoặc khóa toàn cục một cách máy móc.
- Một tác vụ xử lý theo **FIFO** không thể tùy tiện thay bằng priority queue: hợp đồng dequeue đã đổi.
- Một map phải duyệt key theo **thứ tự tăng dần** khác với map chỉ cần lookup nhanh theo key.
- Một queue dùng để điều tiết producer khi consumer chậm cần **capacity/backpressure**, điều mà queue không giới hạn không thể tự cung cấp.

**Ý chính:** quyết định chọn collection phải dựa trên **loại thao tác đọc/ghi, số thread cạnh tranh, chi phí phần tử, yêu cầu ordering, iterator consistency, boundedness/backpressure và invariant nghiệp vụ**, không chỉ tỉ lệ “80% đọc, 20% ghi”.

Bài này thuộc **Concurrent Collections** của **Java Advance - concurrency** và tập trung vào **“Chọn collection theo read/write ratio và ordering”** trong Java SE 17+. Không sử dụng framework hay API riêng của Spring vì phần concurrency của Spring có chương riêng.

Sau bài, bạn có thể:
1. Phân loại workload thành read-mostly, write-heavy, mixed, queue/stream và sorted/range query.
2. Phân biệt **insertion order**, **key/comparator order**, **FIFO**, **priority order**, **encounter order**, **fairness** và **thứ tự toàn cục dưới concurrency**.
3. Chọn giữa `ConcurrentHashMap` và `ConcurrentSkipListMap`; giữa `CopyOnWriteArrayList` và list dùng đồng bộ; giữa các queue nonblocking, blocking, bounded và priority.
4. Hiểu **snapshot, weakly consistent và fail-fast iteration**, tránh tin iterator của concurrent collection là một transaction/snapshot nhất quán tuyệt đối.
5. Nhận diện atomicity của **một phương thức**, nguy cơ **check-then-act**, và thao tác nhiều collection/key chưa atomic.
6. Thiết kế thử nghiệm benchmark theo read/write ratio thực và kiểm chứng correctness, thứ tự và backpressure.
7. Chạy các chương trình Java 17 đầy đủ, với đầu ra tất định khi đã kiểm soát concurrency.

## 2. Read/write ratio phải được đo theo loại thao tác

Một tỉ lệ như `read:write = 95:5` chỉ có ý nghĩa nếu xác định rõ mẫu số và loại đọc/ghi. Ví dụ:

- `get(key)` là một thao tác đọc ngắn, khác với `forEach` quét cả map có một triệu entries.
- `contains` hoặc `size` có chi phí và ý nghĩa khác với `take()` trên queue.
- `add(element)` vào copy-on-write list thường tạo một bản sao backing array, khác `put` vào ConcurrentHashMap.
- `computeIfAbsent` là một thao tác có khả năng cập nhật atomically một mapping, không đơn giản giống một lần read rồi một lần write.
- `removeIf` là thao tác bulk nhiều phần tử, không có nghĩa “một write” về chi phí.
- Đọc trên list theo chỉ số là khác với iterate snapshot; viết ở đầu list khác viết ở cuối list.

### Ba workload cơ bản

**Read-mostly:** nhiều `get/contains/iteration`, ít `put/add/remove`. Ví dụ danh sách listeners đăng ký lúc startup, cấu hình được publish thỉnh thoảng, metadata hiếm thay đổi.

**Mixed:** nhiều readers và writers hoạt động đồng thời, thường get/put/remove/compute. Ví dụ registry session, cache key-value, trạng thái user đang online.

**Write-heavy:** nhiều threads liên tục update, enqueue/dequeue hoặc increment. Ví dụ event counters, work queues, state transitions, logging intake.

**Không cố gắng đo read/write ratio khi chưa biết read là snapshot hay point lookup và write là append, replace hay remove**. Một workload 99% đọc nhưng mỗi lần đọc phải giữ lock và đi qua toàn bộ dữ liệu vẫn có contention/latency đáng kể.

### Tỉ lệ chưa đủ; cần thêm các biến

Một phiếu workload nên ghi ít nhất:

| Câu hỏi | Ví dụ | Vì sao quyết định collection |
| --- | --- | --- |
| Đọc theo cách nào? | `get(key)`, `get(index)`, `forEach` | Chi phí truy cập và iterator semantics khác nhau |
| Ghi theo cách nào? | `add`, `remove`, `merge`, `compute` | Copy, contention và atomicity khác nhau |
| Read/write ratio tại peak? | 99:1, 70:30, 20:80 | Bình quân ngày có thể che burst write |
| Số thread đồng thời? | 2, 16, 200 | Mức độ contention và lock behavior |
| Kích thước trung bình/cao nhất? | 100, 100.000, 10 triệu | Copy-on-write và memory footprint |
| Phần tử nặng bao nhiêu? | Ref nhỏ vs object graph lớn | Chi phí allocation, GC, cache |
| Có ordering gì? | FIFO, sorted key, priority, insertion | Loại collection và comparator |
| Cần snapshot nhất quán không? | Tất cả phần tử cùng một thời điểm | Weakly consistent iterator có thể không đủ |
| Có cần backpressure không? | Capacity 1.000, producers phải chờ | Bounded BlockingQueue |
| Có deadline/hủy không? | `poll(timeout)`, interruption | Chọn API blocking/timed phù hợp |
| Có invariant đa key? | Chuyển tiền giữa hai tài khoản | Atomic per-key không đủ |
| Thứ tự giữa nhiều producers? | Sequence toàn cục/ordering per-source | Queue FIFO không định nghĩa mọi race |

Không có “ngưỡng 90% reads” được JDK bảo đảm cho `CopyOnWriteArrayList`. Phải tính **write cost ~ kích thước collection** và **read pattern**, rồi đo trên workload thật.

## 3. Nhiều nghĩa của ordering: dễ chọn sai nhất

Từ “có thứ tự” trong Java concurrency có thể chỉ các hợp đồng hoàn toàn khác nhau.

### 3.1. Insertion order

Trong một collection tuần tự như `LinkedHashMap` hoặc `LinkedHashSet`, iteration có thể giữ thứ tự insertion (tùy mode và contract). Nhưng chúng **không tự thread-safe**. Dùng `LinkedHashMap` trực tiếp từ nhiều threads đọc/ghi là không an toàn.

Nếu cần **insertion-order snapshot**, có thể chụp dữ liệu trong một critical section hoặc publish một immutable snapshot sau mỗi batch cập nhật, tùy write frequency. Không nên thay `ConcurrentHashMap` bằng `LinkedHashMap` rồi cho nhiều writers chạy song song mà không đồng bộ.

### 3.2. Sorted order theo key/comparator

`ConcurrentSkipListMap<K,V>` duy trì key trong **thứ tự sắp xếp** theo natural ordering hoặc comparator, hỗ trợ `firstKey`, `lastKey`, `floorKey`, `ceilingKey`, `subMap`, `headMap`, `tailMap`.

**Sorted by key không phải insertion order.** Insert key 30 rồi 10 rồi 20, iterator theo khóa tăng dần vẫn đi 10, 20, 30. Nếu comparator không phân biệt được hai key (`compare(a,b)==0`), chúng có thể được xem là cùng một key theo ordering map; cần comparator nhất quán với domain identity.

`ConcurrentSkipListSet` cho yêu cầu tập hợp sorted keys tương tự. Đổi lại, ordered/range operations thường có chi phí và cấu trúc khác hash table; không mặc định nhanh hơn `ConcurrentHashMap` cho point lookup.

### 3.3. FIFO — first in, first out

`ConcurrentLinkedQueue`, `LinkedBlockingQueue` và `ArrayBlockingQueue` có **hợp đồng FIFO** cho những phần tử đã enqueue theo thứ tự xác định.

Nhưng khi nhiều producer gọi `offer()` đồng thời, **thứ tự tuyệt đối giữa hai lời gọi chồng lấn** không tự được xác định bởi thứ tự log, timestamp do thread riêng lấy, hoặc thứ tự worker được OS lập lịch. Các thao tác thành công có một thứ tự hiệu lực theo giao thức queue; nếu business đòi “thứ tự request nhận tại gateway”, phải định nghĩa sequence ở **đúng điểm giao nhận** và áp dụng xử lý phù hợp.

FIFO của hàng đợi cũng **không bảo đảm thứ tự hoàn tất** khi nhiều consumer xử lý song song:

~~~text
Queue lấy ra lần lượt: A, rồi B.
Consumer 1 xử lý A mất 500ms.
Consumer 2 xử lý B mất 10ms.
Kết quả B có thể được công bố trước kết quả A.
~~~

Muốn output hoàn tất theo thứ tự dequeue, cần một tầng reorder/sequence/commit riêng, hoặc xử lý tuần tự.

### 3.4. Priority order

`PriorityBlockingQueue` sắp xếp phần tử theo **priority/natural ordering hoặc comparator**, không theo FIFO nói chung. Phần tử có priority cao hơn theo comparator lấy ra trước; trong Java `PriorityQueue` semantics thường phần tử nhỏ nhất theo comparator đứng đầu.

**Không có bounded capacity thực sự do constructor cung cấp trong `PriorityBlockingQueue`** theo kiểu `ArrayBlockingQueue`. Nó được mô tả là unbounded về cấu trúc (tất nhiên bị giới hạn bởi tài nguyên bộ nhớ). `put()` không tạo backpressure như bounded queue.

Với priority bằng nhau, `PriorityBlockingQueue` **không bảo đảm thứ tự ổn định**. Nếu cần tie-breaker, đưa sequence vào comparator. Dù vậy, khi workers lấy item song song, **thứ tự hoàn thành** vẫn có thể khác thứ tự priority.

### 3.5. Fairness của thread chờ khác thứ tự item

`ArrayBlockingQueue(int capacity, boolean fair)` hỗ trợ fairness policy cho **thứ tự cấp quyền truy cập cho các thread producer/consumer đang chờ**. `fair=true` không có nghĩa:
- Queue trở thành priority queue.
- Tác vụ được xử lý xong theo thứ tự enqueue trong hệ thống nhiều consumer.
- Mọi producer có thể chạy đồng thời mà tạo ra một timestamp ordering ngoài queue.

Fairness thường đánh đổi throughput để giảm biến động/starvation của những thread bị chặn; cần cân nhắc latency và contention thực tế.

### 3.6. Encounter order / snapshot order

`CopyOnWriteArrayList` giữ thứ tự các phần tử như List trong **snapshot backing array** tại lúc tạo iterator; iterator không phản ánh write sau đó. Trong khi đó `ConcurrentHashMap` không có meaningful key iteration order. `ConcurrentSkipListMap` iterator có sorted key order nhưng có thể weakly consistent khi writer đồng thời thay đổi map.

**Kết luận:** trước khi hỏi “collection nào ordered?”, phải trả lời **ordered theo cái gì, tại thời điểm nào, với concurrent writers ra sao và output cần giữ thứ tự nào**.

## 4. Ma trận chọn map: ConcurrentHashMap hay ConcurrentSkipListMap?

| Tiêu chí | `ConcurrentHashMap<K,V>` | `ConcurrentSkipListMap<K,V>` |
| --- | --- | --- |
| Thread-safe truy cập concurrent | Có | Có |
| Key iteration order | **Không bảo đảm** | Theo comparator/natural order tăng dần |
| Point lookup key | Hash-based; thường phù hợp get/put/compute nhanh | Sorted structure; hỗ trợ range/navigation |
| Range `subMap/headMap` | Không phải API cốt lõi | Có |
| `firstKey/ceilingKey` | Không hỗ trợ như NavigableMap | Có |
| Iterators với writes đồng thời | Weakly consistent | Weakly consistent, nhưng theo key ordering của view |
| Global atomic snapshot | Không; aggregate reads có thể thấy trạng thái đang đổi | Không; nhiều thao tác bulk không atomic |
| `null` keys/values | Không hỗ trợ | Không hỗ trợ |
| Multi-key transaction | Không có sẵn | Không có sẵn |
| Common use | Registry, counters, cache lookup | Leaderboard key-sorted, time index, range query |

**Ưu tiên `ConcurrentHashMap` khi:** mục tiêu chính là map lookup/update theo khóa, không yêu cầu thứ tự duyệt; dùng `putIfAbsent`, `compute`, `merge`, conditional `replace` theo key để tránh check-then-act.

**Ưu tiên `ConcurrentSkipListMap` khi:** yêu cầu nghiệp vụ **đọc theo thứ tự key hoặc lấy đoạn khóa** là phần cốt lõi; bạn chấp nhận overhead của cấu trúc sorted.

### Những điều cả hai đều KHÔNG cung cấp

- Không tự tạo một transaction atomic giữa **hai key khác nhau**.
- Không bảo đảm `size()` rồi `get()` phản ánh cùng một snapshot khi writers chạy.
- Không biến mọi vòng for-each thành **snapshot tức thời** của toàn map.
- Không tự bảo đảm các object mutable được lưu trong value thread-safe.
- Không cho phép map key có comparator/hashCode/equals không ổn định do mutable fields bị thay đổi.

### Hash order ngẫu nhiên quan sát được không phải contract

Trong một lần chạy, bạn có thể thấy iterator của `ConcurrentHashMap` xuất key trùng thứ tự insert hoặc như tăng dần. Đó chỉ là hiện tượng tại dữ liệu/hash state ấy, **không phải API guarantee**. Thay JDK, resize, key distribution hoặc interleaving là có thể khác.

Khi chỉ cần in báo cáo **theo thứ tự key tại một thời điểm sau khi writers đã dừng**, có thể copy sang `TreeMap` để sắp xếp. Nếu writers vẫn còn chạy, việc copy từ `ConcurrentHashMap` không tự là một **atomic snapshot**.

## 5. Ví dụ 1 — ConcurrentHashMap write-heavy, đọc kết quả sau join

Bài toán: bốn thread cập nhật các bộ đếm `apple` và `banana`, mỗi thread thêm 1.000 lần vào từng key. Mẫu an toàn dùng `merge`, thực hiện read-modify-write **atomically per key**.

Tạo file **`ConcurrentMapRatioDemo.java`**:

~~~java
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentMapRatioDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            Future<?>[] jobs = new Future<?>[4];
            for (int w = 0; w < jobs.length; w++) {
                jobs[w] = pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        counts.merge("apple", 1, Integer::sum);
                        counts.merge("banana", 1, Integer::sum);
                    }
                });
            }

            for (Future<?> job : jobs) {
                job.get();
            }

            Map<String, Integer> sortedAfterCompletion =
                    new TreeMap<>(counts);

            System.out.println("apple=" + counts.get("apple"));
            System.out.println("banana=" + counts.get("banana"));
            System.out.println("sorted=" + sortedAfterCompletion);
        } finally {
            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac ConcurrentMapRatioDemo.java
java ConcurrentMapRatioDemo
~~~

Stdout khi không có exception/interruption bên ngoài:

~~~text
apple=4000
banana=4000
sorted={apple=4000, banana=4000}
~~~

**Giải thích:**
- `merge("apple",1,Integer::sum)` là phép cập nhật per-key theo contract `ConcurrentHashMap`, tránh mẫu lỗi `get` rồi `put` riêng rẽ.
- Bốn workers, mỗi worker 1.000 lần, nên mỗi key có giá trị 4.000.
- Main chờ đủ `Future.get()` trước khi copy map; khi ấy **không còn writer của demo đang hoạt động**, nên snapshot bản copy ổn định.
- `TreeMap` **chỉ dùng để xuất kết quả sorted** sau khi workers dừng; bản sao không thay map gốc thành ordered.
- Không in trực tiếp `counts.toString()` và tuyên bố một thứ tự, vì `ConcurrentHashMap` không có ordering contract.

### Nếu workload là counter thực sự

Nếu nhiều thread cùng cộng vào **một key nóng**, cập nhật `Integer` bằng `merge` có thể bị contention. `ConcurrentHashMap<String,LongAdder>` với `computeIfAbsent(k, x -> new LongAdder()).increment()` là pattern đếm tần suất phổ biến. Nhưng việc đọc `LongAdder.sum()` trong khi writes đang diễn ra **không phải atomic snapshot** toàn bộ updates; và nếu bạn remove/replace entry `LongAdder`, cần định nghĩa ownership/lifecycle để không làm mất increment.

Không áp dụng LongAdder cho bài toán cần transaction đa key hoặc đòi số đếm tại mọi thời điểm phải chính xác linearizable trên nhiều biến.

## 6. Ví dụ 2 — Sorted key và range query với ConcurrentSkipListMap

Cần lưu các key số nguyên và duyệt theo thứ tự tăng dần, bất kể thứ tự insert. `ConcurrentSkipListMap` giữ ordering theo key.

Tạo file **`SortedConcurrentMapDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentSkipListMap;

public class SortedConcurrentMapDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(20, "twenty");
        map.put(40, "forty");

        System.out.println("keys=" + map.navigableKeySet());
        System.out.println("first=" + map.firstKey());
        System.out.println("ceiling25=" + map.ceilingKey(25));
        System.out.println("range=" + map.subMap(20, true, 40, false));
    }
}
~~~

Chạy:

~~~bash
javac SortedConcurrentMapDemo.java
java SortedConcurrentMapDemo
~~~

Stdout (không có concurrent writer trong demo):

~~~text
keys=[10, 20, 30, 40]
first=10
ceiling25=30
range={20=twenty, 30=thirty}
~~~

Khi nhiều writers đồng thời thay đổi map:
- Navigation/range views vẫn tuân thủ comparator ordering cho các phần tử chúng quan sát.
- Iterator là **weakly consistent**, có thể thấy hoặc không thấy một số cập nhật đồng thời.
- `subMap` tạo **view theo range**, không phải một bản sao immutable hoặc một snapshot nguyên tử của cả range.
- Nếu business yêu cầu một báo cáo range tại **cùng một thời điểm logic**, cần một giao thức snapshot/locking/versioning ngoài collection.

### Comparator quyết định “hai key có giống nhau không”

Ví dụ dùng comparator so sánh chuỗi không phân biệt hoa/thường:

~~~java
ConcurrentSkipListMap<String, Integer> m =
        new ConcurrentSkipListMap<>(String.CASE_INSENSITIVE_ORDER);
m.put("ABC", 1);
m.put("abc", 2);
~~~

Đây là snippet; do comparator coi hai chuỗi bằng nhau về ordering, hai `put` tác động tới **cùng một mapping theo comparator**, không tạo hai key độc lập theo cách `String.equals`. Comparator cần được chọn từ **định nghĩa định danh dữ liệu**, không chỉ từ tiêu chí hiển thị.

## 7. Danh sách read-mostly: CopyOnWriteArrayList

`CopyOnWriteArrayList<E>` có cách đánh đổi khác biệt:
- Các phép cập nhật như `add` hoặc `set` thường tạo **bản sao backing array** rồi publish phiên bản mới.
- Reads/iteration có thể truy cập một backing array ổn định mà không cần lock của writer cho từng phần tử.
- Iterator theo **snapshot** tại lúc tạo. Các thêm/xóa/sửa sau đó **không hiện trong iterator cũ**.
- Iterator không hỗ trợ `remove/set/add` qua chính iterator, các thao tác đó ném `UnsupportedOperationException`.
- List giữ **thứ tự theo index của phiên bản snapshot**, không phải sorted key.
- `null` phần tử được phép theo hợp đồng class, khác nhiều concurrent maps/queues.

**Tốt khi:** dữ liệu tương đối nhỏ, reads/iterations rất nhiều, writers hiếm, cần iterator không bị cản trở bởi cập nhật đồng thời. Ví dụ danh sách listeners, callbacks, feature flags được publish từng đợt.

**Không tốt khi:** collection lớn và phải liên tục add/remove/set, vì mỗi update có chi phí copy gần theo kích thước array và áp lực allocation/GC. Một write burst làm ratio trung bình read-heavy không còn phản ánh chi phí đỉnh.

### Snapshot có bất biến gì?

Snapshot iterator cố định **tập reference và thứ tự phần tử** của backing array ở thời điểm tạo. Nó **không deep-copy object được tham chiếu**. Nếu một element là mutable bean và thread khác sửa bean ấy, snapshot list **không đóng băng trạng thái bên trong bean**.

Đây là khác biệt giữa:
- **Snapshot của cấu trúc List**.
- **Immutable snapshot của toàn bộ object graph**.

Nếu cần snapshot bất biến thật, hãy dùng **immutable elements** (ví dụ records với field immutable) hoặc sao chép sâu theo yêu cầu nghiệp vụ.

## 8. Ví dụ 3 — Snapshot iterator và write tới CopyOnWriteArrayList

Tạo file **`CopyOnWriteReadMostlyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteReadMostlyDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>();

        listeners.add("alpha");
        listeners.add("beta");

        Iterator<String> snapshot = listeners.iterator();
        listeners.add("gamma");
        listeners.remove("alpha");

        List<String> oldView = new ArrayList<>();
        snapshot.forEachRemaining(oldView::add);

        System.out.println("snapshot=" + oldView);
        System.out.println("current=" + listeners);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CopyOnWriteReadMostlyDemo.java
java CopyOnWriteReadMostlyDemo
~~~

Stdout:

~~~text
snapshot=[alpha, beta]
current=[beta, gamma]
~~~

**Vì sao?**
1. Iterator `snapshot` được tạo khi list chứa `alpha,beta`.
2. `add("gamma")` và `remove("alpha")` thay đổi phiên bản backing array hiện hành.
3. Iterator cũ vẫn đi qua các reference của phiên bản cũ.
4. Khi in chính `listeners`, ta thấy nội dung hiện tại `beta,gamma`.

Ví dụ thực thi tuần tự để tách biệt semantics snapshot khỏi scheduler. Khi writers chạy đồng thời, iterator cũ vẫn dùng snapshot của cấu trúc list, nhưng như đã nói **không đóng băng field mutable của element**.

### Iterator.remove() không hỗ trợ

~~~java
Iterator<String> iterator = listeners.iterator();
iterator.remove(); // UnsupportedOperationException
~~~

Đây là snippet minh họa. Nếu cần xóa, sử dụng phương thức collection `listeners.remove(x)` hoặc thao tác update thích hợp, hiểu rằng chúng có thể tạo bản sao backing array mới.

### Read-heavy không có nghĩa “CopyOnWrite cho mọi map”

`CopyOnWriteArrayList` là **List**, không phải bản thay thế cho `ConcurrentHashMap`:
- Lookup một phần tử bằng `contains` có thể quét tuyến tính.
- Không có `get(key)` như map.
- Duplicates, vị trí list và callback-order có semantics riêng.
- Mỗi lần write copy backing array là đánh đổi quan trọng.

Nếu bạn có một map lớn read-mostly, cân nhắc **immutable map snapshot publish qua `volatile`/`AtomicReference`**, hoặc `ConcurrentHashMap` nếu vẫn có nhiều incremental updates, tùy chi phí snapshot và yêu cầu atomic read.

## 9. List có nhiều writes: synchronizedList, locking hay kiến trúc khác?

Nếu các write vào List diễn ra thường xuyên, sao chép toàn bộ array mỗi lần có thể quá đắt. Một phương án là:

~~~java
List<String> list =
        Collections.synchronizedList(new ArrayList<>());
~~~

Snippet cần `import java.util.*;`. Wrapper dùng synchronization bảo vệ **từng lời gọi method** qua wrapper, nhưng không tự biến **nhiều lời gọi** thành một transaction. Ví dụ:

~~~java
if (!list.contains("x")) {
    list.add("x");
}
~~~

Hai thread có thể cùng thấy chưa chứa x rồi cùng thêm, tạo duplicate. Nếu cần atomic check-then-add phải giữ **cùng monitor** của list quanh toàn bộ sequence:

~~~java
synchronized (list) {
    if (!list.contains("x")) {
        list.add("x");
    }
}
~~~

**Iterator của synchronizedList yêu cầu đồng bộ thủ công khi đang traverse**:

~~~java
synchronized (list) {
    for (String value : list) {
        consume(value);
    }
}
~~~

Đây là snippet với `consume` là method đã tồn tại. Nếu dùng collection view/subList, phải xem đúng tài liệu wrapper và monitor cần dùng. Nếu callback `consume` chậm, việc giữ monitor trong suốt iteration có thể block writers lâu; có thể **copy snapshot dưới lock** rồi iterate ngoài lock khi phù hợp.

### Khi nào thay đổi kiến trúc thay vì khóa List?

- Nếu liên tục append và drain, dùng **queue** thay List với `add` + `remove(0)`.
- Nếu cần lookup theo ID, dùng **map** thay List rồi scan.
- Nếu cần theo key order, dùng **sorted concurrent map/set**.
- Nếu cần nhiều reader đọc một phiên bản ổn định trong khi writers build batch mới, dùng **immutable snapshot + atomic publication**.
- Nếu cần index-stable mutation đồng thời, cần khóa/ownership rõ; không có một concurrent list tổng quát thay thế mọi `ArrayList` với chi phí không đáng kể.

**Ordering của List** còn cần nói rõ: index order của List không phải completion order của các thread. Nếu nhiều writers cùng `add`, thứ tự cuối là thứ tự mà cập nhật được chấp nhận trong cơ chế collection, không phải thứ tự timestamp logic tự phát của các thread.

## 10. Weakly consistent iteration khác snapshot và fail-fast

Ba kiểu hành vi thường gặp:

| Kiểu iterator | Đặc tính | Ví dụ |
| --- | --- | --- |
| **Fail-fast (best effort)** | Có thể ném `ConcurrentModificationException` khi phát hiện structural modification trái phép; không phải cơ chế safety guarantee | `ArrayList` iterator khi bị sửa không đúng quy tắc |
| **Weakly consistent** | Không ném CME chỉ vì cập nhật đồng thời; có thể phản ánh một số thay đổi trong lúc duyệt, không tạo snapshot toàn cục | `ConcurrentHashMap`, `ConcurrentLinkedQueue`, `ConcurrentSkipListMap` |
| **Snapshot** | Duyệt backing snapshot lúc tạo; không thấy thay đổi cấu trúc sau đó | `CopyOnWriteArrayList` |

### Một hiểu lầm nghiêm trọng

**“Không ném ConcurrentModificationException” không có nghĩa iterator đã nhìn được tất cả records đúng tại một thời điểm.** Với weakly consistent iterator, dữ liệu có thể được quan sát theo tiến trình cập nhật; nó hợp lý cho monitoring, scanning hoặc best-effort operations, nhưng không tự phù hợp cho báo cáo phải phản ánh cùng một thời điểm logic.

**“Fail-fast” cũng không phải một biện pháp đồng bộ.** `ConcurrentModificationException` là best-effort bug detector, không bảo đảm được ném trong mọi race. Không viết test correctness dựa vào việc “chắc chắn sẽ ném CME”.

### Snapshot của CopyOnWriteArrayList không phải snapshot của hai collection

Nếu bạn có một `CopyOnWriteArrayList` và một `ConcurrentHashMap`, đọc iterator list rồi đọc map không tự tạo **multi-collection atomic snapshot**. Nếu invariant yêu cầu hai nguồn cùng một epoch/version, cần publish một immutable aggregate state dưới một reference, dùng lock hoặc thiết kế snapshot/transaction riêng.

## 11. Các queue: FIFO, priority, blocking và boundedness

| Collection | Order khi lấy | Blocking API | Bounded? | Gợi ý |
| --- | --- | --- | --- | --- |
| `ConcurrentLinkedQueue<E>` | FIFO | `offer/poll` nonblocking; không có `take` | Unbounded về cấu trúc | Throughput event handoff với kiểm soát tải bên ngoài |
| `LinkedBlockingQueue<E>` | FIFO | `put/take/offer(timeout)/poll(timeout)` | Có capacity tùy chọn; mặc định thực tế rất lớn | Producer-consumer cần block khi trống |
| `ArrayBlockingQueue<E>` | FIFO | `put/take` và timed methods | **Capacity cố định** | Backpressure và giới hạn bộ nhớ rõ |
| `LinkedBlockingDeque<E>` | Hai đầu; FIFO khi dùng `putLast/takeFirst` | Blocking ở hai đầu | Capacity tùy chọn | Work deque, đầu/cuối khác semantics |
| `PriorityBlockingQueue<E>` | Comparator/natural priority | `take` khi trống | **Không có bounded capacity thực tế** | Scheduler theo priority, không FIFO |
| `SynchronousQueue<E>` | Handoff trực tiếp, không buffer | `put/take` đợi đối tác | **Capacity 0** | Rendezvous giữa producer-consumer |
| `LinkedTransferQueue<E>` | FIFO với transfer semantics | `transfer` có thể đợi consumer nhận | Unbounded về cấu trúc | Phối hợp direct transfer khi phù hợp |

Ở đây “unbounded” không có nghĩa vô hạn bộ nhớ: chương trình vẫn có thể bị `OutOfMemoryError` khi producers nhanh hơn consumers và không có backpressure.

### Queue có FIFO ≠ các task xử lý xong FIFO

Nếu một queue trả item A trước B nhưng có hai consumers, B có thể hoàn tất trước A. Đây là câu hỏi về **processing/commit order**, không phải contract dequeue của queue.

### Bounded queue là cơ chế bảo vệ tài nguyên

Với `ArrayBlockingQueue<>(capacity)`:
- `put` chờ khi full.
- `offer` trả `false` khi full.
- `offer(timeout)` đợi có giới hạn.
- `take` chờ khi empty.
- `poll` trả `null` khi empty.
- `poll(timeout)` chờ có hạn.

Đây là các lựa chọn backpressure/timeout theo nghiệp vụ. Khi producer vượt khả năng consumer, một bounded queue ngăn tăng backlog không kiểm soát, nhưng nếu mọi producer đều block trong thread pool nhỏ, bạn phải xét **thread-starvation deadlock và throughput**. Backpressure là một chính sách toàn pipeline, không chỉ một constructor.

### Priority có thể gây starvation

Nếu liên tục có item priority cao, các item priority thấp có thể đợi rất lâu. `PriorityBlockingQueue` không tự bảo đảm **aging/fairness theo tuổi item**. Nếu business cần ngăn starvation, hãy thiết kế comparator/aging hoặc scheduler phù hợp, chú ý comparator nhất quán và tính đồng bộ của priority fields.

## 12. Ví dụ 4 — FIFO, capacity và priority: ba yêu cầu khác nhau

Tạo file **`QueueOrderingDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.PriorityBlockingQueue;

public class QueueOrderingDemo {
    public static void main(String[] args) {
        ArrayBlockingQueue<String> fifo =
                new ArrayBlockingQueue<>(2, true);

        boolean first = fifo.offer("A");
        boolean second = fifo.offer("B");
        boolean third = fifo.offer("C");

        System.out.println("fifoAccepted=" +
                first + "," + second + "," + third);
        System.out.println("fifoPoll1=" + fifo.poll());
        System.out.println("fifoPoll2=" + fifo.poll());

        PriorityBlockingQueue<Integer> priority =
                new PriorityBlockingQueue<>();
        priority.offer(30);
        priority.offer(10);
        priority.offer(20);

        System.out.println("priorityPoll1=" + priority.poll());
        System.out.println("priorityPoll2=" + priority.poll());
        System.out.println("priorityPoll3=" + priority.poll());
    }
}
~~~

Chạy:

~~~bash
javac QueueOrderingDemo.java
java QueueOrderingDemo
~~~

Stdout:

~~~text
fifoAccepted=true,true,false
fifoPoll1=A
fifoPoll2=B
priorityPoll1=10
priorityPoll2=20
priorityPoll3=30
~~~

**Phân tích:**
- FIFO bounded capacity 2: `offer("C")` bị từ chối khi đang full, không block. Đây là backpressure có thể quan sát và xử lý.
- `fair=true` nói về **fairness của các thread chờ truy cập**, không đổi thứ tự A rồi B thành priority order.
- `PriorityBlockingQueue` lấy số nhỏ nhất theo natural comparator trước, dù insert theo thứ tự 30,10,20.
- Ví dụ đơn thread để test contract; khi nhiều producers cạnh tranh, thứ tự enqueue thực tế chịu ảnh hưởng timing, và khi nhiều consumers, thứ tự hoàn tất là vấn đề khác.
- Không dựa vào `PriorityBlockingQueue.iterator()` để xuất một dãy **sorted**; iterator của priority queue không nhất thiết duyệt theo thứ tự priority. Muốn quan sát lấy theo priority, dùng `poll/take` hoặc tạo snapshot rồi sort.

### Các phần tử priority bằng nhau

Giả sử hai item có cùng priority. `PriorityBlockingQueue` không bảo đảm chúng được lấy FIFO theo thời điểm insert. Nếu cần tie-break, đưa một **sequence number** vào item và comparator:

~~~java
record Job(int priority, long sequence, String payload) {}

Comparator<Job> comparator =
        Comparator.comparingInt(Job::priority)
                  .thenComparingLong(Job::sequence);
~~~

Đây là snippet, cần import `java.util.Comparator`. Nếu nhiều producers cần sequence duy nhất, sử dụng `AtomicLong.getAndIncrement()` ở điểm xác định ordering. Tuy nhiên **lúc lấy sequence và lúc enqueue không là một transaction**, nên nếu business yêu cầu thứ tự ingress tuyệt đối, hãy thiết kế chính sách gán sequence/tie-break tại đúng ranh giới tiếp nhận.

## 13. Ví dụ 5 — ConcurrentLinkedQueue và nhiều consumers: claim bằng poll()

Một queue FIFO concurrent cho phép nhiều workers tranh lấy phần tử. Nếu muốn mỗi item được một consumer nhận, dùng **chính thao tác `poll()` để claim**, không dùng check-then-act kiểu `if (!queue.isEmpty()) queue.remove()`.

Tạo file **`ConcurrentQueueClaimDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentQueueClaimDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();

        for (int i = 1; i <= 1_000; i++) {
            queue.offer(i);
        }

        AtomicInteger processed = new AtomicInteger();
        AtomicInteger sum = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            Future<?>[] workers = new Future<?>[4];
            for (int w = 0; w < workers.length; w++) {
                workers[w] = pool.submit(() -> {
                    Integer value;
                    while ((value = queue.poll()) != null) {
                        processed.incrementAndGet();
                        sum.addAndGet(value);
                    }
                });
            }

            for (Future<?> worker : workers) {
                worker.get();
            }

            System.out.println("processed=" + processed.get());
            System.out.println("sum=" + sum.get());
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac ConcurrentQueueClaimDemo.java
java ConcurrentQueueClaimDemo
~~~

Stdout:

~~~text
processed=1000
sum=500500
remaining=0
~~~

**Chứng minh kết quả:**
1. Queue được nạp sẵn 1.000 số `1..1000`, không có producer trong giai đoạn consumer chạy.
2. Mỗi `poll()` thành công lấy đúng một item. Không có hai consumer cùng nhận một phần tử từ cùng thao tác dequeue.
3. Các consumer dừng khi `poll()` trả `null`; vì không có producer mới, đó là điều kiện kết thúc hợp lệ của demo.
4. `Future.get()` đợi đủ workers; `AtomicInteger` bảo vệ `processed/sum` khi cập nhật đa thread.
5. Tổng dãy là `1000*1001/2=500500`; queue sau đó rỗng.

**Trong production có producer liên tục:** `poll()==null` chỉ có nghĩa **hiện tại** không có item để lấy, không có nghĩa producer sẽ không gửi thêm. Cần lifecycle như `closed`, poison pill, scheduler/wakeup hoặc một `BlockingQueue.take()` thích hợp. Cũng đừng dùng `queue.size()` của `ConcurrentLinkedQueue` để quyết định chính xác một business invariant giữa nhiều writers: size có thể tốn O(n) và thay đổi trong lúc đếm.

### FIFO không áp đặt thời gian hoàn tất

Ngay cả khi queue cung cấp item theo FIFO, bốn workers có thể xử lý và cập nhật aggregate theo thứ tự bất kỳ. Chỉ kết quả cuối sau `get()` là xác định, không có stdout “worker 1 xử lý 1, worker 2 xử lý 2” nào được bảo đảm.

## 14. Ví dụ 6 — Bounded BlockingQueue và producer-consumer

Để có **backpressure** và chờ dữ liệu không busy-poll, `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` với capacity rõ là lựa chọn phổ biến.

Tạo file **`BoundedPipelineDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedPipelineDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> producer = pool.submit(() -> {
                try {
                    queue.put(1);
                    queue.put(2);
                    queue.put(3);
                    queue.put(-1); // Sentinel kết thúc cho một consumer.
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            Future<List<Integer>> consumer = pool.submit(() -> {
                List<Integer> received = new ArrayList<>();
                while (true) {
                    int value = queue.take();
                    if (value == -1) {
                        return received;
                    }
                    received.add(value);
                }
            });

            producer.get();
            System.out.println("received=" + consumer.get());
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac BoundedPipelineDemo.java
java BoundedPipelineDemo
~~~

Stdout khi không có interruption/lỗi bên ngoài:

~~~text
received=[1, 2, 3]
remaining=0
~~~

**Phân tích:**
- Queue capacity 2 khiến producer **có thể phải đợi** nếu consumer chưa lấy phần tử; đây là backpressure thay vì tăng memory backlog không giới hạn.
- Một producer đưa `1,2,3,-1` theo thứ tự, một consumer lấy theo FIFO nên List nhận `[1,2,3]`.
- Sentinel chỉ dành cho ví dụ **một consumer**, và -1 được định nghĩa là giá trị không phải dữ liệu thực.
- Nếu có N consumers và muốn dùng poison pills, cần thiết kế số tín hiệu kết thúc phù hợp, không chỉ một sentinel; hoặc dùng một giao thức `closed`/coordinator riêng.
- Nếu producer bị interrupt trước khi gửi sentinel, consumer có thể chờ mãi; trong production cần timeout/cancellation/shutdown robust.
- Dùng `shutdownNow()` khi tất cả futures đã kết thúc trong demo chỉ là cleanup executor; không nên ngầm dùng nó để cắt ngang task nghiệp vụ còn đang commit.

### Khi nào dùng LinkedBlockingQueue?

`LinkedBlockingQueue` có node-based FIFO và capacity tùy chọn. `new LinkedBlockingQueue<>()` mặc định capacity là `Integer.MAX_VALUE`, vì vậy nếu producers có thể nhanh hơn consumers kéo dài, nên truyền **capacity hữu hạn** để bảo vệ hệ thống.

`ArrayBlockingQueue` dùng một backing array với capacity cố định; dễ kiểm soát memory footprint của các references. Không kết luận ArrayBlockingQueue luôn nhanh hơn LinkedBlockingQueue: workload contention, operation patterns, allocation, GC và fairness đều ảnh hưởng.

## 15. Chọn queue theo yêu cầu thực tế

### 15.1. Nonblocking handoff

Nếu producer và consumer nên hoạt động mà không chờ queue có item, dùng `ConcurrentLinkedQueue.offer/poll`. Caller tự quyết định khi `poll()==null`, ví dụ ngừng batch, đợi signal ở tầng khác hoặc quay lại scheduler. Không dùng vòng:

~~~java
while (queue.isEmpty()) {
    // quay nóng không timeout / không chờ hiệu quả
}
~~~

Đây là anti-pattern khi không có chiến lược backoff/yield hoặc event notification; nó có thể ngốn CPU.

### 15.2. Blocking FIFO có backpressure

Nếu thiếu item thì consumer chờ, queue đầy thì producer phải chờ, dùng `BlockingQueue` có capacity:
- `ArrayBlockingQueue`: fixed bounded array, có tùy chọn fairness.
- `LinkedBlockingQueue(capacity)`: linked FIFO với capacity cấu hình.

Chọn timed `offer/poll` nếu có deadline hoặc không muốn block vô hạn. Khi shutdown, chuyển trạng thái ở đúng protocol và đánh thức các workers đang chờ.

### 15.3. Direct handoff

`SynchronousQueue` không giữ item trong buffer. Producer `put` chờ consumer tương ứng nhận; consumer `take` chờ producer. Đây là mô hình **rendezvous**, không phải queue có backlog. Có thể hữu ích khi muốn handoff trực tiếp và không cho tích tụ item, nhưng phải tránh deadlock do cả hai phía chạy trong pool quá nhỏ.

### 15.4. Priority scheduling

`PriorityBlockingQueue` dùng khi thứ tự ưu tiên là hợp đồng thực sự. Một câu hỏi cần trả lời: nếu item có priority bằng nhau, có cần FIFO hay không? Nếu có, bổ sung sequence/tie-breaker nhất quán. Nếu task priority thấp không được phép starve, cần aging hoặc scheduler cao hơn.

### 15.5. Double-ended queue

`LinkedBlockingDeque`/`ConcurrentLinkedDeque` cho phép thêm/lấy hai đầu, phù hợp work queue/deque khi có semantics head/tail rõ. Nếu chỉ dùng `addLast/pollFirst`, có hành vi FIFO; nếu dùng `push/pop` thì có hành vi stack LIFO. “Deque là ordered” không mô tả đủ contract.

## 16. Atomicity: thread-safe collection không tự tạo transaction

Một collection thread-safe bảo vệ hợp đồng của từng thao tác, nhưng các bước ghép lại có thể không atomic.

### 16.1. Check-then-act trên Map

Sai:

~~~java
if (!map.containsKey(key)) {
    map.put(key, value);
}
~~~

Hai writers có thể cùng thấy key chưa tồn tại rồi cùng put; điều kiện “chỉ một writer được tạo” bị vi phạm. Với concurrent map, dùng `putIfAbsent` nếu chỉ cần đặt mapping khi vắng:

~~~java
V old = map.putIfAbsent(key, value);
~~~

Đây là snippet có kiểu `K/V` và `map` phù hợp. Nếu value cần tính, dùng `computeIfAbsent` với mapping function không sửa chính map một cách đệ quy và tránh thực hiện I/O/side effect lâu khi contract của implementation yêu cầu hàm ngắn.

### 16.2. Update counter theo key

Sai:

~~~java
map.put(key, map.get(key) + 1);
~~~

Từng lời gọi get/put có thể thread-safe nhưng tổ hợp không atomic. Dùng `compute` hoặc `merge` cho mapping một key, hoặc `LongAdder` cho frequency counter khi semantics phù hợp.

### 16.3. Atomic per-key không bằng atomic multi-key

Giả sử chuyển 100 đồng từ tài khoản A sang B lưu trong ConcurrentHashMap:

~~~java
balances.compute("A", (k, v) -> v - 100);
balances.compute("B", (k, v) -> v + 100);
~~~

Hai cập nhật per-key có thể atomic từng cái nhưng có thời điểm observer thấy A đã giảm còn B chưa tăng. Nếu invariant đòi tổng tiền không đổi ở **mọi snapshot nghiệp vụ**, cần một lock/giao thức transaction bảo vệ cả hai key, hoặc publish một immutable aggregate state bằng atomic reference. Không có một ConcurrentHashMap method đơn lẻ tạo transaction đa key cho bạn.

### 16.4. size/isEmpty không thay thế claim

Ở queue concurrent, `isEmpty()` rồi `remove()` có race với consumer khác. Dùng `poll()` để claim một item; với yêu cầu chờ, dùng `take()`. Ở map đồng thời ghi, `size()` và `containsValue()` không luôn phù hợp làm decision-critical status dưới writes đang diễn ra; thường chỉ hữu ích cho monitoring/estimation.

### 16.5. Mutable value vẫn cần protection

`ConcurrentHashMap<String,ArrayList<Event>>` không làm thao tác trên các `ArrayList<Event>` nằm bên trong tự trở nên thread-safe. Collection bảo vệ **map structure**; object nằm ở value có contract riêng. Chọn immutable values, concurrent value type hoặc một giao thức lock/ownership rõ ràng.

## 17. Snapshot nhất quán và publish immutable state

Khi yêu cầu là “rất nhiều readers, writer cập nhật theo batch và mỗi reader cần **một phiên bản dữ liệu nhất quán**”, có thể tốt hơn dùng **immutable snapshot** thay vì collection mutable concurrent trực tiếp.

Pattern:

~~~java
record Config(int version, Map<String, String> options) {}

AtomicReference<Config> current = new AtomicReference<>(
        new Config(1, Map.of("mode", "safe")));

Config before = current.get();
Config next = new Config(2, Map.of("mode", "fast"));
current.set(next);
~~~

Đây là snippet cần imports `java.util.Map` và `java.util.concurrent.atomic.AtomicReference`. `Map.of` tạo immutable map; object `Config` là record giữ reference bất biến trong ví dụ.

- Reader lấy `Config snapshot = current.get()` một lần, rồi dùng **chính object đó** cho mọi field cần nhất quán.
- Writer xây cả trạng thái mới **trước** khi publish bằng `set`/`compareAndSet`.
- Một lần read reference là atomic, phù hợp đọc nhiều/write ít khi cần snapshot coherent nhiều field.
- Nếu nhiều writers cạnh tranh, dùng `compareAndSet`/update loop để không làm lost update; `set` mù có thể ghi đè state của writer khác.
- Không nên dùng mutable map cũ rồi sửa sau khi publish; lúc đó reader vẫn có thể thấy state thay đổi.

**CopyOnWriteArrayList** tự có snapshot của backing array theo iterator, còn immutable aggregate publication giúp tổ chức **nhiều cấu trúc liên quan** cùng một version. Đây là hai lựa chọn khác nhau, tùy invariant.

## 18. Benchmark và read/write ratio: đo cái gì?

Để chọn tốt không thể chỉ nhìn tên “Concurrent”. Hãy đo workload đại diện theo nhiều tỉ lệ và mức contention:
- 99:1, 90:10, 50:50, 10:90 và burst writes, nhưng chỉ dùng chúng như **kịch bản thử**, không là mốc tối ưu mặc định.
- Point lookup, index read, full iteration/range query, add/remove, put/compute/merge.
- Dữ liệu nhỏ/vừa/lớn, kích thước element/value thực tế, số keys nóng.
- 1, 2, 4, 8, ... threads tùy máy và CPU quota.
- Tốc độ producer/consumer, capacity/backpressure và tỉ lệ dropped/blocked operations.
- Ordering correctness: sorted keys, FIFO dequeue, priority tie-break, snapshot epoch và result completion order.
- Allocation/GC, p95/p99 latency, throughput, CPU utilization, lock contention và memory footprint.

### Ma trận thí nghiệm gợi ý

| Workload | Collection đối chiếu | Metric chính |
| --- | --- | --- |
| 99% list iteration, write hiếm | `CopyOnWriteArrayList` vs synchronized immutable snapshot | p99 iteration latency, write copy cost, GC |
| Frequent map get/merge | `ConcurrentHashMap` vs `ConcurrentSkipListMap` (chỉ khi ordering thật sự cần) | Throughput per-key, contention, latency |
| Sorted range query | `ConcurrentSkipListMap` vs sorted snapshot publication | Range latency, freshness, memory |
| FIFO handoff | `ConcurrentLinkedQueue` vs bounded `BlockingQueue` | Consumer wakeup, throughput, CPU spin |
| Bounded producer-consumer | `ArrayBlockingQueue` vs `LinkedBlockingQueue(capacity)` | Queue wait time, backlog, memory |
| Priority tasks | `PriorityBlockingQueue` + policy | Ordering, starvation, latency theo priority |
| Snapshot read của nhiều field | Immutable aggregate `AtomicReference` | Coherent versions, write latency |

### JMH và đo điều kiện hệ thống

Với microbenchmark, nên dùng **JMH**:
- Warm-up JVM/JIT trước khi đo.
- Tránh dead-code elimination bằng cách consume kết quả.
- Tránh đo log/console trong hot path.
- Dùng nhiều iterations/forks, kiểm tra correctness ngoài benchmark.
- Ghi rõ VM, OS, CPU, core/threads, GC và collection sizes.
- Cẩn trọng với benchmark có chung một lock nóng hoặc key nóng gây méo tỉ lệ.

Không trình bày một kết quả “ConcurrentHashMap nhanh hơn SkipListMap 3 lần” khi chưa đo đúng workload. Cũng không lấy một sample `System.nanoTime()` làm kết luận phổ quát.

### Chọn workload theo thời điểm cao điểm, không chỉ trung bình

Một cấu hình có 99% đọc trong cả ngày có thể có đợt rollout cập nhật toàn bộ list trong một giây. Với CopyOnWriteArrayList, mỗi add/remove copy array; một burst viết liên tục vào list lớn có thể tạo allocation spike. Nếu ứng dụng có **batch update**, có thể build một immutable snapshot mới rồi publish một lần thay vì 10.000 lần `add`.

## 19. Hướng dẫn lựa chọn theo tình huống

### Tình huống A: Cache theo key, không cần ordering

**Chọn điểm xuất phát:** `ConcurrentHashMap<K,V>`. Nếu giá trị được compute khi thiếu, dùng `computeIfAbsent` phù hợp và callback ngắn. Nếu cần eviction/TTL/LRU thực sự, concurrent hash map đơn thuần **không tự có cơ chế cache eviction**, cần abstraction cache đúng hợp đồng.

### Tình huống B: Danh sách listeners read-many/write-rare

**Chọn điểm xuất phát:** `CopyOnWriteArrayList<E>`. Iterator nhìn snapshot callback list; một listener đăng ký hoặc xóa giữa lúc dispatch không thay đổi iterator đang chạy. Nếu listener object mutable hoặc callback có side effect, bản thân list không bảo đảm thread-safety cho listener.

### Tình huống C: Registry theo ID có duyệt sorted/range

**Chọn điểm xuất phát:** `ConcurrentSkipListMap<K,V>`. Nếu point lookup chiếm đa số và sorted report rất hiếm, cân nhắc `ConcurrentHashMap` + snapshot sort ở lúc báo cáo (khi chấp nhận được freshness/consistency policy).

### Tình huống D: Producer/consumer FIFO có giới hạn memory

**Chọn điểm xuất phát:** `ArrayBlockingQueue` hoặc `LinkedBlockingQueue(capacity)`. Chọn `put/take` nếu chấp nhận chờ, `offer/poll(timeout)` nếu cần deadline. Đặt policy cho full queue: block, reject, drop, retry hay shed load.

### Tình huống E: Handoff nonblocking với backlog được kiểm soát bên ngoài

**Chọn điểm xuất phát:** `ConcurrentLinkedQueue`. Dùng `poll` để claim item. Nếu backlog có nguy cơ tăng vô hạn mà không có cơ chế điều tiết, đừng chọn unbounded queue chỉ vì throughput tốt ở benchmark nhỏ.

### Tình huống F: Work queue ưu tiên

**Chọn điểm xuất phát:** `PriorityBlockingQueue` khi comparator order là yêu cầu chính. Thiết kế sequence cho tie-breaking và aging chống starvation nếu cần. Vì không bounded theo constructor, phải bổ sung admission control/backpressure ở tầng ngoài.

### Tình huống G: Đọc cả một phiên bản cấu hình nhất quán

**Chọn điểm xuất phát:** immutable aggregate snapshot được publish qua `AtomicReference`/`volatile`, hoặc `CopyOnWriteArrayList` khi chỉ cần versioned list of refs. Nếu snapshot quá lớn và updates thường xuyên, chi phí copy có thể quá đắt.

### Tình huống H: Insertion order phải được giữ cùng multi-step atomic mutation

Không có “ConcurrentLinkedHashMap của JDK 17” trong bộ collection chuẩn tương đương `LinkedHashMap` có sẵn ordering và thread-safety tổng quát. Có thể dùng synchronized wrapper và giữ lock cho toàn bộ sequence, hoặc thiết kế immutable state publication, hoặc chọn một thư viện có contract rõ. **Không mặc định `ConcurrentHashMap` giữ insertion order.**

## 20. Lỗi thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chọn collection chỉ vì read/write ratio trung bình | Bỏ qua iteration cost, burst và contention | Đo workload theo operation và peak |
| Dùng `ConcurrentHashMap` rồi dựa vào thứ tự iterator | Output không có ordering contract | `ConcurrentSkipListMap` hoặc sorted snapshot |
| Nhầm sorted key với insertion order | Dữ liệu hiển thị theo key, không theo arrival | Chọn đúng ordering semantics |
| Nhầm FIFO với completion order | Nhiều consumers xử lý xong khác dequeue order | Sequence/reorder/serial commit |
| Nhầm `fair=true` với priority order | Chính sách chờ thread không đổi thứ tự item | Phân biệt fairness với queue comparator |
| Dùng `PriorityBlockingQueue` nhưng cần bounded backpressure | Backlog có thể tăng vượt giới hạn memory | Admission control/bounded design |
| Dùng `CopyOnWriteArrayList` cho write-heavy large list | Copy array và GC tăng mạnh | Chọn lock/batch snapshot/kiến trúc khác |
| Cho rằng snapshot iterator deep-copy elements | Mutable fields vẫn có thể thay đổi | Immutable elements/deep snapshot |
| Dùng `Collections.synchronizedList` rồi iterate không khóa | Contract iteration chưa được bảo vệ | `synchronized(list)` quanh traverse |
| Dùng `containsKey` + `put` để đảm bảo single creator | Check-then-act race | `putIfAbsent/computeIfAbsent` |
| Dùng `get` + `put` để increment | Lost update | `compute/merge/LongAdder` |
| Dùng `size/isEmpty` làm điều kiện claim trong concurrent queue | Race, size có thể tốn O(n) | `poll/take` |
| Dùng `ConcurrentHashMap<String,ArrayList>` và tưởng value an toàn | Value vẫn mutable không thread-safe | Bảo vệ value/immutable structure |
| Dùng weakly consistent iterator làm atomic audit snapshot | Thiếu/mix updates theo epoch | Snapshot/version/transaction |
| Tin fail-fast CME bảo vệ correctness | Exception là best-effort detector | Đồng bộ hoặc concurrent collection đúng |
| Gọi `poll()==null` coi là stream kết thúc khi producer còn chạy | Mất dữ liệu đến muộn | Closed flag/sentinel/wakeup protocol |
| Sử dụng `PriorityBlockingQueue.iterator()` làm sorted traversal | Iterator không hứa thứ tự priority | Drain bằng `poll` hoặc snapshot sort |
| Dùng comparator phụ thuộc mutable priority field | Invariant heap/tree có thể không cập nhật | Immutable priority; remove/reinsert |
| Trộn nhiều key updates và coi atomic per-key là transaction | Observer thấy intermediate states | Lock/immutable aggregate/transaction |
| Đặt queue unbounded cho burst không kiểm soát | Memory pressure/OOM | Capacity + backpressure |
| Coi mọi concurrent collection hỗ trợ `null` | NPE/hợp đồng mơ hồ | Kiểm tra class contract |
| Không quản lý executor và timeout khi demo queue block | Thread treo khi không còn producer | Lifecycle/poison pill/interrupt/timeout |

## 21. Checklist trước khi chốt thiết kế

1. **Định nghĩa read/write ratio:** theo method calls, bytes, thời gian hay business events?
2. **Peak workload:** burst add/remove có phá giả định read-mostly không?
3. **Ordering:** cần key sorted, insertion order, FIFO, priority, hay output completion order?
4. **Consistency:** chấp nhận weakly consistent hay cần snapshot cùng epoch?
5. **Point lookup vs full scan:** số reads rất cao nhưng mỗi read đắt không?
6. **Phần tử mutable:** collection có bảo vệ dữ liệu bên trong value không?
7. **Write atomicity:** chỉ một key hay invariant nhiều key/collection?
8. **Capacity/backpressure:** có thể chấp nhận backlog tăng không?
9. **Blocking policy:** chờ, timeout, drop hay reject khi queue đầy?
10. **Số producers/consumers:** concurrency cao có gây lock contention không?
11. **Priority starvation:** low priority có cơ chế aging không?
12. **Fairness:** cần giảm starvation của thread chờ hơn là tối đa throughput?
13. **Cancel/shutdown:** mọi blocking consumer có đường kết thúc không?
14. **Null semantics:** collection có cho null không? `poll()==null` dùng để báo empty?
15. **Key consistency:** comparator/equals/hashCode có ổn định và đúng domain identity?
16. **Versioning:** cần publish immutable snapshot đồng bộ nhiều field không?
17. **Memory:** allocation/GC/backlog khi write burst?
18. **Benchmark:** có baseline tuần tự và kiểm tra correctness?
19. **Mục tiêu tối ưu:** throughput, p95 latency, memory hay fairness? Không phải lúc nào cùng tối ưu.
20. **Operations contract:** API có cung cấp atomic compound method phù hợp?
21. **Ordered output:** nếu có nhiều consumers, reorder/commit policy nằm ở đâu?
22. **Validation:** đã thử đồng thời writers và readers, edge cases, timeout và shutdown chưa?

## 22. Câu hỏi tự kiểm tra và đáp án

1. `ConcurrentHashMap` có duyệt theo insertion order không? **Không**, không có ordering guarantee.
2. Khi cần `firstKey/ceilingKey/subMap` đồng thời với writes, nên xem class nào? **`ConcurrentSkipListMap`**.
3. Sorted by key có đồng nghĩa FIFO không? **Không**, một bên theo comparator, một bên theo enqueue order.
4. `CopyOnWriteArrayList.iterator()` có thấy item thêm sau lúc iterator được tạo không? **Không**, iterator dùng snapshot backing array.
5. Snapshot iterator có đóng băng field của mutable element không? **Không**, chỉ cấu trúc tham chiếu của list.
6. Một list đọc 99%, nhưng writer cập nhật 1 triệu phần tử bằng các `add` riêng, chắc chắn CopyOnWrite tốt nhất không? **Không**, write copies/GC có thể rất lớn.
7. `Collections.synchronizedList` tự đồng bộ toàn vòng for-each không? **Không**, phải giữ monitor wrapper đúng khi traverse.
8. `ConcurrentLinkedQueue` có `take()` không? **Không**, dùng `poll` và giao thức chờ/lifecycle riêng hoặc chọn BlockingQueue.
9. Queue FIFO có bảo đảm workers xử lý xong FIFO không? **Không**, khi có nhiều consumers.
10. `ArrayBlockingQueue` fair=true có sắp xếp item theo priority không? **Không**, fairness nói về truy cập của thread đang chờ.
11. `PriorityBlockingQueue` có capacity hữu hạn như ArrayBlockingQueue không? **Không**, cần admission control riêng.
12. Hai item có cùng comparator priority, có chắc lấy theo FIFO không? **Không**, tie order không được bảo đảm.
13. `PriorityBlockingQueue.iterator()` có sorted order không? **Không** được hứa như thứ tự `poll`.
14. `ConcurrentSkipListMap.subMap` có tạo snapshot bất biến không? **Không**, đó là một view theo range.
15. Weakly consistent iterator có là atomic snapshot không? **Không**.
16. Không có `ConcurrentModificationException` có chứng minh các updates được đọc cùng epoch không? **Không**.
17. `ConcurrentHashMap.merge` giúp sửa bug nào? **Atomic read-modify-write trên một key**, tránh get+put race.
18. Hai `compute` cập nhật key A và B có tự làm transaction không? **Không**.
19. `ConcurrentHashMap<String,ArrayList>` có tự bảo vệ add vào mỗi ArrayList không? **Không**.
20. Khi nhiều consumer tranh một item, nên claim bằng `isEmpty()` rồi `remove()` hay `poll()`? **`poll()`**.
21. `poll()==null` khi producer đang chạy có nghĩa stream đã kết thúc không? **Không**, chỉ trống tại thời điểm lấy.
22. `ConcurrentLinkedQueue.size()` có luôn O(1) và chính xác dưới writes không? **Không**, có thể duyệt và kết quả thay đổi.
23. Khi cần read snapshot nhiều field nhất quán cùng version, lựa chọn nào? **Publish immutable aggregate qua atomic reference/lock/transaction phù hợp**.
24. ConcurrentSkipListMap có cho `null` keys/values không? **Không**.
25. `CopyOnWriteArrayList` có cho phép `null` elements không? **Có**.
26. Tại sao LinkedBlockingQueue không capacity cấu hình có thể nguy hiểm? **Default rất lớn; backlog có thể làm cạn memory**.
27. Map cần LRU/TTL cache hoàn chỉnh, ConcurrentHashMap có tự eviction không? **Không**.
28. Vì sao nên đo write bursts thay vì chỉ read/write ratio trung bình? **Burst có thể tạo write-copy/lock/backlog spikes**.
29. Với priority bằng nhau và cần ổn định, phải làm gì? **Dùng sequence number làm tie-breaker, thiết kế assignment đúng điểm ordering**.
30. Mục tiêu tối ưu được ưu tiên là gì? **Dựa trên SLO: throughput, p99 latency, memory, fairness và correctness, không chỉ tên collection**.

## 23. Tổng kết

**Không chọn concurrent collection chỉ vì nó “thread-safe”.** Hãy đi từ yêu cầu:
- **Read-mostly List + snapshot iteration:** cân nhắc `CopyOnWriteArrayList` hoặc immutable snapshot publication.
- **Mixed/write-heavy Map không cần order:** `ConcurrentHashMap` với các thao tác atomic per-key.
- **Sorted/range key:** `ConcurrentSkipListMap` hoặc `ConcurrentSkipListSet`.
- **FIFO nonblocking handoff:** `ConcurrentLinkedQueue` nếu có admission control/lifecycle thích hợp.
- **FIFO blocking + capacity/backpressure:** `ArrayBlockingQueue` hoặc `LinkedBlockingQueue(capacity)`.
- **Priority:** `PriorityBlockingQueue` với comparator, tie-breaker và kiểm soát backlog ngoài.
- **Nhiều field cần snapshot cùng epoch:** immutable aggregate + atomic publication hoặc transaction.

Một read/write ratio chỉ là **điểm bắt đầu**. Ordering, atomicity, iteration consistency, boundedness, deadline, cancellation và nguyên tắc ownership mới quyết định đúng sai. Sau khi chọn ứng viên, hãy **kiểm tra hợp đồng Java 17, đo trên workload thực và xác minh invariant nghiệp vụ**.

## Tài liệu tham khảo Java SE 17

- [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic per-key operations và weakly consistent iteration, không ordering.
- [ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): sorted key views, navigation/range, weakly consistent.
- [ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html): sorted set concurrent.
- [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterator, read-mostly tradeoff.
- [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): FIFO nonblocking queue, weak consistency và chi phí `size()`.
- [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO, fairness.
- [LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): FIFO, optional capacity, blocking.
- [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): comparator ordering, unbounded và iterator order.
- [SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): direct handoff.
- [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)): manual synchronization for iteration.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): memory model và happens-before.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): benchmark Java có kiểm soát.
