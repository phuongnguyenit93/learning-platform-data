# Dùng toUnmodifiableList và toUnmodifiableSet

## 1. Vì sao cần thu thập thành Collection không thể sửa đổi?

Trong **Java Stream API**, `filter`, `map` và các thao tác trung gian khác mô tả một pipeline xử lý dữ liệu theo cách khai báo. Đến thao tác kết thúc `collect`, dữ liệu mới được gom vào một kết quả như `List`, `Set` hoặc `Map`.

Một số kết quả được dùng làm **danh sách tham chiếu**, **tập mã hợp lệ** hoặc **dữ liệu trả về từ tầng dịch vụ**. Nếu code nhận kết quả có thể tự ý thêm hoặc xóa phần tử, quy tắc nghiệp vụ dễ bị phá vỡ. Hai collector sau giúp biểu đạt rằng **cấu trúc Collection kết quả không được chỉnh sửa**:

- `Collectors.toUnmodifiableList()`: tạo một danh sách không cho phép chỉnh sửa, **giữ phần tử trùng lặp** và bảo toàn encounter order nếu Stream có thứ tự.
- `Collectors.toUnmodifiableSet()`: tạo một tập không cho phép chỉnh sửa, **loại phần tử trùng theo `equals`/`hashCode`**, không cam kết thứ tự duyệt.

Ví dụ:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> codes = List.of("A", "B", "A", "C");

List<String> asList = codes.stream()
        .collect(Collectors.toUnmodifiableList());

Set<String> asSet = codes.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(asList);       // [A, B, A, C]
System.out.println(asSet.size()); // 3
```

`asList` giữ bốn phần tử theo thứ tự; `asSet` chỉ chứa ba giá trị khác nhau `A`, `B`, `C`. Cả hai đều từ chối những thao tác như `add`, `remove` hoặc `clear`.

Bài học thuộc chương **Thu thập thành Collection**. Sau khi học, bạn có thể chọn đúng collector theo nhu cầu về thứ tự và trùng lặp; xử lý `null` trước khi thu thập; phân biệt kết quả unmodifiable với bất biến sâu; và dùng các collector này trong pipeline tuần tự, song song và báo cáo nghiệp vụ.

**Phiên bản Java:** cả `Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()` có từ **Java 10**. Ví dụ hoàn chỉnh trong bài dùng Java 17+ để có `record` và `Stream.toList()`. Không cần Java 17 nếu chỉ sử dụng hai collector trên.

## 2. Kiểu trả về và vị trí trong collect

Hai phương thức của lớp `java.util.stream.Collectors` có chữ ký:

```java
public static <T> Collector<T, ?, List<T>> toUnmodifiableList()

public static <T> Collector<T, ?, Set<T>> toUnmodifiableSet()
```

Đối số `Collector<T, A, R>` mô tả cách gom từng phần tử `T` vào một trạng thái tích lũy `A` rồi tạo kết quả `R`. Ở hai chữ ký trên, trạng thái tích lũy được ẩn bởi dấu `?`, còn kết quả lần lượt là `List<T>` và `Set<T>`.

Sử dụng qua terminal operation `collect(Collector)`:

```java
List<String> labels = List.of("  Java  ", "Stream", "Java")
        .stream()
        .map(String::strip)
        .collect(Collectors.toUnmodifiableList());

Set<String> distinctLabels = List.of("  Java  ", "Stream", "Java")
        .stream()
        .map(String::strip)
        .collect(Collectors.toUnmodifiableSet());
```

Pipeline hoạt động theo logic:

```text
Nguồn Stream<T>
     |
 filter / map             Thao tác trung gian lazy
     |
 collect(...)             Thao tác kết thúc
     |
 +--------------------+-----------------------+
 |                    |                       |
 toUnmodifiableList() |                toUnmodifiableSet()
 |                    |                       |
 List<T>              |                    Set<T>
 giữ trùng + thứ tự   |              loại trùng, không hứa thứ tự
 không sửa cấu trúc   |              không sửa cấu trúc
 +--------------------+-----------------------+
