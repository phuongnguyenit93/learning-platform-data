# Vì sao ArrayList và HashMap không an toàn khi truy cập chung?

`ArrayList` và `HashMap` thuộc nhóm collection quen thuộc nhất của Java. Chúng phù hợp để quản lý dữ liệu trong một thread, hoặc khi **ứng dụng tự bảo vệ mọi truy cập chia sẻ bằng một giao thức đồng bộ đúng**. Nhưng nếu nhiều thread đồng thời đọc/ghi một instance mà không phối hợp, chúng **không cung cấp thread safety**: có thể mất cập nhật, quan sát dữ liệu không nhất quán, gặp exception, nhận kết quả sai hoặc phá vỡ những giả định về vòng đời dữ liệu.

Không có nghĩa “cứ hai thread cùng dùng `ArrayList`/`HashMap` là lập tức lỗi”. Nếu collection được **khởi tạo xong, công bố an toàn, rồi chỉ đọc** mà không có thread nào mutate, nhiều reader có thể sử dụng nó. Rủi ro chủ yếu xuất hiện khi có **mutable shared state** và giao thức đồng bộ không đáp ứng được cả ba điều kiện: **atomicity, visibility và ordering**.

Bài giải thích cụ thể những cấu trúc nội bộ dễ gặp race, tại sao `volatile` không sửa được chúng, khác biệt giữa “một method thread-safe” và “một workflow atomic”, cách tạo test có interleaving xác định và cách chọn `Collections.synchronizedList/Map`, `CopyOnWriteArrayList`, `ConcurrentHashMap`, immutable collection hoặc ownership.

Phạm vi: **Java concurrency nói chung**, Java 17+, không phụ thuộc Spring hoặc framework.

## 1. Thread-safe là gì trong ngữ cảnh collection?

Một collection thread-safe cần có **hợp đồng rõ ràng** cho các thao tác concurrent: những thao tác nào được phép gọi, tính nguyên tử của từng thao tác, người đọc quan sát giá trị bằng cơ chế memory-consistency nào, iterator thấy dữ liệu như thế nào, và compound operations có cần khóa bên ngoài không.

Một số tiêu chí kiểm tra:

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Atomicity** | Hai thread cùng `add`/`put` có làm mất tác vụ hoặc ghi đè một cập nhật không? |
| **Visibility** | Thread đọc có quan sát được state đã được thread khác công bố theo Java Memory Model không? |
| **Ordering** | Có happens-before giữa cập nhật và việc đọc dựa vào cập nhật đó không? |
| **Structural invariants** | `size`, backing array, buckets, links, resize state có còn nhất quán khi nhiều writers thao tác không? |
| **Compound atomicity** | `contains` rồi `add`, hoặc `get` rồi `put`, có là một quyết định atomic không? |
| **Iteration semantics** | Iterator là fail-fast, snapshot, weakly consistent hay được bảo vệ bởi cùng lock? |
| **Lifecycle/ownership** | Ai được phép mutate, khi nào collection được publish và lúc nào kết thúc sử dụng? |

**Thread-safe không có nghĩa mọi chuỗi method call đều atomic.** Ví dụ một map có `get` và `put` thread-safe riêng lẻ vẫn có thể mắc lỗi nghiệp vụ khi code viết `get`, tính giá trị mới, rồi `put`. Cả chuỗi read–modify–write phải được đồng bộ hoặc thay bằng một operation atomic phù hợp.

## 2. Cấu trúc bên trong `ArrayList` vì sao dễ race?

`ArrayList<E>` về mặt khái niệm lưu dữ liệu trong **mảng nền** và duy trì thông tin số phần tử hiện có. Khi `add(E)`, nó cần phối hợp ít nhất các việc:

1. Xác định vị trí tiếp theo từ `size`.
2. Nếu cần, mở rộng hoặc thay backing array.
3. Ghi phần tử vào mảng tại vị trí mới.
4. Cập nhật `size` và thông tin structural modification phục vụ iterator.

Các bước đó **không được bảo vệ bằng mutual exclusion** trong một `ArrayList` thông thường. Nếu thread A và B cùng gọi `add`:

```text
Ban đầu: size = 0

Thread A                       Thread B
--------------------------     --------------------------
đọc size = 0                   đọc size = 0
chọn vị trí 0                  chọn vị trí 0
ghi phần tử A ở vị trí 0       ghi phần tử B ở vị trí 0
cập nhật size                  cập nhật size

Kết quả có thể không chứa đầy đủ cả A và B.
```

Đây là **một interleaving để giải thích**, không phải một lịch duy nhất hoặc pseudocode chính xác từng bytecode của mọi phiên bản JDK. Các triệu chứng có thể gồm **mất phần tử, sai kích thước, ô null bất ngờ, exception** hoặc những kết quả khó lặp. Khi đồng thời tăng capacity, các writers còn có thể tranh chấp việc thay mảng nền.

Một số điểm quan trọng:

- `new ArrayList<>(1000)` chỉ đặt **capacity dự kiến**, không biến các lệnh `add` thành thread-safe.
- `Collections.synchronizedList(...)` bao bọc các method bằng synchronization, nhưng **vẫn cần lock ngoài** cho nhiều thao tác kết hợp hoặc vòng lặp qua iterator.
- `ArrayList.set(index, value)` không làm mọi cách truy cập đồng thời an toàn; phải phân tích index ownership, không có structural mutation, publication và visibility. Không lấy trường hợp mỗi thread ghi ô riêng làm bằng chứng `ArrayList` nói chung thread-safe.
- Một biến reference kiểu `volatile List<T>` chỉ bảo đảm semantics của **reference**, không tự đồng bộ các field bên trong `ArrayList`.

### `size()` có thể là nguồn sự thật khi concurrent writes không?

Không nên. Nếu các thread mutate `ArrayList` mà không có happens-before hoặc mutual exclusion, việc đọc `size()` ở thread khác không bảo đảm phản ánh một snapshot hợp lệ. Ví dụ “thấy size=5” không chứng minh năm phần tử tương ứng đã được công bố và đọc một cách an toàn trong một giao thức không đồng bộ.

## 3. Cấu trúc bên trong `HashMap` vì sao không an toàn?

