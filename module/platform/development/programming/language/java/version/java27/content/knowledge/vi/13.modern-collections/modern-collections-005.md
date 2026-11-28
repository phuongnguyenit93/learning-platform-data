# SequencedCollection, SequencedSet và SequencedMap

> **Phạm vi:** Java 27 — chương **Collections hiện đại**. Bài học trình bày ba interface `java.util.SequencedCollection`, `SequencedSet` và `SequencedMap`, cách quản lý **encounter order**, các phép toán ở hai đầu, reverse-ordered view và cách chọn implementation phù hợp. Đây là API chính thức được đưa vào Java từ **JDK 21 theo JEP 431** và vẫn áp dụng trong Java 27, không cần preview feature.

## 1. Vấn đề mà Sequenced Collections giải quyết

Java Collections Framework đã có nhiều cấu trúc giữ thứ tự:

- `List` có vị trí phần tử, truy cập bằng chỉ số.
- `Deque` hỗ trợ thao tác tại hai đầu.
- `LinkedHashSet` giữ thứ tự chèn của các phần tử không trùng lặp.
- `SortedSet`/`NavigableSet` duyệt phần tử theo comparator hoặc thứ tự tự nhiên.
- `LinkedHashMap` giữ thứ tự của các mapping; `SortedMap` giữ thứ tự khóa.

Nhưng trước JDK 21, không có **giao diện chung** thể hiện yêu cầu “collection này có thứ tự duyệt xác định, có phần tử đầu/cuối và có thể duyệt đảo chiều”. Tìm phần tử đầu trên `List` thường dùng `get(0)`, trên `Deque` dùng `getFirst()`, trên `SortedSet` dùng `first()`. Điều này gây phân mảnh API và khiến phương thức nhận `Collection<E>` không thể nói rõ rằng thứ tự là một phần của hợp đồng.

**Sequenced Collections** thống nhất các thao tác này thông qua ba interface:

| Interface | Bản chất | Đơn vị giữ thứ tự |
| --- | --- | --- |
| `SequencedCollection<E>` | Collection có encounter order xác định | Phần tử `E` |
| `SequencedSet<E>` | Set không trùng phần tử và có encounter order | Phần tử duy nhất `E` |
| `SequencedMap<K, V>` | Map có encounter order xác định | Mapping `K → V` |

**Encounter order** là thứ tự phần tử/mapping mà các thao tác có thứ tự của collection quan sát được — đặc biệt là iterator, stream có thứ tự và thao tác ở hai đầu. Thứ tự này **không đồng nghĩa** với vị trí vật lý trong bộ nhớ.

## 2. Vị trí của ba interface trong Java Collections Framework

Sơ đồ khái niệm (chỉ thể hiện một số interface và implementation tiêu biểu):

~~~text
Iterable<E>
└── Collection<E>
    ├── SequencedCollection<E>
    │   ├── List<E>          → ArrayList, LinkedList, ...
    │   ├── Deque<E>         → ArrayDeque, LinkedList, ...
    │   └── SequencedSet<E>  → LinkedHashSet, TreeSet, ...
    │       └── SortedSet<E> → NavigableSet<E>
    └── Set<E>               → HashSet, ...
        └── SequencedSet<E>  (cũng kế thừa Set<E>)

Map<K,V>
└── SequencedMap<K,V>
    ├── SortedMap<K,V>       → NavigableMap<K,V> → TreeMap
    └── LinkedHashMap<K,V>   (implements trực tiếp)
~~~

`SequencedSet` kế thừa **đồng thời** `Set` và `SequencedCollection`. `SequencedMap` kế thừa `Map`, **không** kế thừa `SequencedCollection` vì map chứa các mapping, không phải một collection phần tử độc lập.

Những implementation thường gặp:

| Kiểu cụ thể | Sequenced interface | Quy tắc thứ tự |
| --- | --- | --- |
| `ArrayList` | `List` → `SequencedCollection` | Vị trí trong danh sách |
| `ArrayDeque` | `Deque` → `SequencedCollection` | Thứ tự deque |
| `LinkedHashSet` | `SequencedSet` | Thường theo thứ tự chèn |
| `TreeSet` | `SortedSet` → `SequencedSet` | Thứ tự comparator |
| `LinkedHashMap` | `SequencedMap` | Thường theo thứ tự chèn; có thể cấu hình access-order |
| `TreeMap` | `SortedMap` → `SequencedMap` | Thứ tự comparator |
| `HashSet` | Không có `SequencedSet` | Không cam kết encounter order |
| `HashMap` | Không có `SequencedMap` | Không cam kết encounter order |

**Không suy ra thứ tự từ kết quả chạy thử.** Một `HashMap` có thể tình cờ in ra một thứ tự ổn định ở vài lần chạy nhưng không có hợp đồng thứ tự để dựa vào. Khi thứ tự là yêu cầu nghiệp vụ, hãy chọn kiểu và giao diện công bố rõ điều đó.

## 3. SequencedCollection<E>: giao diện chung của collection có thứ tự

`SequencedCollection<E>` kế thừa `Collection<E>` và bổ sung các thao tác chung:

~~~java
interface SequencedCollection<E> extends Collection<E> {
    SequencedCollection<E> reversed();
    void addFirst(E e);
    void addLast(E e);
    E getFirst();
    E getLast();
    E removeFirst();
    E removeLast();
}
~~~

Đây là bản phác họa **các chữ ký chính**, không phải đoạn khai báo cần tạo lại trong dự án. Các phương thức bổ sung là các API đang có sẵn trong `java.util`.

### 3.1. Đọc hai đầu bằng getFirst/getLast

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> stages = new ArrayList<>(
        List.of("receive", "validate", "publish"));