```

`collect` **kích hoạt việc duyệt Stream**. Sau khi terminal operation kết thúc, Stream đó không thể dùng lại; nếu cần một kết quả List và một kết quả Set từ cùng nguồn, hãy tạo hai pipeline riêng hoặc thiết kế phép thu thập kết hợp khi thực sự cần một lượt duyệt.

## 3. toUnmodifiableList: giữ thứ tự và giữ phần tử trùng

Khi dữ liệu biểu diễn **chuỗi bước**, **danh sách giao dịch** hoặc **lịch sử xuất hiện**, một phần tử lặp lại vẫn có thể mang ý nghĩa. `toUnmodifiableList` giữ nguyên các phần tử đó.

```java
List<String> events = List.of("LOGIN", "VIEW", "VIEW", "LOGOUT");

List<String> history = events.stream()
        .filter(event -> !event.isBlank())
        .collect(Collectors.toUnmodifiableList());

System.out.println(history); // [LOGIN, VIEW, VIEW, LOGOUT]
```

Với Stream có **encounter order** như `List.stream()`, List kết quả giữ thứ tự gặp phần tử. Nếu nguồn không có thứ tự, ví dụ một số `Set` hoặc pipeline gọi `unordered()`, collector này không thể tự suy ra thứ tự nghiệp vụ và không bảo đảm một thứ tự có ý nghĩa.

### Không thể sửa cấu trúc List đã thu thập

```java
List<Integer> scores = List.of(8, 9, 7)
        .stream()
        .collect(Collectors.toUnmodifiableList());

// Mỗi thao tác bên dưới đều ném UnsupportedOperationException.
// scores.add(10);
// scores.remove(0);
// scores.set(0, 10);
// scores.clear();
```

Tuy nhiên, **đọc dữ liệu** vẫn bình thường: `scores.size()`, `scores.get(0)`, `scores.stream()` và duyệt bằng vòng lặp vẫn hợp lệ.

Điểm cần phân biệt là kết quả unmodifiable không có nghĩa tất cả đối tượng nằm bên trong đều bất biến. Nếu List chứa một đối tượng mutable, code vẫn có thể gọi phương thức làm thay đổi trạng thái của đối tượng đó. Mục 8 sẽ minh họa rõ.

### Danh sách mới có phụ thuộc thay đổi nguồn không?

```java
List<String> mutableSource =
        new java.util.ArrayList<>(List.of("A", "B"));

List<String> locked = mutableSource.stream()
        .collect(Collectors.toUnmodifiableList());

mutableSource.add("C");
System.out.println(mutableSource); // [A, B, C]
System.out.println(locked);        // [A, B]
```

Kết quả `locked` đã được thu thập; nó không phải view được liên kết với Collection nguồn. **Các tham chiếu đối tượng phần tử** vẫn có thể được chia sẻ nếu phần tử thuộc kiểu mutable.

## 4. toUnmodifiableSet: bảo đảm tính duy nhất theo equals/hashCode

Nếu dữ liệu cần biểu diễn **tập mã duy nhất**, **các vai trò đã cấp** hoặc **danh sách tính năng đã bật**, một `Set` sẽ phù hợp hơn danh sách có thể chứa phần tử trùng.

```java
List<String> permissions = List.of(
        "READ", "WRITE", "READ", "EXPORT", "WRITE"
);

Set<String> uniquePermissions = permissions.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(uniquePermissions.size());         // 3
System.out.println(uniquePermissions.contains("READ")); // true
```

Đừng dựa vào kết quả `System.out.println(uniquePermissions)` có cùng thứ tự với nguồn. `toUnmodifiableSet` không hứa giữ encounter order, nên ví dụ kiểm tra **kích thước và sự tồn tại của phần tử**.

### Trùng lặp theo quy tắc nào?

Set dùng cơ chế bình đẳng của phần tử: đối với kiểu đối tượng thông thường, đó là `equals` và `hashCode`. Với `String`, hai chuỗi có cùng nội dung là bằng nhau.

Với đối tượng tự định nghĩa, hai đối tượng khác tham chiếu vẫn có thể bị coi là trùng nếu có quy tắc bình đẳng tương ứng. Ví dụ `record` tự sinh `equals`/`hashCode` dựa trên các thành phần:

```java
record Tag(String code, String label) {}

List<Tag> input = List.of(
        new Tag("T1", "Java"),
        new Tag("T1", "Java"),
        new Tag("T1", "Programming")
);

