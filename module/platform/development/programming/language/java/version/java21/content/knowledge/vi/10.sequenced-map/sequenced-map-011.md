# Ứng dụng map có thứ tự vào lịch sử truy cập, hàng đợi và bộ nhớ đệm

`SequencedMap<K, V>` trong Java 21 biểu diễn một map có thứ tự gặp (encounter order) xác định và hỗ trợ thao tác ở cả đầu lẫn cuối. Ngoài việc lưu ánh xạ key-value như `Map`, interface này cho phép đặt một mapping ở đầu hoặc cuối, đọc/xóa mapping ở hai đầu và tạo view có thứ tự ngược bằng `reversed()`.

Những khả năng này phù hợp với các cấu trúc dữ liệu cần giữ thứ tự như lịch sử sự kiện, hàng đợi công việc có mã định danh và bộ nhớ đệm LRU (Least Recently Used). Mỗi bài toán có quy tắc thứ tự riêng: lịch sử thường giữ thứ tự phát sinh, hàng đợi thường lấy phần tử cũ nhất trước, còn LRU sắp xếp theo lần truy cập gần nhất. Cần chọn đúng chế độ của implementation và hiểu rằng map không lưu được nhiều mapping có cùng key.

## 1. SequencedMap và các thao tác theo thứ tự

`SequencedMap<K, V>` thuộc package `java.util` và được bổ sung trong Java 21. Interface này mở rộng `Map<K, V>`, đồng thời cung cấp hợp đồng cho thứ tự gặp của các mapping.

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `putFirst(key, value)` | Thêm hoặc cập nhật mapping ở đầu thứ tự gặp |
| `putLast(key, value)` | Thêm hoặc cập nhật mapping ở cuối thứ tự gặp |
| `firstEntry()` | Đọc mapping đầu tiên mà không xóa |
| `lastEntry()` | Đọc mapping cuối cùng mà không xóa |
| `pollFirstEntry()` | Lấy và xóa mapping đầu tiên |
| `pollLastEntry()` | Lấy và xóa mapping cuối cùng |
| `reversed()` | Tạo view map có thứ tự gặp đảo ngược |

Ngoài ra, `sequencedKeySet()`, `sequencedValues()` và `sequencedEntrySet()` cung cấp các view theo đúng thứ tự của map. Chúng hữu ích khi muốn duyệt key, value hoặc entry mà vẫn giữ encounter order.

Ví dụ khai báo:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

class Main {
    public static void main(String[] args) {
        SequencedMap<String, Integer> scores = new LinkedHashMap<>();

        scores.putLast("An", 85);
        scores.putLast("Bình", 92);
        scores.putFirst("Chi", 88);

        System.out.println(scores); // {Chi=88, An=85, Bình=92}
        System.out.println(scores.firstEntry()); // Chi=88
        System.out.println(scores.lastEntry());  // Bình=92
    }
}
```

`LinkedHashMap` là implementation phổ biến khi cần thứ tự gặp có thể kiểm soát. Khi khai báo biến theo `SequencedMap`, mã nguồn phụ thuộc vào hợp đồng của interface thay vì phụ thuộc trực tiếp vào toàn bộ API riêng của một implementation.

## 2. Dùng SequencedMap để lưu lịch sử truy cập

Lịch sử truy cập thường cần giữ thứ tự các sự kiện xảy ra. Một mapping có thể dùng mã sự kiện làm key và nội dung hoặc thông tin sự kiện làm value. Khi sự kiện mới xuất hiện, thêm nó vào cuối bằng `putLast`.

```java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.SequencedMap;

record AccessEvent(String resource, Instant accessedAt) {}

class AccessHistory {
    private final SequencedMap<Long, AccessEvent> events =
            new LinkedHashMap<>();

    void record(long eventId, AccessEvent event) {
        events.putLast(eventId, event);
    }

    void printOldestFirst() {
        for (var entry : events.sequencedEntrySet()) {
            System.out.println(entry.getKey() + ": " + entry.getValue());
        }
    }

