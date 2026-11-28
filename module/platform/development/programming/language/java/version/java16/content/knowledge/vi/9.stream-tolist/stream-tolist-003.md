# Hợp đồng unmodifiable và `UnsupportedOperationException` khi sửa danh sách

`Stream.toList()` có từ Java 16 và trả về một `List` không sửa đổi được (*unmodifiable list*). Theo hợp đồng API, mọi lời gọi phương thức thay đổi danh sách này đều ném `UnsupportedOperationException`. Quy tắc đó áp dụng cả khi cố thêm, xóa, thay thế hoặc sắp xếp phần tử.

Điều này giúp thể hiện rõ ý định của chương trình: pipeline tạo ra một kết quả danh sách để đọc và chuyển giao. Nếu bên nhận cần chỉnh sửa danh sách, hãy tạo một collection mutable có chủ đích, chẳng hạn `new ArrayList<>(result)` hoặc `Collectors.toCollection(ArrayList::new)`.

## 1. Hợp đồng của `Stream.toList()`

Ví dụ cơ bản:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .filter(name -> !name.isBlank())
    .toList();

System.out.println(names); // [An, Bình, Chi]
```

Bạn có thể đọc danh sách bằng các thao tác như `size()`, `get()`, `contains()`, duyệt bằng `for` hoặc `forEach()`, và tiếp tục tạo stream từ danh sách đó. Tuy nhiên, không thể dùng danh sách này để thay đổi tập hợp phần tử.

Javadoc của `Stream.toList()` quy định rõ: danh sách trả về là unmodifiable và lời gọi bất kỳ mutator method nào luôn gây ra `UnsupportedOperationException`. API không cam kết lớp triển khai cụ thể hoặc khả năng tuần tự hóa của danh sách. Vì vậy, hãy khai báo và sử dụng nó qua interface `List<T>`:

```java
import java.util.List;

List<String> source = List.of("An", "", "Bình");

List<String> result = source.stream()
    .filter(String::isBlank)
    .toList();
```

Không ép kiểu `result` thành `ArrayList`, cũng không dựa vào tên lớp nội bộ mà debugger hiển thị. Lớp triển khai là chi tiết do JDK quyết định.

Javadoc hiện hành còn cho biết instance trả về có thể là *value-based*. Không dựa vào identity của danh sách bằng `==`, `System.identityHashCode()` hoặc dùng chính danh sách làm monitor cho `synchronized`; các thao tác phụ thuộc identity không được bảo đảm đáng tin cậy.

## 2. Những thao tác nào ném `UnsupportedOperationException`?

Các nhóm thao tác sau đều làm thay đổi danh sách nên không được hỗ trợ:

| Nhóm thao tác | Ví dụ | Mục đích |
| --- | --- | --- |
| Thêm phần tử | `add(e)`, `add(index, e)`, `addAll(...)` | Thêm một hoặc nhiều phần tử. |
| Xóa phần tử | `remove(e)`, `remove(index)`, `removeAll(...)`, `retainAll(...)`, `clear()` | Xóa phần tử hoặc làm rỗng danh sách. |
| Thay thế phần tử | `set(index, e)`, `replaceAll(...)` | Ghi giá trị khác vào vị trí hiện có. |
| Sắp xếp tại chỗ | `sort(comparator)` | Thay đổi thứ tự phần tử ngay trên danh sách. |
| Xóa theo điều kiện | `removeIf(predicate)` | Xóa các phần tử thỏa điều kiện. |

Ví dụ, các lệnh dưới đây đều không hợp lệ với danh sách lấy từ `toList()`:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream().toList();

names.add("Dung");                 // UnsupportedOperationException
names.remove("An");                // UnsupportedOperationException
names.set(0, "Anh");               // UnsupportedOperationException
names.replaceAll(String::toUpperCase); // UnsupportedOperationException
names.sort(String::compareTo);      // UnsupportedOperationException
names.clear();                     // UnsupportedOperationException
```

Các lệnh trong ví dụ được minh họa riêng lẻ; thực tế chương trình dừng tại lời gọi đầu tiên ném exception nếu không xử lý exception đó.

Hợp đồng `Stream.toList()` nói rõ mutator method luôn ném exception. Do đó, không nên dựa vào việc một lời gọi có thể không làm thay đổi dữ liệu để mong nó thành công. Ví dụ, `removeIf(...)` với predicate không khớp phần tử nào vẫn là một mutator method và không phải cách kiểm tra danh sách có thể sửa đổi hay không.

## 3. Không thể sửa danh sách qua iterator hoặc view

