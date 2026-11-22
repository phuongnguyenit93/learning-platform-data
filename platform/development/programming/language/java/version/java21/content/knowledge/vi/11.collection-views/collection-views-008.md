# Làm việc với collection immutable có hỗ trợ đọc hai đầu và reversed

Một collection không thể sửa đổi vẫn có thể cung cấp thứ tự duyệt xác định và cho phép đọc phần tử ở cả hai đầu. Từ Java 21, `SequencedCollection`, `SequencedSet` và `SequencedMap` chuẩn hóa các thao tác này, bao gồm `getFirst()`, `getLast()` và `reversed()` đối với collection, cùng các thao tác đọc đầu/cuối tương ứng đối với map.

Điểm cần chú ý là không phải mọi collection immutable đều có encounter order. `List.of()` tạo list không thể sửa đổi nhưng vẫn có thứ tự vị trí; `Set.of()` và `Map.of()` không cam kết thứ tự duyệt. Nếu cần một set hoặc map vừa không thể sửa đổi vừa giữ thứ tự, cần chọn implementation có encounter order và bọc nó bằng API sequenced phù hợp.

Trong tài liệu Java, thuật ngữ thường dùng là *unmodifiable collection*. Từ “immutable” trong bài này được dùng theo nghĩa collection không cho phép sửa đổi cấu trúc qua API collection; nó không mặc nhiên có nghĩa các object phần tử cũng bất biến sâu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Đọc phần tử đầu và cuối của collection có encounter order mà không thay đổi collection.
- Dùng `reversed()` để duyệt collection không thể sửa đổi theo chiều ngược lại.
- Phân biệt list có thứ tự với set/map không cam kết encounter order.
- Tạo sequenced set và sequenced map không thể sửa đổi mà vẫn giữ thứ tự.
- Hiểu giới hạn của unmodifiable wrapper, collection rỗng và phần tử mutable.

## 1. Collection không thể sửa đổi vẫn có thể có thứ tự

Khả năng sửa đổi và encounter order là hai đặc tính riêng:

- **Khả năng sửa đổi** cho biết chương trình có thể thêm, xóa hoặc thay thế phần tử thông qua API collection hay không.
- **Encounter order** cho biết thứ tự các phần tử được gặp khi duyệt collection.

Một list có thể không cho phép sửa đổi nhưng vẫn có thứ tự vị trí. Một set có thể không cho phép sửa đổi và có thứ tự liên kết. Ngược lại, một set không thể sửa đổi vẫn có thể không cam kết thứ tự duyệt.

| Collection | Không thể sửa đổi | Encounter order được bảo đảm | Đọc hai đầu qua Sequenced API |
|---|---|---|---|
| `List.of(...)` | Có | Có, theo thứ tự list | Có |
| `List.copyOf(source)` | Có | Có, theo thứ tự duyệt của nguồn | Có |
| `Set.of(...)` | Có | Không cam kết | Không có hợp đồng `SequencedSet` |
| `Set.copyOf(source)` | Có | Không cam kết thứ tự nguồn | Không có hợp đồng `SequencedSet` |
| `Map.of(...)` | Có | Không cam kết | Không có hợp đồng `SequencedMap` |
| `Map.copyOf(source)` | Có | Không cam kết thứ tự nguồn | Không có hợp đồng `SequencedMap` |
| `Collections.unmodifiableSequencedSet(...)` | Không qua wrapper | Có, theo sequenced set nền | Có |
| `Collections.unmodifiableSequencedMap(...)` | Không qua wrapper | Có, theo sequenced map nền | Có |

`List` mở rộng `SequencedCollection`, `SequencedSet` mở rộng `SequencedCollection` và `Set`, còn `SequencedMap` là abstraction riêng cho map có encounter order. Vì vậy, không nên chỉ nhìn thấy chữ “unmodifiable” rồi kết luận collection có thể dùng `getFirst()`, `getLast()` hoặc `reversed()`.

## 2. Đọc hai đầu của một immutable List

Trong Java 21, `List` là một `SequencedCollection`. Do đó, các list tạo bằng `List.of()` và `List.copyOf()` có thể sử dụng `getFirst()` và `getLast()`.

```java
import java.util.List;

List<String> states = List.of("queued", "running", "completed");

System.out.println(states.getFirst()); // queued
System.out.println(states.getLast());  // completed
System.out.println(states);            // [queued, running, completed]
```

