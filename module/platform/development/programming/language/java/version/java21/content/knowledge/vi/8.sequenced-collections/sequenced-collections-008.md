# Các thao tác tùy chọn và `UnsupportedOperationException`

## 1. Sequenced Collections không đồng nghĩa với collection có thể thay đổi

Java 21 bổ sung các interface `SequencedCollection`, `SequencedSet` và `SequencedMap` để mô tả những collection có **encounter order** rõ ràng và hỗ trợ truy cập phần tử ở hai đầu theo thứ tự đó. Các interface này cung cấp những thao tác như `getFirst()`, `getLast()`, `addFirst()`, `addLast()`, `removeFirst()`, `removeLast()` hoặc `putFirst()` và `putLast()`.

Việc một đối tượng triển khai `SequencedCollection` hay `SequencedMap` chỉ cho biết nó có thứ tự và cung cấp API theo thứ tự. Điều đó **không đảm bảo mọi thao tác thay đổi đều được hỗ trợ**. Một implementation có thể cho phép đọc nhưng không cho phép thêm, xóa hoặc di chuyển phần tử. Đây là lý do các API Java Collections sử dụng khái niệm *optional operation* (thao tác tùy chọn).

Ví dụ, cả `ArrayList` có thể thay đổi và list được tạo bằng `List.of(...)` đều là `List`, do đó cũng là `SequencedCollection`. Tuy nhiên, chúng có khả năng thay đổi khác nhau:

```java
List<String> editable = new ArrayList<>(List.of("A", "B"));
editable.addFirst("START"); // Được hỗ trợ

List<String> readOnly = List.of("A", "B");
readOnly.addFirst("START"); // Ném UnsupportedOperationException
```

Để dùng các thao tác đầu/cuối đúng cách, cần kiểm tra hợp đồng của implementation cụ thể thay vì chỉ nhìn vào kiểu interface.

## 2. Thao tác tùy chọn là gì?

Một thao tác tùy chọn là thao tác mà hợp đồng interface cho phép implementation không hỗ trợ. Nếu không hỗ trợ, implementation có thể ném `UnsupportedOperationException` (UOE) khi caller yêu cầu thực hiện thao tác đó.

Trong Collections Framework, các thao tác thay đổi thường là optional operations. Ví dụ ở `Collection` có `add`, `remove`, `addAll`, `removeAll`, `retainAll`, `clear` và thao tác xóa qua iterator. Với các sequenced interface, những thao tác bổ sung làm thay đổi thứ tự hoặc nội dung ở hai đầu cũng có thể là optional operations.

| Interface | Thao tác có thể là optional operation | Ý nghĩa |
|---|---|---|
| `SequencedCollection` | `addFirst`, `addLast`, `removeFirst`, `removeLast` | Thêm hoặc xóa phần tử ở đầu/cuối encounter order |
| `SequencedSet` | `addFirst`, `addLast` và các thao tác xóa kế thừa | Thêm/xóa phần tử có ảnh hưởng đến tập hợp và thứ tự |
| `SequencedMap` | `putFirst`, `putLast`, `pollFirstEntry`, `pollLastEntry` | Thêm/cập nhật entry ở đầu/cuối hoặc lấy và xóa entry ở hai đầu |
| Các collection view | `add`, `remove`, `clear`, `Iterator.remove` và các thao tác thay đổi khác | Phụ thuộc view có cho phép thay đổi collection nền hay không |

Không phải mọi method trong các interface này đều là thao tác tùy chọn. Các method truy vấn như `getFirst()`, `getLast()`, `firstEntry()` và `lastEntry()` không thay đổi collection. Chúng thường trả về phần tử/entry đầu hoặc cuối; nếu collection rỗng, `getFirst()` và `getLast()` ném `NoSuchElementException`, còn `firstEntry()` và `lastEntry()` của `SequencedMap` trả về `null`.

## 3. `UnsupportedOperationException` biểu thị điều gì?

