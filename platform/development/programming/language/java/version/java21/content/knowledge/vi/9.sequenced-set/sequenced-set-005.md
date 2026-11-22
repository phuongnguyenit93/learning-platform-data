# Reversed view của SequencedSet

`SequencedSet` là một tập hợp vừa bảo đảm các phần tử không trùng lặp như `Set`, vừa có encounter order (thứ tự duyệt) xác định như `SequencedCollection`. Trong Java 21, interface này bổ sung phương thức `reversed()` để cung cấp một view có thứ tự ngược với tập hợp ban đầu.

Reversed view hữu ích khi cần duyệt dữ liệu từ mới nhất đến cũ nhất, xử lý phần tử cuối trước hoặc hiển thị thứ tự ngược mà không phải tạo một tập hợp mới. Tuy nhiên, cần hiểu rõ khác biệt giữa view và bản sao, cách thay đổi dữ liệu qua view, cũng như hành vi riêng của các implementation như `LinkedHashSet` và `TreeSet`.

## 1. SequencedSet và encounter order

`SequencedSet<E>` thuộc package `java.util`, được bổ sung trong Java 21. Interface này mở rộng cả `Set<E>` và `SequencedCollection<E>`.

Một `SequencedSet` có hai đặc điểm:

- **Không chứa phần tử trùng lặp:** tuân theo hợp đồng của `Set`.
- **Có thứ tự gặp phần tử xác định:** các thao tác duyệt có thể quan sát phần tử từ đầu đến cuối.

Ví dụ, `LinkedHashSet` duy trì thứ tự chèn:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> names = new LinkedHashSet<>();

        names.add("An");
        names.add("Bình");
        names.add("Chi");

        System.out.println(names); // [An, Bình, Chi]
    }
}
```

Trong ví dụ này, phần tử đầu tiên là `An`, phần tử cuối cùng là `Chi`. Encounter order là một phần quan trọng của cách dữ liệu được quan sát khi duyệt set.

Không phải mọi `Set` đều là `SequencedSet`. Chẳng hạn, kiểu khai báo `Set<E>` không cung cấp hợp đồng về thứ tự gặp phần tử. Nếu cần gọi `reversed()`, biến cần có kiểu `SequencedSet<E>` hoặc một kiểu con phù hợp.

## 2. reversed() tạo view có thứ tự ngược

Cú pháp:

```java
SequencedSet<E> reversed = original.reversed();
```

Phương thức `reversed()` trả về một `SequencedSet` có encounter order đảo ngược so với tập hợp ban đầu:

- Phần tử cuối của tập hợp gốc trở thành phần tử đầu của view.
- Phần tử đầu của tập hợp gốc trở thành phần tử cuối của view.
- Thứ tự tương đối của các phần tử ở giữa cũng được đảo ngược.

Ví dụ:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> original = new LinkedHashSet<>();
        original.add("A");
        original.add("B");
        original.add("C");

        SequencedSet<String> reversed = original.reversed();

        System.out.println(original); // [A, B, C]
        System.out.println(reversed); // [C, B, A]
    }
}
```

Ở đây, `reversed` là view theo thứ tự ngược của `original`. Cách nhìn này cho phép xử lý dữ liệu từ cuối về đầu mà không cần tự viết vòng lặp đếm chỉ số hoặc tạo danh sách trung gian.

Kiểu trả về là `SequencedSet<E>`, vì vậy view vẫn giữ cả hai hợp đồng: thứ tự gặp phần tử và tính duy nhất của phần tử.

## 3. View khác với bản sao

Reversed view không nên được hiểu là một bản sao độc lập. Hợp đồng của `SequencedSet.reversed()` quy định thứ tự của view là ngược với collection gốc. Nếu implementation cho phép sửa đổi thông qua view, những thay đổi đó được ghi trực tiếp vào collection nền.

