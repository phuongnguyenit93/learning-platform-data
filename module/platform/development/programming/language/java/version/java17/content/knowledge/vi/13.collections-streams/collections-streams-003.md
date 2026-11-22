# Stream.toList từ Java 16 và danh sách không cho phép sửa đổi

Từ Java 16, `Stream` có phương thức terminal `toList()` để thu các phần tử của stream thành một `List`. Vì phương thức này đã được chuẩn hóa trước Java 17, chương trình Java 17 có thể sử dụng trực tiếp mà không cần bật preview:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .map(String::toUpperCase)
        .toList();

System.out.println(names);
```

Kết quả:

```text
[AN, BÌNH, CHI]
```

Điểm quan trọng nhất của `Stream.toList()` là **danh sách trả về không cho phép sửa đổi** (*unmodifiable list*). Có thể đọc, duyệt, lấy kích thước hoặc kiểm tra phần tử; nhưng những thao tác thay đổi cấu trúc hay thay thế phần tử sẽ ném `UnsupportedOperationException`.

Đây là khác biệt cần nhớ khi chuyển code cũ từ `collect(Collectors.toList())` sang `toList()`. Một số chương trình trước đây gọi `add`, `remove` hoặc `sort` ngay sau khi thu stream. Nếu đổi sang `toList()` mà vẫn giữ những thao tác đó, chương trình sẽ phát sinh ngoại lệ lúc chạy.

## 1. Stream.toList() là gì?

`toList()` là một **terminal operation** của `java.util.stream.Stream<T>`. Nó tiêu thụ stream và trả về một đối tượng có kiểu khai báo `List<T>` chứa các phần tử mà pipeline tạo ra.

```java
List<Integer> squares = Stream.of(1, 2, 3, 4)
        .map(number -> number * number)
        .toList();

System.out.println(squares); // [1, 4, 9, 16]
```

Các đặc điểm chính:

- **Có từ Java 16:** dùng được ổn định trong Java 17.
- **Là terminal operation:** sau khi gọi `toList()`, stream đã được tiêu thụ và không thể dùng lại.
- **Trả về `List<T>`:** không cam kết một lớp triển khai cụ thể như `ArrayList`.
- **Không cho phép sửa đổi:** các thao tác mutator luôn ném `UnsupportedOperationException`.
- **Giữ encounter order nếu stream có thứ tự gặp:** với stream có encounter order, danh sách phản ánh thứ tự đó.
- **Có thể là value-based:** không nên dựa vào identity của đối tượng danh sách.

Tên `toList()` có vẻ tương tự collector `Collectors.toList()`, nhưng đây là hai API khác nhau. Một bên là phương thức trực tiếp của `Stream`; bên kia là collector được truyền vào `collect(...)`. Quan trọng hơn, hợp đồng về khả năng sửa đổi của hai kết quả **không giống nhau**.

### 1.1. Ví dụ từ pipeline đến danh sách

```java
import java.util.List;
import java.util.stream.Stream;

public class StreamToListBasic {
    public static void main(String[] args) {
        List<String> result = Stream.of("java", "stream", "list")
                .filter(word -> word.length() >= 5)
                .map(String::toUpperCase)
                .toList();

        System.out.println(result);
        System.out.println(result.size());
        System.out.println(result.get(0));
    }
}
```

Kết quả:

```text
[STREAM]
1
STREAM
```

Các thao tác trung gian `filter` và `map` tạo pipeline; `toList()` thực thi pipeline và thu các kết quả vào danh sách. Có thể dùng danh sách sau đó ở những nơi nhận `List`, mà không cần giữ stream đang mở.

### 1.2. toList() tiêu thụ stream

Stream được thiết kế để chỉ sử dụng một lần. Sau terminal operation, không được gọi thêm một terminal operation khác trên cùng stream:

```java
Stream<String> stream = Stream.of("A", "B", "C");

List<String> first = stream.toList();

