# Iterator, Spliterator và sửa đổi collection khi duyệt trong Java 27

Trong Java 27, Java Collections Framework cung cấp nhiều cách truy cập phần tử của một collection. `Iterator<E>` giúp duyệt tuần tự và, nếu được hỗ trợ, xóa phần tử hiện tại một cách hợp lệ. `ListIterator<E>` mở rộng khả năng duyệt và chỉnh sửa danh sách. `Spliterator<T>` hỗ trợ duyệt và **chia** nguồn dữ liệu, là một cơ chế nền tảng cho Stream API.

Điểm quan trọng không chỉ là cú pháp: **được phép thay đổi collection vào thời điểm nào, bằng phương thức nào, và thay đổi có được phản ánh trong quá trình duyệt hay không**. Một số iterator phát hiện thay đổi cấu trúc theo kiểu *fail-fast*, một số duyệt ảnh chụp (*snapshot*), còn một số được thiết kế để chịu thay đổi đồng thời (*weakly consistent*). Hiểu sự khác biệt này giúp tránh lỗi `ConcurrentModificationException` và các lỗi logic khó tái hiện.

Bài viết tập trung vào các cơ chế hiện hành của **Java SE 27** và cách lựa chọn phù hợp khi viết mã mới.

## 1. Phân biệt Iterable, Iterator, Spliterator và Stream

Các giao diện này có vai trò liên quan nhưng không giống nhau.

| API | Mục đích chính | Thao tác tiêu biểu |
|---|---|---|
| `Iterable<T>` | Cung cấp cách lấy iterator để duyệt phần tử | `iterator()`, `forEach(...)`, `spliterator()` |
| `Iterator<E>` | Duyệt từng phần tử theo một chiều; có thể hỗ trợ xóa phần tử vừa lấy | `hasNext()`, `next()`, `remove()` |
| `ListIterator<E>` | Duyệt danh sách theo hai chiều; có thể hỗ trợ thêm, sửa, xóa tại vị trí iterator | `previous()`, `add(...)`, `set(...)` |
| `Spliterator<T>` | Duyệt từng phần tử hoặc chia phần nguồn để xử lý | `tryAdvance(...)`, `trySplit()` |
| `Stream<T>` | Khai báo chuỗi phép xử lý dữ liệu và thực thi ở terminal operation | `filter(...)`, `map(...)`, `collect(...)`, `toList()` |

Ví dụ với một `ArrayList`:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;

public class TraversalWays {
    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("An", "Bình", "Chi"));

        // 1. Enhanced for: đọc tuần tự.
        for (String name : names) {
            System.out.println(name);
        }

        // 2. Iterator: điều khiển từng bước.
        Iterator<String> iterator = names.iterator();
        while (iterator.hasNext()) {
            System.out.println(iterator.next());
        }

        // 3. Spliterator: duyệt qua Consumer.
        Spliterator<String> spliterator = names.spliterator();
        spliterator.forEachRemaining(System.out::println);

        // 4. Stream: biến đổi và thu thập dữ liệu.
        List<String> upperNames = names.stream()
                .map(String::toUpperCase)
                .toList();

        System.out.println(upperNames);
    }
}
~~~

Với `Iterable`, vòng lặp enhanced `for` sử dụng cơ chế iterator để duyệt, nhưng nó **không cho bạn giữ tham chiếu đến iterator** để gọi `remove()`. Đối với mảng, enhanced `for` sử dụng cơ chế duyệt mảng, không cần tạo `Iterator`.

`Iterator` và `Spliterator` có trạng thái tiến trình duyệt. Sau khi đã duyệt hết, không thể giả định chúng tự trở lại đầu. Nếu cần lượt duyệt mới, hãy lấy đối tượng iterator/spliterator mới từ nguồn.

## 2. Iterator: mô hình duyệt từng phần tử

`Iterator<E>` có các phương thức cơ bản:

- `hasNext()`: trả về `true` khi còn phần tử tiếp theo.
- `next()`: trả về phần tử tiếp theo và đưa iterator tiến lên.
- `remove()`: xóa phần tử cuối cùng được trả về từ `next()`, **nếu iterator hỗ trợ**.
- `forEachRemaining(action)`: đưa lần lượt các phần tử còn lại vào một `Consumer`.

Ví dụ:

~~~java
import java.util.Iterator;
import java.util.List;

List<String> languages = List.of("Java", "Kotlin", "Scala");

Iterator<String> iterator = languages.iterator();

while (iterator.hasNext()) {
    String language = iterator.next();
    System.out.println(language);
}
~~~

Nếu gọi `next()` khi không còn phần tử, iterator ném `NoSuchElementException`:

~~~java
Iterator<Integer> iterator = List.of(10).iterator();

System.out.println(iterator.next()); // 10
System.out.println(iterator.hasNext()); // false

// iterator.next(); // NoSuchElementException
~~~

Không nên gọi `next()` hai lần trong một lượt xử lý chỉ để vừa kiểm tra vừa lấy phần tử, vì mỗi lần gọi sẽ làm iterator tiến đến phần tử tiếp theo.

### 2.1. Thứ tự duyệt tùy collection

`Iterator` không tự quy định mọi collection phải có một thứ tự chung.

- `ArrayList` duyệt theo thứ tự chỉ số của danh sách.
- `LinkedHashSet` duyệt theo thứ tự chèn phần tử, theo hợp đồng của kiểu đó.
- `TreeSet` duyệt theo thứ tự sắp xếp của tập hợp.
- `HashSet` không cam kết thứ tự duyệt ổn định.

Nếu kết quả cần thứ tự xác định, hãy sử dụng collection có hợp đồng thứ tự phù hợp hoặc sắp xếp dữ liệu có chủ đích. Đừng dựa vào thứ tự tình cờ quan sát được khi in một `HashSet`.

### 2.2. forEachRemaining không phải cơ chế xóa phần tử

~~~java
Iterator<String> iterator =
        List.of("An", "Bình", "Chi").iterator();

iterator.next(); // Đã tiêu thụ "An"

iterator.forEachRemaining(System.out::println);
// Bình
// Chi
~~~