`UnsupportedOperationException` là unchecked exception trong Java, kế thừa `RuntimeException`. Nó cho biết đối tượng được gọi không hỗ trợ thao tác được yêu cầu. Vì là unchecked exception, method không cần khai báo UOE trong `throws` và caller không bắt buộc phải catch.

Ví dụ:

```java
SequencedCollection<String> values = List.of("first", "second");

System.out.println(values.getFirst()); // first
values.addLast("third");               // UnsupportedOperationException
```

Đọc phần tử vẫn hợp lệ; thêm phần tử không được hỗ trợ bởi list không thể thay đổi này. UOE không có nghĩa toàn bộ object không thể sử dụng, mà chỉ cho biết thao tác cụ thể không được implementation hỗ trợ.

### 3.1. Phân biệt UOE với exception do trạng thái dữ liệu

Không nên nhầm UOE với các exception khác:

| Exception | Ý nghĩa điển hình | Ví dụ |
|---|---|---|
| `UnsupportedOperationException` | Implementation không hỗ trợ thao tác | Gọi `addFirst` trên sequenced collection không cho phép thêm |
| `NoSuchElementException` | Không có phần tử để lấy/xóa bằng thao tác yêu cầu phần tử tồn tại | Gọi `getFirst()` trên collection rỗng |
| `NullPointerException` | Đầu vào `null` không được implementation chấp nhận | Thêm key hoặc element `null` vào collection không cho phép null |
| `ClassCastException` | Giá trị có kiểu không phù hợp với giới hạn kiểu của collection | Thêm object không tương thích vào collection có kiểm tra kiểu runtime |

Một collection có thể hỗ trợ `removeFirst()` nhưng ném `NoSuchElementException` khi rỗng. Một collection khác có thể không hỗ trợ xóa và ném UOE cho thao tác đó. Nguyên nhân khác nhau nên cách xử lý cũng khác nhau.

## 4. Khả năng thay đổi của `SequencedCollection`

`SequencedCollection` bổ sung các method đầu/cuối cho collection có thứ tự:

- `getFirst()` và `getLast()` đọc phần tử ở hai đầu.
- `addFirst(element)` và `addLast(element)` thêm phần tử ở hai đầu nếu implementation hỗ trợ.
- `removeFirst()` và `removeLast()` lấy ra đồng thời xóa phần tử ở hai đầu nếu implementation hỗ trợ.
- `reversed()` trả về một view có encounter order đảo ngược.

Ví dụ với list có thể thay đổi:

```java
List<String> tasks = new ArrayList<>(List.of("review", "build"));

tasks.addFirst("prepare");
tasks.addLast("release");

System.out.println(tasks);           // [prepare, review, build, release]
System.out.println(tasks.getFirst()); // prepare
System.out.println(tasks.getLast());  // release

String first = tasks.removeFirst();
String last = tasks.removeLast();
```

Các thao tác trên thay đổi nội dung list. Với implementation không hỗ trợ thêm hoặc xóa, method tương ứng có thể ném UOE.

### 4.1. Thao tác đầu/cuối không nhất thiết được hỗ trợ đồng nhất

Khả năng hỗ trợ từng thao tác phụ thuộc vào cấu trúc collection. Ví dụ, `SortedSet` là một sequenced set nhưng thứ tự của nó được xác định bởi thứ tự tự nhiên hoặc comparator. Caller không thể ép một phần tử vào đầu/cuối nếu điều đó vi phạm thứ tự sắp xếp. Vì vậy, các method `addFirst()` và `addLast()` được `SortedSet` cung cấp dưới dạng thao tác không hỗ trợ và ném UOE.

```java
SequencedSet<Integer> sorted = new TreeSet<>();
sorted.add(10); // Được hỗ trợ
sorted.add(5);  // Được hỗ trợ; thứ tự vẫn do comparator quyết định

sorted.addFirst(20); // UnsupportedOperationException
sorted.addLast(30);  // UnsupportedOperationException
```

