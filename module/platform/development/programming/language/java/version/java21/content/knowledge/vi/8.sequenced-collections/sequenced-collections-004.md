# getFirst, getLast và hành vi khi collection rỗng

Java 21 bổ sung `SequencedCollection<E>` vào Collections Framework để biểu diễn collection có **thứ tự duyệt xác định** và có thể truy cập hai đầu. Hai phương thức `getFirst()` và `getLast()` lấy phần tử đầu hoặc cuối theo encounter order của collection. Nếu collection rỗng, cả hai đều ném `NoSuchElementException`.

Các phương thức này chỉ đọc phần tử, không xóa hay thay đổi collection. Chúng phù hợp khi chương trình cần lấy phần tử ở một đầu và muốn thể hiện rõ ý nghĩa đó thay vì tự tính chỉ số. Tuy nhiên, chỉ những kiểu có thứ tự như `List`, `Deque` và `SequencedSet` mới cung cấp API này qua kiểu khai báo tương ứng; không thể gọi trực tiếp trên mọi `Collection` hoặc `Set`.

## 1. SequencedCollection và thứ tự encounter order

`SequencedCollection<E>` là interface thuộc `java.util`, được giới thiệu trong Java 21. Nó mở rộng `Collection<E>` và `Iterable<E>`, đồng thời quy định collection có encounter order rõ ràng từ phần tử đầu đến phần tử cuối.

Một số interface liên quan:

- `List<E>`: thứ tự theo vị trí trong danh sách.
- `Deque<E>`: thứ tự từ đầu deque (head) đến cuối deque (tail).
- `SequencedSet<E>`: tập hợp không trùng phần tử nhưng có thứ tự duyệt xác định.
- `SortedSet<E>` và `NavigableSet<E>`: thứ tự theo quy tắc sắp xếp hoặc comparator.

Vì vậy, ý nghĩa của “đầu” và “cuối” phụ thuộc vào collection đang dùng. Với `ArrayList`, phần tử đầu là phần tử ở vị trí index 0. Với `LinkedHashSet`, đó là phần tử đầu tiên theo encounter order được duy trì. Với `TreeSet`, phần tử đầu và cuối lần lượt theo thứ tự sắp xếp, thường là nhỏ nhất và lớn nhất theo comparator.

Không phải mọi `Collection` đều có thứ tự như vậy. Chẳng hạn, `HashSet` không triển khai `SequencedSet`; không nên dựa vào thứ tự duyệt của nó để xác định phần tử đầu hoặc cuối.

## 2. Cú pháp và hợp đồng của getFirst/getLast

Hai phương thức có chữ ký:

```java
E getFirst();
E getLast();
```

- `getFirst()` trả về phần tử đầu tiên theo encounter order.
- `getLast()` trả về phần tử cuối cùng theo encounter order.
- Nếu collection rỗng, cả hai ném `NoSuchElementException`.
- Hai phương thức không xóa phần tử và không làm thay đổi thứ tự collection.

Đây là các phương thức đọc, không phải thao tác lấy ra khỏi collection. Nếu cần lấy đồng thời xóa phần tử ở đầu hoặc cuối, API tương ứng là `removeFirst()` hoặc `removeLast()`; các phương thức remove có thể không được hỗ trợ bởi collection bất biến hoặc không hỗ trợ xóa.

Ví dụ với `List`:

```java
import java.util.ArrayList;
import java.util.List;

public class GetEndsDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

        System.out.println(names.getFirst()); // An
        System.out.println(names.getLast());  // Chi
        System.out.println(names);            // [An, Binh, Chi]
    }
}
```

`getFirst()` và `getLast()` không yêu cầu danh sách phải mutable. Chẳng hạn, `List.of("An", "Binh")` là danh sách không sửa đổi được nhưng vẫn có thể gọi hai phương thức đọc này.

## 3. Hành vi khi collection rỗng

Trường hợp rỗng được quy định rõ: `getFirst()` và `getLast()` ném `java.util.NoSuchElementException`. Đây là unchecked exception, nên compiler không bắt buộc phải khai báo `throws` hoặc viết `catch`; chương trình cần chủ động quyết định cách xử lý.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;

public class EmptyListDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();

        try {
            System.out.println(names.getFirst());
        } catch (NoSuchElementException exception) {
            System.out.println("Danh sách chưa có phần tử đầu tiên");
        }

        try {
            System.out.println(names.getLast());
        } catch (NoSuchElementException exception) {
            System.out.println("Danh sách chưa có phần tử cuối cùng");
        }
    }
}
```

Kết quả:

```text
Danh sách chưa có phần tử đầu tiên
Danh sách chưa có phần tử cuối cùng
```

Nếu collection rỗng là trạng thái bình thường của luồng nghiệp vụ, kiểm tra `isEmpty()` trước khi gọi:

```java
static void printEnds(List<String> values) {
    if (values.isEmpty()) {
        System.out.println("Danh sách rỗng");
        return;
    }

    System.out.println("Đầu: " + values.getFirst());
    System.out.println("Cuối: " + values.getLast());
}
```

Nếu collection rỗng biểu thị vi phạm điều kiện đầu vào, có thể để `NoSuchElementException` truyền lên hoặc chuyển thành exception mang ý nghĩa nghiệp vụ rõ hơn ở ranh giới phù hợp. Không nên bắt `Exception` quá rộng chỉ để che trường hợp collection rỗng.

### Phân biệt với get(index)

Với `List`, có thể lấy phần tử đầu và cuối bằng chỉ số:

```java
List<String> names = new ArrayList<>();

