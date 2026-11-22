# Collections.synchronizedMap/List và yêu cầu khóa khi duyệt

## 1. Bài toán: collection thông thường không tự an toàn khi nhiều thread truy cập

`ArrayList` và `HashMap` được thiết kế chủ yếu cho truy cập thông thường. Nếu một thread sửa chúng trong khi thread khác đọc hoặc sửa mà không có cơ chế đồng bộ phù hợp, chương trình có thể gặp race condition, kết quả không nhất quán hoặc hành vi ngoài mong đợi. Không nên suy luận rằng chỉ vì một lời gọi `get()` hoặc `add()` nhìn đơn giản thì việc dùng cùng một collection từ nhiều thread là an toàn.

Java cung cấp các wrapper đồng bộ trong `java.util.Collections`:

```java
Map<String, Integer> map =
        Collections.synchronizedMap(new HashMap<>());

List<String> list =
        Collections.synchronizedList(new ArrayList<>());
```

Các phương thức trên tạo **wrapper** bao quanh collection gốc. Wrapper dùng một monitor chung để đồng bộ các thao tác do nó cung cấp, như `get`, `put`, `add`, `remove` hoặc `size`. Đây là lựa chọn hữu ích khi muốn sử dụng giao diện `Map`/`List` quen thuộc với một cơ chế khóa đơn giản.

Tuy nhiên, **mỗi lời gọi được đồng bộ không đồng nghĩa một chuỗi nhiều lời gọi là nguyên tử**. Và một điểm rất quan trọng: **khi duyệt bằng `Iterator`, enhanced `for`, `Spliterator` hoặc `Stream`, người dùng thường phải chủ động khóa wrapper trong toàn bộ thời gian duyệt**.

Bài học này tập trung vào Java Concurrency nói chung, không liên quan đến Spring.

## 2. Wrapper đồng bộ hoạt động như thế nào?

Ví dụ:

```java
List<String> raw = new ArrayList<>();
List<String> safe = Collections.synchronizedList(raw);
```

Ý tưởng là mọi truy cập chia sẻ tới dữ liệu phải đi qua `safe`. Phần triển khai của wrapper sử dụng khóa nội bộ nhất quán để bảo vệ các lời gọi của nó. Với wrapper trả về trực tiếp từ `Collections.synchronizedList(...)` hoặc `synchronizedMap(...)`, **khóa bên ngoài cần sử dụng chính đối tượng wrapper**:

```java
synchronized (safe) {
    // Nhiều thao tác liên quan được giữ dưới cùng monitor.
    safe.add("a");
    safe.add("b");
}
```

Đồng bộ kiểu này cung cấp các quan hệ *happens-before* khi thread nhả monitor và thread khác lấy cùng monitor. Nhờ đó, dữ liệu mà wrapper bảo vệ có thể được nhìn thấy đúng theo những quy tắc đồng bộ Java. Tuy nhiên:

- Wrapper **không tự bảo vệ** các truy cập đi thẳng qua `raw` nếu code khác vẫn giữ tham chiếu đến collection gốc.
- Wrapper không sửa được logic nhiều bước bị race nếu không khóa trọn chuỗi.
- Nó không làm một phần tử mutable bên trong collection trở nên thread-safe. Chẳng hạn, một `Person` có trường thay đổi vẫn cần cơ chế đồng bộ riêng cho trạng thái của `Person`.
- Nó không biến collection thành snapshot bất biến hay cho phép iterator duyệt an toàn trong lúc các thread khác sửa mà không có khóa.
- Tất cả thread muốn được bảo vệ bởi cùng hợp đồng phải thống nhất sử dụng đúng wrapper/monitor.

Để tránh đường truy cập không đồng bộ, nên tạo collection gốc và wrapper cùng lúc, rồi **chỉ công bố wrapper** cho các thread khác. Công bố tham chiếu an toàn cũng là một phần của thiết kế chia sẻ dữ liệu: dùng các cơ chế như khởi tạo trước khi start thread, trường `final` được xây dựng đúng hoặc giao nhận qua cấu trúc concurrent thích hợp.

## 3. Điều gì được bảo vệ bởi synchronizedMap và synchronizedList?

### Một lời gọi phương thức