Với `LinkedHashSet`, tài liệu Java 21 quy định rõ cả hai chiều: sửa đổi view được truyền tới set gốc và sửa đổi set gốc được phản ánh trong view.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> original = new LinkedHashSet<>();
        original.add("A");
        original.add("B");
        original.add("C");

        SequencedSet<String> reversed = original.reversed();

        reversed.removeFirst();

        System.out.println(reversed); // [B, A]
        System.out.println(original); // [A, B]
    }
}
```

`removeFirst()` trên view xóa phần tử đầu tiên theo thứ tự đảo ngược, tức phần tử cuối của set gốc. Vì vậy, `C` bị xóa khỏi cả hai cách nhìn.

Cần lưu ý rằng hợp đồng chung của interface có một điểm phụ thuộc implementation: nếu view hỗ trợ sửa đổi thì thao tác qua view được ghi xuống collection nền, nhưng việc thay đổi trực tiếp collection nền có được phản ánh vào view hay không có thể phụ thuộc implementation. Với `LinkedHashSet`, tài liệu bảo đảm thay đổi ở set gốc được thấy trong view và ngược lại. Khi dùng implementation khác, hãy kiểm tra hợp đồng cụ thể của nó.

### 3.1. Khi cần bản sao độc lập

Nếu cần một set có thứ tự đảo ngược nhưng muốn cấu trúc dữ liệu độc lập với set ban đầu, hãy tạo bản sao tường minh:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> original = new LinkedHashSet<>();
        original.add("A");
        original.add("B");
        original.add("C");

        SequencedSet<String> reversedCopy =
                new LinkedHashSet<>(original.reversed());

        original.add("D");

        System.out.println(original);     // [A, B, C, D]
        System.out.println(reversedCopy); // [C, B, A]
    }
}
```

Constructor của `LinkedHashSet` lấy các phần tử theo thứ tự iterator của collection đầu vào. Vì đầu vào là reversed view, bản sao được tạo với thứ tự `[C, B, A]`. Sau đó, thêm `D` vào set gốc không làm thay đổi cấu trúc của bản sao.

Đây là bản sao nông (shallow copy): hai set có cấu trúc riêng nhưng vẫn có thể tham chiếu tới cùng các object phần tử. Nếu phần tử là object mutable, thay đổi trạng thái bên trong object vẫn có thể được nhìn thấy qua cả hai set.

## 4. Thao tác hai đầu trên reversed view

Các phương thức hai đầu của view được hiểu theo thứ tự đảo ngược. Với implementation hỗ trợ sửa đổi như `LinkedHashSet`, thao tác ở một đầu của view tương ứng với đầu đối diện của set gốc.

| Thao tác trên reversed view | Tác động tương ứng trên set gốc |
|---|---|
| `getFirst()` | Đọc phần tử cuối của set gốc |
| `getLast()` | Đọc phần tử đầu của set gốc |
| `addFirst(e)` | Đưa `e` về cuối set gốc |
| `addLast(e)` | Đưa `e` về đầu set gốc |
| `removeFirst()` | Xóa phần tử cuối set gốc |
| `removeLast()` | Xóa phần tử đầu set gốc |

Ví dụ:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> original = new LinkedHashSet<>();
        original.add("A");
        original.add("B");
        original.add("C");

        SequencedSet<String> reversed = original.reversed();

        reversed.addFirst("D");

        System.out.println(reversed); // [D, C, B, A]
        System.out.println(original); // [A, B, C, D]

        reversed.addLast("B");

        System.out.println(reversed); // [D, C, A, B]
        System.out.println(original); // [B, A, C, D]
    }
}
```

Lần gọi `reversed.addFirst("D")` đưa `D` lên đầu view, tương ứng với cuối set gốc. Ở lần gọi tiếp theo, `B` đã tồn tại; `reversed.addLast("B")` đưa nó về cuối view, tương ứng với đầu set gốc.

Các phép ánh xạ trên mô tả ý nghĩa thứ tự. Việc sửa đổi thực tế vẫn phụ thuộc implementation có hỗ trợ thao tác đó hay không.

## 5. Tính duy nhất và di chuyển phần tử trong LinkedHashSet

Một điểm đáng chú ý của `LinkedHashSet` trong Java 21 là `addFirst` và `addLast` có thể thay đổi vị trí của phần tử đã tồn tại.

Điều này khác với `add(E)`: nếu phần tử đã có trong `LinkedHashSet`, gọi `add` lần nữa không làm thay đổi encounter order. Trong khi đó:

- `addFirst(e)` bảo đảm `e` là phần tử đầu tiên; nếu đã có, nó được di chuyển lên đầu.
- `addLast(e)` bảo đảm `e` là phần tử cuối cùng; nếu đã có, nó được di chuyển xuống cuối.

Quy tắc này cũng áp dụng khi thao tác thông qua reversed view, nhưng vị trí đầu/cuối được hiểu theo thứ tự của view.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> original = new LinkedHashSet<>();
        original.add("A");
        original.add("B");
        original.add("C");

        SequencedSet<String> reversed = original.reversed();
        reversed.addFirst("A");

        System.out.println(reversed); // [A, C, B]
        System.out.println(original); // [B, C, A]
    }
}
```

