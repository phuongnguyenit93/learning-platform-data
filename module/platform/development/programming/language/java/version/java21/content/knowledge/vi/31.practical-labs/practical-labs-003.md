# Thiết kế API thao tác hai đầu với SequencedCollection, Set và Map

Java 21 bổ sung hệ thống **Sequenced Collections** để biểu diễn collection có encounter order rõ ràng và cung cấp thao tác thống nhất ở hai đầu. Khi thiết kế API, có thể dùng `SequencedCollection<E>` cho chuỗi phần tử, `SequencedSet<E>` cho tập phần tử duy nhất có thứ tự và `SequencedMap<K,V>` cho ánh xạ có thứ tự.

Bài thực hành xây dựng ba thành phần: lịch sử có giới hạn dung lượng, tập nhãn có thứ tự và registry ánh xạ có thứ tự. Mỗi API hỗ trợ đọc, thêm hoặc loại bỏ ở đầu và cuối; đồng thời phân biệt reverse view với snapshot để tránh vô tình cho caller sửa trạng thái nội bộ.

## 1. Yêu cầu thiết kế

Giả sử một dịch vụ cần lưu lịch sử thao tác gần đây, duy trì thứ tự ưu tiên của nhãn và đăng ký các endpoint theo thứ tự xử lý. API cần đáp ứng:

- Đọc phần tử đầu tiên và cuối cùng.
- Thêm hoặc đưa phần tử lên đầu/cuối khi implementation hỗ trợ.
- Loại bỏ phần tử ở đầu/cuối.
- Duyệt theo thứ tự ngược mà không phải tự đảo collection.
- Giữ đúng ngữ nghĩa riêng của List, Set và Map.
- Quy định rõ collection mutable hay immutable, view có được phép ghi hay chỉ đọc.
- Không phụ thuộc vào thứ tự của `HashSet` hoặc `HashMap`.

## 2. Chọn đúng interface và implementation

| Nhu cầu | Interface nên khai báo | Implementation thường dùng |
|---|---|---|
| Chuỗi phần tử, cho phép trùng lặp, thao tác hai đầu | `SequencedCollection<E>` hoặc `Deque<E>` nếu cần queue API | `ArrayDeque`, `LinkedList` |
| Phần tử duy nhất, giữ thứ tự chèn hoặc thứ tự ưu tiên | `SequencedSet<E>` | `LinkedHashSet` |
| Key duy nhất, giữ thứ tự mapping | `SequencedMap<K,V>` | `LinkedHashMap` |
| Thứ tự được xác định bởi comparator | `SequencedSet<E>` / `SequencedMap<K,V>` qua `SortedSet` / `SortedMap` | `TreeSet`, `TreeMap` |

`HashSet` và `HashMap` không cung cấp encounter order ổn định nên không phù hợp nếu API cần thao tác hai đầu theo thứ tự. `LinkedHashSet` và `LinkedHashMap` phù hợp với thứ tự chèn có thể điều chỉnh.

`TreeSet` và `TreeMap` cũng là sequenced collections, nhưng thứ tự của chúng do comparator hoặc natural ordering quyết định. Các thao tác tùy ý đặt phần tử ở đầu/cuối như `addFirst`, `addLast`, `putFirst` và `putLast` không phù hợp với thứ tự được sắp xếp và có thể ném `UnsupportedOperationException`.

## 3. Các thao tác hai đầu trong API Java 21

`SequencedCollection<E>` cung cấp các thao tác chung:

| Phương thức | Ý nghĩa | Khi collection rỗng hoặc không hỗ trợ |
|---|---|---|
| `addFirst(e)` | Thêm phần tử vào đầu encounter order | Có thể ném `UnsupportedOperationException` nếu không hỗ trợ ghi |
| `addLast(e)` | Thêm phần tử vào cuối encounter order | Có thể ném `UnsupportedOperationException` nếu không hỗ trợ ghi |
| `getFirst()` | Đọc phần tử đầu | Ném `NoSuchElementException` nếu rỗng |
| `getLast()` | Đọc phần tử cuối | Ném `NoSuchElementException` nếu rỗng |
| `removeFirst()` | Xóa và trả phần tử đầu | Ném `NoSuchElementException` nếu rỗng |
| `removeLast()` | Xóa và trả phần tử cuối | Ném `NoSuchElementException` nếu rỗng |
| `reversed()` | Trả về reverse-ordered view | Không đảo dữ liệu gốc tại thời điểm gọi |