// Sai: stream đã được tiêu thụ.
// long count = stream.count();
```

Nếu cần hai kết quả khác nhau, tạo pipeline mới từ nguồn có thể đọc lại hoặc tạo một stream mới:

```java
List<String> all = Stream.of("A", "B", "C").toList();
long count = Stream.of("A", "B", "C").count();
```

Không nên lưu một `Stream` để chia sẻ hoặc tái sử dụng như một collection. Nếu cần dữ liệu có thể duyệt nhiều lần, hãy thu nó thành collection phù hợp.

## 2. Danh sách không cho phép sửa đổi nghĩa là gì?

Một `List` trả về từ `toList()` vẫn hỗ trợ các thao tác đọc thông thường:

```java
List<String> languages = Stream.of("Java", "Kotlin", "Scala")
        .toList();

System.out.println(languages.size());          // 3
System.out.println(languages.get(1));          // Kotlin
System.out.println(languages.contains("Java")); // true

for (String language : languages) {
    System.out.println(language);
}
```

Nhưng các thao tác thay đổi danh sách không được phép:

```java
List<String> languages = Stream.of("Java", "Kotlin", "Scala")
        .toList();

languages.add("Go");             // UnsupportedOperationException
languages.remove("Kotlin");      // UnsupportedOperationException
languages.set(0, "Java 17");     // UnsupportedOperationException
languages.clear();               // UnsupportedOperationException
```

Mỗi dòng gây ngoại lệ độc lập. Khi chạy thực tế, nếu dòng `add` đã ném ngoại lệ thì các dòng sau trong cùng luồng thực thi sẽ không được chạy, trừ khi ngoại lệ được bắt.

### 2.1. Những phương thức nào bị ảnh hưởng?

Hợp đồng của `Stream.toList()` quy định các phương thức mutator luôn gây `UnsupportedOperationException`. Không chỉ `add` và `remove`, mà còn các thao tác thay đổi thông qua API khác:

| Thao tác | Kết quả với danh sách từ toList() |
| --- | --- |
| `add(element)` | Ném `UnsupportedOperationException`. |
| `addAll(collection)` | Ném `UnsupportedOperationException`. |
| `remove(element)` | Ném `UnsupportedOperationException`. |
| `remove(index)` | Ném `UnsupportedOperationException`. |
| `removeAll(...)` / `retainAll(...)` | Ném `UnsupportedOperationException`. |
| `clear()` | Ném `UnsupportedOperationException`. |
| `set(index, element)` | Ném `UnsupportedOperationException`. |
| `replaceAll(operator)` | Ném `UnsupportedOperationException`. |
| `sort(comparator)` | Ném `UnsupportedOperationException`. |
| `Iterator.remove()` | Ném `UnsupportedOperationException`. |
| `ListIterator.add(...)` / `set(...)` | Ném `UnsupportedOperationException`. |

Đặc biệt, không nên dựa vào giả định “nếu danh sách rỗng thì `clear()` không làm gì nên sẽ không lỗi” hoặc “`remove` phần tử không tồn tại thì có thể trả `false`”. Hợp đồng của danh sách này quy định các thao tác mutator luôn ném ngoại lệ.

Ví dụ:

```java
List<String> empty = Stream.<String>empty().toList();

// Vẫn không được gọi mutator trên danh sách không cho phép sửa đổi.
// empty.clear();
```

Các phương thức đọc như `size`, `isEmpty`, `get`, `contains`, `iterator` và `toArray` vẫn có thể dùng bình thường.

### 2.2. Ngoại lệ xuất hiện lúc chạy

`UnsupportedOperationException` là unchecked exception (`RuntimeException`). Compiler không bắt buộc bạn khai báo `throws` hoặc dùng `try/catch`.

```java
List<Integer> values = Stream.of(1, 2, 3).toList();

