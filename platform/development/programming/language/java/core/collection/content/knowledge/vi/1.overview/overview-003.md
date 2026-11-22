# Quan hệ Iterable, Collection, List, Set, Queue và Deque

Khi chọn cấu trúc dữ liệu trong Java, câu hỏi đầu tiên không phải là “dùng lớp nào?”, mà là “đoạn mã cần hợp đồng nào?”. Chỉ cần duyệt các phần tử, cần truy cập theo vị trí, cần loại bỏ phần tử trùng, hay cần lấy phần tử ở một hoặc hai đầu? Sáu interface trong bài này mô tả các nhu cầu đó ở những mức khác nhau.

Một đối tượng có thể được nhìn qua nhiều interface. Chẳng hạn, một `ArrayList<String>` đồng thời là `List<String>`, `Collection<String>` và `Iterable<String>`. Đây là cùng một đối tượng, không phải ba bản sao. Kiểu của biến quyết định những thao tác mà trình biên dịch cho phép gọi qua biến đó; lớp thực tế quyết định cách thao tác được thực hiện.

## 1. Bản đồ các hợp đồng

| Interface | Câu hỏi mà hợp đồng trả lời | Đặc điểm chính |
| --- | --- | --- |
| `Iterable<E>` | Có thể duyệt lần lượt các phần tử bằng iterator không? | Cung cấp điểm bắt đầu duyệt; không mặc nhiên có kích thước hay thao tác thêm/xóa. |
| `Collection<E>` | Có thể làm việc với một tập hợp phần tử như một đơn vị không? | Có các thao tác chung như kiểm tra kích thước, kiểm tra chứa phần tử và các thao tác thay đổi tùy chọn. |
| `List<E>` | Có cần một dãy có vị trí và truy cập theo chỉ số không? | Thứ tự của dãy có ý nghĩa; cho phép phần tử trùng theo hợp đồng chung. |
| `Set<E>` | Có cần bảo đảm không chứa phần tử trùng không? | Tính duy nhất là đặc điểm cốt lõi; thứ tự phụ thuộc hợp đồng cụ thể. |
| `Queue<E>` | Có cần thêm phần tử chờ xử lý và lấy phần tử ở đầu hàng không? | Cách xác định phần tử ở đầu phụ thuộc loại hàng đợi, không nhất thiết là FIFO. |
| `Deque<E>` | Có cần thao tác ở cả đầu và cuối dãy không? | Hàng đợi hai đầu; có thể dùng theo cách FIFO hoặc LIFO. |

`E` là tham số kiểu của phần tử, ví dụ `String`, `Integer` hoặc `Order`. Các interface này không phải các lớp lưu trữ cụ thể.

`Iterable` thuộc gói `java.lang`, được nhập ngầm như `String`. Các interface còn lại trong danh sách thuộc `java.util`.

## 2. Quan hệ kế thừa và khác biệt phiên bản

Trong Java 17, các quan hệ `extends` trực tiếp giữa sáu interface được biểu diễn như sau. Mũi tên đi từ interface con lên interface cha:

~~~mermaid
flowchart BT
    C["Collection<E>"] -->|extends| I["Iterable<E>"]
    L["List<E>"] -->|extends| C
    S["Set<E>"] -->|extends| C
    Q["Queue<E>"] -->|extends| C
    D["Deque<E>"] -->|extends| Q
~~~

Từ sơ đồ có thể suy ra:

- Mọi `List`, `Set`, `Queue` và `Deque` đều là `Collection`, nên đều là `Iterable`.
- Mọi `Deque` đều là `Queue`; chiều ngược lại không đúng.
- Không phải mọi `Iterable` đều là `Collection`.
- `List`, `Set` và `Queue` không kế thừa lẫn nhau.
- `Deque` không kế thừa `List`, dù cả hai có thể biểu diễn dữ liệu theo một thứ tự.

### Từ Java 21: có thêm SequencedCollection