`HashMap<K,V>` quản lý một bảng buckets. Tùy hash và kích thước, các entries trong bucket có thể ở cấu trúc liên kết hoặc cây; khi số entries vượt ngưỡng, map có thể **resize** và phân phối lại entries sang table mới. `put` cần phối hợp việc tìm key, cập nhật hoặc thêm node, thay bucket links và cập nhật các thống kê như `size`.

Khi nhiều threads cùng `put`, `remove`, `compute` hoặc mutate state mà không có synchronization:

- Hai lần thêm khác key có thể cùng thay đổi cấu trúc hoặc cùng trigger resize.
- Một lần `put` có thể đè giá trị được tính từ snapshot cũ của một thread khác.
- Reader có thể không quan sát được cập nhật đúng cách do thiếu happens-before.
- Iteration trên structure đang bị thay đổi có thể phát sinh `ConcurrentModificationException` hoặc nhìn thấy dữ liệu không nhất quán; exception không được bảo đảm xuất hiện.
- Nội bộ buckets/links/size có thể bị cập nhật với các interleavings không thuộc hợp đồng an toàn của map.

**Không dùng `HashMap` cho concurrent structural mutations chỉ vì “key nào cũng khác nhau”.** Mutations khác key vẫn có thể cùng động tới table, resize, size và bucket metadata. Ngay cả khi table đủ capacity, Java API vẫn không cam kết an toàn cho nhiều writers không đồng bộ.

### Lưu ý về những câu chuyện “HashMap vô hạn vòng lặp”

Một số ví dụ nổi tiếng trong tài liệu cũ mô tả tình huống cấu trúc liên kết bị rối khi nhiều threads cùng resize một `HashMap` ở các phiên bản JDK cũ. Đây là ví dụ lịch sử, **không nên tuyên bố mọi JDK 17 sẽ nhất định bị vòng lặp vô hạn**. Kết luận đáng tin cậy hơn: `HashMap` **không có hợp đồng concurrent writes**, nên kết quả không được bảo đảm. Dựa vào tài liệu và synchronization đúng thay vì trông chờ một biểu hiện hỏng cụ thể.

## 4. Hai nhóm lỗi cần tách riêng

### 4.1. Data race / unsafe structural mutation

Ví dụ hai threads cùng gọi `ArrayList.add` lên một list chưa được bảo vệ, hoặc một thread `HashMap.put` trong khi thread khác đọc/duyệt map. Những method không được thiết kế cho concurrent access có thể đọc/ghi cùng mutable fields mà thiếu synchronization.

Hậu quả không chỉ là sai “business logic”; dữ liệu nội bộ của collection và khả năng hiển thị cập nhật đều có thể trở nên không nhất quán theo Java Memory Model.

### 4.2. Check–then–act / read–modify–write không nguyên tử

Ngay cả khi từng method **được khóa riêng**, workflow sau vẫn sai nếu muốn chỉ thêm duy nhất một giá trị:

```java
if (!list.contains("job-A")) {
    list.add("job-A");
}
```

Snippet này không độc lập; `list` là danh sách được chia sẻ. Hai threads có thể đều thấy chưa có `job-A`, sau đó cả hai cùng thêm. Nếu dùng `Collections.synchronizedList` nhưng không bọc toàn bộ `contains + add` trong **một khóa chung**, lỗi logic vẫn xảy ra.

Với map:

```java
Integer old = map.get("hits");
map.put("hits", old == null ? 1 : old + 1);
```

Đây cũng là snippet. Hai threads có thể cùng thấy `old=0`, rồi cả hai put `1`: **lost update**. Dùng `Collections.synchronizedMap` và gọi từng method riêng vẫn chưa làm cả chuỗi atomic.

**Phân biệt hai tầng lỗi:** “Collection tự bảo vệ internal state” và “Toàn bộ business operation bảo toàn invariant” là hai câu hỏi khác nhau. `ConcurrentHashMap` giải quyết rất nhiều nhu cầu đồng thời ở tầng collection, nhưng một workflow phức tạp gồm nhiều keys/resources vẫn cần thiết kế atomicity tổng thể.

## 5. Java 17: test điều phối để thấy check–then–act sai

Nhiều bài demo thử “chạy hai threads thật nhanh” rồi hy vọng lost update. Cách đó dễ flaky. Ví dụ sau cố tình cho hai threads **đọc snapshot cũ trước**, rồi **ghi lần lượt** theo latches. Điều này tạo kết quả sai **có thể dự đoán**, đồng thời không cố kích hoạt corruption nội bộ bằng concurrent structural writes.

Tạo tệp **`CheckThenActTrapDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CheckThenActTrapDemo {
    public static void main(String[] args) throws Exception {
        List<String> names = new ArrayList<>();
        Map<String, Integer> counts = new HashMap<>();

        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch firstWritten = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<Void> first = () -> {
            boolean absent = !names.contains("A");
            int old = counts.getOrDefault("hits", 0);
            bothRead.countDown();
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Read rendezvous failed");
            }

            try {
                if (absent) names.add("A");
                counts.put("hits", old + 1);
            } finally {
                firstWritten.countDown();
            }
            return null;
        };

        Callable<Void> second = () -> {
            boolean absent = !names.contains("A");
            int old = counts.getOrDefault("hits", 0);
            bothRead.countDown();
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Read rendezvous failed");
            }

            if (!firstWritten.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First write missing");
            }
            if (absent) names.add("A");
            counts.put("hits", old + 1);
            return null;
        };

        try {
            Future<Void> a = pool.submit(first);
            Future<Void> b = pool.submit(second);
            a.get(5, TimeUnit.SECONDS);
            b.get(5, TimeUnit.SECONDS);

            System.out.println("listCount=" + names.size());
            System.out.println("mapCount=" + counts.get("hits"));
            System.out.println("expectedMapCount=2");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac CheckThenActTrapDemo.java
java CheckThenActTrapDemo
```

Stdout khi cả hai worker hoàn thành trong deadline:

```text
listCount=2
mapCount=1
expectedMapCount=2
```

**Cách chứng minh output:**

