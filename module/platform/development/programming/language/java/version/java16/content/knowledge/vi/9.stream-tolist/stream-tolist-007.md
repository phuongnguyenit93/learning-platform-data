# So sánh `Stream.toList()` với `Collectors.toUnmodifiableList()` về null

`Stream.toList()` và `Collectors.toUnmodifiableList()` đều tạo ra danh sách không sửa đổi được, nhưng chính sách đối với phần tử `null` khác nhau. `Stream.toList()` giữ các phần tử mà stream phát ra, kể cả `null`. `Collectors.toUnmodifiableList()` từ chối `null` và ném `NullPointerException` nếu collector nhận phần tử này.

Khác biệt đó quyết định API nào phù hợp với dữ liệu. Nếu `null` là một giá trị cần được giữ lại, dùng `Stream.toList()`. Nếu `null` vi phạm hợp đồng dữ liệu và cần bị từ chối ngay khi thu thập, dùng `Collectors.toUnmodifiableList()`. Cả hai đều không cho phép thay đổi cấu trúc danh sách sau khi tạo.

## 1. Hai API có cùng tính unmodifiable nhưng khác chính sách null

Ví dụ với stream phát ra một phần tử null:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> withNull = Stream.of("An", null, "Chi").toList();
System.out.println(withNull); // [An, null, Chi]

List<String> withoutNull = Stream.of("An", null, "Chi")
    .collect(Collectors.toUnmodifiableList());
// Ném NullPointerException khi collector nhận null
```

Hai pipeline có cùng nguồn dữ liệu. Pipeline đầu hoàn tất và giữ null trong kết quả. Pipeline thứ hai thất bại vì collector có hợp đồng từ chối null.

| Tiêu chí | `stream.toList()` | `stream.collect(Collectors.toUnmodifiableList())` |
| --- | --- | --- |
| Có từ phiên bản | Java 16 | Java 10 |
| Kết quả | `List<T>` unmodifiable | `List<T>` unmodifiable |
| Phần tử `null` | Được giữ trong kết quả | Bị từ chối, ném `NullPointerException` |
| Mutator như `add`, `set`, `remove` | Ném `UnsupportedOperationException` | Ném `UnsupportedOperationException` |
| Encounter order | Giữ nếu stream có encounter order | Tích lũy theo encounter order nếu stream có thứ tự |
| Mục đích thể hiện | Thu phần tử stream thành danh sách không sửa đổi được | Thu danh sách không sửa đổi được và xác nhận không có null |

Điểm cần nhớ: *unmodifiable* nói về khả năng thay đổi danh sách; chính sách null là một thuộc tính riêng. Không thể suy ra một danh sách không sửa đổi được thì nhất thiết phải từ chối null.

## 2. `Stream.toList()` giữ null trong kết quả

`Stream.toList()` thu các phần tử mà pipeline phát ra. Nếu stream phát ra một phần tử null, phần tử đó vẫn có mặt trong danh sách:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("Java", null, "Stream").toList();

System.out.println(values.size()); // 3
System.out.println(values.get(1) == null); // true
System.out.println(values); // [Java, null, Stream]
```

Danh sách này không sửa đổi được. Bạn có thể đọc phần tử null, kiểm tra `value == null`, duyệt danh sách hoặc tạo stream mới từ danh sách. Những thao tác thay đổi cấu trúc như `add`, `remove`, `set` và `clear` vẫn ném `UnsupportedOperationException`:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("Java", null, "Stream").toList();
values.add("API"); // UnsupportedOperationException
```

Nếu cần một stream có đúng một phần tử null, hãy định kiểu rõ ràng:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> oneNull = Stream.of((String) null).toList();
System.out.println(oneNull); // [null]
```

Điều này khác với stream rỗng:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> empty = Stream.<String>empty().toList();
System.out.println(empty); // []
```

Stream rỗng không phát ra phần tử; stream một phần tử null phát ra một phần tử có giá trị null.

## 3. `Collectors.toUnmodifiableList()` từ chối null

Hợp đồng của `Collectors.toUnmodifiableList()` quy định collector không chấp nhận giá trị null. Khi một phần tử null được chuyển tới collector, quá trình thu thập ném `NullPointerException`:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", null, "Bình")
    .collect(Collectors.toUnmodifiableList());
// NullPointerException
```

Đây là lựa chọn phù hợp khi danh sách kết quả theo hợp đồng phải chứa các giá trị khác null. Collector vừa thu thập dữ liệu vừa thực thi chính sách null đã được API quy định.

Không nên xem exception này như một cách thay thế cho việc xác thực dữ liệu ở biên hệ thống. Nếu cần thông báo lỗi cụ thể, ghi nhận bản ghi vi phạm hoặc xử lý theo quy tắc nghiệp vụ, hãy xác thực trước khi gọi collector.

## 4. Phân biệt lỗi do collector với lỗi trong pipeline

`NullPointerException` có thể phát sinh ở nhiều vị trí. Cần xác định null bị từ chối bởi collector hay bị sử dụng sai trong một intermediate operation.

**Trường hợp collector từ chối null:**

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> values = Stream.of("An", null, "Chi")
    .collect(Collectors.toUnmodifiableList());
// NullPointerException khi collector nhận phần tử null
```

**Trường hợp mapper dereference null trước khi collector nhận phần tử:**

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> normalized = Stream.of(" An ", null, " Chi ")
    .map(String::trim)
    .collect(Collectors.toUnmodifiableList());
// NullPointerException khi String::trim được gọi trên null
```