`forEachRemaining` xử lý các phần tử **còn lại**, không bắt đầu lại từ đầu. Theo hợp đồng của `Iterator`, nếu callback tự thay đổi nguồn đang được duyệt, hành vi không được bảo đảm, trừ khi implementation công bố chính sách sửa đổi đồng thời riêng.

Vì thế, không viết:

~~~java
// Không an toàn với ArrayList thông thường.
List<String> names = new ArrayList<>(List.of("An", "Bình"));

names.iterator().forEachRemaining(name -> {
    if (name.equals("An")) {
        names.remove(name);
    }
});
~~~

Muốn lọc/xóa, hãy dùng `removeIf` hoặc vòng `while` với `Iterator.remove`.

## 3. Sửa collection khi duyệt: thế nào là thay đổi cấu trúc?

**Thay đổi cấu trúc (structural modification)** là thay đổi cấu trúc phần tử của collection, thường như thêm hoặc xóa phần tử.

Ví dụ với `ArrayList`:

~~~java
List<String> names =
        new ArrayList<>(List.of("An", "Bình", "Chi"));

names.add("Dung");      // Thêm phần tử: thay đổi cấu trúc.
names.remove("Bình");   // Xóa phần tử: thay đổi cấu trúc.
names.set(0, "Anh");    // Thay phần tử ở một vị trí hiện có.
~~~

Với `ArrayList`, thay giá trị tại chỉ số có sẵn bằng `set(index, value)` không phải thay đổi cấu trúc theo nghĩa thêm/xóa phần tử. Tuy nhiên, điều đó **không có nghĩa** có thể tùy ý sửa mọi collection đang được duyệt. Hãy đọc hợp đồng của từng implementation.

Với `HashMap`, chèn một khóa mới hoặc xóa mapping là thay đổi cấu trúc. Thay giá trị của khóa đã có không có cùng tính chất cấu trúc như thêm khóa mới, nhưng vẫn phải cân nhắc đồng bộ hóa nếu nhiều luồng truy cập.

### 3.1. Trường hợp thường gây ConcurrentModificationException

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers =
        new ArrayList<>(List.of(10, 20, 30, 40));

for (Integer number : numbers) {
    if (number == 20) {
        numbers.remove(Integer.valueOf(20)); // Sai cách khi đang duyệt.
    }
}
~~~

Đối với `ArrayList`, đoạn mã này có thể ném `ConcurrentModificationException` vì collection bị thay đổi cấu trúc trực tiếp trong khi iterator do enhanced `for` sử dụng vẫn đang hoạt động.

Điểm cần nhớ: **tên ngoại lệ có chữ "Concurrent" không có nghĩa phải tồn tại nhiều thread**. Một thread duy nhất cũng có thể làm phát sinh lỗi này khi tự sửa collection trong lúc duyệt.

### 3.2. Fail-fast là cơ chế phát hiện lỗi theo best effort

Iterator của một số collection không hỗ trợ sửa đổi đồng thời trực tiếp, trong đó có `ArrayList` và `HashMap`, thường phát hiện thay đổi cấu trúc và ném `ConcurrentModificationException` theo kiểu **fail-fast**.

Tuy nhiên, fail-fast không phải bảo đảm tuyệt đối:

- Lỗi có thể được phát hiện ở lần gọi `next()` hoặc một thao tác duyệt khác.
- Không phải mọi thay đổi sẽ được phát hiện trong mọi thời điểm.
- Hành vi khi sửa nguồn trái hợp đồng có thể không xác định.
- Không được dùng ngoại lệ này để điều khiển logic nghiệp vụ hoặc làm cơ chế đồng bộ giữa các thread.

Do đó, đừng viết thuật toán theo giả định rằng chương trình **chắc chắn** ném `ConcurrentModificationException` khi sửa sai. Cách đúng là thiết kế thao tác sửa phù hợp với hợp đồng collection và iterator ngay từ đầu.

## 4. Xóa phần tử an toàn bằng Iterator.remove()

Nếu iterator hỗ trợ `remove()`, bạn có thể xóa **chính phần tử vừa được `next()` trả về**, bằng iterator đang dùng để duyệt.

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class IteratorRemoveExample {
    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));

        Iterator<Integer> iterator = numbers.iterator();

        while (iterator.hasNext()) {
            int number = iterator.next();

            if (number % 2 == 0) {
                iterator.remove();
            }
        }

        System.out.println(numbers); // [1, 3, 5]
    }
}
~~~

Đây là cách xóa đúng trong vòng duyệt của `ArrayList`. Iterator giữ vị trí và trạng thái thay đổi phù hợp nên không gây ra sai lệch như khi trực tiếp gọi `numbers.remove(...)`.

### 4.1. Hợp đồng của Iterator.remove()

`remove()` có các ràng buộc quan trọng:

1. Không thể gọi trước `next()`.
2. Chỉ được gọi **một lần cho mỗi lần `next()`**.
3. Thao tác là **tùy chọn**: không phải iterator nào cũng hỗ trợ.
4. Nếu phương thức này không được hỗ trợ, có thể nhận `UnsupportedOperationException`.
5. Nếu gọi không đúng trạng thái, có thể nhận `IllegalStateException`.

Ví dụ sai:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

Iterator<String> iterator =
        new ArrayList<>(List.of("An", "Bình")).iterator();

// iterator.remove(); // IllegalStateException: chưa gọi next().

iterator.next();
iterator.remove();

// iterator.remove(); // IllegalStateException: gọi lần thứ hai
// mà chưa có next() mới.
~~~

Với một collection không cho sửa đổi:

~~~java
Iterator<String> iterator =
        List.of("An", "Bình").iterator();

iterator.next();

// iterator.remove(); // UnsupportedOperationException
~~~

`List.of(...)` trả về danh sách không cho phép thay đổi cấu trúc. Việc có phương thức `remove()` trên giao diện không có nghĩa thao tác ấy hợp lệ với mọi instance.

### 4.2. Không dùng Iterator.remove sau forEachRemaining nếu không có bảo đảm riêng

Hợp đồng chung của `Iterator` không bảo đảm hành vi khi gọi `remove()` sau `forEachRemaining(...)`. Nếu cần xóa có điều kiện, dùng vòng `while (iterator.hasNext())` và gọi `remove()` ngay sau `next()` tương ứng.