1. `bothRead` buộc A và B **đều đọc** list rỗng, map chưa có key `hits` trước khi có writer nào được tiếp tục.
2. Worker thứ nhất thêm `"A"` và ghi `hits=1`.
3. `firstWritten` bảo đảm worker thứ hai **chỉ ghi sau** khi worker thứ nhất đã làm xong writes.
4. B vẫn dùng **snapshot cũ**: `absent=true`, `old=0`. Nó thêm một `"A"` nữa và ghi đè `hits=1`.
5. Hai business actions nhưng map còn `1`, list có hai phần tử trùng nhau. Giao thức latches làm kết quả xác định mà không cần `Thread.sleep`.

**Phân tích chính xác giới hạn của thí nghiệm:** Hai threads thực hiện **reads trước writes**, và các **writes được tuần tự hóa** bởi latch. Vì vậy ví dụ này chủ động minh họa **compound check–then–act không nguyên tử**, **không phải** một bằng chứng rằng cấu trúc bên trong `ArrayList` hoặc `HashMap` đã bị corruption do hai writers đồng thời. Để kiểm tra unsafe concurrent structural writes cần stress/lincheck/JMM reasoning riêng; không dùng một kết quả “may mắn đúng” để hợp thức hóa code không thread-safe.

## 6. Cách sửa 1: dùng một khóa cho toàn bộ workflow

Nếu collection thường được chia sẻ cho nhiều threads, có thể dùng **intrinsic monitor** bảo vệ tất cả reads/writes liên quan.

```java
private final Object lock = new Object();
private final List<String> names = new ArrayList<>();

boolean addIfAbsent(String name) {
    synchronized (lock) {
        if (names.contains(name)) {
            return false;
        }
        names.add(name);
        return true;
    }
}
```

Đây là snippet trong một class, cần import `List`/`ArrayList`. Khi mọi code đọc/ghi list đều dùng **cùng lock**, hai threads không thể đồng thời quyết định `name` chưa tồn tại. Phép `contains + add` trở thành một critical section.

Map counter tương tự:

```java
private final Object lock = new Object();
private final Map<String, Integer> counts = new HashMap<>();

int increment(String key) {
    synchronized (lock) {
        int next = counts.getOrDefault(key, 0) + 1;
        counts.put(key, next);
        return next;
    }
}
```

Đây là snippet trong class khác hoặc phần class phù hợp; không khai báo lại các field cùng tên trong một class. **Tất cả paths** đọc/ghi state phục vụ invariant phải theo protocol lock: nếu một thread lén gọi `counts.put` không khóa, bảo đảm bị phá.

### Lock granularity

Một khóa chung đơn giản, dễ chứng minh correctness, nhưng có thể gây contention nếu rất nhiều threads cập nhật **những keys độc lập**. Khi đó `ConcurrentHashMap` thường là lựa chọn tốt. Tuy nhiên nếu invariant trải trên **hai hoặc nhiều collections** (ví dụ ghi order và trừ quota), một lock hoặc transaction có phạm vi đủ lớn vẫn có thể cần thiết.

**Không giữ lock khi làm I/O dài, gọi callback không đáng tin hoặc `Future.get`** nếu không có lý do; điều đó có thể tạo deadlock và tail latency. Hãy tách phần tính toán/side effect sao cho invariant vẫn đúng.

## 7. Cách sửa 2: `Collections.synchronizedList` và `synchronizedMap`

JDK có các wrapper:

```java
List<String> names =
        java.util.Collections.synchronizedList(
                new java.util.ArrayList<>());

Map<String, Integer> counts =
        java.util.Collections.synchronizedMap(
                new java.util.HashMap<>());
```

Các phương thức collection được wrapper đồng bộ theo hợp đồng. Đối với các operation đơn lẻ như `add/get/put` qua wrapper, đây là cách đơn giản để bảo vệ state nội bộ.

**Nhưng:** synchronization của từng call **không tự động gộp** một cặp method thành transaction:

```java
if (!names.contains("A")) {
    names.add("A");
}
```

Dù `names` ở đây là synchronized wrapper, hai threads vẫn có thể xen vào giữa `contains` và `add`. Để atomic:

```java
synchronized (names) {
    if (!names.contains("A")) {
        names.add("A");
    }
}
```

Với map:

```java
synchronized (counts) {
    int old = counts.getOrDefault("hits", 0);
    counts.put("hits", old + 1);
}
```

**Điều kiện:** mọi caller phải sử dụng **chính wrapper** và khóa tương ứng. Nếu còn giữ reference tới `new ArrayList<>()`/`new HashMap<>()` gốc rồi mutate qua reference đó, wrapper không thể bảo vệ những paths đi vòng.

### Iteration của synchronized wrapper vẫn cần khóa ngoài

Theo JDK documentation của synchronized collection wrappers, khi duyệt bằng `Iterator`/`Spliterator` hoặc stream, caller phải manually synchronize trên wrapper trong suốt traversal:

```java
synchronized (names) {
    for (String name : names) {
        consume(name);
    }
}
```

Đây là snippet với `consume` là method của ứng dụng. Tương tự:

```java
synchronized (counts) {
    for (Map.Entry<String, Integer> e
            : counts.entrySet()) {
        inspect(e);
    }
}
```

Đây là snippet, `inspect` do ứng dụng định nghĩa. Chỉ gọi `names.iterator()` trong synchronized rồi ra ngoài mới `next()` là **chưa đủ** nếu writers có thể mutate giữa các bước.

Nếu callback trong iteration đắt hoặc blocking, có thể **copy snapshot dưới lock** rồi iterate ngoài lock. Snapshot chỉ chụp references/values tại một thời điểm; nếu elements mutable và bị sửa sau đó, cần thêm immutable value/ownership.

## 8. Cách sửa 3: `ConcurrentHashMap` và atomic map operations

`ConcurrentHashMap<K,V>` được thiết kế cho concurrent access. Nó cho phép nhiều reads và updates theo contract, không dùng một global monitor cho mọi operation như synchronized wrapper ở nhiều trường hợp. Nó có những operation như:

- `putIfAbsent(key, value)`: chỉ đặt nếu key chưa có, theo một update atomic phù hợp.
- `computeIfAbsent(key, mappingFunction)`: tính value nếu key chưa mapped và cập nhật theo contract atomic.
- `compute(key, remappingFunction)`: tính lại value dựa trên mapping hiện hành cho key đó.
- `merge(key, value, remappingFunction)`: kết hợp một giá trị mới với giá trị hiện tại một cách atomic trên mapping được xử lý.
- `replace(key, oldValue, newValue)`: CAS-like conditional replacement cho mapping.
- `remove(key, value)`: chỉ xóa nếu còn mapped tới value mong đợi.

Thay vì:

```java
Integer old = concurrentMap.get("hits");
concurrentMap.put("hits", old == null ? 1 : old + 1);
```

vẫn có **lost update logic** vì hai thao tác atomic riêng biệt không thành một transaction, hãy dùng:

```java
concurrentMap.merge("hits", 1, Integer::sum);
```

Đây là snippet, `concurrentMap` là `ConcurrentHashMap<String,Integer>`. `merge` bảo vệ operation cập nhật mapping ở key đó. Với cùng một key, hai calls `merge("hits",1,Integer::sum)` hợp lệ sẽ cho tổng tăng hai lần thay vì cùng ghi đè snapshot.

**Không suy ra `ConcurrentHashMap` giải quyết mọi invariant nhiều keys.** Ví dụ kiểm tra `mapA` còn quota rồi ghi `mapB` ở một map khác không trở thành atomic chỉ nhờ hai maps đều là concurrent maps. Cần lock, transaction, state machine hoặc mô hình ownership cho toàn workflow.

### Một số giới hạn quan trọng

- `ConcurrentHashMap` không cho phép **null keys/values**, khác `HashMap`. Code dùng `map.get(key)==null` để phân biệt absent và “mapped to null” phải điều chỉnh.
- Iterator/view thường **weakly consistent**, có thể quan sát một phần cập nhật diễn ra trong lúc duyệt; nó không phải snapshot toàn map được đóng băng.
- Mapping/remapping function của `compute/merge` nên **ngắn, thuần về mặt business effect và không blocking lâu**. Trong một số tình huống, other updates có thể bị ảnh hưởng trong lúc computation diễn ra; không gọi lại chính map theo cách recursive có nguy cơ bị cấm hoặc deadlock.
- Method có suffix `computeIfAbsent` không phải nơi thích hợp để gửi email/charge payment với giả định exactly-once toàn hệ thống; lỗi process/network và vòng đời dữ liệu vẫn cần thiết kế.
- Compound operations trên nhiều entries vẫn không có atomic snapshot mặc định.

### `putIfAbsent` khác `containsKey` rồi `put`

```java
String old = concurrentMap.putIfAbsent("id-7", "reserved");
if (old == null) {
    // Thread này đã đặt mapping mới khi key trước đó absent.
}
```

Đây là snippet; giả định `concurrentMap` có type `ConcurrentHashMap<String,String>`. So với `containsKey + put`, method này có atomicity đúng cho **một key**. Nhưng khi “đặt chỗ” còn phải ghi DB, trừ quota, thanh toán và gửi email, việc map nhận key mới **không** chứng minh toàn bộ nghiệp vụ đã commit.

## 9. Cách sửa 4: `CopyOnWriteArrayList` cho read-mostly

`CopyOnWriteArrayList<E>` phù hợp với nhiều readers và số lần thêm/xóa thấp. Mỗi structural write tạo một backing array mới theo thiết kế copy-on-write; reader và iterator có thể quan sát **snapshot** đã tồn tại ở thời điểm tạo iterator.

Ưu điểm:
- Traversal không ném `ConcurrentModificationException` theo kiểu iterator fail-fast của `ArrayList`.
- Iteration không yêu cầu giữ global monitor bao quanh toàn bộ vòng đọc.
- Hữu ích cho danh sách listeners/configurations nhỏ, ít thay đổi.

Nhược điểm:
- `add/remove` tốn chi phí copy array và allocation, không phù hợp write-heavy hoặc list quá lớn.
- Iterator snapshot **không tự thấy** elements được thêm sau khi iterator được tạo.
- Elements mutable bên trong list **không tự trở nên immutable/thread-safe**.
- Một check–then–act dùng hai methods vẫn không mặc nhiên atomic. `CopyOnWriteArrayList.addIfAbsent` là operation riêng có nghĩa phù hợp hơn nếu mục tiêu là thêm value tối đa một lần.

Ví dụ:

```java
CopyOnWriteArrayList<String> listeners =
        new CopyOnWriteArrayList<>();

listeners.addIfAbsent("listener-A");
listeners.addIfAbsent("listener-A");
// Chỉ một element "listener-A" sau hai calls tuần tự.
```

Đây là snippet, cần import `java.util.concurrent.CopyOnWriteArrayList`. Nếu cần bảo đảm uniqueness theo **business key** trên các objects có semantics khác, phải phân tích `equals` và lựa chọn structure/operation phù hợp.

## 10. Java 17: giải pháp đồng thời và iterator snapshot

Chương trình sau chạy hai producers, mỗi worker cập nhật `ConcurrentHashMap.merge` và `Collections.synchronizedList.add` 500 lần. Main chỉ đọc kết quả sau khi `Future.get` xác nhận cả hai đã xong. Nó cũng minh họa iterator snapshot của `CopyOnWriteArrayList`.

Tạo **`ConcurrentCollectionsFixDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ConcurrentCollectionsFixDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        List<Integer> values =
                Collections.synchronizedList(new ArrayList<>());

        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<Void> worker = () -> {
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate failed");
            }
            for (int i = 0; i < 500; i++) {
                counts.merge("hits", 1, Integer::sum);
                values.add(i);
            }
            return null;
        };

        try {
            Future<Void> a = pool.submit(worker);
            Future<Void> b = pool.submit(worker);
            start.countDown();
            a.get(5, TimeUnit.SECONDS);
            b.get(5, TimeUnit.SECONDS);

            long sum = 0;
            synchronized (values) {
                for (int value : values) {
                    sum += value;
                }
            }

            CopyOnWriteArrayList<String> copyOnWrite =
                    new CopyOnWriteArrayList<>();
            copyOnWrite.add("before");
            Iterator<String> snapshot = copyOnWrite.iterator();
            copyOnWrite.add("after");

            System.out.println("mapCount=" + counts.get("hits"));
            System.out.println("listSize=" + values.size());
            System.out.println("listSum=" + sum);
            System.out.println("snapshotFirst=" + snapshot.next());
            System.out.println("snapshotHasNext=" + snapshot.hasNext());
            System.out.println("currentSize=" + copyOnWrite.size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy JDK 17+:

```bash
javac ConcurrentCollectionsFixDemo.java
java ConcurrentCollectionsFixDemo
```

Stdout bình thường:

```text
mapCount=1000
listSize=1000
listSum=249500
snapshotFirst=before
snapshotHasNext=false
currentSize=2
```

**Giải thích:**

- `ConcurrentHashMap.merge` bảo đảm hai threads không mất increment trên key `hits`.
- Wrapper `synchronizedList` bảo vệ từng `add`, nên list cuối có đủ 1.000 elements.
- Việc iterate được bao bởi `synchronized (values)`; khi hai workers đã hoàn thành, kết quả tổng mỗi dãy 0..499 được ghi hai lần: `2 × (499 × 500 / 2) = 249500`.
- Iterator copy-on-write được tạo **trước** khi thêm `"after"`, nên snapshot còn một element `"before"`, nhưng collection hiện tại có hai.
- `Future.get(5,SECONDS)` đặt deadline cho bài demo và propagate worker exceptions; code dùng `shutdownNow()` trong finally như cleanup pool. Deadline không hứa hủy mọi loại công việc blocking trong production.

**Đúng nhưng chưa phải tối ưu:** Với workload nhiều writes, `synchronizedList` có thể trở thành điểm contention, còn `CopyOnWriteArrayList` có chi phí sao chép. Chọn đúng collection theo pattern sử dụng, không áp một tên “concurrent” cho mọi tình huống.

## 11. `ConcurrentModificationException`: không phải “cơ chế bảo vệ thread”

Iterator của `ArrayList` và `HashMap` thường có behavior **fail-fast**: nếu cấu trúc collection được sửa ở ngoài iterator trong khi duyệt, nó có thể ném `ConcurrentModificationException`. Tuy nhiên tài liệu JDK nhấn mạnh không thể bảo đảm phát hiện tất cả concurrent modifications; fail-fast là cơ chế **best-effort để phát hiện bug**, không được dùng làm protocol correctness.

Một chương trình một thread cũng có thể ném exception:

Tạo **`FailFastIsNotSafetyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class FailFastIsNotSafetyDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("A");
        names.add("B");

        Iterator<String> iterator = names.iterator();
        names.add("C"); // Structural modification outside iterator.

        boolean detected = false;
        try {
            iterator.next();
        } catch (ConcurrentModificationException e) {
            detected = true;
        }

        System.out.println("detected=" + detected);
        System.out.println("size=" + names.size());
    }
}
```

Biên dịch/chạy:

```bash
javac FailFastIsNotSafetyDemo.java
java FailFastIsNotSafetyDemo
```

Stdout bình thường trên JDK 17 cho thứ tự này:

```text
detected=true
size=3
```

Ví dụ **không có hai threads** nhưng vẫn ném `ConcurrentModificationException` do structural modification sau khi iterator được tạo. Điều đó chứng minh tên exception **không đồng nghĩa có race giữa hai thread**.

Với mutation đồng thời thực sự, đôi khi sẽ ném exception, đôi khi không. **Không viết logic kiểu “nếu chưa thấy ConcurrentModificationException thì list an toàn”**. Bảo vệ traversal bằng cùng lock, dùng snapshot hoặc collection có iteration semantics phù hợp.

### Iterator của synchronized wrapper

`Collections.synchronizedList`/`synchronizedMap` bảo vệ methods nhưng iterator **không tự khóa cả vòng duyệt**. Phải synchronize thủ công trên wrapper khi lấy iterator và duyệt. Trong khi đó, `CopyOnWriteArrayList` có snapshot iterator; `ConcurrentHashMap` có weakly consistent iterator. Cả hai không có cùng semantics và không thể thay nhau tùy tiện nếu yêu cầu một snapshot logic duy nhất.

## 12. `volatile` có sửa được `ArrayList`/`HashMap` không?

Ví dụ:

```java
private volatile List<String> shared = new ArrayList<>();

void add(String value) {
    shared.add(value);
}
```

Đây là snippet trong class. `volatile` áp dụng cho **việc đọc/ghi reference `shared`**, không tự đặt monitor/CAS vào các thao tác `ArrayList.add`. Nếu hai threads cùng gọi `add`, chúng vẫn đang mutate **cùng object** với những field không được thiết kế concurrent.

Tương tự:

```java
private volatile Map<String, Integer> map = new HashMap<>();
```

không khiến `map.put` thread-safe.

### Khi volatile giúp được: publish snapshot, không mutate sau publish

Một thiết kế khác là:

```java
private volatile List<String> snapshot = List.of();

void replaceAllNames(List<String> source) {
    snapshot = List.copyOf(source);
}