```java
Map<String, Integer> counts =
        Collections.synchronizedMap(new HashMap<>());
counts.put("ok", 1);        // Một lời gọi được đồng bộ.
Integer value = counts.get("ok"); // Một lời gọi được đồng bộ.
```

Từng lời gọi ở trên được wrapper bảo vệ bằng monitor của nó. Tương tự, với `synchronizedList`, các thao tác `add`, `get`, `set`, `remove`, `size` thông thường được đồng bộ ở cấp phương thức.

Từ Java 8, các wrapper trong JDK cũng triển khai đồng bộ cho nhiều phương thức mặc định phù hợp, chẳng hạn `Map.computeIfAbsent`, `Map.merge`, `Map.forEach` hoặc `List.replaceAll`. Khi dùng một phương thức đơn lẻ, nên đọc hợp đồng chính xác của phương thức đó, thay vì tự gộp nó với nhiều lời gọi tách rời.

### Nhiều lời gọi liên tiếp

Ví dụ logic không an toàn về tính nguyên tử:

```java
if (!counts.containsKey("hits")) {
    counts.put("hits", 0);
}
counts.put("hits", counts.get("hits") + 1);
```

Đây là fragment minh họa. Mỗi bước `containsKey`, `get` và `put` có khóa riêng, nhưng **các thread khác có thể xen vào giữa chúng**. Đặc biệt, hai thread đều đọc cùng giá trị cũ và cùng ghi giá trị mới, gây mất lượt tăng.

Khi cần biến nhiều thao tác thành một đơn vị logic, đồng bộ **bao trọn chuỗi**:

```java
synchronized (counts) {
    counts.put("hits", counts.getOrDefault("hits", 0) + 1);
}
```

Lúc này các thread khác dùng cùng wrapper/monitor không thể chen vào giữa `getOrDefault` và `put`. Cần giữ phần nằm trong khóa đủ ngắn để tránh tăng thời gian chờ.

Một lựa chọn khác, khi bài toán thực sự là cập nhật theo khóa và cần đồng thời cao, là `ConcurrentHashMap` với `compute`, `merge` hoặc `AtomicInteger` đúng cách. Không phải lúc nào cần giữ `synchronizedMap`.

## 4. Quy tắc quan trọng nhất: phải khóa toàn bộ vòng duyệt

JDK quy định rõ: khi duyệt collection đồng bộ qua `Iterator`, `Spliterator` hoặc `Stream`, người dùng phải thực hiện thao tác duyệt trong khối `synchronized` trên wrapper phù hợp. Bởi vì việc tạo iterator hoặc lấy stream không làm cho **cả chuỗi bước duyệt** được khóa nguyên tử.

### 4.1. Duyệt synchronizedList

**Sai:**

```java
List<String> items =
        Collections.synchronizedList(new ArrayList<>());
items.add("A");
items.add("B");

for (String item : items) { // Không có khóa bao trọn traversal.
    System.out.println(item);
}
```

Vòng `for-each` thực chất gọi `iterator()` và nhiều bước `hasNext()`/`next()`. Một thread khác có thể sửa list giữa các bước. Việc mỗi lời gọi `items.add(...)` được đồng bộ **không bảo đảm** traversal không bị race.

**Đúng:**

```java
synchronized (items) {
    for (String item : items) {
        System.out.println(item);
    }
}
```

Trong thời gian vòng lặp chạy, các thread sửa list thông qua chính wrapper `items` phải chờ monitor được nhả. Đây là cách tạo một vùng quan sát nhất quán theo hợp đồng sử dụng chung monitor.

### 4.2. Duyệt synchronizedMap

**Sai:**