    void printNewestFirst() {
        for (var entry : events.reversed().sequencedEntrySet()) {
            System.out.println(entry.getKey() + ": " + entry.getValue());
        }
    }
}
```

Trong ví dụ này:

- `putLast` thêm sự kiện mới ở cuối lịch sử.
- `sequencedEntrySet()` duyệt từ sự kiện cũ đến mới.
- `reversed().sequencedEntrySet()` duyệt từ mới đến cũ.
- Key là mã sự kiện, do đó mỗi sự kiện cần có mã duy nhất nếu muốn giữ tất cả bản ghi.

Nếu gọi `putLast` với một key đã tồn tại, map vẫn chỉ có một mapping cho key đó; mapping hiện tại được đặt lại ở vị trí cuối theo hợp đồng của thao tác hai đầu. Vì vậy, không nên dùng key trùng nếu mục tiêu là lưu nhiều sự kiện độc lập.

### 2.1. Giới hạn số lượng bản ghi lịch sử

Một số màn hình chỉ cần giữ N sự kiện gần nhất. Có thể giới hạn kích thước bằng cách thêm mapping mới rồi xóa mapping đầu tiên khi vượt quá giới hạn:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

class RecentHistory<K, V> {
    private final int limit;
    private final SequencedMap<K, V> entries = new LinkedHashMap<>();

    RecentHistory(int limit) {
        if (limit < 1) {
            throw new IllegalArgumentException("limit phải lớn hơn 0");
        }
        this.limit = limit;
    }

    void record(K id, V event) {
        entries.putLast(id, event);

        while (entries.size() > limit) {
            entries.pollFirstEntry();
        }
    }

    SequencedMap<K, V> newestFirst() {
        return entries.reversed();
    }
}
```

Cách làm này giữ tối đa `limit` mapping theo thứ tự ghi nhận. Nếu key đã tồn tại, `putLast` cập nhật và đưa mapping đó về cuối, vì vậy chính sách trên phù hợp với lịch sử có định danh duy nhất và muốn ghi nhận lại key như một hoạt động mới.

Nếu cần lưu nhiều lần truy cập tới cùng một tài nguyên, hãy dùng mã sự kiện riêng làm key hoặc dùng một cấu trúc dạng queue/list. Không dùng tên tài nguyên làm key nếu các lần truy cập lặp lại đều cần được lưu thành bản ghi riêng.

## 3. Dùng SequencedMap làm hàng đợi có key

Một hàng đợi công việc thường xử lý theo FIFO: công việc được đưa vào cuối và lấy ra từ đầu. Có thể biểu diễn hàng đợi bằng `SequencedMap` khi mỗi công việc có một key duy nhất, ví dụ job ID.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedMap;

record Job(String id, String description) {}

class JobQueue {
    private final SequencedMap<String, Job> jobs = new LinkedHashMap<>();

    void enqueue(Job job) {
        jobs.putLast(job.id(), job);
    }

    Job peekNext() {
        Map.Entry<String, Job> first = jobs.firstEntry();
        return first == null ? null : first.getValue();
    }

