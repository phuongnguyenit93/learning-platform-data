# Xử lý phần tử `null` khi dùng `Stream.toList()`

`Stream.toList()` có thể giữ phần tử `null` trong danh sách kết quả. Danh sách trả về vẫn là *unmodifiable*: bạn có thể đọc phần tử `null`, nhưng không thể thêm, xóa hoặc thay thế phần tử trong danh sách. Đây là điểm khác biệt cần nhớ khi so sánh với `List.of()`, `List.copyOf()` và `Collectors.toUnmodifiableList()`, vì các API đó từ chối `null`.

Do đó, có hai quyết định riêng khi thiết kế pipeline: chương trình có chấp nhận dữ liệu `null` hay không, và danh sách kết quả có cần sửa đổi cấu trúc hay không. Đừng suy ra chính sách null từ tính unmodifiable của danh sách.

## 1. `Stream.toList()` giữ được phần tử `null`

Ví dụ sau tạo stream có một phần tử `null` ở giữa:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("An", null, "Chi").toList();

System.out.println(names);       // [An, null, Chi]
System.out.println(names.size()); // 3
System.out.println(names.get(1) == null); // true

names.add("Dung"); // UnsupportedOperationException
```

`toList()` giữ nguyên phần tử null như một phần tử của kết quả. Danh sách vẫn có kích thước 3 và phần tử null chiếm một vị trí. Lời gọi `add()` thất bại vì danh sách không sửa đổi được, không phải vì danh sách chứa null.

Nếu stream chỉ có một phần tử null, hãy viết rõ kiểu phần tử để tránh nhầm lẫn với đối số mảng varargs của `Stream.of`:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> oneNull = Stream.of((String) null).toList();
System.out.println(oneNull); // [null]
```

Phép ép kiểu `(String) null` làm rõ rằng null là một phần tử kiểu `String`. Trong trường hợp muốn biểu diễn một giá trị có thể vắng mặt bằng stream gồm không hoặc một phần tử, `Stream.ofNullable(value)` là lựa chọn rõ nghĩa hơn.

## 2. So sánh chính sách null của các API tạo List

Các API sau đều có thể tạo danh sách không sửa đổi được, nhưng khác nhau về việc chấp nhận null:

| API | Có nhận phần tử `null`? | Khả năng sửa đổi cấu trúc | Ghi chú |
| --- | --- | --- | --- |
| `stream.toList()` | Có | Không | Thu các phần tử stream; giữ null nếu pipeline phát ra null. |
| `List.of(...)` | Không | Không | Ném `NullPointerException` nếu một đối số phần tử là null. |
| `List.copyOf(collection)` | Không | Không | Ném `NullPointerException` nếu collection đầu vào chứa null. |
| `stream.collect(Collectors.toUnmodifiableList())` | Không | Không | Collector ghi rõ từ chối null và ném `NullPointerException`. |
| `stream.collect(Collectors.toList())` | Hợp đồng không quy định rõ chính sách null; implementation OpenJDK hiện tại nhận null | Không có bảo đảm mutable hay unmodifiable | Không dùng nó để diễn đạt một chính sách null hoặc mutability cụ thể. |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Có | Có | Chọn `ArrayList` tường minh khi cần danh sách mutable có thể chứa null. |

Ví dụ, `List.of()` từ chối null ngay khi tạo danh sách:

```java
import java.util.List;

List<String> names = List.of("An", null, "Chi");
// Ném NullPointerException ngay tại lời gọi List.of(...)
```

`List.copyOf()` cũng kiểm tra phần tử của collection đầu vào:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("An", null, "Chi").toList();
List<String> copy = List.copyOf(values);
// Ném NullPointerException vì values có phần tử null
```

Collector `toUnmodifiableList()` cũng từ chối null theo hợp đồng:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> values = Stream.of("An", null, "Chi")
    .collect(Collectors.toUnmodifiableList());
// Ném NullPointerException khi collector nhận phần tử null
```

Nếu muốn một danh sách vừa mutable vừa cho phép null, hãy chọn collection cụ thể:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> values = Stream.of("An", null, "Chi")
    .collect(Collectors.toCollection(ArrayList::new));

