# LinkedHashSet và thứ tự chèn của phần tử

## Mục tiêu

`LinkedHashSet` là một implementation của `Set` giữ thứ tự duyệt phần tử theo thứ tự chèn. Từ Java 21, lớp này còn triển khai `SequencedSet`, vì vậy có thể thao tác trực tiếp với phần tử ở đầu và cuối, lấy phần tử đầu/cuối, xóa ở hai đầu và tạo một view có thứ tự đảo ngược.

Bài học này giải thích cách `LinkedHashSet` duy trì thứ tự, sự khác nhau giữa thêm phần tử mới và thêm lại phần tử đã tồn tại, cũng như cách dùng các API `SequencedSet` trong Java 21. Nội dung tập trung vào hành vi hiện hành của Java 21.

## 1. `LinkedHashSet` là gì?

`LinkedHashSet` là một implementation của `Set`: mỗi phần tử chỉ xuất hiện một lần theo quy tắc `equals()` và `hashCode()`. Điểm khác biệt chính so với `HashSet` là `LinkedHashSet` duy trì một encounter order xác định, mặc định là thứ tự phần tử được thêm vào set lần đầu.

```java
import java.util.LinkedHashSet;
import java.util.Set;

class LinkedHashSetIntro {
    public static void main(String[] args) {
        Set<String> languages = new LinkedHashSet<>();

        languages.add("Java");
        languages.add("Kotlin");
        languages.add("Scala");

        System.out.println(languages); // [Java, Kotlin, Scala]

        for (String language : languages) {
            System.out.println(language);
        }
    }
}
```

Vòng lặp duyệt theo thứ tự `Java`, `Kotlin`, `Scala`, tương ứng với thứ tự các phần tử được thêm lần đầu. Vì vậy, `LinkedHashSet` phù hợp khi ứng dụng cần đồng thời:

- Không lưu phần tử trùng lặp.
- Duy trì thứ tự gặp phần tử.
- Duyệt dữ liệu theo một thứ tự ổn định, dễ dự đoán.

`LinkedHashSet` thường dùng bảng băm để tìm kiếm và quản lý tính duy nhất, đồng thời duy trì liên kết giữa các entry để giữ thứ tự. Cấu trúc liên kết này tạo thêm chi phí bộ nhớ so với `HashSet`, đổi lại thứ tự duyệt được xác định. Thời gian duyệt `LinkedHashSet` tỷ lệ với số phần tử, không phụ thuộc trực tiếp vào capacity của bảng băm.

## 2. Thứ tự chèn được duy trì như thế nào?

Khi gọi `add()` với một phần tử chưa có trong set, phần tử được thêm vào cuối encounter order. Nếu phần tử đã tồn tại, set không thêm bản sao và thứ tự hiện tại không thay đổi.

```java
import java.util.LinkedHashSet;

class InsertionOrderDemo {
    public static void main(String[] args) {
        var names = new LinkedHashSet<String>();

        names.add("An");
        names.add("Binh");
        names.add("Chi");
        names.add("Binh"); // đã tồn tại, không chuyển vị trí

        System.out.println(names); // [An, Binh, Chi]
    }
}
```

Lệnh `names.add("Binh")` lần thứ hai không làm `Binh` xuất hiện thêm và cũng không chuyển nó xuống cuối. Phương thức `add()` trả về `false` nếu phần tử đã có, và `true` nếu set thực sự được bổ sung phần tử mới.

Khi tạo `LinkedHashSet` từ một collection, thứ tự duyệt ban đầu của collection nguồn được dùng làm thứ tự thêm phần tử. Vì thế, nếu nguồn là `List`, thứ tự trong list được giữ:

```java
import java.util.LinkedHashSet;
import java.util.List;

var source = List.of("Red", "Green", "Blue");
var colors = new LinkedHashSet<>(source);

System.out.println(colors); // [Red, Green, Blue]
```

Nếu collection nguồn không có encounter order được bảo đảm, không nên giả định thứ tự của nó là một thứ tự nghiệp vụ ổn định. `LinkedHashSet` duy trì thứ tự mà nó nhận được khi duyệt nguồn; nó không tự sắp xếp phần tử theo tên, số hoặc một tiêu chí khác.

