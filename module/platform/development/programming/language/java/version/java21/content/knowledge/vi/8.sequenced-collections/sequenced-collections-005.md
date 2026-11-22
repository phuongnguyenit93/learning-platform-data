# addFirst, addLast, removeFirst và removeLast

Java 21 bổ sung Sequenced Collections để biểu diễn các collection có thứ tự gặp phần tử được xác định rõ ràng. Thay vì phải nhớ cách thêm hoặc xóa ở đầu và cuối của từng kiểu collection, lập trình viên có thể dùng các phương thức thống nhất `addFirst`, `addLast`, `removeFirst` và `removeLast`.

Bốn phương thức này thao tác trực tiếp với hai đầu của collection. Chúng hữu ích khi xây dựng danh sách có thứ tự ưu tiên, hàng đợi hai đầu, lịch sử thao tác hoặc xử lý phần tử theo thứ tự gần nhất/cũ nhất. Hiệu năng cụ thể phụ thuộc vào implementation, vì vậy cần chọn kiểu collection phù hợp với tần suất thao tác ở đầu hay cuối.

## 1. SequencedCollection và thao tác ở hai đầu

`SequencedCollection<E>` là interface trong `java.util`, được bổ sung từ Java 21. Interface này mở rộng `Collection<E>` và quy định thứ tự phần tử có thể được quan sát từ đầu đến cuối.

Các phương thức hai đầu quan trọng:

| Phương thức | Tác dụng | Kết quả |
|---|---|---|
| `addFirst(E element)` | Thêm phần tử vào đầu collection | Không trả về giá trị |
| `addLast(E element)` | Thêm phần tử vào cuối collection | Không trả về giá trị |
| `removeFirst()` | Xóa và lấy phần tử đầu tiên | Trả về phần tử vừa xóa |
| `removeLast()` | Xóa và lấy phần tử cuối cùng | Trả về phần tử vừa xóa |

Để đọc mà không xóa phần tử, interface còn cung cấp `getFirst()` và `getLast()`. Các phương thức này giúp kiểm tra hai đầu trước khi quyết định có xóa hay không.

Ví dụ khai báo:

```java
import java.util.ArrayList;
import java.util.SequencedCollection;

class Main {
    public static void main(String[] args) {
        SequencedCollection<String> tasks = new ArrayList<>();

        tasks.addLast("Review pull request");
        tasks.addLast("Deploy application");
        tasks.addFirst("Fix build");

        System.out.println(tasks);             // [Fix build, Review pull request, Deploy application]
        System.out.println(tasks.getFirst());  // Fix build
        System.out.println(tasks.getLast());   // Deploy application
    }
}
```

Khai báo biến theo interface `SequencedCollection` cho phép chương trình phụ thuộc vào hợp đồng thao tác theo thứ tự, thay vì phụ thuộc trực tiếp vào một implementation cụ thể như `ArrayList` hay `LinkedList`.

## 2. Thêm phần tử bằng addFirst và addLast

### 2.1. addFirst(E element)

`addFirst` chèn phần tử vào vị trí đầu tiên của collection. Các phần tử đang có sẽ nằm sau phần tử mới theo thứ tự của collection.

```java
import java.util.ArrayList;
import java.util.SequencedCollection;

class Main {
    public static void main(String[] args) {
        SequencedCollection<String> names = new ArrayList<>();

        names.addLast("Bình");
        names.addLast("Chi");
        names.addFirst("An");

        System.out.println(names); // [An, Bình, Chi]
    }
}
```

Phương thức phù hợp khi phần tử mới cần được ưu tiên đứng trước các phần tử hiện tại, ví dụ:

- Thêm công việc có mức ưu tiên cao vào đầu danh sách chờ.
- Đưa bản ghi mới nhất lên đầu lịch sử hiển thị.
- Thêm một bước xử lý cần thực hiện trước các bước còn lại.

`addFirst` không có nghĩa là collection luôn hoạt động như stack hoặc queue. Nó chỉ cung cấp thao tác chèn ở đầu; cách sử dụng collection trong thuật toán vẫn do chương trình quyết định.

### 2.2. addLast(E element)

`addLast` chèn phần tử vào cuối collection. Đây là thao tác thường dùng khi muốn duy trì thứ tự thêm vào.

```java
SequencedCollection<String> events = new ArrayList<>();

events.addLast("User signed in");
events.addLast("File uploaded");
events.addLast("Report generated");

System.out.println(events);
// [User signed in, File uploaded, Report generated]
```

Các tình huống thường gặp:

- Thêm công việc mới vào cuối hàng đợi.
- Ghi sự kiện theo thứ tự phát sinh.
- Tạo danh sách kết quả theo thứ tự thu thập.