System.out.println(stages.getFirst()); // receive
System.out.println(stages.getLast());  // publish
~~~

Nếu collection **rỗng**, `getFirst()` và `getLast()` ném `NoSuchElementException`. Đừng nhầm với `SequencedMap.firstEntry()`, phương thức trả `null` nếu map rỗng.

### 3.2. Thêm và xóa ở hai đầu

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(2, 3));

numbers.addFirst(1);
numbers.addLast(4);

System.out.println(numbers);              // [1, 2, 3, 4]
System.out.println(numbers.removeFirst()); // 1
System.out.println(numbers.removeLast());  // 4
System.out.println(numbers);              // [2, 3]
~~~

**Các phép thay đổi là optional operations.** Việc một class triển khai `SequencedCollection` không có nghĩa là nó luôn cho phép `addFirst`, `addLast`, `removeFirst` hay `removeLast`.

~~~java
import java.util.List;

List<String> fixed = List.of("A", "B");
System.out.println(fixed.getFirst()); // A
System.out.println(fixed.getLast());  // B

// fixed.addFirst("Z"); // UnsupportedOperationException
// fixed.removeLast();  // UnsupportedOperationException
~~~

Chú thích trên biểu diễn lời gọi sẽ ném ngoại lệ **khi chạy**, không phải lời gọi không thể biên dịch.

### 3.3. getFirst và removeFirst khác nhau

| Phương thức | Có đổi dữ liệu không? | Collection rỗng |
| --- | --- | --- |
| `getFirst()` | Không | `NoSuchElementException` |
| `getLast()` | Không | `NoSuchElementException` |
| `removeFirst()` | Có, nếu được hỗ trợ | `NoSuchElementException` (hoặc UOE nếu thao tác không được hỗ trợ) |
| `removeLast()` | Có, nếu được hỗ trợ | `NoSuchElementException` (hoặc UOE nếu thao tác không được hỗ trợ) |
| `addFirst(e)` | Có, nếu được hỗ trợ | Không liên quan đến rỗng; có thể UOE |
| `addLast(e)` | Có, nếu được hỗ trợ | Không liên quan đến rỗng; có thể UOE |

`UnsupportedOperationException` (UOE) là tín hiệu thao tác tùy chọn không được implementation cho phép. Một collection có thể hỗ trợ đọc phần tử ở hai đầu mà vẫn cấm thêm/xóa.

## 4. reversed(): view đảo thứ tự, không phải snapshot

`reversed()` trả về **reverse-ordered view**: thứ tự nhìn thấy là đảo ngược của collection nguồn. Phương thức này không yêu cầu copy toàn bộ phần tử thành collection mới.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B", "C"));
List<String> reverse = source.reversed();

System.out.println(source);  // [A, B, C]
System.out.println(reverse); // [C, B, A]

source.add("D");
System.out.println(reverse); // [D, C, B, A]

reverse.removeFirst();       // Xóa D trong source
System.out.println(source);  // [A, B, C]
~~~

Ví dụ dùng `ArrayList` nên thay đổi được phản ánh hai chiều. **Đừng suy diễn** rằng tất cả implementation phải cho phép sửa view hoặc có cùng quy tắc quan sát thay đổi: API chung quy định nếu view cho phép sửa thì thao tác ghi xuyên về backing collection, còn khả năng nhìn thấy thay đổi từ backing collection tùy implementation.

### 4.1. Hai đầu được đảo nghĩa

Với một reverse view:

- `reverse.getFirst()` tương ứng `original.getLast()`.
- `reverse.getLast()` tương ứng `original.getFirst()`.
- Nếu cho phép, `reverse.addFirst(x)` thêm vào **cuối** encounter order của collection gốc.
- Nếu cho phép, `reverse.removeLast()` xóa **đầu** collection gốc.

Các thao tác có thứ tự như iterator, `forEach`, `stream` và `toArray` của view đều quan sát thứ tự đảo.

~~~java
import java.util.LinkedHashSet;

var tags = new LinkedHashSet<String>();
tags.add("urgent");
tags.add("review");
tags.add("done");

tags.reversed().forEach(System.out::println);
// done
// review
// urgent
~~~

### 4.2. View không tự bảo đảm thread safety

Một reverse view sống cùng dữ liệu nguồn. Không được dùng `reversed()` như một “snapshot an toàn đa luồng”. Với collection mutable, sửa trong lúc duyệt có thể gây `ConcurrentModificationException` ở một số implementation, hoặc có hành vi phụ thuộc hợp đồng iterator. Fail-fast không phải một cơ chế đồng bộ.

Nếu cần **snapshot độc lập có thứ tự đảo**:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B", "C"));
List<String> snapshot = List.copyOf(source.reversed());

source.add("D");
System.out.println(snapshot); // [C, B, A]
~~~

`List.copyOf` tạo collection không cho phép cập nhật cấu trúc, nhưng sao chép **nông**: nếu phần tử là object mutable thì việc sửa object đó vẫn có thể được quan sát từ cả hai nơi.

### 4.3. Stream song song và encounter order

Nguồn `SequencedCollection` có encounter order. Với stream tuần tự, việc duyệt thường tôn trọng thứ tự đó; với stream song song, `forEach` không bảo đảm thứ tự thực thi của từng phần tử, dù nguồn có order.

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C");

values.reversed()
        .parallelStream()
        .forEachOrdered(System.out::println);
// C
// B
// A
~~~

Nếu thật sự cần thứ tự đầu ra trong parallel stream, dùng `forEachOrdered` hoặc thao tác terminal có hợp đồng giữ thứ tự phù hợp. Việc giữ thứ tự có thể hạn chế hiệu năng song song.

