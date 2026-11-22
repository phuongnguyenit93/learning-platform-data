# Quan hệ của List và Deque với SequencedCollection

Từ Java 21, `List` và `Deque` cùng mở rộng `SequencedCollection`. Interface này chuẩn hóa cách biểu diễn một collection có thứ tự gặp (encounter order), có phần tử đầu và cuối, hỗ trợ thao tác ở hai đầu và cung cấp view đảo thứ tự bằng `reversed()`.

`List` vẫn giữ khả năng truy cập theo chỉ số; `Deque` vẫn giữ các thao tác queue và stack ở hai đầu. `SequencedCollection` tạo ra phần giao nhau để API có thể làm việc với cả hai kiểu collection mà không cần phụ thuộc vào cấu trúc dữ liệu cụ thể.

## 1. Vì sao Java 21 bổ sung SequencedCollection?

Trước Java 21, `List` và `Deque` đều có encounter order, nhưng chúng nằm ở các nhánh khác nhau của Collections Framework. `List` mô tả một dãy phần tử theo vị trí; `Deque` mô tả một hàng đợi hai đầu và đồng thời là một `Queue`.

Vì thiếu một superinterface chung diễn đạt rõ ràng khái niệm thứ tự, một API muốn nhận collection có thứ tự thường phải chọn `List` dù không cần truy cập theo index, hoặc chọn `Collection` rồi mô tả yêu cầu về thứ tự bằng tài liệu riêng.

Java 21 đưa vào ba interface:

- `SequencedCollection<E>`: collection có encounter order.
- `SequencedSet<E>`: set có encounter order, kết hợp ngữ nghĩa của `Set` và `SequencedCollection`.
- `SequencedMap<K,V>`: map có thứ tự gặp của các mapping.

Bài này tập trung vào quan hệ giữa `List`, `Deque` và `SequencedCollection`.

## 2. Vị trí trong hệ thống interface

Quan hệ kế thừa trong Java 21 có thể đọc qua các khai báo rút gọn sau:

~~~java
public interface SequencedCollection<E> extends Collection<E> {
    // Sáu default method đầu/cuối được trình bày ở mục tiếp theo.
    SequencedCollection<E> reversed();
}

public interface List<E> extends SequencedCollection<E> {
    // Các thao tác đặc trưng của List:
    // get(index), add(index, element), set(index, element), listIterator(), ...
}

public interface Deque<E> extends Queue<E>, SequencedCollection<E> {
    // Các thao tác đặc trưng của Deque:
    // offerFirst/Last, pollFirst/Last, peekFirst/Last,
    // push, pop, descendingIterator, ...
}
~~~

Sơ đồ quan hệ:

~~~text
Collection
├── SequencedCollection
│   ├── List
│   └── Deque
└── Queue
    └── Deque (cùng interface Deque như nhánh trên)
~~~

Sơ đồ trên chỉ thể hiện các nhánh liên quan. Chính xác hơn, `Deque` mở rộng cả `Queue` và `SequencedCollection`; `Queue` cũng là một subinterface của `Collection`.

Điểm cần nhớ:

- `List` có `SequencedCollection` làm superinterface trực tiếp.
- `Deque` cũng có `SequencedCollection` làm superinterface trực tiếp, đồng thời mở rộng `Queue`.
- `ArrayList` là một implementation của `List`.
- `ArrayDeque` là một implementation của `Deque`.
- `LinkedList` triển khai cả `List` và `Deque`, vì vậy có thể dùng nó ở cả hai vai trò.

`SequencedCollection` không thay thế `List` hoặc `Deque`. Nó bổ sung một kiểu trừu tượng chung để mô tả đặc tính thứ tự mà hai interface này cùng có.

## 3. Các thao tác đầu và cuối được chuẩn hóa

`SequencedCollection` định nghĩa sáu thao tác làm việc với hai đầu:

| Phương thức | Ý nghĩa |
|---|---|
| `addFirst(e)` | Thêm phần tử vào đầu encounter order |
| `addLast(e)` | Thêm phần tử vào cuối encounter order |
| `getFirst()` | Lấy phần tử đầu mà không xóa |
| `getLast()` | Lấy phần tử cuối mà không xóa |
| `removeFirst()` | Xóa và trả về phần tử đầu |
| `removeLast()` | Xóa và trả về phần tử cuối |

Đây là các thao tác tùy chọn đối với việc thay đổi collection. Implementation không hỗ trợ sửa đổi, chẳng hạn một unmodifiable list, có thể ném `UnsupportedOperationException` khi gọi các thao tác thêm hoặc xóa.

Nếu collection rỗng, `getFirst()`, `getLast()`, `removeFirst()` và `removeLast()` ném `NoSuchElementException`. Vì vậy, nếu collection có thể rỗng, hãy kiểm tra `isEmpty()` trước khi gọi các phương thức này.

### Cách List triển khai các thao tác đầu/cuối

Với `List`, các phương thức mới có ý nghĩa theo vị trí index:

| Phương thức sequenced | Hành vi tương ứng của List |
|---|---|
| `addFirst(e)` | `add(0, e)` |
| `addLast(e)` | `add(e)` |
| `getFirst()` | `get(0)` |
| `getLast()` | `get(size() - 1)` |
| `removeFirst()` | `remove(0)` |
| `removeLast()` | `remove(size() - 1)` |

Ví dụ:

~~~java
List<String> names = new ArrayList<>(
    List.of("An", "Bình", "Chi")
);

names.addFirst("Mở đầu");
names.addLast("Kết thúc");

System.out.println(names.getFirst()); // Mở đầu
System.out.println(names.getLast());  // Kết thúc

String first = names.removeFirst();
String last = names.removeLast();
~~~

`addFirst` thêm phần tử mới ở vị trí đầu, không thay thế phần tử đang ở đó. `List` vẫn cho phép phần tử trùng lặp nếu implementation của list cho phép.

Các thao tác index vẫn là đặc trưng của `List`. `SequencedCollection` không cung cấp `get(int)`, `set(int, E)` hoặc `listIterator()`.

### Cách Deque triển khai các thao tác đầu/cuối

`Deque` đã có các phương thức như `addFirst`, `addLast`, `getFirst`, `getLast`, `removeFirst` và `removeLast` trước Java 21. Java 21 đưa những thao tác này lên `SequencedCollection` để collection có thứ tự khác cũng có thể dùng cùng một hợp đồng API.

Với `Deque`, đầu và cuối thường được gọi là head và tail:

~~~java
Deque<String> tasks = new ArrayDeque<>();

tasks.addFirst("Khẩn cấp");
tasks.addLast("Bình thường");

System.out.println(tasks.getFirst()); // Khẩn cấp
System.out.println(tasks.getLast());  // Bình thường

String urgent = tasks.removeFirst();
String normal = tasks.removeLast();
~~~

`Deque` còn có các phương thức đặc trưng như `offerFirst`, `offerLast`, `pollFirst`, `pollLast`, `peekFirst`, `peekLast`, `push` và `pop`. Các phương thức này không nằm trong `SequencedCollection`, vì chúng thể hiện hành vi queue/stack cụ thể.

## 4. Viết API dùng chung cho List và Deque

Nếu một phương thức chỉ cần đọc hoặc thao tác ở hai đầu của một collection có thứ tự, có thể khai báo tham số là `SequencedCollection<E>`.

~~~java
static <E> void printEnds(SequencedCollection<E> elements) {
    if (elements.isEmpty()) {
        System.out.println("Collection rỗng");
        return;
    }

    System.out.println("Đầu: " + elements.getFirst());
    System.out.println("Cuối: " + elements.getLast());
}
~~~

Cả `List` và `Deque` đều truyền được vào phương thức:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình", "Chi"));
Deque<String> queue = new ArrayDeque<>(List.of("A", "B", "C"));

printEnds(names);
printEnds(queue);
~~~

Chọn kiểu tham số theo đúng nhu cầu của API:

| Nhu cầu | Kiểu nên dùng |
|---|---|
| Chỉ cần encounter order và thao tác đầu/cuối | `SequencedCollection<E>` |
| Cần index, `subList`, `ListIterator` hoặc hợp đồng equality của List | `List<E>` |
| Cần queue/stack, offer/poll/peek ở hai đầu | `Deque<E>` |
| Không cần bảo đảm thứ tự gặp | `Collection<E>` |

Dùng `SequencedCollection` giúp API bớt phụ thuộc vào một cấu trúc dữ liệu cụ thể. Tuy nhiên, nó không đảm bảo collection có thể sửa đổi, cũng không đảm bảo độ phức tạp thời gian của thao tác đầu/cuối.

## 5. reversed() trả về view đảo thứ tự

`SequencedCollection` định nghĩa `reversed()` để cung cấp một view có encounter order đảo ngược.

Nếu collection ban đầu có thứ tự:

~~~text
A → B → C → D
~~~

thì view đảo thứ tự có thứ tự:

~~~text
D → C → B → A
~~~

Trong view:

- Phần tử đầu là phần tử cuối của collection gốc.
- Phần tử cuối là phần tử đầu của collection gốc.
- Successor và predecessor được đảo chiều.
- Iterator, stream và các thao tác nhạy với thứ tự hoạt động theo hướng đảo ngược.

`List` và `Deque` override phương thức này với kiểu trả về cụ thể hơn:

~~~java
List<E> reversedList = list.reversed();
Deque<E> reversedDeque = deque.reversed();
~~~

Đây là covariant return type: kiểu trả về vẫn giữ được khả năng sử dụng các thao tác đặc trưng của `List` hoặc `Deque`, thay vì chỉ nhận được `SequencedCollection`.

Ví dụ với List:

~~~java
List<String> names = new ArrayList<>(
    List.of("An", "Bình", "Chi")
);

List<String> reverseNames = names.reversed();

System.out.println(names);        // [An, Bình, Chi]
System.out.println(reverseNames); // [Chi, Bình, An]

System.out.println(reverseNames.getFirst()); // Chi
System.out.println(reverseNames.getLast());  // An
~~~

Ví dụ với Deque:

~~~java
Deque<Integer> numbers = new ArrayDeque<>(
    List.of(10, 20, 30)
);

Deque<Integer> reverseNumbers = numbers.reversed();

System.out.println(reverseNumbers); // [30, 20, 10]
System.out.println(reverseNumbers.getFirst()); // 30
~~~

`reversed()` trả về view, không phải yêu cầu tạo một bản sao độc lập. Nếu view hỗ trợ sửa đổi, thao tác qua view sẽ được ghi xuống collection nền. Việc thay đổi trực tiếp collection nền có được phản ánh trong view hay không phụ thuộc implementation.

Nếu cần một bản sao độc lập theo thứ tự đảo ngược, hãy tạo collection mới từ view:

~~~java
List<String> reversedCopy = new ArrayList<>(names.reversed());
~~~

Cần phân biệt:

- `names.reversed()`: tạo view đảo thứ tự.
- `new ArrayList<>(names.reversed())`: tạo một list mới chứa các phần tử theo thứ tự đảo.

## 6. Ý nghĩa của reversed() đối với hai interface

### Với List

View đảo thứ tự vẫn là `List`, nên các thao tác index được diễn giải theo thứ tự mới:

~~~java
List<String> values = new ArrayList<>(
    List.of("A", "B", "C")
);

List<String> reverse = values.reversed();

System.out.println(reverse.get(0)); // C
System.out.println(reverse.get(1)); // B
System.out.println(reverse.get(2)); // A
~~~

Các thao tác đầu/cuối cũng đổi hướng tương ứng. Ví dụ `reverse.addFirst("X")` sẽ thêm phần tử ở đầu view, tức vị trí cuối của list gốc, nếu implementation hỗ trợ sửa đổi.

### Với Deque