Hai phương thức trên chỉ đọc phần tử ở hai đầu. Chúng không xóa hoặc thay đổi vị trí phần tử.

Nếu collection có thể rỗng, `getFirst()` và `getLast()` ném `NoSuchElementException`. Chúng không trả về `null` hoặc `Optional` khi không có phần tử. Có thể kiểm tra trước:

```java
if (!states.isEmpty()) {
    System.out.println(states.getFirst());
}
```

`List.of()` không chấp nhận phần tử `null`. `List.copyOf()` cũng không chấp nhận collection nguồn có phần tử `null`; trường hợp đó sẽ ném `NullPointerException`.

### 2.1. Tạo immutable List từ collection hiện có

`List.copyOf()` tạo list không thể sửa đổi, giữ encounter order của collection nguồn và không phản ánh những thay đổi cấu trúc tiếp theo của nguồn:

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("draft", "review"));
List<String> stable = List.copyOf(source);

source.add("published");

System.out.println(stable.getFirst()); // draft
System.out.println(stable.getLast());  // review
System.out.println(stable);            // [draft, review]
```

`stable` không thể được thêm, xóa hoặc thay thế phần tử. Các phương thức sửa đổi như `add`, `set`, `remove`, `addFirst` và `addLast` đều không được hỗ trợ.

Nếu chỉ cần cung cấp một list cố định đã biết trước, `List.of()` là lựa chọn gọn hơn. Nếu cần tạo list không thể sửa đổi từ dữ liệu hiện có, `List.copyOf()` thường thể hiện ý định rõ ràng.

## 3. Duyệt immutable collection theo chiều ngược với `reversed()`

`reversed()` được thêm vào các interface sequenced trong Java 21. Phương thức trả về một view có encounter order đảo ngược. Với immutable list, view này cũng không hỗ trợ sửa đổi.

```java
import java.util.List;
import java.util.SequencedCollection;

List<String> history = List.of("created", "validated", "stored");
SequencedCollection<String> newestFirst = history.reversed();

for (String event : newestFirst) {
    System.out.println(event);
}
```

Kết quả:

```text
stored
validated
created
```

`reversed()` không tạo một list mới bằng cách sao chép rồi đảo các phần tử. Nó trả về reverse-ordered view của collection gốc. Vì vậy, có thể dùng view này để đọc theo chiều ngược mà không phải tạo một bản sao chỉ nhằm đổi thứ tự duyệt.

### 3.1. Đọc hai đầu trên reverse view

Đầu và cuối được xác định theo encounter order của view:

```java
List<Integer> values = List.of(10, 20, 30, 40);
SequencedCollection<Integer> reverse = values.reversed();

System.out.println(reverse.getFirst()); // 40
System.out.println(reverse.getLast());  // 10
```

Với view đảo chiều, `getFirst()` tương ứng với phần tử cuối của collection gốc và `getLast()` tương ứng với phần tử đầu của collection gốc.

Có thể gọi `reversed()` trên view để lấy lại góc nhìn theo chiều ban đầu:

```java
System.out.println(reverse.reversed()); // [10, 20, 30, 40]
```

Không nên dựa vào identity của hai view để so sánh bằng `==`. Hãy quan tâm đến encounter order và hợp đồng đọc dữ liệu thay vì giả định implementation phải trả đúng cùng một object view.

### 3.2. View đảo chiều không làm collection trở nên mutable

Nếu collection gốc không hỗ trợ sửa đổi, reverse view cũng không cho phép sửa đổi:

```java
List<String> fixed = List.of("first", "second");
SequencedCollection<String> reverse = fixed.reversed();

System.out.println(reverse.getFirst()); // second

