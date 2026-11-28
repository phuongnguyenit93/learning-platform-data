# So sánh `toList()` với `Collectors.toList()` về hợp đồng mutability

`Stream.toList()` và `stream.collect(Collectors.toList())` đều thu các phần tử của pipeline thành một `List`, nhưng hợp đồng về khả năng sửa đổi của chúng khác nhau. `Stream.toList()` được bổ sung trong Java 16 và **bảo đảm danh sách kết quả không sửa đổi được**. Ngược lại, `Collectors.toList()` không cam kết danh sách kết quả mutable hay unmodifiable, cũng không cam kết kiểu triển khai cụ thể.

Vì vậy, khi chỉ cần đọc kết quả, `Stream.toList()` thể hiện rõ ý định. Khi cần thêm, xóa, thay thế hoặc sắp xếp phần tử sau khi thu thập, hãy yêu cầu một loại collection mutable cụ thể bằng `Collectors.toCollection(ArrayList::new)` hoặc tạo bản sao `new ArrayList<>(result)`.

## 1. Hai cách thu thập có hợp đồng khác nhau

Ví dụ cùng một pipeline nhưng dùng hai terminal operation:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of("An", "Bình", "Chi");

List<String> readOnlyNames = source.stream()
    .filter(name -> !name.isBlank())
    .toList();

List<String> collectedNames = source.stream()
    .filter(name -> !name.isBlank())
    .collect(Collectors.toList());
```

Cả hai biến đều có kiểu khai báo `List<String>`. Tuy nhiên, kiểu interface `List` không biểu diễn khả năng sửa đổi trong hệ thống kiểu của Java. Muốn biết có thể thay đổi kết quả hay không, phải đọc hợp đồng của terminal operation đã tạo ra nó.

| Tiêu chí | `stream.toList()` | `stream.collect(Collectors.toList())` |
| --- | --- | --- |
| Có từ phiên bản | Java 16 | Java 8 |
| Kiểu kết quả | `List<T>` | `List<T>` |
| Khả năng sửa đổi | Bảo đảm unmodifiable | Không có bảo đảm mutable hoặc unmodifiable |
| Gọi mutator | Luôn ném `UnsupportedOperationException` | Không được dựa vào việc lời gọi sẽ thành công hay thất bại |
| Kiểu triển khai | Không được bảo đảm | Không được bảo đảm |
| Encounter order | Giữ thứ tự nếu stream có encounter order | Collector giữ thứ tự theo hợp đồng collector nếu stream có thứ tự |
| Khi cần chọn rõ collection | Dùng bản sao mutable | Dùng `Collectors.toCollection(factory)` |

## 2. Hợp đồng của `Stream.toList()`

Javadoc quy định danh sách do `Stream.toList()` trả về là unmodifiable. Mọi lời gọi mutator method trên danh sách đều ném `UnsupportedOperationException`, kể cả khi thao tác đó không làm thay đổi nội dung trong trường hợp cụ thể.

```java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi").stream().toList();

System.out.println(names.get(0)); // An
System.out.println(names.size()); // 3
System.out.println(names.contains("Bình")); // true

names.add("Dung"); // UnsupportedOperationException
```

Các thao tác đọc như `get`, `size`, `contains`, duyệt bằng vòng lặp và tạo stream mới vẫn sử dụng bình thường. Các thao tác làm thay đổi cấu trúc hoặc giá trị phần tử như `add`, `remove`, `set`, `clear`, `replaceAll`, `removeIf` và `sort` đều không được hỗ trợ.

Hợp đồng cũng không bảo đảm lớp triển khai cụ thể. Không ép kiểu kết quả thành `ArrayList`, không dựa vào tên lớp nội bộ trong debugger và không dùng identity của danh sách để điều khiển logic. Danh sách có thể là value-based; hãy dùng `equals()` khi cần so sánh nội dung.

## 3. Hợp đồng của `Collectors.toList()`

`Collectors.toList()` tạo một collector tích lũy phần tử stream thành `List`. Tuy nhiên, tài liệu API nói rõ không có bảo đảm về:

- Kiểu triển khai cụ thể của `List`.
- Khả năng sửa đổi của danh sách.
- Khả năng tuần tự hóa.
- Tính thread-safe của danh sách.

Một số phiên bản OpenJDK thường trả về `ArrayList`, nên đoạn mã như sau có thể hoạt động trong môi trường đang dùng:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Bình", "Chi").stream()
    .collect(Collectors.toList());

names.add("Dung"); // Có thể chạy trên một số implementation, nhưng không được API bảo đảm
```