// Khi có phần tử:
String first = names.get(0);
String last = names.get(names.size() - 1);
```

Tuy nhiên, khi danh sách rỗng, `get(0)` hoặc chỉ số cuối không hợp lệ sẽ ném `IndexOutOfBoundsException`. Còn `getFirst()` và `getLast()` thể hiện trực tiếp ý định lấy ở hai đầu và có hợp đồng ném `NoSuchElementException` khi rỗng. Hãy chọn API theo ngữ nghĩa mong muốn và xử lý exception đúng với hợp đồng của nó.

## 4. Phân biệt collection rỗng với phần tử đầu/cuối là null

Không phải mọi collection đều cấm `null`. Ví dụ, `ArrayList` cho phép lưu `null`. Khi danh sách có phần tử đầu tiên là `null`, `getFirst()` trả về `null`; điều đó không có nghĩa danh sách rỗng.

```java
List<String> values = new ArrayList<>();
values.add(null);

System.out.println(values.isEmpty()); // false
System.out.println(values.getFirst()); // null
```

Vì vậy, không dùng kết quả `null` của `getFirst()` hoặc `getLast()` làm dấu hiệu chung cho collection rỗng. Hãy kiểm tra `isEmpty()` nếu cần phân biệt hai trạng thái. Với collection không cho phép null, kết quả null không thể là phần tử hợp lệ theo hợp đồng của implementation đó.

Nếu API nghiệp vụ cần trả về `Optional<E>`, chỉ dùng `Optional.of(values.getFirst())` sau khi đã kiểm tra collection không rỗng và bảo đảm phần tử không null. `Optional` không biểu diễn được trạng thái “có phần tử nhưng phần tử đó là null”; do đó cần quy định rõ chính sách null trước khi chuyển kết quả sang `Optional`.

## 5. Dùng với List, Deque và SequencedSet

### List

`List` trong Java 21 kế thừa `SequencedCollection`, vì vậy mọi biến có kiểu khai báo `List<E>` đều có thể gọi `getFirst()` và `getLast()`:

```java
List<Integer> scores = new ArrayList<>(List.of(7, 8, 9));

int lowestPosition = scores.getFirst(); // 7: phần tử ở đầu danh sách
int latestPosition = scores.getLast();  // 9: phần tử ở cuối danh sách
```

Hai tên biến trong ví dụ chỉ minh họa vị trí; `getFirst()` không tự xác định giá trị nhỏ nhất và `getLast()` cũng không tự xác định giá trị lớn nhất. Chúng chỉ theo thứ tự hiện có của list.

### Deque

`Deque<E>` đã có `getFirst()` và `getLast()` từ các phiên bản Java trước; trong Java 21, `Deque` cũng là một `SequencedCollection`. Hai phương thức đọc head và tail, đồng thời ném `NoSuchElementException` nếu deque rỗng.

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;

Deque<String> tasks = new ArrayDeque<>(List.of("compile", "test", "package"));

System.out.println(tasks.getFirst()); // compile (head)
System.out.println(tasks.getLast());  // package (tail)
```

Với `Deque`, có thêm `peekFirst()` và `peekLast()`. Các phương thức `peek` trả về `null` nếu deque rỗng, trong khi `getFirst()` và `getLast()` ném `NoSuchElementException`. Các implementation `Deque` chuẩn không cho phép phần tử null, nên giá trị null từ `peek` có thể dùng để nhận biết deque rỗng theo hợp đồng của `Deque`.

### SequencedSet

`SequencedSet<E>` kết hợp tính duy nhất của `Set` với encounter order xác định. Ví dụ, `LinkedHashSet` giữ thứ tự encounter theo thứ tự thêm phần tử mới:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

SequencedSet<String> tags = new LinkedHashSet<>();
tags.add("java");
tags.add("collections");
tags.add("jdk21");

System.out.println(tags.getFirst()); // java
System.out.println(tags.getLast());  // jdk21
```

Nếu khai báo biến chỉ bằng kiểu `Set<String>`, compiler không cho gọi `getFirst()` vì `Set` không công bố API sequenced. Khi cần thao tác theo hai đầu, hãy dùng kiểu khai báo `SequencedSet<String>` hoặc `SequencedCollection<String>` và bảo đảm implementation thực sự hỗ trợ hợp đồng đó.

## 6. Làm việc qua kiểu SequencedCollection

Khi một phương thức cần nhận nhiều loại collection có thứ tự, khai báo tham số là `SequencedCollection<E>` thay vì phụ thuộc riêng vào `List<E>` hoặc `Deque<E>`:

```java
import java.util.SequencedCollection;