## 5. removeIf: cách ngắn gọn để xóa theo điều kiện

Với collection có hỗ trợ thay đổi, `Collection.removeIf(Predicate)` thường là cách diễn đạt ý định rõ ràng nhất:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 3, 4, 5, 6));

boolean changed = numbers.removeIf(n -> n % 2 == 0);

System.out.println(changed); // true
System.out.println(numbers); // [1, 3, 5]
~~~

`removeIf` trả `true` nếu collection đã thay đổi. Trong hợp đồng mặc định của `Collection`, thao tác này duyệt bằng iterator và gọi `Iterator.remove()` cho phần tử thỏa predicate. Một implementation có thể cung cấp tối ưu hóa riêng.

Những điều cần lưu ý:

- Chỉ dùng khi collection cho phép xóa.
- Predicate nên chỉ **kiểm tra điều kiện**, không tự sửa chính collection đang được xử lý.
- Nếu collection không hỗ trợ xóa một phần tử phù hợp, thao tác có thể ném `UnsupportedOperationException`.
- Nếu predicate ném ngoại lệ, ngoại lệ được chuyển tiếp cho bên gọi.

Ví dụ với dữ liệu nghiệp vụ:

~~~java
record Task(String name, boolean completed) {}

List<Task> tasks = new ArrayList<>(List.of(
        new Task("Thiết kế", true),
        new Task("Kiểm thử", false),
        new Task("Triển khai", true)
));

tasks.removeIf(Task::completed);

System.out.println(tasks);
// [Task[name=Kiểm thử, completed=false]]
~~~

### 5.1. Khi nào dùng removeIf, Iterator.remove hoặc lọc tạo danh sách mới?

| Yêu cầu | Cách thường phù hợp |
|---|---|
| Xóa tất cả phần tử đáp ứng một predicate khỏi collection mutable | `removeIf` |
| Cần xử lý từng phần tử rồi quyết định xóa chính phần tử đó | `Iterator.remove` |
| Không muốn sửa collection gốc | `stream().filter(...).toList()` |
| Muốn sửa giá trị/tại vị trí cụ thể khi duyệt danh sách | `ListIterator.set` hoặc API `List` phù hợp |
| Có nhiều thread đồng thời đọc và ghi | Chọn collection concurrent và chính sách nhất quán phù hợp |

Ví dụ tạo danh sách mới, không sửa dữ liệu nguồn:

~~~java
List<Integer> source = List.of(1, 2, 3, 4, 5, 6);

List<Integer> oddNumbers = source.stream()
        .filter(n -> n % 2 != 0)
        .toList();

System.out.println(source);     // [1, 2, 3, 4, 5, 6]
System.out.println(oddNumbers); // [1, 3, 5]
~~~

`Stream.toList()` trả danh sách không cho sửa đổi. Nếu cần kết quả mutable, có thể thu thập vào `ArrayList` bằng `Collectors.toCollection(ArrayList::new)`.

## 6. ListIterator: duyệt hai chiều và chỉnh sửa danh sách

`ListIterator<E>` là một iterator dành cho `List`, hỗ trợ duyệt tiến, lùi và một số thao tác chỉnh sửa tại vị trí của iterator.

| Phương thức | Công dụng |
|---|---|
| `hasNext()`, `next()` | Kiểm tra và lấy phần tử tiếp theo |
| `hasPrevious()`, `previous()` | Kiểm tra và lấy phần tử phía trước |
| `nextIndex()`, `previousIndex()` | Lấy chỉ số phần tử tương ứng |
| `remove()` | Xóa phần tử vừa được `next()` hoặc `previous()` trả về |
| `set(value)` | Thay phần tử vừa được trả về, nếu được hỗ trợ |
| `add(value)` | Chèn phần tử vào vị trí của iterator, nếu được hỗ trợ |

Ví dụ với `ArrayList`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;

public class ListIteratorExample {
    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("An", "Bình"));

        ListIterator<String> iterator = names.listIterator();

        while (iterator.hasNext()) {
            String name = iterator.next();

            if (name.equals("An")) {
                iterator.set("Anh"); // Thay phần tử vừa duyệt.
            }

            if (name.equals("Bình")) {
                iterator.add("Chi"); // Chèn tại vị trí iterator.
            }
        }

        System.out.println(names); // [Anh, Bình, Chi]

        while (iterator.hasPrevious()) {
            System.out.println(iterator.previous());
        }
        // Chi, Bình, Anh
    }
}
~~~

`ListIterator` giữ một **vị trí con trỏ giữa các phần tử**. Gọi `next()` di chuyển con trỏ sang phải; gọi `previous()` di chuyển sang trái. Phương thức `add` chèn vào vị trí con trỏ và có ảnh hưởng đến kết quả của các lời gọi tiếp theo theo hợp đồng của `ListIterator`.

`set` và `remove` phụ thuộc vào lần gọi `next` hoặc `previous` gần nhất, và có những ràng buộc trạng thái sau `add` hoặc `remove`. Vì vậy, không được giả định có thể gọi `set` hoặc `remove` tùy ý ở mọi thời điểm.

### 6.1. Chỉ hỗ trợ nếu implementation cho phép

`ListIterator` của danh sách từ `List.of(...)` không cho thêm, xóa hoặc thay phần tử. `ListIterator` của `CopyOnWriteArrayList` cũng không cho chỉnh sửa thông qua iterator, dù chính danh sách đó có các phương thức cập nhật.

### 6.2. SequencedCollection và thứ tự đảo

Java hiện đại có `SequencedCollection` và các API như `reversed()` để truy cập theo thứ tự ngược đối với collection có thứ tự gặp phần tử. Với `List`, bạn có thể:

~~~java
List<String> names =
        new ArrayList<>(List.of("An", "Bình", "Chi"));

for (String name : names.reversed()) {
    System.out.println(name);
}
~~~

`reversed()` tạo **view đảo thứ tự**, không phải bản sao tách rời. Nếu việc chỉnh sửa thông qua view được hỗ trợ, thay đổi có thể tác động đến collection gốc. Đừng nhầm view này với snapshot an toàn để sửa nguồn tùy ý trong lúc duyệt.