try {
    values.add(4);
} catch (UnsupportedOperationException ex) {
    System.out.println("Danh sách không cho phép sửa đổi");
}
```

Trong ứng dụng thực tế, không nên dùng `try/catch` để thử xem collection có sửa được hay không. Hãy thiết kế rõ từ đầu: nếu cần kết quả chỉ đọc, dùng `toList()`; nếu cần thay đổi, tạo một collection mutable.

## 3. So sánh Stream.toList() với Collectors.toList()

Đây là phần quan trọng khi nâng cấp code Java 16/17 hoặc refactor pipeline cũ.

### 3.1. Stream.toList()

```java
List<String> names = Stream.of("An", "Bình", "Chi")
        .toList();
```

Kết quả là danh sách **unmodifiable**. Không được thêm, xóa hoặc thay thế phần tử.

### 3.2. collect(Collectors.toList())

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .collect(Collectors.toList());
```

`Collectors.toList()` không đưa ra bảo đảm về:

- Kiểu triển khai cụ thể của danh sách.
- Khả năng sửa đổi của danh sách.
- Khả năng serializable hoặc thread-safe.

Trong các bản triển khai JDK phổ biến, collector này thường tạo một `ArrayList` có thể sửa đổi. Tuy nhiên, **không nên dựa vào hành vi triển khai đó như một cam kết của API**. Nếu chương trình bắt buộc cần một danh sách mutable hoặc cần một kiểu cụ thể, hãy yêu cầu rõ điều đó bằng `Collectors.toCollection(ArrayList::new)`.

### 3.3. Bảng so sánh hợp đồng

| Tiêu chí | `Stream.toList()` | `collect(Collectors.toList())` |
| --- | --- | --- |
| Có từ | Java 16 | Java 8 |
| Cách gọi | `stream.toList()` | `stream.collect(Collectors.toList())` |
| Kiểu trả về khai báo | `List<T>` | `List<T>` |
| Khả năng sửa đổi | **Không cho phép sửa đổi** | Không có bảo đảm về mutability |
| Kiểu triển khai | Không được cam kết | Không được cam kết |
| Thứ tự phần tử | Encounter order nếu stream có encounter order | Theo đặc tính collector và encounter order của stream |
| Phù hợp khi | Chỉ cần kết quả dạng danh sách để đọc/duyệt | Cần dùng collector tổng quát; nếu cần mutable, hãy chỉ định collection rõ ràng |

Không nên đổi mọi `collect(Collectors.toList())` thành `toList()` mà không xem code phía sau. Nếu có đoạn `result.add(...)`, `result.sort(...)` hoặc truyền danh sách vào API có ý định chỉnh sửa, thay đổi đó có thể gây lỗi runtime.

## 4. Khi cần danh sách mutable, dùng cách nào?

Nếu kết quả cần được bổ sung, xóa hoặc sắp xếp tại chỗ, có thể chọn một trong các cách sau.

### 4.1. Collectors.toCollection(ArrayList::new) khi cần ArrayList

Đây là lựa chọn rõ ràng khi cần một `ArrayList` mới:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .collect(Collectors.toCollection(ArrayList::new));

names.add("Dũng");
names.remove("An");
names.sort(String.CASE_INSENSITIVE_ORDER);

System.out.println(names);
```

Collector nhận supplier `ArrayList::new`, nên kiểu collection đích được yêu cầu cụ thể. Danh sách tạo ra có thể sửa đổi theo hợp đồng của `ArrayList`.

### 4.2. Tạo ArrayList từ kết quả toList()

Nếu pipeline đã dùng `toList()` và sau đó mới phát sinh nhu cầu sửa đổi:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> readOnly = Stream.of("A", "B", "C").toList();
List<String> editable = new ArrayList<>(readOnly);

editable.add("D");
editable.set(0, "Updated");

System.out.println(readOnly); // [A, B, C]
System.out.println(editable); // [Updated, B, C, D]
```

Constructor `ArrayList(Collection<? extends E>)` tạo một danh sách mới chứa các phần tử của collection nguồn. Việc sửa `editable` không thay đổi cấu trúc của `readOnly`.

### 4.3. Sắp xếp mà không sửa danh sách gốc

Nếu muốn có kết quả đã sắp xếp nhưng vẫn giữ danh sách ban đầu, có thể tạo bản mutable:

```java
List<String> original = Stream.of("pear", "apple", "orange").toList();

List<String> sorted = new ArrayList<>(original);
sorted.sort(String.CASE_INSENSITIVE_ORDER);

System.out.println(original); // [pear, apple, orange]
System.out.println(sorted);   // [apple, orange, pear]
```

Hoặc thực hiện sắp xếp ngay trong pipeline trước khi thu:

```java
List<String> sorted = Stream.of("pear", "apple", "orange")
        .sorted(String.CASE_INSENSITIVE_ORDER)
        .toList();
```

Cách thứ hai tạo danh sách kết quả đã có thứ tự mong muốn và không cần sửa sau khi thu.

## 5. Phân biệt toList(), toUnmodifiableList() và List.copyOf()

Java có nhiều API tạo danh sách không cho phép sửa đổi. Chúng gần nhau về mục tiêu nhưng khác điểm xuất phát và một số chi tiết hợp đồng.

### 5.1. Collectors.toUnmodifiableList()

Collector này được bổ sung từ Java 10:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .collect(Collectors.toUnmodifiableList());
```

Kết quả không cho phép sửa đổi. Khác với `Stream.toList()`, `Collectors.toUnmodifiableList()` **không chấp nhận phần tử null**; nếu stream chứa null, collector ném `NullPointerException`.

### 5.2. List.copyOf(...)

Nếu đã có một collection và muốn tạo một danh sách không cho phép sửa đổi từ các phần tử đó:

```java
import java.util.ArrayList;

List<String> source = new ArrayList<>();
source.add("Java");
source.add("Kotlin");

List<String> snapshot = List.copyOf(source);
```

`List.copyOf` tạo danh sách không cho phép sửa đổi từ các phần tử của collection nguồn. Phương thức này không chấp nhận null; nếu nguồn chứa null, nó ném `NullPointerException`.

### 5.3. Bảng lựa chọn

| API | Đầu vào | Kết quả | Null |
| --- | --- | --- | --- |
| `stream.toList()` | Stream | List không cho phép sửa đổi | Trong JDK 17, phần tử null phát ra từ stream được giữ lại |
| `stream.collect(Collectors.toList())` | Stream | List; không cam kết mutability hoặc implementation | Không nên suy luận hợp đồng chỉ từ implementation hiện tại |
| `stream.collect(Collectors.toUnmodifiableList())` | Stream | List không cho phép sửa đổi | Ném `NullPointerException` nếu có phần tử null |
| `List.copyOf(collection)` | Collection | List không cho phép sửa đổi | Ném `NullPointerException` nếu collection có null |
| `Collections.unmodifiableList(list)` | List | View không cho phép sửa đổi | Phụ thuộc collection nền |
| `new ArrayList<>(collection)` | Collection | ArrayList có thể sửa đổi | ArrayList cho phép null |

Khi null là một phần hợp lệ của dữ liệu, cần đặc biệt chú ý: không thể thay `Stream.toList()` bằng `Collectors.toUnmodifiableList()` hoặc `List.copyOf()` mà không kiểm tra lại chính sách null.

## 6. Unmodifiable không có nghĩa là immutable sâu

Danh sách không cho phép sửa đổi ngăn các thao tác thay đổi **cấu trúc danh sách** hoặc thay thế phần tử. Nó không tự biến các đối tượng bên trong thành bất biến.

Ví dụ:

```java
import java.util.List;
import java.util.stream.Stream;

class User {
    private String name;

    User(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String newName) {
        this.name = newName;
    }
}

