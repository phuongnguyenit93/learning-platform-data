# Đánh giá thread safety và concurrent modification theo implementation

`reversed()` chỉ thay đổi hướng quan sát một collection; nó không tự bổ sung khóa, cơ chế đồng bộ hay bảo đảm an toàn luồng. Khi nhiều luồng cùng truy cập reverse view và collection gốc, cách hoạt động phụ thuộc implementation đứng phía sau: có implementation dùng iterator fail-fast, có implementation cho phép duyệt đồng thời với iterator weakly consistent, và có implementation tạo iterator snapshot.

Vì vậy, không thể kết luận một reverse view an toàn hay không an toàn chỉ từ kiểu `List` hoặc `SequencedCollection`. Cần xác định implementation cụ thể, hợp đồng iterator/spliterator của nó và cách chương trình đồng bộ các thao tác đọc/ghi. Các API Sequenced Collections được chuẩn hóa trong Java 21 qua [JEP 431](https://openjdk.org/jeps/431).

## 1. Reverse view không tạo ra thread safety

`SequencedCollection.reversed()` trả về view có encounter order đảo ngược. Nếu implementation cho phép sửa đổi view, thay đổi qua view được ghi vào collection gốc. Tuy nhiên, hợp đồng API cũng nêu rằng thay đổi trên collection nền có thể hoặc không được nhìn thấy qua reverse view, tùy implementation.

```java
List<String> tasks = new ArrayList<>(List.of("compile", "test", "package"));
List<String> reverseView = tasks.reversed();

reverseView.addFirst("deploy"); // Ghi vào collection gốc nếu thao tác được hỗ trợ.
```

`reversedView` và `tasks` là hai đường truy cập liên quan đến cùng dữ liệu. Nếu một luồng thêm phần tử vào `tasks` trong khi luồng khác duyệt `reverseView`, chương trình vẫn phải tuân theo quy tắc đồng bộ của implementation. Đổi hướng duyệt không biến `ArrayList` thành collection concurrent.

Một view cũng không phải lúc nào cũng là snapshot. View có thể phản ánh thay đổi qua các thao tác được backing, nhưng iterator hoặc spliterator lấy từ view lại có thể có chính sách riêng. Ví dụ `CopyOnWriteArrayList` có reverse view nhìn thấy thay đổi của list, trong khi iterator được tạo từ view giữ snapshot tại thời điểm iterator được tạo.

## 2. Phân biệt thread safety, fail-fast và concurrent modification

Ba khái niệm này giải quyết các vấn đề khác nhau:

- **Thread safety**: implementation quy định cách nhiều luồng có thể đọc/ghi dữ liệu mà không phá vỡ các bất biến của collection và bảo đảm những hiệu ứng bộ nhớ cần thiết.
- **Fail-fast**: iterator hoặc spliterator cố phát hiện một số thay đổi không được phép trong lúc duyệt và có thể ném `ConcurrentModificationException` (CME). Đây chủ yếu là cơ chế phát hiện lỗi.
- **Concurrent modification policy**: hợp đồng quy định iterator phản ứng ra sao khi collection thay đổi trong lúc duyệt. Ngoài fail-fast còn có weakly consistent và snapshot iterator.

Một iterator fail-fast không làm collection trở nên thread-safe. Ngược lại, iterator không ném CME cũng không tự chứng minh mọi thao tác trên collection đều an toàn hoặc nguyên tử.

`ConcurrentModificationException` cũng không có nghĩa chắc chắn có hai luồng. Một luồng có thể tự gây ra lỗi nếu sửa cấu trúc collection trực tiếp trong lúc iterator fail-fast đang hoạt động. Ví dụ:

```java
List<String> tasks = new ArrayList<>(List.of("compile", "test", "package", "deploy"));

for (String task : tasks) {
    if (task.equals("test")) {
        tasks.remove(task); // Có thể làm iterator fail-fast ném CME.
    }
}
```

Nếu cần xóa theo điều kiện trong một luồng, dùng API được thiết kế cho thao tác đó:

```java
tasks.removeIf("test"::equals);
```

Hoặc dùng `Iterator.remove()` sau khi gọi `next()` nếu cần điều khiển từng bước. Không dùng `try/catch (ConcurrentModificationException)` để lặp lại hoặc bỏ qua lỗi như một cơ chế đồng bộ.

## 3. Fail-fast iterator: phát hiện thay đổi cấu trúc theo best-effort

Các collection thông dụng như `ArrayList`, `HashMap` và các view của chúng thường cung cấp iterator fail-fast. Với `ArrayList`, thay đổi cấu trúc gồm thêm hoặc xóa phần tử hay thay đổi kích thước mảng nền; chỉ thay giá trị tại một vị trí bằng `set()` không được xem là structural modification theo hợp đồng của lớp.

```java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
List<String> reverseView = values.reversed();

var iterator = reverseView.iterator();
System.out.println(iterator.next()); // C

values.add("D"); // Thay đổi cấu trúc qua collection gốc.

// Lần duyệt tiếp theo có thể ném ConcurrentModificationException.
while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
```

Iterator của reverse view dựa trên implementation của list. Nếu implementation dùng fail-fast iterator, thay đổi cấu trúc thông qua đường truy cập khác có thể bị phát hiện. Không dựa vào việc CME luôn xuất hiện: Java chỉ bảo đảm fail-fast ở mức best-effort vì không thể đưa ra bảo đảm cứng khi có thay đổi đồng thời không được đồng bộ.

`HashMap` cũng định nghĩa structural modification là thêm hoặc xóa mapping; cập nhật giá trị của khóa đã có không được xem là structural modification. Iterator của các collection view như `keySet()`, `values()` và `entrySet()` là fail-fast theo hợp đồng của `HashMap`.

Khi gặp CME, hãy xem đó là dấu hiệu có lỗi trong cách phối hợp truy cập hoặc trong luồng điều khiển duyệt collection. Nếu nhiều luồng cùng dùng collection thường, bảo vệ toàn bộ vùng đọc/ghi liên quan bằng cùng một khóa hoặc chuyển sang collection concurrent phù hợp.

## 4. Synchronized wrappers: đồng bộ thao tác và khóa khi duyệt

`Collections.synchronizedList()` và `Collections.synchronizedMap()` tạo wrapper đồng bộ dựa trên collection/map được truyền vào. Các lời gọi phương thức qua wrapper được đồng bộ trên monitor của wrapper. Để bảo đảm serial access, mọi truy cập đến backing collection phải đi qua wrapper đó.

Iterator, spliterator và stream vẫn cần khóa ngoài. Tài liệu Java 21 yêu cầu đồng bộ trên chính wrapper khi duyệt, bởi vì một lượt duyệt gồm nhiều lời gọi liên tiếp và cần được bảo vệ như một vùng thao tác thống nhất.

Ví dụ với reverse view của một synchronized list:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> synchronizedTasks =
        Collections.synchronizedList(new ArrayList<>(List.of("compile", "test", "package")));

synchronized (synchronizedTasks) {
    for (String task : synchronizedTasks.reversed()) {
        System.out.println(task);
    }
}
```

Khóa trên `synchronizedTasks`, tức wrapper được tạo bởi `Collections.synchronizedList()`. Không khóa trên object reverse view. Các luồng ghi dữ liệu cũng phải dùng cùng wrapper/monitor này; giữ lại và sửa trực tiếp list nền bên ngoài wrapper sẽ phá vỡ bảo đảm đồng bộ.

### Khóa cả thao tác tổng hợp

Đồng bộ từng lời gọi riêng lẻ không tự làm một chuỗi nhiều lời gọi trở thành nguyên tử. Ví dụ, kiểm tra rỗng rồi xóa phần tử phải nằm trong cùng vùng khóa:

```java
static void removeLastIfPresent(List<String> synchronizedTasks) {
    synchronized (synchronizedTasks) {
        if (!synchronizedTasks.isEmpty()) {
            synchronizedTasks.reversed().removeFirst();
        }
    }
}
```

Nếu bỏ `synchronized` bên ngoài, một luồng khác có thể thay đổi list giữa bước `isEmpty()` và bước xóa. Khóa ngoài giữ hai bước trong cùng một vùng loại trừ tương hỗ.

Với synchronized map, khi duyệt `keySet()`, `values()` hoặc `entrySet()`, khóa trên map wrapper, không khóa trên collection view:

```java
Map<String, Integer> synchronizedScores =
        Collections.synchronizedMap(new HashMap<>());

var keys = synchronizedScores.keySet();
synchronized (synchronizedScores) {
    for (String key : keys) {
        System.out.println(key);
    }
}
```

Quy tắc tương tự áp dụng cho các view con của synchronized sorted/navigable collections: khóa trên wrapper gốc theo tài liệu API, không khóa riêng trên subview.

## 5. Weakly consistent iterator: cho phép duyệt cùng lúc cập nhật

Các collection concurrent như `ConcurrentLinkedDeque` và `ConcurrentHashMap` dùng iterator/spliterator weakly consistent cho những API được tài liệu công bố. Các iterator này có thể hoạt động trong khi luồng khác thêm hoặc xóa phần tử và không ném `ConcurrentModificationException` vì những thay đổi đó. `ConcurrentHashMap` không triển khai `SequencedMap`; nó được nêu ở đây để so sánh chính sách duyệt của các map view concurrent.

Weakly consistent không có nghĩa là snapshot chính xác tại một thời điểm duy nhất. Iterator sẽ duyệt các phần tử tồn tại lúc được tạo theo hợp đồng của implementation và có thể phản ánh một số thay đổi xảy ra sau đó; mức độ nhìn thấy thay đổi phụ thuộc implementation. Các thao tác tổng hợp như `size()`, `forEach()` hoặc `removeIf()` cũng không mặc nhiên là một giao dịch nguyên tử.

`ConcurrentLinkedDeque` có `descendingIterator()` để duyệt từ cuối deque về đầu. Iterator này được tài liệu xác định là weakly consistent:

```java
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedDeque;

ConcurrentLinkedDeque<String> deque =
        new ConcurrentLinkedDeque<>(List.of("A", "B", "C"));

Iterator<String> descending = deque.descendingIterator();
deque.addFirst("D"); // Thay đổi sau khi tạo iterator.

while (descending.hasNext()) {
    System.out.println(descending.next());
}
```

Không dựa vào ví dụ trên để khẳng định `D` chắc chắn xuất hiện hoặc chắc chắn không xuất hiện. Iterator weakly consistent cho phép duyệt đồng thời và không ném CME, nhưng không hứa hẹn một snapshot cố định chứa mọi thay đổi sau lúc tạo iterator.

Với thao tác lấy/xóa một phần tử ở đầu deque, dùng phương thức nguyên tử như `pollFirst()` hoặc `pollLast()` thay vì ghép `isEmpty()` với `removeFirst()` qua hai bước độc lập. `ConcurrentLinkedDeque` không cho phép phần tử `null`, vì vậy `pollFirst()` trả về `null` khi deque rỗng.

## 6. Snapshot iterator: `CopyOnWriteArrayList`

`CopyOnWriteArrayList` phù hợp khi số lượt đọc/duyệt lớn hơn nhiều so với số lần cập nhật. Mỗi thao tác thay đổi tạo một bản sao mảng nền mới. Iterator và spliterator giữ trạng thái mảng tại thời điểm được tạo, nên không bị ảnh hưởng bởi thay đổi về sau và không ném CME.

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

CopyOnWriteArrayList<String> names =
        new CopyOnWriteArrayList<>(List.of("An", "Binh"));
List<String> reversed = names.reversed();

var iterator = reversed.iterator();
names.add("Chi");

while (iterator.hasNext()) {
    System.out.println(iterator.next());
}

System.out.println(reversed); // [Chi, Binh, An]
```

Iterator được tạo trước khi thêm `Chi`, nên nó duyệt snapshot cũ theo thứ tự ngược: `Binh`, `An`. Khi đọc view sau cập nhật, `reversed` phản ánh list hiện tại theo thứ tự `[Chi, Binh, An]` theo hợp đồng của `CopyOnWriteArrayList`.

Iterator của `CopyOnWriteArrayList` không hỗ trợ `remove()`, `set()` hoặc `add()`; các thao tác này ném `UnsupportedOperationException`. Muốn cập nhật, gọi phương thức trên list hoặc reverse view. Đổi lại, mỗi lần sửa đổi có chi phí tạo mảng mới và sao chép phần tử, nên không phù hợp với workload ghi liên tục hoặc collection lớn có nhiều cập nhật.

## 7. So sánh chính sách duyệt theo implementation

| Implementation | Chính sách iterator thường gặp | Khi collection thay đổi trong lúc duyệt | Phù hợp khi |
| --- | --- | --- | --- |
| `ArrayList` / `LinkedList` | Fail-fast | Thay đổi cấu trúc ngoài iterator có thể làm ném CME; không có bảo đảm thread safety. | Dữ liệu không chia sẻ giữa nhiều luồng hoặc được bảo vệ bằng khóa ngoài. |
| `HashMap` và các collection view của nó | Fail-fast | Thêm/xóa mapping ngoài iterator có thể làm ném CME; CME chỉ best-effort. | Map thông thường với quyền truy cập được kiểm soát. |
| `Collections.synchronizedList()` / `synchronizedMap()` | Iterator không tự khóa toàn bộ lượt duyệt | Phải khóa wrapper gốc khi duyệt; mọi truy cập phải đi qua wrapper. | Cần serial access bằng một monitor chung. |
| `ConcurrentLinkedDeque` | Weakly consistent | Có thể duyệt cùng lúc cập nhật; không ném CME vì concurrent update. | Nhiều luồng cần thao tác deque ở hai đầu. |
| `ConcurrentHashMap` | Weakly consistent ở iterator và các view | Iterator có thể phản ánh trạng thái từ lúc tạo trở đi; không ném CME. | Nhiều luồng đọc/ghi map mà không cần một khóa loại trừ toàn map. |
| `CopyOnWriteArrayList` | Snapshot | Iterator không thấy cập nhật sau lúc tạo và không ném CME. | Đọc/duyệt rất nhiều, cập nhật ít. |

Không suy rộng chính sách iterator của một implementation sang mọi collection có cùng interface. Ví dụ, hai đối tượng cùng khai báo kiểu `List` có thể có chính sách duyệt hoàn toàn khác nhau nếu một đối tượng là `ArrayList`, đối tượng còn lại là `CopyOnWriteArrayList` hoặc synchronized wrapper.

## 8. Snapshot dữ liệu và giới hạn của việc sao chép

Nếu cần duyệt một danh sách ổn định mà không giữ khóa trong suốt lượt duyệt, có thể tạo snapshot trước:

```java
List<String> snapshot;
synchronized (synchronizedTasks) {
    snapshot = List.copyOf(synchronizedTasks.reversed());
}

for (String task : snapshot) {
    System.out.println(task);
}
```

Khóa bảo vệ thao tác sao chép để không có luồng khác sửa collection trong lúc tạo snapshot. Sau khi sao chép xong, có thể duyệt snapshot bên ngoài khóa. `List.copyOf()` tạo danh sách không sửa đổi và không nhận phần tử `null`; nếu dữ liệu có thể chứa `null`, dùng `new ArrayList<>(...)` trong cùng vùng khóa.

Chỉ gọi `new ArrayList<>(reverseView)` hoặc `List.copyOf(reverseView)` mà không đồng bộ không đảm bảo tạo được snapshot nhất quán khi collection gốc đang bị sửa đồng thời. Bản sao độc lập sau khi tạo không đồng nghĩa quá trình tạo bản sao là nguyên tử.

Snapshot cũng chỉ sao chép tham chiếu phần tử, không sao chép sâu object. Nếu các phần tử là object mutable và nhiều luồng cùng sửa nội dung của chúng, cần đồng bộ riêng cho object đó hoặc thiết kế object bất biến.

## 9. Quy tắc lựa chọn và xử lý concurrent modification

1. Xác định implementation thực tế của collection đứng sau reverse view.
2. Đọc tài liệu của iterator, spliterator và stream: fail-fast, weakly consistent hay snapshot.
3. Nếu dùng collection thường giữa nhiều luồng, bảo vệ mọi thao tác liên quan bằng cùng một khóa; không chỉ khóa đoạn lặp.
4. Nếu dùng synchronized wrapper, chỉ truy cập backing data qua wrapper và khóa wrapper gốc khi duyệt view hoặc thực hiện nhiều bước cần nguyên tử.
5. Nếu workload cần cập nhật đồng thời, chọn concurrent collection có semantics phù hợp; đừng chỉ bọc collection thường rồi mong có iterator weakly consistent.
6. Nếu cần dữ liệu cố định để xử lý lâu dài, tạo snapshot trong vùng đồng bộ hoặc dùng implementation có snapshot iterator.
7. Không dùng CME làm tín hiệu đồng bộ, không giả định không có CME nghĩa là không có race condition.

Thread-safe collection cũng không làm object chứa bên trong tự động thread-safe. Bảo đảm bộ nhớ của collection chủ yếu quy định quan hệ giữa thao tác đưa tham chiếu vào collection và thao tác đọc/lấy tham chiếu đó; trạng thái mutable của object vẫn cần chính sách đồng bộ riêng.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cho rằng `reversed()` tự làm collection thread-safe | Reverse view chỉ thay đổi encounter order. | Chọn implementation và cơ chế đồng bộ phù hợp. |
| Dùng CME để phát hiện mọi lần ghi đồng thời | Fail-fast chỉ best-effort. | Đồng bộ đúng; xem CME là tín hiệu phát hiện lỗi. |
| Nghĩ CME luôn do một luồng khác | Một luồng cũng có thể sửa collection trực tiếp khi iterator đang chạy. | Sửa qua iterator hoặc dùng `removeIf()` phù hợp. |
| Duyệt synchronized list mà không khóa | Iterator/spliterator/stream không tự giữ khóa trong suốt lượt duyệt. | Khóa trên synchronized wrapper gốc. |
| Khóa reverse view thay vì wrapper gốc | Các luồng khác đồng bộ trên monitor của wrapper, không phải monitor của view. | Dùng cùng monitor của wrapper được trả về bởi `Collections.synchronizedList()`. |
| Coi weakly consistent iterator là snapshot | Iterator có thể phản ánh một số cập nhật sau lúc tạo. | Dùng snapshot iterator hoặc sao chép trong vùng đồng bộ nếu cần ảnh chụp cố định. |
| Coi `CopyOnWriteArrayList` phù hợp với ghi liên tục | Mỗi thay đổi sao chép mảng nền. | Dùng khi đọc nhiều, ghi ít; cân nhắc concurrent deque/map cho workload khác. |
| Sao chép collection trong lúc nguồn bị sửa đồng thời | Quá trình sao chép có thể không tạo trạng thái nhất quán. | Đồng bộ trong lúc tạo snapshot hoặc dùng API snapshot của implementation. |

## 11. Tài liệu tham khảo chính thức

- [Java SE 21 API — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): hợp đồng reverse view, write-through và khả năng quan sát thay đổi từ collection nền.
- [Java SE 21 API — `List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): hành vi và giới hạn của `List.reversed()`.
- [Java SE 21 API — `ConcurrentModificationException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ConcurrentModificationException.html): fail-fast, best-effort và mục đích phát hiện lỗi.
- [Java SE 21 API — `ArrayList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html): structural modification và fail-fast iterator.
- [Java SE 21 API — `Collections`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): synchronized wrappers và yêu cầu khóa khi duyệt iterator, spliterator hoặc stream.
- [Java SE 21 API — `CopyOnWriteArrayList`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterator, chi phí copy-on-write và memory consistency.
- [Java SE 21 API — `ConcurrentLinkedDeque`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): weakly consistent iterator, spliterator và descending iterator.
- [Java SE 21 API — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): truy cập đồng thời và weakly consistent collection views.
- [Java SE 21 — `java.util.concurrent` package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html): khác biệt giữa synchronized và concurrent collections, weak consistency và memory consistency properties.
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431): API sequenced collections được đưa vào Java 21.