Với `SequencedSet<E>`, các thao tác đầu/cuối giữ tính duy nhất. Với `SequencedMap<K,V>`, thao tác tương ứng làm việc trên mapping:

| SequencedSet | SequencedMap | Ý nghĩa |
|---|---|---|
| `addFirst(e)` | `putFirst(k, v)` | Đặt phần tử/mapping ở đầu |
| `addLast(e)` | `putLast(k, v)` | Đặt phần tử/mapping ở cuối |
| `getFirst()` | `firstEntry()` | Đọc phần tử/mapping đầu |
| `getLast()` | `lastEntry()` | Đọc phần tử/mapping cuối |
| `removeFirst()` | `pollFirstEntry()` | Xóa phần tử/mapping đầu và trả về |
| `removeLast()` | `pollLastEntry()` | Xóa phần tử/mapping cuối và trả về |
| `reversed()` | `reversed()` | Reverse view có encounter order ngược |

Khác biệt cần nhớ: `SequencedMap.firstEntry()` và `lastEntry()` trả về `null` khi map rỗng; `pollFirstEntry()` và `pollLastEntry()` cũng trả `null` khi không có mapping. `SequencedCollection.getFirst()` và `getLast()` ném `NoSuchElementException` khi rỗng.

## 4. Thực hành A: xây dựng lịch sử có dung lượng giới hạn

Yêu cầu: lưu tối đa N sự kiện theo thứ tự cũ đến mới. Khi thêm sự kiện mới ở cuối và vượt dung lượng, loại sự kiện cũ nhất ở đầu. Caller cần snapshot theo cả hai hướng.