Từ Java 21, Java bổ sung các interface cho tập hợp có thứ tự duyệt xác định, trong đó có `SequencedCollection<E>`. Khi mô tả quan hệ trực tiếp, cần cập nhật:

| Interface | Java 17 | Từ Java 21 |
| --- | --- | --- |
| `Collection<E>` | Kế thừa `Iterable<E>` | Vẫn kế thừa `Iterable<E>`. |
| `List<E>` | Kế thừa trực tiếp `Collection<E>` | Kế thừa `SequencedCollection<E>`, rồi đến `Collection<E>`. |
| `Set<E>` | Kế thừa `Collection<E>` | Vẫn kế thừa `Collection<E>`; không phải mọi `Set` đều có thứ tự duyệt xác định. |
| `Queue<E>` | Kế thừa `Collection<E>` | Vẫn kế thừa `Collection<E>`. |
| `Deque<E>` | Kế thừa `Queue<E>` | Kế thừa cả `Queue<E>` và `SequencedCollection<E>`. |

`SequencedCollection<E>` kế thừa `Collection<E>`. `SequencedSet<E>` kết hợp hợp đồng của `Set<E>` với `SequencedCollection<E>`. Điều này không biến mọi `Set` thành một dãy có chỉ số.

Các thao tác như `getFirst()`, `getLast()` và `reversed()` có thể xuất hiện qua hợp đồng sequenced ở Java 21. `reversed()` cung cấp một góc nhìn theo thứ tự ngược, không phải lệnh tự đảo dãy tại chỗ. Khả năng thêm/xóa vẫn phụ thuộc hỗ trợ của đối tượng cụ thể.

Những suy luận về kiểu con giữa sáu interface ở trên vẫn đúng. Thay đổi quan trọng là không vẽ `List extends Collection` như một quan hệ trực tiếp cho Java 21. Các ví dụ chạy trong bài chỉ sử dụng API có từ Java 17 để người học có thể chạy trên Java 17 trở lên.

## 3. Iterable: khả năng duyệt, chưa phải tập hợp

Hợp đồng trung tâm của `Iterable<E>` là cung cấp `iterator()`. Vòng lặp for-each có thể dùng iterator đó để lấy từng phần tử.

~~~java
// Đoạn mã trong một phương thức; không phải chương trình độc lập.
Iterable<String> values = List.of("A", "B");

for (String value : values) {
    System.out.println(value);
}
~~~

Qua biến `values`, có thể duyệt nhưng không thể gọi `size()`, `add(...)` hoặc `get(...)`, vì những phương thức đó không thuộc hợp đồng `Iterable`.

`Iterable` không yêu cầu đối tượng phải lưu toàn bộ dữ liệu sẵn trong bộ nhớ. Nó có thể đại diện cho một nguồn tạo phần tử khi duyệt. Chỉ biết một đối tượng là `Iterable` chưa đủ để kết luận:

- Có thể biết trước số phần tử hay không.
- Có thể chỉnh sửa nguồn hay không.
- Dữ liệu có hữu hạn hay không.
- Các lần duyệt có cho cùng kết quả hay không.

### Iterable và Iterator là hai vai trò khác nhau

`Iterable` là đối tượng cung cấp cách bắt đầu duyệt. `Iterator` giữ trạng thái của một lượt duyệt, với các thao tác như `hasNext()` và `next()`.

Không dùng hai tên này thay thế nhau. `Iterator` không kế thừa `Iterable`, và không thể mặc nhiên đưa một biến `Iterator` vào for-each. Một iterator đã đi qua phần tử cũng không tự quay lại đầu.

Mảng Java dùng được trong for-each nhưng không triển khai `Iterable`. Cú pháp for-each hỗ trợ riêng cả mảng lẫn đối tượng `Iterable`; sự giống nhau về cú pháp không chứng minh quan hệ kế thừa.

## 4. Collection: hợp đồng chung cho tập hợp phần tử

`Collection<E>` bổ sung các thao tác chung cho một tập hợp phần tử, chẳng hạn:

- `size()`, `isEmpty()`: hỏi về kích thước và trạng thái rỗng.
- `contains(Object)`: hỏi một phần tử có thuộc tập hợp không.
- `iterator()`: duyệt các phần tử.
- `add(E)`, `remove(Object)`, `clear()`: các thao tác thay đổi tùy chọn.
- `addAll(...)`, `containsAll(...)`, `removeAll(...)`: làm việc với nhiều phần tử.
- `toArray()`, `stream()`: chuyển sang các cách xử lý khác.

Chỉ biết một đối tượng là `Collection` không cho biết nó có cho phép trùng phần tử, có thứ tự nào, có cho phép `null`, có an toàn khi dùng đồng thời hay không. Những điều đó phải được xác định từ interface cụ thể hơn và lớp triển khai.

### Có phương thức không có nghĩa là được phép thay đổi

`Collection` khai báo các thao tác thay đổi, nhưng nhiều thao tác là tùy chọn. Ví dụ:

~~~java
// Đoạn mã minh họa trong một phương thức.
Collection<String> values = List.of("A", "B");

// values.add("C"); // Biên dịch được, nhưng nếu chạy sẽ ném UnsupportedOperationException.
~~~

`List.of(...)` trả về một danh sách không cho sửa đổi cấu trúc hay thay thế phần tử. Việc gán nó cho biến `Collection` không làm nó trở thành đối tượng có thể chỉnh sửa.

Một ví dụ khác là `Arrays.asList(...)`: danh sách có kích thước cố định, cho phép `set(...)` nhưng không hỗ trợ `add(...)` hoặc `remove(...)` để đổi kích thước. Vì vậy, “không sửa được”, “kích thước cố định” và “có thể sửa” là những khả năng khác nhau.

## 5. List: dãy có vị trí

`List<E>` mô tả một dãy mà vị trí của phần tử có ý nghĩa. Chỉ số bắt đầu từ `0`.

~~~java
// Cần import java.util.ArrayList và java.util.List.
List<String> names = new ArrayList<>(List.of("An", "Bình", "An"));

System.out.println(names.get(1)); // Bình
System.out.println(names.size()); // 3
~~~

Hai phần tử `"An"` cùng tồn tại vì `List` không đặt điều kiện duy nhất như `Set`.

Các thao tác thể hiện đặc điểm của `List` gồm `get(index)`, `set(index, value)`, `add(index, value)`, `remove(index)` và `listIterator()`.

Cần phân biệt:

- **Có thứ tự**: các phần tử tạo thành một dãy với các vị trí xác định.
- **Đã sắp xếp**: các phần tử tuân theo một quy tắc so sánh, chẳng hạn tăng dần.

Một `List` có thứ tự nhưng không mặc nhiên được sắp xếp. `List.of(30, 10, 20)` giữ dãy `30, 10, 20`, không tự đổi thành `10, 20, 30`.

Hợp đồng truy cập theo chỉ số cũng không bảo đảm `get(index)` luôn nhanh như nhau. `ArrayList` và `LinkedList` cùng là `List` nhưng có cấu trúc và chi phí thao tác khác nhau.

### Chú ý hai dạng remove của List

Với `List<Integer>`, `remove(1)` chọn phương thức nhận chỉ số `int`, còn `remove(Integer.valueOf(1))` chọn phương thức nhận đối tượng cần xóa. Đây là sự khác nhau về chữ ký phương thức, không phải Java tự đoán mục đích từ dữ liệu.

Không dùng ví dụ này để suy ra mọi `Collection<Integer>` đều có `remove(index)`: phương thức theo chỉ số thuộc `List`, không thuộc hợp đồng chung của `Collection`.

## 6. Set: tính duy nhất, không phải “luôn không có thứ tự”

`Set<E>` bảo đảm không chứa phần tử trùng theo hợp đồng của tập hợp. Ví dụ với một tập hợp giữ thứ tự chèn:

~~~java
// Cần import java.util.LinkedHashSet và java.util.Set.
Set<String> tags = new LinkedHashSet<>();

System.out.println(tags.add("java")); // true
System.out.println(tags.add("java")); // false
System.out.println(tags.size());      // 1
~~~

Lần thêm thứ hai không làm thay đổi tập hợp.

Không nên định nghĩa `Set` là “Collection không có thứ tự”, vì các triển khai có hành vi khác nhau:

| Triển khai | Thứ tự duyệt cần hiểu |
| --- | --- |
| `HashSet` | Không cam kết thứ tự duyệt. Không dựa vào một thứ tự tình cờ quan sát được. |
| `LinkedHashSet` | Thường dùng khi cần giữ thứ tự chèn trong các thao tác thêm thông thường. |
| `TreeSet` | Duyệt theo thứ tự so sánh tự nhiên hoặc `Comparator`. |

`Set` không cung cấp `get(index)` như `List`. Việc một triển khai có thứ tự duyệt không đồng nghĩa nó có truy cập ngẫu nhiên bằng chỉ số.

Với các tập hợp dựa trên băm như `HashSet`, thiết kế `equals()` và `hashCode()` phải nhất quán. Với `TreeSet`, kết quả so sánh bằng `0` quyết định việc xem hai phần tử là cùng vị trí trong tập; thứ tự so sánh nên nhất quán với `equals()` để đáp ứng đầy đủ hợp đồng `Set`. Đây là lý do không nên giải thích tính duy nhất bằng cách chỉ nhìn chuỗi hiển thị của đối tượng.

Không thay đổi tùy tiện những thuộc tính ảnh hưởng đến băm hoặc so sánh khi đối tượng đang nằm trong tập hợp, vì có thể làm các phép tra cứu hoạt động sai với kỳ vọng.

## 7. Queue: lấy phần tử theo quy tắc của hàng đợi

`Queue<E>` mô tả tập hợp phục vụ việc giữ phần tử trước khi xử lý. Một khái niệm quan trọng là **đầu hàng**: phần tử mà thao tác lấy tiếp theo sẽ trả về.

Nhiều hàng đợi hoạt động theo FIFO, tức phần tử vào trước được lấy trước. Nhưng FIFO không phải quy tắc duy nhất của toàn bộ `Queue`.

Ví dụ, `PriorityQueue` xác định đầu hàng theo độ ưu tiên. Với thứ tự tự nhiên của số nguyên, thêm `30, 10, 20` rồi liên tục `poll()` sẽ nhận `10, 20, 30`.

Không suy ra thứ tự `poll()` từ kết quả for-each hay `toString()` của `PriorityQueue`. Iterator của nó không cam kết duyệt theo thứ tự ưu tiên; phải lấy bằng các thao tác hàng đợi nếu mục tiêu là xử lý theo ưu tiên.

### Hai nhóm phương thức

| Mục đích | Dạng báo lỗi bằng ngoại lệ | Dạng trả giá trị đặc biệt |
| --- | --- | --- |
| Thêm phần tử | `add(e)` | `offer(e)` |
| Lấy và bỏ đầu hàng | `remove()` | `poll()` |
| Xem đầu hàng, không bỏ | `element()` | `peek()` |

Khi hàng đợi rỗng, `remove()` và `element()` ném `NoSuchElementException`; `poll()` và `peek()` trả `null`.

Khi không thể thêm do giới hạn sức chứa, `offer(e)` trả `false`, còn `add(e)` có thể ném `IllegalStateException`. “Trả giá trị đặc biệt” không có nghĩa là không bao giờ có ngoại lệ: đầu vào không hợp lệ, chẳng hạn `null` ở một triển khai cấm `null`, vẫn có thể bị từ chối bằng ngoại lệ.

`remove()` không tham số của `Queue` khác với `remove(Object)` kế thừa từ `Collection`. Cái đầu lấy đầu hàng; cái sau tìm và xóa phần tử được chỉ định.