## 5. SequencedSet<E>: duy nhất và có encounter order

`SequencedSet<E>` kết hợp hợp đồng của `Set<E>` và `SequencedCollection<E>`:

~~~java
interface SequencedSet<E> extends Set<E>, SequencedCollection<E> {
    SequencedSet<E> reversed();
}
~~~

Phương thức `reversed()` được override với kiểu trả về chuyên biệt `SequencedSet<E>` để không mất thông tin “đây vẫn là một set”. Các phần tử **không trùng** theo ngữ nghĩa set.

### 5.1. LinkedHashSet: insertion order và di chuyển phần tử

~~~java
import java.util.LinkedHashSet;

LinkedHashSet<String> workflow = new LinkedHashSet<>();
workflow.add("draft");
workflow.add("review");
workflow.add("publish");

System.out.println(workflow); // [draft, review, publish]

workflow.add("review");       // Đã tồn tại: không đổi vị trí
System.out.println(workflow); // [draft, review, publish]

workflow.addFirst("publish"); // Chuyển phần tử hiện có lên đầu
System.out.println(workflow); // [publish, draft, review]

workflow.addLast("draft");    // Chuyển phần tử hiện có xuống cuối
System.out.println(workflow); // [publish, review, draft]
~~~

Đây là điểm đáng chú ý trong Java hiện đại: `LinkedHashSet.addFirst` và `addLast` **không chỉ áp dụng cho phần tử mới**. Khi phần tử đã tồn tại, chúng thay đổi vị trí của chính phần tử đó trong encounter order, vẫn bảo đảm set không trùng.

`LinkedHashSet.add(e)` thông thường không chuyển vị trí của phần tử đã có.

### 5.2. TreeSet: thứ tự do comparator quyết định

~~~java
import java.util.TreeSet;

TreeSet<Integer> scores = new TreeSet<>();
scores.add(30);
scores.add(10);
scores.add(20);

System.out.println(scores);                   // [10, 20, 30]
System.out.println(scores.getFirst());        // 10
System.out.println(scores.getLast());         // 30
System.out.println(scores.reversed());        // [30, 20, 10]
~~~

`TreeSet` là `SequencedSet` vì nó có thứ tự xác định. Nhưng thứ tự này được quyết định bởi `Comparable` hoặc `Comparator`, **không phải vị trí do caller tự chọn**:

~~~java
import java.util.TreeSet;

var scores = new TreeSet<Integer>();
scores.add(10);
scores.add(20);

// scores.addFirst(5); // UnsupportedOperationException
// scores.addLast(30); // UnsupportedOperationException
~~~

Các method `addFirst`/`addLast` vẫn tồn tại trong interface, nhưng sorted set không cho phép ép phần tử vào đầu/cuối trái với comparator. Để thêm phần tử vào sorted set, dùng `add` và để comparator quyết định vị trí.

### 5.3. equals/hashCode của SequencedSet không xét thứ tự

`SequencedSet` tuân theo hợp đồng `Set.equals`/`Set.hashCode`:

~~~java
import java.util.LinkedHashSet;
import java.util.List;

var a = new LinkedHashSet<>(List.of("A", "B"));
var b = new LinkedHashSet<>(List.of("B", "A"));

System.out.println(a.equals(b)); // true
System.out.println(a.reversed().equals(b.reversed())); // true
~~~

Hai set có encounter order khác nhau vẫn được coi là bằng nhau nếu cùng tập phần tử. Vì vậy, **thứ tự không thuộc hợp đồng equality của set**. Nếu nghiệp vụ cần tính cả thứ tự trong equality, hãy lưu dữ liệu bằng một kiểu có equality dựa trên thứ tự (chẳng hạn `List`) hoặc định nghĩa domain value object riêng.

## 6. SequencedMap<K,V>: map có mapping đầu và cuối

`SequencedMap<K,V>` kế thừa `Map<K,V>` và bổ sung các phương thức:

~~~java
interface SequencedMap<K,V> extends Map<K,V> {
    SequencedMap<K,V> reversed();

    Map.Entry<K,V> firstEntry();
    Map.Entry<K,V> lastEntry();
    Map.Entry<K,V> pollFirstEntry();
    Map.Entry<K,V> pollLastEntry();

    V putFirst(K key, V value);
    V putLast(K key, V value);

    SequencedSet<K> sequencedKeySet();
    SequencedCollection<V> sequencedValues();
    SequencedSet<Map.Entry<K,V>> sequencedEntrySet();
}
~~~

Các chữ ký trên là **sơ đồ rút gọn**; dùng interface đã có trong JDK, không khai báo lại.

### 6.1. Đọc mapping đầu/cuối

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

LinkedHashMap<String,Integer> inventory = new LinkedHashMap<>();
inventory.put("A", 10);
inventory.put("B", 20);
inventory.put("C", 30);

Map.Entry<String,Integer> first = inventory.firstEntry();
Map.Entry<String,Integer> last = inventory.lastEntry();

System.out.println(first); // A=10
System.out.println(last);  // C=30
~~~

Khác với `SequencedCollection.getFirst()`, `SequencedMap.firstEntry()` và `lastEntry()` **trả `null` khi map rỗng**. Giá trị `Map.Entry` trả về là **snapshot của mapping tại thời điểm gọi** và không hỗ trợ `setValue()` để đổi map. Snapshot ở đây chỉ là cặp key/value, không tự deep-copy object key/value bên trong.

### 6.2. pollFirstEntry/pollLastEntry xóa mapping

~~~java
import java.util.LinkedHashMap;