Đừng biến hành vi quan sát được của một JDK thành giả định của ứng dụng. Nếu chương trình bắt buộc phải chỉnh sửa danh sách, việc gọi `add()` trên kết quả của `Collectors.toList()` đang phụ thuộc vào một thuộc tính không được hợp đồng bảo đảm. Điều đó có thể khiến mã hoạt động ở môi trường phát triển nhưng gặp lỗi hoặc hành vi khác khi đổi JDK hay implementation.

## 4. Khi cần danh sách mutable, hãy yêu cầu rõ `ArrayList`

`Collectors.toCollection(Supplier)` cho phép chỉ định collection cần tạo. Nếu muốn một `ArrayList` có thể thêm, xóa và thay thế phần tử, hãy truyền `ArrayList::new`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> editableNames = List.of("An", "Bình", "Chi").stream()
    .filter(name -> !name.isBlank())
    .collect(Collectors.toCollection(ArrayList::new));

editableNames.add("Dung"); // Hợp lệ
editableNames.set(0, "Anh"); // Hợp lệ
editableNames.remove("Bình"); // Hợp lệ
```

Ở đây, `ArrayList` là loại collection được chỉ định trực tiếp bởi factory. Chương trình có thể dựa vào hợp đồng mutable của `ArrayList`, không phải phỏng đoán loại collection do collector tự chọn.

Nếu đã có kết quả từ `Stream.toList()` và muốn tạo một danh sách làm việc riêng, dùng copy constructor:

```java
import java.util.ArrayList;
import java.util.List;

List<String> result = List.of("An", "Bình", "Chi").stream().toList();
List<String> editableCopy = new ArrayList<>(result);

editableCopy.add("Dung");
editableCopy.remove("Bình");

System.out.println(result);       // [An, Bình, Chi]
System.out.println(editableCopy); // [An, Chi, Dung]
```

Hai danh sách có cấu trúc riêng. Đây là bản sao nông: nếu phần tử là object mutable, cả hai danh sách vẫn có thể tham chiếu tới cùng object. Nếu cần tách cả trạng thái object, phải sao chép từng phần tử hoặc chuyển đổi sang kiểu immutable phù hợp.

## 5. `toList()` và `toUnmodifiableList()` không giống nhau hoàn toàn

`Collectors.toUnmodifiableList()` cũng tạo danh sách không sửa đổi được, nhưng có một khác biệt quan trọng về null:

| API | Danh sách có sửa đổi được? | Chấp nhận phần tử `null`? |
| --- | --- | --- |
| `stream.toList()` | Không | Có |
| `stream.collect(Collectors.toUnmodifiableList())` | Không | Không; ném `NullPointerException` |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Có | Có |

Ví dụ:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> allowsNull = Stream.of("An", null, "Chi").toList();
// [An, null, Chi]

List<String> rejectsNull = Stream.of("An", null, "Chi")
    .collect(Collectors.toUnmodifiableList());
// Ném NullPointerException
```

Nếu mục tiêu chỉ là danh sách không sửa đổi được và dữ liệu có thể chứa null, `Stream.toList()` phù hợp. Nếu chính sách dữ liệu yêu cầu từ chối null, `Collectors.toUnmodifiableList()` thể hiện điều đó rõ ràng. Nếu cần mutable và chấp nhận null, chọn `ArrayList` qua `toCollection`.

## 6. Ảnh hưởng khi chuyển mã từ `Collectors.toList()` sang `Stream.toList()`

Hai cách gọi trông tương đương về cú pháp và kiểu trả về, nhưng thay thế trực tiếp có thể làm thay đổi hành vi chương trình. Hãy kiểm tra mọi nơi sử dụng kết quả sau khi thu thập.

**Trước khi chuyển đổi:**

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> source = List.of(" An ", "Bình ", "Chi");

List<String> names = source.stream()
    .map(String::trim)
    .collect(Collectors.toList());

names.add("Dung");
names.sort(String::compareTo);
```

**Nếu chỉ cần đọc kết quả sau chuyển đổi:**

```java
import java.util.List;

List<String> source = List.of(" An ", "Bình ", "Chi");

List<String> names = source.stream()
    .map(String::trim)
    .toList();

names.forEach(System.out::println);
```

**Nếu vẫn cần chỉnh sửa kết quả:**

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = List.of(" An ", "Bình ", "Chi");

List<String> names = new ArrayList<>(source.stream()
    .map(String::trim)
    .toList());

names.add("Dung");
names.sort(String::compareTo);
```