public class ShallowUnmodifiable {
    public static void main(String[] args) {
        User user = new User("An");
        List<User> users = Stream.of(user).toList();

        // Không được thay phần tử trong list:
        // users.set(0, new User("Bình"));

        // Nhưng đối tượng User bên trong vẫn mutable:
        users.get(0).rename("Bình");

        System.out.println(users.get(0).name()); // Bình
    }
}
```

Danh sách vẫn chứa cùng tham chiếu đến đối tượng `User`; `rename` thay đổi trạng thái của đối tượng đó. Đây là **shallow unmodifiable collection**, không phải deep immutable object graph.

Nếu cần dữ liệu bất biến sâu, phải thiết kế các phần tử bất biến hoặc tạo bản sao phù hợp. `Stream.toList()` không tự sao chép từng phần tử và không thể biết cách clone một object tùy ý.

### 6.1. Thay đổi nguồn sau khi thu có làm danh sách kết quả đổi không?

`toList()` là terminal operation tạo ra kết quả collection từ các phần tử được stream phát ra; nó không trả về một view sống của collection nguồn.

```java
List<String> source = new ArrayList<>(List.of("A", "B"));

List<String> result = source.stream().toList();
source.add("C");

System.out.println(source); // [A, B, C]
System.out.println(result); // [A, B]
```

Trong ví dụ với các chuỗi bất biến, kết quả `result` vẫn gồm hai phần tử ban đầu. Nếu phần tử là object mutable, hai collection có thể cùng giữ tham chiếu đến object đó; thay đổi object vẫn được nhìn thấy qua cả hai collection.

## 7. Phân biệt unmodifiable list với unmodifiable view

Tên gọi “không cho phép sửa đổi” dễ khiến người học nghĩ mọi API đều tạo ra cùng một loại kết quả. Hãy phân biệt:

- `stream.toList()`: thu phần tử thành một danh sách kết quả không cho phép sửa đổi.
- `List.copyOf(source)`: tạo một danh sách không cho phép sửa đổi từ các phần tử của collection nguồn.
- `Collections.unmodifiableList(source)`: tạo **view không cho phép sửa đổi** trên collection nền. Nếu code khác sửa collection nền, view sẽ phản ánh thay đổi đó.

Ví dụ về view:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> backing = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(backing);

// Không thể sửa qua view:
// view.add("C");

// Nhưng code giữ backing vẫn có thể sửa:
backing.add("C");

System.out.println(view); // [A, B, C]
```

Nếu cần một snapshot không cho phép sửa đổi, hãy cân nhắc `List.copyOf` hoặc `stream.toList()` tùy nguồn. Nếu cần cung cấp một view chỉ đọc nhưng muốn người sở hữu collection nền tiếp tục cập nhật dữ liệu, `Collections.unmodifiableList` có thể phù hợp.

## 8. Encounter order: thứ tự của danh sách kết quả

Stream có thể có hoặc không có **encounter order** (thứ tự gặp phần tử). `toList()` giữ thứ tự đó nếu stream có thứ tự:

```java
List<String> ordered = Stream.of("first", "second", "third").toList();
System.out.println(ordered);
```

Kết quả:

```text
[first, second, third]
```

Với stream song song nhưng có encounter order, `toList()` vẫn trả phần tử theo encounter order:

```java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.parallelStream()
        .map(number -> number * 10)
        .toList();

System.out.println(result); // [10, 20, 30, 40, 50]
```

Không nên suy ra thứ tự từ cách tác vụ song song hoàn thành; stream framework quản lý kết quả theo encounter order của nguồn nếu thứ tự đó được giữ.

Ngược lại, nếu pipeline không có encounter order, không nên dựa vào thứ tự của danh sách:

```java
List<Integer> result = List.of(5, 1, 4, 2, 3)
        .stream()
        .unordered()
        .toList();
```

Trong trường hợp này, nếu ứng dụng cần một thứ tự xác định, hãy gọi `sorted()` trước `toList()`:

```java
List<Integer> sorted = List.of(5, 1, 4, 2, 3)
        .stream()
        .unordered()
        .sorted()
        .toList();

System.out.println(sorted); // [1, 2, 3, 4, 5]
```

## 9. Stream song song và tính an toàn luồng

`toList()` hoạt động với cả stream tuần tự và song song:

```java
List<Integer> result = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .toList();
```

Tuy nhiên, cần phân biệt ba vấn đề:

1. **Parallel execution:** các phép xử lý trong pipeline có thể chạy đồng thời.
2. **Unmodifiable list:** không cho phép thay đổi danh sách thông qua mutator.
3. **Thread safety:** không đồng nghĩa mọi phần tử bên trong hoặc mọi cách truy cập đồng thời đều an toàn.

Tài liệu API của `Stream.toList()` lưu ý rằng nếu pipeline song song, danh sách trả về có thể không thread-safe. Đừng lấy tính không cho phép sửa đổi làm bằng chứng rằng đối tượng hoặc các phần tử bên trong an toàn cho mọi tình huống đồng thời. Nếu cần chia sẻ qua nhiều thread, hãy xác định rõ quy tắc công bố dữ liệu, khả năng thread-safe của phần tử và cơ chế đồng bộ phù hợp.

## 10. Value-based list và không dựa vào identity

Javadoc của `Stream.toList()` nêu rằng danh sách trả về **có thể là value-based**. Người gọi không nên giả định identity của các instance được trả về.

Tránh viết logic phụ thuộc vào:

- So sánh tham chiếu `==` để xác định hai kết quả `toList()` có “cùng một danh sách” hay không.
- `System.identityHashCode(list)` như một định danh nghiệp vụ.
- Dùng chính danh sách làm monitor trong `synchronized(list)`.

Ví dụ, không nên dựa vào:

```java
List<String> first = Stream.of("A", "B").toList();
List<String> second = Stream.of("A", "B").toList();

// Không dùng identity để kiểm tra hai kết quả có cùng dữ liệu.
boolean sameReference = first == second;

// Nếu muốn so sánh nội dung, dùng equals:
boolean sameContents = first.equals(second);
```

`equals` so sánh nội dung theo hợp đồng của `List`; `==` so sánh hai tham chiếu có trỏ đến cùng một object hay không. Khi làm việc với collection value-based, nên quan tâm **giá trị chứa trong danh sách**, không phải identity của object danh sách.

## 11. Xử lý phần tử null

`Stream.toList()` không đặt quy tắc loại bỏ null như `Collectors.toUnmodifiableList()` hoặc `List.copyOf()`. Trong triển khai JDK 17, nếu stream phát ra null, danh sách kết quả giữ phần tử đó:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("A", null, "C").toList();

System.out.println(values.size());       // 3
System.out.println(values.get(1));       // null
```

Điều này không có nghĩa nên để null xuất hiện tùy tiện trong mọi pipeline. Nếu phần tử null không hợp lệ theo nghiệp vụ, hãy kiểm tra hoặc lọc rõ ràng:

```java
List<String> names = Stream.of("An", null, "Bình")
        .filter(java.util.Objects::nonNull)
        .toList();
```

Ngược lại, `Collectors.toUnmodifiableList()` và `List.copyOf()` ném `NullPointerException` nếu đầu vào có null. Khi thay API thu thập danh sách, hãy kiểm tra chính sách null của dữ liệu để tránh thay đổi hành vi ngoài dự kiến.

## 12. Các kiểu dữ liệu primitive

`Stream.toList()` là phương thức trên `Stream<T>` (reference stream). Các stream chuyên biệt `IntStream`, `LongStream`, `DoubleStream` có API riêng; muốn dùng `toList()` cho giá trị primitive thì thường phải boxing:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.rangeClosed(1, 5)
        .boxed()
        .toList();

System.out.println(numbers); // [1, 2, 3, 4, 5]
```

Nếu chỉ cần một mảng primitive, không cần boxing thành `List<Integer>`:

```java
int[] numbers = IntStream.rangeClosed(1, 5).toArray();
```

Chọn `boxed().toList()` khi API phía sau cần `List<Integer>`. Chọn `toArray()` khi muốn giữ dữ liệu primitive và thao tác theo mảng.

## 13. Tình huống thực tế: thu kết quả truy vấn để chỉ đọc

Giả sử dịch vụ đọc dữ liệu đơn hàng và trả về danh sách kết quả cho lớp gọi. Nếu lớp gọi chỉ cần duyệt và hiển thị, một danh sách không cho phép sửa đổi là phù hợp:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Stream;