Danh sách không trở nên mutable khi truy cập thông qua một đối tượng trung gian. Iterator của danh sách không hỗ trợ xóa phần tử; `ListIterator` cũng không hỗ trợ thêm hoặc thay thế phần tử:

```java
import java.util.List;
import java.util.ListIterator;

List<String> names = List.of("An", "Bình", "Chi").stream().toList();

var iterator = names.iterator();
iterator.next();
iterator.remove(); // UnsupportedOperationException

ListIterator<String> listIterator = names.listIterator();
listIterator.next();
listIterator.set("Anh"); // UnsupportedOperationException
listIterator.add("Dung"); // UnsupportedOperationException
```

Tương tự, `subList(from, to)` tạo một view trên một đoạn của danh sách. Nếu danh sách gốc không sửa đổi được, view này cũng không cho phép thay đổi phần tử:

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi", "Dung").stream().toList();
List<String> firstTwo = names.subList(0, 2);

System.out.println(firstTwo); // [An, Bình]
firstTwo.clear();             // UnsupportedOperationException
```

Đừng tìm cách sửa danh sách bằng iterator, `subList`, hoặc một API khác nhận `List` làm đầu vào. Những cách đó vẫn thao tác trên cùng hợp đồng không sửa đổi.

## 4. Unmodifiable không đồng nghĩa với immutable sâu

`unmodifiable` mô tả khả năng thay đổi cấu trúc danh sách: không thể thêm, xóa hoặc thay thế phần tử. Nó không tự làm cho từng object nằm trong danh sách trở nên bất biến.

Ví dụ, `StringBuilder` có thể thay đổi trạng thái của chính nó. Danh sách không cho phép thay phần tử, nhưng vẫn cho phép gọi phương thức trên object mà `get()` trả về:

```java
import java.util.List;
import java.util.stream.Stream;

StringBuilder message = new StringBuilder("Xin chào");
List<StringBuilder> messages = Stream.of(message).toList();

messages.get(0).append(" Java"); // Hợp lệ: sửa object StringBuilder
System.out.println(messages.get(0)); // Xin chào Java

messages.set(0, new StringBuilder("Khác")); // UnsupportedOperationException
```

Hai thao tác có bản chất khác nhau:

- `messages.get(0).append(...)` gọi phương thức trên object đang được tham chiếu. Cấu trúc danh sách không đổi.
- `messages.set(0, ...)` thay object được lưu tại vị trí số 0. Đây là thao tác sửa danh sách nên bị từ chối.

Nếu yêu cầu nghiệp vụ cần dữ liệu bất biến sâu, chỉ dùng `toList()` là chưa đủ. Hãy thiết kế phần tử theo hướng immutable, hoặc tạo bản sao độc lập của từng phần tử bằng logic sao chép phù hợp với kiểu dữ liệu.

## 5. Phân biệt unmodifiable list, unmodifiable view và immutable object

Ba khái niệm này liên quan nhưng không giống nhau:

| Khái niệm | Có thể sửa cấu trúc qua đối tượng đó? | Dữ liệu có thể thay đổi từ nơi khác? |
| --- | --- | --- |
| Danh sách từ `Stream.toList()` | Không | Trạng thái của object phần tử mutable vẫn có thể thay đổi. |
| View từ `Collections.unmodifiableList(source)` | Không | Có. Nếu mã khác sửa `source`, view phản ánh thay đổi đó. |
| Danh sách mutable như `ArrayList` | Có | Có thể sửa qua chính danh sách hoặc tham chiếu khác tới phần tử. |
| Immutable object / cấu trúc immutable sâu | Không có trạng thái quan sát được để sửa | Không, nếu toàn bộ trạng thái bên trong cũng bất biến. |

Ví dụ về unmodifiable view:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("An", "Bình"));
List<String> view = Collections.unmodifiableList(source);

// view.add("Chi"); // UnsupportedOperationException
source.add("Chi");  // Hợp lệ: source vẫn mutable

System.out.println(view); // [An, Bình, Chi]
```

View chỉ chặn việc sửa thông qua `view`; nó không đóng băng collection gốc. `Stream.toList()` là terminal operation thu các phần tử stream thành kết quả danh sách không sửa đổi được, nên không nên đánh đồng hợp đồng này với một wrapper view được tạo quanh một collection mutable mà mã khác vẫn giữ tham chiếu.

## 6. Khi cần chỉnh sửa, hãy tạo danh sách mutable

Nếu cần thêm, xóa, thay thế hoặc sắp xếp kết quả sau khi thu thập, hãy chọn một trong hai cách sau.