var queue = new LinkedHashMap<String, Integer>();
queue.put("job-A", 1);
queue.put("job-B", 2);
queue.put("job-C", 3);

var removed = queue.pollFirstEntry();

System.out.println(removed);        // job-A=1
System.out.println(queue.keySet()); // [job-B, job-C]
~~~

`pollFirstEntry()` và `pollLastEntry()` là optional mutation; nếu map hỗ trợ chúng, chúng trả snapshot entry đã xóa, hoặc `null` nếu rỗng. Đừng dùng `firstEntry()` nếu mong muốn xóa phần tử.

### 6.3. putFirst/putLast: thêm hoặc chuyển vị trí mapping

~~~java
import java.util.LinkedHashMap;

var tasks = new LinkedHashMap<String, String>();
tasks.put("a", "open");
tasks.put("b", "pending");
tasks.put("c", "done");

tasks.putFirst("c", "review"); // Đổi value và chuyển c lên đầu
System.out.println(tasks.keySet()); // [c, a, b]

tasks.putLast("a", "ready");  // Đổi value và chuyển a xuống cuối
System.out.println(tasks.keySet()); // [c, b, a]
~~~

Khi key đã tồn tại, `putFirst`/`putLast` thay value và **đổi vị trí** mapping. Chúng trả về **giá trị cũ** tương ứng key, hoặc `null` nếu trước đó key chưa có mapping (hoặc có mapping sang `null` — phải kiểm tra `containsKey` nếu cần phân biệt).

Trong `LinkedHashMap` dạng insertion-order mặc định, `put` với key đã tồn tại **không đổi vị trí**, trái với `putFirst`/`putLast`.

### 6.4. TreeMap: putFirst/putLast không được hỗ trợ

~~~java
import java.util.TreeMap;

var ranks = new TreeMap<Integer,String>();
ranks.put(30, "third");
ranks.put(10, "first");
ranks.put(20, "second");

System.out.println(ranks.firstEntry()); // 10=first
System.out.println(ranks.lastEntry());  // 30=third

// ranks.putFirst(5, "new"); // UnsupportedOperationException
// ranks.putLast(40, "new"); // UnsupportedOperationException
~~~

`TreeMap` sắp xếp theo khóa; không thể đặt mapping vào vị trí tùy ý. Đây là cùng nguyên tắc với `TreeSet.addFirst`/`addLast`. Nếu thứ tự do comparator quyết định, hãy dùng `put` thông thường.

## 7. Những sequenced view của map

`SequencedMap` có ba API trả view với kiểu thể hiện thứ tự:

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `sequencedKeySet()` | `SequencedSet<K>` | Các khóa theo encounter order |
| `sequencedValues()` | `SequencedCollection<V>` | Các giá trị theo encounter order của mapping |
| `sequencedEntrySet()` | `SequencedSet<Map.Entry<K,V>>` | Các cặp key/value theo encounter order |

Ví dụ:

~~~java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String,Integer> map = new LinkedHashMap<>();
map.put("first", 10);
map.put("second", 20);
map.put("third", 30);

System.out.println(map.sequencedKeySet().getFirst()); // first
System.out.println(map.sequencedValues().getLast());  // 30
System.out.println(map.sequencedEntrySet().getFirst()); // first=10

System.out.println(map.reversed().sequencedKeySet());
// [third, second, first]
~~~

### 7.1. View có liên kết với map, không phải copy

Với `LinkedHashMap`, các view bám theo mapping nguồn. Nếu map bị thay đổi, các view phản ánh thay đổi theo hợp đồng của implementation; nếu view cho phép xóa, xóa qua view sẽ ảnh hưởng map.

~~~java
import java.util.LinkedHashMap;

var map = new LinkedHashMap<String,Integer>();
map.put("alpha", 1);
map.put("beta", 2);

var keys = map.sequencedKeySet();
keys.removeFirst();

System.out.println(map); // {beta=2}
~~~

**Không dùng** `sequencedKeySet().addFirst(...)` để thêm key mới, `sequencedValues().addLast(...)` để thêm value hoặc `sequencedEntrySet().addFirst(...)` để thêm entry: các phép **add** trên những view này không được hỗ trợ. Thêm/reposition mapping phải thực hiện qua `map.put`, `putFirst` hoặc `putLast` khi implementation cho phép.

### 7.2. firstEntry khác với sequencedEntrySet().getFirst()

`map.firstEntry()` được quy định trả **snapshot entry**, nên gọi `entry.setValue(...)` không được phép. Trong khi đó, `map.sequencedEntrySet().getFirst()` trả một entry lấy từ view; việc nó có kết nối ghi xuyên về map hay không **phụ thuộc implementation** và không được cam kết chỉ từ interface `SequencedMap`.

Do đó, cách cập nhật rõ ràng là `map.put(key, newValue)` hoặc `map.replace(key, newValue)`. Không dựa vào `Map.Entry.setValue` từ một entry mà hợp đồng kết nối không chắc chắn.

### 7.3. reversed map đảo cả view key/value/entry

~~~java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String,Integer> original = new LinkedHashMap<>();
original.put("A", 1);
original.put("B", 2);

SequencedMap<String,Integer> reverse = original.reversed();

System.out.println(reverse.firstEntry()); // B=2
System.out.println(reverse.sequencedKeySet()); // [B, A]

reverse.putFirst("C", 3); // Với LinkedHashMap: thêm C ở cuối original
System.out.println(original.sequencedKeySet()); // [A, B, C]
~~~