Nên tránh dùng `null` làm dữ liệu hàng đợi vì `null` còn được dùng làm tín hiệu “không có phần tử”. Không phải mọi triển khai đều có cùng chính sách với `null`.

## 8. Deque: cùng một dãy, thao tác được ở hai đầu

`Deque` là viết tắt của double-ended queue: hàng đợi hai đầu.

Ngoài việc là một `Queue`, nó cho phép thao tác rõ ràng ở đầu và cuối:

| Vị trí | Thêm | Lấy và bỏ | Chỉ xem |
| --- | --- | --- | --- |
| Đầu dãy | `offerFirst(e)` | `pollFirst()` | `peekFirst()` |
| Cuối dãy | `offerLast(e)` | `pollLast()` | `peekLast()` |

Ngoài các dạng này còn có các dạng dùng ngoại lệ như `addFirst`, `removeFirst`, `getFirst`, `addLast`, `removeLast` và `getLast`.

### Dùng như hàng đợi FIFO

Thêm ở cuối, lấy ở đầu:

~~~java
// Cần import java.util.ArrayDeque và java.util.Deque.
Deque<String> tasks = new ArrayDeque<>();
tasks.offerLast("A");
tasks.offerLast("B");

System.out.println(tasks.pollFirst()); // A
System.out.println(tasks.pollFirst()); // B
~~~

Khi nhìn `Deque` qua hợp đồng `Queue`, `offer(e)` tương ứng với `offerLast(e)`, `poll()` với `pollFirst()`, và `peek()` với `peekFirst()`.

### Dùng như ngăn xếp LIFO

Thêm và lấy ở cùng đầu:

~~~java
// Đoạn mã trong một phương thức, với các import tương tự ví dụ trên.
Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");

System.out.println(stack.pop()); // B
System.out.println(stack.pop()); // A
~~~

`push(e)` tương ứng với `addFirst(e)`; `pop()` tương ứng với `removeFirst()`. `pop()` trên dãy rỗng ném ngoại lệ, còn `pollFirst()` trả `null`.

`Deque` cung cấp cách dùng ngăn xếp mà không cần dựa vào lớp `Stack` cũ. `ArrayDeque` là một lựa chọn thường gặp cho ngăn xếp hoặc hàng đợi trong mã một luồng; nó không cho phép phần tử `null`.

Có hai đầu không có nghĩa là có `get(index)`. `Deque` không phải một `List`.

## 9. Kiểu khai báo và đối tượng thực tế

Đoạn mã sau không tạo thêm tập hợp khi đổi kiểu tham chiếu:

~~~java
// Đoạn mã trong một phương thức, với import java.util tương ứng.
List<String> list = new ArrayList<>(List.of("A", "B"));
Collection<String> collection = list;
Iterable<String> iterable = collection;

System.out.println(list.get(0));       // A
System.out.println(collection.size()); // 2

// collection.get(0); // Không biên dịch: Collection không khai báo get(index).
// iterable.size();   // Không biên dịch: Iterable không khai báo size().

list.add("C");
System.out.println(collection.size()); // 3
~~~

Cả ba biến cùng trỏ đến đối tượng `ArrayList`. Vì vậy, thay đổi thông qua `list` được nhìn thấy qua `collection`. Tuy nhiên, việc đối tượng thực tế có phương thức `get` không làm trình biên dịch cho phép gọi `get` trên một biến có kiểu `Collection`.

Nên khai báo tham số bằng hợp đồng đáp ứng nhu cầu của phương thức:

- Chỉ duyệt: cân nhắc `Iterable<?>` hoặc `Iterable<? extends T>`.
- Cần thêm `size()` hay `contains(...)`: cân nhắc `Collection<T>`.
- Cần vị trí: dùng `List<T>`.
- Cần biểu đạt điều kiện duy nhất: dùng `Set<T>`.
- Cần thao tác hàng đợi: dùng `Queue<T>`.
- Cần cả hai đầu hoặc ngăn xếp: dùng `Deque<T>`.