record OrderSummary(long id, BigDecimal total) {}

class OrderService {
    List<OrderSummary> summaries() {
        return Stream.of(
                new OrderSummary(101, new BigDecimal("120.00")),
                new OrderSummary(102, new BigDecimal("250.00")),
                new OrderSummary(103, new BigDecimal("80.00"))
        )
        .filter(order -> order.total().signum() > 0)
        .toList();
    }
}

public class OrderReport {
    public static void main(String[] args) {
        OrderService service = new OrderService();
        List<OrderSummary> orders = service.summaries();

        for (OrderSummary order : orders) {
            System.out.println(
                    order.id() + ": " + order.total()
            );
        }
    }
}
```

Lớp gọi nhận một `List<OrderSummary>` để đọc. Nếu yêu cầu nghiệp vụ không cho phép lớp gọi thêm hoặc xóa đơn hàng trong kết quả, `toList()` diễn đạt đúng ý định. Nếu cần chỉnh sửa bản hiển thị riêng, lớp gọi có thể tạo `new ArrayList<>(orders)`.

Lưu ý: danh sách không cho phép sửa đổi không thay thế kiểm soát quyền truy cập dữ liệu hoặc bảo vệ dữ liệu ở tầng database. Nó chỉ giới hạn thao tác trên collection kết quả đang được trả về.

## 14. Chuyển code cũ sang toList() an toàn

Khi refactor:

```java
List<String> result = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .collect(Collectors.toList());
```

Có thể đổi thành:

```java
List<String> result = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .toList();
```

Nhưng trước khi đổi, hãy nhìn các dòng sử dụng `result` tiếp theo:

```java
result.add("Other");
result.remove(0);
result.sort(String.CASE_INSENSITIVE_ORDER);
```

Nếu các thao tác này là một phần hành vi cần thiết, có hai hướng:

**Hướng A — Yêu cầu danh sách mutable ngay từ pipeline**

```java
List<String> result = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .collect(Collectors.toCollection(ArrayList::new));
```

**Hướng B — Thu kết quả chỉ đọc rồi tạo bản mutable ở nơi cần sửa**

```java
List<String> collected = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .toList();