## 3. Phân biệt `LinkedHashSet`, `HashSet` và `TreeSet`

Các implementation của `Set` có mục đích khác nhau:

| Implementation | Encounter order | Khi nên dùng |
|---|---|---|
| `HashSet` | Không bảo đảm thứ tự duyệt | Chỉ cần tính duy nhất và thao tác tập hợp dựa trên hash |
| `LinkedHashSet` | Theo thứ tự chèn | Cần loại trùng nhưng vẫn giữ thứ tự phần tử được thêm |
| `TreeSet` | Theo thứ tự sắp xếp tự nhiên hoặc comparator | Cần duyệt phần tử theo tiêu chí sắp xếp |

Ví dụ cùng một dữ liệu:

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.TreeSet;
import java.util.List;

var source = List.of("C", "A", "B");

var hashSet = new HashSet<>(source);
var linkedHashSet = new LinkedHashSet<>(source);
var treeSet = new TreeSet<>(source);

System.out.println(linkedHashSet); // [C, A, B]
System.out.println(treeSet);       // [A, B, C]
System.out.println(hashSet);       // không có thứ tự được bảo đảm
```

Không nên dùng `HashSet` khi logic chương trình phụ thuộc vào thứ tự duyệt. Cũng không nên dùng `TreeSet` chỉ để giữ thứ tự chèn, vì `TreeSet` sắp xếp theo comparator hoặc thứ tự tự nhiên thay vì lịch sử thêm phần tử.

## 4. `LinkedHashSet` trong Java 21 và `SequencedSet`

Java 21 bổ sung hệ thống sequenced collections, trong đó `SequencedSet` mở rộng `Set` và cung cấp hợp đồng cho tập hợp có thứ tự encounter rõ ràng. `LinkedHashSet` triển khai `SequencedSet`, vì vậy có thể khai báo biến theo interface để dùng các thao tác đầu/cuối.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class SequencedSetDeclaration {
    public static void main(String[] args) {
        SequencedSet<String> names = new LinkedHashSet<>();

        names.add("An");
        names.add("Binh");
        names.add("Chi");

        System.out.println(names.getFirst()); // An
        System.out.println(names.getLast());  // Chi
    }
}
```

Khai báo bằng `SequencedSet` giúp code phụ thuộc vào hợp đồng hành vi có thứ tự thay vì phụ thuộc trực tiếp vào một implementation. Khi cần các chức năng riêng của `LinkedHashSet`, có thể khai báo kiểu cụ thể; còn khi chỉ cần các thao tác của sequenced set, interface là lựa chọn phù hợp.

Các phương thức quan trọng của `SequencedSet` gồm:

| Phương thức | Hành vi |
|---|---|
| `addFirst(e)` | Thêm `e` vào đầu; nếu đã tồn tại thì chuyển nó lên đầu |
| `addLast(e)` | Thêm `e` vào cuối; nếu đã tồn tại thì chuyển nó xuống cuối |
| `getFirst()` | Trả về phần tử đầu tiên |
| `getLast()` | Trả về phần tử cuối cùng |
| `removeFirst()` | Xóa và trả về phần tử đầu tiên |
| `removeLast()` | Xóa và trả về phần tử cuối cùng |
| `reversed()` | Trả về view có encounter order đảo ngược |

Các thao tác này có sẵn trên `LinkedHashSet` từ Java 21 và không cần bật preview feature.

## 5. Di chuyển phần tử bằng `addFirst()` và `addLast()`