Phần tử `A` đã có trong set. Đưa nó lên đầu reversed view tương ứng với việc đưa nó xuống cuối set gốc. Set vẫn chỉ có một phần tử `A`, vì `SequencedSet` duy trì tính duy nhất.

Không nên suy rộng hành vi di chuyển phần tử này cho mọi implementation của `SequencedSet`. Đây là hành vi được `LinkedHashSet` hỗ trợ và được tài liệu của lớp mô tả cụ thể.

## 6. Duyệt và xử lý dữ liệu theo thứ tự ngược

Reversed view đảo thứ tự cho các thao tác nhạy với encounter order. Có thể dùng enhanced for, `forEach`, iterator hoặc Stream API trực tiếp trên view.

Ví dụ duyệt:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> recentFiles = new LinkedHashSet<>();
        recentFiles.add("report.csv");
        recentFiles.add("summary.pdf");
        recentFiles.add("diagram.png");

        for (String file : recentFiles.reversed()) {
            System.out.println(file);
        }
    }
}
```

Kết quả:

```text
diagram.png
summary.pdf
report.csv
```

Có thể tạo stream theo encounter order đảo ngược:

```java
recentFiles.reversed()
        .stream()
        .forEachOrdered(System.out::println);
```

Dùng `forEachOrdered` khi cần giữ thứ tự encounter trong thao tác terminal của stream. Với xử lý song song, `forEach` không bảo đảm hành động được thực hiện theo encounter order.

## 7. reversed view của SortedSet và TreeSet

`SortedSet` và `TreeSet` cũng thuộc hệ phân cấp `SequencedSet`. Tuy nhiên, thứ tự của chúng được xác định bởi natural ordering hoặc `Comparator`, thay vì thứ tự chèn.

Với một sorted set, `reversed()` cung cấp view có thứ tự ngược với thứ tự sắp xếp hiện tại. Ví dụ:

```java
import java.util.SequencedSet;
import java.util.SortedSet;
import java.util.TreeSet;

class Main {
    public static void main(String[] args) {
        SortedSet<Integer> numbers = new TreeSet<>();
        numbers.add(2);
        numbers.add(5);
        numbers.add(9);

        SequencedSet<Integer> descending = numbers.reversed();

        System.out.println(numbers);   // [2, 5, 9]
        System.out.println(descending); // [9, 5, 2]
    }
}
```

Với `TreeSet`, view đảo ngược vẫn tuân theo thứ tự so sánh ngược. Khi thêm một phần tử bằng `add`, vị trí của nó được quyết định bởi comparator, không phải vị trí tùy ý do người gọi chọn.

Do đó, `SortedSet` không hỗ trợ `addFirst` và `addLast`; hai phương thức này ném `UnsupportedOperationException` vì việc ép phần tử vào một đầu có thể phá vỡ thứ tự sắp xếp. Không nên áp dụng ví dụ di chuyển phần tử của `LinkedHashSet` cho `TreeSet`.

## 8. equals và hashCode không xét encounter order

Mặc dù `SequencedSet` có thứ tự duyệt xác định, hợp đồng `equals` và `hashCode` vẫn tuân theo `Set`. Hai set chứa cùng phần tử sẽ bằng nhau bất kể thứ tự encounter.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class Main {
    public static void main(String[] args) {
        SequencedSet<String> first = new LinkedHashSet<>();
        first.add("A");
        first.add("B");
        first.add("C");

        SequencedSet<String> second = new LinkedHashSet<>();
        second.add("C");
        second.add("B");
        second.add("A");

        System.out.println(first);          // [A, B, C]
        System.out.println(second);         // [C, B, A]
        System.out.println(first.equals(second)); // true
    }
}
```