    Job dequeue() {
        Map.Entry<String, Job> first = jobs.pollFirstEntry();
        return first == null ? null : first.getValue();
    }
}
```

Trong ví dụ:

- `enqueue` thêm công việc vào cuối hàng đợi.
- `peekNext` đọc công việc đầu tiên mà không xóa.
- `dequeue` lấy và xóa công việc đầu tiên.
- `firstEntry()` và `pollFirstEntry()` trả về `null` khi map rỗng.

Các phương thức đọc/xóa entry ở hai đầu trả về một `Map.Entry` đại diện cho mapping tại thời điểm gọi; hãy xem entry này như dữ liệu đọc, không dùng `setValue` để cập nhật map. Nếu cần cập nhật value, gọi `put` với key tương ứng.

### 3.1. Đưa công việc ưu tiên lên đầu

Có thể dùng `putFirst` để đặt một công việc ở đầu hàng đợi:

```java
jobs.putLast("job-101", new Job("job-101", "Generate report"));
jobs.putLast("job-102", new Job("job-102", "Send notification"));
jobs.putFirst("job-urgent", new Job("job-urgent", "Restore service"));
```

Khi lấy bằng `pollFirstEntry()`, công việc `job-urgent` sẽ được lấy trước. Cách này phù hợp với một mức ưu tiên đơn giản như đưa tác vụ khẩn cấp lên đầu.

Đây không phải một priority queue tổng quát. `putFirst` chỉ định vị trí ở đầu; nó không tự so sánh độ ưu tiên, deadline hoặc trọng số của các công việc. Nếu cần sắp xếp theo nhiều mức ưu tiên hoặc cập nhật ưu tiên liên tục, hãy thiết kế quy tắc đặt vị trí hoặc chọn cấu trúc dữ liệu chuyên biệt.

### 3.2. Key trùng và giới hạn của mô hình hàng đợi

Map chỉ chứa tối đa một mapping cho mỗi key. Nếu gọi `putLast` với key đã tồn tại, mapping cũ được cập nhật và định vị lại ở cuối; nó không tạo thêm một phần tử hàng đợi mới.

Điều này quan trọng khi có thể enqueue nhiều công việc cùng loại:

- Nếu mỗi công việc có ID duy nhất, `SequencedMap` có thể biểu diễn hàng đợi theo ID.
- Nếu key đại diện cho loại công việc và cùng loại có thể xuất hiện nhiều lần, các lần enqueue sẽ ghi đè mapping cùng key.
- Nếu cần lưu các phần tử trùng lặp hoặc chỉ cần FIFO, `Queue`/`Deque` thường là mô hình phù hợp hơn.

`SequencedMap` phù hợp khi cần vừa duy trì thứ tự vừa tra cứu nhanh theo key, chẳng hạn hủy hoặc cập nhật công việc dựa trên ID.

## 4. Dùng LinkedHashMap làm bộ nhớ đệm LRU

LRU (Least Recently Used) là chính sách loại bỏ mục ít được truy cập gần đây nhất khi bộ nhớ đệm vượt quá dung lượng. Trong LRU cache, thứ tự map thường được duy trì từ ít được dùng gần đây nhất ở đầu đến được dùng gần đây nhất ở cuối.

`LinkedHashMap` hỗ trợ thứ tự truy cập (access-order) thông qua constructor có tham số `accessOrder = true`:

```java
new LinkedHashMap<K, V>(initialCapacity, loadFactor, true)
```

Trong chế độ này, các thao tác truy cập mapping như `get` sẽ đưa mapping được truy cập về cuối thứ tự gặp. Do đó:

- `firstEntry()` là mapping ít được truy cập gần đây nhất.
- `lastEntry()` là mapping được truy cập gần đây nhất.
- `pollFirstEntry()` lấy và xóa mapping LRU.

Ví dụ cache giới hạn dung lượng:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

class LruCache<K, V> {
    private final int capacity;
    private final SequencedMap<K, V> entries;

    LruCache(int capacity) {
        if (capacity < 1) {
            throw new IllegalArgumentException("capacity phải lớn hơn 0");
        }

        this.capacity = capacity;
        this.entries = new LinkedHashMap<>(16, 0.75f, true);
    }

    V get(K key) {
        return entries.get(key);
    }

    void put(K key, V value) {
        entries.put(key, value);

        if (entries.size() > capacity) {
            entries.pollFirstEntry();
        }
    }

    int size() {
        return entries.size();
    }
}
```

Khi thêm mapping mới, nó xuất hiện ở cuối thứ tự truy cập. Nếu kích thước vượt quá `capacity`, `pollFirstEntry()` loại bỏ mapping ở đầu, tức mapping ít được truy cập gần đây nhất.

Đây là một ví dụ LRU đơn giản để minh họa cách dùng `SequencedMap` với access-order `LinkedHashMap`. Ứng dụng production còn cần cân nhắc đồng bộ đa luồng, tải dữ liệu khi cache miss, thời hạn hết hạn (TTL), giới hạn bộ nhớ theo kích thước value và thống kê hit/miss.

### 4.1. Minh họa thứ tự LRU

Giả sử cache có dung lượng 3 và lần lượt nhận các thao tác:

| Thao tác | Thứ tự từ LRU đến MRU |
|---|---|
| Thêm A, B, C | A, B, C |
| Truy cập A | B, C, A |
| Thêm D | C, A, D |
| Truy cập C | A, D, C |
| Thêm E | D, C, E |

LRU là phần tử ở đầu. Sau khi thêm D, B bị loại bỏ vì nó là phần tử ít được truy cập gần đây nhất. Sau khi truy cập C và thêm E, A bị loại bỏ.

Có thể quan sát trạng thái bằng `firstEntry()` và `lastEntry()`:

```java
var leastRecent = entries.firstEntry();
var mostRecent = entries.lastEntry();
```

Lưu ý: ví dụ bảng mô tả chính sách LRU. Với cache thực tế, thao tác đọc hoặc ghi mapping phải được thiết kế nhất quán để mọi truy cập liên quan đều cập nhật thứ tự đúng như chính sách mong muốn.

## 5. Phân biệt insertion-order và access-order

