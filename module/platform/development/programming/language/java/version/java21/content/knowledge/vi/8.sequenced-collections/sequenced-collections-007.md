# Ảnh hưởng của reversed đến iterator, stream và thao tác hai đầu

Trong Java 21, `SequencedCollection.reversed()` trả về một **view có encounter order ngược lại** với collection gốc. View này được backing bởi collection ban đầu: thay đổi nhìn thấy qua view cũng phản ánh vào collection gốc và ngược lại. Vì vậy, `reversed()` rất hữu ích khi cần duyệt hoặc thao tác từ cuối về đầu mà vẫn giữ một nguồn dữ liệu chung.

Ảnh hưởng của view ngược thể hiện rõ ở ba nơi: iterator đi theo thứ tự mới, stream nhận encounter order mới, và các thao tác ở hai đầu được ánh xạ sang đầu đối diện của collection gốc. Đây là API chuẩn của Java 21 thuộc [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431).

## 1. `reversed()` tạo view, không đảo dữ liệu gốc

`SequencedCollection<E>` định nghĩa phương thức:

```java
SequencedCollection<E> reversed();
```

Với `List`, phương thức được override với kiểu trả về `List<E>`; với `SequencedSet`, kiểu trả về là `SequencedSet<E>`. View trả về có encounter order đối lập với collection gốc.

```java
import java.util.ArrayList;
import java.util.List;

List<String> tasks = new ArrayList<>(List.of("compile", "test", "package"));
List<String> reverseView = tasks.reversed();

System.out.println(tasks);       // [compile, test, package]
System.out.println(reverseView); // [package, test, compile]
```

Collection gốc vẫn có thứ tự `compile`, `test`, `package`. Chỉ có cách nhìn qua `reverseView` là ngược lại. `reversed()` không yêu cầu tạo một collection độc lập chứa bản sao các phần tử.

View được backing bởi collection gốc:

```java
reverseView.addFirst("deploy");

System.out.println(reverseView); // [deploy, package, test, compile]
System.out.println(tasks);       // [compile, test, package, deploy]
```

Thay đổi qua view làm thay đổi collection gốc. Tương tự, thay đổi collection gốc sẽ được phản ánh khi đọc view. Gọi `reversed()` trên view ngược trả về view theo hướng ban đầu, theo hợp đồng của API.

Không nên nhầm view với một bản sao đã đảo. Nếu cần kết quả độc lập để xử lý hoặc lưu trữ, hãy tạo collection mới từ view:

```java
List<String> reversedCopy = new ArrayList<>(tasks.reversed());
```

`reversedCopy` là collection riêng. Các thay đổi sau đó trên `tasks` hoặc view của nó không tự động cập nhật bản sao này.

## 2. Ảnh hưởng đến `iterator()` và vòng lặp

Iterator lấy từ reverse view duyệt theo encounter order của view, tức là từ phần tử cuối của collection gốc đến phần tử đầu:

```java
List<String> tasks = new ArrayList<>(List.of("compile", "test", "package"));

for (String task : tasks.reversed()) {
    System.out.println(task);
}
```

Kết quả:

```text
package
test
compile
```

Vòng lặp `for-each` sử dụng iterator của biểu thức được duyệt. Vì biểu thức là reverse view, vòng lặp tự nhận thứ tự ngược mà không cần tính index hoặc thay đổi thứ tự của danh sách ban đầu.

### Iterator và thao tác xóa

Nếu iterator của collection hỗ trợ `remove()`, iterator lấy từ reverse view cũng có thể xóa phần tử hiện tại khỏi backing collection theo hợp đồng của implementation:

```java
List<String> tasks = new ArrayList<>(List.of("compile", "test", "package"));

var iterator = tasks.reversed().iterator();
while (iterator.hasNext()) {
    String task = iterator.next();
    if (task.equals("test")) {
        iterator.remove();
    }
}

System.out.println(tasks); // [compile, package]
```

Phần tử `test` bị xóa khỏi collection gốc vì reverse view được backing bởi `tasks`. Việc gọi `remove()` vẫn phụ thuộc khả năng sửa đổi của collection; iterator trên collection không hỗ trợ xóa có thể ném `UnsupportedOperationException`.