## 7. Với Map: duyệt entrySet và xóa mapping

`Map` không trực tiếp là một `Iterable`. Thông thường, bạn duyệt thông qua `entrySet()`, `keySet()` hoặc `values()`.

Nếu cần loại bỏ mapping của `HashMap` trong khi duyệt, hãy dùng iterator của một view hỗ trợ xóa:

~~~java
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

public class MapRemovalExample {
    public static void main(String[] args) {
        Map<String, Integer> scores = new HashMap<>(
                Map.of("An", 0, "Bình", 9, "Chi", 0)
        );

        Iterator<Map.Entry<String, Integer>> iterator =
                scores.entrySet().iterator();

        while (iterator.hasNext()) {
            Map.Entry<String, Integer> entry = iterator.next();

            if (entry.getValue() == 0) {
                iterator.remove();
            }
        }

        System.out.println(scores); // {Bình=9}
    }
}
~~~

`iterator.remove()` xóa mapping của entry vừa lấy. Còn nếu vừa duyệt `entrySet` vừa gọi `scores.remove(key)` trên cùng `HashMap`, iterator có thể bị invalidated do thay đổi cấu trúc.

Để thay toàn bộ các giá trị mà không xóa entry, có thể dùng `Map.replaceAll` ngoài vòng duyệt:

~~~java
scores.replaceAll((name, score) -> score + 1);
~~~

Nếu yêu cầu là xóa theo điều kiện tại một thời điểm riêng biệt, cũng có thể dùng view hỗ trợ xóa:

~~~java
scores.entrySet().removeIf(entry -> entry.getValue() < 0);
~~~

Lưu ý `HashMap` không bảo đảm thứ tự phần tử khi in ra; ví dụ trên chỉ có một entry còn lại nên kết quả hiển thị không bị ảnh hưởng bởi thứ tự.

## 8. Không phải iterator nào cũng fail-fast

Hành vi khi nguồn dữ liệu thay đổi tùy collection và đặc tả của iterator. Có ba nhóm cơ chế cần phân biệt:

| Cơ chế | Ý tưởng | Ví dụ thường gặp |
|---|---|---|
| **Fail-fast (best effort)** | Có thể phát hiện thay đổi cấu trúc trái hợp đồng và ném `ConcurrentModificationException` | Iterator của `ArrayList`, `HashMap` |
| **Snapshot** | Duyệt dữ liệu theo trạng thái đã chụp khi tạo iterator; không thấy thay đổi cấu trúc sau đó | Iterator của `CopyOnWriteArrayList` |
| **Weakly consistent** | Có thể tiếp tục duyệt dù collection đang thay đổi; không cam kết ảnh chụp cố định của mọi phần tử | Iterator của `ConcurrentHashMap` |

Các tên này mô tả **chính sách quan sát dữ liệu**; không có một giao diện Java tên là "FailSafeIterator". Thuật ngữ "fail-safe" đôi khi xuất hiện trong tài liệu phổ thông, nhưng không nên xem đó là một hợp đồng chuẩn chung.

### 8.1. CopyOnWriteArrayList: iterator theo snapshot

`CopyOnWriteArrayList` là một danh sách thread-safe, phù hợp khi số lần đọc/duyệt nhiều hơn đáng kể so với số lần sửa.

~~~java
import java.util.Iterator;
import java.util.concurrent.CopyOnWriteArrayList;

CopyOnWriteArrayList<String> names =
        new CopyOnWriteArrayList<>();

names.add("An");
names.add("Bình");

Iterator<String> iterator = names.iterator();

names.add("Chi");

while (iterator.hasNext()) {
    System.out.println(iterator.next());
}
// An
// Bình

System.out.println(names);
// [An, Bình, Chi]
~~~

Iterator đã tạo trước khi thêm "Chi" nên chỉ nhìn thấy trạng thái ở thời điểm tạo iterator. Các thao tác cập nhật trên danh sách tạo bản sao mảng lưu trữ, khiến ghi dữ liệu thường đắt hơn so với `ArrayList`.

Điều quan trọng:

- Iterator snapshot **không ném `ConcurrentModificationException` do chỉnh sửa danh sách sau khi tạo iterator**.
- Iterator không nhìn thấy phần tử mới thêm/xóa sau thời điểm snapshot.
- Iterator không hỗ trợ `remove`, `set` hoặc `add`; các thao tác tương ứng sẽ ném `UnsupportedOperationException`.
- Snapshot của iterator là snapshot của **các tham chiếu phần tử**, không tự sao chép sâu trạng thái bên trong các đối tượng mutable.

### 8.2. ConcurrentHashMap: iterator weakly consistent

`ConcurrentHashMap` cho phép truy cập và cập nhật map đồng thời với mức độ concurrency cao. Iterator của các view không ném `ConcurrentModificationException` do thay đổi đồng thời của map.

~~~java
import java.util.Iterator;
import java.util.concurrent.ConcurrentHashMap;

ConcurrentHashMap<String, Integer> scores =
        new ConcurrentHashMap<>();

scores.put("An", 5);
scores.put("Bình", 8);

Iterator<String> keys = scores.keySet().iterator();

scores.put("Chi", 10);

while (keys.hasNext()) {
    System.out.println(keys.next());
}
~~~

Không có kết quả in chính xác nào được cam kết về việc iterator tạo trước `put("Chi", 10)` có nhìn thấy "Chi" hay không. Nó có thể quan sát các cập nhật đã xảy ra từ lúc iterator được tạo, theo hợp đồng của collection.

**Weakly consistent không đồng nghĩa snapshot.** Nếu nghiệp vụ đòi hỏi một ảnh nhất quán tại một thời điểm, phải thiết kế phương án đồng bộ, snapshot hoặc transaction phù hợp; chỉ chuyển sang `ConcurrentHashMap` không tự giải quyết yêu cầu đó.

### 8.3. Collections.synchronizedList và vòng duyệt

`Collections.synchronizedList(...)` cung cấp một view đồng bộ cho các thao tác truy cập, nhưng iterator nhận được **không được tự động đồng bộ hóa trong toàn bộ quá trình duyệt**.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

List<String> shared =
        Collections.synchronizedList(new ArrayList<>());

shared.add("An");
shared.add("Bình");