static <E> void printFirstAndLast(SequencedCollection<E> values) {
    if (values.isEmpty()) {
        System.out.println("Collection rỗng");
        return;
    }

    E first = values.getFirst();
    E last = values.getLast();

    System.out.println("First: " + first);
    System.out.println("Last: " + last);
}
```

Phương thức này có thể nhận `List`, `Deque` hoặc `SequencedSet` phù hợp. Nó không nhận một `Collection` bất kỳ, bởi `Collection` không đảm bảo encounter order.

Nếu collection có thể bị thread khác sửa đồng thời, thao tác `isEmpty()` rồi gọi `getFirst()` không phải một thao tác nguyên tử. Trạng thái có thể thay đổi giữa hai lời gọi. Với dữ liệu dùng chung giữa nhiều thread, hãy sử dụng cơ chế đồng bộ hoặc API concurrency phù hợp với implementation; không dựa vào cặp kiểm tra rồi truy cập như một bảo đảm atomic.

## 7. Quan hệ giữa getFirst/getLast và reversed()

`SequencedCollection` cung cấp `reversed()` để lấy một view có encounter order ngược với collection gốc. Vì hai đầu bị đảo, phần tử đầu của view đảo chính là phần tử cuối của collection ban đầu:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.SequencedCollection;

List<String> values = new ArrayList<>(List.of("A", "B", "C"));
SequencedCollection<String> reversed = values.reversed();

System.out.println(values.getFirst());    // A
System.out.println(values.getLast());     // C
System.out.println(reversed.getFirst());  // C
System.out.println(reversed.getLast());   // A
```

`reversed()` trả về view theo thứ tự đảo, không phải một bản sao được sắp xếp lại. Với implementation cho phép sửa view, thay đổi qua view có thể được ghi trực tiếp vào collection gốc. Nếu chỉ cần lấy phần tử cuối, gọi `getLast()` trực tiếp thường rõ ràng hơn việc tạo view đảo rồi gọi `getFirst()`.

## 8. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| `NoSuchElementException` tại `getFirst()` | Collection đang rỗng | Kiểm tra `isEmpty()` hoặc xử lý exception theo hợp đồng nghiệp vụ |
| `NoSuchElementException` tại `getLast()` | Không có phần tử cuối vì collection rỗng | Kiểm tra collection trước khi truy cập |
| `cannot find symbol: getFirst()` | Biến được khai báo bằng `Collection` hoặc `Set` không sequenced, hoặc đang biên dịch bằng JDK trước 21 | Dùng kiểu `List`, `Deque`, `SequencedSet`, `SequencedCollection` phù hợp và JDK 21 |
| Nhận được `null` dù collection không rỗng | Phần tử đầu/cuối thực sự là null và implementation cho phép null | Dùng `isEmpty()` để phân biệt collection rỗng với phần tử null |
| Nhận nhầm phần tử “đầu tiên” | Đang giả định thứ tự mà implementation không cam kết | Chọn implementation có encounter order xác định và khai báo qua sequenced interface |
| `UnsupportedOperationException` khi gọi thao tác đầu/cuối | Đang dùng phương thức thay đổi như `removeFirst()` trên collection không hỗ trợ xóa | Dùng `getFirst()` nếu chỉ cần đọc; kiểm tra khả năng sửa đổi trước khi remove |

Lưu ý: `getFirst()` và `getLast()` là thao tác đọc. Nếu gặp `UnsupportedOperationException`, hãy kiểm tra xem mã có thực sự đang gọi `removeFirst()`, `removeLast()` hoặc một thao tác sửa đổi khác hay không. Collection bất biến vẫn cho phép đọc hai đầu.

## 9. Checklist khi sử dụng getFirst/getLast

- Biến có kiểu khai báo hỗ trợ `SequencedCollection`, chẳng hạn `List`, `Deque` hoặc `SequencedSet`.
- Đã hiểu encounter order của implementation cụ thể.
- Đã xác định collection có thể rỗng hay không.
- Xử lý `NoSuchElementException` hoặc kiểm tra `isEmpty()` khi collection rỗng là trạng thái hợp lệ.
- Không dùng `null` làm dấu hiệu collection rỗng nếu implementation cho phép phần tử null.
- Dùng `getFirst()`/`getLast()` khi chỉ đọc; dùng `removeFirst()`/`removeLast()` khi cần lấy và xóa.
- Không giả định `isEmpty()` rồi `getFirst()` là atomic khi có thread khác sửa collection.
- Dùng `reversed()` khi cần view theo encounter order ngược, không tạo bản sao nếu không cần.

`getFirst()` và `getLast()` cung cấp cách truy cập hai đầu thống nhất cho các collection có encounter order trong Java 21. Điểm quan trọng nhất khi collection rỗng là cả hai phương thức đều ném `NoSuchElementException`; nếu collection cho phép null, giá trị trả về null vẫn có thể là một phần tử thực sự. Hiểu rõ kiểu sequenced, encounter order và hợp đồng null giúp chọn đúng cách truy cập và xử lý biên.