`TreeSet` vẫn cho phép thêm/xóa theo hợp đồng `Set`, nhưng không cho caller điều khiển vị trí đầu/cuối trái với thứ tự sắp xếp. Đây là ví dụ cho thấy một implementation có thể hỗ trợ một số thao tác thay đổi và từ chối các thao tác khác.

## 5. Thao tác tùy chọn trên `SequencedMap`

`SequencedMap` cung cấp API làm việc với entry ở đầu/cuối encounter order:

- `firstEntry()` và `lastEntry()` đọc entry đầu/cuối mà không xóa.
- `pollFirstEntry()` và `pollLastEntry()` lấy và xóa entry đầu/cuối nếu implementation hỗ trợ xóa.
- `putFirst(key, value)` và `putLast(key, value)` đặt entry ở đầu/cuối nếu implementation hỗ trợ điều khiển thứ tự.
- `reversed()` tạo view của map với thứ tự entry đảo ngược.
- `sequencedKeySet()`, `sequencedValues()` và `sequencedEntrySet()` cung cấp các view có thứ tự tương ứng.

Ví dụ với `LinkedHashMap`:

```java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();

scores.putLast("An", 8);
scores.putLast("Binh", 9);
scores.putFirst("Chi", 10);

System.out.println(scores.firstEntry()); // Chi=10
System.out.println(scores.lastEntry());  // Binh=9

var reverseView = scores.reversed();
System.out.println(reverseView);         // Binh, An, Chi

var removed = scores.pollFirstEntry();   // Lấy và xóa Chi=10
```

`LinkedHashMap` duy trì encounter order và hỗ trợ các thao tác định vị entry ở hai đầu. Ngược lại, `SortedMap` xác định thứ tự bằng comparator hoặc thứ tự tự nhiên; các thao tác `putFirst()` và `putLast()` không được hỗ trợ vì chúng sẽ đi ngược thứ tự đã xác định.

```java
SequencedMap<String, Integer> sortedMap = new TreeMap<>();
sortedMap.put("B", 2); // Được hỗ trợ
sortedMap.put("A", 1); // Được hỗ trợ; thứ tự theo key

sortedMap.putFirst("Z", 26); // UnsupportedOperationException
sortedMap.putLast("C", 3);   // UnsupportedOperationException
```

Các thao tác `put` thông thường vẫn được hỗ trợ. Chỉ các thao tác cố tình đặt entry ở vị trí đầu/cuối trái với thứ tự sắp xếp mới bị từ chối.

## 6. `reversed()` là view, không phải bản sao độc lập

`reversed()` trả về một view có encounter order ngược với collection hoặc map ban đầu. Nó không mặc định tạo một bản sao mới. Thay đổi được hỗ trợ thông qua view có thể tác động đến collection nền và ngược lại.

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C"));
var reversed = original.reversed();

System.out.println(reversed); // [C, B, A]

reversed.addFirst("D");
System.out.println(original); // [A, B, C, D]
```

`addFirst("D")` trên view đảo ngược tương ứng với việc thêm ở cuối collection ban đầu. Nếu collection nền không hỗ trợ thao tác thêm, view đảo ngược cũng không thể biến thao tác đó thành được hỗ trợ.

Đối với map, `reversed()` cũng là view có thứ tự entry đảo ngược. `putFirst` trên reversed view tương ứng với đặt entry ở cuối map gốc nếu implementation hỗ trợ thao tác đó.

Không nên coi `reversed()` là cơ chế tạo snapshot bất biến. Nếu cần một bản sao độc lập, hãy tạo collection mới từ view và chọn rõ chính sách có thể thay đổi hay không.

## 7. Unmodifiable collection và các thao tác bị từ chối

Java cung cấp các factory như `List.of(...)`, `Set.of(...)`, `Map.of(...)`, `List.copyOf(...)` và các wrapper trong `Collections` để tạo collection không thể thay đổi qua API được trả về. Java 21 bổ sung wrapper theo sequenced interface, chẳng hạn `Collections.unmodifiableSequencedCollection(...)`, `Collections.unmodifiableSequencedSet(...)` và `Collections.unmodifiableSequencedMap(...)`.

Ví dụ:

```java
List<String> source = new ArrayList<>(List.of("draft", "published"));
SequencedCollection<String> view =
        Collections.unmodifiableSequencedCollection(source);