// reverse.removeFirst(); // UnsupportedOperationException
// reverse.addLast("third"); // UnsupportedOperationException
```

`reversed()` thay đổi góc nhìn về thứ tự, không thay đổi quyền sửa đổi của collection.

## 4. Vì sao Set.of và Set.copyOf không thay thế SequencedSet?

`Set.of()` và `Set.copyOf()` tạo set không thể sửa đổi, nhưng API `Set` không cam kết encounter order. Thứ tự lặp của các set này không được bảo đảm và có thể thay đổi giữa các lần chạy hoặc phiên bản runtime.

```java
Set<String> colors = Set.of("red", "green", "blue");
```

Không nên viết logic nghiệp vụ dựa trên giả định rằng phần tử đầu tiên của `colors` luôn là `red`, hoặc phần tử cuối luôn là `blue`. Kiểu trả về `Set<String>` cũng không cung cấp các phương thức `getFirst()`, `getLast()` và `reversed()`.

Nếu cần set không thể sửa đổi nhưng vẫn giữ thứ tự thêm vào, hãy tạo một `LinkedHashSet` rồi bọc nó bằng `Collections.unmodifiableSequencedSet()`.

```java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

SequencedSet<String> roles = Collections.unmodifiableSequencedSet(
    new LinkedHashSet<>(List.of("reader", "editor", "admin"))
);

System.out.println(roles.getFirst()); // reader
System.out.println(roles.getLast());  // admin
System.out.println(roles.reversed()); // [admin, editor, reader]
```

`LinkedHashSet` duy trì encounter order theo thứ tự liên kết. Wrapper sequenced không cho phép người gọi sửa set qua tham chiếu `roles`, nhưng vẫn giữ các thao tác đọc hai đầu và `reversed()`.

### 4.1. Wrapper không thể sửa đổi và snapshot có thứ tự

`Collections.unmodifiableSequencedSet(source)` là unmodifiable view được backing bởi `source`. Nếu một tham chiếu khác thay đổi set nền, view sẽ phản ánh thay đổi đó:

```java
LinkedHashSet<String> backing = new LinkedHashSet<>(List.of("reader", "editor"));
SequencedSet<String> view = Collections.unmodifiableSequencedSet(backing);

backing.addLast("admin");
System.out.println(view.getLast()); // admin
```

Nếu cần một snapshot có thứ tự và không thể sửa đổi qua API được trả về, hãy sao chép trước rồi bọc bản sao:

```java
static <E> SequencedSet<E> orderedSnapshot(SequencedSet<E> source) {
    LinkedHashSet<E> copy = new LinkedHashSet<>(source);
    return Collections.unmodifiableSequencedSet(copy);
}
```

Bản sao `LinkedHashSet` giữ encounter order của nguồn sequenced set tại thời điểm sao chép. Wrapper ngăn người nhận thay đổi cấu trúc qua API set. Không giữ hoặc chia sẻ tham chiếu mutable đến `copy` ở nơi khác nếu muốn duy trì hợp đồng snapshot.

`Collections.unmodifiableSequencedSet()` không tự sao chép dữ liệu và không làm cho các object phần tử trở nên immutable.

## 5. Làm việc với immutable SequencedMap

`Map.of()` và `Map.copyOf()` trả về map không thể sửa đổi nhưng không bảo đảm encounter order. Nếu cần đọc ánh xạ đầu/cuối hoặc duyệt map theo chiều ngược, hãy dùng `SequencedMap`.

Java 21 cung cấp các thao tác đọc trên `SequencedMap`:

| Phương thức | Ý nghĩa |
|---|---|
| `firstEntry()` | Trả entry đầu theo encounter order; trả `null` nếu map rỗng |
| `lastEntry()` | Trả entry cuối theo encounter order; trả `null` nếu map rỗng |
| `reversed()` | Trả reverse-ordered view của map |
| `sequencedKeySet()` | View các khóa theo encounter order của map |
| `sequencedValues()` | View các giá trị theo encounter order của map |
| `sequencedEntrySet()` | View các entry theo encounter order của map |

Khác với `SequencedCollection.getFirst()` và `getLast()`, `firstEntry()` và `lastEntry()` trả `null` khi map rỗng. Hãy kiểm tra null trước khi đọc key hoặc value từ entry.

### 5.1. Tạo unmodifiable map có encounter order

`LinkedHashMap` giữ thứ tự liên kết của các ánh xạ. Có thể dùng nó làm backing cho `Collections.unmodifiableSequencedMap()`:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedMap;

LinkedHashMap<String, Integer> backing = new LinkedHashMap<>();
backing.put("An", 8);
backing.put("Binh", 9);
backing.put("Chi", 10);

SequencedMap<String, Integer> scores =
    Collections.unmodifiableSequencedMap(backing);

System.out.println(scores.firstEntry()); // An=8
System.out.println(scores.lastEntry());  // Chi=10
System.out.println(scores.reversed().firstEntry()); // Chi=10
```