synchronized (shared) {
    Iterator<String> iterator = shared.iterator();

    while (iterator.hasNext()) {
        System.out.println(iterator.next());
    }
}
~~~

Mọi luồng truy cập vào `shared` phải tuân thủ cùng một quy ước khóa để tránh sửa nguồn trong lúc vòng duyệt giữ lock. Nếu không, hành vi vẫn có thể không an toàn.

## 9. Spliterator là gì?

`Spliterator<T>` là giao diện phục vụ **duyệt** và **phân chia** phần tử của một nguồn. Tên gọi kết hợp ý tưởng *splitting* và *iterator*.

Nguồn có thể là một collection, mảng hoặc nguồn do chương trình tự cung cấp. Các phương thức chính:

- `tryAdvance(Consumer)`: xử lý một phần tử tiếp theo và trả `true` nếu có phần tử.
- `forEachRemaining(Consumer)`: xử lý toàn bộ phần tử còn lại.
- `trySplit()`: cố gắng chia một phần tử nguồn thành một spliterator mới.
- `estimateSize()`: ước lượng số phần tử còn lại.
- `getExactSizeIfKnown()`: trả số lượng chính xác khi có thể xác định, nếu không trả `-1`.
- `characteristics()` và `hasCharacteristics(flags)`: công bố đặc tính của nguồn.
- `getComparator()`: áp dụng khi spliterator có đặc tính `SORTED`.

Khác với `Iterator`, giao diện `Spliterator` **không có `remove()`**. Nó tập trung vào quá trình tiêu thụ phần tử và phân chia công việc, không phải vào thao tác sửa nguồn khi duyệt.

### 9.1. Duyệt từng phần tử bằng tryAdvance

~~~java
import java.util.List;
import java.util.Spliterator;

public class SpliteratorAdvance {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");
        Spliterator<String> spliterator = names.spliterator();

        boolean first = spliterator.tryAdvance(
                name -> System.out.println("Đầu tiên: " + name)
        );

        System.out.println(first); // true

        spliterator.forEachRemaining(System.out::println);
        // Bình
        // Chi

        System.out.println(
                spliterator.tryAdvance(System.out::println)
        ); // false
    }
}
~~~

`tryAdvance` nhận một `Consumer`; có thể dùng lambda hoặc method reference. Nó làm tiến trình duyệt tiến lên một phần tử khi có dữ liệu.

`forEachRemaining` tiếp tục từ vị trí hiện tại. Sau khi tiêu thụ hết, spliterator không tự khởi động lại.

### 9.2. Phân chia dữ liệu với trySplit

~~~java
import java.util.List;
import java.util.Spliterator;

public class SpliteratorSplit {
    public static void main(String[] args) {
        List<Integer> numbers =
                List.of(1, 2, 3, 4, 5, 6, 7, 8);

        Spliterator<Integer> remainder =
                numbers.spliterator();

        Spliterator<Integer> prefix =
                remainder.trySplit();

        if (prefix != null) {
            System.out.println("Phần tách:");
            prefix.forEachRemaining(System.out::println);
        }

        System.out.println("Phần còn lại:");
        remainder.forEachRemaining(System.out::println);
    }
}
~~~

`trySplit()` trả về một spliterator mới nếu có thể tách, hoặc `null` nếu không thể/không nên tách. Sau phép chia, hai spliterator bao phủ các phần dữ liệu còn lại không trùng nhau theo hợp đồng tách.

Với spliterator có `ORDERED`, phần được trả về biểu diễn một **tiền tố** của các phần tử còn lại theo thứ tự gặp. Vì thế, duyệt tiền tố rồi đến phần còn lại có thể tái tạo thứ tự ban đầu. Tuy nhiên, **không được giả định luôn chia chính xác một nửa**, và một spliterator không bắt buộc phải tách được.

### 9.3. Hình dung quy trình chia

~~~text
Nguồn: [1, 2, 3, 4, 5, 6, 7, 8]
                      |
                      v
                 Spliterator
                      |
                  trySplit()
                 /          \
                v            v
            prefix        remainder
             [1..4]          [5..8]
             (minh họa, không bảo đảm tỷ lệ chia)
~~~

Một thuật toán xử lý song song có thể tiếp tục chia từng phần, giao mỗi spliterator con cho một luồng phù hợp rồi tổng hợp kết quả.

Bản thân `Spliterator` không tự tạo thread. Việc phân phối công việc và đồng bộ kết quả thuộc về chương trình hoặc framework, ví dụ Stream API.

## 10. Đặc tính của Spliterator

`Spliterator` cung cấp các hằng số đặc tính dưới dạng bit flag. Chúng giúp thư viện xử lý nguồn dữ liệu chính xác và tối ưu hơn.

| Characteristic | Ý nghĩa |
|---|---|
| `ORDERED` | Có **encounter order** được xác định |
| `DISTINCT` | Không có hai phần tử khác vị trí được xem là bằng nhau theo `equals` |
| `SORTED` | Các phần tử có thứ tự sắp xếp theo comparator/natural order tương ứng |
| `SIZED` | Ước lượng kích thước là chính xác nếu không có thay đổi cấu trúc nguồn |
| `SUBSIZED` | Các spliterator tạo ra khi chia tiếp cũng thỏa `SIZED` và `SUBSIZED` theo hợp đồng |
| `NONNULL` | Nguồn bảo đảm không trả về phần tử `null` |
| `IMMUTABLE` | Nguồn không thể bị thay đổi cấu trúc trong quá trình duyệt |
| `CONCURRENT` | Nguồn hỗ trợ thay đổi đồng thời theo chính sách mà implementation công bố |

Ví dụ kiểm tra đặc tính:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

List<String> names =
        new ArrayList<>(List.of("An", "Bình", "Chi"));

Spliterator<String> spliterator = names.spliterator();

System.out.println(
        spliterator.hasCharacteristics(Spliterator.ORDERED)
); // true

System.out.println(
        spliterator.hasCharacteristics(Spliterator.SIZED)
); // true

System.out.println(spliterator.estimateSize()); // 3
~~~

Khi kiểm tra nhiều flag, `hasCharacteristics(mask)` yêu cầu spliterator có **tất cả** các flag trong mask.