System.out.println(view.getFirst()); // draft
view.addLast("archived");           // UnsupportedOperationException
```

Wrapper cho phép đọc thông qua view nhưng từ chối các thao tác làm thay đổi collection qua chính view đó.

### 7.1. Unmodifiable view và immutable value

Hai khái niệm này liên quan nhưng không hoàn toàn giống nhau:

| Loại | Đặc điểm | Ví dụ |
|---|---|---|
| Unmodifiable view | Không thể sửa qua view; thay đổi trên collection nền vẫn có thể được nhìn thấy | `Collections.unmodifiableSequencedCollection(source)` |
| Collection không thể thay đổi được tạo từ factory/copy | Không cung cấp cách thay đổi cấu trúc collection qua API trả về; không có collection nền do caller giữ để cập nhật view | `List.of(...)`, `List.copyOf(...)` |

Ví dụ view phản ánh thay đổi từ collection nền:

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
SequencedCollection<String> view =
        Collections.unmodifiableSequencedCollection(source);

source.addFirst("START");
System.out.println(view); // [START, A, B]
```

View không cho phép caller thêm hoặc xóa phần tử thông qua `view`, nhưng owner vẫn có thể thay đổi `source`. Vì thế, nếu cần bảo vệ trạng thái khỏi mọi thay đổi bên ngoài, cần kiểm soát cả quyền truy cập đến collection nền.

Ngoài ra, unmodifiable collection thường chỉ đảm bảo cấu trúc collection không bị thay đổi qua API của nó. Nếu phần tử bên trong là object mutable, trạng thái của các phần tử vẫn có thể thay đổi. Đây là tính bất biến nông (shallow immutability), không phải bất biến sâu của toàn bộ object graph.

## 8. Cách xử lý `UnsupportedOperationException`

Khi nhận một `SequencedCollection` hoặc `SequencedMap` từ code khác, không thể chỉ dựa vào kiểu interface để kết luận thao tác thay đổi sẽ thành công. Có một số cách thiết kế an toàn:

1. **Quy định rõ hợp đồng đầu vào**: nếu method cần thêm/xóa phần tử, mô tả rõ rằng collection truyền vào phải hỗ trợ thao tác tương ứng.
2. **Tạo bản sao có thể thay đổi khi cần quyền sở hữu riêng**: dùng `new ArrayList<>(source)` hoặc `new LinkedHashMap<>(source)` rồi thay đổi bản sao.
3. **Trả về kiểu không thể thay đổi khi chỉ muốn cung cấp dữ liệu đọc**: dùng `List.copyOf`, `Collections.unmodifiableSequencedCollection` hoặc wrapper tương ứng.
4. **Dùng cấu trúc phù hợp với thứ tự**: nếu cần điều khiển đầu/cuối, chọn implementation hỗ trợ thứ tự có thể cập nhật như `ArrayList`, `LinkedList`, `LinkedHashSet` hoặc `LinkedHashMap`; nếu cần thứ tự sắp xếp, dùng `TreeSet`/`TreeMap` và không gọi thao tác định vị đầu/cuối.
5. **Không dùng exception làm phép thử khả năng hỗ trợ**: hiểu hợp đồng của implementation và thiết kế API theo yêu cầu thay đổi ngay từ đầu.

Ví dụ tạo bản sao có thể thay đổi trước khi thêm phần tử:

```java
static <E> List<E> withMarker(SequencedCollection<E> input, E marker) {
    List<E> result = new ArrayList<>(input);
    result.addFirst(marker);
    return result;
}
```

Method trên không cố thay đổi collection mà caller truyền vào. Nó tạo một list mới, sở hữu riêng, rồi thêm marker vào đầu. Cách này phù hợp khi API chỉ cần tạo kết quả mới và không có yêu cầu cập nhật collection nguồn.

### 8.1. Có nên catch `UnsupportedOperationException` không?

Chỉ catch UOE khi chương trình có một cách xử lý hợp lệ cho trường hợp implementation không hỗ trợ thao tác. Ví dụ, một adapter có thể chuyển sang tạo bản sao nếu việc thay đổi tại chỗ chỉ là tối ưu. Không nên catch UOE một cách tổng quát rồi bỏ qua, vì thao tác quan trọng có thể đã không được thực hiện và trạng thái chương trình sẽ sai.

```java
// Không nên: che giấu việc cập nhật không thành công.
try {
    collection.addLast(value);
} catch (UnsupportedOperationException ignored) {
    // Bỏ qua khiến caller tưởng rằng value đã được thêm.
}
```

Nếu thao tác là yêu cầu bắt buộc, hãy để lỗi được truyền lên hoặc chuyển sang một chiến lược được xác định rõ, chẳng hạn tạo và trả về bản sao mới.

## 9. Những điều cần kiểm tra trước khi gọi thao tác

| Câu hỏi | Lý do |
|---|---|
| Collection có encounter order rõ ràng không? | Các thao tác đầu/cuối dựa trên thứ tự đó |
| Implementation có hỗ trợ thêm/xóa không? | Các method mutator có thể là optional operations |
| Thứ tự có bị cố định bởi comparator không? | `SortedSet`/`SortedMap` không cho phép ép vị trí đầu/cuối tùy ý |
| Đối tượng là collection mutable, unmodifiable view hay collection không thể thay đổi? | Quyết định thao tác nào có thể thành công và thay đổi có phản ánh qua view không |
| Collection có đang được chia sẻ giữa nhiều thành phần không? | Thay đổi có thể ảnh hưởng đến các caller khác; cần quy định quyền sở hữu và đồng bộ phù hợp |
| Collection có rỗng không? | Các method yêu cầu phần tử như `getFirst`/`removeFirst` có thể ném `NoSuchElementException` |

Đừng suy luận khả năng thay đổi chỉ từ `SequencedCollection`, `SequencedSet` hoặc `SequencedMap`. Hãy dựa trên hợp đồng của implementation, wrapper và view thực tế đang sử dụng.

## 10. Tài liệu tham khảo chính thức

- [Java SE 21 API — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): thao tác đầu/cuối, `reversed()` và optional operations.
- [Java SE 21 API — `SequencedSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): sequenced set và các thao tác vị trí.
- [Java SE 21 API — `SequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): thao tác entry ở đầu/cuối và các sequenced views.
- [Java SE 21 API — `SortedSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) và [ `SortedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html): các thao tác đầu/cuối không được hỗ trợ khi thứ tự do sắp xếp quyết định.
- [Java SE 21 API — `Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): các wrapper unmodifiable cho sequenced collection, set và map.
- [Java SE 21 API — `UnsupportedOperationException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsupportedOperationException.html): ý nghĩa của exception khi thao tác không được hỗ trợ.

Khi sử dụng Sequenced Collections, hãy phân biệt rõ thao tác truy vấn và thao tác thay đổi. Interface cung cấp cách làm việc thống nhất với thứ tự, còn khả năng thêm, xóa hoặc di chuyển phần tử phụ thuộc vào implementation. `UnsupportedOperationException` là tín hiệu rằng thao tác cụ thể không được hỗ trợ; hãy thiết kế hợp đồng và quyền sở hữu collection rõ ràng để tránh phụ thuộc vào khả năng thay đổi không được bảo đảm.