View đảo thứ tự vẫn là `Deque`. Các khái niệm head/tail được đảo trong view. Vì thế, `getFirst()` trên view trả về phần tử cuối của deque gốc; `addFirst` trên view tương ứng thêm vào đầu đối diện của deque gốc.

`Deque` vốn có `descendingIterator()` để duyệt ngược. `reversed()` cung cấp một view đầy đủ hơn: ngoài việc duyệt ngược, nó còn cho phép dùng các thao tác đầu/cuối, queue và stack theo thứ tự đảo ngược nếu implementation hỗ trợ.

## 7. Tính khả biến và giới hạn của implementation

Việc một collection triển khai `SequencedCollection` không có nghĩa mọi thao tác đều sửa đổi được collection.

Ví dụ, `List.of` trả về list không hỗ trợ sửa đổi:

~~~java
List<String> fixed = List.of("An", "Bình", "Chi");

System.out.println(fixed.getFirst()); // An
System.out.println(fixed.getLast());  // Chi

// Ném UnsupportedOperationException
fixed.addFirst("Mở đầu");
~~~

Các phương thức đọc đầu/cuối vẫn dùng được. Những phương thức thêm/xóa là optional operations và có thể ném `UnsupportedOperationException`.

Ngoài ra, `SequencedCollection` chỉ chuẩn hóa ngữ nghĩa thứ tự và các thao tác ở hai đầu. Nó không cam kết độ phức tạp:

- Thêm ở đầu `ArrayList` thường cần dịch chuyển các phần tử hiện có.
- `ArrayDeque` được thiết kế cho thao tác ở hai đầu.
- `LinkedList` triển khai cả `List` và `Deque`, nhưng truy cập theo index không có đặc tính truy cập ngẫu nhiên như `ArrayList`.

Hãy chọn implementation theo workload thực tế và hợp đồng API, không suy luận hiệu năng chỉ từ kiểu `SequencedCollection`.

## 8. Một số điểm tương thích cần nhớ

- `List` và `Deque` đều có thứ tự gặp trước Java 21; Java 21 chuẩn hóa đặc tính chung đó qua `SequencedCollection`.
- Những phương thức đầu/cuối mới của `List` được thêm dưới dạng default methods, vì vậy implementation của `List` có thể kế thừa hành vi dựa trên các thao tác index hiện có.
- `Deque` tiếp tục giữ hợp đồng queue và stack. `SequencedCollection` không thay thế `Queue` và không thêm các phương thức `offer`, `poll` hoặc `peek`.
- `reversed()` trả về view có kiểu trả về covariant ở `List` và `Deque`.
- `SequencedCollection` không định nghĩa lại `equals` và `hashCode`. Ngữ nghĩa equality vẫn do subinterface cụ thể quyết định; `List` so sánh theo nội dung và thứ tự, còn `Set` có hợp đồng equality riêng.

## 9. Checklist khi thiết kế API

- [ ] Dùng `SequencedCollection` nếu API chỉ cần collection có encounter order và thao tác ở hai đầu.
- [ ] Dùng `List` nếu cần truy cập theo index hoặc các thao tác đặc trưng của list.
- [ ] Dùng `Deque` nếu cần queue/stack hoặc các thao tác offer/poll/peek.
- [ ] Kiểm tra collection rỗng trước khi gọi `getFirst`, `getLast`, `removeFirst` hoặc `removeLast`.
- [ ] Xác định implementation có hỗ trợ sửa đổi trước khi gọi các thao tác add/remove.
- [ ] Dùng `reversed()` khi cần view đảo thứ tự; tạo collection mới nếu cần bản sao độc lập.
- [ ] Không suy luận hiệu năng của thao tác đầu/cuối chỉ từ kiểu `SequencedCollection`.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API — List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)
- [Java SE 21 API — Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html)
- [Java SE 21 API — ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html)
- [Java SE 21 API — ArrayDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html)
- [JEP 431: Sequenced Collections](https://openjdk.org/jeps/431)
- [Oracle Java 21 Core Libraries — Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html)