### 10.1. ORDERED không đồng nghĩa SORTED

Một `ArrayList` có thứ tự gặp theo chỉ số, nên spliterator của nó thường báo `ORDERED`. Nhưng các phần tử có thể ở bất kỳ thứ tự giá trị nào, nên không có nghĩa chúng đã được sắp xếp.

Một `TreeSet` có thứ tự phần tử theo comparator/natural order, nên spliterator của nó có thể báo cả `ORDERED` và `SORTED`.

Với spliterator có `SORTED`, `getComparator()` trả về comparator khi dùng comparator tường minh, hoặc `null` nếu thứ tự tự nhiên được áp dụng. Nếu không có `SORTED`, lời gọi `getComparator()` ném `IllegalStateException`.

### 10.2. SIZED và SUBSIZED

`estimateSize()` là một ước lượng và có thể trả `Long.MAX_VALUE` nếu không biết kích thước hữu hạn. `getExactSizeIfKnown()` chỉ trả độ dài chính xác khi đặc tính tương ứng cho phép; nếu không, trả `-1`.

Không nên gán `SIZED` cho một spliterator tùy biến nếu số phần tử có thể phát ra thực tế không khớp với con số báo cáo trong điều kiện mà đặc tính yêu cầu.

`SUBSIZED` quan trọng cho chia dữ liệu: nó bảo đảm các phần con được chia tiếp cũng có thể báo kích thước chính xác theo hợp đồng.

### 10.3. IMMUTABLE và CONCURRENT khác nhau

`IMMUTABLE`: cấu trúc nguồn không thể bị sửa trong lúc spliterator duyệt. `CONCURRENT`: cấu trúc nguồn **có thể** bị sửa đồng thời một cách an toàn theo chính sách đã công bố.

Một top-level spliterator không nên báo đồng thời `IMMUTABLE` và `CONCURRENT` vì hai ý nghĩa này mâu thuẫn. Tương tự, spliterator top-level dạng `CONCURRENT` không nên báo `SIZED` vì số phần tử có thể thay đổi trong khi duyệt.

Đừng đánh đồng **unmodifiable view** với `IMMUTABLE`: `Collections.unmodifiableList(backing)` có thể không cho sửa qua view, nhưng collection gốc `backing` vẫn có thể được thay đổi qua tham chiếu khác.

## 11. Late-binding, fail-fast và tương tác với sửa đổi nguồn

Một số spliterator là **late-binding**: chỉ gắn với nguồn một cách đủ cụ thể vào lúc bắt đầu duyệt, chia hoặc kiểm tra kích thước.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

List<String> names =
        new ArrayList<>(List.of("An", "Bình"));

Spliterator<String> spliterator = names.spliterator();

// Sửa trước khi spliterator bắt đầu bind.
names.add("Chi");

spliterator.forEachRemaining(System.out::println);
// Với spliterator late-binding của ArrayList:
// An, Bình, Chi
~~~

Sau khi spliterator đã bind và bắt đầu duyệt, sửa cấu trúc của một collection fail-fast có thể dẫn đến `ConcurrentModificationException`. Dù vậy, như với `Iterator`, cơ chế này là **best effort**, không phải biện pháp đồng bộ hóa.

Đặc biệt, `forEachRemaining` của một spliterator có thể kiểm tra thay đổi cấu trúc **sau khi** xử lý một nhóm phần tử, thay vì ngay sau mỗi phần tử. Vì vậy, không được dùng kết quả ném ngoại lệ để suy luận chắc chắn phần tử nào đã được xử lý.

### 11.1. Một spliterator không được nhiều thread cùng điều khiển

Theo hợp đồng chung, `Spliterator` không được kỳ vọng tự thread-safe. Khi một thread gọi `trySplit()` rồi chuyển spliterator con cho một thread khác, mỗi spliterator phải được một luồng sử dụng tại một thời điểm theo cơ chế quản lý phù hợp.

Không gọi đồng thời `tryAdvance` hoặc `trySplit` trên cùng một spliterator mà không có hợp đồng riêng cho phép.

### 11.2. Không can thiệp vào nguồn trong callback

~~~java
List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 3, 4));

Spliterator<Integer> spliterator = numbers.spliterator();

// Sai nguyên tắc với ArrayList thường:
spliterator.forEachRemaining(n -> {
    if (n % 2 == 0) {
        numbers.remove(n);
    }
});
~~~

Đoạn mã này cố ý minh họa cách làm không an toàn. Khi cần lọc để tạo kết quả mới, hãy xử lý bên ngoài:

~~~java
List<Integer> odds = numbers.stream()
        .filter(n -> n % 2 != 0)
        .toList();
~~~

Khi cần sửa nguồn, dùng `removeIf` trực tiếp trên collection mutable **trước hoặc sau** quá trình duyệt, không sửa nguồn đang được một spliterator thông thường sử dụng.

## 12. Spliterator và Stream API

Các phương thức `Collection.stream()` và `parallelStream()` sử dụng cơ chế spliterator của nguồn để hỗ trợ việc duyệt, phân chia và xử lý.

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

int sum = numbers.stream()
        .filter(n -> n % 2 == 0)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 12
~~~

Với collection thông thường, hãy **ưu tiên `collection.stream()`** thay vì tự tạo stream từ spliterator. Chỉ cần `StreamSupport` khi bạn có một nguồn tùy biến hoặc cần xây dựng stream ở mức thấp.

Ví dụ chuyển một iterator thành spliterator:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class StreamSupportExample {
    public static void main(String[] args) {
        Iterator<String> iterator =
                List.of("Java", "Kotlin", "Scala").iterator();

        Spliterator<String> spliterator =
                Spliterators.spliteratorUnknownSize(
                        iterator,
                        Spliterator.ORDERED
                );

        List<String> upper = StreamSupport
                .stream(spliterator, false)
                .map(String::toUpperCase)
                .toList();

        System.out.println(upper);
    }
}
~~~

`spliteratorUnknownSize` thích hợp khi chưa biết số phần tử. Chỉ khai báo những characteristic mà nguồn thực sự bảo đảm; báo sai đặc tính có thể khiến các thuật toán tiêu thụ nguồn hoạt động không đúng.