Không nên sửa cấu trúc collection gốc bằng một đường truy cập khác trong lúc iterator của reverse view đang hoạt động. Với các implementation fail-fast, thay đổi cấu trúc bên ngoài iterator thường được phát hiện bằng `ConcurrentModificationException`; tuy nhiên fail-fast chỉ là cơ chế phát hiện lỗi ở mức best-effort, không phải bảo đảm đồng bộ hay bảo đảm phát hiện mọi thay đổi.

### `ListIterator` trên reverse view

Vì `List.reversed()` trả về một `List`, có thể lấy `ListIterator` trên view đó. Chỉ số và hướng di chuyển được hiểu theo danh sách ngược:

```java
List<String> tasks = new ArrayList<>(List.of("compile", "test", "package"));
List<String> reverseView = tasks.reversed();

var iterator = reverseView.listIterator();
System.out.println(iterator.next()); // package
System.out.println(iterator.next()); // test
System.out.println(iterator.previous()); // test
```

Iterator bắt đầu trước phần tử đầu tiên của reverse view. Do đó, `next()` đầu tiên trả về phần tử cuối của danh sách gốc. `previous()` di chuyển ngược trong thứ tự của view, nghĩa là đi theo hướng từ đầu đến cuối của collection gốc.

## 3. Ảnh hưởng đến `stream()` và encounter order

Stream tạo từ reverse view nhận encounter order của view. Với một collection có thứ tự, `reversed().stream()` xử lý các phần tử theo thứ tự ngược với stream tạo từ collection gốc:

```java
List<String> tasks = new ArrayList<>(List.of("compile", "test", "package"));

List<String> result = tasks.reversed()
        .stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [PACKAGE, TEST, COMPILE]
```

Các thao tác phụ thuộc encounter order cũng tính từ đầu của reverse view:

```java
String first = tasks.reversed().stream().findFirst().orElse("empty");
List<String> firstTwo = tasks.reversed().stream().limit(2).toList();
List<String> afterFirst = tasks.reversed().stream().skip(1).toList();
```

Với dữ liệu ban đầu là `[compile, test, package]`:

- `findFirst()` trả về `package`, tức phần tử cuối của collection gốc.
- `limit(2)` lấy `package` và `test`.
- `skip(1)` bỏ `package`, sau đó còn `test` và `compile`.

`findAny()` không có cam kết chọn phần tử đầu tiên của encounter order; không dùng nó khi cần phần tử cuối của collection gốc. Nếu yêu cầu phần tử đầu theo hướng ngược, dùng `findFirst()` trên reverse view.

### Stream tuần tự và song song

Stream từ reverse view vẫn là ordered stream nếu nguồn có encounter order. Với stream tuần tự, các thao tác có thứ tự làm việc theo encounter order này. Với parallel stream, nếu cần hành động quan sát được theo đúng thứ tự ngược, hãy dùng `forEachOrdered()`:

```java
tasks.reversed()
        .parallelStream()
        .forEachOrdered(System.out::println);
```

`forEach()` trên parallel stream không bảo đảm thực hiện action theo encounter order. Nếu thứ tự quan trọng, không thay `forEachOrdered()` bằng `forEach()`.

Các thao tác như `sorted()` có thể tạo encounter order mới theo comparator; `unordered()` loại bỏ ràng buộc encounter order. Sau các thao tác này, không nên giả định kết quả vẫn giữ thứ tự đảo ban đầu. `toList()` tạo một danh sách kết quả theo encounter order của stream; danh sách kết quả đó độc lập với reverse view và không sửa đổi được.

Stream không phải bản sao dữ liệu được tạo ngay tại lúc gọi `stream()`. Stream pipeline được thực thi khi có terminal operation. Tránh thay đổi collection gốc hoặc reverse view trong khi pipeline đang được thực hiện; đây là can thiệp vào nguồn dữ liệu và kết quả có thể không xác định theo hợp đồng của stream.

## 4. Ánh xạ các thao tác hai đầu

Trên reverse view, khái niệm đầu và cuối được đảo so với collection gốc. Vì vậy, thao tác tại đầu của view tương ứng với thao tác tại cuối của collection gốc, và ngược lại.

Giả sử collection gốc có encounter order:

```text
original:    [A, B, C]
reversed:    [C, B, A]
```

Các phương thức hai đầu được ánh xạ như sau:

| Thao tác trên reverse view | Tương ứng trên collection gốc | Ý nghĩa |
| --- | --- | --- |
| `getFirst()` | `getLast()` | Lấy phần tử cuối của gốc. |
| `getLast()` | `getFirst()` | Lấy phần tử đầu của gốc. |
| `addFirst(x)` | `addLast(x)` | Thêm `x` vào cuối gốc. |
| `addLast(x)` | `addFirst(x)` | Thêm `x` vào đầu gốc. |
| `removeFirst()` | `removeLast()` | Xóa phần tử cuối của gốc. |
| `removeLast()` | `removeFirst()` | Xóa phần tử đầu của gốc. |

Ví dụ với `List`:

```java
List<String> original = new ArrayList<>(List.of("A", "B", "C"));
List<String> reversed = original.reversed();

System.out.println(reversed.getFirst()); // C
System.out.println(reversed.getLast());  // A

reversed.addFirst("X");
System.out.println(original); // [A, B, C, X]

reversed.addLast("Y");
System.out.println(original); // [Y, A, B, C, X]

System.out.println(reversed.removeFirst()); // X
System.out.println(original);                // [Y, A, B, C]

System.out.println(reversed.removeLast()); // Y
System.out.println(original);               // [A, B, C]
```

Ánh xạ này giúp viết thuật toán theo góc nhìn đầu/cuối mà không phải tự quy đổi index. Hãy nhớ rằng `addFirst` và `addLast` là các thao tác tùy chọn theo implementation; nếu collection không hỗ trợ chèn tại vị trí được yêu cầu, chúng có thể ném `UnsupportedOperationException`. Chẳng hạn, collection có thứ tự được quyết định bởi comparator có thể không cho phép chèn tùy ý vào đầu hoặc cuối.

Các thao tác lấy và xóa ở hai đầu cũng có quy tắc với collection rỗng: `getFirst()`, `getLast()`, `removeFirst()` và `removeLast()` ném `NoSuchElementException` khi không có phần tử. Nếu collection có thể rỗng, kiểm tra `isEmpty()` trước khi gọi hoặc chọn cách xử lý phù hợp với hợp đồng của ứng dụng.

## 5. Ảnh hưởng với `SequencedSet`

`SequencedSet` kết hợp ngữ nghĩa của `Set` với encounter order có thể truy cập từ cả hai đầu. `reversed()` trả về một `SequencedSet` view có thứ tự ngược, vẫn giữ tính duy nhất của phần tử.

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

SequencedSet<String> steps = new LinkedHashSet<>();
steps.add("compile");
steps.add("test");
steps.add("package");

SequencedSet<String> reverseSteps = steps.reversed();
System.out.println(reverseSteps); // [package, test, compile]
```

Iterator và stream của `reverseSteps` duyệt theo thứ tự `package`, `test`, `compile`. Các thao tác `getFirst()`/`getLast()` và `removeFirst()`/`removeLast()` cũng đổi đầu tương ứng như với `SequencedCollection`.

`addFirst()` và `addLast()` vẫn tuân thủ quy tắc duy nhất của `Set`: nếu phần tử đã có, nó được chuyển đến vị trí đầu hoặc cuối tương ứng thay vì được thêm lần thứ hai. Khả năng hỗ trợ chèn tại đầu/cuối phụ thuộc implementation. Ví dụ `LinkedHashSet` hỗ trợ các thao tác này; `TreeSet` sắp xếp phần tử theo comparator nên không hỗ trợ định vị tùy ý và ném `UnsupportedOperationException` khi gọi `addFirst()` hoặc `addLast()`.

## 6. Ảnh hưởng với `SequencedMap`

`SequencedMap` không phải `Collection`, vì vậy không gọi trực tiếp `stream()` trên map. Tuy nhiên, `SequencedMap.reversed()` cũng tạo reverse-ordered view. Các view có thứ tự của map như `sequencedKeySet()`, `sequencedValues()` và `sequencedEntrySet()` có thể được duyệt hoặc stream theo thứ tự ngược:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 8);
scores.put("Binh", 9);
scores.put("Chi", 10);

SequencedMap<String, Integer> reverseScores = scores.reversed();

System.out.println(reverseScores.sequencedKeySet()); // [Chi, Binh, An]
reverseScores.sequencedEntrySet().stream()
        .forEachOrdered(System.out::println);
```

View ngược của map được backing bởi map gốc, nên thay đổi map qua view phản ánh vào map gốc. Các thao tác đầu/cuối của map cũng đổi phía tương ứng: `firstEntry()` trên view ngược tương ứng entry cuối của map gốc; `putFirst()` trên view ngược định vị entry ở cuối map gốc. Các thao tác map cụ thể còn tuân theo quy tắc khóa và implementation của map.