values.add(null); // Hợp lệ với ArrayList
values.set(1, "Bình"); // Hợp lệ
```

`Collectors.toList()` không bảo đảm kiểu triển khai, khả năng sửa đổi, tuần tự hóa hoặc thread-safety. Một số JDK thường trả về `ArrayList`, nhưng nếu yêu cầu cụ thể là danh sách mutable và chấp nhận null, `toCollection(ArrayList::new)` thể hiện hợp đồng cần dùng rõ ràng hơn.

## 3. Phân biệt stream rỗng với stream có một phần tử `null`

Hai trường hợp sau khác nhau:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> empty = Stream.<String>empty().toList();
List<String> containingNull = Stream.of((String) null).toList();

System.out.println(empty);            // []
System.out.println(containingNull);  // [null]
System.out.println(empty.size());   // 0
System.out.println(containingNull.size()); // 1
```

Stream rỗng không phát ra phần tử nào. Stream có một phần tử null vẫn phát ra một phần tử, chỉ là giá trị phần tử đó không tham chiếu tới object nào.

Khi nguồn là một biến có thể null và nghiệp vụ muốn coi null như không có dữ liệu, dùng `Stream.ofNullable()`:

```java
import java.util.List;
import java.util.stream.Stream;

String optionalName = null;

List<String> names = Stream.ofNullable(optionalName).toList();
System.out.println(names); // []
```

`Stream.ofNullable(value)` tạo stream một phần tử nếu `value` khác null, và stream rỗng nếu `value` là null. Phương thức này có từ Java 9 và vẫn dùng được trong Java hiện đại.

Với một stream chứa nhiều giá trị có thể null, có thể dùng `flatMap(Stream::ofNullable)` để bỏ các giá trị null:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("An", null, "Bình", null, "Chi")
    .flatMap(Stream::ofNullable)
    .toList();

System.out.println(names); // [An, Bình, Chi]
```

## 4. Lọc null hay giữ null trong kết quả?

Quyết định này phụ thuộc vào ý nghĩa nghiệp vụ của null.

**Lọc null khi phần tử vắng mặt không có ích cho kết quả.** Dùng `Objects.nonNull` để giữ các giá trị khác null:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

List<String> names = Stream.of("An", null, "Bình", null, "Chi")
    .filter(Objects::nonNull)
    .toList();

System.out.println(names); // [An, Bình, Chi]
```

**Giữ null khi vị trí hoặc ý nghĩa “chưa có giá trị” cần được bảo toàn.** Ví dụ, danh sách kết quả được căn theo các dòng dữ liệu nguồn, và null biểu thị trường chưa được nhập:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> phoneNumbers = Stream.of(
    "0900000001",
    null,
    "0900000003"
).toList();

System.out.println(phoneNumbers);
// [0900000001, null, 0900000003]
```

Nếu lọc null trong trường hợp này, vị trí của các bản ghi sẽ không còn tương ứng với nguồn. Hãy chỉ lọc khi nghiệp vụ xác định rõ có thể bỏ các phần tử vắng mặt.

**Chuyển null thành một giá trị biểu diễn rõ ràng.** Khi tạo dữ liệu hiển thị, có thể ánh xạ null thành nhãn:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> displayNames = Stream.of("An", null, "Chi")
    .map(name -> name == null ? "(chưa nhập)" : name)
    .toList();

System.out.println(displayNames); // [An, (chưa nhập), Chi]
```

## 5. Những thao tác có thể ném `NullPointerException`

`toList()` có thể giữ null, nhưng điều đó không có nghĩa mọi operation trong pipeline đều xử lý null. Lỗi thường xuất hiện khi code dereference null, truyền null vào API cấm null hoặc yêu cầu so sánh null bằng comparator không hỗ trợ.

### Gọi phương thức trên phần tử null

```java
import java.util.List;
import java.util.stream.Stream;

List<String> normalized = Stream.of(" An ", null, " Chi ")
    .map(String::trim)
    .toList();
// Ném NullPointerException khi map gọi trim() trên null
```

Vì stream là lazy, intermediate operation `map()` chỉ mô tả pipeline. Exception phát sinh khi terminal operation `toList()` kích hoạt việc duyệt phần tử và hàm ánh xạ gặp null.

Nếu null có thể xuất hiện, hãy lọc trước khi dereference hoặc ánh xạ null thành giá trị thay thế:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

List<String> normalized = Stream.of(" An ", null, " Chi ")
    .filter(Objects::nonNull)
    .map(String::trim)
    .toList();