Set<Tag> tags = input.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(tags.size()); // 2
```

Hai entry đầu bằng nhau nên bị loại trùng; entry thứ ba khác `label`, vì vậy vẫn là một phần tử riêng. Nếu nghiệp vụ định nghĩa "trùng" **chỉ theo mã `code`**, phải chuẩn hóa hoặc lựa chọn khóa so sánh trước khi thu thập. `toUnmodifiableSet` không nhận comparator hay hàm xác định khóa tùy chỉnh.

### Phần tử nào được giữ khi các đối tượng bằng nhau?

Nếu các phần tử **bằng nhau theo `equals`** nhưng là các đối tượng khác nhau, API cho phép giữ một phần tử **bất kỳ** trong nhóm trùng. Không được dựa vào việc giữ "bản đầu tiên" hoặc "bản cuối cùng", nhất là trong pipeline song song.

Khi cần chọn bản ghi mới nhất theo ID hoặc ưu tiên dữ liệu có trạng thái tốt nhất, hãy biểu diễn quy tắc chọn bằng `toMap` có hàm merge, `groupingBy` hoặc một phép xử lý riêng, sau đó mới tạo đầu ra không sửa được.

## 5. toUnmodifiableList và toUnmodifiableSet khác nhau thế nào?

| Thuộc tính | `toUnmodifiableList()` | `toUnmodifiableSet()` |
| --- | --- | --- |
| Kiểu kết quả | `List<T>` | `Set<T>` |
| Giữ phần tử trùng | Có | Không |
| Encounter order | Bảo toàn khi Stream có thứ tự | Không cam kết |
| Lấy phần tử theo chỉ số | Có, qua `get(index)` | Không có chỉ số |
| Kiểm tra thuộc tập | `contains` được hỗ trợ | `contains` được hỗ trợ; phù hợp ngữ nghĩa tập hợp |
| Cho phép `null` | Không | Không |
| Cho phép `add`/`remove`/`clear` | Không | Không |
| Bảo đảm phần tử bên trong bất biến sâu | Không | Không |
| Đảm bảo kiểu triển khai cụ thể | Không | Không |

Cả hai collector đều tạo kết quả **unmodifiable**, nhưng không hứa kiểu triển khai như `ArrayList`, `HashSet`, `LinkedHashSet`, cũng không hứa khả năng tuần tự hóa (`Serializable`). Để code có thể thay thế triển khai, hãy lập trình với interface `List` hoặc `Set`.

Nếu cần **thứ tự và tính duy nhất đồng thời**, có thể xử lý trên Stream có thứ tự trước khi thu thập thành List:

```java
List<String> orderedUnique = List.of("A", "B", "A", "C")
        .stream()
        .distinct()
        .collect(Collectors.toUnmodifiableList());

System.out.println(orderedUnique); // [A, B, C]
```

Với Stream **có thứ tự**, `distinct()` giữ lần xuất hiện đầu tiên của mỗi giá trị bằng nhau. Danh sách sau đó giữ thứ tự đã chọn. Nếu cần hẳn một Set có thứ tự lặp được bảo đảm bởi thiết kế Collection, `LinkedHashSet` là lựa chọn phù hợp; có thể khóa thao tác sửa sau khi thu thập như ở mục 7.

## 6. Chính sách với null: cả hai collector đều từ chối

Đây là khác biệt quan trọng với một số cách thu thập Collection khác: **`toUnmodifiableList` và `toUnmodifiableSet` không chấp nhận phần tử `null`**. Nếu Stream có phần tử `null`, terminal operation sẽ thất bại với `NullPointerException`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> data = Arrays.asList("A", null, "B");

// SAI: kết quả mong muốn chứa null.
// List<String> invalid = data.stream()
//         .collect(Collectors.toUnmodifiableList());
// Ném NullPointerException.
```

Điều tương tự xảy ra với `toUnmodifiableSet`. Trước khi thu thập, hãy quyết định `null` là dữ liệu lỗi, phần tử cần bỏ qua hay giá trị thiếu cần thay thế.

### Bỏ qua phần tử null

```java
import java.util.Objects;

List<String> nonNull = data.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());

System.out.println(nonNull); // [A, B]
```