Với các kiểu collection có thứ tự như List, `addLast` tương ứng với việc thêm vào cuối danh sách. Với `SequencedSet`, tính duy nhất của phần tử vẫn được bảo toàn: nếu phần tử đã tồn tại, thao tác thêm ở đầu hoặc cuối sẽ đưa phần tử đó tới vị trí được yêu cầu thay vì tạo bản sao trùng lặp. Vì vậy, không nên giả định rằng mọi collection đều cho phép chứa phần tử trùng nhau.

### 2.3. Thứ tự sau nhiều lần thêm

Hai phương thức có thể phối hợp để xây dựng collection từ cả hai đầu:

```java
SequencedCollection<Integer> numbers = new ArrayList<>();

numbers.addLast(20);
numbers.addFirst(10);
numbers.addLast(30);
numbers.addFirst(5);

System.out.println(numbers); // [5, 10, 20, 30]
```

Mỗi lần gọi phương thức sẽ làm thay đổi thứ tự quan sát của collection. Các thao tác đọc, duyệt và chuyển đổi sang dạng khác sau đó sẽ nhìn thấy thứ tự mới này.

## 3. Xóa phần tử bằng removeFirst và removeLast

Khác với các phương thức thêm, hai phương thức xóa vừa thay đổi collection vừa trả về phần tử bị xóa. Điều này hữu ích khi cần lấy phần tử ra để xử lý ngay.

### 3.1. removeFirst()

`removeFirst` xóa và trả về phần tử đầu tiên:

```java
SequencedCollection<String> queue = new ArrayList<>();

queue.addLast("Task A");
queue.addLast("Task B");
queue.addLast("Task C");

String nextTask = queue.removeFirst();

System.out.println(nextTask); // Task A
System.out.println(queue);    // [Task B, Task C]
```

Thao tác này phù hợp với cách xử lý FIFO (First In, First Out) khi phần tử được đưa vào cuối và lấy ra ở đầu. FIFO là quy tắc sử dụng do chương trình tạo ra từ hai thao tác; bản thân `SequencedCollection` không áp đặt collection phải là queue.

### 3.2. removeLast()

`removeLast` xóa và trả về phần tử cuối cùng:

```java
SequencedCollection<String> history = new ArrayList<>();

history.addLast("Open document");
history.addLast("Edit document");
history.addLast("Save document");

String latestAction = history.removeLast();

System.out.println(latestAction); // Save document
System.out.println(history);      // [Open document, Edit document]
```

Thao tác này phù hợp khi cần loại bỏ phần tử mới nhất hoặc xử lý theo hướng ngược lại với thứ tự thêm vào.

### 3.3. Kết hợp thêm và xóa ở hai đầu

Khi kết hợp bốn phương thức, một collection có thể hoạt động như hàng đợi hai đầu (deque):

```java
import java.util.ArrayDeque;
import java.util.SequencedCollection;

class Main {
    public static void main(String[] args) {
        SequencedCollection<String> work = new ArrayDeque<>();

        work.addLast("Normal task");
        work.addFirst("Urgent task");
        work.addLast("Background task");

        String current = work.removeFirst();

        System.out.println(current); // Urgent task
        System.out.println(work);    // [Normal task, Background task]

        String deferred = work.removeLast();

        System.out.println(deferred); // Background task
        System.out.println(work);    // [Normal task]
    }
}
```

Trong ví dụ này, công việc khẩn cấp được đưa vào đầu và lấy ra trước; công việc nền được đưa vào cuối và có thể lấy ra từ cuối khi cần.

## 4. Đọc phần tử trước khi xóa

Nếu chỉ muốn quan sát hai đầu, hãy dùng `getFirst` và `getLast`:

```java
SequencedCollection<String> names = new ArrayList<>();
names.addLast("An");
names.addLast("Bình");

String first = names.getFirst();
String last = names.getLast();

System.out.println(first); // An
System.out.println(last);  // Bình
System.out.println(names); // [An, Bình]
```

Hai phương thức này không làm thay đổi collection. Ngược lại, `removeFirst` và `removeLast` xóa phần tử sau khi lấy ra.

| Mục đích | Đầu collection | Cuối collection |
|---|---|---|
| Thêm | `addFirst` | `addLast` |
| Đọc, không xóa | `getFirst` | `getLast` |
| Đọc và xóa | `removeFirst` | `removeLast` |

Sự phân biệt này giúp tránh việc vô tình xóa phần tử khi chỉ cần kiểm tra dữ liệu.

## 5. Xử lý collection rỗng