```java
Map<String, Integer> scores =
        Collections.synchronizedMap(new HashMap<>());
scores.put("A", 10);
scores.put("B", 20);

for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

**Đúng:**

```java
synchronized (scores) {
    for (Map.Entry<String, Integer> entry : scores.entrySet()) {
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
```

Với các view của map như `keySet()`, `entrySet()` và `values()`, khóa cần lấy là **map wrapper gốc**, tức `scores` trong ví dụ.

Không dùng `synchronized(scores.entrySet())` để thay thế. View được trả về có thể chia sẻ mutex nội bộ với map gốc, nhưng monitor của chính đối tượng view không nhất thiết là monitor đang bảo vệ những lời gọi trên wrapper. Hợp đồng API yêu cầu khóa `scores`.

### 4.3. Với Iterator, Spliterator và Stream

Áp dụng cùng nguyên tắc:

```java
synchronized (items) {
    Iterator<String> it = items.iterator();
    while (it.hasNext()) {
        String value = it.next();
        // Xử lý ngắn, không tạo side effect phức tạp.
        System.out.println(value);
    }
}
```

Và với stream:

```java
long count;
synchronized (items) {
    count = items.stream()
            .filter(s -> !s.isBlank())
            .count();
}
```

Chú ý: cần giữ khóa **đến khi terminal operation hoàn tất**, chứ không chỉ khóa khi tạo `stream()`. Với `parallelStream()`, việc giữ monitor ở thread gọi chưa tự bảo đảm an toàn cho callback chạy ở các worker khác nếu chúng truy cập trạng thái ngoài. Cân nhắc snapshot rồi mới xử lý song song, thay vì cố giữ khóa dài qua một pipeline phức tạp.

### 4.4. Vì sao fail-fast iterator không thay thế khóa?

Iterator của `ArrayList` và `HashMap` thông thường có cơ chế phát hiện sửa đổi cấu trúc để ném `ConcurrentModificationException` trong một số tình huống. Đây là **phát hiện lỗi theo best effort**, không phải cơ chế đồng bộ và không bảo đảm luôn ném exception nếu có race.

Điều sai lầm là viết:

```java
try {
    for (String item : items) {
        use(item);
    }
} catch (ConcurrentModificationException ignored) {
    // Không biến thao tác duyệt trở nên an toàn.
}
```

Đây là fragment, `use(...)` do ứng dụng định nghĩa. Việc bắt exception chỉ che giấu vấn đề. Giải pháp là khóa đúng hoặc đổi thiết kế collection/traversal. Ngay cả khi không thấy `ConcurrentModificationException`, kết quả duyệt không khóa vẫn có thể thiếu, lặp hoặc không nhất quán khi có sửa đổi đồng thời.

## 5. Chọn monitor nào khi duyệt view và subList?

Một lỗi tinh vi là khóa nhầm đối tượng được trả về từ method tạo view.

| Collection dùng để duyệt | Monitor cần khóa |
| --- | --- |
| `Collections.synchronizedList(list)` trực tiếp | Chính đối tượng synchronized-list wrapper |
| `list.subList(from, to)` trả từ synchronized-list | **List wrapper gốc** đã tạo sublist |
| `Collections.synchronizedMap(map)` trực tiếp | Chính synchronized-map wrapper |
| `map.keySet()` | **Map wrapper gốc** |
| `map.entrySet()` | **Map wrapper gốc** |
| `map.values()` | **Map wrapper gốc** |

Ví dụ:

```java
List<Integer> numbers = Collections.synchronizedList(
        new ArrayList<>(List.of(1, 2, 3, 4)));

List<Integer> tail = numbers.subList(2, 4);

synchronized (numbers) { // Khóa wrapper gốc, không phải tail.
    for (Integer n : tail) {
        System.out.println(n);
    }
}
```

View có liên hệ với collection gốc; thay đổi ở collection gốc có thể làm view thay đổi hoặc vô hiệu hóa sublist theo hợp đồng `List`. Không nên công bố view ra nhiều thread mà không kiểm soát rõ monitor và vòng đời.

Ví dụ map:

```java
Map<String, Integer> map =
        Collections.synchronizedMap(new HashMap<>());
Set<String> keys = map.keySet();

synchronized (map) {
    for (String key : keys) {
        System.out.println(key);
    }
}
```

Việc `keys` có thể là một synchronized view không làm thay đổi quy tắc khóa: **dùng `map`** cho toàn bộ traversal.

## 6. Ví dụ Java 17 chạy độc lập: lost update và duyệt đúng khóa

Chương trình này tạo một race **có điều khiển** bằng `CountDownLatch`. Hai task cùng đọc giá trị cũ trước khi được phép ghi; kết quả chắc chắn cho thấy mất một lượt tăng dù `get` và `put` đều là method synchronized. Sau đó chương trình chuyển sang khóa ngoài bao trọn thao tác đọc–sửa–ghi và kiểm tra được hai lượt tăng.

Nửa sau minh họa cách duyệt synchronized-list và synchronized-map với kết quả ổn định. Để không phụ thuộc thứ tự duyệt của `HashMap`, ta tạo snapshot bên trong khóa rồi sắp xếp snapshot sau khi nhả khóa.

Lưu tệp **`SynchronizedCollectionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SynchronizedCollectionsDemo {
    public static void main(String[] args) throws Exception {
        Map<String, Integer> counts =
                Collections.synchronizedMap(new HashMap<>());
        counts.put("hits", 0);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        try {
            Callable<Void> unsafeIncrement = () -> {
                int old = counts.get("hits");  // Riêng get() là an toàn.
                bothRead.countDown();
                mayWrite.await();             // Cả hai đã đọc old=0.
                counts.put("hits", old + 1);   // Riêng put() là an toàn.
                return null;
            };

            Future<Void> first = pool.submit(unsafeIncrement);
            Future<Void> second = pool.submit(unsafeIncrement);

            bothRead.await();
            mayWrite.countDown();
            first.get();
            second.get();
            System.out.println("Separate get/put = " + counts.get("hits"));

            counts.put("hits", 0);
            Callable<Void> safeIncrement = () -> {
                synchronized (counts) {
                    int old = counts.get("hits");
                    counts.put("hits", old + 1);
                }
                return null;
            };

            first = pool.submit(safeIncrement);
            second = pool.submit(safeIncrement);
            first.get();
            second.get();
            System.out.println("Atomic get/put = " + counts.get("hits"));
        } finally {
            mayWrite.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }

        List<String> words = Collections.synchronizedList(
                new ArrayList<>(List.of("beta", "alpha")));
        List<String> wordSnapshot = new ArrayList<>();

        synchronized (words) {
            for (String word : words) {
                wordSnapshot.add(word);
            }
        }
        Collections.sort(wordSnapshot);
        System.out.println("List snapshot = "
                + String.join(",", wordSnapshot));

        Map<String, Integer> scores =
                Collections.synchronizedMap(new HashMap<>());
        scores.put("b", 2);
        scores.put("a", 1);
        List<String> entries = new ArrayList<>();

        synchronized (scores) {
            for (Map.Entry<String, Integer> entry : scores.entrySet()) {
                entries.add(entry.getKey() + "=" + entry.getValue());
            }
        }
        Collections.sort(entries);
        System.out.println("Map snapshot = " + String.join(",", entries));
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac SynchronizedCollectionsDemo.java
java SynchronizedCollectionsDemo
```

Stdout xác định:

```text
Separate get/put = 1
Atomic get/put = 2
List snapshot = alpha,beta
Map snapshot = a=1,b=2
```

Giải thích:

- Trong thử nghiệm đầu, `bothRead` buộc **cả hai task đọc `0`** rồi mới được phép ghi. Do đó mỗi task đều ghi `1`; không có việc kết quả tình cờ là `2` vì một thread chạy hết trước.
- Ở thử nghiệm tiếp, mỗi task giữ monitor `counts` suốt thao tác lấy giá trị cũ và ghi giá trị mới. Không thread nào có thể chen giữa hai bước, nên kết quả là `2`.
- List và Map đều tạo snapshot trong khối `synchronized` rồi sắp xếp/in snapshot sau khi nhả khóa. Như vậy code bên ngoài khóa không giữ monitor lâu và kết quả in không lệ thuộc thứ tự của `HashMap`.
- Hai lần `Future.get()` khiến main chờ task xong, đồng thời phát hiện exception nếu task gặp lỗi. `shutdown()` ngừng pool nhận task mới; `awaitTermination` dùng để kết thúc gọn trong demo.

Đây là ví dụ giáo dục có `CountDownLatch` chủ động tạo tình huống race. Trong ứng dụng thực tế, ta không dùng latch để làm chậm mọi lần tăng biến; ví dụ chỉ cho thấy **method-level synchronization khác transaction-level synchronization**.

## 7. Snapshot: giảm thời gian giữ khóa và tránh duyệt trên collection đang đổi

Nếu thao tác duyệt có nhiều việc chậm (ghi file, gọi dịch vụ ngoài, tính toán tốn CPU), giữ khóa xuyên suốt có thể khiến tất cả thread muốn sửa collection bị chặn. Khi cần xem một ảnh chụp nhất quán tại một thời điểm, tạo bản sao **trong khi giữ khóa**, rồi xử lý bản sao bên ngoài:

```java
List<String> snapshot;
synchronized (items) {
    snapshot = new ArrayList<>(items);
}

for (String value : snapshot) {
    slowOperation(value);
}
```

Fragment này giả định `items` là synchronized-list wrapper và `slowOperation` do ứng dụng định nghĩa. Tác dụng: khóa chỉ được giữ trong lúc sao chép cấu trúc list. Tuy nhiên **snapshot này là shallow copy**: nếu phần tử là object mutable, các đối tượng phần tử vẫn có thể bị sửa bởi thread khác. Muốn ảnh chụp dữ liệu bất biến thực sự, cần sao chép/đóng băng phần tử hoặc thiết kế immutable phù hợp.

Tương tự với map:

```java
Map<String, Integer> snapshot;
synchronized (scores) {
    snapshot = new HashMap<>(scores);
}
for (Map.Entry<String, Integer> entry : snapshot.entrySet()) {
    slowOperation(entry);
}
```

Bản sao map sau khi nhả khóa không tự cập nhật khi `scores` thay đổi. Đây thường là điều mong muốn cho báo cáo hoặc xử lý nhất quán theo một thời điểm, nhưng cần chấp nhận dữ liệu có thể cũ ngay sau snapshot.

### So sánh thời gian giữ khóa

| Chiến lược | Tính nhất quán | Ảnh hưởng producer |
| --- | --- | --- |
| Duyệt trực tiếp trong `synchronized(list)` | Không thread tuân thủ monitor chen vào sửa trong lúc duyệt | Thread sửa/đọc qua wrapper có thể chờ đến hết traversal |
| Tạo snapshot trong khóa, xử lý ngoài khóa | Snapshot ổn định về cấu trúc sau khi copy | Producer chỉ chờ trong thời gian copy |
| Duyệt không khóa trên synchronized wrapper | Không được bảo đảm an toàn khi sửa đồng thời | Có race; không sử dụng |
| Dùng collection concurrent có iterator yếu nhất quán hoặc snapshot | Phụ thuộc hợp đồng từng loại | Thường giảm blocking, đổi lấy semantics và chi phí khác |

Snapshot hữu ích khi phép duyệt dài hơn chi phí sao chép; nếu collection khổng lồ hoặc việc tạo bản sao gây áp lực bộ nhớ/GC, cần cân nhắc thiết kế riêng.

## 8. Synchronized wrapper khác concurrent collection ở điểm nào?

`Collections.synchronizedMap/List` dùng một **khóa chung** cho các lời gọi cần đồng bộ. Đây là mô hình dễ hiểu nhưng contention có thể cao khi nhiều thread liên tục truy cập.

| Lựa chọn | Phù hợp | Lưu ý về traversal và cập nhật |
| --- | --- | --- |
| `Collections.synchronizedMap(new HashMap<>())` | Muốn semantics gần HashMap, hỗ trợ khóa ngoài cho chuỗi nhiều bước | Duyệt view phải khóa map gốc |
| `Collections.synchronizedList(new ArrayList<>())` | Muốn semantics gần ArrayList và khóa ngoài rõ ràng | Duyệt iterator/list phải khóa list wrapper |
| `ConcurrentHashMap<K,V>` | Nhiều thread đọc/cập nhật độc lập, cần giảm contention | Iterator *weakly consistent*, có thể phản ánh một phần thay đổi; không cần khóa toàn map để tránh race nội bộ |
| `CopyOnWriteArrayList<E>` | Đọc/duyệt nhiều, sửa rất ít | Iterator là snapshot tại lúc tạo; mỗi sửa thường phải copy mảng, chi phí lớn |
| Collection immutable (`List.of`, `Map.of`, copy phù hợp) | Chỉ đọc sau công bố an toàn | Không hỗ trợ cập nhật; phần tử mutable vẫn cần lưu ý |

`ConcurrentHashMap` có các phép cập nhật nguyên tử theo khóa như `compute`, `merge` và `putIfAbsent`. Nhưng nó **không** bảo đảm một phép duyệt toàn map là snapshot nguyên tử trong khi các thread vẫn cập nhật. Ngoài ra, `ConcurrentHashMap` không cho phép key/value `null`, khác với `HashMap` (và wrapper synchronizedMap bao quanh HashMap).

`CopyOnWriteArrayList` thích hợp với ít ghi, nhiều lượt duyệt, ví dụ danh sách listener hiếm khi thay đổi. Các iterator của nó dựa trên snapshot mảng và không hỗ trợ `remove()` qua iterator; mỗi thay đổi mảng có overhead sao chép.

`Collections.unmodifiableList` và `Collections.unmodifiableMap` chỉ chặn sửa **qua view**, không tự thêm khóa và không biến backing collection mutable thành thread-safe. Không dùng “unmodifiable” như một cách thay thế synchronization cho dữ liệu vẫn bị thread khác chỉnh sửa.

### Khi nào synchronized wrapper vẫn là lựa chọn hợp lý?

- Dữ liệu nhỏ hoặc lượng tranh chấp thấp.
- Muốn giữ ngữ nghĩa và API `HashMap`/`ArrayList`, gồm hành vi key/value `null` tương ứng.
- Cần thao tác nhiều bước với monitor có thể khóa bên ngoài.
- Không cần throughput cao khi có rất nhiều thread đọc/ghi đồng thời.

Khi throughput hoặc latency giảm vì một monitor chung, cân nhắc concurrent collection hoặc đổi thiết kế dữ liệu — không nên chỉ thêm nhiều thread.

## 9. Những thao tác nhiều bước khác dễ bị race

### 9.1. Kiểm tra rồi thêm vào List

```java
if (!items.contains("task-A")) {
    items.add("task-A");
}
```

Hai thread có thể đều thấy chưa tồn tại và cùng thêm. Muốn “thêm duy nhất một lần” theo hợp đồng list:

```java
synchronized (items) {
    if (!items.contains("task-A")) {
        items.add("task-A");
    }
}
```

Nếu mục tiêu thực sự là tập hợp duy nhất, `Set` phù hợp hơn; có thể dùng `Collections.synchronizedSet` hoặc concurrent set tùy nhu cầu.

### 9.2. Kiểm tra kích thước rồi xóa phần tử đầu

```java
if (!items.isEmpty()) {
    String first = items.remove(0);
}
```

Giữa `isEmpty()` và `remove(0)`, thread khác có thể xóa phần tử; khi đó code có thể ném `IndexOutOfBoundsException` dù từng method synchronized.

```java
String first = null;
synchronized (items) {
    if (!items.isEmpty()) {
        first = items.remove(0);
    }
}
```

Đây là fragment; với thao tác producer/consumer cần chờ đến khi có item, `BlockingQueue` thường diễn đạt đúng nghiệp vụ hơn một list được đồng bộ.

### 9.3. Duyệt và xóa có kiểm soát

Khi cần duyệt và xóa phần tử theo điều kiện, dùng iterator trong khóa:

```java
synchronized (items) {
    Iterator<String> it = items.iterator();
    while (it.hasNext()) {
        if (it.next().startsWith("old-")) {
            it.remove();
        }
    }
}
```

Không nên đồng thời gọi `items.remove(...)` từ một thread khác mà không giữ cùng monitor, cũng không sửa backing list gốc trực tiếp. `Iterator.remove()` hợp lệ tùy collection và trạng thái iterator; wrapper synchronized-list quanh `ArrayList` cho phép thao tác này khi đúng điều kiện của Iterator.

### 9.4. Sử dụng compute/merge thay vì chuỗi thủ công?

Nếu wrapper và JDK của bạn hỗ trợ `Map.merge` hoặc `compute` với đồng bộ hóa trên wrapper, một phép gọi đơn có thể thay thao tác nhiều bước. Ví dụ:

```java
counts.merge("hits", 1, Integer::sum);
```

Với `Collections.synchronizedMap` trong JDK hiện đại, phương thức `merge` được wrapper đồng bộ trong quá trình thực hiện. Đây là cách rõ ràng hơn so với `get` rồi `put` riêng biệt khi cập nhật một khóa. Tuy nhiên callback trong `compute/merge` có thể chạy trong lúc giữ monitor; không nên thực hiện I/O lâu, gọi code ngoài không kiểm soát hoặc tạo phụ thuộc khóa vòng trong callback.

## 10. Deadlock và thời gian giữ khóa

Mô hình khóa bằng monitor dễ dẫn tới deadlock nếu nhiều thread giữ các khóa theo thứ tự khác nhau.

Ví dụ fragment minh họa nguy cơ:

```java
// Thread 1
synchronized (listA) {
    synchronized (listB) {
        transferAtoB();
    }
}

// Thread 2
synchronized (listB) {
    synchronized (listA) {
        transferBtoA();
    }
}
```

Nếu hai thread lấy khóa ngoài cùng lúc, chúng có thể chờ nhau vô hạn. Hai hàm chuyển dữ liệu chỉ là ký hiệu minh họa, không phải chương trình độc lập. Giải pháp là áp dụng **một thứ tự khóa nhất quán** hoặc một lock cấp ứng dụng được thiết kế rõ.

Một vòng lặp:

```java
synchronized (items) {
    for (String item : items) {
        sendOverNetwork(item);
    }
}
```

có thể khóa list trong thời gian network chậm, khiến producer dừng rất lâu. Nếu không cần giữ collection ổn định tới tận lúc gửi, hãy sao chép snapshot trong khóa rồi gửi ở ngoài khóa. Đừng gọi callback không kiểm soát, chờ Future hoặc thực hiện I/O dài trong monitor mà không đánh giá nguy cơ latency/deadlock.

Các phương thức đồng bộ nội bộ của wrapper không có cơ chế timeout khi giành monitor. Nếu cần locking có timeout, có thể phải dùng thiết kế dựa trên `ReentrantLock.tryLock(...)` hoặc collection khác; đừng cố dùng vòng lặp `sleep` để giả lập thời hạn cho `synchronized`.

## 11. Lưu ý về memory visibility và publication

Monitor bảo đảm quan hệ *happens-before* từ lần unlock tới lần lock sau trên **cùng monitor**. Vì vậy, nếu nhiều thread chỉ đọc/ghi nội dung collection qua wrapper đúng cách, những cập nhật tương ứng được quan sát theo quy tắc bộ nhớ Java.

Nhưng những điều sau vẫn phải có thiết kế riêng:

1. **Backing collection bị lộ:** có thread giữ `raw` và thay đổi mà không khóa, phá vỡ hợp đồng.
2. **Phần tử mutable:** wrapper chỉ bảo vệ việc cấu trúc collection truy cập/chỉnh sửa qua nó; trường trong object chứa bên trong cần synchronization hoặc thiết kế immutable.
3. **Sử dụng nhiều monitor khác nhau:** `synchronized(raw)` và `synchronized(wrapper)` là hai khóa khác nhau nếu wrapper là object khác backing; khóa sai không đảm bảo bảo vệ trước tất cả cập nhật.
4. **Bỏ khóa khi lấy Iterator:** iterator không tự giữ lock từ lúc tạo đến lúc `next()`.
5. **Khởi tạo/công bố wrapper không an toàn:** một reference có thể được chia sẻ sai cách nếu không có quan hệ happens-before để thread đọc thấy state được xây dựng đầy đủ.

Đối với dữ liệu chỉ đọc sau khởi tạo, xây dựng immutable snapshot và công bố an toàn thường giảm đáng kể nhu cầu khóa.

## 12. Cách kiểm thử concurrency cho synchronizedMap/List

Không nên viết test chỉ dựa vào `Thread.sleep(10)` để “hy vọng” hai thread chạm race. Thời gian thực thi phụ thuộc JIT, OS scheduler, CPU và tải hệ thống.

Nên dùng:

- `CountDownLatch` để điều khiển hai thread cùng đọc rồi mới ghi, như chương trình ở phần 6.
- `ExecutorService` và `Future.get()` để đợi task hoàn tất và báo lỗi task.
- Nhiều lượt thực thi để kiểm tra invariants dưới tải nhưng không dựa hoàn toàn vào số lượt để chứng minh race không thể xảy ra.
- Test riêng cho compound action như “contains-then-add”, “read-modify-write”, “check-then-remove”.
- Test duyệt `Iterator`, map views và `subList` khi thread khác sửa; khẳng định rằng khóa ngoài đúng mang lại hợp đồng mong muốn thay vì chờ một `ConcurrentModificationException` ngẫu nhiên.
- Các phép đo thời gian giữ khóa, số thread chờ, p95 latency nếu collection là điểm nghẽn.

Đừng dùng `ConcurrentModificationException` làm tín hiệu đồng bộ: nó có thể xảy ra hoặc không xảy ra dưới race; hành vi không phải một hợp đồng quan sát nhất quán.

## 13. Checklist khi dùng synchronizedMap/List

1. **Wrapper được tạo một lần** và là đường truy cập chia sẻ chính; không để backing mutable collection bị sửa ngoài wrapper.
2. **Lời gọi đơn** như `get/add/put/remove` sử dụng synchronization của wrapper.
3. **Thao tác kết hợp** cần atomicity thì bọc toàn chuỗi bằng `synchronized(wrapper)` hoặc dùng một phép atomic phù hợp.
4. **Duyệt Iterator, Spliterator, Stream** trong khối `synchronized(wrapper)` theo hợp đồng API.
5. **Map views** (`keySet/entrySet/values`) luôn duyệt dưới khóa map wrapper gốc.
6. **List subList** duyệt dưới khóa list wrapper gốc.
7. **Tránh giữ khóa lâu** khi có I/O, callback, chờ hoặc tính toán nặng; cân nhắc snapshot.
8. **Phần tử mutable** cần được bảo vệ độc lập nếu các thread sửa trạng thái của chính phần tử.
9. **Kiểm soát thứ tự khóa** nếu thao tác liên quan nhiều wrapper khác nhau.
10. **Chọn đúng collection** nếu số thread và tần suất cập nhật cao: `ConcurrentHashMap`, `CopyOnWriteArrayList` hoặc `BlockingQueue` có thể có semantics phù hợp hơn.

## 14. Câu hỏi tự kiểm tra

**1. Hai thread cùng gọi `map.get()` và `map.put()` trên synchronizedMap có tạo thành một phép tăng nguyên tử không?**  
Không. Mỗi lời gọi riêng được đồng bộ, nhưng thread khác có thể xen giữa các bước. Khóa toàn read-modify-write hoặc dùng operation nguyên tử thích hợp.

**2. Vì sao enhanced for trên synchronizedList cần khóa ngoài?**  
Enhanced for dùng Iterator với nhiều bước; wrapper không giữ monitor trong toàn traversal khi caller chỉ lấy Iterator rồi duyệt.

**3. Khi duyệt `map.entrySet()`, khóa `entrySet()` hay `map`?**  
Khóa **synchronized-map wrapper gốc** (`map`). Khóa view riêng không thay thế được hợp đồng này.

**4. Nếu dùng `list.subList(...)` rồi duyệt, khóa nào đúng?**  
Khóa **synchronized-list wrapper gốc**, không chỉ khóa sublist được trả về.

**5. Nếu chưa từng gặp `ConcurrentModificationException`, vòng duyệt không khóa đã an toàn chưa?**  
Chưa. Fail-fast detection là best-effort, không chứng minh không có race.

**6. Snapshot có bảo vệ việc sửa trạng thái của từng object bên trong không?**  
Không khi snapshot chỉ sao chép tham chiếu. Phần tử mutable vẫn chia sẻ cùng object.

**7. Vì sao `ConcurrentHashMap` không cần khóa toàn map để iterator tránh lỗi nội bộ?**  
Nó có iterator weakly consistent được thiết kế cho cập nhật đồng thời. Nhưng iterator không cho một snapshot nguyên tử của toàn map.

**8. Khi nào `CopyOnWriteArrayList` hữu ích hơn synchronizedList?**  
Khi traversal/đọc rất nhiều, cập nhật rất hiếm và chấp nhận chi phí copy mảng trên mỗi lần sửa.

**9. Gọi `Collections.unmodifiableList(raw)` có biến `raw` thành thread-safe không?**  
Không. View unmodifiable chỉ chặn sửa qua view; backing collection vẫn có thể bị sửa và cần synchronization.

## Tài liệu tham khảo

- [Java SE 17 — Collections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [Java SE 17 — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)
- [Java SE 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java SE 17 — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)
