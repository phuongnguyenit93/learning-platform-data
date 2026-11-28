# Chọn `Collectors.toCollection()` khi cần kiểu collection và quyền sửa cụ thể

`Stream.toList()` phù hợp khi cần thu kết quả thành một danh sách không sửa đổi được. Nếu chương trình cần một loại collection cụ thể hoặc cần chỉnh sửa kết quả sau khi thu thập, hãy cân nhắc `Collectors.toCollection(...)`. Phương thức này cho phép cung cấp một `Supplier` tạo collection đích, chẳng hạn `ArrayList`, `LinkedHashSet`, `TreeSet` hoặc `ArrayDeque`.

Điểm quan trọng là chọn collection theo đúng ngữ nghĩa dữ liệu: có cần giữ phần tử trùng lặp không, có cần thứ tự chèn hay thứ tự sắp xếp không, có cần thao tác như hàng đợi hay không, và dữ liệu có thể chứa `null` không. `toCollection()` cho phép chỉ định kiểu đích; các đặc tính còn lại phụ thuộc vào collection mà bạn cung cấp.

## 1. `Collectors.toCollection()` hoạt động như thế nào?

Cú pháp tổng quát:

```java
stream.collect(Collectors.toCollection(collectionFactory));
```

`collectionFactory` là một `Supplier<C>` tạo collection đích. Collector sử dụng collection được tạo để tích lũy phần tử stream và trả về collection đó.

`Collectors.toCollection()` có từ Java 8 và vẫn là API chuẩn trong Java hiện đại. Nó đặc biệt hữu ích khi hợp đồng của chương trình cần một implementation cụ thể, thay vì chỉ cần một `List` hoặc `Set` bất kỳ.

`toCollection()` không tự biến collection thành mutable hay thread-safe. Các đặc tính này phụ thuộc vào lớp mà supplier tạo ra. Hãy cung cấp một collection rỗng có thể nhận phần tử và hỗ trợ việc kết hợp kết quả; các ví dụ trong bài dùng những implementation mutable tiêu chuẩn.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .collect(Collectors.toCollection(ArrayList::new));

names.add("Dung"); // Hợp lệ: kết quả là ArrayList mutable
```

Ở ví dụ này, `ArrayList::new` là factory. Mỗi lần supplier được gọi, nó tạo một `ArrayList` mới, rỗng. Collector thêm các phần tử vào collection trong quá trình thu thập.

Với `ArrayList`, chương trình có thể dựa vào các đặc tính đã biết của lớp này: giữ thứ tự phần tử, cho phép phần tử trùng lặp, cho phép `null`, hỗ trợ truy cập theo chỉ số và cho phép thay đổi cấu trúc. Nếu muốn các đặc tính khác, hãy cung cấp một loại collection khác.

## 2. Chọn collection theo yêu cầu dữ liệu

| Collection đích | Giữ trùng lặp? | Thứ tự khi duyệt | Cho phép `null`? | Khi nên chọn |
| --- | --- | --- | --- | --- |
| `ArrayList` | Có | Thứ tự chèn | Có | Cần `List` mutable, giữ mọi phần tử và truy cập theo chỉ số. |
| `LinkedList` | Có | Thứ tự chèn | Có | Cần `List` mutable đồng thời cần thao tác ở hai đầu qua `Deque`; chọn sau khi cân nhắc đặc tính hiệu năng thực tế. |
| `LinkedHashSet` | Không | Thứ tự chèn của các phần tử duy nhất | Có, tối đa một null | Cần loại bỏ trùng lặp nhưng vẫn giữ thứ tự gặp đầu tiên. |
| `TreeSet` | Không | Thứ tự theo natural order hoặc comparator | Phụ thuộc comparator; natural ordering không nhận null | Cần tập hợp phần tử duy nhất được sắp xếp. |
| `ArrayDeque` | Có | Thứ tự trong deque | Không | Cần cấu trúc hàng đợi hoặc ngăn xếp mutable, thao tác ở hai đầu. |

Đây là các đặc tính của từng collection, không phải những bảo đảm chung mà `toCollection()` tự thêm vào. Ví dụ, `toCollection(HashSet::new)` cũng tạo `Set` loại bỏ trùng lặp, nhưng không bảo đảm thứ tự duyệt ổn định.

## 3. Dùng `ArrayList` khi cần danh sách mutable

`ArrayList` là lựa chọn thông dụng khi kết quả cần giữ tất cả phần tử theo encounter order và được chỉnh sửa sau khi thu thập:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of(" An ", "Bình ", "Chi");

List<String> editableNames = source.stream()
    .map(String::trim)
    .collect(Collectors.toCollection(ArrayList::new));

editableNames.add("Dung");
editableNames.set(0, "Anh");
editableNames.remove("Bình");

System.out.println(editableNames); // [Anh, Chi, Dung]
```