Hai set có thứ tự hiển thị khác nhau nhưng `equals` trả về `true` vì chúng có cùng tập phần tử. Nếu yêu cầu nghiệp vụ cần so sánh cả thứ tự, hãy chuyển sang một cấu trúc có hợp đồng equality theo thứ tự, chẳng hạn `List`, hoặc tự viết phép so sánh encounter order.

## 9. Giới hạn sửa đổi, đồng bộ và iterator

Không phải mọi reversed view đều cho phép sửa đổi. Nếu set gốc không hỗ trợ thao tác thêm/xóa, view tương ứng cũng có thể từ chối các thao tác sửa đổi bằng `UnsupportedOperationException`.

Ngoài ra, `LinkedHashSet` không được đồng bộ hóa. Reversed view không tự bổ sung thread safety. Nếu nhiều luồng cùng truy cập và có ít nhất một luồng sửa đổi set, chương trình cần cơ chế đồng bộ thích hợp.

Khi đang duyệt set hoặc view, tránh cấu trúc lại set thông qua một tham chiếu khác trong cùng lúc. Iterator của `LinkedHashSet` có cơ chế fail-fast và có thể ném `ConcurrentModificationException` khi phát hiện sửa đổi cấu trúc ngoài iterator. Đây là cơ chế phát hiện lỗi theo best effort, không phải cơ chế đồng bộ và không được dùng làm nền tảng bảo đảm tính đúng đắn giữa các luồng.

## 10. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi `reversed()` trên biến chỉ có kiểu `Set` | `Set` không cam kết encounter order và không khai báo phương thức này | Dùng implementation hoặc kiểu khai báo `SequencedSet` phù hợp |
| Nghĩ reversed view là bản sao | Nhầm view với collection độc lập | Tạo `new LinkedHashSet<>(original.reversed())` nếu cần bản sao |
| Cho rằng mọi thay đổi từ set gốc luôn hiển thị trên mọi reversed view | Khả năng phản ánh thay đổi phụ thuộc implementation | Kiểm tra hợp đồng; LinkedHashSet bảo đảm đồng bộ hai chiều |
| Thêm phần tử trùng bằng `addFirst` và mong có bản sao | Set không cho phép phần tử trùng | Với LinkedHashSet, phần tử hiện có được di chuyển đến vị trí yêu cầu |
| Dùng `addFirst` hoặc `addLast` trên TreeSet | Thứ tự được comparator kiểm soát | Dùng `add` để chèn theo thứ tự sắp xếp |
| So sánh hai set và mong thứ tự ảnh hưởng đến `equals` | Set equality không xét encounter order | Dùng List hoặc phép so sánh thứ tự riêng |
| Giả định reversed view an toàn đa luồng | View không tự thêm đồng bộ hóa | Đồng bộ truy cập và sửa đổi trên collection gốc theo một cơ chế thống nhất |

## 11. Cách áp dụng trong Java 21

Khi cần xử lý một `SequencedSet` theo thứ tự ngược, hãy chọn cách dùng dựa trên mục tiêu:

1. Dùng `reversed()` để duyệt hoặc đọc dữ liệu từ cuối về đầu mà không tạo collection mới.
2. Dùng trực tiếp các thao tác trên view nếu implementation hỗ trợ sửa đổi và bạn muốn thay đổi collection gốc thông qua view.
3. Tạo một `LinkedHashSet` mới từ reversed view nếu cần một cấu trúc độc lập với thứ tự đảo ngược.
4. Phân biệt hành vi của `LinkedHashSet` với `SortedSet`: linked set cho phép định vị phần tử ở hai đầu, sorted set giữ thứ tự comparator.
5. Không dựa vào thứ tự encounter khi dùng `equals` hoặc `hashCode` của Set.
6. Xem xét khả năng sửa đổi và đồng bộ hóa nếu collection được chia sẻ giữa nhiều phần của ứng dụng.

`reversed()` giúp Java 21 xử lý thứ tự ngược trực tiếp trên một `SequencedSet`. Hiểu rõ view, tính duy nhất, semantics của từng implementation và equality theo Set giúp tránh tạo bản sao không cần thiết, đồng thời giữ được hành vi dữ liệu đúng với mục tiêu của chương trình.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Oracle Java SE 21 API — LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html)
- [Oracle Java SE 21 API — SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