Đảo thứ tự không đổi key-value association; nó chỉ thay đổi cách quan sát và các phép toán liên quan thứ tự. Khi `reversed()` được dùng trên map hỗ trợ chỉnh sửa, thay đổi trên view có thể ghi về backing map.

## 8. Thứ tự chèn, thứ tự truy cập và thứ tự sắp xếp

Ba loại thứ tự nên được phân biệt ngay từ thiết kế:

| Loại thứ tự | Ví dụ | Khi nào thay đổi? |
| --- | --- | --- |
| Insertion-order | `LinkedHashSet`, `LinkedHashMap` mặc định | Khi thêm phần tử mới; hoặc đặt lại vị trí bằng `addFirst/addLast`, `putFirst/putLast` |
| Access-order | `LinkedHashMap` tạo bằng constructor có `accessOrder=true` | Một số thao tác truy cập như `get` có thể đổi vị trí |
| Sorted-order | `TreeSet`, `TreeMap` | Do `Comparator`/`Comparable` quyết định |

### 8.1. LinkedHashMap với access-order

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

LinkedHashMap<String,Integer> lastAccess = new LinkedHashMap<>(
        16, 0.75f, true);

lastAccess.put("A", 1);
lastAccess.put("B", 2);
lastAccess.put("C", 3);

lastAccess.get("A"); // A chuyển về cuối (recently accessed)

System.out.println(lastAccess.sequencedKeySet());
// [B, C, A]
~~~

Trong access-order map, `get` có thể thay đổi encounter order; việc đó quan trọng với LRU cache, nhưng cũng có thể ảnh hưởng iterator đang hoạt động. Đọc một entry không còn luôn là “quan sát không làm thay đổi cấu trúc” theo ý nghĩa iterator.

**Không suy ra từ tên interface rằng mọi SequencedMap là LRU map.** `SequencedMap` chỉ yêu cầu encounter order xác định; bản thân nó không định nghĩa chính sách cache, đồng bộ, eviction hay cách xử lý TTL.

### 8.2. Sorted-order và tính nhất quán comparator

`TreeSet`/`TreeMap` dùng comparator để tìm vị trí và xác định key/element nào được coi là trùng về mặt sắp xếp. Nếu comparator không nhất quán với `equals`, collection có thể không tuân hợp đồng tổng quát của `Set`/`Map`.

Một quy tắc thực hành: với domain key, lựa chọn `Comparable`/`Comparator` sao cho `compare(a,b)==0` phản ánh đúng khái niệm trùng khóa dự kiến. Không dùng comparator chỉ để ép thứ tự hiển thị nếu điều đó làm mất key khác nhau về nghiệp vụ.

## 9. Thứ tự và phép bằng nhau

Đừng nhầm **encounter order** với **hợp đồng equals**.

| Kiểu | equals() có xét vị trí? | Ví dụ |
| --- | --- | --- |
| `List` | Có, so sánh phần tử theo từng vị trí | `[A,B]` khác `[B,A]` |
| `Set`/`SequencedSet` | Không, so sánh tập phần tử | `{A,B}` bằng `{B,A}` |
| `Map`/`SequencedMap` | Không, so sánh mapping | Hai map cùng key/value có thể equals dù order khác nhau |
| `SequencedCollection` nói chung | Không tự quy định equals/hashCode | Phụ thuộc hợp đồng subtype/implementation |

~~~java
import java.util.LinkedHashMap;
import java.util.List;

System.out.println(List.of("A", "B").equals(List.of("B", "A")));
// false

var first = new LinkedHashMap<String,Integer>();
first.put("A", 1);
first.put("B", 2);

var second = new LinkedHashMap<String,Integer>();
second.put("B", 2);
second.put("A", 1);

System.out.println(first.equals(second)); // true
~~~

Nếu thứ tự là một phần của giá trị nghiệp vụ (ví dụ lịch trình hoặc thứ tự bước quy trình), dùng cấu trúc và `equals` xét thứ tự — thường là `List` hoặc value object chứa list bất biến.

## 10. API nào nên nhận SequencedCollection thay vì List?

Nếu một phương thức chỉ cần:

- Thứ tự duyệt xác định.
- Truy cập đầu/cuối.
- Duyệt xuôi hoặc ngược.
- Không yêu cầu chỉ số, chèn vào giữa hay thuật toán chỉ dành cho list.

Thì nhận `SequencedCollection<E>` giúp API tổng quát hơn:

~~~java
import java.util.SequencedCollection;

public final class EventPrinter {
    private EventPrinter() {}

    public static <E> void printLatestFirst(
            SequencedCollection<E> events) {
        for (E event : events.reversed()) {
            System.out.println(event);
        }
    }
}
~~~

Phương thức này nhận được `ArrayList`, `ArrayDeque`, `LinkedHashSet` và `TreeSet`, miễn là đầu vào đáp ứng `SequencedCollection<E>`. Nếu chỉ dùng `List<E>`, nhiều collection có thứ tự khác sẽ bị loại bỏ không cần thiết.

**Đừng thay List bằng SequencedCollection cho mọi API.** Nếu logic cần `get(index)`, `subList`, thao tác ngẫu nhiên theo vị trí hay hợp đồng equality của list, `List` diễn đạt yêu cầu chính xác hơn.

Tương tự:

- Nhận `SequencedSet<E>` khi cần **duy nhất và có thứ tự**.
- Nhận `SequencedMap<K,V>` khi cần **mapping có thứ tự**.
- Nhận `SortedSet<E>`/`SortedMap<K,V>` khi yêu cầu **thứ tự sắp xếp do comparator**.
- Nhận `Deque<E>` khi cần hợp đồng thao tác queue/deque (peek/poll/offer), không chỉ “có thứ tự”.