List<String> result = new ArrayList<>(collected);
result.add("Other");
```

Hướng A thể hiện rõ ngay tại pipeline rằng kết quả cần là `ArrayList`. Hướng B hữu ích khi muốn giữ một kết quả chỉ đọc và chỉ một bước xử lý sau đó mới cần bản sao mutable.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `add()` sau `toList()` và nhận `UnsupportedOperationException`. | Danh sách từ `Stream.toList()` không cho phép sửa đổi. | Dùng `Collectors.toCollection(ArrayList::new)` hoặc sao chép sang `new ArrayList<>(result)`. |
| `set()` hoặc `sort()` cũng ném ngoại lệ. | Các thao tác thay thế/sắp xếp là mutator. | Tạo danh sách mutable trước khi thay đổi. |
| Đổi `Collectors.toList()` sang `toList()` làm code cũ lỗi runtime. | Code cũ dựa vào khả năng sửa đổi của implementation collector hiện tại. | Xác định hợp đồng cần có và chọn API tương ứng, không dựa vào implementation ngẫu nhiên. |
| Gọi lại stream sau `toList()` bị lỗi. | `toList()` đã tiêu thụ stream. | Tạo stream mới từ nguồn hoặc giữ kết quả collection để dùng lại. |
| Dùng `List.copyOf()` thay `toList()` làm phát sinh NPE. | `List.copyOf()` không chấp nhận null. | Xác định null có hợp lệ không; chọn API phù hợp hoặc lọc/validate trước. |
| Nghĩ các object trong list cũng bất biến. | Unmodifiable chỉ giới hạn thao tác trên danh sách. | Dùng phần tử immutable hoặc tạo bản sao sâu nếu yêu cầu nghiệp vụ cần. |
| Dựa vào thứ tự của stream unordered. | Nguồn/pipeline không có encounter order. | Dùng `sorted()` hoặc một nguồn có thứ tự nếu cần kết quả xác định. |
| Dùng `==` để so sánh hai danh sách được tạo từ stream. | Identity không phải hợp đồng nội dung; danh sách có thể value-based. | Dùng `equals()` để so sánh nội dung. |
| Cho rằng unmodifiable đồng nghĩa thread-safe. | Tính không cho phép sửa đổi và an toàn luồng là hai khái niệm khác nhau. | Xem xét thread safety của collection và các phần tử; thiết kế đồng bộ khi cần. |

## 16. Bài tập thực hành

### Bài 1 — Quan sát danh sách không cho phép sửa đổi

Viết chương trình tạo danh sách từ:

```java
List<String> values = Stream.of("Java", "Kotlin", "Scala").toList();
```

Thử gọi `add`, `remove`, `set`, `clear` và ghi nhận ngoại lệ. Sau đó gọi `size`, `get`, `contains` và duyệt bằng vòng `for-each`.

### Bài 2 — Chọn API đúng cho danh sách mutable

Cho pipeline lọc và chuyển đổi một danh sách sản phẩm. Sau khi thu, chương trình phải thêm một sản phẩm khuyến mãi và sắp xếp kết quả. Viết phiên bản dùng `Collectors.toCollection(ArrayList::new)`, giải thích vì sao `toList()` không phù hợp nếu muốn sửa trực tiếp kết quả.

### Bài 3 — So sánh các collector

Tạo ba kết quả từ cùng một stream:

- `stream.toList()`
- `stream.collect(Collectors.toList())`
- `stream.collect(Collectors.toUnmodifiableList())`

So sánh hợp đồng mutability của chúng. Không kết luận `Collectors.toList()` luôn trả về `ArrayList` chỉ vì một bản JDK cụ thể đang làm như vậy.

### Bài 4 — Kiểm tra null

Thử tạo stream có phần tử null và thu bằng `toList()`, sau đó thử với `Collectors.toUnmodifiableList()` và `List.copyOf()`. Giải thích sự khác nhau trong chính sách null.

### Bài 5 — Unmodifiable hay immutable sâu?

Tạo một lớp mutable `Person` có phương thức đổi tên. Thu một `List<Person>` bằng `toList()`, thử thay phần tử trong danh sách và thử đổi tên object lấy từ `get(0)`. Giải thích vì sao hai thao tác có kết quả khác nhau.

### Bài 6 — Encounter order

Tạo stream tuần tự, stream song song từ `List.of(1, 2, 3, 4, 5)` và stream đã gọi `unordered()`. Thu mỗi stream bằng `toList()`. Nêu trường hợp nào có thể dựa vào encounter order và trường hợp nào cần `sorted()`.

## 17. Tài liệu Java 17 chính thức

- [Java SE 17 API — Stream.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): hợp đồng phương thức, thời điểm xuất hiện, tính unmodifiable, encounter order và lưu ý value-based.
- [Java SE 17 API — Collectors.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): hợp đồng collector và những điều không được bảo đảm về loại list, mutability, serializability, thread safety.
- [Java SE 17 API — Collectors.toUnmodifiableList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector tạo danh sách không cho phép sửa đổi và xử lý null.
- [Java SE 17 API — List.copyOf()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): tạo danh sách không cho phép sửa đổi từ collection nguồn.
- [Java SE 17 API — Collections.unmodifiableList(...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view không cho phép sửa đổi trên list nền.

`Stream.toList()` là lựa chọn tự nhiên khi pipeline cần tạo một kết quả `List` để đọc và duyệt. Nếu chương trình cần thêm, xóa, thay thế hoặc sắp xếp trực tiếp danh sách, hãy yêu cầu collection mutable một cách rõ ràng. Phân biệt hợp đồng của `toList()` với `Collectors.toList()`, đồng thời nhớ rằng **unmodifiable list không làm các object bên trong trở thành immutable**.