`ArrayDeque` là lựa chọn phù hợp vì hỗ trợ thao tác hai đầu hiệu quả, cho phép phần tử trùng lặp và không cho phép `null`.

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class RecentHistory<E> {
    private final Deque<E> events = new ArrayDeque<>();
    private final int capacity;

    public RecentHistory(int capacity) {
        if (capacity < 1) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    public void record(E event) {
        events.addLast(Objects.requireNonNull(event, "event"));
        while (events.size() > capacity) {
            events.removeFirst();
        }
    }

    public Optional<E> oldest() {
        return Optional.ofNullable(events.peekFirst());
    }

    public Optional<E> newest() {
        return Optional.ofNullable(events.peekLast());
    }

    public Optional<E> removeOldest() {
        return Optional.ofNullable(events.pollFirst());
    }

    public Optional<E> removeNewest() {
        return Optional.ofNullable(events.pollLast());
    }

    public List<E> oldestFirstSnapshot() {
        return List.copyOf(events);
    }

    public List<E> newestFirstSnapshot() {
        return List.copyOf(events.reversed());
    }
}
```

`record()` thêm ở cuối vì sự kiện mới nhất phải nằm cuối encounter order. Khi vượt capacity, `removeFirst()` loại sự kiện cũ nhất. `peekFirst()` và `peekLast()` trả `null` nếu rỗng nên được chuyển thành `Optional`.

Các phương thức snapshot dùng `List.copyOf(...)`: caller nhận một list độc lập, không thể sửa list trả về và không làm thay đổi lịch sử nội bộ. Vì `ArrayDeque` không cho phép `null`, `List.copyOf` không gặp vấn đề với phần tử null.

## 5. Dùng SequencedCollection làm kiểu tham số tổng quát

Nếu API chỉ cần đọc encounter order và tạo snapshot đảo chiều, không cần phụ thuộc vào `Deque` hoặc một implementation cụ thể:

```java
import java.util.List;
import java.util.SequencedCollection;

static <E> List<E> reverseSnapshot(SequencedCollection<E> source) {
    return List.copyOf(source.reversed());
}
```

Phương thức chấp nhận các implementation sequenced khác nhau, chẳng hạn `ArrayList`, `LinkedList` hoặc `ArrayDeque`. Kiểu tham số càng tổng quát thì API càng dễ tái sử dụng; chỉ dùng `Deque` khi cần thêm các thao tác queue/stack như `offer`, `poll` hoặc `push`.

## 6. Thực hành B: tập nhãn duy nhất có thứ tự

Yêu cầu: quản lý tập nhãn của một bản ghi. Nhãn không được trùng, nhưng caller có thể đưa một nhãn hiện có lên đầu hoặc cuối để thay đổi thứ tự ưu tiên.

`LinkedHashSet` triển khai `SequencedSet`. Khi phần tử đã có trong set, `addFirst` hoặc `addLast` sẽ định vị lại phần tử đó ở đầu/cuối thay vì tạo phần tử trùng.

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.SequencedSet;

public final class OrderedTags<E> {
    private final SequencedSet<E> tags = new LinkedHashSet<>();

    public void prioritize(E tag) {
        tags.addFirst(Objects.requireNonNull(tag, "tag"));
    }

    public void addLowestPriority(E tag) {
        tags.addLast(Objects.requireNonNull(tag, "tag"));
    }

    public E highestPriority() {
        return tags.getFirst();
    }

    public E lowestPriority() {
        return tags.getLast();
    }

    public E removeHighestPriority() {
        return tags.removeFirst();
    }

    public E removeLowestPriority() {
        return tags.removeLast();
    }

    public List<E> snapshot() {
        return List.copyOf(tags);
    }

    public List<E> reverseSnapshot() {
        return List.copyOf(tags.reversed());
    }
}
```

Ví dụ:

```java
OrderedTags<String> tags = new OrderedTags<>();
tags.addLowestPriority("java");
tags.addLowestPriority("database");
tags.addLowestPriority("observability");
tags.prioritize("database");

System.out.println(tags.snapshot());
// [database, java, observability]
```

`database` đã tồn tại nên được chuyển lên đầu. Set vẫn chỉ có một phần tử `"database"`.

Không dựa vào `Set.equals()` để kiểm tra thứ tự. Equality của `Set` chỉ xét thành viên; hai set có cùng phần tử nhưng encounter order khác nhau vẫn bằng nhau theo hợp đồng `Set`.

## 7. Thực hành C: registry có thứ tự bằng SequencedMap

Yêu cầu: lưu các handler theo thứ tự ưu tiên. Có thể đăng ký mapping ở đầu/cuối, đọc mapping ưu tiên nhất/thấp nhất, loại bỏ mapping ở hai đầu và xem thứ tự ngược.

`LinkedHashMap` là implementation phù hợp cho thứ tự có thể điều chỉnh. API bên ngoài dùng `SequencedMap<K,V>` để biểu đạt rõ hợp đồng thứ tự.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.SequencedMap;

public final class OrderedRegistry<K, V> {
    public record Mapping<K, V>(K key, V value) {}

    private final SequencedMap<K, V> entries = new LinkedHashMap<>();

    public void registerFirst(K key, V value) {
        entries.putFirst(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value"));
    }

    public void registerLast(K key, V value) {
        entries.putLast(
                Objects.requireNonNull(key, "key"),
                Objects.requireNonNull(value, "value"));
    }

    public Optional<Mapping<K, V>> first() {
        return Optional.ofNullable(copy(entries.firstEntry()));
    }

    public Optional<Mapping<K, V>> last() {
        return Optional.ofNullable(copy(entries.lastEntry()));
    }

    public Optional<Mapping<K, V>> removeFirst() {
        return Optional.ofNullable(copy(entries.pollFirstEntry()));
    }

    public Optional<Mapping<K, V>> removeLast() {
        return Optional.ofNullable(copy(entries.pollLastEntry()));
    }

    public List<K> keysOldestFirst() {
        return List.copyOf(entries.sequencedKeySet());
    }

    public List<Mapping<K, V>> newestFirstSnapshot() {
        List<Mapping<K, V>> result = new ArrayList<>();
        for (Map.Entry<K, V> entry
                : entries.reversed().sequencedEntrySet()) {
            result.add(new Mapping<>(entry.getKey(), entry.getValue()));
        }
        return List.copyOf(result);
    }

    public SequencedMap<K, V> newestFirstReadOnlyView() {
        return Collections.unmodifiableSequencedMap(entries.reversed());
    }

    private Mapping<K, V> copy(Map.Entry<K, V> entry) {
        return entry == null ? null : new Mapping<>(entry.getKey(), entry.getValue());
    }
}
```

`registerFirst` và `registerLast` dùng `putFirst`/`putLast`. Nếu key đã tồn tại, mapping được cập nhật và định vị lại ở đầu/cuối. `firstEntry`/`lastEntry` đọc mapping ở hai đầu; `pollFirstEntry`/`pollLastEntry` loại mapping và trả kết quả, hoặc `null` nếu map rỗng.

`Mapping` là snapshot của một cặp key/value, giúp caller không giữ một `Map.Entry` đang gắn với map nội bộ. Đây là bản sao nông: nếu key hoặc value là object mutable, record vẫn giữ reference tới object đó. `newestFirstSnapshot()` tạo list độc lập theo thứ tự ngược. `newestFirstReadOnlyView()` trả về view không cho caller ghi nhưng vẫn được backing map cập nhật; đây là view sống, không phải snapshot.

Ví dụ sử dụng:

```java
OrderedRegistry<String, String> registry = new OrderedRegistry<>();
registry.registerLast("search", "SearchHandler");
registry.registerLast("billing", "BillingHandler");
registry.registerFirst("health", "HealthHandler");

System.out.println(registry.keysOldestFirst());
// [health, search, billing]

registry.registerFirst("billing", "NewBillingHandler");
System.out.println(registry.keysOldestFirst());
// [billing, health, search]

System.out.println(registry.newestFirstSnapshot());
// [Mapping[key=search, value=SearchHandler],
//  Mapping[key=health, value=HealthHandler],
//  Mapping[key=billing, value=NewBillingHandler]]
```

## 8. Reverse view và snapshot có hợp đồng khác nhau

`reversed()` trả về một view có encounter order ngược. Với các collection mutable hỗ trợ thao tác tương ứng, thay đổi qua view được phản ánh vào collection gốc và ngược lại.

| Cách trả dữ liệu | Có phản ánh cập nhật về sau? | Caller có thể ghi? | Dùng khi |
|---|---|---|---|
| `source.reversed()` | Có, vì là backed view | Có thể, tùy collection và operation | Caller được phép thao tác trực tiếp trên view |
| `Collections.unmodifiableSequencedCollection(source.reversed())` | Có, vẫn là view sống | Không qua wrapper | Muốn cung cấp view chỉ đọc nhưng phản ánh trạng thái mới |
| `List.copyOf(source.reversed())` | Không | Không | Muốn trả snapshot bất biến tại thời điểm gọi |
| `new LinkedHashMap<>(map.reversed())` | Không | Bản sao có thể mutable | Muốn tạo map độc lập giữ thứ tự đảo ngược |

`reversed().reversed()` trả lại collection gốc theo hợp đồng Sequenced Collections. Không gọi `Collections.reverse(...)` nếu mục tiêu chỉ là cung cấp thứ tự duyệt ngược: phương thức đó thay đổi list tại chỗ, trong khi `reversed()` tạo view.

## 9. Các view của SequencedMap

`SequencedMap` cung cấp ba view có encounter order:

- `sequencedKeySet()` trả về `SequencedSet<K>` theo thứ tự key.
- `sequencedValues()` trả về `SequencedCollection<V>` theo thứ tự mapping.
- `sequencedEntrySet()` trả về `SequencedSet<Map.Entry<K,V>>` theo thứ tự entry.

Các view này được backing bởi map. Xóa key qua `sequencedKeySet()` hoặc xóa entry qua `sequencedEntrySet()` có thể làm thay đổi map gốc nếu operation được hỗ trợ. Không nên đưa mutable view ra khỏi lớp quản lý dữ liệu nếu caller không được phép sửa trạng thái.

Ví dụ tạo snapshot key theo thứ tự ưu tiên:

```java
List<String> keys = List.copyOf(registryMap.sequencedKeySet());
List<String> reverseKeys =
        List.copyOf(registryMap.reversed().sequencedKeySet());
```

`Map.equals()` không xét encounter order. Để kiểm thử hoặc hiển thị thứ tự mapping, hãy duyệt `sequencedEntrySet()` hoặc chuyển key/entry sang `List` snapshot.

## 10. Kiểm thử hợp đồng thao tác hai đầu

Các test nên xác minh cả dữ liệu và encounter order. Ví dụ với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedMap;
import java.util.SequencedSet;
import org.junit.jupiter.api.Test;

class SequencedApiTest {
    @Test
    void listReverseViewUsesReverseOrderAndWritesThrough() {
        List<String> original =
                new ArrayList<>(List.of("A", "B", "C"));
        List<String> reversed = original.reversed();

        assertIterableEquals(List.of("C", "B", "A"), reversed);
        reversed.addFirst("D");
        assertIterableEquals(List.of("A", "B", "C", "D"), original);
        assertSame(original, reversed.reversed());
    }

    @Test
    void sequencedSetRepositionsAnExistingElement() {
        SequencedSet<String> tags = new LinkedHashSet<>();
        tags.addLast("A");
        tags.addLast("B");
        tags.addLast("C");

        tags.addFirst("B");

        assertIterableEquals(List.of("B", "A", "C"),
                new ArrayList<>(tags));
    }

    @Test
    void sequencedMapCanMoveAnExistingMappingToTheEnd() {
        SequencedMap<String, Integer> map = new LinkedHashMap<>();
        map.putLast("A", 1);
        map.putLast("B", 2);
        map.putLast("C", 3);

        map.putLast("B", 20);

        assertIterableEquals(List.of("A", "C", "B"),
                new ArrayList<>(map.sequencedKeySet()));
        assertEquals(20, map.get("B"));
        assertEquals(map, map.reversed());
    }
}
```

Test đầu xác nhận reverse view của List vừa có thứ tự ngược vừa ghi xuyên về list gốc. Test set xác nhận phần tử trùng được định vị lại mà không tạo bản sao. Test map xác nhận mapping hiện có có thể chuyển xuống cuối và `Map.equals()` vẫn không phải assertion về thứ tự.

Với `Set` và `Map`, luôn chuyển encounter order thành list hoặc dùng `assertIterableEquals`. `assertEquals(setA, setB)` và `assertEquals(mapA, mapB)` chỉ xác minh equality theo hợp đồng Set/Map, không xác minh thứ tự duyệt.

## 11. Giới hạn theo implementation

Không phải mọi `SequencedCollection` đều hỗ trợ mọi thao tác ghi:

- `List.of(...)` là immutable; thao tác ghi qua view cũng bị từ chối.
- `Arrays.asList(...)` cho phép thay thế phần tử nhưng không hỗ trợ thay đổi kích thước; `set` có thể hoạt động trong khi `addFirst` hoặc `removeLast` không hoạt động.
- `ArrayDeque` hỗ trợ thao tác hai đầu nhưng không cho phép `null`.
- `LinkedHashSet` và `LinkedHashMap` cho phép điều chỉnh encounter order bằng các phương thức đầu/cuối.
- `TreeSet` và `TreeMap` duy trì thứ tự sắp xếp; không thể tùy ý chèn một phần tử vào đầu/cuối nếu vị trí đó trái comparator.
- Wrapper unmodifiable giữ khả năng đọc/reverse nhưng chặn các thao tác ghi qua wrapper.

Các thao tác `addFirst`, `addLast`, `putFirst` và `putLast` có thể là optional operations. Thiết kế API nên mô tả rõ implementation được yêu cầu hỗ trợ thao tác nào và xử lý `UnsupportedOperationException` ở ranh giới phù hợp.

## 12. Null, empty và lỗi API

Chọn chính sách null ngay từ đầu. `ArrayDeque` không cho phép null; `LinkedHashSet` và `LinkedHashMap` có thể cho phép null tùy implementation. Ví dụ trong bài chủ động từ chối null bằng `Objects.requireNonNull` để tránh nhầm null với kết quả rỗng.

Với collection:

- Dùng `getFirst()`/`getLast()` nếu collection rỗng là trạng thái lỗi theo hợp đồng; chúng ném `NoSuchElementException`.
- Dùng `peekFirst()`/`peekLast()` của `Deque` nếu muốn nhận `null` khi rỗng, sau đó có thể chuyển thành `Optional` nếu null không được lưu.
- Dùng `pollFirst()`/`pollLast()` để xóa an toàn khi rỗng mà không ném `NoSuchElementException`.

Với map, `firstEntry`, `lastEntry`, `pollFirstEntry` và `pollLastEntry` trả `null` nếu map rỗng. Nếu map cho phép null value, hãy phân biệt rõ entry không tồn tại với entry có value null; record snapshot hoặc `Optional<Mapping<K,V>>` giúp thể hiện trạng thái này rõ hơn.

## 13. Thread safety và quyền sở hữu view

`ArrayDeque`, `LinkedHashSet` và `LinkedHashMap` không tự trở thành thread-safe chỉ vì chúng triển khai Sequenced interfaces. Reverse view và các view của map cũng chia sẻ backing collection, nên việc đọc/ghi đồng thời vẫn cần đồng bộ phù hợp.

Trong API production:

- Giữ collection mutable ở bên trong lớp quản lý nếu caller không cần quyền ghi.
- Trả snapshot bất biến khi caller chỉ cần dữ liệu tại thời điểm gọi.
- Chỉ trả backed view khi muốn caller nhìn thấy cập nhật mới và đã xác định rõ quyền đọc/ghi.
- Nếu chia sẻ giữa nhiều thread, dùng lock hoặc cấu trúc đồng thời phù hợp; không giả định reverse view tự cung cấp đồng bộ.
- Không duyệt collection trong khi thread khác sửa cấu trúc nếu implementation không hỗ trợ concurrency đó.

## 14. Chọn API nào cho từng bài toán?

| Bài toán | Lựa chọn | Lý do |
|---|---|---|
| Lịch sử sự kiện giới hạn N phần tử | `Deque<E>` / `ArrayDeque<E>` | Thêm cuối, bỏ đầu, đọc hai đầu hiệu quả |
| Danh sách ưu tiên không trùng | `SequencedSet<E>` / `LinkedHashSet<E>` | Duy trì uniqueness và có thể đưa phần tử lên đầu/cuối |
| Registry có thứ tự mapping | `SequencedMap<K,V>` / `LinkedHashMap<K,V>` | Quản lý mapping và reposition theo hai đầu |
| Dữ liệu có thứ tự comparator | `SortedSet`/`SortedMap` qua Sequenced interfaces | Thứ tự do comparator quyết định, không tùy ý reposition |
| Caller cần dữ liệu ổn định tại thời điểm trả về | Snapshot bằng `List.copyOf` hoặc bản sao có thứ tự | Không để caller quan sát thay đổi sau đó |
| Caller cần view luôn phản ánh dữ liệu mới | `reversed()` hoặc unmodifiable sequenced wrapper | View sống, chia sẻ backing collection |

## 15. Bài tập tự thực hành

1. Mở rộng `RecentHistory<E>` với `removeNewest()` và phương thức trả về sự kiện ở vị trí đầu/cuối mà không làm thay đổi lịch sử.
2. Thêm `moveToFront(E)` vào `OrderedTags<E>`; nếu nhãn chưa có thì thêm mới, nếu đã có thì chuyển lên đầu.
3. Bổ sung `moveToEnd(K,V)` cho `OrderedRegistry<K,V>` và xác định hành vi khi key đã tồn tại.
4. Viết test chứng minh `reversed().reversed()` trả lại collection gốc.
5. Viết test xác nhận mutation qua reverse view cập nhật backing collection.
6. Viết test với `List.of(...)` và xác nhận thao tác ghi ném `UnsupportedOperationException`.
7. Thử `TreeSet`/`TreeMap` và ghi nhận vì sao thao tác add/put vào đầu/cuối không phù hợp với thứ tự comparator.
8. Thay API trả mutable view bằng snapshot bất biến, sau đó so sánh hành vi khi backing collection thay đổi.

## 16. Biên dịch với Java 21

Sequenced Collections được hoàn thiện trong Java 21 qua JEP 431. Các interface và phương thức trong bài là API final, không cần bật Preview.

```bash
javac --release 21 -d out src/RecentHistory.java
```

Khi biên dịch dự án thực tế, đặt toolchain/release bằng 21 và dùng JDK 21 để chạy. Nếu chạy trên JDK mới hơn, các API Sequenced Collections vẫn là API chuẩn; kiểm tra tài liệu runtime tương ứng cho những thay đổi khác ngoài phạm vi bài này.

## 17. Tài liệu tham khảo

- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API — SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Java SE 21 API — Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html)
- [Java SE 21 API — LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html)
- [Java SE 21 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)
- [Java SE 21 API — Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html)