### 12.1. Parallel stream không mặc định nhanh hơn

~~~java
long total = List.of(1, 2, 3, 4, 5, 6)
        .parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 21
~~~

`parallelStream` có thể chia nguồn và thực hiện các phần công việc trên nhiều thread. Tuy nhiên:

- Tách, lập lịch và gộp kết quả có chi phí.
- Với dữ liệu nhỏ, song song có thể chậm hơn tuần tự.
- Nguồn và thao tác trung gian cần phù hợp cho xử lý song song.
- Các hàm xử lý phải không can thiệp vào nguồn (*non-interfering*); nếu có trạng thái chia sẻ, cần bảo đảm tính an toàn.
- Không được giả định `forEach` trên parallel stream giữ đúng encounter order.

Nếu cần giữ encounter order khi thực hiện hành động có thứ tự, cân nhắc `forEachOrdered`, đồng thời hiểu rằng việc bảo đảm thứ tự có thể làm giảm lợi ích song song.

### 12.2. Primitive Spliterator

Java có các giao diện chuyên biệt:

- `Spliterator.OfInt`
- `Spliterator.OfLong`
- `Spliterator.OfDouble`

Chúng cho phép duyệt dữ liệu nguyên thủy và tránh một phần chi phí boxing/unboxing không cần thiết trong các trường hợp phù hợp.

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

Spliterator.OfInt ints =
        IntStream.rangeClosed(1, 4).spliterator();

ints.forEachRemaining((int n) ->
        System.out.println(n * n)
);
// 1
// 4
// 9
// 16
~~~

## 13. Các chiến lược an toàn khi cần sửa trong quá trình xử lý

Không có một quy tắc áp dụng cho mọi collection. Có thể chọn theo mục tiêu thực tế.

### 13.1. Một thread, cần xóa trực tiếp

~~~java
List<String> names =
        new ArrayList<>(List.of("", "An", "", "Bình"));

names.removeIf(String::isEmpty);

System.out.println(names); // [An, Bình]
~~~

`removeIf` ngắn gọn và thể hiện rõ điều kiện lọc.

### 13.2. Một thread, cần kết hợp xử lý và xóa

~~~java
List<Integer> numbers =
        new ArrayList<>(List.of(3, 8, 12, 15));

Iterator<Integer> iterator = numbers.iterator();

while (iterator.hasNext()) {
    int n = iterator.next();

    if (n > 10) {
        iterator.remove();
    } else {
        System.out.println("Giữ: " + n);
    }
}
~~~

Trong vòng lặp, chỉ dùng **iterator hiện tại** để xóa phần tử vừa lấy.

### 13.3. Không sửa nguồn, tạo kết quả mới

~~~java
List<String> names = List.of("An", "Bình", "Chi");

List<String> selected = names.stream()
        .filter(name -> name.length() >= 3)
        .toList();
~~~

Cách này giảm khả năng làm ảnh hưởng những nơi khác đang giữ tham chiếu đến collection gốc.

### 13.4. Nhiều luồng đọc, thỉnh thoảng ghi

Nếu một danh sách được đọc rất nhiều nhưng hiếm khi sửa, `CopyOnWriteArrayList` có thể phù hợp. Mỗi lần chỉnh sửa thường sao chép mảng lưu trữ, nên cần cân nhắc kích thước danh sách và tần suất ghi.

### 13.5. Nhiều luồng cần cập nhật map

Nếu đọc và ghi map đồng thời là yêu cầu thường xuyên, cân nhắc `ConcurrentHashMap`. Tuy nhiên, việc lặp qua map khi có cập nhật có thể quan sát các trạng thái thay đổi; nếu cần snapshot nhất quán, phải có cơ chế riêng.

### 13.6. Cần duyệt trong khi dữ liệu khác đang cập nhật nhưng vẫn có kết quả ổn định

Có thể tạo bản sao trước, sau đó duyệt bản sao:

~~~java
List<String> source =
        new ArrayList<>(List.of("An", "Bình"));

List<String> snapshot = List.copyOf(source);

source.add("Chi");

for (String name : snapshot) {
    System.out.println(name);
}
// An
// Bình
~~~

`List.copyOf` tạo danh sách kết quả không cho sửa đổi, tách khỏi những thay đổi cấu trúc tiếp theo của danh sách nguồn. Nhưng đây là **bản sao nông**: đối tượng phần tử mutable vẫn có thể bị sửa thông qua tham chiếu khác.

Ngoài ra, nếu nhiều luồng **đang sửa nguồn đúng lúc tạo bản sao**, việc sao chép cần được phối hợp theo hợp đồng thread-safety của nguồn. `List.copyOf` không tự biến mọi collection không thread-safe thành nguồn snapshot đồng bộ.

## 14. Bảng chọn cơ chế theo yêu cầu

| Tình huống | Lựa chọn | Điều cần nhớ |
|---|---|---|
| Chỉ duyệt đọc | Enhanced `for` hoặc `forEach` | Không sửa cấu trúc nguồn trong callback |
| Duyệt và xóa phần tử hiện tại | `Iterator.remove` | Phải được implementation hỗ trợ |
| Xóa hàng loạt theo điều kiện | `Collection.removeIf` | Predicate không nên sửa nguồn |
| Duyệt list hai chiều, chèn hoặc thay ở vị trí iterator | `ListIterator` | Theo dõi hợp đồng `next/previous/add/set/remove` |
| Lọc mà giữ nguyên nguồn | Stream + `filter` + `toList` | Danh sách kết quả không cho sửa đổi |
| Xử lý dữ liệu có thể phân chia | `Spliterator` hoặc Stream API | Không tự giả định chia đều hoặc song song luôn hiệu quả |
| Nhiều lượt đọc và ít lượt ghi đồng thời | `CopyOnWriteArrayList` | Iterator snapshot, sửa tốn sao chép |
| Map được cập nhật đồng thời | `ConcurrentHashMap` | Iterator weakly consistent |
| Cần một thứ tự ổn định | Collection có hợp đồng thứ tự hoặc sắp xếp | `HashSet` và `HashMap` không cam kết thứ tự |
| Cần snapshot nhất quán nhiều bước | Cơ chế đồng bộ/snapshot theo nghiệp vụ | Concurrent collection không tự là transaction |