## 7. Giới hạn sửa đổi và an toàn khi duyệt

`reversed()` cung cấp một góc nhìn khác về cùng dữ liệu. Nó không làm cho collection mutable trở thành immutable hoặc ngược lại:

- Nếu collection gốc cho phép sửa đổi và thao tác tương ứng được hỗ trợ, reverse view có thể phản ánh thay đổi đó.
- Nếu collection gốc không sửa đổi được, thao tác sửa qua reverse view cũng có thể ném `UnsupportedOperationException`.
- Nếu một thao tác cụ thể không được implementation hỗ trợ, không giả định rằng mọi thao tác hai đầu đều hoạt động chỉ vì `reversed()` trả về view.
- Không sửa cấu trúc backing collection từ một luồng hoặc đường truy cập khác trong lúc đang duyệt view, trừ khi implementation có hợp đồng đồng thời rõ ràng.

Nếu cần một kết quả ổn định để xử lý lâu dài, tạo bản sao rõ ràng:

```java
List<String> snapshot = List.copyOf(tasks.reversed());
```

`List.copyOf()` tạo danh sách không sửa đổi chứa các phần tử theo thứ tự encounter tại thời điểm tạo bản sao; nó không còn là view liên kết với `tasks` và sẽ ném `NullPointerException` nếu nguồn có phần tử `null`. Nếu cần bản sao mutable hoặc cần giữ phần tử `null`, dùng `new ArrayList<>(tasks.reversed())`.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ rằng `reversed()` đảo trực tiếp collection gốc | Phương thức trả về reverse view được backing bởi collection gốc. | Dùng view để đọc/thao tác theo hướng ngược; tạo bản sao nếu cần dữ liệu độc lập. |
| Duyệt reverse view nhưng mong phần tử đầu của gốc xuất hiện trước | Iterator tuân theo encounter order của view. | Nhớ rằng phần tử cuối của gốc là phần tử đầu của view. |
| `findFirst()` trả về phần tử cuối của collection ban đầu | `findFirst()` lấy phần tử đầu theo encounter order của stream nguồn. | Đây là hành vi đúng của reverse view; dùng stream gốc nếu cần phần tử đầu ban đầu. |
| Parallel `forEach()` in ra không theo thứ tự ngược | `forEach()` không cam kết encounter order trong parallel stream. | Dùng `forEachOrdered()` nếu thứ tự quan sát được là yêu cầu. |
| Thay đổi qua view làm collection gốc đổi theo | View và collection gốc chia sẻ backing data. | Tạo bản sao bằng `new ArrayList<>(view)` hoặc `List.copyOf(view)` nếu cần tách biệt. |
| `addFirst()`/`addLast()` ném `UnsupportedOperationException` | Implementation không hỗ trợ chèn tại đầu/cuối hoặc collection không cho phép sửa đổi. | Kiểm tra hợp đồng và khả năng sửa đổi của implementation đang dùng. |
| Gọi `getFirst()` hoặc `removeFirst()` trên collection rỗng | Các thao tác này yêu cầu collection có phần tử. | Kiểm tra `isEmpty()` trước hoặc xử lý `NoSuchElementException`. |
| Sửa collection gốc khi reverse iterator đang chạy | Iterator có thể bị invalidated; fail-fast chỉ là best-effort. | Dùng `iterator.remove()` nếu được hỗ trợ hoặc kết thúc lượt duyệt trước khi sửa collection. |

## 9. Tài liệu tham khảo chính thức

- [Java SE 21 API — `SequencedCollection`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html): hợp đồng của reverse-ordered view, encounter order và các thao tác hai đầu.
- [Java SE 21 API — `List`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): kiểu trả về và hành vi của `List.reversed()`.
- [Java SE 21 API — `SequencedSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html): reverse view và các thao tác định vị phần tử của sequenced set.
- [Java SE 21 API — `SequencedMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): reverse view, các view có thứ tự và thao tác hai đầu của map.
- [Java SE 21 API — `Stream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): encounter order, `findFirst`, `forEachOrdered`, parallel stream và các thao tác làm mất hoặc thay đổi thứ tự.
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431): mục tiêu thiết kế và API sequenced collections được đưa vào Java 21.