Nếu đã thu kết quả bằng `Stream.toList()` và sau đó mới phát sinh nhu cầu chỉnh sửa, có thể sao chép sang `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;

List<String> readOnlyResult = List.of("An", "Bình", "Chi").stream().toList();
List<String> workingCopy = new ArrayList<>(readOnlyResult);

workingCopy.add("Dung");
```

Hai cách đều tạo ra `ArrayList` mutable. Chọn `toCollection(ArrayList::new)` khi muốn pipeline thu thập trực tiếp vào loại collection đích; chọn copy constructor khi đã có một collection và muốn tạo bản làm việc riêng.

## 4. Dùng `LinkedHashSet` khi cần loại bỏ trùng lặp nhưng giữ thứ tự gặp đầu tiên

`LinkedHashSet` loại bỏ phần tử trùng nhau theo `equals()`/`hashCode()` và giữ thứ tự chèn. Khi thu thập từ một stream có encounter order, các phần tử duy nhất được giữ theo thứ tự xuất hiện đầu tiên:

```java
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;

Set<String> uniqueNames = java.util.stream.Stream.of(
        "An", "Bình", "An", "Chi", "Bình")
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(uniqueNames); // [An, Bình, Chi]

uniqueNames.add("Dung"); // Hợp lệ
```

Khi phần tử xuất hiện nhiều lần, lần xuất hiện đầu tiên quyết định vị trí trong thứ tự duyệt; các lần sau không tạo thêm phần tử. Điều này hữu ích khi tạo danh sách mã định danh hoặc nhãn duy nhất mà giao diện vẫn cần hiển thị theo thứ tự nguồn.

`Set` sử dụng `equals()` và `hashCode()` để xác định phần tử trùng. Với object tự định nghĩa, hãy triển khai hai phương thức này nhất quán nếu muốn loại bỏ trùng lặp theo giá trị nghiệp vụ.

## 5. Dùng `TreeSet` khi cần kết quả duy nhất và được sắp xếp

`TreeSet` duy trì phần tử theo natural ordering hoặc comparator. Nó phù hợp khi kết quả cần vừa loại bỏ phần tử được xem là trùng theo thứ tự so sánh, vừa được duyệt theo thứ tự sắp xếp:

```java
import java.util.NavigableSet;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

NavigableSet<Integer> sortedScores = Stream.of(80, 95, 70, 95, 85)
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(sortedScores); // [70, 80, 85, 95]
System.out.println(sortedScores.first()); // 70
System.out.println(sortedScores.last());  // 95

sortedScores.add(100); // Hợp lệ
```

Nếu cần thứ tự riêng, tạo `TreeSet` với comparator trong supplier:

```java
import java.util.Comparator;
import java.util.NavigableSet;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

NavigableSet<String> reverseNames = Stream.of("An", "Chi", "Bình")
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(Comparator.reverseOrder())
    ));

System.out.println(reverseNames); // [Chi, Bình, An]
```

Với `TreeSet`, comparator không chỉ quyết định thứ tự; hai phần tử mà comparator trả về `0` được xem là cùng một phần tử trong set. Vì thế, hãy bảo đảm comparator phù hợp với quy tắc định danh phần tử của nghiệp vụ.

Natural ordering của `TreeSet` không nhận `null`. Comparator tùy chỉnh chỉ có thể xử lý null nếu được thiết kế rõ ràng, ví dụ `Comparator.nullsFirst(...)`:

```java
import java.util.Comparator;
import java.util.TreeSet;

TreeSet<String> names = new TreeSet<>(
    Comparator.nullsFirst(Comparator.naturalOrder())
);

names.add("Bình");
names.add(null);
names.add("An");

System.out.println(names); // [null, An, Bình]
```

## 6. Dùng `ArrayDeque` khi kết quả sẽ được xử lý như hàng đợi hoặc ngăn xếp

Nếu dữ liệu sau khi thu thập sẽ được lấy ra từ đầu hoặc cuối, `ArrayDeque` biểu diễn mục đích đó rõ hơn một `List`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Deque<String> tasks = Stream.of("Đọc file", "Xử lý", "Ghi kết quả")
    .collect(Collectors.toCollection(ArrayDeque::new));

tasks.addLast("Gửi thông báo");
String nextTask = tasks.removeFirst();

System.out.println(nextTask); // Đọc file
System.out.println(tasks); // [Xử lý, Ghi kết quả, Gửi thông báo]
```

`ArrayDeque` hỗ trợ thêm và lấy phần tử ở hai đầu, nhưng không hỗ trợ truy cập theo chỉ số như `List`. Collection này cũng không cho phép `null`. Nếu stream có thể phát ra null, hãy xác thực hoặc lọc dữ liệu trước khi thu vào `ArrayDeque`.

## 7. Supplier phải tạo collection mới và rỗng

Supplier được truyền cho `toCollection()` phải tạo collection mới cho mỗi lần gọi. Điều này đặc biệt quan trọng khi stream được xử lý song song: framework có thể tạo nhiều collection trung gian rồi kết hợp chúng.

Đúng:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> source = IntStream.range(0, 1_000).boxed().toList();

List<Integer> values = source.parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));
```