`LinkedHashMap` có hai chế độ encounter order phổ biến:

| Chế độ | Thứ tự | Ứng dụng |
|---|---|---|
| Insertion-order | Theo thứ tự mapping được chèn lần đầu | Lịch sử, cấu hình, danh sách kết quả |
| Access-order | Theo thứ tự truy cập, từ ít gần đây nhất đến nhiều gần đây nhất | LRU cache |

Với insertion-order, cập nhật value của key đã tồn tại bằng `put` không tự động di chuyển mapping khỏi vị trí hiện tại. Nếu muốn chủ động di chuyển mapping đến một đầu, dùng `putFirst` hoặc `putLast`.

Với access-order, các thao tác truy cập mapping có thể làm thay đổi encounter order. Vì vậy, duyệt map trong lúc thực hiện `get` trên cùng map có thể làm thay đổi cấu trúc thứ tự và gây `ConcurrentModificationException` với iterator fail-fast. Nếu cần duyệt để xử lý, hãy tránh truy cập map theo cách làm thay đổi thứ tự trong chính vòng lặp đó hoặc duyệt trên bản sao phù hợp.

Không nên chọn access-order cho mọi loại lịch sử. Nếu yêu cầu là lưu thứ tự phát sinh bất kể người dùng mở lại một mục, insertion-order thường dễ hiểu và đúng ý nghĩa hơn.

## 6. reversed() và các view có thứ tự

`SequencedMap.reversed()` trả về một view map có encounter order ngược với map gốc. View này được liên kết với map nền; các thay đổi qua view được phản ánh vào map gốc và ngược lại theo hợp đồng của SequencedMap.

Ví dụ đọc lịch sử mới nhất trước:

```java
SequencedMap<Long, String> history = new LinkedHashMap<>();
history.putLast(1L, "Login");
history.putLast(2L, "Open report");
history.putLast(3L, "Download file");

for (var entry : history.reversed().sequencedEntrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
```

Kết quả bắt đầu từ mapping có key `3`, sau đó `2` và `1`. Không cần tạo một map mới chỉ để đảo thứ tự duyệt.

Các view theo thứ tự có thể dùng trực tiếp:

- `sequencedKeySet()`: tập key có thứ tự.
- `sequencedValues()`: collection value có thứ tự.
- `sequencedEntrySet()`: tập entry có thứ tự.

Các view này gắn với map nền. Nếu cần snapshot để duyệt ổn định trong khi map tiếp tục thay đổi, hãy tạo bản sao phù hợp trước khi xử lý.

## 7. SequencedMap với SortedMap và TreeMap

`TreeMap` cũng triển khai `SequencedMap`, nhưng encounter order của nó do natural ordering hoặc `Comparator` quyết định. `reversed()` tạo view theo thứ tự so sánh ngược.

Với sorted map, `putFirst` và `putLast` không thể ép một key vào vị trí tùy ý vì điều đó sẽ vi phạm thứ tự sắp xếp; các thao tác này ném `UnsupportedOperationException`. Việc chèn vẫn được thực hiện bằng `put`, và vị trí do comparator quyết định.

Do đó:

- Dùng `LinkedHashMap` khi ứng dụng cần điều khiển thứ tự chèn hoặc thứ tự truy cập.
- Dùng `TreeMap` khi cần thứ tự theo key hoặc comparator.
- Dùng `SequencedMap` làm kiểu tham chiếu khi chỉ cần thao tác theo thứ tự và không muốn phụ thuộc vào implementation cụ thể.

Không nên dùng `TreeMap` làm lịch sử theo thứ tự phát sinh nếu key không được thiết kế để sắp xếp theo đúng trình tự nghiệp vụ.

## 8. Xử lý map rỗng, entry và khả năng sửa đổi

Khác với `SequencedCollection.getFirst()`, các phương thức `SequencedMap.firstEntry()`, `lastEntry()`, `pollFirstEntry()` và `pollLastEntry()` trả về `null` khi map rỗng.

```java
Map.Entry<String, Integer> first = scores.firstEntry();

if (first == null) {
    System.out.println("Map chưa có dữ liệu");
} else {
    System.out.println(first.getKey() + " = " + first.getValue());
}
```

Các phương thức `pollFirstEntry()` và `pollLastEntry()` xóa mapping được trả về. Các phương thức `firstEntry()` và `lastEntry()` chỉ đọc mapping.