**Cách 1: Thu thập trực tiếp thành `ArrayList`.** Dùng `Collectors.toCollection(ArrayList::new)` khi muốn pipeline tạo ra collection mutable ngay từ đầu:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> editableNames = List.of("An", "Bình", "Chi").stream()
    .filter(name -> !name.isBlank())
    .collect(Collectors.toCollection(ArrayList::new));

editableNames.add("Dung"); // Hợp lệ
editableNames.set(0, "Anh"); // Hợp lệ
```

**Cách 2: Sao chép kết quả đã thu thập.** Dùng constructor `ArrayList(Collection)` khi muốn giữ kết quả ban đầu không sửa đổi được và tạo một bản làm việc riêng:

```java
import java.util.ArrayList;
import java.util.List;

List<String> result = List.of("An", "Bình", "Chi").stream().toList();
List<String> editableCopy = new ArrayList<>(result);

editableCopy.remove("Bình"); // Hợp lệ
editableCopy.add("Dung");    // Hợp lệ

System.out.println(result);       // [An, Bình, Chi]
System.out.println(editableCopy); // [An, Chi, Dung]
```

Đây là bản sao nông (*shallow copy*): danh sách mới có cấu trúc riêng, nhưng nếu phần tử là object mutable thì hai danh sách vẫn có thể chứa tham chiếu tới cùng object. Nếu cần bản sao sâu, phải sao chép từng phần tử theo quy tắc của kiểu dữ liệu.

Không chọn `Collectors.toList()` chỉ vì mong nhận được `ArrayList`. Hợp đồng của collector này không bảo đảm kiểu triển khai hoặc khả năng sửa đổi. Khi cần mutable, `Collectors.toCollection(ArrayList::new)` diễn đạt yêu cầu rõ ràng hơn.

## 7. `UnsupportedOperationException` nên được xử lý thế nào?

`UnsupportedOperationException` là unchecked exception, thuộc nhóm `RuntimeException`. Khi exception xuất hiện tại một thao tác sửa danh sách từ `toList()`, hãy kiểm tra lại yêu cầu dữ liệu và cách tạo collection.

- Nếu kết quả chỉ để đọc, giữ nguyên danh sách và bỏ lời gọi sửa đổi.
- Nếu cần sửa kết quả, tạo `ArrayList` mutable trước khi sửa.
- Nếu API nhận `List<T>` từ nơi khác, đọc hợp đồng của API đó; kiểu tham chiếu `List<T>` không tự nói lên danh sách có mutable hay không.
- Không dùng `try/catch (UnsupportedOperationException)` để dò khả năng sửa đổi rồi mới quyết định luồng xử lý. Hãy xác định loại collection ngay tại nơi tạo ra nó.

Ví dụ, một phương thức có thể nói rõ quyền sở hữu và khả năng chỉnh sửa trong tên biến hoặc tài liệu API:

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = List.of("An", "Bình");
List<String> readOnlyResult = source.stream().toList();
List<String> workingCopy = new ArrayList<>(readOnlyResult);

System.out.println(readOnlyResult);
workingCopy.add("Chi");
System.out.println(workingCopy);
```

Hai biến có cùng interface `List<String>`, nhưng hợp đồng sử dụng khác nhau được thể hiện rõ qua cách khởi tạo.

## 8. Ghi nhớ khi sử dụng trong Java hiện đại

- `Stream.toList()` có từ Java 16 và là terminal operation.
- Danh sách trả về không sửa đổi được; mọi mutator method đều ném `UnsupportedOperationException`.
- Các thao tác đọc vẫn dùng bình thường.
- Iterator, `ListIterator` và `subList` không mở ra con đường sửa đổi khác.
- Trạng thái của object mutable bên trong vẫn có thể thay đổi; unmodifiable không phải immutable sâu.
- Không dựa vào lớp triển khai, khả năng tuần tự hóa hoặc identity của danh sách trả về.
- Dùng `ArrayList` hoặc `Collectors.toCollection(...)` nếu nghiệp vụ cần collection mutable.

Hãy chọn `Stream.toList()` khi muốn chuyển kết quả pipeline thành danh sách không sửa đổi được. Nếu cần thay đổi tập hợp phần tử, hãy thể hiện rõ điều đó bằng một collection mutable. Cách chọn collection phù hợp giúp hợp đồng giữa nơi tạo dữ liệu và nơi sử dụng dữ liệu dễ hiểu, dễ bảo trì.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collection – Unmodifiable Collections, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html)
- [Collectors.toCollection() và Collectors.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Collections.unmodifiableList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))