### Thay thế null bằng giá trị tường minh

```java
List<String> normalized = data.stream()
        .map(value -> value == null ? "UNKNOWN" : value)
        .collect(Collectors.toUnmodifiableSet());

System.out.println(normalized.contains("UNKNOWN")); // true
```

Với dữ liệu bắt buộc, việc thay `null` bằng `"UNKNOWN"` có thể che giấu lỗi. Hãy kiểm tra và báo lỗi trước khi thực hiện pipeline nếu quy tắc nghiệp vụ yêu cầu.

### Phân biệt với Stream.toList()

`Stream.toList()` (Java 16+) cũng trả về một **List không cho phép chỉnh sửa**. Tuy nhiên, hai API không có cùng toàn bộ hợp đồng: `Collectors.toUnmodifiableList()` quy định rõ **từ chối `null`**, còn `Stream.toList()` trên các JDK hiện hành cho phép kết quả chứa `null`.

```java
List<String> maybeNull = java.util.Arrays.asList("A", null).stream()
        .toList(); // Có thể chứa null; đầu ra vẫn unmodifiable.
```

Nếu muốn bảo đảm dữ liệu không có `null`, đừng chỉ đổi terminal operation rồi hy vọng. Hãy thể hiện chính sách bằng kiểm tra, lọc hoặc collector có ràng buộc `null` rõ ràng.

## 7. So sánh với các cách thu thập Collection khác

Chữ "List" hay "Set" trong tên collector **chưa đủ để kết luận khả năng chỉnh sửa kết quả**.

| Cách thu thập | Kết quả | Cam kết về chỉnh sửa |
| --- | --- | --- |
| `collect(Collectors.toUnmodifiableList())` | `List<T>`, giữ trùng, giữ encounter order | **Không cho chỉnh sửa** |
| `collect(Collectors.toUnmodifiableSet())` | `Set<T>`, loại trùng | **Không cho chỉnh sửa** |
| `stream.toList()` | `List<T>`, giữ encounter order | **Không cho chỉnh sửa**, Java 16+ |
| `collect(Collectors.toList())` | `List<T>` | **Không cam kết** kiểu triển khai hay khả năng chỉnh sửa |
| `collect(Collectors.toSet())` | `Set<T>` | **Không cam kết** kiểu triển khai, khả năng chỉnh sửa hay thứ tự |
| `collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` | Có thể thêm/xóa phần tử |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet<T>` | Có thể sửa; lặp theo thứ tự chèn |
| `List.copyOf(collection)` / `Set.copyOf(collection)` | Bản sao không cho chỉnh sửa | Java 10+; từ chối `null` |

Nếu cần một danh sách có thể thay đổi có chủ đích, yêu cầu trực tiếp kiểu Collection:

```java
List<String> editable = List.of("A", "B").stream()
        .collect(Collectors.toCollection(java.util.ArrayList::new));

editable.add("C"); // Hợp lệ.
```

Nếu cần **Set giữ thứ tự chèn** rồi ngăn code sử dụng kết quả sửa nó:

```java
import java.util.Collections;
import java.util.LinkedHashSet;

Set<String> orderedUnique = List.of("A", "B", "A", "C").stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(LinkedHashSet::new),
                Collections::unmodifiableSet
        ));

System.out.println(orderedUnique); // [A, B, C] theo thứ tự chèn.
```

`Collections.unmodifiableSet` tạo **view không cho phép sửa qua view đó** trên Set được truyền vào. Nếu còn tham chiếu đến Set gốc, thay đổi qua tham chiếu ấy vẫn hiện trong view. Trong pipeline trên, Set trung gian được tạo nội bộ và không bị công bố ở nơi khác, nên cách viết phù hợp với mục tiêu ngăn người dùng kết quả sửa cấu trúc.

Trái lại, `toUnmodifiableSet` đã diễn đạt trực tiếp việc thu thập thành một Set không cho sửa, nhưng **không hứa thứ tự**. Hãy ưu tiên cách đơn giản khi thứ tự không có ý nghĩa nghiệp vụ.

### Khác biệt giữa Set.of và thu thập thành Set

`Set.of("A", "A")` ném `IllegalArgumentException` vì các phần tử truyền vào bị trùng. `Collectors.toUnmodifiableSet()` **loại trùng** trong lúc thu thập, không ném lỗi chỉ vì có nhiều phần tử bằng nhau.

`Set.copyOf(collection)` cũng tạo Set không sửa được và xử lý phần tử trùng theo quy tắc tập hợp. Nếu muốn xem trùng là lỗi dữ liệu, cần kiểm tra trùng riêng thay vì dựa vào `toUnmodifiableSet`.

## 8. Unmodifiable không có nghĩa là bất biến sâu

Kết quả từ hai collector không cho phép **thay đổi cấu trúc Collection**; chúng **không tự sao chép sâu** các đối tượng mutable được chứa bên trong.

```java
StringBuilder mutableText = new StringBuilder("draft");