Khi rà soát mã nguồn, chú ý các lời gọi trực tiếp như `add`, `remove`, `set`, `sort`, `replaceAll`, `removeIf`, `clear`, cũng như các phương thức khác nhận danh sách rồi sửa nó. Đừng chỉ tìm các mutator ngay sau dòng tạo list; danh sách có thể được truyền qua nhiều lớp trước khi bị chỉnh sửa.

Nếu dự án cần chạy trên Java 8 đến Java 15, `Stream.toList()` chưa có trong API của các phiên bản đó. Khi đó cần tiếp tục dùng collector tương thích và chọn `toCollection(ArrayList::new)` nếu cần mutable. Từ Java 16 trở lên, có thể dùng `Stream.toList()` khi hợp đồng unmodifiable là phù hợp.

## 7. Chọn API theo yêu cầu của chương trình

| Nhu cầu | API nên chọn | Lý do |
| --- | --- | --- |
| Thu kết quả chỉ để đọc | `stream.toList()` | Hợp đồng unmodifiable rõ ràng, cú pháp ngắn. |
| Thu kết quả rồi cần thêm/xóa/thay thế/sắp xếp | `collect(Collectors.toCollection(ArrayList::new))` | Bảo đảm collection được tạo là `ArrayList` mutable. |
| Đã có list unmodifiable và cần bản làm việc | `new ArrayList<>(result)` | Tạo cấu trúc mutable độc lập. |
| Cần unmodifiable list và phải từ chối null | `collect(Collectors.toUnmodifiableList())` | Collector thể hiện rõ chính sách không nhận null. |
| Cần một loại collection khác | `collect(Collectors.toCollection(factory))` | Chỉ định rõ implementation phù hợp với nghiệp vụ. |

Trong thiết kế phương thức, hãy mô tả rõ hợp đồng kết quả. Kiểu trả về `List<T>` không cho người gọi biết danh sách có mutable hay không. Nếu phương thức trả về danh sách unmodifiable, ghi điều đó trong Javadoc. Nếu người gọi được phép sửa đổi, hãy trả về collection mutable theo hợp đồng hoặc cung cấp bản sao mutable có chủ đích.

Ví dụ một phương thức trả về kết quả chỉ đọc:

```java
import java.util.List;

class NameService {
    /** Returns an unmodifiable list of normalized names. */
    List<String> normalizedNames(List<String> source) {
        return source.stream()
            .filter(name -> !name.isBlank())
            .map(String::trim)
            .toList();
    }
}
```

Nếu hợp đồng yêu cầu caller chỉnh sửa kết quả, phương thức có thể tạo `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

class EditableNameService {
    List<String> normalizedNames(List<String> source) {
        return source.stream()
            .filter(name -> !name.isBlank())
            .map(String::trim)
            .collect(Collectors.toCollection(ArrayList::new));
    }
}
```

Trong các ví dụ này, `source` được giả định không chứa null vì pipeline gọi `isBlank()` và `trim()` trực tiếp trên phần tử. Nếu dữ liệu đầu vào có thể null, hãy xác định chính sách null và xử lý trước khi gọi các phương thức đó.

## 8. Ghi nhớ

- `Stream.toList()` có từ Java 16 và luôn trả về danh sách không sửa đổi được.
- `Collectors.toList()` không cam kết kết quả mutable, unmodifiable hoặc thuộc lớp triển khai nào.
- Việc một JDK hiện trả về `ArrayList` cho `Collectors.toList()` không phải bảo đảm của API.
- Nếu cần mutable, chọn `Collectors.toCollection(ArrayList::new)` hoặc `new ArrayList<>(result)`.
- Khi thay `Collectors.toList()` bằng `Stream.toList()`, rà soát mọi thao tác sửa đổi ở các nơi tiêu thụ kết quả.
- Kiểu khai báo `List<T>` không tự thể hiện hợp đồng mutability; hãy ghi rõ trong tài liệu phương thức.

Chọn terminal operation theo cách chương trình sẽ sử dụng kết quả. `Stream.toList()` phù hợp với danh sách chỉ đọc; `Collectors.toCollection(...)` phù hợp khi cần một collection cụ thể và có hành vi sửa đổi đã biết. Cách chọn tường minh giúp mã ổn định khi thay đổi phiên bản JDK và dễ hiểu hơn với người bảo trì.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Collectors.html)
- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors.toList(), toUnmodifiableList() và toCollection() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [List – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