Khả năng sửa đổi còn phụ thuộc implementation. Một map không sửa đổi được có thể ném `UnsupportedOperationException` khi gọi `putFirst`, `putLast` hoặc các phương thức xóa. View đảo ngược cũng không tự làm cho map có thể sửa đổi.

Các entry được trả về từ những phương thức đầu/cuối là snapshot không hỗ trợ cập nhật mapping qua `setValue`. Để thay đổi value, dùng `put(key, newValue)` hoặc API cập nhật tương ứng trên map.

## 9. Thread safety và tính nhất quán

`SequencedMap` chỉ quy định thứ tự và các thao tác hai đầu; interface không đảm bảo thread safety. `LinkedHashMap` và các view của nó không tự đồng bộ hóa khi nhiều luồng truy cập.

Trong hàng đợi công việc hoặc cache chia sẻ giữa nhiều luồng, thao tác ghép như:

1. Đọc mapping đầu tiên.
2. Xóa mapping đầu tiên.
3. Cập nhật trạng thái xử lý.

cần được bảo vệ như một đơn vị nhất quán nếu ứng dụng yêu cầu không mất hoặc xử lý trùng công việc. Việc chỉ kiểm tra `isEmpty()` rồi gọi `pollFirstEntry()` không tạo thành thao tác nguyên tử.

Có thể dùng một khóa đồng bộ chung quanh các thao tác trên map nếu tải và mô hình ứng dụng cho phép. Với hệ thống cần hàng đợi hoặc cache đồng thời ở quy mô lớn, nên cân nhắc các cấu trúc dữ liệu hoặc thư viện chuyên dụng có hợp đồng concurrency phù hợp. Không nên coi fail-fast iterator là cơ chế đồng bộ.

## 10. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng map không có encounter order cho lịch sử | `Map` nói chung không cam kết thứ tự duyệt | Dùng implementation có thứ tự như `LinkedHashMap` |
| Dùng key trùng để lưu nhiều sự kiện hoặc công việc | Map chỉ có một mapping cho mỗi key | Tạo ID riêng cho từng bản ghi hoặc dùng Queue/Deque |
| Gọi `pollFirstEntry` mà không xử lý map rỗng | Map rỗng trả về `null` | Kiểm tra kết quả trước khi truy cập key/value |
| Dùng insertion-order map làm LRU | Đọc key không tự chuyển mapping về cuối | Dùng access-order `LinkedHashMap` |
| Dùng `putFirst`/`putLast` với `TreeMap` | Comparator quyết định vị trí key | Dùng `put` và để map sắp xếp |
| Giả định reversed view là bản sao | Nhầm view với cấu trúc độc lập | Tạo map mới từ view nếu cần snapshot |
| Cho rằng SequencedMap an toàn đa luồng | Interface không cung cấp đồng bộ hóa | Dùng khóa hoặc cấu trúc concurrency phù hợp |

## 11. Chọn mô hình cho từng bài toán

| Bài toán | Cách tổ chức thứ tự | Phương thức tiêu biểu | Implementation gợi ý |
|---|---|---|---|
| Lịch sử truy cập/sự kiện | Cũ ở đầu, mới ở cuối | `putLast`, `reversed()`, `pollFirstEntry()` để giới hạn lịch sử | `LinkedHashMap` insertion-order |
| Hàng đợi công việc có ID duy nhất | Công việc mới ở cuối, lấy công việc đầu | `putLast`, `firstEntry`, `pollFirstEntry` | `LinkedHashMap` |
| Tác vụ cần xử lý trước | Đưa tác vụ lên đầu | `putFirst`, `pollFirstEntry` | `LinkedHashMap` |
| Cache LRU | Ít được truy cập ở đầu, mới truy cập ở cuối | `get`, `firstEntry`, `pollFirstEntry` | `LinkedHashMap` access-order |
| Map sắp xếp theo key | Theo natural order hoặc comparator | `firstEntry`, `lastEntry`, `reversed()` | `TreeMap` |

Một map có thứ tự có thể phục vụ nhiều bài toán, nhưng chính sách của từng bài toán phải được xác định rõ. Lịch sử cần giữ thứ tự phát sinh; queue cần quy tắc enqueue/dequeue; LRU cần cập nhật thứ tự mỗi khi mapping được truy cập. Chọn đúng implementation và thao tác đầu/cuối sẽ giúp code thể hiện trực tiếp chính sách đó.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Oracle Java SE 21 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)
- [Oracle Java SE 21 API — TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