`getFirst`, `getLast`, `removeFirst` và `removeLast` đều ném `NoSuchElementException` nếu collection rỗng. Vì vậy, nếu collection có thể rỗng, hãy kiểm tra trước bằng `isEmpty()` hoặc xử lý exception phù hợp.

Một số implementation như `ArrayList` và `LinkedList` cho phép chứa `null`. Khi đó, `getFirst()` hoặc `removeFirst()` có thể trả về `null` vì phần tử thực sự ở đầu là null; giá trị trả về null không nhất thiết có nghĩa collection rỗng. Dùng `isEmpty()` để kiểm tra trạng thái rỗng. `ArrayDeque` không cho phép phần tử null.

```java
static void processFirst(SequencedCollection<String> items) {
    if (items.isEmpty()) {
        System.out.println("Không có phần tử để xử lý");
        return;
    }

    String item = items.removeFirst();
    System.out.println("Đã lấy: " + item);
}
```

Không nên gọi trực tiếp `removeFirst` hoặc `getFirst` trên collection mà không biết trạng thái của nó nếu dữ liệu đầu vào có thể rỗng.

Nếu cần thao tác nguyên tử trong môi trường đa luồng, việc kiểm tra `isEmpty()` rồi gọi `removeFirst()` trên một collection không đồng bộ có thể phát sinh race condition: một luồng khác có thể thay đổi collection giữa hai thao tác. Hãy dùng cấu trúc dữ liệu đồng thời phù hợp với yêu cầu hoặc đồng bộ hóa toàn bộ đoạn thao tác. `SequencedCollection` tự nó không đảm bảo thread safety.

## 6. Collection không hỗ trợ sửa đổi

Không phải mọi đối tượng triển khai `SequencedCollection` đều có thể thêm hoặc xóa phần tử. Một collection không sửa đổi được có thể ném `UnsupportedOperationException` khi gọi `addFirst`, `addLast`, `removeFirst` hoặc `removeLast`.

Ví dụ:

```java
import java.util.List;

var fixed = List.of("An", "Bình");

// Ném UnsupportedOperationException vì List.of tạo danh sách không sửa đổi được.
// fixed.addFirst("Chi");
```

Nếu cần thay đổi hai đầu, hãy tạo collection có thể sửa đổi:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.SequencedCollection;

List<String> source = List.of("An", "Bình");
SequencedCollection<String> editable = new ArrayList<>(source);

editable.addFirst("Chi");
editable.removeLast();

System.out.println(editable); // [Chi, An]
```

Khả năng gọi một phương thức trên kiểu interface không đồng nghĩa với việc mọi implementation đều hỗ trợ thao tác đó. Hãy xác định collection có thể sửa đổi hay không từ cách tạo, tài liệu API và hợp đồng của implementation.

## 7. Hiệu năng phụ thuộc implementation

`SequencedCollection` quy định ý nghĩa thao tác ở hai đầu, nhưng không cam kết mọi implementation có cùng độ phức tạp thời gian.

| Implementation | `addFirst` / `removeFirst` | `addLast` / `removeLast` | Ghi chú |
|---|---|---|---|
| `ArrayList` | Thường O(n) do phải dịch chuyển phần tử | Thêm cuối thường O(1) khấu hao; xóa cuối O(1) | Phù hợp khi truy cập theo chỉ số và thao tác cuối danh sách là chủ yếu |
| `LinkedList` | O(1) | O(1) | Có thể thao tác hai đầu hiệu quả, nhưng tốn bộ nhớ cho các node và không truy cập chỉ số nhanh |
| `ArrayDeque` | O(1) khấu hao | O(1) khấu hao | Thích hợp cho hàng đợi hai đầu; không cho phép phần tử null |

Đây là đặc điểm của các implementation phổ biến, không phải bảo đảm độ phức tạp chung của interface. Khi lựa chọn:

- Dùng `ArrayList` nếu cần truy cập theo chỉ số thường xuyên và chủ yếu thêm ở cuối.
- Dùng `ArrayDeque` nếu cần thêm/xóa liên tục ở cả hai đầu và không cần truy cập theo chỉ số.
- Dùng `LinkedList` khi cần các đặc điểm của linked list và thao tác đầu/cuối; cân nhắc chi phí bộ nhớ và hiệu năng duyệt.

Không nên chọn implementation chỉ dựa trên tên phương thức. Hãy xem xét kiểu truy cập, số lượng phần tử, tần suất thêm/xóa và giới hạn dữ liệu thực tế.

## 8. Quan hệ với Deque và List

`SequencedCollection` cung cấp một hợp đồng chung cho collection có thứ tự. Hai interface quen thuộc là `List` và `Deque` đều thuộc hệ phân cấp này trong Java 21.

- Với `List`, các thao tác hai đầu giúp làm việc theo thứ tự mà không cần dùng chỉ số `0` hoặc `size() - 1`.
- Với `Deque`, các thao tác hai đầu phù hợp trực tiếp với mô hình hàng đợi hai đầu.
- Với `SequencedCollection`, mã nguồn có thể dùng chung các thao tác hai đầu mà không cần phụ thuộc vào toàn bộ API riêng của List hoặc Deque.

Ví dụ viết hàm nhận mọi SequencedCollection:

```java
static <E> E takeNewest(SequencedCollection<E> items) {
    return items.removeLast();
}
```

Hàm này có thể làm việc với nhiều implementation có thứ tự, miễn là collection có thể sửa đổi và không rỗng tại thời điểm gọi. Nếu điều kiện đó không được bảo đảm, hàm cần kiểm tra hoặc quy định rõ hợp đồng đầu vào.

## 9. Kết hợp với reversed()

`SequencedCollection` còn cung cấp `reversed()` để tạo view có thứ tự ngược với collection ban đầu. View này được liên kết với collection gốc; các thay đổi thông qua view sẽ phản ánh vào collection gốc và ngược lại.

Điều này có ý nghĩa khi gọi các thao tác hai đầu trên view đảo ngược:

```java
import java.util.ArrayList;
import java.util.SequencedCollection;