Wrapper giữ thứ tự của `LinkedHashMap` và ngăn thao tác ghi qua `scores`. Các thao tác như `put`, `putFirst`, `putLast`, `remove`, `pollFirstEntry` và `pollLastEntry` không được hỗ trợ qua wrapper.

### 5.2. Tạo snapshot map có thứ tự

Nếu map nguồn đã là `SequencedMap`, có thể sao chép vào `LinkedHashMap` rồi bọc unmodifiable:

```java
static <K, V> SequencedMap<K, V> orderedMapSnapshot(
        SequencedMap<K, V> source) {
    LinkedHashMap<K, V> copy = new LinkedHashMap<>(source);
    return Collections.unmodifiableSequencedMap(copy);
}
```

Constructor `LinkedHashMap` duyệt các entry của nguồn và giữ encounter order quan sát được trong quá trình sao chép. Nếu nguồn chỉ có kiểu `Map` và không có hợp đồng encounter order, không thể suy ra một thứ tự nghiệp vụ đáng tin cậy từ nó; hãy xác định thứ tự trước khi tạo snapshot.

## 6. Unmodifiable sequenced wrapper và collection factory

Java 21 bổ sung các wrapper sequenced trong `Collections`:

| Phương thức | Kiểu trả về | Mục đích |
|---|---|---|
| `unmodifiableSequencedCollection(c)` | `SequencedCollection<E>` | View không cho sửa collection có encounter order |
| `unmodifiableSequencedSet(s)` | `SequencedSet<E>` | View không cho sửa sequenced set |
| `unmodifiableSequencedMap(m)` | `SequencedMap<K, V>` | View không cho sửa sequenced map |

Các wrapper này hữu ích khi API cần công khai kiểu sequenced nhưng giới hạn quyền sửa đổi qua tham chiếu trả về. Chúng không thay thế thao tác sao chép. Nếu nguồn thay đổi qua một tham chiếu khác, wrapper vẫn đọc trạng thái mới từ nguồn.

Đối với list, `List.of()` và `List.copyOf()` đã trả về list không thể sửa đổi có encounter order. Không cần bọc lại bằng `unmodifiableSequencedCollection()` nếu API cần giữ kiểu `List` và các phương thức riêng của `List`.

Đối với set hoặc map, nếu cần encounter order, hãy chọn backing implementation có thứ tự như `LinkedHashSet` hoặc `LinkedHashMap`, sau đó dùng wrapper sequenced phù hợp. `Set.of`, `Set.copyOf`, `Map.of` và `Map.copyOf` không phải lựa chọn để bảo đảm thứ tự hai đầu.

## 7. Giới hạn của tính bất biến

Unmodifiable collection ngăn các thao tác sửa đổi qua API collection, nhưng không tự biến object phần tử thành immutable.

```java
final class UserProfile {
    private String displayName;

    UserProfile(String displayName) {
        this.displayName = displayName;
    }

    void rename(String displayName) {
        this.displayName = displayName;
    }

    String displayName() {
        return displayName;
    }
}

UserProfile user = new UserProfile("An");
List<UserProfile> users = List.of(user);

user.rename("An Nguyen");
System.out.println(users.getFirst().displayName()); // An Nguyen
```

List không thể thêm hoặc xóa phần tử, nhưng object `UserProfile` vẫn thay đổi được thông qua tham chiếu `user`. Vì vậy, khi yêu cầu dữ liệu bất biến thực sự, hãy dùng phần tử bất biến hoặc tạo bản sao phần tử theo quy tắc của domain.

Unmodifiable wrapper cũng không phải ranh giới bảo mật nếu code khác vẫn giữ tham chiếu đến backing collection. Nếu cần công bố snapshot, hãy tạo bản sao riêng rồi chỉ giữ wrapper của bản sao đó.

## 8. Collection rỗng và ngoại lệ khi đọc hai đầu

Hành vi khi collection không có phần tử cần được xử lý rõ ràng:

| API | Khi collection/map rỗng |
|---|---|
| `SequencedCollection.getFirst()` | Ném `NoSuchElementException` |
| `SequencedCollection.getLast()` | Ném `NoSuchElementException` |
| `SequencedMap.firstEntry()` | Trả `null` |
| `SequencedMap.lastEntry()` | Trả `null` |
| `reversed()` | Trả view đảo chiều rỗng |

Ví dụ:

```java
List<String> empty = List.of();
System.out.println(empty.reversed()); // []

// empty.getFirst(); // NoSuchElementException
```

Với map:

```java
SequencedMap<String, Integer> emptyMap =
    Collections.unmodifiableSequencedMap(new LinkedHashMap<>());

System.out.println(emptyMap.firstEntry()); // null
System.out.println(emptyMap.lastEntry());  // null
```

Không nên dùng cùng một cách kiểm tra cho collection và map. Với collection, kiểm tra `isEmpty()` trước khi gọi `getFirst()` hoặc `getLast()`. Với map, kiểm tra entry trả về có null hay không.

## 9. Chọn API theo yêu cầu

| Yêu cầu | Lựa chọn phù hợp |
|---|---|
| List cố định, cần đọc đầu/cuối và đảo chiều | `List.of()` hoặc `List.copyOf()` |
| Set không thể sửa đổi, cần giữ thứ tự thêm vào | `Collections.unmodifiableSequencedSet(new LinkedHashSet<>(...))` |
| Map không thể sửa đổi, cần giữ thứ tự ánh xạ | `Collections.unmodifiableSequencedMap(new LinkedHashMap<>(...))` |
| Chỉ cần chặn ghi qua một tham chiếu, vẫn muốn nhìn thấy thay đổi nguồn | Unmodifiable sequenced wrapper trên backing collection hiện có |
| Cần snapshot độc lập có thứ tự | Sao chép vào `LinkedHashSet`/`LinkedHashMap` rồi bọc unmodifiable |
| Chỉ cần set/map không thể sửa đổi, không yêu cầu thứ tự | `Set.of`/`Set.copyOf` hoặc `Map.of`/`Map.copyOf` |

Trước khi chọn API, hãy xác định:

1. Có cần encounter order ổn định không?
2. Có cần đọc phần tử đầu/cuối hoặc duyệt ngược không?
3. Collection cần là snapshot hay view phản ánh thay đổi của nguồn?
4. Người nhận có được phép sửa cấu trúc collection không?
5. Các object phần tử có mutable không?
6. Collection hoặc map có thể rỗng không?

## 10. Nguyên tắc sử dụng

- Dùng `getFirst()` và `getLast()` khi collection có encounter order và cần đọc hai đầu.
- Dùng `reversed()` để đọc theo chiều ngược; nhớ rằng kết quả là view.
- Dùng `List.of()` hoặc `List.copyOf()` khi cần list không thể sửa đổi mà vẫn giữ thứ tự.
- Không dựa vào thứ tự của `Set.of`, `Set.copyOf`, `Map.of` hoặc `Map.copyOf`.
- Dùng `Collections.unmodifiableSequencedSet` hoặc `unmodifiableSequencedMap` khi cần wrapper sequenced không cho ghi.
- Sao chép vào `LinkedHashSet` hoặc `LinkedHashMap` trước khi bọc nếu cần snapshot giữ thứ tự liên kết.
- Phân biệt unmodifiable collection với deep immutable object graph.
- Xử lý riêng collection rỗng và map rỗng theo hợp đồng của từng phương thức đọc.

Java 21 cho phép đọc hai đầu và duyệt ngược trên các collection có encounter order thông qua Sequenced Collections. Khi kết hợp đúng API tạo collection không thể sửa đổi với implementation có thứ tự, chương trình có thể công bố dữ liệu chỉ đọc mà vẫn giữ được thứ tự và các thao tác đọc cần thiết.

## Tài liệu tham khảo

- [Java SE 21 API — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): `getFirst`, `getLast`, `reversed` và encounter order.
- [Java SE 21 API — `SequencedSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): sequenced set và reverse-ordered view.
- [Java SE 21 API — `SequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): first/last entry, sequenced views và reverse-ordered map.
- [Java SE 21 API — `Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): unmodifiable sequenced wrappers.
- [Java SE 21 API — `List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): `of`, `copyOf` và encounter order của list.
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431): mục tiêu thiết kế và các API sequenced được bổ sung trong Java 21.