List<StringBuilder> locked = java.util.stream.Stream.of(mutableText)
        .collect(Collectors.toUnmodifiableList());

// locked.add(new StringBuilder("new")); // UnsupportedOperationException
mutableText.append("-updated");

System.out.println(locked.get(0)); // draft-updated
```

Tương tự, nếu Set chứa đối tượng mutable có `equals` hoặc `hashCode` phụ thuộc trường có thể thay đổi, việc sửa trường đó sau khi đưa vào Set có thể làm các thao tác `contains` và tìm kiếm hoạt động không như mong đợi.

Để tạo dữ liệu trả về ổn định hơn, hãy **ánh xạ phần tử sang giá trị bất biến** trước khi thu thập:

```java
List<StringBuilder> builders = List.of(
        new StringBuilder("A"),
        new StringBuilder("B")
);

List<String> stableText = builders.stream()
        .map(StringBuilder::toString)
        .collect(Collectors.toUnmodifiableList());

builders.get(0).append("-changed");
System.out.println(stableText); // [A, B]
```

Với cấu trúc lồng nhau, chuyển đổi từng Collection con nếu muốn tránh sửa cả bên trong. Ví dụ `List<List<String>>` chỉ không cho sửa List ngoài khi các List con còn mutable. Có thể làm rõ quyền thay đổi:

```java
List<List<String>> nested = List.of(
        new java.util.ArrayList<>(List.of("A")),
        new java.util.ArrayList<>(List.of("B"))
);

List<List<String>> deeplyLockedForStrings = nested.stream()
        .map(List::copyOf)
        .collect(Collectors.toUnmodifiableList());
```

Ví dụ này chốt cả hai tầng List; `String` bản thân là kiểu bất biến. Nếu phần tử là một đối tượng nghiệp vụ mutable, `List.copyOf` vẫn không tạo bản sao sâu của đối tượng đó.

## 9. Tiền xử lý trước khi thu thập: filter, map và distinct

Hai collector chỉ quyết định **cách lưu kết quả cuối cùng**. Các quy tắc chọn và chuẩn hóa dữ liệu nên được diễn đạt trong pipeline.

```java
import java.util.Locale;

List<String> input = List.of("  Admin", "admin ", "Reader", "reader", " ");

Set<String> roles = input.stream()
        .map(String::strip)
        .filter(text -> !text.isEmpty())
        .map(text -> text.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableSet());

System.out.println(roles.size());          // 2
System.out.println(roles.contains("ADMIN")); // true
System.out.println(roles.contains("READER")); // true
```

Thứ tự trong Set không được cam kết. Nếu muốn **giữ lịch sử mã sau chuẩn hóa**, dùng List:

```java
List<String> normalizedHistory = input.stream()
        .map(String::strip)
        .filter(text -> !text.isEmpty())
        .map(text -> text.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableList());

System.out.println(normalizedHistory);
// [ADMIN, ADMIN, READER, READER]
```

Không cần thêm `distinct()` trước `toUnmodifiableSet()` chỉ để bảo đảm Set không chứa phần tử trùng: chính Set đã thực hiện ràng buộc đó. `distinct()` có thể có ý nghĩa nếu muốn loại trùng **trước khi thực hiện một bước biến đổi tốn kém**; cần đánh giá thứ tự, chi phí và nghĩa của pipeline.

### Muốn chọn đối tượng theo khóa thay vì equals?

`toUnmodifiableSet` không thay `groupingBy` hoặc `toMap` khi doanh nghiệp định nghĩa "duy nhất theo mã" nhưng đối tượng chứa nhiều trường:

```java
record Product(String sku, String name) {}