class Main {
    public static void main(String[] args) {
        SequencedCollection<String> original = new ArrayList<>();
        original.addLast("A");
        original.addLast("B");
        original.addLast("C");

        SequencedCollection<String> reversed = original.reversed();

        System.out.println(reversed); // [C, B, A]

        reversed.addFirst("D");

        System.out.println(reversed); // [D, C, B, A]
        System.out.println(original); // [A, B, C, D]
    }
}
```

Trong view đảo ngược, đầu và cuối được nhìn theo hướng ngược lại với collection gốc. Vì vậy, `reversed.addFirst(x)` tương ứng với việc thêm `x` vào cuối collection gốc. Đây là view, không phải bản sao độc lập; nếu cần một collection riêng, hãy tạo bản sao tường minh bằng constructor phù hợp.

## 10. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi `removeFirst` trên collection rỗng | Không có phần tử để lấy và xóa | Kiểm tra `isEmpty()` hoặc xử lý `NoSuchElementException` |
| Dùng `getFirst` khi mục tiêu là xóa phần tử | Nhầm phương thức đọc với phương thức đọc và xóa | Dùng `removeFirst` khi muốn lấy ra khỏi collection |
| Gọi `addFirst` trên `List.of(...)` | Collection không sửa đổi được | Tạo bản có thể sửa đổi như `new ArrayList<>(source)` |
| Dùng `ArrayList` cho thao tác đầu/cuối với tần suất rất cao | Thao tác ở đầu cần dịch chuyển phần tử | Cân nhắc `ArrayDeque` hoặc `LinkedList` theo nhu cầu |
| Giả định mọi SequencedCollection đều cho phép phần tử null | Quy tắc null phụ thuộc implementation | Kiểm tra hợp đồng của collection cụ thể |
| Cho rằng interface đảm bảo thread safety | SequencedCollection không quy định đồng bộ hóa | Dùng cấu trúc đồng thời hoặc cơ chế đồng bộ phù hợp |
| Coi `reversed()` là bản sao | Đây là view có liên kết với collection gốc | Tạo bản sao riêng nếu cần dữ liệu độc lập |

## 11. Hướng dẫn sử dụng trong Java 21

Khi thao tác với hai đầu của một collection, hãy chọn phương thức theo mục đích:

1. Dùng `addFirst` khi phần tử mới cần đứng ở đầu.
2. Dùng `addLast` khi phần tử mới cần đứng ở cuối.
3. Dùng `getFirst` hoặc `getLast` khi chỉ cần quan sát.
4. Dùng `removeFirst` hoặc `removeLast` khi cần lấy và loại bỏ phần tử.
5. Kiểm tra collection rỗng trước khi đọc hoặc xóa nếu trạng thái rỗng có thể xảy ra.
6. Xác nhận collection hỗ trợ sửa đổi và quy tắc null của implementation.
7. Chọn implementation dựa trên tần suất thao tác hai đầu và yêu cầu truy cập dữ liệu.

Các phương thức `addFirst`, `addLast`, `removeFirst` và `removeLast` giúp mã Java 21 diễn đạt trực tiếp ý định thao tác theo thứ tự. Khi kết hợp với `SequencedCollection`, chương trình có thể làm việc nhất quán với hai đầu của nhiều loại collection, đồng thời vẫn lựa chọn implementation phù hợp với hiệu năng và hợp đồng dữ liệu.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