### 10.1. Đừng ép kiểu tùy tiện

~~~java
import java.util.HashSet;
import java.util.SequencedSet;
import java.util.Set;

Set<String> unknownOrder = new HashSet<>();
unknownOrder.add("A");

// Không làm điều này:
// SequencedSet<String> ordered = (SequencedSet<String>) unknownOrder;
// Runtime sẽ ném ClassCastException.
~~~

Muốn **tạo một collection có thứ tự chèn từ input**, hãy chọn implementation rõ ràng:

~~~java
import java.util.LinkedHashSet;
import java.util.SequencedSet;
import java.util.Set;

Set<String> input = Set.of("A", "B", "C");
SequencedSet<String> ordered = new LinkedHashSet<>(input);
~~~

Ở ví dụ này, `ordered` duyệt theo encounter order **đã được iterator của input cung cấp**, nhưng `Set.of` không cam kết thứ tự đầu vào nên không nên mong luôn ra `A,B,C`. Nếu cần thứ tự `A,B,C`, truyền dữ liệu gốc qua `List.of("A", "B", "C")`.

## 11. Unmodifiable sequenced view và snapshot

Từ JDK 21, `Collections` có các wrapper bảo toàn interface có thứ tự:

- `Collections.unmodifiableSequencedCollection(...)`.
- `Collections.unmodifiableSequencedSet(...)`.
- `Collections.unmodifiableSequencedMap(...)`.

Chúng tạo **unmodifiable view**, không tự tạo bản sao dữ liệu.

### 11.1. Unmodifiable view vẫn phản ánh thay đổi backing data

~~~java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.SequencedSet;

LinkedHashSet<String> source = new LinkedHashSet<>();
source.add("A");

SequencedSet<String> readOnly =
        Collections.unmodifiableSequencedSet(source);

source.add("B");
System.out.println(readOnly); // [A, B]

// readOnly.addFirst("C"); // UnsupportedOperationException
~~~

Wrapper chặn sửa qua chính nó, nhưng caller giữ `source` vẫn có thể sửa backing collection. Vì vậy, **unmodifiable không đồng nghĩa immutable snapshot**.

### 11.2. Tạo snapshot giữ thứ tự cho SequencedSet

Nếu cần snapshot không cho thay đổi qua interface set và muốn giữ encounter order ở thời điểm copy:

~~~java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.SequencedSet;

LinkedHashSet<String> original = new LinkedHashSet<>();
original.add("A");
original.add("B");

SequencedSet<String> snapshot =
        Collections.unmodifiableSequencedSet(
                new LinkedHashSet<>(original));

original.add("C");
System.out.println(snapshot); // [A, B]
~~~

`snapshot` ở đây có một **backing copy riêng**; code ngoài không giữ tham chiếu mutable đến backing copy. Nhưng các phần tử bên trong vẫn là shallow references: `SequencedSet<MutableObject>` cần đánh giá việc sao chép sâu hoặc dùng value object bất biến.

### 11.3. Snapshot có thứ tự cho map

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.SequencedMap;

LinkedHashMap<String,Integer> original = new LinkedHashMap<>();
original.put("A", 1);
original.put("B", 2);

SequencedMap<String,Integer> snapshot =
        Collections.unmodifiableSequencedMap(
                new LinkedHashMap<>(original));

original.put("C", 3);
System.out.println(snapshot.sequencedKeySet()); // [A, B]
~~~

`Map.copyOf(original)` là một immutable map phù hợp khi thứ tự **không** quan trọng, nhưng API `Map.copyOf` không hứa bảo toàn encounter order và không trả `SequencedMap`. Nếu thứ tự là hợp đồng, mô hình snapshot bằng `LinkedHashMap` + unmodifiable sequenced wrapper là cách diễn đạt rõ hơn.

### 11.4. List.of, Set.of, Map.of khác nhau về thứ tự

- `List.of(...)` trả `List` unmodifiable; `List` có encounter order nên các phép `getFirst/getLast/reversed` được hỗ trợ đọc.
- `Set.of(...)` trả `Set` không cam kết encounter order và **không** được công bố như `SequencedSet`.
- `Map.of(...)` trả `Map` không cam kết encounter order và **không** được công bố như `SequencedMap`.

**Không** đặt giả định thứ tự vào dữ liệu cấu hình chỉ vì một map/set factory tình cờ duyệt theo thứ tự bạn thấy trong một lần chạy.

## 12. Trường hợp rỗng và các ngoại lệ cần ghi nhớ

| Lời gọi | Khi collection/map rỗng | Nếu thao tác không được hỗ trợ |
| --- | --- | --- |
| `SequencedCollection.getFirst()` | `NoSuchElementException` | Không áp dụng |
| `SequencedCollection.getLast()` | `NoSuchElementException` | Không áp dụng |
| `SequencedCollection.removeFirst/Last()` | `NoSuchElementException` theo thao tác được hỗ trợ | `UnsupportedOperationException` |
| `SequencedMap.firstEntry()/lastEntry()` | `null` | Không áp dụng |
| `SequencedMap.pollFirstEntry()/pollLastEntry()` | `null` nếu được hỗ trợ | `UnsupportedOperationException` |
| `SequencedCollection.addFirst/addLast(e)` | Thêm nếu được hỗ trợ | `UnsupportedOperationException` |
| `SequencedMap.putFirst/putLast(k,v)` | Thêm nếu được hỗ trợ | `UnsupportedOperationException` |

Ngoài các ngoại lệ trên, những điều kiện như null không được phép, kiểu phần tử không tương thích hoặc comparator lỗi vẫn có thể dẫn đến ngoại lệ tương ứng theo từng implementation.