## 15. Ví dụ tổng hợp: dọn danh sách công việc và thống kê

Ví dụ sau kết hợp `removeIf`, `Iterator`, `Spliterator` và Stream, đồng thời tránh sửa nguồn trong lúc một traversal khác đang chạy.

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;

public class CollectionTraversalDemo {
    record Job(String id, int priority, boolean completed) {}

    public static void main(String[] args) {
        List<Job> jobs = new ArrayList<>(List.of(
                new Job("J-101", 1, true),
                new Job("J-102", 8, false),
                new Job("J-103", 4, false),
                new Job("J-104", 9, false)
        ));

        // 1. Xóa toàn bộ job đã hoàn tất khi chưa bắt đầu duyệt.
        jobs.removeIf(Job::completed);

        // 2. Duyệt để hiển thị phần tử còn lại.
        Iterator<Job> iterator = jobs.iterator();
        while (iterator.hasNext()) {
            Job job = iterator.next();
            System.out.println(job.id());
        }

        // 3. Tạo danh sách mới chỉ gồm job ưu tiên cao.
        List<String> urgentIds = jobs.stream()
                .filter(job -> job.priority() >= 8)
                .map(Job::id)
                .toList();

        System.out.println(urgentIds); // [J-102, J-104]

        // 4. Lấy Spliterator mới để duyệt phần tử đang có.
        Spliterator<Job> spliterator = jobs.spliterator();
        spliterator.forEachRemaining(job ->
                System.out.println(job.id() + ": " + job.priority())
        );
    }
}
~~~

Phân tích:

1. `jobs.removeIf(Job::completed)` xóa phần tử trước khi tạo iterator.
2. Iterator sau đó chỉ quan sát các job còn lại và không bị sửa cấu trúc trong vòng duyệt.
3. Stream tạo kết quả mới, không thay đổi `jobs`.
4. Spliterator lấy sau các thay đổi, duyệt đúng trạng thái hiện tại của danh sách.
5. Không dùng `ConcurrentModificationException` để điều khiển logic và không giả định rằng spliterator tự thực thi song song.

## 16. Lỗi phổ biến và cách kiểm tra

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| `ConcurrentModificationException` trong enhanced `for` | Gọi `remove/add` trực tiếp trên collection khi iterator đang duyệt | Dùng `removeIf` hoặc `Iterator.remove` |
| `IllegalStateException` khi gọi `Iterator.remove` | Chưa `next` hoặc gọi `remove` quá một lần | Mỗi lần `next` tối đa một lần `remove` |
| `UnsupportedOperationException` khi xóa | Iterator hoặc collection không cho sửa | Đọc hợp đồng collection; dùng bản mutable nếu cần |
| `NoSuchElementException` | Gọi `next` khi đã hết phần tử | Kiểm tra `hasNext` |
| Lọc xong nhưng nguồn không thay đổi | `stream().filter(...).toList()` tạo kết quả mới | Gán kết quả mới hoặc dùng `removeIf` nếu thực sự muốn sửa |
| Iterator không thấy phần tử vừa thêm | Snapshot iterator của `CopyOnWriteArrayList` | Hiểu chính sách snapshot; tạo iterator mới khi cần |
| Iterator đôi khi thấy thay đổi, đôi khi không | Iterator weakly consistent | Không dùng nó cho báo cáo snapshot nhất quán |
| Spliterator không chia dữ liệu | `trySplit()` trả `null` | Không giả định mọi nguồn đều phân chia hiệu quả |
| Parallel stream cho kết quả sai | Callback có trạng thái chia sẻ hoặc sửa nguồn | Dùng thao tác non-interfering, cấu trúc kết quả phù hợp |
| Thứ tự `parallelStream().forEach` thay đổi | Xử lý song song không bảo đảm thứ tự hành động | Dùng `forEachOrdered` nếu thực sự cần thứ tự |
| Duyệt synchronized collection vẫn bị lỗi | Không giữ lock trong toàn bộ quá trình duyệt | Đồng bộ theo đúng hợp đồng của wrapper |
| Xóa một số phần tử rồi bỏ sót phần còn lại | Vừa duyệt bằng chỉ số tăng vừa xóa khiến chỉ số dịch chuyển | Dùng `removeIf`, iterator hoặc chiến lược chỉ số phù hợp |

## 17. Checklist khi viết mã Java 27

- Collection đang dùng có bảo đảm thứ tự duyệt hay không?
- Đoạn mã chỉ đọc, cần sửa phần tử, hay cần thêm/xóa cấu trúc?
- Nếu xóa phần tử trong lượt duyệt, có thể dùng `removeIf` hoặc `Iterator.remove` không?
- Iterator của implementation có hỗ trợ `remove`/`set`/`add` không?
- Có dùng callback của `forEach`, `forEachRemaining` hay Stream mà vô tình thay đổi nguồn không?
- Fail-fast có đang bị nhầm thành cơ chế đồng bộ hoặc một ngoại lệ chắc chắn xảy ra không?
- Với nhiều thread, collection là snapshot, weakly consistent hay cần khóa riêng?
- Có cần kết quả nhất quán tại một thời điểm hay có thể chấp nhận thay đổi được quan sát dần?
- Spliterator có đúng các characteristic mà thuật toán đang dựa vào không?
- Spliterator được chia rồi trao cho mỗi thread với quyền sở hữu rõ ràng chưa?
- Đang sử dụng stream tuần tự hay song song, và các hàm xử lý có non-interfering không?
- Nếu cần một bản sao, có phân biệt sao chép cấu trúc và sao chép sâu các đối tượng phần tử không?

## Tài liệu tham khảo chính thức

- [Iterator — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Iterator.html)
- [Iterable — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Iterable.html)
- [ListIterator — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ListIterator.html)
- [Collection — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collection.html)
- [Spliterator — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Spliterator.html)
- [Spliterators — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Spliterators.html)
- [ArrayList — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayList.html)
- [ConcurrentModificationException — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ConcurrentModificationException.html)
- [CopyOnWriteArrayList — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)
- [ConcurrentHashMap — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Stream — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
- [StreamSupport — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/StreamSupport.html)