List<Product> products = List.of(
        new Product("P01", "Bút xanh"),
        new Product("P01", "Bút bi"),
        new Product("P02", "Vở")
);

Set<Product> set = products.stream()
        .collect(Collectors.toUnmodifiableSet());

System.out.println(set.size()); // 3: hai Product P01 khác name.
```

Nếu chỉ cần tập mã sản phẩm, hãy ánh xạ sang `sku` trước khi thu thập:

```java
Set<String> distinctSkus = products.stream()
        .map(Product::sku)
        .collect(Collectors.toUnmodifiableSet());

System.out.println(distinctSkus.size()); // 2
```

Nếu cần giữ lại **một Product đầy đủ cho mỗi SKU**, phải định nghĩa rõ cách chọn khi trùng mã, ví dụ dùng `Collectors.toMap(Product::sku, Function.identity(), mergeFunction)` và sau đó chuyển kết quả sang dạng không cho sửa. Không được dựa vào Set tự hiểu một tiêu chí trùng không có trong `equals`/`hashCode`.

## 10. Nguồn có thứ tự, chạy song song và khả năng dự đoán

### Với Stream có thứ tự

`List.stream()` có encounter order. `toUnmodifiableList` bảo toàn thứ tự đó:

```java
List<Integer> numbers = List.of(5, 1, 4, 1, 3);

List<Integer> sequential = numbers.stream()
        .collect(Collectors.toUnmodifiableList());

List<Integer> parallel = numbers.parallelStream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(sequential); // [5, 1, 4, 1, 3]
System.out.println(parallel);   // [5, 1, 4, 1, 3]
```

Thứ tự **thực thi lambda** có thể khác giữa các thread, nhưng kết quả của phép thu thập đúng hợp đồng từ nguồn có thứ tự vẫn giữ encounter order.

### Với Set không có thứ tự cam kết

`toUnmodifiableSet` bảo đảm tập hợp phần tử duy nhất, **không bảo đảm thứ tự trình bày** khi chạy tuần tự hoặc song song. Với hai đối tượng bằng nhau, không dựa vào đối tượng nào sẽ được giữ lại.

Vì vậy, nếu hệ thống cần danh sách hiển thị có thứ tự ổn định, hãy sắp xếp theo tiêu chí cụ thể và thu thập sang List:

```java
List<Integer> sortedUnique = numbers.parallelStream()
        .distinct()
        .sorted()
        .collect(Collectors.toUnmodifiableList());

System.out.println(sortedUnique); // [1, 3, 4, 5]
```

### Về hiệu năng và bộ nhớ

Cả hai collector đều là terminal operation cần **lưu toàn bộ kết quả** vào Collection. Chúng không thay thế `count`, `sum` hoặc `reduce` khi chỉ cần một số tổng hợp. Với nguồn rất lớn, cần xem bộ nhớ của kết quả, chi phí loại trùng và tình huống dữ liệu không hữu hạn.

`parallelStream()` không mặc nhiên nhanh hơn: việc tách nguồn, thu thập kết quả từng phần và kết hợp có thể tốn chi phí lớn hơn lợi ích của xử lý đồng thời, nhất là khi dữ liệu nhỏ hoặc logic nhẹ.

Hãy giữ các lambda `filter` và `map` **stateless, non-interfering**: không thêm/xóa phần tử vào nguồn đang được duyệt hoặc ghi vào một Collection dùng chung từ bên ngoài. Để Stream và collector quản lý các kết quả từng phần.

## 11. Ví dụ hoàn chỉnh: danh sách khóa học và tập kỹ năng

Giả sử hệ thống học tập lưu các lượt ghi danh. Cần hai dạng kết quả cho bảng điều khiển:

1. **Lịch sử khóa học** của những lượt ghi danh hợp lệ: giữ thứ tự và giữ cả lượt trùng.
2. **Tập kỹ năng đang học**: chỉ giữ mã kỹ năng duy nhất để kiểm tra nhanh xem một kỹ năng có xuất hiện.

Ví dụ chạy được trên **Java 17+**:

```java
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