### 12.1. Kiểm tra rỗng trước khi đọc

~~~java
import java.util.NoSuchElementException;
import java.util.SequencedCollection;

public final class FirstElement {
    public static <E> E requireFirst(SequencedCollection<E> items) {
        if (items.isEmpty()) {
            throw new NoSuchElementException("No elements");
        }
        return items.getFirst();
    }
}
~~~

Đây là ví dụ minh họa cho collection được sử dụng trong một luồng điều khiển không bị sửa đồng thời. Với mutable concurrent collection, trạng thái có thể thay đổi giữa `isEmpty()` và `getFirst()`; cần thiết kế thao tác nguyên tử hoặc xử lý ngoại lệ phù hợp với API của collection đó.

## 13. Ví dụ thực tế: hàng đợi tác vụ không trùng ID

Mục tiêu: lưu các task ID không trùng, cho phép ưu tiên một task bằng cách chuyển lên đầu, xử lý theo thứ tự và xem danh sách đảo:

~~~java
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.SequencedSet;

public final class TaskQueue {
    private final SequencedSet<String> pending = new LinkedHashSet<>();

    public void submit(String taskId) {
        pending.add(Objects.requireNonNull(taskId, "taskId"));
    }

    public void prioritize(String taskId) {
        taskId = Objects.requireNonNull(taskId, "taskId");
        if (!pending.contains(taskId)) {
            throw new IllegalArgumentException("Unknown task: " + taskId);
        }
        pending.addFirst(taskId);
    }

    public String takeNext() {
        return pending.removeFirst();
    }

    public SequencedSet<String> newestFirstView() {
        return java.util.Collections.unmodifiableSequencedSet(
                pending.reversed());
    }
}
~~~

Ví dụ sử dụng:

~~~java
TaskQueue queue = new TaskQueue();
queue.submit("A");
queue.submit("B");
queue.submit("C");

queue.prioritize("C");
System.out.println(queue.takeNext()); // C
System.out.println(queue.newestFirstView()); // [B, A]
~~~

Đây là mô hình đơn luồng nhằm minh họa contract của `SequencedSet`. `newestFirstView()` là **view chỉ đọc**, **không phải snapshot**; tên method nên được lựa chọn theo ý nghĩa thực tế của hệ thống. Nếu cần xử lý concurrent, phải chọn cấu trúc/thao tác phù hợp và quản lý đồng bộ. `LinkedHashSet` tự nó không thread-safe.

Nếu cần một queue cho phép ID trùng nhau, `SequencedSet` sẽ không đúng vì `Set` loại trùng; hãy cân nhắc `Deque`. Nếu cần FIFO tuyệt đối không cho reposition, đừng cung cấp `prioritize`.

## 14. Ví dụ thực tế: cấu hình có thứ tự và xem trước đảo chiều

Giả sử hệ thống hiển thị các bước cấu hình theo encounter order, cho phép di chuyển mục lên trước/cuối, nhưng API đọc cần chống caller sửa trực tiếp:

~~~java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.SequencedMap;

public final class OrderedSettings {
    private final LinkedHashMap<String,String> settings =
            new LinkedHashMap<>();