List<String> readSnapshot() {
    return snapshot;
}
```

Đây là snippet trong class, dùng `java.util.List`. Ý tưởng là **tạo collection mới** rồi publish reference qua volatile; readers quan sát một list snapshot được tạo đầy đủ, không mutate list ấy. Tuy nhiên, nếu nhiều writers cùng thay snapshot dựa vào state cũ, cần lock/CAS để tránh **lost update giữa các snapshots**. Ngoài ra `List.copyOf` là **shallow immutability** đối với elements: nếu element là object mutable được chia sẻ, nó vẫn có thể bị mutate bên ngoài.

**Nhận xét:** immutable snapshot phù hợp với cấu hình/read-mostly; không phải thay thế cho concurrent updates từng phần tử ở workload write-heavy.

## 13. Read-only concurrent access có thể đúng khi nào?

Một `ArrayList`/`HashMap` **không bị mutate nữa** sau khi xây dựng có thể được nhiều threads chỉ đọc, với điều kiện object và dữ liệu liên quan được **safely published**.

Một số cơ chế publication có hợp đồng phù hợp:

- Khởi tạo trước `Thread.start()` rồi truyền reference an toàn tới các threads được start sau đó.
- Publish bằng `volatile` hoặc `AtomicReference`.
- Công bố dưới `synchronized`/`Lock` và readers đọc với cùng cơ chế.
- Truyền qua `BlockingQueue`/concurrent structures với memory-consistency contract phù hợp.
- Dùng immutable values/`List.of`/`Map.of` khi không cần mutate.

**Không có nghĩa “chỉ đọc thì khỏi nghĩ visibility”.** Nếu một thread tạo và mutate map rồi rò reference sang thread khác qua field thường không đồng bộ, reader có thể chưa thấy một trạng thái được công bố đúng.

### Immutable collection không tự làm immutable elements

`List.of(person1, person2)` không cho thêm/xóa/thay phần tử qua list API, nhưng nếu `person1` là object mutable được một thread khác sửa, dữ liệu bên trong vẫn có race. Immutable collection bảo vệ **cấu trúc collection**; data model bên trong vẫn phải tuân theo ownership/immutability/JMM.

### `Collections.unmodifiableList` không phải synchronized snapshot

`Collections.unmodifiableList(mutableList)` thường chỉ tạo **read-only view** của underlying list. Nếu một thread khác giữ `mutableList` và thay đổi nó, view có thể thấy updates và các vấn đề tương ứng. Đừng gọi một unmodifiable view của mutable shared state là “immutable thread-safe” khi dữ liệu nền còn bị mutate.

## 14. `HashMap.get` đồng thời với `HashMap.put` có an toàn?

Không có bảo đảm thread safety nếu thread A đang mutate map còn thread B `get` mà không đồng bộ. Dù B “chỉ đọc”, cùng object đang bị sửa nên có thể không thấy value mới hoặc quan sát không nhất quán theo JMM. Không nên dùng `HashMap` như một concurrent cache chỉ vì “cache miss thỉnh thoảng không sao”.

Giải pháp tùy contract:

- **Concurrent mutable cache:** dùng `ConcurrentHashMap` với API atomic `computeIfAbsent`, `putIfAbsent` khi cần.
- **Snapshot config/map hiếm thay đổi:** build map mới, immutable copy, publish an toàn bằng volatile/atomic reference.
- **Nhiều keys liên quan trong một transaction:** dùng lock chung hoặc state snapshot có invariant nhiều keys.
- **Cache có eviction, expiry, loading, capacity:** cân nhắc implementation cache chuyên dụng phù hợp; `ConcurrentHashMap` không tự cung cấp TTL, bounded memory hoặc exactly-once external load.

### Vì sao `getOrDefault + put` vẫn sai ngay cả với concurrent map?

`ConcurrentHashMap.getOrDefault` và `put` đều có semantics phù hợp khi gọi riêng, nhưng một thread vẫn có thể chen vào giữa chúng. Muốn tăng counter, dùng `merge` hoặc `compute` trên cùng key; muốn chỉ đăng ký nếu chưa có, dùng `putIfAbsent`. **Thread-safe method** không tự động nâng mọi business sequence lên atomicity.

## 15. HashMap key, hashCode và mutable keys

Ngay cả trong **một thread**, dùng object mutable làm key mà `equals/hashCode` thay đổi sau khi `put` có thể khiến `get` không còn tìm được mapping. Đây là bug **khác** với concurrency.

Trong nhiều threads, rủi ro lớn hơn: nếu các thread đồng thời mutate các fields ảnh hưởng `hashCode/equals` của key đang nằm map, việc tìm key và tính toán hash có thể không nhất quán. **ConcurrentHashMap không chữa mutable-key bug**. Hãy chọn immutable keys hoặc ngữ nghĩa khóa ổn định trong suốt thời gian key ở map.

Ví dụ minh họa:

```java
record Key(String region, long id) {}
```

Java 17 `record` với các components bất biến về reference/primitive là lựa chọn hợp lý cho key đơn giản. Nhưng record chứa mutable object vẫn có thể có rủi ro nếu thành phần đó bị sửa.

**Một nguyên tắc độc lập:** không mutate các state quyết định `equals/hashCode` của key sau khi thêm vào hash-based map.

## 16. Tối ưu lựa chọn collection theo workload

| Nhu cầu | Lựa chọn thường phù hợp | Điều phải hiểu |
| --- | --- | --- |
| Một thread sở hữu danh sách | `ArrayList` | Không cần chi phí concurrent abstraction |
| Nhiều readers sau khi xây dựng xong | Safely published immutable/snapshot | Không mutate sau publish, chú ý mutable elements |
| Nhiều threads mutate list, order/index | `Collections.synchronizedList` + lock protocol | Compound operations/iteration cần lock chung |
| Danh sách listeners nhỏ, rất ít writes | `CopyOnWriteArrayList` | Write copy tốn memory/CPU; iteration snapshot |
| Concurrent map nhiều keys độc lập | `ConcurrentHashMap` | Operations atomic theo key khi dùng đúng method |
| Map ít truy cập, dễ khóa toàn bộ | `Collections.synchronizedMap` | Tránh bỏ qua wrapper và compound atomicity |
| Ordered concurrent set/map | `ConcurrentSkipListMap/Set` khi cần ordering | Chi phí và semantics khác hash map |
| Counter theo key | `ConcurrentHashMap.merge/compute` | Tránh `get + put` |
| Nhiều writes vào cùng một hot counter | `AtomicLong`/`LongAdder` tùy semantics | LongAdder không phải atomic snapshot khi updates concurrent |
| Multi-object invariant mạnh | Shared lock/transaction/immutable aggregate CAS | Một atomic method trên một map chưa đủ |

**Đừng thay mọi `ArrayList` bằng `CopyOnWriteArrayList` và mọi `HashMap` bằng `ConcurrentHashMap` một cách máy móc.** Nếu instance chỉ dùng trong method của một worker và không escape, thread-safe collection không cần thiết. Nếu cần toàn bộ invariant giữa nhiều collections, riêng việc chọn tên collection cũng không đủ.

## 17. Đồng bộ theo một khóa: tại sao có thể vẫn deadlock?

Nếu dùng synchronized wrapper hoặc một shared monitor, phải bảo đảm lock order rõ. Ví dụ thread A giữ `lockA` rồi gọi vào code cần `lockB`, còn thread B giữ `lockB` rồi chờ `lockA`: có nguy cơ deadlock. Nếu giữ lock trong lúc gọi I/O dài, các threads khác bị trì hoãn.

Chính sách tốt:

1. Chỉ giữ lock khi đọc/sửa **đúng state cần bảo vệ**.
2. Giữ một **thứ tự lấy locks** nhất quán trên toàn ứng dụng khi cần nhiều locks.
3. Không gọi callback tùy ý hay tác vụ blocking trong critical section nếu tránh được.
4. Không expose backing collection mutable cho code bên ngoài đi vòng protocol.
5. Đóng gói access qua methods có invariant rõ ràng, thay vì giao toàn bộ list/map cho mọi nơi.
6. Khi dùng synchronization wrapper, khóa trên **wrapper chính nó** nếu contract iterator yêu cầu, không tự chọn một monitor khác ở caller.

Nếu code có nhiều readers, một `ReadWriteLock` có thể giúp trong vài workload nhưng **không luôn nhanh hơn** một monitor hoặc `ConcurrentHashMap`. Đo dưới tải thực.

## 18. Không dựa vào test stress đơn lẻ để chứng minh thread safety

Một test kiểu:

```java
List<Integer> list = new ArrayList<>();
for (int i = 0; i < 10_000; i++) {
    new Thread(() -> list.add(1)).start();
}
```

là **snippet sai để dùng trong code sản phẩm**: nó tạo quá nhiều threads, không đợi chúng hoàn tất, không định nghĩa shutdown và làm stress sai đối tượng. Có lần bạn sẽ thấy kết quả trùng kỳ vọng, có lần không; có thể OOM hoặc lỗi unrelated tới `ArrayList`.

Để kiểm thử có ích:

- **Định nghĩa invariant:** không mất job, không duplicate booking, count đúng, không phá thứ tự nếu contract yêu cầu.
- **Ép interleavings:** dùng `CountDownLatch`/`CyclicBarrier` đặt checkpoint trước read–modify–write, như `CheckThenActTrapDemo`.
- **Stress thực sự:** dùng số workers hữu hạn, `Future.get(timeout)`, kiểm tra kết quả/tính nhất quán, lặp nhiều lần nhưng không gọi “không lỗi” là proof.
- **Kiểm tra publication/JMM:** reason về happens-before và data races; một stress test trên một CPU/JDK không bao phủ mọi lịch.
- **Phân biệt test nội bộ với business logic:** check–then–act có thể sai ngay cả khi các structural writes được serialize; unsafe concurrent structural mutation có thể xảy ra ngoài test deterministic.
- **Dùng công cụ đúng:** JMH dành cho performance benchmark, không dùng kết quả benchmark để chứng minh thread safety; JCStress hoặc test điều phối hỗ trợ kiểm tra interleavings/memory effects, nhưng vẫn cần lý luận đúng contract.
- **Không chạy forever:** đặt timeout, cleanup executor, và báo exception workers về thread chính.

### Test không nên bắt `ConcurrentModificationException` làm dấu hiệu bắt buộc

Fail-fast chỉ best-effort; một mutation concurrent có thể không bị iterator phát hiện. Ngược lại CME cũng xuất hiện khi **cùng thread** mutate list trong lúc dùng iterator sai cách. Hãy assert invariant và đồng bộ đúng thay vì mong exception báo lỗi.

## 19. Ba nguyên tắc chính từ Java Memory Model

### 19.1. Mutual exclusion/atomicity

Một lock chung khiến cùng lúc chỉ một thread thực hiện critical section, hoặc một operation atomic (như `ConcurrentHashMap.merge`) cập nhật đúng key theo contract. Không có atomicity, hai writers có thể dựa trên snapshot cũ.

### 19.2. Visibility và happens-before

Nếu writer thay state rồi publish bằng volatile/atomic/lock hoặc concurrent queue, reader quan sát state theo happens-before phù hợp. Nếu không, một reader `HashMap.get` có thể không thấy state mới một cách đáng tin, và đọc `ArrayList.size` không đồng nghĩa có snapshot hợp lệ.

### 19.3. Ordering

Compiler, JIT và CPU có thể thực hiện các tối ưu theo Java Memory Model. Không dùng ý tưởng “trên máy tôi hai lệnh luôn chạy theo thứ tự nguồn” để suy ra thread khác thấy các field theo thứ tự đó mà không có đồng bộ hợp lệ.

Một reference `final` hoặc list/map container bất biến có thể hỗ trợ thiết kế, nhưng các yêu cầu safe publication và mutation ownership vẫn phải được phân tích cho từng object.

## 20. Những lỗi phổ biến

| Lỗi | Vì sao sai | Sửa bằng gì? |
| --- | --- | --- |
| Coi `ArrayList.add` là atomic trong multi-writer | `size`/backing array không được bảo vệ | Lock hoặc thread-safe collection |
| Coi `HashMap.put` an toàn vì keys khác nhau | Resize, table, size là shared structure | `ConcurrentHashMap` hoặc lock |
| `volatile List/Map` rồi mutate nội bộ | Volatile chỉ áp dụng cho reference access | Bảo vệ mutable object |
| `Collections.synchronizedList` rồi `contains + add` không khóa | Compound operation vẫn xen ngang | `synchronized(list)` bao toàn bộ |
| Iterator của synchronized wrapper không khóa | Lệnh `next` chạy trong lúc writer mutate | Khóa wrapper trong toàn bộ traversal |
| `ConcurrentHashMap.get + put` để tăng counter | Hai method riêng không gộp atomic | `merge`/`compute` |
| Dùng mutable key thay đổi `hashCode` | Mapping không còn tra cứu ổn định | Immutable/stable keys |
| Nghĩ `ConcurrentModificationException` luôn xuất hiện | Fail-fast best-effort | Không dựa vào exception cho correctness |
| Nghĩ không thấy CME thì an toàn | Data races có thể im lặng | Chọn đúng synchronization contract |
| Chỉ test `Thread.sleep` | Scheduling không xác định | Latch/barrier có deadline |
| Coi `ConcurrentHashMap` là transaction multi-key | Per-key update không bảo vệ toàn workflow | Lock/transaction/aggregate state |
| Nghĩ `CopyOnWriteArrayList` miễn phí | Writes copy toàn mảng | Chỉ dùng read-mostly |
| Dùng `List.copyOf` nhưng elements mutable | Immutability nông | Deep immutable/ownership |
| Dùng `Collections.unmodifiableList` trên list còn mutate | View không phải snapshot | Snapshot/immutable publication |
| Expose backing map qua getter | Caller có thể bypass protocol | Trả snapshot hoặc interface hẹp |
| Giữ lock khi gọi I/O/callback lâu | Contention/deadlock | Giảm critical section |
| Chọn collection “concurrent” là xong | Business invariant có thể nhiều steps | Thiết kế atomic workflow |
| Coi stress không lỗi là proof | Thiếu bao phủ mọi interleaving | Reason JMM + tests có chủ đích |

## 21. Câu hỏi tự kiểm tra

**1. Vì sao `new ArrayList<>(1000)` không an toàn khi hai threads `add`?** Capacity có sẵn không biến việc chọn index, ghi array và cập nhật size thành một atomic operation.

**2. Nếu hai threads `HashMap.put` vào hai keys khác nhau, có luôn an toàn không?** Không. Chúng vẫn mutate shared buckets/table/size và có thể cùng resize.

**3. Hai readers chỉ đọc một `HashMap` có an toàn không?** Có thể, nếu map đã được xây dựng và **công bố an toàn** rồi không bị mutate, cùng với dữ liệu elements được quản lý đúng.

**4. `volatile Map` có làm `map.put` thread-safe không?** Không. Volatile reference không bảo vệ mutable fields bên trong map.

**5. Vì sao `Collections.synchronizedList` vẫn có thể thêm duplicate?** `contains` và `add` là hai synchronized method calls tách biệt. Cần lock chung bao cả workflow hoặc API atomic phù hợp.

**6. `ConcurrentHashMap` có làm `get + put` tăng counter atomic không?** Không. Dùng `merge("hits",1,Integer::sum)` hoặc `compute`.

**7. Thấy `ConcurrentModificationException` có chắc có hai threads không?** Không. Cùng thread mutate ngoài iterator cũng có thể ném.

**8. Không thấy `ConcurrentModificationException` thì list/map an toàn?** Không. Fail-fast là best-effort và không phải safety mechanism.

**9. Iterator của `CopyOnWriteArrayList` có thấy element thêm sau khi tạo iterator không?** Không; nó duyệt snapshot của thời điểm tạo iterator.

**10. `ConcurrentHashMap` iterator có là transaction snapshot tuyệt đối không?** Không. Nó weakly consistent và có thể quan sát một phần updates khi đang iterate.

**11. `Collections.unmodifiableList` có phải immutable snapshot không?** Không nhất thiết. Nó có thể là view trên underlying mutable list.

**12. Khi nào `HashMap` vẫn hợp lý trong code concurrent?** Khi map chỉ thuộc một thread, hoặc immutable sau safe publication, hoặc mọi reads/writes mutable đều được bảo vệ bởi giao thức synchronization hợp lệ.

**13. Dùng `ConcurrentHashMap.putIfAbsent` có giúp tránh race đăng ký một key không?** Có đối với atomic mapping cho key, nhưng không tự tạo transaction gồm DB/payment/resource bên ngoài.

**14. Vì sao test hai threads với latches mà vẫn có thể sai logic ngay cả khi writes serialize?** Vì cả hai đã đọc cùng snapshot cũ trước khi lần write đầu xảy ra. Đây là check–then–act race, không cần concurrent writes cùng thời điểm.

**15. Muốn cập nhật nhiều keys cùng một invariant thì dùng gì?** Cần lock/transaction/immutable aggregate và state machine phù hợp; các atomic operations trên từng key không tự tạo atomic multi-key operation.

## 22. Checklist lựa chọn và triển khai

1. **Collection có bị share cho nhiều threads không?** Nếu không, dùng `ArrayList`/`HashMap` bình thường.
2. **Có mutation sau khi publish không?** Nếu không, dùng safely published immutable/read-only snapshot.
3. **Có nhiều concurrent writers không?** Chọn synchronization hoặc collection có đúng hợp đồng.
4. **Invariant chỉ liên quan một key hay nhiều keys?** `ConcurrentHashMap.merge/compute` phù hợp per-key, lock/transaction cho multi-state.
5. **List cần snapshot iteration hay cập nhật liên tục?** `CopyOnWriteArrayList` cho read-mostly; synchronized list cho patterns khác.
6. **Có compound check–then–act không?** Chọn atomic method hoặc khóa chung bao toàn bộ.
7. **Iteration qua wrapper có được khóa đầy đủ không?** `synchronized(wrapper)` khi cần.
8. **Có reference tới backing collection bị lộ ra ngoài không?** Ngăn bypass protocol.
9. **Elements/keys có mutable không?** Ổn định `equals/hashCode`, cân nhắc deep immutability.
10. **Có thời gian chờ/side effects trong critical section không?** Giảm hoặc tổ chức lại.
11. **Có test với latches và invariant không?** Không phụ thuộc may rủi của `Thread.sleep`.
12. **Có test failure/timeout/executor cleanup không?** Không bỏ worker sống mãi.
13. **Có đo contention, throughput và allocation trước khi tối ưu không?** Correctness đi trước.
14. **Có giải thích memory visibility và publication cho readers không?** Thread safety không chỉ là khóa writes.
15. **Có chọn đúng iteration semantics không?** Fail-fast khác weakly consistent và snapshot.

**Kết luận:** `ArrayList` và `HashMap` **không tự bảo vệ mutable internal state khi được nhiều threads đọc/ghi mà thiếu synchronization**. Lỗi có hai tầng: **data race/structural inconsistency** do mutations không an toàn, và **business check–then–act không nguyên tử** do ghép nhiều operations tách biệt. Cách chữa phải dựa vào invariant: dùng một lock chung, synchronized wrapper kèm external lock khi iterate/compound, `ConcurrentHashMap` với `merge/compute/putIfAbsent`, `CopyOnWriteArrayList` cho read-mostly, hoặc immutable snapshot được công bố an toàn. Quan trọng nhất là **thiết kế chính sách ownership và happens-before cho toàn workflow**, không chỉ đổi tên collection.