public class UnmodifiableCollectionsDemo {
    record Enrollment(
            String studentId,
            String course,
            String skill,
            boolean active
    ) {}

    public static void main(String[] args) {
        List<Enrollment> enrollments = List.of(
                new Enrollment("S01", "Java Core", "JAVA", true),
                new Enrollment("S02", "Java Stream", " STREAM ", true),
                new Enrollment("S01", "Java Stream", "STREAM", true),
                new Enrollment("S03", "SQL", "SQL", false),
                new Enrollment("S04", "Java Core", "JAVA", true)
        );

        List<String> activeCourses = enrollments.stream()
                .filter(Enrollment::active)
                .map(Enrollment::course)
                .collect(Collectors.toUnmodifiableList());

        Set<String> activeSkills = enrollments.stream()
                .filter(Enrollment::active)
                .map(Enrollment::skill)
                .map(String::strip)
                .map(skill -> skill.toUpperCase(Locale.ROOT))
                .collect(Collectors.toUnmodifiableSet());

        System.out.println(activeCourses);
        // [Java Core, Java Stream, Java Stream, Java Core]

        System.out.println(activeSkills.size());          // 2
        System.out.println(activeSkills.contains("JAVA"));  // true
        System.out.println(activeSkills.contains("STREAM")); // true
        System.out.println(activeSkills.contains("SQL"));   // false

        // Các thao tác sửa cấu trúc kết quả đều bị từ chối.
        try {
            activeCourses.add("New Course");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Không thể sửa danh sách khóa học");
        }

        try {
            activeSkills.remove("JAVA");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Không thể sửa tập kỹ năng");
        }
    }
}
```

Diễn giải:

1. `filter(Enrollment::active)` loại lượt ghi danh không hoạt động trước khi thu thập.
2. `toUnmodifiableList` giữ hai lượt `Java Stream` và hai lượt `Java Core`, bởi vì đây là **lịch sử** chứ không phải danh mục duy nhất.
3. `toUnmodifiableSet` chuẩn hóa mã kỹ năng rồi loại trùng; khoảng trắng của `" STREAM "` không tạo thành một kỹ năng khác.
4. Hai kết quả không cho phép thêm/xóa trực tiếp; code sử dụng không thể vô tình sửa tập quyền/danh mục đã công bố.
5. Mỗi `enrollments.stream()` tạo pipeline mới. Nguồn ban đầu không bị thay đổi.

Vì ví dụ dùng `String` và `record` với dữ liệu không chứa Collection mutable bên trong, đầu ra đủ ổn định cho các giá trị trình bày này. Nếu chứa đối tượng mutable, vẫn phải thiết kế ánh xạ/bản sao phù hợp trước khi thu thập.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedOperationException` khi `add`/`remove` | Kết quả từ `toUnmodifiableList` hoặc `toUnmodifiableSet` là unmodifiable | Nếu thật sự cần sửa, dùng `toCollection(ArrayList::new)` hoặc `toCollection(HashSet::new)` |
| `NullPointerException` trong terminal operation | Stream có phần tử `null` | Quy định chính sách, lọc/biến đổi `null` trước `collect` |
| List vẫn có phần tử trùng | `toUnmodifiableList` không loại trùng | Dùng `distinct` hoặc `toUnmodifiableSet` nếu đúng nhu cầu |
| Số phần tử Set ít hơn mong đợi | Set loại những phần tử bằng nhau theo `equals`/`hashCode` | Kiểm tra phép chuẩn hóa và tiêu chí bình đẳng |
| Thứ tự Set khác khi chạy lại | Collector không cam kết thứ tự | Dùng `distinct().sorted().collect(Collectors.toUnmodifiableList())` hoặc một Set có thứ tự rõ ràng |
| Bản ghi trùng mã vẫn cùng tồn tại trong Set | `equals` xem cả trường khác mã | Ánh xạ sang mã hoặc dùng Map với chính sách gộp |
| Collection "khóa" nhưng dữ liệu bên trong vẫn đổi | Phần tử là đối tượng mutable | Tạo bản sao/DTO bất biến trước khi thu thập |
| `Collectors.toList()` được xem là chắc chắn mutable | API không cam kết mutability | Dùng `toCollection(ArrayList::new)` khi cần chắc chắn sửa được |
| `Stream.toList()` được xem là hoàn toàn tương đương `toUnmodifiableList()` | Khác biệt về hợp đồng với `null` và phiên bản Java | Chọn rõ terminal operation và quy tắc dữ liệu |
| Pipeline song song có kết quả Set không ổn định về thứ tự | Thứ tự được bỏ qua ở kết quả dạng Set | So sánh nội dung Set, không so sánh thứ tự in |