    public void putAtEnd(String key, String value) {
        settings.putLast(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value"));
    }

    public void putAtStart(String key, String value) {
        settings.putFirst(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value"));
    }

    public SequencedMap<String,String> snapshot() {
        return Collections.unmodifiableSequencedMap(
                new LinkedHashMap<>(settings));
    }

    public Map.Entry<String,String> first() {
        return settings.firstEntry();
    }
}
~~~

Ví dụ:

~~~java
OrderedSettings config = new OrderedSettings();
config.putAtEnd("locale", "vi-VN");
config.putAtEnd("theme", "dark");
config.putAtStart("theme", "light");

System.out.println(config.snapshot().sequencedKeySet());
// [theme, locale]

System.out.println(config.first());
// theme=light
~~~

Ở đây `snapshot()` copy cấu trúc map trước khi bọc; caller không thể sửa map nội bộ qua kết quả. Vì value là `String` bất biến, bản sao nông cũng đủ với mô hình này.

## 15. So sánh nhanh với những API đã có

| Nhu cầu | API hiện đại nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Đọc phần tử đầu/cuối danh sách | `list.getFirst()/getLast()` | Thống nhất với sequenced APIs |
| Duyệt List từ cuối | `list.reversed()` | Reverse view, không copy |
| Duyệt Set có thứ tự từ cuối | `sequencedSet.reversed()` | Không yêu cầu chuyển sang List |
| Đưa phần tử `LinkedHashSet` lên đầu | `set.addFirst(element)` | Có thể reposition phần tử hiện có |
| Đưa mapping `LinkedHashMap` xuống cuối | `map.putLast(key,value)` | Có thể reposition key hiện có |
| Lấy key cuối của map có thứ tự | `map.lastEntry()` | Trả entry snapshot hoặc null |
| Xem các key có thứ tự và reversible | `map.sequencedKeySet()` | View, không tự copy |
| Tạo giao diện chỉ đọc giữ order | `Collections.unmodifiableSequencedMap(...)` | View; copy backing trước nếu muốn snapshot |
| Cần sorted-order | `TreeSet`/`TreeMap` | Không ép vị trí bằng addFirst/putFirst |
| Cần random access qua chỉ số | `List` | SequencedCollection không có index |

Không cần viết thuật toán đảo mảng hay đẩy dữ liệu vào `ArrayList` chỉ để duyệt `LinkedHashSet` theo thứ tự ngược khi `reversed()` đã đáp ứng hợp đồng. Tuy nhiên, các API lâu đời như `Collections.reverse` hoặc `NavigableSet.descendingSet` **vẫn hợp lệ** trong ngữ cảnh thích hợp; mục tiêu là chọn API diễn đạt đúng ý định, không coi mọi API cũ là “legacy”.

## 16. Những lỗi phổ biến

| Nhầm lẫn | Hệ quả | Cách sửa |
| --- | --- | --- |
| `SequencedCollection` nghĩa là luôn sửa được | `UnsupportedOperationException` | Xem mutation là optional; chọn implementation/wrapper đúng |
| `reversed()` tạo copy | View vẫn liên kết backing collection | Dùng copy khi cần snapshot |
| Dùng `HashSet`/`HashMap` khi cần encounter order | Thứ tự không được bảo đảm | Dùng `LinkedHashSet`/`LinkedHashMap` hoặc sorted types |
| Coi `TreeSet.addFirst`/`TreeMap.putFirst` sẽ đổi thứ tự | Ném UOE | Sorted order do comparator quyết định |
| Dùng `getFirst()` trên collection rỗng | `NoSuchElementException` | Kiểm tra rỗng hoặc xử lý ngoại lệ theo contract |
| Nghĩ `firstEntry()` ném như `getFirst()` | Không nhận ra null | Xử lý `null` với map rỗng |
| Dùng `firstEntry().setValue(...)` | Entry snapshot không sửa map | Dùng `put`/`replace` |
| Thêm key qua `sequencedKeySet().addFirst` | Unsupported operation | Thêm qua map |
| Cho rằng `Set.equals` xét encounter order | So sánh không phát hiện đổi thứ tự | Dùng list/value object nếu order là một phần equality |
| Dùng `Map.copyOf` rồi chờ vẫn là SequencedMap | Order không có hợp đồng | Copy vào `LinkedHashMap` rồi bọc sequenced view |
| Sửa collection trong khi đang duyệt reverse view | Có thể gặp ConcurrentModificationException | Không sửa đồng thời không được đồng bộ |
| Xem `SequencedMap` như concurrent LRU cache | Race conditions và thiếu eviction policy | Thiết kế riêng cache/đồng bộ |

## 17. Checklist thiết kế và review

- [ ] Xác định thứ tự nghiệp vụ: insertion-order, access-order hay sorted-order.
- [ ] Chọn `SequencedCollection` khi cần encounter order nhưng không cần index.
- [ ] Chọn `SequencedSet` nếu cần tập hợp phần tử duy nhất có thứ tự.
- [ ] Chọn `SequencedMap` nếu cần key-value mapping có thứ tự.
- [ ] Không giả định `HashSet`/`HashMap` hay `Set.of`/`Map.of` có encounter order cố định.
- [ ] Phân biệt `addFirst/addLast` và `putFirst/putLast` là optional mutation.
- [ ] Không đặt vị trí tường minh cho sorted collections trái với comparator.
- [ ] Xác định `reversed()` là view, không phải snapshot và không tự thread-safe.
- [ ] Kiểm tra trường hợp collection/map rỗng và sự khác nhau giữa `NoSuchElementException` với `null`.
- [ ] Dùng `sequencedKeySet/Values/EntrySet` khi API đọc cần thể hiện encounter order.
- [ ] Chỉ cập nhật map qua API map, không dựa vào khả năng ghi `Map.Entry` snapshot.
- [ ] Nếu trả dữ liệu cho caller, quyết định rõ cần live view, unmodifiable view hay snapshot.
- [ ] Không quên shallow-copy caveat khi phần tử hoặc value object có thể mutable.
- [ ] Nếu dùng parallel stream, lựa chọn terminal operation phù hợp yêu cầu thứ tự.
- [ ] Test các kịch bản phần tử/key tồn tại trước khi gọi `addFirst/putLast`.
- [ ] Khi có nhiều luồng, áp dụng thread-safety và memory-visibility theo contract implementation, không dựa vào interface sequenced.

## 18. Nguồn tài liệu chính thức

- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431) — mục tiêu, thiết kế và mốc đưa ba interface vào JDK 21.
- [Java SE 27 API — SequencedCollection](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedCollection.html) — encounter order, get/add/remove ở hai đầu, reversed view.
- [Java SE 27 API — SequencedSet](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedSet.html) — giao diện kết hợp Set và SequencedCollection; equality theo Set.
- [Java SE 27 API — SequencedMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SequencedMap.html) — entry đầu/cuối, putFirst/putLast và ordered views.
- [Java SE 27 API — LinkedHashSet](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/LinkedHashSet.html) — insertion-order, addFirst/addLast và phép reposition.
- [Java SE 27 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/LinkedHashMap.html) — insertion-order/access-order và putFirst/putLast.
- [Java SE 27 API — TreeSet](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/TreeSet.html) — sorted-order, sequenced operations và các giới hạn.
- [Java SE 27 API — TreeMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/TreeMap.html) — sorted-order và putFirst/putLast không hỗ trợ.
- [Java SE 27 API — Collections](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html) — unmodifiableSequencedCollection/Set/Map wrappers.
- [Java SE — Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/27/core/creating-sequenced-collections-sets-and-maps.html) — hướng dẫn chính thức về API sequenced.

**Kết luận:** Sequenced interfaces giúp Java diễn đạt encounter order trực tiếp trong kiểu API và cung cấp thao tác thống nhất ở hai đầu cùng reverse-ordered view. Chọn đúng implementation theo **cách xác định thứ tự**, phân biệt **view với snapshot**, và xem mutation là **tùy chọn** là ba nguyên tắc quan trọng nhất khi dùng API này trong Java 27.