Trong ví dụ thứ hai, exception xảy ra ở hàm ánh xạ `String::trim`. Collector chưa nhận được giá trị null từ mapper. Đổi terminal operation sang `toList()` cũng không khắc phục lỗi này, vì mapper vẫn phải gọi `trim()` trên null.

Nếu muốn bỏ qua null trước khi gọi phương thức trên phần tử, lọc chúng trước:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> normalized = Stream.of(" An ", null, " Chi ")
    .filter(Objects::nonNull)
    .map(String::trim)
    .collect(Collectors.toUnmodifiableList());

System.out.println(normalized); // [An, Chi]
```

## 5. Xử lý dữ liệu trước khi dùng collector từ chối null

Khi nghiệp vụ không cho phép null, có thể chọn cách xử lý theo yêu cầu.

**Lọc phần tử null:** phù hợp khi null có thể được bỏ qua mà không làm sai ý nghĩa kết quả.

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", null, "Bình", null, "Chi")
    .filter(Objects::nonNull)
    .collect(Collectors.toUnmodifiableList());

System.out.println(names); // [An, Bình, Chi]
```

**Từ chối null với thông báo rõ ràng:** phù hợp khi null là dữ liệu sai và cần báo lỗi tại bước xác thực.

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", null, "Bình")
    .map(name -> Objects.requireNonNull(name, "Tên không được null"))
    .collect(Collectors.toUnmodifiableList());
```

Ở đây `Objects.requireNonNull` ném exception có thông điệp được chỉ định trước khi collector nhận phần tử. Nếu không có null, collector tiếp tục tạo danh sách unmodifiable.

**Chuyển null thành giá trị miền nghiệp vụ:** phù hợp khi cần bảo toàn số lượng và vị trí phần tử nhưng không muốn null xuất hiện trong kết quả.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> displayNames = Stream.of("An", null, "Chi")
    .map(name -> name == null ? "(chưa nhập)" : name)
    .collect(Collectors.toUnmodifiableList());

System.out.println(displayNames); // [An, (chưa nhập), Chi]
```

Không chọn cách lọc chỉ để làm collector hết lỗi nếu null biểu thị một trạng thái cần giữ lại. Chính sách phải xuất phát từ ý nghĩa dữ liệu.

## 6. Nếu cần giữ null nhưng vẫn muốn collection mutable

`Stream.toList()` giữ null nhưng trả về danh sách unmodifiable. Nếu vừa cần giữ null vừa cần thêm, xóa hoặc thay thế phần tử, hãy chỉ định collection mutable:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> editable = Stream.of("An", null, "Chi")
    .collect(Collectors.toCollection(ArrayList::new));

editable.add("Dung"); // Hợp lệ
editable.set(1, "Bình"); // Hợp lệ
System.out.println(editable); // [An, Bình, Chi, Dung]
```

`Collectors.toCollection(ArrayList::new)` làm rõ cả hai yêu cầu: collection kết quả là `ArrayList` mutable và `ArrayList` chấp nhận null. `Collectors.toList()` không cam kết mutability hay lớp triển khai, nên không nên dùng nó chỉ vì một JDK hiện tại thường trả về `ArrayList`.

## 7. Chọn API theo hợp đồng dữ liệu

| Yêu cầu | Cách thu thập phù hợp | Kết quả |
| --- | --- | --- |
| Giữ null, chỉ cần đọc danh sách | `stream.toList()` | Unmodifiable, giữ null. |
| Từ chối null, chỉ cần đọc danh sách | `collect(Collectors.toUnmodifiableList())` | Unmodifiable, ném NPE khi nhận null. |
| Bỏ null, chỉ cần đọc danh sách | `filter(Objects::nonNull).toList()` | Unmodifiable, không còn null. |
| Báo lỗi null với thông điệp cụ thể | `map(value -> Objects.requireNonNull(value, "Tên không được null")).collect(Collectors.toUnmodifiableList())` | Ném NPE tại bước xác thực nếu gặp null. |
| Giữ null và cần sửa danh sách | `collect(Collectors.toCollection(ArrayList::new))` | Mutable `ArrayList`, cho phép null. |
| Không nhận null và cần sửa danh sách | Xác thực/lọc trước rồi `collect(Collectors.toCollection(ArrayList::new))` | Mutable `ArrayList`, dữ liệu được làm sạch theo chính sách đã chọn. |

Khi thiết kế API, ghi rõ hai thuộc tính riêng trong tài liệu phương thức: danh sách trả về có sửa đổi được không và phần tử null có được phép không. Kiểu trả về `List<T>` không thể hiện đầy đủ hai điều đó.

## 8. Ghi nhớ

- `Stream.toList()` có từ Java 16, trả về danh sách unmodifiable và giữ null nếu stream phát ra null.
- `Collectors.toUnmodifiableList()` có từ Java 10, trả về danh sách unmodifiable nhưng từ chối null bằng `NullPointerException`.
- Cả hai đều ném `UnsupportedOperationException` khi gọi mutator trên danh sách kết quả.
- NPE có thể xảy ra trong mapper trước khi collector nhận dữ liệu; hãy phân biệt nguyên nhân theo stack trace.
- Lọc null khi nghiệp vụ cho phép bỏ phần tử; dùng `requireNonNull` khi null vi phạm hợp đồng.
- Nếu cần mutable và cho phép null, chỉ định `ArrayList` bằng `Collectors.toCollection(ArrayList::new)`.

Hãy chọn API dựa trên cả chính sách null và yêu cầu mutability. `Stream.toList()` phù hợp khi muốn giữ nguyên các phần tử stream trong một danh sách không sửa đổi được; `Collectors.toUnmodifiableList()` phù hợp khi null phải bị từ chối ngay trong bước thu thập.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors.toUnmodifiableList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList())
- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