## 13. Bài tập thực hành và lời giải

Cho danh sách dữ liệu thô:

```java
List<String> rawCodes = List.of(
        " admin ", "reader", "ADMIN", "", " reader ", "export"
);
```

**Yêu cầu:**

1. Chuẩn hóa các mã bằng `strip()` và `toUpperCase(Locale.ROOT)`; bỏ mã rỗng.
2. Thu thập thành `List<String>` không chỉnh sửa được và giữ cả phần tử trùng.
3. Thu thập thành `Set<String>` không chỉnh sửa được và chỉ giữ mã duy nhất.
4. Nếu muốn một **danh sách duy nhất, giữ thứ tự gặp đầu tiên**, nên kết hợp những thao tác nào?
5. Thử thêm `null` vào nguồn bằng `Arrays.asList`, dự đoán kết quả khi gọi cả hai collector mà không lọc `null`.

**Lời giải tham khảo:**

```java
List<String> normalizedList = rawCodes.stream()
        .map(String::strip)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableList());

System.out.println(normalizedList);
// [ADMIN, READER, ADMIN, READER, EXPORT]

Set<String> normalizedSet = rawCodes.stream()
        .map(String::strip)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(Collectors.toUnmodifiableSet());

System.out.println(normalizedSet.size()); // 3

List<String> uniqueInEncounterOrder = rawCodes.stream()
        .map(String::strip)
        .filter(code -> !code.isEmpty())
        .map(code -> code.toUpperCase(Locale.ROOT))
        .distinct()
        .collect(Collectors.toUnmodifiableList());

System.out.println(uniqueInEncounterOrder);
// [ADMIN, READER, EXPORT]
```

Với câu 5, `Arrays.asList("admin", null, "reader")` tạo List có `null`. Nếu mapper gọi `String::strip` trên `null`, lỗi sẽ xảy ra **trước** `collect`. Nếu đưa `null` nguyên vẹn tới một trong hai collector, chúng cũng sẽ từ chối `null` bằng `NullPointerException`. Muốn bỏ qua, đặt `filter(Objects::nonNull)` **trước** các mapper không chấp nhận `null`.

**Câu hỏi mở rộng:** Giả sử hai `Product` có cùng SKU nhưng giá khác nhau, và nghiệp vụ cần chọn bản có thời gian cập nhật mới nhất. `toUnmodifiableSet` có đủ thông tin để quyết định không? Hãy cân nhắc `toMap` với hàm gộp dựa trên thời gian rồi chuyển sang Collection không sửa được. Cần định nghĩa rõ quy tắc khi hai thời điểm cập nhật bằng nhau.

## Ghi nhớ

`Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()` cùng tạo **Collection không cho phép sửa cấu trúc** từ Stream. Chọn **List** khi cần thứ tự và muốn giữ phần tử trùng; chọn **Set** khi cần tính duy nhất theo `equals`/`hashCode` và không cần thứ tự. Cả hai collector đều từ chối `null`, không cam kết kiểu triển khai cụ thể và không tự biến đối tượng mutable bên trong thành bất biến sâu.

Hãy chuẩn hóa, lọc và kiểm tra dữ liệu trước `collect`. Nếu cần thứ tự duy nhất, dùng `distinct` trên Stream có thứ tự rồi thu thập thành List, hoặc chọn cấu trúc Set có hợp đồng thứ tự riêng. Với pipeline song song, đánh giá nội dung kết quả theo hợp đồng của List/Set, không dựa vào thứ tự gọi lambda hay thời điểm kết hợp. Chỉ dùng các giải pháp phức tạp hơn khi yêu cầu nghiệp vụ thực sự cần.