```

### Sắp xếp với comparator không chấp nhận null

Sắp xếp theo natural order không xác định được vị trí của null. Nếu muốn giữ null trong kết quả đã sắp xếp, hãy dùng `Comparator.nullsFirst()` hoặc `Comparator.nullsLast()`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

List<String> sorted = Stream.of("Chi", null, "An", "Bình")
    .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
    .toList();

System.out.println(sorted); // [An, Bình, Chi, null]
```

`nullsFirst()` đặt null trước các giá trị khác; `nullsLast()` đặt null sau các giá trị khác. Nếu không muốn giữ null, hãy lọc chúng trước khi gọi `sorted()`.

### Chuyển sang API từ chối null

Một pipeline có thể chạy thành công đến `toList()` nhưng thất bại khi kết quả được chuyển sang API khác:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("An", null, "Chi").toList();
List<String> safeValues = List.copyOf(values);
// Ném NullPointerException tại List.copyOf(...)
```

Nếu đích đến yêu cầu không có null, hãy xác thực hoặc làm sạch dữ liệu trước khi gọi API đó. Đừng đợi exception xuất hiện ở một bước xa hơn trong luồng xử lý.

## 6. Chủ động xác thực khi null là dữ liệu không hợp lệ

Có hai cách phổ biến tùy theo yêu cầu:

**Loại bỏ phần tử null:**

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

List<String> validNames = Stream.of("An", null, "Chi")
    .filter(Objects::nonNull)
    .toList();
```

**Dừng pipeline ngay khi gặp null:**

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

List<String> validatedNames = Stream.of("An", null, "Chi")
    .map(name -> Objects.requireNonNull(name, "Tên không được null"))
    .toList();
```

`filter(Objects::nonNull)` có nghĩa là bỏ qua dữ liệu null. `Objects.requireNonNull(...)` có nghĩa là null vi phạm hợp đồng và phải báo lỗi. Chọn cách phù hợp với nghiệp vụ; không dùng filter để che giấu dữ liệu đầu vào sai nếu chương trình cần phát hiện lỗi.

Nếu một trường có thể vắng mặt một cách hợp lệ, hãy cân nhắc biểu diễn sự vắng mặt rõ ràng bằng `Optional<T>` trong API phù hợp, thay vì để người gọi phải đoán ý nghĩa của null. `Optional` không chứa null bên trong; `Optional.empty()` biểu diễn trường hợp không có giá trị.

## 7. Checklist khi dùng `Stream.toList()` với dữ liệu nullable

- Nhớ rằng `Stream.toList()` giữ được null nhưng danh sách kết quả không sửa đổi được.
- Không nhầm stream rỗng `[]` với danh sách có một phần tử null `[null]`.
- Dùng `Stream.ofNullable(value)` nếu null của một nguồn đơn lẻ nên trở thành stream rỗng.
- Dùng `filter(Objects::nonNull)` nếu nghiệp vụ cho phép bỏ phần tử null.
- Dùng `Objects.requireNonNull(...)` nếu null phải bị xem là lỗi dữ liệu.
- Dùng `Comparator.nullsFirst()` hoặc `nullsLast()` nếu cần sắp xếp mà vẫn giữ null.
- Kiểm tra các API nhận kết quả tiếp theo; `List.of`, `List.copyOf` và `Collectors.toUnmodifiableList` từ chối null.
- Nếu cần List mutable và cho phép null, chọn rõ `Collectors.toCollection(ArrayList::new)`.

`Stream.toList()` tách biệt hai đặc tính: danh sách không sửa đổi được và phần tử có thể là null. Khi thiết kế pipeline, hãy xác định null có ý nghĩa gì trong dữ liệu, xử lý nó tại nơi phù hợp, rồi chọn API tạo collection theo đúng yêu cầu về null và khả năng sửa đổi.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Stream.toList() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Collectors.toUnmodifiableList() và toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [List.of() và List.copyOf() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
- [Stream.ofNullable() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#ofNullable(T))
- [Objects.requireNonNull() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String))
- [Hidden gems in Java 16 and Java 17 – Oracle Java Magazine](https://blogs.oracle.com/content/published/api/v1.1/assets/CONT037630B9803E46879C3D1AC9C12860E0/native?cb=_cache_ee5b&channelToken=4d6a6a00a153413e9a7a992032379dbf)