Khác với `add()`, hai phương thức `addFirst()` và `addLast()` thể hiện rõ vị trí mong muốn trong encounter order. Nếu phần tử đã tồn tại, nó được chuyển đến đầu hoặc cuối tương ứng, không tạo bản sao.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class AddAtEndsDemo {
    public static void main(String[] args) {
        SequencedSet<String> names = new LinkedHashSet<>();
        names.add("An");
        names.add("Binh");
        names.add("Chi");
        names.add("Dung");

        names.addFirst("Chi");
        System.out.println(names); // [Chi, An, Binh, Dung]

        names.addLast("An");
        System.out.println(names); // [Chi, Binh, Dung, An]
    }
}
```

Sau `addFirst("Chi")`, `Chi` được đưa lên đầu. Sau `addLast("An")`, `An` được chuyển xuống cuối. Tính duy nhất của `Set` vẫn được giữ trong cả hai thao tác.

Nên dùng:

- `add()` khi muốn thêm phần tử mới theo thứ tự chèn thông thường.
- `addFirst()` khi phần tử cần được ưu tiên ở đầu encounter order.
- `addLast()` khi muốn đưa phần tử về cuối encounter order.

## 6. Đọc và xóa phần tử ở hai đầu

`getFirst()` và `getLast()` cho phép đọc trực tiếp hai đầu mà không cần duyệt toàn bộ set. `removeFirst()` và `removeLast()` vừa lấy vừa xóa phần tử ở vị trí tương ứng.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class ReadRemoveEndsDemo {
    public static void main(String[] args) {
        SequencedSet<String> queue = new LinkedHashSet<>();
        queue.add("Task-1");
        queue.add("Task-2");
        queue.add("Task-3");

        System.out.println(queue.getFirst()); // Task-1
        System.out.println(queue.getLast());  // Task-3

        String completed = queue.removeFirst();
        String deferred = queue.removeLast();

        System.out.println(completed); // Task-1
        System.out.println(deferred);  // Task-3
        System.out.println(queue);     // [Task-2]
    }
}
```

Nếu set rỗng, `getFirst()`, `getLast()`, `removeFirst()` và `removeLast()` ném `NoSuchElementException`. Khi dữ liệu có thể rỗng, hãy kiểm tra `isEmpty()` trước khi gọi hoặc thiết kế luồng xử lý ngoại lệ phù hợp.

```java
if (!queue.isEmpty()) {
    String first = queue.removeFirst();
    System.out.println(first);
}
```

Không nên giả định các phương thức này trả về `null` khi set rỗng; hợp đồng của chúng là ném ngoại lệ nếu không có phần tử ở vị trí được yêu cầu.

## 7. Duyệt theo thứ tự đảo ngược với `reversed()`

`reversed()` trả về một `SequencedSet` view có encounter order ngược với set gốc. View này được backing bởi set ban đầu: thay đổi qua view sẽ phản ánh lên set gốc và ngược lại.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class ReversedViewDemo {
    public static void main(String[] args) {
        SequencedSet<String> names = new LinkedHashSet<>();
        names.add("An");
        names.add("Binh");
        names.add("Chi");

        SequencedSet<String> reverseView = names.reversed();
        System.out.println(reverseView); // [Chi, Binh, An]

        reverseView.remove("Binh");
        System.out.println(names); // [An, Chi]
    }
}
```

`reversed()` không tạo một bản sao độc lập. Nếu chỉ cần duyệt theo chiều ngược, có thể dùng view trực tiếp. Nếu cần một set mới có thứ tự đảo ngược độc lập với set ban đầu, hãy tạo bản sao:

```java
var reversedCopy = new LinkedHashSet<>(names.reversed());
```

Sau khi tạo `reversedCopy`, việc thay đổi một set không làm thay đổi set còn lại. Tuy nhiên, các phần tử bên trong vẫn là cùng những object được tham chiếu; bản sao collection không tự sao chép sâu từng phần tử.

## 8. Thứ tự duyệt không làm thay đổi ngữ nghĩa bằng nhau của Set

Theo hợp đồng `Set`, hai set được xem là bằng nhau nếu chúng chứa cùng các phần tử, bất kể thứ tự duyệt. Vì vậy, hai `LinkedHashSet` có cùng phần tử nhưng thứ tự chèn khác nhau vẫn có thể bằng nhau theo `equals()`.

```java
import java.util.LinkedHashSet;
import java.util.List;