Không khai báo kiểu quá chung rồi ép kiểu trở lại chỉ để gọi phương thức mà thiết kế đã cần từ đầu. Ép một `Collection` tùy ý thành `List` có thể gây `ClassCastException` nếu đối tượng thực tế là một `HashSet`.

### Một lớp có thể đáp ứng nhiều hợp đồng

`LinkedList` triển khai cả `List` lẫn `Deque`:

~~~java
// Đoạn mã trong một phương thức; cần import java.util.LinkedList.
LinkedList<String> actual = new LinkedList<>();
List<String> listView = actual;
Deque<String> dequeView = actual;
~~~

Điều này không tạo ra quan hệ `List extends Deque` hay `Deque extends List`. Quan hệ của lớp triển khai không được suy ngược thành quan hệ kế thừa giữa hai interface.

Tương tự, `Collection<Integer>` không phải kiểu con của `Collection<Number>`, dù `Integer` là kiểu con của `Number`. Đây là quy tắc về generic, tách biệt với quan hệ `List<E>` là kiểu con của `Collection<E>`. Khi nhận nhiều kiểu phần tử để chỉ đọc, wildcard có thể biểu đạt ý định phù hợp.

## 10. Chương trình hoàn chỉnh

Lưu mã dưới đây trong tệp **CollectionRelationshipsDemo.java**. Chương trình chỉ dùng API có trong Java 17; phần `Iterable` không cần import vì thuộc `java.lang`.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.Set;
import java.util.StringJoiner;

public class CollectionRelationshipsDemo {
    public static void main(String[] args) {
        List<String> list = new ArrayList<>(List.of("A", "B", "A"));
        Collection<String> collectionView = list;
        Iterable<String> iterableView = collectionView;

        printAll("Iterable view", iterableView);
        System.out.println("Collection size = " + collectionView.size());
        System.out.println("List get(1) = " + list.get(1));

        Set<String> unique = new LinkedHashSet<>(list);
        System.out.println("Set = " + unique);

        Queue<Integer> priority = new PriorityQueue<>(List.of(30, 10, 20));
        List<Integer> removed = new ArrayList<>();
        Integer next;
        while ((next = priority.poll()) != null) {
            removed.add(next);
        }
        System.out.println("Queue poll order = " + removed);

        Deque<String> deque = new ArrayDeque<>();
        deque.offerLast("A");
        deque.offerLast("B");
        System.out.println("Deque after offerLast = " + deque);
        System.out.println("Deque pollFirst = " + deque.pollFirst());

        deque.offerFirst("Z");
        System.out.println("Deque after offerFirst = " + deque);
        System.out.println("Deque pollLast = " + deque.pollLast());

        Queue<String> queueView = deque;
        System.out.println("Queue view peek = " + queueView.peek());

        Iterable<Integer> onlyIterable = () -> List.of(1, 2, 3).iterator();
        printAll("Only Iterable", onlyIterable);
        System.out.println(
                "Only Iterable is Collection = "
                        + (onlyIterable instanceof Collection<?>)
        );
    }