Không dùng một collection dùng chung làm kết quả của supplier:

```java
// Không làm như sau:
// List<String> shared = new ArrayList<>();
// source.parallelStream()
//     .collect(Collectors.toCollection(() -> shared));
```

Nếu supplier luôn trả về cùng một object, các nhánh tích lũy có thể ghi vào cùng collection, phá vỡ yêu cầu về các container độc lập của quá trình reduction. Với parallel stream, hãy dùng constructor reference hoặc supplier tạo một instance mới mỗi lần.

Collection đích cũng cần hỗ trợ các thao tác mà collector dùng để tích lũy và kết hợp phần tử, bao gồm thêm phần tử và hợp nhất nội dung collection. Tránh cung cấp một collection không sửa đổi được hoặc collection có giới hạn không phù hợp với lượng dữ liệu.

## 8. Parallel stream không làm collection kết quả tự thread-safe

Collector có thể sử dụng các collection trung gian riêng trong quá trình xử lý song song rồi kết hợp chúng. Điều đó không có nghĩa collection kết quả sau khi thu thập tự trở thành thread-safe.

Ví dụ, `ArrayList` vẫn là collection mutable không đồng bộ hóa. Nếu chia sẻ kết quả cho nhiều thread và có ghi đồng thời, ứng dụng phải tự thiết kế cơ chế đồng bộ hoặc dùng collection phù hợp với yêu cầu concurrency.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> values = IntStream.range(0, 1_000)
    .parallel()
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));

// Thu thập hoàn tất; values là ArrayList thông thường.
// Nếu chia sẻ values và nhiều thread cùng sửa, cần đồng bộ hóa phù hợp.
```

Chỉ chọn collection concurrent khi ứng dụng thực sự cần nhiều thread thao tác đồng thời sau khi thu thập. Không cần dùng collection concurrent chỉ vì pipeline đầu vào là parallel stream.

## 9. So sánh với các collector khác

| Collector | Collection đích | Khi nên dùng |
| --- | --- | --- |
| `Collectors.toList()` | Một `List` không xác định lớp triển khai và mutability | Khi chỉ cần hợp đồng `List` mà không phụ thuộc đặc tính bổ sung. |
| `Collectors.toSet()` | Một `Set` không xác định lớp triển khai | Khi chỉ cần loại bỏ trùng lặp, không cần bảo đảm loại set cụ thể. |
| `Collectors.toCollection(ArrayList::new)` | `ArrayList` | Khi cần list mutable, giữ trùng lặp và thứ tự chèn. |
| `Collectors.toCollection(LinkedHashSet::new)` | `LinkedHashSet` | Khi cần duy nhất và giữ thứ tự chèn. |
| `Collectors.toCollection(TreeSet::new)` | `TreeSet` | Khi cần duy nhất và được sắp xếp. |
| `Collectors.toCollection(ArrayDeque::new)` | `ArrayDeque` | Khi cần thao tác queue/deque và không có null. |

`toCollection()` hữu ích khi yêu cầu của chương trình gắn với đặc tính của một implementation cụ thể. Nếu không cần các đặc tính đó, chọn collector đơn giản hơn sẽ giúp ý định của code dễ đọc.

## 10. Checklist trước khi chọn collection đích

- Cần giữ phần tử trùng lặp hay loại bỏ chúng?
- Cần giữ encounter order, thứ tự chèn hay thứ tự sắp xếp?
- Cần truy cập theo chỉ số, thao tác ở hai đầu hay tra cứu theo key?
- Phần tử có thể là `null` không? `ArrayDeque` và `TreeSet` natural ordering không nhận null.
- Kết quả có cần mutable sau khi thu thập không?
- Supplier có tạo collection mới, rỗng trong mỗi lần gọi không?
- Collection có hỗ trợ việc tích lũy và kết hợp dữ liệu của collector không?
- Nếu chia sẻ kết quả giữa nhiều thread, đã xử lý thread-safety của collection chưa?

Hãy dùng `Stream.toList()` khi cần một danh sách không sửa đổi được. Khi cần kiểm soát loại collection và hành vi sửa đổi, dùng `Collectors.toCollection(...)` với factory phù hợp. Cách chọn collection theo semantics giúp tránh phụ thuộc vào implementation không được bảo đảm và làm rõ ý định của pipeline.

## Tài liệu tham khảo

- [Collectors.toCollection() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier))
- [Collectors.toCollection() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier))
- [Supplier – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html)
- [Collection – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html)
- [ArrayList – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html)
- [LinkedHashSet – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LinkedHashSet.html)
- [TreeSet – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html)
- [ArrayDeque – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayDeque.html)