class SetEqualityDemo {
    public static void main(String[] args) {
        var first = new LinkedHashSet<>(List.of("A", "B", "C"));
        var second = new LinkedHashSet<>(List.of("C", "B", "A"));

        System.out.println(first);        // [A, B, C]
        System.out.println(second);       // [C, B, A]
        System.out.println(first.equals(second)); // true
    }
}
```

Thứ tự encounter ảnh hưởng đến cách duyệt, stream và biểu diễn dạng chuỗi, nhưng không trở thành một phần của phép so sánh `Set.equals()`. Nếu nghiệp vụ yêu cầu so sánh cả thứ tự, hãy so sánh hai danh sách được tạo từ encounter order, chẳng hạn `List.copyOf(first)` và `List.copyOf(second)`.

## 9. Chọn `LinkedHashSet` cho tình huống thực tế

Một trường hợp phổ biến là loại bỏ dữ liệu trùng lặp nhưng giữ lần xuất hiện đầu tiên, ví dụ danh sách mã được nhập từ nhiều nguồn:

```java
import java.util.LinkedHashSet;
import java.util.List;

class UniqueInEncounterOrder {
    static List<String> uniqueCodes(List<String> input) {
        return List.copyOf(new LinkedHashSet<>(input));
    }

    public static void main(String[] args) {
        var input = List.of("A12", "B08", "A12", "C31", "B08");
        System.out.println(uniqueCodes(input)); // [A12, B08, C31]
    }
}
```

`LinkedHashSet` loại bỏ lần xuất hiện lặp lại và giữ vị trí của lần xuất hiện đầu tiên. `List.copyOf` tạo một danh sách không thể sửa đổi từ encounter order đó. Đây là một cách hữu ích khi cần kết quả dạng list nhưng muốn khử trùng lặp theo thứ tự đầu vào.

Chọn `LinkedHashSet` khi thứ tự chèn là một phần của hành vi ứng dụng. Nếu thứ tự không quan trọng, `HashSet` có thể phù hợp hơn vì không cần duy trì liên kết thứ tự. Nếu cần thứ tự sắp xếp, dùng `TreeSet` hoặc sắp xếp ở bước riêng.

## 10. Lưu ý khi sử dụng

- **Tính duy nhất phụ thuộc vào `equals()` và `hashCode()`:** với object tự định nghĩa, cần triển khai hai phương thức này nhất quán để set nhận diện phần tử trùng đúng mong muốn.
- **Thay đổi field tham gia `hashCode()` khi object đang ở trong set là nguy hiểm:** set có thể không tìm hoặc loại bỏ được phần tử theo cách mong đợi. Nên dùng key có trạng thái ổn định trong thời gian lưu trong set.
- **`LinkedHashSet` không tự sắp xếp:** thứ tự của nó là encounter order, không phải thứ tự alphabet hay thứ tự theo giá trị.
- **`reversed()` là view có liên kết:** cần dùng bản sao nếu muốn dữ liệu độc lập.
- **Không tự đồng bộ hóa:** `LinkedHashSet` không phải collection thread-safe. Nếu nhiều thread cùng thay đổi, cần cơ chế đồng bộ phù hợp hoặc chọn cấu trúc dữ liệu concurrent đáp ứng đúng yêu cầu.
- **Không nhầm `add()` với `addFirst()`/`addLast()`:** thêm phần tử đã tồn tại bằng `add()` không đổi vị trí; hai phương thức đầu/cuối có thể di chuyển phần tử đã có.

## Kết luận

`LinkedHashSet` giữ tính duy nhất của `Set` đồng thời duy trì thứ tự chèn để việc duyệt có thể dự đoán. Trong Java 21, nó triển khai `SequencedSet`, cung cấp `addFirst()`, `addLast()`, `getFirst()`, `getLast()`, `removeFirst()`, `removeLast()` và `reversed()`. Hãy chọn `LinkedHashSet` khi encounter order có ý nghĩa, phân biệt thao tác thêm thông thường với di chuyển phần tử ở hai đầu, và nhớ rằng thứ tự duyệt không làm thay đổi quy tắc bằng nhau của `Set`.