    private static void printAll(String label, Iterable<?> values) {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (Object value : values) {
            result.add(String.valueOf(value));
        }
        System.out.println(label + " = " + result);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 CollectionRelationshipsDemo.java
java CollectionRelationshipsDemo
~~~

Stdout:

~~~text
Iterable view = [A, B, A]
Collection size = 3
List get(1) = B
Set = [A, B]
Queue poll order = [10, 20, 30]
Deque after offerLast = [A, B]
Deque pollFirst = A
Deque after offerFirst = [Z, B]
Deque pollLast = B
Queue view peek = Z
Only Iterable = [1, 2, 3]
Only Iterable is Collection = false
~~~

### Đọc kết quả theo hợp đồng

1. `Iterable view` và `Collection size` quan sát cùng danh sách ban đầu, không tạo bản sao.
2. `List get(1)` dùng khả năng truy cập theo vị trí chỉ có ở hợp đồng phù hợp.
3. `LinkedHashSet` loại phần tử `A` lặp, đồng thời giữ thứ tự chèn trong ví dụ nên kết quả là `[A, B]`.
4. `PriorityQueue` lấy số theo thứ tự ưu tiên; kết quả được thu bằng `poll()`, không phải bằng iterator.
5. `Deque` cho phép thêm/lấy ở cả hai đầu. Khi đổi sang biến `Queue`, thao tác `peek()` nhìn đầu dãy của cùng đối tượng.
6. Đối tượng lambda `onlyIterable` chỉ cung cấp `Iterable`; chính đối tượng đó không phải `Collection`, dù iterator mà nó trả về được lấy từ một danh sách.

Phương thức `printAll` nhận `Iterable<?>` vì nó chỉ cần duyệt. Nó không đòi người gọi phải đưa một `List` hay một tập hợp có thể thay đổi.

## 11. Chọn lớp triển khai sau khi đã chọn hợp đồng

| Nhu cầu của đoạn mã | Kiểu khai báo thường phù hợp | Triển khai minh họa | Điều cần kiểm tra thêm |
| --- | --- | --- | --- |
| Danh sách có vị trí, truy cập theo chỉ số | `List<E>` | `ArrayList<E>` | Chi phí chèn/xóa, kích thước và khả năng thay đổi. |
| Thành viên duy nhất, không cần thứ tự duyệt | `Set<E>` | `HashSet<E>` | Hợp đồng `equals/hashCode`; không dựa vào thứ tự tình cờ. |
| Thành viên duy nhất, cần thứ tự chèn | `Set<E>` | `LinkedHashSet<E>` | Nếu cần API sequenced, xem phiên bản Java và kiểu khai báo cụ thể hơn. |
| Thành viên duy nhất theo thứ tự so sánh | `Set<E>` hoặc interface tập hợp sắp xếp phù hợp | `TreeSet<E>` | Quy tắc so sánh và sự nhất quán với `equals`. |
| Xử lý theo độ ưu tiên | `Queue<E>` | `PriorityQueue<E>` | Cách so sánh phần tử; iterator không phải thứ tự lấy. |
| Hàng đợi FIFO hoặc ngăn xếp LIFO một luồng | `Queue<E>` hoặc `Deque<E>` | `ArrayDeque<E>` | Chọn thao tác đầu/cuối đúng ý định; không cho phép `null`. |

Bảng không khẳng định một triển khai phù hợp cho mọi khối lượng dữ liệu. Khi có nhiều luồng, giới hạn sức chứa, chờ phần tử hoặc yêu cầu truy cập đồng thời, phải xét thêm hợp đồng và triển khai chuyên biệt. Chỉ đổi biến từ `List` sang `Collection` không làm đối tượng trở nên an toàn khi dùng đồng thời.

## 12. Những quan hệ dễ nhầm

### Collection và Collections

`Collection` là interface mô tả tập hợp phần tử. `Collections` là lớp tiện ích có các phương thức tĩnh, chẳng hạn sắp xếp, đảo danh sách hoặc tạo một số góc nhìn bao bọc.

Tên gần nhau không có nghĩa `Collections` là interface cha hoặc lớp triển khai của mọi `Collection`.

### Map không kế thừa Collection

`Map<K, V>` mô tả ánh xạ khóa–giá trị, không kế thừa `Collection` và không mặc nhiên là `Iterable`.

Nó cung cấp các góc nhìn liên quan:

- `keySet()`: một `Set<K>`.
- `values()`: một `Collection<V>`, vì các giá trị có thể trùng nhau.
- `entrySet()`: một `Set<Map.Entry<K, V>>`.

Có thể for-each trên những góc nhìn này. Đây không phải bằng chứng rằng chính `Map` là `Collection`. Một góc nhìn cũng không nhất thiết là bản sao độc lập, và không phải mọi thao tác thay đổi đều được hỗ trợ.

### Stream không phải Iterable hay Collection

`Stream` mô tả một chuỗi xử lý dữ liệu, không phải tập hợp dùng để lưu và truy cập các phần tử như `List`. `Collection.stream()` là cách tạo stream từ tập hợp, không phải quan hệ kế thừa.

Không mặc nhiên dùng lại một stream sau khi đã thực hiện thao tác kết thúc, và không dùng `Stream` thay cho `Iterable` chỉ vì cả hai có thể xử lý từng phần tử.

## 13. Các lỗi thường gặp khi dùng quan hệ interface

| Cách hiểu sai | Cách hiểu cần giữ |
| --- | --- |
| Mọi `Iterable` đều có `size()`. | Chỉ khả năng duyệt không kéo theo hợp đồng về kích thước. |
| Mọi `Collection` đều cho phép thêm/xóa. | Các thao tác thay đổi có thể không được hỗ trợ. |
| `List` là dữ liệu đã sắp xếp. | `List` là dãy có vị trí; sắp xếp là một điều kiện riêng. |
| `Set` luôn không có thứ tự. | `Set` đặt trọng tâm vào tính duy nhất; triển khai quyết định thêm về thứ tự. |
| Mọi `Queue` đều là FIFO. | Phần tử ở đầu có thể được chọn theo độ ưu tiên hoặc quy tắc khác. |
| Có thể xem `PriorityQueue` như một danh sách đã sắp xếp. | Thứ tự lấy bằng `poll` và thứ tự duyệt là hai hợp đồng khác nhau. |
| `Deque` là một `List` vì đều có đầu và cuối. | `Deque` không cung cấp hợp đồng truy cập theo chỉ số. |
| Đổi kiểu biến tạo ra một tập hợp mới. | Phép gán tham chiếu không sao chép đối tượng. |
| Lớp triển khai hai interface nghĩa là hai interface kế thừa nhau. | Đó là quan hệ của lớp với từng interface, không phải của hai interface với nhau. |
| Sơ đồ quan hệ trực tiếp của Java 17 luôn đúng nguyên dạng ở Java 21. | Java 21 thêm tầng `SequencedCollection` cho `List` và thêm nó vào các cha của `Deque`. |

Một điểm thực hành khác là không tùy tiện sửa cấu trúc tập hợp trong for-each. Tùy triển khai, iterator có thể phát hiện thay đổi và ném `ConcurrentModificationException`; cơ chế phát hiện này không phải một giải pháp đồng bộ giữa các luồng. Nếu cần xóa khi duyệt, phải dùng thao tác được hợp đồng và đối tượng cụ thể hỗ trợ, chẳng hạn `Iterator.remove()` hoặc `removeIf(...)` trong bối cảnh phù hợp.

## 14. Tự kiểm tra

1. Một phương thức chỉ in lần lượt phần tử có cần nhận `List` không? Vì sao `Iterable` có thể là hợp đồng phù hợp hơn?
2. Vì sao gọi `add` qua biến `Collection` có thể biên dịch nhưng vẫn thất bại khi chạy?
3. Nếu cần danh sách các tên không trùng và giữ thứ tự nhập, chỉ biết “dùng `Set`” đã đủ để chọn triển khai chưa?
4. Vì sao for-each trên `PriorityQueue` không phải cách lấy các phần tử theo độ ưu tiên?
5. Hãy dùng `ArrayDeque` để xử lý ba tác vụ theo FIFO, rồi đổi cách thao tác để xử lý theo LIFO.
6. Vì sao `LinkedList` có thể gán cho cả `List` và `Deque`, nhưng không thể kết luận `List` kế thừa `Deque`?
7. Khi nâng mô tả kiến trúc từ Java 17 lên Java 21, cần sửa điều gì trong quan hệ trực tiếp của `List` và `Deque`?

Khi tự giải thích được các câu hỏi này, người học có thể đọc một khai báo kiểu và biết đoạn mã được quyền kỳ vọng những gì trước khi xét đến lớp lưu trữ, hiệu năng hoặc tính đồng thời.
